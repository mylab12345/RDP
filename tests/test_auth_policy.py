"""Pure authentication policy coverage."""

from __future__ import annotations

import pytest

from rdpstudio.core.auth import (
    AUTH_AGENT,
    AUTH_CREDENTIAL,
    AUTH_NONE,
    AUTH_PASSWORD,
    PROTOCOL_LOCAL,
    PROTOCOL_RDP,
    PROTOCOL_SSH,
    auth_method_options,
    needs_credential_prompt,
    preferred_auth_for_session,
)
from rdpstudio.core.models import Session

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_auth_method_options_are_protocol_specific():
    assert [method for method, _label in auth_method_options(PROTOCOL_SSH)] == [
        AUTH_PASSWORD,
        AUTH_CREDENTIAL,
        "key",
        AUTH_AGENT,
    ]
    assert [method for method, _label in auth_method_options(PROTOCOL_RDP)] == [
        AUTH_PASSWORD,
        AUTH_CREDENTIAL,
    ]
    assert [method for method, _label in auth_method_options(PROTOCOL_LOCAL)] == [AUTH_NONE]


def test_preferred_auth_surfaces_legacy_vault_backed_password_state():
    session = Session(
        protocol=PROTOCOL_RDP,
        host="win.lab",
        username="admin",
        auth=AUTH_PASSWORD,
        password="",
        credential_id="vault-123",
    )
    assert preferred_auth_for_session(session) == AUTH_CREDENTIAL


def test_session_loader_repairs_invalid_protocol_auth_combinations():
    rdp = Session.from_dict({"protocol": PROTOCOL_RDP, "auth": AUTH_AGENT})
    local = Session.from_dict({"protocol": PROTOCOL_LOCAL, "auth": AUTH_PASSWORD})

    assert rdp.auth == AUTH_PASSWORD
    assert local.auth == AUTH_NONE


def test_needs_credential_prompt_uses_normalized_auth_rules():
    session = Session(protocol=PROTOCOL_RDP, host="win.lab", username="admin", auth=AUTH_AGENT)
    assert needs_credential_prompt(session) is True

    session.credential_id = "vault-123"
    assert needs_credential_prompt(session) is False
