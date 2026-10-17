"""Real-time user and connection activity log.

Pure Python (no Qt). Records connection state changes, quick-connect actions,
file transfers, theme/accessibility updates, support chat interactions, and
feedback submissions into an in-memory ring buffer backed by
``logs/activity.jsonl`` (bounded at :data:`MAX_ACTIVITY_ENTRIES`).

Secrets and raw credentials are never stored.
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .events import EventBus
from .log import get_logger

log = get_logger("activity")

MAX_ACTIVITY_ENTRIES = 500

ACTIVITY_KINDS: tuple[str, ...] = (
    "connection",
    "session",
    "transfer",
    "ui",
    "support",
    "feedback",
    "security",
)

ACTIVITY_LEVELS: tuple[str, ...] = ("info", "good", "warn", "bad")


@dataclass
class ActivityEntry:
    """One user-visible activity or connection event."""

    ts: float = 0.0
    kind: str = "connection"
    level: str = "info"
    title: str = ""
    detail: str = ""
    session: str = ""
    protocol: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: object) -> ActivityEntry | None:
        if not isinstance(d, dict):
            return None
        try:
            ts = float(d.get("ts") or 0.0)
            kind = str(d.get("kind") or "connection").strip().lower()
            if kind not in ACTIVITY_KINDS:
                kind = "connection"
            level = str(d.get("level") or "info").strip().lower()
            if level not in ACTIVITY_LEVELS:
                level = "info"
            title = str(d.get("title") or "").strip()[:200]
            if not title:
                return None
            detail = str(d.get("detail") or "").strip()[:400]
            session = str(d.get("session") or "").strip()[:120]
            protocol = str(d.get("protocol") or "").strip().lower()[:24]
            return cls(
                ts=ts,
                kind=kind,
                level=level,
                title=title,
                detail=detail,
                session=session,
                protocol=protocol,
            )
        except (TypeError, ValueError):
            return None


class ActivityLog:
    """Thread-safe, bounded activity log with optional JSONL persistence."""

    def __init__(self, path: Path | None = None, max_entries: int = MAX_ACTIVITY_ENTRIES) -> None:
        self.path = path
        self.max_entries = max(20, int(max_entries))
        self._lock = threading.Lock()
        self._entries: deque[ActivityEntry] = deque(maxlen=self.max_entries)
        self._listeners: list[Callable[[ActivityEntry], None]] = []
        if self.path is not None:
            self._load_existing()

    def _load_existing(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return
        for line in lines[-self.max_entries :]:
            try:
                entry = ActivityEntry.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if entry is not None:
                self._entries.append(entry)

    def subscribe(self, fn: Callable[[ActivityEntry], None]) -> Callable[[], None]:
        """Register a listener invoked whenever a new entry is recorded."""
        with self._lock:
            self._listeners.append(fn)

        def _unsub() -> None:
            with self._lock:
                try:
                    self._listeners.remove(fn)
                except ValueError:
                    pass

        return _unsub

    def record(
        self,
        kind: str,
        title: str,
        detail: str = "",
        *,
        level: str = "info",
        session: str = "",
        protocol: str = "",
        ts: float | None = None,
    ) -> ActivityEntry:
        """Append one activity event and notify subscribers."""
        clean_kind = kind.strip().lower() if isinstance(kind, str) else "connection"
        if clean_kind not in ACTIVITY_KINDS:
            clean_kind = "connection"
        clean_level = level.strip().lower() if isinstance(level, str) else "info"
        if clean_level not in ACTIVITY_LEVELS:
            clean_level = "info"
        entry = ActivityEntry(
            ts=float(ts if ts is not None else time.time()),
            kind=clean_kind,
            level=clean_level,
            title=str(title or "Event").strip()[:200],
            detail=str(detail or "").strip()[:400],
            session=str(session or "").strip()[:120],
            protocol=str(protocol or "").strip().lower()[:24],
        )
        with self._lock:
            self._entries.append(entry)
            listeners = list(self._listeners)
            if self.path is not None:
                self._append_disk_locked(entry)
        for fn in listeners:
            try:
                fn(entry)
            except Exception:  # noqa: BLE001
                log.debug("activity listener error", exc_info=True)
        return entry

    def _append_disk_locked(self, entry: ActivityEntry) -> None:
        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            if len(self._entries) >= self.max_entries:
                self._compact_locked()
        except OSError as exc:
            log.debug("activity log disk write failed: %s", exc)

    def _compact_locked(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            if len(lines) <= self.max_entries:
                return
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines[-self.max_entries :]) + "\n")
        except OSError:
            pass

    def entries(
        self,
        *,
        limit: int = 100,
        kind: str = "",
        level: str = "",
        search: str = "",
    ) -> list[ActivityEntry]:
        """Return matching entries newest-first."""
        limit = max(1, min(int(limit), self.max_entries))
        kind_filter = (kind or "").strip().lower()
        level_filter = (level or "").strip().lower()
        needle = (search or "").strip().lower()
        with self._lock:
            snapshot = list(reversed(self._entries))
        out: list[ActivityEntry] = []
        for e in snapshot:
            if kind_filter and e.kind != kind_filter:
                continue
            if level_filter and e.level != level_filter:
                continue
            if needle:
                hay = f"{e.title} {e.detail} {e.session} {e.protocol} {e.kind}".lower()
                if needle not in hay:
                    continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    def summary_counts(self) -> dict[str, int]:
        """Return counts grouped by kind and level."""
        with self._lock:
            snapshot = list(self._entries)
        counts: dict[str, int] = {k: 0 for k in ACTIVITY_KINDS}
        counts["total"] = len(snapshot)
        counts["errors"] = 0
        counts["warnings"] = 0
        for e in snapshot:
            counts[e.kind] = counts.get(e.kind, 0) + 1
            if e.level == "bad":
                counts["errors"] += 1
            elif e.level == "warn":
                counts["warnings"] += 1
        return counts

    def clear(self) -> None:
        """Clear both in-memory and on-disk activity entries."""
        with self._lock:
            self._entries.clear()
            if self.path is not None:
                try:
                    if self.path.exists():
                        self.path.unlink()
                except OSError:
                    pass

    def attach_bus(self, bus: EventBus) -> Callable[[], None]:
        """Subscribe to an :class:`EventBus` to automatically record session & UI events."""
        unsubs: list[Callable[[], None]] = []

        def _on_connected(payload: dict[str, Any]) -> None:
            proto = str(payload.get("protocol") or "ssh").upper()
            host = str(payload.get("host") or payload.get("session") or "local")
            session_name = str(payload.get("session") or host)
            self.record(
                "connection",
                f"{proto} session connected",
                f"Connected to {host}",
                level="good",
                session=session_name,
                protocol=proto.lower(),
            )

        def _on_connecting(payload: dict[str, Any]) -> None:
            proto = str(payload.get("protocol") or "ssh").upper()
            host = str(payload.get("host") or payload.get("session") or "local")
            session_name = str(payload.get("session") or host)
            self.record(
                "connection",
                f"{proto} connecting",
                f"Initiating connection to {host}",
                level="info",
                session=session_name,
                protocol=proto.lower(),
            )

        def _on_reconnecting(payload: dict[str, Any]) -> None:
            proto = str(payload.get("protocol") or "ssh").upper()
            host = str(payload.get("host") or payload.get("session") or "local")
            attempt = payload.get("attempt", 1)
            self.record(
                "connection",
                f"{proto} reconnecting (attempt #{attempt})",
                f"Reconnecting to {host}",
                level="warn",
                session=str(payload.get("session") or host),
                protocol=proto.lower(),
            )

        def _on_failed(payload: dict[str, Any]) -> None:
            proto = str(payload.get("protocol") or "ssh").upper()
            host = str(payload.get("host") or payload.get("session") or "local")
            reason = str(payload.get("reason") or payload.get("error") or "Connection failed")
            self.record(
                "connection",
                f"{proto} connection failed",
                reason,
                level="bad",
                session=str(payload.get("session") or host),
                protocol=proto.lower(),
            )

        def _on_closed(payload: dict[str, Any]) -> None:
            proto = str(payload.get("protocol") or "ssh").upper()
            host = str(payload.get("host") or payload.get("session") or "local")
            reason = str(payload.get("reason") or "Session closed")
            self.record(
                "connection",
                f"{proto} session closed",
                reason,
                level="info",
                session=str(payload.get("session") or host),
                protocol=proto.lower(),
            )

        def _on_transfer(payload: dict[str, Any]) -> None:
            direction = str(payload.get("direction") or "transfer")
            ok = bool(payload.get("ok", True))
            detail = str(payload.get("detail") or payload.get("destination") or "")
            self.record(
                "transfer",
                f"File {direction} {'completed' if ok else 'failed'}",
                detail,
                level="good" if ok else "bad",
                session=str(payload.get("session") or ""),
                protocol=str(payload.get("protocol") or "sftp"),
            )

        def _on_feedback(payload: dict[str, Any]) -> None:
            cat = str(payload.get("category") or "general")
            title = str(payload.get("title") or "User feedback")
            self.record(
                "feedback",
                f"Feedback submitted ({cat})",
                title,
                level="good",
            )

        unsubs.append(bus.subscribe("session/connected", _on_connected))
        unsubs.append(bus.subscribe("session/connecting", _on_connecting))
        unsubs.append(bus.subscribe("session/reconnecting", _on_reconnecting))
        unsubs.append(bus.subscribe("session/failed", _on_failed))
        unsubs.append(bus.subscribe("session/closed", _on_closed))
        unsubs.append(bus.subscribe("transfer/completed", _on_transfer))
        unsubs.append(bus.subscribe("feedback/submitted", _on_feedback))

        def _detach() -> None:
            for u in unsubs:
                u()

        return _detach


_default_activity: ActivityLog | None = None
_default_lock = threading.Lock()


def default_activity_log() -> ActivityLog:
    """Process-wide activity log rooted at ``paths.activity_log_file()``."""
    global _default_activity
    with _default_lock:
        if _default_activity is None:
            from . import paths

            _default_activity = ActivityLog(paths.activity_log_file())
        return _default_activity


def log_activity(
    kind: str,
    title: str,
    detail: str = "",
    *,
    level: str = "info",
    session: str = "",
    protocol: str = "",
) -> ActivityEntry | None:
    """Best-effort append to the process-wide activity log (never raises)."""
    try:
        return default_activity_log().record(
            kind,
            title,
            detail,
            level=level,
            session=session,
            protocol=protocol,
        )
    except Exception:  # noqa: BLE001
        return None
