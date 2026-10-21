"""Remote monitoring: CPU, memory, swap, disk and network for an SSH session.

Polls the host over a second SSH channel (``SshSessionController.exec_command``)
so the interactive shell is untouched.  Parsing is a pure function so it can
be tested without a server.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from ..core.log import get_logger

log = get_logger("ui.monitor")

MONITOR_COMMAND = (
    "echo @@HOST; hostname 2>/dev/null; uname -sr 2>/dev/null; "
    "echo @@UP; cat /proc/uptime 2>/dev/null; "
    "echo @@LOAD; cat /proc/loadavg 2>/dev/null; "
    "echo @@CPU; head -n 1 /proc/stat 2>/dev/null; sleep 0.25; head -n 1 /proc/stat 2>/dev/null; "
    "echo @@MEM; grep -E '^(MemTotal|MemAvailable|MemFree|Buffers|Cached|SwapTotal|SwapFree):' "
    "/proc/meminfo 2>/dev/null; "
    "echo @@DISK; df -Pk / 2>/dev/null | tail -n 1; "
    "echo @@NET; cat /proc/net/dev 2>/dev/null"
)


def _sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("@@"):
            current = line[2:].strip()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return out


def _cpu_sample(line: str) -> tuple[int, int] | None:
    parts = line.split()
    if not parts or parts[0] != "cpu":
        return None
    try:
        values = [int(p) for p in parts[1:] if p.isdigit()]
    except ValueError:
        return None
    if len(values) < 4:
        return None
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def _meminfo(lines: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in lines:
        key, _, rest = line.partition(":")
        if not rest:
            continue
        try:
            out[key.strip()] = int(rest.split()[0])
        except (IndexError, ValueError):
            continue
    return out


def _net_totals(lines: list[str]) -> tuple[int, int]:
    rx = tx = 0
    for line in lines:
        name, _, rest = line.partition(":")
        if not rest or name.strip() == "lo":
            continue
        fields = rest.split()
        if len(fields) < 9:
            continue
        try:
            rx += int(fields[0])
            tx += int(fields[8])
        except ValueError:
            continue
    return rx, tx


def _percent(used: float, total: float) -> float:
    return max(0.0, min(100.0, 100.0 * used / total)) if total > 0 else 0.0


def parse_monitor_output(
    text: str,
    prev_net: tuple[int, int] | None = None,
    elapsed: float | None = None,
) -> dict:
    """Parse the ``MONITOR_COMMAND`` output into a stats dict.

    ``prev_net``/``elapsed`` come from the previous poll and add network
    rates; without them the rate fields are None.
    """
    sec = _sections(text)
    stats: dict = {
        "host": "",
        "os": "",
        "uptime_s": None,
        "load": None,
        "cpu_percent": None,
        "mem_total_kb": 0,
        "mem_used_kb": 0,
        "mem_percent": 0.0,
        "swap_total_kb": 0,
        "swap_used_kb": 0,
        "swap_percent": 0.0,
        "disk_total_kb": 0,
        "disk_used_kb": 0,
        "disk_percent": 0.0,
        "disk_mount": "",
        "net_rx": 0,
        "net_tx": 0,
        "net_rx_rate": None,
        "net_tx_rate": None,
    }

    host_lines = [ln.strip() for ln in sec.get("HOST", []) if ln.strip()]
    if host_lines:
        stats["host"] = host_lines[0]
    if len(host_lines) > 1:
        stats["os"] = host_lines[1]

    for line in sec.get("UP", []):
        try:
            stats["uptime_s"] = float(line.split()[0])
            break
        except (IndexError, ValueError):
            continue

    for line in sec.get("LOAD", []):
        parts = line.split()
        if len(parts) >= 3:
            try:
                stats["load"] = tuple(float(p) for p in parts[:3])
            except ValueError:
                pass
        break

    samples = [s for s in (_cpu_sample(ln) for ln in sec.get("CPU", [])) if s]
    if len(samples) >= 2:
        total_delta = samples[1][0] - samples[0][0]
        idle_delta = samples[1][1] - samples[0][1]
        if total_delta > 0:
            stats["cpu_percent"] = max(
                0.0, min(100.0, 100.0 * (1.0 - idle_delta / total_delta))
            )

    mem = _meminfo(sec.get("MEM", []))
    total = mem.get("MemTotal", 0)
    if total:
        available = mem.get("MemAvailable")
        if available is None:
            available = mem.get("MemFree", 0) + mem.get("Buffers", 0) + mem.get("Cached", 0)
        used = max(0, total - available)
        stats["mem_total_kb"] = total
        stats["mem_used_kb"] = used
        stats["mem_percent"] = _percent(used, total)
    swap_total = mem.get("SwapTotal", 0)
    swap_used = max(0, swap_total - mem.get("SwapFree", 0)) if swap_total else 0
    stats["swap_total_kb"] = swap_total
    stats["swap_used_kb"] = swap_used
    stats["swap_percent"] = _percent(swap_used, swap_total)

    for line in sec.get("DISK", []):
        parts = line.split()
        if len(parts) < 6:
            continue
        try:
            total_kb = int(parts[1])
            used_kb = int(parts[2])
        except ValueError:
            continue
        stats["disk_total_kb"] = total_kb
        stats["disk_used_kb"] = used_kb
        stats["disk_percent"] = _percent(used_kb, total_kb)
        stats["disk_mount"] = parts[5]
        break

    rx, tx = _net_totals(sec.get("NET", []))
    stats["net_rx"], stats["net_tx"] = rx, tx
    if prev_net is not None and elapsed and elapsed > 0:
        stats["net_rx_rate"] = max(0.0, (rx - prev_net[0]) / elapsed)
        stats["net_tx_rate"] = max(0.0, (tx - prev_net[1]) / elapsed)
    return stats


def format_bytes(value: float, suffix: str = "") -> str:
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}{suffix}" if unit != "B" else f"{int(value)} B{suffix}"
        value /= 1024.0
    return f"{value:.1f} TB{suffix}"


def format_uptime(seconds: float | None) -> str:
    if not seconds or seconds < 0:
        return "—"
    seconds = int(seconds)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class RemoteMonitorDialog(QDialog):
    """Non-modal live stats window for one SSH session."""

    statsReady = Signal(dict)
    pollFailed = Signal(str)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.controller = controller
        defn = controller.definition
        self.setWindowTitle(f"Remote monitoring — {defn.display_name()}")
        self.resize(440, 460)
        self._closed = False
        self._busy = False
        self._prev_net: tuple[int, int] | None = None
        self._prev_time: float | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(12)

        self.host_label = QLabel(defn.target())
        self.host_label.setObjectName("sessionInfo")
        lay.addWidget(self.host_label)
        self.os_label = QLabel("")
        self.os_label.setObjectName("caption")
        lay.addWidget(self.os_label)

        form = QFormLayout()
        form.setSpacing(10)
        self.cpu_bar = self._bar()
        self.mem_bar = self._bar()
        self.swap_bar = self._bar()
        self.disk_bar = self._bar()
        form.addRow("CPU", self.cpu_bar)
        form.addRow("Memory", self.mem_bar)
        form.addRow("Swap", self.swap_bar)
        form.addRow("Disk /", self.disk_bar)
        lay.addLayout(form)

        self.detail = QLabel("Collecting…")
        self.detail.setObjectName("caption")
        self.detail.setWordWrap(True)
        lay.addWidget(self.detail)

        self.error_label = QLabel("")
        self.error_label.setObjectName("caption")
        self.error_label.setWordWrap(True)
        lay.addWidget(self.error_label)

        lay.addStretch(1)

        row = QHBoxLayout()
        self.auto = QCheckBox("Auto-refresh")
        self.auto.setChecked(True)
        self.auto.toggled.connect(self._set_auto)
        row.addWidget(self.auto)
        row.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        lay.addLayout(row)

        self.statsReady.connect(self._apply)
        self.pollFailed.connect(self._fail)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    @staticmethod
    def _bar() -> QProgressBar:
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        bar.setFormat("%p%")
        bar.setFixedHeight(16)
        return bar

    def _set_auto(self, enabled: bool) -> None:
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()

    def refresh(self) -> None:
        if self._closed or self._busy:
            return
        self._busy = True
        threading.Thread(target=self._poll, name="remote-monitor", daemon=True).start()

    def _poll(self) -> None:
        try:
            text = self.controller.exec_command(MONITOR_COMMAND, timeout=6.0)
            now = time.monotonic()
            elapsed = (now - self._prev_time) if self._prev_time else None
            stats = parse_monitor_output(text, self._prev_net, elapsed)
            self._prev_net = (stats["net_rx"], stats["net_tx"])
            self._prev_time = now
            if not self._closed:
                self.statsReady.emit(stats)
        except Exception as exc:  # noqa: BLE001 — show the reason, keep polling
            log.debug("monitor poll failed", exc_info=True)
            if not self._closed:
                self.pollFailed.emit(str(exc))
        finally:
            self._busy = False

    def _apply(self, stats: dict) -> None:
        if self._closed:
            return
        self.error_label.setText("")
        self.os_label.setText(stats.get("os", ""))
        if stats.get("host"):
            self.host_label.setText(stats["host"])

        cpu = stats.get("cpu_percent")
        self.cpu_bar.setValue(int(cpu) if cpu is not None else 0)
        self.cpu_bar.setFormat(f"{cpu:.0f}%" if cpu is not None else "—")
        self.mem_bar.setValue(int(stats["mem_percent"]))
        self.mem_bar.setFormat(
            f"{format_bytes(stats['mem_used_kb'] * 1024)} / "
            f"{format_bytes(stats['mem_total_kb'] * 1024)}"
        )
        self.swap_bar.setValue(int(stats["swap_percent"]))
        self.swap_bar.setFormat(
            f"{format_bytes(stats['swap_used_kb'] * 1024)} / "
            f"{format_bytes(stats['swap_total_kb'] * 1024)}"
        )
        self.disk_bar.setValue(int(stats["disk_percent"]))
        self.disk_bar.setFormat(
            f"{format_bytes(stats['disk_used_kb'] * 1024)} / "
            f"{format_bytes(stats['disk_total_kb'] * 1024)}"
        )

        parts = []
        load = stats.get("load")
        if load:
            parts.append("Load " + " ".join(f"{v:.2f}" for v in load))
        parts.append("Uptime " + format_uptime(stats.get("uptime_s")))
        line = "   ·   ".join(parts)
        net = [
            f"↓ {format_bytes(stats['net_rx'])}",
            f"↑ {format_bytes(stats['net_tx'])}",
        ]
        if stats.get("net_rx_rate") is not None:
            net[0] = f"↓ {format_bytes(stats['net_rx_rate'])}/s"
            net[1] = f"↑ {format_bytes(stats['net_tx_rate'])}/s"
        self.detail.setText(f"{line}\nNetwork  {'   '.join(net)}")

    def _fail(self, message: str) -> None:
        if self._closed:
            return
        self.error_label.setText(message)
        self.detail.setText("Waiting for the session…" if "not connected" in message else "—")

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt naming
        self._closed = True
        self._timer.stop()
        super().closeEvent(event)


__all__ = [
    "MONITOR_COMMAND",
    "RemoteMonitorDialog",
    "format_bytes",
    "format_uptime",
    "parse_monitor_output",
]
