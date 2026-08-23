"""SSH pump: keystroke wakeup latency and output coalescing (fake channel)."""

from __future__ import annotations

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


def _worker_with_fake_channel():
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
    worker._chan = FakeChannel(r)
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
