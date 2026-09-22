"""Production-readiness hardening: CLI contract, quiet logging, state chip.

Covers the changes from the production-readiness pass:
- ``app.parse_cli`` — pure flag parsing (repeatable -v/--verbose, -q, any order)
- ``log.setup_logging(quiet=...)`` — console-only WARNING, file log keeps detail
- MainWindow status-bar state chip — live state of the current tab, STANDBY
  reset when no tab is open, protocol-aware window title
"""

from __future__ import annotations

import logging

import pytest


# --- app.parse_cli --------------------------------------------------------------
@pytest.mark.unit
def test_parse_cli_empty():
    from rdpstudio.app import parse_cli

    assert parse_cli([]) == (0, [])


@pytest.mark.unit
def test_parse_cli_flag_positions_are_irrelevant():
    from rdpstudio.app import parse_cli

    verbose, targets = parse_cli(["-v", "user@host", "--verbose"])
    assert verbose == 2
    assert targets == ["user@host"]


@pytest.mark.unit
def test_parse_cli_quiet_wins_when_mixed():
    from rdpstudio.app import parse_cli

    verbose, targets = parse_cli(["-v", "-q", "user@host:2222"])
    assert verbose == 0
    assert targets == ["user@host:2222"]
    verbose, _ = parse_cli(["-q", "-q", "-v"])
    assert verbose == -1


@pytest.mark.unit
def test_parse_cli_unknown_args_stay_positional():
    from rdpstudio.app import parse_cli

    verbose, targets = parse_cli(["--frobnicate", "sess-1"])
    assert verbose == 0
    assert targets == ["--frobnicate", "sess-1"]


# --- setup_logging(quiet=...) ----------------------------------------------------
@pytest.fixture()
def fresh_logging(tmp_path, monkeypatch):
    """Give setup_logging a private logger namespace and a clean config flag."""
    import rdpstudio.core.log as logmod

    monkeypatch.setattr(logmod, "_configured", False)
    monkeypatch.setattr(logmod, "_LOGGER_NAME", "rdpstudio.test-fresh")
    yield logmod
    root = logging.getLogger("rdpstudio.test-fresh")
    for handler in list(root.handlers):
        root.removeHandler(handler)


@pytest.mark.unit
def test_setup_logging_quiet_keeps_file_detail(fresh_logging, tmp_path):
    logmod = fresh_logging
    logmod.setup_logging(tmp_path, verbose=False, quiet=True)

    root = logging.getLogger("rdpstudio.test-fresh")
    console = next(
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.handlers.RotatingFileHandler)
    )
    file_handler = next(
        h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
    )
    assert console.level == logging.WARNING
    assert file_handler.level == logging.NOTSET  # file keeps INFO detail
    assert root.level == logging.INFO


@pytest.mark.unit
def test_setup_logging_verbose_and_default(fresh_logging, tmp_path):
    logmod = fresh_logging
    logmod.setup_logging(tmp_path, verbose=True, quiet=False)
    root = logging.getLogger("rdpstudio.test-fresh")
    console = next(
        h
        for h in root.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.handlers.RotatingFileHandler)
    )
    assert root.level == logging.DEBUG
    assert console.level == logging.NOTSET


# --- MainWindow state chip -------------------------------------------------------
@pytest.fixture()
def ctx(home, qtapp):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.plugin import SessionContext
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    return SessionContext(
        settings=Settings(),
        store=SessionStore(home / "sessions.json"),
        vault=CredentialVault(home / "vault.bin"),
        bus=EventBus(),
        prompter=HeadlessPromptProvider(),
    )


@pytest.mark.gui
def test_state_chip_starts_standby_and_resets_without_tabs(ctx, qtapp):
    from PySide6.QtWidgets import QMessageBox

    from rdpstudio.ui import main_window
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    # No tabs: chip is dim STANDBY and the title is the plain app name
    assert win.state_chip.text() == "STANDBY"
    assert win.windowTitle() == "KB-Remote"

    # Close-confirm path is stubbed so a blocked close can't open a dialog
    monkey = pytest.MonkeyPatch()
    monkey.setattr(
        main_window.MainWindow,
        "_safe_to_close",
        lambda self, tab: True,
    )
    monkey.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    try:
        win._update_state_chip(None)
        assert win.state_chip.text() == "STANDBY"
        assert win.windowTitle() == "KB-Remote"
    finally:
        monkey.undo()
    win.close()
    qtapp.processEvents()


@pytest.mark.gui
def test_state_chip_follows_current_tab_state(ctx, qtapp):
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    tab = win.open_local_terminal()
    qtapp.processEvents()
    assert tab is not None

    # Local sessions update the chip but must not pollute the window title
    tab.controller.set_state("connected")
    assert "CONNECTED" in win.state_chip.text()
    assert win.windowTitle() == "KB-Remote"

    # A background tab's state must not leak into the chip
    defn = Session(protocol=PROTOCOL_LOCAL)
    other = win.open_session(defn)
    qtapp.processEvents()
    if other is not None and other is not tab:
        win.tabs.setCurrentWidget(tab)
        qtapp.processEvents()
        assert "CONNECTED" in win.state_chip.text()

    tab.controller.stop("test over")
    qtapp.processEvents()
    win.close()


@pytest.mark.gui
def test_state_chip_swithes_with_tab_selection(ctx, qtapp):
    """The chip mirrors the *current* tab: switching tabs re-syncs it."""
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    first = win.open_local_terminal()
    second = win.open_session(Session(protocol=PROTOCOL_LOCAL))
    qtapp.processEvents()
    if first is None or second is None:
        pytest.skip("local terminal tabs unavailable")

    first.controller.set_state("connected")
    second.controller.set_state("closed")
    win.tabs.setCurrentWidget(second)
    qtapp.processEvents()
    assert "CLOSED" in win.state_chip.text()

    win.tabs.setCurrentWidget(first)
    qtapp.processEvents()
    assert "CONNECTED" in win.state_chip.text()

    for t in (second, first):
        t.controller.stop("test over")
    win.close()


@pytest.mark.unit
def test_store_delete_rolls_back_on_save_failure(tmp_path, monkeypatch):
    """close_tab's teardown guard depends on delete() keeping memory == disk."""
    from rdpstudio.core.models import Session
    from rdpstudio.core.store import SessionStore

    path = tmp_path / "sessions.json"
    store = SessionStore(path)
    s = Session(name="x", protocol="ssh", host="h")
    store.upsert(s)

    def broken_write(_text):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_atomic_write", broken_write)
    with pytest.raises(OSError):
        store.delete(s.id)
    # in-memory state must still hold the session (disk unchanged too)
    assert store.get(s.id) is not None


# --- transactional upsert (REL-04) ----------------------------------------------
@pytest.mark.unit
def test_store_upsert_insert_rolls_back_on_save_failure(tmp_path, monkeypatch):
    """A failed save during a *new* session must not leave it in memory."""
    from rdpstudio.core.models import Session
    from rdpstudio.core.store import SessionStore

    store = SessionStore(tmp_path / "sessions.json")

    def broken_write(_text):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_atomic_write", broken_write)
    with pytest.raises(OSError):
        store.upsert(Session(name="fresh", protocol="ssh", host="h"))
    assert store.sessions() == []
    # the store still works after the failed write
    monkeypatch.undo()
    recovered = Session(name="after", protocol="ssh", host="h2")
    store.upsert(recovered)
    assert store.get(recovered.id) is not None


@pytest.mark.unit
def test_store_upsert_update_rolls_back_on_save_failure(tmp_path, monkeypatch):
    """A failed save during an *edit* must restore the previous session."""
    from rdpstudio.core.models import Session
    from rdpstudio.core.store import SessionStore

    path = tmp_path / "sessions.json"
    store = SessionStore(path)
    original = Session(name="prod", protocol="ssh", host="10.0.0.1")
    store.upsert(original)
    before = store.get(original.id)

    edited = store.get(original.id)
    edited.host = "10.0.0.99"

    def broken_write(_text):
        raise OSError("disk full")

    monkeypatch.setattr(store, "_atomic_write", broken_write)
    with pytest.raises(OSError):
        store.upsert(edited)
    # memory must still match what is on disk
    current = store.get(original.id)
    assert current.host == before.host == "10.0.0.1"
    # and the on-disk copy is untouched
    reloaded = SessionStore(path)
    assert reloaded.get(original.id).host == "10.0.0.1"


# --- connect_session returns the tab (sidebar Connect & SFTP) --------------------
@pytest.mark.gui
def test_connect_session_returns_open_tab(ctx, qtapp):
    """_connect_and_sftp chains on the return value; it must not always be None."""
    from rdpstudio.core.models import PROTOCOL_LOCAL, Session
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    try:
        defn = Session(protocol=PROTOCOL_LOCAL, name="term")
        ctx.store.upsert(defn)
        tab = win.connect_session(defn.id)
        qtapp.processEvents()
        assert tab is not None
        assert win.tabs.indexOf(tab) >= 0
        # unknown id → None
        assert win.connect_session("no-such-id") is None
    finally:
        win.close()
        qtapp.processEvents()


# --- vault auto-lock is wired to the Settings value -------------------------------
@pytest.mark.gui
def test_autolock_locks_vault_after_inactivity(ctx, qtapp):
    """The 30 s _autolock timer honours vault_autolock_minutes (previously a no-op)."""
    from rdpstudio.ui.main_window import MainWindow

    win = MainWindow(ctx)
    try:
        vault = ctx.vault
        vault.create("master-pw")
        assert vault.unlocked is True

        # Disabled (0 min): stays unlocked
        ctx.settings.vault_autolock_minutes = 0
        win._autolock()
        assert vault.unlocked is True

        # 15 min idle threshold with fresh activity: stays unlocked
        ctx.settings.vault_autolock_minutes = 15
        win._autolock()
        assert vault.unlocked is True

        # Idle beyond the threshold: locks
        vault.last_activity -= 16 * 60  # simulate 16 minutes of inactivity
        win._autolock()
        assert vault.unlocked is False
    finally:
        win.close()
        qtapp.processEvents()
