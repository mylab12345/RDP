"""Coverage for extracted pure helpers used by GUI-facing modules."""

from __future__ import annotations

import pytest

from rdpstudio.core.downloads import resolve_download_start
from rdpstudio.core.fuzzy import fuzzy_score
from rdpstudio.protocols.ssh.target import parse_ssh_target

pytestmark = [pytest.mark.unit, pytest.mark.regression]


def test_fuzzy_score_requires_subsequence():
    assert fuzzy_score("abc", "xabc") > 0
    assert fuzzy_score("acb", "abc") == 0
    assert fuzzy_score("zz", "abc") == 0
    assert fuzzy_score("abx", "ab") == 0


def test_fuzzy_score_rewards_early_consecutive_matches():
    assert fuzzy_score("nw", "Network Tools & Port Scanner") > fuzzy_score("nw", "Session")
    assert fuzzy_score("se", "Settings…") > fuzzy_score("se", "imported session")
    assert fuzzy_score("", "anything") == 1


def test_resolve_download_start_prefers_existing(tmp_path):
    configured = tmp_path / "configured"
    configured.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    assert resolve_download_start("/nonexistent", str(configured), str(home)) == str(configured)
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert resolve_download_start(str(explicit), str(configured), str(home)) == str(explicit)
    assert resolve_download_start("/nope", "/missing", str(home)) == str(home)
    assert resolve_download_start("", "", "") == ""


def test_parse_ssh_target_supports_ipv4_and_ipv6():
    assert parse_ssh_target("[::1]:2222") == ("", "::1", 2222)
    assert parse_ssh_target("root@[2001:db8::5]") == ("root", "2001:db8::5", 0)
    assert parse_ssh_target("::1") == ("", "::1", 0)
    assert parse_ssh_target("user@host:22") == ("user", "host", 22)
    assert parse_ssh_target("not a host!") is None
