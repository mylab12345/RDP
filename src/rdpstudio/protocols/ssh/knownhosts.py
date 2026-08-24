"""Host-key verification (TOFU) backed by our own known_hosts file.

Policy:
- ``strict``   - unknown hosts are rejected outright.
- ``accept-new`` (default, TOFU) - unknown hosts are accepted after the user
  confirms; *changed* keys are always treated as a hard failure requiring
  explicit, loudly-warned acceptance.
"""

from __future__ import annotations

from pathlib import Path

import paramiko

from ...core.log import get_logger
from ...core.plugin import PromptProvider

log = get_logger("ssh.knownhosts")


class HostKeyDecision:
    ACCEPT = "accept"
    REJECT = "reject"
    ONCE = "once"  # accept for this connection only


class KnownHostsVerifier(paramiko.MissingHostKeyPolicy):
    """paramiko policy that consults our known_hosts + the user."""

    def __init__(self, path: Path, policy: str, prompter: PromptProvider | None) -> None:
        self.path = path
        self.policy = policy  # strict | accept-new
        self.prompter = prompter
        self.host_keys = paramiko.HostKeys(str(path)) if path.exists() else paramiko.HostKeys()
        self.last_fingerprint = ""
        self.last_changed = False

    def missing_host_key(self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey):
        from .keys import fingerprint_sha64

        fingerprint = fingerprint_sha64(key)
        existing = self.host_keys.lookup(hostname)
        existing_keys = list(existing.values()) if existing else []
        changed = bool(existing_keys) and not any(k == key for k in existing_keys)
        self.last_fingerprint = fingerprint
        self.last_changed = changed

        if changed:
            # Changed keys are serious (possible MITM). Require explicit consent.
            accept = bool(
                self.prompter and self.prompter.ask_host_key(hostname, key.get_name(), fingerprint, changed=True)
            )
        elif self.policy == "strict":
            accept = False
        else:
            accept = bool(
                self.prompter and self.prompter.ask_host_key(hostname, key.get_name(), fingerprint, changed=False)
            )

        if not accept:
            raise paramiko.SSHException(
                f"host key for {hostname} rejected ({'changed' if changed else 'unknown'})"
            )
        self.host_keys.add(hostname, key.get_name(), key)
        self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.host_keys.save(str(self.path))
            try:
                import os

                os.chmod(self.path, 0o600)
            except OSError:
                pass
        except OSError:
            log.exception("could not persist known_hosts")

    def known_fingerprint(self, hostname: str) -> str | None:
        entry = self.host_keys.lookup(hostname)
        if not entry:
            return None
        from .keys import fingerprint_sha64

        keys = list(entry.values())
        if not keys:
            return None
        return fingerprint_sha64(keys[0])
