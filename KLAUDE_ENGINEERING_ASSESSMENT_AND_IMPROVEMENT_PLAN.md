# Klaude Engineering Assessment and Improvement Plan

Status: working planning document
Assessment date: 2026-09-10
Repository version observed: `0.2.0a3` development worktree

Latest review: **2026-10-01**. Start with
[the stabilization-first roadmap](#late-september-2026-stabilization-first-roadmap)
below. Its execution order supersedes the historical recommendations; older
progress entries remain historical evidence, not current completion guarantees.

Current continuation checkpoint: **Stage 1, authentication/MCP setup,
stable-ID pickers, cross-client settings coordination, and owned catalog/skill
jobs, asynchronous local catalogs/Codex usage, and cancellable cloud activation
implemented, plus snapshot-only status/read-only metadata jobs and coalesced
shared-session I/O (2026-09-30)**.
Hardware-only Auto Calibrate now also runs in an owned cancellable job.
Settings overview memory/MCP summaries now use owned read-only snapshot jobs.
Runtime preference writes now also use a serialized background writer.
Permission/composer changes and runtime resets now share that writer as well,
with ordered reset/edit coalescing and revision-scoped merged policy acknowledgements.
Appearance now has its own serialized writer with lock-scoped legacy migration,
immediate previews, field merges, and independent revision-scoped save feedback.
Tools now uses live snapshots and the shared serialized preference writer,
including rapid-toggle/reset ordering and merged boolean acknowledgements.
Remembered-model saves now share the preferences writer, with save feedback and
confirmed-selection-only submission; the mode-picker cancel rollback bug is fixed.
Model-setting history and observer updates now use an owned ordered action lane
and a single atomic transaction, rather than synchronous selection-handler writes.
Memory detail inventory now uses an owned bounded read-only job; automatic-memory
toggle/reset and TUI on/off commands use live intent and ordered background writes.
MCP settings/registry-detail navigation now uses bounded private metadata jobs,
aged caches, stable filters/selection, and complete-inventory install gating.
Undiscovered-server review now uses an owned job with exact-definition confirmation;
enable preflight rejects changed definitions off the UI thread before contacting them.
Post-discovery MCP publication now saves and prepares replacement tools off-thread,
with actual-outcome reporting for late cancellation and preservation on reload failure.
Cached MCP toggles now use the fixed ordered mutation lane with definition binding,
bounded acceptance/shutdown waiting, scoped acknowledgements, and uncertain-catalog queue holds.
Post-discovery enable now hands off to that same lane without an unbounded setup drain
(2026-10-01); its acknowledgement is the sole enable-success boundary.
Verified read-only reload recovery and disabled registry installs without secret
input now use that lane as well (2026-10-01).
Atomic disabled imports and custom adds without bearer secrets now use it too.
Next: finish bearer-token custom setup and secret-bearing install publication,
then remaining explicit session actions before
finishing terminal latency and
modal/queue lifecycle acceptance gates. See the execution records before
starting another implementation slice.

## Implementation progress

Updated 2026-09-12:

- Checkpoint `e60c5d6` was committed and pushed before roadmap work began.
- Priority 0 started: a least-privilege, SHA-pinned GitHub Actions workflow now
  covers Python 3.11-3.13 tests, Ruff, and production-source mypy; `make check`
  mirrors the same local quality surface.
- Priority 1 advanced: the existing finalization reserve is retained, the 1-64
  step ceiling is visible and persistent through Runtime settings, and a new
  provider-independent governor tracks steps, tool calls, safe-boundary elapsed
  time, repeated outcomes, and cross-tool non-progress. It stops tool activity
  after a bounded non-progress streak and drives a factual tool-free finalization.
- Priority 2 is substantially implemented: immutable `TurnCapabilities`
  snapshots now distinguish the global enabled registry from actual request
  schemas and record unavailable reasons, effective permissions, hard constraints,
  dirty-worktree state, provider capabilities, injected instructions, and live
  budgets. Denied tools are omitted from schemas. The model prompt, `/status`,
  agent completion event, and shared `turn_done` event use the same snapshot.
- Priority 3 implemented for the current architecture: applicable `AGENTS.md`
  files are loaded root-to-leaf with deterministic precedence, a combined
  12,000-character bound, and reserved capacity for nested guidance. Status
  reports whether instructions were injected fully or with bounded truncation.
- Priority 5 has started with offline, fixture-driven transcript replays that
  assert routed schemas, model capability claims, and completion metadata remain
  identical for disk diagnostics, contextual typo follow-ups, and web lookups.
  Those replays now run as a capability matrix across constrained local,
  default local coder, general OpenAI, Codex-authenticated, and tool-less model
  profiles. Tool-capable profiles must preserve routing; tool-less profiles must
  expose no schemas and explain the provider limitation without retrying.
  Coverage now also includes provider changes retaining conversation, live
  capability synchronization to resumed observers, transactional stale-worker
  recovery, concurrent recovery idempotence, and tool start/result/activity/
  completion ordering.
- Session recovery now durably finalizes a turn whose worker lease expired:
  partial public output is saved once, one visible interruption and recovered
  `turn_done` are recorded, and the stale lease is cleared atomically. It never
  fabricates a tool result or completed activity milestone.
- A real subprocess crash harness now kills a lease-owning worker during a turn
  and verifies that another process recovers it exactly once without fabricating
  a tool result. Interrupted streams also discard an unpublished partial
  text-form tool tag from subsequent model history while preserving safe prose.
- Native OpenAI streams now require an explicit terminal completion and Codex
  native tool items are validated for identifiers and JSON-object arguments;
  malformed provider events fail closed with deterministic regression coverage.
- Codex stream assembly now reconciles missing `output_item.done` events from
  the authoritative completed response, deduplicates provider-issued tool and
  encrypted-reasoning IDs, uses completed text as a safe delta fallback, and
  retains non-secret response identity/status metadata. Klaude deliberately
  does not send `previous_response_id` while its cloud privacy boundary remains
  `store=false`; continuity uses local history replay.
- Priority 0 now includes a distribution smoke gate: all workspace wheels are
  built, installed together in a fresh virtual environment, imported, and the
  installed `klaude --help` is executed locally and in CI.
- Cloud token telemetry now normalizes Ollama, OpenAI/Codex, and Gemini usage,
  preserves live estimates when usage is absent, and mirrors only a bounded
  secret-free metadata whitelist to `/resume` observers.
- Provider/model tool support is now authoritative: a model declaring no tool
  support receives no schemas, and its capability snapshot explains that
  unavailability. CI now runs for feature-branch pushes, and development package
  identities have advanced beyond the published alpha.3 artifacts. The root
  `uv.lock` is now tracked so frozen CI can reproduce the validated dependency
  graph from a clean checkout.
- Priority 0 now has a manual non-publishing release-candidate gate: it builds
  the five wheels twice with a fixed source timestamp, validates structure and
  package identity, requires byte-identical output, writes SHA-256 sums, and
  uses the current official `actions/attest` path for Sigstore-backed GitHub
  provenance. Local double-build validation passed for all five alpha.4 wheels.
- Provider-specific interruption handling is now hardened across Ollama,
  OpenAI/Codex, and Gemini: active transports are detached before close,
  repeated cancellation is idempotent, teardown exceptions cannot escape into
  TUI controls, and focused fixtures cover failed provider closers. Existing
  partial-output and partial-tool-markup recovery remains the safe-boundary
  contract.
- The next evaluation slice should add an opt-in live model harness that records
  success, invalid calls, retries, permission prompts, tokens, time, safety
  violations, finalization quality, and retrieval support without making the
  deterministic unit suite depend on network services or paid accounts.
- That opt-in harness is now implemented in `scripts/evaluate_agent_behavior.py`.
  Each model/scenario pair uses a fresh read-only child process with a hard
  timeout; network retrieval requires an extra explicit flag; report paths are
  preflighted before provider work; and JSON retains sanitized metrics and an
  answer fingerprint rather than answer text, tool output, raw provider errors,
  or credentials. The next step is to run and publish representative results on
  explicitly authorized local/cloud models before changing orchestration policy.
- The configured local Ollama endpoint was unavailable during the current live
  probe, so no model-quality claim is made from an unexecuted live harness run.
  Adaptive concurrency is checkpointed in `7e34e02`, and visible runtime
  configuration is checkpointed in `947c1c4`.
- Normal-turn tool-call budgeting is now independently configurable through
  `[agent].max_tool_calls` (0 retains the derived two-calls-per-step ceiling),
  and the effective value is disclosed in model configuration and `/status`.
- Normal-turn exact token budgeting is also configurable through
  `[agent].max_total_tokens` (0 keeps the provider/context default and missing
  usage remains unknown), completing the basic user-visible governor controls.
- LanceDB validation was isolated: under the restricted Codex sandbox, LanceDB
  0.38 can block inside its Rust-backed async local connection/list-table path;
  outside that restriction, the isolated roundtrip passes and the complete
  knowledge suite passes 80 tests with 18 expected skips. No storage backend
  change was committed because the failure is environment-specific.
- Live qwen3.5:9b workspace inspection now passes after a bounded
  `workspace_info` preflight. Contextual storage follow-ups also now retain
  `storage_usage` when scoped routing removes the unavailable `run_shell` hint;
  deterministic regression coverage passes. A subsequent live contextual probe
  reached a provider/model startup timeout before its capability observer, so it
  is not treated as a product failure or success claim.
- Live routing validation on 2026-09-12 exposed and repaired negation blindness:
  prohibited workspace inspection no longer runs, `do not modify` no longer
  suppresses a contextual `run them` storage diagnostic, and the resolved
  storage decision survives user-boundary compaction. qwen3.5:4b then passed the
  direct-answer scenario in 48.779s and contextual diagnostic in 77.067s with a
  coherent `storage_usage` start/result pair and no retries or safety violations.
- OpenAI Codex gpt-5.5 passed the playground workspace-inspection scenario in
  17.747s after completed host preflights were removed from callable schemas;
  the redundant second `workspace_info` call disappeared. Timeout evaluations
  now retain sanitized progress: a deliberately capped qwen3.5:4b run recorded
  one completed workspace preflight and one in-flight model request without
  saving answer text, tool output, raw provider errors, or credentials.
- Priority 4 advanced without weakening the local-first privacy boundary:
  OpenAI API and Codex Responses calls keep `store=false`, request encrypted
  reasoning content, and retain a strict provider replay envelope for reasoning,
  assistant messages, and function calls. Stateless continuation now preserves
  assistant `phase` values and avoids reconstructed duplicates; incomplete
  function-call pairs remain excluded. Completed replay envelopes persist only
  as private session `model_content`, allowing process resume without exposing
  opaque state in transcript text or shared events. A SHA-256-derived session
  cache key now stays stable across turns and resume without disclosing the raw
  session ID, and rotates for new/forked sessions. OpenAI API and Codex requests
  use server-side compaction at 75 percent of a known context window while
  retaining `store=false`; encrypted compaction items are replayed privately and
  older provider dialogue is pruned before the latest item without dropping the
  current Klaude system/capability contract. `/status` and observers receive only
  exact cache hit/write counters reported by the provider. Priority 4 is complete
  for the current OpenAI Responses providers; non-Responses backends retain their
  existing provider-specific continuity contracts.

## Remaining roadmap snapshot (2026-09-13)

- Priority 0: create coherent named checkpoints for the current dirty work and
  split the oversized root guidance into maintainable runtime, contributor, UI,
  release, and architecture documents without weakening instruction precedence.
- Priority 4: complete for OpenAI API and Codex Responses. Stateless reasoning,
  phase preservation, private replay across process resume, stable private cache
  routing, provider compaction, and bounded cache telemetry are implemented.
- Priority 5: expand live matrices across representative local/cloud models,
  expand the new isolated synthetic learned-document grounding scenario into a
  broader retrieval-quality dataset, and publish comparable reports. Each worker
  now gets a private data directory, uses no real memory/session/library state,
  and earns grounding credit only when an expected claim and accepted exact
  source appear together after successful retrieval. Timeout observability and
  direct/tool-routing validity are also covered. Reports now aggregate pass rate,
  elapsed time, grounding, token totals, and missing-token counts by model and
  scenario. Live validation on 2026-09-13 showed OpenAI Codex gpt-5.5 passing the
  synthetic learned-document scenario in 9.071 seconds with one coherent
  `query_knowledge` start/result pair, grounding score 1.0, and no retries. The
  constrained qwen3.5:4b omitted retrieval after one corrective retry; qwen3.5:9b
  reached the retry but exceeded the 180-second boundary. These remain model
  capability/performance failures captured by the matrix, not reasons to bypass
  model-led retrieval with an automatic hidden tool call.
- Priority 6: validate controlled read/research and test/diagnostic subagents
  live before considering any mutation-capable implementation worker.
- Priority 7: design and implement an opt-in durable worker service for work that
  survives the owning CLI process; current session leases provide observation
  and crash recovery, not continued execution.
- Priority 8: incrementally extract TUI, routing, execution, and provider-state
  responsibilities from the large CLI and agent modules behind existing tests.
- Priorities 9-10: benchmark learned-knowledge freshness and traceability, add
  dependency/license/secret scanning and parser/sandbox fuzzing, produce SBOMs,
  and seek independent security and coding-benchmark evidence.

## Executive assessment

Klaude is an exceptional alpha-stage local-first agent platform with strong
safety, session, retrieval, and knowledge foundations. It is not yet a
frontier-grade product because runtime correctness, maintainability,
evaluation, release discipline, and multi-agent execution lag behind the
breadth of its features.

The greatest risk is no longer a missing feature. It is the interaction between
many sophisticated features inside a few very large modules without continuous
integration or systematic agent evaluations.

## Live measurements

These measurements came from the development checkout on 2026-09-10:

| Check | Result |
|---|---:|
| Python source | 58,059 lines |
| Unit suite | 1,000 passed, 19 skipped in 34.66s |
| Ruff | All checks passed |
| Production-source mypy | 0 issues in 37 files |
| Whole-repository mypy | 247 errors in 15 files |
| Git history | 17 commits, one author |
| Worktree at assessment time | 32 modified, 1 deleted, 4 untracked |
| Knowledge inventory | 789 libraries, 819 online-doc entries |
| CI workflows | None at initial assessment; implementation now added |
| ADRs | Directory exists but is empty |
| `AGENTS.md` | 1,194 lines, 70,454 bytes |
| Largest production module | CLI: 13,081 lines |
| Agent runtime | 5,196 lines |
| Web providers | 5,528 lines |

The complete unit suite passed outside the restricted assessment sandbox. One
LanceDB test stalled inside that sandbox but passed individually in 2.42 seconds
outside it. This appears environment-sensitive rather than a confirmed storage
defect, although Klaude should report a timeout instead of appearing hung.

## Corrections to the external assessment

- The current test result is 1,000 passed and 19 skipped, not 991 passed.
- Mypy is clean for the selected production directories, but `mypy .` reports
  247 errors in tests, fakes, and protocol implementations.
- The interactive UI intentionally uses the normal terminal screen, not an
  alternate-screen full-screen TUI, so completed output remains in scrollback.
- The default agent limit is 20 steps and is configurable from 1 to 64 in
  `config.toml` and Runtime settings through Safe, Balanced, Extended, and
  Custom choices.
- Klaude is not entirely dependent on Ollama. It supports Ollama, OpenAI API,
  Gemini, and OpenAI Codex/ChatGPT-account runtimes.
- Klaude has background model threads and cross-process session observation.
  It does not yet have a durable worker that continues after the owning process
  exits.
- Encrypted Codex reasoning items are preserved across requests. Provider-native
  response IDs, phase preservation, and provider compaction remain incomplete.
- Search and knowledge architecture are strong, but claims that they outperform
  every commercial agent have not been proven with comparative benchmarks.
- The security design deserves a high score, but an A+ claim requires external
  review and adversarial validation.

## Strong foundations

### Safety architecture

Klaude has unusually strong controls for an open-source agent:

- Linux Landlock sandboxing
- workspace path confinement
- command preflight and risk classification
- dirty-worktree mutation lockout
- sensitive-path restrictions
- environment and secret scrubbing
- isolated shell `HOME` and temporary storage
- bounded system-storage diagnostics
- per-tool permission gates
- protection against committing unrelated user work

The next safety challenge is compositional correctness: these boundaries must
remain safe when routing, permissions, Git ownership, subprocess execution,
auto-commit, cancellation, and recovery interact.

### Sessions and terminal behavior

Klaude has a strong local session system:

- renewable SQLite worker leases
- active-session observation from another client
- streamed activity and transcript events
- shared `/resume`
- interrupted-turn recovery
- queued and steered messages
- model changes retained in the conversation
- persistent terminal scrollback

This is a meaningful product differentiator.

### Knowledge and web systems

The knowledge layer includes:

- LanceDB vectors and SQLite FTS5
- hybrid retrieval and rank fusion
- versioned source activation
- failed-operation recovery
- refreshable documentation
- source learning and skill imports
- MCP exposure

The web layer has nine-provider routing, provenance, provider fallback, safety
bounds, and conservative billing controls. Search results must remain discovery
leads until selected pages are fetched and verified as evidence.

### Product boundary

Klaude remains responsible for tools, memory, knowledge, permissions, sessions,
and its UI even when a cloud model is selected. That is the correct design. It
prevents Klaude from becoming a wrapper around another agent CLI.

## Principal weaknesses

### Unreleased worktree state

Important behavior currently spans dozens of modified files, while new Codex
authentication and reliability modules remain untracked. The tagged release
therefore does not reproduce the product currently being tested, regressions
are difficult to bisect, and repairs can accidentally depend on unsaved work.

### Runtime state is insufficiently formalized

The agent loop handles routing, recovery, text-form tool parsing, retrieval,
compaction, permissions, provider behavior, validation, events, and finalization.
Failures such as exhausted step budgets, disappearing output, invalid tool
calls, and inconsistent recovery indicate the need for an explicit execution
state model rather than a larger fixed step cap.

### Provider continuity is incomplete

Klaude preserves Codex reasoning state but still manually reconstructs much of
the provider input. Provider adapters should explicitly support response
continuation, phase preservation, compaction, usage accounting, prompt caching,
tool-call streaming, resumability, and model discovery where available.

### The model does not receive every important truth consistently

- Repository `AGENTS.md` files are detected but not yet injected.
- Interactive permission overrides can differ from base configuration reported
  by top-level status.
- Global tools, per-turn callable tools, permission decisions, and hard safety
  constraints need one authoritative capability snapshot.
- The turn-step setting is not visible in Settings.
- Provider quota and reset information can be incomplete.

### Maintainability

The 13,081-line CLI, 5,528-line provider module, and 5,196-line agent runtime
concentrate too many responsibilities. The large CLI test module mirrors this
structure rather than containing its complexity.

### Continuous validation

The repository now has a first least-privilege continuous-integration workflow,
but still lacks coverage gates, packaging smoke
tests, transcript replay, local-model behavior matrices, retrieval benchmarks,
tool-routing evaluations, and systematic adversarial sandbox tests.

## Prioritized improvement program

### Priority 0: Make the current state reproducible

1. Review and organize the dirty worktree into coherent checkpoints.
2. Ensure every new implementation file is tracked.
3. Expand the new CI across supported Python versions beyond unit tests, Ruff,
   production mypy, installation/import checks, CLI smoke tests, and bounded
   knowledge tests.
4. Add a release-candidate workflow and changelog.
5. Split the root guidance into a concise runtime contract, contributor guide,
   UI behavior specification, release history, and architecture decisions.

Acceptance gate: a clean checkout at a named commit reproduces the tested
behavior and validation results.

### Priority 1: Replace the step cap with a progress-aware governor

Keep a hard emergency ceiling, but govern turns with several independent
budgets:

| Budget | Purpose |
|---|---|
| Model/tool transitions | Emergency runaway protection |
| Wall time | Prevent indefinitely stalled turns |
| Model tokens | Bound context and provider cost |
| Tool calls | Bound external actions |
| Repeated failure signatures | Stop retry loops immediately |
| Research budget | Bound search and fetch expansion |
| Mutation budget | Bound affected files and operations |
| Finalization reserve | Preserve one answer-producing step |

Progress signals should include new evidence, changed failure conditions,
improved test results, fewer unresolved tasks, and expected file-state changes.
When progress stops, Klaude should preserve completed work and explain how the
user can continue instead of returning a raw step-budget exception.

Recommended terminal message:

> `[STOPPED] Klaude reached this turn's execution limit after 20 model/tool`
> `steps. Completed work was preserved. It stopped to prevent an unproductive`
> `loop. Ask it to continue, narrow the task, or raise the limit in Runtime`
> `settings.`

Add a `Turn limits` Runtime setting with Safe, Balanced, Extended, and Custom
presets. Keep bounded defaults for constrained hardware and visible overrides
for stronger systems.

### Priority 2: Establish one per-turn capability contract

Before every model request, create an immutable snapshot containing:

- globally registered tools
- tools callable in this turn
- effective ask/allow/deny policy
- hard constraints that permission cannot override
- workspace and dirty-tree state
- plan, review, and init restrictions
- remaining execution budgets
- provider capabilities
- applicable injected instructions

The model prompt, `/status`, tool router, permission UI, and event stream should
derive from the same snapshot. Permission changes from Settings must affect the
next model request immediately. Status should distinguish configured defaults
from interactive overrides.

Implemented: `klaude_core.capabilities.TurnCapabilities` is rebuilt before every
request and serialized into the model prompt, `/status`, agent `done` payload, and
cross-process `turn_done` event. Typed `standard`, `plan`, `review`, `init`, and
`evaluation` scopes apply explicit tool allowlists before schemas are built. Init
writes have a hard pre-permission target check for the workspace-root `AGENTS.md`;
evaluation cannot request interactive input. Settings changes and scope boundaries
are regression-tested across consecutive requests in one process.

### Priority 3: Inject repository instructions properly

1. Load the root `AGENTS.md`.
2. Load more specific guidance for files and directories being accessed.
3. Apply deterministic precedence.
4. Bound instruction size.
5. Treat repository text as context, never permission escalation.
6. Display exactly what was injected in `/status`.

Do not send the current 70 KB document wholesale on every turn. Extract a
compact runtime contract and retrieve detailed behavioral specifications only
when relevant.

### Priority 4: Complete provider-native continuity

Define an explicit provider-capability contract for:

- persisted reasoning
- response continuation IDs
- prompt caching
- provider compaction
- streaming tool calls
- usage and rate-limit metadata
- resumability
- model discovery

For OpenAI Codex, preserve response phase, use native compaction when suitable,
retain compatible continuation identifiers, map quota errors to useful reset
messages, and display only quota windows actually reported by the backend.
Clearly label estimates or unavailable values.

Relevant official guidance:

- [OpenAI latest-model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [OpenAI GPT-5.5 guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.5)
- [Responses compaction reference](https://developers.openai.com/api/reference/java/resources/responses/methods/compact)

### Priority 5: Build behavioral evaluations

Create transcript-driven regressions from real failures:

- capability claims disagree with callable tools
- unavailable or malformed tool calls repeat
- permissions change during a session
- dirty worktrees perform read-only diagnostics
- model changes retain conversational context
- long edits approach execution limits
- clients resume an active remote turn
- a process dies during model or tool work
- contextual corrections such as `run them`
- learned-document retrieval includes supporting citations

Run the suite against a constrained local model, the default local coding model,
one general cloud model, and the Codex-authenticated runtime. Track success,
invalid calls, unnecessary permission prompts, repeated failures, tokens, time,
safety violations, finalization quality, and retrieval support.

### Priority 6: Add controlled subagents

Recommended topology:

```text
Turn supervisor
|-- Primary agent
|-- Read/research worker
|-- Test/diagnostic worker
`-- Optional scoped implementation worker
```

Each child receives a typed task, bounded context, explicit tool subset,
intersection of parent and user permissions, independent budgets, structured
result contract, cancellation, and public activity events.

Safety and coordination rules:

- Children are read-only by default.
- Only the primary agent coordinates mutations.
- Git mutation remains primary-agent-only.
- Independent inspection and tests may run concurrently.
- Conflicting edits are serialized or protected by file ownership.
- Children cannot elevate permissions or escape parent budgets.
- Results remain visible and resumable through the session event system.

Use adaptive concurrency: one child on constrained local hardware, up to two on
stronger local hardware, and configurable higher concurrency for cloud models.
Never silently change models or hardware settings.

Foundation implemented: core now defines typed read/research and
test/diagnostic tasks, parent-intersected read-only capability assignments,
conservative permission inheritance, bounded child and aggregate budgets,
cancellation checks, structured results, and public lifecycle events. Execution
is intentionally sequential until provider-runtime isolation exists. An isolated
child adapter now receives only bounded task context under a dedicated
non-interactive scope and charges successful or failed child usage to the parent
turn governor. Explicit delegation and second-opinion requests now narrowly expose
one permission-controlled child. Each built-in provider now forks an independent
transport/session tracker for the child, while host cancellation fans out across
primary and child transports. Sanitized start/finish metadata and a bounded public
result persist for `/resume`. Model steps and tool calls now have independent
and aggregate caps, with one parent result slot reserved and multi-call batches
stopped at the exhausted boundary. Exact provider-reported input/output tokens
are accumulated across child requests under per-child and aggregate caps;
missing or partial counters are marked unknown rather than estimated, and the
tool-free finalization reserve is counted even when it crosses the nominal cap.
Lifecycle ordering is now implemented: every
batch has a durable public ID and monotonic sequence, callbacks are serialized
across worker threads, duplicate or impossible transitions are dropped, and work
blocked before starting is recorded as rejected rather than finished. Adaptive
execution is now implemented for up to three independent tasks per delegation:
Ollama remains single-worker, cloud runtimes use at most two workers, and only an
audited stateless workspace-tool subset may overlap. Parallel children receive
fixed aggregate reservations before launch and results are restored to input
order; web, knowledge, Git, shell, mutation, and unknown tools still force
sequential execution. The next slice is live behavioral validation and visible
configuration before considering implementation workers. Runtime settings now
provide that visible configuration: provider-aware Auto plus explicit 1-4 worker
overrides, persisted independently from the repository config default and shown
to the active model and `/status`.

### Priority 7: Add durable background jobs

Current observers can follow a live owning process, but they cannot keep work
alive after it exits. A later worker service should add durable jobs, renewable
leases, heartbeats, idempotent activity IDs, crash recovery, reconnectable
permission and input prompts, cancellation, and observer synchronization.

### Priority 8: Modularize the TUI and agent runtime

Suggested CLI structure:

```text
klaude_cli/
  commands/
  tui/
    controller.py
    composer.py
    completion.py
    pickers.py
    transcript.py
    activity.py
    session_sync.py
    permissions.py
  rendering/
  auth/
```

Suggested core structure:

```text
klaude_core/
  execution/
    supervisor.py
    governor.py
    state.py
    recovery.py
    events.py
  routing/
  provider_state/
  instructions/
```

Migrate incrementally behind current tests. Do not attempt a wholesale rewrite.

### Priority 9: Improve retrieval and learned knowledge

Focus on quality and lifecycle rather than merely ingesting more documents:

- source provenance and revision history
- freshness and invalidation
- retrieval evaluation datasets
- old/new source conflict handling
- citation-to-chunk traceability
- routing across hundreds of libraries
- duplicate and obsolete library detection
- incremental refresh
- visible source health
- model-led retrieval without forced irrelevant search

Learning must remain explicit or permission-approved. Ordinary browsing should
not silently mutate durable knowledge.

### Priority 10: Establish external confidence

- Run SWE-bench Verified or a transparent smaller subset.
- Publish routing and retrieval evaluation results.
- Add dependency, license, and secret scanning.
- Fuzz command parsing and classification.
- Test symlink races, TOCTOU, redirection, environment leakage, and cancellation.
- Produce SBOMs and signed releases.
- Obtain an independent security review.

Native IDE and cloud-execution integrations should follow core reliability;
they expand surface area without fixing the underlying agent.

## Revised scorecard

| Dimension | Grade | Assessment |
|---|---:|---|
| Architecture | A- | Excellent subsystem boundaries; oversized implementations |
| Unit engineering | A- | 1,000 passing tests and clean Ruff; no CI |
| Type safety | B | Production source clean; complete repository is not |
| Security design | A- | Outstanding controls, pending adversarial review |
| Agent runtime | B+ | Sophisticated but still heuristic and cap-driven |
| Provider integration | B+ | Broad and improving; native continuity incomplete |
| Sessions and resume | A- | One of Klaude's strongest differentiators |
| Knowledge/RAG | B+ | Strong architecture, insufficient quality benchmarking |
| Web research | A- | Exceptional breadth, unproven comparative quality |
| TUI/UX | B+ | Excellent capability, poor modularity |
| Maintainability | C+ | God modules and oversized behavioral specification |
| CI and release discipline | C- | No automation; important work is unreleased |
| Ecosystem and evidence | C | MCP is valuable; no independent benchmark evidence |

Overall: **B+ as a product today and A- for ambition and technical
foundations.**

## Recommended execution order

1. Make the current state reproducible.
2. Formalize execution, progress, and capability state.
3. Inject repository instructions accurately.
4. Complete provider-native continuity.
5. Establish transcript-driven evaluations.
6. Add scoped subagents.
7. Add durable background execution.
8. Modularize large implementation files incrementally.
9. Benchmark retrieval and coding behavior.
10. Expand into IDE and ecosystem integrations only after reliability gates pass.

Following this order can move Klaude from an impressive personal agent into a
credible frontier open-source platform without sacrificing its local-first
identity, constrained-hardware support, or safety model.

## Late September 2026 stabilization-first roadmap

Review date: 2026-09-30. Status: planned; this section does not claim its repairs
have been implemented. Preserve existing worktree changes. Saving this plan
does not authorize committing, pushing, or expanding implementation scope.

### Decision and scope

Continue Klaude, but prioritize stabilization before adding more capabilities.
Keep the existing Python workspace, provider abstraction, permission boundaries,
local knowledge, session observation, Prompt Toolkit, and ordinary terminal
scrollback. Use incremental extraction behind regression tests, not a rewrite.

Do not equate unit-test success, library counts, provider counts, or Landlock
support with frontier task performance or an independently audited security
claim. Keyless external search is not offline or inherently private. Cloud
models are supported, so capability is not limited to the local model alone.

### Findings to address

- High: `_run_codex_auth_action` and `_run_mcp_enable` invoke synchronous work
  through `run_in_terminal(operation)` without executor offloading. The installed
  Prompt Toolkit defaults to calling that work on its event loop.
- High: `_refresh_choice_filter` resets selection when its query becomes empty;
  `_refresh_resume_choices` replaces displayed rows without updating the canonical
  filtering state. Filters, selected identity, and refresh need one controller.
- High: `MCPRegistry` uses secure atomic replacement, but load/modify/save lacks
  cross-client coordination and can lose competing updates.
- High: MCP schema selection relies on keyword overlap and a six-tool subset;
  unfamiliar names and paraphrases can leave relevant tools undiscoverable.
- Medium: `TurnGovernor` detects progress through normalized result prefixes,
  not validated task outcomes. Its safe-boundary wall-time check is not a deadline
  for an in-flight hung request.
- Medium: the CLI/TUI, agent, and web-provider modules contain respectively
  16,306, 5,707, and 5,528 lines in the reviewed checkout. Overlapping ownership,
  rather than line count alone, is the concern.
- Medium: root `AGENTS.md` is approximately 94 KB while repository instruction
  injection shares a 12,000-character budget. Important later guidance can be
  truncated; split operational guidance and retain accurate bounded status.
- Investigation: MCP settings rebuild the global tool registry while a turn
  may retain selected tool objects. Test and define when disable/reconfigure
  takes effect; do not claim a reproduced execution race without evidence.
- Strategic: worker leases and observer replay do not provide execution that
  survives the owning CLI process. Durable background work remains separate.

### Stage 1: Responsive background jobs and consistent settings

- [x] Give authentication, MCP discovery, catalog refresh, and skill scanning
  explicit cancellable background-job ownership.
- [ ] Keep TUI rendering and state transitions on the UI thread; offload blocking
  work. Cancellation must stop polling and close owned transports/processes,
  not merely abandon a thread's result.
- [x] Use stable option IDs instead of changing display labels as identity.
- [x] Preserve query, selection, scrolling, and preview across asynchronous
  refreshes, settings updates, and Back/Escape navigation.
- [ ] Keep unavailable options highlightable but inert, with a visible reason.
  Enter on no matching results must not accidentally choose Back.
- [x] Coordinate configuration updates through locking or revision-aware writes.

Acceptance gate: terminal tests for slow login/discovery, cancellation, filtered
live refresh, selector preservation, and competing two-client settings updates.
First implementation slice: cancellable authentication/MCP jobs plus the shared
stable-ID picker controller.

#### Execution record: authentication/MCP setup slice, 2026-09-30

Implemented, with mocked regression coverage; **Stage 1 as a whole is not done**:

- Codex login/logout runs off the TUI event loop through the official broker.
  Cooperative cancellation wakes broker message waits, requests device-login
  cancellation, closes the owned process, and drains the worker before returning.
  Device login now has an absolute deadline even under unrelated notifications.
- Setup owns a transient progress/cancel picker and animated elapsed waiting
  footer. Escape, Ctrl+C, the cancel row, and exit request cancellation. Setup
  prevents queued model work from starting and refuses startup during a local
  model turn. Device codes and authorization URLs are not appended to history.
- MCP discovery has an async entry point; cancellation unwinds its transports.
  Settings OAuth uses an async bounded loopback listener with connection cleanup
  and immediate denial feedback. Failed/cancelled initial OAuth removes newly
  acquired credentials without deleting existing credential state.
- MCP enabling writes only after successful discovery; after the network wait it
  reloads configuration and rejects a removed/replaced definition. This mitigates
  stale enable results but is **not** a replacement for cross-process settings
  transactions, which remain planned.
- Added tests for queue gating, timeout feedback, cancellation before startup,
  broker cancellation and absolute deadlines, transient code display, MCP
  success/failure/cancellation/reconfiguration, OAuth credential preservation,
  and callback/listener cleanup.
- Files for this slice: CLI `main.py`, new CLI `setup_jobs.py`, core
  `codex_auth.py` and `mcp_client.py`, corresponding CLI/auth/setup tests, this
  plan, and the implemented-behavior guidance in `AGENTS.md`.

Limitations: no real account login/logout was exercised or credentials changed.
Settings MCP OAuth still uses desktop loopback; SSH/headless users retain
`klaude mcp auth login NAME --manual`. End-to-end terminal latency measurements
and comprehensive modal/job lifecycle coordination remain follow-up work.
Catalog/skill job ownership is not newly unified by this slice.

**Next slice at this checkpoint (completed below):** implement stable option IDs and one picker controller;
cover filter clearing, no-match Enter, asynchronous updates, selection/scroll
preservation, and Back/Escape previews. Then add cross-client settings write
coordination. Do not start durable workers or mutation-capable subagents yet.

Final verification: **635 passed, 1 skipped in 16.89s** in the expanded mocked
regression suite; Ruff passed; production mypy passed for **45 source files**;
`git diff --check` passed. Full unit suite and real login/end-to-end terminal
validation were not run. No commit or push was made.

Validation commands for this slice:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit/test_setup_jobs.py tests/unit/test_codex_auth.py tests/unit/test_mcp_client.py tests/unit/test_cli_commands.py tests/unit/test_model_runtime.py tests/unit/test_transcript_replays.py tests/unit/test_reliability_repair.py
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
git diff --check
```

The expanded mocked suite runs outside the restricted execution sandbox: even a
minimal `asyncio.to_thread` probe completed its thread but stalled at executor
shutdown inside that sandbox. No production authentication is used by tests.

#### Execution record: stable picker identity slice, 2026-09-30

Implemented; **Stage 1 as a whole remains incomplete**:

- Added a pure shared `PickerController` for identity, ranked filtering,
  selection, and viewport state. The CLI adapter assigns stable settings names,
  model references, session IDs, registry names, and authentication-action IDs
  independently from labels and live values.
- Settings toggles retain their highlighted logical row and filter. Live
  session/model/catalog updates reapply the filter and preserve selection;
  clearing filters restores the original selection or a manually chosen match.
- No-match Enter stays in the picker and explains how to recover, rather than
  choosing Back. Unavailable options remain highlightable and inert, retaining
  the typed filter. Explicit Back/Cancel and Escape remain usable.
- Back/Escape restores parent picker state; unchanged permission previews keep
  their scroll position. Viewports preserve the selected row's offset across
  insertions and clamp safely after deletion. Mouse confirmation follows
  option identity rather than a potentially changed screen position.
- Device-code setup rows are not saved in the picker-state cache.
- Files for this slice: new CLI `pickers.py`, CLI `main.py`, new
  `tests/unit/test_pickers.py`, CLI regression tests, `AGENTS.md`, and this plan.

Validation:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_pickers.py tests/unit/test_cli_commands.py -k 'picker or settings or choice or permission or resume'
# 98 passed, 364 deselected in 8.13s
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit/test_pickers.py tests/unit/test_setup_jobs.py tests/unit/test_codex_auth.py tests/unit/test_mcp_client.py tests/unit/test_cli_commands.py tests/unit/test_model_runtime.py tests/unit/test_transcript_replays.py tests/unit/test_reliability_repair.py
# 652 passed, 1 skipped in 18.42s (before the final model-refresh regression)
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit
# 1266 passed, 19 skipped in 38.85s (includes the final model-refresh regression)
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# No issues in 46 source files
git diff --check
# Passed
```

The expanded and full mocked suites ran outside the restricted sandbox for the
executor-shutdown issue documented above. No live credentials were changed.
Existing terminal replay tests passed, but interactive SSH/WSL testing and
measured latency under load were not performed. This slice extracts the picker
controller only; it does not complete the broader typed-modal/job-state refactor.
Existing dirty changes were preserved. No commit or push was made.

**Next slice at this checkpoint (completed below):** inspect every saved-settings writer, add cross-client
locking or revision-aware read/modify/write coordination, and test two clients
changing independent fields plus conflicting changes. Preserve private-secret
file modes and atomic writes. Then revisit unified catalog/skill job ownership
and remaining Stage 1 latency/lifecycle gates before beginning Stage 2.

#### Execution record: cross-client settings coordination, 2026-09-30

Implemented; **Stage 1 remains incomplete**:

- Introduced shared `settings_store.py` transactions with stable owner-only
  Linux advisory locks, bounded 200 ms lock acquisition, scoped updates,
  unique private temporary files, atomic replacement, and file/directory fsync.
  Busy clients receive a retryable error, rather than indefinitely blocking.
- Appearance, model selection, composer, runtime, tools, display, and permission
  writers now change only the explicitly edited fields in the latest document.
  Independent edits merge; the last serialized explicit assignment wins for
  the same field. Presets and resets intentionally replace only their scope.
  Runtime device mode and GPU override commit together. Single permission rows
  no longer save stale policy maps; process-only permission grants stay separate.
- Provider-secret writes lock the complete dotenv read/modify/write operation,
  preserve comments/other keys, and retain mode 0600. Secret values are not
  written to lock files, preferences, or error messages.
- MCP registries retain detached baselines and atomically merge changes to
  different servers. Conflicting edits, deletions, and duplicate additions are
  rejected without replacing newer definitions. Discovery's existing definition
  recheck is now backed by conflict detection at commit. CLI failures are clean,
  and logout does not delete credentials before a conflicting disable fails.
- Scoped Nano editing holds the same lock. Corrupt JSON and symlinked settings
  or locks fail closed; failed publication leaves the original file intact.
  Legacy appearance migration preserves unrelated theme values.
- Added spawned-process concurrency tests and stale-client UI regressions,
  bounded lock contention, private modes, secret preservation, corruption,
  symlink refusal, atomic-write failure cleanup, and MCP conflict feedback.
- Files in this slice: new core `settings_store.py`, core `config.py` and
  `mcp_client.py`, CLI `main.py`, new `tests/unit/test_settings_store.py`,
  `tests/unit/test_cli_commands.py`, `AGENTS.md`, and this plan.

Validation:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_settings_store.py tests/unit/test_config.py tests/unit/test_mcp_client.py tests/unit/test_cli_commands.py -k 'settings or preferences or appearance or registry or permission or secret or runtime or stale or processes or field or lock or invalid or symlink'
# 118 passed, 392 deselected in 7.63s (before final feedback/legacy regressions)
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit
# 1287 passed, 19 skipped in 44.72s (final state; spawned writers, no fork warnings)
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# No issues in 47 source files
git diff --check
# Passed
```

The full suite ran outside the restricted sandbox for the previously documented
async executor-shutdown issue. All configuration tests use temporary files; no
real accounts or stored credentials were changed. Existing dirty work was
preserved, and no commit or push was made.

Limitations: advisory locks require cooperating writers; arbitrary external
editors can ignore them. Separate settings/credential files are not one atomic
transaction. This does not synchronize every running client's in-memory state,
solve simultaneous OAuth token refresh, or reconcile delayed model catalog
cache writes. Synchronous fsync latency and SSH/WSL interaction under load have
not been measured. Linux is the supported canonical implementation.

**Next slice at this checkpoint (completed below):** inventory catalog/skill jobs and their queue/modal/exit
interactions; move them to owned cancellable jobs, reject stale provider results
after key removal or model-provider changes, and publish provider-scoped catalog
updates without losing another client's cache. Add deterministic cancellation,
stale-result, and UI latency tests. Finish Stage 1 acceptance before Stage 2;
do not start durable workers or mutation-capable subagents yet.

#### Execution record: owned catalog/skill jobs, 2026-09-30

Implemented; **Stage 1 remains incomplete**:

- Added a keyed read-only background-job owner for skill inventories, official
  MCP Registry searches, Codex sign-in checks, and cloud-model discovery.
  Fixed-operation subprocesses have bounded deadlines and private JSON IPC;
  cancellation terminates/reaps their process groups rather than abandoning a
  blocked network thread. Exit cancels and drains owned jobs. Superseded results
  cannot change the current picker or replace a secret-input modal.
- Skills reads bounded public manifest metadata without importing the indexing
  stack. Symlinked and oversized manifests are skipped; inventories are capped
  with an explicit truncation notice. Opening/loading and cloud-picker tests
  check responsiveness without slow local model inference.
- Cloud catalog requests snapshot the provider's credential revision and cache
  generation. The worker checks both before publishing a provider-scoped update
  under coordinated locks, including key removal/replacement and same-key ABA
  races. Random revisions contain no secret-derived fingerprints. Discovery
  failures or empty results retain the previous catalog. Logout invalidates only
  that provider. Cloud picker rendering no longer queries the Ollama daemon.
- Model and MCP search-cache writers merge independent updates under the
  private atomic settings writer. Fresh MCP results remain usable if optional
  cache persistence fails. Keys travel through private stdin, never worker argv,
  environment, public events, or logs; errors are normalized before UI delivery.
- Added regressions for process cancellation, timeout, cleanup, stale jobs,
  masked-modal preservation, selector exit, key/cache races, and scoped updates.
  Updated `AGENTS.md` and ignored private credential revision/lock/temp files.

Validation:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit
# 1303 passed, 19 skipped in 43.91s
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_background_jobs.py tests/unit/test_mcp_catalog.py
# 23 passed in 1.18s after the final normalized-error hardening
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# No issues in 49 source files
git diff --check
# Passed
UV_CACHE_DIR=/tmp/klaude-review-uv UV_OFFLINE=1 uv run python scripts/package_smoke.py
# Could not resolve uncached hatchling with network disabled
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run python scripts/package_smoke.py
# Built all five wheels; timed out (exit 124) downloading installation dependencies
```

The full suite used the previously documented outside-sandbox executor-shutdown
workaround. Tests use fake providers and temporary credentials/cache files; the
real subprocess test only reads temporary skill manifests. No live model or
real authentication request was needed. For future live AI validation, use
**OpenRouter Free**, not local models, as requested by the user. Existing dirty
work remains preserved; no commit or push was made.

Packaging limitation: all five wheels built, and direct ZIP inspection confirmed
both new worker modules are present in the CLI wheel. The isolated installation
and installed CLI smoke check did not finish within the dependency-download
timeout; do not treat this as a completed packaging acceptance test.

Limitations: this is not durable work that survives CLI termination. Abrupt
parent SIGKILL, simultaneous OAuth refresh, and changes made directly through
the external Codex CLI are not fully coordinated. Advisory locks do not control
non-cooperating editors. Arbitrary running clients do not auto-reload every
setting. Local model discovery and some status/config paths still need a UI
blocking audit; real SSH/WSL latency and queue/modal interactions under sustained
background load have not yet passed a measured acceptance gate.

**Next slice at this checkpoint (completed in part below):** audit synchronous local-model discovery, status, saved
configuration access, and modal transitions; offload blocking I/O with bounded
ownership where needed. Add terminal-level slow-provider and queue/modal
cancellation tests, including delayed refreshes and unavailable-option reasons.
Measure input/render latency on SSH/WSL where available and report unsupported
environments honestly. Finish Stage 1 acceptance before Stage 2; do not start
durable workers or mutation-capable subagents yet.

#### Execution record: responsive local catalogs and Codex usage, 2026-09-30

Implemented; **Stage 1 remains incomplete**:

- TUI local model discovery now uses an owned fixed-operation worker with an
  eight-second outer deadline and three-second HTTP timeout. It requests only
  Ollama `/api/tags`; it never runs local inference. The picker opens with an
  active-model fallback/loading notice, keeps typed filtering through delayed
  results, and cancels discovery on Back/Escape or a provider switch. Inventory
  results are bounded and control-character names rejected. Empty successful
  catalogs remain honestly empty; failures preserve prior inventory with a
  visible reason and a 30-second retry cooldown.
- Explicit local model names resolve from available snapshots; if local
  discovery has not completed, open a filtered picker without silently changing
  the active model. Reset verifies the configured default against the owned
  inventory, asking the user to retry after discovery rather than blocking the
  UI on a synchronous daemon request.
- TUI `/status` no longer calls the official Codex usage broker synchronously.
  It prints immediately using loading or explicitly aged cached quota data,
  then an owned eight-second job posts the actual public limits separately.
  Results only print into the originating session while it is still on Codex.
  Failed refreshes keep the true age of a previous snapshot and throttle retries;
  authentication changes cancel pending quota jobs and clear the account cache.
  Line-oriented status retains its direct synchronous behavior.
- Confirming an unavailable action remains inert and keeps the picker open,
  but now displays its visible reason rather than silently clearing feedback.
- Added real Prompt Toolkit pipe-input/render coverage: typing filters while
  catalog discovery remains pending, a delayed result preserves that query and
  picks the matching model, and Escape returns to the parent. Additional tests
  cover immediate active-turn status, cross-session quota delivery, retry bounds,
  quota-cache age, local reset, and worker metadata sanitization. These are
  synthetic terminal checks, not measured real SSH/WSL acceptance.

Validation:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_cli_commands.py -k 'local_picker or local_refresh or live_local or codex_status_never or codex_quota_failure or model_reset_waits or unknown_local or quota_refresh_failure or unavailable_model_remains or cancel_during_effort'
# 10 passed, 462 deselected in 2.79s
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_background_jobs.py
# 13 passed in 0.93s
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit
# 1314 passed, 19 skipped in 43.56s
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# No issues in 49 source files
git diff --check
# Passed
```

The full suite again used the documented outside-sandbox executor-shutdown
workaround. Initial new-test failures (a missing constant import and a filter
not initialized for programmatic `/model NAME`) were corrected before the final
green run. Changed files in this slice: CLI `main.py`, `background_worker.py`,
`tests/unit/test_cli_commands.py`, `tests/unit/test_background_jobs.py`,
`AGENTS.md`, and this plan. Existing dirty changes were preserved. No commit or
push was made. Real SSH/WSL measurements and a new installed-wheel smoke test
were not performed in this slice.

No live model calls or real account-limit calls were needed. Local worker tests
mock HTTP `/api/tags`, and account-limit tests mock the official broker. Future
live AI validation must use **OpenRouter Free**, not local inference.

**Next slice at this checkpoint (completed below):** `_set_agent_model` still synchronously loads optional SDKs
and, for Codex, calls `runtime.auth.credentials()` from the TUI selection path.
Prepare/validate the chosen runtime in an owned cancellable operation, then
commit the model switch on the UI thread only when still current; preserve the
previous model on failure/cancellation. Audit filesystem-heavy `/status`
repository-guidance/SQLite reads and settings persistence for UI-thread stalls.
Add delayed-auth/model-selection plus queue/modal cancellation tests. Do not
claim Stage 1 acceptance or begin Stage 2 until those remaining paths and the
terminal latency/lifecycle gates are addressed.

#### Execution record: cancellable cloud-model activation, 2026-09-30

Implemented; **Stage 1 remains incomplete**:

- TUI model selection and explicit cloud `/model NAME` now validate optional
  SDK dependencies and Codex account credentials in a fixed-operation owned
  worker. The worker has a 20-second deadline; the transient setup modal has a
  25-second outer deadline. Escape/Ctrl+C/exit cancel the operation and its
  owned worker group. Pending turns pause during preparation.
- Only a readiness boolean returns through IPC. Access tokens, account IDs,
  SDK objects, and broker responses never enter UI events, transcript, or
  preferences. Temporary validation SDK clients are closed. API-key provider
  preparation verifies dependency/key configuration, not remote API-key validity;
  a first real request can still fail, and no model request is made by validation.
- The active model/runtime remain unchanged until readiness is accepted on the
  UI thread. Changed session/model/key, newly observed remote work, or another
  modal prevents activation. The worker also rejects a saved key removed or
  replaced during preparation. Provider runtimes are constructed lazily after
  validation so SDK imports and credential checks do not reoccur in key handlers.
- Mode/effort cancellation restores the exact previous runtime object and
  reasoning settings rather than calling model activation again. This removes
  a second hidden UI-thread credential check in the rollback path.
- Added mocked coverage for successful setup, expired authentication,
  cancellation, timeout, session/key/modal/remote-state changes, queued turns,
  exact runtime rollback, worker client cleanup, and credential-free results.
  Real Prompt Toolkit pipe-input/render tests exercise Escape and Ctrl+C while
  the preparation future remains pending. `AGENTS.md` describes these boundaries.

Validation:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit/test_cli_commands.py -k 'activation or expired_codex or cancel_during_effort' tests/unit/test_background_jobs.py
# 16 passed, 483 deselected in 3.38s
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit
# 1328 passed, 19 skipped in 51.06s
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# No issues in 49 source files
git diff --check
# Passed
```

The initial restricted-sandbox focused run hit the documented async executor
hang and was interrupted (exit 130); the focused and full runs above completed
outside that sandbox using mocked providers. Changed files in this slice:
CLI `main.py`, `background_worker.py`, `tests/unit/test_cli_commands.py`,
`tests/unit/test_background_jobs.py`, `AGENTS.md`, and this plan.

No real cloud authentication, model request, or paid/free model evaluation was
needed. Future live AI validation continues to use **OpenRouter Free**, not local
inference. Existing dirty changes remain preserved; no commit/push is made.
Installed-wheel verification and measured real SSH/WSL interaction are not part
of this slice.

**Next slice at this checkpoint (completed below):** make TUI `/status` use an immutable snapshot rather than
recomputing repository guidance and modifying injected-guidance fields from a
key handler. Offload slow session/guidance metadata reads with bounded owned
jobs, keeping late results session-scoped and labels honest about actual prompt
injection. Audit settings read/fsync/lock persistence and runtime auto-calibration
for remaining input/render stalls. Add delayed-filesystem and queue/modal tests,
then finish the Stage 1 latency/lifecycle acceptance checklist before Stage 2.
Do not start durable workers or mutation-capable subagents yet.

#### Execution record: snapshot-only status and read-only metadata, 2026-09-30

Implemented; **Stage 1 remains incomplete**:

- Status no longer calls `_repository_instruction_context` or writes injection
  bookkeeping. It formats the latest immutable request's guidance metadata,
  falling back to the last prompt-build snapshot. Newly created/changed files
  are not retroactively labeled injected. Before a snapshot exists, status says
  so; empty snapshots do not invent file-detection evidence. The configuration
  builder records detection/readability only when it actually builds guidance.
- TUI `/status` uses its current session-name hint and cached memory mode,
  never synchronous `session_title`/`auto_memory_enabled` queries. Unknown memory
  mode is explicit. A fixed-operation eight-second job uses a separate read-only
  SQLite connection with a 200ms lock timeout and `query_only`, returning only
  bounded assigned-title and automatic-memory metadata. It does not instantiate
  Memory, migrate storage, read conversation content, or create a missing DB.
  Memory exposes its already-configured DB path for this purpose.
- Metadata results are scoped to session/title and refreshed with a 30-second
  cache. Local memory changes invalidate pending results. A session/title change
  can supersede an older job without waiting for it. Late responses cannot
  overwrite a rename, another session, or a newer memory setting; updates leave
  masked modal contents untouched. Errors are normalized and retries throttled.
- Added no-I/O/no-agent-mutation status regressions, newly created guidance
  coverage, stale metadata/masked-modal tests, read-only bounded-result tests,
  and missing-database safety coverage. The prior status fixture now supplies
  actual injection snapshot evidence instead of merely creating files on disk.

Validation:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_cli_commands.py -k 'status or instruction or configuration or memory_settings' tests/unit/test_background_jobs.py
# 35 passed, 473 deselected in 2.78s (before final cache-scope refinement)
UV_CACHE_DIR=/tmp/klaude-review-uv timeout 60s uv run pytest -q tests/unit
# 1337 passed, 19 skipped in 57.29s (final code)
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# No issues in 49 source files
git diff --check
# Passed
```

Full validation used the established outside-sandbox executor workaround. No
live AI/auth calls were needed; future live tests use **OpenRouter Free**. Files
changed: CLI `main.py`/`background_worker.py`, core `agent.py`/`memory.py`,
`tests/unit/test_cli_commands.py`/`test_background_jobs.py`, `AGENTS.md`, this plan.
Unrelated dirty work was preserved. No commit/push or new installed-wheel test
was performed. Real SSH/WSL latency has not been measured.

Audit findings still open: `_before_render` calls `_sync_shared_session` and
`_refresh_resume_choices` synchronously; `_publish_live_composer` writes SQLite
from rendering. Memory's five-second busy timeout can therefore still stall a
frame despite this status-handler repair. `_settings_categories` also reads
memory/MCP data directly; `_persist_runtime_preferences` performs locked atomic
write/fsync on the UI thread; `_calibrate_runtime` synchronously collects full
runtime context. Do not claim the whole TUI is free of blocking I/O.

**Exact next slice:** coalesce shared-session reads/draft writes into an owned
I/O coordinator and feed render callbacks cached snapshots only. Preserve lease
renewal/cancellation guarantees, per-client drafts, event ordering, and session
scope; prevent stale jobs writing old drafts after a switch. Test SQLite lock
contention and slow storage with responsive pipe-input/render tests. Then move
settings summaries/persistence and hardware-only calibration off the UI thread,
before closing the Stage 1 acceptance checklist or beginning Stage 2.

### Stage 1 execution record: coalesced shared-session I/O (2026-09-30)

Implemented; **Stage 1 remains incomplete**:

- Render polling now submits immutable requests to one owned, lazy session-I/O
  thread. A separate existing-database connection has a 200 ms busy timeout;
  opening it does not run migrations or create missing session storage.
- Only the latest pending request is retained. Lease renewal, public draft/queue
  publication, shared event reads, expired-worker recovery, completed-turn replay,
  and resume-picker badge refresh are serialized in that worker.
- Session changes discard pending old requests and arrange cleanup after old
  in-flight writes, before new-scope publication. UI application rejects stale
  session/turn results and skips already consumed event IDs. Other clients' drafts
  are not overwritten. Secret and modal input is excluded from draft snapshots.
- Lost leases interrupt safely. Twelve seconds without an observed successful
  renewal also cancels the turn rather than continuing past an uncertain lease.
  Storage errors expose a generic retry message without database contents.
- Exit requests cleanup and bounds thread joining to two seconds. An OS-level
  filesystem hang cannot be forcibly killed in this thread design; expired leases
  and client presence remain the recovery boundary. SQLite contention itself is
  bounded and does not block input/rendering.

Validation includes independent connection/busy-timeout checks, coalescing and
scope-cleanup ordering, lock contention followed by recovery, separate-client
drafts, stale-result rejection, secret exclusion, renewal failure, and a running
Prompt Toolkit pipe-input test that accepts and renders text while session I/O
is deliberately blocked. This is not a real SSH/WSL latency benchmark.

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_session_io.py tests/unit/test_cli_commands.py -k 'shared or session_polling or resumed_tuis or remote_worker or session_snapshot or session_lease_timeout or render_submits or coordinator or session_connection or session_io_renewal or sqlite_lock or live_composer_accepts_input'
# 15 passed, 482 deselected in 4.23s
timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit
# 1346 passed, 19 skipped in 56.73s (stable final source snapshot)
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# Success: no issues found in 50 source files
```

Scoped files: `session_io.py`, CLI adapter, `memory.py`, session-I/O and CLI unit
tests, `AGENTS.md`, and this plan. Earlier unrelated changes were preserved;
no commit/push or live model call was performed.
An intermediate full-suite run had one source-inspection failure because a source
file changed during the run; the unchanged-source rerun above passed. The broader
unit suite used approved execution outside the restricted sandbox to avoid the
previous mocked executor-shutdown issue. `git diff --check` also passed.

**Exact next slice:** offload settings summary inventory, saved-setting persistence,
and hardware-only calibration; retain stable selection and make pending/failure
states honest. Audit queued-turn starts and explicit session actions separately:
they still access SQLite synchronously, including dispatch after completion events.
The synchronous session helpers retained for unit/diagnostic adapters are not
called by production render polling. Complete terminal/SSH/WSL latency and
modal/queue lifecycle acceptance before closing Stage 1 or starting Stage 2.

### Stage 1 execution record: hardware-only asynchronous calibration (2026-09-30)

Implemented; **Stage 1 remains incomplete**:

- Auto Calibrate no longer invokes full runtime-context collection from a key
  handler. It submits one fixed-operation, eight-second owned subprocess job;
  cancellation and deadline use the existing process-group termination/reaping
  mechanism. No model loading, inference, network probing, repository inspection,
  location inference, hostname, or general system inventory is needed.
- The hardware collector reads bounded numeric CPU/RAM/VRAM hints, considers CPU
  affinity and root cgroup-v2 CPU/memory limits, and optionally runs one fixed
  `/usr/bin/nvidia-smi` numeric-memory query with a two-second timeout and minimal
  environment. It never looks for a GPU executable in a workspace-controlled PATH.
  The largest GPU's dedicated VRAM is used, not an assumed pooled total.
- Only bounded `num_thread`/`num_ctx` recommendations cross IPC. Validation accepts
  1–16 threads and the existing 8,192–65,536 context presets; other returned keys
  cannot alter runtime settings. Device placement remains Auto.
- A stable-ID Cancel Calibration row and loading hint appear while pending. The
  picker remains filterable and keeps its query and logical selector on completion.
  Back/Escape/Ctrl+C, navigation, runtime changes, session switches, and exit cancel
  or invalidate the request. Session/model/options guards suppress stale results;
  active local or observed work prevents starting/committing calibration.
- Failures preserve existing options and display an honest retryable error.
  Successful calibration is labeled a hardware heuristic, not a model-fit test.
  Applying it still uses the scoped atomic settings writer synchronously; that
  remaining persistence latency is not hidden by this repair.

Validation:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_runtime_calibration.py tests/unit/test_cli_commands.py -k 'calibration or runtime_settings'
# 23 passed, 490 deselected in 2.26s
timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit
# 1366 passed, 19 skipped in 54.63s
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# Success: no issues found in 51 source files
git diff --check
# Passed
```

Scoped files: core `runtime_calibration.py`, fixed-operation background worker,
CLI adapter, calibration/CLI tests, `AGENTS.md`, and this plan. Unrelated dirty
changes were preserved. No commit/push or live model request was performed.

Limitations: unsupported/non-Linux GPU inventory can remain unknown; nested
cgroup hierarchies and cgroup-v1 limits are not fully modeled. Numeric capacity
does not establish current model KV-cache/weight fit or detect placement failure.
There is no real SSH/WSL latency measurement or live-model-fit evaluation in this
slice. Low-resource fallback remains bounded and users can override recommendations.

**Exact next slice:** make `_settings_categories` use owned/cached memory and MCP
inventory snapshots with loading/failure feedback instead of synchronous reads.
Then serialize saved-setting writes off the UI thread, preserving scoped merge,
cross-client locking, immediate effective state, and truthful pending/failure status.
Audit synchronous queued-turn starts/session actions afterward; finish terminal,
SSH/WSL and modal/queue acceptance gates before closing Stage 1 or starting Stage 2.

### Stage 1 execution record: asynchronous Settings overview (2026-09-30)

Implemented; **Stage 1 remains incomplete**:

- `_settings_categories` renders pure cached state instead of calling the memory
  database or loading MCP configuration. Opening/refreshing the real overview
  starts one fixed-operation, cancellable eight-second subprocess job.
- The worker reads only the automatic-memory setting through a 200 ms read-only
  SQLite connection and the existing bounded MCP registry loader. It neither
  initializes/migrates missing storage nor connects to, enables, or executes MCP
  servers. IPC contains only a boolean and enabled/total counts, never definitions,
  arguments, credentials, tool schemas, server names, or conversation content.
- A pure `SettingsOverviewSnapshot` holds independent field values, successful
  timestamps, and failure state. One field can succeed while the other is
  unavailable. Failed refreshes retain each successful field's true age instead
  of making old data appear newly loaded; initial failures remain unknown.
- The UI shows loading, unavailable, and aged cached/refreshing states. Successes
  and failed attempts are cached/throttled for 30 seconds. A cheap render-time
  check schedules refresh when an open overview expires, without filesystem or
  SQLite work on the UI thread. Refresh preserves stable selection and query.
- Leaving the page cancels pending work. Memory/MCP edits invalidate inventory;
  successful local memory changes update the known snapshot immediately. Session
  and storage-path guards prevent old results replacing a newer source's state.
  Unavailable inventory does not disable the category's setup/navigation page.

Validation covers pure state/age semantics, malformed and partial worker results,
read-only missing/symlinked/corrupt storage, SQLite lock contention, no MCP execution,
private metadata exclusion, a real owned-worker run, cache expiry/throttling,
navigation/cancellation/source changes, selector preservation, and live pipe-input
filtering while the read is pending. No live model request was required.

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_settings_overview.py tests/unit/test_cli_commands.py -k 'settings or picker_redraws'
# 58 passed, 467 deselected in 5.84s
timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit
# 1388 passed, 19 skipped in 50.50s (overview checkpoint)
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
git diff --check
```

Scoped files: `settings_overview.py`, fixed-operation worker, CLI adapter,
overview/CLI tests, `AGENTS.md`, and this plan. Earlier dirty changes were preserved;
no commit/push or production session mutation was performed.

**Exact next slice:** serialize saved-setting writes off the UI thread, maintaining
the existing field-scoped merges and cross-client locking. Keep effective runtime
changes immediate, make pending/saved/failed persistence truthful, and do not
claim that cancellation undoes a write which already committed. Inventory remaining
category-detail reads (Memory, MCP, Tools, cloud caches) and queued-turn/session
dispatch afterward. Real SSH/WSL latency and modal/queue lifecycle acceptance
remain open. Do not close Stage 1 or begin Stage 2 yet.

### Stage 1 execution record: serialized runtime preference saves (2026-09-30)

Implemented; **Stage 1 remains incomplete**:

- Runtime preference assignments/deletions now submit field-scoped intent to one
  serialized writer. The UI never takes the settings lock or waits for atomic
  write/fsync in `_persist_runtime_preferences`. Effective options update at once.
- Pending fields coalesce, keeping the latest value per field. In-flight writes
  finish before subsequent writes; existing cross-client locking and private
  atomic publication remain unchanged. Other model/preference fields are preserved.
- Revision-scoped acknowledgements prevent an older failure/success replacing
  newer pending state. The runtime picker exposes saving/saved/unconfirmed feedback
  while preserving selection/filtering. Failure details are generic, not raw paths
  or diagnostics. Unconfirmed options remain active for the current chat.
- Failed intent is retained for the next explicit save, merged below newer values;
  no infinite retry loop runs. Navigation/session changes do not cancel accepted
  saves. Shutdown drains accepted work for at most two seconds and warns if final
  persistence is unconfirmed. An OS-level filesystem hang cannot be killed safely
  in this thread design; cancellation never implies rollback after publication.
- The runtime-preferences Nano editor is unavailable while a save is pending,
  preventing a concurrent editor from racing this client's older write intent.

Tests cover controlled slow saves, coalescing and ordering, failed intent recovery,
draining/closed-submission behavior, unconfirmed publication, concurrent independent
client fields, non-blocking UI submission, stale acknowledgements, editor gating,
and a live picker accepting/filtering input while its real writer is blocked.

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_settings_writer.py tests/unit/test_cli_commands.py -k 'runtime or calibration or competing or settings_writer or failed_settings or close_drains or two_settings or close_reports'
# 37 passed, 484 deselected in 3.21s
timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit
# 1396 passed, 19 skipped in 55.68s (overview and runtime writer final snapshot)
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# Success: no issues found in 53 source files
git diff --check
# Passed
```

Scoped files: `settings_writer.py`, CLI adapter, writer/CLI tests, `AGENTS.md`,
and this plan. Existing tests retain an immediate writer adapter; dedicated worker
and pipe-input tests exercise the asynchronous production implementation.
Unrelated dirty changes were preserved; no live model calls or commit/push.

**Exact next slice:** inventory remaining appearance/composer, permission, and
tool-preference writers and move their scoped updates onto the serialized writer.
Their UI state must remain authoritative while saves are pending: do not reread
old on-disk preferences and accidentally undo an unsaved toggle. Preserve MCP CAS
and secret-entry trust boundaries instead of indiscriminately moving all mutations
into one generic job. Category-detail reads and synchronous queued-turn/session
actions remain separate open work. Finish terminal/SSH/WSL and modal/queue gates
before closing Stage 1 or starting Stage 2.

### Stage 1 execution record: permission/composer saves and ordered resets (2026-09-30)

Implemented; **Stage 1 remains incomplete**:

- Composer-mode changes, permission presets, individual tool-policy cycles, and
  permission resets now update authoritative live state immediately and submit
  only scoped intent to the existing serialized writer. Turn-limit and subagent
  worker resets also use it, removing their special synchronous writes.
- Permission toggles read the live gate, not stale on-disk preferences while a
  save is pending. Saving/saved/unconfirmed feedback preserves selector/query;
  failed persistence leaves the user's explicit current-process choice effective.
- Runtime/composer/permission changes share one acknowledgement revision. Older
  completions cannot clear newer pending state. Confirmed writer transactions
  return bounded valid permission metadata, preserving cross-client merges on
  the UI thread without exposing arbitrary stored preferences/private values.
  Unknown tools and stale acknowledgements cannot change the gate.
- Coalescing now preserves parent/child chronology: reset then edit recreates the
  requested child, while edit then reset removes the override. New parent presets
  supersede prior child edits. Mutable preset maps are frozen before dispatch;
  retained failed intent merges below newer user intent with the same ordering.
- Process-lifetime `always` remains in memory only. Explicit permission settings
  changes keep their existing grant-reset behavior; acknowledgement refresh never
  clears/persists those grants. Workspace, dirty-tree, plan-mode, command, and
  transport hard constraints are unchanged.

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_settings_writer.py tests/unit/test_cli_commands.py -k 'permission or composer or runtime or coalescing or writer'
# 102 passed, 428 deselected in 6.25s
timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit
# 1405 passed, 19 skipped in 51.98s
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# Success: no issues found in 53 source files
git diff --check
# Passed
```

Tests include reset/preset/child ordering, immutable input, private-field exclusion
from acknowledgements, live pending policy cycles, merged two-client permissions,
stale acknowledgement suppression, process-grant preservation, and a real busy
settings lock with responsive composer submission and visible unconfirmed save.
The old busy-composer regression was updated deliberately: effective mode now
changes immediately even when persistence is unavailable.

Scoped files: writer, CLI adapter, writer/CLI tests, `AGENTS.md`, and this plan.
No live models, production session changes, commit, or push. Unrelated dirty work
was preserved; subprocess/thread shutdown limitations remain as documented.

**Exact next slice:** move appearance saves with legacy-theme migration onto an
owned serialized writer for their separate file. Then move Tools preferences,
first replacing disk-backed toggle reads with authoritative UI snapshots so
pending writes cannot undo another toggle. Model preference saves, category-detail
reads, and explicit session/queued-turn actions still need audit. Keep MCP CAS and
credential storage as separate trust boundaries. Complete terminal/SSH/WSL and
modal/queue acceptance before closing Stage 1 or starting Stage 2.

### Stage 1 execution record: asynchronous appearance saves (2026-09-30)

Theme, border, input-height, and appearance resets now enqueue immutable scoped
changes on a separate owned writer for `appearance.json`. Live styling applies
immediately; the transcript explicitly says applied/saving, and Theme/Input Field
pages show saving/saved/unconfirmed feedback. Legacy flat-theme migration runs
inside the atomic cross-client update lock, preserving unrelated content. Old
acknowledgements cannot override newer save state, reset filters/selections, or
change current appearance/permission values. Navigation does not cancel accepted
writes. Exit drains each writer for at most two seconds and reports uncertainty;
kernel-blocked threads remain a documented limitation, not a cancellation claim.

Focused coverage includes a live input picker while its real writer is deliberately
blocked, stale/failed acknowledgements, independent preference revisions, legacy
migration, private publication, and scoped cross-client merges.

Validation:

- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_settings_writer.py tests/unit/test_cli_commands.py -k 'appearance or theme or input_height or input_field or settings_writer'`
  — **51 passed, 482 deselected in 2.67s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,408 passed, 19 skipped in 52.34s** (normal subprocess teardown outside
  the restricted sandbox; offline tests, no live provider calls).
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **53 source files**.
- `git diff --check` — passed.

Scoped files: CLI adapter, settings writer, their two unit-test modules,
`AGENTS.md`, and this plan. No commit/push, live model calls, or production
session changes; unrelated dirty work was preserved.

**Exact next slice:** Tools preferences. Replace disk-backed toggle reads with
authoritative UI snapshots before moving their writes onto the preferences writer;
otherwise a rapid second toggle can restore stale values. Model preference saves,
category-detail reads, explicit session/queued-turn actions, and terminal/SSH/WSL
modal acceptance still remain. Keep MCP CAS and credential storage as separate
trust boundaries. Stage 1 remains incomplete; do not start Stage 2 yet.

### Stage 1 execution record: asynchronous Tools preferences (2026-09-30)

Tools pages and actions no longer reread saved preferences or write synchronously.
Validation, research-tool availability, web-provider availability, and activity
updates use UI-owned snapshots and apply immediately. Scoped changes enter the
existing serialized preferences writer; reset uses ordered whole-section changes,
so rapid toggles and reset-then-edit cannot reuse stale disk values. Only the latest
revision acknowledges persistence and merges sanitized, bounded boolean metadata
from the cross-client atomic save. Other clients' unrelated saved fields survive;
unknown keys/non-boolean values cannot enable tools. Existing external disabled
tools remain disabled. Failed saves leave live choices active, retain intent, and
show unconfirmed feedback without resetting picker focus/filtering.

A live input test also exposed that the global `y`/`n`/`a` insertion handlers did
not refresh picker filtering. They now refresh when a picker is open; permission
responses still require Enter and their invocation/process semantics are unchanged.

Focused regressions cover repeated pending toggles in every Tools group, resets,
stale/failed acknowledgements, cross-client merged state, metadata privacy/bounds,
and a real Tools picker while its writer is deliberately blocked. No live model
calls, production session changes, commit, or push; unrelated dirty work preserved.

Validation:

- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_cli_commands.py tests/unit/test_settings_writer.py -k 'tool or live_picker or writer'`
  — **71 passed, 466 deselected in 3.35s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,412 passed, 19 skipped in 55.60s** (offline regression suite with normal
  subprocess teardown outside the restricted sandbox).
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **53 production source files**.
- `git diff --check` — passed.

**Exact next slice:** model-selection preference persistence. Audit the selection,
mode/effort, cancellation, and rollback paths before moving saves onto the shared
writer; success must retain history and cancellation must retain the prior runtime.
Then handle remaining category-detail reads and explicit session/queued-turn I/O,
and finish terminal/SSH/WSL modal/queue acceptance. MCP CAS and secret storage remain
separate trust boundaries. Stage 1 remains open; Stage 2 has not started.

### Stage 1 execution record: asynchronous remembered-model saves (2026-09-30)

Confirmed TUI model selections enqueue only the canonical `last_model` field on
the shared serialized preferences writer. Styling/runtime/history changes do not
wait for disk publication, and Settings' Models summary reports saving/saved/
unconfirmed state while retaining its filter and selector. Old acknowledgements
cannot overwrite newer save state. Unconfirmed saves keep the selected runtime
and history; failed intent participates in the writer's next explicit save. Mode
and effort remain session-only, and startup/line-oriented compatibility saves
remain synchronous outside TUI key handlers.

Cancellation audit found a real mode-picker defect: its cancel row reached the
mode handler before the generic cancellation handler, finalizing the new model.
Cancel now restores the exact prior runtime and reasoning state with no preference
save, matching effort cancellation. Regressions cover both paths, preserved
conversation history, scoped pending saves, failed/stale acknowledgements,
mode-only behavior, and the real settings picker under deliberately blocked
model-preference storage.

Validation:

- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_cli_commands.py tests/unit/test_settings_writer.py -k 'model or reasoning or cloud_activation or live_picker or writer'`
  — **63 passed, 478 deselected in 6.48s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,416 passed, 19 skipped in 53.40s**, offline with normal subprocess
  cleanup outside the restricted sandbox.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **53 production source files**.
- `git diff --check` — passed.

Scoped files: CLI adapter, CLI regression tests, `AGENTS.md`, and this plan.
No live models, production session changes, commit, or push; unrelated worktree
changes preserved.

**Exact next slice:** remove synchronous session-setting history/event writes from
`_finish_reasoning_selection` using an owned ordered session action lane. These
writes still occur in the selection handler; this slice does not claim fully
nonblocking model completion. Actions must drain rather than be coalesced away,
remain scoped to their originating session across navigation, and report partial/
unconfirmed publication honestly. Then audit Memory/MCP detail reads and remaining
explicit session/queued-turn I/O, followed by terminal/SSH/WSL modal acceptance.
Preserve secret/MCP trust boundaries. Stage 1 remains open; Stage 2 has not started.

### Stage 1 execution record: ordered session-setting writes (2026-09-30)

`_finish_reasoning_selection` no longer writes SQLite or publishes shared events
on the UI thread. It submits a frozen public update to an owned serialized session
action writer using an independent existing-database connection with a 200ms busy
timeout. `Memory.record_session_update` commits the history row and observer event
in one transaction, preventing a durable half-update. Actions retain originating
session/client scope, stay ordered across navigation, are not coalesced, and drain
on close subject to a two-second join. The queue is bounded to 128 pending updates
and details to 2,048 characters. Rejection, unavailable storage, lock failures,
and unconfirmed shutdown are reported without exposing raw database errors or
rolling back the active model. There are no blind retries after publication.

Tests cover atomic rollback with an injected event failure, ordered multi-session
writes through shutdown, a real blocked SQLite writer with responsive picker input,
locked/missing storage, bounded queue rejection, and original-scope failure notices.
The lane orders only its setting updates; other workers' model events may interleave.
It does not implement a universal session lifecycle contract or migrate every
explicit session action. Kernel-blocked filesystem threads remain unkillable.

Validation:

- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_session_actions.py tests/unit/test_cli_commands.py -k 'model or reasoning or session_setting or action'`
  — **44 passed, 491 deselected in 5.43s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,423 passed, 19 skipped in 57.01s**, offline with normal subprocess/thread
  teardown outside the restricted sandbox.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **54 production source files**.
- `git diff --check` — passed.

Scoped files: new CLI `session_actions.py`, CLI adapter, core memory transaction,
new session-action tests, CLI regression tests, `AGENTS.md`, and this plan.

**Exact next slice:** Memory category detail reads and toggles. Use an owned bounded
read-only inventory job for facts/status, show honest loading/cached/error states,
and make the automatic-memory toggle use a live snapshot with an ordered write
operation rather than synchronous SQLite reads/writes. Keep late results scoped,
filters/selection stable, and failed persistence explicit. Then audit MCP details,
remaining explicit session/queued-turn actions, and terminal/SSH/WSL modal gates.
Stage 1 remains open. No Stage 2 work, live model calls, production session changes,
commit, or push; unrelated dirty work is preserved.

### Stage 1 execution record: asynchronous Memory settings (2026-09-30)

Memory opens without file/SQLite reads, using loading or a 30-second cached
inventory. Its eight-second owned read-only job accesses only existing storage,
uses a 200ms SQLite busy timeout, rejects symlink/non-regular/over-1-MiB fact files,
and returns a count plus up to eight sanitized 120-character facts. Detected
sensitive facts stay out of the returned preview, with an explicit hidden count.
Errors retain the true cache age, leave unknown toggles focusable but inert, and
retry after Back/reopen. Navigation cancels the job; session/path/revision checks
drop stale results.

Automatic-memory toggle/reset and TUI `/memory on|off` now apply process-local
intent immediately and submit revision-tagged fixed writes to the ordered action
lane. Rapid changes never read stale SQLite state. Only the latest acknowledgement
can clear the process override or show saved/unconfirmed state. Failed/rejected
writes keep current intent active and visibly unconfirmed; they are not claimed
persistent. Late inventory/status/overview reads cannot undo pending or failed
intent. Filters and logical selection survive refresh. Writes retain the lane's
128-pending bound, 200ms busy timeout, ordered drain and two-second exit join.

Regressions cover read bounds and sensitive-data filtering, a real owned inventory
worker, ordered toggles, live input while a write is blocked, stale/failed/cache
results, reset, no key-handler memory I/O, and process-override semantics.

Validation:

- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_memory_inventory.py tests/unit/test_session_actions.py tests/unit/test_background_jobs.py tests/unit/test_cli_commands.py -k 'memory or action or settings_picker_responds'`
  — **39 passed, 526 deselected in 6.18s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,433 passed, 19 skipped in 56.27s**, final rerun after acknowledgement-time
  stale-read invalidation; offline outside the restricted sandbox for teardown.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **55 production source files**.
- `git diff --check` — passed.

**Exact next slice:** MCP category/detail inventory. Remove synchronous registry
loads from navigation/rendering, using bounded owned read-only metadata jobs and
honest cache/error states while retaining stable selection/filtering. Preserve
definition identity/CAS revalidation for enabling, disable-before-execution import
rules, OAuth/secret handling, and explicit trust confirmations. Then audit remaining
session/queue actions and bare `/memory`/`/skills` direct reads before terminal/
SSH/WSL modal acceptance. Stage 1 remains open; Stage 2 has not started.

Scoped files: CLI Memory inventory module/worker/adapter, core process override,
session action extension, four test modules, `AGENTS.md`, and this plan. No live
models, production session changes, commit, or push; unrelated dirty work preserved.

### Stage 1 execution record: asynchronous MCP inventory/navigation (2026-09-30)

MCP settings and public Registry detail pages no longer synchronously load saved
definitions. An owned eight-second read-only job reads at most 16 MB of regular,
non-symlink configuration, validates definitions with the existing parser, and
returns at most 1,000 metadata rows. Only names, enabled state, transport, OAuth
flag, and tool counts cross IPC; private endpoints, arguments, env/header values,
credential references, and schemas stay in the worker. The job never connects,
discovers, executes, writes configuration, or touches auth storage.

Snapshots cache for 30 seconds with visible true age. Failed reads retain the
previous snapshot/age and show a neutral unavailable message; Back/reopen retries.
Navigation cancels reads, guards session/path/job identities, and retains picker
filter/logical selection. Related settings/detail navigation can share its read
without cancelling it mid-transition. Successful mutations/reload invalidate the
cache. Registry install choices stay focusable but inert until configured-name
inventory is known and complete; truncated previews explain the CLI alternative.
Actual install/enable checks still use current registry definitions and existing
CAS behavior; metadata is not execution authorization.

Regressions cover private metadata only, a real owned worker, missing/malformed/
symlink/FIFO/oversized config, the explicit server ceiling, responsive live input,
cache age/failure, cancellation, and installation gating for unknown/truncated
inventories. No live providers/MCP connections, production session changes, commit,
or push; unrelated worktree changes preserved.

Validation:

- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_mcp_inventory.py tests/unit/test_background_jobs.py tests/unit/test_cli_commands.py -k 'mcp'`
  — **23 passed, 541 deselected in 4.46s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,443 passed, 19 skipped in 58.43s**, offline outside the restricted sandbox
  for normal subprocess/thread teardown.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **56 production source files**.
- `git diff --check` — passed.

**Exact next slice:** MCP mutation/enable preflight. Selecting existing-server
toggles, add/import/install saves, `_reload_mcp_tools`, and registry reads inside
the asynchronous setup coroutine still perform local I/O on the UI event loop.
Move these fixed operations off-thread with owned bounded setup/action handling;
bind the trust preview/confirmation to an exact definition fingerprint and recheck
it before connecting as well as before CAS publication. Preserve disabled imports,
duplicate checks, secret/OAuth isolation, and the user's previous active tools on
failure/cancellation. Do not execute from cached inventory or treat cancelling an
accepted mutation as rollback. Then audit remaining session/queue actions and
direct inventory commands before terminal/SSH/WSL acceptance. Stage 1 remains open;
Stage 2 has not started.

Scoped files: MCP inventory module/worker/CLI adapter, three test modules,
`AGENTS.md`, and this plan.

### Stage 1 execution record: exact-definition MCP review/enable preflight (2026-09-30)

Selecting a cached disabled server without discovered tools now starts an owned
eight-second definition-review process, not a key-handler registry read. The
transient confirmation includes an opaque SHA-256 digest binding the complete
effective server definition. HTTP previews show origin only; paths/queries and
stdio arguments stay private, with an explicit configuration-file review hint.
Late/cancelled/session-or-path-changed review results cannot open confirmation.

Enable performs its initial live read off the UI thread and checks the confirmed
digest before discovery/OAuth, so changing the server between review and Enter
does not authorize a different endpoint/command. Existing post-discovery equality
and CAS publication remain intact. Registry reads now open no-follow/nonblocking
descriptors, reject non-regular files (including FIFOs), and enforce the byte bound
while reading, closing size-check/read races without weakening normal validation.
The enable preflight uses a read-only thread; cancelled results cannot initiate
discovery, but kernel-blocked filesystem threads cannot be forcibly stopped.

Coverage includes digest sensitivity without private-field disclosure, safe HTTP
previews, a real owned review worker, no UI registry read for the cached review
path, cancelled late reviews, changed-definition rejection before discovery,
normal-registry FIFO rejection, and existing OAuth cancellation/CAS regressions.
The initial restricted focused run stalled during executor teardown and was
interrupted; the normal-teardown offline focused run passed. No live MCP/provider
requests, production data changes, commit, or push; unrelated dirty work preserved.

Validation:

- `timeout 45s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_background_jobs.py tests/unit/test_cli_commands.py tests/unit/test_mcp_client.py tests/unit/test_mcp_inventory.py -k 'mcp'`
  — **50 passed, 541 deselected in 5.33s**, offline normal-thread teardown.
- Initial `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1 failed, 1,449 passed, 19 skipped in 63.57s**. The unchanged concurrent-secret
  test hit `EBUSY` at the existing 200ms lock boundary under contention.
- `timeout 20s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_settings_store.py -k 'concurrent_secrets_preserve_comments_other_keys_and_private_mode'`
  — **1 passed, 14 deselected in 1.44s**. No lock deadline or unrelated test changes.
- Full-suite rerun with the same command — **1,450 passed, 19 skipped in 60.55s**.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .` — all checks passed.
- `UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **56 production source files**.
- `git diff --check` — passed.

**Exact next slice:** MCP fixed mutation lane. Cached/discovered-server toggles,
add/import/install saves, post-discovery publication, `_reload_mcp_tools`, and the
uncached/stale-selection fallback still perform local I/O on the UI loop. Move
fixed operations into owned ordered work with definition CAS/revalidation, bounded
backpressure, acknowledged publication, and explicit outcome-unknown handling.
Never treat cancellation of an accepted write as rollback or update live tools
from stale definitions. Preserve disabled imports, duplicate checks, OAuth/secret
boundaries, history, and previous live tools on failed/cancelled pre-publication
work. Then finish the session/queue/direct-inventory audit and terminal/SSH/WSL
acceptance. Stage 1 remains open; Stage 2 has not started.

Scoped files: MCP read/review module and worker, CLI adapter, core bounded registry
reader, three changed regression-test modules, `AGENTS.md`, and this plan.
The existing MCP-client regression module was also run without changing it.

### Stage 1 execution record: off-thread post-discovery MCP publication (2026-09-30)

Continued the mutation boundary work without starting Stage 2. After successful
discovery, definition revalidation, registry CAS save, and replacement tool
preparation now run in owned off-thread setup work. The setup boundary remains
owned until an accepted save returns, pausing queued turns. Late cancellation
reports the real saved outcome instead of implying rollback; save rejection
never reports enable success. A completed save followed by catalog-preparation
failure reports saved configuration and retains previous live tools with an
explicit reload/restart instruction.

Prepared catalogs publish on the UI thread without file I/O, only in the original
session/config scope. Publication preserves local tools and explicit permission
overrides. Standalone reload also prepares the replacement before changing the
existing mapping, so malformed configuration cannot silently delete live tools.
No secrets or OAuth payloads are added to public results; no live transport is
opened during catalog construction. Existing definition review, CAS, disabled
imports, and explicit enable boundaries remain in place.

Regression coverage includes UI responsiveness while save blocks, late-cancel
success and save rejection, changed-session suppression, catalog failure after
successful persistence, reload failure preserving tools, and local-tool/permission
preservation. The first focused run found two test-fixture mistakes (FakeAgent
does not initially provide a tools mapping); these were corrected before the
final full run. No production provider calls, data changes, commit, or push.

Validation:

- `timeout 45s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_cli_commands.py tests/unit/test_background_jobs.py tests/unit/test_mcp_client.py tests/unit/test_mcp_inventory.py -k mcp`
  — **56 passed, 541 deselected in 4.68s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,456 passed, 19 skipped in 62.78s**.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .`
  — all checks passed.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **56 production source files**.
- `git diff --check` — passed.

**Exact next slice:** consolidate MCP writes in a fixed, ordered, bounded mutation
lane with accepted-write acknowledgements. Cached/discovered toggles,
add/import/install saves, standalone tool reload, and uncached/stale-selection
fallback still perform synchronous local I/O. Post-discovery publication is now
off-thread but drains its accepted filesystem worker: a kernel I/O stall can
delay cancellation/exit beyond the setup deadline. Add bounded waiting and
late-result/outcome-unknown ownership rather than pretending a timed-out write
rolled back. Preserve CAS and avoid stale catalog publication. Then finish
session/queue/direct-inventory and terminal/SSH/WSL acceptance. Stage 1 remains
open; Stage 2 has not started.

Scoped files for this slice: CLI adapter, CLI regression tests, `AGENTS.md`, and
this plan. All unrelated worktree changes preserved.

### Stage 1 execution record: ordered cached-MCP toggle writes (2026-09-30)

Added a fixed MCP mutation lane, initially supporting explicit enabled-state
changes to previously discovered definitions. Its immutable requests carry the
originating session and an opaque SHA-256 identity, never raw credentials. The
worker re-reads and validates that identity, preserves registry CAS merging, and
constructs replacement tools from the fresh merged saved configuration without
connecting. Unknown/old settings metadata now starts an asynchronous inventory
refresh instead of falling through to a synchronous registry read.

The lane admits at most 16 active/pending writes; the TUI admits one at a time,
so repeated Enter cannot reverse intent based on an unchanged cached row.
Accepted writes remain owned when users navigate away. After eight seconds the
UI reports pending/outcome-unknown rather than rollback and still processes the
late acknowledgement. Shutdown waits at most two seconds and visibly warns if
the accepted lane has not drained. Save exceptions after entering publication
are conservatively unconfirmed, never automatically retried. Catalog-building
failure after a completed save acknowledges persistence while preserving the
old mapping. No private exception strings are returned to the UI.

Queued model work pauses until acknowledgement and remains held if persistence
or the effective tool catalog is unconfirmed. This prevents continuing with a
tool that a possibly completed save disabled. Verified current publication or
restart reconciles that hold. Session/config-stale acknowledgements cannot
publish catalogs or reopen unrelated pickers; current acknowledgements preserve
the settings row. Add/import/install paths reject overlapping accepted toggles
but have not yet moved to this lane.

Validation:

- `timeout 45s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_mcp_mutations.py tests/unit/test_mcp_inventory.py tests/unit/test_background_jobs.py tests/unit/test_cli_commands.py tests/unit/test_mcp_client.py -k mcp`
  — **68 passed, 541 deselected in 6.51s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,468 passed, 19 skipped in 62.86s**.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .`
  — all checks passed after final formatting.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **57 production source files**.
- `git diff --check` — passed.

Initial focused runs found fixture-only errors: a registry replacement lacked
its CAS baseline, an inventory assertion lacked the new digest, and a Config
property was incorrectly treated as assignable. Corrected the fixtures without
weakening product safeguards. Coverage includes ordering, stale rejection,
post-save exceptions, catalog failure, backpressure, bounded shutdown waiting,
late acknowledgement, duplicate input, and session-scope suppression. No live
provider calls, production configuration writes, commit, or push. Unrelated
dirty worktree changes preserved.

**Exact next slice:** extend this fixed lane to post-discovery publication first,
replacing its unbounded cancellation drain with bounded waiting plus retained
late-result ownership. Then move add/import/install saves and standalone reload
into fixed operations, preserving secret-composer boundaries, disabled imports,
duplicate checks, and existing live tools. Reconcile unknown outcomes through a
verified catalog read rather than blind retry. Finish the explicit session/queue
and terminal/SSH/WSL acceptance audit afterward. Stage 1 remains open; Stage 2
has not started.

Scoped files: new mutation lane and tests, MCP inventory/worker tests, CLI
adapter/regression tests, `AGENTS.md`, and this plan.

### Stage 1 execution record: discovery-to-mutation handoff (2026-10-01)

Moved discovered-server enable publication into the same fixed ordered lane as
cached toggles. Cancellable setup now completes discovery and captures a private,
immutable, bounded JSON schema snapshot, checks cancellation and originating
scope again, then submits an explicit enable request. After acceptance there is
no filesystem worker awaited by setup: the lane owns CAS publication and emits
its acknowledgement. The initial transcript states discovery complete/save
pending; only the saved acknowledgement emits enable success. MCP settings show
an accepted-save hint while publication is outstanding.

The lane validates discovery payload structure, object schemas, the 128-tool
ceiling, and per-tool/aggregate bounds. Full original-definition identity remains
required, so changes during discovery reject publication without enabling the
replacement. Enable and toggle requests share ordering, backpressure, two-second
shutdown waiting, and late-result handling. Private schema snapshots and prepared
catalogs are excluded from request/result reprs. Unknown persistence or a failed
catalog still holds queued work; stale-scope acknowledgements never replace live
tools. Existing OAuth/discovery cancellation and credential cleanup remain intact.

Also closed a related storage boundary: registry save checks the exact merged,
formatted encoded payload under its existing lock before atomic replacement.
It refuses output larger than the read-byte ceiling, retaining the old readable
file even when concurrent additions or a large discovery would exceed it.

Validation:

- `timeout 45s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_mcp_mutations.py tests/unit/test_mcp_inventory.py tests/unit/test_background_jobs.py tests/unit/test_cli_commands.py tests/unit/test_mcp_client.py -k mcp`
  — **73 passed, 541 deselected in 6.01s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,473 passed, 19 skipped in 62.08s**.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .`
  — all checks passed.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **57 production source files**.
- `git diff --check` — passed.

Tests exercise mixed enable/toggle ordering, immutable capture, malformed schema
rejection, storage-limit preservation, setup completing while save is blocked,
late success/failure/session-stale results, and existing OAuth/discovery/CAS
regressions. No live services, production configuration writes, commit, or push;
unrelated dirty worktree changes preserved.

**Exact next slice:** add/import/install saves and verified catalog reloads as
fixed lane operations. Keep secret collection/storage separate, imports disabled,
duplicates rejected, trust confirmation explicit, and accepted-write outcomes
honest. Add a verified read-only reconciliation operation for unknown catalogs,
so recovery need not require restart or a new toggle. Then finish the explicit
session/queue/direct-inventory and terminal/SSH/WSL acceptance audit. Stage 1
remains open; Stage 2 has not started. Read-only preflight/OAuth credential file
access still has thread/local-I/O limitations; this slice removes the accepted
publication drain, not every remaining filesystem path. A daemon write can
remain stalled or be cut short by process exit; report unconfirmed, never rollback.

Scoped files: mutation lane, CLI adapter, core registry save bound, their
regression tests, `AGENTS.md`, and this plan.

### Stage 1 execution record: verified reload recovery and disabled installs (2026-10-01)

Added a visible `Reload configured MCP tools` settings action backed by a fixed
read-only operation in the ordered lane. It loads bounded configuration,
prepares cached tools without connecting, then verifies full definition digests
against a second read. Changes during preparation reject the snapshot. A
successful current acknowledgement publishes the catalog, clears the uncertain
catalog queue hold, and reconciles the lane's prior save uncertainty without
rewriting configuration or forcing another toggle. Failed or stale reload keeps
the existing tools and any hold. Outstanding reloads have distinct read-only
progress text; acknowledgements preserve the user's currently highlighted row.

Registry install plans that need no secret input now submit private immutable
definitions to a fixed disabled-add operation, rather than doing registry I/O
in the selection handler. The worker validates, rejects duplicates, forces
disabled state, discards any supplied cached tools, retains provenance, and
uses existing CAS/size-bounded atomic persistence. Success appears only after
acknowledgement. No package execution, download, transport connection, or
implicit enabling is added. Unknown installation outcomes continue to pause
model work until verified recovery. Custom add, import, and secret-bearing
registry installs remain separate pending migrations.

The default fake TUI now explicitly rejects unconfigured mutation requests;
tests must opt into a temporary scoped lane. This prevents future test omissions
from accidentally writing real MCP configuration. Existing registry-install
coverage now waits for actual acknowledgement rather than assuming synchronous
publication. Added regressions for reload reconciliation after a post-save
exception, changed-during-prepare rejection, disabled adds/duplicate handling,
current/stale/rejected UI recovery, and queue holds after failed verification.

Validation:

- `timeout 45s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_mcp_mutations.py tests/unit/test_mcp_inventory.py tests/unit/test_background_jobs.py tests/unit/test_cli_commands.py tests/unit/test_mcp_client.py -k mcp`
  — **79 passed, 541 deselected in 6.79s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,479 passed, 19 skipped in 62.07s**.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .`
  — all checks passed.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **57 production source files**.
- `git diff --check` — passed.

An initial new UI test used a nonexistent modal-clear helper, and mypy found a
union narrowing issue; corrected both before final validation. No live provider
calls, production configuration writes, SSH/WSL acceptance run, commit, or push.
Unrelated dirty worktree changes preserved.

**Exact next slice:** use the fixed disabled-add operation for custom setup and
secret-bearing registry definitions, preserving masked secret collection and
private environment-reference storage as a separate boundary. Add a fixed
bounded import operation that reads approved local import files off-thread,
validates every definition, refuses duplicates atomically, and forces all entries
disabled with no cached tools or execution. Keep outcomes and live publication
acknowledged; neither cancellation nor a failed save may be described as rollback.
Then complete remaining explicit session/queue/direct-inventory and terminal
latency/SSH/WSL acceptance audits. Stage 1 remains open; Stage 2 has not started.
Verified reload guarantees its checked snapshot, not a permanent lock against
future external edits. The unused legacy private reload helper remains
synchronous; current TUI reload dispatch uses the lane. Secret/custom/import
paths and read-only preflight/OAuth file access retain their documented I/O gaps.

Scoped files: mutation lane, CLI adapter, their regression tests, `AGENTS.md`,
and this plan.

### Stage 1 execution record: atomic imports and non-secret custom adds (2026-10-01)

MCP settings import now submits an immutable private source-path request to the
ordered lane rather than reading/parsing/saving in the input handler. The worker
reads and validates the full selected import, refuses any existing-name duplicate
before changing the batch, forces every imported definition disabled, removes
cached tools, and publishes one CAS-protected atomic save. The imported count
appears only after a saved acknowledgement; rejection never claims partial
success. Source paths are excluded from request reprs and public feedback.

Hardened the shared import reader: no-follow/nonblocking file descriptors,
regular-file checks, a 4 MB stat-and-actual-read bound, and fail-closed validation
of every entry. FIFOs, directories, symlinks, oversized input, missing supported
shapes, malformed entries, and unsafe credentials are rejected without executing
anything. VS Code, standard, and OpenCode normalization remain supported. Import
file content is read when the accepted worker processes it; the imported
definitions still require separate user review/enable afterward.

Custom stdio, unauthenticated HTTP, and OAuth definitions now share the existing
fixed disabled-add operation. A common scoped submission helper also handles
registry installs without secret input. Custom bearer-token and secret-bearing
registry flows retain their existing separate private-secret path for the next
slice; no unsafe partial migration or credential copying into definitions was
introduced. Queued work remains governed by acknowledged catalog state.

Validation:

- `timeout 45s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_mcp_mutations.py tests/unit/test_mcp_inventory.py tests/unit/test_background_jobs.py tests/unit/test_cli_commands.py tests/unit/test_mcp_client.py -k mcp`
  — **90 passed, 541 deselected in 6.29s**.
- `timeout 90s env UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit`
  — **1,490 passed, 19 skipped in 60.98s**.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .`
  — all checks passed.
- `env UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`
  — no issues in **57 production source files**.
- `git diff --check` — passed.

Coverage includes unsafe source types, invalid-entry/duplicate/secret rejection
with byte-identical existing registry preservation, full disabled batch imports,
off-UI input dispatch, private-path feedback, and acknowledged custom setup.
An initial custom-setup test needed its temporary fake agent tools/policies
initialized for real publication; fixed the fixture before final validation.
No live providers, production configuration writes, SSH/WSL acceptance run,
commit, or push. Unrelated dirty worktree changes preserved.

**Exact next slice:** finish bearer-token custom setup and secret-bearing registry
installs. Preserve masked input and private environment-reference storage, check
duplicates and secret namespace conflicts before writing, and avoid overwriting
unrelated credentials. Move fixed private operations off-thread with honest
acknowledgements and bounded ownership. Registry and environment files are not
one transaction: distinguish rejected, partially completed, and unknown outcomes
without claiming rollback or blindly retrying. Then finish remaining explicit
session/queue/direct-inventory and terminal latency/SSH/WSL acceptance audits.
Stage 1 remains open; Stage 2 has not started. Existing read-only preflight/OAuth
file-access limitations and the unused synchronous private reload helper remain
documented, rather than being counted as solved by this slice.

Scoped files: mutation lane, CLI adapter, shared core import reader, their three
regression-test modules, `AGENTS.md`, and this plan.

### Stage 2: One observable runtime lifecycle

2026-10-01 architecture decision: pilot Pydantic AI behind a compatibility
adapter before extending the production loop further. The isolated runtime
spike passed async tool dispatch, stream events, cancellation cleanup, and
completed-history/model-switch replay; it did not validate real Ollama,
permissions, partial-turn durability, or TUI behavior. See
`docs/runtime_reuse_spike_2026-10-01.md` for the evidence and ownership split.
This decision does not close Stage 1 or authorize a production loop rewrite.

- [ ] Extend existing events and capability snapshots into a versioned contract
  with stable session, turn, invocation, and request IDs.
- [ ] Define ordered start/result/completion events and explicit completed,
  interrupted, failed, and outcome-unknown states.
- [ ] Derive transcript, live footer, observer replay, `/status`, and audit state
  from the same authoritative lifecycle; keep private reasoning private.
- [ ] Define the effective boundary for permission and MCP changes during work.
- [ ] Reconcile crash recovery instead of automatically repeating mutations.
  A missing completion event is not proof that an operation did not execute.

Acceptance gate: inject failures during streaming, permission waits, tool
execution, persistence, and lease loss. No unsupported completed activity, silent
abandoned turn, or automatic replay of an uncertain mutation may result.

### Stage 3: Bounded capability discovery

- [ ] Retain cheap deterministic routing for obvious requests, but provide a
  model-callable discovery path for other authorized capabilities.
- [ ] Distinguish callable, discoverable/not loaded, disabled, authentication
  required, and prohibited-by-scope states.
- [ ] Load schemas on demand without granting permissions or bypassing plan,
  workspace, transport, or settings boundaries.
- [ ] Offer compact constrained-model profiles and visible user overrides;
  never silently switch the model or require hidden automatic retrieval.

Acceptance gate: paraphrases, typos, contextual follow-ups, and unfamiliar MCP
names discover appropriate tools without exposing unrelated mutation tools.

### Stage 4: Long-task control and user-owned edits

- [ ] Track normalized failure categories, argument fingerprints, new evidence,
  changed-file outcomes, test results, and resolved diagnostics for progress.
- [ ] Keep emergency ceilings and explicit finalization reserves. Add deadlines
  at the actual request/tool owners; report unknown usage honestly.
- [ ] Preserve dirty-tree protection. Design an explicitly approved isolated
  worktree or agent-owned patch workflow before enabling edits on dirty trees.
- [ ] Separate edit checkpoints/recovery from automatic Git commits; recovery
  must not capture, discard, or restore over unrelated user changes.

Acceptance gate: repeated equivalent failures terminate promptly; genuinely
progressing tasks remain viable within configured budgets; recovery and edits
preserve user-owned changes, including changes made during the turn.

### Stage 5: Incremental modularization

- [ ] Extract picker controller and typed UI/modal state.
- [ ] Extract settings, provider authentication, and MCP setup services.
- [ ] Extract session/queue control and transcript rendering.
- [ ] Separate routing and tool execution from the core conversation loop.
- [ ] Split repository guidance into scoped runtime/contributor/UI/release
  documents with clear precedence and bounded model-facing instructions.

Acceptance gate: existing CLI, keybindings, footer, queue, permission behavior,
observer replay, and native scrollback regressions remain covered and passing.

### Stage 6: Behavioral evidence before increased autonomy

- [ ] Run repeatable representative local/cloud model matrices with isolated
  data and no production-memory or learned-library contamination.
- [ ] Evaluate multi-file coding against held-out tests; capability discovery;
  live permission changes; model changes; compaction and process resume.
- [ ] Measure retrieval relevance, freshness, exact citation support, latency,
  token cost, task success, recovery rate, and safety violations.
- [ ] Exercise malicious MCP descriptions, retrieved prompt injection, parser
  boundaries, sandbox escape attempts, and secret handling.
- [ ] Add dependency/license/secret scanning, parser/sandbox fuzzing, SBOMs,
  reproducible release evidence, and independent assessment where practical.
- [ ] Expand durable workers and mutation-capable subagents only after these
  gates pass. Start parallelism with isolated read/research/diagnostic work and
  shared quota accounting; do not assume more workers improve quality.

Acceptance gate: publish comparable results and limitations. A green unit suite
alone is not sufficient evidence for broader autonomy or frontier equivalence.

### TUI UX acceptance requirements across all stages

- [ ] Keep login/setup progress in settings with Cancel and timeout feedback.
- [ ] Preserve navigation state through background updates and filter changes.
- [ ] Retain animated Braille live footer and completed-only transcript badges.
- [ ] Explain configured versus effective permissions when they differ.
- [ ] Distinguish local execution, remote observation, and detached jobs.
- [ ] Use Add/Remove API key for API credentials; Login/Logout for account auth.
- [ ] Put `openrouter/free` first as requested, without implying guaranteed
  availability, zero downstream costs for unrelated tools, or model quality.
- [ ] Test narrow terminals, SSH/WSL, Unicode, multiline cursor movement, large
  paste, modal input, queue steering, `/resume`, and redraw/native scrollback.
- [ ] Establish and measure an input-latency target; heavy work must never run
  on the keystroke/render path. Include latency tests under background load.

### Reference implementations and research

Official sources consulted on 2026-09-30; upstream documentation is mutable.
Use them as design references, not proof of comparative benchmark performance:

- [Codex app-server lifecycle, approval resolution, and turn diffs](https://developers.openai.com/codex/app-server)
- [Codex subagents and parallel-work tradeoffs](https://developers.openai.com/codex/multi-agent)
- [Claude Code isolated subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code deferred MCP tool discovery](https://code.claude.com/docs/en/mcp#scale-with-mcp-tool-search)
- [Claude Code edit checkpoints](https://code.claude.com/docs/en/checkpointing)
- [Hermes shared runtime, prompt assembly, gateway, and automation architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture)

### Review validation baseline

Read-only review ran these commands; none constitutes a full integration or
independent security audit:

```bash
UV_CACHE_DIR=/tmp/klaude-review-uv uv run pytest -q tests/unit/test_execution.py tests/unit/test_capabilities.py tests/unit/test_mcp_client.py tests/unit/test_mcp_catalog.py tests/unit/test_intent.py
# 45 passed in 1.12s
UV_CACHE_DIR=/tmp/klaude-review-uv uv run ruff check .
# All checks passed
UV_CACHE_DIR=/tmp/klaude-review-uv uv run mypy apps/cli/src packages/core/src packages/tools_local/src packages/web/src packages/knowledge/src
# No issues in 44 source files
git diff --check
# Passed
```

Full-suite rerun, live provider matrix, terminal fault testing, and independent
security review were not completed in this assessment. Checkboxes above must
be updated only alongside implemented behavior and corresponding evidence.
