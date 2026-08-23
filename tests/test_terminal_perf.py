"""Terminal performance: dirty-row tracking, partial repaint correctness,
render caches — the fixes that speed up Linux VM sessions."""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.usefixtures("home")


def _view(app, width=1200, height=800):
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.terminal import TerminalView

    tv = TerminalView(Settings())
    tv.resize(width, height)
    tv.show()
    time.sleep(0.06)
    app.processEvents()  # let the 40 ms resize debounce apply
    tv._relayout()
    tv._blink_timer.stop()
    tv._blink_state = True  # deterministic cursor for image comparison
    return tv


def _settle(app):
    for _ in range(6):
        time.sleep(0.004)
        app.processEvents()


_BLOB = (
    "".join(
        f"\x1b[1;34mLOG-{i:03d}\x1b[0m colored \x1b[31merror\x1b[0m plain text {i}\r\n"
        for i in range(40)
    )
    + "".join(f"prompt$ \x1b[1mbold \x1b[4munder \x1b[7mrev\x1b[0m tail {i}\r\n" for i in range(30))
).encode()


def test_core_drain_changed_rows(qtapp):
    from rdpstudio.ui.terminal import TerminalCore

    core = TerminalCore(cols=80, rows=24)
    core.feed(b"hello world\r\n")
    changed = core.drain_changed_rows()
    assert changed, "feed must report changed screen rows"
    assert 0 in changed  # first line
    assert core.drain_changed_rows() == set(), "drain must consume the set"


def test_core_changed_rows_cover_scroll(qtapp):
    """A scroll shifts the whole screen: every row must be reported dirty."""
    from rdpstudio.ui.terminal import TerminalCore

    core = TerminalCore(cols=80, rows=5)
    for i in range(10):
        core.feed(f"line {i}\r\n".encode())
    before = len(core.screen.history.top)
    core.feed(b"one more\r\n")
    changed = core.drain_changed_rows()
    after = len(core.screen.history.top)
    if after > before:
        assert changed == set(range(5)), "scroll must dirty every screen row"


def test_partial_repaint_matches_full_repaint(qtapp):
    a = _view(qtapp)
    b = _view(qtapp)
    a.feed(_BLOB)
    b.feed(_BLOB)
    a.update()
    b.update()
    _settle(qtapp)
    assert a.grab().toImage() == b.grab().toImage(), "baseline must match"

    # incremental output: b only repaints its dirty rows
    step = b"new line from remote \x1b[1;32mOK\x1b[0m 12345\r\n"
    a.feed(step)
    b.feed(step)
    _settle(qtapp)
    a.update()  # a additionally gets a full invalidation = full-repaint reference
    _settle(qtapp)
    assert a.grab().toImage() == b.grab().toImage(), (
        "dirty-row partial repaint differs from full repaint"
    )
    a.deleteLater()
    b.deleteLater()


def test_scrolled_back_output_matches_full_repaint(qtapp):
    a = _view(qtapp)
    b = _view(qtapp)
    a.feed(_BLOB)
    b.feed(_BLOB)
    a.update()
    b.update()
    _settle(qtapp)
    a.scroll_lines(15)
    b.scroll_lines(15)
    _settle(qtapp)
    a.feed(b"more output while scrolled back\r\n")
    b.feed(b"more output while scrolled back\r\n")
    _settle(qtapp)
    a.update()
    _settle(qtapp)
    assert a.grab().toImage() == b.grab().toImage(), (
        "scrolled-back output must repaint the whole viewport"
    )
    a.deleteLater()
    b.deleteLater()


def test_cursor_move_without_content_repaints_both_cells(qtapp):
    a = _view(qtapp)
    b = _view(qtapp)
    a.feed(b"hello\r\n")
    b.feed(b"hello\r\n")
    a.update()
    b.update()
    _settle(qtapp)
    assert a.grab().toImage() == b.grab().toImage()

    # plain cursor addressing: no content changes, only the cursor moves
    a.feed(b"\x1b[1;1H")
    b.feed(b"\x1b[1;1H")
    _settle(qtapp)
    a.update()
    _settle(qtapp)
    assert a.grab().toImage() == b.grab().toImage(), (
        "cursor-only move must repaint old and new cursor cells"
    )
    a.deleteLater()
    b.deleteLater()


def test_full_screen_tui_redraw_matches(qtapp):
    a = _view(qtapp)
    b = _view(qtapp)
    a.feed(b"hello\r\n")
    b.feed(b"hello\r\n")
    a.update()
    b.update()
    _settle(qtapp)
    tui = b"\x1b[2J" + b"".join(
        b"\x1b[%d;1Hline %d \x1b[1;33mxx\x1b[0m\r\n" % (i, i) for i in range(1, 25)
    )
    a.feed(tui)
    b.feed(tui)
    _settle(qtapp)
    a.update()
    _settle(qtapp)
    assert a.grab().toImage() == b.grab().toImage(), "TUI full-screen redraw mismatch"
    a.deleteLater()
    b.deleteLater()


def test_runs_cache_reused_for_unchanged_rows(qtapp):
    tv = _view(qtapp)
    tv.feed(b"row one\r\nrow two\r\n")
    _settle(qtapp)
    tv.update()
    _settle(qtapp)
    cached = len(tv._runs_cache)
    assert cached > 0, "stable rows should be style-run cached"

    # feed more output: only new rows are dirty, old rows keep their cache
    old_ids = {k: v[1] for k, v in tv._runs_cache.items()}
    tv.feed(b"row three\r\n")
    _settle(qtapp)
    for row, line_id in old_ids.items():
        entry = tv._runs_cache.get(row)
        if entry is not None:
            assert entry[1] == line_id, "unchanged row should keep its cached runs"
    tv.deleteLater()


def test_theme_change_invalidates_caches(qtapp):
    tv = _view(qtapp)
    tv.feed(b"\x1b[1;31mred text\x1b[0m plain\r\n")
    _settle(qtapp)
    tv.update()
    _settle(qtapp)
    gen = tv._palette_gen
    assert tv._palette_gen == gen

    tv.settings.theme = "light" if tv.settings.theme == "dark" else "dark"
    tv.update()
    _settle(qtapp)
    assert tv._palette_gen == gen + 1, "palette bump must invalidate caches"
    # after the repaint, any cached rows belong to the *new* palette generation
    for row, (row_gen, _line_id, _runs) in tv._runs_cache.items():
        assert row_gen == tv._palette_gen, f"row {row} kept stale runs"
    tv.deleteLater()
