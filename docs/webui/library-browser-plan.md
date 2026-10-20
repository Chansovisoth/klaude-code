# Library file browser implementation

Baseline: 763cff9, synchronized with origin/main on 2026-10-20. The three local
Solid Explorer screenshots were inspected before implementation. Preserve those
untracked references and all existing Library actions.

## Architecture and constraints

- Vanilla JavaScript/DOM (`static/library.js`), local SVG paths, Roboto and existing
  Material 3 color/shape/motion tokens; no frontend framework or icon dependency.
- `LibraryManagement` projects an SQLite artifact inventory, filtered before
  bounded pagination. Browser routes authenticate the local owner and preserve
  revision/hash checks. CLI/TUI share this store and retain their existing batches.
- Files stores private copies, not a directory tree. There are no folders to
  navigate or synthesize. Breadcrumbs show Library → Uploads or Library → Generated;
  type/status remain filters. Workspaces is the separate filesystem browser.
- Only `created` (time added) is available. Dates and gallery groups say Added;
  do not present it as modified time or EXIF capture time.
- Existing text/image details, download, tags, archive/restore/delete and reviewed
  imports remain the action surface. Existing pagination and native dialogs are
  reused. The disposable resource-limited image decoder supports derivatives.
- Existing sessionStorage navigation preferences remain the persistence seam.
  Library URL query/history entries encode section, mode, search, sort, filters
  and page; URL state is authoritative when present, otherwise stored preferences.

## Implementation slices

1. Shared toolbar, icons, view state/history, honest metadata and expanded sorts.
2. Compact List and Grid presentations, retaining exact existing actions.
3. Image-only Gallery grouped by month added for date sorts; expanded preview
   with keyboard/touch previous/next, including page boundaries.
4. Authenticated thumbnail/preview derivatives with bounded cache and decoding;
   reject arbitrary paths, unsupported data, stale revisions and revoked owners.
5. Verify search/filter-before-page behavior, cancellation, bounded requests,
   existing operations, all views/themes and 320/390/768/1440 layouts in Chrome.

## Progress

- Investigation complete; no folder/modified-date functionality assumed.
- Shared structure, all three views, state/history, derivatives and image viewer
  implemented. No new dependencies or folder/modified-date assumptions.
- 153 focused regressions, Ruff, 211-file production mypy and seven-wheel package
  smoke passed. Both Chrome scripts passed; the new browser fixture has 1,058
  files and 50 images, covering 24 mode/theme/viewport combinations.
- The live host was preserved while its chat turn was active, then gracefully
  reloaded after it became idle. Its exact session, dialogue, settings, workspace
  and LAN address were retained. Live Chrome verified the existing WebP gallery
  thumbnail, expanded preview and reload at desktop/phone widths. Updated assets
  also retain compatible behavior if served by an older host in the future.
- Details, scope limits and changed-file manifest:
  [library-browser-validation.md](library-browser-validation.md).
- Follow-up: separate imported Files from Generated using the existing Research
  kind/generated-image provenance before paging/counting. Reuse the shared browser
  and artifact actions; migrate old Research selections and preserve URL history.
  AI tagging does not change an imported file's placement. Knowledge stays separate.
- Follow-up: Knowledge now lives under Integrations beside Skills. Reuse its forms,
  services and review flow with independent status/paging and guarded reads. Legacy
  Library Knowledge preferences/links migrate to the new Integrations location.
