"""Real-time connection status monitor & user activity log viewer."""

from __future__ import annotations

import json
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.activity import ACTIVITY_KINDS, ActivityEntry, ActivityLog, default_activity_log
from .theme import icon, palette
from .widgets import PillBadge, StatusIndicator, toast

_KIND_LABELS: dict[str, str] = {
    "": "All categories",
    "connection": "Connections",
    "session": "Sessions",
    "transfer": "File Transfers",
    "ui": "UI & Appearance",
    "support": "Support & Chat",
    "feedback": "User Feedback",
    "security": "Security",
}


class ActivityLogDialog(QDialog):
    """Real-time connection status indicators and user activity log."""

    def __init__(self, main_window=None, activity_log: ActivityLog | None = None, parent=None) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self.activity_log = activity_log or getattr(main_window, "activity_log", None) or default_activity_log()
        self.setWindowTitle("Connection Status & Activity Log")
        self.setObjectName("activityLogDialog")
        self.resize(860, 620)
        self.setMinimumSize(560, 420)

        pal = palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        # ── Header: title + live status indicator ──
        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        title = QLabel("Connection Status & Activity Log")
        title.setObjectName("h1")
        hdr.addWidget(title)
        hdr.addStretch(1)

        self.live_indicator = StatusIndicator("disconnected")
        self.live_indicator.setObjectName("activityLiveIndicator")
        hdr.addWidget(self.live_indicator)
        root.addLayout(hdr)

        sub = QLabel(
            "Real-time session health, connection transitions, file transfers, and user actions."
        )
        sub.setObjectName("caption")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Real-time Connection Summary Card ──
        summary_card = QFrame()
        summary_card.setObjectName("card")
        sc_lay = QVBoxLayout(summary_card)
        sc_lay.setContentsMargins(14, 10, 14, 10)
        sc_lay.setSpacing(8)

        badges_row = QHBoxLayout()
        badges_row.setSpacing(10)
        conn_hdr = QLabel("Active Connections")
        conn_hdr.setObjectName("h2")
        badges_row.addWidget(conn_hdr)
        badges_row.addStretch(1)

        self.badge_active = PillBadge("0 open", "default")
        self.badge_connected = PillBadge("0 connected", "good")
        self.badge_alerts = PillBadge("0 alerts", "warn")
        self.badge_events = PillBadge("0 events", "accent")
        badges_row.addWidget(self.badge_active)
        badges_row.addWidget(self.badge_connected)
        badges_row.addWidget(self.badge_alerts)
        badges_row.addWidget(self.badge_events)
        sc_lay.addLayout(badges_row)

        self.sessions_table = QTableWidget(0, 4)
        self.sessions_table.setObjectName("activeSessionsTable")
        self.sessions_table.setHorizontalHeaderLabels(["Session", "Protocol", "Target", "Live State"])
        self.sessions_table.verticalHeader().setVisible(False)
        self.sessions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sessions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sessions_table.setMaximumHeight(120)
        sh = self.sessions_table.horizontalHeader()
        sh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        sh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        sh.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        sh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        sc_lay.addWidget(self.sessions_table)
        root.addWidget(summary_card)

        # ── Filter & Search Bar ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("activitySearch")
        self.search_input.setPlaceholderText("Filter activity by session, host, or event…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.textChanged.connect(lambda _t: self.refresh())
        filter_row.addWidget(self.search_input, 1)

        self.kind_combo = QComboBox()
        self.kind_combo.setObjectName("activityKindFilter")
        self.kind_combo.addItem(_KIND_LABELS[""], "")
        for k in ACTIVITY_KINDS:
            self.kind_combo.addItem(_KIND_LABELS.get(k, k.capitalize()), k)
        self.kind_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        filter_row.addWidget(self.kind_combo)

        self.level_combo = QComboBox()
        self.level_combo.setObjectName("activityLevelFilter")
        self.level_combo.addItem("All severities", "")
        self.level_combo.addItem("Info", "info")
        self.level_combo.addItem("Success", "good")
        self.level_combo.addItem("Warning", "warn")
        self.level_combo.addItem("Error", "bad")
        self.level_combo.currentIndexChanged.connect(lambda _i: self.refresh())
        filter_row.addWidget(self.level_combo)
        root.addLayout(filter_row)

        # ── Activity Log Table ──
        self.table = QTableWidget(0, 5)
        self.table.setObjectName("activityLogTable")
        self.table.setHorizontalHeaderLabels(["Time", "Category", "Event", "Session", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.EditBehavior.SelectRows if hasattr(QAbstractItemView, "EditBehavior") else QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        th = self.table.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        # ── Footer actions ──
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.btn_copy = QPushButton("Copy Log")
        self.btn_copy.setObjectName("subtle")
        self.btn_copy.setToolTip("Copy visible activity log entries to clipboard")
        self.btn_copy.clicked.connect(self.copy_log)
        footer.addWidget(self.btn_copy)

        self.btn_export = QPushButton("Export JSON…")
        self.btn_export.setObjectName("subtle")
        self.btn_export.setToolTip("Export activity log entries to a JSON file")
        self.btn_export.clicked.connect(self.export_json)
        footer.addWidget(self.btn_export)

        self.btn_clear = QPushButton("Clear Log")
        self.btn_clear.setObjectName("danger")
        self.btn_clear.setToolTip("Clear all recorded activity log entries")
        self.btn_clear.clicked.connect(self.clear_log)
        footer.addWidget(self.btn_clear)

        footer.addStretch(1)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("primary")
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)
        root.addLayout(footer)

        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self._pal = pal
        self.refresh()

    def _collect_live_sessions(self) -> list[dict[str, str]]:
        if self.main is None or not hasattr(self.main, "tabs"):
            return []
        rows: list[dict[str, str]] = []
        for i in range(self.main.tabs.count()):
            w = self.main.tabs.widget(i)
            ctrl = getattr(w, "controller", None)
            if ctrl is None:
                continue
            defn = getattr(ctrl, "definition", None)
            name = self.main.tabs.tabText(i) or (defn.display_name() if defn else "Session")
            proto = (getattr(defn, "protocol", "") or "ssh").upper()
            target = defn.target() if defn and hasattr(defn, "target") else "local"
            state = (ctrl.state() if hasattr(ctrl, "state") else "unknown") or "unknown"
            rows.append(
                {
                    "name": name,
                    "protocol": proto,
                    "target": target,
                    "state": state,
                }
            )
        return rows

    def refresh(self) -> None:
        """Refresh both live connection status indicators and the activity table."""
        pal = palette()
        live_rows = self._collect_live_sessions()
        self.sessions_table.setRowCount(0)
        connected_count = 0
        connecting_count = 0
        failed_count = 0
        for row_data in live_rows:
            r = self.sessions_table.rowCount()
            self.sessions_table.insertRow(r)
            st = row_data["state"].lower()
            if st == "connected":
                connected_count += 1
            elif st in ("connecting", "reconnecting"):
                connecting_count += 1
            elif st == "failed":
                failed_count += 1
            for col, key in enumerate(("name", "protocol", "target", "state")):
                val = row_data[key].upper() if key == "state" else row_data[key]
                item = QTableWidgetItem(val)
                if key == "state":
                    color_key = {
                        "connected": "good",
                        "connecting": "info",
                        "reconnecting": "warn",
                        "failed": "bad",
                    }.get(st, "fg_dim")
                    item.setForeground(QColor(pal.get(color_key, pal["fg_dim"])))
                self.sessions_table.setItem(r, col, item)

        if connected_count > 0:
            self.live_indicator.set_status("connected")
        elif connecting_count > 0:
            self.live_indicator.set_status("connecting")
        elif failed_count > 0:
            self.live_indicator.set_status("failed")
        else:
            self.live_indicator.set_status("disconnected")

        counts = self.activity_log.summary_counts()
        self.badge_active.setText(f"{len(live_rows)} open")
        self.badge_connected.setText(f"{connected_count} connected")
        alerts = counts.get("errors", 0) + counts.get("warnings", 0) + failed_count
        self.badge_alerts.setText(f"{alerts} alert{'s' if alerts != 1 else ''}")
        self.badge_events.setText(f"{counts.get('total', 0)} events")

        entries = self.visible_entries()
        self.table.setRowCount(0)
        for entry in entries:
            r = self.table.rowCount()
            self.table.insertRow(r)
            stamp = time.strftime("%H:%M:%S", time.localtime(entry.ts or time.time()))
            cat = _KIND_LABELS.get(entry.kind, entry.kind.capitalize())
            cells = (
                stamp,
                cat,
                entry.title,
                entry.session or (entry.protocol.upper() if entry.protocol else "—"),
                entry.detail or "—",
            )
            level_color = {
                "good": pal["good"],
                "warn": pal["warn"],
                "bad": pal["bad"],
                "info": pal["fg"],
            }.get(entry.level, pal["fg"])
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 2:
                    item.setForeground(QColor(level_color))
                self.table.setItem(r, col, item)

    def visible_entries(self) -> list[ActivityEntry]:
        return self.activity_log.entries(
            limit=200,
            kind=self.kind_combo.currentData() or "",
            level=self.level_combo.currentData() or "",
            search=self.search_input.text(),
        )

    def copy_log(self) -> None:
        entries = self.visible_entries()
        lines = [
            f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(e.ts))}  "
            f"[{e.kind.upper()}/{e.level.upper()}]  {e.title}"
            + (f" ({e.session})" if e.session else "")
            + (f" — {e.detail}" if e.detail else "")
            for e in entries
        ]
        QGuiApplication.clipboard().setText("\n".join(lines) or "No activity entries.")
        toast(self, f"Copied {len(entries)} activity entry(s)", "info")

    def export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Activity Log", "kb-remote-activity.json", "JSON (*.json)"
        )
        if not path:
            return
        payload = [e.to_dict() for e in self.visible_entries()]
        try:
            Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
            toast(self, f"Exported {len(payload)} activity entries", "good")
        except OSError as exc:
            toast(self, f"Export failed: {exc}", "bad")

    def clear_log(self) -> None:
        self.activity_log.clear()
        self.refresh()
        if self.main is not None and hasattr(self.main, "_update_activity_badge"):
            self.main._update_activity_badge()
        toast(self, "Activity log cleared", "info")
