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
    # password never rides argv — delivered via /args-from:file: (0600)
    assert "s3cret" not in " ".join(args)
    assert "/from-stdin" not in args
    assert "/v:w" in args
    assert "/u:u" in args


def test_build_embedded_args_detected_size_overrides_session_resolution():
    """Fit mode: the detected display size replaces the saved /size so the
    whole remote screen is visible inside the tab."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_embedded_args

    s = Session(protocol="rdp", host="w", rdp_width=1600, rdp_height=900)
    args = build_embedded_args(s, None, 7, size=(1234, 720))
    size_args = [a for a in args if a.startswith("/size:")]
    assert size_args == ["/size:1234x720"]
    # exactly one /size on the command line (the session default was replaced)
    assert len([a for a in args if a.startswith("/size:")]) == 1


def test_build_embedded_args_detected_size_clamped():
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_embedded_args

    s = Session(protocol="rdp", host="w")
    # below the FreeRDP/Windows minimum → clamped up
    args = build_embedded_args(s, None, 7, size=(100, 100))
    assert "/size:640x480" in args
    # beyond the maximum → clamped down
    args = build_embedded_args(s, None, 7, size=(10000, 5000))
    assert "/size:7680x4320" in args


def test_embedded_args_drop_fullscreen():
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import build_embedded_args

    s = Session(protocol="rdp", host="w", rdp_fullscreen=True)
    args = build_embedded_args(s, None, 7)
    assert "/f" not in args
    assert "/parent-window:7" in args


def test_detected_size_follows_surface(tmp_path, qtapp):
    """The embedded desktop resolution tracks the tab's display area, falling
    back to the saved session resolution only while the widget is unmapped."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    ctrl = RdpSessionController(Session(protocol="rdp", host="w", rdp_width=1600, rdp_height=900), ctx, qtapp)

    # surface is laid out → remote desktop matches it exactly
    ctrl._surface.resize(1280, 700)
    assert ctrl._detected_size() == (1280, 700)

    # clamped to the supported range
    ctrl._surface.resize(400, 300)  # below the FreeRDP/Windows minimum
    assert ctrl._detected_size() == (640, 480)
    ctrl._surface.resize(9000, 9000)  # beyond the maximum
    assert ctrl._detected_size() == (7680, 4320)

    # tiny/unmapped widget → fall back to the saved session resolution
    ctrl._surface.resize(10, 10)
    ctrl.definition.rdp_width, ctrl.definition.rdp_height = 1600, 900
    assert ctrl._detected_size() == (1600, 900)


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
    # client is started as: xfreerdp /args-from:file:<f> — dump both the
    # launcher argv and the args-file contents so assertions cover both
    script = tmp_path / "fake-freerdp.sh"
    script.write_text(
        "#!/bin/sh\n"
        "{ printf '%s\\n' \"$@\"; "
        "for a in \"$@\"; do case \"$a\" in /args-from:file:*) cat \"${a#/args-from:file:}\";; esac; done; } "
        f"> {argv_file}\n"
        "sleep 30\n"
    )
    script.chmod(0o755)
    monkeypatch.setattr(rdp_session, "find_rdp_client", lambda: (str(script), "freerdp"))
    monkeypatch.setattr(rdp_session, "find_embedded_client", lambda: str(script))
    monkeypatch.setattr(rdp_session, "embedded_support", lambda *a, **k: (True, ""))
    # pretend this FreeRDP supports /args-from:file: (FreeRDP 3.x)
    monkeypatch.setattr(rdp_session, "_freerdp_supports_args_from_file", lambda *a, **k: True)

    ctrl = RdpSessionController(
        Session(protocol="rdp", host="w", port=3389, username="u", password="s3cret"),
        ctx, qtapp,
    )
    assert ctrl._mode == "embedded"
    # offscreen Qt has no native X window — fake the window id
    monkeypatch.setattr(type(ctrl._surface), "winId", lambda self: 0xABC)
    # the tab's display area is what the remote desktop must fit
    ctrl._surface.resize(1920, 1080)

    ctrl.start()
    import time

    # wait until the fake client recorded the launcher argv AND flushed the
    # expanded args-file contents (cat runs as a second process after printf)
    for _ in range(200):
        qtapp.processEvents()
        if argv_file.exists() and "/parent-window" in argv_file.read_text():
            break
        time.sleep(0.05)
    assert ctrl._proc is not None, "embedded client did not start"
    argv = argv_file.read_text().splitlines()
    assert any(a.startswith("/args-from:file:") for a in argv)  # secret-safe delivery
    assert "/parent-window:2748" in argv  # 0xABC == 2748
    assert "-decorations" in argv
    assert "/v:w" in argv
    # fit-to-display: the remote screen matches the detected tab size, so the
    # entire desktop is visible inside the app (not the fixed session default)
    assert "/size:1920x1080" in argv
    assert "/size:1600x900" not in argv
    ctrl.stop("done")
    for _ in range(100):  # wait for the fake client to actually die
        qtapp.processEvents()
        if ctrl._proc is None or ctrl._proc.state() == QProcess.ProcessState.NotRunning:
            break
        time.sleep(0.05)


# --- sidebar toggle must not disturb a live session ---------------------------
def _install_fake_client(tmp_path, monkeypatch) -> list[list[str]]:
    """A stand-in xfreerdp that records every launch and stays alive.

    Returns the list of recorded argument lists (one per launch).
    """
    from rdpstudio.protocols.rdp import session as rdp_session

    script = tmp_path / "fake-freerdp.sh"
    script.write_text("#!/bin/sh\nwhile true; do sleep 0.05; done\n")
    script.chmod(0o755)
    monkeypatch.setattr(rdp_session, "find_rdp_client", lambda: (str(script), "freerdp"))
    monkeypatch.setattr(rdp_session, "find_embedded_client", lambda: str(script))
    monkeypatch.setattr(rdp_session, "embedded_support", lambda *a, **k: (True, ""))

    launches: list[list[str]] = []
    original = rdp_session.RdpSessionController._launch_client

    def counting(self, path, args, direct_argv=None):
        launches.append(list(args or direct_argv or []))
        return original(self, path, args, direct_argv)

    monkeypatch.setattr(rdp_session.RdpSessionController, "_launch_client", counting)
    return launches


def _open_connected_rdp_tab(tmp_path, monkeypatch, qtapp):
    """MainWindow with one embedded RDP tab whose handshake has completed."""
    import time

    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import Session
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.ui.main_window import MainWindow
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    launches = _install_fake_client(tmp_path, monkeypatch)
    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(tmp_path / "sessions.json"),
        vault=None,
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    ctx.settings.rdp_client = "embedded"
    win = MainWindow(ctx)
    win.resize(1400, 900)
    win.show()
    for _ in range(40):
        qtapp.processEvents()
        time.sleep(0.01)
    ctx.store.upsert(Session(protocol="rdp", host="win-server", port=3389, username="u"))
    tab = win.open_session(ctx.store.sessions()[0])
    ctrl = tab.controller
    for _ in range(60):  # let the surface get laid out and the client start
        qtapp.processEvents()
        time.sleep(0.01)
    assert ctrl._mode == "embedded"
    assert ctrl._proc is not None and ctrl._proc.processId(), "fake client did not start"
    ctrl._mark_connected()  # the 15 s startup grace elapsed
    assert ctrl.state() == "connected"
    return win, tab, ctrl, launches


def _pump(qtapp, seconds: float) -> None:
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qtapp.processEvents()
        time.sleep(0.005)


def test_sidebar_toggle_keeps_embedded_session_alive(tmp_path, qtapp, monkeypatch):
    """Regression: hiding/showing the sidebar killed the RDP session.

    The tween resizes the tab, the resize handler killed FreeRDP, QProcess
    reported that kill as "client crashed", and the session ended up CLOSED —
    the user had to reconnect by hand.
    """
    win, tab, ctrl, launches = _open_connected_rdp_tab(tmp_path, monkeypatch, qtapp)
    try:
        pid = ctrl._proc.processId()
        errors = []
        ctrl.statusInfo.connect(lambda info: errors.append(info.get("error")))

        win._toggle_sidebar(False)  # hide
        _pump(qtapp, 1.5)
        win._toggle_sidebar(True)  # show again
        _pump(qtapp, 1.5)

        # the session never went down: same client process, still connected
        assert ctrl._proc is not None and ctrl._proc.processId() == pid
        assert ctrl.state() == "connected"
        assert ctrl._proc.state() == ctrl._proc.ProcessState.Running
        assert len(launches) == 1, "the client must not be relaunched for a sidebar toggle"
        assert not [e for e in errors if e], f"session reported errors: {errors}"
        assert "CONNECTED" in tab.chip.text().upper()
        assert "crash" not in tab.chip.text().lower()
        assert ctrl._emb_hint.text() == ""  # no "crashed"/"reconnecting" hint
    finally:
        ctrl.stop("test done")
        win.close()
        _pump(qtapp, 0.3)


def test_rapid_sidebar_toggles_do_not_relaunch_or_stack_tweens(
    tmp_path, qtapp, monkeypatch
):
    """Hammering Ctrl+B must not stack animations or restart the client."""
    win, tab, ctrl, launches = _open_connected_rdp_tab(tmp_path, monkeypatch, qtapp)
    try:
        pid = ctrl._proc.processId()
        for _ in range(6):
            win._toggle_sidebar(None)  # the plain-trigger (invert) path
            _pump(qtapp, 0.03)
        _pump(qtapp, 1.5)
        assert len(launches) == 1
        assert ctrl.state() == "connected"
        assert ctrl._proc.processId() == pid
    finally:
        ctrl.stop("test done")
        win.close()
        _pump(qtapp, 0.3)


def test_sidebar_tween_replaces_a_running_animation(tmp_path, qtapp, monkeypatch):
    """One tween at a time: a mid-flight reversal must not leave both running.

    Stacked animations fight over the splitter sizes, which multiplies the
    layout churn every open session has to absorb.
    """
    from PySide6.QtCore import QAbstractAnimation

    win, tab, ctrl, _launches = _open_connected_rdp_tab(tmp_path, monkeypatch, qtapp)
    running = QAbstractAnimation.State.Running
    try:
        full_width = win._sidebar_width()
        win._toggle_sidebar(False)
        _pump(qtapp, 0.06)  # partway through the 140 ms tween
        first = win._sidebar_anim
        assert first is not None and first.state() == running

        first_updates: list[int] = []
        first.valueChanged.connect(lambda v: first_updates.append(int(v)))
        win._toggle_sidebar(True)  # reverse before the first tween finished
        second = win._sidebar_anim
        assert second is not None and second is not first, "the running tween was replaced"
        _pump(qtapp, 0.8)

        # the replaced tween is stopped, not left driving the splitter too
        assert first_updates == [], f"the superseded tween kept running: {first_updates}"

        # the reversal completed: the sidebar is back at its full width
        assert win._sidebar_width() == full_width
        assert not win._sidebar_collapsed
        assert win._act_sidebar_toolbar.isChecked()
    finally:
        ctrl.stop("test done")
        win.close()
        _pump(qtapp, 0.3)


# --- resize handling in the controller ----------------------------------------
def test_surface_coalesces_resize_bursts(tmp_path, qtapp):
    """A layout change fires many resize events; only one notification goes out."""
    import time

    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    ctrl = RdpSessionController(Session(protocol="rdp", host="w"), ctx, qtapp)
    # Qt only delivers resize events to a visible widget, so show the page the
    # surface lives in and drive the size through it (as a layout would).
    page = ctrl._page_emb
    page.resize(1000, 700)
    page.show()
    qtapp.processEvents()
    events: list[int] = []
    ctrl._surface.resized.connect(lambda: events.append(1))
    ctrl._surface.set_launch_size((ctrl._surface.width(), ctrl._surface.height()))

    for width in range(1000, 700, -25):  # a 12-frame tween
        page.resize(width, 700)
        qtapp.processEvents()
        time.sleep(0.005)
    assert events == [], "no notification while the size is still moving"

    end = time.monotonic() + 1.0
    while time.monotonic() < end and not events:
        qtapp.processEvents()
        time.sleep(0.005)
    assert len(events) == 1, "exactly one notification once the size settles"


def test_ui_layout_busy_suppresses_refit(tmp_path, qtapp):
    """While the chrome re-lays out, a resize must never touch the session."""
    import time

    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    ctrl = RdpSessionController(Session(protocol="rdp", host="w"), ctx, qtapp)
    ctrl._proc = _FakeProc()
    ctrl.set_state("connected")
    ctrl._launched_size = (640, 480)
    ctrl._surface.resize(1200, 800)

    ctrl.set_ui_layout_busy(True)
    ctrl._on_surface_resized()
    assert ctrl._proc.kills == 0, "a sidebar tween must not kill the client"

    ctrl.set_ui_layout_busy(False)
    ctrl._on_surface_resized()  # still inside the settle window
    assert ctrl._proc.kills == 0

    end = time.monotonic() + 1.0
    while time.monotonic() < end and ctrl._ui_layout_busy:
        qtapp.processEvents()
        time.sleep(0.005)
    assert not ctrl._ui_layout_busy, "resize handling resumes after the settle window"


def test_settled_user_resize_refits_once_and_relaunches(tmp_path, qtapp, monkeypatch):
    """A real resize of the display area re-fits: one kill, one relaunch."""
    import time

    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    launches = _install_fake_client(tmp_path, monkeypatch)
    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    monkeypatch.setattr(rdp_session, "_freerdp_supports_args_from_file", lambda *a, **k: False)
    ctrl = RdpSessionController(
        Session(protocol="rdp", host="w", username="u", password="s"), ctx, qtapp
    )
    monkeypatch.setattr(type(ctrl._surface), "winId", lambda self: 0xABC)
    ctrl._surface.resize(1200, 800)
    ctrl.start()
    for _ in range(100):
        qtapp.processEvents()
        if ctrl._proc is not None and ctrl._proc.state() == ctrl._proc.ProcessState.Running:
            break
    ctrl._mark_connected()
    assert len(launches) == 1
    first = ctrl._proc

    ctrl._surface.resize(800, 600)  # the user made the window smaller
    ctrl._on_surface_resized()
    assert ctrl._refit_requested, "a settled user resize schedules exactly one refit"
    ctrl._on_surface_resized()  # a second resize while the refit is in flight
    assert len(launches) == 1, "no second client is spawned while the first is dying"
    assert ctrl._proc is first

    end = time.monotonic() + 5.0  # the relaunch waits for the old client to exit
    while time.monotonic() < end and ctrl._proc is first:
        qtapp.processEvents()
        time.sleep(0.01)
    assert ctrl._proc is not first, "the client was relaunched for the new size"
    assert len(launches) == 2, "exactly one relaunch for the refit"
    assert "/size:800x600" in launches[-1]
    assert ctrl._launched_size == (800, 600)
    ctrl.stop("test done")
    _pump(qtapp, 0.5)


def test_stop_is_a_clean_close_not_a_crash(tmp_path, qtapp, monkeypatch):
    """The kill we ask for must not surface as "client crashed"/FAILED."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    _install_fake_client(tmp_path, monkeypatch)
    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    ctrl = RdpSessionController(Session(protocol="rdp", host="w", username="u", password="s"), ctx, qtapp)
    monkeypatch.setattr(type(ctrl._surface), "winId", lambda self: 0xABC)
    ctrl._surface.resize(1200, 800)
    ctrl.start()
    for _ in range(100):
        qtapp.processEvents()
        if ctrl._proc is not None and ctrl._proc.state() == ctrl._proc.ProcessState.Running:
            break
    ctrl._mark_connected()
    errors = []
    ctrl.statusInfo.connect(lambda info: errors.append(info.get("error")))

    assert ctrl._proc is not None
    ctrl.stop("closed by user")
    _pump(qtapp, 1.0)
    assert ctrl._proc is None, "the exited client is retired, not left wired up"
    assert ctrl.state() == "closed"
    assert not [e for e in errors if e], f"stop reported errors: {errors}"


class _FakeProc:
    """Minimal QProcess stand-in: records kill() and reports Running."""

    def __init__(self) -> None:
        self.kills = 0

    def state(self):
        from PySide6.QtCore import QProcess

        return QProcess.ProcessState.Running

    def kill(self) -> None:
        self.kills += 1
