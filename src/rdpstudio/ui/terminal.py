"""Terminal emulator.

Split into two layers:

- :class:`TerminalCore` — pure Python: pyte screen + byte stream, OSC-52
  clipboard sniffing and bracketed-paste tracking. Fully unit-testable
  without Qt.
- :class:`TerminalView` — the QWidget that renders the core, handles
  keyboard/mouse, selection, clipboard, scrolling, in-terminal search, and session logging.
"""

from __future__ import annotations

import base64
import binascii
import re
import time
from pathlib import Path

import pyte
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QClipboard, QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollBar,
    QToolButton,
    QWidget,
)

from ..core.settings import Settings

# ----------------------------------------------------------------------
# Pure core
# ----------------------------------------------------------------------
_OSC52_RE = re.compile(rb"\x1b\]52;([a-zA-Z0-9]+);([A-Za-z0-9+/=]*)\x07|\x1b\]52;([a-zA-Z0-9]+);([A-Za-z0-9+/=]*)\x1b\\")
_BPASTE_RE = re.compile(rb"\x1b\[\?2004([hl])")

# Largest escape-sequence prefix we will buffer waiting for its terminator.
_MAX_PENDING_SEQ = 1024
# Largest OSC-52 base64 payload accepted from the remote host (~768 KiB text).
_MAX_OSC52_B64 = 1_048_576


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
        """Feed transport bytes.

        Returns freshly decoded OSC-52 clipboard text, or ``None`` when this
        chunk carried none.  (It must *not* keep returning the last payload:
        doing so let a remote host re-assert the local clipboard on every
        byte of output — an effective clipboard hijack.)
        """
        data = self._tail + data
        self._tail = b""

        # Extract OSC 52 before pyte sees it (pyte would ignore it anyway).
        osc52: list[str] = []
        for m in _OSC52_RE.finditer(data):
            b64 = m.group(2) or m.group(4) or ""
            osc52.append(b64)
        if osc52:
            data = _OSC52_RE.sub(b"", data)

        # Track bracketed paste mode toggles (pyte does not track 2004).
        for m in _BPASTE_RE.finditer(data):
            self.bracketed_paste = m.group(1) == b"h"

        # Hold back a potentially incomplete tail sequence (no terminator yet).
        esc = data.rfind(b"\x1b")
        if esc != -1 and not _seq_complete(data[esc:]) and (len(data) - esc) < _MAX_PENDING_SEQ:
            self._tail = data[esc:]
            data = data[:esc]

        self.stream.feed(data)

        fresh: str | None = None
        if osc52:
            payload = osc52[-1]
            # Bound the decode: a hostile host could otherwise stream a
            # multi-megabyte base64 blob straight into the clipboard.
            if 0 < len(payload) <= _MAX_OSC52_B64:
                try:
                    fresh = base64.b64decode(payload, validate=True).decode("utf-8", "replace")
                except (ValueError, binascii.Error):
                    fresh = None
            if fresh is not None:
                self.osc52_last_clipboard = fresh
        return fresh

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

    def find_text(
        self,
        needle: str,
        from_line: int = 0,
        backward: bool = False,
        case_sensitive: bool = False,
    ) -> tuple[int, int] | None:
        """Return (line, col) of first match at/after/before from_line, else None."""
        if not needle:
            return None
        total = self.total_lines()
        target_needle = needle if case_sensitive else needle.lower()
        if backward:
            start = min(from_line, total - 1)
            for idx in range(start, -1, -1):
                raw = self.line_at(idx)
                line = raw if case_sensitive else raw.lower()
                col = line.rfind(target_needle)
                if col >= 0:
                    return idx, col
        else:
            start = max(0, from_line)
            for idx in range(start, total):
                raw = self.line_at(idx)
                line = raw if case_sensitive else raw.lower()
                col = line.find(target_needle)
                if col >= 0:
                    return idx, col
        return None

    def find_all(
        self, needle: str, case_sensitive: bool = False
    ) -> list[tuple[int, int, int]]:
        """Return list of (line, start_col, end_col) for all matches in buffer."""
        if not needle:
            return []
        matches: list[tuple[int, int, int]] = []
        target = needle if case_sensitive else needle.lower()
        nlen = len(needle)
        for idx in range(self.total_lines()):
            raw = self.line_at(idx)
            line = raw if case_sensitive else raw.lower()
            pos = 0
            while True:
                col = line.find(target, pos)
                if col == -1:
                    break
                matches.append((idx, col, col + nlen))
                pos = col + max(1, nlen)
        return matches


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
# Floating In-Terminal Search Bar
# ----------------------------------------------------------------------
class TerminalSearchBar(QWidget):
    """Floating modern search bar overlay for TerminalView."""

    findNext = Signal(str, bool)  # needle, case_sensitive
    findPrev = Signal(str, bool)
    queryChanged = Signal(str, bool)
    closed = Signal()

    def __init__(self, parent: TerminalView) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(40)
        self.setMinimumWidth(360)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        lbl = QLabel("⌕")
        lbl.setObjectName("muted")
        lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(lbl)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Find in terminal…")
        self.input.setObjectName("search")
        self.input.setClearButtonEnabled(True)
        self.input.setMinimumWidth(160)
        self.input.textChanged.connect(self._on_text_changed)
        self.input.returnPressed.connect(self._on_return)
        layout.addWidget(self.input, 1)

        self.lbl_count = QLabel("0 matches")
        self.lbl_count.setObjectName("caption")
        self.lbl_count.setStyleSheet("font-size: 11px; min-width: 65px;")
        layout.addWidget(self.lbl_count)

        self.btn_case = QToolButton()
        self.btn_case.setText("Aa")
        self.btn_case.setCheckable(True)
        self.btn_case.setToolTip("Match case (Alt+C)")
        self.btn_case.setShortcut("Alt+C")
        self.btn_case.toggled.connect(self._on_text_changed)
        layout.addWidget(self.btn_case)

        self.btn_prev = QToolButton()
        self.btn_prev.setText("▲")
        self.btn_prev.setToolTip("Previous match (Shift+Enter / Shift+F3)")
        self.btn_prev.clicked.connect(self._on_prev)
        layout.addWidget(self.btn_prev)

        self.btn_next = QToolButton()
        self.btn_next.setText("▼")
        self.btn_next.setToolTip("Next match (Enter / F3)")
        self.btn_next.clicked.connect(self._on_next)
        layout.addWidget(self.btn_next)

        self.btn_close = QToolButton()
        self.btn_close.setText("✕")
        self.btn_close.setToolTip("Close search (Escape)")
        self.btn_close.clicked.connect(self.close_bar)
        layout.addWidget(self.btn_close)

    def _on_text_changed(self) -> None:
        self.queryChanged.emit(self.input.text(), self.btn_case.isChecked())

    def _on_return(self) -> None:
        # If shift is pressed during enter, find prev
        mods = QGuiApplication.keyboardModifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            self._on_prev()
        else:
            self._on_next()

    def _on_next(self) -> None:
        self.findNext.emit(self.input.text(), self.btn_case.isChecked())

    def _on_prev(self) -> None:
        self.findPrev.emit(self.input.text(), self.btn_case.isChecked())

    def set_match_status(self, current_idx: int, total_matches: int) -> None:
        if total_matches == 0:
            self.lbl_count.setText("0 matches")
        else:
            self.lbl_count.setText(f"{current_idx + 1} of {total_matches}")

    def open_with_text(self, text: str = "") -> None:
        if text:
            self.input.setText(text)
        self.show()
        self.raise_()
        self.input.setFocus()
        self.input.selectAll()
        self._on_text_changed()

    def close_bar(self) -> None:
        self.hide()
        self.closed.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close_bar()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F3:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._on_prev()
            else:
                self._on_next()
            event.accept()
            return
        super().keyPressEvent(event)


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
        self._last_title: str | None = None
        self._dirty = True

        # Render caches — rebuilt only when the theme or font changes.
        self._palette_cache: dict | None = None
        self._palette_theme: str | None = None
        self._font_variants: dict[tuple[bool, bool], QFont] = {}

        # Search state
        self._search_query = ""
        self._search_case = False
        self._search_matches: list[tuple[int, int, int]] = []
        self._search_current_idx = -1

        # Session logging
        self._log_file = None
        self._log_path: Path | None = None

        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(self._toggle_blink)
        self._blink_timer.start()

        # Output coalescing: repaint at most ~60 fps
        self._coalesce = QTimer(self)
        self._coalesce.setSingleShot(True)
        self._coalesce.setTimerType(Qt.TimerType.PreciseTimer)
        self._coalesce.setInterval(16)
        self._coalesce.timeout.connect(self._flush_frame)

        self._syncing_scrollbar = False
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(40)
        self._resize_timer.timeout.connect(self._relayout)

        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(self._cell_w * 20, self._cell_h * 6)
        self._font_size = self._font.pointSize()  # Ctrl+wheel zoom base

        self.vbar = QScrollBar(Qt.Orientation.Vertical, self)
        self.vbar.setStyleSheet("""
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 2px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2a3448;
                border-radius: 4px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #3a4a6a;
            }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        """)
        self.vbar.rangeChanged.connect(self._sync_scrollbar)
        self.vbar.valueChanged.connect(self._on_scrollbar)

        # In-terminal search bar overlay
        self.search_bar = TerminalSearchBar(self)
        self.search_bar.hide()
        self.search_bar.queryChanged.connect(self._on_search_query)
        self.search_bar.findNext.connect(self._on_find_next)
        self.search_bar.findPrev.connect(self._on_find_prev)
        self.search_bar.closed.connect(self._on_search_closed)

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
        self._font_variants.clear()
        self._font_size = size
        self._relayout()

    # -- session logging ---------------------------------------------------
    def start_logging(self, path: str | Path) -> None:
        """Log all terminal output to a local text/log file."""
        self.stop_logging()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = open(p, "a", encoding="utf-8", buffering=1)
        self._log_path = p
        self._log_file.write(f"\n--- RDP Studio Session Log Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")

    def stop_logging(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.write(f"\n--- RDP Studio Session Log Ended: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None
            self._log_path = None

    def is_logging(self) -> bool:
        return self._log_file is not None

    def log_path(self) -> Path | None:
        return self._log_path

    # -- search flow -------------------------------------------------------
    def open_search(self) -> None:
        preset = self.selection() if self.has_selection() else self._search_query
        self._position_search_bar()
        self.search_bar.open_with_text(preset)

    def close_search(self) -> None:
        self.search_bar.close_bar()

    def _position_search_bar(self) -> None:
        sb_width = min(420, max(300, self.width() - 60))
        self.search_bar.resize(sb_width, 40)
        x = max(10, self.width() - sb_width - self.vbar.width() - 14)
        self.search_bar.move(x, 10)

    def _on_search_query(self, query: str, case_sensitive: bool) -> None:
        self._search_query = query
        self._search_case = case_sensitive
        if not query:
            self._search_matches = []
            self._search_current_idx = -1
            self.search_bar.set_match_status(0, 0)
            self.update()
            return
        self._search_matches = self.core.find_all(query, case_sensitive=case_sensitive)
        total = len(self._search_matches)
        if total > 0:
            # Find closest match at or after current scroll position
            top = len(self.core.screen.history.top)
            first_visible = top - self._scroll
            idx = 0
            for i, (r, _, _) in enumerate(self._search_matches):
                if r >= first_visible:
                    idx = i
                    break
            self._search_current_idx = idx
            self.search_bar.set_match_status(idx, total)
            self._scroll_to_match(self._search_matches[idx])
        else:
            self._search_current_idx = -1
            self.search_bar.set_match_status(0, 0)
        self.update()

    def _on_find_next(self, query: str, case_sensitive: bool) -> None:
        if not self._search_matches:
            self._on_search_query(query, case_sensitive)
            return
        total = len(self._search_matches)
        if total > 0:
            self._search_current_idx = (self._search_current_idx + 1) % total
            match = self._search_matches[self._search_current_idx]
            self.search_bar.set_match_status(self._search_current_idx, total)
            self._scroll_to_match(match)
            self.update()

    def _on_find_prev(self, query: str, case_sensitive: bool) -> None:
        if not self._search_matches:
            self._on_search_query(query, case_sensitive)
            return
        total = len(self._search_matches)
        if total > 0:
            self._search_current_idx = (self._search_current_idx - 1 + total) % total
            match = self._search_matches[self._search_current_idx]
            self.search_bar.set_match_status(self._search_current_idx, total)
            self._scroll_to_match(match)
            self.update()

    def _scroll_to_match(self, match: tuple[int, int, int]) -> None:
        r, c1, _ = match
        top = len(self.core.screen.history.top)
        visible = self.core.rows
        # Scroll so line r is nicely centered in visible window
        target_first_row = max(0, r - (visible // 2))
        max_scroll = self.vbar.maximum()
        scroll_val = max(0, min(max_scroll, top - target_first_row))
        self._scroll = scroll_val
        self.vbar.setValue(max_scroll - self._scroll)

    def _on_search_closed(self) -> None:
        self._search_query = ""
        self._search_matches = []
        self._search_current_idx = -1
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    # -- data flow --------------------------------------------------------
    def feed(self, data: bytes) -> None:
        # Write to session log if active
        if self._log_file is not None:
            try:
                # Strip raw ESC control sequences for clean log readability
                clean = re.sub(r"\x1b\[[0-9;?<=>!\"#$%&'()*+,\-./ ]*[@-~]", "", data.decode("utf-8", "replace"))
                clean = re.sub(r"\x1b\].*?(\x07|\x1b\\)", "", clean)
                self._log_file.write(clean)
            except Exception:
                pass

        payload = self.core.feed(data)
        title = getattr(self.core.screen, "title", None)
        if title and title != self._last_title:
            self._last_title = str(title)
            self.titleChanged.emit(self._last_title)
        if payload is not None:
            self.clipboardRequested.emit(payload)
        self._dirty = True
        if not self._coalesce.isActive():
            self._coalesce.start()

    def _flush_frame(self) -> None:
        """Repaint once for all output accumulated since the last frame."""
        if not self._dirty:
            return
        self._dirty = False
        self._sync_scrollbar()
        self.update()

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
        self._resize_timer.start()
        self.vbar.setGeometry(self.width() - self.vbar.width(), 0, self.vbar.width(), self.height())
        if self.search_bar.isVisible():
            self._position_search_bar()

    def _sync_scrollbar(self, *_) -> None:
        if self._syncing_scrollbar:
            return
        self._syncing_scrollbar = True
        try:
            total = self.core.total_lines()
            visible = self.core.rows
            max_scroll = max(0, total - visible)
            self.vbar.setPageStep(visible)
            self.vbar.setRange(0, max_scroll)
            self.vbar.setValue(max_scroll - self._scroll)
        finally:
            self._syncing_scrollbar = False

    def _on_scrollbar(self, value: int) -> None:
        if self._syncing_scrollbar:
            return
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
        """Blink the cursor by repainting *only* its cell, not the widget."""
        if not (self.hasFocus() and self._scroll == 0):
            return
        self._blink_state = not self._blink_state
        self.update(self._cursor_rect())

    def _cursor_rect(self) -> QRect:
        top = len(self.core.screen.history.top)
        first_row = top - self._scroll
        cx, cy_abs = self.core.cursor_pos()
        cy = cy_abs - first_row
        return QRect(2 + cx * self._cell_w, 2 + cy * self._cell_h, self._cell_w, self._cell_h)

    def _palette(self) -> dict:
        """Theme palette, built once per theme."""
        theme = self.settings.theme
        cached = self._palette_cache
        if cached is not None and self._palette_theme == theme:
            return cached
        pal = self._build_palette()
        self._palette_cache = pal
        self._palette_theme = theme
        return pal

    def _build_palette(self) -> dict:
        dark = self.settings.theme == "dark"
        if dark:
            base = {
                "fg": QColor("#e6eaf2"),
                "bg": QColor("#0b0f19"),
                "cursor": QColor("#6c8bff"),
                "sel": QColor("#2a3a5e"),
                "match": QColor(251, 191, 106, 75),       # soft amber highlight
                "match_active": QColor(251, 191, 106, 170),
                "match_border": QColor("#fbbf6a"),
            }
            palette16 = [
                "#1a1f2e", "#ff7a7a", "#6ee7a5", "#fbbf6a", "#7cc4ff", "#c4a7ff", "#6c8bff", "#e6eaf2",
                "#5c677e", "#ff9a9a", "#8ff0b8", "#ffd08a", "#9cd6ff", "#d4bfff", "#8aa4ff", "#f6f7fb"
            ]
        else:
            base = {
                "fg": QColor("#151a2b"),
                "bg": QColor("#ffffff"),
                "cursor": QColor("#4f6ef7"),
                "sel": QColor("#c7d9ff"),
                "match": QColor(255, 230, 100, 100),
                "match_active": QColor(255, 210, 50, 190),
                "match_border": QColor("#d97706"),
            }
            palette16 = [
                "#000000", "#e02424", "#0e9f6e", "#c07a00", "#1a73e8", "#7c3aed", "#4f6ef7", "#5c677e",
                "#6b768f", "#ff6b6b", "#34d399", "#fbbf24", "#60a5fa", "#a78bfa", "#818cf8", "#eef1f8"
            ]
        base["16"] = [QColor(c.lower()) for c in palette16]
        base["fg_dim"] = QColor("#8a94ac") if dark else QColor("#6b768f")
        return base

    def _font_for(self, bold: bool, italic: bool) -> QFont:
        key = (bold, italic)
        font = self._font_variants.get(key)
        if font is None:
            font = QFont(self._font)
            font.setBold(bold)
            font.setItalic(italic)
            self._font_variants[key] = font
        return font

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = self._palette()
        painter = QPainter(self)
        bg_default = pal["bg"]
        painter.fillRect(event.rect(), bg_default)
        top = len(self.core.screen.history.top)
        first_row = top - self._scroll
        cw, ch = self._cell_w, self._cell_h
        ascent = self._ascent

        dirty = event.rect()
        row_from = max(0, (dirty.top() - 2) // ch)
        row_to = min(self.core.rows, (dirty.bottom() - 2) // ch + 1)

        painter.setFont(self._font)
        for row in range(row_from, row_to):
            abs_index = first_row + row
            if abs_index < 0:
                continue
            y = 2 + row * ch
            if abs_index < top:
                # scrollback line
                text = self.core.line_at(abs_index).rstrip()
                if text:
                    painter.setPen(pal["fg_dim"])
                    painter.drawText(2, y + ascent, text)
                continue
            cells = self.core.cells_at(abs_index)
            if not cells:
                continue
            for run in _style_runs(cells, pal):
                start, text, fg, bg, bold, italic, underline, strike = run
                x = 2 + start * cw
                width = cw * len(text)
                if bg is not None:
                    painter.fillRect(x, y, width, ch, bg)
                if not text.strip():
                    continue
                painter.setPen(QPen(fg))
                painter.setFont(self._font_for(bold, italic))
                painter.drawText(x, y + ascent, text)
                if underline:
                    painter.drawLine(x, y + ch - 2, x + width, y + ch - 2)
                if strike:
                    painter.drawLine(x, y + ch // 2, x + width, y + ch // 2)

        # Search match highlights
        if self._search_matches:
            for idx, (m_row, m_c1, m_c2) in enumerate(self._search_matches):
                if first_row <= m_row < first_row + self.core.rows:
                    y = 2 + (m_row - first_row) * ch
                    x = 2 + m_c1 * cw
                    w = (m_c2 - m_c1) * cw
                    is_active = (idx == self._search_current_idx)
                    m_rect = QRect(x, y, w, ch)
                    painter.fillRect(m_rect, pal["match_active"] if is_active else pal["match"])
                    if is_active:
                        painter.setPen(QPen(pal["match_border"], 1.5))
                        painter.drawRect(m_rect.adjusted(0, 0, -1, -1))

        # Selection
        if self._sel_start and self._sel_end:
            rect = self._selection_rect()
            if rect:
                painter.fillRect(rect, pal["sel"])

        # Cursor
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
        self.setFocus(Qt.FocusReason.MouseFocusReason)
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
    def event(self, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab) and not (
                mods
                & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
            ):
                self.keyPressEvent(event)
                return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()

        # In-terminal search shortcut (Ctrl+F)
        if (mods & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_F:
            self.open_search()
            event.accept()
            return

        # F3 for next / Shift+F3 for prev search match
        if key == Qt.Key.Key_F3:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self._on_find_prev(self._search_query, self._search_case)
            else:
                self._on_find_next(self._search_query, self._search_case)
            event.accept()
            return

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
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                steps = abs(delta) // 120 or 1
                self._zoom_font(steps if delta > 0 else -steps)
                event.accept()
                return
        steps = event.angleDelta().y() // 40
        if steps:
            self.scroll_lines(-steps * 3)

    def _zoom_font(self, step: int) -> None:
        size = max(6, min(48, self._font_size + step))
        self._font_size = size
        self.apply_font(self._font.family(), size)

    def focusInEvent(self, event) -> None:  # noqa: N802
        self._blink_state = True
        self.update()
        super().focusInEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        copy_action = menu.addAction("Copy\tCtrl+Shift+C")
        copy_action.triggered.connect(self.copy_selection)
        paste_action = menu.addAction("Paste\tCtrl+Shift+V")
        # triggered() passes its `checked` bool as the first argument —
        # binding it directly would disable the multi-line paste confirmation.
        paste_action.triggered.connect(lambda _checked=False: self.paste_clipboard(confirm=True))
        menu.addSeparator()
        find_action = menu.addAction("Find in terminal…\tCtrl+F")
        find_action.triggered.connect(self.open_search)
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
    """Translate a QKeyEvent to terminal bytes (xterm-ish)."""
    key = event.key()
    mods = event.modifiers()
    text = event.text()

    ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
    alt = bool(mods & Qt.KeyboardModifier.AltModifier)
    shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

    app_cursor = False
    try:
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
            return b"\x1b" + out
        return out
    return None


def _default_mono() -> str:
    if __import__("sys").platform == "win32":
        return "Consolas"
    return "DejaVu Sans Mono"


def _style_runs(cells, pal):
    end = len(cells)
    while end > 0:
        cell = cells[end - 1]
        if cell is not None and cell.data not in ("", " "):
            break
        if cell is not None and cell.bg not in (None, "default"):
            break
        end -= 1

    run_start = 0
    run_chars: list[str] = []
    run_key = None
    run_style = None

    for index in range(end):
        cell = cells[index]
        if cell is None:
            data, key, style = " ", (None,), (pal["fg"], None, False, False, False, False)
        else:
            fg, bg = _colors_for(cell, pal)
            style = (fg, bg, cell.bold, cell.italics, cell.underscore, cell.strikethrough)
            key = (
                fg.rgba(),
                bg.rgba() if bg is not None else None,
                cell.bold,
                cell.italics,
                cell.underscore,
                cell.strikethrough,
            )
            data = cell.data or " "
        if key != run_key:
            if run_chars and run_style is not None:
                yield (run_start, "".join(run_chars), *run_style)
            run_start, run_chars, run_key, run_style = index, [data], key, style
        else:
            run_chars.append(data)
    if run_chars and run_style is not None:
        yield (run_start, "".join(run_chars), *run_style)


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
