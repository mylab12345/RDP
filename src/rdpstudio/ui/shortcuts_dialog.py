"""Keyboard-shortcuts reference dialog — a calm, grouped table (Help → shortcuts)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from .theme import icon, palette

_GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "General",
        [
            ("New saved session", "Ctrl + N"),
            ("Command palette / switcher", "Ctrl + P  or  Ctrl + K"),
            ("Settings", "Ctrl + ,"),
            ("Toggle sidebar", "Ctrl + B"),
            ("Quit", "Ctrl + Q"),
        ],
    ),
    (
        "Tabs",
        [
            ("Close current tab", "Ctrl + W"),
            ("Duplicate current tab", "Ctrl + Shift + D"),
            ("Next tab", "Ctrl + Tab"),
            ("Previous tab", "Ctrl + Shift + Tab"),
            ("Switch to tab 1–9", "Ctrl + 1 … 9"),
            ("Rename a tab", "double-click its tab"),
        ],
    ),
    (
        "Tools",
        [
            ("Network tools / port scanner", "Ctrl + Shift + N"),
            ("SSH key utility", "Ctrl + Shift + U"),
            ("Local terminal tab", "Ctrl + Shift + T"),
            ("Terminal: start/stop logging", "Ctrl + Shift + L"),
            ("Jump to quick connect", "Ctrl + Shift + K"),
        ],
    ),
]


class ShortcutsDialog(QDialog):
    """Read-only, grouped keyboard shortcut reference."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.setObjectName("shortcutsDialog")
        pal = palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(12)

        head = QGridLayout()
        head.setContentsMargins(0, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(icon("key", pal["accent"]).pixmap(20, 20))
        head.addWidget(logo, 0, 0)
        title = QLabel("Keyboard shortcuts")
        title.setObjectName("dialogTitle")
        title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {pal['fg']};")
        head.addWidget(title, 0, 1)
        sub = QLabel("Everything you can reach without the mouse.")
        sub.setStyleSheet(f"font-size: 12px; color: {pal['fg_muted']};")
        head.addWidget(sub, 1, 1)
        head.setColumnStretch(2, 1)
        root.addLayout(head)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(14)

        for group_name, rows in _GROUPS:
            frame = QFrame()
            frame.setObjectName("group")
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(16, 12, 16, 14)
            fl.setSpacing(6)
            gtitle = QLabel(group_name)
            gtitle.setStyleSheet(
                f"font-size: 11px; font-weight: 700; letter-spacing: 0.6px;"
                f" color: {pal['fg_dim']}; text-transform: uppercase;"
            )
            fl.addWidget(gtitle)
            grid = QGridLayout()
            grid.setContentsMargins(0, 2, 0, 0)
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(5)
            grid.setColumnStretch(0, 1)
            for i, (label, keys) in enumerate(rows):
                l1 = QLabel(label)
                l1.setStyleSheet(f"font-size: 13px; color: {pal['fg']};")
                k = QLabel(keys)
                k.setStyleSheet(
                    f"font-family: {pal.get('ui_mono') or 'monospace'}; font-size: 11.5px;"
                    f" color: {pal['fg_dim']}; background: {pal['bg3']};"
                    f" padding: 1px 8px; border-radius: 4px;"
                )
                k.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(l1, i, 0)
                grid.addWidget(k, i, 1)
            fl.addLayout(grid)
            bl.addWidget(frame)

        bl.addStretch(1)
        root.addWidget(body, 1)
        self.resize(460, 560)
