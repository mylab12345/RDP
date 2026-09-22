"""Session store: JSON persistence with atomic writes.

Format::

    {"format": 1, "groups": [...], "sessions": [{...}, ...]}

Vault secrets are never stored here — the store holds only references to
vault entries (``credential_id``). The one deliberate exception is a plain
password the user explicitly saves on a session (the simple no-vault flow);
it is written as-is to the local sessions file and stripped from exports.
"""

from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path

from .log import get_logger
from .models import Session, new_id
from .persistence import atomic_write_text

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
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                log.exception("corrupt sessions file %s; starting empty", self.path)
                return
            if not isinstance(data, dict):
                log.error("sessions file %s is not a JSON object; starting empty", self.path)
                return
            groups = data.get("groups", [])
            if isinstance(groups, list):
                # Preserve file order while repairing duplicate/corrupt names.
                self._groups = list(
                    dict.fromkeys(g for g in groups if isinstance(g, str) and g)
                )
            raw_sessions = data.get("sessions", [])
            if not isinstance(raw_sessions, list):
                return
            for raw in raw_sessions:
                if not isinstance(raw, dict):
                    continue
                try:
                    s = Session.from_dict(raw)
                    if s.id:
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
        """Compatibility wrapper around the shared durable writer."""
        # This file can hold explicitly saved plain-text session passwords,
        # so the shared writer publishes it as 0600 and never exposes a
        # partially serialized replacement.
        atomic_write_text(self.path, text, prefix=".sessions-", suffix=".tmp")

    # ------------------------------------------------------------------
    def sessions(self) -> list[Session]:
        """Return detached session copies sorted for presentation."""
        with self._lock:
            ordered = sorted(self._sessions.values(), key=lambda s: s.display_name().lower())
            return [copy.deepcopy(session) for session in ordered]

    def get(self, session_id: str) -> Session | None:
        """Return a detached session copy owned by the caller."""
        with self._lock:
            current = self._sessions.get(session_id)
            return copy.deepcopy(current) if current is not None else None

    def get_copy(self, session_id: str) -> Session | None:
        """Compatibility alias for :meth:`get`."""
        return self.get(session_id)

    def update(self, session_id: str, mutator) -> Session | None:
        """Atomically mutate one session with snapshot → save → commit semantics.

        The mutator receives a detached copy. If it raises, or if the
        subsequent save fails, in-memory state is left untouched (unlike
        mutating ``get()`` results in place and then calling ``upsert()``).
        Returns a detached copy of the committed session, or None if the id
        is unknown. The session id cannot be changed by the mutator.
        """
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None:
                return None
            candidate = copy.deepcopy(current)
            mutator(candidate)  # raises ⇒ no state change
            candidate.id = session_id
            candidate.updated_at = time.time()
            snapshot_groups = list(self._groups)
            self._sessions[session_id] = candidate
            if candidate.group and candidate.group not in self._groups:
                self._groups.append(candidate.group)
            try:
                self.save()
            except Exception:
                self._sessions[session_id] = current
                self._groups = snapshot_groups
                raise
            return copy.deepcopy(candidate)

    def upsert(self, session: Session) -> None:
        with self._lock:
            owned = copy.deepcopy(session)
            owned.updated_at = time.time()
            # Snapshot what we are about to change so a failed save can be
            # rolled back (same transactional contract as update()/delete():
            # memory must never run ahead of disk).
            had_previous = owned.id in self._sessions
            previous = self._sessions.get(owned.id)
            snapshot_groups = list(self._groups)
            self._sessions[owned.id] = owned
            if owned.group and owned.group not in self._groups:
                self._groups.append(owned.group)
            try:
                self.save()
            except Exception:
                if had_previous:
                    self._sessions[owned.id] = previous
                else:
                    self._sessions.pop(owned.id, None)
                self._groups = snapshot_groups
                raise

    def delete(self, session_id: str) -> None:
        with self._lock:
            removed = self._sessions.pop(session_id, None)
            if removed is not None:
                try:
                    self.save()
                except Exception:
                    # Memory must never run ahead of disk: restore the
                    # deleted session so a failed save can't silently lose it.
                    self._sessions[session_id] = removed
                    raise

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
                if new in self._groups:
                    # Target group already exists: merge into it instead of
                    # ending up with the same group listed twice.
                    self._groups.remove(old)
                else:
                    self._groups[self._groups.index(old)] = new
            elif new not in self._groups:
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
        """Bulk import without mutating inputs or replacing saved sessions.

        Returns the number imported.  Conflicting ids always receive a fresh
        id; when ``on_conflict`` is ``"rename"``, names receive a stable,
        unique ``(imported N)`` suffix even across repeated imports.
        """
        added = 0
        with self._lock:
            existing_names = {s.display_name() for s in self._sessions.values()}
            for source in sessions:
                if not isinstance(source, Session):
                    continue
                # The store owns imported objects.  Without this copy, a
                # caller retaining ``source`` could silently mutate persisted
                # state after the import returned.
                session = copy.deepcopy(source)
                # An import must never silently replace an existing session:
                # exports (and third-party files) carry their own ids, so a
                # colliding id gets a fresh one instead of overwriting.
                while not session.id or session.id in self._sessions:
                    session.id = new_id()
                name = session.display_name()
                if name in existing_names and on_conflict == "rename":
                    session.name = self._unique_import_name(name, existing_names)
                self._sessions[session.id] = session
                existing_names.add(session.display_name())
                if session.group and session.group not in self._groups:
                    self._groups.append(session.group)
                added += 1
            self.save()
        return added

    @staticmethod
    def _unique_import_name(name: str, existing_names: set[str]) -> str:
        candidate = f"{name} (imported)"
        if candidate not in existing_names:
            return candidate
        index = 2
        while f"{name} (imported {index})" in existing_names:
            index += 1
        return f"{name} (imported {index})"

    def jump_hops(self, session: Session, *, max_hops: int = 16) -> list[Session]:
        """Return the ProxyJump chain for ``session``, stopping on cycles.

        The starting session is not included. Missing / non-SSH hops are
        ignored. ``max_hops`` is a hard ceiling so a corrupt file cannot
        walk forever even if ids somehow collide.
        """
        hops: list[Session] = []
        seen: set[str] = {session.id} if session.id else set()
        current = session
        for _ in range(max(0, int(max_hops))):
            jid = current.jump_session_id
            if not jid or jid in seen:
                break
            nxt = self.get(jid)
            if nxt is None or nxt.protocol != "ssh":
                break
            hops.append(nxt)
            if nxt.id:
                seen.add(nxt.id)
            current = nxt
        return hops

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
