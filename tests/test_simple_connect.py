"""Simple connect flow: plain username+password (no vault) + fit display to screen."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("home")


# --- FreeRDP command line ---------------------------------------------------
def test_freerdp_args_fit_screen():
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_freerdp_args

    s = Session(protocol="rdp", host="win.lab", username="admin", rdp_fit_screen=True)
    args = build_freerdp_args(s, password=None)
    assert "/smart-sizing" in args

    s.rdp_fit_screen = False
    args = build_freerdp_args(s, password=None)
    assert "/smart-sizing" not in args


def test_freerdp_password_never_on_cmdline_by_default():
    """The secret must not be readable via `ps` / /proc/<pid>/cmdline."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_freerdp_args, uses_args_file

    s = Session(protocol="rdp", host="win.lab", username="admin", password="s3cret")
    args = build_freerdp_args(s, password="s3cret")
    assert "s3cret" not in " ".join(args)
    assert "/from-stdin" not in args  # FreeRDP 3.x aborts on piped stdin
    assert "/args-from" not in " ".join(args)  # argv stays clean; file added at launch
    assert uses_args_file(s, "s3cret") is True

    # vault-style password: same treatment
    s2 = Session(protocol="rdp", host="win.lab", username="admin")
    args2 = build_freerdp_args(s2, password="vpass")
    assert "vpass" not in " ".join(args2)

    # explicit opt-in still supported (documented as insecure)
    s2.rdp_pass_on_cmdline = True
    assert "/p:vpass" in build_freerdp_args(s2, password="vpass")
    assert uses_args_file(s2, "vpass") is False


def test_freerdp_no_stdin_flag_without_password():
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_freerdp_args, uses_args_file

    s = Session(protocol="rdp", host="win.lab", username="admin")
    args = build_freerdp_args(s, password=None)
    assert "/from-stdin" not in args
    assert "/p:" not in " ".join(args)
    assert uses_args_file(s, None) is False


# --- mstsc .rdp file ---------------------------------------------------------
def test_rdp_file_smart_sizing():
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.rdpfile import build_rdp_text

    s = Session(protocol="rdp", host="w", username="a")
    assert "smart sizing:i:0" in build_rdp_text(s).splitlines()
    s.rdp_fit_screen = True
    assert "smart sizing:i:1" in build_rdp_text(s).splitlines()


# --- secret resolution -------------------------------------------------------
def _ctx(tmp_path):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    return SessionContext(
        settings=Settings(),
        store=SessionStore(tmp_path / "sessions.json"),
        vault=None,
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )


def test_rdp_saved_password_resolved_without_vault(tmp_path, qtapp):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    s = Session(protocol="rdp", host="w", username="a", password="s3cret")
    ctrl = RdpSessionController(s, _ctx(tmp_path), qtapp)
    assert ctrl._resolve_secret() == "s3cret"

    s.password = ""
    assert ctrl._resolve_secret() is None  # no vault, nothing saved → logon prompt


def test_ssh_saved_password_becomes_material(qtapp, tmp_path):
    from rdpstudio.core.models import AUTH_PASSWORD, Session
    from rdpstudio.protocols.ssh.session import SshSessionController

    s = Session(protocol="ssh", host="h", username="u", password="s3cret", auth=AUTH_PASSWORD)
    ctrl = SshSessionController(s, _ctx(tmp_path), qtapp)
    material = ctrl._build_material(s)
    assert material.password == "s3cret"
    assert material.username == "u"

    # empty saved password → worker will prompt at connect
    s.password = ""
    assert SshSessionController(s, _ctx(tmp_path), qtapp)._build_material(s).password is None


# --- dialog wiring -----------------------------------------------------------
def test_session_dialog_exposes_simple_fields(qtapp, tmp_path):
    from rdpstudio.core.models import Session
    from rdpstudio.ui.session_dialog import SessionDialog

    ctx = _ctx(tmp_path)
    dlg = SessionDialog(ctx, Session(protocol="rdp", host="w"), None)
    # username + password on the main page…
    dlg.username.setText("admin")
    dlg.password.setText("s3cret")
    # …and the fit-to-screen switch on the RDP page
    dlg.protocol.setCurrentIndex(dlg.protocol.findData("rdp"))
    dlg.rdp_fit_screen.setChecked(True)
    dlg._on_save()

    loaded = ctx.store.get(dlg.session.id)
    assert loaded.username == "admin"
    assert loaded.password == "s3cret"
    assert loaded.rdp_fit_screen is True


def test_session_dialog_port_follows_protocol(qtapp, tmp_path):
    from rdpstudio.core.models import Session
    from rdpstudio.ui.session_dialog import SessionDialog

    ctx = _ctx(tmp_path)
    dlg = SessionDialog(ctx, Session(protocol="ssh"), None)
    assert dlg.port.value() == 22
    dlg.protocol.setCurrentIndex(dlg.protocol.findData("rdp"))
    assert dlg.port.value() == 3389  # moved to the RDP default
    dlg.port.setValue(2222)  # user-typed port survives a protocol switch
    dlg.protocol.setCurrentIndex(dlg.protocol.findData("ssh"))
    assert dlg.port.value() == 2222
