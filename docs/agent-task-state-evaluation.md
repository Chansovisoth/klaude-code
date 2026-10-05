# Agent task-state evaluation

Continuation of [source-context evaluation](agent-source-context-evaluation.md)
and Phase 1 of [the orchestration plan](agent-orchestration-plan.md), 2026-10-05.
This pass addresses request references, active file scopes and estimated request
admission. Later phases have not started. Neither model completes the benchmark.
Final-candidate GPU comparisons are pending a hardware reset; passing the host
suite does not establish benchmark completion.

## Unchanged comparison

Use the exact [Stockroom fixture](benchmarks/stockroom.json), its six baseline
files, two original regressions and thirteen independent acceptance cases.
Prompt SHA-256:
`c1c41dfa913d8c1355e6ab8aa34648f5c80ff63fc2245e25f0b5fd379f5b5f7d`.
Acceptance SHA-256:
`30d08650be70448be0adff78ce5b3278c4b47aeb5def8d5f2b32acf94ec93eba`.
Models remain `qwen2.5-coder:3b` and `qwen3.5:4b`, thinking off, code
context/output 16,384/4,096 and general 8,192/2,048. Existing step, tool, token
and thirty-minute turn budgets remain unchanged. No acceptance feedback is
provided during an autonomous attempt; projects/config/data are isolated and
outside Git. Production sources are frozen and imported through the actual CLI.

The earlier CPU runs explicitly set `num_gpu = 0` only in isolated evaluation
configurations. At that time, Ollama's service diagnostics reported failed CUDA
initialization (`cuInit failed: 100`, no CUDA-capable device), following the
previous runtime failure. No global configuration, service or driver changes
are made. CPU wall times are not comparable with prior GPU runs. Keep runtime
capacity, model capability and agent defects separate in the conclusion.

After the subsequent reboot, the temporary workspace and v9 TUI process were
absent. The completed v7 run, frozen sources and earlier host diagnostics were
restored from the ignored archive. The v9 TUI outcome cannot be established and
is recorded as interrupted, not a completed comparison. The final v13 runs use
the original placement configuration; Ollama reports the 3B model on CUDA at
16,384 context. Record final GPU and earlier CPU timings separately.

## Evidence and root causes

- The previous 3B plan classified application guarantees as validation steps
  and omitted requested tests, documentation and review. The host accepted the
  structural classification, leaving the smaller model too much orchestration
  to invent.
- Request goals survived conversation projection, but plans had no exact
  links to requested outcomes. An omitted requirement was indistinguishable
  from deliberate decomposition.
- Protocol completion was applied before actions. A passing check could also
  advance the cursor automatically, so a completion flag could skip the next
  review step. Scoped actions also need an immutable contract across a response.
- The newest complete exchange was deliberately preserved even when it exceeded
  the estimated request allocation. Protecting call/result pairs alone did not
  prevent silent backend truncation of an oversized essential request.
- A first task-state candidate repeated reference excerpts during discovery.
  The final candidate reserves them for planning, relevant active work and review.
- Actual CLI diagnostics exposed admission outside the guarded loop, before
  selecting the constrained execution schemas. An initially oversized request
  raised a traceback; a coding request mentioning tools/commands also admitted
  unrelated product settings policies. Both are host context defects.
- The interrupted v9 TUI model attempted to finish without edits, then replaced
  the CLI with the imported entry-point body after four batched reads. In the
  local JSON adapter, converted assistant actions lost their call-ID binding
  while unpaged result bodies had no filename. The model made the incorrect
  edit; the adapter also made source association unnecessarily ambiguous.

## Changes

Extend `WorkspaceExecution`, the existing loop and Ollama adapter; do not add a
second runner or a general planning service.

1. Retain up to sixteen exact request spans with stable IDs and character
   offsets. A long tail remains one span; the original objective remains
   unchanged in dialogue. These are navigation fragments, not a semantic
   requirements parser. Plans may link actual IDs; unknown IDs are rejected.
   Unlinked references remain visible and final review sees every reference.
2. Ask the optional existing planner for one to four coherent file changes.
   The host appends project checks and final coverage review. The model no
   longer chooses a `kind` for each application requirement. This adds no
   planning call and keeps simple/native/provider paths unchanged.
   The v7 live plan collapsed all work into three files in one change, omitted
   README, and linked every reference anyway. The subsequent v9 contract allows
   one target file per proposed change so it cannot collapse multiple execution
   files into one phase. This still does not verify semantic coverage. The model
   may omit work, and later review retains the whole objective.
3. Project constrained write/edit schemas onto the active implementation files,
   keeping canonical schemas unchanged. Validate both contracts before
   permissions or execution. Failed checks and review allow wider repair scope.
   A typed scope rejection may be retried when its exact arguments become valid
   in a later response; completed edits keep duplicate guards.
4. Apply completion after actual successful actions to the cursor captured
   before that response executes. Require the flag in the one-action local
   response grammar, while tolerating older compatible normalization. Passing
   checks cannot consume the following review through a second cursor advance.
   The history adapter retains the model's completion flag in preceding JSON
   actions, rather than stripping a required field from its protocol examples.
5. Estimate policy/state, schema/protocol and output cost before projecting
   optional complete exchanges and source. If essential dialogue still exceeds
   that allocation, stop before inference with a typed constraint report and
   preserve history. No allocation increase or fabricated provider usage.
6. Select constrained execution before initial compaction, and perform request
   admission inside the guarded model loop afterward. Coding requests mentioning
   tools or commands retain the smaller workspace policy selection. A real CLI
   oversized-read diagnostic now reaches its three intended tool requests and
   exits 1 with a clear constraint report, without a traceback or invented usage.
7. Remove the final-answer choice from local action grammar while the existing
   completion gate would reject it. Passing validation and final review, or an
   actual permission block, retain their existing finalization semantics. This
   avoids asking for an ineligible answer; it does not prove requirement coverage.
8. Attribute each paired local `read_file` result to its requested path/range
   in the constrained adapter's derived dialogue. Retain the original body,
   canonical history and native provider pairing. Include failed reads with the
   same requested-argument label; unknown call IDs are never guessed. No extra
   reads or model calls are introduced.
9. The v13 4B run made a real 9,830-character store write, then stopped before
   request 6: the newest exchange retained its entire historical write payload
   (12,260 dialogue characters against an estimated 10,012 allocation). v14 can
   omit that complete successful built-in edit exchange under pressure in the
   constrained local path. A host-owned changed marker and exact pair establish
   eligibility. The execution record preserves the observed edit; a notice says
   its omitted contents are unavailable and do not prove completion. Reads,
   failures, shell results, no-ops, mixed/partial batches and corrective feedback
   remain protected. Canonical history and completed-write duplicate guards stay
   intact; other providers/native paths retain their latest exchange. This adds
   no model call or larger allocation. Needed current source still requires an
   authorized read; the host does not reconstruct it from a write proposal.
10. The v14 4B run stops after one CLI write and its duplicate, before request 8.
    Retained dialogue is 10,416 characters against a 10,094 estimate because the
    projection adds its omission notice after choosing optional exchanges. v15
    reserves that notice first and removes another optional complete exchange.
    The original goal and newest diagnostic remain intact. The initial hypothesis
    of a retry instruction being a user boundary was disproved by the wire trace;
    controllers remain system messages and their roles/lifetimes are unchanged.
11. The same run leaves `completed_step = false` after the CLI write. A strict
    single-file enum blocks the following planned store file, despite the existing
    cursor's ability to infer movement from actual later file actions. v15 also
    offers the next planned implementation file after actual active-file edits.
    Earlier unedited steps remain blocked, repairs retain existing rules, and
    one immutable scope applies to the response. This avoids making a separate
    completion flag the only path through a coherent multi-file plan.
12. v15 reaches three edited files and failing project checks, but its full read
    of the enlarged test file exceeds the essential allocation by 186 characters
    (9,558 against 9,372) before repair. v16 declares a 100-line default for local
    action-protocol readers with a paging schema. Omitted limits normalize to
    that actual range; explicit ranges and native unpaged behavior are unchanged.
    This provides a bounded reading affordance without automatic reads, another
    planning call or larger allocation. It is a line bound, not a tokenizer or
    maximum-character guarantee. Oversized explicit pages/long lines still stop.
13. v16 3B explicitly selects one-line pages, inspecting only imports in the
    implementation files. The import-only fallback counted visited paths as
    completely inspected, opening planning prematurely. v17 records complete
    coverage separately, decodes numbered source before classification, and
    keeps partial sources in discovery choices. Useful later implementation
    pages still permit work; fully read empty/import-only projects still permit
    creation. Coverage uses the actual result, not a possibly evicted or
    differently keyed alias excerpt. The local paging default now lives in the
    copied schema rather than another protocol sentence. Explicit ranges remain
    unchanged. This host correction is verified through the real CLI control;
    its effect on autonomous benchmark completion is not yet established.

The estimate uses character ratios, not the model's tokenizer. It is an
admission guard, not proof of exact wire token size. It currently stops on an
oversized essential exchange rather than automatically scheduling a smaller
paged recovery. Source caching remains pressure-driven, version-checked and
permission-derived, as evaluated in the previous pass.

## Validation so far

- Controlled tests execute real local edits/checks through the agent: premature
  out-of-scope edit rejected without execution; identical retry succeeds after
  legitimate scope movement; failed check triggers repair; rerun passes; review
  remains the next request. No completed-call guard or permission is relaxed.
- Exact span/tail preservation, unknown link rejection, unlinked test/doc
  references and advisory coverage are tested.
- Context-pressure cases distinguish trimmable accumulated exchanges from an
  oversized essential newest exchange. The latter stops before another runtime
  call, retains the actual exchange and records no extra provider usage.
- v8 focused source/state/adapter tests: 81 passed, 3 skipped.
- v8 full unit suite: 2,423 passed, 19 skipped in 152.13s. The earlier
  intermediate v7 suite was 2,422 passed, 19 skipped in 137.18s.
- Final v9 focused tests with permitted local-network fixtures: 86 passed.
- Final v9 full unit suite: 2,425 passed, 19 skipped in 146.83s.
- Final v13 full unit suite: 2,428 passed, 19 skipped in 126.82s.
- v14 focused source/state/adapter tests: 100 passed in 9.88s.
- v14 full unit suite: 2,439 passed, 19 skipped in 132.19s.
- v15 focused source/state/adapter tests: 102 passed in 9.82s.
- v15 full unit suite: 2,441 passed, 19 skipped in 128.31s.
- v16 focused source/state/adapter tests: 105 passed in 9.92s.
- v16 full unit suite: 2,444 passed, 19 skipped in 119.52s.
- v17 focused source/state/adapter tests: 108 passed, 3 skipped in 17.20s in the
  restricted environment. The initial run exposed an old fixture passing paged
  output with unpaged arguments; the fixture now supplies the executed range.
- v17 full locked unit suite with permitted HTTP/subprocess cases: 2,450 passed,
  19 skipped in 156.69s. Existing cancellation, plan approval, malformed-call,
  path recovery, failed-shell, cache invalidation, dirty-worktree and exit-status
  regressions remain passing. These skips are not claimed as live validation.
- Ruff passes; production mypy passes for 83 source files.

A separate controlled HTTP provider drives the real `klaude ask` path and actual
local file/shell tools. It is a host diagnostic, not a model-capability test or
CSV success. Across twelve responses, an early README write receives
`ToolScopeError` before execution; the identical write succeeds after the active
source step advances. The actual unittest check exits 1, the source is repaired,
the identical command exits 0, and final review remains present before finishing.
CLI exit is 0, the independent rerun passes and final source/docs match the
requested behavior. The unchanged original assertion is retained. The script,
requests, session, stdout and independent check are retained in
`phase1-task-scope/cli-scope-repair`.

The final v13 source repeats this control through the actual CLI: twelve provider
responses, 4.34s, exit 0, independent check passing. Its separate oversized-read
control takes three responses, 2.69s and exits 1 with no traceback; source/docs
remain unchanged and the intentionally failing original assertion is preserved.
These use controlled HTTP replies, not either real local model. Artifacts are
`phase1-task-scope/cli-scope-repair-v13` and `cli-context-limit-v13`.

The v14 real CLI large-edit control keeps the benchmark's 16,384/4,096 setting
and twelve responses, with a 24,008-character actual write. It then recovers from
the out-of-scope edit, reads a bounded current page, performs a failing project
check, repairs the value, reruns successfully and finishes review. Exit 0,
4.89s, independent test passing. The copied canonical edit remains available;
the next derived request omits its large arguments. Its earlier 8K diagnostic
stopped before editing because the policies/state left only 894 characters for
1,393 essential characters. That smaller-allocation failure is retained; it is
not a completed recovery or the unchanged CSV comparison. Intermediate unit
fixtures initially lacked valid discovery and compared escaped dictionary text
with literal newlines; those fixture errors were corrected before the passing
run, with the earlier failures retained. Artifact: `cli-large-edit-repair-v14b`.

The initial `after-v7-3b-cpu` launcher failed before inference. The temporary
recorder treated an unset fault index as matching a non-chat discovery request
and returned an empty body. Its fault condition now requires a chat request and
an explicitly set injection index. This was a harness defect, not a model or
Klaude discovery failure. The corrected autonomous comparison uses no injection.
Intermediate failed test fixtures and failed launch artifacts remain retained.

## Live comparison

| Candidate / model | Requests | Recorded input/output | Actual work | Outcome |
| --- | ---: | --- | --- | --- |
| v7 / 3B, CPU | 11 | 49,732 / 450 | 3 directory listings, 6 distinct reads, no edits/checks | Incomplete, exit 1; 2 original tests preserved |
| v9 / 3B, CPU, TUI | Interrupted | Not retained as a completed run | Observed incorrect CLI replacement before reboot | Completion unknown; temporary run lost |
| v13 / 3B, GPU, one-shot | 11, 9 complete usage records | At least 33,780 / 307 | 3 listings, 6 distinct reads, 3 empty knowledge queries, no edits/checks | Incomplete, exit 1; original 2/2 preserved |
| v13 / 4B, GPU, TUI | 5 | 20,207 / 2,784 | 3 listings, 5 distinct reads, 1 store write, no checks | Incomplete; task failed, original 0/2 |
| v14 / 4B, GPU, one-shot | 7 | 32,196 / 1,111 | 3 listings, 7 read calls including a directory error, 1 CLI write and its rejected duplicate | Incomplete, exit 1; acceptance 0/13, original 2/2 |
| v15 / 3B, GPU, one-shot | 13 | 64,625 / 901 | 3 listings, 6 reads, 1 CLI write, Git diff/status; no checks | Incomplete, exit 1; acceptance 0/13, original 1/2 |
| v15 / 4B, GPU, one-shot | 13 | 74,454 / 4,785 | 3 listings, 10 reads, 2 source edits, test write, 2 checks | Incomplete, exit 1; acceptance 0/13, original 2/2, generated 10/15 |
| v16 / 3B, GPU, one-shot | 11, 10 complete usage records | At least 34,284 / 366 | 3 listings, 6 reads; import-only single-line source pages; no edits/checks | Exit 1 after CUDA unknown error; original 2/2, no importer |
| v16 / 4B, CPU fallback, one-shot | 7, 6 complete usage records | At least 26,268 / 952 | 3 listings, 6 reads, 1 CLI edit; no checks | Host-cancelled, exit 130; original 2/2, acceptance 0/13; not an autonomous outcome |
| v17 / both models, GPU | Not run | Not measured | Final host correction awaiting healthy hardware | Pending |

The v7 run took 2,171.19s. Its final request began just before the thirty-minute
limit and finished afterward; the governor operates at request/tool boundaries.
The model proposed one broad change across CLI, store and tests, linked every
request reference and omitted README. Its next response attempted to finish by
echoing the coverage disclaimer. Klaude rejected this premature answer and
stopped with factual incomplete state. No tool failed and no partial edit was
applied. All requested constraints were retained in every recorded request.
Independent acceptance reports ten rejection cases passing because argparse
rejects an unsupported `import-csv`; all success controls fail. This is no
importer implementation and is not a useful success percentage. Both original
tests pass on the unchanged project.

The final v13 3B one-shot takes 189.74s. Discovery response 5 and optional plan
response 8 end without a completion marker; Ollama logs the same empty grammar
stack failure previously observed. Partial calls never execute. The existing
fresh-action retry repairs discovery; the optional plan falls back to execution.
The model then searches empty libraries named `csv`, `pandas` and `numpy` instead
of editing. Three non-progress results stop the turn with an accurate incomplete
report. No baseline file changes; the ten rejection-only acceptance passes still
do not establish an importer. Both original regressions pass.

The v13 4B TUI comparison completed in `TEST KLAUDE FEATURES`
(session `ba6913ce26d6406eac241074ff30610c`). The unchanged benchmark is submitted
through bracketed paste and Enter. Its initial UI context estimate again uses
the ordinary chat window; the recorded execution request uses 16,384/4,096.
This is an unresolved display estimate, not an increased runtime allocation.
The task took 451.79s (TUI process lifetime including idle time was 704.85s).
Its plan covers storage, CLI, tests and README. The storage write changes 248
lines but incorrectly removes conversion of a string store path to `Path` and
confuses persisted stock keys with transaction identity. Both original tests
fail afterward. The CLI importer is absent, so the ten rejection-only acceptance
passes again provide no importer success. The new context guard reports the
incomplete task honestly, but retention of the completed edit stops further
implementation and repair unnecessarily. This motivates v14's projection change.
The TUI closes normally with process exit 0 after `/exit`; its persisted
`turn_done.failed = true` is the task outcome, not that process exit code.
The v14 one-shot took 324.73s. It made the CLI depend on an unimplemented store
method, repeated its identical write and then hit the omission-notice estimate
defect. No checks ran. The original tests still pass, but no acceptance case does.
The v15 3B comparison takes 229.92s. It changes only CLI and breaks its original
regression, then uses non-repository Git operations and stalls without validation.
No transport truncation occurs. Source retention alone does not establish correct
implementation or appropriate tool selection for this smaller model.

v15 4B takes 990.67s and advances from CLI to store to tests without requiring
completion flags. It repairs `python` not found (exit 127) by running `python3`.
The actual generated suite runs 15 tests with four failures and one error. The
model reads store, CLI and tests to investigate; the latest whole-file read then
hits essential admission and prevents implementation repair. Its code confuses
stock quantity with transaction identity, never persists transaction history,
and the CLI assumes an `error` key absent from successful store results. Its BOM
test writes a literal escape in bytes instead of a BOM. Original 2/2 still pass;
no independent acceptance case does. Context projection also leaves only the
last 800 characters of failed validation in execution state once the full older
diagnostic exchange is omitted; earlier failing cases are absent from request 12.
Retaining better bounded failure diagnostics remains a justified follow-up.

v15's twelve-response large-edit CLI control passes in 3.21s, including an early
scope rejection before any active-file edit, the later identical successful
retry, failed validation, repair and passing rerun. v17's extended thirteen-call
control passes in 6.36s and additionally proves that a first import-only page
keeps mutation out of the following discovery request. The later source page
opens planning; an actual large write, scope recovery, failed check, repair and
passing rerun all follow through the real CLI. An initial control failed because
its assertion depended on tool ordering; that harness failure remains retained.
The v17 oversized explicit-page control stops cleanly after three calls in
3.39s, exits 1, preserves the original files and records no extra runtime usage.
These controlled HTTP replies establish host behavior, not model intelligence.

During the final v16 3B request, Ollama reports `CUDA error: unknown error`.
At 22:50:36 local time, read-only diagnostics report `GPU requires reset`,
utilization unavailable and 1 MiB used. Ollama's 4B process has zero VRAM and
16,384 context. The directory named `after-v16-4b-gpu` was queued before this
fault, but its actual execution is CPU; its name is not runtime evidence.
No global service, configuration or driver changes were made. Do not compare
its wall time to healthy GPU attempts or classify the transport failure as a
model capability result. The user has been offered reboot or continued CPU
evaluation. The outdated CPU attempt was subsequently cancelled with SIGINT to
its verified owned CLI child, preserving session data and completed edits. It
exits 130 after 1,769.12s; its seventh request has no completion response, so that
request's token usage is unknown. A CLI edit had executed before cancellation;
the store importer is still absent. Original 2/2 pass and acceptance 0/13, but
these are partial-state checks, not an autonomous benchmark outcome. The global
Ollama service and unrelated clients are unchanged. No model comparison remains
running; final-candidate comparisons are pending healthy hardware.

## Efficiency and remaining work

4B progresses from one source write without checks in v13/v14 to CLI, storage,
tests and two actual validation commands in v15. That progress costs 13 requests,
74,454 input / 4,785 output tokens and 990.67s, versus five requests and 451.79s
for the incomplete v13 task. It is greater autonomous reach, not a latency or
completion improvement. v15 request input peaks at 7,434 recorded tokens under
the unchanged 16,384/4,096 runtime allocation; estimated admission still stops
on an oversized last read. Three application/test rereads follow the failed
check; two requests reuse current source excerpts. Source retention is useful
but does not eliminate repair reads or establish semantic correctness.

3B goes from no edits in v13 to one incorrect CLI write in v15, with input usage
rising from at least 33,780 to 64,625. It then wastes Git calls outside a Git
repository and never validates. Six reads remain in each run. Neither model
completes the thirteen-case benchmark. Rejection-only passes when the command
is absent are explicitly excluded as evidence of implementation success.

Observed model limitations include weak cross-file result contracts, confusion
between transaction history and stock state, incomplete plans and incorrectly
constructed tests. Host limitations still contribute: validation state retains
only the diagnostic tail once the original failed-check exchange leaves working
context, task activation still uses a length heuristic, and tool choice can
divert to irrelevant empty libraries or Git tools. The context estimate is
conservative and can stop instead of scheduling a smaller recovery read; the
TUI's initial context estimate uses the ordinary chat allocation. These are
documented gaps, not evidence that remaining failure is purely model capacity.

Next, finish the unchanged two-model v17 comparison after healthy CUDA is
available, retaining the same models and allocations. If failures still show
irrelevant tool choices, Phase 2's narrower active tool inventory is justified.
Phase 3 should preserve bounded useful validation diagnostics and reserve a
repair opportunity. Neither later phase is implemented here. Do not add more
system prose or automatic CSV-specific behavior to compensate for these gaps.

Artifacts are restored under `/tmp/klaude-agent-phase1`; completed runs, frozen
sources and controlled diagnostics are copied into ignored
`playground/agent-source-context-20261005`. Active SQLite evidence uses a consistent
backup and an explicit incomplete-snapshot marker; the cancelled CPU run's final
shutdown data is archived separately as a host-cancelled outcome. Standalone
resume instructions are in that archive's `PHASE1-RESUME.md`. Do not relabel earlier
source-context runs or interrupted attempts as final task-state results.
