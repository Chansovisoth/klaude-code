# Klaude — Native Chat Image Generation, Repository-Aware Codex Handoff (v2)

**This document supersedes the earlier generic handoff. It combines that implementation specification with Codex's repository reconnaissance. Treat the reconnaissance as findings reported from a prior inspection, not as independently verified facts; recheck against the current worktree before editing.**

## Execution mandate and priority

Implement native text-to-image requests from normal Klaude chat using the **already configured local Stable Diffusion v1.5 backend**. Then complete durable turn/job/asset projection, reconnect and cancellation semantics, and real supported image editing. Keep the existing manual Image Studio as a functioning, polished entry point. Do not stop at a proposal, a refactor, mocked chat cards, or an intent recognizer that cannot produce a persisted real image.

**Order of importance:** (1) protect the existing worktree and image stack, (2) define identity, ownership, approval and recovery correctly, (3) build a minimal actual local generation vertical slice, (4) validate streaming/replay and image actions, (5) add real img2img where verified, (6) polish UX and run regressions. You may stage the implementation internally, but finish as much of the complete feature as environment and tests allow. Report genuine blockers precisely.

## Repo-specific findings from the earlier Codex preflight

Verify each claim at runtime/repository before depending on it:

| Area | Reported finding | Required handling |
|---|---|---|
| Stable Diffusion | `http://localhost:1234` with `v1-5-pruned-emaonly.safetensors`; metadata checks pass | Reuse this exact configured service/checkpoint; check API shape and actual inference capability before selecting edit APIs. Do not assume successful metadata probing proves inference. |
| Storage | Sources, builds and model files under `/mnt/HDD1/klaude-image` | Keep this arrangement. Do not copy checkpoints into the repo, alter model storage, or install a second engine. |
| Lifecycle | Runtime starts through a **transient** `klaude-image-setup.service` user unit | Do not claim persistent automatic startup or silently install/enable one. Expose disconnected/recovery state; only change service-install policy with explicit authorization. |
| Image Studio | Recently redesigned desktop composer/output columns, mobile stacking, previews/history/actions | Preserve the existing layout, controls, review flow, draft preservation and responsive behavior. Chat image cards should reuse preview/download affordances, not duplicate the studio. |
| Existing validation | Focused browser fixture walkthrough passed generation, review, cancellation, output preview/download, draft preservation and responsive checks | Treat these as fixture tests; do **not** call them a proven real inference test. |
| Known baseline | Broader management walkthrough fails on an earlier unrelated connection-review assertion; full suite not green | Record the failure as baseline if reproduced. Repair regressions caused by this feature; do not quietly rewrite unrelated expectations. |
| Worktree | Extensive intentional dirty changes | Inspect and preserve. Never stash, reset, force-checkout, commit, push or overwrite unrelated edits. |

### Existing flow — start here, not from scratch

```text
Image Studio (management.js)
  → prepareChange
  → LibraryManagement review/submit
  → operation journal / owned worker (browser_jobs.py)
  → ImageGenerationCommand
  → core image_generation.py
  → configured local Stable Diffusion
  → ArtifactStore (library_artifacts.py)
```

Reported primary files:

- `packages/application/src/klaude_application/browser_jobs.py` — reviewed generation, cancellation, recovery, operation ownership and journal.
- `packages/core/src/klaude_core/image_generation.py` — request/service validation, bounded execution, job receipts, unknown/uncertain outcomes and PNG validation.
- `packages/core/src/klaude_core/library_artifacts.py` (around line 343) — idempotent artifact storage and **private** generation provenance.
- `packages/application/src/klaude_application/service.py`, `coordination.py`, `contracts.py` — chat execution, fencing, snapshots, durable state, public projection and replay.
- `docs/webui/image-studio-validation.md` — what the Image Studio browser walkthrough has and has not demonstrated.

Chat reportedly already accepts image attachments and renders Markdown images, **but does not register an image-generation tool and does not persist generated artifacts as chat-turn results**. Do not mistake existing image input/display for completion of the feature.

### Explicit architecture decision

**Reuse the core operation and artifact boundaries**. Introduce a single application-level image-generation entry point that both reviewed manual Studio commands and authorized chat image actions can call without inventing a second generator or undermining the Studio's reviewed workflow.

Conceptual target:

```text
Studio manual request ── existing review/approval/journal ──┐
                                                            ├── shared validated image operation
Chat message ─ intent candidate / model tool ─ chat policy ─┘       │
          │                                       ↑                  │
          └─ durable turn/action identity ────────┘                  ▼
                                                owned execution / SD server
                                                          │
                                             validated ArtifactStore asset
                                                          │
                                         durable chat result projection
                                                          │
                                      snapshot + replay + authenticated UI
```

Do not route normal chat actions through a frontend-only `management.js` shortcut. Do not make users complete Image Studio's manual review wizard for every obvious in-chat request **unless** the actual existing permission policy requires a review/approval. *Reuse authorization policy, not necessarily the manual presentation.* No hidden elevation and no bypass of ownership, approval, tool permissions or admission checks.

## Non-negotiable engineering details missing from generic specs

### 1. Durable linkage *before* routing or execution

Define a stable, auditable relation among authenticated principal/owner, `session_id`, `turn_id`, request/submission identity, logical `image_action_id`, job/operation receipt, generated `artifact_id`(s), and published assistant result. Use the repository's existing identifiers and versioned contracts; do not invent parallel identifiers if types already exist.

- **Reserve/persist one action identity before calling SD.** A user submission replayed after transport reconnect, agent stream resume, LLM tool replay or application restart must resolve to the same admitted logical action.
- Put a database/operation-journal uniqueness constraint or equivalent atomic compare-and-create at the *authoritative* action boundary. A frontend debounce is not sufficient. For explicit multi-image requests, one logical action can own multiple output assets; never multiply entire generation jobs accidentally.
- Distinguish: (a) retransmitting the same intent, (b) user-requested *new variation*, (c) an explicit retry after a confirmed failure, and (d) an **unknown external-provider outcome**. (d) must not automatically re-invoke the provider.
- Persist job state and actual artifact IDs **before** notifying the chat projection of completion. Make publication idempotent. A crash after pixel storage but before chat projection must reattach the existing artifact, not regenerate it; use existing journal receipts/storage idempotency to reconcile.
- Fencing/session ownership: stale stream producers and superseded turns must not publish over current turns or leak to other sessions. Decide how a surviving independent job is reflected in the session after the initiating turn stops.
- If the SD adapter cannot prove whether an interrupted command actually ran, expose `unknown`/`interrupted` (using existing status vocabulary when possible) and require explicit recovery/retry. **Do not promise mathematically exact once execution of an uncooperative backend.** The guarantee is idempotent admission, publication, reconciliation when receipts exist, and no blind duplicate execution in uncertainty.

### 2. Structured public results, private metadata

Use existing public contract/projection/snapshot/replay mechanisms, with forward/backward-compatible extension and schema/test updates. A completed chat image result must be a **structured reference**, not an arbitrary Markdown URL pasted by the model. Authorize previews/downloads with the existing ArtifactStore endpoints and principal/session scope. No raw base64, local filesystem paths, SD backend URLs, generation provenance/private prompt transcripts, or sensitive settings in public chat events. The chat may show user-safe caption, job status and dimensions.

Persist original pixels only in the managed asset store. Retain immutable source/parent references for edits and correct gallery ordering. Refresh, `/resume`, reconnect, snapshots and replay must yield the same assets and statuses. Protect legacy clients against unknown event fields/types as the existing contract does.

### 3. Two decision sources, only one executor

For clear raster-image requests, provide a conservative low-latency routing path *and* a well-described model-callable image tool, because small local Ollama models may skip calls. All candidates go through **one** chat action arbiter → policy/admission → durable operation. A fast-path recognition and subsequent LLM tool call must not create two jobs. Respect explicit output modality (`generate a PNG` vs `build an SVG component`, `write an image prompt`, `find photos`, `analyze screenshot`). Contextual follow-ups need resolution against permitted assets, not keyword matching alone. On ambiguity, ask one focused question. Keep the user's selected chat LLM; the image executor is separate. Avoid unconditional slow second-model routing.

### 4. Editing must be substantiated by real installed capabilities

Earlier inspection says the local server **advertises initialization-image and mask fields**, but the actual Klaude adapter submits only text-to-image. Inspect its live schema and test actual image-to-image on the installed SD1.5 service with a small bounded request. If it succeeds, implement img2img using a real persisted source asset (immutable ID, owner check, content hash and expected revision). Keep output as a new derived asset, never overwrite the original. For inpainting, require an actual supported mask/workflow. Existence of an API field is not sufficient evidence that model, pipeline or UI can make reliable precise localized edits.

- `make it darker` → actual img2img with the referenced source if working; otherwise explain lack of edit support.
- `change only the sky` → inpainting with real mask if proven; otherwise request a mask or explicitly offer *broader* img2img with user consent. Never present unmasked txt2img as an edit.
- Deleted/missing/changed/cross-session sources → explicit safe error or clarification, not implicit reference to something else.
- Repeated gallery results → correctly identify `second image` relative to the relevant gallery and supported selected-image context.

### 5. Chat stop, image cancel and independent work

Write down the lifecycle contract **before** implementing controls:

- Distinguish `stop assistant turn`, `cancel queued image job`, and `cancel running image job`; don't let a browser disconnect implicitly cancel persistent owned work.
- Decide and document whether the image job is tied to the turn or may continue independently. Prefer continuing already admitted work under an owned job with a durable chat placeholder, unless existing semantics/policy clearly require cancellation. Use a job-scoped explicit cancel request.
- Respect SD server's shared queue. If only a global interrupt exists and the operation cannot prove exclusive ownership, **never globally interrupt an unrelated backend job**. Show `cancel requested`/suppress publication according to established recovery semantics if actual compute cannot safely be stopped.
- Expose only correlated progress; if unavailable show an indeterminate indicator. Reconcile complete/failed/cancelled/unknown states on reconnect and restart.
- Bound one-GPU concurrency, pending queue size, input/output sizes, timeout and retries; don't launch multiple inference processes.

### 6. Honest validation and baseline discipline

Record separate results for the following:

1. Existing Studio fixture/browser flows, including its responsive design and draft-preservation cases.
2. New deterministic tests for idempotency, approval, ownership, image intent negatives, duplicate chat+model arbitration, crash windows, projection/replay, bad/missing source and cancel isolation.
3. **Real txt2img smoke test** against the configured `http://localhost:1234` and actual checkpoint, with conservative parameters and controlled load. Validate stored image bytes and dimensions, not just a returned 200 or metadata ping.
4. **Real img2img smoke test** only if genuinely supported, feeding a real source image. Verify resulting pixels and lineage.
5. Appropriate repo lint/static checks/build and broader tests; compare known connection-review baseline failure honestly.

Do not destroy, reconfigure or automatically enable the transient service to make a test pass. If server is unavailable or the GPU cannot run the request, record that accurately and still implement robust fake-adapter tests. Do not claim the feature is end-to-end verified until real inference and durable chat presentation are proven.

### 7. Compatibility with the current polished UI

Image Studio remains intact. Use its existing preview/download/history patterns for chat result cards where appropriate, but keep chat cards compact. Mobile chat has limited vertical space: avoid a new always-visible image toolbar/model selector, excessive empty card padding, and a mandatory configuration dialog. Show a status + preview + small contextual actions. Accessible keyboard/touch behavior and reduced motion remain required.

### 8. Deliverable expectations

Implement the code as well as tests and contract updates. If there is a hard technical blocker, stop only at that blocker, leave a safe partial vertical slice, and give concrete evidence. The final report must include exact code entry points changed, a before/after architecture path, manual Studio regressions, new-chat behavior, persistence/cancellation semantics, the real inference status, tests run/failed/skipped, and whether img2img/inpainting was **actually** exercised. Do not commit or push.

---

## General implementation specification (retained and subordinate to the repo-specific instructions above)

## Mission

Implement **first-class, conversational image creation and editing** inside Klaude's existing chat, using **Klaude's already-integrated, locally hosted Stable Diffusion backend**. This is an implementation task, not just an RFC or mockup.

Today users must select **Attach → Generate image** and complete a manual characteristics/description form. After this change, a user should simply type:

> Generate a cinematic 16:9 image of a futuristic Cambodian city at night.

Klaude must recognize the intent, reuse its **current** Stable Diffusion integration, generate a real image, and show the result inline in that conversation. Follow-ups such as "Make it rainier," "Try a pixel-art version," or "Generate two more" should behave naturally, with actual image references when editing.

**Do not replace local Stable Diffusion with Ollama image generation, ComfyUI, AUTOMATIC1111, Forge, diffusers, or a cloud image API unless that is what Klaude already uses.** "Stable Diffusion" describes the underlying image-generation technology, not a known API. First discover the existing invocation path (which might be a Python diffusers pipeline, ComfyUI workflow, SD WebUI/Forge-compatible API, a custom service, or something else). Reuse and improve it. Do not build a redundant provider stack.

The user's chosen **chat LLM** and the configured **Stable Diffusion image model** are distinct: a text-only local Ollama model should be able to request an image operation without switching the chat model.

## Working rules / repo safety

- Repository: `/home/klaude/klaude-code`.
- Read `AGENTS.md` and applicable project instructions. Inspect `git status --short`, staged/unstaged diffs, and relevant code before editing.
- The worktree can contain substantial unrelated user changes. Preserve everything unrelated. No stash, reset, discard, force checkout, commit, or push.
- Follow existing backend/WebUI/CLI/TUI architecture, public bridge contracts, security, permissions, settings conventions, and tests.
- Keep the current WebUI theme, Material 3 Expressive-inspired visual language, responsive layout, image preview, motion, and components. **Do not redesign Theme or Agent, and do not add a new UI kit.**
- Use a small, comprehensible, typed implementation. Extend working services instead of creating a new agent loop, event bus, database, or image engine.
- Make the smallest complete vertical slice work end-to-end first, then add editing and polish. Do not leave a frontend-only prototype or simulated results.
- When infrastructure is not running, implement and test with fakes but clearly report which real-provider flows could not be verified.

## Phase 0 — Mandatory repository reconnaissance

**Before altering code, trace the existing implementation end-to-end.** Identify and record actual names/paths for:

1. The WebUI **Attach → Generate image** entry point, current dialog, form state, validation, settings and action handler.
2. The server request/command invoked by that dialog, including how prompts, characteristics, negative prompts, image size, count, seed and model settings are passed.
3. The **local Stable Diffusion runtime**: in-process pipeline, subprocess, ComfyUI, SD WebUI, Forge or custom API; lifecycle/startup, model/checkpoint selection, health checks, supported operations, timeouts, progress and cancellation.
4. Output storage: where images are written, how files become attachments, how previews work, and which metadata is persisted.
5. Chat orchestration: user request submission, intent/capability routing, model tool calling, tool schemas/execution, approvals, stream events, assistant message construction and completion semantics.
6. Session persistence/resume, conversation/image attachment references, auth/access controls, browser reconnect and CLI/TUI message rendering.
7. Relevant tests, integration harnesses, feature flags, build/typecheck commands and existing configuration screens.

Useful initial commands (adapt search terms to actual repository):

```bash
cd /home/klaude/klaude-code
git status --short
rg -n -i 'stable.?diffusion|txt2img|img2img|comfyui|forge|diffusers|generate.?image|image.?generation|inpaint|sdapi' .
rg -n 'tool_call|tool_result|attachment|asset|session|stream|cancel|permission' klaude webui tests 2>/dev/null
```

Create a brief internal implementation map: `composer/dialog → bridge/endpoint → generation service → Stable Diffusion → saved asset → message/preview`. Locate the best existing abstraction to expose the generator to chat. **Do not assume file or class names from this handoff exist.**

## Required user-visible behavior

### A. Generate from ordinary chat

- "Generate an image of an orange cat" → **one** text-to-image job; output appears in the chat.
- "Draw a 16:9 pixel-art landscape" → set compatible dimensions preserving 16:9 as closely as the checkpoint/runtime supports.
- "Make 3 variations of a glowing logo" → enforce configured output-count bounds and show a gallery of actual images.
- "Create a logo with a transparent background" → only promise transparency if the actual pipeline supports it; do not present a white-background PNG as transparent. Offer an honest limitation or a supported postprocessing operation.
- "Explain the concept, then illustrate it" → support mixed text + image work in one user turn, with one image operation as appropriate.
- Khmer/multilingual phrasing should work to the extent the selected chat model understands it; don't hardcode an English-only trigger list as the sole routing method.

### B. Edit and iterate on real images

- "Make the last image darker" → resolve the most recent unambiguous generated image in this conversation and invoke actual **img2img** with its bytes as input (not txt2img from a prose description).
- "Change only the sky" → use **inpainting with a valid region/mask** if supported and a region can be identified; otherwise ask the user to select/mask the region or clearly explain the limitation. Never pretend unrestricted Stable Diffusion img2img guarantees localized preservation.
- "Make the second one more colorful" → select image #2 from the previous gallery, not arbitrary image #2 in the session.
- "Use this uploaded picture as a reference" → connect an actual authorized uploaded image to the image-edit or conditioning workflow that exists; if no supported reference mechanism exists, do not silently ignore the reference.
- "Try again" / "Generate another" → regenerate with a new seed by default unless the user explicitly requests reproducibility. "Same seed" → reuse when supported.
- Keep originals and derivatives, so editing never destructively overwrites the source.
- When two or more images are equally plausible as "this one," ask **one** short selection question or use an explicit selected-image context from the preview.

### C. Do NOT accidentally generate

These are **not** generation tasks unless the user also asks for an actual new image:

- "Explain how Stable Diffusion works."
- "Write a Stable Diffusion prompt for a forest."
- "Search for images of Phnom Penh."
- "Describe this attached screenshot" / "What's in this picture?"
- "Build an HTML/CSS image gallery" or "Make an SVG icon component."
- "Do not generate an image yet."
- Requests for diagrams in code/Markdown, files, screenshots, browsing, or image analysis must obey their actual requested output format.

## Architecture — one shared image capability, two entry points

Expose the **existing local generator** through a shared backend application capability. Both the old manual dialog and the new chat tool call it. Conceptual flow:

```text
                       ┌───────────────────────────────┐
User chat message ─────►│ Existing chat orchestrator     │
                       │ Intent/tool decision          │
                       └──────────────┬────────────────┘
                                      │ typed image operation
Existing Generate Image dialog ───────┤
                                      ▼
                          Shared image service
                    validate • queue • execute • persist
                                      │
                                      ▼
                         Existing Stable Diffusion
                          runtime / API / workflow
                                      │
                                      ▼
                           Managed image asset(s)
                                      │
                                      ▼
                      Chat message + gallery + preview
```

Do **not** put detection/execution in React alone, create a parallel generation implementation, inject giant image payloads into the chat model history, or replace the normal conversation model with a diffusion checkpoint.

### Suggested logical data contracts (adapt to existing languages/types)

```ts
// Illustrative contracts — reuse existing types/schema names where possible.
type ImageOperation = 'text_to_image' | 'image_to_image' | 'inpaint' | 'variation';

type ImageGenerateRequest = {
  operation: ImageOperation;
  prompt: string;
  sourceAssetIds?: string[];      // Actual managed assets; required when editing
  maskAssetId?: string;          // Required when inpainting is used
  aspectRatio?: '1:1' | '4:3' | '3:4' | '16:9' | '9:16' | string;
  width?: number;
  height?: number;
  count?: number;
  seed?: number | null;
  // Keep Stable Diffusion low-level settings behind an optional advanced section
  steps?: number;
  cfgScale?: number;
  sampler?: string;
  denoiseStrength?: number;
  negativePrompt?: string;
};

type ImageJob = {
  id: string;
  conversationId: string;
  userMessageId: string;
  assistantMessageId: string;
  toolCallId?: string;
  idempotencyKey: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress?: { kind: 'determinate'; percent: number } | { kind: 'indeterminate' };
  assetIds: string[];
  errorCode?: string;
};

type ImageAsset = {
  id: string;
  conversationId: string;
  mimeType: string;
  width: number;
  height: number;
  byteSize: number;
  sourceAssetIds: string[];       // Revision lineage
  generationJobId: string;
  createdAt: string;
};
```

Keep provider-only fields separate from the generic agent-facing tool contract. Stable Diffusion parameters can be preserved as generation metadata with values actually used (including checkpoint, sampler, scheduler, CFG, steps, seed, dimensions, denoise, LoRA/workflow IDs when available). Do not write secrets into metadata.

### Chat tool / action

Expose a typed, permission-aware capability such as `generate_image` (use the project's existing tool registration mechanism). Tool description should state when to call it and when not to. Example behavior:

```text
Use this tool only when the user wants an image file generated, edited,
varied or refined. Use the existing local Stable Diffusion generator.
For editing, supply source asset references. Do not call for explanations,
prompt-writing, image search, image analysis or code-only artwork.
Do not call again simply because the client reconnects or restreams.
```

The selected chat LLM should remain the controller. Ensure routing works from **ordinary chat mode** and doesn't require toggling an unrelated agent mode. Avoid leaking image-generation metadata into unrelated agent tasks.

### Reliability with smaller local LLMs

A pure "hope the model calls a tool" approach can fail with smaller Ollama models. Build a **single authoritative decision/execution path**:

1. Prefer existing tool-call routing when the model supports it.
2. For **unambiguous direct requests** ("Generate an image of..."), a small deterministic fast path may construct an *intent candidate*, then pass through the exact same validation/execution service. This must not be a blind `image|draw|create` regex that hijacks code or writing requests.
3. For contextual/multilingual/ambiguous requests, use the current LLM-driven tool selection or a **small bounded structured intent step** only if warranted by what Klaude already supports.
4. Gate via a clear action arbitration rule so deterministic routing and LLM tool calls cannot each create a separate job. A unique user-turn/tool-action idempotency key must enforce **at most one actual job** per intended action, except explicit multiple requested images.
5. Do not run a second LLM merely to reword every normal prompt. Keep latency low and allow users to see job queued immediately when intent is certain.
6. If the request is ambiguous between a code artifact and a raster image, follow the explicit output format and/or ask a concise clarification; never produce a random image instead of requested code.

Tests must demonstrate successful routing with the **actual small local chat model(s) used in development**, not only a mocked ideal tool-calling model.

## Stable Diffusion-specific implementation requirements

### 1. Preserve the real backend and settings

Find the precise Stable Diffusion runtime Klaude already uses and its supported functions. If the current dialog already works, preserve its setup/configuration: endpoint or pipeline, checkpoint, scheduler/sampler, default resolution, steps, CFG, negative prompt, seed, batch size, LoRA, output directory and other existing options. **Do not unilaterally change their defaults.**

Detect actual runtime capabilities rather than assuming every SD checkpoint or API supports: image-to-image, masked inpainting, reference conditioning, transparent background, ControlNet, upscaling, multiple outputs or precise localized editing.

Provide a small capability report for use by the tool schema, request validator and UI. Example: `textToImage`, `imageToImage`, `inpainting`, `upscale`, `maskInput`, `supportedSizeConstraints`, `maximumCount`, `supportsProgress`, `supportsTargetedCancellation`. A disabled/unsupported operation should be clearly reported, not silently substituted.

### 2. Normalize human requests into supported SD parameters

- Infer **subject, scene, style, visual composition, colors, lighting, aspect ratio, count** and optional reproducibility requirements from the user request.
- Use the current generator's known-good defaults for unspecified steps, CFG, sampler, scheduler, negative prompt and checkpoint. Do not invent a globally optimal setting; different checkpoints have different recommended ranges.
- Map aspect ratios to valid physical pixel sizes according to model architecture/VRAM limits and dimension multiples supported by the installed pipeline. Respect configured maximum megapixels and count. On approximation, record dimensions actually used. Never claim 16:9 when silently returning square images.
- Preserve explicit content and style requirements when creating an SD-effective prompt. **Do not always append a giant generic "masterpiece, 8k, ultra-detailed" prompt** that overrides artistic intent. Distinguish `userPrompt` from `effectivePrompt` in metadata; keep prompt rewriting small, optional or adapted to existing implementation.
- Respect existing negative-prompt defaults and user overrides; don't assume every pipeline uses negative prompts.
- If a local LLM is used to extract structured settings, validate its output as untrusted data. If parsing fails, fall back conservatively, not to arbitrary/unbounded defaults.
- Clamp/reject unsupported values clearly: count, steps, CFG, denoise, width/height, aspect ratio, seeds and special options. Avoid the backend silently ignoring key user instructions.

### 3. Generate, img2img, inpaint: different operations

- **Text-to-image**: user prompt + supported SD settings → generated image(s).
- **Image-to-image**: reference source pixels + effective edit prompt + carefully chosen denoise strength (favor preservation for small refinements). Higher denoise generally causes larger changes, so make this configurable and provider-aware. Do not use text-only regeneration while labeling it "edit."
- **Inpainting**: real source image + valid mask/selected region + prompt + compatible workflow/model. If Klaude has no mask editor or corresponding pipeline, offer a supported broader img2img operation with an explicit limitation, or ask the user for a mask. Do not fabricate mask segmentation accuracy.
- **Variations**: new generation with intentionally varied seeds or SD settings, or a reference-conditioned variation if supported. Keep the original unmodified.
- **Regenerate**: repeat the chosen operation using preserved parameters, with a new random seed by default; deterministic reuse when explicitly requested.

Use local image files/managed assets for input; no unnecessary upload to external endpoints. Keep image dimensional transforms, alpha channels and EXIF handling safe and intentional.

### 4. Conditional backend notes — implement only the applicable branch

- **A1111 / SD WebUI / compatible Forge API:** inspect the running service's `/docs` schema. Common endpoints include `/sdapi/v1/txt2img`, `/sdapi/v1/img2img` and `/sdapi/v1/progress`; replies may contain base64 images. Decode on the server, enforce size limits, save managed images, and never stream base64 inside chat events. Global `/interrupt` and `/progress` may refer to shared work: guard against cancelling or showing another job's progress.
- **ComfyUI:** reuse current exported/versioned API workflow(s) and node IDs; submit to `/prompt`, correlate the returned `prompt_id`, subscribe to `/ws` if already used, retrieve outputs from history/view, and use the running version's targeted cancel mechanism when available. Do not replace the user's workflows or send global interrupt/clear commands that affect unrelated work.
- **Python diffusers/in-process:** reuse loaded model/pipeline, avoid reloading for every chat turn, manage GPU execution with a bounded worker/lock, check cancellation cooperatively if supported, and use the current runtime's memory/precision/offload strategy. Don't indiscriminately flush GPU caches or terminate other inference processes.
- **Other/custom service:** preserve its contracts and add the minimal adapter capabilities actually supported.

## Job management, GPU limits and durability

Image generation can be expensive on local hardware, and chats can reconnect/resume mid-run.

- Use the existing job/event/queue mechanism if one exists. Otherwise add the smallest persistent job record and bounded server-side execution worker (not a new orchestration platform).
- States: `queued → running → completed | failed | cancelled`. Represent the initial server acceptance as a stable job ID, and persist terminal status plus asset IDs.
- Ensure **idempotency** across HTTP retries, stream reconnects, agent replays and duplicate tool results. Distinguish retrying delivery from intentionally regenerating an image. A duplicate request with the same action key must return the existing job/result.
- Apply sane configurable bounds: maximum image count, dimensions/pixels, simultaneous jobs (default conservative for one local GPU), pending queue size, request payload size, GPU allocation and timeout behavior. Guard against accidentally launching many parallel SD instances.
- Progress must be truthful. Show percentages only when they correspond to **this job**; otherwise show "Queued" or an indeterminate generating state. Don't invent elapsed-time forecasts.
- **Cancellation is job scoped**: cancel pending work immediately. For running work, only send a backend interrupt if known to target the current Klaude-owned job; otherwise mark cancel requested and finish/discard safely under the existing policy. Never stop someone else's ComfyUI/A1111 job.
- Handle disconnects without cancelling by accident. On restart/resume, reconcile stored jobs with provider state when possible; otherwise mark interrupted jobs honestly as interrupted/retryable. Never mark an unknown state as successful or resubmit blindly.
- Failure states: no SD backend configured, backend unreachable, checkpoint unavailable, invalid workflow/model, unsupported edit mode, OOM, invalid image/mask, backend timeout, malformed output, disk full and user cancellation. Map to short actionable UX messages; keep actionable diagnostics in safe server logs.
- A final assistant response must not claim a generated image exists unless at least one validated asset has actually been persisted.

## Asset persistence, messages and context

1. Save the actual output files in Klaude's existing asset storage; avoid arbitrary agent-chosen output paths. Preserve original full-resolution images and generate optimized thumbnails only if the current preview implementation requires them.
2. Create stable **asset IDs** and durable metadata: owner/session/conversation/job, source/parent asset IDs, MIME, hash, dimensions, original/effective prompt (subject to current privacy design), provider/backend identifier, checkpoint/workflow, parameters and timestamps. Reuse existing schemas and make backward-compatible migrations.
3. Link job and resulting image asset(s) to a persistent assistant message in the correct conversation, rather than relying only on transient local React state. Ensure images appear after refresh, reconnect, export/import as supported, and `/resume`.
4. In conversation context, provide bounded image references/metadata (IDs, order, captions, source chain). Do not append base64 image data or huge generation metadata to every language model prompt. If the LLM needs visual understanding, use the existing image-understanding pipeline when supported.
5. Resolve deictic references ("last one", "second", "the attached image", "that picture") against actual conversation-scoped assets. Respect edits to earlier images and avoid leaking references across conversations.
6. Downloads and previews should be served by authenticated/authorized endpoints. Validate signatures, decoded pixel counts and encoded byte counts; reject path traversal, malformed images and decompression bombs. Never expose arbitrary files from the workspace through an asset ID.
7. Decide and test deletion semantics: image assets should follow Klaude's existing conversation/media retention behavior; do not leave orphaned files on repeated retries or abandon files on partial failure.

## Streaming / bridge contract and frontend

Reuse Klaude's versioned chat/WebUI bridge and tool-lifecycle messages. Extend it minimally to represent image jobs/assets. If there is an existing event format, use that instead of inventing the following names:

```text
image.job.queued      { jobId, messageId, status }
image.job.started     { jobId, status }
image.job.progress    { jobId, percent? }     # only real, correlated progress
image.job.completed   { jobId, assetIds[] }  # actual persisted assets
image.job.failed      { jobId, code, message }
image.job.cancelled   { jobId }
```

Messages/events must carry stable IDs, obey existing authorization/ordering, and reconcile correctly after reconnect. Avoid giant inline blobs in SSE/WebSocket payloads. Keep chat responsive while a job is running.

### WebUI details

- **No extra mandatory controls in composer.** Natural language in the normal message box triggers generation. Keep Attach → Generate image as an advanced/manual path using the shared service.
- Show one compact **inline assistant card**: "Queued" → "Generating image" (with spinner or truthful progress) → image preview; no pop-up wizard or huge settings block.
- Completed state: correctly sized responsive thumbnail/card with existing image preview on click/tap, full-resolution Download, and compact contextual actions **Edit / Regenerate / More** if they fit established Klaude action styling. Multiple results use a responsive gallery.
- Clicking **Edit/Refine** should preselect the corresponding asset context and focus the chat composer with an unobtrusive hint (e.g., "Editing image") so "make it darker" targets the intended image. The hint can be cleared. Do not force the existing manual form open unless the user explicitly chooses advanced editing.
- On mobile, maintain available vertical chat space; don't add a persistent model-picker/image-toolbar row. Respect keyboard safe areas, reduced-motion settings, accessible names, focus, pending state and touch targets.
- Show useful localized error state and **Retry** for retryable failures; **Cancel** while queued/running; do not hide a failed generation silently.
- Chat model selector remains unchanged; put generator configuration in existing **Settings → Models** or current image settings location, using existing design patterns. Don't duplicate generator selectors in multiple places.
- Preserve the current image preview component, Library/Integrations-level layout quality, colors, typography, rounded surfaces and animation language; avoid competing button styles.

### Settings / local-only behavior

Reuse the current Stable Diffusion setup rather than inventing a second setup flow. In the current configuration location, show a clear **Image generation: Local Stable Diffusion** label, configured checkpoint/backend identity when known, ready/disconnected state and genuinely supported operations. Advanced steps/CFG/seed/sampler parameters remain optional and nonintrusive.

**No automatic cloud fallback.** Never send prompt, images or local project data to OpenAI, Gemini or a hosted image service merely because local SD fails. If optional cloud support already exists, it is opt-in and governed by existing provider/permission rules; it is not required for this feature.

## Security and permissions

- Chat tool inputs are untrusted. Validate against schemas and caps on the backend; don't permit an LLM to set arbitrary server URL, checkpoint path, filesystem output path, executable, custom-node script or untrusted workflow JSON.
- Service endpoint addresses and credentials must come only from trusted settings. Preserve loopback/private-network boundaries and avoid SSRF, especially if Klaude WebUI is remotely accessible. Do not expose a raw unauthenticated Stable Diffusion endpoint through the browser.
- Use existing authentication for job and asset ownership. Prevent cross-conversation or cross-user image access.
- For requested generation with the explicitly configured local provider, don't insert redundant permission confirmations. If the user requests writing a generated image into a repository path, that is a **separate file-write operation** respecting the existing tool permission model.
- Do not expose local project files as source images without explicit user intent and existing file-read permissions.
- Do not log base64 images, auth tokens, large prompts unnecessarily, or secret-bearing metadata. Preserve the existing local-first retention/privacy policy.

## Suggested implementation stages — finish each slice, then extend

### Stage 1. Shared service and direct text-to-image

- Identify existing service and migrate/reuse the manual dialog's code path if necessary.
- Define normalized request/result/asset contract, backend validator and capability discovery.
- Add a typed `generate_image` tool/intent route from normal chat.
- Produce a real saved image and attach it to the assistant chat message. Existing dialog must continue to work.
- Show one minimal loading/result card.

**Gate:** "Generate an image of a red fox" generates exactly one real local SD image and remains visible after refreshing the page.

### Stage 2. Quality and reliability

- Add job queue/bounded concurrency, idempotency, useful failure handling, server-side cancellation where safe, correlation-aware progress and reconnect/resume.
- Test direct requests, negatives and smaller local LLM routing.
- Persist real job/asset lineage/metadata and ensure auth checks.

**Gate:** queued/failed/cancelled/completed operations are consistent after reconnection; no duplicate generations or cross-job cancellation.

### Stage 3. Conversational image editing

- Resolve image references using persisted conversation context.
- Implement supported img2img and optional masked inpainting using existing SD backend. Preserve originals/revision lineage.
- Make the selected image available from preview/chat actions. Add multi-image gallery and regeneration with controlled seeds.

**Gate:** "Make the last image darker" sends the actual last image as source bytes to an editing-capable pipeline and renders a new saved revision; unsupported precise edits are handled honestly.

### Stage 4. UX refinement and regression verification

- Align empty/queued/generating/succeeded/failed/cancelled cards with Klaude's existing patterns.
- Test small/mobile viewports and keyboard, accessibility, existing preview/download flows and manual dialog.
- Validate CLI/TUI graceful rendering of generated assets or path/link using the shared backend, without requiring a new full-screen image viewer.

**Gate:** normal chat, mobile, session resume, old Generate Image dialog, tool permissions and chat streaming all remain usable.

## Mandatory verification matrix

Add focused unit/integration/contract tests using the repository's testing conventions:

| Area | Minimum scenarios |
|---|---|
| Intent positive | generate/draw/render; 16:9, portrait, three images; multilingual where supported; mixed explain+illustrate |
| Intent negative | explain SD; write an image prompt; find images; analyze screenshot; build SVG/HTML; "don't generate" |
| Model routing | small local Ollama chat model (if available); no agent-mode requirement; at most one job per action |
| SD mapping | valid dimensions, bounded count/steps/CFG, model capabilities, preserved prompt, negative prompt, real seed, safe defaults |
| Generation | one valid file generated, correct dimensions/MIME, real assistant message attachment, full-resolution download |
| Editing | last and second image resolution, selected preview, real img2img source bytes, inpaint mask required, revision lineage |
| Durability | refresh, reconnect, `/resume`, duplicate request IDs, replay, retry, export/import as supported |
| Failures | no model, offline SD, malformed image, OOM/timeout, disk full, cancelling queued/running work |
| Isolation | shared backend progress/cancel isolation, asset auth, path traversal/SSRF, prompt/private file boundaries |
| UX | desktop and narrow mobile, responsive gallery, preview, edit, regenerate, cancel, retry, keyboard/accessibility |
| Regression | existing manual generation dialog, attachments, chat streaming, CLI/TUI, unrelated tool calls, typecheck/build |

Use a fake/recording Stable Diffusion adapter for deterministic tests, plus **at least one real local SD generation** if the configured service is runnable. For edit, test real img2img if available. If hardware/runtime isn't available, do not claim end-to-end success; report exact unverified stages. Inspect output bytes and dimensions, not just an HTTP 200 response.

Run appropriate unit tests, lint, static type checks and WebUI build. Address failures caused by this change; report pre-existing failures separately. **Do not hide tests or silently skip critical checks.**

## Delivery report

When finished, provide:

1. The discovered Stable Diffusion integration type (in-process diffusers / ComfyUI / A1111-compatible / other), actual entrypoint and supported operations.
2. Concise architecture map showing the existing dialog and new chat tool sharing one service.
3. Files changed and visible UX behavior.
4. Specific local generation/editing scenarios exercised and results (real vs mocks).
5. Tests/build/typecheck commands and outcomes.
6. Any genuine restrictions (e.g., no inpainting/mask support, no targeted cancel, GPU limits), with a minimally invasive next step.
7. Confirm worktree preserved; **do not commit or push**.

**Definition of done:** A user types a direct image request in Klaude chat and receives an actual locally generated Stable Diffusion image inline with reliable persistent state. A subsequent edit uses the image's real asset when supported. No mandatory image dialog, no invented success, no unauthorized cloud processing, and no regression to the existing generator.

## Official reference material (confirm against installed runtime/version)

- AUTOMATIC1111 WebUI API and live `/docs`: https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API
- AUTOMATIC1111 API route implementation: https://github.com/AUTOMATIC1111/stable-diffusion-webui/blob/master/modules/api/api.py
- ComfyUI self-hosted server routes/WS: https://docs.comfy.org/development/comfyui-server/comms_routes
- ComfyUI OpenAPI contract (version-sensitive, including job IDs/cancellation): https://github.com/Comfy-Org/ComfyUI/blob/master/openapi.yaml
- Diffusers img2img behavior / denoising strength: https://huggingface.co/docs/diffusers/main/using-diffusers/img2img
- Diffusers inpainting / real masks: https://huggingface.co/docs/diffusers/main/api/pipelines/stable_diffusion/inpaint
