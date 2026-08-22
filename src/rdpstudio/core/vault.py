"""Encrypted credential vault.

Secrets (passwords, key passphrases) are AES-256-GCM encrypted under a master
passphrase. Nothing readable is ever written to disk; unlocking happens in
memory and the vault auto-locks after inactivity.

The vault also records *references*: SSH keys stored on disk are referenced by
path and their passphrases can live in vault entries.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .crypto import CryptoError, Envelope, open_envelope, seal
from .log import get_logger, redact_secret

log = get_logger("vault")


@dataclass
class Credential:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    kind: str = "password"  # password | passphrase | secret
    username: str = ""
    secret: str = ""  # kept in memory only; encrypted at rest
    host_hint: str = ""
    notes: str = ""
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Credential:
        c = cls()
        for k, v in d.items():
            if hasattr(c, k):
                setattr(c, k, v)
        return c

    def safe_summary(self) -> str:
        return f"{self.name or self.id} · {self.kind} · user={self.username or '—'}"


class VaultLockedError(RuntimeError):
    pass


class VaultBusyError(RuntimeError):
    pass


class CredentialVault:
    """In-memory unlocked vault backed by an encrypted file."""

    def __init__(self, path: Path, kdf_iterations: int = 310_000) -> None:
        self.path = path
        self.kdf_iterations = kdf_iterations
        self._entries: dict[str, Credential] = {}
        self.unlocked = False
        self.last_activity = time.monotonic()
        # The master passphrase is kept in memory *only* while unlocked so the
        # vault can re-encrypt on every change without re-prompting. It never
        # touches disk and is wiped on lock().
        self._master: str | None = None

    # ------------------------------------------------------------------
    @property
    def exists(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def create(self, master_passphrase: str) -> None:
        if not master_passphrase:
            raise ValueError("master passphrase must not be empty")
        self._entries = {}
        self.unlocked = True
        self._master = master_passphrase
        self._save_locked(master_passphrase)

    def unlock(self, master_passphrase: str) -> None:
        if not self.exists:
            raise CryptoError("vault does not exist")
        env = Envelope.from_json(self.path.read_text(encoding="utf-8"))
        raw = open_envelope(env, master_passphrase)
        data = json.loads(raw.decode("utf-8"))
        self._entries = {c["id"]: Credential.from_dict(c) for c in data.get("entries", [])}
        self.unlocked = True
        self._master = master_passphrase
        self.last_activity = time.monotonic()
        log.info("vault unlocked (%d entries)", len(self._entries))

    def lock(self) -> None:
        for cred in self._entries.values():
            redact_secret(cred.secret)
        self._entries = {}
        self.unlocked = False
        self._master = None
        log.info("vault locked")

    def save_if_master(self) -> bool:
        """Persist changes if the vault holds the in-memory master key."""
        if self.unlocked and self._master:
            self._save_locked(self._master)
            return True
        return False

    # -- autolock --------------------------------------------------------
    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def lock_if_due(self, idle_minutes: int) -> bool:
        if self.unlocked and idle_minutes > 0:
            if time.monotonic() - self.last_activity > idle_minutes * 60:
                self.lock()
                return True
        return False

    # -- entries ---------------------------------------------------------
    def _require_unlocked(self) -> None:
        if not self.unlocked:
            raise VaultLockedError("vault is locked")

    def entries(self) -> list[Credential]:
        self._require_unlocked()
        self.touch()
        return sorted(self._entries.values(), key=lambda c: c.name.lower())

    def get(self, credential_id: str) -> Credential | None:
        self._require_unlocked()
        self.touch()
        return self._entries.get(credential_id)

    def put(self, cred: Credential) -> Credential:
        """Insert/update an entry and persist immediately (auto-save).

        Persistence requires the in-memory master (set by create/unlock);
        otherwise the change lives only in memory until an explicit save().
        """
        self._require_unlocked()
        if not cred.id or cred.id in ("new",):
            cred.id = uuid.uuid4().hex[:12]
        cred.updated_at = time.time()
        self._entries[cred.id] = cred
        self.save_if_master()
        return cred

    def delete(self, credential_id: str) -> None:
        self._require_unlocked()
        self._entries.pop(credential_id, None)
        self.save_if_master()

    # -- persistence -----------------------------------------------------
    def save(self, master_passphrase: str) -> None:
        self._require_unlocked()
        self._save_locked(master_passphrase)

    def _save_locked(self, master_passphrase: str) -> None:
        raw = json.dumps(
            {"entries": [c.to_dict() for c in self._entries.values()]}, ensure_ascii=False
        ).encode("utf-8")
        env = seal(master_passphrase, raw, self.kdf_iterations)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".vault-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(env.to_json())
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def change_master(self, old_passphrase: str, new_passphrase: str) -> None:
        """Re-encrypt under a new master passphrase (verifies old first)."""
        if not self.unlocked:
            # one-shot verification without changing in-memory state
            probe = CredentialVault(self.path, self.kdf_iterations)
            probe.unlock(old_passphrase)
        elif self.exists:
            # verify old passphrase against the file before overwriting
            probe = CredentialVault(self.path, self.kdf_iterations)
            probe.unlock(old_passphrase)
        if not new_passphrase:
            raise ValueError("master passphrase must not be empty")
        self._save_locked(new_passphrase)
