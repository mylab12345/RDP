"""Application settings (appearance, terminal, security defaults)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .coerce import as_bool, as_float, as_int, as_text
from .crypto import MAX_KDF_ITERATIONS
from .persistence import atomic_write_text

# Theme ids accepted in settings.json. Studio Dark is the default visual
# refresh; the MobaXterm themes and other established palettes remain
# selectable for users who prefer the classic look. Unknown ids fall back
# to DEFAULT_THEME on load, so removing a theme never breaks configs.
THEME_CHOICES: tuple[tuple[str, str], ...] = (
    ("studio_dark", "Studio Dark — deep slate · mint accent (default)"),
    ("mobaxterm_dark", "MobaXterm Dark — charcoal chrome · Windows blue"),
    ("mobaxterm", "MobaXterm — light gray chrome · Windows blue"),
    ("midnight", "Midnight — deep navy night · sky accent"),
    ("dracula", "Dracula — violet night · pink & cyan"),
    ("ocean", "Ocean — deep teal · cyan"),
    ("contrast", "High contrast — pure black & white · accessibility"),
)
THEME_IDS = {tid for tid, _ in THEME_CHOICES}
DARK_THEMES = {"studio_dark", "mobaxterm_dark", "midnight", "dracula", "ocean", "contrast"}
# Fallback for a missing/unknown theme id (hand-edited or older settings.json).
DEFAULT_THEME = "studio_dark"

_HEX_COLOR_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def normalize_hex_color(value: object) -> str:
    """Return a canonical ``#rrggbb`` colour or ``""`` for invalid input."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if not _HEX_COLOR_RE.fullmatch(text):
        return ""
    if not text.startswith("#"):
        text = f"#{text}"
    return text.lower()


def _coerce_session_snapshots(value: object) -> list[dict]:
    """Repair the tab-snapshot list loaded from settings.json.

    Snapshots intentionally store only saved-session ids, not copied session
    definitions, so settings never become a second place for credentials.
    """
    if not isinstance(value, list):
        return []
    out: list[dict] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        name = as_text(raw.get("name"), "").strip()
        ids = raw.get("session_ids", [])
        if not isinstance(ids, list):
            ids = []
        session_ids: list[str] = []
        seen: set[str] = set()
        for sid in ids:
            if not isinstance(sid, str) or not sid or sid in seen:
                continue
            seen.add(sid)
            session_ids.append(sid)
            if len(session_ids) >= 20:
                break
        if not name or not session_ids:
            continue
        out.append(
            {
                "name": name[:80],
                "session_ids": session_ids,
                "created_at": as_float(raw.get("created_at"), 0.0, minimum=0.0),
            }
        )
        if len(out) >= 12:
            break
    return out


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


# Welcome-dashboard personalisation (see ui/dashboard.py). ``tiles`` lists
# the launcher-tile ids shown on the dashboard, in order; the four defaults
# keep the empty workbench minimal. Unknown ids are dropped on load.
DASHBOARD_TILE_IDS: tuple[str, ...] = (
    "new_session",
    "new_rdp",
    "local_terminal",
    "commands",
    "settings",
    "network_tools",
    "keys",
    "rdp_servers",
    "tunnels",
    "cluster",
    "activity_log",
    "support_chat",
    "onboarding",
    "feedback",
)
DASHBOARD_SECTION_KEYS: tuple[str, ...] = (
    "show_quick_connect",
    "show_actions",
    "show_recents",
    "show_shortcuts",
)
DEFAULT_DASHBOARD_LAYOUT: dict = {
    "show_quick_connect": True,
    "show_actions": True,
    "show_recents": True,
    "show_shortcuts": True,
    "tiles": ["new_session", "local_terminal", "commands", "settings"],
}


def coerce_dashboard_layout(value: object) -> dict:
    """Repair a ``dashboard_layout`` mapping loaded from settings.json.

    Missing keys fall back to the defaults, unknown tile ids are dropped,
    and an empty tile list restores the default launcher set — the dashboard
    must always be able to render something useful.
    """
    out = {
        "show_quick_connect": True,
        "show_actions": True,
        "show_recents": True,
        "show_shortcuts": True,
        "tiles": list(DEFAULT_DASHBOARD_LAYOUT["tiles"]),
    }
    if not isinstance(value, dict):
        return out
    for key in DASHBOARD_SECTION_KEYS:
        # A missing key keeps the default; an explicit null/false turns the
        # section off (as_bool's JSON-null convention).
        if key in value:
            out[key] = as_bool(value[key], True)
    raw_tiles = value.get("tiles")
    if isinstance(raw_tiles, list):
        seen: set[str] = set()
        tiles: list[str] = []
        for tid in raw_tiles:
            if not isinstance(tid, str) or tid not in DASHBOARD_TILE_IDS or tid in seen:
                continue
            seen.add(tid)
            tiles.append(tid)
            if len(tiles) >= len(DASHBOARD_TILE_IDS):
                break
        if tiles:
            out["tiles"] = tiles
    return out


@dataclass
class Settings:
    # appearance
    theme: str = DEFAULT_THEME  # see THEME_IDS
    density: str = "comfortable"  # comfortable | compact
    toolbar_labels: bool = True  # icon+label vs icon-only toolbar
    animations: bool = True  # disable for reduced motion
    # Optional app-wide accent override. Empty = use the selected theme's accent.
    accent_color: str = ""
    font_family: str = ""  # auto-detect when empty
    font_size: int = 10  # points

    # terminal
    scrollback_lines: int = 5000
    copy_on_select: bool = True
    paste_on_middle_click: bool = True
    confirm_multiline_paste: bool = True
    cursor_style: str = "block"  # block | underline | bar
    cursor_blink: bool = True
    terminal_line_spacing: int = 0  # extra pixels between terminal rows
    terminal_color_scheme: str = "mobaxterm"  # see ui.terminal_schemes
    # SSH tabs keep the remote host's native console palette by default;
    # opt in here to paint them in the selected scheme instead.
    terminal_override_remote: bool = False
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
    # SFTP browser transfer engine: sftp (default) | scp. SCP has no
    # directory listing, so browsing still uses SFTP — only the byte
    # transfer runs over the scp wire protocol.
    transfer_protocol: str = "sftp"

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
    # welcome-dashboard personalisation: visible sections + launcher tiles
    # (see DEFAULT_DASHBOARD_LAYOUT / DASHBOARD_TILE_IDS)
    dashboard_layout: dict = field(
        default_factory=lambda: coerce_dashboard_layout(None)
    )
    # command palette: recently executed commands (titles, newest first)
    palette_recents: list = field(default_factory=list)
    # recently connected session ids (newest first, capped at 10)
    recent_session_ids: list = field(default_factory=list)
    # connection frequency per saved session id (session_id -> count)
    session_connect_counts: dict = field(default_factory=dict)
    # named sets of saved session ids for restoring a working tab layout
    # [{"name": str, "session_ids": [str], "created_at": float}]
    session_snapshots: list = field(default_factory=list)
    # preferred dark theme restored when toggling back from light mode
    preferred_dark_theme: str = DEFAULT_THEME
    # onboarding & interactive guidance
    onboarding_completed: bool = False
    interactive_tooltips: bool = True
    # responsive tablet/smartphone touch layout override
    mobile_touch_mode: bool = False

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

        s.theme = as_text(s.theme, DEFAULT_THEME)
        s.density = as_text(s.density, "comfortable")
        s.accent_color = normalize_hex_color(s.accent_color)
        s.font_family = as_text(s.font_family)
        s.cursor_style = as_text(s.cursor_style, "block")
        s.terminal_backend = as_text(s.terminal_backend, "auto")
        s.terminal_color_scheme = as_text(s.terminal_color_scheme, "mobaxterm")
        s.host_key_policy = as_text(s.host_key_policy, "accept-new")
        s.rdp_client = as_text(s.rdp_client, "auto")
        s.default_download_dir = as_text(s.default_download_dir)
        s.transfer_protocol = as_text(s.transfer_protocol, "sftp")
        s.terminal_line_spacing = as_int(s.terminal_line_spacing, 0, minimum=0, maximum=12)

        if s.theme not in THEME_IDS:
            s.theme = DEFAULT_THEME
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
        if s.terminal_color_scheme not in (
            "mobaxterm", "dracula", "monokai", "nord",
            "solarized-dark", "solarized-light", "light",
        ):
            s.terminal_color_scheme = "mobaxterm"
        if s.transfer_protocol not in ("sftp", "scp"):
            s.transfer_protocol = "sftp"

        bool_defaults = {
            "toolbar_labels": True,
            "animations": True,
            "copy_on_select": True,
            "paste_on_middle_click": True,
            "confirm_multiline_paste": True,
            "cursor_blink": True,
            "terminal_override_remote": False,
            "bell_flash": True,
            "default_auto_reconnect": True,
            "onboarding_completed": False,
            "interactive_tooltips": True,
            "mobile_touch_mode": False,
        }
        for name, default in bool_defaults.items():
            setattr(s, name, as_bool(getattr(s, name), default))

        s.preferred_dark_theme = as_text(s.preferred_dark_theme, DEFAULT_THEME)
        if s.preferred_dark_theme not in DARK_THEMES:
            s.preferred_dark_theme = DEFAULT_THEME

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
        if not isinstance(s.recent_session_ids, list):
            s.recent_session_ids = []
        s.recent_session_ids = [t for t in s.recent_session_ids if isinstance(t, str)][:10]
        if not isinstance(s.session_connect_counts, dict):
            s.session_connect_counts = {}
        clean_counts: dict[str, int] = {}
        for k, v in list(s.session_connect_counts.items())[:50]:
            if isinstance(k, str) and k:
                cnt = as_int(v, 0, minimum=0)
                if cnt > 0:
                    clean_counts[k] = cnt
        s.session_connect_counts = clean_counts
        s.session_snapshots = _coerce_session_snapshots(s.session_snapshots)
        s.dashboard_layout = coerce_dashboard_layout(s.dashboard_layout)
        if not isinstance(s.geometry, dict):
            s.geometry = {}
        return s

    def touch_recent_session(self, session_id: str) -> None:
        """Record a connect: newest-first, de-duplicated, capped at 10, plus frequency."""
        if not session_id:
            return
        recents = [s for s in self.recent_session_ids if s != session_id]
        recents.insert(0, session_id)
        self.recent_session_ids = recents[:10]
        if not isinstance(self.session_connect_counts, dict):
            self.session_connect_counts = {}
        self.session_connect_counts[session_id] = int(self.session_connect_counts.get(session_id, 0) or 0) + 1
        if len(self.session_connect_counts) > 50:
            # Retain the highest-frequency entries
            top = sorted(self.session_connect_counts.items(), key=lambda kv: kv[1], reverse=True)[:50]
            self.session_connect_counts = dict(top)

    def frequent_session_ids(self, limit: int = 6) -> list[str]:
        """Return session ids ordered by frequency (highest first), then recency."""
        limit = max(1, int(limit))
        counts = self.session_connect_counts if isinstance(self.session_connect_counts, dict) else {}
        recents = list(self.recent_session_ids or [])
        all_ids = list(dict.fromkeys([*recents, *counts.keys()]))
        rec_rank = {sid: idx for idx, sid in enumerate(recents)}
        all_ids.sort(key=lambda sid: (-int(counts.get(sid, 0) or 0), rec_rank.get(sid, 999)))
        return all_ids[:limit]

    def is_dark_mode(self) -> bool:
        """Whether the active theme is a dark palette."""
        return self.theme in DARK_THEMES

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
