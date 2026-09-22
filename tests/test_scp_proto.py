"""Unit + integration tests for the classic ``scp`` wire-protocol client.

Pure header/quoting helpers are tested without any network; ``ScpClient``
is driven against a scripted in-memory channel; and — when the sandbox can
run one — against a real ``sshd`` + system ``scp`` server, which settles the
trickiest part (the three-ack file exchange) empirically.
"""

from __future__ import annotations

import stat as statmod

import pytest

from rdpstudio.core.retry import is_transient
from rdpstudio.protocols.ssh.scp import (
    ScpClient,
    ScpError,
    format_dir_header,
    format_file_header,
    format_time_header,
    parse_dir_header,
    parse_file_header,
    parse_time_header,
    quote_remote_path,
)


# ----------------------------------------------------------------------
# quoting
# ----------------------------------------------------------------------
def test_quote_simple_path():
    assert quote_remote_path("/home/u/file.txt") == "'/home/u/file.txt'"


def test_quote_path_with_spaces():
    assert quote_remote_path("/home/u/my file.txt") == "'/home/u/my file.txt'"


def test_quote_escapes_single_quote():
    # 'o'clock' -> 'o'"'"'clock'  (close, escaped quote, reopen)
    assert quote_remote_path("o'clock") == "'o'\"'\"'clock'"


@pytest.mark.parametrize("bad", ["", "   ", "a\nb", "a\x00b"])
def test_quote_rejects_unsafe(bad):
    with pytest.raises(ScpError):
        quote_remote_path(bad)


# ----------------------------------------------------------------------
# header parsing / formatting
# ----------------------------------------------------------------------
def test_parse_file_header():
    mode, size, name = parse_file_header("C0644 1234 hello.txt")
    assert (mode, size, name) == (0o644, 1234, "hello.txt")


def test_parse_file_header_name_may_contain_spaces():
    mode, size, name = parse_file_header("C0644 10 my file.txt")
    assert (mode, size, name) == (0o644, 10, "my file.txt")


@pytest.mark.parametrize(
    "line",
    [
        "D0644 10 x",  # wrong kind
        "C0644 10",  # missing name
        "C999 10 x",  # bad octal
        "C0644 ten x",  # bad size
        "C0644 -1 x",  # negative size
        "C0644 10 ..",  # traversal
        "C0644 10 a/b",  # slash
        "C0644 10 -rf",  # option-looking
        "C0644 10 ",  # empty name
    ],
)
def test_parse_file_header_rejects(line):
    with pytest.raises(ScpError):
        parse_file_header(line)


def test_parse_dir_header():
    mode, name = parse_dir_header("D0755 0 mydir")
    assert (mode, name) == (0o755, "mydir")


@pytest.mark.parametrize("line", ["C0755 0 x", "D0755", "D999 0 x", "D0755 0 ../up"])
def test_parse_dir_header_rejects(line):
    with pytest.raises(ScpError):
        parse_dir_header(line)


def test_parse_time_header():
    assert parse_time_header("T1715616000 0 1715616100 0") == (1715616000, 1715616100)


@pytest.mark.parametrize("line", ["C1 2 3 4", "T1 2 3", "Txx 0 1 0"])
def test_parse_time_header_rejects(line):
    with pytest.raises(ScpError):
        parse_time_header(line)


def test_format_parse_roundtrip():
    assert parse_file_header(format_file_header(0o640, 42, "f.bin").decode().rstrip("\n")) == (
        0o640,
        42,
        "f.bin",
    )
    assert parse_dir_header(format_dir_header(0o750, "d").decode().rstrip("\n")) == (0o750, "d")
    assert parse_time_header(format_time_header(11, 22).decode().rstrip("\n")) == (11, 22)


def test_format_rejects_unsafe():
    with pytest.raises(ScpError):
        format_file_header(0o644, 1, "../evil")
    with pytest.raises(ScpError):
        format_file_header(0o644, -5, "ok")
    with pytest.raises(ScpError):
        format_dir_header(0o755, "a/b")


# ----------------------------------------------------------------------
# scripted channel
# ----------------------------------------------------------------------
class FakeChannel:
    """A paramiko-style channel fed from a preloaded byte buffer."""

    def __init__(self, incoming: bytes = b""):
        self._in = bytearray(incoming)
        self.out = bytearray()
        self.cmd = ""
        self.closed = False

    def send(self, data) -> int:
        blob = bytes(data)
        self.out += blob
        return len(blob)

    def recv(self, n: int) -> bytes:
        chunk = bytes(self._in[:n])
        del self._in[:n]
        return chunk

    def settimeout(self, _timeout) -> None:
        pass

    def exec_command(self, cmd: str) -> None:
        self.cmd = cmd

    def close(self) -> None:
        self.closed = True

    def recv_stderr_ready(self) -> bool:
        return False

    def recv_stderr(self, _n: int) -> bytes:
        return b""


class FakeTransport:
    def __init__(self, chan: FakeChannel):
        self.chan = chan

    def open_session(self, timeout=None):
        return self.chan


def _client(chan: FakeChannel) -> ScpClient:
    return ScpClient(FakeTransport(chan))


def test_download_single_file(tmp_path):
    chan = FakeChannel(b"C0644 11 hello.txt\nhello world\x00")
    stats = _client(chan).download("/remote/hello.txt", tmp_path)
    assert (tmp_path / "hello.txt").read_bytes() == b"hello world"
    assert (stats.files, stats.bytes) == (1, 11)
    assert chan.cmd.startswith("scp -f ") and "'/remote/hello.txt'" in chan.cmd
    # kick + pre-file ack + post-file ack
    assert bytes(chan.out) == b"\x00\x00\x00"
    assert chan.closed


def test_download_applies_time_and_mode(tmp_path):
    chan = FakeChannel(b"T1715616000 0 1715616100 0\nC0600 4 f.bin\nabcd\x00")
    _client(chan).download("/r/f.bin", tmp_path)
    target = tmp_path / "f.bin"
    st = target.stat()  # stat first: reading the file bumps atime on relatime mounts
    assert target.read_bytes() == b"abcd"
    assert int(st.st_mtime) == 1715616000
    assert int(st.st_atime) == 1715616100
    assert statmod.S_IMODE(st.st_mode) == 0o600


def test_download_explicit_file_target(tmp_path):
    chan = FakeChannel(b"C0644 3 a.txt\nabc\x00")
    dest = tmp_path / "renamed.txt"
    _client(chan).download("/r/a.txt", dest)
    assert dest.read_bytes() == b"abc"


def test_download_recursive_tree(tmp_path):
    incoming = (
        b"D0755 0 mydir\n"
        b"C0644 3 a.txt\nabc\x00"
        b"D0755 0 sub\n"
        b"C0644 1 b\nz\x00"
        b"E\n"
        b"E\n"
    )
    dest = tmp_path / "newdir"  # does not exist yet: becomes the received dir
    stats = _client(FakeChannel(incoming)).download("/r/mydir", dest, recursive=True)
    assert (dest / "a.txt").read_bytes() == b"abc"
    assert (dest / "sub" / "b").read_bytes() == b"z"
    assert stats.files == 2


def test_download_directory_without_recursive_flag_fails(tmp_path):
    chan = FakeChannel(b"D0755 0 d\n")
    with pytest.raises(ScpError, match="directory"):
        _client(chan).download("/r/d", tmp_path)
    assert chan.closed  # channel is always released


def test_download_remote_error_surfaces(tmp_path):
    chan = FakeChannel(b"\x01scp: /nope: No such file or directory\n")
    with pytest.raises(ScpError, match="No such file"):
        _client(chan).download("/nope", tmp_path)


def test_download_truncated_stream_cleans_tempfile(tmp_path):
    chan = FakeChannel(b"C0644 100 f\nshort")
    with pytest.raises(ScpError, match="closed"):
        _client(chan).download("/r/f", tmp_path)
    leftovers = [p for p in tmp_path.iterdir() if ".kb-scp-part-" in p.name]
    assert leftovers == [] and not (tmp_path / "f").exists()


def test_path_traversal_from_wire_is_rejected(tmp_path):
    chan = FakeChannel(b"C0644 3 ../../evil\nabc\x00")
    with pytest.raises(ScpError, match="[Uu]nsafe|escap"):
        _client(chan).download("/r/evil", tmp_path)


def test_upload_single_file(tmp_path):
    src = tmp_path / "up.txt"
    src.write_bytes(b"payload-123")
    chan = FakeChannel(b"\x00" * 4)  # ready, T-ack, C-ack, post-file ack
    stats = _client(chan).upload(src, "/remote/dir")
    assert (stats.files, stats.bytes) == (1, 11)
    assert chan.cmd.startswith("scp -t ") and "'/remote/dir'" in chan.cmd
    # T line, C line, payload, trailing ack
    head, _, rest = bytes(chan.out).partition(b"\n")
    assert head.startswith(b"T")
    cline, _, rest = rest.partition(b"\n")
    mode, size, name = parse_file_header(cline.decode())
    assert (size, name) == (11, "up.txt") and mode == statmod.S_IMODE(src.stat().st_mode)
    assert rest == b"payload-123\x00"
    assert chan.closed


def test_upload_tree_recursive(tmp_path):
    root = tmp_path / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"a")
    (root / "sub" / "b.txt").write_bytes(b"bb")
    # initial + D(tree) + C(a) + post(a) + D(sub) + C(b) + post(b) + E(sub) + E(tree)
    chan = FakeChannel(b"\x00" * 9)
    stats = _client(chan).upload(root, "/remote", recursive=True, preserve_times=False)
    assert (stats.files, stats.bytes) == (2, 3)
    out = bytes(chan.out)
    assert b"D" in out.split(b"\n")[0]
    assert out.count(b"\nC") == 2 and out.rstrip(b"\x00").endswith(b"E\n")


def test_upload_missing_path_rejected(tmp_path):
    with pytest.raises(ScpError, match="does not exist"):
        _client(FakeChannel()).upload(tmp_path / "nope", "/r")


def test_upload_directory_needs_recursive_flag(tmp_path):
    with pytest.raises(ScpError, match="recursive"):
        _client(FakeChannel()).upload(tmp_path, "/r")


def test_mid_transfer_drop_is_retryable():
    # The engine only retries failures `is_transient` recognizes: a channel
    # that dies mid-transfer must say so in retryable words.
    assert is_transient(ScpError("scp channel closed by remote mid-transfer")) is True
    assert is_transient(ScpError("scp transfer failed (TimeoutError): timed out")) is True
    assert is_transient(ScpError("scp: /x: Permission denied")) is False


def test_channel_open_failure_wraps(tmp_path):
    class DeadTransport:
        def open_session(self, timeout=None):
            raise OSError("boom")

    with pytest.raises(ScpError, match="cannot open scp channel"):
        ScpClient(DeadTransport()).download("/r/f", tmp_path)


# ----------------------------------------------------------------------
# live server: real sshd + system scp (skips when unavailable)
# ----------------------------------------------------------------------
def _live_transport(sshd):
    import paramiko

    transport = paramiko.Transport((sshd["host"], sshd["port"]))
    key = paramiko.Ed25519Key.from_private_key_file(sshd["key"])
    transport.connect(username=sshd["user"], pkey=key)
    return transport


@pytest.mark.integration()
def test_scp_roundtrip_against_real_server(sshd, tmp_path):
    import paramiko

    srv = tmp_path / "srv"
    (srv / "docs").mkdir(parents=True)
    (srv / "hello.txt").write_bytes(b"hello scp\n")
    (srv / "docs" / "n.txt").write_bytes(b"nested\n")

    transport = _live_transport(sshd)
    try:
        client = ScpClient(transport)

        # file download
        dest = tmp_path / "got"
        dest.mkdir()
        stats = client.download(str(srv / "hello.txt"), dest)
        assert (dest / "hello.txt").read_bytes() == b"hello scp\n"
        assert stats.files == 1

        # recursive download
        rdest = tmp_path / "rtree"
        stats = client.download(str(srv), rdest, recursive=True)
        assert (rdest / "hello.txt").exists() and (rdest / "docs" / "n.txt").exists()
        assert stats.files == 2

        # directory without the flag: the real server refuses with
        # "not a regular file" — the exact string the engine's blind-SCP
        # fallback keys on.
        with pytest.raises(ScpError, match="regular file"):
            client.download(str(srv / "docs"), tmp_path / "x")

        # file upload + tree upload, verified back over SFTP
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            up = tmp_path / "up.txt"
            up.write_bytes(b"upload-ok")
            client.upload(up, str(srv))
            assert sftp.stat(str(srv / "up.txt")).st_size == 9

            client.upload(srv / "docs", str(srv / "docs-copy"), recursive=True)
            assert sftp.stat(str(srv / "docs-copy" / "n.txt")).st_size == 7
        finally:
            sftp.close()
    finally:
        transport.close()
