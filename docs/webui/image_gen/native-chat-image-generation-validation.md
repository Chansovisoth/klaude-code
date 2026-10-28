# Native conversational image generation — implementation and validation

Implemented in the existing dirty worktree, 2026-10-28. No commit, push, stash,
reset, production-host restart, engine install, model download or storage move.
The v2 handoff in this directory is the implementation reference.

## Behavior and execution boundary

Ordinary Standard chat requests such as “Generate an image of an apple”, “Draw a
cat” and “Make the last image darker” use a conservative direct intent path. This
works independently of small local models choosing to call tools. The normal
model-callable `generate_image` tool reaches the same arbiter/executor; the selected
chat model is retained. Prompt-writing, search, screenshot analysis, code/SVG,
negation and explanatory requests are excluded from deterministic routing. Plan
mode and other restricted scopes never use this path. Ambiguous multiple-image
references ask which image to use; first/second/third/last resolve within a gallery.

The existing tool policy and structured approval broker run before reserving a
job. The local image capability defaults to Allow; saved Ask first, Deny and tool
availability settings remain effective. A disabled/unavailable/changed image
service returns a safe error and retains the user's request. There is no cloud
fallback. Conversational execution requires the saved local sdcpp service; manual
Studio retains its other existing provider behavior.

Both Studio and chat use `LibraryManagement` → existing operation journal and owned
worker → `ImageGenerationCommand` → core `image_generation` → existing configured
Stable Diffusion → `ArtifactStore`. Studio's review and draft flow is preserved.
There is one implementation of provider execution and pixel publication.

## Durable identity and lifecycle

`application_image_actions` lives in the existing session SQLite database, with a
unique `turn_id`, action identity, canonical assistant row, private child specs,
position, operation receipt ID, assets, state and compare-and-set version. The
existing admitted request/turn links it to the authenticated local owner and
session. `application_image_sources` records explicitly snapshotted attachment
references. No second image-worker or artifact database is introduced.

Before provider execution, one logical action and its assistant placeholder are
saved under the turn fence. Child IDs derive from the turn/action and child index.
The existing operation journal admits those exact child IDs. A duplicate chat
request ID or duplicate model tool call returns the original action. Explicit new
messages/variations are new user requests. Generic retry of an unresolved image
reply is rejected. The UI hides generic response retry on image cards and offers
an explicit draft retry only for definite failures.

The monitor is active only while there are admitted jobs. It serializes chat image
children across the shared chat database, allows up to eight pending actions and
one to three outputs per request, and uses existing server queue/process bounds.
Manual Studio and external clients still share the server's queue; chat does not
claim exclusive use of the GPU. Width/height are 256–1024 in multiples of 64, steps
1–50, outputs bounded to 8 MiB. Default size is 512px and default steps are 20.
Random seeds are chosen and persisted before chat submission; explicit seeds and
“same seed” remain reproducible. There is no invented progress percentage.

Stored pixels are linked by the existing unique generation job ID. If publication
is interrupted after pixel storage, reconciliation attaches the existing artifact
without invoking generation again. Child completion and asset lists update the
original assistant row, including after stopping the initiating turn or starting
a newer turn. Snapshot/replay uses a small `image.changed` signal and structured
`image_action` projection with safe IDs/dimensions, never raw image bytes, backend
URLs, filesystem paths or private generation prompts.

Stop assistant cancels the chat wait; admitted images continue independently.
Cancel image cancels queued actions immediately or sends the existing job-scoped
native cancellation. A cancellation before native acknowledgement remains pending
until the exact job ID exists. No global interrupt is sent. A completion racing
with cancellation keeps its real saved output. Disconnecting a browser has no
cancellation effect.

Transport loss, invalid output and uncertain admission become Outcome unconfirmed.
They never blindly resubmit. Check original output checks only the acknowledged
native job through existing recovery; no native ID means no safe recovery. Exact
failed/cancelled native evidence is retained as terminal. A fresh application
reconstructs the same persisted assets and deduplicates the original request.
Legacy text-to-image receipts remain valid across the additive img2img capability.

## Real source-image editing and UI

Chat image cards now reserve a responsive placeholder for each pending output
(up to the existing three-output bound). A CSS halftone dot field moves while
starting/running; queued/cancelling states retain a still pattern. Both the saved
and system reduced-motion preferences stop it. Finished assets replace their
placeholders; failures, cancellation and unknown outcomes remove pending tiles.
The same media-card frame is used while waiting, creating and cancelling, with
known requested dimensions, Local generation and an integrated Cancel control.
Failed/cancelled jobs retain compact explanations and Retry drafts; uncertain
jobs retain Check original output. The existing execution bar and Execution
details diagnostics stay separate and available. No progress percentage or
output dimensions are invented, and no generation API changed.

The updated `scripts/webui_chat_images_smoke.py` passed the full isolated chat
walkthrough, including eight halftone layouts (320/390/768/1440px, light/dark),
observed animation movement, reduced motion, output preview/download/edit/reload,
cancellation and failure cleanup. Screenshots in
`/tmp/klaude-chat-image-evidence/generating-*.png` were inspected at phone and
desktop sizes. JavaScript syntax, scoped Ruff, Expressive bundle consistency and
`git diff --check` passed. This placeholder validation uses the recording image
service fixture; it does not add a live inference or deployment claim.

Img2img checks the installed native capability and supplies the actual source
pixels as `init_image`, with strength 0.35 by default. Source IDs must belong to
this conversation's generated history or an explicitly attached snapshot. Their
expected revision, SHA-256, encoded size and decoded pixel bounds are checked;
missing, changed, archived and cross-session sources fail explicitly. Output is a
new artifact with private parent ID/hash/revision and generation provenance. The
parent is never overwritten. Repeated galleries retain order; selecting Edit or
Regenerate sets an exact source context in the composer.

The compact inline result uses existing authenticated Library image preview and
content/download routes. Open, Download, Edit, Regenerate, Cancel image, Retry
(draft) and Check original output are contextual. Source selection is clearable
and disappears on sign-out/session changes or successful submission. Thumbnails
reserve known dimensions and use proportional media cards with compact headers
and Edit/Regenerate footers. Square previews target 420px, landscape uses up to
the reading width, and portrait height stays within 560px/70dvh. Pending halftone
tiles use those same ratio/size bounds and reduced-motion handling. See
`../generated-image-card-validation.md`. The existing model
picker and manual Studio layout are preserved.

Inpainting is intentionally unavailable: advertised mask fields do not establish
a verified model/mask/UI workflow. “Change only the sky” asks for a masked workflow
or explicit consent to broader img2img rather than pretending a localized edit.

## Verification

All fixture tests below exercise actual application, journal, subprocess worker
and artifact boundaries with a recording local HTTP diffusion fixture. They are
not evidence of GPU inference.

- Initial image/chat/settings regression batch: **94 passed** in 100.34s.
- Chat-specific regression batch: **21 passed** in 52.25s; subsequent focused
  checks passed for fresh-instance/unresolved-retry handling (2), final model and
  scope behavior (4), and queued/native-ack cancellation races (3). The additive
  legacy-receipt test also passed.
  Coverage includes permission/approval, Plan mode, model-callable
  execution, intent negatives, duplicate tool/request arbitration, fresh SQLite
  application deduplication, canonical unresolved retry rejection, gallery order,
  real attached-source transport, changed/cross-session source rejection, stopped
  turns, early cancel, definite backend failure versus invalid-output uncertainty,
  lost-publication repair and uncertain-admission no-replay.
- Application bridge, coordination, sessions and attachments: **78 passed** in 37.71s.
- Existing WebHost and parallel-session regression files: **44 passed** in 39.86s.
  Their expected production tool inventory now includes `generate_image`.
- Existing Image Studio Chrome walkthrough passed: widths 320, 390, 768, 900 and
  1440; Image/Research drafts, review, ratios/advanced controls, output preview,
  download, repeat, cancellation and service failure, with zero console errors.
- New Chrome chat walkthrough passed: widths 320, 390, 768 and 1440, light/dark,
  reduced motion, no horizontal overflow, 44px output actions, inline decoded
  images, selected-source editing, preview/download, reload preserving asset IDs,
  cancellation and definite backend failure. Screenshots were visually inspected.
- Scoped Ruff and application/core mypy pass; Node syntax and Expressive bundle
  freshness pass. All seven workspace packages built as sdists and wheels (14
  artifacts in `/tmp/klaude-chat-image-builds`). Offline build initially lacked
  Hatchling in the temporary cache; the normal isolated build succeeded after
  resolving its declared build dependency.

Reproducible commands (set a writable `UV_CACHE_DIR` as needed):

```bash
uv run --frozen --offline pytest tests/unit/test_chat_image_actions.py -q
uv run --frozen --offline pytest tests/unit/test_image_generation.py tests/unit/test_web_media_settings.py -q
uv run --frozen --offline python scripts/webui_chat_images_smoke.py
uv run --frozen --offline python scripts/webui_image_studio_smoke.py
uv run --frozen --offline python scripts/chat_image_real_smoke.py
python3 scripts/bundle_webui_expressive.py --check
```

The last command invoking `chat_image_real_smoke.py` performs **real inference**;
it first requires the configured service to be idle, uses isolated temporary chat
and Library state, and does not start/reconfigure the server. Do not run it as a
routine unit test or concurrently with another inference workload.

### Actual installed Stable Diffusion inference

The existing `http://localhost:1234` service used
`v1-5-pruned-emaonly.safetensors` under `/mnt/HDD1/klaude-image`. Its transient
`klaude-image-setup.service`, CUDA build and `--offload-to-cpu` command were left
unchanged. Actual server logs identify TXT2IMG and IMG2IMG, including preprocessing
the supplied source image. No second diffusion engine or cloud provider was used.

The isolated application retained `qwen3:0.6b` as its chat runtime. These direct
requests did not need an LLM routing inference. The final 512 × 512, 20-step test:

| Operation | Seed | Persisted PNG bytes | Time | Stored asset |
| --- | --- | ---: | ---: | --- |
| Generate red apple on wooden table | 42 | 575,089 | 58.85s | `media:aaa950d4e8cb449886fca8b0e7774df7` |
| Refine same image with darker/blue-light request | 43 | 549,286 | 32.18s | `media:d26deded688447f28c2eb369534991e4` |

Full PNG decoding, dimensions, distinct SHA-256 hashes, exact source lineage and
same asset projection after closing/reopening the application passed. A separate
Chrome session also reopened these **real saved assets**, rendered both
inline, opened the full preview, and downloaded a PNG with the original SHA-256
(`/tmp/klaude-chat-image-real-browser.log`, screenshots `real-chat-390.png` and
`real-chat-1440.png` in the same evidence directory). This used no new inference.
Visual inspection shows a recognizable sliced apple on wood and a structurally related
refinement. The requested darker/blue lighting is weak; the test proves genuine
source-based execution/persistence, not precise aesthetic instruction adherence.
Earlier 256px/4-step and 256px/20-step tests decoded successfully but produced
visually degraded abstract output. They are not presented as good-quality images.

Evidence: `/tmp/klaude-chat-image-real-ynge7ka1/report.json`, `generated.png`,
`edit.png`; logs `/tmp/klaude-chat-image-real-512.log`;
`/tmp/klaude-chat-image-evidence/` and `/tmp/klaude-image-studio-evidence/` contain
browser fixture screenshots, which are separate from the real output PNGs.

## Files changed for this feature

- Application: new `chat_image_actions.py`; `service.py`, `contracts.py`,
  `library_management.py`, `browser_jobs.py`.
- Core: `image_generation.py`, `library_artifacts.py`, `memory.py`, `config.py`,
  `tool_settings.py`.
- WebUI: `host.py`, `static/app.js`, `static/media.js`, `static/expressive.css` and
  generated `static/style.css`. Existing Studio and unrelated settings changes in
  these files were preserved.
- Validation: new `tests/unit/test_chat_image_actions.py`,
  `scripts/chat_image_real_smoke.py`, `scripts/webui_chat_images_smoke.py`;
  small extensions to `tests/unit/test_image_generation.py` and
  `tests/unit/test_webhost.py`. Updated this document and the product guidance in
  `AGENTS.md`.

Other dirty files and existing untracked configuration/handoffs were not part of
this implementation and remain in place.

## Remaining limits and validation boundaries

- No verified mask/inpainting UI, video generation or alternative diffusion engine.
  General img2img can alter unrelated parts of an image and may weakly follow a
  refinement instruction. The current model is SD1.5, with its inherent limits.
- Intent routing is conservative English plus a model tool for other phrasing;
  multilingual/tool choice quality was not benchmarked. There is no unconditional
  second routing model, automatic model switching or recovery inference retry.
- Exactly-once remote execution cannot be promised after loss of an uncooperative
  backend acknowledgement. Unknown outcomes stay explicit and never resubmit.
  Session deletion is blocked while image work is unresolved; Library retention
  remains independent of session deletion.
- Standalone CLI/TUI chat still uses its existing terminal orchestration; this
  change integrates WebUI/headless chat and does not add terminal image rendering.
- Existing text exports/branches do not embed image bytes or clone private image
  action ownership into a different conversation. Normal resume/reload retains
  the original session's structured references.
- The production WebUI process was not restarted/deployed during this task. An
  already running older host needs restart and browser reload for the new backend
  capability. The transient diffusion unit is not installed as an automatic boot
  service.
- The full repository suite is not claimed green. Broad host-inclusive mypy still
  reports existing unrelated errors in `model_store_catalog.py:88` and
  `host.py:1211/1213`; broad host Ruff retains its existing E501 at `host.py:400`.
  The older management walkthrough has the previously recorded connection-review
  failure before reaching Image Studio; it was not rewritten to bypass it.
  Browser tests use simulated viewports, not physical phone/keyboard testing.
