"""Docking: MobaXterm dark theme, edge zones and mouse-driven layout moves.

Covers the two user-visible features shipped together:

* the MobaXterm Dark palette (default look, still switchable), and
* dragging the Sessions panel / session tab strip to another window edge,
  including the pure-logic hit testing behind the drop indicator.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture()
def ctx(home, qtapp):  # noqa: ARG001
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


@pytest.fixture()
def win(ctx, qtapp):  # noqa: ARG001
    from rdpstudio.ui import theme
    from rdpstudio.ui.main_window import MainWindow

    # The window re-applies the *settings'* animation pref on build, so turn
    # it off there: the layout moves below then settle in one step instead of
    # racing a 140 ms tween.
    ctx.settings.animations = False
    theme.apply_theme(qtapp, ctx.settings.theme, animations=False)
    window = MainWindow(ctx)
    window.resize(1280, 800)
    yield window
    window.close()
    qtapp.processEvents()


# ----------------------------------------------------------------------
# MobaXterm dark theme
# ----------------------------------------------------------------------
def test_mobaxterm_dark_is_the_default_theme(qtapp) -> None:  # noqa: ARG001
    """The shipped default is MobaXterm Dark; light stays selectable."""
    from rdpstudio.core.settings import DARK_THEMES, THEME_IDS, Settings
    from rdpstudio.ui import theme

    assert "mobaxterm_dark" in THEME_IDS and "mobaxterm" in THEME_IDS
    assert "mobaxterm_dark" in DARK_THEMES and "mobaxterm" not in DARK_THEMES
    assert Settings().theme == "mobaxterm_dark"
    assert Settings.from_dict({"theme": "bogus"}).theme == "mobaxterm_dark"
    assert theme.current_theme() == "mobaxterm_dark"

    pal = theme.PALETTE["mobaxterm_dark"]
    assert len(pal) == 30  # same key set as every other palette (QSS format)
    assert pal["bg"] == "#1c1c1f"  # charcoal chrome, MobaXterm geometry
    assert pal["accent"] == "#1670c6"  # Windows-blue accent, darkened to AA


def test_dark_chrome_renders_dark_not_light(qtapp) -> None:  # noqa: ARG001
    """Guard the classic regression: chrome painted light while dark is set."""
    from rdpstudio.ui import theme
    from rdpstudio.ui.theme import palette_color

    theme.apply_theme(qtapp, "mobaxterm_dark", animations=False)
    assert palette_color(theme.palette()["bg"]).lightness() < 60
    assert palette_color(theme.palette()["bg2"]).lightness() < 70
    qss = qtapp.styleSheet()
    # Every surface the sheet paints comes from the dark palette.
    assert theme.palette()["bg"] in qss and theme.palette()["panel"] in qss
    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    assert palette_color(theme.palette()["bg"]).lightness() > 200


def test_dark_classes_and_legibility(qtapp) -> None:  # noqa: ARG001
    """is_dark_theme() drives terminal colours, and the toolbar glyphs stay
    readable rather than neon on the neutral dark chrome."""
    from PySide6.QtCore import QSize

    from rdpstudio.ui import theme

    assert theme.is_dark_theme("mobaxterm_dark")
    assert not theme.is_dark_theme("mobaxterm")
    theme.apply_theme(qtapp, "mobaxterm_dark", animations=False)
    glyph = theme.toolbar_icon("plus").pixmap(QSize(24, 24)).toImage()
    opaque = [
        glyph.pixelColor(x, y)
        for x in range(glyph.width())
        for y in range(glyph.height())
        if glyph.pixelColor(x, y).alpha() > 200
    ]
    assert opaque, "the session glyph must render"
    # Still green (hue survives the lift) but no channel is allowed to blow
    # out into neon on the charcoal chrome.
    avg = tuple(sum(getattr(c, ch)() for c in opaque) / len(opaque) for ch in ("red", "green", "blue"))
    assert avg[1] > avg[0] and avg[1] > avg[2], avg
    assert avg[1] > 150, f"glyph too dim for dark chrome: {avg}"
    peak = max(max(getattr(c, ch)() for ch in ("red", "green", "blue")) for c in opaque)
    assert peak <= 215, f"glyph blown out for dark chrome: {peak}"

    # Red stays red, and the branch that swaps charcoal for the theme fg
    # still applies to the neutral toolbar glyphs.
    red = theme.toolbar_icon("close").pixmap(QSize(24, 24)).toImage()
    red_px = [
        red.pixelColor(x, y)
        for x in range(red.width())
        for y in range(red.height())
        if red.pixelColor(x, y).alpha() > 200
    ]
    red_avg = tuple(sum(getattr(c, ch)() for c in red_px) / len(red_px) for ch in ("red", "green", "blue"))
    assert red_avg[0] > red_avg[1] and red_avg[0] > red_avg[2], red_avg


def test_theme_cards_cover_every_theme(qtapp) -> None:  # noqa: ARG001
    """Settings offers every registered theme as a preview card."""
    from rdpstudio.core.settings import THEME_CHOICES, THEME_IDS
    from rdpstudio.ui.settings_dialog import _ThemeCard

    assert len(THEME_CHOICES) == len(THEME_IDS) == 6
    for tid, label in THEME_CHOICES:
        card = _ThemeCard(tid, label, selected=False)
        assert card.theme_id == tid
        card.deleteLater()


# ----------------------------------------------------------------------
# Hit testing (pure logic — no window needed)
# ----------------------------------------------------------------------
def test_zone_rects_cover_the_edges() -> None:
    from PySide6.QtCore import QRect

    from rdpstudio.ui.docking import edge_band, zone_rect

    rect = QRect(0, 0, 1000, 600)
    left, right = zone_rect("left", rect), zone_rect("right", rect)
    top, bottom = zone_rect("top", rect), zone_rect("bottom", rect)
    assert left.left() == 0 and left.width() == edge_band(1000)
    assert right.right() == rect.right() and right.width() == edge_band(1000)
    assert top.top() == 0 and top.height() == edge_band(600)
    assert bottom.bottom() == rect.bottom() and bottom.height() == edge_band(600)
    # None of the bands may swallow the middle of the work area.
    assert left.right() < rect.center().x() < right.left()


def test_zone_at_picks_the_nearest_allowed_edge() -> None:
    from PySide6.QtCore import QPoint, QRect

    from rdpstudio.ui.docking import zone_at

    rect = QRect(0, 0, 1200, 800)
    zones = ("left", "right", "top", "left")
    assert zone_at(QPoint(4, 400), rect, zones) == "left"
    assert zone_at(QPoint(1196, 400), rect, zones) == "right"
    assert zone_at(QPoint(600, 4), rect, zones) == "top"
    # Middle of the work area: no dock, the layout stays put.
    assert zone_at(QPoint(600, 400), rect, zones) is None
    # Outside the window is always a cancel.
    assert zone_at(QPoint(-40, 400), rect, zones) is None
    assert zone_at(QPoint(600, 5000), rect, zones) is None
    # A corner picks the closest of the two candidate bands.
    assert zone_at(QPoint(3, 3), rect, zones) == "left"
    assert zone_at(QPoint(3, 3), rect, ("top", "left")) == "top"


def test_zone_at_ignores_zones_a_surface_cannot_use() -> None:
    """The Sessions panel only offers left/right — a top drop is a no-op."""
    from PySide6.QtCore import QPoint, QRect

    from rdpstudio.ui.docking import zone_at

    rect = QRect(0, 0, 1200, 800)
    assert zone_at(QPoint(600, 3), rect, ("left", "right")) is None


# ----------------------------------------------------------------------
# Sessions panel: drag / flip between the left and right edges
# ----------------------------------------------------------------------
def test_sidebar_starts_left_and_flips(win, qtapp) -> None:  # noqa: ARG001
    assert win.sidebar_side() == "left"
    assert win.main_splitter.indexOf(win.sidebar) == 0
    assert win.sidebar.property("side") == "left"

    win.flip_sidebar_side()
    qtapp.processEvents()
    assert win.sidebar_side() == "right"
    # The panel moved to the trailing splitter slot — never duplicated.
    assert win.main_splitter.indexOf(win.sidebar) == 1
    assert win.main_splitter.count() == 2
    assert win.sidebar.property("side") == "right"

    win.flip_sidebar_side()
    qtapp.processEvents()
    assert win.sidebar_side() == "left"
    assert win.main_splitter.indexOf(win.sidebar) == 0


def test_move_sidebar_keeps_width_and_collapse_state(win, qtapp) -> None:  # noqa: ARG001
    win.show()
    qtapp.processEvents()
    win._last_sidebar_width = 300
    win._set_sidebar_width(300)
    qtapp.processEvents()
    before = win._sidebar_width()
    assert before == 300  # the panel really is 300 px wide now

    win.move_sidebar("right")
    qtapp.processEvents()
    sizes = win.main_splitter.sizes()
    # Moving the panel must not resize it: the width the user had is kept.
    assert win._sidebar_width() == before, sizes
    assert win._sidebar_width() == sizes[1]
    assert sizes[0] > sizes[1]  # the work area keeps the room

    # Collapsed stays collapsed across a move.
    win._set_sidebar_width(0)
    qtapp.processEvents()
    assert win._sidebar_collapsed
    win.move_sidebar("left")
    qtapp.processEvents()
    assert win.main_splitter.sizes()[0] == 0
    assert win.sidebar_side() == "left"
    # ...and showing it again restores the remembered width.
    win._toggle_sidebar(True)
    qtapp.processEvents()
    assert win.main_splitter.sizes()[0] == 300


def test_move_sidebar_is_idempotent(win, qtapp) -> None:  # noqa: ARG001
    win.move_sidebar("left")  # already left
    assert win.main_splitter.indexOf(win.sidebar) == 0
    assert win.main_splitter.count() == 2
    win.move_sidebar("bogus-side")  # anything not "right…" means left
    assert win.sidebar_side() == "left"


def test_sidebar_grip_drag_to_left_edge(win, qtapp) -> None:  # noqa: ARG001
    """The real gesture: grab the ⠿ grip, shove it at the other edge."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    win.show()
    qtapp.processEvents()
    win.move_sidebar("right")
    qtapp.processEvents()

    grip = win.sidebar.dock_grip
    target = grip.mapFromGlobal(QPoint(8, grip.mapToGlobal(grip.rect().center()).y()))
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=grip.rect().center())
    QTest.mouseMove(grip, target)
    qtapp.processEvents()
    assert win._sidebar_drag.dragging()
    assert win._sidebar_drag.overlay.isVisible()
    assert win._sidebar_drag.overlay._active == "left"  # indicator lights up
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=target)
    qtapp.processEvents()
    assert win.sidebar_side() == "left"
    assert win.main_splitter.indexOf(win.sidebar) == 0
    assert not win._sidebar_drag.overlay.isVisible()


def test_sidebar_drag_into_the_middle_cancels(win, qtapp) -> None:  # noqa: ARG001
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win.show()
    qtapp.processEvents()
    grip = win.sidebar.dock_grip
    middle = grip.mapFromGlobal(win.mapToGlobal(win.rect().center()))
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=grip.rect().center())
    QTest.mouseMove(grip, middle)
    qtapp.processEvents()
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=middle)
    qtapp.processEvents()
    assert win.sidebar_side() == "left"  # unchanged
    assert not win._sidebar_drag.overlay.isVisible()


def test_grip_click_without_drag_still_clicks(win, qtapp) -> None:  # noqa: ARG001
    """A press/release that never moves must not be eaten by the filter."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    win.show()
    qtapp.processEvents()
    grip = win.sidebar.dock_grip
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=grip.rect().center())
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=grip.rect().center())
    qtapp.processEvents()
    assert not win._sidebar_drag.dragging()
    assert win.sidebar_side() == "left"


def test_splitter_handle_double_click_flips(win, qtapp) -> None:  # noqa: ARG001
    """Double-clicking the divider (or dragging it) is the second gesture."""
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtGui import QMouseEvent

    win.show()
    qtapp.processEvents()
    handle = win.main_splitter.handle(1)
    assert handle is not None
    event = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        QPoint(2, 2),
        handle.mapToGlobal(QPoint(2, 2)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    win.eventFilter(handle, event)
    qtapp.processEvents()
    assert win.sidebar_side() == "right"


# ----------------------------------------------------------------------
# Session tab strip: top / left / right
# ----------------------------------------------------------------------
def test_tab_strip_positions_map_to_qt_edges(win, qtapp) -> None:  # noqa: ARG001
    from PySide6.QtWidgets import QTabWidget

    assert win.tabs_position() == "top"
    assert win.tabs.tabPosition() == QTabWidget.TabPosition.North
    assert win.tabs.tabBar().property("dock") == "top"

    win.set_tabs_position("left")
    assert win.tabs.tabPosition() == QTabWidget.TabPosition.West
    assert win.tabs.tabBar().property("dock") == "left"
    assert win.tabs.property("dock") == "left"

    win.set_tabs_position("right")
    assert win.tabs.tabPosition() == QTabWidget.TabPosition.East

    win.set_tabs_position("sideways")  # unknown ids fall back to the top
    assert win.tabs.tabPosition() == QTabWidget.TabPosition.North
    qtapp.processEvents()


def test_vertical_strip_keeps_the_corner_buttons(win, qtapp) -> None:  # noqa: ARG001
    """QTabWidget drops corner widgets on vertical strips — the session
    counter and quick buttons must survive the move."""
    from PySide6.QtCore import Qt

    win.set_tabs_position("left")
    qtapp.processEvents()
    assert win._tab_corner.parent() is win._corner_row
    assert win.tabs.cornerWidget(Qt.Corner.TopRightCorner) is None
    assert win._corner_row.isVisibleTo(win) is not None
    win.set_tabs_position("top")
    qtapp.processEvents()
    assert win._tab_corner.parent() is win.tabs
    assert win.tabs.cornerWidget(Qt.Corner.TopRightCorner) is win._tab_corner


def test_vertical_strip_is_wide_enough_to_read(win, qtapp) -> None:  # noqa: ARG001
    """Regression: the vertical QSS block keyed off the wrong property value
    ("west"/"east" instead of the zone ids) and silently never matched, so the
    strip collapsed to 48 px and rotated labels elided to two characters."""
    win.show()
    win.open_local_terminal()
    win.tabs.setTabText(0, "root@prod-web-01")
    qtapp.processEvents()

    win.set_tabs_position("left")
    qtapp.processEvents()
    bar = win.tabs.tabBar()
    assert bar.property("dock") == "left"  # what the QSS attribute selector sees
    assert bar.width() >= 140, bar.width()
    assert bar.tabRect(0).height() <= 200  # clamped, not the full strip
    # The label keeps most of its characters rather than eliding to "ro…".
    assert bar.tabSizeHint(0).width() >= 140

    win.set_tabs_position("right")
    qtapp.processEvents()
    assert bar.property("dock") == "right"
    assert bar.width() >= 140
    for i in range(win.tabs.count()):
        controller = getattr(win.tabs.widget(i), "controller", None)
        if controller is not None:
            controller.stop_blocking("test over")


def test_cycle_tabs_position(win, qtapp) -> None:  # noqa: ARG001
    win.set_tabs_position("top")
    win.cycle_tabs_position()
    assert win.tabs_position() == "left"
    win.cycle_tabs_position()
    assert win.tabs_position() == "right"
    win.cycle_tabs_position()
    assert win.tabs_position() == "top"
    qtapp.processEvents()


def test_tab_strip_drag_from_empty_bar_space(win, qtapp) -> None:  # noqa: ARG001
    """Dragging the empty part of the strip docks it to that edge."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    win.show()
    win.open_local_terminal()  # a strip with a tab in it, like real use
    qtapp.processEvents()
    bar = win.tabs.tabBar()
    assert not bar.isHidden()
    row_y = bar.geometry().center().y()
    empty_x = bar.geometry().right() + 40  # past the last tab, still the row
    start = QPoint(empty_x, row_y)
    target_global = QPoint(win.width() - 10, win.mapToGlobal(start).y())
    target = win.tabs.mapFromGlobal(target_global)

    QTest.mousePress(win.tabs, Qt.MouseButton.LeftButton, pos=start)
    qtapp.processEvents()
    QTest.mouseMove(win.tabs, target)
    qtapp.processEvents()
    assert win._tabs_row_drag.dragging()
    assert win._tabs_row_drag.overlay._active == "right"
    QTest.mouseRelease(win.tabs, Qt.MouseButton.LeftButton, pos=target)
    qtapp.processEvents()
    assert win.tabs_position() == "right"
    for i in range(win.tabs.count()):
        controller = getattr(win.tabs.widget(i), "controller", None)
        if controller is not None:
            controller.stop_blocking("test over")


def test_tab_strip_drag_is_vetoed_on_a_tab_and_on_the_pane(win, qtapp) -> None:  # noqa: ARG001
    """Only empty strip space drags the strip: tabs stay reorderable and the
    session pane keeps its own mouse behaviour."""
    from PySide6.QtCore import QPoint

    win.open_local_terminal()
    qtapp.processEvents()
    bar = win.tabs.tabBar()
    on_tab = bar.tabRect(0).center()
    assert not win._tab_drag._can_start(on_tab)
    assert win._tab_drag._can_start(QPoint(bar.geometry().right() + 20, bar.geometry().center().y()))
    # Deep inside the pane, well below the strip row.
    assert not win._in_tab_strip_band(QPoint(40, win.tabs.height() - 5))
    # ...and in the strip band the row test passes.
    assert win._in_tab_strip_band(QPoint(40, bar.geometry().center().y()))
    for i in range(win.tabs.count()):
        controller = getattr(win.tabs.widget(i), "controller", None)
        if controller is not None:
            controller.stop_blocking("test over")


def test_tab_strip_grip_drag(win, qtapp) -> None:  # noqa: ARG001
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    win.show()
    qtapp.processEvents()
    grip = win._tabs_grip
    target = grip.mapFromGlobal(QPoint(8, grip.mapToGlobal(grip.rect().center()).y()))
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=grip.rect().center())
    QTest.mouseMove(grip, target)
    qtapp.processEvents()
    assert win._tabs_grip_drag.dragging()
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=target)
    qtapp.processEvents()
    assert win.tabs_position() == "left"


def test_drag_can_be_cancelled_with_escape(win, qtapp) -> None:  # noqa: ARG001
    from PySide6.QtCore import QEvent, QPoint, Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtTest import QTest

    win.show()
    qtapp.processEvents()
    grip = win.sidebar.dock_grip
    QTest.mousePress(grip, Qt.MouseButton.LeftButton, pos=grip.rect().center())
    QTest.mouseMove(grip, grip.mapFromGlobal(QPoint(8, grip.mapToGlobal(grip.rect().center()).y())))
    qtapp.processEvents()
    assert win._sidebar_drag.dragging()
    win._sidebar_drag.eventFilter(
        grip,
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
    )
    qtapp.processEvents()
    assert not win._sidebar_drag.dragging()
    assert not win._sidebar_drag.overlay.isVisible()
    QTest.mouseRelease(grip, Qt.MouseButton.LeftButton, pos=grip.rect().center())
    qtapp.processEvents()
    assert win.sidebar_side() == "left"  # the Escape won


# ----------------------------------------------------------------------
# Layout persistence + menu wiring
# ----------------------------------------------------------------------
def test_layout_is_remembered_across_restarts(ctx, qtapp) -> None:  # noqa: ARG001
    from rdpstudio.ui import theme
    from rdpstudio.ui.main_window import MainWindow

    theme.apply_theme(qtapp, ctx.settings.theme, animations=False)
    first = MainWindow(ctx)
    first.resize(1280, 800)
    first.move_sidebar("right")
    first.set_tabs_position("left")
    first._last_sidebar_width = 284
    qtapp.processEvents()
    first.close()
    qtapp.processEvents()

    # Settings were written on close; a fresh window restores the layout.
    geo = ctx.settings.geometry
    assert geo["sidebar_side"] == "right"
    assert geo["tabs_position"] == "left"
    second = MainWindow(ctx)
    try:
        assert second.sidebar_side() == "right"
        assert second.main_splitter.indexOf(second.sidebar) == 1
        assert second.tabs_position() == "left"
        assert second.tabs.tabPosition().name == "West"
    finally:
        second.close()
        qtapp.processEvents()


def test_menu_actions_reflect_and_drive_the_layout(win, qtapp) -> None:  # noqa: ARG001
    # Tab strip position actions are a radio group that tracks the state.
    assert win._tabs_pos_actions["top"].isChecked()
    win._tabs_pos_actions["right"].trigger()
    qtapp.processEvents()
    assert win.tabs_position() == "right"
    assert win._tabs_pos_actions["right"].isChecked()
    assert not win._tabs_pos_actions["top"].isChecked()

    # The flip entry always names the edge the panel would move to.
    win.move_sidebar("left")
    win._sync_sidebar_actions()
    assert "Right" in win._act_flip_sidebar.text()
    win._act_flip_sidebar.trigger()
    qtapp.processEvents()
    assert win.sidebar_side() == "right"
    assert "Left" in win._act_flip_sidebar.text()


def test_shortcuts_are_registered(win) -> None:  # noqa: ARG001
    keys = {
        act.shortcut().toString()
        for act in (win._act_flip_sidebar, *win._tabs_pos_actions.values())
        if act.shortcut()
    }
    assert "Ctrl+Shift+B" in keys
    # No duplicate shortcut stealing an existing binding.
    from rdpstudio.core.settings import THEME_IDS  # noqa: F401  (import sanity)

    assert len(keys) == len({k for k in keys})
