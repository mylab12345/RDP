# Changelog

## Unreleased

- **In-app RDP on Wayland desktops** (Ubuntu 25+/26.04, Fedora, …): the
  built-in display needs X11 window embedding, so RDP Studio now restarts
  itself through **XWayland** automatically when an RDP session is in play —
  at startup when saved RDP sessions exist, otherwise on demand via a
  **“Show inside app”** button on the RDP tab (and in Settings). The restart
  is loop-guarded (`RDPSTUDIO_XWAYLAND`), respects an explicit
  `QT_QPA_PLATFORM`, and self-checks that the xcb platform can load — if not,
  it stays on the native platform and uses the external window. Opt out any
  time with *Settings → Connection → RDP display → External*.
- **FreeRDP client fix for the built-in display**: only the X11 flavours
  (`xfreerdp3` / `xfreerdp2` / `xfreerdp`) are used for embedding — the SDL
  and Wayland clients silently ignore `/parent-window` and used to open an
  external window anyway. The support hints now say exactly what to install
  (`sudo apt install freerdp3-x11`).
- **Built-in RDP display** (self-contained, no separate window): on Linux,
  FreeRDP is launched with `/parent-window` so the remote desktop renders
  *inside* RDP Studio's tab. Keyboard/mouse are handled by the embedded
  client; resizing the tab refits the desktop. Choose the display in
  **Settings → Connection → RDP display**: *Built-in* / *External window* /
  *Automatic* (default). Falls back to the external window on Windows or
  when FreeRDP/X11 is unavailable.
- Simple connect flow: sessions take a plain **username + password** field
  directly — no vault required (leave the password empty to be asked at
  connect time). Saved passwords are stored in the local sessions file and are
  never included in JSON exports.
- RDP: new **Fit display to screen** option (FreeRDP `/smart-sizing`, mstsc
  smart sizing) that scales the remote desktop to the RDP window.
- The credential vault is now clearly optional everywhere (status bar, docs).

## 0.9.0 — initial release

- Tabbed session manager with grouped, searchable sidebar and quick connect.
- SSH: paramiko-backed shells, PTY terminal emulator (pyte) with 256-color,
  scrollback, selection/clipboard, bracketed paste, OSC-52; agent / key /
  vault-password / interactive-password auth; ProxyJump chaining; compression
  and keepalives; exponential-backoff auto-reconnect.
- SFTP: dual-pane browser, recursive transfers with progress and cancel.
- Port forwarding: local, remote, and dynamic SOCKS5 with runtime control.
- RDP: mstsc/FreeRDP session launching with saved settings (display,
  clipboard/drive redirection, RD gateway, auto-reconnect), pure-Python
  X.224 negotiation probes, local RDP server status/enable-disable.
- Security: AES-256-GCM credential vault (PBKDF2-SHA256), auto-lock,
  TOFU host-key verification with changed-key protection, redacted logging.
- Local shell tabs (PTY on POSIX, ConPTY/pywinpty or cmd fallback on Windows).
- Plugin registry with entry-point discovery (`rdpstudio.protocols`).
- Import from ~/.ssh/config; JSON export/import of sessions.
- Installers for Linux (install.sh) and Windows (install.ps1), PyInstaller
  spec, Inno Setup script, CI + release workflows.
- 54 tests including live end-to-end SSH/SFTP/tunnel coverage against a
  throwaway sshd.
