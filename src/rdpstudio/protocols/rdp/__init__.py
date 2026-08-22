"""RDP protocol plugin (built-in)."""

from ...core.plugin import registry


def _register() -> None:
    from .session import RdpPlugin

    registry().register(RdpPlugin())


_register()
