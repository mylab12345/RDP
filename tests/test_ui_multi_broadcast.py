"""MultiExec: broadcast input reaches every connected shell tab exactly once."""

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


def _fake_controller(ctx, name: str, shell: bool = True, state: str = "connected"):
    from PySide6.QtWidgets import QWidget

    from rdpstudio.core.models import Session
    from rdpstudio.core.plugin import SessionController, SessionState
    from rdpstudio.protocols.base_caps import capability_set

    class FakeController(SessionController):
        def __init__(self):
            super().__init__(Session(name=name, host=f"{name}.example"), ctx)
            self.writes: list[bytes] = []
            self.set_state(state)

        def start(self) -> None:  # pragma: no cover - tabs are added manually
            pass

        def widget(self):
            return QWidget()

        def capabilities(self):
            return capability_set(shell=shell)

        def write(self, data: bytes) -> None:
            self.writes.append(bytes(data))

    assert SessionState.CONNECTED == "connected"
    return FakeController()


def test_broadcast_sends_to_other_connected_shell_tabs_only(qtapp):
    from rdpstudio.ui.main_window import MainWindow, SessionTab

    ctx = _ctx()
    win = MainWindow(ctx)
    one = _fake_controller(ctx, "one")
    two = _fake_controller(ctx, "two")
    rdp = _fake_controller(ctx, "rdp", shell=False)
    offline = _fake_controller(ctx, "offline", state="closed")
    for controller in (one, two, rdp, offline):
        win.tabs.addTab(SessionTab(controller, win), controller.definition.name)

    win.set_broadcast_input(True)
    assert win._broadcast_input is True
    assert win._act_broadcast.isChecked()
    for i in range(win.tabs.count()):
        assert not win.tabs.widget(i).multi_chip.isHidden()

    win._broadcast_bytes(one, b"uptime\n")
    assert one.writes == []  # the source already received its own input
    assert two.writes == [b"uptime\n"]
    assert rdp.writes == []  # not shell-capable
    assert offline.writes == []  # not connected

    win.set_broadcast_input(False)
    win._broadcast_bytes(one, b"ls\n")
    assert two.writes == [b"uptime\n"]
    assert win._act_broadcast.isChecked() is False
    for i in range(win.tabs.count()):
        assert win.tabs.widget(i).multi_chip.isHidden()
    win.close()
    qtapp.processEvents()


def test_broadcast_ignores_input_when_disabled(qtapp):
    from rdpstudio.ui.main_window import MainWindow, SessionTab

    ctx = _ctx()
    win = MainWindow(ctx)
    one = _fake_controller(ctx, "one")
    two = _fake_controller(ctx, "two")
    win.tabs.addTab(SessionTab(one, win), "one")
    win.tabs.addTab(SessionTab(two, win), "two")

    win._broadcast_bytes(one, b"rm -rf /\n")
    assert two.writes == []
    win.close()
    qtapp.processEvents()


def test_terminal_input_hook_broadcasts_from_open_session(qtapp):
    """The real wiring: typing in one tab reaches the other tab's writer."""
    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    first = win.open_local_terminal()
    second = win.open_local_terminal()
    got: list[bytes] = []
    first.controller.set_state("connected")
    second.controller.set_state("connected")
    second.controller.write = got.append

    win.set_broadcast_input(True)
    first.controller.term.dataWritten.emit(b"echo hi\n")
    assert got == [b"echo hi\n"]
    win.set_broadcast_input(False)
    first.controller.term.dataWritten.emit(b"echo bye\n")
    assert got == [b"echo hi\n"]
    win.close()
    qtapp.processEvents()
