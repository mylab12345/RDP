# Installation

KB-Remote runs on Linux and Windows, Python 3.10+.

## Linux

### From source (recommended for a checkout)

```bash
./install.sh
```

What it does:

1. creates `~/.kb-remote/venv` (or reuses it),
2. `pip install .` into that venv (and, on Python 3.11+ when available, the
   optional native Linux terminal renderer),
3. writes `~/.local/bin/kb-remote` launcher (and keeps a legacy `rdpstudio` alias),
4. installs `~/.local/share/applications/rdpstudio.desktop` + icon.

For the native Linux terminal renderer used by SSH Pilot-style sessions, use
Python 3.11+ and install the optional extra:

```bash
python3 -m pip install --user 'rdp-studio[native-terminal]'
# or, from this checkout:
pipx install '.[native-terminal]'
```

This installs the PySide6 QTermWidget bindings. New local and SSH tabs then
keep PTY/SSH ownership in KB-Remote but delegate VT parsing, scrollback and
painting to the compiled terminal widget. If the wheel is unavailable or its
Qt ABI does not match, the app transparently uses the pyte renderer instead.
Set `RDPSTUDIO_TERMINAL_BACKEND=native` to require the native choice for new
GUI tabs (it still falls back if the binding cannot load), or use
`RDPSTUDIO_TERMINAL_BACKEND=pyte` to force the fallback while diagnosing a
machine. `./install.sh` tries the native extra on Python 3.11+; set
`KB_REMOTE_NATIVE_TERMINAL=0` to skip that optional install.

### With pipx / pip

```bash
pipx install .            # isolated, on PATH immediately
# or
python3 -m pip install --user .
kb-remote
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

**Wayland sessions**: no X11 login session needed — KB-Remote restarts itself
through **XWayland** automatically (once, at startup, when saved RDP sessions
exist; otherwise on demand from the RDP tab's *Show inside app* button or
Settings). Set *RDP display → External* if you prefer the native Wayland
window, or start with an explicit `QT_QPA_PLATFORM` to opt out of the restart.
If the xcb platform cannot load in the restarted process, the app falls back
to its native platform and RDP uses the external window.

## Docker

A multi-stage `Dockerfile` builds a minimal Debian Bookworm image that bundles
all Python dependencies (`PySide6-Essentials`, `paramiko`, `cryptography`,
`pyte`, and the native `pyside6-qtermwidget` terminal renderer) alongside all
system runtime dependencies (FreeRDP X11 client for embedded/external RDP,
OpenSSH client/key tools, X11/XCB, Wayland, OpenGL/EGL, D-Bus, PulseAudio/ALSA,
and DejaVu fonts) while pruning unused Qt addons, WebEngine/3D/QML modules,
translations, headers, and debug symbols (`packaging/docker/prune_venv.py`).

```bash
# Build the image
docker build -t kb-remote:latest .
# or: make docker-build

# Run with X11 forwarding and persistent state (Linux desktop)
xhost +local:docker
docker compose up
# or: make docker-run

# Verify CLI / headless mode without a display
docker run --rm kb-remote:latest --version
```

## Windows

One universal installer covers Windows 10 1809+/11 and Windows Server
2019/2022/2025 (x64, and ARM64 via x64 emulation). Everything needed at run
time — Python, Qt/PySide6 and the SSH/crypto libraries — is bundled, so the
machine needs nothing else and no administrator rights (per-user install).

```powershell
# Universal link — always the newest release, silent install
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/mylab12345/RDP/releases/latest/download/install.ps1 -OutFile $env:TEMP\kbri.ps1; & $env:TEMP\kbri.ps1"
```

Or download
[KB-Remote-Setup.exe](https://github.com/mylab12345/RDP/releases/latest/download/KB-Remote-Setup.exe)
directly (double-click for the wizard), or the double-clickable
[install.cmd](https://github.com/mylab12345/RDP/releases/latest/download/install.cmd).

- Installs to `%LOCALAPPDATA%\Programs\KB-Remote` (or `%ProgramFiles%` when
  run elevated / with `-InstallDir`), with a Start-Menu shortcut.
- RDP uses the built-in `mstsc.exe` — nothing to install.
- Local shells use the bundled ConPTY support (`pywinpty`).
- Options: `-Version X.Y.Z`, `-Interactive`, `-InstallDir <path>`, `-NoLaunch`,
  `-Force`.
- Developer flow from a checkout:
  `powershell -ExecutionPolicy Bypass -File install.ps1 -FromSource` creates a
  venv in the repo and runs `pip install -e ".[win]"`.

See [packaging/windows/README.md](../packaging/windows/README.md) for details
and code-signing.

## From CI artifacts

Every tagged release builds (see `packaging/ci/release.yml` — run
`packaging/ci/install-workflows.sh` once to enable GitHub Actions CI) and
attaches to the GitHub release:

- `KB-Remote-Setup.exe` — universal Windows installer (stable link name)
- `KB-Remote-Setup-<ver>-windows-x64.exe` — versioned copy of the same
- `install.ps1` / `install.cmd` — bootstrap scripts for the universal link
- `KB-Remote-<ver>-windows-x64.zip` — portable PyInstaller bundle
- `KB-Remote-<ver>-linux-x86_64.tar.gz` — PyInstaller onedir bundle

## Building packages yourself

```bash
pip install pyinstaller
pyinstaller packaging/rdpstudio.spec          # → dist/KB-Remote/
```

Windows installer: install [Inno Setup
6.3+](https://jrsoftware.org/isinfo.php) and run
`packaging\windows\build.ps1` (or `build.bat`) after the PyInstaller build; it
produces the versioned installer plus the stable `KB-Remote-Setup.exe` copy
and the bootstrap scripts.

## Uninstall

```bash
rm -rf ~/.kb-remote ~/.local/bin/kb-remote ~/.local/bin/rdpstudio ~/.local/share/applications/rdpstudio.desktop
# state (sessions/vault) lives in ~/.config/kb-remote — remove if desired
```

Windows: use *Settings → Apps → KB-Remote → Uninstall* (or "Apps & features"),
then delete `%APPDATA%\KB-Remote` if you also want to drop saved state.
