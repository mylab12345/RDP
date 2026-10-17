#!/usr/bin/env python3
"""Prune a KB-Remote virtualenv for minimal Docker image size.

``PySide6-Essentials`` (and ``PySide6-Addons`` when pulled transitively by
``pyside6-qtermwidget``) ships ~650 MB of Qt libraries, QML controls,
WebEngine/Chromium, 3D/Multimedia engines, translations, C++ headers, type
stubs, and standalone developer tools (Designer, Linguist, Assistant, qmlls).

KB-Remote is a pure ``QtWidgets`` + ``QtSvg`` desktop application (with
optional ``pyside6_qtermwidget`` linking against ``QtCore``, ``QtGui``,
``QtWidgets``, ``QtQml``, ``QtNetwork`` and ``QtDBus``). Removing the unused
Qt components and build-time packaging tools reduces ``/opt/venv`` from
~700 MB to ~125 MB (~82% smaller) without affecting SSH, SFTP, RDP, or the
native Linux terminal renderer.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

# Build-time or meta-packages that are not needed at runtime.
# Note: ``pyside6-qtermwidget`` declares ``Requires-Dist: PySide6`` which pulls
# in ``PySide6-Addons`` (~350 MB of QtWebEngine/Qt3D/Multimedia), even though
# ``libqtermwidget6`` only links against libraries in ``PySide6-Essentials``.
UNINSTALL_PACKAGES: tuple[str, ...] = (
    "PySide6",
    "PySide6-Addons",
    "pip",
    "setuptools",
    "wheel",
)

# Directories and standalone developer binaries inside ``site-packages/PySide6``
# that are unused at runtime.
PYSIDE_REMOVE_PATHS: tuple[str, ...] = (
    "assistant",
    "designer",
    "linguist",
    "lrelease",
    "lupdate",
    "qmlls",
    "qmlformat",
    "balsam",
    "balsamui",
    "qsb",
    "include",
    "typesystems",
    "glue",
    "scripts",
    "doc",
    "Qt/translations",
    "Qt/qml",
    "Qt/metatypes",
    "Qt/libexec",
    "Qt/resources",
)

# Qt plugin categories required at runtime for X11/XCB, Wayland, Offscreen,
# SVG icons, and system integration.
KEEP_QT_PLUGIN_DIRS: frozenset[str] = frozenset(
    {
        "platforms",
        "xcbglintegrations",
        "wayland-decoration-client",
        "wayland-graphics-integration-client",
        "wayland-shell-integration",
        "iconengines",
        "imageformats",
        "platforminputcontexts",
        "platformthemes",
        "tls",
        "generic",
        "networkinformation",
    }
)

# Specific plugin shared objects inside kept plugin directories that depend on
# removed Qt modules (QtPdf, QtVirtualKeyboard).
REMOVE_QT_PLUGIN_FILES: tuple[str, ...] = (
    "imageformats/libqpdf.so",
    "platforminputcontexts/libqtvirtualkeyboardplugin.so",
)

# PySide6 Python extension modules used by KB-Remote or QTermWidget.
KEEP_PYSIDE_BINDINGS: frozenset[str] = frozenset(
    {
        "QtCore.abi3.so",
        "QtGui.abi3.so",
        "QtWidgets.abi3.so",
        "QtSvg.abi3.so",
        "QtSvgWidgets.abi3.so",
        "QtNetwork.abi3.so",
        "QtDBus.abi3.so",
        "QtOpenGL.abi3.so",
        "QtOpenGLWidgets.abi3.so",
    }
)

# Shared libraries in ``PySide6/Qt/lib`` required by the kept bindings,
# ``pyside6_qtermwidget``, and the kept platform/icon/imageformat plugins.
KEEP_QT_LIB_PREFIXES: tuple[str, ...] = (
    "libQt6Core.",
    "libQt6Gui.",
    "libQt6Widgets.",
    "libQt6Svg.",
    "libQt6SvgWidgets.",
    "libQt6DBus.",
    "libQt6Network.",
    "libQt6OpenGL.",
    "libQt6OpenGLWidgets.",
    "libQt6Qml.",
    "libQt6XcbQpa.",
    "libQt6WaylandClient.",
    "libQt6WlShellIntegration.",
    "libQt6EglFSDeviceIntegration.",
    "libQt6EglFsKmsSupport.",
    "libicudata.",
    "libicui18n.",
    "libicuuc.",
)


def _find_site_packages(venv_dir: pathlib.Path) -> pathlib.Path:
    matches = sorted((venv_dir / "lib").glob("python*/site-packages"))
    if not matches:
        raise FileNotFoundError(f"No site-packages found under {venv_dir / 'lib'}")
    return matches[0]


def uninstall_build_packages(venv_dir: pathlib.Path) -> None:
    """Uninstall non-runtime packages via the venv's Python interpreter."""
    python_bin = venv_dir / "bin" / "python"
    if not python_bin.is_file():
        return
    for pkg in UNINSTALL_PACKAGES:
        subprocess.run(
            [str(python_bin), "-m", "pip", "uninstall", "-y", "-q", pkg],
            check=False,
        )


def prune_site_packages(site_packages: pathlib.Path, bin_dir: pathlib.Path | None = None) -> None:
    """Remove unused PySide6/Qt files, type stubs, and bytecode caches."""
    pyside = site_packages / "PySide6"
    if pyside.is_dir():
        for rel in PYSIDE_REMOVE_PATHS:
            target = pyside / rel
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists() or target.is_symlink():
                target.unlink(missing_ok=True)

        plugins_dir = pyside / "Qt" / "plugins"
        if plugins_dir.is_dir():
            for child in list(plugins_dir.iterdir()):
                if child.is_dir() and child.name not in KEEP_QT_PLUGIN_DIRS:
                    shutil.rmtree(child, ignore_errors=True)
            for rel_file in REMOVE_QT_PLUGIN_FILES:
                plugin_file = plugins_dir / rel_file
                if plugin_file.exists() or plugin_file.is_symlink():
                    plugin_file.unlink(missing_ok=True)

        for binding in list(pyside.glob("Qt*.abi3.so")):
            if binding.name not in KEEP_PYSIDE_BINDINGS:
                binding.unlink(missing_ok=True)

        qt_lib_dir = pyside / "Qt" / "lib"
        if qt_lib_dir.is_dir():
            for lib in list(qt_lib_dir.iterdir()):
                if not lib.name.startswith(KEEP_QT_LIB_PREFIXES):
                    if lib.is_dir():
                        shutil.rmtree(lib, ignore_errors=True)
                    else:
                        lib.unlink(missing_ok=True)

    if bin_dir is not None and bin_dir.is_dir():
        for tool in list(bin_dir.glob("pyside6-*")):
            tool.unlink(missing_ok=True)

    for stub in list(site_packages.rglob("*.pyi")):
        stub.unlink(missing_ok=True)

    for cache in list(site_packages.rglob("__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)


def strip_shared_objects(root: pathlib.Path) -> None:
    """Strip debug/unneeded symbols from ELF shared libraries when ``strip`` exists."""
    strip_bin = shutil.which("strip")
    if not strip_bin:
        return
    so_files = [
        str(p)
        for p in root.rglob("*.so*")
        if p.is_file() and not p.is_symlink()
    ]
    if so_files:
        subprocess.run(
            [strip_bin, "--strip-unneeded", *so_files],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def prune_venv(venv_dir: pathlib.Path, *, run_pip_uninstall: bool = True) -> None:
    """Prune ``venv_dir`` in place for minimal runtime size."""
    if run_pip_uninstall:
        uninstall_build_packages(venv_dir)
    site_packages = _find_site_packages(venv_dir)
    prune_site_packages(site_packages, bin_dir=venv_dir / "bin")
    for cache in list(venv_dir.rglob("__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)
    strip_shared_objects(site_packages)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: prune_venv.py <venv-path>", file=sys.stderr)
        return 2
    venv_path = pathlib.Path(args[0]).resolve()
    if not venv_path.is_dir():
        print(f"Error: virtualenv directory not found: {venv_path}", file=sys.stderr)
        return 1
    prune_venv(venv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
