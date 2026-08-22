"""Worker-level integration: full SshWorker shell through Qt signals.

Runs the real worker on a QThread against the local sshd — exactly the path
the GUI uses.
"""

from __future__ import annotations

import sys
import time

import pytest

pytestmark = pytest.mark.usefixtures("home")


@pytest.fixture()
def ctx(sshd, home, qtapp):
    """A SessionContext with a headless prompter wired for the test sshd."""
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    settings = Settings()
    settings.host_key_policy = "accept-new"
    return SessionContext(
        settings=settings,
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(accept_host_keys=True),
    )


def _wait_signal(obj, signal_name, timeout=10.0):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    result = {"args": None, "timed_out": True}

    def capture(*args):
        result["args"] = args
        result["timed_out"] = False
        loop.quit()

    signal = getattr(obj, signal_name)
    signal.connect(capture)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(int(timeout * 1000))
    loop.exec()
    signal.disconnect(capture)
    return result["args"], result["timed_out"]


def test_worker_shell_echo(sshd, ctx, qtapp):
    pytest.importorskip("paramiko")
    from PySide6.QtCore import QThread

    from rdpstudio.core import paths
    from rdpstudio.protocols.ssh.worker import AuthMaterial, SshWorker

    material = AuthMaterial(
        host=sshd["host"], port=sshd["port"], username=sshd["user"],
        key_path=sshd["key"], allow_agent=False,
    )
    worker = SshWorker(
        host=sshd["host"], port=sshd["port"], material=material,
        known_hosts_path=paths.known_hosts_file(),
        host_key_policy="accept-new", prompter=ctx.prompter,
        term_size=(100, 30),
    )
    collected = bytearray()
    worker.output.connect(lambda data: collected.extend(data))

    thread = QThread()
    worker.moveToThread(thread)
    # QueuedConnection — the connect+pump must run on the worker thread
    thread.started.connect(worker.connect_and_shell)
    thread.start()

    connected, timed_out = _wait_signal(worker, "connected")
    assert not timed_out and connected, "worker failed to connect"
    assert connected[0]["host"].startswith("127.0.0.1")

    worker.write_input(b"echo WORKER-OK-$((40+2))\n")
    deadline = time.time() + 8
    while time.time() < deadline and b"WORKER-OK-42" not in bytes(collected):
        qtapp.processEvents()
        time.sleep(0.05)
    assert b"WORKER-OK-42" in bytes(collected), f"output: {bytes(collected)!r}"

    worker.write_input(b"exit\n")
    _wait_signal(worker, "disconnected", timeout=8)
    thread.quit()
    thread.wait(3000)
    worker._cleanup()


def test_local_shell_controller(qtapp, home):
    pytest.importorskip("PySide6")
    if sys.platform == "win32":
        pytest.skip("posix pty test")

    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.protocols.local.session import LocalShellController
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx = SessionContext(
        settings=Settings(), store=SessionStore(home / "s.json"),
        vault=None, bus=EventBus(), prompter=HeadlessPromptProvider(),
    )
    defn = Session(protocol=PROTOCOL_LOCAL)
    defn.options["command"] = "/bin/sh"
    controller = LocalShellController(defn, ctx)
    controller.term.core.resize(80, 24)
    controller.start()
    controller.term.send_text("echo LOCAL-$((6*7))\n")

    deadline = time.time() + 8
    body = ""
    while time.time() < deadline:
        qtapp.processEvents()
        body = "\n".join(
            controller.term.core.line_at(i)
            for i in range(controller.term.core.total_lines())
        )
        if "LOCAL-42" in body:
            break
        time.sleep(0.05)
    controller.term.send_text("exit\n")
    time.sleep(0.3)
    qtapp.processEvents()
    controller.stop("done")
    qtapp.processEvents()
    assert "LOCAL-42" in body
