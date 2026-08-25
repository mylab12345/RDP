"""New/Edit session dialog — modern 2026 bento-card design."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
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
    AUTH_KEY,
    AUTH_PASSWORD,
    PROTOCOL_LOCAL,
    PROTOCOL_RDP,
    PROTOCOL_SSH,
    Session,
    default_port_for,
)
from ..core.plugin import SessionContext, registry

RDP_RESOLUTIONS = ((1280, 720), (1366, 768), (1600, 900), (1920, 1080), (2560, 1440))
_RDP_STEP = 8


def _display_mode_of(session: Session):
    if session.rdp_fullscreen:
        return "fullscreen"
    if session.rdp_fit_screen:
        return "fit"
    size = (session.rdp_width, session.rdp_height)
    return f"{size[0]}x{size[1]}" if size in RDP_RESOLUTIONS else "custom"


_INVALID_STYLE = "border: 1px solid {bad};"
_VALID_STYLE = "border: 1px solid {border};"


class SessionDialog(QDialog):
    """Create or edit a saved session — modern bento-card design."""

    def __init__(self, ctx: SessionContext, session: Session | None = None, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.session = session or Session(protocol=PROTOCOL_SSH)
        self.is_new = session is None
        if self.is_new:
            self.session.port = default_port_for(self.session.protocol)
        self.setWindowTitle("New session" if self.is_new else f"Edit \u201c{self.session.display_name()}\u201d")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setMinimumHeight(560)
        self.resize(680, 780)

        from .theme import palette as theme_palette
        self._pal = theme_palette()

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)

        title_row = QHBoxLayout()
        title_label = QLabel("New Session" if self.is_new else "Edit Session")
        title_label.setObjectName("h1")
        title_row.addWidget(title_label)
        title_row.addStretch(1)
        root.addLayout(title_row)

        subtitle = QLabel("Configure your remote connection. Fields can be left blank to prompt at connect time.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        self._advanced: list[QWidget] = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(2, 2, 8, 2)
        scroll_layout.setSpacing(16)

        header_card = self._make_card("General")
        header_content = self._card_content(header_card)
        head = QFormLayout(header_content)
        head.setSpacing(12)
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

        conn_card = self._make_card("Connection")
        conn_content = self._card_content(conn_card)
        conn_layout = QVBoxLayout(conn_content)
        conn_layout.setContentsMargins(16, 16, 16, 16)
        conn_layout.setSpacing(12)
        self._build_connection(conn_layout)
        scroll_layout.addWidget(conn_card)

        self.stack = QStackedWidget()
        scroll_layout.addWidget(self.stack, 1)

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

        self.btn_advanced = QPushButton("Advanced options  \u25b8")
        self.btn_advanced.setObjectName("ghost")
        self.btn_advanced.setCheckable(True)
        self.btn_advanced.setChecked(False)
        self.btn_advanced.toggled.connect(self._on_advanced)
        adv_row = QHBoxLayout()
        adv_row.addWidget(self.btn_advanced)
        adv_row.addStretch(1)
        root.addLayout(adv_row)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        root.addWidget(line)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_left = QHBoxLayout()
        btn_left.setSpacing(8)
        btn_right = QHBoxLayout()
        btn_right.setSpacing(8)

        self.btn_test = QPushButton("Test")
        self.btn_test.setMinimumHeight(36)
        self.btn_test.setObjectName("ghost")
        self.btn_test.clicked.connect(self._on_test)
        btn_left.addWidget(self.btn_test)

        self.btn_save = QPushButton("Save")
        self.btn_save.setMinimumHeight(36)
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self._on_save)
        btn_left.addWidget(self.btn_save)

        btn_left.addStretch(1)

        if not self.is_new:
            self.btn_delete = QPushButton("Delete")
            self.btn_delete.setMinimumHeight(36)
            self.btn_delete.setObjectName("danger")
            self.btn_delete.clicked.connect(self._on_delete)
            btn_right.addWidget(self.btn_delete)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setMinimumHeight(36)
        self.btn_connect.setObjectName("accent")
        self.btn_connect.clicked.connect(self._on_connect)
        btn_right.addWidget(self.btn_connect)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setMinimumHeight(36)
        self.btn_cancel.setObjectName("subtle")
        self.btn_cancel.clicked.connect(self.reject)
        btn_right.addWidget(self.btn_cancel)

        btn_row.addLayout(btn_left)
        btn_row.addLayout(btn_right)
        root.addLayout(btn_row)

        self._apply_button_styles()

        self._on_advanced(False)

        idx = self.protocol.findData(self.session.protocol)
        if idx >= 0:
            self.protocol.setCurrentIndex(idx)
        self._on_protocol()

    # ------------------------------------------------------------------
    # Card helpers
    # ------------------------------------------------------------------

    def _make_card(self, title: str) -> QWidget:
        card = QWidget()
        card.setObjectName("card")
        br = 14
        card.setStyleSheet(
            f"QWidget#card {{ background: {self._pal['bg2']}; "
            f"border: 1px solid {self._pal['border']}; "
            f"border-radius: {br}px; }}"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        if title:
            header = QWidget()
            header.setStyleSheet(
                f"background: {self._pal['panel']}; "
                f"border-top-left-radius: {br}px; border-top-right-radius: {br}px;"
            )
            hl = QHBoxLayout(header)
            hl.setContentsMargins(18, 10, 18, 10)
            dot = QLabel("\u25c9")
            dot.setStyleSheet(f"color: {self._pal['accent']}; font-size: 10px;")
            hl.addWidget(dot)
            lbl = QLabel(title)
            lbl.setObjectName("h2")
            lbl.setStyleSheet(
                f"font-size: 12.5px; font-weight: 700; letter-spacing: 0.6px; "
                f"color: {self._pal['fg']};"
            )
            hl.addWidget(lbl)
            hl.addStretch(1)
            outer.addWidget(header)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setObjectName("hairline")
            sep.setFixedHeight(1)
            outer.addWidget(sep)
        content = QWidget()
        outer.addWidget(content)
        card._content_widget = content  # type: ignore[attr-defined]
        return card

    def _card_content(self, card: QWidget) -> QWidget:
        return getattr(card, "_content_widget", card)

    def _mark_advanced(self, *widgets: QWidget) -> None:
        self._advanced.extend(w for w in widgets if w is not None)

    def _on_advanced(self, expanded: bool) -> None:
        self.btn_advanced.setText(
            "Advanced options  \u25be" if expanded else "Advanced options  \u25b8"
        )
        for widget in self._advanced:
            widget.setVisible(expanded)
        self.adjustSize()

    # ------------------------------------------------------------------
    # Styled input helpers
    # ------------------------------------------------------------------

    def _make_input(self, text: str = "", placeholder: str = "") -> QLineEdit:
        le = QLineEdit(text)
        le.setPlaceholderText(placeholder)
        le.setMinimumHeight(34)
        le.setStyleSheet(
            f"QLineEdit {{ font-size: 13px; padding: 6px 10px; "
            f"border: 1px solid {self._pal['border']}; border-radius: 8px; "
            f"background: {self._pal['bg3']}; color: {self._pal['fg']}; }}"
            f"QLineEdit:focus {{ border-color: {self._pal['accent']}; }}"
            f"QLineEdit:disabled {{ color: {self._pal['fg_muted']}; "
            f"background: {self._pal['bg2']}; border-color: {self._pal['border_subtle']}; }}"
        )
        return le

    def _make_spinbox(self, value: int, lo: int = 0, hi: int = 65535, suffix: str = "") -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(value)
        sb.setMinimumHeight(34)
        if suffix:
            sb.setSuffix(suffix)
        sb.setStyleSheet(
            f"QSpinBox {{ font-size: 13px; padding: 6px 10px; "
            f"border: 1px solid {self._pal['border']}; border-radius: 8px; "
            f"background: {self._pal['bg3']}; color: {self._pal['fg']}; }}"
            f"QSpinBox:focus {{ border-color: {self._pal['accent']}; }}"
            f"QSpinBox:disabled {{ color: {self._pal['fg_muted']}; "
            f"background: {self._pal['bg2']}; border-color: {self._pal['border_subtle']}; }}"
        )
        return sb

    def _make_combo(self) -> QComboBox:
        cb = QComboBox()
        cb.setMinimumHeight(34)
        cb.setStyleSheet(
            f"QComboBox {{ font-size: 13px; padding: 6px 10px; "
            f"border: 1px solid {self._pal['border']}; border-radius: 8px; "
            f"background: {self._pal['bg3']}; color: {self._pal['fg']}; }}"
            f"QComboBox:focus {{ border-color: {self._pal['accent']}; }}"
            f"QComboBox::drop-down {{ border: none; width: 28px; }}"
            f"QComboBox::down-arrow {{ image: none; border-left: 4px solid transparent; "
            f"border-right: 4px solid transparent; border-top: 5px solid {self._pal['fg_dim']}; "
            f"margin-right: 8px; }}"
            f"QComboBox QAbstractItemView {{ background: {self._pal['bg2']}; color: {self._pal['fg']}; "
            f"border: 1px solid {self._pal['border']}; border-radius: 6px; "
            f"selection-background-color: {self._pal['accent_subtle']}; padding: 4px; }}"
        )
        return cb

    def _make_checkbox(self, text: str, checked: bool = False) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(checked)
        cb.setStyleSheet(
            f"QCheckBox {{ font-size: 13px; color: {self._pal['fg']}; spacing: 8px; }}"
            f"QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; "
            f"border: 1px solid {self._pal['border']}; background: {self._pal['bg3']}; }}"
            f"QCheckBox::indicator:checked {{ background: {self._pal['accent']}; "
            f"border-color: {self._pal['accent']}; }}"
            f"QCheckBox::indicator:hover {{ border-color: {self._pal['accent']}; }}"
        )
        return cb

    def _make_label(self, text: str, size: float = 11.5) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: {size}px; color: {self._pal['fg_dim']}; font-weight: 600;")
        return lbl

    def _apply_button_styles(self) -> None:
        p = self._pal
        for btn in self.findChildren(QPushButton):
            obj = btn.objectName()
            if obj == "primary":
                btn.setStyleSheet(
                    f"QPushButton {{ background: {p['panel2']}; color: {p['fg']}; border: 1px solid {p['border']}; "
                    f"border-radius: 8px; font-size: 13px; font-weight: 600; padding: 8px 18px; }}"
                    f"QPushButton:hover {{ background: {p['panel3']}; border-color: {p['border_strong']}; }}"
                    f"QPushButton:pressed {{ background: {p['border']}; }}"
                )
            elif obj == "accent":
                btn.setStyleSheet(
                    f"QPushButton {{ background: {p['accent']}; color: {p['accent_text']}; border: none; "
                    f"border-radius: 8px; font-size: 13px; font-weight: 700; padding: 8px 22px; }}"
                    f"QPushButton:hover {{ background: {p['accent_hover']}; }}"
                    f"QPushButton:pressed {{ background: {p['accent_active']}; }}"
                )
            elif obj == "danger":
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {p['bad']}; border: 1px solid {p['bad']}; "
                    f"border-radius: 8px; font-size: 13px; font-weight: 600; padding: 8px 18px; }}"
                    f"QPushButton:hover {{ background: {p['bad']}18; }}"
                    f"QPushButton:pressed {{ background: {p['bad']}30; }}"
                )
            elif obj == "ghost":
                btn.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {p['fg_dim']}; border: none; "
                    f"font-size: 12.5px; font-weight: 600; padding: 6px 10px; }}"
                    f"QPushButton:hover {{ color: {p['fg']}; }}"
                )
            elif obj == "subtle":
                btn.setStyleSheet(
                    f"QPushButton {{ background: {p['bg3']}; color: {p['fg_dim']}; border: 1px solid {p['border']}; "
                    f"border-radius: 8px; font-size: 13px; padding: 8px 18px; }}"
                    f"QPushButton:hover {{ background: {p['panel2']}; color: {p['fg']}; }}"
                )

    # ------------------------------------------------------------------
    # Connection card fields
    # ------------------------------------------------------------------

    def _build_connection(self, parent: QVBoxLayout) -> None:
        row1 = QHBoxLayout()
        row1.setSpacing(12)

        host_col = QVBoxLayout()
        host_col.setSpacing(4)
        host_col.addWidget(self._make_label("Host / IP"))
        self.host = self._make_input(self.session.host, "10.0.0.5 or web.example.com")
        host_col.addWidget(self.host)
        row1.addLayout(host_col, 3)

        self._port_widget = QWidget()
        port_col = QVBoxLayout(self._port_widget)
        port_col.setContentsMargins(0, 0, 0, 0)
        port_col.setSpacing(4)
        port_col.addWidget(self._make_label("Port"))
        self.port = self._make_spinbox(self.session.port or 22, 1, 65535)
        port_col.addWidget(self.port)
        row1.addWidget(self._port_widget)
        self._port_widget.hide()
        self._mark_advanced(self._port_widget)

        parent.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)

        user_col = QVBoxLayout()
        user_col.setSpacing(4)
        user_col.addWidget(self._make_label("Username"))
        self.username = self._make_input(self.session.username, "root, ubuntu, administrator")
        user_col.addWidget(self.username)
        row2.addLayout(user_col, 1)

        pw_col = QVBoxLayout()
        pw_col.setSpacing(4)
        pw_col.addWidget(self._make_label("Password"))
        pw_wrap = QHBoxLayout()
        pw_wrap.setSpacing(0)
        self.password = self._make_input(self.session.password, "leave blank to prompt at connect")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        pw_wrap.addWidget(self.password)
        self._pw_toggle = QPushButton("\u25ce")
        self._pw_toggle.setCheckable(True)
        self._pw_toggle.setFixedSize(34, 34)
        self._pw_toggle.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {self._pal['fg_dim']}; border: none; "
            f"font-size: 15px; border-left: 1px solid {self._pal['border']}; border-radius: 0px; "
            f"border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}"
            f"QPushButton:hover {{ color: {self._pal['fg']}; }}"
        )
        self._pw_toggle.toggled.connect(self._toggle_password)
        pw_wrap.addWidget(self._pw_toggle)
        pw_col.addLayout(pw_wrap)
        row2.addLayout(pw_col, 1)

        parent.addLayout(row2)

        self._domain_widget = QWidget()
        domain_h = QHBoxLayout(self._domain_widget)
        domain_h.setContentsMargins(0, 0, 0, 0)
        domain_h.setSpacing(12)
        domain_col = QVBoxLayout()
        domain_col.setSpacing(4)
        self._domain_lbl = self._make_label("Domain")
        domain_col.addWidget(self._domain_lbl)
        self.domain = self._make_input(self.session.domain, "optional AD domain")
        domain_col.addWidget(self.domain)
        domain_h.addLayout(domain_col, 1)
        domain_h.addStretch(1)
        parent.addWidget(self._domain_widget)
        self._mark_advanced(self._domain_widget)

        row3 = QHBoxLayout()
        row3.setSpacing(12)
        desc_col = QVBoxLayout()
        desc_col.setSpacing(4)
        self._desc_lbl = self._make_label("Description")
        desc_col.addWidget(self._desc_lbl)
        self.description = self._make_input(self.session.description, "optional")
        desc_col.addWidget(self.description)
        row3.addLayout(desc_col, 1)

        tags_col = QVBoxLayout()
        tags_col.setSpacing(4)
        self._tags_lbl = self._make_label("Tags")
        tags_col.addWidget(self._tags_lbl)
        self.tags = self._make_input(" ".join(self.session.tags), "prod, web, db\u2026")
        tags_col.addWidget(self.tags)
        row3.addLayout(tags_col, 1)

        parent.addLayout(row3)
        self._mark_advanced(self._desc_lbl, self.description, self._tags_lbl, self.tags)

    def _toggle_password(self, visible: bool) -> None:
        self.password.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )

    # ------------------------------------------------------------------
    # Auth box (SSH / RDP)
    # ------------------------------------------------------------------

    def _build_auth_box(self, protocol: str) -> QGroupBox:
        card = self._make_card("Authentication")
        content = self._card_content(card)
        form = QFormLayout(content)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        auth = self._make_combo()
        auth.addItem("Password", AUTH_PASSWORD)
        auth.addItem("Private key", AUTH_KEY)
        auth.addItem("SSH agent", AUTH_AGENT)
        auth_label = self._make_label("Method")
        form.addRow(auth_label, auth)

        credential = self._make_combo()
        credential_label = self._make_label("Credential")
        form.addRow(credential_label, credential)

        key_path = self._make_input(self.session.key_path, "~/.ssh/id_ed25519")
        key_row = QWidget()
        key_layout = QHBoxLayout(key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)
        key_layout.addWidget(key_path, 1)
        browse = QPushButton("Browse\u2026")
        browse.setObjectName("subtle")
        browse.clicked.connect(lambda _=False, edit=key_path: self._browse_key(edit))
        key_layout.addWidget(browse)
        key_label = self._make_label("Key file")
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
        return card

    def _current_auth_ui(self, protocol: str | None = None) -> dict:
        pid = protocol or self.protocol.currentData() or PROTOCOL_SSH
        return self._auth_ui.get(pid, self._auth_ui[PROTOCOL_SSH])

    def _reload_credentials(self) -> None:
        for ui in self._auth_ui.values():
            self._reload_credentials_into(ui["credential"])

    def _reload_credentials_into(self, combo: QComboBox) -> None:
        current = combo.currentData()
        combo.clear()
        combo.addItem("\u2014 none \u2014", "")
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

    # ------------------------------------------------------------------
    # SSH page
    # ------------------------------------------------------------------

    def _build_ssh_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._build_auth_box(PROTOCOL_SSH))

        beh_card = self._make_card("Session behaviour")
        beh_content = self._card_content(beh_card)
        form = QFormLayout(beh_content)
        form.setSpacing(10)
        form.setContentsMargins(16, 16, 16, 16)

        self.jump = self._make_combo()
        self.jump.addItem("\u2014 none \u2014", "")
        for s in self.ctx.store.sessions():
            if s.protocol == PROTOCOL_SSH and s.id != self.session.id:
                self.jump.addItem(s.display_name(), s.id)
        if self.session.jump_session_id:
            ji = self.jump.findData(self.session.jump_session_id)
            if ji >= 0:
                self.jump.setCurrentIndex(ji)
        form.addRow(self._make_label("Jump host"), self.jump)

        self.startup = self._make_input(self.session.startup_command, "e.g. sudo -i")
        form.addRow(self._make_label("Startup command"), self.startup)

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(self._make_label("Keepalive"))
        self.keepalive = self._make_spinbox(self.session.keepalive or 30, 5, 300, " s")
        row.addWidget(self.keepalive)
        row.addWidget(self._make_label("Timeout"))
        self.timeout = self._make_spinbox(self.session.timeout or 10, 3, 120, " s")
        row.addWidget(self.timeout)
        row.addStretch(1)
        form.addRow(row)

        self.compression = self._make_checkbox("Compression", self.session.compression)
        self.auto_reconnect = self._make_checkbox("Auto-reconnect", self.session.auto_reconnect)
        check_row = QHBoxLayout()
        check_row.addWidget(self.compression)
        check_row.addWidget(self.auto_reconnect)
        check_row.addStretch(1)
        form.addRow(check_row)
        layout.addWidget(beh_card)

        layout.addStretch(1)
        self._mark_advanced(beh_card)
        return page

    # ------------------------------------------------------------------
    # RDP page
    # ------------------------------------------------------------------

    def _build_rdp_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(self._build_auth_box(PROTOCOL_RDP))

        display_card = self._make_card("Display")
        disp_content = self._card_content(display_card)
        dform = QFormLayout(disp_content)
        dform.setSpacing(10)
        dform.setContentsMargins(16, 16, 16, 16)

        self.rdp_display_mode = self._make_combo()
        self.rdp_display_mode.addItem("Fit to window (recommended)", "fit")
        self.rdp_display_mode.addItem("Fullscreen", "fullscreen")
        for w, h in RDP_RESOLUTIONS:
            self.rdp_display_mode.addItem(f"{w} \u00d7 {h}", f"{w}x{h}")
        self.rdp_display_mode.addItem("Custom\u2026", "custom")
        preset = self.rdp_display_mode.findData(_display_mode_of(self.session))
        self.rdp_display_mode.setCurrentIndex(preset if preset >= 0 else 0)
        self.rdp_display_mode.currentIndexChanged.connect(self._on_rdp_display_mode)
        dform.addRow(self._make_label("Resolution"), self.rdp_display_mode)

        self.rdp_width = self._make_spinbox(self.session.rdp_width, 640, 7680)
        self.rdp_width.setSingleStep(_RDP_STEP)
        self.rdp_height = self._make_spinbox(self.session.rdp_height, 480, 4320)
        self.rdp_height.setSingleStep(_RDP_STEP)

        self.rdp_bpp = self._make_combo()
        for bpp in (16, 24, 32):
            self.rdp_bpp.addItem(f"{bpp}-bit", bpp)
        bi = self.rdp_bpp.findData(self.session.rdp_color_depth)
        self.rdp_bpp.setCurrentIndex(bi if bi >= 0 else 2)

        custom = QWidget()
        res = QHBoxLayout(custom)
        res.setContentsMargins(0, 0, 0, 0)
        res.setSpacing(8)
        res.addWidget(self.rdp_width)
        x_lbl = QLabel("\u00d7")
        x_lbl.setStyleSheet(f"color: {self._pal['fg_dim']}; font-size: 14px;")
        res.addWidget(x_lbl)
        res.addWidget(self.rdp_height)
        res.addSpacing(12)
        res.addWidget(self.rdp_bpp)
        res.addStretch(1)
        self._rdp_custom_label = self._make_label("Size")
        dform.addRow(self._rdp_custom_label, custom)
        self._rdp_custom = custom

        self.rdp_fullscreen = self._make_checkbox("Fullscreen", self.session.rdp_fullscreen)
        self.rdp_fullscreen.setVisible(False)
        self.rdp_fit_screen = self._make_checkbox("Fit display to screen", self.session.rdp_fit_screen)
        self.rdp_fit_screen.setVisible(False)

        emb_note = QLabel("Desktop renders inside this app when possible (Linux + X11 + FreeRDP).")
        emb_note.setObjectName("muted")
        emb_note.setStyleSheet(f"font-size: 11px; color: {self._pal['fg_muted']}; padding: 2px 0;")
        emb_note.setWordWrap(True)
        dform.addRow(emb_note)
        layout.addWidget(display_card)
        self._mark_advanced(emb_note)

        redir_card = self._make_card("Device Redirection")
        redir_content = self._card_content(redir_card)
        rform = QFormLayout(redir_content)
        rform.setSpacing(10)
        rform.setContentsMargins(16, 16, 16, 16)

        self.rdp_clipboard = self._make_checkbox("Share clipboard", self.session.rdp_clipboard)
        self.rdp_drives = self._make_checkbox("Share local drives", self.session.rdp_drives)
        self.rdp_audio = self._make_checkbox("Redirect audio", True)
        self.rdp_audio.setToolTip("Redirect audio to the local device during the RDP session")
        rform.addRow(self.rdp_clipboard)
        rform.addRow(self.rdp_drives)
        rform.addRow(self.rdp_audio)
        self._mark_advanced(self.rdp_audio)
        layout.addWidget(redir_card)

        sec_card = self._make_card("Security")
        sec_content = self._card_content(sec_card)
        sform = QFormLayout(sec_content)
        sform.setSpacing(10)
        sform.setContentsMargins(16, 16, 16, 16)
        self.rdp_cert_ignore = self._make_checkbox(
            "Accept any certificate (not recommended)", self.session.rdp_cert_ignore
        )
        self.rdp_pass_cmd = self._make_checkbox(
            "Pass password on command line (insecure)", self.session.rdp_pass_on_cmdline
        )
        sform.addRow(self.rdp_cert_ignore)
        sform.addRow(self.rdp_pass_cmd)
        layout.addWidget(sec_card)

        gw_card = self._make_card("RD Gateway")
        gw_content = self._card_content(gw_card)
        gw_outer = QVBoxLayout(gw_content)
        gw_outer.setContentsMargins(16, 16, 16, 16)
        gw_outer.setSpacing(12)

        gw_row1 = QHBoxLayout()
        gw_row1.setSpacing(12)
        gw_h_col = QVBoxLayout()
        gw_h_col.setSpacing(4)
        gw_h_col.addWidget(self._make_label("Gateway host"))
        self.gw_host = self._make_input(self.session.rdp_gateway_host, "gateway.example.com")
        gw_h_col.addWidget(self.gw_host)
        gw_row1.addLayout(gw_h_col, 2)

        gw_p_col = QVBoxLayout()
        gw_p_col.setSpacing(4)
        gw_p_col.addWidget(self._make_label("Port"))
        self.gw_port = self._make_spinbox(self.session.rdp_gateway_port or 443, 1, 65535)
        gw_p_col.addWidget(self.gw_port)
        gw_row1.addLayout(gw_p_col, 1)

        gw_u_col = QVBoxLayout()
        gw_u_col.setSpacing(4)
        gw_u_col.addWidget(self._make_label("Username"))
        self.gw_user = self._make_input(self.session.rdp_gateway_user, "gateway user")
        gw_u_col.addWidget(self.gw_user)
        gw_row1.addLayout(gw_u_col, 2)

        gw_outer.addLayout(gw_row1)
        layout.addWidget(gw_card)
        self._mark_advanced(gw_card)

        layout.addStretch(1)
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

    # ------------------------------------------------------------------
    # Local page
    # ------------------------------------------------------------------

    def _build_local_page(self) -> QWidget:
        page = QWidget()
        card = self._make_card("Local Shell")
        content = self._card_content(card)
        form = QFormLayout(content)
        form.setSpacing(12)
        form.setContentsMargins(16, 16, 16, 16)
        self.local_cmd = self._make_input(self.session.options.get("command", ""), "default: your login shell (bash / PowerShell)")
        form.addRow(self._make_label("Command"), self.local_cmd)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Protocol switching
    # ------------------------------------------------------------------

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
        self._domain_widget.setVisible(pid == PROTOCOL_RDP and not is_local)
        widget = {
            PROTOCOL_SSH: self._ssh_page,
            PROTOCOL_RDP: self._rdp_page,
            PROTOCOL_LOCAL: self._local_page,
        }.get(pid, self._ssh_page)
        self.stack.setCurrentWidget(widget)

    def _on_auth(self, protocol: str | None = None) -> None:
        ui = self._current_auth_ui(protocol)
        method = ui["auth"].currentData()
        wants_credential = False
        wants_key = method == AUTH_KEY
        ui["credential_label"].setVisible(wants_credential)
        ui["credential"].setVisible(wants_credential)
        ui["key_label"].setVisible(wants_key)
        ui["key_row"].setVisible(wants_key)
        ui["credential"].setEnabled(wants_credential)
        ui["key_path"].setEnabled(wants_key)
        uses_password = method == AUTH_PASSWORD
        self.password.setEnabled(uses_password)
        self.password.setPlaceholderText(
            "leave blank to prompt at connect" if uses_password
            else "not used with this method"
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_fields(self) -> bool:
        p = self._pal
        ok = True
        pid = self.protocol.currentData() or PROTOCOL_SSH
        is_local = pid == PROTOCOL_LOCAL

        if not is_local:
            host_text = self.host.text().strip()
            if not host_text:
                self.host.setStyleSheet(
                    f"QLineEdit {{ font-size: 13px; padding: 6px 10px; "
                    f"border: 1px solid {p['bad']}; border-radius: 8px; "
                    f"background: {p['bg3']}; color: {p['fg']}; }}"
                    f"QLineEdit:focus {{ border-color: {p['bad']}; }}"
                )
                ok = False
            else:
                self.host.setStyleSheet(
                    f"QLineEdit {{ font-size: 13px; padding: 6px 10px; "
                    f"border: 1px solid {p['border']}; border-radius: 8px; "
                    f"background: {p['bg3']}; color: {p['fg']}; }}"
                    f"QLineEdit:focus {{ border-color: {p['accent']}; }}"
                )

            port_val = self.port.value()
            if port_val < 1 or port_val > 65535:
                self.port.setStyleSheet(
                    f"QSpinBox {{ font-size: 13px; padding: 6px 10px; "
                    f"border: 1px solid {p['bad']}; border-radius: 8px; "
                    f"background: {p['bg3']}; color: {p['fg']}; }}"
                    f"QSpinBox:focus {{ border-color: {p['bad']}; }}"
                )
                ok = False
            else:
                self.port.setStyleSheet(
                    f"QSpinBox {{ font-size: 13px; padding: 6px 10px; "
                    f"border: 1px solid {p['border']}; border-radius: 8px; "
                    f"background: {p['bg3']}; color: {p['fg']}; }}"
                    f"QSpinBox:focus {{ border-color: {p['accent']}; }}"
                )
        return ok

    def _flash_invalid(self, widget: QWidget) -> None:
        p = self._pal
        wname = type(widget).__name__
        widget.setStyleSheet(
            f"{wname} {{ font-size: 13px; padding: 6px 10px; "
            f"border: 1px solid {p['bad']}; border-radius: 8px; "
            f"background: {p['bg3']}; color: {p['fg']}; }}"
            f"{wname}:focus {{ border-color: {p['bad']}; }}"
        )
        QTimer.singleShot(1200, lambda w=widget: self._reset_field_style(w))

    def _reset_field_style(self, widget: QWidget) -> None:
        p = self._pal
        wname = type(widget).__name__
        widget.setStyleSheet(
            f"{wname} {{ font-size: 13px; padding: 6px 10px; "
            f"border: 1px solid {p['border']}; border-radius: 8px; "
            f"background: {p['bg3']}; color: {p['fg']}; "
            f"font-size: 13px; }}"
            f"{wname}:focus {{ border-color: {p['accent']}; }}"
        )

    # ------------------------------------------------------------------
    # Save / connect / test / delete
    # ------------------------------------------------------------------

    def _collect_session(self) -> Session:
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
        return s

    def _on_save(self) -> None:
        if not self._validate_fields():
            return
        s = self._collect_session()
        self.ctx.store.upsert(s)
        self.accept()

    def _on_connect(self) -> None:
        if not self._validate_fields():
            return
        s = self._collect_session()
        self.ctx.store.upsert(s)
        self.accept()

    def _on_test(self) -> None:
        if not self._validate_fields():
            return
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "Test connection",
            "Connection test is not yet implemented. The session will be saved and you can connect to test it.",
        )

    def _on_delete(self) -> None:
        from PySide6.QtWidgets import QMessageBox
        btn = QMessageBox.question(
            self,
            "Delete session",
            f"Delete \u201c{self.session.display_name()}\u201d?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if btn == QMessageBox.StandardButton.Yes:
            self.ctx.store.delete(self.session.id)
            self.accept()

    # ------------------------------------------------------------------
    # Public property
    # ------------------------------------------------------------------

    @property
    def result_session(self) -> Session:
        return self.session


def icon_text(plugin) -> str:
    labels = {"ssh": "SSH terminal", "rdp": "RDP remote desktop", "local": "Local shell"}
    return labels.get(plugin.id, plugin.title)
