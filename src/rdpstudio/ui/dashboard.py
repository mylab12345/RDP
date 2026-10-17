"""Welcome-dashboard builders, moved verbatim from MainWindow (ARCH-02).

Mixin methods — ``self`` is the MainWindow at runtime.

The dashboard is user-customisable: Settings → General → *Customize
dashboard…* (or the *Customize…* button on the dashboard itself) chooses
which sections are visible and which launcher tiles appear, in which order
(see ``core.settings.DEFAULT_DASHBOARD_LAYOUT``). Tiles flow-wrap so the
page stays usable on narrow windows.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from ..core import paths
from ..core.log import get_logger
from ..core.settings import DASHBOARD_TILE_IDS, coerce_dashboard_layout
from . import theme
from .theme import icon, palette, protocol_badge, solid_on
from .widgets import FlowLayout, animate_in, install_hover_shadow

log = get_logger("ui.dashboard")

# Launcher tiles the dashboard can show — id → presentation + MainWindow
# method. The order here is the order in the Customize dialog's list.
DASHBOARD_TILES: dict[str, dict] = {
    "new_session": {
        "method": "new_session",
        "icon": "plus",
        "label": "New session",
        "caption": "SSH · RDP · more",
        "tooltip": "Create a new connection (Ctrl+N)",
    },
    "local_terminal": {
        "method": "open_local_terminal",
        "icon": "console",
        "label": "Local terminal",
        "caption": "Start a shell",
        "tooltip": "Open a local terminal (Ctrl+Shift+T)",
    },
    "commands": {
        "method": "open_command_palette",
        "icon": "search",
        "label": "Commands",
        "caption": "Palette · switcher",
        "tooltip": "Search commands & sessions (Ctrl+P / Ctrl+K)",
    },
    "settings": {
        "method": "open_settings",
        "icon": "gear",
        "label": "Settings",
        "caption": "Themes · fonts · keys",
        "tooltip": "Configure KB-Remote (Ctrl+,)",
    },
    "network_tools": {
        "method": "open_network_tools",
        "icon": "server",
        "label": "Network tools",
        "caption": "Scanner · ping · DNS",
        "tooltip": "Port scanner, ping and DNS diagnostics (Ctrl+Shift+N)",
    },
    "keys": {
        "method": "open_key_utility",
        "icon": "key",
        "label": "SSH keys",
        "caption": "Generate · convert",
        "tooltip": "SSH key utility & converter (Ctrl+Shift+U)",
    },
    "rdp_servers": {
        "method": "open_rdp_server_manager",
        "icon": "windows",
        "label": "RDP servers",
        "caption": "Local RDP listener",
        "tooltip": "Check or enable the local RDP server",
    },
    "tunnels": {
        "method": "open_tunnels_dialog",
        "icon": "transfer",
        "label": "Tunnels",
        "caption": "Port forwarding",
        "tooltip": "SSH tunnels for the active session",
    },
    "cluster": {
        "method": "open_cluster_runner",
        "icon": "plug",
        "label": "Cluster runner",
        "caption": "Run on many hosts",
        "tooltip": "Run a command across many saved sessions",
    },
    "new_rdp": {
        "method": "new_rdp_session",
        "icon": "windows",
        "label": "New RDP desktop",
        "caption": "Windows · xrdp",
        "tooltip": "Create or connect to a remote desktop (RDP 3389)",
    },
    "activity_log": {
        "method": "open_activity_log",
        "icon": "activity",
        "label": "Activity & status",
        "caption": "Live event log",
        "tooltip": "View real-time connection status & activity log (Ctrl+Shift+A)",
    },
    "support_chat": {
        "method": "open_support_chat",
        "icon": "help",
        "label": "Support chat",
        "caption": "Troubleshooting",
        "tooltip": "Open in-session support & troubleshooting chat (Ctrl+Shift+H)",
    },
    "onboarding": {
        "method": "open_onboarding_guide",
        "icon": "star",
        "label": "Interactive tour",
        "caption": "Onboarding guide",
        "tooltip": "Walk through KB-Remote features step by step",
    },
    "feedback": {
        "method": "open_feedback_dialog",
        "icon": "edit",
        "label": "Send feedback",
        "caption": "Suggest features",
        "tooltip": "Suggest an improvement or report an issue (Ctrl+Shift+F)",
    },
}


def _make_activatable(
    frame: QFrame,
    callback,
    *,
    accessible_name: str = "",
    tooltip: str = "",
) -> QFrame:
    """Make a card frame mouse- *and* keyboard-activatable.

    Accessibility: the card takes keyboard focus (with a visible focus ring
    from the global QSS) and activates on Enter/Space, so the dashboard is
    fully usable without a mouse. Screen readers get a name and a tooltip.
    """
    frame.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        frame.setToolTip(tooltip)
    if accessible_name:
        frame.setAccessibleName(accessible_name)
        frame.setAccessibleDescription(tooltip or accessible_name)
    frame.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    frame.mousePressEvent = lambda _e, c=callback: c()

    def _key(event, c=callback, w=frame):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            c()
            event.accept()
        else:
            QFrame.keyPressEvent(w, event)

    frame.keyPressEvent = _key
    return frame


class DashboardCustomizeDialog(QDialog):
    """Choose the dashboard's sections and launcher tiles.

    ``save_to_disk=True`` (dashboard path) writes straight into the live
    settings and persists them; ``save_to_disk=False`` (Settings-dialog path)
    only fills :attr:`result_layout` so the caller can merge it into its own
    candidate settings object. ``on_apply`` runs after a successful accept.
    """

    def __init__(self, settings, parent=None, *, save_to_disk: bool = True, on_apply=None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._save_to_disk = save_to_disk
        self._on_apply = on_apply
        self.result_layout: dict = coerce_dashboard_layout(
            getattr(settings, "dashboard_layout", None)
        )
        self.setWindowTitle("Customize dashboard")
        self.setModal(True)
        self.resize(470, 540)

        pal = palette()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        title = QLabel("Customize dashboard")
        title.setObjectName("h1")
        outer.addWidget(title)
        hint = QLabel(
            "Choose the sections and launcher tiles on the welcome dashboard. "
            "Changes apply immediately."
        )
        hint.setObjectName("caption")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        # ── sections ──
        sec_card = QWidget()
        sec_card.setObjectName("card")
        sec_lay = QVBoxLayout(sec_card)
        sec_lay.setContentsMargins(14, 12, 14, 12)
        sec_lay.setSpacing(8)
        sec_title = QLabel("Sections")
        sec_title.setStyleSheet(f"color: {pal['fg']}; font-size: 13px; font-weight: 600;")
        sec_lay.addWidget(sec_title)

        def _section_checkbox(label: str, key: str, tip: str) -> QCheckBox:
            cb = QCheckBox(label)
            cb.setChecked(bool(self.result_layout.get(key, True)))
            cb.setToolTip(tip)
            cb.setMinimumHeight(26)
            sec_lay.addWidget(cb)
            return cb

        self._cb_quick = _section_checkbox(
            "Quick connect field", "show_quick_connect",
            "The hero user@host input at the top of the dashboard",
        )
        self._cb_actions = _section_checkbox(
            "Launcher tiles", "show_actions",
            "The row of action tiles (new session, terminal, …)",
        )
        self._cb_recents = _section_checkbox(
            "Recent sessions", "show_recents",
            "The recently-used sessions list",
        )
        self._cb_shortcuts = _section_checkbox(
            "Keyboard shortcuts", "show_shortcuts",
            "The keyboard-shortcut chips at the bottom",
        )
        outer.addWidget(sec_card)

        # ── launcher tiles ──
        tile_card = QWidget()
        tile_card.setObjectName("card")
        tile_lay = QVBoxLayout(tile_card)
        tile_lay.setContentsMargins(14, 12, 14, 12)
        tile_lay.setSpacing(8)
        tile_title = QLabel("Launcher tiles")
        tile_title.setStyleSheet(f"color: {pal['fg']}; font-size: 13px; font-weight: 600;")
        tile_lay.addWidget(tile_title)
        tile_hint = QLabel("Checked tiles appear on the dashboard, in list order.")
        tile_hint.setObjectName("caption")
        tile_hint.setWordWrap(True)
        tile_lay.addWidget(tile_hint)

        current_tiles = list(self.result_layout.get("tiles") or [])
        self._tile_list = QListWidget()
        self._tile_list.setObjectName("dashTileList")
        self._tile_list.setAccessibleName("Dashboard launcher tiles")
        self._tile_list.setToolTip("Check the tiles to show; reorder with the buttons below")
        for tid in DASHBOARD_TILE_IDS:
            spec = DASHBOARD_TILES[tid]
            item = QListWidgetItem(spec["label"])
            item.setData(Qt.ItemDataRole.UserRole, tid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if tid in current_tiles else Qt.CheckState.Unchecked
            )
            item.setToolTip(spec["tooltip"])
            self._tile_list.addItem(item)
        tile_lay.addWidget(self._tile_list, 1)

        reorder_row = QHBoxLayout()
        reorder_row.setSpacing(8)
        reorder_row.addStretch(1)
        self._btn_up = QPushButton("Move up")
        self._btn_up.setObjectName("subtle")
        self._btn_up.setToolTip("Move the selected tile up (shown earlier)")
        self._btn_up.clicked.connect(lambda: self._move_selected(-1))
        reorder_row.addWidget(self._btn_up)
        self._btn_down = QPushButton("Move down")
        self._btn_down.setObjectName("subtle")
        self._btn_down.setToolTip("Move the selected tile down (shown later)")
        self._btn_down.clicked.connect(lambda: self._move_selected(1))
        reorder_row.addWidget(self._btn_down)
        tile_lay.addLayout(reorder_row)
        outer.addWidget(tile_card, 1)

        # ── footer ──
        footer = QHBoxLayout()
        footer.setSpacing(10)
        footer.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("subtle")
        cancel.setMinimumHeight(34)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("primary")
        apply_btn.setMinimumHeight(34)
        apply_btn.setToolTip("Apply the dashboard layout")
        apply_btn.clicked.connect(self.accept)
        footer.addWidget(apply_btn)
        outer.addLayout(footer)

    def _move_selected(self, delta: int) -> None:
        row = self._tile_list.currentRow()
        new = row + delta
        if row < 0 or not (0 <= new < self._tile_list.count()):
            return
        item = self._tile_list.takeItem(row)
        self._tile_list.insertItem(new, item)
        self._tile_list.setCurrentRow(new)

    def _collect(self) -> dict:
        tiles: list[str] = []
        for i in range(self._tile_list.count()):
            item = self._tile_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                tid = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(tid, str):
                    tiles.append(tid)
        return coerce_dashboard_layout(
            {
                "show_quick_connect": self._cb_quick.isChecked(),
                "show_actions": self._cb_actions.isChecked(),
                "show_recents": self._cb_recents.isChecked(),
                "show_shortcuts": self._cb_shortcuts.isChecked(),
                "tiles": tiles,
            }
        )

    def accept(self) -> None:  # noqa: N802 — Qt naming
        self.result_layout = self._collect()
        if self._save_to_disk:
            self._settings.dashboard_layout = self.result_layout
            try:
                self._settings.save(paths.settings_file())
            except OSError:
                log.exception("could not persist the dashboard layout")
        if self._on_apply is not None:
            self._on_apply()
        super().accept()


class DashboardMixin:
    """Builds the welcome dashboard tab (no state of its own)."""

    def _dashboard_layout(self) -> dict:
        """Sanitised dashboard personalisation (never raises on bad data)."""
        settings = getattr(getattr(self, "ctx", None), "settings", None)
        return coerce_dashboard_layout(getattr(settings, "dashboard_layout", None))

    def _build_dashboard(self) -> QWidget:
        """Modern welcome page shown when no tabs are open.

        A document card with the app identity, a prominent quick connect
        field, a row of launcher tiles, the recent-sessions list and
        keyboard shortcut chips. Which sections appear — and which tiles,
        in which order — is user-customisable (Customize… button). Styling
        lives in the global QSS (object-name selectors).
        """
        lay_pref = self._dashboard_layout()
        w = QWidget()
        w.setObjectName("dashboard")
        w.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        w.customContextMenuRequested.connect(
            lambda pos: self._show_dashboard_context_menu(w.mapToGlobal(pos))
        )
        el = QVBoxLayout(w)
        el.setAlignment(Qt.AlignmentFlag.AlignTop)
        el.setSpacing(16)
        el.setContentsMargins(28, 24, 28, 20)

        # Header: logo mark + name + version + quick access affordances
        header_row = QHBoxLayout()
        header_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_row.setSpacing(10)
        logo_tile = QLabel()
        self._dash_logo_tile = logo_tile
        logo_tile.setFixedSize(42, 42)
        logo_tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_tile.setStyleSheet(
            f"background: {solid_on(palette()['accent_subtle'], palette()['bg'])}; "
            f"border: 1px solid {palette()['border']}; "
            f"border-radius: 10px;"
        )
        logo_inner = QLabel()
        logo_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_inner.setPixmap(theme.accent_icon("logo", 24).pixmap(QSize(24, 24)))
        logo_tile.layout = QHBoxLayout(logo_tile)
        logo_tile.layout.setContentsMargins(0, 0, 0, 0)
        logo_tile.layout.addWidget(logo_inner)
        header_row.addWidget(logo_tile)
        title = QLabel(APP_NAME)
        title.setObjectName("dashTitle")
        self._dash_header_label = title  # density-dependent font size
        header_row.addWidget(title)
        version = QLabel(f"v{__version__}  ·  SSH · SFTP · RDP · local terminal")
        version.setObjectName("dashVersion")
        header_row.addWidget(version, 0, Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch(1)

        if hasattr(self, "open_onboarding_guide"):
            tour_btn = QPushButton("Tour")
            tour_btn.setObjectName("subtle")
            tour_btn.setIcon(icon("star", size=14))
            tour_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            tour_btn.setToolTip("Interactive onboarding guide for new users")
            tour_btn.setAccessibleName("Interactive tour")
            tour_btn.clicked.connect(self.open_onboarding_guide)
            header_row.addWidget(tour_btn)

        if hasattr(self, "open_activity_log"):
            act_btn = QPushButton("Activity")
            act_btn.setObjectName("subtle")
            act_btn.setIcon(icon("activity", size=14))
            act_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            act_btn.setToolTip("Real-time connection status & user activity log (Ctrl+Shift+A)")
            act_btn.setAccessibleName("Activity log")
            act_btn.clicked.connect(self.open_activity_log)
            header_row.addWidget(act_btn)

        if hasattr(self, "open_support_chat"):
            sup_btn = QPushButton("Support")
            sup_btn.setObjectName("subtle")
            sup_btn.setIcon(icon("help", size=14))
            sup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            sup_btn.setToolTip("In-session support chat & instant troubleshooting (Ctrl+Shift+H)")
            sup_btn.setAccessibleName("Support chat")
            sup_btn.clicked.connect(self.open_support_chat)
            header_row.addWidget(sup_btn)

        if hasattr(self, "open_feedback_dialog"):
            fb_btn = QPushButton("Feedback")
            fb_btn.setObjectName("subtle")
            fb_btn.setIcon(icon("edit", size=14))
            fb_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            fb_btn.setToolTip("Suggest improvements or report an issue (Ctrl+Shift+F)")
            fb_btn.setAccessibleName("Send feedback")
            fb_btn.clicked.connect(self.open_feedback_dialog)
            header_row.addWidget(fb_btn)

        customize_btn = QPushButton("Customize…")
        customize_btn.setObjectName("subtle")
        customize_btn.setIcon(icon("edit", size=14))
        customize_btn.setMinimumWidth(108)
        customize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        customize_btn.setToolTip(
            "Choose which dashboard sections and launcher tiles are shown"
        )
        customize_btn.setAccessibleName("Customize dashboard")
        customize_btn.clicked.connect(self.open_dashboard_customizer)
        header_row.addWidget(customize_btn)
        el.addLayout(header_row)

        # Hero — quick connect + one-click RDP feature bar + frequent servers
        if lay_pref["show_quick_connect"]:
            quick_section = QFrame()
            quick_section.setObjectName("dashSectionQuick")
            quick_section.setStyleSheet(
                f"QFrame#dashSectionQuick {{ background: {palette()['panel']}; "
                f"border: 1px solid {palette()['border']}; border-radius: 8px; }}"
            )
            qs = QVBoxLayout(quick_section)
            qs.setContentsMargins(16, 12, 16, 14)
            qs.setSpacing(8)
            hero_hdr = QHBoxLayout()
            hero_hdr.setContentsMargins(0, 0, 0, 0)
            hero_hdr.setSpacing(6)
            hero_label = QLabel("Quick connect")
            hero_label.setObjectName("dashSection")
            hero_hdr.addWidget(hero_label)
            hero_hdr.addStretch(1)

            for proto_label, proto_hint, proto_code in (
                ("RDP 3389", "Pre-fill RDP port 3389 for remote desktop", "rdp"),
                ("SSH 22", "Pre-fill SSH port 22 for remote shell", "ssh"),
                ("SFTP", "Open SFTP file transfer browser", "sftp"),
            ):
                pbtn = QPushButton(proto_label)
                pbtn.setObjectName("subtle")
                pbtn.setFixedHeight(24)
                pbtn.setCursor(Qt.CursorShape.PointingHandCursor)
                pbtn.setToolTip(proto_hint)
                pbtn.clicked.connect(
                    lambda _=False, pc=proto_code: self._set_dash_quick_protocol(pc)
                )
                hero_hdr.addWidget(pbtn)

            for hint_txt in ("ssh user@host", "host:3389 (RDP)"):
                hint_chip = QLabel(hint_txt)
                hint_chip.setObjectName("protoChip")
                hero_hdr.addWidget(hint_chip)
            qs.addLayout(hero_hdr)

            hero_row = QHBoxLayout()
            hero_row.setSpacing(8)
            self.dash_quick = QLineEdit()
            self.dash_quick.setObjectName("dashQuick")
            self.dash_quick.setPlaceholderText(
                "user@host[:port]  —  port 3389 connects as RDP"
            )
            self.dash_quick.setAccessibleName("Quick connect")
            self.dash_quick.setToolTip("Open user@host[:port] — port 3389 opens RDP (Enter)")
            self.dash_quick.returnPressed.connect(
                lambda: self._quick_connect_from(self.dash_quick)
            )
            hero_row.addWidget(self.dash_quick, 1)
            dash_go = QPushButton("Connect")
            dash_go.setObjectName("primary")
            dash_go.setFixedHeight(38)
            dash_go.setMinimumWidth(98)
            dash_go.setCursor(Qt.CursorShape.PointingHandCursor)
            dash_go.setAccessibleName("Connect")
            dash_go.clicked.connect(lambda: self._quick_connect_from(self.dash_quick))
            hero_row.addWidget(dash_go)

            if hasattr(self, "new_rdp_session"):
                rdp_btn = QPushButton("New RDP Desktop")
                rdp_btn.setObjectName("subtle")
                rdp_btn.setIcon(icon("windows", size=14))
                rdp_btn.setFixedHeight(38)
                rdp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                rdp_btn.setToolTip("Configure & launch a full Windows / Linux RDP desktop session")
                rdp_btn.clicked.connect(self.new_rdp_session)
                hero_row.addWidget(rdp_btn)
            qs.addLayout(hero_row)

            # One-click Frequent & Saved Servers bar inside Quick Connect
            freq_sessions = self._frequent_sessions_for_dashboard(limit=6)
            if freq_sessions:
                freq_wrap = QWidget()
                freq_wrap.setObjectName("dashFrequentPanel")
                fl = QHBoxLayout(freq_wrap)
                fl.setContentsMargins(0, 4, 0, 0)
                fl.setSpacing(6)
                freq_lbl = QLabel("Frequent servers:")
                freq_lbl.setObjectName("caption")
                fl.addWidget(freq_lbl)
                counts = getattr(self.ctx.settings, "session_connect_counts", {}) or {}
                for sess in freq_sessions:
                    cnt = int(counts.get(sess.id, 0) or 0)
                    badge_txt = f"{sess.display_name()} ({ sess.protocol.upper() })"
                    if cnt > 1:
                        badge_txt += f" · {cnt}×"
                    sbtn = QPushButton(badge_txt)
                    sbtn.setObjectName("subtle")
                    sbtn.setFixedHeight(26)
                    sbtn.setCursor(Qt.CursorShape.PointingHandCursor)
                    sbtn.setToolTip(
                        f"One-click connect to {sess.display_name()} ({sess.protocol.upper()} {sess.target()})\n"
                        "Right-click for session options"
                    )
                    sbtn.clicked.connect(lambda _=False, sid=sess.id: self.connect_session(sid))
                    sbtn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                    sbtn.customContextMenuRequested.connect(
                        lambda pos, b=sbtn, s=sess: self._show_dashboard_session_menu(
                            s, b.mapToGlobal(pos)
                        )
                    )
                    fl.addWidget(sbtn)
                fl.addStretch(1)
                qs.addWidget(freq_wrap)

            el.addWidget(quick_section)

        # Action tiles — launcher shortcuts (flow-wrapped for narrow windows)
        if lay_pref["show_actions"]:
            actions_section = QWidget()
            actions_section.setObjectName("dashSectionActions")
            as_lay = QVBoxLayout(actions_section)
            as_lay.setContentsMargins(0, 0, 0, 0)
            as_lay.setSpacing(8)
            actions_label = QLabel("Launchers")
            actions_label.setObjectName("dashSection")
            as_lay.addWidget(actions_label)

            self._dash_action_icons: list[tuple[QLabel, str]] = []
            tiles_row = QWidget()
            tiles_flow = FlowLayout(tiles_row, margin=0, spacing=10)

            for tid in lay_pref["tiles"]:
                spec = DASHBOARD_TILES.get(tid)
                if spec is None:
                    continue
                callback = getattr(self, spec["method"], None)
                if callback is None:
                    continue
                tiles_flow.addWidget(
                    self._dash_action_card(
                        spec["icon"], spec["label"], spec["caption"],
                        spec["tooltip"], callback,
                    )
                )
            as_lay.addWidget(tiles_row)
            el.addWidget(actions_section)
        else:
            self._dash_action_icons = []

        # Recent connections — protocol badges, pinned first
        if lay_pref["show_recents"]:
            recents_section = self._build_recent_section()
            if recents_section is not None:
                el.addWidget(recents_section)

        el.addStretch(1)

        # Keyboard shortcut chips (flow-wrapped too)
        if lay_pref["show_shortcuts"]:
            shortcuts_section = QWidget()
            shortcuts_section.setObjectName("dashSectionShortcuts")
            ss = QVBoxLayout(shortcuts_section)
            ss.setContentsMargins(0, 0, 0, 0)
            ss.setSpacing(8)
            shortcuts_label = QLabel("Keyboard shortcuts")
            shortcuts_label.setObjectName("dashSection")
            ss.addWidget(shortcuts_label)
            chips_row = QWidget()
            chips_flow = FlowLayout(chips_row, margin=0, spacing=16)
            chips_flow.setContentsMargins(0, 0, 0, 0)
            for combo, what in (
                ("Ctrl+N", "new session"),
                ("Ctrl+Shift+T", "local terminal"),
                ("Ctrl+K", "commands"),
                ("Ctrl+B", "sessions panel"),
                ("Ctrl+,", "settings"),
            ):
                pair = QHBoxLayout()
                pair.setContentsMargins(0, 0, 0, 0)
                pair.setSpacing(6)
                key = QLabel(combo)
                key.setObjectName("kbd")
                pair.addWidget(key)
                cap = QLabel(what)
                cap.setObjectName("caption")
                pair.addWidget(cap)
                wrap = QWidget()
                wrap.setLayout(pair)
                chips_flow.addWidget(wrap)
            ss.addWidget(chips_row)
            el.addWidget(shortcuts_section)

        animate_in(w)
        return w

    def _dash_action_card(
        self, icon_name: str, label: str, caption: str, tooltip: str, callback
    ) -> QFrame:
        """One launcher tile — icon tile, title, caption; hover-lifted."""
        card = QFrame()
        card.setObjectName("dashTile")
        card.setFixedSize(162, 108)
        install_hover_shadow(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(6)
        tile_icon = QLabel()
        tile_icon.setObjectName("dashTileIcon")
        tile_icon.setFixedSize(36, 36)
        tile_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile_icon.layout = QHBoxLayout(tile_icon)
        tile_icon.layout.setContentsMargins(0, 0, 0, 0)
        inner = QLabel()
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.setPixmap(theme.toolbar_icon(icon_name).pixmap(QSize(20, 20)))
        tile_icon.layout.addWidget(inner)
        self._dash_action_icons.append((inner, icon_name))
        lay.addWidget(tile_icon)
        lbl = QLabel(label)
        lbl.setObjectName("cardTitle")
        lay.addWidget(lbl)
        sub = QLabel(caption)
        sub.setObjectName("cardSub")
        sub.setWordWrap(True)
        lay.addWidget(sub)
        lay.addStretch(1)
        _make_activatable(card, callback, accessible_name=label, tooltip=tooltip)
        return card

    def _build_recent_section(self) -> QWidget | None:
        """The 'Recent sessions' card inside its own section wrapper."""
        sessions = sorted(
            self.ctx.store.sessions(),
            key=lambda s: (not s.options.get("pinned", False), s.name),
        )[:6]
        if not sessions:
            return None
        section = QWidget()
        section.setObjectName("dashSectionRecents")
        sec_lay = QVBoxLayout(section)
        sec_lay.setContentsMargins(0, 0, 0, 0)
        sec_lay.setSpacing(8)
        sec_lay.addWidget(self._build_recent_card())
        return section

    def _build_recent_card(self) -> QWidget:
        """Recent-sessions card: protocol badges, pinned first."""
        sessions = sorted(
            self.ctx.store.sessions(),
            key=lambda s: (not s.options.get("pinned", False), s.name),
        )[:6]
        recent_card = QWidget()
        recent_card.setObjectName("card")
        recent_card.setMinimumWidth(420)
        rc_lay = QVBoxLayout(recent_card)
        rc_lay.setContentsMargins(12, 12, 12, 10)
        rc_lay.setSpacing(4)
        rc_hdr_row = QHBoxLayout()
        rc_hdr_row.setContentsMargins(2, 0, 2, 4)
        rc_hdr_row.setSpacing(8)
        rc_header = QLabel("Recent & Pinned Sessions")
        rc_header.setObjectName("h2")
        rc_hdr_row.addWidget(rc_header)
        rc_count = QLabel(str(len(sessions)))
        rc_count.setObjectName("sideCount")
        rc_hdr_row.addWidget(rc_count)
        rc_hdr_row.addStretch(1)
        rc_lay.addLayout(rc_hdr_row)

        self._dash_recent_rows: list[tuple[QLabel, str, object]] = []
        for sess in sessions[:5]:
            item = QFrame()
            item.setObjectName("card_hover")
            il = QHBoxLayout(item)
            il.setContentsMargins(10, 7, 10, 7)
            il.setSpacing(10)
            pi = QLabel()
            pi.setPixmap(protocol_badge(sess.protocol, self._proto_icon(sess.protocol)).pixmap(QSize(20, 20)))
            pi.setFixedSize(20, 20)
            self._dash_recent_rows.append((pi, "proto", sess.protocol))
            il.addWidget(pi)
            if sess.options.get("pinned", False):
                star = QLabel()
                star.setPixmap(icon("star", palette()["warn"]).pixmap(QSize(14, 14)))
                star.setFixedSize(14, 14)
                star.setToolTip("Pinned session")
                self._dash_recent_rows.append((star, "icon", ("star", "warn")))
                il.addWidget(star)
            name_lbl = QLabel(sess.display_name())
            name_lbl.setObjectName("cardTitle")
            il.addWidget(name_lbl)
            if sess.group:
                grp = QLabel(sess.group)
                grp.setObjectName("protoChip")
                il.addWidget(grp)
            il.addStretch(1)
            target = QLabel(sess.target())
            target.setObjectName("cardSub")
            il.addWidget(target)
            proto = QLabel(sess.protocol.upper())
            proto.setObjectName("protoChip")
            il.addWidget(proto)
            _make_activatable(
                item,
                lambda s=sess: self.connect_session(s.id),
                accessible_name=f"Connect to {sess.display_name()}",
                tooltip=f"{sess.protocol.upper()} · {sess.target()}",
            )
            item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            item.customContextMenuRequested.connect(
                lambda pos, it=item, s=sess: self._show_dashboard_session_menu(
                    s, it.mapToGlobal(pos)
                )
            )
            rc_lay.addWidget(item)
        return recent_card

    def _frequent_sessions_for_dashboard(self, limit: int = 6) -> list:
        """Return saved sessions ordered by pinned status, connection frequency, and recency."""
        store = getattr(getattr(self, "ctx", None), "store", None)
        settings = getattr(getattr(self, "ctx", None), "settings", None)
        if store is None:
            return []
        by_id = {s.id: s for s in store.sessions()}
        if not by_id:
            return []
        freq_ids = settings.frequent_session_ids(limit=limit * 2) if settings is not None else []
        counts = getattr(settings, "session_connect_counts", {}) if settings is not None else {}
        ordered = sorted(
            by_id.values(),
            key=lambda s: (
                not bool(s.options.get("pinned", False)),
                -int(counts.get(s.id, 0) or 0),
                freq_ids.index(s.id) if s.id in freq_ids else 999,
                s.display_name().lower(),
            ),
        )
        return ordered[:limit]

    def _set_dash_quick_protocol(self, proto_code: str) -> None:
        """Apply a protocol quick-preset to the dashboard quick-connect box."""
        quick = getattr(self, "dash_quick", None)
        if quick is None:
            return
        cur = quick.text().strip()
        if proto_code == "rdp":
            if cur and ":" not in cur:
                quick.setText(f"{cur}:3389")
            elif not cur:
                quick.setPlaceholderText("user@rdp-host:3389  —  press Enter to open RDP desktop")
            quick.setFocus()
        elif proto_code == "ssh":
            if cur.endswith(":3389"):
                quick.setText(cur[:-5] + ":22")
            elif not cur:
                quick.setPlaceholderText("user@ssh-host:22  —  press Enter to open SSH shell")
            quick.setFocus()
        elif proto_code == "sftp":
            if hasattr(self, "new_sftp_session"):
                self.new_sftp_session()
            else:
                quick.setFocus()

    def _show_dashboard_context_menu(self, global_pos: QPoint) -> None:
        """Context menu when right-clicking the dashboard background."""
        menu = QMenu(self)
        act_new = menu.addAction(icon("plus"), "New Session…\tCtrl+N")
        act_rdp = menu.addAction(icon("windows"), "New RDP Desktop…")
        act_local = menu.addAction(icon("console"), "Open Local Terminal\tCtrl+Shift+T")
        act_cmd = menu.addAction(icon("search"), "Command Palette…\tCtrl+K")
        menu.addSeparator()
        act_act = menu.addAction(icon("activity"), "Connection Status & Activity Log…\tCtrl+Shift+A")
        act_sup = menu.addAction(icon("help"), "In-Session Support Chat…\tCtrl+Shift+H")
        act_tour = menu.addAction(icon("star"), "Interactive Onboarding Tour…")
        act_fb = menu.addAction(icon("edit"), "Send Feedback…\tCtrl+Shift+F")
        menu.addSeparator()
        act_theme = menu.addAction(icon("appearance"), "Toggle Dark / Light Theme\tCtrl+Shift+L")
        act_cust = menu.addAction(icon("gear"), "Customize Dashboard…")

        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        dispatch = {
            act_new: "new_session",
            act_rdp: "new_rdp_session",
            act_local: "open_local_terminal",
            act_cmd: "open_command_palette",
            act_act: "open_activity_log",
            act_sup: "open_support_chat",
            act_tour: "open_onboarding_guide",
            act_fb: "open_feedback_dialog",
            act_theme: "toggle_dark_light_theme",
            act_cust: "open_dashboard_customizer",
        }
        method_name = dispatch.get(chosen)
        if method_name and hasattr(self, method_name):
            getattr(self, method_name)()

    def _show_dashboard_session_menu(self, sess, global_pos: QPoint) -> None:
        """Context menu for a saved session chip or recent row on the dashboard."""
        menu = QMenu(self)
        act_conn = menu.addAction(icon("play"), f"Connect to {sess.display_name()}")
        act_edit = menu.addAction(icon("edit"), "Edit Session…")
        pinned = bool(sess.options.get("pinned", False))
        act_pin = menu.addAction(
            icon("star"), "Unpin from Frequent" if pinned else "Pin to Frequent"
        )
        act_copy = menu.addAction(icon("copy"), f"Copy Host ({sess.host or sess.target()})")
        menu.addSeparator()
        act_del = menu.addAction(icon("trash"), "Delete Session…")

        chosen = menu.exec(global_pos)
        if chosen == act_conn:
            self.connect_session(sess.id)
        elif chosen == act_edit and hasattr(self, "edit_session"):
            self.edit_session(sess.id)
        elif chosen == act_pin and hasattr(self, "toggle_pin_session"):
            self.toggle_pin_session(sess.id)
        elif chosen == act_copy:
            QGuiApplication.clipboard().setText(sess.host or sess.target())
        elif chosen == act_del and hasattr(self, "delete_session"):
            self.delete_session(sess.id)

    def open_dashboard_customizer(self) -> None:
        """Open the dashboard personalisation dialog and rebuild on apply."""
        def _applied() -> None:
            self._refresh_dashboard()
            from .widgets import toast

            toast(self, "Dashboard updated", "good")

        dlg = DashboardCustomizeDialog(self.ctx.settings, self, on_apply=_applied)
        animate_in(dlg)
        dlg.exec()

    @staticmethod
    def _proto_icon(protocol: str) -> str:
        return {"rdp": "windows", "ssh": "terminal"}.get((protocol or "").lower(), "console")
