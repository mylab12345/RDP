"""Application settings dialog — flight-ops layout."""

from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
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
from ..core.settings import FONT_PRESETS, THEME_CHOICES


def _system_families() -> list[str]:
    try:
        return list(QFontDatabase.families())
    except Exception:  # noqa: BLE001
        return []


def _is_fixed(family: str) -> bool:
    try:
        return bool(QFontDatabase.isFixedPitch(family))
    except Exception:  # noqa: BLE001
        key = family.lower()
        return any(tok in key for tok in ("mono", "consol", "courier", "code", "term", "fixed"))


def collect_terminal_fonts() -> list[str]:
    """Recommended presets first, then every monospaced face on this machine."""
    installed = _system_families()
    installed_set = set(installed)
    out: list[str] = []
    seen: set[str] = set()
    for name in FONT_PRESETS:
        if name in installed_set and name not in seen:
            out.append(name)
            seen.add(name)
    for name in sorted(f for f in installed if _is_fixed(f)):
        if name not in seen:
            out.append(name)
            seen.add(name)
    # Still offer the remaining presets so the operator can type a known name.
    for name in FONT_PRESETS:
        if name not in seen:
            out.append(name)
            seen.add(name)
    return out or list(FONT_PRESETS)


class SettingsDialog(QDialog):
    def __init__(self, ctx: SessionContext, parent=None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(640, 700)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 16)
        outer.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("h1")
        outer.addWidget(title)

        subtitle = QLabel(
            "Workbench appearance and local-console defaults. "
            "SSH sessions keep the remote host’s own terminal colors."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 8, 2)
        layout.setSpacing(16)

        # --- appearance ------------------------------------------------------
        appearance = QGroupBox("Appearance")
        form = QFormLayout(appearance)
        form.setSpacing(12)
        self.theme = QComboBox()
        for tid, label in THEME_CHOICES:
            self.theme.addItem(label, tid)
        ti = self.theme.findData(ctx.settings.theme)
        self.theme.setCurrentIndex(ti if ti >= 0 else 0)
        form.addRow("Theme", self.theme)

        self.font_family = QComboBox()
        self.font_family.setEditable(True)
        fonts = collect_terminal_fonts()
        self.font_family.addItems(fonts)
        if ctx.settings.font_family:
            self.font_family.setCurrentText(ctx.settings.font_family)
        else:
            preferred = next(
                (f for f in ("DejaVu Sans Mono", "Liberation Mono", "Consolas", "Courier New") if f in fonts),
                fonts[0] if fonts else "",
            )
            self.font_family.setCurrentText(preferred)
        form.addRow("Terminal font", self.font_family)

        self.font_size = QSpinBox()
        self.font_size.setRange(7, 24)
        self.font_size.setValue(ctx.settings.font_size)
        form.addRow("Font size", self.font_size)

        self._font_preview = QLabel("ABCDEFGHIJK  0123456789  ls -la  ~/ops  ERROR  NOMINAL")
        self._font_preview.setObjectName("card")
        self._font_preview.setWordWrap(True)
        self._font_preview.setMinimumHeight(44)
        self._font_preview.setContentsMargins(10, 8, 10, 8)
        form.addRow("Preview", self._font_preview)
        self.font_family.currentTextChanged.connect(lambda _t: self._refresh_font_preview())
        self.font_size.valueChanged.connect(lambda _v: self._refresh_font_preview())
        self._refresh_font_preview()

        note = QLabel(
            "Typefaces listed here are the fonts installed on this workstation. "
            "Nothing extra is downloaded."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)

        self.cursor = QComboBox()
        self.cursor.addItem("Block █", "block")
        self.cursor.addItem("Underline _", "underline")
        self.cursor.addItem("Bar │", "bar")
        ci = self.cursor.findData(ctx.settings.cursor_style)
        self.cursor.setCurrentIndex(ci if ci >= 0 else 0)
        form.addRow("Cursor", self.cursor)
        layout.addWidget(appearance)

        # --- terminal ---------------------------------------------------------
        terminal = QGroupBox("Local terminal")
        tform = QFormLayout(terminal)
        tform.setSpacing(10)
        ssh_note = QLabel(
            "SSH / OpenSSH tabs render the remote VM’s own console palette "
            "(VGA / linux / xterm ANSI). Theme colors are not applied to those sessions."
        )
        ssh_note.setObjectName("muted")
        ssh_note.setWordWrap(True)
        tform.addRow(ssh_note)
        self.scrollback = QSpinBox()
        self.scrollback.setRange(200, 100_000)
        self.scrollback.setSingleStep(500)
        self.scrollback.setValue(ctx.settings.scrollback_lines)
        tform.addRow("Scrollback", self.scrollback)
        self.copy_on_select = QCheckBox("Copy on select — instant copy when you select text")
        self.copy_on_select.setChecked(ctx.settings.copy_on_select)
        self.middle_paste = QCheckBox("Middle-click paste — paste clipboard with middle mouse")
        self.middle_paste.setChecked(ctx.settings.paste_on_middle_click)
        self.confirm_paste = QCheckBox("Confirm multi-line paste — safety check for large pastes")
        self.confirm_paste.setChecked(ctx.settings.confirm_multiline_paste)
        tform.addRow(self.copy_on_select)
        tform.addRow(self.middle_paste)
        tform.addRow(self.confirm_paste)
        layout.addWidget(terminal)

        # --- connection -------------------------------------------------------
        conn = QGroupBox("Connection")
        cform = QFormLayout(conn)
        cform.setSpacing(10)
        self.keepalive = QSpinBox()
        self.keepalive.setRange(5, 300)
        self.keepalive.setValue(ctx.settings.default_keepalive)
        cform.addRow("Keepalive", self.keepalive)
        self.max_attempts = QSpinBox()
        self.max_attempts.setRange(1, 100)
        self.max_attempts.setValue(ctx.settings.reconnect_max_attempts)
        cform.addRow("Reconnect attempts", self.max_attempts)
        self.host_key_policy = QComboBox()
        self.host_key_policy.addItem("TOFU — trust on first use", "accept-new")
        self.host_key_policy.addItem("Strict — always prompt", "strict")
        hi = self.host_key_policy.findData(ctx.settings.host_key_policy)
        self.host_key_policy.setCurrentIndex(hi if hi >= 0 else 0)
        cform.addRow("Host key policy", self.host_key_policy)
        self.rdp_client = QComboBox()
        self.rdp_client.addItem("Built-in — inside app", "embedded")
        self.rdp_client.addItem("External — separate window", "external")
        self.rdp_client.addItem("Automatic", "auto")
        ri = self.rdp_client.findData(ctx.settings.rdp_client)
        self.rdp_client.setCurrentIndex(ri if ri >= 0 else 2)
        cform.addRow("RDP display", self.rdp_client)
        self.rdp_status = QLabel("")
        self.rdp_status.setObjectName("muted")
        self.rdp_status.setWordWrap(True)
        cform.addRow(self.rdp_status)
        self.btn_xwayland = QPushButton("Restart via XWayland now")
        self.btn_xwayland.setObjectName("subtle")
        self.btn_xwayland.clicked.connect(self._restart_via_xwayland)
        self._refresh_rdp_status()
        if self._xwayland_useful:
            cform.addRow(self.btn_xwayland)
        layout.addWidget(conn)

        layout.addStretch(1)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        line.setFixedHeight(1)
        outer.addWidget(line)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setMinimumHeight(36)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("subtle")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setMinimumHeight(36)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _refresh_font_preview(self) -> None:
        family = self.font_family.currentText().strip() or "monospace"
        size = max(7, int(self.font_size.value()))
        font = QFont(family)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setPointSize(size)
        self._font_preview.setFont(font)

    def _refresh_rdp_status(self) -> None:
        from ..protocols.rdp.embed import embed_blocked_on_wayland, embedded_support

        self._xwayland_useful = False
        ok, reason = embedded_support()
        if ok:
            self.rdp_status.setText("In-app display active — remote desktops render inside KB-Remote.")
        elif embed_blocked_on_wayland():
            self._xwayland_useful = True
            self.rdp_status.setText(
                "Wayland session detected: in-app RDP needs X11. KB-Remote can restart\n"
                "through XWayland — it also does so automatically at startup when saved\n"
                "RDP sessions exist."
            )
        elif reason:
            self.rdp_status.setText(reason)
        else:
            self.rdp_status.setText("")
        self.btn_xwayland.setVisible(self._xwayland_useful)

    def _restart_via_xwayland(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from ..protocols.rdp.embed import relaunch_under_x11

        answer = QMessageBox.question(
            self,
            "Restart via XWayland",
            "Restart through XWayland so RDP renders inside the app?\nOpen sessions will be closed.",
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
        s.save(paths.settings_file())
        self.accept()
