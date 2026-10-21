# Library file browser and image gallery

Implemented 2026-10-20 against checkpoint 763cff9. `origin/main` was fetched and
matched HEAD before editing; the three untracked Solid Explorer reference JPEGs
were inspected and preserved. Investigation and staged design decisions are in
[library-browser-plan.md](library-browser-plan.md).

## Architecture and presentation

This extends the existing vanilla DOM Library, its native item dialog and shared
SQLite artifact store. No framework, icon package or other dependency was added.
Library separates imported Uploads and Generated (saved research reports/generated
images); indexed Knowledge is under Integrations. Uploads/Generated reuse the same browser and
artifact actions, with provenance filtering before sorting, counts and pages.
Small SVG paths follow the existing icon style, and every surface/text/focus color
uses Klaude's theme tokens. Existing Roboto, rounded shapes, 44px primary targets
and reduced-motion behavior remain in place.

Solid Explorer's compact rows, aligned metadata, file-type tiles and closely
spaced month-grouped imagery informed the layout. Klaude retains its own shell,
colors and typography. Mobile secondary filters collapse behind the Filters and
sort button; search, view switching, location and Add a file remain accessible.
The add action is now a labeled plus icon in the search/actions row, opening a
native dialog styled with the existing `domain-dialog` primitive. It preserves
the unrestricted picker and explicit import review. Upload errors stay inside
the dialog; closing it rejects and discards a late review instead of reopening
the interface.

Below the existing 650px content-width breakpoint, the desktop column header is
hidden. The expandable Filters and sort panel retains type, Saved/Archived and
all seven sort options/directions using the same native selects and URL state.
Escape collapses the panel and returns focus to its trigger. Search, action and
view controls have 48px targets; mobile rows are 70px including their border,
with filename, thumbnail/type icon, type and size. The first row begins 4px below
the closed toolbar. Compact row placeholders replace large card skeletons only
in List mode. Grid/Gallery tile geometry and page capacities are unchanged.

- **List:** compact two-line mobile rows; desktop aligns name, type, size and
  Added columns. Column controls sort the underlying inventory. Full filenames
  remain in accessible button names/tooltips; visible text truncates sensibly.
- **Grid:** two/three/four/six columns, consistent visual areas and filename
  footers. Supported pictures use derivatives; text/code/PDF/audio/video/archive
  and unknown files use type-specific icons. Existing actions open in item details.
- **Gallery:** supported PNG/JPEG/WebP/GIF files only, filtered before counts and
  pagination. Square tiles use object-fit cover without stretching source pixels.
  Date sorts group each page by month added; other sorts retain the requested
  order without misleading month headings. Mobile uses three columns, wider
  layouts four/six. Loading artwork and failed-image fallbacks retain the file's
  accessible name and opening action.

The collection is flat: it has no folder entities, directory hierarchy, source
modification time or capture-date field. No folder cards or invented dates were
introduced. Breadcrumbs show Library → Uploads or Library → Generated; type and
saved/archive state remain in their existing filter controls.
The stored `created` timestamp is always described as when a file was added.
Workspaces remains the separate filesystem-browsing surface.

Add a file uses one unrestricted picker without a Document/Image selector.
The server classifies at most 64 KiB of the captured immutable upload using the
existing PNG/JPEG/WebP/GIF header reader, before presenting the import review.
Recognized images use Media storage and other files use Document storage; the
current search, type and archive filters do not choose the import destination.
The reviewed explicit kind and checksum follow the same owned worker path.
Explicit document/media API drafts and CLI/TUI imports remain compatible.

## State and performance

Library URL state is allowlisted and owns section, mode, filters, search, sort and
page when present. Otherwise, mode/type/status reuse the existing versioned
sessionStorage navigation seam. History restores filters and presentation, and
refresh restores a Library URL. Explicitly leaving Library removes its query
state so refresh honors the newly selected application page. Main-page routing
otherwise retains its existing conventions.

Files uses 24 items per page in every mode. This fits complete two/three/four/six
column grids; month groups can have incomplete rows. At most two existing bounded
inventory reads compose a page; CLI/TUI batches are unchanged. An eight-page,
30-second metadata cache lets List/Grid presentation changes reuse reads. Refresh,
completed operations and sign-out invalidate it. Identical rows retain their DOM
and thumbnails. Obsolete inventory/detail reads are aborted and stale completion
tokens still prevent publication. Canceled image responses close quietly.

Search and seven sort orders run in SQLite before pagination: name ascending or
descending, added newest or oldest, size largest or smallest, and MIME type/name.
Gallery uses exactly the same search/type/status/sort scope plus the image filter.

Image details reuse download, manual tags and the existing reviewed artifact
actions. Previous/next and arrow keys navigate matching images on the current
List/Grid page; Gallery additionally crosses page boundaries. Expansion uses the
native dialog, touch buttons stay visible, Escape closes, and closing restores
the original grid scroll/focus. Browsing images does not move the background page.

## Image service boundaries

`/api/v1/library/image` accepts only a typed artifact ID, exact revision and one of
two fixed sizes. It never accepts a filesystem path. Owner cookie, Host/Origin
and same-origin response protections remain unchanged; image output is no-store.
Source bytes are bounded SQLite blob reads under a read transaction, checked for
actual length, a 32 MiB maximum and the stored SHA-256 before decoding.

The existing disposable decoder verifies image format and dimensions, limits
sources to 40 megapixels/32768px per side, and applies its CPU/memory/output/time
bounds. Thumbnails fit 320px and expanded previews fit 2048px, within the existing
7,500,000-byte delivery cap. Orientation is normalized and metadata stripped;
animated sources show frame zero. Originals and artifact revisions are unchanged.

The private per-host LRU keys output by store, ID, revision, source hash and size.
It retains at most 128 entries/32 MiB for 15 minutes; two preparation workers bound
concurrency. Revision/owner checks apply to hits, concurrent changes and logout
reject a newly generated result, and shutdown clears the cache. Output delivery
rechecks owner liveness between bounded chunks. Unsupported/corrupt images fail
without executing document content or exposing source paths.

The original `/library/content?inline=1` endpoint retains its earlier limits and
behavior. Small thumbnails never request original-resolution downloads.
An older running host advertises no derivative capability: updated assets retain
its prior bounded inline preview path and original sort options, and disable
Gallery with restart guidance. New hosts always use derivatives for Library
thumbnails. Capability changes are scoped without repeatedly reloading inventories.

## Verification

See the final execution results below. These checks use isolated model-free
fixtures and real Chrome; they do not certify physical Android/iOS devices,
every screen reader, or full WCAG conformance.

- Core/HTTP regressions cover filter-before-page counts, expanded ordering,
  thumbnail cache reuse, source immutability/metadata stripping, large-image
  derivatives, exact revision/archive/delete semantics, authentication, cross-site
  rejection, path traversal, corrupt bytes and revocation during decoding.
- `scripts/webui_library_browser_smoke.py` uses 1,058 saved files and 50 supported
  images of portrait/landscape/square dimensions. It checks read reuse, URL
  back/forward, reload/search/sort, abort races, date grouping, page-crossing image
  navigation, arrow keys/Escape/focus, phone filters, expansion, reviewed tags,
  corrupt-image fallback and logout cleanup. All 24 combinations of List/Grid/
  Gallery × Light/Dark × 1440/768/390/320px are visually inspected and fit without
  horizontal overflow. Exactly 24 file items render per full page. No original
  image content route is used for thumbnails.
- The existing loading smoke checks Library/Knowledge/Skills, migration from old
  stored tabs, placeholder lifecycle, stale-result ownership, reduced motion,
  preview cancellation and logout. Its fixtures now include the real Added field,
  and legacy-tab tests omit explicit URL state as required by the new precedence.
- Screenshots: `/tmp/klaude-library-browser-preview/`; browser result files:
  `/tmp/klaude-library-browser-smoke-result.json` and
  `/tmp/klaude-loading-library-regression.json`.

## Files and limitations

Frontend: `static/index.html`, `library.js`, `style.css`, and the optional request
signal/navigation integration in `app.js`. Backend: `library_images.py`, host
routes, `application.library_management`, core artifact filtering/sorting and the
shared image preparation size option. Coverage: the new Library browser unit and
Chrome scripts, updated loading smoke, this record/plan, README, CHANGELOG,
coverage checklist and AGENTS.

Complete changed-file manifest:

- `apps/webhost/src/klaude_webhost/static/app.js`
- `apps/webhost/src/klaude_webhost/static/index.html`
- `apps/webhost/src/klaude_webhost/static/library.js`
- `apps/webhost/src/klaude_webhost/static/style.css`
- `apps/webhost/src/klaude_webhost/host.py`
- `apps/webhost/src/klaude_webhost/library_images.py` (new)
- `packages/application/src/klaude_application/library_management.py`
- `packages/core/src/klaude_core/library_artifacts.py`
- `packages/core/src/klaude_core/image_preparation.py`
- `tests/unit/test_library_browser.py` (new)
- `tests/unit/test_web_library.py`
- `scripts/webui_library_browser_smoke.py` (new)
- `scripts/webui_loading_smoke.py`
- `AGENTS.md`, `README.md`, `CHANGELOG.md`
- `docs/webui/coverage.md`
- `docs/webui/library-browser-plan.md` (new)
- `docs/webui/library-browser-validation.md` (new)

Folder management, original modification/capture metadata, full-resolution zoom,
animation playback, image editing, bulk selection and arbitrary document renderers
remain outside this enhancement. Browser metadata caches refresh after 30 seconds
or explicitly; decoded pixels are cached only in the host's bounded private memory.

### Final execution results

- Focused Library, operations, host/accounts, attachments, image-preparation and
  artifact regressions: **153 passed in 111.77s**. This is a focused suite, not a
  full repository unit run.
- `make lint typecheck`: Ruff passed across the repository, and production mypy
  passed all **211 source files**. JavaScript syntax checks and `git diff --check`
  passed.
- `make package-smoke`: all seven workspace wheels built and installed in an
  isolated temporary environment; imports, bundled assets and both CLI help
  commands passed. No dependencies or lockfile changes were needed.
- Real Chrome Library acceptance and existing loading smoke both passed with
  no JavaScript exceptions. The final Library fixture additionally covers the
  old-host capability guard and file selection feedback. The fixture observed
  no long tasks after its final reload; this is diagnostic, not a hardware or
  sustained performance benchmark.
- The running host initially had an active chat turn, which was left running.
  After it became idle with no queue/reviews, the updated application first
  reopened its exact saved runtime without generation. A graceful host reload
  retained session ID, dialogue hash, model/mode/effort/plan/composer settings,
  workspace and LAN address. The new image capability was verified live.
- Real Chrome on the live host decoded the existing lossless WebP as a 290 ×
  320 Gallery thumbnail and a 1598 × 1763 detail preview. It worked after reload
  and fit 1440/390/320px layouts. The original content checksum and conversation
  were unchanged; the temporary client signed out with no browser exceptions.
  Diagnostic: `/tmp/klaude-library-live-browser-check.py`. It uses the exact
  artifact ID because stored filenames can legitimately repeat.
- No active turn was canceled, no user artifact was changed, and no commit/push
  was performed for this enhancement. Existing browser clients must refresh and
  sign in again after the graceful host reload.

### Automatic import follow-up

- Removed the manual storage-type selector. Focused HTTP, shared operations and
  artifact regressions passed: **74 passed in 42.78s**. Authenticated reviewed
  imports cover ordinary text and all four supported image formats, including a
  PNG named `.txt`; imported checksums, dimensions, Gallery eligibility,
  deduplication and logout ownership are verified through real owned workers.
  Earlier explicit-kind service tests continue to pass.
- Both Chrome scripts passed without browser exceptions. The Library script
  additionally imports a WebP named `.txt` with a false `text/plain` declaration
  while the Document filter and unrelated search are active. The review detects
  an image; confirmation saves Media, preserves the filter/search and displays
  the resulting thumbnail in Gallery. The loading script checks the unrestricted
  picker and absence of the selector. Native dialog focus checks now wait for
  the close event, and programmatic filter tests dispatch real change events.
- Repository Ruff and production mypy passed (211 source files). No dependency
  changes or repeat packaging build were needed for this follow-up.
- The idle managed host was reloaded with the exact session/workspace/LAN
  configuration after verifying its saved runtime could reopen. Dialogue and
  model/mode/effort/plan/settings revisions remained unchanged. Diagnostic output:
  `/tmp/klaude-library-automatic-import-browser.json` and
  `/tmp/klaude-loading-automatic-import.json`.

### Compact mobile Files follow-up

- Inspected the existing toolbar/form, shared native dialogs, row renderer,
  container queries, URL/filter state and loading primitive before editing.
  Reused existing icons, tokens, typography, shapes, motion, review operations and
  paging. No dependencies or backend changes were required for this follow-up.
- Changed `static/index.html`, `static/library.js` and `static/style.css`, extended
  `scripts/webui_library_browser_smoke.py` and `scripts/webui_loading_smoke.py`,
  and updated `AGENTS.md`, `CHANGELOG.md`, `docs/webui/coverage.md` and this record.
- Focused HTTP Library/browser regressions: **25 passed in 21.38s**. The first
  sandboxed invocation could not create loopback sockets; rerunning with socket
  access passed. No application test failure remained.
- Chrome 148 checked List/Grid/Gallery in both themes at 320, 390, 560, 768, 850
  and 1440px (36 combinations). Compact lists measured a 48px toolbar, 70px rows,
  no visible column header and a 4px first-row gap. Wide layouts retained sortable
  headers. No document/content overflow or browser exceptions were observed.
- Actual pointer activation verified toolbar controls and dialog access; Escape
  verified filter/dialog dismissal and focus restoration. All seven sort options,
  existing search/history/page navigation, reviewed tags, automatic reviewed
  imports, and discarded late import reviews passed. Native file-picker OS UI
  was not automated; fixture files were assigned through the browser File API.
- Delayed-response checks exercised populated, loading and empty List layouts at
  320/390/768/1440px, including return to a previous width. Unique queries avoid
  mistaking a legitimate metadata-cache hit for a missing loading placeholder.
  Existing stale-response, reduced-motion and sign-out checks also passed.
- Inspected desktop/mobile screenshots including light/dark lists, 320px upload
  dialog and mobile/desktop empty/loading states. Evidence:
  `/tmp/klaude-files-compact-browser.json`, `/tmp/klaude-files-compact-loading.json`,
  `/tmp/klaude-files-compact-tests.txt`; screenshots remain under
  `/tmp/klaude-library-browser-preview` and `/tmp/klaude-loading-preview`.
- Repository Ruff, JavaScript syntax and `git diff --check` passed. There is no
  frontend build step for these native browser assets. The full Python suite and
  physical-device/screen-reader verification were not run for this CSS/DOM change.
  Existing dirty work was preserved; this follow-up did not commit, push or restart
  the managed host.

### Separate user inputs and AI outputs

- Added **AI outputs** beside Files and Knowledge. Files contains imported
  Documents/Media; AI outputs contains saved Research reports and generated
  images, with All outputs/Research reports/Images filters. Only Files shows
  the upload action. Search, sorting, Saved/Archived, List/Grid/Gallery and existing
  reviewed preview/tag/source/archive/restore/delete behavior are shared.
- The additive `source=all|input|output` read filter reaches the shared artifact
  inventory. A Research record or an artifact present in the existing
  `generated_images` provenance table is an output. Every other artifact is an
  input. Filenames, tags, model labels and prompts do not decide authorship.
  The filter runs in SQLite before counts, search/sort and paging. No artifacts
  are moved, rewritten or reclassified, and no schema migration is needed.
  Legacy stores without `generated_images` remain read-only and separate Research
  records correctly. Existing `kind=all` API and CLI/TUI behavior is unchanged.
- The counts endpoint supplies independent unfiltered Files/outputs totals.
  The browser retains active per-tab filters/search/sort/page/view when switching,
  existing allowlisted URL history stays authoritative, and output preferences
  reuse the existing sessionStorage namespace. Old Research tabs and Files URLs
  with `files-type=research` migrate to AI outputs. An older running host without
  source support shows restart guidance instead of a mixed file inventory.
- Changed `static/index.html`, `static/app.js`, `static/library.js`,
  `static/style.css`, `host.py`, application `library_management.py`, core
  `library_artifacts.py`, both Library/loading Chrome scripts,
  `tests/unit/test_library_browser.py`, `tests/unit/test_library_management.py`,
  `AGENTS.md`, `README.md`, `CHANGELOG.md`, `coverage.md`, the browser plan and this
  validation record. No dependency was added.
- Focused HTTP/browser/shared-management/artifact suite: **86 passed in 58.74s**.
  A subsequent focused provenance check also passed after explicitly testing an
  AI-tagged imported image. Coverage includes disjoint inventories and accurate
  counts across multiple pages, name/search filters, archived inputs/outputs,
  generated-image Gallery filtering, invalid/unauthenticated reads, unchanged
  private DTO boundaries and a legacy database without a provenance table.
- Chrome covers both tabs, independent counts, report preview, stored Research
  migration, old Reports-filter URLs, direct reload and back/forward, old-host
  guidance, all view modes, and existing imports/tags/image navigation. The base
  fixture still has 1,058 inputs/50 input images; three reports and three generated
  images are additional, disjoint outputs. Files covers 36 view/theme/viewport
  combinations; outputs also cover List/Grid/Gallery at 320/1440px. Loading/empty
  states and old navigation preferences passed in the delayed-response script.
- Inspected desktop/mobile Files/outputs screenshots. The verified idle managed
  host was gracefully reloaded after exact saved-runtime preflight; its session,
  dialogue, model/settings revisions, workspace and LAN listeners were preserved.
  Read-only live Chrome checks at 1440/390/320px found disjoint inventories,
  correct upload visibility, no horizontal overflow and no browser exceptions.
  Stored artifact IDs/revisions/checksums/archive flags were unchanged. Evidence:
  `/tmp/klaude-library-sources-tests.txt`, `-provenance.txt`, `-types.txt`,
  `-browser.json`, `-loading.json`, `-reload-result.txt`, `-live-result.json`
  (all with prefix `/tmp/klaude-library-sources`). Screenshots are under
  `/tmp/klaude-library-browser-preview` and `/tmp/klaude-library-sources-live`.
- Repository Ruff, 211-file production mypy, JavaScript syntax and diff checks
  passed. No new build step/dependency was introduced. The full repository suite,
  physical-device and complete screen-reader testing were not run for this slice.
  AI outputs currently covers saved Research/generated-image records; arbitrary
  workspace files or ordinary chat replies are not automatically collected there.
  Existing dirty work is retained; no commit or push was performed.

### AI outputs empty-state placement

- Moved AI outputs empty/no-match messages from the status above the controls
  into the full-width content area below its toolbar. Empty lists omit the column
  header; populated rows replace the message. The paragraph reuses the existing
  status typography/color and has `role="status"`. Other Library status behavior
  is unchanged.
- Updated `static/library.js`, `static/style.css`, the loading smoke, and agent
  guidance. The loading smoke passed at 320/390/768/1440px, checking position,
  accessible status, no overflow and clearing after results return. Live read-only
  Chrome checks passed at 1440/390/320px, including the exact saved-output message;
  desktop/mobile screenshots were inspected. No browser exceptions or artifact
  changes occurred. JavaScript syntax, focused Ruff and diff checks passed.
- Evidence: `/tmp/klaude-output-empty-loading.json`,
  `/tmp/klaude-output-empty-live-result.json`, screenshots under
  `/tmp/klaude-output-empty-live`. No managed-host restart was needed.

### Generated label

- Renamed the public AI outputs tab to **Generated**, including breadcrumbs,
  search labels, preview return text, gallery captions and the empty-state copy.
  Its type selector now says All types. Existing `outputs` URL/count identifiers
  and stored preferences remain compatible; research reports and generated images
  use the same provenance filters and actions.
- Live Chrome verified the label and empty content at 1440/390/320px, including
  both light and dark appearances, with no browser exceptions or artifact changes.
  JavaScript syntax, focused Ruff and diff checks passed. Evidence:
  `/tmp/klaude-generated-label-live-result.json`, screenshots under
  `/tmp/klaude-generated-label-live`. No restart was needed.

### Knowledge under Integrations

- Library now has only Files and Generated. Moved the existing Knowledge forms,
  results and Sources into an Integrations panel beside Skills; the deferred
  Connections control remains present. Reused all existing Material 3 primitives,
  native controls, typography and color/motion tokens without new dependencies.
- Extracted the Knowledge read renderer from the shared Files renderer. Knowledge
  has its own status, results and pager, while Sources retains its existing
  controls. Near-20 whole-row page capacities, bounded two-read composition,
  search, Learn URL/text uploads, exact source-refresh reviews, and accepted
  operation refresh use the existing services. No backend route or store changed.
- `integrations=knowledge` URLs retain selected library, query and result/source
  pages. Legacy `library=knowledge` links and saved Library Knowledge selections
  migrate. Browser reload/back/forward and switching to Skills preserve Knowledge
  state. URL pages resolve after measuring the visible grid, so a 21-card page
  survives reload. Leaving rejects obsolete read results; sign-out also stops
  deferred rendering and clears Knowledge fields/content. Accepted work continues.
- Changed `static/index.html`, `static/app.js`, `static/library.js`, the existing
  loading Chrome smoke, and `AGENTS.md`, `README.md`, `CHANGELOG.md`, `coverage.md`,
  the browser plan and this validation record. No additional CSS system or Python
  backend changes were needed for this move.
- Focused HTTP Library/Knowledge/Skills/shared-operation tests: **39 passed in
  38.22s**. Chrome loading regression passed, including the moved panels, independent
  status, stale results/sign-out, Knowledge Learn/source-refresh review drafts,
  Cancel focus and discard behavior. Review transport was controlled in the
  browser; no model, embedding or network learning job was submitted there.
- The existing Files/List/Grid/Gallery browser acceptance passed with 36 base
  mode/theme/viewport combinations plus Generated checks and reviewed imports.
  Live read-only Chrome verified actual Knowledge inventory/search, legacy-link
  migration, page-2 reload, back/forward, Skills switching and Library's two tabs.
  Eight light/dark layouts at 320/390/768/1440px fit without horizontal overflow;
  desktop/mobile screenshots were inspected. No browser exceptions or artifact
  changes occurred. Evidence: `/tmp/klaude-knowledge-integrations-tests.txt`,
  `-loading.json`, `-files.json`, `-live-result.json` with the same prefix;
  screenshots under `/tmp/klaude-knowledge-integrations-live`.
- Repository Ruff, both edited JavaScript syntax checks and `git diff --check`
  passed. No full repository suite or physical-device/screen-reader audit was run.
  No host restart, commit or push was performed; unrelated dirty work is retained.

### Uploads label

- Renamed the public Files tab to **Uploads**, including its breadcrumb, search
  labels, All uploads filter, gallery caption, empty state and preview return
  text. Existing `files` routing/count/preference identifiers remain compatible;
  Generated and Integrations → Knowledge retain their behavior.
- Live read-only Chrome checked the tab/breadcrumb/search/filter labels at
  1440/390/320px, light/dark appearance, and preserved Generated/empty-state
  behavior. No browser exceptions or artifact changes occurred. JavaScript
  syntax, focused Ruff and diff checks passed. Evidence:
  `/tmp/klaude-uploads-label-live-result.json`; screenshots under
  `/tmp/klaude-uploads-label-live`. No restart was needed.

### Shared document/media filters

- Both Uploads and Generated now use **All types / Documents / Media**. Research
  reports are a document subtype, so they appear under Generated → Documents.
  The browser maps that category to the existing `research` API filter; previews,
  record IDs, permissions and reviewed actions are unchanged. No backend/store
  change or host reload was required. Older Research preference/URL values migrate
  to the Documents category and are canonicalized in subsequent navigation.
- Changed the existing selector configuration/URL mapping in `static/library.js`,
  its initial HTML option, both existing browser smoke scripts and product docs.
  No client-side post-pagination filtering or extra read source was introduced.
- The full Library Chrome smoke passed, including identical selector choices,
  generated reports under Documents, images under Media, legacy Report links,
  history, paging and reviewed imports. Loading/migration checks also passed.
  Live read-only desktop/mobile checks at 1440/390/320px verified both selectors,
  with no browser exceptions or artifact changes. JavaScript syntax, focused
  Ruff and diff checks passed. Evidence: `/tmp/klaude-library-types-browser.json`,
  `-loading.json`, `-live-result.json` with the same prefix; screenshots under
  `/tmp/klaude-library-types-live` and `/tmp/klaude-library-browser-preview`.

### Library breadcrumbs

- Breadcrumbs now show **Library → Uploads** and **Library → Generated**.
  Saved/Archived and type remain filter state. These labels describe application
  sections, independent of workspace project paths; Workspaces remains the real
  filesystem browser. Existing breadcrumb reset behavior is preserved.
- Tightened breadcrumb gaps/padding while retaining a 48px Library touch target;
  the current section keeps its accessible full name and title at narrow widths.
  Updated the loading regression to check archive state through the status
  selector. Live Chrome checked both paths at 1440/390/320px with no horizontal
  overflow, browser exceptions or artifact changes. The loading/archive filter
  smoke, JavaScript syntax, focused Ruff and diff checks passed. Evidence:
  `/tmp/klaude-library-breadcrumb-live-result.json`,
  `/tmp/klaude-library-breadcrumb-loading.json`, screenshots under
  `/tmp/klaude-library-breadcrumb-live`. No backend change or restart was needed.

### Combined checkpoint verification

- Fresh focused regression run: **189 passed in 118.64s** across Library browser,
  source links, artifacts, management, HTTP Library, workspace Library, host,
  accounts and image preparation. This is not the full repository unit suite.
- Repository Ruff, production mypy (**211 source files**), JavaScript syntax
  checks for library/app/markdown and staged whitespace checks passed.
- All four real Chrome scripts passed: Library browser (36 mode/theme/viewport
  layouts), image preview (12 layouts with touch gestures and reviewed actions),
  loading/empty/stale-response states (19 checks) and Markdown (24 checks).
  Each reported zero browser exceptions or console errors. Evidence:
  `/tmp/klaude-checkpoint-library-browser.json`,
  `/tmp/klaude-checkpoint-image-preview.json`,
  `/tmp/klaude-checkpoint-loading.json`, `/tmp/klaude-checkpoint-markdown.json`.
- Packaging built and installed all **seven workspace wheels**, checked imports
  and bundled assets, and ran both CLI help commands. The initial sandbox run
  could not resolve PyPI; rerunning with network access passed. Log:
  `/tmp/klaude-checkpoint-package.log`.
- No new dependencies or lockfile changes. Physical-device, Safari and full
  screen-reader/accessibility testing remain outside this checkpoint's evidence.

## Text and code preview controls

The source-layout and whitespace refinements in
[`file-preview-refinement.md`](file-preview-refinement.md) supersede the initial
text-control implementation described below. The optional authenticated source
projection preserves tabs and line endings; terminal/legacy-host lines retain
their original normalization. See that report for current browser evidence.

Readable text/code files now offer **Wrap**, **No wrap** and **Copy** in the fixed
preview toolbar. Wrap is selected when a preview opens. No wrap preserves line
layout and scrolls long lines horizontally within the preview; switching back to
Wrap resets horizontal scrolling. The code font and text color use the existing
theme roles.

Copy writes the exact displayed preview text, preserving spaces, line breaks and
Unicode. It shows a checkmark, **Copied** feedback and an accessible status, and
retains keyboard focus while preventing overlapping copy requests. The existing
clipboard helper supports the HTTP/LAN selection fallback. Copy uses the bounded
preview; the truncation notice and Download link identify how to get a complete
file. These controls are cleared while loading, on close and for image/binary
previews. Reload the browser page to load the updated static assets.

Validation: the real Chrome Library browser smoke passed its existing navigation,
image and reviewed-action checks plus 16 text-preview wrap/theme/width states at
1440, 768, 390 and 320px. It verified contained horizontal scrolling, matching theme
text colors, exact Unicode/indentation copying through the clipboard API and real
HTTP fallback, retained Copy focus, default reset on reopen, literal HTML, and
hidden controls for image/binary previews. There were zero browser exceptions.
Scoped Ruff, JavaScript syntax and `git diff --check` passed. This is browser-fixture
validation, not the full unit suite or physical-device coverage. Evidence:
`/tmp/klaude-code-preview-smoke.json` and
`/tmp/klaude-library-browser-preview/code-{wrap,no-wrap}-{light,dark}-{1440,320}.png`.

### Generated filter visibility

Removed the Generated-only rule that hid the filter dropdowns on wide content.
Generated now matches Uploads: Type, Status and Sort appear inline at the existing
650px content breakpoint; compact layouts expose them through Filters and sort.
The Create plus button remains beside the toolbar controls.

`KLAUDE_TEST_GENERATED_FILTERS_ONLY=1 .venv/bin/python
scripts/webui_library_browser_smoke.py` passed with real generated image/report
fixtures at 320/390/768/1440px. It checked visible, enabled controls, Documents and
Media inventories, descending name order and no horizontal page overflow, with
zero JavaScript exceptions. Phone and desktop screenshots were visually checked:
`/tmp/klaude-library-browser-preview/generated-filters-{390,1440}.png`.
Focused Ruff, Python compilation and `git diff --check` passed. This records the
focused filter run; no new full browser or repository suite pass is claimed.
