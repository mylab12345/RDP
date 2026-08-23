"""Remote host monitoring over an existing SSH transport.

A :class:`MonitorEngine` periodically runs a small, read-only probe on the
remote host and reports CPU / memory / disk / load / network figures. It
borrows the *live* transport from the session's worker (paramiko multiplexes
channels), so monitoring costs one extra channel and no extra login.

Design notes
------------
* The probe is a single ``sh`` script reading ``/proc`` and ``df``; one round
  trip per sample instead of a dozen. It is strictly read-only and contains
  no interpolated user data.
* CPU percentage needs two ``/proc/stat`` readings, so the first sample
  reports ``cpu_percent = None`` and every later one is a real delta.
* Everything runs on the engine's own thread; results arrive as Qt signals.
"""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from ...core.log import get_logger

log = get_logger("ssh.monitor")

# Read-only probe. Kept as one script so a sample is a single round trip.
# Nothing here is user-controlled, so there is no injection surface.
PROBE_SCRIPT = r"""
echo "###uptime"; cat /proc/uptime 2>/dev/null
echo "###loadavg"; cat /proc/loadavg 2>/dev/null
echo "###stat"; grep -E '^cpu ' /proc/stat 2>/dev/null
echo "###meminfo"; grep -E '^(MemTotal|MemAvailable|MemFree|SwapTotal|SwapFree):' /proc/meminfo 2>/dev/null
echo "###netdev"; cat /proc/net/dev 2>/dev/null
echo "###df"; df -kP / 2>/dev/null | tail -n +2
echo "###who"; who 2>/dev/null | wc -l
echo "###end"
"""

DEFAULT_INTERVAL_MS = 3000
# Hard ceiling on probe output; a hostile/broken host cannot balloon memory.
_MAX_PROBE_BYTES = 256 * 1024
# A monitoring sample should be cheap; if the host is slower than this the
# connection is effectively dead and the panel reports it instead of
# stalling (5 s also bounds how long teardown can wait for a probe).
_PROBE_TIMEOUT = 5.0


@dataclass
class HostSample:
    """One point-in-time reading of the remote host."""

    ok: bool = True
    error: str = ""
    uptime_seconds: float = 0.0
    load1: float = 0.0
    load5: float = 0.0
    load15: float = 0.0
    cpu_percent: float | None = None
    cpu_cores: int = 0
    mem_total_kb: int = 0
    mem_available_kb: int = 0
    swap_total_kb: int = 0
    swap_free_kb: int = 0
    disk_total_kb: int = 0
    disk_used_kb: int = 0
    net_rx_bytes: int = 0
    net_tx_bytes: int = 0
    rx_rate: float = 0.0  # bytes/s since previous sample
    tx_rate: float = 0.0
    users: int = 0

    # -- derived ------------------------------------------------------
    @property
    def mem_used_kb(self) -> int:
        return max(0, self.mem_total_kb - self.mem_available_kb)

    @property
    def mem_percent(self) -> float:
        return _percent(self.mem_used_kb, self.mem_total_kb)

    @property
    def swap_used_kb(self) -> int:
        return max(0, self.swap_total_kb - self.swap_free_kb)

    @property
    def swap_percent(self) -> float:
        return _percent(self.swap_used_kb, self.swap_total_kb)

    @property
    def disk_percent(self) -> float:
        return _percent(self.disk_used_kb, self.disk_total_kb)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "error": self.error,
            "uptime_seconds": self.uptime_seconds,
            "load1": self.load1,
            "load5": self.load5,
            "load15": self.load15,
            "cpu_percent": self.cpu_percent,
            "cpu_cores": self.cpu_cores,
            "mem_total_kb": self.mem_total_kb,
            "mem_available_kb": self.mem_available_kb,
            "mem_percent": self.mem_percent,
            "swap_percent": self.swap_percent,
            "disk_total_kb": self.disk_total_kb,
            "disk_used_kb": self.disk_used_kb,
            "disk_percent": self.disk_percent,
            "rx_rate": self.rx_rate,
            "tx_rate": self.tx_rate,
            "users": self.users,
        }


def _percent(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return max(0.0, min(100.0, part / whole * 100.0))


def _sections(text: str) -> dict[str, list[str]]:
    """Split probe output into ``{section: [lines]}``."""
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("###"):
            current = line[3:].strip()
            out[current] = []
        elif current:
            out[current].append(line)
    return out


@dataclass
class _Prev:
    """Previous counters, needed to turn totals into rates."""

    cpu_total: int = 0
    cpu_idle: int = 0
    rx: int = 0
    tx: int = 0
    have: bool = False
    fields: dict = field(default_factory=dict)


def parse_probe(text: str, prev: _Prev | None = None) -> tuple[HostSample, _Prev]:
    """Parse probe output into a :class:`HostSample` (pure — unit tested)."""
    prev = prev or _Prev()
    sec = _sections(text)
    s = HostSample()

    up = sec.get("uptime", [])
    if up and up[0].split():
        s.uptime_seconds = _to_float(up[0].split()[0])

    load = sec.get("loadavg", [])
    if load and len(load[0].split()) >= 3:
        parts = load[0].split()
        s.load1, s.load5, s.load15 = (_to_float(p) for p in parts[:3])

    # CPU: percentage is a delta between two /proc/stat readings.
    new = _Prev()
    stat_lines = sec.get("stat", [])
    if stat_lines and stat_lines[0].startswith("cpu"):
        vals = [_to_int(v) for v in stat_lines[0].split()[1:]]
        if len(vals) >= 4:
            total = sum(vals)
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            new.cpu_total, new.cpu_idle = total, idle
            if prev.have and total > prev.cpu_total:
                dt = total - prev.cpu_total
                di = idle - prev.cpu_idle
                s.cpu_percent = _percent(dt - di, dt)

    for line in sec.get("meminfo", []):
        key, _, rest = line.partition(":")
        value = _to_int(rest.strip().split()[0]) if rest.strip() else 0
        if key == "MemTotal":
            s.mem_total_kb = value
        elif key == "MemAvailable":
            s.mem_available_kb = value
        elif key == "MemFree" and not s.mem_available_kb:
            s.mem_available_kb = value  # pre-3.14 kernels
        elif key == "SwapTotal":
            s.swap_total_kb = value
        elif key == "SwapFree":
            s.swap_free_kb = value

    # Network: sum all interfaces except loopback.
    rx = tx = 0
    for line in sec.get("netdev", []):
        name, _, rest = line.partition(":")
        name = name.strip()
        if not rest or name in ("lo", "Inter-|   Receive", "face"):
            continue
        cols = rest.split()
        if len(cols) >= 9:
            rx += _to_int(cols[0])
            tx += _to_int(cols[8])
    s.net_rx_bytes, s.net_tx_bytes = rx, tx
    new.rx, new.tx = rx, tx
    if prev.have:
        # Counters can wrap or reset (interface down); clamp to >= 0.
        s.rx_rate = max(0, rx - prev.rx)
        s.tx_rate = max(0, tx - prev.tx)

    df = sec.get("df", [])
    if df:
        cols = df[0].split()
        if len(cols) >= 4:
            s.disk_total_kb = _to_int(cols[1])
            s.disk_used_kb = _to_int(cols[2])

    who = sec.get("who", [])
    if who:
        s.users = _to_int(who[0].strip())

    new.have = True
    return s, new


def _to_int(text: str) -> int:
    try:
        return int(text)
    except (TypeError, ValueError):
        return 0


def _to_float(text: str) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return 0.0


class MonitorEngine(QObject):
    """Polls a remote host over an existing transport. Lives on its own thread."""

    sample = Signal(dict)   # HostSample.to_dict()
    failed = Signal(str)

    def __init__(self, transport_provider, interval_ms: int = DEFAULT_INTERVAL_MS) -> None:
        super().__init__()
        self._transport_provider = transport_provider
        self._interval_ms = max(1000, int(interval_ms))
        self._prev = _Prev()
        self._timer: QTimer | None = None
        self._running = False
        self._last_sample_at: float = 0.0
        self._probe_chan = None  # channel of an in-flight probe (same thread)

    # ------------------------------------------------------------------
    @Slot()
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        # Created here so the timer belongs to the engine's own thread.
        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self.poll)
        self._timer.start()
        self.poll()  # don't make the user wait a full interval for row one

    @Slot()
    def stop(self) -> None:
        self._running = False
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        # Unblock a probe that is currently sitting in recv() so teardown
        # (tab switches, window close) is prompt.  Same thread → no race.
        chan = self._probe_chan
        if chan is not None:
            try:
                chan.close()
            except Exception:  # noqa: BLE001
                pass
            self._probe_chan = None

    @Slot(int)
    def set_interval(self, interval_ms: int) -> None:
        self._interval_ms = max(1000, int(interval_ms))
        if self._timer is not None:
            self._timer.setInterval(self._interval_ms)

    @Slot()
    def poll(self) -> None:
        if not self._running:
            return
        try:
            text = self._run_probe()
        except Exception as exc:  # noqa: BLE001 - never kill the poll loop
            if not self._running:
                return  # stopped mid-probe — nothing to report
            log.debug("monitor probe failed: %s", exc)
            self.failed.emit(str(exc))
            return
        if not self._running:
            return
        try:
            sample, self._prev = parse_probe(text, self._prev)
        except Exception as exc:  # noqa: BLE001 - malformed output
            log.debug("monitor parse failed: %s", exc)
            self.failed.emit(f"unreadable probe output: {exc}")
            return
        # Convert byte deltas to per-second rates using the *actual* elapsed
        # time between samples (a slow probe makes the real cadence longer
        # than the configured interval).
        now = time.monotonic()
        seconds = (
            now - self._last_sample_at
            if self._last_sample_at
            else self._interval_ms / 1000.0
        )
        self._last_sample_at = now
        seconds = max(0.25, seconds)
        sample.rx_rate /= seconds
        sample.tx_rate /= seconds
        self.sample.emit(sample.to_dict())

    # ------------------------------------------------------------------
    def _run_probe(self) -> str:
        transport = self._transport_provider()
        if transport is None or not transport.is_active():
            raise RuntimeError("session is not connected")
        chan = transport.open_session(timeout=_PROBE_TIMEOUT)
        self._probe_chan = chan
        try:
            chan.settimeout(_PROBE_TIMEOUT)
            chan.exec_command(f"sh -c {shlex.quote(PROBE_SCRIPT)}")
            chunks: list[bytes] = []
            size = 0
            while True:
                if not self._running:
                    raise RuntimeError("monitor stopped")
                data = chan.recv(32768)
                if not data:
                    break
                size += len(data)
                if size > _MAX_PROBE_BYTES:
                    raise RuntimeError("probe output too large")
                chunks.append(data)
            return b"".join(chunks).decode("utf-8", "replace")
        finally:
            self._probe_chan = None
            try:
                chan.close()
            except Exception:  # noqa: BLE001
                pass
