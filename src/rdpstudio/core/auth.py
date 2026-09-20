"""Pure authentication policy helpers shared by UI and runtime code.

These helpers keep protocol/auth-method rules out of Qt widgets so they can be
validated with fast unit tests and reused consistently across dialogs,
persistence repair, and connection guards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

AUTH_PASSWORD = "password"
AUTH_KEY = "key"
AUTH_AGENT = "agent"
AUTH_CREDENTIAL = "credential"
AUTH_NONE = "none"

PROTOCOL_SSH = "ssh"
PROTOCOL_RDP = "rdp"
PROTOCOL_LOCAL = "local"

_PROTOCOL_AUTH_OPTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    PROTOCOL_SSH: (
        (AUTH_PASSWORD, "Password"),
        (AUTH_CREDENTIAL, "Saved credential"),
        (AUTH_KEY, "Private key"),
        (AUTH_AGENT, "SSH agent"),
    ),
    PROTOCOL_RDP: (
        (AUTH_PASSWORD, "Password"),
        (AUTH_CREDENTIAL, "Saved credential"),
    ),
    PROTOCOL_LOCAL: ((AUTH_NONE, "No authentication"),),
}

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .models import Session


def auth_method_options(protocol: str) -> tuple[tuple[str, str], ...]:
    """Return ``(method, label)`` pairs valid for ``protocol``."""
    return _PROTOCOL_AUTH_OPTIONS.get(protocol, ((AUTH_PASSWORD, "Password"),))


def supported_auth_methods(protocol: str) -> tuple[str, ...]:
    """Return the auth method ids valid for ``protocol``."""
    return tuple(method for method, _label in auth_method_options(protocol))


def normalize_auth_for_protocol(protocol: str, auth: str | None) -> str:
    """Repair unsupported / stale auth methods to a safe protocol default."""
    value = str(auth or "")
    methods = supported_auth_methods(protocol)
    if value in methods:
        return value
    if protocol == PROTOCOL_LOCAL:
        return AUTH_NONE
    return AUTH_PASSWORD


def auth_uses_saved_password(protocol: str, auth: str | None) -> bool:
    return normalize_auth_for_protocol(protocol, auth) == AUTH_PASSWORD


def auth_uses_credential(protocol: str, auth: str | None) -> bool:
    return normalize_auth_for_protocol(protocol, auth) == AUTH_CREDENTIAL


def auth_uses_key_file(protocol: str, auth: str | None) -> bool:
    return (
        protocol == PROTOCOL_SSH
        and normalize_auth_for_protocol(protocol, auth) == AUTH_KEY
    )


def auth_uses_agent(protocol: str, auth: str | None) -> bool:
    return (
        protocol == PROTOCOL_SSH
        and normalize_auth_for_protocol(protocol, auth) == AUTH_AGENT
    )


def auth_supports_vault_passphrase(protocol: str, auth: str | None) -> bool:
    """Whether a vault credential can provide an SSH key passphrase."""
    return auth_uses_key_file(protocol, auth)


def preferred_auth_for_session(session: Session) -> str:
    """Best-effort UI/runtime auth selection for a saved session.

    Historical releases could persist ``credential_id`` while leaving
    ``auth="password"``. That state still works at runtime, but the editor
    should surface it as "Saved credential" rather than pretending a blank
    plain-text password is configured.
    """
    auth = normalize_auth_for_protocol(session.protocol, getattr(session, "auth", ""))
    if (
        getattr(session, "protocol", "") in (PROTOCOL_SSH, PROTOCOL_RDP)
        and auth == AUTH_PASSWORD
        and getattr(session, "credential_id", "")
        and not getattr(session, "password", "")
    ):
        return AUTH_CREDENTIAL
    return auth


def needs_credential_prompt(defn: Session) -> bool:
    """Return True when the session lacks sufficient credentials to connect."""
    if defn.protocol == PROTOCOL_LOCAL:
        return False
    if getattr(defn, "credential_id", ""):
        return False
    auth = normalize_auth_for_protocol(defn.protocol, getattr(defn, "auth", ""))
    if auth in (AUTH_KEY, AUTH_AGENT, AUTH_NONE):
        return not bool(getattr(defn, "username", ""))
    return not bool(getattr(defn, "username", "")) or not bool(getattr(defn, "password", ""))
