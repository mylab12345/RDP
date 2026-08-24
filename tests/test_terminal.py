"""Terminal emulation core: parsing, scrollback, selection, OSC 52, search."""

from rdpstudio.ui.terminal import TerminalCore, _seq_complete, encode_key_event


def test_basic_text():
    core = TerminalCore(cols=20, rows=5)
    core.feed(b"hello world")
    assert core.line_at(core.total_lines() - core.rows) == "hello world"


def test_wrap_and_scrollback():
    core = TerminalCore(cols=10, rows=3)
    core.feed("\r\n".join(f"line{i}" for i in range(1, 6)).encode())
    # rows=3 → lines 1..2 scrolled into history, 3..5 visible
    top = len(core.screen.history.top)
    assert top == 2
    assert core.line_at(0) == "line1"
    assert core.line_at(1) == "line2"
    assert core.line_at(2) == "line3"


def test_colors_and_attributes():
    core = TerminalCore()
    core.feed(b"\x1b[1;31mRED\x1b[0m plain")
    row = core.screen.buffer[0]
    assert row[0].data == "R"
    assert row[0].bold
    assert str(row[0].fg) == "red" or row[0].fg == "red"
    assert row[4].data == "p" and not row[4].bold


def test_osc52_clipboard():
    core = TerminalCore()
    import base64

    payload = base64.b64encode(b"hello clipboard").decode()
    text = core.feed(f"\x1b]52;c;{payload}\x07".encode())
    assert text == "hello clipboard"


def test_bracketed_paste_tracking():
    core = TerminalCore()
    core.feed(b"\x1b[?2004h")
    assert core.bracketed_paste is True
    core.feed(b"\x1b[?2004l")
    assert core.bracketed_paste is False


def test_partial_escape_tail_held_back():
    core = TerminalCore()
    core.feed(b"abc\x1b[3")
    assert core.line_at(core.total_lines() - core.rows) == "abc"
    core.feed(b"~")
    # the completed DEL sequence was applied, not printed
    assert core.screen.cursor.x == 3


def test_selection_text():
    core = TerminalCore(cols=20, rows=5)
    core.feed(b"alpha beta\r\ngamma delta")
    top = len(core.screen.history.top)
    text = core.selection_text((top, 6), (top + 1, 10))
    assert text == "beta\ngamma delta"


def test_resize():
    core = TerminalCore(cols=10, rows=5)
    core.feed(b"0123456789")
    core.resize(20, 10)
    assert (core.cols, core.rows) == (20, 10)


def test_find():
    core = TerminalCore(cols=20, rows=4)
    core.feed(b"one\r\ntwo\r\nthree")
    pos = core.find_text("two")
    assert pos is not None and core.line_at(pos[0]).startswith("two")


def test_seq_complete():
    assert _seq_complete(b"\x1b[31m")
    assert not _seq_complete(b"\x1b[31")
    assert _seq_complete(b"\x1b]0;title\x07")
    assert not _seq_complete(b"\x1b]0;titl")


# ---- key encoding --------------------------------------------------------
class _FakeScreen:
    def __init__(self, app_cursor=False):
        self.mode = {1 << 5} if app_cursor else set()  # DECCKM as pyte stores it


class _FakeEvent:
    def __init__(self, key, text="", ctrl=False, alt=False, shift=False):
        from PySide6.QtCore import Qt

        mods = Qt.KeyboardModifier.NoModifier
        if ctrl:
            mods |= Qt.KeyboardModifier.ControlModifier
        if alt:
            mods |= Qt.KeyboardModifier.AltModifier
        if shift:
            mods |= Qt.KeyboardModifier.ShiftModifier
        self._key, self._text, self._mods = key, text, mods

    def key(self):
        return self._key

    def text(self):
        return self._text

    def modifiers(self):
        return self._mods


def test_native_palette_is_vga_and_ignores_theme(qtapp):
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.terminal import TerminalView

    settings = Settings(theme="light")
    term = TerminalView(settings, native_colors=True)
    pal = term._palette()
    assert pal["bg"].name().lower() == "#000000"
    settings.theme = "sunset"
    pal2 = term._palette()
    assert pal2 is pal  # cache key is "native", not the workbench theme
    term.deleteLater()


def test_key_encoding():
    from PySide6.QtCore import Qt

    assert encode_key_event(_FakeEvent(Qt.Key.Key_A, "a"), _FakeScreen()) == b"a"
    assert encode_key_event(_FakeEvent(Qt.Key.Key_A, "\x01", ctrl=True), _FakeScreen()) == b"\x01"
    assert encode_key_event(
        _FakeEvent(Qt.Key.Key_Up, "", ctrl=True), _FakeScreen()
    ) == b"\x1b[1;5A"
    assert encode_key_event(
        _FakeEvent(Qt.Key.Key_Up, ""), _FakeScreen(app_cursor=True)
    ) == b"\x1bOA"
    assert encode_key_event(_FakeEvent(Qt.Key.Key_Return, "\r"), _FakeScreen()) == b"\r"
    assert encode_key_event(_FakeEvent(Qt.Key.Key_F5, ""), _FakeScreen()) == b"\x1b[15~"
    assert encode_key_event(_FakeEvent(Qt.Key.Key_F5, "", ctrl=True), _FakeScreen()) == b"\x1b[15;5~"
    assert encode_key_event(_FakeEvent(Qt.Key.Key_Delete, ""), _FakeScreen()) == b"\x1b[3~"
    assert encode_key_event(_FakeEvent(Qt.Key.Key_Backspace, "\x7f"), _FakeScreen()) == b"\x7f"
    assert encode_key_event(_FakeEvent(Qt.Key.Key_B, "b", alt=True), _FakeScreen()) == b"\x1bb"


# ----------------------------------------------------------------------
# Modern TUI compatibility (opencode / helix / zellij / ratatui / crossterm)
# ----------------------------------------------------------------------
# These toolkits emit 24-bit color with colon sub-parameters
# (``ESC[38:2:R:G:Bm``) instead of the legacy semicolon form that pyte
# parses natively.  pyte would otherwise drop the SGR and leak the raw
# parameter bytes onto the screen.

def test_colon_truecolor_foreground():
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[38:2:40:44:52mhello")
    assert core.screen.buffer[0][0].fg == "282c34"
    line = core.line_at(core.total_lines() - core.rows)
    assert "2:" not in line and "m" not in line.replace("hello", "")


def test_colon_truecolor_background():
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[48:2:97:175:239mworld")
    assert core.screen.buffer[0][0].bg == "61afef"


def test_colon_truecolor_empty_colorspace():
    # ``38:2::R:G:B`` form (empty color-space id).
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[38:2::40:44:52mX")
    assert core.screen.buffer[0][0].fg == "282c34"


def test_colon_truecolor_fg_and_bg_in_one_sgr():
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[48:2:97:175:239;38:2:0:0:0mhi")
    cell = core.screen.buffer[0][0]
    assert cell.bg == "61afef"
    assert cell.fg == "000000"


def test_colon_256color_palette():
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[38:5:200mX")
    # xterm-256 colour index 200 is 0xff00d7.
    assert core.screen.buffer[0][0].fg == "ff00d7"


def test_semicolon_truecolor_still_works():
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[38;2;40;44;52mX")
    assert core.screen.buffer[0][0].fg == "282c34"


def test_colon_truecolor_split_across_chunks():
    # A color SGR split mid-sequence by the transport must reassemble, not
    # leak a half-parsed sequence as text.
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[2J\x1b[H\x1b[48:2:97:175")
    core.feed(b":239mSPLIT")
    row = core.screen.buffer[0]
    assert row[0].bg == "61afef"
    assert "".join(row[x].data for x in range(5)) == "SPLIT"


def test_no_inline_parameter_garbage():
    # The exact "weird screen" symptom: leftover ``2:..:..m`` must not print.
    core = TerminalCore(cols=30, rows=3)
    core.feed(b"\x1b[48:2:97:175:239mHELLO")
    line = core.line_at(core.total_lines() - core.rows)
    assert line.strip() == "HELLO"


def test_synchronized_output_stripped():
    core = TerminalCore(cols=20, rows=2)
    core.feed(b"\x1b[?2026hSYNC\x1b[?2026l")
    line = core.line_at(core.total_lines() - core.rows)
    assert "2026" not in line
    assert "SYNC" in line


def test_osc8_hyperlink_uri_stripped():
    core = TerminalCore(cols=40, rows=2)
    core.feed(b"\x1b]8;;https://example.com\x07click here\x1b]8;;\x07")
    line = core.line_at(core.total_lines() - core.rows)
    assert "https" not in line
    assert "click here" in line


def test_private_mode_csi_not_mangled():
    # Alternate-screen / bracketed-paste toggles must pass through untouched
    # (the SGR normalizer must never rewrite '?' private-mode sequences).
    core = TerminalCore(cols=20, rows=3)
    core.feed(b"\x1b[?1049h\x1b[2J\x1b[H\x1b[?2004hOK")
    assert core.bracketed_paste is True  # tracked by TerminalCore
    assert core.screen.buffer[0][0].data == "O"
    assert core.screen.buffer[0][1].data == "K"


def test_mixed_sgr_and_cursor_csi_unaffected():
    # Cursor positioning with semicolons (no colons) must be left intact,
    # and a colon-truecolor SGR later in the stream must still normalize.
    core = TerminalCore(cols=20, rows=12)
    core.feed(b"\x1b[10H\x1b[38:2:10:20:30mX")
    # ESC[10H is row 10 (1-based) -> buffer row 9 (0-based), col 0.
    assert core.screen.buffer[9][0].data == "X"
    assert core.screen.buffer[9][0].fg == "0a141e"
