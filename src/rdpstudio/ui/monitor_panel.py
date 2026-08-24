"""Bottom-docked remote monitoring panel — beautiful natural bento design 2026.

A compact, always-available strip along the bottom of the main window that
shows live CPU / memory / disk / network figures for the *active* monitor-capable
remote session.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..protocols.ssh.monitor import DEFAULT_INTERVAL_MS, MonitorEngine
from .monitor_dialog import INTERVALS, Sparkline, format_uptime
from .theme import palette
from .widgets import format_bytes


class _MetricCell(QWidget):
    """One bento metric: title + value, bar, caption or sparkline — natural."""

    def __init__(self, title: str, color: str, with_spark: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCell")
        pal = palette()
        self.setStyleSheet(
            f"""
            QWidget#metricCell {{
                background: {pal['bg2']};
                border: 1.5px solid {pal['border_subtle']};
                border-radius: 12px;
            }}
            QWidget#metricCell:hover {{
                border-color: {pal['border']};
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(8)
        name = QLabel(title)
        name.setObjectName("metricTitle")
        name.setStyleSheet(f"font-size: 10.5px; font-weight: 700; color: {pal['fg_dim']}; letter-spacing: 0.6px;")
        self.value = QLabel("—")
        self.value.setObjectName("metricValue")
        self.value.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {pal['fg']};")
        head.addWidget(name)
        head.addStretch(1)
        head.addWidget(self.value)
        layout.addLayout(head)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setObjectName("metricBar")
        layout.addWidget(self.bar)

        if with_spark:
            self.spark = Sparkline(color)
            self.spark.setFixedHeight(24)
            layout.addWidget(self.spark)
            self.caption = None
        else:
            self.spark = None
            self.caption = QLabel("")
            self.caption.setObjectName("muted")
            self.caption.setStyleSheet("font-size: 11px;")
            layout.addWidget(self.caption)

    def set(self, percent: float | None, value_text: str, caption: str = "") -> None:
        if percent is None:
            self.bar.setValue(0)
        else:
            self.bar.setValue(int(max(0, min(100, percent))))
        self.value.setText(value_text)
        if self.spark is not None and percent is not None:
            self.spark.push(percent)
        elif self.caption is not None:
            self.caption.setText(caption)

    def set_rate(self, value_text: str, spark_value: float | None = None) -> None:
        self.bar.setVisible(False)
        self.value.setText(value_text)
        if self.spark is not None and spark_value is not None:
            self.spark.push(spark_value)

    def reset(self) -> None:
        self.bar.setValue(0)
        self.value.setText("—")
        if self.spark is not None:
            self.spark.clear()
        if self.caption is not None:
            self.caption.setText("")


class MonitorPanel(QWidget):
    """Live monitoring strip — beautiful natural bento."""

    openFullMonitor = Signal()

    _sigStart = Signal()
    _sigStop = Signal()
    _sigInterval = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("monitorPanel")
        self._controller = None
        self._thread: QThread | None = None
        self._engine: MonitorEngine | None = None
        self._paused = False
        self._bound_name = ""

        pal = palette()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header — bento pill style
        header = QWidget()
        header.setObjectName("monitorHeader")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 8, 12, 8)
        hl.setSpacing(10)

        icon_lbl = QLabel("▤")
        icon_lbl.setStyleSheet(f"color: {pal['accent']}; font-size: 14px; font-weight: 800;")
        hl.addWidget(icon_lbl)

        title = QLabel("Remote monitor")
        title.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {pal['fg']}; letter-spacing: 0.3px;")
        hl.addWidget(title)

        self.host_label = QLabel("")
        self.host_label.setStyleSheet(f"font-size: 12px; color: {pal['fg_dim']};")
        hl.addWidget(self.host_label)

        self.status = QLabel("idle")
        self.status.setObjectName("monitorStatus")
        hl.addWidget(self.status)

        hl.addStretch(1)

        self.interval = QComboBox()
        self.interval.setToolTip("Probe refresh rate")
        self.interval.setMinimumHeight(28)
        for label, ms in INTERVALS:
            self.interval.addItem(label, ms)
        default = self.interval.findData(DEFAULT_INTERVAL_MS)
        self.interval.setCurrentIndex(default if default >= 0 else 1)
        self.interval.currentIndexChanged.connect(self._on_interval_changed)
        hl.addWidget(self.interval)

        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.setObjectName("subtle")
        self.btn_pause.setFixedWidth(88)
        self.btn_pause.setMinimumHeight(28)
        self.btn_pause.clicked.connect(self.toggle_pause)
        hl.addWidget(self.btn_pause)

        self.btn_details = QPushButton("Details")
        self.btn_details.setObjectName("subtle")
        self.btn_details.setFixedWidth(76)
        self.btn_details.setMinimumHeight(28)
        self.btn_details.setToolTip("Open the full remote monitor window")
        self.btn_details.clicked.connect(self.openFullMonitor.emit)
        hl.addWidget(self.btn_details)

        self.btn_collapse = QPushButton("⌄")
        self.btn_collapse.setObjectName("ghost")
        self.btn_collapse.setFixedSize(32, 28)
        self.btn_collapse.setToolTip("Collapse / expand the monitor panel")
        self.btn_collapse.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        hl.addWidget(self.btn_collapse)

        root.addWidget(header)

        self._hairline = QFrame()
        self._hairline.setFrameShape(QFrame.Shape.HLine)
        self._hairline.setObjectName("hairline")
        self._hairline.setFixedHeight(1)
        root.addWidget(self._hairline)

        # Body — bento grid
        body = QWidget()
        body.setObjectName("monitorBody")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(12, 10, 12, 12)
        bl.setSpacing(10)

        self.cpu = _MetricCell("CPU", "good", with_spark=True)
        self.mem = _MetricCell("Memory", "info")
        self.disk = _MetricCell("Disk (/)", "warn")
        self.net = _MetricCell("Network", "accent", with_spark=True)
        self.net.bar.setVisible(False)
        for cell in (self.cpu, self.mem, self.disk, self.net):
            bl.addWidget(cell, 1)

        summary = QWidget()
        summary.setObjectName("monitorSummary")
        sl = QVBoxLayout(summary)
        sl.setContentsMargins(14, 10, 14, 10)
        sl.setSpacing(6)
        self.lbl_uptime = QLabel("Uptime —")
        self.lbl_load = QLabel("Load —")
        self.lbl_users = QLabel("Users —")
        self.lbl_swap = QLabel("Swap —")
        for lbl in (self.lbl_uptime, self.lbl_load, self.lbl_users, self.lbl_swap):
            lbl.setStyleSheet(f"font-size: 11.5px; color: {pal['fg_dim']};")
            sl.addWidget(lbl)
        bl.addWidget(summary, 0)

        self.placeholder = QLabel(
            "🌿 No monitor-capable remote session — open or focus any SSH host to see live metrics"
        )
        self.placeholder.setObjectName("muted")
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setStyleSheet(
            f"""
            font-size: 12.5px;
            color: {pal['fg_dim']};
            background: {pal['bg3']};
            border: 1px dashed {pal['border']};
            border-radius: 12px;
            padding: 16px;
            """
        )

        self.body = body
        root.addWidget(body)
        root.addWidget(self.placeholder)

        self._collapsed = False
        self.set_collapsed(False)
        self._no_session()

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        self._refresh_body_visibility()
        self.btn_collapse.setText("⌃" if collapsed else "⌄")
        self.btn_collapse.setToolTip(
            "Expand the monitor panel" if collapsed else "Collapse the monitor panel"
        )

    def _refresh_body_visibility(self) -> None:
        has_engine = self._engine is not None
        self.body.setVisible(not self._collapsed and has_engine)
        self.placeholder.setVisible(not self._collapsed and not has_engine)

    def bind(self, controller) -> None:
        if controller is self._controller:
            return
        self._teardown_engine()
        self._controller = controller
        if controller is None:
            self._no_session()
            return
        provider = getattr(controller, "transport_provider", None)
        if provider is None:
            self._no_session()
            return

        name = ""
        try:
            name = controller.definition.display_name()
        except Exception:
            name = "session"
        self._bound_name = name
        self.host_label.setText(f"— {name}")
        self.status.setText("connecting…")

        self._engine = MonitorEngine(provider(), int(self.interval.currentData()))
        self._thread = QThread(self)
        self._thread.setObjectName("monitor-panel")
        self._engine.moveToThread(self._thread)
        self._engine.sample.connect(self._on_sample)
        self._engine.failed.connect(self._on_failed)
        self._sigStart.connect(self._engine.start)
        self._sigStop.connect(self._engine.stop)
        self._sigInterval.connect(self._engine.set_interval)
        self._thread.start()
        self._sigStart.emit()
        if self._paused:
            self._sigStop.emit()
        self._refresh_body_visibility()

    def _no_session(self) -> None:
        self._bound_name = ""
        self.host_label.setText("")
        self.status.setText("no session")
        self.btn_pause.setEnabled(False)
        for cell in (self.cpu, self.mem, self.disk, self.net):
            cell.reset()
        self.lbl_uptime.setText("Uptime —")
        self.lbl_load.setText("Load —")
        self.lbl_users.setText("Users —")
        self.lbl_swap.setText("Swap —")
        self._refresh_body_visibility()

    def _teardown_engine(self) -> None:
        engine, thread = self._engine, self._thread
        self._engine, self._thread = None, None
        self.btn_pause.setEnabled(True)
        if engine is not None:
            try:
                self._sigStart.disconnect(engine.start)
                self._sigStop.disconnect(engine.stop)
                self._sigInterval.disconnect(engine.set_interval)
            except (RuntimeError, TypeError):
                pass
            self._sigStop.emit()
        if thread is not None:
            thread.quit()
            if not thread.wait(800):
                thread.terminate()
                thread.wait(200)
        if engine is not None:
            try:
                engine.deleteLater()
            except RuntimeError:
                pass

    def _on_interval_changed(self, _index: int) -> None:
        if self._engine is not None:
            self._sigInterval.emit(int(self.interval.currentData()))

    def toggle_pause(self) -> None:
        if self._engine is None:
            return
        self._paused = not self._paused
        if self._paused:
            self._sigStop.emit()
            self.status.setText("paused")
            self.btn_pause.setText("▶ Resume")
        else:
            self._sigStart.emit()
            self.btn_pause.setText("⏸ Pause")

    def _on_failed(self, message: str) -> None:
        self.status.setText(message or "probe failed")

    def _on_sample(self, data: dict) -> None:
        if self._paused:
            return
        self.status.setText("live")
        self.lbl_uptime.setText(f"Uptime {format_uptime(data.get('uptime_seconds', 0))}")
        self.lbl_load.setText(
            f"Load {data.get('load1', 0):.2f} · {data.get('load5', 0):.2f} · {data.get('load15', 0):.2f}"
        )
        self.lbl_users.setText(f"Users {data.get('users', 0)}")
        swap = data.get("swap_percent", 0.0)
        self.lbl_swap.setText(f"Swap {swap:.0f}%" if swap else "Swap —")

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
            f"{format_bytes((total_kb - avail_kb) * 1024)} / {format_bytes(total_kb * 1024)}",
        )

        d_total = data.get("disk_total_kb", 0)
        d_used = data.get("disk_used_kb", 0)
        self.disk.set(
            data.get("disk_percent", 0.0),
            f"{data.get('disk_percent', 0.0):.0f}%",
            f"{format_bytes(d_used * 1024)} / {format_bytes(d_total * 1024)}",
        )

        rx, tx = data.get("rx_rate", 0.0), data.get("tx_rate", 0.0)
        self.net.set_rate(f"↓ {format_bytes(rx)}/s  ↑ {format_bytes(tx)}/s", rx + tx)

    def shutdown(self) -> None:
        self._teardown_engine()
        self._controller = None

    def closeEvent(self, event) -> None:  # noqa: N802
        self.shutdown()
        super().closeEvent(event)
