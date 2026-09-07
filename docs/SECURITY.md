# Security design

## Threat model

KB-Remote holds credentials for many machines and speaks to untrusted
servers. We assume:

- The workstation may be inspected by an attacker **after** a session
  (protect at-rest secrets).
- The network path to servers is hostile (verify host keys; prefer TOFU with
  loud change warnings).
- Local logs may be shared for debugging (never write secrets).

## Credential vault

- **KDF**: PBKDF2-HMAC-SHA256, ≥310,000 iterations by default (OWASP 2023),
  128-bit random salt per vault. Iterations are configurable for
  future-proofing; the AAD binds them to the ciphertext so an attacker cannot
  downgrade parameters (`crypto._aad`). Envelope parsing imposes a 10,000,000
  ceiling (well above the UI maximum) so a corrupt file cannot request an
  effectively unbounded CPU operation.
- **Cipher**: AES-256-GCM via `cryptography` — authenticated encryption;
  tampering or wrong passphrase both yield `CryptoError` without
  distinguishing which occurred.
- **At rest**: single `vault.bin`, written through the shared durable
  transaction (private temp file, file `fsync`, atomic replace) with `0600`
  permissions. Only the encrypted envelope exists on disk.
- **In memory**: the master passphrase is held only while unlocked, and wiped
  on lock/auto-lock (15 min inactivity default). Secrets are registered with
  the redaction filter and removed on lock.
- **Session store** contains no vault secrets — sessions reference vault
  entries by id. The one exception is a *plain password the user explicitly
  saves on a session* (the simple no-vault flow): it is written as-is to the
  local sessions file, surfaced with a tooltip that it is plain text, and is
  **stripped from JSON exports**. Use the vault instead for shared machines.
- **Autolock**: `Vault.lock_if_due()` runs on a 30 s UI timer.

Known limitation: while unlocked, the master key exists in process memory —
the same trade-off every password manager makes for auto-save.

## Host key verification

- Own `known_hosts` file, separate from the system one.
- Policy `accept-new` (default, TOFU): unknown keys → dialog showing
  SHA256 fingerprint → user consent → persisted.
- Policy `strict`: unknown keys are rejected; they must be provisioned in the
  application's known-hosts file out of band.
- **Changed keys are always a hard stop**: the dialog states the MITM risk
  explicitly and requires re-consent; refusal aborts the connection. The
  fingerprint is surfaced (SHA256 + MD5 in the key manager) so it can be
  compared out-of-band.
- Trust updates use the same private, atomic persistence transaction as other
  state; interruption cannot replace `known_hosts` with a partial file.

## Logging

`core.log._RedactingFilter` masks any registered secret in both file and
console sinks before formatting. Passwords are additionally registered via
`redact_secret()` the moment they enter the process (vault unlock, auth
prompt, material resolution).

## Process hygiene

- RDP passwords on **FreeRDP 3** are placed in a private `0600`
  `/args-from:file:` file and removed shortly after process startup. The
  secret does not appear in `argv`/`ps`; newline/NUL-bearing fields are
  rejected before that file is created. The explicit `rdp_pass_on_cmdline`
  option remains documented as unsafe.
- **FreeRDP 2 limitation:** it has no `/args-from:file:` support and its
  non-interactive compatibility path uses `/p:` in `argv`. Prefer FreeRDP 3
  on multi-user workstations. `mstsc` never receives a password via CLI;
  Windows credential UI is used.
- FreeRDP certificate checking defaults to TOFU (`/cert:tofu`), while mstsc
  keeps authentication warnings enabled. “Accept any certificate” explicitly
  switches to `/cert:ignore` / mstsc authentication level 0 and is labelled
  “not recommended”.
- Tunnels bind to `127.0.0.1` by default, never `0.0.0.0`.
- No telemetry, no network calls except the sessions you open.

## Reporting

Please open a private security advisory on GitHub (Security tab) rather than a
public issue for vulnerabilities.


## Hardening notes

These properties are covered by regression tests in
`tests/test_security_hardening.py`:

| Area | Property |
|---|---|
| RDP credentials | FreeRDP 3 receives the password through a short-lived `0600` argument file, not normal `argv`; direct command-line exposure is an explicit opt-in. FreeRDP 2's documented compatibility fallback remains process-visible (CWE-214). |
| RDP certificates | TOFU/warnings are the default on FreeRDP/mstsc; certificate ignore is emitted only for the explicit per-session opt-in. |
| Vault envelope | Wrong container shapes, malformed AEAD fields and excessive PBKDF2 work factors fail as `CryptoError` before expensive decryption. |
| State on disk | The config directory is `0700` and `sessions.json` is `0600`; pre-existing lax permissions are tightened at startup. A saved session password is plain text by design, so the file must stay private (CWE-276). |
| `.rdp` files | Written `0600`, with the filename derived from the session name **sanitised** so it cannot traverse out of the target directory (CWE-22). |
| SFTP transfers | Remote-supplied names are reduced to their basename and re-checked against the destination root, so a hostile server cannot write outside it ("Zip-Slip"). Non-regular files (devices, FIFOs, symlinks) are skipped. |
| Terminal | OSC-52 clipboard payloads are applied **once**, only when freshly received (a remote host cannot hold the local clipboard hostage), are size-bounded, and are strictly base64-validated. |
| Dependencies | Floors exclude known CVEs: `paramiko>=3.4.1` (CVE-2023-48795 "Terrapin"), `cryptography>=44.0.1` (CVE-2024-12797). |
