"""Generate ``.rdp`` files for the Windows Terminal Services client (mstsc)."""

from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path

from ...core.models import Session

_CTRL = re.compile(r"[\x00-\x1f\x7f]")

# Fallback location used when the default per-user temp directory cannot be
# trusted (symlinked, or owned by someone else on a shared /tmp).
_fallback_dir: Path | None = None


def _private_temp_dir() -> Path:
    """Return a directory only this user can write, or a fresh private one.

    ``tempfile.gettempdir()`` is world-writable, so a predictable
    ``rdpstudio-<uid>`` name can be pre-created by another local user as a
    symlink (CWE-377/CWE-59).  Only an existing *directory* we own with no
    group/other access is used as-is; anything else falls back to
    ``mkdtemp``, which is atomic, uniquely named and already 0700.
    """
    global _fallback_dir
    uid = os.getuid() if hasattr(os, "getuid") else "user"
    candidate = Path(tempfile.gettempdir()) / f"rdpstudio-{uid}"
    try:
        candidate.mkdir(mode=0o700, exist_ok=True)
        info = os.lstat(candidate)
        trusted = stat.S_ISDIR(info.st_mode)
        if trusted and os.name == "posix":
            trusted = info.st_uid == os.getuid()
        if trusted:
            if os.name == "posix" and stat.S_IMODE(info.st_mode) & 0o077:
                os.chmod(candidate, 0o700)
            return candidate
    except OSError:
        pass
    if _fallback_dir is None or not _fallback_dir.is_dir():
        _fallback_dir = Path(tempfile.mkdtemp(prefix="rdpstudio-rdp-"))
    return _fallback_dir


def _rdp_str(value: object) -> str:
    """Reject CR/LF/NUL so a field cannot inject extra .rdp records (SR-02)."""
    text = str(value or "")
    if _CTRL.search(text):
        raise ValueError("RDP field contains control characters")
    return text


def build_rdp_text(defn: Session) -> str:
    width = defn.rdp_width or 1600
    height = defn.rdp_height or 900
    full = defn.rdp_fullscreen
    lines = [
        f"full address:s:{_rdp_str(defn.host)}",
        f"server port:i:{defn.endpoint()[1]}",
        f"username:s:{_rdp_str(defn.username)}",
        f"domain:s:{_rdp_str(defn.domain)}",
        f"desktopwidth:i:{'0' if full else width}",
        f"desktopheight:i:{'0' if full else height}",
        f"session bpp:i:{defn.rdp_color_depth}",
        "compression:i:1",
        "keyboardhook:i:2",
        "audiocapturemode:i:0",
        "videoplaybackmode:i:1",
        "connection type:i:7",  # autodetect
        "networkautodetect:i:1",
        "bandwidthautodetect:i:1",
        "displayconnectionbar:i:1",
        "disable wallpaper:i:0",
        "allow font smoothing:i:1",
        "allow desktop composition:i:1",
        "disable full window drag:i:0",
        "disable menu anims:i:0",
        "disable themes:i:0",
        "disable cursor setting:i:0",
        "bitmapcachepersistenable:i:1",
        f"redirectclipboard:i:{1 if defn.rdp_clipboard else 0}",
        f"drivestoredirect:s:{'*' if defn.rdp_drives else ''}",
        f"redirectprinters:i:{1 if getattr(defn, 'rdp_printer', False) else 0}",
        "redirectcomports:i:0",
        "redirectsmartcards:i:0",
        "redirectposdevices:i:0",
        "autoreconnection enabled:i:1",
        f"authentication level:i:{0 if defn.rdp_cert_ignore else 2}",
        "prompt for credentials:i:0",
        "negotiate security layer:i:1",
        "remoteapplicationmode:i:0",
        "alternate shell:s:",
        "shell working directory:s:",
        "gatewayhostname:s:" + _rdp_str(defn.rdp_gateway_host),
        f"gatewayusagemethod:i:{4 if defn.rdp_gateway_host else 0}",
        "gatewaycredentialssource:i:4" if defn.rdp_gateway_host else "gatewaycredentialssource:i:0",
        "gatewayprofileusagemethod:i:1" if defn.rdp_gateway_host else "gatewayprofileusagemethod:i:0",
        f"gatewayusername:s:{_rdp_str(defn.rdp_gateway_user)}",
        f"smart sizing:i:{1 if defn.rdp_fit_screen else 0}",
        "use multimon:i:0",
    ]
    # mstsc applies the LAST occurrence of a key, so duplicates are not just
    # noise — they can silently override earlier values. Emit each key once
    # (first occurrence wins).
    seen: set[str] = set()
    out = []
    for line in lines:
        key = line.split(":", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\r\n".join(out) + "\r\n"


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def write_rdp_file(defn: Session, directory: Path | None = None) -> Path:
    """Write a .rdp file for mstsc, private to the current user.

    The filename is derived from a user-controlled display name, so it is
    sanitised: an unfiltered name could contain ``/`` or ``..`` and escape the
    target directory (CWE-22).  The file lands in a per-user directory with
    restrictive permissions because it embeds the username/host layout.

    The file is created with ``O_EXCL|O_NOFOLLOW`` and ``0600`` so a
    pre-planted symlink or hard link in the destination cannot redirect the
    write to a victim file (CWE-377/CWE-59).  A stale file left by an earlier
    launch is replaced only after it is confirmed to be a regular file owned
    by this user.
    """
    if directory is None:
        directory = _private_temp_dir()
    else:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    safe = _SAFE_NAME.sub("_", defn.display_name()).strip("._") or "session"
    path = directory / f"{safe[:64]}_{_SAFE_NAME.sub('_', defn.id)}.rdp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        info = os.lstat(path)
        owned = os.name != "posix" or getattr(info, "st_uid", os.getuid()) == os.getuid()
        if not stat.S_ISREG(info.st_mode) or not owned:
            # Symlink/FIFO/foreign file: refuse rather than truncate it.
            raise OSError(f"refusing to replace unsafe file at {path}") from None
        os.unlink(path)
        fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            # utf-16 includes the BOM, which mstsc uses to detect Unicode files
            # (without it non-ASCII usernames/domains can be misread as ANSI).
            fh.write(build_rdp_text(defn).encode("utf-16"))
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    return path
