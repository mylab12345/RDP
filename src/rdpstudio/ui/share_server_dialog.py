"""File sharing manager — the built-in SFTP share server.

One place to point at the local folders you want to hand out, start the
listener, and copy the exact command the remote (Windows) machine needs.
Windows has no SSH daemon to serve files *back* to us, so the files are served
from here instead: the remote machine connects with its own SFTP client
(``sftp.exe`` on Windows 10 1809+, or WinSCP) and sees one directory per
share.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..core.log import get_logger
from ..core.models import Session
from ..core.shares import (
    MAX_SHARES,
    SCOPE_GLOBAL,
    SCOPE_SESSION,
    Share,
    sanitize_share_name,
    share_name_from_path,
    unique_share_names,
)
from ..tools.share_server import ShareServerError
from .theme import icon, palette
from .widgets import toast

log = get_logger("ui.shares")

_COLUMNS = ("Share name", "Local folder", "Shared with", "On")
_REFRESH_MS = 2000
_COL_CHECK = 3


class _PasswordDialog(QDialog):
    """Ask for a share password twice; nothing is stored in clear text."""

    def __init__(self, username: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Share password")
        self.setModal(True)
        self.setMinimumWidth(420)
        pal = palette()
        layout = QVBoxLayout(self)
        note = QLabel(
            f"Remote machines log in as <b>{username or 'kbshare'}</b> with this password.<br>"
            "It is stored as a PBKDF2-HMAC-SHA256 hash — never in clear text."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 12px;")
        layout.addWidget(note)

        form = QFormLayout()
        self.pw1 = QLineEdit()
        self.pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw2 = QLineEdit()
        self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password", self.pw1)
        form.addRow("Repeat", self.pw2)
        layout.addLayout(form)

        self._error = QLabel("")
        self._error.setStyleSheet(f"color: {pal['bad']}; font-size: 12px;")
        layout.addWidget(self._error)

        box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        box.accepted.connect(self._on_ok)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _on_ok(self) -> None:
        first, second = self.pw1.text(), self.pw2.text()
        if len(first) < 8:
            self._error.setText("Use at least 8 characters.")
            return
        if first != second:
            self._error.setText("The two passwords do not match.")
            return
        self.accept()

    def password(self) -> str:
        return self.pw1.text()


class ShareServerDialog(QDialog):
    """Start/stop the share server and edit the folders it hands out."""

    def __init__(self, service, parent=None, session: Session | None = None) -> None:
        super().__init__(parent)
        self.service = service
        self.session = session
        # Rows currently rendered, in table order: (share, scope).
        self._rows: list[tuple[Share, str]] = []
        self._loading = False

        self.setWindowTitle(
            "File sharing" + (f" — {session.display_name()}" if session is not None else "")
        )
        self.resize(780, 640)
        self.setModal(False)

        pal = palette()
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        title = QLabel("<b>Local file share server</b>")
        title.setStyleSheet("font-size: 15px;")
        root.addWidget(title)
        intro = QLabel(
            "Serve local folders to remote machines over SFTP. A Windows box you reach over "
            "RDP connects back with its own client — nothing to install on it."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 12px;")
        root.addWidget(intro)

        root.addWidget(self._status_card())
        root.addWidget(self._config_card())
        root.addWidget(self._shares_card(), 1)
        root.addWidget(self._connect_card())
        root.addWidget(self._activity_card())
        root.addLayout(self._buttons())

        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    # ------------------------------------------------------------------
    # sections
    # ------------------------------------------------------------------
    def _card(self) -> QFrame:
        frame = QFrame()
        pal = palette()
        frame.setObjectName("card")
        frame.setStyleSheet(
            f"QFrame#card {{ background: {pal['bg2']}; border: 1px solid {pal['border']};"
            f" border-radius: 2px; }}"
        )
        return frame

    def _muted(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet(f"color: {palette()['fg_muted']}; font-size: 11px;")
        return label

    def _status_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        self.status_line = QLabel("")
        self.status_line.setStyleSheet("font-size: 13px;")
        self.detail_line = self._muted("")
        layout.addWidget(self.status_line)
        layout.addWidget(self.detail_line)
        return card

    def _config_card(self) -> QFrame:
        card = self._card()
        form = QFormLayout(card)
        form.setContentsMargins(12, 10, 12, 10)
        form.setSpacing(8)
        config = self.service.server.config
        self.bind = QLineEdit(str(config.bind))
        self.bind.setToolTip("0.0.0.0 = every interface; 127.0.0.1 = this machine only")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(config.port))
        self.user = QLineEdit(str(config.username))
        self.writable = QCheckBox("Allow remote machines to write (upload / delete)")
        self.writable.setChecked(bool(config.allow_write))

        pw_row = QHBoxLayout()
        self.btn_password = QPushButton(icon("key"), " Set password…")
        self.btn_password.clicked.connect(self._set_password)
        self.pw_state = self._muted("")
        pw_row.addWidget(self.btn_password)
        pw_row.addWidget(self.pw_state)
        pw_row.addStretch(1)

        form.addRow("Listen on", self.bind)
        form.addRow("Port", self.port)
        form.addRow("Username", self.user)
        form.addRow("Password", pw_row)
        form.addRow("", self.writable)
        return card

    def _shares_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel("<b>Shared folders</b>"))
        head.addStretch(1)
        self.btn_add = QPushButton(icon("plus"), " Add folder…")
        self.btn_add.setToolTip("Share with every machine")
        self.btn_add.clicked.connect(lambda: self._add_folder(SCOPE_GLOBAL))
        head.addWidget(self.btn_add)
        if self.session is not None:
            self.btn_add_session = QPushButton(icon("plus"), " Add for this machine…")
            self.btn_add_session.setToolTip(f"Share only while “{self.session.display_name()}” is open")
            self.btn_add_session.clicked.connect(lambda: self._add_folder(SCOPE_SESSION))
            head.addWidget(self.btn_add_session)
        self.btn_remove = QPushButton(icon("trash"), " Remove")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_open = QPushButton(icon("folder"), " Open")
        self.btn_open.clicked.connect(self._open_selected)
        head.addWidget(self.btn_remove)
        head.addWidget(self.btn_open)
        layout.addLayout(head)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_CHECK, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        layout.addWidget(
            self._muted(
                "Each folder is a top-level directory for the SFTP client — share <b>Tools</b> "
                "is <code>/Tools/</code>. Untick a row to keep it configured but not shared. "
                f"Up to {MAX_SHARES} shares."
            )
        )
        return card

    def _connect_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(QLabel("<b>Connect from the remote machine</b>"))

        self.cmd_edit = QLineEdit()
        self.cmd_edit.setReadOnly(True)
        cmd_row = QHBoxLayout()
        cmd_row.addWidget(self.cmd_edit, 1)
        cmd_row.addWidget(self._copy_button(self.cmd_edit))
        layout.addLayout(cmd_row)

        self.winscp_edit = QLineEdit()
        self.winscp_edit.setReadOnly(True)
        url_row = QHBoxLayout()
        url_row.addWidget(self.winscp_edit, 1)
        url_row.addWidget(self._copy_button(self.winscp_edit))
        layout.addLayout(url_row)

        self.connect_hint = self._muted("")
        layout.addWidget(self.connect_hint)
        return card

    def _copy_button(self, source: QLineEdit) -> QPushButton:
        button = QPushButton("Copy")
        button.clicked.connect(lambda: self._copy(source.text()))
        return button

    def _activity_card(self) -> QFrame:
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(QLabel("<b>Activity</b>"))
        head.addStretch(1)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear_events)
        head.addWidget(btn_clear)
        layout.addLayout(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(150)
        self.log_view.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self.log_view)
        return card

    def _buttons(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.btn_toggle = QPushButton(icon("connect"), " Start server")
        self.btn_toggle.setObjectName("primary")
        self.btn_toggle.clicked.connect(self._toggle)
        self.btn_apply = QPushButton("Apply settings")
        self.btn_apply.clicked.connect(self._apply_settings)
        row.addWidget(self.btn_toggle)
        row.addWidget(self.btn_apply)
        row.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        box.clicked.connect(self.accept)
        row.addWidget(box)
        return row

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _copy(self, text: str) -> None:
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        toast(self, "Copied to clipboard", "info")

    def _clear_events(self) -> None:
        self.service.server.clear_events()
        self.refresh()

    def _open_path(self, path: str) -> None:
        if not path or not os.path.isdir(path):
            toast(self, "That folder is gone", "warn")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])  # noqa: S603,S607
            else:
                subprocess.Popen(["xdg-open", path])  # noqa: S603,S607
        except OSError as exc:
            QMessageBox.warning(self, "Cannot open folder", str(exc))

    # ------------------------------------------------------------------
    # shares table
    # ------------------------------------------------------------------
    def _all_shares(self) -> list[tuple[Share, str]]:
        rows = [(share.copy(), SCOPE_GLOBAL) for share in self.service.global_shares()]
        if self.session is not None:
            rows.extend((share.copy(), SCOPE_SESSION) for share in self.session.rdp_shares)
        return rows

    def _reload_table(self) -> None:
        self._loading = True
        self._rows = self._all_shares()
        self.table.setRowCount(0)
        for share, scope in self._rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QTableWidgetItem(share.name)
            name.setToolTip("The name the remote machine sees")
            path = QTableWidgetItem(share.path)
            path.setToolTip(share.path)
            where = QTableWidgetItem("all machines" if scope == SCOPE_GLOBAL else "this machine only")
            where.setFlags(Qt.ItemFlag.ItemIsEnabled)
            tick = QTableWidgetItem()
            tick.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            tick.setToolTip("Share this folder")
            tick.setCheckState(Qt.CheckState.Checked if share.enabled else Qt.CheckState.Unchecked)
            for column, item in enumerate((name, path, where, tick)):
                self.table.setItem(row, column, item)
        self._loading = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or item.column() != _COL_CHECK:
            return  # only the tick is editable; names come from the folder
        self._commit_table()

    def _commit_table(self) -> None:
        """Push the enable ticks back into the service / session."""
        changed = False
        for row, (share, _scope) in enumerate(self._rows):
            tick = self.table.item(row, _COL_CHECK)
            if tick is None:
                continue
            enabled = tick.checkState() == Qt.CheckState.Checked
            if enabled != share.enabled:
                share.enabled = enabled
                changed = True
        if not changed:
            return
        self.service.set_global_shares([s for s, scope in self._rows if scope == SCOPE_GLOBAL])
        if self.session is not None:
            self.session.rdp_shares = [s for s, scope in self._rows if scope == SCOPE_SESSION]
        self._persist()

    def _add_folder(self, scope: str) -> None:
        if len(self._rows) >= MAX_SHARES:
            QMessageBox.information(self, "Limit reached", f"At most {MAX_SHARES} shared folders.")
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder to share", os.path.expanduser("~"))
        if not folder:
            return
        existing = self._all_shares()
        if any(os.path.abspath(s.path) == os.path.abspath(folder) for s, _ in existing):
            toast(self, "That folder is already shared", "warn")
            return
        name = unique_share_names([s for s, _ in existing], share_name_from_path(folder))
        share = Share(name=sanitize_share_name(name), path=folder, enabled=True)
        if scope == SCOPE_SESSION and self.session is not None:
            self.session.rdp_shares.append(share)
        else:
            shares = self.service.global_shares()
            shares.append(share)
            self.service.set_global_shares(shares)
        self._reload_table()
        self._persist()
        toast(self, f"Sharing “{share.name}” — {folder}", "info")
        self.refresh()

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows):
            return
        share, scope = self._rows[row]
        if scope == SCOPE_GLOBAL:
            self.service.set_global_shares(
                [s for s in self.service.global_shares() if s.path != share.path]
            )
        elif self.session is not None:
            self.session.rdp_shares = [s for s in self.session.rdp_shares if s.path != share.path]
        self._reload_table()
        self._persist()

    def _open_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._rows):
            self._open_path(self._rows[row][0].path)

    # ------------------------------------------------------------------
    # credentials + lifecycle
    # ------------------------------------------------------------------
    def _set_password(self) -> None:
        dialog = _PasswordDialog(self.user.text().strip(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.service.server.config.username = self.user.text().strip() or "kbshare"
        self.service.set_password(dialog.password())
        self.service.save_settings()
        self._persist()
        toast(self, "Share password updated", "good")
        self.refresh()

    def _apply_settings(self) -> None:
        config = self.service.server.config
        config.bind = self.bind.text().strip() or "0.0.0.0"
        config.port = int(self.port.value())
        config.username = self.user.text().strip() or "kbshare"
        config.allow_write = self.writable.isChecked()
        self._commit_table()
        self.service.save_settings()
        self._persist()
        if self.service.server.running:
            try:
                self.service.server.restart()
            except ShareServerError as exc:
                QMessageBox.warning(self, "Cannot restart the listener", str(exc))
        toast(self, "Settings applied", "good")
        self.refresh()

    def _toggle(self) -> None:
        self._apply_settings()
        try:
            if self.service.server.running:
                self.service.stop()
                self._persist()
                toast(self, "Share server stopped", "info")
                self.refresh()
                return
            if not self.service.has_password():
                QMessageBox.information(
                    self,
                    "Password needed",
                    "Set a share password first — remote machines need it to log in.",
                )
                self._set_password()
                if not self.service.has_password():
                    return
            if not self.service.registry.entries():
                answer = QMessageBox.question(
                    self,
                    "No shared folders",
                    "Nothing is shared yet. Start anyway and add folders later?",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
            self.service.start()
            self._persist()
            toast(self, f"Sharing on {self.service.server.display_address()}", "good")
        except ShareServerError as exc:
            QMessageBox.warning(self, "Cannot start the share server", str(exc))
        self.refresh()

    def _persist(self) -> None:
        """Save the session (if any) and the settings file."""
        owner = self.parent()
        ctx = getattr(owner, "ctx", None) or getattr(getattr(owner, "main", None), "ctx", None)
        if ctx is None:
            return
        try:
            if self.session is not None and ctx.store.get(self.session.id) is not None:
                ctx.store.upsert(self.session)
            self.service.save_settings()
            save = getattr(owner, "save_settings", None) or getattr(owner, "_save_settings", None)
            if callable(save):
                save()
        except OSError as exc:
            log.warning("could not persist share settings: %s", exc)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._reload_table()  # row model first: the status line counts it
        snap = self.service.snapshot()
        running = snap["running"]
        pal = palette()
        colour = pal["good"] if running else pal["bad"]
        bits = [f"<b style='color:{colour}'>● {'Running' if running else 'Stopped'}</b>"]
        if running:
            bits.append(f"{snap['display_address']}")
            bits.append(f"{snap['clients']} client(s)")
        served = len(snap["shares"])
        pending = len(self._rows) - served
        bits.append(f"{served} folder(s) served")
        if pending > 0 and self.session is not None:
            bits.append(f"+{pending} when “{self.session.display_name()}” connects")
        if not snap["writable"]:
            bits.append("read-only")
        self.status_line.setText(" &nbsp;·&nbsp; ".join(bits))

        details = []
        if snap["shares"]:
            details.append("On the remote machine: " + ", ".join(f"/{s['name']}/" for s in snap["shares"]))
        else:
            details.append("No folders shared yet — add one below.")
        if running:
            details.append(f"Host key {snap['fingerprint']}")
        self.detail_line.setText(" · ".join(details))

        self.btn_toggle.setText(" Stop server" if running else " Start server")
        self.btn_toggle.setIcon(icon("stop") if running else icon("connect"))

        self.cmd_edit.setText(snap["command"])
        self.winscp_edit.setText(snap["winscp"])
        self.connect_hint.setText(
            "Windows 10 1809+ ships <code>sftp.exe</code> (run it in PowerShell); WinSCP and "
            f"FileZilla take the sftp:// URL. First connection asks you to accept the host key "
            f"(user <b>{snap['username']}</b>)."
        )
        self.pw_state.setText("set" if self.service.has_password() else "not set — required")

        lines = []
        for event in snap["events"][-40:]:
            stamp = time.strftime("%H:%M:%S", time.localtime(event["ts"]))
            peer = f"  ({event['peer']})" if event.get("peer") else ""
            lines.append(f"{stamp}  {event['kind']:<6}  {event['detail']}{peer}")
        self.log_view.setPlainText("\n".join(lines) or "Nothing yet.")

    def reject(self) -> None:
        self._commit_table()
        super().reject()


def open_share_dialog(parent, service, session: Session | None = None) -> ShareServerDialog:
    """Show (or re-raise) the share manager for ``service``."""
    existing = getattr(parent, "_share_dialog", None)
    if isinstance(existing, ShareServerDialog) and existing.isVisible():
        existing.raise_()
        existing.activateWindow()
        return existing
    dialog = ShareServerDialog(service, parent, session)
    parent._share_dialog = dialog
    dialog.show()
    return dialog


__all__ = ["ShareServerDialog", "open_share_dialog"]
