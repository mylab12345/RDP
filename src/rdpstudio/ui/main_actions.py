"""Menu-bar + toolbar builders, moved verbatim from MainWindow (ARCH-02).

Mixin methods — ``self`` is the MainWindow at runtime.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from . import theme
from .theme import icon


class MainActionsMixin:
    """Builds the menu bar and the MobaXterm-style toolbar."""

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

        # Docking (mouse-first): grab a grip and shove it at an edge, or use
        # these entries. The label flips as the panel moves (see
        # _sync_sidebar_actions).
        self._act_flip_sidebar = QAction(icon("panel"), "Move Sessions Panel to the &Right", self)
        self._act_flip_sidebar.setShortcut(QKeySequence("Ctrl+Shift+B"))
        self._act_flip_sidebar.setStatusTip(
            "Dock the Sessions panel to the other edge of the window"
        )
        self._act_flip_sidebar.triggered.connect(self.flip_sidebar_side)
        m_view.addAction(self._act_flip_sidebar)

        m_tabs_pos = m_view.addMenu(icon("panel"), "Session &Tabs Position")
        m_tabs_pos.setStatusTip("Where the open-session tab strip lives")
        self._tabs_pos_group = QActionGroup(self)
        self._tabs_pos_group.setExclusive(True)
        self._tabs_pos_actions: dict[str, QAction] = {}
        for key, label in (
            ("top", "&Top — horizontal strip"),
            ("left", "&Left — vertical rail"),
            ("right", "R&ight — vertical rail"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.triggered.connect(lambda checked, k=key: checked and self.set_tabs_position(k))
            self._tabs_pos_group.addAction(act)
            m_tabs_pos.addAction(act)
            self._tabs_pos_actions[key] = act
        act = QAction("&Cycle tab strip position", self)
        act.setShortcut(QKeySequence("Ctrl+Shift+J"))
        act.triggered.connect(self.cycle_tabs_position)
        m_tabs_pos.addSeparator()
        m_tabs_pos.addAction(act)

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

        a = QAction(icon("transfer"), "&File sharing server…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+S"))
        a.setStatusTip("Share local folders with remote machines over SFTP")
        a.triggered.connect(self.open_share_server)
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
        act_close.triggered.connect(self.close_current_tab)
        m_tabs.addAction(act_close)

        a = QAction("Close &Other Tabs", self)
        a.triggered.connect(self._close_others_current)
        m_tabs.addAction(a)

        a = QAction("Close Tabs &to the Right", self)
        a.triggered.connect(self._close_right_current)
        m_tabs.addAction(a)

        a = QAction("Close &All Tabs", self)
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
        """MobaXterm-style toolbar: large coloured icons with labels below.

        Same actions and wiring as before — only the look changed (icon size,
        text-under-icon layout, per-action colour tints, grouping).
        """
        bar = QToolBar()
        bar.setObjectName("moxaToolbar")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(24, 24))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._toolbar = bar
        self._themed_actions: list[tuple[QAction, str]] = []

        def themed_action(icon_name: str, text: str) -> QAction:
            act = bar.addAction(theme.toolbar_icon(icon_name), text)
            self._themed_actions.append((act, icon_name))
            return act

        a = themed_action("plus", "Session")
        a.setToolTip("Create a new saved session (Ctrl+N)")
        a.triggered.connect(self.new_session)

        a = themed_action("console", "Terminal")
        a.setToolTip("Open a local terminal tab (Ctrl+Shift+T)")
        a.triggered.connect(self.open_local_terminal)

        act_sidebar = themed_action("panel", "Sessions")
        act_sidebar.setToolTip("Show / hide the Sessions side panel (Ctrl+B)")
        act_sidebar.setCheckable(True)
        act_sidebar.toggled.connect(self._toggle_sidebar)
        self._act_sidebar_toolbar = act_sidebar

        bar.addSeparator()

        def add_tool(icon_name, text, tip, cb):
            act = themed_action(icon_name, text)
            act.setToolTip(tip)
            act.triggered.connect(cb)
            return act

        add_tool("search", "Commands", "Command Palette & Quick Switcher (Ctrl+P / Ctrl+K)", self.open_command_palette)
        add_tool("server", "Servers", "Network Tools & Port Scanner (Ctrl+Shift+N)", self.open_network_tools)
        add_tool("key", "Keys", "SSH Key Utility & Converter (Ctrl+Shift+U)", self.open_key_utility)
        add_tool("transfer", "Tunneling", "SSH tunnels / port forwarding for the active session", self.open_tunnels_dialog)
        add_tool("folder", "Sharing", "Serve local folders to remote machines (Ctrl+Shift+S)", self.open_share_server)

        bar.addSeparator()

        # Quick connect — MobaXterm's "Quick connect" strip: white input +
        # blue Connect button, sitting in the toolbar after the tool groups.
        quick_wrap = QWidget()
        quick_wrap.setObjectName("quickConnect")
        ql = QHBoxLayout(quick_wrap)
        ql.setContentsMargins(1, 1, 1, 1)
        ql.setSpacing(0)

        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Quick connect:  user@host[:port]")
        self.quick.setFixedWidth(212)
        self.quick.setObjectName("quickInput")
        self.quick.returnPressed.connect(self.quick_connect)
        self.quick.setAccessibleName("Quick connect")
        ql.addWidget(self.quick, 1)

        qc_btn = QPushButton("Connect")
        qc_btn.setObjectName("primary")
        qc_btn.setToolTip("Connect now (Enter)")
        qc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qc_btn.clicked.connect(self.quick_connect)
        qc_btn.setFixedWidth(84)
        ql.addWidget(qc_btn, 0)
        quick_wrap.setFixedHeight(30)
        quick_wrap.setFixedWidth(212 + 84)
        quick_holder = QWidget()
        qhl = QVBoxLayout(quick_holder)
        qhl.setContentsMargins(6, 0, 6, 0)
        qhl.addStretch(1)
        qhl.addWidget(quick_wrap)
        qhl.addStretch(1)
        bar.addWidget(quick_holder)

        # Right-aligned group (Settings · Help · Close all) like MobaXterm's
        # "X server / Exit" cluster.
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bar.addWidget(spacer)

        bar.addSeparator()
        add_tool("gear", "Settings", "Settings (Ctrl+,)", self.open_settings)
        add_tool("shield", "Help", "Keyboard shortcuts & help", self.open_shortcuts)

        # Close all tabs button
        self._close_all_btn = themed_action("close", "Close all")
        self._close_all_btn.setToolTip("Close all open session tabs")
        self._close_all_btn.triggered.connect(self._close_all_tabs)
        self._close_all_btn.setVisible(False)

        self.addToolBar(bar)
        self._apply_ui_prefs()
