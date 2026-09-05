"""Look & feel: MobaXterm-style global theme.

Design language (modelled on MobaXterm's classic Windows chrome):
- Light gray window chrome (#f0f0f0) with white work surfaces
- Flat, square-ish controls (2-3 px radii), 1 px #adadad/#d9d9d9 borders
- Windows-blue selection (#0078d7 / #cce8ff) and hover (#e5f3ff)
- Segoe UI / Tahoma 9 pt typography, Consolas for code
- Big text-under-icon toolbar with coloured glyphs, classic document tabs,
  a Sessions side panel with a vertical tab strip

The MobaXterm light look is the default; ``dark`` is the MobaXterm dark
variant. The remaining palettes are kept as optional colour schemes and
share the same MobaXterm geometry.

No bundled fonts or extra resources — only system fonts and SVG icons.
"""

from __future__ import annotations

import os
import re
import tempfile
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
    # MobaXterm — classic light Windows chrome (default)
    "mobaxterm": {
        "bg": "#f0f0f0",
        "bg2": "#ffffff",
        "bg3": "#e5e5e5",
        "panel": "#f5f5f5",
        "panel2": "#e9e9e9",
        "panel3": "#d9d9d9",
        "border": "#d9d9d9",
        "border_strong": "#adadad",
        "border_subtle": "#e3e3e3",
        "fg": "#1e1e1e",
        "fg_dim": "#505050",
        "fg_muted": "#6d6d6d",
        "accent": "#0078d7",
        "accent_hover": "#1a86e0",
        "accent_active": "#005a9e",
        "accent_text": "#ffffff",
        "accent_subtle": "#cce8ff",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b8ee0, stop:1 #0a6fc9)",
        "good": "#2e8b3d",
        "warn": "#d9822b",
        "bad": "#d13438",
        "info": "#0078d7",
        "term_bg": "#000000",
        "term_fg": "#bfbfbf",
        "sel": "#cce8ff",
        "sel_hover": "#e5f3ff",
        "shadow": "#00000033",
        "shadow_soft": "#0000001a",
        "overlay": "#f0f0f0e6",
        "card_shadow": "#00000014",
    },
    # Dark — MobaXterm dark variant: neutral grays, Windows blue
    "dark": {
        "bg": "#2b2b2b",
        "bg2": "#333333",
        "bg3": "#3d3d3d",
        "panel": "#2f2f2f",
        "panel2": "#383838",
        "panel3": "#474747",
        "border": "#454545",
        "border_strong": "#5c5c5c",
        "border_subtle": "#3a3a3a",
        "fg": "#e8e8e8",
        "fg_dim": "#b4b4b4",
        "fg_muted": "#8c8c8c",
        "accent": "#3d8fd6",
        "accent_hover": "#5aa1de",
        "accent_active": "#2a78bd",
        "accent_text": "#ffffff",
        "accent_subtle": "#3d8fd640",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4a99dc, stop:1 #2f7fc6)",
        "good": "#4caf50",
        "warn": "#e0a030",
        "bad": "#e05252",
        "info": "#4aa3e0",
        "term_bg": "#000000",
        "term_fg": "#bfbfbf",
        "sel": "#3a5470",
        "sel_hover": "#3f4a57",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#2b2b2bcc",
        "card_shadow": "#00000044",
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
    painter.setPen(QColor(palette()["fg"]))
    font = painter.font()
    font.setFamily("Consolas")
    font.setPointSize(13)
    font.setWeight(font.Weight.Medium)
    painter.setFont(font)
    painter.drawText(pix.rect(), _Qt.AlignmentFlag.AlignCenter, glyph)
    painter.end()
    return QIcon(pix)


# Theme currently applied to the app (see apply_theme). Widgets that build
# colors at construction time use this so light theme doesn't render dark.
_current_theme = "mobaxterm"
_density = "comfortable"  # comfortable | compact
MOTIONS_ENABLED = True  # global motion switch (Settings → UI → Animations)


def current_theme() -> str:
    return _current_theme


def current_density() -> str:
    return _density


# ----------------------------------------------------------------------
# Theme-change notifications
# ----------------------------------------------------------------------
# Widgets that bake palette colours into inline styles or pre-rendered
# icons (chips, dashboard, tab badges) register a callback here so a live
# theme switch re-tints them instead of showing stale colours.
_theme_changed_callbacks: list = []


def add_theme_changed_callback(cb) -> None:
    """Register ``cb()`` to run after every successful apply_theme()."""
    if cb not in _theme_changed_callbacks:
        _theme_changed_callbacks.append(cb)


def remove_theme_changed_callback(cb) -> None:
    try:
        _theme_changed_callbacks.remove(cb)
    except ValueError:
        pass


def _fire_theme_changed() -> None:
    for cb in list(_theme_changed_callbacks):
        try:
            cb()
        except Exception:  # noqa: BLE001 — one broken view must not kill theming
            from ..core.log import log

            log.exception("theme-change callback failed")


# Per-protocol accent colours (palette keys) so tabs, rows and previews
# read the protocol at a glance: SSH green, RDP blue, local = theme accent.
PROTOCOL_TINTS: dict[str, str] = {"ssh": "good", "rdp": "info", "local": "accent"}


def protocol_tint(protocol: str) -> str:
    """Palette key used to colour-mark ``protocol``."""
    return PROTOCOL_TINTS.get((protocol or "").lower(), "accent")


def protocol_badge(protocol: str, icon_name: str, size: int = 16) -> QIcon:
    """Rounded-tile icon in the protocol's accent colour — for tabs & rows."""
    return badge_icon(icon_name, size, palette()[protocol_tint(protocol)])


def palette(theme: str | None = None) -> dict[str, str]:
    """Palette for ``theme`` — defaults to the currently applied theme."""
    return PALETTE.get(theme or _current_theme, PALETTE["mobaxterm"])


# Typography — MobaXterm uses the Windows UI stack (Segoe UI / Tahoma 9 pt)
# and Consolas for code. Nothing is bundled; the stack degrades gracefully.
_UI_SANS = (
    '"Segoe UI", "Tahoma", "Noto Sans", "DejaVu Sans", "Liberation Sans", '
    '"Nimbus Sans L", "Helvetica Neue", "Arial", sans-serif'
)
_UI_MONO = (
    '"Consolas", "Cascadia Mono", "Lucida Console", "DejaVu Sans Mono", '
    '"Liberation Mono", "Noto Sans Mono", "Courier New", monospace'
)
_UI_DISPLAY = (
    '"Segoe UI Semibold", "Segoe UI", "Tahoma", "Noto Sans", "DejaVu Sans", '
    '"Liberation Sans", "Arial", sans-serif'
)

# MobaXterm's big toolbar uses coloured glyphs — one tint per action so the
# buttons read at a glance (keys are the icon names in resources/icons/).
TOOLBAR_ICON_TINTS: dict[str, str] = {
    "plus": "#2e9e44",       # Session — green
    "console": "#3a3a3a",    # Terminal — charcoal
    "terminal": "#3a3a3a",
    "panel": "#d9822b",      # Sessions panel — orange
    "server": "#2f7fc6",     # Servers / scanner — blue
    "key": "#c9a227",        # Keys — gold
    "transfer": "#7a4fbf",   # Tunneling — purple
    "search": "#0078d7",     # Commands — blue
    "gear": "#6d6d6d",       # Settings — gray
    "shield": "#1e6fd0",     # Help — blue
    "close": "#d13438",      # Close all / Exit — red
    "stop": "#d13438",
    "windows": "#0078d7",
    "folder": "#e8b33c",     # folders — Windows yellow
    "star": "#e8b33c",
    "connect": "#2e9e44",
    "edit": "#505050",
    "trash": "#d13438",
}


def toolbar_icon(name: str) -> QIcon:
    """Coloured MobaXterm-style toolbar glyph (falls back to the theme tint)."""
    tint = TOOLBAR_ICON_TINTS.get(name)
    if tint and not is_dark_theme(None):
        return icon(name, tint)
    if tint:
        # Lift the tint a little on dark chrome so it stays legible.
        return icon(name, _shade(tint, 1.35) if tint != "#3a3a3a" else palette()["fg"])
    return icon(name)

# ----------------------------------------------------------------------
# MobaXterm global theme QSS — flat Windows chrome, classic tabs, blue
# selection, square-ish controls
# ----------------------------------------------------------------------

_CHECK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
    'fill="none"><path d="M3.5 8.5l3 3 6-7" stroke="{color}" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_RADIO_DOT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" '
    'fill="none"><circle cx="8" cy="8" r="3.2" fill="{color}"/></svg>'
)
# Tree expanders and combo/spin arrows — thin Windows-style chevrons.
_CHEVRON_RIGHT_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none">'
    '<path d="M6 4l4 4-4 4" stroke="{color}" stroke-width="1.4" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_CHEVRON_DOWN_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none">'
    '<path d="M4 6l4 4 4-4" stroke="{color}" stroke-width="1.4" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_CHEVRON_UP_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none">'
    '<path d="M4 10l4-4 4 4" stroke="{color}" stroke-width="1.4" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def _indicator_image_urls(pal: dict[str, str]) -> dict[str, str]:
    """Write per-theme check/radio/chevron glyph SVGs into a cache dir.

    QSS cannot tint a loaded raster, but it can point ``image:`` at a file —
    so we regenerate the small glyphs in the theme's colours every time the
    palette changes.
    """
    cache = Path(tempfile.gettempdir()) / f"kb-remote-indicators-{os.getuid()}"
    empty = {
        "check_url": "", "dot_url": "", "chev_right_url": "",
        "chev_down_url": "", "chev_up_url": "", "chev_down_dim_url": "",
    }
    try:
        cache.mkdir(parents=True, exist_ok=True)
        accent_hex = pal["accent"].lstrip("#")
        fg_hex = pal["fg"].lstrip("#")
        dim_hex = pal["fg_dim"].lstrip("#")
        out = {}
        for key, fname, svg, color in (
            ("check_url", f"check-{accent_hex}.svg", _CHECK_SVG, pal["accent_text"]),
            ("dot_url", f"radio-{accent_hex}.svg", _RADIO_DOT_SVG, pal["accent_text"]),
            ("chev_right_url", f"chev-r-{dim_hex}.svg", _CHEVRON_RIGHT_SVG, pal["fg_dim"]),
            ("chev_down_url", f"chev-d-{fg_hex}.svg", _CHEVRON_DOWN_SVG, pal["fg"]),
            ("chev_down_dim_url", f"chev-dd-{dim_hex}.svg", _CHEVRON_DOWN_SVG, pal["fg_dim"]),
            ("chev_up_url", f"chev-u-{dim_hex}.svg", _CHEVRON_UP_SVG, pal["fg_dim"]),
        ):
            path = cache / fname
            path.write_text(svg.format(color=color), encoding="utf-8")
            out[key] = path.as_posix()
        return out
    except OSError:
        return empty


_QSS = """
/* ================= KB-Remote — MobaXterm look =================
   Flat light-gray Windows chrome, white work surfaces, 1 px borders,
   2–3 px radii, Windows-blue selection. Segoe UI 9 pt. */

* {{
    font-family: {ui_sans};
    outline: none;
}}
QMainWindow, QDialog {{
    background: {bg};
}}
QWidget {{
    color: {fg};
    font-size: 12px;
}}
QToolTip {{
    background: {bg2};
    color: {fg};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 4px 7px;
    font-size: 12px;
}}

/* ================= Menu bar — classic Windows ================= */
QMenuBar {{
    background: {bg};
    border-bottom: 1px solid {border};
    padding: 0px 2px;
    spacing: 0px;
    font-size: 12px;
    min-height: 22px;
}}
QMenuBar::item {{
    padding: 3px 8px;
    border-radius: 0px;
    color: {fg};
    margin: 0px;
}}
QMenuBar::item:selected {{
    background: {sel_hover};
    color: {fg};
    border: 1px solid {accent_subtle};
    padding: 2px 7px;
}}
QMenuBar::item:pressed {{
    background: {accent_subtle};
    color: {fg};
}}

QMenu {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 2px 0px;
}}
QMenu::item {{
    padding: 5px 24px 5px 30px;
    border-radius: 0px;
    color: {fg};
    font-size: 12px;
    margin: 0px;
}}
QMenu::item:selected {{
    background: {accent_subtle};
    color: {fg};
}}
QMenu::item:selected:active {{
    background: {accent_subtle};
    color: {fg};
}}
QMenu::item:disabled {{
    color: {fg_muted};
}}
QMenu::separator {{
    height: 1px;
    background: {border};
    margin: 3px 2px 3px 30px;
}}
QMenu::icon {{
    left: 6px;
}}
QMenu::indicator {{
    left: 7px;
    width: 13px;
    height: 13px;
    border-radius: 2px;
    border: 1px solid {border_strong};
    background: {bg2};
}}
QMenu::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url({check_url});
}}
QMenu::right-arrow {{
    image: url({chev_right_url});
    width: 12px; height: 12px;
    right: 6px;
}}

/* ================= Toolbar — MobaXterm big buttons ================= */
QToolBar {{
    background: {bg};
    border: none;
    border-bottom: 1px solid {border};
    spacing: 1px;
    padding: 2px 4px;
    min-height: 34px;
}}
QToolBar#moxaToolbar {{
    spacing: 1px;
    padding: 3px 6px 2px 6px;
    min-height: 58px;
}}
QToolBar#moxaToolbar QToolButton {{
    padding: 3px 7px 2px 7px;
    min-width: 48px;
    min-height: 44px;
    font-size: 11px;
    font-weight: 400;
    border-radius: 2px;
    color: {fg};
}}
QToolBar::separator {{
    width: 1px;
    background: {border_strong};
    margin: 6px 4px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 3px 6px;
    color: {fg};
    font-weight: 400;
    font-size: 12px;
}}
QToolButton:hover {{
    background: {sel_hover};
    color: {fg};
    border-color: {accent_subtle};
}}
QToolButton:pressed {{
    background: {accent_subtle};
    border-color: {accent};
}}
QToolButton:checked {{
    background: {accent_subtle};
    color: {fg};
    border-color: {accent}99;
}}
QToolButton:focus {{
    border: 1px dotted {fg_dim};
}}
QToolButton:disabled {{
    color: {fg_muted};
}}
QToolButton::menu-indicator {{
    image: none;
}}

/* ================= Buttons — flat Windows push buttons ================= */
QPushButton {{
    background: {panel2};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 3px 14px;
    color: {fg};
    font-weight: 400;
    font-size: 12px;
    min-height: 17px;
    min-width: 56px;
}}
QPushButton:hover {{
    background: {sel_hover};
    border-color: {accent};
}}
QPushButton:pressed {{
    background: {accent_subtle};
    border-color: {accent_active};
}}
QPushButton:focus {{
    border: 1px solid {accent};
}}
QPushButton:default {{
    border: 1px solid {accent};
}}
QPushButton:disabled {{
    color: {fg_muted};
    background: {bg3};
    border-color: {border};
}}
QPushButton#primary, QPushButton#accent {{
    background: {accent};
    color: {accent_text};
    border: 1px solid {accent_active};
    font-weight: 400;
    border-radius: 2px;
}}
QPushButton#primary:hover, QPushButton#accent:hover {{
    background: {accent_hover};
    border-color: {accent};
}}
QPushButton#primary:pressed, QPushButton#accent:pressed {{
    background: {accent_active};
    border-color: {accent_active};
}}
QPushButton#primary:disabled, QPushButton#accent:disabled {{
    background: {bg3};
    color: {fg_muted};
    border-color: {border};
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {fg};
    border-radius: 2px;
    min-width: 0px;
}}
QPushButton#ghost:hover {{
    background: {sel_hover};
    border-color: {accent_subtle};
}}
QPushButton#ghost:pressed {{
    background: {accent_subtle};
}}
QPushButton#subtle {{
    background: {panel2};
    border: 1px solid {border_strong};
    color: {fg};
    border-radius: 2px;
    min-width: 0px;
}}
QPushButton#subtle:hover {{
    background: {sel_hover};
    border-color: {accent};
}}
QPushButton#danger {{
    background: {panel2};
    border: 1px solid {border_strong};
    color: {bad};
    border-radius: 2px;
    font-weight: 400;
}}
QPushButton#danger:hover {{
    background: {bad};
    border-color: {bad_active};
    color: {bad_text};
}}
QPushButton#danger:pressed {{
    background: {bad_active};
    border-color: {bad_active};
    color: {bad_text};
}}
QPushButton#danger:disabled {{
    color: {fg_muted};
    background: {bg3};
    border-color: {border};
}}

/* Quick connect — joined input + button group (toolbar) */
QWidget#quickConnect {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 2px;
}}
QWidget#quickConnect:hover {{
    border-color: {accent};
}}
QWidget#quickConnect QLineEdit {{
    background: transparent;
    border: none;
    padding: 3px 8px;
    font-size: 12px;
    color: {fg};
    min-height: 18px;
}}
QWidget#quickConnect QPushButton {{
    border: none;
    border-left: 1px solid {accent_active};
    border-radius: 0px;
    padding: 3px 10px;
    font-size: 12px;
    min-height: 18px;
    min-width: 0px;
}}

/* ================= Inputs — white sunken fields ================= */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 3px 6px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    color: {fg};
    min-height: 18px;
    font-size: 12px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
    background: {bg2};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
    border-color: {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background: {bg};
    color: {fg_muted};
    border-color: {border};
}}
QLineEdit#search {{
    border-radius: 2px;
    padding: 3px 6px 3px 6px;
    background: {bg2};
    border: 1px solid {border_strong};
    font-size: 12px;
}}
QLineEdit#search:focus {{
    border-color: {accent};
}}
QLineEdit#search:hover {{
    border-color: {accent};
}}
QLineEdit#invalid, QSpinBox#invalid, QComboBox#invalid {{
    border-color: {bad};
}}

QComboBox {{
    padding-right: 20px;
    background: {bg2};
    selection-background-color: {bg2};
    selection-color: {fg};
}}
QComboBox:on {{
    background: {bg2};
    border-color: {accent};
}}
QComboBox:editable {{
    background: {bg2};
}}
QComboBox:!editable, QComboBox::drop-down:editable,
QComboBox:!editable:on, QComboBox::drop-down:editable:on {{
    background: {bg2};
}}
QComboBox::drop-down {{
    border: none;
    border-left: 1px solid transparent;
    width: 20px;
    border-radius: 0px;
}}
QComboBox::drop-down:hover {{
    background: {sel_hover};
}}
QComboBox::down-arrow {{
    image: url({chev_down_dim_url});
    width: 12px; height: 12px;
}}
QComboBox QAbstractItemView {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 0px;
    selection-background-color: {accent};
    selection-color: {accent_text};
    outline: none;
    font-family: {ui_sans};
}}
QComboBox QAbstractItemView::item {{
    padding: 3px 8px;
    border-radius: 0px;
    margin: 0px;
    min-height: 18px;
    border: none;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {sel_hover};
    color: {fg};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {accent};
    color: {accent_text};
    font-weight: 400;
}}

/* ================= Tabs — classic MobaXterm document tabs ================= */
QTabWidget::pane {{
    border: 1px solid {border_strong};
    border-top: 1px solid {border_strong};
    background: {bg2};
    border-radius: 0px;
    top: -1px;
}}
QTabBar {{
    background: transparent;
    qproperty-drawBase: 0;
    border: none;
}}
QTabBar::tab {{
    background: {bg3};
    color: {fg_dim};
    padding: 4px 10px 4px 8px;
    border: 1px solid {border_strong};
    border-bottom: none;
    border-top-left-radius: 3px;
    border-top-right-radius: 3px;
    margin-right: -1px;
    margin-top: 3px;
    font-weight: 400;
    font-size: 12px;
    min-height: 18px;
    max-width: 200px;
}}
QTabBar::tab:selected {{
    background: {bg2};
    color: {fg};
    border-color: {border_strong};
    border-top: 2px solid {accent};
    margin-top: 0px;
    padding-bottom: 5px;
}}
QTabBar::tab:hover:!selected {{
    background: {sel_hover};
    color: {fg};
}}
QTabBar::tab:first {{
    margin-left: 2px;
}}
QTabBar::close-button {{
    subcontrol-position: right;
    width: 14px; height: 14px;
    border-radius: 2px;
    margin-left: 4px;
    margin-right: 0px;
    background: transparent;
}}
QTabBar::close-button:hover {{
    background: {bad};
}}
QTabBar::close-button:pressed {{
    background: {bad_active};
}}
QTabBar QToolButton {{
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 1px;
    margin-top: 3px;
}}
QTabBar QToolButton:hover {{
    background: {sel_hover};
    border-color: {accent};
}}
QTabBar::scroller {{
    width: 32px;
}}

/* Vertical tab strip (sidebar left rail: Sessions / Tools / Macros) */
QTabBar#sideRail::tab {{
    background: {bg3};
    color: {fg_dim};
    border: 1px solid {border_strong};
    border-right: none;
    border-top-left-radius: 3px;
    border-bottom-left-radius: 3px;
    border-top-right-radius: 0px;
    border-bottom-right-radius: 0px;
    padding: 12px 4px 12px 3px;
    margin: 0px 0px 2px 3px;
    min-height: 60px;
    min-width: 14px;
    font-size: 11px;
}}
QTabBar#sideRail::tab:selected {{
    background: {bg2};
    color: {fg};
    border-left: 2px solid {accent};
    border-top: 1px solid {border_strong};
    margin-left: 0px;
    padding-right: 5px;
}}
QTabBar#sideRail::tab:hover:!selected {{
    background: {sel_hover};
    color: {fg};
}}

/* ================= Trees & Lists — Explorer style ================= */
QTreeView, QListView, QTableView {{
    background: {bg2};
    alternate-background-color: {bg};
    border: 1px solid {border_strong};
    border-radius: 0px;
    padding: 0px;
    outline: none;
    font-size: 12px;
    show-decoration-selected: 1;
}}
QTreeView::item, QListView::item, QTableView::item {{
    padding: 2px 4px;
    border-radius: 0px;
    margin: 0px;
    color: {fg};
    border: 1px solid transparent;
    min-height: 20px;
}}
QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background: {sel_hover};
    border-color: {accent_subtle};
}}
QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background: {accent_subtle};
    color: {fg};
    border: 1px solid {accent}99;
    font-weight: 400;
}}
QTreeView::item:selected:active, QListView::item:selected:active {{
    background: {accent_subtle};
    color: {fg};
}}
QTreeView::item:selected:!active, QListView::item:selected:!active {{
    background: {bg3};
    border-color: {border_strong};
}}
QTreeView::branch {{
    background: transparent;
}}
QTreeView::branch:selected {{
    background: {accent_subtle};
}}
QTreeView::branch:hover {{
    background: {sel_hover};
}}
QTreeView::branch:has-children:!has-siblings:closed,
QTreeView::branch:closed:has-children:has-siblings {{
    image: url({chev_right_url});
    border-image: none;
}}
QTreeView::branch:open:has-children:!has-siblings,
QTreeView::branch:open:has-children:has-siblings {{
    image: url({chev_down_url});
    border-image: none;
}}
QHeaderView::section {{
    background: {bg2};
    border: none;
    border-bottom: 1px solid {border};
    border-right: 1px solid {border};
    padding: 4px 8px;
    font-weight: 400;
    color: {fg};
    font-size: 12px;
}}
QHeaderView::section:hover {{
    background: {sel_hover};
}}
QTableView QTableCornerButton::section {{
    background: {bg2};
    border: 1px solid {border};
}}

/* ================= Splitter ================= */
QSplitter::handle {{
    background: {bg};
    width: 4px;
    height: 4px;
}}
QSplitter::handle:hover {{
    background: {accent_subtle};
}}
QSplitter::handle:vertical {{
    height: 4px;
}}

/* ================= Scrollbars — classic Windows, slim ================= */
QScrollBar:vertical {{
    background: {bg};
    width: 12px;
    margin: 0px;
    border-left: 1px solid {border_subtle};
}}
QScrollBar::handle:vertical {{
    background: {panel3};
    border-radius: 0px;
    min-height: 28px;
    margin: 1px 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {border_strong};
}}
QScrollBar::handle:vertical:pressed {{
    background: {fg_muted};
}}
QScrollBar:horizontal {{
    background: {bg};
    height: 12px;
    margin: 0px;
    border-top: 1px solid {border_subtle};
}}
QScrollBar::handle:horizontal {{
    background: {panel3};
    min-width: 28px;
    margin: 2px 1px;
    border-radius: 0px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {border_strong};
}}
QScrollBar::handle:horizontal:pressed {{
    background: {fg_muted};
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
    background: {bg};
    border-top: 1px solid {border};
    color: {fg};
    padding: 0px 6px;
    font-size: 11.5px;
    min-height: 20px;
}}
QStatusBar::item {{
    border: none;
    border-right: 1px solid {border};
}}

/* ================= Groups — classic etched group boxes ================= */
QGroupBox {{
    border: 1px solid {border_strong};
    border-radius: 3px;
    margin-top: 10px;
    padding: 12px 10px 8px 10px;
    background: transparent;
    font-weight: 400;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    top: 0px;
    padding: 0px 4px;
    background: {bg};
    color: {accent};
    border: none;
    font-size: 12px;
    font-weight: 400;
}}
QDialog QGroupBox::title {{
    background: {bg};
}}
QFormLayout QLabel {{
    padding-top: 0px;
}}

/* ================= Progress — Windows green bar ================= */
QProgressBar {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 0px;
    text-align: center;
    height: 14px;
    color: {fg};
    font-size: 10.5px;
}}
QProgressBar::chunk {{
    background: {good};
    border-radius: 0px;
    margin: 1px;
}}

/* ================= Checkboxes & Radios ================= */
QCheckBox, QRadioButton {{
    spacing: 6px;
    color: {fg};
    font-size: 12px;
    padding: 1px 0px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 13px; height: 13px;
    border-radius: 2px;
    border: 1px solid {fg_dim};
    background: {bg2};
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url({check_url});
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent};
    background: {sel_hover};
}}
QCheckBox::indicator:indeterminate {{
    background: {accent};
    border-color: {accent};
}}
QRadioButton::indicator {{
    border-radius: 7px;
}}
QRadioButton::indicator:checked {{
    background: {bg2};
    border-color: {accent};
    image: url({dot_url});
}}
QCheckBox::indicator:checked:hover {{
    background: {accent_hover};
    border-color: {accent_hover};
}}
QRadioButton::indicator:checked:hover {{
    background: {bg2};
    border-color: {accent_hover};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {border};
    background: {bg};
}}

/* ================= Labels ================= */
QLabel#muted {{
    color: {fg_dim};
}}
QLabel#h1 {{
    font-size: 15px;
    font-weight: 400;
    font-family: {ui_display};
    color: {accent};
}}
QLabel#h2 {{
    font-size: 12px;
    font-weight: 700;
    color: {fg};
}}
QLabel#caption {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#dashTitle {{
    font-size: 20px;
    font-weight: 400;
    color: {accent};
    font-family: {ui_display};
}}
QLabel#dashVersion {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#quickTitle {{
    font-size: 12px;
    font-weight: 700;
    color: {fg};
}}
QLabel#cardTitle {{
    font-size: 12px;
    font-weight: 400;
    color: {fg};
}}
QLabel#cardSub {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#protoChip {{
    font-size: 10px;
    font-weight: 700;
    color: {fg_dim};
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
}}
QLabel#tabCount {{
    font-size: 10px;
    font-weight: 700;
    color: {fg};
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
}}
QLabel#sideTitle {{
    font-size: 12px;
    font-weight: 700;
    color: {fg};
}}
QLabel#sideCount {{
    background: {bg3};
    color: {fg_dim};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
    font-size: 11px;
    font-weight: 400;
}}
QTreeView#sessionTree {{
    border: 1px solid {border_strong};
    background: {bg2};
    outline: none;
}}
QTreeView#sessionTree::item {{
    min-height: 20px;
    border-radius: 0px;
    margin: 0px;
    padding: 1px 3px;
    border: 1px solid transparent;
}}
QTreeView#sessionTree::item:hover {{
    background: {sel_hover};
    border-color: {accent_subtle};
}}
QTreeView#sessionTree::item:selected {{
    background: {accent_subtle};
    color: {fg};
    border-color: {accent}99;
}}
QTreeView#sessionTree::item:selected:!active {{
    background: {bg3};
    border-color: {border_strong};
}}
QTreeView#sessionTree::branch {{
    background: transparent;
}}
QLabel#pvTitle {{
    font-size: 12.5px;
    font-weight: 700;
    color: {fg};
}}
QFrame#palettePreview {{
    background: {bg};
    border: 1px solid {border_strong};
    border-radius: 0px;
}}
QSplitter#paletteSplit::handle {{
    background: transparent;
    width: 6px;
}}
QLabel#pvSub {{
    font-size: 11px;
    color: {fg_dim};
}}
QLabel#pvChip {{
    font-size: 10px;
    font-weight: 700;
    color: {fg_dim};
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 1px 5px;
}}
QLabel#pvKbd, QLabel#kbd {{
    font-size: 11px;
    font-weight: 400;
    color: {fg};
    background: {bg2};
    border: 1px solid {border_strong};
    border-bottom: 2px solid {border_strong};
    border-radius: 2px;
    padding: 0px 5px;
    font-family: {ui_mono};
}}
QPushButton#tabClose {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 1px;
    min-width: 0px;
}}
QPushButton#tabClose:hover {{
    background: {bad};
    border-color: {bad_active};
}}
QPushButton#tabClose:pressed {{
    background: {bad_active};
}}
QFrame#hairline {{
    background: {border};
    max-height: 1px;
    border: none;
}}

/* ================= Dialogs ================= */
QDialog {{
    background: {bg};
    border-radius: 0px;
}}

/* ================= Surfaces ================= */
QWidget#card {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 3px;
}}
QWidget#card_hover {{
    background: {bg2};
    border: 1px solid {border};
    border-radius: 3px;
}}
QWidget#card_hover:hover {{
    border-color: {accent};
    background: {sel_hover};
}}
QWidget#header {{
    background: {bg};
    border-bottom: 1px solid {border};
    border-radius: 0px;
}}
QWidget#sidebar {{
    background: {bg};
    border-right: 1px solid {border};
}}
QWidget#sidebarPanel {{
    background: {bg};
}}
QWidget#workArea {{
    background: {bg};
}}
QWidget#dashboard {{
    background: {bg2};
    border: 1px solid {border_strong};
}}

/* ================= Command bar (MobaXterm terminal command line) ===== */
QWidget#commandBar {{
    background: {bg};
    border-top: 1px solid {border};
    padding: 0px;
}}
QLabel#commandPrompt {{
    color: {fg};
    font-size: 12px;
    font-weight: 400;
    padding-left: 2px;
}}
QLineEdit#commandLine {{
    background: {bg2};
    border: 1px solid {border_strong};
    border-radius: 2px;
    padding: 2px 6px;
    font-size: 12px;
    font-family: {ui_mono};
    min-height: 16px;
}}
QLineEdit#commandLine:focus {{
    border-color: {accent};
    background: {bg2};
}}
QLineEdit#commandLine:hover {{
    border-color: {accent};
}}

/* ================= Status session chip ================= */
QLabel#statusSession {{
    color: {fg};
    font-family: {ui_sans};
    font-size: 11.5px;
    background: transparent;
    border: none;
    padding: 0px 6px;
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

/* ================= SpinBox buttons — Windows up/down ================= */
QSpinBox::up-button, QSpinBox::down-button {{
    background: {bg2};
    border: none;
    border-left: 1px solid {border};
    border-radius: 0px;
    width: 16px;
    margin: 0px;
}}
QSpinBox::up-button {{
    border-bottom: 1px solid {border};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {sel_hover};
}}
QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
    background: {accent_subtle};
}}
QSpinBox::up-arrow {{
    image: url({chev_up_url});
    width: 10px; height: 10px;
}}
QSpinBox::down-arrow {{
    image: url({chev_down_dim_url});
    width: 10px; height: 10px;
}}

/* ================= Sliders ================= */
QSlider::groove:horizontal {{
    height: 4px;
    background: {bg3};
    border: 1px solid {border_strong};
    border-radius: 0px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    border: 1px solid {accent_active};
    width: 10px;
    margin: -6px 0;
    border-radius: 2px;
}}
QSlider::handle:horizontal:hover {{
    background: {accent_hover};
}}

/* ================= Dock / misc ================= */
QDockWidget::title {{
    background: {bg3};
    padding: 4px 6px;
    border: 1px solid {border};
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {border};
}}
"""


_QSS_COMPACT = """
/* ================= Compact density (Settings → UI) ================= */
QWidget {{ font-size: 11.5px; }}
QMenuBar {{ min-height: 20px; font-size: 11.5px; }}
QMenuBar::item {{ padding: 2px 7px; }}
QMenu::item {{ padding: 3px 20px 3px 28px; }}
QToolBar {{ min-height: 28px; padding: 1px 4px; }}
QToolBar#moxaToolbar {{ min-height: 44px; padding: 2px 4px; }}
QToolBar#moxaToolbar QToolButton {{ min-height: 34px; min-width: 40px; padding: 2px 5px; font-size: 10.5px; }}
QToolButton {{ padding: 2px 5px; min-height: 20px; font-size: 11.5px; }}
QPushButton {{ padding: 2px 10px; min-height: 15px; font-size: 11.5px; }}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox {{
    padding: 2px 5px; min-height: 15px; font-size: 11.5px;
}}
QTabBar::tab {{ padding: 3px 8px; min-height: 16px; }}
QTreeView::item, QListView::item, QTableView::item {{ padding: 1px 3px; min-height: 18px; }}
QTreeView#sessionTree::item {{ min-height: 18px; padding: 0px 3px; }}
QStatusBar {{ min-height: 18px; font-size: 11px; }}
QGroupBox {{ margin-top: 9px; padding: 9px 8px 6px 8px; }}
QCheckBox, QRadioButton {{ font-size: 11.5px; }}
"""


def _shade(hex_color: str, factor: float) -> str:
    """Darken (<1) or lighten (>1) a #rrggbb colour, clamped to 0-255."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = (min(255, max(0, int(round(c * factor))) ) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def apply_theme(
    app: QApplication,
    theme: str = "dark",
    density: str = "comfortable",
    animations: bool = True,
) -> None:
    global _current_theme, _density, MOTIONS_ENABLED
    _current_theme = theme if theme in PALETTE else "mobaxterm"
    _density = density if density in ("comfortable", "compact") else "comfortable"
    MOTIONS_ENABLED = bool(animations)
    pal = palette(theme)
    extra = _indicator_image_urls(pal)
    # Danger-button shades derived from the palette's `bad` colour.
    fmt = {
        **pal,
        **extra,
        "bad_hover": _shade(pal["bad"], 1.18),
        "bad_active": _shade(pal["bad"], 0.82),
        "bad_text": "#ffffff",
        "ui_sans": _UI_SANS,
        "ui_mono": _UI_MONO,
        "ui_display": _UI_DISPLAY,
    }
    qss = _QSS.format(**fmt)
    if _density == "compact":
        qss += _QSS_COMPACT.format(**fmt)
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
    # Let live views (dashboard, chips, tab badges…) re-tint themselves now
    # that the new stylesheet, palette and icon cache are in place.
    _fire_theme_changed()
