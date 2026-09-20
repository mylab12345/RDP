"""Pure local-shell plugin descriptor."""

from __future__ import annotations

from ...core.models import Session
from ...core.plugin import ProtocolPlugin, SessionContext, SessionController


class LocalShellPlugin(ProtocolPlugin):
    id = "local"
    title = "Local shell"
    description = "Interactive local terminal (bash/PowerShell) in a tab."
    default_port = 0
    icon_name = "console"
    can_edit = True
    tags = ["local", "shell"]

    def create_session(self, definition: Session, ctx: SessionContext) -> SessionController:
        from .session import LocalShellController

        return LocalShellController(definition, ctx)


__all__ = ["LocalShellPlugin"]
