"""Look & feel: NASA mission-control QSS, palette, icon loading.

Flight-ops chrome: deep-space panels, NASA red / NASA blue accents,
telemetry typography. Uses only system fonts and existing icons —
no bundled extra resources.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication

RESOURCES = Path(__file__).parent.parent / "resources"
ICONS = RESOURCES / "icons"

# NASA identity + mission-control neutrals (public NASA color usage).
NASA_RED = "#FC3D21"
NASA_BLUE = "#0B3D91"
NASA_BLUE_BRIGHT = "#1C67E3"

# ----------------------------------------------------------------------
# Palettes — mission-control / flight-day, plus nature variants
# ----------------------------------------------------------------------
PALETTE = {
    "dark": {
        "bg": "#05070c",
        "bg2": "#0a1018",
        "bg3": "#121a28",
        "panel": "#0d1522",
        "panel2": "#162033",
        "panel3": "#1c2a44",
        "border": "#1c2a44",
        "border_strong": "#2a3d62",
        "fg": "#e8eef6",
        "fg_dim": "#8b97ab",
        "fg_muted": "#5a6678",
        "accent": NASA_RED,
        "accent_hover": "#ff5a3c",
        "accent_active": "#d42e16",
        "accent_text": "#ffffff",
        "accent_subtle": "#FC3D2118",
        "good": "#3ecf8e",
        "warn": "#f0b429",
        "bad": NASA_RED,
        "info": "#4db8e8",
        "term_bg": "#000000",
        "term_fg": "#c8d0dc",
        "sel": "#1a3058",
        "shadow": "#00000088",
        "overlay": "#05070c99",
    },
    "light": {
        "bg": "#eef1f5",
        "bg2": "#ffffff",
        "bg3": "#e4e9f0",
        "panel": "#f7f8fb",
        "panel2": "#dce3ee",
        "panel3": "#c9d4e4",
        "border": "#c5cdd8",
        "border_strong": "#0B3D91",
        "fg": "#121820",
        "fg_dim": "#4a5564",
        "fg_muted": "#6b7686",
        "accent": NASA_BLUE,
        "accent_hover": NASA_BLUE_BRIGHT,
        "accent_active": "#082c6b",
        "accent_text": "#ffffff",
        "accent_subtle": "#0B3D9114",
        "good": "#2E8540",
        "warn": "#b8860b",
        "bad": "#E31C3D",
        "info": NASA_BLUE_BRIGHT,
        "term_bg": "#ffffff",
        "term_fg": "#121820",
        "sel": "#c5d4f0",
        "shadow": "#0B3D9114",
        "overlay": "#eef1f599",
    },
    "forest": {
        "bg": "#07100c",
        "bg2": "#0c1812",
        "bg3": "#13241a",
        "panel": "#102018",
        "panel2": "#183028",
        "panel3": "#204038",
        "border": "#1c3830",
        "border_strong": "#2c5848",
        "fg": "#e2eee4",
        "fg_dim": "#8aa890",
        "fg_muted": "#5e7464",
        "accent": "#6fbf78",
        "accent_hover": "#86d08e",
        "accent_active": "#5aa863",
        "accent_text": "#07100c",
        "accent_subtle": "#6fbf7818",
        "good": "#8fd4a0",
        "warn": "#d4b06a",
        "bad": NASA_RED,
        "info": "#7eb8a0",
        "term_bg": "#000000",
        "term_fg": "#d5e4d4",
        "sel": "#2a4a34",
        "shadow": "#00000066",
        "overlay": "#07100c99",
    },
    "ocean": {
        "bg": "#050e16",
        "bg2": "#0a1822",
        "bg3": "#102430",
        "panel": "#102838",
        "panel2": "#183848",
        "panel3": "#204858",
        "border": "#1c3848",
        "border_strong": "#2c5468",
        "fg": "#dceef4",
        "fg_dim": "#7aa4b4",
        "fg_muted": "#4e7484",
        "accent": "#3db8c4",
        "accent_hover": "#58c8d2",
        "accent_active": "#2a9eaa",
        "accent_text": "#050e16",
        "accent_subtle": "#3db8c418",
        "good": "#5ed0b0",
        "warn": "#e0b46a",
        "bad": NASA_RED,
        "info": "#6ec8e8",
        "term_bg": "#000000",
        "term_fg": "#d0e8ee",
        "sel": "#1a4050",
        "shadow": "#00000066",
        "overlay": "#050e1699",
    },
    "sunset": {
        "bg": "#120c10",
        "bg2": "#1c1418",
        "bg3": "#261c20",
        "panel": "#2a1c22",
        "panel2": "#382428",
        "panel3": "#463030",
        "border": "#3c2830",
        "border_strong": "#5a3840",
        "fg": "#f4e6dc",
        "fg_dim": "#b89890",
        "fg_muted": "#806868",
        "accent": NASA_RED,
        "accent_hover": "#ff6a40",
        "accent_active": "#d42e16",
        "accent_text": "#ffffff",
        "accent_subtle": "#FC3D2118",
        "good": "#c4b06a",
        "warn": "#f0a050",
        "bad": NASA_RED,
        "info": "#d4a0c0",
        "term_bg": "#000000",
        "term_fg": "#f0ddd0",
        "sel": "#4a2830",
        "shadow": "#00000066",
        "overlay": "#120c1099",
    },
    "aurora": {
        "bg": "#060e14",
        "bg2": "#0c181e",
        "bg3": "#12242c",
        "panel": "#162830",
        "panel2": "#1e3440",
        "panel3": "#264050",
        "border": "#243848",
        "border_strong": "#345060",
        "fg": "#e4f4f0",
        "fg_dim": "#88b0b0",
        "fg_muted": "#5a787c",
        "accent": "#5ee0b8",
        "accent_hover": "#78ecd0",
        "accent_active": "#42c8a0",
        "accent_text": "#060e14",
        "accent_subtle": "#5ee0b818",
        "good": "#6ee0c0",
        "warn": "#c8e080",
        "bad": NASA_RED,
        "info": "#80b0e8",
        "term_bg": "#000000",
        "term_fg": "#d8ece8",
        "sel": "#1c4050",
        "shadow": "#00000066",
        "overlay": "#060e1499",
    },
    "meadow": {
        "bg": "#eef2e8",
        "bg2": "#f8faf4",
        "bg3": "#e2ead8",
        "panel": "#e6ecd8",
        "panel2": "#d4dec4",
        "panel3": "#c4d4b0",
        "border": "#c8d4b8",
        "border_strong": "#4a8c4e",
        "fg": "#1a2218",
        "fg_dim": "#5e6e54",
        "fg_muted": "#88987c",
        "accent": "#2E8540",
        "accent_hover": "#3a9a4e",
        "accent_active": "#246834",
        "accent_text": "#ffffff",
        "accent_subtle": "#2E854018",
        "good": "#2d8a4e",
        "warn": "#b07a10",
        "bad": "#c04038",
        "info": "#2a7a88",
        "term_bg": "#f8faf4",
        "term_fg": "#1a2218",
        "sel": "#c8dcb0",
        "shadow": "#1a221814",
        "overlay": "#eef2e899",
    },
    "desert": {
        "bg": "#f0e8dc",
        "bg2": "#f8f2e8",
        "bg3": "#e8dcc8",
        "panel": "#ece0cc",
        "panel2": "#dcccb4",
        "panel3": "#d0bc9c",
        "border": "#d4c4ac",
        "border_strong": "#c4783a",
        "fg": "#241c14",
        "fg_dim": "#7a6854",
        "fg_muted": "#a09078",
        "accent": "#c4783a",
        "accent_hover": "#d48a4c",
        "accent_active": "#b06830",
        "accent_text": "#ffffff",
        "accent_subtle": "#c4783a18",
        "good": "#5a8a48",
        "warn": "#c48820",
        "bad": NASA_RED,
        "info": "#3a7a88",
        "term_bg": "#f8f2e8",
        "term_fg": "#241c14",
        "sel": "#e8c8a0",
        "shadow": "#241c1414",
        "overlay": "#f0e8dc99",
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
    "logo": "◈",
}


def icon(name: str) -> QIcon:
    """Load a PNG or SVG icon; falls back to a drawn text glyph when unavailable."""
    cached = _icon_cache.get(name)
    if cached is not None:
        return cached
    ic = QIcon()
    for ext in (".png", ".svg"):
        path = ICONS / f"{name}{ext}"
        if path.exists():
            ic = QIcon(str(path))
            if not ic.isNull():
                break
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
    font.setFamily("DejaVu Sans Mono")
    font.setPointSize(13)
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


# Multiple system font families — no bundled font files.
_UI_SANS = (
    '"Nimbus Sans L", "Liberation Sans", "DejaVu Sans", "FreeSans", '
    '"Segoe UI", "Helvetica Neue", "Arial", sans-serif'
)
_UI_MONO = (
    '"DejaVu Sans Mono", "Liberation Mono", "Nimbus Mono L", "FreeMono", '
    '"Noto Sans Mono", "Ubuntu Mono", "Cascadia Mono", "Consolas", '
    '"Courier New", monospace'
)

# ----------------------------------------------------------------------
# NASA / MCC QSS — tight radii, telemetry type, identity accents
# ----------------------------------------------------------------------
_QSS = """
/* Global — flight-ops type stack */
* {{
    font-family: {ui_sans};
    outline: none;
}}
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {fg};
    font-size: 13px;
}}
QToolTip {{
    background: {panel};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 5px 8px;
    font-family: {ui_mono};
    font-size: 11.5px;
}}

/* Menu bar — mission header */
QMenuBar {{
    background: {bg};
    border-bottom: 1px solid {border};
    padding: 0 6px;
    spacing: 0px;
    font-family: {ui_mono};
    font-size: 11.5px;
    letter-spacing: 0.8px;
}}
QMenuBar::item {{
    padding: 7px 12px;
    border-radius: 0px;
    color: {fg_dim};
}}
QMenuBar::item:selected {{
    background: {bg3};
    color: {fg};
    border-bottom: 2px solid {accent};
}}

QMenu {{
    background: {panel};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 4px;
}}
QMenu::item {{
    padding: 7px 14px 7px 26px;
    border-radius: 2px;
    color: {fg};
    font-size: 12.5px;
}}
QMenu::item:selected {{
    background: {panel2};
    color: {fg};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 4px 8px;
}}
QMenu::indicator {{
    left: 8px;
    width: 12px;
    height: 12px;
}}

QToolBar {{
    background: {bg};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 1px;
    padding: 3px 8px;
    min-height: 36px;
}}
QToolBar#moxaToolbar {{
    spacing: 1px;
    padding: 2px 8px;
    min-height: 36px;
}}
QToolBar#moxaToolbar QToolButton {{
    padding: 5px;
    min-width: 24px;
    min-height: 22px;
}}
QToolBar::separator {{
    width: 1px;
    background: {border};
    margin: 6px 8px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 6px 10px;
    color: {fg_dim};
    font-weight: 600;
    font-family: {ui_mono};
    font-size: 11px;
    letter-spacing: 0.4px;
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
    border-color: {accent};
}}

QPushButton {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 2px;
    padding: 7px 14px;
    color: {fg};
    font-weight: 600;
    font-family: {ui_mono};
    font-size: 11.5px;
    letter-spacing: 0.5px;
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
    border: 1px solid {accent};
    font-weight: 700;
}}
QPushButton#primary:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
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

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 2px;
    padding: 6px 10px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    color: {fg};
    min-height: 16px;
    font-family: {ui_mono};
    font-size: 12.5px;
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
    border-radius: 2px;
    padding-left: 12px;
    background: {bg3};
    border-color: {border};
}}
QLineEdit#search:focus {{
    background: {bg2};
    border-color: {accent};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
    border-top-right-radius: 2px;
    border-bottom-right-radius: 2px;
}}
QComboBox::down-arrow {{
    image: none;
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {fg_dim};
    margin-right: 8px;
    margin-top: 2px;
}}
QComboBox QAbstractItemView {{
    background: {panel};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 4px;
    selection-background-color: {panel2};
    outline: none;
    font-family: {ui_mono};
}}

QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 2px;
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
    padding: 6px 12px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 1px;
    font-weight: 600;
    font-family: {ui_mono};
    font-size: 11.5px;
    letter-spacing: 0.4px;
    min-width: 56px;
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
    width: 14px; height: 14px;
    border-radius: 2px;
    margin-left: 6px;
}}
QTabBar::close-button:hover {{
    background: {panel2};
}}
QTabBar QToolButton {{
    background: {bg3};
    border: 1px solid {border};
    border-radius: 2px;
    padding: 3px;
}}
QTabBar QToolButton:hover {{
    background: {panel2};
}}

QTreeView, QListView, QTableView {{
    background: {bg2};
    alternate-background-color: {bg};
    border: 1px solid {border};
    border-radius: 2px;
    padding: 2px;
    outline: none;
    font-family: {ui_mono};
    font-size: 12.5px;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 6px 8px;
    border-radius: 0px;
    margin: 0px;
    color: {fg};
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {bg3};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {panel2};
    color: {fg};
    border: none;
    border-left: 2px solid {accent};
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent_subtle};
}}
QTreeView::branch {{
    background: transparent;
}}
QHeaderView::section {{
    background: {bg2};
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
    padding: 8px 10px;
    font-weight: 700;
    color: {fg_dim};
    font-size: 10.5px;
    font-family: {ui_mono};
    text-transform: uppercase;
    letter-spacing: 1px;
}}

QSplitter::handle {{
    background: {border};
    width: 1px;
    height: 1px;
}}
QSplitter::handle:hover {{
    background: {accent};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px 2px 2px 0px;
    border-radius: 0px;
}}
QScrollBar::handle:vertical {{
    background: {panel2};
    border-radius: 0px;
    min-height: 28px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {panel3};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0px 2px 2px 2px;
}}
QScrollBar::handle:horizontal {{
    background: {panel2};
    min-width: 28px;
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

QStatusBar {{
    background: {bg2};
    border-top: 1px solid {border};
    color: {fg_dim};
    padding: 1px 10px;
    font-family: {ui_mono};
    font-size: 11px;
    letter-spacing: 0.4px;
}}
QStatusBar::item {{
    border: none;
}}

QGroupBox {{
    border: 1px solid {border};
    border-radius: 2px;
    margin-top: 14px;
    padding: 14px 10px 10px 10px;
    background: {bg2};
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    top: 2px;
    padding: 1px 8px;
    background: {bg2};
    color: {fg_dim};
    border-radius: 0px;
    font-size: 10.5px;
    font-weight: 700;
    font-family: {ui_mono};
    letter-spacing: 1.2px;
    text-transform: uppercase;
}}

QProgressBar {{
    background: {panel};
    border: 1px solid {border};
    border-radius: 0px;
    text-align: center;
    height: 6px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 0px;
}}

QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {fg};
    font-family: {ui_sans};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px; height: 14px;
    border-radius: 2px;
    border: 1px solid {border_strong};
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
    border-radius: 8px;
}}

QLabel#muted {{
    color: {fg_dim};
}}
QLabel#h1 {{
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 1.6px;
    font-family: {ui_mono};
    text-transform: uppercase;
}}
QLabel#h2 {{
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1.4px;
    font-family: {ui_mono};
    text-transform: uppercase;
    color: {fg_dim};
}}
QLabel#caption {{
    font-size: 11px;
    color: {fg_dim};
    font-family: {ui_mono};
    letter-spacing: 0.6px;
}}
QFrame#hairline {{
    background: {border};
    max-height: 1px;
    border: none;
}}

QDialog {{
    background: {bg};
    border-radius: 2px;
}}

QWidget#card {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 2px;
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

QWidget#commandBar {{
    background: {bg2};
    border-top: 1px solid {border};
}}
QLabel#commandPrompt {{
    color: {accent};
    font-size: 13px;
    font-weight: 700;
    font-family: {ui_mono};
}}
QLineEdit#commandLine {{
    background: {bg3};
    border: 1px solid {border};
    border-radius: 2px;
    padding: 4px 8px;
    font-size: 12px;
    font-family: {ui_mono};
    min-height: 12px;
}}
QLineEdit#commandLine:focus {{
    border-color: {accent};
    background: {bg2};
}}

QWidget#monitorPanel {{
    background: {bg2};
    border-top: 1px solid {border};
}}
QWidget#monitorHeader {{
    background: {bg3};
    border-bottom: 1px solid {border};
    min-height: 24px;
}}
QWidget#monitorBody {{
    background: {bg2};
}}
QWidget#monitorSummary {{
    background: {bg3};
    border: 1px solid {border};
    border-radius: 2px;
    min-width: 150px;
}}
QLabel#metricTitle {{
    color: {fg_dim};
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 1.1px;
    text-transform: uppercase;
    font-family: {ui_mono};
}}
QLabel#metricValue {{
    color: {fg};
    font-size: 12px;
    font-weight: 700;
    font-family: {ui_mono};
}}
QLabel#monitorStatus {{
    color: {fg_dim};
    font-size: 11px;
    font-family: {ui_mono};
    letter-spacing: 0.6px;
}}
QProgressBar#metricBar {{
    background: {panel};
    border: none;
    border-radius: 0px;
    min-height: 0;
}}
QProgressBar#metricBar::chunk {{
    background: {accent};
    border-radius: 0px;
}}

QLabel#statusSession {{
    color: {fg_dim};
    font-size: 11px;
    font-family: {ui_mono};
    letter-spacing: 0.4px;
}}
"""


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    global _current_theme
    _current_theme = theme if theme in PALETTE else "dark"
    pal = palette(theme)
    app.setStyleSheet(_QSS.format(**pal, ui_sans=_UI_SANS, ui_mono=_UI_MONO))
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
