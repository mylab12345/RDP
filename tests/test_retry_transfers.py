"""Tests for retry/backoff policy and the transfer-history log (pure Python)."""

from __future__ import annotations

import errno
import time

import pytest

from rdpstudio.core import transfers
from rdpstudio.core.retry import RetryPolicy, is_transient, retry_call
from rdpstudio.core.transfers import TransferLog, TransferRecord, log_transfer


# ----------------------------------------------------------------------
# RetryPolicy
# ----------------------------------------------------------------------
def test_delay_grows_and_caps():
    policy = RetryPolicy(attempts=5, base_delay=0.5, max_delay=1.0, backoff=2.0, jitter=0.0)
    assert policy.delay_for(1) == pytest.approx(0.5)
    assert policy.delay_for(2) == pytest.approx(1.0)
    assert policy.delay_for(9) == pytest.approx(1.0)  # capped


def test_delay_jitter_stays_in_bounds():
    policy = RetryPolicy(base_delay=1.0, jitter=0.5)
    for _ in range(50):
        assert 1.0 <= policy.delay_for(1) <= 1.5


# ----------------------------------------------------------------------
# is_transient
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "exc",
    [
        TimeoutError("timed out"),
        EOFError("eof"),
        ConnectionResetError("reset by peer"),
        ConnectionAbortedError("aborted"),
        BrokenPipeError("broken pipe"),
        OSError(errno.EPIPE, "broken pipe"),
        OSError(errno.ECONNRESET, "reset"),
        OSError(errno.ETIMEDOUT, "timed out"),
        OSError("socket is closed"),
        RuntimeError("connection reset by peer"),
        RuntimeError("server response timed out waiting"),
        RuntimeError("please try again later"),
        RuntimeError("network is unreachable"),
    ],
)
def test_transient_errors(exc):
    assert is_transient(exc) is True


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("bad value"),
        RuntimeError("something broke"),
        FileNotFoundError("nope"),
        PermissionError("denied"),
        IsADirectoryError("is a dir"),
        OSError(errno.ENOENT, "missing"),
        OSError(errno.EACCES, "denied"),
        OSError(errno.EEXIST, "exists"),
        OSError(errno.ENOSPC, "full disk"),
    ],
)
def test_permanent_errors(exc):
    assert is_transient(exc) is False


def test_paramiko_auth_errors_are_permanent_but_transport_is_not():
    paramiko = pytest.importorskip("paramiko")
    assert is_transient(paramiko.AuthenticationException("bad password")) is False
    assert is_transient(paramiko.SSHException("Connection reset by peer")) is True
    assert is_transient(paramiko.SSHException("weird protocol state")) is False


# ----------------------------------------------------------------------
# retry_call
# ----------------------------------------------------------------------
def test_retry_call_success_first_try():
    sleeps: list[float] = []
    calls: list[int] = []

    def func(a, b=0):
        calls.append(1)
        return a + b

    assert retry_call(RetryPolicy(), func, 2, b=3, sleep=sleeps.append) == 5
    assert len(calls) == 1 and sleeps == []


def test_retry_call_retries_transient_then_succeeds():
    sleeps: list[float] = []
    attempts: list[int] = []

    def func():
        attempts.append(1)
        if len(attempts) < 3:
            raise ConnectionResetError("reset")
        return "ok"

    policy = RetryPolicy(attempts=3, base_delay=0.5, jitter=0.0)
    assert retry_call(policy, func, sleep=sleeps.append) == "ok"
    assert len(attempts) == 3
    assert sleeps == [pytest.approx(0.5), pytest.approx(1.0)]


def test_retry_call_exhaustion_reraises_last():
    def func():
        raise TimeoutError("still down")

    with pytest.raises(TimeoutError, match="still down"):
        retry_call(RetryPolicy(attempts=2), func, sleep=lambda _s: None)


def test_retry_call_permanent_error_raises_immediately():
    sleeps: list[float] = []
    calls: list[int] = []

    def func():
        calls.append(1)
        raise PermissionError("denied")

    with pytest.raises(PermissionError):
        retry_call(RetryPolicy(attempts=5), func, sleep=sleeps.append)
    assert len(calls) == 1 and sleeps == []


def test_retry_call_does_not_swallow_keyboard_interrupt():
    def func():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        retry_call(RetryPolicy(attempts=5), func, sleep=lambda _s: None)


# ----------------------------------------------------------------------
# TransferRecord
# ----------------------------------------------------------------------
def test_record_roundtrip():
    rec = TransferRecord(
        protocol="scp",
        direction="upload",
        session="prod",
        source="/a (2 item(s))",
        destination="/b",
        bytes_total=100,
        files_total=2,
        ok=True,
        duration_s=1.25,
        finished_at=1700000000.0,
    )
    clone = TransferRecord.from_dict(rec.to_dict())
    assert clone == rec


def test_record_from_dict_rejects_garbage():
    assert TransferRecord.from_dict(None) is None
    assert TransferRecord.from_dict("nope") is None
    assert TransferRecord.from_dict({"bytes_total": "not-a-number"}) is None


def test_record_from_dict_coerces_and_ignores_unknown_keys():
    rec = TransferRecord.from_dict({"bytes_total": "12", "ok": 0, "future_field": [1]})
    assert rec is not None
    assert rec.bytes_total == 12 and rec.ok is False


# ----------------------------------------------------------------------
# TransferLog
# ----------------------------------------------------------------------
def _rec(i: int, **kw) -> TransferRecord:
    fields = {"source": f"/src/{i}", "destination": f"/dst/{i}"}
    fields.update(kw)
    return TransferRecord(**fields)


def test_log_append_and_read_recent(tmp_path):
    log = TransferLog(tmp_path / "t.jsonl")
    assert log.read_recent() == []
    before = time.time()
    log.append(_rec(1, bytes_total=10))
    log.append(_rec(2, bytes_total=20, ok=False, error="boom"))
    assert log.path.exists()
    # on-disk format: one JSON object per line
    lines = log.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    recs = log.read_recent()
    assert [r.source for r in recs] == ["/src/1", "/src/2"]
    assert recs[0].finished_at >= before
    assert recs[1].ok is False and recs[1].error == "boom"
    assert log.read_recent(limit=1) == [recs[1]]


def test_log_skips_corrupt_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"source": "/a", "destination": "/b"}\nnot json\n[1,2]\n', encoding="utf-8")
    recs = TransferLog(path).read_recent()
    assert [r.source for r in recs] == ["/a"]


def test_log_is_size_bounded(tmp_path):
    log = TransferLog(tmp_path / "t.jsonl", max_records=10)
    for i in range(12):
        log.append(_rec(i))
    recs = log.read_recent(limit=50)
    assert len(recs) == 10
    assert recs[0].source == "/src/2"  # oldest compacted away


def test_log_unicode_paths_roundtrip(tmp_path):
    log = TransferLog(tmp_path / "t.jsonl")
    log.append(_rec(1, source="/srv/données f–ile.txt"))
    assert log.read_recent()[0].source == "/srv/données f–ile.txt"


def test_log_transfer_never_raises(monkeypatch):
    def _boom():
        raise OSError("disk gone")

    monkeypatch.setattr(transfers, "default_log", _boom)
    log_transfer(_rec(1))  # must not raise


def test_default_log_lives_under_home_logs(home, monkeypatch):
    monkeypatch.setattr(transfers, "_default_log", None)
    log = transfers.default_log()
    assert log.path == home / "logs" / "transfers.jsonl"
