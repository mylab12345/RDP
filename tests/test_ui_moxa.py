"""MobaXterm-style UI: shell-tab layout and main-window wiring."""

from __future__ import annotations

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
# The per-tab command line was removed (typing happens in the terminal).
# ---------------------------------------------------------------------------
def test_shell_tab_has_no_command_bar(qtapp):
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/bin/sh"
    tab = win.open_session(defn)
    assert tab is not None
    assert not hasattr(tab, "command_bar")
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
