"""Application settings dialog — beautiful natural bento layout 2026."""

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
    QHBoxLayout,
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
from .theme import palette


def _system_families() -> list[str]:
    try:
        return list(QFontDatabase.families())
    except Exception:
        return []


def _is_fixed(family: str) -> bool:
    try:
        return bool(QFontDatabase.isFixedPitch(family))
    except Exception:
        key = family.lower()
        return any(tok in key for tok in ("mono", "consol", "courier", "code", "term", "fixed"))


def collect_terminal_fonts() -> list[str]:
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
        self.resize(700, 760)

        pal = palette()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 18)
        outer.setSpacing(16)

        # Header with accent dot
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        dot = QLabel("◉")
        dot.setStyleSheet(f"color: {pal['accent']}; font-size: 16px;")
        header_row.addWidget(dot)
        title = QLabel("Settings")
        title.setObjectName("h1")
        title.setStyleSheet("font-size: 22px; font-weight: 800; letter-spacing: -0.4px;")
        header_row.addWidget(title)
        header_row.addStretch(1)

        # Theme preview pill
        theme_pill = QLabel(f"🌿 {ctx.settings.theme}")
        theme_pill.setStyleSheet(
            f"""
            background: {pal['accent_subtle']};
            border: 1px solid {pal['accent']}35;
            border-radius: 20px;
            padding: 4px 12px;
            color: {pal['accent']};
            font-size: 11.5px;
            font-weight: 700;
            """
        )
        header_row.addWidget(theme_pill)
        outer.addLayout(header_row)

        subtitle = QLabel(
            "Beautiful natural themes — forest, ocean, meadow, desert & more. "
            "SSH sessions keep the remote host's own terminal colors."
        )
        subtitle.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 13px;")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        page = QWidget()
        scroll.setWidget(page)
        outer.addWidget(scroll, 1)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 10, 2)
        layout.setSpacing(18)

        # --- appearance ------------------------------------------------------
        appearance = QGroupBox("🎨 Appearance — Natural Themes")
        form = QFormLayout(appearance)
        form.setSpacing(14)
        form.setContentsMargins(18, 24, 18, 18)

        self.theme = QComboBox()
        self.theme.setMinimumHeight(40)
        for tid, label in THEME_CHOICES:
            self.theme.addItem(label, tid)
        ti = self.theme.findData(ctx.settings.theme)
        self.theme.setCurrentIndex(ti if ti >= 0 else 0)
        # Theme description
        theme_desc = QLabel(
            "🌲 Forest: deep pine & moss  •  🌊 Ocean: Atlantic teal  •  🌅 Sunset: terracotta dusk\n"
            "✨ Aurora: northern lights  •  🌾 Meadow: sage & cream  •  🏜️ Desert: sand & clay"
        )
        theme_desc.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 11px; line-height: 1.4;")
        theme_desc.setWordWrap(True)
        form.addRow("Theme", self.theme)
        form.addRow(theme_desc)

        self.font_family = QComboBox()
        self.font_family.setEditable(True)
        self.font_family.setMinimumHeight(38)
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
        self.font_size.setMinimumHeight(38)
        form.addRow("Font size", self.font_size)

        self._font_preview = QLabel("ABCDEFGHIJK  0123456789  ls -la  ~/ops  ERROR  NOMINAL")
        self._font_preview.setObjectName("card")
        self._font_preview.setWordWrap(True)
        self._font_preview.setMinimumHeight(52)
        self._font_preview.setStyleSheet(
            f"""
            background: {pal['bg3']};
            border: 1.5px solid {pal['border']};
            border-radius: 12px;
            padding: 12px 14px;
            font-size: 13px;
            """
        )
        form.addRow("Preview", self._font_preview)
        self.font_family.currentTextChanged.connect(lambda _t: self._refresh_font_preview())
        self.font_size.valueChanged.connect(lambda _v: self._refresh_font_preview())
        self._refresh_font_preview()

        note = QLabel(
            "Typefaces listed here are the fonts installed on this workstation. "
            "Nothing extra is downloaded — natural & local."
        )
        note.setStyleSheet(f"color: {pal['fg_muted']}; font-size: 11px;")
        note.setWordWrap(True)
        form.addRow(note)

        self.cursor = QComboBox()
        self.cursor.setMinimumHeight(38)
        self.cursor.addItem("Block █", "block")
        self.cursor.addItem("Underline _", "underline")
        self.cursor.addItem("Bar │", "bar")
        ci = self.cursor.findData(ctx.settings.cursor_style)
        self.cursor.setCurrentIndex(ci if ci >= 0 else 0)
        form.addRow("Cursor", self.cursor)
        layout.addWidget(appearance)

        # --- terminal ---------------------------------------------------------
        terminal = QGroupBox("💻 Terminal")
        tform = QFormLayout(terminal)
        tform.setSpacing(12)
        tform.setContentsMargins(18, 24, 18, 18)
        ssh_note = QLabel(
            "SSH / OpenSSH tabs render the remote VM's own console palette "
            "(VGA / linux / xterm ANSI). Theme colors are not applied to those sessions."
        )
        ssh_note.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 12px;")
        ssh_note.setWordWrap(True)
        tform.addRow(ssh_note)
        self.scrollback = QSpinBox()
        self.scrollback.setRange(200, 100_000)
        self.scrollback.setSingleStep(500)
        self.scrollback.setValue(ctx.settings.scrollback_lines)
        self.scrollback.setMinimumHeight(38)
        tform.addRow("Scrollback", self.scrollback)
        self.terminal_backend = QComboBox()
        self.terminal_backend.setMinimumHeight(38)
        self.terminal_backend.addItem("Automatic — native on Linux when available", "auto")
        self.terminal_backend.addItem("Native — QTermWidget/Konsole-style renderer", "native")
        self.terminal_backend.addItem("Python fallback — pyte renderer", "pyte")
        bi = self.terminal_backend.findData(getattr(ctx.settings, "terminal_backend", "auto"))
        self.terminal_backend.setCurrentIndex(bi if bi >= 0 else 0)
        tform.addRow("Terminal engine", self.terminal_backend)
        backend_note = QLabel(
            "The native engine keeps VT parsing, scrollback and painting in compiled code, "
            "like SSH Pilot's Linux VTE path. Install the optional native-terminal extra "
            "to enable it; existing tabs keep their current engine until reopened."
        )
        backend_note.setStyleSheet(f"color: {pal['fg_muted']}; font-size: 11px;")
        backend_note.setWordWrap(True)
        tform.addRow(backend_note)
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
        conn = QGroupBox("🔗 Connection")
        cform = QFormLayout(conn)
        cform.setSpacing(12)
        cform.setContentsMargins(18, 24, 18, 18)
        self.keepalive = QSpinBox()
        self.keepalive.setRange(5, 300)
        self.keepalive.setValue(ctx.settings.default_keepalive)
        self.keepalive.setMinimumHeight(38)
        cform.addRow("Keepalive", self.keepalive)
        self.max_attempts = QSpinBox()
        self.max_attempts.setRange(1, 100)
        self.max_attempts.setValue(ctx.settings.reconnect_max_attempts)
        self.max_attempts.setMinimumHeight(38)
        cform.addRow("Reconnect attempts", self.max_attempts)
        self.host_key_policy = QComboBox()
        self.host_key_policy.setMinimumHeight(38)
        self.host_key_policy.addItem("TOFU — trust on first use", "accept-new")
        self.host_key_policy.addItem("Strict — always prompt", "strict")
        hi = self.host_key_policy.findData(ctx.settings.host_key_policy)
        self.host_key_policy.setCurrentIndex(hi if hi >= 0 else 0)
        cform.addRow("Host key policy", self.host_key_policy)
        self.rdp_client = QComboBox()
        self.rdp_client.setMinimumHeight(38)
        self.rdp_client.addItem("Built-in — inside app", "embedded")
        self.rdp_client.addItem("External — separate window", "external")
        self.rdp_client.addItem("Automatic", "auto")
        ri = self.rdp_client.findData(ctx.settings.rdp_client)
        self.rdp_client.setCurrentIndex(ri if ri >= 0 else 2)
        cform.addRow("RDP display", self.rdp_client)
        self.rdp_status = QLabel("")
        self.rdp_status.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 12px;")
        self.rdp_status.setWordWrap(True)
        cform.addRow(self.rdp_status)
        self.btn_xwayland = QPushButton("Restart via XWayland now")
        self.btn_xwayland.setObjectName("subtle")
        self.btn_xwayland.setMinimumHeight(38)
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
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Save Settings")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setMinimumHeight(42)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setObjectName("subtle")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setMinimumHeight(42)
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
            self.rdp_status.setText("✦ In-app display active — remote desktops render inside KB-Remote.")
        elif embed_blocked_on_wayland():
            self._xwayland_useful = True
            self.rdp_status.setText(
                "Wayland session detected: in-app RDP needs X11. KB-Remote can restart "
                "through XWayland — it also does so automatically at startup when saved "
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
        s.terminal_backend = self.terminal_backend.currentData()
        s.copy_on_select = self.copy_on_select.isChecked()
        s.paste_on_middle_click = self.middle_paste.isChecked()
        s.confirm_multiline_paste = self.confirm_paste.isChecked()
        s.default_keepalive = self.keepalive.value()
        s.reconnect_max_attempts = self.max_attempts.value()
        s.host_key_policy = self.host_key_policy.currentData()
        s.rdp_client = self.rdp_client.currentData()
        s.save(paths.settings_file())
        self.accept()
