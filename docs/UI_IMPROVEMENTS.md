# UI improvement plan — current trends, zero core impact

This is a prioritised, trend-aware (2025/2026) modernisation plan for KB-Remote's
workbench UI. Every item below lives in the **presentation layer** —
`src/rdpstudio/ui/theme.py` (QSS + palettes), `src/rdpstudio/ui/widgets.py`,
widget layout code in `src/rdpstudio/ui/*.py`, and resource files
(`resources/icons/*.svg`). The plan's sanctioned exceptions are a handful of
**backward-compatible** additions to `core/settings.py` (new optional fields
with defaults: `density`, `toolbar_labels`, `animations`,
`palette_recents`) and one optional per-session flag
(`session.options["pinned"]`). Session, authentication, reconnect, SFTP and
RDP behaviour stay byte-for-byte identical.

## Status — implemented 2026-08 (this round)

| § | Item | Status |
|---|---|---|
| §1 | Theme-aware icon tinting (`theme.icon(name, tint=…)` + `badge_icon`) | ✅ done |
| §1 | Icon-only toolbar mode (`Settings → UI → Toolbar labels`) | ✅ done |
| §1 | Protocol tab icons as mini-badges | ⏸ deferred (badge helper exists; tabs keep single-tone icons) |
| §1 | State icons on buttons (Stop ↔ Reconnect dual button) | ✅ done |
| §2 | Unified radius scale (4/6/8/14) | ✅ done |
| §2 | Accent gradient on `#primary` | ✅ done |
| §2 | Soft shadows (`widgets.soft_shadow` helper; palette card already had one) | ✅ helper added |
| §2 | WCAG AA contrast bumps (light/meadow/desert `fg_muted`) | ✅ done |
| §3 | Tabular figures on status chip (mono stack) | ✅ done |
| §4 | Tab max-width + `»` overflow | ✅ done |
| §4 | Sidebar collapse + 140 ms tween + persistence (`Ctrl+B`, toolbar, View) | ✅ done |
| §4 | Density mode (Comfortable/Compact) | ✅ done |
| §4 | Pinned sessions (sidebar + dashboard, pinned-first) | ✅ done |
| §5 | Motion helpers + global reduce-motion (`animate_in`, `pulse`, `MOTIONS_ENABLED`) | ✅ done |
| §5 | Shimmer progress + byte-rate captions (SFTP bottom bar) | ✅ done |
| §5 | Connection chip pulse | ✅ done |
| §6 | Focus rings on buttons/inputs/tabs/tree rows | ✅ done |
| §6 | Palette no-match empty state | ✅ done |
| §6 | Inline validation (`#invalid`, clears on fix) | ✅ done |
| §6 | Shortcuts dialog (`Help → Keyboard shortcuts…`) | ✅ done |
| §6 | High-contrast preset | ✅ done |
| §7 | All menu actions in the palette | ✅ done |
| §7 | Recents (last 8, persisted) | ✅ done |
| §7 | Fuzzy subsequence ranker (`fuzzy_score`, unit-tested) | ✅ done |
| §7 | Two-pane preview | ⏸ deferred |
| §8 | Searchable settings (group filtering) | ✅ done |
| §8 | Settings UI group (density/toolbar/animation) | ✅ done |
| §8 | Confirm before closing a tab with active logging | ✅ done |
| §9 | Tray icon (guarded, where a tray exists) | ✅ done |
| — | Double-click tab rename, dashboard logo mark, closeEvent double-prop fix | ✅ done |

Covered by `tests/test_ui_polish.py` (fuzzy ranker, tint pixels, badge,
settings coercion, contrast palette, density QSS, motion gating) plus the
existing suite (185 passed / 1 skipped) and regenerated
`docs/screenshots/`.

---

## What was fixed in this round (already done)

| Change | Where | Why |
|---|---|---|
| **Icon loader bug** | `ui/theme.py → icon()` | SVG icons are scalable, so Qt reports no `availableSizes()` for them; the old check discarded *every* valid SVG and every button rendered a drawn text glyph (`>_`, `⚙`, `▤`) — on many systems those render as tofu boxes `□`. That was the "weird and bad icons". Fix: trust a non-null SVG `QIcon` once the engine rasterises it. |
| **New icon set** | `resources/icons/*.svg` | 14 icons redrawn on a shared 24×24 grid, 2 px stroke, round caps/joins, one neutral tone (`#a6adbb`). Each action now has a distinct, meaningful glyph: network-nodes for the port scanner (was a server rack), link for Connect/Reconnect (was "refresh" arrows), power symbol for Disable (was a filled red square), monitor for RDP (was a filled MS logo), tray-out arrow for Export (was a down arrow), neutral trash (was red). |
| **Remote monitoring removed** | across the codebase | Bottom monitor strip, monitor window, `Ctrl+Shift+M`, per-tab Monitor button, the SSH `monitor` capability and the probe engine are gone (see CHANGELOG). The shared `Sparkline` widget moved to `ui/widgets.py` for the network tools dialog. |
| **Fresh screenshots** | `docs/screenshots/` | Regenerated with `scripts/dev_screenshots.py` so the README shows the real (fixed) chrome instead of the old glyph-icon builds. |

---

## 1. Icon system polish — quick wins

**Trend:** a single icon language with optical consistency (Lucide/Phosphor style)
and theme-aware tinting. The geometry is done; the remaining gaps are colour
and state.

- **Theme-aware icon tinting** (small `theme.py` change, high visual payoff).
  Currently all icons carry one baked-in gray, which is tuned for dark themes.
  Add a `tint_icon(QIcon, color)` helper that re-renders the SVG with the
  current palette's `fg_dim`/`fg`/`accent` (Qt can't recolour a loaded `QIcon`,
  but we own the SVG text: substitute the stroke colour before `QIcon(path)`).
  Then icons light up on hover states, dim when disabled, and the accent icon
  in selected rows gets the theme accent automatically.
- **Icon-only toolbar mode.** The toolbar is `TextBesideIcon` today. Add a
  `Settings → UI → Toolbar labels` toggle (pure `QToolBar.setToolButtonStyle`
  + tooltip parity). Dense 16-inch laptops will thank us; icons are now
  consistent enough to stand alone.
- **Protocol tab icons as mini-badges.** SSH/RDP/local tabs use `terminal` /
  `windows` / `console`. Consider a 2-tone treatment (accent glyph on a
  rounded `bg3` tile) so the protocol is readable at a glance — the palette
  colours already exist, it's just a `QPixmap` composition in `theme.icon()`.
- **State icons on buttons.** Disabled/connected/disconnected states can swap
  icons (`connect` → `stop` while running, `plus` → `check` after save).
  Only needs per-button `setIcon` at state-change events that already exist
  (`stateChanged`, `statusInfo`) — no new machinery.

Effort: **S** each (half a day total). No core impact.

## 2. Colour, depth and material — the "soft bento" pass

**Trend:** layered surfaces + soft shadows + one confident accent (the
"flight-ops console" look this app is aiming at, taken further).

- **Unify the radius scale.** Radii today are 3/4/5/6/8/14 px in the QSS.
  Pick a 4-step scale (4 = chips/indicators, 6 = inputs/buttons, 8 = cards/
  menus, 14 = dialogs/large cards) and sweep the QSS. Pure `theme.py` text.
- **Use the accent gradient.** `accent_gradient` is defined in every palette
  but never referenced. Apply it to the toolbar `#primary` Connect button and
  the palette's execute affordance — instant "modern product" signal, one QSS
  line each.
- **Soft shadows on floating surfaces.** `QGraphicsDropShadowEffect` is
  already used for toasts. Extend to: `QMenu` (already slightly — make it
  8–12 px blur), dialog cards, and the sidebar group headers. Keep blur ≤ 12
  and opacity ≤ 0.25 so it stays "ops console", not "iOS".
- **Contrast audit (WCAG AA).** Two palette families are close to the line:
  `fg_muted` on `bg3` in `light`/`meadow`/`desert`. Bump the three `*_muted`
  values by one step and verify with a contrast checker. Palette dict edit
  only.
- **Status colours as the only saturated pixels.** Keep the whole chrome
  neutral and let `good/warn/bad/info` carry all semantic colour (they already
  do in chips). Resist the temptation to add more accents; one per theme is
  the current trend.

Effort: **S–M** (a day, mostly QSS). No core impact.

## 3. Typography

**Trend:** one sans stack + one mono stack, tight tracking on display text,
tabular figures anywhere numbers tick.

- The stacks are already modern (`Inter/Geist/Nimbus…`, `JetBrains Mono/…`).
- **Tabular figures** in the status bar and any ticking counter:
  `QFont.setPreferableFamily` + `QFont::StyleHint` won't do it; set
  `font-feature-settings "tnum"` via `QFontEngine`/`setStyleSheet`
  (`font-variant-numeric: tabular-nums;`) on the `#statusSession` label.
  Prevents the status bar from jittering as ciphers/versions change.
- **Type scale discipline.** Consolidate the 10.5/11/11.5/12/12.5/13/16 px
  soup into: 11 (captions/uppercase labels), 12.5 (body/controls), 13
  (terminal-adjacent chrome), 16 (h1). Sweep widgets that set ad-hoc
  `setStyleSheet` font sizes to the label classes (`#caption`, `#h2`)
  already defined in QSS.
- **Letter-spacing** on the uppercase micro-labels is right (0.4–0.6 px);
  keep it, and apply the same to the tab titles if they move to all-caps.

Effort: **S**. No core impact.

## 4. Layout & information architecture

**Trend:** everything keyboard-reachable, side rails that tuck away, density
control, the command palette as the true home screen.

- **Tabs stay south (MobaXterm-style)** but get: (a) a max-width + `…`
  overflow menu so 20 tabs don't squish the chrome, (b) drag-reorder is on —
  add a drop-target highlight (`QTabBar` hover is fine; add the accent
  underline animation), (c) double-click to rename (it's only in the context
  menu today).
- **Collapsible sidebar with a smooth width tween.** `main_splitter` sizes are
  persisted via the settings geometry dict already. Add a chevron button in
  the sidebar header + a 120 ms `QPropertyAnimation` on the split width.
  When collapsed, show a slim rail of protocol icons only.
- **Density mode (Compact / Comfortable).** A settings toggle that flips one
  QSS variable block (padding 5→3 px, min-heights −2 px, font 12.5→11.5).
  Implement as two pre-built QSS suffixes in `theme.py` selected in
  `apply_theme` — zero per-widget code.
- **Pinned sessions on the dashboard.** The welcome screen lists the 5 most
  recent; add a `⭐ pin` per session row (pinned first, then recents). The
  `Session` model already carries `group`; pinning is a one-field settings
  list — but note: this one does touch `core/models.py` (new optional field),
  so treat it as a small core-adjacent change, or implement purely in the
  `SessionTree` ordering if you want to stay strictly out of core.
- **Per-tab header density.** The tab header row (chip · info · Files
  button) is 36 px; in Compact mode let it shrink to 28 px and hide the
  info label behind a tooltip.

Effort: **M** (2–3 days). The pin feature is the only one that brushes
`core/`; everything else is layout/QSS.

## 5. Motion & feedback

**Trend:** 100–200 ms, ease-out, *always* interruptible, and a global
reduce-motion switch.

- **Panels and menus:** animate the SFTP dialog, vault and settings on
  appear (scale 0.98→1 + fade 120 ms) using the `QPropertyAnimation`
  pattern the toast already uses.
- **Progress:** SFTP and key-gen progress bars should shimmer (a moving
  gradient `chunk` via QSS animation is not possible in pure QSS — use a
  `QTimer` + `QLinearGradient` brush update; keep it in `widgets.py`).
  Add byte-rate captions (`format_bytes` already exists).
- **Connection choreography:** when `stateChanged` fires CONNECTING →
  CONNECTED, pulse the state chip once (alpha 1→0.6→1, 300 ms). It reuses the
  existing signal; no new plumbing.
- **Reduce motion:** honour `QT_ACCESSIBILITY` / a `Settings → UI →
  Animations` toggle that sets a global multiplier to 0 in one place
  (`widgets.py: animate(...)`) so every animation call respects it.

Effort: **M**. No core impact.

## 6. States, affordances & accessibility

**Trend (2026):** accessibility is a headline feature, not a footnote.
The current QSS has one real gap to close.

- **Focus visibility.** The global QSS sets `outline: none` on `*`, which
  removes the keyboard focus ring everywhere. Add a `:focus` style with a
  1 px accent outline (offset 1 px) for `QPushButton`, `QToolButton`,
  `QLineEdit`, `QTabBar::tab`, `QTreeView::item`. This is the single highest
  value a11y fix available.
- **Empty states everywhere.** The `EmptyState` widget exists but is only
  used for the dashboard. Apply to: SFTP browser on connect failure, palette
  with no matches, key utility before a key is generated, network tools
  before a scan.
- **Inline validation in the session editor.** Host/username errors should
  turn the input border `bad` + 11 px helper text below the field (the QSS
  for `:disabled`/`focus` exists; add an `#invalid` object name). Validates
  on blur, not on Save.
- **Tooltip parity.** Every icon-only button (toolbar, tab corner `+`,
  palette rows) must carry a tooltip *and* an accessible name
  (`setAccessibleName`) — cheap, and it's what screen readers see.
- **Shortcuts dialog (Help → Keyboard shortcuts).** Generate the list from
  the existing `QAction`s (walk the menu bar) — no duplication, and it's
  the kind of "power-tool self-documentation" users of MobaXterm expect.
- **Minimum target size.** A few 22 px controls (tab corner `+`, header
  buttons at 26 px) are below the 24–28 px comfort zone; nudge paddings up in
  the QSS only (hit area grows without visual change).
- **High-contrast preset.** Add one `contrast` palette (pure `#000`/`#fff` +
  2 px accent focus) behind the existing theme picker — 20 minutes of dict
  copy-paste.

Effort: **M** spread over a week. No core impact (shortcuts dialog reads
existing `QAction`s).

## 7. Command palette as the centrepiece

**Trend:** the palette is the home screen (Raycast/Linear/VS Code pattern).
KB-Remote already has the best foundation in this list.

- **Add every menu action to the palette** (generate items from the menu
  bar in `_build_items` — ~30 lines) so the palette becomes a true
  full-command surface: "Tools → RDP server manager", "File → Export…",
  theme switches, etc.
- **Recents.** Remember the last 8 executed palette commands in settings
  and show them first when the query is empty.
- **Fuzzy → ranked.** The current substring filter is fine; a cheap
  subsequence+bonus-score ranker in `command_palette.py` (pure function,
  unit-testable) gets you "sftp" → "Browse Files (SFTP)" without external
  deps.
- **Two-pane preview.** With the palette wide enough, show a right-hand
  pane: session target/protocol for connect items, shortcut for actions.
  The item data already has `subtitle` + `shortcut`.

Effort: **M** (mostly `command_palette.py`). No core impact (recents
persist in the existing settings store — a new key, same file).

## 8. Settings & dialogs UX

- **Searchable settings.** One `QLineEdit` at the top that filters
  group-boxes by label (the settings dialog is a group-box stack; hide
  non-matching rows). 30 lines, huge UX win once there are 5+ categories.
- **Live preview card.** Settings already previews fonts; extend the same
  pattern to theme (a mini workbench swatch: button + chip + tab) and to
  density/animation toggles so changes are visible without reopening things.
- **Consistent dialog chrome.** All dialogs should share the ModernCard
  header pattern (title + caption + close) — several currently use the bare
  `QDialog` + title bar.
- **Confirmation dialogs** for destructive acts (session delete exists; add
  for "Close all tabs" when 2+ tabs are open, and for `Ctrl+W` on a tab
  with active logging — the `● REC` chip already tells the user logging is
  on).

Effort: **S–M**. No core impact.

## 9. Platform polish

- **Per-OS frame behaviour:** on Windows, `mstsc`/FreeRDP external windows
  already live outside; keep the app chrome native-menu on Windows
  (`QMenuBar` is fine) and consider `Qt::AA_DontShowIconsInMenus` off so
  the new icons also appear in menus on macOS.
- **Tray icon** (logo tile) with "Show window / Close all sessions" menu —
  optional extra; keep the existing single-instance behaviour.
- **DPI:** the SVG icon set is resolution-independent; verify 200 % scaling
  on a HiDPI display once (Qt handles it; icons are the usual failure point
  — they're now vector, so this should pass for free).
- **Wayland:** no change needed; the XWayland restart for built-in RDP is
  orthogonal to UI.

Effort: **S** (tray) / validation only. No core impact.

## 10. What we deliberately do NOT do

- **Frameless windows / custom title bars.** Tempting for the "one
  continuous surface" look, but it breaks native window management,
  multi-monitor snapping and a11y tooling. The current native frame + dark
  menubar is the 2026-correct call for an ops tool.
- **In-app RDP renderer.** Out of scope (see ARCHITECTURE roadmap) — and
  unrelated to UI polish.
- **Changing tab position to the top.** The south-docked tab strip is a
  deliberate MobaXterm-style choice that keeps the terminal maximally tall;
  keep it, polish it.
- **Multi-monitor dashboards / GPU-accelerated widgets.** Overkill for the
  workload; Qt's default compositor is fine.

---

## Suggested order of attack

| # | Item | Effort | Impact |
|---|---|---|---|
| 1 | Focus-ring QSS fix (§6) | S | a11y, very visible |
| 2 | Theme-aware icon tinting + accent gradient on primary buttons (§1, §2) | S | immediate "wow" |
| 3 | Radius/contrast/type-scale sweep (§2, §3) | S–M | cohesion |
| 4 | Palette: all menu actions + recents + ranking (§7) | M | keyboard-first story |
| 5 | Motion pass + reduce-motion toggle (§5) | M | feel |
| 6 | Sidebar collapse + density mode (§4) | M | productivity |
| 7 | Empty states + inline validation + shortcuts dialog (§6, §8) | M | robustness perception |
| 8 | Searchable settings + live preview (§8) | S–M | settings usability |

Each row is independently shippable; none requires touching
`src/rdpstudio/core/` or `src/rdpstudio/protocols/` (the session-delete
"pinning" and palette "recents" persist through the existing settings
store — new keys, old file).
