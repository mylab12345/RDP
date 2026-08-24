"""Logging with automatic secret redaction.

Secrets registered via :func:`redact_secret` are masked before anything is
written to disk, so a verbose debug log can never leak a password that flowed
through the app.
"""

from __future__ import annotations

import logging
import logging.handlers
import threading
from pathlib import Path

_LOCK = threading.Lock()
_SECRETS: list[str] = []
_LOGGER_NAME = "rdpstudio"
_configured = False

_MASK = "***REDACTED***"


_MAX_SECRETS = 256


def redact_secret(value: str | None) -> None:
    """Register a secret to be masked in all log output."""
    if not value or not isinstance(value, str) or len(value) < 4:
        return
    with _LOCK:
        if value not in _SECRETS:
            _SECRETS.append(value)
            # Bound memory if a long-lived process sees many unique secrets.
            if len(_SECRETS) > _MAX_SECRETS:
                del _SECRETS[: len(_SECRETS) - _MAX_SECRETS]


def forget_secrets() -> None:
    with _LOCK:
        _SECRETS.clear()


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        with _LOCK:
            for secret in _SECRETS:
                if secret in msg:
                    msg = msg.replace(secret, _MASK)
        record.msg = msg
        record.args = ()
        return True


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)


def setup_logging(log_dir: Path, verbose: bool = False) -> None:
    """Rotating file log + console log, both redacted."""
    global _configured
    if _configured:
        return
    root = logging.getLogger(_LOGGER_NAME)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "rdpstudio.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(_RedactingFilter())

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    console.addFilter(_RedactingFilter())

    root.addHandler(file_handler)
    root.addHandler(console)
    _configured = True
