# File inspector and AI Review refinement

## Scope and existing contracts

The existing vanilla-JavaScript preview keeps its image stage, derivative, zoom,
toolbar and navigation implementation. Changes are confined to its inspector,
Vision presentation, native full-review reader and acceptance checks. No framework,
dependency, endpoint, worker prompt, model selection or budget semantics changed.

`GET /api/v1/library/vision` already returns revision-scoped analysis/tag results
with `id`, `created`, `model`, `text`/`tags`, pending-operation metadata and
`available_hours: 24`. The private store returns at most ten current-revision
results and can evict earlier under its existing global bounds. This UI shows
the latest analysis and latest tag suggestions, without a history tab or durable
client storage. Model/provider disclosure uses the actual model reference; no
missing provider, runtime or billing information is invented.

## Behavior

- Details contains compact filename, file type, MIME, size, optional dimensions
  and Added rows, existing source management, manual/AI tags and Learn controls.
  AI controls live only in AI Review. Unsupported/archived files disable AI Review.
- Source uses compact Add/Edit/Remove actions and an inline HTTP(S) editor. Long
  links truncate visually, keep their complete stored value and open with
  `noopener noreferrer`. Cancel restores the saved value; invalid inputs and
  failed saves retain typed text. Removing a link still requires explicit review.
- Tags uses a removable chip draft with Enter/+ additions, whitespace normalization,
  case-insensitive duplicate prevention and the existing 20-tag/40-character limits.
  Unchanged/pending saves are disabled. Cancel discards the draft; rejected saves
  retain it. Opening the editor never runs inference. Actual backend suggestions
  add only to this draft and require explicit Save tags and the existing review.
- Tabs use native buttons with linked tabpanels, selected state, roving tab stops
  and arrows/Home/End navigation. Tab changes preserve question/token/tag drafts
  and each panel's scroll position. Selecting another file checks its eligibility.
- AI Review shows a useful Understand this image empty state and displays the
  latest analysis first when available, with compact model/time/expiry metadata,
  Copy and Read full review actions. Actual tag suggestions use wrapping Material
  filter-chip buttons with outlined/tonal selected states and selected-only SVG
  checkmarks. Entire chips support pointer and native keyboard activation.
  Selected count, Clear selection and a primary Save N tags action make saving
  explicit; existing manual/AI tags are excluded case-insensitively. Cancel and
  rejected saves retain selections. Successful saves invalidate the detail cache
  before rereading the new revision, including after a failed save and retry.
  The editable question, full-width Review image and secondary Generate tag
  suggestions actions follow. Advanced initially
  hides the existing token controls; invalid hidden settings open for correction.
- Review image? and Suggest image tags? reuse the shared confirmation system,
  with text-only titles, concise descriptions, a compact filename and visible
  provider/cost notices. Tag generation also states that tags are not saved
  automatically. Collapsed Technical details keeps the exact backend-reviewed
  model/provider order, context/output budgets, capability checks and continuation
  notice available. Cancel is focused initially; buttons name the actual action.
  Non-AI reviews reset these additions and retain their existing presentation.
- The shared `ChatMarkdown.renderDocument` builds allowlisted DOM with raw HTML
  disabled, safe links and remote images represented as links. Paragraphs,
  headings, emphasis, lists and code reuse the existing theme. Code wraps within
  the inspector instead of creating a second vertical scroll area.
- No additional response truncation is introduced. Expand opens an independently
  scrollable native reader with the complete stored review; its cross collapses
  back to the inspector. Both copy actions preserve the full stored Markdown,
  including whitespace, using existing secure-context and HTTP clipboard paths.
- A new request uses the existing Material loading indicator/status system and
  preserves previous analysis. Success, rejection/failure, cancellation,
  unknown outcomes, unavailable results and known expiry have distinct messages.
  The inspector reopens after confirmation/cancellation on mobile as well.
- Only the selected image's results are cached in memory, keyed by exact revision.
  Expiration is derived from creation time and the server's availability window;
  an open reader also closes when its result expires. Sign-out clears content.
  Tag suggestions remain unselected initially and require explicit confirmation.
- Desktop retains its right sidebar. Mobile uses the existing full-height details
  sheet below the preview header, with one inspector scroll region and existing
  safe-area, Escape, handle and outside-dismissal conventions.

## Validation

- Focused backend/API checks passed: **84 tests in 42.99 seconds** across
  `test_browser_vision.py`, `test_library_source_links.py`, `test_library_artifacts.py`
  and `test_web_library.py`.
  They cover real pixel requests, confirmation, tag offers, revisions, cancellation,
  private-result expiry, source links and existing authenticated Library contracts.
- `webui_inspector_smoke.py` passed with actual owned Vision/tag workers and a
  local protocol fixture. It covers empty state, long Markdown, allowed formatting,
  HTML/script/unsafe-link injection, complete native/HTTP copying, full reader and
  focus restoration, pending/success/failure/expiry, preparation errors, invalid
  hidden Advanced fields, preserved drafts/tag choices, reviewed tag cancellation
  and saving, unsupported files and sign-out cleanup. Light/dark layouts pass at
  320, 390, 768 and 1440px, with keyboard tab navigation and no horizontal overflow.
- Existing image preview acceptance passed 12 light/dark viewport combinations,
  including gestures, source/tag editing, menu actions, direct deletion and focus.
  Existing file acceptance passed 16 source and eight Markdown layouts, copying,
  complete download, empty/truncated content and literal HTML checks. These three
  focused Chrome runs report **zero browser exceptions**. Screenshots of empty,
  populated, Details and full-review states were visually inspected.
- `webui_metadata_smoke.py` passes real reviewed source add/edit/remove, cancel,
  invalid URLs, long URLs, stale preparation, tag normalization/duplicates/limits,
  actual AI suggestions added only to drafts, successful saves and a real worker
  revision rejection that preserves the draft. Both editors fit light/dark
  320, 390, 768 and 1440px layouts without horizontal overflow.
- The inspector acceptance now also checks chip labels/count/clear, keyboard
  activation, selection through tabs/cancel, duplicate exclusion, original tag
  strings, expired confirmation, and a real checksum rejection before tag
  publication followed by a successful retry. AI confirmations and chip wrapping
  pass narrow/desktop light and dark layouts; visible notices and exact technical
  budgets/order/capability wording are checked. Screenshots were visually reviewed.
- `webui_dialogs_smoke.py` passes **82 mouse/touch backdrop checks**, inside taps,
  inside/outside drags, stacked dialogs and cancellation of a destructive review.
  The result-dependent full-review reader is checked with an actual Vision result
  by the inspector script rather than opened artificially without one. All five
  focused browser scripts report zero browser exceptions.
- The broader `webui_management_smoke.py` was also attempted. Its combined fixture
  exhausted the existing **16 retained reviews / five-minute window** before tag
  saving, reporting `Reviews busy; close an earlier review or wait five minutes`.
  An earlier retry also timed out in its unrelated Skills import step. This is
  **not a green full management run**. The focused inspector script independently
  verifies real analysis and confirmed tag saving within the existing quota; no
  production quota or retention behavior was changed to accommodate testing.
- Repository Ruff, production mypy (**222 source files**), changed Python
  compilation, JavaScript syntax checks and `git diff --check` passed.
- Offline packaging smoke built/installed **all seven workspace wheels**, checked
  bundled WebUI assets/imports and both CLI help commands. A final Webhost wheel
  build includes the completed inspector markup and scripts.

Evidence: `/tmp/klaude-inspector-refinement-ai.json`,
`/tmp/klaude-inspector-refinement-metadata.json`,
`/tmp/klaude-inspector-refinement-backend.log`,
`/tmp/klaude-inspector-refinement-images.json`,
`/tmp/klaude-inspector-refinement-files.json`,
`/tmp/klaude-inspector-refinement-dialogs.json`,
`/tmp/klaude-inspector-management.log`,
`/tmp/klaude-inspector-refinement-package.log` and screenshots in
`/tmp/klaude-inspector/` and `/tmp/klaude-metadata-refinement/`.

## Changed files and limits

- `static/index.html`: inspector tabs, review hierarchy, collapsed Advanced and
  native full-review reader.
- `static/library.js`: inspector tab/scroll state, compact metadata and mobile
  full-height sheet, inline Source/Tags editors and shared AI confirmation
  presentation. Image stage/toolbar/zoom/navigation are retained.
- `static/media.js`: latest-result rendering through the existing safe Markdown
  renderer, metadata/copy/full reader, status/cache/expiry and confirmed filter-chip
  selection with preserved retry choices.
- `static/management.js`: passes captured filename to the existing shared review.
- `static/style.css`: scoped inspector/Markdown/reader styles using existing tokens.
- `scripts/webui_inspector_smoke.py` and `webui_metadata_smoke.py`: focused browser
  acceptance. Existing `webui_image_preview_smoke.py`, `webui_dialogs_smoke.py`
  and `webui_management_smoke.py` adapt to the current inspector controls and
  animation/result-dependent lifecycle.
- `AGENTS.md` and this validation record describe the resulting behavior.

Static paths above are under `apps/webhost/src/klaude_webhost/`. Existing unrelated
dirty changes were preserved; no stash, reset, commit or push was performed.
Refresh the browser to load the static changes; no host restart is needed.

This is focused validation, not a full repository suite or physical-device /
screen-reader certification. AI Review remains limited to current saved images;
the existing 32,000-character stored-response bound, revision checks and up-to-24-
hour availability remain authoritative. There is no persistent history feature.
