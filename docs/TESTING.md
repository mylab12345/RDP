# Testing guide

KB-Remote uses `pytest` for unit, integration, GUI, and regression tests and
Ruff for static checks. Tests must isolate application state through
`KB_REMOTE_HOME`; the shared `home` fixture does this automatically.

## Set up

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

Linux GUI tests need the runtime libraries required by Qt's offscreen plugin.
On Debian/Ubuntu CI these arrive with the normal desktop/Qt dependencies; a
minimal container may additionally need packages such as `libgl1`, `libegl1`,
`libxkbcommon0`, and `libdbus-1-3`. Live SSH integration tests need
`openssh-server`; they skip when `sshd` is unavailable.

## Standard verification

```bash
# Complete suite, including Qt tests and local-sshd integration when available
QT_QPA_PLATFORM=offscreen python -m pytest tests

# Static checks
ruff check src tests scripts

# Reinstall the editable application, verify its import path, and boot it
# offscreen; --all also requests tests and lint.
./update.sh --all
```

The repository `Makefile` provides equivalent `make test` and `make lint`
targets. CI runs the complete suite on supported Python boundary versions and
builds the Linux PyInstaller artifact.

## Test layers

Markers are registered in `pyproject.toml`:

| Marker | Purpose | Typical dependencies |
|---|---|---|
| `unit` | One pure function/class with injected I/O | none outside Python packages |
| `integration` | Multiple stores, processes, sockets, or a real sshd | filesystem/network/process |
| `gui` | QWidget/controller behavior | `QApplication`, offscreen/native Qt |
| `regression` | A previously identified failure mode | whichever layer owns the defect |

New tests should carry all applicable markers. The older suite predates marker
registration and is being categorized incrementally, so `-m unit` is currently
a focused subset rather than an alias for every fast existing test.

Examples:

```bash
pytest -m unit
pytest -m 'regression and not gui'
pytest -m integration
```

## Suite organization

- `test_core_persistence.py`: atomic-write failure injection and cross-store
  persistence integration.
- `test_state_validation.py`: corrupt settings/session/vault regression cases.
- `test_rdp_client.py`: pure FreeRDP/mstsc command and certificate policy.
- `test_architecture_boundaries.py`: subprocess import checks preventing Qt
  coupling in pure protocol helpers.
- `test_network_scanner_bounded.py`: queue bounds, cancellation, callback
  isolation.
- `test_store_import_safety.py`: id/name conflicts and ownership isolation.
- Existing `test_ssh_integration.py` exercises real SSH/SFTP/tunnel behavior;
  RDP embedded/XWayland tests use deterministic stand-in processes and injected
  support probes.

## Writing stable tests

1. **Test behavior, not implementation details.** Private attributes are
   acceptable only where they define a threading/process safety invariant that
   has no public observation point.
2. **Inject external effects.** Client discovery, sockets, subprocesses,
   clocks, and filesystem failures should be monkeypatched at the module where
   they are used.
3. **Never use the developer's state.** Use `tmp_path` and/or the `home`
   fixture. Do not read the real vault, SSH config, or known-hosts file.
4. **Bound every wait.** Prefer Qt signals/events. If a process/thread must be
   observed, use a deadline and fail with actionable diagnostics.
5. **Clean secrets and processes in `finally`.** Argument files, fake clients,
   sockets, QThreads, and sshd instances must not survive a failed assertion.
6. **Pin regressions narrowly.** The test name/docstring should describe the
   former failure and make the security or lifecycle invariant obvious.
7. **Keep pure modules pure.** Import-boundary tests should run in a fresh
   subprocess so earlier test imports cannot hide accidental PySide coupling.

## Manual release checks

Offscreen tests cannot validate OS compositor/client integration. Before a
release, exercise:

- Linux X11: embedded FreeRDP keyboard, mouse, resize, sidebar toggle, stop,
  reconnect, and certificate first-use/change flows.
- Linux Wayland: XWayland relaunch success and external-window fallback.
- Windows: mstsc `.rdp` generation, certificate-warning policy, ConPTY fallback,
  installer, and app shutdown with active sessions.
- SSH: password/key/agent auth, changed host key rejection, jump chain, SFTP,
  local/remote/SOCKS forwarding, reconnect, and closing the app under load.
- Persistence: upgrade with existing `sessions.json`, `settings.json`, vault,
  snippets, and known-hosts files; simulate a read-only/full state directory.

Record environment versions and results in the release notes. Platform failures
must not be converted into blanket `except`/skip behavior without a tracked
issue and a pure fallback test.
