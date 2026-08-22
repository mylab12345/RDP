# RDP Studio

**A cross-platform remote-access workbench, inspired by MobaXterm.**
Tabbed SSH sessions to Linux hosts, RDP sessions to Windows hosts, an encrypted
credential vault, SFTP file transfer, port forwarding (including SOCKS), and a
plugin architecture for adding protocols — all in one clean, dark-themed GUI.

![Main window](docs/screenshots/main-window.png)

| A live SSH tab (real session) | Session editor |
|---|---|
| ![SSH session](docs/screenshots/ssh-session.png) | ![Session editor](docs/screenshots/session-editor.png) |

| Credential vault & keys | Port forwarding | RDP server manager |
|---|---|---|
| ![Vault](docs/screenshots/vault.png) | ![Tunnels](docs/screenshots/tunnels.png) | ![RDP server](docs/screenshots/rdp-server-manager.png) |

---

## Feature overview

| Area | What you get |
|---|---|
| **SSH (Linux)** | Interactive shells in tabs with a real VT emulator (pyte-based: colors, scrollback, mouse-selection, bracketed paste, OSC-52 clipboard), agent/key/password auth, ProxyJump chaining, compression, keepalives |
| **RDP (Windows)** | RDP sessions via the native client (mstsc on Windows, FreeRDP on Linux) with saved settings, **fit display to screen** (smart sizing), fullscreen, drive/clipboard redirection, RD-gateway; **protocol-level server probes** (X.224 negotiation) to verify reachability + negotiated security; local RDP **server** status/enable/disable |
| **Session manager** | Grouped, searchable sidebar of saved sessions; quick connect (`user@host[:port]`, port 3389 ⇒ RDP); duplicate/import/export; import from `~/.ssh/config` |
| **Credentials** | Simple path: type a **username + password** per session (stored in the sessions file — no vault required). Power path: AES-256-GCM encrypted vault under a master passphrase (PBKDF2-SHA256, 310k iterations default), auto-lock, redacted logging; SSH key generation (Ed25519/ECDSA/RSA) with passphrases stored in the vault |
| **File transfer** | Dual-pane SFTP browser (remote ⇄ local), recursive uploads/downloads with progress + cancel, context menus, drag-friendly workflow |
| **Port forwarding** | Local, remote and **dynamic (SOCKS5)** tunnels per session, runtime start/stop, forward events surfaced in the UI |
| **Reconnect** | Exponential backoff + jitter, attempt limits, live status chips; FreeRDP `+auto-reconnect` for RDP |
| **Clipboard** | Copy-on-select, middle-click paste, Ctrl+Shift+C/V, multi-line paste confirmation, OSC-52 (`\x1b]52`) support, RDP clipboard redirection |
| **Security** | TOFU host-key verification with loud changed-key warnings (own `known_hosts`), vault secrets never in session store (a plain password is only written if you explicitly save it), passwords never exported, atomic encrypted vault writes (0600) |
| **Extensible** | Every protocol is a plugin; third parties register protocols via the `rdpstudio.protocols` entry point (see [docs/PROTOCOLS.md](docs/PROTOCOLS.md)) |

Runs on **Linux and Windows** (and the codebase is macOS-friendly), Python ≥ 3.10, Qt 6.

## Install

### Linux

```bash
# from a checkout
./install.sh                 # venv + pip install . + launcher + .desktop

# or from PyPI-style source
pipx install .               # or: pip install --user rdp-studio
rdpstudio
```

For RDP you'll want FreeRDP: `sudo apt install freerdp3-x11` (or `freerdp2-x11`).

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
rdpstudio
```

RDP uses the built-in `mstsc.exe`. The optional `pywinpty` extra gives local
ConPTY shells: `pip install rdp-studio[win]`.

See [docs/INSTALL.md](docs/INSTALL.md) for details, PyInstaller builds
(`packaging/rdpstudio.spec`), and the Inno Setup installer
(`packaging/windows/RDPStudio.iss`).

## Quick start

1. Launch `rdpstudio`.
2. **Session → New session** (Ctrl+N) → pick *SSH terminal* or *RDP remote
   desktop* → fill **Host**, **Username** and **Password** → *Save*. No vault
   needed — the password is stored with the session (leave it empty and you'll
   be asked at connect time). For RDP, tick **Fit display to screen** to scale
   the remote desktop to the window.
3. Double-click the session in the sidebar. Use **Files** / **Tunnels** on the
   tab header for SFTP and port forwarding.
4. Or just type `root@10.0.0.9:2222` into the quick-connect box and hit ⏎.
5. *(Optional)* **Tools → Credential vault** (Ctrl+Shift+K) → keep passwords in
   an encrypted vault instead of the session file.

## Scope note on RDP

RDP remoting is delegated to the platform's native client (`mstsc` /
FreeRDP) — the same approach used by Remina and mRemoteNG — because no
licenseable embeddable RDP client exists. RDP Studio adds protocol-level
*RDP server probing* (real X.224/TPKT negotiation in pure Python), session
settings management, gateway support, auto-reconnect, and local server
enable/disable. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the
roadmap toward in-process RDP rendering.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest                # includes live end-to-end tests against a local sshd
ruff check src tests
python scripts/dev_screenshots.py docs/screenshots   # offscreen GUI captures
```

The test-suite spins up a throwaway `sshd` (key auth + SFTP subsystem) and
exercises the *real* worker, tunnels (local + SOCKS5), TOFU host-key flow and
SFTP round-trips — skipped automatically if no `sshd` is available.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — layers, threading model, data flow
- [docs/PROTOCOLS.md](docs/PROTOCOLS.md) — writing protocol plugins
- [docs/SECURITY.md](docs/SECURITY.md) — threat model, vault design, host-key policy
- [docs/INSTALL.md](docs/INSTALL.md) — per-OS install, packaging, CI builds

## License

MIT (see [LICENSE](LICENSE)).
