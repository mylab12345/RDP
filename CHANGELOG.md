# Changelog

## Unreleased

### Added
- **RDP fits the terminal.** The built-in (in-app) RDP display detects the
  size of the tab's display area and launches the remote desktop at exactly
  that resolution, so the whole screen is visible with no scrolling or
  clipping — and re-fits automatically when the tab is resized. The detected
  size replaces the session's fixed resolution and is clamped to the
  FreeRDP/Windows-supported range.
- **Ctrl+wheel font zoom in terminals.** Ctrl+scroll up grows the terminal
  font, Ctrl+scroll down shrinks it (6–48 pt). Scoped to terminal widgets
  only — the RDP view is unaffected.
- **Tab now autocompletes in the terminal.** Qt was silently consuming Tab
  for focus traversal (it jumped to the toolbar instead of the shell), so
  shell completion never fired inside the app; Tab/Shift+Tab are now routed
  to the shell like in a normal terminal, while Ctrl+Tab still switches tabs.
- **One-click local terminal** — toolbar button, `Session → New local terminal`
  and `Ctrl+Shift+T` open a native shell (real PTY on POSIX, ConPTY on Windows)
  in a tab. Scratch terminals are not written to the saved-session list.
- **Remote monitoring** — live CPU, memory, swap, disk, load, logged-in users
  and network throughput for any SSH session, with sparkline history and a
  selectable refresh interval. Available from the toolbar, `Tools → Remote
  monitor…` (`Ctrl+Shift+M`) or the per-tab **Monitor** button. The probe is a
  single read-only `/proc` script per sample, reusing the existing SSH
  transport.

### Changed
- **Simplified SSH/RDP session editor.** The form now shows host, username and
  password by default; ports, tags, description, jump hosts, keepalives,
  forwards, gateways and certificate options moved behind one **Advanced
  options** disclosure. Auth rows appear only when the selected method uses
  them.
- **Simplified RDP display setup.** Two spin boxes, a colour-depth combo and
  two checkboxes are replaced by a single **Display** dropdown (Fit to window /
  Fullscreen / common resolutions / Custom…).

### Performance
- Terminal rendering is ~2.3x faster: consecutive same-style cells are batched
  into single `drawText` calls, the palette and font variants are cached
  instead of rebuilt every frame, and only the invalidated rows are repainted.
- Terminal output repaints are capped at ~60 fps and can no longer be starved
  indefinitely by a fast writer (`yes`, large `cat`).
- Window resizing is debounced, so dragging an edge no longer sends a PTY
  resize per pixel.
- Cursor blink repaints only the cursor cell instead of the whole widget.
- The RDP **Test server** probe runs off the GUI thread — it previously froze
  the whole application for up to 5 seconds.
- Sidebar search is debounced and the tree is rebuilt in a single batch.

### Security
- RDP passwords are no longer placed on the FreeRDP command line by default;
  they are passed over stdin, so other local users can no longer read them via
  `ps` / `/proc/<pid>/cmdline` (CWE-214). The old behaviour remains as an
  explicit, clearly-labelled opt-in.
- The configuration directory and `sessions.json` (which may hold plain-text
  passwords) are created `0700`/`0600`; pre-existing lax permissions are
  tightened on startup (CWE-276).
- Generated `.rdp` files are written `0600` and their names sanitised, closing
  a path-traversal via the session display name (CWE-22).
- SFTP downloads are confined to the destination directory, so a hostile server
  cannot escape it with `..` entries ("Zip-Slip"), and non-regular files are
  skipped.
- OSC-52 clipboard writes are no longer re-applied on every subsequent chunk
  (a remote host could hold the local clipboard hostage) and oversized payloads
  are rejected.
- Dependency floors raised past known CVEs: `paramiko>=3.4.1`
  (CVE-2023-48795, Terrapin) and `cryptography>=44.0.1` (CVE-2024-12797).

### Fixed
- Local shell: the PTY master is no longer closed while the reader thread is
  still blocked on it (which could stream an unrelated file into the terminal);
  the child's whole process group is signalled on close; a failed `Popen` no
  longer leaks a PTY pair; a bad shell command now reports an error instead of
  showing a dead "connected" tab; Reconnect works after the shell exits.
- Terminal: bold/italic no longer leak into later frames via the shared font
  object; the scrollbar sync no longer re-enters itself; the tab title is only
  re-emitted when it actually changes.
- Icon fallback no longer leaks a `QLabel` per icon and no longer aborts when
  used before a `QGuiApplication` exists.
- Session import validates its input, bounds the file size and no longer leaks
  a file handle; export reports errors instead of raising.
- `subprocess` timeouts/missing binaries are handled in the RDP server manager.

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
