"""Tests for the 2026 UI polish layer: fuzzy palette, tinted icons, density
settings, high-contrast theme and the new motion helpers."""

from __future__ import annotations


# ----------------------------------------------------------------------
# Command palette fuzzy ranker
# ----------------------------------------------------------------------
def test_fuzzy_score_requires_subsequence() -> None:
    from rdpstudio.core.fuzzy import fuzzy_score

    assert fuzzy_score("abc", "xabc") > 0
    assert fuzzy_score("acb", "abc") == 0  # order matters
    assert fuzzy_score("zz", "abc") == 0
    assert fuzzy_score("abx", "ab") == 0  # needle longer than text


def test_fuzzy_score_rewards_early_consecutive_matches() -> None:
    from rdpstudio.core.fuzzy import fuzzy_score

    # "nw" starts "Network" — must beat the deep, scattered hit in "Session".
    assert fuzzy_score("nw", "Network Tools & Port Scanner") > fuzzy_score("nw", "Session")
    # Consecutive + word-boundary beats a late, non-boundary match.
    assert fuzzy_score("se", "Settings…") > fuzzy_score("se", "imported session")
    # Empty needle matches everything (used for the default listing).
    assert fuzzy_score("", "anything") == 1


def test_palette_lists_menu_actions_and_recents(home, qtapp) -> None:  # noqa: ARG001
    """The palette must expose real menu actions and a no-match state."""
    from rdpstudio.app import build_context
    from rdpstudio.ui import theme
    from rdpstudio.ui.command_palette import CommandPaletteDialog
    from rdpstudio.ui.main_window import MainWindow

    ctx = build_context()
    theme.apply_theme(qtapp, ctx.settings.theme, animations=False)
    win = MainWindow(ctx)
    try:
        dlg = CommandPaletteDialog(win)
        menu_items = [i for i in dlg._items if i.category.startswith("Menu ·")]
        assert menu_items, "menu actions should be palette items"
        # Every menu item must carry a callable action.
        for item in menu_items:
            assert callable(item.action)
        dlg._populate_list("qqqq-no-such-command")
        assert dlg.list.count() == 1
        assert dlg.list.item(0).text().startswith("No matching")
        dlg.close()
    finally:
        win.close()
        qtapp.processEvents()


# ----------------------------------------------------------------------
# Icon tinting + badges
# ----------------------------------------------------------------------
def _average_opaque_color(pixmap) -> tuple[int, int, int]:
    """Average color over the fully-opaque pixels (skips AA fringe)."""
    from PySide6.QtGui import QImage

    # ARGB32 keeps the alpha channel — RGB32 would fake alpha 255 for every
    # pixel (turning transparent areas into black and skewing the average).
    img = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    rs = gs = bs = n = 0
    for x in range(0, img.width(), 2):
        for y in range(0, img.height(), 2):
            r, g, b, a = img.pixelColor(x, y).getRgb()
            if a > 200:
                rs += r
                gs += g
                bs += b
                n += 1
    if n == 0:
        return (0, 0, 0)
    return (rs // n, gs // n, bs // n)


def test_icon_tint_recolors_svg(qtapp) -> None:  # noqa: ARG001
    from PySide6.QtCore import QSize

    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "midnight", animations=False)
    default = _average_opaque_color(theme.icon("server").pixmap(QSize(24, 24)))
    red = _average_opaque_color(theme.icon("server", tint="#ff0000").pixmap(QSize(24, 24)))
    white = _average_opaque_color(theme.icon("stop", tint="#ffffff").pixmap(QSize(24, 24)))
    # Red tint must actually be red…
    assert red[0] >= 200 and red[1] <= 90 and red[2] <= 90
    # …and differ from the default (theme fg_dim gray) rendering.
    assert red != default
    # White tint for icons placed on accent backgrounds.
    assert min(white) >= 220


def test_badge_icon_renders(qtapp) -> None:  # noqa: ARG001
    from PySide6.QtCore import QSize

    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "midnight", animations=False)
    badge = theme.badge_icon("terminal")
    assert not badge.isNull()
    pm = badge.pixmap(QSize(16, 16))
    assert not pm.isNull()


# ----------------------------------------------------------------------
# Settings: new appearance fields + high-contrast theme
# ----------------------------------------------------------------------
def test_settings_new_fields_defaults_and_coercion() -> None:
    from rdpstudio.core.settings import DARK_THEMES, THEME_IDS, Settings

    s = Settings()
    assert s.density == "comfortable"
    assert s.toolbar_labels is True
    assert s.animations is True
    assert s.palette_recents == []

    s2 = Settings.from_dict(
        {
            "density": "bogus",
            "toolbar_labels": "yes",
            "animations": None,
            "palette_recents": ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
            "theme": "contrast",
            "font_size": 99,
        }
    )
    assert s2.density == "comfortable"  # unknown value falls back
    assert s2.toolbar_labels is True
    assert s2.animations is False
    assert len(s2.palette_recents) == 8  # capped
    assert s2.palette_recents[0] == "a"
    assert s2.theme == "contrast"

    # High-contrast palette must be a registered, dark theme.
    assert "contrast" in THEME_IDS
    assert "contrast" in DARK_THEMES


def test_contrast_palette_applies_without_keyerror(qtapp) -> None:  # noqa: ARG001
    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "contrast", animations=False)
    assert theme.current_theme() == "contrast"
    pal = theme.palette()
    assert pal["fg"] == "#ffffff"
    assert pal["term_bg"] == "#000000"
    assert "qlineargradient" in pal["accent_gradient"]
    # And every other palette must expose the same key (QSS .format safety).
    from rdpstudio.core.settings import THEME_IDS

    for tid in THEME_IDS:
        theme.apply_theme(qtapp, tid, animations=False)
        assert "accent_gradient" in theme.palette()


def test_density_switches_compact_qss(qtapp) -> None:  # noqa: ARG001
    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "midnight", density="comfortable", animations=False)
    comfy_qss = qtapp.styleSheet()
    theme.apply_theme(qtapp, "midnight", density="compact", animations=False)
    compact_qss = qtapp.styleSheet()
    assert theme.current_density() == "compact"
    assert len(compact_qss) > len(comfy_qss)  # compact block appended
    theme.apply_theme(qtapp, "midnight", density="comfortable", animations=False)


def test_motion_helpers_respect_settings(qtapp) -> None:  # noqa: ARG001
    from PySide6.QtWidgets import QLabel

    from rdpstudio.ui import theme
    from rdpstudio.ui.widgets import animate_in, pulse, soft_shadow

    label = QLabel("x")
    theme.apply_theme(qtapp, "midnight", animations=False)
    assert theme.MOTIONS_ENABLED is False
    animate_in(label)
    pulse(label)
    assert label.graphicsEffect() is None  # skipped entirely
    soft_shadow(label)
    assert label.graphicsEffect() is not None  # shadows are not motion
    label.setGraphicsEffect(None)

    theme.apply_theme(qtapp, "midnight", animations=True)
    assert theme.MOTIONS_ENABLED is True
    label2 = QLabel("y")
    animate_in(label2)
    assert label2.graphicsEffect() is not None  # fade actually attached
    while label2.graphicsEffect() is not None:
        qtapp.processEvents()


# ----------------------------------------------------------------------
# MobaXterm look — default theme, coloured toolbar glyphs, sidebar rail
# ----------------------------------------------------------------------
def test_mobaxterm_dark_is_default_theme() -> None:
    from rdpstudio.core.settings import DARK_THEMES, THEME_IDS, Settings
    from rdpstudio.ui import theme

    assert "mobaxterm_dark" in THEME_IDS and "mobaxterm" in THEME_IDS
    assert DARK_THEMES == {"mobaxterm_dark", "midnight", "dracula", "ocean", "contrast"}
    assert Settings().theme == "mobaxterm_dark"
    assert Settings.from_dict({"theme": "bogus"}).theme == "mobaxterm_dark"
    pal = theme.PALETTE["mobaxterm_dark"]
    # MobaXterm signature colours, lights off: charcoal chrome, Windows blue
    # accent (deepened so white button text meets WCAG AA).
    assert pal["bg"].lower() == "#1c1c1f"
    assert pal["accent"].lower() == "#1670c6"
    # The classic light chrome is still shipped and still MobaXterm.
    light = theme.PALETTE["mobaxterm"]
    assert light["bg"].lower() == "#f0f0f0"
    assert light["accent"].lower() == "#0075d2"


def test_toolbar_icons_are_tinted_per_action(qtapp) -> None:  # noqa: ARG001
    from PySide6.QtCore import QSize

    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    green = _average_opaque_color(theme.toolbar_icon("plus").pixmap(QSize(24, 24)))
    red = _average_opaque_color(theme.toolbar_icon("close").pixmap(QSize(24, 24)))
    assert green[1] > green[0] and green[1] > green[2]  # "Session" is green
    assert red[0] > red[1] and red[0] > red[2]  # "Close all" is red


def test_qss_uses_consistent_design_scale(qtapp) -> None:  # noqa: ARG001
    """Round 7: the ops-console design system ships a 4/6/8/10 px radius
    scale (pills 999 px) — no ad-hoc large radii in the global sheet."""
    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    qss = qtapp.styleSheet()
    assert "QToolBar#moxaToolbar" in qss
    assert "QTabBar#sideRail" in qss
    assert "border-radius: 6px" in qss  # controls (buttons, inputs, tabs)
    assert "border-radius: 8px" in qss  # cards, menus
    assert "border-radius: 999px" in qss  # pills
    # Nothing in the global sheet rounds past the 10 px floating-surface step.
    for radius in ("12px", "14px", "16px", "20px", "24px"):
        assert f"border-radius: {radius}" not in qss, radius


def test_sidebar_has_rail_and_pages(home, qtapp) -> None:
    from rdpstudio.core.store import SessionStore
    from rdpstudio.ui import theme
    from rdpstudio.ui.sidebar import SessionTree

    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    sb = SessionTree(SessionStore(home / "sessions.json"))
    assert sb.rail.count() == 2 and sb.pages.count() == 2
    assert sb.rail.tabText(0) == "Sessions"
    sb.rail.setCurrentIndex(1)
    assert sb.pages.currentIndex() == 1
    sb.close()


def _wcag_ratio(a: str, b: str) -> float:
    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def lum(h: str) -> float:
        h = h.lstrip("#")
        r, g, bl = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(bl)

    hi, lo = max(lum(a), lum(b)), min(lum(a), lum(b))
    return (hi + 0.05) / (lo + 0.05)


def test_all_palettes_meet_wcag_aa() -> None:
    """Round 5: secondary text >= 4.5, accent buttons >= 4.5, accents >= 3:1."""
    from rdpstudio.ui.theme_palettes import PALETTE

    for tid, pal in sorted(PALETTE.items()):
        assert _wcag_ratio(pal["fg_muted"], pal["bg3"]) >= 4.5, f"{tid} muted"
        assert _wcag_ratio(pal["accent_text"], pal["accent"]) >= 4.5, f"{tid} button"
        assert _wcag_ratio(pal["accent"], pal["bg"]) >= 3.0, f"{tid} accent"


def test_keyboard_focus_rings_in_stylesheet(qtapp) -> None:  # noqa: ARG001
    """Round 5: every focusable chrome family has a visible focus rule."""
    from rdpstudio.ui import theme

    for tid in ("mobaxterm", "midnight", "contrast"):
        theme.apply_theme(qtapp, tid, animations=False)
        qss = qtapp.styleSheet()
        assert "QTabBar:focus" in qss, tid
        assert "QTreeView:focus" in qss, tid
        assert "QPushButton:focus" in qss, tid
        assert "QLineEdit:focus" in qss, tid
        assert "QToolButton:focus" in qss, tid
    theme.apply_theme(qtapp, "mobaxterm", animations=False)


def test_data_tables_use_alternating_rows(home, qtapp) -> None:  # noqa: ARG001
    """Round 6: readability striping on data tables (display-only)."""
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.cluster_dialog import ClusterDialog
    from rdpstudio.ui.network_tools_dialog import NetworkToolsDialog
    from rdpstudio.ui.sftp_dialog import _Pane

    assert _Pane("LOCAL", False).list.alternatingRowColors()
    assert NetworkToolsDialog(main_window=None).table.alternatingRowColors()
    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=None,
    )
    cluster = ClusterDialog(ctx)
    assert cluster.host_tree.alternatingRowColors()
    assert cluster.results_table.alternatingRowColors()
    cluster.close()


def test_table_grid_and_splitter_pressed_in_stylesheet(qtapp) -> None:  # noqa: ARG001
    """Round 6: calm gridlines + pressed splitter feedback in every theme."""
    from rdpstudio.ui import theme

    for tid in ("mobaxterm", "midnight", "contrast"):
        theme.apply_theme(qtapp, tid, animations=False)
        qss = qtapp.styleSheet()
        assert "gridline-color" in qss, tid
        assert "alternate-background-color" in qss, tid
        assert "QSplitter::handle:pressed" in qss, tid
    theme.apply_theme(qtapp, "mobaxterm", animations=False)


def test_midnight_theme_registered_and_distinct(qtapp) -> None:  # noqa: ARG001
    """New theme ships registered, dark-classified, and visually distinct."""
    from rdpstudio.core.settings import DARK_THEMES, THEME_IDS, Settings
    from rdpstudio.ui import theme

    assert "midnight" in THEME_IDS and "midnight" in DARK_THEMES
    assert Settings().theme == "mobaxterm_dark"  # default (MobaXterm Dark)
    assert len(theme.PALETTE["midnight"]) == 30  # full key set, no fallback gaps
    theme.apply_theme(qtapp, "midnight", animations=False)
    assert qtapp.styleSheet()
    assert theme.PALETTE["midnight"]["bg"] != theme.PALETTE["mobaxterm"]["bg"]
    theme.apply_theme(qtapp, "mobaxterm", animations=False)


# ----------------------------------------------------------------------
# Round 7 — ops-console design system: focus rings, pills, dashboard,
# sidebar empty states
# ----------------------------------------------------------------------
def test_focus_rings_use_visible_outline(qtapp) -> None:
    """Every interactive family gets a 2 px accent outline, not a
    border-only recolor, and the global sheet no longer kills outlines."""
    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    qss = qtapp.styleSheet()
    accent = theme.palette()["accent"]
    assert f"outline: 2px solid {accent}" in qss
    for sel in (
        "QPushButton:focus",
        "QLineEdit:focus",
        "QToolButton:focus",
        "QTabBar:focus",
        "QTreeView:focus",
    ):
        assert sel in qss, sel


def test_state_chips_and_badges_are_pills(qtapp) -> None:  # noqa: ARG001
    from rdpstudio.ui.widgets import PillBadge, StateChip

    chip = StateChip("connected", "good")
    assert "border-radius: 999px" in chip.styleSheet()
    pill = PillBadge("5", "accent")
    assert "border-radius: 999px" in pill.styleSheet()


def test_dashboard_has_hero_quick_connect(home, qtapp) -> None:  # noqa: ARG001
    """The welcome page offers a prominent quick-connect field wired to the
    same parse/connect path as the toolbar one."""
    from rdpstudio.app import build_context
    from rdpstudio.ui import theme
    from rdpstudio.ui.main_window import MainWindow

    ctx = build_context()
    theme.apply_theme(qtapp, ctx.settings.theme, animations=False)
    win = MainWindow(ctx)
    try:
        # The dashboard is the current "empty" page; the input is owned by
        # the window (DashboardMixin) so toolbar and dashboard share one
        # quick-connect code path.
        assert win._empty is not None
        quick = getattr(win, "dash_quick", None)
        assert quick is not None, "dashboard quick-connect input missing"
        assert quick.objectName() == "dashQuick"
        assert "3389" in quick.placeholderText()
    finally:
        win.close()
        qtapp.processEvents()


def test_sidebar_empty_states_toggle(home, qtapp) -> None:  # noqa: ARG001
    """No saved sessions → friendly empty state with an action; adding one
    brings the tree back; a dead search shows the no-match state."""
    from rdpstudio.core.models import PROTOCOL_SSH, Session
    from rdpstudio.core.store import SessionStore
    from rdpstudio.ui import theme
    from rdpstudio.ui.sidebar import SessionTree

    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    store = SessionStore(home / "sessions.json")
    sb = SessionTree(store)
    # The tree is never shown in this test, so assert on the widgets' own
    # visibility flags (isHidden) rather than isVisible (parent-chain).
    try:
        assert not sb._empty_state.isHidden()
        assert sb.tree.isHidden()
        store.upsert(Session(name="prod", protocol=PROTOCOL_SSH, host="10.0.0.1"))
        sb.reload()
        assert not sb.tree.isHidden()
        assert sb._empty_state.isHidden()
        # dead search → no-match state instead of a bare empty tree
        sb._filter = "zzzz-no-match"
        sb.reload()
        assert not sb._no_match_state.isHidden()
        assert sb.tree.isHidden()
        sb._filter = ""
        sb.reload()
        assert not sb.tree.isHidden()
        assert sb._no_match_state.isHidden()
    finally:
        sb.close()
        qtapp.processEvents()


def test_protocol_badges_use_tinted_tiles(qtapp) -> None:  # noqa: ARG001
    """Badges render the protocol hue in the tile AND the glyph — not a
    neutral gray tile with a colored glyph."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QColor

    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "mobaxterm", animations=False)
    pal = theme.palette()
    ssh = _average_opaque_color(theme.protocol_badge("ssh", "terminal").pixmap(QSize(16, 16)))
    green = QColor(pal["good"]).getRgb()[:3]
    # The average over a tinted tile + glyph should lean toward the protocol hue.
    assert ssh[1] > ssh[0], f"ssh badge not green-leaning: {ssh}"
    assert abs(ssh[0] - green[0]) < 120
