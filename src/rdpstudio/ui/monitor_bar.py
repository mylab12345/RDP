"""MobaXterm-style live monitoring strip under the session workspace.

Always-on, compact view of the active SSH session: CPU, memory, disk and
network, sampled over the session's existing transport.  It follows tab
switches and disappears for tabs that cannot be monitored (RDP/local).
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QWidget,
)

from ..core.log import get_logger
from ..core.plugin import SessionState
from .monitor_dialog import MONITOR_COMMAND, format_bytes, format_uptime, parse_monitor_output

log = get_logger("ui.monitor_bar")

_INTERVAL_MS = 2000


class _Meter(QWidget):
    """Title + slim bar + value, the compact MobaXterm-style cell."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monitorMeter")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        name = QLabel(title)
        name.setObjectName("monitorTitle")
        lay.addWidget(name)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(62, 6)
        lay.addWidget(self.bar)

        self.value = QLabel("—")
        self.value.setObjectName("monitorValue")
        self.value.setMinimumWidth(38)
        lay.addWidget(self.value)

    def set(self, percent: float | None, text: str) -> None:
        self.bar.setValue(0 if percent is None else int(max(0.0, min(100.0, percent))))
        self.value.setText(text)


class MonitorBar(QWidget):
    """Live stats for one bound SSH controller; hidden otherwise."""

    statsReady = Signal(dict)
    pollFailed = Signal(str)
    openDetails = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monitorBar")
        self.setFixedHeight(32)
        self._controller = None
        self._bound_key = None
        self._generation = 0
        self._busy = False
        self._closed = False
        self._prev_net: tuple[int, int] | None = None
        self._prev_time: float | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 8, 2)
        lay.setSpacing(12)

        title = QLabel("MONITOR")
        title.setObjectName("monitorTitle")
        lay.addWidget(title)

        self.host = QLabel("")
        self.host.setObjectName("monitorHost")
        lay.addWidget(self.host)

        self.cpu = _Meter("CPU")
        self.mem = _Meter("MEM")
        self.disk = _Meter("DISK")
        for meter in (self.cpu, self.mem, self.disk):
            lay.addWidget(meter)

        self.net = QLabel("NET —")
        self.net.setObjectName("monitorValue")
        lay.addWidget(self.net)

        self.detail = QLabel("")
        self.detail.setObjectName("monitorHost")
        lay.addWidget(self.detail)

        lay.addStretch(1)

        self.btn_details = QPushButton("Details")
        self.btn_details.setObjectName("ghost")
        self.btn_details.setProperty("iconOnly", False)
        self.btn_details.setFixedHeight(22)
        self.btn_details.setStyleSheet("font-size: 11px; padding: 0px 8px;")
        self.btn_details.setToolTip("Open the full remote monitor window")
        self.btn_details.clicked.connect(self.openDetails.emit)
        lay.addWidget(self.btn_details)

        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self.statsReady.connect(self._apply)
        self.pollFailed.connect(self._fail)
        self.hide()

    # ------------------------------------------------------------------
    def controller(self):
        return self._controller

    def bind(self, controller) -> None:
        """Follow the active tab.  Safe to call on every switch/state change."""
        state = controller.state() if controller is not None else None
        key = (controller, state)
        if key == self._bound_key:
            return
        self._bound_key = key
        self._generation += 1
        self._timer.stop()
        self._busy = False
        self._controller = controller
        self._prev_net = None
        self._prev_time = None

        monitorable = (
            controller is not None
            and hasattr(controller, "exec_command")
            and state == SessionState.CONNECTED
        )
        if not monitorable:
            self._reset()
            self.hide()
            return

        try:
            self.host.setText(controller.definition.display_name())
        except Exception:  # noqa: BLE001 - a label must never break a tab switch
            self.host.setText("session")
        self._reset()
        self.show()
        self._timer.start()
        self.refresh()

    def _reset(self) -> None:
        for meter in (self.cpu, self.mem, self.disk):
            meter.set(None, "—")
        self.net.setText("NET —")
        self.detail.setText("")

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        controller = self._controller
        if self._closed or self._busy or controller is None or not self.isVisible():
            return
        self._busy = True
        generation = self._generation
        threading.Thread(
            target=self._poll,
            args=(controller, generation),
            name="monitor-bar",
            daemon=True,
        ).start()

    def _poll(self, controller, generation: int) -> None:
        try:
            text = controller.exec_command(MONITOR_COMMAND, timeout=6.0)
            now = time.monotonic()
            elapsed = (now - self._prev_time) if self._prev_time else None
            stats = parse_monitor_output(text, self._prev_net, elapsed)
            if generation == self._generation and not self._closed:
                self._prev_net = (stats["net_rx"], stats["net_tx"])
                self._prev_time = now
                self.statsReady.emit(stats)
        except Exception as exc:  # noqa: BLE001 - keep the bar, show the reason
            log.debug("monitor bar poll failed", exc_info=True)
            if not self._closed and generation == self._generation:
                self.pollFailed.emit(str(exc))
        finally:
            if generation == self._generation:
                self._busy = False

    def _apply(self, stats: dict) -> None:
        cpu = stats.get("cpu_percent")
        self.cpu.set(cpu, "—" if cpu is None else f"{cpu:.0f}%")
        self.mem.set(
            stats["mem_percent"],
            "—" if stats["mem_total_kb"] == 0
            else format_bytes(stats["mem_used_kb"] * 1024).replace(" ", ""),
        )
        self.disk.set(
            stats["disk_percent"],
            "—" if stats["disk_total_kb"] == 0
            else format_bytes(stats["disk_used_kb"] * 1024).replace(" ", ""),
        )
        if stats.get("net_rx_rate") is not None:
            self.net.setText(
                f"NET ↓ {format_bytes(stats['net_rx_rate'])}/s  "
                f"↑ {format_bytes(stats['net_tx_rate'])}/s"
            )
        else:
            self.net.setText("NET measuring…")

        bits = []
        load = stats.get("load")
        if load:
            bits.append("Load " + " ".join(f"{v:.2f}" for v in load))
        if stats.get("uptime_s"):
            bits.append("Up " + format_uptime(stats["uptime_s"]))
        self.detail.setText("  ·  ".join(bits))
        if stats.get("host"):
            self.host.setText(stats["host"])

    def _fail(self, message: str) -> None:
        self.detail.setText("monitor unavailable")
        self.detail.setToolTip(message)
        self.net.setText("NET —")

    # ------------------------------------------------------------------
    def shutdown(self) -> None:
        self._closed = True
        self._timer.stop()
        self._controller = None


__all__ = ["MonitorBar"]
