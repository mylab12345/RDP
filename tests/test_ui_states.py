"""Round 12 UI contracts: session state surface, header controls & dashboard.

These pin the presentation-layer guarantees of the "clear session states"
pass — none of them touch protocol behaviour:

* every session surfaces connecting / connected / failed / closed on the
  session area itself, with the next step in reach,
* the header carries disconnect, fullscreen, scaling, clipboard and a
  session menu, all keyboard reachable,
* a window with nothing saved explains how to start instead of showing a
  blank dashboard,
* the Sessions panel marks sessions already open in a tab.

Only local shells (real PTY) and RDP sessions that fail immediately are used,
so the suite stays fast and never waits on the network.
"""

from __future__ import annotations

import pytest


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _main_window(qtapp):
    from rdpstudio.app import build_context
    from rdpstudio.ui import theme
    from rdpstudio.ui.main_window import MainWindow

    theme.apply_theme(qtapp, "studio_dark", animations=False)
    ctx = build_context()
    win = MainWindow(ctx)
    win.resize(1280, 800)
    win.show()
    qtapp.processEvents()
    return win, ctx


def _local_session():
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session

    defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/bin/sh"
    return defn


def _rdp_session(session_id: str = ""):
    """An RDP session that fails fast: no client, no reachable port."""
    from rdpstudio.core.models import PROTOCOL_RDP, Session

    return Session(
        name="unreachable",
        protocol=PROTOCOL_RDP,
        host="127.0.0.1",
        port=1,
        username="admin",
        password="secret",
        id=session_id or Session().id,
    )


def _pump(qtapp, rounds: int = 30) -> None:
    for _ in range(rounds):
        qtapp.processEvents()


def _open_local(win, qtapp):
    tab = win.open_session(_local_session())
    assert tab is not None
    for _ in range(80):
        qtapp.processEvents()
    return tab


# ----------------------------------------------------------------------
# Session state surface
# ----------------------------------------------------------------------
@pytest.mark.gui
def test_overlay_shows_every_session_state(qtapp) -> None:  # noqa: ARG001
    """connecting · reconnecting · failed · disconnected · ready — all render."""
    from rdpstudio.ui.session_states import SessionStateOverlay

    overlay = SessionStateOverlay()
    for state, actions in (
        ("connecting", ("cancel",)),
        ("reconnecting", ("cancel",)),
        ("failed", ("retry", "settings", "close")),
        ("closed", ("reconnect", "settings", "close")),
        ("idle", ("connect", "settings", "close")),
    ):
        overlay.show_state(state, detail="detail line", actions=actions)
        assert overlay.state() == state
        for action in actions:
            assert overlay.is_action_visible(action), (state, action)
        # Only the listed actions are visible — no leftovers from an earlier
        # state bleeding into this one.
        for action in ("connect", "retry", "reconnect", "cancel"):
            if action not in actions:
                assert not overlay.is_action_visible(action), (state, action)
        assert overlay._detail.text()  # every state explains itself
    overlay.close()


@pytest.mark.gui
def test_overlay_unknown_state_never_renders_blank(qtapp) -> None:  # noqa: ARG001
    """A future/unknown session state must still show a title and detail."""
    from rdpstudio.ui.session_states import SessionStateOverlay

    overlay = SessionStateOverlay()
    overlay.show_state("some-future-state", detail="", actions=("close",))
    assert overlay._title.text()
    assert overlay._detail.text()
    overlay.close()


@pytest.mark.gui
def test_overlay_actions_emit_their_signals(qtapp) -> None:  # noqa: ARG001
    from rdpstudio.ui.session_states import SessionStateOverlay

    overlay = SessionStateOverlay()
    fired: list[str] = []
    overlay.connectRequested.connect(lambda: fired.append("connect"))
    overlay.retryRequested.connect(lambda: fired.append("retry"))
    overlay.reconnectRequested.connect(lambda: fired.append("reconnect"))
    overlay.settingsRequested.connect(lambda: fired.append("settings"))
    overlay.closeRequested.connect(lambda: fired.append("close"))
    for key in ("connect", "retry", "reconnect", "settings", "close"):
        overlay.trigger_action(key)
    assert fired == ["connect", "retry", "reconnect", "settings", "close"]
    overlay.close()


@pytest.mark.gui
def test_failed_session_offers_retry_and_reports_the_reason(home, qtapp) -> None:  # noqa: ARG001
    """A session that cannot connect says so on the surface, with a way back."""
    win, _ctx = _main_window(qtapp)
    try:
        tab = win.open_session(_rdp_session())
        assert tab is not None
        _pump(qtapp, 40)
        assert tab.controller.state() == "failed"
        assert tab.overlay.state() == "failed"
        assert tab.overlay.is_action_visible("retry")
        assert tab.overlay.is_action_visible("settings")
        assert tab.overlay.is_action_visible("close")
        assert tab.overlay._detail.text(), "the failure reason must be shown"
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_connecting_state_is_shown_before_the_session_is_live(home, qtapp) -> None:  # noqa: ARG001
    """The very first paint is a live state, never a blank surface."""
    win, _ctx = _main_window(qtapp)
    try:
        tab = win.open_session(_rdp_session())
        assert tab is not None
        qtapp.processEvents()
        assert tab.overlay.state() in ("connecting", "failed")
        assert tab.overlay._detail.text()
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_connected_session_hides_the_state_surface(home, qtapp) -> None:  # noqa: ARG001
    """A live local shell shows its terminal — no overlay covering it."""
    win, _ctx = _main_window(qtapp)
    try:
        tab = _open_local(win, qtapp)
        assert tab.controller.state() == "connected"
        assert tab.overlay.state() == ""
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_disconnected_session_offers_reconnect(home, qtapp) -> None:  # noqa: ARG001
    """A session that was live and then stopped explains it, with Reconnect."""
    win, _ctx = _main_window(qtapp)
    try:
        tab = _open_local(win, qtapp)
        tab.controller.stop("test over")
        _pump(qtapp, 40)
        assert tab.overlay.state() == "closed"
        assert tab.overlay.is_action_visible("reconnect")
        assert tab.btn_reconnect.text() == "Reconnect"
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# Session header controls
# ----------------------------------------------------------------------
@pytest.mark.gui
def test_header_carries_disconnect_fullscreen_and_session_menu(home, qtapp) -> None:  # noqa: ARG001
    """The session header exposes status, stop, fullscreen and the ⋯ menu."""
    win, _ctx = _main_window(qtapp)
    try:
        tab = _open_local(win, qtapp)
        tab._populate_session_menu(tab._session_menu)  # what opening the menu does

        # Stop is the state-aware primary action once connected.
        assert tab.btn_reconnect.text() == "Stop"
        assert tab.btn_reconnect.isVisible()

        # Fullscreen control is checkable, explained, and keyboard reachable.
        assert tab.btn_fullscreen.isCheckable()
        assert tab.btn_fullscreen.accessibleName()
        assert "fullscreen" in tab.btn_fullscreen.toolTip().lower()
        assert tab.btn_fullscreen.focusPolicy() != 0

        # The session menu carries the session actions.
        labels = [a.text() for a in tab._session_menu.actions() if a.text()]
        assert "Close tab" in labels
        assert "Session settings…" in labels
        assert "Disconnect" in labels
        assert "Rename tab…" in labels
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_fullscreen_action_is_wired_both_ways(home, qtapp) -> None:  # noqa: ARG001
    """View → Fullscreen, F11 and the header control are one mechanism."""
    win, _ctx = _main_window(qtapp)
    try:
        act = win._act_fullscreen
        assert act.isCheckable()
        assert act.shortcut().toString() == "F11"
        win.set_fullscreen(True)
        qtapp.processEvents()
        assert win.isFullScreen()
        assert act.isChecked()
        win.toggle_fullscreen()
        qtapp.processEvents()
        assert not win.isFullScreen()
        assert not act.isChecked()
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_rdp_clipboard_toggle_updates_the_session_setting(home, qtapp) -> None:  # noqa: ARG001
    """The clipboard control writes the session's own redirection setting."""
    from rdpstudio.core.models import PROTOCOL_RDP, Session

    win, ctx = _main_window(qtapp)
    try:
        defn = Session(
            name="win", protocol=PROTOCOL_RDP, host="127.0.0.1", port=1,
            username="admin", password="x", rdp_clipboard=True,
        )
        ctx.store.upsert(defn)
        tab = win.open_session(ctx.store.get(defn.id))
        assert tab is not None
        _pump(qtapp, 20)
        assert tab.btn_clipboard is not None
        assert tab.btn_clipboard.isChecked()
        tab._toggle_clipboard(False)
        assert tab.controller.definition.rdp_clipboard is False
        assert ctx.store.get(defn.id).rdp_clipboard is False

        # Non-RDP sessions have no clipboard control at all.
        other = _open_local(win, qtapp)
        assert other.btn_clipboard is None
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_rdp_scaling_menu_entries_persist(home, qtapp) -> None:  # noqa: ARG001
    """Fit-to-screen and fullscreen are readable and persistable switches."""
    from rdpstudio.core.models import PROTOCOL_RDP, Session

    win, ctx = _main_window(qtapp)
    try:
        defn = Session(
            name="win", protocol=PROTOCOL_RDP, host="127.0.0.1", port=1,
            username="admin", password="x", rdp_fit_screen=True,
        )
        ctx.store.upsert(defn)
        tab = win.open_session(ctx.store.get(defn.id))
        assert tab is not None
        _pump(qtapp, 20)
        labels = [a.text() for a in tab._session_menu.actions() if a.text()]
        assert "Fit display to screen" in labels
        assert "Fullscreen session display" in labels
        tab._toggle_fit_screen(False)
        assert ctx.store.get(defn.id).rdp_fit_screen is False
        tab._toggle_rdp_fullscreen(True)
        assert ctx.store.get(defn.id).rdp_fullscreen is True
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_header_sheds_labels_before_it_can_clip(home, qtapp) -> None:  # noqa: ARG001
    """Narrow windows keep icon-only actions instead of overflowing text."""
    win, _ctx = _main_window(qtapp)
    try:
        tab = _open_local(win, qtapp)
        win.resize(1400, 800)
        _pump(qtapp, 10)
        assert tab._close_btn.text() == "Close"
        win.resize(560, 620)
        _pump(qtapp, 20)
        assert tab._close_btn.text() == ""
        assert tab._close_btn.toolTip()  # icon-only controls stay explained
        assert tab._close_btn.accessibleName()
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------
@pytest.mark.gui
def test_dashboard_first_run_explains_how_to_start(home, qtapp) -> None:  # noqa: ARG001
    """No saved sessions → concrete next steps, not an empty page."""
    from PySide6.QtWidgets import QLabel, QPushButton

    win, _ctx = _main_window(qtapp)
    try:
        titles = [
            lbl.text()
            for lbl in win._empty.findChildren(QLabel)
            if lbl.objectName() == "dashEmptyTitle"
        ]
        assert titles == ["No saved connections yet"]
        body = " ".join(
            lbl.text() for lbl in win._empty.findChildren(QLabel)
            if lbl.objectName() in ("dashEmptyBody", "dashSection")
        )
        assert "Quick connect" in body
        assert "~/.ssh/config" in body
        buttons = {b.text() for b in win._empty.findChildren(QPushButton)}
        assert "New session" in buttons
        assert "Import ~/.ssh/config" in buttons
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_dashboard_recent_rows_have_an_explicit_connect(home, qtapp) -> None:  # noqa: ARG001
    """Saved sessions get a labelled Connect button, not just a clickable row."""
    from PySide6.QtWidgets import QPushButton

    from rdpstudio.core.models import PROTOCOL_SSH, Session

    win, ctx = _main_window(qtapp)
    try:
        ctx.store.upsert(Session(name="web", protocol=PROTOCOL_SSH, host="10.0.0.5", username="u"))
        win.sidebar.reload()
        win._refresh_dashboard()
        _pump(qtapp, 10)
        row_buttons = [
            b for b in win._empty.findChildren(QPushButton)
            if b.objectName() == "dashRowConnect"
        ]
        assert row_buttons, "each recent row carries its own Connect action"
        assert all(b.accessibleName() for b in row_buttons)
        assert all(b.isEnabled() for b in row_buttons)
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_sidebar_marks_open_sessions(home, qtapp) -> None:  # noqa: ARG001
    """The Sessions panel receives open-session states from the window."""
    from rdpstudio.core.models import PROTOCOL_RDP, Session

    win, ctx = _main_window(qtapp)
    try:
        saved = Session(name="win", protocol=PROTOCOL_RDP, host="127.0.0.1", port=1,
                        username="admin", password="x")
        ctx.store.upsert(saved)
        win.sidebar.reload()
        tab = win.open_session(ctx.store.get(saved.id))
        assert tab is not None
        _pump(qtapp, 40)
        win._sync_sidebar_status()
        assert win.sidebar._open_states.get(saved.id) in (
            "connecting", "connected", "failed", "closed",
        )
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# Regression guards
# ----------------------------------------------------------------------
@pytest.mark.gui
def test_editing_a_session_updates_the_live_tab_without_redial(home, qtapp) -> None:  # noqa: ARG001
    """Editing a saved session touches live tabs only for safe settings."""
    from rdpstudio.core.models import PROTOCOL_RDP, Session

    win, ctx = _main_window(qtapp)
    try:
        defn = Session(
            name="win", protocol=PROTOCOL_RDP, host="127.0.0.1", port=1,
            username="admin", password="x", rdp_clipboard=False,
        )
        ctx.store.upsert(defn)
        tab = win.open_session(ctx.store.get(defn.id))
        assert tab is not None
        _pump(qtapp, 20)
        edited = ctx.store.get(defn.id)
        edited.rdp_clipboard = True
        win._apply_saved_settings_to_tabs(edited)
        assert tab.btn_clipboard.isChecked()
        assert tab.controller.definition.rdp_clipboard is True
    finally:
        win.close()
        qtapp.processEvents()


@pytest.mark.gui
def test_header_keeps_every_action_reachable_after_theme_switch(home, qtapp) -> None:  # noqa: ARG001
    """Re-tinting after a live theme switch must not drop any control."""
    from rdpstudio.ui import theme

    win, _ctx = _main_window(qtapp)
    try:
        tab = win.open_session(_rdp_session())
        assert tab is not None
        _pump(qtapp, 20)
        theme.apply_theme(qtapp, "mobaxterm", animations=False)
        _pump(qtapp, 5)
        for btn in (tab.btn_fullscreen, tab.btn_more, tab._close_btn, tab.btn_reconnect):
            assert not btn.icon().isNull(), "header icons must survive a theme switch"
        assert tab.btn_fullscreen.isCheckable()
        assert tab.overlay.state() in ("connecting", "failed")
    finally:
        win.close()
        qtapp.processEvents()
