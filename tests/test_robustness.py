"""Regression tests for the robustness pass.

Each test pins a failure mode that used to crash, wipe data, or hang.
They must stay green if the intended behaviour is preserved.
"""

from __future__ import annotations

import json
import struct

import pytest

from rdpstudio.core.crypto import CryptoError, Envelope, seal
from rdpstudio.core.models import Forward, Session
from rdpstudio.core.reconnect import ReconnectPolicy
from rdpstudio.core.settings import Settings
from rdpstudio.core.store import SessionStore
from rdpstudio.core.vault import Credential, CredentialVault


def test_change_master_updates_in_memory_key(tmp_path):
    """After rotate, auto-save must keep using the *new* passphrase."""
    vault = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    vault.create("old-master")
    cred = Credential(name="prod", secret="s3cret")
    vault.put(cred)
    vault.change_master("old-master", "new-master")

    # A subsequent put() used to re-seal with the *old* master, so the
    # vault became unopenable with the passphrase the user just chose.
    vault.put(Credential(name="extra", secret="another"))
    vault.lock()

    fresh = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    fresh.unlock("new-master")
    names = {c.name for c in fresh.entries()}
    assert names == {"prod", "extra"}
    with pytest.raises(CryptoError):
        CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000).unlock("old-master")


def test_change_master_while_locked_does_not_wipe(tmp_path):
    vault = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    vault.create("old-master")
    cred = Credential(name="keep-me", secret="dont-drop")
    vault.put(cred)
    vault.lock()

    # Previously this wrote the (empty) in-memory entry list over the file.
    locked = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    locked.change_master("old-master", "new-master")
    assert not locked.unlocked

    fresh = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    fresh.unlock("new-master")
    got = fresh.get(cred.id)
    assert got is not None and got.secret == "dont-drop"


def test_unlock_skips_corrupt_entries(tmp_path):
    vault = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    vault.create("m")
    vault.put(Credential(name="good", secret="hunter2"))
    # Forge a payload with one broken entry mixed in.
    raw = json.dumps(
        {
            "entries": [
                {"id": "aaaa", "name": "good", "secret": "hunter2"},
                "not-a-dict",
                {"id": "", "name": "nameless"},
                {"id": "bbbb", "name": "also-good", "secret": 12345},
            ]
        }
    ).encode()
    env = seal("m", raw, 60_000)
    vault.path.write_text(env.to_json(), encoding="utf-8")

    fresh = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    fresh.unlock("m")
    names = {c.name for c in fresh.entries()}
    assert "good" in names
    assert "also-good" in names


def test_envelope_rejects_impossible_params():
    env = seal("m", b"x", iterations=60_000)
    doc = json.loads(env.to_json())
    doc["kdf"]["iterations"] = 0
    with pytest.raises(CryptoError):
        Envelope.from_json(json.dumps(doc))
    doc = json.loads(env.to_json())
    doc["aead"]["nonce"] = "AA=="  # too short
    with pytest.raises(CryptoError):
        Envelope.from_json(json.dumps(doc))


def test_session_from_dict_garbage_never_raises():
    s = Session.from_dict(
        {
            "id": 12,
            "port": "not-a-port",
            "timeout": None,
            "keepalive": "x",
            "tags": "prod",
            "forwards": [{"listen_port": "nope"}, "bad", {"kind": "dynamic", "listen_port": 1080}],
            "options": ["not", "a", "dict"],
            "rdp_width": -5,
            "created_at": "yesterday",
        }
    )
    assert s.port == 22
    assert s.timeout >= 1
    assert s.tags == ["prod"]
    assert len(s.forwards) == 2
    assert s.forwards[1].kind == "dynamic"
    assert s.forwards[1].listen_port == 1080
    assert s.options == {}
    assert s.rdp_width >= 640
    assert isinstance(s.created_at, float)

    assert Session.from_dict("nope").host == ""
    assert Forward.from_dict("nope").kind == "local"


def test_store_survives_corrupt_file_shapes(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    store = SessionStore(path)
    assert store.sessions() == []

    path.write_text(json.dumps({"groups": "Production", "sessions": {"id": "x"}}), encoding="utf-8")
    store.load()
    assert store.groups() == []
    assert store.sessions() == []

    path.write_text(
        json.dumps(
            {
                "groups": ["ok", 3, ""],
                "sessions": [{"name": "web", "host": "h"}, "nope", {"port": "zz", "host": "ok"}],
            }
        ),
        encoding="utf-8",
    )
    store.load()
    assert store.groups() == ["ok"]
    assert len(store.sessions()) == 2


def test_import_sessions_skips_non_sessions(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    added = store.import_sessions([None, "x", Session(name="real", host="h")])  # type: ignore[list-item]
    assert added == 1
    assert store.sessions()[0].name == "real"


def test_settings_coerce_enums_and_floats():
    s = Settings.from_dict(
        {
            "theme": "neon",
            "host_key_policy": "yolo",
            "rdp_client": "maybe",
            "cursor_style": "blink",
            "reconnect_base_delay": "fast",
            "reconnect_max_delay": float("nan"),
            "geometry": "wide",
        }
    )
    assert s.theme == "dark"
    assert s.host_key_policy == "accept-new"
    assert s.rdp_client == "auto"
    assert s.cursor_style == "block"
    assert s.reconnect_base_delay >= 0.2
    assert s.reconnect_max_delay >= 0.2
    assert s.geometry == {}


def test_reconnect_policy_guards_bad_attempts():
    policy = ReconnectPolicy(max_attempts=3, base_delay=1.0, max_delay=10.0, jitter=0)
    assert policy.delay_for_attempt(0) == 1.0
    assert policy.delay_for_attempt(-9) == 1.0
    assert policy.delay_for_attempt("nope") == 1.0  # type: ignore[arg-type]
    assert policy.delay_for_attempt(99) == 10.0
    assert not policy.should_retry(0)
    assert not policy.should_retry("x")  # type: ignore[arg-type]


def _load_negotiate():
    """Import negotiate.py without pulling the Qt plugin package."""
    import importlib.util
    import sys
    from pathlib import Path

    name = "rdpstudio_rdp_negotiate"
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parents[1] / "src/rdpstudio/protocols/rdp/negotiate.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_probe_rejects_oversized_tpkt_length():
    """A peer advertising a 64 KiB TPKT must not make us buffer forever."""
    import socket
    import threading

    negotiate = _load_negotiate()
    parse_connection_confirm, probe = negotiate.parse_connection_confirm, negotiate.probe

    # TPKT version 3, reserved 0, length 65535 — classic length-bomb.
    bomb = struct.pack(">BBH", 3, 0, 65535) + b"\x00" * 20

    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def run():
        conn, _ = srv.accept()
        conn.recv(512)
        conn.sendall(bomb)
        conn.close()
        srv.close()

    threading.Thread(target=run, daemon=True).start()
    result = probe("127.0.0.1", port, timeout=3.0)
    # Must return (not hang) and treat the truncated header as not-ok or
    # as a classic confirm — either way, no exception.
    assert isinstance(result.ok, bool)
    parsed = parse_connection_confirm(bomb[:24])
    assert parsed.ok or parsed.error


def test_probe_rejects_bad_port():
    negotiate = _load_negotiate()
    with pytest.raises(negotiate.RdpProbeError):
        negotiate.probe("127.0.0.1", 0)
    with pytest.raises(negotiate.RdpProbeError):
        negotiate.probe("", 3389)


def test_jump_cycle_does_not_recurse(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    a = Session(name="a", host="a.example", username="u")
    b = Session(name="b", host="b.example", username="u")
    a.jump_session_id = b.id
    b.jump_session_id = a.id
    store.upsert(a)
    store.upsert(b)

    hops = store.jump_hops(a)
    assert [h.host for h in hops] == ["b.example"]

    # Self-loop
    a.jump_session_id = a.id
    store.upsert(a)
    assert store.jump_hops(a) == []

    # Linear A → B → C is fully walked
    c = Session(name="c", host="c.example", username="u")
    store.upsert(c)
    b.jump_session_id = c.id
    a.jump_session_id = b.id
    store.upsert(a)
    store.upsert(b)
    assert [h.host for h in store.jump_hops(a)] == ["b.example", "c.example"]


def test_parse_ports_filters_garbage():
    from rdpstudio.tools.network_scanner import PRESET_COMMON, parse_ports

    assert parse_ports([22, "nope", 80, 999999, -1]) == [22, 80]
    assert parse_ports("nope,also-bad") == PRESET_COMMON
