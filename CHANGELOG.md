# Changelog

## Unreleased

### Added
- **NASA / mission-control chrome.** Workbench QSS restyled as flight-ops
  consoles: NASA red / NASA blue accents, telemetry type, tight radii. Uses
  only system fonts already on the machine — no extra assets.
- **Multiple terminal fonts.** Settings lists a curated set of console
  typefaces (DejaVu, Liberation, Cascadia, Fira, JetBrains, IBM Plex, Hack,
  Consolas, …) plus every monospaced face installed locally, with a live
  preview.
- **App icon.** A new key + terminal mark for KB-Remote (window, launcher, and packaging).
- **Nature themes.** Settings and **View → Theme** now include Forest, Ocean,
  Sunset, Aurora, Meadow and Desert palettes alongside Dark and Light.

### Changed
- **SSH keeps the remote VM’s own console colors.** Opening an SSH session no
  longer applies Tools → Settings theme colors (or the workbench 16-color
  palette) to the terminal. SSH tabs render the classic VGA / linux / xterm
  palette the host itself emits. Theme colors still apply to the workbench
  chrome and to local terminals.
- Removed from the UI: Broadcast input, Command snippets, Port forwarding,
  Multi-host parallel runner, and the Credential vault. Session passwords
  stay on the session itself.

### Added
- **Nature themes (labels).** Forest, Ocean, Sunset, Aurora, Meadow and Desert
  palettes remain available under flight-ops names.

### Changed
- Settings no longer expose **Vault auto-lock** or **KDF iterations**. The
  vault stays unlocked until you lock it; new vaults still use the OWASP
  PBKDF2 default (310k).

### Fixed
- Vault `change_master()` now updates the in-memory master so later auto-saves
  stay encrypted under the new passphrase, and rotating while locked no longer
  writes an empty entry list over existing secrets.
- Corrupt or hand-edited session/settings/vault files no longer crash startup:
  numeric fields, enums, groups and forwards are coerced or skipped, and
  structurally impossible vault envelopes (0 KDF iterations, truncated nonce)
  raise `CryptoError` instead of hanging in the KDF.
- ProxyJump cycles (`A → B → A`) no longer recurse until the stack overflows.
- RDP probe and the port scanner speak IPv6, cap TPKT length so a hostile
  peer cannot balloon the read buffer, and always close sockets.
- Cluster runner always closes the SSH client and bounds captured output.
- Terminal: rich full-screen TUIs (opencode, lazygit, …) rendered flat and
  colorless — grey text on black with occasional raw escape fragments like
  `3m`.  Three gaps, all fixed:
  - pyte reports 256-color and 24-bit RGB cell attributes as hex strings
    *without* the leading `#` ("67e2f9"); the painter only recognized
    `#rrggbb`, names and numeric indices, so every themed color was
    silently dropped back to the default grey.  `#`-less hex is now
    resolved to its true color.
  - xterm OSC 10/11 "what are your default colors?" probes (used by
    opencode to auto-detect dark vs. light themes) were dropped
    unanswered, so the app stalled and guessed the wrong palette.  The
    terminal now replies with the colors it is actually painting (the
    VM's native palette for SSH tabs, the workbench theme for local
    shells).
  - kitty-style SGR colon sub-parameters (`ESC[4:3m` styled underline,
    `ESC[58:2::r:g:bm` underline color) fell outside pyte's grammar and
    leaked onto the screen as literal text; they are normalized down to
    their base attribute before parsing.

### Added
- **MobaXterm-style layout.** The menu bar is reorganised into
  **File / View / Tools / Tabs / Session / Help** (session actions under
  Session, tab actions under Tabs, tools under Tools), and the toolbar is a
  compact icon strip with the quick-connect box centred — the same
  information architecture as MobaXterm, without losing any existing feature
  (SFTP, tunnels, vault, snippets, scanner, cluster, keys and settings all
  remain one click away).
- **Per-tab command line.** Every terminal tab has a MobaXterm-style command
  bar along its bottom edge: type a command and press Enter to run it in
  that terminal (no click-to-focus needed), `Up`/`Down` recalls the tab's
  command history (newest first, consecutive duplicates skipped, capped at
  100 entries). In broadcast mode the bar sends to *all* shell tabs.
- **Docked remote monitor (bottom).** The live CPU / memory / disk / network
  figures for the active SSH session are now available as an always-available
  panel docked along the bottom of the main window (the same probe engine as
  the standalone monitor). It follows the active tab, auto-expands once per
  host on first connect, collapses to a one-line strip, and offers the same
  pause / refresh-interval / **Details** (opens the full monitor window)
  controls. Toggle from the toolbar or `View → Toggle remote monitor panel`.
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
- **Native Linux terminal path.** New local and SSH tabs can use the optional
  QTermWidget/Konsole-style compiled emulator, following the same split as
  SSH Pilot's VTE path: controllers keep ownership of the PTY/SSH transport,
  while VT parsing, scrollback, selection and painting leave Python. Output is
  fed through a lossless non-blocking PTY bridge and input returns as raw bytes.
  The complete pyte renderer remains the automatic fallback when the optional
  binding is absent, incompatible, or the process is headless. Select the
  engine under Settings → Terminal engine or force it with
  `RDPSTUDIO_TERMINAL_BACKEND`.
- **Remote Linux VMs feel snappier in the terminal** — two layers of work:
  - *Rendering*: full repaints measure **14.8 ms → 4.3 ms** (≈3.4×) and the
    common interactive case (one prompt line) **2.14 ms → 0.81 ms per output
    event** (≈2.6×). Consecutive same-style cells are batched into single
    `drawText` calls, styled runs are cached per row (invalidated on theme
    change), the palette and font variants are cached instead of rebuilt every
    frame, and only invalidated rows are repainted.
  - *Pumping*: the SSH worker's output pump now wakes immediately on
    keystroke-able writes (self-pipe instead of polling) and ships small
    coalesced chunks from an idle remote after **~8 ms** instead of waiting
    the full 150 ms pacing window — a prompt on the remote no longer feels
    like it "arrives late". Large bursts still coalesce (≤64 KB per emit),
    and any output still buffered when the session stops is flushed before
    teardown, so the tail of a transfer is never dropped.
- Local PTY reads now use the same idle-blocking + short coalescing window as
  remote SSH output, so chatty commands do not create one queued Qt event per
  read while an idle shell consumes no polling CPU.
- Terminal output repaints are capped at ~60 fps and can no longer be starved
  indefinitely by a fast writer (`yes`, large `cat`); the coalesce window
  adapts (16 ms while dirty, 33 ms at rest) so steady output stays smooth
  while idle tabs use almost no CPU.
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
- Terminal: the vertical scrollbar was sizing itself to the platform default
  (~100 px) before the stylesheet applied, leaving a wide blank strip on the
  right of every terminal and wasting ~10 columns of shell width; the bar is
  now pinned to its 12 px styled width.
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
- Session editor: the SSH and RDP pages each own their authentication widgets
  now — previously the RDP page's combos shadowed the SSH page's, so auth
  method, vault credential and key path edits made on the SSH page were
  silently dropped on save.
- Quick connect: a bare `user@host` connects over SSH again. The RDP plugin
  claimed every parseable target, and because plugins are tried in order,
  `user@host` opened an RDP session; RDP now only matches an explicit `:3389`.
- Broadcast input mode and command snippets actually send to terminal tabs
  (both checked a `send_text` attribute no controller has, so they silently
  did nothing).
- Remote port forwards read the server-assigned port from the correct tuple
  element (`request_port_forward` returns `(address, port)`).
- `.rdp` files no longer contain duplicate keys (mstsc applies the last
  occurrence of a key, so the duplicate `full address` line could override
  values) and are written with a UTF-16 BOM so mstsc reads non-ASCII
  usernames/domains correctly.
- RDP probe: a classic (pre-RDP5) Connection Confirm is exactly 10 bytes and
  was wrongly rejected; partial TCP responses are reassembled before parsing.
- SSH worker: the `disconnected` signal is emitted exactly once (pump thread
  and shutdown slot could both fire it, double-counting reconnect attempts);
  the write queue no longer busy-spins when the channel accepts 0 bytes.
- SFTP/monitoring keep working across reconnects: the transport provider now
  resolves the current worker at call time instead of pinning the old one.
- Network tools: ping and DNS lookups run off the GUI thread (a closed port ×
  many probes could freeze the whole window for minutes).
- Terminal context-menu paste honours the multi-line paste confirmation again
  (Qt's `triggered(checked)` was disabling it).
- Light theme: widgets built at runtime used the dark palette unconditionally;
  `palette()` now follows the applied theme.
- Session import no longer silently overwrites a saved session when an
  imported file carries a colliding id; renaming a folder into an existing
  folder merges instead of duplicating the group entry.
- Vault: `create()` refuses to overwrite an existing vault; corrupt vault
  files raise a proper `CryptoError` instead of crashing on decode; imported
  SSH keys are forced to `0600` regardless of source permissions.
- `known_hosts` fingerprint lookup no longer indexes a dict method
  (`entry.keys[0]` → `TypeError`).
- ssh/config importer understands `Key=Value` and tab-separated entries;
  quick connect supports bracketed IPv6 (`[::1]:2222`).
- Settings with garbage numeric values no longer crash startup; a failed
  XWayland relaunch restores the previous `QT_QPA_PLATFORM`.
- Monitor network rates use the real elapsed time between samples; toasts are
  positioned at their parent window instead of the screen corner; duplicate
  `Ctrl+W` shortcut could close two tabs per keypress.
- Clean application exit: SSH worker threads are joined synchronously in
  `closeEvent` (they were torn down via a deferred timer that never ran after
  quit, causing Qt's "QThread destroyed while still running" abort).

## Unreleased

- **In-app RDP on Wayland desktops** (Ubuntu 25+/26.04, Fedora, …): the
  built-in display needs X11 window embedding, so KB-Remote now restarts
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
  *inside* KB-Remote's tab. Keyboard/mouse are handled by the embedded
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
