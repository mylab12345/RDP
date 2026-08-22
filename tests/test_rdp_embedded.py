"""Built-in (embedded) RDP display: support detection, args, mode selection."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("home")


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


# --- support detection --------------------------------------------------------
def test_embedded_support_matrix():
    from rdpstudio.protocols.rdp.session import embedded_support

    # mstsc cannot be embedded
    ok, why = embedded_support(
        find_client=lambda: ("/x/mstsc.exe", "mstsc"), platform_name="xcb", display=":0"
    )
    assert not ok and "mstsc" in why

    # no client at all
    ok, why = embedded_support(find_client=lambda: None, platform_name="xcb", display=":0")
    assert not ok and "FreeRDP" in why

    # X11 FreeRDP + X11 + display → ok
    ok, why = embedded_support(
        find_client=lambda: ("/usr/bin/xfreerdp3", "freerdp"),
        platform_name="xcb",
        display=":0",
        find_embedded=lambda: "/usr/bin/xfreerdp3",
    )
    assert ok and why == ""

    # SDL/Wayland FreeRDP flavour cannot embed — hint must say what to install
    ok, why = embedded_support(
        find_client=lambda: ("/usr/bin/sdl-freerdp3", "freerdp"),
        platform_name="xcb",
        display=":0",
        find_embedded=lambda: None,
    )
    assert not ok and "freerdp3-x11" in why

    # Wayland with XWayland available → actionable restart hint
    ok, why = embedded_support(
        find_client=lambda: ("/usr/bin/xfreerdp3", "freerdp"),
        platform_name="wayland",
        display=":0",
        find_embedded=lambda: "/usr/bin/xfreerdp3",
    )
    assert not ok and "XWayland" in why

    # Wayland without any X server → plain X11 explanation
    ok, why = embedded_support(
        find_client=lambda: ("/usr/bin/xfreerdp3", "freerdp"),
        platform_name="wayland",
        display="",
        find_embedded=lambda: "/usr/bin/xfreerdp3",
    )
    assert not ok and "X11" in why

    # no $DISPLAY
    ok, why = embedded_support(
        find_client=lambda: ("/usr/bin/xfreerdp3", "freerdp"),
        platform_name="xcb",
        display="",
        find_embedded=lambda: "/usr/bin/xfreerdp3",
    )
    assert not ok and "DISPLAY" in why


# --- embedded command line ----------------------------------------------------
def test_build_embedded_args():
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_embedded_args

    s = Session(protocol="rdp", host="w", port=3389, username="u", password="s3cret", rdp_fit_screen=True)
    args = build_embedded_args(s, "s3cret", 0x1234)
    assert "/parent-window:4660" in args
    assert "-decorations" in args
    assert "/smart-sizing" in args
    # password goes over stdin, never argv
    assert "s3cret" not in " ".join(args)
    assert "/from-stdin" in args
    assert "/v:w" in args
    assert "/u:u" in args


def test_embedded_args_drop_fullscreen():
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_embedded_args

    s = Session(protocol="rdp", host="w", rdp_fullscreen=True)
    args = build_embedded_args(s, None, 7)
    assert "/f" not in args
    assert "/parent-window:7" in args


# --- mode selection -------------------------------------------------------------
def test_mode_pref_external(tmp_path, qtapp):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "external"
    ctrl = RdpSessionController(Session(protocol="rdp", host="w"), ctx, qtapp)
    assert ctrl._mode == "external"
    assert ctrl.widget() is ctrl._page_ext


def test_mode_auto_falls_back_without_x11(tmp_path, qtapp, monkeypatch):
    """Auto mode: FreeRDP present but Qt is offscreen → external (no X11 embedding)."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "auto"
    monkeypatch.setattr(rdp_session, "find_rdp_client", lambda: ("/usr/bin/xfreerdp3", "freerdp"))
    ctrl = RdpSessionController(Session(protocol="rdp", host="w"), ctx, qtapp)
    assert ctrl._mode == "external"
    assert ctrl.widget() is ctrl._page_ext


def test_mode_embedded_when_available(tmp_path, qtapp, monkeypatch):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "auto"
    monkeypatch.setattr(rdp_session, "embedded_support", lambda *a, **k: (True, ""))
    ctrl = RdpSessionController(Session(protocol="rdp", host="w"), ctx, qtapp)
    assert ctrl._mode == "embedded"
    assert ctrl.widget() is ctrl._page_emb


def test_mode_embedded_unavailable_warns(tmp_path, qtapp, monkeypatch):
    """User forced built-in but it's not possible → falls back to external."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    monkeypatch.setattr(rdp_session, "embedded_support", lambda *a, **k: (False, "no X11"))
    ctrl = RdpSessionController(Session(protocol="rdp", host="w"), ctx, qtapp)
    assert ctrl._mode == "external"


def test_embedded_launch_passes_parent_window(tmp_path, qtapp, monkeypatch):
    """The embedded client is launched with /parent-window + -decorations."""
    from PySide6.QtCore import QProcess

    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    argv_file = tmp_path / "argv.txt"
    script = tmp_path / "fake-freerdp.sh"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {argv_file}\nsleep 30\n")
    script.chmod(0o755)
    monkeypatch.setattr(rdp_session, "find_rdp_client", lambda: (str(script), "freerdp"))
    monkeypatch.setattr(rdp_session, "find_embedded_client", lambda: str(script))
    monkeypatch.setattr(rdp_session, "embedded_support", lambda *a, **k: (True, ""))

    ctrl = RdpSessionController(Session(protocol="rdp", host="w", port=3389, username="u"), ctx, qtapp)
    assert ctrl._mode == "embedded"
    # offscreen Qt has no native X window — fake the window id
    monkeypatch.setattr(type(ctrl._surface), "winId", lambda self: 0xABC)

    ctrl.start()
    import time

    for _ in range(200):  # wait for the fake client to record its arguments
        qtapp.processEvents()
        if argv_file.exists() and ctrl._proc is not None:
            break
        time.sleep(0.05)
    assert ctrl._proc is not None, "embedded client did not start"
    argv = argv_file.read_text().splitlines()
    assert "/parent-window:2748" in argv  # 0xABC == 2748
    assert "-decorations" in argv
    assert "/v:w" in argv
    assert "/size:1600x900" in argv
    ctrl.stop("done")
    for _ in range(100):  # wait for the fake client to actually die
        qtapp.processEvents()
        if ctrl._proc is None or ctrl._proc.state() == QProcess.ProcessState.NotRunning:
            break
        time.sleep(0.05)
