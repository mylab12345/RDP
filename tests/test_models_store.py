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
