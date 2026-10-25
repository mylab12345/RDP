"""Credential vault + SSH key manager dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from ..core.log import get_logger
from ..core.plugin import SessionContext
from ..core.vault import Credential, CredentialVault
from .theme import icon
from .widgets import toast

log = get_logger("ui.vault")


class VaultDialog(QDialog):
    def __init__(self, ctx: SessionContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Credentials & keys")
        self.setModal(True)
        self.resize(860, 540)

        self.setMinimumSize(760, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        from .widgets import DialogHeader

        layout.addWidget(
            DialogHeader(
                "Credentials & keys",
                "Secrets stay encrypted at rest and are wiped from this window "
                "the moment the vault auto-locks.",
                icon_name="key",
            )
        )

        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        tabs = QTabWidget()
        tabs.setObjectName("toolTabs")
        layout.addWidget(tabs, 1)

        tabs.addTab(self._build_credentials_tab(), "Credentials")
        tabs.addTab(self._build_keys_tab(), "SSH keys")
        self._tabs = tabs

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.setObjectName("dialogActions")
        close.rejected.connect(self.reject)
        close.clicked.connect(self.accept)
        layout.addWidget(close)

        # Auto-lock happens on a timer in the main window; the dialog must
        # notice it even while it is open, so no cached secret survives (SR-04).
        self._last_unlocked = self.ctx.vault.unlocked
        self._lock_watch = QTimer(self)
        self._lock_watch.setInterval(1000)
        self._lock_watch.timeout.connect(self._watch_vault_lock)
        self._lock_watch.start()

        self._refresh()
        # Land the caret on the credential list, not on the tab strip: a
        # focused tab bar paints a keyboard ring on open, which reads as an
        # error state on a freshly opened dialog.
        self.cred_list.setFocus()

    # ------------------------------------------------------------------
    def _build_credentials_tab(self) -> QWidget:
        page = QWidget()
        h = QHBoxLayout(page)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        h.addWidget(splitter)

        self.cred_list = QListWidget()
        splitter.addWidget(self.cred_list)

        editor = QWidget()
        form = QFormLayout(editor)
        form.setContentsMargins(4, 4, 4, 4)
        form.setSpacing(9)
        self.cred_name = QLineEdit()
        self.cred_kind = QComboBox()
        self.cred_kind.addItems(["password", "passphrase", "secret"])
        self.cred_username = QLineEdit()
        self.cred_secret = QLineEdit()
        self.cred_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.cred_host = QLineEdit()
        self.cred_notes = QLineEdit()
        form.addRow("Name", self.cred_name)
        form.addRow("Kind", self.cred_kind)
        form.addRow("Username", self.cred_username)

        # Secret + reveal share one row: "Show" belongs to the field it
        # reveals, not on a row of its own.
        secret_row = QHBoxLayout()
        secret_row.setSpacing(6)
        secret_row.addWidget(self.cred_secret, 1)
        reveal = QPushButton("Show")
        reveal.setCheckable(True)
        reveal.setEnabled(False)  # until the vault is unlocked and an entry is picked
        reveal.setMinimumWidth(64)
        reveal.setObjectName("subtle")
        reveal.toggled.connect(self._set_secret_visible)
        self.cred_secret.textChanged.connect(lambda _: reveal.setChecked(False))
        self.reveal_btn = reveal
        secret_row.addWidget(reveal)
        form.addRow("Secret", secret_row)

        form.addRow("Host hint", self.cred_host)
        form.addRow("Notes", self.cred_notes)

        # Destructive action far left, primary action last — the standard
        # dialog action order the rest of the app follows.
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        new_btn = QPushButton(icon("plus"), "New")
        new_btn.setObjectName("ghost")
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primary")
        del_btn = QPushButton(icon("trash"), "Delete")
        del_btn.setObjectName("danger")
        buttons.addWidget(del_btn)
        buttons.addStretch(1)
        buttons.addWidget(new_btn)
        buttons.addWidget(save_btn)
        form.addRow(buttons)
        splitter.addWidget(editor)
        splitter.setSizes([300, 500])

        new_btn.clicked.connect(self._new_credential)
        save_btn.clicked.connect(self._save_credential)
        del_btn.clicked.connect(self._delete_credential)
        self.cred_list.currentRowChanged.connect(self._load_credential)
        return page

    def _build_keys_tab(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)

        self.key_list = QListWidget()
        v.addWidget(self.key_list)

        row = QHBoxLayout()
        gen = QPushButton(icon("key"), "Generate key…")
        imp = QPushButton("Import existing key…")
        agent = QPushButton("Show agent keys")
        row.addWidget(gen)
        row.addWidget(imp)
        row.addWidget(agent)
        row.addStretch(1)
        v.addLayout(row)

        gen.clicked.connect(self._generate_key)
        imp.clicked.connect(self._import_key)
        agent.clicked.connect(self._show_agent_keys)
        return page

    # ------------------------------------------------------------------
    # credentials
    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        vault: CredentialVault = self.ctx.vault
        if not vault.exists:
            self.status.setText("No vault yet — create one with a master password.")
        elif not vault.unlocked:
            self.status.setText("Vault is locked.")
        else:
            self.status.setText(f"Vault unlocked · {len(vault.entries())} credential(s)")
        self.cred_list.clear()
        if vault.unlocked:
            for cred in vault.entries():
                item = QListWidgetItem(f"{cred.name or cred.id} · {cred.kind}")
                # Only the id is cached: list items must not carry secrets or
                # live credential objects past a lock (SR-04/SR-15).
                item.setData(Qt.ItemDataRole.UserRole, cred.id)
                self.cred_list.addItem(item)
        else:
            self._clear_editor()
        self._last_unlocked = vault.unlocked
        self._refresh_key_list()

    # -- lock handling ---------------------------------------------------
    def _watch_vault_lock(self) -> None:
        """Purge every secret-bearing widget the moment the vault locks."""
        unlocked = self.ctx.vault.unlocked
        if self._last_unlocked and not unlocked:
            self._handle_vault_locked()
        self._last_unlocked = unlocked

    def _handle_vault_locked(self) -> None:
        if self.cred_list.count() or self.cred_list.currentRow() >= 0 or self.cred_secret.text():
            self.cred_list.clearSelection()
            self.cred_list.clear()
        self._clear_editor()
        self.status.setText("Vault is locked.")
        self._refresh_key_list()

    def _clear_editor(self) -> None:
        self.reveal_btn.setChecked(False)
        self.reveal_btn.setEnabled(False)
        for field in (
            self.cred_name,
            self.cred_username,
            self.cred_secret,
            self.cred_host,
            self.cred_notes,
        ):
            field.clear()
        self.cred_kind.setCurrentIndex(0)

    def _set_secret_visible(self, on: bool) -> None:
        if on and not self.ctx.vault.unlocked:
            self.reveal_btn.setChecked(False)
            return
        self.cred_secret.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        )

    def _new_credential(self) -> None:
        if not self._ensure_unlocked():
            return
        self.cred_list.clearSelection()
        self.cred_name.clear()
        self.cred_username.clear()
        self.cred_secret.clear()
        self.cred_host.clear()
        self.cred_notes.clear()
        self.cred_kind.setCurrentIndex(0)
        self.cred_name.setFocus()

    def _load_credential(self, row: int) -> None:
        vault: CredentialVault = self.ctx.vault
        if row < 0 or not vault.unlocked:
            # Selecting a stale row after a lock must never repopulate the
            # editor with secrets (SR-04).
            self._clear_editor()
            return
        item = self.cred_list.item(row)
        credential_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        cred = vault.get(credential_id) if credential_id else None
        if cred is None:
            self._clear_editor()
            return
        self.reveal_btn.setEnabled(True)
        self.cred_name.setText(cred.name)
        self.cred_kind.setCurrentText(cred.kind)
        self.cred_username.setText(cred.username)
        self.cred_secret.setText(cred.secret)
        self.cred_host.setText(cred.host_hint)
        self.cred_notes.setText(cred.notes)

    def _save_credential(self) -> None:
        vault: CredentialVault = self.ctx.vault
        if not self._ensure_unlocked():
            return
        item = self.cred_list.currentItem()
        credential_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        cred = vault.get(credential_id) if credential_id else None
        cred = cred or Credential()
        cred.name = self.cred_name.text().strip() or cred.id
        cred.kind = self.cred_kind.currentText()
        cred.username = self.cred_username.text().strip()
        cred.secret = self.cred_secret.text()
        cred.host_hint = self.cred_host.text().strip()
        cred.notes = self.cred_notes.text()
        vault.put(cred)
        self._persist_master()
        self._refresh()
        toast(self, f"Saved “{cred.name}”", "good")

    def _delete_credential(self) -> None:
        item = self.cred_list.currentItem()
        if item is None:
            return
        credential_id = item.data(Qt.ItemDataRole.UserRole)
        vault: CredentialVault = self.ctx.vault
        if not vault.unlocked:
            self._handle_vault_locked()
            return
        if credential_id:
            vault.delete(str(credential_id))
            self._persist_master()
            self._refresh()

    def _ensure_unlocked(self) -> bool:
        vault: CredentialVault = self.ctx.vault
        if vault.unlocked:
            return True
        if not vault.exists:
            pass1, ok = QInputDialog.getText(
                self, "Create vault", "Choose a master password:", QLineEdit.EchoMode.Password
            )
            if not ok or not pass1:
                return False
            pass2, ok = QInputDialog.getText(
                self, "Create vault", "Repeat master password:", QLineEdit.EchoMode.Password
            )
            if not ok or pass1 != pass2:
                QMessageBox.warning(self, "Vault", "Passwords do not match.")
                return False
            vault.create(pass1)
            self._refresh()
            return True
        password, ok = QInputDialog.getText(
            self, "Unlock vault", "Master password:", QLineEdit.EchoMode.Password
        )
        if not ok:
            return False
        try:
            vault.unlock(password)
            self._refresh()
            return True
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Vault", str(exc))
            return False

    def _persist_master(self) -> None:
        vault: CredentialVault = self.ctx.vault
        if vault.save_if_master():
            return
        master, ok = QInputDialog.getText(
            self, "Master password", "Enter master password to save changes:", QLineEdit.EchoMode.Password
        )
        if not ok:
            toast(self, "Changes not persisted (no master password given)", "warn")
            return
        try:
            vault.save(master)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Vault", f"Could not save: {exc}")

    # ------------------------------------------------------------------
    # keys
    # ------------------------------------------------------------------
    def _refresh_key_list(self) -> None:
        from ..protocols.ssh import keys

        self.key_list.clear()
        base = paths.keys_dir()
        for pub in sorted(base.glob("*.pub")):
            try:
                info = keys.key_info(str(pub).replace(".pub", ""))
                self.key_list.addItem(
                    f"{info.key_type} {info.bits}  ·  {info.path}\n  {info.sha256_fingerprint}"
                )
            except Exception:  # noqa: BLE001
                continue

    def _generate_key(self) -> None:
        from ..protocols.ssh import keys

        algo, ok = QInputDialog.getItem(
            self, "Key type", "Algorithm:", ["ed25519", "ecdsa", "rsa (4096)"], 0, False
        )
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "Key name", "File name:", text="id_ed25519_rdpstudio")
        if not ok or not name:
            return
        passphrase, ok = QInputDialog.getText(
            self, "Passphrase", "Passphrase (empty for none):", QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        path = str(paths.keys_dir() / name)
        key_type = "rsa" if algo.startswith("rsa") else algo.split()[0]
        try:
            info = keys.generate(
                path, key_type=key_type, bits=4096, passphrase=passphrase or ""
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Key generation failed", str(exc))
            return
        if passphrase:
            self._offer_store_in_vault(f"Passphrase for {name}", passphrase)
        toast(self, f"Generated {info.key_type} key\n{info.sha256_fingerprint}", "good")
        self._refresh_key_list()

    def _import_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", "", "All files (*)")
        if not path:
            return
        import os
        import shutil

        target = paths.keys_dir() / (path.split("/")[-1].split("\\")[-1])
        if str(target) != path:
            shutil.copy2(path, target)
        # copy2 preserves the source permissions — a world-readable source
        # would otherwise leak the private key (SSH itself refuses such keys).
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        toast(self, f"Imported {target.name}", "good")
        self._refresh_key_list()

    def _show_agent_keys(self) -> None:
        from ..protocols.ssh import keys

        entries = keys.agent_keys()
        if not entries:
            QMessageBox.information(self, "Agent", "No keys found in ssh-agent.")
            return
        QMessageBox.information(
            self,
            "Agent keys",
            "\n".join(f"{fp}\n  {desc}" for fp, desc in entries),
        )

    def _offer_store_in_vault(self, name: str, secret: str) -> None:
        btn = QMessageBox.question(
            self,
            "Vault",
            "Store this passphrase in the encrypted vault?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if btn != QMessageBox.StandardButton.Yes:
            return
        if not self._ensure_unlocked():
            return
        cred = Credential(name=name, kind="passphrase", secret=secret)
        self.ctx.vault.put(cred)
        self._persist_master()
        self._refresh()
