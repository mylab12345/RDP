"""Application settings (appearance, terminal, security defaults)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

# Theme ids accepted in settings.json. Beautiful natural global theme — 2026 bento design.
THEME_CHOICES: tuple[tuple[str, str], ...] = (
    ("dark", "🌙 Midnight — slate & mint · natural dark"),
    ("light", "☀️ Daylight — warm paper & forest · natural light"),
    ("forest", "🌲 Forest — deep pine & moss · vibrant leaf"),
    ("ocean", "🌊 Ocean — Atlantic deep teal · cyan"),
    ("sunset", "🌅 Sunset — terracotta dusk · warm coral"),
    ("aurora", "✨ Aurora — northern lights · mint & lavender"),
    ("meadow", "🌾 Meadow — sage & cream · airy light"),
    ("desert", "🏜️ Desert — sand & clay · sun-baked warm"),
)
THEME_IDS = {tid for tid, _ in THEME_CHOICES}
DARK_THEMES = {"dark", "forest", "ocean", "sunset", "aurora"}

# Curated terminal typefaces (system-installed only; nothing is bundled).
FONT_PRESETS: tuple[str, ...] = (
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Nimbus Mono L",
    "FreeMono",
    "Noto Sans Mono",
    "Ubuntu Mono",
    "JetBrains Mono",
    "JetBrains Mono NL",
    "Cascadia Code",
    "Cascadia Mono",
    "Fira Code",
    "Fira Mono",
    "Source Code Pro",
    "IBM Plex Mono",
    "Hack",
    "Inconsolata",
    "Roboto Mono",
    "PT Mono",
    "Anonymous Pro",
    "Cousine",
    "Droid Sans Mono",
    "Go Mono",
    "Iosevka",
    "Iosevka Term",
    "Input Mono",
    "Menlo",
    "Monaco",
    "SF Mono",
    "Andale Mono",
    "Consolas",
    "Lucida Console",
    "Lucida Sans Typewriter",
    "Courier New",
    "Courier",
    "Monospace",
)


def _as_int(value, default: int, minimum: int) -> int:
    """Best-effort int coercion that never raises (settings may be corrupt)."""
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = default
    return max(minimum, out)


def _as_float(value, default: float, minimum: float) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = default
    if out != out or out == float("inf") or out == float("-inf"):
        out = default
    return max(minimum, out)


@dataclass
class Settings:
    # appearance
    theme: str = "dark"  # see THEME_IDS
    font_family: str = ""  # auto-detect when empty
    font_size: int = 10  # points

    # terminal
    scrollback_lines: int = 5000
    copy_on_select: bool = True
    paste_on_middle_click: bool = True
    confirm_multiline_paste: bool = True
    cursor_style: str = "block"  # block | underline | bar
    bell_flash: bool = True
    # automatic = native QTermWidget on a displayed Linux desktop when
    # installed, otherwise the pure-Python pyte renderer.  ``native`` and
    # ``pyte`` are useful explicit diagnostics choices.
    terminal_backend: str = "auto"  # auto | native | pyte

    # connection
    default_keepalive: int = 30
    default_auto_reconnect: bool = True
    reconnect_max_attempts: int = 12
    reconnect_base_delay: float = 1.5
    reconnect_max_delay: float = 60.0
    # accept-new (TOFU) | strict
    host_key_policy: str = "accept-new"
    # RDP display: auto (built-in when possible) | embedded | external
    rdp_client: str = "auto"

    # security
    vault_autolock_minutes: int = 15
    kdf_iterations: int = 310_000  # OWASP 2023 guidance for PBKDF2-SHA256

    # files
    default_download_dir: str = ""

    # window
    geometry: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Settings:
        valid = {f.name for f in fields(cls)}
        kwargs = {}
        for k, v in (d or {}).items():
            if k in valid:
                kwargs[k] = v
        try:
            s = cls(**kwargs)
        except TypeError:
            s = cls()
        # Coerce/repair fields that can arrive as garbage from a hand-edited
        # or half-written file — a bad value must never crash startup.
        s.font_size = _as_int(s.font_size, 10, minimum=6)
        s.scrollback_lines = _as_int(s.scrollback_lines, 5000, minimum=200)
        s.default_keepalive = _as_int(s.default_keepalive, 30, minimum=5)
        s.reconnect_max_attempts = _as_int(s.reconnect_max_attempts, 12, minimum=1)
        s.reconnect_base_delay = _as_float(s.reconnect_base_delay, 1.5, minimum=0.2)
        s.reconnect_max_delay = _as_float(s.reconnect_max_delay, 60.0, minimum=0.2)
        s.vault_autolock_minutes = _as_int(s.vault_autolock_minutes, 15, minimum=0)
        s.kdf_iterations = _as_int(s.kdf_iterations, 310_000, minimum=100_000)
        if s.theme not in THEME_IDS:
            s.theme = "dark"
        if s.host_key_policy not in ("accept-new", "strict"):
            s.host_key_policy = "accept-new"
        if s.rdp_client not in ("auto", "embedded", "external"):
            s.rdp_client = "auto"
        if s.cursor_style not in ("block", "underline", "bar"):
            s.cursor_style = "block"
        if s.terminal_backend not in ("auto", "native", "pyte"):
            s.terminal_backend = "auto"
        if not isinstance(s.geometry, dict):
            s.geometry = {}
        return s

    @classmethod
    def load(cls, path: Path) -> Settings:
        try:
            if path.exists():
                return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".settings-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(self.to_dict(), indent=2))
            os.replace(tmp, path)
        except BaseException:
            # Never leave a stray .settings-XXXX temp file behind on error.
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
