"""SFTP engine: browse + transfers with progress, running on its own thread.

One engine per transfer window. It borrows the *existing* transport from a
live SSH session (paramiko transports are thread-safe and multiplex channels),
so opening the file browser costs nothing extra.

Transfers are recursive and cancellable; progress is reported as
(bytes_done, bytes_total, files_done, files_total).
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

log = get_logger("ssh.sftp")

CHUNK = 131_072


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

    def __init__(self, transport_provider) -> None:
        """``transport_provider``: callable returning a live paramiko Transport
        (called on the engine thread)."""
        super().__init__()
        self._transport_provider = transport_provider
        self._sftp: paramiko.SFTPClient | None = None
        self._jobs: dict[str, TransferJob] = {}
        self._pending_locals: dict[str, str] = {}
        self._pending_remotes: dict[str, str] = {}

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
        job = TransferJob(op_id=op_id, direction="download", remote_root=remote_dir)
        self._jobs[op_id] = job
        local_dir = self._pending_locals.pop(op_id, "")
        try:
            self.ensure_open()
            assert self._sftp is not None
            targets = [posixpath.join(remote_dir, n) for n in names.split("\n") if n]
            self._compute_totals(targets, job)
            for t in targets:
                self._download_rec(t, local_dir, job)
            self._finish(job, True, "download complete")
        except Exception as exc:  # noqa: BLE001
            log.exception("download failed")
            self._finish(job, False, str(exc))

    @Slot(str, str, str)
    def upload(self, op_id: str, local_dir: str, names: str) -> None:
        job = TransferJob(op_id=op_id, direction="upload", local_root=local_dir)
        self._jobs[op_id] = job
        remote_dir = self._pending_remotes.pop(op_id, "")
        try:
            self.ensure_open()
            assert self._sftp is not None
            targets = [os.path.join(local_dir, n) for n in names.split("\n") if n]
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

    def _download_rec(self, remote: str, local_dir: str, job: TransferJob) -> None:
        if self._cancelled(job):
            raise RuntimeError("cancelled")
        assert self._sftp is not None
        st = self._sftp.stat(remote)
        name = posixpath.basename(remote)
        local_path = Path(local_dir) / name
        if stat.S_ISDIR(st.st_mode):
            local_path.mkdir(parents=True, exist_ok=True)
            for child in self._sftp.listdir(remote):
                self._download_rec(posixpath.join(remote, child), str(local_path), job)
            return
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as out:
            with self._sftp.open(remote, "rb") as src:
                while True:
                    if self._cancelled(job):
                        raise RuntimeError("cancelled")
                    data = src.read(CHUNK)
                    if not data:
                        break
                    out.write(data)
                    job.done_bytes += len(data)
                    self._progress(job)
        job.files_done += 1
        os.utime(local_path, (st.st_atime, st.st_mtime))
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

    def _progress(self, job: TransferJob) -> None:
        elapsed = max(0.001, time.monotonic() - job.started_at)
        rate = job.done_bytes / elapsed
        self.transferProgress.emit(
            job.op_id, job.done_bytes, job.total_bytes, job.files_done, job.files_total, rate
        )

    def _finish(self, job: TransferJob, ok: bool, message: str) -> None:
        self._jobs.pop(job.op_id, None)
        self.transferDone.emit(job.op_id, ok, message)

    @Slot(str)
    def realpath(self, path: str) -> None:
        try:
            assert self._sftp is not None
            self.opDone.emit("realpath", True, self._sftp.normalize(path))
        except Exception as exc:  # noqa: BLE001
            self.opDone.emit("realpath", False, str(exc))


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
