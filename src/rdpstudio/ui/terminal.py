"""Terminal emulator.

Split into two layers:

- :class:`TerminalCore` — pure Python: pyte screen + byte stream, OSC-52
  clipboard sniffing and bracketed-paste tracking. Fully unit-testable
  without Qt.
- :class:`TerminalView` — the QWidget that renders the core, handles
  keyboard/mouse, selection, clipboard and scrolling.
"""

from __future__ import annotations

import base64
import re

import pyte
from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QClipboard, QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QMenu, QScrollBar, QWidget

from ..core.settings import Settings

# ----------------------------------------------------------------------
# Pure core
# ----------------------------------------------------------------------
_OSC52_RE = re.compile(rb"\x1b\]52;([a-zA-Z0-9]+);([A-Za-z0-9+/=]*)\x07|\x1b\]52;([a-zA-Z0-9]+);([A-Za-z0-9+/=]*)\x1b\\")
_BPASTE_RE = re.compile(rb"\x1b\[\?2004([hl])")


class TerminalCore:
    def __init__(self, cols: int = 80, rows: int = 24, history: int = 5000) -> None:
        self.screen = pyte.HistoryScreen(cols, rows, history=history)
        self.stream = pyte.ByteStream()
        self.stream.attach(self.screen)
        self.bracketed_paste = False
        self.osc52_last_clipboard: str | None = None
        self._tail = b""

    # ------------------------------------------------------------------
    def feed(self, data: bytes) -> str | None:
        """Feed transport bytes; returns decoded OSC-52 text if present."""
        data = self._tail + data
        self._tail = b""

        # Extract OSC 52 before pyte sees it (pyte would ignore it anyway).
        osc52: list[str] = []
        for m in _OSC52_RE.finditer(data):
            b64 = m.group(2) or m.group(4) or ""
            osc52.append(b64)
        data = _OSC52_RE.sub(b"", data)

        # Track bracketed paste mode toggles (pyte does not track 2004).
        for m in _BPASTE_RE.finditer(data):
            self.bracketed_paste = m.group(1) == b"h"

        # Hold back a potentially incomplete tail sequence (no terminator yet).
        esc = data.rfind(b"\x1b")
        if esc != -1 and not _seq_complete(data[esc:]) and (len(data) - esc) < 1024:
            self._tail = data[esc:]
            data = data[:esc]

        self.stream.feed(data)
        if osc52:
            try:
                text = base64.b64decode(osc52[-1]).decode("utf-8", "replace")
                self.osc52_last_clipboard = text
            except Exception:  # noqa: BLE001
                pass
        return self.osc52_last_clipboard

    # ------------------------------------------------------------------
    @property
    def cols(self) -> int:
        return self.screen.columns

    @property
    def rows(self) -> int:
        return self.screen.lines

    def resize(self, cols: int, rows: int) -> None:
        self.screen.resize(rows, cols)

    def total_lines(self) -> int:
        """scrollback + visible lines."""
        return len(self.screen.history.top) + self.screen.lines

    def line_at(self, index: int) -> str:
        """Line by absolute index (0 = oldest scrollback, last = top of screen)."""
        top = len(self.screen.history.top)
        if index < top:
            line = self.screen.history.top[index]
            return "".join(cell.data for cell in line.values())
        row = index - top
        line = self.screen.buffer.get(row)
        if line is None:
            return ""
        return "".join(cell.data for cell in line.values())

    def cells_at(self, index: int) -> list | None:
        """pyte cells for absolute line index, or None for history lines."""
        top = len(self.screen.history.top)
        if index < top:
            return None
        row = index - top
        line = self.screen.buffer.get(row)
        if line is None:
            return None
        return [line.get(x) for x in range(self.screen.columns)]

    def cursor_pos(self) -> tuple[int, int]:
        top = len(self.screen.history.top)
        return self.screen.cursor.x, top + self.screen.cursor.y

    def visible_range(self) -> tuple[int, int]:
        top = len(self.screen.history.top)
        return top, top + self.screen.lines

    def selection_text(self, start: tuple[int, int], end: tuple[int, int]) -> str:
        (r1, c1), (r2, c2) = start, end
        if (r1, c1) > (r2, c2):
            (r1, c1), (r2, c2) = (r2, c2), (r1, c1)
        lines: list[str] = []
        for r in range(r1, r2 + 1):
            text = self.line_at(r)
            a = c1 if r == r1 else 0
            b = c2 + 1 if r == r2 else len(text)
            lines.append(text[a:b].rstrip() or "")
        return "\n".join(lines).rstrip("\n")

    def find_text(self, needle: str, from_line: int = 0) -> tuple[int, int] | None:
        """Return (line, col) of first match at/after from_line, else None."""
        if not needle:
            return None
        for idx in range(from_line, self.total_lines()):
            col = self.line_at(idx).find(needle)
            if col >= 0:
                return idx, col
        return None


def _seq_complete(window: bytes) -> bool:
    """Heuristic: does this escape-sequence-looking window look complete?"""
    if not window.startswith(b"\x1b"):
        return True
    body = window[1:]
    if not body:
        return False
    if body[:1] in b"()#":  # charset selection: 1 char
        return len(body) >= 2
    if body[:1] == b"]":  # OSC: terminated by BEL or ST
        return b"\x07" in body or b"\x1b\\" in body
    if body[:1] == b"[":  # CSI: ends with a letter or ~
        return bool(re.match(rb"^\[[0-9;?<=>!\"#$%&'()*+,\-./ ]*[@-~]", body))
    if body[:1] == b"P":  # DCS
        return b"\x1b\\" in body
    return True


# ----------------------------------------------------------------------
# Qt view
# ----------------------------------------------------------------------
class TerminalView(QWidget):
    """Renders a :class:`TerminalCore` and ships input as ``dataWritten``."""

    dataWritten = Signal(bytes)
    sizeChanged = Signal(int, int)  # cols, rows
    titleChanged = Signal(str)
    clipboardRequested = Signal(str)  # OSC-52 payload decoded
    bellRequested = Signal()
    linkActivated = Signal(str)

    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.core = TerminalCore(history=settings.scrollback_lines)
        self.core.screen.bell = self._on_bell  # type: ignore[method-assign]

        self._font = QFont(settings.font_family) if settings.font_family else QFont(_default_mono())
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setPointSize(max(6, settings.font_size))
        self._fm = QFontMetrics(self._font)
        self._cell_w = max(4, self._fm.horizontalAdvance("M"))
        self._cell_h = max(6, self._fm.height())
        self._ascent = self._fm.ascent()

        self._scroll = 0  # lines scrolled back (0 = live)
        self._sel_start: tuple[int, int] | None = None
        self._sel_end: tuple[int, int] | None = None
        self._dragging = False
        self._blink_state = True
        self._dirty = True

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(lambda: (self._toggle_blink()))
        self._blink_timer.start()

        self._coalesce = QTimer(self)
        self._coalesce.setSingleShot(True)
        self._coalesce.setInterval(8)
        self._coalesce.timeout.connect(self.update)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(self._cell_w * 20, self._cell_h * 6)

        self.vbar = QScrollBar(Qt.Orientation.Vertical, self)
        self.vbar.rangeChanged.connect(self._sync_scrollbar)
        self.vbar.valueChanged.connect(self._on_scrollbar)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    # ------------------------------------------------------------------
    def _on_bell(self) -> None:
        self.bellRequested.emit()

    def font(self) -> QFont:
        return self._font

    def apply_font(self, family: str, size: int) -> None:
        self._font = QFont(family) if family else QFont(_default_mono())
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setPointSize(max(6, size))
        self._fm = QFontMetrics(self._font)
        self._cell_w = max(4, self._fm.horizontalAdvance("M"))
        self._cell_h = max(6, self._fm.height())
        self._ascent = self._fm.ascent()
        self._relayout()

    # -- data flow --------------------------------------------------------
    def feed(self, data: bytes) -> None:
        payload = self.core.feed(data)
        title = getattr(self.core.screen, "title", None)
        if title:
            self.titleChanged.emit(str(title))
        if payload is not None:
            self.clipboardRequested.emit(payload)
        self._dirty = True
        self._coalesce.start()

    def write_user(self, data: bytes) -> None:
        self.dataWritten.emit(data)

    def send_text(self, text: str) -> None:
        self.dataWritten.emit(text.encode("utf-8"))

    # -- geometry ----------------------------------------------------------
    def cols_rows(self) -> tuple[int, int]:
        cw, ch = self._cell_w, self._cell_h
        w = self.width() - self.vbar.width() - 4
        h = self.height() - 4
        return max(2, w // cw), max(2, h // ch)

    def _relayout(self) -> None:
        cols, rows = self.cols_rows()
        if (cols, rows) != (self.core.cols, self.core.rows):
            self.core.resize(cols, rows)
            self.sizeChanged.emit(cols, rows)
        self._sync_scrollbar()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()
        self.vbar.setGeometry(self.width() - self.vbar.width(), 0, self.vbar.width(), self.height())

    def _sync_scrollbar(self, *_) -> None:
        total = self.core.total_lines()
        visible = self.core.rows
        max_scroll = max(0, total - visible)
        self.vbar.setPageStep(visible)
        self.vbar.setRange(0, max_scroll)
        self.vbar.setValue(max_scroll - self._scroll)

    def _on_scrollbar(self, value: int) -> None:
        self._scroll = self.vbar.maximum() - value
        self.update()

    def scroll_lines(self, n: int) -> None:
        self._scroll = min(max(0, self._scroll + n), self.vbar.maximum())
        self.vbar.setValue(self.vbar.maximum() - self._scroll)
        self.update()

    def scroll_to_bottom(self) -> None:
        self._scroll = 0
        self.vbar.setValue(self.vbar.maximum())
        self.update()

    # -- rendering ----------------------------------------------------------
    def _toggle_blink(self) -> None:
        if self.hasFocus() and self._scroll == 0:
            self._blink_state = not self._blink_state
            self.update()

    def _palette(self) -> dict:
        dark = self.settings.theme == "dark"
        base = {
            "fg": QColor("#d8dee9") if dark else QColor("#1b1f24"),
            "bg": QColor("#11151c") if dark else QColor("#ffffff"),
            "cursor": QColor("#88c0d0") if dark else QColor("#2e3440"),
            "sel": QColor("#2f4b67") if dark else QColor("#b3d4fc"),
        }
        palette16 = (
            ["#2e3440", "#bf616a", "#a3be8c", "#ebcb8b", "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
             "#4c566a", "#d08770", "#a3be8c", "#ebcb8b", "#5e81ac", "#b48ead", "#8fbcbb", "#eceff4"]
            if dark
            else ["#000000", "#a31515", "#357200", "#8f6700", "#0b5cc4", "#832e83", "#0e7a8a", "#5e5e5e",
                  "#4d4d4d", "#b15b5b", "#4f9f4f", "#b5a52f", "#5f87d7", "#9b6b9b", "#54b3c5", "#efefef"]
        )
        base["16"] = [QColor(c.lower()) for c in palette16]
        base["fg_dim"] = base["16"][8]
        return base

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = self._palette()
        painter = QPainter(self)
        painter.fillRect(self.rect(), pal["bg"])
        top = len(self.core.screen.history.top)
        first_row = top - self._scroll
        cw, ch = self._cell_w, self._cell_h

        painter.setFont(self._font)
        for row in range(self.core.rows):
            abs_index = first_row + row
            if abs_index < 0:
                continue
            y = 2 + row * ch
            if abs_index < top:
                # scrollback line (plain text)
                text = self.core.line_at(abs_index)
                painter.setPen(pal["fg_dim"])
                painter.drawText(2, y + self._ascent, text)
                continue
            cells = self.core.cells_at(abs_index) or []
            x = 2
            for xoff, cell in enumerate(cells):
                if cell is None or cell.data == "":
                    x += 0
                    continue
                fg, bg = _colors_for(cell, pal)
                x = 2 + xoff * cw
                if bg is not None:
                    painter.fillRect(x, y, cw, ch, bg)
                pen = QPen(fg)
                painter.setPen(pen)
                font = self._font
                if cell.bold:
                    font.setBold(True)
                if cell.italics:
                    font.setItalic(True)
                painter.setFont(font)
                painter.drawText(x, y + self._ascent, cell.data)
                if cell.underscore:
                    painter.drawLine(x, y + ch - 2, x + cw, y + ch - 2)
                if cell.strikethrough:
                    painter.drawLine(x, y + ch // 2, x + cw, y + ch // 2)
                font.setBold(False)
                font.setItalic(False)

        # selection
        if self._sel_start and self._sel_end:
            rect = self._selection_rect()
            if rect:
                painter.fillRect(rect, pal["sel"])

        # cursor
        if self._blink_state and self._scroll == 0:
            cx, cy_abs = self.core.cursor_pos()
            cy = cy_abs - first_row
            if 0 <= cy < self.core.rows:
                x = 2 + cx * cw
                y = 2 + cy * ch
                style = self.settings.cursor_style
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Xor)
                if style == "underline":
                    painter.fillRect(x, y + ch - 3, cw, 3, pal["cursor"])
                elif style == "bar":
                    painter.fillRect(x, y, 2, ch, pal["cursor"])
                else:
                    painter.fillRect(x, y, cw, ch, pal["cursor"])
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.end()

    # -- selection -----------------------------------------------------------
    def _pos_to_cell(self, pos: QPoint) -> tuple[int, int]:
        top = len(self.core.screen.history.top)
        first_row = top - self._scroll
        col = max(0, (pos.x() - 2) // self._cell_w)
        row = max(0, min(self.core.rows - 1, (pos.y() - 2) // self._cell_h))
        return first_row + row, min(col, self.core.cols - 1)

    def _selection_rect(self) -> QRect | None:
        if not (self._sel_start and self._sel_end):
            return None
        (r1, c1), (r2, c2) = self._sel_start, self._sel_end
        if (r1, c1) > (r2, c2):
            (r1, c1), (r2, c2) = (r2, c2), (r1, c1)
        top = len(self.core.screen.history.top)
        first_row = top - self._scroll
        y1 = 2 + (r1 - first_row) * self._cell_h
        y2 = 2 + (r2 - first_row) * self._cell_h + self._cell_h
        x1 = 2 + c1 * self._cell_w
        x2 = 2 + (c2 + 1) * self._cell_w
        return QRect(x1, y1, x2 - x1, y2 - y1)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._sel_start = self._sel_end = self._pos_to_cell(event.position().toPoint())
            self._dragging = True
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton:
            if self.settings.paste_on_middle_click:
                self.paste_clipboard(confirm=False)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            self._sel_end = self._pos_to_cell(event.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self.settings.copy_on_select and self.has_selection():
                self.copy_selection()
            self.update()

    def has_selection(self) -> bool:
        if not (self._sel_start and self._sel_end):
            return False
        return self.core.selection_text(self._sel_start, self._sel_end).strip() != ""

    def selection(self) -> str:
        if not (self._sel_start and self._sel_end):
            return ""
        return self.core.selection_text(self._sel_start, self._sel_end)

    def copy_selection(self) -> None:
        text = self.selection()
        if text:
            QGuiApplication.clipboard().setText(text, QClipboard.Mode.Selection)
            QGuiApplication.clipboard().setText(text, QClipboard.Mode.Clipboard)

    def paste_clipboard(self, confirm: bool = True) -> None:
        text = QGuiApplication.clipboard().text()
        if not text:
            return
        self.paste_text(text, confirm=confirm)

    def paste_text(self, text: str, confirm: bool = True) -> None:
        if confirm and self.settings.confirm_multiline_paste and ("\n" in text or len(text) > 200):
            from PySide6.QtWidgets import QMessageBox

            preview = text if len(text) < 400 else text[:400] + "…"
            btn = QMessageBox.question(
                self,
                "Paste multiple lines?",
                f"Paste the following to the remote host?\n\n{preview}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if btn != QMessageBox.StandardButton.Yes:
                return
        if self.core.bracketed_paste:
            self.write_user(b"\x1b[200~" + text.encode("utf-8") + b"\x1b[201~")
        else:
            self.write_user(text.encode("utf-8"))
        self.scroll_to_bottom()

    # -- keyboard --------------------------------------------------------------
    def keyPressEvent(self, event) -> None:  # noqa: N802
        data = encode_key_event(event, self.core.screen)
        if data:
            self.write_user(data)
            self.scroll_to_bottom()
            event.accept()
        else:
            super().keyPressEvent(event)

    def inputMethodEvent(self, event) -> None:  # noqa: N802
        commit = event.commitString()
        if commit:
            self.write_user(commit.encode("utf-8"))

    def wheelEvent(self, event) -> None:  # noqa: N802
        steps = event.angleDelta().y() // 40
        if steps:
            self.scroll_lines(-steps * 3)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._blink_state = True
        self.update()
        super().focusInEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        copy_action = menu.addAction("Copy\tCtrl+Shift+C")
        copy_action.triggered.connect(self.copy_selection)
        paste_action = menu.addAction("Paste\tCtrl+Shift+V")
        paste_action.triggered.connect(self.paste_clipboard)
        menu.addSeparator()
        select_all = menu.addAction("Select all")
        select_all.triggered.connect(self.select_all)
        clear_sb = menu.addAction("Clear scrollback")
        clear_sb.triggered.connect(self.clear_scrollback)
        menu.exec(event.globalPos())

    def select_all(self) -> None:
        total = self.core.total_lines()
        if total == 0:
            return
        self._sel_start = (0, 0)
        last = total - 1
        self._sel_end = (last, max(0, len(self.core.line_at(last)) - 1))
        self.update()

    def clear_scrollback(self) -> None:
        self.core.screen.history.top.clear()
        self._scroll = 0
        self._sync_scrollbar()
        self.update()

    def sizeHint(self):  # noqa: N802 - Qt override naming
        from PySide6.QtCore import QSize

        return QSize(self._cell_w * self.core.cols, self._cell_h * self.core.rows)


# ----------------------------------------------------------------------
# Key encoding (xterm)
# ----------------------------------------------------------------------
def _modifier_code(mods) -> int:
    code = 1
    if mods & Qt.KeyboardModifier.ShiftModifier:
        code += 1
    if mods & Qt.KeyboardModifier.AltModifier:
        code += 2
    if mods & Qt.KeyboardModifier.ControlModifier:
        code += 4
    if mods & Qt.KeyboardModifier.MetaModifier:
        code += 8
    return code


def encode_key_event(event, screen) -> bytes | None:
    """Translate a QKeyEvent to terminal bytes (xterm-ish).

    ``event`` only needs ``key()``, ``text()`` and ``modifiers()`` — tests
    pass duck-typed fakes.
    """
    key = event.key()
    mods = event.modifiers()
    text = event.text()

    ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
    alt = bool(mods & Qt.KeyboardModifier.AltModifier)
    shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

    app_cursor = False
    try:
        # pyte stores private modes bit-shifted (DECCKM=1 → 1<<5)
        app_cursor = (1 << 5) in (screen.mode or set())
    except Exception:  # noqa: BLE001
        pass

    # --- control characters ------------------------------------------
    if ctrl and not alt:
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return bytes([(key - Qt.Key.Key_A) + 1])
        if key == Qt.Key.Key_Space:
            return b"\x00"
        if key == Qt.Key.Key_BracketLeft:
            return b"\x1b"
        if key == Qt.Key.Key_Backslash:
            return b"\x1c"
        if key == Qt.Key.Key_BracketRight:
            return b"\x1d"
        if key == Qt.Key.Key_AsciiCircum:
            return b"\x1e"
        if key == Qt.Key.Key_Underscore or key == Qt.Key.Key_Slash:
            return b"\x1f"
    if ctrl and alt:
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return b"\x1b" + bytes([(key - Qt.Key.Key_A) + 1])

    # --- special keys ---------------------------------------------------
    simple: dict = {
        Qt.Key.Key_Return: b"\r",
        Qt.Key.Key_Enter: b"\r",
        Qt.Key.Key_Backspace: b"\x7f",
        Qt.Key.Key_Escape: b"\x1b",
        Qt.Key.Key_Tab: b"\t",
    }
    if key in simple:
        out = simple[key]
        return b"\x1b" + out if alt else out

    if key == Qt.Key.Key_Backtab:
        return b"\x1b[Z"

    arrows = {
        Qt.Key.Key_Up: "A",
        Qt.Key.Key_Down: "B",
        Qt.Key.Key_Right: "C",
        Qt.Key.Key_Left: "D",
    }
    if key in arrows:
        suffix = arrows[key]
        if app_cursor and not (shift or ctrl or alt):
            return f"\x1bO{suffix}".encode()
        m = _modifier_code(mods)
        seq = f"\x1b[1;{m}{suffix}" if m > 1 else f"\x1b[{suffix}"
        return seq.encode()

    home_end = {Qt.Key.Key_Home: "H", Qt.Key.Key_End: "F"}
    if key in home_end:
        suffix = home_end[key]
        m = _modifier_code(mods)
        if app_cursor and m == 1:
            return f"\x1bO{suffix}".encode()
        return f"\x1b[1;{m}{suffix}".encode()

    tilde = {
        Qt.Key.Key_Insert: 2,
        Qt.Key.Key_Delete: 3,
        Qt.Key.Key_PageUp: 5,
        Qt.Key.Key_PageDown: 6,
    }
    if key in tilde:
        n = tilde[key]
        m = _modifier_code(mods)
        return f"\x1b[{n};{m}~".encode() if m > 1 else f"\x1b[{n}~".encode()

    fn = {
        Qt.Key.Key_F1: (11, "P"),
        Qt.Key.Key_F2: (12, "Q"),
        Qt.Key.Key_F3: (13, "R"),
        Qt.Key.Key_F4: (14, "S"),
        Qt.Key.Key_F5: 15,
        Qt.Key.Key_F6: 17,
        Qt.Key.Key_F7: 18,
        Qt.Key.Key_F8: 19,
        Qt.Key.Key_F9: 20,
        Qt.Key.Key_F10: 21,
        Qt.Key.Key_F11: 23,
        Qt.Key.Key_F12: 24,
    }
    if key in fn:
        val = fn[key]
        m = _modifier_code(mods)
        if isinstance(val, tuple):
            n, suffix = val
            return f"\x1b[1;{m}{suffix}".encode() if m > 1 else f"\x1bO{suffix}".encode()
        return f"\x1b[{val};{m}~".encode() if m > 1 else f"\x1b[{val}~".encode()

    # --- plain text -------------------------------------------------------
    if text:
        out = text.encode("utf-8")
        if alt:
            # ESC-prefix each char is overkill; prefix the whole string once
            return b"\x1b" + out
        return out
    return None


def _default_mono() -> str:
    if __import__("sys").platform == "win32":
        return "Consolas"
    return "DejaVu Sans Mono"


def _colors_for(cell, pal) -> tuple[QColor, QColor | None]:
    fg = pal["fg"]
    bg: QColor | None = None

    def resolve(color, is_fg: bool) -> None:
        nonlocal fg, bg
        if color in (None, "default"):
            return
        if isinstance(color, int) or (isinstance(color, str) and color.isdigit()):
            idx = int(color)
            c = pal["16"][idx] if idx < 16 else _xterm256(idx, pal)
        elif isinstance(color, str) and color.lower() in _NAMED:
            c = QColor(_NAMED[color.lower()])
        elif isinstance(color, str) and color.startswith("#"):
            c = QColor(color)
        else:
            return
        if is_fg:
            fg = c
        else:
            bg = c

    resolve(cell.fg, True)
    resolve(cell.bg, False)
    if cell.reverse:
        fg, bg = (bg or pal["bg"]), QColor(fg)
    return fg, bg


_NAMED: dict[str, str | QColor] = {
    "black": "#2e3440",
    "red": "#bf616a",
    "green": "#a3be8c",
    "yellow": "#ebcb8b",
    "blue": "#81a1c1",
    "magenta": "#b48ead",
    "cyan": "#88c0d0",
    "white": "#e5e9f0",
    "brightblack": "#4c566a",
    "brightred": "#d08770",
    "brightgreen": "#a3be8c",
    "brightyellow": "#ebcb8b",
    "brightblue": "#5e81ac",
    "brightmagenta": "#b48ead",
    "brightcyan": "#8fbcbb",
    "brightwhite": "#eceff4",
    "default": "#d8dee9",
}


def _xterm256(idx: int, pal) -> QColor:
    if 16 <= idx < 232:
        idx -= 16
        steps = [0, 95, 135, 175, 215, 255]
        r = steps[(idx // 36) % 6]
        g = steps[(idx // 6) % 6]
        b = steps[idx % 6]
        return QColor(r, g, b)
    if idx >= 232:
        grey = 8 + (idx - 232) * 10
        return QColor(grey, grey, grey)
    return pal["16"][idx % 16]
