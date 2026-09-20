"""Pure local-path selection helpers for downloads and file browsers."""

from __future__ import annotations

from pathlib import Path


def resolve_download_start(explicit: str, configured: str, home: str) -> str:
    """First existing directory wins: explicit path → configured default → home."""
    for candidate in (explicit or "", configured or "", home or ""):
        if candidate and Path(candidate).is_dir():
            return candidate
    return home or ""


__all__ = ["resolve_download_start"]
