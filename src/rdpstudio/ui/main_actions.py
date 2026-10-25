"""Menu-bar + toolbar builders, moved verbatim from MainWindow (ARCH-02).

Mixin methods — ``self`` is the MainWindow at runtime.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
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
    """Builds the menu bar and the compact Studio command bar."""

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

        self._act_broadcast = QAction(icon("transfer"), "&MultiExec (broadcast input)", self)
        self._act_broadcast.setCheckable(True)
        self._act_broadcast.setShortcut(QKeySequence("Ctrl+Alt+B"))
        self._act_broadcast.setStatusTip(
            "Send every keystroke and command to all connected shell tabs"
        )
        self._act_broadcast.toggled.connect(self.set_broadcast_input)
        m_session.addAction(self._act_broadcast)
        self._menu_action(
            m_session, "clock", "Remote &monitoring…",
            "Live CPU, memory, swap, disk and network of the current SSH host (Ctrl+Shift+M)",
            self.open_remote_monitor, shortcut="Ctrl+Shift+M",
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
        """Build the command bar: brand, primary action, tools, quick connect.

        Visual hierarchy (left → right): product mark, the one primary action
        (*New session*), destination actions (Terminal / Sessions), utility
        tools, the always-available quick-connect field, then a quiet icon
        cluster for preferences at the far edge. Actions are unchanged — only
        their grouping, prominence and object names (for the stylesheet) are
        new.
        """
        bar = QToolBar()
        bar.setObjectName("moxaToolbar")  # retained for stylesheet/test compatibility
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(18, 18))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toolbar = bar
        self._themed_actions: list[tuple[QAction, str]] = []
        self._themed_labels: list[tuple[QLabel, str]] = []

        # ---- brand block ------------------------------------------------
        brand = QWidget()
        brand.setObjectName("brandBlock")
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(2, 0, 10, 0)
        bl.setSpacing(9)

        mark = QLabel("KB")
        mark.setObjectName("brandMark")
        mark.setFixedSize(30, 30)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bl.addWidget(mark)

        title = QLabel("KB-Remote")
        title.setObjectName("brandName")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bl.addWidget(title)
        self._brand_title = title

        self._brand_block = brand
        self._brand_action = bar.addWidget(brand)

        divider = QFrame()
        divider.setObjectName("brandDivider")
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setFixedWidth(1)
        self._brand_divider_action = bar.addWidget(divider)
        self._brand_divider = divider

        def themed_action(icon_name: str, text: str) -> QAction:
            act = bar.addAction(theme.toolbar_icon(icon_name), text)
            self._themed_actions.append((act, icon_name))
            return act

        def style_action(act: QAction, object_name: str) -> None:
            """Tag the toolbar button a QAction materialises as."""
            button = bar.widgetForAction(act)
            if button is not None:
                button.setObjectName(object_name)
                button.setCursor(Qt.CursorShape.PointingHandCursor)

        def set_compact(act: QAction) -> None:
            """Icon-only button: the label lives in the tooltip.

            Keeps the bar to a single calm row — the primary action is the
            only item that carries a persistent label, so the eye has one
            obvious destination instead of nine competing words.
            """
            button = bar.widgetForAction(act)
            if button is not None:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setMinimumWidth(34)

        # ---- primary + destinations ------------------------------------
        a = themed_action("plus", "New session")
        a.setToolTip("Create a new saved session (Ctrl+N)")
        a.setStatusTip("Create a new saved session")
        a.triggered.connect(self.new_session)
        style_action(a, "tbPrimary")
        self._act_new_session = a

        a = themed_action("console", "Terminal")
        a.setToolTip("Open a local terminal tab (Ctrl+Shift+T)")
        a.setStatusTip("Open a local terminal tab")
        a.triggered.connect(self.open_local_terminal)
        set_compact(a)
        self._act_terminal_toolbar = a

        act_sidebar = themed_action("panel", "Sessions")
        act_sidebar.setToolTip("Show / hide the Sessions side panel (Ctrl+B)")
        act_sidebar.setStatusTip("Show or hide the Sessions side panel")
        act_sidebar.setCheckable(True)
        act_sidebar.toggled.connect(self._toggle_sidebar)
        set_compact(act_sidebar)
        self._act_sidebar_toolbar = act_sidebar

        bar.addSeparator()

        # ---- tools ------------------------------------------------------
        def add_tool(icon_name, text, tip, cb):
            act = themed_action(icon_name, text)
            act.setToolTip(tip)
            act.setStatusTip(tip)
            act.triggered.connect(cb)
            return act

        self._tool_actions = []
        for icon_name, label, tip, callback in (
            ("search", "Commands", "Command Palette & Quick Switcher (Ctrl+P / Ctrl+K)", self.open_command_palette),
            ("server", "Servers", "Network Tools & Port Scanner (Ctrl+Shift+N)", self.open_network_tools),
            ("key", "Keys", "SSH Key Utility & Converter (Ctrl+Shift+U)", self.open_key_utility),
            ("transfer", "Tunnels", "SSH tunnels / port forwarding", self.open_tunnels_dialog),
        ):
            act = add_tool(icon_name, label, tip, callback)
            set_compact(act)
            self._tool_actions.append(act)

        bar.addSeparator()

        # ---- quick connect ---------------------------------------------
        # Deliberately integrated into the command bar so the highest-frequency
        # action stays available without opening a dialog.
        quick_wrap = QWidget()
        quick_wrap.setObjectName("quickConnect")
        ql = QHBoxLayout(quick_wrap)
        ql.setContentsMargins(10, 1, 2, 1)
        ql.setSpacing(6)
        self._quick_wrap = quick_wrap

        qc_ic = QLabel()
        qc_ic.setPixmap(theme.accent_icon("plug", 14).pixmap(14, 14))
        qc_ic.setFixedSize(16, 16)
        qc_ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qc_ic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._quick_icon = qc_ic
        ql.addWidget(qc_ic, 0)

        self.quick = QLineEdit()
        self.quick.setPlaceholderText("user@host[:port]")
        # Flexible width: the strip compresses on narrow windows instead of
        # pushing the whole toolbar off-screen.
        self.quick.setMinimumWidth(140)
        self.quick.setMaximumWidth(248)
        self.quick.setObjectName("quickInput")
        self.quick.returnPressed.connect(self.quick_connect)
        self.quick.setAccessibleName("Quick connect")
        self.quick.setToolTip("Open user@host[:port] — port 3389 opens RDP (Enter)")
        ql.addWidget(self.quick, 1)

        qc_btn = QPushButton("Connect")
        qc_btn.setObjectName("primary")
        qc_btn.setProperty("quickGo", True)
        qc_btn.setToolTip("Connect now (Enter)")
        qc_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        qc_btn.clicked.connect(self.quick_connect)
        qc_btn.setMinimumWidth(76)
        ql.addWidget(qc_btn, 0)
        self._quick_go = qc_btn
        quick_wrap.setFixedHeight(34)
        quick_wrap.setMinimumWidth(244)
        quick_wrap.setMaximumWidth(348)
        quick_holder = QWidget()
        qhl = QVBoxLayout(quick_holder)
        qhl.setContentsMargins(6, 0, 6, 0)
        qhl.addStretch(1)
        qhl.addWidget(quick_wrap)
        qhl.addStretch(1)
        self._quick_holder = quick_holder
        self._quick_holder_action = bar.addWidget(quick_holder)

        # ---- quiet preferences cluster ----------------------------------
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        spacer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        bar.addWidget(spacer)

        sep = QFrame()
        sep.setObjectName("brandDivider")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        self._end_divider_action = bar.addWidget(sep)
        self._end_divider = sep

        prefs = []
        prefs.append(add_tool("gear", "Settings", "Settings (Ctrl+,)", self.open_settings))
        prefs.append(add_tool("shield", "Help", "Keyboard shortcuts & help", self.open_shortcuts))
        for act in prefs:
            style_action(act, "tbIcon")
            button = bar.widgetForAction(act)
            if button is not None:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        # Close all — destructive, hidden until more than one tab is open.
        self._close_all_btn = themed_action("close", "Close all")
        self._close_all_btn.setToolTip("Close all open session tabs")
        self._close_all_btn.triggered.connect(self._close_all_tabs)
        self._close_all_btn.setVisible(False)
        style_action(self._close_all_btn, "tbIcon")

        self.addToolBar(bar)
        self._apply_ui_prefs()

    # ------------------------------------------------------------------
    # Responsive chrome
    # ------------------------------------------------------------------
    def _apply_responsive_chrome(self, width: int) -> None:
        """Adapt the command bar to the window width (mobile-first rules).

        Three breakpoints, checked widest first:

        * ≥ 1240 px — full chrome: brand, labelled primary, all tools.
        * ≥ 1040 px — brand stays, the quick-connect field narrows.
        * ≥ 900 px  — the wordmark drops (the mark remains), quick narrows
          again so nothing is pushed into the overflow menu.
        * < 900 px  — icon-only buttons; the utility tools step aside for
          the palette (still reachable via Ctrl+P and the menus) and the
          quick-connect field yields to the dashboard/sidebar inputs, which
          are always on screen.
        """
        bar = getattr(self, "_toolbar", None)
        if bar is None:
            return
        if width < 900:
            tier = 0
        elif width < 1040:
            tier = 1
        elif width < 1240:
            tier = 2
        else:
            tier = 3

        if tier != getattr(self, "_responsive_tier", None):
            self._responsive_tier = tier
            # The bar-level style stays "label beside icon" (the app's normal
            # look and the documented default); the compact buttons opt out
            # individually below. ``QToolBar.setToolButtonStyle`` resets every
            # button, so the per-button overrides must come after this call.
            bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            # Widget actions are shown/hidden through the QAction the toolbar
            # created for them — the toolbar re-applies that state on every
            # layout pass, so setting the widget directly does not stick.
            brand_rows = (
                getattr(self, "_brand_action", None),
                getattr(self, "_brand_divider_action", None),
                getattr(self, "_end_divider_action", None),
            )
            for action in brand_rows:
                if action is not None:
                    action.setVisible(tier >= 2)
            # The primary action always keeps its label — it is the one
            # destination the user should never have to hunt for.
            primary = getattr(self, "_act_new_session", None)
            if primary is not None:
                button = bar.widgetForAction(primary)
                if button is not None:
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            # Everything else is icon-only: one labelled destination per row.
            for act, _icon in getattr(self, "_themed_actions", []):
                if act is primary:
                    continue
                button = bar.widgetForAction(act)
                if button is not None:
                    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                    button.setMinimumWidth(34)
            quick = getattr(self, "quick", None)
            if quick is not None:
                quick.setMaximumWidth(248 if tier >= 2 else 168)
            wrap = getattr(self, "_quick_wrap", None)
            if wrap is not None:
                wrap.setMaximumWidth(348 if tier >= 2 else 268)
            holder_action = getattr(self, "_quick_holder_action", None)
            if holder_action is not None:
                holder_action.setVisible(tier >= 1)
            for act in getattr(self, "_tool_actions", []):
                act.setVisible(tier >= 1)
            tool_actions = set(getattr(self, "_tool_actions", []))
            for act, _icon in getattr(self, "_themed_actions", []):
                if act in tool_actions or act is self._close_all_btn:
                    continue
                act.setVisible(True)

