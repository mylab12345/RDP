"""SSH key utilities: generation, loading, fingerprints, agent discovery."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

import paramiko

from ...core.log import get_logger

log = get_logger("ssh.keys")


class KeyOperationError(RuntimeError):
    pass


@dataclass
class KeyInfo:
    path: str
    key_type: str
    bits: int
    sha256_fingerprint: str
    md5_fingerprint: str
    has_passphrase: bool
    comment: str = ""


def fingerprint_sha64(pkey: paramiko.PKey) -> str:
    import base64
    import hashlib

    digest = hashlib.sha256(pkey.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def fingerprint_md5(pkey: paramiko.PKey) -> str:
    import hashlib

    digest = hashlib.md5(pkey.asbytes()).hexdigest()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2)).upper()


def describe(pkey: paramiko.PKey) -> tuple[str, int]:
    name = pkey.get_name()
    bits = 0
    get_bits = getattr(pkey, "get_bits", None)
    if callable(get_bits):
        try:
            bits = int(get_bits())
        except (TypeError, ValueError):
            bits = 0
    if not bits:
        bits = getattr(pkey, "bits", 0) or 0
    try:
        bits = int(bits)
    except (TypeError, ValueError):
        bits = 0
    if not bits:
        bits = len(pkey.asbytes()) * 8  # rough fallback
    return name, bits


def load_key(path: str, passphrase: str | None = None) -> paramiko.PKey:
    """Load any supported private key type; raises KeyOperationError on failure."""
    path = os.path.expanduser(path)
    last_err: Exception | None = None
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            key = cls.from_private_key_file(path, password=passphrase)
            return key
        except paramiko.PasswordRequiredException:
            raise
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise KeyOperationError(f"cannot load key {path}: {last_err}") from last_err


def key_info(path: str, passphrase: str | None = None) -> KeyInfo:
    path = os.path.expanduser(path)
    has_pass = False
    try:
        key = load_key(path, passphrase)
    except paramiko.PasswordRequiredException:
        has_pass = True
        raise
    name, bits = describe(key)
    return KeyInfo(
        path=path,
        key_type=name,
        bits=bits,
        sha256_fingerprint=fingerprint_sha64(key),
        md5_fingerprint=fingerprint_md5(key),
        has_passphrase=has_pass,
    )


def generate(
    path: str,
    key_type: str = "ed25519",
    bits: int = 4096,
    passphrase: str = "",
    comment: str = "",
) -> KeyInfo:
    """Generate a new keypair, writing private (0600) and public parts."""
    path = os.path.expanduser(path)
    if os.path.exists(path):
        raise KeyOperationError(f"{path} already exists")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if key_type == "ed25519":
        pkey: paramiko.PKey = _generate_ed25519(path, passphrase)
    elif key_type == "ecdsa":
        pkey = paramiko.ECDSAKey.generate()
        write_private(pkey, path, passphrase)
    elif key_type == "rsa":
        pkey = paramiko.RSAKey.generate(bits=bits)
        write_private(pkey, path, passphrase)
    else:
        raise KeyOperationError(f"unsupported key type {key_type!r}")

    write_public(pkey, path + ".pub", comment)
    name, nbits = describe(pkey)
    return KeyInfo(
        path=path,
        key_type=name,
        bits=nbits,
        sha256_fingerprint=fingerprint_sha64(pkey),
        md5_fingerprint=fingerprint_md5(pkey),
        has_passphrase=bool(passphrase),
        comment=comment,
    )



def _generate_ed25519(path: str, passphrase: str) -> paramiko.PKey:
    """Ed25519 generation across paramiko versions.

    paramiko >= 5 removed ``Ed25519Key.generate`` and its private-key writer;
    in that case we generate with ``cryptography`` and persist OpenSSH-format
    PEM ourselves (still loadable by paramiko and OpenSSH tools).
    """
    gen = getattr(paramiko.Ed25519Key, "generate", None)
    if callable(gen):
        pkey = gen()
        write_private(pkey, path, passphrase)
        return pkey
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    if passphrase:
        enc: serialization.KeySerializationEncryption = (
            serialization.BestAvailableEncryption(passphrase.encode())
        )
    else:
        enc = serialization.NoEncryption()
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, enc
    )
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    return paramiko.Ed25519Key.from_private_key_file(path, password=passphrase or None)


def write_private(pkey: paramiko.PKey, path: str, passphrase: str = "") -> None:
    def write_to(fh) -> None:
        pkey.write_private_key(fh, password=passphrase or None)

    _write_private_0600(path, write_to)


def _write_private_0600(path: str, writer) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            writer(fh)
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise
    os.chmod(path, 0o600)


def write_public(pkey: paramiko.PKey, path: str, comment: str = "") -> None:
    """Write the OpenSSH-format public key line."""
    line = f"{pkey.get_name()} {pkey.get_base64()} {comment}\n".strip() + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(line)
    os.chmod(path, 0o644)


def agent_keys() -> list[tuple[str, str]]:
    """Return [(fingerprint, description)] for keys currently loaded in ssh-agent."""
    try:
        agent = paramiko.Agent()
        keys = agent.get_keys() or []
        result = []
        for k in keys:
            desc = getattr(k, "name", "") or ""
            result.append((fingerprint_sha64(k), f"{k.get_name()} {desc}".strip()))
        agent.close()
        return result
    except Exception:  # noqa: BLE001
        return []


def check_permissions(path: str) -> bool:
    """True when the private-key file permissions are not group/world open (POSIX)."""
    st = os.stat(os.path.expanduser(path))
    return not (st.st_mode & (stat.S_IRWXG | stat.S_IRWXO))
