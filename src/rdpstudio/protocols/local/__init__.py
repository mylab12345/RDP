"""Local shell protocol plugin (built-in)."""

from ...core.plugin import registry


def _register() -> None:
    from .session import LocalShellPlugin

    registry().register(LocalShellPlugin())


_register()
