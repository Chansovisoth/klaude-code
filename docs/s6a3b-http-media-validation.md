# S6a3b: reviewed HTTP Media analysis

Date: 2026-10-15. Builds on [S6a3a chat images](s6a3-http-chat-images-validation.md)
and [S6a1 Media analysis](s6a-local-vision-validation.md). Reviewed Media analysis
now supports native Ollama, native Anthropic Messages and compatible HTTP
endpoints with declared image support. S6a3 remains partial: SDK adapters and
paid-provider certification remain open; S6b generation/S6c tags are unstarted.

## Implementation

- AI Defaults → Vision allows the supported HTTP endpoints for its explicit
  model and ordered fallbacks. Missing authentication/disabled endpoints remain
  unavailable. Declared thinking-required Anthropic models are unavailable to
  this thinking-disabled Media consumer; their supported chat modes remain intact.
- Settings, preparation, analysis and chat share core `vision.inspect_model`.
  Exact-model Anthropic capabilities and compatible input modalities remain
  mandatory; unknown compatible catalogs may use an already configured native
  Ollama peer at the same root/auth scope. Negative evidence is not overridden.
  Chat additionally verifies that its active runtime still matches the captured
  binding. Capability inspection neither loads a model nor sends pixels.
- `library analyze` and Library → Media → Analyze image retain the existing
  owned-worker lane, private forms/results, Back-focused reviews and model/queue
  gates. Reviews list the exact image, endpoint/model, output/context bounds and
  all approved fallbacks. Declining or disabled Vision sends no pixels.
- Native Ollama retains `/api/chat`, disabled thinking and explicit `num_ctx`/
  `num_predict`. HTTP adapters reuse existing native provider runtimes, neutral
  image parts and completed SSE validation; no tools are supplied or executed.
  Anthropic sends image-before-text base64 sources with disabled thinking;
  compatible requests use image data URIs and the reviewed output limit.
- HTTP context is a conservative local input admission limit. The form, review
  and CLI explain that server allocation remains server owned. The existing
  chat image estimate is shared with Media; declared context/output limits and
  Anthropic's 7,500,000-byte raw image limit are checked before review/send.
  Existing PNG/JPEG, 8 MiB, 4096-per-side and four-megapixel bounds remain.
- Media tightens shared HTTP stream limits to **1 MB total response, 256 KB per
  event and 32,000 text characters**. Ordinary chat retains its previous defaults.
  A timer bounds generation to 90 seconds even during pre-header stalls or
  slowly arriving events. Partial, blank, oversized, tool, incomplete and output
  limit responses never produce a completed result or trigger fallback.
- Fallback eligibility retains the existing typed network/timeout/temporary
  status policy, including 429/503/529. Only reviewed references may run; the
  result reports the actual model and failed attempts. Authentication, missing
  capabilities, changed revisions and protocol/quality failures do not fall back.
- Metadata may require a catalog plus a configured native peer. Shared outer
  worker allowances are **15 seconds for inspection, 60 seconds for preparation,
  110 seconds per analysis model**. These include metadata/cleanup overhead;
  individual metadata requests remain bounded to six seconds and generation
  remains 90 seconds. CLI/TUI use the same constants, avoiding cancellation by
  an outer deadline before an otherwise valid inner request completes.
- Image/settings/definition/credential revisions are rechecked before delivery
  and result publication. Original files, stored bytes/tags, chat, research and
  knowledge remain independent. Results are private and unsaved. Owned cancel
  reaps the request process before releasing the task lane.

Wire references: [Anthropic Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
and [Ollama's compatible image API](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx).
These support the existing transport contract; this pass does not claim paid
Anthropic certification or broad visual reasoning accuracy.

## Concrete issue repaired: deletion through a native alias

`ollama_manager.role_models` previously recognized only `ollama` references.
Selecting Vision through a compatible endpoint at the same Ollama server left
that model unprotected in native Model Manager. A regression reproduced the
failure: expected `bound`, received `ok`, with the mocked native delete permitted.
Log: `/tmp/klaude-s6a3b-alias-before.log`.

The shared role check now recognizes native and compatible references at the
same normalized root. Tests cover Default Chat, Utility, Research, Utility
fallbacks, Vision and Vision fallbacks; deletion is blocked before HTTP DELETE.
Different endpoint roots remain separate. This also protects active compatible
session references supplied to the same role checker. Model/endpoint disable
and removal keep their existing revision-checked role guards.

## Real CLI/TUI evidence

Both walkthroughs used isolated settings/stores and a session named
**TEST KLAUDE FEATURES HTTP MEDIA**. The input was the previous 192×128,
839-byte red/green/blue PNG:
SHA256 `08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.
The observation endpoint compared decoded generation bytes to that exact input.

### Actual compatible Ollama generation

Model: `openai_compatible@media-http/gemma4:e2b` through a loopback proxy to the
machine's existing Ollama. Its compatible catalog omits modalities; the explicit
native peer verifies `/api/show` support. No model installation or production
configuration change was required.

Passed through the actual terminal/worker path:

1. Disabled Vision rejects review without generation.
2. AI Defaults selects the HTTP endpoint and exact model, checks capabilities,
   saves the role, then explicitly enables Vision.
3. Private question/output edits, review and initially focused Back work.
4. Review rendering at **40/70/120 columns** wraps values and exposes the exact
   endpoint/model, budgets and server-allocation explanation. Navigation/filter/
   PageUp/PageDown retain the common panel behavior.
5. Declining the review sends no pixels; accepting it returns a private result
   with the correct `Red, Green, Blue` colors.
6. Real CLI analysis first declines with no generation, then explicitly accepts
   with `--yes` and returns the correct colors, exit 0, approximately **6.08s**.

Both generation requests used `/v1/chat/completions`, one verified image and
512 output tokens. **Zero chat turns** were created. Original image bytes,
the stored artifact/tags, unrelated workspace content and **22 installed model
digests** were retained.
Receipt: `.klaude/data/s2-models-wwf9xgr6/http-media-result.json`.
Log: `/tmp/klaude-s6a3b-real-compatible.log`.

### Native Anthropic protocol/worker fixture

The same settings/review/TUI/CLI scenarios passed using a loopback HTTP native
Anthropic fixture with private fake credentials and declared model capabilities.
The actual owned worker validated native API-key/version headers, image base64
blocks, disabled thinking, 512-token output and complete native SSE. No tool
schema was supplied. Original/stored bytes remained intact; **zero chat turns**.
The CLI accepted run exited 0 in approximately **1.97s**.

**Answers are canned, not paid Anthropic generation.** This pass validates native
protocol and real worker/UI behavior; it does not certify a cloud account, TLS
against Anthropic or model quality. The prior S6a3a TLS fixture remains separate.
The first driver seeded Default Chat with a model absent from its native fixture
catalog, causing startup's model picker to capture the subsequent commands.
Aligning the fixture's seed with its actual catalog fixed the driver, with no
product startup change.
Receipt: `.klaude/data/s2-models-taav_uih/http-media-result.json`.
Log: `/tmp/klaude-s6a3b-real-anthropic-fixture-final.log`.

## Validation

- The first existing regression run found a refactor bug: the catalog serializer
  excludes models without a connection record, leaving an empty capability list.
  Capability inspection now serializes its validated dataclass fields directly,
  independent of catalog filtering/model-name heuristics. The repaired existing
  regression run passed **211 tests in 72.82s**.
- New HTTP tests initially caught the remaining native-only persisted Vision
  role restriction. Both saved-role validation and endpoint selection now use the
  same supported adapter set. Protocol/ownership coverage then passed **45 tests**.
- Final focused Vision/provider/defaults/chat/session set: **292 passed in
  121.19s**, including raw image/output limits, actual pixel blocks, no tools/chat,
  temporary fallbacks, auth/protocol/blank/oversized failures, stale reviews,
  always-on thinking rejection, input estimates, deadlines and owned cancellation.
  Log: `/tmp/klaude-s6a3b-final-focused.log`.
- Model Manager regression set: **40 passed in 3.57s**, including the six new
  normalized native/compatible role protection cases.
  Log: `/tmp/klaude-s6a3b-manager-regression.log`.
- Focused production mypy: **112 source files** passed; Ruff and
  `git diff --check` passed.
- Full frozen/offline `make check`: **3299 passed, 19 skipped in 507.28s**;
  Ruff passed and production mypy passed **138 source files**. This full run
  includes all current cases and the final production implementation.
  Log: `/tmp/klaude-s6a3b-make-check.log`.
- Frozen/offline `make package-smoke` passed: all five wheels built and installed
  together in an isolated environment; public package imports and installed
  `klaude --help` passed. Log: `/tmp/klaude-s6a3b-package-smoke.log`.
- Baseline review started with **84** already dirty/untracked files. **65** retain
  their exact SHA256 hashes; **19** received the documented adapter/role/UI/test/
  documentation changes, and none disappeared. Two previously clean production
  transport modules and the new HTTP Media tests/evaluation are intentional
  additions to this pass. Review: `/tmp/klaude-s6a3b-worktree-review.json`.
  `git diff --check` passed. No dependency, lockfile or version changes; no commit
  or push.

## Remaining scope

Follow-up: [S6a3c OpenRouter image validation](s6a3c-openrouter-vision-validation.md)
extends chat and reviewed Media with declared OpenRouter capabilities and actual
free-model generation. The SDK limitations below describe this pass's boundary.

- SDK-backed providers need their own declared capability evidence and image
  protocol/actual generation checks before delivery is enabled. Unknown support
  cannot be inferred from IDs, context or tool capability. Paid certification
  requires an available explicitly selected account/model.
- Compatible endpoints without declared image modalities or a configured native
  peer still fail explicitly; engine-specific llama.cpp/vLLM metadata adapters
  are not guessed from URL shape. Generic allocation/reasoning remains server owned.
- Small allocations can reject large images conservatively. Resize externally or
  visibly adjust the supported context; no resizing/model changes occur silently.
- Synthetic colors prove pixel delivery and isolation, not OCR/coding accuracy.
  No generation, automatic tags, image editing, indexing or durable analysis
  reports are added. Import/open/export and manual lifecycle remain separate.
