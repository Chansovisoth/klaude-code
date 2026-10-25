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

- AI Review's introduction shows the current model, context tokens and output
  tokens. Review settings offers the configured Vision role or a temporary model
  for the current conversation, using enabled connections and bounded catalogs.
  Temporary choices survive image reopen in the current tab and clear on
  sign-out/reload. They never update global model defaults. Unknown capabilities
  remain labeled; worker execution still checks current image capabilities and
  exact connection/credential bindings. Override requests use exactly one model,
  while the Settings default retains its configured fallback order.
- Details contains compact filename, file type, MIME, size, optional dimensions
  and Added rows, existing source management, manual/AI tags and Learn controls.
  AI controls live only in AI Review. Unsupported/archived files disable AI Review.
- Source uses Add/Edit actions and an inline plain-text editor for notes or URLs. Add
  source replaces the empty-state text in place; edits save on blur or Ctrl/Cmd+Enter
  without buttons, helper text or a confirmation dialog. Escape restores the
  saved value. Enter adds a line. Notes render as inert text; valid HTTP(S) URLs
  within notes or a list of sources are clickable. Pending blur saves continue
  after the viewer closes. Only safe HTTP(S) links
  are clickable, retain their complete stored value and open with
  `noopener noreferrer`.
  The editor input stays in its form while the view text is rendered separately;
  switching modes never detaches the input. `scripts/webui_source_editor_smoke.py`
  covers repeated empty blur/reopen, Escape, direct saves, and image close/reopen
  at 1440px and 390px. The focused regression passed with zero browser exceptions.
- Tags uses a removable chip draft with Enter/+ additions, whitespace normalization,
  case-insensitive duplicate prevention and the existing 20-tag/40-character limits.
  Add tags opens a compact editable chip in the tag row. Its text field stays
  mounted while other chips render; Enter or blur adds the draft tag, and the
  inline plus supports touch. There is no separate full-width tag input card.
  Unchanged/pending saves are disabled. Cancel discards the draft; rejected saves
  retain it. Save tags submits the exact validated draft directly without a
  confirmation dialog, retaining backend revision and receipt checks. Opening the
  editor never runs inference. Actual backend suggestions
  add only to this draft and require explicit Save tags.
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

## Compact AI Review sidebar (2026-10-24)

Inspector tabs use transparent faces, accent text and a 2px underline. The
introduction retains its original centered 48px icon container, heading and
description. Question, textarea and Review image remain together; the empty
textarea shows a placeholder and submits the existing "Describe this image."
default. The Review action uses an md3.io-inspired filled split button with a three-dot
trailing action opening the native Review settings dialog.
Tag generation is a ghost action with a tag icon; retention uses an info icon
and the theme's on-surface text. Existing radius, color and motion tokens remain
authoritative, with 44px minimum action targets and reduced-motion support.

The Chrome inspector fixture checks transparent active tabs, underline geometry,
icons, 320px overflow, native Enter dialog activation, Escape dismissal/focus return and visible keyboard
focus. Computed foreground/background contrast checks require 4.5:1 for the
active tab, tag action, primary action and retention notice in the tested theme.
The broader fixture covers light/dark layouts at 320, 390, 768 and 1440px,
review/tag workers, drafts, tab navigation, copy, errors and expiry. This is
fixture validation, not a live deployment or an exhaustive custom-palette audit.


### Split Review action (2026-10-24)

Inspected material@3.2.4 split-button constants, factory, and styles from the
local reference package. Adapted its small filled two-button geometry and 2px
gap to Klaude's native form and live tokens; retained 44px targets. The trailing
action uses the shared more icon at 16px, matching session row actions, and opens
a dialog instead of the library's menu. No Solid runtime or dependency added.
The existing context/output inputs keep their IDs, defaults, bounds and form
association. Done validates; Enter in an input also validates and closes. Escape
or Close retains the draft values; closing returns focus to the trigger.
Invalid submission opens settings and focuses the invalid input. Auth reset
resets the associated form and closes settings; viewer closure also closes it.
Chrome fixture checks modal fit at 320/1440px, keyboard activation/dismissal,
focus return, invalid budgets, retained drafts and real review/tag workers.

The split action uses finite 22px outer radii and shared extra-small inner
corners, avoiding CSS radius normalization flattening the inner corners when
combined with a 9999px pill. Hover/focus softens the inner corners to the shared
small radius, with themed hover/press color feedback and existing motion/press
behavior. Browser checks exercise hover on both halves and require visible
rounded corners. Inspector source styles precede the generated Expressive block;
the bundle consistency check passes.

Tag suggestion generation and Review image start directly from their buttons
without a confirmation dialog. Backend model/capability checks and durable receipts remain in use. The
focused source-editor browser regression verifies suggestions arrive in the open
inspector without a modal and that saved AI tags remain unchanged.

## Review clearing and generation presentation

Copy and Read full review now share their action row with Clear. Clear removes
analysis results through the exact displayed result from private local storage,
including older reviews that could otherwise reappear. It retains newer results,
tag suggestions, saved tags and image metadata. The authenticated POST uses the
existing session/Origin/CSRF guards and artifact revision check; replaying the
same clear cannot delete later work. A pre-clear read cannot restore stale UI.

Loading saved AI Review data now reuses the centered generation introduction:
the heading is “Loading AI Review…” and its 48px icon slot contains the shared
normal circular loading indicator. It follows the user's normal loading style;
the generating shape remains reserved for active AI work. The old inline loading
row is absent. Inputs remain busy until the read succeeds or fails, and a failed
or superseded read cannot leave the introductory loader stuck.

The isolated `scripts/webui_review_loading_smoke.py` passed at 320/768/1440px in
light and dark themes. It checks the shared introduction, a 48px normal loader,
absence of the old inline loading row, busy inputs, the distinct generating
indicator, read failure and late results after closing. No model generation was
invoked and no browser exceptions occurred. Screenshots are under
`/tmp/klaude-review-loading`. Focused Ruff, JavaScript syntax and whitespace checks
passed.

During analysis, the existing centered introduction shows the configured
48px generating indicator and “Generating review”. Review image becomes Cancel
review, using the existing owned-operation cancellation path. Other inputs remain
locked while pending; the previous review returns after cancellation or failure.
Tag-suggestion requests keep their separate presentation.

Validation: 14 Vision HTTP tests passed, including exact/repeated clear, rejected
unauthenticated/cross-site/stale/tag-result requests, retained newer results/tags
and unchanged image metadata. The isolated 1440px/390px browser smoke passed real
slow review generation, the primary Cancel review action and Clear surviving
image reopen, with zero browser exceptions. JavaScript syntax, focused Ruff,
result-service mypy and diff-whitespace checks passed. Existing unrelated host.py
line 63 exceeds Ruff's line-length limit; it was not modified for this change.
The new clear endpoint and pending-operation kind require restarting an older
running host; validation used isolated fresh hosts, not the user's live host.


### Escape in tag editing

Escape invokes the existing Cancel tags path before preview dismissal or phone
sheet dismissal: manual tag drafts and pending AI-tag removals are discarded,
the pending input clears, saved tags return and focus moves to Edit tags. The
preview and current details sheet remain open. Source editor Escape is unchanged.
The source-editor Chrome fixture exercises a chip draft plus an uncommitted
input at 1440px and 390px and checks focus, preserved preview and unchanged store.

Tag generation also reuses the introduction: the generating indicator and
Generating tag suggestions replace its idle icon/title, and the tag-generation
button becomes Cancel tag suggestions. The existing cancellation ownership and
pending locks remain authoritative. Previous suggestions return after a cancelled
request. Completed suggestions sit immediately below Generate new tag suggestions;
the chips precede selection actions and model metadata. Suggested chips share
Details' 4px/12px face padding, 32px height and 8px row gaps, including selected
states. Browser regression passed slow tag generation, actual cancellation,
retained suggestions, DOM ordering and computed chip-spacing comparisons, with
zero browser exceptions; review generation/cancellation and Clear still passed.


AI Review tag selection uses compact Clear and Save buttons aligned to the right,
matching Details' action row. Clear deselects draft suggestions; saved artifact
tags are untouched. Save retains its selected-tag count in its accessible label
and preserves Saving/Save unconfirmed states. Both actions disable when blocked
or no tags are selected. The source-editor fixture checks labels, alignment and
Clear selection behavior after real tag generation.


## md3.io primary inspector tabs

Details / AI Review now use material@3.2.4 primary-tabs CSS and its actual
createTabIndicator runtime from the locally inspected package. The MIT license,
upstream files and hashes are vendored under static/vendor/material-tabs-*.
The component reference is https://md3.io/components/tabs/; both that page and
its /docs variant failed to load during this run, so implementation was checked
against the installed package source, constants and styles.

The native buttons retain their IDs, ARIA relationships and existing state owner.
Their adapter synchronizes the upstream active class and indicator. Primary
geometry is 48px targets, 14px/20px labels, and a 3px rounded indicator measuring
label width minus 4px (minimum 24px). Upstream CSS anchor positioning and its
JavaScript fallback/resize update stay intact. Local roles supply colors/fonts;
existing reduced-motion rules apply. No Solid/framework dependency added.

scripts/bundle_webui_tabs.py embeds the indicator in the existing library.js
route. The Expressive CSS bundler includes upstream tabs CSS before the local
adapters. Browser fixture checks measure active label/indicator centers and
widths at desktop/phone sizes and exercise keyboard selection, then run the
existing editing, AI generation, clear/save and dismissal checks.
