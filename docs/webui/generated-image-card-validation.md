# Generated-image response cards — 2026-10-28

The implementation was compared with `markdown.js`'s code-block renderer and
its toolbar, action buttons, rounded surfaces and shared menu styles before
editing. Chat images now use the same Material surface tokens, icon factory,
button helpers, native popover pattern and authenticated artifact mechanisms.

Each completed output has one cohesive media card: compact image title and
dimensions, Download/Expand/overflow icon controls, the full proportional image,
and matching Edit/Regenerate footer buttons. The former gray preview canvas,
detached dimensions and outlined Download pill are removed. Normal assistant
message actions remain outside the media card.

The card width derives from the image ratio. Square images target 420px on
desktop; landscape can extend to the chat reading width. In mobile chat (up to
850px), galleries cap at 75% of the chat width so cards leave breathing room on
the right. Proportional sizing and existing height bounds still apply. Portrait preview height
is bounded by 560px and 70dvh. Decoded natural dimensions also update the ratio,
and the preview has no artificial letterboxing or cropping. Single-image headers
stay at the conversation viewport's top while their image scrolls, bounded by
the preview region so they cannot cover the footer on short screens. Gallery
headers remain within their own cards, avoiding stacks of floating toolbars.

Multiple outputs use a responsive grid with a shared Generated images heading
and count, numbered cards and individual authenticated preview/download actions.
Controls have at least 44px height. Narrow portrait cards move Regenerate into
their overflow menu; Edit remains in the footer. Image details opens the existing
viewer. Native menus support keyboard activation, arrows/Home/End, Escape, outside
dismissal and focus return. Navigation, session changes and sign-out close them.

Pending outputs now use that same frame, preview dimensions and footer height.
Their header shows the image icon, a concise waiting/preparing/creating/cancelling
state and the requested dimensions. Cancel is integrated into the header and
calls the existing image-job control endpoint. It stays disabled while
cancellation is pending; only an authoritative terminal state removes the placeholder.
The footer identifies Local generation. The existing halftone provides the sole
indeterminate animation inside the card, remains still while queued/cancelling,
and respects both system and saved reduced-motion preferences. There are no
invented percentages, steps or completion estimates.

Failed and cancelled jobs use compact cards with a safe explanation and Retry,
which restores the original request as a composer draft. An unconfirmed outcome
offers the existing Check original output control and never submits another job.
Focus survives card replacement, including a Cancel control becoming disabled or
disappearing. Status text uses the conversation's existing live-announcement
semantics and polite status roles.

The existing execution bar, native Execution details disclosure, timeline and
diagnostic classification remain intact. Image cards contain creation/result
state rather than copies of tool/stage records. The only public contract addition
is an allowlisted output width/height list and the persisted serial-output index,
used for correct placeholder geometry and the current child. No private prompts,
server addresses, seeds or full job specifications are projected.

Validation uses temporary local stores and a recording SD service fixture, never
owner data or live inference. The PNG fixture matches each explicitly requested
ratio, so all images pass the unchanged generation/storage path:

- Square 512×512, landscape 1024×576, portrait 576×1024 and a three-output gallery.
- 320×568, 390×720, 768×900, 844×390 and 1440×900, in light and dark (40 cases).
- Image ratios, image/preview bounds, zero letterboxing, preview height limits,
  horizontal fit, icon labels/touch sizes and separate assistant actions.
- Reload of each shape and resume of the conversation preserve the exact saved
  asset IDs and rendered cards. Keyboard overflow activation/Escape and viewer
  focus return use real Chromium input.
- The existing chat image walkthrough checks Download, preview, real source-image
  editing, cancellation, errors and eight halftone loading layouts.
- Queued, running, cancellation pending, cancelled, failed, completed, SSE
  reconnect, browser reload and resumed running jobs retain their authoritative
  identity and an operable Execution details disclosure with matching timeline
  rows. The placeholder and finished landscape card have identical dimensions.
- A fresh image-action owner reconstructs an expired admission as unknown. Reload
  and repeated snapshots retain that outcome and recovery control, without a
  success preview, Retry or new native request. Native request counts also guard
  reconnect/resume and Retry draft behavior against duplicate submissions.
- The existing Image Studio walkthrough checks five widths (320–1440), Chat
  entry points, Uploads, service failures, ratios/drafts, review, output, download
  and cancellation, with zero browser errors.

Commands: `.venv/bin/python scripts/webui_chat_images_smoke.py` and
`.venv/bin/python scripts/webui_image_studio_smoke.py`. Screenshot evidence is in
`/tmp/klaude-chat-image-evidence/media-*.png` and
`/tmp/klaude-image-studio-evidence/`. Phone and desktop screenshots were inspected.
JavaScript syntax, scoped Ruff, both generated-bundle checks and
`git diff --check` are also checked.

The 22 chat-image application tests pass, including the bounded public dimensions
projection and existing cancellation, recovery, persistence and deduplication
contracts. The activity browser fixture separately exercises actual tool review,
questions, completion, error, cancellation, reload and reconnect, plus all 13
execution labels at four widths. Its reload synchronization now waits for the
new document before asserting restored history.

Only chat presentation, the additive public dimensions/index projection, focused
checks and documentation change.
The generation pipeline, artifact storage, permissions, orchestration and manual
Image Studio implementation are preserved. Unrelated worktree changes are kept;
no commit, push or live host restart is performed. This is focused Chromium
coverage, not a full repository suite or physical-device/cross-browser claim.
