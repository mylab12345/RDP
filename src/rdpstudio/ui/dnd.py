"""Drag-and-drop file transfers for the SFTP browser (MobaXterm-style).

Pure helpers (no Qt at import time) plus thin Qt glue:

- drag remote files onto the local pane (or a system file manager) to
  download them;
- drag local files onto the remote pane to upload them;
- drop files from the system file manager onto the remote pane to upload,
  onto the local pane to copy;
- drag between the panes works in both directions.

The wire format for pane-to-pane drags is a newline-joined payload under
:data:`MIME_REMOTE_FILES` / :data:`MIME_LOCAL_FILES`; drops from outside
the app arrive as the standard ``text/uri-list``. :func:`classify_drop`
turns a drop into a single :class:`DropAction` the dialog can execute, so
the routing logic is unit-testable without widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote
from urllib.request import url2pathname

MIME_REMOTE_FILES = "application/x-kbremote-remote-files"
MIME_LOCAL_FILES = "application/x-kbremote-local-files"


@dataclass(frozen=True)
class DropAction:
    """One resolved drop: what to move, from where, to where."""

    action: str  # download | upload | copy_local | navigate | none
    names: tuple[str, ...] = ()
    source_dir: str = ""
    dest_dir: str = ""
    reason: str = ""  # human note when action == "none"


def encode_remote_payload(remote_dir: str, names: list[str]) -> bytes:
    """Payload for a drag *from* the remote pane."""
    lines = [remote_dir, *names]
    return "\n".join(lines).encode("utf-8")


def decode_remote_payload(data: bytes) -> tuple[str, list[str]]:
    """Inverse of :func:`encode_remote_payload` → (remote_dir, names)."""
    parts = data.decode("utf-8", "replace").split("\n")
    if not parts:
        return "", []
    return parts[0], [p for p in parts[1:] if p]


def encode_local_payload(local_dir: str, names: list[str]) -> bytes:
    lines = [local_dir, *names]
    return "\n".join(lines).encode("utf-8")


def decode_local_payload(data: bytes) -> tuple[str, list[str]]:
    parts = data.decode("utf-8", "replace").split("\n")
    if not parts:
        return "", []
    return parts[0], [p for p in parts[1:] if p]


def urls_to_local_paths(urls: list[str]) -> list[str]:
    """Turn ``file://`` URLs (as carried by ``text/uri-list``) into paths.

    Non-file URLs are ignored. Percent-escapes are decoded; Windows
    ``file:///C:/...`` forms are normalized to ``C:/...``.
    """
    out: list[str] = []
    for url in urls:
        text = url.strip()
        if not text or text.startswith("#"):
            continue
        if text.lower().startswith("file:"):
            path = url2pathname(unquote(text[5:]))
            # "file:///path" carries an empty netloc: collapse the spurious
            # slashes ("///tmp/x" -> "/tmp/x"); "//host/..." keeps its own
            # handling below.
            if path.startswith("///"):
                path = path[2:]
            # url2pathname on POSIX leaves a leading "//host/..." for
            # file://host/path — keep it simple and strip a localhost netloc.
            if path.startswith("//localhost/"):
                path = path[len("//localhost"):]
            # Windows drive form: "/C:/..." → "C:/..."
            if len(path) >= 3 and path[0] == "/" and path[2] == ":" and path[1].isalpha():
                path = path[1:]
            # Qt may give "///C:/" variants; url2pathname handles most.
            out.append(path)
        elif "://" not in text and Path(text).exists():
            # Some managers deliver plain paths (no scheme) — accept those.
            out.append(text)
    return out


def classify_drop(
    *,
    target_is_remote: bool,
    target_dir: str,
    has_remote_mime: bool,
    remote_payload: bytes = b"",
    has_local_mime: bool = False,
    local_payload: bytes = b"",
    urls: list[str] | None = None,
) -> DropAction:
    """Decide what a drop onto a browser pane should do.

    ``target_is_remote`` selects the pane the pointer is over;
    ``target_dir`` is that pane's current directory. At most one of the
    payload kinds is expected per drop; when several are present the
    in-app mime wins over the OS urls (it is more precise).
    """
    if has_remote_mime:
        remote_dir, names = decode_remote_payload(remote_payload)
        if not names:
            return DropAction("none", reason="no remote files in drag")
        if target_is_remote:
            # Remote → remote drop: same tree — treat as a no-op rather
            # than a self-copy (a move/rename gesture is out of scope).
            return DropAction("none", reason="already on the remote side")
        return DropAction("download", tuple(names), source_dir=remote_dir, dest_dir=target_dir)
    if has_local_mime:
        local_dir, names = decode_local_payload(local_payload)
        if not names:
            return DropAction("none", reason="no local files in drag")
        if not target_is_remote:
            if _same_dir(local_dir, target_dir):
                return DropAction("none", reason="already in this folder")
            return DropAction("copy_local", tuple(names), source_dir=local_dir, dest_dir=target_dir)
        return DropAction("upload", tuple(names), source_dir=local_dir, dest_dir=target_dir)
    paths = urls_to_local_paths(urls or [])
    if paths:
        if target_is_remote:
            # Full local paths: the dialog groups them by parent directory
            # and uploads each group in one operation.
            return DropAction(
                "upload",
                tuple(paths),
                source_dir="",
                dest_dir=target_dir,
                reason="os-drop",
            )
        # OS → local pane: copy into the viewed folder, or navigate when a
        # single directory was dropped.
        if len(paths) == 1 and Path(paths[0]).is_dir():
            return DropAction("navigate", (), source_dir="", dest_dir=paths[0])
        return DropAction("copy_local", tuple(paths), source_dir="", dest_dir=target_dir)
    return DropAction("none", reason="unsupported drop content")


def _same_dir(a: str, b: str) -> bool:
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except OSError:
        return a == b


def copy_local_files(names: tuple[str, ...], source_dir: str, dest_dir: str) -> tuple[int, str]:
    """Copy local files (or absolute paths) into ``dest_dir``.

    Returns ``(copied_count, error_text)``; directories are copied
    recursively. Absolute entries in ``names`` (OS drops) are used as-is.
    """
    import shutil

    dest = Path(dest_dir).expanduser()
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return 0, str(exc)
    copied = 0
    errors: list[str] = []
    for name in names:
        src = Path(name) if Path(name).is_absolute() else (Path(source_dir).expanduser() / name)
        try:
            target = dest / src.name
            if src.resolve() == target.resolve():
                continue
            if src.is_dir():
                if target.exists():
                    errors.append(f"{src.name}: already exists")
                    continue
                shutil.copytree(src, target)
            else:
                shutil.copy2(src, target)
            copied += 1
        except OSError as exc:
            errors.append(f"{src.name}: {exc}")
    return copied, "; ".join(errors)
