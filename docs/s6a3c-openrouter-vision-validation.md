# S6a3c: verified OpenRouter images

Date: 2026-10-15. Continues [S6a3b reviewed HTTP Media](s6a3b-http-media-validation.md).
OpenRouter now supports chat attachments and reviewed Media analysis through
the existing private image lifecycle. OpenAI/Gemini image adapters, paid-provider
certification, S6b generation and S6c AI tags remain open.

## Capability and protocol investigation

- OpenRouter's [model catalog](https://openrouter.ai/docs/api/api-reference/models/get-models)
  declares input/output modalities and context/output limits. Fresh inspection
  requests the image-input/text-output catalog, then requires one exact selected
  model with both declarations. Names and tool support are not image evidence.
  Ordinary model inventories retain declared/unsupported/unknown image labels.
- Its [reasoning contract](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
  exposes mandatory reasoning. Such models require explicit Thinking chat mode;
  thinking-disabled Media rejects them. No mode, budget or model changes silently.
- OpenAI's [model resource](https://developers.openai.com/api/reference/resources/models/methods/retrieve)
  and Gemini's [model resource](https://ai.google.dev/api/models) do not establish
  equivalent per-model input-modality evidence in the inspected schemas.
  OpenAI's [image guide](https://developers.openai.com/api/docs/guides/images-vision)
  documents image delivery, but does not certify arbitrary selected IDs.
  These are capability-inspection gaps in Klaude, not claims that those providers
  lack vision. Pixel delivery through their SDK adapters remains unavailable.

## Implementation and root causes

- `image_content.IMAGE_BACKENDS`, model discovery and the shared
  `vision.inspect_model` allow verified OpenRouter endpoints. Selection checks
  definitions/credentials before and after inspection; all existing private
  attachment scopes, image bounds, snapshots and resume behavior are reused.
- New `OpenRouterImages` reuses the bounded cancellable HTTP transport and
  compatible SSE/tool parser. It emits OpenRouter image data URIs and reasoning
  controls, preserving ordered private reasoning details and complete tool pairs.
  The protocol follows OpenRouter's [image request documentation](https://openrouter.ai/blog/tutorials/send-image-to-llm/).
  Private details have count/size limits and publish only after success.
- `OpenRouterRuntime` delegates image-bearing requests to that adapter at the
  same endpoint/model/key, copying runtime metadata and forwarding cancellation
  and close. Its ordinary text SDK path remains. This avoids relying on SDK
  initialization for Media and reuses pre-header cancellation/raw response bounds
  already required by image consumers. It introduces no dependency or scheduler.
- Reviewed Media uses that same adapter with existing owned workers, 90-second
  generation, 1 MB responses, 256 KB events and 32,000 text characters. Disabled
  Vision, declined/stale reviews, changed credentials or missing declarations
  send no pixels. Only previously reviewed temporary-failure fallbacks may run.
  Media adds no tools, chat turns, saved analysis, indexing or tags.
- **Observed live catalog failure:** a valid filtered catalog was 537,629 bytes,
  below the 1 MB metadata cap. `VisionHTTP` also applied the 256 KB event cap to
  nonstream bodies. The event cap now applies only to streams; total response
  bounds remain intact. A >256 KB/<1 MB metadata regression reproduces the fix.
- **SDK completion ordering:** streamed tool calls/private continuation were
  released before the completion check; blocking chat also accepted truncated
  completions. Both now require a successful `stop`/`tool_calls` outcome before
  releasing buffered calls or private state. Missing termination, output limits
  and content filtering fail explicitly; previously streamed public text may
  remain partial, with no success claim or tool execution.
- An initial test treated `AgentEvent.payload.model_message` as public output.
  Inspection confirmed it is intentional private continuation saved separately
  from rendered text. The test now verifies that boundary; private reasoning
  preservation was retained rather than removed.

## Real CLI and interactive evidence

Tests used isolated configurations/private credentials and explicit qualified
models. Existing product settings, local model selection and repository files
were not changed by Klaude. The PNG contained red/green/blue vertical bands:
192 × 128 RGB, 839 bytes, SHA256
`08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.

### One-shot

The request was `Name only the three colors from left to right in @capture.png.`
with `klaude ask` and an explicit qualified `--model` selection.

| Explicit model | Outcome | Wall time |
| --- | --- | --- |
| `google/gemma-4-26b-a4b-it:free`, before metadata fix | Exit 1, metadata size error; no generation | 2.87 s |
| Same Gemma after fix | Exit 1, provider HTTP 429; no automatic fallback | 3.57 s |
| `dots-studio/dots-3-note-preview:free`, separate explicit run | Exit 0, `Red, Green, Blue` | 4.76 s |

Both IDs were observed in the authenticated live catalog with image/text
declarations and zero prompt/completion prices. The second choice was an explicit
test selection, not product fallback. No paid route was substituted. The dirty
repository guard remained active in the one-shot workspace.
Receipts: `.klaude/data/s6a3c-router-live-brfv0kcb/live-{ask,ask-after,second-model}-result.json`.

### Interactive and reviewed Media

Actual bare-CLI PTY session: **TEST KLAUDE FEATURES OPENROUTER VISION**,
explicit model `openrouter@router-live/dots-studio/dots-3-note-preview:free`,
standard mode, 8192 Runtime context / 512 output tokens.

1. Attached the PNG inline; actual provider returned all three colors.
2. Deleted the source and asked for its center color; retained pixels yielded Green.
3. Exited, started another process and resumed the session. The explicit provider/
   mode restored; retained pixels yielded Blue for the rightmost band.
4. Opened Library → Media → Analyze image; edited the private question and reviewed
   image/model/endpoint/budgets. Captured 40/70/120-column paged reviews, with safe
   Back focus, then declined without generation.
5. Reopened the review and accepted actual analysis: `Red, Green, Blue`. The result
   identified the selected model and remained private. Clean exit returned 0.
6. Confirmed exactly three chat answers, zero Media-added turns, unchanged imported
   artifact/workspace sentinel and all **22** native Ollama model digests retained.

Receipt/screens: `.klaude/data/s2-models-hf038mt0/router-live-tui-result.json`,
`router-image-{chat,followup,resume}-120.{txt,svg}`,
`router-media-review-{40,70,120}.{txt,svg}` and `router-media-result-120.{txt,svg}`.
Driver/log: `/tmp/klaude_s6a3c_live_tui.py`,
`/tmp/klaude-s6a3c-live-tui-after.log`.

The first TUI driver used a different native endpoint spelling from its seed
configuration. Startup's unavailable-default picker captured subsequent commands.
Aligning the driver's seed binding fixed the walkthrough; no endpoint identity or
startup safety rule was relaxed. A prior approval-review usage-limit failure did
not execute the attempted rerun; normal reviewed execution succeeded on resume.

## Automated validation

- Existing image/Media/SDK/connection tests before new coverage: **244 passed**.
- New OpenRouter protocol tests cover declared/negative/unknown/nontext models,
  private restore, signed tool continuations, incomplete/length/auth failures,
  owned and pre-header cancellation, stale reviews, mandatory thinking and large
  metadata. Shared HTTP fixture answers are canned; live results above are separate.
- Focused provider/image/Media/session/default set before the final blocking-SDK
  guard: **334 passed in 128.74s**; focused production mypy: **113 source files**.
- Final OpenRouter/SDK regressions, including blocking and streamed failure
  publication: **117 passed in 15.38s**.
- Full frozen/offline `make check`: **3327 passed, 19 skipped in 531.04s**;
  Ruff passed; production mypy passed **139 source files**. This includes the
  final blocking/streaming guard and all existing reliability tests.
  Log: `/tmp/klaude-s6a3c-make-check.log`.
- Frozen/offline `make package-smoke` passed: five wheels built and installed
  together in an isolated environment, public imports and installed
  `klaude --help` passed. Log: `/tmp/klaude-s6a3c-package-smoke.log`.
- Worktree review began with **88** dirty/untracked files. **76** retain their
  exact baseline SHA256; **12** received the documented implementation/test/docs
  edits, and none disappeared. This pass adds the OpenRouter image adapter,
  provider tests and this report. Dependency metadata, `uv.lock` and versions are
  unchanged; no commit or push. Review: `/tmp/klaude-s6a3c-worktree-review.json`.

## Remaining scope and next step

Follow-up: [S6a3d OpenAI Responses images](s6a3d-openai-vision-validation.md)
adds exact official-documentation profiles and native delivery. Its live account
check reported exhausted credit; protocol fixtures remain distinct from generation.
The SDK boundary below describes this OpenRouter pass's completion point.

- OpenAI/Gemini need a reviewed exact-model capability mechanism, then native
  image protocols and real generation/cancellation checks. Investigate official
  versioned capability profiles or an explicit bounded capability probe; do not
  use naming heuristics or send pixels merely to discover support.
- Live evidence covers the specified free OpenRouter model and simple synthetic
  colors. It does not certify paid routes, mandatory-reasoning generation, OCR,
  arbitrary screenshots, model quality or every upstream provider behind routing.
  Free routes may rate-limit; failures remain explicit.
- Review/result fields align at 120 columns and stack at 40. The global chat
  status/composer footer still truncates heavily at 40 columns; this slice does
  not redesign that shared footer. Paging retains safe Back focus.
- Existing text SDK pre-header cancellation remains best-effort; the bounded
  image transport does not claim to replace all SDK runtime behavior. Generic
  compatible servers still own allocation and model-specific reasoning controls.
- No image generation, AI tagging, editing or indexing was added. Existing native,
  Anthropic and compatible evidence remains separate and unchanged.
