"""User feedback store: persists improvement suggestions and bug reports.

Pure Python (no Qt). Entries are stored in ``feedback.jsonl`` under the
application config directory (bounded at :data:`MAX_FEEDBACK_ENTRIES`) and can
be formatted as Markdown for sharing or issue filing.

Never stores credentials, passwords, or private hostnames.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .log import get_logger

log = get_logger("feedback")

MAX_FEEDBACK_ENTRIES = 200

FEEDBACK_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("improvement", "Feature Request / Improvement"),
    ("ui_ux", "UI / Navigation & Layout"),
    ("rdp", "RDP & Remote Desktop"),
    ("transfer", "File Transfer (SFTP / Drag & Drop)"),
    ("mobile", "Mobile / Tablet Responsiveness"),
    ("accessibility", "Themes, Fonts & Accessibility"),
    ("bug", "Bug Report / Troubleshooting"),
    ("other", "Other Suggestion"),
)

FEEDBACK_CATEGORY_IDS = {cid for cid, _ in FEEDBACK_CATEGORIES}


@dataclass
class FeedbackEntry:
    """One user-submitted feedback item."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    ts: float = field(default_factory=time.time)
    category: str = "improvement"
    rating: int = 5
    title: str = ""
    description: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: object) -> FeedbackEntry | None:
        if not isinstance(d, dict):
            return None
        try:
            title = str(d.get("title") or "").strip()[:200]
            description = str(d.get("description") or "").strip()[:4000]
            if not title and not description:
                return None
            cat = str(d.get("category") or "improvement").strip().lower()
            if cat not in FEEDBACK_CATEGORY_IDS:
                cat = "improvement"
            rating = max(1, min(5, int(d.get("rating") or 5)))
            diag = d.get("diagnostics")
            if not isinstance(diag, dict):
                diag = {}
            return cls(
                id=str(d.get("id") or uuid.uuid4().hex[:10])[:24],
                ts=float(d.get("ts") or time.time()),
                category=cat,
                rating=rating,
                title=title or description.splitlines()[0][:80],
                description=description,
                diagnostics={str(k): v for k, v in list(diag.items())[:15]},
            )
        except (TypeError, ValueError):
            return None

    def to_markdown(self) -> str:
        """Render the feedback entry as a clean Markdown report."""
        cat_label = dict(FEEDBACK_CATEGORIES).get(self.category, self.category)
        stars = "★" * self.rating + "☆" * (5 - self.rating)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts))
        lines = [
            f"### [{cat_label}] {self.title}",
            f"- **Rating**: {stars} ({self.rating}/5)",
            f"- **Submitted**: {stamp}",
            "",
            self.description or "_No additional details provided._",
        ]
        if self.diagnostics:
            lines.append("")
            lines.append("#### Environment Diagnostics")
            for k, v in sorted(self.diagnostics.items()):
                lines.append(f"- **{k}**: `{v}`")
        return "\n".join(lines)


def build_safe_diagnostics(settings: Any = None, active_protocol: str = "") -> dict[str, Any]:
    """Collect anonymized, secret-free UI & platform diagnostics."""
    from .. import __version__

    diag: dict[str, Any] = {
        "version": __version__,
        "platform": sys.platform,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }
    if settings is not None:
        diag["theme"] = getattr(settings, "theme", "studio_dark")
        diag["density"] = getattr(settings, "density", "comfortable")
        diag["font_size"] = getattr(settings, "font_size", 10)
        diag["rdp_client"] = getattr(settings, "rdp_client", "auto")
    if active_protocol:
        diag["active_protocol"] = str(active_protocol).lower()
    return diag


class FeedbackStore:
    """Thread-safe JSONL store for user feedback."""

    def __init__(self, path: Path, max_entries: int = MAX_FEEDBACK_ENTRIES) -> None:
        self.path = path
        self.max_entries = max(10, int(max_entries))
        self._lock = threading.Lock()

    def submit(
        self,
        *,
        title: str,
        description: str = "",
        category: str = "improvement",
        rating: int = 5,
        diagnostics: dict[str, Any] | None = None,
    ) -> FeedbackEntry:
        clean_title = (title or "").strip()[:200]
        clean_desc = (description or "").strip()[:4000]
        if not clean_title and not clean_desc:
            raise ValueError("Please provide a title or description for your feedback.")
        if not clean_title:
            clean_title = clean_desc.splitlines()[0][:80]
        cat = (category or "improvement").strip().lower()
        if cat not in FEEDBACK_CATEGORY_IDS:
            cat = "improvement"
        entry = FeedbackEntry(
            category=cat,
            rating=max(1, min(5, int(rating or 5))),
            title=clean_title,
            description=clean_desc,
            diagnostics=dict(diagnostics or {}),
        )
        line = json.dumps(entry.to_dict(), ensure_ascii=False)
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                self._compact_locked()
            except OSError as exc:
                log.debug("feedback write failed: %s", exc)
        return entry

    def list_recent(self, limit: int = 50) -> list[FeedbackEntry]:
        limit = max(1, min(int(limit), self.max_entries))
        with self._lock:
            if not self.path.exists():
                return []
            try:
                lines = self.path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                return []
        out: list[FeedbackEntry] = []
        for line in reversed(lines):
            try:
                entry = FeedbackEntry.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if entry is not None:
                out.append(entry)
                if len(out) >= limit:
                    break
        return out

    def clear(self) -> None:
        with self._lock:
            try:
                if self.path.exists():
                    self.path.unlink()
            except OSError:
                pass

    def _compact_locked(self) -> None:
        if not self.path.exists():
            return
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            if len(lines) <= self.max_entries:
                return
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines[-self.max_entries :]) + "\n")
        except OSError:
            pass


_default_store: FeedbackStore | None = None
_default_lock = threading.Lock()


def default_feedback_store() -> FeedbackStore:
    """Process-wide feedback store rooted at ``paths.feedback_file()``."""
    global _default_store
    with _default_lock:
        if _default_store is None:
            from . import paths

            _default_store = FeedbackStore(paths.feedback_file())
        return _default_store
