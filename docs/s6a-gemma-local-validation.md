# Local Gemma vision follow-up

Date: 2026-10-15. Extends the native Ollama evidence in
[S6a1 Media](s6a-local-vision-validation.md) and
[S6a2 chat](s6a2-chat-images-validation.md), after
[S6a3f current Gemini](s6a3f-current-gemini-validation.md).

## Scope and selection

Exercise the installed local Gemma models through Klaude's actual CLI and TUI,
without changing production defaults, downloading models or adding model-name
exceptions. Ollama 0.33.3 reported 22 installed model names and no loaded models
before this pass. The machine has an NVIDIA GeForce GTX 1650 with 4096 MiB VRAM.

Fresh native `/api/show` declared `vision` for all four installed Gemma variants:

| Exact installed ID | Installed digest | Generation tested here |
| --- | --- | --- |
| `gemma4:e2b` | `7fbdbf8f5e45a75bb122155ed546e765b4d9c53a1285f62fd9f506baa1c5a47e` | Yes |
| `gemma4:e4b` | `c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb` | Yes |
| `gemma4:12b` | `6114515d63c17436a7c0417d82820ac65ad643e2806c5a3c89cb62846436ed0b` | No; metadata only |
| `gemma4:31b` | `6316f0629137b426c9d9b853ffc4c8209589f30ee39aebede6285096c0ff47e7` | No; metadata only |

The smaller variants were explicitly selected for bounded tests on this machine.
No model-fit certification or larger-model inference claim follows from metadata.
Installed digests differ from some current registry tags; no update was performed.
Capability receipt: `/tmp/klaude-s6a-gemma-inventory.json`.

Primary references checked:

- Google's [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4?hl=en)
  documents image input/text output and permits disabled thinking. Its general
  visual capabilities do not certify any particular installed quantization.
- Ollama's [Gemma 4 registry](https://registry.ollama.com/library/gemma4/tags)
  lists image-input variants. Klaude still checks the actual installed model's
  declaration; names and registry listings do not authorize pixel delivery.

## Real one-shot and owned Media scenarios

Used isolated configuration, private session/artifact stores and a temporary
workspace containing an unrelated sentinel file. Native requests went to the
existing local Ollama service. No provider key or cloud endpoint was involved.

1. Prior RGB regression: 192×128 PNG, 839 bytes, SHA-256
   `08495da3512a52229de30d36fb32933e88a6b7fac10cf454739836a9dde331b8`.
2. A rendered 640×360 screenshot fixture with a Build checks heading, two count
   cards and a failed-job label. SHA-256
   `ed555783ca04364d7e5b7557367039eed7e254f7b9b8fca249822e352796e163`.
   Its generic filename and question do not reveal the expected answer.

Exact chat prompts:

```text
Name only the three colors from left to right in @u27.png.
Read @u84.png. How many checks passed and failed, and which job failed? Answer in one sentence.
```

Explicit qualified `--model` references selected each model. Chat used Standard
mode, 8192 context and 128 output tokens. Imported Media used the existing owned
worker and reviewed Vision role: 4096 context, 128 output, 90-second model deadline,
question `Name only the three colors from left to right.`, with explicit `--yes`.

| Model | Chat colors | Chat screenshot | Media colors |
| --- | --- | --- | --- |
| `gemma4:e2b` | Red, Green, Blue; 8.09 s | 18 passed, 2 failed, Unit tests; 4.47 s | Red, Green, Blue; 8.22 s |
| `gemma4:e4b` | Red, Green, Blue; 66.51 s | Eighteen passed, two failed, Unit tests; 8.12 s | Red, Green, Blue; 14.37 s |

All six commands exited **0**, with correct answers. These are individual wall
times, including process startup and changing model/cache/allocation state, not
a controlled speed benchmark. E4B's first request spent 64.497 seconds before
headers; no attribution to a specific loading bottleneck is established here.
Later requests demonstrate why cold first-response latency should not be treated
as steady-state token speed.

Receipt directory: `.klaude/data/s6a-gemma-v6mrs2yk/`. `result.json` retains the
original numeric-only assertion's false negative: E4B correctly spelled out
“Eighteen” and “two”. `reviewed-results.json` records that semantic review; raw
outputs were retained rather than rewritten or needlessly regenerated. The QA
driver initially depended on unavailable Pillow; it was corrected to render its
fixture with installed ImageMagick, without adding a project dependency.

The metadata-only HTTPX observation hook captured the four chat requests, each
with one image, zero tools, `think=false`, the exact requested model/budgets and
HTTP 200. It neither rerouted requests nor retained pixel payloads. Owned Media
workers do not inherit this hook; their successful real CLI results are separate
evidence, not additional hook-observed requests.

## Real interactive continuity

Session **TEST KLAUDE FEATURES GEMMA VISION**, ID
`0211e448ad9e4778a7e823bf9f0606cf`:

1. Bare Klaude with explicitly configured E2B and enabled Vision. `/attach u84.png`
   followed by the screenshot question returned the correct counts and job.
2. Delete the original screenshot. A follow-up still identified **Unit tests**
   from the retained snapshot.
3. Explicitly choose E4B through `/model` and its Standard-mode picker. A new
   request read the retained screenshot and gave the correct two counts.
4. Exit normally, launch a fresh process and `/resume` the exact session. The
   restored E4B answered **18** when asked only for the passed-check count.

Exactly **four** native generation requests supplied one image each. The observed
model sequence was E2B, E2B, E4B, E4B; all used `think=false`, 8192 context,
128 output tokens, no tools and HTTP 200. No retry, web retrieval or automatic
model/fallback selection was needed. Payload text grew from 1555 to 1923 characters.
Both processes exited **0**. Public stored turns contained neither pixel base64
nor private image-input references. All 22 installed names/digests, connection
definitions and unrelated workspace bytes were preserved.

Receipt and actual 40/70/120-column captures:
`.klaude/data/s2-models-kysggic1/gemma-vision-result.json` and adjacent captures.
The composer/status adapt to width. Already printed transcript lines are terminal
scrollback; the QA terminal emulator clips them on narrowing and cannot reconstruct
their original columns when widened. This pass does not claim transcript reflow
or a new settings-layout certification. Corrected SVG rendering was inspected;
an initial renderer incorrectly hid Rich's clipped text, not the actual TUI.

## Validation, changes and limits

- Existing native chat-image, reviewed Vision/HTTP and session-runtime regressions:
  **130 passed in 89.21 seconds**. Log: `/tmp/klaude-s6a-gemma-regressions.log`.
- Real CLI driver: `/tmp/klaude_s6a_gemma_cli.py`; log:
  `/tmp/klaude-s6a-gemma-cli.log`. TUI driver:
  `/tmp/klaude_s6a_gemma_tui.py`; log: `/tmp/klaude-s6a-gemma-tui.log`.
- No production code/dependency/lock changes were needed: the existing declared
  native-vision path works for these installed models. This pass adds evidence
  and documentation only. The prior full gate remains separately recorded under
  S6a3f: 3430 passed, 19 skipped, Ruff, mypy and five-wheel packaging; its final
  request-counter refinement had an additional fresh 191-test selection. The
  130-test run here is a focused check, not another full-suite result.
- All 100 pre-existing dirty/untracked files remain present; only the three
  documentation files intentionally linked to this report were updated. Hash
  preservation receipt: `/tmp/klaude-s6a-gemma-worktree-receipt.json`.
  No reset, stash, discard, commit or push was performed.

The two small fixtures establish local pixel delivery, straightforward screenshot
reading and continuity. They do not certify arbitrary OCR, dense charts, object
localization, adversarial image instructions, visual coding accuracy, Thinking
mode, tool calling or inference on the larger Gemma variants. No model downloads,
service changes, unloading commands, context enlargement, tags or indexing ran.
Paid-provider certification remains outstanding; S6b image generation and S6c AI
tags remain unstarted. A broader visual-coding benchmark is a separate quality
evaluation, not a prerequisite for using these already supported local models.
