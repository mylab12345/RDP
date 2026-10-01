"""Collision-free display names for copied and imported records.

Sessions and snippets both need "give me a name like this one that is not
taken yet" when a record is duplicated or pulled in from a file.  The three
hand-rolled copies of that loop have been replaced by :func:`unique_name`, so
the numbering convention is defined exactly once.

The convention is::

    "Web server"              -> "Web server (copy)"
    ... already taken         -> "Web server (copy 2)", "(copy 3)", ...
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["COPY_SUFFIX", "IMPORT_SUFFIX", "unique_name"]

COPY_SUFFIX = "copy"
IMPORT_SUFFIX = "imported"


def unique_name(name: str, existing: Iterable[str], suffix: str = COPY_SUFFIX) -> str:
    """Return ``"<name> (<suffix>)"``, numbered up until it is unused.

    ``existing`` is any iterable of names already in use; it is materialised
    into a set so callers may pass a generator and so membership stays O(1)
    while the counter walks upwards.
    """
    taken = set(existing)
    candidate = f"{name} ({suffix})"
    if candidate not in taken:
        return candidate
    index = 2
    while f"{name} ({suffix} {index})" in taken:
        index += 1
    return f"{name} ({suffix} {index})"
