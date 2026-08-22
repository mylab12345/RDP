"""Unit tests for Network Scanner, target & port parser, ping & DNS tools."""

from __future__ import annotations

import socket

from rdpstudio.tools.network_scanner import (
    PortScanner,
    check_port,
    dns_lookup,
    parse_ports,
    parse_target_hosts,
    tcp_ping,
)


def test_parse_target_hosts():
    assert parse_target_hosts("192.168.1.1") == ["192.168.1.1"]
    assert parse_target_hosts("192.168.1.1, 192.168.1.2") == ["192.168.1.1", "192.168.1.2"]

    # CIDR subnet
    cidr_hosts = parse_target_hosts("192.168.1.0/30")
    assert len(cidr_hosts) == 2
    assert "192.168.1.1" in cidr_hosts
    assert "192.168.1.2" in cidr_hosts

    # Range
    range_hosts = parse_target_hosts("10.0.0.1-10.0.0.5")
    assert range_hosts == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4", "10.0.0.5"]


def test_parse_ports():
    assert parse_ports("22") == [22]
    assert parse_ports("22,80,443") == [22, 80, 443]
    assert parse_ports("8000-8003") == [8000, 8001, 8002, 8003]
    assert parse_ports([22, 3389]) == [22, 3389]


def test_check_port_live_and_closed():
    # Spin up local dummy listening socket
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    try:
        res = check_port("127.0.0.1", port, timeout=0.5, grab_banner=False)
        assert res.open is True
        assert res.host == "127.0.0.1"
        assert res.port == port
        assert res.latency_ms >= 0
    finally:
        srv.close()

    # Closed port probe
    closed_res = check_port("127.0.0.1", port, timeout=0.3, grab_banner=False)
    assert closed_res.open is False


def test_port_scanner_multithreaded():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    scanner = PortScanner(max_workers=5)
    results = scanner.scan(["127.0.0.1"], [port, 65530], timeout=0.5, grab_banner=False)
    srv.close()

    assert len(results) == 2
    open_ports = [r.port for r in results if r.open]
    assert port in open_ports


def test_tcp_ping_and_dns():
    # TCP ping to closed port should report loss or timing
    summary = tcp_ping("127.0.0.1", port=65530, count=2, timeout=0.1)
    assert summary.sent == 2
    assert summary.host == "127.0.0.1"

    # DNS lookup of localhost / 127.0.0.1
    dns_res = dns_lookup("127.0.0.1")
    assert "A" in dns_res
    assert "127.0.0.1" in dns_res["A"]
