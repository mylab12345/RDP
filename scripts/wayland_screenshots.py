#!/usr/bin/env python3
"""Capture the Wayland/XWayland RDP UI (offscreen) for docs.

Shows what an RDP tab and Settings look like on a Wayland desktop before the
XWayland restart: the "Show inside app" button, the explanatory note, and the
Settings hint + restart button.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
STATE = Path(tempfile.mkdtemp(prefix="rdpstudio-wayland-shots-"))
os.environ["RDPSTUDIO_HOME"] = str(STATE)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from rdpstudio.app import build_context
    from rdpstudio.core.models import Session
    from rdpstudio.protocols.rdp import embed
    from rdpstudio.protocols.rdp import session as rdp_session
    from rdpstudio.ui.main_window import MainWindow
    from rdpstudio.ui.settings_dialog import SettingsDialog

    app = QApplication([])

    # simulate the user's machine: Wayland + XWayland + xfreerdp present,
    # so the only obstacle to the in-app desktop is the Wayland session
    rdp_session.embed_blocked_on_wayland = lambda *a, **k: True
    embed.embedded_support = lambda **k: (
        False,
        "In-app RDP needs X11. Restart via XWayland (X11 compatibility) "
        "to render the desktop inside RDP Studio.",
    )

    ctx = build_context(home_override=str(STATE))
    win = MainWindow(ctx)
    win.resize(1180, 760)
    win.show()
    app.processEvents()

    defn = Session(
        name="win-server-01", protocol="rdp", host="192.168.1.50", port=3389,
        username="Administrator", rdp_fit_screen=True,
    )
    ctx.store.upsert(defn)
    win.sidebar.reload()
    win.open_session(defn)
    app.processEvents()
    win.grab().save(str(OUT / "rdp-wayland-inapp.png"))

    dlg = SettingsDialog(ctx, win)
    dlg.resize(560, 560)
    dlg.show()
    app.processEvents()
    dlg.grab().save(str(OUT / "rdp-wayland-settings.png"))
    print("saved:", OUT / "rdp-wayland-inapp.png", "and", OUT / "rdp-wayland-settings.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
