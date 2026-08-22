"""RDP negotiation probe against a fake RDP server socket."""

from __future__ import annotations

import socket
import struct
import threading

from rdpstudio.protocols.rdp.negotiate import (
    PROTOCOL_HYBRID,
    PROTOCOL_SSL,
    build_connection_request,
    parse_connection_confirm,
    probe,
)


def _neg_rsp(selected: int) -> bytes:
    neg = struct.pack("<BBHI", 0x02, 0x00, 8, selected)
    li = 5 + len(neg)
    x224 = bytes([li]) + struct.pack(">HHB", 0, 0, 0) + neg
    return struct.pack(">BBH", 3, 0, len(x224) + 4) + x224


def _neg_failure(code: int) -> bytes:
    neg = struct.pack("<BBHI", 0x03, 0x00, 8, code)
    li = 5 + len(neg)
    x224 = bytes([li]) + struct.pack(">HHB", 0, 0, 0) + neg
    return struct.pack(">BBH", 3, 0, len(x224) + 4) + x224


def _serve_once(response: bytes):
    """Start a TCP server that replies once; returns (host, port)."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        conn, _ = srv.accept()
        data = conn.recv(512)
        assert data.startswith(b"\x03\x00")  # TPKT
        conn.sendall(response)
        conn.close()
        srv.close()

    threading.Thread(target=run, daemon=True).start()
    return "127.0.0.1", port


def test_connection_request_layout():
    req = build_connection_request()
    assert req[0] == 3 and req[1] == 0
    assert struct.unpack(">H", req[2:4])[0] == len(req)
    li = req[4]
    # cookie + 8-byte negotiation request follow DST/SRC/class
    var = req[10:]
    assert var.startswith(b"Cookie: mstshash=")
    assert var.endswith(b"\x01\x00\x08\x00\x0b\x00\x00\x00")
    assert li == 5 + len(var)


def test_probe_hybrid_selected():
    host, port = _serve_once(_neg_rsp(PROTOCOL_HYBRID))
    result = probe(host, port, timeout=3)
    assert result.ok
    assert result.selected_protocol == PROTOCOL_HYBRID
    assert result.selected_protocol_name == "CredSSP/NLA"


def test_probe_ssl_selected():
    host, port = _serve_once(_neg_rsp(PROTOCOL_SSL))
    result = probe(host, port, timeout=3)
    assert result.ok and result.selected_protocol == PROTOCOL_SSL


def test_probe_negotiation_failure_is_still_rdp():
    host, port = _serve_once(_neg_failure(0x00000001))
    result = probe(host, port, timeout=3)
    assert result.ok
    assert result.failure_code == 1
    assert result.failure_name == "SSL_REQUIRED_BY_SERVER"


def test_probe_refused():
    import pytest

    from rdpstudio.protocols.rdp.negotiate import RdpProbeError

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # likely free
    with pytest.raises(RdpProbeError):
        probe("127.0.0.1", port, timeout=0.5)


def test_parse_legacy_response_without_negotiation():
    x224 = bytes([5]) + struct.pack(">HHB", 0, 0, 0)
    data = struct.pack(">BBH", 3, 0, len(x224) + 4) + x224 + b"\x00" * 6
    result = parse_connection_confirm(data)
    assert result.ok
    assert result.selected_protocol_name == "Standard RDP"
