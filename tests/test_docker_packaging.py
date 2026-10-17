"""Tests for the minimal multi-stage Docker packaging, venv pruning, and entrypoint."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import stat
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_prune_module():
    path = ROOT / "packaging" / "docker" / "prune_venv.py"
    spec = importlib.util.spec_from_file_location("prune_venv", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_dockerfile_is_multistage_slim_and_includes_all_dependencies():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    # Multi-stage slim build
    assert "AS builder" in dockerfile
    assert "AS runtime" in dockerfile
    assert "-slim-bookworm" in dockerfile
    assert "--no-install-recommends" in dockerfile
    assert "COPY --from=builder /opt/venv /opt/venv" in dockerfile
    assert "prune_venv.py /opt/venv" in dockerfile
    assert "/var/lib/apt/lists/*" in dockerfile

    # Python dependencies (including native terminal extra with fallback)
    assert ".[native-terminal]" in dockerfile

    # All required system & GUI runtime packages
    required_Runtime_packages = (
        "freerdp3-x11",
        "freerdp2-x11",
        "openssh-client",
        "ca-certificates",
        "bash",
        "tini",
        "xauth",
        "xdg-utils",
        "fonts-dejavu-core",
        "fontconfig",
        "libfontconfig1",
        "libfreetype6",
        "libglib2.0-0",
        "libdbus-1-3",
        "libgl1",
        "libegl1",
        "libglx0",
        "libopengl0",
        "libx11-6",
        "libx11-xcb1",
        "libxcb1",
        "libxcb-cursor0",
        "libxcb-icccm4",
        "libxcb-image0",
        "libxcb-keysyms1",
        "libxcb-randr0",
        "libxcb-render0",
        "libxcb-render-util0",
        "libxcb-shape0",
        "libxcb-shm0",
        "libxcb-sync1",
        "libxcb-util1",
        "libxcb-xfixes0",
        "libxcb-xkb1",
        "libxkbcommon0",
        "libxkbcommon-x11-0",
        "libwayland-client0",
        "libwayland-cursor0",
        "libwayland-egl1",
        "libpulse0",
        "libasound2",
    )
    for pkg in required_Runtime_packages:
        assert pkg in dockerfile, f"Missing required package {pkg!r} in Dockerfile"

    # Non-root runtime user, volume, SFTP share server port, and entrypoint
    assert "USER kbremote" in dockerfile
    assert "EXPOSE 2222" in dockerfile
    assert "VOLUME" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "docker-entrypoint.sh" in dockerfile


@pytest.mark.unit
def test_dockerignore_and_compose_exist():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    for pattern in (".git", ".venv", "__pycache__", "docs/screenshots", "tests", "dist", "build"):
        assert pattern in dockerignore

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "dockerfile: Dockerfile" in compose
    assert "/tmp/.X11-unix:/tmp/.X11-unix" in compose
    assert "2222:2222" in compose
    assert "ipc: host" in compose


@pytest.mark.unit
def test_prune_venv_preserves_needed_qt_files_and_removes_bloat(tmp_path):
    prune_mod = _load_prune_module()

    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    site = venv / "lib" / "python3.12" / "site-packages"
    pyside = site / "PySide6"
    qt_lib = pyside / "Qt" / "lib"
    qt_plugins = pyside / "Qt" / "plugins"

    for d in (
        bin_dir,
        qt_lib,
        qt_plugins / "platforms",
        qt_plugins / "xcbglintegrations",
        qt_plugins / "iconengines",
        qt_plugins / "imageformats",
        qt_plugins / "platforminputcontexts",
        qt_plugins / "designer",
        qt_plugins / "sqldrivers",
        pyside / "Qt" / "translations",
        pyside / "Qt" / "qml",
        pyside / "Qt" / "metatypes",
        pyside / "Qt" / "resources",
        pyside / "include",
        site / "rdpstudio" / "__pycache__",
    ):
        d.mkdir(parents=True, exist_ok=True)

    # Files that MUST be kept
    keep_files = [
        bin_dir / "kb-remote",
        bin_dir / "python",
        pyside / "QtCore.abi3.so",
        pyside / "QtGui.abi3.so",
        pyside / "QtWidgets.abi3.so",
        pyside / "QtSvg.abi3.so",
        pyside / "QtNetwork.abi3.so",
        pyside / "QtDBus.abi3.so",
        qt_lib / "libQt6Core.so.6",
        qt_lib / "libQt6Gui.so.6",
        qt_lib / "libQt6Widgets.so.6",
        qt_lib / "libQt6Svg.so.6",
        qt_lib / "libQt6DBus.so.6",
        qt_lib / "libQt6Network.so.6",
        qt_lib / "libQt6Qml.so.6",
        qt_lib / "libQt6XcbQpa.so.6",
        qt_lib / "libQt6WaylandClient.so.6",
        qt_lib / "libicudata.so.73",
        qt_lib / "libicui18n.so.73",
        qt_lib / "libicuuc.so.73",
        qt_plugins / "platforms" / "libqxcb.so",
        qt_plugins / "platforms" / "libqwayland.so",
        qt_plugins / "platforms" / "libqoffscreen.so",
        qt_plugins / "xcbglintegrations" / "libqxcb-glx-integration.so",
        qt_plugins / "iconengines" / "libqsvgicon.so",
        qt_plugins / "imageformats" / "libqsvg.so",
    ]
    for f in keep_files:
        f.write_bytes(b"keep")

    # Files that MUST be removed
    remove_files = [
        bin_dir / "pyside6-designer",
        bin_dir / "pyside6-linguist",
        pyside / "designer",
        pyside / "assistant",
        pyside / "qmlls",
        pyside / "QtWidgets.pyi",
        pyside / "QtWebEngineCore.abi3.so",
        pyside / "Qt3DRender.abi3.so",
        pyside / "QtCharts.abi3.so",
        qt_lib / "libQt6WebEngineCore.so.6",
        qt_lib / "libQt6Designer.so.6",
        qt_lib / "libQt6Quick.so.6",
        qt_lib / "libQt6ShaderTools.so.6",
        qt_lib / "libavcodec.so.61",
        qt_plugins / "designer" / "libPySidePlugin.so",
        qt_plugins / "sqldrivers" / "libqsqlmysql.so",
        qt_plugins / "imageformats" / "libqpdf.so",
        qt_plugins / "platforminputcontexts" / "libqtvirtualkeyboardplugin.so",
        pyside / "Qt" / "translations" / "assistant_de.qm",
        pyside / "Qt" / "qml" / "builtins.qmltypes",
        pyside / "Qt" / "metatypes" / "qt6core_metatypes.json",
        pyside / "Qt" / "resources" / "qtwebengine_resources.pak",
        pyside / "include" / "pyside.h",
        site / "rdpstudio" / "__pycache__" / "app.cpython-312.pyc",
    ]
    for f in remove_files:
        f.write_bytes(b"bloat")

    prune_mod.prune_venv(venv, run_pip_uninstall=False)

    for f in keep_files:
        assert f.exists(), f"Expected {f} to be preserved"
    for f in remove_files:
        assert not f.exists(), f"Expected {f} to be pruned"


@pytest.mark.unit
def test_entrypoint_sets_private_dirs_and_headless_fallback(tmp_path):
    entrypoint = ROOT / "packaging" / "docker" / "entrypoint.sh"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()

    # Stub `kb-remote` that prints environment variables and arguments
    stub = fake_bin / "kb-remote"
    stub.write_text(
        "#!/bin/sh\n"
        'printf "ARGS=%s\\n" "$*"\n'
        'printf "PLATFORM=%s\\n" "${QT_QPA_PLATFORM:-}"\n'
        'printf "HOME_DIR=%s\\n" "${KB_REMOTE_HOME:-}"\n'
        'printf "RUNTIME_DIR=%s\\n" "${XDG_RUNTIME_DIR:-}"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)

    kb_home = tmp_path / "state"
    rt_dir = tmp_path / "runtime"
    env = {
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": str(tmp_path),
        "KB_REMOTE_HOME": str(kb_home),
        "XDG_RUNTIME_DIR": str(rt_dir),
    }

    # 1. Leading flag (`--version`) should invoke `kb-remote --version` with offscreen fallback
    res = subprocess.run(
        ["/bin/sh", str(entrypoint), "--version"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "ARGS=--version" in res.stdout
    assert "PLATFORM=offscreen" in res.stdout
    assert kb_home.is_dir()
    assert rt_dir.is_dir()
    assert stat.S_IMODE(kb_home.stat().st_mode) == 0o700
    assert stat.S_IMODE(rt_dir.stat().st_mode) == 0o700

    # 2. When DISPLAY is set, QT_QPA_PLATFORM is not forced to offscreen
    env_with_display = {**env, "DISPLAY": ":0"}
    res_disp = subprocess.run(
        ["/bin/sh", str(entrypoint), "kb-remote"],
        env=env_with_display,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "PLATFORM=" in res_disp.stdout
    assert "PLATFORM=offscreen" not in res_disp.stdout
