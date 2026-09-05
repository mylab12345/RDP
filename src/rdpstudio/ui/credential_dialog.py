"""Credential prompt dialog — shown before connecting when username or
password are missing from the saved session.

Prevents the app from silently connecting (and potentially authenticating
as the wrong user or skipping auth entirely) when only an IP address was
entered via Quick Connect or when a saved session has no credentials.

The dialog is intentionally compact and focused: Username + Password only.
If the user cancels, the connection is aborted.  The filled-in values are
written back onto the ``Session`` object in-memory so the controller sees
them without requiring a vault entry or a permanent save.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.models import (
    AUTH_AGENT,
    AUTH_KEY,
    AUTH_NONE,
    PROTOCOL_LOCAL,
    PROTOCOL_RDP,
    Session,
)


def needs_credential_prompt(defn: Session) -> bool:
    """Return True when the session lacks sufficient credentials to connect.

    Rules
    -----
    * Local-shell sessions never need credentials.
    * Sessions whose auth method does not use a password (key / agent / none)
      only need a username — skip the prompt if one is saved.
    * For password-based auth: both username AND password must be present.
      A missing username or password triggers the prompt.
    * Sessions with a vault ``credential_id`` are considered complete
      (the vault resolves the secret at connect time).
    """
    if defn.protocol == PROTOCOL_LOCAL:
        return False  # no credentials needed for a local shell

    # Vault credential covers everything — no prompt needed
    if defn.credential_id:
        return False

    # Key / agent / none methods need only a username
    if defn.auth in (AUTH_KEY, AUTH_AGENT, AUTH_NONE):
        return not defn.username  # prompt only if username is also missing

    # Password-based: need both username AND password
    missing_user = not defn.username
    missing_pass = not defn.password
    return missing_user or missing_pass


class CredentialDialog(QDialog):
    """Compact credential prompt shown before connecting an uncredentialed session.

    Parameters
    ----------
    defn:
        The session being opened.  ``defn.username`` and ``defn.password``
        are pre-filled from whatever was already saved so the user only has
        to fill in what is missing.
    parent:
        Parent widget (the main window).
    """

    def __init__(self, defn: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._defn = defn
        self.setWindowTitle("Credentials required")
        self.setModal(True)
        self.setMinimumWidth(400)

        # --- try to get theme palette without crashing if theme not loaded ---
        try:
            from .theme import palette as theme_palette
            pal = theme_palette()
        except Exception:  # noqa: BLE001
            pal = {
                "bg2": "#1e2330",
                "bg3": "#252c3d",
                "border": "#343c52",
                "accent": "#4e8cff",
                "fg": "#d0d8f0",
                "bad": "#e05050",
                "panel": "#171e2d",
            }

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(14)

        # ---- header --------------------------------------------------------
        host = defn.host or "(unknown host)"
        proto = defn.protocol.upper()
        title = QLabel(f"Enter credentials for  <b>{host}</b>")
        title.setObjectName("h1")
        root.addWidget(title)

        subtitle = QLabel(
            f"Protocol: <b>{proto}</b> · "
            "Username and password are required to connect."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        # ---- divider -------------------------------------------------------
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        root.addWidget(line)

        # ---- form ----------------------------------------------------------
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setSpacing(10)
        form.setContentsMargins(0, 4, 0, 4)

        _input_style = (
            f"QLineEdit {{ font-size: 13px; padding: 6px 10px; "
            f"border: 1px solid {pal['border']}; border-radius: 3px; "
            f"background: {pal['bg3']}; color: {pal['fg']}; }}"
            f"QLineEdit:focus {{ border-color: {pal['accent']}; }}"
        )

        self._user_edit = QLineEdit(defn.username or "")
        self._user_edit.setPlaceholderText("e.g. Administrator  or  DOMAIN\\user")
        self._user_edit.setMinimumHeight(34)
        self._user_edit.setStyleSheet(_input_style)
        form.addRow(QLabel("Username:"), self._user_edit)

        # Domain field (RDP only)
        self._domain_edit: QLineEdit | None = None
        if defn.protocol == PROTOCOL_RDP:
            self._domain_edit = QLineEdit(defn.domain or "")
            self._domain_edit.setPlaceholderText("e.g. WORKGROUP  (leave blank for local accounts)")
            self._domain_edit.setMinimumHeight(34)
            self._domain_edit.setStyleSheet(_input_style)
            form.addRow(QLabel("Domain:"), self._domain_edit)

        self._pass_edit = QLineEdit(defn.password or "")
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_edit.setPlaceholderText("Password")
        self._pass_edit.setMinimumHeight(34)
        self._pass_edit.setStyleSheet(_input_style)
        form.addRow(QLabel("Password:"), self._pass_edit)

        root.addWidget(form_widget)

        # ---- buttons -------------------------------------------------------
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setObjectName("hairline")
        line2.setFixedHeight(1)
        root.addWidget(line2)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

        # Focus the first empty field
        if not defn.username:
            self._user_edit.setFocus()
        else:
            self._pass_edit.setFocus()

    # ------------------------------------------------------------------
    def _on_accept(self) -> None:
        username = self._user_edit.text().strip()
        password = self._pass_edit.text()

        if not username:
            self._user_edit.setStyleSheet(
                self._user_edit.styleSheet()
                + "QLineEdit { border-color: #e05050; }"
            )
            self._user_edit.setFocus()
            return  # don't accept — user must provide a username

        # Write back onto the session object in-memory
        self._defn.username = username
        self._defn.password = password
        if self._domain_edit is not None:
            self._defn.domain = self._domain_edit.text().strip()

        self.accept()
