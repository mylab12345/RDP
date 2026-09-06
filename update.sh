#!/usr/bin/env bash
# KB-Remote — rebuild and refresh the local installation from this checkout.
#
# Idempotent and self-healing: safe to run after every source change. Before
# rebuilding it repairs the damage left behind by past `sudo pip` runs that
# would otherwise break the rebuild or make pip print warnings on every
# invocation:
#   - root-owned / unwritable src/*.egg-info ("Cannot update time stamp")
#   - `~`-prefixed broken-distribution dirs in site-packages
#     ("WARNING: Ignoring invalid distribution")
# Neither can be deleted without sudo, and a root-owned directory cannot even
# be renamed across parent directories — but renaming within the same parent
# only needs write access to that parent, which the current user owns. The
# junk is therefore renamed in place to a name no tool scans again; a hint
# shows how to purge it with sudo.
#
# Steps:
#   1. self-heal install damage (see above) and unwritable tool caches
#   2. clear stale Python / test / build caches
#   3. force-reinstall the app (editable) into the venv
#   4. verify the installed code resolves to this checkout
#   5. boot check — construct the main window offscreen
#   6. optional: lint (--lint) and tests (--test); missing dev tools are
#      installed on demand so they never turn into "module not found"
#
# Usage:
#   ./update.sh             rebuild + verify + boot check
#   ./update.sh --test      also run the test suite (offscreen)
#   ./update.sh --lint      also run ruff over src/ tests/ scripts/
#   ./update.sh --all       tests + lint as well
#   ./update.sh --no-test   accepted for compatibility (tests are opt-in)
#   ./update.sh --help
set -euo pipefail

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
KB-Remote update — rebuild and refresh the local installation.

Usage:
  ./update.sh             rebuild + verify + boot check
  ./update.sh --test      also run the test suite (offscreen)
  ./update.sh --lint      also run ruff over src/ tests/ scripts/
  ./update.sh --all       tests + lint as well
  ./update.sh --no-test   accepted for compatibility (tests are opt-in)
  ./update.sh --help      show this help
EOF
}

# run_with_timeout <seconds> <command...> — fall back to a plain run when
# GNU timeout is unavailable.
run_with_timeout() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "$1" "${@:2}"
  else
    "${@:2}"
  fi
}

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
RUN_TESTS=0
RUN_LINT=0
for arg in "$@"; do
  case "$arg" in
    --test)    RUN_TESTS=1 ;;
    --lint)    RUN_LINT=1 ;;
    --all)     RUN_TESTS=1; RUN_LINT=1 ;;
    --no-test) ;; # tests are opt-in; kept so old invocations keep working
    --help|-h) usage; exit 0 ;;
    *) die "unknown option: $arg (try --help)" ;;
  esac
done

# ---------------------------------------------------------------------------
# Resolve the virtualenv: $KB_REMOTE_VENV / $RDPSTUDIO_VENV, then the
# canonical user venv, then the project .venv. If none exists, bootstrap
# with the project installer.
# ---------------------------------------------------------------------------
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${KB_REMOTE_VENV:-${RDPSTUDIO_VENV:-$HOME/.kb-remote/venv}}"
if [ ! -x "$VENV_DIR/bin/python" ] && [ -x "$ROOT_DIR/.venv/bin/python" ]; then
  VENV_DIR="$ROOT_DIR/.venv"
fi
if [ ! -x "$VENV_DIR/bin/python" ]; then
  say "No virtualenv found — creating one with install.sh"
  "$ROOT_DIR/install.sh"
fi

PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"
if [ ! -x "$PYTHON" ] || [ ! -x "$PIP" ]; then
  die "virtualenv is incomplete: $VENV_DIR"
fi

TRASH="$(mktemp -d /tmp/kb-remote-update.XXXXXX)"
LOG="$(mktemp /tmp/kb-remote-update.XXXXXX.log)"
trap 'rm -rf "$TRASH" "$LOG" 2>/dev/null || true' EXIT

# ---------------------------------------------------------------------------
# 1. Self-heal: `~`-prefixed broken-distribution leftovers in site-packages
#    (from interrupted or sudo pip runs) make every pip command print
#    "Ignoring invalid distribution" warnings. Renaming them in place to a
#    "*.quarantined" name keeps them out of every scanner; the rename stays
#    inside site-packages so no cross-directory permission is needed.
# ---------------------------------------------------------------------------
SITE_PKGS="$(find "$VENV_DIR/lib" -maxdepth 3 -type d -name site-packages -print -quit 2>/dev/null || true)"
if [ -n "$SITE_PKGS" ]; then
  fixed=0
  for leftover in "$SITE_PKGS"/~*.dist-info "$SITE_PKGS"/~*.egg-info; do
    if [ ! -e "$leftover" ]; then continue; fi
    # Unique suffix: pip can recreate a same-named tombstone later (its
    # uninstall renames "r..." to "~..."), and mv cannot overwrite a
    # previous, undeletable quarantine directory.
    target="$leftover.quarantined-$(date +%Y%m%d%H%M%S)-$$"
    if mv "$leftover" "$target" 2>/dev/null; then
      fixed=$((fixed + 1))
    else
      say "Could not quarantine $leftover — remove it with: sudo rm -rf $leftover"
    fi
  done
  if [ "$fixed" -gt 0 ]; then
    say "Quarantined $fixed broken pip leftover(s)"
    say "Purge them anytime with: sudo rm -rf $SITE_PKGS/~*.quarantined*"
  fi
fi

# ---------------------------------------------------------------------------
# 2. Self-heal: an egg-info directory this user cannot write (typically
#    root-owned from a past `sudo pip install`) breaks the editable rebuild
#    with "Cannot update time stamp". Renaming it in place to
#    "stale-<timestamp>-<name>.egg-info" clears the way for pip — setuptools
#    only manages the exact "<name>.egg-info", and *.egg-info/ is already
#    gitignored. The stale- prefix keeps later runs from touching it again.
# ---------------------------------------------------------------------------
for egg in "$ROOT_DIR"/src/*.egg-info; do
  if [ ! -d "$egg" ]; then continue; fi
  base="$(basename "$egg")"
  case "$base" in stale-*) continue ;; esac
  if [ -w "$egg" ]; then continue; fi
  target="$ROOT_DIR/src/stale-$(date +%Y%m%d%H%M%S)-$base"
  if mv "$egg" "$target" 2>/dev/null; then
    say "Quarantined unwritable $base (it was blocking the rebuild)"
    say "Purge it anytime with: sudo rm -rf $target"
  else
    die "cannot clear $egg — remove it with: sudo rm -rf $egg"
  fi
done

# ---------------------------------------------------------------------------
# 3. Self-heal: unwritable tool cache directories in the repo (typically
#    root-owned .pytest_cache / .ruff_cache from a past sudo run) make the
#    tools warn "could not write" on every use. Rename aside to a *.log name
#    (already gitignored); the tools recreate fresh user-owned caches.
# ---------------------------------------------------------------------------
for cache in "$ROOT_DIR/.pytest_cache" "$ROOT_DIR/.ruff_cache"; do
  if [ -d "$cache" ] && [ ! -w "$cache" ]; then
    target="$ROOT_DIR/$(basename "$cache").stale-$(date +%Y%m%d%H%M%S)-$$.log"
    if mv "$cache" "$target" 2>/dev/null; then
      say "Quarantined unwritable $(basename "$cache") (it was blocking tool caches)"
      say "Purge it anytime with: sudo rm -rf $target"
    else
      say "Could not quarantine $cache — remove it with: sudo rm -rf $cache"
    fi
  fi
done

# ---------------------------------------------------------------------------
# 4. Remove stale caches and build artifacts
# ---------------------------------------------------------------------------
say "Clearing stale caches"
find "$ROOT_DIR/src" "$ROOT_DIR/tests" "$ROOT_DIR/scripts" \
  -type d \( -name __pycache__ -o -name '*.egg-info' \) -prune \
  -exec rm -rf {} + 2>/dev/null || true
rm -rf "$ROOT_DIR/.pytest_cache" "$ROOT_DIR/.ruff_cache" \
  "$ROOT_DIR/build/lib" "$ROOT_DIR/dist" 2>/dev/null || true
find "$ROOT_DIR/build" -maxdepth 1 -type d -name 'bdist.*' \
  -exec rm -rf {} + 2>/dev/null || true

# ---------------------------------------------------------------------------
# 5. Reinstall from current source into the venv
# ---------------------------------------------------------------------------
say "Reinstalling KB-Remote into $VENV_DIR"
if ! "$PIP" install --quiet --no-input --disable-pip-version-check \
        --force-reinstall --no-deps -e "$ROOT_DIR" 2>"$LOG"; then
  cat "$LOG" >&2
  say "Retrying verbosely for full diagnostics"
  "$PIP" install --no-input --force-reinstall --no-deps -e "$ROOT_DIR" \
    || die "pip reinstall failed"
fi

# ---------------------------------------------------------------------------
# 6. Verify the installed module resolves to this checkout
# ---------------------------------------------------------------------------
say "Verifying installed code"
if ! installed_path="$("$PYTHON" -c 'import rdpstudio.ui.main_window as m; print(m.__file__)' 2>/dev/null)"; then
  die "rdpstudio is not importable from $VENV_DIR — run $ROOT_DIR/install.sh"
fi
case "$installed_path" in
  "$ROOT_DIR"/src/rdpstudio/*) ;;
  *) die "installed module resolved outside this checkout: $installed_path" ;;
esac
printf '    %s\n' "$installed_path"

# ---------------------------------------------------------------------------
# 7. Boot check — construct the main window offscreen and run the event loop
# ---------------------------------------------------------------------------
say "Boot check (offscreen)"
cat > "$TRASH/boot_check.py" <<'PYEOF'
import tempfile
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from rdpstudio.core.events import EventBus
from rdpstudio.core.plugin import SessionContext
from rdpstudio.core.settings import Settings
from rdpstudio.core.store import SessionStore
from rdpstudio.core.vault import CredentialVault
from rdpstudio.ui.main_window import MainWindow
from rdpstudio.ui.prompter import HeadlessPromptProvider

d = Path(tempfile.mkdtemp())
ctx = SessionContext(settings=Settings(), store=SessionStore(d / "sessions.json"),
                     vault=CredentialVault(d / "vault.bin"), bus=EventBus(),
                     prompter=HeadlessPromptProvider())
app = QApplication([])
win = MainWindow(ctx)
QTimer.singleShot(1500, app.quit)
app.exec()
win.close()
print("boot OK")
PYEOF
if ! QT_QPA_PLATFORM=offscreen run_with_timeout 30 "$PYTHON" "$TRASH/boot_check.py" >"$LOG" 2>&1; then
  cat "$LOG" >&2
  die "boot check failed"
fi

# ---------------------------------------------------------------------------
# 8. Lint (opt-in: --lint / --all). ruff is installed on demand so a missing
#    tool never turns into a "module not found" dead end.
# ---------------------------------------------------------------------------
if [ "$RUN_LINT" = "1" ]; then
  say "Lint (ruff)"
  "$PIP" install --quiet --no-input --disable-pip-version-check "ruff>=0.5" \
    || die "could not install ruff into $VENV_DIR"
  "$VENV_DIR/bin/ruff" check "$ROOT_DIR/src" "$ROOT_DIR/tests" "$ROOT_DIR/scripts"
fi

# ---------------------------------------------------------------------------
# 9. Tests (opt-in: --test / --all). pytest and pytest-timeout are installed
#    on demand (the timeout plugin also silences the "Unknown config option:
#    timeout" warning from pyproject). Known pre-existing failures are listed
#    in AGENTS.md and do not block the rebuild.
# ---------------------------------------------------------------------------
if [ "$RUN_TESTS" = "1" ]; then
  say "Tests (offscreen)"
  "$PIP" install --quiet --no-input --disable-pip-version-check \
      "pytest>=8" "pytest-timeout>=2.3" \
    || die "could not install pytest/pytest-timeout into $VENV_DIR"
  if ! QT_QPA_PLATFORM=offscreen run_with_timeout 600 "$PYTHON" -m pytest "$ROOT_DIR/tests"; then
    say "pytest reported failures (see summary above; known pre-existing failures are listed in AGENTS.md)"
  fi
fi

say "Update complete — restart KB-Remote to use the updated code."
