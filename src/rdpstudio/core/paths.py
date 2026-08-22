"""Filesystem layout for RDP Studio.

All application state lives under a single per-user directory so it is easy to
back up, and easy to redirect for tests (``RDPSTUDIO_HOME``).

Linux:    ~/.config/rdpstudio       (honours $XDG_CONFIG_HOME)
Windows:  %APPDATA%/RDPStudio
macOS:    ~/Library/Application Support/RDPStudio
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

_ENV_OVERRIDE = "RDPSTUDIO_HOME"


def _base_dir() -> Path:
    override = os.environ.get(_ENV_OVERRIDE)
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "RDPStudio"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "RDPStudio"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "rdpstudio"


def _secure_mkdir(path: Path) -> Path:
    """Create ``path`` (and parents) private to the current user.

    State files hold saved passwords, private keys and host-key trust, so the
    directory must never be group/world readable (CWE-276). Existing
    directories are tightened too — upgrading from an older, laxer version
    should not leave secrets exposed.
    """
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        try:
            if stat.S_IMODE(path.stat().st_mode) & 0o077:
                path.chmod(0o700)
        except OSError:  # pragma: no cover - unusual filesystems
            pass
    return path


def app_dir() -> Path:
    """Root state directory (created on demand, private to this user)."""
    return _secure_mkdir(_base_dir())


def sessions_file() -> Path:
    return app_dir() / "sessions.json"


def settings_file() -> Path:
    return app_dir() / "settings.json"


def vault_file() -> Path:
    return app_dir() / "vault.bin"


def known_hosts_file() -> Path:
    return app_dir() / "known_hosts"


def keys_dir() -> Path:
    return _secure_mkdir(app_dir() / "keys")


def logs_dir() -> Path:
    return _secure_mkdir(app_dir() / "logs")


def downloads_dir() -> Path:
    return _secure_mkdir(app_dir() / "downloads")


def cache_dir() -> Path:
    return _secure_mkdir(app_dir() / "cache")


def snippets_file() -> Path:
    return app_dir() / "snippets.json"

