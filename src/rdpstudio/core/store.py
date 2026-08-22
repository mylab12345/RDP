"""Session store: JSON persistence with atomic writes.

Format::

    {"format": 1, "groups": [...], "sessions": [{...}, ...]}

Vault secrets are never stored here — the store holds only references to
vault entries (``credential_id``). The one deliberate exception is a plain
password the user explicitly saves on a session (the simple no-vault flow);
it is written as-is to the local sessions file and stripped from exports.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .log import get_logger
from .models import Session

log = get_logger("store")

_FORMAT = 1


class SessionStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._sessions: dict[str, Session] = {}
        self._groups: list[str] = []
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        with self._lock:
            self._sessions = {}
            self._groups = []
            if not self.path.exists():
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                log.exception("corrupt sessions file %s; starting empty", self.path)
                return
            self._groups = list(data.get("groups", []))
            for raw in data.get("sessions", []):
                try:
                    s = Session.from_dict(raw)
                    self._sessions[s.id] = s
                except Exception:  # noqa: BLE001
                    log.exception("skipping corrupt session entry")

    def save(self) -> None:
        with self._lock:
            data = {
                "format": _FORMAT,
                "groups": self._groups,
                "sessions": [s.to_dict() for s in self._sessions.values()],
            }
            self._atomic_write(json.dumps(data, indent=2, ensure_ascii=False))

    def _atomic_write(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".sessions-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            # This file can hold plain-text session passwords, so it must not
            # be readable by other users (mkstemp is already 0600; make the
            # intent explicit and survive a pre-existing laxer file).
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    def sessions(self) -> list[Session]:
        with self._lock:
            return sorted(self._sessions.values(), key=lambda s: s.display_name().lower())

    def get(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def upsert(self, session: Session) -> None:
        with self._lock:
            import time

            session.updated_at = time.time()
            self._sessions[session.id] = session
            if session.group and session.group not in self._groups:
                self._groups.append(session.group)
            self.save()

    def delete(self, session_id: str) -> None:
        with self._lock:
            if self._sessions.pop(session_id, None) is not None:
                self.save()

    def duplicate(self, session_id: str) -> Session | None:
        s = self.get(session_id)
        if not s:
            return None
        dup = s.copy()
        self.upsert(dup)
        return dup

    # --- groups --------------------------------------------------------
    def groups(self) -> list[str]:
        with self._lock:
            return sorted(self._groups)

    def ensure_group(self, name: str) -> None:
        with self._lock:
            if name and name not in self._groups:
                self._groups.append(name)
                self.save()

    def rename_group(self, old: str, new: str) -> None:
        with self._lock:
            if not new or old == new:
                return
            for s in self._sessions.values():
                if s.group == old:
                    s.group = new
            if old in self._groups:
                self._groups[self._groups.index(old)] = new
            else:
                self._groups.append(new)
            self.save()

    def delete_group(self, name: str, move_to: str = "") -> None:
        """Remove a group; its sessions move to ``move_to`` (top level if empty)."""
        with self._lock:
            for s in self._sessions.values():
                if s.group == name:
                    s.group = move_to
            if name in self._groups:
                self._groups.remove(name)
            self.save()

    def import_sessions(self, sessions: list[Session], on_conflict: str = "rename") -> int:
        """Bulk import; returns number imported. Conflicting ids/names get renamed."""
        added = 0
        with self._lock:
            existing_names = {s.display_name() for s in self._sessions.values()}
            for s in sessions:
                s.id = type(s).new_id() if hasattr(type(s), "new_id") else s.id
                name = s.display_name()
                if name in existing_names and on_conflict == "rename":
                    s.name = f"{name} (imported)"
                self._sessions[s.id] = s
                existing_names.add(s.display_name())
                if s.group and s.group not in self._groups:
                    self._groups.append(s.group)
                added += 1
            self.save()
        return added

    def export_dict(self) -> dict:
        with self._lock:
            sessions = []
            for s in self._sessions.values():
                d = s.to_dict()
                d.pop("password", None)  # never leak saved passwords into exports
                sessions.append(d)
            return {
                "format": _FORMAT,
                "groups": list(self._groups),
                "sessions": sessions,
            }
