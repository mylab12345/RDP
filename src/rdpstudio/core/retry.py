"""Retry with exponential backoff + jitter for transient transfer failures.

Pure Python (no Qt): usable from worker threads, engines and tests alike.

A retryable failure is a *transient transport* problem — a reset connection,
a dropped channel, a timeout — never an authentication error, a permission
denial or a missing file. :func:`is_transient` encodes that distinction so
callers retry only what a retry could plausibly fix.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """How many attempts with what spacing.

    ``attempts`` counts the *total* tries (1 = no retry). Delays grow as
    ``base_delay * backoff ** (n-1)`` capped at ``max_delay``, plus uniform
    jitter in ``[0, jitter]`` so a fleet of clients does not retry in
    lockstep (thundering herd).
    """

    attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    backoff: float = 2.0
    jitter: float = 0.25

    def delay_for(self, attempt: int) -> float:
        """Delay *before* attempt number ``attempt`` (1-based, ≥1)."""
        attempt = max(1, int(attempt))
        delay = self.base_delay * (self.backoff ** (attempt - 1))
        delay = min(delay, self.max_delay)
        if self.jitter > 0:
            delay += random.uniform(0.0, self.jitter)
        return max(0.0, delay)


# Substrings (lowercased) of exception messages that indicate a transient
# transport problem rather than a permanent failure.
_TRANSIENT_MARKERS = (
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "connection lost",
    "connection closed",
    "broken pipe",
    "eof",
    "socket is closed",
    "channel closed",
    "no existing session",
    "transport",
    "temporarily",
    "try again",
    "network is unreachable",
    "network unreachable",
    "host is down",
)


def _type_names(exc: BaseException) -> list[str]:
    return [c.__name__ for c in type(exc).__mro__]


def is_transient(exc: BaseException) -> bool:
    """True when ``exc`` looks like a transient transport failure.

    Network-level errors (``OSError``/``IOError``, ``EOFError``,
    ``TimeoutError``) and paramiko transport/channel errors are transient;
    authentication, permission and not-found errors are not.
    """
    # Permanent by type — never retry these.
    permanent_types = {
        "AuthenticationException",
        "BadAuthenticationType",
        "PasswordRequiredException",
        "PartialAuthentication",
        "PermissionError",
        "FileNotFoundError",
        "IsADirectoryError",
        "NotADirectoryError",
        "SSHException",  # paramiko base is too broad; refined below by message
    }
    names = _type_names(exc)
    # paramiko.SSHException itself is ambiguous (auth vs transport), so only
    # the message markers decide for it; other permanent types short-circuit.
    for name in names:
        if name in permanent_types and name != "SSHException":
            # An OSError subclass that is also permanent (e.g. PermissionError
            # subclasses OSError) must win over the transient OSError rule.
            return False
    if isinstance(exc, (TimeoutError, EOFError, ConnectionError)):
        return True
    msg = str(exc).lower()
    if any(marker in msg for marker in _TRANSIENT_MARKERS):
        return True
    # Bare OSError without a permanent errno and without a recognized
    # message is treated as transient (reset sockets, etc.).
    if isinstance(exc, OSError):
        import errno as _errno

        permanent_errnos = {
            _errno.EACCES, _errno.EPERM, _errno.ENOENT, _errno.EISDIR,
            _errno.ENOTDIR, _errno.EEXIST, _errno.ENOTEMPTY, _errno.ELOOP,
            _errno.ENAMETOOLONG, _errno.EFBIG, _errno.ENOSPC, _errno.EROFS,
        }
        if exc.errno in permanent_errnos:
            return False
        return True
    return False


def retry_call(policy: RetryPolicy, func, *args, sleep=time.sleep, **kwargs):
    """Call ``func`` until it succeeds or the policy is exhausted.

    Only :func:`is_transient` failures are retried; anything else raises
    immediately. The last transient failure raises when attempts run out.
    ``sleep`` is injectable so tests never wait.
    """
    attempts = max(1, int(policy.attempts))
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — classification decides
            last = exc
            if attempt >= attempts or not is_transient(exc):
                raise
            sleep(policy.delay_for(attempt))
    assert last is not None  # unreachable; keeps type checkers calm
    raise last
