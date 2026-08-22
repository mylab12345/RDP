"""SSH session controller: owns the worker thread, terminal, tunnels, SFTP."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtWidgets import QWidget

from ...core import paths
from ...core.log import get_logger
from ...core.models import Session
from ...core.plugin import (
    Capabilities,
    ProtocolPlugin,
    SessionContext,
    SessionController,
    SessionState,
)
from ...core.reconnect import ReconnectPolicy
from ..base_caps import capability_set
from .worker import AuthMaterial, SshWorker

log = get_logger("ssh.session")


class SshSessionController(SessionController):
    """One SSH tab: transport + shell channel, with reconnect support."""

    transportUp = Signal()  # emitted when transport is ready (SFTP/tunnels ok)

    # cross-thread bridges to the worker (auto → queued connections)
    # write/resize now also have direct thread-safe fast paths
    _sigWrite = Signal(bytes)
    _sigResize = Signal(int, int)
    _sigStartForward = Signal(dict)
    _sigStopForward = Signal(int)
    _sigShutdown = Signal(str)

    def __init__(self, definition: Session, ctx: SessionContext, parent=None) -> None:
        super().__init__(definition, ctx, parent)
        self._policy = ReconnectPolicy.from_settings(ctx.settings)
        self._attempt = 0
        self._wanted_stop = False

        from ...ui.terminal import TerminalView

        self.term = TerminalView(ctx.settings)
        self.term.dataWritten.connect(self._on_terminal_input)
        self.term.sizeChanged.connect(lambda c, r: self._worker_call("resize_pty", c, r))
        self.term.clipboardRequested.connect(self._on_osc52)

        self._thread: QThread | None = None
        self._worker: SshWorker | None = None
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_reconnect)

        self.set_state(SessionState.CLOSED)

    # ------------------------------------------------------------------
    def capabilities(self) -> Capabilities:
        return capability_set(shell=True, sftp=True, tunnels=True, monitor=True)

    def widget(self) -> QWidget:
        return self.term

    def term_size(self) -> tuple[int, int]:
        return self.term.cols_rows()

    # ------------------------------------------------------------------
    def start(self) -> None:
        self._wanted_stop = False
        self._spawn_worker()
        if self._thread is not None and self._worker is not None:
            # The worker now starts its pump in a Python thread and returns
            # immediately, so the QThread event loop stays alive and queued
            # slots (forwards, shutdown) still work. Input uses a direct
            # thread-safe path for zero-latency typing.
            self._thread.started.connect(self._worker.connect_and_shell)
            self._thread.start()

    def _worker_connect(self) -> None:
        """Legacy hook — kept for tests; prefer thread.started → worker slot."""
        if self._worker is not None:
            self._worker.connect_and_shell()

    def _spawn_worker(self) -> None:
        assert self._thread is None and self._worker is None
        material = self._build_material(self.definition)
        cols, rows = self.term.cols_rows()
        self._worker = SshWorker(
            host=self.definition.host,
            port=self.definition.endpoint()[1],
            material=material,
            known_hosts_path=Path(paths.known_hosts_file()),
            host_key_policy=self.ctx.settings.host_key_policy,
            prompter=self.ctx.prompter,
            keepalive=self.definition.keepalive,
            compression=self.definition.compression,
            timeout=self.definition.timeout,
            term_size=(cols, rows),
            startup_command=self.definition.startup_command,
        )
        self._worker.connected.connect(self._on_connected)
        self._worker.disconnected.connect(self._on_disconnected)
        self._worker.failed.connect(self._on_failed)
        self._worker.output.connect(self.term.feed)
        self._worker.stateInfo.connect(
            lambda txt: self.statusInfo.emit({"status_text": txt})
        )
        self._worker.forwardEvent.connect(
            lambda ev: self.statusInfo.emit({"forward": ev})
        )
        # bridge signals → worker slots (queued: worker lives on its thread)
        # For typing we now call directly, but keep signals for compat.
        self._sigWrite.connect(self._worker.write_input_slot)
        self._sigResize.connect(self._worker.resize_pty_slot)
        self._sigStartForward.connect(self._worker.start_forward)
        self._sigStopForward.connect(self._worker.stop_forward)
        self._sigShutdown.connect(self._worker.shutdown)
        self._thread = QThread(self)
        self._thread.setObjectName(f"ssh-{self.definition.host}")
        # when the pump ends (any reason), let the thread's event loop exit
        self._worker.disconnected.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.moveToThread(self._thread)

    def _build_material(self, defn: Session) -> AuthMaterial:
        password = None
        key_path = ""
        passphrase = None
        allow_agent = defn.auth == "agent"
        if defn.auth == "password":
            # plain password saved on the session (simple path, no vault),
            # falling back to a vault credential, else prompt at connect
            password = defn.password or (self._vault_secret(defn.credential_id) or None)
        elif defn.auth == "credential":
            password = self._vault_secret(defn.credential_id)
        elif defn.auth == "key":
            key_path = defn.key_path
            if defn.credential_id:  # key passphrase kept in vault
                passphrase = self._vault_secret(defn.credential_id)
        jump = None
        if defn.jump_session_id:
            jump_defn = self.ctx.store.get(defn.jump_session_id)
            if jump_defn is not None and jump_defn.protocol == "ssh":
                jump = self._build_material(jump_defn)
            else:
                log.warning("jump session %s not found / not ssh; ignoring", defn.jump_session_id)
        return AuthMaterial(
            host=defn.host,
            port=defn.endpoint()[1],
            username=defn.username,
            password=password,
            key_path=key_path,
            key_passphrase=passphrase,
            allow_agent=allow_agent,
            jump=jump,
        )

    def _vault_secret(self, credential_id: str) -> str | None:
        try:
            cred = self.ctx.vault.get(credential_id)
            if cred is not None and cred.secret:
                return cred.secret
        except Exception:  # vault locked etc.
            return None
        return None

    # -- lifecycle events -------------------------------------------------
    def _on_connected(self, info: dict) -> None:
        self._attempt = 0
        self.set_state(SessionState.CONNECTED)
        self.titleChanged.emit(self.definition.display_name())
        self.statusInfo.emit({"connected": info, "status_text": ""})
        self.transportUp.emit()
        self.ctx.publish("session/connected", {"protocol": "ssh", **info})
        # Ensure terminal gets focus after connect — previously focus could
        # stay on the quick-connect box, making it look like typing was broken.
        QTimer.singleShot(0, lambda: self.term.setFocus())

    def _on_failed(self, message: str) -> None:
        self.set_state(SessionState.FAILED)
        self.statusInfo.emit({"error": message, "status_text": message})
        self._teardown_thread()
        if self.definition.auto_reconnect and not self._wanted_stop:
            self._schedule_reconnect()
        else:
            self.emit_finished_once(f"connection failed: {message}")

    def _on_disconnected(self, reason: str) -> None:
        if self._wanted_stop or not self.definition.auto_reconnect:
            self._teardown_thread()
            self.emit_finished_once(reason or "closed")
            return
        self.set_state(SessionState.RECONNECTING)
        self._teardown_thread()
        self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        self._attempt += 1
        if not self._policy.should_retry(self._attempt):
            self.emit_finished_once("gave up reconnecting")
            return
        delay = self._policy.delay_for_attempt(self._attempt)
        self.reconnectScheduled.emit(self._attempt, delay)
        self.statusInfo.emit({"status_text": f"reconnecting in {delay:.1f}s (attempt {self._attempt})…"})
        self._reconnect_timer.start(int(delay * 1000))

    def _do_reconnect(self) -> None:
        if self._wanted_stop:
            return
        log.info("reconnecting to %s (attempt %d)", self.definition.host, self._attempt)
        self.set_state(SessionState.RECONNECTING)
        self._spawn_worker()
        if self._thread is not None and self._worker is not None:
            self._thread.started.connect(self._worker.connect_and_shell)
            self._thread.start()

    def request_reconnect(self) -> None:
        self._attempt = 0
        self._wanted_stop = False
        if self._thread is None:
            self._do_reconnect()
        else:
            self.statusInfo.emit({"status_text": "already connecting…"})

    def stop(self, reason: str = "closed by user") -> None:
        self._wanted_stop = True
        self._reconnect_timer.stop()
        worker = self._worker
        if worker is not None:
            worker.request_stop()  # unblocks the pump on the worker thread
            self._sigShutdown.emit(reason)  # best-effort graceful shutdown slot
        self._teardown_thread()
        self.emit_finished_once(reason)

    # -- helpers -----------------------------------------------------------
    def _worker_call(self, method: str, *args) -> None:
        """Thread-safe dispatch to worker.

        For input and resize we call directly (no queued delay) so typing
        feels instant even under load. Forwards/shutdown still go via queued
        signals because they touch the TunnelManager which lives on the
        worker's QThread.
        """
        worker = self._worker
        if worker is None:
            return
        if method == "write_input" and args:
            try:
                worker.write_input(bytes(args[0]))
                return
            except Exception:
                pass
            # fallback to queued
            self._sigWrite.emit(bytes(args[0]))
        elif method == "resize_pty" and len(args) == 2:
            try:
                worker.resize_pty(int(args[0]), int(args[1]))
                return
            except Exception:
                pass
            self._sigResize.emit(int(args[0]), int(args[1]))
        elif method == "start_forward" and args:
            self._sigStartForward.emit(dict(args[0]))
        elif method == "stop_forward" and args:
            self._sigStopForward.emit(int(args[0]))
        elif method == "shutdown" and args:
            self._sigShutdown.emit(str(args[0]))
        elif method == "shutdown":
            self._sigShutdown.emit("")

    def _on_terminal_input(self, data: bytes) -> None:
        self._worker_call("write_input", data)

    def _on_osc52(self, text: str) -> None:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(text)

    def _teardown_thread(self) -> None:
        thread, worker = self._thread, self._worker
        self._thread, self._worker = None, None
        if thread is None or worker is None:
            return

        def _finish() -> None:
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(1000)
            worker.deleteLater()

        # give the worker a moment to finish its current select() iteration
        QTimer.singleShot(120, _finish)

    # -- tunnels & sftp ------------------------------------------------------
    def start_forward(self, forward_dict: dict) -> None:
        self._worker_call("start_forward", forward_dict)

    def stop_forward(self, port: int) -> None:
        self._worker_call("stop_forward", port)

    def open_sftp(self) -> None:
        if self._worker is None:
            return
        from ...ui.main_window import get_main_window

        win = get_main_window(self.ctx.parent_widget)
        if win is not None:
            win.open_sftp_for_controller(self)

    def open_tunnels(self) -> None:
        from ...ui.main_window import get_main_window

        win = get_main_window(self.ctx.parent_widget)
        if win is not None:
            win.open_tunnels_for_controller(self)

    def open_monitor(self) -> None:
        from ...ui.main_window import get_main_window

        win = get_main_window(self.ctx.parent_widget)
        if win is not None:
            win.open_monitor_for_controller(self)

    def transport_provider(self):
        """Callable for SftpEngine: returns live transport (engine thread)."""
        worker = self._worker

        def provider():
            return worker.transport() if worker is not None else None

        return provider


class SshPlugin(ProtocolPlugin):
    id = "ssh"
    title = "SSH"
    description = "Secure shell to Linux/BSD hosts: terminal, SFTP, tunnels."
    default_port = 22
    icon_name = "terminal"
    tags = ["ssh", "shell", "sftp"]

    def create_session(self, definition: Session, ctx: SessionContext) -> SessionController:
        return SshSessionController(definition, ctx)

    def quick_connect_target(self, text: str) -> Session | None:
        parsed = parse_ssh_target(text)
        if parsed is None:
            return None
        user, host, port = parsed
        s = Session(protocol="ssh", host=host, port=port or 22, username=user or "")
        s.name = s.target()
        return s


def parse_ssh_target(text: str) -> tuple[str, str, int] | None:
    """Parse ``[user@]host[:port]``; returns (user, host, port) or None."""
    text = text.strip()
    if not text or "/" in text or " " in text:
        return None
    user = ""
    if "@" in text:
        user, _, rest = text.partition("@")
        text = rest
    port = 0
    if ":" in text:
        host, _, port_s = text.rpartition(":")
        if not host or not port_s.isdigit():
            return None
        port = int(port_s)
        text = host
    if not text:
        return None
    return user, text, port
