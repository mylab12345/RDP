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


# ---- color fidelity for rich TUIs (opencode, lazygit, …) ------------------
def test_truecolor_and_256_sgr_resolve_to_rgb(qtapp):
    """pyte reports extended colors as '#'-less hex; the painter must honor it."""
    from PySide6.QtGui import QColor

    from rdpstudio.ui.terminal import _colors_for

    core = TerminalCore()
    core.feed(b"\x1b[38;2;103;226;249mRGB\x1b[0m \x1b[38;5;45mX\x1b[0m")
    row = core.screen.buffer[0]
    assert str(row[0].fg) == "67e2f9"  # 24-bit RGB, stored without '#'
    assert str(row[4].fg) == "00d7ff"  # 256-color idx 45, normalized to hex

    pal = {"fg": QColor("#aaaaaa"), "bg": QColor("#000000"), "16": [], "named": {}}
    fg, _ = _colors_for("67e2f9", "default", False, pal)
    assert fg.name() == "#67e2f9"
    fg, _ = _colors_for("00d7ff", "default", False, pal)
    assert fg.name() == "#00d7ff"
    # bg works the same way (48;2 / 48;5 sequences)
    _, bg = _colors_for("default", "0e141d", False, pal)
    assert bg is not None and bg.name() == "#0e141d"
    # named 16-color attributes are untouched ("red" must not parse as hex)
    fg, _ = _colors_for("brightred", "default", False, pal)
    assert fg.name() == pal["fg"].name() or fg.name() == "#d08770"


def test_sgr_colon_subparameters_do_not_leak_text():
    core = TerminalCore()
    # kitty curly-underline + underline color: only "UX tail" may appear
    core.feed(b"\x1b[4:3mU\x1b[58:2::255:0:0mX\x1b[0m tail")
    line = core.line_at(core.total_lines() - core.rows)
    assert line.startswith("UX tail")
    row = core.screen.buffer[0]
    assert row[0].data == "U" and row[0].underscore  # base attribute kept
    assert row[1].data == "X"


def test_osc_color_query_captured_and_stripped():
    core = TerminalCore()
    core.feed(b"\x1b]10;?\x07\x1b]11;?\x1b\\ok")
    assert core.take_terminal_queries() == [10, 11]
    assert core.take_terminal_queries() == []  # drained, not sticky
    assert core.line_at(core.total_lines() - core.rows).startswith("ok")


def test_view_answers_osc11_with_its_palette(qtapp):
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.terminal import TerminalView

    term = TerminalView(Settings(), native_colors=True)  # VM palette: bg black
    sent: list[bytes] = []
    term.dataWritten.connect(sent.append)
    term.feed(b"\x1b]11;?\x07")
    assert sent == [b"\x1b]11;rgb:0000/0000/0000\x1b\\"]
    assert term.core.take_terminal_queries() == []  # answered, not pending
    term.deleteLater()
