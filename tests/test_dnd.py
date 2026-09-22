"""Tests for file-browser drag-and-drop payloads, drop routing and local copy."""

from __future__ import annotations

from rdpstudio.ui.dnd import (
    classify_drop,
    copy_local_files,
    decode_local_payload,
    decode_remote_payload,
    encode_local_payload,
    encode_remote_payload,
    urls_to_local_paths,
)


# ----------------------------------------------------------------------
# payloads
# ----------------------------------------------------------------------
def test_remote_payload_roundtrip():
    blob = encode_remote_payload("/srv/data", ["a.txt", "ünïcodé f.bin"])
    assert decode_remote_payload(blob) == ("/srv/data", ["a.txt", "ünïcodé f.bin"])


def test_local_payload_roundtrip():
    blob = encode_local_payload("/tmp", ["x"])
    assert decode_local_payload(blob) == ("/tmp", ["x"])


def test_decode_tolerates_garbage():
    assert decode_remote_payload(b"") == ("", [])
    assert decode_local_payload(b"\xff\xfe\n\n") == ("��", [])
    assert decode_remote_payload(b"/dir\n") == ("/dir", [])


# ----------------------------------------------------------------------
# urls
# ----------------------------------------------------------------------
def test_urls_file_scheme_and_percent_decoding():
    assert urls_to_local_paths(["file:///tmp/a%20b/c.txt"]) == ["/tmp/a b/c.txt"]
    assert urls_to_local_paths(["file://localhost/etc/hosts"]) == ["/etc/hosts"]


def test_urls_ignore_non_file_and_comments():
    assert urls_to_local_paths(["https://example.com/x", "# a comment", "  "]) == []
    assert urls_to_local_paths(["file:///C:/Temp/x.txt"]) == ["C:/Temp/x.txt"]


def test_urls_accept_plain_existing_paths(tmp_path):
    f = tmp_path / "plain.txt"
    f.write_text("x")
    assert urls_to_local_paths([str(f)]) == [str(f)]
    assert urls_to_local_paths([str(tmp_path / "missing")]) == []


# ----------------------------------------------------------------------
# classify_drop
# ----------------------------------------------------------------------
def _remote(dir_: str, names: list[str]) -> tuple[bool, bytes]:
    return True, encode_remote_payload(dir_, names)


def _local(dir_: str, names: list[str]) -> tuple[bool, bytes]:
    return True, encode_local_payload(dir_, names)


def test_remote_onto_local_pane_downloads():
    has, blob = _remote("/srv", ["a.txt", "b"])
    action = classify_drop(
        target_is_remote=False, target_dir="/tmp/out",
        has_remote_mime=has, remote_payload=blob,
    )
    assert action.action == "download"
    assert action.names == ("a.txt", "b")
    assert action.source_dir == "/srv" and action.dest_dir == "/tmp/out"


def test_remote_onto_remote_pane_is_noop():
    has, blob = _remote("/srv", ["a.txt"])
    action = classify_drop(
        target_is_remote=True, target_dir="/srv/other",
        has_remote_mime=has, remote_payload=blob,
    )
    assert action.action == "none"


def test_local_onto_remote_pane_uploads():
    has, blob = _local("/tmp/in", ["a.txt"])
    action = classify_drop(
        target_is_remote=True, target_dir="/srv",
        has_remote_mime=False, has_local_mime=has, local_payload=blob,
    )
    assert action.action == "upload"
    assert action.names == ("a.txt",)
    assert action.source_dir == "/tmp/in" and action.dest_dir == "/srv"


def test_local_onto_other_local_dir_copies(tmp_path):
    src = tmp_path / "a"
    dst = tmp_path / "b"
    src.mkdir()
    dst.mkdir()
    has, blob = _local(str(src), ["f.txt"])
    action = classify_drop(
        target_is_remote=False, target_dir=str(dst),
        has_remote_mime=False, has_local_mime=has, local_payload=blob,
    )
    assert action.action == "copy_local"
    assert action.names == ("f.txt",)


def test_local_onto_same_local_dir_is_noop(tmp_path):
    has, blob = _local(str(tmp_path), ["f.txt"])
    action = classify_drop(
        target_is_remote=False, target_dir=str(tmp_path),
        has_remote_mime=False, has_local_mime=has, local_payload=blob,
    )
    assert action.action == "none"


def test_os_files_onto_remote_pane_upload_full_paths(tmp_path):
    urls = [f"file://{tmp_path}/a.txt", f"file://{tmp_path}/sub/b.txt"]
    action = classify_drop(target_is_remote=True, target_dir="/srv", has_remote_mime=False, urls=urls)
    assert action.action == "upload"
    assert action.names == (f"{tmp_path}/a.txt", f"{tmp_path}/sub/b.txt")
    assert action.reason == "os-drop"


def test_os_directory_onto_local_pane_navigates(tmp_path):
    action = classify_drop(
        target_is_remote=False, target_dir="/tmp", has_remote_mime=False,
        urls=[f"file://{tmp_path}"],
    )
    assert action.action == "navigate"
    assert action.dest_dir == str(tmp_path)


def test_os_files_onto_local_pane_copy(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x")
    action = classify_drop(
        target_is_remote=False, target_dir="/tmp/out", has_remote_mime=False,
        urls=[f"file://{f}"],
    )
    assert action.action == "copy_local"
    assert action.names == (str(f),)


def test_garbage_drop_is_noop():
    action = classify_drop(
        target_is_remote=True, target_dir="/srv", has_remote_mime=False,
        urls=["https://example.com/"],
    )
    assert action.action == "none" and action.reason


def test_in_app_mime_wins_over_urls():
    has, blob = _remote("/srv", ["a"])
    action = classify_drop(
        target_is_remote=False, target_dir="/tmp",
        has_remote_mime=has, remote_payload=blob,
        urls=["file:///etc/hosts"],
    )
    assert action.action == "download" and action.source_dir == "/srv"


# ----------------------------------------------------------------------
# copy_local_files
# ----------------------------------------------------------------------
def test_copy_files_and_dirs(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_bytes(b"a")
    (src / "sub" / "b.txt").write_bytes(b"bb")
    dst = tmp_path / "dst"

    copied, err = copy_local_files(("a.txt", "sub"), str(src), str(dst))
    assert (copied, err) == (2, "")
    assert (dst / "a.txt").read_bytes() == b"a"
    assert (dst / "sub" / "b.txt").read_bytes() == b"bb"


def test_copy_absolute_os_drop_paths(tmp_path):
    f = tmp_path / "drop.txt"
    f.write_bytes(b"dropped")
    copied, err = copy_local_files((str(f),), "", str(tmp_path / "dst"))
    assert (copied, err) == (1, "")
    assert (tmp_path / "dst" / "drop.txt").read_bytes() == b"dropped"


def test_copy_missing_reports_error(tmp_path):
    copied, err = copy_local_files(("nope.txt",), str(tmp_path), str(tmp_path / "dst"))
    assert copied == 0 and "nope.txt" in err


def test_copy_into_itself_is_skipped(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"a")
    copied, err = copy_local_files(("a.txt",), str(tmp_path), str(tmp_path))
    assert (copied, err) == (0, "")
