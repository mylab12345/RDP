"""Local shell session (a MobaXterm-style local terminal tab).

- POSIX: real PTY via :mod:`pty` — colors, resize, vim/top all work.
- Windows: uses ConPTY through ``pywinpty`` when installed (optional extra);
  otherwise falls back to ``cmd.exe``/PowerShell via QProcess (no PTY).
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import struct
import subprocess
import threading

from PySide6.QtCore import QProcess, Signal
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
        raw = str(self.definition.options.get("command", "") or "").strip()
        if raw:
            try:
                cmd = shlex.split(raw)
            except ValueError as exc:  # unbalanced quotes
                self._fail(f"invalid command {raw!r}: {exc}")
                return
            if not cmd:
                cmd = None
        try:
            if POSIX:
                self._start_pty(cmd)
            else:
                self._start_windows(cmd)
        except (OSError, ValueError) as exc:
            # A missing shell used to leave the tab claiming "connected"
            # with a dead, silent terminal.
            self._fail(f"cannot start shell: {exc}")
            return
        self.set_state(SessionState.CONNECTED)
        self.titleChanged.emit(self.definition.display_name() or "Terminal")
        self.ctx.publish("session/connected", {"protocol": "local"})

    def _fail(self, message: str) -> None:
        log.error("local shell failed: %s", message)
        self.set_state(SessionState.FAILED)
        self.statusInfo.emit({"error": message, "status_text": message})
        self.term.feed(b"\r\n\x1b[31m" + message.encode("utf-8", "replace") + b"\x1b[0m\r\n")
        self.emit_finished_once(message)

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
        except OSError:
            # Popen failed (no such shell, EPERM, ...): release *both* ends,
            # otherwise every failed launch leaked a PTY pair.
            os.close(slave)
            os.close(master)
            raise
        finally:
            if self._proc is not None:
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
    def _close_master(self) -> None:
        """Close the PTY master exactly once.

        The reader thread blocks in ``os.read(master)``. Closing the fd while
        it is in flight lets the kernel hand the same number to an unrelated
        open() — the reader would then stream a random file into the terminal.
        So we only close after the reader has observed EOF (or been joined).
        """
        fd, self._master = self._master, None
        if fd is None:
            return
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        try:
            os.close(fd)
        except OSError:
            pass

    def _reap(self) -> None:
        """Terminate the child's whole process group and release the fd."""
        proc, self._proc = self._proc, None
        if proc is not None and proc.poll() is None:
            # start_new_session=True put the shell in its own process group;
            # signal the group so pipelines/children die with it instead of
            # being reparented to init.
            try:
                os.killpg(proc.pid, signal.SIGHUP)
            except (OSError, AttributeError, ProcessLookupError):
                try:
                    proc.terminate()
                except OSError:
                    pass
            try:
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (OSError, AttributeError, ProcessLookupError):
                    proc.kill()
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:  # pragma: no cover - zombie
                    pass
        self._close_master()

    def _finished(self, reason: str) -> None:
        if self._state == SessionState.CLOSED:
            return
        self._reap()
        self.emit_finished_once(reason)

    def stop(self, reason: str = "closed by user") -> None:
        self._reap()
        winpty, self._winpty = self._winpty, None
        if winpty is not None:
            try:
                winpty.terminate(force=True)
            except Exception:  # noqa: BLE001
                pass
        qproc, self._qproc = self._qproc, None
        if qproc is not None:
            qproc.kill()
            qproc.waitForFinished(1000)
        self.emit_finished_once(reason)

    def request_reconnect(self) -> None:
        """Restart the shell in the same tab (the Reconnect button)."""
        if self._state != SessionState.CLOSED:
            return
        # Clear per-run state so start() builds a fresh PTY instead of
        # reusing the dead one.
        self._reap()
        self._winpty = None
        self._qproc = None
        self._finished_emitted = False
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
