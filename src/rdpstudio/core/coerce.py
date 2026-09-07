"""Defensive scalar coercion for data loaded from user-controlled files.

JSON guarantees only broad value types, not the schema expected by the
application.  Keeping the coercion rules here prevents the settings, session,
and vault models from drifting apart when they repair hand-edited or partially
migrated state files.
"""

from __future__ import annotations

import math
from typing import Any

_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
_FALSE_STRINGS = frozenset({"0", "false", "no", "off", ""})


def as_bool(value: Any, default: bool = False) -> bool:
    """Return a predictable boolean without treating ``"false"`` as true.

    Native booleans are preserved.  The common textual spellings and numeric
    values are accepted for compatibility with hand-written configuration;
    containers and unknown strings fall back to ``default``.
    """
    if isinstance(value, bool):
        return value
    # Preserve the long-standing JSON-null behaviour (bool(None) is false)
    # while avoiding Python's surprising bool("false") result.
    if value is None:
        return False
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_STRINGS:
            return True
        if normalized in _FALSE_STRINGS:
            return False
        return default
    if isinstance(value, (int, float)):
        try:
            return bool(value) if math.isfinite(value) else default
        except TypeError:  # defensive for unusual numeric subclasses
            return default
    return default


def as_int(
    value: Any,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Best-effort bounded integer coercion that never raises."""
    try:
        # bool is intentionally accepted as 0/1, matching json/int behaviour.
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def as_float(
    value: Any,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Best-effort finite, bounded floating-point coercion."""
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        result = default
    if not math.isfinite(result):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    if maximum is not None:
        result = min(maximum, result)
    return result


def as_text(value: Any, default: str = "") -> str:
    """Keep strings and reject structured JSON values.

    Converting a list or mapping with ``str`` often postpones a startup crash
    until the value reaches Qt or an OS API.  Configuration text fields are
    therefore repaired to their default instead.
    """
    return value if isinstance(value, str) else default
