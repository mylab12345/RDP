"""Application settings (appearance, terminal, security defaults)."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class Settings:
    # appearance
    theme: str = "dark"  # dark | light
    font_family: str = ""  # auto-detect when empty
    font_size: int = 10  # points

    # terminal
    scrollback_lines: int = 5000
    copy_on_select: bool = True
    paste_on_middle_click: bool = True
    confirm_multiline_paste: bool = True
    cursor_style: str = "block"  # block | underline | bar
    bell_flash: bool = True

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
        if not s.font_size or s.font_size < 6:
            s.font_size = 10
        s.kdf_iterations = max(100_000, int(s.kdf_iterations))
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
