"""Unit and integration coverage for durable state-file persistence."""

from __future__ import annotations

import json
import os
import stat

import pytest

from rdpstudio.core.persistence import (
    atomic_write_text,
    atomic_write_via_path,
)

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_atomic_write_is_private_and_replaces_complete_content(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("old", encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o644)

    atomic_write_text(path, '{"value": "✓"}')

    assert path.read_text(encoding="utf-8") == '{"value": "✓"}'
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_failed_replace_preserves_destination_and_removes_temp(tmp_path, monkeypatch):
    from rdpstudio.core import persistence

    path = tmp_path / "settings.json"
    path.write_text("known-good", encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("simulated full filesystem")

    monkeypatch.setattr(persistence.os, "replace", fail_replace)
    with pytest.raises(OSError, match="full filesystem"):
        atomic_write_text(path, "new", prefix=".settings-")

    assert path.read_text(encoding="utf-8") == "known-good"
    assert list(tmp_path.glob(".settings-*")) == []


def test_path_writer_failure_is_transactional(tmp_path):
    path = tmp_path / "known_hosts"
    path.write_text("trusted old key\n", encoding="utf-8")

    def broken_writer(temp_path):
        temp_path.write_text("partial", encoding="utf-8")
        raise OSError("serializer stopped")

    with pytest.raises(OSError, match="serializer stopped"):
        atomic_write_via_path(path, broken_writer, prefix=".known-hosts-")

    assert path.read_text(encoding="utf-8") == "trusted old key\n"
    assert list(tmp_path.glob(".known-hosts-*")) == []


@pytest.mark.integration
def test_application_state_stores_roundtrip_through_shared_writer(tmp_path):
    """Settings, sessions, snippets, and the vault remain interoperable."""
    from rdpstudio.core.models import Session
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import Credential, CredentialVault
    from rdpstudio.tools.snippets import Snippet, SnippetStore

    settings_path = tmp_path / "settings.json"
    settings = Settings(theme="nord", copy_on_select=False)
    settings.save(settings_path)

    sessions_path = tmp_path / "sessions.json"
    sessions = SessionStore(sessions_path)
    sessions.upsert(Session(name="prod", host="prod.example", username="ops"))

    snippets_path = tmp_path / "snippets.json"
    snippets = SnippetStore(snippets_path)
    snippets.reset_defaults()
    custom = Snippet(name="Health", command="uptime", category="Ops")
    snippets.upsert(custom)

    vault_path = tmp_path / "vault.bin"
    vault = CredentialVault(vault_path, kdf_iterations=60_000)
    vault.create("correct horse")
    credential = vault.put(Credential(name="prod", username="ops", secret="battery staple"))
    vault.lock()

    assert Settings.load(settings_path).to_dict() == settings.to_dict()
    assert SessionStore(sessions_path).sessions()[0].host == "prod.example"
    assert SnippetStore(snippets_path).get(custom.id).command == "uptime"
    fresh_vault = CredentialVault(vault_path, kdf_iterations=60_000)
    fresh_vault.unlock("correct horse")
    assert fresh_vault.get(credential.id).secret == "battery staple"

    # All JSON-backed stores must contain complete parseable documents.
    json.loads(settings_path.read_text(encoding="utf-8"))
    json.loads(sessions_path.read_text(encoding="utf-8"))
    json.loads(snippets_path.read_text(encoding="utf-8"))
    json.loads(vault_path.read_text(encoding="utf-8"))
