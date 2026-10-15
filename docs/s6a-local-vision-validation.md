# S6a1: explicit native Ollama image analysis

Implemented and exercised locally on 2026-10-14. This delivers the first Vision
consumer through Library → Media and the real CLI. **S6a remains partial**:
provider-neutral image messages, other provider adapters and image attachments
in ordinary coding chat were subsequent work at this checkpoint. S6a2 now
provides native chat attachments: [follow-up evidence](s6a2-chat-images-validation.md).
S6b generation and S6c AI tags have
not started. This does not introduce a Gallery or image editor.

## Product flow

- Settings → AI Defaults → **Vision** has an off-by-default enable switch, an
  explicit endpoint/model and up to three ordered explicit fallbacks. No inherited
  chat model, auto-detection or automatic cloud choice is used.
- This slice permits native Ollama endpoints. Selecting a model checks bounded
  `/api/show` metadata and requires declared `vision` support before saving.
  Unsupported/unverified models fail; their names do not imply capability.
- Library → Media retains its existing import/storage/preview/export behavior.
  Importing or browsing calls no model or indexer. On an unarchived image detail,
  **Analyze image** opens a private question/budget form and Vision settings link.
  Returning from settings retains the image and question.
- **Review analysis** checks the current image revision/checksum, format/size,
  enabled model choices and endpoint/credential revisions. The Back-focused
  review names every model and endpoint that may receive pixels.
- Accepted **Analyze image** sends one stored image and question to the selected
  native endpoint. Result identifies the actual model used. The request has no
  tools, repository instructions, conversation history or knowledge operations.
- Result text is private, bounded and held in the current panel only. It is not
  saved as an artifact/session turn, indexed, learned or converted into tags.
  Navigate away during work and return through the same image detail to see it.
  Session/store changes discard stale results. Another question needs a new review.
- Default budget: **4,096 context / 512 output tokens**; the form permits explicit
  **2,048–32,768 context / 128–2,048 output** choices. Increasing budgets is a
  visible user choice, without a model-fit or server-allocation guarantee.

The synchronized command registry also includes:

```bash
klaude library analyze MEDIA_ID "Describe this screenshot" --context 4096 --output-tokens 512
```

The command uses the same Vision defaults/preflight/owned worker. Review defaults
to No; `--yes` accepts for scripted use. Complete answers exit 0, failures 1,
Ctrl+C 130. No complete answer is printed for incomplete/limited/tool-bearing
responses. Native input follows the documented text-plus-base64 `images` contract:
[Ollama vision API](https://github.com/ollama/ollama/blob/main/docs/capabilities/vision.mdx).

## Bounds, continuity and failure handling

- Managed PNG/JPEG only, **8 MiB**, at most **4 megapixels** and **4,096 pixels
  per side. Source bytes and metadata are not rewritten or resized. The existing
  header reader/checksum validates routing/dimensions/integrity; it is not a full
  client image decoder. The native server decodes pixels and may reject malformed
  images. GIF/WebP remain stored/exportable but unsupported by this first consumer.
- Questions are printable and at most 1,000 characters. No image bytes appear in
  job request metadata, logs, transcript or durable model context. The worker
  reads the approved artifact privately; image pixels intentionally go to the
  reviewed endpoint.
- Installed-model capability inspection starts no generation or model download.
  API metadata does not certify image quality or tool calling.
- Generation uses the shared cancellable HTTP transport: no ambient proxies,
  redirects or unrelated provider keys. Connection deadline 3 seconds, metadata
  read 5 seconds/outer 6, generation **90 seconds per attempt**, with cancellation
  waking requests before headers. Response 1 MB, event buffer 256 KB, answer
  32,000 characters, complete native termination required.
- Review uses an owned 30-second job. Accepted analysis uses an owned deadline
  of 100 seconds per reviewed model, at most four attempts. Model/Knowledge/
  Research/Utility/setup work and accepted Vision generation gate each other;
  queue counters and live progress/elapsed state remain visible. Requests survive
  navigation without stealing later navigation. Cancellation releases the task
  only after the owned worker is reaped.
- Only reviewed fallbacks may run after typed network/timeout/rate-limit/temporary
  service failures. Authentication, capability/configuration, malformed/incomplete
  streams, tool calls and output-limit errors stop without trying another model.
  The shared fallback policy now recognizes typed HTTPX status exceptions as well
  as the existing adapter status exceptions.
- Endpoint, credentials, enabled Vision choices and artifact revision are checked
  at acceptance and before returning an answer. Changing the image or role needs
  another review. Referenced Vision models/fallbacks are protected from endpoint/
  visibility mutation, native deletion and retained setup removal; explicitly
  clear/change Vision choices first.
- At the S6a1 checkpoint, ordinary chat kept its text/metadata declaration. This
  separate Vision operation does not imply pixels are available to the coding
  agent or restored chat context.

Implementation: core `vision`, `ai_defaults`, `utility`, `model_management`,
`ollama_manager`, `model_setup_removal`; CLI `vision_panel`, AI Defaults, Library
artifact/workspace/commands, owned background worker and existing model-work gates.
No dependency, lock or version update is needed.

## Actual native CLI evidence

Final receipt: `/tmp/klaude-s6a-native-hyhofdz0/result.json`.
Driver/output: `/tmp/klaude_s6a_native_vision.py` and
`/tmp/klaude-s6a-native-final.log`; exact cancelled/accepted CLI output is retained
beside the receipt.

- Existing **qwen3.5:4b**, native Ollama on this machine/GTX 1650; its `/api/show`
  declares completion, vision, tools and thinking. Vision runs with thinking off
  and no tools; this test certifies pixel analysis only.
- A valid synthetic **192 × 128 PNG**, three vertical red/green/blue bands,
  neutral filename `capture.png`, **839 bytes**, SHA-256
  `08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.
  The question does not supply its color values.
- Actual `klaude library analyze`: decline first (exit 0), then accept explicit
  analysis with context 4,096/output 128. The model identifies all three colors;
  complete command exit **0**, **8.66 seconds** on this warmed run.
- All **22 original Ollama names/digests**, original image/dirty workspace bytes,
  initial endpoint definitions and private role selections were retained.
  Public turns **0**; no session database or analysis artifact was created.

The initial CLI receipt `/tmp/klaude-s6a-native-jbompafk/result.json` remains
incomplete: its generation failed after approximately **22.08 seconds** from file
timestamps and the original generic error hid the exception type. Inspection
found a **20-second transport read timeout despite a 90-second advertised request
deadline**. This is consistent with cold header waiting, but that initial exception
was not retained, so its exact cause is not claimed. A direct retry correctly
identified the pixels in **18.12 seconds**. The transport now honors the advertised
deadline; a delayed-header regression and the real CLI/TUI reruns verify it.
Typed timeout/HTTP failures now have distinct user-facing messages.

The CLI answer initially added unnecessary caveats to an obvious image. The small
system instruction now asks for uncertainty only on unclear requested details;
the subsequent TUI answer was the concise **Red, green, blue.** One fixture does
not certify arbitrary OCR, UI interpretation or model quality.

## Actual terminal evidence

Final receipt:
`.klaude/data/s2-models-fid1ap1q/vision-real-tui-result.json`.
Driver/output: `/tmp/klaude_s6a_real_tui.py` and
`/tmp/klaude-s6a-real-tui-final.log`; text/SVG/raw terminal captures are beside it.

- Bare `klaude`, named **TEST KLAUDE FEATURES VISION**, private configuration and
  a dirty temporary workspace. The unrelated chat catalog uses a metadata fixture;
  the Vision connection and actual pixel generation use native Ollama.
- Imported the image through the real Media editor. Attempting analysis while
  disabled failed before pixel generation. The model picker rejected installed
  text-only `qwen2.5-coder:3b`; then accepted declared `qwen3.5:4b` and enabled
  Vision through real settings saves.
- Returned to the original private question, explicitly chose output 128,
  reviewed at **40/70/120 columns**, checked Back focus/paging, declined review,
  then accepted. Actual owned Vision generation returned **Red, green, blue.**
- Wide/narrow review and result captures were visually inspected: aligned values,
  wrapped questions/endpoints and reachable effects, safe Back and fixed
  header/footer. Existing narrow banner/status cropping remains outside this slice.
- Dismissed Library before `/exit`; final exit **0**, public turns **0**, all
  22 original model digests, initial endpoint definitions and original image/
  workspace bytes retained. Stored image stayed unarchived and untagged.

The first terminal run completed pixel analysis but its driver submitted `/exit`
while still inside a panel; raw output shows it being treated as a panel filter.
The incomplete receipt remains under `.klaude/data/s2-models-5h1oeff7` and
`/tmp/klaude-s6a-real-tui.log`. The corrected driver verifies Library dismissal
before exit and completed the whole flow; no product exit-hang claim is made.

## Regression validation

- An initial sandboxed targeted run stalled after 58 passing assertions and was
  explicitly stopped. Its interrupted **58 passed** record is not a full pass;
  later runs use required local socket/worker access.
- First accessible focused run: **139 passed, 2 failed** in 27.76 seconds.
  The HTTPX temporary-status fallback gap was a product bug and fixed centrally.
  The role-protection test expected an unnormalized model key; corrected to check
  the protected role across native normalized identities.
- Rerun **153 passed** in 31.05 seconds. Expanded delayed-header/image/defaults/
  Library/model-management regressions: **154 passed** in **29.81 seconds**,
  `/tmp/klaude-s6a-focused-complete.log`.
- Cases cover exact pixel input, no tools/history/indexing, disabled/unsupported/
  archived/corrupt inputs, stale image/endpoint reviews, no fallback on auth or
  malformed/incomplete/limited output, explicit temporary-failure fallback and
  actual used-model reporting, protected Vision roles, review paging, real CLI
  No, owned cancellation and delayed headers within the request deadline.
- Complete locked `make check`: **3,142 passed, 19 skipped** in **422.76 seconds**;
  Ruff clean and production mypy clean across **134 source files**.
  `/tmp/klaude-s6a-full-check.log`. Local Python 3.12 only; no new CI claim for
  3.11/3.13.
- Separate `make package-smoke`, started after the complete checks: **passed**
  for all **five wheels**, isolated installation/public imports and installed
  `klaude --help`. `/tmp/klaude-s6a-package.log`.
- `git diff --check` and whitespace checks on the new files passed. All **46
  unrelated pre-existing dirty/untracked files** retain exact contents against
  the turn baseline. No dependency/version/lock change, commit or push.

## Remaining S6a work

1. S6a2 now delivers the provider-neutral contract, native image attachments,
   private restore/compaction, switching and per-request pixel declarations;
   see [chat image follow-up](s6a2-chat-images-validation.md).
2. Additional provider image transports remain S6a3; paid generation stays explicit.
3. Additional image formats/decoding/resizing and richer screenshots require
   explicit resource/quality evidence. This simple test establishes pixel delivery
   and lifecycle, not general OCR or screenshot reasoning quality.

Image generation (S6b), AI-generated tags (S6c), public Gallery and editor workflows
remain separate. Importing and viewing Media still perform no automatic AI work.
