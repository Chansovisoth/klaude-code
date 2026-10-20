# Cloud comparison and smaller execution phases

## Scope

Follow-up to [validation and recovery](agent-validation-recovery-followup.md),
authorized on 2026-10-16: try GPT Luna or free OpenRouter models on the failed
scenarios, then start the recommended smaller behavior-and-test execution work.
Baseline revision: `90137f46f59f15346f16401c2ecd5b6aecc8a7f7`; the existing dirty
worktree, including the preceding fixes, is the source under test. No commit,
push, credential/default change, model download or GPU/service repair.

Private evidence: `.klaude/data/cloud-phased-evaluation-59lag0eh/`. The initial
worktree/revision and all 154 production Python/prompt hashes are captured before
this pass. Cloud baseline attempts finish before new production edits begin.

## Unchanged benchmark and method

The exact [stockroom fixture](benchmarks/stockroom.json) retains its prompt,
six starting files, original tests and 13 external acceptance cases. Prompt
SHA-256 `c1c41dfa913d8c1355e6ab8aa34648f5c80ff63fc2245e25f0b5fd379f5b5f7d`;
acceptance SHA-256 `30d08650be70448be0adff78ce5b3278c4b47aeb5def8d5f2b32acf94ec93eba`.
Budgets remain 20 model steps, 40 tool attempts and 1800 seconds at safe
boundaries, with the same 2200-second external timeout. Isolated non-Git
temporary projects protect the real repository. The benchmark prompt is passed
unchanged to the real `klaude ask` command; original and external tests stay
outside the model's workspace and run only after the attempt ends.

The private observer wraps real runtime methods and records requests, responses,
usage, tool events and outcomes. It does not replace inference, tools, routing,
permissions or results. Ephemeral model-cache records select the exact models
verified in live catalogs; no saved user defaults change. Provider credentials
remain in process memory/environment, not evidence files. Runs share the same
owned evaluation lock and execute serially.

These are **provider comparisons, not a controlled model-only experiment**.
Cloud adapters use native calls rather than Ollama's constrained action grammar.
Their configured allocation and provider limits also differ: Luna API has the
existing unknown-cloud estimate, Codex publishes Klaude's conservative 128,000
fallback, and the selected OpenRouter catalog declares 256,000. The usual
4096-token coding output option is forwarded to the API/OpenRouter adapters;
Codex owns its output allocation. No claim of equal server context or hardware.

## Cloud baseline results

| Exact selection | Wall s | Outcome | Implementation/check progress |
| --- | ---: | --- | --- |
| `openai_api/gpt-6-luna` | 8.80 | Exit 1, `credit_balance_exhausted` | No tools or edits; generation access unavailable despite successful model metadata lookup. |
| `openai_codex/gpt-6-luna` | 13.47 | Exit 1, connection failure | Exact model listed by the existing authenticated broker; no successful inference or tools. |
| `openrouter/cohere/north-mini-code:free` | 252.38 | Exit 1, repair response reaches output limit | CLI/storage/README/new tests written, baseline check passed, post-edit check failed; repair not applied. |

The two Luna outcomes establish access/transport limits, **not model capability**.
Their unchanged projects' rejection-only acceptance passes are not reported as
CSV implementation. Catalog access never establishes generation access.

### Free OpenRouter run

Live metadata verifies the exact `:free` ID, tool support and zero prompt/output
pricing. A direct catalog connection fails; retry with the normal proxy
environment succeeds, matching the existing SDK's network path. An exact model
is selected instead of the random `openrouter/free` router.

Session `1bec34508023422d9eb6d92550226dfe` completes 20 real model requests and
19 tool proposals, of which 18 execute. One duplicate read is blocked. Exploration
is mostly serial, including an empty initializer and entry-point reread. A new
`IMPLEMENTATION_REQUIREMENTS.md` note consumes another step. There is no optional
Ollama planner request on this native provider path.

It changes `stockroom/cli.py`, `stockroom/store.py`, README, and adds the note and
`tests/test_csv_import.py`. It runs `python3 -m unittest discover -s tests -v`
before editing (exit 0), then after editing (12 tests, 10 errors, exit 1). The
generated tests call `main()` expecting returned error codes, while its new
implementation raises `SystemExit`; other generated expectations also conflict
with the implementation. The original held-out tests remain **2/2**. The model
reads the CLI to repair it, but its twentieth response ends with output-limit
failure. Partial native calls are discarded, no incomplete repair executes,
and the persisted final answer correctly says validation failed and work is
incomplete. No external timeout or evaluator intervention occurs.

External acceptance is **11/13**, including **1/3 positive cases**. These are
real command behaviors, unlike the earlier local unknown-command rejections.
The two positive failures are JSON summary shape differences: the implementation
returns ID lists for `applied`/`skipped`, while the unchanged grader expects
counts. **The task prompt names these fields but does not specify their types.**
This is a benchmark specification ambiguity; it is not by itself evidence of
broken storage semantics. The grader/prompt are not changed or normalized to
award a pass. The generated suite still demonstrably fails, and full benchmark
completion is not claimed.

Known usage: **68,547 input / 6595 output tokens**, peak known input **6650**;
the output-limited request has unknown usage in this baseline. Some successful
requests report reasoning tokens despite `think=false`. This exposes a control
defect: the adapter omits the reasoning option when off, allowing the provider's
default. The available baseline usage cannot establish that reasoning caused
the final output limit.

Source hashes match the pre-run snapshots for all three attempts. Raw evidence
is under `luna-api/`, `luna-codex/`, `openrouter-north-mini/`, with terminal,
request, event, independent-test and persisted-session records plus `analysis.json`.

## Confirmed issues motivating the next step

1. Whole-file implementation/repair responses are expensive and can exceed the
   existing output cap. Local storage writes took over ten minutes; this cloud
   repair also truncates. No partial call may execute.
2. Per-file plans can group many unrelated behaviors into one large edit and
   postpone every test until the end. Source and its corresponding tests need
   to be considered together, with check opportunities between changes.
3. OpenRouter's explicit thinking-off selection does not override provider
   defaults. Automatic/default selection must remain distinct from explicit off.
4. Buffered OpenRouter failures discard observed usage. A failed request still
   consumes inference; its partial tool/reasoning content must remain private.
5. Ollama retains total/load duration but drops its native prefill/decode timing
   fields, preventing useful diagnosis of CPU latency and prompt overhead.

## Changes implemented

### Behavior changes, tests and checks share a phase

The existing optional Ollama planner now proposes **1–3 small behavior changes**,
each naming **1–3 files requiring edits**, including focused tests where needed.
Klaude deterministically inserts a validation step after each change and appends
the existing final review. The previous planner allocated one entire file per
change and deferred validation until all changes were implemented.

The execution state records the revision at the beginning of each phase. A later
phase reusing the same source/test files needs fresh edits; an earlier phase's
edit and passing check cannot consume that phase. Active phase validation offers
inspection/check tools before more writes. Actual failed checks retain the
existing repair route. No tests run automatically and permissions are unchanged.

This extends the existing turn-local state and optional planning request; it adds
no new planner, judge, persistent task database or fixed workflow for simple
questions. The existing late-planning cutoff, context allocation and turn budgets
remain unchanged. Additional intermediate checks still consume the same budget.
Older unphased adapter plans remain compatible. This is a sequencing aid, not
proof of requirement coverage or semantic correctness.

Implementation: [Ollama.chat_workspace_plan](../packages/core/src/klaude_core/ollama.py),
[WorkspaceExecution](../packages/core/src/klaude_core/workspace_execution.py).
Native cloud providers retain their existing tool-call path: their runs below
**do not exercise this optional Ollama planner**.

### Explicit cloud controls and failure accounting

OpenRouter now forwards explicit thinking off/on as `reasoning.enabled=false/true`.
Automatic/unspecified selection still preserves provider defaults; explicit effort
selection remains supported. Both chat paths clear stale metadata before a new
request. Buffered responses retain observed usage, response ID and finish reason
even when terminal validation or call parsing fails. Partial calls and private
reasoning are never published to obtain that accounting. There is no new retry,
output increase or model substitution.

Implementation: [OpenRouterRuntime](../packages/core/src/klaude_core/model_runtime.py).

### Native latency evidence

Ollama's existing final metadata retains `prompt_eval_duration` and `eval_duration`
on buffered and streamed paths, alongside total/load durations and token counts.
These are server-reported stage timings, not an estimate of network or host work.
No extra inference or metadata requests are made.

Implementation: [Ollama.chat and chat_stream](../packages/core/src/klaude_core/ollama.py).

## Actual-model verification after the changes

### Same free coding model, explicit thinking off

Fresh unchanged CSV run `openrouter-north-mini-after/`, session
`76f8266c40c94a6e95c49fd093fe1739`: **103.05 seconds, exit 1**. The same exact
`cohere/north-mini-code:free` model, prompt, starting project and budgets are used.
All observed successful requests report **zero reasoning tokens**, confirming
that the formerly ignored off control is effective on this live provider.

Task performance **does not improve**. The model reads the six starting files and
runs the original suite successfully. It then makes four empty tool-discovery
queries (`csv`, `json`, `argparse`, `json import csv`), despite having callable
write/edit/shell tools, followed by unsuccessful workspace searches. Discovery
feedback reports no matching capabilities and points back to supplied schemas.
The no-progress governor stops execution. No edit executes and no new tests are
written. A final tools-disabled summary accurately says the task is unfinished,
but is unnecessarily long and asks whether to proceed despite prior authorization.

There are **18 execution requests plus one final summary request**, 18 tool
attempts, **65,367 input / 873 output tokens**, peak input **3885**, and no unknown
usage requests. Held original tests remain **2/2**. External acceptance is
**10/13**, **0/3 positive cases**: the ten passes are unknown-command rejections,
not implemented CSV behavior. The original generated suite still contains only
the two baseline tests. There is no truncation in this run, so failed-response
accounting is verified by deterministic transport tests rather than this run.

This is one stochastic run with a changed reasoning control; it does not prove
that disabling thinking causes poor implementation, or that the model cannot
implement the task. It does demonstrate that faster inference and correct controls
alone do not resolve the task-execution failure. Native provider discovery and
progress decisions remain a practical weakness.

### Additional cloud availability check

Fresh unchanged CSV attempt with catalog-listed
`google/gemma-4-31b-it:free`, session `6527966f96c542f68800abe1e6058a6c`, exits 1
after **11.04 seconds** with HTTP 429 on the first generation request. No tool or
edit executes. This is an access/rate-limit result, **not** a model-quality result.
The separate attempted fresh catalog read fails before receiving metadata; this
selection uses the previously captured same-pass catalog. No claim of fresh
Gemma capability verification is made. No further generation retries follow.

### Local evaluation stopped to honor the testing preference

The queued local pair was cancelled after the user directed that slow local
inference be replaced with cloud evaluation, including in future work. The owned
driver, harness and CLI child were checked stopped and the evaluation lock was
released; Ollama and unrelated processes were not stopped. This interrupted
partial attempt is **not** a local before/after quality measurement. The previous
completed 3B/4B outcomes remain in the linked historical report.

The new preference is recorded in [AGENTS.md](../AGENTS.md): use authorized cloud
models when local inference would be slow, preserve user defaults, and distinguish
cloud evidence from bounded local/protocol verification. A fresh live Ollama
CSV run of the phased planner is deliberately **not certified** by this pass.

## Before/after efficiency

| Observation | Free coding model baseline | Same model after explicit off |
| --- | ---: | ---: |
| Wall time | 252.38 s | 103.05 s |
| Actual runtime requests, including final summary | 20 | 19 |
| Tool attempts | 19 | 18 |
| Known input/output tokens | 68,547 / 6595 | 65,367 / 873 |
| Unknown-usage requests | 1 | 0 |
| Peak known input tokens | 6650 | 3885 |
| Requested implementation | CLI/store/docs/tests written | No edits |
| Post-edit validation | Failing generated suite; repair truncates | No post-edit check possible |
| External positive cases | 1/3 | 0/3 |

These figures are not an efficiency win: the faster run accomplishes less.
Baseline token totals omit its failed request's unavailable usage. The local
phase change adds check opportunities without another planning call, but its
live-model effect on latency, token growth and completion remains unmeasured.

## Regression validation

- Focused suite: **393 passed, 3 existing skips**, 15.46 seconds. Modules cover
  model runtimes, Ollama protocol/plans, workspace execution, reliability repair,
  compound tasks and tool discovery.
- New phase integration executes real file writes and real unittest commands:
  passing first phase, failing second phase, repair, then passing second phase
  (**exit sequence 0 → 1 → 0**), reusing the same source/test files. Scripted
  model responses are labelled fixtures; this is not live model capability proof.
- Protocol tests check paired source/test targets, deterministic interleaved
  validation, fresh revision requirements, legacy unphased compatibility and
  phase checkpoints without time pressure.
- Runtime tests check explicit on/off/auto/effort payloads, retained usage and
  finish reason on truncation, no partial tool/private publication, stale usage
  reset after a later pre-stream failure, and both native stage-timing paths.
- Ruff passes for the repository; production mypy passes for 153 source files.
- Fresh full `make check`: **3717 passed, 19 skipped**, 730.28 seconds for
  pytest; Ruff passes and production mypy passes for 153 files. Complete gate
  command exits 0 in 731.74 seconds on Python 3.12.3. This is a new full run,
  not the preceding pass's successful gate.
- Fresh `make package-smoke`: **passes**, 6.11 seconds. All five wheels build,
  install together in an isolated temporary environment, import and provide
  installed `klaude --help`. No dependency/lock update or network retry is needed.
- Full-suite coverage retains the previous plan-approval, cancellation,
  malformed-call, path/shell recovery, workspace-cache, dirty-tree safety,
  validation-rerun and CLI exit-code tests. This does not certify every external
  provider or replace the failed actual-model results above.
- Gate evidence: `gate-5ytmrei9/` and `final-validation-summary.json` beneath
  the private evidence root. Production hashes match before/after the gate;
  `git diff --check` and the report's relative source links also pass.

Production hashes are frozen in `phased-source-sha256.json`; the two new cloud
attempts report matching source hashes. The pass changes three production files
listed above, their focused tests and documentation. Unrelated dirty work is
preserved. No commit or push is performed.

## Remaining limits and next justified step

**No tested model completes the full benchmark in this pass.** The historical
small local models remain unsuccessful; new local phase inference is unmeasured.
Luna API credit, Codex connection and the additional free-model rate limit prevent
quality conclusions for those selections. The one successful cloud provider
still either produces inconsistent tests/oversized repairs or stalls without
editing. The prompt/grader summary-type ambiguity also remains unresolved and
prevents treating two baseline acceptance failures as a clean semantics verdict.

Confirmed remaining Klaude limits are expensive whole-file repair payloads,
serial/low-value exploration, and weak native-provider movement from inspection
to implementation. The bounded no-progress stop prevents indefinite looping but
does not help the model choose a useful next implementation action. The final
summary remains too verbose. None of these is solved merely by additional prompt
text or by hiding a failing result.

The next justified experiment is to expose the same compact execution/phase
state to native cloud callers, after a bounded inspection stage, while preserving
native tool protocol and avoiding a mandatory planner on simple tasks. Compare
that against the unchanged native path using an available cloud model, with
short admission/access checks before scheduling a full task. Keep decisions
model-led and measure actual edits/checks, not plan completion flags. A new
abstraction, automatic tool execution, larger system prompt or increased budgets
is not justified by the current evidence.

## Sources checked

- [OpenAI GPT-6 Luna model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna): exact model identity; account access is checked separately.
- [OpenRouter catalog API](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties): live IDs, declared tools/context/pricing.
- [OpenRouter reasoning controls](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens): explicit controls versus provider defaults, and reasoning/output sharing a limit on most providers. This does not identify the cause of the truncated baseline without its missing usage.

No paid OpenAI generation or successful Codex inference is newly certified.
The CSV benchmark is still not fully completed by any model tested in these
passes. Later results must retain the baseline outcomes above.
