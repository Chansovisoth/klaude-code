# Library image preview redesign

Implemented 2026-10-20 on the existing dirty Library browser/import work.
The approved HTML mockup and three Solid Explorer JPEG references were inspected
and preserved. The mockup supplies hierarchy and composition; Klaude's existing
Material 3 Expressive design system supplies presentation. Investigation and the
pre-edit implementation plan are in [image-preview-plan.md](image-preview-plan.md).

## Architecture and behavior

The existing native `artifact-detail` dialog, file-detail API, image derivatives,
gallery ordering/page navigation and fixed reviewed-operation worker remain the
integration points. A local presentation/gesture closure in `library.js` owns
the image transform, details state, menu, source form and draft tag chips.
There is one viewer implementation with responsive presentation, without another
router, framework, gesture dependency or competing file-operation owner.

- Desktop uses a large image stage and a 340px scrollable details sidebar. The
  sidebar can collapse; the viewer fits the available window rather than using
  the old narrow item modal.
- At the shell's existing 850px breakpoint, the dialog fills the dynamic viewport
  and respects safe areas. The image starts fitted with details closed. Details
  opens a flexible partial sheet, expands fully and closes through the outside
  scrim, handle gestures or Escape. Its own scroll container holds long filenames,
  metadata and tag collections; the covered image controls become inert.
- Compact controls provide zoom in/out, fit, download and details. Desktop also
  offers expanded image presentation. The top bar has a truncated filename,
  image position and one Close cross on the right. The overflow menu sits beside
  the Details title in place of the duplicate Close button. Archive/Restore and
  Delete appear in the menu; Download is not duplicated below an image. Existing
  document preview and download behavior remain available.
- Pinch and anchored 1–8x zoom, panning, double-tap, fit-only horizontal swipe and
  arrow/button navigation share the same image stage. Zoomed arrow keys pan;
  `+`/`-` zoom and `0`/`F` fit. Switching images resets the transform. Input and
  details interactions do not navigate the sequence. Closing restores the
  original Library location, scroll and focus, including refreshed item rows.
- Image pixels still come from authenticated, exact-revision 2048px derivatives;
  zoom does not trigger original-resolution transfers. Existing host image LRU,
  decoder bounds and original download behavior are unchanged. Metadata reuse
  has a 24-item/30-second bound, checked against known revisions and cleared on
  explicit refresh, operations and sign-out. Obsolete loads remain abortable.

All surfaces/text/chips/focus indicators use the existing primary, secondary,
tertiary, surface, outline and error roles. Roboto, local SVG paths, 44px controls,
existing 12/20/24/28px shape treatments, 150/280ms durations and standard easing
are reused. The details sheet delays hiding only during its close transition;
opening is immediately focusable. Reduced motion removes sheet transitions and
uses the existing reduced-motion dialog behavior. No separate reference palette,
favorite feature, Notes tab, invented folders or modification/capture dates were
introduced. Added is the only available timestamp.

## Details, links and reviewed changes

File details is a semantic name/value list. It contains full filename, type/MIME,
human-readable and exact byte size, dimensions where known, Added and archived
status where applicable. Link display and its initially hidden editor are inside
the bottom of that section; there is no separate Source heading. Links open only
on user activation, use `noopener noreferrer`, and have copy/edit controls.
The existing secure/LAN clipboard helper is reused inside the active dialog.

Source links did not exist in the model. The additive private `artifact_links`
table is created only on writes; legacy stores return an empty link without
migration during browsing. HTTP(S)-only values have a 2048-character bound and
reject credentials, whitespace/control characters, backslashes and invalid ports.
The fixed `source_link` review validates and captures the normalized value;
the owned worker rechecks artifact revision and saves under the existing resource
fence. Links are never fetched, do not replace the private origin, and are removed
with permanent artifact deletion. The browser detail DTO alone adds `source_url`;
inventory reads retain their earlier shape. Older hosts disable link editing with
restart guidance.

Manual/AI tags have distinct tonal chips and a count, initially showing at most
eight. Show more reveals the remaining bounded collection. Edit adds/removes draft
manual chips, while review still submits the original comma-separated semantics:
up to 20 printable tags of at most 40 characters, with existing deduplication and
AI/manual overlap handling. The permanent comma-separated input is gone. As
before, opening a mutation review closes the file preview; work starts only after
confirmation, and accepted operations continue through the existing owner.

Saved files offer Archive and Delete; archived files offer Restore and Delete.
Delete opens a Cancel-focused native confirmation without requiring archive,
names the irreversible operation and keeps the existing exact revision/effect
checks. Cancel performs no deletion. Menu arrow/Home/End/Tab/Escape/outside-click
behavior follows the existing chat popover convention. The Markdown browser test
now targets its specific message-menu ID so shared menu styling does not make it
inspect the Library's closed menu.

## Changed files for this redesign

- `apps/webhost/src/klaude_webhost/static/index.html`: shared dialog and source/tag
  forms, compact toolbar, details/sidebar/sheet and accessible review descriptions.
- `apps/webhost/src/klaude_webhost/static/library.js`: viewer presentation,
  gestures, details cache, menu/review integration and private-state cleanup.
- `apps/webhost/src/klaude_webhost/static/style.css`: scoped responsive preview
  layouts using existing Material tokens and motion.
- `apps/webhost/src/klaude_webhost/static/markdown.js`: expose the existing copy
  helper with an optional container for a native modal; current callers retain
  the existing default.
- `apps/webhost/src/klaude_webhost/host.py`: source-link capability advertisement.
- `packages/core/src/klaude_core/library_artifacts.py`: optional link metadata,
  validation and atomic revisioned changes/deletion cleanup.
- `packages/application/src/klaude_application/library_management.py`: bounded
  public link details and fixed reviewed source-link changes.
- `tests/unit/test_library_source_links.py` (new): validation, legacy reads,
  revisions, authenticated real owned-worker changes/removal and deletion cleanup.
- `tests/unit/test_web_library.py`: deliberate detail-only optional-field contract.
- `scripts/webui_image_preview_smoke.py` (new): dedicated real Chrome acceptance.
- `scripts/webui_markdown_smoke.py`: scope message menu checks by their actual ID.
- `AGENTS.md`, `README.md`, `CHANGELOG.md`, `docs/webui/coverage.md` and these
  preview planning/validation records.

No dependencies, lockfile changes or generated production assets were added.

## Verification and limits

Chrome emulation does not establish
physical Android/iOS behavior, screen-reader acceptance or full WCAG conformance.
Zoom uses the existing 2048px derivative, so deep zoom can be softer than the
original download. Animated files retain the existing frame-zero preview.
Original modification/capture dates, favorites, notes and bulk management remain
unsupported. The existing manual-tag and image-input limits are unchanged.

### Final results

- **175 focused Python tests passed in two runs:** 102 in 54.77s across source
  links, core artifacts, management operations, HTTP Library and image-browser
  regressions; 73 in 54.84s across the shared application Library, host/accounts,
  chat attachments and image preparation. This is not a full repository unit run.
- Repository Ruff, production mypy across **211 source files**, `node --check`
  for both changed JavaScript files and `git diff --check` passed.
- The final packaging smoke built and installed **all seven workspace wheels**,
  checked imports/bundled assets and ran both CLI help commands successfully.
  Log: `/tmp/klaude-image-preview-package-final.log`.
- The new real Chrome script passed 12 light/dark viewport combinations:
  1440×900, 1024×768, 768×1024, 390×844, 320×568 and 844×390. Screenshots cover
  collapsed/partial/full details, long filenames, 40 manual/AI tag chips and
  landscape/portrait/square images. Every fit screenshot asserts the image box
  stays inside the stage with `object-fit: contain`; toolbar targets remain at
  least 44×44px and dialogs/controls have no horizontal overflow.
- Trusted mouse, touch and keyboard input verified pinch/pan/swipe/double-tap,
  transform reset, sheet handle dragging, sheet focus/Escape, menu keyboard
  controls, metadata read reuse, source placement and real LAN clipboard fallback
  inside the native dialog. Real owned workers verified reviewed source saving,
  chip edits with AI tags present, archive, Delete cancellation for saved and
  archived files and confirmed deletion. Reduced motion, private-state cleanup,
  no external requests and **zero browser exceptions** passed.
- The existing Library browser, loading and Markdown Chrome scripts also passed.
  Library covers 1,058 files, 50 images and 24 mode/theme/viewport combinations,
  including page-crossing navigation and corrupt-image fallbacks. Loading covers
  stale/canceled previews and other Library/Knowledge/Skills surfaces. Markdown
  verifies the shared copy helper and message menu. Its successful fixture
  teardown logged one disconnected `/models/local` response (`BrokenPipeError`);
  there were no failed assertions or browser exceptions.
- Browser results: `/tmp/klaude-image-preview-result.json`,
  `/tmp/klaude-image-preview-library-final.json`,
  `/tmp/klaude-image-preview-loading-final.json` and
  `/tmp/klaude-image-preview-markdown.json`. Screenshots are in
  `/tmp/klaude-image-preview/`. Final visual inspection specifically corrected
  the portrait image's intrinsic grid sizing, and focus is kept on the stable
  image stage while navigation controls temporarily disable during loading.
- After an exact saved-runtime preflight and an idle/empty-queue check, the
  managed host was gracefully reloaded. Session ID, dialogue hash, model/ref,
  mode/effort/plan/settings revisions, workspace and LAN configuration were
  preserved. Source-link capability was verified live. No active turn was canceled.
- Live Chrome verified the user's existing lossless WebP as a **1598×1763**
  preview at 1440×900 (Lavender light/dark), 390×844 (Sage light), 320×568 and
  844×390 (Slate dark). Fit bounds, structured dimensions, enabled source editing,
  responsive details and restored focus passed with zero browser exceptions.
  The artifact metadata/checksum/revision remained unchanged; live tests did not
  edit tags/links, archive or delete user files. Results/screenshots:
  `/tmp/klaude-image-preview-live-result.json` and
  `/tmp/klaude-image-preview-live/`.
- Existing uncommitted work and all reference files remain preserved. No
  commit/push was performed. Browsers need to refresh and sign in again after
  the graceful host reload.

## Direct file deletion (2026-10-21)

- Saved and archived Library files both offer Delete, including images,
  documents and Research reports. The viewer, review preparation and shared
  storage effect no longer require archiving first. The Cancel-focused permanent
  deletion review and exact revision check remain in place. Original workspace
  files and independent exported copies remain untouched.
- Focused Library artifact, management and HTTP regression tests passed:
  **87 passed in 54.61 seconds**. Coverage includes direct deletion for all three
  stored kinds, cancellation, changed-file rejection and duplicate HTTP receipts.
- The Chrome viewer smoke passed with actual PNG/WebP fixtures and owned workers:
  saved-image and document deletion, saved/archived Delete cancellation, confirmed
  archived deletion, existing viewer gestures, light/dark responsive layouts and
  logout cleanup. It reported zero browser exceptions or external requests.
- Focused Ruff, JavaScript syntax, Python compilation and `git diff --check`
  passed. This is focused validation rather than a full repository suite.
- After verifying no active chat work or Library operations, the managed host
  was gracefully reloaded. Selected conversation, public dialogue, exact runtime,
  workspace, loopback/LAN listeners and saved hosting preferences were preserved.
  No real-profile files were deleted as probes. Refresh and sign in again to use
  the updated host.

## Preview header controls (2026-10-21)

- Image and file previews use one Close cross at the far right of the main
  header. File options moved to the Details title row, replacing its duplicate
  Close button. Opening Details focuses its handle; hiding Details also dismisses
  its menu. Sheet scrim, Escape and drag dismissal remain available.
- Both isolated Chrome acceptance scripts passed with zero browser exceptions
  or external requests. Image checks covered 12 light/dark viewport combinations,
  menu placement and keyboard dismissal, sheet focus/gestures and reviewed file
  actions. File checks covered 16 source layouts, eight Markdown layouts, exact
  copying, complete downloads and existing preview safeguards.
- Desktop and phone screenshots were inspected. Focused Ruff, JavaScript syntax,
  Python compilation and `git diff --check` passed. This is focused validation,
  not a full repository test run. Results: `/tmp/klaude-preview-header-images.json`
  and `/tmp/klaude-preview-header-files.json`.
- Refresh the browser to load these static asset changes; no host restart is
  required.
