"""Small reusable UI pieces: status chips, toasts, section headers — beautiful natural design 2026."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .theme import palette


class StateChip(QLabel):
    """Modern pill with dot — bento style, soft glow, natural."""

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

        # Background mapping with subtle alpha for natural depth
        bg_map = {
            "good": f"{hexcolor}22",
            "warn": f"{hexcolor}22",
            "bad": f"{hexcolor}1E",
            "info": f"{hexcolor}20",
            "fg_dim": pal["bg3"],
            "accent": pal["accent_subtle"],
        }
        bg = bg_map.get(color, f"{hexcolor}18")

        border_map = {
            "good": f"{hexcolor}40",
            "warn": f"{hexcolor}40",
            "bad": f"{hexcolor}40",
            "info": f"{hexcolor}40",
            "fg_dim": pal["border"],
            "accent": f"{pal['accent']}35",
        }
        border = border_map.get(color, f"{hexcolor}30")

        text_color = {
            "good": pal.get("good", hexcolor),
            "warn": pal.get("warn", hexcolor),
            "bad": pal.get("bad", hexcolor),
            "info": pal.get("info", hexcolor),
            "fg_dim": pal["fg_dim"],
            "accent": pal["accent"],
        }.get(color, hexcolor if color != "fg_dim" else pal["fg_dim"])

        self.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {text_color};
                border: 1.5px solid {border};
                border-radius: 20px;
                padding: 4px 14px 4px 12px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.6px;
                font-family: "Inter", "Nimbus Sans L", "DejaVu Sans", sans-serif;
            }}
            """
        )

    def setText(self, text: str) -> None:  # noqa: N802
        if text and self._color_key in (
            "good",
            "warn",
            "bad",
            "info",
            "accent",
            "connected",
            "connecting",
            "reconnecting",
            "closed",
            "failed",
        ):
            display = text.upper() if len(text) < 20 else text
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
    """Modern transient notification — bento card with icon, soft shadow, auto-dismiss."""

    def __init__(self, parent: QWidget, text: str, kind: str = "info") -> None:
        super().__init__(parent)
        pal = palette()
        border_map = {"info": "info", "good": "good", "bad": "bad", "warn": "warn"}
        border_key = border_map.get(kind, "info")
        border = pal.get(border_key, pal["info"])
        bg = pal["bg2"]

        icons = {"info": "✦", "good": "✓", "bad": "✕", "warn": "⚠"}
        icon_char = icons.get(kind, "✦")

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.setStyleSheet(
            f"""
            QWidget#toastCard {{
                background: {bg};
                border: 1.5px solid {pal['border']};
                border-radius: 14px;
                padding: 2px;
            }}
            QLabel#toastIcon {{
                background: {border}18;
                color: {border};
                border-radius: 10px;
                padding: 8px;
                font-weight: 800;
                font-size: 14px;
                min-width: 22px;
                min-height: 22px;
            }}
            QLabel#toastText {{
                color: {pal['fg']};
                font-size: 13px;
                font-weight: 500;
                line-height: 1.4;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(pal["shadow"] or "#00000066"))
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        card = QWidget()
        card.setObjectName("toastCard")
        outer.addWidget(card)

        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 12, 16, 12)
        lay.setSpacing(12)

        icon_label = QLabel(icon_char)
        icon_label.setObjectName("toastIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon_label)

        label = QLabel(text)
        label.setObjectName("toastText")
        label.setWordWrap(True)
        label.setMinimumWidth(220)
        label.setMaximumWidth(400)
        lay.addWidget(label, 1)

        self.adjustSize()
        if parent is not None:
            x = max(12, parent.width() - self.width() - 20)
            y = max(12, parent.height() - self.height() - 56)
            self.move(parent.mapToGlobal(QPoint(x, y)))
        self.show()
        self.raise_()

        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        QTimer.singleShot(3600, self._start_hide)

    def _start_hide(self):
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.deleteLater)
        self._anim.start()


def toast(parent: QWidget, text: str, kind: str = "info") -> None:
    Toast(parent, text, kind)


class ModernCard(QWidget):
    """Reusable bento card container with natural styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        pal = palette()
        self.setStyleSheet(
            f"""
            QWidget#card {{
                background: {pal['bg2']};
                border: 1.5px solid {pal['border']};
                border-radius: 14px;
            }}
            QWidget#card:hover {{
                border-color: {pal['border_strong']};
            }}
            """
        )


class PillBadge(QLabel):
    """Small pill badge for counts, tags, etc."""

    def __init__(self, text: str = "", kind: str = "default", parent=None):
        super().__init__(text, parent)
        pal = palette()
        bg = {
            "default": pal["bg3"],
            "accent": pal["accent_subtle"],
            "good": f"{pal['good']}20",
            "warn": f"{pal['warn']}20",
        }.get(kind, pal["bg3"])
        fg = {
            "default": pal["fg_dim"],
            "accent": pal["accent"],
            "good": pal["good"],
            "warn": pal["warn"],
        }.get(kind, pal["fg_dim"])
        border = {
            "default": pal["border"],
            "accent": f"{pal['accent']}30",
            "good": f"{pal['good']}30",
            "warn": f"{pal['warn']}30",
        }.get(kind, pal["border"])

        self.setStyleSheet(
            f"""
            QLabel {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 20px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 700;
            }}
            """
        )
