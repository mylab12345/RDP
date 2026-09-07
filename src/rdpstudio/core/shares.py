"""Local folder shares exposed to remote machines.

A *share* pairs a short name with a local directory. The built-in SFTP share
server (see :mod:`rdpstudio.tools.share_server`) presents every enabled share
as a top-level directory of one virtual root, so a remote machine — a Windows
box reached over RDP, or anything else with an SFTP client — sees::

    /Tools/setup.exe          (share "Tools"  -> ~/shared/tools)
    /Builds/app-1.2.msi       (share "Builds" -> /srv/builds)

Shares come from two places:

- **global** — the defaults in *Settings → File sharing*, offered to every
  machine; and
- **session** — extras attached to one saved session, offered while that
  session's tab is open.

This module is deliberately pure (no Qt, no sockets): the name rules, the
registry and the path jail are the parts worth testing on their own.

Security note
-------------
Every path handed back by :meth:`ShareRegistry.resolve` is confined to the
real path of its share root. A client asking for ``/Tools/../../etc/passwd``
gets ``None`` — the resolution is done on *real* paths, so symlinks that point
outside a share cannot be used to escape either (CWE-22, CWE-59).
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCOPE_GLOBAL = "global"
SCOPE_SESSION = "session"

# SFTP clients address shares as the first path component, so the name has to
# survive a round trip through POSIX paths, Windows UNC paths
# (\\tsclient-style names in other tools) and SMB-ish share naming rules.
# Keep it boring: letters, digits, dash, dot and underscore.
_NAME_ALLOWED = re.compile(r"[^A-Za-z0-9._-]+")
# Names are a single path component — a separator or a dot-only name would
# either escape the virtual root or address the root itself.
_NAME_FORBIDDEN = re.compile(r"^\.+$")
_NAME_MAX = 64
MAX_SHARES = 32


class ShareError(ValueError):
    """Raised for an unusable share definition."""


@dataclass
class Share:
    """A named local directory offered to remote machines."""

    name: str = ""
    path: str = ""
    enabled: bool = True

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": self.path, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, d: object) -> Share:
        if not isinstance(d, dict):
            return cls()
        from .coerce import as_bool

        return cls(
            name=str(d.get("name") or ""),
            path=str(d.get("path") or ""),
            enabled=as_bool(d.get("enabled", True), True),
        )

    def copy(self) -> Share:
        return Share(name=self.name, path=self.path, enabled=self.enabled)


@dataclass
class ResolvedShare:
    """A share as the server actually sees it (unique name, real path)."""

    name: str
    path: Path
    scope: str
    source: str = ""  # "settings" or the session display name
    writable: bool = True

    def remote_root(self) -> str:
        """Virtual path of this share, as an SFTP client would type it."""
        return f"/{self.name}"


def sanitize_share_name(raw: str, fallback: str = "share") -> str:
    """Coerce ``raw`` into a usable share name.

    Falls back to ``fallback`` when nothing usable is left. Never raises: the
    UI calls this on every keystroke of a folder picker result.
    """
    candidate = _NAME_ALLOWED.sub("_", str(raw or "")).strip("._")
    if not candidate or _NAME_FORBIDDEN.match(candidate):
        candidate = fallback
    candidate = _NAME_ALLOWED.sub("_", candidate).strip("._") or fallback
    return candidate[:_NAME_MAX]


def share_name_from_path(path: str | Path) -> str:
    """Derive a share name from a local directory (its last component)."""
    name = Path(os.path.expanduser(str(path))).name
    return sanitize_share_name(name, fallback="share")


def validate_share(share: Share) -> Share:
    """Check a share definition and normalise its name.

    Raises :class:`ShareError` with a user-presentable message. The name is
    normalised in place so a persisted share is always servable.
    """
    if not share.name.strip():
        raise ShareError("Share name is empty.")
    if "/" in share.name or "\\" in share.name:
        raise ShareError("Share name must not contain a path separator.")
    share.name = sanitize_share_name(share.name)
    if _NAME_FORBIDDEN.match(share.name):
        raise ShareError("Share name must not be only dots.")
    if not share.path.strip():
        raise ShareError(f"Share “{share.name}” has no folder.")
    root = Path(os.path.expanduser(share.path))
    if not root.is_absolute():
        raise ShareError(f"Share “{share.name}” needs an absolute folder path.")
    if not root.exists():
        raise ShareError(f"Share “{share.name}”: folder {root} does not exist.")
    if not root.is_dir():
        raise ShareError(f"Share “{share.name}”: {root} is not a folder.")
    share.path = str(root)
    return share


class ShareRegistry:
    """Live view of the shares the server offers right now.

    The server consults this on every operation, so a share can be added or
    removed while a client is connected without restarting the listener.
    All methods are safe to call from the accept thread, the SFTP worker
    threads and the GUI thread.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._global: list[Share] = []
        self._sessions: dict[str, tuple[str, list[Share]]] = {}
        self._writable = True

    # -- population ------------------------------------------------------
    def set_global(self, shares: list[Share], writable: bool = True) -> None:
        with self._lock:
            self._global = [s.copy() for s in shares]
            self._writable = bool(writable)

    def set_session(self, session_id: str, label: str, shares: list[Share]) -> None:
        with self._lock:
            if shares:
                self._sessions[session_id] = (label or session_id, [s.copy() for s in shares])
            else:
                self._sessions.pop(session_id, None)

    def remove_session(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def set_writable(self, writable: bool) -> None:
        with self._lock:
            self._writable = bool(writable)

    def is_writable(self) -> bool:
        with self._lock:
            return self._writable

    # -- inspection ------------------------------------------------------
    def entries(self, *, include_missing: bool = False) -> list[ResolvedShare]:
        """Every enabled share, with globally-unique names.

        A later share whose name collides with an earlier one is suffixed
        (``Builds-2``) rather than hidden — silently dropping a share the user
        configured is worse than an ugly name.
        """
        with self._lock:
            raw: list[tuple[Share, str, str]] = [(s, SCOPE_GLOBAL, "settings") for s in self._global]
            for _sid, (label, shares) in self._sessions.items():
                raw.extend((s, SCOPE_SESSION, label) for s in shares if s.enabled or include_missing)
        out: list[ResolvedShare] = []
        used: set[str] = set()
        for share, scope, source in raw:
            if not share.enabled and scope == SCOPE_SESSION:
                continue
            if not share.enabled:
                continue
            name = share.name
            n = 2
            while name.lower() in used:
                name = sanitize_share_name(f"{share.name}-{n}")
                n += 1
            used.add(name.lower())
            root = Path(os.path.expanduser(share.path))
            if not include_missing and not root.is_dir():
                continue
            out.append(
                ResolvedShare(
                    name=name,
                    path=root,
                    scope=scope,
                    source=source,
                    writable=self.is_writable(),
                )
            )
        return out

    def by_name(self, name: str) -> ResolvedShare | None:
        wanted = str(name or "").strip("/").lower()
        for entry in self.entries():
            if entry.name.lower() == wanted:
                return entry
        return None

    def is_empty(self) -> bool:
        with self._lock:
            return not self._global and not self._sessions

    # -- path jail -------------------------------------------------------
    def resolve(self, client_path: str) -> tuple[ResolvedShare, Path] | None:
        """Map a client path to ``(share, real_path)`` or ``None``.

        ``None`` means "no such share" or "outside the share" — the caller
        turns that into SFTP_NO_SUCH_FILE / SFTP_PERMISSION_DENIED. The
        returned path need not exist (create/mkdir targets it).
        """
        share, parts = self._split(client_path)
        if share is None:
            return None
        root = Path(os.path.realpath(share.path))
        target = root.joinpath(*parts) if parts else root
        real = Path(os.path.realpath(target))
        if real != root and root not in real.parents:
            return None  # traversal / symlink escape
        return share, real

    def _split(self, client_path: str) -> tuple[ResolvedShare | None, tuple[str, ...]]:
        text = str(client_path or "").replace("\\", "/")
        parts = [p for p in text.split("/") if p not in ("", ".")]
        if not parts:
            return None, ()
        entry = self.by_name(parts[0])
        if entry is None:
            return None, ()
        return entry, tuple(parts[1:])

    # -- convenience -----------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Serialisable view, for logs and the UI."""
        return {
            "shares": [
                {"name": e.name, "path": str(e.path), "scope": e.scope, "source": e.source}
                for e in self.entries()
            ]
        }


def shares_from_dicts(raw: object) -> list[Share]:
    """Coerce a stored list (hand-edited JSON included) into valid shares."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[Share] = []
    for item in raw:
        share = Share.from_dict(item)
        if share.name.strip() and share.path.strip():
            share.name = sanitize_share_name(share.name)
            out.append(share)
    return out[:MAX_SHARES]


def unique_share_names(existing: list[Share], wanted: str) -> str:
    """Return ``wanted``, suffixed if a share in ``existing`` already uses it."""
    taken = {s.name.lower() for s in existing}
    if wanted.lower() not in taken:
        return wanted
    n = 2
    while f"{wanted}-{n}".lower() in taken:
        n += 1
    return f"{wanted}-{n}"


__all__ = [
    "MAX_SHARES",
    "SCOPE_GLOBAL",
    "SCOPE_SESSION",
    "ResolvedShare",
    "Share",
    "ShareError",
    "ShareRegistry",
    "sanitize_share_name",
    "share_name_from_path",
    "shares_from_dicts",
    "unique_share_names",
    "validate_share",
]
