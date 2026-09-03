# KB-Remote Linux distribution & packaging

KB-Remote is packaged for **every major Linux distribution** with portable,
self-contained formats. This directory and the repo root contain everything
needed to build and install it anywhere.

## Formats

| Format | Artifact | Best for |
|---|---|---|
| **AppImage** | `.AppImage` single file | Portable, distro-agnostic, no install; run from anywhere |
| **Flatpak** | `.flatpak` bundle; Flathub | Sandboxed, desktop-integrated, auto-updating |
| **Snap** | `.snap`; Snapcraft | Ubuntu/Canonical ecosystem, auto-updating |
| **pip/venv** | `install.sh` | Developers, minimal systems |

## Quick install (any Linux)

```sh
# Auto path (AppImage first, pip/venv fallback):
curl -fsSL https://github.com/mylab12345/RDP/releases/latest/download/install-universal.sh | bash

# Force a specific backend:
curl -fsSL .../install-universal.sh | bash -s -- --flatpak
curl -fsSL .../install-universal.sh | bash -s -- --snap
curl -fsSL .../install-universal.sh | bash -s -- --appimage
```

After the CI release pipeline runs on a `v*` tag, the AppImage/Flatpak/Snap
artifacts are attached to the GitHub Release and are download-able at:

```
https://github.com/mylab12345/RDP/releases/latest
```

## Building locally

```sh
# AppImage (needs linuxdeploy + appimagetool; or use CI):
bash packaging/linux/build-appimage.sh

# Flatpak (needs flatpak-builder + Flathub remote):
flatpak-builder --user --install --force-clean _build flatpak/io.github.mylab12345.KBRemote.yaml
flatpak run io.github.mylab12345.KBRemote

# Snap (needs snapcraft):
snapcraft
```

The CI workflow `packaging/ci/release-linux.yml` builds all three on every
`v*` tag and attaches them to the release.

## App metadata

- **App ID:** `io.github.mylab12345.KBRemote`
- **Desktop entry:** `packaging/linux/io.github.mylab12345.KBRemote.desktop`
- **AppStream metainfo:** `packaging/linux/io.github.mylab12345.KBRemote.metainfo.xml`
- **Icons:** `src/rdpstudio/resources/icons/logo.svg` / `logo.png`

## Submitting to Flathub

1. Fork [flathub/flathub](https://github.com/flathub/flathub).
2. Create directory `io.github.mylab12345.KBRemote/` containing:
   - `io.github.mylab12345.KBRemote.yaml` (copy of `flatpak/io.github.mylab12345.KBRemote.yaml`)
   - A `sources/` dir with generated tarball + python sources (use
     `flatpak run org.flatpak.Builder --generate-sources` or `flatpak-pip-generator`).
3. Add a screenshot link (already in the metainfo).
4. Open a PR to Flathub. The Flathub CI validates the metainfo, icon, and manifest.

## Submitting to Snapcraft

1. `snapcraft login`
2. `snapcraft register kb-remote` (claim the name)
3. From a release: `snapcraft --remote-build --release=stable`
   (or push the `.snap` built in CI: `snapcraft upload dist/*.snap`)

## Runtime note (RDP)

RDP uses FreeRDP. In AppImage builds the binary is bundled; in the Flatpak it
is built from source; in the Snap it comes from the `freerdp3-x11` package.
**SSH/SFTP work without FreeRDP** — only RDP needs it. The app falls back
gracefully and prints a hint if no RDP client is found.
