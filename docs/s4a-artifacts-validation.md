# S4a — Documents and Media artifact validation

Date: 2026-10-13. This follows the [Library foundation](s4a-library-validation.md)
and implements the Documents/Media slice of the
[S4 plan](odysseus-settings-and-features-plan.md#s4--library-then-deep-research).
The subsequent [Knowledge action slice](s4a-knowledge-validation.md) supplies
S4a's explicit Knowledge TUI consumers. S4b research jobs and the Research report
browser, S5 Model Manager and S6 vision/generation were not started at that
checkpoint. The subsequent [S4b validation](s4b-deep-research-validation.md)
completes research jobs and report consumers.

## Delivered behavior

- Keep the exact root order: Sessions, Knowledge, Documents, Research, Media,
  Archive. Existing learned-library IDs, `libraries`, `collections`, `query`,
  `learn`, managed-source owners, sessions and recall retain their meaning.
- Documents and Media import one regular file as a private managed copy, up to
  32 MiB. Originals remain untouched. Import and browse do not call a model,
  embed/index content or insert it into model/chat history.
- Metadata search covers names, manual tags, MIME types and origin paths. Lists
  have 100-record pages, newest/oldest/name sorting and type filters. `/` still
  filters the loaded page; submitting Search metadata clears that navigation
  filter so it cannot conceal the newly searched store results.
- Details show name, MIME/size, available image dimensions, source/import date,
  exact typed ID, manual tags and known session/job/model associations. TUI imports
  capture the actual session; generation/model provenance remains unknown.
  Actions appear above extended metadata, which scrolls independently.
- Text previews are bounded to 16 KiB, 100 lines and 500 characters per line,
  strip terminal controls and report truncation. Long previews open at the start.
  Binary files have an explicit export/open fallback.
- Media accepts PNG/JPEG/GIF/WebP headers. Dimensions are read from bounded
  headers where supported, without full decoding, EXIF parsing, vision or generation.
  Preview uses dimensions plus export/open fallback; terminal image protocols and
  full image validity verification are not implemented in this slice.
- Edit tags is a private single-line editor: at most 20 distinct printable tags,
  40 characters each. Blank removes all tags. No AI tagging is implied.
- Export creates a new owner-only file inside the active workspace. Existing
  files, symlink paths and paths outside that workspace are rejected. It streams
  the exact stored bytes, verifies their checksum and removes partial exports
  on failure. Export directories must already exist.
- Open externally invokes a fixed desktop opener without a shell, with a
  five-second deadline and safe filename extensions. It creates a private viewer
  copy and retains it for asynchronous readers. The cache is capped at eight
  copies; headless/unavailable/failed open reports a fallback to Export. Desktop
  success here is mocked, not certified against a live GUI application.
- Archive → Documents and Media searches supported archived artifact types,
  restores content/tags and separately confirms permanent deletion with Back
  initially focused. Originals, exported/opened copies and learned knowledge
  remain independent. Current-record revisions reject stale changes and deletion
  confirmations after another client restores an artifact.
- `klaude library list/import/info/export/tags/archive/restore/delete` exposes
  matching explicit operations, canonical help and failure exit codes.
  `klaude libraries` continues to list named knowledge libraries. To learn a
  stored document explicitly, export it and use the existing learn command.

**Stored ≠ indexed; Imported ≠ learned; Archived ≠ deleted.**

## Implementation and ownership

- Core `library_artifacts.py` owns `data/library/artifacts.db`, with owner-only
  directory/database permissions. Immutable content and bounded metadata share
  one SQLite transaction, avoiding metadata/content publication mismatches.
  IDs distinguish `document:…`, `media:…` and future `research:…` records.
- Listings select metadata only. Missing-store browsing creates no directories or
  database. Existing Library read jobs retain their eight-second outer deadline,
  200ms SQLite busy timeout, three-second query deadline, bounded result pipe,
  30-second/16-entry snapshot cache and session/request-scoped stale rejection.
- `library_artifact_panel.py` owns typed Documents/Media interaction state;
  `library_workspace.py` keeps shared navigation, jobs and draft/Back behavior.
  `library_commands.py` exposes CLI consumers; `main.py` adds registry/event wiring.
- Writes reuse `SessionActionWriter`, with captured store/session/target/revision
  and workspace identities. No second permission, preferences or model store was
  added. Accepted writes survive navigation; late acknowledgements cannot publish
  into another store/session or jump into an unrelated record. Private input and
  source bytes are not included in action acknowledgements or chat messages.
- The `store_report` primitive stores Markdown plus known job/session/model
  references. It does not generate reports, validate citations, checkpoint jobs
  or supply replayable source evidence. Those consumers remain S4b work.

## Problems found through real use and corrected

1. Manual-tag metadata and Edit tags shared a row ID. The real TUI rejected the
   detail page. Give metadata/actions separate IDs and assert detail publication.
2. Long metadata pushed useful actions below the initial viewport. Put a concise
   summary and actions first, followed by scrollable extended metadata.
3. Long previews initially focused a Reload row after the content, showing the
   end of the excerpt. Put preview controls first so the viewport starts at the
   beginning; add a focused-line regression assertion.
4. Opening Search metadata through `/` left its navigation filter active and
   concealed store results. Clear that filter when submitting the explicit search;
   apply the same correction to full-store session search.
5. A single long text line was shortened without truncation feedback. Include
   per-line shortening in the truncation result and describe all preview bounds.
6. Reject control characters in explicit export destinations before any file is
   created or its path is echoed in the TUI/CLI.

Incomplete runs are not counted as successful product validation. The first
focused run also used sandboxed LanceDB and did not finish; it was stopped and
rerun with the local runtime available. A test-driver tag case accidentally used
duplicate tags instead of 21 distinct tags and was corrected. Two later driver
assertions expected off-screen text, and its final lookup assumed a navigation-only
session had public turns. The driver was corrected; these are separate from the
actual row-ID, viewport and search-filter bugs above.

## Real CLI/TUI evidence

Session: **TEST KLAUDE FEATURES LIBRARY ARTIFACTS**. Run a real bare `klaude`
process through a 40-row PTY in an isolated project/config/data directory, with
real SQLite and a seeded LanceDB/FTS knowledge source. A localhost provider fixture
counts generation requests; browsing/importing artifacts requires none.

The walkthrough verifies:

1. Managed document import with the actual session association and unknown model
   provenance; original-byte hashes remain unchanged.
2. Private tag editing, metadata/tag search, bounded document preview, headless
   external-open feedback, existing-file/path-boundary export failures and exact
   successful export bytes.
3. Archive, retained content, Back-focused deletion cancellation and restore.
4. Image import, header dimensions, binary preview fallback, manual tags and type
   filter; image export preserves exact bytes without a vision model.
5. Wrapped Documents/Media layouts at 40, 70 and 120 columns, with controls above
   tables. Existing general chat chrome remains cramped at 40 columns; reduced
   terminal heights and all terminal image protocols are not certified.
6. Actual CLI import/list/info/tags/archive/restore/export, plus cancelled and
   confirmed permanent deletion of a disposable copy. CLI/TUI exit code is zero.
7. Zero model generation requests, unchanged knowledge-file hashes and no document
   contents in the navigation-only session's public history.

Driver: `/tmp/klaude_s4_artifact_walkthrough.py`. The final completed run is
recorded in `.klaude/data/s2-models-rb2ohzf0/artifact-result.json`; terminal
text/SVG captures and CLI outputs are alongside it (ignored local QA data).
Log: `/tmp/klaude-s4-artifacts-verified-live.log`. Final result: **passed**,
exit code **0**, generation requests **0**, original/knowledge hashes unchanged.
An earlier completed run is `.klaude/data/s2-models-_h5qesly/artifact-result.json`.
Visual inspection covered the wrapped list at 40/120 columns, action-first
document detail and image-metadata preview; the PTY driver also exercised 70 columns.

## Automated regression validation

- **30 artifact cases** cover import independence, private modes, immutable bytes,
  bounded/truncated previews, metadata/tag/type search, sorting/paging, archive
  retention, stale deletion, invalid tags/IDs, symlinks/hardlinks/FIFOs/size bounds,
  export jail/no-overwrite/checksum cleanup, transactional rollback, headless and
  mocked desktop behavior, ordered action acknowledgements, private editors,
  search/Back/focus, confirmation defaults, wrapped widths and CLI exit codes.
- Earlier focused Library/artifact run: **47 passed** in 10.45s. Later cases were
  included in the final full suite; focused validation alone was not the gate.
- Final frozen/offline `make check`, with isolated config/data and local runtime
  available: **2,797 passed, 19 skipped in 147.83s**; Ruff passed; production mypy
  passed over **108 source files**. Log:
  `/tmp/klaude-s4-artifacts-verified-check.log`. Previous local final run passed
  2,796 tests before the last long-line preview case was added.
- Frozen/offline `make package-smoke`: **passed**, all five wheels built, installed
  together, public imports and installed `klaude --help` checked. Log:
  `/tmp/klaude-s4-artifacts-verified-package.log`.
- `git diff --check` passed. Baseline audit of 75 pre-existing dirty files found
  ten intentional changes, five new slice files, no unexpected changes and no
  missing original files. Audit: `/tmp/klaude-s4-artifacts-worktree-audit.json`.
  No commit, push, reset, stash or unrelated changes were made.
- These are local results; GitHub's Python 3.11–3.13 matrix was not run in this
  uncommitted slice. Existing reliability behavior remains covered by the full
  local suite, without claiming new live model-capability or cloud certification.

## Remaining work and limits

- Knowledge TUI consumers were pending at this artifact checkpoint and are supplied
  by the linked Knowledge slice.
- S4b research form/defaults, canonical-runtime owned jobs, supported citations,
  cancellation/recovery, source evidence and saved-report view/discuss actions.
- Source filters currently use metadata search over origin paths; dedicated
  source facets, image rendering protocols, folder imports and document editing
  are not implemented. Imported images have only available header dimensions;
  unsupported/missing dimensions remain unknown.
- Import/export perform bounded local I/O on the ordered action lane; accepted
  writes are not interruptible. Shutdown retains the existing two-second drain,
  rather than introducing a new worker lifecycle. Slow filesystems can exceed it.
- Viewer copies are retained until removed from the private opened-copy directory;
  the eight-copy cap fails explicitly and suggests Export. No automatic deletion
  of files a desktop application may still read is attempted.
- Permanent deletion removes the stored record/content from the product; it is
  not a disk sanitization guarantee, and SQLite freed pages may retain data.
- Desktop success paths are mocked. Actual headless behavior, managed local stores,
  CLI/TUI navigation and zero model/indexing work are verified separately.

Do not mark all S4 complete from the Library slices. The linked Knowledge
consumers complete S4a locally; continue S4b. S5 and S6 remain outside this pass.
