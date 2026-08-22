"""Shared small helpers for protocol plugins."""

from __future__ import annotations

from ..core.plugin import Capabilities


def capability_set(**flags) -> Capabilities:
    defaults = dict(shell=False, sftp=False, tunnels=False, external_window=False, monitor=False)
    defaults.update(flags)
    return Capabilities(**defaults)
