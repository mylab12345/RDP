# PyInstaller spec for KB-Remote (Windows).
#   pyinstaller packaging\windows\rdpstudio-windows.spec
# Output: dist\KB-Remote\ (onedir; faster startup + updatable)
#
# Build on a Windows runner with:
#   pip install . pyinstaller ".[win]"

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).parents[1]  # noqa: F821  (packaging/windows -> repo root)

native_datas = []
native_binaries = []
native_hiddenimports = []
try:
    from PyInstaller.utils.hooks import collect_all

    native_datas, native_binaries, native_hiddenimports = collect_all("pyside6_qtermwidget")
except Exception:
    pass

winpty_datas = []
winpty_binaries = []
winpty_hiddenimports = []
try:
    from PyInstaller.utils.hooks import collect_all

    winpty_datas, winpty_binaries, winpty_hiddenimports = collect_all("winpty")
except Exception:
    pass

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=native_binaries + winpty_binaries,
    datas=[
        (str(ROOT / "src" / "rdpstudio" / "resources" / "icons"), "rdpstudio/resources/icons"),
        (str(ROOT / "src" / "rdpstudio" / "resources" / "*.qss"), "rdpstudio/resources"),
        *native_datas,
        *winpty_datas,
    ],
    hiddenimports=[
        "paramiko",
        "pyte",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "rdpstudio.protocols.ssh",
        "rdpstudio.protocols.rdp",
        "rdpstudio.protocols.local",
        "winpty",
        *native_hiddenimports,
        *winpty_hiddenimports,
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
    name="KB-Remote",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # GUI app; logs go to KB_REMOTE_HOME\logs
    icon=str(ROOT / "src" / "rdpstudio" / "resources" / "icons" / "logo.ico"),
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="KB-Remote")
"""