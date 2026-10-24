"""Regression tests for the October 2026 hardening pass.

Each test pins one previously exploitable behaviour:

* predictable/symlinkable ``.rdp`` staging file (CWE-377/CWE-59)
* remote-supplied setuid/setgid/sticky bits applied by SCP and the share server
  (CWE-732)
* share-server write handles that survive a read-only policy change (SR-01)
* pre-auth share enumeration and unthrottled share-password guessing (SR-13)
* PPK export with a non-spec MAC, an ignored passphrase and a world-readable
  output file (SR-03)
* vault auto-lock that leaves credentials readable in the open dialog (SR-04)
* vault reads that hand out live objects and defeat rollback (SR-15)
* paste guard bypassed by a bracketed-paste terminator / escape sequence (SR-06)
* known_hosts keeping the *old* key trusted after a change was accepted (SR-09)
* spreadsheet formula injection in the cluster export (CWE-1236)
* world-readable session transcripts (SR-05)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import stat
import struct

import pytest

from rdpstudio.ui.session_log import SessionLogMixin

pytestmark = pytest.mark.unit


# ----------------------------------------------------------------------
# .rdp staging file: no symlink following, private permissions
# ----------------------------------------------------------------------
def test_rdp_file_refuses_planted_symlink(tmp_path):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.rdpfile import write_rdp_file

    victim = tmp_path / "victim.txt"
    victim.write_text("do not touch", encoding="utf-8")
    session = Session(id="abc123", name="win box", protocol="rdp", host="w")
    planted = tmp_path / "win_box_abc123.rdp"
    os.symlink(victim, planted)

    with pytest.raises(OSError):
        write_rdp_file(session, tmp_path)
    assert victim.read_text(encoding="utf-8") == "do not touch"


def test_rdp_file_overwrites_its_own_stale_copy(tmp_path):
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp.rdpfile import write_rdp_file

    session = Session(id="abc123", name="win box", protocol="rdp", host="w")
    first = write_rdp_file(session, tmp_path)
    second = write_rdp_file(session, tmp_path)
    assert first == second
    assert second.exists()
    if os.name == "posix":
        assert stat.S_IMODE(second.stat().st_mode) & 0o077 == 0


def test_rdp_default_directory_rejects_foreign_symlink(tmp_path, monkeypatch):
    from rdpstudio.protocols.rdp import rdpfile

    fake_tmp = tmp_path / "tmp"
    fake_tmp.mkdir()
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    uid = os.getuid() if hasattr(os, "getuid") else "user"
    os.symlink(attacker, fake_tmp / f"rdpstudio-{uid}")

    monkeypatch.setattr(rdpfile.tempfile, "gettempdir", lambda: str(fake_tmp))
    monkeypatch.setattr(rdpfile, "_fallback_dir", None)
    chosen = rdpfile._private_temp_dir()
    assert chosen != fake_tmp / f"rdpstudio-{uid}"
    assert chosen.is_dir()


# ----------------------------------------------------------------------
# SCP: never apply setuid/setgid/sticky bits from a remote header
# ----------------------------------------------------------------------
def test_scp_download_mode_drops_privileged_bits(tmp_path):
    from rdpstudio.protocols.ssh.scp import _apply_metadata

    target = tmp_path / "downloaded"
    target.write_bytes(b"payload")
    _apply_metadata(target, 0o4755, None, None, preserve_times=False)
    assert stat.S_IMODE(target.stat().st_mode) == 0o755
    _apply_metadata(target, 0o2777, None, None, preserve_times=False)
    assert stat.S_IMODE(target.stat().st_mode) == 0o777


# ----------------------------------------------------------------------
# Share server: mode masking, live revocation, banner, throttling
# ----------------------------------------------------------------------
class _FakeShareServer:
    def __init__(self, registry) -> None:
        self.registry = registry
        self.events: list[tuple[str, str, str]] = []

    def event(self, kind: str, detail: str, peer: str = "") -> None:
        self.events.append((kind, detail, peer))

    def peer_of(self, _iface) -> str:
        return ""


@pytest.fixture()
def share_backend(tmp_path):
    from rdpstudio.core.shares import Share, ShareRegistry
    from rdpstudio.tools.share_server import _ShareSFTPBackend

    root = tmp_path / "tools"
    root.mkdir()
    registry = ShareRegistry()
    registry.set_global([Share("Tools", str(root))], writable=True)
    fake = _FakeShareServer(registry)
    backend = _ShareSFTPBackend(object(), fake)
    return backend, registry, fake, root


def test_share_open_strips_privileged_mode_bits(share_backend):
    from paramiko import SFTPAttributes

    from rdpstudio.tools.share_server import SFTP_OK

    backend, _registry, _fake, root = share_backend
    attr = SFTPAttributes()
    attr.st_mode = 0o4755
    old_umask = os.umask(0)
    try:
        handle = backend.open("/Tools/new.sh", os.O_WRONLY | os.O_CREAT, attr)
        assert handle.write(0, b"#!/bin/sh\n") == SFTP_OK
        handle.close()
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE((root / "new.sh").stat().st_mode) == 0o755


def test_share_chattr_strips_privileged_mode_bits(share_backend):
    from paramiko import SFTPAttributes

    backend, _registry, _fake, root = share_backend
    target = root / "tool"
    target.write_text("x", encoding="utf-8")
    attr = SFTPAttributes()
    attr.st_mode = 0o6755
    assert backend.chattr("/Tools/tool", attr) == 0
    assert stat.S_IMODE(target.stat().st_mode) == 0o755


def test_share_mkdir_strips_privileged_mode_bits(share_backend):
    from paramiko import SFTPAttributes

    backend, _registry, _fake, root = share_backend
    attr = SFTPAttributes()
    attr.st_mode = 0o1777
    old_umask = os.umask(0)
    try:
        assert backend.mkdir("/Tools/sub", attr) == 0
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE((root / "sub").stat().st_mode) == 0o777


def test_open_write_handle_stops_after_read_only_switch(share_backend):
    from paramiko import SFTP_OK, SFTP_PERMISSION_DENIED, SFTPAttributes

    backend, registry, _fake, root = share_backend
    target = root / "log.txt"
    target.write_text("start", encoding="utf-8")
    handle = backend.open("/Tools/log.txt", os.O_WRONLY, SFTPAttributes())
    assert handle.write(0, b"before") == SFTP_OK

    registry.set_writable(False)
    assert handle.write(6, b"after") == SFTP_PERMISSION_DENIED
    handle.close()
    assert b"after" not in target.read_bytes()


def test_share_banner_does_not_enumerate_shares(tmp_path):
    from rdpstudio.core.shares import Share, ShareRegistry
    from rdpstudio.tools.share_server import SftpShareServer, ShareServerConfig, _ShareAuthServer  # noqa: I001

    root = tmp_path / "secret-dir"
    root.mkdir()
    registry = ShareRegistry()
    registry.set_global([Share("Payroll", str(root))], writable=False)
    srv = SftpShareServer(ShareServerConfig(bind="127.0.0.1", port=0), registry)
    banner, _lang = _ShareAuthServer(srv).get_banner()
    assert "Payroll" not in banner


def test_auth_throttle_backs_off_and_resets():
    from rdpstudio.tools.share_server import _AuthThrottle

    throttle = _AuthThrottle(free_failures=2, window=60.0, max_delay=4.0)
    peer = "192.0.2.10"
    for _ in range(2):
        throttle.record_failure(peer)
    assert throttle.delay_for(peer) == 0.0
    throttle.record_failure(peer)
    first = throttle.delay_for(peer)
    assert first > 0.0
    for _ in range(4):
        throttle.record_failure(peer)
    assert throttle.delay_for(peer) <= 4.0
    throttle.reset(peer)
    assert throttle.delay_for(peer) == 0.0


def test_auth_throttle_is_bounded():
    from rdpstudio.tools.share_server import _AuthThrottle

    throttle = _AuthThrottle(max_peers=8)
    for i in range(64):
        throttle.record_failure(f"198.51.100.{i}")
    assert len(throttle._failures) <= 9  # bounded, no unbounded growth


# ----------------------------------------------------------------------
# PPK export correctness and confidentiality
# ----------------------------------------------------------------------
def _expected_ppk_mac(ppk_text: str) -> str:
    lines = ppk_text.strip().splitlines()
    key_type = lines[0].split(": ", 1)[1].encode("ascii")
    encryption = lines[1].split(": ", 1)[1].encode("ascii")
    comment = lines[2].split(": ", 1)[1].encode("utf-8")
    pub_lines = int(lines[3].split(": ", 1)[1])
    pub = base64.b64decode("".join(lines[4 : 4 + pub_lines]))
    priv_idx = 4 + pub_lines
    priv_lines = int(lines[priv_idx].split(": ", 1)[1])
    priv = base64.b64decode("".join(lines[priv_idx + 1 : priv_idx + 1 + priv_lines]))
    data = (
        struct.pack(">I", len(key_type)) + key_type
        + struct.pack(">I", len(encryption)) + encryption
        + struct.pack(">I", len(comment)) + comment
        + struct.pack(">I", len(pub)) + pub
        + struct.pack(">I", len(priv)) + priv
    )
    return hmac.new(hashlib.sha1(comment).digest(), data, hashlib.sha1).hexdigest()


def test_ppk_mac_matches_the_ppk_v2_construction(tmp_path):
    from rdpstudio.protocols.ssh import keys
    from rdpstudio.tools.key_converter import openssh_to_ppk

    key_path = tmp_path / "id_ed25519"
    keys.generate(str(key_path), key_type="ed25519")
    ppk = openssh_to_ppk(key_path.read_bytes(), comment="test-key")
    mac = [ln.split(": ", 1)[1] for ln in ppk.splitlines() if ln.startswith("Private-MAC:")][0]
    assert mac == _expected_ppk_mac(ppk)


def test_ppk_ed25519_private_blob_is_the_raw_scalar(tmp_path):
    from rdpstudio.protocols.ssh import keys
    from rdpstudio.tools.key_converter import openssh_to_ppk

    key_path = tmp_path / "id_ed25519"
    info = keys.generate(str(key_path), key_type="ed25519")
    ppk = openssh_to_ppk(key_path.read_bytes())
    lines = ppk.strip().splitlines()
    priv_idx = lines.index([ln for ln in lines if ln.startswith("Private-Lines:")][0])
    priv = base64.b64decode("".join(lines[priv_idx + 1 : -1]))
    assert len(priv) == 32
    assert info.key_type == "ssh-ed25519"


def test_ppk_rejects_silently_ignored_passphrase(tmp_path):
    from rdpstudio.protocols.ssh import keys
    from rdpstudio.tools.key_converter import openssh_to_ppk

    key_path = tmp_path / "id_ed25519"
    keys.generate(str(key_path), key_type="ed25519")
    with pytest.raises(ValueError, match="encrypt"):
        openssh_to_ppk(key_path.read_bytes(), passphrase="secret")


def test_ppk_comment_cannot_inject_records(tmp_path):
    from rdpstudio.protocols.ssh import keys
    from rdpstudio.tools.key_converter import openssh_to_ppk

    key_path = tmp_path / "id_ed25519"
    keys.generate(str(key_path), key_type="ed25519")
    with pytest.raises(ValueError, match="control"):
        openssh_to_ppk(key_path.read_bytes(), comment="x\nEncryption: none")


# ----------------------------------------------------------------------
# Vault: detached reads, and the dialog purges secrets on lock
# ----------------------------------------------------------------------
def test_vault_reads_are_detached(tmp_path):
    from rdpstudio.core.vault import Credential, CredentialVault

    vault = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    vault.create("master")
    stored = vault.put(Credential(name="prod", secret="s3cret"))

    live = vault.get(stored.id)
    live.secret = "tampered"
    assert vault.get(stored.id).secret == "s3cret"
    assert [c.secret for c in vault.entries()] == ["s3cret"]

    stored.secret = "mutated after put"
    assert vault.get(stored.id).secret == "s3cret"


def test_vault_dialog_purges_secrets_when_the_vault_locks(home, qtapp):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import Credential, CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider
    from rdpstudio.ui.vault_dialog import VaultDialog

    vault = CredentialVault(home / "vault.bin", kdf_iterations=60_000)
    vault.create("master")
    vault.put(Credential(name="prod", secret="s3cret"))
    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=vault,
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    dlg = VaultDialog(ctx, None)
    try:
        assert dlg.cred_list.count() == 1
        dlg.cred_list.setCurrentRow(0)
        qtapp.processEvents()
        assert dlg.cred_secret.text() == "s3cret"
        dlg.reveal_btn.setChecked(True)
        assert dlg.cred_secret.echoMode() == dlg.cred_secret.EchoMode.Normal

        vault.lock()
        dlg._watch_vault_lock()
        qtapp.processEvents()

        assert dlg.cred_secret.text() == ""
        assert dlg.cred_list.count() == 0
        assert dlg.reveal_btn.isChecked() is False
        assert dlg.cred_secret.echoMode() == dlg.cred_secret.EchoMode.Password
        # Selecting a stale row must not restore anything either.
        dlg._load_credential(0)
        assert dlg.cred_secret.text() == ""
    finally:
        dlg.deleteLater()


# ----------------------------------------------------------------------
# Paste guard: escape sequences and bracketed-paste terminators
# ----------------------------------------------------------------------
def test_paste_guard_treats_escape_sequences_as_dangerous():
    from rdpstudio.ui.paste_guard import needs_paste_confirmation

    assert needs_paste_confirmation("\x1b[201~rm -rf /")
    assert needs_paste_confirmation("title\x07")
    assert not needs_paste_confirmation("ls -la")
    assert not needs_paste_confirmation("tab\tseparated")


def test_bracketed_paste_markers_are_stripped():
    from rdpstudio.ui.paste_guard import sanitize_bracketed_paste

    assert sanitize_bracketed_paste("safe\x1b[201~rm -rf /") == "saferm -rf /"
    assert sanitize_bracketed_paste("\x1b[200~payload") == "payload"
    assert sanitize_bracketed_paste("plain") == "plain"


# ----------------------------------------------------------------------
# known_hosts: an accepted key change replaces the old trust
# ----------------------------------------------------------------------
def test_known_hosts_replaces_key_after_accepted_change(tmp_path):
    import paramiko

    from rdpstudio.protocols.ssh import keys
    from rdpstudio.protocols.ssh.knownhosts import KnownHostsVerifier

    first_path = tmp_path / "k1"
    second_path = tmp_path / "k2"
    keys.generate(str(first_path), key_type="ed25519")
    keys.generate(str(second_path), key_type="ed25519")
    first = paramiko.Ed25519Key(filename=str(first_path))
    second = paramiko.Ed25519Key(filename=str(second_path))

    class _AcceptAll:
        def ask_host_key(self, hostname, keytype, fingerprint, changed=False):
            return True

    kh_path = tmp_path / "known_hosts"
    verifier = KnownHostsVerifier(kh_path, "accept-new", _AcceptAll())
    verifier.missing_host_key(None, "example.test", first)
    assert first in list(verifier.host_keys.lookup("example.test").values())

    verifier.missing_host_key(None, "example.test", second)
    assert verifier.last_changed is True
    trusted = list(verifier.host_keys.lookup("example.test").values())
    assert trusted == [second], "the superseded key must no longer be trusted"

    reloaded = KnownHostsVerifier(kh_path, "accept-new", _AcceptAll())
    assert list(reloaded.host_keys.lookup("example.test").values()) == [second]


# ----------------------------------------------------------------------
# Cluster export: spreadsheet/markdown injection
# ----------------------------------------------------------------------
def test_csv_export_neutralises_formulas():
    from rdpstudio.core.export_safety import sanitize_csv_cell, sanitize_markdown_cell

    for payload in ("=cmd|' /C calc'!A0", "+1+1", "-2+3", "@SUM(A1)"):
        assert sanitize_csv_cell(payload).startswith("'")
    assert sanitize_csv_cell("  =1+1").startswith("'")
    assert sanitize_csv_cell("normal output") == "normal output"
    assert sanitize_csv_cell("") == ""
    assert sanitize_markdown_cell("a|b\nc") == "a\\|b c"
    assert sanitize_markdown_cell("=1+1") == "=1+1"


# ----------------------------------------------------------------------
# Session transcripts are private and never follow a symlink
# ----------------------------------------------------------------------
class _LogHost(SessionLogMixin):
    def __init__(self) -> None:
        self._log_file = None
        self._log_path = None


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission model")
def test_session_log_file_is_private(tmp_path):
    host = _LogHost()
    target = tmp_path / "session.log"
    target.write_text("previous", encoding="utf-8")
    os.chmod(target, 0o644)

    host.start_logging(target)
    try:
        assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0
    finally:
        host.stop_logging()


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission model")
def test_session_log_refuses_symlink(tmp_path):
    host = _LogHost()
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    link = tmp_path / "session.log"
    os.symlink(victim, link)
    with pytest.raises(OSError):
        host.start_logging(link)
    assert victim.read_text(encoding="utf-8") == "keep"
