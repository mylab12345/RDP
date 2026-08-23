"""RDP session controller — built-in (embedded) and external display modes.

RDP remoting is provided by FreeRDP (Linux) or the native client (mstsc on
Windows):

- **Built-in (embedded)**: the FreeRDP client is launched with
  ``/parent-window:<xid>`` so the remote desktop renders *inside this
  application's window* — no separate RDP window appears, like MobaXterm's
  in-tab RDP. Keyboard and mouse are handled by FreeRDP on its embedded X
  window. On Wayland desktops the app restarts itself through XWayland
  (see :mod:`.embed`) to make this possible.
- **External**: launches ``mstsc.exe`` (Windows) or a normal ``xfreerdp``/
  ``sdl-freerdp`` window; the tab becomes a session monitor.

Display mode is chosen in Settings → Connection → "RDP display":
``auto`` (built-in when possible, default), ``embedded`` or ``external``.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer, Signal
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
from .embed import (
    EMBEDDABLE_CLIENTS,  # noqa: F401  (re-exported for tests/docs)
    embed_blocked_on_wayland,
    embedded_support,  # noqa: F401  (re-exported; historical import path)
    find_embedded_client,
    relaunch_under_x11,
)
from .negotiate import RdpProbeError, probe
from .rdpfile import write_rdp_file

log = get_logger("rdp.session")

# FreeRDP / Windows RD Session Host limits for the remote desktop resolution.
# Kept in sync with the Session dialog's spin-box ranges.
_MIN_RDP_W, _MIN_RDP_H = 640, 480
_MAX_RDP_W, _MAX_RDP_H = 7680, 4320
# Below this the surface is not laid out yet (widget not mapped); fall back
# to the session's saved resolution instead of launching a tiny desktop.
_MIN_MAPPED_W, _MIN_MAPPED_H = 320, 200


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
    """FreeRDP command line for ``defn`` — **never contains the secret**.

    The password is delivered through a private ``/args-from:file:`` args
    file (see :func:`write_args_file`) unless the user explicitly opts in
    via ``rdp_pass_on_cmdline`` (then ``/p:`` lands on argv, visible in
    ``ps`` — a documented opt-in, CWE-214).

    Why not ``/from-stdin``: FreeRDP ≥3.x reads stdin credentials through
    its terminal passphrase helper, which aborts with
    ``ERRCONNECT_CONNECT_CANCELLED`` (client exit 145) when stdin is a pipe
    instead of a TTY — exactly what QProcess gives it. ``/args-from`` is the
    supported non-TTY path and is what Remmina-class wrappers use too.
    """
    host, port = defn.endpoint()
    args = ["/v:" + (f"{host}:{port}" if port != 3389 else host)]
    if defn.username:
        domain_prefix = f"{defn.domain}\\" if defn.domain else ""
        args.append(f"/u:{domain_prefix}{defn.username}")
    if password and defn.rdp_pass_on_cmdline:
        # explicit opt-in only; default path routes the secret via args file
        args.append(f"/p:{password}")
    args.append(f"/size:{defn.rdp_width}x{defn.rdp_height}")
    args.append(f"/bpp:{defn.rdp_color_depth}")
    args.append("/clipboard" if defn.rdp_clipboard else "-clipboard")
    if defn.rdp_fit_screen:
        args.append("/smart-sizing")  # scale the remote desktop to fit the window
    if defn.rdp_fullscreen:
        args.append("/f")
    if defn.rdp_drives:
        args.append(f"/drive:KB-Remote,{os.path.expanduser('~')}")
    args.append("/cert:ignore" if defn.rdp_cert_ignore else "/cert:tofu")
    args.append("+auto-reconnect")
    args.append("/network:auto")
    if defn.rdp_gateway_host:
        args.append(f"/g:{defn.rdp_gateway_host}:{defn.rdp_gateway_port}")
        if defn.rdp_gateway_user:
            args.append(f"/gu:{defn.rdp_gateway_user}")
    return args


def password_via_stdin(defn: Session, password: str | None) -> bool:
    """Deprecated alias for :func:`uses_args_file` (old stdin mechanism)."""
    return uses_args_file(defn, password)


def uses_args_file(defn: Session, password: str | None) -> bool:
    """Whether the secret must be delivered via a private args file."""
    return bool(password) and not defn.rdp_pass_on_cmdline


def write_args_file(args: list[str]) -> Path:
    """Persist FreeRDP arguments one-per-line for ``/args-from:file:``.

    The file is created ``0600`` so the credential inside is private; the
    controller unlinks it shortly after the client starts. This keeps the
    secret out of ``ps``/``/proc/*/cmdline`` while avoiding the broken
    piped-stdin credential path of FreeRDP 3.x.
    """
    import tempfile

    fd, name = tempfile.mkstemp(prefix="rdpstudio-args-", suffix=".cmd")
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(args) + "\n")
    return Path(name)


def build_embedded_args(
    defn: Session, password: str | None, parent_xid: int, size: tuple[int, int] | None = None
) -> list[str]:
    """FreeRDP args for the built-in mode: render inside our X window.

    ``/parent-window`` makes FreeRDP create its framebuffer as a *child* of
    the given X11 window, so the desktop appears inside KB-Remote itself;
    ``-decorations`` drops the title bar (we provide the tab chrome).

    ``size`` (optional) is the *detected* display area of the embedded
    surface.  When given it replaces the session's fixed ``/size:`` so the
    remote desktop is created at exactly the resolution of the tab — the
    whole screen is visible, no scrolling or clipping.  Clamped to the
    FreeRDP/Windows-supported range.
    """
    args = build_freerdp_args(defn, password)
    if size is not None:
        w = min(max(int(size[0]), _MIN_RDP_W), _MAX_RDP_W)
        h = min(max(int(size[1]), _MIN_RDP_H), _MAX_RDP_H)
        args = [a for a in args if not a.startswith("/size:")]
        args.append(f"/size:{w}x{h}")
    if defn.rdp_fullscreen:  # fullscreen is meaningless inside a tab
        args.remove("/f")
    args += [f"/parent-window:{parent_xid}", "-decorations"]
    return args


def _redact_args(args: list[str]) -> str:
    """Command line for logs with any ``/p:`` secret masked."""
    out = []
    for a in args:
        if a.startswith("/p:"):
            out.append("/p:***")
        else:
            out.append(a)
    return " ".join(out)


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
    # probe thread → GUI thread (auto connection ⇒ queued)
    _sigProbeResult = Signal(str)

    def __init__(self, definition: Session, ctx: SessionContext, parent=None) -> None:
        super().__init__(definition, ctx, parent)
        self._proc: QProcess | None = None
        self._resized_restart = False
        self._probe_thread: threading.Thread | None = None
        self._args_file: Path | None = None  # /args-from:file: (holds the secret)
        self._embed_retry: bool = False
        self._proc_stderr: str = ""
        self._proc_stdout: str = ""
        self._proc_start_time: float = 0.0
        self._sigProbeResult.connect(self._on_probe_result)
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
        # offered only when Wayland is the sole obstacle to the built-in
        # display — restarting through XWayland enables the in-app desktop
        self._btn_inapp = QPushButton("⧉  Show inside app")
        self._btn_inapp.setToolTip(
            "Restart KB-Remote through XWayland (the X11 compatibility layer)\n"
            "so this remote desktop renders inside the app — no separate window."
        )
        self._btn_inapp.clicked.connect(self._restart_for_embedded)
        self._inapp_possible = embed_blocked_on_wayland()
        self._btn_inapp.setVisible(self._inapp_possible)
        for b in (self._btn_connect, self._btn_probe, self._btn_stop, self._btn_inapp):
            b.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            buttons.addWidget(b)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        if self._inapp_possible:
            note_text = (
                "In-app RDP needs X11. KB-Remote can restart through XWayland\n"
                "(the built-in X11 compatibility layer) so the desktop renders\n"
                "inside this tab — click “Show inside app”."
            )
        else:
            note_text = (
                "The RDP window opens in its own OS window (mstsc / FreeRDP).\n"
                "Clipboard and drive redirection follow the session settings."
            )
        note = QLabel(note_text)
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
        if not ok:
            log.warning(
                "built-in RDP display unavailable (%s) — %s",
                reason,
                "falling back to the external window",
            )
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
        self.set_state(SessionState.CONNECTING)
        self._status.setText(f"Launching {os.path.basename(path)}…")
        self._status_info({"client": os.path.basename(path)})
        try:
            if kind == "mstsc":
                rdp_file = write_rdp_file(self.definition)
                log.info("launching mstsc: %s %s", path, rdp_file)
                self._launch_client(path, direct_argv=[
                    str(rdp_file),
                    f"/w:{self.definition.rdp_width}",
                    f"/h:{self.definition.rdp_height}",
                ])
            else:
                args = build_freerdp_args(self.definition, self._resolve_secret())
                log.info("launching freerdp: %s %s", path, _redact_args(args))
                self._launch_client(path, args)
        except Exception as exc:  # noqa: BLE001
            self._on_error_text(str(exc))
            return

    def _fall_back_to_external(self, why: str) -> None:
        log.warning("built-in RDP unavailable at start (%s) — using external window", why)
        self._mode = "external"
        self.widgetChanged.emit()
        self._start_external()

    def _restart_for_embedded(self) -> None:
        """Restart the whole app via XWayland so this session can embed."""
        from PySide6.QtWidgets import QMessageBox


        parent = getattr(self.ctx, "parent_widget", None)
        answer = QMessageBox.question(
            parent,
            "Show RDP inside the app",
            "KB-Remote will restart through XWayland (the X11 compatibility\n"
            "layer of your desktop) so remote desktops render inside the app\n"
            "tab — no separate window, like MobaXterm.\n\n"
            "Open sessions will be closed. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        relaunch_under_x11()

    def _start_embedded(self) -> None:
        path = find_embedded_client()
        if path is None:
            self._fall_back_to_external("no X11 FreeRDP client (need xfreerdp for /parent-window)")
            return
        # Ensure the surface has a native window; defer if not yet mapped.
        xid = int(self._surface.winId())
        if not xid:
            # Widget not yet native (e.g. not shown) — retry once after event loop.
            if not self._embed_retry:
                self._embed_retry = True

                def _retry() -> None:
                    self._embed_retry = False
                    self._start_embedded()

                QTimer.singleShot(100, _retry)
            else:
                self._fall_back_to_external("no native X11 window id")
            return
        self._surface.set_launch_size((self._surface.width(), self._surface.height()))
        self.set_state(SessionState.CONNECTING)
        self._set_emb_hint("Connecting…")
        self._status_info({"client": os.path.basename(path), "embedded": True})
        try:
            # Fit the remote desktop to the detected display area of the tab
            # so the entire screen is visible inside the app.
            size = self._detected_size()
            args = build_embedded_args(self.definition, self._resolve_secret(), xid, size=size)
            log.info(
                "launching embedded freerdp (Remmina-style X11 reparent): %s %s (xid=%s, size=%dx%d)",
                path, _redact_args(args), xid, size[0], size[1],
            )
            self._launch_client(path, args)
        except Exception as exc:  # noqa: BLE001
            self._on_error_text(str(exc))
            return

    def _launch_client(self, path: str, args: list[str], direct_argv: list[str] | None = None) -> None:
        """Wire up and start the RDP client process.

        Default delivery is FreeRDP's native ``/args-from:file:<f>``: the full
        argument list (including ``/p:<secret>``) is written to a 0600 file so
        nothing sensitive appears in the process list. Only an explicit
        ``rdp_pass_on_cmdline`` opt-in puts the secret on argv directly.
        """
        import time as _time

        self._cleanup_args_file()
        self._proc = QProcess(self)
        self._proc_stderr = ""
        self._proc_stdout = ""
        self._proc_start_time = _time.monotonic()
        # capture client output for diagnostics (exit code 145 etc.)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._proc.readyReadStandardError.connect(self._on_proc_stderr)
        self._proc.readyReadStandardOutput.connect(self._on_proc_stdout)
        self._proc.started.connect(self._on_proc_started)
        self._proc.finished.connect(self._on_proc_finished)
        self._proc.errorOccurred.connect(self._on_proc_error)
        try:
            if direct_argv is not None or self.definition.rdp_pass_on_cmdline:
                # mstsc (.rdp file) or explicit ps-visible opt-in
                self._proc.start(path, direct_argv if direct_argv is not None else args)
            else:
                password = self._resolve_secret()
                full_args = list(args)
                if password:
                    full_args.append(f"/p:{password}")
                self._args_file = write_args_file(full_args)
                log.info("client launched via private args file (%s)", self._args_file.name)
                self._proc.start(path, ["/args-from:file:" + str(self._args_file)])
        except Exception as exc:  # noqa: BLE001
            self._on_error_text(str(exc))
            return

    def _cleanup_args_file(self) -> None:
        """Remove the private args file (secret) as soon as it's consumed."""
        f = self._args_file
        self._args_file = None
        if f is not None:
            try:
                f.unlink(missing_ok=True)
            except OSError:
                pass

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

    def _detected_size(self) -> tuple[int, int]:
        """Size of the embedded surface (the tab's display area).

        The remote desktop is launched at this resolution so the whole screen
        fits the tab.  Falls back to the session's saved resolution while the
        widget is not laid out yet (tiny/unmapped), and clamps to the range
        Windows/FreeRDP accept.
        """
        w, h = self._surface.width(), self._surface.height()
        if w < _MIN_MAPPED_W or h < _MIN_MAPPED_H:
            w, h = self.definition.rdp_width, self.definition.rdp_height
        return (
            min(max(w, _MIN_RDP_W), _MAX_RDP_W),
            min(max(h, _MIN_RDP_H), _MAX_RDP_H),
        )

    def _on_proc_stderr(self) -> None:
        if self._proc is None:
            return
        try:
            data = bytes(self._proc.readAllStandardError()).decode(errors="ignore")
            self._proc_stderr += data
            # keep buffer bounded
            if len(self._proc_stderr) > 8000:
                self._proc_stderr = self._proc_stderr[-8000:]
        except Exception:
            pass

    def _on_proc_stdout(self) -> None:
        if self._proc is None:
            return
        try:
            data = bytes(self._proc.readAllStandardOutput()).decode(errors="ignore")
            self._proc_stdout += data
            if len(self._proc_stdout) > 8000:
                self._proc_stdout = self._proc_stdout[-8000:]
        except Exception:
            pass

    def _on_proc_started(self) -> None:
        # Give the client a moment to parse /args-from, then shred the file.
        QTimer.singleShot(4000, self._cleanup_args_file)
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
        # drain any remaining output; shred the args file if still around
        self._on_proc_stderr()
        self._on_proc_stdout()
        self._cleanup_args_file()
        code = self._proc.exitCode() if self._proc else 0
        status = self._proc.exitStatus() if self._proc else QProcess.ExitStatus.NormalExit
        # QProcess reports crash separately
        import time as _time

        elapsed = _time.monotonic() - self._proc_start_time if self._proc_start_time else 999
        resized = self._resized_restart
        self._resized_restart = False
        self._btn_connect.setEnabled(True)
        self._btn_stop.setEnabled(False)
        # build diagnostic tail (first error line or last 500 chars)
        diag = (self._proc_stderr or self._proc_stdout).strip()
        # pick most relevant line
        diag_line = ""
        if diag:
            for line in reversed(diag.splitlines()):
                low = line.lower()
                if "error" in low or "fail" in low or "errno" in low or "could not" in low or "unable" in low:
                    diag_line = line.strip()[:300]
                    break
            if not diag_line:
                # fallback to last non-empty line
                for line in reversed(diag.splitlines()):
                    if line.strip():
                        diag_line = line.strip()[:300]
                        break
        if resized:
            reason = "refitting to new window size"
        else:
            # map known FreeRDP quirks
            if status == QProcess.ExitStatus.CrashExit:
                reason = f"RDP client crashed (code {code})"
                if diag_line:
                    reason += f": {diag_line}"
            elif code == 0 and diag and "error" in diag.lower():
                reason = f"RDP failed: {diag_line or diag[:300]}"
            elif code == 145:
                # 145 is a generic FreeRDP early-exit (bad args, missing X display, bad parent-window)
                reason = "RDP client exited (code 145)"
                if diag_line:
                    reason += f": {diag_line}"
                else:
                    reason += " — FreeRDP could not start (often: invalid /parent-window or no X display, or bad /size). Try Settings → Connection → RDP display = External, or run `xfreerdp /help` to check args."
                log.warning("freerdp 145 failure: args may be invalid; stderr=%r stdout=%r", self._proc_stderr[:2000], self._proc_stdout[:500])
                # auto-fallback from embedded → external on 145 if it happened quickly
                if self._mode == "embedded" and elapsed < 3.0:
                    log.warning("embedded RDP failed quickly (%.1fs) with 145 — falling back to external window", elapsed)
                    self._fall_back_to_external("embedded client exited 145 (likely bad parent-window/X display)")
                    return
            elif code != 0:
                reason = f"RDP client exited (code {code})"
                if diag_line:
                    reason += f": {diag_line}"
                # rapid failure = likely config error, don't spam reconnect
                if elapsed < 2.0 and diag_line:
                    reason += " — check host/port and FreeRDP args"
            else:
                reason = f"RDP client exited (code {code})"
                if diag_line and "error" in diag_line.lower():
                    reason += f": {diag_line}"
        # log full diagnostics
        if diag:
            log.warning("RDP client finished code=%s status=%s elapsed=%.1fs stderr=%r", code, status, elapsed, self._proc_stderr[-2000:])
        # rapid non-zero exit should NOT auto-reconnect (would loop); treat as FAILED
        rapid_failure = (not resized) and code != 0 and elapsed < 2.0 and self._mode == "embedded" and code == 145
        should_reconnect = (
            self._state in (SessionState.CONNECTED, SessionState.RECONNECTING)
            and self.definition.auto_reconnect
            and not rapid_failure
            and not (code != 0 and elapsed < 1.5)  # don't loop on instant config errors
        )
        if should_reconnect:
            self.set_state(SessionState.RECONNECTING)
            if self._mode == "embedded":
                self._set_emb_hint(reason + " — reconnecting…")
            else:
                self._status.setText(reason + " — auto-reconnecting…")
            self.reconnectScheduled.emit(1, 1.0 if resized else 3.0)
            delay = 500 if resized else 3000
            QTimer.singleShot(delay, lambda: self.start() if self._state == SessionState.RECONNECTING else None)
        else:
            if code != 0 and not resized:
                self.set_state(SessionState.FAILED)
                self.statusInfo.emit({"error": reason})
            if self._mode == "embedded":
                self._set_emb_hint(reason)
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
        self._cleanup_args_file()
        self.set_state(SessionState.FAILED)
        self._status.setText(message)
        if self._mode == "embedded":
            self._set_emb_hint(message)
        self._btn_connect.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self.statusInfo.emit({"error": message})

    def stop(self, reason: str = "closed by user") -> None:
        self._cleanup_args_file()
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
        if self._probe_thread is not None and self._probe_thread.is_alive():
            return  # a probe is already running
        self._probe_label.setText(f"Probing {host}:{port}…")
        self._btn_probe.setEnabled(False)

        def work() -> None:
            # Runs on a plain daemon thread: probe() does blocking socket I/O
            # for up to 5 s, which used to freeze the entire GUI because
            # QTimer.singleShot(0, ...) still executes on the GUI thread.
            try:
                result = probe(host, port, timeout=5.0)
            except RdpProbeError as exc:
                self._sigProbeResult.emit(f"✗ {exc}")
                return
            except Exception as exc:  # noqa: BLE001 - never kill the thread
                self._sigProbeResult.emit(f"✗ {exc}")
                return
            if result.failure_code is not None:
                self._sigProbeResult.emit(
                    f"RDP server answered; refused requested security: {result.failure_name}"
                )
            else:
                self._sigProbeResult.emit(
                    f"✓ RDP server OK — security: {result.selected_protocol_name}, "
                    f"{result.latency_ms:.0f} ms"
                )

        self._probe_thread = threading.Thread(
            target=work, daemon=True, name=f"rdp-probe-{host}"
        )
        self._probe_thread.start()

    def _on_probe_result(self, text: str) -> None:
        """Queued back onto the GUI thread by ``_sigProbeResult``."""
        self._probe_label.setText(text)
        self._btn_probe.setEnabled(True)

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
        # Only claim the target when the port explicitly says RDP — quick
        # connect walks plugins in order, and a bare ``user@host`` must fall
        # through to SSH (the documented "port 3389 ⇒ RDP" behaviour).
        if port != 3389:
            return None
        s = Session(protocol="rdp", host=host, port=3389, username=user or "")
        s.name = s.target()
        return s
