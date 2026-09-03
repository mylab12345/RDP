#!/usr/bin/env bash
#
# install-universal.sh — install KB-Remote on any Linux distribution.
#
# Detects your distro and package manager, checks dependencies, then installs
# via the most portable path available, in this order:
#   1. AppImage  (default, when a release artifact is reachable)
#   2. Flatpak   (via Flathub, if --flatpak)
#   3. Snap      (via Snapcraft, if --snap)
#   4. pip/venv  (fallback local install from this checkout)
#
# Usage:
#   curl -fsSL <URL>/install-universal.sh | bash
#   bash install-universal.sh                 # auto (AppImage first)
#   bash install-universal.sh --appimage      # force AppImage
#   bash install-universal.sh --flatpak       # force Flatpak/Flathub
#   bash install-universal.sh --snap          # force Snap
#   bash install-universal.sh --pip           # force pip/venv fallback
#   bash install-universal.sh --version 0.9.0 # pin a version (default: latest)
#
set -euo pipefail

# ---- configuration ---------------------------------------------------------
GITHUB_OWNER="mylab12345"
GITHUB_REPO="RDP"
VERSION="${KB_REMOTE_VERSION:-}"
MODE="${KB_REMOTE_MODE:-auto}"
INSTALL_DIR="${KB_REMOTE_INSTALL_DIR:-$HOME/.local/kb-remote}"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
ICON_PNG_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

for arg in "$@"; do
  case "$arg" in
    --appimage) MODE="appimage" ;;
    --flatpak)  MODE="flatpak" ;;
    --snap)     MODE="snap" ;;
    --pip)      MODE="pip" ;;
    --version)  shift; VERSION="${1:-}" ;;
    --help|-h)
      sed -n '2,20p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) die "unknown option: $arg (see --help)" ;;
  esac
done

arch="$(uname -m)"
case "$arch" in
  x86_64) appimage_arch="x86_64" ;;
  aarch64|arm64) appimage_arch="aarch64" ;;
  *) appimage_arch="$arch" ;;
esac

# ---- dependency checks -----------------------------------------------------
have() { command -v "$1" >/dev/null 2>&1; }

require_python() {
  have python3 || die "python3 not found (need 3.10+) — install it first."
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
    || die "python3 is older than 3.10"
}

# Resolve the latest release version from the GitHub API when not pinned.
resolve_version() {
  if [ -n "$VERSION" ]; then return; fi
  if have curl; then
    VERSION="$(curl -fsSL "https://api.github.com/repos/$GITHUB_OWNER/$GITHUB_REPO/releases/latest" \
      | grep -m1 '"tag_name"' | sed 's/.*"tag_name": *"//; s/".*//' | tr -d 'v' || true)"
  fi
  VERSION="${VERSION:-0.9.0}"
}

# ---- mode 1: AppImage ------------------------------------------------------
install_appimage() {
  resolve_version
  require_python
  mkdir -p "$INSTALL_DIR"
  local url
  url="https://github.com/$GITHUB_OWNER/$GITHUB_REPO/releases/download/v${VERSION}/KB-Remote-${VERSION}-linux-${appimage_arch}.AppImage"
  local appimage="$INSTALL_DIR/KB-Remote.AppImage"
  say "Downloading AppImage $VERSION ($appimage_arch)"
  if ! curl -LfsS --retry 3 -o "$appimage" "$url"; then
    say "AppImage download failed; falling back."
    return 1
  fi
  chmod +x "$appimage"
  ln -sf "$appimage" "$INSTALL_DIR/kb-remote"
  ln -sf "$appimage" "$HOME/.local/bin/kb-remote" 2>/dev/null || true
  desktop_entry "$HOME/.local/bin/kb-remote"
  say "AppImage installed. Start with:  kb-remote"
  return 0
}

# ---- mode 2: Flatpak -------------------------------------------------------
install_flatpak() {
  if ! have flatpak; then
    die "flatpak not installed. Install it via your package manager, then add Flathub:"
    die "  flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo"
  fi
  say "Installing KB-Remote from Flathub"
  flatpak install --user -y flathub io.github.mylab12345.KBRemote
  say "Installed. Start with:  flatpak run io.github.mylab12345.KBRemote"
}

# ---- mode 3: Snap ----------------------------------------------------------
install_snap() {
  if ! have snap; then
    die "snapd not detected. Enable Snap support first, e.g.:  sudo apt install snapd"
  fi
  say "Installing KB-Remote from Snapcraft"
  sudo snap install kb-remote
  say "Installed. Start with:  kb-remote"
}

# ---- mode 4: pip/venv fallback ---------------------------------------------
install_pip() {
  require_python
  if [ -f ./install.sh ]; then
    say "Using bundled local installer (pip/venv)"
    bash ./install.sh
  else
    say "No bundled installer; installing from PyPI into a private venv"
    local venv="$HOME/.kb-remote/venv"
    python3 -m venv "$venv"
    "$venv/bin/pip" install --quiet --upgrade pip
    "$venv/bin/pip" install --quiet "rdp-studio"
    mkdir -p "$HOME/.local/bin"
    cat > "$HOME/.local/bin/kb-remote" <<EOF
#!/bin/sh
exec "$venv/bin/kb-remote" "\$@"
EOF
    chmod +x "$HOME/.local/bin/kb-remote"
    desktop_entry "$HOME/.local/bin/kb-remote"
    say "Installed. Start with:  kb-remote"
  fi
}

# ---- shared: desktop entry -------------------------------------------------
install_icon() {
  mkdir -p "$ICON_DIR" "$ICON_PNG_DIR"
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "$here/src/rdpstudio/resources/icons/logo.svg" ]; then
    cp "$here/src/rdpstudio/resources/icons/logo.svg" "$ICON_DIR/io.github.mylab12345.KBRemote.svg"
  fi
  if [ -f "$here/src/rdpstudio/resources/icons/logo.png" ]; then
    cp "$here/src/rdpstudio/resources/icons/logo.png" "$ICON_PNG_DIR/io.github.mylab12345.KBRemote.png"
  fi
}

desktop_entry() {
  local exec_path="$1"
  mkdir -p "$DESKTOP_DIR" "$ICON_DIR" "$ICON_PNG_DIR"
  install_icon
  cat > "$DESKTOP_DIR/kb-remote.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=KB-Remote
GenericName=Remote Access Workbench
Comment=SSH and RDP sessions with tunnels, vault and file transfer
Exec=$exec_path
Icon=io.github.mylab12345.KBRemote
Terminal=false
Categories=Network;RemoteAccess;System;Utility;
Keywords=ssh;sftp;rdp;remote;terminal;tunnel;
StartupWMClass=kb-remote
EOF
  chmod +x "$DESKTOP_DIR/kb-remote.desktop"
  update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
}

# ---- run -------------------------------------------------------------------
case "$MODE" in
  appimage) install_appimage ;;
  flatpak)  install_flatpak ;;
  snap)     install_snap ;;
  pip)      install_pip ;;
  auto)
    if install_appimage; then
      :
    else
      install_pip
    fi
    ;;
esac

echo
say "Done. Start KB-Remote with:  kb-remote"
