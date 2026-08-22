"""Protocol plugin architecture.

RDP Studio treats every protocol as a plugin. SSH, RDP and the local shell are
simply *built-in* plugins; third parties can register more via the
``rdpstudio.protocols`` entry-point group::

    # pyproject.toml of a plugin package
    [project.entry-points."rdpstudio.protocols"]
    vnc = "my_plugins.vnc:VncPlugin"

Contract
--------
A :class:`ProtocolPlugin` describes a protocol and manufactures
:class:`SessionController` objects. A controller owns one live session: it
exposes the widget to embed in a tab, emits Qt signals about state changes,
and implements stop/reconnect. Controllers live in the GUI thread and may own
worker objects/threads for blocking I/O.

This separation (describe vs. run) lets the UI build "New session" dialogs,
sidebars and quick-connect logic generically for any protocol.
"""

from __future__ import annotations

import importlib
import importlib.metadata as importlib_metadata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from .events import EventBus
from .log import get_logger
from .models import Session
from .settings import Settings
from .store import SessionStore

log = get_logger("plugins")

ENTRY_POINT_GROUP = "rdpstudio.protocols"


# ----------------------------------------------------------------------
# Prompt provider: how a controller asks the user something without
# knowing about any concrete UI.
# ----------------------------------------------------------------------
class PromptProvider(ABC):
    """Blocking prompts. Implementations must be callable from any thread."""

    @abstractmethod
    def ask_host_key(self, host: str, key_type: str, fingerprint: str, changed: bool) -> bool:
        """Unknown (``changed=False``) or changed (``changed=True``) host key.
        Return True to accept & remember."""

    @abstractmethod
    def ask_secret(
        self, title: str, prompt: str, secret: bool = True, preset: str = ""
    ) -> str | None:
        """Ask the user for a string (password/passphrase when ``secret``)."""


@dataclass
class SessionContext:
    """Services handed to plugins when creating sessions."""

    settings: Settings
    store: SessionStore
    vault: Any  # CredentialVault (typed loosely to avoid import cycle)
    bus: EventBus
    prompter: PromptProvider
    parent_widget: QWidget | None = None

    def publish(self, topic: str, payload: dict | None = None) -> None:
        self.bus.publish(topic, payload)


# ----------------------------------------------------------------------
# Controller: one live session
# ----------------------------------------------------------------------
class SessionState:
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass
class Capabilities:
    shell: bool = False
    sftp: bool = False
    tunnels: bool = False
    external_window: bool = False  # protocol renders in its own OS window
    monitor: bool = False  # exposes live remote host metrics


class SessionController(QObject):
    """Base class for a live session bound to a tab in the main window."""

    titleChanged = Signal(str)
    stateChanged = Signal(str)  # SessionState value
    statusInfo = Signal(dict)  # free-form info dict for tab header/status bar
    finished = Signal(str)  # human-readable reason; always emitted once at end
    reconnectScheduled = Signal(int, float)  # attempt, delay seconds

    def __init__(self, definition: Session, ctx: SessionContext, parent: QObject | None = None):
        super().__init__(parent)
        self.definition = definition
        self.ctx = ctx
        self._state = SessionState.CLOSED
        self._finished_emitted = False

    # -- lifecycle -------------------------------------------------------
    @abstractmethod
    def start(self) -> None: ...

    def stop(self, reason: str = "closed by user") -> None:
        """Tear the session down; must emit finished(reason) shortly after."""

    def request_reconnect(self) -> None:
        """Best-effort reconnect (default: restart)."""

    # -- introspection ----------------------------------------------------
    @abstractmethod
    def widget(self) -> QWidget:
        """The widget to embed in the session tab."""

    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    def emit_finished_once(self, reason: str) -> None:
        if not self._finished_emitted:
            self._finished_emitted = True
            self.set_state(SessionState.CLOSED)
            self.finished.emit(reason)

    # -- terminal-ish protocols -------------------------------------------
    def write(self, data: bytes) -> None:  # pragma: no cover - optional
        """Send user input (only for shell-capable controllers)."""

    def resize(self, cols: int, rows: int) -> None:  # pragma: no cover - optional
        """Terminal resize (only for shell-capable controllers)."""

    # -- helpers -----------------------------------------------------------
    def open_sftp(self) -> None:  # pragma: no cover - optional
        """Open an SFTP/transfer window for this session."""

    def open_tunnels(self) -> None:  # pragma: no cover - optional
        """Open the port-forwarding manager for this session."""

    def open_monitor(self) -> None:  # pragma: no cover - optional
        """Open the remote host monitor for this session."""


# ----------------------------------------------------------------------
# Plugin descriptor
# ----------------------------------------------------------------------
class ProtocolPlugin(ABC):
    """Describe a protocol and manufacture session controllers.

    Subclasses set the class attributes; ``id`` must be unique.
    """

    id: str = ""
    title: str = ""
    description: str = ""
    default_port: int = 0
    icon_name: str = "server"
    can_edit: bool = True  # show in "New session" dialog
    tags: list[str] = []

    @abstractmethod
    def create_session(self, definition: Session, ctx: SessionContext) -> SessionController: ...

    def build_editor(self, definition: Session, parent: QWidget) -> QWidget | None:
        """Extra per-protocol editor page for the session dialog."""
        return None

    def quick_connect_target(self, text: str) -> Session | None:
        """Optionally parse a quick-connect string into a session definition."""
        return None


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------
class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, ProtocolPlugin] = {}

    def register(self, plugin: ProtocolPlugin) -> None:
        if not plugin.id:
            raise ValueError("plugin id must not be empty")
        if plugin.id in self._plugins:
            log.warning("plugin %s registered twice; replacing", plugin.id)
        self._plugins[plugin.id] = plugin
        log.debug("registered protocol plugin %s (%s)", plugin.id, plugin.title)

    def get(self, protocol_id: str) -> ProtocolPlugin | None:
        return self._plugins.get(protocol_id)

    def require(self, protocol_id: str) -> ProtocolPlugin:
        plugin = self._plugins.get(protocol_id)
        if plugin is None:
            raise KeyError(f"no protocol plugin registered for {protocol_id!r}")
        return plugin

    def all(self) -> list[ProtocolPlugin]:
        return sorted(self._plugins.values(), key=lambda p: p.title.lower())

    def editable(self) -> list[ProtocolPlugin]:
        return [p for p in self.all() if p.can_edit]

    # -- discovery ---------------------------------------------------------
    def load_entry_points(self) -> list[str]:
        """Load third-party plugins registered via packaging entry points."""
        loaded: list[str] = []
        try:
            eps = importlib_metadata.entry_points()
            if hasattr(eps, "select"):
                group = eps.select(group=ENTRY_POINT_GROUP)
            else:  # pragma: no cover - legacy API
                group = eps.get(ENTRY_POINT_GROUP, [])
        except Exception:  # pragma: no cover
            return loaded
        for ep in group:
            try:
                obj = ep.load()
                plugin = obj() if isinstance(obj, type) else obj
                self.register(plugin)
                loaded.append(plugin.id)
            except Exception:  # noqa: BLE001
                log.exception("failed to load plugin entry point %s", ep.name)
        return loaded

    def builtin_module_names(self) -> list[str]:
        return ["rdpstudio.protocols.ssh", "rdpstudio.protocols.rdp", "rdpstudio.protocols.local"]


_REGISTRY: PluginRegistry | None = None


def registry() -> PluginRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PluginRegistry()
        for modname in _REGISTRY.builtin_module_names():
            try:
                importlib.import_module(modname)
            except Exception:  # noqa: BLE001
                log.exception("builtin plugin module failed to import: %s", modname)
        _REGISTRY.load_entry_points()
    return _REGISTRY


def reset_registry() -> None:
    """Test hook."""
    global _REGISTRY
    _REGISTRY = None
