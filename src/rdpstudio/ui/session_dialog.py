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

# Offered in the RDP "Display" dropdown (16:9 / 16:10 ladder people recognise).
RDP_RESOLUTIONS = ((1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440))
_RDP_STEP = 8


def _display_mode_of(session: Session):
    """Map a stored session onto one of the simple Display choices."""
    if session.rdp_fullscreen:
        return "fullscreen"
    if session.rdp_fit_screen:
        return "fit"
    size = (session.rdp_width, session.rdp_height)
    return f"{size[0]}x{size[1]}" if size in RDP_RESOLUTIONS else "custom"


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

        # Widgets that only appear when "Advanced options" is expanded.
        self._advanced: list[QWidget] = []

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

        # --- advanced toggle -------------------------------------------------
        # Everything most people never touch (gateway, keepalives, colour
        # depth, forwards, …) is registered in ``self._advanced`` and hidden
        # until asked for, so the default dialog is username/password short.
        self.btn_advanced = QPushButton("Advanced options  ▸")
        self.btn_advanced.setFlat(True)
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setChecked(False)
        self.btn_advanced.toggled.connect(self._on_advanced)
        adv_row = QHBoxLayout()
        adv_row.addWidget(self.btn_advanced)
        adv_row.addStretch(1)
        root.addLayout(adv_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._on_advanced(False)

        idx = self.protocol.findData(self.session.protocol)
        if idx >= 0:
            self.protocol.setCurrentIndex(idx)
        self._on_protocol()

    # ------------------------------------------------------------------
    def _mark_advanced(self, *widgets: QWidget) -> None:
        """Register widgets to be shown only in advanced mode."""
        self._advanced.extend(w for w in widgets if w is not None)

    def _on_advanced(self, expanded: bool) -> None:
        self.btn_advanced.setText(
            "Advanced options  ▾" if expanded else "Advanced options  ▸"
        )
        for widget in self._advanced:
            widget.setVisible(expanded)
        # let the dialog shrink back down when collapsing
        self.adjustSize()

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
        self._port_label = QLabel("Port")
        form.addRow(self._port_label, self.port)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        self._desc_label = QLabel("Description")
        form.addRow(self._desc_label, self.description)
        self._tags_label = QLabel("Tags")
        form.addRow(self._tags_label, self.tags)
        # Host + username + password are the whole story for most sessions;
        # the rest only shows up under "Advanced options".
        self._mark_advanced(
            self._port_label, self.port,
            self._desc_label, self.description,
            self._tags_label, self.tags,
        )
        return page

    def _build_auth_box(self) -> QGroupBox:
        box = QGroupBox("Authentication")
        form = QFormLayout(box)
        self.auth = QComboBox()
        self.auth.addItem("Password (field above)", AUTH_PASSWORD)
        self.auth.addItem("Vault credential (optional)", AUTH_CREDENTIAL)
        self.auth.addItem("Private key", AUTH_KEY)
        self.auth.addItem("SSH agent", AUTH_AGENT)
        self._auth_label = QLabel("Method")
        form.addRow(self._auth_label, self.auth)

        self.credential = QComboBox()
        self._reload_credentials()
        self._credential_label = QLabel("Credential")
        form.addRow(self._credential_label, self.credential)

        self.key_path = QLineEdit(self.session.key_path)
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.addWidget(self.key_path, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_key)
        key_layout.addWidget(browse)
        self._key_label = QLabel("Key file")
        form.addRow(self._key_label, key_row)
        self._key_row = key_row

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
        # Jump hosts, keepalives, compression and port forwarding are
        # power-user territory — keep the default SSH form to auth only.
        self._mark_advanced(behaviour, fwd_box)
        return page

    def _build_rdp_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_auth_box())

        display = QGroupBox("Display")
        form = QFormLayout(display)

        # Simple path: one "Display" dropdown covering what people actually
        # pick, instead of two spinboxes + a colour-depth combo + 2 checkboxes.
        self.rdp_display_mode = QComboBox()
        self.rdp_display_mode.addItem("Fit to window (recommended)", "fit")
        self.rdp_display_mode.addItem("Fullscreen", "fullscreen")
        for w, h in RDP_RESOLUTIONS:
            # Data is a plain "WxH" string: QVariant round-tripping of Python
            # tuples through findData() is not reliable across bindings.
            self.rdp_display_mode.addItem(f"{w} × {h}", f"{w}x{h}")
        self.rdp_display_mode.addItem("Custom…", "custom")
        preset = self.rdp_display_mode.findData(_display_mode_of(self.session))
        self.rdp_display_mode.setCurrentIndex(preset if preset >= 0 else 0)
        self.rdp_display_mode.currentIndexChanged.connect(self._on_rdp_display_mode)
        form.addRow("Display", self.rdp_display_mode)

        # Custom size + colour depth: only shown for "Custom…" / advanced.
        self.rdp_width = QSpinBox()
        self.rdp_width.setRange(640, 7680)
        self.rdp_width.setSingleStep(_RDP_STEP)
        self.rdp_width.setValue(self.session.rdp_width)
        self.rdp_height = QSpinBox()
        self.rdp_height.setRange(480, 4320)
        self.rdp_height.setSingleStep(_RDP_STEP)
        self.rdp_height.setValue(self.session.rdp_height)
        self.rdp_bpp = QComboBox()
        for bpp in (16, 24, 32):
            self.rdp_bpp.addItem(f"{bpp}-bit colour", bpp)
        bi = self.rdp_bpp.findData(self.session.rdp_color_depth)
        self.rdp_bpp.setCurrentIndex(bi if bi >= 0 else 2)

        custom = QWidget()
        res = QHBoxLayout(custom)
        res.setContentsMargins(0, 0, 0, 0)
        res.addWidget(self.rdp_width)
        res.addWidget(QLabel("×"))
        res.addWidget(self.rdp_height)
        res.addSpacing(10)
        res.addWidget(self.rdp_bpp)
        res.addStretch(1)
        self._rdp_custom_label = QLabel("Size")
        form.addRow(self._rdp_custom_label, custom)
        self._rdp_custom = custom

        # Kept as real state (the rest of the app reads these) but driven by
        # the dropdown above rather than shown as separate checkboxes.
        self.rdp_fullscreen = QCheckBox("Fullscreen")
        self.rdp_fullscreen.setChecked(self.session.rdp_fullscreen)
        self.rdp_fullscreen.setVisible(False)
        self.rdp_fit_screen = QCheckBox("Fit display to screen")
        self.rdp_fit_screen.setChecked(self.session.rdp_fit_screen)
        self.rdp_fit_screen.setVisible(False)

        emb_note = QLabel(
            "The desktop renders inside this app when possible (Linux + X11 + FreeRDP)."
        )
        emb_note.setObjectName("muted")
        emb_note.setWordWrap(True)
        form.addRow(emb_note)
        layout.addWidget(display)
        self._mark_advanced(emb_note)

        redir = QGroupBox("Local devices")
        rform = QFormLayout(redir)
        self.rdp_clipboard = QCheckBox("Share clipboard")
        self.rdp_clipboard.setChecked(self.session.rdp_clipboard)
        self.rdp_drives = QCheckBox("Share local drives (file transfer)")
        self.rdp_drives.setChecked(self.session.rdp_drives)
        rform.addRow(self.rdp_clipboard)
        rform.addRow(self.rdp_drives)

        self.domain = QLineEdit(self.session.domain)
        self.domain.setPlaceholderText("optional (Active Directory domain)")
        self._domain_label = QLabel("Domain")
        rform.addRow(self._domain_label, self.domain)
        layout.addWidget(redir)
        self._mark_advanced(self._domain_label, self.domain)

        adv = QGroupBox("Security / gateway")
        aform = QFormLayout(adv)
        self.rdp_cert_ignore = QCheckBox("Accept any certificate (not recommended)")
        self.rdp_cert_ignore.setChecked(self.session.rdp_cert_ignore)
        self.rdp_pass_cmd = QCheckBox(
            "Pass password on the FreeRDP command line (insecure — visible to other "
            "local users in `ps`; by default it is sent over stdin)"
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
        # Certificates, cmdline-password opt-in and RD gateway: advanced only.
        self._mark_advanced(adv)
        self._on_rdp_display_mode()
        return page

    def _on_rdp_display_mode(self) -> None:
        """Sync the hidden fullscreen/fit/size state to the Display choice."""
        mode = self.rdp_display_mode.currentData()
        self.rdp_fullscreen.setChecked(mode == "fullscreen")
        self.rdp_fit_screen.setChecked(mode == "fit")
        if isinstance(mode, str) and "x" in mode:
            width, _, height = mode.partition("x")
            self.rdp_width.setValue(int(width))
            self.rdp_height.setValue(int(height))
        custom = mode == "custom"
        self._rdp_custom_label.setVisible(custom)
        self._rdp_custom.setVisible(custom)

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
        """Show only the fields the chosen auth method actually uses."""
        method = self.auth.currentData()
        wants_credential = method in (AUTH_CREDENTIAL, AUTH_KEY)
        wants_key = method == AUTH_KEY
        # Hide rather than grey out: an empty, irrelevant row is pure noise.
        self._credential_label.setVisible(wants_credential)
        self.credential.setVisible(wants_credential)
        self._key_label.setVisible(wants_key)
        self._key_row.setVisible(wants_key)
        self.credential.setEnabled(wants_credential)
        self.key_path.setEnabled(wants_key)
        # The plain password field is meaningless for key/agent auth.
        uses_password = method in (AUTH_PASSWORD, AUTH_CREDENTIAL)
        self.password.setEnabled(uses_password)
        self.password.setPlaceholderText(
            "leave empty to be asked at connect"
            if uses_password
            else "not used with this method"
        )

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
