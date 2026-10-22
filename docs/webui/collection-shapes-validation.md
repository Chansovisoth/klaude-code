# Stable collection shapes — 2026-10-22

Skills, Knowledge libraries/sources and Connections share the existing collection
row component. The shared Expressive CSS now owns its full corner hierarchy in
every interaction state: 12px interior corners and 23px outer corners on the
first/last rows. A single row receives all four external corners. Full-row action
buttons inherit the row geometry without the general button pill morph or press
scale. Tonal feedback, ripple/state layers, selected Knowledge color, native
switches and visible keyboard focus remain. Segmented tab shape transitions and
their row detection are unchanged.

## Cause and reproduction

Generic card hover rules, connected-row corners and the full-row button's general
hover/press shape rules competed. At a stationary pointer near a corner, Chrome
showed the row button interpolating toward an oversized pill while its parent
changed to another radius. Skills and Connections also lost hover at that fixed
point. The previous rules were reproduced in an isolated authenticated browser
using read-only inventory fixtures.

The new regression was also run against the previous CSS, served from a temporary
static directory without editing the worktree. It correctly failed its first
stationary-pointer geometry assertion. Evidence:
`/tmp/klaude-collection-shapes-validation/previous-style-failure.json`.

## Validation

Run `.venv/bin/python scripts/webui_collection_shapes_smoke.py` with the existing
cached Chrome, or set `KLAUDE_TEST_CHROME`. It reuses the isolated Expressive HTTP
and account fixture; inventory responses are browser fixtures, not live user data
or a claim of backend import/connection coverage.

- **24 cases:** Skills/Knowledge/Connections × light/dark × 320/390/850/1440px.
  First, middle and last rows retain identical computed corners, size and
  transform on every sampled animation frame under a stationary edge pointer.
  The successful run sampled 1,137 hover frames.
- Real mouse press/cancel and keyboard focus preserve geometry. Keyboard focus
  remains visible. Unchanged refreshes preserve row identity and shape.
- Filtering Connections to a single row preserves all four outer corners.
  Knowledge selection retains its selected color and source rows retain stable
  geometry. System reduced motion also passes.
- No page overflow or browser exceptions. Twelve fixture screenshots cover
  light/dark desktop and phone layouts; representative Skills and Knowledge
  captures were visually inspected for connected corners and focus outlines.
- Existing `scripts/webui_loading_smoke.py` passed its delayed reads, retained
  refresh content, stale responses, reviews, reduced motion and logout checks.
- `KLAUDE_TEST_CONNECTIONS_ONLY=1 .venv/bin/python scripts/webui_management_smoke.py`
  passed reviewed add, details and confirmed-state retention after a rejected
  direct toggle, with zero browser exceptions.
- Focused Ruff, CSS bundle consistency and `git diff --check` passed.

Measurements and captures: `/tmp/klaude-collection-shapes-validation/`.

The first new-regression run reached all layout cases but stopped because its
source-list fixture used the wrong URL. The fixture now matches the existing
`/api/v1/library/sources` route; the complete rerun passed.

## Broader checks that did not pass

The full `webui_management_smoke.py` stops at its Models-role assertion (line
302), waiting for an immediate review after form submission. Serving the previous
CSS from a temporary directory reproduces the same failure; it is not reported
as a pass or changed as part of this shape fix.

Its `KLAUDE_TEST_INTEGRATIONS_ONLY=1` mode initially timed out waiting for the
imported `modal-skill` row. A retry stopped earlier on exact float equality for a
48px button measured as 47.99998474121094px. The comparison run with previous CSS
passed that mode. These broader test failures remain unresolved; no Skill import
or management-test code was changed. The dedicated shape regression, loading
regression and Connections-only workflow results above remain separate.

The full repository suite and physical-device tests were not run. No backend,
permission enforcement, tab behavior, commit, push or live-host restart changed.

Follow-up on 2026-10-22: all 24 cases passed again after the generic hover-corner
fix (`hover-corners-validation.md`). The Knowledge fixture now follows the new
`/api/v1/library/knowledge/contents` and `/api/v1/library/knowledge/sources` reads;
selected-source checks replace the retired selected-library layout. The earlier
route discussion above describes the original run.
