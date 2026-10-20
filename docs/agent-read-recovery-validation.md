# Lookup recovery: exact arguments, current evidence and interactive sequencing

Date: 2026-10-16. Base checkpoint:
`90137f46f59f15346f16401c2ecd5b6aecc8a7f7`, branch `klaude/20260908-1448`.
This continues [the first M0/M1 evaluation](agent-multi-action-validation.md)
and [the researched delivery order](agent-multi-action-research.md).
The checkpoint was pushed before implementation. This follow-up and the earlier
M0/M1 implementation remain uncommitted; existing dirty changes were preserved.

The subsequent discovery and broader-workflow continuation is recorded in
[capability discovery validation](agent-capability-discovery-validation.md).
Remaining-step statements below describe the end of this earlier iteration.

## Scope and outcome

The previous 3B text-model failure had a concrete orchestration cause: recovery
allowed arguments belonging to a final answer to appear in a source-read action.
Exact argument binding resolved that failure in repeated real CLI runs. Both
tested Qwen models completed the controlled text lookup on the initial integrated
change. Subsequent real TUI runs exposed two further causes of unnecessary work:
stale information requests were presented as unresolved gaps, and a dependent
question could be generated alongside the read whose result should answer it.
After these corrections, the 3B interactive lookup, source recall and direct
exact-output follow-up all completed without intervention.

These are controlled retrieval results, not proof of general reasoning quality,
real image attribution, live search reliability or CSV implementation completion.
Final automated and additional model-run results are recorded below. Later
reruns exposed a GPU-runner failure and CPU inference, with two confounded trials
retained separately. The final sequential pair completed on both models.

## Benchmark and isolation

Exact prompt, unchanged between baseline, prototype and integrated runs:

> Look up Luma Quill, read the relevant portfolio page, and tell me the title and creation date of the credited illustration.

- Native local `qwen2.5-coder:3b` and `qwen3.5:4b`, Standard / `think=false`.
- Final environment snapshot: Ollama `0.33.3`; both models are Q4_K_M. Exact
  installed digests are `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`
  (3B) and `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`
  (4B). This is observed final metadata, not a reconstruction of earlier hardware
  allocation.
- Explicit 8192-token context and 768-token output allocation. No silent model,
  context or output increase. The prompt is text-only; unsupported image input is
  not a model failure in this test.
- The same controlled search/fetch evidence as the preceding evaluation: queries
  mentioning Luma or Quill return `https://artist.example/portfolio`; other
  queries return no results. Reading that exact URL yields title `SALAD PARTY`,
  creation date `18 February 2024` and the credited illustrator. Other URLs fail.
  Search results do not contain the requested title/date.
- Real Typer `ask` and actual PTY `chat` paths, real native Ollama inference,
  normal model selection, permissions, agent loop and SQLite session persistence.
  The launcher replaces only the search/fetch functions and adds observation
  wrappers. It does not fabricate model calls, rewrite model answers or execute
  the successful path for the model.
- The prototype alone changes the recovery schema at the runtime seam, explicitly
  distinguished below. Integrated runs disable that experimental override; the
  production implementation supplies the capability flag and exact schema.
- Each evaluation uses a separate `/tmp` workspace outside this repository, with
  isolated config/preferences/session storage under ignored `.klaude/data/`.
  No user images or production preferences are changed, and no paid inference
  or real search-provider request is needed.
- Success requires an executed read and the requested facts in the actual saved
  assistant answer. A tool preview, process exit 0 or a schema-valid plan is
  insufficient. SQL `turns.content` is JSON-decoded before answer comparison.

### Observation limits

The launcher observes the underlying `Ollama.chat`, including constrained-action
requests, rather than only the runtime facade. Native direct-answer streaming
does not necessarily pass that observer; persisted governor counters remain the
authoritative model-step totals for completed turns. An exhausted tool-free
synthesis can appear as an extra HTTP request beyond those step counters. Known
input/output totals are provider-reported aggregate counts, not a measured peak
context window or unique-token count. Cold loads, caches and GPU/CPU placement
make these small samples unsuitable for p50/p95 or universal speed claims.

## Measured progression

| Revision / model | Actual outcome | Requests and tools | Known input / output tokens | Wall time |
| --- | --- | --- | --- | --- |
| Fresh baseline, 3B | Exit 1; no source read, no completed answer | 5 charged steps, 6 observed HTTP calls; 4 charged tool attempts, only 2 fixture searches executed | 17,375 / 400; 1 unknown-usage request | 59.94s |
| Fresh baseline, 4B | Exit 0; correct title/date and URL | 3 requests; search + fetch | 10,238 / 269 | 90.45s |
| Evaluation-only exact schema, 3B | Exit 0; correct title/date | 4 requests; search + fetch | 13,305 / 256 | 37.85s |
| Evaluation-only exact schema, 4B | Exit 0; requested facts correct; added an unsupported alternate-title characterization | 3 native requests; search + fetch; exact recovery not exercised | 10,237 / 254 | 89.98s |
| Initial integrated production, 3B | Exit 0; correct title/date | 4 requests; search + fetch | 13,405 / 255 | 38.43s |
| Initial integrated production, 4B | Exit 0; correct title/date and URL after malformed native tool name | 4 requests; search + fetch | 13,956 / 412 | 125.92s |
| Initial integrated production, 3B repeat | Exit 0; correct title/date | 4 requests; search + fetch | 13,419 / 319 | 39.61s |
| Final sequential CPU run, 3B | Exit 0; correct title/date, no repeated tools | 4 requests; search + fetch | 13,390 / 236 | 352.87s |
| Final sequential CPU run, 4B | Exit 0; correct title/date and URL, but unsupported cross-source corroboration claim | 3 native requests; search + fetch | 10,261 / 253 | 543.39s |

Baseline 3B mixed `answer` into `fetch_url` arguments; canonical host validation
correctly rejected it. Repeated search and final exhausted synthesis did not
complete the requested read. The integrated 3B runs eliminate those mixed fields
and unnecessary executed searches in this sample. Lower aggregate known input
reflects fewer unsuccessful rounds, not a larger allocation. The integrated 4B
run recovered from a bad native tool name, costing an additional round and time;
this is a reliability improvement in that run, not evidence of universal latency
improvement. The prototype 4B response's unsupported embellishment is retained as
a semantic limitation despite correct requested facts.

In the final 3B run, reported per-request prompt tokens grew
`2865 → 3212 → 3529 → 3784` within the same explicit 8192 allocation. The failed
baseline's five known prompts grew `2836 → 3208 → 3541 → 3745 → 4045`, followed by
one unreported failed request. The smaller known aggregate and fewer wasted
rounds establish tool/context efficiency for this sample. They do not isolate
decoder speed, cache performance or peak allocation on the failed request.

### Real interactive iterations

All use the same 3B model and the exact lookup prompt above, in a session named
`TEST KLAUDE FEATURES READ RECOVERY`.

1. **Exact arguments alone:** the model searched three times, read the correct
   page, invented a `/credits` URL and asked an unnecessary question. The harness
   timed out at 300s waiting for completion and then closed its owned client.
   Root cause: old pre-call information targets were repeatedly asserted as gaps
   even after the answer-bearing page arrived. This was not a successful run.
2. **Information-request correction:** the model generated fetch and a dependent
   user question in the same response. It could not use the unread result to
   decide whether that question was necessary. This evaluation was explicitly
   interrupted, not passed. A duplicate harness SIGINT interrupted cleanup; the
   child subsequently exited on PTY closure, and an exact client/process-handle
   check found no surviving evaluation client. Its interruption receipt is kept.
3. **Ordered recovery decisions:** main lookup completed in 39.72s with correct
   facts. An incomplete native response after the read recovered through the
   existing bounded fresh-action retry. The next source-recall assertion failed
   because the deterministic recap listed tool names but omitted the URL.
   The lookup subscenario passed; the full sequence did not.
4. **URL-aware recorded source recap:** the complete sequence passed, normal exit
   0, session `a4f546780f6c40e485e935d183295356`:

   | Turn | Saved result | Wall time | New tool executions |
   | --- | --- | --- | --- |
   | Exact benchmark | Requested title/date correct | 30.43s | One search, one fetch |
   | `Which source did you actually use? Reply concisely.` | Exact recorded public URL plus execution/evidence caveat | 0.71s | None; no new model request |
   | `Reply with exactly "OK".` | Exactly `OK` | 4.60s | None |

   The first answer literally begins `cene: Luma Quill; title: SALAD PARTY;`.
   Required facts are correct, but that malformed prefix remains a model wording
   defect. It was not silently rewritten or graded as polished prose. The final
   URL-userinfo guard was tightened after this process imported its sources; the
   simple safe URL follows the same path, and focused tests cover the final guard.

### Additional final paired rerun

Two final-source reruns accidentally overlapped across context compaction: the
earlier owned job was still running when another was started. Their 3B processes
hit the 240s external harness deadline before a tool completed (240.05s / 240.11s).
The first CLI explicitly reported `GPU runner failed; retrying safely on CPU...`;
`/api/ps` showed `size_vram: 0`, and `nvidia-smi` reported unavailable utilization
with 1 MiB allocation on the GTX 1650. These are confounded, incomplete runs,
not application exit-code failures, performance comparisons or passes.

Only the two identified evaluation clients were interrupted. Their 4B turns
exited 130 in 233.23s / 103.60s, with one search / no tool respectively; neither
completed. An exact process check confirmed all those owned clients had exited.
The receipts and traces remain, rather than silently dropping the bad trials.
One subsequent sequential pair retains the exact prompt and application budgets,
with a 900s external harness deadline for CPU inference. It overlaps the automated
validation and is still unsuitable for isolated latency comparisons. Results
are recorded in the progression table. The final 3B run completed with no unknown
usage requests, session `2d5af005962e4c869dc0738c75e82542`. Its slow first native
response was followed by exact search/fetch/finish recovery, without a failed
tool execution or repeated search.

The final 4B run also completed with no unknown usage requests, session
`5bf6c7677a314a73a04d2493c4e8089e`. It used three ordinary native requests and
only one search plus one read; recovery was unnecessary. Reported prompt tokens
grew `3102 → 3437 → 3722`, within 8192. Both final sessions returned exit 0 and
the requested title/date without intervention. Their allocation receipts both
show zero VRAM. Slow CPU execution is not claimed as a latency improvement.

The 4B final answer ends: `This information appears consistent across available
sources with no conflicting details found.` Only one unique page was read; the
search lead pointed to that same page. The requested facts and citation are
correct, but this corroboration claim is unsupported. The run passes requested
lookup completion, not full claim-grounding quality. The host's source-examination
boundary cannot certify factual interpretation merely because a read executed.

## Root causes and changes

### Exact action arguments in existing recovery

[Ollama.chat_structured_action](../packages/core/src/klaude_core/ollama.py)
previously merged read-tool and finish-action fields into one permissive object.
That let weaker models emit syntactically accepted but semantically invalid
combinations such as a fetch with `answer` or timezone fields. The executor then
correctly rejected them. Workspace mutation recovery already used exact variants.

Native Ollama now advertises `supports_bound_action_arguments`; its runtime
wrapper forwards the optional capability. For non-coding lookup outcomes, the
agent opts into exact action variants in the existing constrained recovery call.
Each tool discriminator binds the canonical parameters, and `__finish__` has its
own answer-only arguments. The bound prompt includes that schema without a
second full tool-catalog copy. This adds neither a new planner nor an obligatory
model call to normal turns. Unsupported runtimes receive no new argument.

The implementation retains client parsing, canonical argument validation,
permission checks, response-time scope snapshots and existing budgets. It does
not enable tools, broaden permissions, invent arguments, rename tools, change
provider-native successful calls or change workspace discovery's default grammar.

[Ollama structured-output documentation](https://docs.ollama.com/capabilities/structured-outputs)
supports passing and validating a JSON schema while grounding it in the prompt.
[JSON Schema's combination reference](https://json-schema.org/understanding-json-schema/reference/combining)
defines `oneOf` and warns about schema evaluation cost. These justify the contract
shape, not an assumption that every decoder or small model will behave correctly.
Existing bounded protocol recovery remains necessary; no model-name exception
was introduced.

### Separate requested information from observed limitations

In [AgenticSearchState](../packages/core/src/klaude_core/agent.py), a model's
pre-call `missing_information` previously entered `unresolved_information` and
was repeated beside every subsequent source result. The host had no semantic
evidence that the requested fact was still missing, but presented it as a live gap.

Pre-call notes now go to bounded audit `information_requests`: at most 16 unique
240-character normalized notes. They are not repeated in the model's live summary.
Real host failures and exhausted budgets stay in the existing limitation list,
whose summary is labeled `recorded limitations`. Reading a page does not
automatically establish sufficient evidence or clear actual errors.

### Sequence dependent decisions and enforce requested source reads

Bound interactive recovery uses one action per response when `request_user_input`
is callable. The model sees the read result before deciding whether a question is
needed. Oversized batches are rejected atomically. Bound non-interactive reads
still support up to four actions, and workspace mutation completion flags retain
their existing rules. This targets observed recovery behavior, not every native
tool batch or a general mandatory workflow.

The existing explicit page-read requirement now also creates a source-examination
outcome in [task progress](../packages/core/src/klaude_core/task_progress.py).
Budget-end tool-free synthesis must respect it, just as it respects an image-origin
source obligation. The model chooses the page; the host cannot manufacture a read
or replace an incomplete request with an unsupported successful final answer.

### Give retrospective source questions the recorded URL

[source_use.py](../packages/core/src/klaude_core/source_use.py) now includes up
to four distinct public fetched URLs from observed execution metadata or completed
restored receipts, using the shared
[research receipt sanitizer](../packages/core/src/klaude_core/research_receipts.py).
Restored identifiers are revalidated. Search leads and arbitrary MCP metadata do
not become fetched URLs. Query and fragment values, credentials and private hosts
are excluded; all userinfo is rejected, including an empty username with a password.

This deterministic recap adds no model call. It explicitly states that recorded
execution does not preserve or prove the answer's evidence. No body or saved
receipt is replayed as a new tool result by this change.

### Correct a previous evaluation assertion

The earlier literal-output receipt compared JSON-encoded `turns.content` directly
to plain text and falsely reported retained quote delimiters. Decoding the stored
value confirms that the previous actual output was exactly `look them up`.
The old receipt remains; a separate corrected receipt and the earlier document
explain the harness error. No host output rewriting was added to manufacture an
exact-output pass. Current scripts decode the persisted content first.

## Regression validation

The final focused set passed **368 tests in 11.36s**, covering the changed agent,
native runtime, workspace execution, scoped recovery, research state and source
provenance modules. Ruff passed, and production mypy reported no issues in 152
files before the final full gate. New checks cover:

- Exact discriminator/arguments, finish isolation, canonical schemas and read
  batch bounds; compatibility when the capability is absent.
- Real OllamaRuntime wrapper over mocked HTTP: bad native syntax, exact recovery,
  source completion, and allow/ask-denied/deny policies. Denied functions never run.
- Recovered interactive read/question batch rejection with no partial execution;
  default workspace/read discovery remains on its previous contract.
- Explicit page-read completion before synthesis, including an exhausted step
  budget; no extra request can invent the missing read.
- Bounded pre-call audit notes, preserved actual limitations and no inferred
  semantic sufficiency after a source arrives.
- Live/restored/compacted source recaps, URL bounds and dedupe, failed-fetch
  exclusion, credential/private-address suppression and query/fragment stripping.

The final frozen/offline `make check` completed with exit 0 on Python 3.12.3:

- **3663 passed, 19 skipped** in 997.79s; complete gate time 999.93s.
- Ruff: all checks passed.
- Production mypy: no issues in 152 source files.
- All 19 skips are the existing superseded retrieval tests. No new skip was added.
- All 153 recorded production Python/prompt files matched their starting SHA-256
  hashes after the gate. No production source changed during validation.
- `make package-smoke` passed in 12.97s: all five wheels built, installed together
  in an isolated environment, public imports succeeded and installed
  `klaude --help` completed.
- `git diff --check` passed. No implementation commit or push was made.

The complete suite includes plan approval, cancellation, malformed-call/path
recovery, shell failure tracking, workspace cache invalidation, dirty-worktree
safety, validation reruns and exit-code checks; these are automated regressions,
not renewed live certifications of every provider. This gate overlaps CPU model
inference and is not a comparison of test-suite speed with the previous pass.
No new Python 3.11/3.13 or GitHub CI run is claimed for uncommitted changes.

## Evidence index

Local evidence is under ignored `.klaude/data/`, not a public source or release
artifact. Each completed paired run contains terminal output, JSONL underlying
model/tool observations, saved session data and `results.json`.

| Evidence | Location |
| --- | --- |
| Fresh baseline | `.klaude/data/compound-read-binding-baseline-decpxxsh/` |
| Evaluation-only exact schema | `.klaude/data/compound-read-binding-exact-klll7qdd/` |
| Initial integrated pair and 3B repeat | `.klaude/data/compound-read-binding-production-cx3bawmv/` |
| Interactive exact-argument timeout | `.klaude/data/compound-interactive-read-binding-c91k4hxk/` |
| Interactive interrupted dependent question | `.klaude/data/compound-interactive-read-binding-0ocjkjcp/` |
| Interactive lookup pass / source-recall failure | `.klaude/data/compound-interactive-read-binding-w537gqug/` |
| Complete interactive sequence, text/SVG captures | `.klaude/data/compound-interactive-read-binding-mu65uuy7/` |
| Corrected old literal-output assertion | `.klaude/data/compound-quoted-control-fixed-s0j4ehn8/results-corrected.json` |
| Confounded paired reruns | `.klaude/data/compound-read-binding-final-production-n0ltea4m/`, `.klaude/data/compound-read-binding-final-production-id1ilgn4/` |
| Final sequential pair and environment snapshot | `.klaude/data/compound-read-binding-final-sequential-cpu-777cilev/` |
| Focused tests | `/tmp/klaude-read-recovery-final-focused.log` |
| Final full gate / source hashes / packaging | `/tmp/klaude-read-recovery-final-validation-rlfc4eiy/` |

The isolated launchers and harnesses are `/tmp/klaude_read_binding_launcher.py`,
`/tmp/klaude_read_binding_eval.py`, `/tmp/klaude_read_binding_production.py`,
`/tmp/klaude_read_binding_tui.py` and
`/tmp/klaude_read_recovery_final_models.py` and
`/tmp/klaude_read_recovery_final_sequential.py`. Copies of all eight local harness
files, including their two helper dependencies, and their hashes are retained in
the sequential pair's `harness/` directory. These are not shipped product
capabilities. Unit regressions in the repository provide the durable offline
contract coverage.

## Remaining limitations and next architectural step

- The 3B model now completes this lookup in repeated integrated CLI runs and the
  full interactive sequence. This does not establish semantic reliability for
  arbitrary compound tasks; awkward wording and unnecessary interpretations
  remain possible even when tools and requested facts are correct.
- The final 4B model completes the requested facts with ordinary native calls,
  preserving its three-request path, but still overstates corroboration. This is
  an observed model grounding defect and a limit of Klaude's mechanical outcome
  checks; it is not attributed conclusively to model capability alone. A selective
  grounding check needs evaluation against accuracy and extra latency before
  becoming production behavior. No output rewrite or mandatory judge was added.
- Incomplete native/structured decoding remains observable. Exact binding reduces
  cross-action ambiguity; it does not repair a broken decoder or make a failed
  request evidence of work. Existing recovery and incomplete outcomes stay bounded.
- The earlier Gemma interactive image-evidence interpretation defect was not
  retested in this text-only slice and is not marked fixed.
- GPU-runner failure and slow CPU inference are separate operational constraints.
  No service restart, GPU reset, weight move or automatic model substitution was
  performed as part of this agent-loop change.
- Stockroom CSV and workspace planning/execution were not changed or rerun. There
  is no new claim that either small model completes that benchmark. Workspace
  discovery intentionally retains its default schema; extending the new grammar
  to coding requires the unchanged CSV comparison first.
- Generic capability discovery across built-ins/Skills/MCPs (M2) remains pending.
  The next justified step is bounded, revisable discovery under the existing
  permission and context snapshots, evaluated independently from result
  interpretation. A mandatory planner/judge, broader tool exposure on every
  greeting or another agent executor is not supported by this evidence.
- Python 3.11/3.13 CI, live search websites and paid-provider quality are not
  certified by local Python 3.12 tests and controlled retrieval fixtures.
