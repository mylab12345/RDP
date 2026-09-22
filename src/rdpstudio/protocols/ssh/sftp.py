"""SFTP/SCP engine: browse + transfers with progress, running on its own thread.

One engine per transfer window. It borrows the *existing* transport from a
live SSH session (paramiko transports are thread-safe and multiplex channels),
so opening the file browser costs nothing extra.

Transfers are recursive and cancellable; progress is reported as
(bytes_done, bytes_total, files_done, files_total). Downloads are atomic
(stream to ``*.part``, rename on success) and resumable; transient
transport failures are retried with backoff; every finished transfer is
recorded in the transfer history. The byte transfer can run over SFTP
(default) or the classic ``scp`` wire protocol (see :mod:`.scp`) — browsing
always uses SFTP, since SCP has no listing command.
"""

from __future__ import annotations

import os
import posixpath
import stat
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import paramiko
from PySide6.QtCore import QObject, Signal, Slot

from ...core.log import get_logger
from ...core.retry import RetryPolicy, is_transient
from ...core.transfers import TransferRecord, log_transfer
from .scp import ScpClient, ScpError

log = get_logger("ssh.sftp")

CHUNK = 131_072

#: Retry policy for transient transfer failures (cancel-aware waits).
TRANSFER_RETRY = RetryPolicy(attempts=3, base_delay=0.5, max_delay=4.0, jitter=0.2)


@dataclass
class RemoteEntry:
    name: str
    longname: str
    is_dir: bool
    size: int
    mtime: float
    permissions: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_dir": self.is_dir,
            "size": self.size,
            "mtime": self.mtime,
            "permissions": self.permissions,
            "longname": self.longname,
        }


@dataclass
class TransferJob:
    op_id: str
    direction: str  # download | upload
    sources: list[str] = field(default_factory=list)
    dest: str = ""
    remote_root: str = ""
    local_root: str = ""
    protocol: str = "sftp"  # sftp | scp
    session: str = ""
    done_bytes: int = 0
    total_bytes: int = 0
    files_done: int = 0
    files_total: int = 0
    started_at: float = field(default_factory=time.monotonic)
    cancelled: threading.Event = field(default_factory=threading.Event)


class SftpEngine(QObject):
    """All slots run on the engine's own thread (moveToThread before use)."""

    connected = Signal()
    failed = Signal(str)
    listed = Signal(str, list)  # path, [RemoteEntry.to_dict()]
    listedLocal = Signal(str, list)  # local dir listing
    stats = Signal(str)  # error/status text for header
    transferProgress = Signal(str, int, int, int, int, float)  # id, bytes,total,files,files_total, rate B/s
    transferDone = Signal(str, bool, str)  # id, ok, message
    opDone = Signal(str, bool, str)  # generic op name, ok, message
    fileRead = Signal(str, bytes)  # path, content_bytes
    fileWritten = Signal(str, bool, str)  # path, ok, message

    def __init__(self, transport_provider, session_name: str = "", transfer_protocol: str = "sftp") -> None:
        """``transport_provider``: callable returning a live paramiko Transport
        (called on the engine thread)."""
        super().__init__()
        self._transport_provider = transport_provider
        self._session_name = session_name
        self._transfer_mode = transfer_protocol if transfer_protocol in ("sftp", "scp") else "sftp"
        self._sftp: paramiko.SFTPClient | None = None
        self._jobs: dict[str, TransferJob] = {}
        self._pending_locals: dict[str, str] = {}
        self._pending_remotes: dict[str, str] = {}

    @Slot(str)
    def set_transfer_mode(self, mode: str) -> None:
        """Switch the byte-transfer engine (``sftp`` | ``scp``).

        Queued slot: safe to call from the GUI thread; applies to transfers
        started afterwards.
        """
        if mode in ("sftp", "scp"):
            self._transfer_mode = mode

    @property
    def transfer_mode(self) -> str:
        return self._transfer_mode

    # ------------------------------------------------------------------
    @Slot()
    def ensure_open(self) -> None:
        if self._sftp is not None:
            self.connected.emit()
            return
        try:
            transport = self._transport_provider()
            if transport is None or not transport.is_active():
                raise RuntimeError("session is not connected")
            self._sftp = paramiko.SFTPClient.from_transport(transport)
            if self._sftp is None:
                raise RuntimeError("server does not support SFTP")
            self.connected.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    @Slot(str)
    def chdir(self, path: str) -> None:
        try:
            self.ensure_open()
            assert self._sftp is not None
            if not path:
                path = self._sftp.normalize(".")
            self._sftp.chdir(path)
            self.list_dir(path)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"cannot open {path}: {exc}")

    @Slot(str)
    def list_dir(self, path: str) -> None:
        try:
            assert self._sftp is not None
            entries: list[dict] = []
            for attr in self._sftp.listdir_attr(path):
                entries.append(_entry_from_attr(attr).to_dict())
            entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
            self.listed.emit(path, entries)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"cannot list {path}: {exc}")

    @Slot(str)
    def list_local(self, path: str) -> None:
        try:
            entries: list[dict] = []
            if path in ("", "~"):
                path = str(Path.home())
            p = Path(path).expanduser()
            for child in sorted(p.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
                try:
                    st = child.stat()
                    entries.append(
                        {
                            "name": child.name,
                            "is_dir": child.is_dir(),
                            "size": st.st_size,
                            "mtime": st.st_mtime,
                            "permissions": oct(stat.S_IMODE(st.st_mode)),
                            "longname": str(child),
                        }
                    )
                except OSError:
                    continue
            self.listedLocal.emit(str(p), entries)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"cannot list {path}: {exc}")

    @Slot(str, str)
    def mkdir(self, path: str, name: str) -> None:
        try:
            assert self._sftp is not None
            target = posixpath.join(path, name)
            self._sftp.mkdir(target)
            self.opDone.emit("mkdir", True, target)
            self.list_dir(path)
        except Exception as exc:  # noqa: BLE001
            self.opDone.emit("mkdir", False, str(exc))

    @Slot(str, str)
    def remove(self, path: str, name: str) -> None:
        try:
            assert self._sftp is not None
            target = posixpath.join(path, name)
            st = self._sftp.stat(target)
            if stat.S_ISDIR(st.st_mode):
                for child in self._sftp.listdir(target):
                    self.remove(target, child)
                self._sftp.rmdir(target)
            else:
                self._sftp.remove(target)
            self.opDone.emit("remove", True, target)
            self.list_dir(path)
        except Exception as exc:  # noqa: BLE001
            self.opDone.emit("remove", False, str(exc))

    @Slot(str, str, str)
    def rename(self, path: str, old: str, new: str) -> None:
        try:
            assert self._sftp is not None
            self._sftp.posix_rename(posixpath.join(path, old), posixpath.join(path, new))
            self.opDone.emit("rename", True, new)
            self.list_dir(path)
        except Exception as exc:  # noqa: BLE001
            self.opDone.emit("rename", False, str(exc))

    # --- transfers -------------------------------------------------------
    @Slot(str, str, str)
    def download(self, op_id: str, remote_dir: str, names: str) -> None:
        """``names`` is a '\\n'-joined list inside ``remote_dir``."""
        job = TransferJob(
            op_id=op_id, direction="download", remote_root=remote_dir,
            protocol=self._transfer_mode, session=self._session_name,
            sources=[n for n in names.split("\n") if n.strip()],
        )
        self._jobs[op_id] = job
        local_dir = self._pending_locals.pop(op_id, "")
        job.dest = local_dir
        if not job.sources:
            self._jobs.pop(op_id, None)
            self.transferDone.emit(op_id, False, "nothing selected")
            return
        try:
            targets = [posixpath.join(remote_dir, n) for n in job.sources]
            if self._transfer_mode == "scp":
                self._download_scp(targets, local_dir, job)
            else:
                self.ensure_open()
                assert self._sftp is not None
                self._compute_totals(targets, job)
                for t in targets:
                    self._download_rec(t, local_dir, job)
            self._finish(job, True, "download complete")
        except Exception as exc:  # noqa: BLE001
            log.exception("download failed")
            self._finish(job, False, str(exc))

    @Slot(str, str, str)
    def upload(self, op_id: str, local_dir: str, names: str) -> None:
        job = TransferJob(
            op_id=op_id, direction="upload", local_root=local_dir,
            protocol=self._transfer_mode, session=self._session_name,
            sources=[n for n in names.split("\n") if n.strip()],
        )
        self._jobs[op_id] = job
        remote_dir = self._pending_remotes.pop(op_id, "")
        job.dest = remote_dir
        if not job.sources:
            self._jobs.pop(op_id, None)
            self.transferDone.emit(op_id, False, "nothing selected")
            return
        try:
            targets = [os.path.join(local_dir, n) for n in job.sources]
            if self._transfer_mode == "scp":
                self._upload_scp(targets, remote_dir, job)
            else:
                self.ensure_open()
                assert self._sftp is not None
                self._compute_totals_local(targets, job)
                for t in targets:
                    self._upload_rec(t, remote_dir, job)
            self._finish(job, True, "upload complete")
        except Exception as exc:  # noqa: BLE001
            log.exception("upload failed")
            self._finish(job, False, str(exc))

    @Slot(str, str, str)
    def download_to(self, op_id: str, local_dir: str, payload: str) -> None:
        """payload = remote_dir + '\\n' + name1 + '\\n' + name2 ..."""
        parts = payload.split("\n")
        remote_dir, names = parts[0], parts[1:]
        self._pending_locals[op_id] = local_dir
        self.download(op_id, remote_dir, "\n".join(names))

    @Slot(str, str, str)
    def upload_to(self, op_id: str, remote_dir: str, payload: str) -> None:
        parts = payload.split("\n")
        local_dir, names = parts[0], parts[1:]
        self._pending_remotes[op_id] = remote_dir
        self.upload(op_id, local_dir, "\n".join(names))

    @Slot(str)
    def cancel(self, op_id: str) -> None:
        job = self._jobs.get(op_id)
        if job:
            job.cancelled.set()

    def _cancelled(self, job: TransferJob) -> bool:
        return job.cancelled.is_set()

    # -- recursive walks ---------------------------------------------------
    def _compute_totals(self, targets: list[str], job: TransferJob) -> None:
        assert self._sftp is not None
        for t in targets:
            st = self._sftp.stat(t)
            if stat.S_ISDIR(st.st_mode):
                for child in self._sftp.listdir(t):
                    self._compute_totals([posixpath.join(t, child)], job)
            else:
                job.total_bytes += st.st_size
                job.files_total += 1

    def _compute_totals_local(self, targets: list[str], job: TransferJob) -> None:
        for t in targets:
            p = Path(t)
            if p.is_dir():
                for child in p.iterdir():
                    self._compute_totals_local([str(child)], job)
            else:
                job.total_bytes += p.stat().st_size
                job.files_total += 1

    def _with_retry(self, job: TransferJob, func, *args, **kwargs):
        """Run ``func`` with cancel-aware retries on transient failures."""
        last: Exception | None = None
        for attempt in range(1, TRANSFER_RETRY.attempts + 1):
            if self._cancelled(job):
                raise RuntimeError("cancelled")
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — classification decides
                last = exc
                if attempt >= TRANSFER_RETRY.attempts or not is_transient(exc):
                    raise
                if self._cancelled(job):
                    raise RuntimeError("cancelled") from exc
                log.info("transfer hit %s; retrying (%d/%d)", exc, attempt, TRANSFER_RETRY.attempts)
                job.cancelled.wait(TRANSFER_RETRY.delay_for(attempt))
        assert last is not None
        raise last

    def _download_rec(self, remote: str, local_dir: str, job: TransferJob) -> None:
        if self._cancelled(job):
            raise RuntimeError("cancelled")
        assert self._sftp is not None
        st = self._sftp.stat(remote)
        name = posixpath.basename(remote)
        # A hostile (or buggy) server can return entries like ".." or
        # "../../.ssh/authorized_keys" from listdir(); joining those blindly
        # writes outside the download directory (CWE-22, "Zip-Slip").
        local_path = _safe_child(local_dir, name)
        if stat.S_ISDIR(st.st_mode):
            local_path.mkdir(parents=True, exist_ok=True)
            for child in self._sftp.listdir(remote):
                if child in (".", ".."):
                    continue
                self._download_rec(posixpath.join(remote, child), str(local_path), job)
            return
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            # Never materialise devices/fifos/sockets from a remote listing.
            log.warning("skipping non-regular remote file %s", remote)
            return
        self._with_retry(job, self._download_file, remote, local_path, st, job)

    def _download_file(self, remote: str, local_path: Path, st, job: TransferJob) -> None:
        """Download one regular file: atomic, resumable, prefetched.

        Bytes stream into a ``*.part`` sibling so an interrupted transfer
        never leaves a half file masquerading as the real thing; a
        leftover ``*.part`` smaller than the remote file is resumed instead
        of restarted. ``SFTPFile.prefetch()`` keeps the pipe full on
        high-latency links (guarded: test doubles may lack it).
        """
        assert self._sftp is not None
        local_path.parent.mkdir(parents=True, exist_ok=True)
        part = local_path.with_name(local_path.name + ".part")
        resume_from = 0
        try:
            existing = part.stat().st_size
        except OSError:
            existing = 0
        remote_size = int(st.st_size or 0)
        if 0 < existing < remote_size:
            resume_from = existing
        elif existing >= remote_size and remote_size > 0:
            try:
                part.unlink()
            except OSError:
                pass
        # Bytes already on disk from an interrupted run count immediately.
        job.done_bytes += resume_from
        with open(part, "ab" if resume_from else "wb") as out:
            with self._sftp.open(remote, "rb") as src:
                prefetch = getattr(src, "prefetch", None)
                if callable(prefetch):
                    try:
                        prefetch()
                    except Exception:  # noqa: BLE001 — prefetch is best effort
                        pass
                if resume_from:
                    try:
                        src.seek(resume_from)
                    except Exception:  # noqa: BLE001 — restart instead
                        job.done_bytes -= resume_from
                        out.seek(0)
                        out.truncate()
                while True:
                    if self._cancelled(job):
                        raise RuntimeError("cancelled")
                    data = src.read(CHUNK)
                    if not data:
                        break
                    out.write(data)
                    job.done_bytes += len(data)
                    self._progress(job)
        os.replace(part, local_path)
        job.files_done += 1
        try:
            os.utime(local_path, (st.st_atime, st.st_mtime))
        except OSError:
            pass
        self._progress(job)

    def _upload_rec(self, local: str, remote_dir: str, job: TransferJob) -> None:
        if self._cancelled(job):
            raise RuntimeError("cancelled")
        assert self._sftp is not None
        p = Path(local)
        target = posixpath.join(remote_dir, p.name)
        if p.is_dir():
            try:
                self._sftp.stat(target)
            except FileNotFoundError:
                self._sftp.mkdir(target)
            for child in p.iterdir():
                self._upload_rec(str(child), target, job)
            return
        self._with_retry(job, self._upload_file, local, target, job)

    def _upload_file(self, local: str, target: str, job: TransferJob) -> None:
        assert self._sftp is not None
        with open(local, "rb") as src, self._sftp.open(target, "wb") as dst:
            while True:
                if self._cancelled(job):
                    raise RuntimeError("cancelled")
                data = src.read(CHUNK)
                if not data:
                    break
                dst.write(data)
                job.done_bytes += len(data)
                self._progress(job)
        job.files_done += 1
        self._progress(job)

    # -- SCP transfer paths --------------------------------------------------
    def _scp_client(self) -> ScpClient:
        transport = self._transport_provider()
        if transport is None or not transport.is_active():
            raise ScpError("session is not connected")
        return ScpClient(transport)

    def _classify_remote(self, remote: str) -> str:
        """Return ``"dir"`` or ``"file"`` for a remote path (SFTP stat)."""
        assert self._sftp is not None
        st = self._sftp.stat(remote)
        return "dir" if stat.S_ISDIR(st.st_mode) else "file"

    def _download_scp(self, targets: list[str], local_dir: str, job: TransferJob) -> None:
        # Totals + dir/file classification still come from SFTP when the
        # subsystem is there; without it, totals stay indeterminate (0) and
        # each target is tried as a file first, then as a directory.
        have_sftp = True
        try:
            self.ensure_open()
            assert self._sftp is not None
            self._compute_totals(targets, job)
        except Exception as exc:  # noqa: BLE001 — blind SCP fallback below
            log.info("SFTP unavailable, using blind SCP: %s", exc)
            self._sftp = None
            have_sftp = False
        client = self._scp_client()
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        for target in targets:
            if self._cancelled(job):
                raise RuntimeError("cancelled")
            is_dir = have_sftp and self._classify_remote(target) == "dir"
            base = job.done_bytes
            stats = self._with_retry(
                job, self._scp_download_one, client, target, local_dir,
                bool(is_dir), have_sftp, base, job,
            )
            job.files_done += stats.files

    def _scp_download_one(self, client: ScpClient, target: str, local_dir: str,
                          is_dir: bool, have_sftp: bool, base: int, job: TransferJob):
        def _progress(done: int, _total) -> None:
            job.done_bytes = base + done
            self._progress(job)

        if is_dir:
            return client.download(target, local_dir, recursive=True, progress=_progress)
        try:
            return client.download(target, local_dir, recursive=False, progress=_progress)
        except ScpError as exc:
            if have_sftp or self._cancelled(job):
                raise
            # Blind fallback: maybe it was a directory after all.
            if "directory" in str(exc).lower() or "regular file" in str(exc).lower():
                return client.download(target, local_dir, recursive=True, progress=_progress)
            raise

    def _upload_scp(self, targets: list[str], remote_dir: str, job: TransferJob) -> None:
        self._compute_totals_local(targets, job)
        client = self._scp_client()
        for target in targets:
            if self._cancelled(job):
                raise RuntimeError("cancelled")
            base = job.done_bytes

            def _progress(done: int, _total, _base: int = base) -> None:
                job.done_bytes = _base + done
                self._progress(job)

            stats = self._with_retry(
                job, client.upload, target, remote_dir,
                recursive=Path(target).is_dir(), progress=_progress,
            )
            job.files_done += stats.files

    def _progress(self, job: TransferJob) -> None:
        elapsed = max(0.001, time.monotonic() - job.started_at)
        rate = job.done_bytes / elapsed
        self.transferProgress.emit(
            job.op_id, job.done_bytes, job.total_bytes, job.files_done, job.files_total, rate
        )

    def _finish(self, job: TransferJob, ok: bool, message: str) -> None:
        self._jobs.pop(job.op_id, None)
        duration = max(0.0, time.monotonic() - job.started_at)
        if job.direction == "download":
            source = f"{job.remote_root} ({len(job.sources)} item(s))"
            dest = job.dest
        else:
            source = f"{job.local_root} ({len(job.sources)} item(s))"
            dest = job.dest
        log_transfer(TransferRecord(
            protocol=job.protocol,
            direction=job.direction,
            session=self._session_name,
            source=source,
            destination=dest,
            bytes_total=job.done_bytes if ok else job.total_bytes,
            files_total=job.files_done if ok else job.files_total,
            ok=ok,
            error="" if ok else message[:300],
            duration_s=round(duration, 2),
        ))
        self.transferDone.emit(job.op_id, ok, message)

    @Slot(str)
    def realpath(self, path: str) -> None:
        try:
            assert self._sftp is not None
            self.opDone.emit("realpath", True, self._sftp.normalize(path))
        except Exception as exc:  # noqa: BLE001
            self.opDone.emit("realpath", False, str(exc))

    @Slot(str)
    def read_file_content(self, remote_path: str) -> None:
        try:
            self.ensure_open()
            assert self._sftp is not None
            with self._sftp.open(remote_path, "rb") as f:
                data = f.read(16 * 1024 * 1024)
            self.fileRead.emit(remote_path, data)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"Failed reading {remote_path}: {exc}")

    @Slot(str, bytes)
    def write_file_content(self, remote_path: str, data: bytes) -> None:
        try:
            self.ensure_open()
            assert self._sftp is not None
            with self._sftp.open(remote_path, "wb") as f:
                f.write(data)
            self.fileWritten.emit(remote_path, True, "File saved successfully")
        except Exception as exc:  # noqa: BLE001
            self.fileWritten.emit(remote_path, False, str(exc))



def _safe_child(directory: str, name: str) -> Path:
    """Resolve ``name`` inside ``directory``, refusing to escape it.

    Guards against remote-controlled names such as ``..``, ``../../x`` and
    absolute paths.
    """
    base = Path(directory).resolve()
    candidate = (base / posixpath.basename(name)).resolve()
    if candidate != base and base not in candidate.parents:
        raise RuntimeError(f"refusing unsafe transfer path: {name!r}")
    return candidate


def _entry_from_attr(attr: paramiko.SFTPAttributes) -> RemoteEntry:
    is_dir = stat.S_ISDIR(attr.st_mode or 0)
    perms = ""
    if attr.st_mode is not None:
        perms = _mode_to_str(attr.st_mode)
    return RemoteEntry(
        name=attr.filename,
        longname=getattr(attr, "longname", "") or "",
        is_dir=is_dir,
        size=attr.st_size or 0,
        mtime=float(attr.st_mtime or 0.0),
        permissions=perms,
    )


def _mode_to_str(mode: int) -> str:
    bits = ""
    for shift in (6, 3, 0):
        for flag, char in ((4, "r"), (2, "w"), (1, "x")):
            bits += char if (mode >> shift) & flag else "-"
    prefix = "d" if stat.S_ISDIR(mode) else "-"
    return prefix + bits
