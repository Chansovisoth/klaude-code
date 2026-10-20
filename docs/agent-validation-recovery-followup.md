# Validation and recovery follow-up

The subsequent authorized [cloud comparison and phased-execution work](agent-phased-execution-validation.md)
records new provider controls and experiments separately; the local results below
remain historical evidence.

## Scope and baseline

This follows the completed [capability-discovery evaluation](agent-capability-discovery-validation.md).
Its results remain historical evidence; this pass does not replace them with unit
test claims. Repository baseline: `90137f46f59f15346f16401c2ecd5b6aecc8a7f7`,
branch `klaude/20260908-1448`. The live, already-dirty worktree is the implementation
under test. No unrelated changes were reset, stashed or discarded; no commit,
push, dependency change or model substitution is part of this pass.

The user accepts testing on this machine despite the previously observed Ollama
grammar and GPU failures. Those failures are recorded separately from mistakes
in the agent and model. This pass does not repair the driver or change the server.

Private evidence root: `.klaude/data/validation-recovery-sklj25o6/`.
`baseline-production-sha256.json` records the preceding verified implementation;
`scope.txt` explains the initial status capture boundary. Source snapshots and
per-run hashes distinguish this pass from the earlier extensive uncommitted work.

**Outcome:** the observed host defects below are fixed, and deterministic literal
output improves in the real TUI. **Neither small model completes the full CSV
benchmark.** The final 4B attempt still implements only part of storage, breaks
both original tests and performs no executed project check. These changes do not
establish better end-to-end CSV implementation performance.

## Observed problems and causes

| Previous observation | Implementation cause or remaining uncertainty |
| --- | --- |
| A weak plan omitted tests or documentation, constraining subsequent edits. | Constrained execution projected only active/next planned paths even when other files had already been discovered. A proposed plan became an unnecessary restriction beyond actual workspace permissions. |
| The 4B CSV run wrote three files but never checked them before exhausting its elapsed allowance. | Validation was required at completion, but implementation could consume the budget first. Large generations and CPU fallback also consumed substantial time; the agent does not control those decoding costs. |
| A broken Python edit could require a later shell call to reveal syntax problems. | Edit results reported application of the edit without cheap static syntax feedback. |
| A terminal provider failure left an old public plan as the latest assistant turn. | The error path emitted the error/status but did not reliably append a factual workspace-state summary. |
| `Reply exactly OK. Do not use tools.` produced `OK.` in 35.25 seconds. | A fully specified literal was still passed through probabilistic generation. |

The previous CSV outcomes were **3B: 10/13 acceptance cases, including zero of
three positive feature cases; 4B: 1/13**. Rejecting an unknown command accounts
for misleading rejection-only passes. Neither was a completed implementation.
Both are compared using the same fixture and grading procedure below.

## Changes

### Plans guide execution without hiding discovered files

`WorkspaceExecution.allowed_edit_files` retains the active/next plan projection
and includes paths observed through actual workspace tools. Existing tests and
documentation omitted by a weak plan remain available. This does not invent
paths, authorize writes, bypass dirty-tree protection or change the canonical
tool schemas. Each response is still checked against its own immutable schema
projection; executing a plan update does not retroactively authorize another
call from the same response.

### Earlier validation within the existing budget

Workspace execution records a validation checkpoint after newly changing tests,
two non-document files, or an unchecked change when at most four model steps
remain or 55% of the elapsed allowance has been consumed. Already-tested files
do not by themselves trigger another checkpoint after a documentation change.

At an ordinary checkpoint, the local constrained path offers project checks and
inspection instead of another implementation action. Under budget pressure it
offers only the available shell/check tool; failed checks reopen inspection and
repair. The model still selects the command;
the normal shell permission and workspace boundaries still apply. No command
runs automatically and no extra
model, planner, judge or allowance is added. Native paths retain their existing
flexible schemas and receive execution-state guidance; they are not newly
certified to have the same constrained behavior.

An optional plan is not requested when fewer than six steps remain or 35% of
elapsed time has already passed. This avoids spending the remaining allowance
on a late plan. Check recognition also includes common `uv run`, `poetry run`
and `pipenv run` wrappers. Recognition establishes observed check execution,
not semantic requirement coverage.

### Cheap feedback on actual Python edits

After an applied `.py` edit of at most 65,536 characters, the tool parses the
source with `ast.parse`. A syntax error is returned with a bounded line/message
diagnostic and retained in execution state until repaired or freshly verified.
Known syntax errors prevent completion. The edit remains applied: this is not
a rollback or a claim that syntactically valid code works. Nothing imports or
executes the edited module and no bytecode is created. Larger files and parser
resource failures retain normal tool behavior without a false syntax verdict.

### Factual terminal failure summaries

On unrecoverable provider failure during a workspace task, the agent saves and
displays a summary drawn from observed changed files, validation and unresolved
state before emitting the error. It makes no further model request. The failure
continues to produce a failed turn and CLI exit 1. Cancellation follows its
existing separate path.

### Exact literal responses

A complete, unconditional request to output user-supplied quoted text, or an
explicit `exactly` request for one bare token, returns that text directly.
Whitespace, punctuation and backslashes inside quotes are preserved. Conditions,
destinations, transformations, additional actions and non-printable payloads
do not match. The fast path is disabled when new image inputs are present.
Tool-looking words inside the literal remain text. Normal dialogue is persisted
and fresh usage is zero; previous usage is not reused. This is deliberately a
narrow deterministic operation, not a general natural-language executor.

### Implementation references

| Concern | Source |
| --- | --- |
| Literal matching | [intent.py](../packages/core/src/klaude_core/intent.py), `exact_literal_response` |
| Turn routing, planner timing and terminal failure path | [agent.py](../packages/core/src/klaude_core/agent.py), `Agent._run` |
| Observed edit scope, checkpoints and diagnostics | [workspace_execution.py](../packages/core/src/klaude_core/workspace_execution.py), `WorkspaceExecution` |
| Passive edit syntax feedback | [toolkit.py](../packages/tools_local/src/klaude_tools/toolkit.py), `_edit_result` |
| Regression contracts | [workspace tests](../tests/unit/test_workspace_execution.py), [literal/compound tests](../tests/unit/test_compound_tasks.py), [intent tests](../tests/unit/test_intent.py), [tool tests](../tests/unit/test_tools.py), [discovery tests](../tests/unit/test_tool_discovery.py) |

## Interactive verification

The real bare CLI resumed a private copy of the existing Gemma session
`41098d8394924fbc87f5812b1f20bed8`, preserving the original evidence. Three new
turns were sent through its actual TUI and read back from persisted history:

| Prompt | Actual saved answer | Model/tool calls | Agent elapsed |
| --- | --- | --- | --- |
| `Reply exactly OK. Do not use tools.` | `OK` | 0/0 | 0.037 s |
| `Print exactly "  release: ready.  ".` | Two leading and trailing spaces preserved | 0/0 | 0.054 s |
| `Print exactly "search the web".` | `search the web` | 0/0 | 0.026 s |

The configured provider/model remained real Ollama/Gemma. These turns exercise
the CLI, TUI, restoration, routing and persistence, **not new model reasoning**:
no inference is needed for this operation. Harness-observed delivery was about
0.30 seconds per turn, including its polling. The previous incorrect `OK.` took
35.25 seconds. This improvement removes unnecessary generation; it does not
claim faster model decoding. The client exited normally, without touching the
original session or stopping Ollama.

Evidence: `literal-tui-j3o4zvab/results.json`, terminal capture and 120-column
text/SVG capture under the private pass root. An earlier harness attempt stopped
before sending prompts because restored history moved the session ID out of its
visible-screen check; the corrected harness checks raw output. That harness
failure is not an application failure.

A separate controlled-generation run uses the actual `ask` CLI, native adapter
parsing, file tools and SQLite persistence. After inspection and exactly one
applied `app.py` edit, two scripted incomplete responses exhaust the existing
single retry. The CLI exits **1** and saves the changed path, `Validation: not
run`, remaining check/review steps and the failure reason. There is no repeated
write or extra summary-generation call. Evidence:
`terminal-failure-swlw4bvo/result.json` and trace. This is fault injection, not a
local-model quality measurement.

The first version of this harness used a short request that does not activate
the existing complex-task execution state (600-character threshold). Its file
edit was preserved and exit 1 was correct, but it had no factual workspace
summary. The summary improvement is therefore scoped to tracked complex tasks;
uniform summaries for shorter editing requests remain a known limitation.

## Unchanged CSV regression

Fixture: [stockroom.json](benchmarks/stockroom.json). Both original models retain
the original native Ollama configuration and task; external acceptance cases
are withheld until the attempt ends.

- Prompt SHA-256: `c1c41dfa913d8c1355e6ab8aa34648f5c80ff63fc2245e25f0b5fd379f5b5f7d`.
- Acceptance SHA-256: `30d08650be70448be0adff78ce5b3278c4b47aeb5def8d5f2b32acf94ec93eba`.
- `qwen2.5-coder:3b`, Q4_K_M, digest
  `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`.
- `qwen3.5:4b`, Q4_K_M, digest
  `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.
- General context/output: 8192/2048; code context/output: 16384/4096;
  `think=false`; 20 model steps, 40 tools, 1800-second safe-boundary allowance.
- Non-Git temporary workspaces protect the real dirty repository; isolated
  config/data, serial inference and per-attempt source/request/trace captures.
- External harness timeout remains 2200 seconds, followed by SIGINT and bounded
  cleanup. Original held-out tests, generated tests and external acceptance are
  graded separately after autonomous execution.

### First iteration: full autonomous attempts

The initial live runtime snapshot reports Ollama **0.33.3**, the same model
digests, and **CPU-only** placement (`size_vram=0`) for 3B at context 16384.
This differs from the preceding mixed GPU/CPU failures. New wall-clock numbers
therefore describe this machine's actual runs, not a controlled speedup.
No benchmark inference overlaps the full suite. Read-only inspection and brief
focused contracts are not a dedicated performance laboratory.

The 3B attempt's first nine requests perform serial inspection in **972.901 s**,
using 31,414 known input and 286 output tokens, peak input 4,259. It reads the
nearly empty initializer and import-forwarding entry point separately, despite
read batching being available. The optional planner is correctly skipped after
this late inspection. The next request spends 266.783 s discovering nonexistent
`add-csv` tools, then the model requests already-delivered files again; the
existing duplicate guard blocks their execution. The constrained request does
contain tool descriptions, including the discovery tool's explicit purpose.
This does not establish a missing-description defect or context exhaustion.
It exposes model action-selection weakness and substantial CPU request cost.

The completed 3B attempt (`5130f6cf4d8942329c9fecee836baa9e`) takes **1817.15 s**
and exits **1** without external interruption. It performs 13 model requests,
13 tool attempts but only 10 executions; three duplicate reads are blocked.
No file changes and no autonomous checks occur. The no-progress governor stops
at its existing safe boundary (elapsed 1815.22 s), and the saved final answer
correctly says no edit executed and validation did not run. No provider exception
is observed. Known usage: **54,247 input / 443 output tokens**, no unknown-usage
requests, peak input **5897**, largest captured request 23,705 characters.
Original tests remain **2/2**; the so-called generated suite is only those same
unchanged tests. Acceptance is **10/13, zero of three positive cases**; the CSV
command is absent. This is **not better CSV implementation progress**. The
run cannot exercise the new checkpoint or syntax feedback because it never edits.

The 4B placement snapshot also reports `size_vram=0` at context 16384 with the
expected digest. Its completed attempt (`f204a3f8e6064e459ef05737c482d11a`) takes
**1988.02 s**, with **7 requests, 11 executed tools, 33,327 input / 2275 output
tokens**, zero unknown-usage requests and no provider exception. Peak input is
**6885**, largest captured request 28,326 characters. Three requests inspect the
project using batches; the plan takes 253.130 s, followed by a 672.357 s storage
edit. Passive syntax feedback correctly reports valid Python. The model marks
that change `completed_step=false`, so its unfinished helpers are not proof it
considered the storage feature complete.

The first checkpoint restricts further writes and advertises validation, but
still allows read tools. The model spends **369.612 s** rereading the unchanged
CLI and **278.269 s** reading the changed store instead of checking. The original
store read is stale after the edit, and earlier full results have left the
bounded working projection: these are not all necessarily unjustified rereads.
However, permitting another inspection round under time pressure fails to
reserve useful validation. This is an observed orchestration weakness.

Only `stockroom/store.py` changes. Original tests remain **2/2**, and no tests or
README changes are added. The CLI command is absent: acceptance **10/13**, with
**zero positive cases**. The stored partial implementation contains placeholder
history methods, ignores dry-run and uses direct writes despite its atomic-save
docstring; this is unfinished work, not functioning transaction persistence.
No autonomous check or repair happens. The governor ends at a safe boundary,
exits **1**, and saves a factual incomplete answer. Neither attempt hits the
external harness timeout.

### Before/after observations

These are individual observed runs, not repeated statistical trials. CPU-only
placement prevents attributing wall-time differences to the code alone.

| Model / run | Wall s | Requests | Known input / output | Changed files | Autonomous checks | Positive acceptance | Original tests |
| --- | ---: | ---: | --- | ---: | ---: | --- | --- |
| 3B preceding pass | 198.54 | 13 | 44,852 / 671; 2 unknown | 1, incorrect CLI edit | 0 | 0/3 | 1/2 |
| 3B first iteration | 1817.15 | 13 | 54,247 / 443 | 0 | 0 | 0/3 | 2/2, unchanged project |
| 4B preceding pass | 1856.78 | 9 | 39,913 / 4037; 1 unknown | 3 | 0 | 1/3 | 2/2 |
| 4B first iteration | 1988.02 | 7 | 33,327 / 2275 | 1, partial storage | 0 | 0/3 | 2/2 |
| 4B final autonomous | 1920.98 | 7 | 32,453 / 2194 | 1, incorrect partial storage | 0 executed; 1 rejected smoke proposal | 0/3 | 0/2 |

The lower 4B token/request totals do **not** establish useful efficiency: it
implements less and still does not check. Both first-iteration generated-test runs are
only the original two tests. Both apparent 10/13 acceptance totals are rejection
passes for an unknown command, not successful CSV features. No full CSV
completion is claimed. Final incomplete reports remain accurate.

### Second iteration: tighten the pressured checkpoint

The observed 4B read loop justifies one further general change: an unchecked
edit under budget pressure projects only `run_shell` when it is available.
Earlier checkpoints retain inspection options. Syntax failures and failed checks
reopen normal inspection/repair, including when pressure remains. No command is
synthesized or executed automatically; normal permission, risk and workspace
checks remain authoritative. This is limited to already-tracked complex local
execution; it does not force a workflow on short requests.

The relevant rerun uses the same exact CSV fixture and actual CLI. Its first
five recorded responses are explicitly replayed, actual tools reconstruct the
same partial project, and the original approximately 1338 seconds of elapsed
budget are carried forward before one **fresh** 4B checkpoint request. Replayed
generations have unknown usage and are never billed as newly observed tokens.
The probe ends deliberately after that check; it cannot establish full autonomous
benchmark completion or a whole-task speedup. The final pressure refinement does
not affect the completed 3B run, which never reaches an edit/checkpoint.

The first fresh probe (`checkpoint-probe-xgn7kk2l/`) takes **361.987 s** for one
real request, with 6713 input / 33 output tokens. It executes
`python3 -m stockroom --help`, not tests. Exit 0 for help is correctly **not**
accepted as validation, and the probe's check criterion fails. Its original
1338.542 s elapsed prefix is preserved. A shell-only choice does not ensure a
useful check; this negative result is retained.

### Third iteration: retain context needed for validation

Comparing actual request captures identifies a second host problem: the README
test command is absent at the checkpoint. The original working-source projection
has room only for a partial test file after removing older exchanges; the
shell-only version retains more code, but still omits the README. The model is
being asked to select a check without the instructions it already read.

Validation checkpoints now prefer already-inspected documentation/configuration
excerpts through `WorkingSources`, ahead of incidental code. No file is read
automatically, no command is extracted or synthesized, and no allocation grows.
Existing version checks, range labels, cache limits and untrusted-source
boundaries still apply. A real-tool regression confirms the exact README check
instruction survives a large edit and the project check runs successfully.

The second same-prefix probe (`checkpoint-probe-i6fxwmm7/`) demonstrably supplies
the full README and original test file, including the exact test command, in
**27,165 content characters**, versus 27,211 for the first probe. The fresh
request takes **355.382 s**, with **6623 input / 45 output tokens**. It chooses
`python3 -m stockroom --store stock.json import-csv tests/data/sample.csv --dry-run`.
That smoke probe fails with exit **2** because the CLI command does not exist;
the proposed CSV fixture path was also never discovered. This is actionable
negative feedback, **not a passing test suite or full benchmark success**.
The probe deliberately ends after that one shell action, so it does not establish
model-driven recovery. Captured source hashes distinguish both refinements.

This result exposes another host edge: an unrecognized failing shell probe
could leave the pressured checkpoint closed to edits, since it was not classified
as a test-suite check. Current-revision nonzero shell exits now reopen inspection
and repair with explicit failure guidance. An applied repair returns to the
checkpoint. Successful help output still cannot become passing validation.
The initial exploration guard also takes precedence if a native edit arrived
before inspection, preventing an empty intersection of discovery/checkpoint
choices. Focused regression coverage exercises both paths.

### Final autonomous rerun

A fresh **4B** attempt on the unchanged full fixture follows these refinements.
It does not replay decisions or reset the task's budgets. The earlier complete
3B attempt never reaches an edit/checkpoint,
so the final checkpoint/context refinements do not change the branch it exercised;
it is not represented as a new final-source 3B trial.

The two decision-point probes remain separate from full autonomous measurements.
Neither a successful shell process nor restored source context establishes
complete CSV implementation.

Final full-attempt evidence is captured separately in
`stockroom-final-v0oxkv3k/`, with production hashes frozen in
`final-source-sha256.json`. Session `ddedced6149443398322239668122823` exits **1**
after **1920.98 seconds**, with no external timeout or provider error. The
post-run native snapshot confirms Ollama 0.33.3, the exact original 4B digest,
context 16384 and **CPU-only** placement. No runtime or model setting changes.

Seven real requests use **32,453 input / 2194 output tokens**, zero unknown-usage
requests, peak input **6134**, largest captured request **24,735 characters**.
Seventeen tool proposals yield eleven executions. Three duplicate root listings
and two duplicate reads are blocked; there are no repeated executed file reads.
A directory passed to `read_file` fails safely. Four initial discovery requests
take 670.228 seconds, and the late optional plan is correctly skipped. A further
310.597-second request proposes another already-delivered storage read.

The storage write takes **641.566 seconds** and applies 6792 characters. AST
feedback reports valid syntax; this is correctly not treated as correctness.
The next captured request offers only `run_shell` and retains the README's exact
`python3 -m unittest discover -s tests -v` instruction within 24,522 content
characters. Thus the final autonomous run exercises both the narrowed
checkpoint and the source-retention change, without additional reads or a larger
context window.

The model instead proposes
`python3 -m stockroom --store /tmp/test_stock.json import-csv /tmp/test_import.csv --dry-run`.
Neither test file was created or discovered. The unchanged workspace boundary
rejects the absolute outside-workspace paths with `WorkspacePathError` before
command execution. This is **one rejected smoke proposal, zero executed checks**,
not a test failure followed by repair. The 296.566-second response arrives after
the 1800-second safe-boundary allowance; the next boundary stops the turn before
another model request. Elapsed governor time is 1919.393 seconds. Its saved
answer identifies the changed storage file, says validation did not run and
reports the time-budget stop. It does not claim completion.

Independent post-attempt grading finds **0/2 original tests** and the same two
failures in the unchanged generated-test directory. The edit removes constructor
conversion from string to `Path`, breaking the CLI, and reverses the temporary
file replacement, breaking new-store saves. It also rejects negative deltas
despite the signed-delta requirement. The CLI import command, transaction
integration, tests and README remain unfinished. Acceptance is again **10/13,
zero of three positive cases**: the apparent passes are rejections of an unknown
command. No benchmark files were repaired by the evaluator.

The checkpoint now prevents another read loop, and its retained instructions
remove a verified context defect. **It still does not produce useful autonomous
validation or more complete implementation.** A large generation consumes most
remaining time, and the model chooses a guessed smoke action despite the real
test command being available. Lower request/token totals and shorter wall time
do not establish a quality or efficiency gain. Status questions did not restart
the attempt. The bounded owned pipeline starts the regression gate only after
inference ends, avoiding suite/model contention.

No context-window rejection occurs in these fresh CPU attempts. Their observed
peak input counts remain below the unchanged 16,384-token coding allocation,
including the 4096-token output reserve. This does not rule out attention or
instruction-following limits: the earlier source-selection defect could remove
check instructions independently of the provider's context limit.

## Regression validation

- Focused contracts after the first fixes: **145 passed**.
- Expanded reliability, workspace, CLI and compound-action selection:
  **1132 passed, 1 existing skip** in 77.08 seconds.
- Actual-tool integrations exercise an incomplete plan, an omitted existing test,
  a failing project check, repair and a passing rerun; a late-budget scenario
  verifies that optional planning is skipped without expanding the allowance.
- Ruff passes; production mypy passes across 153 files.
- After the pressured-checkpoint refinement, **130 focused tests pass** in
  8.89 seconds, including reopening inspection and repair after a failed check.
- Final execution/discovery/compound/source-cache selection: **145 passed** in
  9.54 seconds, including retained check instructions, failed smoke recovery
  and an available inspection route before initial exploration completes.
- A permanent regression tests a preserved actual edit, two incomplete responses,
  one saved factual report and no summary inference; its focused run passes.
- The first full locked gate finished in 728.67 seconds with **3697 passed,
  19 existing skips and 3 failures**. Two discovery tests still expected an
  inference request for literal output; they now check zero requests and expiry
  of discovery authority. The new repair integration used equal-length source
  writes within one second, permitting stale timestamp/size-based CPython
  bytecode. Its repaired fixture changes source size without sleeps or cache
  deletion, retaining the same actual failing/passing checks. The relevant
  rerun passes **86 tests** in 8.70 seconds. Production hashes were unchanged.
- Final frozen/offline **`make check` passes** on Python **3.12.3** in
  **738.04 seconds**: **3703 passed, 19 skipped** in 735.19 seconds, Ruff clean,
  production mypy clean across 153 source files. The 19 existing skips are
  explicitly superseded retrieval-policy tests, not missing runtime dependencies.
  Evidence: `gate-76pgllj1/check.log`, `pytest.xml` and `test-summary.json`.
- The final JUnit results confirm the existing approved-plan continuation and
  scope constraints, pre-header cancellation, bounded incomplete-call recovery,
  missing-path discovery, nonzero-shell tracking, post-edit rereads and identical
  validation reruns, dirty-tree write protection, argument checks before approval,
  and one-shot failure persistence/exit contracts all pass. Controlled real-CLI
  fault injection above separately verifies failure exit 1 and the saved summary.
- All **154 production Python/prompt hashes** match between the final autonomous
  benchmark and the final gate, and remain unchanged at gate completion. The
  earlier failed gate remains at `gate-qxv4gy70/`; it is not counted as passing.
- The final gate's offline packaging step fails before building because this
  cache lacks `hatchling`. `gate-76pgllj1/package.log` retains that environment
  failure, and the combined pipeline correctly records `gate_failed` rather
  than success. A separate **network-enabled `make package-smoke` retry passes
  with exit 0**: five wheels built and installed together in an isolated
  temporary environment, all public packages imported, installed `klaude --help`
  succeeded. The retry uses `UV_FROZEN=1 UV_OFFLINE=0` and the same task cache,
  populating missing build/runtime downloads without changing repository
  dependencies or lockfiles. Evidence: `gate-76pgllj1/package-retry.log` and
  `package-retry-result.json`. No production change followed the passing suite;
  the initial offline packaging failure is not rewritten as a passing run.
- Final source hashes and benchmark prompt/acceptance checksums remain unchanged;
  report links resolve and `git diff --check` passes. No commit or push was made.
  These are local Python 3.12 results, not new Python 3.11/3.13 CI evidence or
  paid-provider generation certification.

## Remaining boundaries

Plans, file edits and check success still cannot prove every natural-language
requirement was implemented. Models may generate wrong tests, misunderstand
transaction semantics or choose an unhelpful check. Checkpoints create an
opportunity for diagnosis, not an independent correctness judge. Syntax feedback
only covers bounded Python source. Non-Python diagnostics remain project-owned.

The elapsed governor still checks safe boundaries, not a hard cutoff inside a
healthy inference request. GPU/grammar failures and slow CPU fallback remain
external runtime conditions. This pass does not silently select a different
model, enlarge the context window or increase budgets. Broad paid-provider
inference, model-specific semantic mistakes and narrow-terminal layout are not
newly certified by these changes.

### Model limits versus remaining orchestration work

- **3B action selection:** the full source and supplied mutation tools do not
  produce an implementation in the observed CPU attempt. Wrong discovery terms
  and repeated completed reads persist with tool descriptions present. This is
  evidence of model decision weakness, compounded by expensive requests; it is
  not proof of a universal 3B capability ceiling on stable faster hardware.
- **Large execution slices:** the 4B storage edit takes over eleven minutes and
  remains unfinished. The current planner's one-file goals do not necessarily
  produce small behavior changes with corresponding tests. A checkpoint between
  responses cannot recover time already spent on a large generation. The final
  skipped-plan attempt still takes over ten minutes for one incorrect edit;
  removing the optional plan alone does not solve this bottleneck.
- **Context selection:** preferring inspected docs helps this observed check
  context, but the existing eight-excerpt/32,000-character cache and request
  budget still bound retention. Evicted or unread instructions require a new
  authorized read. A source preference is not durable task state.
- **Discovery choices:** the shared local discovery grammar can still permit
  mismatched path/tool choices and redundant read batches. The final run records
  a directory passed to `read_file`; it fails safely. Duplicate guards prevent
  repeated execution, but redundant proposals still consume output and budget.
  Those are remaining opportunities for better tool presentation, not claims
  that all failed choices are intrinsic model limitations.
- **Validation meaning:** a shell tool choice is not automatically validation.
  Help output, a guessed smoke fixture, passing old tests and model-authored
  assertions cannot independently establish requested behavior. Typed failures
  must drive another cycle; remaining budget and model judgment still matter.
- **Measurement:** the Ollama adapter retains total/load time and token counts,
  but currently omits native prompt-evaluation and generation durations. These
  captures cannot separate prefill, decode and cache effects reliably.

The next justified architecture experiment is **smaller behavior-and-test
slices**, using the existing execution state rather than another mandatory
planner or executor. Measure phase-relevant tool/context selection and bounded
edit size on the unchanged benchmark, with native stage timing captured first.
Test exact discovery bindings separately across both models instead of assuming
that a more complex grammar helps. Ordinary short turns should retain their
direct path. Preserve the same permission, provenance, dirty-tree and recovery
boundaries, and keep resource choices visible and user-controlled.
