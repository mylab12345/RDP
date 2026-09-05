# PyInstaller spec for KB-Remote (Windows + Linux).
# Release build — normally driven by packaging/windows/build-windows.ps1:
#   pyinstaller packaging/rdpstudio.spec
# Output: dist/KB-Remote/ (onedir; the single distributable Windows
# installer is then compiled from this folder by Inno Setup).

import platform
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).parent  # noqa: F821
IS_WIN = platform.system() == "Windows"
ICON = ROOT / "src" / "rdpstudio" / "resources" / "icons" / (
    "logo.ico" if IS_WIN else "logo.png"
)
VERSION_FILE = ROOT / "packaging" / "windows" / "version_info.txt"

# The native terminal is an optional runtime extra.  Include it in standalone
# builds when the builder environment has it, but keep the ordinary Windows /
# minimal-Linux build independent of that optional Qt extension.
native_datas = []
native_binaries = []
native_hiddenimports = []
try:
    from PyInstaller.utils.hooks import collect_all

    native_datas, native_binaries, native_hiddenimports = collect_all("pyside6_qtermwidget")
except Exception:
    pass

# Windows only: bundle the Visual C++ runtime DLLs beside the executable so
# the frozen app starts on machines without the system-wide VC++
# Redistributable (typical on Windows Server, but also seen on fresh
# clients). The loader resolves the application directory first, so these
# take precedence without touching the target system — no admin rights,
# no reboot, no separate download.
msvc_binaries: list[tuple[str, str]] = []
if IS_WIN:
    import os as _os

    _sys32 = _os.path.join(_os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    for _dll in (
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "concrt140.dll",
    ):
        _path = _os.path.join(_sys32, _dll)
        if _os.path.isfile(_path):
            msvc_binaries.append((_path, "."))


a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=native_binaries + msvc_binaries,
    datas=[
        (str(ROOT / "src" / "rdpstudio" / "resources" / "icons"), "rdpstudio/resources/icons"),
        *native_datas,
    ],
    hiddenimports=[
        "paramiko",
        "pyte",
        "rdpstudio.protocols.ssh",
        "rdpstudio.protocols.rdp",
        "rdpstudio.protocols.local",
        # Windows-only ConPTY backend for local shells (the pywinpty
        # package provides the `winpty` module; the app falls back to
        # cmd via QProcess when it is absent).
        *([] if not IS_WIN else ["winpty"]),
        *native_hiddenimports,
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "pydoc_data"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="kb-remote",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # GUI app; logs go to KB_REMOTE_HOME/logs
    icon=str(ICON),
    version=str(VERSION_FILE) if IS_WIN and VERSION_FILE.exists() else None,
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="KB-Remote")
