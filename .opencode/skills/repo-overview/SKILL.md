---
name: repo-overview
description: Give a token-efficient tiered overview of any local repo (structure, deps, entry points) without dumping file bodies.
license: MIT
compatibility: opencode
metadata:
  audience: engineers
  workflow: codebase-discovery
---

# Repo overview (token-efficient)

Give a detailed overview of a repo WITHOUT wasting tokens. Never dump full
files. Work in tiers and stop at the cheapest tier that answers the question.

## 0. Resolve target (any repo, not just cwd)

1. Target = user-supplied path, else cwd.
2. If target has no `.git`, run `git rev-parse --show-toplevel` from cwd and
   use that as root. Report the resolved `root` first.
3. All paths in output are relative to root.

## 1. Tiers — always start at L1, escalate only on request

- **L1 quick (~1-2k tokens):** git snapshot + depth-2 tree + file counts by
  extension + total LOC + first ~40 lines of manifests
  (`README.md`, `AGENTS.md`, `pyproject.toml`/`package.json`/`Cargo.toml`/
  `go.mod`, `Makefile`). End with "want L2?".
- **L2 standard (~4-6k):** L1 + entry points (`[project.scripts]`, `bin/`,
  `Makefile` targets), module map (top-level `def`/`class` names only, no
  bodies), `tests/` + `.github/workflows/` + `docs/` listing.
- **L3 deep (paged):** one directory at a time, per-file first ~15 lines only,
  max ~40 files. Ask which directory before starting L3.

## 2. Tool discipline (this is how tokens are saved)

- Prefer: `python scripts/repo_overview.py <root> --level <tier>` (stdlib
  only, output already capped). Fall back to manual steps below if the script
  is absent (e.g. foreign repo).
- Manual fallback — use counts and names, never bodies:
  - `git log -5 --format='%h %ad %s' --date=short && git status --short --branch`
  - `glob` for layout (cap depth 2-3, skip `.git __pycache__ .venv node_modules
    dist build target coverage`); `grep` for `^(def|class|func|fn|export)` with
    `include` filters instead of reading files.
  - `read` ONLY with `limit` (≤60) and `offset`; truncate observations to
    160 cols. Never `read` a full file >200 lines.
  - Count LOC with `rg --files | head -c` style walks or `wc -l` on filtered
    lists, not by opening files.
- FORBIDDEN for overviews: full-file reads, `cat`, recursive dumps, pasting
  lockfiles, `node_modules`/build output, screenshots.

## 3. Output template (L1/L2)

```md
# <repo> — L<n> overview
Root: `<path>` | branch/commit | remote
Layout: <depth-capped tree code block>
Inventory: ~N files, ~LOC text lines; top extensions table
Manifests: README/AGENTS/build-file highlights (bullets, not quotes)
Entry points (L2+): binaries, scripts, Makefile targets
Module map (L2+): `path` — symbols (names only)
Tests/CI: paths only
Suggested L3 slices: <dir1>, <dir2>
```

Keep bullets terse. Quote at most 5 lines from any one file.

## 4. This repo (KB-Remote) appendix — apply when root is RDP

- Source in `src/rdpstudio` (`app.py`, `core/`, `protocols/`, `ui/`, `tools/`).
- Entry points: `kb-remote = rdpstudio.app:main` (see `pyproject.toml`).
- Quirks: `pyside6_qtermwidget.sendData` can't marshal — keyboard goes via
  event-filter shim in `src/rdpstudio/ui/native_terminal.py`. Editable install;
  after `src/` edits reinstall + offscreen test per `AGENTS.md`.
- Don't launch the GUI for an overview; use
  `QT_QPA_PLATFORM=offscreen` only if a smoke test is explicitly requested.
