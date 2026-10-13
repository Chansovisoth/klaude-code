# S4a — Explicit Knowledge actions and validation

Date: 2026-10-13. This completes the remaining S4a Knowledge consumers after the
[Library foundation](s4a-library-validation.md) and
[Documents/Media slice](s4a-artifacts-validation.md). The
[phase plan](odysseus-settings-and-features-plan.md#s4--library-then-deep-research)
then proceeded to S4b Deep Research. S4b, S5 and S6 were not started in this
Knowledge slice. The subsequent [S4b validation](s4b-deep-research-validation.md)
completes S4.

## Delivered behavior

- Library → Knowledge puts **Learn source…**, **Managed sources** and Reload
  above the inventory. Existing-library details retain **Search indexed text**
  and add **Learn source…**, **Hybrid query…** and **Managed sources**.
- Ordinary inventories and indexed-text search remain read-only, with no model,
  embedding, index-write or new-store work. Hybrid query is a separate explicit
  action using the existing embedding/vector/FTS/validation service. It returns
  up to six bounded source excerpts without chat generation.
- Learning accepts one regular UTF-8 file or public HTTP(S) page and an explicit
  destination knowledge library. Private single-line editors do not create chat
  turns. A review shows source, library, embedding model and indexing effects,
  with Back initially focused. Merely entering or cancelling a review does no
  network, embedding or indexing work.
- Local sources reject symlink paths, binary text, changing files and content
  above 2 MiB. Originals and independently stored document/media copies remain
  unchanged. Identical source content skips re-embedding and re-indexing.
- Managed sources lists existing docs/crawl definitions without network calls.
  Refresh reviews the selected definition, preserves its library and crawl/page
  settings, and fetches fresh content through the existing web safety/fetch layer.
  It bypasses page/turn caches rather than re-indexing a cached copy.
- Learning and refresh retain the existing shared source-owner and atomic
  replacement semantics. Partial, oversized or failed refreshes do not replace
  the previous active indexed snapshot. Changed definitions are rejected before
  publication. Replacement content is never silently truncated to fit a limit.
- New action controls precede inventories and hybrid-query hits; excerpts scroll
  from their beginning. Back,
  repeated queries and page-local filtering preserve the intended destination.
  Two-column counts use available width instead of reserving a blank description
  column. Panels use one text/cursor render snapshot when the terminal resizes.
- Success uses green, failures red and uncertain outcomes yellow; query/unchanged
  acknowledgements stay neutral. Live spinner/elapsed state and ordinary
  queue/context counters remain visible while work runs.

**Stored ≠ indexed; Imported ≠ learned; Archived ≠ deleted.** Existing learned
library IDs, CLI `learn`, `query`, `docs`, `libraries`, `collections` and their
compatibility flags retain their meaning. No automatic artifact learning was added.

## Execution ownership and bounds

- `library_knowledge_panel.py` owns typed interaction/task state;
  `library_knowledge.py` owns the fixed worker operation. `library_workspace.py`
  retains common Library navigation and the existing bounded read lane.
- Tasks reuse `OwnedBackgroundJobs` and `background_worker.py`, with a five-minute
  outer deadline and bounded private request/result pipes. The configuration,
  workspace, native embedding role and public retrieval settings are captured at
  acceptance; private provider values remain in the worker pipe.
- Embedding requests have a 30-second timeout and batches of at most 16; indexing
  is capped at 1,000 chunks. Learning text is capped at 2 MiB and refresh at 8 MiB
  cumulative text, including crawl fetches. These are TUI operation bounds; the
  existing CLI limits were not changed. No chat generation or cloud embedding
  fallback is introduced.
- Starting requires idle model/setup/skill work. Accepted work survives ordinary
  Library navigation and pauses model queue consumption. A cross-client task
  lock serializes these TUI operations; existing CLI/model concurrency remains
  owned by those services.
- Cancel, `/cancel` and Ctrl+C stop and reap the owned process before releasing
  the busy state. The optional cancellation acknowledgement does not change
  other background jobs' default event behavior. Feedback explicitly states that
  completed indexing may remain; cancellation is not a rollback guarantee.
- Task return state and definition identities are captured. Late results cannot
  replace another session/store's state or steal unrelated navigation. Failed or
  timed-out work asks for Reload rather than claiming success or retrying writes.
- CLI and TUI share `klaude_knowledge.docs.index_installed_docs`, including atomic
  owner replacement and manifest finalization. Pending-source recovery now
  requires exact active source checksums; matching URL names alone is insufficient.

## Problems observed and root causes corrected

1. Refresh could receive previously cached content from the normal fetch path.
   Added explicit fresh fetching through the same guarded fetch cascade; ordinary
   cached agent fetching remains unchanged.
2. Recovery compared pending and active URL sets without proving that the new
   content had reached the index. An interrupted same-URL update could finalize
   an unindexed version. Compare exact active owner checksums before recovery
   finalization and cover both interrupted and completed activation.
3. Repeated hybrid-query and managed-source Back navigation retained the wrong
   parent. Capture operation and source-list parents separately. Clear the
   navigation filter when a submitted query opens its result page so it cannot
   conceal new results.
4. Resizing long results caused an actual Prompt Toolkit `list index out of range`
   crash: cached rendered lines and a separately recalculated cursor used
   different widths. Compute both from one body render. The fix applies to the
   shared Settings/Library panel control, with a resize regression case.
5. Operation progress was absent from the ordinary activity state. Integrate
   Knowledge work into live spinner/elapsed status, cancellation and queue
   consumption without inserting task inputs/results into model context.
6. Knowledge counts wrapped while a reserved description column stayed empty.
   Let two-column inventories use the remaining width for values; verify counts
   stay on one line at 70 and 120 columns. Learning review text now describes
   learning; refresh-specific wording is confined to refresh reviews.

Incomplete and failed runs are not counted as successful validation. The first
focused run had fixture configuration/expectation problems, which were corrected.
The first full gate reported **1 failed, 2,819 passed, 19 skipped** because an old
test inspected the moved helper's implementation text. Replace it with a
behavioral shared-owner test. Early real walkthroughs exposed the resize crash
and retained query filter; both were repaired before completed reruns.

## Real CLI/TUI evidence

Session: **TEST KLAUDE FEATURES KNOWLEDGE ACTIONS**. The real bare `klaude` process
runs in a PTY with isolated project/config/data, real LanceDB/FTS/indexing and a
local native embedding protocol fixture. Managed-source refresh uses the actual
public CPython README at
`https://raw.githubusercontent.com/python/cpython/3.13/README.rst`.

The completed walkthrough verifies:

1. Private source/library entry, Back-focused review and cancelled review with
   no embedding or implicit artifact learning.
2. Real file learning, unchanged-source embedding skip, hybrid retrieval and a
   repeated query returning to the original library detail.
3. Missing-source feedback and natural return to a new review.
4. Cancellation during delayed embedding, cleanup acknowledgement and retention
   of the prior active knowledge rather than the cancelled replacement.
5. Fresh public-source refresh, real indexed replacement of the old canary and
   working source-detail/list/library Back navigation.
6. Long-result resize at **40, 70 and 120 columns**, followed by clean `/exit`.
7. Independent artifact content, **zero generation requests**, **six embedding
   requests**, observed maximum embedding batch **one**, and exit code **0**.

Driver: `/tmp/klaude_s4_knowledge_walkthrough.py`. Final evidence:
`.klaude/data/s2-models-vbwqd2_0/knowledge-result.json`, with terminal text/SVG
captures alongside it (ignored local QA data). Log:
`/tmp/klaude-s4-knowledge-acceptance-live.log`. Result: **passed**.
Earlier completed runs are `s2-models-n_9aveia`, `s2-models-2k1qgbe0` and
`s2-models-b5oecof6`. Visual inspection covered the final inventory, learning review
and narrow result layout. General chat chrome remains cramped at 40 columns.

This certifies real CLI/TUI, indexing/retrieval and public fetch transport with a
deterministic embedding protocol fixture. It does **not** certify an embedding
model's semantic quality, GPU behavior, live cloud generation or every terminal.

## Automated regression gate

- **26 Knowledge cases** cover shared learning/query ownership, idempotence,
  binary/symlink/byte/chunk limits, metadata-only inventory, unavailable records,
  stale definitions, partial/fresh fetch, cumulative crawl bounds, checksum-based
  recovery, private reviews, cancellation acknowledgement, stale result scope,
  queue/activity, Back/filter behavior, resize and two-column width allocation.
- Final frozen/offline `make check` with isolated config/data and local runtime:
  **2,823 passed, 19 skipped in 157.69s**. Ruff passed; production mypy passed
  over **110 source files**. Log: `/tmp/klaude-s4-knowledge-acceptance-check.log`.
  Earlier successful full gates had 2,822 tests before the final count-width case.
- Final frozen/offline `make package-smoke`: **passed**, all five wheels built
  and installed together, public imports and installed `klaude --help` checked.
  Log: `/tmp/klaude-s4-knowledge-acceptance-package.log`.
- `git diff --check` and the baseline preservation audit passed. The audit uses
  the hashes of **80 pre-existing dirty files**, lists this slice's intentional
  changes/new files, and verifies no baseline file disappeared or changed outside
  the slice. Audit: `/tmp/klaude-s4-knowledge-worktree-audit.json`.
  No commit, push, reset or stash was performed.
- These are local checks. The existing 19 skips remain; GitHub's Python
  3.11–3.13 matrix was not run for this uncommitted slice. The full local suite
  covers the prior provider, tool-loop, permission and reliability fixes.

## Remaining limits and next step

- Learning here supports one UTF-8 source, not folders, PDFs or implicit stored
  artifact ingestion. Docs/crawl installation forms remain existing CLI flows;
  this slice adds review/refresh of installed definitions.
- Managed-source inventory inspects at most 1,000 directories, with 100-record
  pages and explicit bounded/unavailable feedback. Query inputs are capped at
  200 characters and returned excerpts at 1,200 characters per hit.
- Slow/large embedding tasks can exceed the five-minute deadline. Cancellation
  cannot guarantee remote request cancellation or undo completed activation.
  Reload verifies current indexed state after uncertain termination.
- Partial source refresh rejects the whole replacement. The prior active index
  stays usable; already downloaded pending versions may remain for recovery.
- Existing CLI/model indexing is not serialized by the TUI task lock; shared
  index services retain their existing atomic activation guarantees. There is
  no new general index-job coordinator or automatic migration of embedding roles.
- **S4a is complete locally. Next: S4b Deep Research** — form/defaults,
  canonical-runtime owned jobs, source/citation evidence, bounded cancellation
  and recovery, saved-report browsing and explicit discussion. S5 Model Manager
  and S6 vision/generation remain outside this pass.
