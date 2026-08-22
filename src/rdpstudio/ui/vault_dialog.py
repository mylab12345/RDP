"""Credential vault + SSH key manager dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
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

        layout = QVBoxLayout(self)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

        tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        tabs.addTab(self._build_credentials_tab(), "Credentials")
        tabs.addTab(self._build_keys_tab(), "SSH keys")

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.clicked.connect(self.accept)
        layout.addWidget(close)

        self._refresh()

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
        form.addRow("Secret", self.cred_secret)
        form.addRow("Host hint", self.cred_host)
        form.addRow("Notes", self.cred_notes)

        reveal = QPushButton("Show")
        reveal.setCheckable(True)
        reveal.toggled.connect(
            lambda on: self.cred_secret.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        self.cred_secret.textChanged.connect(lambda _: reveal.setChecked(False))

        buttons = QHBoxLayout()
        new_btn = QPushButton(icon("plus"), "New")
        save_btn = QPushButton("Save")
        del_btn = QPushButton(icon("trash"), "Delete")
        for b in (new_btn, save_btn, del_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        form.addRow(buttons)
        form.addRow(reveal)
        splitter.addWidget(editor)
        splitter.setSizes([320, 480])

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
                item.setData(Qt.ItemDataRole.UserRole, cred)
                self.cred_list.addItem(item)
        self._refresh_key_list()

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
        if row < 0:
            return
        item = self.cred_list.item(row)
        cred = item.data(Qt.ItemDataRole.UserRole)
        if cred is None:
            return
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
        cred = item.data(Qt.ItemDataRole.UserRole) if item else None
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
        cred = item.data(Qt.ItemDataRole.UserRole)
        vault: CredentialVault = self.ctx.vault
        if vault.unlocked and cred:
            vault.delete(cred.id)
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
        import shutil

        target = paths.keys_dir() / (path.split("/")[-1].split("\\")[-1])
        if str(target) != path:
            shutil.copy2(path, target)
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
