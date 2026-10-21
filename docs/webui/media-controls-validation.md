# Browser Model Defaults and image controls

This continues the feature-completion plan. It implements shared model roles,
image-service setup, image analysis and reviewed AI tags. Model connection/secret
setup, Model Manager, remote Skill discovery, interactive MCP OAuth and full
workspace execution remain outside this slice.

## Behavior

- Settings → Model Defaults chooses Chat, Utility, Research and Vision models
  from an explicitly loaded configured catalog. Role saves check exact endpoint
  and credential revisions. Native models require fresh completion declarations;
  Chat/Research additionally require tools. Vision requires actual image support
  and a Standard-mode model. Utility/Vision allow up to three distinct explicit
  fallbacks. Utility output remains bounded to 128–2048 tokens.
- Changes preserve the current conversation's model. An explicit Chat default is
  used for new chats and a fresh host. An unset default requires selection; an
  unavailable startup default leaves the browser usable with sending blocked
  until selection. No replacement model generates automatically. Exact saved
  conversations retain their existing offline resume path.
- Generated Research offers its saved role or the current chat model. Existing
  immutable question/model/provider/budget bindings still govern each job.
- Settings → Image generation service tests a user-entered stable-diffusion.cpp
  endpoint before review, captures its loaded model and bounded capabilities,
  and checks them again before saving. This does not submit a generation job or
  load models on the image server.
- Model Defaults and image-service writes adopt the same witnessed journal
  receipt/resource as terminal saves. Both expose pending/unknown state and an
  explicit reviewed saved-state check. Recovery compares exact prior/final local
  fields without replay, metadata requests or generation; changed storage stays
  fenced. Vision activation checks its reviewed model bindings under the shared
  preference/registry/credential locks.
- Library image details offers reviewed questions and AI tag suggestions. Review
  captures the exact image revision/checksum, configured Vision models/fallbacks,
  context and output budgets. Capability inspection, disposable pixel preparation
  and inference run in the owned worker after approval. Inputs retain existing
  32 MiB/40MP decoding limits and bounded prepared-pixel limits. Supported images
  stored as Documents use their original record and do not change type.
- Analysis does not change chat history, manual tags, indexing or original pixels.
  AI suggestions start unselected. Only offered, checked tags can be saved after
  a separate review; manual tags remain separate. The tag effect checks its fence
  inside the artifact write transaction after the revision/hash checks. A lost
  acknowledgement after that gate remains unknown rather than claiming rejection.
- Stop requests cancel only an owned analysis/suggestion worker. Its receipt is
  cancelled and resource released only after the worker process group is reaped.
  This does not promise that a remote provider stops computation or reverses a
  charge. Tag saves cannot be cancelled through this read-operation endpoint.
- Results live in a separate private `browser-results.db`, outside operation
  receipts and chat events. At most 64 bounded records fit within a 24 MiB SQLite
  page limit. Results are available for 24 hours and expired rows are removed on
  later writes. Authenticated reads require a completed owner receipt and the
  exact current, saved image revision. Public tags omit private provenance.
  Sign-out clears all browser results, prompts and setup forms; accepted work
  retains profile ownership. No image bytes are stored in these result records.
- Loading another model catalog preserves unsaved role and image-service drafts.
  Obsolete viewer reads/reviews are discarded; late results cannot replace the
  selected image. New capability checks retain old-host restart guidance.

## Validation

- Real loopback model/image fixtures exercise metadata, reviewed setup/save,
  duplicate IDs, shared receipts/recovery, startup/new-chat behavior, native pixel
  requests, analysis, tag proposals/selection, changed/corrupt images and worker
  cancellation. Indexing, artifacts and session/HTTP regressions reuse their real
  shared stores. These fixtures do not establish live cloud/GPU behavior.
- `scripts/webui_management_smoke.py` passes in Chrome with actual HTTP, workers,
  image pixels and Knowledge indexing. It configures Vision/Research roles and
  image service, generates an image, analyzes it, verifies initially unchecked
  tags, saves one selected tag and checks logout cleanup. Settings, Integrations
  and Generated fit 320/390/768/1440px. No browser console errors were observed.
- Repository Ruff, production mypy (222 source files), JavaScript syntax checks
  and the seven-wheel build/install/import/entry-point smoke pass. Installed-wheel
  assertions now include `management.js` and `media.js`.

The prior full-suite run's timeout and split results remain recorded in
`feature-completion-validation.md`; it is not a current uninterrupted full-suite
pass. Final focused counts and host reload evidence are appended below.

- Final focused regression gate: **299 passed in 204.35 seconds**, covering all
  new media tests plus AI defaults, generation, tags, Vision, artifacts, application
  bridge/coordination, Web host, Web Library and prior profile management.
- The final Chrome run passed all setup, pixel analysis, initially unselected tag
  suggestions, selected-tag persistence, existing management/Knowledge flows and
  the four recorded responsive widths, with zero browser console errors.
- The managed host was confirmed idle and gracefully reloaded. Its selected
  conversation/workspace and loopback/LAN listeners were preserved. The live host
  reports `media_management: true` and serves the current `/media.js` with HTTP 200.
  Normal shutdown revoked browser cookies; users must refresh and sign in again.
  No real-profile preferences, Memory entries or artifacts were changed as probes.

## Generated Create dialog (2026-10-21)

- Generated uses a 48px plus button to the right of its toolbar controls.
  Type, Status and Sort match Uploads: inline above the 650px content breakpoint,
  or behind Filters and sort on compact layouts. The plus button opens a native
  Create dialog with Image and Research tabs.
  Image contains Prompt, Width, Height and Steps; Research contains Model,
  Research question and Format. Each tab has its own job history below its form,
  with the existing live updates and controls. Research no longer has a separate
  inline form on the Generated page. Existing reviews and service checks remain.
- Switching tabs preserves both drafts. The selected tab remains active on
  reopening; sign-out resets it to Image. Tabs expose selected state and panel
  relationships, a single keyboard tab stop and arrow/Home/End navigation.
  Each form keeps its own pending state so image work does not block Research.
- Escape and Close dismiss the form and restore focus. Closing during preparation
  discards a late review, as does switching tabs. Navigation dismisses the dialog;
  sign-out clears both private drafts. Preparation errors appear inside the
  dialog. Research/image review actions close it before opening confirmation.
- `KLAUDE_TEST_GENERATED_ONLY=1 .venv/bin/python
  scripts/webui_management_smoke.py` passed with isolated HTTP/image fixtures:
  plus placement, 320/390/768/1440px layouts, filters, input focus and restoration,
  keyboard tab switching, draft preservation, late-review disposal for both tabs,
  reviewed Research queue/stop, image generation, each history below its form,
  opening output and returning to the dialog, navigation and logout cleanup.
  Chrome reported zero JavaScript exceptions. Optional
  `KLAUDE_TEST_SCREENSHOTS=/tmp/klaude-generated-dialog` saves dialog captures.
- JavaScript syntax, focused Ruff, Python compilation and `git diff --check`
  passed. The initial broader management smoke stopped later while waiting for
  the separate AI-tag-save review; it is not a full management or full-suite pass.
  No production image server or real-profile settings were changed for validation.
