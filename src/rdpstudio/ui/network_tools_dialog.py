"""Network diagnostics & Port Scanner dialog: multi-threaded port scanner, ping & DNS."""

from __future__ import annotations

import csv
import json

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Session
from ..tools.network_scanner import (
    PRESET_COMMON,
    PRESET_DATABASES,
    PRESET_REMOTE,
    PRESET_WEB,
    PortScanner,
    ScanResult,
    dns_lookup,
    parse_ports,
    parse_target_hosts,
    tcp_ping,
)
from .monitor_dialog import Sparkline
from .theme import icon
from .widgets import toast


class _ScannerThread(QThread):
    resultReady = Signal(object)
    progressReady = Signal(int, int)
    finishedScan = Signal(list)

    def __init__(self, targets: list[str], ports: list[int], timeout: float, parent=None) -> None:
        super().__init__(parent)
        self.targets = targets
        self.ports = ports
        self.timeout = timeout
        self.scanner = PortScanner(max_workers=60)

    def run(self) -> None:
        def on_res(res):
            self.resultReady.emit(res)

        def on_prog(done, total):
            self.progressReady.emit(done, total)

        results = self.scanner.scan(
            self.targets,
            self.ports,
            timeout=self.timeout,
            grab_banner=True,
            on_result=on_res,
            on_progress=on_prog,
        )
        self.finishedScan.emit(results)

    def cancel(self) -> None:
        self.scanner.cancel()


class NetworkToolsDialog(QDialog):
    """Standalone diagnostic workstation: Port Scanner, Ping & DNS."""

    def __init__(self, main_window=None, parent=None) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self.setWindowTitle("Network Tools & Port Scanner")
        self.resize(920, 620)
        self.setMinimumSize(700, 480)

        self._scan_thread: _ScannerThread | None = None
        self._scan_results: list[ScanResult] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        head = QHBoxLayout()
        title = QLabel("Network Diagnostics & Scanner")
        title.setObjectName("h1")
        head.addWidget(title)
        head.addStretch(1)
        layout.addLayout(head)

        tabs = QTabWidget()
        tabs.addTab(self._build_scanner_tab(), "Port Scanner")
        tabs.addTab(self._build_ping_tab(), "Ping & Latency")
        tabs.addTab(self._build_dns_tab(), "DNS & IP Lookup")
        layout.addWidget(tabs, 1)

    # ------------------------------------------------------------------
    # TAB 1: Port Scanner
    # ------------------------------------------------------------------
    def _build_scanner_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Controls row
        ctrl = QWidget()
        ctrl.setObjectName("card")
        cl = QVBoxLayout(ctrl)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Target:"))
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("Hostname, IP, range (192.168.1.1-10), or CIDR (10.0.0.0/28)")
        self.target_input.setText("127.0.0.1")
        r1.addWidget(self.target_input, 2)

        r1.addWidget(QLabel("Ports:"))
        self.port_preset = QComboBox()
        self.port_preset.addItem("Common Ports (~25 ports)", "common")
        self.port_preset.addItem("Remote Services (SSH, RDP, VNC, Web)", "remote")
        self.port_preset.addItem("Web Only (80, 443, 8080, 8443)", "web")
        self.port_preset.addItem("Databases (MySQL, Postgres, Redis, Mongo)", "db")
        self.port_preset.addItem("Custom Ports…", "custom")
        self.port_preset.currentIndexChanged.connect(self._on_port_preset)
        r1.addWidget(self.port_preset, 1)

        self.custom_ports = QLineEdit()
        self.custom_ports.setPlaceholderText("e.g. 22,80,443,8000-8080")
        self.custom_ports.setVisible(False)
        r1.addWidget(self.custom_ports, 1)
        cl.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Timeout (s):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setValue(1)
        r2.addWidget(self.timeout_spin)

        self.chk_open_only = QComboBox()
        self.chk_open_only.addItem("Show Open Ports Only")
        self.chk_open_only.addItem("Show All Probed Ports")
        self.chk_open_only.currentIndexChanged.connect(self._refresh_table)
        r2.addWidget(self.chk_open_only)

        r2.addStretch(1)

        self.btn_scan = QPushButton("▶ Start Scan")
        self.btn_scan.setObjectName("primary")
        self.btn_scan.clicked.connect(self._toggle_scan)
        r2.addWidget(self.btn_scan)

        cl.addLayout(r2)
        layout.addWidget(ctrl)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Results table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Target", "Port", "Service", "State", "Latency", "Banner / Info"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        # Action bar
        act = QHBoxLayout()
        self.lbl_scan_stats = QLabel("Ready to scan")
        self.lbl_scan_stats.setObjectName("caption")
        act.addWidget(self.lbl_scan_stats)
        act.addStretch(1)

        btn_connect_ssh = QPushButton("Connect SSH")
        btn_connect_ssh.setObjectName("subtle")
        btn_connect_ssh.clicked.connect(lambda: self._connect_selected("ssh"))
        act.addWidget(btn_connect_ssh)

        btn_connect_rdp = QPushButton("Connect RDP")
        btn_connect_rdp.setObjectName("subtle")
        btn_connect_rdp.clicked.connect(lambda: self._connect_selected("rdp"))
        act.addWidget(btn_connect_rdp)

        btn_export = QPushButton("Export Results…")
        btn_export.setObjectName("ghost")
        btn_export.clicked.connect(self._export_scan_results)
        act.addWidget(btn_export)

        layout.addLayout(act)
        return page

    def _on_port_preset(self) -> None:
        custom = self.port_preset.currentData() == "custom"
        self.custom_ports.setVisible(custom)

    def _get_ports(self) -> list[int]:
        preset = self.port_preset.currentData()
        if preset == "common":
            return PRESET_COMMON
        elif preset == "remote":
            return PRESET_REMOTE
        elif preset == "web":
            return PRESET_WEB
        elif preset == "db":
            return PRESET_DATABASES
        else:
            return parse_ports(self.custom_ports.text())

    def _toggle_scan(self) -> None:
        if self._scan_thread and self._scan_thread.isRunning():
            self._scan_thread.cancel()
            self.btn_scan.setText("▶ Start Scan")
            self.progress_bar.setVisible(False)
            return

        targets = parse_target_hosts(self.target_input.text())
        if not targets:
            toast(self, "Please enter a valid target host or IP range", "warn")
            return
        ports = self._get_ports()
        if not ports:
            toast(self, "No valid ports selected", "warn")
            return

        self._scan_results.clear()
        self.table.setRowCount(0)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_scan.setText("■ Stop Scan")
        self.lbl_scan_stats.setText(f"Scanning {len(targets)} host(s) across {len(ports)} port(s)…")

        self._scan_thread = _ScannerThread(targets, ports, timeout=float(self.timeout_spin.value()))
        self._scan_thread.resultReady.connect(self._on_scan_result)
        self._scan_thread.progressReady.connect(self._on_scan_progress)
        self._scan_thread.finishedScan.connect(self._on_scan_finished)
        self._scan_thread.start()

    def _on_scan_result(self, res: ScanResult) -> None:
        self._scan_results.append(res)
        if self.chk_open_only.currentIndex() == 0 and not res.open:
            return
        self._append_table_row(res)

    def _on_scan_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setValue(int(done * 100 / total))

    def _on_scan_finished(self, results: list[ScanResult]) -> None:
        self.progress_bar.setVisible(False)
        self.btn_scan.setText("▶ Start Scan")
        open_count = sum(1 for r in results if r.open)
        self.lbl_scan_stats.setText(f"Scan complete: {len(results)} probes, {open_count} open port(s) found.")
        toast(self, f"Scan finished: {open_count} open port(s)", "good" if open_count else "info")

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        open_only = self.chk_open_only.currentIndex() == 0
        for r in self._scan_results:
            if open_only and not r.open:
                continue
            self._append_table_row(r)

    def _append_table_row(self, res: ScanResult) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        state_str = "● Open" if res.open else "○ Closed"
        color = Qt.GlobalColor.green if res.open else Qt.GlobalColor.gray
        lat_str = f"{res.latency_ms:.1f} ms" if res.open else "—"

        item_host = QTableWidgetItem(res.host)
        item_port = QTableWidgetItem(str(res.port))
        item_svc = QTableWidgetItem(res.service)
        item_state = QTableWidgetItem(state_str)
        item_state.setForeground(color)
        item_lat = QTableWidgetItem(lat_str)
        item_banner = QTableWidgetItem(res.banner or res.error)

        for col, item in enumerate((item_host, item_port, item_svc, item_state, item_lat, item_banner)):
            item.setData(Qt.ItemDataRole.UserRole, res)
            self.table.setItem(row, col, item)

    def _selected_result(self) -> ScanResult | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _connect_selected(self, protocol: str) -> None:
        res = self._selected_result()
        if not res:
            toast(self, "Select a host from the table first", "warn")
            return
        if not self.main:
            return
        port = res.port if res.open else (22 if protocol == "ssh" else 3389)
        s = Session(
            name=f"{res.host}:{port}",
            protocol=protocol,
            host=res.host,
            port=port,
        )
        self.main.ctx.store.upsert(s)
        self.main.sidebar.reload()
        self.main.open_session(s)
        toast(self, f"Connecting {protocol.upper()} to {res.host}:{port}…", "good")

    def _table_context_menu(self, pos) -> None:
        res = self._selected_result()
        if not res:
            return
        menu = QMenu(self)
        menu.addAction(icon("connect"), f"Connect SSH ({res.host}:{res.port})", lambda: self._connect_selected("ssh"))
        menu.addAction(icon("windows"), f"Connect RDP ({res.host}:{res.port})", lambda: self._connect_selected("rdp"))
        menu.addSeparator()
        menu.addAction("Copy IP:Port", lambda: QGuiApplication.clipboard().setText(f"{res.host}:{res.port}"))
        menu.addAction("Copy Banner", lambda: QGuiApplication.clipboard().setText(res.banner or ""))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _export_scan_results(self) -> None:
        if not self._scan_results:
            toast(self, "No scan results to export", "warn")
            return
        path, filt = QFileDialog.getSaveFileName(self, "Export Results", "scan-results.json", "JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        try:
            if path.endswith(".csv"):
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["Host", "Port", "Service", "Open", "Latency_ms", "Banner", "Error"])
                    for r in self._scan_results:
                        writer.writerow([r.host, r.port, r.service, r.open, r.latency_ms, r.banner, r.error])
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump([r.to_dict() for r in self._scan_results], fh, indent=2)
            toast(self, f"Exported {len(self._scan_results)} results", "good")
        except Exception as exc:
            toast(self, f"Export failed: {exc}", "bad")

    # ------------------------------------------------------------------
    # TAB 2: Ping & Latency
    # ------------------------------------------------------------------
    def _build_ping_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        ctrl = QWidget()
        ctrl.setObjectName("card")
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)

        cl.addWidget(QLabel("Host:"))
        self.ping_host = QLineEdit("8.8.8.8")
        cl.addWidget(self.ping_host, 2)

        cl.addWidget(QLabel("Port:"))
        self.ping_port = QSpinBox()
        self.ping_port.setRange(1, 65535)
        self.ping_port.setValue(443)
        cl.addWidget(self.ping_port)

        cl.addWidget(QLabel("Count:"))
        self.ping_count = QSpinBox()
        self.ping_count.setRange(1, 50)
        self.ping_count.setValue(6)
        cl.addWidget(self.ping_count)

        btn_ping = QPushButton("▶ Ping")
        btn_ping.setObjectName("primary")
        btn_ping.clicked.connect(self._run_ping)
        cl.addWidget(btn_ping)
        layout.addWidget(ctrl)

        # Summary cards
        stats_card = QWidget()
        stats_card.setObjectName("card")
        sl = QHBoxLayout(stats_card)
        sl.setContentsMargins(16, 12, 16, 12)

        def make_stat_box(title: str):
            w = QWidget()
            vl = QVBoxLayout(w)
            vl.setContentsMargins(0, 0, 0, 0)
            t = QLabel(title)
            t.setObjectName("muted")
            val = QLabel("—")
            val.setObjectName("h2")
            vl.addWidget(t)
            vl.addWidget(val)
            sl.addWidget(w)
            return val

        self.lbl_ping_loss = make_stat_box("Packet Loss")
        self.lbl_ping_min = make_stat_box("Min Latency")
        self.lbl_ping_avg = make_stat_box("Avg Latency")
        self.lbl_ping_max = make_stat_box("Max Latency")
        self.lbl_ping_jitter = make_stat_box("Jitter")
        layout.addWidget(stats_card)

        # Sparkline
        self.ping_spark = Sparkline("accent")
        layout.addWidget(QLabel("<b>Latency History:</b>"))
        layout.addWidget(self.ping_spark)

        # Details list
        self.ping_log = QTableWidget(0, 3)
        self.ping_log.setHorizontalHeaderLabels(["Seq #", "Latency", "Status"])
        self.ping_log.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.ping_log, 1)

        return page

    def _run_ping(self) -> None:
        host = self.ping_host.text().strip()
        port = self.ping_port.value()
        count = self.ping_count.value()
        if not host:
            return

        self.ping_log.setRowCount(0)
        self.ping_spark.clear()

        # Run ping in background
        summary = tcp_ping(host, port=port, count=count)

        self.lbl_ping_loss.setText(f"{summary.packet_loss_pct:.0f}%")
        self.lbl_ping_min.setText(f"{summary.min_ms:.1f} ms" if summary.received else "—")
        self.lbl_ping_avg.setText(f"{summary.avg_ms:.1f} ms" if summary.received else "—")
        self.lbl_ping_max.setText(f"{summary.max_ms:.1f} ms" if summary.received else "—")
        self.lbl_ping_jitter.setText(f"{summary.jitter_ms:.1f} ms" if summary.received else "—")

        for idx, lat in enumerate(summary.latencies):
            row = self.ping_log.rowCount()
            self.ping_log.insertRow(row)
            self.ping_log.setItem(row, 0, QTableWidgetItem(f"#{idx + 1}"))
            self.ping_log.setItem(row, 1, QTableWidgetItem(f"{lat:.1f} ms"))
            item_st = QTableWidgetItem("✓ Received")
            item_st.setForeground(Qt.GlobalColor.green)
            self.ping_log.setItem(row, 2, item_st)
            self.ping_spark.push(lat)

    # ------------------------------------------------------------------
    # TAB 3: DNS & IP Lookup
    # ------------------------------------------------------------------
    def _build_dns_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        ctrl = QWidget()
        ctrl.setObjectName("card")
        cl = QHBoxLayout(ctrl)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(8)

        cl.addWidget(QLabel("Hostname / IP:"))
        self.dns_input = QLineEdit("google.com")
        self.dns_input.returnPressed.connect(self._run_dns)
        cl.addWidget(self.dns_input, 2)

        btn_dns = QPushButton("⌕ Lookup")
        btn_dns.setObjectName("primary")
        btn_dns.clicked.connect(self._run_dns)
        cl.addWidget(btn_dns)
        layout.addWidget(ctrl)

        self.dns_table = QTableWidget(0, 2)
        self.dns_table.setHorizontalHeaderLabels(["Record Type", "Resolved Value / IP / Host"])
        self.dns_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dns_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.dns_table, 1)

        return page

    def _run_dns(self) -> None:
        target = self.dns_input.text().strip()
        if not target:
            return
        self.dns_table.setRowCount(0)
        res = dns_lookup(target)

        for rec_type, values in res.items():
            for v in values:
                row = self.dns_table.rowCount()
                self.dns_table.insertRow(row)
                self.dns_table.setItem(row, 0, QTableWidgetItem(rec_type))
                self.dns_table.setItem(row, 1, QTableWidgetItem(v))
        toast(self, f"Resolved records for {target}", "good")
