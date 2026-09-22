"""SCP file transfer over an established SSH transport.

Implements the client side of the classic OpenSSH ``scp`` wire protocol
(``scp -f`` to receive, ``scp -t`` to send) on top of a paramiko
``Transport``. The protocol itself is publicly documented OpenSSH behavior
(see ``man scp`` and the OpenSSH ``scp.c`` source): single-letter reply
bytes (``\\0`` ok, ``\\1`` warning, ``\\2`` fatal), ``C``/``D``/``E``/``T``
control lines, raw file bytes in between. No proprietary code is involved —
this module speaks the same bytes any ``scp`` client speaks.

SCP has no directory *listing* command, so browsing still uses SFTP; only
the byte transfer runs over SCP. That matches MobaXterm's "SCP transfer
mode": pick it per transfer when the server's SFTP subsystem is missing or
slow.

Threading: a client is used from one engine thread at a time; the transport
itself multiplexes channels and is thread-safe.
"""

from __future__ import annotations

import os
import stat as _stat
import time
from dataclasses import dataclass
from pathlib import Path

from ...core.log import get_logger

log = get_logger("ssh.scp")

__all__ = [
    "ScpClient",
    "ScpError",
    "ScpStats",
    "format_file_header",
    "parse_dir_header",
    "parse_file_header",
    "parse_time_header",
    "quote_remote_path",
]

_CHUNK = 64 * 1024
_MAX_LINE = 8 * 1024  # longest C/D/T control line we accept
_MAX_DEPTH = 64  # nested D...E recursion cap on receive
_MAX_SIZE = (1 << 63) - 1


class ScpError(RuntimeError):
    """The remote scp endpoint reported an error, or the wire misbehaved."""


@dataclass
class ScpStats:
    files: int = 0
    bytes: int = 0
    elapsed_s: float = 0.0


# ----------------------------------------------------------------------
# Pure helpers (unit-tested without paramiko)
# ----------------------------------------------------------------------
def quote_remote_path(path: str) -> str:
    """POSIX-shell-quote one remote path for ``scp -f/-t <path>``.

    Empty paths are rejected — an empty word would make the remote scp
    read from an unintended location.
    """
    if not path or not path.strip():
        raise ScpError("refusing to transfer an empty remote path")
    if "\x00" in path or "\n" in path:
        raise ScpError(f"refusing unsafe remote path: {path!r}")
    return "'" + path.replace("'", "'\"'\"'") + "'"


def parse_file_header(line: str) -> tuple[int, int, str]:
    """Parse ``C<mode> <size> <name>`` → (mode, size, name)."""
    if not line.startswith("C"):
        raise ScpError(f"expected file header, got: {line[:60]!r}")
    parts = line[1:].split(" ", 2)
    if len(parts) != 3:
        raise ScpError(f"malformed file header: {line[:60]!r}")
    try:
        mode = int(parts[0], 8)
        size = int(parts[1], 10)
    except ValueError:
        raise ScpError(f"malformed file header: {line[:60]!r}") from None
    name = parts[2]
    if size < 0 or size > _MAX_SIZE:
        raise ScpError(f"absurd file size in header: {line[:60]!r}")
    _check_wire_name(name)
    return mode, size, name


def parse_dir_header(line: str) -> tuple[int, str]:
    """Parse ``D<mode> 0 <name>`` → (mode, name)."""
    if not line.startswith("D"):
        raise ScpError(f"expected directory header, got: {line[:60]!r}")
    parts = line[1:].split(" ", 2)
    if len(parts) != 3:
        raise ScpError(f"malformed directory header: {line[:60]!r}")
    try:
        mode = int(parts[0], 8)
    except ValueError:
        raise ScpError(f"malformed directory header: {line[:60]!r}") from None
    _check_wire_name(parts[2])
    return mode, parts[2]


def parse_time_header(line: str) -> tuple[int, int]:
    """Parse ``T<mtime> 0 <atime> 0`` → (mtime, atime)."""
    if not line.startswith("T"):
        raise ScpError(f"expected time header, got: {line[:60]!r}")
    parts = line[1:].split(" ")
    if len(parts) != 4:
        raise ScpError(f"malformed time header: {line[:60]!r}")
    try:
        return int(parts[0]), int(parts[2])
    except ValueError:
        raise ScpError(f"malformed time header: {line[:60]!r}") from None


def format_file_header(mode: int, size: int, name: str) -> bytes:
    """Build a ``C<mode> <size> <name>\\n`` control line."""
    _check_wire_name(name)
    if size < 0 or size > _MAX_SIZE:
        raise ScpError(f"refusing to send absurd size {size}")
    return f"C{mode & 0o7777:04o} {size} {name}\n".encode()


def format_dir_header(mode: int, name: str) -> bytes:
    _check_wire_name(name)
    return f"D{mode & 0o7777:04o} 0 {name}\n".encode()


def format_time_header(mtime: int, atime: int) -> bytes:
    return f"T{int(mtime)} 0 {int(atime)} 0\n".encode()


def _check_wire_name(name: str) -> None:
    """Reject names that would escape the destination directory."""
    if not name or name in (".", "..") or "/" in name or name.startswith("-"):
        raise ScpError(f"refusing unsafe scp filename: {name!r}")
    if "\x00" in name or "\n" in name or "\r" in name:
        raise ScpError(f"refusing unsafe scp filename: {name!r}")


def _safe_join(base: Path, name: str) -> Path:
    """Join one wire ``name`` under ``base``, refusing escapes (CWE-22)."""
    _check_wire_name(name)
    resolved_base = base.resolve()
    candidate = (resolved_base / name).resolve()
    if candidate != resolved_base and resolved_base not in candidate.parents:
        raise ScpError(f"refusing escaping scp path: {name!r}")
    return candidate


# ----------------------------------------------------------------------
# Wire I/O against a paramiko-style channel (send/recv/close)
# ----------------------------------------------------------------------
def _send_all(chan, data: bytes) -> None:
    view = memoryview(data)
    while view:
        n = chan.send(view)
        if n <= 0:
            raise ScpError("scp channel closed by remote mid-transfer")
        view = view[n:]


def _recv_exact(chan, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = chan.recv(n - len(buf))
        if not chunk:
            raise ScpError("scp channel closed by remote mid-transfer")
        buf += chunk
    return bytes(buf)


def _readline(chan) -> bytes:
    """Read one ``\\n``-terminated control line (bounded)."""
    buf = bytearray()
    while True:
        byte = chan.recv(1)
        if not byte:
            raise ScpError("scp channel closed by remote mid-transfer")
        buf += byte
        if byte == b"\n":
            return bytes(buf)
        if len(buf) > _MAX_LINE:
            raise ScpError("remote sent an over-long scp control line")


def _read_ack(chan) -> None:
    """Read one scp reply byte; raise with the remote message on 1/2."""
    code = _recv_exact(chan, 1)[0]
    if code == 0:
        return
    raw = _readline(chan).decode("utf-8", "replace").strip()
    msg = raw or ("remote scp error" if code == 1 else "remote scp fatal error")
    raise ScpError(msg)


def _send_ok(chan) -> None:
    _send_all(chan, b"\x00")


def _with_stderr(chan, exc: ScpError) -> ScpError:
    """Enrich ``exc`` with the remote scp's stderr tail, when available.

    Best effort only: exotic or already-closed channels simply yield no
    tail, and the original message stands on its own.
    """
    try:
        recv_stderr = getattr(chan, "recv_stderr", None)
        stderr_ready = getattr(chan, "recv_stderr_ready", None)
        if recv_stderr is None:
            return exc
        if callable(stderr_ready) and not stderr_ready():
            return exc
        tail = recv_stderr(2048)
        if not tail:
            return exc
        text = bytes(tail).decode("utf-8", "replace").strip()
        if text and text not in str(exc):
            return ScpError(f"{exc} (remote: {text[:300]})")
    except Exception:  # noqa: BLE001 — diagnostics must not mask the error
        pass
    return exc


# ----------------------------------------------------------------------
# Client
# ----------------------------------------------------------------------
class ScpClient:
    """SCP sender/receiver multiplexed over one SSH transport."""

    def __init__(self, transport, timeout: int = 30) -> None:
        self._transport = transport
        self._timeout = max(5, int(timeout))

    # -- public ------------------------------------------------------
    def download(
        self,
        remote: str,
        local: str | Path,
        *,
        recursive: bool = False,
        preserve_times: bool = True,
        progress=None,  # callable(done_bytes, total_bytes|None) -> None
    ) -> ScpStats:
        """Receive ``remote`` into local path ``local``.

        When ``local`` is a directory (or ends with a separator and
        ``recursive`` is set), the remote basename is appended, like the
        ``scp`` command does.
        """
        started = time.monotonic()
        stats = ScpStats()
        local_path = Path(local)
        cmd = f"scp -f {'-r ' if recursive else ''}{'-p ' if preserve_times else ''}{quote_remote_path(remote)}"
        chan = self._open(cmd)
        try:
            _send_all(chan, b"\x00")  # kick the sender off
            self._receive_into(chan, local_path, stats, progress, depth=0,
                                 preserve_times=preserve_times, recursive=recursive)
        except ScpError as exc:
            raise _with_stderr(chan, exc) from exc
        except (TimeoutError, EOFError) as exc:
            # Channel-level transport failure (paramiko raises socket.timeout
            # / EOFError): keep the ScpError contract while preserving the
            # transient markers the engine's retry classifier keys on.
            raise _with_stderr(chan, ScpError(f"scp transfer failed ({type(exc).__name__}): {exc}")) from exc
        finally:
            try:
                chan.close()
            except Exception:  # noqa: BLE001 — teardown must not mask results
                pass
        stats.elapsed_s = time.monotonic() - started
        return stats

    def upload(
        self,
        local: str | Path,
        remote: str,
        *,
        recursive: bool = False,
        preserve_times: bool = True,
        progress=None,
    ) -> ScpStats:
        """Send local path ``local`` to ``remote`` (file or directory)."""
        started = time.monotonic()
        stats = ScpStats()
        src = Path(local)
        if not src.exists():
            raise ScpError(f"local path does not exist: {src}")
        if src.is_dir() and not recursive:
            raise ScpError(f"{src} is a directory — pass recursive=True")
        # No `-d`: measured against OpenSSH's sink, omitting it gives cp-like
        # semantics in every case (missing target becomes the dir, existing
        # dir nests inside it), while `-d` refuses missing targets outright.
        cmd = f"scp -t {'-r ' if recursive else ''}{'-p ' if preserve_times else ''}{quote_remote_path(remote)}"
        chan = self._open(cmd)
        try:
            _read_ack(chan)  # sink ready?
            if src.is_dir():
                # Send the directory itself (like `scp -r dir remote:`).
                self._send_dir(chan, src, stats, progress, preserve_times)
            else:
                self._send_file(chan, src, stats, progress, preserve_times)
        except ScpError as exc:
            raise _with_stderr(chan, exc) from exc
        except (TimeoutError, EOFError) as exc:
            # Channel-level transport failure (paramiko raises socket.timeout
            # / EOFError): keep the ScpError contract while preserving the
            # transient markers the engine's retry classifier keys on.
            raise _with_stderr(chan, ScpError(f"scp transfer failed ({type(exc).__name__}): {exc}")) from exc
        finally:
            try:
                chan.close()
            except Exception:  # noqa: BLE001
                pass
        stats.elapsed_s = time.monotonic() - started
        return stats

    # -- transport ---------------------------------------------------
    def _open(self, cmd: str):
        try:
            chan = self._transport.open_session(timeout=self._timeout)
        except Exception as exc:
            raise ScpError(f"cannot open scp channel: {exc}") from exc
        try:
            chan.settimeout(self._timeout)
        except Exception:  # noqa: BLE001 — exotic channels may lack timeouts
            pass
        try:
            chan.exec_command(cmd)
        except Exception as exc:
            try:
                chan.close()
            except Exception:  # noqa: BLE001
                pass
            raise ScpError(f"cannot start remote scp: {exc}") from exc
        return chan

    # -- receive -----------------------------------------------------
    def _receive_into(self, chan, dest: Path, stats: ScpStats, progress, *, depth: int,
                        preserve_times: bool, recursive: bool = False) -> None:
        """Receive one entry (file or, recursively, directory tree)."""
        if depth > _MAX_DEPTH:
            raise ScpError("remote directory tree is too deep")
        mtime: int | None = None
        atime: int | None = None
        while True:
            line = _readline(chan).decode("utf-8", "replace").rstrip("\n")
            kind = line[:1]
            if kind == "T":
                mtime, atime = parse_time_header(line)
                _send_ok(chan)
                continue
            if kind == "C":
                mode, size, name = parse_file_header(line)
                target = dest / name if dest.is_dir() or str(dest).endswith(os.sep) else dest
                if dest.is_dir() or str(dest).endswith(os.sep):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target = _safe_join(target.parent, name)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                _send_ok(chan)
                self._receive_file(chan, target, size, stats, progress)
                _read_ack(chan)  # sender's end-of-file marker... actually sender sends \0
                _send_ok(chan)
                if preserve_times and mtime is not None and atime is not None:
                    try:
                        os.utime(target, (atime, mtime))
                    except OSError:
                        pass
                try:
                    os.chmod(target, mode & 0o7777)
                except OSError:
                    pass
                return
            if kind == "D":
                mode, name = parse_dir_header(line)
                if not recursive:
                    raise ScpError(f"remote path is a directory ({name}) — pass recursive=True")
                if dest.is_dir():
                    target = _safe_join(dest, name)
                else:
                    # `scp -r host:dir ./newname` — dest itself becomes the
                    # received directory (only when it does not exist yet).
                    target = dest
                target.mkdir(parents=True, exist_ok=True)
                _send_ok(chan)
                # Children arrive until the matching "E".
                while True:
                    peek = _readline(chan).decode("utf-8", "replace").rstrip("\n")
                    if peek == "E":
                        _send_ok(chan)
                        break
                    self._receive_entry(chan, target, peek, stats, progress, depth=depth + 1,
                                        preserve_times=preserve_times)
                if preserve_times and mtime is not None and atime is not None:
                    try:
                        os.utime(target, (atime, mtime))
                    except OSError:
                        pass
                try:
                    os.chmod(target, mode & 0o7777)
                except OSError:
                    pass
                return
            if kind == "E":
                # End of the current directory level (recursive receive).
                _send_ok(chan)
                return
            if kind in ("\x01", "\x02"):
                raise ScpError(line[1:] or "remote scp error")
            raise ScpError(f"unexpected scp control line: {line[:60]!r}")

    def _receive_entry(self, chan, dest_dir: Path, line: str, stats: ScpStats, progress, *, depth: int,
                       preserve_times: bool) -> None:
        """Receive one entry whose first control line was already read."""
        if depth > _MAX_DEPTH:
            raise ScpError("remote directory tree is too deep")
        mtime: int | None = None
        atime: int | None = None
        if line.startswith("T"):
            mtime, atime = parse_time_header(line)
            _send_ok(chan)
            line = _readline(chan).decode("utf-8", "replace").rstrip("\n")
        kind = line[:1]
        if kind == "C":
            mode, size, name = parse_file_header(line)
            target = _safe_join(dest_dir, name)
            _send_ok(chan)
            self._receive_file(chan, target, size, stats, progress)
            _read_ack(chan)
            _send_ok(chan)
            if preserve_times and mtime is not None and atime is not None:
                try:
                    os.utime(target, (atime, mtime))
                except OSError:
                    pass
            try:
                os.chmod(target, mode & 0o7777)
            except OSError:
                pass
            return
        if kind == "D":
            mode, name = parse_dir_header(line)
            target = _safe_join(dest_dir, name)
            target.mkdir(parents=True, exist_ok=True)
            _send_ok(chan)
            while True:
                child = _readline(chan).decode("utf-8", "replace").rstrip("\n")
                if child == "E":
                    _send_ok(chan)
                    break
                self._receive_entry(chan, target, child, stats, progress, depth=depth + 1,
                                    preserve_times=preserve_times)
            if preserve_times and mtime is not None and atime is not None:
                try:
                    os.utime(target, (atime, mtime))
                except OSError:
                    pass
            try:
                os.chmod(target, mode & 0o7777)
            except OSError:
                pass
            return
        if kind in ("\x01", "\x02"):
            raise ScpError(line[1:] or "remote scp error")
        raise ScpError(f"unexpected scp control line: {line[:60]!r}")

    def _receive_file(self, chan, target: Path, size: int, stats: ScpStats, progress) -> None:
        # Atomic receive: stream to a temp sibling, then rename over the
        # destination, so an interrupted transfer never leaves a half file
        # masquerading as the real thing.
        tmp = target.with_name(target.name + f".kb-scp-part-{os.getpid()}")
        remaining = size
        try:
            with open(tmp, "wb") as out:
                while remaining > 0:
                    chunk = chan.recv(min(_CHUNK, remaining))
                    if not chunk:
                        raise ScpError("scp channel closed by remote mid-transfer")
                    out.write(chunk)
                    remaining -= len(chunk)
                    stats.bytes += len(chunk)
                    if progress is not None:
                        progress(stats.bytes, None)
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        os.replace(tmp, target)
        stats.files += 1

    # -- send ----------------------------------------------------------
    def _send_file(self, chan, src: Path, stats: ScpStats, progress, preserve_times: bool) -> None:
        st = src.stat()
        if not _stat.S_ISREG(st.st_mode):
            raise ScpError(f"refusing to send non-regular file: {src}")
        if preserve_times:
            _send_all(chan, format_time_header(int(st.st_mtime), int(st.st_atime)))
            _read_ack(chan)
        _send_all(chan, format_file_header(_stat.S_IMODE(st.st_mode), st.st_size, src.name))
        _read_ack(chan)
        sent = 0
        with open(src, "rb") as fh:
            while True:
                chunk = fh.read(_CHUNK)
                if not chunk:
                    break
                _send_all(chan, chunk)
                sent += len(chunk)
                stats.bytes += len(chunk)
                if progress is not None:
                    progress(stats.bytes, None)
        if sent != st.st_size:
            log.warning("scp sent %d of %d bytes for %s (file changed?)", sent, st.st_size, src)
        _send_all(chan, b"\x00")
        _read_ack(chan)
        stats.files += 1

    def _send_dir(self, chan, src: Path, stats: ScpStats, progress, preserve_times: bool) -> None:
        st = src.stat()
        if preserve_times:
            _send_all(chan, format_time_header(int(st.st_mtime), int(st.st_atime)))
            _read_ack(chan)
        _send_all(chan, format_dir_header(_stat.S_IMODE(st.st_mode), src.name))
        _read_ack(chan)
        for child in sorted(src.iterdir(), key=lambda p: p.name):
            if child.is_dir() and not child.is_symlink():
                self._send_dir(chan, child, stats, progress, preserve_times)
            elif child.is_file() and not child.is_symlink():
                # Nested files are sent relative to their own directory:
                # temporarily chdir the *name* by sending from the child dir.
                self._send_file_at(chan, child, stats, progress, preserve_times)
            else:
                log.warning("scp skipping non-regular %s", child)
        _send_all(chan, b"E\n")
        _read_ack(chan)

    def _send_file_at(self, chan, src: Path, stats: ScpStats, progress, preserve_times: bool) -> None:
        """Send one file inside a directory tree (name only, no path)."""
        st = src.stat()
        if preserve_times:
            _send_all(chan, format_time_header(int(st.st_mtime), int(st.st_atime)))
            _read_ack(chan)
        _send_all(chan, format_file_header(_stat.S_IMODE(st.st_mode), st.st_size, src.name))
        _read_ack(chan)
        with open(src, "rb") as fh:
            while True:
                chunk = fh.read(_CHUNK)
                if not chunk:
                    break
                _send_all(chan, chunk)
                stats.bytes += len(chunk)
                if progress is not None:
                    progress(stats.bytes, None)
        _send_all(chan, b"\x00")
        _read_ack(chan)
        stats.files += 1


