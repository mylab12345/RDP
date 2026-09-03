#!/usr/bin/env bash
#
# build-appimage.sh — build a self-contained KB-Remote AppImage for Linux.
#
# Produces: dist/KB-Remote-<version>-linux-<arch>.AppImage
#
# Requirements (installed automatically in CI, or by you locally):
#   - python3, pyinstaller
#   - linuxdeploy + linuxdeploy-plugin-qt (https://github.com/linuxdeploy)
#   - appimagetool (https://github.com/AppImage/appimagetool)
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 -c 'from rdpstudio import __version__; print(__version__)')"
ARCH="$(uname -m)"

TOOLSDIR="${APPDIR_TOOLSDIR:-$HOME/.cache/appimage-tools}"
APPID="io.github.mylab12345.KBRemote"
APPDIR="dist/AppDir"

fetch() { # fetch <url> <dest>
  local url="$1" dest="$2"
  if [ ! -f "$dest" ]; then
    mkdir -p "$(dirname "$dest")"
    echo "Fetching $(basename "$dest")..."
    curl -L --fail --retry 3 -o "$dest" "$url"
    chmod +x "$dest"
  fi
}

mkdir -p "$TOOLSDIR"
fetch "https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-$ARCH.AppImage" "$TOOLSDIR/linuxdeploy"
fetch "https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-$ARCH.AppImage" "$TOOLSDIR/linuxdeploy-plugin-qt"
fetch "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-$ARCH.AppImage" "$TOOLSDIR/appimagetool"

echo "==> Building PyInstaller bundle"
rm -rf build dist/AppDir dist/KB-Remote
python3 -m PyInstaller --noconfirm packaging/rdpstudio.spec

echo "==> Assembling AppDir"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps" \
         "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
         "$APPDIR/usr/share/metainfo"

cp -r dist/KB-Remote/* "$APPDIR/usr/bin/"
cp packaging/linux/io.github.mylab12345.KBRemote.desktop "$APPDIR/usr/share/applications/"
cp packaging/linux/io.github.mylab12345.KBRemote.metainfo.xml "$APPDIR/usr/share/metainfo/"
cp src/rdpstudio/resources/icons/logo.svg "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APPID.svg"
cp src/rdpstudio/resources/icons/logo.png "$APPDIR/usr/share/icons/hicolor/512x512/apps/$APPID.png"

echo "==> linuxdeploy (bundle Qt deps)"
LINUXDEPLOY_OUTPUT_VERSION="$VERSION" \
  "$TOOLSDIR/linuxdeploy" --appdir "$APPDIR" \
  -e "dist/KB-Remote/kb-remote" \
  -d "$APPDIR/usr/share/applications/io.github.mylab12345.KBRemote.desktop" \
  -i "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APPID.svg" \
  --plugin qt

echo "==> appimagetool"
OUT="dist/KB-Remote-$VERSION-linux-$ARCH.AppImage"
"$TOOLSDIR/appimagetool" --appimage-extract-and-run "$APPDIR" "$OUT"

echo "==> Done: $OUT"
