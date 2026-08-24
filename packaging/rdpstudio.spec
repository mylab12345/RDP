# PyInstaller spec for KB-Remote (Windows + Linux).
#   pyinstaller packaging/rdpstudio.spec
# Output: dist/KB-Remote/ (onedir, faster startup + updatable)

from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).parent  # noqa: F821

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


a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=native_binaries,
    datas=[
        (str(ROOT / "src" / "rdpstudio" / "resources" / "icons" / "*.svg"), "rdpstudio/resources/icons"),
        (str(ROOT / "src" / "rdpstudio" / "resources" / "icons" / "*.png"), "rdpstudio/resources/icons"),
        *native_datas,
    ],
    hiddenimports=[
        "paramiko",
        "pyte",
        "rdpstudio.protocols.ssh",
        "rdpstudio.protocols.rdp",
        "rdpstudio.protocols.local",
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
    icon=str(ROOT / "src" / "rdpstudio" / "resources" / "icons" / "logo.png"),
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="KB-Remote")
