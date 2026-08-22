"""Filesystem layout for RDP Studio.

All application state lives under a single per-user directory so it is easy to
back up, and easy to redirect for tests (``RDPSTUDIO_HOME``).

Linux:    ~/.config/rdpstudio       (honours $XDG_CONFIG_HOME)
Windows:  %APPDATA%/RDPStudio
macOS:    ~/Library/Application Support/RDPStudio
"""

from __future__ import annotations

import os
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


def app_dir() -> Path:
    """Root state directory (created on demand)."""
    path = _base_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def sessions_file() -> Path:
    return app_dir() / "sessions.json"


def settings_file() -> Path:
    return app_dir() / "settings.json"


def vault_file() -> Path:
    return app_dir() / "vault.bin"


def known_hosts_file() -> Path:
    return app_dir() / "known_hosts"


def keys_dir() -> Path:
    path = app_dir() / "keys"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def downloads_dir() -> Path:
    path = app_dir() / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = app_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path
