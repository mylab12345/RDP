"""Main window: tabbed sessions, sidebar, toolbar, quick connect, tools & command palette."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
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
from .snippets_panel import SnippetsPanel
from .theme import icon
from .widgets import STATE_COLORS, StateChip, toast

log = get_logger("ui.main")

_MAX_IMPORT_BYTES = 32 * 1024 * 1024

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
    """One tab: hosts a SessionController + a modern status header."""

    def __init__(self, controller: SessionController, main: MainWindow) -> None:
        super().__init__()
        self.controller = controller
        self.main = main
        self._custom_title: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setObjectName("header")
        header.setMinimumHeight(44)
        h = QHBoxLayout(header)
        h.setContentsMargins(12, 6, 12, 6)
        h.setSpacing(8)

        self.chip = StateChip("connecting", "info")
        h.addWidget(self.chip)

        self.rec_chip = StateChip("● REC", "bad")
        self.rec_chip.setVisible(False)
        self.rec_chip.setToolTip("Logging active session output to file")
        h.addWidget(self.rec_chip)

        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.info.setStyleSheet("font-size: 12.5px;")
        h.addWidget(self.info, 1)

        self.btn_reconnect = QPushButton("↻ Reconnect")
        self.btn_reconnect.setObjectName("primary")
        self.btn_reconnect.clicked.connect(controller.request_reconnect)
        self.btn_reconnect.setVisible(False)
        self.btn_reconnect.setMinimumHeight(32)
        h.addWidget(self.btn_reconnect)

        caps = controller.capabilities()

        def make_action_btn(text, icon_name, tip, cb):
            b = QPushButton(text)
            if icon_name:
                b.setIcon(icon(icon_name))
            b.setObjectName("subtle")
            b.setToolTip(tip)
            b.clicked.connect(cb)
            b.setMinimumHeight(32)
            return b

        if caps.sftp:
            b = make_action_btn("Files", "folder", "Browse remote files (SFTP)", controller.open_sftp)
            h.addWidget(b)
        if caps.tunnels:
            b = make_action_btn("Tunnels", "plug", "Manage port forwards", controller.open_tunnels)
            h.addWidget(b)
        if caps.monitor:
            b = make_action_btn("Monitor", "server", "Live CPU, memory, disk and network", controller.open_monitor)
            h.addWidget(b)

        layout.addWidget(header)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        layout.addWidget(line)

        self._content = controller.widget()
        layout.addWidget(self._content, 1)

        widget_changed = getattr(controller, "widgetChanged", None)
        if widget_changed is not None:
            widget_changed.connect(self._swap_content)

        controller.stateChanged.connect(self._on_state)
        controller.statusInfo.connect(self._on_status)
        controller.finished.connect(self._on_finished)
        controller.reconnectScheduled.connect(self._on_reconnect_scheduled)

        # Hook terminal input for broadcast mode
        term = getattr(controller, "term", None)
        if term is not None and hasattr(term, "dataWritten"):
            term.dataWritten.connect(lambda data: self.main._on_terminal_user_input(self, data))

    def _swap_content(self) -> None:
        old = self._content
        if old is None:
            return
        layout = self.layout()
        layout.removeWidget(old)
        old.hide()
        self._content = self.controller.widget()
        layout.addWidget(self._content, 1)
        self._content.show()

    def _on_state(self, state: str) -> None:
        self.chip.setText(state)
        self.chip.set_color(STATE_COLORS.get(state, "fg_dim"))
        self.btn_reconnect.setVisible(state in (SessionState.CLOSED, SessionState.FAILED))

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
        self._broadcast_mode = False
        self._in_broadcast_dispatch = False

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._bind_shortcuts()

        status = QStatusBar()
        status.setSizeGripEnabled(False)
        self.setStatusBar(status)

        self.vault_label = QLabel("")
        self.vault_label.setObjectName("caption")
        status.addWidget(self.vault_label)

        self.broadcast_label = QLabel("")
        self.broadcast_label.setObjectName("caption")
        status.addWidget(self.broadcast_label)

        self.status_label = QLabel("")
        self.status_label.setObjectName("caption")
        status.addPermanentWidget(self.status_label)

        self._refresh_vault_label()

        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(30_000)
        self._lock_timer.timeout.connect(self._autolock)
        self._lock_timer.start()

        geo = ctx.settings.geometry
        if isinstance(geo, dict) and geo.get("size"):
            self.resize(QSize(int(geo["size"][0]), int(geo["size"][1])))
            if geo.get("pos"):
                self.move(QPoint(int(geo["pos"][0]), int(geo["pos"][1])))
            if geo.get("maximized"):
                self.showMaximized()

    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&Session")

        act = QAction(icon("plus"), "&New session…", self)
        act.setShortcut(QKeySequence("Ctrl+N"))
        act.triggered.connect(self.new_session)
        m_file.addAction(act)

        act = QAction(icon("console"), "New local &terminal", self)
        act.setShortcut(QKeySequence("Ctrl+Shift+T"))
        act.setStatusTip("Open a native local shell in a new tab")
        act.triggered.connect(self.open_local_terminal)
        m_file.addAction(act)

        act = QAction(icon("search"), "Command &Palette / Switcher…", self)
        act.setShortcut(QKeySequence("Ctrl+P"))
        act.setStatusTip("Search sessions, tabs, tools and actions")
        act.triggered.connect(self.open_command_palette)
        m_file.addAction(act)

        m_file.addSeparator()

        act_log = QAction("Start / Stop Session &Logging…", self)
        act_log.setShortcut(QKeySequence("Ctrl+Shift+L"))
        act_log.triggered.connect(self.toggle_session_logging)
        m_file.addAction(act_log)

        act_dupl = QAction("Duplicate Active Tab", self)
        act_dupl.setShortcut(QKeySequence("Ctrl+Shift+D"))
        act_dupl.triggered.connect(self.duplicate_current_tab)
        m_file.addAction(act_dupl)

        act_close = QAction("Close Active Tab", self)
        act_close.setShortcut(QKeySequence("Ctrl+W"))
        act_close.triggered.connect(self.close_current_tab)
        m_file.addAction(act_close)

        m_file.addSeparator()

        imp = m_file.addMenu("&Import")
        a = QAction("From ~/.ssh/config", self)
        a.triggered.connect(self._import_ssh_config)
        imp.addAction(a)
        a = QAction("From file (JSON)…", self)
        a.triggered.connect(self._import_json)
        imp.addAction(a)

        exp = QAction("&Export to file…", self)
        exp.triggered.connect(self._export_json)
        m_file.addAction(exp)
        m_file.addSeparator()

        q = QAction("E&xit", self)
        q.setShortcut(QKeySequence("Ctrl+Q"))
        q.triggered.connect(self.close)
        m_file.addAction(q)

        m_tools = self.menuBar().addMenu("&Tools")
        a = QAction(icon("server"), "Network Tools & Port &Scanner…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+N"))
        a.triggered.connect(self.open_network_tools)
        m_tools.addAction(a)

        a = QAction(icon("transfer"), "Multi-Host &Parallel Runner…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+X"))
        a.triggered.connect(self.open_cluster_runner)
        m_tools.addAction(a)

        a = QAction(icon("key"), "SSH &Key Utility & Converter…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+U"))
        a.triggered.connect(self.open_key_utility)
        m_tools.addAction(a)

        m_tools.addSeparator()

        a = QAction(icon("shield"), "Credential &vault…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+K"))
        a.triggered.connect(self.open_vault)
        m_tools.addAction(a)

        a = QAction(icon("plug"), "&Port forwarding…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+P"))
        a.triggered.connect(self.open_tunnels_dialog)
        m_tools.addAction(a)

        a = QAction(icon("server"), "Remote &monitor…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+M"))
        a.triggered.connect(self.open_monitor_dialog)
        m_tools.addAction(a)

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

        m_view = self.menuBar().addMenu("&View")

        self._act_broadcast = QAction("📡 &Broadcast Input Mode", self)
        self._act_broadcast.setCheckable(True)
        self._act_broadcast.setShortcut(QKeySequence("Ctrl+Shift+B"))
        self._act_broadcast.toggled.connect(self.set_broadcast_mode)
        m_view.addAction(self._act_broadcast)

        self._act_snippets = QAction("📝 Command &Snippets Panel", self)
        self._act_snippets.setCheckable(True)
        self._act_snippets.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._act_snippets.toggled.connect(self.set_snippets_visible)
        m_view.addAction(self._act_snippets)

        m_view.addSeparator()

        self._theme_action = QAction("&Dark theme", self)
        self._theme_action.setCheckable(True)
        self._theme_action.setChecked(self.ctx.settings.theme == "dark")
        self._theme_action.toggled.connect(self._toggle_theme)
        m_view.addAction(self._theme_action)

        m_help = self.menuBar().addMenu("&Help")
        a = QAction("&About", self)
        a.triggered.connect(self._about)
        m_help.addAction(a)

    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        bar.setIconSize(QSize(18, 18))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        a = bar.addAction(icon("plus"), "New Session")
        a.setToolTip("Create a new saved session (Ctrl+N)")
        a.triggered.connect(self.new_session)

        a = bar.addAction(icon("console"), "Terminal")
        a.setToolTip("Open a local terminal tab (Ctrl+Shift+T)")
        a.triggered.connect(self.open_local_terminal)

        a = bar.addAction(icon("search"), "Palette")
        a.setToolTip("Command Palette & Quick Switcher (Ctrl+P / Ctrl+K)")
        a.triggered.connect(self.open_command_palette)

        bar.addSeparator()

        # Quick connect input
        quick_wrap = QWidget()
        ql = QHBoxLayout(quick_wrap)
        ql.setContentsMargins(8, 2, 8, 2)
        ql.setSpacing(8)

        lbl = QLabel("⌕")
        lbl.setObjectName("muted")
        lbl.setStyleSheet("font-size: 14px;")
        ql.addWidget(lbl)

        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Quick connect: user@host[:port]  ⏎")
        self.quick.setFixedWidth(260)
        self.quick.setObjectName("search")
        self.quick.returnPressed.connect(self.quick_connect)
        ql.addWidget(self.quick)
        bar.addWidget(quick_wrap)

        bar.addSeparator()

        # Broadcast Mode Toggle Button
        self.btn_broadcast = QPushButton("📡 Broadcast: OFF")
        self.btn_broadcast.setObjectName("ghost")
        self.btn_broadcast.setCheckable(True)
        self.btn_broadcast.setToolTip("Broadcast Mode: send input to all open terminal tabs (Ctrl+Shift+B)")
        self.btn_broadcast.toggled.connect(self.set_broadcast_mode)
        bar.addWidget(self.btn_broadcast)

        # Snippets Panel Toggle Button
        self.btn_snippets = QPushButton("📝 Snippets")
        self.btn_snippets.setObjectName("ghost")
        self.btn_snippets.setCheckable(True)
        self.btn_snippets.setToolTip("Toggle Command Snippets & Macros Panel (Ctrl+Shift+S)")
        self.btn_snippets.toggled.connect(self.set_snippets_visible)
        bar.addWidget(self.btn_snippets)

        bar.addSeparator()

        def add_tool(icon_name, text, tip, cb):
            act = bar.addAction(icon(icon_name), text)
            act.setToolTip(tip)
            act.triggered.connect(cb)
            return act

        add_tool("server", "Scanner", "Network Tools & Port Scanner (Ctrl+Shift+N)", self.open_network_tools)
        add_tool("transfer", "Cluster", "Multi-Host Parallel Runner (Ctrl+Shift+X)", self.open_cluster_runner)
        add_tool("key", "Keys", "SSH Key Utility & Converter (Ctrl+Shift+U)", self.open_key_utility)
        add_tool("shield", "Vault", "Credential vault (Ctrl+Shift+K)", self.open_vault)
        add_tool("plug", "Tunnels", "Port forwarding (Ctrl+Shift+P)", self.open_tunnels_dialog)
        add_tool("gear", "Settings", "Settings (Ctrl+,)", self.open_settings)

        self.addToolBar(bar)

    def _build_body(self) -> None:
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.main_splitter.setHandleWidth(1)

        self.sidebar = SessionTree(self.ctx.store)
        self.main_splitter.addWidget(self.sidebar)

        # Center tabbed container
        tabs_wrap = QWidget()
        tabs_wrap.setObjectName("card")
        tl = QVBoxLayout(tabs_wrap)
        tl.setContentsMargins(6, 6, 6, 6)
        tl.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideRight)

        # Tab bar context menu
        self.tabs.tabBar().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self._tab_context_menu)

        # Corner buttons (New Tab + Command Palette)
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(4, 2, 8, 2)
        cl.setSpacing(6)

        btn_palette = QPushButton("⌕")
        btn_palette.setObjectName("ghost")
        btn_palette.setToolTip("Command Palette (Ctrl+P)")
        btn_palette.clicked.connect(self.open_command_palette)
        cl.addWidget(btn_palette)

        plus = QPushButton("＋ New Tab")
        plus.setObjectName("ghost")
        plus.setToolTip("New session (Ctrl+N)")
        plus.clicked.connect(self.new_session)
        cl.addWidget(plus)
        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)

        # Empty state widget
        self._empty = QWidget()
        el = QVBoxLayout(self._empty)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.setSpacing(16)
        el.setContentsMargins(40, 40, 40, 40)

        logo = QLabel("◐")
        logo.setStyleSheet("font-size: 48px; color: #5c677e;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(logo)

        title = QLabel(f"Welcome to {APP_NAME}")
        title.setObjectName("h1")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(title)

        subtitle = QLabel("Open a saved session from the sidebar, create a new one, or use quick connect above.\n"
                          "Press Ctrl+P for Command Palette, or Ctrl+Shift+T for local terminal.")
        subtitle.setObjectName("muted")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        el.addWidget(subtitle)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_row.setSpacing(10)
        b1 = QPushButton("＋ New Session")
        b1.setObjectName("primary")
        b1.clicked.connect(self.new_session)
        b2 = QPushButton("▢ Terminal")
        b2.setObjectName("subtle")
        b2.clicked.connect(self.open_local_terminal)
        b3 = QPushButton("⌕ Command Palette")
        b3.setObjectName("subtle")
        b3.clicked.connect(self.open_command_palette)
        btn_row.addWidget(b1)
        btn_row.addWidget(b2)
        btn_row.addWidget(b3)
        el.addLayout(btn_row)

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

        # Right side: Snippets panel (collapsible)
        self.snippets_panel = SnippetsPanel(self)
        self.snippets_panel.setVisible(False)
        self.main_splitter.addWidget(self.snippets_panel)

        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([280, 1100, 0])
        self.setCentralWidget(self.main_splitter)

        # Sidebar events
        self.sidebar.connectRequested.connect(self.connect_session)
        self.sidebar.editRequested.connect(self.edit_session)
        self.sidebar.duplicateRequested.connect(lambda sid: (self.ctx.store.duplicate(sid), self.sidebar.reload()))
        self.sidebar.deleteRequested.connect(self._delete_session)
        self.sidebar.sftpRequested.connect(self._connect_and_sftp)
        self.sidebar.newSessionRequested.connect(self.new_session)
        self.sidebar.newFolderRequested.connect(self.sidebar.prompt_new_folder)

    def _bind_shortcuts(self) -> None:
        # Tab navigation shortcuts
        QShortcut(QKeySequence("Ctrl+Tab"), self, self.next_tab)
        QShortcut(QKeySequence("Ctrl+Shift+Backtab"), self, self.prev_tab)
        QShortcut(QKeySequence("Ctrl+K"), self, self.open_command_palette)
        # Note: Ctrl+W lives on the Session menu action — a second QShortcut
        # here would fire twice and close two tabs per keypress.

        for i in range(1, 10):
            QShortcut(QKeySequence(f"Ctrl+{i}"), self, lambda idx=i-1: self.switch_to_tab(idx))

    def _update_empty_state(self) -> None:
        has_tabs = self.tabs.count() > 0
        self._empty.setVisible(not has_tabs)
        self._tabs_container.setVisible(has_tabs)

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
        if caps.sftp or caps.tunnels or caps.monitor:
            menu.addSeparator()
            if caps.sftp:
                menu.addAction("Browse Files (SFTP)", widget.controller.open_sftp)
            if caps.tunnels:
                menu.addAction("Port Forwarding (Tunnels)", widget.controller.open_tunnels)
            if caps.monitor:
                menu.addAction("Remote Monitor", widget.controller.open_monitor)

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
    # Broadcast Input Mode
    # ------------------------------------------------------------------
    def set_broadcast_mode(self, enabled: bool) -> None:
        self._broadcast_mode = enabled
        self._act_broadcast.setChecked(enabled)
        self.btn_broadcast.setChecked(enabled)
        self.btn_broadcast.setText("📡 Broadcast: ON" if enabled else "📡 Broadcast: OFF")
        self.btn_broadcast.setObjectName("primary" if enabled else "ghost")
        theme.apply_theme(QApplication.instance(), self.ctx.settings.theme)
        if enabled:
            self.broadcast_label.setText("  📡 BROADCAST INPUT: ACTIVE")
            toast(self, "Broadcast Mode ON: Input is sent to ALL open terminal tabs", "warn")
        else:
            self.broadcast_label.setText("")
            toast(self, "Broadcast Mode OFF", "info")

    def toggle_broadcast_mode(self) -> None:
        self.set_broadcast_mode(not self._broadcast_mode)

    def _on_terminal_user_input(self, source_tab: SessionTab, data: bytes) -> None:
        if not self._broadcast_mode or self._in_broadcast_dispatch:
            return
        self._in_broadcast_dispatch = True
        try:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if isinstance(w, SessionTab) and w is not source_tab:
                    c = w.controller
                    # Only shell-capable sessions accept raw input (SSH and
                    # local terminals implement write(); RDP windows don't).
                    if c.capabilities().shell:
                        try:
                            c.write(data)
                        except Exception:  # noqa: BLE001 - never break typing
                            log.exception("broadcast write failed")
        finally:
            self._in_broadcast_dispatch = False

    # ------------------------------------------------------------------
    # Snippets & Command Palette
    # ------------------------------------------------------------------
    def set_snippets_visible(self, visible: bool) -> None:
        self.snippets_panel.setVisible(visible)
        self._act_snippets.setChecked(visible)
        self.btn_snippets.setChecked(visible)
        if visible:
            self.main_splitter.setSizes([260, 840, 280])

    def toggle_snippets_panel(self) -> None:
        self.set_snippets_visible(not self.snippets_panel.isVisible())

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
        controller.start()
        self._update_empty_state()
        return tab

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
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
            widget.controller.deleteLater()
        if widget is not None:
            widget.deleteLater()
        self._update_empty_state()

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
        text = self.quick.text().strip()
        if not text:
            return
        for plugin in registry().editable():
            defn = plugin.quick_connect_target(text)
            if defn is not None:
                self.ctx.store.upsert(defn)
                self.sidebar.reload()
                self.open_session(defn)
                self.quick.clear()
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
        self._refresh_vault_label()

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

    def open_monitor_dialog(self) -> None:
        controller = self.current_controller()
        if controller is None or not controller.capabilities().monitor:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                if isinstance(w, SessionTab) and w.controller.capabilities().monitor:
                    controller = w.controller
                    break
        if controller is None or not controller.capabilities().monitor:
            toast(self, "Open an SSH session first — monitoring runs over SSH.", "warn")
            return
        self.open_monitor_for_controller(controller)

    def open_monitor_for_controller(self, controller) -> None:
        from .monitor_dialog import MonitorDialog

        MonitorDialog(self.ctx, controller, self).show()

    def open_sftp_for_controller(self, controller) -> None:
        from .sftp_dialog import SftpDialog

        SftpDialog(self.ctx, controller, self).show()

    def open_rdp_server_manager(self) -> None:
        from .rdp_server_dialog import RdpServerDialog

        RdpServerDialog(self).exec()

    def open_settings(self) -> None:
        from .settings_dialog import SettingsDialog

        dlg = SettingsDialog(self.ctx, self)
        if dlg.exec():
            app = QApplication.instance()
            theme.apply_theme(app, self.ctx.settings.theme)
            self._theme_action.setChecked(self.ctx.settings.theme == "dark")

    def _toggle_theme(self, dark: bool) -> None:
        self.ctx.settings.theme = "dark" if dark else "light"
        self.ctx.settings.save(paths.settings_file())
        theme.apply_theme(QApplication.instance(), self.ctx.settings.theme)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> {__version__}<br><br>"
            "Cross-platform remote-access workbench.<br>"
            "SSH/SFTP to Linux hosts, RDP to Windows hosts.<br><br>"
            "Python · Qt (PySide6) · paramiko · pyte<br><br>"
            "<span style='color: #8a94ac;'>Modern UI • Fast terminal • Secure vault</span>",
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

    def _refresh_vault_label(self) -> None:
        try:
            unlocked = self.ctx.vault.unlocked
            exists = self.ctx.vault.exists
        except Exception:
            unlocked, exists = False, False
        if unlocked:
            self.vault_label.setText(" 🔓 vault unlocked")
        elif exists:
            self.vault_label.setText(" 🔒 vault locked")
        else:
            self.vault_label.setText(" ○ no vault — passwords saved per session")

    def _autolock(self) -> None:
        changed = self.ctx.vault.lock_if_due(self.ctx.settings.vault_autolock_minutes)
        if changed:
            self._refresh_vault_label()
            toast(self, "Vault auto-locked after inactivity", "warn")

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
        }
        settings.save(paths.settings_file())
        super().closeEvent(event)
