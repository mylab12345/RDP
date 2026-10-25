"""Look & feel: Studio Dark and alternate application themes.

The default chrome uses deep slate surfaces, a restrained mint accent, a
compact command bar, and softly layered session surfaces. Established
MobaXterm, Midnight, Dracula, Ocean, and high-contrast palettes remain
available in View → Theme; every palette shares the same accessible widgets
and geometry.

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


def icon(name: str, tint: str | None = None, size: int | None = None) -> QIcon:
    """Load a PNG or SVG icon.

    SVGs are re-rendered in ``tint`` (default: the current theme's icon
    colour, ``fg_dim``) so they stay legible and consistent in every theme.
    Falls back to a drawn text glyph when no icon file can be loaded.
    """
    _ = size  # accepted for caller convenience; QIcon carries multi-size pixmaps
    key = (name, tint or "")
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached

    ic: QIcon | None = None
    exts = (".svg", ".png") if tint else (".png", ".svg")
    for ext in exts:
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


def accent_icon(name: str, size: int = 18) -> QIcon:
    """Return ``name`` tinted with the current theme's accent colour."""
    return icon(name, palette()["accent"], size=size)


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
    """Icon on a rounded surface tile — protocol marks for tabs and rows.

    Modern treatment: a soft tile in the tint's own hue (14 % alpha) with
    the glyph in full tint, so the protocol reads as a colour mark.
    """
    pal = palette()
    tint = tint or pal["fg_dim"]
    key = (f"badge:{name}:{size}", tint)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    radius = max(3, int(size * 0.28))
    pix = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(palette_color(tint + "24"))  # 14 % tint fill
    painter.drawRoundedRect(0, 0, size, size, radius, radius)
    inner = icon(name, tint).pixmap(QSize(int(size * 0.68), int(size * 0.68)))
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
# colors at construction time use this so a live theme switch doesn't render
# one frame of stale chrome.
_current_theme = "studio_dark"
_density = "comfortable"  # comfortable | compact
_accent_color = ""  # empty = selected palette accent
MOTIONS_ENABLED = True  # global motion switch (Settings → UI → Animations)


def current_theme() -> str:
    return _current_theme


def current_density() -> str:
    return _density


def current_accent_color() -> str:
    """Currently applied custom accent, or ``""`` for the theme default."""
    return _accent_color


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


def _default_theme() -> str:
    """Shipped default theme id (imported lazily — ``core`` stays Qt-free)."""
    from ..core.settings import DEFAULT_THEME

    return DEFAULT_THEME


def _normalize_hex(value: str | None) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if not text.startswith("#"):
        text = f"#{text}"
    if len(text) != 7:
        return ""
    try:
        int(text[1:], 16)
    except ValueError:
        return ""
    return text.lower()


def _mix_hex(a: str, b: str, amount: float) -> str:
    """Mix ``a`` toward ``b`` by ``amount`` (0..1)."""
    amount = max(0.0, min(1.0, float(amount)))
    ca = QColor(a)
    cb = QColor(b)
    r = round(ca.red() + (cb.red() - ca.red()) * amount)
    g = round(ca.green() + (cb.green() - ca.green()) * amount)
    bl = round(ca.blue() + (cb.blue() - ca.blue()) * amount)
    return f"#{r:02x}{g:02x}{bl:02x}"


def _relative_luminance(hex_color: str) -> float:
    color = QColor(hex_color)

    def channel(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(color.red()) + 0.7152 * channel(color.green()) + 0.0722 * channel(color.blue())


def _contrast_ratio(fg: str, bg: str) -> float:
    hi, lo = max(_relative_luminance(fg), _relative_luminance(bg)), min(
        _relative_luminance(fg), _relative_luminance(bg)
    )
    return (hi + 0.05) / (lo + 0.05)


def _accent_text_for(accent: str) -> str:
    """Choose white or black text for the custom accent button fill."""
    white = _contrast_ratio("#ffffff", accent)
    black = _contrast_ratio("#000000", accent)
    return "#000000" if black >= white and black >= 4.5 else "#ffffff"


def _with_accent_override(base: dict[str, str], accent: str) -> dict[str, str]:
    """Return ``base`` with just the interactive accent family replaced."""
    accent = _normalize_hex(accent)
    if not accent:
        return base
    pal = dict(base)
    text = _accent_text_for(accent)
    hover = _mix_hex(accent, "#ffffff", 0.18)
    active = _mix_hex(accent, "#000000", 0.18)
    pal.update(
        {
            "accent": accent,
            "accent_hover": hover,
            "accent_active": active,
            "accent_text": text,
            "accent_subtle": f"{accent}29",
            "accent_gradient": (
                "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                f"stop:0 {hover}, stop:1 {active})"
            ),
        }
    )
    return pal


def palette(theme: str | None = None) -> dict[str, str]:
    """Palette for ``theme`` — defaults to the currently applied theme.

    A user-chosen accent colour is layered on top at runtime; the shipped
    :data:`PALETTE` constants stay untouched for tests, previews and exports.
    """
    base = PALETTE.get(theme or _current_theme, PALETTE[_default_theme()])
    return _with_accent_override(base, _accent_color)




def toolbar_icon(name: str) -> QIcon:
    """Return a legible action glyph tuned to the active visual theme.

    Studio Dark uses a quiet, coordinated tint set with color reserved for
    primary actions and semantic states. The classic themes retain their
    original MobaXterm action colors.
    """
    if current_theme() == "studio_dark":
        pal = palette()
        studio_tints = {
            "plus": pal["accent"],
            "connect": pal["accent"],
            "search": pal["accent"],
            "transfer": pal["accent"],
            "server": pal["info"],
            "windows": pal["info"],
            "key": pal["warn"],
            "folder": pal["warn"],
            "star": pal["warn"],
            "shield": pal["good"],
            "close": pal["bad"],
            "stop": pal["bad"],
            "trash": pal["bad"],
        }
        return icon(name, studio_tints.get(name, pal["fg_dim"]))

    tint = TOOLBAR_ICON_TINTS.get(name)
    if tint and not is_dark_theme(None):
        return icon(name, tint)
    if tint:
        # Charcoal glyphs read as "off" on dark chrome — use the theme fg.
        if tint == "#3a3a3a":
            return icon(name, palette()["fg"])
        # Neutral charcoal chrome needs a gentler lift than the saturated
        # night palettes, and a ceiling keeps action glyphs out of neon.
        lift = 1.5 if current_theme() == "mobaxterm_dark" else 1.9
        return icon(name, _lift_for_dark(tint, lift))
    return icon(name)

# ----------------------------------------------------------------------
# Global application QSS — layered workbench surfaces, restrained controls,
# compact command bar, and palette-driven selection states.
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
    uid = os.getuid() if hasattr(os, "getuid") else "user"
    cache = Path(tempfile.gettempdir()) / f"kb-remote-indicators-{uid}"
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






def palette_color(value: str) -> QColor:
    """Parse a palette hex value (CSS RRGGBBAA order) into a QColor.

    Qt's string parser expects ``#AARRGGBB`` for 8-digit values, so the
    alpha byte must be moved into place manually — otherwise a
    ``"#2e9e4424"`` (14 % green) comes out as opaque brownish red.
    """
    h = value.lstrip("#")
    if len(h) == 8:
        r, g, b, a = (int(h[i : i + 2], 16) for i in (0, 2, 4, 6))
        return QColor(r, g, b, a)
    return QColor(value)


def solid_on(hex_fg: str, base: str) -> str:
    """Pre-blend an 8-digit RRGGBBAA colour over ``base`` → opaque #rrggbb.

    Qt's *stylesheet* parser mangles 8-digit hex (it reads ``#AARRGGBB``),
    so anything that ends up in QSS must be a solid 6-digit value first.
    """
    h = hex_fg.lstrip("#")
    if len(h) != 8:
        return hex_fg
    fg = palette_color(hex_fg)
    bg = QColor(base)
    a = fg.alphaF()
    out = QColor(
        round(bg.red() + (fg.red() - bg.red()) * a),
        round(bg.green() + (fg.green() - bg.green()) * a),
        round(bg.blue() + (fg.blue() - bg.blue()) * a),
    )
    return out.name()


def tint(hex_color: str, alpha: int, over: str | None = None) -> str:
    """``hex_color`` at ``alpha`` (0-255) as a QSS-safe solid colour.

    Pre-blends over ``over`` (default: the theme's ``bg2`` card surface).
    """
    base = over or palette()["bg2"]
    fg = QColor(hex_color)
    fg.setAlpha(max(0, min(255, int(alpha))))
    h = f"#{fg.red():02x}{fg.green():02x}{fg.blue():02x}{fg.alpha():02x}"
    return solid_on(h, base)


# Brightest channel a lifted glyph may reach on dark chrome. Above this the
# icon colours stop reading as MobaXterm's calm toolbar and start glowing.
_DARK_GLYPH_CEILING = 205


def _lift_for_dark(hex_color: str, factor: float) -> str:
    """Brighten ``hex_color`` for dark chrome, capping the peak channel.

    Plain multiplication saturates whatever channel was already brightest
    (green glyphs went neon, reds blew out). Scaling the whole colour back
    once its peak hits :data:`_DARK_GLYPH_CEILING` keeps the hue and the
    relative channel ratios — which is what makes the tint readable.
    """
    lifted = _shade(hex_color, factor)
    h = lifted.lstrip("#")
    if len(h) != 6:
        return lifted
    rgb = [int(h[i : i + 2], 16) for i in (0, 2, 4)]
    peak = max(rgb)
    if peak <= _DARK_GLYPH_CEILING:
        return lifted
    scale = _DARK_GLYPH_CEILING / peak
    return "#" + "".join(f"{min(255, max(0, round(c * scale))):02x}" for c in rgb)


def _shade(hex_color: str, factor: float) -> str:
    """Darken (<1) or lighten (>1) a #rrggbb colour, clamped to 0-255."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = (min(255, max(0, round(c * factor))) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ----------------------------------------------------------------------
# Design tokens — derived from the palette, never hard-coded per theme
# ----------------------------------------------------------------------
def _grad(*stops: tuple[float, str], x1: float = 0, y1: float = 0, x2: float = 0, y2: float = 1) -> str:
    """Build a QSS ``qlineargradient`` from ``(position, colour)`` stops."""
    body = ", ".join(f"stop:{pos:g} {color}" for pos, color in stops)
    return f"qlineargradient(x1:{x1:g}, y1:{y1:g}, x2:{x2:g}, y2:{y2:g}, {body})"


def design_tokens(pal: dict[str, str]) -> dict[str, str]:
    """Presentation tokens shared by the global sheet and inline widgets.

    The palette defines *semantics* (surface, text, accent, state); this layer
    turns them into the concrete values the design system needs: surface
    gradients, elevation steps, focus rings, soft state washes, and the
    button/field faces.  Everything is recomputed per theme, so a custom
    accent or a light palette produces a coherent set rather than a dark-only
    skin pasted onto white.
    """
    bg, bg2, bg3 = pal["bg"], pal["bg2"], pal["bg3"]
    panel, panel2 = pal["panel"], pal["panel2"]
    border, border_strong = pal["border"], pal["border_strong"]
    fg = pal["fg"]
    accent, accent_hover, accent_active = pal["accent"], pal["accent_hover"], pal["accent_active"]

    # Light themes invert the elevation direction: raised surfaces get
    # *lighter* and "shade" means a soft grey wash, not a glow.
    light = _relative_luminance(bg) > 0.5
    lift = 0.30 if light else 0.55  # how far to mix toward fg when raising

    field_bg = _mix_hex(bg2, bg, 0.55 if not light else 0.0)
    tokens = {
        # --- surfaces ---------------------------------------------------
        # A near-invisible accent wash at the top of the window gives the
        # chrome depth without a background image or gradient banding.
        "bg_grad": _grad((0.0, _mix_hex(bg, accent, 0.05 if not light else 0.03)),
                        (0.55, bg), (1.0, _mix_hex(bg, "#000000", 0.18 if not light else 0.02))),
        "chrome_grad": _grad((0.0, _mix_hex(panel2, "#ffffff", 0.05 if light else 0.03)),
                            (1.0, panel)),
        "card_grad": _grad((0.0, _mix_hex(bg2, fg, 0.035 if not light else 0.0)),
                          (1.0, bg2)),
        "card_grad_hover": _grad((0.0, _mix_hex(bg3, fg, 0.045 if not light else 0.0)),
                                (1.0, _mix_hex(bg2, accent, 0.04))),
        "hero_grad": _grad(
            (0.0, _mix_hex(bg2, accent, 0.16 if not light else 0.10)),
            (0.55, _mix_hex(bg2, accent, 0.05 if not light else 0.03)),
            (1.0, bg2),
            x1=0, y1=0, x2=1, y2=1,
        ),
        "rail_grad": _grad((0.0, _mix_hex(panel, accent, 0.10 if not light else 0.05)),
                          (1.0, panel)),
        "nav_active_grad": _grad((0.0, _mix_hex(bg3, accent, 0.26 if not light else 0.16)),
                                (1.0, _mix_hex(bg2, accent, 0.10 if not light else 0.06))),
        "tab_active_grad": _grad((0.0, _mix_hex(bg2, accent, 0.20 if not light else 0.10)),
                                (1.0, bg2)),
        "elev_line": _mix_hex(bg2, "#ffffff", 0.09 if not light else 0.0),
        "hairline": _mix_hex(bg2, border, 0.6),
        "scrim": _mix_hex(bg, "#000000", 0.25 if not light else 0.0),

        # --- controls ---------------------------------------------------
        "field_bg": field_bg,
        "field_bg_hover": _mix_hex(field_bg, fg if not light else bg, 0.03 if not light else 0.45),
        "field_bg_focus": _mix_hex(field_bg, accent, 0.06 if not light else 0.04),
        # Light themes raise a button by *darkening* it toward the window
        # chrome; dark themes lift it with a hint of the text colour.
        "btn_face": _mix_hex(bg2, fg, 0.055) if not light else _mix_hex(bg2, bg, 0.55),
        "btn_face_hover": _mix_hex(bg2, fg, 0.105) if not light else _mix_hex(bg2, bg, 0.85),
        "btn_face_press": _mix_hex(bg2, fg, 0.02) if not light else _mix_hex(bg2, bg, 1.0),
        "btn_line": _mix_hex(border, fg, 0.10) if not light else border_strong,
        "btn_line_hover": _mix_hex(border_strong, accent, 0.25 if not light else 0.10),
        "accent_grad": _grad((0.0, accent_hover), (1.0, accent_active),
                             x1=0, y1=0, x2=0.85, y2=1),
        "accent_grad_hover": _grad((0.0, _mix_hex(accent_hover, "#ffffff", 0.12)),
                                   (1.0, accent)),
        "accent_grad_press": _grad((0.0, accent), (1.0, accent_active)),

        # --- accent washes & focus --------------------------------------
        "accent_ring": tint(accent, 0x3d, bg),
        "accent_soft": tint(accent, 0x1c, bg2),
        "accent_soft2": tint(accent, 0x2c, bg2),
        "accent_line": tint(accent, 0x66, bg2),
        "accent_text_soft": _mix_hex(accent, fg, 0.35 if not light else 0.15),

        # --- state washes (chips, banners, meters) ----------------------
        "good_soft": tint(pal["good"], 0x1e, bg2),
        "good_line": tint(pal["good"], 0x55, bg2),
        "warn_soft": tint(pal["warn"], 0x1e, bg2),
        "warn_line": tint(pal["warn"], 0x55, bg2),
        "info_soft": tint(pal["info"], 0x1e, bg2),
        "info_line": tint(pal["info"], 0x55, bg2),
        "bad_soft": tint(pal["bad"], 0x22, bg2),
        "bad_line": tint(pal["bad"], 0x55, bg2),

        # --- type & space ------------------------------------------------
        "ui_sans": _UI_SANS,
        "ui_mono": _UI_MONO,
        "ui_display": _UI_DISPLAY,
        # Motion is expressed in the sheet only as easing hints for the
        # widgets that animate themselves (see widgets.animate_*).
        "lift": f"{lift:g}",
    }
    # Danger shades (hover/press) derived from the palette's bad colour.
    tokens.update(
        {
            "bad_hover": _shade(pal["bad"], 1.18),
            "bad_active": _shade(pal["bad"], 0.82),
            "bad_text": "#ffffff",
            "bad_border": tint(pal["bad"], 0x55, bg2),
            "bad_faint": tint(pal["bad"], 0x1A, bg2),
        }
    )
    return tokens


def apply_theme(
    app: QApplication,
    theme: str = "",
    density: str = "comfortable",
    animations: bool = True,
    accent_color: str = "",
) -> None:
    global _current_theme, _density, _accent_color, MOTIONS_ENABLED
    _current_theme = theme if theme in PALETTE else _default_theme()
    _density = density if density in ("comfortable", "compact") else "comfortable"
    _accent_color = _normalize_hex(accent_color)
    MOTIONS_ENABLED = bool(animations)
    pal = palette(theme)
    extra = _indicator_image_urls(pal)
    # Palette + derived design tokens + regenerated indicator glyphs.
    # QSS cannot parse 8-digit hex (Qt mangles the alpha byte order), so every
    # translucent tint is pre-blended into a solid colour by design_tokens().
    fmt = {
        **pal,
        **design_tokens(pal),
        **extra,
        "bad_soft2": tint(pal["bad"], 0x33, pal["bg2"]),
    }
    # QSS cannot parse 8-digit hex (Qt mangles the alpha byte order), so
    # semi-transparent tints are pre-blended into solid colours over the
    # base surface.
    if len(pal["accent_subtle"].lstrip("#")) == 8:
        fmt["accent_subtle"] = solid_on(pal["accent_subtle"], pal["bg"])
    qss = _QSS.format(**fmt)
    if _density == "compact":
        qss += _QSS_COMPACT.format(**fmt)
    try:
        import gc
        import sys

        from PySide6.QtCore import QCoreApplication, QEvent
        from shiboken6 import delete as _qt_delete

        from .main_window import _MAIN

        caller_locals = {id(v) for v in sys._getframe(1).f_locals.values()}
        gc.collect()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for w in list(app.topLevelWidgets()):
            if (
                w.parentWidget() is None
                and id(w) not in caller_locals
                and (w is not _MAIN or getattr(w, "_closed_once", False))
            ):
                _qt_delete(w)
    except Exception:
        pass
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
