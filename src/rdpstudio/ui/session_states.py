"""Non-live session surfaces: connecting, reconnecting, failed, disconnected.

Presentation only. :class:`SessionStateOverlay` renders *what the controller
already reports* — it never talks to a protocol plugin, never retries on its
own and never invents state. The owning :class:`~rdpstudio.ui.main_window.SessionTab`
converts clicks on the overlay into the same controller calls the header
buttons use (``start`` / ``stop`` / ``request_reconnect``).

Design: one centred card over the session surface — a state icon tile, a
title, one line of plain-language detail, and at most three actions, the
primary one first. Everything is keyboard reachable (Tab / Enter) and carries
an accessible name, so the overlay is usable without a mouse.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .theme import palette
from .widgets import pulse

# State id → (icon, title, hint). ``detail`` is always supplied by the caller
# because only the controller knows the host, the reason or the error text.
_PRESETS: dict[str, tuple[str, str, str]] = {
    "idle": ("connect", "Ready to connect", "Press Enter to start this session"),
    "connecting": ("connect", "Connecting…", "Negotiating with the host"),
    "reconnecting": ("connect", "Reconnecting…", "Automatic retry in progress"),
    "failed": ("shield", "Connection failed", "Check the address and credentials"),
    "closed": ("stop", "Disconnected", "The session is no longer live"),
}

# Action key → button label/icon/role. ``primary`` is the focused default.
_ACTIONS: dict[str, tuple[str, str | None, bool]] = {
    "connect": ("Connect", "connect", True),
    "retry": ("Try again", "connect", True),
    "reconnect": ("Reconnect", "connect", True),
    "sharing": ("Share folders…", "folder", False),
    "settings": ("Connection settings…", "gear", False),
    "cancel": ("Cancel", None, False),
    "close": ("Close tab", None, False),
}


class SessionStateOverlay(QFrame):
    """Centred status card shown while a session is *not* live.

    Signals mirror user intent; the tab decides which ones a given state
    exposes (see :meth:`show_state`). Keyboard: Tab moves between buttons,
    Enter/Space activates the focused one.
    """

    connectRequested = Signal()
    retryRequested = Signal()
    reconnectRequested = Signal()
    shareRequested = Signal()
    settingsRequested = Signal()
    cancelRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("stateOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._state = ""
        self._build()

    # -- construction ----------------------------------------------------
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName("stateCard")
        card.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self._card = card
        lay = QVBoxLayout(card)
        lay.setContentsMargins(28, 26, 28, 24)
        lay.setSpacing(14)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._icon_tile = QLabel()
        self._icon_tile.setObjectName("stateIconTile")
        self._icon_tile.setFixedSize(56, 56)
        self._icon_tile.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._icon_tile, 0, Qt.AlignmentFlag.AlignHCenter)

        self._title = QLabel("")
        self._title.setObjectName("stateTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self._title)

        self._detail = QLabel("")
        self._detail.setObjectName("stateDetail")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._detail.setWordWrap(True)
        self._detail.setMinimumWidth(300)
        self._detail.setMaximumWidth(460)
        self._detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        lay.addWidget(self._detail, 0, Qt.AlignmentFlag.AlignHCenter)

        self._action_row = QHBoxLayout()
        self._action_row.setContentsMargins(0, 2, 0, 0)
        self._action_row.setSpacing(10)
        self._action_row.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._buttons: dict[str, QPushButton] = {}
        for key, (label, icon_name, is_primary) in _ACTIONS.items():
            btn = QPushButton(label)
            if icon_name:
                btn.setIcon(theme.icon(icon_name))
            btn.setObjectName("primary" if is_primary else "subtle")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(34)
            btn.setIconSize(QSize(16, 16))
            btn.setAccessibleName(label)
            btn.clicked.connect(
                lambda _checked=False, k=key: self._emit_for(k)
            )
            btn.setVisible(False)
            self._buttons[key] = btn
            self._action_row.addWidget(btn)

        self._hint = QLabel("")
        self._hint.setObjectName("caption")
        self._hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._hint.setWordWrap(True)
        self._hint.setMinimumWidth(300)
        self._hint.setMaximumWidth(460)
        self._hint.setVisible(False)
        lay.addWidget(self._hint, 0, Qt.AlignmentFlag.AlignHCenter)

        lay.addLayout(self._action_row)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    # -- intent ----------------------------------------------------------
    def _emit_for(self, key: str) -> None:
        signal = {
            "connect": self.connectRequested,
            "retry": self.retryRequested,
            "reconnect": self.reconnectRequested,
            "sharing": self.shareRequested,
            "settings": self.settingsRequested,
            "cancel": self.cancelRequested,
            "close": self.closeRequested,
        }.get(key)
        if signal is not None:
            signal.emit()

    # -- presentation ----------------------------------------------------
    def show_state(
        self,
        state: str,
        *,
        detail: str = "",
        title: str = "",
        actions: tuple[str, ...] = (),
        hint: str = "",
        tone: str = "",
    ) -> None:
        """Render ``state`` with an explicit action list.

        Unknown states fall back to the ``closed`` preset so a future session
        state can never leave the surface blank.
        """
        icon_name, default_title, default_hint = _PRESETS.get(
            state, _PRESETS["closed"]
        )
        self._state = state
        tone = tone or {"failed": "bad", "closed": "fg_dim"}.get(state, "accent")
        pal = palette()
        tint_key = tone if tone in ("bad", "warn", "good", "info") else "accent"
        tint_colour = pal.get(tint_key, pal["accent"])
        self._icon_tile.setStyleSheet(
            "background: {}; border: 1px solid {}; border-radius: 10px;".format(
                theme.tint(tint_colour, 0x22, pal["bg2"]), pal["border"]
            )
        )
        self._icon_tile.setPixmap(
            theme.icon(icon_name, tint_colour if tone != "fg_dim" else pal["fg_dim"])
            .pixmap(QSize(26, 26))
        )
        self._title.setText(title or default_title)
        self._detail.setText(detail or default_hint)
        self._detail.setVisible(bool(self._detail.text()))
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))

        wanted = set(actions)
        for key, btn in self._buttons.items():
            btn.setVisible(key in wanted)
        # Primary action takes focus so Enter re-runs it immediately.
        for key, _spec in _ACTIONS.items():
            if key in wanted and _spec[2] and self._buttons[key].isVisible():
                self._buttons[key].setFocus(Qt.FocusReason.OtherFocusReason)
                break
        if state == "connecting":
            pulse(self._icon_tile)
        self.setAccessibleName(f"{self._title.text()}. {self._detail.text()}".strip())

    def state(self) -> str:
        """The state currently rendered (``""`` when the surface is hidden)."""
        return self._state

    def hideEvent(self, event) -> None:  # noqa: N802 — Qt naming
        """Forget the state when the surface goes away (e.g. session live)."""
        self._state = ""
        super().hideEvent(event)

    def is_action_visible(self, key: str) -> bool:
        """Whether ``key`` belongs to the state on screen (ignores the window
        being hidden, so the state can be asserted without a shown window)."""
        btn = self._buttons.get(key)
        return bool(btn is not None and btn.isVisibleTo(self))

    def trigger_action(self, key: str) -> None:
        """Programmatic activation — used by tests and keyboard shortcuts."""
        self._emit_for(key)

    def button(self, key: str) -> QPushButton | None:
        return self._buttons.get(key)
