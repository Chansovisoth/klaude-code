# Small-model implementation follow-up

Continuation of [the power-user evaluation](power-user-evaluation.md), conducted
2026-10-04 through 2026-10-05. Neither small model has demonstrated
completion of the full benchmark. Automated checks and valid tool calls alone
do not establish feature success.

## Exact benchmark and environment

The exact Stockroom CSV task, dependency-free baseline, original two unittest
assertions, and 13-case independent acceptance harness are unchanged. The full
prompt is quoted in the linked previous evaluation; its working copy remains
`/tmp/klaude-power-user/task.txt` and the baseline is
`/tmp/klaude-power-user/baseline`. A durable copy of the exact prompt, six baseline
files, settings, and acceptance script is now checked in as
[the Stockroom fixture](benchmarks/README.md). Both models remain `qwen3.5:4b` and
`qwen2.5-coder:3b`, thinking off, general context/output 8192/2048, code
16384/4096. No model switch or budget increase was used.

Each run uses the real CLI, isolated config/data, a fresh non-Git project copy,
and a pass-through local Ollama recorder in `/tmp/klaude-small-models`. Actual
request/response bodies, token counts, shell results, and wall times are retained.
Model runs are sequential. The post-change interactive session is named
**TEST KLAUDE FEATURES**, and its provider request contains the exact same prompt
as the one-shot baseline. Unrelated worktree changes are preserved. The user
subsequently authorized a checkpoint commit and push to `main`; unrelated
settings edits are excluded from that checkpoint. Benchmark projects stay
outside Git, and their task still forbids the tested agent to commit or push.

## Observed failures before this pass

| Model/run | Actual behavior | Outcome |
| --- | --- | --- |
| 3B, `before-3b` | 45.95 seconds; one request, 5822 input / 513 output tokens; malformed fenced JSON and invented path/API; no executed tools or edits. | Exit 0 incorrectly resembled completion. Original two tests remain intact, but the CSV success controls fail. |
| 4B, `before-4b` | 2055.03 seconds; 11 requests, 107204 input / 11274 output tokens; 14 executed calls: three listings, six reads, four writes, one validation command. | Reached implementation and 26 generated tests, with 10 failures and two errors; no repair or README update. Original regression suite fails one of two tests, and the acceptance success controls fail. |

The 4B system context was 20740 characters around an approximately 1200-character
serialized objective. Request seven spent 4096 output tokens and 552.86 seconds
without returning a complete native call. Klaude asked for a literal continuation
of unavailable arguments. After eventually writing a 14786-character test file,
the repair request used 16106 input + 278 output tokens, exactly the 16384-token
window. It could not finish a repair call. The eventual final report accurately
admitted failures but returned exit 0.

These are orchestration obstacles in addition to genuine implementation mistakes.
The model also broke compatibility, replay, summaries, and error behavior; removing
context obstacles does not by itself establish that it can implement those rules.

## Architectural changes

- **Selected policy modules:** use callable-tool policy modules and a compact
  execution capability view. Remove unrelated UI/configuration/runtime and
  standalone-code-answer detail during workspace implementation. Keep repository
  guidance, installed Skill metadata, host constraints, and full audit snapshots.
- **Bounded working context:** retain the complete current objective and latest
  complete exchange; omit older complete exchanges from requests without altering
  canonical session/provider payloads. Never invent omitted contents. Release
  only omitted read guards and governor outcome entries so necessary fresh reads
  remain possible. Preserve the original goal through short continuations.
- **Observed execution state:** bounded actual paths, inspected/changed files,
  edit revisions, command exits, checks, recent failures, and next-action guidance.
  A check becomes stale after a file edit. Failed validation or missing work gets
  one completion recovery attempt. A governor final report for observably
  incomplete work emits an error, preserving edits and nonzero one-shot exit.
  A passing check remains evidence rather than a semantic coverage verdict.
- **Declared local actions:** supported local Ollama runtimes start complex
  execution with a schema-constrained action batch; simple turns retain native
  execution and can use this protocol after failed syntax. Up to four independent
  reads share a response during discovery. Once workspace writes/shell are
  callable, the response grammar and normalization permit one action only.
  This structurally prevents appended edits/tests from losing an earlier action
  at the output limit; individual large arguments can still overflow. Only responses to
  that explicitly declared protocol normalize into calls; arbitrary printed JSON
  still never executes. Validation, permissions, jail, and budgets are unchanged.
- **Grounded exploration in recovery:** actual directory/file inventories guide
  path choices; defer other tools until implementation and known tests have been
  inspected. Shared path choices are enforced in the discovery grammar, and a
  final answer is excluded until inspection or a real permission block. This is
  limited to complex eligible local execution; ordinary native calls remain flexible.
- **Public execution plan:** after observed inspection, one optional constrained
  planning request produces two to six small model-written steps. Actual edits
  for scoped files gate implementation completion; current passing checks gate
  validation completion. Later-file edits/current checks align the cursor without
  requiring the model to send a protocol flag correctly. Work done ahead of the
  cursor remains usable. A final review still requires those observed facts. Simple
  requests incur no planning call; failed optional planning falls back to tools.
  This is execution evidence, not independent proof of requirement coverage.
- **Recovery feedback:** retain missing-path error types through duplicate skips
  so a failed filename does not retire the entire reader. Omit `read_skill` when
  the enabled inventory is empty and structured input when the client has no
  handler. A lost call at the output limit gets one smaller fresh action.
  Exact-anchor conflicts allow fresh target reads rather than retiring all edits;
  outside shell paths remain blocked while legitimate project checks remain
  available. Secret-path, dirty-worktree, risk, and permission restrictions are
  preserved. A response's callable snapshot stays stable through its batch.
  Recoverable failures no longer consume an unrelated invalid-call retirement
  counter. Canonical argument errors remain bounded by the governor but do not
  retire the tool. Argument grammars now restrict declared fields, preventing
  protocol controls from appearing inside ordinary tool arguments. A live 4B
  rerun then exposed cross-tool field mixing: file edits carried a shell
  command. Execution now uses a discriminator for each tool with its exact
  canonical parameters, while discovery keeps the existing shared grammar.
  The full catalog is not serialized again beside those execution schemas.
- **Completion and usage:** successful arbitrary shell wrappers do not count as
  project validation. Known incomplete work at the step/governor limit gets a
  host-written factual report and exit 1, rather than another model call that
  may fabricate tests. Tool-free implementation answers get one declared-action
  retry. The TUI retains explicitly marked last-known usage when a failed
  request has no counters; such failures do not charge the previous usage again.
- **Stream completion:** EOF without a terminal marker and embedded runner errors
  are runtime failures. Partial calls are discarded. Constrained finalization
  uses an answer action rather than returning a fake printed call.

No new dependencies, automatic model escalation, larger budgets, mandatory plan
approval, or CSV-specific execution rules were introduced. The response format
uses Ollama's documented [structured output API](https://docs.ollama.com/capabilities/structured-outputs).

## Staged live results

| Stage | Actual result |
| --- | --- |
| Context selection and native recovery, 3B | Smaller system context, but still invalid native calls and no edits. Bounded failure returns exit 1. |
| First declared recovery, 3B | A CLI-wrapper forwarding omission prevented any format request. Fixed the integration and added wrapper/permission coverage. |
| Wrapper connected, `structured-runtime-3b` | Actual format requests recover two executed calls. Wrong path selection, duplicate failure metadata loss, and an empty Skill lookup prevent implementation. |
| Grounded choices, `grounded-3b` | Root listing and README read execute. Unrelated knowledge/input calls still dominate; no edits, exit 1, 100.33 seconds. |
| Narrow exploration with union grammar, `exploration-3b` | Root listing and README read execute. Ollama aborts with “Unexpected empty grammar stack”; the response has no completion marker. No edits, exit 1, 37.60 seconds. |
| Single-object grammar, `simple-format-3b` | 13 requests, 47441 input / 1263 output tokens, 168.73 seconds. Eleven executed calls: two listings, two reads, seven grep calls. Reaches the real CLI but spends the remaining budget searching individual lines; no edits or validation. Exit 1. |
| `after-4b-interactive`, real TUI | Exact prompt and TEST KLAUDE FEATURES name verified. Initial system context 10335 characters / 3600 input tokens versus 20740 / 6284 before. CUDA fault safely retried on CPU, but the later large native store call timed out; only an incorrect CLI edit executed. Turn failed after 24m34s. Normal `/exit` returned 0, which is not task success; wrapper time includes idle time. |
| `after-batch-4b` | 362.36s, nine requests, 33912 input / 865 output tokens. Recovered a native XML-parser error with valid declared actions but repeated no-op initializer writes. No meaningful implementation; exit 1. |
| `planned-4b`, before plans applied to native success | 1251.18s, 21 requests, 107071 input / 5975 output tokens, 24 executed calls and ten proposed repeated reads. CLI/store edits, a stale anchor, an outside shell path, and a wrapper returning 0 while printing an inner exit 1. No generated CSV tests or README edits. All 13 independent cases fail; original two tests pass. Step-limit final fabricated a two-test validation and returned 0. This exposed the completion/wrapper problems fixed next. Despite its directory name, no planning request occurred. |
| `final-3b`, native first | 188s, nine requests, 32367 input / 4337 output tokens. Lost the initial 4096-token native call; declared recovery read README/tests, then repeated root listings. No edits; truthful host failure and exit 1. |
| `bounded-discovery-3b`, enforced discovery grammar | 107.42s, ten requests, 37530 input / 596 output tokens. Nine executed calls: three listings and all six project file reads. One plan, then duplicate listings/reads without editing. Original two tests pass; CSV success controls fail; exit 1 with observed incomplete state. |
| `phased-4b`, plans plus enforced discovery | Interrupted before completion when the CLI process ended during an intervening user turn; no result record, so no completion time or success score. Inspected source/tests and planned work, then edited CLI/store incorrectly. Stale-anchor recovery worked, but nested protocol flags produced canonical argument errors and retired the editor. This motivated typed field grammars and separate argument-error recovery. |
| `typed-3b`, typed argument fields | 29.90s, three requests; two executed calls (root listing and README read), 5712 input / 41 output tokens from completed requests. Ollama aborted an ordinary grounded list-path grammar without a completion marker. Partial response discarded; exit 1; no edits. Original two tests pass; positive CSV controls fail. Earlier identical discovery grammars worked, so this is an intermittent runtime fault, not evidence that object unions alone caused it. |
| `typed-4b`, typed fields before final cursor/argument recovery | 1709.81s, 20 requests, 110573 input / 8373 output tokens. Twenty executed calls: three listings, twelve reads, two edits, two writes, one failing validation. Six proposed repeat reads. CLI command added without its earlier parser regression, but store implementation remained incorrect and tests gained a syntax error. An unchanged write did not count as progress. A 4096-token action exceeded the output limit; smaller retries had arguments for the wrong selected tool and retired it. All 13 acceptance cases fail; untouched original two tests pass; README unchanged; exit 1 with factual incomplete report. Final cursor alignment and typed argument-error recovery address the retirement/bookkeeping symptoms, not the incorrect CSV algorithm. |
| `final-interactive-3b`, latest loop in the real TUI | Exact 1179-character goal and TEST KLAUDE FEATURES name verified. Turn 391.49s, 19 requests, 93074 input / 5925 output tokens. Twenty-one executed calls (three listings, nine reads, nine edit attempts), three proposed repeat reads. All six project files inspected. A 4096-token attempted file write was discarded as incomplete; smaller actions edited the wrong program structure. Six executed stale-anchor failures kept editing available, but repeated cached failures ended the turn. CLI has an IndentationError; all 13 acceptance cases fail, and original/generated tests cannot import it. No project validation was executed. Host final admits unfinished work; session state is failed. `/exit` returns 0 only for normal interactive shutdown; 1375.08s wrapper time includes substantial pre-task idle time and is not task latency. Footer correctly shows the last actual 5796 input / 142 output tokens and 16384 context allocation. |
| `final-4b-resumed`, latest cursor/argument recovery | Genuine `/resume` of the failed `typed-4b` session, then `continue`; the provider request retains the original complete goal. Seven actual directory/read calls refresh current files; old audit bodies are not replayed. A new five-step plan scopes store/tests/docs/checks. The first mutation response nevertheless tries an edit plus a large test rewrite and reaches 4096 output tokens (484.94s), so no partial call executes. Its complete first action also has an invalid extra command field. Cancelled through real Ctrl+C at 837.01s to replace the permissive batch grammar; interruption saved at a safe boundary, then normal `/exit`. No implementation or acceptance improvement; this is an interrupted continuation, not a fresh benchmark success. Last-known 6342 input / 4096 output counters remain visible. |
| `single-action-4b`, fresh baseline after batch cap | 645.77s, seven requests, 30030 input / 4639 output tokens. Eight actual discovery calls; execution replies complete in 1541/1363 tokens instead of losing a mixed batch at 4096. However both edit/write calls include an invalid command argument, then repeat the cached failure. No edits/checks; exit 1. Original tests pass; positive acceptance controls fail. This exposed the remaining shared-field ambiguity, fixed by per-tool discriminators. Faster bounded failure is not feature success. |
| `bound-arguments-3b`, fresh baseline with canonical per-tool execution | 271.39s, 15 requests, 69010 input / 3406 output tokens. Thirteen actual calls: three listings, eight reads, two failed edit attempts; two proposed repeat reads. No malformed or cross-tool argument calls and no grammar-runtime abort. It still invents absent CLI anchors after reading actual source; repeated cached failures stop the turn. No edits or validation; original tests pass, positive acceptance controls fail; exit 1. |
| `bound-arguments-4b`, fresh baseline with canonical per-tool execution | 1819.87s, 20 requests, 108975 input / 10990 output tokens. Twenty-three actual calls: three listings, sixteen reads, four edit attempts (two succeed, two stale anchors); ten proposed repeat reads. All execution argument shapes are valid. Store/CLI edited, but history/atomic saving remain absent, CLI uses Path without importing it, and output is human messages rather than the requested summary. A single oversized test edit still reaches 4096 tokens and is discarded. Tests and README remain unchanged; no validation command is run before the step limit. All 13 acceptance cases fail; untouched original two tests pass; factual incomplete report and exit 1. |

Original checks are run independently from the untouched baseline, even if the
model replaces its own tests. The acceptance harness has positive success controls:
rejection tests passing because `import-csv` is unsupported cannot establish CSV
correctness. No full benchmark success is claimed. The latest interactive 3B run was worse
than the discovery-only run on preservation of existing behavior, despite better
tool execution and truthful failure handling.

## Efficiency observations

Context selection reduced the first 4B request from 6284 input tokens to 3600
in the early interactive comparison and 2793 in `typed-4b`. The `typed-4b` run stayed at 2793–6553 input tokens per request, well below the 16384-token
allocation. The final bound-argument 4B run peaks at 7364 input tokens; its first request
uses 2806. The original failed repair request consumed 16106 input tokens.
Retaining the objective and bounded working exchanges fixes that observed context
pressure. It does not make generated code correct.

There is **no general speed or token saving claim**. `typed-4b` took 1709.81s
versus 2055.03s before, but used 20 requests and 110573 total input tokens versus
11 and 107204. Output fell from 11274 to 8373; fewer new tests were produced,
so this is not an equivalent successful workload. The intermediate 3B TUI turn used
93074 input / 5925 output tokens over 391.49s, versus 5822 / 513 over 45.95s
before. It did more real work but produced a broken CLI; this is not a net
implementation-quality or efficiency win. One retry still spent 4096
  output tokens without a usable action. Several earlier runs failed much sooner
without accomplishing more. Sequential test models still share the host with
ordinary Ollama clients; loading, CPU offload, and contention affect latency.

Batch discovery let 3B read all actual project files, rather than exhaust its
budget on individual grep queries. A plan adds one request only for eligible
complex work. Repeated reads remain a cost: omitted working exchanges sometimes
require fresh evidence, while other repetitions are unproductive model choices.
The rendered tool catalog and execution state still grow after discovery;
`typed-4b` system content reached 17742 characters from an initial 11868, and
final bound-argument 4B reaches 17519 from 11919 despite bounded dialogue. Simple requests retain their existing direct/native path.

The final canonical-binding 3B run falls to 271.39s / 69010 input / 3406 output
from the intermediate interactive 391.49s / 93074 / 5925 and preserves the
original program, but still implements nothing. The final 4B run takes 1819.87s /
108975 / 10990 versus the pre-pass 2055.03s / 107204 / 11274. It spends more
requests on repeated reads and fewer on useful work: no tests/checks/docs in the
last run versus generated failing tests before. That is not a functional or
universal efficiency improvement. Canonical binding does demonstrably eliminate
the observed cross-tool argument mistakes and allows real file edits; the
remaining software task still fails.

## Regression validation

- Complete current worktree after canonical argument binding:
  **2392 passed, 19 skipped**, 115.90s; preceding gates 2388/19 and 2391/19.
- Exact selected checkpoint export, excluding unrelated settings edits:
  **2376 passed, 19 skipped**, 137.58s; preceding gates 2372/19 and 2375/19. Its CLI/core/local-tool imports were
  verified to resolve to the exported tree, using the repository's locked
  dependency environment. This is a separate full gate, not focused-test success.
- Focused live-HTTP orchestration/provider regression gate: **241 passed**.
- Ruff passed; production mypy passed **82 source files**, including the exact
  checkpoint export. `git diff --check` passed.
- Package smoke: all **five wheels** built and installed, package imports and
  installed `klaude --help` passed for both the current worktree and exact
  selected checkpoint. An initial isolated attempt could not fetch
  the build backend; propagating `UV_OFFLINE=1` used the existing cached backend
  and completed the entire smoke check.
- Coverage includes plan approval, cancellation, malformed calls, path recovery,
  shell failure tracking, dirty-worktree safety, cache invalidation, validation
  reruns, whole tool exchanges, permission denial through the runtime wrapper,
  fresh reads after omission, completion failure, and incomplete streams.
  New coverage includes stale-anchor recovery, outside-path recovery without
  escaping the jail, step-limit factual failure, arbitrary-wrapper nonvalidation,
  native/declared planning integration, actual failing-check repair/rerun,
  observed-path grammar, cursor alignment without protocol flags, canonical
  argument failures retaining valid tools, rejecting oversized execution
  batches without losing discovery batches, binding each selected tool to its
  canonical parameters without duplicating the catalog, and honest counters after a failed
  request. These tests establish orchestration behavior, not model task ability.

## Remaining model and runtime limitations

- 3B can follow constrained project discovery, but repeatedly fails to move from
  inspection to useful implementation. Its plan confuses acceptance requirements
  with validation phases and omits tests/docs. The intermediate TUI run made
  three successful edits but mixed entry-point and CLI code, damaging the public
  API. The final canonical-binding run invents absent source anchors and makes
  no successful edit.
  Native calls sometimes become invented API/program text.
- Across runs, 4B confuses transaction identity with stock keys, mishandles
  dry-run, skips existing SKUs, fails to preserve history, and saves
  invalid/partial batches. Its final implementation omits history and labels an
  ordinary write atomic without implementing atomic replacement. These are substantive
  reasoning failures even with the complete task and source available.
- Clear syntax diagnostics do not reliably produce a repair. Rewriting the same
  broken file, selecting the wrong tool for generated arguments, and oversized
  edits still waste the budget. More prompt prose has not solved this.
- Ollama can abort constrained decoding with “Unexpected empty grammar stack”
  even for a small schema without object unions. GPU runner failures and slow
  generation remain external runtime risks. Klaude discards incomplete calls and
  fails honestly; it does not transparently migrate to another model.

## Remaining Klaude limitations and next step

Execution state and model-authored plans record facts, not requirement coverage.
Cursor alignment now follows observed edits/checks, but requested outcomes can
still be omitted from a plan. Recognizing a test command cannot prove its tests
cover the requested behavior or were not weakened. Shell edits do not supply the
file-revision facts of file tools. State is rebuilt each turn rather than a
persisted project task record. Restored audit events are not replayed as tool
results; evidence must be re-read. A successful request after failure can retain
last-known counters, but unknown failed-request usage remains unknown.

The context estimate is approximate. A newest oversized exchange or large fixed
schema/repository instructions can still exceed its target. Discovery enumerates
paths only within a bounded inventory; it is not an index for a large monorepo.
The current phase structure narrows initial discovery, then exposes a relatively
large decision space again. Execution now binds fields to their selected tool, fixing the observed
command-argument mixing. Valid schemas still cannot ensure valid programs or
accurate source anchors. Large old/new string payloads remain expensive and
can overflow even a single action. Complex eligibility currently uses a length/intent
heuristic and may misclassify short complex requests or verbose simple ones. Partial file edits survive cancellation/failure;
there is no multi-file transaction or automatic rollback.

The next justified experiment is **phase-scoped working context**: the original
constraints plus one active subtask, its actual files, and its current diagnostics;
a smaller applicable tool set; and a bounded source snapshot keyed to known file
revisions. Compare that against the same fresh fixture and budgets before adding
more machinery. Project-supplied acceptance checks would also improve semantic
completion evidence where they exist. Do not embed the external CSV harness in
production or count a small model's self-written tests as independent acceptance.
A stronger local/cloud model comparison would help separate residual orchestration
cost from capability, but switching models is a user decision and was not used
to manufacture benchmark success in this pass.

## Conclusion and retained evidence

Neither model now completes the full CSV benchmark. Improvements are established
for context headroom, tool-call correctness, bounded recovery, and honest failure;
no improvement in complete implementation quality has been demonstrated. The
first remaining bottleneck is exact-source editing and stalled execution: valid
calls repeat or carry inaccurate anchors, and the budget expires before checks.
Model reasoning also fails substantive data/API requirements. This is not enough
evidence to attribute every remaining failure to model size.

Klaude still leaves too much sequencing and requirement tracking to a fallible
public plan. Steps can overlap files; touching a file does not establish every
goal for it. Plans are not revised or semantically rejected after poor
decomposition. Whole exchanges preserve old/new edit blobs, then require fresh
reads when omitted. Validation has no reserved budget, so a model can use every
step without checking its edited project. The next controlled ablation should
combine phase-scoped current file snapshots with a smaller applicable tool set,
explicit task constraints, and reserved validation/repair opportunities. Keep
simple tasks direct, preserve all safety gates, and repeat this fixture at the
same budgets. Do not add more system prose or label passing old tests as new
feature acceptance.

Temporary evidence: `/tmp/klaude-small-models/RUN/{request-*.json,response-*.json,
timing.jsonl,cli.log,metrics.json,independent-verification.json}`. Interactive
runs use saved SQLite events instead of a one-shot CLI log. Key sessions:
`d1afaa08752e4e4d84a88bb304d4be4e` (final 3B TUI, TEST KLAUDE FEATURES),
`619294bf520d4edf8fc2ebd9a32d9842` (typed 4B and explicitly interrupted cloned
resume, renamed TEST KLAUDE FEATURES). The durable fixture and reproduction
commands are linked above; temporary evidence is not shipped as repository data.
