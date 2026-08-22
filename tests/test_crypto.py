"""Vault crypto: seal/open roundtrips, tamper detection, KDF binding."""

from __future__ import annotations

import pytest

from rdpstudio.core.crypto import CryptoError, Envelope, open_envelope, seal


def test_roundtrip():
    env = seal("master-pass", b"secret payload", iterations=60_000)
    text = env.to_json()
    env2 = Envelope.from_json(text)
    assert open_envelope(env2, "master-pass") == b"secret payload"


def test_wrong_passphrase_rejected():
    env = seal("master-pass", b"data", iterations=60_000)
    with pytest.raises(CryptoError):
        open_envelope(env, "wrong")


def test_tampered_ciphertext_rejected():
    import dataclasses

    env = seal("master-pass", b"data", iterations=60_000)
    tampered = dataclasses.replace(env, ciphertext=env.ciphertext[:-4] + b"\x00\x00\x00\x00")
    with pytest.raises(CryptoError):
        open_envelope(tampered, "master-pass")


def test_kdf_params_bound_by_aad():
    # ciphertext sealed under iteration count N cannot be opened under N+1
    env = seal("m", b"data", iterations=60_000)
    forged = Envelope(env.salt, 60_001, env.nonce, env.ciphertext)
    with pytest.raises(CryptoError):
        open_envelope(forged, "m")


def test_format_version_guard():
    import json

    env = seal("m", b"x", iterations=60_000)
    doc = json.loads(env.to_json())
    doc["format"] = 99
    with pytest.raises(CryptoError):
        Envelope.from_json(json.dumps(doc))
