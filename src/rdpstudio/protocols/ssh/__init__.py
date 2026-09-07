"""SSH protocol package.

The package itself is side-effect free so key, forwarding, and host-file
helpers remain importable in headless tools.  The global plugin registry loads
:class:`.session.SshPlugin` explicitly when the application starts.
"""
