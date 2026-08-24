# AGENTS.md

## Project
KB-Remote (RDP/SSH/local terminal client, PySide6). Source in `src/rdpstudio`.

## Environment
- venv: `~/.kb-remote/venv` (pytest, ruff installed there)
- App launcher: `~/.local/bin/kb-remote` → venv entry point
- Install is **editable** (`pip install -e .`), so source edits are live on app restart.

## Workflow rules (user requirement)
- After every code change: rebuild/reinstall the app so the running install matches the repo:
  `~/.kb-remote/venv/bin/pip install --quiet --force-reinstall --no-deps -e .`
  Then verify the installed module resolves to the updated code and the app launches.
- Run checks before finishing any change:
  - `QT_QPA_PLATFORM=offscreen ~/.kb-remote/venv/bin/python -m pytest tests`
    (3 known pre-existing failures: test_local_terminal_and_monitor tab-completes,
    test_security_hardening monitor-probe, test_ui_moxa monitor-panel — ignore those)
  - `~/.kb-remote/venv/bin/ruff check src tests scripts`
- Never commit unless explicitly asked.

## Known quirks
- `pyside6_qtermwidget`: `sendData(const char*, int)` cannot marshal into Python;
  keyboard input goes through the event-filter shim in
  `src/rdpstudio/ui/native_terminal.py` (installed on QTermWidget's focus proxy).
