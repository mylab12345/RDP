"""RDP session controller — built-in (embedded) and external display modes.

RDP remoting is provided by FreeRDP (Linux) or the native client (mstsc on
Windows):

- **Built-in (embedded, Linux/X11)**: the FreeRDP client is launched with
  ``/parent-window:<xid>`` so the remote desktop renders *inside this
  application's window* — no separate RDP window appears. Keyboard and mouse
  are handled by FreeRDP on its embedded X window.
- **External**: launches ``mstsc.exe`` (Windows) or a normal ``xfreerdp``
  window; the tab becomes a session monitor (status, probe, reconnect).

Display mode is chosen in Settings → Connection → "RDP display":
``auto`` (built-in when possible, default), ``embedded`` or ``external``.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
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
    if password and (defn.password or defn.rdp_pass_on_cmdline):
        # a password saved on the session is passed automatically (that is
        # what makes the simple no-vault flow work without a terminal prompt);
        # vault passwords are only passed when the opt-in flag is set
        args.append(f"/p:{password}")
    args.append(f"/size:{defn.rdp_width}x{defn.rdp_height}")
    args.append(f"/bpp:{defn.rdp_color_depth}")
    args.append("/clipboard" if defn.rdp_clipboard else "-clipboard")
    if defn.rdp_fit_screen:
        args.append("/smart-sizing")  # scale the remote desktop to fit the window
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


def build_embedded_args(defn: Session, password: str | None, parent_xid: int) -> list[str]:
    """FreeRDP args for the built-in mode: render inside our X window.

    ``/parent-window`` makes FreeRDP create its framebuffer as a *child* of
    the given X11 window, so the desktop appears inside RDP Studio itself;
    ``-decorations`` drops the title bar (we provide the tab chrome).
    """
    args = build_freerdp_args(defn, password)
    if defn.rdp_fullscreen:  # fullscreen is meaningless inside a tab
        args.remove("/f")
    args += [f"/parent-window:{parent_xid}", "-decorations"]
    return args


def embedded_support(
    find_client: Callable | None = None,
    platform_name: str | None = None,
    display: str | None = None,
) -> tuple[bool, str]:
    """Whether the built-in (embedded) RDP display is possible.

    Requires: a FreeRDP binary (mstsc cannot embed), the Qt X11 platform
    plugin (window embedding is an X11 mechanism) and an X display.
    Returns ``(ok, reason)`` — the reason doubles as a UI hint.
    """
    client = (find_client or find_rdp_client)()
    if client is None:
        return False, "No FreeRDP client found (install `freerdp3-x11` or `freerdp2-x11`)."
    if client[1] != "freerdp":
        return False, "Only FreeRDP can render inside the app (mstsc cannot be embedded)."
    name = platform_name
    if name is None:
        app = QGuiApplication.instance()
        name = app.platformName() if app is not None else ""
    if name != "xcb":
        return False, f"Built-in display needs X11 (current Qt platform: {name or 'none'})."
    disp = display if display is not None else os.environ.get("DISPLAY")
    if not disp:
        return False, "No X display ($DISPLAY) available."
    return True, ""


class _EmbeddedSurface(QWidget):
    """Native X11 window that hosts the embedded FreeRDP child window."""

    resized = Signal()  # emitted when the tab was resized while connected

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet("background: #101418;")
        self._launch_size: tuple[int, int] | None = None

    def set_launch_size(self, size: tuple[int, int]) -> None:
        self._launch_size = size

    def size_changed(self) -> bool:
        """True if the widget moved >=32 px away from the launch size."""
        if self._launch_size is None:
            return False
        dw = abs(self.width() - self._launch_size[0])
        dh = abs(self.height() - self._launch_size[1])
        return dw >= 32 or dh >= 32

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._launch_size is not None and self.size_changed():
            self.resized.emit()
        if getattr(self, "_hint", None) is not None:
            # keep the hint centred over the desktop
            self._hint.setGeometry(
                0,
                (self.height() - self._hint.height()) // 2,
                self.width(),
                self._hint.height(),
            )


class RdpSessionController(SessionController):
    """Runs the RDP session — built-in (embedded in this app) or external."""

    widgetChanged = Signal()  # display mode switched; tab must swap the widget

    def __init__(self, definition: Session, ctx: SessionContext, parent=None) -> None:
        super().__init__(definition, ctx, parent)
        self._proc: QProcess | None = None
        self._resized_restart = False
        self._build_ui()
        # resolved up-front so the tab shows the right page before start()
        self._mode: str = self.resolve_mode()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # --- external mode: session monitor page --------------------------
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
        self._page_ext = page

        # --- built-in mode: the desktop renders in this widget ------------
        emb = QWidget()
        el = QVBoxLayout(emb)
        el.setContentsMargins(0, 0, 0, 0)
        self._surface = _EmbeddedSurface()
        self._surface.resized.connect(self._on_surface_resized)
        self._emb_hint = QLabel("", self._surface)
        self._emb_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._emb_hint.setStyleSheet("color: #9fb2c8; font-size: 13px; background: rgba(16,20,24,180);")
        self._emb_hint.setWordWrap(True)
        self._emb_hint.hide()
        self._surface._hint = self._emb_hint
        el.addWidget(self._surface, 1)
        self._page_emb = emb

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
        if self._mode == "embedded":
            return self._page_emb
        return self._page_ext

    # ------------------------------------------------------------------
    # mode
    # ------------------------------------------------------------------
    def resolve_mode(self) -> str:
        pref = getattr(self.ctx.settings, "rdp_client", "auto")
        if pref == "external":
            return "external"
        ok, reason = embedded_support()
        if pref == "embedded" and not ok:
            log.warning("built-in RDP requested but unavailable: %s", reason)
        return "embedded" if ok else "external"

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        new_mode = self.resolve_mode()
        if new_mode != self._mode:
            self._mode = new_mode
            self.widgetChanged.emit()  # the tab must show the other page
        if self._mode == "embedded":
            self._start_embedded()
        else:
            self._start_external()

    def _start_external(self) -> None:
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

    def _fall_back_to_external(self, why: str) -> None:
        log.warning("built-in RDP unavailable at start (%s) — using external window", why)
        self._mode = "external"
        self.widgetChanged.emit()
        self._start_external()

    def _start_embedded(self) -> None:
        client = find_rdp_client()
        if client is None or client[1] != "freerdp":
            self._fall_back_to_external("no FreeRDP client")
            return
        path = client[0]
        password = self._resolve_secret()
        xid = int(self._surface.winId())
        if not xid:
            self._fall_back_to_external("no native X11 window id")
            return
        self._surface.set_launch_size((self._surface.width(), self._surface.height()))
        self.set_state(SessionState.CONNECTING)
        self._set_emb_hint("Connecting…")
        self._status_info({"client": os.path.basename(path), "embedded": True})
        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_proc_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        try:
            self._proc.start(path, build_embedded_args(self.definition, password, xid))
        except Exception as exc:  # noqa: BLE001
            self._on_error_text(str(exc))
            return
        self._proc.started.connect(self._on_proc_started)

    def _on_surface_resized(self) -> None:
        """Restart the embedded client so the desktop follows the tab size."""
        if self._mode != "embedded" or self._proc is None:
            return
        if self._proc.state() != QProcess.ProcessState.Running:
            return
        if self._state not in (SessionState.CONNECTED, SessionState.CONNECTING):
            return
        log.info("RDP tab resized — restarting embedded client to refit")
        self._surface.set_launch_size((self._surface.width(), self._surface.height()))
        self._resized_restart = True
        self._proc.kill()

    def _set_emb_hint(self, text: str) -> None:
        self._emb_hint.setText(text)
        self._emb_hint.setVisible(bool(text))

    def _on_proc_started(self) -> None:
        self.set_state(SessionState.CONNECTED)
        self._set_emb_hint("")
        if self._mode == "embedded":
            self._status.setText("Built-in RDP window active.")
        else:
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
        resized = self._resized_restart
        self._resized_restart = False
        self._btn_connect.setEnabled(True)
        self._btn_stop.setEnabled(False)
        if resized:
            reason = "refitting to new window size"
        else:
            reason = f"RDP client exited (code {code})"
        if self._state in (SessionState.CONNECTED, SessionState.RECONNECTING) and self.definition.auto_reconnect:
            self.set_state(SessionState.RECONNECTING)
            if self._mode == "embedded":
                self._set_emb_hint(reason + " — reconnecting…")
            else:
                self._status.setText(reason + " — auto-reconnecting…")
            self.reconnectScheduled.emit(1, 1.0 if resized else 3.0)
            delay = 500 if resized else 3000
            QTimer.singleShot(delay, lambda: self.start() if self._state == SessionState.RECONNECTING else None)
        else:
            if self._mode == "embedded":
                self._set_emb_hint("Disconnected — use Reconnect in the tab bar.")
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
        if self._mode == "embedded":
            self._set_emb_hint(message)
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

    # ------------------------------------------------------------------
    def _resolve_secret(self) -> str | None:
        defn = self.definition
        if defn.password:
            return defn.password  # plain password saved on the session (no vault)
        if defn.credential_id:
            try:
                cred = self.ctx.vault.get(defn.credential_id)
                if cred and cred.secret:
                    return cred.secret
            except Exception:  # vault locked
                return None
        return None

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
    description = "Remote Desktop to Windows hosts — built-in display (FreeRDP embedded) or mstsc/FreeRDP window."
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
