"""Pure parsing helpers for SSH-style quick-connect targets."""

from __future__ import annotations


def parse_ssh_target(text: str) -> tuple[str, str, int] | None:
    """Parse ``[user@]host[:port]``; returns ``(user, host, port)`` or None.

    IPv6 is supported as ``[::1]:2222`` (bracketed, with port) or a bare
    literal like ``::1`` (no port).
    """
    text = text.strip()
    if not text or "/" in text or " " in text:
        return None
    user = ""
    if "@" in text:
        user, _, rest = text.partition("@")
        text = rest
    port = 0
    if text.startswith("["):
        host, _, rest = text[1:].partition("]")
        if not host:
            return None
        if rest:
            if not rest.startswith(":") or not rest[1:].isdigit():
                return None
            port = int(rest[1:])
        text = host
    elif ":" in text:
        host, _, port_s = text.rpartition(":")
        if ":" in host:
            return user, text, 0
        if not host or not port_s.isdigit():
            return None
        port = int(port_s)
        text = host
    if not text:
        return None
    return user, text, port


__all__ = ["parse_ssh_target"]
