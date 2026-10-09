"""Welcome-dashboard builders, moved verbatim from MainWindow (ARCH-02).

Mixin methods — ``self`` is the MainWindow at runtime.

The dashboard is user-customisable: Settings → General → *Customize
dashboard…* (or the *Customize…* button on the dashboard itself) chooses
which sections are visible and which launcher tiles appear, in which order
(see ``core.settings.DEFAULT_DASHBOARD_LAYOUT``). Tiles flow-wrap so the
page stays usable on narrow windows.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
        el = QVBoxLayout(w)
        el.setAlignment(Qt.AlignmentFlag.AlignTop)
        el.setSpacing(16)
        el.setContentsMargins(28, 24, 28, 20)

        # Header: logo mark + name + version + customize affordance
        header_row = QHBoxLayout()
        header_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_row.setSpacing(12)
        logo_tile = QLabel()
        self._dash_logo_tile = logo_tile
        logo_tile.setFixedSize(40, 40)
        logo_tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_tile.setStyleSheet(
            f"background: {solid_on(palette()['accent_subtle'], palette()['bg'])}; "
            f"border: 1px solid {palette()['border_subtle']}; "
            f"border-radius: 10px;"
        )
        logo_inner = QLabel()
        logo_inner.setPixmap(icon("logo").pixmap(QSize(24, 24)))
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
        customize_btn = QPushButton("Customize…")
        customize_btn.setObjectName("subtle")
        customize_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        customize_btn.setToolTip(
            "Choose which dashboard sections and launcher tiles are shown"
        )
        customize_btn.setAccessibleName("Customize dashboard")
        customize_btn.clicked.connect(self.open_dashboard_customizer)
        header_row.addWidget(customize_btn)
        el.addLayout(header_row)

        # Hero — quick connect, the primary path from an empty workbench
        if lay_pref["show_quick_connect"]:
            quick_section = QWidget()
            quick_section.setObjectName("dashSectionQuick")
            qs = QVBoxLayout(quick_section)
            qs.setContentsMargins(0, 0, 0, 0)
            qs.setSpacing(8)
            hero_label = QLabel("Quick connect")
            hero_label.setObjectName("dashSection")
            qs.addWidget(hero_label)

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
            dash_go.setFixedHeight(40)
            dash_go.setCursor(Qt.CursorShape.PointingHandCursor)
            dash_go.setAccessibleName("Connect")
            dash_go.clicked.connect(lambda: self._quick_connect_from(self.dash_quick))
            hero_row.addWidget(dash_go)
            qs.addLayout(hero_row)
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
        card.setFixedSize(154, 104)
        install_hover_shadow(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 14, 14, 10)
        lay.setSpacing(6)
        tile_icon = QLabel()
        tile_icon.setObjectName("dashTileIcon")
        tile_icon.setFixedSize(34, 34)
        tile_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tile_icon.layout = QHBoxLayout(tile_icon)
        tile_icon.layout.setContentsMargins(0, 0, 0, 0)
        inner = QLabel()
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
        rc_lay.setContentsMargins(10, 10, 10, 6)
        rc_lay.setSpacing(2)
        rc_header = QLabel("Recent sessions")
        rc_header.setObjectName("h2")
        rc_lay.addWidget(rc_header)

        self._dash_recent_rows: list[tuple[QLabel, str, object]] = []
        for sess in sessions[:5]:
            item = QFrame()
            item.setObjectName("card_hover")
            il = QHBoxLayout(item)
            il.setContentsMargins(8, 6, 8, 6)
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
            rc_lay.addWidget(item)
        return recent_card

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
