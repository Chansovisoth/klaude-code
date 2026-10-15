# S6a3e — native Gemini image delivery

Date: 2026-10-15. Continues [S6a3d](s6a3d-openai-vision-validation.md).

## Scope and capability evidence

This slice adds native **Gemini 2.5 Flash and Flash-Lite** image chat and reviewed
Library → Media analysis. It does not certify successful Google generation for
this account. Both real one-shot attempts returned HTTP 404 after successful
metadata inspection. Successful CLI/TUI answers below are explicitly canned
TLS fixture responses.

Exact model documentation supplies image-input evidence:
[gemini-2.5-flash](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash?hl=en),
[gemini-2.5-flash-lite](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite?hl=en).
`image_profiles.py` records those exact stable IDs, source URLs and review date,
with 1,048,576 input and 65,536 output ceilings. Only the canonical
`https://generativelanguage.googleapis.com` root qualifies. No prefix/alias,
newer-generation or custom-root inference is made.

- Before pixels are sent, a bounded authenticated `/v1beta/models/ID` lookup
  must identify `models/ID`, declare `generateContent` and supply valid input/
  output limits. The lower documented/live limits apply to prepared capabilities.
  Chat retains its 30-second, revision-bound inspection cache.
- Inventory distinguishes **Images: documented** from catalog-declared support.
  Media review now says **metadata verified**, clarifying that catalog access
  does not prove generation entitlement, billing capacity or model availability.
- Google's [thinking contract](https://ai.google.dev/gemini-api/docs/generate-content/thinking?hl=en)
  permits `thinkingBudget=0` for these two IDs. Standard chat and private Media
  send zero explicitly; chat Thinking efforts use the existing bounded
  low/medium/high budget mapping. Output limits include thinking tokens.
- The inspected newer 3.5 Flash-Lite and 3.8 Flash IDs also returned metadata,
  but require a different thinking contract. They remain unknown to this image
  slice. Media's thinking-disabled contract is not silently relaxed.

## Native protocol and reliability changes

The existing chat image snapshots, neutral parts, endpoint/credential revisions,
agent tool loop, context admission and owned Media worker remain the owners.
There is no new scheduler, task loop or persistent remote file store.

- `GeminiImages` uses the native
  [streamGenerateContent API](https://ai.google.dev/api/generate-content):
  `contents[].parts[].inlineData` with PNG/JPEG MIME types and base64,
  `systemInstruction`, explicit `generationConfig.maxOutputTokens`, one candidate,
  `thinkingConfig`, `x-goog-api-key` and `store=false`.
- Native function declarations use `parametersJsonSchema`, retaining JSON Schema
  tool contracts. Tools remain manually executed by Klaude; no Google built-in
  tools or SDK automatic execution are enabled.
- The [inline image guide](https://ai.google.dev/gemini-api/docs/generate-content/image-understanding?hl=en)
  limits the whole request to 20 MB. Klaude checks serialized bytes including
  system/context text and encoded images before POST. Two individually valid
  8 MiB images can exceed that ceiling and fail locally. No automatic Files API
  upload, resizing or model switch occurs.
- Image-bearing requests and subsequent native continuation use the shared
  cancellable HTTP transport, including cancellation before response headers.
  Ordinary Gemini SDK text requests retain their existing route. Forked runtimes
  isolate mutable transports and retain the verified model marker.
- The native SSE reader is bounded to 16 MB responses/1 MB events in chat, or
  1 MB/256 KB in Media. Connects have a three-second deadline. Existing Media
  generation remains bounded to 90 seconds with owned worker cleanup and at
  most 32,000 public text characters.
- Tools and private state publish only after `STOP` and clean stream termination.
  Missing finish status, truncation, safety refusal, malformed calls, unexpected
  late candidates/errors and `CONTINUATION` fail. No SDK automatic long-decode
  continuation or hidden retry runs beyond the reviewed output request.
- Following Google's
  [thought-signature rules](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures),
  full signed text/thought/function parts stay exact in private
  `gemini_continuation`, scoped to root/model/key. They are not reduced to
  function-call signatures or merged with unsigned text. Thought parts are not
  public answer text. Validated state is limited to 512 parts/256 KB; streaming
  accounting is incremental rather than reserializing the entire history on
  each chunk. Only completed tool pairs are projected; host-generated IDs are
  not inserted into originally signed provider parts.
- Agent persistence/restore retains this private state, compaction counts its
  size and ordinary public history/export omits it. Foreign-scope signatures
  are never replayed. Existing image snapshots retain pixels after originals
  disappear and across process resume.
- Native image output usage includes reported candidate plus thought tokens.
  A new measured-counter test exposed a shared HTTP Media bug: the normalizer
  received the inner usage object rather than the complete metadata envelope,
  producing unknown counters. The corrected call returns the reported values.
- Observed HTTP 404 now explains that generation may be unavailable despite
  visible metadata. Status remains available to existing fallback classification;
  404 does not authorize an automatic fallback. Raw provider bodies/keys are not
  printed.

## Real provider attempts

Used the existing configured Gemini key, copied privately into isolated QA
configuration; production roles/defaults/credentials were not changed. Each
attempt used the actual installed workspace `klaude ask` entry point, an explicit
qualified model and Standard mode with 8,192 runtime context/512 output tokens.
The prompt was:

```text
Name only the three colors from left to right in @capture.png.
```

Input was the prior synthetic 192×128 RGB-band PNG, 839 bytes, SHA-256
`08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.

| Exact model | Metadata | Actual CLI generation | Wall time | Exit |
| --- | --- | --- | --- | --- |
| gemini-2.5-flash-lite | 200, matching ID/method/limits | HTTP 404 | 3.04 s | 1 |
| gemini-2.5-flash | 200, matching ID/method/limits | HTTP 404, NOT_FOUND | 2.78 s | 1 |

Flash's bounded private diagnostic identifies a new-user availability restriction,
not an unknown request field. Google recommends a newer model; Klaude did not
substitute it. Flash-Lite's original failure body was not retained, so its precise
404 cause is not asserted. Metadata-only checks also returned 200 for the newer
3.5 Flash-Lite and 3.8 Flash IDs; these are not generation tests.

Machine-local receipts:

- `.klaude/data/s6a3e-gemini-live-7ebdsqnj/result.json` — Flash-Lite CLI outcome.
- `.klaude/data/s6a3e-gemini-live-cggslqe6/result.json` and private
  `api-error.json` — Flash CLI outcome and bounded diagnosis.

No further live retries were made after identifying the restriction. The privacy
flag and image wire format remain protocol-fixture verified, not live-generation
certified by these rejected requests.

## Actual CLI/TUI flow against TLS fixtures

The fixture validates native request paths, auth headers, exact synthetic bytes,
MIME types, disabled thinking, output caps, `store=false` and absence of tools in
the chosen analysis tasks. It sends canned STOP/text/signature/usage envelopes.
QA-only in-place HTTP routing preserves the production canonical endpoint checks
and class identities; the separate owned Media worker inherits this QA route.
No production trust exception or fixture endpoint was added.

- Actual one-shot `klaude ask ... --model gemini_api@gemini-fixture/gemini-2.5-flash-lite`
  returned the canned RGB answer, exit 0, in 2.33 seconds.
- Actual `klaude library analyze MEDIA_ID QUESTION --yes` returned the canned
  RGB answer, exit 0, in 1.89 seconds. No analysis was saved into chat or artifacts.
- TUI session **TEST KLAUDE FEATURES GEMINI VISION** exercised disabled analysis
  with no POST, explicit Vision model selection/enabling, private question editing,
  owned metadata preparation, safe Back-focused review and decline with no POST.
- Reviews were paged and captured at 40, 70 and 120 columns. Narrow metadata
  stacks and wraps; wide labels align. Paging preserves safe initial Back focus.
- Private Media result, ask-another-question, pre-header cancellation and cleanup
  back to the form passed. Existing artifact metadata/content was unchanged.
- Explicit Chat model selection, inline image send and follow-up after original
  deletion passed. A fresh process resumed the same session model/mode/pixels and
  answered a further image question. All processes exited 0.
- Five POSTs covered one Media success, one cancelled Media attempt and three
  chat answers. Media added zero chat turns. An unrelated sentinel file retained
  its exact content.

Initial complete TUI receipt/captures:
`.klaude/data/s2-models-vy7_ef7i/gemini-fixture-result.json` and
`gemini-media-review-{40,70,120}.{txt,svg}`. CLI receipt:
`.klaude/data/s2-models-pvynkjn_/cli-result.json`.
The final metadata wording received a fresh complete TUI walkthrough; its receipt
is `.klaude/data/s2-models-vfof29hi/gemini-fixture-result.json`. All six scenarios
passed again, including process resume. A separate post-run SQLite/export check
found all three assistant turns retained private native state while public
transcript, session search and a real Markdown export contained no signatures
or private image references. Receipt: the same directory's
`private-state-receipt.json`.

## Automated validation

- Existing runtime/OpenAI/Anthropic/compatible image regression selection:
  **207 passed in 86.38 seconds**.
- New Gemini HTTP/profile/agent/Media tests: **34 passed in 22.25 seconds** before
  adding the shared usage assertion. That assertion first failed with both
  counters unknown; the envelope fix made it pass.
- Final combined Gemini/HTTP Media/OpenAI regression selection:
  **114 passed in 80.93 seconds**, including the usage assertion.
- Production-source mypy: **142 source files**, passed; Ruff passed.
- Final frozen/offline `make check`: **3,393 passed, 19 skipped in 575.53 seconds**;
  Ruff passed and production mypy passed on **142 source files**.
- Final frozen/offline `make package-smoke`: **passed**, building all five wheels,
  installing them together in an isolated environment, importing every public
  package and running the installed `klaude --help`.
- `git diff --check`: passed. Complete logs:
  `/tmp/klaude-s6a3e-make-check.log` and
  `/tmp/klaude-s6a3e-package-smoke.log`.

The first sandboxed fixture run could not bind loopback sockets; rerunning with
local-network permission passed. One preliminary full check was deliberately
interrupted to fix the observed usage failure; it is not counted as a complete
gate. The first TUI harness rejected its own accidental `/v1` Gemini root before
launch; correcting only the harness to the canonical root produced the receipts
above. These harness/setup failures did not prompt production trust relaxation.

## Remaining limits and next step

- Successful real Gemini image generation is **unverified** for both delivered
  legacy IDs. Returning users with access need a new actual pixel run. Metadata
  visibility alone must not change this status.
- A separate slice should review a current, accessible thinking-required Gemini
  model for explicit Thinking chat. Extending private Media needs an explicit
  consumer/budget decision; minimal thinking is not equivalent to thinking off.
- Ordinary SDK-only Gemini text requests retain their earlier completion and
  legacy call-signature behavior. This pass's complete native signed-part replay
  starts at the image/native-continuation boundary; it does not claim to recover
  signatures already lost by earlier SDK-only history.
- Signed continuation and inline request bounds can reject large outputs/inputs
  before provider limits are reached. Failures remain explicit. No Files uploads,
  server-managed conversation state, automatic model migration or image generation
  are included.
- S6a3 remains partial because current-generation/native paid-provider generation
  evidence remains incomplete. S6b generation and S6c AI tagging remain unstarted.

The pre-existing dirty worktree is retained: all 95 baseline files still exist,
83 are byte-identical, and the other 12 received the scoped runtime/UI/docs
changes described above. Three files were added: the native adapter, its tests
and this evaluation. Snapshot comparison:
`/tmp/klaude-s6a3e-worktree-receipt.json`. No commit or push was requested.
