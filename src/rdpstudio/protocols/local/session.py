"""Local shell session (a MobaXterm-style local terminal tab).

- POSIX: real PTY via :mod:`pty` — colors, resize, vim/top all work.
- Windows: uses ConPTY through ``pywinpty`` when installed (optional extra);
  otherwise falls back to ``cmd.exe``/PowerShell via QProcess (no PTY).
"""

from __future__ import annotations

import os
import shlex
import shutil
import struct
import subprocess
import threading

from PySide6.QtCore import QProcess, QTimer, Signal
from PySide6.QtWidgets import QWidget

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

log = get_logger("local.session")

try:  # POSIX terminal helpers
    import fcntl
    import termios

    POSIX = True
except ImportError:  # pragma: no cover - Windows
    POSIX = False


def _default_shell() -> list[str]:
    if POSIX:
        for candidate in (os.environ.get("SHELL"), "/bin/bash", "/bin/sh"):
            if candidate and shutil.which(candidate):
                return [candidate, "-i"]
        return ["/bin/sh"]
    if shutil.which("pwsh"):
        return ["pwsh", "-NoLogo"]
    if shutil.which("powershell"):
        return ["powershell", "-NoLogo"]
    return ["cmd.exe", "/Q"]


class LocalShellController(SessionController):
    """Tab running an interactive local shell."""

    # reader thread → GUI thread (auto → queued; widgets must not be touched
    # from the reader thread)
    _sigFeed = Signal(bytes)
    _sigClosed = Signal(str)

    def __init__(self, definition: Session, ctx: SessionContext, parent=None) -> None:
        super().__init__(definition, ctx, parent)
        from ...ui.terminal import TerminalView

        self.term = TerminalView(ctx.settings)
        self.term.dataWritten.connect(self._on_input)
        self.term.sizeChanged.connect(self._on_resize)
        self._sigFeed.connect(self.term.feed)
        self._sigClosed.connect(self._finished)
        self._proc: subprocess.Popen | None = None
        self._qproc: QProcess | None = None
        self._master: int | None = None
        self._thread: threading.Thread | None = None
        self._winpty = None
        self.set_state(SessionState.CLOSED)

    def capabilities(self) -> Capabilities:
        return capability_set(shell=True)

    def widget(self) -> QWidget:
        return self.term

    # ------------------------------------------------------------------
    def start(self) -> None:
        self.set_state(SessionState.CONNECTING)
        cmd = None
        raw = self.definition.options.get("command", "")
        if raw:
            cmd = shlex.split(raw)
        if POSIX:
            self._start_pty(cmd)
        else:
            self._start_windows(cmd)
        self.set_state(SessionState.CONNECTED)
        self.titleChanged.emit("Local shell")
        self.ctx.publish("session/connected", {"protocol": "local"})

    # -- POSIX PTY --------------------------------------------------------
    def _start_pty(self, cmd: list[str] | None) -> None:
        import pty as pty_mod

        cmd = cmd or _default_shell()
        master, slave = pty_mod.openpty()
        self._set_winsize(master, *self.term.cols_rows())
        env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor")
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                start_new_session=True,
                close_fds=True,
                env=env,
            )
        finally:
            os.close(slave)
        self._master = master
        self._thread = threading.Thread(target=self._read_loop, args=(master,), daemon=True)
        self._thread.start()
        if self.definition.startup_command:
            self._on_input(self.definition.startup_command.encode() + b"\n")

    def _read_loop(self, fd: int) -> None:
        try:
            while True:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                self._sigFeed.emit(data)  # queued → GUI thread
        finally:
            self._sigClosed.emit("shell exited")

    def _set_winsize(self, fd: int, cols: int, rows: int) -> None:
        if not POSIX:
            return
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def _on_resize(self, cols: int, rows: int) -> None:
        if self._master is not None:
            try:
                self._set_winsize(self._master, cols, rows)
            except OSError:
                pass
        if self._winpty is not None:
            try:
                self._winpty.set_size(cols, rows)
            except Exception:  # noqa: BLE001
                pass

    def _on_input(self, data: bytes) -> None:
        if self._master is not None:
            try:
                os.write(self._master, data)
            except OSError:
                pass
        elif self._winpty is not None:
            try:
                self._winpty.write(data.decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
        elif self._qproc is not None:
            self._qproc.write(bytes(data))

    # -- Windows -----------------------------------------------------------
    def _start_windows(self, cmd: list[str] | None) -> None:
        try:
            from winpty import PtyProcess  # type: ignore

            cols, rows = self.term.cols_rows()
            self._winpty = PtyProcess.spawn(
                cmd or _default_shell(),
                dimensions=(rows, cols),
                env=dict(os.environ, TERM="xterm-256color"),
            )
            threading.Thread(target=self._winpty_read, daemon=True).start()
            return
        except ImportError:
            log.info("pywinpty not installed; falling back to cmd via QProcess")

        self._qproc = QProcess(self)
        self._qproc.readyReadStandardOutput.connect(self._qout)
        self._qproc.readyReadStandardError.connect(self._qout)
        self._qproc.finished.connect(
            lambda code, status: self._finished(f"shell exited ({code})")
        )
        argv = cmd or _default_shell()
        self._qproc.start(argv[0], argv[1:])

    def _winpty_read(self) -> None:
        p = self._winpty
        assert p is not None
        try:
            while True:
                data = p.read(65536, timeout=0.2)
                if data:
                    self._sigFeed.emit(data.encode("utf-8", "replace"))
                if p.exited:
                    break
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._sigClosed.emit("shell exited")

    def _qout(self) -> None:
        assert self._qproc is not None
        data = bytes(self._qproc.readAllStandardOutput()) + bytes(
            self._qproc.readAllStandardError()
        )
        if data:
            self.term.feed(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    # -- teardown ------------------------------------------------------------
    def _finished(self, reason: str) -> None:
        if self._state == SessionState.CLOSED:
            return
        self._master = None
        self.emit_finished_once(reason)

    def stop(self, reason: str = "closed by user") -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                QTimer.singleShot(500, self._proc.kill)
            except Exception:  # noqa: BLE001
                pass
        if self._winpty is not None:
            try:
                self._winpty.terminate(force=True)
            except Exception:  # noqa: BLE001
                pass
        if self._qproc is not None:
            self._qproc.kill()
        if self._master is not None:
            try:
                os.close(self._master)
            except OSError:
                pass
        self.emit_finished_once(reason)

    def request_reconnect(self) -> None:
        if self._state == SessionState.CLOSED:
            self.start()


class LocalShellPlugin(ProtocolPlugin):
    id = "local"
    title = "Local shell"
    description = "Interactive local terminal (bash/PowerShell) in a tab."
    default_port = 0
    icon_name = "console"
    can_edit = True
    tags = ["local", "shell"]

    def create_session(self, definition: Session, ctx: SessionContext) -> SessionController:
        return LocalShellController(definition, ctx)
