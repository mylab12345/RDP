"""Terminal color schemes for the built-in (pyte) renderer.

Pure data + helpers (no Qt at import time): each scheme is a dict of hex
colors — default fg/bg, cursor, selection, search-match tint and the 16
ANSI colors. Local shells render in the selected scheme; SSH tabs keep the
remote host's native console palette unless the user opts into overriding
it (``Settings.terminal_override_remote``).

Schemes are curated from widely used open palettes (Solarized by Ethan
Schoonover, Dracula by Zeno Rocha, Nord by Arctic Ice Studio, Monokai);
only hex values are stored, which are facts, not copyrightable expression.
"""

from __future__ import annotations

DEFAULT_SCHEME = "mobaxterm"


def _scheme(
    label: str,
    fg: str,
    bg: str,
    cursor: str,
    sel: str,
    colors16: list[str],
    *,
    fg_dim: str = "",
    dark: bool = True,
) -> dict:
    return {
        "id": "",
        "label": label,
        "fg": fg,
        "bg": bg,
        "cursor": cursor,
        "sel": sel,
        "fg_dim": fg_dim or fg,
        "dark": dark,
        "16": list(colors16),
    }


TERMINAL_SCHEMES: dict[str, dict] = {}


def _register(sid: str, scheme: dict) -> None:
    scheme["id"] = sid
    TERMINAL_SCHEMES[sid] = scheme


_register(
    "mobaxterm",
    _scheme(
        "MobaXterm (default)",
        fg="#e6eaf2",
        bg="#1c1c1f",
        cursor="#1670c6",
        sel="#1670c6",
        colors16=[
            "#1c1c1f", "#e5484d", "#46a758", "#f5a524", "#3e8ef7", "#a259d9", "#12a594", "#e6eaf2",
            "#5c677e", "#ff7a7a", "#6ee7a5", "#ffcb66", "#7cc4ff", "#c4a7ff", "#5eead4", "#f6f7fb",
        ],
        fg_dim="#8a94ac",
        dark=True,
    ),
)

_register(
    "solarized-dark",
    _scheme(
        "Solarized Dark",
        fg="#839496",
        bg="#002b36",
        cursor="#93a1a1",
        sel="#073642",
        colors16=[
            "#073642", "#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198", "#eee8d5",
            "#002b36", "#cb4b16", "#586e75", "#657b83", "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
        ],
        fg_dim="#586e75",
        dark=True,
    ),
)

_register(
    "solarized-light",
    _scheme(
        "Solarized Light",
        fg="#657b83",
        bg="#fdf6e3",
        cursor="#586e75",
        sel="#eee8d5",
        colors16=[
            "#073642", "#dc322f", "#859900", "#b58900", "#268bd2", "#d33682", "#2aa198", "#eee8d5",
            "#002b36", "#cb4b16", "#586e75", "#657b83", "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
        ],
        fg_dim="#93a1a1",
        dark=False,
    ),
)

_register(
    "dracula",
    _scheme(
        "Dracula",
        fg="#f8f8f2",
        bg="#282a36",
        cursor="#ff79c6",
        sel="#44475a",
        colors16=[
            "#21222c", "#ff5555", "#50fa7b", "#f1fa8c", "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
            "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5", "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
        ],
        fg_dim="#6272a4",
        dark=True,
    ),
)

_register(
    "monokai",
    _scheme(
        "Monokai",
        fg="#f8f8f2",
        bg="#272822",
        cursor="#f8f8f0",
        sel="#49483e",
        colors16=[
            "#272822", "#f92672", "#a6e22e", "#f4bf75", "#66d9ef", "#ae81ff", "#a1efe4", "#f8f8f2",
            "#75715e", "#f92672", "#a6e22e", "#f4bf75", "#66d9ef", "#ae81ff", "#a1efe4", "#f9f8f5",
        ],
        fg_dim="#75715e",
        dark=True,
    ),
)

_register(
    "nord",
    _scheme(
        "Nord",
        fg="#d8dee9",
        bg="#2e3440",
        cursor="#88c0d0",
        sel="#434c5e",
        colors16=[
            "#3b4252", "#bf616a", "#a3be8c", "#ebcb8b", "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
            "#4c566a", "#bf616a", "#a3be8c", "#ebcb8b", "#81a1c1", "#b48ead", "#8fbcbb", "#eceff4",
        ],
        fg_dim="#4c566a",
        dark=True,
    ),
)

_register(
    "light",
    _scheme(
        "Light (paper)",
        fg="#1f2430",
        bg="#fafafa",
        cursor="#1670c6",
        sel="#cfe3fa",
        colors16=[
            "#000000", "#c42b1c", "#0e7a3d", "#9a6a00", "#1a5fd7", "#7c3aed", "#007a87", "#5c677e",
            "#6b768f", "#e5484d", "#18a058", "#c77e00", "#3e8ef7", "#a259d9", "#12a594", "#eef1f8",
        ],
        fg_dim="#6b768f",
        dark=False,
    ),
)

del _register, _scheme


def scheme_ids() -> list[str]:
    """Stable scheme ids in presentation order."""
    order = ["mobaxterm", "dracula", "monokai", "nord", "solarized-dark", "solarized-light", "light"]
    return [sid for sid in order if sid in TERMINAL_SCHEMES]


def scheme_choices() -> list[tuple[str, str]]:
    """``(id, label)`` pairs for settings combos."""
    return [(sid, TERMINAL_SCHEMES[sid]["label"]) for sid in scheme_ids()]


def get_scheme(sid: str | None) -> dict:
    """Return the scheme for ``sid``, falling back to the default."""
    if sid in TERMINAL_SCHEMES:
        return TERMINAL_SCHEMES[sid]
    return TERMINAL_SCHEMES[DEFAULT_SCHEME]


# ----------------------------------------------------------------------
# Contrast helpers (WCAG relative luminance; used by tests + UI hints)
# ----------------------------------------------------------------------
def _channel_luminance(c: int) -> float:
    v = c / 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.2126 * _channel_luminance(r) + 0.7152 * _channel_luminance(g) + 0.0722 * _channel_luminance(b)


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` colors (1..21)."""
    la, lb = relative_luminance(hex_a), relative_luminance(hex_b)
    lighter, darker = (la, lb) if la >= lb else (lb, la)
    return (lighter + 0.05) / (darker + 0.05)
