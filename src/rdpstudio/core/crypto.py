"""Envelope encryption for the credential vault.

- Key derivation: PBKDF2-HMAC-SHA256 (iterations configurable, OWASP ≥310k).
- Payload encryption: AES-256-GCM via the ``cryptography`` package
  (authenticated; tampering is detected on open).

The vault file is a small JSON document::

    {
      "format": 1,
      "kdf":  {"algo": "pbkdf2-sha256", "salt": "<b64>", "iterations": 310000},
      "aead": {"algo": "aes-256-gcm", "nonce": "<b64>", "ciphertext": "<b64>"}
    }

The AAD binds the KDF parameters to the ciphertext so parameters cannot be
silently downgraded.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VAULT_FORMAT = 1
KDF_ALGO = "pbkdf2-sha256"
AEAD_ALGO = "aes-256-gcm"


class CryptoError(Exception):
    """Raised for wrong passphrase or tampered ciphertext."""


@dataclass(frozen=True)
class Envelope:
    salt: bytes
    iterations: int
    nonce: bytes
    ciphertext: bytes

    # -- serialisation --------------------------------------------------
    def to_json(self) -> str:
        return json.dumps(
            {
                "format": VAULT_FORMAT,
                "kdf": {
                    "algo": KDF_ALGO,
                    "salt": _b64e(self.salt),
                    "iterations": self.iterations,
                },
                "aead": {
                    "algo": AEAD_ALGO,
                    "nonce": _b64e(self.nonce),
                    "ciphertext": _b64e(self.ciphertext),
                },
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> Envelope:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CryptoError("vault file is not valid JSON") from exc
        if data.get("format") != VAULT_FORMAT:
            raise CryptoError(f"unsupported vault format {data.get('format')!r}")
        kdf, aead = data.get("kdf"), data.get("aead")
        if not kdf or not aead:
            raise CryptoError("vault file is missing kdf/aead sections")
        if kdf.get("algo") != KDF_ALGO or aead.get("algo") != AEAD_ALGO:
            raise CryptoError("unsupported KDF/AEAD algorithm")
        try:
            iterations = int(kdf["iterations"])
            salt = _b64d(kdf["salt"])
            nonce = _b64d(aead["nonce"])
            ciphertext = _b64d(aead["ciphertext"])
        except (KeyError, ValueError, TypeError) as exc:
            raise CryptoError("vault file is corrupted") from exc
        # Reject structurally impossible envelopes before they hit the KDF /
        # AES-GCM (0 iterations, truncated nonce, empty ciphertext).
        if iterations < 1 or len(salt) < 8 or len(nonce) != 12 or not ciphertext:
            raise CryptoError("vault file is corrupted")
        return cls(salt=salt, iterations=iterations, nonce=nonce, ciphertext=ciphertext)


def derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    if iterations < 1:
        raise ValueError("KDF iterations must be positive")
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)


def seal(passphrase: str, plaintext: bytes, iterations: int = 310_000) -> Envelope:
    if iterations < 1:
        raise ValueError("KDF iterations must be positive")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(passphrase, salt, iterations)
    aad = _aad(salt, iterations)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return Envelope(salt=salt, iterations=iterations, nonce=nonce, ciphertext=ct)


def open_envelope(env: Envelope, passphrase: str) -> bytes:
    key = derive_key(passphrase, env.salt, env.iterations)
    try:
        return AESGCM(key).decrypt(env.nonce, env.ciphertext, _aad(env.salt, env.iterations))
    except Exception as exc:  # invalid tag OR wrong key — do not distinguish
        raise CryptoError("wrong passphrase or vault corrupted") from exc


def _aad(salt: bytes, iterations: int) -> bytes:
    return f"rdpstudio-vault:{VAULT_FORMAT}:{KDF_ALGO}:{iterations}:".encode() + salt


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    # validate=True: a corrupted vault must fail loudly, not decode garbage.
    return base64.b64decode(s.encode("ascii"), validate=True)
