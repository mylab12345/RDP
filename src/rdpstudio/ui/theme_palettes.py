"""Theme data: palettes, tints, font stacks.

Extracted verbatim from ``theme.py`` (ARCH-02). Pure data, no Qt
imports. ``theme.py`` re-exports these names, so ``from .theme
import PALETTE`` keeps working.
"""

from __future__ import annotations

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
        "fg_muted": "#656565",
        "accent": "#0075d2",
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
        "fg_muted": "#7196a7",
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
        "fg_dim": "#b0b8c8",
        "fg_muted": "#9ea8c3",
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
    # Midnight — deep navy night · sky accent. White button text and muted
    # text both meet WCAG AA (verified by test_all_palettes_meet_wcag_aa).
    "midnight": {
        "bg": "#0a1120",
        "bg2": "#0e1730",
        "bg3": "#1a2540",
        "panel": "#101b36",
        "panel2": "#1a2540",
        "panel3": "#2b3d63",
        "border": "#223350",
        "border_strong": "#3a5079",
        "border_subtle": "#141f38",
        "fg": "#e6edf7",
        "fg_dim": "#a9bcd6",
        "fg_muted": "#93a7c4",
        "accent": "#3b75b9",
        "accent_hover": "#3c78bd",
        "accent_active": "#2c5a96",
        "accent_text": "#ffffff",
        "accent_subtle": "#17395f",
        "accent_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3b75b9, stop:1 #2c5a96)",
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
