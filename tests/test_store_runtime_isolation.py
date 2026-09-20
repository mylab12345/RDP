"""Regression coverage for store/runtime object isolation."""

from __future__ import annotations

import pytest

from rdpstudio.core.models import Session
from rdpstudio.core.store import SessionStore

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_upsert_detaches_caller_owned_session(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    session = Session(name="prod", host="prod.example")
    store.upsert(session)

    session.password = "ephemeral-secret"
    session.options["pinned"] = True
    session.group = "Mutated outside the store"

    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.password == ""
    assert loaded.options == {}
    assert loaded.group == ""

    store.ensure_group("ops")  # force an unrelated save
    reloaded = SessionStore(tmp_path / "sessions.json").get(session.id)
    assert reloaded is not None
    assert reloaded.password == ""
    assert reloaded.options == {}
    assert reloaded.group == ""


def test_read_apis_return_detached_copies(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    session = Session(name="prod", host="prod.example")
    store.upsert(session)

    loaded = store.get(session.id)
    listed = store.sessions()[0]
    assert loaded is not None
    loaded.password = "prompt-only"
    listed.options["pinned"] = True

    fresh = store.get(session.id)
    assert fresh is not None
    assert fresh.password == ""
    assert fresh.options == {}
