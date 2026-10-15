# S6a3d: reviewed OpenAI Responses images

Date: 2026-10-15. Continues [S6a3c OpenRouter](s6a3c-openrouter-vision-validation.md).
Native OpenAI chat and reviewed Media images are implemented for two documented
IDs. Protocol, CLI/TUI and worker validation is separate from actual generation:
the configured OpenAI account returned **credit_balance_exhausted**. Live image
generation is **unverified**. Gemini, S6b generation and S6c tags remain unstarted.

## Exact capability evidence

The [official GPT-4.1 Mini model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
documents image input, text output, Responses, context/output limits, its alias
and dated ID. The [model resource](https://developers.openai.com/api/reference/resources/models/methods/retrieve)
does not itself publish modality capabilities. Klaude now distinguishes those
sources instead of rejecting all such catalogs or guessing from model names.

- `image_profiles.py` records the official source, review date **2026-10-15**,
  context/output bounds, and exact IDs `gpt-4.1-mini` and
  `gpt-4.1-mini-2025-04-14`. Profiles apply only to `https://api.openai.com/v1`.
- Fresh authenticated `/models/ID` must return that exact ID. Existing
  endpoint/credential revisions and 30-second chat metadata caching still apply.
  A profile documents capability; the live check establishes metadata access,
  not billing capacity or successful generation.
- Custom origins, fine-tunes, unknown IDs and differently named snapshots do not
  inherit support. Codex account auth remains separate. Profiles do not override
  missing models, deprecation or account access; both IDs returned HTTP 200 during
  this pass, despite the official page's deprecation labels.
- Inventory says **Images: documented** for profiles, retaining **declared** for
  live modality declarations. Media review says documented support / model access
  checked. Those checks send no pixels. The profile source/date is retained in
  prepared metadata and is inspectable in code; no docs scraping runs per turn.
- These non-reasoning models require Standard mode. Cached inspection cannot
  authorize a later unsupported reasoning request or oversized output budget:
  the request boundary checks both again before image delivery.

Google's official [2.5 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash?hl=en)
and [3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash?hl=en)
pages likewise provide exact model capability evidence, while the
[model resource](https://ai.google.dev/api/models) omits input modalities.
This resolves a potential evidence source for the next slice; it does not
implement Gemini image payloads, thinking modes or thought-signature continuation.

## Implementation and observed reliability fixes

- OpenAI uses native Responses `input_image` data URIs and `input_text`, following
  the [image guide](https://developers.openai.com/api/docs/guides/images-vision).
  Shared neutral validation retains PNG/JPEG, 8 MiB, dimensions and two-image
  limits. Endpoint-scoped private snapshots, restore and public-export boundaries
  are reused. No image generation, indexing or tags are added.
- `OpenAIImageTransport` reuses the cancellable HTTP connection tracker and bounded
  SSE reader. A small SDK-shaped JSON view lets the existing Responses parser
  handle messages, encrypted reasoning/compaction, complete tool pairs, refusals,
  usage and cache counters. Media requires no optional cloud SDK import.
- Existing `OpenAIRuntime` routes actual image-bearing requests through that
  transport, at the same model/root/key. Ordinary SDK text and Codex routing stay
  intact. HTTP connects are limited to three seconds; response/event bounds are
  the existing 16 MB/1 MB chat defaults or 1 MB/256 KB for Media. Nonstream bodies
  are bounded too. Media retains its owned worker, 90-second generation timer,
  32,000 text characters and explicit reviewed fallback chain.
- Responses [streaming semantics](https://developers.openai.com/api/reference/resources/responses/streaming-events)
  distinguish complete items from partial events. Tool/private state remains
  buffered until successful terminal status and clean stream termination;
  truncation, missing completion, late errors or invalid terminal status fail.
- **Output budget bug found in inspection:** OpenAI streaming did not forward
  positive configured `num_predict`, although blocking chat did. Both now forward
  it to `max_output_tokens`; image requests always have a bounded default of 2048.
  Output above the profile's 32,768 limit fails before pixels are sent.
- **Compaction gap found in inspection:** the existing Responses projection
  removes content before the newest opaque compaction item. For image requests,
  approved older pixels are now re-supplied after that item, with a neutral label
  and without replaying the old task instructions. Current system instructions
  and provider continuation remain intact. A recap is not visual evidence.
- **Observed metadata-timeout traceback:** a six-second inspection timer closed
  its socket, whose trace raised a generic cancellation RuntimeError outside the
  preparation error contract. Deadline-triggered cancellation now becomes
  TimeoutError, then a clean image-preparation error. Explicit cancellation stays
  distinct. No deadline was increased and no hidden retries were introduced.
- **Observed exhausted-credit failure:** bounded native HTTP returned 429 with
  `credit_balance_exhausted` / `insufficient_quota`. Error envelopes are read up
  to 64 KB, provider messages are excluded, and exhausted credit is reported
  without treating it as a temporary-failure fallback. Recognized streamed errors
  also get bounded actionable labels rather than raw provider text.

## Live account checks: what did and did not pass

- Authenticated model lookups returned HTTP 200 and exact IDs for both profiles.
- Real `klaude ask` used explicit qualified model
  `openai_api@openai-live/gpt-4.1-mini`, enabled Vision, a 192 × 128 RGB test PNG
  (839 bytes), 8192 context / 512 output, and isolated settings. Prompt:
  `Name only the three colors from left to right in @capture.png.`
- Initial one-shot exited 1 in **9.36s**, with a generic incomplete/failed
  provider event and no answer. Its original terminal detail was not captured;
  the later quota result does not reconstruct that earlier event.
- Diagnostic one-shots then hit metadata deadlines. Before the deadline fix one
  emitted a traceback; afterward it exited 1 in **9.43s** with a clean
  `Could not verify image support; check the active endpoint` message.
- One minimal native Responses request with the same PNG/model and 128 output
  isolated account access from orchestration: **HTTP 429**, code
  `credit_balance_exhausted`, type `insufficient_quota`, no generated text.
  Further cloud generation attempts stopped. No model/fallback was substituted.
- The existing dirty-worktree guard remained active. Credentials were copied only
  into isolated private test configuration and never included in argv, reports
  or public logs. Production defaults and the active user session were retained.

Artifacts: `.klaude/data/s6a3d-openai-live-t30yxlgy/result.json`,
`ask.{stdout,stderr}`, `diagnostic-after.{stdout,stderr}`;
driver `/tmp/klaude_s6a3d_live.py`; metadata/error observer
`/tmp/klaude_s6a3d_observe.py`. The observer retained only terminal status,
code/parameter/incomplete reason, not provider messages or credentials.

## Real CLI/TUI protocol walkthrough

Bare-CLI PTY session **TEST KLAUDE FEATURES OPENAI VISION**, with real TLS HTTP
and **canned fixture answers**. No cloud generation is claimed. Fixture-only
transport hooks redirect the official hostname to an isolated loopback TLS server
and trust its certificate; worker subprocesses receive that same QA hook.
Production endpoint/profile restrictions, parser, persistence, panel and owned
worker code run normally. Production trust or worker environment rules were not
changed. Fixture credentials are synthetic.

1. Disabled Vision / declined review sent zero image requests.
2. AI Defaults → Vision selected the OpenAI endpoint and exact manual model ID
   through owned inspection, then explicitly enabled Vision.
3. Media review at **40/70/120 columns** preserved Back focus and paged fields;
   decline sent no pixels. Accepted analysis produced a private fixture answer.
4. A second analysis stalled before headers; Cancel reaped the owned worker before
   returning to the form. No partial result was published.
5. Explicit Chat selection and inline attachment delivered the exact PNG bytes.
   A follow-up after source deletion retained pixels and returned the center color.
6. Clean exit/restart/resume restored the explicit model/mode and private pixels;
   a third chat answer identified the rightmost color. Exit code 0.
7. Exactly three chat answers, **zero Media-added turns**, unchanged imported
   artifact and workspace sentinel. Five fixture image requests included the
   cancelled analysis; every request used the selected model, `store=false`,
   an explicit 512 output limit, and no tools or reasoning for these questions.

Receipt: `.klaude/data/s2-models-louhsjsw/openai-fixture-result.json`.
Screens: `openai-settings-120`, `openai-media-review-{40,70,120}`,
`openai-media-result-120`, `openai-media-cancel-120`, `openai-chat-120` and
`openai-resume-120` as `.txt`/`.svg` in that directory.
Driver/log: `/tmp/klaude_s6a3d_fixture_tui.py`,
`/tmp/klaude-s6a3d-fixture-tui-after.log`.
The first fixture hook replaced Popen's class, breaking an MCP type annotation;
preserving the class and wrapping its initializer repaired the test harness.

## Automated validation

- Existing provider/Media/image regressions: **220 passed in 99.30s**.
- Focused provider/image/session regressions: **315 passed in 141.50s** before
  final quota/output guard additions. Log: `/tmp/klaude-s6a3d-focused.log`.
- Final OpenAI set: **32 passed in 20.80s**. Covers exact profiles/custom and
  unknown IDs, native streamed/blocking pixels, output limits, usage/cache state,
  private tool pairs/restore, failed/incomplete/late streams, stale reviews,
  owned transport cancellation, clean metadata deadlines, temporary fallbacks,
  quota rejection and retained pixels across compaction.
  Log: `/tmp/klaude-s6a3d-openai-verified.log`.
- Focused production mypy passed **4 files**; Ruff and whitespace checks passed.
- Full frozen/offline `make check`: **3359 passed, 19 skipped in 549.03s**;
  Ruff passed; production mypy passed **141 source files**. The run includes the
  final production source and all new tests. Log:
  `/tmp/klaude-s6a3d-make-check-verified.log`. Earlier full attempts were stopped
  for the final guard/fixture repair and are not successful full-suite evidence.
- Frozen/offline `make package-smoke` passed: all five wheels built and installed
  together in an isolated environment; public imports and installed
  `klaude --help` passed. Log: `/tmp/klaude-s6a3d-package-smoke.log`.
- Worktree review started with **91** already dirty/untracked files: **78** are
  byte-for-byte unchanged; **13** received the documented adapter/UI/docs edits,
  and none disappeared. Four additions are the profile, transport, tests and this
  report. Metadata, lockfile and versions are unchanged; no commit or push.
  Review: `/tmp/klaude-s6a3d-worktree-review.json`.

## Remaining limits / next step

- Actual OpenAI pixel generation remains uncertified until usable credits are
  available. TLS fixtures cannot establish provider behavior, quality or latency.
- Only the two reviewed IDs are enabled. Add exact official evidence and verify
  native behavior before extending profiles, especially reasoning models. Profile
  maintenance is a release responsibility; no naming heuristics or wildcard rules.
- Gemini needs a native image adapter with its model-specific thinking/signature
  contract. Its documented modalities are a useful evidence source, not an
  implementation. Codex account image support needs separate account evidence.
- Global terminal footer truncation at 40 columns remains as documented in S6a3c;
  Media fields stack and page safely. Header checks remain a bounded format check,
  not a complete client image decoder. No resizing or budget/model switching is
  automatic. S6b generation and S6c tags remain unstarted.
