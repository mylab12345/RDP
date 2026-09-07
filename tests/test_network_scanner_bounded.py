"""Regression tests for bounded scanner scheduling and cancellation."""

from __future__ import annotations

import threading
import time

import pytest

from rdpstudio.tools import network_scanner
from rdpstudio.tools.network_scanner import PortScanner, ScanResult

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def _result(host: str, port: int) -> ScanResult:
    return ScanResult(host=host, port=port, open=False, service="test")


def test_scanner_bounds_pending_futures(monkeypatch):
    release = threading.Event()
    started = threading.Event()
    calls = 0
    submitted = 0
    calls_lock = threading.Lock()
    real_executor = network_scanner.concurrent.futures.ThreadPoolExecutor

    class TrackingExecutor(real_executor):
        def submit(self, *args, **kwargs):
            nonlocal submitted
            with calls_lock:
                submitted += 1
            return super().submit(*args, **kwargs)

    def blocked_check(host, port, _timeout, _grab_banner):
        nonlocal calls
        with calls_lock:
            calls += 1
            started.set()
        release.wait(5)
        return _result(host, port)

    monkeypatch.setattr(network_scanner.concurrent.futures, "ThreadPoolExecutor", TrackingExecutor)
    monkeypatch.setattr(network_scanner, "check_port", blocked_check)
    scanner = PortScanner(max_workers=2)
    output: list[list[ScanResult]] = []
    thread = threading.Thread(
        target=lambda: output.append(scanner.scan(["host"], list(range(1, 101)), grab_banner=False))
    )
    thread.start()
    assert started.wait(1)
    time.sleep(0.05)  # let the initial bounded submission finish

    # Two running + at most two queued, rather than all 100 futures at once.
    with calls_lock:
        assert calls <= scanner.max_workers
        assert submitted <= scanner.max_workers * scanner._IN_FLIGHT_FACTOR
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert len(output[0]) == 100


def test_cancel_returns_without_waiting_for_all_targets(monkeypatch):
    release = threading.Event()
    started = threading.Event()
    calls = 0
    calls_lock = threading.Lock()

    def blocked_check(host, port, _timeout, _grab_banner):
        nonlocal calls
        with calls_lock:
            calls += 1
            started.set()
        release.wait(5)
        return _result(host, port)

    monkeypatch.setattr(network_scanner, "check_port", blocked_check)
    scanner = PortScanner(max_workers=2)
    thread = threading.Thread(target=lambda: scanner.scan(["host"], list(range(1, 1001)), grab_banner=False))
    thread.start()
    assert started.wait(1)

    scanner.cancel()
    thread.join(1)
    try:
        assert not thread.is_alive(), "cancel waited for blocked network probes"
        # Submission is bounded to two batches regardless of target count.
        with calls_lock:
            assert calls <= scanner.max_workers
    finally:
        # Allow the at-most-two executor workers to exit before monkeypatch is undone.
        release.set()


def test_callback_failure_does_not_duplicate_or_abort_results(monkeypatch):
    monkeypatch.setattr(
        network_scanner,
        "check_port",
        lambda host, port, _timeout, _banner: _result(host, port),
    )
    scanner = PortScanner(max_workers=2)

    def broken_callback(_result):
        raise RuntimeError("observer failed")

    results = scanner.scan(
        ["host"],
        [22, 80, 443],
        grab_banner=False,
        on_result=broken_callback,
    )
    assert sorted(result.port for result in results) == [22, 80, 443]
