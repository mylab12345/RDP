"""Main window: tabbed sessions, sidebar, toolbar, quick connect, tools & command palette."""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core import paths
from ..core.log import get_logger
from ..core.models import Session
from ..core.plugin import (
    SessionContext,
    SessionController,
    SessionState,
    registry,
)
from . import theme
from .command_bar import (
    CommandBar,
    _HistoryLineEdit,  # noqa: F401  (compat re-export)
)
from .command_palette import CommandPaletteDialog
from .dashboard import DashboardMixin
from .docking import DockDragFilter
from .main_actions import MainActionsMixin
from .sidebar import SessionTree
from .theme import icon, palette, protocol_badge
from .widgets import STATE_COLORS, StateChip, animate_in, pulse, toast

log = get_logger("ui.main")

_MAX_IMPORT_BYTES = 32 * 1024 * 1024

# Session tab strip edges: "top" is the classic horizontal strip, "left" and
# "right" turn it into a vertical rail like MobaXterm's side panels.
_TAB_STRIP_POSITIONS = {
    "top": QTabWidget.TabPosition.North,
    "left": QTabWidget.TabPosition.West,
    "right": QTabWidget.TabPosition.East,
}
_TAB_STRIP_LABELS = {
    "top": "Tabs on top",
    "left": "Tabs on the left edge",
    "right": "Tabs on the right edge",
}

_MAIN = None




def get_main_window(widget=None) -> MainWindow | None:
    global _MAIN
    if _MAIN is not None:
        return _MAIN
    app = QApplication.instance()
    if app is not None:
        for w in app.topLevelWidgets():
            if isinstance(w, MainWindow):
                _MAIN = w
                return w
    return None


class SessionTab(QWidget):
    """One tab: hosts a SessionController + modern auto-hiding toolbar."""

    def __init__(self, controller: SessionController, main: MainWindow) -> None:
        super().__init__()
        self.controller = controller
        self.main = main
        self._custom_title: str | None = None
        self._toolbar_visible = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Compact session header — chips, info, actions
        header = QWidget()
        header.setObjectName("header")
        header.setMinimumHeight(36)
        header.setMaximumHeight(36)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 5, 10, 5)
        h.setSpacing(8)

        self.chip = StateChip("connecting", "info")
        h.addWidget(self.chip)

        self.rec_chip = StateChip("● REC", "bad")
        self.rec_chip.setVisible(False)
        self.rec_chip.setToolTip("Logging active session output to file")
        h.addWidget(self.rec_chip)

        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.info.setStyleSheet("font-size: 11.5px; font-weight: 400;")
        h.addWidget(self.info, 1)

        # Session action buttons — compact icon-style
        self._themed_buttons: list[tuple[QPushButton, str, str | None]] = []

        def make_action_btn(text, icon_name, tip, cb):
            b = QPushButton(text)
            if icon_name:
                b.setIcon(icon(icon_name, palette()["fg_dim"]))
                self._themed_buttons.append((b, icon_name, None))
            b.setObjectName("subtle")
            b.setToolTip(tip)
            b.clicked.connect(cb)
            b.setFixedHeight(26)
            b.setFixedWidth(74)
            b.setStyleSheet(
                b.styleSheet()
                + "font-size: 11.5px; font-weight: 500; padding: 1px 10px; "
                + "border-radius: 6px;"
            )
            return b

        # One state-aware action button: Stop while live, Reconnect when down.
        self.btn_reconnect = QPushButton("Stop")
        self.btn_reconnect.setIcon(icon("stop", palette()["accent_text"]))
        self.btn_reconnect.setObjectName("primary")
        self.btn_reconnect.clicked.connect(self._on_action_btn)
        self.btn_reconnect.setVisible(False)
        self.btn_reconnect.setFixedHeight(26)
        self.btn_reconnect.setFixedWidth(88)
        self.btn_reconnect.setStyleSheet(
            self.btn_reconnect.styleSheet()
            + "font-size: 11.5px; font-weight: 600; padding: 1px 12px; "
            + "border-radius: 6px;"
        )
        h.addWidget(self.btn_reconnect)

        caps = controller.capabilities()

        if caps.sftp:
            b = make_action_btn("Files", "folder", "Browse remote files (SFTP)", controller.open_sftp)
            h.addWidget(b)

        if caps.file_sharing:
            b = make_action_btn(
                "Share",
                "transfer",
                "Share local folders with this machine over SFTP",
                lambda: self.main.open_share_for_session(controller.definition),
            )
            h.addWidget(b)

        # Close button for the tab
        close_btn = QPushButton()
        close_btn.setIcon(icon("close"))
        self._themed_buttons.append((close_btn, "close", None))
        close_btn.setObjectName("tabClose")
        close_btn.setToolTip("Close this session tab")
        close_btn.setFixedSize(22, 22)
        close_btn.setIconSize(QSize(13, 13))
        close_btn.clicked.connect(lambda: self.main.close_tab(self.main.tabs.indexOf(self)))
        h.addWidget(close_btn)

        layout.addWidget(header)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        layout.addWidget(line)

        self._content = controller.widget()
        layout.addWidget(self._content, 1)

        # MobaXterm-style command line below the terminal (shell tabs only)
        self.command_bar = None
        if caps.shell:
            self.command_bar = CommandBar()
            self.command_bar.commandSent.connect(self._on_command_sent)
            layout.addWidget(self.command_bar)

        widget_changed = getattr(controller, "widgetChanged", None)
        if widget_changed is not None:
            widget_changed.connect(self._swap_content)

        controller.stateChanged.connect(self._on_state)
        controller.statusInfo.connect(self._on_status)
        controller.finished.connect(self._on_finished)
        controller.reconnectScheduled.connect(self._on_reconnect_scheduled)

    def _swap_content(self) -> None:
        old = self._content
        if old is None:
            return
        layout = self.layout()
        layout.removeWidget(old)
        old.hide()
        self._content = self.controller.widget()
        # Reinsert after the header divider and before the command bar.
        layout.insertWidget(2, self._content, 1)
        self._content.show()

    def _on_command_sent(self, text: str) -> None:
        self.main._on_command_sent(self, text)

    def _on_action_btn(self) -> None:
        if self.controller.state() == SessionState.CONNECTED:
            self.controller.stop("stopped by user")
        else:
            self.controller.request_reconnect()

    def _refresh_theme(self) -> None:
        """Re-tint header icons/chips after a live theme switch."""
        pal = palette()
        self.chip.refresh_theme()
        self.rec_chip.refresh_theme()
        for btn, icon_name, tint_key in self._themed_buttons:
            tint = pal.get(tint_key) if tint_key else None
            btn.setIcon(icon(icon_name, tint))
        # Re-runs chip colour, button icon and visibility — idempotent.
        self._on_state(self.controller.state())

    def _on_state(self, state: str) -> None:
        pal = palette()
        self.chip.setText((state or "").upper())
        self.chip.set_color(STATE_COLORS.get(state, "fg_dim"))
        visible = state in (SessionState.CONNECTED, SessionState.CLOSED, SessionState.FAILED)
        if visible and not self.btn_reconnect.isVisible():
            # first live connection: pulse the state chip once
            if state == SessionState.CONNECTED:
                pulse(self.chip)
        self.btn_reconnect.setVisible(visible)
        if state == SessionState.CONNECTED:
            self.btn_reconnect.setText("Stop")
            self.btn_reconnect.setIcon(icon("stop", pal["accent_text"]))
            self.btn_reconnect.setToolTip("Stop this session")
        else:
            self.btn_reconnect.setText("Reconnect")
            self.btn_reconnect.setIcon(icon("connect", pal["accent_text"]))
            self.btn_reconnect.setToolTip("Reconnect this session")

    def _on_status(self, info: dict) -> None:
        if "connected" in info:
            c = info["connected"]
            user = c.get("username", "")
            host = c.get("host", "")
            cipher = c.get("cipher", "")
            ver = c.get("remote_version", "").split("\n")[0] if c.get("remote_version") else ""
            parts = []
            if user and host:
                parts.append(f"{user}@{host}")
            elif host:
                parts.append(host)
            if cipher:
                parts.append(cipher)
            if ver:
                parts.append(ver[:32])
            self.info.setText("  ·  ".join(parts))
        if "status_text" in info and info["status_text"]:
            self.chip.setText(info["status_text"][:40])
        if info.get("error"):
            self.info.setText(str(info["error"]))

    def _on_reconnect_scheduled(self, attempt: int, delay: float) -> None:
        self.chip.setText(f"reconnecting #{attempt} in {delay:.1f}s")
        self.chip.set_color("warn")

    def _on_finished(self, reason: str) -> None:
        self.chip.setText("closed")
        self.chip.set_color("fg_dim")
        self.btn_reconnect.setVisible(True)
        if reason and "user" not in reason:
            self.info.setText(reason)


class MainWindow(DashboardMixin, MainActionsMixin, QMainWindow):
    def __init__(self, ctx: SessionContext) -> None:
        super().__init__()
        global _MAIN
        _MAIN = self
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon("logo"))
        self.resize(1380, 880)
        self.setMinimumSize(1024, 640)
        self.controllers: dict[int, SessionTab] = {}
        # Last "connected" info per controller, for the status-bar summary.
        self._last_connected_info: dict[int, dict] = {}
        # Open (non-modal) tool dialogs keyed by controller id — reuse instead
        # of stacking a new window on every click.
        self._tool_dialogs: dict[int, QWidget] = {}

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._bind_shortcuts()
        self._setup_tray()
        # Live theme switches re-tint icons and palette-baked chrome.
        theme.add_theme_changed_callback(self._refresh_theme)

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)

        # Modern status bar — session info left, connection state right
        self.session_info_label = QLabel("")
        self.session_info_label.setObjectName("statusSession")
        status.addWidget(self.session_info_label, 1)

        self.status_label = QLabel("STANDBY")
        self.status_label.setObjectName("caption")
        status.addPermanentWidget(self.status_label)

        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(30_000)
        self._lock_timer.timeout.connect(self._autolock)
        self._lock_timer.start()

        # Opt-in: bring the share listener up with the app. Deferred so a
        # socket error surfaces as a toast after the window is visible rather
        # than during construction.
        QTimer.singleShot(400, self._autostart_share_server)

        geo = ctx.settings.geometry
        if isinstance(geo, dict) and geo.get("size"):
            try:
                w, h = int(geo["size"][0]), int(geo["size"][1])
                if w >= 400 and h >= 300:
                    self.resize(QSize(w, h))
                if geo.get("pos"):
                    self.move(QPoint(int(geo["pos"][0]), int(geo["pos"][1])))
                if geo.get("maximized"):
                    self.showMaximized()
            except (TypeError, ValueError, KeyError, IndexError):
                pass

    # ------------------------------------------------------------------


    def _build_body(self) -> None:
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setHandleWidth(4)

        self.sidebar = SessionTree(self.ctx.store)
        self.main_splitter.addWidget(self.sidebar)

        # Center tabbed container
        tabs_wrap = QWidget()
        tabs_wrap.setObjectName("workArea")
        tl = QVBoxLayout(tabs_wrap)
        tl.setContentsMargins(0, 2, 4, 4)
        tl.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        # Classic framed tabs (MobaXterm), not document-mode underline tabs
        self.tabs.setDocumentMode(False)
        # Content-sized tabs (MobaXterm), not stretched to fill the strip:
        # besides looking right, the leftover strip space is what you grab to
        # drag the whole tab strip to another edge (see _setup_docking).
        # NB: setDocumentMode() above re-enables expanding, so this must stay
        # *after* it.
        self.tabs.tabBar().setExpanding(False)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
        # Protocol badges render on a 16px tile
        self.tabs.setIconSize(QSize(16, 16))

        # Tab bar context menu
        self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self._tab_context_menu)
        # Double-click a tab to rename it (matches the context-menu action)
        self.tabs.tabBarDoubleClicked.connect(
            lambda idx: (self.tabs.setCurrentIndex(idx), self._rename_current_tab())
        )

        # Corner buttons — session count + quick actions
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(4, 3, 4, 0)
        cl.setSpacing(2)

        # Session count indicator
        self._tab_count_label = QLabel("0")
        self._tab_count_label.setObjectName("tabCount")
        self._tab_count_label.setFixedHeight(18)
        self._tab_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tab_count_label.setToolTip("Number of open sessions")
        cl.addWidget(self._tab_count_label)

        self._themed_corner_buttons: list[tuple[QPushButton, str]] = []

        def corner_button(icon_name: str, tip: str, cb) -> QPushButton:
            b = QPushButton()
            b.setIcon(icon(icon_name))
            self._themed_corner_buttons.append((b, icon_name))
            b.setObjectName("ghost")
            b.setProperty("iconOnly", True)  # square variant: no min-width
            b.setToolTip(tip)
            b.setFixedSize(26, 26)
            b.setIconSize(QSize(16, 16))
            b.clicked.connect(cb)
            return b

        cl.addWidget(corner_button("plus", "New session (Ctrl+N)", self.new_session))
        cl.addWidget(corner_button("console", "Local terminal (Ctrl+Shift+T)", self.open_local_terminal))
        cl.addWidget(corner_button("gear", "Settings (Ctrl+,)", self.open_settings))

        # Dock grip for the session tab strip — drag it to the top, left or
        # right edge (main_window wires the drag). The empty part of the tab
        # bar works too.
        self._tabs_grip = QPushButton()
        self._tabs_grip.setObjectName("dockGrip")
        self._tabs_grip.setIcon(icon("grip"))
        self._tabs_grip.setIconSize(QSize(14, 14))
        self._tabs_grip.setFixedSize(20, 20)
        self._tabs_grip.setCursor(Qt.CursorShape.OpenHandCursor)
        self._tabs_grip.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._tabs_grip.setToolTip(
            "Drag to move the session tab strip to the top, left or right edge"
        )
        cl.addWidget(self._tabs_grip)

        # The corner widget is the session counter + quick action buttons.
        # QTabWidget only paints a corner for a horizontal strip, so when the
        # strip docks to a side the same widget moves onto a one-row bar above
        # it (see _relayout_tab_corner) instead of disappearing.
        self._tab_corner = corner
        self._corner_row = QWidget()
        self._corner_row.setObjectName("tabCornerBar")
        self._corner_layout = QHBoxLayout(self._corner_row)
        self._corner_layout.setContentsMargins(4, 2, 4, 2)
        self._corner_layout.setSpacing(2)
        self._corner_row.setVisible(False)

        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)

        # Dashboard — compact welcome: quick connect, actions, recents
        self._empty = self._build_dashboard()

        self._tabs_container = QWidget()
        tcl = QVBoxLayout(self._tabs_container)
        tcl.setContentsMargins(0, 0, 0, 0)
        tcl.setSpacing(0)
        tcl.addWidget(self._corner_row, 0)
        tcl.addWidget(self.tabs, 1)

        self._center_stack = QWidget()
        csl = QVBoxLayout(self._center_stack)
        csl.setContentsMargins(0, 0, 0, 0)
        csl.setSpacing(0)
        csl.addWidget(self._empty, 1)
        csl.addWidget(self._tabs_container, 1)
        self._center_layout = csl
        self._empty.setVisible(True)
        self._tabs_container.setVisible(False)

        tl.addWidget(self._center_stack, 1)
        self.main_splitter.addWidget(tabs_wrap)

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([240, 1100])

        self.setCentralWidget(self.main_splitter)

        # Sidebar events
        self.sidebar.connectRequested.connect(self.connect_session)
        self.sidebar.editRequested.connect(self.edit_session)
        self.sidebar.duplicateRequested.connect(lambda sid: (self.ctx.store.duplicate(sid), self.sidebar.reload()))
        self.sidebar.deleteRequested.connect(self._delete_session)
        self.sidebar.sftpRequested.connect(self._connect_and_sftp)
        self.sidebar.newSessionRequested.connect(self.new_session)
        self.sidebar.newFolderRequested.connect(self.sidebar.prompt_new_folder)
        self.sidebar.localTerminalRequested.connect(self.open_local_terminal)

        # Track manual splitter drag so the sidebar width survives a
        # hide/show toggle and persists across restarts.
        self.main_splitter.splitterMoved.connect(self._on_splitter_moved)

        # Restore sidebar state (persistence) then sync the checkable actions.
        # "checked" on the toggle actions means the sidebar is *visible*.
        self._last_sidebar_width = 260
        saved_w = self.ctx.settings.geometry.get("sidebar_width")
        if isinstance(saved_w, int) and 150 <= saved_w <= 480:
            self._last_sidebar_width = saved_w
        self._sidebar_collapsed = bool(self.ctx.settings.geometry.get("sidebar_collapsed", False))
        self._sidebar_side = (
            "right"
            if str(self.ctx.settings.geometry.get("sidebar_side", "left")).lower().startswith("r")
            else "left"
        )
        self.main_splitter.setSizes(
            [0 if self._sidebar_collapsed else self._last_sidebar_width, 1200]
        )
        self._sync_sidebar_actions()

        # Mouse-driven docking (edges + grips) and the saved tab strip edge.
        self._setup_docking()

    def _sidebar_index(self) -> int:
        """Splitter slot the Sessions panel currently occupies (0 or 1).

        The panel can be docked to the right edge, in which case the *work
        area* is the leading widget — every width calculation has to ask
        rather than assume slot 0.
        """
        if not hasattr(self, "main_splitter") or not hasattr(self, "sidebar"):
            return 0
        return max(0, self.main_splitter.indexOf(self.sidebar))

    def _sidebar_width(self) -> int:
        if not hasattr(self, "main_splitter"):
            return 240
        sizes = self.main_splitter.sizes()
        index = self._sidebar_index()
        return sizes[index] if index < len(sizes) else 240

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Record the sidebar width after the user drags the splitter handle."""
        w = self._sidebar_width()
        self._sidebar_collapsed = w <= 0
        if w > 0:
            self._last_sidebar_width = w

    def _set_sidebar_width(self, width: int) -> None:
        # Never record the width here: this runs on every tween frame, so a
        # hide animation would clobber the user's width with the last partial
        # frame (~5 px). Only _on_splitter_moved records (real user drags —
        # programmatic setSizes never emits splitterMoved).
        sizes = self.main_splitter.sizes()
        total = sum(sizes)
        index = self._sidebar_index()
        self._sidebar_collapsed = width <= 0
        if index < len(sizes) and sizes[index] == width:
            return  # nothing to do — skip the layout pass entirely
        other = max(320, total - width)
        self.main_splitter.setSizes([width, other] if index == 0 else [other, width])

    # ------------------------------------------------------------------
    # Docking — every edge of the window is a valid home
    # ------------------------------------------------------------------
    def _setup_docking(self) -> None:
        """Wire the drag gestures, the splitter handle and the saved layout."""
        # Sessions panel: ⠿ grip drags it to either side edge, and the splitter
        # handle flips it on a double-click (dragging the handle still resizes).
        self._sidebar_drag = DockDragFilter(
            self.sidebar.dock_grip,
            self,
            ("left", "right"),
            {
                "left": "Sessions panel → left edge",
                "right": "Sessions panel → right edge",
            },
        )
        self._sidebar_drag.dockRequested.connect(self.move_sidebar)
        self.sidebar.sideFlipRequested.connect(self.flip_sidebar_side)

        # Session tab strip: drag it by any empty part of the tab bar — a
        # press on a tab itself still means "reorder this tab".
        self._tab_drag = DockDragFilter(
            self.tabs.tabBar(),
            self,
            ("top", "left", "right"),
            _TAB_STRIP_LABELS,
            can_start=lambda pos: pos is not None and self.tabs.tabBar().tabAt(pos) < 0,
        )
        self._tab_drag.dockRequested.connect(self.set_tabs_position)

        # ...and the corner-bar grip does the same, for when the strip is full
        # of tabs and has no empty space left to press on.
        self._tabs_grip_drag = DockDragFilter(
            self._tabs_grip, self, ("top", "left", "right"), _TAB_STRIP_LABELS
        )
        self._tabs_grip_drag.dockRequested.connect(self.set_tabs_position)

        # The leftover strip space past the last tab belongs to the QTabWidget
        # itself (the bar only spans its own size hint), so that surface needs
        # its own filter — restricted to the strip row, never the session pane.
        self._tabs_row_drag = DockDragFilter(
            self.tabs,
            self,
            ("top", "left", "right"),
            _TAB_STRIP_LABELS,
            can_start=self._in_tab_strip_band,
        )
        self._tabs_row_drag.dockRequested.connect(self.set_tabs_position)

        self._apply_sidebar_side()
        self.set_tabs_position(
            str(self.ctx.settings.geometry.get("tabs_position", "top")).lower()
        )
        self._bind_splitter_handle()

    def _bind_splitter_handle(self) -> None:
        """Double-clicking the divider moves the panel to the other side."""
        handle = self.main_splitter.handle(1)
        if handle is None:
            return
        self._splitter_handle = handle
        handle.installEventFilter(self)
        handle.setToolTip(
            "Drag to resize the Sessions panel\n"
            "Double-click to move it to the other side"
        )

    def sidebar_side(self) -> str:
        """``"left"`` or ``"right"`` — edge the Sessions panel is docked to."""
        return getattr(self, "_sidebar_side", "left")

    def _apply_sidebar_side(self) -> None:
        """Put the panel in the splitter slot its side asks for.

        ``QSplitter.insertWidget`` *moves* a widget that is already a child, so
        this only reorders — it never duplicates the panel or its state.
        """
        side = self.sidebar_side()
        index = 0 if side == "left" else 1
        self.main_splitter.insertWidget(index, self.sidebar)
        self.main_splitter.setStretchFactor(0, 0 if side == "left" else 1)
        self.main_splitter.setStretchFactor(1, 1 if side == "left" else 0)
        self.sidebar.set_side(side)
        width = 0 if getattr(self, "_sidebar_collapsed", False) else max(220, self._last_sidebar_width)
        self._set_sidebar_width(width)

    def move_sidebar(self, side: str) -> None:
        """Dock the Sessions panel to ``side`` — drag, menu or command palette."""
        side = "right" if str(side).strip().lower().startswith("r") else "left"
        if side == self.sidebar_side():
            return
        # Reordering resizes every open tab once; an embedded desktop (RDP)
        # must not read that as the user dragging the splitter.
        self._set_ui_layout_busy(True)
        try:
            self._sidebar_side = side
            self._apply_sidebar_side()
            self._bind_splitter_handle()
        finally:
            self._set_ui_layout_busy(False)
        self.ctx.settings.geometry["sidebar_side"] = side
        self._sync_sidebar_actions()
        toast(self, f"Sessions panel docked {side}")

    def flip_sidebar_side(self) -> None:
        """Move the Sessions panel to the opposite edge (Ctrl+Shift+B)."""
        self.move_sidebar("right" if self.sidebar_side() == "left" else "left")

    # -- session tab strip ---------------------------------------------
    def _in_tab_strip_band(self, pos) -> bool:
        """Is ``pos`` (tab-widget coords) in the tab strip's own row/column?

        Keeps the strip drag off the session pane: only the thin band the tabs
        actually live in starts a dock drag.
        """
        if pos is None:
            return False
        bar = self.tabs.tabBar()
        # isHidden(), not isVisible(): Qt hides the bar when no session is
        # open, and that is the only case with no strip to grab — a window
        # that simply has not been shown yet must still count as draggable.
        if bar.isHidden():
            return False
        rect = bar.geometry()
        key = self.tabs_position()
        if key == "left":
            return 0 <= pos.x() <= rect.right()
        if key == "right":
            return rect.left() <= pos.x() < self.tabs.width()
        return 0 <= pos.y() <= rect.bottom()

    def tabs_position(self) -> str:
        """``"top"``, ``"left"`` or ``"right"`` — where the session tabs live."""
        return getattr(self, "_tabs_dock", "top")

    def set_tabs_position(self, position: str) -> None:
        """Dock the session tab strip to the top, left or right edge."""
        key = str(position or "").strip().lower()
        if key not in _TAB_STRIP_POSITIONS:
            key = "top"
        self._set_ui_layout_busy(True)
        try:
            self._tabs_dock = key
            vertical = key in ("left", "right")
            self.tabs.setTabPosition(_TAB_STRIP_POSITIONS[key])
            # Right-elide in both orientations: a middle-elided *rotated*
            # label ("ro-apo…@prod") reads as noise, while "root@prod-web-01…"
            # stays recognisable.
            self.tabs.setElideMode(Qt.TextElideMode.ElideRight)
            for widget in (self.tabs, self.tabs.tabBar()):
                widget.setProperty("dock", key)
                style = widget.style()
                style.unpolish(widget)
                style.polish(widget)
            self._relayout_tab_corner(vertical)
        finally:
            self._set_ui_layout_busy(False)
        self.ctx.settings.geometry["tabs_position"] = key
        self._sync_tabs_position_actions()

    def _relayout_tab_corner(self, vertical: bool) -> None:
        """Keep the session counter and quick buttons with the tab strip."""
        if not hasattr(self, "_corner_row"):
            return
        if vertical:
            self.tabs.setCornerWidget(None, Qt.Corner.TopRightCorner)
            self._corner_layout.addWidget(self._tab_corner)
            self._tab_corner.show()
            self._corner_row.setVisible(True)
        else:
            self._corner_row.setVisible(False)
            self.tabs.setCornerWidget(self._tab_corner, Qt.Corner.TopRightCorner)
            self._tab_corner.show()

    def _sync_tabs_position_actions(self) -> None:
        current = self.tabs_position()
        for key, act in getattr(self, "_tabs_pos_actions", {}).items():
            act.blockSignals(True)
            act.setChecked(key == current)
            act.blockSignals(False)

    def cycle_tabs_position(self) -> None:
        """Walk top → left → right → top (View menu / keyboard)."""
        order = ("top", "left", "right")
        current = self.tabs_position()
        nxt = order[(order.index(current) + 1) % len(order)] if current in order else "top"
        self.set_tabs_position(nxt)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 — Qt naming
        """Double-clicking the splitter divider flips the Sessions panel."""
        if obj is getattr(self, "_splitter_handle", None) and event.type() == QEvent.Type.MouseButtonDblClick:
            self.flip_sidebar_side()
            return True
        return super().eventFilter(obj, event)

    def _toggle_sidebar(self, checked: bool = None) -> None:
        """checked=True shows the sidebar, checked=False collapses it.

        Called with the action's new state; if None (plain trigger), invert.
        """
        if not hasattr(self, "main_splitter"):
            return
        if checked is None:
            checked = self._sidebar_collapsed  # invert the current state
        self._sync_sidebar_actions(checked)
        # The tween resizes every open tab ~10 times in 140 ms. Sessions with
        # an embedded native surface (RDP) must not read that as the user
        # resizing the tab — that tore down a healthy remote desktop and left
        # it disconnected. Mark the chrome busy for the duration.
        self._set_ui_layout_busy(True)
        target = max(220, self._last_sidebar_width) if checked else 0
        self._animate_splitter(self._sidebar_width(), target)

    def _animate_splitter(self, start: int, end: int) -> None:
        from PySide6.QtCore import QVariantAnimation

        # One tween at a time: overlapping animations fight over the splitter
        # sizes and multiply the layout churn (rapid Ctrl+B presses).
        prev = getattr(self, "_sidebar_anim", None)
        if prev is not None:
            try:
                prev.stop()
                prev.deleteLater()
            except RuntimeError:  # C++ object already deleted
                pass
            self._sidebar_anim = None

        if not theme.MOTIONS_ENABLED or start == end:
            self._set_sidebar_width(end)
            self._set_ui_layout_busy(False)
            return
        anim = QVariantAnimation(self)
        anim.setDuration(140)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: self._set_sidebar_width(int(v)))
        self._sidebar_anim = anim  # keep alive across the event loop
        anim.finished.connect(lambda: self._set_ui_layout_busy(False))
        anim.finished.connect(anim.deleteLater)
        anim.start()

    def _set_ui_layout_busy(self, busy: bool) -> None:
        """Tell every open session that the window chrome is re-laying out.

        Protocol-agnostic: controllers that care (RDP's embedded desktop)
        implement the optional hook and keep their session untouched, the rest
        ignore it.
        """
        if not hasattr(self, "tabs"):
            return
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if not isinstance(tab, SessionTab):
                continue
            hook = getattr(tab.controller, "set_ui_layout_busy", None)
            if hook is None:
                continue
            try:
                hook(busy)
            except Exception:  # never let a session break the chrome
                log.exception("set_ui_layout_busy failed")

    def _sync_sidebar_actions(self, visible: bool = None) -> None:
        if visible is None:
            visible = not self._sidebar_collapsed
        flip = getattr(self, "_act_flip_sidebar", None)
        if flip is not None:
            other = "left" if self.sidebar_side() == "right" else "right"
            flip.setText(f"Move Sessions Panel to the &{other.capitalize()}")
        for act in (
            getattr(self, "_act_sidebar_toolbar", None),
            getattr(self, "_act_sidebar_menu", None),
        ):
            if act is not None:
                act.blockSignals(True)
                act.setChecked(visible)
                act.blockSignals(False)

    def _apply_ui_prefs(self) -> None:
        """Apply density / toolbar-labels / animation settings to the chrome."""
        s = self.ctx.settings
        theme.apply_theme(
            QApplication.instance(), s.theme, density=s.density, animations=s.animations
        )
        if hasattr(self, "_toolbar"):
            if s.toolbar_labels:
                # Default: large icon with the caption underneath
                self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                self._toolbar.setIconSize(QSize(22, 22))
            else:
                self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                self._toolbar.setIconSize(QSize(22, 22))
        # Dashboard title sizing (comfortable/compact) lives in the global
        # QSS (#dashTitle) — no inline overrides.

    def _refresh_theme(self) -> None:
        """Re-tint every palette-baked icon after a live theme switch.

        Called by ``theme.apply_theme`` via the change-callback registry.
        """
        for act, icon_name in getattr(self, "_themed_actions", []):
            act.setIcon(theme.toolbar_icon(icon_name))
        sidebar = getattr(self, "sidebar", None)
        if sidebar is not None:
            sidebar.refresh_theme()
        for btn, icon_name in getattr(self, "_themed_corner_buttons", []):
            btn.setIcon(icon(icon_name))
        tabs_grip = getattr(self, "_tabs_grip", None)
        if tabs_grip is not None:
            tabs_grip.setIcon(icon("grip"))
        for lbl, icon_name in getattr(self, "_dash_action_icons", []):
            lbl.setPixmap(theme.toolbar_icon(icon_name).pixmap(QSize(20, 20)))
        logo_tile = getattr(self, "_dash_logo_tile", None)
        if logo_tile is not None:
            p = palette()
            logo_tile.setStyleSheet(
                f"background: {theme.solid_on(p['accent_subtle'], p['bg'])}; "
                f"border: 1px solid {p['border_subtle']}; "
                f"border-radius: 10px;"
            )
        for lbl, mode, arg in getattr(self, "_dash_recent_rows", []):
            if mode == "proto":
                lbl.setPixmap(protocol_badge(str(arg), self._proto_icon(str(arg))).pixmap(QSize(20, 20)))
            else:
                name, tint_key = arg
                lbl.setPixmap(icon(name, palette()[tint_key]).pixmap(QSize(14, 14)))
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, SessionTab):
                w._refresh_theme()

    def _bind_shortcuts(self) -> None:
        # Tab navigation shortcuts (Ctrl+Tab / Ctrl+Shift+Backtab live on the
        # Tabs-menu actions — duplicating them here would fire twice).
        QShortcut(QKeySequence("Ctrl+K"), self, self.open_command_palette)
        QShortcut(QKeySequence("Ctrl+Shift+K"), self, self._focus_quick_connect)
        # Ctrl+W and Ctrl+Shift+W are terminal editing keys (backward-word
        # delete).  They deliberately have no tab-closing binding.

        for i in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, lambda idx=i-1: self.switch_to_tab(idx))

    def _focus_quick_connect(self) -> None:
        """Ctrl+Shift+K — jump to the toolbar quick-connect input."""
        self.quick.setFocus()
        self.quick.selectAll()

    def _update_empty_state(self) -> None:
        has_tabs = self.tabs.count() > 0
        self._empty.setVisible(not has_tabs)
        self._tabs_container.setVisible(has_tabs)
        # Update the tab count badge in the corner widget
        if hasattr(self, "_tab_count_label"):
            count = self.tabs.count()
            self._tab_count_label.setText(str(count))
            self._tab_count_label.setVisible(count > 0)
        # Show/hide the "Close All" toolbar button
        if hasattr(self, "_close_all_btn"):
            self._close_all_btn.setVisible(has_tabs)
        if not has_tabs:
            # The welcome page goes back on screen — refresh its recents so
            # recently saved/removed sessions are current.
            self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        """Rebuild the welcome dashboard (recents, tiles) — only visible
        when no tabs are open, so this is cheap and side-effect free."""
        if self.tabs.count() > 0:
            return
        lay = self._center_layout
        lay.removeWidget(self._empty)
        self._empty.deleteLater()
        self._empty = self._build_dashboard()
        lay.insertWidget(0, self._empty)
        self._empty.setVisible(True)

    # ------------------------------------------------------------------
    # Tab actions & Context menu
    # ------------------------------------------------------------------
    def switch_to_tab(self, index: int) -> None:
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def next_tab(self) -> None:
        count = self.tabs.count()
        if count > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + 1) % count)

    def prev_tab(self) -> None:
        count = self.tabs.count()
        if count > 1:
            self.tabs.setCurrentIndex((self.tabs.currentIndex() - 1 + count) % count)

    def close_current_tab(self) -> None:
        idx = self.tabs.currentIndex()
        if idx >= 0:
            self.close_tab(idx)

    def duplicate_current_tab(self) -> None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, SessionTab):
            self.open_session(widget.controller.definition)

    # -- Tabs-menu helpers (operate on the current tab) -------------------
    def _current_tab(self) -> SessionTab | None:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, SessionTab) else None

    def _close_others_current(self) -> None:
        idx = self.tabs.currentIndex()
        if idx >= 0:
            self._close_other_tabs(idx)

    def _close_right_current(self) -> None:
        idx = self.tabs.currentIndex()
        if idx >= 0:
            self._close_tabs_right(idx)

    def _close_all_tabs(self) -> None:
        """Close all open tabs."""
        if self.tabs.count() == 0:
            return
        box = QMessageBox(self)
        box.setWindowTitle(APP_NAME)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Close all {self.tabs.count()} tabs?")
        box.setInformativeText("Active sessions will be stopped.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText("Close All")
        box.button(QMessageBox.StandardButton.No).setText("Cancel")
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        # Close tabs from last to first to avoid index shifting
        for i in range(self.tabs.count() - 1, -1, -1):
            self.close_tab(i)

    def _rename_current_tab(self) -> None:
        idx = self.tabs.currentIndex()
        if idx >= 0:
            self._rename_tab(idx, self.tabs.widget(idx))

    def _safe_to_close(self, tab: SessionTab) -> bool:
        """Ask before losing a session that is actively writing a log."""
        term = getattr(tab.controller, "term", None)
        if term is not None and hasattr(term, "is_logging") and term.is_logging():
            box = QMessageBox(self)
            box.setWindowTitle(APP_NAME)
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(f"Close “{self.tabs.tabText(self.tabs.indexOf(tab))}”?")
            box.setInformativeText("Terminal logging is running — the capture will stop.")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            box.button(QMessageBox.StandardButton.Yes).setText("Stop & Close")
            box.button(QMessageBox.StandardButton.No).setText("Keep Session")
            box.setDefaultButton(QMessageBox.StandardButton.No)
            return box.exec() == QMessageBox.StandardButton.Yes
        return True

    def _reconnect_current(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.controller.request_reconnect()

    def _sftp_current(self) -> None:
        tab = self._current_tab()
        if tab is not None and tab.controller.capabilities().sftp:
            tab.controller.open_sftp()
        else:
            toast(self, "Open an SSH session first — SFTP rides on SSH.", "warn")

    def _on_command_sent(self, source_tab: SessionTab, text: str) -> None:
        """CommandBar Enter: run the command in the tab's terminal."""
        data = (text + "\r").encode("utf-8")
        try:
            source_tab.controller.write(data)
        except Exception:  # noqa: BLE001 - never break the command line
            log.exception("command send failed")

    def _tab_context_menu(self, pos: QPoint) -> None:
        tab_bar = self.tabs.tabBar()
        index = tab_bar.tabAt(pos)
        if index < 0:
            return
        widget = self.tabs.widget(index)
        if not isinstance(widget, SessionTab):
            return

        menu = QMenu(self)
        menu.addAction("Close Tab", lambda: self.close_tab(index))
        menu.addAction("Close Other Tabs", lambda: self._close_other_tabs(index))
        menu.addAction("Close Tabs to the Right", lambda: self._close_tabs_right(index))
        menu.addAction("Close All Tabs", self._close_all_tabs)
        menu.addSeparator()
        menu.addAction("Duplicate Tab\tCtrl+Shift+D", lambda: self.open_session(widget.controller.definition))
        menu.addAction("Rename Tab…", lambda: self._rename_tab(index, widget))
        menu.addAction("Reconnect Session", lambda: widget.controller.request_reconnect())
        menu.addSeparator()

        # Logging action
        is_logging = False
        term = getattr(widget.controller, "term", None)
        if term and hasattr(term, "is_logging"):
            is_logging = term.is_logging()
        act_log = menu.addAction("Stop Session Logging" if is_logging else "Start Session Logging…")
        act_log.triggered.connect(lambda: self._toggle_tab_logging(widget))

        caps = widget.controller.capabilities()
        if caps.sftp:
            menu.addSeparator()
            menu.addAction("Browse Files (SFTP)", widget.controller.open_sftp)
        if caps.file_sharing:
            menu.addAction(
                "Share Local Folders\u2026",
                lambda: self.open_share_for_session(widget.controller.definition),
            )

        menu.exec(tab_bar.mapToGlobal(pos))

    def _close_other_tabs(self, keep_index: int) -> None:
        for i in range(self.tabs.count() - 1, -1, -1):
            if i != keep_index:
                self.close_tab(i)

    def _close_tabs_right(self, index: int) -> None:
        for i in range(self.tabs.count() - 1, index, -1):
            self.close_tab(i)

    def _rename_tab(self, index: int, tab: SessionTab) -> None:
        current = self.tabs.tabText(index)
        name, ok = QInputDialog.getText(self, "Rename Tab", "Tab title:", text=current)
        if ok and name:
            tab._custom_title = name
            self.tabs.setTabText(index, name)

    def _toggle_tab_logging(self, tab: SessionTab) -> None:
        term = getattr(tab.controller, "term", None)
        if not term or not hasattr(term, "start_logging"):
            return
        if term.is_logging():
            term.stop_logging()
            tab.rec_chip.setVisible(False)
            toast(self, "Session logging stopped", "info")
        else:
            default_name = f"session-{tab.controller.definition.display_name()}-{time.strftime('%Y%m%d-%H%M%S')}.log"
            dest, _ = QFileDialog.getSaveFileName(self, "Log Session Output", str(paths.logs_dir() / default_name), "Log Files (*.log *.txt)")
            if dest:
                term.start_logging(dest)
                tab.rec_chip.setVisible(True)
                toast(self, f"Logging session to {Path(dest).name}", "good")

    def toggle_session_logging(self) -> None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, SessionTab):
            self._toggle_tab_logging(widget)
        else:
            toast(self, "Open a terminal session first to start logging", "warn")

    # ------------------------------------------------------------------
    # Command Palette
    # ------------------------------------------------------------------
    def open_command_palette(self) -> None:
        dlg = CommandPaletteDialog(self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Standalone Tools Openers
    # ------------------------------------------------------------------
    def open_network_tools(self) -> None:
        from .network_tools_dialog import NetworkToolsDialog

        NetworkToolsDialog(self).show()

    def open_cluster_runner(self) -> None:
        from .cluster_dialog import ClusterDialog

        ClusterDialog(self.ctx, self).show()

    def open_key_utility(self) -> None:
        from .key_utility_dialog import KeyUtilityDialog

        KeyUtilityDialog(self.ctx, self).show()

    # ------------------------------------------------------------------
    # Built-in SFTP share server
    # ------------------------------------------------------------------
    def share_service(self):
        """The app-wide share service (built lazily when the context lacks one)."""
        service = getattr(self.ctx, "share_service", None)
        if service is None:
            from ..tools.share_server import ShareService

            service = ShareService(self.ctx.settings)
            self.ctx.share_service = service
        return service

    def open_share_server(self):
        from .share_server_dialog import open_share_dialog

        return open_share_dialog(self, self.share_service())

    def open_share_for_session(self, definition: Session):
        """Share manager scoped to one machine: global folders + its own."""
        from .share_server_dialog import open_share_dialog

        return open_share_dialog(self, self.share_service(), definition)

    def save_settings(self) -> None:
        """Persist settings now (used by tool dialogs that edit them live)."""
        self.ctx.settings.save(paths.settings_file())

    def _autostart_share_server(self) -> None:
        """Bring the share listener up if the user enabled autostart."""
        service = self.share_service()
        settings = self.ctx.settings
        if not (settings.share_server_enabled or settings.share_server_autostart):
            return
        if service.server.running:
            return
        try:
            service.start()
            toast(self, f"File share listening on {service.server.display_address()}", "info")
        except Exception as exc:  # a failed listener must never block startup
            log.warning("share server autostart failed: %s", exc)
            toast(self, f"Share server could not start: {exc}", "warn")

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def connect_session(self, session_id: str) -> None:
        defn = self.ctx.store.get(session_id)
        if defn is None:
            return
        self.open_session(defn)

    def open_session(self, defn: Session) -> SessionTab | None:
        defn = copy.deepcopy(defn)
        try:
            plugin = registry().require(defn.protocol)
        except KeyError as exc:
            QMessageBox.warning(self, "Unknown protocol", str(exc))
            return None

        # ------------------------------------------------------------------
        # Credential guard — prompt for username / password whenever the
        # session has no saved credentials and is not a local shell.
        # This stops a bare IP (quick-connect or saved session with no auth)
        # from connecting silently without credentials.
        # ------------------------------------------------------------------
        from .credential_dialog import CredentialDialog, needs_credential_prompt
        if needs_credential_prompt(defn):
            dlg = CredentialDialog(defn, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                # User cancelled — abort the connection entirely
                return None
            # defn.username / defn.password are now filled in by the dialog

        controller = plugin.create_session(defn, self.ctx)
        controller.setParent(self)
        tab = SessionTab(controller, self)
        self.tabs.addTab(tab, defn.display_name())
        self.tabs.setCurrentWidget(tab)
        # Protocol mini-badge — colour-coded (SSH/RDP/local) tab identity
        self.tabs.setTabIcon(self.tabs.indexOf(tab), protocol_badge(defn.protocol, plugin.icon_name))

        def _set_title(t, _tab=tab):
            if _tab._custom_title:
                return
            idx = self.tabs.indexOf(_tab)
            if idx >= 0:
                self.tabs.setTabText(idx, t)

        controller.titleChanged.connect(_set_title)
        # Status-bar summary follows the session.
        controller.statusInfo.connect(
            lambda info, c=controller: self._on_controller_status(info, c)
        )
        controller.start()
        self._update_empty_state()
        return tab

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, SessionTab) and not self._safe_to_close(widget):
            return
        self.tabs.removeTab(index)
        if isinstance(widget, SessionTab):
            try:
                # Stop logging if active
                term = getattr(widget.controller, "term", None)
                if term and hasattr(term, "stop_logging"):
                    term.stop_logging()
                widget.controller.stop("closed by user")
            except Exception:
                log.exception("error stopping session controller")
            self._last_connected_info.pop(id(widget.controller), None)
            widget.controller.deleteLater()
        if widget is not None:
            widget.deleteLater()
        self._update_empty_state()
        self._update_session_status(self.current_controller())

    def current_controller(self) -> SessionController | None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, SessionTab):
            return widget.controller
        return None

    def _tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, SessionTab):
            caps = widget.controller.capabilities()
            if caps.shell:
                QTimer.singleShot(0, lambda: widget.controller.widget().setFocus())
        self._update_session_status(self.current_controller())

    # ------------------------------------------------------------------
    # Status-bar session summary
    # ------------------------------------------------------------------
    def _update_session_status(self, controller: SessionController | None) -> None:
        if controller is None:
            self.session_info_label.setText("")
            return
        defn = controller.definition
        caps = controller.capabilities()
        proto = defn.protocol.upper()
        host = defn.host or ""
        user = defn.username or ""
        port = defn.endpoint()[1]
        if host:
            ident = f"{user}@{host}:{port}" if user else f"{host}:{port}"
        elif user:
            ident = user
        else:
            ident = "local"
        parts = [f"{proto}: {ident}"]
        info = getattr(self, "_last_connected_info", {}).get(id(controller), {})
        if info.get("cipher"):
            parts.append(info["cipher"])
        ver = (info.get("remote_version") or "").split("\n")[0]
        if ver:
            parts.append(ver[:28])
        feats = []
        if caps.sftp:
            feats.append("SFTP")
        if feats:
            parts.append(" · " + "  ".join(feats))
        self.session_info_label.setText("   ".join(parts))

    def _on_controller_status(self, info: dict, controller: SessionController) -> None:
        if "connected" in info:
            self._last_connected_info[id(controller)] = info["connected"]
        if self.current_controller() is controller:
            self._update_session_status(controller)

    # -- dialogs -------------------------------------------------------------
    def new_session(self, *args) -> None:
        from .session_dialog import SessionDialog

        group = self.sidebar.selected_group()
        dlg = SessionDialog(self.ctx, Session(group=group), self)
        if dlg.exec():
            self.sidebar.reload()
            self._refresh_dashboard()
            if dlg.session.id:
                self.connect_session(dlg.session.id)

    def open_local_terminal(self, *args) -> SessionTab | None:
        from ..core.models import PROTOCOL_LOCAL

        defn = Session(protocol=PROTOCOL_LOCAL, name="Terminal")
        return self.open_session(defn)

    def edit_session(self, session_id: str) -> None:
        from .session_dialog import SessionDialog

        defn = self.ctx.store.get(session_id)
        if defn is None:
            return
        dlg = SessionDialog(self.ctx, defn, self)
        if dlg.exec():
            self.sidebar.reload()
            self._refresh_dashboard()

    def _delete_session(self, session_id: str) -> None:
        defn = self.ctx.store.get(session_id)
        if defn is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Delete session")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(f"Delete “{defn.display_name()}”?")
        box.setInformativeText("The saved session and its settings will be removed. Open tabs are not affected.")
        yes = box.addButton("Delete", QMessageBox.ButtonRole.YesRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes)
        box.exec()
        if box.clickedButton() is yes:
            self.ctx.store.delete(session_id)
            self.sidebar.reload()
            self._refresh_dashboard()

    def quick_connect(self) -> None:
        self._quick_connect_from(self.quick)

    def _quick_connect_from(self, source: QLineEdit) -> None:
        text = source.text().strip()
        if not text:
            return
        for plugin in registry().editable():
            defn = plugin.quick_connect_target(text)
            if defn is not None:
                self.ctx.store.upsert(defn)
                self.sidebar.reload()
                self.open_session(defn)
                source.clear()
                return
        toast(self, "Could not parse that. Use user@host[:port] (port 3389 ⇒ RDP).", "warn")
        source.selectAll()
        source.setFocus()

    def _connect_and_sftp(self, session_id: str) -> None:
        tab = self.connect_session(session_id)
        if tab is not None and tab.controller.capabilities().sftp:
            tab.controller.transportUp.connect(lambda: self.open_sftp_for_controller(tab.controller))

    # -- tools ---------------------------------------------------------------
    def open_vault(self) -> None:
        from .vault_dialog import VaultDialog

        VaultDialog(self.ctx, self).exec()

    def open_tunnels_dialog(self) -> None:
        controller = self.current_controller()
        if controller is None or not controller.capabilities().tunnels:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if isinstance(w, SessionTab) and w.controller.capabilities().tunnels:
                    controller = w.controller
                    break
        if controller is None or not controller.capabilities().tunnels:
            toast(self, "Open an SSH session first — tunnels ride on SSH.", "warn")
            return
        self.open_tunnels_for_controller(controller)

    def _reuse_tool_dialog(self, controller):
        """Bring an already-open non-modal tool dialog back to front; else None."""
        cid = id(controller)
        dlg = self._tool_dialogs.get(cid)
        if dlg is None:
            return None
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        return dlg

    def open_tunnels_for_controller(self, controller) -> None:
        from .tunnels_dialog import TunnelsDialog

        if self._reuse_tool_dialog(controller):
            return
        dlg = TunnelsDialog(self.ctx, controller, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(lambda _r, c=controller: self._tool_dialogs.pop(id(c), None))
        self._tool_dialogs[id(controller)] = dlg
        dlg.show()

    def open_sftp_for_controller(self, controller) -> None:
        from .sftp_dialog import SftpDialog

        if self._reuse_tool_dialog(controller):
            return
        dlg = SftpDialog(self.ctx, controller, self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.finished.connect(lambda _r, c=controller: self._tool_dialogs.pop(id(c), None))
        self._tool_dialogs[id(controller)] = dlg
        dlg.show()

    def open_rdp_server_manager(self) -> None:
        from .rdp_server_dialog import RdpServerDialog

        RdpServerDialog(self).exec()

    def open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        dlg = SettingsDialog(self.ctx.settings, self)
        animate_in(dlg)
        if dlg.exec():
            self._apply_ui_prefs()
            self._sync_theme_actions()
            self._apply_terminal_prefs()

    def _apply_terminal_prefs(self) -> None:
        """Push font size/family to open terminals. SSH colors stay native."""
        s = self.ctx.settings
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if not isinstance(w, SessionTab):
                continue
            term = getattr(w.controller, "term", None)
            if term is not None and hasattr(term, "apply_font"):
                try:
                    term.apply_font(s.font_family, s.font_size)
                    if hasattr(term, "apply_theme"):
                        term.apply_theme()
                except Exception:  # noqa: BLE001
                    log.exception("apply terminal preferences failed")

    def apply_theme_id(self, theme_id: str) -> None:
        from ..core.settings import THEME_IDS

        if theme_id not in THEME_IDS:
            return
        self.ctx.settings.theme = theme_id
        self.ctx.settings.save(paths.settings_file())
        theme.apply_theme(
            QApplication.instance(),
            theme_id,
            density=self.ctx.settings.density,
            animations=self.ctx.settings.animations,
        )
        self._sync_theme_actions()
        self._apply_terminal_prefs()

    def cycle_theme(self) -> None:
        from ..core.settings import THEME_CHOICES

        ids = [tid for tid, _ in THEME_CHOICES]
        cur = self.ctx.settings.theme
        nxt = ids[(ids.index(cur) + 1) % len(ids)] if cur in ids else ids[0]
        self.apply_theme_id(nxt)

    def _toggle_theme(self, dark: bool) -> None:
        """Legacy dark/light flip used by older callers."""
        self.apply_theme_id("midnight" if dark else "mobaxterm")

    def _sync_theme_actions(self) -> None:
        current = self.ctx.settings.theme
        for tid, act in getattr(self, "_theme_actions", {}).items():
            act.setChecked(tid == current)

    def open_shortcuts(self) -> None:
        from .shortcuts_dialog import ShortcutsDialog

        dlg = ShortcutsDialog(self)
        animate_in(dlg)
        dlg.exec()

    def _setup_tray(self) -> None:
        """Optional system-tray icon (only where a tray actually exists)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self)
        tray.setIcon(icon("logo"))
        tray.setToolTip(APP_NAME)
        menu = QMenu()
        a = menu.addAction("Show / hide window")
        a.triggered.connect(self._toggle_visible)
        a = menu.addAction("Quit")
        a.triggered.connect(self.close)
        tray.setContextMenu(menu)
        tray.activated.connect(
            lambda reason: self._tray_activated(reason)
        )
        tray.show()
        self._tray = tray

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_visible()

    def _toggle_visible(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "Flight operations workbench.<br>"
            "SSH / SFTP / OpenSSH to Linux, Windows, BSD and macOS hosts; RDP to Windows hosts.<br><br>"
            "Python · Qt (PySide6) · paramiko · pyte<br><br>"
            "<span style='color: #8a94ac; letter-spacing: 1px;'>SSH · SFTP · RDP</span>",
        )

    def _import_ssh_config(self) -> None:
        from ..importers.ssh_config import import_ssh_config

        added = import_ssh_config(self.ctx.store)
        self.sidebar.reload()
        self._refresh_dashboard()
        toast(self, f"Imported {added} session(s) from ~/.ssh/config", "good")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import sessions", "", "JSON (*.json)")
        if not path:
            return
        import json

        try:
            size = Path(path).stat().st_size
            if size > _MAX_IMPORT_BYTES:
                raise ValueError(
                    f"file is too large to be a session export ({size // 1_048_576} MB)"
                )
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, dict):
                raise ValueError("expected a JSON object")
            raw_sessions = payload.get("sessions", [])
            if not isinstance(raw_sessions, list):
                raise ValueError("'sessions' must be a list")
            sessions = [Session.from_dict(d) for d in raw_sessions if isinstance(d, dict)]
            added = self.ctx.store.import_sessions(sessions)
            for g in payload.get("groups", []):
                if isinstance(g, str) and g:
                    self.ctx.store.ensure_group(g)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        self.sidebar.reload()
        self._refresh_dashboard()
        toast(self, f"Imported {added} session(s)", "good")

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export sessions", "rdpstudio-sessions.json", "JSON (*.json)")
        if not path:
            return
        import json

        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.ctx.store.export_dict(), fh, indent=2)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        toast(self, "Exported (secrets are NOT included)", "good")

    def _open_path(self, path) -> None:
        import subprocess

        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _autolock(self) -> None:
        # Vault auto-lock was removed from Settings; keep the timer as a
        # no-op so existing callers/tests that start it stay safe.
        return

    def closeEvent(self, event) -> None:  # noqa: N802
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, SessionTab):
                try:
                    # Blocking teardown: the event loop won't run again after
                    # closeEvent, so deferred shutdowns would leave worker
                    # threads alive at exit.
                    w.controller.stop_blocking("app closed")
                except Exception:
                    log.exception("error stopping session on shutdown")
        settings = self.ctx.settings
        settings.geometry = {
            "size": [self.width(), self.height()],
            "pos": [self.x(), self.y()],
            "maximized": self.isMaximized(),
            "sidebar_collapsed": self._sidebar_collapsed,
            "sidebar_width": self._last_sidebar_width,
            "sidebar_side": self.sidebar_side(),
            "tabs_position": self.tabs_position(),
        }
        settings.save(paths.settings_file())
        service = getattr(self.ctx, "share_service", None)
        if service is not None:
            try:
                service.server.stop()
            except Exception:
                log.exception("error stopping the share server on shutdown")
        super().closeEvent(event)
