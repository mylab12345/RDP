"""New/Edit session dialog with per-protocol option pages."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.models import (
    AUTH_AGENT,
    AUTH_CREDENTIAL,
    AUTH_KEY,
    AUTH_PASSWORD,
    PROTOCOL_LOCAL,
    PROTOCOL_RDP,
    PROTOCOL_SSH,
    Session,
    default_port_for,
)
from ..core.plugin import SessionContext, registry
from .forward_editor import ForwardListEditor


class SessionDialog(QDialog):
    """Create or edit a saved session."""

    def __init__(self, ctx: SessionContext, session: Session | None = None, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.session = session or Session(protocol=PROTOCOL_SSH)
        self.is_new = session is None
        if self.is_new:
            # fresh sessions start at the protocol's default port (22 / 3389)
            self.session.port = default_port_for(self.session.protocol)
        self.setWindowTitle("New session" if self.is_new else f"Edit “{self.session.display_name()}”")
        self.setModal(True)
        self.setMinimumWidth(560)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # --- header row: protocol + name/group -----------------------------
        head = QFormLayout()
        self.protocol = QComboBox()
        for plugin in registry().editable():
            self.protocol.addItem(icon_text(plugin), plugin.id)
        self.name = QLineEdit(self.session.name)
        self.name.setPlaceholderText("(defaults to user@host)")
        self.group = QComboBox()
        self.group.setEditable(True)
        for g in ctx.store.groups():
            self.group.addItem(g)
        self.group.setCurrentText(self.session.group)
        head.addRow("Protocol", self.protocol)
        head.addRow("Name", self.name)
        head.addRow("Folder", self.group)
        root.addLayout(head)

        # --- common connection fields (always visible: host/user/password) ---
        common_wrap = QWidget()
        cl = QVBoxLayout(common_wrap)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self._build_common())
        root.addWidget(common_wrap)

        # --- protocol-specific options ---------------------------------------
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self._ssh_page = self._build_ssh_page()
        self.stack.addWidget(self._ssh_page)
        self._rdp_page = self._build_rdp_page()
        self.stack.addWidget(self._rdp_page)
        self._local_page = self._build_local_page()
        self.stack.addWidget(self._local_page)

        self._last_pid: str | None = None
        self.protocol.currentIndexChanged.connect(self._on_protocol)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        idx = self.protocol.findData(self.session.protocol)
        if idx >= 0:
            self.protocol.setCurrentIndex(idx)
        self._on_protocol()

    # ------------------------------------------------------------------
    def _build_common(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.host = QLineEdit(self.session.host)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(self.session.port or 22)
        self.username = QLineEdit(self.session.username)
        self.password = QLineEdit(self.session.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("leave empty to be asked at connect")
        self.password.setToolTip(
            "Optional. Stored in plain text in the sessions file — no vault needed.\n"
            "Leave empty and you'll be asked each time you connect."
        )
        self.description = QLineEdit(self.session.description)
        self.tags = QLineEdit(" ".join(self.session.tags))
        self.tags.setPlaceholderText("prod, web, …")

        form.addRow("Host", self.host)
        form.addRow("Port", self.port)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        form.addRow("Description", self.description)
        form.addRow("Tags", self.tags)
        return page

    def _build_auth_box(self) -> QGroupBox:
        box = QGroupBox("Authentication")
        form = QFormLayout(box)
        self.auth = QComboBox()
        self.auth.addItem("Password (field above)", AUTH_PASSWORD)
        self.auth.addItem("Vault credential (optional)", AUTH_CREDENTIAL)
        self.auth.addItem("Private key", AUTH_KEY)
        self.auth.addItem("SSH agent", AUTH_AGENT)
        form.addRow("Method", self.auth)

        self.credential = QComboBox()
        self._reload_credentials()
        form.addRow("Credential", self.credential)

        self.key_path = QLineEdit(self.session.key_path)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_path, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_key)
        key_row.addWidget(browse)
        form.addRow("Key file", key_row)

        self.auth.currentIndexChanged.connect(self._on_auth)
        idx = self.auth.findData(self.session.auth or AUTH_PASSWORD)
        self.auth.setCurrentIndex(idx if idx >= 0 else 0)
        if self.session.credential_id:
            ci = self.credential.findData(self.session.credential_id)
            if ci >= 0:
                self.credential.setCurrentIndex(ci)
        self._on_auth()
        return box

    def _reload_credentials(self) -> None:
        self.credential.clear()
        self.credential.addItem("— none —", "")
        try:
            for cred in self.ctx.vault.entries():
                label = cred.name or cred.id
                if cred.username:
                    label += f" ({cred.username})"
                self.credential.addItem(label, cred.id)
        except Exception:  # vault locked
            pass

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose private key", "", "Keys (*)")
        if path:
            self.key_path.setText(path)

    def _build_ssh_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_auth_box())

        behaviour = QGroupBox("Session behaviour")
        form = QFormLayout(behaviour)
        self.jump = QComboBox()
        self.jump.addItem("— none —", "")
        for s in self.ctx.store.sessions():
            if s.protocol == PROTOCOL_SSH and s.id != self.session.id:
                self.jump.addItem(s.display_name(), s.id)
        if self.session.jump_session_id:
            ji = self.jump.findData(self.session.jump_session_id)
            if ji >= 0:
                self.jump.setCurrentIndex(ji)
        form.addRow("Jump host (ProxyJump)", self.jump)

        self.startup = QLineEdit(self.session.startup_command)
        self.startup.setPlaceholderText("e.g. sudo -i   (run after login)")
        form.addRow("Startup command", self.startup)

        row = QHBoxLayout()
        self.keepalive = QSpinBox()
        self.keepalive.setRange(5, 300)
        self.keepalive.setValue(self.session.keepalive or 30)
        self.keepalive.setSuffix(" s")
        row.addWidget(QLabel("Keepalive"))
        row.addWidget(self.keepalive)
        row.addWidget(QLabel("Timeout"))
        self.timeout = QSpinBox()
        self.timeout.setRange(3, 120)
        self.timeout.setValue(self.session.timeout or 10)
        self.timeout.setSuffix(" s")
        row.addWidget(self.timeout)
        row.addStretch(1)
        form.addRow(row)

        self.compression = QCheckBox("Compression")
        self.compression.setChecked(self.session.compression)
        self.auto_reconnect = QCheckBox("Auto-reconnect")
        self.auto_reconnect.setChecked(self.session.auto_reconnect)
        auto_row = QHBoxLayout()
        auto_row.addWidget(self.compression)
        auto_row.addWidget(self.auto_reconnect)
        auto_row.addStretch(1)
        form.addRow(auto_row)
        layout.addWidget(behaviour)

        fwd_box = QGroupBox("Port forwarding (starts with session)")
        fl = QVBoxLayout(fwd_box)
        self.forwards = ForwardListEditor()
        self.forwards.set_forwards(self.session.forwards)
        fl.addWidget(self.forwards)
        layout.addWidget(fwd_box)
        layout.addStretch(1)
        return page

    def _build_rdp_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_auth_box())

        display = QGroupBox("Display")
        form = QFormLayout(display)
        res = QHBoxLayout()
        self.rdp_width = QSpinBox()
        self.rdp_width.setRange(640, 7680)
        self.rdp_width.setValue(self.session.rdp_width)
        self.rdp_height = QSpinBox()
        self.rdp_height.setRange(480, 4320)
        self.rdp_height.setValue(self.session.rdp_height)
        res.addWidget(self.rdp_width)
        res.addWidget(QLabel("×"))
        res.addWidget(self.rdp_height)
        res.addWidget(QLabel("  Color depth"))
        self.rdp_bpp = QComboBox()
        for bpp in (16, 24, 32):
            self.rdp_bpp.addItem(f"{bpp}-bit", bpp)
        bi = self.rdp_bpp.findData(self.session.rdp_color_depth)
        self.rdp_bpp.setCurrentIndex(bi if bi >= 0 else 2)
        res.addWidget(self.rdp_bpp)
        res.addStretch(1)
        form.addRow("Resolution", res)
        self.rdp_fullscreen = QCheckBox("Fullscreen")
        self.rdp_fullscreen.setChecked(self.session.rdp_fullscreen)
        self.rdp_fit_screen = QCheckBox("Fit display to screen")
        self.rdp_fit_screen.setChecked(self.session.rdp_fit_screen)
        self.rdp_fit_screen.setToolTip(
            "Scale the remote desktop to fill the RDP window "
            "(FreeRDP /smart-sizing · mstsc smart sizing)"
        )
        fit_row = QHBoxLayout()
        fit_row.addWidget(self.rdp_fullscreen)
        fit_row.addWidget(self.rdp_fit_screen)
        fit_row.addStretch(1)
        form.addRow("", fit_row)
        layout.addWidget(display)

        redir = QGroupBox("Local devices")
        rform = QFormLayout(redir)
        self.rdp_clipboard = QCheckBox("Share clipboard")
        self.rdp_clipboard.setChecked(self.session.rdp_clipboard)
        self.rdp_drives = QCheckBox("Share local drives (file transfer)")
        self.rdp_drives.setChecked(self.session.rdp_drives)
        rform.addRow(self.rdp_clipboard)
        rform.addRow(self.rdp_drives)

        self.domain = QLineEdit(self.session.domain)
        rform.addRow("Domain", self.domain)
        layout.addWidget(redir)

        adv = QGroupBox("Security / gateway")
        aform = QFormLayout(adv)
        self.rdp_cert_ignore = QCheckBox("Accept any certificate (not recommended)")
        self.rdp_cert_ignore.setChecked(self.session.rdp_cert_ignore)
        self.rdp_pass_cmd = QCheckBox(
            "Pass vault password on FreeRDP command line (visible in `ps`; prompts otherwise)"
        )
        self.rdp_pass_cmd.setChecked(self.session.rdp_pass_on_cmdline)
        aform.addRow(self.rdp_cert_ignore)
        aform.addRow(self.rdp_pass_cmd)

        self.gw_host = QLineEdit(self.session.rdp_gateway_host)
        self.gw_port = QSpinBox()
        self.gw_port.setRange(1, 65535)
        self.gw_port.setValue(self.session.rdp_gateway_port or 443)
        self.gw_user = QLineEdit(self.session.rdp_gateway_user)
        gw = QHBoxLayout()
        gw.addWidget(self.gw_host, 2)
        gw.addWidget(self.gw_port, 1)
        gw.addWidget(self.gw_user, 2)
        aform.addRow("RD gateway host:port / user", gw)
        layout.addWidget(adv)
        layout.addStretch(1)
        return page

    def _build_local_page(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        self.local_cmd = QLineEdit(self.session.options.get("command", ""))
        self.local_cmd.setPlaceholderText("default: your login shell (bash / PowerShell)")
        form.addRow("Command", self.local_cmd)
        return page

    # ------------------------------------------------------------------
    def _on_protocol(self) -> None:
        pid = self.protocol.currentData()
        prev = self._last_pid
        self._last_pid = pid
        if prev and pid != prev:
            # protocol switched: if the port is still at the previous
            # protocol's default, move it to the new protocol's default
            # (22 ⇄ 3389); keep user-typed ports
            if self.port.value() == default_port_for(prev):
                self.port.setValue(default_port_for(pid))
        else:
            self.port.setValue(self.session.port or default_port_for(pid))
        is_local = pid == PROTOCOL_LOCAL
        self.host.setEnabled(not is_local)
        self.port.setEnabled(not is_local)
        self.username.setEnabled(not is_local)
        self.password.setEnabled(not is_local)
        widget = {
            PROTOCOL_SSH: self._ssh_page,
            PROTOCOL_RDP: self._rdp_page,
            PROTOCOL_LOCAL: self._local_page,
        }.get(pid, self._ssh_page)
        self.stack.setCurrentWidget(widget)

    def _on_auth(self) -> None:
        method = self.auth.currentData()
        self.credential.setEnabled(method in (AUTH_CREDENTIAL, AUTH_KEY))
        self.key_path.setEnabled(method == AUTH_KEY)

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        s = self.session
        s.protocol = self.protocol.currentData() or PROTOCOL_SSH
        s.name = self.name.text().strip()
        s.group = self.group.currentText().strip()
        s.host = self.host.text().strip()
        s.port = self.port.value()
        s.username = self.username.text().strip()
        s.password = self.password.text()
        s.description = self.description.text().strip()
        s.tags = [t for t in self.tags.text().replace(",", " ").split() if t]

        if s.protocol == PROTOCOL_SSH:
            s.auth = self.auth.currentData()
            s.credential_id = self.credential.currentData() or ""
            s.key_path = self.key_path.text().strip()
            s.jump_session_id = self.jump.currentData() or ""
            s.startup_command = self.startup.text()
            s.keepalive = self.keepalive.value()
            s.timeout = self.timeout.value()
            s.compression = self.compression.isChecked()
            s.auto_reconnect = self.auto_reconnect.isChecked()
            s.forwards = self.forwards.get_forwards()
        elif s.protocol == PROTOCOL_RDP:
            s.auth = self.auth.currentData()
            s.credential_id = self.credential.currentData() or ""
            s.domain = self.domain.text().strip()
            s.rdp_width = self.rdp_width.value()
            s.rdp_height = self.rdp_height.value()
            s.rdp_color_depth = self.rdp_bpp.currentData() or 32
            s.rdp_fullscreen = self.rdp_fullscreen.isChecked()
            s.rdp_fit_screen = self.rdp_fit_screen.isChecked()
            s.rdp_clipboard = self.rdp_clipboard.isChecked()
            s.rdp_drives = self.rdp_drives.isChecked()
            s.rdp_cert_ignore = self.rdp_cert_ignore.isChecked()
            s.rdp_pass_on_cmdline = self.rdp_pass_cmd.isChecked()
            s.rdp_gateway_host = self.gw_host.text().strip()
            s.rdp_gateway_port = self.gw_port.value()
            s.rdp_gateway_user = self.gw_user.text().strip()
            s.auto_reconnect = True
        else:  # local
            s.options["command"] = self.local_cmd.text().strip()

        if not s.name and s.protocol == PROTOCOL_LOCAL:
            s.name = "Local shell"
        if s.group:
            self.ctx.store.ensure_group(s.group)

        self.ctx.store.upsert(s)
        self.accept()


def icon_text(plugin) -> str:
    labels = {"ssh": "SSH terminal", "rdp": "RDP remote desktop", "local": "Local shell"}
    return labels.get(plugin.id, plugin.title)
