# Model Defaults dropdowns

Model Defaults previously created only Unset/saved options until Load models was
submitted manually. Loading also supplied one unfiltered catalog to every role,
so completion-only, tool-enabled, image-capable and embedding models were mixed.

The browser now loads the selected enabled connection automatically, including
after connection changes. Refresh models repeats that read. The existing catalog
route accepts `purpose=defaults` and returns per-role hints without generation or
settings writes. Ordinary catalog responses and the main Models page retain their
existing contract and discovery cost.

Native Ollama uses the existing bounded metadata reader and `/api/show` batches
of eight, with four concurrent inspections per batch. New batches stop after a
20-second inspection budget; unavailable/uninspected capabilities remain unknown.
Definitions and credential revisions are rechecked before returning choices.
There are no model-name heuristics. Embedding-only models are excluded. Startup
chat and Research require tools; Utility and Vision do not. Utility, Research and
Vision exclude known mandatory-Thinking models and unsupported adapters. Utility
and Vision fallback controls use the same role filters as their primaries.

Unknown capabilities stay selectable with Capability unknown, rather than being
presented as verified or silently hiding potentially supported cloud models.
Exact existing review checks remain authoritative, including Vision inspection.
Review also rejects Codex for bounded Utility/Research roles and mandatory-Thinking
Research models, matching their existing execution restrictions. No provider
support is inferred beyond existing metadata and reviewed backend contracts.

Saved references remain visible when outside the selected catalog. Dirty model,
fallback, token and image-service inputs survive reads and connection changes.
Failed refreshes retain populated choices and drafts; loading placeholders clear
when a request fails. Aborted/obsolete responses cannot repopulate after sign-out.
No default is saved automatically and the current conversation keeps its model.

Validation:

- **71 passed in 27.90s** across WebUI media settings, model capabilities and AI
  defaults. Includes real local metadata requests, per-role filtering, embedding
  exclusion, unknown metadata, inspection limits, stale definitions, unsupported
  role rejection, reviewed persistence, deduplication and recovery.
- Host registry/resume/runtime regressions: **3 passed, 37 deselected**.
- New isolated Chrome smoke: automatic lists for all four roles and all six
  fallback selects, connection changes, dirty drafts, failed refresh, cancellation,
  real reviewed Vision save, saved values outside the active catalog, logout race,
  accessible labels and eight light/dark viewport checks (320/390/768/1440px).
  Zero browser exceptions and zero inference calls. Phone/desktop captures were
  visually inspected.
- Existing Settings smoke passed both password/bootstrap hosts and **90**
  panel/theme/viewport combinations, including compact Review alignment and
  timezone save/cancel. Main Models configured/legacy catalog, runtime selection,
  history, keyboard navigation and logout regressions also passed.
- Repository Ruff, production mypy (**223 files**), modified Python compilation,
  JavaScript syntax and whitespace checks passed. Offline packaging built and
  installed all **seven wheels**, verified assets/imports and both CLI help entry
  points.

Read-only verification against the actual installed Ollama catalog found **10
Vision models**, **19 chat/Research models** and **21 Utility models**, with no
unverified native entries. This contacted only catalog/capability metadata and
did not generate responses or change defaults. Cloud provider inference and
physical-device testing were not performed; this is focused, not full-suite,
coverage.

Initial checks encountered sandbox socket restrictions and incomplete offline
build caches; localhost checks were rerun with permitted access and the build
passed using the populated existing attachments cache. Two new fixture assertions
were corrected (connection constructor order and a preserved legacy startup
option); final tests above passed.

Live activation used a graceful managed-host reload after confirming zero active
turns, queue entries, pending interactions and accepted/running/cancelling domain
operations. The public conversation digest/count, session, model/mode/effort,
settings revision, workspace, LAN address/certificate and preference/hosting file
hashes all matched afterward. Browser cookies were revoked by the existing stop
behavior, requiring sign-in again. The pending WebUI date/time feature was loaded
by the same restart. No defaults, OS timezone or user files were changed.

Evidence: `/tmp/klaude-model-defaults-backend-current.log`,
`/tmp/klaude-model-defaults-host.log`,
`/tmp/klaude-model-defaults-smoke-final.{json,log}`,
`/tmp/klaude-model-defaults-settings-final.{json,log}`,
`/tmp/klaude-model-defaults-models-regression.{json,log}`,
`/tmp/klaude-model-defaults-{ruff,mypy}-final.log`,
`/tmp/klaude-model-defaults-package-final.log`,
`/tmp/klaude-model-defaults-live-reload.json` and captures in
`/tmp/klaude-model-defaults-preview/`.

Changed files: `browser_media_settings.py`, `host.py`, static `media.js` and
`index.html`, `test_web_media_settings.py`, `webui_settings_smoke.py`, new
`webui_model_defaults_smoke.py`, `AGENTS.md`, `coverage.md` and this record.
The date/time validation record adds the shared live activation evidence.
Pre-existing dirty worktree changes remain intact; no stash/reset/commit/push.

The subsequent [Store and settings completion](model_store/completion-validation.md)
adds a native searchable picker with the shared numbered pager for each primary
and fallback slot. It retains staged Apply/Discard and the underlying native
select/change seam. Enabled Vision cannot clear its primary until disabled.
