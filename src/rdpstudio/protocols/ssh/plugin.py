"""Pure SSH plugin descriptor.

This module keeps quick-connect parsing and plugin registration importable
without QtWidgets. The session controller itself is imported lazily only when
an actual SSH session is created.
"""

from __future__ import annotations

from ...core.models import Session
from ...core.plugin import ProtocolPlugin, SessionContext, SessionController
from .target import parse_ssh_target


class SshPlugin(ProtocolPlugin):
    id = "ssh"
    title = "SSH"
    description = "Secure shell/OpenSSH to Linux, Windows, BSD and macOS hosts: terminal, SFTP, tunnels."
    default_port = 22
    icon_name = "terminal"
    tags = ["ssh", "shell", "sftp"]

    def create_session(self, definition: Session, ctx: SessionContext) -> SessionController:
        from .session import SshSessionController

        return SshSessionController(definition, ctx)

    def quick_connect_target(self, text: str) -> Session | None:
        parsed = parse_ssh_target(text)
        if parsed is None:
            return None
        user, host, port = parsed
        session = Session(protocol="ssh", host=host, port=port or 22, username=user or "")
        session.name = session.target()
        return session


__all__ = ["SshPlugin"]
