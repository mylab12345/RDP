"""Welcome-dashboard builders, moved verbatim from MainWindow (ARCH-02).

Mixin methods — ``self`` is the MainWindow at runtime, so bodies are
byte-identical to the originals.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, __version__
from . import theme
from .theme import icon, palette, protocol_badge


class DashboardMixin:
    """Builds the welcome dashboard tab (no state of its own)."""

    def _build_dashboard(self) -> QWidget:
        """MobaXterm-style welcome page shown when no tabs are open.

        A white document page with the app title, a one-line quick connect,
        a row of flat action tiles and the recent-sessions list. Styling
        lives in the global QSS (object-name selectors).
        """
        w = QWidget()
        w.setObjectName("dashboard")
        el = QVBoxLayout(w)
        el.setAlignment(Qt.AlignmentFlag.AlignTop)
        el.setSpacing(12)
        el.setContentsMargins(28, 22, 28, 20)

        # Header: logo mark + name + version — MobaXterm's "Start local terminal" page header
        header_row = QHBoxLayout()
        header_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        header_row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(icon("logo").pixmap(28, 28))
        header_row.addWidget(logo)
        title = QLabel(APP_NAME)
        title.setObjectName("dashTitle")
        self._dash_header_label = title  # density-dependent font size
        header_row.addWidget(title)
        version = QLabel(f"v{__version__}  ·  SSH · SFTP · RDP · local terminal")
        version.setObjectName("dashVersion")
        header_row.addWidget(version, 0, Qt.AlignmentFlag.AlignBottom)
        header_row.addStretch(1)
        el.addLayout(header_row)

        rule = QFrame()
        rule.setObjectName("hairline")
        rule.setFixedHeight(1)
        el.addWidget(rule)

        # Quick connect lives in the toolbar; the dashboard stays simple:
        # action tiles, recent sessions, shortcut chips.
        # Action tiles — MobaXterm's big flat launcher buttons
        actions_row = QHBoxLayout()
        actions_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        actions_row.setSpacing(8)
        self._dash_action_icons: list[tuple[QLabel, str]] = []

        def _action_card(icon_name: str, label: str, caption: str, tooltip: str, callback) -> QWidget:
            card = QFrame()
            card.setObjectName("card_hover")
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.setToolTip(tooltip)
            card.setFixedSize(150, 92)
            lay = QVBoxLayout(card)
            lay.setContentsMargins(10, 10, 10, 8)
            lay.setSpacing(4)
            lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            ic = QLabel()
            ic.setPixmap(theme.toolbar_icon(icon_name).pixmap(QSize(28, 28)))
            ic.setFixedSize(28, 28)
            ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dash_action_icons.append((ic, icon_name))
            lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignHCenter)
            lbl = QLabel(label)
            lbl.setObjectName("cardTitle")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(lbl)
            sub = QLabel(caption)
            sub.setObjectName("cardSub")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(sub)
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
        chips.setSpacing(14)
        for combo, what in (
            ("Ctrl+N", "new session"),
            ("Ctrl+Shift+T", "local terminal"),
            ("Ctrl+K", "commands"),
            ("Ctrl+B", "sessions panel"),
            ("Ctrl+,", "settings"),
        ):
            pair = QHBoxLayout()
            pair.setContentsMargins(0, 0, 0, 0)
            pair.setSpacing(5)
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
        """Fill the 'Recent Connections' card into dashboard layout ``el``."""
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
        rc_lay.setContentsMargins(10, 8, 10, 8)
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
            il.setContentsMargins(8, 5, 8, 5)
            il.setSpacing(8)
            pi = QLabel()
            pi.setPixmap(protocol_badge(sess.protocol, self._proto_icon(sess.protocol)).pixmap(QSize(18, 18)))
            pi.setFixedSize(18, 18)
            self._dash_recent_rows.append((pi, "proto", sess.protocol))
            il.addWidget(pi)
            if sess.options.get("pinned", False):
                star = QLabel()
                star.setPixmap(icon("star", palette()["warn"]).pixmap(QSize(13, 13)))
                star.setFixedSize(13, 13)
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
