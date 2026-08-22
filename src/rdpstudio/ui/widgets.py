"""Small reusable UI pieces: status chips, toasts, section headers."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .theme import palette


class StateChip(QLabel):
    """Coloured pill showing connection state."""

    def __init__(self, text: str = "", color: str = "fg_dim", parent=None) -> None:
        super().__init__(text, parent)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        pal = palette()
        hexcolor = pal.get(color, color)
        self.setStyleSheet(
            f"background: {hexcolor}22; color: {hexcolor}; border: 1px solid {hexcolor};"
            "border-radius: 8px; padding: 1px 9px; font-size: 11px; font-weight: 700;"
        )


STATE_COLORS = {
    "connecting": "info",
    "connected": "good",
    "reconnecting": "warn",
    "closed": "fg_dim",
    "failed": "bad",
}


def format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.0f} {unit}" if unit in ("B",) else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


class Toast(QWidget):
    """Transient notification sliding in from the bottom-right."""

    def __init__(self, parent: QWidget, text: str, kind: str = "info") -> None:
        super().__init__(parent)
        pal = palette()
        border = pal.get({"info": "info", "good": "good", "bad": "bad", "warn": "warn"}[kind], "info")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"background: {pal['panel']}; color: {pal['fg']}; border: 1px solid {border};"
            "border-radius: 8px; padding: 10px 14px; font-size: 12px;"
        )
        lay = QVBoxLayout(self)
        label = QLabel(text)
        label.setWordWrap(True)
        lay.addWidget(label)
        self.adjustSize()
        if parent:
            x = max(8, parent.width() - self.width() - 18)
            y = max(8, parent.height() - self.height() - 40)
            self.move(QPoint(x, y))
        self.show()
        self.raise_()
        QTimer.singleShot(3600, self.deleteLater)


def toast(parent: QWidget, text: str, kind: str = "info") -> None:
    Toast(parent, text, kind)
