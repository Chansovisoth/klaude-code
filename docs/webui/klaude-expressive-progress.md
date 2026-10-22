# Klaude Expressive implementation record

## Scope and preservation

Requested: the complete existing WebUI, using end-4 source as the primary visual
reference. Frontend stays local vanilla JavaScript, HTML, CSS and authenticated
SVG/image assets. Backend authorization, runtime and artifact contracts stay intact.
The initial implementation request did not authorize commit or push; the user
authorized a Git commit/push checkpoint on 2026-10-22.

The initial worktree contained extensive user changes, including Context Panel,
attachment identity/drop, staged Settings, responsive chat and native Material
loading. They are the implementation baseline, not changes created by this task.
An exact static-file snapshot and initial Git status/diff are retained at
`/tmp/klaude-expressive-baseline-v514rwoc` for comparison. No stashing/resetting.

## Reference

- Repository: https://github.com/end-4/dots-hyprland
- Clone: `/tmp/klaude-end4-reference` (reference only)
- Commit: `2f2a376fdb2ad738bf55f693dd0b474b64bb0ab8`
- QML root: `dots/.config/quickshell/ii`
- Root license: GPL-3.0; Klaude root license: MIT.
- The rounded-polygon directory is a pinned Git submodule; inspect its own notices.
- Do not copy GPL implementation/assets into the MIT frontend. Independently
  implement measured geometry/layout/state behavior; retain existing Apache-2.0
  Google Material/AndroidX geometry and use Apache-2.0 Material color utilities.

## Completed implementation

1. Reference/code/license audit complete. Source commit, shape submodule and
   actual QML/JavaScript behavior are mapped in `klaude-expressive-reference.md`.
2. Design system integrated: Material color generation, semantic roles, shared
   shapes, measured motion/corners, state layers and native expressive controls.
3. Shell and every existing Settings category use the shared system. Theme
   includes live preview, retained presets, nine variants, custom/image accents,
   bounded transparency and expressive/classic loading with Discard/Apply.
4. Chat/composer, stable technical Markdown, code, attachment/status surfaces and
   native actions are restyled without changing agent or approval contracts.
5. Full/Context Library use common Gallery geometry and original artifact
   identity. Full Library has Current/All; Context Attach supports every viewport,
   and the panel is closed by default. Existing draft-only drop behavior remains.
6. Models, Integrations, Activity, Memory, account/session/review dialogs and
   empty/error/loading surfaces use the same components. Workspaces has file
   rows, breadcrumbs, safe highlighted previews/Copy and diff colors. Returning
   to a file preview preserves the file-read operation. Commands/shortcuts are
   searchable and keyboard accessible, routed through existing actions.
7. Focused validation complete: 48 webhost/account tests, staged-draft Node test,
   13 isolated browser regression scripts, 88 light/dark responsive cases, 12
   automated accessibility surfaces, semantic contrast matrix, local image palette
   extraction, real HTTP/SSE/drop/review behavior, source/asset hashes, repository
   Ruff and seven-wheel build/install/import/help validation.

## Final records and limits

- Follow-up: shared grouped buttons/radios restore expressive 23px external
  corners, 9px inner corners and selected pills. Shared row detection handles
  wrapping, visibility, single items and resizing; selected radii use actual
  half-height for smooth shape transitions. Validation and current evidence are
  recorded in the grouped refinement section of `klaude-expressive-validation.md`.
- Source map/licenses/deviations: `docs/webui/klaude-expressive-reference.md`.
- Exact validation, screenshots, coverage and limits:
  `docs/webui/klaude-expressive-validation.md`.
- Captures/results: `/tmp/klaude-expressive-validation/` (fixture content).
- Reference screenshot: `/tmp/klaude-end4-reference-settings.png`.
- Rebuild shared assets after edits with `scripts/bundle_webui_loading.py` and
  `scripts/bundle_webui_expressive.py`; both have deterministic `--check` modes.
- No live-host restart or change to backend security enforcement.
- Mobile section-navigation follow-up: Library and Integrations share a full-width
  wrapping tab row through 560px, with buttons growing into each row's free space.
  Focused browser checks cover 320/390/560/1440px; existing corner, loading and
  Models validation above is reused for the requested checkpoint.

No implementation phase is left as an unintegrated demonstration. Deliberate web
adaptations remain: stable-width selection groups, nine static shapes and the
seven-shape loader rather than arbitrary all-pairs morphing, native immediate
modal close, extracted-seed persistence rather than wallpaper storage, and
existing terminal-only model/provider operations. Physical device/Safari,
screen-reader and low-end performance acceptance and a full repository unit run
were not performed. These are documented validation/platform limits, not claimed
passes. Further work should begin from those explicit limits or new user feedback.
