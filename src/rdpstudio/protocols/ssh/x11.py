"""SSH X11 forwarding: bridge remote X11 channels to the local display.

``ssh -X`` sends the server a random ("fake") MIT-MAGIC-COOKIE-1 and rewrites
it to the local display's real cookie on every incoming connection.  This
module does the same for a paramiko shell channel:

* :func:`local_display` parses ``$DISPLAY``.
* :func:`real_cookie` reads the display's cookie with ``xauth``.
* :func:`rewrite_auth_cookie` substitutes it in the X11 setup packet.
* :func:`handle_connection` is the paramiko X11 handler and bridges bytes
  between the SSH channel and the local X server socket.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import socket
import struct
import subprocess
import threading

from ...core.log import debug_ratelimited, get_logger

log = get_logger("ssh.x11")

_DISPLAY_RE = re.compile(r"^(?P<host>[^:]*):(?P<num>\d+)(?:\.\d+)?$")
_SETUP_MIN = 12  # X11 connection-setup fixed header


def local_display() -> tuple[str, int] | None:
    """Return ``(host, display_number)`` for ``$DISPLAY``, or None."""
    raw = (os.environ.get("DISPLAY") or "").strip()
    match = _DISPLAY_RE.match(raw)
    if not match:
        return None
    return match.group("host"), int(match.group("num"))


def real_cookie(display: tuple[str, int]) -> bytes | None:
    """Read the display's MIT-MAGIC-COOKIE-1 via ``xauth list``."""
    xauth = shutil.which("xauth")
    if not xauth:
        return None
    host, num = display
    name = f"{host or 'unix'}:{num}"

    def _match(out: str, want_display: bool) -> bytes | None:
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 3 or parts[-2] != "MIT-MAGIC-COOKIE-1":
                continue
            if want_display:
                try:
                    entry_num = int(parts[0].rsplit(":", 1)[1].split(".")[0])
                except (IndexError, ValueError):
                    continue
                if entry_num != num:
                    continue
            try:
                cookie = bytes.fromhex(parts[-1])
            except ValueError:
                continue
            if cookie:
                return cookie
        return None

    try:
        out = subprocess.run(
            [xauth, "list", name],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        debug_ratelimited(log, "xauth-list", "xauth list failed: %s", exc)
        return None
    cookie = _match(out, want_display=False)
    if cookie is not None:
        return cookie
    # xauth's name matching varies (":0" vs "host/unix:0"); fall back to all.
    try:
        out = subprocess.run(
            [xauth, "list"], capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return _match(out, want_display=True)


def rewrite_auth_cookie(setup: bytes, cookie: bytes | None) -> bytes:
    """Replace the auth data of an X11 connection-setup packet.

    Only a 16-byte MIT-MAGIC-COOKIE-1 is replaced; anything else (no auth,
    different protocol, truncated packet) is returned untouched.
    """
    if not cookie or len(setup) < _SETUP_MIN:
        return setup
    order = setup[:1]
    fmt = {b"B": ">BBHHHHH", b"l": "<BBHHHHH"}.get(order)
    if fmt is None:
        return setup
    _b, _pad, _maj, _min, name_len, data_len, _pad2 = struct.unpack(fmt, setup[:_SETUP_MIN])
    name_start = _SETUP_MIN
    name_end = name_start + name_len
    data_start = name_start + ((name_len + 3) // 4) * 4
    data_end = data_start + data_len
    if data_end > len(setup) or data_len != len(cookie):
        return setup
    if setup[name_start:name_end] != b"MIT-MAGIC-COOKIE-1":
        return setup
    return setup[:data_start] + cookie + setup[data_end:]


def _connect_local(display: tuple[str, int]) -> socket.socket | None:
    host, num = display
    candidates: list = []
    if host in ("", "unix"):
        candidates.append(("unix", f"/tmp/.X11-unix/X{num}"))
        candidates.append(("tcp", ("127.0.0.1", 6000 + num)))
    else:
        candidates.append(("tcp", (host, 6000 + num)))
    for kind, addr in candidates:
        sock = None
        try:
            if kind == "unix":
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(3)
                sock.connect(addr)
            else:
                sock = socket.create_connection(addr, timeout=3)
            sock.settimeout(None)
            return sock
        except OSError as exc:
            debug_ratelimited(log, "connect-local", "local X connect failed: %s", exc)
            try:
                sock.close()
            except Exception:  # noqa: BLE001 - best effort
                pass
    return None


def _recv_exact(chan, count: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < count:
        chunk = chan.recv(count - len(buf))
        if not chunk:
            return None
        buf += chunk
    return bytes(buf)


def _send_all(chan, data: bytes) -> bool:
    while data:
        try:
            sent = chan.send(data)
        except Exception:  # noqa: BLE001 - channel closed
            return False
        if sent <= 0:
            return False
        data = data[sent:]
    return True


def _bridge(chan, sock: socket.socket, display: tuple[str, int], cookie: bytes | None) -> None:
    try:
        header = _recv_exact(chan, _SETUP_MIN)
        if header is None:
            return
        order = header[:1]
        fmt = {b"B": ">BBHHHHH", b"l": "<BBHHHHH"}.get(order)
        if fmt is None:
            sock.sendall(header)
            rest = b""
        else:
            _b, _pad, _maj, _min, name_len, data_len, _pad2 = struct.unpack(fmt, header)
            rest = _recv_exact(chan, ((name_len + 3) // 4) * 4 + ((data_len + 3) // 4) * 4)
            if rest is None:
                return
        sock.sendall(rewrite_auth_cookie(header + rest, cookie))

        while True:
            if chan.recv_ready():
                data = chan.recv(65536)
                if not data:
                    break
                sock.sendall(data)
            if sock in select.select([sock], [], [], 0)[0]:
                data = sock.recv(65536)
                if not data:
                    break
                if not _send_all(chan, data):
                    break
            if chan.closed or chan.eof_received:
                break
            # Poll the SSH channel at 20 ms: paramiko does not expose a
            # per-channel fd, and watching the shared transport socket would
            # spin whenever any other channel has traffic.
            try:
                select.select([sock], [], [], 0.02)
            except (OSError, ValueError):
                break
    except Exception as exc:  # noqa: BLE001 - one X11 client must not hurt the shell
        debug_ratelimited(log, "x11-bridge", "X11 bridge ended: %s", exc)
    finally:
        for closer in (
            lambda: sock.close(),
            lambda: chan.close(),
        ):
            try:
                closer()
            except Exception:  # noqa: BLE001 - best effort
                pass


def handle_connection(chan, address, display: tuple[str, int] | None = None) -> None:
    """Paramiko X11 handler: bridge one remote client to the local display.

    Called from paramiko's transport thread — connect + handshake + copy run
    on a dedicated daemon thread so the SSH transport is never blocked.
    """
    display = display or local_display()
    if display is None:
        log.warning("X11 request ignored: no local DISPLAY")
        try:
            chan.close()
        except Exception:  # noqa: BLE001 - best effort
            pass
        return
    cookie = real_cookie(display)
    if cookie is None:
        log.warning("X11 request: no MIT-MAGIC-COOKIE-1 for %s (server may deny it)", display)
    sock = _connect_local(display)
    if sock is None:
        log.warning("X11 request ignored: cannot reach local display %s", display)
        try:
            chan.close()
        except Exception:  # noqa: BLE001 - best effort
            pass
        return
    threading.Thread(
        target=_bridge,
        args=(chan, sock, display, cookie),
        name="ssh-x11-bridge",
        daemon=True,
    ).start()


__all__ = [
    "handle_connection",
    "local_display",
    "real_cookie",
    "rewrite_auth_cookie",
]
