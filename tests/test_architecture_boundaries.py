"""Tests that pin module boundaries and prevent accidental GUI coupling."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_pure_protocol_helpers_do_not_import_qt():
    script = r"""
import sys
import rdpstudio.protocols.rdp.client
import rdpstudio.protocols.rdp.embed
import rdpstudio.protocols.rdp.negotiate
import rdpstudio.protocols.rdp.rdpfile
import rdpstudio.protocols.ssh.keys
import rdpstudio.protocols.ssh.knownhosts
assert "rdpstudio.core.plugin" not in sys.modules
assert not any(name == "PySide6" or name.startswith("PySide6.") for name in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_protocol_packages_have_no_registration_side_effects():
    script = r"""
import sys
import rdpstudio.protocols.local
import rdpstudio.protocols.rdp
import rdpstudio.protocols.ssh
assert "rdpstudio.core.plugin" not in sys.modules
assert not any(name == "PySide6" or name.startswith("PySide6.") for name in sys.modules)
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.gui
def test_registry_explicitly_loads_every_builtin_after_reset():
    from rdpstudio.core.plugin import registry, reset_registry

    reset_registry()
    try:
        assert {plugin.id for plugin in registry().all()} >= {"ssh", "rdp", "local"}
    finally:
        reset_registry()
