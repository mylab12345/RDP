"""RDP client session controller.

RDP remoting is delegated to the platform's native/FreeRDP client, exactly
like Remmina (FreeRDP) and mRemoteNG (mstsc COM control) do:

- Windows: generates a ``.rdp`` file and launches the built-in ``mstsc.exe``
  (with drive/clipboard redirection, gateway, autoreconnect settings).
- Linux: launches ``sdl-freerdp3`` / ``xfreerdp`` (FreeRDP 2/3) with matching
  flags, including ``+auto-reconnect``.

The tab itself becomes a *session monitor*: live status (process running /
exited), latency probe (X.224 negotiation), and controls (reconnect, probe,
open session). This keeps the GUI honest — RDP renders in its own window —
while everything (saved settings, credentials, gateway, reconnect) is managed
centrally. Embedding FreeRDP's framebuffer in-process is a documented future
extension point (see docs/PROTOCOLS.md).
"""

from __future__ import annotations

import os
import shutil
import sys

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...core.log import get_logger
from ...core.models import Session
from ...core.plugin import (
    Capabilities,
    ProtocolPlugin,
    SessionContext,
    SessionController,
    SessionState,
)
from ..base_caps import capability_set
from .negotiate import RdpProbeError, probe
from .rdpfile import write_rdp_file

log = get_logger("rdp.session")


def find_rdp_client() -> tuple[str, str] | None:
    """Locate an RDP client binary: (path, kind) where kind is mstsc|freerdp."""
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        mstsc = os.path.join(system_root, "System32", "mstsc.exe")
        alt = shutil.which("mstsc")
        if os.path.exists(mstsc):
            return mstsc, "mstsc"
        if alt:
            return alt, "mstsc"
        return None
    for name in (
        "sdl-freerdp3",
        "sdl-freerdp",
        "wlfreerdp3",
        "wlfreerdp",
        "xfreerdp3",
        "xfreerdp2",
        "xfreerdp",
    ):
        path = shutil.which(name)
        if path:
            return path, "freerdp"
    return None


def build_freerdp_args(defn: Session, password: str | None) -> list[str]:
    host, port = defn.endpoint()
    args = ["/v:" + (f"{host}:{port}" if port != 3389 else host)]
    if defn.username:
        domain_prefix = f"{defn.domain}\\" if defn.domain else ""
        args.append(f"/u:{domain_prefix}{defn.username}")
    if password and defn.rdp_pass_on_cmdline:
        args.append(f"/p:{password}")  # visible in ps(1); opt-in only
    args.append(f"/size:{defn.rdp_width}x{defn.rdp_height}")
    args.append(f"/bpp:{defn.rdp_color_depth}")
    args.append("/clipboard" if defn.rdp_clipboard else "-clipboard")
    if defn.rdp_fullscreen:
        args.append("/f")
    if defn.rdp_drives:
        args.append(f"/drive:RDPStudio,{os.path.expanduser('~')}")
    args.append("/cert:ignore" if defn.rdp_cert_ignore else "/cert:tofu")
    args.append("+auto-reconnect")
    args.append("/network:auto")
    if defn.rdp_gateway_host:
        args.append(f"/g:{defn.rdp_gateway_host}:{defn.rdp_gateway_port}")
        if defn.rdp_gateway_user:
            args.append(f"/gu:{defn.rdp_gateway_user}")
    return args


class RdpSessionController(SessionController):
    """Launches + monitors the native RDP client for one saved RDP session."""

    def __init__(self, definition: Session, ctx: SessionContext, parent=None) -> None:
        super().__init__(definition, ctx, parent)
        self._proc: QProcess | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        head = QHBoxLayout()
        self._icon_label = QLabel("🖥")
        self._icon_label.setStyleSheet("font-size: 34px;")
        title = QLabel(f"<b>{self.definition.display_name()}</b>")
        self._target_label = QLabel(self.definition.target())
        self._target_label.setObjectName("muted")
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addWidget(title)
        box.addWidget(self._target_label)
        head.addWidget(self._icon_label)
        head.addLayout(box)
        head.addStretch(1)
        layout.addLayout(head)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("hairline")
        layout.addWidget(line)

        self._status = QLabel("Not connected")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("font-size: 13px;")
        layout.addWidget(self._status)

        self._probe_label = QLabel("")
        self._probe_label.setObjectName("muted")
        self._probe_label.setWordWrap(True)
        layout.addWidget(self._probe_label)

        buttons = QHBoxLayout()
        self._btn_connect = QPushButton("  Connect")
        self._btn_connect.clicked.connect(self.start)
        self._btn_probe = QPushButton("  Test server")
        self._btn_probe.clicked.connect(self.run_probe)
        self._btn_stop = QPushButton("  Disconnect")
        self._btn_stop.clicked.connect(lambda: self.stop("closed by user"))
        self._btn_stop.setEnabled(False)
        for b in (self._btn_connect, self._btn_probe, self._btn_stop):
            b.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            buttons.addWidget(b)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        note = QLabel(
            "The RDP window opens in its own OS window (mstsc / FreeRDP).\n"
            "Clipboard and drive redirection follow the session settings."
        )
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addStretch(1)

        self._page = page
        client = find_rdp_client()
        if client is None:
            self._btn_connect.setEnabled(False)
            self._status.setText(
                "No RDP client found.\n"
                "Windows ships mstsc.exe; on Linux install FreeRDP "
                "(e.g. `sudo apt install freerdp3-x11` or freerdp2-x11)."
            )

    def capabilities(self) -> Capabilities:
        return capability_set(external_window=True)

    def widget(self) -> QWidget:
        return self._page

    # ------------------------------------------------------------------
    def start(self) -> None:
        client = find_rdp_client()
        if client is None:
            self.set_state(SessionState.FAILED)
            self._status.setText("No RDP client executable found on this machine.")
            return
        path, kind = client
        password = self._resolve_secret()
        self.set_state(SessionState.CONNECTING)
        self._status.setText(f"Launching {os.path.basename(path)}…")
        self._status_info({"client": os.path.basename(path)})
        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_proc_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        try:
            if kind == "mstsc":
                rdp_file = write_rdp_file(self.definition)
                self._proc.start(
                    path,
                    [
                        str(rdp_file),
                        f"/w:{self.definition.rdp_width}",
                        f"/h:{self.definition.rdp_height}",
                    ],
                )
            else:
                self._proc.start(path, build_freerdp_args(self.definition, password))
        except Exception as exc:  # noqa: BLE001
            self._on_error_text(str(exc))
            return
        self._proc.started.connect(self._on_proc_started)

    def _resolve_secret(self) -> str | None:
        defn = self.definition
        if defn.credential_id:
            try:
                cred = self.ctx.vault.get(defn.credential_id)
                if cred and cred.secret:
                    return cred.secret
            except Exception:  # vault locked
                return None
        return None

    def _on_proc_started(self) -> None:
        self.set_state(SessionState.CONNECTED)
        self._status.setText(
            "RDP session window is open (external client). "
            "This tab monitors the connection."
        )
        self._btn_connect.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self.titleChanged.emit(self.definition.display_name())
        self.ctx.publish("session/connected", {"protocol": "rdp", "host": self.definition.host})

    def _on_proc_finished(self) -> None:
        code = self._proc.exitCode() if self._proc else 0
        self._btn_connect.setEnabled(True)
        self._btn_stop.setEnabled(False)
        reason = f"RDP client exited (code {code})"
        if self._state in (SessionState.CONNECTED, SessionState.RECONNECTING) and self.definition.auto_reconnect:
            self.set_state(SessionState.RECONNECTING)
            self._status.setText(reason + " — auto-reconnecting…")
            self.reconnectScheduled.emit(1, 3.0)
            QTimer.singleShot(3000, lambda: self.start() if self._state == SessionState.RECONNECTING else None)
        else:
            self._status.setText(reason)
            self.emit_finished_once(reason)

    def _on_proc_error(self, error) -> None:
        from PySide6.QtCore import QProcess

        names = {
            QProcess.ProcessError.FailedToStart: "client failed to start",
            QProcess.ProcessError.Crashed: "client crashed",
            QProcess.ProcessError.Timedout: "timeout",
            QProcess.ProcessError.WriteError: "write error",
            QProcess.ProcessError.ReadError: "read error",
            QProcess.ProcessError.UnknownError: "unknown error",
        }
        self._on_error_text(names.get(error, "error"))

    def _on_error_text(self, message: str) -> None:
        self.set_state(SessionState.FAILED)
        self._status.setText(message)
        self._btn_connect.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self.statusInfo.emit({"error": message})

    def stop(self, reason: str = "closed by user") -> None:
        if self._proc is not None:
            self._proc.kill()
        self._btn_connect.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self.emit_finished_once(reason)

    def request_reconnect(self) -> None:
        self.start()

    # -- probe -------------------------------------------------------------
    def run_probe(self) -> None:
        host, port = self.definition.endpoint()
        self._probe_label.setText(f"Probing {host}:{port}…")

        def work() -> None:
            try:
                result = probe(host, port, timeout=5.0)
            except RdpProbeError as exc:
                self._probe_label.setText(f"✗ {exc}")
                return
            if result.failure_code is not None:
                self._probe_label.setText(
                    f"RDP server answered; refused requested security: {result.failure_name}"
                )
            else:
                self._probe_label.setText(
                    f"✓ RDP server OK — security: {result.selected_protocol_name}, "
                    f"{result.latency_ms:.0f} ms"
                )

        QTimer.singleShot(0, work)

    def _status_info(self, info: dict) -> None:
        self.statusInfo.emit(info)


class RdpPlugin(ProtocolPlugin):
    id = "rdp"
    title = "RDP"
    description = "Remote Desktop to Windows hosts (mstsc / FreeRDP), with server health probes."
    default_port = 3389
    icon_name = "windows"
    tags = ["rdp", "windows", "remote-desktop"]

    def create_session(self, definition: Session, ctx: SessionContext) -> SessionController:
        return RdpSessionController(definition, ctx)

    def quick_connect_target(self, text: str) -> Session | None:
        from ..ssh.session import parse_ssh_target

        parsed = parse_ssh_target(text)
        if parsed is None:
            return None
        user, host, port = parsed
        s = Session(protocol="rdp", host=host, port=port or 3389, username=user or "")
        s.name = s.target()
        return s
