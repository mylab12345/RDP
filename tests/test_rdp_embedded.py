"""Built-in (embedded) RDP display: support detection, args, mode selection."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.usefixtures("home")

# The stand-in FreeRDP client used below is a POSIX shell script, so the tests
# that actually spawn it are POSIX-only (the same convention as
# tests/test_rdp_xwayland.py).
posix_shell_client = pytest.mark.skipif(
    sys.platform == "win32", reason="the stand-in FreeRDP client is a POSIX shell script"
)


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
    # in-tab desktops follow the tab size: dynamic resolution, never the
    # (mutually exclusive) client-side bitmap scaling
    assert "/dynamic-resolution" in args
    assert "/smart-sizing" not in args
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
def _install_fake_fitter(monkeypatch, available: bool = True) -> list[tuple[int, int, int]]:
    """Stand-in for the X11 child-window fit (no X server under offscreen Qt).

    Records every ``(xid, width, height)`` request.  ``available=False``
    mimics a host without libX11 / DISPLAY, where the fit reports failure and
    the controller must fall back to the relaunch-based refit.
    """
    from rdpstudio.protocols.rdp import session as rdp_session

    fits: list[tuple[int, int, int]] = []

    def fake_fit(xid: int, w: int, h: int) -> bool:
        fits.append((int(xid), int(w), int(h)))
        return available

    monkeypatch.setattr(rdp_session, "fit_child_windows", fake_fit)
    original_init = rdp_session._EmbeddedSurface.__init__

    def patched_init(self, *a, **k):
        original_init(self, *a, **k)
        self._fitter = fake_fit

    monkeypatch.setattr(rdp_session._EmbeddedSurface, "__init__", patched_init)
    return fits


def _install_fake_client(tmp_path, monkeypatch, fit_available: bool = True) -> list[list[str]]:
    """A stand-in xfreerdp that records every launch and stays alive.

    Returns the list of recorded argument lists (one per launch).  The X11
    child fit is faked too (see :func:`_install_fake_fitter`); the recorded
    fit requests are available as ``launches.fits``.
    """
    from rdpstudio.protocols.rdp import session as rdp_session

    fits = _install_fake_fitter(monkeypatch, available=fit_available)
    script = tmp_path / "fake-freerdp.sh"
    script.write_text("#!/bin/sh\nwhile true; do sleep 0.05; done\n")
    script.chmod(0o755)
    monkeypatch.setattr(rdp_session, "find_rdp_client", lambda: (str(script), "freerdp"))
    monkeypatch.setattr(rdp_session, "find_embedded_client", lambda: str(script))
    monkeypatch.setattr(rdp_session, "embedded_support", lambda *a, **k: (True, ""))

    class _Launches(list):
        fits: list[tuple[int, int, int]]

    launches = _Launches()
    launches.fits = fits
    original = rdp_session.RdpSessionController._launch_client

    def counting(self, path, args, direct_argv=None):
        launches.append(list(args or direct_argv or []))
        return original(self, path, args, direct_argv)

    monkeypatch.setattr(rdp_session.RdpSessionController, "_launch_client", counting)
    return launches


def _open_connected_rdp_tab(tmp_path, monkeypatch, qtapp, fit_available: bool = True):
    """MainWindow with one embedded RDP tab whose handshake has completed."""
    import time

    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import Session
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.ui.main_window import MainWindow
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    launches = _install_fake_client(tmp_path, monkeypatch, fit_available=fit_available)
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
    # Password included: open_session() must not open the (modal, blocking)
    # credential prompt for a session that already has full credentials.
    ctx.store.upsert(Session(protocol="rdp", host="win-server", port=3389,
                             username="u", password="p"))
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


@posix_shell_client
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


@posix_shell_client
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


@posix_shell_client
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


@posix_shell_client
def test_settled_user_resize_refits_once_and_relaunches(tmp_path, qtapp, monkeypatch):
    """Fallback without X11 live fit: a real resize re-fits by relaunching —
    one kill, one relaunch — so the desktop still ends up filling the tab."""
    import time

    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import session as rdp_session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    launches = _install_fake_client(tmp_path, monkeypatch, fit_available=False)
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


@posix_shell_client
def test_settled_user_resize_follows_tab_without_relaunch(tmp_path, qtapp, monkeypatch):
    """With X11 live fit the desktop follows the tab: the FreeRDP child window
    is resized in place (dynamic resolution does the rest) — no relaunch."""
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
    assert "/dynamic-resolution" in launches[0]
    first = ctrl._proc

    ctrl._surface.resize(800, 600)
    ctrl._on_surface_resized()
    assert not ctrl._refit_requested, "no relaunch when the child window can be resized"
    assert ctrl._proc is first and first.state() == first.ProcessState.Running
    assert launches.fits[-1] == (0xABC, 800, 600), "the child window was fitted to the tab"
    assert ctrl._launched_size == (800, 600)
    _pump(qtapp, 0.3)
    assert len(launches) == 1
    ctrl.stop("test done")
    _pump(qtapp, 0.5)


@posix_shell_client
def test_sidebar_toggle_keeps_desktop_flush_with_tab(tmp_path, qtapp, monkeypatch):
    """Regression: hiding the sidebar left a black gap next to the desktop and
    showing it again clipped the desktop — the FreeRDP child X window kept its
    old size.  It must be resized to the surface during and after the tween."""
    win, tab, ctrl, launches = _open_connected_rdp_tab(tmp_path, monkeypatch, qtapp)
    try:
        surface = ctrl._surface
        xid = int(surface.winId())
        start = (surface.width(), surface.height())

        n0 = len(launches.fits)
        win._toggle_sidebar(False)  # hide → the tab grows
        _pump(qtapp, 1.0)
        grown = (surface.width(), surface.height())
        assert grown[0] > start[0], "hiding the sidebar widened the tab"
        assert len(launches.fits) > n0, "the child window was fitted during/after the tween"
        assert launches.fits[-1] == (xid, *grown), "final fit == the settled tab size (no gap)"
        assert surface.fitted_size() == grown
        assert ctrl._launched_size == ctrl._detected_size(), "settled size is the new reference"
        assert not ctrl._ui_layout_busy

        n1 = len(launches.fits)
        win._toggle_sidebar(True)  # show → the tab shrinks back
        _pump(qtapp, 1.0)
        shrunk = (surface.width(), surface.height())
        assert shrunk[0] < grown[0]
        assert len(launches.fits) > n1
        assert launches.fits[-1] == (xid, *shrunk), "desktop shrank with the tab (no clipping)"
        assert ctrl._launched_size == ctrl._detected_size()

        # all of it without disturbing the session
        assert len(launches) == 1
        assert ctrl.state() == "connected"
        assert ctrl._proc.state() == ctrl._proc.ProcessState.Running
    finally:
        ctrl.stop("test done")
        win.close()
        _pump(qtapp, 0.3)


def test_surface_live_fit_only_while_embedded(qtapp, monkeypatch, tmp_path):
    """The X fit runs only while a client is embedded and never for a 0-size
    widget; each resize burst is coalesced into one request per frame."""
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.session import RdpSessionController

    fits = _install_fake_fitter(monkeypatch)
    ctx = _ctx(tmp_path)
    ctx.settings.rdp_client = "embedded"
    ctrl = RdpSessionController(Session(protocol="rdp", host="w"), ctx, qtapp)
    surface = ctrl._surface
    page = ctrl._page_emb
    page.resize(1000, 700)
    page.show()
    qtapp.processEvents()

    assert surface.fit_child() is False and fits == [], "idle surface: nothing to fit"

    surface.live_fit_enabled = True
    for width in range(1000, 700, -25):  # a 12-frame tween
        page.resize(width, 700)
        qtapp.processEvents()
    _pump(qtapp, 0.1)
    assert fits, "the child was fitted"
    assert len(fits) < 12, "per-frame coalescing: fewer requests than resize events"
    assert fits[-1][1:] == (surface.width(), surface.height())

    surface.live_fit_enabled = False
    n = len(fits)
    page.resize(900, 700)
    _pump(qtapp, 0.1)
    assert len(fits) == n, "no fit once the client is gone"


def test_fit_child_windows_without_x11_is_a_noop(monkeypatch):
    """No DISPLAY (Windows, headless): the helper reports False, never raises."""
    from rdpstudio.protocols.rdp import x11

    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(x11, "_display", None)
    monkeypatch.setattr(x11, "_display_failed", False)
    assert x11.fit_child_windows(0x123, 800, 600) is False
    assert x11.fit_child_windows(0, 800, 600) is False
    assert x11.fit_child_windows(0x123, 0, 600) is False


@posix_shell_client
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
