"""Pure session connectivity checks used by the session editor.

The checks are intentionally lightweight and safe:

- SSH: TCP connect + banner read (verifies the endpoint is speaking SSH)
- RDP: protocol-level X.224 negotiation probe
- Local: validate the configured command / default shell exists

No credentials are sent and no session is started.
"""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .models import Session

_MAX_SSH_BANNER_BYTES = 512
_MAX_SSH_BANNER_LINES = 3


@dataclass(frozen=True)
class SessionCheckResult:
    ok: bool
    summary: str
    details: str = ""


class SessionCheckError(RuntimeError):
    pass


def check_session_connectivity(session: Session, timeout: float = 5.0) -> SessionCheckResult:
    """Run a lightweight protocol-aware connection check for ``session``."""
    protocol = getattr(session, "protocol", "")
    try:
        if protocol == "ssh":
            return _check_ssh(session, timeout=timeout)
        if protocol == "rdp":
            return _check_rdp(session, timeout=timeout)
        if protocol == "local":
            return _check_local(session)
        return SessionCheckResult(False, f"Unsupported protocol: {protocol or 'unknown'}")
    except SessionCheckError as exc:
        return SessionCheckResult(False, str(exc))


def _check_ssh(session: Session, timeout: float) -> SessionCheckResult:
    host, port = session.endpoint()
    if not host:
        raise SessionCheckError("Enter a host first.")
    t0 = time.monotonic()
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        raise SessionCheckError(f"SSH check failed for {host}:{port}: {exc}") from exc
    banner = None
    payload = bytearray()
    try:
        sock.settimeout(timeout)
        while len(payload) < _MAX_SSH_BANNER_BYTES:
            chunk = sock.recv(128)
            if not chunk:
                break
            payload.extend(chunk)
            lines = payload.splitlines()
            for raw in lines[:_MAX_SSH_BANNER_LINES]:
                text = raw.decode("utf-8", "replace").strip("\r")
                if text.startswith("SSH-"):
                    banner = text
                    break
            if banner or len(lines) >= _MAX_SSH_BANNER_LINES or b"\n" in payload:
                break
    except OSError as exc:
        raise SessionCheckError(f"SSH check failed for {host}:{port}: {exc}") from exc
    finally:
        try:
            sock.close()
        except OSError:
            pass
    if not banner:
        preview = payload.decode("utf-8", "replace").strip() or "no banner received"
        raise SessionCheckError(
            f"{host}:{port} is reachable, but it did not present a valid SSH banner ({preview})."
        )
    latency_ms = (time.monotonic() - t0) * 1000
    return SessionCheckResult(
        True,
        f"SSH server reachable — {latency_ms:.0f} ms",
        f"Server banner: {banner}",
    )


def _check_rdp(session: Session, timeout: float) -> SessionCheckResult:
    from ..protocols.rdp.negotiate import RdpProbeError, probe

    host, port = session.endpoint()
    if not host:
        raise SessionCheckError("Enter a host first.")
    try:
        result = probe(host, port, timeout=timeout)
    except RdpProbeError as exc:
        raise SessionCheckError(f"RDP check failed for {host}:{port}: {exc}") from exc
    if result.failure_code is not None:
        return SessionCheckResult(
            True,
            f"RDP server reachable — {result.latency_ms:.0f} ms",
            f"The server refused the requested security mode: {result.failure_name}",
        )
    return SessionCheckResult(
        True,
        f"RDP server reachable — {result.latency_ms:.0f} ms",
        f"Negotiated security: {result.selected_protocol_name}",
    )


def _check_local(session: Session) -> SessionCheckResult:
    argv = resolve_local_command(str(getattr(session, "options", {}).get("command", "") or ""))
    return SessionCheckResult(
        True,
        "Local shell command looks available.",
        "Command: " + " ".join(argv),
    )


def resolve_local_command(raw: str, *, env: dict[str, str] | None = None) -> list[str]:
    """Resolve the configured local command or the platform default shell."""
    env = env if env is not None else os.environ
    text = str(raw or "").strip()
    if text:
        try:
            argv = shlex.split(text, posix=(os.name != "nt"))
        except ValueError as exc:
            raise SessionCheckError(f"Invalid local command: {exc}") from exc
        if not argv:
            raise SessionCheckError("Enter a command or leave it blank for the default shell.")
    else:
        argv = _default_local_command(env)
    executable = _resolve_executable(argv[0])
    if executable is None:
        raise SessionCheckError(f"Command not found: {argv[0]}")
    return [executable, *argv[1:]]


def _default_local_command(env: dict[str, str]) -> list[str]:
    if os.name != "nt":
        for candidate in (env.get("SHELL"), "/bin/bash", "/bin/sh"):
            if candidate and _resolve_executable(candidate):
                return [candidate, "-i"] if candidate != "/bin/sh" else [candidate]
        raise SessionCheckError("No usable local shell was found.")
    for candidate in ("pwsh", "powershell", "cmd.exe"):
        resolved = _resolve_executable(candidate)
        if resolved:
            if candidate == "cmd.exe":
                return [resolved, "/Q"]
            return [resolved, "-NoLogo"]
    raise SessionCheckError("No usable local shell was found.")


def _resolve_executable(command: str) -> str | None:
    expanded = os.path.expanduser(command)
    if os.path.isabs(expanded) or any(sep and sep in expanded for sep in (os.path.sep, os.path.altsep)):
        path = Path(expanded)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        return None
    return shutil.which(expanded)
