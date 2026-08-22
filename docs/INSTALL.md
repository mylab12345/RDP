# Installation

RDP Studio runs on Linux and Windows, Python 3.10+.

## Linux

### From source (recommended for a checkout)

```bash
./install.sh
```

What it does:

1. creates `~/.rdpstudio/venv` (or reuses it),
2. `pip install .` into that venv,
3. writes `~/.local/bin/rdpstudio` launcher,
4. installs `~/.local/share/applications/rdpstudio.desktop` + icon.

### With pipx / pip

```bash
pipx install .            # isolated, on PATH immediately
# or
python3 -pip install --user .
```

### RDP prerequisites

The **built-in RDP display** (desktop renders inside the app) uses the system
FreeRDP client, and so does the external-window mode:

```bash
sudo apt install freerdp3-x11     # Debian/Ubuntu (freerdp2-x11 also works)
sudo dnf install freerdp          # Fedora
```

Built-in mode additionally needs X11 (it embeds FreeRDP's X11 window with
`/parent-window`), so install the **X11 flavour** (`freerdp3-x11`) — the SDL
client (`sdl-freerdp`) cannot embed.

**Wayland sessions**: no X11 login session needed — RDP Studio restarts itself
through **XWayland** automatically (once, at startup, when saved RDP sessions
exist; otherwise on demand from the RDP tab's *Show inside app* button or
Settings). Set *RDP display → External* if you prefer the native Wayland
window, or start with an explicit `QT_QPA_PLATFORM` to opt out of the restart.
If the xcb platform cannot load in the restarted process, the app falls back
to its native platform and RDP uses the external window.

## Windows

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

- creates `%LOCALAPPDATA%\RDPStudio\venv`, installs the package, adds a
  Start-Menu shortcut.
- RDP uses the built-in `mstsc.exe` — nothing to install.
- optional: `pip install rdp-studio[win]` for ConPTY-backed local shells
  (`pywinpty`).

## From CI artifacts

Every tagged release builds (see `packaging/ci/release.yml` — run
`packaging/ci/install-workflows.sh` once to enable GitHub Actions CI):

- `RDPStudio-<ver>-windows-x64.zip` — standalone PyInstaller bundle
  (+ `RDPStudio-Setup-<ver>.exe` Inno Setup installer built from
  `packaging/windows/RDPStudio.iss`)
- `rdpstudio-<ver>-linux-x86_64.tar.gz` — PyInstaller onedir bundle

## Building packages yourself

```bash
pip install pyinstaller
pyinstaller packaging/rdpstudio.spec          # → dist/RDPStudio/
```

Windows installer: install [Inno Setup](https://jrsoftware.org/isinfo.php)
and compile `packaging/windows/RDPStudio.iss` after the PyInstaller build.

## Uninstall

```bash
rm -rf ~/.rdpstudio ~/.local/bin/rdpstudio ~/.local/share/applications/rdpstudio.desktop
# state (sessions/vault) lives in ~/.config/rdpstudio — remove if desired
```

Windows: delete `%LOCALAPPDATA%\RDPStudio` and the Start-Menu folder; state
lives in `%APPDATA%\RDPStudio`.
