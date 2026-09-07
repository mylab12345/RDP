"""Pure unit tests for RDP client command policy."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from rdpstudio.core.models import Session
from rdpstudio.protocols.rdp import client
from rdpstudio.protocols.rdp.client import (
    build_embedded_args,
    build_freerdp_args,
    freerdp_supports_args_from_file,
    write_args_file,
)
from rdpstudio.protocols.rdp.rdpfile import build_rdp_text

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_freerdp_certificate_policy_is_tofu_by_default():
    session = Session(protocol="rdp", host="windows.example", rdp_cert_ignore=False)
    args = build_freerdp_args(session, None)
    assert "/cert:tofu" in args
    assert "/cert:ignore" not in args

    session.rdp_cert_ignore = True
    args = build_freerdp_args(session, None)
    assert "/cert:ignore" in args
    assert "/cert:tofu" not in args


def test_mstsc_certificate_policy_follows_same_opt_in():
    session = Session(protocol="rdp", host="windows.example", rdp_cert_ignore=False)
    assert "authentication level:i:2" in build_rdp_text(session)

    session.rdp_cert_ignore = True
    assert "authentication level:i:0" in build_rdp_text(session)


def test_embedded_command_policy_is_qt_independent_and_secret_safe():
    session = Session(
        protocol="rdp",
        host="windows.example",
        username="admin",
        rdp_fullscreen=True,
        rdp_fit_screen=True,
    )
    args = build_embedded_args(session, "top-secret", 42, size=(1200, 700))
    assert "/parent-window:42" in args
    assert "/size:1200x700" in args
    assert "/dynamic-resolution" in args
    assert "/smart-sizing" not in args
    assert "/f" not in args
    assert "top-secret" not in " ".join(args)


def test_args_file_rejects_option_injection_before_creating_file(monkeypatch):
    def must_not_create(*_args, **_kwargs):
        raise AssertionError("mkstemp must not run for invalid arguments")

    monkeypatch.setattr(client.tempfile, "mkstemp", must_not_create)
    with pytest.raises(ValueError, match="line breaks"):
        write_args_file(["/v:server", "/u:user\n/cert:ignore"])
    with pytest.raises(ValueError, match="NUL"):
        write_args_file(["/v:server\x00/cert:ignore"])


def test_args_file_cleanup_when_flush_fails(tmp_path, monkeypatch):
    real_mkstemp = client.tempfile.mkstemp

    def local_mkstemp(*, prefix, suffix):
        return real_mkstemp(dir=tmp_path, prefix=prefix, suffix=suffix)

    monkeypatch.setattr(client.tempfile, "mkstemp", local_mkstemp)
    monkeypatch.setattr(client.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError, match="disk full"):
        write_args_file(["/v:server"])
    assert list(tmp_path.iterdir()) == []


def test_freerdp_version_capability_detection_is_cached(monkeypatch):
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        return SimpleNamespace(stdout="This is FreeRDP version 3.9.0", stderr="")

    monkeypatch.setattr(client.subprocess, "run", run)
    freerdp_supports_args_from_file._cache = {}
    assert freerdp_supports_args_from_file("/opt/xfreerdp") is True
    assert freerdp_supports_args_from_file("/opt/xfreerdp") is True
    assert calls == [["/opt/xfreerdp", "--version"]]


def test_freerdp_version_probe_failure_degrades_safely(monkeypatch):
    def fail(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("xfreerdp", 5)

    monkeypatch.setattr(client.subprocess, "run", fail)
    freerdp_supports_args_from_file._cache = {}
    assert freerdp_supports_args_from_file("/opt/hung-xfreerdp") is False
