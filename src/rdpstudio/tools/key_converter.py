"""SSH key utility: randomart visualizer, OpenSSH ⇄ PuTTY PPK converter."""

from __future__ import annotations

import base64
import hashlib
import struct
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa


def generate_randomart(raw_digest: bytes, key_type: str = "ED25519", bits: int = 256) -> str:
    """Classic OpenSSH Drunken Bishop algorithm for visual key fingerprint art."""
    # 9 rows, 17 columns
    width, height = 17, 9
    field = [[0 for _ in range(width)] for _ in range(height)]
    symbols = " .o+=*BOX@%&#/^SE"
    x, y = width // 2, height // 2

    for byte in raw_digest:
        for _ in range(4):
            dx = 1 if (byte & 0x01) else -1
            dy = 1 if (byte & 0x02) else -1
            byte >>= 2
            x = min(max(0, x + dx), width - 1)
            y = min(max(0, y + dy), height - 1)
            if field[y][x] < len(symbols) - 3:
                field[y][x] += 1

    field[height // 2][width // 2] = len(symbols) - 2  # 'S' = start
    field[y][x] = len(symbols) - 1  # 'E' = end

    header = f"[{key_type} {bits}]"
    top_bar = "+" + header.center(width, "-") + "+"
    bottom_bar = "+" + "-" * width + "+"

    lines = [top_bar]
    for row in field:
        row_str = "".join(symbols[v] for v in row)
        lines.append(f"|{row_str}|")
    lines.append(bottom_bar)
    return "\n".join(lines)


def parse_key_details(key_file_path: str | Path, passphrase: str | None = None) -> dict[str, Any]:
    """Parse key file and return comprehensive metadata, fingerprint, randomart, and public key."""
    p = Path(key_file_path)
    data = p.read_bytes()
    pass_bytes = passphrase.encode("utf-8") if passphrase else None

    # Load private or public key
    is_private = True
    try:
        key = serialization.load_ssh_private_key(data, password=pass_bytes)
    except Exception:
        try:
            key = serialization.load_pem_private_key(data, password=pass_bytes)
        except Exception:
            is_private = False
            try:
                key = serialization.load_ssh_public_key(data)
            except Exception as e:
                raise ValueError(f"Could not load key file: {e}") from e

    if is_private:
        pub_key = key.public_key()
    else:
        pub_key = key

    # Format public key
    ssh_pub_bytes = pub_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    ssh_pub_str = ssh_pub_bytes.decode("utf-8", "replace")

    # Extract raw key blob from OpenSSH format (parts: 'ssh-ed25519 <base64> [comment]')
    parts = ssh_pub_str.split()
    raw_key_blob = base64.b64decode(parts[1]) if len(parts) >= 2 else b""

    # SHA256 and MD5 fingerprints
    sha256_digest = hashlib.sha256(raw_key_blob).digest()
    sha256_fp = "SHA256:" + base64.b64encode(sha256_digest).decode().rstrip("=")
    md5_digest = hashlib.md5(raw_key_blob).hexdigest()
    md5_fp = ":".join(md5_digest[i : i + 2] for i in range(0, len(md5_digest), 2))

    # Algorithm details
    if isinstance(pub_key, ed25519.Ed25519PublicKey):
        algo = "ED25519"
        bits = 256
    elif isinstance(pub_key, rsa.RSAPublicKey):
        algo = "RSA"
        bits = pub_key.key_size
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        algo = f"ECDSA-{pub_key.curve.name}"
        bits = pub_key.key_size
    else:
        algo = "UNKNOWN"
        bits = 0

    art = generate_randomart(sha256_digest, key_type=algo, bits=bits)

    return {
        "path": str(p),
        "is_private": is_private,
        "algorithm": algo,
        "bits": bits,
        "sha256": sha256_fp,
        "md5": md5_fp,
        "public_key": ssh_pub_str,
        "randomart": art,
    }


def openssh_to_ppk(key_data: bytes, comment: str = "rdpstudio-key", passphrase: str = "") -> str:
    """Generate a PuTTY PPK v2/v3 compatible formatted text string from unencrypted OpenSSH key."""
    # Attempt to load as private key
    try:
        key = serialization.load_ssh_private_key(key_data, password=None)
    except Exception:
        key = serialization.load_pem_private_key(key_data, password=None)

    pub_key = key.public_key()
    pub_bytes = pub_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    pub_parts = pub_bytes.decode().split()
    pub_b64 = pub_parts[1] if len(pub_parts) >= 2 else ""

    if isinstance(key, ed25519.Ed25519PrivateKey):
        key_type = "ssh-ed25519"
        # Ed25519 raw private bytes (32 bytes secret + 32 bytes public)
        raw_priv = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        raw_pub = pub_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        priv_blob = struct.pack(">I", 32) + raw_priv + struct.pack(">I", 32) + raw_pub
        priv_b64 = base64.b64encode(priv_blob).decode()
    elif isinstance(key, rsa.RSAPrivateKey):
        key_type = "ssh-rsa"
        priv_numbers = key.private_numbers()
        # PPK RSA private blob
        d_bytes = priv_numbers.d.to_bytes((priv_numbers.d.bit_length() + 7) // 8, "big")
        p_bytes = priv_numbers.p.to_bytes((priv_numbers.p.bit_length() + 7) // 8, "big")
        q_bytes = priv_numbers.q.to_bytes((priv_numbers.q.bit_length() + 7) // 8, "big")
        iqmp_bytes = priv_numbers.iqmp.to_bytes((priv_numbers.iqmp.bit_length() + 7) // 8, "big")
        blob = (
            struct.pack(">I", len(d_bytes)) + d_bytes +
            struct.pack(">I", len(p_bytes)) + p_bytes +
            struct.pack(">I", len(q_bytes)) + q_bytes +
            struct.pack(">I", len(iqmp_bytes)) + iqmp_bytes
        )
        priv_b64 = base64.b64encode(blob).decode()
    else:
        raise ValueError("Unsupported key type for PPK conversion")

    # Format into lines of 64 chars
    def wrap_64(s: str) -> list[str]:
        return [s[i : i + 64] for i in range(0, len(s), 64)]

    pub_lines = wrap_64(pub_b64)
    priv_lines = wrap_64(priv_b64)

    # MAC computation for unencrypted PPK v2
    mac_data = (
        struct.pack(">I", len(key_type)) + key_type.encode() +
        struct.pack(">I", 4) + b"none" +
        struct.pack(">I", len(comment)) + comment.encode() +
        struct.pack(">I", len(base64.b64decode(pub_b64))) + base64.b64decode(pub_b64) +
        struct.pack(">I", len(base64.b64decode(priv_b64))) + base64.b64decode(priv_b64)
    )
    mac = hashlib.sha1(mac_data).hexdigest()

    ppk_lines = [
        f"PuTTY-User-Key-File-2: {key_type}",
        "Encryption: none",
        f"Comment: {comment}",
        f"Public-Lines: {len(pub_lines)}",
        *pub_lines,
        f"Private-Lines: {len(priv_lines)}",
        *priv_lines,
        f"Private-MAC: {mac}",
    ]
    return "\n".join(ppk_lines) + "\n"
