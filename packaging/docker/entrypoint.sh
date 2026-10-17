#!/bin/sh
# Container entrypoint for KB-Remote.
#
# - Ensures private state ($KB_REMOTE_HOME) and Qt runtime ($XDG_RUNTIME_DIR)
#   directories exist with 0700 permissions (CWE-276).
# - Falls back to QT_QPA_PLATFORM=offscreen when neither DISPLAY nor
#   WAYLAND_DISPLAY is mounted so CLI/headless invocations do not abort.
set -eu

KB_REMOTE_HOME="${KB_REMOTE_HOME:-${RDPSTUDIO_HOME:-${HOME:-/tmp}/.config/kb-remote}}"
export KB_REMOTE_HOME
mkdir -p "$KB_REMOTE_HOME"
chmod 700 "$KB_REMOTE_HOME" 2>/dev/null || true

XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-kbremote}"
export XDG_RUNTIME_DIR
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null || true

# Treat leading flags (e.g. `docker run kb-remote --version`) as arguments to kb-remote.
if [ "$#" -eq 0 ]; then
  set -- kb-remote
elif [ "${1#-}" != "$1" ]; then
  set -- kb-remote "$@"
fi

case "$1" in
  kb-remote|rdpstudio|*/kb-remote|*/rdpstudio)
    if [ -z "${QT_QPA_PLATFORM:-}" ] && [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
      export QT_QPA_PLATFORM="offscreen"
    fi
    ;;
esac

exec "$@"
