"""Pure protocol-aware connection-check coverage."""

from __future__ import annotations

import socket
import threading

import pytest

from rdpstudio.core.models import PROTOCOL_LOCAL, PROTOCOL_RDP, PROTOCOL_SSH, Session
from rdpstudio.core.session_check import (
    SessionCheckError,
    check_session_connectivity,
    resolve_local_command,
)

pytestmark = [pytest.mark.unit, pytest.mark.regression]


class _BannerServer:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self._sock = socket.socket()
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        conn, _addr = self._sock.accept()
        try:
            conn.sendall(self._payload)
        finally:
            conn.close()
            self._sock.close()


def test_ssh_check_accepts_valid_banner():
    server = _BannerServer(b"SSH-2.0-OpenSSH_9.8\r\n")
    result = check_session_connectivity(
        Session(protocol=PROTOCOL_SSH, host="127.0.0.1", port=server.port)
    )
    assert result.ok is True
    assert "SSH server reachable" in result.summary
    assert "OpenSSH_9.8" in result.details


def test_ssh_check_rejects_non_ssh_service():
    server = _BannerServer(b"HTTP/1.1 200 OK\r\n")
    result = check_session_connectivity(
        Session(protocol=PROTOCOL_SSH, host="127.0.0.1", port=server.port)
    )
    assert result.ok is False
    assert "did not present a valid SSH banner" in result.summary


def test_local_command_resolution_finds_default_shell(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/sh")
    argv = resolve_local_command("")
    assert argv[0] == "/bin/sh"


def test_local_command_resolution_rejects_missing_binary():
    with pytest.raises(SessionCheckError, match="Command not found"):
        resolve_local_command("definitely-not-a-real-kb-remote-binary")


def test_rdp_check_uses_protocol_probe(monkeypatch):
    from rdpstudio.protocols.rdp import negotiate
    from rdpstudio.protocols.rdp.negotiate import RdpProbeResult

    monkeypatch.setattr(
        negotiate,
        "probe",
        lambda host, port, timeout=5.0: RdpProbeResult(
            host=host,
            port=port,
            ok=True,
            selected_protocol_name="TLS",
            latency_ms=12.5,
        ),
    )

    result = check_session_connectivity(Session(protocol=PROTOCOL_RDP, host="win.lab", port=3389))
    assert result.ok is True
    assert result.summary == "RDP server reachable — 12 ms"
    assert result.details == "Negotiated security: TLS"


def test_local_session_check_reports_resolved_command(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/sh")
    result = check_session_connectivity(Session(protocol=PROTOCOL_LOCAL))
    assert result.ok is True
    assert "Local shell command looks available" in result.summary
    assert "/bin/sh" in result.details
