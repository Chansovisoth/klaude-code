# WebUI usability refinement validation

## Architecture and scope

Inspected the current `app.js`, `library.js`, HTML/CSS shell, application Library
management/inventory/worker projections, existing browser fixtures, planning spec
v2 and bridge RFC before implementation. The frontend is plain JavaScript with
native dialogs/popovers, allowlisted URL/sessionStorage state and shared Material
3 Expressive tokens. Historical planning navigation does not override the current
Uploads/Generated and Integrations hierarchy.

The working tree was clean at inspection (`e9fe4a6`). Attachment/text-preview
source, tests and documentation changed concurrently during this work. Those edits were
preserved; this refinement did not change backend APIs, storage, permissions,
session ownership, streaming or workers. No dependencies, commit or push.

## Result

- **Library:** Uploads and Generated stay separate, with existing provenance
  counts and independent filters. List/Grid/Gallery, thumbnails, all existing
  sort options, preview/download, reviewed import/tags/archive/delete and browser
  history remain. Search uses one debounced field plus Enter/native search-clear
  behavior. There is no redundant search button.
- **Refresh:** existing reads and cache invalidation are wrapped with an in-flight
  guard and accessible busy state. No search/filter/view/sort/tab reset. Existing
  content remains visible during refresh and after failure; errors use the
  existing status mechanism. The browser test preserves the actual row node and
  scroll position through a failed refresh, then adds a backend fixture and
  verifies a successful refresh retrieves it with identical controls.
- **Empty/loading/error:** initial empty Uploads/Generated, unmatched searches,
  excluded filters, row skeletons and initial load failures are distinct. Empty
  file messages appear below the toolbar with a small existing icon and one live
  status announcement. Failed refreshes retain useful data.
- **Skills:** compact keyed rows show a bounded two-line description, confirmed
  enabled state, labeled native-button switch and details affordance. Metadata
  and deletion move to a native dialog. Switches keep the exact existing review,
  submit, ownership and receipt flow. Preparing/accepted/unconfirmed requests
  prevent conflicts. Failed requests leave the confirmed state unchanged;
  uncertain requests remain blocked for local inspection. Deletion describes the
  retained originals/index removal and focuses Cancel before permanent deletion.
  Leaving Skills while a review is preparing discards the late result; accepted
  operations retain their existing lifetime.
- **Knowledge:** compact keyed library/source rows keep existing exploration,
  indexed-text search, learning and reviewed source refresh. Library IDs, source
  counts and chunk counts come from their existing public projection; absent
  counts are unavailable, never invented. Inventory/search/source pages are
  bounded to 20 rows. No duplicated client-side 795-record inventory or new API.
- **Navigation:** desktop retains its destinations. Phones show Chat, Workspaces,
  Library, Integrations and More; More contains Activity/Settings, using the
  existing native popover/menu styling and icons. Labels grow from 9px to 11px
  with targets at least 48px. More supports arrows/Home/End/Escape, outside
  dismissal, active-page indication and auth/resize cleanup. Allowlisted primary
  `view` URLs extend existing Library/Knowledge history; route changes retain
  unsent chat text and accepted operations. Tablet rail items fit their column.
- **Identity:** existing tonal roles, palettes, Roboto, SVG icons, rounded shapes,
  focus styling, motion and reduced-motion rules remain authoritative. No new
  hardcoded colors or UI framework. The warm Peach dark palette remains intact.

The Knowledge tab count is the number of indexed **library IDs**, bounded at
1,000, not the number of sources/chunks. This follows `knowledge_inventory()` and
`LibraryManagement._inventory_page()`/`tab_counts()`. The acceptance fixture uses
795 distinct libraries and verifies 20-row pages, actual FTS search, sources and
page-two reload. Each row reports its own source/chunk counts independently.

## Files changed by this refinement

| File | Purpose |
| --- | --- |
| `apps/webhost/src/klaude_webhost/static/app.js` | More menu, primary-route URL/history, focus and cleanup |
| `apps/webhost/src/klaude_webhost/static/index.html` | Single file search control, collection containers, Skill dialog, More menu, Settings Memory placeholder |
| `apps/webhost/src/klaude_webhost/static/library.js` | Compact keyed rows, refresh guard, debounced search, empty states, reviewed Skill state/details |
| `apps/webhost/src/klaude_webhost/static/style.css` | Compact rows/switches, toolbar widths, mobile labels/menu and tablet rail sizing |
| `scripts/webui_refinement_smoke.py` | Isolated real-backend/browser acceptance plus controlled request failures and screenshots |
| `scripts/webui_loading_smoke.py` | Update the empty-Uploads assertion to its content-area location |
| `AGENTS.md` | Current UI behavior/paging; preserve concurrent attachment notes |
| `docs/webui/coverage.md` | Supported UI and deferred boundaries |
| `docs/webui/ux-refinement-plan.md` | Investigation, implementation sequence and constraints |
| `docs/webui/ux-refinement-validation.md` | This report |

## Executed validation

- Focused HTTP Library, browser and management regressions:
  **51 passed in 59.25s**. This is not the full repository suite.
- Repository Ruff passed; production mypy passed **211 source files**.
  `node --check` passed for both changed scripts; `git diff --check` passed.
- Packaging smoke built/installed **seven workspace wheels**, checked imports
  and bundled WebUI assets and ran both CLI help commands. Evidence:
  `/tmp/klaude-refinement-package.log`.
- Existing real Chrome Library regression passed **36** mode/theme/viewport
  combinations, with 1,058 input files and 50 images, reviewed imports/tags,
  Gallery navigation, filters/history/cache and corrupt-image fallbacks.
  `/tmp/klaude-refinement-library.json`.
- Existing loading Chrome regression passed **19** checks, including empty states,
  canceled/stale responses, reviewed Knowledge actions and sign-out cleanup.
  `/tmp/klaude-refinement-loading.json`.
- Existing Markdown Chrome regression passed **24** checks, preserving message
  actions/links/sharing and stream presentation.
  `/tmp/klaude-refinement-markdown.json`.
- Existing image-preview Chrome regression passed **12** light/dark viewport
  layouts plus real reviewed source/tag/archive/delete operations, pinch/pan/
  swipe/double-tap, keyboard, reduced motion and logout cleanup.
  `/tmp/klaude-refinement-image-preview.json`.
- The refinement Chrome script checks **24** Library/Skills/Knowledge layout
  combinations at **360/390/768/1280px**, light and dark; failed/deduplicated
  refresh, initial load errors, search/filter/empty states, Skill paging/review/
  real worker success/rejection/deletion, Knowledge FTS/source navigation/reload,
  More keyboard/history/deep reload, draft preservation and all eight palettes.
  These fixtures invoke no model or provider generation.
  Evidence: `/tmp/klaude-refinement-acceptance.json`.
- Every successful Chrome report recorded **zero browser exceptions/console
  errors**. Controlled HTTP failures are deliberate fixtures, not production
  failures. These checks use real Chrome viewport/pointer/keyboard behavior,
  not physical phones or Safari.

## Visual comparison

Baseline screenshots are in `/tmp/klaude-refinement-before`; final screenshots
are in `/tmp/klaude-refinement-after`. These are temporary local artifacts using
fixture data, not committed screenshots of the user's private profile.

At 360px, repetitive Skill rows changed from **344px to 100px**, Knowledge from
**171px to 74px**; compact file rows stay **70px**. Details remain available
without placing every field/deletion button on each row. Inspected mobile,
tablet and desktop screenshots, warm dark/light variants and the open More menu.
The visual pass caught a tablet rail scrollbar; items now fit the rail width.
The final acceptance run asserts both document and rail overflow bounds.

| Comparison | Before | After |
| --- | --- | --- |
| Skills, 360px | `/tmp/klaude-refinement-before/skills-360.png` | `/tmp/klaude-refinement-after/skills-360-light.png` |
| Knowledge, 1280px | `/tmp/klaude-refinement-before/knowledge-1280.png` | `/tmp/klaude-refinement-after/knowledge-1280-light.png` |
| Warm dark palette | Existing Peach palette retained | `/tmp/klaude-refinement-after/skills-360-peach-dark.png` |
| Mobile navigation | Six 9px labels | `/tmp/klaude-refinement-after/more-menu-360.png` |

## Remaining boundaries and follow-up

- Browser Connections remains disabled with its truthful configured MCP count;
  there is no existing public management API to preserve or fabricate.
- Settings contains a clear Memory placeholder. Browser memory management remains
  deferred, with saved memories managed in the CLI.
- Skill details display the metadata the current public inventory supplies.
  Descriptions are backend-bounded, installation information is a safe label,
  and only indexed-file counts are available. No repository URLs, full source
  paths, indexing progress or connectivity statuses are inferred.
- Unconfirmed operations retain the existing local-inspection/reconciliation
  boundary. There is no new browser recovery endpoint.
- No full unit suite, physical-device/Safari, exhaustive contrast/font-scaling
  certification or screen-reader audit was performed. A later accessibility/
  device pass is the appropriate follow-up; deferred domain management requires
  its own reviewed bridge contract.

## Continuation: state and accessibility

The continuation stayed within the existing frontend. It reused the completed
backend/unit/build evidence above instead of running those suites again.

- Fixed Skills search/page restoration using the existing allowlisted URL seam.
  `skills-q` retains at most 200 characters; `skills-page` uses the existing
  bounded page range. Skills and Knowledge remove each other's URL fields when
  switching, preserving their local state. No backend parameters or APIs changed.
- Verified actual keyboard activation, native details dismissal/focus return and
  stable focused row identity across refresh. Browser Back also closes Skill
  details before restoring the previous list. Native Enter/Escape test inputs
  needed their virtual key codes; missing codes were fixture issues, not product
  keyboard failures.
- The enlarged-text inspection found overlapping collection headings and clipped
  navigation labels. Headings and labels now wrap, and the mobile bar can grow.
  A ResizeObserver on the bar alone reserves its intrinsic height for content,
  menus and drawers. It does not observe visualViewport, resize from keyboard
  events or adjust focused-input scrolling. Safe-area handling remains in CSS.
- Collection buttons expose counts/descriptions alongside their concise names.
  Forced-color switches use system colors to distinguish track/thumb states.
- Focused Chrome run, `scripts/webui_refinement_smoke.py --accessibility`, passed
  **six checks**, **12 enlarged-text layouts** (Library/Skills/Knowledge at
  360/390/768/1280px) and **16 palette/scheme contrast samples**, with **zero
  browser exceptions**. Query/page restoration, Refresh, tab switching and
  Back/Forward passed. Chrome's accessibility tree exposes named controls and
  checked switch states. Reduced motion and forced-color focus cues passed.
- The text stress doubles computed fonts and line heights on the scoped controls,
  asserts the doubled values actually apply, and checks for document/content/rail
  overflow and heading/navigation overlap. This is a controlled text-size test,
  not certification of browser zoom or a physical device's font setting. Inline
  stylesheet injection was rejected by the existing CSP during test development;
  the fixture uses direct style properties without weakening production CSP.
- Sampled existing surface, muted, primary and selected-row text pairs all exceed
  **4.5:1** across eight palettes in light/dark; the lowest sampled ratio is
  **6.07:1**. This is not an exhaustive contrast/state audit.
- Evidence: `/tmp/klaude-refinement-a11y-final.json`; enlarged-text and forced-color
  screenshots in `/tmp/klaude-refinement-after/a11y-*.png`. Mobile and tablet
  final screenshots were visually inspected after the fixes.
- The normal refinement Chrome regression also passed again: **24 layouts** and
  **eight workflow checks**, zero browser exceptions. Evidence:
  `/tmp/klaude-refinement-continuation.json`. Repository Ruff, both changed
  JavaScript syntax checks and `git diff --check` passed. Prior Python, mypy and
  packaging results above were reused, not rerun for this frontend follow-up.

Physical-device/Safari testing and a manual screen-reader audit remain follow-up
work. Connections/Memory management remains deferred. Concurrent attachment and
text-preview changes remain preserved; no commit or push was performed.

## Consistent action icons (2026-10-21)

Dialog close controls use the same local SVG cross, including conversation
details, attachments, message Sources/Share and the file viewer. Icon-only
controls retain accessible names. Download Markdown and Archive/Restore place
their existing local SVG icon before the label; state changes preserve the icon.

The existing Markdown, attachment and Generated-focused management Chrome checks
passed with zero console errors across 320/390/768/1440px. A focused visual check
also confirmed all nine static close icons, conversation action fit, and the
Archive-to-Restore icon on an archived fixture. Screenshots:
`/tmp/klaude-control-icons/`. All four changed JavaScript syntax checks and
`git diff --check` passed. These static-asset changes require a page refresh.

## Dialog backdrop dismissal (2026-10-21)

All native dialogs now use the shared pointer handler in `app.js`, including
message dialogs created later. A primary press must start and finish on the
exposed backdrop without becoming a drag. Inside clicks, scrolling/dragging and
cancelled or multi-touch gestures keep the dialog open. Closing uses the existing
dialog cleanup, including discarding unconfirmed reviews; accepted work keeps
its existing lifecycle. Stacked dialogs dismiss only the targeted top dialog.

`scripts/webui_dialogs_smoke.py` passed **82 real mouse/touch backdrop checks**
at 320/390/768/1440px: all nine static dialogs where a backdrop is exposed, dynamic
Share/Sources dialogs, inside taps, drags in both directions, stacked dismissal
and cancellation of an actual Delete review without changing the file. Phone
and tablet file viewers are fullscreen and have no exposed backdrop; their cross
button and details-sheet scrim remain available. Zero browser exceptions.

The existing Markdown and Generated-focused management Chrome checks also passed,
including stale preparation disposal and logout cleanup. JavaScript syntax,
focused Ruff, Python compilation and `git diff --check` passed. No live-profile
mutations or host restart were needed; refresh the page for the updated assets.
