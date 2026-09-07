"""Built-in SFTP share server: shares, jail, auth, live transfers, UI wiring.

The transfer tests talk to the *real* listener over a real SSH transport with
paramiko's SFTP client — the same client the Windows ``sftp.exe`` / WinSCP
implement — so the protocol behaviour is covered, not a re-implementation of it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rdpstudio.core.shares import (
    SCOPE_GLOBAL,
    SCOPE_SESSION,
    Share,
    ShareError,
    ShareRegistry,
    sanitize_share_name,
    share_name_from_path,
    shares_from_dicts,
    unique_share_names,
    validate_share,
)
from rdpstudio.tools.share_server import (
    DEFAULT_PORT,
    SftpShareServer,
    ShareServerConfig,
    ShareServerError,
    ShareService,
    ensure_host_key,
    hash_password,
    key_fingerprint,
    verify_password,
)

pytestmark = [pytest.mark.regression]

PASSWORD = "correct-horse-battery-staple"


# ----------------------------------------------------------------------
# fixtures
# ----------------------------------------------------------------------
@pytest.fixture()
def share_tree(tmp_path: Path) -> dict[str, Path]:
    tools = tmp_path / "tools"
    builds = tmp_path / "builds"
    tools.mkdir()
    builds.mkdir()
    (tools / "setup.exe").write_bytes(b"MZ" + b"x" * 2048)
    (builds / "app.msi").write_text("installer payload")
    return {"root": tmp_path, "tools": tools, "builds": builds}


@pytest.fixture()
def registry(share_tree) -> ShareRegistry:
    reg = ShareRegistry()
    reg.set_global([Share("Tools", str(share_tree["tools"])), Share("Builds", str(share_tree["builds"]))])
    return reg


@pytest.fixture()
def server(home, registry, tmp_path):
    """A live listener on an ephemeral port, always stopped afterwards."""
    config = ShareServerConfig(
        bind="127.0.0.1",
        port=0,
        username="kbshare",
        password_hash=hash_password(PASSWORD),
        host_key_path=str(tmp_path / "share_host_key"),
    )
    srv = SftpShareServer(config, registry)
    srv.start()
    yield srv
    srv.stop()


def _connect(srv, username="kbshare", password=PASSWORD):
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    host, port = srv.address()
    client.connect(
        host,
        port=port,
        username=username,
        password=password,
        look_for_keys=False,
        allow_agent=False,
        timeout=15,
        auth_timeout=15,
        banner_timeout=15,
    )
    return client


# ----------------------------------------------------------------------
# share names + validation
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_share_names_are_sanitised_and_never_path_components():
    assert sanitize_share_name("My Tools") == "My_Tools"
    assert sanitize_share_name("../../etc") == "etc"
    assert sanitize_share_name("...") == "share"
    assert sanitize_share_name("") == "share"
    assert len(sanitize_share_name("x" * 500)) == 64
    assert share_name_from_path("/srv/build artefacts") == "build_artefacts"
    assert share_name_from_path("/") == "share"


@pytest.mark.unit
def test_validate_share_rejects_unusable_definitions(share_tree):
    ok = validate_share(Share("Tools", str(share_tree["tools"])))
    assert ok.path == str(share_tree["tools"])

    with pytest.raises(ShareError):
        validate_share(Share("", str(share_tree["tools"])))
    with pytest.raises(ShareError):
        validate_share(Share("a/b", str(share_tree["tools"])))
    with pytest.raises(ShareError):
        validate_share(Share("Tools", ""))
    with pytest.raises(ShareError):
        validate_share(Share("Tools", "relative/path"))
    with pytest.raises(ShareError):
        validate_share(Share("Tools", str(share_tree["tools"] / "missing")))
    with pytest.raises(ShareError):
        validate_share(Share("Tools", str(share_tree["tools"] / "setup.exe")))


@pytest.mark.unit
def test_shares_from_dicts_survives_hand_edited_json(share_tree):
    raw = [
        {"name": "Tools", "path": str(share_tree["tools"])},
        {"name": "", "path": "/tmp"},  # dropped: no name
        "nonsense",  # dropped: not an object
        {"path": "/tmp"},  # dropped: no name
        {"name": "No Path"},  # dropped: no path
    ]
    out = shares_from_dicts(raw)
    assert [s.name for s in out] == ["Tools"]
    assert shares_from_dicts("nope") == []
    assert shares_from_dicts(None) == []


@pytest.mark.unit
def test_unique_share_names_are_suffixed():
    existing = [Share("Tools", "/a"), Share("Tools-2", "/b")]
    assert unique_share_names(existing, "Builds") == "Builds"
    assert unique_share_names(existing, "Tools") == "Tools-3"


# ----------------------------------------------------------------------
# registry: scopes, collisions, dynamic updates
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_registry_merges_global_and_session_shares(registry, share_tree):
    entries = registry.entries()
    assert [(e.name, e.scope) for e in entries] == [
        ("Tools", SCOPE_GLOBAL),
        ("Builds", SCOPE_GLOBAL),
    ]

    registry.set_session("s1", "win10", [Share("Extra", str(share_tree["root"]))])
    assert [(e.name, e.scope, e.source) for e in registry.entries()][2] == (
        "Extra",
        SCOPE_SESSION,
        "win10",
    )

    registry.remove_session("s1")
    assert len(registry.entries()) == 2


@pytest.mark.unit
def test_registry_collisions_are_suffixed_not_dropped(registry, share_tree):
    registry.set_session("s1", "win10", [Share("Tools", str(share_tree["root"]))])
    names = [e.name for e in registry.entries()]
    assert names == ["Tools", "Builds", "Tools-2"]


@pytest.mark.unit
def test_disabled_shares_are_not_offered(registry, share_tree):
    registry.set_global([Share("Tools", str(share_tree["tools"]), enabled=False)])
    assert registry.entries() == []
    assert registry.by_name("Tools") is None


# ----------------------------------------------------------------------
# path jail (CWE-22 / CWE-59)
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_resolve_maps_client_paths_into_the_share(registry, share_tree):
    share, real = registry.resolve("/Tools/setup.exe")
    assert share.name == "Tools"
    assert real == share_tree["tools"] / "setup.exe"

    share, real = registry.resolve("/Tools")
    assert real == share_tree["tools"]

    # unknown share and nonsense paths resolve to nothing
    assert registry.resolve("/Nope/x") is None
    assert registry.resolve("/") is None
    assert registry.resolve("") is None


@pytest.mark.unit
def test_resolve_refuses_traversal_and_symlink_escapes(registry, share_tree):
    for evil in (
        "/Tools/../../etc/passwd",
        "/Tools/../../../etc/shadow",
        "/../etc/passwd",
        "/Tools/./../../etc/hosts",
    ):
        assert registry.resolve(evil) is None, evil

    link = share_tree["tools"] / "escape"
    link.symlink_to("/etc")
    assert registry.resolve("/Tools/escape") is None
    assert registry.resolve("/Tools/escape/passwd") is None


@pytest.mark.unit
def test_resolve_allows_nested_paths_inside_a_share(registry, share_tree):
    nested = share_tree["tools"] / "sub" / "deep"
    nested.mkdir(parents=True)
    share, real = registry.resolve("/Tools/sub/deep")
    assert real == nested
    # a not-yet-existing target inside the share is still resolvable (create)
    assert registry.resolve("/Tools/new.txt")[1] == share_tree["tools"] / "new.txt"


# ----------------------------------------------------------------------
# password hashing + config
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_password_hash_roundtrip_is_salted_and_verified():
    stored = hash_password(PASSWORD)
    assert stored.startswith("pbkdf2-sha256$")
    assert verify_password(PASSWORD, stored)
    assert not verify_password("wrong", stored)
    assert not verify_password("", stored)
    # a different salt each time, so identical passwords do not look alike
    assert hash_password(PASSWORD) != stored
    # garbage / hostile stored values fail closed
    for bad in ("", None, "nonsense", "pbkdf2-sha256$10$a$b", "pbkdf2-sha256$notanint$!!$!!"):
        assert not verify_password(PASSWORD, bad)
    with pytest.raises(ValueError):
        hash_password("")


@pytest.mark.unit
def test_share_config_coerces_garbage():
    config = ShareServerConfig.from_dict(
        {"port": "nonsense", "username": "  lab  ", "bind": "", "max_connections": 999}
    )
    assert config.port == DEFAULT_PORT
    assert config.username == "lab"
    assert config.bind == "0.0.0.0"
    assert config.max_connections == 16
    assert ShareServerConfig.from_dict("junk").port == DEFAULT_PORT
    assert not ShareServerConfig().has_password()


@pytest.mark.unit
def test_host_key_is_persisted_0600_and_stable(home, tmp_path):
    key_path = tmp_path / "keys" / "share_host_key"
    first = ensure_host_key(key_path)
    if os.name == "posix":
        assert oct(os.stat(key_path).st_mode & 0o777) == "0o600"
    second = ensure_host_key(key_path)
    assert key_fingerprint(first) == key_fingerprint(second)
    assert key_fingerprint(first).startswith("SHA256:")


# ----------------------------------------------------------------------
# server lifecycle
# ----------------------------------------------------------------------
@pytest.mark.integration
def test_server_refuses_to_start_without_a_password(home, registry, tmp_path):
    srv = SftpShareServer(
        ShareServerConfig(bind="127.0.0.1", port=0, host_key_path=str(tmp_path / "k")), registry
    )
    with pytest.raises(ShareServerError, match="password"):
        srv.start()
    assert not srv.running


@pytest.mark.integration
def test_second_listener_on_the_same_port_reports_an_actionable_error(server, registry):
    host, port = server.address()
    other = SftpShareServer(
        ShareServerConfig(
            bind=host,
            port=port,
            password_hash=hash_password(PASSWORD),
            host_key_path=str(Path(server.config.host_key_path)),
        ),
        registry,
    )
    with pytest.raises(ShareServerError, match="already in use"):
        other.start()
    assert not other.running
    assert server.running  # the original listener is untouched


@pytest.mark.integration
def test_bind_to_a_foreign_address_is_explained(home, registry, tmp_path):
    srv = SftpShareServer(
        ShareServerConfig(
            bind="203.0.113.7",
            port=0,
            password_hash=hash_password(PASSWORD),
            host_key_path=str(tmp_path / "k"),
        ),
        registry,
    )
    with pytest.raises(ShareServerError, match="not on this machine"):
        srv.start()


# ----------------------------------------------------------------------
# live transfers
# ----------------------------------------------------------------------
@pytest.mark.integration
def test_client_sees_one_directory_per_share(server):
    client = _connect(server)
    try:
        sftp = client.open_sftp()
        assert sorted(e.filename for e in sftp.listdir_attr("/")) == ["Builds", "Tools"]
        assert sorted(sftp.listdir("/Tools")) == ["setup.exe"]
        stat = sftp.stat("/Tools/setup.exe")
        assert stat.st_size == 2050
    finally:
        client.close()


@pytest.mark.integration
def test_upload_download_rename_delete_round_trip(server, share_tree):
    client = _connect(server)
    try:
        sftp = client.open_sftp()

        with sftp.open("/Tools/setup.exe", "rb") as handle:
            downloaded = handle.read()
        assert downloaded[:2] == b"MZ" and len(downloaded) == 2050

        with sftp.open("/Tools/notes.txt", "wb") as handle:
            handle.write(b"from windows\r\n")
        # byte-exact: read_text() would silently normalise the CRLF
        assert (share_tree["tools"] / "notes.txt").read_bytes() == b"from windows\r\n"

        sftp.mkdir("/Builds/release")
        sftp.rename("/Tools/notes.txt", "/Builds/release/notes.txt")
        assert (share_tree["builds"] / "release" / "notes.txt").exists()

        sftp.remove("/Builds/release/notes.txt")
        sftp.rmdir("/Builds/release")
        assert not (share_tree["builds"] / "release").exists()

        # a POSIX rename may clobber; a plain rename may not
        (share_tree["tools"] / "a.txt").write_text("a")
        (share_tree["tools"] / "b.txt").write_bytes(b"b")
        with pytest.raises(OSError):
            sftp.rename("/Tools/a.txt", "/Tools/b.txt")
        sftp.posix_rename("/Tools/a.txt", "/Tools/b.txt")
        assert (share_tree["tools"] / "b.txt").read_bytes() == b"a"
    finally:
        client.close()

    kinds = {event.kind for event in server.events()}
    assert {"auth", "put", "get", "delete", "rename"} <= kinds


@pytest.mark.integration
def test_traversal_and_symlink_are_refused_over_the_wire(server, share_tree):
    client = _connect(server)
    try:
        sftp = client.open_sftp()
        for evil in ("/Tools/../../etc/passwd", "/../etc/shadow"):
            with pytest.raises(OSError):
                sftp.listdir(evil)
        with pytest.raises(OSError):
            sftp.symlink("/etc/passwd", "/Tools/evil")
        with pytest.raises(OSError):
            sftp.readlink("/Tools")
        assert not (share_tree["tools"] / "evil").exists()
    finally:
        client.close()


@pytest.mark.integration
def test_only_the_sftp_subsystem_is_served(server):
    import paramiko

    client = _connect(server)
    try:
        channel = client.get_transport().open_session()
        with pytest.raises(paramiko.SSHException):
            channel.exec_command("whoami")
        with pytest.raises(paramiko.SSHException):
            client.invoke_shell()
        assert any("refused exec request" in e.detail for e in server.events())
    finally:
        client.close()


@pytest.mark.integration
def test_wrong_password_and_user_are_rejected(server):
    import paramiko

    for username, password in (("kbshare", "wrong"), ("someone", PASSWORD), ("kbshare", "")):
        with pytest.raises(paramiko.AuthenticationException):
            _connect(server, username, password)
    kinds = [event.detail for event in server.events() if event.kind == "auth"]
    assert any("rejected" in detail for detail in kinds)


@pytest.mark.integration
def test_read_only_shares_refuse_writes(home, share_tree, tmp_path):
    registry = ShareRegistry()
    registry.set_global([Share("Tools", str(share_tree["tools"]))], writable=False)
    config = ShareServerConfig(
        bind="127.0.0.1",
        port=0,
        username="kbshare",
        password_hash=hash_password(PASSWORD),
        host_key_path=str(tmp_path / "ro_key"),
        allow_write=False,
    )
    srv = SftpShareServer(config, registry)
    srv.start()
    try:
        client = _connect(srv)
        sftp = client.open_sftp()
        with pytest.raises(OSError):
            sftp.open("/Tools/new.txt", "wb").write(b"x")
        with pytest.raises(OSError):
            sftp.remove("/Tools/setup.exe")
        assert (share_tree["tools"] / "setup.exe").exists()
        # reading still works
        with sftp.open("/Tools/setup.exe", "rb") as handle:
            assert handle.read(2) == b"MZ"
        client.close()
    finally:
        srv.stop()


@pytest.mark.integration
def test_shares_appear_live_while_a_client_is_connected(server, share_tree):
    client = _connect(server)
    try:
        sftp = client.open_sftp()
        assert "Extra" not in sftp.listdir("/")

        extra = share_tree["root"] / "extra"
        extra.mkdir()
        (extra / "payload.bin").write_bytes(b"data")
        server.registry.set_session("s1", "win10", [Share("Extra", str(extra))])

        assert "Extra" in sftp.listdir("/")
        with sftp.open("/Extra/payload.bin", "rb") as handle:
            assert handle.read() == b"data"

        server.registry.remove_session("s1")
        assert "Extra" not in sftp.listdir("/")
    finally:
        client.close()


@pytest.mark.integration
def test_stopping_the_server_drops_clients(server):
    client = _connect(server)
    sftp = client.open_sftp()
    assert sftp.listdir("/")
    server.stop()
    assert not server.running
    with pytest.raises(OSError):
        sftp.listdir("/")
    client.close()
    server.start()  # restartable
    try:
        assert server.running
    finally:
        server.stop()


@pytest.mark.integration
def test_connection_limit_is_enforced(home, registry, tmp_path):
    import paramiko

    srv = SftpShareServer(
        ShareServerConfig(
            bind="127.0.0.1",
            port=0,
            username="kbshare",
            password_hash=hash_password(PASSWORD),
            host_key_path=str(tmp_path / "k"),
            max_connections=1,
        ),
        registry,
    )
    srv.start()
    clients = []
    try:
        clients.append(_connect(srv))
        assert srv.connection_count() == 1
        # Force the "limit reached" branch: the next client is dropped before
        # the SSH banner, so it fails during the handshake.
        srv._register = lambda conn: False
        with pytest.raises(paramiko.SSHException):
            _connect(srv)
        assert any("limit reached" in e.detail for e in srv.events())
        assert srv.connection_count() == 1  # the refused client is not counted
    finally:
        for client in clients:
            client.close()
        srv.stop()


# ----------------------------------------------------------------------
# settings + session persistence
# ----------------------------------------------------------------------
@pytest.mark.unit
def test_settings_carry_share_server_configuration():
    from rdpstudio.core.settings import Settings

    settings = Settings()
    settings.share_server_enabled = True
    settings.share_server_port = 2200
    settings.share_server_user = "lab"
    settings.share_server_shares = [{"name": "Tools", "path": "/tmp"}]
    restored = Settings.from_dict(settings.to_dict())
    assert restored.share_server_enabled is True
    assert restored.share_server_port == 2200
    assert restored.share_server_user == "lab"
    assert restored.share_server_shares == [{"name": "Tools", "path": "/tmp", "enabled": True}]

    # hand-edited garbage must not crash startup
    junk = Settings.from_dict(
        {
            "share_server_port": "abc",
            "share_server_user": None,
            "share_server_bind": "",
            "share_server_shares": {"not": "a list"},
        }
    )
    assert junk.share_server_port == DEFAULT_PORT
    assert junk.share_server_user == "kbshare"
    assert junk.share_server_bind == "0.0.0.0"
    assert junk.share_server_shares == []


@pytest.mark.unit
def test_session_stores_its_own_shares():
    from rdpstudio.core.models import Session

    session = Session(protocol="rdp", host="win10", rdp_shares=[Share("Tools", "/srv/tools")])
    restored = Session.from_dict(session.to_dict())
    assert [(s.name, s.path) for s in restored.rdp_shares] == [("Tools", "/srv/tools")]
    assert Session.from_dict({"protocol": "rdp"}).rdp_shares == []


# ----------------------------------------------------------------------
# service (settings <-> registry <-> listener)
# ----------------------------------------------------------------------
@pytest.mark.integration
def test_service_publishes_session_shares_and_starts_on_demand(home, share_tree):
    from rdpstudio.core.settings import Settings

    settings = Settings()
    settings.share_server_enabled = True
    settings.share_server_port = 0
    settings.share_server_bind = "127.0.0.1"
    settings.share_server_shares = [{"name": "Tools", "path": str(share_tree["tools"])}]
    service = ShareService(settings)
    service.set_password(PASSWORD)
    assert not service.server.running

    service.publish_session("s1", "win10", [Share("Builds", str(share_tree["builds"]))])
    assert [e.name for e in service.registry.entries()] == ["Tools", "Builds"]
    assert service.ensure_running() is True
    assert service.server.running

    service.forget_session("s1")
    assert [e.name for e in service.registry.entries()] == ["Tools"]
    service.stop()
    assert not service.server.running

    # autostart off ⇒ ensure_running is a no-op
    settings.share_server_enabled = False
    settings.share_server_autostart = False
    assert service.ensure_running() is False
    assert not service.server.running


@pytest.mark.integration
def test_service_settings_round_trip(home, share_tree):
    from rdpstudio.core.settings import Settings

    settings = Settings()
    service = ShareService(settings)
    service.server.config.port = 2299
    service.server.config.username = "lab"
    service.server.config.allow_write = False
    service.set_global_shares([Share("Builds", str(share_tree["builds"]))])
    service.save_settings()

    assert settings.share_server_port == 2299
    assert settings.share_server_user == "lab"
    assert settings.share_server_writable is False
    assert settings.share_server_shares[0]["name"] == "Builds"

    fresh = ShareService(Settings.from_dict(settings.to_dict()))
    assert fresh.server.config.port == 2299
    assert [s.name for s in fresh.global_shares()] == ["Builds"]
    assert fresh.server.config.allow_write is False


@pytest.mark.integration
def test_snapshot_describes_the_live_state(home, share_tree):
    from rdpstudio.core.settings import Settings

    settings = Settings()
    settings.share_server_port = 0
    settings.share_server_bind = "127.0.0.1"
    service = ShareService(settings)
    service.set_password(PASSWORD)
    service.set_global_shares([Share("Tools", str(share_tree["tools"]))])
    service.start()
    try:
        snap = service.snapshot()
        assert snap["running"] is True
        assert snap["username"] == "kbshare"
        assert [s["name"] for s in snap["shares"]] == ["Tools"]
        assert snap["command"].startswith("sftp -P ")
        assert snap["winscp"].startswith("sftp://kbshare@")
        assert snap["fingerprint"].startswith("SHA256:")
    finally:
        service.stop()


# ----------------------------------------------------------------------
# UI + RDP wiring
# ----------------------------------------------------------------------
@pytest.mark.gui
def test_share_dialog_lists_shares_and_controls_the_listener(qtapp, home, share_tree):
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.share_server_dialog import ShareServerDialog

    settings = Settings()
    settings.share_server_port = 0
    settings.share_server_bind = "127.0.0.1"
    service = ShareService(settings)
    service.set_password(PASSWORD)
    service.set_global_shares([Share("Tools", str(share_tree["tools"]))])

    dialog = ShareServerDialog(service)
    try:
        dialog.refresh()
        assert dialog.table.rowCount() == 1
        assert "Stopped" in dialog.status_line.text()
        assert dialog.btn_toggle.text().strip().startswith("Start")

        dialog._toggle()  # start
        assert service.server.running
        dialog.refresh()
        assert "Running" in dialog.status_line.text()
        assert dialog.btn_toggle.text().strip().startswith("Stop")
        assert dialog.cmd_edit.text().startswith("sftp -P ")

        dialog._toggle()  # stop
        assert not service.server.running
    finally:
        dialog._timer.stop()
        service.stop()
        dialog.close()


@pytest.mark.gui
def test_share_dialog_separates_global_and_session_shares(qtapp, home, share_tree):
    from rdpstudio.core.models import PROTOCOL_RDP, Session
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.share_server_dialog import ShareServerDialog

    service = ShareService(Settings())
    service.set_global_shares([Share("Tools", str(share_tree["tools"]))])
    session = Session(protocol=PROTOCOL_RDP, host="win10", rdp_shares=[Share("Builds", str(share_tree["builds"]))])

    dialog = ShareServerDialog(service, session=session)
    try:
        dialog.refresh()
        assert dialog.table.rowCount() == 2
        scopes = [dialog.table.item(row, 2).text() for row in range(dialog.table.rowCount())]
        assert scopes == ["all machines", "this machine only"]

        # untick the session share; only that one changes
        from PySide6.QtCore import Qt

        tick = dialog.table.item(1, 3)
        tick.setCheckState(Qt.CheckState.Unchecked)
        dialog._commit_table()
        assert service.global_shares()[0].enabled is True
        assert session.rdp_shares[0].enabled is False
    finally:
        dialog._timer.stop()
        dialog.close()


@pytest.mark.gui
def test_rdp_controller_publishes_and_forgets_its_shares(qtapp, home, share_tree, tmp_path):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import PROTOCOL_RDP, Session
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.protocols.rdp.session import RdpSessionController
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    settings = Settings()
    settings.share_server_port = 0
    settings.share_server_bind = "127.0.0.1"
    settings.share_server_enabled = True
    service = ShareService(settings)
    service.set_password(PASSWORD)
    ctx = SessionContext(
        settings=settings,
        store=SessionStore(tmp_path / "sessions.json"),
        vault=None,
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
        share_service=service,
    )
    session = Session(
        protocol=PROTOCOL_RDP,
        host="10.0.0.9",
        username="lab",
        password="pw",
        rdp_shares=[Share("Builds", str(share_tree["builds"]))],
    )
    controller = RdpSessionController(session, ctx)
    try:
        controller._publish_shares()
        assert [e.name for e in service.registry.entries()] == ["Builds"]
        assert service.server.running  # enabled ⇒ the listener came up

        controller._unpublish_shares()
        assert service.registry.entries() == []
    finally:
        service.stop()
        controller.deleteLater()


@pytest.mark.gui
def test_rdp_capabilities_advertise_file_sharing(qtapp, home, tmp_path):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import PROTOCOL_RDP, Session
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.protocols.rdp.session import RdpSessionController
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(tmp_path / "sessions.json"),
        vault=None,
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    controller = RdpSessionController(Session(protocol=PROTOCOL_RDP, host="win10"), ctx)
    try:
        caps = controller.capabilities()
        assert caps.file_sharing is True
        assert caps.sftp is False  # RDP still has no SFTP channel of its own
    finally:
        controller.deleteLater()


@pytest.mark.gui
def test_rdp_tab_offers_a_share_button(qtapp, home, tmp_path):
    """The RDP tab header must expose the share manager (the entry point users click)."""
    from PySide6.QtWidgets import QPushButton

    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import PROTOCOL_RDP, Session
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.ui.main_window import MainWindow
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(tmp_path / "sessions.json"),
        vault=None,
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    main = MainWindow(ctx)
    try:
        session = Session(protocol=PROTOCOL_RDP, host="10.0.0.9", username="lab", password="pw")
        ctx.store.upsert(session)
        tab = main.open_session(ctx.store.get(session.id))
        labels = [b.text() for b in tab.findChildren(QPushButton)]
        assert "Share" in labels

        # ...and it opens the manager for that machine
        share_btn = next(b for b in tab.findChildren(QPushButton) if b.text() == "Share")
        share_btn.click()
        dialog = getattr(main, "_share_dialog", None)
        assert dialog is not None and dialog.session.id == session.id
        dialog._timer.stop()
        dialog.close()
    finally:
        main.close()


@pytest.mark.gui
def test_session_dialog_edits_rdp_shares(qtapp, home, share_tree, tmp_path):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.models import PROTOCOL_RDP, Session
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.ui.prompter import HeadlessPromptProvider
    from rdpstudio.ui.session_dialog import SessionDialog

    ctx = SessionContext(
        settings=Settings(),
        store=SessionStore(tmp_path / "sessions.json"),
        vault=None,
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )
    session = Session(
        protocol=PROTOCOL_RDP,
        host="win10",
        rdp_shares=[Share("Builds", str(share_tree["builds"]))],
    )
    dialog = SessionDialog(ctx, session)
    try:
        assert dialog.share_list.count() == 1
        dialog.share_list.setCurrentRow(0)
        dialog._remove_shared_folder()
        collected = dialog._collect_session()
        assert collected.rdp_shares == []
    finally:
        dialog.close()


@pytest.mark.gui
def test_settings_dialog_exposes_share_defaults(qtapp, home, share_tree, tmp_path):
    from rdpstudio.core.settings import Settings
    from rdpstudio.ui.settings_dialog import SettingsDialog

    settings = Settings()
    settings.share_server_port = 2211
    settings.share_server_user = "lab"
    settings.share_server_shares = [{"name": "Tools", "path": str(share_tree["tools"])}]
    dialog = SettingsDialog(settings)
    try:
        assert dialog.share_port.value() == 2211
        assert dialog.share_user.text() == "lab"
        assert dialog.share_folders.count() == 1
        dialog._save()
        assert settings.share_server_port == 2211
        assert settings.share_server_shares[0]["path"] == str(share_tree["tools"])
    finally:
        dialog.close()
