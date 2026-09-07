# Engineering review and refactoring plan

**Review date:** 2026-09-07  
**Baseline:** `ec7519b` (`main`)  
**Scope:** all tracked Python under `src/rdpstudio`, tests, build metadata,
CI, developer scripts, and architecture/security documentation.

This is a risk-based review, not a claim that static inspection can prove the
absence of every defect. Findings are tracked below so a later review can
reproduce the evidence and continue the plan rather than starting over.

## Executive summary

The application already has good foundations: protocol controllers are behind
a plugin contract, blocking SSH/SFTP work is generally off the GUI thread,
state paths are private, and the baseline contained 204 test functions. The
highest immediate risks were not missing features; they were policy code mixed
into Qt controllers, four independent implementations of atomic writes,
unbounded scanner scheduling, and malformed state that could bypass defaults
or crash during startup.

This pass addresses those risks without changing persisted formats or public
session-controller behavior:

- RDP certificate verification now honors the existing opt-in: TOFU by default,
  ignore only when selected. The same policy is emitted for FreeRDP and mstsc.
- FreeRDP discovery/argument policy moved from the 1,284-line Qt controller to
  the pure `protocols/rdp/client.py` module. Historical imports from
  `protocols.rdp.session` remain available.
- Built-in plugins are loaded explicitly. Importing pure RDP/SSH helpers no
  longer initializes the Qt plugin graph.
- Settings, sessions, snippets, vault, and known-hosts writes share one private,
  flushed, atomic persistence primitive.
- The port scanner keeps at most `2 × max_workers` futures in flight and Cancel
  no longer waits for the full target matrix to be submitted or completed.
- State coercion, vault envelope validation, import isolation, and failure
  rollback gained regression coverage. The suite now contains 231 test
  functions (247 collected cases).

## Method

1. Read every package boundary and the architecture, security, protocol, and
   install documentation.
2. Established objective hotspots with file/function line counts.
3. Searched blocking I/O, subprocess/socket use, broad exception handlers,
   persistence calls, TODO markers, and state deserializers.
4. Ran Ruff and the existing tests before changes. The initial sandbox lacked
   the system OpenGL libraries required to import Qt; pure checks were run
   first, then the missing runtime libraries were supplied and the complete
   offscreen suite was used as the regression gate.
5. Made small compatibility-preserving extractions, with focused tests before
   proceeding to the next area.

### Baseline indicators

| Indicator | Baseline observation |
|---|---:|
| Python source | about 21,500 lines |
| Test functions | 204 |
| Largest modules | `ui/theme.py` 1,917; `ui/main_window.py` 1,808; `ui/terminal.py` 1,675; `ui/widgets.py` 1,310; `protocols/rdp/session.py` 1,284 |
| Longest functions | several UI constructors/builders over 120 lines; largest 172 lines |
| Ruff | clean |
| CI | Python 3.10/3.12 on Ubuntu; offscreen Qt; local sshd integration; Linux PyInstaller build |

## Finding register

Severity is based on user/security impact and likelihood. “Resolved” means a
regression test exists in this branch.

| ID | Severity | Finding and impact | Disposition |
|---|---|---|---|
| SEC-01 | High | `build_freerdp_args` always emitted `/cert:ignore`, so the existing “Accept any certificate” checkbox had no effect and the documented secure default was bypassed. | **Resolved:** `/cert:tofu` by default; explicit ignore maps to FreeRDP and mstsc settings. |
| PERF-01 | High | `PortScanner` materialized and submitted the entire host×port matrix (up to roughly 512,000 futures under UI parser limits). Memory grew with the whole scan and Cancel was delayed by submission/context-manager shutdown. | **Resolved:** lazy task generator, bounded in-flight futures, event cancellation, callback isolation. |
| REL-01 | High | Settings, sessions, snippets, and vault each had subtly different temp-write logic; none flushed file data before rename. `known_hosts` was written in place, so interruption could erase trust state. | **Resolved:** shared 0600 write+flush+fsync+replace primitive and filename-writer adapter. |
| SEC-02 | High | FreeRDP argument files accepted newline/NUL-bearing values. Imported or hand-edited fields could become additional options when parsed one-per-line. Failed writes also left secret-bearing temp files behind. | **Resolved:** reject ambiguous control characters, fsync successful files, clean every failure path. |
| SEC-03 | Medium/High | Vault envelope parsing assumed object-shaped JSON and allowed an attacker-controlled, effectively unbounded PBKDF2 iteration count. Corrupt structures raised incidental exceptions or could consume CPU for an excessive period. | **Resolved:** structural checks, 10M hard ceiling (well above UI maximum), minimum GCM-tag length, uniform `CryptoError`. |
| REL-02 | Medium | A failed vault create/put/delete could leave in-memory state claiming a change that was not durable. Explicit `save(new_key)` did not update the key used by the next auto-save. | **Resolved:** rollback collection state and update the in-memory master only after successful persistence. |
| REL-03 | Medium | Non-object settings JSON and invalid UTF-8 could crash load. Python interpreted the string `"false"` as true, including security-sensitive session booleans. Structured values could reach Qt APIs. | **Resolved:** shared finite/bounded scalar coercion and safe fallbacks; JSON `null` retains prior false semantics. |
| ARCH-01 | Medium | Importing a pure helper such as `rdp.negotiate` executed package registration, imported Qt, and recursively loaded every built-in plugin. This contradicted the documented “testable without GUI” boundary. | **Resolved:** side-effect-free protocol packages and explicit built-in specs. Subprocess tests assert no PySide import. |
| DATA-01 | Medium | Session import stored caller-owned objects, mutated ids/names in place, and generated duplicate `name (imported)` labels on repeated imports. Duplicate groups survived file load. | **Resolved:** deep-copy on import, collision-safe ids, deterministic unique suffixes, ordered group de-duplication. |
| ARCH-02 | Medium | Four UI modules exceed 1,300 lines and combine construction, state, styling, and event orchestration. Changes have a wide regression radius. | **Open:** staged extraction plan below; avoid a single rewrite. |
| REL-04 | Medium | `SessionStore.get()` exposes mutable internal models, and most mutating methods update memory before persistence. A failed save can therefore leave process state ahead of disk. | **Open:** introduce transaction snapshots or immutable DTO/copy APIs after call-site inventory. |
| FEAT-01 | Medium | `Session.agent_forwarding` and `Settings.default_download_dir` are persisted but not wired to runtime/UI behavior. They appear supported at model level but are inert. | **Open:** either implement with explicit security UX/tests or remove through a versioned migration; do not silently activate agent forwarding. |
| TEST-01 | Medium | CI has no Windows job, native X11/Wayland smoke test, FreeRDP compatibility matrix, or coverage trend. Linux offscreen tests cannot validate native embedding/input end to end. | **Open:** staged CI additions below. |
| SEC-04 | Medium | FreeRDP 2 lacks `/args-from:file:`; its compatibility fallback still puts a password in process argv. The UI warns about command-line exposure, but automatic fallback has the same local disclosure risk. | **Open:** prefer FreeRDP 3; investigate a supported file descriptor/credential helper for v2 or refuse password automation by policy. |
| PERF-02 | Low/Medium | A completed large scan retains every result for UI/export, and resolver calls cannot be interrupted below the socket timeout. Bounded futures fix the spike, not total result volume. | **Open:** optional streaming/export mode and configurable result cap. |
| OBS-01 | Low/Medium | Numerous broad catches are justified at process/UI boundaries, but several silently discard optional-backend errors. Diagnosis depends on reproducing with debug logging. | **Open:** replace silent catches with rate-limited debug records as modules are touched. |

## Refactoring strategy

The rule for every stage is: preserve file formats and public imports, add a
characterization test first, keep one conceptual change per patch, and retain a
straightforward revert path.

### Stage 0 — characterize and secure boundaries (completed here)

1. Pin certificate, malformed-state, scanner, import, and persistence failure
   behavior with regression tests.
2. Add shared `core.coerce` and `core.persistence` utilities.
3. Extract pure RDP command policy and make plugin loading explicit.
4. Keep compatibility aliases in `protocols.rdp.session`.

**Rollback:** each consumer can return to its local writer; `client.py` exports
have the same function signatures as the former controller helpers.

### Stage 1 — make core mutations transactional

1. Inventory every caller that mutates a model returned by `SessionStore.get()`.
2. Add `update(session_id, mutator)` with snapshot→save→commit semantics.
3. Add copy-returning read APIs, migrate call sites one feature at a time, then
   deprecate mutable reads.
4. Add concurrent-reader/writer and disk-failure tests.

Do not combine this with a JSON format migration.

### Stage 2 — split UI composition from orchestration

Prioritize by churn and size:

1. `main_window.py`: extract menu/toolbar action catalog, dashboard factory,
   and tab lifecycle coordinator.
2. `terminal.py`: keep `TerminalCore` pure; split key encoding, palette/style
   run creation, clipboard/OSC handling, and QWidget painting.
3. `theme.py`: split palette data, stylesheet generation, icons, and runtime
   theme notifications.
4. `widgets.py`: one module per coherent widget family.

Every extraction should leave a forwarding import for one release and run the
GUI smoke/regression suite before the next extraction.

### Stage 3 — formalize worker lifecycles

1. Model SSH/local/RDP lifecycle transitions as explicit state tables.
2. Give every worker a cancellation token and bounded shutdown contract.
3. Replace silent cleanup catches with structured diagnostic events.
4. Add fault-injection tests for connect, authentication, process startup,
   channel close, and application shutdown.

Thread ownership rules in `ARCHITECTURE.md` remain invariants, not refactoring
targets.

### Stage 4 — broaden compatibility gates

1. Add Python 3.11/3.13 as support policy dictates and cache dependencies.
2. Add Windows unit/GUI smoke and package-build jobs.
3. Add an Xvfb+FreeRDP command/embedding smoke job; keep Wayland/XWayland
   decision logic as pure tests.
4. Track branch coverage without initially enforcing a disruptive threshold;
   establish a baseline, then ratchet only upward.
5. Add dependency auditing and a scheduled (not every-PR) live compatibility
   matrix for supported Paramiko/FreeRDP versions.

## Architectural decisions from this pass

- **Persistence is a core service, not store-specific plumbing.** All sensitive
  state replacements use a private same-directory temporary file, file fsync,
  atomic replace, and best-effort directory fsync.
- **Protocol policy is pure; protocol runtime may use Qt.** Detection, parsing,
  and argument construction must be importable without PySide. Widgets,
  `QProcess`, and controller signals stay in runtime modules.
- **Plugin discovery is explicit.** Package import does not mutate a global
  registry. Built-ins and entry points are loaded only when `registry()` is
  requested.
- **Cancellation bounds work, not just callbacks.** Producers must stop
  scheduling promptly and cap queued tasks; suppressing UI updates alone is
  not cancellation.
- **Persisted data is untrusted.** Deserializers validate shape, coerce only
  documented scalar forms, bound expensive parameters, and choose secure
  defaults.

See [TESTING.md](TESTING.md) for the verification matrix and commands.
