"""Application entry point.

Run with ``kb-remote`` (installed console script) or ``python -m rdpstudio``.

Usage:
    kb-remote                     # open the GUI
    kb-remote <session-id>        # open + connect a saved session
    kb-remote user@host[:port]    # quick connect (3389 ⇒ RDP)
    kb-remote --version
"""

from __future__ import annotations

import os
import sys


def build_context(home_override: str | None = None, verbose: bool = False):
    """Assemble settings, store, vault, bus and the session context."""
    if home_override:
        os.environ["KB_REMOTE_HOME"] = home_override
    from . import APP_NAME
    from .core import paths
    from .core.events import EventBus
    from .core.log import get_logger, setup_logging
    from .core.plugin import SessionContext
    from .core.settings import Settings
    from .core.store import SessionStore
    from .core.vault import CredentialVault

    setup_logging(paths.logs_dir(), verbose=verbose)
    log = get_logger("app")
    settings = Settings.load(paths.settings_file())
    store = SessionStore(paths.sessions_file())
    vault = CredentialVault(paths.vault_file(), settings.kdf_iterations)
    bus = EventBus()

    from .ui.prompter import GuiPromptProvider

    ctx = SessionContext(
        settings=settings,
        store=store,
        vault=vault,
        bus=bus,
        prompter=GuiPromptProvider(None),
        parent_widget=None,
    )
    log.info("%s starting (config dir: %s)", APP_NAME, paths.app_dir())
    return ctx


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    verbose = False
    if "--verbose" in argv:
        verbose = True
        argv.remove("--verbose")
    if "-v" in argv:
        verbose = True
        argv.remove("-v")
    if "--version" in argv:
        from . import __version__

        print(f"kb-remote {__version__}")
        return 0
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    from PySide6.QtWidgets import QApplication

    from . import APP_NAME, ORG_NAME, __version__
    from .protocols.rdp.embed import maybe_relaunch_for_embedded, xcb_relaunch_self_check
    from .ui import theme

    # On Wayland desktops, restart via XWayland *before* the QApplication
    # exists so the built-in RDP display (X11 window embedding) can work —
    # no-op unless the session is Wayland, XWayland + an X11 FreeRDP client
    # are available and RDP is actually in play.
    maybe_relaunch_for_embedded(argv)
    # In the restarted process: if xcb cannot load, fall back gracefully.
    xcb_relaunch_self_check()

    # AA_UseHighDpiPixmaps is deprecated and always-on in Qt 6; setting it
    # only emits a warning.
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    ctx = build_context(verbose=verbose)
    theme.apply_theme(app, ctx.settings.theme)

    from .ui.main_window import MainWindow

    win = MainWindow(ctx)
    ctx.prompter._parent = win  # prompts parent to the main window
    win.show()

    # optional startup target (session id or user@host)
    if argv:
        target = argv[0]
        defn = ctx.store.get(target)
        if defn is not None:
            win.open_session(defn)
        else:
            from .core.plugin import registry

            for plugin in registry().editable():
                parsed = plugin.quick_connect_target(target)
                if parsed is not None:
                    ctx.store.upsert(parsed)
                    win.sidebar.reload()
                    win.open_session(parsed)
                    break

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
