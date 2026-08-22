"""Small reusable UI pieces: status chips, toasts, section headers — modern."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .theme import palette


class StateChip(QLabel):
    """Modern pill with dot — like Linear / Vercel status."""

    def __init__(self, text: str = "", color: str = "fg_dim", parent=None) -> None:
        super().__init__(parent)
        self._color_key = color
        self._dot = True
        self.set_color(color)
        self.setText(text)

    def set_color(self, color: str) -> None:
        self._color_key = color
        pal = palette()
        hexcolor = pal.get(color, color)
        # Map semantic to dot + subtle bg
        bg = {
            "good": f"{hexcolor}18",
            "warn": f"{hexcolor}18",
            "bad": f"{hexcolor}18",
            "info": f"{hexcolor}18",
            "fg_dim": pal["bg3"],
        }.get(color, f"{hexcolor}15")

        border = {
            "good": f"{hexcolor}33",
            "warn": f"{hexcolor}33",
            "bad": f"{hexcolor}33",
            "info": f"{hexcolor}33",
            "fg_dim": pal["border"],
        }.get(color, f"{hexcolor}22")

        # Dot via unicode + styling
        self.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {hexcolor if color != 'fg_dim' else pal['fg_dim']};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 3px 12px 3px 10px;
                font-size: 11.5px;
                font-weight: 600;
                letter-spacing: 0.2px;
            }}
            """
        )

    def setText(self, text: str) -> None:  # noqa: N802
        if text and self._color_key in ("good", "warn", "bad", "info", "connected", "connecting", "reconnecting", "closed", "failed"):
            # Normalize state names to colors
            display = text
            super().setText(f"●  {display}")
        else:
            super().setText(text)


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
    """Modern transient notification — card with icon, subtle shadow, auto-dismiss."""

    def __init__(self, parent: QWidget, text: str, kind: str = "info") -> None:
        super().__init__(parent)
        pal = palette()
        border_map = {"info": "info", "good": "good", "bad": "bad", "warn": "warn"}
        border_key = border_map.get(kind, "info")
        border = pal.get(border_key, pal["info"])
        bg = pal["panel"]
        # Icon map
        icons = {"info": "ℹ", "good": "✓", "bad": "✕", "warn": "⚠"}
        icon_char = icons.get(kind, "ℹ")

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # Card styling
        self.setStyleSheet(
            f"""
            QWidget#toastCard {{
                background: {bg};
                border: 1px solid {pal['border']};
                border-left: 3px solid {border};
                border-radius: 12px;
                padding: 2px;
            }}
            QLabel#toastIcon {{
                background: {border}18;
                color: {border};
                border-radius: 8px;
                padding: 6px;
                font-weight: 700;
                font-size: 14px;
                min-width: 20px;
                min-height: 20px;
            }}
            QLabel#toastText {{
                color: {pal['fg']};
                font-size: 13px;
                font-weight: 450;
            }}
            """
        )

        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(pal["shadow"] and __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(pal["shadow"]) or __import__("PySide6.QtGui", fromlist=["QColor"]).QColor("#00000066"))
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("toastCard")
        outer.addWidget(card)

        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 14, 10)
        lay.setSpacing(10)

        icon_label = QLabel(icon_char)
        icon_label.setObjectName("toastIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_label)

        label = QLabel(text)
        label.setObjectName("toastText")
        label.setWordWrap(True)
        label.setMinimumWidth(200)
        label.setMaximumWidth(380)
        lay.addWidget(label, 1)

        self.adjustSize()
        if parent:
            x = max(12, parent.width() - self.width() - 20)
            y = max(12, parent.height() - self.height() - 48)
            self.move(QPoint(x, y))
        self.show()
        self.raise_()

        # Fade out animation
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        QTimer.singleShot(3400, self._start_hide)

    def _start_hide(self):
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.deleteLater)
        self._anim.start()


def toast(parent: QWidget, text: str, kind: str = "info") -> None:
    Toast(parent, text, kind)


class ModernCard(QWidget):
    """Reusable card container with modern styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        pal = palette()
        self.setStyleSheet(
            f"""
            QWidget#card {{
                background: {pal['bg2']};
                border: 1px solid {pal['border']};
                border-radius: 12px;
            }}
            """
        )
