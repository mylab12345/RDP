"""Import sessions from ~/.ssh/config."""

from __future__ import annotations

from pathlib import Path

from ..core.log import get_logger
from ..core.models import AUTH_KEY, AUTH_NONE, PROTOCOL_SSH, Session
from ..core.store import SessionStore

log = get_logger("importers.sshconfig")


def parse_ssh_config(text: str) -> list[Session]:
    sessions: list[Session] = []
    current: Session | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # OpenSSH accepts "Key value", "Key=value" and tab separators.
        if "=" in line and " " not in line.split("=", 1)[0] and "\t" not in line.split("=", 1)[0]:
            key, _, value = line.partition("=")
        else:
            parts = line.split(None, 1)
            key = parts[0]
            value = parts[1] if len(parts) > 1 else ""
        value = value.strip()
        key = key.strip().lower()
        if key == "host":
            names = value.split()
            for name in names:
                if any(ch in name for ch in "*?!") or not name:
                    continue
                current = Session(protocol=PROTOCOL_SSH, name=name)
                current.host = name
                current.auth = AUTH_NONE
                sessions.append(current)
        elif current is not None:
            if key == "hostname":
                current.host = value
            elif key == "user":
                current.username = value
            elif key == "port":
                try:
                    current.port = int(value)
                except ValueError:
                    pass
            elif key == "identityfile":
                current.key_path = value.replace("~", str(Path.home()), 1)
                current.auth = AUTH_KEY
            elif key == "proxyjump":
                current.options["imported_proxyjump"] = value
    return sessions


def import_ssh_config(store: SessionStore, path: Path | None = None) -> int:
    path = path or Path.home() / ".ssh" / "config"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    sessions = parse_ssh_config(text)
    if not sessions:
        return 0
    return store.import_sessions(sessions, on_conflict="rename")
