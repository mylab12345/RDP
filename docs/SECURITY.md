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

- **KDF**: PBKDF2-HMAC-SHA256, ≥310,000 iterations (OWASP 2023), 128-bit
  random salt per vault. Iterations are configurable (Settings) for
  future-proofing; the AAD binds them to the ciphertext so an attacker cannot
  downgrade parameters (`crypto._aad`).
- **Cipher**: AES-256-GCM via `cryptography` — authenticated encryption;
  tampering or wrong passphrase both yield `CryptoError` without
  distinguishing which occurred.
- **At rest**: single `vault.bin`, written atomically (temp file + rename)
  with `0600` permissions. Only the encrypted envelope exists on disk.
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
- Policy `strict`: every unknown key must be manually accepted.
- **Changed keys are always a hard stop**: the dialog states the MITM risk
  explicitly and requires re-consent; refusal aborts the connection. The
  fingerprint is surfaced (SHA256 + MD5 in the key manager) so it can be
  compared out-of-band.

## Logging

`core.log._RedactingFilter` masks any registered secret in both file and
console sinks before formatting. Passwords are additionally registered via
`redact_secret()` the moment they enter the process (vault unlock, auth
prompt, material resolution).

## Process hygiene

- RDP passwords: a **plain password saved on the session** is passed on
  FreeRDP's command line (`/p:`, `ps(1)` visibility) — a GUI-launched xfreerdp
  has no terminal to prompt on, so this is the only way the simple no-vault
  flow can log in. **Vault** passwords are **not** passed by default
  (`ps(1)` visibility); the opt-in `rdp_pass_on_cmdline` flag is documented as
  unsafe in the session editor. `mstsc` never receives passwords via CLI —
  Windows credential UI is used.
- FreeRDP certificate checking defaults to TOFU (`/cert:tofu`);
  `/cert:ignore` is opt-in and labelled "not recommended".
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
| RDP credentials | The password is passed to FreeRDP over **stdin**, never `argv`. Process arguments are world-readable (`ps`, `/proc/<pid>/cmdline`), so the command-line form is an explicit, clearly-labelled opt-in only (CWE-214). |
| State on disk | The config directory is `0700` and `sessions.json` is `0600`; pre-existing lax permissions are tightened at startup. A saved session password is plain text by design, so the file must stay private (CWE-276). |
| `.rdp` files | Written `0600`, with the filename derived from the session name **sanitised** so it cannot traverse out of the target directory (CWE-22). |
| SFTP transfers | Remote-supplied names are reduced to their basename and re-checked against the destination root, so a hostile server cannot write outside it ("Zip-Slip"). Non-regular files (devices, FIFOs, symlinks) are skipped. |
| Terminal | OSC-52 clipboard payloads are applied **once**, only when freshly received (a remote host cannot hold the local clipboard hostage), are size-bounded, and are strictly base64-validated. |
| Dependencies | Floors exclude known CVEs: `paramiko>=3.4.1` (CVE-2023-48795 "Terrapin"), `cryptography>=44.0.1` (CVE-2024-12797). |
