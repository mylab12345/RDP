"""Look & feel: modern QSS themes, palette, icon loading.

Modernized for 2026: soft dark/light, rounded 10px, subtle borders,
focused states, improved tab bar, toolbar, tree, inputs, scrollbars.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication

RESOURCES = Path(__file__).parent.parent / "resources"
ICONS = RESOURCES / "icons"

# ----------------------------------------------------------------------
# Palettes — refined, low-contrast modern (inspired by Linear, VSCode, Raycast)
# ----------------------------------------------------------------------
PALETTE = {
    "dark": {
        # Base
        "bg": "#0b0f19",          # app background
        "bg2": "#111726",         # cards, inputs, secondary bg
        "bg3": "#151c2e",         # hover / tertiary
        "panel": "#181f33",       # panels, menus
        "panel2": "#1f2942",      # button, hover
        "panel3": "#26314d",      # active / pressed
        "border": "#222d47",      # subtle border
        "border_strong": "#2d3a5a",
        # Text
        "fg": "#e6eaf2",
        "fg_dim": "#8a94ac",
        "fg_muted": "#5c677e",
        # Accent — modern indigo/blue
        "accent": "#6c8bff",
        "accent_hover": "#829dff",
        "accent_active": "#5a78e6",
        "accent_text": "#ffffff",
        "accent_subtle": "#6c8bff18",
        # Semantic
        "good": "#6ee7a5",
        "warn": "#fbbf6a",
        "bad": "#ff7a7a",
        "info": "#7cc4ff",
        # Terminal
        "term_bg": "#0b0f19",
        "term_fg": "#d8dee9",
        "sel": "#2a3a5e",
        # Shadows / extras
        "shadow": "#00000066",
        "overlay": "#0b0f1999",
    },
    "light": {
        "bg": "#f6f7fb",
        "bg2": "#ffffff",
        "bg3": "#eef1f8",
        "panel": "#e8ecf5",
        "panel2": "#dde4f0",
        "panel3": "#cfd8ea",
        "border": "#d6deeb",
        "border_strong": "#b8c4db",
        "fg": "#151a2b",
        "fg_dim": "#6b768f",
        "fg_muted": "#8f9ab3",
        "accent": "#4f6ef7",
        "accent_hover": "#6a84ff",
        "accent_active": "#3f5ae0",
        "accent_text": "#ffffff",
        "accent_subtle": "#4f6ef718",
        "good": "#0e9f6e",
        "warn": "#c07a00",
        "bad": "#e02424",
        "info": "#1a73e8",
        "term_bg": "#ffffff",
        "term_fg": "#151a2b",
        "sel": "#c7d9ff",
        "shadow": "#00000014",
        "overlay": "#ffffff99",
    },
    "forest": {
        "bg": "#0c1410",
        "bg2": "#121c16",
        "bg3": "#18241c",
        "panel": "#1a2820",
        "panel2": "#22362a",
        "panel3": "#2a4434",
        "border": "#2a4032",
        "border_strong": "#3a5844",
        "fg": "#e2eee4",
        "fg_dim": "#8aa890",
        "fg_muted": "#5e7464",
        "accent": "#6fbf78",
        "accent_hover": "#86d08e",
        "accent_active": "#5aa863",
        "accent_text": "#0c1410",
        "accent_subtle": "#6fbf7818",
        "good": "#8fd4a0",
        "warn": "#d4b06a",
        "bad": "#d4786a",
        "info": "#7eb8a0",
        "term_bg": "#0c1410",
        "term_fg": "#d5e4d4",
        "sel": "#2a4a34",
        "shadow": "#00000066",
        "overlay": "#0c141099",
    },
    "ocean": {
        "bg": "#07141c",
        "bg2": "#0c1d28",
        "bg3": "#122632",
        "panel": "#163040",
        "panel2": "#1c3c50",
        "panel3": "#244858",
        "border": "#1e3a4a",
        "border_strong": "#2c5468",
        "fg": "#dceef4",
        "fg_dim": "#7aa4b4",
        "fg_muted": "#4e7484",
        "accent": "#3db8c4",
        "accent_hover": "#58c8d2",
        "accent_active": "#2a9eaa",
        "accent_text": "#07141c",
        "accent_subtle": "#3db8c418",
        "good": "#5ed0b0",
        "warn": "#e0b46a",
        "bad": "#e07880",
        "info": "#6ec8e8",
        "term_bg": "#061018",
        "term_fg": "#d0e8ee",
        "sel": "#1a4050",
        "shadow": "#00000066",
        "overlay": "#07141c99",
    },
    "sunset": {
        "bg": "#161014",
        "bg2": "#20161c",
        "bg3": "#2a1c22",
        "panel": "#322028",
        "panel2": "#402830",
        "panel3": "#4c3038",
        "border": "#3c2830",
        "border_strong": "#5a3840",
        "fg": "#f4e6dc",
        "fg_dim": "#b89890",
        "fg_muted": "#806868",
        "accent": "#e07a4a",
        "accent_hover": "#ec9060",
        "accent_active": "#c8683a",
        "accent_text": "#1a1010",
        "accent_subtle": "#e07a4a18",
        "good": "#c4b06a",
        "warn": "#f0a050",
        "bad": "#e06060",
        "info": "#d4a0c0",
        "term_bg": "#160e12",
        "term_fg": "#f0ddd0",
        "sel": "#4a2830",
        "shadow": "#00000066",
        "overlay": "#16101499",
    },
    "aurora": {
        "bg": "#0a1218",
        "bg2": "#101c24",
        "bg3": "#162430",
        "panel": "#1a2834",
        "panel2": "#223440",
        "panel3": "#2a4050",
        "border": "#243848",
        "border_strong": "#345060",
        "fg": "#e4f4f0",
        "fg_dim": "#88b0b0",
        "fg_muted": "#5a787c",
        "accent": "#5ee0b8",
        "accent_hover": "#78ecd0",
        "accent_active": "#42c8a0",
        "accent_text": "#0a1218",
        "accent_subtle": "#5ee0b818",
        "good": "#6ee0c0",
        "warn": "#c8e080",
        "bad": "#e080a0",
        "info": "#80b0e8",
        "term_bg": "#081018",
        "term_fg": "#d8ece8",
        "sel": "#1c4050",
        "shadow": "#00000066",
        "overlay": "#0a121899",
    },
    "meadow": {
        "bg": "#f3f6ee",
        "bg2": "#fbfcf6",
        "bg3": "#e8eedc",
        "panel": "#e4ebd8",
        "panel2": "#d6e0c8",
        "panel3": "#c6d4b4",
        "border": "#d0dcc0",
        "border_strong": "#b4c4a0",
        "fg": "#1e2a1c",
        "fg_dim": "#5e6e54",
        "fg_muted": "#88987c",
        "accent": "#4a8c4e",
        "accent_hover": "#5aa05e",
        "accent_active": "#3c7840",
        "accent_text": "#ffffff",
        "accent_subtle": "#4a8c4e18",
        "good": "#2d8a4e",
        "warn": "#b07a10",
        "bad": "#c04038",
        "info": "#2a7a88",
        "term_bg": "#fbfcf6",
        "term_fg": "#1e2a1c",
        "sel": "#c8dcb0",
        "shadow": "#1e2a1c14",
        "overlay": "#f3f6ee99",
    },
    "desert": {
        "bg": "#f4ece0",
        "bg2": "#fbf6ee",
        "bg3": "#ece0d0",
        "panel": "#e8dcc8",
        "panel2": "#dcccb4",
        "panel3": "#d0bc9c",
        "border": "#d8c8b0",
        "border_strong": "#c0a888",
        "fg": "#2c2218",
        "fg_dim": "#7a6854",
        "fg_muted": "#a09078",
        "accent": "#c4783a",
        "accent_hover": "#d48a4c",
        "accent_active": "#b06830",
        "accent_text": "#ffffff",
        "accent_subtle": "#c4783a18",
        "good": "#5a8a48",
        "warn": "#c48820",
        "bad": "#c05038",
        "info": "#3a7a88",
        "term_bg": "#fbf6ee",
        "term_fg": "#2c2218",
        "sel": "#e8c8a0",
        "shadow": "#2c221814",
        "overlay": "#f4ece099",
    },
}


def is_dark_theme(name: str | None) -> bool:
    from ..core.settings import DARK_THEMES

    return (name or _current_theme) in DARK_THEMES

_icon_cache: dict[str, QIcon] = {}

GLYPH_FALLBACK = {
    "terminal": ">_",
    "windows": "▣",
    "console": "▢",
    "server": "▤",
    "key": "⚿",
    "plug": "⇄",
    "folder": "▣",
    "gear": "⚙",
    "transfer": "⇩",
    "shield": "⛨",
    "plus": "＋",
    "connect": "↻",
    "search": "⌕",
    "edit": "✎",
    "trash": "🗑",
    "logo": "◐",
}


def icon(name: str) -> QIcon:
    """Load an SVG icon; falls back to a drawn text glyph when unavailable."""
    cached = _icon_cache.get(name)
    if cached is not None:
        return cached
    path = ICONS / f"{name}.svg"
    ic = QIcon(str(path)) if path.exists() else QIcon()
    if ic.isNull() or not ic.availableSizes():
        ic = _glyph_icon(GLYPH_FALLBACK.get(name, "•"))
    _icon_cache[name] = ic
    return ic


def _glyph_icon(glyph: str) -> QIcon:
    """Render a text glyph into a pixmap."""
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtGui import QGuiApplication, QPainter, QPixmap

    if QGuiApplication.instance() is None:
        return QIcon()
    pix = QPixmap(28, 28)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setPen(QColor(PALETTE["dark"]["fg"]))
    font = painter.font()
    font.setPointSize(15)
    font.setWeight(font.Weight.Medium)
    painter.setFont(font)
    painter.drawText(pix.rect(), _Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pix)


# Theme currently applied to the app (see apply_theme). Widgets that build
# colors at construction time use this so light theme doesn't render dark.
_current_theme = "dark"


def current_theme() -> str:
    return _current_theme


def palette(theme: str | None = None) -> dict[str, str]:
    """Palette for ``theme`` — defaults to the currently applied theme."""
    return PALETTE.get(theme or _current_theme, PALETTE["dark"])


# ----------------------------------------------------------------------
# Modern QSS — 2026 style: rounded, soft, spacious, focus rings
# ----------------------------------------------------------------------
_QSS = """
/* Global */
* {{
    font-family: "Inter", "SF Pro Display", "Segoe UI", "Geist", "DejaVu Sans", sans-serif;
    outline: none;
}}
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {fg};
    font-size: 13.5px;
}}
QToolTip {{
    background: {panel};
    color: {fg};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12.5px;
}}

/* Menu bar — minimal, modern */
QMenuBar {{
    background: {bg};
    border-bottom: 1px solid {border};
    padding: 2px 8px;
    spacing: 4px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 8px;
    color: {fg_dim};
}}
QMenuBar::item:selected {{
    background: {bg3};
    color: {fg};
}}

/* Menus — card style */
QMenu {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 6px;
    margin: 4px;
}}
QMenu::item {{
    padding: 8px 14px 8px 28px;
    border-radius: 8px;
    color: {fg};
}}
QMenu::item:selected {{
    background: {panel2};
    color: {fg};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 6px 10px;
}}
QMenu::indicator {{
    left: 8px;
    width: 14px;
    height: 14px;
}}

/* Toolbar — MobaXterm-style: compact single row of icon buttons */
QToolBar {{
    background: {bg};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 1px;
    padding: 4px 10px;
    min-height: 40px;
}}
QToolBar#moxaToolbar {{
    spacing: 1px;
    padding: 3px 10px;
    min-height: 38px;
}}
QToolBar#moxaToolbar QToolButton {{
    padding: 6px;
    min-width: 26px;
    min-height: 24px;
}}
QToolBar::separator {{
    width: 1px;
    background: {border};
    margin: 8px 10px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 7px 12px;
    color: {fg_dim};
    font-weight: 500;
}}
QToolButton:hover {{
    background: {bg3};
    color: {fg};
    border-color: {border};
}}
QToolButton:pressed {{
    background: {panel2};
    border-color: {border_strong};
}}
QToolButton:checked {{
    background: {accent_subtle};
    color: {accent};
    border-color: {accent}33;
}}

/* Buttons — modern, rounded, subtle */
QPushButton {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 8px 16px;
    color: {fg};
    font-weight: 500;
    min-height: 14px;
}}
QPushButton:hover {{
    background: {panel2};
    border-color: {border_strong};
}}
QPushButton:pressed {{
    background: {panel3};
}}
QPushButton:disabled {{
    color: {fg_muted};
    background: {bg2};
    border-color: {border};
}}
QPushButton#primary {{
    background: {accent};
    color: {accent_text};
    border: none;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {accent_hover};
}}
QPushButton#primary:pressed {{
    background: {accent_active};
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {fg_dim};
}}
QPushButton#ghost:hover {{
    background: {bg3};
    color: {fg};
    border-color: {border};
}}
QPushButton#subtle {{
    background: {bg3};
    border: 1px solid {border};
    color: {fg_dim};
}}
QPushButton#subtle:hover {{
    color: {fg};
    border-color: {border_strong};
}}

/* Inputs — taller, rounded, focus ring */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg2};
    border: 1.5px solid {border};
    border-radius: 10px;
    padding: 8px 12px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    color: {fg};
    min-height: 18px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {accent};
    background: {bg2};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
    border-color: {border_strong};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: {bg};
    color: {fg_muted};
}}
QLineEdit#search {{
    border-radius: 12px;
    padding-left: 36px;
    background: {bg3};
    border-color: transparent;
}}
QLineEdit#search:focus {{
    background: {bg2};
    border-color: {accent};
}}

/* Combobox dropdown */
QComboBox::drop-down {{
    border: none;
    width: 28px;
    border-top-right-radius: 10px;
    border-bottom-right-radius: 10px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {fg_dim};
    margin-right: 10px;
    margin-top: 2px;
}}
QComboBox QAbstractItemView {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 6px;
    selection-background-color: {panel2};
    outline: none;
}}

/* Tabs — MobaXterm-style: compact flat tabs, accent underline when active */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
    background: {bg2};
    top: -1px;
}}
QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {fg_dim};
    padding: 7px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 2px;
    font-weight: 500;
    min-width: 64px;
}}
QTabBar::tab:selected {{
    background: {bg2};
    color: {fg};
    border-bottom: 2px solid {accent};
}}
QTabBar::tab:hover:!selected {{
    background: {bg3};
    color: {fg};
}}
QTabBar::close-button {{
    image: none;
    subcontrol-position: right;
    width: 16px; height: 16px;
    border-radius: 6px;
    margin-left: 8px;
}}
QTabBar::close-button:hover {{
    background: {panel2};
}}
QTabBar QToolButton {{
    background: {bg3};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 4px;
}}
QTabBar QToolButton:hover {{
    background: {panel2};
}}

/* Tree / List / Table — modern cards */
QTreeView, QListView, QTableView {{
    background: {bg2};
    alternate-background-color: {bg};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 4px;
    outline: none;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 8px 10px;
    border-radius: 8px;
    margin: 1px 2px;
    color: {fg};
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {bg3};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {panel2};
    color: {fg};
    border: 1px solid {border};
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent_subtle};
    border-color: {accent}33;
}}
QTreeView::branch {{
    background: transparent;
}}
QHeaderView::section {{
    background: {bg2};
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
    padding: 10px 12px;
    font-weight: 600;
    color: {fg_dim};
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

/* Splitter */
QSplitter::handle {{
    background: {border};
    width: 1px;
    height: 1px;
}}
QSplitter::handle:hover {{
    background: {accent}66;
}}

/* Scrollbars — ultra thin, modern */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 2px 2px 0px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {panel2};
    border-radius: 4px;
    min-height: 32px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {panel3};
    width: 8px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px 2px 2px 2px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {panel2};
    border-radius: 4px;
    min-width: 32px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {panel3};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* Status bar — minimal */
QStatusBar {{
    background: {bg2};
    border-top: 1px solid {border};
    color: {fg_dim};
    padding: 2px 12px;
    font-size: 12px;
}}
QStatusBar::item {{
    border: none;
}}

/* GroupBox — card */
QGroupBox {{
    border: 1px solid {border};
    border-radius: 12px;
    margin-top: 16px;
    padding: 16px 12px 12px 12px;
    background: {bg2};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    top: 4px;
    padding: 2px 10px;
    background: {bg2};
    color: {fg_dim};
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}

/* Progress */
QProgressBar {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 8px;
    text-align: center;
    height: 8px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 7px;
}}

/* Checkboxes / Radio */
QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {fg};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px; height: 18px;
    border-radius: 6px;
    border: 1.5px solid {border_strong};
    background: {bg2};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: none;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent};
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}

/* Labels */
QLabel#muted {{
    color: {fg_dim};
}}
QLabel#h1 {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.3px;
}}
QLabel#h2 {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#caption {{
    font-size: 12px;
    color: {fg_dim};
}}
QFrame#hairline {{
    background: {border};
    max-height: 1px;
    border: none;
}}

/* Dialogs — rounded, elevated */
QDialog {{
    background: {bg};
    border-radius: 16px;
}}

/* Custom: search container, chips, etc. */
QWidget#card {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 12px;
}}
QWidget#card_hover:hover {{
    border-color: {border_strong};
}}
QWidget#header {{
    background: {bg2};
    border-bottom: 1px solid {border};
}}
QWidget#sidebar {{
    background: {bg};
    border-right: 1px solid {border};
}}

/* MobaXterm-style per-tab command line (below the terminal) */
QWidget#commandBar {{
    background: {bg2};
    border-top: 1px solid {border};
}}
QLabel#commandPrompt {{
    color: {accent};
    font-size: 13px;
    font-weight: 700;
}}
QLineEdit#commandLine {{
    background: {bg3};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 5px 10px;
    font-size: 12.5px;
    min-height: 12px;
}}
QLineEdit#commandLine:focus {{
    border-color: {accent};
    background: {bg2};
}}

/* Bottom remote-monitor panel */
QWidget#monitorPanel {{
    background: {bg2};
    border-top: 1px solid {border};
}}
QWidget#monitorHeader {{
    background: {bg3};
    border-bottom: 1px solid {border};
    min-height: 26px;
}}
QWidget#monitorBody {{
    background: {bg2};
}}
QWidget#monitorSummary {{
    background: {bg3};
    border: 1px solid {border};
    border-radius: 8px;
    min-width: 150px;
}}
QLabel#metricTitle {{
    color: {fg_dim};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}}
QLabel#metricValue {{
    color: {fg};
    font-size: 12px;
    font-weight: 700;
}}
QLabel#monitorStatus {{
    color: {fg_dim};
    font-size: 11.5px;
}}
QProgressBar#metricBar {{
    background: {panel};
    border: none;
    border-radius: 4px;
    min-height: 0;
}}
QProgressBar#metricBar::chunk {{
    background: {accent};
    border-radius: 3px;
}}

/* Status-bar session summary (MobaXterm-style) */
QLabel#statusSession {{
    color: {fg_dim};
    font-size: 12px;
}}
"""

def apply_theme(app: QApplication, theme: str = "dark") -> None:
    global _current_theme
    _current_theme = theme if theme in PALETTE else "dark"
    pal = palette(theme)
    app.setStyleSheet(_QSS.format(**pal))
    from PySide6.QtGui import QPalette

    qpal = QPalette()
    qpal.setColor(QPalette.ColorRole.Window, QColor(pal["bg"]))
    qpal.setColor(QPalette.ColorRole.Base, QColor(pal["bg2"]))
    qpal.setColor(QPalette.ColorRole.AlternateBase, QColor(pal["bg"]))
    qpal.setColor(QPalette.ColorRole.Text, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorRole.WindowText, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorRole.Button, QColor(pal["panel"]))
    qpal.setColor(QPalette.ColorRole.ButtonText, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorRole.Highlight, QColor(pal["accent"]))
    qpal.setColor(QPalette.ColorRole.HighlightedText, QColor(pal["accent_text"]))
    qpal.setColor(QPalette.ColorRole.ToolTipBase, QColor(pal["panel"]))
    qpal.setColor(QPalette.ColorRole.ToolTipText, QColor(pal["fg"]))
    qpal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(pal["fg_muted"]))
    qpal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(pal["fg_muted"]))
    app.setPalette(qpal)
