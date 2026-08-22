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
