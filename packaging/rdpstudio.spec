# PyInstaller spec for RDP Studio (Windows + Linux).
#   pyinstaller packaging/rdpstudio.spec
# Output: dist/RDPStudio/ (onedir, faster startup + updatable)

import sys
from pathlib import Path

block_cipher = None
ROOT = Path(SPECPATH).parent  # noqa: F821

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "src" / "rdpstudio" / "resources" / "icons" / "*.svg"), "rdpstudio/resources/icons"),
    ],
    hiddenimports=[
        "paramiko",
        "pyte",
        "rdpstudio.protocols.ssh",
        "rdpstudio.protocols.rdp",
        "rdpstudio.protocols.local",
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
    name="rdpstudio",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # GUI app; logs go to RDPSTUDIO_HOME/logs
    icon=str(ROOT / "src" / "rdpstudio" / "resources" / "icons" / "logo.svg")
    if sys.platform != "win32"
    else None,
)

coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="RDPStudio")
