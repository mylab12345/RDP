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
