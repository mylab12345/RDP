"""Reconcile a save dialog's selected type filter with the typed filename.

``QFileDialog.getSaveFileName`` returns the filter the user picked alongside
the path, but it does *not* append the matching extension when the user typed
a bare name.  Export code that then branches on ``path.endswith(".csv")``
silently writes the wrong format: pick "CSV", type ``results``, get JSON.

:func:`apply_selected_suffix` closes that gap so every exporter can keep its
simple extension-based dispatch.
"""

from __future__ import annotations

import re

__all__ = ["apply_selected_suffix", "suffixes_in_filter"]

_GLOB_RE = re.compile(r"\*(\.[A-Za-z0-9_]+)")


def suffixes_in_filter(selected_filter: str) -> list[str]:
    """Extensions named by a Qt filter string, e.g. ``"CSV (*.csv)"``.

    Returns them lower-cased and dot-prefixed, in the order they appear.
    ``"*"`` / ``"*.*"`` wildcards yield nothing, since they impose no format.
    """
    return [m.group(1).lower() for m in _GLOB_RE.finditer(selected_filter or "")]


def apply_selected_suffix(path: str, selected_filter: str) -> str:
    """Return ``path`` with the filter's extension applied when it is missing.

    An explicit extension the user typed always wins when the filter allows
    it; otherwise the filter's first extension is appended. A path that has
    some *other* extension is left untouched — the user was explicit, and
    silently renaming their file would be worse than the mismatch.
    """
    if not path:
        return path
    suffixes = suffixes_in_filter(selected_filter)
    if not suffixes:
        return path
    lowered = path.lower()
    if any(lowered.endswith(sfx) for sfx in suffixes):
        return path
    # Only append when the name carries no extension at all; respect a
    # deliberate, different one.
    tail = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if "." in tail.lstrip("."):
        return path
    return path + suffixes[0]
