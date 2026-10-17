"""Main window: tabbed sessions, sidebar, toolbar, quick connect, tools & command palette."""

from __future__ import annotations

import copy
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QDropEvent, QGuiApplication, QKeySequence, QShortcut
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
    QProgressBar,
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
from ..core.activity import default_activity_log, log_activity
from ..core.log import get_logger
from ..core.models import PROTOCOL_RDP, Session
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
from .onboarding import set_interactive_tooltip
from .sidebar import SessionTree
from .support_chat import SupportChatPanel
from .theme import icon, palette, protocol_badge
from .widgets import (
    STATE_COLORS,
    ShimmerProgressBar,
    StateChip,
    StatusIndicator,
    animate_in,
    pulse,
    toast,
)

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
    """One tab: hosts a SessionController with a modern, distinct header.

    Design goals (beyond theme colours):
    - Header and all controls live in a distinct surface (panel) that never
      uses terminal colours, so the terminal area is visually isolated.
    - Each tab has a clearly visible, labelled Close button that fully clears
      session state on click.
    - Professional spacing, rounded controls, and clear visual hierarchy.
    """

    def __init__(self, controller: SessionController, main: MainWindow) -> None:
        super().__init__()
        self.controller = controller
        self.main = main
        self._custom_title: str | None = None
        self._toolbar_visible = True
        self._is_closing = False
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Modern session header — distinct surface from terminal ──
        header = QWidget()
        header.setObjectName("sessionHeader")
        header.setMinimumHeight(46)
        header.setMaximumHeight(46)
        h = QHBoxLayout(header)
        h.setContentsMargins(14, 6, 12, 6)
        h.setSpacing(10)

        # Left: status + session identity
        left_wrap = QWidget()
        left_wrap.setObjectName("sessionHeaderLeft")
        left_l = QHBoxLayout(left_wrap)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(8)

        defn_obj = getattr(controller, "definition", None) or getattr(controller, "defn", None)
        proto_str = (getattr(defn_obj, "protocol", "") or "ssh").upper()
        self.proto_chip = QLabel(proto_str)
        self.proto_chip.setObjectName("protoChip")
        left_l.addWidget(self.proto_chip)

        self.status_dot = StatusIndicator("connecting")
        self.status_dot.setObjectName("sessionStatusIndicator")
        left_l.addWidget(self.status_dot)

        self.chip = StateChip("connecting", "info")
        left_l.addWidget(self.chip)

        self.rec_chip = StateChip("● REC", "bad")
        self.rec_chip.setVisible(False)
        self.rec_chip.setToolTip("Logging active session output to file")
        left_l.addWidget(self.rec_chip)

        sep_left = QFrame()
        sep_left.setObjectName("sessionSep")
        sep_left.setFrameShape(QFrame.Shape.VLine)
        sep_left.setFixedWidth(1)
        sep_left.setFixedHeight(16)
        left_l.addWidget(sep_left)

        self.info = QLabel("")
        self.info.setObjectName("sessionInfo")
        self.info.setStyleSheet("font-size: 12px; font-weight: 500;")
        left_l.addWidget(self.info, 1)

        grp_str = getattr(defn_obj, "group", "") or ""
        if grp_str:
            grp_lbl = QLabel(grp_str)
            grp_lbl.setObjectName("protoChip")
            left_l.addWidget(grp_lbl)

        h.addWidget(left_wrap, 1)

        # Right: actions + clearly visible Close
        actions_wrap = QWidget()
        actions_wrap.setObjectName("sessionActions")
        ah = QHBoxLayout(actions_wrap)
        ah.setContentsMargins(0, 0, 0, 0)
        ah.setSpacing(8)

        self._themed_buttons: list[tuple[QPushButton, str, str | None]] = []

        def make_action_btn(text, icon_name, tip, cb, primary=False):
            b = QPushButton(text)
            if icon_name:
                b.setIcon(icon(icon_name, palette()["fg_dim"] if not primary else palette()["accent_text"]))
                self._themed_buttons.append((b, icon_name, None))
            b.setObjectName("sessionActionPrimary" if primary else "sessionAction")
            b.setToolTip(tip)
            b.clicked.connect(cb)
            b.setFixedHeight(30)
            b.setMinimumWidth(78)
            b.setIconSize(QSize(16, 16))
            return b

        # State-aware Stop / Reconnect — primary action
        self.btn_reconnect = QPushButton("Stop")
        self.btn_reconnect.setIcon(icon("stop", palette()["accent_text"]))
        self.btn_reconnect.setObjectName("sessionActionPrimary")
        self.btn_reconnect.clicked.connect(self._on_action_btn)
        self.btn_reconnect.setVisible(False)
        self.btn_reconnect.setFixedHeight(30)
        self.btn_reconnect.setMinimumWidth(92)
        self.btn_reconnect.setIconSize(QSize(14, 14))
        ah.addWidget(self.btn_reconnect)

        caps = controller.capabilities()

        if caps.sftp:
            b = make_action_btn("Files", "folder", "Browse remote files (SFTP)", controller.open_sftp)
            ah.addWidget(b)

        self.btn_support = make_action_btn(
            "Support",
            "help",
            "Toggle in-session support & instant troubleshooting chat",
            self.toggle_support_panel,
        )
        ah.addWidget(self.btn_support)

        # Separator between actions and Close — visual grouping
        sep = QFrame()
        sep.setObjectName("sessionSep")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        sep.setFixedHeight(22)
        ah.addWidget(sep)

        # Clearly visible Close — labelled, not just an icon (modern professional)
        close_btn = QPushButton("Close")
        close_btn.setIcon(icon("close"))
        self._themed_buttons.append((close_btn, "close", None))
        close_btn.setObjectName("sessionClose")
        close_btn.setToolTip("Close this session and clear all related data")
        close_btn.setAccessibleName("Close session")
        close_btn.setAccessibleDescription("Close this session tab and clear all related data")
        close_btn.setStatusTip("Close this session and clear all related data")
        close_btn.setFixedHeight(30)
        close_btn.setMinimumWidth(84)
        close_btn.setIconSize(QSize(14, 14))
        close_btn.clicked.connect(self._request_close)
        ah.addWidget(close_btn)
        self._close_btn = close_btn

        h.addWidget(actions_wrap)

        layout.addWidget(header)

        # Divider — crisp separation between controls and terminal
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("sessionDivider")
        line.setFixedHeight(1)
        layout.addWidget(line)

        # Terminal container — distinct, isolated surface
        self._term_container = QWidget()
        self._term_container.setObjectName("terminalContainer")
        tc_l = QVBoxLayout(self._term_container)
        tc_l.setContentsMargins(0, 0, 0, 0)
        tc_l.setSpacing(0)
        self._content = controller.widget()
        self._content.setObjectName("terminalContent")
        tc_l.addWidget(self._content, 1)
        layout.addWidget(self._term_container, 1)

        # Command bar — distinct surface below terminal (must remain at layout index 3)
        self.command_bar = None
        if caps.shell:
            self.command_bar = CommandBar()
            self.command_bar.setObjectName("sessionCommandBar")
            self.command_bar.commandSent.connect(self._on_command_sent)
            layout.addWidget(self.command_bar)

        # Visual Drag-and-Drop File Transfer Progress Bar (index 4+)
        self.transfer_bar = QFrame()
        self.transfer_bar.setObjectName("sessionTransferBar")
        tb_lay = QVBoxLayout(self.transfer_bar)
        tb_lay.setContentsMargins(12, 6, 12, 6)
        tb_lay.setSpacing(4)
        tb_top = QHBoxLayout()
        tb_top.setSpacing(8)
        self.transfer_label = QLabel("Ready for drag-and-drop file transfer")
        self.transfer_label.setObjectName("caption")
        tb_top.addWidget(self.transfer_label, 1)
        self.transfer_progress = QProgressBar()
        self.transfer_progress.setObjectName("sessionTransferProgress")
        self.transfer_progress.setRange(0, 100)
        self.transfer_progress.setValue(0)
        self.transfer_progress.setFixedWidth(180)
        self.transfer_progress.setFixedHeight(16)
        tb_top.addWidget(self.transfer_progress)
        tb_lay.addLayout(tb_top)
        self.transfer_shimmer = ShimmerProgressBar()
        self.transfer_shimmer.setFixedHeight(4)
        tb_lay.addWidget(self.transfer_shimmer)
        self.transfer_bar.setVisible(False)
        layout.addWidget(self.transfer_bar)

        # In-Session Support & Troubleshooting Chat Panel (index 5+)
        defn_name = defn_obj.display_name() if defn_obj and hasattr(defn_obj, "display_name") else "Session"
        defn_host = getattr(defn_obj, "host", "") or ""
        defn_port = int(getattr(defn_obj, "port", 0) or 0)
        self.support_panel = SupportChatPanel(
            session_name=defn_name,
            protocol=proto_str.lower(),
            host=defn_host,
            port=defn_port,
            state="connecting",
            compact=True,
            parent=self,
        )
        self.support_panel.setVisible(False)
        self.support_panel.closeRequested.connect(lambda: self.support_panel.setVisible(False))
        self.support_panel.reconnectRequested.connect(self.controller.request_reconnect)
        self.support_panel.feedbackRequested.connect(
            lambda prefill: self.main.open_feedback_dialog(
                prefill_description=prefill, category="bug"
            )
        )
        layout.addWidget(self.support_panel)

        widget_changed = getattr(controller, "widgetChanged", None)
        if widget_changed is not None:
            widget_changed.connect(self._swap_content)

        controller.stateChanged.connect(self._on_state)
        controller.statusInfo.connect(self._on_status)
        controller.finished.connect(self._on_finished)
        controller.reconnectScheduled.connect(self._on_reconnect_scheduled)

    def toggle_support_panel(self) -> bool:
        """Show or hide the embedded in-session support chat panel."""
        vis = self.support_panel.isHidden()
        self.support_panel.setVisible(vis)
        if vis:
            self.support_panel.input.setFocus()
        return vis

    def show_transfer_progress(self, label: str, percent: int) -> None:
        """Display the visual file-transfer progress bar on this session tab."""
        pct = max(0, min(100, int(percent)))
        self.transfer_bar.setVisible(True)
        self.transfer_label.setText(label)
        self.transfer_progress.setValue(pct)
        self.transfer_shimmer.set_percent(pct)
        if 0 < pct < 100:
            self.transfer_shimmer.start_shimmer()
        else:
            self.transfer_shimmer.stop_shimmer()

    def handle_dropped_files(self, local_paths: list[str]) -> int:
        """Handle local file paths dropped onto the session tab."""
        valid = [str(p) for p in local_paths if p]
        if not valid:
            return 0
        defn = getattr(self.controller, "definition", None)
        sess_name = defn.display_name() if defn and hasattr(defn, "display_name") else "Session"
        proto = (getattr(defn, "protocol", "") or "ssh").lower()
        count = len(valid)
        names_preview = ", ".join(Path(p).name for p in valid[:3])
        if count > 3:
            names_preview += f" (+{count - 3} more)"

        self.show_transfer_progress(f"Uploading {count} file(s): {names_preview}", 100)
        log_activity(
            "transfer",
            f"Drag-and-drop transfer ({count} file{'s' if count != 1 else ''})",
            names_preview,
            level="good",
            session=sess_name,
            protocol=proto,
        )
        caps = self.controller.capabilities()
        if caps.sftp and hasattr(self.main, "open_sftp_for_controller"):
            try:
                self.main.open_sftp_for_controller(self.controller)
                dlg = self.main._tool_dialogs.get(id(self.controller))
                if dlg is not None and hasattr(dlg, "_upload_paths"):
                    dlg._upload_paths(valid, dlg.remote.current_dir() or ".")
            except Exception:  # noqa: BLE001
                log.debug("sftp drop handoff skipped", exc_info=True)
        toast(self.main, f"Queued {count} dropped file(s) for transfer", "good")
        return count

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        mime = event.mimeData()
        if mime.hasUrls():
            paths_list = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if not paths_list:
                paths_list = [u.toString() for u in mime.urls()]
            self.handle_dropped_files(paths_list)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

    def _request_close(self) -> None:
        """User pressed the prominent Close button in the header."""
        if self._is_closing:
            return
        idx = self.main.tabs.indexOf(self)
        if idx >= 0:
            self.main.close_tab(idx)

    def cleanup_session_state(self) -> None:
        """Fully clear all session-related data to prevent mixing or leaks.

        Called during tab close to ensure no terminal colours, buffers,
        or state leak into other sessions.
        """
        if self._is_closing:
            return
        self._is_closing = True
        try:
            # Stop logging
            term = getattr(self.controller, "term", None)
            if term is not None:
                if hasattr(term, "stop_logging"):
                    try:
                        term.stop_logging()
                    except Exception:
                        pass
                if hasattr(term, "clear_scrollback"):
                    try:
                        term.clear_scrollback()
                    except Exception:
                        pass
            # Clear info label to remove any terminal-influenced text
            if hasattr(self, "info"):
                self.info.clear()
            # Hide chips
            if hasattr(self, "rec_chip"):
                self.rec_chip.setVisible(False)
        except Exception:
            pass

    def _swap_content(self) -> None:
        old = self._content
        if old is None:
            return
        # Content lives inside the terminal container for visual isolation
        container_layout = self._term_container.layout()
        if container_layout is not None:
            container_layout.removeWidget(old)
        old.hide()
        old.setParent(None)
        self._content = self.controller.widget()
        self._content.setObjectName("terminalContent")
        if container_layout is not None:
            container_layout.addWidget(self._content, 1)
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
        dot_state = {
            SessionState.CONNECTED: "connected",
            SessionState.CONNECTING: "connecting",
            SessionState.RECONNECTING: "reconnecting",
            SessionState.FAILED: "failed",
            SessionState.CLOSED: "disconnected",
        }.get(state, "disconnected")
        if hasattr(self, "status_dot"):
            self.status_dot.set_status(dot_state)
        if hasattr(self, "support_panel"):
            self.support_panel.update_session_context(state=state or "standby")
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
        # Small enough for half-screen / laptop-split use; the dashboard
        # tiles flow-wrap and the sidebar can be dragged narrower.
        self.setMinimumSize(880, 540)
        self.controllers: dict[int, SessionTab] = {}
        # Last "connected" info per controller, for the status-bar summary.
        self._last_connected_info: dict[int, dict] = {}
        # Open (non-modal) tool dialogs keyed by controller id — reuse instead
        # of stacking a new window on every click.
        self._tool_dialogs: dict[int, QWidget] = {}
        self._is_compact_viewport = False

        # Real-time user & connection activity log
        self.activity_log = default_activity_log()
        self._activity_bus_unsub = self.activity_log.attach_bus(self.ctx.bus)
        self._activity_listener_unsub = self.activity_log.subscribe(
            lambda _entry: QTimer.singleShot(0, self._update_activity_badge)
        )

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status_bar()
        self._bind_shortcuts()
        self._setup_tray()
        self._apply_interactive_tooltips()
        if getattr(self.ctx.settings, "mobile_touch_mode", False):
            self.set_mobile_touch_mode(True)
        # Live theme switches re-tint icons and palette-baked chrome.
        theme.add_theme_changed_callback(self._refresh_theme)
        # The window can be deleted without closeEvent (deleteLater, tests,
        # teardown).  Drop the global callback with the C++ object, otherwise a
        # later theme switch fires it on a deleted window and raises.
        self.destroyed.connect(self._on_destroyed_remove_theme_callback)

        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(30_000)
        self._lock_timer.timeout.connect(self._autolock)
        self._lock_timer.start()

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

        self.sidebar = SessionTree(self.ctx.store, settings=self.ctx.settings)
        self.main_splitter.addWidget(self.sidebar)

        # Center tabbed container
        tabs_wrap = QWidget()
        tabs_wrap.setObjectName("workArea")
        tl = QVBoxLayout(tabs_wrap)
        tl.setContentsMargins(0, 2, 4, 4)
        tl.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("sessionTabs")
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        # Framed session tabs keep the workspace's active connection distinct.
        self.tabs.setDocumentMode(False)
        # Content-sized tabs, not stretched to fill the strip:
        # besides looking right, the leftover strip space is what you grab to
        # drag the whole tab strip to another edge (see _setup_docking).
        # NB: setDocumentMode() above re-enables expanding, so this must stay
        # *after* it.
        self.tabs.tabBar().setExpanding(False)
        # Keep Qt's overflow scroller enabled: tab labels remain readable when
        # a power user has many sessions open instead of shrinking indefinitely.
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().setAccessibleName("Open session tabs")
        self.tabs.setAccessibleName("Session workspace")
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

        # Corner buttons — session count + quick actions (modern, distinct)
        corner = QWidget()
        corner.setObjectName("tabCorner")
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(6, 4, 6, 2)
        cl.setSpacing(4)

        # Session count indicator
        self._tab_count_label = QLabel("0")
        self._tab_count_label.setObjectName("tabCount")
        self._tab_count_label.setFixedHeight(18)
        self._tab_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tab_count_label.setToolTip("Number of open sessions")
        self._tab_count_label.setAccessibleName("Open session count")
        cl.addWidget(self._tab_count_label)

        self._themed_corner_buttons: list[tuple[QPushButton, str]] = []

        def corner_button(icon_name: str, tip: str, cb) -> QPushButton:
            b = QPushButton()
            b.setIcon(icon(icon_name))
            self._themed_corner_buttons.append((b, icon_name))
            b.setObjectName("ghost")
            b.setProperty("iconOnly", True)  # square variant: no min-width
            b.setStyleSheet("min-width: 0px; max-width: 26px; min-height: 0px; padding: 0px;")
            b.setToolTip(tip)
            b.setAccessibleName(tip.split(" (")[0])
            b.setStatusTip(tip)
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
        self._tabs_grip.setProperty("iconOnly", True)
        self._tabs_grip.setStyleSheet("min-width: 0px; max-width: 24px; min-height: 0px; padding: 0px;")
        self._tabs_grip.setIcon(icon("grip"))
        self._tabs_grip.setIconSize(QSize(14, 14))
        self._tabs_grip.setFixedSize(24, 24)
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
        # MobaXterm sidebar chrome: rail chevron collapses the panel (the
        # Ctrl+B path — pass False explicitly so the signal never *toggles*);
        # the top-of-panel quick-connect box shares the toolbar's parse path.
        self.sidebar.collapseRequested.connect(lambda: self._toggle_sidebar(False))
        self.sidebar.quickConnectRequested.connect(
            lambda: self._quick_connect_from(self.sidebar.side_quick)
        )
        # Tools page — the pane mirrors the Tools menu (MobaXterm's Tools tab).
        self.sidebar.networkToolsRequested.connect(self.open_network_tools)
        self.sidebar.keyUtilityRequested.connect(self.open_key_utility)
        self.sidebar.rdpServerRequested.connect(self.open_rdp_server_manager)
        self.sidebar.paletteRequested.connect(self.open_command_palette)
        self.sidebar.settingsRequested.connect(self.open_settings)
        self.sidebar.activityLogRequested.connect(self.open_activity_log)
        self.sidebar.supportChatRequested.connect(self.open_support_chat)
        self.sidebar.onboardingRequested.connect(self.open_onboarding_guide)
        self.sidebar.feedbackRequested.connect(self.open_feedback_dialog)

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
        # Startup restore is done — dock moves from here on get a toast.
        self._layout_ready = True
        # Watch our own activation so an in-app RDP desktop gets its keyboard
        # back the moment the application is brought to the front.
        self.installEventFilter(self)

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
        previous = getattr(self, "_tabs_dock", key)
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
        # Feedback for the move — but not for the startup restore.
        if getattr(self, "_layout_ready", False) and key != previous:
            toast(self, f"Session tabs docked {key}", "info")

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
        if obj is self and event.type() == QEvent.Type.WindowActivate:
            # Brought to the front (Alt+Tab, taskbar): the embedded RDP child
            # is not window-managed, so nothing else would give it the
            # keyboard back — do it here.
            self._refocus_current_embedded()
        if obj is getattr(self, "_splitter_handle", None) and event.type() == QEvent.Type.MouseButtonDblClick:
            self.flip_sidebar_side()
            return True
        return super().eventFilter(obj, event)

    def _toggle_sidebar(self, checked: bool | None = None) -> None:
        """checked=True shows the sidebar, checked=False collapses it.

        Called with the action's new state; if None (plain trigger), invert.
        """
        if not hasattr(self, "main_splitter"):
            return
        if checked is None:
            checked = self._sidebar_collapsed  # invert the current state
        self._sidebar_collapsed = not bool(checked)
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

    def _sync_sidebar_actions(self, visible: bool | None = None) -> None:
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
            QApplication.instance(),
            s.theme,
            density=s.density,
            animations=s.animations,
            accent_color=getattr(s, "accent_color", ""),
        )
        if hasattr(self, "_toolbar"):
            if s.toolbar_labels:
                # Studio chrome keeps labels beside smaller, scannable icons.
                self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                self._toolbar.setIconSize(QSize(18, 18))
            else:
                self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                self._toolbar.setIconSize(QSize(18, 18))
        # Dashboard title sizing (comfortable/compact) lives in the global
        # QSS (#dashTitle) — no inline overrides.

    def _on_destroyed_remove_theme_callback(self, *_args) -> None:
        """Drop the global theme callback when the C++ window is deleted."""
        theme.remove_theme_changed_callback(self._refresh_theme)
        for attr in ("_activity_bus_unsub", "_activity_listener_unsub"):
            fn = getattr(self, attr, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
                setattr(self, attr, None)

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
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_sidebar_search)
        QShortcut(QKeySequence("Ctrl+="), self, self.increase_font_size)
        # Ctrl+W and Ctrl+Shift+W are terminal editing keys (backward-word
        # delete).  They deliberately have no tab-closing binding.

        for i in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, lambda idx=i-1: self.switch_to_tab(idx))

    def _focus_quick_connect(self) -> None:
        """Ctrl+Shift+K — jump to the toolbar quick-connect input."""
        self.quick.setFocus()
        self.quick.selectAll()

    def _focus_sidebar_search(self) -> None:
        """Ctrl+F — focus the sidebar session search box."""
        if getattr(self, "_sidebar_collapsed", False):
            self._toggle_sidebar(True)
        if hasattr(self, "sidebar") and hasattr(self.sidebar, "search"):
            self.sidebar.search.setFocus()
            self.sidebar.search.selectAll()

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

        menu.addSeparator()
        menu.addAction("In-Session Support Chat", widget.toggle_support_panel)
        menu.addAction("Connection Activity Log…", self.open_activity_log)
        defn = widget.controller.definition
        if defn.host or defn.target():
            menu.addAction(
                f"Copy Host ({defn.host or defn.target()})",
                lambda: QGuiApplication.clipboard().setText(defn.host or defn.target()),
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
            self._update_tab_tooltip(tab)

    def _update_tab_tooltip(self, tab: SessionTab) -> None:
        """Tab hover tooltip: full title + protocol/target (user feedback).

        Long session names elide in the strip — the tooltip always shows
        the whole identity, and screen readers announce it too.
        """
        idx = self.tabs.indexOf(tab)
        if idx < 0:
            return
        title = tab._custom_title or self.tabs.tabText(idx)
        base = getattr(tab, "_tooltip_base", "")
        tip = f"{title}\n{base}" if base else title
        self.tabs.setTabToolTip(idx, tip)

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
    # Session snapshots
    # ------------------------------------------------------------------
    def _active_saved_session_ids(self) -> list[str]:
        """Saved, non-local session ids currently open, de-duplicated in tab order."""
        ids: list[str] = []
        seen: set[str] = set()
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if not isinstance(tab, SessionTab):
                continue
            defn = tab.controller.definition
            if defn.protocol == "local" or not defn.id or defn.id in seen:
                continue
            if self.ctx.store.get(defn.id) is None:
                continue
            seen.add(defn.id)
            ids.append(defn.id)
        return ids

    def _save_session_snapshot_named(self, name: str) -> bool:
        """Persist a named snapshot; public UI wraps this with a prompt."""
        session_ids = self._active_saved_session_ids()
        if not session_ids:
            toast(self, "Open at least one saved SSH or RDP session before saving a snapshot.", "warn")
            return False
        name = (name or "").strip()
        if not name:
            return False
        entries = [
            e for e in (getattr(self.ctx.settings, "session_snapshots", []) or [])
            if isinstance(e, dict) and e.get("name") != name
        ]
        entries.insert(
            0,
            {
                "name": name[:80],
                "session_ids": session_ids,
                "created_at": time.time(),
            },
        )
        self.ctx.settings.session_snapshots = entries[:12]
        self.ctx.settings.save(paths.settings_file())
        toast(self, f"Saved snapshot “{name}” ({len(session_ids)} session{'s' if len(session_ids) != 1 else ''})", "good")
        return True

    def save_session_snapshot(self) -> None:
        session_ids = self._active_saved_session_ids()
        if not session_ids:
            toast(self, "Open at least one saved SSH or RDP session before saving a snapshot.", "warn")
            return
        default = f"Workspace {time.strftime('%Y-%m-%d %H:%M')}"
        name, ok = QInputDialog.getText(self, "Save session snapshot", "Snapshot name:", text=default)
        if ok:
            self._save_session_snapshot_named(name)

    def _snapshot_entries(self) -> list[dict]:
        entries = getattr(self.ctx.settings, "session_snapshots", []) or []
        return [e for e in entries if isinstance(e, dict) and e.get("session_ids")]

    def _populate_snapshot_menu(self) -> None:
        menu = getattr(self, "_snapshot_restore_menu", None)
        if menu is None:
            return
        menu.clear()
        entries = self._snapshot_entries()
        if not entries:
            empty = menu.addAction("No snapshots yet")
            empty.setEnabled(False)
            return
        for idx, entry in enumerate(entries):
            ids = [sid for sid in entry.get("session_ids", []) if isinstance(sid, str)]
            label = f"{entry.get('name', 'Snapshot')}  ({len(ids)} session{'s' if len(ids) != 1 else ''})"
            act = menu.addAction(icon("connect"), label, lambda _=False, i=idx: self.restore_session_snapshot(i))
            created = entry.get("created_at")
            if created:
                act.setToolTip(time.strftime("Saved %Y-%m-%d %H:%M", time.localtime(float(created))))
        menu.addSeparator()
        menu.addAction(icon("trash"), "Clear snapshots", self.clear_session_snapshots)

    def restore_session_snapshot(self, index: int) -> None:
        entries = self._snapshot_entries()
        if not (0 <= index < len(entries)):
            return
        entry = entries[index]
        opened = 0
        missing = 0
        for sid in entry.get("session_ids", []):
            if not isinstance(sid, str):
                continue
            if self.ctx.store.get(sid) is None:
                missing += 1
                continue
            if self.connect_session(sid) is not None:
                opened += 1
        name = entry.get("name", "Snapshot")
        if opened:
            msg = f"Restored “{name}” ({opened} session{'s' if opened != 1 else ''})"
            if missing:
                msg += f" · {missing} missing"
            toast(self, msg, "good" if not missing else "warn")
        elif missing:
            toast(self, f"No sessions from “{name}” still exist.", "warn")

    def clear_session_snapshots(self) -> None:
        if not self._snapshot_entries():
            return
        box = QMessageBox(self)
        box.setWindowTitle("Clear session snapshots")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("Delete all saved session snapshots?")
        box.setInformativeText("Saved sessions themselves will not be changed.")
        yes = box.addButton("Clear Snapshots", QMessageBox.ButtonRole.YesRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.NoRole)
        box.setDefaultButton(yes)
        box.exec()
        if box.clickedButton() is yes:
            self.ctx.settings.session_snapshots = []
            self.ctx.settings.save(paths.settings_file())
            toast(self, "Session snapshots cleared", "info")

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

    def save_settings(self) -> None:
        """Persist settings now (used by tool dialogs that edit them live)."""
        self.ctx.settings.save(paths.settings_file())

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def connect_session(self, session_id: str) -> SessionTab | None:
        """Open a saved session by id; returns its tab (or None on failure).

        The return value lets callers chain follow-up actions on the new tab
        (e.g. *Connect & SFTP* opens the browser once the transport is up);
        every other caller (sidebar double-click, palette, dashboard) simply
        ignores it.
        """
        defn = self.ctx.store.get(session_id)
        if defn is None:
            return None
        return self.open_session(defn)

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
        tab._tooltip_base = f"{defn.protocol.upper()} · {defn.target()}"
        self.tabs.addTab(tab, defn.display_name())
        self.tabs.setCurrentWidget(tab)
        # Protocol mini-badge — colour-coded (SSH/RDP/local) tab identity
        self.tabs.setTabIcon(self.tabs.indexOf(tab), protocol_badge(defn.protocol, plugin.icon_name))
        self._update_tab_tooltip(tab)

        def _set_title(t, _tab=tab):
            if _tab._custom_title:
                return
            idx = self.tabs.indexOf(_tab)
            if idx >= 0:
                self.tabs.setTabText(idx, t)
                self._update_tab_tooltip(_tab)

        controller.titleChanged.connect(_set_title)
        # Status-bar summary follows the session.
        controller.statusInfo.connect(
            lambda info, c=controller: self._on_controller_status(info, c)
        )
        # Live state chip + window title follow the current tab's session.
        controller.stateChanged.connect(
            lambda state, c=controller: self._on_tab_state_changed(state, c)
        )
        controller.start()
        self._update_empty_state()
        log_activity(
            "session",
            f"Opened {defn.protocol.upper()} session",
            f"Target: {defn.target()}",
            level="info",
            session=defn.display_name(),
            protocol=defn.protocol,
        )
        # Recently-connected sessions power the sidebar's Recent section.
        if defn.id and defn.protocol != "local":
            try:
                self.ctx.settings.touch_recent_session(defn.id)
                self.ctx.settings.save(paths.settings_file())
                if hasattr(self, "sidebar"):
                    self.sidebar.reload()
            except Exception:  # noqa: BLE001 — recents must not break connects
                log.debug("recent-session tracking failed", exc_info=True)
        return tab

    def close_tab(self, index: int) -> None:
        """Close a session tab and fully clear all related state.

        Guarantees:
        - No terminal colours or buffers leak into other sessions
        - All controls remain visually distinct and stable
        - Associated dialogs (SFTP, tunnels) are closed
        - Controller, term, logging and tracking dicts are cleaned
        - No exception during cleanup disrupts tool stability
        """
        if index < 0 or index >= self.tabs.count():
            return
        widget = self.tabs.widget(index)
        if isinstance(widget, SessionTab) and not self._safe_to_close(widget):
            return

        # ── Full session state cleanup ──
        if isinstance(widget, SessionTab):
            try:
                widget.cleanup_session_state()
            except Exception:
                log.exception("pre-cleanup failed")

            controller = widget.controller
            cid = id(controller)

            # Close any tool dialogs tied to this controller (SFTP, tunnels, etc.)
            try:
                dlg = self._tool_dialogs.pop(cid, None)
                if dlg is not None:
                    try:
                        dlg.close()
                        dlg.deleteLater()
                    except Exception:
                        log.debug("failed to close tool dialog", exc_info=True)
                # Defensive sweep: dialogs that store controller via attribute
                for other_cid, other_dlg in list(self._tool_dialogs.items()):
                    try:
                        d_ctrl = getattr(other_dlg, "controller", None) or getattr(other_dlg, "_controller", None)
                        if d_ctrl is controller or id(d_ctrl) == cid:
                            other_dlg.close()
                            other_dlg.deleteLater()
                            self._tool_dialogs.pop(other_cid, None)
                    except Exception:
                        continue
            except Exception:
                log.exception("tool-dialog cleanup failed")

            # Stop logging and clear terminal buffer to avoid colour mixing
            try:
                term = getattr(controller, "term", None)
                if term is not None:
                    if hasattr(term, "stop_logging"):
                        try:
                            term.stop_logging()
                        except Exception:
                            pass
                    if hasattr(term, "clear_scrollback"):
                        try:
                            term.clear_scrollback()
                        except Exception:
                            pass
            except Exception:
                log.debug("terminal cleanup failed", exc_info=True)

            # Stop the controller — blocking stop for thorough teardown
            try:
                if hasattr(controller, "stop_blocking"):
                    controller.stop_blocking("closed by user")
                else:
                    controller.stop("closed by user")
            except Exception:
                log.exception("error stopping session controller")
            finally:
                # Always clear tracking structures even if stop() raised
                self._last_connected_info.pop(cid, None)
                self.controllers.pop(cid, None)

            # Disconnect signals to prevent post-deletion callbacks
            for sig_name in ("stateChanged", "statusInfo", "finished", "reconnectScheduled", "widgetChanged", "transportUp", "titleChanged"):
                try:
                    sig = getattr(controller, sig_name, None)
                    if sig is not None:
                        sig.disconnect()
                except Exception:
                    pass

            try:
                controller.setParent(None)
            except Exception:
                pass

            # Remove tab from UI before deleting the widget to avoid flicker
            try:
                self.tabs.removeTab(index)
            except Exception:
                log.exception("removeTab failed")

            try:
                controller.deleteLater()
            except Exception:
                pass
            try:
                widget.deleteLater()
            except Exception:
                pass
        else:
            # Non-session widget (should not happen, but be safe)
            try:
                self.tabs.removeTab(index)
            except Exception:
                pass
            if widget is not None:
                try:
                    widget.deleteLater()
                except Exception:
                    pass

        self._update_empty_state()
        self._update_session_status(self.current_controller())

    def current_controller(self) -> SessionController | None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, SessionTab):
            return widget.controller
        return None

    def _build_status_bar(self) -> None:
        """Status bar: session identity left, live indicators + accessibility & feedback right."""
        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)

        self.session_info_label = QLabel("")
        self.session_info_label.setObjectName("statusSession")
        self.session_info_label.setAccessibleName("Current session")
        status.addWidget(self.session_info_label, 1)

        # Real-time connection status indicator dot + label
        self.status_indicator = StatusIndicator("disconnected")
        self.status_indicator.setObjectName("statusConnectionIndicator")
        status.addPermanentWidget(self.status_indicator)

        # Live connection state of the *current* tab (CONNECTING/CONNECTED/
        # RECONNECTING/CLOSED/FAILED) — the at-a-glance health indicator.
        self.state_chip = StateChip("STANDBY", "fg_dim")
        self.state_chip.setAccessibleName("Session state")
        status.addPermanentWidget(self.state_chip)

        # Live user & connection activity log button
        self.activity_btn = QPushButton("0 events")
        self.activity_btn.setObjectName("subtle")
        self.activity_btn.setIcon(icon("activity", size=13))
        self.activity_btn.setFixedHeight(22)
        self.activity_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.activity_btn.setToolTip("Open real-time Connection Status & Activity Log (Ctrl+Shift+A)")
        self.activity_btn.clicked.connect(self.open_activity_log)
        status.addPermanentWidget(self.activity_btn)

        # Accessibility font scaling controls
        self.font_dec_btn = QPushButton("A-")
        self.font_dec_btn.setObjectName("subtle")
        self.font_dec_btn.setFixedSize(26, 22)
        self.font_dec_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.font_dec_btn.setToolTip("Decrease font size (Ctrl+-)")
        self.font_dec_btn.clicked.connect(self.decrease_font_size)
        status.addPermanentWidget(self.font_dec_btn)

        self.font_size_label = QLabel(f"{self.ctx.settings.font_size}pt")
        self.font_size_label.setObjectName("caption")
        self.font_size_label.setToolTip("Current terminal & UI font size (Ctrl+0 to reset)")
        status.addPermanentWidget(self.font_size_label)

        self.font_inc_btn = QPushButton("A+")
        self.font_inc_btn.setObjectName("subtle")
        self.font_inc_btn.setFixedSize(26, 22)
        self.font_inc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.font_inc_btn.setToolTip("Increase font size (Ctrl++)")
        self.font_inc_btn.clicked.connect(self.increase_font_size)
        status.addPermanentWidget(self.font_inc_btn)

        # One-click Dark / Light mode toggle button
        self.theme_toggle_btn = QPushButton(
            "☾ Dark" if self.ctx.settings.is_dark_mode() else "☀ Light"
        )
        self.theme_toggle_btn.setObjectName("subtle")
        self.theme_toggle_btn.setFixedHeight(22)
        self.theme_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_toggle_btn.setToolTip("Toggle Dark / Light theme mode (Ctrl+Alt+T)")
        self.theme_toggle_btn.clicked.connect(self.toggle_dark_light_theme)
        status.addPermanentWidget(self.theme_toggle_btn)

        # Direct UI Feedback button
        self.feedback_status_btn = QPushButton("Feedback")
        self.feedback_status_btn.setObjectName("subtle")
        self.feedback_status_btn.setIcon(icon("edit", size=13))
        self.feedback_status_btn.setFixedHeight(22)
        self.feedback_status_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.feedback_status_btn.setToolTip(
            "Suggest improvements or report an issue directly from the UI (Ctrl+Shift+I)"
        )
        self.feedback_status_btn.clicked.connect(self.open_feedback_dialog)
        status.addPermanentWidget(self.feedback_status_btn)

        self.status_label = QLabel("")
        self.status_label.setObjectName("caption")
        status.addPermanentWidget(self.status_label)
        self._update_activity_badge()

    def _tab_changed(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, SessionTab):
            caps = widget.controller.capabilities()
            if caps.shell:
                QTimer.singleShot(0, lambda: widget.controller.widget().setFocus())
            # An embedded (in-app) RDP desktop is a reparented X11 window that
            # is not window-managed: activating its tab must hand it keyboard
            # focus again, otherwise the keyboard stays dead after switching
            # tabs (or back from another application).
            focus_embedded = getattr(widget.controller, "focus_embedded", None)
            if callable(focus_embedded):
                QTimer.singleShot(0, focus_embedded)
        controller = self.current_controller()
        self._update_session_status(controller)
        self._update_state_chip(controller)

    def _refocus_current_embedded(self) -> None:
        """Give the current tab's in-app RDP desktop keyboard focus again."""
        focus_embedded = getattr(self.current_controller(), "focus_embedded", None)
        if callable(focus_embedded):
            focus_embedded()

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

    # ------------------------------------------------------------------
    # Live state chip (status bar)
    # ------------------------------------------------------------------
    def _update_state_chip(self, controller: SessionController | None) -> None:
        """Mirror the current tab's session state in the status-bar chip & live dot."""
        if controller is None:
            self.state_chip.set_color("fg_dim")
            self.state_chip.setText("STANDBY")
            if hasattr(self, "status_indicator"):
                self.status_indicator.set_status("disconnected")
            self.setWindowTitle(APP_NAME)
            return
        state = controller.state()
        self.state_chip.set_color(STATE_COLORS.get(state, "fg_dim"))
        self.state_chip.setText((state or "").upper())
        if hasattr(self, "status_indicator"):
            dot_state = {
                SessionState.CONNECTED: "connected",
                SessionState.CONNECTING: "connecting",
                SessionState.RECONNECTING: "reconnecting",
                SessionState.FAILED: "failed",
                SessionState.CLOSED: "disconnected",
            }.get(state, "disconnected")
            self.status_indicator.set_status(dot_state)

    def _on_tab_state_changed(self, state: str, controller: SessionController) -> None:
        defn = getattr(controller, "definition", None)
        sess_name = defn.display_name() if defn and hasattr(defn, "display_name") else "Session"
        proto = getattr(defn, "protocol", "") or "ssh"
        level_map = {
            SessionState.CONNECTED: "good",
            SessionState.CONNECTING: "info",
            SessionState.RECONNECTING: "warn",
            SessionState.FAILED: "bad",
            SessionState.CLOSED: "info",
        }
        if state:
            log_activity(
                "connection",
                f"Session state → {state.upper()}",
                f"{proto.upper()} · {defn.target() if defn else ''}",
                level=level_map.get(state, "info"),
                session=sess_name,
                protocol=proto,
            )
        if self.current_controller() is not controller:
            return
        self._update_state_chip(controller)
        if state and controller.definition.protocol != "local":
            self.setWindowTitle(f"{state.upper()} · {APP_NAME}")

    def _update_activity_badge(self) -> None:
        if not hasattr(self, "activity_btn"):
            return
        total = self.activity_log.count() if hasattr(self, "activity_log") else 0
        self.activity_btn.setText(f"{total} event{'s' if total != 1 else ''}")

    # -- dialogs -------------------------------------------------------------
    def new_session(self, *args) -> None:
        from .session_dialog import SessionDialog

        group = self.sidebar.selected_group()
        dlg = SessionDialog(self.ctx, Session(group=group), self)
        if dlg.exec():
            self.sidebar.reload()
            self._refresh_dashboard()
            if dlg.connect_requested and dlg.session.id:
                self.connect_session(dlg.session.id)

    def new_rdp_session(self, *args) -> None:
        """Open the New Session dialog pre-set to RDP (port 3389)."""
        from .session_dialog import SessionDialog

        group = self.sidebar.selected_group()
        dlg = SessionDialog(
            self.ctx,
            Session(protocol=PROTOCOL_RDP, port=3389, group=group),
            self,
        )
        if dlg.exec():
            self.sidebar.reload()
            self._refresh_dashboard()
            if dlg.connect_requested and dlg.session.id:
                self.connect_session(dlg.session.id)

    def new_sftp_session(self, *args) -> None:
        """Open SFTP on the current SSH tab, or prompt to create an SSH/SFTP session."""
        tab = self._current_tab()
        if tab is not None and tab.controller.capabilities().sftp:
            tab.controller.open_sftp()
            return
        self.new_session()

    def toggle_pin_session(self, session_id: str) -> None:
        """Pin or unpin a saved session and refresh sidebar + dashboard."""
        if hasattr(self, "sidebar") and hasattr(self.sidebar, "_toggle_pin"):
            self.sidebar._toggle_pin(session_id)
        self._refresh_dashboard()

    def delete_session(self, session_id: str) -> None:
        self._delete_session(session_id)

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
            if dlg.connect_requested and dlg.session.id:
                self.connect_session(dlg.session.id)

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
            # SettingsDialog edits a detached candidate (and Reset creates a
            # fresh defaults object).  Publish that candidate to every live
            # service only after it has been persisted successfully.
            self.ctx.settings = dlg.result_settings
            share_service = getattr(self.ctx, "share_service", None)
            if share_service is not None:
                try:
                    share_service.reload_settings(self.ctx.settings)
                except Exception as exc:  # noqa: BLE001
                    toast(self, f"File-sharing settings could not be applied: {exc}", "error")
            self._apply_ui_prefs()
            self._sync_theme_actions()
            self._apply_terminal_prefs()
            # The dashboard may have been customised in Settings.
            self._refresh_dashboard()

    def _apply_terminal_prefs(self) -> None:
        """Push font/scheme/blink/spacing prefs to open terminals."""
        s = self.ctx.settings
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if not isinstance(w, SessionTab):
                continue
            term = getattr(w.controller, "term", None)
            if term is None:
                continue
            try:
                if hasattr(term, "apply_font"):
                    term.apply_font(s.font_family, s.font_size)
                # apply_terminal_prefs covers scheme/blink/spacing; the
                # legacy apply_theme alias maps to it on TerminalView.
                if hasattr(term, "apply_terminal_prefs"):
                    term.apply_terminal_prefs()
                elif hasattr(term, "apply_theme"):
                    term.apply_theme()
            except Exception:  # noqa: BLE001
                log.exception("apply terminal preferences failed")

    def apply_theme_id(self, theme_id: str) -> None:
        from ..core.settings import DARK_THEMES, THEME_CHOICES, THEME_IDS

        if theme_id not in THEME_IDS:
            return
        self.ctx.settings.theme = theme_id
        if theme_id in DARK_THEMES:
            self.ctx.settings.preferred_dark_theme = theme_id
        self.ctx.settings.save(paths.settings_file())
        theme.apply_theme(
            QApplication.instance(),
            theme_id,
            density=self.ctx.settings.density,
            animations=self.ctx.settings.animations,
            accent_color=getattr(self.ctx.settings, "accent_color", ""),
        )
        self._sync_theme_actions()
        self._apply_terminal_prefs()
        if hasattr(self, "theme_toggle_btn"):
            self.theme_toggle_btn.setText(
                "☾ Dark" if self.ctx.settings.is_dark_mode() else "☀ Light"
            )
        label = dict(THEME_CHOICES).get(theme_id, theme_id)
        short_label = label.split("—")[0].strip()
        log_activity("ui", f"Theme changed to {short_label}", f"theme_id={theme_id}", level="info")
        toast(self, f"Theme: {short_label}", "info")

    def toggle_dark_light_theme(self) -> str:
        """Switch between Dark mode (preferred dark theme) and Light mode ('mobaxterm')."""
        from ..core.settings import DARK_THEMES, DEFAULT_THEME

        if self.ctx.settings.is_dark_mode():
            self.ctx.settings.preferred_dark_theme = self.ctx.settings.theme
            target = "mobaxterm"
        else:
            pref = getattr(self.ctx.settings, "preferred_dark_theme", DEFAULT_THEME)
            target = pref if pref in DARK_THEMES else DEFAULT_THEME
        self.apply_theme_id(target)
        return target

    def set_font_size(self, size: int) -> int:
        """Set terminal & UI font size (clamped to 7..24 pt) and apply live."""
        clamped = max(7, min(24, int(size)))
        self.ctx.settings.font_size = clamped
        self._save_settings()
        if hasattr(self, "font_size_label"):
            self.font_size_label.setText(f"{clamped}pt")
        self._apply_terminal_prefs()
        log_activity("ui", f"Font size set to {clamped}pt", "", level="info")
        toast(self, f"Font size: {clamped}pt", "info")
        return clamped

    def increase_font_size(self) -> int:
        return self.set_font_size(int(self.ctx.settings.font_size) + 1)

    def decrease_font_size(self) -> int:
        return self.set_font_size(int(self.ctx.settings.font_size) - 1)

    def reset_font_size(self) -> int:
        return self.set_font_size(10)

    def _current_session_tab(self) -> SessionTab | None:
        return self._current_tab()

    def toggle_current_session_support(self) -> None:
        tab = self._current_tab()
        if tab is not None:
            tab.toggle_support_panel()
        else:
            self.open_support_chat()

    def open_activity_log(self, *_args):
        """Open the real-time Connection Status & Activity Log dialog."""
        from .activity_dialog import ActivityLogDialog

        dlg = ActivityLogDialog(self, self.activity_log, self)
        animate_in(dlg)
        dlg.show()
        dlg.raise_()
        return dlg

    def open_support_chat(self, *_args):
        """Open the In-Session Support & Instant Troubleshooting Chat dialog."""
        from .support_chat import SupportChatDialog

        dlg = SupportChatDialog(self, self)
        animate_in(dlg)
        dlg.show()
        dlg.raise_()
        return dlg

    def open_onboarding_guide(self, *_args):
        """Open the step-by-step Interactive Onboarding Tour for new users."""
        from .onboarding import OnboardingGuideDialog

        dlg = OnboardingGuideDialog(self, self)
        animate_in(dlg)
        dlg.show()
        dlg.raise_()
        return dlg

    def open_feedback_dialog(
        self,
        *_args,
        prefill_title: str = "",
        prefill_description: str = "",
        category: str = "improvement",
    ):
        """Open the User Feedback dialog to suggest improvements from the UI."""
        from .feedback_dialog import FeedbackDialog

        dlg = FeedbackDialog(
            self,
            prefill_title=prefill_title,
            prefill_description=prefill_description,
            category=category,
            parent=self,
        )
        animate_in(dlg)
        dlg.show()
        dlg.raise_()
        return dlg

    def set_interactive_tooltips(self, enabled: bool) -> None:
        self.ctx.settings.interactive_tooltips = bool(enabled)
        self._save_settings()
        self._apply_interactive_tooltips()

    def _apply_interactive_tooltips(self) -> None:
        enabled = bool(getattr(self.ctx.settings, "interactive_tooltips", True))
        if hasattr(self, "quick"):
            set_interactive_tooltip(
                self.quick,
                "Quick Connect",
                "Connect to any SSH or RDP host immediately (port 3389 opens RDP).",
                shortcut="Ctrl+Shift+K",
                tip="Type user@host:3389 and press Enter for a one-step RDP session.",
                enabled=enabled,
            )
        if hasattr(self, "activity_btn"):
            set_interactive_tooltip(
                self.activity_btn,
                "Connection Status & Activity Log",
                "Inspect live session state transitions, file transfers, and user events.",
                shortcut="Ctrl+Shift+A",
                tip="Filter events by severity or export the log to JSON.",
                enabled=enabled,
            )
        if hasattr(self, "theme_toggle_btn"):
            set_interactive_tooltip(
                self.theme_toggle_btn,
                "Dark / Light Theme Toggle",
                "Switch between your preferred Dark palette and Light mode.",
                shortcut="Ctrl+Alt+T",
                tip="Customise 7 palettes and accent colours in Settings (Ctrl+,).",
                enabled=enabled,
            )
        if hasattr(self, "feedback_status_btn"):
            set_interactive_tooltip(
                self.feedback_status_btn,
                "Send Feedback",
                "Suggest improvements or report issues directly from the UI.",
                shortcut="Ctrl+Shift+I",
                tip="Includes optional anonymous UI diagnostics.",
                enabled=enabled,
            )

    def set_mobile_touch_mode(self, enabled: bool) -> None:
        """Enable or disable responsive tablet/smartphone touch layout."""
        enabled = bool(enabled)
        self.ctx.settings.mobile_touch_mode = enabled
        self._save_settings()
        act = getattr(self, "_act_mobile_mode", None)
        if act is not None:
            act.blockSignals(True)
            act.setChecked(enabled)
            act.blockSignals(False)
        self._apply_responsive_layout(force_mobile=enabled)
        log_activity(
            "ui",
            f"Mobile / Touch mode {'enabled' if enabled else 'disabled'}",
            "",
            level="info",
        )

    def toggle_mobile_touch_mode(self) -> bool:
        new_state = not bool(getattr(self.ctx.settings, "mobile_touch_mode", False))
        self.set_mobile_touch_mode(new_state)
        return new_state

    def _apply_responsive_layout(self, *, force_mobile: bool | None = None) -> None:
        """Adapt toolbar, sidebar, and touch targets for compact/mobile viewports."""
        is_mobile = (
            bool(force_mobile)
            if force_mobile is not None
            else (
                bool(getattr(self.ctx.settings, "mobile_touch_mode", False))
                or self._is_compact_viewport
            )
        )
        self.setProperty("mobileMode", is_mobile)
        if hasattr(self, "_toolbar"):
            if is_mobile:
                self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                self._toolbar.setIconSize(QSize(22, 22))
                if not getattr(self, "_sidebar_collapsed", False):
                    self._toggle_sidebar(False)
            else:
                if self.ctx.settings.toolbar_labels:
                    self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                else:
                    self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                self._toolbar.setIconSize(QSize(18, 18))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        try:
            w = event.size().width()
            compact = 0 < w < 760
            if compact != getattr(self, "_is_compact_viewport", False):
                self._is_compact_viewport = compact
                self._apply_responsive_layout()
        except Exception:  # noqa: BLE001
            pass

    def _save_settings(self) -> None:
        try:
            self.ctx.settings.save(paths.settings_file())
        except OSError:
            log.debug("failed to save settings", exc_info=True)

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
        """Lock the vault after configured inactivity (Settings → Security).

        The timer fires every 30 s; the vault itself tracks activity via
        ``touch()`` on every access, so only the idle threshold matters here.
        Set 0 minutes in Settings to disable auto-lock entirely.
        """
        minutes = int(getattr(self.ctx.settings, "vault_autolock_minutes", 0) or 0)
        if minutes <= 0:
            return
        try:
            if self.ctx.vault.lock_if_due(minutes):
                toast(self, "Credential vault locked after inactivity", "info")
        except Exception:  # noqa: BLE001 — a lock failure must never crash the timer
            log.exception("vault auto-lock failed")

    def closeEvent(self, event) -> None:  # noqa: N802
        """Real, explicit application exit.

        With ``quitOnLastWindowClosed`` disabled (see :mod:`rdpstudio.app`),
        this is the *only* path that ends the process — reached by the user
        closing the window itself, the Exit menu action, or the tray's Quit
        action (both just call :meth:`close`, which triggers this). Closing
        the last session tab must never land here: that only empties the
        tab strip and shows the dashboard, keeping the app running and
        ready to accept new connections.
        """
        # Close all tool dialogs first for clean shutdown
        global _MAIN
        if _MAIN is self:
            _MAIN = None
        self._on_destroyed_remove_theme_callback()
        for dlg in list(self._tool_dialogs.values()):
            try:
                dlg.close()
                dlg.deleteLater()
            except Exception:
                pass
        self._tool_dialogs.clear()

        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, SessionTab):
                try:
                    # Full cleanup: logging, buffers, and blocking teardown
                    try:
                        w.cleanup_session_state()
                    except Exception:
                        pass
                    # Blocking teardown: the event loop won't run again after
                    # closeEvent, so deferred shutdowns would leave worker
                    # threads alive at exit.
                    w.controller.stop_blocking("app closed")
                except Exception:
                    log.exception("error stopping session on shutdown")
        self._last_connected_info.clear()
        self.controllers.clear()
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
        self._closed_once = True
        if event.isAccepted():
            # quitOnLastWindowClosed is off, so nothing else will end the
            # process — do it ourselves now that the window is really going
            # away (not just hidden, e.g. by the tray's "Show / hide").
            app = QApplication.instance()
            if app is not None:
                app.quit()
