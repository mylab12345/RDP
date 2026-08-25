"""Small reusable UI pieces: status chips, toasts, section headers — beautiful natural design 2026."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .theme import icon as theme_icon
from .theme import is_dark_theme, palette

_FONT = '"Inter", "Nimbus Sans L", "DejaVu Sans", sans-serif'


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
                border: 1px solid {border};
                border-radius: 4px;
                padding: 2px 9px 2px 8px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.3px;
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


# How many samples the sparklines keep.
HISTORY = 120


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
                border: 1px solid {pal['border']};
                border-radius: 8px;
                padding: 2px;
            }}
            QLabel#toastIcon {{
                background: {border}18;
                color: {border};
                border-radius: 6px;
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
                border: 1px solid {pal['border']};
                border-radius: 8px;
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
                border-radius: 4px;
                padding: 1px 8px;
                font-size: 11px;
                font-weight: 700;
            }}
            """
        )


# ───────────────────────────────────────────────────────────────
# Reusable UI components — natural 2026 design system
# ───────────────────────────────────────────────────────────────


class ModernButton(QPushButton):
    """Styled button with primary/ghost/subtle/danger variants and sm/md/lg sizes."""

    def __init__(
        self,
        text: str = "",
        icon_name: str = "",
        variant: str = "primary",
        size: str = "md",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._variant = variant
        self._size = size
        if icon_name:
            self.setIcon(theme_icon(icon_name))
        self._apply_style()

    def _apply_style(self) -> None:
        pal = palette()
        v = self._variant

        size_map = {
            "sm": ("11px", "5px 14px", "28px"),
            "md": ("13px", "8px 20px", "36px"),
            "lg": ("14px", "10px 26px", "44px"),
        }
        font_size, padding, min_h = size_map.get(self._size, size_map["md"])

        if v == "primary":
            bg, fg, border = pal["accent"], pal["accent_text"], pal["accent"]
            bg_h, bg_p = pal["accent_hover"], pal["accent_active"]
            bd_h, bd_p = bg_h, bg_p
            fw = "700"
        elif v == "ghost":
            bg, fg, border = "transparent", pal["fg_dim"], "transparent"
            bg_h, bg_p = pal["bg3"], pal["panel2"]
            bd_h, bd_p = pal["border"], pal["border_strong"]
            fw = "600"
        elif v == "subtle":
            bg, fg, border = pal["bg3"], pal["fg_dim"], pal["border"]
            bg_h, bg_p = pal["panel2"], pal["panel3"]
            bd_h, bd_p = pal["border_strong"], pal["border_strong"]
            fw = "600"
        elif v == "danger":
            bg, fg, border = pal["bad"], "#ffffff", pal["bad"]
            bg_h, bg_p = pal["bad"], pal["bad"]
            bd_h, bd_p = pal["bad"], pal["bad"]
            fw = "700"
        else:
            bg, fg, border = pal["bg2"], pal["fg"], pal["border"]
            bg_h, bg_p = pal["bg3"], pal["panel2"]
            bd_h, bd_p = pal["border_strong"], pal["border_strong"]
            fw = "600"

        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 6px;
                padding: {padding};
                font-size: {font_size};
                font-weight: {fw};
                min-height: {min_h};
                font-family: {_FONT};
            }}
            QPushButton:hover {{
                background: {bg_h};
                border-color: {bd_h};
            }}
            QPushButton:pressed {{
                background: {bg_p};
                border-color: {bd_p};
            }}
            QPushButton:focus {{
                border: 1px solid {pal['accent']};
                outline: none;
            }}
            QPushButton:disabled {{
                color: {pal['fg_muted']};
                background: {pal['bg']};
                border-color: {pal['border_subtle']};
            }}
            """
        )


class ModernLineEdit(QLineEdit):
    """Styled line edit with optional prefix icon and password mode."""

    def __init__(
        self,
        placeholder: str = "",
        prefix_icon: str = "",
        password: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._prefix_icon = prefix_icon
        if placeholder:
            self.setPlaceholderText(placeholder)
        if password:
            self.setEchoMode(QLineEdit.EchoMode.Password)
        if prefix_icon:
            self.setTextMargins(28, 0, 0, 0)
        self._apply_style()

    def _apply_style(self) -> None:
        pal = palette()
        left_pad = "28px" if self._prefix_icon else "14px"
        self.setStyleSheet(
            f"""
            QLineEdit {{
                background: {pal['bg2']};
                border: 1px solid {pal['border']};
                border-radius: 6px;
                padding: 8px 14px 8px {left_pad};
                color: {pal['fg']};
                font-size: 13px;
                font-family: {_FONT};
                min-height: 20px;
                selection-background-color: {pal['accent']};
                selection-color: {pal['accent_text']};
            }}
            QLineEdit:hover {{
                border-color: {pal['border_strong']};
            }}
            QLineEdit:focus {{
                border: 1px solid {pal['accent']};
            }}
            QLineEdit:disabled {{
                background: {pal['bg']};
                color: {pal['fg_muted']};
                border-color: {pal['border_subtle']};
            }}
            """
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._prefix_icon:
            from PySide6.QtGui import QPainter

            painter = QPainter(self)
            painter.setPen(QColor(palette()["fg_dim"]))
            painter.drawText(
                8, 0, 22, self.height(),
                int(Qt.AlignmentFlag.AlignCenter), self._prefix_icon,
            )
            painter.end()


class ModernComboBox(QComboBox):
    """Styled combo box with accent border on focus."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._apply_style()

    def _apply_style(self) -> None:
        pal = palette()
        self.setStyleSheet(
            f"""
            QComboBox {{
                background: {pal['bg2']};
                border: 1px solid {pal['border']};
                border-radius: 6px;
                padding: 8px 36px 8px 14px;
                color: {pal['fg']};
                font-size: 13px;
                font-family: {_FONT};
                min-height: 20px;
            }}
            QComboBox:hover {{
                border-color: {pal['border_strong']};
            }}
            QComboBox:focus {{
                border: 1px solid {pal['accent']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 32px;
                border-top-right-radius: 11px;
                border-bottom-right-radius: 11px;
            }}
            QComboBox::down-arrow {{
                image: none;
                width: 0; height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {pal['fg_dim']};
                margin-right: 12px;
                margin-top: 2px;
            }}
            QComboBox QAbstractItemView {{
                background: {pal['bg2']};
                border: 1px solid {pal['border']};
                border-radius: 6px;
                padding: 6px;
                selection-background-color: {pal['accent_subtle']};
                selection-color: {pal['fg']};
                outline: none;
                font-family: {_FONT};
            }}
            QComboBox:disabled {{
                background: {pal['bg']};
                color: {pal['fg_muted']};
                border-color: {pal['border_subtle']};
            }}
            """
        )


class SectionHeader(QWidget):
    """Reusable section header with title and optional action button."""

    def __init__(
        self,
        title: str,
        action_text: str = "",
        action_callback: callable = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        pal = palette()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title row
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        title_label = QLabel(title.upper())
        title_label.setStyleSheet(
            f"""
            QLabel {{
                font-size: 11px;
                font-weight: 700;
                color: {pal['fg_muted']};
                letter-spacing: 0.6px;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        row.addWidget(title_label)

        if action_text and action_callback:
            action_btn = QPushButton(action_text)
            action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            action_btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    color: {pal['accent']};
                    border: none;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 2px 6px;
                    font-family: {_FONT};
                }}
                QPushButton:hover {{
                    color: {pal['accent_hover']};
                }}
                """
            )
            action_btn.clicked.connect(action_callback)
            row.addWidget(action_btn)

        row.addStretch()
        layout.addLayout(row)

        # Accent underline
        underline = QFrame()
        underline.setFixedHeight(1)
        underline.setStyleSheet(
            f"background: {pal['border']}; border: none;"
        )
        layout.addWidget(underline)


class StatusIndicator(QWidget):
    """Connection status indicator with animated pulse dot."""

    _COLORS = {
        "connected": "good",
        "connecting": "warn",
        "failed": "bad",
        "disconnected": "fg_muted",
    }

    def __init__(
        self, status: str = "disconnected", parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._status = status

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Pulse dot
        self._dot = QLabel("●")
        self._dot.setFixedSize(10, 10)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._opacity_effect = QGraphicsOpacityEffect(self._dot)
        self._dot.setGraphicsEffect(self._opacity_effect)
        layout.addWidget(self._dot)

        # Status text
        self._label = QLabel(status.upper())
        self._label.setStyleSheet(
            f"""
            QLabel {{
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        layout.addWidget(self._label)

        layout.addStretch()

        # Pulse animation — theme-aware opacity range
        pulse_min = 0.3 if is_dark_theme(None) else 0.4
        self._pulse_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._pulse_anim.setDuration(2000)
        self._pulse_anim.setStartValue(pulse_min)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setEndValue(pulse_min)
        self._pulse_anim.setLoopCount(-1)

        self.set_status(status)

    def set_status(self, status: str) -> None:
        self._status = status
        pal = palette()
        color_key = self._COLORS.get(status, "fg_muted")
        color = pal.get(color_key, pal["fg_muted"])

        self._label.setText(status.upper())
        self._label.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 0.5px;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        self._dot.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                font-size: 10px;
                background: transparent;
            }}
            """
        )

        if status in ("connected", "connecting"):
            self._opacity_effect.setOpacity(1.0)
            self._pulse_anim.start()
        else:
            self._pulse_anim.stop()
            self._opacity_effect.setOpacity(1.0)


class EmptyState(QWidget):
    """Centered empty state with icon, title, subtitle, and optional action."""

    def __init__(
        self,
        icon_name: str = "",
        title: str = "",
        subtitle: str = "",
        action_text: str = "",
        action_callback: callable = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        pal = palette()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        if icon_name:
            ic = theme_icon(icon_name)
            icon_label = QLabel()
            icon_label.setPixmap(ic.pixmap(48, 48))
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setStyleSheet("background: transparent;")
            layout.addWidget(icon_label)

        if title:
            title_label = QLabel(title)
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {pal['fg']};
                    font-size: 16px;
                    font-weight: 700;
                    font-family: {_FONT};
                    background: transparent;
                }}
                """
            )
            layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            subtitle_label.setWordWrap(True)
            subtitle_label.setStyleSheet(
                f"""
                QLabel {{
                    color: {pal['fg_dim']};
                    font-size: 13px;
                    font-family: {_FONT};
                    background: transparent;
                    max-width: 360px;
                }}
                """
            )
            layout.addWidget(subtitle_label)

        if action_text and action_callback:
            action_btn = ModernButton(action_text, variant="primary", size="md")
            action_btn.clicked.connect(action_callback)
            btn_row = QHBoxLayout()
            btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_row.addWidget(action_btn)
            layout.addLayout(btn_row)


class InfoRow(QWidget):
    """Horizontal row with label and value for displaying connection details."""

    def __init__(
        self,
        label: str = "",
        value: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        pal = palette()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(8)

        label_widget = QLabel(label)
        label_widget.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg_dim']};
                font-size: 12px;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        layout.addWidget(label_widget)

        layout.addStretch()

        self._value = QLabel(value)
        self._value.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg']};
                font-size: 12px;
                font-weight: 600;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        layout.addWidget(self._value)

        self.setStyleSheet(
            f"""
            InfoRow {{
                border-bottom: 1px solid {pal['border_subtle']};
            }}
            """
        )

    def set_value(self, value: str) -> None:
        self._value.setText(value)


class SearchInput(QWidget):
    """Search bar with magnifying glass prefix and clear button."""

    def __init__(
        self,
        placeholder: str = "Search...",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        pal = palette()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Search icon
        self._icon = QLabel("\u2315")
        self._icon.setFixedSize(32, 32)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg_dim']};
                font-size: 14px;
                background: transparent;
            }}
            """
        )
        layout.addWidget(self._icon)

        # Line edit
        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.setStyleSheet(
            f"""
            QLineEdit {{
                background: {pal['bg3']};
                border: 1px solid {pal['border_subtle']};
                border-radius: 6px;
                padding: 8px 36px 8px 4px;
                color: {pal['fg']};
                font-size: 13px;
                font-family: {_FONT};
                min-height: 20px;
            }}
            QLineEdit:hover {{
                border-color: {pal['border']};
            }}
            QLineEdit:focus {{
                background: {pal['bg2']};
                border-color: {pal['accent']};
            }}
            """
        )
        layout.addWidget(self._edit, 1)

        # Clear button
        self._clear_btn = QPushButton("\u2715")
        self._clear_btn.setFixedSize(24, 24)
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {pal['fg_dim']};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {pal['bg3']};
                color: {pal['fg']};
            }}
            """
        )
        self._clear_btn.clicked.connect(self._edit.clear)
        self._clear_btn.hide()
        layout.addWidget(self._clear_btn)

        self._edit.textChanged.connect(self._update_clear)

    def _update_clear(self, text: str) -> None:
        self._clear_btn.setVisible(bool(text))

    def text(self) -> str:
        return self._edit.text()

    def setText(self, text: str) -> None:  # noqa: N802
        self._edit.setText(text)

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        self._edit.setPlaceholderText(text)

    def textChanged(self):  # noqa: N802
        return self._edit.textChanged


class CollapsibleCard(QWidget):
    """Card that can expand/collapse with animated height transition."""

    def __init__(
        self,
        title: str,
        content_widget: QWidget,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._expanded = False
        pal = palette()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Card wrapper
        self._card = QWidget()
        self._card.setObjectName("card")
        self._card.setStyleSheet(
            f"""
            QWidget#card {{
                background: {pal['bg2']};
                border: 1px solid {pal['border']};
                border-radius: 8px;
            }}
            """
        )
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Header
        self._header = QWidget()
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.setStyleSheet(
            f"""
            QWidget {{
                background: transparent;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }}
            QWidget:hover {{
                background: {pal['bg3']};
            }}
            """
        )
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg']};
                font-size: 13px;
                font-weight: 600;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        self._chevron = QLabel("\u25b8")
        self._chevron.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg_dim']};
                font-size: 12px;
                background: transparent;
            }}
            """
        )
        header_layout.addWidget(self._chevron)

        # Content container (animated max-height)
        self._content_container = QWidget()
        self._content_container.setMaximumHeight(0)
        self._content_container.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self._content_container)
        content_layout.setContentsMargins(16, 0, 16, 16)
        content_layout.addWidget(content_widget)

        card_layout.addWidget(self._header)
        card_layout.addWidget(self._content_container)

        main_layout.addWidget(self._card)

        # Animation
        self._anim = QPropertyAnimation(self._content_container, b"maximumHeight")
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._header.mousePressEvent = self._toggle

    def _toggle(self, event=None) -> None:
        if self._expanded:
            self._collapse()
        else:
            self._expand()

    def _expand(self) -> None:
        self._expanded = True
        self._chevron.setText("\u25be")
        self._content_container.setMaximumHeight(16777215)
        self._content_container.adjustSize()
        target = self._content_container.sizeHint().height()
        self._content_container.setMaximumHeight(0)
        self._anim.setDuration(250)
        self._anim.setStartValue(0)
        self._anim.setEndValue(target)
        self._anim.start()

    def _collapse(self) -> None:
        self._expanded = False
        self._chevron.setText("\u25b8")
        self._anim.setDuration(200)
        self._anim.setStartValue(self._content_container.height())
        self._anim.setEndValue(0)
        self._anim.start()

    def toggle(self) -> None:
        """Programmatically toggle expanded state."""
        self._toggle()


class ConnectionStatusBar(QWidget):
    """Thin status bar showing connection state, latency, protocol, and display mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(32)
        pal = palette()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Gradient accent line
        accent_line = QFrame()
        accent_line.setFixedHeight(2)
        accent_line.setStyleSheet(
            f"QFrame {{ background: {pal['accent_gradient']}; border: none; }}"
        )
        main_layout.addWidget(accent_line)

        # Content area
        content = QWidget()
        content.setStyleSheet(f"QWidget {{ background: {pal['panel']}; }}")
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(12, 0, 12, 0)
        content_layout.setSpacing(16)

        self._status = StatusIndicator("disconnected")
        content_layout.addWidget(self._status)

        content_layout.addStretch()

        self._latency = QLabel("-- ms")
        self._latency.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg_dim']};
                font-size: 11px;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        content_layout.addWidget(self._latency)

        self._protocol = QLabel("RDP")
        self._protocol.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg_dim']};
                font-size: 11px;
                font-weight: 600;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        content_layout.addWidget(self._protocol)

        self._display = QLabel("")
        self._display.setStyleSheet(
            f"""
            QLabel {{
                color: {pal['fg_dim']};
                font-size: 11px;
                font-family: {_FONT};
                background: transparent;
            }}
            """
        )
        content_layout.addWidget(self._display)

        main_layout.addWidget(content)

    def set_status(self, status: str) -> None:
        self._status.set_status(status)

    def set_latency(self, latency: str) -> None:
        self._latency.setText(latency)

    def set_protocol(self, protocol: str) -> None:
        self._protocol.setText(protocol)

    def set_display_mode(self, mode: str) -> None:
        self._display.setText(mode)


# ----------------------------------------------------------------------
# Motion, shadows and shimmer — 2026 polish layer (all optional via
# Settings → UI; see theme.MOTIONS_ENABLED)
# ----------------------------------------------------------------------
def _motion_on() -> bool:
    from .theme import MOTIONS_ENABLED

    return MOTIONS_ENABLED


def animate_in(widget: QWidget, duration: int = 140) -> None:
    """Fade a dialog/panel in (opacity 0.55 → 1, ease-out).

    Skipped entirely when animations are disabled in Settings.
    """
    if not _motion_on():
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    effect.setOpacity(0.55)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.55)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._kb_anim = anim  # keep a reference so the loop owns it

    def _cleanup() -> None:
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
        anim.deleteLater()

    anim.finished.connect(_cleanup)
    anim.start()


def pulse(widget: QWidget, duration: int = 320) -> None:
    """One soft opacity pulse — used when a session connects."""
    if not _motion_on():
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(duration)
    anim.setKeyValueAt(0.0, 1.0)
    anim.setKeyValueAt(0.5, 0.45)
    anim.setKeyValueAt(1.0, 1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._kb_anim = anim

    def _cleanup() -> None:
        if widget.graphicsEffect() is effect:
            widget.setGraphicsEffect(None)
        anim.deleteLater()

    anim.finished.connect(_cleanup)
    anim.start()


def soft_shadow(widget: QWidget, blur: int = 14, dy: int = 3, alpha: int = 90) -> None:
    """Bento-style soft drop shadow on floating surfaces (menus, cards)."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, dy)
    shadow.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(shadow)


class ShimmerProgressBar(QProgressBar):
    """Progress bar with a moving highlight band while a transfer runs."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setTextVisible(False)
        self.setRange(0, 1000)
        self.setValue(0)
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    def set_percent(self, pct: float) -> None:
        self.setValue(int(max(0.0, min(100.0, pct)) * 10))

    def start_shimmer(self) -> None:
        if _motion_on():
            self._timer.start()

    def stop_shimmer(self) -> None:
        self._timer.stop()
        self.setStyleSheet("")

    def _tick(self) -> None:
        from .theme import palette

        pal = palette()
        self._phase = (self._phase + 0.12) % 1.0
        s = f"{self._phase:.2f}"
        self.setStyleSheet(
            "QProgressBar { background: transparent; border: none; }"
            f"QProgressBar::chunk {{ border-radius: 4px;"
            f" background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 {pal['accent']}, stop:{s} {pal['accent_hover']},"
            f" stop:1 {pal['accent']}); }}"
        )
