# Reliable image attachments: diagnosis and proposed approach

Date: 2026-10-15. Base revision: `4a64ce6`, with the existing uncommitted
Library/navigation and verification work preserved. This document records the diagnosis and implementation scope. The follow-up was
implemented on 2026-10-16; see [validation and limits](image-attachment-reliability-validation.md).
Original provider/model preferences were preserved.

## Objective

Ordinary supported images should attach without manual resizing, survive retries
and resume, and fit the active request efficiently. Preserve original bytes and
show any preparation or loss of detail honestly. Absolute success for arbitrary
files or external providers cannot be guaranteed: corrupt files, unsupported
codecs, context limits, unavailable models and provider policy still exist.

## Actual session findings

Inspected session `075e753a2edc4e7a9fbbb3e9995c11a0` read-only, including public
turns, private reference metadata, request capability events and completion
metadata. Its explicit model is
`openrouter@default-openrouter/openrouter/free`, Standard mode.

| Input | Stored bytes | Dimensions | Existing generic image-token estimate | Observed outcome |
| --- | ---: | --- | ---: | --- |
| First JPEG | 167,704 | 800×1280 | 4,000 | Completed visual response |
| Second JPEG | 183,158 | 864×1184 | 3,996 | Local context rejection; later attempts reached the provider and failed |
| Third JPEG | 54,052 | 580×680 | 1,591 | Completed response containing classification-like safety labels |

All three stored images have valid checksums, remain unarchived, and fully
decode as JPEG without warnings in a bounded local decoder. None exceeds the
current 8 MiB, 4096-pixel-side or 4-megapixel attachment bounds. No image was
re-uploaded or sent to a model during this investigation.

### Confirmed Klaude problems

1. **Inconsistent context authority.** The saved request capabilities report
   unknown provider context. `ChatImages.project` then uses 8192, while cloud
   history compaction has a separate unknown-context fallback. Fresh image
   inspection returns capability metadata, but `ChatImages.verify` does not
   propagate its context/output limits to the active request's shared budget.
   The current public exact-ID catalog advertises `openrouter/free` as a router
   with image input and a 200,000-token context. That current declaration does
   not establish what every routed model accepted during the earlier session.
2. **One generic image estimate for all models.** `image_token_estimate` uses
   16×16 patches regardless of provider preprocessing. Thus this small second
   JPEG is charged 3996 estimated tokens locally. This is a conservative
   estimate, not observed provider image usage. Increasing JPEG compression
   alone would not change that dimension-based estimate.
3. **Admission follows already-recorded input.** The UI records the accepted
   user turn before the agent's final image/context projection. Preparation
   retry retention only handles failures before `input_started`. Later
   admission failures do not receive the same explicit attachment-retry state.
4. **Useful provider failure evidence is discarded.** Compatible image streams
   collapse every error event to `Model server reported a generation error`.
   Both later errors in this session are therefore ambiguous: no preserved typed
   cause establishes whether they were context, availability, image, policy or
   other upstream failures. Image completion metadata also omits the actual
   model selected by the free router.
5. **Request accounting can reuse earlier usage.** The local context rejection
   retains the preceding successful response's total usage in its completion
   metadata. A failed preflight must not inherit another request's usage.

### What the record does not prove

- The answer claiming pixels were unavailable is **not proof of host-side
  attachment loss**. That completed retry's capability metadata records one
  supplied image. The exact routed model and image-consumption outcome were
  not recorded, so the discrepancy cannot be resolved from saved evidence alone.
- Classification-like `User Safety` / `Response Safety` answers are observable,
  but the record does not identify a moderation model or prove why it responded
  that way. Do not add a text-stripping heuristic to turn them into success.
- The generic upstream errors do not establish a context overflow. The first
  rejection is conclusively local context admission; the two later failures
  reached the server and remain unclassified.

## Recommended architecture

Use one shared attachment preparation and request-budget path for chat and Media,
retaining their distinct permissions, settings, tools and persistence behavior.
Avoid adding a second agent or a large prompt instructing models to compensate.

### A1 — Repair request budgets, state and diagnostics first

- Resolve context/output/image capability evidence for the exact active endpoint
  and model, respecting connection/credential revisions and supported modes.
  Feed it into one request-budget authority used by compaction, image admission,
  token estimates and the UI. Retain an explicit user cap where configured.
- Keep native Ollama allocation distinct from cloud model limits. Do not
  increase local `num_ctx`, change models or allocate additional GPU memory
  silently. Unknown metadata needs a clearly identified bounded policy, not
  accidental inheritance of an unrelated local-runtime default.
- Account for system instructions, essential user text, complete tool pairs,
  schemas/protocol, images and output reserve together. Remove optional old
  context before rejecting a valid current attachment. Never discard constraints
  or split provider tool pairs to fit an image.
- Give attachment attempts explicit prepared/sending/failed/completed state,
  with stable private artifact references. A local admission failure retains
  the prompt and image for retry; an accepted turn that fails later retains a
  failed attempt rather than duplicating successful dialogue.
- Interpret explicit retry of a failed image attempt using that attempt's exact
  references, endpoint approval and question, not a vague text-only continuation.
- Record safe typed error code, requested/routed model, request identity and
  current image count when available. Keep raw error bodies, keys, images and
  reasoning private. Reset per-request usage before local validation and retain
  an honest unknown/unsent state for failures without measured usage.

### A2 — Prepare bounded image derivatives automatically

- Keep an immutable original in the private artifact lifecycle. Decode a working
  copy in an owned cancellable worker with source-byte, decoded-pixel, memory,
  output-byte and time bounds. Header checks alone are not full validation.
- Normalize EXIF orientation and supported color modes, handle transparency
  deliberately, and remove unnecessary metadata from transmitted derivatives.
  Preserve aspect ratio and avoid enlarging small images.
- Accept PNG/JPEG and add decoded static WebP/GIF normalization. Animation/frame
  selection must be explicit. HEIC/AVIF require separately tested decoder
  availability, not a promise based only on a filename extension.
- Cache a derivative by source checksum, decoder/preparation revision, provider
  profile, detail and target size. Source deletion after attachment, resume and
  provider changes retain the existing private approval/checksum guarantees.
- Use provider/model-specific documented sizing and estimates. For compatible
  endpoints without reliable evidence, use bounded conservative preparation and
  label the estimate as uncertain. Never infer exact patch rules from a model
  name or copy one provider's formula into every adapter.

### A3 — Adapt quality and active images to the task

- Default to **Auto**: a bounded overview for ordinary scene questions; more
  detail for screenshots, diagrams and small text when the request budget permits.
  Offer an explicit detailed/original option, subject to actual model limits.
- If fine detail does not fit, use bounded source-derived crops/zoom requests
  when needed, within the same approved provider and execution budget. Retain
  the source-to-derivative coordinate transform for spatial tasks. A small
  thumbnail or text recap is not equivalent to full-resolution pixel evidence.
- Separate stored attachments from images active in a particular request. Favor
  the current image and explicitly referenced earlier images; do not resend every
  historical image indefinitely. Make omitted images reactivatable from private
  originals without requiring reattachment of a deleted source file.
- Replace the universal two-image limit only after the shared budget/preparation
  path is validated. Large batches need visible bounded grouping; overview-only
  or sequential analysis must not claim simultaneous detailed comparison.
- Show concise preparation/presence state: source/prepared dimensions, active
  image count, detail reduction and retry action. No base64 or verbose internal
  planning state belongs in the ordinary chat UI.

### A4 — Make provider recovery predictable

- Keep `openrouter/free` available as an explicit user choice, but label it as a
  dynamic router and display the actual routed model when returned. Offer an
  explicitly selected vision model for repeatable behavior; never switch it
  silently or imply free routing guarantees availability or consistent output.
- Use typed context/image errors to trigger one bounded local re-preparation
  cycle where appropriate. Retry transient pre-output failures only within
  limits and honor `Retry-After`. Never retry cancellation, permanent auth,
  exhausted credits or policy rejection as if they were transient.
- After partial output or an uncertain request outcome, preserve the attempt
  and offer explicit retry; do not silently resubmit paid requests. Any model
  fallback must be preconfigured, reviewed and compatible with pixel approval.
- Do not claim a valid pixels count proves model comprehension. Surface empty,
  refused or unusable answers honestly without fabricated image descriptions.

## Current official guidance supporting the approach

- [OpenAI Images and vision](https://developers.openai.com/api/docs/guides/images-vision):
  detail, resizing and tokenization vary by model; image tokens and text must fit
  the context. Low detail is not universally cheaper. Apply only documented,
  reviewed profiles rather than a universal sizing formula.
- [Claude Vision](https://platform.claude.com/docs/en/build-with-claude/vision):
  provider/model resolution tiers, resizing, format and request limits are
  explicit; pre-resizing can reduce latency. Detail reduction affects small
  text and coordinates, so task-sensitive preparation matters.
- [Ollama Vision](https://docs.ollama.com/capabilities/vision):
  use native image inputs with a capable model. It does not document one universal
  image-token formula for every Ollama model; preserve that uncertainty.
- [OpenRouter free router](https://openrouter.ai/docs/guides/routing/routers/free-router):
  random feature-compatible routing, variable availability and a response field
  identifying the model actually used. Pinning an available exact model is an
  explicit user choice, not an automatic repair.
- [OpenRouter error handling](https://openrouter.ai/docs/api/reference/errors-and-debugging):
  errors can arrive inside HTTP-200 SSE streams; normalized typed error metadata
  supports actionable classification. HTTP status alone is insufficient.

These pages were actually fetched/read for this diagnosis. They inform the
proposed design; they do not certify future codec/model/provider support.

## Verification and acceptance gates

1. Start with A1, then A2; validate real one-shot and interactive runs after each
   meaningful change before adding batch/zoom features.
2. Regress the observed image dimensions and sequence with synthetic fixtures,
   a long existing conversation, unknown versus verified cloud metadata, explicit
   small native context, repeated retries, source deletion and process resume.
   Do not publish the user's images or use their content as a shared fixture.
3. Test format/color/orientation/transparency cases, panoramas, phone images,
   dense screenshots, corrupt/truncated files and decode/resource exhaustion.
4. Verify exact source/derived checksums, endpoint approval, output reservation,
   no silent model/context changes, no tool-pair breakage and no duplicate sends.
5. Use actual Gemma E2B/E4B and a declared compatible endpoint; keep paid-provider
   and OpenRouter generation evidence separate from controlled protocol tests.
6. Validate context/auth/quota/policy/transient/partial-stream failures distinctly,
   cancellation during decode/metadata/send and truthful final status/usage.
7. Run the relevant unit tests and full locked test/lint/type gates for actual
   implementation changes. A green suite alone is not an end-to-end image pass.

### Investigation performed now

- Read-only inspection and full local decoding of the three stored JPEGs; all
  valid. No model generation or image egress.
- Fetched the public exact-ID OpenRouter catalog (no credentials or image
  content sent): one matching entry, image/text input, 200,000 declared context.
- Controlled projector probe using the second image's reference dimensions and
  synthetic text, without transmitting pixels: an unknown active context still
  rejects at the 8192 fallback even when fresh inspected metadata says 200,000;
  propagating 200,000 into the stub active budget admits one image. This isolates
  metadata/budget inconsistency; it is not a replay of the original full request.
- Six focused current admission/restore/OpenRouter failure checks passed in
  5.54 seconds. They confirm existing contracts, not the proposed improvements.
- Local evidence: `/tmp/klaude-image-session-context-probe.json` and
  `/tmp/klaude-image-session-openrouter-model.json`. Source references:
  `chat_image_support.inspect_support`, `ChatImages.verify/capture/project`,
  `image_content.image_token_estimate`, `Agent._compact_history/model_messages`,
  `CompatibleRuntime.chat_stream`, and the CLI turn worker's `input_started`
  boundary in `apps/cli/src/klaude_cli/main.py`.

Recommended first delivery: **shared verified budgets, explicit retry state and
typed diagnostics; then automatic bounded image preparation**. Raising every
context window or removing image limits would not resolve the observed failures.

## Implementation follow-up (2026-10-16)

A1/A2 and the bounded A3/A4 attachment path are implemented. Real local Gemma
E2B/E4B one-shots, TUI crops from a deleted source's snapshot and process resume
passed at an unchanged 4096-token local context. The two-image request limit is
retained deliberately. Crops/frame/detail are explicit user actions; an autonomous
zoom tool and batch comparison are not introduced. Unknown provider patch costs
remain conservative estimates, and pixel delivery does not certify comprehension.
See the linked validation for exact evidence, full checks and provider limits.
