"""Small, durable persistence primitives shared by application stores.

State is written to a private temporary file in the destination directory,
flushed, and atomically replaced.  A failed serialization or replace leaves
the previous destination untouched and removes the temporary file.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

PRIVATE_FILE_MODE = 0o600


def _prepare_temp(path: Path, *, mode: int, prefix: str | None, suffix: str) -> tuple[int, Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=prefix or f".{path.name}-",
        suffix=suffix,
    )
    temp_path = Path(raw_path)
    if os.name == "posix":
        # Set permissions before any content is written.  mkstemp already uses
        # 0600, but an explicit mode documents and enforces each caller's
        # policy without a briefly over-permissive window.
        os.fchmod(fd, mode)
    return fd, temp_path


def _sync_directory(directory: Path) -> None:
    """Best-effort fsync of a committed rename on POSIX filesystems."""
    if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        # Some network/synthetic filesystems do not support directory fsync;
        # the file itself was already safely flushed and replaced.
        pass
    finally:
        os.close(fd)


def _commit(temp_path: Path, path: Path) -> None:
    os.replace(temp_path, path)
    _sync_directory(path.parent)


class _StagedWrite:
    """Mutable bookkeeping for one :func:`_staged_write` block."""

    __slots__ = ("committed", "fd", "temp_path")

    def __init__(self, fd: int, temp_path: Path) -> None:
        self.fd = fd
        self.temp_path = temp_path
        self.committed = False

    def release_fd(self) -> int:
        """Hand the descriptor to a file object; we stop owning it."""
        fd, self.fd = self.fd, -1
        return fd

    def close_fd(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1


@contextmanager
def _staged_write(path: Path, *, mode: int, prefix: str | None, suffix: str):
    """Yield a :class:`_StagedWrite` for a write that publishes atomically.

    The block writes into ``temp_path``; on a clean exit the caller has
    already committed it and set ``state.committed``. On any exit path the
    descriptor in ``state.fd`` is closed and an uncommitted temporary file is
    removed, so a failed or cancelled write never leaks a descriptor nor
    litters the destination directory.
    """
    state = _StagedWrite(*_prepare_temp(path, mode=mode, prefix=prefix, suffix=suffix))
    try:
        yield state
    finally:
        state.close_fd()
        if not state.committed:
            try:
                state.temp_path.unlink()
            except OSError:
                pass


def atomic_write_bytes(
    path: str | os.PathLike[str],
    data: bytes,
    *,
    mode: int = PRIVATE_FILE_MODE,
    prefix: str | None = None,
    suffix: str = ".tmp",
) -> None:
    """Atomically replace ``path`` with ``data``.

    The destination remains unchanged if writing, flushing, or replacement
    fails.  Temporary files are always cleaned up, including on cancellation
    exceptions derived directly from :class:`BaseException`.
    """
    destination = Path(path)
    with _staged_write(destination, mode=mode, prefix=prefix, suffix=suffix) as staged:
        with os.fdopen(staged.release_fd(), "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _commit(staged.temp_path, destination)
        staged.committed = True


def atomic_write_text(
    path: str | os.PathLike[str],
    text: str,
    *,
    encoding: str = "utf-8",
    mode: int = PRIVATE_FILE_MODE,
    prefix: str | None = None,
    suffix: str = ".tmp",
) -> None:
    """Encode ``text`` and atomically replace ``path``."""
    atomic_write_bytes(
        path,
        text.encode(encoding),
        mode=mode,
        prefix=prefix,
        suffix=suffix,
    )


def atomic_write_via_path(
    path: str | os.PathLike[str],
    writer: Callable[[Path], None],
    *,
    mode: int = PRIVATE_FILE_MODE,
    prefix: str | None = None,
    suffix: str = ".tmp",
) -> None:
    """Atomically write with an API that requires a filename.

    ``writer`` receives a private temporary path in the destination directory.
    This is useful for third-party serializers such as Paramiko's
    ``HostKeys.save`` that cannot write to an already-open file object.
    """
    destination = Path(path)
    with _staged_write(destination, mode=mode, prefix=prefix, suffix=suffix) as staged:
        staged.close_fd()  # the writer opens the path itself
        writer(staged.temp_path)
        # A third-party writer may have replaced the temporary file itself;
        # re-assert privacy and durability before publishing it.
        if os.name == "posix":
            staged.temp_path.chmod(mode)
        with staged.temp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        _commit(staged.temp_path, destination)
        staged.committed = True
