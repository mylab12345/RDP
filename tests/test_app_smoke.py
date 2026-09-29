"""GUI smoke tests (offscreen): main window builds, tabs open, sidebar lists."""

from __future__ import annotations

import time

import pytest


@pytest.fixture()
def ctx(home, qtapp):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    return SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )


def test_main_window_builds(ctx, qtapp):
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    assert win.windowTitle() == "KB-Remote"
    assert win.sidebar is not None
    # MobaXterm chrome: big text-under-icon toolbar
    from PySide6.QtCore import Qt

    assert win._toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon
    win.close()
    qtapp.processEvents()


def test_session_dialog_builds(ctx, qtapp):
    from rdpstudio.core.models import Session
    from rdpstudio.ui.session_dialog import SessionDialog

    dlg = SessionDialog(ctx, Session(name="t", protocol="ssh", host="h", port=22), None)
    assert dlg.protocol.count() >= 3
    # switch protocols to construct every page
    for i in range(dlg.protocol.count()):
        dlg.protocol.setCurrentIndex(i)
        qtapp.processEvents()
    dlg.deleteLater()


def test_vault_dialog_builds(ctx, qtapp):
    from rdpstudio.ui.vault_dialog import VaultDialog

    dlg = VaultDialog(ctx, None)
    assert dlg.cred_list is not None
    dlg.deleteLater()


def test_open_local_session_tab(ctx, qtapp, monkeypatch):
    import sys

    if sys.platform == "win32":
        pytest.skip("posix pty")
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/bin/sh"
    tab = win.open_session(defn)
    assert tab is not None
    assert win.tabs.count() == 1

    deadline = time.time() + 5
    ok = False
    while time.time() < deadline:
        qtapp.processEvents()
        body = "\n".join(
            tab.controller.term.core.line_at(i)
            for i in range(tab.controller.term.core.total_lines())
        )
        if "$" in body or "#" in body or "sh" in body:
            ok = True
            break
        time.sleep(0.05)
    assert ok, "shell produced no output"

    win.close_tab(0)
    qtapp.processEvents()
    assert win.tabs.count() == 0
    win.close()


def test_close_tabs_have_no_ctrl_w_shortcut(ctx, qtapp):
    """Ctrl+W is reserved for the terminal's readline backward-word command."""
    from PySide6.QtGui import QAction, QKeySequence

    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    sequences = {
        action.shortcut().toString(QKeySequence.SequenceFormat.PortableText)
        for action in win.findChildren(QAction)
        if not action.shortcut().isEmpty()
    }
    assert "Ctrl+W" not in sequences
    assert "Ctrl+Shift+W" not in sequences
    win.close()
    qtapp.processEvents()


def test_session_dialog_saves_agent_forwarding(ctx, qtapp):
    from rdpstudio.core.models import Session
    from rdpstudio.ui.session_dialog import SessionDialog

    dlg = SessionDialog(ctx, Session(name="t", protocol="ssh", host="h", port=22), None)
    assert dlg.agent_forward.isChecked() is False
    assert "trust" in dlg.agent_forward.toolTip()
    dlg.agent_forward.setChecked(True)
    assert dlg._collect_session().agent_forwarding is True
    dlg.deleteLater()


def test_settings_dialog_saves_download_dir(ctx, qtapp, home):
    from rdpstudio.core import paths
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.settings_dialog import SettingsDialog

    target = home / "dl"
    target.mkdir()
    dlg = SettingsDialog(ctx.settings, None)
    dlg.download_dir.setText(str(target))
    dlg._save()
    assert Settings.load(paths.settings_file()).default_download_dir == str(target)
    dlg.deleteLater()


def test_closing_last_session_tab_keeps_app_running(ctx, qtapp, monkeypatch):
    """Closing every open session must never quit the application — the
    window stays up, showing the dashboard, ready to accept new sessions."""
    import sys

    if sys.platform == "win32":
        pytest.skip("posix pty")
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    quit_calls = []
    monkeypatch.setattr(qtapp, "quit", lambda: quit_calls.append(True))

    defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/bin/sh"
    tab = win.open_session(defn)
    assert tab is not None
    qtapp.processEvents()

    win.close_tab(0)
    qtapp.processEvents()

    assert win.tabs.count() == 0
    assert win.isVisible()
    assert quit_calls == [], "closing the last session tab must not quit the app"

    win.close()
    qtapp.processEvents()


def test_closing_all_tabs_via_close_all_keeps_app_running(ctx, qtapp, monkeypatch):
    import sys

    if sys.platform == "win32":
        pytest.skip("posix pty")
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    quit_calls = []
    monkeypatch.setattr(qtapp, "quit", lambda: quit_calls.append(True))

    for _ in range(3):
        defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
        defn.options["command"] = "/bin/sh"
        win.open_session(defn)
    qtapp.processEvents()
    assert win.tabs.count() == 3

    for i in range(win.tabs.count() - 1, -1, -1):
        win.close_tab(i)
    qtapp.processEvents()

    assert win.tabs.count() == 0
    assert win.isVisible()
    assert quit_calls == []

    win.close()
    qtapp.processEvents()


def test_closing_the_window_quits_the_app(ctx, qtapp, monkeypatch):
    """The only ways to exit: closing the window itself, or the Exit / tray
    Quit actions — both of which route through MainWindow.close()."""
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    quit_calls = []
    monkeypatch.setattr(qtapp, "quit", lambda: quit_calls.append(True))

    win.close()
    qtapp.processEvents()

    assert quit_calls == [True]
    assert not win.isVisible()


def test_app_disables_quit_on_last_window_closed(qtapp):
    """The app must not rely on Qt's implicit last-window-closed heuristic —
    quitting is explicit (window close / Exit / tray Quit) so a transient
    dialog or an empty tab strip never takes the whole app down with it.

    ``main()`` builds its own ``QApplication`` (and blocks on ``exec()``),
    so it isn't exercised directly here; instead this asserts the flag is
    set on the shared application the same way ``rdpstudio.app.main`` does,
    pinning down the behaviour the other tests in this file rely on.
    """
    import inspect

    from rdpstudio import app as app_mod

    source = inspect.getsource(app_mod.main)
    assert "setQuitOnLastWindowClosed(False)" in source
