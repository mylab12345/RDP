"""Local-terminal button, simplified session UI and remote monitoring."""

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


# --- one-click local terminal -------------------------------------------------
def test_open_local_terminal_runs_a_real_shell(qtapp):
    import time

    from rdpstudio.core.plugin import SessionState
    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    tab = win.open_local_terminal()

    assert tab is not None
    assert tab.controller.state() == SessionState.CONNECTED
    assert win.tabs.count() == 1
    # a scratch terminal must not be persisted as a saved session
    assert ctx.store.sessions() == []

    controller = tab.controller
    controller.term.write_user(b"echo RDPSTUDIO-OK-$((6*7))\n")
    deadline = time.time() + 10
    seen = ""
    while time.time() < deadline:
        qtapp.processEvents()
        seen = "\n".join(
            controller.term.core.line_at(i)
            for i in range(controller.term.core.total_lines())
        )
        if "RDPSTUDIO-OK-42" in seen:
            break
        time.sleep(0.05)
    assert "RDPSTUDIO-OK-42" in seen, f"shell produced no output:\n{seen}"

    controller.stop("test over")
    qtapp.processEvents()
    # teardown must release the child process and the PTY fd
    assert controller._proc is None
    assert controller._master is None
    win.close()


def test_local_terminal_reports_a_bad_command(qtapp):
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.core.plugin import SessionState
    from rdpstudio.protocols.local.session import LocalShellController

    ctx = _ctx()
    defn = Session(protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/nonexistent/shell-binary"
    controller = LocalShellController(defn, ctx)

    states: list[str] = []
    errors: list[str] = []
    controller.stateChanged.connect(states.append)
    controller.statusInfo.connect(lambda info: errors.append(str(info.get("error", ""))))

    controller.start()
    qtapp.processEvents()

    # must surface the failure instead of showing a dead "connected" tab
    assert SessionState.FAILED in states
    assert SessionState.CONNECTED not in states
    assert any("No such file" in e for e in errors), errors


# --- simplified session dialog -------------------------------------------------
def test_session_dialog_hides_advanced_options_by_default(qtapp):
    from rdpstudio.core.models import Session
    from rdpstudio.ui.session_dialog import SessionDialog

    dlg = SessionDialog(_ctx(), Session(protocol="ssh"))
    dlg.show()
    qtapp.processEvents()

    # the simple view is host/user/password only
    assert dlg.host.isVisible()
    assert dlg.username.isVisible()
    assert dlg.password.isVisible()
    assert not dlg.port.isVisible()
    assert not dlg.tags.isVisible()

    dlg.btn_advanced.setChecked(True)
    qtapp.processEvents()
    assert dlg.port.isVisible()
    assert dlg.tags.isVisible()
    dlg.close()


def test_rdp_display_presets_round_trip(qtapp):
    from rdpstudio.core.models import Session
    from rdpstudio.ui.session_dialog import SessionDialog, _display_mode_of

    ctx = _ctx()
    dlg = SessionDialog(ctx, Session(protocol="rdp", host="w", username="u"))
    dlg.show()
    qtapp.processEvents()

    dlg.rdp_display_mode.setCurrentIndex(dlg.rdp_display_mode.findData("1920x1080"))
    dlg._on_save()
    saved = ctx.store.sessions()[-1]
    assert (saved.rdp_width, saved.rdp_height) == (1920, 1080)
    assert _display_mode_of(saved) == "1920x1080"

    saved.rdp_fit_screen = True
    assert _display_mode_of(saved) == "fit"
    saved.rdp_fit_screen = False
    saved.rdp_fullscreen = True
    assert _display_mode_of(saved) == "fullscreen"


# --- terminal Tab completion ----------------------------------------------------
def test_tab_reaches_shell_not_focus_traversal(qtapp):
    """Pressing Tab inside the app must send \\t to the shell (autocomplete),
    not jump focus to the next widget (Qt steals Tab for focus traversal)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    win.show()
    qtapp.processEvents()
    tab = win.open_local_terminal()
    qtapp.processEvents()

    term = tab.controller.term
    written: list[bytes] = []
    term.dataWritten.connect(written.append)
    term.setFocus()
    qtapp.processEvents()
    assert term.hasFocus()

    QTest.keyClick(term, Qt.Key.Key_Tab)
    qtapp.processEvents()

    assert written == [b"\t"], f"Tab was swallowed by focus traversal: {written}"
    # focus must stay on the terminal, not jump to the toolbar quick-connect box
    assert term.hasFocus()

    tab.controller.stop("test over")
    win.close()


def test_tab_completes_command_in_real_shell(qtapp):
    """End-to-end: `ec<Tab>` expands to `echo` in the local shell."""
    import time

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    win.show()
    qtapp.processEvents()
    tab = win.open_local_terminal()
    deadline = time.time() + 10
    while time.time() < deadline:  # wait for the prompt to be live
        qtapp.processEvents()
        text = "\n".join(
            tab.controller.term.core.line_at(i)
            for i in range(tab.controller.term.core.total_lines())
        )
        if "$" in text or "#" in text:
            break
        time.sleep(0.05)

    term = tab.controller.term
    term.setFocus()
    qtapp.processEvents()
    QTest.keyClick(term, Qt.Key.Key_E)
    QTest.keyClick(term, Qt.Key.Key_C)
    qtapp.processEvents()
    QTest.keyClick(term, Qt.Key.Key_Tab)

    deadline = time.time() + 10
    seen = ""
    while time.time() < deadline:
        qtapp.processEvents()
        seen = "\n".join(
            term.core.line_at(i) for i in range(term.core.total_lines())
        )
        if "echo" in seen:
            break
        time.sleep(0.05)
    assert "echo" in seen, f"Tab did not complete the command:\n{seen}"

    tab.controller.stop("test over")
    win.close()


# --- terminal Ctrl+wheel font zoom ----------------------------------------------
def test_ctrl_wheel_zooms_terminal_font(qtapp):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent

    from rdpstudio.ui.terminal import TerminalView

    term = TerminalView(_ctx().settings)
    term.show()
    qtapp.processEvents()
    base = term._font_size

    def wheel(dy: int, ctrl: bool) -> None:
        mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
        ev = QWheelEvent(
            QPointF(50, 50), QPointF(50, 50), QPoint(0, 0), QPoint(0, dy),
            Qt.MouseButton.NoButton, mods, Qt.ScrollPhase.NoScrollPhase, False,
        )
        term.wheelEvent(ev)

    wheel(120, ctrl=True)
    assert term._font_size == base + 1
    assert term.font().pointSize() == base + 1
    wheel(-120, ctrl=True)
    assert term._font_size == base
    # plain wheel (no Ctrl) must NOT change the font size
    wheel(120, ctrl=False)
    assert term._font_size == base
    term.close()


# --- remote monitoring ----------------------------------------------------------
def test_monitor_parses_a_realistic_probe():
    from rdpstudio.protocols.ssh.monitor import parse_probe

    first = (
        "###uptime\n90061.5 100.0\n"
        "###loadavg\n0.50 0.40 0.30 1/200 1234\n"
        "###stat\ncpu 100 0 100 800 0 0 0 0 0 0\n"
        "###meminfo\nMemTotal: 8000000 kB\nMemAvailable: 2000000 kB\n"
        "SwapTotal: 1000000 kB\nSwapFree: 750000 kB\n"
        "###netdev\nlo: 5 0 0 0 0 0 0 0 5 0\neth0: 1000 0 0 0 0 0 0 0 500 0\n"
        "###df\n/dev/sda1 100000 25000 75000 25% /\n"
        "###who\n3\n"
        "###end\n"
    )
    sample, prev = parse_probe(first)
    assert sample.cpu_percent is None  # needs two readings
    assert sample.mem_percent == pytest.approx(75.0)
    assert sample.disk_percent == pytest.approx(25.0)
    assert sample.swap_percent == pytest.approx(25.0)
    assert sample.users == 3
    assert sample.load1 == pytest.approx(0.5)

    # second reading: 200 more jiffies, 100 of them idle ⇒ 50% busy
    second = first.replace(
        "cpu 100 0 100 800 0 0 0 0 0 0", "cpu 150 0 150 900 0 0 0 0 0 0"
    ).replace("eth0: 1000 0 0 0 0 0 0 0 500 0", "eth0: 3000 0 0 0 0 0 0 0 1500 0")
    sample2, _ = parse_probe(second, prev)
    assert sample2.cpu_percent == pytest.approx(50.0)
    # loopback excluded, deltas clamped at >= 0
    assert sample2.rx_rate == 2000
    assert sample2.tx_rate == 1000


def test_monitor_capability_and_uptime_format():
    from rdpstudio.core.plugin import registry
    from rdpstudio.ui.monitor_dialog import format_uptime

    ssh = registry().require("ssh")
    from rdpstudio.core.models import Session

    controller = ssh.create_session(Session(protocol="ssh", host="h"), _ctx())
    assert controller.capabilities().monitor is True
    # local shells have no remote host to monitor
    local = registry().require("local")
    assert local.create_session(Session(protocol="local"), _ctx()).capabilities().monitor is False

    assert format_uptime(90061) == "1d 1h"
    assert format_uptime(3700) == "1h 1m"
    assert format_uptime(120) == "2m"
