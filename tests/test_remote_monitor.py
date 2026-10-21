"""Remote monitoring: output parsing, formatting, and dialog rendering."""

from __future__ import annotations

SAMPLE = """@@HOST
box01
Linux 6.8.0-45-generic
@@UP
12345.67 9000.00
@@LOAD
0.15 0.20 0.25 1/100 1234
@@CPU
cpu  100 0 100 800 0 0 0 0 0 0
cpu  110 0 110 850 0 0 0 0 0 0
@@MEM
MemTotal:        8000000 kB
MemFree:         1000000 kB
MemAvailable:    2000000 kB
Buffers:          500000 kB
Cached:          1500000 kB
SwapTotal:       2000000 kB
SwapFree:        1500000 kB
@@DISK
/dev/sda1 100000000 40000000 60000000 40% /
@@NET
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:  1000      10    0    0    0     0          0         0     1000      10    0    0    0     0       0          0
  eth0: 2048      20    0    0    0     0          0         0     4096      20    0    0    0     0       0          0
"""


def test_parse_monitor_output_core_stats():
    from rdpstudio.ui.monitor_dialog import parse_monitor_output

    stats = parse_monitor_output(SAMPLE)
    assert stats["host"] == "box01"
    assert stats["os"].startswith("Linux")
    assert stats["uptime_s"] == 12345.67
    assert stats["load"] == (0.15, 0.20, 0.25)
    # CPU delta: total +70, idle +50 -> 28.57% busy
    assert stats["cpu_percent"] == 100 * (1 - 50 / 70)
    assert stats["mem_total_kb"] == 8_000_000
    assert stats["mem_used_kb"] == 6_000_000
    assert stats["mem_percent"] == 75.0
    assert stats["swap_used_kb"] == 500_000
    assert stats["disk_percent"] == 40.0
    assert stats["disk_mount"] == "/"
    assert stats["net_rx"] == 2048  # loopback excluded
    assert stats["net_tx"] == 4096
    assert stats["net_rx_rate"] is None


def test_parse_monitor_output_network_rates():
    from rdpstudio.ui.monitor_dialog import parse_monitor_output

    later = SAMPLE.replace(
        "  eth0: 2048      20    0    0    0     0          0         0     4096      20",
        "  eth0: 6144      20    0    0    0     0          0         0     4096      20",
    )
    stats = parse_monitor_output(later, prev_net=(2048, 4096), elapsed=2.0)
    assert stats["net_rx"] == 6144
    assert stats["net_rx_rate"] == (6144 - 2048) / 2.0
    assert stats["net_tx_rate"] == (4096 - 4096) / 2.0


def test_format_helpers():
    from rdpstudio.ui.monitor_dialog import format_bytes, format_uptime

    assert format_bytes(0) == "0 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_uptime(59) == "0m"
    assert format_uptime(3600 + 120) == "1h 2m"
    assert format_uptime(86400 + 7200) == "1d 2h 0m"
    assert format_uptime(None) == "—"


def test_monitor_dialog_renders_stats(qtapp, monkeypatch):
    from rdpstudio.core.models import Session
    from rdpstudio.ui import monitor_dialog

    class Controller:
        definition = Session(host="box01", username="u", name="box01")

        def exec_command(self, command, timeout=6.0):  # pragma: no cover - not polled
            raise AssertionError("no polling in this test")

    monkeypatch.setattr(monitor_dialog.RemoteMonitorDialog, "refresh", lambda self: None)
    dlg = monitor_dialog.RemoteMonitorDialog(Controller())
    stats = monitor_dialog.parse_monitor_output(
        SAMPLE, prev_net=(1024, 1024), elapsed=2.0
    )
    dlg._apply(stats)
    assert dlg.host_label.text() == "box01"
    assert dlg.mem_bar.value() == 75
    assert dlg.disk_bar.value() == 40
    assert "Load 0.15" in dlg.detail.text()
    assert "↓" in dlg.detail.text()
    dlg.close()
    assert dlg._closed is True


def test_ssh_tab_header_shows_monitor_button(qtapp):
    from PySide6.QtWidgets import QPushButton, QWidget

    from rdpstudio.core import paths
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import Session
    from rdpstudio.core.plugin import SessionContext, SessionController
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.protocols.base_caps import capability_set
    from rdpstudio.ui.main_window import MainWindow, SessionTab
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(paths.sessions_file()),
        vault=CredentialVault(paths.vault_file()),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )

    class Sshish(SessionController):
        def __init__(self):
            super().__init__(Session(name="ssh", host="h.example"), ctx)
            self.set_state("connected")

        def start(self):
            pass

        def widget(self):
            return QWidget()

        def capabilities(self):
            return capability_set(shell=True, sftp=True)

        def exec_command(self, command, timeout=8.0):  # pragma: no cover
            return ""

        def open_sftp(self):
            pass

    win = MainWindow(ctx)
    controller = Sshish()
    tab = SessionTab(controller, win)
    win.tabs.addTab(tab, "ssh")
    opened: list = []
    win.open_remote_monitor_for = opened.append
    button = next(
        b for b in tab.findChildren(QPushButton) if b.text() == "Monitor"
    )
    button.click()
    assert opened == [controller]
    win.close()
    qtapp.processEvents()


def test_monitor_bar_follows_connected_ssh_tab(qtapp, monkeypatch):
    from rdpstudio.core.models import Session
    from rdpstudio.ui import monitor_bar

    class Controller:
        def __init__(self, state):
            self.definition = Session(host="box01", username="u", name="box01")
            self._state = state

        def state(self):
            return self._state

        def exec_command(self, command, timeout=6.0):  # pragma: no cover - not polled
            raise AssertionError("polling is stubbed in this test")

    # Keep bind() from starting the polling thread.
    monkeypatch.setattr(monitor_bar.MonitorBar, "refresh", lambda self: None)
    bar = monitor_bar.MonitorBar()
    bar.bind(None)
    assert bar.isHidden()

    live = Controller("connected")
    bar.bind(live)
    assert not bar.isHidden()
    assert bar.host.text() == "box01"
    assert bar._timer.isActive()

    stats = monitor_bar.parse_monitor_output(
        SAMPLE, prev_net=(1024, 1024), elapsed=2.0
    )
    bar._apply(stats)
    assert bar.cpu.value.text().endswith("%")
    assert bar.mem.value.text() == "5.7GB"
    assert bar.disk.value.text() == "38.1GB"
    assert "↓" in bar.net.text()
    assert "Load" in bar.detail.text()

    bar.bind(Controller("closed"))
    assert bar.isHidden()
    assert not bar._timer.isActive()
    bar.shutdown()
