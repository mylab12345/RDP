"""Look & feel: Beautiful natural global theme — 2026 modern design.

Design philosophy:
- Natural harmony: colors drawn from forests, oceans, meadows, deserts
- Bento-inspired: rounded cards (14px), generous whitespace, soft layers
- Tactile depth: subtle shadows via borders, layered panels, hover lifts
- Typography: clean sans (Nimbus Sans / Inter / Segoe UI) + mono for code
- Dark-first but light is equally polished
- Every component feels organic, warm, and calm

No bundled fonts or extra resources — only system fonts and SVG icons.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QApplication

RESOURCES = Path(__file__).parent.parent / "resources"
ICONS = RESOURCES / "icons"

# ----------------------------------------------------------------------
# Palettes — natural, harmonious, carefully tuned for contrast & warmth
# Each palette is a complete design system with bg, surfaces, text, accents
# ----------------------------------------------------------------------
PALETTE = {
    # Midnight — refined dark, not purple, natural slate with mint accent
    "dark": {
        "bg": "#0e1016",
        "bg2": "#171b26",
        "bg3": "#1f2433",
        "panel": "#141821",
        "panel2": "#1c2130",
        "panel3": "#272d42",
        "border": "#212636",
        "border_strong": "#2d344b",
        "border_subtle": "#1a1f2e",
        "fg": "#e8eaf0",
        "fg_dim": "#9aa3b8",
        "fg_muted": "#636c82",
        "accent": "#6ee7b7",
        "accent_hover": "#86efc5",
        "accent_active": "#34d399",
        "accent_text": "#052e1a",
        "accent_subtle": "#6ee7b722",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6ee7b7, stop:1 #34d399)",
        "good": "#6ee7b7",
        "warn": "#fcd34d",
        "bad": "#fb7185",
        "info": "#7dd3fc",
        "term_bg": "#0a0e14",
        "term_fg": "#cbd5e1",
        "sel": "#1e3a4a",
        "sel_hover": "#243d52",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#0e1016cc",
        "card_shadow": "#00000033",
    },
    # Daylight — warm natural light, paper & forest
    "light": {
        "bg": "#fafaf8",
        "bg2": "#ffffff",
        "bg3": "#f2f0eb",
        "panel": "#f7f5f0",
        "panel2": "#ede9e2",
        "panel3": "#e2ddd4",
        "border": "#e8e2d6",
        "border_strong": "#d5cec0",
        "border_subtle": "#f0ebe2",
        "fg": "#1e1f24",
        "fg_dim": "#6b7280",
        "fg_muted": "#9ca3af",
        "accent": "#2d6a4f",
        "accent_hover": "#3a8a66",
        "accent_active": "#1e4a36",
        "accent_text": "#ffffff",
        "accent_subtle": "#2d6a4f12",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2d6a4f, stop:1 #40916c)",
        "good": "#2d6a4f",
        "warn": "#d97706",
        "bad": "#dc2626",
        "info": "#0e7490",
        "term_bg": "#ffffff",
        "term_fg": "#1e1f24",
        "sel": "#d1fae5",
        "sel_hover": "#a7f3d0",
        "shadow": "#1e1f2412",
        "shadow_soft": "#1e1f2408",
        "overlay": "#fafaf8e6",
        "card_shadow": "#1e1f240d",
    },
    # Forest — deep pine & moss, vibrant leaf green
    "forest": {
        "bg": "#080f0c",
        "bg2": "#111d17",
        "bg3": "#1a2d22",
        "panel": "#0f1e16",
        "panel2": "#1a2e22",
        "panel3": "#23402e",
        "border": "#1b3326",
        "border_strong": "#284a36",
        "border_subtle": "#14261c",
        "fg": "#d8e8dc",
        "fg_dim": "#8bb89a",
        "fg_muted": "#5e7e68",
        "accent": "#4ade80",
        "accent_hover": "#6ee7a5",
        "accent_active": "#22c55e",
        "accent_text": "#052e16",
        "accent_subtle": "#4ade8018",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4ade80, stop:1 #22c55e)",
        "good": "#4ade80",
        "warn": "#fbbf24",
        "bad": "#f87171",
        "info": "#6ee7b7",
        "term_bg": "#050a07",
        "term_fg": "#d8e8dc",
        "sel": "#1a3d26",
        "sel_hover": "#1e4a2e",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#080f0ccc",
        "card_shadow": "#00000044",
    },
    # Ocean — deep Atlantic, teal & cyan
    "ocean": {
        "bg": "#060e18",
        "bg2": "#0c1d2c",
        "bg3": "#122a3d",
        "panel": "#0c1f2e",
        "panel2": "#132d42",
        "panel3": "#1b3d56",
        "border": "#173148",
        "border_strong": "#224865",
        "border_subtle": "#0e2536",
        "fg": "#cfe8f4",
        "fg_dim": "#7fb8d0",
        "fg_muted": "#5a8294",
        "accent": "#22d3ee",
        "accent_hover": "#67e8f9",
        "accent_active": "#06b6d4",
        "accent_text": "#042e3a",
        "accent_subtle": "#22d3ee18",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22d3ee, stop:1 #06b6d4)",
        "good": "#34d399",
        "warn": "#fbbf24",
        "bad": "#fb7185",
        "info": "#38bdf8",
        "term_bg": "#040d14",
        "term_fg": "#cfe8f4",
        "sel": "#0e2f45",
        "sel_hover": "#123a56",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#060e18cc",
        "card_shadow": "#00000044",
    },
    # Sunset — warm terracotta dusk, coral & amber
    "sunset": {
        "bg": "#160f0d",
        "bg2": "#231a16",
        "bg3": "#33251f",
        "panel": "#251c18",
        "panel2": "#362a24",
        "panel3": "#4a372f",
        "border": "#3a2c26",
        "border_strong": "#54403a",
        "border_subtle": "#2a201c",
        "fg": "#f5e6d8",
        "fg_dim": "#c9a88e",
        "fg_muted": "#8c7060",
        "accent": "#fb923c",
        "accent_hover": "#fdba74",
        "accent_active": "#ea580c",
        "accent_text": "#1f1208",
        "accent_subtle": "#fb923c18",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #fb923c, stop:1 #f97316)",
        "good": "#a3e635",
        "warn": "#fbbf24",
        "bad": "#f87171",
        "info": "#fcd34d",
        "term_bg": "#0e0a08",
        "term_fg": "#f5e6d8",
        "sel": "#3d2a22",
        "sel_hover": "#4a332a",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#160f0dcc",
        "card_shadow": "#00000044",
    },
    # Aurora — northern lights, mint & lavender on deep teal
    "aurora": {
        "bg": "#080f18",
        "bg2": "#101e2a",
        "bg3": "#182c3c",
        "panel": "#122230",
        "panel2": "#1a3244",
        "panel3": "#224258",
        "border": "#1c3446",
        "border_strong": "#284a62",
        "border_subtle": "#142836",
        "fg": "#d2e8e4",
        "fg_dim": "#8ab8b0",
        "fg_muted": "#5e8a84",
        "accent": "#5eead4",
        "accent_hover": "#7ef0de",
        "accent_active": "#2dd4bf",
        "accent_text": "#042f2e",
        "accent_subtle": "#5eead418",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5eead4, stop:1 #a5b4fc)",
        "good": "#5eead4",
        "warn": "#fde68a",
        "bad": "#fda4af",
        "info": "#a5b4fc",
        "term_bg": "#050e14",
        "term_fg": "#d2e8e4",
        "sel": "#14303c",
        "sel_hover": "#1a3d4e",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#080f18cc",
        "card_shadow": "#00000044",
    },
    # Meadow — sage & cream, light & airy natural
    "meadow": {
        "bg": "#f8faf6",
        "bg2": "#ffffff",
        "bg3": "#eef4e8",
        "panel": "#f2f6ed",
        "panel2": "#e6ecd8",
        "panel3": "#d6dfc2",
        "border": "#dde8d2",
        "border_strong": "#b8c9a8",
        "border_subtle": "#eef4e8",
        "fg": "#1c2a18",
        "fg_dim": "#5a6e52",
        "fg_muted": "#8a9c82",
        "accent": "#4a7c59",
        "accent_hover": "#5c946c",
        "accent_active": "#3a6346",
        "accent_text": "#ffffff",
        "accent_subtle": "#4a7c5914",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4a7c59, stop:1 #6b9e7a)",
        "good": "#4a7c59",
        "warn": "#a16207",
        "bad": "#b91c1c",
        "info": "#0e7490",
        "term_bg": "#ffffff",
        "term_fg": "#1c2a18",
        "sel": "#d9e8c8",
        "sel_hover": "#c5d8b0",
        "shadow": "#1c2a1810",
        "shadow_soft": "#1c2a1808",
        "overlay": "#f8faf6e6",
        "card_shadow": "#1c2a180c",
    },
    # Desert — warm sand & clay, sun-baked natural
    "desert": {
        "bg": "#fdf8f0",
        "bg2": "#ffffff",
        "bg3": "#f5ead4",
        "panel": "#faf3e6",
        "panel2": "#efe2c6",
        "panel3": "#e6d4ac",
        "border": "#eadec4",
        "border_strong": "#d4c2a0",
        "border_subtle": "#f5eee0",
        "fg": "#2c2418",
        "fg_dim": "#7a6a54",
        "fg_muted": "#a89880",
        "accent": "#c27a3a",
        "accent_hover": "#d48e4e",
        "accent_active": "#a8662e",
        "accent_text": "#ffffff",
        "accent_subtle": "#c27a3a14",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #c27a3a, stop:1 #d48e4e)",
        "good": "#5a7c4a",
        "warn": "#b45309",
        "bad": "#dc2626",
        "info": "#78716c",
        "term_bg": "#ffffff",
        "term_fg": "#2c2418",
        "sel": "#f0d8b0",
        "sel_hover": "#e8c8a0",
        "shadow": "#2c241810",
        "shadow_soft": "#2c241808",
        "overlay": "#fdf8f0e6",
        "card_shadow": "#2c24180c",
    },
    # Graphite — neutral professional, blue accent on warm gray
    "graphite": {
        "bg": "#1a1c22",
        "bg2": "#22252d",
        "bg3": "#2c2f38",
        "panel": "#1e2128",
        "panel2": "#262930",
        "panel3": "#32353e",
        "border": "#2e313a",
        "border_strong": "#3d4150",
        "border_subtle": "#252830",
        "fg": "#e4e6ec",
        "fg_dim": "#9ca0b0",
        "fg_muted": "#6b6f80",
        "accent": "#6c9cfc",
        "accent_hover": "#8db8ff",
        "accent_active": "#4a80f0",
        "accent_text": "#0c1a3a",
        "accent_subtle": "#6c9cfc18",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6c9cfc, stop:1 #4a80f0)",
        "good": "#73d9a8",
        "warn": "#f0c050",
        "bad": "#e87070",
        "info": "#70b8e0",
        "term_bg": "#15171c",
        "term_fg": "#d4d8e0",
        "sel": "#2a3a55",
        "sel_hover": "#324460",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#1a1c22cc",
        "card_shadow": "#00000033",
    },
    # Nord — arctic cold palette (https://www.nordtheme.com)
    "nord": {
        "bg": "#2e3440",
        "bg2": "#3b4252",
        "bg3": "#434c5e",
        "panel": "#323844",
        "panel2": "#3b4252",
        "panel3": "#4c566a",
        "border": "#434c5e",
        "border_strong": "#4c566a",
        "border_subtle": "#3b4252",
        "fg": "#eceff4",
        "fg_dim": "#a0aabe",
        "fg_muted": "#6b7a90",
        "accent": "#88c0d0",
        "accent_hover": "#9fd8e8",
        "accent_active": "#5fb8cc",
        "accent_text": "#2e3440",
        "accent_subtle": "#88c0d018",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #88c0d0, stop:1 #5fb8cc)",
        "good": "#a3be8c",
        "warn": "#ebcb8b",
        "bad": "#bf616a",
        "info": "#81a1c1",
        "term_bg": "#2e3440",
        "term_fg": "#d8dee9",
        "sel": "#434c5e",
        "sel_hover": "#4c566a",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#2e3440cc",
        "card_shadow": "#00000044",
    },
    # Dracula — purple night, pink & cyan on dark violet
    "dracula": {
        "bg": "#1e1f29",
        "bg2": "#282a36",
        "bg3": "#343746",
        "panel": "#21222c",
        "panel2": "#282a36",
        "panel3": "#383a4e",
        "border": "#343746",
        "border_strong": "#44475a",
        "border_subtle": "#2c2e3c",
        "fg": "#f8f8f2",
        "fg_dim": "#b0b8c8",
        "fg_muted": "#6272a4",
        "accent": "#bd93f9",
        "accent_hover": "#caa8ff",
        "accent_active": "#a67ce8",
        "accent_text": "#1e1f29",
        "accent_subtle": "#bd93f918",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #bd93f9, stop:1 #ff79c6)",
        "good": "#50fa7b",
        "warn": "#f1fa8c",
        "bad": "#ff5555",
        "info": "#8be9fd",
        "term_bg": "#1e1f29",
        "term_fg": "#f8f8f2",
        "sel": "#383a4e",
        "sel_hover": "#44475a",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#1e1f29cc",
        "card_shadow": "#00000044",
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


# Typography — modern 2026 system stack, no bundled fonts
_UI_SANS = (
    '"Inter", "Geist", "Nimbus Sans L", "Liberation Sans", "DejaVu Sans", '
    '"FreeSans", "Segoe UI", "Helvetica Neue", "Arial", sans-serif'
)
_UI_MONO = (
    '"JetBrains Mono", "Geist Mono", "DejaVu Sans Mono", "Liberation Mono", '
    '"Nimbus Mono L", "FreeMono", "Noto Sans Mono", "Ubuntu Mono", '
    '"Cascadia Code", "Cascadia Mono", "Fira Code", "Consolas", '
    '"Courier New", monospace'
)
_UI_DISPLAY = (
    '"Inter", "Geist", "Nimbus Sans L", "Liberation Sans", "DejaVu Sans", '
    '"Segoe UI", sans-serif'
)

# ----------------------------------------------------------------------
# Beautiful natural global theme QSS — 2026 design language
# Bento cards, soft layers, organic radii, tactile depth
# ----------------------------------------------------------------------
_QSS = """
/* ========== Global foundation ========== */
* {{
    font-family: {ui_sans};
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
    background: {panel2};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 12.5px;
}}

/* ========== Menu bar — clean & minimal ========== */
QMenuBar {{
    background: {panel};
    border-bottom: 1px solid {border_subtle};
    padding: 2px 8px;
    spacing: 2px;
    font-size: 13px;
    min-height: 28px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 8px;
    color: {fg_dim};
    margin: 2px 1px;
}}
QMenuBar::item:selected {{
    background: {bg3};
    color: {fg};
}}
QMenuBar::item:pressed {{
    background: {panel2};
}}

QMenu {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 14px;
    padding: 6px;
}}
QMenu::item {{
    padding: 9px 16px 9px 32px;
    border-radius: 10px;
    color: {fg};
    font-size: 13px;
    margin: 1px 2px;
}}
QMenu::item:selected {{
    background: {accent_subtle};
    color: {fg};
}}
QMenu::item:selected:active {{
    background: {accent};
    color: {accent_text};
}}
QMenu::separator {{
    height: 1px;
    background: {border_subtle};
    margin: 6px 12px;
}}
QMenu::indicator {{
    left: 10px;
    width: 16px;
    height: 16px;
    border-radius: 5px;
}}
QMenu::indicator:checked {{
    background: {accent};
}}

/* ========== Toolbar — pill buttons, bento style ========== */
QToolBar {{
    background: {panel};
    border: none;
    border-bottom: 1px solid {border_subtle};
    spacing: 4px;
    padding: 6px 10px;
    min-height: 48px;
}}
QToolBar#moxaToolbar {{
    spacing: 6px;
    padding: 6px 12px;
    min-height: 52px;
}}
QToolBar#moxaToolbar QToolButton {{
    padding: 6px 12px;
    min-width: 48px;
    min-height: 36px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 10px;
}}
QToolBar::separator {{
    width: 1px;
    background: {border_subtle};
    margin: 10px 8px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 6px 12px;
    color: {fg_dim};
    font-weight: 600;
    font-size: 12px;
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
    background: {accent};
    color: {accent_text};
    border-color: {accent};
}}

/* ========== Buttons — organic, pill-ish, tactile ========== */
QPushButton {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 11px;
    padding: 8px 18px;
    color: {fg};
    font-weight: 600;
    font-size: 13px;
    min-height: 20px;
}}
QPushButton:hover {{
    background: {bg3};
    border-color: {border_strong};
}}
QPushButton:pressed {{
    background: {panel2};
    border-color: {border_strong};
}}
QPushButton:disabled {{
    color: {fg_muted};
    background: {bg};
    border-color: {border_subtle};
}}
QPushButton#primary {{
    background: {accent};
    color: {accent_text};
    border: 1px solid {accent};
    font-weight: 700;
    border-radius: 11px;
}}
QPushButton#primary:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QPushButton#primary:pressed {{
    background: {accent_active};
    border-color: {accent_active};
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {fg_dim};
    border-radius: 10px;
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
    border-radius: 10px;
}}
QPushButton#subtle:hover {{
    background: {panel2};
    color: {fg};
    border-color: {border_strong};
}}

/* ========== Inputs — soft, rounded, natural focus ========== */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg2};
    border: 1.5px solid {border};
    border-radius: 11px;
    padding: 8px 14px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    color: {fg};
    min-height: 20px;
    font-size: 13px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1.5px solid {accent};
    background: {bg2};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
    border-color: {border_strong};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: {bg};
    color: {fg_muted};
    border-color: {border_subtle};
}}
QLineEdit#search {{
    border-radius: 20px;
    padding: 8px 16px 8px 18px;
    background: {bg3};
    border: 1.5px solid {border_subtle};
    font-size: 13px;
}}
QLineEdit#search:focus {{
    background: {bg2};
    border-color: {accent};
}}
QLineEdit#search:hover {{
    border-color: {border};
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
    border-top: 6px solid {fg_dim};
    margin-right: 12px;
    margin-top: 2px;
}}
QComboBox QAbstractItemView {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 6px;
    selection-background-color: {accent_subtle};
    selection-color: {fg};
    outline: none;
    font-family: {ui_sans};
}}

/* ========== Tabs — pill indicator, bento style ========== */
QTabWidget::pane {{
    border: none;
    background: {bg};
    border-radius: 0px;
}}
QTabBar {{
    background: {panel};
    qproperty-drawBase: 0;
    border-top: 1px solid {border_subtle};
    border-bottom: none;
}}
QTabBar::tab {{
    background: transparent;
    color: {fg_dim};
    padding: 8px 18px;
    border: none;
    border-top: 2.5px solid transparent;
    border-radius: 0px;
    margin-right: 2px;
    font-weight: 600;
    font-size: 12.5px;
    min-width: 90px;
    min-height: 28px;
}}
QTabBar::tab:selected {{
    background: {bg};
    color: {fg};
    border-top: 2.5px solid {accent};
    font-weight: 700;
}}
QTabBar::tab:hover:!selected {{
    background: {bg3};
    color: {fg};
    border-top: 2.5px solid {border};
}}
QTabBar::close-button {{
    image: none;
    subcontrol-position: right;
    width: 18px; height: 18px;
    border-radius: 9px;
    margin-left: 8px;
    background: transparent;
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
    border-color: {border_strong};
}}

/* ========== Trees & Lists — bento cards, rounded selection ========== */
QTreeView, QListView, QTableView {{
    background: transparent;
    alternate-background-color: {bg3};
    border: none;
    border-radius: 12px;
    padding: 4px;
    outline: none;
    font-size: 13px;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 9px 12px;
    border-radius: 10px;
    margin: 2px 2px;
    color: {fg};
    border: 1px solid transparent;
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {bg3};
    border-color: {border_subtle};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {accent};
    color: {accent_text};
    border: 1px solid {accent};
    font-weight: 600;
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent};
    color: {accent_text};
}}
QTreeView::branch {{
    background: transparent;
}}
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    image: none;
    border-image: none;
}}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    image: none;
    border-image: none;
}}
QHeaderView::section {{
    background: {panel};
    border: none;
    border-bottom: 1.5px solid {border};
    border-right: 1px solid {border_subtle};
    padding: 10px 14px;
    font-weight: 700;
    color: {fg_dim};
    font-size: 11.5px;
    letter-spacing: 0.3px;
}}

/* ========== Splitter — subtle, organic ========== */
QSplitter::handle {{
    background: {border_subtle};
    width: 1px;
    height: 1px;
}}
QSplitter::handle:hover {{
    background: {accent};
}}
QSplitter::handle:vertical {{
    height: 1px;
}}

/* ========== Scrollbars — thin, rounded, natural ========== */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px 4px 0px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {panel3};
    border-radius: 5px;
    min-height: 32px;
    margin: 2px;
    border: 1px solid {border_subtle};
}}
QScrollBar::handle:vertical:hover {{
    background: {accent};
    border-color: {accent};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0px 4px 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {panel3};
    min-width: 32px;
    margin: 2px;
    border-radius: 5px;
    border: 1px solid {border_subtle};
}}
QScrollBar::handle:horizontal:hover {{
    background: {accent};
    border-color: {accent};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ========== Status bar — soft, minimal ========== */
QStatusBar {{
    background: {panel};
    border-top: 1px solid {border_subtle};
    color: {fg_dim};
    padding: 3px 14px;
    font-size: 11.5px;
    min-height: 22px;
}}
QStatusBar::item {{
    border: none;
}}

/* ========== Groups — bento card style ========== */
QGroupBox {{
    border: 1.5px solid {border};
    border-radius: 14px;
    margin-top: 18px;
    padding: 18px 16px 16px 16px;
    background: {bg2};
    font-weight: 700;
    font-size: 13px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    top: 4px;
    padding: 3px 12px;
    background: {bg2};
    color: {fg_dim};
    border: 1px solid {border};
    border-radius: 20px;
    font-size: 11.5px;
    font-weight: 700;
    letter-spacing: 0.3px;
}}

/* ========== Progress — rounded, natural ========== */
QProgressBar {{
    background: {bg3};
    border: 1px solid {border_subtle};
    border-radius: 8px;
    text-align: center;
    height: 10px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 7px;
}}

/* ========== Checkboxes & Radios — rounded, tactile ========== */
QCheckBox, QRadioButton {{
    spacing: 10px;
    color: {fg};
    font-size: 13px;
    padding: 3px 0px;
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
    background: {bg3};
}}
QCheckBox::indicator:checked:hover, QRadioButton::indicator:checked:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}

/* ========== Labels — hierarchy, natural ========== */
QLabel#muted {{
    color: {fg_dim};
}}
QLabel#h1 {{
    font-size: 20px;
    font-weight: 800;
    font-family: {ui_display};
    letter-spacing: -0.3px;
    color: {fg};
}}
QLabel#h2 {{
    font-size: 12.5px;
    font-weight: 700;
    color: {fg_dim};
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QLabel#caption {{
    font-size: 11.5px;
    color: {fg_dim};
    letter-spacing: 0.2px;
}}
QFrame#hairline {{
    background: {border_subtle};
    max-height: 1px;
    border: none;
}}

/* ========== Dialogs — bento modal ========== */
QDialog {{
    background: {bg};
    border-radius: 16px;
}}

/* ========== Cards — core bento element ========== */
QWidget#card {{
    background: {bg2};
    border: 1.5px solid {border};
    border-radius: 14px;
}}
QWidget#card_hover:hover {{
    border-color: {border_strong};
    background: {bg2};
}}
QWidget#header {{
    background: {panel};
    border-bottom: 1px solid {border_subtle};
    border-radius: 0px;
}}
QWidget#sidebar {{
    background: {panel};
    border-right: 1px solid {border_subtle};
}}

/* ========== Command bar — soft pill input ========== */
QWidget#commandBar {{
    background: {panel};
    border-top: 1px solid {border_subtle};
    padding: 2px 0px;
}}
QLabel#commandPrompt {{
    color: {accent};
    font-size: 14px;
    font-weight: 700;
    padding-left: 4px;
}}
QLineEdit#commandLine {{
    background: {bg2};
    border: 1.5px solid {border};
    border-radius: 20px;
    padding: 7px 14px;
    font-size: 13px;
    min-height: 16px;
}}
QLineEdit#commandLine:focus {{
    border-color: {accent};
    background: {bg2};
}}
QLineEdit#commandLine:hover {{
    border-color: {border_strong};
}}

/* ========== Monitor panel — bento metrics ========== */
QWidget#monitorPanel {{
    background: {bg2};
    border-top: 1px solid {border_subtle};
    border-radius: 0px;
}}
QWidget#monitorHeader {{
    background: {panel};
    border-bottom: 1px solid {border_subtle};
    min-height: 30px;
}}
QWidget#monitorBody {{
    background: {bg2};
}}
QWidget#monitorSummary {{
    background: {panel};
    border: 1.5px solid {border};
    border-radius: 12px;
    min-width: 160px;
}}
QWidget#metricCell {{
    background: {bg2};
    border: 1px solid {border_subtle};
    border-radius: 12px;
}}
QLabel#metricTitle {{
    color: {fg_dim};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}}
QLabel#metricValue {{
    color: {fg};
    font-size: 13px;
    font-weight: 700;
}}
QLabel#monitorStatus {{
    color: {fg_dim};
    font-size: 11.5px;
    background: {bg3};
    border-radius: 20px;
    padding: 2px 10px;
    border: 1px solid {border_subtle};
}}
QProgressBar#metricBar {{
    background: {bg3};
    border: 1px solid {border_subtle};
    border-radius: 6px;
    min-height: 6px;
    max-height: 6px;
}}
QProgressBar#metricBar::chunk {{
    background: {accent};
    border-radius: 5px;
}}

/* ========== Status session — subtle pill ========== */
QLabel#statusSession {{
    color: {fg_dim};
    font-size: 11.5px;
    background: {bg3};
    border-radius: 20px;
    padding: 2px 10px;
    border: 1px solid {border_subtle};
}}

/* ========== Scroll area — clean ========== */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

/* ========== Tab widget corner — rounded ========== */
QTabWidget::tab-bar {{
    alignment: left;
}}

/* ========== SpinBox buttons — rounded ========== */
QSpinBox::up-button, QSpinBox::down-button {{
    background: {bg3};
    border: 1px solid {border_subtle};
    border-radius: 6px;
    width: 20px;
    margin: 2px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {panel2};
    border-color: {border};
}}
QSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {fg_dim};
    width: 0; height: 0;
}}
QSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {fg_dim};
    width: 0; height: 0;
}}
"""


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    global _current_theme
    _current_theme = theme if theme in PALETTE else "dark"
    pal = palette(theme)
    app.setStyleSheet(
        _QSS.format(
            **pal,
            ui_sans=_UI_SANS,
            ui_mono=_UI_MONO,
            ui_display=_UI_DISPLAY,
        )
    )
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
