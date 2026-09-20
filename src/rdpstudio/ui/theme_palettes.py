"""Theme data: palettes, tints, font stacks.

Extracted verbatim from ``theme.py`` (ARCH-02). Pure data, no Qt
imports. ``theme.py`` re-exports these names, so ``from .theme
import PALETTE`` keeps working.

Every palette exposes the exact same 30 keys (see
``tests/test_ui_polish.py``) so the global QSS can ``.format(**pal)``
safely on any theme.
"""

from __future__ import annotations

# ----------------------------------------------------------------------
# Palettes — carefully tuned for contrast (WCAG AA) and layered surfaces
# Surface model:  bg (window chrome) < panel (chrome panels) < bg3 (fill)
#                < bg2 (content surface) — borders separate the layers.
# ----------------------------------------------------------------------
PALETTE = {
    # MobaXterm Dark (default) — the same neutral, square MobaXterm chrome
    # with the lights off: charcoal window chrome, Microsoft-blue accent.
    # The light palette's layer order is inverted (raised surfaces get
    # *lighter*, not darker) while every signature relationship holds:
    # bg < panel < bg3 < bg2 in luminance terms, accent #1670c6 with white
    # button text (5.0:1) and muted secondary text at 6.1:1 on bg3.
    "mobaxterm_dark": {
        "bg": "#1c1c1f",
        "bg2": "#232327",
        "bg3": "#2c2c31",
        "panel": "#202024",
        "panel2": "#292930",
        "panel3": "#3a3a42",
        "border": "#33333a",
        "border_strong": "#4a4a54",
        "border_subtle": "#2a2a2f",
        "fg": "#e9edf2",
        "fg_dim": "#b7bdc7",
        "fg_muted": "#a6adb8",
        "accent": "#1670c6",
        "accent_hover": "#2a86dd",
        "accent_active": "#0f5aa3",
        "accent_text": "#ffffff",
        "accent_subtle": "#1670c629",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a86dd, stop:1 #0f5aa3)",
        "good": "#4ec96b",
        "warn": "#e3a63c",
        "bad": "#ef6f74",
        "info": "#4da3f0",
        "term_bg": "#141416",
        "term_fg": "#dfe3e8",
        "sel": "#26456b",
        "sel_hover": "#2e2e34",
        "shadow": "#00000088",
        "shadow_soft": "#00000044",
        "overlay": "#1c1c1fe6",
        "card_shadow": "#00000055",
    },
    # MobaXterm — light neutral chrome (legacy default, still selectable). Signature values kept:
    # window chrome #f0f0f0, Microsoft-blue accent #0075d2 (white button
    # text at 4.7:1). Everything else is a cool, calm neutral family.
    "mobaxterm": {
        "bg": "#f0f0f0",
        "bg2": "#ffffff",
        "bg3": "#eceef1",
        "panel": "#f7f8fa",
        "panel2": "#eef0f3",
        "panel3": "#d8dce2",
        "border": "#e3e5e9",
        "border_strong": "#c9ced6",
        "border_subtle": "#eceef1",
        "fg": "#1f2329",
        "fg_dim": "#4d5460",
        "fg_muted": "#5f6672",
        "accent": "#0075d2",
        "accent_hover": "#1a86e0",
        "accent_active": "#0062ab",
        "accent_text": "#ffffff",
        "accent_subtle": "#e8f1fa",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2b8ee0, stop:1 #0a6fc9)",
        "good": "#2e8b3d",
        "warn": "#c0741f",
        "bad": "#d13438",
        "info": "#0078d7",
        "term_bg": "#0d1117",
        "term_fg": "#d4d9e1",
        "sel": "#cce8ff",
        "sel_hover": "#f4f6f8",
        "shadow": "#10182826",
        "shadow_soft": "#10182814",
        "overlay": "#f0f0f0e6",
        "card_shadow": "#1018280f",
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
        "fg_dim": "#8fc3d9",
        "fg_muted": "#7f9fb0",
        "accent": "#22d3ee",
        "accent_hover": "#67e8f9",
        "accent_active": "#06b6d4",
        "accent_text": "#04262f",
        "accent_subtle": "#22d3ee1f",
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
        "accent": "#3876b9",
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
        "fg_dim": "#b3bad0",
        "fg_muted": "#a0aac4",
        "accent": "#bd93f9",
        "accent_hover": "#caa8ff",
        "accent_active": "#a67ce8",
        "accent_text": "#1e1f29",
        "accent_subtle": "#bd93f924",
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
    # Midnight — deep navy night, vivid sky accent with dark label text.
    # All pairs verified against WCAG AA (test_all_palettes_meet_wcag_aa).
    "midnight": {
        "bg": "#0a1120",
        "bg2": "#0f1930",
        "bg3": "#1a2540",
        "panel": "#0e1830",
        "panel2": "#16233e",
        "panel3": "#2b3d63",
        "border": "#223350",
        "border_strong": "#3a5079",
        "border_subtle": "#141f38",
        "fg": "#e8edf5",
        "fg_dim": "#a8b6cf",
        "fg_muted": "#91a3c0",
        "accent": "#4d8fe8",
        "accent_hover": "#6ba3ef",
        "accent_active": "#2f6fd0",
        "accent_text": "#081120",
        "accent_subtle": "#1d3a5f",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4d8fe8, stop:1 #2f6fd0)",
        "good": "#34d399",
        "warn": "#fbbf24",
        "bad": "#f87171",
        "info": "#5aa5f5",
        "term_bg": "#050a14",
        "term_fg": "#c9d8ea",
        "sel": "#1d3a5f",
        "sel_hover": "#23466f",
        "shadow": "#00000066",
        "shadow_soft": "#00000033",
        "overlay": "#0a1120e6",
        "card_shadow": "#00000044",
    },
}

# Per-protocol accent colours (palette keys) so tabs, rows and previews
# read the protocol at a glance: SSH green, RDP blue, local = theme accent.
PROTOCOL_TINTS: dict[str, str] = {"ssh": "good", "rdp": "info", "local": "accent"}

# Typography — system UI stack first (Segoe UI on Windows), degrading to
# quality open-source fallbacks. Consolas for code/data.
_UI_SANS = (
    '"Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Liberation Sans", '
    '"Nimbus Sans L", "Helvetica Neue", "Arial", sans-serif'
)
_UI_MONO = (
    '"Cascadia Mono", "Consolas", "JetBrains Mono", "Liberation Mono", '
    '"DejaVu Sans Mono", "Noto Sans Mono", "Courier New", monospace'
)
_UI_DISPLAY = (
    '"Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", "Liberation Sans", '
    '"Helvetica Neue", "Arial", sans-serif'
)

# Toolbar glyphs — one tint per action so the big toolbar reads at a
# glance (keys are the icon names in resources/icons/).
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
