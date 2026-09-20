"""Tests for the credential guard — ensures that sessions without saved
credentials require username+password before connecting.

These tests exercise only the pure-Python logic of ``needs_credential_prompt``
so they work in a headless environment (no Qt / libGL required).
"""

from __future__ import annotations

from rdpstudio.core.auth import needs_credential_prompt
from rdpstudio.core.models import (
    AUTH_AGENT,
    AUTH_KEY,
    AUTH_PASSWORD,
    PROTOCOL_LOCAL,
    PROTOCOL_RDP,
    PROTOCOL_SSH,
    Session,
)


class TestNeedsCredentialPrompt:
    def test_local_never_prompts(self):
        s = Session(protocol=PROTOCOL_LOCAL)
        assert not needs_credential_prompt(s)

    def test_rdp_bare_ip_prompts(self):
        """The core bug: bare IP with no credentials must trigger the prompt."""
        s = Session(protocol=PROTOCOL_RDP, host="192.168.1.100")
        assert needs_credential_prompt(s)

    def test_ssh_bare_ip_prompts(self):
        s = Session(protocol=PROTOCOL_SSH, host="10.0.0.5")
        assert needs_credential_prompt(s)

    def test_rdp_full_credentials_no_prompt(self):
        s = Session(
            protocol=PROTOCOL_RDP,
            host="192.168.1.100",
            username="Administrator",
            password="Secret1!",
        )
        assert not needs_credential_prompt(s)

    def test_rdp_vault_credential_no_prompt(self):
        s = Session(
            protocol=PROTOCOL_RDP,
            host="192.168.1.100",
            credential_id="vault-entry-abc",
        )
        assert not needs_credential_prompt(s)

    def test_rdp_missing_password_prompts(self):
        """Username without password must still prompt."""
        s = Session(
            protocol=PROTOCOL_RDP,
            host="192.168.1.100",
            username="Administrator",
            password="",
        )
        assert needs_credential_prompt(s)

    def test_rdp_missing_username_prompts(self):
        """Password without username must prompt."""
        s = Session(
            protocol=PROTOCOL_RDP,
            host="192.168.1.100",
            username="",
            password="Secret1!",
        )
        assert needs_credential_prompt(s)

    def test_ssh_key_auth_username_present_no_prompt(self):
        """Key auth only needs username — no prompt when both are present."""
        s = Session(
            protocol=PROTOCOL_SSH,
            host="10.0.0.1",
            username="root",
            auth=AUTH_KEY,
            key_path="/home/user/.ssh/id_ed25519",
        )
        assert not needs_credential_prompt(s)

    def test_ssh_key_auth_no_username_prompts(self):
        """Key auth but missing username must prompt."""
        s = Session(
            protocol=PROTOCOL_SSH,
            host="10.0.0.1",
            username="",
            auth=AUTH_KEY,
            key_path="/home/user/.ssh/id_ed25519",
        )
        assert needs_credential_prompt(s)

    def test_ssh_agent_auth_username_present_no_prompt(self):
        s = Session(
            protocol=PROTOCOL_SSH,
            host="10.0.0.1",
            username="deploy",
            auth=AUTH_AGENT,
        )
        assert not needs_credential_prompt(s)

    def test_ssh_password_auth_full_no_prompt(self):
        s = Session(
            protocol=PROTOCOL_SSH,
            host="10.0.0.1",
            username="ubuntu",
            password="p@ssw0rd",
            auth=AUTH_PASSWORD,
        )
        assert not needs_credential_prompt(s)

    def test_domain_machine_no_creds_prompts(self):
        """Domain RDP session with domain set but no user/pass still prompts."""
        s = Session(
            protocol=PROTOCOL_RDP,
            host="server.corp.example.com",
            domain="CORP",
        )
        assert needs_credential_prompt(s)

    def test_domain_machine_full_creds_no_prompt(self):
        s = Session(
            protocol=PROTOCOL_RDP,
            host="server.corp.example.com",
            domain="CORP",
            username="jdoe",
            password="hunter2",
        )
        assert not needs_credential_prompt(s)
