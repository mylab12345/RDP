"""Welcome-dashboard builders, moved verbatim from MainWindow (ARCH-02).

Mixin methods — ``self`` is the MainWindow at runtime.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from . import theme
from .theme import icon, palette, protocol_badge, solid_on


class DashboardMixin:
    """Builds the welcome dashboard tab (no state of its own)."""

    def _build_dashboard(self) -> QWidget:
        """Modern welcome page shown when no tabs are open.

        A white document card with the app identity, a prominent quick
        connect field, a row of launcher tiles, the recent-sessions list
        and keyboard shortcut chips. Styling lives in the global QSS
        (object-name selectors).
        """
        w = QWidget()
        w.setObjectName("dashboard")
        el = QVBoxLayout(w)
        el.setAlignment(Qt.AlignmentFlag.AlignTop)
        el.setSpacing(16)
        el.setContentsMargins(28, 24, 28, 20)

        # Header: logo mark + name + version
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
        el.addLayout(header_row)

        # Hero — quick connect, the primary path from an empty workbench
        hero_label = QLabel("Quick connect")
        hero_label.setObjectName("caption")
        hero_label.setStyleSheet("font-weight: 600; letter-spacing: 0.4px;")
        el.addWidget(hero_label)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(8)
        self.dash_quick = QLineEdit()
        self.dash_quick.setObjectName("dashQuick")
        self.dash_quick.setPlaceholderText(
            "user@host[:port]  —  port 3389 connects as RDP"
        )
        self.dash_quick.setAccessibleName("Quick connect")
        self.dash_quick.returnPressed.connect(
            lambda: self._quick_connect_from(self.dash_quick)
        )
        hero_row.addWidget(self.dash_quick, 1)
        dash_go = QPushButton("Connect")
        dash_go.setObjectName("primary")
        dash_go.setFixedHeight(40)
        dash_go.setCursor(Qt.CursorShape.PointingHandCursor)
        dash_go.clicked.connect(lambda: self._quick_connect_from(self.dash_quick))
        hero_row.addWidget(dash_go)
        el.addLayout(hero_row)

        # Action tiles — launcher shortcuts
        actions_row = QHBoxLayout()
        actions_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        actions_row.setSpacing(10)
        self._dash_action_icons: list[tuple[QLabel, str]] = []

        def _action_card(icon_name: str, label: str, caption: str, tooltip: str, callback) -> QWidget:
            card = QFrame()
            card.setObjectName("dashTile")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip(tooltip)
            card.setFixedSize(154, 104)
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
            card.mousePressEvent = lambda _, c=callback: c()
            return card

        actions_row.addWidget(_action_card("plus", "New session", "SSH · RDP · more", "Create a new connection (Ctrl+N)", self.new_session))
        actions_row.addWidget(_action_card("console", "Local terminal", "Start a shell", "Open a local terminal (Ctrl+Shift+T)", self.open_local_terminal))
        actions_row.addWidget(_action_card("search", "Commands", "Palette · switcher", "Search commands & sessions (Ctrl+K)", self.open_command_palette))
        actions_row.addWidget(_action_card("gear", "Settings", "Themes · fonts · keys", "Configure KB-Remote (Ctrl+,)", self.open_settings))
        el.addLayout(actions_row)

        # Recent connections — protocol badges, pinned first
        self._build_recent_card(el)

        el.addStretch(1)

        # Keyboard shortcut chips
        chips = QHBoxLayout()
        chips.setAlignment(Qt.AlignmentFlag.AlignLeft)
        chips.setSpacing(16)
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
            chips.addWidget(wrap)
        el.addLayout(chips)
        return w

    def _build_recent_card(self, el: QVBoxLayout) -> None:
        """Fill the 'Recent sessions' card into dashboard layout ``el``."""
        sessions = sorted(
            self.ctx.store.sessions(),
            key=lambda s: (not s.options.get("pinned", False), s.name),
        )[:6]
        if not sessions:
            return
        recent_card = QWidget()
        recent_card.setObjectName("card")
        recent_card.setMinimumWidth(640)
        rc_lay = QVBoxLayout(recent_card)
        rc_lay.setContentsMargins(10, 10, 10, 6)
        rc_lay.setSpacing(2)
        rc_header = QLabel("Recent sessions")
        rc_header.setObjectName("h2")
        rc_lay.addWidget(rc_header)

        self._dash_recent_rows: list[tuple[QLabel, str, object]] = []
        for sess in sessions[:5]:
            item = QFrame()
            item.setCursor(Qt.CursorShape.PointingHandCursor)
            item.setObjectName("card_hover")
            item.mousePressEvent = lambda _, s=sess: self.connect_session(s.id)
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
            rc_lay.addWidget(item)
        el.addWidget(recent_card)

    @staticmethod
    def _proto_icon(protocol: str) -> str:
        return {"rdp": "windows", "ssh": "terminal"}.get((protocol or "").lower(), "console")
