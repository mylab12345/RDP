"""Application settings dialog — organized tabbed pages 2026."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from ..core.settings import FONT_PRESETS, THEME_CHOICES
from .theme import PALETTE, palette


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


# ── helpers ──────────────────────────────────────────────────────────────

def _make_label(text: str, *, pal: dict[str, str] | None = None, bold: bool = False, dim: bool = False, muted: bool = False, size: float = 13) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    weight = "700" if bold else "400"
    if dim:
        col = (pal or {})["fg_dim"] if pal else "#9aa3b8"
    elif muted:
        col = (pal or {})["fg_muted"] if pal else "#636c82"
    else:
        col = (pal or {})["fg"] if pal else "#e8eaf0"
    lbl.setStyleSheet(f"color: {col}; font-size: {size}px; font-weight: {weight};")
    return lbl


def _make_separator(pal: dict[str, str]) -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet(f"background: {pal['border_subtle']}; border: none;")
    return f


def _make_scroll_page() -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    inner = QWidget()
    scroll.setWidget(inner)
    lay = QVBoxLayout(inner)
    lay.setContentsMargins(4, 8, 14, 8)
    lay.setSpacing(18)
    return scroll, lay


def _make_group(title: str, pal: dict[str, str]) -> tuple[QFrame, QVBoxLayout]:
    """Create a card-style group with title pill."""
    card = QWidget()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QWidget#card {{ background: {pal['bg2']}; border: 1px solid {pal['border']}; border-radius: 8px; }}"
    )
    v = QVBoxLayout(card)
    v.setContentsMargins(18, 18, 18, 16)
    v.setSpacing(10)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {pal['fg_dim']}; font-size: 11.5px; font-weight: 700; "
        f"letter-spacing: 0.4px; padding-bottom: 4px;"
    )
    v.addWidget(title_lbl)
    return card, v


def _make_row_label(text: str, pal: dict[str, str]) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {pal['fg']}; font-size: 13px; font-weight: 500;")
    return lbl


def _make_hint(text: str, pal: dict[str, str]) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {pal['fg_muted']}; font-size: 11px; margin-top: -2px;")
    return lbl


# ── theme preview card ───────────────────────────────────────────────────

class _ThemeCard(QFrame):
    """Small preview card for a single theme."""

    def __init__(self, tid: str, label: str, selected: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme_id = tid
        self._selected = selected
        pal_data = PALETTE.get(tid, PALETTE["dark"])
        accent = pal_data["accent"]
        bg = pal_data["bg"]
        fg = pal_data["fg"]

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(80)
        self.setMinimumWidth(130)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

        border = f"2px solid {accent}" if selected else f"1px solid {pal_data.get('border', '#333')}"
        self.setStyleSheet(
            f"""
            _ThemeCard {{
                background: {bg};
                border: {border};
                border-radius: 8px;
            }}
            _ThemeCard:hover {{
                border: 2px solid {accent};
            }}
            """
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)

        dot = QLabel("●")
        dot.setFixedWidth(18)
        dot.setStyleSheet(f"color: {accent}; font-size: 14px; background: transparent; border: none;")
        top.addWidget(dot)

        name = QLabel(label.split("—")[0].strip() if "—" in label else label.split("·")[0].strip())
        name.setStyleSheet(
            f"color: {fg}; font-size: 11.5px; font-weight: 700; background: transparent; border: none;"
        )
        top.addWidget(name)
        top.addStretch(1)
        lay.addLayout(top)

        preview = QLabel(f"Aa  {bg}  {fg}")
        preview.setStyleSheet(
            f"color: {pal_data['fg_dim']}; font-size: 9.5px; background: transparent; border: none;"
        )
        lay.addWidget(preview)

        if selected:
            check = QLabel("✓")
            check.setStyleSheet(
                f"color: {accent}; font-size: 12px; font-weight: 800; background: transparent; border: none;"
            )
            check.setFixedWidth(16)
            top.insertWidget(0, check)

    def mousePressEvent(self, ev) -> None:
        super().mousePressEvent(ev)


# ── main dialog ──────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None) -> None:
        super().__init__(parent)
        if hasattr(settings, "settings"):
            settings = settings.settings
        self.result_settings = settings
        self._selected_theme = settings.theme
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(780, 820)

        pal = palette()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 18)
        outer.setSpacing(16)

        # ── header ──
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        title = QLabel("Settings")
        title.setObjectName("h1")
        title.setStyleSheet("font-size: 16px; font-weight: 700; letter-spacing: -0.2px;")
        header_row.addWidget(title)
        header_row.addStretch(1)
        outer.addLayout(header_row)

        # ── tab widget (left-side tab bar) ──
        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.West)
        tabs.setDocumentMode(True)
        tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{ border: none; background: transparent; }}
            QTabBar {{
                background: {pal['bg2']};
                qproperty-drawBase: 0;
                border: 1px solid {pal['border']};
                border-radius: 8px;
                padding: 6px 4px;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {pal['fg_dim']};
                padding: 10px 16px;
                border: none;
                border-left: 3px solid transparent;
                border-radius: 0px;
                margin: 2px 0px;
                font-weight: 600;
                font-size: 12.5px;
                min-width: 100px;
                text-align: left;
            }}
            QTabBar::tab:selected {{
                background: {pal['accent_subtle']};
                color: {pal['accent']};
                border-left: 3px solid {pal['accent']};
                font-weight: 700;
            }}
            QTabBar::tab:hover:!selected {{
                background: {pal['bg3']};
                color: {pal['fg']};
            }}
            """
        )
        outer.addWidget(tabs, 1)

        # ── build all pages ──
        self._theme_cards: list[_ThemeCard] = []
        self._rdp_tab_idx = -1
        self._build_general_tab(tabs, settings, pal)
        self._build_terminal_tab(tabs, settings, pal)
        self._build_connections_tab(tabs, settings, pal)
        self._build_security_tab(tabs, settings, pal)
        self._build_rdp_tab(tabs, settings, pal)

        # ── footer ──
        outer.addWidget(_make_separator(pal))
        footer = QHBoxLayout()
        footer.setSpacing(12)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setObjectName("ghost")
        reset_btn.setMinimumHeight(40)
        reset_btn.clicked.connect(self._reset_defaults)
        footer.addWidget(reset_btn)
        footer.addStretch(1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("subtle")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.clicked.connect(self.reject)
        footer.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primary")
        save_btn.setMinimumHeight(40)
        save_btn.clicked.connect(self._save)
        footer.addWidget(save_btn)

        outer.addLayout(footer)

        # Switch to RDP tab if the xwayland button needs to be visible
        if getattr(self, "_xwayland_useful", False) and self._rdp_tab_idx >= 0:
            tabs.setCurrentIndex(self._rdp_tab_idx)

    # ── General tab ──────────────────────────────────────────────────────

    def _build_general_tab(self, tabs: QTabWidget, settings, pal: dict[str, str]) -> None:
        scroll, lay = _make_scroll_page()
        tabs.addTab(scroll, "  General  ")

        # -- theme card grid --
        grp, grp_lay = _make_group("Theme", pal)
        grp_lay.addSpacing(6)

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (tid, label) in enumerate(THEME_CHOICES):
            card = _ThemeCard(tid, label, selected=(tid == settings.theme))
            card._theme_click_handler = self._on_theme_card_clicked
            card.mousePressEvent = lambda ev, c=card: c._theme_click_handler(c.theme_id)
            self._theme_cards.append(card)
            grid.addWidget(card, i // 3, i % 3)
        grid_widget = QWidget()
        grid_widget.setLayout(grid)
        grid_widget.setStyleSheet("background: transparent; border: none;")
        grp_lay.addWidget(grid_widget)

        note = _make_hint(
            "SSH / OpenSSH tabs render the remote host's own console palette — theme colors "
            "are not applied to those sessions.",
            pal,
        )
        grp_lay.addWidget(note)
        lay.addWidget(grp)

        # -- font --
        grp2, grp2_lay = _make_group("Typography", pal)

        r1 = QHBoxLayout()
        r1.setSpacing(12)
        r1.addWidget(_make_row_label("Font family", pal))
        self.font_family = QComboBox()
        self.font_family.setEditable(True)
        self.font_family.setMinimumHeight(38)
        fonts = collect_terminal_fonts()
        self.font_family.addItems(fonts)
        if settings.font_family:
            self.font_family.setCurrentText(settings.font_family)
        else:
            preferred = next(
                (f for f in ("DejaVu Sans Mono", "Liberation Mono", "Consolas", "Courier New") if f in fonts),
                fonts[0] if fonts else "",
            )
            self.font_family.setCurrentText(preferred)
        r1.addWidget(self.font_family, 1)

        r1.addWidget(_make_row_label("Size", pal))
        self.font_size = QSpinBox()
        self.font_size.setRange(7, 24)
        self.font_size.setValue(settings.font_size)
        self.font_size.setMinimumHeight(38)
        self.font_size.setFixedWidth(80)
        r1.addWidget(self.font_size)
        grp2_lay.addLayout(r1)

        # font preview
        self._font_preview = QLabel("ABCDEFGHIJK  0123456789  ls -la  ~/ops  ERROR  NOMINAL")
        self._font_preview.setObjectName("card")
        self._font_preview.setWordWrap(True)
        self._font_preview.setMinimumHeight(52)
        self._font_preview.setStyleSheet(
            f"""
            background: {pal['bg3']};
            border: 1px solid {pal['border']};
            border-radius: 6px;
            padding: 12px 14px;
            font-size: 13px;
            """
        )
        grp2_lay.addWidget(self._font_preview)
        self.font_family.currentTextChanged.connect(lambda _t: self._refresh_font_preview())
        self.font_size.valueChanged.connect(lambda _v: self._refresh_font_preview())
        self._refresh_font_preview()

        note2 = _make_hint("Typefaces listed are system-installed fonts — nothing extra is downloaded.", pal)
        grp2_lay.addWidget(note2)
        lay.addWidget(grp2)

        # -- cursor --
        grp3, grp3_lay = _make_group("Cursor", pal)
        self.cursor = QComboBox()
        self.cursor.setMinimumHeight(38)
        self.cursor.addItem("Block", "block")
        self.cursor.addItem("Underline", "underline")
        self.cursor.addItem("Bar", "bar")
        ci = self.cursor.findData(settings.cursor_style)
        self.cursor.setCurrentIndex(ci if ci >= 0 else 0)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_make_row_label("Cursor style", pal))
        row.addWidget(self.cursor, 1)
        grp3_lay.addLayout(row)
        lay.addWidget(grp3)

        lay.addStretch(1)

    # ── Terminal tab ─────────────────────────────────────────────────────

    def _build_terminal_tab(self, tabs: QTabWidget, settings, pal: dict[str, str]) -> None:
        scroll, lay = _make_scroll_page()
        tabs.addTab(scroll, "  Terminal  ")

        # -- buffer --
        grp, grp_lay = _make_group("Buffer & Rendering", pal)
        self.scrollback = QSpinBox()
        self.scrollback.setRange(200, 100_000)
        self.scrollback.setSingleStep(500)
        self.scrollback.setValue(settings.scrollback_lines)
        self.scrollback.setMinimumHeight(38)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_make_row_label("Scrollback lines", pal))
        row.addWidget(self.scrollback, 1)
        grp_lay.addLayout(row)
        grp_lay.addWidget(_make_hint("Number of lines kept in terminal scrollback history.", pal))

        grp_lay.addWidget(_make_separator(pal))

        self.terminal_backend = QComboBox()
        self.terminal_backend.setMinimumHeight(38)
        self.terminal_backend.addItem("Automatic — native on Linux when available", "auto")
        self.terminal_backend.addItem("Native — QTermWidget/Konsole-style renderer", "native")
        self.terminal_backend.addItem("Python fallback — pyte renderer", "pyte")
        bi = self.terminal_backend.findData(getattr(settings, "terminal_backend", "auto"))
        self.terminal_backend.setCurrentIndex(bi if bi >= 0 else 0)
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(_make_row_label("Terminal engine", pal))
        row2.addWidget(self.terminal_backend, 1)
        grp_lay.addLayout(row2)
        grp_lay.addWidget(_make_hint(
            "The native engine keeps VT parsing and painting in compiled code. "
            "Install the optional native-terminal extra to enable it.",
            pal,
        ))
        lay.addWidget(grp)

        # -- cursor (also here for accessibility) --
        grp_c, grp_c_lay = _make_group("Cursor", pal)
        self.cursor_tab = QComboBox()
        self.cursor_tab.setMinimumHeight(38)
        self.cursor_tab.addItem("Block", "block")
        self.cursor_tab.addItem("Underline", "underline")
        self.cursor_tab.addItem("Bar", "bar")
        ci = self.cursor_tab.findData(settings.cursor_style)
        self.cursor_tab.setCurrentIndex(ci if ci >= 0 else 0)
        row_c = QHBoxLayout()
        row_c.setSpacing(12)
        row_c.addWidget(_make_row_label("Cursor style", pal))
        row_c.addWidget(self.cursor_tab, 1)
        grp_c_lay.addLayout(row_c)
        lay.addWidget(grp_c)

        # -- copy / paste --
        grp2, grp2_lay = _make_group("Copy & Paste", pal)
        self.copy_on_select = QCheckBox("Copy on select — instant copy when you select text")
        self.copy_on_select.setChecked(settings.copy_on_select)
        self.copy_on_select.setMinimumHeight(32)
        grp2_lay.addWidget(self.copy_on_select)

        self.middle_paste = QCheckBox("Middle-click paste — paste clipboard with middle mouse button")
        self.middle_paste.setChecked(settings.paste_on_middle_click)
        self.middle_paste.setMinimumHeight(32)
        grp2_lay.addWidget(self.middle_paste)

        self.confirm_paste = QCheckBox("Confirm multi-line paste — safety check for large pastes")
        self.confirm_paste.setChecked(settings.confirm_multiline_paste)
        self.confirm_paste.setMinimumHeight(32)
        grp2_lay.addWidget(self.confirm_paste)
        lay.addWidget(grp2)

        # -- bell --
        grp3, grp3_lay = _make_group("Bell", pal)
        self.bell_flash = QCheckBox("Visual bell — flash the terminal on bell character")
        self.bell_flash.setChecked(getattr(settings, "bell_flash", True))
        self.bell_flash.setMinimumHeight(32)
        grp3_lay.addWidget(self.bell_flash)
        lay.addWidget(grp3)

        lay.addStretch(1)

    # ── Connections tab ──────────────────────────────────────────────────

    def _build_connections_tab(self, tabs: QTabWidget, settings, pal: dict[str, str]) -> None:
        scroll, lay = _make_scroll_page()
        tabs.addTab(scroll, "  Connections  ")

        # -- keepalive --
        grp, grp_lay = _make_group("Keepalive", pal)
        self.keepalive = QSpinBox()
        self.keepalive.setRange(5, 300)
        self.keepalive.setValue(settings.default_keepalive)
        self.keepalive.setMinimumHeight(38)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_make_row_label("Interval (seconds)", pal))
        row.addWidget(self.keepalive, 1)
        grp_lay.addLayout(row)
        grp_lay.addWidget(_make_hint("SSH keepalive interval. Set to 0 to disable.", pal))
        lay.addWidget(grp)

        # -- reconnect --
        grp2, grp2_lay = _make_group("Auto-Reconnect", pal)

        self.auto_reconnect = QCheckBox("Enable auto-reconnect on connection drop")
        self.auto_reconnect.setChecked(getattr(settings, "default_auto_reconnect", True))
        self.auto_reconnect.setMinimumHeight(32)
        grp2_lay.addWidget(self.auto_reconnect)

        grp2_lay.addWidget(_make_separator(pal))

        self.max_attempts = QSpinBox()
        self.max_attempts.setRange(1, 100)
        self.max_attempts.setValue(settings.reconnect_max_attempts)
        self.max_attempts.setMinimumHeight(38)
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(_make_row_label("Max attempts", pal))
        row2.addWidget(self.max_attempts, 1)
        grp2_lay.addLayout(row2)

        self.reconnect_base_delay = QDoubleSpinBox()
        self.reconnect_base_delay.setRange(0.2, 30.0)
        self.reconnect_base_delay.setSingleStep(0.5)
        self.reconnect_base_delay.setDecimals(1)
        self.reconnect_base_delay.setValue(getattr(settings, "reconnect_base_delay", 1.5))
        self.reconnect_base_delay.setMinimumHeight(38)
        row3 = QHBoxLayout()
        row3.setSpacing(12)
        row3.addWidget(_make_row_label("Base delay (seconds)", pal))
        row3.addWidget(self.reconnect_base_delay, 1)
        grp2_lay.addLayout(row3)

        self.reconnect_max_delay = QDoubleSpinBox()
        self.reconnect_max_delay.setRange(1.0, 600.0)
        self.reconnect_max_delay.setSingleStep(5.0)
        self.reconnect_max_delay.setDecimals(1)
        self.reconnect_max_delay.setValue(getattr(settings, "reconnect_max_delay", 60.0))
        self.reconnect_max_delay.setMinimumHeight(38)
        row4 = QHBoxLayout()
        row4.setSpacing(12)
        row4.addWidget(_make_row_label("Max delay (seconds)", pal))
        row4.addWidget(self.reconnect_max_delay, 1)
        grp2_lay.addLayout(row4)

        grp2_lay.addWidget(_make_hint(
            "Exponential backoff: base delay doubles each attempt, capped at max delay.",
            pal,
        ))
        lay.addWidget(grp2)

        # -- host key --
        grp3, grp3_lay = _make_group("Host Key Verification", pal)
        self.host_key_policy = QComboBox()
        self.host_key_policy.setMinimumHeight(38)
        self.host_key_policy.addItem("TOFU — trust on first use", "accept-new")
        self.host_key_policy.addItem("Strict — always prompt on change", "strict")
        hi = self.host_key_policy.findData(settings.host_key_policy)
        self.host_key_policy.setCurrentIndex(hi if hi >= 0 else 0)
        row5 = QHBoxLayout()
        row5.setSpacing(12)
        row5.addWidget(_make_row_label("Policy", pal))
        row5.addWidget(self.host_key_policy, 1)
        grp3_lay.addLayout(row5)
        grp3_lay.addWidget(_make_hint(
            "TOFU remembers keys after first connection. Strict warns if the key ever changes.",
            pal,
        ))
        lay.addWidget(grp3)

        lay.addStretch(1)

    # ── Security tab ─────────────────────────────────────────────────────

    def _build_security_tab(self, tabs: QTabWidget, settings, pal: dict[str, str]) -> None:
        scroll, lay = _make_scroll_page()
        tabs.addTab(scroll, "  Security  ")

        # -- vault --
        grp, grp_lay = _make_group("Vault Auto-Lock", pal)
        self.vault_autolock = QSpinBox()
        self.vault_autolock.setRange(0, 120)
        self.vault_autolock.setSuffix(" min")
        self.vault_autolock.setValue(getattr(settings, "vault_autolock_minutes", 15))
        self.vault_autolock.setMinimumHeight(38)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_make_row_label("Lock after inactivity", pal))
        row.addWidget(self.vault_autolock, 1)
        grp_lay.addLayout(row)
        grp_lay.addWidget(_make_hint(
            "Automatically lock the credential vault after this many minutes of inactivity. "
            "Set to 0 to disable.",
            pal,
        ))
        lay.addWidget(grp)

        # -- KDF --
        grp2, grp2_lay = _make_group("Encryption", pal)
        self.kdf_iterations = QSpinBox()
        self.kdf_iterations.setRange(100_000, 2_000_000)
        self.kdf_iterations.setSingleStep(10_000)
        self.kdf_iterations.setValue(getattr(settings, "kdf_iterations", 310_000))
        self.kdf_iterations.setMinimumHeight(38)
        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.addWidget(_make_row_label("PBKDF2 iterations", pal))
        row2.addWidget(self.kdf_iterations, 1)
        grp2_lay.addLayout(row2)
        grp2_lay.addWidget(_make_hint(
            "Higher values slow brute-force attacks but increase unlock time. "
            "OWASP 2023 minimum: 310 000 for PBKDF2-SHA256.",
            pal,
        ))
        lay.addWidget(grp2)

        lay.addStretch(1)

    # ── RDP tab ──────────────────────────────────────────────────────────

    def _build_rdp_tab(self, tabs: QTabWidget, settings, pal: dict[str, str]) -> None:
        scroll, lay = _make_scroll_page()
        self._rdp_tab_idx = tabs.count()
        tabs.addTab(scroll, "  RDP  ")

        grp, grp_lay = _make_group("RDP Client Mode", pal)

        self.rdp_client = QComboBox()
        self.rdp_client.setMinimumHeight(38)
        self.rdp_client.addItem("Automatic — built-in when possible", "auto")
        self.rdp_client.addItem("Embedded — render inside the app", "embedded")
        self.rdp_client.addItem("External — open in a separate window", "external")
        ri = self.rdp_client.findData(settings.rdp_client)
        self.rdp_client.setCurrentIndex(ri if ri >= 0 else 0)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(_make_row_label("Display mode", pal))
        row.addWidget(self.rdp_client, 1)
        grp_lay.addLayout(row)

        self.rdp_status = QLabel("")
        self.rdp_status.setStyleSheet(f"color: {pal['fg_dim']}; font-size: 12px;")
        self.rdp_status.setWordWrap(True)
        grp_lay.addWidget(self.rdp_status)

        self.btn_xwayland = QPushButton("Restart via XWayland now")
        self.btn_xwayland.setObjectName("subtle")
        self.btn_xwayland.setMinimumHeight(38)
        self.btn_xwayland.clicked.connect(self._restart_via_xwayland)
        self._refresh_rdp_status()
        if self._xwayland_useful:
            grp_lay.addWidget(self.btn_xwayland)

        grp_lay.addWidget(_make_separator(pal))
        grp_lay.addWidget(_make_hint(
            "Embedded mode renders RDP inside KB-Remote using FreeRDP. "
            "External mode opens an xfreerdp process in a separate window.",
            pal,
        ))
        lay.addWidget(grp)

        lay.addStretch(1)

    # ── helpers ──────────────────────────────────────────────────────────

    def _on_theme_card_clicked(self, theme_id: str) -> None:
        self._selected_theme = theme_id
        for card in self._theme_cards:
            card._selected = (card.theme_id == theme_id)
            pal_data = PALETTE.get(card.theme_id, PALETTE["dark"])
            border = f"2px solid {pal_data['accent']}" if card.theme_id == theme_id else f"1px solid {pal_data.get('border', '#333')}"
            card.setStyleSheet(
                f"""
                _ThemeCard {{
                    background: {pal_data['bg']};
                    border: {border};
                    border-radius: 8px;
                }}
                _ThemeCard:hover {{
                    border: 2px solid {pal_data['accent']};
                }}
                """
            )

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

    def _reset_defaults(self) -> None:
        from ..core.settings import Settings

        defaults = Settings()
        self.result_settings = defaults
        self._selected_theme = defaults.theme
        self.font_family.setCurrentText(defaults.font_family or "")
        self.font_size.setValue(defaults.font_size)
        self.cursor.setCurrentIndex(self.cursor.findData(defaults.cursor_style))
        self.cursor_tab.setCurrentIndex(self.cursor_tab.findData(defaults.cursor_style))
        self.scrollback.setValue(defaults.scrollback_lines)
        self.terminal_backend.setCurrentIndex(self.terminal_backend.findData(defaults.terminal_backend))
        self.copy_on_select.setChecked(defaults.copy_on_select)
        self.middle_paste.setChecked(defaults.paste_on_middle_click)
        self.confirm_paste.setChecked(defaults.confirm_multiline_paste)
        self.bell_flash.setChecked(defaults.bell_flash)
        self.keepalive.setValue(defaults.default_keepalive)
        self.auto_reconnect.setChecked(defaults.default_auto_reconnect)
        self.max_attempts.setValue(defaults.reconnect_max_attempts)
        self.reconnect_base_delay.setValue(defaults.reconnect_base_delay)
        self.reconnect_max_delay.setValue(defaults.reconnect_max_delay)
        self.host_key_policy.setCurrentIndex(self.host_key_policy.findData(defaults.host_key_policy))
        self.vault_autolock.setValue(defaults.vault_autolock_minutes)
        self.kdf_iterations.setValue(defaults.kdf_iterations)
        self.rdp_client.setCurrentIndex(self.rdp_client.findData(defaults.rdp_client))
        for _card in self._theme_cards:
            self._on_theme_card_clicked(defaults.theme)

    def _save(self) -> None:
        s = self.result_settings
        s.theme = self._selected_theme
        s.font_family = self.font_family.currentText()
        s.font_size = self.font_size.value()
        s.cursor_style = self.cursor_tab.currentData() or self.cursor.currentData()
        s.scrollback_lines = self.scrollback.value()
        s.terminal_backend = self.terminal_backend.currentData()
        s.copy_on_select = self.copy_on_select.isChecked()
        s.paste_on_middle_click = self.middle_paste.isChecked()
        s.confirm_multiline_paste = self.confirm_paste.isChecked()
        s.bell_flash = self.bell_flash.isChecked()
        s.default_keepalive = self.keepalive.value()
        s.default_auto_reconnect = self.auto_reconnect.isChecked()
        s.reconnect_max_attempts = self.max_attempts.value()
        s.reconnect_base_delay = self.reconnect_base_delay.value()
        s.reconnect_max_delay = self.reconnect_max_delay.value()
        s.host_key_policy = self.host_key_policy.currentData()
        s.vault_autolock_minutes = self.vault_autolock.value()
        s.kdf_iterations = self.kdf_iterations.value()
        s.rdp_client = self.rdp_client.currentData()
        s.save(paths.settings_file())
        self.accept()
