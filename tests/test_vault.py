"""Credential vault behaviour."""

from __future__ import annotations

import time

from rdpstudio.core.vault import Credential, CredentialVault, VaultLockedError


def make_vault(tmp_path):
    return CredentialVault(tmp_path / "vault.bin", kdf_iterations=60_000)


def test_create_unlock_cycle(tmp_path):
    vault = make_vault(tmp_path)
    vault.create("master1")
    cred = Credential(name="prod root", kind="password", username="root", secret="hunter2")
    vault.put(cred)
    vault.lock()

    assert not vault.unlocked
    with open(vault.path, "rb") as fh:
        blob = fh.read()
    assert b"hunter2" not in blob  # encrypted at rest

    vault2 = make_vault(tmp_path)
    vault2.unlock("master1")
    got = vault2.get(cred.id)
    assert got is not None and got.secret == "hunter2"


def test_wrong_master_fails(tmp_path):
    from rdpstudio.core.crypto import CryptoError

    vault = make_vault(tmp_path)
    vault.create("right")
    vault.lock()
    vault2 = make_vault(tmp_path)
    with open("/dev/null", "w") as _:  # silence any output
        pass
    try:
        vault2.unlock("wrong")
        raised = False
    except CryptoError:
        raised = True
    assert raised


def test_locked_operations_raise(tmp_path):
    vault = make_vault(tmp_path)
    with __import__("pytest").raises(VaultLockedError):
        vault.entries()


def test_autolock_after_idle(tmp_path):
    vault = make_vault(tmp_path)
    vault.create("m")
    vault.last_activity = time.monotonic() - 99999
    assert vault.lock_if_due(15) is True
    assert not vault.unlocked


def test_change_master(tmp_path):
    vault = make_vault(tmp_path)
    vault.create("old")
    cred = Credential(name="x", secret="s3cret")
    vault.put(cred)
    vault.change_master("old", "new")
    vault.lock()
    fresh = make_vault(tmp_path)
    fresh.unlock("new")
    assert fresh.get(cred.id).secret == "s3cret"
