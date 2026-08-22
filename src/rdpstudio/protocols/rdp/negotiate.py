"""RDP protocol-level connectivity probe.

Implements enough of the RDP connection negotiation (MS-RDPBCGR) to answer
"is this an RDP server, and what security does it speak?" without any
external process:

1. TCP connect to host:port.
2. Send a TPKT + X.224 Class-0 Connection Request carrying an RDP Negotiation
   Request (PROTOCOL_RDP | PROTOCOL_SSL | PROTOCOL_HYBRID).
3. Parse the X.224 Connection Confirm + Negotiation Response
   (selected security protocol) or Negotiation Failure (code).

This is the same handshake ``mstsc``/``xfreerdp`` perform before TLS starts.
"""

from __future__ import annotations

import socket
import struct
from dataclasses import dataclass, field

# Negotiation protocols (MS-RDPBCGR 2.2.1.1.1)
PROTOCOL_RDP = 0x00  # Standard RDP Security
PROTOCOL_SSL = 0x01  # TLS 1.0
PROTOCOL_HYBRID = 0x02  # CredSSP (NLA)
PROTOCOL_HYBRID_EX = 0x08  # CredSSP + pre-authentication (Gateway)

PROTOCOL_NAMES = {
    PROTOCOL_RDP: "Standard RDP",
    PROTOCOL_SSL: "TLS",
    PROTOCOL_HYBRID: "CredSSP/NLA",
    PROTOCOL_HYBRID_EX: "CredSSP+NLA-EX",
}

NEG_FAILURE_CODES = {
    0x00000001: "SSL_REQUIRED_BY_SERVER",
    0x00000002: "SSL_NOT_ALLOWED_BY_SERVER",
    0x00000003: "SSL_CERT_NOT_ON_SERVER",
    0x00000004: "INCONSISTENT_FLAGS",
    0x00000005: "HYBRID_REQUIRED_BY_SERVER",
    0x00000006: "SSL_WITH_USER_AUTH_REQUIRED_BY_SERVER",
}

TYPE_RDP_NEG_REQ = 0x01
TYPE_RDP_NEG_RSP = 0x02
TYPE_RDP_NEG_FAILURE = 0x03


class RdpProbeError(RuntimeError):
    pass


@dataclass
class RdpProbeResult:
    host: str = ""
    port: int = 3389
    ok: bool = False
    selected_protocol: int | None = None
    selected_protocol_name: str = ""
    failure_code: int | None = None
    failure_name: str = ""
    x224_message: str = ""
    latency_ms: float = 0.0
    error: str = ""
    raw_header: bytes = field(default_factory=bytes)


def build_connection_request(cookie: str = "rdpstudio", requested: int = 0x0B) -> bytes:
    """Build TPKT + X.224 CR + RDP Negotiation Request.

    ``requested`` defaults to RDP|SSL|HYBRID|HYBRID_EX (0x0B).
    Negotiation structures are 8 bytes: type(1) flags(1) length(2)=8 prot(4).
    """
    neg_req = struct.pack("<BBHI", TYPE_RDP_NEG_REQ, 0x00, 0x0008, requested)
    cookie_bytes = f"Cookie: mstshash={cookie}\r\n".encode("ascii")
    var = cookie_bytes + neg_req
    # X.224 CR PDU: LI | DST-REF(2) | SRC-REF(2) | class-options(1) | variable
    li = 5 + len(var)  # LI counts everything after itself
    x224 = bytes([li]) + struct.pack(">HHB", 0x0000, 0x0000, 0x00) + var
    tpkt = struct.pack(">BBH", 3, 0, len(x224) + 4)
    return tpkt + x224


def parse_connection_confirm(data: bytes) -> RdpProbeResult:
    result = RdpProbeResult()
    if len(data) < 11 or data[0] != 3:
        result.error = f"not a TPKT response ({data[:4].hex() if data else 'empty'})"
        return result
    result.raw_header = data[:16]
    # TPKT(4) LI(1) DST-REF(2) SRC-REF(2) class(1) → negotiation blob at 10
    tail = data[10:]
    if len(tail) >= 8 and tail[0] in (TYPE_RDP_NEG_RSP, TYPE_RDP_NEG_FAILURE):
        if tail[0] == TYPE_RDP_NEG_RSP:
            proto = struct.unpack("<I", tail[4:8])[0]
            result.ok = True
            result.selected_protocol = proto
            result.selected_protocol_name = PROTOCOL_NAMES.get(proto, f"0x{proto:08x}")
        else:
            code = struct.unpack("<I", tail[4:8])[0]
            result.failure_code = code
            result.failure_name = NEG_FAILURE_CODES.get(code, f"0x{code:08x}")
            # A negotiation failure still proves an RDP server is listening.
            result.ok = True
    else:
        # No negotiation blob: classic pre-RDP5 server → standard security.
        result.ok = True
        result.selected_protocol = PROTOCOL_RDP
        result.selected_protocol_name = PROTOCOL_NAMES[PROTOCOL_RDP]
    return result


def probe(host: str, port: int = 3389, timeout: float = 5.0) -> RdpProbeResult:
    """Connect and negotiate. Raises RdpProbeError on transport errors."""
    import time

    result = RdpProbeResult(host=host, port=port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        t0 = time.monotonic()
        sock.connect((host, port))
        result.latency_ms = (time.monotonic() - t0) * 1000
        sock.sendall(build_connection_request())
        data = sock.recv(256)
        if not data:
            raise RdpProbeError("connection closed without a response")
        parsed = parse_connection_confirm(data)
        parsed.host, parsed.port = host, port
        parsed.latency_ms = result.latency_ms
        return parsed
    except OSError as exc:
        raise RdpProbeError(f"{host}:{port}: {exc}") from exc
    finally:
        try:
            sock.close()
        except OSError:
            pass
