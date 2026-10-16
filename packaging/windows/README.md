# Windows packaging — universal installer

KB-Remote ships to Windows as **one self-contained setup executable**. The
PyInstaller bundle inside it already contains the Python runtime, Qt/PySide6,
`paramiko`, `cryptography`, `pyte` and (optionally) `pywinpty`, so the target
machine needs **no Python, no package manager and no other prerequisite**.
RDP uses the built-in `mstsc.exe`; SSH and local ConPTY shells are covered by
the bundled libraries.

Supported targets:

| OS | Notes |
|----|-------|
| Windows 10 1809+ / Windows 11 | x64, and ARM64 via Windows' x64 emulation |
| Windows Server 2019 / 2022 / 2025 | x64, and ARM64 via x64 emulation |

Windows Server 2016 and older are below Qt 6's minimum (build 17763); the
installer refuses them with a clear message.

## The universal link

Every tagged release publishes three stable asset names, so this link always
resolves to the newest build:

```
https://github.com/mylab12345/RDP/releases/latest/download/KB-Remote-Setup.exe
```

Give end users **one** of these — each installs everything, silently, with no
admin rights required (per-user install by default):

```powershell
# PowerShell one-liner
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://github.com/mylab12345/RDP/releases/latest/download/install.ps1 -OutFile $env:TEMP\kbri.ps1; & $env:TEMP\kbri.ps1"
```

```cmd
:: cmd.exe / double-click (download install.cmd once)
install.cmd
```

Or download `KB-Remote-Setup.exe` directly and run it (double-click shows the
wizard; silent flags are below).

### Options

| Flag | Effect |
|------|--------|
| `-Version X.Y.Z` | install a specific release instead of `latest` |
| `-Interactive` | show the graphical wizard instead of a silent install |
| `-InstallDir <path>` | choose the install location |
| `-NoLaunch` | do not start the app afterwards |
| `-Force` | reinstall / upgrade even if already present |
| `-FromSource` | create a venv from a checkout and `pip install -e ".[win]"` |

Run as **Administrator**, or pass `-InstallDir "$env:ProgramFiles\KB-Remote"`,
for an all-users install. Otherwise it installs to
`%LOCALAPPDATA%\Programs\KB-Remote`.

## Building locally

```powershell
# from the repository root, on Windows with Python 3.10+ and Inno Setup 6.3+
.\packaging\windows\build.ps1            # or: build.bat
```

Output:

- `dist\KB-Remote\` — onedir PyInstaller bundle
- `installer\KB-Remote-Setup-<ver>-windows-x64.exe` — versioned installer
- `installer\KB-Remote-Setup.exe` — stable name for the universal link
- `installer\install.ps1`, `installer\install.cmd` — bootstrap scripts

`packaging/ci/release.yml` runs exactly this on `windows-latest` for every
`v*` tag and attaches all four assets to the GitHub release.

## Signing

The builds are currently unsigned, so Windows SmartScreen will warn on first
run. To remove the warning, sign `KB-Remote-Setup.exe` (and the PyInstaller
`KB-Remote.exe`) with an EV/OV code-signing certificate — pass
`-SignTool <name> -CertThumbprint <thumbprint>` to `build.ps1`, which forwards
them to Inno Setup.
