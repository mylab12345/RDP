"""Menu-bar + toolbar builders, moved verbatim from MainWindow (ARCH-02).

Mixin methods — ``self`` is the MainWindow at runtime.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..core import paths
from . import theme
from .theme import icon


class MainActionsMixin:
    """Builds the menu bar and the MobaXterm-style toolbar."""

    def _menu_action(
        self,
        menu,
        icon_name: str | None,
        text: str,
        tip: str,
        callback=None,
        *,
        shortcut: str | None = None,
    ) -> QAction:
        """One menu entry: icon + label + status-bar tip + shortcut.

        Every action explains itself in the status bar (user feedback) and
        carries an icon so the grouped menus scan at a glance.
        """
        act = QAction(icon(icon_name) if icon_name else QIcon(), text, self)
        act.setStatusTip(tip)
        if shortcut:
            act.setShortcut(QKeySequence(shortcut))
        if callback is not None:
            act.triggered.connect(callback)
        menu.addAction(act)
        return act

    def _build_menu(self) -> None:
        """Menu layout: File, View, Tools, Tabs, Session, Help.

        Navigation is grouped by task — related features sit together
        behind clear labels, every action has an icon and a status-bar tip,
        and nothing is more than one submenu deep.
        """
        # ── File: create · import/export · exit ──
        m_file = self.menuBar().addMenu("&File")

        self._menu_action(
            m_file, "plus", "&New session…",
            "Create a new saved session (Ctrl+N)",
            self.new_session, shortcut="Ctrl+N",
        )
        self._menu_action(
            m_file, "console", "New local &terminal",
            "Open a native local shell in a new tab (Ctrl+Shift+T)",
            self.open_local_terminal, shortcut="Ctrl+Shift+T",
        )

        m_file.addSeparator()

        imp = m_file.addMenu(icon("folder"), "&Import")
        imp.menuAction().setStatusTip("Bring sessions in from another tool or file")
        self._menu_action(
            imp, "folder", "From ~/.ssh/config",
            "Import hosts from your OpenSSH config file",
            self._import_ssh_config,
        )
        self._menu_action(
            imp, "file", "From file (JSON)…",
            "Import sessions from a KB-Remote JSON export",
            self._import_json,
        )

        self._menu_action(
            m_file, "transfer", "&Export sessions to file…",
            "Export saved sessions to JSON (secrets are never included)",
            self._export_json,
        )
        m_file.addSeparator()

        self._menu_action(
            m_file, "close", "E&xit",
            "Close KB-Remote (Ctrl+Q)",
            self.close, shortcut="Ctrl+Q",
        )

        # ── View: launchers · panels & layout · appearance ──
        m_view = self.menuBar().addMenu("&View")

        self._menu_action(
            m_view, "search", "Command &Palette / Switcher…",
            "Search sessions, tabs, tools and actions (Ctrl+P)",
            self.open_command_palette, shortcut="Ctrl+P",
        )

        m_view.addSeparator()

        self._act_sidebar_menu = QAction(icon("panel"), "&Toggle Sidebar", self)
        self._act_sidebar_menu.setShortcut(QKeySequence("Ctrl+B"))
        self._act_sidebar_menu.setCheckable(True)
        self._act_sidebar_menu.setStatusTip("Show / hide the Sessions side panel (Ctrl+B)")
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
        m_tabs_pos.menuAction().setStatusTip("Where the open-session tab strip lives")
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
            act.setStatusTip(f"Dock the session tab strip to the {key} edge")
            act.triggered.connect(lambda checked, k=key: checked and self.set_tabs_position(k))
            self._tabs_pos_group.addAction(act)
            m_tabs_pos.addAction(act)
            self._tabs_pos_actions[key] = act
        act = QAction(icon("panel"), "&Cycle tab strip position", self)
        act.setShortcut(QKeySequence("Ctrl+Shift+J"))
        act.setStatusTip("Walk the tab strip top → left → right → top")
        act.triggered.connect(self.cycle_tabs_position)
        m_tabs_pos.addSeparator()
        m_tabs_pos.addAction(act)

        m_view.addSeparator()

        m_themes = m_view.addMenu(icon("star"), "&Theme")
        m_themes.menuAction().setStatusTip("Switch the application colour scheme")
        from ..core.settings import THEME_CHOICES

        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for tid, label in THEME_CHOICES:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self.ctx.settings.theme == tid)
            act.setStatusTip(f"Apply the {label.split('—')[0].strip()} theme")
            act.triggered.connect(lambda checked, t=tid: checked and self.apply_theme_id(t))
            self._theme_group.addAction(act)
            m_themes.addAction(act)
            self._theme_actions[tid] = act

        # ── Tools: diagnostics · credentials · configuration ──
        m_tools = self.menuBar().addMenu("&Tools")
        self._menu_action(
            m_tools, "server", "Network Tools & Port &Scanner…",
            "TCP port scanner, ping latency probe and DNS lookup (Ctrl+Shift+N)",
            self.open_network_tools, shortcut="Ctrl+Shift+N",
        )
        self._menu_action(
            m_tools, "key", "SSH &Key Utility & Converter…",
            "Generate keys, visualise randomart, convert to PuTTY PPK (Ctrl+Shift+U)",
            self.open_key_utility, shortcut="Ctrl+Shift+U",
        )
        self._menu_action(
            m_tools, "windows", "RDP server &manager…",
            "Check and enable or disable this machine's RDP listener",
            self.open_rdp_server_manager,
        )

        m_tools.addSeparator()

        self._menu_action(
            m_tools, "gear", "&Settings…",
            "Preferences: themes, fonts, connections, security (Ctrl+,)",
            self.open_settings, shortcut="Ctrl+",
        )
        self._menu_action(
            m_tools, "folder", "Open &logs folder",
            "Open the folder holding session logs",
            lambda: paths.logs_dir() and self._open_path(paths.logs_dir()),
        )

        # ── Tabs: close · manage · snapshots · navigate ──
        m_tabs = self.menuBar().addMenu("&Tabs")

        self._menu_action(
            m_tabs, "close", "Close &Tab",
            "Close the current session tab",
            self.close_current_tab,
        )
        self._menu_action(
            m_tabs, "close", "Close &Other Tabs",
            "Close every session tab except the current one",
            self._close_others_current,
        )
        self._menu_action(
            m_tabs, "close", "Close Tabs &to the Right",
            "Close the session tabs to the right of the current one",
            self._close_right_current,
        )
        self._menu_action(
            m_tabs, "close", "Close &All Tabs",
            "Close every open session tab (asks first)",
            self._close_all_tabs,
        )

        m_tabs.addSeparator()

        self._menu_action(
            m_tabs, "plus", "&Duplicate Tab",
            "Open a second tab with the same session (Ctrl+Shift+D)",
            self.duplicate_current_tab, shortcut="Ctrl+Shift+D",
        )
        self._menu_action(
            m_tabs, "edit", "&Rename Tab…",
            "Give the current session tab a custom title",
            self._rename_current_tab,
        )
        self._menu_action(
            m_tabs, "connect", "&Reconnect Session",
            "Reconnect the current session tab",
            self._reconnect_current,
        )

        m_tabs.addSeparator()

        self._menu_action(
            m_tabs, "clock", "Save Session S&napshot…",
            "Save the current set of open saved sessions for quick reconnection (Ctrl+Alt+S)",
            self.save_session_snapshot, shortcut="Ctrl+Alt+S",
        )

        self._snapshot_restore_menu = m_tabs.addMenu(icon("clock"), "Restore Session Snap&shot")
        self._snapshot_restore_menu.menuAction().setStatusTip("Reopen a saved set of session tabs")
        self._snapshot_restore_menu.aboutToShow.connect(self._populate_snapshot_menu)

        m_tabs.addSeparator()

        self._menu_action(
            m_tabs, None, "&Next Tab",
            "Switch to the next session tab (Ctrl+Tab)",
            self.next_tab, shortcut="Ctrl+Tab",
        )
        self._menu_action(
            m_tabs, None, "Pre&vious Tab",
            "Switch to the previous session tab (Ctrl+Shift+Backtab)",
            self.prev_tab, shortcut="Ctrl+Shift+Backtab",
        )

        # ── Session: this session's actions ──
        m_session = self.menuBar().addMenu("&Session")

        self._menu_action(
            m_session, "plus", "&New session…",
            "Create a new saved session (Ctrl+N)",
            self.new_session, shortcut="Ctrl+N",
        )
        self._menu_action(
            m_session, "file", "Start / Stop Session &Logging…",
            "Capture the current session's output to a log file (Ctrl+Shift+L)",
            self.toggle_session_logging, shortcut="Ctrl+Shift+L",
        )

        m_session.addSeparator()

        self._menu_action(
            m_session, "folder", "Browse &Files (SFTP)…",
            "Browse and transfer files on the current session's host",
            self._sftp_current,
        )

        # ── Help ──
        m_help = self.menuBar().addMenu("&Help")
        self._menu_action(
            m_help, "shield", "&Keyboard shortcuts…",
            "See every keyboard shortcut in one place",
            self.open_shortcuts,
        )
        self._menu_action(
            m_help, "logo", "&About",
            f"About {APP_NAME}",
            self._about,
        )

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
        # Flexible width: the strip compresses on narrow windows instead of
        # pushing the whole toolbar off-screen.
        self.quick.setMinimumWidth(140)
        self.quick.setMaximumWidth(212)
        self.quick.setObjectName("quickInput")
        self.quick.returnPressed.connect(self.quick_connect)
        self.quick.setAccessibleName("Quick connect")
        self.quick.setToolTip("Open user@host[:port] — port 3389 opens RDP (Enter)")
        ql.addWidget(self.quick, 1)

        qc_btn = QPushButton("Connect")
        qc_btn.setObjectName("primary")
        qc_btn.setToolTip("Connect now (Enter)")
        qc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qc_btn.clicked.connect(self.quick_connect)
        qc_btn.setFixedWidth(84)
        ql.addWidget(qc_btn, 0)
        quick_wrap.setFixedHeight(30)
        quick_wrap.setMinimumWidth(230)
        quick_wrap.setMaximumWidth(300)
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
