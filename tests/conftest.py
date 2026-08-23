"""Shared test fixtures: isolated KB_REMOTE_HOME, offscreen Qt, local sshd."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def home(tmp_path, monkeypatch) -> Path:
    """Isolated state directory for every test."""
    monkeypatch.setenv("KB_REMOTE_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture(scope="session")
def qtapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def sshd():
    """A real local sshd on 127.0.0.1:2201 (key + password auth, sftp).

    Skipped when the sandbox machine cannot run one.
    """
    sshd_bin = shutil.which("sshd") or "/usr/sbin/sshd"
    if not Path(sshd_bin).exists():
        pytest.skip("no sshd available")
    base = Path(tempfile.mkdtemp(prefix="rdpstudio-sshtest-"))
    host_key = base / "host_ed25519"
    client_key = base / "client_ed25519"
    authorized = base / "authorized_keys"
    for key_path, key_type in ((host_key, "ed25519"), (client_key, "ed25519")):
        subprocess.run(
            ["ssh-keygen", "-q", "-t", key_type, "-N", "", "-f", str(key_path)], check=True
        )
    authorized.write_text(client_key.with_suffix(".pub").read_text())

    # pick a free port
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    # ensure the test user's login works for key auth: point AuthorizedKeysFile
    # at our file so no ~/.ssh modification is needed.
    cfg = base / "sshd_config"
    cfg.write_text(
        f"Port {port}\n"
        "ListenAddress 127.0.0.1\n"
        f"HostKey {host_key}\n"
        "PidFile " + str(base / "sshd.pid") + "\n"
        "PasswordAuthentication no\n"
        "PubkeyAuthentication yes\n"
        f"AuthorizedKeysFile {authorized}\n"
        "StrictModes no\n"
        "PermitRootLogin no\n"
        "UsePAM no\n"
        "Subsystem sftp internal-sftp\n"
        "LogLevel ERROR\n"
    )
    run_dir = Path("/run/sshd")
    run_dir.mkdir(exist_ok=True)
    proc = subprocess.Popen(
        [sshd_bin, "-f", str(cfg), "-E", str(base / "sshd.log"), "-D"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # wait for the port
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.4):
                break
        except OSError:
            if proc.poll() is not None:
                pytest.skip("sshd died during startup")
            time.sleep(0.1)
    else:
        proc.terminate()
        pytest.skip("sshd did not come up")

    import pwd

    user = pwd.getpwuid(os.getuid()).pw_name
    yield {"host": "127.0.0.1", "port": port, "user": user, "key": str(client_key)}

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    shutil.rmtree(base, ignore_errors=True)
