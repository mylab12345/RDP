"""New/Edit session dialog — modern 2026 card-based design."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
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

RDP_RESOLUTIONS = ((1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440))
_RDP_STEP = 8


def _display_mode_of(session: Session):
    if session.rdp_fullscreen:
        return "fullscreen"
    if session.rdp_fit_screen:
        return "fit"
    size = (session.rdp_width, session.rdp_height)
    return f"{size[0]}x{size[1]}" if size in RDP_RESOLUTIONS else "custom"


class SessionDialog(QDialog):
    """Create or edit a saved session — modern."""

    def __init__(self, ctx: SessionContext, session: Session | None = None, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.session = session or Session(protocol=PROTOCOL_SSH)
        self.is_new = session is None
        if self.is_new:
            self.session.port = default_port_for(self.session.protocol)
        self.setWindowTitle("New session" if self.is_new else f"Edit “{self.session.display_name()}”")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)
        self.resize(680, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)

        # Title
        title_row = QHBoxLayout()
        title_label = QLabel("New Session" if self.is_new else "Edit Session")
        title_label.setObjectName("h1")
        title_row.addWidget(title_label)
        title_row.addStretch(1)
        root.addLayout(title_row)

        # Subtitle
        subtitle = QLabel("Connect to a remote host via SSH or RDP. Credentials can be saved or asked at connect time.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self._advanced: list[QWidget] = []

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(2, 2, 8, 2)
        scroll_layout.setSpacing(16)

        # Header card: protocol + name/group
        header_card = self._make_card("General")
        header_content = self._card_content(header_card)
        head = QFormLayout(header_content)
        head.setSpacing(12)
        head.setContentsMargins(16, 16, 16, 16)
        self.protocol = QComboBox()
        for plugin in registry().editable():
            self.protocol.addItem(icon_text(plugin), plugin.id)
        self.name = QLineEdit(self.session.name)
        self.name.setPlaceholderText("e.g. Production Web, My Windows PC")
        self.group = QComboBox()
        self.group.setEditable(True)
        for g in ctx.store.groups():
            self.group.addItem(g)
        self.group.setCurrentText(self.session.group)
        self.group.setPlaceholderText("Folder (optional)")
        head.addRow("Protocol", self.protocol)
        head.addRow("Name", self.name)
        head.addRow("Folder", self.group)
        scroll_layout.addWidget(header_card)

        # Common connection card
        common_card = self._make_card("Connection")
        common_content = self._card_content(common_card)
        common_layout = QVBoxLayout(common_content)
        common_layout.setContentsMargins(16, 16, 16, 16)
        common_layout.addWidget(self._build_common())
        scroll_layout.addWidget(common_card)

        # Protocol-specific stacked
        self.stack = QStackedWidget()
        scroll_layout.addWidget(self.stack, 1)

        # Each protocol page owns its own auth widgets; saving reads the set
        # belonging to the selected protocol. (A single shared set would let
        # one page's combo shadow the other's and silently drop user input.)
        self._auth_ui: dict[str, dict] = {}
        self._ssh_page = self._build_ssh_page()
        self.stack.addWidget(self._ssh_page)
        self._rdp_page = self._build_rdp_page()
        self.stack.addWidget(self._rdp_page)
        self._local_page = self._build_local_page()
        self.stack.addWidget(self._local_page)

        self._last_pid: str | None = None
        self.protocol.currentIndexChanged.connect(self._on_protocol)

        scroll.setWidget(scroll_content)
        root.addWidget(scroll, 1)

        # Advanced toggle — modern ghost button
        self.btn_advanced = QPushButton("Advanced options  ▸")
        self.btn_advanced.setObjectName("ghost")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setChecked(False)
        self.btn_advanced.toggled.connect(self._on_advanced)
        adv_row = QHBoxLayout()
        adv_row.addWidget(self.btn_advanced)
        adv_row.addStretch(1)
        root.addLayout(adv_row)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        root.addWidget(line)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.setObjectName("primary")
        save_btn.setText("Save Session")
        save_btn.setMinimumHeight(36)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setObjectName("subtle")
        cancel_btn.setMinimumHeight(36)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._on_advanced(False)

        idx = self.protocol.findData(self.session.protocol)
        if idx >= 0:
            self.protocol.setCurrentIndex(idx)
        self._on_protocol()

    def _make_card(self, title: str) -> QWidget:
        """Create a modern card with title — returns the card itself."""
        card = QWidget()
        card.setObjectName("card")
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        if title:
            header = QLabel(title)
            header.setObjectName("h2")
            header.setContentsMargins(16, 12, 16, 8)
            outer.addWidget(header)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("hairline")
            sep.setFixedHeight(1)
            outer.addWidget(sep)
        # content area where caller will add its own layout
        content = QWidget()
        outer.addWidget(content)
        # Store content as attribute so caller can add layout to it,
        # but return card so card is added to parent layout (not orphaned).
        card._content_widget = content  # type: ignore[attr-defined]
        return card

    def _card_content(self, card: QWidget) -> QWidget:
        """Get the inner content widget of a card."""
        return getattr(card, "_content_widget", card)

    # Keep original card method for compatibility but wrap
    def _make_card_simple(self) -> QGroupBox:
        box = QGroupBox()
        return box

    def _mark_advanced(self, *widgets: QWidget) -> None:
        self._advanced.extend(w for w in widgets if w is not None)

    def _on_advanced(self, expanded: bool) -> None:
        self.btn_advanced.setText(
            "Advanced options  ▾" if expanded else "Advanced options  ▸"
        )
        for widget in self._advanced:
            widget.setVisible(expanded)
        self.adjustSize()

    def _build_common(self) -> QWidget:
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(12)
        self.host = QLineEdit(self.session.host)
        self.host.setPlaceholderText("hostname or IP, e.g. 10.0.0.5 or web.example.com")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(self.session.port or 22)
        self.username = QLineEdit(self.session.username)
        self.username.setPlaceholderText("e.g. root, ubuntu, administrator")
        self.password = QLineEdit(self.session.password)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("leave empty to be asked at connect")
        self.description = QLineEdit(self.session.description)
        self.description.setPlaceholderText("Optional description")
        self.tags = QLineEdit(" ".join(self.session.tags))
        self.tags.setPlaceholderText("prod, web, db…")

        form.addRow("Host", self.host)
        self._port_label = QLabel("Port")
        form.addRow(self._port_label, self.port)
        form.addRow("Username", self.username)
        form.addRow("Password", self.password)
        self._desc_label = QLabel("Description")
        form.addRow(self._desc_label, self.description)
        self._tags_label = QLabel("Tags")
        form.addRow(self._tags_label, self.tags)
        self._mark_advanced(
            self._port_label, self.port,
            self._desc_label, self.description,
            self._tags_label, self.tags,
        )
        return page

    def _build_auth_box(self, protocol: str) -> QGroupBox:
        box = QGroupBox("Authentication")
        form = QFormLayout(box)
        form.setSpacing(10)
        auth = QComboBox()
        auth.addItem("Password", AUTH_PASSWORD)
        auth.addItem("Vault credential", AUTH_CREDENTIAL)
        auth.addItem("Private key", AUTH_KEY)
        auth.addItem("SSH agent", AUTH_AGENT)
        auth_label = QLabel("Method")
        form.addRow(auth_label, auth)

        credential = QComboBox()
        credential_label = QLabel("Credential")
        form.addRow(credential_label, credential)

        key_path = QLineEdit(self.session.key_path)
        key_path.setPlaceholderText("~/.ssh/id_ed25519")
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)
        key_layout.addWidget(key_path, 1)
        browse = QPushButton("Browse…")
        browse.setObjectName("subtle")
        browse.clicked.connect(lambda _=False, edit=key_path: self._browse_key(edit))
        key_layout.addWidget(browse)
        key_label = QLabel("Key file")
        form.addRow(key_label, key_row)

        self._auth_ui[protocol] = {
            "auth": auth,
            "credential": credential,
            "key_path": key_path,
            "auth_label": auth_label,
            "credential_label": credential_label,
            "key_label": key_label,
            "key_row": key_row,
        }

        auth.currentIndexChanged.connect(lambda _=0, p=protocol: self._on_auth(p))
        idx = auth.findData(self.session.auth or AUTH_PASSWORD)
        auth.setCurrentIndex(idx if idx >= 0 else 0)
        if self.session.credential_id:
            ci = credential.findData(self.session.credential_id)
            if ci >= 0:
                credential.setCurrentIndex(ci)
        self._reload_credentials_into(credential)
        self._on_auth(protocol)
        return box

    def _current_auth_ui(self, protocol: str | None = None) -> dict:
        pid = protocol or self.protocol.currentData() or PROTOCOL_SSH
        return self._auth_ui.get(pid, self._auth_ui[PROTOCOL_SSH])

    def _reload_credentials(self) -> None:
        for ui in self._auth_ui.values():
            self._reload_credentials_into(ui["credential"])

    def _reload_credentials_into(self, combo: QComboBox) -> None:
        current = combo.currentData()
        combo.clear()
        combo.addItem("— none —", "")
        try:
            for cred in self.ctx.vault.entries():
                label = cred.name or cred.id
                if cred.username:
                    label += f" ({cred.username})"
                combo.addItem(label, cred.id)
        except Exception:
            pass
        if current:
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _browse_key(self, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose private key", "", "Keys (*)")
        if path:
            edit.setText(path)

    def _build_ssh_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._build_auth_box(PROTOCOL_SSH))

        behaviour = QGroupBox("Session behaviour")
        form = QFormLayout(behaviour)
        form.setSpacing(10)
        self.jump = QComboBox()
        self.jump.addItem("— none —", "")
        for s in self.ctx.store.sessions():
            if s.protocol == PROTOCOL_SSH and s.id != self.session.id:
                self.jump.addItem(s.display_name(), s.id)
        if self.session.jump_session_id:
            ji = self.jump.findData(self.session.jump_session_id)
            if ji >= 0:
                self.jump.setCurrentIndex(ji)
        form.addRow("Jump host", self.jump)

        self.startup = QLineEdit(self.session.startup_command)
        self.startup.setPlaceholderText("e.g. sudo -i")
        form.addRow("Startup command", self.startup)

        row = QHBoxLayout()
        row.setSpacing(12)
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

        fwd_box = QGroupBox("Port forwarding")
        fl = QVBoxLayout(fwd_box)
        self.forwards = ForwardListEditor()
        self.forwards.set_forwards(self.session.forwards)
        fl.addWidget(self.forwards)
        layout.addWidget(fwd_box)
        layout.addStretch(1)
        self._mark_advanced(behaviour, fwd_box)
        return page

    def _build_rdp_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._build_auth_box(PROTOCOL_RDP))

        display = QGroupBox("Display")
        form = QFormLayout(display)
        form.setSpacing(10)

        self.rdp_display_mode = QComboBox()
        self.rdp_display_mode.addItem("Fit to window (recommended)", "fit")
        self.rdp_display_mode.addItem("Fullscreen", "fullscreen")
        for w, h in RDP_RESOLUTIONS:
            self.rdp_display_mode.addItem(f"{w} × {h}", f"{w}x{h}")
        self.rdp_display_mode.addItem("Custom…", "custom")
        preset = self.rdp_display_mode.findData(_display_mode_of(self.session))
        self.rdp_display_mode.setCurrentIndex(preset if preset >= 0 else 0)
        self.rdp_display_mode.currentIndexChanged.connect(self._on_rdp_display_mode)
        form.addRow("Display", self.rdp_display_mode)

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
            self.rdp_bpp.addItem(f"{bpp}-bit", bpp)
        bi = self.rdp_bpp.findData(self.session.rdp_color_depth)
        self.rdp_bpp.setCurrentIndex(bi if bi >= 0 else 2)

        custom = QWidget()
        res = QHBoxLayout(custom)
        res.setContentsMargins(0, 0, 0, 0)
        res.setSpacing(8)
        res.addWidget(self.rdp_width)
        res.addWidget(QLabel("×"))
        res.addWidget(self.rdp_height)
        res.addSpacing(10)
        res.addWidget(self.rdp_bpp)
        res.addStretch(1)
        self._rdp_custom_label = QLabel("Size")
        form.addRow(self._rdp_custom_label, custom)
        self._rdp_custom = custom

        self.rdp_fullscreen = QCheckBox("Fullscreen")
        self.rdp_fullscreen.setChecked(self.session.rdp_fullscreen)
        self.rdp_fullscreen.setVisible(False)
        self.rdp_fit_screen = QCheckBox("Fit display to screen")
        self.rdp_fit_screen.setChecked(self.session.rdp_fit_screen)
        self.rdp_fit_screen.setVisible(False)

        emb_note = QLabel("The desktop renders inside this app when possible (Linux + X11 + FreeRDP).")
        emb_note.setObjectName("muted")
        emb_note.setWordWrap(True)
        form.addRow(emb_note)
        layout.addWidget(display)
        self._mark_advanced(emb_note)

        redir = QGroupBox("Local devices")
        rform = QFormLayout(redir)
        rform.setSpacing(10)
        self.rdp_clipboard = QCheckBox("Share clipboard")
        self.rdp_clipboard.setChecked(self.session.rdp_clipboard)
        self.rdp_drives = QCheckBox("Share local drives")
        self.rdp_drives.setChecked(self.session.rdp_drives)
        rform.addRow(self.rdp_clipboard)
        rform.addRow(self.rdp_drives)

        self.domain = QLineEdit(self.session.domain)
        self.domain.setPlaceholderText("optional AD domain")
        self._domain_label = QLabel("Domain")
        rform.addRow(self._domain_label, self.domain)
        layout.addWidget(redir)
        self._mark_advanced(self._domain_label, self.domain)

        adv = QGroupBox("Security / gateway")
        aform = QFormLayout(adv)
        aform.setSpacing(10)
        self.rdp_cert_ignore = QCheckBox("Accept any certificate (not recommended)")
        self.rdp_cert_ignore.setChecked(self.session.rdp_cert_ignore)
        self.rdp_pass_cmd = QCheckBox("Pass password on FreeRDP command line (insecure)")
        self.rdp_pass_cmd.setChecked(self.session.rdp_pass_on_cmdline)
        aform.addRow(self.rdp_cert_ignore)
        aform.addRow(self.rdp_pass_cmd)

        self.gw_host = QLineEdit(self.session.rdp_gateway_host)
        self.gw_host.setPlaceholderText("gateway host")
        self.gw_port = QSpinBox()
        self.gw_port.setRange(1, 65535)
        self.gw_port.setValue(self.session.rdp_gateway_port or 443)
        self.gw_user = QLineEdit(self.session.rdp_gateway_user)
        self.gw_user.setPlaceholderText("gateway user")
        gw = QHBoxLayout()
        gw.setSpacing(8)
        gw.addWidget(self.gw_host, 2)
        gw.addWidget(self.gw_port, 1)
        gw.addWidget(self.gw_user, 2)
        aform.addRow("RD gateway", gw)
        layout.addWidget(adv)
        layout.addStretch(1)
        self._mark_advanced(adv)
        self._on_rdp_display_mode()
        return page

    def _on_rdp_display_mode(self) -> None:
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
        form.setSpacing(12)
        self.local_cmd = QLineEdit(self.session.options.get("command", ""))
        self.local_cmd.setPlaceholderText("default: your login shell (bash / PowerShell)")
        form.addRow("Command", self.local_cmd)
        return page

    def _on_protocol(self) -> None:
        pid = self.protocol.currentData()
        prev = self._last_pid
        self._last_pid = pid
        if prev and pid != prev:
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

    def _on_auth(self, protocol: str | None = None) -> None:
        ui = self._current_auth_ui(protocol)
        method = ui["auth"].currentData()
        wants_credential = method in (AUTH_CREDENTIAL, AUTH_KEY)
        wants_key = method == AUTH_KEY
        ui["credential_label"].setVisible(wants_credential)
        ui["credential"].setVisible(wants_credential)
        ui["key_label"].setVisible(wants_key)
        ui["key_row"].setVisible(wants_key)
        ui["credential"].setEnabled(wants_credential)
        ui["key_path"].setEnabled(wants_key)
        uses_password = method in (AUTH_PASSWORD, AUTH_CREDENTIAL)
        self.password.setEnabled(uses_password)
        self.password.setPlaceholderText(
            "leave empty to be asked at connect"
            if uses_password
            else "not used with this method"
        )

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

        # The local-shell page has no auth widgets; only ssh/rdp do.
        auth_ui = (
            self._current_auth_ui(s.protocol)
            if s.protocol in (PROTOCOL_SSH, PROTOCOL_RDP)
            else None
        )
        if s.protocol == PROTOCOL_SSH:
            s.auth = auth_ui["auth"].currentData()
            s.credential_id = auth_ui["credential"].currentData() or ""
            s.key_path = auth_ui["key_path"].text().strip()
            s.jump_session_id = self.jump.currentData() or ""
            s.startup_command = self.startup.text()
            s.keepalive = self.keepalive.value()
            s.timeout = self.timeout.value()
            s.compression = self.compression.isChecked()
            s.auto_reconnect = self.auto_reconnect.isChecked()
            s.forwards = self.forwards.get_forwards()
        elif s.protocol == PROTOCOL_RDP:
            s.auth = auth_ui["auth"].currentData()
            s.credential_id = auth_ui["credential"].currentData() or ""
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
        else:
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
