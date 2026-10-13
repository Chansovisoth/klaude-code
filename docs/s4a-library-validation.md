# S4a — Library foundation validation

Date: 2026-10-13. This document records the Sessions/Knowledge/session Archive
foundation. The subsequent [Documents/Media artifact slice](s4a-artifacts-validation.md)
adds managed-copy/report storage and artifact lifecycle support. **S4a is complete
locally** following the [explicit Knowledge action slice](s4a-knowledge-validation.md).
S4b Deep Research, S5 Model Manager and S6 were not started at that checkpoint.
The subsequent [S4b validation](s4b-deep-research-validation.md) completes S4.
This corrects two earlier “S4 Model Manager” handoff sentences; the phase table
has always assigned Library/Deep Research to S4 and Model Manager to S5.

## Delivered behavior

- `/library [VIEW]` opens the durable-information workspace outside Settings:
  Sessions, Knowledge, Documents, Research, Media, Archive, in that exact order.
  At this foundation checkpoint, unfinished views showed their status and exposed
  no import/model actions; the linked artifact slice adds Documents and Media.
- Sessions: searchable 100-record pages, stable IDs, names/timestamps/turn counts,
  current/active badges, last-eight public-turn previews and existing resume flow.
  `/` filters the loaded page; **Search all sessions** searches the store's public
  conversation text/names. Paging provides access beyond the first 100 records.
- Knowledge: existing library IDs, active-source counts and local indexed-text
  search. Retired versions and disabled skill sources are excluded. This keyword
  browser is distinct from the existing hybrid `klaude query` command, which
  retains embedding/relevance behavior. Learn/query/docs commands remain visible
  in detail; their TUI action consumers were pending at this foundation checkpoint
  and are supplied by the linked Knowledge slice.
- Archive changes normal browsing visibility, preserving turns, separate model
  content, names, events and configured episodic recall. Restore is explicit.
  Permanent deletion is separately confirmed, initially focusing Back, and removes
  only that conversation's records. Durable memories and learned knowledge remain.
- CLI: `klaude sessions archive SESSION_ID`, `klaude sessions --archived`,
  `klaude sessions restore SESSION_ID`. Invalid/stale lifecycle actions exit 1.
  Legacy libraries/collections/query/learn/session-search and delete/clear remain.

## Architecture and corrections

- `library_workspace.py` owns typed navigation and interaction state; main.py adds
  command/event/editor wiring using the canonical registry and existing panels.
  Reload/search controls precede table headings. Rows wrap to terminal width;
  parent filters/focus, unsent drafts and terminal scrollback use the common lifecycle.
- `library_inventory.py` reads existing SQLite/Lance directory metadata without
  constructing or migrating stores. Owned worker jobs have an eight-second outer
  deadline, 200ms SQLite busy timeout, three-second SQL progress deadline, bounded
  pages/excerpts and a bounded 30-second snapshot cache. Failed reloads retain the
  last successful snapshot's timestamp. Stale/session-switched results are rejected.
- Decode JSON string content before bounding previews; slicing encoded JSON first
  broke long/Unicode text and could expose partial structured attachment blocks.
  Previews/search never read `model_content`; structured attachment content is not
  projected into the browser. Control characters are removed from display text.
- Archive adds one metadata table to the existing session database. State checks,
  transitions and worker leases share `BEGIN IMMEDIATE`, preventing archive/worker
  races. A stale deletion cannot remove a session another client restored. Current
  sessions are protected in Library; idle clients affected by CLI archive recover
  their unrun prompt rather than waiting for a nonexistent remote worker.
- Writes use `SessionActionWriter`'s existing ordered lane and captured identities;
  accepted actions survive navigation, and acknowledgements do not jump to a later
  unrelated page. Storage failures report unconfirmed, avoid private diagnostics,
  and are never blindly retried.
- Visual inspection caught a retained “Loading Library…” footer after completion;
  successful publication now clears it. Long labels/badges use wrapped table rows,
  and single-turn counts use singular text. Library footer hints omit irrelevant
  Space-toggle instructions and shorten at narrow widths.

## Real CLI/TUI evidence

Session: **TEST KLAUDE FEATURES LIBRARY**. A real `klaude` process ran through a
PTY in an isolated workspace/config/data directory, with real SQLite conversations
and a real LanceDB/FTS knowledge source seeded with fixed vectors. A localhost
provider fixture counted generation requests; no model generation was needed.

Final artifact: `.klaude/data/s2-models-nwsxykhn/library-result.json` (local ignored
QA data). Driver: `/tmp/klaude_s4_library_walkthrough.py`. Terminal captures beside
the artifact record the home, inventories, full-store search, preview, confirmation,
knowledge results, paging, current-session protection and resumed transcript.

Final layout follow-up: **TEST KLAUDE FEATURES LIBRARY LAYOUT**,
`.klaude/data/s2-models-96a9jymy/layout-result.json`. Actual 40/70/120-column PTY
checks confirmed controls precede table headings, loading feedback clears after
publication, irrelevant Space hints are absent, and no generation occurs.
The temporary driver's first prefix extraction had a syntax error before launching
Klaude; it was fixed and rerun successfully. Exit code: **0**; model requests: **0**.

Verified:

1. 105 seeded conversations plus named records: search, next/previous pages,
   detail, recent public turns and Unicode name handling.
2. Archive preserves exact saved turns, including separate private attachment
   content; cancel deletion on Back; restore preserves turns/events.
3. Confirm deletion of a separate disposable archived conversation.
4. Search a real indexed source without generation or embedding calls; inspect
   captures at 120, 70 and 40 columns.
5. Resume through the existing session flow, display public transcript only, and
   prevent archiving the currently open session.
6. CLI archive/list/restore exits successfully, and **all knowledge-file hashes
   remain unchanged**. Generation requests: **0**. TUI exit code: **0**.

The first driver stopped because it expected the parent filter to disappear on
Back; it was corrected to clear the intentionally retained filter. An intermediate
run used a long-title exact-text assertion that failed when the Current badge
caused truncation; wrapped tables addressed the actual readability issue. These
incomplete runs are not counted as successful validation.

## Automated regression validation

- 22 Library tests: archive/restore retention, recall compatibility,
  cross-client leases/state, stale confirmations, deletion/clear metadata,
  paging/search/privacy, legacy/missing/read-only stores, active/disabled knowledge
  sources, ordered actions, navigation/draft/filter preservation, stale jobs,
  40/70/120-column body rendering, CLI outcomes, long/structured previews, loading
  feedback, private editors, save failure, externally archived-client recovery and
  truthful empty later pages. The first 21 passed in the focused run;
  `/tmp/klaude-s4-final-focused.log`. All 22 are included in the final full suite.
- Expanded Library/CLI regression run before the final three edge cases:
  `/tmp/klaude-s4-focused-expanded.log`: **864 passed, 1 skipped**.
- The first complete suite found the canonical-command regression test still
  expecting only Delete/Clear. It is updated to cover Archive/Restore/`--archived`.
  That run (**1 failed, 2759 passed, 19 skipped**) is retained as failure evidence.
- Final locked `make check`: `/tmp/klaude-s4-final-check.log`, **2767 passed,
  19 skipped** in 153.30 seconds; Ruff passed and production mypy passed over
  **105 source files**. This includes all 22 Library cases and the previous
  cancellation, protocol recovery, session/lease, settings, provider and tool tests.
- Five-wheel packaging: `/tmp/klaude-s4-package.log`, `make package-smoke`
  **passed**: wheel builds, isolated install, package imports and installed CLI help.
  No paid-cloud or local-model capability claims come from this pass.

Worktree review compared all 71 initially dirty file hashes with the pre-edit
snapshot `/tmp/klaude-s4-baseline.json`. Nine existing files changed intentionally;
four Library-specific files were added. No initial files disappeared or unrelated
dirty files changed. No commit, push, reset, stash or discard was performed.

## Remaining work

- Documents/Media workflows and report storage were pending at this foundation
  checkpoint and are implemented in the linked artifact slice.
- Explicit TUI learn/hybrid-query/refresh consumers were pending at this foundation
  checkpoint and are supplied by the linked Knowledge slice.
- S4b research jobs, defaults, bounded checkpoints/cancellation and sourced reports.
- Knowledge inventory is capped at 1000 libraries and search at 20 excerpts;
  session browsing is paged. Keyword search does not replace semantic retrieval.
- Browsing uses snapshots and explicit Reload, not a continuous live inventory.
  The legacy `/resume` picker and CLI store constructors keep their existing I/O
  paths; this slice moves the new Library navigation reads into owned workers.
- At 40 columns the Library body wraps correctly, while existing overall chat
  status/composer chrome remains cramped. Reduced-height live terminals and actual
  model generation were not certified by this storage/navigation pass.

The full S4 research acceptance gate is pending. **Stored ≠ indexed;
Imported ≠ learned; Archived ≠ deleted** remain independent product contracts.
