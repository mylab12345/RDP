"""UI robustness tests: Command Palette, Terminal Search, Snippets, Editor & Tools dialogs."""

from __future__ import annotations

import pytest

from rdpstudio.core.models import Session
from rdpstudio.core.plugin import SessionContext
from rdpstudio.ui.cluster_dialog import ClusterDialog
from rdpstudio.ui.command_palette import CommandPaletteDialog
from rdpstudio.ui.file_editor_dialog import FileEditorDialog
from rdpstudio.ui.key_utility_dialog import KeyUtilityDialog
from rdpstudio.ui.main_window import MainWindow
from rdpstudio.ui.network_tools_dialog import NetworkToolsDialog
from rdpstudio.ui.snippets_panel import SnippetsPanel
from rdpstudio.ui.terminal import TerminalView

pytestmark = pytest.mark.usefixtures("home")


def _ctx(home, qtapp):
    from rdpstudio.core.events import EventBus
    from rdpstudio.core.settings import Settings
    from rdpstudio.core.store import SessionStore
    from rdpstudio.core.vault import CredentialVault
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    store = SessionStore(home / "sessions.json")
    vault = CredentialVault(home / "vault.bin", kdf_iterations=60_000)
    settings = Settings()
    bus = EventBus()
    prompter = HeadlessPromptProvider()
    return SessionContext(store=store, vault=vault, settings=settings, bus=bus, prompter=prompter)


def test_terminal_search_bar_and_matches(home, qtapp):
    ctx = _ctx(home, qtapp)
    term = TerminalView(ctx.settings)
    term.show()
    term.feed(b"Line 1: error in module A\r\nLine 2: warning in module B\r\nLine 3: error in module C\r\n")

    term.open_search()
    assert not term.search_bar.isHidden()

    term.search_bar.input.setText("error")
    assert len(term._search_matches) >= 2
    assert term._search_current_idx == 0

    term.search_bar.findNext.emit("error", False)
    assert term._search_current_idx == 1

    term.search_bar.close_bar()
    assert term.search_bar.isHidden()
    term.close()


def test_terminal_session_logging(home, qtapp, tmp_path):
    ctx = _ctx(home, qtapp)
    term = TerminalView(ctx.settings)
    log_file = tmp_path / "test-session.log"

    term.start_logging(log_file)
    assert term.is_logging()
    assert term.log_path() == log_file

    term.feed(b"Hello logged terminal output\r\n")
    term.stop_logging()
    assert not term.is_logging()

    content = log_file.read_text(encoding="utf-8")
    assert "Hello logged terminal output" in content
    assert "Session Log Started" in content
    term.close()


def test_command_palette_navigation(home, qtapp):
    ctx = _ctx(home, qtapp)
    ctx.store.upsert(Session(name="Prod Web 1", protocol="ssh", host="10.0.0.10"))
    ctx.store.upsert(Session(name="DB Slave", protocol="ssh", host="10.0.0.20"))

    main = MainWindow(ctx)
    main.show()
    dlg = CommandPaletteDialog(main)
    assert dlg.list.count() > 0

    # Search filter
    dlg._on_search("Prod Web")
    assert dlg.list.count() >= 1
    dlg._on_search("Network")
    assert dlg.list.count() >= 1

    dlg.close()
    main.close()


def test_snippets_panel_standalone(home, qtapp):
    ctx = _ctx(home, qtapp)
    main = MainWindow(ctx)
    main.show()
    panel = SnippetsPanel(main)

    assert panel.tree.topLevelItemCount() > 0
    panel.search.setText("Uptime")
    assert panel.tree.topLevelItemCount() > 0
    assert not hasattr(main, "snippets_panel")

    panel.close()
    main.close()


def test_removed_power_tools_are_not_in_chrome(home, qtapp):
    ctx = _ctx(home, qtapp)
    main = MainWindow(ctx)
    main.show()
    texts = []
    for action in main.menuBar().actions():
        menu = action.menu()
        if menu is None:
            continue
        for child in menu.actions():
            texts.append((child.text() or "").replace("&", "").lower())
    blob = " | ".join(texts)
    assert "broadcast" not in blob
    assert "snippet" not in blob
    assert "vault" not in blob
    assert "port forwarding" not in blob
    assert "parallel" not in blob
    toolbar_tips = " ".join(a.toolTip().lower() for a in main.findChildren(type(main.menuBar().actions()[0])))
    assert "broadcast" not in toolbar_tips
    main.close()


def test_file_editor_dialog(home, qtapp):
    saved_payload = None

    def on_save(path, data):
        nonlocal saved_payload
        saved_payload = data

    editor = FileEditorDialog(
        "/etc/nginx/nginx.conf",
        initial_content=b"server { listen 80; }",
        is_remote=True,
        on_save=on_save,
    )
    assert "nginx.conf" in editor.windowTitle()
    editor.editor.setPlainText("server { listen 443 ssl; }")
    editor._on_save_clicked()
    assert saved_payload == b"server { listen 443 ssl; }"
    editor.close()


def test_network_tools_and_key_utility_dialogs(home, qtapp):
    ctx = _ctx(home, qtapp)
    main = MainWindow(ctx)
    main.show()

    net_dlg = NetworkToolsDialog(main)
    assert "Port Scanner" in net_dlg.windowTitle()
    net_dlg.close()

    cluster_dlg = ClusterDialog(ctx, main)
    assert "Parallel" in cluster_dlg.windowTitle()
    cluster_dlg.close()

    key_dlg = KeyUtilityDialog(ctx, main)
    assert "Key Utility" in key_dlg.windowTitle()
    key_dlg.close()

    main.close()
