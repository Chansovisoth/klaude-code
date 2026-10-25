# Klaude Expressive validation — 2026-10-22

This is an integrated frontend redesign of the existing browser surface, using
the current dirty worktree as its baseline. It is not an assertion of full
CLI/TUI feature parity or a backend rewrite. Reference commit, component mapping,
licenses and deliberate web adaptations are in `klaude-expressive-reference.md`.

## Expressive segmented corners — 2026-10-22

The shared controls restore the end-4 selection pattern: an unselected first
segment has rounded outer-left corners, middle segments have small corners,
and the last segment has rounded outer-right corners. Selected segments are
pills regardless of position. This supersedes the earlier uniform-12px change.
Existing theme tokens provide 23px external corners and 9px inner corners;
5px gaps, tonal colors, focus rings, native radio semantics, ripple/state layers
and scale press feedback remain. Shape transitions use the shared 350ms fast
spatial curve and honor both app and system reduced motion.

`expressive.js` marks each rendered row's visible start/end through a shared
layout observer. Row markers are independent of selection, so selecting a middle
segment cannot remove an unselected end's external rounding. Single-item rows
receive both external ends. Markers update on viewport/container/item resize,
visibility/content changes and font readiness, with read/write work batched in
one animation frame. Removed groups release their resize observations. There is
no continuous animation or measurement loop. Selected corner targets use actual
half-height, rather than interpolating toward a visually clamped 9999px radius.

Focused isolated HTTP/Chrome verification passed:

- Computed corners and row markers for all visible shared controls in idle,
  hover, hover+active and focus-visible states (41 visible controls in the initial
  Agent fixture). Hidden panels are checked when opened.
- All seven selection positions in dynamically added, multi-row button and radio
  groups; container-only resizing at 125/235/440px; single visible items; hidden,
  restored and removed neighbors; RTL and LTR; removed groups.
- Nine palette variants in light/dark at 320, 390, 850 and 1440px (72 cases).
  Phone variants wrap into three/four rows without page or group overflow.
- A measured selection transition from 9px through approximately 18.6px at 60ms
  to the final 22px half-height. System reduced motion settles immediately.
- Native permission-radio keyboard selection and Discard; Inspector arrow-key
  selection; visible full/Context Library groups. No browser exceptions.
- Eleven screenshots, with Theme, Tools & Permissions and Inspector desktop/phone
  captures visually inspected for geometry, selection, spacing and wrapping.
- The existing `scripts/webui_settings_save_smoke.py` passed native policies,
  staged Save/Discard, conflicts, security confirmation, uncertain saves,
  responsive action bars and sign-out checks, with zero browser errors.
- Both deterministic bundle checks, JavaScript syntax checks and
  `git diff --check` passed.

Measurements/captures: `/tmp/klaude-segmented-corners-validation/`. The temporary
`/tmp/klaude_segmented_corners_check.py` uses the existing isolated Expressive
fixture, never a user profile or a model/provider. Historical full-overhaul
results below are separate; this refinement did not rerun the full repository
suite. No commit, push or live-host restart was performed.

## Implemented surfaces

Content-row flicker follow-up: shared inventory corners and full-row actions now
keep stable geometry across hover/focus/press; segmented tab morphs remain.
Current reproduction, focused browser evidence and limits are recorded in
`collection-shapes-validation.md`.

- Shared Material semantic color roles, sixteen retained presets, nine palette
  variants, light/dark/system, local custom/image accents, bounded surface
  transparency, source-measured corner/motion tokens, connected controls, native
  switches/radios/ranges/fields, contextual tooltips, dialogs/popovers and shapes.
- Shell/navigation/conversation drawer, chat/composer, Markdown/code actions,
  attachment/status surfaces, Context Panel, full/Context Library, Models,
  Integrations, Settings Account/Theme/Agent/Models/Memory, session/review dialogs,
  Activity and existing empty/error/loading states share the same system.
- The Context Panel starts closed. Its existing public inspector and exact
  Library attachment identity/drop pipeline remain. Rows open Preview; attachment
  uses drag-to-chat or the composer's Library picker. Context Library retains
  Current/All; the full Library's Uploads and Generated span conversations without
  scope controls. Legacy main-Library scope preferences/URLs no longer filter its
  inventories or hide section counts.
- Workspace rows/breadcrumbs navigate the existing bounded filesystem reader.
  Source previews reuse the existing safe token highlighter and clipboard path.
  Diff colors derive from actual prefixes. No workspace security rule changed.
- Searchable command and shortcut dialogs call existing navigation/model/session
  actions. Unresumable sessions and unavailable mutations are omitted. Platform
  shortcuts use Ctrl or Cmd; input composition and active dialogs are respected.
- Loading uses the source-measured end-4 rotation/leap/zoom cadence with existing
  Apache-licensed matched cubic shapes. A shared scheduler pauses hidden or
  reduced-motion indicators and releases removed nodes. Held paths avoid repeated
  geometry work; classic spinner remains selectable.

## Deterministic checks

- **48 passed**: `tests/unit/test_webhost.py` and `tests/unit/test_web_accounts.py`.
  Includes fixed asset boundaries, CSP/no-sniff, authentication/CSRF/Origin,
  authorization, fenced operations and vendor source/hash/license checks. The
  final asset case is also run after bundle regeneration.
- `node --test scripts/webui_settings_drafts.test.cjs` passed.
- Repository `ruff check .`, JavaScript syntax checks for changed controllers and
  components, Python compilation, both bundle `--check` commands and
  `git diff --check` passed.
- `vendor_webui_loading.py --cache /tmp/klaude-official-loading --check` verified
  deterministic geometry regeneration from pinned Google/AndroidX source hashes.
- Seven workspace wheels built/installed in a disposable environment; imports,
  bundled components/fonts/vendor licenses and both installed CLI help commands
  passed `scripts/package_smoke.py`. No runtime npm dependency was added.

## Real browser acceptance

`scripts/webui_expressive_smoke.py` starts a real temporary authenticated HTTP
host and disposable Chrome profile. It never contacts a model/provider or reads
the user's profile. All visible example conversation text, images and files in
these captures are explicitly fixture content.

Evidence directory: `/tmp/klaude-expressive-validation/`.

- **88 page/theme/viewport cases**, light and dark at **320, 390, 850 and 1440px**.
  Every Settings category, chat, Library, Workspaces, Integrations, Models and
  Activity fits its scroll container and page width. **54 screenshots** include
  desktop/phone pages, Context Panel, native file preview and shortcuts.
- Token contrast across **16 presets × 9 variants × 2 modes**, nine primary/
  container/surface/error text-role pairs each. Minimum measured contrast:
  **4.5129:1**, no failing pairs. This tests those semantic pairs, not all possible
  custom image colors or a complete visual-accessibility certification.
- Real Theme input/preview/Discard/Apply/local storage, local image decoding and
  quantization, image-seed-only persistence; measured switch track dimensions.
- Full Library inventory/counts, image-only Gallery, spatial keyboard navigation
  and authenticated preview. Context Library Current/All returns the actual
  conversation-linked/full inventories and keeps its independently validated
  exact-ID attachment pipeline.
- Real workspace directory/file navigation, highlighted preview, retained rows on
  a failed directory refresh, preserved file preview on returning to Workspaces
  and rejected out-of-workspace read.
  Commands support search, Enter execution, Escape dismissal and focus return;
  shortcut search returns only matching actual shortcuts.
- In-between loader geometry moves; reduced motion retains the same path. Nine
  official named static shapes are present. Browser exception capture stays empty.
- Optional **axe-core 4.11.1** maintenance-only scans cover the command/shortcuts
  modal and eleven visible desktop page/category surfaces using WCAG 2 A/AA,
  WCAG 2.1 AA and WCAG 2.2 AA rules. Modal scans inspect the active dialog after
  entrance motion settles, excluding its deliberately dimmed inert background.
  The report is `accessibility.json`; zero violations on the checked surfaces.

Reproduce with the local environment and optional temporary axe installation:

```sh
.venv/bin/python scripts/webui_expressive_smoke.py
KLAUDE_AXE_SOURCE=/tmp/klaude-material-build/node_modules/axe-core/axe.min.js \
  .venv/bin/python scripts/webui_expressive_smoke.py
```

The browser helper discovers the existing cached Chrome or accepts
`KLAUDE_TEST_CHROME`. No live application restart or user-session mutation was
used for acceptance.

## Focused regression scripts

The following isolated Chrome/HTTP scripts passed. Logs are in
`/tmp/klaude-expressive-validation/regressions/`. Initial failures and corrected
reruns remain recorded; a first failed run is not treated as a pass.

| Script | Coverage |
| --- | --- |
| `webui_settings_smoke.py` | Categories/history, two account modes, drafts, density, responsive forms and native permission choices |
| `webui_settings_save_smoke.py` | Native policy keys, staged writes, Discard, exact security confirmation, conflicts and uncertain-save behavior |
| `webui_context_panel_smoke.py` | Real tool/approval/cancel/failure events, SSE/replay/resume, isolation, exact Library IDs, drag/composer picker, 24 responsive layouts |
| `webui_material_loading_smoke.py` | 800ms cadence, 90°/350ms leaps, zoom, seven shapes, stable operation identity, hidden/reduced lifecycle and cleanup; no recorded >50ms tasks in the isolated run |
| `webui_composer_smoke.py` | Enter/touch/IME, send and failed-send drafts, inline status, legacy asset fallback |
| `webui_markdown_smoke.py` | Real shared-worker streaming, code block identity, selection/copy, Markdown and message actions |
| `webui_drop_smoke.py` | Draft-only device/Library drops, limits, stale/session/logout rejection and reviewed import |
| `webui_library_browser_smoke.py` | 1058-item/50-image inventory, paged views/navigation, corrupt fallback, import/tag/review/history and text preview |
| `webui_models_smoke.py` | Provider/legacy catalogs, pagination/filtering, exact runtime changes and compatibility failure retention |
| `webui_dialogs_smoke.py` | Native dynamic/static dialogs, pointer/touch inside/backdrop/drag behavior and focus |
| `webui_loading_smoke.py` | Owned delayed reads, retained content, stale/cancelled responses and sign-out |
| `webui_startup_smoke.py` | First-paint saved themes, inert shell, readiness/failure/reload, reduced motion and corrupt/blocked storage |
| `webui_control_smoke.py` | Multi-tab/terminal handoff, fenced mutations and passive observer behavior |

Failures corrected during refinement included the existing early-startup asset
test mismatch, source-requested Theme/Automatic labels, new accessible Attach
expectations, a shared gallery corner/gap mismatch, premature keyboard focus
before startup readiness, modal geometry sampled during entrance, and a delegated
keyboard handler receiving a non-Element target, a file preview being re-opened
as a directory on page return, and a legacy 150ms path-write expectation that
conflicted with held-shape optimization under the 800ms cadence. The tests now wait for the
relevant UI state rather than removing assertions about the underlying behavior.

## Visual comparison and limits

Inspected the published end-4 Settings/AI screenshot beside the live generated
desktop and phone captures. The comparison informed connected choice geometry,
tonal layer contrast, the original selected pills, compact sidebar/content hierarchy and
wrapping palette choices. Verified the 56×32 rail highlight, 39×24 switch track,
6/12/17/23/30 corner hierarchy and the loader's exact source timing separately.
The source QML compositor is not run here; no claim of pixel/frame identity.

The loader geometry is the already-pinned official Google version rather than a
copy of the end-4 shape implementation. Selection groups now use the user's
expressive row ends and selected pills described above and preserve stable widths; there is
no neighbor-width bounce for dense forms. Arbitrary shape morphing,
wallpaper persistence, Linux transparency behavior and delayed dialog exits are
explicitly adapted as described in the reference document.

This is not a full repository unit-suite run, physical iOS/Android/Safari test,
screen-reader acceptance test or low-end-device performance benchmark. Some
browser operations remain unavailable because their public backend contracts do
not exist; the redesign does not expose invented capabilities or relax those
boundaries. Existing review/security enforcement and unrelated dirty work were
preserved. No commit or push was performed.
