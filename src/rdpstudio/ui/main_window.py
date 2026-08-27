"""Main window: tabbed sessions, sidebar, toolbar, quick connect, tools & command palette."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
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
    QToolBar,
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
from .command_palette import CommandPaletteDialog
from .sidebar import SessionTree
from .theme import icon, palette
from .widgets import STATE_COLORS, StateChip, animate_in, pulse, toast

log = get_logger("ui.main")

_MAX_IMPORT_BYTES = 32 * 1024 * 1024

_MAIN = None


class _HistoryLineEdit(QLineEdit):
    """QLineEdit with MobaXterm-style Up/Down command-history recall."""

    _HISTORY_MAX = 100

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.history: list[str] = []
        self._hist_idx = -1
        self._draft = ""

    def remember(self, text: str) -> None:
        if not self.history or self.history[-1] != text:
            self.history.append(text)
            if len(self.history) > self._HISTORY_MAX:
                self.history.pop(0)
        self._hist_idx = -1
        self._draft = ""

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Up and self.history:
            if self._hist_idx == -1:
                self._draft = self.text()
                self._hist_idx = len(self.history) - 1
            elif self._hist_idx > 0:
                self._hist_idx -= 1
            self.setText(self.history[self._hist_idx])
            self.setCursorPosition(len(self.text()))
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down and self._hist_idx != -1:
            if self._hist_idx < len(self.history) - 1:
                self._hist_idx += 1
                self.setText(self.history[self._hist_idx])
            else:
                self._hist_idx = -1
                self.setText(self._draft)
            self.setCursorPosition(len(self.text()))
            event.accept()
            return
        super().keyPressEvent(event)


class CommandBar(QWidget):
    """Beautiful per-tab command line — bento pill, natural."""

    commandSent = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("commandBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        prompt = QLabel("❯")
        prompt.setObjectName("commandPrompt")
        prompt.setStyleSheet("font-size: 13px; font-weight: 700; padding-left: 2px;")
        layout.addWidget(prompt)

        self.line = _HistoryLineEdit()
        self.line.setObjectName("commandLine")
        self.line.setPlaceholderText("Type a command — Enter runs, ↑↓ history")
        self.line.setClearButtonEnabled(True)
        self.line.returnPressed.connect(self._on_return)
        layout.addWidget(self.line, 1)

    def _on_return(self) -> None:
        text = self.line.text().strip()
        if not text:
            return
        self.line.remember(text)
        self.line.clear()
        self.commandSent.emit(text)

    @property
    def history(self) -> list[str]:
        return self.line.history


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
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(8)

        self.chip = StateChip("connecting", "info")
        h.addWidget(self.chip)

        self.rec_chip = StateChip("● REC", "bad")
        self.rec_chip.setVisible(False)
        self.rec_chip.setToolTip("Logging active session output to file")
        h.addWidget(self.rec_chip)

        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.info.setStyleSheet("font-size: 12px; font-weight: 500;")
        h.addWidget(self.info, 1)

        # Session action buttons — compact icon-style
        def make_action_btn(text, icon_name, tip, cb):
            b = QPushButton(text)
            if icon_name:
                b.setIcon(icon(icon_name))
            b.setObjectName("subtle")
            b.setToolTip(tip)
            b.clicked.connect(cb)
            b.setFixedHeight(26)
            b.setFixedWidth(70)
            b.setStyleSheet(
                b.styleSheet()
                + "font-size: 11px; font-weight: 600; padding: 2px 8px; "
                + "border-radius: 4px;"
            )
            return b

        # One state-aware action button: Stop while live, Reconnect when down.
        self.btn_reconnect = QPushButton("Stop")
        self.btn_reconnect.setIcon(icon("stop", palette()["accent_text"]))
        self.btn_reconnect.setObjectName("primary")
        self.btn_reconnect.clicked.connect(self._on_action_btn)
        self.btn_reconnect.setVisible(False)
        self.btn_reconnect.setFixedHeight(26)
        self.btn_reconnect.setFixedWidth(80)
        self.btn_reconnect.setStyleSheet(
            self.btn_reconnect.styleSheet()
            + "font-size: 11px; font-weight: 700; padding: 2px 10px; "
            + "border-radius: 4px;"
        )
        h.addWidget(self.btn_reconnect)

        caps = controller.capabilities()

        if caps.sftp:
            b = make_action_btn("Files", "folder", "Browse remote files (SFTP)", controller.open_sftp)
            h.addWidget(b)

        # Close button for the tab
        close_btn = QPushButton()
        close_btn.setIcon(icon("close"))
        close_btn.setObjectName("ghost")
        close_btn.setToolTip("Close this session tab")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { border-radius: 4px; padding: 2px; }"
            "QPushButton:hover { background: " + palette()["panel3"] + "; }"
        )
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


class MainWindow(QMainWindow):
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

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._bind_shortcuts()
        self._setup_tray()

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
    def _build_menu(self) -> None:
        """MobaXterm-style menu layout: File, View, Tools, Tabs, Session, Help."""
        m_file = self.menuBar().addMenu("&File")

        act = QAction(icon("plus"), "&New session…", self)
        act.setShortcut(QKeySequence("Ctrl+N"))
        act.triggered.connect(self.new_session)
        m_file.addAction(act)

        act = QAction(icon("console"), "New local &terminal", self)
        act.setShortcut(QKeySequence("Ctrl+Shift+T"))
        act.setStatusTip("Open a native local shell in a new tab")
        act.triggered.connect(self.open_local_terminal)
        m_file.addAction(act)

        m_file.addSeparator()

        imp = m_file.addMenu("&Import")
        a = QAction("From ~/.ssh/config", self)
        a.triggered.connect(self._import_ssh_config)
        imp.addAction(a)
        a = QAction("From file (JSON)…", self)
        a.triggered.connect(self._import_json)
        imp.addAction(a)

        exp = QAction("&Export sessions to file…", self)
        exp.triggered.connect(self._export_json)
        m_file.addAction(exp)
        m_file.addSeparator()

        q = QAction("E&xit", self)
        q.setShortcut(QKeySequence("Ctrl+Q"))
        q.triggered.connect(self.close)
        m_file.addAction(q)

        m_view = self.menuBar().addMenu("&View")

        act = QAction(icon("search"), "Command &Palette / Switcher…", self)
        act.setShortcut(QKeySequence("Ctrl+P"))
        act.setStatusTip("Search sessions, tabs, tools and actions")
        act.triggered.connect(self.open_command_palette)
        m_view.addAction(act)

        self._act_sidebar_menu = QAction(icon("panel"), "&Toggle Sidebar", self)
        self._act_sidebar_menu.setShortcut(QKeySequence("Ctrl+B"))
        self._act_sidebar_menu.setCheckable(True)
        self._act_sidebar_menu.toggled.connect(self._toggle_sidebar)
        m_view.addAction(self._act_sidebar_menu)

        m_view.addSeparator()

        m_themes = m_view.addMenu("&Theme")
        from ..core.settings import THEME_CHOICES

        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for tid, label in THEME_CHOICES:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self.ctx.settings.theme == tid)
            act.triggered.connect(lambda checked, t=tid: checked and self.apply_theme_id(t))
            self._theme_group.addAction(act)
            m_themes.addAction(act)
            self._theme_actions[tid] = act

        m_tools = self.menuBar().addMenu("&Tools")
        a = QAction(icon("server"), "Network Tools & Port &Scanner…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+N"))
        a.triggered.connect(self.open_network_tools)
        m_tools.addAction(a)

        a = QAction(icon("key"), "SSH &Key Utility & Converter…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+U"))
        a.triggered.connect(self.open_key_utility)
        m_tools.addAction(a)

        m_tools.addSeparator()

        a = QAction(icon("windows"), "RDP server &manager…", self)
        a.triggered.connect(self.open_rdp_server_manager)
        m_tools.addAction(a)

        a = QAction(icon("gear"), "&Settings…", self)
        a.setShortcut(QKeySequence("Ctrl+,"))
        a.triggered.connect(self.open_settings)
        m_tools.addAction(a)

        a = QAction("Open &logs folder", self)
        a.triggered.connect(lambda: paths.logs_dir() and self._open_path(paths.logs_dir()))
        m_tools.addAction(a)

        m_tabs = self.menuBar().addMenu("&Tabs")

        act_close = QAction("Close &Tab", self)
        act_close.setShortcut(QKeySequence("Ctrl+W"))
        act_close.triggered.connect(self.close_current_tab)
        m_tabs.addAction(act_close)

        a = QAction("Close &Other Tabs", self)
        a.triggered.connect(self._close_others_current)
        m_tabs.addAction(a)

        a = QAction("Close Tabs &to the Right", self)
        a.triggered.connect(self._close_right_current)
        m_tabs.addAction(a)

        a = QAction("Close &All Tabs", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+W"))
        a.triggered.connect(self._close_all_tabs)
        m_tabs.addAction(a)

        act_dupl = QAction("&Duplicate Tab", self)
        act_dupl.setShortcut(QKeySequence("Ctrl+Shift+D"))
        act_dupl.triggered.connect(self.duplicate_current_tab)
        m_tabs.addAction(act_dupl)

        a = QAction("&Rename Tab…", self)
        a.triggered.connect(self._rename_current_tab)
        m_tabs.addAction(a)

        a = QAction("&Reconnect Session", self)
        a.triggered.connect(self._reconnect_current)
        m_tabs.addAction(a)

        m_tabs.addSeparator()

        a = QAction("&Next Tab", self)
        a.setShortcut(QKeySequence("Ctrl+Tab"))
        a.triggered.connect(self.next_tab)
        m_tabs.addAction(a)

        a = QAction("Pre&vious Tab", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+Backtab"))
        a.triggered.connect(self.prev_tab)
        m_tabs.addAction(a)

        m_session = self.menuBar().addMenu("&Session")

        act = QAction(icon("plus"), "&New session…", self)
        act.setShortcut(QKeySequence("Ctrl+N"))
        act.triggered.connect(self.new_session)
        m_session.addAction(act)

        act_log = QAction("Start / Stop Session &Logging…", self)
        act_log.setShortcut(QKeySequence("Ctrl+Shift+L"))
        act_log.triggered.connect(self.toggle_session_logging)
        m_session.addAction(act_log)

        m_session.addSeparator()

        a = QAction(icon("folder"), "Browse &Files (SFTP)…", self)
        a.triggered.connect(self._sftp_current)
        m_session.addAction(a)

        m_help = self.menuBar().addMenu("&Help")
        a = QAction("&Keyboard shortcuts…", self)
        a.triggered.connect(self.open_shortcuts)
        m_help.addAction(a)
        a = QAction("&About", self)
        a.triggered.connect(self._about)
        m_help.addAction(a)

    def _build_toolbar(self) -> None:
        # Compact professional toolbar: icon+label actions, inline quick connect
        bar = QToolBar()
        bar.setObjectName("moxaToolbar")
        bar.setMovable(False)
        bar.setIconSize(QSize(16, 16))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toolbar = bar

        act_sidebar = bar.addAction(icon("panel"), "Sidebar")
        act_sidebar.setToolTip("Toggle the session sidebar (Ctrl+B)")
        act_sidebar.setCheckable(True)
        act_sidebar.toggled.connect(self._toggle_sidebar)
        self._act_sidebar_toolbar = act_sidebar

        a = bar.addAction(icon("plus"), "New")
        a.setToolTip("Create a new saved session (Ctrl+N)")
        a.triggered.connect(self.new_session)

        a = bar.addAction(icon("console"), "Terminal")
        a.setToolTip("Open a local terminal tab (Ctrl+Shift+T)")
        a.triggered.connect(self.open_local_terminal)

        a = bar.addAction(icon("search"), "Commands")
        a.setToolTip("Command Palette & Quick Switcher (Ctrl+P / Ctrl+K)")
        a.triggered.connect(self.open_command_palette)

        bar.addSeparator()

        # Quick connect — compact single-line group with a real button
        quick_wrap = QWidget()
        quick_wrap.setObjectName("quickConnect")
        ql = QHBoxLayout(quick_wrap)
        ql.setContentsMargins(1, 1, 1, 1)
        ql.setSpacing(0)

        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Quick connect — user@host[:port]")
        self.quick.setFixedWidth(230)
        self.quick.setObjectName("quickInput")
        self.quick.returnPressed.connect(self.quick_connect)
        ql.addWidget(self.quick, 1)

        qc_btn = QPushButton("Connect")
        qc_btn.setObjectName("primary")
        qc_btn.setToolTip("Connect now (Enter)")
        qc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qc_btn.clicked.connect(self.quick_connect)
        ql.addWidget(qc_btn)
        bar.addWidget(quick_wrap)

        bar.addSeparator()

        def add_tool(icon_name, text, tip, cb):
            act = bar.addAction(icon(icon_name), text)
            act.setToolTip(tip)
            act.triggered.connect(cb)
            return act

        add_tool("server", "Scan", "Network Tools & Port Scanner (Ctrl+Shift+N)", self.open_network_tools)
        add_tool("key", "Keys", "SSH Key Utility & Converter (Ctrl+Shift+U)", self.open_key_utility)

        bar.addSeparator()

        # Close all tabs button
        self._close_all_btn = bar.addAction(icon("close"), "Close All")
        self._close_all_btn.setToolTip("Close all open session tabs")
        self._close_all_btn.triggered.connect(self._close_all_tabs)
        self._close_all_btn.setVisible(False)

        add_tool("gear", "Settings", "Settings (Ctrl+,)", self.open_settings)

        self.addToolBar(bar)
        self._apply_ui_prefs()

    def _build_body(self) -> None:
        from .theme import palette as theme_palette

        pal = theme_palette()
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setHandleWidth(1)

        self.sidebar = SessionTree(self.ctx.store)
        self.main_splitter.addWidget(self.sidebar)

        # Center tabbed container
        tabs_wrap = QWidget()
        tabs_wrap.setObjectName("workArea")
        tl = QVBoxLayout(tabs_wrap)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)

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
        cl.setContentsMargins(4, 2, 8, 2)
        cl.setSpacing(4)

        # Session count indicator
        self._tab_count_label = QLabel("0")
        self._tab_count_label.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {palette()['fg_dim']}; "
            f"background: {palette()['bg3']}; border-radius: 8px; padding: 1px 6px;"
        )
        self._tab_count_label.setFixedHeight(18)
        self._tab_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tab_count_label.setToolTip("Number of open sessions")
        cl.addWidget(self._tab_count_label)

        plus = QPushButton()
        plus.setIcon(icon("plus"))
        plus.setObjectName("ghost")
        plus.setToolTip("New session (Ctrl+N)")
        plus.setFixedSize(26, 22)
        plus.clicked.connect(self.new_session)
        cl.addWidget(plus)

        terminal = QPushButton()
        terminal.setIcon(icon("console"))
        terminal.setObjectName("ghost")
        terminal.setToolTip("Local terminal (Ctrl+Shift+T)")
        terminal.setFixedSize(26, 22)
        terminal.clicked.connect(self.open_local_terminal)
        cl.addWidget(terminal)

        settings = QPushButton()
        settings.setIcon(icon("gear"))
        settings.setObjectName("ghost")
        settings.setToolTip("Settings (Ctrl+,)")
        settings.setFixedSize(26, 22)
        settings.clicked.connect(self.open_settings)
        cl.addWidget(settings)

        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)

        # Dashboard — compact welcome: quick connect, actions, recents
        self._empty = QWidget()
        el = QVBoxLayout(self._empty)
        el.setAlignment(Qt.AlignmentFlag.AlignTop)
        el.setSpacing(14)
        el.setContentsMargins(32, 28, 32, 24)

        # Compact header: small logo mark + name + version
        header_row = QHBoxLayout()
        header_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icon("logo").pixmap(20, 20))
        header_row.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 700; letter-spacing: -0.2px; color: {pal['fg']};"
        )
        self._dash_header_label = title  # density-dependent font size
        header_row.addWidget(title)
        version = QLabel(f"v{__version__}  ·  SSH · SFTP · RDP")
        version.setStyleSheet(f"font-size: 11.5px; color: {pal['fg_muted']};")
        header_row.addWidget(version)
        header_row.addStretch(1)
        el.addLayout(header_row)

        # Quick connect — prominent, one line, explicit Connect button
        qc_card = QWidget()
        qc_card.setObjectName("card")
        qc_lay = QHBoxLayout(qc_card)
        qc_lay.setContentsMargins(12, 10, 12, 10)
        qc_lay.setSpacing(8)
        qc_title = QLabel("Quick Connect")
        qc_title.setStyleSheet(f"font-size: 12px; color: {pal['fg_dim']}; font-weight: 700;")
        qc_lay.addWidget(qc_title)
        self._dash_quick = QLineEdit()
        self._dash_quick.setPlaceholderText("user@host[:port]  ·  port 3389 = RDP")
        self._dash_quick.setObjectName("search")
        self._dash_quick.setFixedHeight(30)
        self._dash_quick.returnPressed.connect(self._dash_quick_connect)
        qc_lay.addWidget(self._dash_quick, 1)
        qc_btn = QPushButton("Connect")
        qc_btn.setObjectName("primary")
        qc_btn.setFixedHeight(30)
        qc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qc_btn.clicked.connect(self._dash_quick_connect)
        qc_lay.addWidget(qc_btn)
        qc_card.setFixedWidth(560)
        el.addWidget(qc_card, 0, Qt.AlignmentFlag.AlignHCenter)

        # Action cards — compact, icon + label + description
        actions_row = QHBoxLayout()
        actions_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        actions_row.setSpacing(10)

        def _action_card(icon_name: str, label: str, tooltip: str, callback) -> QWidget:
            card = QFrame()
            card.setObjectName("card_hover")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip(tooltip)
            card.setFixedHeight(64)
            lay = QHBoxLayout(card)
            lay.setContentsMargins(14, 10, 14, 10)
            lay.setSpacing(10)
            ic = QLabel()
            ic.setPixmap(icon(icon_name).pixmap(QSize(20, 20)))
            ic.setFixedSize(20, 20)
            lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"font-size: 12.5px; font-weight: 600; color: {pal['fg']};")
            lay.addWidget(lbl, 1)
            card.mousePressEvent = lambda _, c=callback: c()
            return card

        actions_row.addWidget(_action_card("plus", "New Session", "Create a new connection (Ctrl+N)", self.new_session))
        actions_row.addWidget(_action_card("console", "Local Terminal", "Open a local terminal (Ctrl+Shift+T)", self.open_local_terminal))
        actions_row.addWidget(_action_card("search", "Command Palette", "Search commands & sessions (Ctrl+K)", self.open_command_palette))
        actions_row.addWidget(_action_card("gear", "Settings", "Configure KB-Remote (Ctrl+,)", self.open_settings))
        el.addLayout(actions_row)

        # Recent connections — compact rows (pinned first, then name)
        sessions = sorted(
            self.ctx.store.sessions(),
            key=lambda s: (not s.options.get("pinned", False), s.name),
        )[:6]
        if sessions:
            recent_card = QWidget()
            recent_card.setObjectName("card")
            recent_card.setFixedWidth(560)
            rc_lay = QVBoxLayout(recent_card)
            rc_lay.setContentsMargins(12, 10, 12, 10)
            rc_lay.setSpacing(4)
            rc_header = QLabel("Recent Connections")
            rc_header.setObjectName("h2")
            rc_lay.addWidget(rc_header)

            for sess in sessions[:5]:
                item = QFrame()
                item.setCursor(Qt.CursorShape.PointingHandCursor)
                item.setObjectName("card_hover")
                item.mousePressEvent = lambda _, s=sess: self.connect_session(s.id)
                il = QHBoxLayout(item)
                il.setContentsMargins(8, 5, 8, 5)
                il.setSpacing(8)
                proto_icon = icon("windows") if sess.protocol == "rdp" else icon("terminal") if sess.protocol == "ssh" else icon("console")
                pi = QLabel()
                pi.setPixmap(proto_icon.pixmap(QSize(16, 16)))
                pi.setFixedSize(16, 16)
                il.addWidget(pi)
                if sess.options.get("pinned", False):
                    star = QLabel()
                    star.setPixmap(icon("star", pal["warn"]).pixmap(QSize(13, 13)))
                    star.setFixedSize(13, 13)
                    star.setToolTip("Pinned session")
                    il.addWidget(star)
                name_lbl = QLabel(sess.display_name())
                name_lbl.setStyleSheet(f"font-size: 12.5px; font-weight: 600; color: {pal['fg']};")
                il.addWidget(name_lbl)
                il.addStretch(1)
                target = QLabel(sess.target())
                target.setStyleSheet(f"font-size: 11.5px; color: {pal['fg_muted']};")
                il.addWidget(target)
                proto = QLabel(sess.protocol.upper())
                proto.setStyleSheet(
                    f"font-size: 10.5px; font-weight: 700; color: {pal['fg_dim']}; "
                    f"background: {pal['bg3']}; border-radius: 4px; padding: 1px 6px;"
                )
                il.addWidget(proto)
                rc_lay.addWidget(item)
            el.addWidget(recent_card, 0, Qt.AlignmentFlag.AlignHCenter)

        # Keyboard shortcuts hint
        shortcuts = QLabel("Ctrl+N new · Ctrl+Shift+T terminal · Ctrl+K commands · Ctrl+, settings")
        shortcuts.setObjectName("caption")
        shortcuts.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        shortcuts.setStyleSheet(f"font-size: 11px; color: {pal['fg_muted']};")
        el.addWidget(shortcuts)

        self._tabs_container = QWidget()
        tcl = QVBoxLayout(self._tabs_container)
        tcl.setContentsMargins(0, 0, 0, 0)
        tcl.addWidget(self.tabs, 1)

        self._center_stack = QWidget()
        csl = QVBoxLayout(self._center_stack)
        csl.setContentsMargins(0, 0, 0, 0)
        csl.setSpacing(0)
        csl.addWidget(self._empty, 1)
        csl.addWidget(self._tabs_container, 1)
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

        # Restore sidebar state (persistence) then sync the checkable actions.
        # "checked" on the toggle actions means the sidebar is *visible*.
        self._last_sidebar_width = 260
        saved_w = self.ctx.settings.geometry.get("sidebar_width")
        if isinstance(saved_w, int) and 150 <= saved_w <= 480:
            self._last_sidebar_width = saved_w
        self._sidebar_collapsed = bool(self.ctx.settings.geometry.get("sidebar_collapsed", False))
        self.main_splitter.setSizes(
            [0 if self._sidebar_collapsed else self._last_sidebar_width, 1200]
        )
        self._sync_sidebar_actions()

    def _sidebar_width(self) -> int:
        if not hasattr(self, "main_splitter"):
            return 240
        return self.main_splitter.sizes()[0]

    def _set_sidebar_width(self, width: int) -> None:
        sizes = self.main_splitter.sizes()
        total = sum(sizes)
        self.main_splitter.setSizes([width, max(320, total - width)])
        self._sidebar_collapsed = width <= 0

    def _toggle_sidebar(self, checked: bool = None) -> None:
        """checked=True shows the sidebar, checked=False collapses it.

        Called with the action's new state; if None (plain trigger), invert.
        """
        if not hasattr(self, "main_splitter"):
            return
        if checked is None:
            checked = self._sidebar_collapsed  # invert the current state
        self._sync_sidebar_actions(checked)
        target = max(220, self._last_sidebar_width) if checked else 0
        self._animate_splitter(self._sidebar_width(), target)

    def _animate_splitter(self, start: int, end: int) -> None:
        from PySide6.QtCore import QVariantAnimation

        if not theme.MOTIONS_ENABLED or start == end:
            self._set_sidebar_width(end)
            return
        anim = QVariantAnimation(self)
        anim.setDuration(140)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: self._set_sidebar_width(int(v)))
        self._sidebar_anim = anim  # keep alive across the event loop
        anim.finished.connect(anim.deleteLater)
        anim.start()

    def _sync_sidebar_actions(self, visible: bool = None) -> None:
        if visible is None:
            visible = not self._sidebar_collapsed
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
                self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
                self._toolbar.setIconSize(QSize(16, 16))
            else:
                self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                self._toolbar.setIconSize(QSize(18, 18))
        if hasattr(self, "_dash_header_label"):
            # Compact density trims the dashboard header; comfortable stays roomy.
            self._dash_header_label.setStyleSheet(
                f"font-size: {15 if s.density == 'compact' else 17}px; font-weight: 700; "
                f"letter-spacing: -0.2px; color: {palette()['fg']};"
            )

    def _bind_shortcuts(self) -> None:
        # Tab navigation shortcuts (Ctrl+Tab / Ctrl+Shift+Backtab live on the
        # Tabs-menu actions — duplicating them here would fire twice).
        QShortcut(QKeySequence("Ctrl+K"), self, self.open_command_palette)
        QShortcut(QKeySequence("Ctrl+Shift+K"), self, self._focus_quick_connect)
        # Note: Ctrl+W lives on the Tabs-menu action — a second QShortcut
        # here would fire twice and close two tabs per keypress.

        for i in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, lambda idx=i-1: self.switch_to_tab(idx))

    def _focus_quick_connect(self) -> None:
        """Ctrl+Shift+K — jump to the visible quick-connect input."""
        target = self._dash_quick if self._empty.isVisible() else self.quick
        target.setFocus()
        target.selectAll()

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
        menu.addAction("Close Tab\tCtrl+W", lambda: self.close_tab(index))
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
    # Session lifecycle
    # ------------------------------------------------------------------
    def connect_session(self, session_id: str) -> None:
        defn = self.ctx.store.get(session_id)
        if defn is None:
            return
        self.open_session(defn)

    def open_session(self, defn: Session) -> SessionTab | None:
        try:
            plugin = registry().require(defn.protocol)
        except KeyError as exc:
            QMessageBox.warning(self, "Unknown protocol", str(exc))
            return None
        controller = plugin.create_session(defn, self.ctx)
        controller.setParent(self)
        tab = SessionTab(controller, self)
        self.tabs.addTab(tab, defn.display_name())
        self.tabs.setCurrentWidget(tab)
        self.tabs.setTabIcon(self.tabs.indexOf(tab), icon(plugin.icon_name))

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
            parts.append("·  " + "  ".join(feats))
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

    def _delete_session(self, session_id: str) -> None:
        defn = self.ctx.store.get(session_id)
        if defn is None:
            return
        btn = QMessageBox.question(
            self,
            "Delete session",
            f"Delete “{defn.display_name()}”?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if btn == QMessageBox.StandardButton.Yes:
            self.ctx.store.delete(session_id)
            self.sidebar.reload()

    def quick_connect(self) -> None:
        self._quick_connect_from(self.quick)

    def _dash_quick_connect(self) -> None:
        self._quick_connect_from(self._dash_quick)

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
        QMessageBox.information(
            self,
            "Quick connect",
            "Could not parse that. Use user@host[:port] (port 3389 ⇒ RDP).",
        )

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

    def open_tunnels_for_controller(self, controller) -> None:
        from .tunnels_dialog import TunnelsDialog

        TunnelsDialog(self.ctx, controller, self).show()

    def open_sftp_for_controller(self, controller) -> None:
        from .sftp_dialog import SftpDialog

        SftpDialog(self.ctx, controller, self).show()

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
        self.apply_theme_id("dark" if dark else "light")

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
            "sidebar_width": self._last_sidebar_width if not self._sidebar_collapsed else None,
        }
        settings.save(paths.settings_file())
        super().closeEvent(event)
