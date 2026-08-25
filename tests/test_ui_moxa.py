"""MobaXterm-style UI: per-tab command line and main-window wiring."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.usefixtures("home")


def _ctx():
    from rdpstudio.core import paths
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    return SessionContext(
        settings=Settings(),
        store=SessionStore(paths.sessions_file()),
        vault=CredentialVault(paths.vault_file()),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )


# ---------------------------------------------------------------------------
# Per-tab command line (MobaXterm-style bottom command box)
# ---------------------------------------------------------------------------
def _key(widget, key, mods=None):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods or Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev)
    return ev


def test_command_bar_send_and_history(qtapp):
    from PySide6.QtCore import Qt

    from rdpstudio.ui.main_window import CommandBar

    bar = CommandBar()
    sent = []
    bar.commandSent.connect(sent.append)

    bar.line.setText("echo hello")
    bar._on_return()
    assert sent == ["echo hello"]
    assert bar.line.text() == ""

    bar.line.setText("ls -la")
    bar._on_return()
    assert sent == ["echo hello", "ls -la"]

    # Up: newest → older; Down: back to draft (empty)
    _key(bar.line, Qt.Key.Key_Up)
    assert bar.line.text() == "ls -la"
    _key(bar.line, Qt.Key.Key_Up)
    assert bar.line.text() == "echo hello"
    _key(bar.line, Qt.Key.Key_Down)
    assert bar.line.text() == "ls -la"
    _key(bar.line, Qt.Key.Key_Down)
    assert bar.line.text() == ""

    # duplicate consecutive commands are not re-added
    bar.line.setText("du -sh /")
    bar._on_return()
    bar.line.setText("du -sh /")
    bar._on_return()
    assert bar.history == ["echo hello", "ls -la", "du -sh /"]
    bar.deleteLater()


def test_session_tab_has_command_bar_for_shell_sessions(qtapp):
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/bin/sh"
    tab = win.open_session(defn)
    assert tab is not None
    assert tab.command_bar is not None
    # the command bar lives below the terminal in the tab layout
    layout = tab.layout()
    assert layout.itemAt(3).widget() is tab.command_bar
    win.close()
    qtapp.processEvents()


def test_command_bar_executes_in_terminal(qtapp):
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/bin/sh"
    tab = win.open_session(defn)
    controller = tab.controller
    # wait for the shell
    deadline = time.time() + 5
    while time.time() < deadline and controller.state() != "connected":
        qtapp.processEvents()
        time.sleep(0.02)

    tab.command_bar.line.setText("echo MOXA-CMD-$((2+3))")
    tab.command_bar._on_return()

    deadline = time.time() + 10
    seen = ""
    while time.time() < deadline:
        qtapp.processEvents()
        seen = "\n".join(
            controller.term.core.line_at(i)
            for i in range(controller.term.core.total_lines())
        )
        if "MOXA-CMD-5" in seen:
            break
        time.sleep(0.05)
    assert "MOXA-CMD-5" in seen, f"command bar did not run the command:\n{seen}"
    win.close()
    qtapp.processEvents()


# ---------------------------------------------------------------------------
# Main-window wiring
# ---------------------------------------------------------------------------
def test_menu_layout_is_moxa_style(qtapp):
    from PySide6.QtWidgets import QMenu

    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    top = []
    for action in win.menuBar().actions():
        menu = action.menu()
        if menu is not None and isinstance(menu, QMenu):
            top.append(action.text().replace("&", ""))
    assert top[:3] == ["File", "View", "Tools"], top
    assert "Tabs" in top and "Session" in top and "Help" in top
    win.close()
    qtapp.processEvents()
