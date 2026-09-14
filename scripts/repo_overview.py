#!/usr/bin/env python3
"""Token-efficient repo overview: tiered summary without dumping file contents.

Usage:
    python scripts/repo_overview.py [PATH] [--level quick|standard|deep]
    python scripts/repo_overview.py . --level quick
    python scripts/repo_overview.py /path/to/repo --level standard > overview.md

Levels (token budgets are approximate, output is line-capped):
    quick    ~1-2k tokens: layout, counts, LOC, manifests, git snapshot
    standard ~4-6k tokens: + entry points, module map, test/CI layout
    deep     paged per-file headers: + first N lines of up to M key files

Never prints full file bodies. Everything is truncated by design.
Stdlib only so it runs anywhere.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import subprocess
from collections import Counter
from pathlib import Path

SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "node_modules", "dist", "build",
    ".hg", ".svn", "target", ".idea", ".vscode", "coverage", ".coverage",
}

MANIFESTS = [
    "AGENTS.md", "README.md", "pyproject.toml", "package.json", "Cargo.toml",
    "go.mod", "requirements.txt", "requirements-dev.txt", "Makefile",
    "CMakeLists.txt", "Dockerfile", "compose.yaml", "docker-compose.yml",
]

LEVEL_BUDGETS = {
    "quick": {"tree_depth": 2, "tree_max": 80, "manifest_lines": 40, "key_files": 0},
    "standard": {"tree_depth": 3, "tree_max": 150, "manifest_lines": 60, "key_files": 0},
    "deep": {"tree_depth": 3, "tree_max": 200, "manifest_lines": 60, "key_files": 40},
}


def run(cmd: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=10)
        return (out.stdout or "").strip()
    except Exception:
        return ""


def git_snapshot(root: Path) -> dict[str, str]:
    if not (root / ".git").exists():
        return {"repo": "not a git repo"}
    return {
        "toplevel": run(["git", "rev-parse", "--show-toplevel"], root) or str(root),
        "branch": run(["git", "branch", "--show-current"], root),
        "commit": run(["git", "log", "-1", "--format=%h %ad %s", "--date=short"], root),
        "remote": run(["git", "remote", "get-url", "origin"], root),
        "status": run(["git", "status", "--short", "--branch"], root),
        "recent": run(["git", "log", "-5", "--format=%h %ad %s", "--date=short"], root),
    }


def iter_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".git"))
        dirnames.sort()
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            try:
                if p.is_symlink():
                    continue
            except OSError:
                continue
            yield p


def tree(root: Path, max_depth: int, max_entries: int) -> list[str]:
    lines: list[str] = [f"{root.name}/"]
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        rel = Path(dirpath).relative_to(root)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth > max_depth:
            dirnames[:] = []
            continue
        indent = "  " * depth
        if depth > 0:
            lines.append(f"{'  ' * (depth - 1)}+ {Path(dirpath).name}/")
            count += 1
        for fn in sorted(filenames)[:30]:
            if count >= max_entries:
                lines.append("... (capped: use --level deep or raise caps for more)")
                return lines
            lines.append(f"{indent}  - {fn}")
            count += 1
        if count >= max_entries:
            lines.append("... (capped)")
            return lines
    lines.append(f"({count} entries shown, capped at {max_entries})")
    return lines


def inventory(root: Path) -> tuple[Counter, int, int]:
    by_ext: Counter = Counter()
    total_loc = 0
    n_files = 0
    for p in iter_files(root):
        try:
            if p.stat().st_size > 1_000_000:
                by_ext["<large-skipped>"] += 1
                continue
        except OSError:
            continue
        ext = p.suffix.lower() or "<noext>"
        if len(ext) > 12:
            ext = "<longext>"
        by_ext[ext] += 1
        n_files += 1
        if n_files > 5000:
            break
        if ext in {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".c", ".h",
                   ".cpp", ".java", ".rb", ".sh", ".toml", ".yaml", ".yml", ".json", ".md"}:
            try:
                with p.open("rb") as f:
                    total_loc += sum(1 for _ in f)
            except OSError:
                pass
    return by_ext, total_loc, n_files


def head(path: Path, n: int) -> list[str]:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            return [line.rstrip()[:160] for _, line in zip(range(n), f, strict=False)]
    except OSError:
        return ["<unreadable>"]


def py_surface(path: Path, cap: int = 20) -> list[str]:
    """Top-level defs/classes of one python file via AST (no body dump)."""
    try:
        tree_ = ast.parse(path.read_bytes(), filename=str(path))
    except Exception:
        return []
    out = []
    for node in tree_.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            out.append(f"{kind} {node.name}")
        elif isinstance(node, ast.Assign):
            targets = ", ".join(t.id for t in node.targets if isinstance(t, ast.Name))[:60]
            if targets:
                out.append(f"var {targets}")
        if len(out) >= cap:
            break
    return out


def module_map(root: Path, cap_dirs: int = 20, cap_syms: int = 12) -> list[str]:
    lines: list[str] = []
    py_files = [p for p in iter_files(root) if p.suffix == ".py"]
    # Prefer shallow, non-test files as "key modules".
    key = sorted(py_files, key=lambda p: (len(p.relative_to(root).parts), "test" in p.name.lower()))[:cap_dirs]
    for p in key:
        rel = p.relative_to(root)
        syms = py_surface(p, cap_syms)
        sig = f" ({', '.join(syms[:cap_syms])})" if syms else ""
        lines.append(f"- `{rel}`{sig}")
    lines.append(f"({len(py_files)} python files total; showing {len(key)})")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", nargs="?", default=".", help="Repo path (default: cwd)")
    ap.add_argument("--level", choices=["quick", "standard", "deep"], default="quick")
    ap.add_argument("--manifest-lines", type=int, default=None)
    ap.add_argument("--tree-depth", type=int, default=None)
    ap.add_argument("--exclude", action="append", default=[], help="Glob to exclude (repeatable)")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"error: no such path: {root}")
        return 2
    if (root / ".git").exists() or args.path != ".":
        pass
    else:
        toplevel = run(["git", "rev-parse", "--show-toplevel"], Path.cwd())
        if toplevel:
            root = Path(toplevel)

    budget = LEVEL_BUDGETS[args.level]
    tree_depth = args.tree_depth or budget["tree_depth"]
    manifest_lines = args.manifest_lines or budget["manifest_lines"]

    print(f"# Repo overview: {root.name} (`{args.level}`)")
    print(f"Path: `{root}`")
    print()
    print("## Git snapshot")
    for k, v in git_snapshot(root).items():
        if not v:
            continue
        print(f"- **{k}**:")
        for line in str(v).splitlines()[:8]:
            print(f"    {line[:180]}")
    print()
    print(f"## Layout (depth {tree_depth}, capped)")
    print("```")
    print("\n".join(tree(root, tree_depth, budget["tree_max"])))
    print("```")
    print()
    by_ext, total_loc, n_files = inventory(root)
    print("## Inventory (filenames only, no contents)")
    print(f"- files walked: ~{n_files} | text LOC (capped walk): ~{total_loc}")
    print("- by extension:")
    for ext, n in by_ext.most_common(20):
        print(f"  - `{ext}`: {n}")
    print()
    print(f"## Manifests (first {manifest_lines} lines each, truncated to 160 cols)")
    found_any = False
    for name in MANIFESTS:
        p = root / name
        if fnmatch.fnmatch(name, "*") and p.is_file():
            if any(fnmatch.fnmatch(str(p.relative_to(root)), pat) for pat in args.exclude):
                continue
            found_any = True
            print(f"\n### {name}")
            print("```")
            print("\n".join(head(p, manifest_lines)))
            print("```")
    if not found_any:
        print("(no known manifest files at top level)")
    print()

    if args.level in ("standard", "deep"):
        print("## Module map (signatures only, no bodies)")
        print("\n".join(module_map(root)))
        print()
        print("## Tests / CI (paths only)")
        for _label, pat in [("tests", "tests"), ("workflows", ".github/workflows"), ("docs", "docs")]:
            d = root / pat
            if d.is_dir():
                kids = sorted(x.name for x in d.iterdir())[:30]
                print(f"- `{pat}/`: {', '.join(kids) if kids else '(empty)'}")
            else:
                print(f"- `{pat}/`: —")
        print()

    if args.level == "deep":
        print(f"## Key file headers (first 15 lines, up to {budget['key_files']} files)")
        shown = 0
        for p in iter_files(root):
            if shown >= budget["key_files"]:
                break
            rel = p.relative_to(root)
            if p.suffix not in {".py", ".md", ".toml", ".cfg", ".ini", ".yaml", ".yml"}:
                continue
            if "test" in p.name.lower() and shown > 10:
                continue
            print(f"\n### `{rel}`")
            print("```")
            print("\n".join(head(p, 15)))
            print("```")
            shown += 1
        print(f"\n({shown} headers shown; full bodies deliberately omitted)")

    print("\n---\n*Generated without dumping file bodies. For a deeper dive, ask for one directory at a time.*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
