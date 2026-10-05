# Agent source-context evaluation

Phase 0 and the first Phase 1 change from
[the orchestration plan](agent-orchestration-plan.md), started 2026-10-05.
This continues [the small-model evaluation](small-model-evaluation.md).
The objective remains full autonomous completion of the unchanged benchmark;
passing architecture tests is not that outcome.

The subsequent request references, active file scopes, whole-request admission
and completed-edit projection experiments are documented separately in
[task-state evaluation](agent-task-state-evaluation.md). The results below remain
specific to their original frozen versions.

## Comparison setup

The exact [Stockroom fixture](benchmarks/README.md), both original tests, and all
13 independent acceptance cases remain unchanged. Models are `qwen2.5-coder:3b`
and `qwen3.5:4b`, thinking off, code context/output 16,384/4,096, general
8,192/2,048. Projects and isolated config/data are outside Git. Acceptance
feedback is not supplied during the initial autonomous attempts.

Baselines use a captured copy of the live, dirty agent sources, verified through
Python import paths. Candidate runs use frozen production-source copies through the real CLI.
The v5 candidate adds the two focused state fixes and bounded EOF recovery
described below; the full 4B comparison used the preceding pressure-gated v3 copy.
The final v6 candidate also expires temporary controller instructions between
turns. Its live regression is the interactive recovery/follow-up scenario; neither
full CSV comparison is relabeled as a v6 run.
Both use the same locked environment and a pass-through Ollama recorder.
Requests, responses, original/generated test logs, acceptance results and metrics
are retained under `/tmp/klaude-agent-phase1`. Prompt SHA-256 is
`c1c41dfa913d8c1355e6ab8aa34648f5c80ff63fc2245e25f0b5fd379f5b5f7d`;
acceptance SHA-256 is
`30d08650be70448be0adff78ce5b3278c4b47aeb5def8d5f2b32acf94ec93eba`.

## Observations and implementation

1. Older source bodies were discarded together with complete tool exchanges.
   Observed execution state retained file names, but not current source. The
   model had to reread files or rely on stale conversational code/anchors.
2. Paged reads include display line numbers. These are useful for navigation,
   but source retained for literal edit anchors should omit those prefixes.
3. Previously passing checks could remain current after an unclassified shell
   command. Such commands can modify files even when their exit status fails.

`WorkingSources` now retains only excerpts delivered by successful, authorized
built-in reads whose filesystem identity is unchanged across the operation.
Each excerpt carries its actual path, execution ID, version, line coverage and
truncation. Identity is rechecked before request reuse. Secret, removed, changed,
or escaped paths are dropped. External changes stale previous checks and release
read guards. No file content is recovered from audit metadata.

The final candidate keeps normal tool exchanges while they fit. Source snapshots
are admitted only when context pressure would otherwise remove source. Eager
replacement was tested and rejected: both models reread cached files instead of
implementing. This is not presented as an efficiency improvement.

The store is turn-local: eight excerpts / 32,000 characters maximum; request
admission is at most 8,000 characters within the remaining estimated input
budget. Diagnostic targets and active-step files have priority; retained reads
are not duplicated.
Literal source appears in an escaped, explicitly untrusted context block, not a
new tool response. Budget projection still omits only complete exchanges;
canonical history and complete provider pairs remain intact. A fully admitted
current excerpt retains its duplicate guard. No planner/model call or context
allocation is added.

The first 3B candidate also exposed a separate discovery bug: a package
docstring alone satisfied implementation inspection, triggering a premature
plan about repeatedly inspecting that file. Python docstring/import-only modules
and simple imported entry forwarders now keep discovery open while other source
candidates remain unread. A fully inspected import-only project can still grow
new code. This guard is not a semantic correctness verdict.

Successful edits invalidate their target excerpts. No-ops preserve them; typed
anchor conflicts retain version-checked current source for repair. All shell
operations invalidate excerpts, including failed commands. Unclassified shell
commands stale previous checks without inventing evidence that an edit occurred.

## Live benchmark results

| Run | Time | Requests | Recorded input/output tokens | Executed tools | Acceptance | Original tests |
| --- | ---: | ---: | --- | --- | --- | --- |
| Baseline 3B | 224.54s | 16 | ≥63,815 / ≥985 | 3 lists, 9 reads, 1 edit | 0/13 | 1/2 |
| Baseline 4B | 1849.39s | 14 | 75,374 / 13,129 | 3 lists, 10 reads, 3 edit calls | 2/13 | 2/2 |
| Eager snapshots 3B, rejected | 113.38s | 10 | 37,896 / 439 | 3 lists, 3 reads | 10/13, rejection cases only | 2/2 |
| Eager snapshots 4B, rejected | 375.11s | 10 | 47,884 / 604 | 3 lists, 8 reads | 10/13, rejection cases only | 2/2 |
| Discovery fix with eager snapshots 3B, rejected | 235.79s | 18 | 82,644 / 966 | 3 lists, 7 reads, 1 edit, 3 workspace/Git calls | 10/13, rejection cases only | 1/2 |
| Pressure-gated snapshots 3B, pre-reboot | Interrupted after GPU failure | 8 started | Partial counters only | Inspection only | Not evaluated as a complete run | Pending |
| Pressure-gated snapshots 4B, pre-reboot | Cancelled for GPU recovery reboot | 3 started | Partial counters only | Initial inspection | Not evaluated as a complete run | Pending |
| Pressure-gated 3B, post-reboot | 77.36s | 6 | ≥15,134 / ≥106 | 3 lists, 2 reads | 10/13, rejection cases only | 2/2 |
| Pressure-gated 4B, post-reboot | 1838.70s | 15 | 81,222 / 12,772 | 3 lists, 6 reads, 10 writes | 2/13 | 0/2 |
| v5 3B, GPU then CPU fallback | 449.78s | 11 | ≥38,059 / ≥468 | 3 lists, 6 reads | 10/13, rejection cases only | 2/2 |

The baseline 3B stream ended without a completion marker on request 16, so its
last request's token counters are unknown. The sums above cover 15 complete
records and are lower bounds. Klaude discarded the partial call and returned
exit 1. The model added the `import-csv` parser twice, broke the original CLI
regression, implemented no importer and ran no validation. No acceptance case
passed. Recorded tool executions are audit counts, not replayable result evidence.

The baseline 4B completed initial inspection and a public plan, edited the store
and CLI, then spent 487.88s generating an incomplete 4,096-token test edit.
That edit was discarded. It reread the store/tests and attempted another large
edit. It ultimately exhausted its action output allowance again and returned
exit 1, without new tests, README changes or any validation. Three edit calls
included one no-op; two files actually changed. This is an output-sizing obstacle
separate from source retention.

The eager candidates both made no edits and stopped after repeated reads, with
exit 1. Their smaller token totals and shorter times measure less work, not
better coding. The apparent 10/13 score consists of argparse rejecting an
unsupported command with exit 2; all success controls fail. Fixing discovery
alone let 3B reach real source and one edit, but it still broke the original CLI
test and stalled without validation. Consequently eager replacement is absent
from the final implementation.

## Validation and boundaries

- Controlled real-workspace diagnostics cover paged literal source, context
  pressure, anchor repair, external edits, symlink escape, secret paths, failed
  mutations, no-op/denied writes, check invalidation, bounded storage and
  canonical/provider-pair preservation.
- Original pressure-gated validation: 69 focused tests; full suite 2,408 passed,
  19 skipped.
- v5 recovery/state-focused validation: 101 passed, 3 skipped; full suite
  2,414 passed, 19 skipped in 154.74s.
- Final v6 source/state/adapter-focused validation: 75 passed, 3 skipped,
  including success, repeated failure and generator cancellation after recovery.
- Final full suite: 2,417 passed, 19 skipped in 134.73s.
- Ruff passed. Production mypy passed for 83 source files.

One v6 diagnostic launch failed before chat because its temporary frozen copy
omitted the vendored spinner JSON. The artifact copy was corrected before the
successful live runs; the failed launch is retained. Production package files
were not missing or changed by that harness correction.

This is the source-context slice of Phase 1, not completion of the entire phase.
The newest indivisible exchange can still exceed the estimated budget. Whole
request admission, requirement coverage, smaller execution scopes, and explicit
repair reserves still need evaluation. Mutated source is conservatively dropped
and must be read again; automatic patch reconstruction is deliberately absent.
State is not durable across turns/resume. Tool discovery, Skills/MCP selection
and delegation changes remain in later phases.

Neither model completed the benchmark. Fewer reads in the 4B run did not
translate into successful implementation or better total efficiency. Latencies include model loading,
partial GPU offload and concurrent local validation; they are approximate
observations, not controlled throughput measurements.

## Resume after GPU recovery reboot

The user requested a reboot opportunity on 2026-10-05 after an observed CUDA
launch failure. `nvidia-smi` reported the GTX 1650 with 1 MiB used and unavailable
utilization; Ollama's live allocations reported zero VRAM. The initial
pressure-gated 3B process was interrupted without a final result. Its restarted
4B comparison was cancelled before completion for the reboot. Neither run is
counted as benchmark completion or a usable GPU latency comparison. The
evaluation launcher and its owned CLI/proxy processes were asked to stop;
no unrelated application or service was restarted.

Implementation is saved in the checkout, uncommitted. All 15 unrelated modified
tracked files match their initial hashes; AGENTS.md retains its original edits
plus this pass's guidance. The lockfile is unchanged. At the pre-reboot stopping
point, production matched the frozen v3 sources. The final source now matches
`/tmp/klaude-agent-phase1/candidate-v6-source`; no production edits followed its
full test gate.

## Post-reboot results and additional fixes

The host GPU initially recovered: the GTX 1650 was visible with working
utilization readings. The 4B runtime used the expected 16,384 context and about
2.18 GB of VRAM. Exact installed model digests were verified:

- `qwen2.5-coder:3b`: `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`
- `qwen3.5:4b`: `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`

### 4B: less rereading, more unchecked rework

Source snapshots appeared in requests 7–15. The original goal remained present
in every request. All fifteen responses completed normally; none hit the output
ceiling. The model read each of six files once, compared with ten baseline reads
and five repeated file reads. It then wrote the store four times, CLI four times,
and tests twice. After the initial edits, the active plan remained **Update README**
while the model continued rewriting the other files. No README edit or shell
validation occurred before the ordinary 30-minute governor stopped work.

The generated twelve-test suite had five failures and three errors. Both original
regressions failed. Independent acceptance passed only the new-store dry-run
no-directory and missing-input error cases; neither successful import nor replay
worked. Code review found lost legacy stock, changed `add` output/return behavior,
a removed `main(argv)` interface, text instead of JSON summaries, inadequate
field/conflict checks, and saves during partial processing. These are substantive
implementation errors, not missing tool permissions or unavailable source.

Compared with baseline 4B, recorded input rose 7.8% and output fell 2.7%; elapsed
time remained approximately thirty minutes. Completing more full-file bodies and
avoiding rereads did not improve correctness. Zero rereads also meant the agent
never checked its new source against its tests. This is one observed trajectory,
not a causal or throughput claim. Modified source is invalidated conservatively,
so retaining current post-edit code remains a separate design question.

The final report correctly stated the unfinished README/check/review steps and
validation **not run**, preserved edits, and returned exit 1. It did not claim success.

### 3B: runtime interruption and weak decomposition are separate

The first post-reboot run ended after five successful discovery operations. Its
sixth response stopped mid-JSON without a completion marker. Ollama's service log
reported `Unexpected empty grammar stack after accepting piece: ? (30)`; the
partial call was discarded. The unchanged project's apparent 10/13 score is
argparse rejecting an unsupported command, not importer correctness.

The identical six captured requests were replayed without executing their proposed
actions. All completed on GPU, including the previously failing sixth response.
The exact sixth request also completed on CPU in 201.69s. This establishes that
this recorded failure was recoverable; it does not establish its underlying GPU
or sampler cause. Similar upstream grammar failures are reported in
[Ollama's issue tracker](https://github.com/ollama/ollama/issues/18369), but this
text-only case was not proven to share that report's cause.

A typed `OllamaIncompleteResponse` now identifies assembled responses that ended
without completion and returned no calls. The agent may request one fresh small
action when tools remain callable, no public text was streamed, and cancellation
is not requested. The retry consumes the existing transport-recovery allowance
and normal step/token/time budget; it neither replays completed calls nor raises
limits. A repeated failure remains an error. Healthy answers add no request.

Two source-state fixes were also completed:

- Next-action guidance remains inspection until implementation/test discovery is
  actually ready, matching the available discovery tools.
- Read guards remember canonical source paths, allowing fresh reads through an
  alias after an external source change.

The final 3B one-shot run used these fixes and the unchanged benchmark. It reached
full initial inspection and planning, then repeated reads instead of editing.
The public plan treated feature requirements as five validation phases and
omitted new tests, documentation and final review. Another CUDA runner failure
triggered the existing CPU fallback; host `nvidia-smi` then again reported 1 MiB
and unavailable utilization. On CPU the model repeated another read and the
no-progress governor stopped it. There were no edits or project checks, exit 1,
and the same misleading rejection-only score. The failed CUDA request's counters
are unknown; recorded sums in the table are lower bounds. No service, driver,
model, or user's configuration was changed to force a benchmark pass.

## Interactive follow-up

The real TUI was opened and named **TEST KLAUDE FEATURES**. Rename and deterministic
keyboard help worked without inference. Interactive diagnostics use an explicit
CPU choice in isolated configuration because the GPU fault recurred. They inject
one missing completion marker into a real Ollama response as a separate transport
recovery scenario; this injection was absent from every CSV benchmark attempt.

The v5 prompt requests only `read_file` for `stockroom/cli.py` and
`stockroom/store.py`, an explanation of add/list output, and no edits. The bounded
EOF retry preserved that request. A subsequent text-form tool response needed
the existing constrained-action fallback; both actual reads then executed once,
with no writes or shell operations. The answer omitted the exact add output and
incorrectly implied that listing creates a missing store file.

A natural follow-up asked what `add A 4` prints and whether `list` creates a
missing file. The request contained both original tool bodies, but the model
again omitted the output and repeated the missing-file claim. The correct
answers are `4` and no: `load()` returns an empty dictionary without saving it.
That response completed in about 188s on CPU; completion is not answer accuracy.

Request inspection found a host defect: the previous turn's temporary EOF and
constrained-format instructions remained as system messages in the follow-up,
although its native tool protocol was active again. Controller messages now have
an internal turn-local identity with ordinary role/content wire fields. The
agent drops them on completion, failure or generator cancellation, preserving
actual dialogue and complete tool exchanges. This adds no prompt or model call.
It removes demonstrably obsolete guidance; it does not establish the cause of
the incorrect factual answer.

The final v6 run repeated the same two-file prompt and injected failure. It again
needed four requests and executed exactly two reads. Its first answer completed
in about 446s on CPU and still incorrectly placed the default store beside the
script rather than relative to the current working directory. The captured
follow-up uses native tools without a constrained response format, retains both
actual read bodies, and contains neither obsolete recovery instruction. This
confirms instruction expiry through the real CLI path. It is not evidence that
the model's factual reasoning improved.

The follow-up completed in about 221s on CPU. It correctly described `add()`
returning `4` and `list` printing `{}` after `load()` returns an empty dictionary,
with no save in the listing path. It remained verbose and did not directly give
the two requested answers, `4` and no. This is more accurate than the v5 follow-up,
but the changed prior answer and generation trajectory prevent attributing that
improvement solely to instruction expiry. The original default-directory error
was not corrected. Both interactive workspaces retained every original fixture
file, and their owned processes exited cleanly.

Direct cancellation bypassed the recorder because its blocking upstream read
cannot reliably propagate an early client disconnect. The real v6 TUI resumed
saved session `319ed81bafa54fe0af72fa9ab8eefa51`, submitted a read-only code review,
and received Ctrl+C while awaiting its first response. It returned to Ready
within about three seconds, saved `cancelled: true`, executed no new tools, and
left every fixture file unchanged. No automatic recovery followed cancellation.
The owned interactive process exited cleanly. This tests client responsiveness,
not GPU recovery or CPU throughput.

## Remaining work and recommendation

Neither small model completes the full unchanged benchmark. This source-context
slice establishes bounded, versioned evidence and controlled anchor recovery;
it does not establish better autonomous implementation. The rejected eager
replacement experiment remains absent.

Observed Klaude limitations justify finishing Phase 1 before later phases:

1. Admit the whole request within budget, including the newest indivisible
   exchange; retain user constraints and unresolved requirements explicitly.
2. Check whether a proposed plan covers tests/documentation/review where requested,
   and distinguish project validation from application validation rules.
3. Give the active execution scope a clearer role. `set_plan()` accepts the model's
   proposed steps without linking them to requested outcomes. `complete_step()`
   checks touched files or passing project checks; it cannot establish semantic
   coverage. `align_executed_action()` moves toward later scoped files, but the
   advisory plan does not constrain backwards rewrites. These mechanisms did not
   prevent repeated writes to already-touched files while the active task was docs.
4. Determine how to keep verified current post-edit source without reconstructing
   unknown patches or relaxing read/permission boundaries.

The subsequent tool-selection and validation/repair phases are still justified
by the observed choice overload and unchecked rewrites. Do not treat a touched
file or a passing narrow check as requirement coverage. Preserve simple-request
latency and overall budgets; do not compensate with a larger system prompt,
context allocation, a hidden model switch, or CSV-specific logic.

Runtime instability also limits this machine's evaluations. CPU fallback keeps
requests possible but increases latency substantially. The model's semantic and
planning errors remain visible independently in the healthy 4B run and in 3B's
public plan; hardware failures must not be counted as model incapability.
These are observed model weaknesses, not proof of an intrinsic inability to
complete this project. The remaining host scope/coverage and validation defects
must be tested before declaring a hard model capability ceiling.

Artifacts are retained in `/tmp/klaude-agent-phase1` and the ignored durable backup
`playground/agent-source-context-20261005/`. Frozen sources, exact fixture,
requests/responses, service diagnostics, independent acceptance and original-test
results, and validation logs are retained. Later tool discovery, Skills/MCP
coordination, durable state and worker phases have not started. Work remains
uncommitted; unrelated changes and the lockfile are preserved.
