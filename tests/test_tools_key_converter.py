"""Unit tests for SSH Key Converter, randomart generator, and PPK export."""

from __future__ import annotations

import hashlib

from rdpstudio.protocols.ssh import keys
from rdpstudio.tools.key_converter import generate_randomart, openssh_to_ppk, parse_key_details


def test_randomart_generation():
    digest = hashlib.sha256(b"rdpstudio-test-key").digest()
    art = generate_randomart(digest, key_type="ED25519", bits=256)
    assert "+--[ED25519 256]--+" in art
    lines = art.strip().splitlines()
    assert len(lines) == 11
    assert lines[0].startswith("+")
    assert lines[-1].startswith("+")


def test_key_inspector_and_ppk_conversion(tmp_path):
    key_path = str(tmp_path / "id_ed25519_test")
    info = keys.generate(key_path, key_type="ed25519", bits=256)
    assert info.key_type == "ssh-ed25519"

    details = parse_key_details(key_path)
    assert details["algorithm"] == "ED25519"
    assert details["is_private"] is True
    assert details["sha256"].startswith("SHA256:")
    assert "ssh-ed25519" in details["public_key"]

    # PPK Conversion
    raw_key = (tmp_path / "id_ed25519_test").read_bytes()
    ppk_text = openssh_to_ppk(raw_key, comment="test-key")
    assert "PuTTY-User-Key-File-2: ssh-ed25519" in ppk_text
    assert "Private-MAC:" in ppk_text
    assert "Comment: test-key" in ppk_text
