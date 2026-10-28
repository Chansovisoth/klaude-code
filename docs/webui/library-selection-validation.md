# Library selection validation

Uploads and Generated have an Edit icon immediately before Refresh. Edit enables
toggle selection in List, Grid and Gallery with a floating bottom bar showing the
selected count, Delete and exit. Selected thumbnails show a centered checkmark over a
dark translucent overlay; unselected thumbnails have no selection mark. Selection persists across
pages, sorting and view changes,
up to 100 files. Changing section, search or type/status filters, leaving Library,
browser history navigation and sign-out clear it. Folder moves remain deferred.
In edit mode, holding the left mouse button and dragging selects or deselects a
range on the current page. Reversing the drag restores the previous selection;
Shift-click extends from the last selected anchor, and dragging near the Library
edges scrolls its file list. Touch and keyboard interactions remain available.

Delete uses the existing owner-authenticated review, control fencing and durable
operation receipt. The review captures exact names, IDs and revisions. The owned
worker verifies every revision under one SQLite write transaction before deleting
any selected file. A changed or missing file rejects the entire selection. Unknown
outcomes retain their journal fence. Batch admission waits for outstanding
operations, and artifact changes cannot bypass an outstanding batch fence.
Older hosts disable Edit with restart guidance.

Validated with isolated profiles and fixture data on 2026-10-28:

- `tests/unit/test_web_library.py`, `tests/unit/test_library_artifacts.py` and
  `tests/unit/test_library_management.py`: **107 passed**. Coverage includes
  cancellation, exact revisions, atomic rejection, request deduplication,
  malformed/bounded selections and admission conflicts in both directions.
- `scripts/webui_library_selection_smoke.py`: Chrome passed keyboard selection,
  mouse range selection, reversal, deselection, Shift-click, thumbnail dragging,
  edge scrolling, selection across pages, cancel/confirm deletion, Generated/Uploads separation,
  search/navigation/sign-out cleanup and the older-host fallback. List/Grid/Gallery
  fit at 1440, 768, 390 and 320px in actual light and dark appearance modes, with
  44px action targets and no browser exceptions. Screenshots are in
  `/tmp/klaude-library-selection-evidence`.
- Scoped Ruff, JavaScript syntax, mypy for the artifact store and management
  service, and `git diff --check` passed. The focused HTTP tests ran outside the
  socket-restricted sandbox with approval. A pre-existing Ruff line-length error
  in `host.py:400` remains outside this change.

The full suite and production host restart were not performed.
