# Context Panel and Agent Inspector

Implemented 2026-10-22. The right sidebar now has **Agent Inspector** and
**Library** tabs. The main Activity destination and chat approval controls remain
available. No dependencies, new static routes, settings redesign or security
permission modes were added.

Connection status appears in the navbar; the duplicate Inspector footer and
its status update/style rules have been removed.

## Execution data and privacy

`klaude_application.inspection` projects the existing `application.public.v1`
session journal within the session snapshot transaction. It reads up to 320 recent
non-delta events, preserving event IDs, turn/execution/interaction IDs, recorded
timestamps and actual outcomes. The current task's tool count uses distinct
requested execution IDs across its available journal, independently of the
320-event display window. A missing admission event marks a pruned/legacy count
unavailable. The existing activity projection remains authoritative for lifecycle.

The shared headless and terminal event adapters publish only allowlisted
inspection metadata. A workspace path must pass the existing jail and sensitive
filename checks. A file change requires a native workspace method, successful
executed result and `metadata.edit.changed=true`. An external tool with the same
name cannot claim an edit. Public data includes bounded line counts and known
error class names, never raw arguments, result bodies, patches, shell commands,
environment variables, private model content or credentials.

Activity combines requested/started/finished events into one expandable tool row
using the turn and execution IDs. Stable event IDs remove replay duplicates;
recorded order handles reordered snapshots. Native details elements preserve
expansion across refresh. Its disclosure chevrons share Settings' 16px filled,
rounded styling and rotation timing, using the existing common SVG path.
Expanded rows show available safe path, execution
outcome, timestamp, duration, line counts and error class. They explicitly explain
that raw tool bodies are private. DOM text APIs render names and paths safely;
payload signatures stay in a WeakMap, outside DOM attributes.

The task summary remains above the three subtabs. Details shows the actual active
model/backend and configured connection when present, mode, effort, plan-mode
setting, session identity and recorded timing. Explicit plan progress, tokens and
subagent diagnostics have no supported public contract here and remain
unavailable. Incomplete and interrupted lifecycle values remain distinct.

Changes lists verified edits from available session history. **Inspect** uses the
existing authorized workspace file reader. **Current workspace diff** opens the
existing bounded, redacted diff reader. Its copy explains that this includes
uncommitted changes from other sources; native auto-committed edits can have no
remaining diff. Generated Library artifacts are never treated as workspace edits.

Approval outcomes come from the existing broker. The notice in the panel points
to the original chat controls; it creates no independent decision state. Closing
the panel does not hide or resolve chat approvals.

## Context Library

The existing Library items endpoint accepts additive `scope=current|all` filters.
The visible labels are **Current** and **All**, with no repeated scope
description. The navbar toggle controls panel visibility; there is no second
close button in the panel. The scope tabs equally fill their entire row; search,
view controls share the compact row below, without a refresh button.
This layout passes the existing 24 light/dark responsive browser cases, including
320px-wide screens and keyboard navigation; result:
`/tmp/klaude-context-full-width-tabs.log`.
The host supplies its selected session; a caller cannot choose another session ID.
Current includes stored artifact session ownership, original Library IDs in up to
500 recent public attachment records (508 distinct saved references), and up to
four current selections. Counts, search, image filtering, sorting and pagination
apply after this scope. Bounded reference scans are disclosed with an All-scope
fallback. Legacy descriptors without an original ID cannot establish a historical
association; private `model_content` is never scanned to infer one.

An optional opaque `artifact_id` in public Library attachment descriptors keeps
this association through saves/forks. It exposes no checksum, origin path, source
bytes or private prompt. Existing device descriptors retain their shape.

List, Grid and Gallery preferences and scope are stored independently of the
main Library page. Gallery filters images before paging and now shares its file
tile renderer and Gallery styles with the main Library: three columns within
the narrow panel, square cropped thumbnails, 8px gaps, rounded corners, filename
overlays on hover/keyboard focus and month headings. Month headings omit the
main page's Uploads/Generated subtitle because this panel can contain both.
Rows and tiles show only their Preview action, without per-file Attach buttons. Search is
debounced; reads have abort, authentication, generation, session and scope checks. Failed
reads can be retried by selecting the Library tab again. Sign-out clears search,
inventory and Inspector data.

Previews and lazy authenticated thumbnails reuse existing Library components.
Context previews restore focus to the originating row and do not navigate the
main Library gallery. A short-phone toolbar leaves room for scrollable files.
List file icons use a 38px tile and 22px glyph to fit the 38×42px thumbnail well.
The previous 48px tile overflowed that well, shifting its center 5px right and
3px down. Real-browser bounds now show no clipping and at most 0.01px center
offset for the icon tiles and glyphs across light/dark List and Grid layouts at
1440/768/390/320px. Gallery and page/panel overflow checks also pass: 24 layouts,
no console errors. Measurements: `/tmp/klaude-context-icon-alignment.log`;
screenshots: `/tmp/klaude-context-icon-preview/`. Grid retains its larger icons.
The view and pagination buttons also remove their internal padding: a 22px SVG
previously overflowed their 20px-wide content area, placing it 1px right of the
button center. Follow-up browser measurements include these controls as well as
file tiles and glyphs; all 24 layouts pass with centered controls and no console
errors. Measurements: `/tmp/klaude-context-all-icons-centered.log`.

Native drag/drop carries only the original artifact ID, exact revision and
selecting session in a bounded custom MIME payload. The existing chat drop overlay
and attachment API validate the selection. Keyboard and touch users attach files
through the composer's existing Library picker.
Neither path imports a copy or submits a message. Wrong-session payloads, changed
or archived artifacts and existing attachment limits retain their rejections.
Per-file Attach buttons were removed from List, Grid and Gallery on 2026-10-22.
Their click handlers and unused CSS were removed too. The desktop hint still
explains dragging; the mobile hint points to the chat attachment menu.
The updated browser check verifies each row/tile has only its Preview button
across mouse, keyboard, hybrid-touch and phone/tablet layouts. It compares the
sidebar's computed Gallery styles against the main Library and checks square,
footer-free tiles and date grouping across two months. Native dragging and the
mobile composer Library picker pass with original IDs, preserved draft text,
no duplicate imports and no automatic submission.
Evidence: `/tmp/klaude-context-no-attach.log` (24 light/dark responsive layouts,
zero browser exceptions). JavaScript syntax, scoped Ruff, both asset bundle
checks and `git diff --check` passed. Screenshots:
`/tmp/klaude-context-panel-preview/library-*.png`.
This is a frontend-only change; backend tests were not repeated. Reload the page
to load the updated static assets; no Python host restart is required.

## Validation

- Focused backend regression: **161 passed, 1 deselected** (`test_chat_attachments`, `test_activity`,
  `test_application_bridge`, `test_webhost`, `test_library_management` and new
  `test_inspection`). The unrelated
  `test_webhost_markdown_assets_are_local_pinned_and_keep_csp` assertion is
  excluded: concurrent startup-screen work adds a synchronous
  `/loading-indicator.js` script while the old assertion forbids it. Its initial
  failure is recorded in `/tmp/klaude-context-startup-exclusion.log`; that unrelated behavior
  was preserved.
- New Python cases exercise real native edits, forged tool metadata, denied
  availability, private input/output omission, sensitive paths, safe error
  classes, history bounds, duplicate tool requests, pruned counts, public-only
  Library references and filter-before-pagination semantics. Existing attachment
  HTTP cases also verify Current scope after sending original Library images.
- `scripts/webui_context_panel_smoke.py`: isolated real Chrome/HTTP/SSE fixture;
  idle/running/completed/failed/cancelled/approval states, accepted/denied reviews,
  expansion, reordered/duplicate events, reload/reconnect, session switch/resume,
  authorized file inspection, rejected escape/diff queries, long/untrusted text,
  Library scope/search/preview/retry, native Library drags, Attach, original
  identity, no automatic send, stale payload rejection and view persistence.
  Checks 24 light/dark × 1440/768/390/320 × List/Grid/Gallery layouts, including
  320×480 usable content height, tab arrows, Escape and focus restoration.
- Existing `scripts/webui_activity_smoke.py` and
  `scripts/webui_drop_smoke.py` pass independently. Device drags retain quota,
  stale-selection, logout and reviewed import behavior.
- The main Library browser fixture explicitly closes the Context Panel before
  checking Library content at drawer widths, preserving user-controlled panel
  visibility, and waits for startup to release the shell before physical clicks.
  The broader run passed its view/layout and preview checks but later failed the
  import dialog's Escape focus-return assertion (`file-add`). That workflow was
  left untouched. Failure: `/tmp/klaude-context-gallery-library-regression.log`.
  `KLAUDE_TEST_LIBRARY_VIEWS_ONLY=1` isolates the relevant view/layout regression
  from the import workflow: **36 responsive layouts passed**, including real
  history/search/pagination and image previews, with no browser exceptions.
  Result: `/tmp/klaude-context-gallery-library-views.log`.
- Scoped Ruff, JavaScript syntax checks, mypy for 11 touched source files and
  `git diff --check` pass. These are focused checks, not a full-suite or
  physical-device claim. Browser screenshots are under
  `/tmp/klaude-context-panel-preview`.
- The idle managed host was gracefully reloaded with its session, workspace,
  LAN binding and settings bytes preserved. Its runtime snapshot confirms the
  Context Panel capability and session-matched Inspector projection. Browser
  cookies are revoked by the existing stop behavior; reload and sign in again.
  Receipt: `/tmp/klaude-context-host-validation.json`.

No stash, reset, commit or push. Existing unrelated changes remain in place.

Chevron refinement: the Inspector now shares the Settings disclosure CSS rule,
including 16px sizing, filled rounded shape, muted color and 150ms rotation.
The existing shared SVG path and native details behavior remain unchanged.
A temporary focused browser fixture checked eight light/dark and
1440/768/390/320px combinations, comparing its path and computed styles directly
with the Settings disclosure primitive. Keyboard expansion, 90-degree rotation
and expansion retention after a real snapshot passed with zero browser
exceptions. The fixture first needed to wait for startup focus availability and
send the full Enter key event. Evidence:
`/tmp/klaude-inspector-chevron-smoke.{json,log}` and
`/tmp/klaude-inspector-chevron-preview/`. Whitespace checks passed. This refinement
changes only shared CSS and guidance/validation notes; no backend changes.

Refresh removal: removed the Context Library toolbar button, icon binding and
click handler. Failed reads now direct users to select Library again, using the
existing tab handler to retry. The updated Context Panel smoke verifies the
button is absent and exercises failure/retry through the available controls.
All 24 responsive layouts and remaining workflows passed with zero browser
exceptions (`/tmp/klaude-context-no-refresh.log`). JavaScript syntax, focused
Ruff and whitespace checks passed. Other Library refresh controls are unchanged.
