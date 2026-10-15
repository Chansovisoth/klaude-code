# S6a3f — current Gemini image chat and native continuity

Date: 2026-10-15. Continues [S6a3e](s6a3e-gemini-vision-validation.md).

## Scope

Enable exactly `gemini-3.5-flash-lite` and `gemini-3.8-flash` at Google's canonical
API root for **Thinking chat**, including image attachments. Both now have actual
Google generation evidence. Private Media, Utility and Research retain their
Standard-mode contracts and reject these thinking-required models.

Official evidence reviewed this pass:

- [3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite?hl=en)
  and [3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash?hl=en)
  document image input, text output and the exact stable IDs. Profiles retain
  the 1,048,576 input / 65,536 output ceilings and dated source URLs.
- Google's [thinking contract](https://ai.google.dev/gemini-api/docs/generate-content/thinking?hl=en)
  uses `thinkingLevel` for these models. Flash-Lite offers minimal/low/medium/high;
  Flash offers low/medium/high. Minimal does not guarantee thinking off. The
  output-token cap includes thinking, so it remains a hard request bound.
- The [signature contract](https://ai.google.dev/gemini-api/docs/generate-content/thought-signatures)
  requires preserving signed native parts, keeping parallel function calls before
  their responses, and handling empty-text parts that carry late signatures.

No aliases, fine-tunes, unknown IDs or custom origins inherit profiles. Native
fresh authenticated identity/method/token-limit inspection still precedes image
delivery. Existing two-image, 8 MiB/image, PNG/JPEG/dimension, 20 MB encoded-request,
response/event, cancellation and private snapshot bounds remain in force.

## Problems found and changes

### Thinking controls were specific to one provider

Session mode/effort filtering honored explicit capability types only for
Anthropic. Current Gemini needs the same capability contract, including manual
model IDs and saved sessions without a fresh catalog lookup.

- One pure `gemini_capabilities` helper applies exact reviewed capabilities in
  discovery and CLI model binding. It performs no network work or model switch.
- Session mode/effort choices now follow declared types. Current models offer
  Thinking; Flash-Lite's minimal effort is valid bounded private session state.
  Unsupported choices fail, and restore revalidates the saved model/mode/effort.
- Model selection shows the supported choices; explicit one-shot selection of
  a thinking-required model uses its lowest supported effort. This follows the
  existing required-thinking selection rule. Image preparation never silently
  changes mode or model. Cached image inspection cannot authorize an invalid
  thinking level at the request boundary.
- Command handling and registry/focused help reflect model-supported effort
  choices, rather than advertising a universal low/medium/high list.
- Media, Utility and Research reject current profiles before model generation.
  Manual role selection is guarded; Research rejects before retrieval. Utility
  inheritance does not authorize thinking or a substitute model. Configure a
  compatible separate role model when using current Gemini Chat.
- Local request validation now clears native usage first. Eight strengthened
  cases initially showed that a rejected effort retained the preceding successful
  request's counters, which could double-charge the turn governor. They now
  verify no new POST and no reused usage after rejection.

### Signed history could be lost before the first image

The earlier image-only route left preceding text/tool turns on a manual SDK
projection that cannot preserve every native signed part. A later attachment
could therefore inherit incomplete protocol history.

- Reviewed current models use the existing bounded native adapter from their
  **first text turn**, keeping full scoped parts before an image arrives.
  Unreviewed models and ordinary legacy SDK-only text retain their previous route.
- Native parallel function results share one user content block. An interrupted
  round is omitted atomically, preserving first-call signature requirements for
  complete rounds. Two regression cases failed before this repair.
- Earlier foreign/unscoped tool results remain explicitly historical text,
  without borrowing another scope's signatures or fabricating validator bypasses.
  Scoped current native function history missing its required first signature
  fails locally. Signed parts remain private and are not merged with unsigned
  text. Late empty-text signatures are preserved through continuation.

### Real model discovery failed despite passing mocked tests

A real catalog request raised the closed-client RuntimeError. The function used
`genai.Client(...).models.list()` without retaining the owner: the SDK finalizer
closed its transport before the lazy pager consumed it. Iteration exceptions
also occurred outside the function's soft-failure handler.

- Retain the SDK client through iteration and close it explicitly in `finally`,
  on success and failure. The entire lazy iteration now belongs to the error
  boundary. Catalog requests use a five-second SDK timeout and one attempt.
- The installed SDK exposes `supported_actions`; the old adapter read only
  `supported_generation_methods`. Prefer the current field and retain legacy
  compatibility. Method and incompatible-name filtering exclude embedding,
  TTS and audio-only entries. An embedding regression failed before the repair.
- The actual catalog then returned **39 compatible chat models in 0.90 seconds**,
  including both current reviewed profiles, with zero embedding/TTS/audio rows
  and no generation requests. Receipt: `/tmp/klaude-s6a3f-live-catalog.json`.

### Role-picker status was misleading

The TUI displayed `Enabled` beside a model that could not serve the selected
role. It now says **Available / Unavailable** for that role. Current Gemini Vision
rows are muted/unselectable with the Thinking explanation; Default Chat describes
Thinking without an unrelated Utility-unavailable label. Invalid manual entry
retains its field for correction and safe Escape/back navigation.

## Actual provider scenarios

Used the existing Gemini credential through isolated private QA configurations;
production defaults/roles/credentials were not changed. Native requests used the
same prior synthetic 192×128 RGB-band PNG, 839 bytes, SHA-256
`08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.

Exact one-shot prompt:

```text
Name only the three colors from left to right in @capture.png.
```

| Exact model | Thinking | Output cap | Actual answer | CLI exit | Wall time |
| --- | --- | --- | --- | --- | --- |
| gemini-3.5-flash-lite | minimal | 512 | Red, green, blue | 0 | 5.62 s |
| gemini-3.8-flash | low | 1024 | Red, green, blue | 0 | 7.56 s |

Receipts:
`.klaude/data/s6a3f-gemini-live-wdsdmwit/result.json` and
`.klaude/data/s6a3f-gemini-live-ixe03tr8/result.json`.
This follows the legacy models' two HTTP 404 failures in S6a3e; those IDs were
not automatically replaced or retried. Their generation access remains unverified.

### Real interactive session

Session **TEST KLAUDE FEATURES GEMINI CURRENT**, ID
`21e82ade7fb94516865e0ac2e2bd537b`, used Flash-Lite and minimal effort.

1. Explicitly select the model, Thinking and minimal. `/mode standard` is rejected.
2. Ask to read `checks.txt`, follow its instructions and keep the workspace
   read-only. Klaude lists the directory, calls `read_file` once and answers
   `NATIVE-CHECK-42`, as the file requests. No web search or file edits occur.
3. Attach `capture.png` and request its three colors: correct RGB answer.
4. Delete the original, then ask for the center color from retained pixels: Green.
5. Exit, start a fresh Klaude process, resume and ask for the rightmost color: Blue.
   Thinking/minimal and private image snapshots survive independently of Default Chat.

Four actual assistant answers used **six generation POSTs**: directory listing,
file reading, first final answer, image answer and two follow-ups. A metadata-only
audit hook recorded method/model path, image counts, function-response counts,
first-call signature presence, controls, status and header latency; it did not
reroute requests, change responses or save keys/pixels/signatures. All requests
returned HTTP 200, used `store=false`, explicit minimal and a 512-token output cap.
The final resumed request supplied one actual image. Native signed tool
continuation was observed before the first image, not merely inferred from tools
being listed. Existing user/sentinel files retained exact content.

Actual TUI captures at 40/70/120 columns and request/exit receipts:
`.klaude/data/s2-models-7gqk75tx/`, including `gemini-current-result.json`,
`requests.jsonl` and `current-resume-120.{txt,svg}`.
SQLite inspection found private native envelopes on all four assistant turns;
session state retained Thinking/minimal. Public transcript, session search and an
actual Markdown export omitted private protocol/image references. Receipt:
`private-state-receipt.json` in that directory.

### Real TUI controls against local metadata fixtures

`.klaude/data/s2-models-nb6j0ogi/current-settings-result.json` records a passed
three-width Vision picker/manual-entry walkthrough. Its saved catalog is seeded
fixture data; this is not an additional Google generation test. Both current
models show Unavailable for Vision. Manual current-model entry fails with a clear
Thinking requirement, sends **zero POSTs**, saves no role, and exits 0 after normal
Escape/back navigation. Screenshots retain wrapped descriptions and aligned wide
columns. The real current-model chat captures independently cover live interaction.

Harness corrections: the first resume check waited for a Session divider that
had scrolled offscreen after tool history; resume had loaded successfully. The
corrected check generated the real Blue answer. Settings initially assumed a
fresh catalog on page open, then assumed descriptions never wrapped, and finally
tried `/exit` while still in the retained input editor. The fixture now uses the
documented saved inventory, accepts wrapping and follows visible back navigation.
These were harness errors; no production trust/navigation rule was relaxed.

## Validation and remaining limits

- Initial Gemini/session/runtime/CLI selection: **1,032 passed, 1 skipped**.
- Standard consumer/profile selection: **118 passed**.
- Broader final native/consumer/session/runtime selection: **240 passed**.
- SDK lifetime/filter plus runtime regressions: **92 passed**.
- Fresh command help/current-mode selection after help wording: **14 passed**.
- A preliminary full gate passed **3,428 tests, 19 skipped**, Ruff and production
  mypy on 142 files; it predates the final SDK lifetime fix.
- Final full `make check`: **3,430 passed, 19 skipped in 584.93 seconds**;
  Ruff passed and production mypy passed on **142 source files**. Log:
  `/tmp/klaude-s6a3f-make-check-final.log`.
- After the final native usage-reset refinement, the fresh native/session/runtime
  selection passed **191 tests in 46.89 seconds**, including all eight rejection
  counter regressions. Ruff and production mypy passed again. The full suite
  above was already running when that small refinement landed; this focused run
  is the validation of its final test bodies and request-boundary behavior. Logs:
  `/tmp/klaude-s6a3f-final-native-tests.log` and
  `/tmp/klaude-s6a3f-types-final.log`.
- Frozen/offline `make package-smoke` passed for **all five workspace wheels**,
  isolated installed-package imports and installed `klaude --help`. Log:
  `/tmp/klaude-s6a3f-package-smoke.log`.

The starting worktree already contained 98 modified/untracked files. All remain
present; 83 retain their exact starting bytes. The other 15 were deliberately
updated for this slice, alongside the previously clean Research consumer and
this new report. No reset, stash, discard, commit or push was performed. Final
hash-comparison receipt: `/tmp/klaude-s6a3f-worktree-receipt.json`.

No image generation, tagging, Files upload, new scheduler, automatic model
fallback or validator bypass was added. Native 3.8 image analysis was live-tested;
its tool calling and other effort levels are fixture-verified rather than live
TUI-certified. Legacy Gemini access and OpenAI/native Anthropic paid generation
remain unverified; their earlier restrictions are unchanged. Unreviewed Gemini
IDs retain prior SDK behavior. Scope/continuation bounds can still reject large
histories or outputs explicitly.

S6a3 remains partial for remaining paid-provider certification. S6b image generation
and S6c AI tagging remain unstarted. No commit or push was requested.
