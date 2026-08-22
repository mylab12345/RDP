#!/usr/bin/env bash
# RDP Studio — Linux installer.
# Creates a private venv, installs the app, adds launcher + .desktop entry.
set -euo pipefail

cd "$(dirname "$0")"

VENV_DIR="${RDPSTUDIO_VENV:-$HOME/.rdpstudio/venv}"
BIN_DIR="${RDPSTUDIO_BIN:-$HOME/.local/bin}"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null || die "python3 not found (need 3.10+)"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
  || die "python3 is older than 3.10"

say "Creating virtualenv in $VENV_DIR"
python3 -m venv "$VENV_DIR" 2>/dev/null || true

say "Installing RDP Studio"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet .

say "Installing launcher to $BIN_DIR"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/rdpstudio" <<EOF
#!/bin/sh
exec "$VENV_DIR/bin/rdpstudio" "\$@"
EOF
chmod +x "$BIN_DIR/rdpstudio"

say "Installing desktop entry"
mkdir -p "$DESKTOP_DIR" "$ICON_DIR"
cp src/rdpstudio/resources/icons/logo.svg "$ICON_DIR/rdpstudio.svg"
cat > "$DESKTOP_DIR/rdpstudio.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=RDP Studio
GenericName=Remote Access Workbench
Comment=SSH and RDP sessions with tunnels, vault and file transfer
Exec=$BIN_DIR/rdpstudio
Icon=rdpstudio
Terminal=false
Categories=Network;RemoteAccess;System;Utility;
Keywords=ssh;sftp;rdp;remote;terminal;tunnel;
StartupWMClass=rdpstudio
EOF
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

if ! command -v xfreerdp >/dev/null && ! command -v sdl-freerdp3 >/dev/null; then
  echo
  say "Note: no FreeRDP client found."
  echo "    For RDP sessions install it with:  sudo apt install freerdp3-x11"
  echo "    (SSH/SFTP features work without it.)"
fi

echo
say "Done. Start with:  rdpstudio"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "    (add $BIN_DIR to your PATH)" ;;
esac
