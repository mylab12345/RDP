"""Tests for the 2026 UI polish layer: fuzzy palette, tinted icons, density
settings, high-contrast theme and the new motion helpers."""

from __future__ import annotations


# ----------------------------------------------------------------------
# Command palette fuzzy ranker
# ----------------------------------------------------------------------
def test_fuzzy_score_requires_subsequence() -> None:
    from rdpstudio.ui.command_palette import fuzzy_score

    assert fuzzy_score("abc", "xabc") > 0
    assert fuzzy_score("acb", "abc") == 0  # order matters
    assert fuzzy_score("zz", "abc") == 0
    assert fuzzy_score("abx", "ab") == 0  # needle longer than text


def test_fuzzy_score_rewards_early_consecutive_matches() -> None:
    from rdpstudio.ui.command_palette import fuzzy_score

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

    theme.apply_theme(qtapp, "dark", animations=False)
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

    theme.apply_theme(qtapp, "dark", animations=False)
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

    theme.apply_theme(qtapp, "dark", density="comfortable", animations=False)
    comfy_qss = qtapp.styleSheet()
    theme.apply_theme(qtapp, "dark", density="compact", animations=False)
    compact_qss = qtapp.styleSheet()
    assert theme.current_density() == "compact"
    assert len(compact_qss) > len(comfy_qss)  # compact block appended
    theme.apply_theme(qtapp, "dark", density="comfortable", animations=False)


def test_motion_helpers_respect_settings(qtapp) -> None:  # noqa: ARG001
    from PySide6.QtWidgets import QLabel

    from rdpstudio.ui import theme
    from rdpstudio.ui.widgets import animate_in, pulse, soft_shadow

    label = QLabel("x")
    theme.apply_theme(qtapp, "dark", animations=False)
    assert theme.MOTIONS_ENABLED is False
    animate_in(label)
    pulse(label)
    assert label.graphicsEffect() is None  # skipped entirely
    soft_shadow(label)
    assert label.graphicsEffect() is not None  # shadows are not motion
    label.setGraphicsEffect(None)

    theme.apply_theme(qtapp, "dark", animations=True)
    assert theme.MOTIONS_ENABLED is True
    label2 = QLabel("y")
    animate_in(label2)
    assert label2.graphicsEffect() is not None  # fade actually attached
    while label2.graphicsEffect() is not None:
        qtapp.processEvents()
