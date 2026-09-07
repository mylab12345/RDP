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
import binascii
import hashlib
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VAULT_FORMAT = 1
KDF_ALGO = "pbkdf2-sha256"
AEAD_ALGO = "aes-256-gcm"
# A corrupt envelope must not turn unlock into an effectively unbounded CPU
# operation.  This ceiling is deliberately far above the current 310k default
# and the UI's 2M maximum, while still bounding hostile hand-edited files.
MAX_KDF_ITERATIONS = 10_000_000


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
        except (json.JSONDecodeError, TypeError) as exc:
            raise CryptoError("vault file is not valid JSON") from exc
        if not isinstance(data, dict):
            raise CryptoError("vault file is not a JSON object")
        if data.get("format") != VAULT_FORMAT:
            raise CryptoError(f"unsupported vault format {data.get('format')!r}")
        kdf, aead = data.get("kdf"), data.get("aead")
        if not isinstance(kdf, dict) or not isinstance(aead, dict):
            raise CryptoError("vault file is missing kdf/aead sections")
        if kdf.get("algo") != KDF_ALGO or aead.get("algo") != AEAD_ALGO:
            raise CryptoError("unsupported KDF/AEAD algorithm")
        try:
            raw_iterations = kdf["iterations"]
            if isinstance(raw_iterations, bool):
                raise TypeError("boolean KDF iterations")
            iterations = int(raw_iterations)
            salt = _b64d(kdf["salt"])
            nonce = _b64d(aead["nonce"])
            ciphertext = _b64d(aead["ciphertext"])
        except (KeyError, ValueError, TypeError, UnicodeError, binascii.Error) as exc:
            raise CryptoError("vault file is corrupted") from exc
        # Reject structurally impossible envelopes before they hit the KDF /
        # AES-GCM.  The upper iteration bound prevents a tiny corrupt file
        # from pinning a CPU for minutes during unlock.
        if (
            not 1 <= iterations <= MAX_KDF_ITERATIONS
            or len(salt) < 8
            or len(nonce) != 12
            or len(ciphertext) < 16  # AES-GCM authentication tag
        ):
            raise CryptoError("vault file is corrupted")
        return cls(salt=salt, iterations=iterations, nonce=nonce, ciphertext=ciphertext)


def _validate_iterations(iterations: int) -> None:
    if (
        isinstance(iterations, bool)
        or not isinstance(iterations, int)
        or not 1 <= iterations <= MAX_KDF_ITERATIONS
    ):
        raise ValueError(
            f"KDF iterations must be between 1 and {MAX_KDF_ITERATIONS}"
        )


def derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    _validate_iterations(iterations)
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32)


def seal(passphrase: str, plaintext: bytes, iterations: int = 310_000) -> Envelope:
    _validate_iterations(iterations)
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
    if not isinstance(s, str):
        raise TypeError("base64 field must be text")
    return base64.b64decode(s.encode("ascii"), validate=True)
