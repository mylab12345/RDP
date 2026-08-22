"""Thread-safe prompt bridge.

Protocol workers live on background threads and sometimes *must* ask the user
something mid-handshake (accept a new host key? enter a password?). Qt widgets
may only be touched from the GUI thread, so the GUI prompt provider marshals
the question to the GUI thread with a signal and blocks the calling worker on
a :class:`threading.Event` until the answer arrives.

``HeadlessPromptProvider`` is the non-GUI implementation used by tests and CI.
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal


class _Bridge(QObject):
    askHostKey = Signal(str, str, str, str, bool)  # token, host, key_type, fp, changed
    askSecret = Signal(str, str, str, bool, str)  # token, title, prompt, secret, preset

    def __init__(self) -> None:
        super().__init__()
        self._events: dict[str, threading.Event] = {}
        self._results: dict[str, object] = {}
        self._lock = threading.Lock()

    def make_event(self, token: str) -> threading.Event:
        ev = threading.Event()
        with self._lock:
            self._events[token] = ev
        return ev

    def resolve(self, token: str, value) -> None:
        with self._lock:
            self._results[token] = value
            ev = self._events.pop(token, None)
        if ev:
            ev.set()  # wake the blocked worker

    def wait(self, token: str, ev: threading.Event, timeout: float = 600.0):
        ev.wait(timeout)
        with self._lock:
            return self._results.pop(token, None)


class GuiPromptProvider:
    """Implements core.plugin.PromptProvider; safe to call from any thread."""

    def __init__(self, parent_widget=None) -> None:
        self._bridge = _Bridge()
        self._parent = parent_widget
        self._counter = 0
        self._counter_lock = threading.Lock()
        self._bridge.askHostKey.connect(self._dlg_host_key)
        self._bridge.askSecret.connect(self._dlg_secret)

    def _next_token(self) -> str:
        with self._counter_lock:
            self._counter += 1
            return f"t{self._counter}"

    # -- PromptProvider API ------------------------------------------------
    def ask_host_key(self, host: str, key_type: str, fingerprint: str, changed: bool) -> bool:
        token = self._next_token()
        ev = self._bridge.make_event(token)
        self._bridge.askHostKey.emit(token, host, key_type, fingerprint, changed)
        return bool(self._bridge.wait(token, ev))

    def ask_secret(self, title: str, prompt: str, secret: bool = True, preset: str = "") -> str | None:
        token = self._next_token()
        ev = self._bridge.make_event(token)
        self._bridge.askSecret.emit(token, title, prompt, secret, preset)
        result = self._bridge.wait(token, ev)
        return None if result is None else str(result)

    # -- GUI slots (run on GUI thread) ---------------------------------------
    def _dlg_host_key(self, token: str, host: str, key_type: str, fingerprint: str, changed: bool) -> None:
        from PySide6.QtWidgets import QMessageBox

        if changed:
            title = "⚠ Host key has CHANGED"
            text = (
                f"<b>WARNING: the host key for {host} has changed!</b><br>"
                "This can indicate a man-in-the-middle attack, or that the server "
                "was rebuilt.<br><br>"
                f"New key ({key_type}):<br><code>{fingerprint}</code><br><br>"
                "Accept the new key and update known_hosts?"
            )
            icon = QMessageBox.Icon.Warning
        else:
            title = "Unknown host key"
            text = (
                f"The authenticity of host <b>{host}</b> can't be established.<br>"
                f"{key_type} key fingerprint:<br><code>{fingerprint}</code><br><br>"
                "Trust and connect?"
            )
            icon = QMessageBox.Icon.Question
        box = QMessageBox(
            icon, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, self._parent,
        )
        box.exec()
        self._bridge.resolve(token, box.result() == QMessageBox.StandardButton.Yes.value)

    def _dlg_secret(self, token: str, title: str, prompt: str, secret: bool, preset: str) -> None:
        from PySide6.QtWidgets import QInputDialog

        if secret:
            text, ok = QInputDialog.getText(
                self._parent, title, prompt, echo=QInputDialog.EchoMode.Password, text=preset
            )
        else:
            text, ok = QInputDialog.getText(self._parent, title, prompt, text=preset)
        self._bridge.resolve(token, text if ok else None)


class HeadlessPromptProvider:
    """For tests: auto-answers with configured values."""

    def __init__(
        self,
        accept_host_keys: bool = True,
        secrets: dict[str, str] | None = None,
        default_secret: str | None = None,
    ) -> None:
        self.accept_host_keys = accept_host_keys
        self.secrets = secrets or {}
        self.default_secret = default_secret

    def ask_host_key(self, host: str, key_type: str, fingerprint: str, changed: bool) -> bool:
        return self.accept_host_keys

    def ask_secret(self, title: str, prompt: str, secret: bool = True, preset: str = "") -> str | None:
        for key, value in self.secrets.items():
            if key in prompt or key in title:
                return value
        return self.default_secret
