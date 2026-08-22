"""Local RDP server management.

RDP *clients* get you onto remote Windows machines; this module manages the
other side — checking whether the local machine accepts RDP connections, and
(on Windows) helping enable/disable the built-in Terminal Services listener +
firewall rule. On Linux it inspects ``xrdp``.

All privileged operations are explicit opt-in: we only *report* state unless
the user clicks "Apply" (which runs commands that require elevation).
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class RdpServerStatus:
    supported: bool = False     # platform can host an RDP server
    service_present: bool = False
    enabled: bool = False
    listening: bool = False
    port: int = 3389
    detail: str = ""
    commands: dict | None = None  # enable/disable commands (elevated)


def _win_reg_query(path: str, value: str) -> str | None:
    try:
        out = subprocess.run(
            ["reg", "query", path, "/v", value],
            capture_output=True, text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        if out.returncode != 0:
            return None
        for line in out.stdout.splitlines():
            if value in line:
                return line.split()[-1]
    except OSError:
        return None
    return None


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.6):
            return True
    except OSError:
        return False


def status() -> RdpServerStatus:
    st = RdpServerStatus()
    if sys.platform == "win32":
        st.supported = True
        denied = _win_reg_query(
            r"HKLM\SYSTEM\CurrentControlSet\Control\Terminal Server", "fDenyTSConnections"
        )
        st.service_present = denied is not None
        st.enabled = denied == "0x0"
        st.listening = _port_listening(3389)
        st.detail = (
            f"Terminal Services listener {'enabled' if st.enabled else 'disabled'}, "
            f"port 3389 {'listening' if st.listening else 'not listening'}"
        )
        st.commands = {
            "enable": (
                'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" '
                '/v fDenyTSConnections /t REG_DWORD /d 0 /f & '
                'netsh advfirewall firewall set rule group="remote desktop" new enable=Yes'
            ),
            "disable": (
                'reg add "HKLM\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server" '
                '/v fDenyTSConnections /t REG_DWORD /d 1 /f'
            ),
        }
        return st

    # Linux: xrdp
    st.supported = True
    has_xrdp = shutil.which("xrdp") is not None
    st.service_present = has_xrdp
    st.listening = _port_listening(3389)
    if has_xrdp:
        try:
            out = subprocess.run(
                ["systemctl", "is-active", "xrdp"], capture_output=True, text=True, timeout=10
            )
            active = out.stdout.strip() == "active"
        except OSError:
            active = st.listening
        st.enabled = active
        st.detail = f"xrdp installed; service {'active' if active else 'inactive'}; port 3389 {'listening' if st.listening else 'not listening'}"
        st.commands = {
            "enable": "sudo systemctl enable --now xrdp",
            "disable": "sudo systemctl disable --now xrdp",
        }
    else:
        st.enabled = False
        st.detail = "xrdp is not installed (sudo apt install xrdp)"
    return st
