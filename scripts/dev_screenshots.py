#!/usr/bin/env python3
"""Developer helper: render the GUI offscreen and capture screenshots.

Usage:
    QT_QPA_PLATFORM=offscreen python scripts/dev_screenshots.py [outdir]

Populates a demo state dir, opens a local-shell tab, a real SSH tab (if the
sandbox sshd from tests is reachable) and dialogs, and saves PNGs.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

STATE = Path(tempfile.mkdtemp(prefix="rdpstudio-shots-"))
os.environ["KB_REMOTE_HOME"] = str(STATE)


def spawn_test_sshd() -> tuple[subprocess.Popen, int, str, str] | None:
    """Start the same throwaway sshd the test-suite uses."""
    import shutil
    import socket

    sshd_bin = shutil.which("sshd") or "/usr/sbin/sshd"
    if not Path(sshd_bin).exists():
        return None
    base = Path(tempfile.mkdtemp(prefix="rdpstudio-shotsshd-"))
    hk, ck, ak = base / "h", base / "c", base / "a"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(hk)], check=True)
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(ck)], check=True)
    ak.write_text(ck.with_suffix(".pub").read_text())
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    cfg = base / "cfg"
    cfg.write_text(
        f"Port {port}\nListenAddress 127.0.0.1\nHostKey {hk}\nAuthorizedKeysFile {ak}\n"
        "StrictModes no\nUsePAM no\nSubsystem sftp internal-sftp\nLogLevel ERROR\n"
    )
    proc = subprocess.Popen([sshd_bin, "-f", str(cfg), "-D", "-E", str(base / "log")])
    time.sleep(0.5)
    return proc, port, os.environ.get("USER", "user"), str(ck)


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from rdpstudio.app import build_context
    from rdpstudio.core.models import PROTOCOL_LOCAL, PROTOCOL_RDP, PROTOCOL_SSH, Forward, Session
    from rdpstudio.ui import theme
    from rdpstudio.ui.main_window import MainWindow

    app = QApplication([])
    theme.apply_theme(app, "mobaxterm")
    ctx = build_context()

    # offscreen: replace GUI prompts with automatic answers
    from rdpstudio.ui.prompter import HeadlessPromptProvider

    ctx.prompter = HeadlessPromptProvider(accept_host_keys=True)

    # --- demo saved sessions ----------------------------------------------
    prod = Session(name="web-01", protocol=PROTOCOL_SSH, host="10.20.1.11", username="deploy", group="Production", tags=["web"])
    prod.forwards.append(Forward(kind="local", listen_port=8080, dest_host="10.20.1.11", dest_port=80, name="http"))
    ctx.store.upsert(prod)
    ctx.store.upsert(Session(name="db-primary", protocol=PROTOCOL_SSH, host="10.20.1.20", port=22, username="root", group="Production"))
    ctx.store.upsert(Session(name="win-jump-01", protocol=PROTOCOL_RDP, host="10.20.2.31", username="administrator", group="Windows", rdp_width=1920, rdp_height=1080))
    ctx.store.upsert(Session(name="win10-lab", protocol=PROTOCOL_RDP, host="10.20.2.40", username="labuser", group="Windows", rdp_drives=True))
    ctx.store.upsert(Session(name="bastion", protocol=PROTOCOL_SSH, host="bastion.example.net", username="ops", group=""))

    sshd = spawn_test_sshd()

    win = MainWindow(ctx)
    win.resize(1360, 840)
    win.show()
    app.processEvents()

    # --- local shell tab with real output ------------------------------------
    local = Session(name="local bash", protocol=PROTOCOL_LOCAL)
    local.options["command"] = "/bin/bash"
    tab_local = win.open_session(local)
    _type_and_wait(app, tab_local, [
        "ls --color=always /usr | head -8",
        "echo 'KB-Remote local shell: colors ✔ tabs ✔'",
    ])
    shot = win.grab()
    shot.save(str(OUT / "main-window.png"))

    # --- real SSH tab ----------------------------------------------------------
    if sshd:
        proc, port, user, key = sshd
        ssh_defn = Session(name=f"ssh@localhost:{port}", protocol=PROTOCOL_SSH,
                           host="127.0.0.1", port=port, username=user, auth="key", key_path=key)
        tab_ssh = win.open_session(ssh_defn)
        _type_and_wait(app, tab_ssh, [
            "echo connected via paramiko over $(uname -s)",
            "df -h / | tail -1",
            "free -m | head -2",
        ])
        shot = win.grab()
        shot.save(str(OUT / "ssh-session.png"))
        # tunnels dialog
        from rdpstudio.ui.tunnels_dialog import TunnelsDialog
        ssh_defn.forwards.append(Forward(kind="dynamic", listen_port=1080))
        ssh_defn.forwards.append(Forward(kind="local", listen_port=5432, dest_host="db.internal", dest_port=5432))
        dlg = TunnelsDialog(ctx, tab_ssh.controller, win)
        dlg.resize(780, 440)
        dlg.show()
        app.processEvents()
        dlg.grab().save(str(OUT / "tunnels.png"))
        dlg.close()

    # --- session editor -----------------------------------------------------------
    from rdpstudio.ui.session_dialog import SessionDialog
    dlg = SessionDialog(
        ctx, Session(protocol=PROTOCOL_RDP, host="10.20.2.55", port=3389,
                     username="admin", rdp_fit_screen=True), win
    )
    dlg.resize(620, 760)
    app.processEvents()
    dlg.grab().save(str(OUT / "session-editor.png"))
    dlg.deleteLater()

    # --- vault ---------------------------------------------------------------
    from rdpstudio.ui.vault_dialog import VaultDialog
    ctx.vault.create("demo-master-pass")
    from rdpstudio.core.vault import Credential
    ctx.vault.put(Credential(name="prod root", kind="password", username="root", secret="demo-secret"))
    ctx.vault.put(Credential(name="win admin", kind="password", username="Administrator", secret="demo-secret"))
    dlg = VaultDialog(ctx, win)
    dlg.resize(900, 560)
    app.processEvents()
    dlg.grab().save(str(OUT / "vault.png"))
    dlg.deleteLater()

    # --- RDP server manager ------------------------------------------------------
    from rdpstudio.ui.rdp_server_dialog import RdpServerDialog
    dlg = RdpServerDialog(win)
    dlg.resize(660, 430)
    app.processEvents()
    dlg.grab().save(str(OUT / "rdp-server-manager.png"))
    dlg.deleteLater()

    win.close()
    app.processEvents()

    if sshd:
        sshd[0].terminate()
    print(f"screenshots → {OUT}")
    return 0


def _type_and_wait(app, tab, commands: list[str]) -> None:
    """Send commands to a tab and wait for the last one to show up."""
    core = tab.controller.term.core
    for cmd in commands:
        last = cmd.split("|")[0].strip()
        needle = last[-18:] if len(last) > 18 else last
        tab.controller.term.send_text(cmd + "\n")
        deadline = time.time() + 6
        while time.time() < deadline:
            app.processEvents()
            body = "\n".join(core.line_at(i) for i in range(core.total_lines()))
            if needle and needle in body:
                break
            time.sleep(0.03)


if __name__ == "__main__":
    raise SystemExit(main())
