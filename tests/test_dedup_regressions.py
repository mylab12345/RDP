"""Regressions for the bugs uncovered while de-duplicating shared code.

Each test here pins behaviour that was either wrong or silently duplicated
before the shared helpers in ``core.naming``, ``ui.session_log``,
``ui.paste_guard`` and ``ui.file_filters`` were introduced.
"""

from __future__ import annotations

import pytest

# ----------------------------------------------------------------------
# core.naming — one numbering convention for copies and imports
# ----------------------------------------------------------------------


def test_unique_name_appends_suffix_when_free():
    from rdpstudio.core.naming import unique_name

    assert unique_name("Web", set()) == "Web (copy)"
    assert unique_name("Web", set(), "imported") == "Web (imported)"


def test_unique_name_numbers_upwards_past_collisions():
    from rdpstudio.core.naming import unique_name

    taken = {"Web (copy)", "Web (copy 2)", "Web (copy 3)"}
    assert unique_name("Web", taken) == "Web (copy 4)"


def test_unique_name_accepts_any_iterable():
    """Callers pass generators; membership must still be checked."""
    from rdpstudio.core.naming import unique_name

    assert unique_name("Web", (n for n in ["Web (copy)"])) == "Web (copy 2)"


def test_store_and_snippets_share_the_import_convention(tmp_path):
    from rdpstudio.core.models import Session
    from rdpstudio.core.store import SessionStore

    store = SessionStore(tmp_path / "sessions.json")
    store.upsert(Session(name="Box", protocol="ssh", host="h"))
    store.import_sessions([Session(name="Box", protocol="ssh", host="h")])
    store.import_sessions([Session(name="Box", protocol="ssh", host="h")])
    names = {s.display_name() for s in store.sessions()}
    assert "Box (imported)" in names
    assert "Box (imported 2)" in names


# ----------------------------------------------------------------------
# ui.file_filters — the export format follows the chosen filter
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "selected", "expected"),
    [
        # The bug: filter says CSV, user typed a bare name -> used to be JSON.
        ("results", "CSV (*.csv)", "results.csv"),
        ("results", "JSON (*.json)", "results.json"),
        # Already correct -> untouched.
        ("results.csv", "CSV (*.csv)", "results.csv"),
        ("RESULTS.CSV", "CSV (*.csv)", "RESULTS.CSV"),
        # A deliberate, different extension is respected.
        ("results.txt", "CSV (*.csv)", "results.txt"),
        # Multi-extension filters accept any of their own types.
        ("out.txt", "Log Files (*.log *.txt)", "out.txt"),
        ("out", "Log Files (*.log *.txt)", "out.log"),
        # Wildcards impose no format.
        ("results", "All files (*)", "results"),
        # A dotted directory must not be mistaken for an extension.
        ("/home/a.b/results", "CSV (*.csv)", "/home/a.b/results.csv"),
        # Cancelled dialog.
        ("", "CSV (*.csv)", ""),
    ],
)
def test_apply_selected_suffix(path, selected, expected):
    from rdpstudio.ui.file_filters import apply_selected_suffix

    assert apply_selected_suffix(path, selected) == expected


# ----------------------------------------------------------------------
# ui.session_log — shared logging, and no leaked file handle
# ----------------------------------------------------------------------


def _make_logger():
    from rdpstudio.ui.session_log import SessionLogMixin

    class L(SessionLogMixin):
        def __init__(self):
            self._log_file = None
            self._log_path = None

    return L()


def test_session_log_round_trip(tmp_path):
    log = _make_logger()
    target = tmp_path / "nested" / "session.log"

    assert not log.is_logging()
    log.start_logging(target)
    assert log.is_logging()
    assert log.log_path() == target

    log._log_output(b"hello\n")
    log.stop_logging()

    assert not log.is_logging()
    assert log.log_path() is None
    text = target.read_text()
    assert "Session Log Started" in text
    assert "Session Log Ended" in text
    assert "hello" in text


def test_session_log_strips_escape_sequences(tmp_path):
    log = _make_logger()
    target = tmp_path / "session.log"
    log.start_logging(target)
    log._log_output(b"\x1b[31mred\x1b[0m \x1b]0;title\x07plain\n")
    log.stop_logging()

    body = target.read_text()
    assert "red plain" in body
    assert "\x1b" not in body


def test_stop_logging_closes_handle_even_if_final_write_fails(tmp_path):
    """The old code closed the file inside the same try as the banner write,
    so a failing write leaked the handle forever."""
    log = _make_logger()
    log.start_logging(tmp_path / "session.log")
    handle = log._log_file

    def boom(_data):
        raise OSError("disk full")

    handle.write = boom
    log.stop_logging()

    assert handle.closed
    assert not log.is_logging()


def test_restarting_logging_closes_the_previous_file(tmp_path):
    log = _make_logger()
    log.start_logging(tmp_path / "one.log")
    first = log._log_file
    log.start_logging(tmp_path / "two.log")

    assert first.closed
    assert log.log_path() == tmp_path / "two.log"
    log.stop_logging()


def test_log_output_is_a_noop_when_not_logging():
    log = _make_logger()
    log._log_output(b"ignored")  # must not raise
    assert not log.is_logging()


# ----------------------------------------------------------------------
# ui.paste_guard — one multi-line paste policy for both terminals
# ----------------------------------------------------------------------


def test_paste_guard_allows_short_single_lines(qtapp):
    from rdpstudio.ui.paste_guard import confirm_multiline_paste, needs_paste_confirmation

    assert not needs_paste_confirmation("ls -la")
    # No dialog is constructed, so this is safe without a parent widget.
    assert confirm_multiline_paste(None, "ls -la", enabled=True)


def test_paste_guard_skipped_when_setting_disabled(qtapp):
    from rdpstudio.ui.paste_guard import confirm_multiline_paste

    assert confirm_multiline_paste(None, "rm -rf /\nreboot\n", enabled=False)


def test_paste_guard_flags_multiline_and_bulk():
    from rdpstudio.ui.paste_guard import PASTE_WARN_CHARS, needs_paste_confirmation

    assert needs_paste_confirmation("a\nb")
    assert needs_paste_confirmation("a\rb")
    assert needs_paste_confirmation("x" * (PASTE_WARN_CHARS + 1))
    assert not needs_paste_confirmation("x" * PASTE_WARN_CHARS)


# ----------------------------------------------------------------------
# SessionDialog — "Save" and "Connect" are no longer the same button
# ----------------------------------------------------------------------


@pytest.fixture()
def dialog_ctx(home, qtapp):
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


def _session_dialog(dialog_ctx):
    from rdpstudio.core.models import Session
    from rdpstudio.ui.session_dialog import SessionDialog

    return SessionDialog(dialog_ctx, Session(name="box", protocol="ssh", host="h", port=22), None)


def test_save_persists_without_requesting_a_connection(dialog_ctx):
    """Previously `Save` and `Connect` ran identical code, so callers could
    not tell them apart and `Save` opened a session the user never asked
    for."""
    dlg = _session_dialog(dialog_ctx)
    assert dlg.connect_requested is False

    dlg._on_save()

    assert dlg.connect_requested is False
    assert [s.name for s in dialog_ctx.store.sessions()] == ["box"]
    dlg.deleteLater()


def test_connect_persists_and_requests_a_connection(dialog_ctx):
    dlg = _session_dialog(dialog_ctx)

    dlg._on_connect()

    assert dlg.connect_requested is True
    assert [s.name for s in dialog_ctx.store.sessions()] == ["box"]
    dlg.deleteLater()


def test_failed_validation_neither_saves_nor_connects(dialog_ctx, monkeypatch):
    dlg = _session_dialog(dialog_ctx)
    monkeypatch.setattr(dlg, "_validate_fields", lambda: False)

    dlg._on_connect()

    assert dlg.connect_requested is False
    assert dialog_ctx.store.sessions() == []
    dlg.deleteLater()
