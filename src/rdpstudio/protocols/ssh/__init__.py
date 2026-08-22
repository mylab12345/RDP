"""SSH protocol plugin (built-in).

Importing this package registers the SSH plugin with the global registry.
"""

from ...core.plugin import registry


def _register() -> None:
    from .session import SshPlugin

    registry().register(SshPlugin())


_register()
