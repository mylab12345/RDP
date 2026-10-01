"""Shared session-logging behaviour for the terminal widgets.

Both terminal renderers — the portable pyte/Qt :class:`~rdpstudio.ui.terminal.
TerminalView` and the optional native QTermWidget backend in
:mod:`rdpstudio.ui.native_terminal` — offer the same "log this session to a
file" feature with byte-identical semantics.  Keeping two copies of it meant
every fix (and the file-handle leak fixed here) had to be made twice, so the
behaviour lives in one mixin instead.

The escape-sequence filters are compiled once at import time: ``_log_output``
runs on the terminal's hot output path, and re-parsing the patterns for every
PTY burst is pure overhead.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import IO

__all__ = ["SessionLogMixin", "strip_ansi"]

# CSI / SGR and friends: ESC [ <params> <final byte>.
_CSI_RE = re.compile(r"\x1b\[[0-9;?<=>!\"#$%&'()*+,\-./ ]*[@-~]")
# OSC strings: ESC ] ... terminated by BEL or ST.
_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)")

_BANNER_TIME = "%Y-%m-%d %H:%M:%S"


def strip_ansi(text: str) -> str:
    """Return ``text`` without CSI/OSC escape sequences, for readable logs."""
    return _OSC_RE.sub("", _CSI_RE.sub("", text))


class SessionLogMixin:
    """Append-only session logging shared by the terminal widgets.

    Hosts must initialise the two slots in their ``__init__``::

        self._log_file = None
        self._log_path = None
    """

    _log_file: IO[str] | None
    _log_path: Path | None

    # -- lifecycle ---------------------------------------------------------
    def start_logging(self, path: str | Path) -> None:
        """Log all terminal output to a local text/log file.

        Any log already running is closed first, so calling this twice never
        strands a file handle.
        """
        self.stop_logging()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        handle = open(p, "a", encoding="utf-8", buffering=1)
        try:
            handle.write(f"\n--- KB-Remote Session Log Started: {time.strftime(_BANNER_TIME)} ---\n")
        except Exception:
            # A banner we cannot write means a log we cannot write: do not
            # leave a half-open handle behind.
            handle.close()
            raise
        self._log_file = handle
        self._log_path = p

    def stop_logging(self) -> None:
        """Close the active log, if any. Always releases the file handle."""
        handle = self._log_file
        if handle is None:
            return
        # Clear the slots first: `_log_output` must stop writing even if the
        # closing banner below raises.
        self._log_file = None
        self._log_path = None
        try:
            handle.write(f"\n--- KB-Remote Session Log Ended: {time.strftime(_BANNER_TIME)} ---\n")
        except Exception:  # noqa: BLE001 — a failed banner must not leak the handle
            pass
        finally:
            try:
                handle.close()
            except Exception:  # noqa: BLE001 — teardown must never raise
                pass

    # -- queries -----------------------------------------------------------
    def is_logging(self) -> bool:
        return self._log_file is not None

    def log_path(self) -> Path | None:
        return self._log_path

    # -- output ------------------------------------------------------------
    def _log_output(self, data: bytes) -> None:
        """Append one PTY burst to the log with escape sequences stripped."""
        handle = self._log_file
        if handle is None:
            return
        try:
            handle.write(strip_ansi(data.decode("utf-8", "replace")))
        except Exception:  # noqa: BLE001 — logging must never break the session
            pass
