"""Application settings dialog."""

from __future__ import annotations

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from ..core.plugin import SessionContext


class SettingsDialog(QDialog):
    def __init__(self, ctx: SessionContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(560, 560)

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(page)

        # --- appearance ------------------------------------------------------
        appearance = QGroupBox("Appearance")
        form = QFormLayout(appearance)
        self.theme = QComboBox()
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        ti = self.theme.findData(ctx.settings.theme)
        self.theme.setCurrentIndex(ti if ti >= 0 else 0)
        form.addRow("Theme", self.theme)

        self.font_family = QComboBox()
        self.font_family.setEditable(True)
        families = sorted(set(QFontDatabase.families()))
        mono = [f for f in families if "Mono" in f or "Consol" in f or "mono" in f]
        self.font_family.addItems(mono or families)
        if ctx.settings.font_family:
            self.font_family.setCurrentText(ctx.settings.font_family)
        form.addRow("Terminal font", self.font_family)

        self.font_size = QSpinBox()
        self.font_size.setRange(7, 24)
        self.font_size.setValue(ctx.settings.font_size)
        form.addRow("Font size", self.font_size)
        self.cursor = QComboBox()
        self.cursor.addItem("Block", "block")
        self.cursor.addItem("Underline", "underline")
        self.cursor.addItem("Bar", "bar")
        ci = self.cursor.findData(ctx.settings.cursor_style)
        self.cursor.setCurrentIndex(ci if ci >= 0 else 0)
        form.addRow("Cursor", self.cursor)
        layout.addWidget(appearance)

        # --- terminal ---------------------------------------------------------
        terminal = QGroupBox("Terminal")
        tform = QFormLayout(terminal)
        self.scrollback = QSpinBox()
        self.scrollback.setRange(200, 100_000)
        self.scrollback.setSingleStep(500)
        self.scrollback.setValue(ctx.settings.scrollback_lines)
        tform.addRow("Scrollback (lines)", self.scrollback)
        self.copy_on_select = QCheckBox("Copy on select")
        self.copy_on_select.setChecked(ctx.settings.copy_on_select)
        self.middle_paste = QCheckBox("Middle-click paste")
        self.middle_paste.setChecked(ctx.settings.paste_on_middle_click)
        self.confirm_paste = QCheckBox("Confirm multi-line paste")
        self.confirm_paste.setChecked(ctx.settings.confirm_multiline_paste)
        tform.addRow(self.copy_on_select)
        tform.addRow(self.middle_paste)
        tform.addRow(self.confirm_paste)
        layout.addWidget(terminal)

        # --- connection ---------------------------------------------------------
        conn = QGroupBox("Connection")
        cform = QFormLayout(conn)
        self.keepalive = QSpinBox()
        self.keepalive.setRange(5, 300)
        self.keepalive.setValue(ctx.settings.default_keepalive)
        cform.addRow("Default keepalive (s)", self.keepalive)
        self.max_attempts = QSpinBox()
        self.max_attempts.setRange(1, 100)
        self.max_attempts.setValue(ctx.settings.reconnect_max_attempts)
        cform.addRow("Reconnect attempts", self.max_attempts)
        self.host_key_policy = QComboBox()
        self.host_key_policy.addItem("Trust on first use, prompt for new keys (TOFU)", "accept-new")
        self.host_key_policy.addItem("Strict — always prompt", "strict")
        hi = self.host_key_policy.findData(ctx.settings.host_key_policy)
        self.host_key_policy.setCurrentIndex(hi if hi >= 0 else 0)
        cform.addRow("Host key policy", self.host_key_policy)
        self.rdp_client = QComboBox()
        self.rdp_client.addItem("Built-in — RDP renders inside this app", "embedded")
        self.rdp_client.addItem("External — separate RDP window", "external")
        self.rdp_client.addItem("Automatic (built-in when possible)", "auto")
        ri = self.rdp_client.findData(ctx.settings.rdp_client)
        self.rdp_client.setCurrentIndex(ri if ri >= 0 else 2)
        self.rdp_client.setToolTip(
            "Built-in needs Linux + X11 + FreeRDP (freerdp3-x11 / freerdp2-x11).\n"
            "On Wayland desktops RDP Studio restarts through XWayland to get it;\n"
            "on Windows the external mstsc window is used."
        )
        cform.addRow("RDP display", self.rdp_client)
        self.rdp_status = QLabel("")
        self.rdp_status.setObjectName("muted")
        self.rdp_status.setWordWrap(True)
        cform.addRow(self.rdp_status)
        self.btn_xwayland = QPushButton("Restart via XWayland now")
        self.btn_xwayland.setToolTip(
            "Restart RDP Studio as an X11 client through XWayland so remote\n"
            "desktops render inside the app (in-tab, like MobaXterm)."
        )
        self.btn_xwayland.clicked.connect(self._restart_via_xwayland)
        self._refresh_rdp_status()
        if self._xwayland_useful:
            cform.addRow(self.btn_xwayland)
        layout.addWidget(conn)

        # --- security --------------------------------------------------------------
        sec = QGroupBox("Security")
        sform = QFormLayout(sec)
        self.autolock = QSpinBox()
        self.autolock.setRange(0, 240)
        self.autolock.setSpecialValueText("never")
        self.autolock.setValue(ctx.settings.vault_autolock_minutes)
        sform.addRow("Vault auto-lock after (min)", self.autolock)
        self.kdf = QSpinBox()
        self.kdf.setRange(100_000, 5_000_000)
        self.kdf.setSingleStep(50_000)
        self.kdf.setValue(ctx.settings.kdf_iterations)
        sform.addRow("PBKDF2 iterations (new vaults)", self.kdf)
        note = QLabel("Vault KDF applies when creating/changing a vault.")
        note.setObjectName("muted")
        sform.addRow(note)
        layout.addWidget(sec)

        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _refresh_rdp_status(self) -> None:
        """Explain — and offer to fix — the current in-app RDP situation."""
        from ..protocols.rdp.embed import embed_blocked_on_wayland, embedded_support

        self._xwayland_useful = False
        ok, reason = embedded_support()
        if ok:
            self.rdp_status.setText("✓ In-app display active — remote desktops render inside RDP Studio.")
        elif embed_blocked_on_wayland():
            self._xwayland_useful = True
            self.rdp_status.setText(
                "Wayland session detected: in-app RDP needs X11. RDP Studio can restart\n"
                "through XWayland — it also does so automatically at startup when saved\n"
                "RDP sessions exist."
            )
        elif reason:
            self.rdp_status.setText(reason)
        else:  # pragma: no cover - defensive
            self.rdp_status.setText("")
        self.btn_xwayland.setVisible(self._xwayland_useful)

    def _restart_via_xwayland(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from ..protocols.rdp.embed import relaunch_under_x11

        answer = QMessageBox.question(
            self,
            "Restart via XWayland",
            "RDP Studio will restart through XWayland (the X11 compatibility\n"
            "layer of your desktop) so remote desktops render inside the app.\n\n"
            "Open sessions will be closed. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        relaunch_under_x11()

    def _save(self) -> None:
        s = self.ctx.settings
        s.theme = self.theme.currentData()
        s.font_family = self.font_family.currentText()
        s.font_size = self.font_size.value()
        s.cursor_style = self.cursor.currentData()
        s.scrollback_lines = self.scrollback.value()
        s.copy_on_select = self.copy_on_select.isChecked()
        s.paste_on_middle_click = self.middle_paste.isChecked()
        s.confirm_multiline_paste = self.confirm_paste.isChecked()
        s.default_keepalive = self.keepalive.value()
        s.reconnect_max_attempts = self.max_attempts.value()
        s.host_key_policy = self.host_key_policy.currentData()
        s.rdp_client = self.rdp_client.currentData()
        s.vault_autolock_minutes = self.autolock.value()
        s.kdf_iterations = self.kdf.value()
        s.save(paths.settings_file())
        self.accept()
