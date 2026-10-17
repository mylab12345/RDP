"""User feedback dialog for submitting improvement suggestions and bug reports."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.activity import log_activity
from ..core.feedback import (
    FEEDBACK_CATEGORIES,
    FeedbackEntry,
    FeedbackStore,
    build_safe_diagnostics,
    default_feedback_store,
)
from .widgets import PillBadge, toast


class FeedbackDialog(QDialog):
    """Dialog allowing users to suggest improvements or report issues from the UI."""

    def __init__(
        self,
        main_window=None,
        *,
        store: FeedbackStore | None = None,
        prefill_title: str = "",
        prefill_description: str = "",
        category: str = "improvement",
        parent=None,
    ) -> None:
        super().__init__(parent or main_window)
        self.main = main_window
        self.store = store or default_feedback_store()
        self.last_submitted: FeedbackEntry | None = None
        self._rating = 5

        self.setWindowTitle("Send Feedback & Suggest Improvements")
        self.setObjectName("feedbackDialog")
        self.resize(660, 560)
        self.setMinimumSize(480, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 14)
        root.setSpacing(10)

        hdr = QHBoxLayout()
        title = QLabel("Suggest an Improvement or Share Feedback")
        title.setObjectName("h1")
        hdr.addWidget(title)
        hdr.addStretch(1)
        self.count_badge = PillBadge("0 saved", "accent")
        self.count_badge.setObjectName("feedbackCountBadge")
        hdr.addWidget(self.count_badge)
        root.addLayout(hdr)

        sub = QLabel(
            "Tell us what would make KB-Remote better — dashboard workflow, RDP sessions, "
            "drag-and-drop file transfers, themes, or mobile responsiveness."
        )
        sub.setObjectName("caption")
        sub.setWordWrap(True)
        root.addWidget(sub)

        # ── Form card ──
        card = QFrame()
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        cat_lbl = QLabel("Area:")
        top_row.addWidget(cat_lbl)

        self.category_combo = QComboBox()
        self.category_combo.setObjectName("feedbackCategoryCombo")
        selected_idx = 0
        for idx, (cid, label) in enumerate(FEEDBACK_CATEGORIES):
            self.category_combo.addItem(label, cid)
            if cid == category:
                selected_idx = idx
        self.category_combo.setCurrentIndex(selected_idx)
        top_row.addWidget(self.category_combo, 1)

        rating_lbl = QLabel("Experience:")
        top_row.addWidget(rating_lbl)

        self.star_buttons: list[QPushButton] = []
        for star in range(1, 6):
            b = QPushButton("★")
            b.setObjectName("subtle")
            b.setFixedSize(30, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(f"Rate {star} out of 5 stars")
            b.clicked.connect(lambda _=False, s=star: self.set_rating(s))
            self.star_buttons.append(b)
            top_row.addWidget(b)
        form.addLayout(top_row)

        self.title_input = QLineEdit()
        self.title_input.setObjectName("feedbackTitleInput")
        self.title_input.setPlaceholderText("Short summary (e.g. 'Add one-click RDP scaling preset')")
        if prefill_title:
            self.title_input.setText(prefill_title)
        form.addWidget(self.title_input)

        self.desc_input = QPlainTextEdit()
        self.desc_input.setObjectName("feedbackDescriptionInput")
        self.desc_input.setPlaceholderText(
            "Describe your suggestion, workflow improvement, or issue in detail…"
        )
        self.desc_input.setMinimumHeight(110)
        if prefill_description:
            self.desc_input.setPlainText(prefill_description)
        form.addWidget(self.desc_input, 1)

        self.chk_diagnostics = QCheckBox(
            "Include anonymous UI & environment diagnostics (theme, font size, OS — never credentials)"
        )
        self.chk_diagnostics.setObjectName("feedbackDiagnosticsCheck")
        self.chk_diagnostics.setChecked(True)
        form.addWidget(self.chk_diagnostics)
        root.addWidget(card, 1)

        # ── Recent feedback table ──
        hist_lbl = QLabel("Submitted Feedback History")
        hist_lbl.setObjectName("h2")
        root.addWidget(hist_lbl)

        self.history_table = QTableWidget(0, 4)
        self.history_table.setObjectName("feedbackHistoryTable")
        self.history_table.setHorizontalHeaderLabels(["Time", "Category", "Rating", "Summary"])
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setMaximumHeight(120)
        hh = self.history_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.history_table)

        # ── Footer buttons ──
        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.btn_copy_md = QPushButton("Copy as Markdown")
        self.btn_copy_md.setObjectName("subtle")
        self.btn_copy_md.setToolTip("Copy your feedback formatted as Markdown for GitHub issues")
        self.btn_copy_md.clicked.connect(self.copy_markdown)
        footer.addWidget(self.btn_copy_md)

        footer.addStretch(1)

        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.setObjectName("subtle")
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        self.btn_submit = QPushButton("Submit Feedback")
        self.btn_submit.setObjectName("primary")
        self.btn_submit.clicked.connect(self.submit_feedback)
        footer.addWidget(self.btn_submit)
        root.addLayout(footer)

        self.set_rating(5)
        self._refresh_history()

    @property
    def rating(self) -> int:
        return self._rating

    def set_rating(self, stars: int) -> None:
        self._rating = max(1, min(5, int(stars)))
        for idx, btn in enumerate(self.star_buttons, start=1):
            filled = idx <= self._rating
            btn.setText("★" if filled else "☆")
            btn.setObjectName("primary" if filled else "subtle")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _collect_diagnostics(self) -> dict:
        if not self.chk_diagnostics.isChecked():
            return {}
        settings = getattr(getattr(self.main, "ctx", None), "settings", None)
        active_proto = ""
        if self.main is not None and hasattr(self.main, "_current_session_tab"):
            tab = self.main._current_session_tab()
            if tab is not None:
                active_proto = getattr(tab.controller.definition, "protocol", "")
        return build_safe_diagnostics(settings, active_protocol=active_proto)

    def submit_feedback(self) -> FeedbackEntry | None:
        title = self.title_input.text().strip()
        desc = self.desc_input.toPlainText().strip()
        if not title and not desc:
            toast(self, "Please enter a summary or description for your feedback.", "warn")
            self.title_input.setFocus()
            return None
        cat = str(self.category_combo.currentData() or "improvement")
        entry = self.store.submit(
            title=title,
            description=desc,
            category=cat,
            rating=self._rating,
            diagnostics=self._collect_diagnostics(),
        )
        self.last_submitted = entry
        log_activity(
            "feedback",
            f"Feedback submitted ({cat})",
            entry.title,
            level="good",
        )
        bus = getattr(getattr(self.main, "ctx", None), "bus", None)
        if bus is not None:
            bus.publish(
                "feedback/submitted",
                {"id": entry.id, "category": entry.category, "title": entry.title, "rating": entry.rating},
            )
        self.title_input.clear()
        self.desc_input.clear()
        self._refresh_history()
        target = self.main if self.main is not None else self
        toast(target, "Thank you! Your feedback has been saved.", "good")
        return entry

    def copy_markdown(self) -> str:
        title = self.title_input.text().strip()
        desc = self.desc_input.toPlainText().strip()
        if title or desc:
            entry = FeedbackEntry(
                category=str(self.category_combo.currentData() or "improvement"),
                rating=self._rating,
                title=title or desc.splitlines()[0][:80],
                description=desc,
                diagnostics=self._collect_diagnostics(),
            )
        elif self.last_submitted is not None:
            entry = self.last_submitted
        else:
            recent = self.store.list_recent(limit=1)
            if not recent:
                toast(self, "Nothing to copy yet — type your feedback first.", "warn")
                return ""
            entry = recent[0]
        md = entry.to_markdown()
        QGuiApplication.clipboard().setText(md)
        toast(self, "Feedback copied as Markdown", "info")
        return md

    def _refresh_history(self) -> None:
        recent = self.store.list_recent(limit=25)
        self.count_badge.setText(f"{len(recent)} saved")
        self.history_table.setRowCount(0)
        cat_map = dict(FEEDBACK_CATEGORIES)
        for entry in recent:
            r = self.history_table.rowCount()
            self.history_table.insertRow(r)
            stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(entry.ts))
            cat_label = cat_map.get(entry.category, entry.category)
            stars = "★" * entry.rating
            for col, val in enumerate((stamp, cat_label, stars, entry.title)):
                self.history_table.setItem(r, col, QTableWidgetItem(val))
