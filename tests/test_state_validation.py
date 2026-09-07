"""Regression tests for malformed/corrupt persisted state."""

from __future__ import annotations

import json

import pytest

from rdpstudio.core.crypto import (
    MAX_KDF_ITERATIONS,
    CryptoError,
    Envelope,
    seal,
)
from rdpstudio.core.models import Forward, Session
from rdpstudio.core.settings import Settings
from rdpstudio.core.vault import Credential, CredentialVault

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_settings_rejects_non_object_and_structured_scalars(tmp_path):
    assert Settings.from_dict(["not", "an", "object"]) == Settings()

    settings = Settings.from_dict(
        {
            "theme": [],
            "font_family": {"unexpected": "mapping"},
            "default_download_dir": 123,
            "toolbar_labels": "false",
            "animations": "YES",
            "copy_on_select": "0",
            "default_auto_reconnect": "off",
        }
    )
    assert settings.theme == "mobaxterm"
    assert settings.font_family == ""
    assert settings.default_download_dir == ""
    assert settings.toolbar_labels is False
    assert settings.animations is True
    assert settings.copy_on_select is False
    assert settings.default_auto_reconnect is False
    assert Settings.from_dict({"kdf_iterations": MAX_KDF_ITERATIONS + 1}).kdf_iterations == MAX_KDF_ITERATIONS

    path = tmp_path / "settings.json"
    path.write_bytes(b"\xff\xfe\x00invalid utf-8")
    assert Settings.load(path) == Settings()


def test_session_boolean_strings_and_non_finite_numbers_are_repaired():
    session = Session.from_dict(
        {
            "auto_reconnect": "false",
            "compression": "0",
            "rdp_cert_ignore": "no",
            "rdp_pass_on_cmdline": "off",
            "rdp_clipboard": "yes",
            "created_at": float("inf"),
            "updated_at": float("-inf"),
        }
    )
    assert session.auto_reconnect is False
    assert session.compression is False
    assert session.rdp_cert_ignore is False
    assert session.rdp_pass_on_cmdline is False
    assert session.rdp_clipboard is True
    assert session.created_at != float("inf")
    assert session.updated_at != float("-inf")

    assert Forward.from_dict({"enabled": "false"}).enabled is False


@pytest.mark.parametrize(
    "document",
    [
        [],
        1,
        {"format": 1, "kdf": [], "aead": {}},
        {"format": 1, "kdf": {}, "aead": "bad"},
    ],
)
def test_envelope_rejects_wrong_json_shapes(document):
    with pytest.raises(CryptoError):
        Envelope.from_json(json.dumps(document))


def test_envelope_caps_hostile_kdf_work_factor():
    envelope = seal("master", b"payload", 60_000)
    document = json.loads(envelope.to_json())
    document["kdf"]["iterations"] = MAX_KDF_ITERATIONS + 1
    with pytest.raises(CryptoError):
        Envelope.from_json(json.dumps(document))

    with pytest.raises(ValueError):
        seal("master", b"payload", MAX_KDF_ITERATIONS + 1)


def test_vault_skips_structured_entry_fields(tmp_path):
    path = tmp_path / "vault.bin"
    payload = json.dumps(
        {
            "entries": [
                {"id": ["unhashable"], "name": "bad id", "secret": "skip me"},
                {"id": "valid", "name": ["not text"], "secret": {"not": "text"}},
            ]
        }
    ).encode()
    path.write_text(seal("master", payload, 60_000).to_json(), encoding="utf-8")

    vault = CredentialVault(path, kdf_iterations=60_000)
    vault.unlock("master")
    entries = vault.entries()
    assert [entry.id for entry in entries] == ["valid"]
    assert entries[0].name == ""
    assert entries[0].secret == ""


def test_explicit_vault_save_updates_future_autosave_key(tmp_path):
    path = tmp_path / "vault.bin"
    vault = CredentialVault(path, kdf_iterations=60_000)
    vault.create("old")
    vault.put(Credential(name="first", secret="one"))

    vault.save("new")
    vault.put(Credential(name="second", secret="two"))
    vault.lock()

    reopened = CredentialVault(path, kdf_iterations=60_000)
    reopened.unlock("new")
    assert {item.name for item in reopened.entries()} == {"first", "second"}
    with pytest.raises(CryptoError):
        CredentialVault(path, kdf_iterations=60_000).unlock("old")


def test_failed_vault_autosave_rolls_back_collection(tmp_path, monkeypatch):
    vault = CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)
    vault.create("master")

    def fail_save(_master):
        raise OSError("disk full")

    monkeypatch.setattr(vault, "_save_locked", fail_save)
    credential = Credential(name="not-durable", secret="secret")
    with pytest.raises(OSError, match="disk full"):
        vault.put(credential)

    assert vault.entries() == []
