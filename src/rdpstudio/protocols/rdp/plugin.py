"""Pure RDP plugin descriptor.

The descriptor stays importable without QtWidgets; the heavyweight controller
is loaded lazily only when the app opens a real RDP session.
"""

from __future__ import annotations

from ...core.models import Session
from ...core.plugin import ProtocolPlugin, SessionContext, SessionController
from ..ssh.target import parse_ssh_target


class RdpPlugin(ProtocolPlugin):
    id = "rdp"
    title = "RDP"
    description = "Remote Desktop to Windows hosts — built-in display (FreeRDP embedded) or mstsc/FreeRDP window."
    default_port = 3389
    icon_name = "windows"
    tags = ["rdp", "windows", "remote-desktop"]

    def create_session(self, definition: Session, ctx: SessionContext) -> SessionController:
        from .session import RdpSessionController

        return RdpSessionController(definition, ctx)

    def quick_connect_target(self, text: str) -> Session | None:
        parsed = parse_ssh_target(text)
        if parsed is None:
            return None
        user, host, port = parsed
        if port != 3389:
            return None
        session = Session(protocol="rdp", host=host, port=3389, username=user or "")
        session.name = session.target()
        return session


__all__ = ["RdpPlugin"]
