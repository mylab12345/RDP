"""Regression coverage for deterministic, isolated session imports."""

from __future__ import annotations

import json

import pytest

from rdpstudio.core.models import Session
from rdpstudio.core.store import SessionStore

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_repeated_import_names_are_unique_and_inputs_are_unchanged(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    original = Session(name="db", host="original")
    store.upsert(original)

    first = Session(name="db", host="first")
    second = Session(name="db", host="second")
    first_id, second_id = first.id, second.id
    assert store.import_sessions([first, second]) == 2

    # Import conflict repair belongs to the store; caller-owned models are not
    # unexpectedly renamed or re-identified.
    assert (first.id, first.name) == (first_id, "db")
    assert (second.id, second.name) == (second_id, "db")
    assert {item.display_name() for item in store.sessions()} == {
        "db",
        "db (imported)",
        "db (imported 2)",
    }


def test_imported_session_is_detached_from_caller_object(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    source = Session(name="web", host="before.example")
    store.import_sessions([source])

    source.host = "mutated.example"
    assert store.get(source.id).host == "before.example"


def test_duplicate_groups_are_repaired_on_load(tmp_path):
    path = tmp_path / "sessions.json"
    path.write_text(
        json.dumps({"format": 1, "groups": ["Prod", "Prod", "Dev"], "sessions": []}),
        encoding="utf-8",
    )
    assert SessionStore(path).groups() == ["Dev", "Prod"]
