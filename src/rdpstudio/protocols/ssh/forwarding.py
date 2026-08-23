"""Port forwarding over a paramiko Transport.

Supported forward kinds:

- ``local``   : listen on a local socket; each connection opens a
                ``direct-tcpip`` channel through the SSH server to ``dest``.
- ``remote``  : ask the server to listen (``request_port_forward``); incoming
                server-side connections are bridged to a local destination.
- ``dynamic`` : local SOCKS5 proxy; the destination is chosen per request.

Everything runs on daemon threads owned by :class:`TunnelManager`; events are
reported through a callback so the owning worker can forward them to the GUI.
"""

from __future__ import annotations

import select
import socket
import struct
import threading
from dataclasses import dataclass, field

import paramiko

from ...core.log import get_logger
from ...core.models import Forward

log = get_logger("ssh.forward")


class TunnelError(RuntimeError):
    pass


EventCb = object  # callable(kind: str, payload: dict) -> None


@dataclass
class _LocalTunnel:
    fwd: Forward
    listener: socket.socket
    accept_thread: threading.Thread | None = None
    conns: set = field(default_factory=set)
    stopping: bool = False
    actual_port: int = 0
    error: str = ""


class TunnelManager:
    """Owns all forwards for one SSH transport. Not thread-safe across managers,
    but each manager is confined to its owning worker thread; per-connection
    work happens on dedicated daemon threads."""

    def __init__(self, transport: paramiko.Transport, on_event: EventCb | None = None) -> None:
        self.transport = transport
        self.on_event = on_event or (lambda *a: None)
        self._locals: dict[int, _LocalTunnel] = {}  # listen_port -> tunnel
        self._remotes: dict[int, tuple[Forward, str]] = {}  # server port -> (fwd, address)
        self._conn_threads: set[threading.Thread] = set()

    # ------------------------------------------------------------------
    def start(self, fwd: Forward) -> int:
        if fwd.kind == "remote":
            return self.start_remote(fwd)
        return self.start_local(fwd)

    def start_local(self, fwd: Forward) -> int:
        if fwd.listen_port and fwd.listen_port in self._locals:
            raise TunnelError(f"port {fwd.listen_port} already forwarded locally")
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((fwd.listen_host or "127.0.0.1", fwd.listen_port))
            listener.listen(16)
        except OSError as exc:
            listener.close()
            raise TunnelError(f"cannot listen on {fwd.listen_host}:{fwd.listen_port}: {exc}") from exc
        listener.settimeout(0.5)
        tunnel = _LocalTunnel(fwd=fwd, listener=listener, actual_port=listener.getsockname()[1])
        self._locals[tunnel.actual_port] = tunnel
        tunnel.accept_thread = threading.Thread(
            target=self._accept_loop, args=(tunnel,), daemon=True, name=f"tunnel-l{tunnel.actual_port}"
        )
        tunnel.accept_thread.start()
        self.on_event("started", self.describe(tunnel.actual_port))
        return tunnel.actual_port

    def start_remote(self, fwd: Forward) -> int:
        if not fwd.dest_port:
            raise TunnelError("remote forward needs a destination port")
        try:
            bound = self.transport.request_port_forward(
                fwd.listen_host or "", fwd.listen_port or 0, handler=self._remote_handler(fwd)
            )
        except paramiko.SSHException as exc:
            raise TunnelError(f"server refused remote forward: {exc}") from exc
        # request_port_forward() returns (address, port) — the port is the
        # *second* element (the server picks it when we asked for port 0).
        port = int(bound[1]) if isinstance(bound, tuple) else int(bound or fwd.listen_port)
        self._remotes[port] = (fwd, fwd.listen_host or "")
        self.on_event("started", {"port": port, "kind": "remote", "label": fwd.label()})
        return port

    def stop_port(self, port: int) -> None:
        tunnel = self._locals.pop(port, None)
        if tunnel:
            tunnel.stopping = True
            try:
                tunnel.listener.close()
            except OSError:
                pass
            for conn in list(tunnel.conns):
                try:
                    conn.close()
                except OSError:
                    pass
            self.on_event("stopped", {"port": port, "kind": "local", "label": tunnel.fwd.label()})
        if port in self._remotes:
            fwd, addr = self._remotes.pop(port)
            try:
                self.transport.cancel_port_forward(addr, port)
            except Exception:  # noqa: BLE001
                pass
            self.on_event("stopped", {"port": port, "kind": "remote", "label": fwd.label()})

    def stop_all(self) -> None:
        for port in list(self._locals):
            self.stop_port(port)
        for port in list(self._remotes):
            self.stop_port(port)

    def describe(self, port: int) -> dict:
        tunnel = self._locals.get(port)
        if tunnel:
            return {
                "port": port,
                "kind": tunnel.fwd.kind,
                "label": tunnel.fwd.label(),
                "error": tunnel.error,
            }
        if port in self._remotes:
            fwd, _ = self._remotes[port]
            return {"port": port, "kind": "remote", "label": fwd.label(), "error": ""}
        return {"port": port, "kind": "?", "label": "", "error": "unknown"}

    def active_ports(self) -> list[dict]:
        return [self.describe(p) for p in sorted({*self._locals, *self._remotes})]

    # ------------------------------------------------------------------
    def _accept_loop(self, tunnel: _LocalTunnel) -> None:
        while not tunnel.stopping:
            try:
                conn, addr = tunnel.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            tunnel.conns.add(conn)
            t = threading.Thread(
                target=self._serve_local_conn, args=(tunnel, conn, addr), daemon=True
            )
            t.start()
            self._conn_threads.add(t)

    def _serve_local_conn(self, tunnel: _LocalTunnel, conn: socket.socket, addr) -> None:
        fwd = tunnel.fwd
        chan: paramiko.Channel | None = None
        try:
            if fwd.kind == "dynamic":
                target = _socks5_handshake(conn)
                if target is None:
                    return
                dest_host, dest_port = target
            else:
                dest_host, dest_port = fwd.dest_host, fwd.dest_port

            chan = self.transport.open_channel(
                "direct-tcpip",
                (dest_host, int(dest_port)),
                (addr[0], addr[1]),
                timeout=15,
            )
            if fwd.kind == "dynamic":
                _socks5_reply_ok(conn)
            self._pump(conn, chan)
        except Exception as exc:  # noqa: BLE001
            if fwd.kind == "dynamic":
                try:
                    _socks5_reply_err(conn)
                except Exception:  # noqa: BLE001
                    pass
            tunnel.error = str(exc)
            self.on_event("error", {"label": fwd.label(), "error": str(exc)})
        finally:
            tunnel.conns.discard(conn)
            try:
                conn.close()
            except OSError:
                pass
            if chan is not None:
                try:
                    chan.close()
                except Exception:  # noqa: BLE001
                    pass

    def _remote_handler(self, fwd: Forward):
        def handler(channel: paramiko.Channel, origin) -> None:
            t = threading.Thread(
                target=self._serve_remote_conn, args=(fwd, channel, origin), daemon=True
            )
            t.start()
            self._conn_threads.add(t)

        return handler

    def _serve_remote_conn(self, fwd: Forward, channel: paramiko.Channel, origin) -> None:
        sock: socket.socket | None = None
        try:
            dest_host = fwd.dest_host or "127.0.0.1"
            dest_port = int(fwd.dest_port)
            sock = socket.create_connection((dest_host, dest_port), timeout=10)
            self._pump(sock, channel)
        except Exception as exc:  # noqa: BLE001
            self.on_event("error", {"label": fwd.label(), "error": str(exc)})
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
            try:
                channel.close()
            except Exception:  # noqa: BLE001
                pass

    @staticmethod
    def _pump(sock: socket.socket, chan: paramiko.Channel) -> None:
        """Copy bytes between a socket and a channel until either side closes."""
        sock.settimeout(0.0)
        chan.settimeout(0.0)
        while True:
            try:
                r, _, _ = select.select([sock, chan], [], [], 0.5)
            except (OSError, ValueError):
                break
            if sock in r:
                try:
                    data = sock.recv(65536)
                except (BlockingIOError, InterruptedError):
                    data = None
                except OSError:
                    break
                if data:
                    _send_all_chan(chan, data)
                elif data == b"":
                    break
            if chan in r:
                if chan.recv_ready():
                    data = chan.recv(65536)
                    if data:
                        if not _send_all_sock(sock, data):
                            break
                    else:
                        break
                if chan.closed and not chan.recv_ready():
                    break
            if chan.closed:
                break


def _send_all_chan(chan: paramiko.Channel, data: bytes) -> bool:
    view = memoryview(data)
    while view:
        try:
            if chan.send_ready():
                n = chan.send(view)
                if n <= 0:
                    return False
                view = view[n:]
            else:
                import time

                time.sleep(0.01)
        except Exception:  # noqa: BLE001
            return False
    return True


def _send_all_sock(sock: socket.socket, data: bytes) -> bool:
    view = memoryview(data)
    while view:
        try:
            n = sock.send(view)
            if n <= 0:
                return False
            view = view[n:]
        except (BlockingIOError, InterruptedError):
            import time

            time.sleep(0.01)
        except OSError:
            return False
    return True


# ----------------------------------------------------------------------
# Minimal SOCKS5 server (CONNECT only, no auth) for dynamic forwards.
# ----------------------------------------------------------------------
def _socks5_handshake(conn: socket.socket) -> tuple[str, int] | None:
    conn.settimeout(30)
    header = _recv_exact(conn, 2)
    ver, nmethods = header[0], header[1]
    if ver != 5:
        return None
    _recv_exact(conn, nmethods)  # methods; we only support NO AUTH
    conn.sendall(b"\x05\x00")

    req = _recv_exact(conn, 4)
    ver, cmd, _rsv, atyp = req
    if ver != 5 or cmd != 0x01:  # only CONNECT
        conn.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
        return None
    if atyp == 0x01:
        addr = socket.inet_ntoa(_recv_exact(conn, 4))
    elif atyp == 0x03:
        length = _recv_exact(conn, 1)[0]
        raw = _recv_exact(conn, length)
        try:
            addr = raw.decode("idna")
        except (UnicodeError, ValueError):
            # Not IDNA-clean (e.g. names with underscores) — pass the raw
            # label through; the resolver handles it.
            addr = raw.decode("utf-8", "replace")
    elif atyp == 0x04:
        import ipaddress

        addr = str(ipaddress.IPv6Address(_recv_exact(conn, 16)))
    else:
        return None
    port = struct.unpack(">H", _recv_exact(conn, 2))[0]
    return addr, int(port)


def _socks5_reply_ok(conn: socket.socket) -> None:
    conn.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")


def _socks5_reply_err(conn: socket.socket) -> None:
    conn.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")


def _recv_exact(conn: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socks peer closed")
        buf += chunk
    return buf
