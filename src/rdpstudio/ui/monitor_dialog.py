"""Remote host monitor: live CPU / memory / disk / network for an SSH/OpenSSH session."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from ..protocols.ssh.monitor import DEFAULT_INTERVAL_MS, MonitorEngine
from .theme import palette
from .widgets import format_bytes

# How many samples the sparklines keep.
HISTORY = 120

INTERVALS = (
    ("Every 2 seconds", 2000),
    ("Every 5 seconds", 5000),
    ("Every 10 seconds", 10000),
    ("Every 30 seconds", 30000),
)


def format_uptime(seconds: float) -> str:
    """Human uptime: ``5d 3h``, ``3h 12m``, ``12m``."""
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class Sparkline(QWidget):
    """Tiny history plot; values are percentages (0-100) unless scaled."""

    def __init__(self, color: str = "accent", parent=None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._color = color
        self.setMinimumHeight(38)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def push(self, value: float) -> None:
        self._values.append(float(value))
        if len(self._values) > HISTORY:
            del self._values[: len(self._values) - HISTORY]
        self.update()

    def clear(self) -> None:
        self._values.clear()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = palette()
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(pal["bg2"]))
        values = self._values
        if len(values) < 2:
            painter.end()
            return
        peak = max(max(values), 1.0)
        width, height = self.width(), self.height()
        step = width / (HISTORY - 1)
        offset = width - step * (len(values) - 1)
        color = QColor(pal.get(self._color, pal["accent"]))

        points = [
            (offset + i * step, height - 2 - (v / peak) * (height - 5))
            for i, v in enumerate(values)
        ]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(color, 1.6))
        for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
        painter.end()


class _Metric(QWidget):
    """A labelled progress bar + caption (CPU, memory, disk…)."""

    def __init__(self, title: str, color: str, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        head = QHBoxLayout()
        name = QLabel(f"<b>{title}</b>")
        self.value = QLabel("—")
        self.value.setAlignment(Qt.AlignmentFlag.AlignRight)
        head.addWidget(name)
        head.addStretch(1)
        head.addWidget(self.value)
        layout.addLayout(head)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        layout.addWidget(self.bar)
        self.caption = QLabel("")
        self.caption.setObjectName("muted")
        layout.addWidget(self.caption)
        self.spark = Sparkline(color)
        layout.addWidget(self.spark)

    def set(self, percent: float | None, value_text: str, caption: str = "") -> None:
        if percent is None:
            self.bar.setValue(0)
            self.value.setText(value_text)
        else:
            self.bar.setValue(int(percent))
            self.value.setText(value_text)
            self.spark.push(percent)
        self.caption.setText(caption)


class MonitorDialog(QDialog):
    """Live monitoring panel bound to one monitor-capable session controller."""

    _sigStart = Signal()
    _sigStop = Signal()
    _sigInterval = Signal(int)

    def __init__(self, ctx, controller, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.controller = controller
        name = controller.definition.display_name()
        self.setWindowTitle(f"Monitor — {name}")
        self.resize(560, 720)

        root = QVBoxLayout(self)

        head = QHBoxLayout()
        title = QLabel(f"<b>{name}</b>")
        self.status = QLabel("connecting…")
        self.status.setObjectName("muted")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.status)
        root.addLayout(head)

        # -- summary -------------------------------------------------------
        summary = QGroupBox("Host")
        grid = QGridLayout(summary)
        self.lbl_uptime = QLabel("—")
        self.lbl_load = QLabel("—")
        self.lbl_users = QLabel("—")
        self.lbl_swap = QLabel("—")
        for col, (caption, widget) in enumerate(
            (
                ("Uptime", self.lbl_uptime),
                ("Load avg", self.lbl_load),
                ("Users", self.lbl_users),
                ("Swap", self.lbl_swap),
            )
        ):
            cap = QLabel(caption)
            cap.setObjectName("muted")
            grid.addWidget(cap, 0, col)
            grid.addWidget(widget, 1, col)
        root.addWidget(summary)

        # -- metrics --------------------------------------------------------
        self.cpu = _Metric("CPU", "good")
        self.mem = _Metric("Memory", "info")
        self.disk = _Metric("Disk (/)", "warn")
        self.net = _Metric("Network", "accent")
        for metric in (self.cpu, self.mem, self.disk, self.net):
            root.addWidget(metric)
        self.net.bar.setVisible(False)  # throughput has no natural 0-100 scale

        # -- controls --------------------------------------------------------
        controls = QFormLayout()
        self.interval = QComboBox()
        for label, ms in INTERVALS:
            self.interval.addItem(label, ms)
        default = self.interval.findData(DEFAULT_INTERVAL_MS)
        self.interval.setCurrentIndex(default if default >= 0 else 1)
        self.interval.currentIndexChanged.connect(
            lambda: self._sigInterval.emit(int(self.interval.currentData()))
        )
        controls.addRow("Refresh", self.interval)
        root.addLayout(controls)
        root.addStretch(1)

        self._thread: QThread | None = None
        self._engine: MonitorEngine | None = None
        self._start_engine()

    # ------------------------------------------------------------------
    def _start_engine(self) -> None:
        provider = getattr(self.controller, "transport_provider", None)
        if provider is None:
            self.status.setText("monitoring not supported for this session")
            return
        self._engine = MonitorEngine(provider(), int(self.interval.currentData()))
        self._thread = QThread(self)
        self._thread.setObjectName("monitor")
        self._engine.moveToThread(self._thread)
        self._engine.sample.connect(self._on_sample)
        self._engine.failed.connect(self._on_failed)
        self._sigStart.connect(self._engine.start)
        self._sigStop.connect(self._engine.stop)
        self._sigInterval.connect(self._engine.set_interval)
        self._thread.start()
        self._sigStart.emit()

    def _on_failed(self, message: str) -> None:
        self.status.setText(message)

    def _on_sample(self, data: dict) -> None:
        self.status.setText("live")

        self.lbl_uptime.setText(format_uptime(data.get("uptime_seconds", 0)))
        self.lbl_load.setText(
            f"{data.get('load1', 0):.2f} · {data.get('load5', 0):.2f} · {data.get('load15', 0):.2f}"
        )
        self.lbl_users.setText(str(data.get("users", 0)))
        swap = data.get("swap_percent", 0.0)
        self.lbl_swap.setText(f"{swap:.0f}%" if swap else "none")

        cpu = data.get("cpu_percent")
        if cpu is None:
            self.cpu.set(None, "measuring…")
        else:
            self.cpu.set(cpu, f"{cpu:.0f}%")

        total_kb = data.get("mem_total_kb", 0)
        avail_kb = data.get("mem_available_kb", 0)
        self.mem.set(
            data.get("mem_percent", 0.0),
            f"{data.get('mem_percent', 0.0):.0f}%",
            f"{format_bytes((total_kb - avail_kb) * 1024)} of {format_bytes(total_kb * 1024)} used",
        )

        d_total = data.get("disk_total_kb", 0)
        d_used = data.get("disk_used_kb", 0)
        self.disk.set(
            data.get("disk_percent", 0.0),
            f"{data.get('disk_percent', 0.0):.0f}%",
            f"{format_bytes(d_used * 1024)} of {format_bytes(d_total * 1024)} used",
        )

        rx, tx = data.get("rx_rate", 0.0), data.get("tx_rate", 0.0)
        self.net.value.setText(f"↓ {format_bytes(rx)}/s   ↑ {format_bytes(tx)}/s")
        self.net.spark.push(rx + tx)
        self.net.caption.setText("total across interfaces (excl. loopback)")

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self._shutdown()
        super().closeEvent(event)

    def _shutdown(self) -> None:
        engine, thread = self._engine, self._thread
        self._engine, self._thread = None, None
        if engine is not None:
            self._sigStop.emit()
        if thread is not None:
            thread.quit()
            if not thread.wait(2000):  # pragma: no cover - stuck probe
                thread.terminate()
                thread.wait(500)
        if engine is not None:
            engine.deleteLater()
