# Compound-agent follow-up: capability discovery and broader validation

Date: 2026-10-16. Starting checkpoint remains
`90137f46f59f15346f16401c2ecd5b6aecc8a7f7`; the existing dirty M0/M1 work and
[read-recovery follow-up](agent-read-recovery-validation.md) are preserved.
No implementation commit or push is authorized in this pass.

## Outcome and scope

This engineering and evaluation pass is finished. Bounded capability discovery,
native routing recovery, typed MCP failure accounting and honest no-progress
failure status are implemented and verified. The 4B controlled Skill/MCP task
and Gemma compound image-credit lookup complete successfully. **Neither original
small model completes the unchanged CSV benchmark.** Gemma also fails the strict
punctuation control, despite making no unnecessary tool calls. Repeated GPU
failure limits coding/latency comparisons; the exact outcomes are retained below.

The delivery gates come from [the researched plan](agent-multi-action-research.md).

- M2: implemented and verified bounded discovery across enabled built-ins, installed
  Skills and connected MCPs, without broadening authority or mandatory planning.
- M3: exercised file-directed work, Skills/MCP workflows, follow-ups, cancellation,
  resume and the unchanged Stockroom CSV benchmark with both original local models.
  The broader completion/coverage gate remains partial; tests passing does not
  replace the failed CSV outcome or untested provider/workflow combinations.
- M4: assessed existing bounded read parallelism and deferred an additional
  executor/concurrency layer because no useful measured gain justifies it.
- Rechecked Gemma's image-credit → pronoun lookup through the actual TUI, with
  source deletion, a no-tools control and explicit grading limitations.
- Final full tests, lint/types and packaging passed on frozen production sources;
  all 154 production Python/prompt hashes still match after the live evaluations.

## Current implementation

- New normal permission-controlled `discover_tools(query)` tool, default allow,
  listed under Tools/Orchestration and permission presets.
- Metadata-only lookup, four results/call, four calls/turn, twelve newly loaded
  schemas and a context-derived byte bound. Canonical schemas are not truncated.
  Exact-name matches return only that match. Loaded schema definitions are pinned
  and checked again before execution, including in-place schema changes.
- Matching schemas become callable only on the next response. Current response
  scope, live permissions, disabled tools, dirty workspace and retirement/budget
  gates remain authoritative. Definitions changed since capture are rejected.
- An omitted write/shell/commit/persistence/delegation route cannot be restored
  by discovery. Explicit tool-only, no-tools, no-search and no-Skill bounds remain.
- Installed Skill matches identify exact package names and load `read_skill`;
  instructions are read only by that separate tool, whose package checks remain.
- Turn-local callback and loaded selections are cleared on completion/cancellation;
  discovery receipts are not durable grants.
- Model-facing large-registry summaries show bounded subsets; full immutable
  snapshots remain available to status/audit consumers.
- Existing native Ollama recovery binds exact arguments when non-coding discovery
  is available. Workspace discovery remains on its earlier default protocol.
- A syntactically valid native call to an enabled but deferred tool gets one
  discovery-routing correction, without switching to the constrained protocol.
  Its entire original batch is rejected atomically. Unknown/malformed calls keep
  existing protocol recovery, and repeated routing failures remain bounded.
- Non-coding file/MCP investigations reuse the compact retrieval projection:
  omit unrelated standalone generation/configuration policies while retaining
  repository/Skill guidance, runtime context, tool authority and source trust.
- MCP application errors preserve the raw response envelope and now also carry
  typed `is_error`/failed-status metadata through the actual CLI adapter. The
  governor no longer counts an error as progress. Corrected inputs remain
  possible within the existing budgets, live permissions and duplicate guards;
  there is no automatic remote retry or assumption of rollback. Scoped feedback
  distinguishes correcting task identifiers from rediscovering an unchanged
  schema.

References: core `tool_discovery.py`, `agent.py`, `capabilities.py`, `config.py`,
`tool_settings.py`; CLI `_build_agent`; offline `test_tool_discovery.py` and
`test_capabilities.py`.

### Implementation map

| Boundary | Current implementation |
| --- | --- |
| Metadata matching and fixed limits | [tool_discovery.py](../packages/core/src/klaude_core/tool_discovery.py), `matches`, lines 8–52 |
| Turn-local loading, definition pinning, live gates | [agent.py](../packages/core/src/klaude_core/agent.py), `discover_tools`/`discover`, lines 4292 and 4894 |
| Request projection and native routing correction | Same agent, `text_model_messages`, lines 5116 and 6514 |
| MCP adapter and ordinary tool registration | [main.py](../apps/cli/src/klaude_cli/main.py), `_configured_mcp_tools`/`_build_agent`, lines 7102 and 7182 |
| MCP error recovery | Same agent, `recoverable_remote`, lines 7065 and 7135 |
| Progress accounting | [execution.py](../packages/core/src/klaude_core/execution.py), `TurnGovernor.observe_tool_result`, line 121 |
| Bounded model summary, complete audit snapshot | [capabilities.py](../packages/core/src/klaude_core/capabilities.py), `TurnCapabilities`, line 48 |
| UI activity | CLI `_tool_activity`, line 5101; [tool_settings.py](../packages/core/src/klaude_core/tool_settings.py), Orchestration group |
| Durable offline contracts | [test_tool_discovery.py](../tests/unit/test_tool_discovery.py), [test_capability_routing.py](../tests/unit/test_capability_routing.py), [test_capabilities.py](../tests/unit/test_capabilities.py), [test_execution.py](../tests/unit/test_execution.py), [test_mcp_client.py](../tests/unit/test_mcp_client.py) |

Line references describe this uncommitted worktree, not the base commit.

## Validation chronology

- New discovery/capability contracts: 19 passed in 0.76s. Production types passed
  at that point; later final checks cover the combined implementation.
- Broader focused regression rerun: 1020 passed, one existing skip in 100.04s.
  New cancellation, discovery-permission and call-limit contracts then passed
  with the capability tests: 22 passed in 1.84s.
- The first broader focused run stalled in the known OAuth cancellation area
  under restricted socket permissions. Its interrupt was swallowed by the test;
  only its identified process tree was terminated. This is incomplete validation,
  not a passing run. The corrected run has socket permissions and a 90-second
  faulthandler diagnostic bound; log `/tmp/klaude-discovery-focused.log`.
- First real-model harness setup failed before inference because its fixture
  omitted `MCPServerConfig.transport`. This was a harness error, fixed there.
  Its receipts are retained in `.klaude/data/capability-discovery-a7wywyr1/`.
- A direct actual MCP stdio preflight returned the synthetic blocked deployment.
  The fixture was updated to advertise its tool through `tools/list` as well.
- Initial real CLI comparison root:
  `.klaude/data/capability-discovery-0gz1dkew/`. Completed and interrupted
  outcomes are separated below.
- The real discovery-disabled 3B baseline took 407.37s, executed `read_file`,
  then repeated the brief instead of consulting the Skill/MCP or answering the
  deployment question. Exit 0 did not establish task completion. Session:
  `8b8723b812854bddbd0fddb56307c0f9`.
- The first enabled 3B trial exposed mixed read/search arguments in the shared
  recovery schema, then an unnecessary broad discovery for `read_file`, followed
  by a duplicate invalid read. It was interrupted explicitly after this failure,
  exit 130, 925.16s; it is not a completed benchmark. Exact arguments and exact-name
  metadata matching were corrected before the subsequent 4B and repeated 3B runs.
- The actual PTY TUI walkthrough passed with a **deterministic provider fixture**:
  read brief, discover a deferred tool, invoke it, answer, then a direct follow-up
  with no retained loaded schema. This is UI/session integration, not real-model
  reasoning evidence. Session `b298cc1efb884fab96b2bfd376194091`, titled
  `TEST KLAUDE FEATURES DISCOVERY`; normal exit 0. Captures at 80/120 columns show
  concise discovery activity without raw schema dumps. Evidence:
  `.klaude/data/discovery-tui-fixture-wdux6ex5/`.
- Final binding/definition-identity focused checks: 105 passed, three existing
  skips in 4.81s. The later full gate supplies required local socket access;
  these focused counts alone do not establish complete validation.
- Projection checks: 69 passed in 2.38s. Routing checks: 108 passed, three existing
  skips in 4.80s. The actual TUI fixture also passed the deferred-native-call
  rejection → discovery → invocation path without a protocol switch:
  `.klaude/data/discovery-tui-routing-fixture-uq75s14e/`.
- The 4B candidate exposed a distinct host cause of wasted work: a valid native
  call to the deferred Skill reader caused protocol recovery, even though the
  native parser and calling format were working. The bounded routing correction
  above addresses this rather than adding more planner prose.
- That 4B candidate completed the full requested outcome, session
  `0ee4843f118c42189cc655e4a2ed86c7`: blocked release, exact revision and blocker,
  explicitly interpreted with the read Skill. It took 1863.81s, five model
  requests and five tools (two file reads, discovery, Skill, actual MCP invocation).
  Reported input/output: 28,297/264, no unknown requests; per-request input
  `4338 → 4410 → 4749 → 7275 → 7525`. This is a completed early candidate,
  before the compact-file/MCP projection and distinct routing recovery.
  The 1800s governor is checked at safe boundaries, not a per-request hard
  deadline; its final request completed beyond that threshold. This limitation
  is retained explicitly, rather than describing 1800s as a hard wall limit.
- The original harness's outcome flag incorrectly compared the actual hashed
  MCP name to an unhashed string. Its raw receipt is preserved; separate
  `assessment-corrected.json` verifies the observed canonical namespace and
  actual saved answer. This is a grading fix, not changed input or a model/tool
  rewrite. New harness sources use the canonical-name prefix check.
- The compact 3B candidate read the brief and the real Skill, then supplied the
  tool-name hash `953eae7a` as the release ID instead of `R472`. The real MCP
  returned `is_error: true`, `Unknown release`. The CLI adapter had serialized
  this into content without typed failure metadata; the governor counted it as
  progress. The model then rediscovered the schema, tried unrelated Git status
  and invented HTTP endpoints. This old-code run was explicitly interrupted
  after capturing the failure (exit 130, 1136.32s, ten model steps, nine attempted
  tools, 42,421/393 reported input/output). It is not a completed benchmark.
  Evidence: `.klaude/data/capability-discovery-final-a_gvbawe/`, including the
  interruption reason. Incorrect identifiers are model behavior; losing the
  error signal was a host defect and is now corrected above. The focused MCP,
  routing, governor and discovery regression set passed: **81 tests in 5.91s**.
- The actual TUI plus real stdio MCP client also passed an application-error
  recovery control. Scripted provider responses intentionally sent a wrong ID,
  asserted the returned correction, then used `R472` and produced the correct
  blocked result. A subsequent exact `OK` reply inherited no discovered schema;
  normal shutdown exited 0. This verifies integration, not model reasoning.
  Evidence: `.klaude/data/discovery-tui-mcp-error-fixture-c3bozt4c/`.
- A separate actual TUI process restart and `/resume SESSION_ID` control passed:
  history is restored and the subsequent exact `OK` turn receives no inherited
  discovered schema. Session `27b84997384c4781a8d67ab5724d1188`; provider replies
  are scripted, not real-model evidence. Root:
  `.klaude/data/discovery-tui-resume-fixture-i_1lloc4/`. An earlier fixture failed
  because it expected the session title to be visible; its trace already showed
  correct restored history. That assertion was corrected to inspect the selected
  session/history; the failed fixture remains in `discovery-tui-resume-fixture-8w2fkcxx/`.

## Exact controlled workflow

Prompt: `Read brief.md and answer its question using connected services. Do not edit files.`

The actual project note asks whether deployment R472 is safe to release and
requests the installed `release-checklist` Skill and connected rollout service.
The real installed package explains how to interpret deployment readiness.
A real local stdio MCP server returns state `blocked`, revision `f47c9`, blocker
`schema migration review pending`. It performs no real deployment/network action.
The initial user request does not name the deferred Skill or MCP tool.

The actual CLI/model/agent/permission/Skill reader/MCP client/session paths run;
the external service is a local controlled fixture. Compare discovery disabled
and enabled for `qwen2.5-coder:3b`, then enabled for `qwen3.5:4b`, each in separate
non-Git temporary workspaces and private config/data. Context/output remain
8192/768, thinking off. An advisory owned-evaluation lock prevents concurrent
model runs. The 1900-second external deadline does not change application budgets.
A pass requires the observed read, Skill read, MCP invocation and correct actual
saved answer, not simply exit 0.

Other ordinary tools are not globally mocked in this workflow. The interrupted
3B candidate's invented HTTP probes really executed (one DNS failure and one
public HTTP 200). Neither established a release result. No actual deployment,
cloud model generation or user-image upload was performed. Final 3B/4B workflow
runs execute no such HTTP probes.

The local runtime is **Ollama 0.33.3**. Both original text models retain Q4_K_M
weights and exact identities:

- `qwen2.5-coder:3b`: `f72c60cabf6237b07f6e632b2c48d533cef25eda2efbd34bed21c5e9c01e6225`.
- `qwen3.5:4b`: `2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd`.

Read-only placement checks show zero model VRAM; `nvidia-smi` reports GTX 1650,
unavailable utilization and 1 MiB used. No driver reset, global service restart,
model substitution or allocation increase is performed. The private evidence
root retains model identities and placement. These CPU runs do not certify
healthy-GPU latency or support causal timing comparisons with the older GPU
CSV trajectories.

## Final Skill/MCP workflow results

The final 4B run completes the requested outcome, session
`4386160c35cc4073b529d418bed531db`, exit 0, 1514.23s. Its actual saved answer is:

```text
No, deployment R472 is not safe to release.

Observed rollout state: blocked
Revision: f47c9
Blocker: schema migration review pending
```

It executes one file read, discovery, workspace metadata, the real installed
Skill read, a second discovery and the actual stdio MCP call with `R472`.
No write or external HTTP probe executes. Seven model requests use
**28,755 input / 307 output tokens**, all usage known; per-request input is
`3387 → 3459 → 3516 → 3855 → 4474 → 4968 → 5096`. Two attempted native batches
refer to deferred tools and execute nothing. The first receives the distinct
routing correction; the repeated attempt enters bounded constrained recovery.
The model then discovers the exact Skill and rollout service and completes.
Evidence: `.klaude/data/capability-discovery-final-4b-lzn4zjsn/`, including the
final implementation fingerprints.

Relative to the completed early 4B candidate, peak input falls **32.3%**
(7525 → 5096) and observed wall time falls **18.8%** (1863.81s → 1514.23s).
However model requests rise **5 → 7**, executed tools **5 → 6**, total input rises
**1.6%** (28,297 → 28,755), and output rises 264 → 307. A redundant second
file read is avoided, but unnecessary workspace metadata and extra routing
remain. This supports reduced request pressure and a completed workflow; it
does not establish universally lower latency or token use. These are single,
stochastic CPU trajectories, partly overlapping local automated checks, not
controlled p50/p95 measurements.

### Final 3B outcome: still incomplete

Session `4115ddc4db0b4a7aa2029a4d23b95e6c`, 875.82s, exit **0**, requested
outcome **failed**. It discovers both the correct Skill and MCP definitions,
but again copies `953eae7a` from the tool name into `release_id`. The application
error now carries typed failed metadata and correction feedback. It then
attempts an exact duplicate brief read and selects nonexistent Skill `README.md`
instead of the default `SKILL.md`. Three non-progress responses stop tools;
the reserved finalization says only:

```text
There is no `README.md` file in the specified path. Please check the file path and try again.
```

There are seven observed model requests (six governed rounds plus reserved
finalization), seven charged tool attempts, five actual invocations including
failed MCP/Skill calls, **29,755 input / 328 output tokens**, no unknown usage.
No successful Skill body or release result was obtained. Raw receipts:
`.klaude/data/capability-discovery-mcp-final-syg6fzyo/`.

Unlike the preceding interrupted candidate, it does not invent HTTP endpoints or
try Git status. This is bounded, more relevant failure, **not task completion**.
Discovery-disabled 3B used 407.37s and 12,973/144 tokens without completing either;
the enabled final run is more expensive and still fails. Do not describe that
comparison as an efficiency win. The earlier interrupted enabled candidate is
not a complete wall-time baseline.

This run exposed another host defect: the plain-answer path returned 0 when
finalization produced text after a no-progress stop. The final correction now
preserves the explanation and emits a failed-turn event for that specific
host-detected stop. Existing CLI/TUI consumers retain the answer, persist failure
and make `ask` exit 1. Successful recovery and ordinary step/call-budget
finalization retain their existing behavior. No model call, argument rewrite or
new retry is introduced. Recorded-choice CLI replay and refreshed full checks
are recorded below. This does **not** supply universal semantic goal verification.

The completed CSV comparison and Gemma interpretation control are recorded below.

### No-progress status correction: real CLI replay

The captured 3B decisions were replayed through the actual CLI, file tools,
installed Skill reader and stdio MCP client in another isolated workspace.
Only the provider responses were replayed; no fresh inference or old token
counters were claimed. Final source replay
`.klaude/data/capability-discovery-status-replay-kmg7wdeg/` exits **1**, preserves
the exact prior final explanation, and persists `turn_done.failed=true`,
`cancelled=false` (session `fb92afe7957d4d69b179aaa184849bee`, 3.12s). All seven
model-choice slots have unknown token usage in this fixture. An earlier replay
before the final error-branch ordering also exits 1 and is retained separately.

The change adds no requests, retries or permission grants. A workspace-specific
incomplete error takes priority over the generic no-progress notice to avoid
duplicate failure cards. The focused CLI/recovery/discovery/retrieval set passed
**1116 tests, one existing skip**, 90.88s. The final full gate below refreshes
validation after this correction. This addresses the host-detected stop, not a
model that returns a poor answer without triggering any mechanical guard.

## Completed initial discovery gate

Before the final projection/routing corrections, frozen/offline `make check`
passed on Python 3.12.3: **3683 passed,
19 skipped** in 1036.54s; full gate 1045.60s. Ruff passed, and production mypy
reported no issues in 153 files. The 19 skips are existing superseded retrieval
tests; no new skip was introduced. All 154 production Python/prompt hashes
matched the starting snapshot after completion. `make package-smoke` passed
in 13.27s: five wheels, isolated installation, public imports and installed help.
Evidence: `/tmp/klaude-capability-final-validation-i3_g4anp/` contains
`result.json`, `check.log`, `pytest.xml`, `package.log` and `source-sha256.json`.
This validates that earlier host implementation, not the subsequent corrections
or completion of the live workflows.
Python 3.11/3.13 and new GitHub CI execution are not claimed.

A fresh gate after the projection change was intentionally stopped once the
live trace exposed the distinct routing-recovery defect. Its OAuth cancellation
fixture swallowed SIGINT; only that test process and its descendant were then
terminated. Receipt `/tmp/klaude-capability-final-validation-2jzaox_p/result.json`
records exit 2 and changed source hashes, not success. The completed combined
gates below supersede this interrupted gate.

## Combined regression gate before terminal-status correction

The implementation, including compact file/MCP projection, separate native
routing recovery and typed MCP errors, passed the frozen/offline Python 3.12.3
gate:

- Complete unit suite: **3688 passed, 19 existing skips**, 1030.36s.
- `make check`: exit 0, 1039.16s; Ruff clean, production mypy clean across
  **153 source files**.
- `make package-smoke`: exit 0, 13.08s; all five wheels, isolated install,
  public imports and installed `klaude --help` passed.
- All **154 production Python/prompt hashes** matched the starting snapshot.
- `git diff --check` passed; no dependency/lockfile change or new skip.

The original logs/JUnit/receipts are at
`/tmp/klaude-capability-final-validation-gd222tzd/`, with a private durable copy
in `.klaude/data/capability-discovery-final-evidence-gxayiuua/final-gate/`.
The same evidence root retains eighteen evaluation/helper sources with hashes,
including the original observer and its bounded actual-request capture revision.
Two earlier gates were intentionally interrupted for newly observed host fixes;
neither is counted as a pass. This full gate validates host contracts, not model
reasoning or CSV completion. Python 3.11/3.13 and new CI are not certified here.

### Final gate after the terminal-status correction

Frozen/offline `make check` passed on Python 3.12.3: **3688 passed, 19 existing
skips**, 993.01s; full check 998.18s. Ruff and production mypy (153 files) passed.
`make package-smoke` passed in 12.50s for all five wheels, isolated installation,
imports and installed CLI help. All **154 production Python/prompt hashes**
matched the starting snapshot. No production source changed during this gate.
Evidence: `/tmp/klaude-capability-final-validation-80lvwiy_/`, retained privately
at `.klaude/data/capability-discovery-final-evidence-gxayiuua/final-status-gate/`.
This is the final automated validation for the combined implementation.

### Reliability regression coverage

The retained JUnit file contains 3707 cases: **3688 passed, 19 skipped, zero
failures/errors**. Coverage includes the following existing and extended
contracts, rather than relying on the new discovery tests alone:

| Required boundary | Verified regression surface |
| --- | --- |
| Plan approval and continuation | `test_capability_routing.py`: `test_workspace_plan_continuation_keeps_implementation_tools`, plan-scope/disabled-tool guard and code-budget continuation |
| Cancellation and turn-local grants | `test_tool_discovery.py`: cancelled callback release; existing CLI permission/transport/owned-worker cancellation tests |
| Malformed-call recovery | Native/provider parser tests and bounded fresh-action/incomplete-response tests in `test_ollama.py`, `test_workspace_execution.py` |
| Missing paths and stale edits | `test_reliability_repair.py`: missing-file batch discovery; `test_workspace_execution.py`: fresh reads after stale anchors |
| Workspace/source cache invalidation | `test_workspace_execution.py`: external source changes release the read guard and mark excerpts stale; edits invalidate current validation |
| Dirty-worktree safety | `test_reliability_repair.py`: dirty preflight before approval; `test_tools.py`: write lock and read-only commands |
| Shell failures and validation reruns | `test_execution.py`, `test_reliability_repair.py`: typed failures, no-progress accounting and rerunning the same check after a real edit |
| Completion and exit status | `test_workspace_execution.py`: actual edits/current checks gate completion; no-progress CLI replay above verifies exit 1 and persisted failed status |

These are offline contracts plus the separately identified live CLI/TUI
controls, not a claim that every provider/model completed a real coding task.

## Optional execution optimization decision (M4)

No extra programmatic executor or general tool concurrency is introduced. The
observed failures concern argument contracts, missing definitions and decisions
that depend on preceding results; parallelism cannot remove those dependencies.
Existing audited read-only subagent concurrency remains in `SubagentSupervisor`,
with independent provider transports and reserved aggregate budgets. Normal
dependent action batches remain ordered. Native successful tool paths retain
their current behavior. The existing concurrency/cancellation tests are included
in the full gate. This is a documented decision to defer optional architecture,
not a measured claim of faster parallel execution.

## Unchanged implementation benchmark

The exact `docs/benchmarks/stockroom.json` prompt, six baseline files, original
two regressions and external thirteen-case acceptance script are reused. Prompt
hash `c1c41dfa913d8c1355e6ab8aa34648f5c80ff63fc2245e25f0b5fd379f5b5f7d`;
acceptance hash `30d08650be70448be0adff78ce5b3278c4b47aeb5def8d5f2b32acf94ec93eba`.
The harness asserts both hashes and supplies no external acceptance feedback
during autonomous execution. Both original models retain the fixture's general
8192/2048 and code 16384/4096 allocations, thinking off, existing agent budgets,
isolated non-Git projects and separate config/data. The model evaluation lock
serializes runs. The status pointer is
`/tmp/klaude-remaining-stockroom-status.json`; no CSV success is claimed until
actual implementation, original tests, acceptance and generated output are read.
The fresh untouched baseline passes both original tests and only ten rejection
acceptance cases; positive importer/dry-run controls fail as expected. Evidence:
`.klaude/data/capability-discovery-0gz1dkew/stockroom-baseline.json`.

### 3B autonomous CSV result

Root `.klaude/data/remaining-stockroom-o01yqw9o/qwen2.5-coder-3b/`, session
`ce4fa824106140838aa081baca5107d8`. **Incomplete**, exit **1**, 2099.75s, no outer
timeout or manual intervention. The 1800s governor is checked at safe boundaries;
its final in-flight read finishes afterward. Twelve model requests use
**49,433 input / 580 output tokens**, all usage known. Eleven actual tool
invocations comprise three listings, seven reads (one recovery reread) and one
failed edit. No baseline file changes.

The model inspects all six baseline files once before planning, but chooses one
read per response despite support for four independent reads. Its four-step
implementation plan links only `r3`–`r7`, all to `stockroom/cli.py`; storage,
tests, docs and other request references are absent. Its first edit tries to
replace `raise SystemExit(main())` in `cli.py`, although that line was read from
`__main__.py`. The edit fails before writing. Recovery rereads the real CLI, but
the time budget stops implementation. There is no malformed-call/grammar abort,
path guess, permission refusal, or context-admission failure. Peak actual input
is **6812 tokens** under the unchanged 16,384 allocation; missing context is not
established as the cause of this failure.

Nine inspection requests cost 1082.97s; planning costs 284.82s, the failed edit
431.03s and the recovery read 298.58s. Total recorded model time is 2097.39s,
nearly all elapsed time, with only 580 generated tokens. These counters do not
separate uncached prefill from decoding. No claim about KV-cache efficiency or
its cause is made from total request time alone.

The factual saved answer says the task is incomplete, changed files are **none**,
validation was **not run**, and lists remaining work and unlinked references.
Independent post-run validation passes the original **2/2** tests and only the
same **10 rejection-only** acceptance cases as the untouched baseline; all three
positive success/dry-run controls fail. The “generated tests” command runs the
unchanged original two tests—no new suite was produced. This is **no CSV feature
implementation**, not 10/13 success.

This child started before the terminal no-progress status correction. Its
production Python snapshot differs from the final gate only in `agent.py`'s
terminal failure notice; model inputs, tools, workspace behavior and its existing
workspace-incomplete exit path are unchanged. The final handler is separately
verified by captured-decision CLI replay. The 4B child starts on the final
production snapshot; hashes match all final production Python files. Its private
bounded `request-*.json` files record actual runtime-bound requests, without
headers/credentials. The already-running 3B child has counts/results rather than
those complete request captures; its input visibility is correspondingly limited.

### Reboot interruption and resumed comparison

The machine rebooted before the original 4B attempt completed. Its saved trace
contains six completed requests (1535.08s of recorded model time; 26,124 known
input / 1700 output tokens), project inspection and one CLI edit. That edit
placed an `elif` after `else`, producing invalid Python. The next request was
captured, but there is no terminal response, `turn_done` event or final exit
code. Its temporary project disappeared at reboot; no post-run validation is
claimed. Session `5b6204e9f309482b93e64cc112bfcef1`, retained interruption receipt
`remaining-stockroom-o01yqw9o/qwen3.5-4b/reboot-interruption.json`. The queued
Gemma test had not started. Neither interruption is counted as a pass or a
completed model attempt.

After reboot, all **154** production Python/prompt hashes still match the final
passing gate. Preserved harness sources were reused with explicit local launcher
paths. An initial recovery setup put a test workspace under this repository:
the existing dirty-worktree guard correctly kept it read-only. That invalid
harness run was stopped, recorded and excluded. The corrected runs use independent
temporary non-Git projects and copy final project files into the private case
directory. No application code, model, benchmark requirement or budget changed.
Root: `.klaude/data/remaining-stockroom-post-reboot-gl31xt_t/`.

The GPU initially worked again. Actual Ollama placement is recorded, rather than assuming all
weights/context fit: 3B reports 2,341,942,066/2,341,942,066 bytes GPU-resident;
4B reports 2,176,130,742/3,989,967,990 bytes, both at 16,384 context. Faster times
against the earlier CPU attempts cannot establish an orchestration speed gain.

It then failed again during the 4B storage-generation request: the local server
reports `CUDA error: unspecified launch failure`, an aborted runner and failed
CUDA rediscovery; `nvidia-smi` again reports unavailable utilization. Klaude's
existing single GPU-failure recovery visibly retries on CPU, with the **same
model and 16,384/4096 allocation**, setting only `num_gpu=0`. Actual placement
then reports `size_vram=0`. No partial edit from the failed generation executes.
The bounded server log and before/after placement snapshots are retained in the
resumed root. This is mixed hardware execution, not a clean GPU performance
comparison, and a later timeout cannot by itself establish a model capability
ceiling. Driver/service changes and another machine reboot were not attempted.

### Resumed final-source 3B CSV result

Session `92b605e45876484a9bff0e6717df353f`: **incomplete**, exit **1**, 198.54s,
without external timeout or intervention. Thirteen requests, ten actual tools
(three listings, six reads, one edit), **44,852 known input / 671 output tokens**
and two unknown-usage requests. Peak reported input is 6806 tokens; those two
failed requests have full private request captures but no provider usage.

The proposed four changes merely repeat pieces of the request and all target
`cli.py`; tests, storage and docs remain absent. The accepted edit replaces only
the function declaration with a new function body, leaving the old body after
an unconditional return. It changes the legacy `add` arguments, calls a
nonexistent three-argument storage interface and never adds `import-csv`.
This is a substantive model implementation error, not a successful edit merely
because the replacement applied.

Two later responses ended without Ollama's completion marker. The existing
bounded recovery obtains one complete reread between them; the second incomplete
response fails safely, without executing partial calls. Server diagnostics at
the exact corresponding request times report `Unexpected empty grammar stack
after accepting piece: ? (30)`. The successful edit, failed request, recovery
read and second failed request use the **same canonical response-schema hash**.
This establishes a provider/runtime failure in addition to the preceding model
mistake; it does not establish its GPU/numerical/tokenizer cause. Related
[Ollama](https://github.com/ollama/ollama/issues/18369) and
[llama.cpp](https://github.com/ggml-org/llama.cpp/issues/27619) reports describe
the same exception class in different scenarios, not a verified fix or proof
that this case shares their trigger. No service restart, automatic CPU fallback,
extra retry allowance or model substitution was added.

Independent validation passes only **1/2 original regressions**; both original
and generated-test commands fail on the changed legacy CLI. No new tests or docs
were produced. Acceptance still passes only the ten rejection cases and fails
all three positive controls: the command is absent. The saved assistant content
contains the earlier plan, while the CLI visibly reports the stream error and
returns 1; no final completion answer was generated. This remains an interaction
limitation, not a false success claim. Full requests, trace, project copy,
validation and bounded server diagnostics are retained in the resumed root.

### Resumed final-source 4B CSV result

Session `77bc950a91ae444ba096f924397458d2`: **incomplete**, exit **1**, 1856.78s,
without external timeout or manual intervention. Nine actual provider requests
including the failed GPU generation and its CPU retry; nine charged model steps,
fifteen charged tool attempts and twelve executed tools (three listings, six
reads, three writes). Three duplicate root listings were skipped. Reported usage:
**39,913 known input / 4037 output**, one unknown-usage GPU request; peak known
input **7027**. The CPU storage and test generations take **645.06s** and
**736.47s** respectively. Total recorded request time is 1854.75s, nearly all
elapsed time. This run does not encounter a context-admission failure.

The model inspects the complete six-file baseline, proposes separate CLI,
storage, test and README changes, then writes the first three. Its storage code
does not persist transaction history, treats zero delta as an idempotent skip,
checks negative quantities without accumulating earlier rows, uses direct file
writes instead of an atomic stock/history save, and omits exact field checks.
The CLI prints errors to stdout and returns a nested summary with the wrong
contract. These are visible implementation mistakes. The generated tests also
contain wrong assumptions: two expect pre-existing quantities that their setup
never creates; the nominal idempotency test expects a skip on a first import.
Their failures must not all be interpreted as valid implementation diagnostics.

The 1800-second governor stops at the safe boundary after the test write. The
saved answer accurately lists all three changed files, **validation not run**,
unfinished test/docs/check/review work and unlinked request references. No final
success or passing tests are claimed. Independent post-run checks establish:

- Untouched original regressions: **2/2 pass**.
- Model-generated suite: **11/14 pass**, three failures, no autonomous check run
  or subsequent repair before budget exhaustion.
- Unchanged acceptance: **1/13 pass**, only the new-store dry-run/no-directory
  control. Stock/summary parity, replay, persisted conflicts, field validation,
  stderr behavior and the remaining controls fail. README remains unchanged.

The partial implementation is genuine progress beyond a repeated plan, but it
does **not** complete the benchmark. The failed GPU request and slow CPU retry
consume the time available for validation/repair, so this cannot establish what
the same trajectory would achieve on stable GPU hardware. It also does not
excuse the independently observed semantic and test-fixture mistakes.

### Before/after interpretation

| CSV attempt | Actual requests | Known input / output | Original / generated tests | Outcome |
| --- | --- | --- | --- | --- |
| Prior v15 3B, healthy GPU | 13 | 64,625 / 901 | 1/2 original; no checks run by agent | Incomplete, wrong CLI, 229.92s |
| Current 3B, CPU before reboot | 12 | 49,433 / 580 | 2/2 original; generated command runs unchanged two tests | Incomplete, failed edit/no changes, 2099.75s |
| Current final-source 3B, GPU | 13 | 44,852 / 671; two unknown | 1/2 original; no new tests | Incomplete, wrong edit plus provider grammar failures, 198.54s |
| Prior v15 4B, healthy GPU | 13 | 74,454 / 4785 | 2/2 original; 10/15 generated; two autonomous checks | Incomplete; context admission blocked repair, 990.67s |
| Current final-source 4B, GPU then CPU | 9 | 39,913 / 4037; one unknown | 2/2 original; 11/14 generated independently; no autonomous checks | Incomplete; GPU fault/CPU time budget, 1856.78s |

Prior figures are the recorded v15 baseline in
[task-state evaluation](agent-task-state-evaluation.md), not freshly repeated
historical sources. Current request counts/usage come from actual captured
requests and provider counters. Fewer rounds or lower known totals do not prove
efficiency when work stops earlier and failed requests have unknown usage.
Different generated suites also cannot be compared as one fixed accuracy score.
The unchanged external acceptance test is the semantic regression oracle:
**neither small model completes the full CSV benchmark**. The initial baseline's
ten rejection-only passes come from an absent command, not CSV functionality.

The controlled 4B Skill/MCP task above supplies the positive result for this
pass: correct outcome, bounded schemas and smaller peak request input. The CSV
comparison supplies a deliberately retained limit, with runtime instability
separated from model/code mistakes. No p50/p95, GPU-versus-CPU speedup or general
coding-completion claim is supported by these single mixed-hardware attempts.

## Final real Gemma TUI control

Session **`41098d8394924fbc87f5812b1f20bed8`**, titled
`TEST KLAUDE FEATURES COMPOUND ACTIONS`, uses the real full TUI and native
`gemma4:e2b` inference. It attaches the same synthetic 1000×700 credit image,
asks `Read the credit at the bottom. Do not search.`, deletes the original file,
then sends exactly `look them up`. The actual search/fetch tools are controlled
fixtures as in M0/M1; they require the relevant artist name and return the
portfolio lead and separate fetched title/date/credit. No real image or search
service is involved. CPU placement is recorded; no model/context switch or
extra generation allowance is added.

| Turn | Saved result | Governor time | Actual model steps / tools | Known input / output |
| --- | --- | --- | --- | --- |
| Read image credit, no search | Exactly `SALAD MADE BY LUMA QUILL` | 58.81s | 1 / 0 | 666 / 8 |
| `look them up`, after original deletion | Relevant search → portfolio read → correct credit, title and date, explicitly qualified as synthetic/example evidence | 368.56s | 3 / 2 | 10,273 / 453 |
| `Reply exactly OK. Do not use tools.` | `OK.` | 35.25s | 1 / 0 | 1306 / 3 |

**Compound lookup passes; exact-output control fails.** The final control does
preserve tool isolation and short direct routing, but its punctuation violates
the requested exact answer. The raw harness says `passed` because it checks
lookup facts, no additional tools and normal shutdown; it never asserts byte-exact
`OK`. Manual verification of decoded saved answers catches that gap. Raw results
are retained alongside `assessment-corrected.json`; no model output is rewritten.
This remaining formatting compliance issue is not counted as a green control.

Lookup executes only `web_search("SALAD MADE BY LUMA QUILL")` and
`fetch_url("https://artist.example/portfolio")`, with no duplicate/failed calls
or discovery overhead. Reported inputs grow **3125 → 3380 → 3768** inside the
configured 8192 context. The observer records all three lookup requests; native
tool-free streaming is counted from saved governor outcomes. Config requests
768 output tokens; shared `RequestBudget` conservatively reserves at least
1024 for admission, which does not itself alter native generation options.
Those projection numbers are reservation evidence, not a separate wire capture.

The later lookup uses the already-read textual credit; saved modality metadata
correctly reports **no pixels supplied** for that nonvisual follow-up. This
proves useful continuity after deleting the source, not a new pixel-reread test.
Earlier image-follow-up/resume pixel evidence remains in the linked S6 reports.
The final answer includes the correct fetched facts and identifies `.example`
as potentially synthetic; it does not establish authentic real-image provenance.
It remains verbose and calls a successful read an “attempt,” so prose quality
is not certified as polished.

The TUI exits normally with code 0, releases the owned client/evaluation lock and
persists all three non-error turns. The unchanged production hashes match the
final full gate. Evidence:
`.klaude/data/compound-remaining-gemma-interactive-p91w3ye_/` contains raw results,
corrected assessment, session, trace and 120/80/40-column text/SVG captures.
The 120-column activity is concise and legible. Existing transcript lines clip
when the **pyte** emulator is resized narrower; these captures cannot distinguish
that emulator's history-reflow limitation from application layout behavior.
They are not evidence of fully validated 40-column transcript reflow. The
80-column live footer fits; the 40-column footer is cramped. No rendering change
was made from this inconclusive resize capture.

## Later follow-up

The [validation and recovery follow-up](agent-validation-recovery-followup.md)
addresses the remaining plan restrictions, late validation, syntax feedback,
terminal failure summaries and exact literal output. Its results are separate;
the measurements below describe this completed capability-discovery pass.

## Remaining limits and next decision

### Model and runtime limits

- The 3B model confuses task identifiers with tool-name hashes, repeats weak
  plans and makes incorrect replacements despite having the relevant original
  files. These are observed semantic/implementation mistakes. The final GPU
  grammar failures are separately evidenced provider failures, not proof of a
  model reasoning ceiling.
- The 4B model completes the controlled Skill/MCP question and produces a more
  useful coding plan, but its CSV storage logic and generated test fixtures remain
  incorrect. The current mixed GPU/CPU run never reaches autonomous validation;
  no successful repair cycle or full CSV completion is claimed.
- CUDA launch failure recurs after reboot. CPU fallback preserves the turn and
  the model choice but spends much of the unchanged elapsed budget in two
  generations. Stable-runtime, repeated comparisons are still needed before
  attributing wall time or the incomplete 4B repair phase to agent architecture.

### Klaude limits

- Discovery matches bounded metadata terms, not semantic tool suitability.
  Schema validation cannot establish that a string is the right deployment ID.
  Enabled third-party tools retain their actual permission gates; metadata is
  neither authorization nor proof of safe side effects.
- Lookup obligations verify observed actions, not source relevance, identity,
  interpretation or arbitrary natural-language requirement coverage. Short
  ambiguous follow-ups still depend on the model's use of recent dialogue.
- Implementation plans remain optional, model-proposed and turn-local. Original
  request spans are preserved, but linking a span, changing a file or passing an
  existing test cannot prove the requested feature was implemented.
- Discovery reduces schema pressure; it does not solve large coding histories,
  oversized repository guidance, model-generated wrong tests or all stale-context
  decisions. The current CSV failures do not establish context exhaustion.
- The governor checks elapsed limits at safe boundaries. It does not preempt a
  healthy in-flight generation at exactly 1800 seconds. The external harness has
  its own explicit limit. No new hard-deadline implementation is claimed.
- A terminal transport failure can leave the earlier public plan as the latest
  saved assistant content. The failed status/error is persisted and visible, but
  a new explanatory model answer is not guaranteed after a provider failure.
- Paid cloud inference, free-router quality, broad live website behavior and all
  combinations of knowledge retrieval, Skill-guided editing and research are
  not newly certified here. Existing fixture contracts and earlier live feature
  coverage are linked separately; they are not fresh provider benchmarks.

### Recommended next experiment

First obtain a stable, recorded local-runtime baseline on the **same** models
and unchanged benchmark, without silently increasing budgets or switching models.
Capture separate prefill/generation/cache timing where the runtime actually
provides it; repeated trials are needed for latency claims.

Then measure a bounded validation/repair reserve and earlier useful diagnostics
after a model-chosen implementation slice. The observed runs spend their time on
inspection/planning and large edits before any check; generated tests themselves
can also be wrong. Compare requirement coverage, useful validation, recovery,
total requests and time against this implementation before adopting the change.
Keep ordinary short turns direct and preserve exact tool outcomes/authority.
The evidence does not justify a mandatory new planner/judge, more general prompt
prose, automatic model substitution or another programmatic executor now.

## Delivery audit

| Researched step | Delivered evidence and remaining boundary |
| --- | --- |
| M0 — Observe failures | Earlier typed transport/elapsed diagnostics and synthetic baselines retained; this pass adds exact MCP application-error and terminal no-progress evidence. No new universal hard-deadline claim. |
| M1 — Compound goals | Earlier Qwen text lookups and current Gemma image-credit/pronoun lookup complete; source examination and direct no-tools routing are enforced. Semantic correctness and exact formatting remain model-dependent. |
| M2 — Capability discovery | Implemented and tested across enabled built-ins, real installed Skills and actual stdio MCP; 4B completes the controlled workflow. 3B still supplies wrong identifiers/Skill paths. |
| M3 — Broader workflows | Listed CLI/TUI, recovery, cancellation, resume, dirty-tree and unchanged CSV checks completed. Broader acceptance remains **partial**: neither CSV implementation succeeds, exact Gemma `OK` fails, and paid/live combined workflows are not all certified. |
| M4 — Optional optimization | Assessed and deliberately deferred; existing read-only subagent concurrency remains. No evidence supports adding another executor to these dependent workflows. |

Both final evaluation clients exited, the evaluation lock is released, and no
model evaluation remains queued. Ollama's existing service/model keepalive is
left intact. No production source changed after the final passing full gate;
subsequent changes are this report and links. No commit, push, dependency or
lockfile change was made.
