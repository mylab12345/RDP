# Architecture

RDP Studio is a desktop remote-access workbench. The design goals, in order:

1. **Secure by default** — secrets encrypted at rest, host keys verified,
   logs redacted.
2. **Modular protocols** — every protocol is a plugin behind a small contract;
   the UI never special-cases transport code.
3. **Responsive UI** — all blocking I/O lives on worker threads; the GUI
   thread only renders and dispatches.
4. **Testable without a GUI** — the terminal emulator, crypto, store,
   forwarder and negotiator are pure-Python cores with Qt only at the edges.

## Layer map

```
┌──────────────────────────────────────────────────────────────────┐
│ UI (PySide6/Qt6)                                                 │
│  MainWindow · SessionTab · SessionTree(sidebar) · TerminalView   │
│  SessionDialog · VaultDialog · SftpDialog · TunnelsDialog        │
│  RdpServerDialog · SettingsDialog · GuiPromptProvider            │
├──────────────────────────────────────────────────────────────────┤
│ Plugin layer (rdpstudio.core.plugin)                             │
│  ProtocolPlugin  ← describe protocol, build editor pages         │
│  SessionController ← one live session; Qt signals for state      │
│  PluginRegistry  ← built-ins + entry-point discovery             │
│  SessionContext  ← settings/store/vault/bus/prompter services    │
├───────────────────────┬──────────────────────┬───────────────────┤
│ protocols/ssh         │ protocols/rdp        │ protocols/local   │
│  SshWorker (thread)   │  negotiate.py (X.224)│  PTY / ConPTY     │
│  TunnelManager        │  rdpfile.py (.rdp)   │  LocalShell       │
│  SftpEngine (thread)  │  RdpSession (proc)   │                   │
│  KnownHostsVerifier   │  servermgr.py        │                   │
│  keys.py              │                      │                   │
├───────────────────────┴──────────────────────┴───────────────────┤
│ Core                                                              │
│  SessionStore (JSON) · CredentialVault (AES-GCM) · crypto         │
│  Settings · EventBus · ReconnectPolicy · logging(redaction)      │
└──────────────────────────────────────────────────────────────────┘
```

## Threading model (the part that must never regress)

- **GUI thread** owns all widgets. Controllers live here.
- **SSH worker thread** (one `QThread` per session) owns the paramiko
  `SSHClient`, the shell channel pump, and the `TunnelManager`. GUI → worker
  communication goes through bridge signals (`Signal(bytes) → @Slot`) which Qt
  queues automatically; worker → GUI via signals emitted on the worker thread.
  Two hard rules learned the hard way:
  1. Connect `QThread.started` **directly to a worker slot** (the receiver's
     thread decides where a queued connection runs — a controller method would
     drag the blocking pump into the GUI thread).
  2. Widgets/timers are never touched from reader threads; data crosses via
     signals (`_sigFeed`).
- **SFTP engine thread** (one per transfer window) borrows the *existing*
  paramiko transport — transports multiplex channels and are thread-safe, so
  browsing/transferring never blocks the shell pump.
- **Tunnel connection threads** are daemon threads per accepted connection,
  owned by `TunnelManager` on the worker thread.
- **Local shells**: POSIX PTY with a reader thread; Windows ConPTY
  (`pywinpty`, optional) or a `QProcess` fallback.

## Key flows

### Connect (SSH)

```
SessionTree double-click → MainWindow.open_session(defn)
  → SshPlugin.create_session(defn, ctx) → SshSessionController
  → SessionTab(hosts widget + status header) added to QTabWidget
  → controller.start()
      → resolve AuthMaterial (vault → password/key/passphrase, jump chain)
      → QThread + SshWorker.moveToThread
      → thread.started → worker.connect_and_shell()   [worker thread]
             resolve jump chain (nested clients, direct-tcpip sock)
             KnownHostsVerifier → (prompt via thread-safe bridge)
             auth: agent → key → vault password → prompt (≤3 rounds)
             open_session → get_pty → invoke_shell
             start enabled forwards (TunnelManager)
             pump loop: select(chan) → output(bytes) → GUI → TerminalView.feed
```

### Reconnect

`disconnected` (unexpected) → controller sets RECONNECTING → `ReconnectPolicy`
computes exponential backoff with jitter → `QTimer.singleShot` → fresh worker.
Attempt count and delay are surfaced through `reconnectScheduled(attempt, delay)`
so the tab shows a live countdown chip.

### RDP

`RdpSessionController` runs the session in one of two display modes
(Settings → Connection → **RDP display**: `auto` (default) / `embedded` /
`external`):

- **Built-in (embedded, Linux/X11)** — the FreeRDP client is launched with
  `/parent-window:<xid> -decorations`, so the remote desktop renders *inside
  the app's tab* (no separate RDP window). The tab hosts a native X11
  surface (`_EmbeddedSurface`); resizing the tab restarts the client so the
  desktop refits. Requires the **X11** FreeRDP flavour (`xfreerdp*` — the SDL
  client ignores `/parent-window`) + the Qt `xcb` platform + `$DISPLAY`.
  On **Wayland** sessions, `protocols/rdp/embed.py` restarts the process with
  `QT_QPA_PLATFORM=xcb` (XWayland) before the QApplication exists when RDP is
  in play — guarded by `RDPSTUDIO_XWAYLAND` (no restart loops) and a
  self-check that drops back to the native platform if xcb can't load.
- **External** — Windows → generate a `.rdp` file (UTF-16) and launch
  `mstsc.exe`; Linux → launch `sdl-freerdp3`/`xfreerdp` with flags
  (drive/clipboard/gateway, `+auto-reconnect`, `/cert:tofu` unless the user
  opted out). The tab becomes a monitor (process state, reconnect); when the
  only obstacle to the built-in display is Wayland, it offers a *Show inside
  app* button that triggers the XWayland restart.

In both modes the tab also shows X.224 probe results.
`negotiate.py` speaks enough MS-RDPBCGR to distinguish a live RDP server and
its negotiated security (Standard/TLS/CredSSP) — the same handshake mstsc
performs before TLS starts.

## Data on disk

`RDPSTUDIO_HOME` (default `~/.config/rdpstudio`, `%APPDATA%\RDPStudio`):

| File | Contents |
|---|---|
| `sessions.json` | saved sessions/groups — no vault secrets (only `credential_id` references); an opt-in plain per-session password is the one stored secret |
| `vault.bin` | AES-256-GCM envelope (PBKDF2-SHA256; AAD binds KDF params) |
| `known_hosts` | our own TOFU store (never touched without verification) |
| `settings.json` | appearance/terminal/security prefs + window geometry |
| `keys/` | generated private/public keypairs (0600) |
| `logs/` | rotating, secret-redacted logs |

## Extension points

- **Protocols**: entry-point group `rdpstudio.protocols` (see
  [PROTOCOLS.md](PROTOCOLS.md)). A protocol plugin can add a shell-ish widget
  (like SSH/local), an external-window monitor (like RDP), or something new —
  the tab, dialogs, quick-connect and sidebar are protocol-agnostic.
- **Importers**: `rdpstudio.importers` pattern (ssh_config included; PuTTY
  registry importer can follow the same shape).
- **In-process RDP rendering** (future): the built-in mode embeds FreeRDP's
  own X11 window (`/parent-window`), which needs FreeRDP + X11. A fully
  in-process renderer (a `rdpgfx` channel decoder + QOpenGLWidget surface,
  e.g. via FreeRDP's C API or a pure-Python stack) would remove that
  requirement and also work on Wayland/Windows; `negotiate.py` is the first
  step of that path, and the plugin contract stays unchanged.
