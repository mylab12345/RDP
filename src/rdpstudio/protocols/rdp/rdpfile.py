"""Generate ``.rdp`` files for the Windows Terminal Services client (mstsc)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ...core.models import Session


def build_rdp_text(defn: Session) -> str:
    width = defn.rdp_width or 1600
    height = defn.rdp_height or 900
    full = defn.rdp_fullscreen
    lines = [
        f"full address:s:{defn.host}",
        f"server port:i:{defn.endpoint()[1]}",
        f"username:s:{defn.username}",
        f"domain:s:{defn.domain}",
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
        "full address:s:" + defn.host,  # keep first for compatibility
        f"redirectclipboard:i:{1 if defn.rdp_clipboard else 0}",
        f"drivestoredirect:s:{'*' if defn.rdp_drives else ''}",
        "redirectprinters:i:0",
        "redirectcomports:i:0",
        "redirectsmartcards:i:0",
        "redirectposdevices:i:0",
        "autoreconnection enabled:i:1",
        "authentication level:i:2",
        "prompt for credentials:i:0",
        "negotiate security layer:i:1",
        "remoteapplicationmode:i:0",
        "alternate shell:s:",
        "shell working directory:s:",
        "gatewayhostname:s:" + defn.rdp_gateway_host,
        f"gatewayusagemethod:i:{4 if defn.rdp_gateway_host else 0}",
        "gatewaycredentialssource:i:4" if defn.rdp_gateway_host else "gatewaycredentialssource:i:0",
        "gatewayprofileusagemethod:i:1" if defn.rdp_gateway_host else "gatewayprofileusagemethod:i:0",
        f"gatewayusername:s:{defn.rdp_gateway_user}",
        "smart sizing:i:1",
        "use multimon:i:0",
    ]
    seen = set()
    out = []
    for line in lines:
        key = line.split(":")[0]
        if key in ("full address",) and key in seen:
            continue
        if (key, line) in seen:
            continue
        seen.add((key, line))
        out.append(line)
    return "\r\n".join(out) + "\r\n"


def write_rdp_file(defn: Session, directory: Path | None = None) -> Path:
    directory = directory or Path(tempfile.gettempdir()) / "rdpstudio"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{defn.display_name().replace(' ', '_')}_{defn.id}.rdp"
    path.write_text(build_rdp_text(defn), encoding="utf-16-le")
    return path
