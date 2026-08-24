"""Regression tests for bug fixes (kept separate so each fix is traceable)."""

from __future__ import annotations

import socket
import struct

import pytest

from rdpstudio.core.models import Forward, Session
from rdpstudio.core.store import SessionStore


# --- store: import must never overwrite existing sessions --------------------
def test_import_sessions_id_collision_does_not_overwrite(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    original = Session(name="db", host="db-original")
    store.upsert(original)

    # An import carrying the *same* id must not clobber the saved session.
    intruder = Session(name="db-intruder", host="db-intruder-host")
    intruder.id = original.id
    added = store.import_sessions([intruder])

    assert added == 1
    assert store.get(original.id) is not None
    assert store.get(original.id).host == "db-original"
    hosts = {s.host for s in store.sessions()}
    assert "db-intruder-host" in hosts


def test_rename_group_merging_into_existing_group(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    store.ensure_group("A")
    store.ensure_group("B")
    s = Session(name="x", group="A", host="h")
    store.upsert(s)

    store.rename_group("A", "B")
    assert store.groups().count("B") == 1
    assert "A" not in store.groups()
    assert store.get(s.id).group == "B"


# --- forwarding: remote forward port comes from bound (address, port) --------
def test_remote_forward_uses_bound_port(tmp_path):
    from rdpstudio.protocols.ssh.forwarding import TunnelManager

    class FakeTransport:
        def request_port_forward(self, address, port, handler=None):
            # paramiko returns (address, port) — the server-assigned port is
            # the second element.
            return ("0.0.0.0", 42424)

        def cancel_port_forward(self, address, port):
            pass

    mgr = TunnelManager(FakeTransport())
    fwd = Forward(kind="remote", listen_port=0, dest_host="127.0.0.1", dest_port=80)
    port = mgr.start(fwd)
    assert port == 42424
    assert 42424 in mgr._remotes


# --- knownhosts: known_fingerprint must not raise ----------------------------
def test_known_fingerprint(tmp_path):
    import paramiko

    from rdpstudio.protocols.ssh.knownhosts import KnownHostsVerifier

    path = tmp_path / "known_hosts"
    verifier = KnownHostsVerifier(path, "accept-new", prompter=None)
    key = paramiko.RSAKey.generate(1024)
    verifier.host_keys.add("example.com", key.get_name(), key)

    fp = verifier.known_fingerprint("example.com")
    assert fp is not None and fp.startswith("SHA256:")
    assert verifier.known_fingerprint("nowhere.example") is None


# --- rdpfile: keys must be unique; file carries a UTF-16 BOM -----------------
def test_rdp_file_has_no_duplicate_keys(tmp_path):
    from rdpstudio.protocols.rdp.rdpfile import build_rdp_text, write_rdp_file

    s = Session(protocol="rdp", host="win.lab", username="admin")
    text = build_rdp_text(s)
    keys = [line.split(":", 1)[0] for line in text.splitlines() if line]
    assert len(keys) == len(set(keys)), f"duplicate keys: {[k for k in keys if keys.count(k) > 1]}"
    assert keys.count("full address") == 1

    path = write_rdp_file(s, tmp_path)
    raw = path.read_bytes()
    assert raw[:2] == b"\xff\xfe"  # UTF-16 (LE) BOM for mstsc


# --- negotiate: a 10-byte classic Connection Confirm is valid ----------------
def test_parse_classic_connection_confirm_without_negotiation():
    from rdpstudio.protocols.rdp.negotiate import PROTOCOL_RDP, parse_connection_confirm

    # TPKT(4) + LI/DST/SRC/class(6) = 10 bytes, no negotiation blob.
    x224 = bytes([5]) + struct.pack(">HHB", 0, 0, 0)
    cc = struct.pack(">BBH", 3, 0, len(x224) + 4) + x224
    result = parse_connection_confirm(cc)
    assert result.ok
    assert result.selected_protocol == PROTOCOL_RDP


def test_probe_reads_partial_tpkt_response():
    """The response may arrive in several segments; probe() must reassemble."""
    from rdpstudio.protocols.rdp.negotiate import probe

    neg = struct.pack("<BBHI", 0x02, 0x00, 8, 0x01)  # selects TLS
    x224 = bytes([5 + len(neg)]) + struct.pack(">HHB", 0, 0, 0) + neg
    response = struct.pack(">BBH", 3, 0, len(x224) + 4) + x224

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    import threading

    def run():
        conn, _ = srv.accept()
        conn.recv(512)
        # send byte-by-byte to force partial reads
        for i in range(len(response)):
            conn.sendall(response[i : i + 1])
        conn.close()
        srv.close()

    threading.Thread(target=run, daemon=True).start()
    result = probe("127.0.0.1", port, timeout=5.0)
    assert result.ok and result.selected_protocol == 0x01


# --- quick connect: bare user@host is SSH; only :3389 is RDP ------------------
def test_quick_connect_default_protocol():
    from rdpstudio.core.plugin import registry

    # The app walks registry().editable() in order; RDP used to claim every
    # target, turning "user@host" into an RDP session.
    for plugin in registry().editable():
        defn = plugin.quick_connect_target("ops@10.1.2.3")
        if defn is not None:
            break
    assert defn is not None and defn.protocol == "ssh" and defn.port == 22

    for plugin in registry().editable():
        defn = plugin.quick_connect_target("win.host:3389")
        if defn is not None:
            break
    assert defn is not None and defn.protocol == "rdp" and defn.port == 3389


def test_parse_ssh_target_ipv6():
    from rdpstudio.protocols.ssh.session import parse_ssh_target

    assert parse_ssh_target("[::1]:2222") == ("", "::1", 2222)
    assert parse_ssh_target("root@[2001:db8::5]") == ("root", "2001:db8::5", 0)
    assert parse_ssh_target("::1") == ("", "::1", 0)
    assert parse_ssh_target("user@host:22") == ("user", "host", 22)


# --- session dialog: per-protocol auth widgets actually save ------------------
def test_session_dialog_saves_ssh_auth(qtapp, home):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider
    from rdpstudio.ui.session_dialog import SessionDialog

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    dlg = SessionDialog(ctx, Session(protocol="ssh", host="h"), None)
    dlg.protocol.setCurrentIndex(dlg.protocol.findData("ssh"))
    ssh_auth = dlg._current_auth_ui("ssh")
    ssh_auth["auth"].setCurrentIndex(ssh_auth["auth"].findData("key"))
    ssh_auth["key_path"].setText("/tmp/id_ed25519_test")
    dlg._on_save()

    loaded = ctx.store.get(dlg.session.id)
    assert loaded is not None
    assert loaded.auth == "key"
    assert loaded.key_path == "/tmp/id_ed25519_test"


def test_session_dialog_saves_local_session(qtapp, home):
    """The local page has no auth widgets — saving must not need them."""
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider
    from rdpstudio.ui.session_dialog import SessionDialog

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    dlg = SessionDialog(ctx, Session(protocol="local"), None)
    dlg.protocol.setCurrentIndex(dlg.protocol.findData("local"))
    dlg.local_cmd.setText("htop")
    dlg._on_save()

    loaded = ctx.store.get(dlg.session.id)
    assert loaded is not None
    assert loaded.protocol == "local"
    assert loaded.options.get("command") == "htop"


# --- snippets execute on shell-capable controllers ----------------------------
def test_snippet_runs_on_shell_controller(qtapp, home, monkeypatch):
    from rdpstudio.protocols.base_caps import capability_set
    from rdpstudio.tools.snippets import Snippet
    from rdpstudio.ui.snippets_panel import SnippetsPanel

    written: list[bytes] = []

    class StubController:
        definition = Session(name="s", host="10.0.0.1", username="root", port=2222)

        def capabilities(self):
            return capability_set(shell=True)

        def write(self, data: bytes) -> None:
            written.append(data)

    class StubMain:
        def current_controller(self):
            return StubController()

    from PySide6.QtWidgets import QWidget

    host = QWidget()  # keep a reference so the panel's parent stays alive
    panel = SnippetsPanel(StubMain(), parent=host)
    panel._execute_snippet(Snippet(name="Uptime", command="uptime"))
    assert written == [b"uptime\n"]


# --- SSH terminals ignore workbench theme colors ------------------------------
def test_ssh_terminal_keeps_native_console_palette(qtapp, home):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.protocols.ssh.session import SshSessionController
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    settings = Settings(theme="light", font_family="Courier New", font_size=14)
    ctx = SessionContext(
        settings=settings,
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    ctrl = SshSessionController(Session(name="s", host="h", username="u"), ctx)
    assert ctrl.term.native_colors is True
    pal = ctrl.term._build_palette()
    assert pal["bg"].name().lower() == "#000000"
    assert pal["fg"].name().lower() == "#aaaaaa"
    settings.theme = "forest"
    pal2 = ctrl.term._build_palette()
    assert pal2["bg"].name().lower() == "#000000"
    assert pal2["16"][1].name().lower() == "#aa0000"


# --- theme: palette() follows the applied theme --------------------------------
def test_palette_follows_applied_theme(qtapp):
    from rdpstudio.ui import theme

    theme.apply_theme(qtapp, "light")
    try:
        assert theme.palette()["bg"] == theme.PALETTE["light"]["bg"]
        assert theme.current_theme() == "light"
    finally:
        theme.apply_theme(qtapp, "dark")
    assert theme.palette()["bg"] == theme.PALETTE["dark"]["bg"]


# --- settings: garbage values must not crash ----------------------------------
def test_settings_from_dict_garbage_values():
    from rdpstudio.core.settings import Settings

    s = Settings.from_dict({"font_size": "big", "kdf_iterations": None, "scrollback_lines": -5})
    assert s.font_size == 10
    assert s.kdf_iterations >= 100_000
    assert s.scrollback_lines >= 200


# --- vault: create() refuses to overwrite; corrupt files raise CryptoError ----
def test_vault_create_refuses_overwrite(tmp_path):
    from rdpstudio.core.vault import CredentialVault, VaultBusyError

    path = tmp_path / "vault.bin"
    v1 = CredentialVault(path, kdf_iterations=60_000)
    v1.create("master1")

    v2 = CredentialVault(path, kdf_iterations=60_000)
    with pytest.raises(VaultBusyError):
        v2.create("master2")


def test_corrupt_vault_raises_crypto_error(tmp_path):
    from rdpstudio.core.crypto import CryptoError, Envelope

    with pytest.raises(CryptoError):
        Envelope.from_json("not json at all")
    with pytest.raises(CryptoError):
        Envelope.from_json('{"format": 1, "kdf": {"algo": "pbkdf2-sha256", "salt": "!!", "iterations": 1}, "aead": {"algo": "aes-256-gcm", "nonce": "!!", "ciphertext": "??"}}')


# --- ssh_config importer: tabs and Key=Value syntax ----------------------------
def test_ssh_config_parser_tab_and_equals():
    from rdpstudio.importers.ssh_config import parse_ssh_config

    text = "Host\tweb2\n\tHostName=10.0.0.12\n\tUser\tdeploy\n\tPort=2200\n"
    sessions = parse_ssh_config(text)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.name == "web2"
    assert s.host == "10.0.0.12"
    assert s.username == "deploy"
    assert s.port == 2200


# --- worker: disconnected emitted exactly once ---------------------------------
def test_worker_emits_disconnected_once():
    from rdpstudio.protocols.ssh.worker import AuthMaterial, SshWorker

    worker = SshWorker(
        host="h", port=22, material=AuthMaterial(),
        known_hosts_path=None, host_key_policy="accept-new", prompter=None,
    )
    seen: list[str] = []
    worker.disconnected.connect(seen.append)

    worker._emit_disconnected("first")
    worker._emit_disconnected("second")
    assert seen == ["first"]


# --- monitor engine: transport provider resolved lazily ------------------------
def test_ssh_transport_provider_follows_reconnect(home, qtapp):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.protocols.ssh.session import SshSessionController
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    ctrl = SshSessionController(Session(name="s", host="h", username="u"), ctx)
    provider = ctrl.transport_provider()

    class FakeTransport:
        pass

    class FakeWorker:
        def transport(self):
            return FakeTransport()

    assert provider() is None  # no worker yet
    ctrl._worker = FakeWorker()
    assert isinstance(provider(), FakeTransport)  # resolves the *current* worker


# --- controllers expose a blocking teardown for app exit ---------------------
def test_controllers_have_stop_blocking(home, qtapp):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import PROTOCOL_LOCAL
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    from rdpstudio.protocols.local.session import LocalShellController
    from rdpstudio.protocols.ssh.session import SshSessionController

    ssh = SshSessionController(Session(name="s", host="h", username="u"), ctx)
    local = LocalShellController(Session(protocol=PROTOCOL_LOCAL), ctx)
    for c in (ssh, local):
        assert callable(getattr(c, "stop_blocking", None))
        c.stop_blocking("test exit")  # must not raise even with nothing running
