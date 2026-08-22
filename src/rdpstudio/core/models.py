"""Data model: sessions, groups, forwards.

The model is intentionally protocol-agnostic. Protocol plugins may stash extra
options in ``Session.options`` (a free-form dict) so new protocols never
require changes to the persistence layer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_SSH = "ssh"
PROTOCOL_RDP = "rdp"
PROTOCOL_LOCAL = "local"

AUTH_PASSWORD = "password"
AUTH_KEY = "key"
AUTH_AGENT = "agent"
AUTH_CREDENTIAL = "credential"  # secret resolved from the vault at connect time
AUTH_NONE = "none"


def new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class Forward:
    """A port forward attached to a session.

    kind:
      ``local``    - listen locally, tunnel through the remote host to dest.
      ``remote``   - listen on the remote host, tunnel back to local dest.
      ``dynamic``  - local SOCKS5 proxy; destination chosen per connection.
    """

    kind: str = "local"  # local | remote | dynamic
    listen_host: str = "127.0.0.1"
    listen_port: int = 0
    dest_host: str = ""
    dest_port: int = 0
    enabled: bool = True
    name: str = ""

    def label(self) -> str:
        if self.kind == "dynamic":
            return f"SOCKS {self.listen_host}:{self.listen_port}"
        arrow = "→" if self.kind == "local" else "⇐"
        return f"{self.listen_host}:{self.listen_port} {arrow} {self.dest_host}:{self.dest_port}"

    def dest_label(self) -> str:
        if self.kind == "dynamic":
            return "(per-connection, SOCKS5)"
        return f"{self.dest_host}:{self.dest_port}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "listen_host": self.listen_host,
            "listen_port": self.listen_port,
            "dest_host": self.dest_host,
            "dest_port": self.dest_port,
            "enabled": self.enabled,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Forward:
        return cls(
            kind=d.get("kind", "local"),
            listen_host=d.get("listen_host", "127.0.0.1"),
            listen_port=int(d.get("listen_port", 0) or 0),
            dest_host=d.get("dest_host", ""),
            dest_port=int(d.get("dest_port", 0) or 0),
            enabled=bool(d.get("enabled", True)),
            name=d.get("name", ""),
        )


@dataclass
class Session:
    """A saved remote connection (SSH, RDP, local shell, ...)."""

    id: str = field(default_factory=new_id)
    name: str = ""
    protocol: str = PROTOCOL_SSH
    group: str = ""

    # --- transport ---
    host: str = ""
    port: int = 22
    username: str = ""
    # Optional plain-text password stored with the session (no vault needed).
    # Empty ⇒ interactive prompt at connect (SSH) / logon prompt (RDP).
    password: str = ""
    # password | key | agent | credential | none
    auth: str = AUTH_PASSWORD
    credential_id: str = ""  # vault entry when auth == credential
    key_path: str = ""  # private key when auth == key
    jump_session_id: str = ""  # optional ProxyJump-style chained session
    timeout: int = 10  # connect timeout seconds

    # --- behaviour ---
    startup_command: str = ""
    auto_reconnect: bool = True
    keepalive: int = 30
    description: str = ""
    tags: list[str] = field(default_factory=list)
    forwards: list[Forward] = field(default_factory=list)

    # --- ssh-specific ---
    agent_forwarding: bool = False
    compression: bool = True

    # --- rdp-specific ---
    domain: str = ""
    rdp_width: int = 1600
    rdp_height: int = 900
    rdp_color_depth: int = 32
    rdp_fullscreen: bool = False
    rdp_fit_screen: bool = False  # scale the remote desktop to fit the RDP window
    rdp_clipboard: bool = True
    rdp_drives: bool = False
    rdp_cert_ignore: bool = False
    rdp_pass_on_cmdline: bool = False  # FreeRDP only; visible in `ps`, off by default
    rdp_gateway_host: str = ""
    rdp_gateway_port: int = 443
    rdp_gateway_user: str = ""

    # --- free-form protocol options (future protocols / plugins) ---
    options: dict[str, Any] = field(default_factory=dict)

    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------------
    def display_name(self) -> str:
        return self.name or self.target()

    def target(self) -> str:
        if self.protocol == PROTOCOL_LOCAL:
            return "local shell"
        if not self.host:
            return "(no host)"
        return f"{self.username + '@' if self.username else ''}{self.host}:{self.port}"

    def endpoint(self) -> tuple[str, int]:
        return self.host, int(self.port or (3389 if self.protocol == PROTOCOL_RDP else 22))

    def copy(self) -> Session:
        import copy

        dup = copy.deepcopy(self)
        dup.id = new_id()
        dup.created_at = dup.updated_at = time.time()
        if dup.name:
            dup.name = f"{dup.name} (copy)"
        return dup

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "name": self.name,
            "protocol": self.protocol,
            "group": self.group,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "auth": self.auth,
            "credential_id": self.credential_id,
            "key_path": self.key_path,
            "jump_session_id": self.jump_session_id,
            "timeout": self.timeout,
            "startup_command": self.startup_command,
            "auto_reconnect": self.auto_reconnect,
            "keepalive": self.keepalive,
            "description": self.description,
            "tags": list(self.tags),
            "forwards": [f.to_dict() for f in self.forwards],
            "agent_forwarding": self.agent_forwarding,
            "compression": self.compression,
            "domain": self.domain,
            "rdp_width": self.rdp_width,
            "rdp_height": self.rdp_height,
            "rdp_color_depth": self.rdp_color_depth,
            "rdp_fullscreen": self.rdp_fullscreen,
            "rdp_fit_screen": self.rdp_fit_screen,
            "rdp_clipboard": self.rdp_clipboard,
            "rdp_drives": self.rdp_drives,
            "rdp_cert_ignore": self.rdp_cert_ignore,
            "rdp_pass_on_cmdline": self.rdp_pass_on_cmdline,
            "rdp_gateway_host": self.rdp_gateway_host,
            "rdp_gateway_port": self.rdp_gateway_port,
            "rdp_gateway_user": self.rdp_gateway_user,
            "options": dict(self.options),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Session:
        s = cls()
        s.id = d.get("id") or new_id()
        s.name = d.get("name", "")
        s.protocol = d.get("protocol", PROTOCOL_SSH)
        s.group = d.get("group", "")
        s.host = d.get("host", "")
        s.port = int(d.get("port", 22) or 22)
        s.username = d.get("username", "")
        s.password = d.get("password", "")
        s.auth = d.get("auth", AUTH_PASSWORD)
        s.credential_id = d.get("credential_id", "")
        s.key_path = d.get("key_path", "")
        s.jump_session_id = d.get("jump_session_id", "")
        s.timeout = int(d.get("timeout", 10) or 10)
        s.startup_command = d.get("startup_command", "")
        s.auto_reconnect = bool(d.get("auto_reconnect", True))
        s.keepalive = int(d.get("keepalive", 30) or 30)
        s.description = d.get("description", "")
        s.tags = list(d.get("tags", []))
        s.forwards = [Forward.from_dict(f) for f in d.get("forwards", [])]
        s.agent_forwarding = bool(d.get("agent_forwarding", False))
        s.compression = bool(d.get("compression", True))
        s.domain = d.get("domain", "")
        s.rdp_width = int(d.get("rdp_width", 1600) or 1600)
        s.rdp_height = int(d.get("rdp_height", 900) or 900)
        s.rdp_color_depth = int(d.get("rdp_color_depth", 32) or 32)
        s.rdp_fullscreen = bool(d.get("rdp_fullscreen", False))
        s.rdp_fit_screen = bool(d.get("rdp_fit_screen", False))
        s.rdp_clipboard = bool(d.get("rdp_clipboard", True))
        s.rdp_drives = bool(d.get("rdp_drives", False))
        s.rdp_cert_ignore = bool(d.get("rdp_cert_ignore", False))
        s.rdp_pass_on_cmdline = bool(d.get("rdp_pass_on_cmdline", False))
        s.rdp_gateway_host = d.get("rdp_gateway_host", "")
        s.rdp_gateway_port = int(d.get("rdp_gateway_port", 443) or 443)
        s.rdp_gateway_user = d.get("rdp_gateway_user", "")
        s.options = dict(d.get("options", {}))
        s.created_at = float(d.get("created_at", time.time()))
        s.updated_at = float(d.get("updated_at", time.time()))
        return s


def default_port_for(protocol: str) -> int:
    return {PROTOCOL_RDP: 3389, PROTOCOL_SSH: 22, PROTOCOL_LOCAL: 0}.get(protocol, 22)
