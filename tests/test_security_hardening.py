"""Regression tests for the security hardening pass.

Each test pins a specific weakness that was fixed; they should fail loudly if
anyone reintroduces the old behaviour.
"""

from __future__ import annotations

import os
import stat

import pytest

pytestmark = pytest.mark.usefixtures("home")


# --- credentials must never reach the process command line -------------------
def test_rdp_password_not_in_argv_by_default():
    import stat as _stat

    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import (
        build_freerdp_args,
        uses_args_file,
        write_args_file,
    )

    s = Session(protocol="rdp", host="h", username="u", password="hunter2")
    args = build_freerdp_args(s, "hunter2")
    assert "hunter2" not in " ".join(args)
    assert "/from-stdin" not in args  # broken on piped stdin (FreeRDP 3.x)
    assert uses_args_file(s, "hunter2") is True

    # secret travels in a 0600 args file for /args-from:file:
    f = write_args_file(build_freerdp_args(s, "hunter2") + ["/p:hunter2"])
    try:
        assert _stat.S_IMODE(f.stat().st_mode) & 0o077 == 0
        assert "hunter2" in f.read_text()
    finally:
        f.unlink(missing_ok=True)


# --- state files must be private --------------------------------------------
@pytest.mark.skipif(os.name != "posix", reason="POSIX permission model")
def test_state_dir_and_session_file_are_private(home):
    from rdpstudio.core import paths
    from rdpstudio.core.models import Session
    from rdpstudio.core.store import SessionStore

    app_dir = paths.app_dir()
    assert stat.S_IMODE(app_dir.stat().st_mode) & 0o077 == 0

    store = SessionStore(paths.sessions_file())
    store.upsert(Session(host="h", username="u", password="plaintext"))
    mode = stat.S_IMODE(paths.sessions_file().stat().st_mode)
    assert mode & 0o077 == 0, f"sessions file is group/world accessible: {oct(mode)}"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission model")
def test_rdp_file_is_private_and_path_safe(tmp_path):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.rdpfile import write_rdp_file

    s = Session(protocol="rdp", host="h", name="../../escape attempt")
    path = write_rdp_file(s, directory=tmp_path)
    assert path.parent == tmp_path, "filename escaped the target directory"
    assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


# --- SFTP downloads stay inside the destination -------------------------------
def test_sftp_download_paths_are_contained(tmp_path):
    from rdpstudio.protocols.ssh.sftp import _safe_child

    base = tmp_path.resolve()
    for name in ("f.txt", "../../etc/passwd", "/etc/shadow", "....//x"):
        resolved = _safe_child(str(tmp_path), name)
        assert base in resolved.parents or resolved == base

    with pytest.raises(RuntimeError):
        _safe_child(str(tmp_path), "..")


# --- OSC-52 clipboard cannot be re-asserted forever ---------------------------
def test_osc52_only_reports_fresh_payloads():
    from rdpstudio.ui.terminal import TerminalCore

    core = TerminalCore()
    assert core.feed(b"\x1b]52;c;aGVsbG8=\x07") == "hello"
    # plain output afterwards must NOT keep re-setting the clipboard
    assert core.feed(b"just some output\r\n") is None
    assert core.feed(b"more output") is None


def test_osc52_rejects_oversized_payload():
    from rdpstudio.ui.terminal import _MAX_OSC52_B64, TerminalCore

    core = TerminalCore()
    huge = b"QQ" * _MAX_OSC52_B64
    assert core.feed(b"\x1b]52;c;" + huge + b"\x07") is None
