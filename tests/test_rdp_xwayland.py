"""In-app RDP on Wayland: XWayland restart decision, client preference, UI."""

from __future__ import annotations

import os
import sys

import pytest

pytestmark = pytest.mark.usefixtures("home")


# --- helpers -------------------------------------------------------------------
def _settings(rdp_client="auto"):
    from rdpstudio.core.settings import Settings

    s = Settings()
    s.rdp_client = rdp_client
    return s


_store_seq = 0


def _store(tmp_path, protocols=("rdp",)):
    global _store_seq
    from rdpstudio.core.models import Session
    from rdpstudio.core.store import SessionStore

    _store_seq += 1  # a fresh file per call — earlier cases must not leak in
    store = SessionStore(tmp_path / f"sessions-{_store_seq}.json")
    for i, proto in enumerate(protocols):
        store.upsert(Session(name=f"s{i}", protocol=proto, host="h", port=3389 if proto == "rdp" else 22))
    return store


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


FAKE_WHICH = {
    "sdl-freerdp3": "/usr/bin/sdl-freerdp3",
    "xfreerdp3": "/usr/bin/xfreerdp3",
    "xfreerdp2": "/usr/bin/xfreerdp2",
}


# --- embeddable client discovery -------------------------------------------------
def test_find_embedded_client_prefers_x11_flavour():
    from rdpstudio.protocols.rdp.embed import find_embedded_client

    got = find_embedded_client(which=FAKE_WHICH.get)
    assert got == "/usr/bin/xfreerdp3"  # not sdl-freerdp3: SDL ignores /parent-window


def test_find_embedded_client_skips_sdl_only():
    from rdpstudio.protocols.rdp.embed import find_embedded_client

    which = {"sdl-freerdp3": "/usr/bin/sdl-freerdp3", "wlfreerdp": "/usr/bin/wlfreerdp"}.get
    assert find_embedded_client(which=which) is None


def test_external_client_may_still_be_sdl(monkeypatch):
    from rdpstudio.protocols.rdp import session as rdp_session

    monkeypatch.setattr(rdp_session.shutil, "which", FAKE_WHICH.get)
    assert rdp_session.find_rdp_client() == ("/usr/bin/sdl-freerdp3", "freerdp")


# --- wayland detection -----------------------------------------------------------
def test_embed_blocked_on_wayland():
    from rdpstudio.protocols.rdp.embed import embed_blocked_on_wayland

    ok = embed_blocked_on_wayland(
        platform_name="wayland", display=":0", find_embedded=lambda: "/usr/bin/xfreerdp3"
    )
    assert ok is True
    # xcb already fine / no XWayland / no embeddable client → nothing to fix
    assert not embed_blocked_on_wayland(platform_name="xcb", display=":0")
    assert not embed_blocked_on_wayland(platform_name="wayland", display="")
    assert not embed_blocked_on_wayland(
        platform_name="wayland", display=":0", find_embedded=lambda: None
    )


# --- restart decision ------------------------------------------------------------
def test_should_relaunch_matrix(tmp_path):
    from rdpstudio.protocols.rdp.embed import should_relaunch_for_embedded

    wayland_env = {"WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
    embedded = lambda: "/usr/bin/xfreerdp3"  # noqa: E731

    # the happy path: wayland + XWayland + xfreerdp + a saved RDP session
    ok, why = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path), "wayland", display=":0",
        find_embedded=embedded, env=wayland_env,
    )
    assert ok, why

    # already restarted once → never again (loop guard)
    ok, _ = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path), "wayland", display=":0",
        find_embedded=embedded, env={**wayland_env, "RDPSTUDIO_XWAYLAND": "1"},
    )
    assert not ok

    # user explicitly wants external windows
    ok, _ = should_relaunch_for_embedded(
        _settings("external"), _store(tmp_path), "wayland", display=":0",
        find_embedded=embedded, env=wayland_env,
    )
    assert not ok

    # user forced a non-wayland Qt platform → respect it
    ok, _ = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path), "wayland", display=":0",
        find_embedded=embedded, env={**wayland_env, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert not ok

    # not a wayland session at all (X11 or anything else)
    ok, _ = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path), "xcb", display=":0",
        find_embedded=embedded, env=wayland_env,
    )
    assert not ok

    # no XWayland → in-app display impossible, keep the wayland session
    ok, why = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path), "wayland", display="",
        find_embedded=embedded, env=wayland_env,
    )
    assert not ok and "XWayland" in why

    # no X11 FreeRDP client → nothing embedding could render with
    ok, why = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path), "wayland", display=":0",
        find_embedded=lambda: None, env=wayland_env,
    )
    assert not ok and "freerdp3-x11" in why

    # auto + no saved RDP sessions + no rdp CLI target → don't disturb the user
    ok, _ = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path, protocols=("ssh",)), "wayland", display=":0",
        find_embedded=embedded, env=wayland_env,
    )
    assert not ok

    # …but an RDP command-line target counts
    ok, _ = should_relaunch_for_embedded(
        _settings("auto"), _store(tmp_path, protocols=("ssh",)), "wayland", display=":0",
        find_embedded=embedded, env=wayland_env, rdp_target=True,
    )
    assert ok

    # explicit "Built-in" preference restarts even with no saved sessions
    ok, _ = should_relaunch_for_embedded(
        _settings("embedded"), _store(tmp_path, protocols=("ssh",)), "wayland", display=":0",
        find_embedded=embedded, env=wayland_env,
    )
    assert ok


# --- startup hook ------------------------------------------------------------------
def test_maybe_relaunch_triggers_with_saved_rdp_session(tmp_path, monkeypatch):
    from rdpstudio.protocols.rdp import embed

    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(embed, "find_embedded_client", lambda: "/usr/bin/xfreerdp3")
    calls = []
    assert embed.maybe_relaunch_for_embedded(
        [], settings=_settings("auto"), store=_store(tmp_path), relaunch=calls.append
    )
    assert calls == [[]]

    # no RDP sessions and no CLI target → quiet no-op
    calls.clear()
    assert not embed.maybe_relaunch_for_embedded(
        [], settings=_settings("auto"), store=_store(tmp_path, protocols=("ssh",)),
        relaunch=calls.append,
    )
    assert not calls


def test_maybe_relaunch_rdp_cli_target(tmp_path, monkeypatch):
    from rdpstudio.protocols.rdp import embed

    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setattr(embed, "find_embedded_client", lambda: "/usr/bin/xfreerdp3")
    calls = []
    assert embed.maybe_relaunch_for_embedded(
        ["admin@10.0.0.9:3389"],
        settings=_settings("auto"),
        store=_store(tmp_path, protocols=()),  # nothing saved at all
        relaunch=calls.append,
    )
    assert calls == [["admin@10.0.0.9:3389"]]


def test_maybe_relaunch_ignores_non_wayland(monkeypatch, tmp_path):
    from rdpstudio.protocols.rdp import embed

    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert not embed.maybe_relaunch_for_embedded(
        [], settings=_settings("embedded"), store=_store(tmp_path), relaunch=lambda a: None
    )


def test_relaunch_under_x11_execs_self(monkeypatch):
    from rdpstudio.protocols.rdp import embed

    captured = {}
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr(
        os, "execv", lambda path, args: captured.update(path=path, args=args)
    )
    embed.relaunch_under_x11(["--verbose"])
    assert os.environ.get("QT_QPA_PLATFORM") == "xcb"
    assert os.environ.get(embed.RELAUNCH_ENV) == "1"
    assert captured["path"] == sys.executable
    assert captured["args"] == [sys.executable, "-m", "rdpstudio", "--verbose"]


def test_relaunch_under_x11_frozen(monkeypatch):
    from rdpstudio.protocols.rdp import embed

    captured = {}
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(os, "execv", lambda path, args: captured.update(path=path, args=args))
    embed.relaunch_under_x11([])
    assert captured["args"] == [sys.executable]


# --- post-restart self-check -----------------------------------------------------
def test_xcb_self_check(monkeypatch):
    from rdpstudio.protocols.rdp import embed

    # not a restarted process → nothing to do
    assert embed.xcb_relaunch_self_check(env={}) is True

    env = {embed.RELAUNCH_ENV: "1", "QT_QPA_PLATFORM": "xcb"}
    monkeypatch.setattr(embed, "xcb_platform_ready", lambda: True)
    assert embed.xcb_relaunch_self_check(env=env) is True

    monkeypatch.setattr(embed, "xcb_platform_ready", lambda: False)
    assert embed.xcb_relaunch_self_check(env=env) is False
    assert "QT_QPA_PLATFORM" not in env  # let Qt pick the native platform
    assert env.get(embed.RELAUNCH_FALLBACK_ENV) == "1"


# --- session controller UI -------------------------------------------------------
def test_rdp_tab_offers_in_app_restart_when_wayland_blocks(tmp_path, qtapp, monkeypatch):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session

    monkeypatch.setattr(rdp_session, "embed_blocked_on_wayland", lambda *a, **k: True)

    controller = rdp_session.RdpSessionController(
        Session(name="win", protocol="rdp", host="w", port=3389), _ctx(tmp_path)
    )
    assert controller._mode == "external"
    assert controller._btn_inapp.isVisibleTo(controller._page_ext)

    # answering "No" must not restart; "Yes" must relaunch
    from PySide6.QtWidgets import QMessageBox

    relaunched = []
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )
    # the controller consumes the function via its own module namespace
    monkeypatch.setattr(rdp_session, "relaunch_under_x11", lambda: relaunched.append(1))
    controller._btn_inapp.click()
    assert relaunched == []

    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    controller._btn_inapp.click()
    assert relaunched == [1]


def test_rdp_tab_no_restart_button_when_embed_unrelated(tmp_path, qtapp, monkeypatch):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session

    monkeypatch.setattr(rdp_session, "embed_blocked_on_wayland", lambda *a, **k: False)
    controller = rdp_session.RdpSessionController(
        Session(name="win", protocol="rdp", host="w", port=3389), _ctx(tmp_path)
    )
    assert not controller._btn_inapp.isVisibleTo(controller._page_ext)


def test_embedded_start_falls_back_without_x11_client(tmp_path, qtapp, monkeypatch):
    """No xfreerdp → embedded start must degrade to the external window."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session

    monkeypatch.setattr(rdp_session.RdpSessionController, "resolve_mode", lambda self: "embedded")
    monkeypatch.setattr(rdp_session, "find_embedded_client", lambda: None)
    fell_back = []
    monkeypatch.setattr(
        rdp_session.RdpSessionController, "_start_external", lambda self: fell_back.append(1)
    )
    controller = rdp_session.RdpSessionController(
        Session(name="win", protocol="rdp", host="w", port=3389), _ctx(tmp_path)
    )
    controller.start()
    assert fell_back == [1]
    assert controller._mode == "external"


# --- settings dialog ---------------------------------------------------------------
def test_settings_dialog_xwayland_button(tmp_path, qtapp, monkeypatch):
    from rdpstudio.protocols.rdp import embed
    from rdpstudio.ui.settings_dialog import SettingsDialog

    monkeypatch.setattr(embed, "embedded_support", lambda **k: (False, "In-app RDP needs X11."))
    monkeypatch.setattr(embed, "embed_blocked_on_wayland", lambda **k: True)
    dlg = SettingsDialog(_ctx(tmp_path))
    assert dlg.btn_xwayland.isVisibleTo(dlg)
    assert "XWayland" in dlg.rdp_status.text()

    monkeypatch.setattr(embed, "embedded_support", lambda **k: (True, ""))
    monkeypatch.setattr(embed, "embed_blocked_on_wayland", lambda **k: False)
    dlg2 = SettingsDialog(_ctx(tmp_path))
    assert not dlg2.btn_xwayland.isVisibleTo(dlg2)
    assert "inside RDP Studio" in dlg2.rdp_status.text()


# --- app entry hook -----------------------------------------------------------------
def test_app_main_calls_relaunch_hook_before_qapp(monkeypatch, qtapp):
    """main() must consult the XWayland hook before creating the QApplication."""
    import rdpstudio.app as app_mod

    order = []

    def fake_maybe(argv):
        order.append("maybe_relaunch")

    monkeypatch.setattr("rdpstudio.protocols.rdp.embed.maybe_relaunch_for_embedded", fake_maybe)

    # main() imports QApplication lazily → patch it where it is fetched from;
    # abort as soon as the QApplication is constructed (before any window)
    class _Boom:
        def __init__(self, *a):
            order.append("qapp")
            raise RuntimeError("stop-here")

    monkeypatch.setattr("PySide6.QtWidgets.QApplication", _Boom)
    with pytest.raises(RuntimeError, match="stop-here"):
        app_mod.main(["--verbose"])
    assert order == ["maybe_relaunch", "qapp"]


# --- end-to-end: real subprocess, simulated Wayland session ------------------------
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX exec/env semantics")
def test_e2e_relaunch_switches_to_xcb(tmp_path):
    """Run the real app on a simulated Wayland desktop (XWayland present).

    With a saved RDP session the process must restart itself via XWayland:
    it comes back on the *xcb* platform (and then fails against the fake,
    server-less display :99 — which proves the switch).  Without any RDP
    session it must stay on its native platform instead.
    """
    import subprocess

    from rdpstudio.core.models import Session
    from rdpstudio.core.store import SessionStore
    from rdpstudio.protocols.rdp.embed import xcb_platform_ready

    if not xcb_platform_ready():
        pytest.skip("xcb platform plugin not loadable on this machine")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_client = bin_dir / "xfreerdp3"
    fake_client.write_text("#!/bin/sh\nexec sleep 60\n")
    fake_client.chmod(0o755)

    def run(home_dir):
        env = dict(os.environ)
        env.update(
            RDPSTUDIO_HOME=str(home_dir),
            WAYLAND_DISPLAY="wayland-0",
            XDG_SESSION_TYPE="wayland",
            DISPLAY=":99",  # XWayland socket that does not exist
        )
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env.pop("QT_QPA_PLATFORM", None)  # app must decide on its own
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "rdpstudio"],
                env=env, capture_output=True, text=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            pytest.fail("app started a GUI instead of deciding — relaunch logic broken?")
        return proc.returncode, (proc.stderr or "") + (proc.stdout or "")

    # with an RDP session saved → restart via XWayland → goes *straight* to
    # xcb against the server-less :99 (no native wayland attempt at all)
    home_with_rdp = tmp_path / "home-rdp"
    home_with_rdp.mkdir()
    store = SessionStore(home_with_rdp / "sessions.json")
    store.upsert(Session(name="win", protocol="rdp", host="192.0.2.10", port=3389))
    rc, out = run(home_with_rdp)
    assert rc != 0
    assert "Failed to create wl_display" not in out, out  # restarted → no wayland try
    assert "qt.qpa.xcb" in out and "could not connect to display" in out, out

    # without any RDP session → no restart: the native wayland platform is
    # attempted first (Qt then falls back to xcb on its own — irrelevant)
    home_plain = tmp_path / "home-plain"
    home_plain.mkdir()
    rc2, out2 = run(home_plain)
    assert rc2 != 0
    assert "Failed to create wl_display" in out2, out2
