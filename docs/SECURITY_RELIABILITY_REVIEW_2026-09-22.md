# Security, reliability, and tab-by-tab improvement review

- **Date:** 2026-09-22
- **Reviewed commit:** `1b318c74a95bcc7c3467f22db32d4c6b1a84c9c2`
- **Application:** KB-Remote 0.9.0
- **Outcome:** several security and data-loss defects warrant fixes before a hardened release. **This review does not establish that the application is vulnerability-free.**

This is a follow-up to [the earlier engineering review](ENGINEERING_REVIEW.md), not an implementation patch. Application code and existing tests were not changed. The recommendations below distinguish reproduced behavior, source-traced defects, and additional hardening work.

## 1. Scope, evidence, and limitations

- Inventoried **87 Python source modules, 28,209 source lines, and 1,308 functions/methods**. The test tree contains 480 test functions, before parametrization.
- Ran repository-wide lint, security-pattern scanning, Bandit, dependency audits, selected existing tests, and bounded local reproduction probes. Manually traced the major tabs/actions and their authentication, filesystem, persistence, subprocess, and worker boundaries.
- **Not every function or UI interaction was dynamically tested.** Static scanning and passing tests cannot prove the absence of exploitable flaws.
- Probes used temporary fixtures, test doubles, and an ephemeral **loopback-only** SFTP server. No external host was scanned or attacked. Large allocation/KDF risks were checked with spies rather than exhausting resources.
- The sandbox lacks Qt GUI runtime libraries, including `libGL.so.1`. Attempts to provision them failed because Debian mirrors were unreachable. QtCore-based helpers could run; real widgets could not.
- No Windows/mstsc, real FreeRDP embedding, native QTermWidget, PuTTY interoperability, or X11/Wayland end-to-end run was completed. The OpenSSH `sshd` integration fixture was unavailable. The share-server tests did exercise real local SSH/SFTP connections through Paramiko.

### Checks actually performed

| Check | Result |
|---|---|
| `ruff check src tests scripts` | **Passed.** |
| Headless existing-test subset, listed below | **206 passed.** |
| Existing share-server tests excluding GUI/controller cases | **30 passed; 7 deselected.** |
| Full `QT_QPA_PLATFORM=offscreen python -m pytest tests` | **Blocked:** 3 collection errors caused by missing `libGL.so.1`; not a passing full-suite result. |
| Additional attempt at `test_transfer_engine.py` | Its 13 tests were blocked by the same missing GUI library through the `qtapp` fixture. |
| CLI `--version` and `--help` | **Passed.** GUI startup was not verified. |
| Isolated review probes | **18 bounded probe cases reproduced the targeted behavior**, including two UI slot bodies executed with widget doubles, not real widgets. Observations are described in the finding register. |
| Bandit | 143 raw findings: 3 high, 7 medium, 133 low. These are **scanner flags, not 143 confirmed vulnerabilities**. |
| Audit of freshly resolved Python environment | No advisories reported for the installed application runtime dependencies. Sandbox bootstrap `pip`/`setuptools` were flagged; the local project itself is not auditable as a published PyPI package. |
| Audit of declared minimum Python runtime versions | **7 distinct advisory IDs across Paramiko 3.4.1 and cryptography 44.0.1**, after deduplicating 12 returned records. This is version evidence, not proof that every affected API is reachable in KB-Remote. |

Test environment: Linux, Python 3.11.2; PySide6-Essentials 6.11.2, Paramiko 5.0.0, cryptography 50.0.1, pyte 0.8.2; pytest 9.1.1, Ruff 0.16.8, Bandit 1.9.4, pip-audit 2.10.1.

Bandit triage matters: the MD5 fingerprints are legacy **display** values, `capability_set(shell=True)` is not subprocess execution, and cluster `exec_command(command)` intentionally executes a user-selected command. Do not treat these flags as automatic injection vulnerabilities. The PPK implementation does have separate correctness/privacy problems described below.

### Existing strengths to preserve

- Shared private, atomic state writes with file fsync and best-effort directory fsync.
- AES-GCM authenticated vault encryption and structural/KDF-work validation for vault envelopes.
- FreeRDP certificate TOFU defaults and control-character rejection in its private argument-file writer.
- Detached session-store reads and transactional individual session updates/deletes/upserts.
- SSH shell-output pumping runs on a separate Python thread instead of monopolizing the worker Qt event loop.
- Bounded scanner scheduling, a result cap, streaming export, and cancellation support.
- Explicit protocol loading, loopback-default SSH tunnels, and an opt-in share service that refuses shell/exec/forwarding requests.

Some older review entries are stale: detached store reads, agent-forwarding wiring, download-directory selection, scanner result caps/export, and Windows CI smoke coverage already exist. Do not spend the next pass reimplementing them. Their end-to-end correctness still needs regression coverage.

## 2. Prioritized finding register

**P1:** address before calling a release hardened/reliable. **P2:** next hardening/stability milestone. Priority includes data loss and broken functionality, not just attacker access. A local or authenticated precondition is stated where applicable.

**Practical precautions until fixes land:** do not expose the share service to untrusted clients or rely on its read-only checkbox; avoid untrusted session imports; use a validated external key-conversion tool; close credential views and lock the OS desktop when unattended; back up remote files before editing; prefer FreeRDP 3 with certificate checking and private credential delivery. These reduce exposure but do not repair the defects.

### SR-01 — P1 / High: read-only shares permit file creation and truncation

**Evidence:** [`tools/share_server.py:442–465`](../src/rdpstudio/tools/share_server.py#L442-L465), [`266–305`](../src/rdpstudio/tools/share_server.py#L266-L305).

The write-permission check recognizes `O_WRONLY`, `O_RDWR`, and `O_APPEND`, but not `O_CREAT` or `O_TRUNC`. Paramiko can translate an SFTP READ request carrying CREATE/TRUNCATE into those flags without setting write access. An **authenticated client of an enabled share service** can therefore modify a supposedly read-only share.

**Reproduced over real loopback SFTP:** READ+TRUNCATE emptied a temporary existing file; READ+CREATE created a new file with `allow_write=False`. This is not an unauthenticated takeover or a demonstrated escape from the share root.

**Fix:** reject every mutating flag combination on read-only shares; validate incompatible flags before opening anything. Define and enforce revocation for open handles when a share is unpublished or made read-only. A separate backend probe showed an already-open write handle still works after the registry switches to read-only; the share dialog's restart path can close connections, but that is not backend enforcement.

**Acceptance:** wire-level tests for every access/create/truncate/append combination, plus policy changes with an already-open handle. Until fixed, disable sharing or enforce read-only access at the OS/filesystem level rather than relying on the checkbox alone.

### SR-02 — P1 / High: Windows `.rdp` values can inject additional settings

**Evidence:** [`protocols/rdp/rdpfile.py:13–73`](../src/rdpstudio/protocols/rdp/rdpfile.py#L13-L73), [`core/models.py:283–298`](../src/rdpstudio/core/models.py#L283-L298).

String fields are interpolated into a line-oriented format without rejecting CR/LF/NUL. The duplicate-key filter examines the assembled strings, not extra physical lines embedded inside their values. A crafted **imported or edited session**, subsequently launched by the user, can carry additional RDP property records.

**Reproduced:** a gateway-username value introduced later `authentication level` and `drivestoredirect` records despite the model keeping certificate-ignore and drive sharing disabled. The generated text was tested; native mstsc behavior was not exercised here.

**Fix:** validate every string at the `.rdp` serialization boundary, not just in the editor. Reject control-bearing imported values with an actionable error. Extend the existing FreeRDP argument-file invariant to mstsc files. Also use unique private temporary files rather than trusting a predictable pre-existing filename/directory.

**Acceptance:** tests for CR, LF, CRLF, NUL, duplicate records, Unicode, and malicious imports across all serialized strings; verify effective settings with mstsc on Windows.

### SR-03 — P1 / High privacy impact: PPK export is insufficiently protected and incorrectly encoded

**Evidence:** [`ui/key_utility_dialog.py:270–281`](../src/rdpstudio/ui/key_utility_dialog.py#L270-L281), [`tools/key_converter.py:118–193`](../src/rdpstudio/tools/key_converter.py#L118-L193).

- The dialog saves private-key material with `Path.write_text`, without private permissions. With umask `022`, that write primitive produced **0644**. Other users can read it if the chosen parent directory is accessible.
- `openssh_to_ppk(..., passphrase=...)` ignores the passphrase and always emits `Encryption: none`. The current dialog has no output-encryption control.
- `Private-MAC` is a plain SHA-1 digest, not the PPK v2 HMAC construction. A reference HMAC calculation did not match the emitted value. PuTTY itself was not available for an interoperability test.

**Fix:** reuse private atomic persistence; enforce Windows ACL privacy as well as POSIX permissions. Use a maintained, validated conversion implementation or PuTTYgen with safe credential handling. Implement encryption explicitly or reject a nonempty unsupported passphrase. Validate RSA integer encoding, Ed25519 layout, and UTF-8 comment lengths. Do not advertise OpenSSH ⇄ PPK until both directions work.

**Acceptance:** independent PuTTYgen/WinSCP round trips for every supported key type, Unicode comments, encrypted/unencrypted exports, failed writes, overwrite policy, and file permissions.

### SR-04 — P1 / High local exposure: vault auto-lock does not invalidate the credential UI

**Evidence:** [`core/vault.py:144–149`](../src/rdpstudio/core/vault.py#L144-L149), [`ui/vault_dialog.py:142–182`](../src/rdpstudio/ui/vault_dialog.py#L142-L182), [`ui/main_window.py:1680–1693`](../src/rdpstudio/ui/main_window.py#L1680-L1693).

Locking empties the vault's dictionary, but credential list items retain the previously returned `Credential` objects, and the editor retains secret text. The auto-lock timer only shows a toast. `_load_credential` does not check whether the vault is still unlocked, and Show is not gated on vault state.

**Reproduced with the actual selection-slot body and widget doubles:** after `vault.lock()`, selecting a cached list item could populate the secret field again. This is a UI-state exposure to someone with access to the running desktop, not a break in AES-GCM.

**Fix:** publish a lock-state event; immediately clear secret fields, list-item payloads, reveal state, and other credential views. Store credential IDs rather than secret-bearing objects in widgets; require an unlocked lookup on selection. Handle OS session lock/suspend as policy permits. Do not promise Python memory zeroization or that locking erases credentials already handed to active sessions.

**Acceptance:** keep the dialog open through timer/manual/OS lock, then try selecting, revealing, copying, and saving; all secret access must require unlock.

### SR-05 — P1 / Medium: exception tracebacks bypass log redaction

**Evidence:** [`core/log.py:31–57`](../src/rdpstudio/core/log.py#L31-L57), [`92–119`](../src/rdpstudio/core/log.py#L92-L119).

The filter sanitizes `record.getMessage()`, but a logging formatter subsequently appends exception and stack text. A registered secret inside an exception can therefore reach the log unchanged.

**Reproduced:** a synthetic exception containing a registered dummy secret remained in the formatted traceback. This demonstrates a protection gap; it does not establish that normal authentication currently logs every password.

**Fix:** sanitize the complete rendered record, including chained exceptions and stack information, or reliably sanitize each component. Cover newly added/changed credentials, short secrets, overlapping values, and eviction from the bounded redaction registry. Avoid unnecessarily retaining plaintext secrets indefinitely.

Terminal session recordings are a separate raw-output feature: [`ui/terminal.py:739–746`](../src/rdpstudio/ui/terminal.py#L739-L746) and the native backend use ordinary file opens, not this redactor. Make recordings private and clearly warn that they may contain sensitive terminal output; do not promise complete automatic redaction of arbitrary transcripts.

**Acceptance:** file/console tests for message arguments, traceback chains, stack text, and recording-file permissions.

### SR-06 — P1 / Medium: the multiline-paste setting is bypassed by keyboard paste

**Evidence:** [`ui/terminal.py:1292–1308`](../src/rdpstudio/ui/terminal.py#L1292-L1308), [`1339–1345`](../src/rdpstudio/ui/terminal.py#L1339-L1345), [`ui/native_terminal.py:478–483`](../src/rdpstudio/ui/native_terminal.py#L478-L483), [`protocols/ssh/session.py:362–365`](../src/rdpstudio/protocols/ssh/session.py#L362-L365).

Both backends call `paste_clipboard(confirm=False)` for Ctrl+Shift+V. Middle-click intentionally bypasses the guard too. Even the guarded path checks LF but not a carriage-return-only command boundary. Remote OSC-52 clipboard writes are applied without a per-session permission decision.

**Source-traced:** untrusted clipboard text can reach a shell without the confirmation promised by the setting. This still requires the user to paste; it is not automatic remote code execution.

**Fix:** one pure paste-policy helper shared by both renderers and all input routes. Honor the setting consistently, make any bypass explicit, and account for CR, control bytes, and embedded bracketed-paste terminators. Add a per-session policy for remote clipboard writes, defaulting conservatively for untrusted hosts.

**Acceptance:** keyboard/context-menu/middle-click tests on both renderers, with LF, CR, escape/control bytes, OSC-52, and bracketed-paste on/off.

### SR-07 — P1 / High conditional path risk and data corruption: download staging is not trustworthy

**Evidence:** [`protocols/ssh/sftp.py:373–429`](../src/rdpstudio/protocols/ssh/sftp.py#L373-L429).

Three helper-level behaviors were reproduced:

1. A pre-existing `name.part` symlink was followed. A sentinel **outside the destination but inside the temporary test fixture** was modified, and the final download became a symlink. This requires someone/process to pre-place the local staging link; it is not a demonstrated remote-only path escape.
2. An unrelated same-name partial file was resumed based only on size, producing mixed old/new contents.
3. Early EOF published a 5-byte file as completed although its advertised size was 10 bytes.

**Fix:** private, no-follow staging files; bind resumable state to the session/host, remote path, and remote file identity. Validate the final length and, where supported, a digest/change token before atomic publication. Reject unsafe staging files and protect against directory/symlink substitution during use. Bound prefetch concurrency rather than invoking unbounded prefetch by default.

Also audit recursive upload, download, total-counting, and delete walks: they follow `stat`/`is_dir` results, lack a shared depth/entry budget, and do not consistently check cancellation. In particular, recursive deletion should not follow a directory symlink into unrelated remote contents.

**Acceptance:** symlink/partial collisions, changed source during resume, short reads, concurrent same-name transfers, cyclic trees, cancellation during traversal, and disk-full tests.

### SR-08 — P1 / High data-loss risk: the remote editor can report success before saving

**Evidence:** [`protocols/ssh/sftp.py:576–596`](../src/rdpstudio/protocols/ssh/sftp.py#L576-L596), [`ui/sftp_dialog.py:544–560`](../src/rdpstudio/ui/sftp_dialog.py#L544-L560), [`ui/file_editor_dialog.py:122–181`](../src/rdpstudio/ui/file_editor_dialog.py#L122-L181).

- Remote reads stop at 16 MiB without identifying truncation. Saving that buffer can replace a larger file with only its prefix.
- The editor's save callback merely queues an upload, yet the editor immediately clears `_dirty` and displays “Saved & Uploaded.” The later `fileWritten` callback does not repair that state on failure.
- There is no dirty-close confirmation in the editor. Latin-1 fallback input is always saved as UTF-8; byte/line-ending preservation is not established.
- Upload/save writes truncate the destination directly, leaving it vulnerable to interruption.

**Reproduced with the save-slot body and widget doubles:** the editor became clean/successful before any upload acknowledgement. The larger-file and encoding paths are source-traced, not native GUI-tested.

**Fix:** reject oversized editing or offer an explicitly read-only preview; await a correlated save result for the correct buffer revision; preserve dirty state after failure. Add save/discard/cancel close handling, encoding/line-ending policy, stale-remote-file conflict checks, and temporary-upload-plus-rename where supported.

**Acceptance:** >16 MiB input, binary/non-UTF-8 input, concurrent edits during upload, denied writes, disconnect/disk-full, and closing with pending or failed saves.

### SR-09 — P1 / High functional impact: SSH trust and agent paths need repair

**Evidence:** [`protocols/ssh/knownhosts.py:43–70`](../src/rdpstudio/protocols/ssh/knownhosts.py#L43-L70), [`worker.py:333–335`](../src/rdpstudio/protocols/ssh/worker.py#L333-L335), [`378–398`](../src/rdpstudio/protocols/ssh/worker.py#L378-L398), [`tools/cluster_runner.py:118–136`](../src/rdpstudio/tools/cluster_runner.py#L118-L136).

- Clients install the custom missing-host-key policy without loading their own host-key cache. The policy itself lacks an early accept for an exact stored-key match. A known matching key was rejected in strict mode and in noninteractive accept-new mode. Interactive accept-new unnecessarily asks again; the cluster runner has no prompter and rejects the match.
- The SSH worker obtains `AgentKey` objects, then closes the agent **before authentication needs to sign**. A real Paramiko `AgentKey` signing attempt through the worker's flow failed after that close in a socket-free fixture.

**Fix:** centralize SSH trust/authentication setup for interactive sessions and cluster execution. Accept exact pinned matches, reject unknown keys in strict mode, and explicitly handle changes. Keep the agent connection alive through signing, preferably using the library's supported authentication lifecycle. Preserve jump-host and encrypted-key/passphrase behavior in the cluster path rather than duplicating incomplete authentication policy.

**Acceptance:** connect twice without a second prompt; strict-known success; strict-unknown/changed rejection; concurrent trust updates; real ssh-agent signing, passphrase-protected keys, jump chains, and cluster authentication. Rejecting a host key should not trigger repeated automatic consent prompts.

### SR-10 — P1 / High stability risk: dialog close is not a bounded worker shutdown contract

**Evidence:** [`ui/sftp_dialog.py:702–706`](../src/rdpstudio/ui/sftp_dialog.py#L702-L706), [`ui/main_window.py:1486–1494`](../src/rdpstudio/ui/main_window.py#L1486-L1494), [`ui/network_tools_dialog.py:168–177`](../src/rdpstudio/ui/network_tools_dialog.py#L168-L177), [`ui/cluster_dialog.py:343–349`](../src/rdpstudio/ui/cluster_dialog.py#L343-L349).

A timed `QThread.wait()` is followed by closing the dialog without checking whether the thread stopped. SFTP dialogs are delete-on-close. `quit()` cannot interrupt a running blocking transfer slot. Ping/DNS waits may outlast the two-second close window. The SFTP engine has a cancel method, but the dialog does not expose/wire a transfer-cancel action.

Cluster cancellation is also incomplete: it is checked while iterating completed futures, not while executing a host command; leaving the executor context waits for running work. Sequential stdout/stderr reads followed by `recv_exit_status()` can stall on channel flow control or a missing exit status ([`cluster_runner.py:64–92`](../src/rdpstudio/tools/cluster_runner.py#L64-L92), [`138–148`](../src/rdpstudio/tools/cluster_runner.py#L138-L148)).

**Source-traced risk:** deletion of a still-running QThread can abort the application. This crash was not reproduced with native widgets in this sandbox. The prior review's suite-teardown hang could not be revalidated here.

**Fix:** own each job beyond its window; request cancellation, close/interrupt the job's channel without killing unrelated shell channels, and only dispose its owner after completion. Check timed-wait results. Use operation deadlines and simultaneous stdout/stderr draining. Avoid `QThread.terminate()` as normal cleanup. Resolve deferred SSH teardown before deleting controller-owned thread objects.

**Acceptance:** close dialogs/tabs/app during DNS, handshake, host-key prompt, huge transfer, blocked socket, and cluster output flood. Assert no live workers, channels, or late widget callbacks remain. Put a hard timeout around the entire CI job as well as individual tests.

### SR-11 — P1 / Medium security-policy risk: Settings changes do not consistently reach runtime services

**Evidence:** [`ui/settings_dialog.py:1042–1116`](../src/rdpstudio/ui/settings_dialog.py#L1042-L1116), [`ui/main_window.py:1502–1510`](../src/rdpstudio/ui/main_window.py#L1502-L1510), [`tools/share_server.py:1043–1051`](../src/rdpstudio/tools/share_server.py#L1043-L1051), [`app.py:37–47`](../src/rdpstudio/app.py#L37-L47).

**Source-traced:** saving Settings applies UI/terminal preferences, but does not call `ShareService.reload_settings()` or update the existing vault's KDF configuration. A running sharing service can therefore keep its old write/bind/share policy despite the saved controls. Moreover, `reload_settings()` claims to restart the listener but contains no restart.

Reset-to-defaults rebinds `result_settings` to a new object, while the main window keeps the old context object. The reset also omits some controls. General and Terminal duplicate the cursor selector, but saving always prefers the Terminal selector.

**Fix:** a single settings transaction: validate a detached candidate, persist, then apply it to all affected services through an explicit settings-changed contract. Stop/restart listeners as required and visibly report the actual bound policy. Define whether KDF changes apply on next encryption or through an explicit re-encryption action. Make Reset/Cancel and duplicated controls consistent.

**Acceptance:** change every setting once, save, verify disk and live behavior, reopen, then repeat with Cancel, Reset, and injected save/apply failures. Include disabling sharing while clients are active.

### SR-12 — P1 / dependency risk: allowed minimum versions no longer exclude known advisories

**Evidence:** [`pyproject.toml:28–35`](../pyproject.toml#L28-L35) and the dated pip-audit result from this review.

Auditing the declared minima (`PySide6-Essentials==6.6.0`, `paramiko==3.4.1`, `pyte==0.8.2`, `cryptography==44.0.1`) returned one distinct Paramiko advisory ID and six cryptography IDs. Examples include `GHSA-r374-rxx8-8654`, `GHSA-r6ph-v2qm-q3c2`, and `GHSA-537c-gmf6-5ccf`. The six cryptography IDs include APIs whose reachability in this app was not established; do not label all of them exploitable application flaws.

Freshly resolved Paramiko 5.0.0 and cryptography 50.0.1 had no reported advisories in this audit, but that does not validate every supported combination. The optional renderer, bundled Qt/OpenSSL, OS packages, and native FreeRDP require separate inventory/auditing.

**Fix:** choose patched, compatibility-tested minimum versions; use locked, hash-verified release inputs without unnecessarily freezing a reusable library's entire dependency graph. Add scheduled/PR dependency auditing and update automation. Audit built artifacts, not only the developer venv. Upgrade bootstrap/build tools too.

**Acceptance:** oldest-supported and release-locked dependency jobs pass on the supported Python/OS matrix; audit output is clean or explicitly triaged with an owner and expiry.

### SR-13 — P2 / Medium: inbound service budgets stop at connection count

**Evidence:** [`tools/share_server.py:112–130`](../src/rdpstudio/tools/share_server.py#L112-L130), [`283–294`](../src/rdpstudio/tools/share_server.py#L283-L294), [`598–650`](../src/rdpstudio/tools/share_server.py#L598-L650), [`955–963`](../src/rdpstudio/tools/share_server.py#L955-L963).

The 16-connection limit does not cap SFTP channels/handles per connection or the read length passed to the filesystem. A spy observed a 1 GiB requested length reaching `read()` unclamped; no large allocation was performed. Authenticated sessions have no application idle/operation deadline. Login attempts are not application-rate-limited. Share names are exposed in the pre-auth banner.

Share-password verification also lacks the vault envelope's KDF upper bound and exact decoded-length validation. A mocked KDF received an iteration count of `2**40` from a malformed stored hash. This requires corrupt/controlled local configuration, not a remote choice of the stored hash.

**Fix:** read-chunk, channel, handle, file-type, idle-time and disk-use budgets; per-peer authentication throttling; strict hash parsing and calibrated work limits. Avoid blocking on FIFOs/devices within shares. Show only necessary information before authentication. Prefer read-only shares and deliberate interface selection; default all-interface binding is broader than needed on multi-network machines.

**Acceptance:** bounded fake-reader/KDF tests, many channels on one authenticated transport, stalled sessions, and repeated authentication attempts without resource exhaustion. Also test directory/symlink races: realpath-then-open is not a race-free filesystem jail.

### SR-14 — P2 / Medium: large counters and maximum-length share names break edge cases

**Evidence:** [`protocols/ssh/sftp.py:88`](../src/rdpstudio/protocols/ssh/sftp.py#L88), [`core/shares.py:199–208`](../src/rdpstudio/core/shares.py#L199-L208).

- Transfer byte counts use Qt `Signal(int)`, a signed 32-bit value. Emitting `2**31 + 1` reached the receiver as **-2147483647** in the probe, without allocating a large file.
- Two identical 64-character share names cause the collision loop to append a suffix and then truncate it away repeatedly. A bounded subprocess probe exceeded its deadline; the loop has no terminating candidate for this case.

**Fix:** use a 64-bit Qt type or an object progress payload, and keep percentage arithmetic independently bounded. Reserve suffix space before truncating share names and bound uniqueness attempts.

**Acceptance:** >2 GiB/>4 GiB progress, zero/unknown sizes, and repeated maximum-length/case-colliding share names.

### SR-15 — P2 / Medium: remaining persistence and tool-state ownership gaps

**Evidence:** [`core/vault.py:175–207`](../src/rdpstudio/core/vault.py#L175-L207), [`ui/vault_dialog.py:188–198`](../src/rdpstudio/ui/vault_dialog.py#L188-L198), [`core/store.py:182–246`](../src/rdpstudio/core/store.py#L182-L246), [`ui/main_window.py:1464–1494`](../src/rdpstudio/ui/main_window.py#L1464-L1494).

**Reproduced:** mutating a credential returned by `vault.get()` before `put()` defeats its rollback snapshot: after a failed save, memory contains the edit while disk contains the previous secret. A failed group rename likewise leaves memory ahead of disk. Group operations, bulk import, and snippet mutations need the same transaction discipline already used by individual session updates.

**Source-traced UI defect:** Files and Tunnels share a cache keyed only by controller identity. Opening one after the other can raise the wrong existing dialog instead of the requested tool.

**Fix:** detached vault reads/updates; transactional group/import/snippet changes; preserve or quarantine corrupt originals instead of silently replacing them after an empty-state recovery. Add schema-version/migration checks and a multi-instance conflict strategy. Key tool instances by `(controller identity, tool kind)` and close dependent tools when their session is disposed.

**Acceptance:** save-failure injection at every mutation, parallel editors/imports, corrupt/future-version state recovery, and Files/Tunnels opening independently in either order.

## 3. Every major tab/screen: improvement and regression checklist

These are recommendations, **not a claim that all these interactions were exercised with real widgets**. The SR references above identify concrete defects; the other items are additional hardening or usability work.

| Screen / tab | Recommended improvements and tests |
|---|---|
| Dashboard, roster, saved sessions | Finish group/import transactions (SR-15); validate format, group shape, IDs and protocol-specific options. Preview imported local commands, startup commands, agent forwarding, redirection, shares and insecure certificate flags before activation. Keep malformed imports from partially committing. Preserve selection/filter state after edits. |
| Session editor — SSH/RDP/local | Validate at the model and serialization boundaries, not only widgets. Make plaintext password storage an explicit warning/choice; prefer the vault or OS credential storage. Test protocol switching, Save/Cancel/Test, missing credentials, cycles and missing jump hosts. Explain that Test checks connectivity, not successful authentication. |
| SSH terminal | Fix trust/agent authentication (SR-09), paste policy (SR-06), and shutdown ownership (SR-10). Test authentication refusal versus retryable transport failure, jump chains, reconnect with Files/Tunnels open, resize under output load, and stopping during a prompt. |
| RDP session | Fix `.rdp` serialization (SR-02). Remove silent password-on-argv fallback on FreeRDP 2 unless the user gives specific consent; prefer FreeRDP 3. Validate audio, gateway, printer, drive/clipboard, fullscreen, resize and certificate behavior against real FreeRDP and mstsc—not just generated strings. |
| Local terminal | Retain subprocess argv-based launching and process-group cleanup. Test shell startup failure, restart, child pipelines, close under heavy output, POSIX PTY and Windows ConPTY/fallback separately. Imported local commands should be visibly reviewed before execution. |
| Files — remote/local browser, drag/drop, transfer queue | Address SR-07, SR-10 and SR-14. Add Cancel/Cancel All, conflict/overwrite policy, stable per-job status and bounded directory listings. Replace newline-delimited filename payloads with structured data so filenames containing newlines cannot change operation boundaries. Track which remote session a drag belongs to. |
| In-app file editor | Address SR-08. Preserve dirty state, encoding and line endings; show upload progress/error/conflict state. Test multiple editors of the same remote path and close while a save is pending. |
| Tunnels — local, remote, SOCKS | Fix tool-cache identity (SR-15). Keep loopback defaults and warn before unauthenticated SOCKS/non-loopback exposure. Cap connection threads, remove completed thread references, and add stop/deadline handling to send loops. State whether Stop also closes existing connections; test remote-forward revocation and backpressure. |
| File sharing — global and session folders | Address SR-01, SR-11, SR-13 and SR-14. Clarify that session-scoped folders join one registry accessible to the same share account; this is not per-machine authorization. Add per-client credentials/ACLs if isolation is required. Prefer read-only access and a selected trusted interface. |
| Network tools — Port Scanner | Preserve the implemented bounded scheduler/result cap/streaming export. Reject invalid port expressions rather than silently scanning the common-port preset. Show the exact target/port count and truncated/cancelled state. Bound UI row growth and sanitize spreadsheet-oriented CSV cells. |
| Network tools — Ping & Latency | Add cooperative cancellation and safe close; distinguish TCP connection latency from ICMP ping. Exercise refusals, packet loss, IPv6, long-running probes and exact progress accounting. |
| Network tools — DNS & IP Lookup | Keep DNS off the GUI thread, but add a resolver deadline and stale-result isolation. `socket.create_connection`'s socket timeout does not itself bound blocking `getaddrinfo`; the current scanner comment should not claim otherwise. |
| Cluster command runner | Fix shared authentication (SR-09) and output/cancel/deadline handling (SR-10). Preview the command and exact selected hosts before execution; report cancelled/skipped hosts separately from success. Escape spreadsheet formulas in CSV exports. Execute only against systems the operator is authorized to administer. |
| Snippets and per-tab command bar | Keep explicit execution and clear destination identity. Offer insert-without-executing for untrusted snippets, and confirmation for multi-target/destructive actions where supported. Finish snippet persistence rollback. Provide history clearing and warn against typing secrets into retained command history. |
| Key utility — Inspector & Randomart | Cap input size, distinguish wrong passphrase from unsupported format where safe, and keep SHA-256 primary. Treat MD5 as a legacy display fingerprint (`usedforsecurity=False` where appropriate). Fuzz malformed key inputs and test FIPS environments. |
| Key utility — Generator | Generate expensive keys off the GUI thread; safely cancel/close. Restrict a “key name” to a leaf name or use an explicit save-path picker. Test overwrite refusal, public/private pair consistency, encryption and permissions. |
| Key utility — PuTTY Converter | Address SR-03. Only show supported types/directions. Independently verify produced keys; a test that only finds `Private-MAC:` does not establish a valid PPK. |
| Vault — Credentials | Address SR-04, SR-05 and SR-15. Clear reveal/clipboard state on lock, avoid stale secret-bearing objects, confirm destructive deletion, and avoid a redundant second encryption/save after `put()` already persisted. |
| Vault — SSH keys | Use private atomic imports rather than copy-then-chmod; detect pre-existing/public-key collisions and symlinks. Keep passphrases in the vault, not session JSON. Test import, generate, agent listing and wrong-passphrase errors independently. |
| Settings — General | Address SR-11, especially Reset/Cancel and the duplicate cursor control. Test keyboard focus, reduced motion, screen-reader names, high contrast and 100–200% DPI for every visible control. |
| Settings — Terminal | Enforce the displayed paste policy in both backends (SR-06). Test renderer fallback, scrollback bounds, palette override behavior, font changes and control-sequence parsing under sustained output. Add real backpressure rather than relying on an unbounded queued-output path. |
| Settings — Connections / file sharing | Apply changes to running services (SR-11). Correct the Strict host-key label to explain unknown-key rejection. Warn about broad binding, plaintext session passwords, and configuration changes that restart a listener. |
| Settings — Security | Verify effective auto-lock and KDF behavior, not just persistence (SR-04/SR-11). Establish a measured KDF-strength policy, support safe re-encryption, and label disabling auto-lock clearly. |
| Settings — RDP | Test embedded/external choice, unavailable clients, failed XWayland relaunch, and unsaved settings before restart. Preserve certificate verification by default; make credential exposure and redirection decisions explicit. |
| RDP server manager | Keep privileged changes explicit. Move status checks/commands off the GUI thread (current waits can reach 120 seconds); distinguish UAC cancellation/failure/success and verify resulting service/firewall state. Show exposure scope and make changes reversible. |
| Command palette, tab controls, docking and shortcuts | Fix Files/Tunnels reuse (SR-15). Test rename/duplicate/reconnect/close-other/close-right against the intended session, including asynchronous completion and reordered tabs. Generate action/shortcut listings from one catalog; retain deliberate terminal/readline shortcut precedence. |

## 4. Stable code-quality and release improvements

### Before a hardened release

1. **Write failing regression tests for the P1 cases, then fix them in small patches.** Preserve public imports and file formats where possible. Do not combine security fixes with a large UI rewrite.
2. **Make resource ownership explicit:** a session/tool job owns its worker, channels, cancellation token and pending prompts; the widget observes it. Closing the widget must not destroy an active worker.
3. **Separate pure policy from widgets:** paste policy, trust decisions, settings application, transfer manifests and `TerminalCore` should be importable/testable without Qt GUI libraries. The current terminal import pulls in `QtGui`, blocking otherwise pure parser tests in this sandbox.
4. **Make persistence transactional all the way up to the UI.** An atomic filesystem replacement does not by itself roll back a mutated model or prevent a premature “Saved” message. Add uniform error presentation for read-only/full-disk state paths.
5. **Use safe defaults and clear exceptions:** encrypted credential storage by default; explicit consent for plaintext/argv secrets, writable shares, non-loopback listeners, agent forwarding, clipboard writes and imported executable settings.

### CI and supply chain

**Evidence:** [CI workflow](../.github/workflows/ci.yml), [`release.yml:30–57`](../.github/workflows/release.yml#L30-L57), [`build-appimage.sh:17–37`](../packaging/linux/build-appimage.sh#L17-L37), [Flatpak manifest](../packaging/flatpak/io.github.mylab12345.KBRemote.yaml).

- Add explicit CI/job timeouts, per-test worker-leak diagnostics, coverage reporting and a gradual **branch-coverage** gate around security boundaries. Do not hide hangs with blanket skips or `continue-on-error`.
- Extend—not replace—the existing Windows core smoke job with real GUI/ConPTY/mstsc checks. Add X11/Xvfb and Wayland/XWayland validation plus supported FreeRDP-version compatibility tests.
- Run dependency and secret scanning on PRs and periodically; pin action revisions and restrict workflow permissions. Generate an SBOM and provenance for published artifacts.
- Verify downloaded build tools and release downloads using pinned digests/signatures. The AppImage script executes downloads from mutable `continuous` releases without digest checks.
- Remove `|| true` from the AppImage smoke gate. It currently hides a failed launch.
- The AppImage architecture matrix names both x86_64 and aarch64, but both jobs use `ubuntu-latest` and the script derives architecture solely from `uname -m`. Use an actual ARM runner or validated cross-build, and inspect the artifact architecture before release.
- Validate packaging with the real builders. The Flatpak FreeRDP module declares `buildsystem: meson` while supplying CMake options; its pinned native dependencies and Python source declarations need a build/audit pass. No Flatpak build was attempted in this review.
- Synchronize `.github/workflows/` and the installation copies under `packaging/ci/` so installing templates cannot silently discard newer gates. Repair README references to Windows installer files that are not tracked in this checkout.

### Refactoring after characterization tests

Start with `ui/terminal.py` (1,787 lines), `ui/main_window.py` (1,723), `ui/widgets.py` (1,352), and `protocols/rdp/session.py` (1,109). Extract lifecycle/application services before cosmetic helpers. Some constructors/action builders exceed 150–200 lines.

Add incremental type checking for core/auth/transfer/store APIs; prefer typed result/error objects over free-form dictionaries. Introduce complexity/security lint rules selectively and suppress intentional behavior with reasons. Replace silent catches at important boundaries with sanitized, rate-limited diagnostics. Refresh architecture/security documentation to describe actual thread ownership and limitations rather than guarantees such as “never leaks” or “every operation is jailed” without race/lifecycle qualifications.

## 5. Suggested delivery order and release criteria

| Milestone | Scope | Exit condition |
|---|---|---|
| **1 — Security boundaries** | SR-01–SR-06, dependency policy in SR-12 | Reproduced boundary failures are fixed; secret/clipboard/trust controls match their UI; targeted security regressions pass. |
| **2 — No silent data loss / broken authentication** | SR-07–SR-09, SR-14–SR-15 | Transfers/editor saves are truthful and safe under failure; known-host/agent/cluster flows work; large-file and rollback tests pass. |
| **3 — Lifecycle and effective settings** | SR-10–SR-11, SR-13 | Closing during active work is bounded and nonfatal; settings reach live services; inbound work has meaningful budgets. |
| **4 — Release qualification** | Full tab matrix, native platforms, packaging, CI gates | Full suite exits cleanly, native smoke checks pass, artifact architecture/identity is verified, remaining risks are explicitly documented. |

Do not call the application “unhackable” after these milestones. Maintain ongoing dependency monitoring, fuzz/property tests for hostile inputs, private vulnerability reporting, and periodic independent review. Exposure depends on deployment: a desktop connecting to a trusted host, one connecting to a compromised host, and one serving writable files to a LAN have different threat models.

## Appendix: repeatable verification commands

The following is the **206-test headless subset**, not a replacement for the full release gate:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -ra \
  tests/test_auth_policy.py tests/test_core_persistence.py \
  tests/test_credential_guard.py tests/test_crypto.py tests/test_dnd.py \
  tests/test_headless_helpers.py tests/test_models_store.py \
  tests/test_network_scanner_bounded.py tests/test_rdp.py \
  tests/test_rdp_client.py tests/test_rdpfile.py tests/test_retry_transfers.py \
  tests/test_scp_proto.py tests/test_session_check.py \
  tests/test_state_validation.py tests/test_store_import_safety.py \
  tests/test_store_runtime_isolation.py tests/test_tools_key_converter.py \
  tests/test_tools_network.py tests/test_tools_snippets.py tests/test_vault.py

# 30 real/pure share-server tests; 7 widget/controller cases deselected:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -ra \
  tests/test_share_server.py \
  -k 'not dialog and not controller and not capabilities and not rdp_tab'

.venv/bin/ruff check src tests scripts
.venv/bin/bandit -r src/rdpstudio
.venv/bin/pip-audit

# Required once the documented Qt system dependencies are available:
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests
```

To recheck the declared runtime floors without installing/downgrading them, place the four exact minimum versions listed under SR-12 in a temporary requirements file and run `pip-audit --no-deps --disable-pip -r <file>`. Deduplicate advisory IDs and review reachability; this check intentionally omits transitive dependencies and must accompany, not replace, auditing the actual release environment.
