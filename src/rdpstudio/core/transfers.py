"""Transfer history: a small JSONL log of completed file transfers.

Pure Python (no Qt). Every SFTP/SCP upload and download appends one record
(who, what, how many bytes, how long, did it work) to ``logs/transfers.jsonl``
so a failed overnight sync is diagnosable the next morning. The file is
bounded (oldest entries are compacted away) and never holds secrets — only
paths, sizes and error summaries.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .log import get_logger

log = get_logger("transfers")

#: Keep at most this many records; older ones are dropped on append.
MAX_RECORDS = 500


@dataclass
class TransferRecord:
    protocol: str = "sftp"  # sftp | scp
    direction: str = "download"  # download | upload
    session: str = ""  # session display name (no secrets)
    source: str = ""
    destination: str = ""
    bytes_total: int = 0
    files_total: int = 0
    ok: bool = True
    error: str = ""
    duration_s: float = 0.0
    finished_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: object) -> TransferRecord | None:
        if not isinstance(d, dict):
            return None
        try:
            rec = cls()
            for key, value in d.items():
                if hasattr(rec, key):
                    setattr(rec, key, value)
            rec.bytes_total = int(rec.bytes_total or 0)
            rec.files_total = int(rec.files_total or 0)
            rec.duration_s = float(rec.duration_s or 0.0)
            rec.finished_at = float(rec.finished_at or 0.0)
            rec.ok = bool(rec.ok)
            return rec
        except (TypeError, ValueError):
            return None


class TransferLog:
    """Append-only, size-bounded JSONL transfer history."""

    def __init__(self, path: Path, max_records: int = MAX_RECORDS) -> None:
        self.path = path
        self.max_records = max(10, int(max_records))
        self._lock = threading.Lock()

    def append(self, record: TransferRecord) -> None:
        if not record.finished_at:
            record.finished_at = time.time()
        line = json.dumps(record.to_dict(), ensure_ascii=False)
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                self._compact_locked()
            except OSError as exc:
                # The transfer itself already succeeded/failed; a broken
                # history file must never surface as a transfer error.
                log.debug("transfer history append failed: %s", exc)

    def read_recent(self, limit: int = 50) -> list[TransferRecord]:
        limit = max(1, min(int(limit), self.max_records))
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            return []
        out: list[TransferRecord] = []
        for line in lines[-limit:]:
            try:
                rec = TransferRecord.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            if rec is not None:
                out.append(rec)
        return out

    def _compact_locked(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (OSError, UnicodeDecodeError):
            return
        if len(lines) <= self.max_records:
            return
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines[-self.max_records:]) + "\n")
        except OSError as exc:
            log.debug("transfer history compaction failed: %s", exc)


_default_log: TransferLog | None = None
_default_lock = threading.Lock()


def default_log() -> TransferLog:
    """Process-wide history rooted at the app logs directory."""
    global _default_log
    with _default_lock:
        if _default_log is None:
            from . import paths

            _default_log = TransferLog(Path(paths.logs_dir()) / "transfers.jsonl")
        return _default_log


def log_transfer(record: TransferRecord) -> None:
    """Best-effort append to the process-wide history (never raises)."""
    try:
        default_log().append(record)
    except Exception:  # noqa: BLE001 — history must not break transfers
        pass
