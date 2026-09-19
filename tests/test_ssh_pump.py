"""SSH pump: keystroke wakeup latency and output coalescing (fake channel)."""

from __future__ import annotations

import select
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.usefixtures("home")


class FakeChannel:
    """Minimal paramiko-Channel lookalike backed by a socket."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self.active = True
        self.sent = bytearray()

    def fileno(self) -> int:
        return self._sock.fileno()

    def settimeout(self, _t):
        pass

    def recv(self, n: int) -> bytes:
        return self._sock.recv(n)

    def send_ready(self) -> bool:
        return True

    def send(self, data: bytes) -> int:
        self.sent.extend(data)
        return self._sock.send(data)

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


class BurstChannel(FakeChannel):
    """FakeChannel with paramiko's ``recv_ready()`` — exercises the pump's
    burst-drain path (multiple recvs coalesced per select() round trip)."""

    def recv_ready(self) -> bool:
        return bool(select.select([self._sock], [], [], 0)[0])


def _worker_with_fake_channel(chan_cls=FakeChannel):
    from pathlib import Path

    from rdpstudio.core import paths
    from rdpstudio.protocols.ssh.worker import AuthMaterial, SshWorker
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    r, w = socket.socketpair()
    r.settimeout(1.0)
    worker = SshWorker(
        host="fake",
        port=22,
        material=AuthMaterial(host="fake"),
        known_hosts_path=Path(paths.known_hosts_file()),
        host_key_policy="accept-new",
        prompter=HeadlessPromptProvider(),
    )
    worker._chan = chan_cls(r)
    wake_r, wake_w = socket.socketpair()
    worker._wake_r, worker._wake_w = wake_r, wake_w
    worker._wake_r.setblocking(False)
    worker._wake_w.setblocking(False)
    return worker, w


def test_pump_wakes_on_keystroke(qtapp):
    """write_input must reach the channel promptly (no 150 ms select wait)."""
    worker, remote = _worker_with_fake_channel()
    received = bytearray()
    recv_lock = threading.Lock()

    def drain():
        while True:
            try:
                data = remote.recv(65536)
            except OSError:
                return
            if not data:
                return
            with recv_lock:
                received.extend(data)

    drainer = threading.Thread(target=drain, daemon=True)
    drainer.start()

    pump = threading.Thread(target=worker._pump, daemon=True)
    pump.start()
    time.sleep(0.3)  # let the pump settle into its idle select

    t0 = time.monotonic()
    worker.write_input(b"WAKEUP-KEYS")
    deadline = time.time() + 3
    while time.time() < deadline:
        with recv_lock:
            if b"WAKEUP-KEYS" in bytes(received):
                break
        time.sleep(0.005)
    latency = time.monotonic() - t0
    with recv_lock:
        assert b"WAKEUP-KEYS" in bytes(received), "input never reached the channel"
    # The old implementation could wait up to 150 ms for the select timeout;
    # the self-pipe wakeup must land well inside that budget.
    assert latency < 0.12, f"keystroke took {latency * 1000:.0f} ms to be sent"

    worker._stop.set()
    worker.request_stop()
    pump.join(timeout=3)
    assert not pump.is_alive()


def test_pump_coalesces_output(qtapp):
    """A burst of tiny remote chunks arrives as complete, batched output."""
    worker, remote = _worker_with_fake_channel()
    emissions: list[bytes] = []
    worker.output.connect(lambda d: emissions.append(bytes(d)))

    pump = threading.Thread(target=worker._pump, daemon=True)
    pump.start()
    time.sleep(0.05)

    # 30 tiny chunks in a tight loop — a fast writer's signature
    for i in range(30):
        remote.send(f"c{i}".encode())

    deadline = time.time() + 5
    while time.time() < deadline and len(b"".join(emissions)) < 90:
        qtapp.processEvents()
        time.sleep(0.02)
    payload = b"".join(emissions)
    assert payload == b"".join(f"c{i}".encode() for i in range(30)), payload
    assert len(emissions) < 30, f"no coalescing: {len(emissions)} emissions for 30 chunks"

    worker._stop.set()
    worker.request_stop()
    pump.join(timeout=3)
    assert not pump.is_alive()
    # nothing lost at shutdown
    assert b"".join(emissions) == b"".join(f"c{i}".encode() for i in range(30))


def test_pump_flushes_tail_on_stop(qtapp):
    """Output buffered in the coalescing window is flushed before disconnect."""
    worker, remote = _worker_with_fake_channel()
    emissions: list[bytes] = []
    disconnected: list[str] = []
    worker.output.connect(lambda d: emissions.append(bytes(d)))
    worker.disconnected.connect(lambda r: disconnected.append(r))

    pump = threading.Thread(target=worker._pump, daemon=True)
    pump.start()
    time.sleep(0.05)
    remote.send(b"FINAL-TAIL")  # small chunk: stays in the coalescing window
    time.sleep(0.02)
    worker._stop.set()
    worker.request_stop()
    pump.join(timeout=3)
    assert not pump.is_alive()
    # the worker lives on the GUI thread: its queued signals need the loop
    deadline = time.time() + 2
    while time.time() < deadline and (not emissions or not disconnected):
        qtapp.processEvents()
        time.sleep(0.02)
    assert b"FINAL-TAIL" in b"".join(emissions), "tail output was dropped on stop"
    assert disconnected, "disconnected must be emitted"


def test_auth_material_forward_agent_defaults_off():
    from rdpstudio.protocols.ssh.worker import AuthMaterial

    assert AuthMaterial().forward_agent is False


class _FakeShellChannel:
    def get_pty(self, *args, **kwargs):
        pass

    def invoke_shell(self):
        pass


class _FakeShellTransport:
    def __init__(self, chan):
        self._chan = chan

    def set_keepalive(self, *args):
        pass

    def open_session(self, timeout=None):
        return self._chan


class _FakeShellClient:
    def __init__(self, chan):
        self._transport = _FakeShellTransport(chan)

    def get_transport(self):
        return self._transport


def _forwarding_worker(qtapp, monkeypatch, forward_agent):
    from pathlib import Path

    import paramiko.agent as agent_mod

    from rdpstudio.core import paths
    from rdpstudio.protocols.ssh.worker import AuthMaterial, SshWorker
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    calls = []
    monkeypatch.setattr(agent_mod, "AgentRequestHandler", lambda chan: calls.append(chan))
    worker = SshWorker(
        host="fake",
        port=22,
        material=AuthMaterial(host="fake", forward_agent=forward_agent),
        known_hosts_path=Path(paths.known_hosts_file()),
        host_key_policy="accept-new",
        prompter=HeadlessPromptProvider(),
    )
    chan = _FakeShellChannel()
    worker._client = _FakeShellClient(chan)
    return worker, chan, calls


def test_open_shell_requests_agent_forwarding(qtapp, monkeypatch):
    worker, chan, calls = _forwarding_worker(qtapp, monkeypatch, True)
    worker._open_shell()
    assert worker._chan is chan
    assert calls == [chan]


def test_open_shell_skips_forwarding_by_default(qtapp, monkeypatch):
    worker, chan, calls = _forwarding_worker(qtapp, monkeypatch, False)
    worker._open_shell()
    assert worker._chan is chan
    assert calls == []


def test_open_shell_forward_failure_keeps_shell(qtapp, monkeypatch):
    import paramiko.agent as agent_mod

    worker, chan, calls = _forwarding_worker(qtapp, monkeypatch, True)

    def _boom(_chan):
        raise RuntimeError("refused")

    monkeypatch.setattr(agent_mod, "AgentRequestHandler", _boom)
    worker._open_shell()  # must not raise: forwarding is best-effort
    assert worker._chan is chan


def _ssh_ctx_for_material(home):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    return SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )


def test_build_material_maps_agent_forwarding(qtapp, home):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.ssh.session import SshSessionController

    ctx = _ssh_ctx_for_material(home)
    flagged = Session(name="a", protocol="ssh", host="h", agent_forwarding=True)
    plain = Session(name="b", protocol="ssh", host="h")
    assert SshSessionController(flagged, ctx)._build_material(flagged).forward_agent is True
    assert SshSessionController(plain, ctx)._build_material(plain).forward_agent is False


def test_pump_drains_bulk_output_in_order(qtapp):
    """A 1 MiB burst arrives complete and coalesced (drain loop + caps)."""
    worker, remote = _worker_with_fake_channel(BurstChannel)
    emissions: list[bytes] = []
    worker.output.connect(lambda d: emissions.append(bytes(d)))

    pump = threading.Thread(target=worker._pump, daemon=True)
    pump.start()
    time.sleep(0.05)

    payload = bytes(range(256)) * 4096  # 1 MiB — far more than one recv
    sender = threading.Thread(target=lambda: remote.sendall(payload), daemon=True)
    sender.start()

    deadline = time.time() + 10
    received = b""
    while time.time() < deadline:
        qtapp.processEvents()
        received = b"".join(emissions)
        if len(received) >= len(payload):
            break
        time.sleep(0.01)
    sender.join(timeout=5)
    assert received == payload, f"lost output: {len(received)}/{len(payload)}"
    # Coalescing still bounds the cross-thread signal rate: the drain loop
    # must not regress into one emission per socket read.
    assert len(emissions) <= len(payload) // 65536 + 8, (
        f"{len(emissions)} emissions for 1 MiB — coalescing regressed"
    )

    worker._stop.set()
    worker.request_stop()
    pump.join(timeout=3)
    assert not pump.is_alive()
    assert b"".join(emissions) == payload  # nothing lost at shutdown


def test_pump_ends_on_remote_eof(qtapp):
    """Drain loop must still detect EOF exactly once and flush the tail."""
    worker, remote = _worker_with_fake_channel(BurstChannel)
    emissions: list[bytes] = []
    disconnected: list[str] = []
    worker.output.connect(lambda d: emissions.append(bytes(d)))
    worker.disconnected.connect(disconnected.append)

    pump = threading.Thread(target=worker._pump, daemon=True)
    pump.start()
    time.sleep(0.05)
    remote.send(b"bye")
    time.sleep(0.05)
    remote.close()  # orderly EOF on the socketpair

    pump.join(timeout=3)
    assert not pump.is_alive()
    deadline = time.time() + 2
    while time.time() < deadline and not disconnected:
        qtapp.processEvents()
        time.sleep(0.02)
    assert disconnected == ["connection closed by remote host"]
    assert b"bye" in b"".join(emissions), "tail output was dropped at EOF"


def _plain_worker():
    from pathlib import Path

    from rdpstudio.core import paths
    from rdpstudio.protocols.ssh.worker import AuthMaterial, SshWorker
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    return SshWorker(
        host="fake",
        port=22,
        material=AuthMaterial(host="fake"),
        known_hosts_path=Path(paths.known_hosts_file()),
        host_key_policy="accept-new",
        prompter=HeadlessPromptProvider(),
    )


def test_announce_tunes_transport_flow_control(qtapp):
    """Shell/SFTP/tunnel/jump channels inherit OpenSSH-sized flow control.

    paramiko 3.x/4.x default to 4 KiB max packets, which taxes bulk
    throughput ~8x; ``_announce`` runs for every authenticated transport
    (including each jump hop) before any channel is opened on it.
    """
    from rdpstudio.protocols.ssh.worker import SSH_MAX_PACKET_SIZE, SSH_WINDOW_SIZE

    class LegacyTransport:  # paramiko 3.x-style class-level defaults
        default_window_size = 2 ** 15 * 32
        default_max_packet_size = 2 ** 12
        local_cipher = "aes256-ctr"
        remote_version = "SSH-2.0-legacy"

        def get_username(self):
            return "tester"

        def get_banner(self):
            return ""

    class LegacyClient:
        def __init__(self, transport):
            self._transport = transport

        def get_transport(self):
            return self._transport

    worker = _plain_worker()
    infos: list[dict] = []
    worker.connected.connect(infos.append)
    transport = LegacyTransport()
    worker._announce(LegacyClient(transport))
    assert transport.default_max_packet_size == SSH_MAX_PACKET_SIZE
    assert transport.default_window_size == SSH_WINDOW_SIZE
    assert infos and infos[0]["cipher"] == "aes256-ctr"


def test_announce_keeps_larger_existing_defaults(qtapp):
    """Never shrink a transport that was already configured bigger."""

    class BigTransport:
        default_window_size = 4 * 1024 * 1024
        default_max_packet_size = 64 * 1024
        local_cipher = "chacha20-poly1305@openssh.com"
        remote_version = "SSH-2.0-big"

        def get_username(self):
            return "tester"

        def get_banner(self):
            return ""

    class BigClient:
        def __init__(self, transport):
            self._transport = transport

        def get_transport(self):
            return self._transport

    worker = _plain_worker()
    worker.connected.connect(lambda info: None)
    transport = BigTransport()
    worker._announce(BigClient(transport))
    assert transport.default_max_packet_size == 64 * 1024
    assert transport.default_window_size == 4 * 1024 * 1024


def test_announce_tolerates_transport_without_tunables(qtapp):
    """Exotic/mocked transports missing the attributes must not break auth."""

    class BareTransport:
        local_cipher = ""
        remote_version = ""

        def get_username(self):
            return ""

        def get_banner(self):
            return ""

    worker = _plain_worker()
    infos: list[dict] = []
    worker.connected.connect(infos.append)
    worker._announce(type("C", (), {"get_transport": lambda self: BareTransport()})())
    assert infos, "connected must still be emitted"
