"""Minimal Xlib shim (ctypes) used to keep the embedded FreeRDP window fitted.

The built-in RDP display is a FreeRDP-owned X11 window reparented into one of
our widgets (``/parent-window``).  X11 does not propagate a parent resize to
its children, so when the tab changes size — the sidebar is hidden or shown,
the window is dragged — the remote desktop would keep its old geometry and
leave a black gap (or get clipped).  FreeRDP listens for ``ConfigureNotify``
on its window and reacts to a resize by itself (re-scaling with
``/smart-sizing`` or requesting a new resolution with ``/dynamic-resolution``),
so all that is needed is to resize the child window to the surface size.

A reparented child is also not window-managed, so nothing ever moves the X
input (keyboard) focus into it: this module additionally re-asserts focus with
``XSetInputFocus`` (and raises the desktop window) so the embedded client keeps
receiving keystrokes after the app, another tab or another application has
taken focus away.

Only ``XQueryTree``, ``XMoveResizeWindow``, ``XGetInputFocus``,
``XSetInputFocus`` and ``XRaiseWindow`` are used; everything degrades to
``False`` (caller falls back) when no X display / libX11 is available — e.g.
Windows, Wayland-native, headless tests.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from collections.abc import Callable

from ...core.log import get_logger

log = get_logger("rdp.x11")

_XErrorHandler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)


class _XErrorEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("resourceid", ctypes.c_ulong),
        ("serial", ctypes.c_ulong),
        ("error_code", ctypes.c_ubyte),
        ("request_code", ctypes.c_ubyte),
        ("minor_code", ctypes.c_ubyte),
    ]


class XDisplay:
    """A private Xlib connection with a non-fatal error handler.

    Xlib's default error handler *terminates the process* on e.g. BadWindow
    (a FreeRDP window that just went away).  Errors raised on this connection
    are swallowed and remembered instead; errors of other connections are
    forwarded to whatever handler was installed before (Qt's xcb plugin does
    not use Xlib errors, but be a good citizen).
    """

    def __init__(self, name: str | None = None) -> None:
        libname = ctypes.util.find_library("X11") or "libX11.so.6"
        lib = ctypes.CDLL(libname)
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        lib.XQueryTree.restype = ctypes.c_int
        lib.XQueryTree.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ulong)),
            ctypes.POINTER(ctypes.c_uint),
        ]
        lib.XMoveResizeWindow.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
        ]
        lib.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.XFree.argtypes = [ctypes.c_void_p]
        lib.XGetInputFocus.restype = ctypes.c_int
        lib.XGetInputFocus.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.XSetInputFocus.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_ulong,
        ]
        lib.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        lib.XSetErrorHandler.restype = ctypes.c_void_p
        lib.XSetErrorHandler.argtypes = [_XErrorHandler]
        self._lib = lib
        self._dpy = lib.XOpenDisplay(name.encode() if name else None)
        if not self._dpy:
            raise OSError("cannot open X display")
        self.errors = 0
        self._prev_handler: ctypes.c_void_p | None = None
        self._handler = _XErrorHandler(self._on_error)  # keep the callback alive
        prev = lib.XSetErrorHandler(self._handler)
        self._prev_handler = prev

    # -- error handling --------------------------------------------------
    def _on_error(self, dpy, event) -> int:
        if dpy == self._dpy:
            self.errors += 1
            try:
                ev = ctypes.cast(event, ctypes.POINTER(_XErrorEvent)).contents
                log.debug(
                    "X error %d on request %d (resource 0x%x) — ignored",
                    ev.error_code, ev.request_code, ev.resourceid,
                )
            except Exception:  # noqa: BLE001 - diagnostics only
                pass
            return 0
        if self._prev_handler:
            return _XErrorHandler(self._prev_handler)(dpy, event)
        return 0

    # -- queries / requests ---------------------------------------------
    def _query_tree(self, window: int) -> tuple[int, int, list[int]] | None:
        """``(root, parent, children)`` for ``window`` (None on BadWindow)."""
        root = ctypes.c_ulong()
        parent = ctypes.c_ulong()
        kids = ctypes.POINTER(ctypes.c_ulong)()
        count = ctypes.c_uint()
        before = self.errors
        ok = self._lib.XQueryTree(
            self._dpy, window, ctypes.byref(root), ctypes.byref(parent),
            ctypes.byref(kids), ctypes.byref(count),
        )
        if not ok or self.errors != before:
            return None
        out = [int(kids[i]) for i in range(count.value)] if kids else []
        if kids:
            self._lib.XFree(kids)
        return int(root.value), int(parent.value), out

    def children(self, window: int) -> list[int]:
        result = self._query_tree(window)
        return [] if result is None else result[2]

    def top_level(self, window: int) -> int:
        """Return the outermost ancestor of ``window`` (its top-level window).

        Used to tell an in-process window (the app's own top level) from a
        different application's window; 0 when the window is gone.  The walk is
        bounded so a corrupt tree can never loop forever.
        """
        current = int(window)
        for _ in range(128):
            result = self._query_tree(current)
            if result is None:
                return 0
            root, parent, _ = result
            if parent == 0 or parent == root:  # child of root → top level
                return current
            current = parent
        return current

    def move_resize(self, window: int, x: int, y: int, width: int, height: int) -> bool:
        before = self.errors
        self._lib.XMoveResizeWindow(self._dpy, window, x, y, max(1, width), max(1, height))
        self._lib.XSync(self._dpy, 0)  # deliver now; surfaces a BadWindow immediately
        return self.errors == before

    # -- keyboard focus ------------------------------------------------
    def input_focus(self) -> int:
        """Return the window that currently has X input (keyboard) focus."""
        window = ctypes.c_ulong()
        revert = ctypes.c_int()
        before = self.errors
        self._lib.XGetInputFocus(self._dpy, ctypes.byref(window), ctypes.byref(revert))
        if self.errors != before:
            return 0
        return int(window.value)

    def set_input_focus(self, window: int) -> bool:
        """Give ``window`` the X input (keyboard) focus.

        ``RevertToParent`` hands focus back to the parent when the window goes
        away, so the app window stays keyboard-usable if FreeRDP exits.
        """
        before = self.errors
        self._lib.XSetInputFocus(
            self._dpy, ctypes.c_ulong(int(window)), _REVERT_TO_PARENT, _CURRENT_TIME
        )
        self._lib.XSync(self._dpy, 0)  # deliver now; surfaces a BadWindow immediately
        return self.errors == before

    def raise_window(self, window: int) -> bool:
        """Raise ``window`` to the top of its parent's stacking order."""
        before = self.errors
        self._lib.XRaiseWindow(self._dpy, ctypes.c_ulong(int(window)))
        self._lib.XSync(self._dpy, 0)
        return self.errors == before

    def close(self) -> None:
        if self._dpy:
            try:
                self._lib.XCloseDisplay(self._dpy)
            finally:
                self._dpy = None


_display: XDisplay | None = None
_display_failed = False

# X11 core-protocol constants (X.h) — kept local so no extra module is needed.
_REVERT_TO_PARENT = 2
_CURRENT_TIME = 0


def _get_display() -> XDisplay | None:
    global _display, _display_failed
    if _display is not None:
        return _display
    if _display_failed or not os.environ.get("DISPLAY"):
        return None
    try:
        _display = XDisplay()
    except Exception as exc:  # noqa: BLE001 - no libX11 / no server: fall back
        _display_failed = True
        log.info("live resize of the embedded desktop unavailable: %s", exc)
        return None
    return _display


def fit_child_windows(parent_xid: int, width: int, height: int) -> bool:
    """Resize every X child of ``parent_xid`` to fill ``width`` x ``height``.

    Returns True when at least one child (the FreeRDP desktop window) was
    resized; False when there is no X connection, no child yet, or the
    request failed — callers then fall back to their own strategy.
    """
    if not parent_xid or width <= 0 or height <= 0:
        return False
    dpy = _get_display()
    if dpy is None:
        return False
    kids = dpy.children(int(parent_xid))
    if not kids:
        return False
    done = False
    for kid in kids:
        if dpy.move_resize(kid, 0, 0, int(width), int(height)):
            done = True
    return done


def focus_child_windows(parent_xid: int) -> bool:
    """Give the embedded FreeRDP child window X input (keyboard) focus.

    A window reparented through ``/parent-window`` is not managed by the
    window manager, so nothing ever moves keyboard focus into it.  Without an
    explicit ``XSetInputFocus`` the child only receives key events until the
    Qt window (or another app) takes focus away — after which input silently
    stops working.  Re-asserting focus after launch, on tab activation and on
    returning the pointer into the desktop keeps the embedded client's
    keyboard alive.

    Returns True when a child accepted focus; False without an X connection,
    before the client's window exists, or when the request failed.
    """
    if not parent_xid:
        return False
    dpy = _get_display()
    if dpy is None:
        return False
    focused = False
    for kid in dpy.children(int(parent_xid)):
        # Raise first so the desktop (not a transient helper) sits on top, then
        # hand it the keyboard; later children win the stacking order.
        dpy.raise_window(kid)
        if dpy.set_input_focus(kid):
            focused = True
    return focused


def child_has_input_focus(parent_xid: int) -> bool:
    """Whether the X input focus currently sits inside ``parent_xid``.

    True when the focused window is one of the parent's children (the FreeRDP
    desktop window) or a descendant of one; False when the Qt window or any
    other unrelated window holds focus, and without an X connection.
    """
    if not parent_xid:
        return False
    dpy = _get_display()
    if dpy is None:
        return False
    focus = dpy.input_focus()
    if not focus:
        return False
    for kid in dpy.children(int(parent_xid)):
        if focus == kid:
            return True
        if focus in dpy.children(kid):
            return True
    return False


def focus_owned_by_another_app(parent_xid: int) -> bool:
    """Whether X input focus sits on a *different* application's window.

    The focus keeper must never pull the keyboard away from another app, so it
    checks the focused window's top level against ours.  ``None``/``PointerRoot``
    focus and windows that vanished are treated as *not* another app (safe to
    re-assert).
    """
    if not parent_xid:
        return True
    dpy = _get_display()
    if dpy is None:
        return False
    focus = dpy.input_focus()
    if focus in (0, 1):  # None / PointerRoot — not a concrete foreign window
        return False
    ours = dpy.top_level(int(parent_xid))
    theirs = dpy.top_level(focus)
    if not ours or not theirs:
        return False
    return ours != theirs


# Type of the hook the session controller uses (monkeypatchable in tests).
ChildFitter = Callable[[int, int, int], bool]
