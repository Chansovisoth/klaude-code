# Hover corners and Models collection rows — 2026-10-22

## Cause and change

The generic Expressive hover rule replaced component-specific radii with a
9999px pill. On mouse-out, the 350ms spatial curve
`cubic-bezier(.42,1.67,.21,.90)` overshot below zero while returning to the selected
provider's 30px radius. Chrome clamped that value to zero: a baseline real-pointer
capture recorded **nine square-corner frames out of 31**, before returning to
30px. An older base hover rule also forced 16px corners, causing the same problem
on icon buttons when the Expressive hover override was removed.

Both generic corner overrides are removed centrally. Hover retains tonal/state
feedback, press retains scaling, and ripples and focus rings remain. Existing
finite component-specific transitions and row-aware segmented selected pills
are preserved. Send keeps its 17px geometry; session/tag selection uses the
finite 23px theme token instead of 9999px.

Models uses the existing collection list/row component: common icon tiles,
spacing, 12px interior and 23px outer row corners, tonal current-model selection
and explicit Use model actions. The catalog, Thinking labels and fenced runtime
selection retain their existing contracts. No backend or security changes were
made for this fix.

## Validation

- `scripts/webui_hover_shapes_smoke.py` runs an isolated HTTP/account host and
  Chromium profile with read-only fixture catalogs, without inference or user
  data. Real-pointer hover/exit captures for selected OpenAI, OpenRouter and
  Ollama each retained a minimum 30px radius with no square frames.
- **31** surface/viewport cases passed broad hover/exit frame sampling across
  Chat, Library, Workspaces, Integrations, Models, Activity, all five Settings
  categories, the command palette and app
  reduced motion at phone/desktop widths. Populated Skills, Knowledge
  libraries/chunks/sources and Connections use read-only browser fixtures.
  This sampled 829 button instances and 961 exit frames without square corners.
- Eight actual light/dark layouts at 320/390/850/1440px verify shared Models rows,
  icons, current state, catalog metadata/efforts, contained 44px action targets
  and no horizontal overflow. Light/dark 320px and 1440px captures were inspected.
- `scripts/webui_models_smoke.py` passed its configured and legacy-host paths:
  catalog/search/paging, explicit selection and duplicate suppression, preserved
  Thinking effort, busy/disabled states, failure/retry, refresh failure, history,
  reload, keyboard navigation and late-response sign-out cleanup. Provider
  discovery/runtime construction are fixtures; HTTP/runtime seams are real.
- The segmented-corner browser regression passed **72** variant/theme/viewport
  cases and four interaction states on 41 segments. It also checked all seven
  wrapped selection positions, container resizing, single/hidden/removed items,
  RTL, actual half-height pills, native keyboard/discard behavior, Inspector
  navigation, animated selection and reduced motion. No browser exceptions.
- `scripts/webui_collection_shapes_smoke.py` passed **24** section/theme/viewport
  cases, stationary-pointer edge sampling, press cancellation, visible focus,
  keyed refresh retention, a single filtered row, selected Knowledge source
  corners and system reduced motion. No browser exceptions.
- JavaScript syntax, focused Ruff, bundle synchronization and whitespace checks
  pass. No new dependencies or third-party source were introduced.

The older collection regression initially stopped because it mocked the previous
Knowledge routes. Its read-only fixture now uses the current contents/source
routes and checks selected source rows instead of the retired selected-library
layout. Early development of the new Models fixture also exposed loading and
snapshot races; the final fixture installs transports before navigation, retains
the host's provider capability and waits for completed catalog loading. The
expanded audit also waits for visible inventory reads to finish before forcing
hover, so a catalog replacement cannot invalidate its captured DOM identities.

Evidence: `/tmp/klaude-hover-shapes-validation/report.json` and its light/dark
Models captures; `/tmp/klaude-model-corner-before.json` (baseline);
`/tmp/klaude-models-mcp-preview/` (functional Models run);
`/tmp/klaude-collection-shapes-validation/` (collection regression);
`/tmp/klaude-segmented-corners-validation/` (segmented regression).

Coverage is scoped browser regression and visual inspection, not a full test
suite, live-provider execution, every possible dialog/data state, physical-device
or non-Chromium validation. Unrelated dirty-worktree changes are preserved. No
commit or push was made.
