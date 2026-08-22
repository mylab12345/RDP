"""Built-in protocol plugins.

Third-party protocols register via the ``rdpstudio.protocols`` entry point
group; the three built-ins (SSH, RDP, local shell) are imported (and thereby
registered) by :func:`rdpstudio.core.plugin.registry`.
"""
