"""Network diagnostics: high-performance multithreaded port scanner, ping & DNS."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.log import get_logger

log = get_logger("tools.network")

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
        clean = []
        for p in ports_expr:
            try:
                n = int(p)
            except (TypeError, ValueError):
                continue
            if 1 <= n <= 65535:
                clean.append(n)
        return sorted(set(clean)) or PRESET_COMMON
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
    sock = None
    try:
        # IPv4 + IPv6; create_connection also applies the timeout to DNS.
        sock = socket.create_connection((host, port), timeout=timeout)
        latency = (time.perf_counter() - start) * 1000.0
        banner = ""
        if grab_banner:
            try:
                sock.settimeout(min(0.6, timeout))
                if port in (80, 8080, 8000, 8888):
                    sock.sendall(b"HEAD / HTTP/1.0\r\nHost: " + host.encode("idna", "replace") + b"\r\n\r\n")
                elif port in (21, 22, 25, 110, 143):
                    pass  # Service sends banner immediately upon connect
                raw = sock.recv(256)
                banner = raw.decode("utf-8", "replace").strip().replace("\r", " ").replace("\n", " ")
                if len(banner) > 80:
                    banner = banner[:80] + "…"
            except Exception:
                pass
        return ScanResult(
            host=host,
            port=port,
            open=True,
            service=service,
            latency_ms=latency,
            banner=banner,
        )
    except TimeoutError:
        return ScanResult(
            host=host,
            port=port,
            open=False,
            service=service,
            error="timed out",
        )
    except ConnectionRefusedError:
        return ScanResult(
            host=host,
            port=port,
            open=False,
            service=service,
            error="connection refused",
        )
    except Exception as exc:
        return ScanResult(
            host=host,
            port=port,
            open=False,
            service=service,
            error=str(exc),
        )
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


class PortScanner:
    """Bounded concurrent scanner with progress and responsive cancellation.

    At most twice ``max_workers`` futures are queued.  Earlier versions built
    and submitted the entire Cartesian product first (up to hundreds of
    thousands of futures), causing avoidable memory spikes and making Cancel
    ineffective until submission completed.
    """

    _IN_FLIGHT_FACTOR = 2

    def __init__(self, max_workers: int = 50) -> None:
        try:
            workers = int(max_workers)
        except (TypeError, ValueError, OverflowError):
            workers = 50
        self.max_workers = max(1, workers)
        self._cancelled = False  # compatibility/introspection flag
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancelled = True
        self._cancel_event.set()

    @staticmethod
    def _notify(callback: Callable | None, *args: object) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # noqa: BLE001 - observer bugs must not abort a scan
            log.exception("network scanner callback failed")

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
        self._cancel_event.clear()
        total = len(targets) * len(ports)
        if total == 0:
            return []

        task_iter = ((host, port) for host in targets for port in ports)
        completed = 0
        results: list[ScanResult] = []
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers)
        pending: dict[concurrent.futures.Future, tuple[str, int]] = {}
        exhausted = False
        max_pending = self.max_workers * self._IN_FLIGHT_FACTOR

        def submit_available() -> None:
            nonlocal exhausted
            while (
                not exhausted
                and not self._cancel_event.is_set()
                and len(pending) < max_pending
            ):
                try:
                    host, port = next(task_iter)
                except StopIteration:
                    exhausted = True
                    break
                future = executor.submit(check_port, host, port, timeout, grab_banner)
                pending[future] = (host, port)

        try:
            submit_available()
            while pending and not self._cancel_event.is_set():
                # A short bounded wait makes cancellation responsive even when
                # every network operation is still blocked on its timeout.
                done, _not_done = concurrent.futures.wait(
                    pending,
                    timeout=0.05,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
                if not done:
                    continue
                for future in done:
                    host, port = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:  # defensive: check_port normally contains errors
                        result = ScanResult(
                            host=host,
                            port=port,
                            open=False,
                            service=COMMON_PORTS.get(port, "unknown"),
                            error=str(exc),
                        )
                    results.append(result)
                    completed += 1
                    self._notify(on_result, result)
                    self._notify(on_progress, completed, total)
                submit_available()
        finally:
            cancelled = self._cancel_event.is_set()
            if cancelled:
                for future in pending:
                    future.cancel()
            # On cancellation, return immediately; only the at-most-N running
            # socket probes finish in the executor background (bounded by
            # their own timeout).  A completed scan still joins all workers.
            executor.shutdown(wait=not cancelled, cancel_futures=cancelled)

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
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            latency = (time.perf_counter() - start) * 1000.0
            summary.received += 1
            summary.latencies.append(latency)
        except Exception:
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
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
