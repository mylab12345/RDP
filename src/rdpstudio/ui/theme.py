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

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

RESOURCES = Path(__file__).parent.parent / "resources"
ICONS = RESOURCES / "icons"

# ----------------------------------------------------------------------
# Palettes — natural, harmonious, carefully tuned for contrast & warmth
# Each palette is a complete design system with bg, surfaces, text, accents
# ----------------------------------------------------------------------
PALETTE = {
    # Dark — restrained neutral slate, one blue accent (default)
    "dark": {
        "bg": "#14161b",
        "bg2": "#1a1d23",
        "bg3": "#22262e",
        "panel": "#17191f",
        "panel2": "#1e222a",
        "panel3": "#282d37",
        "border": "#2a2e37",
        "border_strong": "#3b4150",
        "border_subtle": "#22252d",
        "fg": "#e4e7ec",
        "fg_dim": "#9aa1ad",
        "fg_muted": "#6b7280",
        "accent": "#4c8dff",
        "accent_hover": "#6ba1ff",
        "accent_active": "#3a76e8",
        "accent_text": "#ffffff",
        "accent_subtle": "#4c8dff26",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4c8dff, stop:1 #3a76e8)",
        "good": "#3fb950",
        "warn": "#d29922",
        "bad": "#f85149",
        "info": "#58a6ff",
        "term_bg": "#101216",
        "term_fg": "#d4d8e0",
        "sel": "#243044",
        "sel_hover": "#2a3444",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#14161bcc",
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
        "fg_muted": "#7c8591",  # bumped for WCAG AA on light surfaces
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
        "fg_muted": "#6f8264",  # bumped for WCAG AA on light surfaces
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
        "fg_muted": "#8a7a5c",  # bumped for WCAG AA on light surfaces
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
    # High contrast — pure black & white, WCAG AAA (accessibility preset)
    "contrast": {
        "bg": "#000000",
        "bg2": "#0a0a0a",
        "bg3": "#1a1a1a",
        "panel": "#000000",
        "panel2": "#111111",
        "panel3": "#262626",
        "border": "#4d4d4d",
        "border_strong": "#808080",
        "border_subtle": "#333333",
        "fg": "#ffffff",
        "fg_dim": "#d4d4d4",
        "fg_muted": "#a3a3a3",
        "accent": "#4da3ff",
        "accent_hover": "#74b6ff",
        "accent_active": "#2f87e6",
        "accent_text": "#ffffff",
        "accent_subtle": "#4da3ff33",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4da3ff, stop:1 #2f87e6)",
        "good": "#3fb950",
        "warn": "#d29922",
        "bad": "#f85149",
        "info": "#58a6ff",
        "term_bg": "#000000",
        "term_fg": "#ffffff",
        "sel": "#1f3a5f",
        "sel_hover": "#27476e",
        "shadow": "#000000",
        "shadow_soft": "#00000088",
        "overlay": "#000000e6",
        "card_shadow": "#00000066",
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
    "close": "✕",
    "connect": "↻",
    "search": "⌕",
    "edit": "✎",
    "trash": "🗑",
    "logo": "◈",
}


def icon(name: str, tint: str | None = None) -> QIcon:
    """Load a PNG or SVG icon.

    SVGs are re-rendered in ``tint`` (default: the current theme's icon
    colour, ``fg_dim``) so they stay legible and consistent in every theme.
    Falls back to a drawn text glyph when no icon file can be loaded.
    """
    key = (name, tint or "")
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    ic: QIcon | None = None
    for ext in (".png", ".svg"):
        path = ICONS / f"{name}{ext}"
        if not path.exists():
            continue
        if ext == ".png":
            candidate = QIcon(str(path))
            if not candidate.isNull() and candidate.availableSizes():
                ic = candidate
        else:
            color = tint or palette()["fg_dim"]
            candidate = _tinted_svg(path, color)
            # Vector icons are scalable, so Qt reports no fixed
            # availableSizes() for them. Trust the icon once the engine
            # actually rasterises it — otherwise every button would fall
            # back to a drawn text glyph.
            if not candidate.isNull() and not candidate.pixmap(QSize(16, 16)).isNull():
                ic = candidate
        if ic is not None:
            break

    if ic is None:
        ic = _glyph_icon(GLYPH_FALLBACK.get(name, "•"))
    _icon_cache[key] = ic
    return ic


_HEX_COLOR = re.compile(r'(stroke|fill)="#[0-9a-fA-F]{3,8}"')
_ICON_SIZES = (16, 20, 24, 32, 48, 64)


def _svg_to_icon(svg_text: str) -> QIcon:
    """Render SVG text at a set of sizes into one scalable-friendly QIcon."""
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer

    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    if not renderer.isValid():
        return QIcon()
    ic = QIcon()
    for s in _ICON_SIZES:
        pix = QPixmap(s, s)
        pix.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        if not pix.isNull():
            ic.addPixmap(pix)
    return ic


def _tinted_svg(path: Path, color: str) -> QIcon:
    """Load an SVG with every hardcoded colour recoloured to ``color``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return QIcon()
    # fill="none" survives — the pattern only matches hex colours.
    text = _HEX_COLOR.sub(lambda m: f'{m.group(1)}="{color}"', text)
    return _svg_to_icon(text)


def badge_icon(name: str, size: int = 16, tint: str | None = None) -> QIcon:
    """Icon on a rounded surface tile — protocol marks for tabs and rows."""
    pal = palette()
    key = (f"badge:{name}:{size}", tint or "")
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(pal["bg3"]))
    painter.drawRoundedRect(0, 0, size, size, 4, 4)
    inner = icon(name, tint or pal["fg_dim"]).pixmap(
        QSize(int(size * 0.72), int(size * 0.72))
    )
    painter.drawPixmap((size - inner.width()) // 2, (size - inner.height()) // 2, inner)
    painter.end()
    ic = QIcon(pix)
    _icon_cache[key] = ic
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
_density = "comfortable"  # comfortable | compact
MOTIONS_ENABLED = True  # global motion switch (Settings → UI → Animations)


def current_theme() -> str:
    return _current_theme


def current_density() -> str:
    return _density


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
/* ================= KB-Remote global theme =================
   Clean, professional, compact. Neutral dark surfaces, 1px
   borders, 6px radii, single accent. Consistent states. */

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
    background: {panel2};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 4px;
    padding: 5px 8px;
    font-size: 12px;
}}

/* ================= Menu bar ================= */
QMenuBar {{
    background: {panel};
    border-bottom: 1px solid {border_subtle};
    padding: 0px 6px;
    spacing: 0px;
    font-size: 12.5px;
    min-height: 26px;
}}
QMenuBar::item {{
    padding: 4px 10px;
    border-radius: 4px;
    color: {fg_dim};
    margin: 1px 0px;
}}
QMenuBar::item:selected {{
    background: {bg3};
    color: {fg};
}}
QMenuBar::item:pressed {{
    background: {bg3};
    color: {fg};
}}

QMenu {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 14px 6px 30px;
    border-radius: 4px;
    color: {fg};
    font-size: 12.5px;
    margin: 0px 1px;
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
    margin: 5px 8px;
}}
QMenu::indicator {{
    left: 9px;
    width: 14px;
    height: 14px;
    border-radius: 4px;
}}
QMenu::indicator:checked {{
    background: {accent};
}}

/* ================= Toolbar — compact, icon + label ================= */
QToolBar {{
    background: {panel};
    border: none;
    border-bottom: 1px solid {border_subtle};
    spacing: 2px;
    padding: 3px 8px;
    min-height: 38px;
}}
QToolBar#moxaToolbar {{
    spacing: 2px;
    padding: 3px 8px;
    min-height: 38px;
}}
QToolBar#moxaToolbar QToolButton {{
    padding: 4px 9px;
    min-width: 30px;
    min-height: 26px;
    font-size: 12px;
    font-weight: 600;
    border-radius: 5px;
}}
QToolBar::separator {{
    width: 1px;
    background: {border_subtle};
    margin: 8px 5px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 9px;
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
    background: {panel3};
}}
QToolButton:checked {{
    background: {accent_subtle};
    color: {accent};
    border-color: {accent}55;
}}
QToolButton:focus {{
    outline: 1px solid {accent};
    outline-offset: 1px;
}}


/* ================= Buttons ================= */
QPushButton {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 14px;
    color: {fg};
    font-weight: 600;
    font-size: 12.5px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {bg3};
    border-color: {border_strong};
}}
QPushButton:pressed {{
    background: {panel2};
    border-color: {border_strong};
}}
QPushButton:focus {{
    border-color: {accent};
    outline: 1px solid {accent};
    outline-offset: 1px;
}}
QPushButton:disabled {{
    color: {fg_muted};
    background: {bg};
    border-color: {border_subtle};
}}
QPushButton#primary {{
    background: {accent_gradient};
    color: {accent_text};
    border: 1px solid {accent};
    font-weight: 600;
    border-radius: 6px;
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
    border-radius: 6px;
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
    border-radius: 6px;
}}
QPushButton#subtle:hover {{
    background: {panel2};
    color: {fg};
    border-color: {border_strong};
}}

/* Quick connect — joined input + button group */
QWidget#quickConnect {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 6px;
}}
QWidget#quickConnect:hover {{
    border-color: {border_strong};
}}
QWidget#quickConnect QLineEdit {{
    background: transparent;
    border: none;
    padding: 4px 10px;
    font-size: 12.5px;
    color: {fg};
    min-height: 18px;
}}
QWidget#quickConnect QPushButton {{
    border: none;
    border-top-left-radius: 0px;
    border-bottom-left-radius: 0px;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    padding: 4px 12px;
    font-size: 12px;
    min-height: 18px;
}}

/* ================= Inputs ================= */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 10px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    color: {fg};
    min-height: 18px;
    font-size: 12.5px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
    background: {bg2};
    outline: 1px solid {accent};
    outline-offset: 1px;
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
    border-radius: 6px;
    padding: 5px 10px 5px 12px;
    background: {bg2};
    border: 1px solid {border};
    font-size: 12.5px;
}}
QLineEdit#search:focus {{
    background: {bg2};
    border-color: {accent};
}}
QLineEdit#search:hover {{
    border-color: {border_strong};
}}

QComboBox::drop-down {{
    border: none;
    width: 26px;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
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
    background: {bg2};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {accent_subtle};
    selection-color: {fg};
    outline: none;
    font-family: {ui_sans};
}}

/* ================= Tabs — underline indicator ================= */
QTabWidget::pane {{
    border: none;
    background: {bg};
    border-radius: 0px;
}}
QTabBar {{
    background: {panel};
    qproperty-drawBase: 0;
    border-bottom: 1px solid {border_subtle};
    border-top: none;
}}
QTabBar::tab {{
    background: transparent;
    color: {fg_dim};
    padding: 6px 14px;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    margin-right: 1px;
    font-weight: 600;
    font-size: 12px;
    min-height: 24px;
    /* bounded tabs + the built-in overflow menu keep the chrome tidy
       when many sessions are open */
    max-width: 180px;
}}
QTabBar::tab:selected {{
    background: {bg};
    color: {fg};
    border-bottom: 2px solid {accent};
}}
QTabBar::tab:hover:!selected {{
    background: {bg3};
    color: {fg};
}}
QTabBar::close-button {{
    subcontrol-position: right;
    width: 18px; height: 18px;
    border-radius: 4px;
    margin-left: 4px;
    margin-right: 2px;
    background: transparent;
}}
QTabBar::close-button:hover {{
    background: {panel3};
}}
QTabBar::close-button:pressed {{
    background: {bad};
}}
QTabBar QToolButton {{
    background: {bg3};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 2px;
}}
QTabBar QToolButton:hover {{
    background: {panel2};
    border-color: {border_strong};
}}

/* ================= Trees & Lists ================= */
QTreeView, QListView, QTableView {{
    background: transparent;
    alternate-background-color: {bg2};
    border: none;
    border-radius: 6px;
    padding: 2px;
    outline: none;
    font-size: 12.5px;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 4px 8px;
    border-radius: 6px;
    margin: 1px 1px;
    color: {fg};
    border: 1px solid transparent;
}}
QTreeView::item:focus, QListView::item:focus, QTableView::item:focus {{
    outline: 1px solid {accent};
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {bg3};
    border-color: {border_subtle};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {accent_subtle};
    color: {fg};
    border: 1px solid {accent}44;
    font-weight: 600;
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent_subtle};
    color: {fg};
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
    border-bottom: 1px solid {border};
    border-right: 1px solid {border_subtle};
    padding: 6px 10px;
    font-weight: 700;
    color: {fg_dim};
    font-size: 11px;
    letter-spacing: 0.3px;
}}

/* ================= Splitter ================= */
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

/* ================= Scrollbars ================= */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {panel3};
    border-radius: 4px;
    min-height: 28px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {border_strong};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {panel3};
    min-width: 28px;
    margin: 2px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {border_strong};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0; height: 0;
    background: transparent;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ================= Status bar ================= */
QStatusBar {{
    background: {panel};
    border-top: 1px solid {border_subtle};
    color: {fg_dim};
    padding: 2px 10px;
    font-size: 11.5px;
    min-height: 22px;
}}
QStatusBar::item {{
    border: none;
}}

/* ================= Groups ================= */
QGroupBox {{
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 14px;
    padding: 14px 12px 12px 12px;
    background: {bg2};
    font-weight: 700;
    font-size: 12.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    top: 2px;
    padding: 0px 6px;
    background: {bg2};
    color: {fg_dim};
    border: none;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}

/* ================= Progress ================= */
QProgressBar {{
    background: {bg3};
    border: none;
    border-radius: 4px;
    text-align: center;
    height: 8px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {accent};
    border-radius: 4px;
}}

/* ================= Checkboxes & Radios ================= */
QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {fg};
    font-size: 12.5px;
    padding: 2px 0px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
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
QCheckBox::indicator:checked:hover, QRadioButton::indicator:checked:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}

/* ================= Labels ================= */
QLabel#muted {{
    color: {fg_dim};
}}
QLabel#h1 {{
    font-size: 16px;
    font-weight: 700;
    font-family: {ui_display};
    letter-spacing: -0.2px;
    color: {fg};
}}
QLabel#h2 {{
    font-size: 11px;
    font-weight: 700;
    color: {fg_muted};
    letter-spacing: 0.6px;
    text-transform: uppercase;
}}
QLabel#caption {{
    font-size: 11.5px;
    color: {fg_dim};
    letter-spacing: 0.1px;
}}
QFrame#hairline {{
    background: {border_subtle};
    max-height: 1px;
    border: none;
}}

/* ================= Dialogs ================= */
QDialog {{
    background: {bg};
    border-radius: 14px;
}}

/* ================= Surfaces ================= */
QWidget#card {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 8px;
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
QWidget#workArea {{
    background: {bg};
}}

/* ================= Command bar ================= */
QWidget#commandBar {{
    background: {panel};
    border-top: 1px solid {border_subtle};
    padding: 2px 0px;
}}
QLabel#commandPrompt {{
    color: {accent};
    font-size: 13px;
    font-weight: 700;
    padding-left: 4px;
}}
QLineEdit#commandLine {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 12.5px;
    min-height: 16px;
}}
QLineEdit#commandLine:focus {{
    border-color: {accent};
    background: {bg2};
}}
QLineEdit#commandLine:hover {{
    border-color: {border_strong};
}}

/* ================= Status session chip ================= */
QLabel#statusSession {{
    color: {fg_dim};
    /* monospace = tabular figures: the line never jitters as ciphers,
       versions and byte counts tick */
    font-family: {ui_mono};
    font-size: 11px;
    background: {bg3};
    border-radius: 4px;
    padding: 1px 8px;
    border: 1px solid {border_subtle};
}}

/* ================= Scroll area ================= */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}

QTabWidget::tab-bar {{
    alignment: left;
}}

/* ================= SpinBox buttons ================= */
QSpinBox::up-button, QSpinBox::down-button {{
    background: {bg3};
    border: 1px solid {border_subtle};
    border-radius: 4px;
    width: 18px;
    margin: 1px;
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


_QSS_COMPACT = """
/* ================= Compact density (Settings → UI) ================= */
QWidget {{ font-size: 12px; }}
QMenuBar {{ min-height: 22px; font-size: 12px; }}
QMenuBar::item {{ padding: 3px 8px; }}
QMenu::item {{ padding: 4px 14px 4px 28px; }}
QToolBar {{ min-height: 32px; padding: 2px 6px; }}
QToolButton {{ padding: 3px 7px; min-height: 22px; font-size: 11.5px; }}
QPushButton {{ padding: 3px 12px; min-height: 15px; font-size: 12px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    padding: 3px 9px; min-height: 15px; font-size: 12px;
}}
QTabBar::tab {{ padding: 3px 12px; min-height: 18px; }}
QTreeView::item, QListView::item, QTableView::item {{ padding: 2px 8px; }}
QStatusBar {{ min-height: 18px; font-size: 11px; }}
QGroupBox {{ margin-top: 10px; padding: 10px 10px 8px 10px; }}
QCheckBox, QRadioButton {{ font-size: 12px; }}
"""


def apply_theme(
    app: QApplication,
    theme: str = "dark",
    density: str = "comfortable",
    animations: bool = True,
) -> None:
    global _current_theme, _density, MOTIONS_ENABLED
    _current_theme = theme if theme in PALETTE else "dark"
    _density = density if density in ("comfortable", "compact") else "comfortable"
    MOTIONS_ENABLED = bool(animations)
    pal = palette(theme)
    qss = _QSS.format(
        **pal,
        ui_sans=_UI_SANS,
        ui_mono=_UI_MONO,
        ui_display=_UI_DISPLAY,
    )
    if _density == "compact":
        qss += _QSS_COMPACT.format(
            **pal,
            ui_sans=_UI_SANS,
            ui_mono=_UI_MONO,
            ui_display=_UI_DISPLAY,
        )
    app.setStyleSheet(qss)
    # Icon colours follow the theme — drop the cache so widgets built after
    # the switch pick up the new tint.
    _icon_cache.clear()
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
