"""Tests for terminal color schemes: shape, validity and readability."""

from __future__ import annotations

import re

import pytest

from rdpstudio.ui import terminal_schemes as schemes

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_seven_schemes_in_stable_order():
    assert schemes.scheme_ids() == [
        "mobaxterm", "dracula", "monokai", "nord",
        "solarized-dark", "solarized-light", "light",
    ]


def test_default_scheme_is_mobaxterm():
    assert schemes.DEFAULT_SCHEME == "mobaxterm"
    assert schemes.get_scheme("mobaxterm")["label"].startswith("MobaXterm")


@pytest.mark.parametrize("sid", [None, "", "no-such-scheme"])
def test_unknown_scheme_falls_back_to_default(sid):
    assert schemes.get_scheme(sid) is schemes.get_scheme(schemes.DEFAULT_SCHEME)


def test_choices_cover_all_schemes_with_labels():
    choices = schemes.scheme_choices()
    assert [c[0] for c in choices] == schemes.scheme_ids()
    assert all(label.strip() for _sid, label in choices)


@pytest.mark.parametrize("sid", schemes.scheme_ids())
def test_scheme_shape_and_valid_colors(sid):
    s = schemes.get_scheme(sid)
    assert s["id"] == sid
    for key in ("fg", "bg", "cursor", "sel", "fg_dim"):
        assert _HEX.match(s[key]), f"{sid}.{key} = {s[key]!r}"
    assert isinstance(s["dark"], bool)
    assert len(s["16"]) == 16
    assert all(_HEX.match(c) for c in s["16"])


@pytest.mark.parametrize("sid", schemes.scheme_ids())
def test_primary_text_is_readable(sid):
    """Every scheme's default fg/bg must clear WCAG AA for large text (3:1).

    (Measured values are all ≥ 4.1; the bar is set a hair lower so future
    palette tweaks have room without silently shipping mud.)
    """
    s = schemes.get_scheme(sid)
    assert schemes.contrast_ratio(s["fg"], s["bg"]) >= 4.0


def test_contrast_ratio_sanity():
    assert schemes.contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, rel=0.01)
    assert schemes.contrast_ratio("#123456", "#123456") == pytest.approx(1.0)
