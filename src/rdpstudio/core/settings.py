"""Application settings (appearance, terminal, security defaults)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .coerce import as_bool, as_float, as_int, as_text
from .crypto import MAX_KDF_ITERATIONS
from .persistence import atomic_write_text

# Theme ids accepted in settings.json. MobaXterm look is the default.
THEME_CHOICES: tuple[tuple[str, str], ...] = (
    ("mobaxterm", "MobaXterm — light gray chrome · Windows blue (default)"),
    ("dark", "MobaXterm Dark — charcoal chrome · Windows blue"),
    ("graphite", "Graphite — warm gray · blue accent"),
    ("nord", "Nord — arctic · polar night & frost"),
    ("dracula", "Dracula — violet night · pink & cyan"),
    ("light", "Light — paper white · forest green"),
    ("forest", "Forest — deep pine · moss & leaf"),
    ("ocean", "Ocean — deep teal · cyan"),
    ("sunset", "Sunset — dusk · warm coral & amber"),
    ("aurora", "Aurora — deep teal · mint & lavender"),
    ("meadow", "Meadow — sage & cream · airy light"),
    ("desert", "Desert — sand & clay · warm"),
    ("contrast", "High contrast — pure black & white · accessibility"),
)
THEME_IDS = {tid for tid, _ in THEME_CHOICES}
DARK_THEMES = {
    "dark", "graphite", "nord", "dracula", "forest", "ocean", "sunset",
    "aurora", "contrast",
}

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


# Defaults for the built-in SFTP share server. Kept here so the settings UI,
# the server and the tests agree on one value.
SHARE_DEFAULT_BIND = "0.0.0.0"
SHARE_DEFAULT_PORT = 2222
SHARE_DEFAULT_USER = "kbshare"


@dataclass
class Settings:
    # appearance
    theme: str = "mobaxterm"  # see THEME_IDS
    density: str = "comfortable"  # comfortable | compact
    toolbar_labels: bool = True  # icon+label vs icon-only toolbar
    animations: bool = True  # disable for reduced motion
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

    # file sharing — the built-in SFTP share server (see
    # rdpstudio.tools.share_server). Off by default: it is a real network
    # listener, so it is only ever bound by explicit user action.
    share_server_enabled: bool = False
    share_server_autostart: bool = False  # start the listener when the app opens
    share_server_bind: str = SHARE_DEFAULT_BIND
    share_server_port: int = SHARE_DEFAULT_PORT
    share_server_user: str = SHARE_DEFAULT_USER
    # PBKDF2-HMAC-SHA256 hash (``pbkdf2-sha256$iters$salt$hash``) — the
    # plaintext is never written to disk.
    share_server_password: str = ""
    share_server_writable: bool = True
    # Global shares offered to every machine: [{"name", "path", "enabled"}].
    share_server_shares: list = field(default_factory=list)

    # window
    geometry: dict = field(default_factory=dict)
    # command palette: recently executed commands (titles, newest first)
    palette_recents: list = field(default_factory=list)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: object) -> Settings:
        if not isinstance(d, dict):
            return cls()
        valid = {f.name for f in fields(cls)}
        kwargs = {key: value for key, value in d.items() if key in valid}
        try:
            s = cls(**kwargs)
        except TypeError:
            s = cls()

        # Coerce/repair fields that can arrive as garbage from a hand-edited
        # or half-written file — a bad value must never crash startup.
        s.font_size = as_int(s.font_size, 10, minimum=6)
        s.scrollback_lines = as_int(s.scrollback_lines, 5000, minimum=200)
        s.default_keepalive = as_int(s.default_keepalive, 30, minimum=5)
        s.reconnect_max_attempts = as_int(s.reconnect_max_attempts, 12, minimum=1)
        s.reconnect_base_delay = as_float(s.reconnect_base_delay, 1.5, minimum=0.2)
        s.reconnect_max_delay = as_float(s.reconnect_max_delay, 60.0, minimum=0.2)
        s.vault_autolock_minutes = as_int(s.vault_autolock_minutes, 15, minimum=0)
        s.kdf_iterations = as_int(
            s.kdf_iterations,
            310_000,
            minimum=100_000,
            maximum=MAX_KDF_ITERATIONS,
        )

        s.theme = as_text(s.theme, "mobaxterm")
        s.density = as_text(s.density, "comfortable")
        s.font_family = as_text(s.font_family)
        s.cursor_style = as_text(s.cursor_style, "block")
        s.terminal_backend = as_text(s.terminal_backend, "auto")
        s.host_key_policy = as_text(s.host_key_policy, "accept-new")
        s.rdp_client = as_text(s.rdp_client, "auto")
        s.default_download_dir = as_text(s.default_download_dir)

        if s.theme not in THEME_IDS:
            s.theme = "mobaxterm"
        if s.density not in ("comfortable", "compact"):
            s.density = "comfortable"
        if s.host_key_policy not in ("accept-new", "strict"):
            s.host_key_policy = "accept-new"
        if s.rdp_client not in ("auto", "embedded", "external"):
            s.rdp_client = "auto"
        if s.cursor_style not in ("block", "underline", "bar"):
            s.cursor_style = "block"
        if s.terminal_backend not in ("auto", "native", "pyte"):
            s.terminal_backend = "auto"

        bool_defaults = {
            "toolbar_labels": True,
            "animations": True,
            "copy_on_select": True,
            "paste_on_middle_click": True,
            "confirm_multiline_paste": True,
            "bell_flash": True,
            "default_auto_reconnect": True,
        }
        for name, default in bool_defaults.items():
            setattr(s, name, as_bool(getattr(s, name), default))

        from .shares import shares_from_dicts

        s.share_server_enabled = as_bool(s.share_server_enabled, False)
        s.share_server_autostart = as_bool(s.share_server_autostart, False)
        s.share_server_writable = as_bool(s.share_server_writable, True)
        s.share_server_bind = as_text(s.share_server_bind, SHARE_DEFAULT_BIND) or SHARE_DEFAULT_BIND
        s.share_server_user = (as_text(s.share_server_user, SHARE_DEFAULT_USER) or SHARE_DEFAULT_USER).strip()
        s.share_server_port = as_int(
            s.share_server_port, SHARE_DEFAULT_PORT, minimum=1, maximum=65535
        )
        s.share_server_password = as_text(s.share_server_password)
        s.share_server_shares = [sh.to_dict() for sh in shares_from_dicts(s.share_server_shares)]

        if not isinstance(s.palette_recents, list):
            s.palette_recents = []
        s.palette_recents = [t for t in s.palette_recents if isinstance(t, str)][:8]
        if not isinstance(s.geometry, dict):
            s.geometry = {}
        return s

    @classmethod
    def load(cls, path: Path) -> Settings:
        try:
            if path.exists():
                return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
        return cls()

    def save(self, path: Path) -> None:
        atomic_write_text(
            path,
            json.dumps(self.to_dict(), indent=2),
            prefix=".settings-",
        )
