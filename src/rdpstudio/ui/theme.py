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

from .theme_palettes import (
    _UI_DISPLAY,
    _UI_MONO,
    _UI_SANS,
    PALETTE,
    PROTOCOL_TINTS,
    TOOLBAR_ICON_TINTS,
)
from .theme_qss import _QSS, _QSS_COMPACT

RESOURCES = Path(__file__).parent.parent / "resources"
ICONS = RESOURCES / "icons"



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




def protocol_tint(protocol: str) -> str:
    """Palette key used to colour-mark ``protocol``."""
    return PROTOCOL_TINTS.get((protocol or "").lower(), "accent")


def protocol_badge(protocol: str, icon_name: str, size: int = 16) -> QIcon:
    """Rounded-tile icon in the protocol's accent colour — for tabs & rows."""
    return badge_icon(icon_name, size, palette()[protocol_tint(protocol)])


def palette(theme: str | None = None) -> dict[str, str]:
    """Palette for ``theme`` — defaults to the currently applied theme."""
    return PALETTE.get(theme or _current_theme, PALETTE["mobaxterm"])




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
