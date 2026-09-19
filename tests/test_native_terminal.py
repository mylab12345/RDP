"""Native terminal adapter: whole-surface middle-click paste, Ctrl+wheel
zoom, control-sequence gating and the PTY data path.

The real QTermWidget binding is an optional Linux extra and needs a
displayed desktop, so these tests drive :class:`NativeTerminalView`
against a fake widget with the same surface shape (focus-proxy display +
internal scrollbar + interactive search field) — the adapter code under
test is the production code path.
"""

from __future__ import annotations

import base64
import os
import termios

import pytest
from PySide6.QtCore import QCoreApplication, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit, QScrollBar, QWidget

pytestmark = pytest.mark.usefixtures("home")


class FakeQTerm(QWidget):
    """Stand-in for the optional ``pyside6_qtermwidget`` binding.

    Mirrors the real widget's structure: the terminal display is the focus
    proxy and owns an internal scrollbar; a QLineEdit child represents
    interactive internals (the native search bar) that must keep their own
    middle-click behavior.
    """

    sendData = Signal(str)

    def __init__(self, startnow: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.display = QWidget(self)
        self.setFocusProxy(self.display)
        self.scrollbar = QScrollBar(Qt.Orientation.Vertical, self.display)
        self.search_field = QLineEdit(self.display)
        self.master_fd, self.slave_fd = os.openpty()
        os.set_blocking(self.master_fd, False)
        # Raw output: the pty line discipline would otherwise rewrite \n to
        # \r\n (ONLCR) and blur the byte-fidelity check.
        attrs = termios.tcgetattr(self.slave_fd)
        attrs[1] &= ~termios.OPOST
        termios.tcsetattr(self.slave_fd, termios.TCSANOW, attrs)

    def startTerminalTeletype(self) -> None:
        pass

    def getPtySlaveFd(self) -> int:
        return self.slave_fd


@pytest.fixture()
def native_view(qtapp, monkeypatch):
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui import native_terminal

    monkeypatch.setattr(native_terminal, "_load_qtermwidget", lambda: FakeQTerm)
    view = native_terminal.NativeTerminalView(Settings())
    view.resize(600, 400)
    view.show()
    qtapp.processEvents()  # let the deferred child-filter rescan run
    yield view
    view.close()
    fake = view._native
    for fd in (getattr(fake, "master_fd", -1), getattr(fake, "slave_fd", -1)):
        try:
            if fd is not None and fd >= 0:
                os.close(fd)
        except OSError:
            pass
    view.deleteLater()


def _drain_pty(view) -> bytes:
    try:
        return os.read(view._native.master_fd, 65536)
    except BlockingIOError:
        return b""


def _collect(view) -> list[bytes]:
    emitted: list[bytes] = []
    view.dataWritten.connect(emitted.append)
    return emitted


# ----------------------------------------------------------------------
# PTY data path
# ----------------------------------------------------------------------
def test_feed_reaches_pty(native_view):
    native_view.feed(b"hello\r\n")
    assert _drain_pty(native_view) == b"hello\r\n"


def test_control_sequence_gate_skips_plain_text(native_view):
    """Plain bulk output bypasses the escape-sequence shim entirely, while
    real sequences are still tracked across chunks."""
    view = native_view
    view.feed(b"no escapes here " * 200)
    assert view._control_tail == b""
    assert view._bracketed_paste is False
    view.feed(b"\x1b[?2004h")
    assert view._bracketed_paste is True
    emitted = _collect(view)
    view.paste_text("multi\nline", confirm=False)
    assert emitted == [b"\x1b[200~multi\nline\x1b[201~"]
    view.feed(b"\x1b[?2004l")
    assert view._bracketed_paste is False


def test_osc52_still_detected_through_the_gate(native_view):
    view = native_view
    payloads: list[str] = []
    view.clipboardRequested.connect(payloads.append)
    payload = base64.b64encode(b"osc52-works").decode()
    view.feed(f"\x1b]52;c;{payload}\x07".encode())
    assert payloads == ["osc52-works"]


# ----------------------------------------------------------------------
# Middle-click paste on the whole native surface
# ----------------------------------------------------------------------
def test_middle_click_pastes_on_display(native_view, qtapp):
    view = native_view
    emitted = _collect(view)
    QGuiApplication.clipboard().setText("to-remote")
    QTest.mouseClick(view._native.display, Qt.MouseButton.MiddleButton)
    qtapp.processEvents()
    assert emitted == [b"to-remote"]


def test_middle_click_pastes_on_internal_scrollbar(native_view, qtapp):
    """The internal scrollbar strip belongs to the terminal screen."""
    view = native_view
    emitted = _collect(view)
    QGuiApplication.clipboard().setText("to-remote")
    QTest.mouseClick(view._native.scrollbar, Qt.MouseButton.MiddleButton)
    qtapp.processEvents()
    assert emitted == [b"to-remote"]


def test_middle_click_pastes_on_container(native_view, qtapp):
    """Clicks landing on the container itself (layout margins) also paste."""
    view = native_view
    emitted = _collect(view)
    QGuiApplication.clipboard().setText("to-remote")
    QTest.mouseClick(view, Qt.MouseButton.MiddleButton)
    qtapp.processEvents()
    assert emitted == [b"to-remote"]


def test_middle_click_skips_interactive_children(native_view, qtapp):
    """The native search field keeps its own middle-click (paste into the
    field) — the remote-paste gesture must not hijack text inputs."""
    view = native_view
    emitted = _collect(view)
    QGuiApplication.clipboard().setText("to-remote")
    QTest.mouseClick(view._native.search_field, Qt.MouseButton.MiddleButton)
    qtapp.processEvents()
    assert emitted == []


def test_middle_click_disabled_by_setting(native_view, qtapp):
    view = native_view
    emitted = _collect(view)
    view.settings.paste_on_middle_click = False
    QGuiApplication.clipboard().setText("to-remote")
    QTest.mouseClick(view._native.display, Qt.MouseButton.MiddleButton)
    QTest.mouseClick(view._native.scrollbar, Qt.MouseButton.MiddleButton)
    qtapp.processEvents()
    assert emitted == []


def test_late_created_child_joins_paste_surface(native_view, qtapp):
    """Children created after startup (e.g. the native search bar) are
    picked up by the ChildAdded rescan and paste on middle-click too."""
    view = native_view
    late = QWidget(view._native.display)
    qtapp.processEvents()
    emitted = _collect(view)
    QGuiApplication.clipboard().setText("late-child")
    QTest.mouseClick(late, Qt.MouseButton.MiddleButton)
    qtapp.processEvents()
    assert emitted == [b"late-child"]


def test_paste_middle_click_uses_platform_helper(native_view, monkeypatch, qtapp):
    """The gesture pastes via middle_click_text() — PRIMARY selection first
    on X11/Wayland, clipboard elsewhere."""
    from rdpstudio.ui import native_terminal

    view = native_view
    emitted = _collect(view)
    monkeypatch.setattr(native_terminal, "middle_click_text", lambda: "from-primary")
    QTest.mouseClick(view._native.display, Qt.MouseButton.MiddleButton)
    qtapp.processEvents()
    assert emitted == [b"from-primary"]


# ----------------------------------------------------------------------
# Wheel: Ctrl zooms anywhere on the surface, plain wheel stays native
# ----------------------------------------------------------------------
def _wheel(mods: Qt.KeyboardModifier) -> QWheelEvent:
    return QWheelEvent(
        QPointF(3, 3),
        QPointF(3, 3),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        mods,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_ctrl_wheel_zooms_on_scrollbar(native_view):
    view = native_view
    before = view._font_size
    QCoreApplication.sendEvent(view._native.scrollbar, _wheel(Qt.KeyboardModifier.ControlModifier))
    assert view._font_size == before + 1


def test_plain_wheel_not_consumed(native_view):
    """Without Ctrl the wheel belongs to the native scroller."""
    view = native_view
    before = view._font_size
    assert view.eventFilter(view._native.scrollbar, _wheel(Qt.KeyboardModifier.NoModifier)) is False
    assert view._font_size == before
