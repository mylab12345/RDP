"""Built-in (in-app) RDP display: client discovery, support detection and the
Wayland → XWayland restart.

The remote desktop is rendered by FreeRDP into a *child window* of KB-Remote
itself (``/parent-window``) — no separate OS window, exactly like MobaXterm's
in-tab RDP.  Window reparenting is an X11 mechanism, so this needs:

* an **X11 FreeRDP client** (``xfreerdp3`` / ``xfreerdp2`` / ``xfreerdp``).
  The SDL (``sdl-freerdp``) and Wayland (``wlfreerdp``) clients have no
  ``/parent-window`` support and silently open their own window;
* the app itself running on **X11**.  On Wayland desktops (the default on
  modern Ubuntu/Fedora) that is still possible through **XWayland**, the X11
  compatibility server that ships with every mainstream distribution: we
  restart the process with ``QT_QPA_PLATFORM=xcb`` so the whole app — embedded
  desktop included — runs through XWayland inside the Wayland session.

The restart is transparent: it happens automatically at startup when the user
has saved RDP sessions, and on demand (a button in the RDP tab / settings)
otherwise.  A guard environment variable prevents restart loops, and if the
xcb platform cannot load in the restarted process it falls back to the native
platform (external RDP window) instead of failing to start.
"""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from ...core.log import get_logger

log = get_logger("rdp.embed")

# FreeRDP flavors that can render into a parent window. The SDL/Wayland
# clients ignore /parent-window, so they are only used for external windows.
EMBEDDABLE_CLIENTS = ("xfreerdp3", "xfreerdp2", "xfreerdp")

# Set on the restarted process so it never restarts again (loop guard), and
# consumed by the app entry point to sanity-check the xcb platform.
RELAUNCH_ENV = "RDPSTUDIO_XWAYLAND"
RELAUNCH_FALLBACK_ENV = RELAUNCH_ENV + "_FALLBACK"


def find_embedded_client(
    which: Callable[[str], str | None] | None = None,
) -> str | None:
    """Locate an X11 FreeRDP client able to render into a parent window."""
    which = which or shutil.which
    for name in EMBEDDABLE_CLIENTS:
        path = which(name)
        if path:
            return path
    return None


def xwayland_available(display: str | None = None) -> bool:
    """Whether an X server (native X11 session or XWayland) is reachable."""
    disp = display if display is not None else os.environ.get("DISPLAY")
    return bool(disp)


def wayland_session(env: dict | None = None) -> bool:
    """Whether this process would run as a native Wayland client.

    ``WAYLAND_DISPLAY`` is set whenever a Wayland compositor socket exists —
    which is also exactly when Qt picks its ``wayland`` platform.
    """
    env = env if env is not None else os.environ
    return bool(env.get("WAYLAND_DISPLAY"))


def _platform_name(platform_name: str | None) -> str:
    if platform_name is not None:
        return platform_name
    app = None
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
    except Exception:  # no Qt yet (startup relaunch path)
        pass
    if app is not None:
        return app.platformName() or ""
    return "wayland" if wayland_session() else ""


def embedded_support(
    find_client: Callable | None = None,
    platform_name: str | None = None,
    display: str | None = None,
    find_embedded: Callable[[], str | None] | None = None,
) -> tuple[bool, str]:
    """Whether the built-in (embedded) RDP display is possible *right now*.

    Requires: an X11 FreeRDP binary (mstsc cannot embed and neither can the
    SDL/Wayland FreeRDP clients), the Qt X11 platform and an X display
    (native X11 or XWayland).  Returns ``(ok, reason)`` — the reason doubles
    as a UI hint and is kept actionable.
    """
    from .session import find_rdp_client

    client = (find_client or find_rdp_client)()
    if client is None:
        return False, "No FreeRDP client found (install `freerdp3-x11` or `freerdp2-x11`)."
    if client[1] != "freerdp":
        return False, "Only FreeRDP can render inside the app (mstsc cannot be embedded)."
    embedded_client = (find_embedded or find_embedded_client)()
    if embedded_client is None:
        return (
            False,
            "The installed FreeRDP (SDL/Wayland flavour) cannot embed. "
            "Install the X11 client: `sudo apt install freerdp3-x11` (or freerdp2-x11).",
        )
    name = _platform_name(platform_name)
    disp = display if display is not None else os.environ.get("DISPLAY")
    if name != "xcb":
        if name == "wayland" and disp:
            return (
                False,
                "In-app RDP needs X11. Restart via XWayland (X11 compatibility) "
                "to render the desktop inside KB-Remote.",
            )
        return False, f"Built-in display needs X11 (current Qt platform: {name or 'none'})."
    if not disp:
        return False, "No X display ($DISPLAY) available."
    return True, ""


def embed_blocked_on_wayland(
    platform_name: str | None = None,
    display: str | None = None,
    find_embedded: Callable[[], str | None] | None = None,
) -> bool:
    """True when Wayland is the *only* obstacle — i.e. restarting the app
    through XWayland would enable the built-in display right away."""
    if _platform_name(platform_name) != "wayland":
        return False
    return xwayland_available(display) and (find_embedded or find_embedded_client)() is not None


def should_relaunch_for_embedded(
    settings,
    store,
    platform_name: str,
    display: str | None = None,
    find_embedded: Callable[[], str | None] | None = None,
    env: dict | None = None,
    rdp_target: bool = False,
) -> tuple[bool, str]:
    """Decide whether to restart the app via XWayland for in-app RDP.

    Pure decision logic (fully injectable → unit tested).  Relaunch when the
    session is Wayland, XWayland + an X11 FreeRDP client are available, the
    user did not opt for external windows, and RDP is actually in play: a
    saved RDP session exists, a command-line RDP target was given, or the
    built-in display is explicitly requested.
    """
    env = env if env is not None else os.environ
    if env.get(RELAUNCH_ENV) == "1":
        return False, "already restarted for XWayland in this process"
    pref = getattr(settings, "rdp_client", "auto")
    if pref == "external":
        return False, "external RDP window preferred (Settings → Connection)"
    forced = env.get("QT_QPA_PLATFORM", "")
    if forced and forced != "wayland":
        return False, f"QT_QPA_PLATFORM={forced} was set explicitly — respecting it"
    if platform_name != "wayland":
        return False, f"not a Wayland session ({platform_name or 'unknown'})"
    if not xwayland_available(display):
        return False, "no XWayland available ($DISPLAY unset) — external window will be used"
    if (find_embedded or find_embedded_client)() is None:
        return False, "no X11 FreeRDP client (install freerdp3-x11 / freerdp2-x11)"
    if pref == "auto" and not rdp_target:
        if not any(getattr(s, "protocol", "") == "rdp" for s in store.sessions()):
            return False, "no saved RDP sessions — nothing to gain from a restart"
    return True, "restart via XWayland so RDP renders inside the app"


def relaunch_under_x11(argv: list[str] | None = None) -> None:
    """Restart this process as an X11 (XWayland) client.  Never returns on
    success; returns (with the env restored) if ``execv`` itself fails."""
    argv = list(sys.argv[1:] if argv is None else argv)
    prev_platform = os.environ.get("QT_QPA_PLATFORM")
    os.environ[RELAUNCH_ENV] = "1"
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    log.info("restarting KB-Remote via XWayland for the built-in RDP display")
    try:
        if getattr(sys, "frozen", False):  # PyInstaller build
            os.execv(sys.executable, [sys.executable, *argv])
        else:
            os.execv(sys.executable, [sys.executable, "-m", "rdpstudio", *argv])
    except OSError as exc:  # pragma: no cover - exec hardly ever fails
        log.error("XWayland restart failed: %s", exc)
        os.environ.pop(RELAUNCH_ENV, None)
        # Restore whatever the user/session had before (possibly nothing).
        if prev_platform is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = prev_platform


def _cli_rdp_target(argv: list[str], store) -> bool:
    """Whether a command-line argument will open an RDP session."""
    if not argv:
        return False
    saved = store.get(argv[0])
    if saved is not None:
        return saved.protocol == "rdp"
    # quick connect: user@host[:port] — RDP when the port says so (3389)
    try:
        from ..ssh.session import parse_ssh_target

        parsed = parse_ssh_target(argv[0])
        if parsed is not None and parsed[2] == 3389:
            return True
    except Exception:
        pass
    return False


def maybe_relaunch_for_embedded(
    argv: list[str] | None = None,
    *,
    settings=None,
    store=None,
    env: dict | None = None,
    wayland: bool | None = None,
    display: str | None = None,
    find_embedded: Callable[[], str | None] | None = None,
    relaunch: Callable[[list[str]], None] | None = None,
) -> bool:
    """Startup hook: restart via XWayland when that enables in-app RDP.

    Called from :func:`rdpstudio.app.main` *before* the QApplication is
    created (the platform is fixed at construction time).  Returns True when
    a restart was triggered (the caller should not continue — though the
    exec makes that moot in practice).
    """
    env = env if env is not None else os.environ
    is_wayland = wayland if wayland is not None else wayland_session(env)
    if not is_wayland:
        return False
    if settings is None or store is None:
        from ...core.paths import sessions_file, settings_file
        from ...core.settings import Settings
        from ...core.store import SessionStore

        settings = settings or Settings.load(settings_file())
        store = store or SessionStore(sessions_file())
    ok, why = should_relaunch_for_embedded(
        settings,
        store,
        platform_name="wayland",
        display=display,
        find_embedded=find_embedded,
        env=env,
        rdp_target=_cli_rdp_target(list(argv or []), store),
    )
    if not ok:
        log.debug("XWayland restart not needed: %s", why)
        return False
    (relaunch or relaunch_under_x11)(list(argv or []))
    return True


def xcb_platform_ready() -> bool:
    """Whether the Qt xcb platform plugin can actually load here (its X11
    shared-library dependencies resolve).  Used as a self-check in the
    restarted process so a broken system degrades to the external window
    instead of the app failing to start."""
    try:
        from PySide6.QtCore import QLibrary, QLibraryInfo
    except Exception:  # pragma: no cover - PySide6 always present in practice
        return False
    try:
        plugins = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    except Exception:  # older PySide6 enum layout
        return False
    for name in ("libqxcb.so", "libqxcb.dylib", "qxcb.dll"):
        lib = QLibrary(str(Path(plugins) / "platforms" / name))
        if lib.load():
            return True
    return False


def xcb_relaunch_self_check(env: dict | None = None) -> bool:
    """In the restarted process: keep xcb only when it truly works.

    Returns True when the current platform choice is fine; if xcb cannot
    load, drops ``QT_QPA_PLATFORM`` so Qt falls back to the native platform
    and marks the fallback (the RDP tab then offers the external window).
    """
    env = env if env is not None else os.environ
    if env.get(RELAUNCH_ENV) != "1" or env.get("QT_QPA_PLATFORM") != "xcb":
        return True
    if xcb_platform_ready():
        return True
    log.warning("XWayland restart: xcb platform cannot load — staying on the native platform")
    env.pop("QT_QPA_PLATFORM", None)
    env[RELAUNCH_FALLBACK_ENV] = "1"
    return False
