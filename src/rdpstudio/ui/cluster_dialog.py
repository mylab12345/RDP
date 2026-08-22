"""Multi-host parallel command runner dialog (cluster management)."""

from __future__ import annotations

import csv
import json
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.models import Session
from ..core.plugin import SessionContext
from ..tools.cluster_runner import ClusterHostResult, ClusterRunner
from ..tools.snippets import DEFAULT_SNIPPETS
from .widgets import toast


class _ClusterThread(QThread):
    hostResultReady = Signal(object)
    progressReady = Signal(int, int)
    finishedExecution = Signal(list)

    def __init__(
        self,
        ctx: SessionContext,
        sessions: list[Session],
        command: str,
        timeout: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.runner = ClusterRunner(ctx)
        self.sessions = sessions
        self.command = command
        self.timeout = timeout

    def run(self) -> None:
        def on_done(res):
            self.hostResultReady.emit(res)

        def on_prog(done, total):
            self.progressReady.emit(done, total)

        results = self.runner.execute(
            self.sessions,
            self.command,
            timeout=self.timeout,
            on_host_done=on_done,
            on_progress=on_prog,
        )
        self.finishedExecution.emit(results)

    def cancel(self) -> None:
        self.runner.cancel()


class ClusterDialog(QDialog):
    """Run commands in parallel across multiple saved SSH sessions."""

    def __init__(self, ctx: SessionContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Multi-Host Parallel Command Runner")
        self.resize(1020, 680)
        self.setMinimumSize(800, 500)

        self._thread: _ClusterThread | None = None
        self._results: list[ClusterHostResult] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        head = QHBoxLayout()
        title = QLabel("Cluster Command Execution")
        title.setObjectName("h1")
        head.addWidget(title)
        head.addStretch(1)
        layout.addLayout(head)

        # Command input card
        cmd_card = QWidget()
        cmd_card.setObjectName("card")
        ccl = QVBoxLayout(cmd_card)
        ccl.setContentsMargins(12, 10, 12, 10)
        ccl.setSpacing(8)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Command / Script:"))
        self.snippet_presets = QComboBox()
        self.snippet_presets.addItem("— Insert Snippet / Macro —")
        for s in DEFAULT_SNIPPETS:
            self.snippet_presets.addItem(f"{s['category']}: {s['name']}", s["command"])
        self.snippet_presets.currentIndexChanged.connect(self._on_snippet_selected)
        r1.addStretch(1)
        r1.addWidget(QLabel("Presets:"))
        r1.addWidget(self.snippet_presets)
        ccl.addLayout(r1)

        self.cmd_input = QPlainTextEdit()
        self.cmd_input.setPlaceholderText("e.g. df -h && uptime\nEnter shell commands to run on all selected hosts…")
        self.cmd_input.setFixedHeight(70)
        mono_font = QFont("JetBrains Mono")
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        mono_font.setPointSize(10)
        self.cmd_input.setFont(mono_font)
        ccl.addWidget(self.cmd_input)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Timeout (s):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(2, 300)
        self.timeout_spin.setValue(15)
        r2.addWidget(self.timeout_spin)

        r2.addStretch(1)

        self.btn_run = QPushButton("▶ Run on Selected Hosts")
        self.btn_run.setObjectName("primary")
        self.btn_run.clicked.connect(self._toggle_execution)
        r2.addWidget(self.btn_run)

        ccl.addLayout(r2)
        layout.addWidget(cmd_card)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Main splitter (left: host selection tree, right: consolidated results + output)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left host checklist
        host_pane = QWidget()
        hl = QVBoxLayout(host_pane)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        hl_head = QHBoxLayout()
        hl_head.addWidget(QLabel("<b>Target SSH Hosts:</b>"))
        btn_all = QPushButton("All")
        btn_all.setObjectName("ghost")
        btn_all.clicked.connect(self._select_all_hosts)
        btn_none = QPushButton("None")
        btn_none.setObjectName("ghost")
        btn_none.clicked.connect(self._deselect_all_hosts)
        hl_head.addStretch(1)
        hl_head.addWidget(btn_all)
        hl_head.addWidget(btn_none)
        hl.addLayout(hl_head)

        self.host_tree = QTreeWidget()
        self.host_tree.setHeaderHidden(True)
        self.host_tree.setRootIsDecorated(True)
        hl.addWidget(self.host_tree, 1)

        splitter.addWidget(host_pane)

        # Right output pane (top: table, bottom: output inspector)
        right_pane = QWidget()
        rl = QVBoxLayout(right_pane)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)

        self.results_table = QTableWidget(0, 5)
        self.results_table.setHorizontalHeaderLabels(["Host", "Status", "Exit Code", "Duration", "Output Preview"])
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.results_table.itemSelectionChanged.connect(self._on_row_selected)
        rl.addWidget(self.results_table, 1)

        # Bottom detail output
        detail_header = QHBoxLayout()
        self.lbl_detail_host = QLabel("<b>Output Inspector:</b>")
        detail_header.addWidget(self.lbl_detail_host)
        detail_header.addStretch(1)
        btn_copy = QPushButton("Copy Output")
        btn_copy.setObjectName("subtle")
        btn_copy.clicked.connect(self._copy_detail_output)
        detail_header.addWidget(btn_copy)
        rl.addLayout(detail_header)

        self.output_detail = QPlainTextEdit()
        self.output_detail.setReadOnly(True)
        self.output_detail.setFont(mono_font)
        self.output_detail.setFixedHeight(160)
        rl.addWidget(self.output_detail)

        splitter.addWidget(right_pane)
        splitter.setSizes([260, 740])
        layout.addWidget(splitter, 1)

        # Footer
        footer = QHBoxLayout()
        self.lbl_stats = QLabel("Select hosts and enter a command to execute")
        self.lbl_stats.setObjectName("caption")
        footer.addWidget(self.lbl_stats)
        footer.addStretch(1)

        btn_export = QPushButton("Export Results…")
        btn_export.setObjectName("ghost")
        btn_export.clicked.connect(self._export_results)
        footer.addWidget(btn_export)

        btn_close = QPushButton("Close")
        btn_close.setObjectName("subtle")
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

        self._populate_hosts()

    def _populate_hosts(self) -> None:
        self.host_tree.clear()
        sessions = self.ctx.store.sessions()
        ssh_sessions = [s for s in sessions if s.protocol == "ssh"]

        groups: dict[str, list[Session]] = {}
        for s in ssh_sessions:
            groups.setdefault(s.group or "", []).append(s)

        for s in sorted(groups.get("", []), key=lambda x: x.display_name().lower()):
            self._add_host_item(self.host_tree.invisibleRootItem(), s)

        for gname in sorted(g for g in groups if g):
            folder = QTreeWidgetItem([f"📁 {gname}"])
            folder.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            folder.setCheckState(0, Qt.CheckState.Checked)
            folder.setExpanded(True)
            for s in sorted(groups[gname], key=lambda x: x.display_name().lower()):
                self._add_host_item(folder, s)
            self.host_tree.addTopLevelItem(folder)

    def _add_host_item(self, parent, s: Session) -> None:
        item = QTreeWidgetItem([f"{s.display_name()} ({s.host})"])
        item.setData(0, Qt.ItemDataRole.UserRole, s)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
        item.setCheckState(0, Qt.CheckState.Checked)
        parent.addChild(item)

    def _select_all_hosts(self) -> None:
        def check_item(it):
            it.setCheckState(0, Qt.CheckState.Checked)
            for i in range(it.childCount()):
                check_item(it.child(i))

        for i in range(self.host_tree.topLevelItemCount()):
            check_item(self.host_tree.topLevelItem(i))

    def _deselect_all_hosts(self) -> None:
        def uncheck_item(it):
            it.setCheckState(0, Qt.CheckState.Unchecked)
            for i in range(it.childCount()):
                uncheck_item(it.child(i))

        for i in range(self.host_tree.topLevelItemCount()):
            uncheck_item(self.host_tree.topLevelItem(i))

    def _selected_sessions(self) -> list[Session]:
        selected = []

        def collect(it):
            s = it.data(0, Qt.ItemDataRole.UserRole)
            if s and it.checkState(0) == Qt.CheckState.Checked:
                selected.append(s)
            for i in range(it.childCount()):
                collect(it.child(i))

        for i in range(self.host_tree.topLevelItemCount()):
            collect(self.host_tree.topLevelItem(i))
        return selected

    def _on_snippet_selected(self) -> None:
        cmd = self.snippet_presets.currentData()
        if cmd:
            self.cmd_input.setPlainText(str(cmd))

    def _toggle_execution(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.cancel()
            self.btn_run.setText("▶ Run on Selected Hosts")
            self.progress_bar.setVisible(False)
            return

        cmd = self.cmd_input.toPlainText().strip()
        if not cmd:
            toast(self, "Enter a command or script to execute", "warn")
            return

        sessions = self._selected_sessions()
        if not sessions:
            toast(self, "Select at least one SSH host from the list", "warn")
            return

        self._results.clear()
        self.results_table.setRowCount(0)
        self.output_detail.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.btn_run.setText("■ Stop Execution")
        self.lbl_stats.setText(f"Running across {len(sessions)} host(s)…")

        self._thread = _ClusterThread(
            self.ctx,
            sessions,
            command=cmd,
            timeout=self.timeout_spin.value(),
        )
        self._thread.hostResultReady.connect(self._on_host_result)
        self._thread.progressReady.connect(self._on_progress)
        self._thread.finishedExecution.connect(self._on_finished)
        self._thread.start()

    def _on_host_result(self, res: ClusterHostResult) -> None:
        self._results.append(res)
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)

        state_color = {
            "success": Qt.GlobalColor.green,
            "failed": Qt.GlobalColor.red,
            "timeout": Qt.GlobalColor.yellow,
            "auth_error": Qt.GlobalColor.red,
            "conn_error": Qt.GlobalColor.red,
        }.get(res.status, Qt.GlobalColor.gray)

        preview = (res.stdout.strip() or res.stderr.strip() or res.error).replace("\n", " ")[:80]

        item_host = QTableWidgetItem(f"{res.display_name} ({res.host})")
        item_status = QTableWidgetItem(f"● {res.status.upper()}")
        item_status.setForeground(state_color)
        item_code = QTableWidgetItem(str(res.exit_code) if res.exit_code != -1 else "—")
        item_dur = QTableWidgetItem(f"{res.duration_s:.2f}s")
        item_prev = QTableWidgetItem(preview)

        for col, item in enumerate((item_host, item_status, item_code, item_dur, item_prev)):
            item.setData(Qt.ItemDataRole.UserRole, res)
            self.results_table.setItem(row, col, item)

        # Select first row by default to show preview
        if row == 0:
            self.results_table.selectRow(0)

    def _on_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setValue(int(done * 100 / total))

    def _on_finished(self, results: list[ClusterHostResult]) -> None:
        self.progress_bar.setVisible(False)
        self.btn_run.setText("▶ Run on Selected Hosts")
        succeeded = sum(1 for r in results if r.status == "success")
        failed = len(results) - succeeded
        self.lbl_stats.setText(f"Completed: {len(results)} hosts ({succeeded} succeeded, {failed} failed)")
        toast(self, f"Cluster run finished ({succeeded}/{len(results)} ok)", "good" if not failed else "warn")

    def _on_row_selected(self) -> None:
        row = self.results_table.currentRow()
        if row < 0:
            return
        item = self.results_table.item(row, 0)
        res: ClusterHostResult | None = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not res:
            return
        self.lbl_detail_host.setText(f"<b>Output Inspector — {res.display_name} ({res.host})</b>")
        content = ""
        if res.stdout:
            content += f"=== STDOUT ===\n{res.stdout}\n"
        if res.stderr:
            content += f"=== STDERR ===\n{res.stderr}\n"
        if res.error:
            content += f"=== ERROR ===\n{res.error}\n"
        self.output_detail.setPlainText(content or "(no output)")

    def _copy_detail_output(self) -> None:
        text = self.output_detail.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            toast(self, "Copied output to clipboard", "good")

    def _export_results(self) -> None:
        if not self._results:
            toast(self, "No execution results to export", "warn")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Results", "cluster-results.json", "JSON (*.json);;CSV (*.csv);;Markdown (*.md)")
        if not path:
            return
        try:
            if path.endswith(".csv"):
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["Host", "DisplayName", "Status", "ExitCode", "Duration_s", "Stdout", "Stderr", "Error"])
                    for r in self._results:
                        writer.writerow([r.host, r.display_name, r.status, r.exit_code, r.duration_s, r.stdout, r.stderr, r.error])
            elif path.endswith(".md"):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(f"# Cluster Execution Results — {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    fh.write("| Host | Status | Exit Code | Duration | Output |\n|---|---|---|---|---|\n")
                    for r in self._results:
                        prev = (r.stdout.strip() or r.error).replace("\n", " ")[:60]
                        fh.write(f"| {r.display_name} | {r.status} | {r.exit_code} | {r.duration_s:.2f}s | {prev} |\n")
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump([r.to_dict() for r in self._results], fh, indent=2)
            toast(self, f"Exported {len(self._results)} host results", "good")
        except Exception as exc:
            toast(self, f"Export failed: {exc}", "bad")
