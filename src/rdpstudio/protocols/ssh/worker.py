"""SSH transport worker.

An :class:`SshWorker` is a QObject moved to a dedicated ``QThread``. All
paramiko blocking work (connect, auth, shell pump, forwards) happens there;
the GUI thread talks to it through queued slots and receives Qt signals.
"""

from __future__ import annotations

import select
import threading
import time
from collections import deque
from pathlib import Path

import paramiko
from PySide6.QtCore import QObject, Signal, Slot

from ...core.log import get_logger, redact_secret
from ...core.models import Forward
from .forwarding import TunnelError, TunnelManager
from .knownhosts import KnownHostsVerifier

log = get_logger("ssh.worker")

_MAX_PENDING_WRITES = 8 * 1024 * 1024  # cap buffered user input


class AuthMaterial:
    """Everything the worker may need to authenticate one hop.

    ``jump`` chains to another AuthMaterial for the *previous* hop
    (ProxyJump-style): hopN's transport is opened through hop(N-1)'s.
    """

    def __init__(
        self,
        host: str = "",
        port: int = 22,
        username: str = "",
        password: str | None = None,
        key_path: str = "",
        key_passphrase: str | None = None,
        allow_agent: bool = True,
        jump: AuthMaterial | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_path = key_path
        self.key_passphrase = key_passphrase
        self.allow_agent = allow_agent
        self.jump = jump


class SshWorker(QObject):
    # --- lifecycle ------------------------------------------------------
    connected = Signal(dict)        # info: banner, cipher, remote_version...
    disconnected = Signal(str)      # reason ("" when user-requested)
    failed = Signal(str)            # fatal error text
    stateInfo = Signal(str)         # transient human status ("authenticating…")

    # --- terminal --------------------------------------------------------
    output = Signal(bytes)
    ptyClosed = Signal(str)

    # --- forwards ---------------------------------------------------------
    forwardEvent = Signal(dict)     # {"event": started|stopped|error, ...}

    def __init__(self, host: str, port: int, material: AuthMaterial,
                 known_hosts_path: Path, host_key_policy: str,
                 prompter,  # PromptProvider, must be thread-safe
                 keepalive: int = 30, compression: bool = True,
                 timeout: int = 10, term_size: tuple[int, int] = (80, 24),
                 startup_command: str = "") -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.material = material
        self.known_hosts_path = known_hosts_path
        self.host_key_policy = host_key_policy
        self.prompter = prompter
        self.keepalive = keepalive
        self.compression = compression
        self.timeout = timeout
        self.term_size = term_size
        self.startup_command = startup_command

        self._client: paramiko.SSHClient | None = None
        self._hop_clients: list[paramiko.SSHClient] = []
        self._chan: paramiko.Channel | None = None
        self._tunnels: TunnelManager | None = None
        self._writes: deque[bytes] = deque()
        self._write_bytes = 0
        self._write_lock = threading.Lock()
        self._stop = threading.Event()
        self._shell_requested = False
        self._pty_size = term_size

    # ------------------------------------------------------------------
    # slots invoked (queued) from the GUI thread
    # ------------------------------------------------------------------
    @Slot()
    def connect_and_shell(self) -> None:
        """Connect (incl. jump chain + auth), open PTY shell, start pump."""
        try:
            self._client = self._connect(self.material, self.host, self.port)
        except Exception as exc:  # noqa: BLE001
            log.exception("connect failed")
            self.failed.emit(str(exc))
            self._cleanup()
            return

        if self._stop.is_set():
            return
        try:
            self._open_shell()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(f"could not open shell: {exc}")
            self._cleanup()
            return
        self._pump()

    @Slot(bytes)
    def write_input(self, data: bytes) -> None:
        with self._write_lock:
            if self._write_bytes < _MAX_PENDING_WRITES:
                self._write_bytes += len(data)
                self._writes.append(data)
            else:
                log.warning("dropping input: pending write buffer full")

    @Slot(int, int)
    def resize_pty(self, cols: int, rows: int) -> None:
        self._pty_size = (cols, rows)
        chan = self._chan
        if chan is not None:
            try:
                chan.resize_pty(cols, rows)
            except Exception:  # noqa: BLE001
                pass

    @Slot(dict)
    def start_forward(self, fwd_dict: dict) -> None:
        fwd = Forward.from_dict(fwd_dict)
        try:
            port = self.tunnels().start(fwd)
            self.forwardEvent.emit({"event": "bound", "requested": fwd.listen_port, "port": port})
        except TunnelError as exc:
            self.forwardEvent.emit({"event": "error", "label": fwd.label(), "error": str(exc)})

    @Slot(int)
    def stop_forward(self, port: int) -> None:
        if self._tunnels:
            self._tunnels.stop_port(port)

    @Slot(str)
    def shutdown(self, reason: str = "") -> None:
        self._stop.set()
        self._cleanup()
        self.disconnected.emit(reason if reason else "")

    def request_stop(self) -> None:
        """Thread-safe, non-blocking stop request from any thread."""
        self._stop.set()
        chan = self._chan
        if chan is not None:
            try:
                chan.close()  # unblocks the pump immediately
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def tunnels(self) -> TunnelManager:
        assert self._client is not None
        if self._tunnels is None:
            transport = self._client.get_transport()
            assert transport is not None
            self._tunnels = TunnelManager(transport, on_event=self._on_tunnel_event)
        return self._tunnels

    def transport(self) -> paramiko.Transport | None:
        if self._client is not None:
            return self._client.get_transport()
        return None

    def _on_tunnel_event(self, kind: str, payload: dict) -> None:
        payload = dict(payload)
        payload["event"] = kind
        self.forwardEvent.emit(payload)

    def _connect(self, material: AuthMaterial, host: str | None = None, port: int | None = None) -> paramiko.SSHClient:
        host = host or material.host
        port = port or material.port
        sock = None
        if material.jump is not None:
            self.stateInfo.emit("connecting via jump host…")
            hop = self._connect(material.jump)
            self._hop_clients.append(hop)
            hop_transport = hop.get_transport()
            assert hop_transport is not None
            sock = hop_transport.open_channel(
                "direct-tcpip", (host, port), ("rdpstudio-jump", 0), timeout=self.timeout
            )
        client = paramiko.SSHClient()
        verifier = KnownHostsVerifier(self.known_hosts_path, self.host_key_policy, self.prompter)
        client.set_missing_host_key_policy(verifier)
        kwargs: dict = dict(
            hostname=host,
            port=port,
            timeout=self.timeout,
            allow_agent=False,
            look_for_keys=False,
            sock=sock,
        )
        if material.username:
            kwargs["username"] = material.username
        if self.compression:
            kwargs["compress"] = True

        password_attempts = 0
        while True:
            # Build a candidate list for this round.
            pkey = None
            if material.key_path:
                from .keys import load_key

                passphrase = material.key_passphrase
                while True:
                    try:
                        pkey = load_key(material.key_path, passphrase)
                        break
                    except paramiko.PasswordRequiredException:
                        answer = self.prompter.ask_secret(
                            "Key passphrase",
                            f"Passphrase for {material.key_path}:",
                            secret=True,
                        )
                        if answer is None:
                            raise paramiko.AuthenticationException(
                                "passphrase entry cancelled"
                            ) from None
                        passphrase = answer
                        material.key_passphrase = answer
                    except Exception as exc:
                        raise paramiko.AuthenticationException(
                            f"cannot load key {material.key_path}: {exc}"
                        ) from exc
            agent_pkeys: list[paramiko.PKey] = []
            if material.allow_agent:
                try:
                    agent = paramiko.Agent()
                    agent_pkeys = list(agent.get_keys() or ())
                    agent.close()
                except Exception:  # noqa: BLE001
                    agent_pkeys = []

            tried = []
            for candidate in [*agent_pkeys, *([pkey] if pkey else [])]:
                kwargs["pkey"] = candidate
                kwargs.pop("password", None)
                tried.append(candidate.get_name())
                try:
                    client.connect(**kwargs)
                    self._announce(client)
                    return client
                except paramiko.AuthenticationException:
                    continue
                except Exception:
                    raise
            kwargs.pop("pkey", None)
            if material.password:
                redact_secret(material.password)
                kwargs["password"] = material.password
                try:
                    client.connect(**kwargs)
                    self._announce(client)
                    return client
                except paramiko.AuthenticationException:
                    material.password = None

            # Nothing worked: interactive password prompt (max 3 rounds).
            if password_attempts >= 3:
                tried_txt = ", ".join(dict.fromkeys(tried)) or "none"
                raise paramiko.AuthenticationException(
                    f"authentication failed (tried: {tried_txt})"
                )
            password_attempts += 1
            self.stateInfo.emit("authentication required…")
            answer = self.prompter.ask_secret(
                "SSH password", f"Password for {material.username or 'user'}@{host}:{port}",
                secret=True,
            )
            if answer is None:
                raise paramiko.AuthenticationException("password entry cancelled")
            redact_secret(answer)
            material.password = answer
            kwargs["password"] = answer

    def _announce(self, client: paramiko.SSHClient) -> None:
        transport = client.get_transport()
        assert transport is not None
        info = {
            "host": f"{self.host}:{self.port}",
            "username": transport.get_username() or "",
            "cipher": transport.local_cipher or "",
            "remote_version": transport.remote_version or "",
            "banner": transport.get_banner() or "",
        }
        self.connected.emit(info)

    def _open_shell(self) -> None:
        assert self._client is not None
        transport = self._client.get_transport()
        assert transport is not None
        transport.set_keepalive(max(5, self.keepalive))
        chan = transport.open_session(timeout=self.timeout)
        chan.get_pty("xterm-256color", self._pty_size[0], self._pty_size[1])
        chan.invoke_shell()
        self._chan = chan
        self._shell_requested = True
        if self.startup_command:
            self.write_input(self.startup_command.encode("utf-8") + b"\n")

    def _pump(self) -> None:
        """select() loop: channel -> output signal, queued writes -> channel."""
        chan = self._chan
        assert chan is not None
        chan.settimeout(0.0)
        last_alive = time.monotonic()
        while not self._stop.is_set():
            try:
                rlist, _, _ = select.select([chan], [], [], 0.15)
            except (OSError, ValueError):
                break
            if chan in rlist:
                try:
                    data = chan.recv(65536)
                except Exception as exc:  # noqa: BLE001
                    self._end(str(exc))
                    return
                if data:
                    self.output.emit(data)
                else:
                    reason = "connection closed by remote host"
                    self._end(reason)
                    return
            self._flush_writes(chan)
            if not chan.active:
                transport = self._client.get_transport() if self._client else None
                if transport is None or not transport.is_active():
                    self._end("connection lost")
                    return
            if time.monotonic() - last_alive > 1.0:
                last_alive = time.monotonic()
                self._flush_writes(chan)
        if self._stop.is_set():
            self._cleanup()
            self.disconnected.emit("")

    def _flush_writes(self, chan: paramiko.Channel) -> None:
        while True:
            with self._write_lock:
                if not self._writes:
                    return
                data = self._writes[0]
            try:
                if not chan.send_ready():
                    return
                n = chan.send(data)
            except Exception:  # noqa: BLE001
                return
            with self._write_lock:
                if n > 0:
                    self._write_bytes -= n
                    if n >= len(data):
                        self._writes.popleft()
                    else:
                        self._writes[0] = data[n:]

    def _end(self, reason: str) -> None:
        self._cleanup()
        self.disconnected.emit(reason)

    def _cleanup(self) -> None:
        if self._tunnels is not None:
            try:
                self._tunnels.stop_all()
            except Exception:  # noqa: BLE001
                pass
            self._tunnels = None
        for closer, obj in ((lambda c: c.close(), self._chan),):
            if obj is not None:
                try:
                    closer(obj)
                except Exception:  # noqa: BLE001
                    pass
        self._chan = None
        for client in [*self._hop_clients, self._client]:
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass
        self._hop_clients = []
        self._client = None
