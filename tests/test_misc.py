"""Plugin registry, reconnect policy, importers, keys, settings."""

from __future__ import annotations

import pytest


def test_registry_builtins():
    from rdpstudio.core.plugin import registry

    ids = {p.id for p in registry().all()}
    assert {"ssh", "rdp", "local"} <= ids
    ssh = registry().require("ssh")
    assert ssh.default_port == 22
    rdp = registry().require("rdp")
    assert rdp.default_port == 3389


def test_registry_third_party(home):
    from rdpstudio.core.plugin import (
        Capabilities,
        PluginRegistry,
        ProtocolPlugin,
        SessionController,
        SessionState,
    )

    class FakeController(SessionController):
        def start(self):
            self.set_state(SessionState.CONNECTED)

        def widget(self):
            from PySide6.QtWidgets import QLabel

            return QLabel("fake")

        def capabilities(self):
            return Capabilities(shell=True)

    class TelnetPlugin(ProtocolPlugin):
        id = "telnet"
        title = "Telnet"
        description = "legacy"
        default_port = 23

        def create_session(self, definition, ctx):
            return FakeController(definition, ctx)

    reg = PluginRegistry()
    reg.register(TelnetPlugin())
    assert reg.get("telnet") is not None
    assert reg.get("nope") is None
    with pytest.raises(KeyError):
        reg.require("nope")


def test_quick_connect_parse():
    from rdpstudio.core.plugin import registry

    ssh = registry().require("ssh")
    s = ssh.quick_connect_target("root@10.0.0.9:2222")
    assert s is not None
    assert (s.username, s.host, s.port) == ("root", "10.0.0.9", 2222)

    rdp = registry().require("rdp")
    r = rdp.quick_connect_target("win.lab.local:3389")
    assert r is not None and r.protocol == "rdp" and r.port == 3389

    assert ssh.quick_connect_target("not a host!") is None


def test_reconnect_policy():
    from rdpstudio.core.reconnect import ReconnectPolicy

    policy = ReconnectPolicy(max_attempts=3, base_delay=1.0, max_delay=10.0, jitter=0)
    assert policy.should_retry(1) and policy.should_retry(3)
    assert not policy.should_retry(4)
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    assert policy.delay_for_attempt(9) == 10.0  # capped


def test_ssh_config_importer():
    from rdpstudio.importers.ssh_config import parse_ssh_config

    text = """
Host web1
    HostName 10.0.0.11
    User deploy
    Port 2222
    IdentityFile ~/.ssh/id_web

Host *
    Compression yes
"""
    sessions = parse_ssh_config(text)
    assert len(sessions) == 1
    s = sessions[0]
    assert s.host == "10.0.0.11" and s.username == "deploy" and s.port == 2222
    assert s.auth == "key"
    assert s.key_path.endswith("id_web")


def test_key_generation(tmp_path):
    pytest.importorskip("paramiko")
    from rdpstudio.protocols.ssh import keys

    info = keys.generate(str(tmp_path / "k_ed"), "ed25519")
    assert info.key_type == "ssh-ed25519"
    assert info.sha256_fingerprint.startswith("SHA256:")
    loaded = keys.load_key(str(tmp_path / "k_ed"))
    assert loaded.get_name() == "ssh-ed25519"

    info_rsa = keys.generate(str(tmp_path / "k_rsa"), "rsa", bits=2048)
    assert info_rsa.bits == 2048


def test_key_passphrase_roundtrip(tmp_path):
    pytest.importorskip("paramiko")
    import paramiko

    from rdpstudio.protocols.ssh import keys

    path = str(tmp_path / "secret_key")
    keys.generate(path, "ed25519", passphrase="open sesame")

    with pytest.raises(paramiko.PasswordRequiredException):
        keys.load_key(path)
    loaded = keys.load_key(path, "open sesame")
    assert loaded is not None


def test_settings_roundtrip(tmp_path):
    from rdpstudio.core.settings import Settings

    s = Settings()
    s.font_size = 12
    s.theme = "light"
    s.save(tmp_path / "settings.json")
    loaded = Settings.load(tmp_path / "settings.json")
    assert loaded.font_size == 12 and loaded.theme == "light"


def test_font_presets_cover_multiple_families():
    from rdpstudio.core.settings import FONT_PRESETS

    assert len(FONT_PRESETS) >= 16
    for name in (
        "DejaVu Sans Mono",
        "Liberation Mono",
        "JetBrains Mono",
        "Cascadia Code",
        "Fira Code",
        "IBM Plex Mono",
        "Hack",
        "Consolas",
        "Courier New",
    ):
        assert name in FONT_PRESETS
