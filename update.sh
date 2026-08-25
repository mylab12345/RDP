#!/usr/bin/env bash
# KB-Remote — clean rebuild and refresh the local installation.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${KB_REMOTE_VENV:-${RDPSTUDIO_VENV:-$HOME/.kb-remote/venv}}"
PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ ! -x "$PIP" || ! -x "$PYTHON" ]]; then
  say "Virtualenv missing; running the project installer"
  "$ROOT_DIR/install.sh"
fi

[[ -x "$PIP" && -x "$PYTHON" ]] || die "Python virtualenv is unavailable: $VENV_DIR"

say "Removing Python, test, lint, and stale build caches"
find "$ROOT_DIR" -type d \( \
  -name __pycache__ -o \
  -name .pytest_cache -o \
  -name .ruff_cache -o \
  -name '*.egg-info' \
\) -prune -exec rm -rf {} +
rm -rf "$ROOT_DIR/build/lib" "$ROOT_DIR/dist"
find "$ROOT_DIR/build" -maxdepth 1 -type d -name 'bdist.*' -prune -exec rm -rf {} + 2>/dev/null || true

say "Force-reinstalling KB-Remote from current source"
"$PIP" install --quiet --force-reinstall --no-deps -e "$ROOT_DIR"

say "Verifying installed source"
installed_path="$($PYTHON -c 'import rdpstudio.protocols.rdp.session as m; print(m.__file__)')"
case "$installed_path" in
  "$ROOT_DIR"/src/rdpstudio/*) printf 'source=%s\n' "$installed_path" ;;
  *) die "installed module resolved outside this checkout: $installed_path" ;;
esac

launcher="${KB_REMOTE_BIN:-${RDPSTUDIO_BIN:-$HOME/.local/bin}}/kb-remote"
if [[ -x "$launcher" ]]; then
  say "Smoke-testing $launcher"
  set +e
  QT_QPA_PLATFORM=offscreen timeout 5s "$launcher" >/tmp/kb-remote-update.log 2>&1
  launch_code=$?
  set -e
  [[ "$launch_code" -eq 124 ]] || {
    cat /tmp/kb-remote-update.log
    die "KB-Remote failed to launch (exit $launch_code)"
  }
else
  say "Launcher not found at $launcher; package rebuild succeeded"
fi

say "Update complete"
