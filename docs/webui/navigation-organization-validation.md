# Library and Integrations organization

The browser now presents Library as **Files / Knowledge**, and Integrations as
**Skills / Connections**. Connections retains the configured MCP server count
and its deferred browser availability. MCP remains the server/protocol term.

Files combines existing document, media and research artifacts without moving
or rewriting content. Type (All files, Documents, Media, Reports) and status
(Saved, Archived) are independent filters applied before pagination. Existing
preview, download, tags, archive, restore and reviewed deletion still use the
shared artifact services. The Files count sums known saved artifact totals
across all types; partial totals are omitted and bounded totals retain `+`.

Add a file is collapsed by default. Its explicit Document/Image import choice
does not depend on the selected type or archive filter. Imports still require
review and do not index Knowledge. Knowledge retains indexed library browsing,
text search, sources and reviewed learning/refresh operations.

Navigation stays flat on phones. The browser restores Files/Knowledge and the
file type/status after refresh, using allowlisted sessionStorage identifiers.
Previously saved Documents, Media, Research and Archive tabs migrate to their
corresponding file filters. Existing Knowledge selections stay on Knowledge;
fresh tabs enter Files when Library is opened.

## Validation

- `scripts/webui_loading_smoke.py` passed against an isolated local host and
  Chrome, using controlled domain-read responses. Coverage includes the two
  Library destinations, aggregate counts, combined archived-report filters,
  stale reads, explicit import type, Connections naming, and actual page reloads
  for old Media/Archive selections, new filter restoration and fresh defaults.
- Files layouts passed at 320, 390, 768 and 1440 pixels without horizontal page
  or Library overflow. Screenshots were inspected in
  `/tmp/klaude-loading-preview/files-*.png`.
- Existing loading lifecycle checks, reduced motion, preview cancellation,
  source/Skills/operation loading, and logout cleanup passed without browser
  console errors.
- `pytest tests/unit/test_web_library.py -q`: **6 passed**. These focused tests
  cover authenticated reads, import reviews/operations and stale revisions;
  they are not a full Python suite result.
- JavaScript syntax checks, Ruff for the changed smoke script and
  `git diff --check` passed.

This slice changes static presentation only; no server restart or data migration
is required. Reload the browser to pick up the assets. Physical mobile keyboard
behavior and complete accessibility acceptance remain outside these fixtures.

## Remaining IA work

Persistent Memory management belongs in Settings, with Personal/Project scopes;
temporary session context is separate. There is no browser Memory management
backend/UI in this slice. Broader Connections authorization and management,
cross-library search and direct saved-file indexing remain separate features.
