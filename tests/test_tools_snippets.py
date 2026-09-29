"""Unit tests for snippet manager, macro storage, and variable rendering."""

from __future__ import annotations

from rdpstudio.tools.snippets import DEFAULT_SNIPPETS, Snippet, SnippetStore


def test_snippet_model_and_render():
    s = Snippet(
        name="Uptime check",
        command="ssh $USER@$HOST -p $PORT uptime && echo '$SELECTION'",
        category="Admin",
    )
    rendered = s.render({"host": "10.0.0.1", "user": "ubuntu", "port": "2222", "selection": "important_log"})
    assert "ssh ubuntu@10.0.0.1 -p 2222 uptime" in rendered
    assert "'important_log'" in rendered


def test_snippet_store_persistence(tmp_path):
    p = tmp_path / "snippets.json"
    store = SnippetStore(p)
    assert len(store.snippets()) == len(DEFAULT_SNIPPETS)
    assert "System Info" in store.categories()

    custom = Snippet(name="Custom Test", command="echo hello", category="CustomCat")
    store.upsert(custom)

    store2 = SnippetStore(p)
    loaded = store2.get(custom.id)
    assert loaded is not None
    assert loaded.name == "Custom Test"
    assert "CustomCat" in store2.categories()

    assert store2.delete(custom.id) is True
    assert store2.get(custom.id) is None


def test_snippet_store_reset_defaults(tmp_path):
    p = tmp_path / "snippets.json"
    store = SnippetStore(p)
    store.delete(store.snippets()[0].id)
    assert len(store.snippets()) < len(DEFAULT_SNIPPETS)

    store.reset_defaults()
    assert len(store.snippets()) == len(DEFAULT_SNIPPETS)


def test_snippet_library_export_and_import_preserves_local_entries(tmp_path):
    source = SnippetStore(tmp_path / "source.json")
    shared = Snippet(name="Deploy", command="./deploy.sh", category="Release")
    source.upsert(shared)

    destination = SnippetStore(tmp_path / "destination.json")
    local = Snippet(name="Deploy", command="./deploy-local.sh", category="Local")
    destination.upsert(local)

    assert destination.import_dict(source.export_dict()) == len(source.snippets())
    imported = [snippet for snippet in destination.snippets() if snippet.command == "./deploy.sh"]
    assert len(imported) == 1
    assert imported[0].name == "Deploy (imported)"
    assert destination.get(local.id).command == "./deploy-local.sh"


def test_snippet_import_rejects_malformed_entries(tmp_path):
    store = SnippetStore(tmp_path / "snippets.json")
    before = len(store.snippets())
    assert store.import_dict({"snippets": [{"name": "", "command": "uptime"}, "bad"]}) == 0
    assert len(store.snippets()) == before


def test_snippet_duplicate_creates_a_persisted_independent_copy(tmp_path):
    store = SnippetStore(tmp_path / "snippets.json")
    source = Snippet(name="Deploy", command="./deploy.sh", category="Release", description="Production")
    store.upsert(source)

    duplicate = store.duplicate(source.id)
    assert duplicate is not None
    assert duplicate.id != source.id
    assert duplicate.name == "Deploy (copy)"
    assert duplicate.command == source.command
    assert duplicate.description == source.description
    assert SnippetStore(store.path).get(duplicate.id) == duplicate

    another = store.duplicate(source.id)
    assert another is not None
    assert another.name == "Deploy (copy 2)"
