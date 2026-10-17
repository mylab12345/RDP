"""Tests covering the 10 UX & workflow optimizations across KB-Remote."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton, QWidget

from rdpstudio.app import build_context
from rdpstudio.core.activity import ActivityLog
from rdpstudio.core.events import EventBus
from rdpstudio.core.feedback import FeedbackStore, build_safe_diagnostics
from rdpstudio.core.models import PROTOCOL_RDP, PROTOCOL_SSH, Session
from rdpstudio.core.settings import DASHBOARD_TILE_IDS, Settings
from rdpstudio.ui import theme
from rdpstudio.ui.activity_dialog import ActivityLogDialog
from rdpstudio.ui.dashboard import DASHBOARD_TILES
from rdpstudio.ui.feedback_dialog import FeedbackDialog
from rdpstudio.ui.main_window import MainWindow
from rdpstudio.ui.onboarding import (
    ONBOARDING_STEPS,
    OnboardingGuideDialog,
    format_interactive_tooltip,
    set_interactive_tooltip,
)
from rdpstudio.ui.settings_dialog import SettingsDialog
from rdpstudio.ui.shortcuts_dialog import _GROUPS, ShortcutsDialog
from rdpstudio.ui.support_chat import SupportChatDialog, SupportChatPanel, generate_support_reply


def _make_window(qtapp) -> MainWindow:
    ctx = build_context()
    theme.apply_theme(qtapp, ctx.settings.theme, animations=False)
    return MainWindow(ctx)


# ----------------------------------------------------------------------
# 1. Simplified Dashboard & RDP Navigation
# ----------------------------------------------------------------------
def test_dashboard_rdp_navigation_and_protocol_presets(home, qtapp) -> None:  # noqa: ARG001
    for tid in ("new_rdp", "activity_log", "support_chat", "onboarding", "feedback"):
        assert tid in DASHBOARD_TILE_IDS
        assert tid in DASHBOARD_TILES

    win = _make_window(qtapp)
    try:
        dash = win._empty
        labels = [b.text() for b in dash.findChildren(QPushButton)]
        for expected in ("New RDP Desktop", "RDP 3389", "SSH 22", "SFTP", "Tour", "Activity", "Support", "Feedback"):
            assert expected in labels, f"missing {expected} in {labels}"

        win.dash_quick.setText("win-box")
        win._set_dash_quick_protocol("rdp")
        assert win.dash_quick.text() == "win-box:3389"
        win._set_dash_quick_protocol("ssh")
        assert win.dash_quick.text() == "win-box:22"
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 2. Real-time Connection Status Indicators & User Activity Logs
# ----------------------------------------------------------------------
def test_activity_log_core_and_event_bus(tmp_path: Path) -> None:
    log_path = tmp_path / "activity.jsonl"
    alog = ActivityLog(log_path, max_entries=50)
    bus = EventBus()
    detach = alog.attach_bus(bus)
    try:
        bus.publish("session/connecting", {"protocol": "rdp", "host": "10.0.0.5", "session": "WinSRV"})
        bus.publish("session/connected", {"protocol": "rdp", "host": "10.0.0.5", "session": "WinSRV"})
        bus.publish("session/failed", {"protocol": "ssh", "host": "10.0.0.9", "reason": "Auth failed"})
        bus.publish("transfer/completed", {"direction": "upload", "ok": True, "detail": "report.pdf"})

        assert alog.count() == 4
        conn_entries = alog.entries(kind="connection")
        assert len(conn_entries) == 3
        bad_entries = alog.entries(level="bad")
        assert len(bad_entries) == 1
        assert "Auth failed" in bad_entries[0].detail

        # Reload from disk
        reloaded = ActivityLog(log_path, max_entries=50)
        assert reloaded.count() == 4
        counts = reloaded.summary_counts()
        assert counts["total"] == 4
        assert counts["errors"] == 1
    finally:
        detach()


def test_activity_log_dialog_and_status_indicators(home, qtapp) -> None:  # noqa: ARG001
    win = _make_window(qtapp)
    try:
        assert hasattr(win, "status_indicator")
        assert hasattr(win, "activity_btn")
        win.activity_log.record("connection", "RDP connected", "10.0.0.12:3389", level="good", protocol="rdp")
        win._update_activity_badge()
        assert "event" in win.activity_btn.text()

        dlg = ActivityLogDialog(win, win.activity_log, win)
        try:
            assert dlg.table.rowCount() >= 1
            dlg.search_input.setText("10.0.0.12")
            assert len(dlg.visible_entries()) >= 1
            dlg.clear_log()
            assert dlg.table.rowCount() == 0
        finally:
            dlg.close()
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 3. Drag-and-Drop File Transfer with Visual Progress Bars
# ----------------------------------------------------------------------
def test_session_tab_drag_and_drop_progress_bar(home, qtapp, tmp_path: Path) -> None:  # noqa: ARG001
    sample = tmp_path / "payload.txt"
    sample.write_text("hello world", encoding="utf-8")

    win = _make_window(qtapp)
    try:
        tab = win.open_local_terminal()
        assert tab is not None
        assert tab.acceptDrops()
        count = tab.handle_dropped_files([str(sample)])
        assert count == 1
        assert not tab.transfer_bar.isHidden()
        assert tab.transfer_progress.value() == 100
        assert "payload.txt" in tab.transfer_label.text()
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 4. Quick-Connect Panel with Saved Sessions & Frequent Servers
# ----------------------------------------------------------------------
def test_frequent_servers_ranking_and_one_click_access(home, qtapp) -> None:  # noqa: ARG001
    s = Settings()
    s.touch_recent_session("srv-a")
    s.touch_recent_session("srv-b")
    s.touch_recent_session("srv-b")
    s.touch_recent_session("srv-b")
    assert s.session_connect_counts["srv-b"] == 3
    assert s.frequent_session_ids()[0] == "srv-b"

    win = _make_window(qtapp)
    try:
        s1 = Session(id="s1", name="rdp-prod", protocol=PROTOCOL_RDP, host="10.0.1.10", username="admin", password="pw")
        s2 = Session(id="s2", name="ssh-bastion", protocol=PROTOCOL_SSH, host="10.0.1.20", username="ops", password="pw")
        win.ctx.store.upsert(s1)
        win.ctx.store.upsert(s2)
        win.ctx.settings.touch_recent_session("s1")
        win.ctx.settings.touch_recent_session("s1")
        win.sidebar.reload()
        win._refresh_dashboard()

        assert not win.sidebar.frequent_panel.isHidden()
        assert len(win.sidebar.frequent_buttons) == 2
        assert "rdp-prod" in win.sidebar.frequent_buttons[0].text()

        freq_panel = win._empty.findChild(QWidget, "dashFrequentPanel")
        assert freq_panel is not None
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 5. Customisable Themes (Dark/Light Mode) & Font Sizes
# ----------------------------------------------------------------------
def test_dark_light_theme_toggle_and_font_scaling(home, qtapp) -> None:  # noqa: ARG001
    win = _make_window(qtapp)
    try:
        win.apply_theme_id("dracula")
        assert win.ctx.settings.is_dark_mode()
        assert win.ctx.settings.preferred_dark_theme == "dracula"

        # Toggle to Light mode
        t1 = win.toggle_dark_light_theme()
        assert t1 == "mobaxterm"
        assert not win.ctx.settings.is_dark_mode()

        # Toggle back restores preferred dark theme ('dracula')
        t2 = win.toggle_dark_light_theme()
        assert t2 == "dracula"
        assert win.ctx.settings.is_dark_mode()

        # Font scaling
        win.reset_font_size()
        assert win.ctx.settings.font_size == 10
        win.increase_font_size()
        assert win.ctx.settings.font_size == 11
        assert win.font_size_label.text() == "11pt"
        win.decrease_font_size()
        assert win.ctx.settings.font_size == 10

        dlg = SettingsDialog(win.ctx.settings, win)
        try:
            assert hasattr(dlg, "btn_quick_dark")
            assert hasattr(dlg, "btn_quick_light")
            assert len(dlg.font_size_presets) == 4
        finally:
            dlg.close()
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 6. Interactive Tooltips & Onboarding Guides
# ----------------------------------------------------------------------
def test_interactive_tooltips_and_onboarding_guide(home, qtapp) -> None:  # noqa: ARG001
    html_tip = format_interactive_tooltip(
        "Quick Connect",
        "Open SSH or RDP target.",
        shortcut="Ctrl+Shift+K",
        tip="Port 3389 opens RDP.",
    )
    assert "Quick Connect" in html_tip
    assert "Ctrl+Shift+K" in html_tip
    assert "Port 3389 opens RDP." in html_tip

    btn = QPushButton("Test")
    set_interactive_tooltip(btn, "Action", "Desc", shortcut="F1", tip="Helpful", enabled=True)
    assert "<b>Action</b>" in btn.toolTip()
    set_interactive_tooltip(btn, "Action", "Desc", shortcut="F1", tip="Helpful", enabled=False)
    assert btn.toolTip() == "Action (F1)"

    win = _make_window(qtapp)
    try:
        dlg = OnboardingGuideDialog(win, win)
        try:
            assert dlg.step_index == 0
            assert len(ONBOARDING_STEPS) == 6
            dlg.next_step()
            assert dlg.step_index == 1
            dlg.prev_step()
            assert dlg.step_index == 0
            dlg.go_to_step(5)
            assert dlg.step_index == 5
            dlg.finish_tour()
            assert win.ctx.settings.onboarding_completed is True
        finally:
            dlg.close()
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 7. In-Session Chat / Support for Instant Troubleshooting & Feedback
# ----------------------------------------------------------------------
def test_in_session_support_chat_and_diagnostics(home, qtapp) -> None:  # noqa: ARG001
    rdp_reply = generate_support_reply("rdp black screen", protocol="rdp", host="10.0.0.5", port=3389)
    assert "RDP Troubleshooting" in rdp_reply

    auth_reply = generate_support_reply("host key auth failed", protocol="ssh", host="10.0.0.5", port=22)
    assert "Authentication" in auth_reply

    panel = SupportChatPanel(session_name="prod-rdp", protocol="rdp", host="127.0.0.1", port=3389)
    reply = panel.send_message("diagnose connection")
    assert "Live Session Diagnostics" in reply
    assert len(panel.messages) == 3  # greeting + user + support

    win = _make_window(qtapp)
    try:
        tab = win.open_local_terminal()
        assert tab is not None
        assert tab.support_panel.isHidden()
        tab.toggle_support_panel()
        assert not tab.support_panel.isHidden()
        tab.toggle_support_panel()
        assert tab.support_panel.isHidden()

        dlg = SupportChatDialog(win, win)
        dlg.close()
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 8. Mobile Responsiveness for Tablet & Smartphone Users
# ----------------------------------------------------------------------
def test_mobile_touch_responsive_mode(home, qtapp) -> None:  # noqa: ARG001
    win = _make_window(qtapp)
    try:
        assert not win.ctx.settings.mobile_touch_mode
        win.set_mobile_touch_mode(True)
        assert win.ctx.settings.mobile_touch_mode is True
        assert win.property("mobileMode") is True
        assert win._sidebar_collapsed is True
        assert win._toolbar.iconSize() == QSize(22, 22)

        win.set_mobile_touch_mode(False)
        assert win.ctx.settings.mobile_touch_mode is False
        assert win.property("mobileMode") is False
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# 9. Keyboard Shortcuts & Context Menus
# ----------------------------------------------------------------------
def test_keyboard_shortcuts_reference_includes_new_bindings(qtapp) -> None:
    all_rows = [row for _grp, rows in _GROUPS for row in rows]
    combos = " | ".join(combo for _label, combo in all_rows)
    for expected in (
        "Ctrl + Shift + R",
        "Ctrl + Alt + T",
        "Ctrl + Shift + M",
        "Ctrl + Shift + A",
        "Ctrl + Shift + H",
        "Ctrl + Shift + I",
        "Ctrl + Shift + G",
        "F1",
    ):
        assert expected in combos, f"missing {expected}"

    dlg = ShortcutsDialog()
    dlg.close()


# ----------------------------------------------------------------------
# 10. Feedback Button & Store for Suggesting Improvements
# ----------------------------------------------------------------------
def test_feedback_store_and_dialog(home, qtapp, tmp_path: Path) -> None:  # noqa: ARG001
    store = FeedbackStore(tmp_path / "feedback.jsonl")
    diag = build_safe_diagnostics(Settings(), active_protocol="rdp")
    assert "password" not in diag
    assert diag["active_protocol"] == "rdp"

    win = _make_window(qtapp)
    try:
        assert hasattr(win, "feedback_status_btn")
        dlg = FeedbackDialog(
            win,
            store=store,
            prefill_title="Add multi-monitor RDP toggle",
            prefill_description="Allow selecting monitors directly from the RDP header.",
            category="rdp",
        )
        try:
            dlg.set_rating(4)
            assert dlg.rating == 4
            entry = dlg.submit_feedback()
            assert entry is not None
            assert entry.rating == 4
            assert entry.category == "rdp"
            assert len(store.list_recent()) == 1
            md = entry.to_markdown()
            assert "Add multi-monitor RDP toggle" in md
            assert "★★★★☆" in md
        finally:
            dlg.close()
    finally:
        win.close()
        qtapp.processEvents()
