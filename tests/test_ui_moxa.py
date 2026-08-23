"""MobaXterm-style UI: bottom remote-monitor panel + per-tab command line."""

from __future__ import annotations

import time
from types import SimpleNamespace

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
# Bottom remote-monitor panel
# ---------------------------------------------------------------------------
def test_monitor_panel_initial_no_session(qtapp):
    from rdpstudio.ui.monitor_panel import MonitorPanel

    panel = MonitorPanel()
    panel.show()
    qtapp.processEvents()
    assert panel._engine is None
    assert "no active SSH session" in panel.status.text()
    assert not panel.collapsed
    # collapsed -> header only
    panel.set_collapsed(True)
    qtapp.processEvents()
    assert panel.collapsed
    panel.set_collapsed(False)
    qtapp.processEvents()
    assert not panel.collapsed
    panel.shutdown()
    panel.deleteLater()


def test_monitor_panel_bind_unsupported_controller(qtapp):
    from rdpstudio.ui.monitor_panel import MonitorPanel

    class NoProvider:
        definition = SimpleNamespace(display_name=lambda: "fake")

    panel = MonitorPanel()
    panel.show()
    panel.bind(NoProvider())  # no transport_provider attribute
    qtapp.processEvents()
    assert panel._engine is None
    assert "no active SSH session" in panel.status.text()

    panel.bind(None)
    qtapp.processEvents()
    assert panel._engine is None
    panel.shutdown()
    panel.deleteLater()


def test_monitor_panel_renders_sample(qtapp):
    from rdpstudio.ui.monitor_panel import MonitorPanel

    panel = MonitorPanel()
    panel.show()
    panel._on_sample(
        {
            "uptime_seconds": 90_000,
            "load1": 0.52,
            "load5": 0.41,
            "load15": 0.30,
            "cpu_percent": 42.0,
            "cpu_cores": 4,
            "mem_total_kb": 8_000_000,
            "mem_available_kb": 4_000_000,
            "mem_percent": 50.0,
            "swap_percent": 0.0,
            "disk_total_kb": 100_000_000,
            "disk_used_kb": 50_000_000,
            "disk_percent": 50.0,
            "rx_rate": 1024.0,
            "tx_rate": 512.0,
            "users": 2,
        }
    )
    qtapp.processEvents()
    assert "42%" in panel.cpu.value.text()
    assert "50%" in panel.mem.value.text()
    assert "50%" in panel.disk.value.text()
    assert "Uptime 1d" in panel.lbl_uptime.text()
    assert "Load 0.52" in panel.lbl_load.text()
    assert "Users 2" in panel.lbl_users.text()
    assert panel.status.text() == "live"
    panel.shutdown()
    panel.deleteLater()


class _FakeProbeChannel:
    def __init__(self, text: str) -> None:
        self._data = text.encode()

    def settimeout(self, _t):
        pass

    def exec_command(self, _cmd):
        pass

    def recv(self, n: int) -> bytes:
        if self._data:
            chunk, self._data = self._data[:n], self._data[n:]
            return chunk
        return b""

    def close(self):
        pass


class _FakeTransport:
    def __init__(self, texts) -> None:
        self._texts = list(texts)
        self.active = True

    def is_active(self) -> bool:
        return self.active

    def open_session(self, timeout=None):
        text = self._texts.pop(0) if len(self._texts) > 1 else self._texts[-1]
        return _FakeProbeChannel(text)


class _FakeController:
    def __init__(self, transport) -> None:
        self._transport = transport
        self.definition = SimpleNamespace(display_name=lambda: "fakehost")

    def capabilities(self):
        return SimpleNamespace(shell=True, sftp=True, tunnels=True, monitor=True)

    def transport_provider(self):
        return lambda: self._transport


def _probe_text(rx: int, tx: int, cpu_jiffies: int) -> str:
    return (
        "###uptime\n123456.7 654321.0\n"
        "###loadavg\n0.10 0.20 0.30\n"
        f"###stat\ncpu  1000 0 500 {cpu_jiffies} 0 0 0 0 0 0\n"
        "###meminfo\n"
        "MemTotal:       8000000 kB\n"
        "MemAvailable:   4000000 kB\n"
        "MemFree:        3000000 kB\n"
        "SwapTotal:      2000000 kB\n"
        "SwapFree:       2000000 kB\n"
        "###netdev\n"
        "Inter-|   Receive packets  |  Transmit packets  \n"
        "    lo: 100 0 0 0 0 0 0 0 100 0 0 0 0 0 0 0 0\n"
        f"  eth0: {rx} 0 0 0 0 0 0 0 {tx} 0 0 0 0 0 0 0 0\n"
        "###df\n"
        "/dev/sda1 100000000 50000000 50000000 50% /\n"
        "###who\n2\n"
        "###end\n"
    )


def test_monitor_panel_live_engine_over_fake_transport(qtapp):
    """End-to-end: MonitorEngine thread → probe → parse → panel widgets."""
    from rdpstudio.ui.monitor_panel import MonitorPanel

    transport = _FakeTransport(
        [
            _probe_text(rx=1000, tx=100, cpu_jiffies=5000),
            _probe_text(rx=2000, tx=200, cpu_jiffies=10000),
        ]
    )
    panel = MonitorPanel()
    panel.show()
    panel.bind(_FakeController(transport))

    deadline = time.time() + 8
    live = False
    while time.time() < deadline:
        qtapp.processEvents()
        if panel.status.text() == "live":
            live = True
            break
        time.sleep(0.05)
    assert live, f"panel never went live: {panel.status.text()!r}"
    assert "Uptime 1d" in panel.lbl_uptime.text()
    assert "Users 2" in panel.lbl_users.text()
    assert "50%" in panel.mem.value.text()

    # wait for a second sample: CPU is a delta between /proc/stat readings
    deadline = time.time() + 8
    cpu = ""
    while time.time() < deadline:
        qtapp.processEvents()
        cpu = panel.cpu.value.text()
        if cpu and cpu != "measuring…" and "%" in cpu:
            break
        time.sleep(0.05)
    assert "%" in cpu, f"no CPU delta sample: {cpu!r}"

    # pause stops updates, resume re-enables them
    panel.toggle_pause()
    qtapp.processEvents()
    assert "▶ Resume" in panel.btn_pause.text()
    assert panel.status.text() == "paused"
    panel.toggle_pause()
    qtapp.processEvents()
    assert "⏸ Pause" in panel.btn_pause.text()

    panel.shutdown()
    panel.deleteLater()


def test_monitor_panel_tear_down_is_prompt(qtapp):
    """Rebinding must not leave the previous engine thread running."""
    from rdpstudio.ui.monitor_panel import MonitorPanel

    transport = _FakeTransport([_probe_text(1, 1, 5000)])
    panel = MonitorPanel()
    panel.show()
    panel.bind(_FakeController(transport))
    qtapp.processEvents()
    assert panel._engine is not None
    panel.bind(None)
    qtapp.processEvents()
    assert panel._engine is None
    assert panel._thread is None
    panel.shutdown()
    panel.deleteLater()


# ---------------------------------------------------------------------------
# Per-tab command line (MobaXterm-style bottom command box)
# ---------------------------------------------------------------------------
def _key(widget, key, mods=None):
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent

    ev = QKeyEvent(QEvent.Type.KeyPress, key, mods or Qt.KeyboardModifier.NoModifier)
    widget.keyPressEvent(ev)
    return ev


def test_monitor_panel_live_over_real_ssh(qtapp, sshd, home):
    """Full flow: real SSH session -> panel attaches, auto-expands, renders live stats."""
    from rdpstudio.app import build_context
    from rdpstudio.core.models import PROTOCOL_SSH, Session
    from rdpstudio.ui.main_window import MainWindow
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx = build_context(home_override=str(home))
    ctx.prompter = HeadlessPromptProvider(accept_host_keys=True)
    win = MainWindow(ctx)
    win.show()

    defn = Session(
        name="e2e", protocol=PROTOCOL_SSH, host=sshd["host"], port=sshd["port"],
        username=sshd["user"], auth="key", key_path=sshd["key"],
    )
    tab = win.open_session(defn)

    deadline = time.time() + 20
    while time.time() < deadline and "connected" not in tab.chip.text().lower():
        qtapp.processEvents()
        time.sleep(0.05)
    assert "connected" in tab.chip.text().lower(), tab.chip.text()

    # auto-expansion on connect
    time.sleep(0.2)
    qtapp.processEvents()
    mp = win.monitor_panel
    assert not mp._collapsed, "panel should auto-expand for the first live session"
    assert mp._engine is not None
    assert mp.host_label.text()

    # fastest available interval so the first sample arrives quickly
    mp.interval.setCurrentText("Every 2 seconds")

    deadline = time.time() + 20
    while time.time() < deadline and mp.status.text() != "live":
        qtapp.processEvents()
        time.sleep(0.05)
    assert mp.status.text() == "live", f"never went live: {mp.status.text()!r}"
    assert mp.body.isVisible(), "stats body should be visible"
    assert mp.placeholder.isHidden()
    assert mp.lbl_uptime.text().startswith("Uptime ")
    assert mp.lbl_uptime.text() != "Uptime —"
    assert 0 <= mp.cpu.bar.value() <= 100
    win.close()


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
def test_main_window_monitor_panel_wiring(qtapp):
    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx()
    win = MainWindow(ctx)
    assert win.monitor_panel is not None
    assert win.session_info_label is not None
    # default: panel visible, collapsed (MobaXterm-style bottom strip)
    assert not win.monitor_panel.isHidden()
    assert win.monitor_panel.collapsed

    win.set_monitor_panel_visible(False)
    assert win.monitor_panel.isHidden()
    win.set_monitor_panel_visible(True)
    assert not win.monitor_panel.isHidden()
    assert win._act_monitor_panel.isChecked()

    win.close()
    qtapp.processEvents()


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
