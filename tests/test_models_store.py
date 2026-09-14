"""Session model + store persistence."""

from rdpstudio.core.models import Forward, Session
from rdpstudio.core.store import SessionStore


def test_session_roundtrip(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    s = Session(name="web-1", protocol="ssh", host="10.0.0.5", port=2222, username="deploy")
    s.forwards.append(Forward(kind="dynamic", listen_port=1080))
    s.tags = ["prod", "web"]
    store.upsert(s)

    store2 = SessionStore(tmp_path / "sessions.json")
    loaded = store2.get(s.id)
    assert loaded is not None
    assert loaded.host == "10.0.0.5"
    assert loaded.port == 2222
    assert loaded.forwards[0].kind == "dynamic"
    assert loaded.tags == ["prod", "web"]


def test_no_secrets_in_store(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    store.upsert(Session(name="x", host="h", auth="password"))
    raw = (tmp_path / "sessions.json").read_text()
    # the auth method name is stored, but no secret *values* are — a plain
    # password only ever appears if the user explicitly saves one
    assert '"auth": "password"' in raw
    assert "secret" not in raw
    assert '"password": ""' in raw  # empty field, nothing stored by default


def test_saved_password_and_fit_screen_roundtrip(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    s = Session(
        name="win", protocol="rdp", host="10.0.0.9", username="admin",
        password="s3cret", rdp_fit_screen=True,
    )
    store.upsert(s)

    store2 = SessionStore(tmp_path / "sessions.json")
    loaded = store2.get(s.id)
    assert loaded is not None
    assert loaded.password == "s3cret"
    assert loaded.rdp_fit_screen is True

    # exports must never carry saved passwords
    export = store2.export_dict()
    assert "password" not in export["sessions"][0]


def test_groups(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    store.ensure_group("Production")
    s = Session(name="db", group="Production")
    store.upsert(s)
    assert "Production" in store.groups()
    store.rename_group("Production", "Prod")
    assert store.get(s.id).group == "Prod"
    store.delete_group("Prod")
    assert store.get(s.id).group == ""


def test_duplicate_and_import(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    s = Session(name="db", host="db1")
    store.upsert(s)
    dup = store.duplicate(s.id)
    assert dup is not None and dup.id != s.id and dup.name.startswith("db")
    added = store.import_sessions([Session(name="db", host="other")])
    assert added == 1
    names = [x.display_name() for x in store.sessions()]
    assert any("(imported)" in n for n in names)


def test_update_commits_and_persists(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    s = Session(name="web", host="h", group="A")
    store.upsert(s)
    updated = store.update(s.id, lambda c: setattr(c, "group", "B"))
    assert updated is not None and updated.group == "B"
    assert store.get(s.id).group == "B"
    assert "B" in store.groups()
    reloaded = SessionStore(tmp_path / "sessions.json")
    assert reloaded.get(s.id).group == "B"


def test_update_unknown_id_returns_none(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    assert store.update("missing", lambda c: None) is None


def test_update_mutator_error_leaves_state_untouched(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    s = Session(name="web", host="h", group="A")
    store.upsert(s)

    def _boom(candidate):
        candidate.group = "B"
        raise RuntimeError("nope")

    try:
        store.update(s.id, _boom)
    except RuntimeError:
        pass
    assert store.get(s.id).group == "A"
    assert "B" not in store.groups()


def test_update_save_failure_rolls_back_memory(tmp_path, monkeypatch):
    store = SessionStore(tmp_path / "sessions.json")
    s = Session(name="web", host="h", group="A")
    store.upsert(s)

    def _fail(_text):
        raise OSError("disk gone")

    monkeypatch.setattr(store, "_atomic_write", _fail)
    try:
        store.update(s.id, lambda c: setattr(c, "group", "B"))
    except OSError:
        pass
    assert store.get(s.id).group == "A"
    assert "B" not in store.groups()


def test_get_copy_is_detached(tmp_path):
    store = SessionStore(tmp_path / "sessions.json")
    s = Session(name="web", host="h", group="A")
    store.upsert(s)
    dup = store.get_copy(s.id)
    assert dup is not None
    dup.group = "B"
    dup.options["pinned"] = True
    assert store.get(s.id).group == "A"
    assert "pinned" not in store.get(s.id).options


def test_update_concurrent_readers_and_writers(tmp_path):
    import threading

    store = SessionStore(tmp_path / "sessions.json")
    s = Session(name="web", host="h")
    store.upsert(s)
    errors: list = []

    def _writer(n):
        try:
            for i in range(25):
                store.update(s.id, lambda c, v=f"w{n}-{i}": c.options.update(tag=v))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    def _reader():
        try:
            for _ in range(50):
                store.get(s.id)
                store.get_copy(s.id)
                store.sessions()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_writer, args=(n,)) for n in range(4)]
    threads += [threading.Thread(target=_reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert store.get(s.id) is not None
