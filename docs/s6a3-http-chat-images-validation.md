# S6a3a: native Anthropic and compatible HTTP chat images

Date: 2026-10-15. This extends S6a2 chat/one-shot image delivery, with **S6a3
still partial**. Library → Media → Analyze image and `library analyze` remain
native Ollama. The next slice is S6a3b's reviewed HTTP Media analysis. SDK image
adapters, paid-provider certification, S6b generation and S6c tags remain open.

## Delivered behavior

- The existing explicitly enabled Vision setting and active Chat model govern
  image attachments. No fallback, model selection, downloads or Runtime budget
  increases occur automatically. `/attach`, inline `@PATH` and one-shot input
  reuse private Media snapshots and bounded session references.
- Native Anthropic Messages accepts neutral user-image parts as native base64
  image sources before text. Compatible Chat Completions accepts `image_url`
  data URIs. Existing tool-call/result pairs and private Anthropic thinking blocks
  retain their protocol order. Generic requests omit provider-private thinking.
- Capability inspection requires the exact selected model: Anthropic
  `/models/ID` must declare `capabilities.image_input.supported=true`; compatible
  `/models` must have one matching record with image in
  `architecture.input_modalities`. Missing evidence stays unknown; an explicit
  negative declaration stays unsupported. Model rows display those distinctions
  independently of tool support, context or reasoning evidence.
- A compatible catalog with unknown modalities may use `/api/show` from an
  already registered, enabled native Ollama peer at the same normalized root
  and authentication scope. This verifies an observed adapter relationship;
  model names, engine names and tools do not imply image support. An explicit
  compatible negative declaration is never overridden.
- Inspections are metadata-only, bounded to six seconds/1 MB and cancellable
  before response headers, with a 30-second model/endpoint/credential cache.
  Revision changes reject attachment preparation before saving or sending pixels.
- PNG/JPEG bounds remain two distinct images, 4096 pixels per side and four
  megapixels. Anthropic raw input is additionally capped at **7,500,000 bytes**
  per image, keeping encoded input within the documented 10 MB base64 limit.
  Other supported paths retain the 8 MiB bound. The conservative local context
  estimate remains visible and user overridable through Runtime.
- Native approval hashes remain compatible with S6a2. New adapter hashes include
  backend, normalized endpoint and credential digest. Switching providers,
  endpoints or credentials never authorizes historical pixels at the new target.
  Deleted/corrupted snapshots or unavailable historical input produce an honest
  omission notice. Cancellation during historical inspection stops generation.

Protocol references: [Anthropic Vision](https://platform.claude.com/docs/en/build-with-claude/vision),
[native model retrieval](https://platform.claude.com/docs/en/api/models/retrieve),
[official capability schema](https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/src/anthropic/types/model_capabilities.py),
and the [declared compatible catalog schema](https://openrouter.ai/docs/api/api-reference/models/get-models).
These describe the wire/capability fields; this pass does not certify SDK-backed
OpenRouter or other paid providers.

## Problems found through real use and repaired

### Resume selected Default Chat instead of the saved session model

An interactive compatible image session worked until process restart. `/resume`
restored its conversation but retained the newly launched Default Chat runtime.
The proxy then observed a native request to the wrong adapter. The approval guard
correctly withheld old pixels, but session continuity was wrong.

Session state now records the explicit model reference, mode, effort and captured
definition/credential revisions in a bounded private settings record. Accepted
turns and model/mode changes publish it atomically with their existing database
records. Delayed older setting writes cannot replace a newer accepted choice.
TUI and line-oriented resume restore this state without catalog discovery or
Default Chat writes. Changed/disabled/missing endpoints require a new selection
before another prompt. State contains no keys, tool permissions or image bytes.
Fork copies it; archive retains it; permanent deletion/clear removes only scoped
records. Legacy recovery reads Klaude's own exact model-setting events, never
user/assistant dialogue. Legacy sessions without a recoverable selection retain
the active model; no historical model is guessed.

### A visual follow-up became an unrelated public lookup

The first native Anthropic fixture request carried the pixels. A follow-up did
not: its roughly 22,754-character system prompt exhausted an 8192-token context
estimate and dropped the historical image. Initial routing also added the Skill
reader despite no relevant tool match. Removing that unrelated reader was useful
but insufficient: contextual routing then interpreted the assistant's
`Red, Green, Blue` answer as a public lookup topic and exposed session/knowledge/
web retrieval tools.

The Skill reader now accompanies a relevant tool/workspace intent or an explicit
Skill request. Follow-up inheritance stops at a substantive user objective even
when that objective needs no tools. It cannot move past that anchor to turn an
assistant's short answer or an older task into a new lookup request. This is a
general routing fix: it preserves explicit retrieval, coding and Skill workflows.
The same real Anthropic TUI follow-up subsequently retained pixels and omitted
the unrelated retrieval schema/policy context.

## Real CLI/TUI evidence

### Actual local model through the compatible adapter

Model: `openai_compatible@image-http/gemma4:e2b`, using the existing machine's
Ollama through an isolated loopback observation proxy. The compatible catalog
omitted modalities; its explicitly registered native peer verified vision via
`/api/show`. No model weights, production credentials or production settings
were changed.

Input: a 192×128 synthetic red/green/blue PNG, 839 bytes,
SHA256 `08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.
The proxy compared decoded request bytes to that exact image.

- Real `klaude ask --model ...` identified `Red, Green, Blue`, exit 0. The
  successful post-fix one-shot took approximately 15.89 seconds including startup.
- Real interactive model/mode selection and inline attachment delivered one
  image and answered correctly.
- Removing the original file did not prevent the follow-up from answering the
  center color from the private snapshot.
- A new TUI process resumed the same session, restored the qualified compatible
  model and answered another visual question with the retained image.
- All four generation requests stayed on `/v1/chat/completions`, model gemma4:e2b,
  with one verified image and the unchanged 512-token output limit. Exit 0;
  all **22 installed model digests** were retained.

Receipt: `.klaude/data/s2-models-vc3mp4qw/image-http-result.json`.
Log: `/tmp/klaude-s6a3-real-compatible-after.log`.
The synthetic colors demonstrate transport and continuity, not broad visual
reasoning or coding accuracy.

### Native Anthropic protocol through the real TUI

No enabled production Anthropic connection was available. An isolated loopback
TLS fixture used an ephemeral certificate and fixture-only HTTPX trust hook;
system trust, production runtime TLS verification and credentials were retained.
The actual Klaude CLI/TUI performed explicit qualified model/mode selection,
metadata inspection, native API-key/version headers, image-before-text base64
delivery, completed native SSE, follow-up after original removal and process
resume. Screens were captured at 40/70/120 columns, with clean exit.

The fixture verifies exact image bytes and native protocol. **Responses are
canned; paid Anthropic generation and model quality remain unverified.**
The post-routing-fix follow-up used the same private snapshot; the restart run
also restored the Anthropic endpoint/mode before sending. Three native generation
requests carried the same image, model ID and 128-token output cap. Only the
initial attachment and restart performed capability reads; the immediate
follow-up reused the bounded metadata cache.
Receipt: `.klaude/data/s2-models-h1du2wer/anthropic-image-tui-result.json`.
Log: `/tmp/klaude-s6a3-anthropic-tui-resume-final.log`.
The first restart driver waited for a non-visible activity phrase and timed out;
using the actual session header synchronization completed the scenario without
a product change.

## Automated validation and worktree review

- Before session-continuity changes: focused adapter/vision/connection/model
  regressions **212 passed**; full frozen/offline `make check` **3211 passed,
  19 skipped**, Ruff passed and production mypy passed **137 files**. That full
  gate predates the observed resume/routing fixes and is not final-tree evidence.
- New coverage checks bounded/private session state, atomic publication,
  stale-write ordering, lifecycle cleanup, explicit model/mode restoration,
  changed definition/credentials/availability rejection and visual follow-ups
  with actual retained pixel blocks. Exact-model capability identity is checked.
  Final focused adapter/state/responsiveness coverage: **73 passed in 32.79s**,
  log `/tmp/klaude-s6a3-new-focused-final.log`.
- Existing provider fixtures exercise malformed capabilities, auth/endpoint
  changes, source deletion/restore, native thinking/tool pairs, incomplete/output
  limit/authentication failures, cancellation before headers and negative/unknown
  capability distinctions.
- Initial new-test failures were an uncaught invalid reference in the state
  decoder, a fixture using the wrong settings filename, and an existing blocking
  writer mock without the new optional keyword. Decoder and fixtures were fixed;
  the responsiveness test retains its real ordered-writer assertion.

- Full frozen/offline `make check`: **3242 passed, 19 skipped in 471.28s**;
  Ruff passed and production mypy passed **138 files**.
  Log: `/tmp/klaude-s6a3-final-make-check.log`. Collection preceded the last three
  narrow regressions (saved thinking modes and exact capability identity); the
  final focused 73-test run includes them and the final identity guard. Static
  checks ran on the final production source. This is full-suite evidence plus
  final focused coverage, not a claim that all 3245 current cases ran together.
- Frozen/offline `make package-smoke` passed: all five wheels built and installed
  together in an isolated environment; public imports and installed
  `klaude --help` passed. Log: `/tmp/klaude-s6a3-package-smoke.log`.
- Worktree review started with **73** already dirty/untracked files: **59** retain
  their exact SHA256 hashes, **14** received the documented adapter/UI/session
  integration or documentation changes, and none disappeared. Five previously
  clean production modules and six new modules/tests/docs are intentional changes.
  Review: `/tmp/klaude-s6a3-worktree-review.json`. No dependency/lock/version
  changes, commit or push. `git diff --check` passed.

## Remaining limits

Follow-up: [S6a3b HTTP Media analysis](s6a3b-http-media-validation.md) completes
the reviewed Media flow for these HTTP adapters. Native-only Media statements
above describe the original S6a3a checkpoint. Additional SDK adapters and paid
provider certification remain open.

- Media analysis's owned-worker flow still accepts native Ollama only. S6a3b
  must extend that flow with the same reviewed model/budget/fallback semantics.
- Compatible servers without declared image metadata or a configured native
  peer are rejected. llama.cpp/vLLM metadata endpoints are not guessed from URL
  shape. Their additional capability adapters need separate bounded evidence.
- SDK-backed cloud adapters still omit historical images honestly and reject new
  unsupported image input. No paid generation or cross-provider fallback is
  claimed. Models vary in visual quality and server-side allocation is server owned.
- Stored Media copies remain independent of session deletion. Failed/cancelled
  preparation may leave a durable snapshot. Context admission can omit older
  images on small allocations; users can resize externally or explicitly increase
  the existing Runtime allocation. Automatic resizing/decoding, generation, tags,
  editing and a broad visual coding benchmark are outside this slice.
