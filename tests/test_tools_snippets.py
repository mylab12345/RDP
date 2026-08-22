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
