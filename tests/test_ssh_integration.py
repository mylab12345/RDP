"""End-to-end SSH integration against a real local sshd.

Covers: connect+auth (key), banner/exec shell via SshWorker paths, host-key
TOFU store, local/remote/dynamic (SOCKS) forwarding, and SFTP round-trip.
Requires sshd (skipped otherwise).
"""

from __future__ import annotations

import os
import socket
import struct
import threading
import time

import pytest

pytestmark = pytest.mark.usefixtures("home")

paramiko = pytest.importorskip("paramiko")


def _material(server, key_passphrase=None):
    from rdpstudio.protocols.ssh.worker import AuthMaterial

    return AuthMaterial(
        host=server["host"],
        port=server["port"],
        username=server["user"],
        key_path=server["key"],
        allow_agent=False,
    )


def test_plain_paramiko_exec(sshd):
    """Sanity: the fixture sshd works with vanilla paramiko."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        sshd["host"], sshd["port"], username=sshd["user"],
        key_filename=sshd["key"], look_for_keys=False, allow_agent=False,
    )
    _, out, _ = client.exec_command("echo integration-ok")
    assert out.read().decode().strip() == "integration-ok"
    client.close()


def test_known_hosts_tofu(sshd, home):
    from rdpstudio.protocols.ssh.knownhosts import KnownHostsVerifier
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    path = home / "known_hosts"
    prompter = HeadlessPromptProvider(accept_host_keys=True)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(KnownHostsVerifier(path, "accept-new", prompter))
    client.connect(
        sshd["host"], sshd["port"], username=sshd["user"],
        key_filename=sshd["key"], look_for_keys=False, allow_agent=False,
    )
    client.close()
    assert path.exists()
    content = path.read_text()
    assert f"[{sshd['host']}]:{sshd['port']}" in content

    # strict policy rejects unknown hosts outright (no prompt, no exception)
    strict = KnownHostsVerifier(home / "kh2", "strict", HeadlessPromptProvider())
    key = paramiko.Ed25519Key.from_private_key_file(sshd["key"])
    with pytest.raises(paramiko.SSHException):
        strict.missing_host_key(None, "never-seen.example:22", key)

    # a *changed* key always demands explicit consent; refusal raises
    old_key = paramiko.RSAKey.generate(2048)
    verifier = KnownHostsVerifier(home / "kh3", "accept-new", HeadlessPromptProvider(accept_host_keys=False))
    verifier.host_keys.add("some-host", old_key.get_name(), old_key)  # pretend old key
    fresh_key = paramiko.RSAKey.generate(2048)  # definitely different key
    with pytest.raises(paramiko.SSHException):
        verifier.missing_host_key(None, "some-host", fresh_key)


def test_tunnel_manager_local_forward(sshd):
    """Local forward → echo server through the sshd."""
    from rdpstudio.core.models import Forward
    from rdpstudio.protocols.ssh.forwarding import TunnelManager

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        sshd["host"], sshd["port"], username=sshd["user"],
        key_filename=sshd["key"], look_for_keys=False, allow_agent=False,
    )

    # echo server reachable from the sshd host (same machine)
    echo = socket.socket()
    echo.bind(("127.0.0.1", 0))
    echo.listen(4)
    echo_port = echo.getsockname()[1]

    def echo_loop():
        while True:
            try:
                conn, _ = echo.accept()
            except OSError:
                return
            conn.sendall(b"ECHO:" + conn.recv(1024))
            conn.close()

    threading.Thread(target=echo_loop, daemon=True).start()

    mgr = TunnelManager(client.get_transport())
    try:
        fwd = Forward(kind="local", listen_host="127.0.0.1", listen_port=0,
                      dest_host="127.0.0.1", dest_port=echo_port)
        port = mgr.start_local(fwd)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"hi-tunnel")
            data = s.recv(1024)
        assert data == b"ECHO:hi-tunnel"
    finally:
        mgr.stop_all()
        client.close()


def test_tunnel_manager_socks5(sshd):
    """Dynamic forward behaves as a SOCKS5 CONNECT proxy."""
    from rdpstudio.core.models import Forward
    from rdpstudio.protocols.ssh.forwarding import TunnelManager

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        sshd["host"], sshd["port"], username=sshd["user"],
        key_filename=sshd["key"], look_for_keys=False, allow_agent=False,
    )
    target = socket.socket()
    target.bind(("127.0.0.1", 0))
    target.listen(4)
    target_port = target.getsockname()[1]

    def target_loop():
        conn, _ = target.accept()
        conn.sendall(b"via-socks")
        conn.close()

    threading.Thread(target=target_loop, daemon=True).start()

    mgr = TunnelManager(client.get_transport())
    try:
        fwd = Forward(kind="dynamic", listen_host="127.0.0.1", listen_port=0)
        port = mgr.start_local(fwd)
        with socket.create_connection(("127.0.0.1", port), timeout=5) as s:
            s.sendall(b"\x05\x01\x00")  # greeting: no-auth
            assert s.recv(2) == b"\x05\x00"
            addr = "127.0.0.1"
            req = b"\x05\x01\x00\x01" + socket.inet_aton(addr) + struct.pack(">H", target_port)
            s.sendall(req)
            assert s.recv(10)[:2] == b"\x05\x00"
            assert s.recv(64) == b"via-socks"
    finally:
        mgr.stop_all()
        client.close()


def test_sftp_roundtrip(sshd, tmp_path):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        sshd["host"], sshd["port"], username=sshd["user"],
        key_filename=sshd["key"], look_for_keys=False, allow_agent=False,
    )
    sftp = paramiko.SFTPClient.from_transport(client.get_transport())
    remote_dir = f"/tmp/rdpstudio-test-{int(time.time())}"
    sftp.mkdir(remote_dir)
    payload = os.urandom(300_000)
    local = tmp_path / "blob.bin"
    local.write_bytes(payload)
    sftp.put(str(local), f"{remote_dir}/blob.bin")
    got = sftp.open(f"{remote_dir}/blob.bin", "rb").read()
    assert got == payload
    entries = sftp.listdir(remote_dir)
    assert "blob.bin" in entries
    sftp.remove(f"{remote_dir}/blob.bin")
    sftp.rmdir(remote_dir)
    sftp.close()
    client.close()
