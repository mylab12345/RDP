"""Main window: tabbed sessions, sidebar, toolbar, quick connect."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
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
from ..core.models import Session
from ..core.plugin import (
    SessionContext,
    SessionController,
    SessionState,
    registry,
)
from . import theme
from .sidebar import SessionTree
from .theme import icon
from .widgets import STATE_COLORS, StateChip, toast

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
    """One tab: hosts a SessionController + a slim status header."""

    def __init__(self, controller: SessionController, main: MainWindow) -> None:
        super().__init__()
        self.controller = controller
        self.main = main
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 4, 8, 4)
        self.chip = StateChip("connecting", "info")
        self.info = QLabel("")
        self.info.setObjectName("muted")
        h.addWidget(self.chip)
        h.addSpacing(8)
        h.addWidget(self.info, 1)

        self.btn_reconnect = QPushButton("Reconnect")
        self.btn_reconnect.clicked.connect(controller.request_reconnect)
        self.btn_reconnect.setVisible(False)
        h.addWidget(self.btn_reconnect)

        caps = controller.capabilities()
        if caps.sftp:
            b = QPushButton("Files")
            b.clicked.connect(controller.open_sftp)
            h.addWidget(b)
        if caps.tunnels:
            b = QPushButton("Tunnels")
            b.clicked.connect(controller.open_tunnels)
            h.addWidget(b)
        header.setAutoFillBackground(True)
        layout.addWidget(header)

        self._content = controller.widget()
        layout.addWidget(self._content, 1)

        # protocols that can switch display mode at runtime (e.g. RDP
        # built-in → external) tell us to swap the content widget
        widget_changed = getattr(controller, "widgetChanged", None)
        if widget_changed is not None:
            widget_changed.connect(self._swap_content)

        controller.stateChanged.connect(self._on_state)
        controller.statusInfo.connect(self._on_status)
        controller.finished.connect(self._on_finished)
        controller.reconnectScheduled.connect(self._on_reconnect_scheduled)

    def _swap_content(self) -> None:
        """Replace the tab content widget (e.g. RDP display mode changed)."""
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
            self.info.setText(
                f"{c.get('username', '')}@{c.get('host', '')}"
                + (f"  ·  {c['cipher']}" if c.get("cipher") else "")
                + (f"  ·  {c['remote_version'].split(chr(10))[0]}" if c.get("remote_version") else "")
            )
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
        self.resize(1280, 800)
        self.controllers: dict[int, SessionTab] = {}  # tabIndex -> tab (rebuilt lazily)

        self._build_menu()
        self._build_toolbar()
        self._build_body()

        status = QStatusBar()
        self.setStatusBar(status)
        self.vault_label = QLabel("")
        status.addWidget(self.vault_label)
        self.status_label = QLabel("")
        status.addPermanentWidget(self.status_label)
        self._refresh_vault_label()

        # autolock timer
        self._lock_timer = QTimer(self)
        self._lock_timer.setInterval(30_000)
        self._lock_timer.timeout.connect(self._autolock)
        self._lock_timer.start()

        # geometry restore
        geo = ctx.settings.geometry
        if isinstance(geo, dict) and geo.get("size"):
            from PySide6.QtCore import QSize

            self.resize(QSize(int(geo["size"][0]), int(geo["size"][1])))
            if geo.get("pos"):
                from PySide6.QtCore import QPoint

                self.move(QPoint(int(geo["pos"][0]), int(geo["pos"][1])))
            if geo.get("maximized"):
                self.showMaximized()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("&Session")
        act = QAction(icon("plus"), "&New session…", self)
        act.setShortcut(QKeySequence("Ctrl+N"))
        act.triggered.connect(self.new_session)
        m_file.addAction(act)

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
        a = QAction(icon("shield"), "Credential &vault…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+K"))
        a.triggered.connect(self.open_vault)
        m_tools.addAction(a)
        a = QAction(icon("plug"), "&Port forwarding…", self)
        a.setShortcut(QKeySequence("Ctrl+Shift+P"))
        a.triggered.connect(self.open_tunnels_dialog)
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
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        a = bar.addAction(icon("plus"), "New")
        a.triggered.connect(self.new_session)

        self.quick = QLineEdit()
        self.quick.setPlaceholderText("Quick connect: user@host[:port]  ⏎")
        self.quick.setFixedWidth(260)
        self.quick.returnPressed.connect(self.quick_connect)
        bar.addWidget(self.quick)

        bar.addSeparator()
        a = bar.addAction(icon("shield"), "Vault")
        a.triggered.connect(self.open_vault)
        a = bar.addAction(icon("plug"), "Tunnels")
        a.triggered.connect(self.open_tunnels_dialog)
        a = bar.addAction(icon("windows"), "RDP server")
        a.triggered.connect(self.open_rdp_server_manager)
        a = bar.addAction(icon("gear"), "Settings")
        a.triggered.connect(self.open_settings)
        self.addToolBar(bar)

    def _build_body(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.sidebar = SessionTree(self.ctx.store)
        splitter.addWidget(self.sidebar)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        corner = QWidget()
        cl = QHBoxLayout(corner)
        cl.setContentsMargins(6, 2, 6, 2)
        plus = QPushButton("+")
        plus.setFlat(True)
        plus.setToolTip("New session (Ctrl+N)")
        plus.clicked.connect(self.new_session)
        cl.addWidget(plus)
        self.tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)

        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 1000])
        self.setCentralWidget(splitter)

        # sidebar events
        self.sidebar.connectRequested.connect(self.connect_session)
        self.sidebar.editRequested.connect(self.edit_session)
        self.sidebar.duplicateRequested.connect(lambda sid: (self.ctx.store.duplicate(sid), self.sidebar.reload()))
        self.sidebar.deleteRequested.connect(self._delete_session)
        self.sidebar.sftpRequested.connect(self._connect_and_sftp)
        self.sidebar.newSessionRequested.connect(self.new_session)
        self.sidebar.newFolderRequested.connect(self.sidebar.prompt_new_folder)

    # ------------------------------------------------------------------
    # session lifecycle
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
            idx = self.tabs.indexOf(_tab)
            if idx >= 0:
                self.tabs.setTabText(idx, t)

        controller.titleChanged.connect(_set_title)
        controller.start()
        return tab

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, SessionTab):
            widget.controller.stop("closed by user")
            widget.controller.deleteLater()
        self.tabs.removeTab(index)
        widget and widget.deleteLater()

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
                widget.controller.widget().setFocus()

    # -- dialogs -------------------------------------------------------------
    def new_session(self, *args) -> None:
        from .session_dialog import SessionDialog

        group = self.sidebar.selected_group()
        dlg = SessionDialog(self.ctx, Session(group=group), self)
        if dlg.exec():
            self.sidebar.reload()
            if dlg.session.id:
                self.connect_session(dlg.session.id)

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
            # pick any live ssh tab
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
            "Python · Qt (PySide6) · paramiko · pyte",
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
        try:
            data = open(path, encoding="utf-8").read()
            import json

            payload = json.loads(data)
            sessions = [Session.from_dict(d) for d in payload.get("sessions", [])]
            added = self.ctx.store.import_sessions(sessions)
            for g in payload.get("groups", []):
                self.ctx.store.ensure_group(g)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        self.sidebar.reload()
        toast(self, f"Imported {added} session(s)", "good")

    def _export_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export sessions", "rdpstudio-sessions.json", "JSON (*.json)")
        if not path:
            return
        import json

        open(path, "w", encoding="utf-8").write(json.dumps(self.ctx.store.export_dict(), indent=2))
        toast(self, "Exported (secrets are NOT included)", "good")

    def _open_path(self, path) -> None:
        import subprocess

        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    # -- vault status ----------------------------------------------------------
    def _refresh_vault_label(self) -> None:
        try:
            unlocked = self.ctx.vault.unlocked
            exists = self.ctx.vault.exists
        except Exception:  # noqa: BLE001
            unlocked, exists = False, False
        if unlocked:
            self.vault_label.setText(" 🔓 vault unlocked")
        elif exists:
            self.vault_label.setText(" 🔒 vault locked")
        else:
            self.vault_label.setText(" ⚪ no vault (optional — passwords can be saved per session)")

    def _autolock(self) -> None:
        changed = self.ctx.vault.lock_if_due(self.ctx.settings.vault_autolock_minutes)
        if changed:
            self._refresh_vault_label()
            toast(self, "Vault auto-locked after inactivity", "warn")

    # -- close ---------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, SessionTab):
                w.controller.stop("app closed")
        settings = self.ctx.settings
        settings.geometry = {
            "size": [self.width(), self.height()],
            "pos": [self.x(), self.y()],
            "maximized": self.isMaximized(),
        }
        settings.save(paths.settings_file())
        super().closeEvent(event)
