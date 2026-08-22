"""RDP file generation for mstsc."""

from rdpstudio.core.models import Session
from rdpstudio.protocols.rdp.rdpfile import build_rdp_text, write_rdp_file


def test_basic_file():
    s = Session(protocol="rdp", host="win10.lab", port=3389, username="admin", domain="LAB")
    text = build_rdp_text(s)
    lines = text.splitlines()
    assert "full address:s:win10.lab" in lines
    assert "server port:i:3389" in lines
    assert "username:s:admin" in lines
    assert "domain:s:LAB" in lines
    assert "redirectclipboard:i:1" in lines
    assert "autoreconnection enabled:i:1" in lines


def test_custom_port_and_disable_clipboard():
    s = Session(protocol="rdp", host="rdpgw", port=3390, rdp_clipboard=False, rdp_drives=True)
    text = build_rdp_text(s)
    assert "server port:i:3390" in text.splitlines()
    assert "redirectclipboard:i:0" in text.splitlines()
    assert "drivestoredirect:s:*" in text.splitlines()


def test_gateway():
    s = Session(protocol="rdp", host="inner", rdp_gateway_host="gw.corp", rdp_gateway_user="gwd")
    text = build_rdp_text(s)
    assert "gatewayhostname:s:gw.corp" in text
    assert "gatewayusagemethod:i:4" in text
    assert "gatewayusername:s:gwd" in text


def test_write_file(tmp_path):
    s = Session(id="abc123", name="win box", protocol="rdp", host="w")
    path = write_rdp_file(s, tmp_path)
    assert path.exists()
    assert path.name.endswith("win_box_abc123.rdp")
    assert path.read_text(encoding="utf-16-le")  # mstsc expects UTF-16
