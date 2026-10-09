"""Tests for the UI-enhancement round: simplified navigation (icons +
status tips on every menu action), typography/section hierarchy in the QSS,
responsive flow layouts, interactive hover feedback, tab tooltips, and the
customisable welcome dashboard (sections + launcher tiles)."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.usefixtures("home")


def _ctx(settings=None):
    from rdpstudio.core import paths
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    return SessionContext(
        settings=settings or Settings(),
        store=SessionStore(paths.sessions_file()),
        vault=CredentialVault(paths.vault_file()),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )


def _main_window(qtapp, settings=None):
    from rdpstudio.ui import theme
    from rdpstudio.ui.main_window import MainWindow

    ctx = _ctx(settings)
    theme.apply_theme(qtapp, ctx.settings.theme, animations=False)
    return MainWindow(ctx)


# ----------------------------------------------------------------------
# Settings: dashboard_layout defaults + coercion
# ----------------------------------------------------------------------
def test_dashboard_layout_defaults_and_coercion() -> None:
    from rdpstudio.core.settings import (
        DASHBOARD_TILE_IDS,
        DEFAULT_DASHBOARD_LAYOUT,
        Settings,
        coerce_dashboard_layout,
    )

    s = Settings()
    assert s.dashboard_layout == DEFAULT_DASHBOARD_LAYOUT
    # defaults: every section on, the four minimal launcher tiles
    assert s.dashboard_layout["show_quick_connect"] is True
    assert s.dashboard_layout["show_actions"] is True
    assert s.dashboard_layout["show_recents"] is True
    assert s.dashboard_layout["show_shortcuts"] is True
    assert s.dashboard_layout["tiles"] == [
        "new_session", "local_terminal", "commands", "settings",
    ]

    # garbage in → defaults out
    assert coerce_dashboard_layout(None) == DEFAULT_DASHBOARD_LAYOUT
    assert coerce_dashboard_layout("nonsense") == DEFAULT_DASHBOARD_LAYOUT
    assert coerce_dashboard_layout({"tiles": "nope"})["tiles"] == DEFAULT_DASHBOARD_LAYOUT["tiles"]

    # partial dict merges with defaults
    merged = coerce_dashboard_layout({"show_shortcuts": False})
    assert merged["show_shortcuts"] is False
    assert merged["show_recents"] is True

    # unknown tile ids are dropped; an empty selection restores the default
    pruned = coerce_dashboard_layout({"tiles": ["keys", "bogus", "keys", "cluster"]})
    assert pruned["tiles"] == ["keys", "cluster"]
    assert coerce_dashboard_layout({"tiles": ["bogus"]})["tiles"] == DEFAULT_DASHBOARD_LAYOUT["tiles"]

    # every advertised tile id is a known, buildable tile
    assert set(DASHBOARD_TILE_IDS) >= set(DEFAULT_DASHBOARD_LAYOUT["tiles"])

    # round-trips through the settings file format
    loaded = Settings.from_dict({"dashboard_layout": {"show_recents": False, "tiles": ["keys"]}})
    assert loaded.dashboard_layout["show_recents"] is False
    assert loaded.dashboard_layout["tiles"] == ["keys"]
    # a hand-edited garbage file must not break startup
    broken = Settings.from_dict({"dashboard_layout": 42})
    assert broken.dashboard_layout == DEFAULT_DASHBOARD_LAYOUT


# ----------------------------------------------------------------------
# Dashboard: sections + tiles honour the custom layout
# ----------------------------------------------------------------------
def test_dashboard_sections_respect_custom_layout(qtapp) -> None:
    from PySide6.QtWidgets import QWidget

    from rdpstudio.core.settings import Settings

    s = Settings()
    s.dashboard_layout = {
        "show_quick_connect": True,
        "show_actions": True,
        "show_recents": False,
        "show_shortcuts": False,
        "tiles": ["new_session", "local_terminal", "commands", "settings"],
    }
    win = _main_window(qtapp, s)
    try:
        empty = win._empty
        assert empty.findChild(QWidget, "dashSectionQuick") is not None
        assert empty.findChild(QWidget, "dashSectionActions") is not None
        assert empty.findChild(QWidget, "dashSectionShortcuts") is None
        assert empty.findChild(QWidget, "dashSectionRecents") is None
    finally:
        win.close()
        qtapp.processEvents()


def test_dashboard_tiles_selection_and_order(qtapp) -> None:
    from PySide6.QtWidgets import QLabel, QWidget

    from rdpstudio.core.settings import Settings

    s = Settings()
    s.dashboard_layout = {
        "show_quick_connect": False,
        "show_actions": True,
        "show_recents": False,
        "show_shortcuts": False,
        "tiles": ["settings", "keys", "new_session"],
    }
    win = _main_window(qtapp, s)
    try:
        empty = win._empty
        assert empty.findChild(QWidget, "dashSectionQuick") is None
        tiles = empty.findChildren(QWidget, "dashTile")
        labels = []
        for tile in tiles:
            lbl = tile.findChild(QLabel, "cardTitle")
            labels.append(lbl.text() if lbl is not None else "")
        assert labels == ["Settings", "SSH keys", "New session"]
    finally:
        win.close()
        qtapp.processEvents()


def test_dashboard_tiles_are_keyboard_activatable(qtapp, monkeypatch) -> None:
    """Accessibility: tiles take focus and fire on Enter/Space."""
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QWidget

    win = _main_window(qtapp)
    try:
        # Rewire the first tile's action to a spy, then rebuild the
        # dashboard so the tile captures the spy (the real action would
        # open a modal dialog).
        fired: list[str] = []
        monkeypatch.setattr(win, "new_session", lambda *a: fired.append("new"))
        win._refresh_dashboard()
        tiles = win._empty.findChildren(QWidget, "dashTile")
        assert tiles, "dashboard should render launcher tiles"
        tile = tiles[0]
        assert tile.focusPolicy() == Qt.FocusPolicy.StrongFocus
        assert tile.accessibleName()
        ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
        tile.keyPressEvent(ev)
        assert fired == ["new"] and ev.isAccepted()
        ev2 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        tile.keyPressEvent(ev2)
        assert fired == ["new", "new"] and ev2.isAccepted()
    finally:
        win.close()
        qtapp.processEvents()


def test_dashboard_customize_dialog_updates_and_persists(qtapp) -> None:
    from PySide6.QtCore import Qt

    from rdpstudio.core import paths
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.dashboard import DashboardCustomizeDialog

    s = Settings()
    dlg = DashboardCustomizeDialog(s, save_to_disk=True)
    try:
        assert dlg._tile_list.count() >= 9  # every registered tile is listed
        # hide the shortcuts section
        dlg._cb_shortcuts.setChecked(False)
        # uncheck the Settings tile
        for i in range(dlg._tile_list.count()):
            item = dlg._tile_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == "settings":
                item.setCheckState(Qt.CheckState.Unchecked)
        # check "SSH keys" (id "keys") and move it to the top of the list
        for i in range(dlg._tile_list.count()):
            if dlg._tile_list.item(i).data(Qt.ItemDataRole.UserRole) == "keys":
                dlg._tile_list.item(i).setCheckState(Qt.CheckState.Checked)
                dlg._tile_list.setCurrentRow(i)
                break
        for _ in range(dlg._tile_list.count()):
            dlg._move_selected(-1)
        dlg.accept()
        assert dlg.result_layout["show_shortcuts"] is False
        assert dlg.result_layout["tiles"][0] == "keys"
        assert "settings" not in dlg.result_layout["tiles"]
        # live settings object updated + persisted to disk
        assert s.dashboard_layout == dlg.result_layout
        reloaded = Settings.load(paths.settings_file())
        assert reloaded.dashboard_layout == dlg.result_layout
    finally:
        dlg.close()
        qtapp.processEvents()


def test_dashboard_customize_dialog_no_disk_save_leaves_settings(qtapp) -> None:
    from rdpstudio.core.settings import DEFAULT_DASHBOARD_LAYOUT, Settings
    from rdpstudio.ui.dashboard import DashboardCustomizeDialog

    s = Settings()
    dlg = DashboardCustomizeDialog(s, save_to_disk=False)
    try:
        dlg._cb_recents.setChecked(False)
        dlg.accept()
        assert dlg.result_layout["show_recents"] is False
        # the passed settings object is untouched — the caller merges
        assert s.dashboard_layout == DEFAULT_DASHBOARD_LAYOUT
    finally:
        dlg.close()
        qtapp.processEvents()


def test_dashboard_rebuilds_after_customize(qtapp) -> None:
    """Applying the customizer rebuilds the dashboard with the new layout."""
    from PySide6.QtWidgets import QWidget

    win = _main_window(qtapp)
    try:
        assert win._empty.findChild(QWidget, "dashSectionShortcuts") is not None
        win.ctx.settings.dashboard_layout = {
            "show_quick_connect": True,
            "show_actions": True,
            "show_recents": True,
            "show_shortcuts": False,
            "tiles": ["new_session"],
        }
        win._refresh_dashboard()
        assert win._empty.findChild(QWidget, "dashSectionShortcuts") is None
        tiles = win._empty.findChildren(QWidget, "dashTile")
        assert len(tiles) == 1
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# Responsive design: FlowLayout wraps
# ----------------------------------------------------------------------
def test_flow_layout_wraps_on_narrow_width(qtapp) -> None:  # noqa: ARG001
    from PySide6.QtWidgets import QWidget

    from rdpstudio.ui.widgets import FlowLayout

    parent = QWidget()
    flow = FlowLayout(parent, margin=0, spacing=10)
    tiles = []
    for _ in range(4):
        tile = QWidget()
        tile.setFixedSize(154, 104)
        flow.addWidget(tile)
        tiles.append(tile)
    parent.resize(1000, 800)
    # one row when wide, more rows when narrow
    wide = flow.heightForWidth(1000)
    narrow = flow.heightForWidth(340)
    assert narrow > wide
    flow.setGeometry(flow.geometry().adjusted(0, 0, -660, 0))
    ys = {t.y() for t in tiles}
    assert len(ys) > 1, "tiles should wrap to multiple rows"
    parent.close()


# ----------------------------------------------------------------------
# Interactive elements: hover elevation
# ----------------------------------------------------------------------
def test_hover_shadow_toggles_on_enter_leave(qtapp) -> None:  # noqa: ARG001
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtWidgets import QApplication, QWidget

    from rdpstudio.ui.widgets import install_hover_shadow

    w = QWidget()
    install_hover_shadow(w)
    assert w.graphicsEffect() is None
    QApplication.sendEvent(w, QEnterEvent(w.rect().topLeft(), w.rect().center(), w.rect().center()))
    assert w.graphicsEffect() is not None, "hover should elevate the card"
    QApplication.sendEvent(w, QEvent(QEvent.Type.Leave))
    assert w.graphicsEffect() is None, "leaving should drop the elevation"
    w.close()


# ----------------------------------------------------------------------
# Simplified navigation: icons + status tips on every menu action
# ----------------------------------------------------------------------
def _walk_menu_actions(menu):
    for act in menu.actions():
        yield act
        if act.menu() is not None:
            yield from _walk_menu_actions(act.menu())


def test_menu_actions_have_status_tips_and_icons(qtapp) -> None:
    win = _main_window(qtapp)
    try:
        # Tab-walk actions have no fitting glyph; checkable actions show a
        # check/radio indicator instead of an icon.
        iconless_ok = {"&Next Tab", "Pre&vious Tab"}
        checked = 0
        for top in win.menuBar().actions():
            menu = top.menu()
            assert menu is not None, f"{top.text()} should be a menu"
            for act in _walk_menu_actions(menu):
                if act.isSeparator():
                    continue
                checked += 1
                assert act.statusTip(), f"missing status tip: {act.text()}"
                if act.isCheckable() or act.text() in iconless_ok:
                    continue
                assert not act.icon().isNull(), f"missing icon: {act.text()}"
        assert checked > 40, "the menu bar should be fully covered"
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# User feedback: tab tooltips + theme-change toast
# ----------------------------------------------------------------------
def test_tab_tooltip_shows_full_identity(qtapp) -> None:
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session

    win = _main_window(qtapp)
    try:
        defn = Session(name="shell", protocol=PROTOCOL_LOCAL)
        defn.options["command"] = "/bin/sh"
        tab = win.open_session(defn)
        assert tab is not None
        idx = win.tabs.indexOf(tab)
        tip = win.tabs.tabToolTip(idx)
        assert "shell" in tip
        assert "LOCAL" in tip
        win.close_tab(idx)
    finally:
        win.close()
        qtapp.processEvents()


def test_theme_change_gives_feedback(qtapp) -> None:
    win = _main_window(qtapp)
    try:
        win.apply_theme_id("midnight")
        assert win.ctx.settings.theme == "midnight"
        # the theme submenu action is checked
        assert win._theme_actions["midnight"].isChecked()
        win.apply_theme_id("not-a-theme")  # ignored, no crash
        assert win.ctx.settings.theme == "midnight"
    finally:
        win.close()
        qtapp.processEvents()


def test_tabs_position_change_gives_feedback(qtapp) -> None:
    win = _main_window(qtapp)
    try:
        assert win.tabs_position() == "top"
        win.set_tabs_position("left")
        assert win.tabs_position() == "left"
        assert win.ctx.settings.geometry["tabs_position"] == "left"
        win.set_tabs_position("top")
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# Typography / hierarchy / accessibility in the global stylesheet
# ----------------------------------------------------------------------
def test_qss_has_section_labels_and_extended_focus_rings(qtapp) -> None:  # noqa: ARG001
    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    qss = qtapp.styleSheet()
    # visual hierarchy: dashboard section captions + heading scale
    assert "QLabel#dashSection" in qss
    assert "QLabel#dashTitle" in qss
    assert "QLabel#h1" in qss
    # accessibility: focus rings on every interactive family
    for sel in (
        "QMenuBar::item:focus",
        "QCheckBox::indicator:focus",
        "QRadioButton::indicator:focus",
        "QSlider::handle:horizontal:focus",
        "QListView:focus",
        "QTabBar::close-button:hover",
        "QWidget#dashTile:focus",
    ):
        assert sel in qss, sel


def test_window_minimum_size_supports_small_screens(qtapp) -> None:
    win = _main_window(qtapp)
    try:
        assert win.minimumSize().width() <= 900
        assert win.minimumSize().height() <= 560
    finally:
        win.close()
        qtapp.processEvents()


def test_quick_connect_input_is_flexible_width(qtapp) -> None:
    win = _main_window(qtapp)
    try:
        assert win.quick.maximumWidth() < 400  # shrinks on narrow windows
        assert win.quick.minimumWidth() >= 100
    finally:
        win.close()
        qtapp.processEvents()
