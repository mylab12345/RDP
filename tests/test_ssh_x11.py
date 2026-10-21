"""X11 forwarding: display parsing, cookie rewrite, and worker request wiring."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest


def test_local_display_parsing(monkeypatch):
    from rdpstudio.protocols.ssh.x11 import local_display

    monkeypatch.setenv("DISPLAY", ":0")
    assert local_display() == ("", 0)
    monkeypatch.setenv("DISPLAY", "unix:10.0")
    assert local_display() == ("unix", 10)
    monkeypatch.setenv("DISPLAY", "localhost:12")
    assert local_display() == ("localhost", 12)
    monkeypatch.setenv("DISPLAY", "")
    assert local_display() is None
    monkeypatch.setenv("DISPLAY", "not-a-display")
    assert local_display() is None


def _setup(name: bytes, data: bytes, order: bytes = b"B") -> bytes:
    fmt = ">BBHHHHH" if order == b"B" else "<BBHHHHH"
    header = struct.pack(fmt, ord(order), 0, 11, 0, len(name), len(data), 0)
    pad = lambda b: b + b"\0" * ((4 - len(b) % 4) % 4)  # noqa: E731
    return header + pad(name) + pad(data)


@pytest.mark.parametrize("order", [b"B", b"l"])
def test_rewrite_auth_cookie_replaces_only_magic_cookie(order):
    from rdpstudio.protocols.ssh.x11 import rewrite_auth_cookie

    fake = b"\x11" * 16
    real = b"\x22" * 16
    setup = _setup(b"MIT-MAGIC-COOKIE-1", fake, order)
    out = rewrite_auth_cookie(setup, real)
    assert out != setup
    assert real in out and fake not in out
    # Same length: only the cookie bytes changed.
    assert len(out) == len(setup)


def test_rewrite_auth_cookie_leaves_other_setup_alone():
    from rdpstudio.protocols.ssh.x11 import rewrite_auth_cookie

    setup = _setup(b"XDM-AUTHORIZATION-1", b"\x33" * 16)
    assert rewrite_auth_cookie(setup, b"\x44" * 16) == setup
    assert rewrite_auth_cookie(b"", b"\x44" * 16) == b""
    assert rewrite_auth_cookie(setup, None) == setup


def test_worker_requests_x11_when_display_is_available(qtapp, monkeypatch):
    from rdpstudio.protocols.ssh.worker import AuthMaterial, SshWorker

    monkeypatch.setenv("DISPLAY", ":0")
    worker = SshWorker(
        host="example",
        port=22,
        material=AuthMaterial(host="example", username="u"),
        known_hosts_path=Path("/tmp/kb-remote-test-known-hosts"),
        host_key_policy="accept-new",
        prompter=None,
    )

    class Chan:
        def __init__(self):
            self.calls = []

        def request_x11(self, **kwargs):
            self.calls.append(kwargs)

    chan = Chan()
    worker._request_x11_forwarding(chan)
    assert len(chan.calls) == 1
    assert callable(chan.calls[0]["handler"])


def test_worker_skips_x11_without_display(qtapp, monkeypatch):
    from rdpstudio.protocols.ssh.worker import AuthMaterial, SshWorker

    monkeypatch.delenv("DISPLAY", raising=False)
    worker = SshWorker(
        host="example",
        port=22,
        material=AuthMaterial(host="example", username="u"),
        known_hosts_path=Path("/tmp/kb-remote-test-known-hosts"),
        host_key_policy="accept-new",
        prompter=None,
    )

    class Chan:
        def request_x11(self, **kwargs):  # pragma: no cover - must not run
            raise AssertionError("request_x11 called without a display")

    worker._request_x11_forwarding(Chan())


def test_session_x11_flag_round_trip():
    from rdpstudio.core.models import Session

    session = Session(x11_forwarding=True)
    assert Session.from_dict(session.to_dict()).x11_forwarding is True
    assert Session.from_dict({"x11_forwarding": "false"}).x11_forwarding is False


def test_bridge_rewrites_cookie_and_forwards_both_directions():
    import socket
    import threading
    import time

    from rdpstudio.protocols.ssh.x11 import _bridge

    class FakeChan:
        def __init__(self, payload: bytes):
            self.buf = bytearray(payload)
            self.out = bytearray()
            self.closed = False
            self.eof_received = False
            self.transport = None

        def recv_ready(self):
            return bool(self.buf)

        def recv(self, size):
            if not self.buf:
                return b""
            chunk = bytes(self.buf[:size])
            del self.buf[:size]
            return chunk

        def send(self, data):
            self.out += data
            return len(data)

        def close(self):
            self.closed = True

    real = b"\x22" * 16
    setup = _setup(b"MIT-MAGIC-COOKIE-1", b"\x11" * 16)
    chan = FakeChan(setup + b"REQ")
    local, peer = socket.socketpair()
    thread = threading.Thread(
        target=_bridge, args=(chan, local, ("", 0), real), daemon=True
    )
    thread.start()
    try:
        peer.settimeout(3)
        got = b""
        while len(got) < len(setup):
            got += peer.recv(len(setup) - len(got))
        assert real in got
        assert peer.recv(3) == b"REQ"
        peer.sendall(b"RESPONSE")
        peer.close()
        thread.join(3)
        assert not thread.is_alive()
        assert b"RESPONSE" in chan.out
        assert chan.closed is True
    finally:
        for sock in (local, peer):
            try:
                sock.close()
            except OSError:
                pass
        assert not thread.is_alive() or time.sleep(0.01) is None
