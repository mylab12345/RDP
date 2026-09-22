"""Tests for the SFTP/SCP transfer engine: protocol dispatch, blind-SCP
fallback, cancel-aware retry and transfer-history logging.

The engine is exercised directly (no threads, no network) with stubbed SFTP
and SCP clients.
"""

from __future__ import annotations

import stat as statmod
from types import SimpleNamespace

import pytest

from rdpstudio.core.retry import RetryPolicy
from rdpstudio.protocols.ssh import sftp as sftp_mod
from rdpstudio.protocols.ssh.scp import ScpError, ScpStats
from rdpstudio.protocols.ssh.sftp import SftpEngine, TransferJob


class FakeSftp:
    """Minimal SFTP surface used by totals/classification."""

    def __init__(self, entries: dict[str, tuple[bool, int]]):
        # path -> (is_dir, size)
        self.entries = entries

    def stat(self, path: str):
        is_dir, size = self.entries[path]
        mode = statmod.S_IFDIR | 0o755 if is_dir else statmod.S_IFREG | 0o644
        return SimpleNamespace(st_mode=mode, st_size=size)

    def listdir(self, path: str):
        prefix = path.rstrip("/") + "/"
        kids = set()
        for p in self.entries:
            if p.startswith(prefix) and "/" not in p[len(prefix):]:
                kids.add(p[len(prefix):])
        return sorted(kids)


class FakeScp:
    """Records download/upload calls and replays scripted outcomes."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.download_impl = None
        self.upload_impl = None

    def download(self, remote, local, **kw):
        self.calls.append(("download", remote, str(local), kw))
        if self.download_impl is not None:
            return self.download_impl(remote, local, **kw)
        return ScpStats(files=1, bytes=7)

    def upload(self, local, remote, **kw):
        self.calls.append(("upload", str(local), remote, kw))
        if self.upload_impl is not None:
            return self.upload_impl(local, remote, **kw)
        return ScpStats(files=1, bytes=9)


def _job(**kw) -> TransferJob:
    base = {"op_id": "op1", "direction": "download", "remote_root": "/r",
            "local_root": "/tmp/l", "sources": ["f"], "dest": "/tmp/l",
            "protocol": "scp", "session": "sess"}
    base.update(kw)
    return TransferJob(**base)


@pytest.fixture()
def engine(qtapp, monkeypatch):
    eng = SftpEngine(transport_provider=lambda: object(), session_name="sess",
                     transfer_protocol="sftp")
    monkeypatch.setattr(sftp_mod, "TRANSFER_RETRY",
                        RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0))
    return eng


def _open_with(engine, fake: FakeSftp, monkeypatch):
    monkeypatch.setattr(engine, "ensure_open", lambda: setattr(engine, "_sftp", fake))


# ----------------------------------------------------------------------
# download dispatch
# ----------------------------------------------------------------------
def test_scp_download_file_not_recursive(engine, monkeypatch, tmp_path):
    _open_with(engine, FakeSftp({"/r/f.txt": (False, 10)}), monkeypatch)
    fake = FakeScp()
    monkeypatch.setattr(engine, "_scp_client", lambda: fake)
    job = _job()
    engine._download_scp(["/r/f.txt"], str(tmp_path), job)
    assert fake.calls == [("download", "/r/f.txt", str(tmp_path),
                           {"recursive": False, "progress": fake.calls[0][3]["progress"]})]
    assert fake.calls[0][3]["recursive"] is False
    assert (job.total_bytes, job.files_total, job.files_done) == (10, 1, 1)


def test_scp_download_dir_is_recursive(engine, monkeypatch, tmp_path):
    entries = {"/r/d": (True, 0), "/r/d/a": (False, 5), "/r/d/b": (False, 6)}
    _open_with(engine, FakeSftp(entries), monkeypatch)
    fake = FakeScp()
    monkeypatch.setattr(engine, "_scp_client", lambda: fake)
    engine._download_scp(["/r/d"], str(tmp_path), _job())
    assert fake.calls[0][3]["recursive"] is True


def test_scp_blind_fallback_retries_as_directory(engine, monkeypatch, tmp_path):
    def _no_sftp():
        raise OSError("subsystem request failed")

    monkeypatch.setattr(engine, "ensure_open", _no_sftp)
    fake = FakeScp()

    def _dl(remote, local, **kw):
        if not kw.get("recursive"):
            raise ScpError(f"{remote}: not a regular file")
        return ScpStats(files=2, bytes=3)

    fake.download_impl = _dl
    monkeypatch.setattr(engine, "_scp_client", lambda: fake)
    job = _job()
    engine._download_scp(["/r/d"], str(tmp_path), job)
    assert [c[3].get("recursive", False) for c in fake.calls] == [False, True]
    assert job.files_done == 2  # totals stay indeterminate (0) without SFTP
    assert (job.total_bytes, job.files_total) == (0, 0)


def test_scp_blind_fallback_does_not_mask_real_errors(engine, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "ensure_open", lambda: (_ for _ in ()).throw(OSError("down")))
    fake = FakeScp()
    fake.download_impl = lambda *a, **k: (_ for _ in ()).throw(ScpError("permission denied"))
    monkeypatch.setattr(engine, "_scp_client", lambda: fake)
    with pytest.raises(ScpError, match="permission denied"):
        engine._download_scp(["/r/f"], str(tmp_path), _job())


# ----------------------------------------------------------------------
# upload dispatch
# ----------------------------------------------------------------------
def test_scp_upload_marks_dirs_recursive(engine, monkeypatch, tmp_path):
    f = tmp_path / "f.txt"
    f.write_bytes(b"12345")
    d = tmp_path / "d"
    d.mkdir()
    (d / "g.txt").write_bytes(b"12")
    fake = FakeScp()
    monkeypatch.setattr(engine, "_scp_client", lambda: fake)
    job = _job(direction="upload", local_root=str(tmp_path), sources=["f.txt", "d"], dest="/r")
    engine._upload_scp([str(f), str(d)], "/r", job)
    flags = [c[3]["recursive"] for c in fake.calls]
    assert flags == [False, True]
    assert (job.total_bytes, job.files_total) == (7, 2)


# ----------------------------------------------------------------------
# transfer mode + retry + history
# ----------------------------------------------------------------------
def test_set_transfer_mode(engine):
    assert engine.transfer_mode == "sftp"
    engine.set_transfer_mode("scp")
    assert engine.transfer_mode == "scp"
    engine.set_transfer_mode("bogus")  # ignored
    assert engine.transfer_mode == "scp"


def test_with_retry_recovers_transient(engine):
    attempts: list[int] = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionResetError("reset")
        return "done"

    assert engine._with_retry(_job(), flaky) == "done"
    assert len(attempts) == 2


def test_with_retry_gives_up_and_reraises(engine):
    def down():
        raise TimeoutError("still down")

    with pytest.raises(TimeoutError):
        engine._with_retry(_job(), down)


def test_with_retry_rejects_permanent_immediately(engine):
    calls: list[int] = []

    def bad():
        calls.append(1)
        raise PermissionError("denied")

    with pytest.raises(PermissionError):
        engine._with_retry(_job(), bad)
    assert len(calls) == 1


def test_with_retry_honours_cancel(engine):
    job = _job()
    job.cancelled.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        engine._with_retry(job, lambda: pytest.fail("must not run"))


def test_finish_logs_success_record(engine, monkeypatch):
    seen: list = []
    monkeypatch.setattr(sftp_mod, "log_transfer", seen.append)
    done: list = []
    engine.transferDone.connect(lambda *a: done.append(a))
    job = _job(done_bytes=100, total_bytes=100, files_done=2, files_total=2)
    engine._finish(job, True, "ok")
    assert done == [("op1", True, "ok")]
    (rec,) = seen
    assert rec.protocol == "scp" and rec.direction == "download"
    assert rec.session == "sess" and rec.ok is True and rec.error == ""
    assert (rec.bytes_total, rec.files_total) == (100, 2)
    assert "/r" in rec.source and rec.destination == "/tmp/l"
    assert "op1" not in engine._jobs


def test_finish_logs_failure_with_truncated_error(engine, monkeypatch):
    seen: list = []
    monkeypatch.setattr(sftp_mod, "log_transfer", seen.append)
    job = _job(done_bytes=10, total_bytes=50, files_done=1, files_total=3)
    engine._finish(job, False, "x" * 500)
    (rec,) = seen
    assert rec.ok is False and len(rec.error) == 300
    assert (rec.bytes_total, rec.files_total) == (50, 3)


def test_slots_reject_empty_names_without_history(engine, monkeypatch):
    seen: list = []
    logged: list = []
    engine.transferDone.connect(lambda *a: seen.append(a))
    monkeypatch.setattr(sftp_mod, "log_transfer", logged.append)
    engine.download("op-e", "/r", "   ")
    engine.upload("op-e2", "/tmp", "")
    assert seen == [("op-e", False, "nothing selected"), ("op-e2", False, "nothing selected")]
    assert logged == [] and engine._jobs == {}
