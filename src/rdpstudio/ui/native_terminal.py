"""Optional native terminal emulator for Linux.

The normal terminal widget in :mod:`rdpstudio.ui.terminal` is deliberately
pure Qt/Python so KB-Remote remains installable everywhere.  Linux users can
also install the PySide6 bindings for QTermWidget.  QTermWidget is the same
kind of split used by SSH Pilot's VTE backend: a native terminal emulator owns
VT parsing, scrollback and painting, while the application only forwards raw
PTY bytes and input.  That is substantially cheaper than parsing and painting
one remote output burst in Python.

This module is optional by design.  Importing it must never make the normal
PySide6/pyte terminal unavailable when the native library, its Qt ABI, or a
usable display is missing.
"""

from __future__ import annotations

import base64
import binascii
import importlib
import os
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QSocketNotifier, Qt, QTimer, Signal
from PySide6.QtGui import QClipboard, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QMenu, QMessageBox, QWidget

from .terminal import encode_key_event

# QTermWidget's public API is intentionally small.  Keep the import lazy and
# behind a function: the optional wheel is built against a particular Qt ABI
# and can fail with OSError (for example when libGL or the matching Qt library
# is not installed).  A failed optional import is a normal fallback, not an
# application error.
_QTERM_MODULES = ("pyside6_qtermwidget", "QTermWidget")
_qterm_class: Any | None = None
_qterm_import_attempted = False
_qterm_import_error: Exception | None = None

_NATIVE_OSC52_B64 = 1_048_576
_OSC52_PREFIX = b"\x1b]52;"
_OSC_COLOR_Q_RE = re.compile(rb"\x1b\]1([01])\s*;\s*\?\s*(?:\x07|\x1b\\)")
_BPASTE_RE = re.compile(rb"\x1b\[\?2004([hl])")
# DECSET/DECRST 1 = application cursor keys (DECCKM).  QTermWidget tracks
# this internally but does not expose it, and the arrow-key encoding differs
# between the two modes, so the Python input shim tracks it from the stream.
_APP_CURSOR_RE = re.compile(rb"\x1b\[\?1([hl])(?![0-9])")
_CONTROL_PREFIXES = (
    _OSC52_PREFIX,
    b"\x1b[?2004",
    b"\x1b]10;?",
    b"\x1b]11;?",
)


def _load_qtermwidget():
    """Return the optional QTermWidget class, or ``None``.

    Both import names exist in the wild: the PySide6 wheel uses
    ``pyside6_qtermwidget`` while distro/SIP bindings traditionally expose a
    top-level ``QTermWidget`` module.  Do not cache a class from a different Qt
    binding after a failed import.
    """

    global _qterm_class, _qterm_import_attempted, _qterm_import_error
    if _qterm_import_attempted:
        return _qterm_class
    _qterm_import_attempted = True
    for module_name in _QTERM_MODULES:
        try:
            module = importlib.import_module(module_name)
            candidate = getattr(module, "QTermWidget", None)
            if candidate is not None:
                # A system ``QTermWidget`` module may be built for PyQt rather
                # than this application's PySide6 binding.  Such a QWidget
                # cannot be parented into a PySide6 hierarchy safely.
                from PySide6.QtWidgets import QWidget as QtWidget

                if not issubclass(candidate, QtWidget):
                    continue
                _qterm_class = candidate
                _qterm_import_error = None
                return candidate
        except Exception as exc:  # noqa: BLE001 - optional ABI/display dependency
            _qterm_import_error = exc
    return None


def native_terminal_available() -> bool:
    """Whether the optional native terminal binding can be imported.

    ``RDPSTUDIO_TERMINAL_BACKEND=pyte`` is useful for diagnostics and for
    platforms where a native Qt terminal library is present but undesirable.
    Explicit ``native`` still falls back safely if the binding is unavailable.
    """

    if sys.platform != "linux":
        return False
    if os.environ.get("RDPSTUDIO_TERMINAL_BACKEND", "").strip().lower() == "pyte":
        return False
    return _load_qtermwidget() is not None


def native_terminal_import_error() -> Exception | None:
    """Return the last optional import error for diagnostics."""

    _load_qtermwidget()
    return _qterm_import_error


def should_use_native_terminal(settings) -> bool:
    """Resolve the terminal backend policy for one new terminal tab.

    The automatic policy is conservative in headless/offscreen test runs and
    on non-Linux platforms.  Even an explicit ``native`` request requires a
    real display; construction still has a guarded fallback in
    :func:`rdpstudio.ui.terminal.make_terminal_view`.
    """

    requested = os.environ.get("RDPSTUDIO_TERMINAL_BACKEND", "").strip().lower()
    if not requested:
        requested = str(getattr(settings, "terminal_backend", "auto") or "auto").lower()
    if requested in {"pyte", "python", "fallback", "legacy", "off", "false", "0"}:
        return False
    if requested not in {"auto", "native", "qtermwidget"}:
        requested = "auto"
    if not native_terminal_available():
        return False
    # QTermWidget is a real GUI widget.  Avoid replacing the deterministic
    # pyte view for offscreen/no-display test and screenshot processes.  An
    # explicit request cannot make a native widget useful without a display;
    # the safe fallback is preferable to a construction failure.
    if os.environ.get("QT_QPA_PLATFORM", "").strip().lower() in {
        "offscreen",
        "minimal",
        "minimalegl",
    }:
        return False
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _osc_color_reply(code: int, r: int, g: int, b: int) -> bytes:
    # xterm reports 16-bit components.  Repeat the 8-bit value as the native
    # terminal palettes do, which is understood by bash/readline and TUIs.
    return f"\x1b]{code};rgb:{r:02x}{r:02x}/{g:02x}{g:02x}/{b:02x}{b:02x}\x1b\\".encode(
        "ascii"
    )


def _default_mono() -> str:
    return "DejaVu Sans Mono" if sys.platform != "win32" else "Consolas"


class NativeTerminalView(QWidget):
    """QTermWidget-backed terminal view with KB-Remote's small public API.

    QTermWidget's ``startTerminalTeletype`` creates an empty PTY and exposes
    its slave fd.  Remote/local controllers write output to that fd; native
    ``sendData`` signals carry key presses back to the controller.  No shell or
    SSH process is owned here, so the existing lifecycle, authentication,
    reconnect, logging and SFTP code stays unchanged.
    """

    dataWritten = Signal(bytes)
    sizeChanged = Signal(int, int)  # columns, rows
    titleChanged = Signal(str)
    clipboardRequested = Signal(str)
    bellRequested = Signal()
    linkActivated = Signal(str)

    def __init__(self, settings, parent: QWidget | None = None, *, native_colors: bool = False) -> None:
        super().__init__(parent)
        qterm_class = _load_qtermwidget()
        if qterm_class is None:
            error = native_terminal_import_error()
            raise RuntimeError(f"native terminal backend unavailable: {error}")

        self.settings = settings
        self.native_colors = bool(native_colors)
        self._native = qterm_class(0, self)
        self._pty_fd = -1
        self._pending_output: deque[memoryview] = deque()
        self._pending_output_bytes = 0
        self._control_tail = b""
        self._osc52_pending: bytearray | None = None
        self._bracketed_paste = False
        self._app_cursor = False
        self._closed = False
        self._last_size: tuple[int, int] | None = None
        self._last_title = ""
        self._font = QFont(getattr(settings, "font_family", "") or _default_mono())
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setPointSize(max(6, int(getattr(settings, "font_size", 10))))
        self._font_size = self._font.pointSize()
        self._log_file = None
        self._log_path: Path | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._native)

        self._configure_native()
        self._connect_native_signals()
        # Keystroke shim: several pyside6_qtermwidget builds cannot marshal
        # the ``sendData(const char*, int)`` signal into Python (the binding
        # raises "parameter 0 of type const char* cannot be converted" and
        # the bytes are silently dropped), which makes typing dead or
        # intermittent.  Intercept key events in Python before QTermWidget
        # sees them and encode them here instead; keys this shim does not
        # encode still fall through to the native widget (and a working
        # sendData binding).
        # QTermWidget forwards keyboard input to an *internal* child widget
        # (its focus proxy), so the filter must be installed there — a
        # filter on the container never sees the key events.
        self._key_targets = [
            w for w in (
                getattr(self._native, "focusProxy", lambda: None)(),
                self._native,
            )
            if w is not None
        ]
        for target in self._key_targets:
            target.installEventFilter(self)
        try:
            self._native.startTerminalTeletype()
            self._pty_fd = int(self._native.getPtySlaveFd())
        except Exception as exc:  # noqa: BLE001
            self._native.deleteLater()
            raise RuntimeError(f"could not start native terminal emulator: {exc}") from exc
        if self._pty_fd < 0:
            raise RuntimeError("native terminal emulator returned an invalid PTY")

        # The fd is only the input side of QTermWidget's empty PTY.  Making it
        # non-blocking lets a noisy VM queue briefly without freezing the GUI;
        # QSocketNotifier drains the lossless queue as the emulator consumes it.
        try:
            os.set_blocking(self._pty_fd, False)
        except (OSError, AttributeError):
            pass
        self._write_notifier = QSocketNotifier(
            self._pty_fd, QSocketNotifier.Type.Write, self
        )
        self._write_notifier.setEnabled(False)
        self._write_notifier.activated.connect(self._flush_native_output)

        self._size_timer = QTimer(self)
        self._size_timer.setSingleShot(True)
        self._size_timer.setInterval(40)
        self._size_timer.timeout.connect(self._emit_size_if_changed)
        self.setFocusPolicy(self._native.focusPolicy())
        self.setFocusProxy(self._native)
        self._emit_size_if_changed()

    def setFocus(self, reason=None):  # noqa: N802 - Qt API compatibility
        """Keep controller focus requests on the actual native terminal."""
        native = getattr(self, "_native", None)
        if native is None:
            return super().setFocus() if reason is None else super().setFocus(reason)
        if reason is None:
            return native.setFocus()
        return native.setFocus(reason)

    # ------------------------------------------------------------------
    # Native setup and signals
    # ------------------------------------------------------------------
    def _configure_native(self) -> None:
        native = self._native
        operations = (
            ("terminal size hint", lambda: native.setTerminalSizeHint(False)),
            ("history", lambda: native.setHistorySize(int(self.settings.scrollback_lines))),
            ("font", lambda: native.setTerminalFont(self._font)),
            ("flow control", lambda: native.setFlowControlEnabled(False)),
            (
                "cursor shape",
                lambda: native.setKeyboardCursorShape(
                    getattr(native, {
                        "underline": "UnderlineCursor",
                        "bar": "IBeamCursor",
                    }.get(str(getattr(self.settings, "cursor_style", "block")), "BlockCursor"), 0)
                ),
            ),
            ("cursor blink", lambda: native.setBlinkingCursor(True)),
            (
                "scrollbar",
                lambda: native.setScrollBarPosition(getattr(native, "ScrollBarRight", 2)),
            ),  # right
            # The native widget must never show its own multiline-paste
            # confirmation: Ctrl+Shift+V and middle-click in this widget
            # route through paste_clipboard(confirm=False) and the
            # context menu offers its own optional confirm. A native prompt
            # here would be a second, surprising permission dialog.
            ("confirm paste", lambda: native.setConfirmMultilinePaste(False)),
            ("word characters", lambda: native.setWordCharacters("@-./_~")),
            (
                "context menu",
                # The native menu's paste action emits ``sendData``, which is
                # exactly the path some PySide bindings cannot marshal; route
                # clipboard actions through this widget's own menu instead.
                lambda: native.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu),
            ),
        )
        for _name, operation in operations:
            try:
                operation()
            except Exception:  # noqa: BLE001 - old distro bindings vary
                pass
        try:
            # Linux is the closest equivalent to SSH Pilot's native VTE
            # default.  The remote host's SGR colors still win per cell.
            scheme = "Linux"
            if not self.native_colors and str(self.settings.theme) in {
                "light",
                "meadow",
                "desert",
            }:
                scheme = "BlackOnWhite"
            native.setColorScheme(scheme)
        except Exception:
            pass

    def _connect_native_signals(self) -> None:
        native = self._native
        # ``sendData(const char*, int)`` is unusable on several PySide
        # bindings: the ``const char*`` argument cannot be marshalled into
        # Python, so connecting it only produces TypeErrors (and dropped
        # keystrokes) at every emission.  Probe it once; only rely on it
        # when a round-trip actually works — the key-event shim in
        # :meth:`eventFilter` is the keyboard path otherwise.
        if self._send_data_works(native):
            native.sendData.connect(self._on_native_send_data)
        for signal_name, callback in (
            ("titleChanged", self._on_native_title_changed),
            ("bell", self._on_native_bell),
            ("finished", self._on_native_finished),
            ("copyAvailable", self._on_native_copy_available),
            ("urlActivated", self._on_native_url_activated),
        ):
            try:
                getattr(native, signal_name).connect(callback)
            except Exception:
                pass

    @staticmethod
    def _send_data_works(native) -> bool:
        # ``const char*`` signal arguments cannot be marshalled into Python
        # by several pyside6_qtermwidget builds (emitting them raises
        # "parameter 0 of type const char* cannot be converted" and drops
        # the bytes).  Detect that case from the signature itself.
        try:
            return "const char" not in str(native.sendData)
        except Exception:  # noqa: BLE001 - defensive
            return True

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        """Encode key events for the host before QTermWidget handles them.

        See the note in ``__init__``: on bindings where ``sendData`` cannot
        cross into Python, this shim is the only working keyboard path.
        """
        targets = getattr(self, "_key_targets", ())
        if obj not in targets or self._closed:
            return super().eventFilter(obj, event)
        etype = event.type()
        if etype == QEvent.Type.ShortcutOverride:
            # QActions/QShortcuts are resolved before KeyPress.  Claim all
            # encodable terminal keys so window commands never steal native
            # shell editing (Ctrl+B/K/P/W, Home/End, function keys, …).
            mode_stub = type(
                "_ModeStub", (), {"mode": {1 << 5} if self._app_cursor else set()}
            )()
            if encode_key_event(event, mode_stub) is not None:
                event.accept()
                return True
            return False
        if etype == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            alt = bool(mods & Qt.KeyboardModifier.AltModifier)

            # Match native terminal conventions: use Ctrl+Shift+C/V for the
            # clipboard, leaving bare Ctrl+C and Ctrl+V for the remote shell.
            if ctrl and shift and not alt:
                if key == Qt.Key.Key_V:
                    self.paste_clipboard(confirm=False)
                    return True
                if key == Qt.Key.Key_C:
                    self.copy_selection()
                    return True
                if key == Qt.Key.Key_F:
                    self.open_search()
                    return True

            data = encode_key_event(
                event, type("_ModeStub", (), {"mode": {1 << 5} if self._app_cursor else set()})()
            )
            if data is not None:
                self.dataWritten.emit(bytes(data))
                try:
                    self.scroll_to_bottom()
                except Exception:
                    pass
                return True
            # Not an encodable terminal key (shortcuts, modifiers…): let the
            # native widget / Qt handle it.
            return False
        if etype == QEvent.Type.Wheel:
            # Ctrl + mouse wheel zooms the terminal font (same as the pyte
            # view).  Without Ctrl the wheel belongs to the native scroller.
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                delta = event.angleDelta().y()
                if delta:
                    steps = abs(delta) // 120 or 1
                    self._zoom_font(steps if delta > 0 else -steps)
                return True
            return False
        if etype == QEvent.Type.InputMethod:
            commit = event.commitString()
            if commit:
                self.write_user(commit.encode("utf-8"))
                return True
            return False
        if etype == QEvent.Type.MouseButtonPress:
            # Middle-click pastes the clipboard directly, no confirmation.
            # Consume the event so the underlying QTermWidget can't double
            # handle (or ignore) it — this binding's native middle-click is
            # unreliable.
            if event.button() == Qt.MouseButton.MiddleButton:
                if bool(getattr(self.settings, "paste_on_middle_click", True)):
                    self.paste_clipboard(confirm=False)
                return True
            return False
        return False

    def _on_native_send_data(self, *args) -> None:
        if not args:
            return
        raw = args[0]
        length = None
        if len(args) > 1:
            try:
                length = int(args[1])
            except (TypeError, ValueError):
                length = None
        if isinstance(raw, str):
            data = raw.encode("utf-8", "replace")
        else:
            try:
                data = bytes(raw)
            except Exception:  # noqa: BLE001
                data = str(raw).encode("utf-8", "replace")
        if length is not None:
            data = data[: max(0, length)]
        if data:
            self.dataWritten.emit(data)

    def _on_native_title_changed(self, *args) -> None:
        title = ""
        if args and isinstance(args[0], str):
            title = args[0]
        try:
            title = title or str(self._native.title() or "")
        except Exception:
            pass
        if title and title != self._last_title:
            self._last_title = title
            self.titleChanged.emit(title)

    def _on_native_bell(self, *_args) -> None:
        self.bellRequested.emit()

    def _on_native_copy_available(self, available: bool = False) -> None:
        if available and bool(getattr(self.settings, "copy_on_select", True)):
            self.copy_selection()

    def _on_native_url_activated(self, url, *_args) -> None:
        try:
            value = url.toString()
        except AttributeError:
            value = str(url)
        if value:
            self.linkActivated.emit(value)

    def _on_native_finished(self, *_args) -> None:
        # The controller owns the real child and emits its own close signal;
        # this signal only exists for the adapter's completeness.
        pass

    # ------------------------------------------------------------------
    # Data path
    # ------------------------------------------------------------------
    def feed(self, data: bytes) -> None:
        if self._closed or not data:
            return
        raw = bytes(data)
        self._log_output(raw)
        self._inspect_control_sequences(raw)
        self._pending_output.append(memoryview(raw))
        self._pending_output_bytes += len(raw)
        # Never discard terminal bytes: losing an escape sequence in the
        # middle of a TUI redraw is worse than briefly retaining a queue. The
        # non-blocking fd keeps this path off the GUI's blocking I/O path, and
        # SSHWorker/local PTY backpressure bounds normal production growth.
        self._flush_native_output()

    def _flush_native_output(self, *_args) -> None:
        if self._closed or self._pty_fd < 0:
            return
        while self._pending_output:
            chunk = self._pending_output[0]
            try:
                written = os.write(self._pty_fd, chunk)
            except BlockingIOError:
                self._write_notifier.setEnabled(True)
                return
            except OSError:
                self._write_notifier.setEnabled(False)
                return
            if written <= 0:
                self._write_notifier.setEnabled(True)
                return
            self._pending_output_bytes -= written
            if written == len(chunk):
                self._pending_output.popleft()
            else:
                self._pending_output[0] = chunk[written:]
        self._write_notifier.setEnabled(False)

    def _inspect_control_sequences(self, data: bytes) -> None:
        # QTermWidget handles terminal parsing in C++ but portable builds do
        # not all implement OSC-52 or OSC 10/11 reports.  Keep this tiny
        # protocol shim so existing clipboard/theme behavior does not regress;
        # it does not parse screen cells or paint anything.  The small tail and
        # OSC-52 state make sequences split across PTY frames behave correctly.
        self._consume_osc52(data)
        window = self._control_tail + data
        for match in _BPASTE_RE.finditer(window):
            self._bracketed_paste = match.group(1) == b"h"
        for match in _APP_CURSOR_RE.finditer(window):
            self._app_cursor = match.group(1) == b"h"
        replies = bytearray()
        for match in _OSC_COLOR_Q_RE.finditer(window):
            code = 10 + int(match.group(1))
            color = (170, 170, 170) if code == 10 else (0, 0, 0)
            replies += _osc_color_reply(code, *color)
        if replies:
            self.dataWritten.emit(bytes(replies))
        self._control_tail = self._possible_control_tail(window)

    def _consume_osc52(self, data: bytes) -> None:
        """Decode complete OSC-52 clipboard reports without a large parser."""
        stream = bytes(self._osc52_pending or b"") + data
        self._osc52_pending = None
        cursor = 0
        while True:
            start = stream.find(_OSC52_PREFIX, cursor)
            if start < 0:
                self._osc52_pending = bytearray(self._suffix_prefix(stream[cursor:]))
                return
            header_end = stream.find(b";", start + len(_OSC52_PREFIX))
            if header_end < 0:
                pending = stream[start:]
                self._osc52_pending = bytearray(
                    pending
                    if len(pending) <= 128
                    else self._suffix_prefix(pending)
                )
                return
            payload_start = header_end + 1
            bel = stream.find(b"\x07", payload_start)
            st = stream.find(b"\x1b\\", payload_start)
            ends = [end for end in (bel, st) if end >= 0]
            if not ends:
                pending = stream[start:]
                if len(pending) <= len(_OSC52_PREFIX) + _NATIVE_OSC52_B64 + 128:
                    self._osc52_pending = bytearray(pending)
                # A malformed oversized report is deliberately discarded.
                return
            end = min(ends)
            payload = stream[payload_start:end]
            if 0 < len(payload) <= _NATIVE_OSC52_B64:
                try:
                    text = base64.b64decode(payload, validate=True).decode(
                        "utf-8", "replace"
                    )
                except (ValueError, binascii.Error):
                    pass
                else:
                    self.clipboardRequested.emit(text)
            cursor = end + (1 if end == bel else 2)

    @staticmethod
    def _suffix_prefix(data: bytes) -> bytes:
        """Keep only bytes that can begin one of the small control probes."""
        best = b""
        for start in range(max(0, len(data) - 16), len(data)):
            suffix = data[start:]
            if len(suffix) > len(best) and any(
                prefix.startswith(suffix) for prefix in _CONTROL_PREFIXES
            ):
                best = suffix
        return best

    @staticmethod
    def _possible_control_tail(data: bytes) -> bytes:
        return NativeTerminalView._suffix_prefix(data)

    # ------------------------------------------------------------------
    # API shared with TerminalView/controllers
    # ------------------------------------------------------------------
    def font(self) -> QFont:
        return QFont(self._font)

    def apply_font(self, family: str, size: int) -> None:
        self._font = QFont(family or _default_mono())
        self._font.setStyleHint(QFont.StyleHint.Monospace)
        self._font.setPointSize(max(6, int(size)))
        self._font_size = self._font.pointSize()
        try:
            self._native.setTerminalFont(self._font)
        except Exception:
            pass
        self._size_timer.start()

    def _zoom_font(self, step: int) -> None:
        """Ctrl+wheel font zoom, clamped to the same range as the pyte view."""
        size = max(6, min(48, self._font_size + step))
        if size != self._font_size:
            self.apply_font(self._font.family(), size)

    def apply_theme(self) -> None:
        """Refresh the native palette without restarting the session."""
        try:
            scheme = "Linux"
            if not self.native_colors and str(self.settings.theme) in {
                "light",
                "meadow",
                "desert",
            }:
                scheme = "BlackOnWhite"
            self._native.setColorScheme(scheme)
        except Exception:
            pass

    def cols_rows(self) -> tuple[int, int]:
        try:
            cols = int(self._native.screenColumnsCount())
            rows = int(self._native.screenLinesCount())
            if cols > 0 and rows > 0:
                return cols, rows
        except Exception:
            pass
        # Before the first allocation QTermWidget may report zero.  Use the
        # same conservative geometry as the fallback view until it does.
        fm = QFontMetrics(self._font)
        cell_w = max(4, fm.horizontalAdvance("M"))
        cell_h = max(6, fm.height())
        return max(2, (self.width() - 4) // cell_w), max(2, (self.height() - 4) // cell_h)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._size_timer.start()

    def _emit_size_if_changed(self) -> None:
        size = self.cols_rows()
        if size != self._last_size:
            self._last_size = size
            self.sizeChanged.emit(*size)

    def write_user(self, data: bytes) -> None:
        if data:
            self.dataWritten.emit(bytes(data))

    def send_text(self, text: str) -> None:
        self.write_user(text.encode("utf-8"))

    def open_search(self) -> None:
        try:
            self._native.toggleShowSearchBar()
        except Exception:
            pass

    def close_search(self) -> None:
        # QTermWidget's search bar owns its own close action; toggling is the
        # least surprising fallback for callers that expose a close command.
        try:
            self._native.toggleShowSearchBar()
        except Exception:
            pass

    def has_selection(self) -> bool:
        try:
            return bool(self._native.selectedText())
        except Exception:
            return False

    def selection(self) -> str:
        try:
            return str(self._native.selectedText(True) or "")
        except Exception:
            return ""

    def copy_selection(self) -> None:
        try:
            self._native.copyClipboard()
        except Exception:
            text = self.selection()
            if text:
                QGuiApplication.clipboard().setText(text, QClipboard.Mode.Clipboard)

    def paste_clipboard(self, confirm: bool = True) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self.paste_text(text, confirm=confirm)

    def paste_text(self, text: str, confirm: bool = True) -> None:
        if not text:
            return
        if confirm and bool(getattr(self.settings, "confirm_multiline_paste", True)) and (
            "\n" in text or len(text) > 200
        ):
            preview = text if len(text) < 400 else text[:400] + "…"
            answer = QMessageBox.question(
                self,
                "Paste multiple lines?",
                f"Paste the following to the remote host?\n\n{preview}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        payload = text.encode("utf-8")
        if self._bracketed_paste:
            payload = b"\x1b[200~" + payload + b"\x1b[201~"
        self.write_user(payload)
        self.scroll_to_bottom()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        copy_action = menu.addAction("Copy\tCtrl+Shift+C")
        copy_action.triggered.connect(self.copy_selection)
        paste_action = menu.addAction("Paste\tCtrl+Shift+V")
        paste_action.triggered.connect(
            lambda _checked=False: self.paste_clipboard(confirm=True)
        )
        menu.addSeparator()
        select_all = menu.addAction("Select all")
        select_all.triggered.connect(self.select_all)
        clear_sb = menu.addAction("Clear scrollback")
        clear_sb.triggered.connect(self.clear_scrollback)
        search = menu.addAction("Find in terminal…\tCtrl+Shift+F")
        search.triggered.connect(self.open_search)
        menu.exec(event.globalPos())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # The event filter on the native widget handles terminal keys; this
        # widget only receives keys when it (not the native child) has focus.
        native = getattr(self, "_native", None)
        if native is not None:
            data = encode_key_event(
                event,
                type("_ModeStub", (), {"mode": {1 << 5} if self._app_cursor else set()})(),
            )
            if data is not None:
                self.dataWritten.emit(bytes(data))
                return
        super().keyPressEvent(event)

    def select_all(self) -> None:
        try:
            # QTermWidget exposes selection coordinates rather than the
            # QWidget selectAll() convenience used by text edits.
            rows = int(self._native.historyLinesCount()) + int(self._native.screenLinesCount())
            cols = int(self._native.screenColumnsCount())
            self._native.setSelectionStart(0, 0)
            self._native.setSelectionEnd(max(0, rows - 1), max(0, cols - 1))
        except Exception:
            pass

    def clear_scrollback(self) -> None:
        try:
            self._native.clear()
        except Exception:
            pass

    def scroll_to_bottom(self) -> None:
        try:
            self._native.scrollToEnd()
        except Exception:
            pass

    def scroll_lines(self, _n: int) -> None:
        # The native widget owns the scroll model.  Mouse wheel events are
        # handled by QTermWidget; this method is retained for controller/API
        # compatibility and intentionally avoids synthesizing wheel events.
        return

    def start_logging(self, path: str | Path) -> None:
        self.stop_logging()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._log_file = open(p, "a", encoding="utf-8", buffering=1)
        self._log_path = p
        self._log_file.write(
            f"\n--- KB-Remote Session Log Started: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
        )

    def _log_output(self, data: bytes) -> None:
        if self._log_file is None:
            return
        try:
            text = data.decode("utf-8", "replace")
            clean = re.sub(r"\x1b\[[0-9;?<=>!\"#$%&'()*+,\-./ ]*[@-~]", "", text)
            clean = re.sub(r"\x1b\].*?(\x07|\x1b\\)", "", clean)
            self._log_file.write(clean)
        except Exception:
            pass

    def stop_logging(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.write(
                    f"\n--- KB-Remote Session Log Ended: {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n"
                )
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None
            self._log_path = None

    def is_logging(self) -> bool:
        return self._log_file is not None

    def log_path(self) -> Path | None:
        return self._log_path

    def close(self) -> None:
        self._closed = True
        try:
            self._write_notifier.setEnabled(False)
        except Exception:
            pass
        self._pending_output.clear()
        self._pending_output_bytes = 0
        self.stop_logging()
        super().close()

    def deleteLater(self) -> None:
        self._closed = True
        try:
            self._write_notifier.setEnabled(False)
        except AttributeError:
            pass
        except Exception:
            pass
        super().deleteLater()


__all__ = [
    "NativeTerminalView",
    "native_terminal_available",
    "native_terminal_import_error",
    "should_use_native_terminal",
]
