"""Network diagnostics: high-performance multithreaded port scanner, ping & DNS."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

COMMON_PORTS: dict[int, str] = {
    21: "FTP",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    139: "NetBIOS",
    143: "IMAP",
    443: "HTTPS",
    445: "SMB",
    587: "SMTP-Sub",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1521: "Oracle",
    2049: "NFS",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    5900: "VNC",
    6379: "Redis",
    8000: "HTTP-Alt",
    8080: "HTTP-Proxy",
    8443: "HTTPS-Alt",
    9200: "Elasticsearch",
    27017: "MongoDB",
}

PRESET_COMMON = sorted(COMMON_PORTS.keys())
PRESET_REMOTE = [22, 3389, 5900, 80, 443, 8080, 8443]
PRESET_WEB = [80, 443, 8000, 8080, 8443, 8888, 9000, 9443]
PRESET_DATABASES = [1433, 1521, 3306, 5432, 6379, 9200, 27017]


@dataclass
class ScanResult:
    host: str
    port: int
    open: bool
    service: str
    latency_ms: float = 0.0
    banner: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "open": self.open,
            "service": self.service,
            "latency_ms": round(self.latency_ms, 2),
            "banner": self.banner,
            "error": self.error,
        }


def parse_target_hosts(target_expr: str, max_hosts: int = 256) -> list[str]:
    """Parse single host, IP, CIDR (192.168.1.0/28), or range (10.0.0.1-10.0.0.10)."""
    target = target_expr.strip()
    if not target:
        return []

    # CIDR subnet
    if "/" in target:
        try:
            net = ipaddress.ip_network(target, strict=False)
            hosts = [str(ip) for ip in net.hosts()][:max_hosts]
            if not hosts and net.num_addresses == 1:
                hosts = [str(net.network_address)]
            return hosts
        except ValueError:
            return [target]

    # IP range e.g. 192.168.1.10-192.168.1.20 or 192.168.1.10-20
    if "-" in target and not target.startswith("-"):
        parts = target.split("-", 1)
        start_str, end_str = parts[0].strip(), parts[1].strip()
        try:
            start_ip = ipaddress.ip_address(start_str)
            if "." in end_str:
                end_ip = ipaddress.ip_address(end_str)
            else:
                # e.g. 192.168.1.10 - 20
                octets = start_str.split(".")
                octets[-1] = end_str
                end_ip = ipaddress.ip_address(".".join(octets))

            if int(start_ip) <= int(end_ip):
                count = min(int(end_ip) - int(start_ip) + 1, max_hosts)
                return [str(ipaddress.ip_address(int(start_ip) + i)) for i in range(count)]
        except Exception:
            pass

    # Comma-separated list or single host
    if "," in target:
        return [h.strip() for h in target.split(",") if h.strip()][:max_hosts]

    return [target]


def parse_ports(ports_expr: str | list[int]) -> list[int]:
    """Parse comma/dash port expressions like '22,80,443,8000-8080'."""
    if isinstance(ports_expr, list):
        return sorted(set(ports_expr))
    ports: set[int] = set()
    expr = ports_expr.strip()
    if not expr:
        return PRESET_COMMON
    for chunk in expr.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            try:
                p1, p2 = map(int, chunk.split("-", 1))
                if 1 <= p1 <= 65535 and 1 <= p2 <= 65535:
                    p_start, p_end = min(p1, p2), max(p1, p2)
                    # Limit continuous range to max 2000 ports per chunk
                    if p_end - p_start <= 2000:
                        ports.update(range(p_start, p_end + 1))
            except ValueError:
                pass
        else:
            try:
                p = int(chunk)
                if 1 <= p <= 65535:
                    ports.add(p)
            except ValueError:
                pass
    return sorted(ports) or PRESET_COMMON


def check_port(
    host: str,
    port: int,
    timeout: float = 1.2,
    grab_banner: bool = True,
) -> ScanResult:
    """Probe a single (host, port) tuple with TCP SYN/Connect and banner grab."""
    service = COMMON_PORTS.get(port, "unknown")
    start = time.perf_counter()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)

    try:
        sock.connect((host, port))
        latency = (time.perf_counter() - start) * 1000.0
        banner = ""
        if grab_banner:
            try:
                sock.settimeout(min(0.6, timeout))
                if port in (80, 8080, 8000, 8888):
                    sock.sendall(b"HEAD / HTTP/1.0\r\nHost: " + host.encode() + b"\r\n\r\n")
                elif port in (21, 22, 25, 110, 143):
                    pass  # Service sends banner immediately upon connect
                raw = sock.recv(256)
                banner = raw.decode("utf-8", "replace").strip().replace("\r", " ").replace("\n", " ")
                if len(banner) > 80:
                    banner = banner[:80] + "…"
            except Exception:
                pass
        sock.close()
        return ScanResult(
            host=host,
            port=port,
            open=True,
            service=service,
            latency_ms=latency,
            banner=banner,
        )
    except TimeoutError:
        sock.close()
        return ScanResult(
            host=host,
            port=port,
            open=False,
            service=service,
            error="timed out",
        )
    except ConnectionRefusedError:
        sock.close()
        return ScanResult(
            host=host,
            port=port,
            open=False,
            service=service,
            error="connection refused",
        )
    except Exception as exc:
        sock.close()
        return ScanResult(
            host=host,
            port=port,
            open=False,
            service=service,
            error=str(exc),
        )


class PortScanner:
    """Multithreaded concurrent scanner with progress callbacks."""

    def __init__(self, max_workers: int = 50) -> None:
        self.max_workers = max_workers
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def scan(
        self,
        targets: list[str],
        ports: list[int],
        timeout: float = 1.0,
        grab_banner: bool = True,
        on_result: Callable[[ScanResult], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[ScanResult]:
        self._cancelled = False
        tasks: list[tuple[str, int]] = []
        for host in targets:
            for port in ports:
                tasks.append((host, port))

        total = len(tasks)
        completed = 0
        results: list[ScanResult] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(check_port, host, port, timeout, grab_banner): (host, port)
                for host, port in tasks
            }

            for future in concurrent.futures.as_completed(future_to_task):
                if self._cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                try:
                    res = future.result()
                    results.append(res)
                    if on_result is not None:
                        on_result(res)
                except Exception as exc:
                    host, port = future_to_task[future]
                    res = ScanResult(
                        host=host,
                        port=port,
                        open=False,
                        service=COMMON_PORTS.get(port, "unknown"),
                        error=str(exc),
                    )
                    results.append(res)
                    if on_result is not None:
                        on_result(res)

                completed += 1
                if on_progress is not None:
                    on_progress(completed, total)

        return results


# ----------------------------------------------------------------------
# Ping and DNS Diagnostics
# ----------------------------------------------------------------------
@dataclass
class PingSummary:
    host: str
    sent: int = 0
    received: int = 0
    min_ms: float = 0.0
    avg_ms: float = 0.0
    max_ms: float = 0.0
    jitter_ms: float = 0.0
    latencies: list[float] = field(default_factory=list)

    @property
    def packet_loss_pct(self) -> float:
        if self.sent == 0:
            return 0.0
        return ((self.sent - self.received) / self.sent) * 100.0


def tcp_ping(host: str, port: int = 80, count: int = 4, timeout: float = 2.0) -> PingSummary:
    """Reliable user-space TCP ping without requiring root raw ICMP sockets."""
    summary = PingSummary(host=host)
    for _ in range(count):
        summary.sent += 1
        start = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            latency = (time.perf_counter() - start) * 1000.0
            summary.received += 1
            summary.latencies.append(latency)
            sock.close()
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
        time.sleep(0.08)

    if summary.latencies:
        summary.min_ms = min(summary.latencies)
        summary.max_ms = max(summary.latencies)
        summary.avg_ms = sum(summary.latencies) / len(summary.latencies)
        if len(summary.latencies) > 1:
            diffs = [abs(summary.latencies[i] - summary.latencies[i - 1]) for i in range(1, len(summary.latencies))]
            summary.jitter_ms = sum(diffs) / len(diffs)
    return summary


def dns_lookup(hostname: str) -> dict[str, list[str]]:
    """Perform forward & reverse DNS lookups for multiple record types."""
    results: dict[str, list[str]] = {
        "A": [],
        "AAAA": [],
        "PTR": [],
        "Canonical": [],
    }
    # A & AAAA records via getaddrinfo
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, canonname, sockaddr in addr_info:
            ip = sockaddr[0]
            if family == socket.AF_INET and ip not in results["A"]:
                results["A"].append(ip)
            elif family == socket.AF_INET6 and ip not in results["AAAA"]:
                results["AAAA"].append(ip)
            if canonname and canonname not in results["Canonical"]:
                results["Canonical"].append(canonname)
    except Exception as exc:
        results["Error"] = [str(exc)]

    # Reverse PTR lookup if target is an IP
    try:
        ipaddress.ip_address(hostname)
        try:
            rev_host, _, _ = socket.gethostbyaddr(hostname)
            if rev_host:
                results["PTR"].append(rev_host)
        except Exception:
            pass
    except ValueError:
        # Hostname, reverse lookup its resolved A records
        for ip in results["A"][:3]:
            try:
                rev, _, _ = socket.gethostbyaddr(ip)
                results["PTR"].append(f"{ip} → {rev}")
            except Exception:
                pass

    return results
