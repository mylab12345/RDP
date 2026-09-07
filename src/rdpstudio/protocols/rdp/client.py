"""Pure RDP client discovery and command construction.

This module deliberately has no Qt imports.  Process supervision and embedded
surface handling live in :mod:`.session`; command policy stays independently
testable here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ...core.models import Session

# FreeRDP / Windows RD Session Host limits for the remote desktop resolution.
# Kept in sync with the Session dialog's spin-box ranges.
MIN_RDP_WIDTH, MIN_RDP_HEIGHT = 640, 480
MAX_RDP_WIDTH, MAX_RDP_HEIGHT = 7680, 4320


def find_rdp_client() -> tuple[str, str] | None:
    """Locate an RDP client binary as ``(path, kind)``.

    ``kind`` is either ``mstsc`` or ``freerdp``.  External-native clients are
    preferred before X11 FreeRDP; embedded mode requests its X11 client
    separately in :mod:`.embed`.
    """
    if sys.platform == "win32":
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        mstsc = os.path.join(system_root, "System32", "mstsc.exe")
        alternate = shutil.which("mstsc")
        if os.path.exists(mstsc):
            return mstsc, "mstsc"
        if alternate:
            return alternate, "mstsc"
        return None
    for name in (
        "sdl-freerdp3",
        "sdl-freerdp",
        "wlfreerdp3",
        "wlfreerdp",
        "xfreerdp3",
        "xfreerdp2",
        "xfreerdp",
    ):
        path = shutil.which(name)
        if path:
            return path, "freerdp"
    return None


def freerdp_supports_args_from_file(path: str | None = None) -> bool:
    """Detect and cache FreeRDP 3's private ``/args-from:file:`` support."""
    if not hasattr(freerdp_supports_args_from_file, "_cache"):
        freerdp_supports_args_from_file._cache: dict[str, bool] = {}
    if path is None:
        client = find_rdp_client()
        path = client[0] if client else ""
    if path in freerdp_supports_args_from_file._cache:
        return freerdp_supports_args_from_file._cache[path]
    if not path:
        freerdp_supports_args_from_file._cache[path] = False
        return False
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        text = (completed.stdout + completed.stderr).lower()
        has_args_from = "args-from" in text or "/args-from" in text
        if not has_args_from:
            for line in text.splitlines():
                if "freerdp version" not in line:
                    continue
                match = re.search(r"version\s+(\d+)\.", line)
                if match and int(match.group(1)) >= 3:
                    has_args_from = True
                break
        freerdp_supports_args_from_file._cache[path] = has_args_from
        return has_args_from
    except (OSError, subprocess.SubprocessError, ValueError):
        freerdp_supports_args_from_file._cache[path] = False
        return False


def build_freerdp_args(definition: Session, password: str | None) -> list[str]:
    """Build a FreeRDP command line for ``definition``.

    Secrets stay out of the returned argv unless the user explicitly enabled
    ``rdp_pass_on_cmdline``.  Certificate verification uses trust-on-first-use
    by default and is disabled only by the session's explicit
    ``rdp_cert_ignore`` opt-in.
    """
    host, port = definition.endpoint()
    args = ["/v:" + (f"{host}:{port}" if port != 3389 else host)]
    if definition.username:
        args.append(f"/u:{definition.username}")
    if password and definition.rdp_pass_on_cmdline:
        args.append(f"/p:{password}")
    args.append(f"/size:{definition.rdp_width}x{definition.rdp_height}")
    args.append(f"/bpp:{definition.rdp_color_depth}")
    args.append("/clipboard" if definition.rdp_clipboard else "-clipboard")
    if definition.rdp_fit_screen:
        args.append("/smart-sizing")
    if definition.rdp_fullscreen:
        args.append("/f")
    if definition.rdp_drives:
        args.append(f"/drive:KB-Remote,{os.path.expanduser('~')}")
    if getattr(definition, "rdp_printer", False):
        args.append("/printer")
    audio = getattr(definition, "rdp_audio_mode", "local")
    if audio == "remote":
        args.extend(("/sound:sys:pulse", "/audio-mode:0"))
    elif audio == "none":
        args.extend(("-sound", "/audio-mode:2"))
    else:
        args.extend(("/sound:sys:pulse", "/audio-mode:1"))
    args.append("/cert:ignore" if definition.rdp_cert_ignore else "/cert:tofu")
    args.extend(("+auto-reconnect", "/network:auto"))
    if definition.domain:
        args.append(f"/d:{definition.domain}")
    if definition.rdp_gateway_host:
        args.append(f"/g:{definition.rdp_gateway_host}:{definition.rdp_gateway_port}")
        if definition.rdp_gateway_user:
            args.append(f"/gu:{definition.rdp_gateway_user}")
    return args


def uses_args_file(definition: Session, password: str | None) -> bool:
    """Whether a secret should be delivered through a private argument file."""
    return bool(password) and not definition.rdp_pass_on_cmdline


def password_via_stdin(definition: Session, password: str | None) -> bool:
    """Deprecated compatibility alias for :func:`uses_args_file`."""
    return uses_args_file(definition, password)


def write_args_file(args: list[str]) -> Path:
    """Write FreeRDP arguments one-per-line to a private temporary file.

    Newline-bearing arguments are rejected because they could become extra
    FreeRDP options when parsed from the file.  Any failed write is cleaned up
    before the exception escapes.
    """
    for arg in args:
        if not isinstance(arg, str):
            raise TypeError("FreeRDP arguments must be strings")
        if "\n" in arg or "\r" in arg or "\x00" in arg:
            raise ValueError("FreeRDP arguments must not contain line breaks or NUL bytes")

    fd = -1
    name: str | None = None
    try:
        fd, name = tempfile.mkstemp(prefix="rdpstudio-args-", suffix=".cmd")
        if os.name == "posix":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            handle.write("\n".join(args) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return Path(name)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        if name is not None:
            try:
                os.unlink(name)
            except OSError:
                pass
        raise


def build_embedded_args(
    definition: Session,
    password: str | None,
    parent_xid: int,
    size: tuple[int, int] | None = None,
) -> list[str]:
    """Build FreeRDP arguments for an X11 child window inside a tab."""
    args = build_freerdp_args(definition, password)
    if size is not None:
        width = min(max(int(size[0]), MIN_RDP_WIDTH), MAX_RDP_WIDTH)
        height = min(max(int(size[1]), MIN_RDP_HEIGHT), MAX_RDP_HEIGHT)
        args = [arg for arg in args if not arg.startswith("/size:")]
        args.append(f"/size:{width}x{height}")
    args = [arg for arg in args if arg != "/smart-sizing"]
    args.append("/dynamic-resolution")
    if "/f" in args:
        args.remove("/f")  # fullscreen is meaningless inside a tab
    args.extend((f"/parent-window:{parent_xid}", "-decorations"))
    return args


def redact_args(args: list[str]) -> str:
    """Render a command line for logs with any password option masked."""
    return " ".join("/p:***" if arg.startswith("/p:") else arg for arg in args)
