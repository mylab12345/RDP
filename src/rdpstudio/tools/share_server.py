"""Built-in SFTP share server — expose local folders to remote machines.

Windows boxes reached over RDP have no SSH daemon, but they *do* ship an SFTP
client (``sftp.exe`` / ``scp.exe`` in Windows 10 1809+, or WinSCP).  So instead
of asking the remote machine to serve files, KB-Remote serves them: pick the
local folders you want to hand out, start the share server, and the Windows
machine pulls and pushes files with any SFTP client::

    sftp -P 2222 kbshare@192.168.1.10
    sftp> ls
    Builds/  Tools/
    sftp> put patch.msi Tools/patch.msi

Design notes
------------
- **paramiko as the server.** paramiko is already a dependency (for the SSH
  client) and ships a complete SFTP subsystem implementation; this module only
  supplies the filesystem backend and the auth policy.
- **One virtual root.** Every enabled share appears as a directory of ``/``
  (see :mod:`rdpstudio.core.shares`), so one listener serves every machine and
  every share — global defaults plus per-session extras.
- **Pure module.** No Qt: the listener, the SFTP backend and the password
  hashing are all testable headlessly, and the GUI merely starts/stops it and
  renders the event log.

Security
--------
Password auth only (no ``none``, no keyboard-interactive), constant-time
comparison against a PBKDF2-HMAC-SHA256 hash, no shell / exec / pty / port
forwarding, and every filesystem operation is confined to a share root by
:method:`ShareRegistry.resolve`.  The listener is off by default and only ever
bound by explicit user action.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import socket
import stat as stat_module
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paramiko
from paramiko import (
    AUTH_FAILED,
    AUTH_SUCCESSFUL,
    OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED,
    OPEN_SUCCEEDED,
    SFTP_EOF,
    SFTP_FAILURE,
    SFTP_NO_SUCH_FILE,
    SFTP_OK,
    SFTP_OP_UNSUPPORTED,
    SFTP_PERMISSION_DENIED,
    SFTPAttributes,
    SFTPHandle,
    SFTPServer,
    SFTPServerInterface,
    Transport,
)

from ..core.log import get_logger
from ..core.shares import ResolvedShare, ShareRegistry

log = get_logger("share.server")

# A non-privileged port: 22 would collide with the machine's own sshd and, on
# Linux, would need root.
DEFAULT_PORT = 2222
DEFAULT_USERNAME = "kbshare"
DEFAULT_BIND = "0.0.0.0"
DEFAULT_BANNER = "KB-Remote file share"
MAX_CONNECTIONS = 16
KDF_ALGO = "pbkdf2-sha256"
KDF_ITERATIONS = 310_000  # matches the vault's OWASP-2023 baseline
_SALT_BYTES = 16
_KEY_BYTES = 32
# Reject a client that authenticates but never opens the SFTP subsystem.
_AUTH_TIMEOUT = 20.0
_EVENT_HISTORY = 200


class ShareServerError(RuntimeError):
    """Raised when the share server cannot be started."""


# ----------------------------------------------------------------------
# Password hashing
# ----------------------------------------------------------------------
def hash_password(password: str, iterations: int = KDF_ITERATIONS) -> str:
    """Hash a share password for storage.

    Format ``pbkdf2-sha256$<iterations>$<b64 salt>$<b64 hash>``. Stored in
    ``settings.json`` (mode 0600) — never the plaintext.
    """
    if not password:
        raise ValueError("share password must not be empty")
    iterations = max(int(iterations or KDF_ITERATIONS), 100_000)
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=_KEY_BYTES)
    enc = base64.b64encode
    return f"{KDF_ALGO}${iterations}${enc(salt).decode()}${enc(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a :func:`hash_password` value."""
    if not stored or not isinstance(stored, str):
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[0] != KDF_ALGO:
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        expected = base64.b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    if iterations < 100_000 or not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", (password or "").encode("utf-8"), salt, iterations, dklen=len(expected)
    )
    return hmac.compare_digest(digest, expected)


# A fixed dummy hash keeps the timing of a failed login roughly the same
# whether or not the username exists (no cheap user enumeration).
_DUMMY_HASH = hash_password("kb-remote-dummy-password")


# ----------------------------------------------------------------------
# Configuration + events
# ----------------------------------------------------------------------
@dataclass
class ShareServerConfig:
    """Everything the listener needs, serialisable for ``settings.json``."""

    enabled: bool = False
    bind: str = DEFAULT_BIND
    port: int = DEFAULT_PORT
    username: str = DEFAULT_USERNAME
    password_hash: str = ""
    host_key_path: str = ""
    banner: str = DEFAULT_BANNER
    max_connections: int = MAX_CONNECTIONS
    allow_write: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "bind": self.bind,
            "port": self.port,
            "username": self.username,
            "password_hash": self.password_hash,
            "host_key_path": self.host_key_path,
            "banner": self.banner,
            "max_connections": self.max_connections,
            "allow_write": self.allow_write,
        }

    @classmethod
    def from_dict(cls, d: object) -> ShareServerConfig:
        from ..core.coerce import as_bool, as_int, as_text

        if not isinstance(d, dict):
            return cls()
        return cls(
            enabled=as_bool(d.get("enabled", False), False),
            bind=as_text(d.get("bind"), DEFAULT_BIND) or DEFAULT_BIND,
            port=as_int(d.get("port", DEFAULT_PORT) or DEFAULT_PORT, DEFAULT_PORT, minimum=1, maximum=65535),
            username=(as_text(d.get("username"), DEFAULT_USERNAME) or DEFAULT_USERNAME).strip(),
            password_hash=as_text(d.get("password_hash")),
            host_key_path=as_text(d.get("host_key_path")),
            banner=as_text(d.get("banner"), DEFAULT_BANNER) or DEFAULT_BANNER,
            max_connections=as_int(
                d.get("max_connections", MAX_CONNECTIONS) or MAX_CONNECTIONS,
                MAX_CONNECTIONS,
                minimum=1,
                maximum=MAX_CONNECTIONS,
            ),
            allow_write=as_bool(d.get("allow_write", True), True),
        )

    def has_password(self) -> bool:
        return bool(self.password_hash)


@dataclass
class ShareEvent:
    """One line of the share server's activity log."""

    ts: float
    kind: str  # listen | auth | open | put | get | delete | rename | error | stop
    detail: str
    peer: str = ""

    def stamp(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime(self.ts))

    def to_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "kind": self.kind, "detail": self.detail, "peer": self.peer}


# ----------------------------------------------------------------------
# Host key
# ----------------------------------------------------------------------
def ensure_host_key(path: str | Path | None) -> paramiko.PKey:
    """Load the share server's host key, generating an RSA-3072 key if absent.

    The key is written 0600 before it is used: it authenticates the server to
    connecting clients, so a world-readable copy would let anyone impersonate
    the share (CWE-276).
    """
    if path is None or str(path) == "":
        from ..core import paths as _paths

        path = _paths.share_host_key_file()
    key_path = Path(path).expanduser()
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        for loader in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
            try:
                return loader(filename=str(key_path))
            except (paramiko.SSHException, ValueError, OSError):
                continue
        log.warning("unreadable share host key %s — regenerating", key_path)
    key = paramiko.RSAKey.generate(3072)
    key.write_private_key_file(str(key_path))
    try:
        os.chmod(key_path, 0o600)
    except OSError:  # pragma: no cover - unusual filesystems
        pass
    log.info("generated share server host key %s", key_path)
    return key


def key_fingerprint(key: paramiko.PKey) -> str:
    """SHA256 fingerprint, in the format ``ssh-keygen -lf`` prints."""
    blob = key.asbytes()
    digest = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"


# ----------------------------------------------------------------------
# SFTP filesystem backend
# ----------------------------------------------------------------------
class _ShareHandle(SFTPHandle):
    """One open file inside a share, with transfer accounting."""

    def __init__(self, share: ResolvedShare, real: Path, flags: int, server: _ShareSFTPBackend) -> None:
        super().__init__(flags)
        self._share = share
        self._real = real
        self._server = server
        self.readfile = None
        self.writefile = None
        self._written = 0
        self._read = 0
        mode = getattr(server, "_open_mode", 0o644) or 0o644
        # The flags word already carries O_CREAT/O_EXCL/O_APPEND/O_TRUNC from
        # the client's SFTP pflags (paramiko converts them); O_BINARY is a
        # no-op on POSIX and required for sane writes on Windows.
        os_flags = flags | getattr(os, "O_BINARY", 0)
        fd = os.open(str(real), os_flags, mode)
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND))
        try:
            handle = os.fdopen(fd, "r+b" if writing else "rb")
        except OSError:
            os.close(fd)  # do not leak the descriptor if wrapping fails
            raise
        if writing:
            self.writefile = handle
        else:
            self.readfile = handle

    def read(self, offset: int, length: int):
        if self.readfile is None:
            return SFTP_PERMISSION_DENIED
        try:
            self.readfile.seek(offset)
            data = self.readfile.read(length)
        except OSError:
            return SFTP_FAILURE
        if len(data) == 0:
            return SFTP_EOF
        self._read += len(data)
        return data

    def write(self, offset: int, data: bytes):
        if self.writefile is None:
            return SFTP_PERMISSION_DENIED
        try:
            self.writefile.seek(offset)
            self.writefile.write(data)
        except OSError:
            return SFTP_FAILURE
        self._written += len(data)
        return SFTP_OK

    def stat(self):
        try:
            return SFTPAttributes.from_stat(os.stat(str(self._real)))
        except OSError:
            return SFTP_NO_SUCH_FILE

    def chattr(self, attr):
        return self._server.apply_attr(self._share, self._real, attr)

    def close(self):
        if self._written:
            self._server.note(
                "put",
                f"{self._share.remote_root()}/{self._real.name} ({self._written} bytes)",
            )
        elif self._read:
            self._server.note(
                "get",
                f"{self._share.remote_root()}/{self._real.name} ({self._read} bytes)",
            )
        for handle in (self.readfile, self.writefile):
            if handle is not None:
                try:
                    handle.flush()
                except (OSError, ValueError):
                    pass
                try:
                    handle.close()
                except OSError:
                    pass
        self.readfile = self.writefile = None
        return super().close()


class _ShareSFTPBackend(SFTPServerInterface):
    """Filesystem backend for one SFTP session, jailed to the share roots."""

    def __init__(self, server: Any, share_server: SftpShareServer | None = None) -> None:
        self._owner = server
        self._server = share_server
        self._registry: ShareRegistry | None = getattr(share_server, "registry", None)
        self._open_mode = 0o644
        self._peer = getattr(share_server, "peer_of", lambda _s: "")(server)

    # -- helpers ---------------------------------------------------------
    @property
    def registry(self) -> ShareRegistry | None:
        return self._registry

    def note(self, kind: str, detail: str) -> None:
        if self._server is not None:
            self._server.event(kind, detail, self._peer)

    def _resolve(self, path: str) -> tuple[ResolvedShare, Path] | None:
        if self._registry is None:
            return None
        return self._registry.resolve(path)

    # -- path handling ---------------------------------------------------
    def canonicalize(self, path: str) -> str:
        text = str(path or "").replace("\\", "/").strip()
        if text in ("", ".", "/"):
            return "/"
        parts = [p for p in text.split("/") if p not in ("", ".")]
        return "/" + "/".join(parts)

    def _attr_for(self, real: Path, name: str, follow: bool = True) -> SFTPAttributes | int:
        try:
            st = os.stat(str(real)) if follow else os.lstat(str(real))
        except OSError:
            return SFTP_NO_SUCH_FILE
        attr = SFTPAttributes.from_stat(st)
        attr.filename = name
        return attr

    # -- listing ---------------------------------------------------------
    def list_folder(self, path: str):
        canonical = self.canonicalize(path)
        if canonical == "/":
            if self._registry is None:
                return []
            now = int(time.time())
            out = []
            for entry in self._registry.entries():
                attr = SFTPAttributes()
                attr.filename = entry.name
                attr.st_mode = stat_module.S_IFDIR | (0o755 if entry.writable else 0o555)
                attr.st_size = 0
                attr.st_mtime = now
                attr.st_atime = now
                out.append(attr)
            return out
        found = self._resolve(canonical)
        if found is None:
            return SFTP_NO_SUCH_FILE
        _share, real = found
        if not real.is_dir():
            return SFTP_FAILURE
        out = []
        try:
            names = os.listdir(str(real))
        except OSError:
            return SFTP_PERMISSION_DENIED
        for name in names:
            attr = self._attr_for(real / name, name)
            if isinstance(attr, int):
                continue
            out.append(attr)
        return out

    def stat(self, path: str):
        canonical = self.canonicalize(path)
        if canonical == "/":
            attr = SFTPAttributes()
            attr.filename = "/"
            attr.st_mode = stat_module.S_IFDIR | 0o755
            attr.st_size = 0
            return attr
        found = self._resolve(canonical)
        if found is None:
            return SFTP_NO_SUCH_FILE
        _share, real = found
        return self._attr_for(real, real.name)

    def lstat(self, path: str):
        canonical = self.canonicalize(path)
        if canonical == "/":
            return self.stat(path)
        found = self._resolve(canonical)
        if found is None:
            return SFTP_NO_SUCH_FILE
        _share, real = found
        return self._attr_for(real, real.name, follow=False)

    # -- open / mutate ---------------------------------------------------
    def open(self, path: str, flags: int, attr):
        found = self._resolve(self.canonicalize(path))
        if found is None:
            return SFTP_NO_SUCH_FILE
        share, real = found
        creating = bool(flags & os.O_CREAT)
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND))
        if writing and not share.writable:
            self.note("error", f"write refused (share {share.name} is read-only): {real.name}")
            return SFTP_PERMISSION_DENIED
        if creating and real.is_dir():
            return SFTP_FAILURE
        mode = getattr(attr, "st_mode", 0) or 0
        self._open_mode = stat_module.S_IMODE(mode) or 0o644
        try:
            handle = _ShareHandle(share, real, flags, self)
        except OSError as exc:
            self.note("error", f"open {share.remote_root()}/{real.name} failed: {exc!r} (flags={flags})")
            if creating and exc.errno in (13, 30):  # EACCES / EROFS
                return SFTP_PERMISSION_DENIED
            return SFTP_FAILURE
        if creating:
            self.note("open", f"created {share.remote_root()}/{real.name}")
        return handle

    def remove(self, path: str):
        found = self._resolve(self.canonicalize(path))
        if found is None:
            return SFTP_NO_SUCH_FILE
        share, real = found
        if not share.writable:
            return SFTP_PERMISSION_DENIED
        try:
            os.unlink(str(real))
        except OSError:
            return SFTP_FAILURE
        self.note("delete", f"{share.remote_root()}/{real.name}")
        return SFTP_OK

    def rename(self, src: str, dest: str):
        a = self._resolve(self.canonicalize(src))
        b = self._resolve(self.canonicalize(dest))
        if a is None or b is None:
            return SFTP_NO_SUCH_FILE
        share_a, real_a = a
        share_b, real_b = b
        if not share_a.writable or not share_b.writable:
            return SFTP_PERMISSION_DENIED
        if real_b.exists():
            return SFTP_FAILURE  # POSIX rename semantics: refuse to clobber
        try:
            os.rename(str(real_a), str(real_b))
        except OSError:
            return SFTP_FAILURE
        self.note("rename", f"{share_a.remote_root()}/{real_a.name} → {share_b.remote_root()}/{real_b.name}")
        return SFTP_OK

    def posix_rename(self, src: str, dest: str):
        a = self._resolve(self.canonicalize(src))
        b = self._resolve(self.canonicalize(dest))
        if a is None or b is None:
            return SFTP_NO_SUCH_FILE
        share_a, real_a = a
        share_b, real_b = b
        if not share_a.writable or not share_b.writable:
            return SFTP_PERMISSION_DENIED
        try:
            os.replace(str(real_a), str(real_b))
        except OSError:
            return SFTP_FAILURE
        self.note(
            "rename",
            f"{share_a.remote_root()}/{real_a.name} → {share_b.remote_root()}/{real_b.name} (overwrite)",
        )
        return SFTP_OK

    def mkdir(self, path: str, attr):
        found = self._resolve(self.canonicalize(path))
        if found is None:
            return SFTP_NO_SUCH_FILE
        share, real = found
        if not share.writable:
            return SFTP_PERMISSION_DENIED
        mode = stat_module.S_IMODE(getattr(attr, "st_mode", 0) or 0) or 0o755
        try:
            os.mkdir(str(real), mode)
        except OSError:
            return SFTP_FAILURE
        self.note("open", f"mkdir {share.remote_root()}/{real.name}")
        return SFTP_OK

    def rmdir(self, path: str):
        found = self._resolve(self.canonicalize(path))
        if found is None:
            return SFTP_NO_SUCH_FILE
        share, real = found
        if not share.writable:
            return SFTP_PERMISSION_DENIED
        try:
            os.rmdir(str(real))
        except OSError:
            return SFTP_FAILURE
        self.note("delete", f"rmdir {share.remote_root()}/{real.name}")
        return SFTP_OK

    def chattr(self, path: str, attr):
        found = self._resolve(self.canonicalize(path))
        if found is None:
            return SFTP_NO_SUCH_FILE
        share, real = found
        return self.apply_attr(share, real, attr)

    def apply_attr(self, share: ResolvedShare, real: Path, attr) -> int:
        """Apply an attribute change to an already-resolved path."""
        if not share.writable:
            return SFTP_PERMISSION_DENIED
        try:
            if getattr(attr, "st_mode", None):
                os.chmod(str(real), stat_module.S_IMODE(attr.st_mode))
            if getattr(attr, "st_mtime", None) is not None:
                os.utime(str(real), (time.time(), attr.st_mtime))
        except OSError:
            return SFTP_FAILURE
        return SFTP_OK

    # Refused on purpose: a symlink is exactly how a jailed server gets
    # walked out of its root, and this server has no use for them.
    def readlink(self, path: str):
        return SFTP_OP_UNSUPPORTED

    def symlink(self, target_path: str, path: str):
        return SFTP_OP_UNSUPPORTED

    # -- session lifecycle ----------------------------------------------
    def session_started(self):
        self.note("auth", "SFTP session opened")

    def session_ended(self):
        self.note("auth", "SFTP session closed")


# ----------------------------------------------------------------------
# Auth policy
# ----------------------------------------------------------------------
class _ShareAuthServer(paramiko.ServerInterface):
    """Password-only auth; file transfer only — no shell, no forwarding."""

    def __init__(self, share_server: SftpShareServer) -> None:
        self._server = share_server
        self.username = ""
        # Set once a client has authenticated; the connection thread waits on
        # it. (``Transport.start_server``'s own event only signals the end of
        # key exchange, so it cannot be used to gate on authentication.)
        self.authenticated = threading.Event()
        self.transport = None  # assigned by the connection thread

    # -- authentication --------------------------------------------------
    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def get_banner(self):
        banner = self._server.config.banner or DEFAULT_BANNER
        shares = ", ".join(e.name for e in self._server.registry.entries()) or "(none configured)"
        return f"{banner}\r\nShares: {shares}\r\n", "en-US"

    def _check_password(self, username: str, password: str) -> int:
        config = self._server.config
        peer = f"{self._server.peer_of(self)} as {username}"
        stored = config.password_hash
        if not stored:
            self._server.event("error", "login refused: no share password configured", peer)
            return AUTH_FAILED
        user_ok = hmac.compare_digest(
            (username or "").encode("utf-8"), (config.username or "").encode("utf-8")
        )
        pass_ok = verify_password(password or "", stored or _DUMMY_HASH)
        if user_ok and pass_ok:
            self.username = username
            self.authenticated.set()
            self._server.event("auth", f"user “{username}” authenticated", peer)
            log.info("share server: %s authenticated from %s", username, peer)
            return AUTH_SUCCESSFUL
        self._server.event("auth", f"rejected login attempt for “{username or '(empty)'}”", peer)
        log.warning("share server: rejected login for %r from %s", username, peer)
        return AUTH_FAILED

    def check_auth_password(self, username: str, password: str) -> int:
        return self._check_password(username, password)

    def check_auth_none(self, username: str) -> int:
        return AUTH_FAILED

    def check_auth_publickey(self, username: str, key) -> int:
        return AUTH_FAILED

    # -- channel policy --------------------------------------------------
    def check_channel_request(self, kind: str, chanid: int) -> int:
        if kind == "session":
            return OPEN_SUCCEEDED
        return OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_subsystem_request(self, channel, name: str) -> bool:
        # Only SFTP is served. The base implementation looks the handler up in
        # the transport's subsystem table *and starts it*, so it must do the
        # work — returning True here would leave the client talking to nobody.
        if name != "sftp":
            self._server.event("error", f"refused subsystem “{name}” (only sftp is served)")
            return False
        return super().check_channel_subsystem_request(channel, name)

    def check_channel_shell_request(self, channel) -> bool:
        self._server.event("error", "refused shell request")
        return False

    def check_channel_exec_request(self, channel, command) -> bool:
        self._server.event("error", "refused exec request")
        return False

    def check_channel_pty_request(self, channel, *args) -> bool:
        return False

    def check_channel_x11_request(self, channel, *args) -> bool:
        return False

    def check_channel_forward_agent_request(self, channel) -> bool:
        return False

    def check_channel_direct_tcpip_request(self, chanid, origin, destination) -> int:
        return OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_port_forward_request(self, address: str, port: int):
        return False

    def check_global_request(self, kind: str, msg):
        return False


# ----------------------------------------------------------------------
# The server
# ----------------------------------------------------------------------
class SftpShareServer:
    """A threaded SFTP listener over the shares in a :class:`ShareRegistry`."""

    def __init__(
        self,
        config: ShareServerConfig,
        registry: ShareRegistry,
        *,
        logger=None,
    ) -> None:
        self.config = config
        self.registry = registry
        self._log = logger or log
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._connections: set[_Connection] = set()
        self._events: deque[ShareEvent] = deque(maxlen=_EVENT_HISTORY)
        self._host_key: paramiko.PKey | None = None
        self._bound: tuple[str, int] | None = None
        self._last_error: str = ""
        registry.set_writable(config.allow_write)

    # -- lifecycle -------------------------------------------------------
    def start(self) -> None:
        """Bind and start accepting. Raises :class:`ShareServerError` on failure."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if not self.config.has_password():
                raise ShareServerError(
                    "Set a share password first (Settings → File sharing, or the share dialog)."
                )
            self._host_key = ensure_host_key(self.config.host_key_path or None)
            self._stop.clear()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((self.config.bind or DEFAULT_BIND, int(self.config.port)))
                sock.listen(8)
            except OSError as exc:
                sock.close()
                detail = _bind_hint(self.config.bind, self.config.port, exc)
                self._last_error = detail
                raise ShareServerError(detail) from exc
            sock.settimeout(1.0)
            self._sock = sock
            self._bound = sock.getsockname()[:2]
            self.registry.set_writable(self.config.allow_write)
            self._thread = threading.Thread(
                target=self._accept_loop, name="share-server", daemon=True
            )
            self._thread.start()
        self.event(
            "listen",
            f"listening on {self._bound[0]}:{self._bound[1]} "
            f"({len(self.registry.entries())} share(s), "
            f"{'read/write' if self.config.allow_write else 'read-only'})",
        )
        self._log.info("share server listening on %s:%s", self._bound[0], self._bound[1])

    def stop(self, timeout: float = 4.0) -> None:
        with self._lock:
            thread = self._thread
            sock = self._sock
            self._thread = None
            self._sock = None
            self._stop.set()
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        for conn in list(self._connections):
            conn.shutdown()
        if thread is not None:
            self.event("stop", "share server stopped")

    def restart(self) -> None:
        """Apply new settings to a running listener."""
        was_running = self.running
        if was_running:
            self.stop()
        self.registry.set_writable(self.config.allow_write)
        if was_running:
            self.start()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def address(self) -> tuple[str, int] | None:
        return self._bound if self.running else None

    def last_error(self) -> str:
        return self._last_error

    @property
    def host_key(self) -> paramiko.PKey | None:
        return self._host_key

    def fingerprint(self) -> str:
        if self._host_key is None:
            try:
                self._host_key = ensure_host_key(self.config.host_key_path or None)
            except OSError:
                return ""
        return key_fingerprint(self._host_key)

    def connection_count(self) -> int:
        with self._lock:
            return len(self._connections)

    def events(self) -> list[ShareEvent]:
        with self._lock:
            return list(self._events)

    def clear_events(self) -> None:
        with self._lock:
            self._events.clear()

    # -- client-facing helpers -------------------------------------------
    def lan_addresses(self) -> list[str]:
        """Plausible addresses a remote machine would dial (best effort)."""
        out: list[str] = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                addr = info[4][0]
                if addr not in out and not addr.startswith("127."):
                    out.append(addr)
        except OSError:
            pass
        if not out:
            try:  # the interface the default route lives on
                probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                try:
                    probe.connect(("8.8.8.8", 53))
                    out.append(probe.getsockname()[0])
                finally:
                    probe.close()
            except OSError:
                pass
        return out

    def display_address(self) -> str:
        """The address to show/copy: a LAN IP when bound to 0.0.0.0."""
        bound = self.address()
        if bound is None:
            return ""
        host, port = bound
        if host in ("0.0.0.0", "::"):
            candidates = self.lan_addresses()
            host = candidates[0] if candidates else "127.0.0.1"
        return f"{host}:{port}"

    def client_command(self, host: str | None = None) -> str:
        """The command to paste on the remote (Windows) machine."""
        port = (self.address() or ("", self.config.port))[1]
        target = host or self.display_address().split(":")[0] or "<this-machine-ip>"
        return f"sftp -P {port} {self.config.username}@{target}"

    def winscp_url(self, host: str | None = None) -> str:
        port = (self.address() or ("", self.config.port))[1]
        target = host or self.display_address().split(":")[0] or "<this-machine-ip>"
        return f"sftp://{self.config.username}@{target}:{port}/"

    # -- plumbing used by the handlers -----------------------------------
    def event(self, kind: str, detail: str, peer: str = "") -> None:
        with self._lock:
            self._events.append(ShareEvent(time.time(), kind, detail, peer))
        if kind == "error":
            self._log.warning("share server: %s", detail)
        else:
            self._log.debug("share server: %s %s", kind, detail)

    def peer_of(self, server_interface: Any) -> str:
        transport = getattr(server_interface, "transport", None)
        try:
            peername = transport.getpeername() if transport is not None else None
        except Exception:  # pragma: no cover - defensive
            peername = None
        if isinstance(peername, tuple) and peername:
            return f"{peername[0]}:{peername[1]}"
        return ""

    def _register(self, conn: _Connection) -> bool:
        with self._lock:
            if self._stop.is_set():
                return False
            if len(self._connections) >= max(1, int(self.config.max_connections or MAX_CONNECTIONS)):
                return False
            self._connections.add(conn)
            return True

    def _forget(self, conn: _Connection) -> None:
        with self._lock:
            self._connections.discard(conn)

    def _accept_loop(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                client, addr = sock.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._stop.is_set():
                    return
                self.event("error", "listener socket failed; server stopping")
                return
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn = _Connection(client, addr, self)
            if not self._register(conn):
                self.event("error", f"refused connection from {addr[0]} (limit reached)")
                try:
                    client.close()
                except OSError:
                    pass
                continue
            conn.start()


class _Connection(threading.Thread):
    """One SSH transport per connecting client."""

    def __init__(self, sock: socket.socket, addr, share_server: SftpShareServer) -> None:
        super().__init__(name=f"share-conn-{addr[0]}", daemon=True)
        self._sock = sock
        self._addr = addr
        self._peer_label = f"{addr[0]}:{addr[1]}"
        self._server = share_server
        self._transport: Transport | None = None

    def run(self) -> None:
        transport: Transport | None = None
        try:
            transport = Transport(self._sock)
            self._transport = transport
            transport.banner_timeout = 30.0
            transport.auth_timeout = _AUTH_TIMEOUT
            transport.add_server_key(self._server.host_key)
            transport.set_subsystem_handler(
                "sftp", SFTPServer, sftp_si=_ShareSFTPBackend, share_server=self._server
            )
            auth = _ShareAuthServer(self._server)
            auth.transport = transport
            transport.start_server(server=auth)
            if not auth.authenticated.wait(timeout=_AUTH_TIMEOUT):
                if transport.is_active():
                    self._server.event("error", f"no successful auth from {self._peer_label}")
                return
            self._server.event("open", "client connected", self._peer_label)
            self._wait_for_disconnect(transport)
        except Exception as exc:  # noqa: BLE001 - a bad client must not kill us
            self._server.event("error", f"{self._peer_label}: {exc.__class__.__name__}: {exc}")
        finally:
            if transport is not None:
                try:
                    transport.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                self._sock.close()
            except OSError:
                pass
            self._server._forget(self)
            self._server.event("open", "client disconnected", self._peer_label)

    def _wait_for_disconnect(self, transport: Transport) -> None:
        """Park until the client hangs up or the server is stopped.

        paramiko drives the SFTP subsystem on its own threads; this thread
        only owns the transport's lifetime.  Polling is cheap (4 Hz) and keeps
        shutdown responsive without needing a transport-level callback.
        """
        while not self._server._stop.is_set() and transport.is_active():
            time.sleep(0.25)

    def shutdown(self) -> None:
        transport = self._transport
        if transport is not None:
            try:
                transport.close()
            except Exception:  # noqa: BLE001
                pass


def _bind_hint(bind: str, port: int, exc: OSError) -> str:
    errno = getattr(exc, "errno", None)
    if errno == 13:  # EACCES
        return (
            f"Cannot bind {bind}:{port} — permission denied. "
            "Use a port above 1024, or start the service with elevated rights."
        )
    if errno == 98 or errno == 10048:  # EADDRINUSE (POSIX / Windows)
        return (
            f"Port {port} is already in use. Another program (or another KB-Remote "
            "instance) is listening on it — pick a different port in Settings → File sharing."
        )
    if errno in (99, 10049):  # EADDRNOTAVAIL
        return (
            f"Cannot bind {bind}:{port} — that address is not on this machine. "
            "Use 0.0.0.0 (all interfaces) or one of this machine's own addresses."
        )
    return f"Cannot listen on {bind}:{port}: {exc}"


__all__ = [
    "DEFAULT_BIND",
    "DEFAULT_PORT",
    "DEFAULT_USERNAME",
    "ShareEvent",
    "ShareServerError",
    "ShareServerConfig",
    "SftpShareServer",
    "ensure_host_key",
    "hash_password",
    "key_fingerprint",
    "verify_password",
]


# ----------------------------------------------------------------------
# Service: the one object the GUI and the session controllers talk to
# ----------------------------------------------------------------------
class ShareService:
    """Bind the share server to the application's settings + registry.

    The UI, the RDP session controller and the tests all drive the server
    through this object, so there is exactly one place where a
    :class:`~rdpstudio.core.settings.Settings` object becomes a running
    listener.
    """

    def __init__(self, settings, registry: ShareRegistry | None = None) -> None:
        from ..core.shares import shares_from_dicts

        self.settings = settings
        self.registry = registry or ShareRegistry()
        self.server = SftpShareServer(self._config_from_settings(), self.registry)
        self._global_shares = shares_from_dicts(getattr(settings, "share_server_shares", []))
        self.registry.set_global(self._global_shares, self.server.config.allow_write)

    # -- settings <-> config ---------------------------------------------
    def _config_from_settings(self) -> ShareServerConfig:
        s = self.settings
        return ShareServerConfig(
            enabled=bool(getattr(s, "share_server_enabled", False)),
            bind=str(getattr(s, "share_server_bind", DEFAULT_BIND) or DEFAULT_BIND),
            port=int(getattr(s, "share_server_port", DEFAULT_PORT) or DEFAULT_PORT),
            username=str(getattr(s, "share_server_user", DEFAULT_USERNAME) or DEFAULT_USERNAME),
            password_hash=str(getattr(s, "share_server_password", "") or ""),
            host_key_path="",
            allow_write=bool(getattr(s, "share_server_writable", True)),
        )

    def reload_settings(self, settings=None) -> None:
        """Pick up edits made in Settings; a running listener is restarted."""
        if settings is not None:
            self.settings = settings
        from ..core.shares import shares_from_dicts

        self._global_shares = shares_from_dicts(getattr(self.settings, "share_server_shares", []))
        self.server.config = self._config_from_settings()
        self.registry.set_global(self._global_shares, self.server.config.allow_write)

    def save_settings(self) -> None:
        """Write the live configuration back into the Settings object."""
        cfg = self.server.config
        s = self.settings
        s.share_server_enabled = cfg.enabled
        s.share_server_bind = cfg.bind
        s.share_server_port = cfg.port
        s.share_server_user = cfg.username
        s.share_server_password = cfg.password_hash
        s.share_server_writable = cfg.allow_write
        s.share_server_shares = [share.to_dict() for share in self._global_shares]

    # -- shares -----------------------------------------------------------
    def global_shares(self) -> list:
        return [share.copy() for share in self._global_shares]

    def set_global_shares(self, shares: list) -> None:
        self._global_shares = [share.copy() for share in shares]
        self.settings.share_server_shares = [share.to_dict() for share in self._global_shares]
        self.registry.set_global(self._global_shares, self.server.config.allow_write)

    def publish_session(self, session_id: str, label: str, shares: list) -> None:
        """Offer a session's own folders while its tab is open."""
        self.registry.set_session(session_id, label, list(shares))

    def forget_session(self, session_id: str) -> None:
        self.registry.remove_session(session_id)

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        self.server.config.enabled = True
        self.settings.share_server_enabled = True
        self.server.start()

    def stop(self) -> None:
        self.server.config.enabled = False
        self.settings.share_server_enabled = False
        self.server.stop()

    def ensure_running(self) -> bool:
        """Start the listener if the user asked for it (autostart).

        Never raises: a share server that cannot bind must not stop an RDP
        session from connecting. Returns whether it is listening afterwards.
        """
        if self.server.running:
            return True
        if not (
            getattr(self.settings, "share_server_enabled", False)
            or getattr(self.settings, "share_server_autostart", False)
        ):
            return False
        try:
            self.start()
            return True
        except ShareServerError as exc:
            log.warning("share server autostart failed: %s", exc)
            self.server.event("error", f"autostart failed: {exc}")
            return False

    def set_password(self, password: str, iterations: int = KDF_ITERATIONS) -> None:
        self.server.config.password_hash = hash_password(password, iterations)
        self.settings.share_server_password = self.server.config.password_hash

    def has_password(self) -> bool:
        return bool(self.server.config.password_hash)

    # -- presentation -----------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """UI/test-friendly view of the current state."""
        address = self.server.address()
        return {
            "running": self.server.running,
            "address": f"{address[0]}:{address[1]}" if address else "",
            "display_address": self.server.display_address(),
            "shares": [
                {"name": e.name, "path": str(e.path), "scope": e.scope, "source": e.source}
                for e in self.registry.entries()
            ],
            "clients": self.server.connection_count(),
            "fingerprint": self.server.fingerprint(),
            "username": self.server.config.username,
            "command": self.server.client_command(),
            "winscp": self.server.winscp_url(),
            "writable": self.server.config.allow_write,
            "events": [e.to_dict() for e in self.server.events()[-50:]],
        }


__all__.append("ShareService")
