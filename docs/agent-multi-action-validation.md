# Compound lookup execution: first implementation and evaluation

Date: 2026-10-16. Starting checkpoint: `90137f46f59f15346f16401c2ecd5b6aecc8a7f7`.
This follows [the researched recommendation](agent-multi-action-research.md).
The checkpoint was pushed to `klaude/20260908-1448` before these implementation
changes. The changes described here are subsequent, uncommitted work.

**Follow-up:** [read recovery and interactive lookup evaluation](agent-read-recovery-validation.md)
addresses the mixed-action arguments and stale research gaps observed below.
The results and remaining limitations in this document describe the earlier
iteration; its full gate does not certify the subsequent follow-up sources.

## Scope and evidence boundaries

This is the first M0/M1 implementation, not completion of every proposed step.
It addresses skipped lookup actions, stopping at a source lead, excessive context
for retrieval and loss of transport diagnostics. Existing workspace execution,
permission gates, provider-native continuations and budgets remain in use.

**Result:** both Gemma models completed the controlled one-shot source lookup in
the source-obligation iteration. The latest interactive continuation executed
search and source reading, but still misrepresented the source of the retrieved
facts in its final answer. This is an action-reliability improvement, not a claim
of reliable semantic completion. Automated and packaging evidence is listed below.

The original production session `e590f24185454f818bdc099c7a5025fa` was inspected
read-only during research. Its user image was not uploaded or used in external
evaluations. The previous generic network failure cannot be classified
retrospectively. No paid cloud inference or automatic model switch was used.

Real-model tests use native local `gemma4:e2b` and `gemma4:e4b`, Standard mode,
with explicit context allocations. A synthetic 1000×700 PNG depicts red/green
shapes and the credit `SALAD MADE BY LUMA QUILL`. Controlled tools return an
artist portfolio lead, followed by a separate source containing the title
`SALAD PARTY` and date `18 February 2024`. The `.example` source is a fixture,
not a real artist attribution. Queries must mention Luma or Quill to return that
lead. Models choose their queries and calls; responses are real Ollama inference.

The launcher runs the real Typer CLI/session/TUI paths and substitutes only the
search/fetch tool functions, plus observation wrappers. This establishes model
and client orchestration against controlled evidence. It does not certify real
search-provider availability, website extraction or original-image matching.
No reverse-image upload/matching capability was added.

## Observed baseline and iterations

Main prompt: `can you look up where this is from @PATH_TO_SYNTHETIC_IMAGE`.
The interactive continuation uses exactly `look them up`.

| Revision / test | E2B | E4B | Interpretation |
| --- | --- | --- | --- |
| Checkpoint, 8K context | Admission rejected, exit 1, 2.35s; no inference | Admission rejected, exit 1, 1.82s; no inference | Essential prompt/tool/output cost prevented even the first image request. |
| Checkpoint, explicitly configured 16K | Exit 0 in 47.39s; no tools; offered further help and claimed image-source lookup limitations | Correct image-credit search observed, then externally timed out at 300s | Neither completed the source-lookup task. E2B's successful process exit did not establish completion. |
| Initial outcome guard and partial prompt selection, 8K | Still rejected before inference | Still rejected before inference | Merely adding state does not fix an oversized prompt. |
| Coding policies omitted and repeated search guidance removed, 8K | Search executed; next request rejected, exit 1, 25.55s | Correct search; next request rejected, exit 1, 59.12s | The full generic research instructions still crowded out tool-result continuation. |
| Compact retrieval policy, 8K | Search → fetch → final, exit 0, 66.56s; four model requests including one empty-response recovery | Search → lead and redundant offer to open it, exit 0, 72.54s; two requests | Retrieval improved, but finding a lead did not fulfill image-origin/source examination. |
| Separate source-examination obligation, 8K | Search → one bounded source correction → fetch → final, exit 0, 66.83s, four requests; correct fixture credit/title/date | Search → bounded correction → fetch → final, exit 0, 175.66s, five model requests | The correction targets the remaining outcome, without another permission question. |

Early evidence roots under ignored `.klaude/data/`:
`compound-before-b724yzsd`, `compound-before-16k-p8vrfw6r`,
`compound-after-focused-8k-706h0ms1`, `compound-after-8k-final-9vlcuf6q`,
`compound-after-compact-8k-lmciarh4`, `compound-after-source-check-8k-w6sno9fr`.
The 16K harness initially aborted on its external deadline; its E2B terminal log,
E4B search receipt and saved session remain evidence, not a completed E4B result.

### Test-isolation correction

The earliest fixture workspace was accidentally nested beneath this repository.
Klaude's existing workspace setup switched the enclosing repository onto its
normal temporary branch. Reflog and HEAD checks established that both branches
pointed to the checkpoint. The original branch was restored without resetting,
stashing or removing edits. Subsequent workspaces are independent `/tmp`
directories; preferences and session stores remain isolated. No production
preferences, user images or provider keys were changed.

## Root causes and implementation

### Observable outcomes and bounded repair

New [task_progress.py](../packages/core/src/klaude_core/task_progress.py) records
bounded host-observed outcomes, attempted calls, execution IDs and blockers.
[agent.py](../packages/core/src/klaude_core/agent.py) integrates this record into
the existing tool loop and request projection.

- Lookup detection accepts an arbitrary object between `look` and `up`, or
  following `look up`, including pronouns and misspelled object words. Explicit
  prohibitions and local dictionary/file/library operations retain their bounds.
  Quoted examples/code do not create host-enforced lookup obligations. Each
  occurrence is checked against its own prohibition, so a negated online lookup
  cannot borrow authorization from a later local dictionary action. These guards
  affect the bootstrap only; the model still receives the unchanged user request.
  This remains bounded lexical handling, not general semantic understanding.
- Routing restores permitted search/read schemas even when the initial selector
  omitted them. It does not enable disabled tools or widen host scope.
- A source read can satisfy external retrieval directly. A namespaced MCP result
  can satisfy it only with observed source-provenance metadata. Descriptions and
  tool names alone are not evidence.
- Image-associated lookups and explicit origin requests also require an actual
  candidate source examination. Search leads do not satisfy that outcome.
- Failed, denied, malformed, skipped or empty results cannot establish an observed
  outcome. The model chooses dependent calls and queries from actual dialogue.
- Each missing outcome gets at most one corrective opportunity, charged to the
  existing governor. A repeated omission or unavailable route produces a host
  incomplete result and an error; it does not publish the unsupported final claim.
- Unfulfilled action responses are buffered up to 64,000 characters before
  completion checks. Live stage/tool progress remains visible. Ordinary chat
  streaming remains direct. Cancellation does not publish held success claims.
- Task state is turn-local. Restore retains actual dialogue and approved pixels;
  old audit metadata does not become replayable result evidence. No new durable
  semantic goal/entity database or separate planner/judge service was introduced.

This record verifies execution of tracked actions. It cannot prove source
relevance, identity, authenticity or correct interpretation of every requirement.
The model must assess those and report uncertainty. A valid state record is not
proof of semantic completion.

### Bounded, relevant context

[request_context.py](../packages/core/src/klaude_core/request_context.py) selects
short research guidance for retrieval-only requests, omitting standalone coding
and unrelated configuration details. The canonical
[system prompt](../packages/core/src/klaude_core/prompts/system.md) scopes workspace
editing/review instructions to actual workspace tools. Core authority, dirty-tree
protection, repository instructions, Skill catalog, dates/location, evidence
boundaries and callable-schema information remain available.

The measured system projection fell from 17,732 characters in an intermediate
candidate to approximately 10,600 with both lookup obligations. The successful
compact E2B run reported 3,187 input tokens on its first request; the 16K baseline
reported 9,079 for its sole completed E2B request. These counts include different
request projections and image allocations; they are observations, not a universal
compression ratio. Local context was never silently increased. Tools/result
continuations now fit the explicit 8K allocation in the successful runs.

No extra model call is added for direct conversation. Corrections add calls only
when an explicit action is missing. More complete work may take longer than an
incorrect one-response answer. Single runs, model loading, GPU placement and
concurrent host tests do not support p50/p95 latency claims.

### Historical dates versus the local clock

A subsequent text-only run exposed another host contribution to the difficulty:
the CLI selected `current_time` for the bare word `date` in "creation date".
That irrelevant tool also disqualified the request from compact research context,
nearly doubling the first request's text. The selector now recognizes explicit
clock/current-date requests instead of every mention of dates or timings.
Historical/publication dates, event start times and time-complexity questions do
not automatically expose the clock. Ordinary clock questions, named clock calls
and weather retain their tools. Legitimate research with clock/weather tools can
also use the compact research projection. This changes no permission or default
context allocation.

The unchanged text task was:

> Look up Luma Quill, read the relevant portfolio page, and tell me the title and creation date of the credited illustration.

Both `qwen2.5-coder:3b` and `qwen3.5:4b` used the same controlled search/source
functions, native local Ollama and explicit 8192 context/768 output configuration.
There were no image inputs. This is a retrieval regression, not the CSV coding
benchmark or evidence of new CSV completion.

| Text-only test | Before clock/projection correction | After correction |
| --- | --- | --- |
| Qwen 2.5 Coder 3B | Exit 1, 113.79s; 9 charged model steps and 7 charged tool attempts. Search found the lead; page-read arguments mixed unrelated `answer`/`timezone` fields, followed by search/clock retries and an incomplete stream. First native input: 5009 tokens. | Exit 1, 67.03s; 5 charged model steps and 4 charged tool attempts. Three fixture searches, no source read, no clock calls; the existing no-progress guard stopped it without a false completion. First native input: 2837 tokens. |
| Qwen 3.5 4B | Exit 0, 133.53s; search → fetch → correct title/date answer. Three model steps, two tool attempts, 16,788 aggregate input tokens and 232 output tokens. First native input: 5286. | Exit 0, 91.95s; search → fetch → correct title/date and source-URL answer. Three model steps, two tool attempts, 10,162 aggregate input tokens and 252 output tokens. First native input: 3073. |

The 3B run's recorded input totals fell from at least 36,648 (two requests had
unknown usage) to 21,703 (all five requests had usage); these are not complete
before/after totals for every request. Counts above use the saved session governor,
because the observation wrapper does not intercept every structured-recovery
request. Its trace's `model_requests` field alone undercounts the 3B run.

The 4B task completed correctly in both runs while using less input after the
fix. The 3B model failed faster and avoided irrelevant clock work, but still did
not fulfill the requested page read. Neither a shorter failure nor passing host
tests is scored as task success. Timings are individual runs, with model loading,
placement and concurrent automated checks uncontrolled; no general speed or
statistical reliability claim follows.

Evidence: `.klaude/data/compound-text-models-y86ia26z` before the clock fix and
`.klaude/data/compound-text-models-tx27fk5o` after it, including `results.json`,
per-model traces/transcripts and isolated session databases. The `.example` URL
and reported provider names remain controlled fixtures, not live search evidence.

### Literal response requests are data, not tool instructions

The real negative control `Print exactly "look them up".` exposed a separate
route error. The short-name heuristic offered four retrieval tools for this
five-word request. Qwen 3.5 4B then refused because it thought printing required
a shell tool: exit 0, 39.40s, 5452 input tokens, no actual tool calls. Avoiding
forced lookup alone was insufficient; the tool/context projection was wrong.

A shared whole-request literal-response predicate now keeps quoted echo/reply/
print requests on the direct path. The CLI exposes no tools for that operation;
core does not infer retrieval obligations from the literal payload and retains
direct context and normal runtime options even if that text mentions code or
Klaude settings. This does not change the requested text or answer it with a
hardcoded host response. Compound requests and explicit destinations, such as
`Say "ready", then look the artist up online` or `Print "hello" to output.txt`,
do not match this rule and retain normal routing.

The unchanged Qwen 4B control reran in 4.13s with one model step, zero tool calls,
293 input tokens and four output tokens. Its decoded answer and CLI transcript
are exactly `look them up`, without quotation marks. This fixes the false inability
and irrelevant tool exposure, and passes the exact-output assertion.
Evidence: `.klaude/data/compound-quoted-control-k3gj3t0p` before and
`.klaude/data/compound-quoted-control-fixed-s0j4ehn8` after. The original raw
`passed: false` receipt remains intact beside `results-corrected.json`. The first
harness mistakenly compared JSON-encoded `turns.content` instead of decoding it
as `Memory.load_session` does; the enclosing quotes were storage syntax, not
model output. This correction was verified against the saved CLI transcript.
No production response rewrite was needed. These remain individual timings.

### Transport and diagnostics

[compatible_runtime.py](../packages/core/src/klaude_core/compatible_runtime.py)
retains safe HTTPX categories: connect/read/write/pool timeouts, connection/read/
write/proxy failures, protocol failures and a generic transport fallback. It records
response phase, whether generation/output had started, elapsed time and an actual
routed model when received. Raw exception URLs, credentials and provider messages
are not serialized. Cancellation remains cancellation.

The CLI's public metadata allowlist retains these fields. Previous known token
counts remain explicitly labeled as belonging to a previous request and no longer
replace current failure diagnostics. The agent updates its elapsed governor
snapshot at actual failure/cancellation completion rather than retaining only the
request-start value.

No automatic transport retry, paid-generation replay or uncertain-side-effect
replay was added. Existing typed image-limit/temporary-rejection policies remain
separate. Current configurable transport deadlines are unchanged: choosing new
connect/inactivity/total defaults requires broader provider/local measurements.

### Follow-up goal/referent correction

The initial TUI action trace exposed a semantic failure despite valid tool calls:
the answer repeated the old credit-reading task. `TaskProgress` now retains the
bounded exact current objective; short dependent lookups also retain at most
600 characters of the previous public assistant answer, explicitly marked as
unverified referent context. It does not extract or certify a person's identity.
After a complete tool round, one ephemeral current-objective note follows the
results. It is rebuilt for each request, preserves native call/result pairs and
never accumulates in canonical history. No additional inference call is needed
for this state projection.

That observed missing-action failure justified reusing the existing native
Ollama constrained-action protocol on the one corrective attempt. The active
schemas narrow to the missing outcome's permitted routes; the finish action is
withheld while that action is outstanding. After observed completion, normal
native answering resumes. There is no new planner, executor or model-specific
name exception. Unsupported runtimes retain the bounded ordinary correction.
Permission/argument checks, source restrictions and budgets remain in force.
Budget-end tool-free synthesis also checks these outcomes, preventing it from
claiming source confirmation after only a final permitted search.

A rerun hit an observed Ollama GPU runner fault, took the existing CPU recovery,
and asked for a referent instead of searching, then exited honestly incomplete
on the bounded correction. That failed run is retained separately at
`.klaude/data/compound-interactive-_2j59472`. An explicit-CPU rerun with
current goal/referent state (`compound-interactive-mcxlyy8z`) performed the correct
search, then repeatedly claimed pages could not be opened despite `fetch_url`
being available. It ended honestly incomplete after bounded repair. This is
recorded as a failed semantic/action attempt, not a successful rerun. It must not
be mixed with the earlier GPU timings or reported as a guaranteed multimodal-model
success.

The final explicit-CPU run (`compound-interactive-j_9xdthv`, session
`829abed240a5479889d377c46679f6eb`) searched the correct credit and fetched the
portfolio without intervention. The lookup took 323.06s across three observed
native requests: 103.76s, 61.79s and 156.76s. Their reported input counts were
3037, 3292 and 3732, within the configured 8192 context. The source file had been
deleted after the first credit-reading turn; the private session snapshot still
provided the image. The exact-OK/no-tools control added no tool calls.

Its final answer included the retrieved date and source URL, but incorrectly
attributed the fetched page's details to the search snippet, claimed it had not
read the page and offered another fetch. Its skepticism about an `.example`
fixture is reasonable; the incorrect account of which tool supplied the facts
is still a real failure. The receipt's `passed` label checks required actions and
presence of source facts; manual transcript grading is **partial**, not semantic
success. The final request did not require constrained recovery: native tool
calling already selected both operations. The recovery branch is covered by
deterministic regression tests, not claimed as separately live-certified here.

The production record and tests therefore establish whether a usable tool result
was observed, not whether the answer correctly used it. A task-progress status of
`complete` means the tracked execution obligations were observed. It is not a
semantic quality score or proof of original attribution. A selective grounding
evaluation would need to distinguish factual uncertainty from false claims that
a completed tool action never occurred; a generic extra judge on every turn has
not been justified or introduced.

## Validation

The first real TUI continuation executed the required actions in session `7caeb48eb3494ff1a461c2ca3872c1d6`,
titled `TEST KLAUDE FEATURES COMPOUND ACTIONS`. It first read the synthetic credit
without search, then the source file was deleted. `look them up` searched the
correct credit and fetched the portfolio in 34.02s. An exact-OK/no-tools follow-up
added no tool calls. Transcript inspection then found that the final response
repeated the earlier image-credit answer instead of reporting source findings.
The receipt's original `passed` label covers its weak action-only assertions;
it is **not** semantic completion evidence. The strengthened test requires the
saved final assistant answer to contain substantive source findings.
Captures were made at 120/80/40 columns; the 120-column source
answer and direct control were inspected. Evidence:
`.klaude/data/compound-interactive-jko8j1by/{results.json,interactive-trace.jsonl,terminal.log}`.

A real CLI/local HTTP fixture also stalled before headers and after a visible SSE
prefix, with a **test-only** 0.2s read timeout. Each `ask` exited 1 after exactly one
request, retained `read_timeout` plus the correct phase/started state and actual
elapsed budget in saved session events. The partial stream retained its visible
prefix and actual routed-model identity; no automatic retry occurred. Evidence:
`.klaude/data/transport-cli-lifq3k5d/results.json` (2.56s/1.80s process wall time).
This tests transport/session wiring; it changes no production timeout default.

Focused agent, provider, image and cancellation regressions passed: 220 tests. New coverage additionally
checks both original lookup formulations, paraphrases, misspelled objects,
source-examination recovery, alternative direct reads, provenance-bearing MCP
results, no-results/permission failure, bounded repeated omissions, streaming
suppression, restored candidates and actual failure elapsed time. Negative controls
cover greetings, exact OK, colors-only requests, no-search/no-tools and dictionary
lookups. Transport fixtures exercise nine HTTPX categories, partial streams,
cancellation and secret redaction.

The clock/projection correction also passed 1012 focused CLI, context and
reliability checks with one pre-existing skip. The last quoted-example and
per-clause guards passed all 57 focused intent, compound-task, request-context
and transport checks. Literal routing then passed 1046 focused checks with one
pre-existing skip; the final intent/context/runtime-option regressions passed all
62 checks. The final full gate below covers their combined sources.

### Integration regression found and repaired

An initial full run reported 16 failures, 3586 passed and 19 skipped in 772.30s.
Fifteen replay failures exposed a new regression: updating elapsed time after an
already completed `done` event changed its corresponding capability snapshot.
Failure/interruption-only refresh now retains actual failed-request time while
leaving completed snapshots stable. The remaining failure exercised an earlier
cancellation-test expectation; cancellation stays a typed `cancelled` error.

The old lookup replay returned canned completion without performing its requested
action. Its fixture now includes a real scripted search call/result and verifies
executed evidence, correct request count and no recovery/error for compliant model
profiles. Tool-less profiles remain bounded and expose no callable schemas.
The 55 affected/new checks passed after these fixes. No safety assertions were
removed to make the failures disappear.

A second full integration run found one further regression: focused selection
replaced arbitrary custom `<web_research_policy>` text. Compaction now requires
the canonical block's explicit `default="klaude"` opt-in; custom policy content
is retained. That run reported 3608 passed, 19 skipped and one failure in 865.78s.
The custom-policy regression and 165 related checks passed after repair. Final
source hashes are recorded for the fresh full gate; final results follow below.

### Completed full gate before the historical-date correction

On Python 3.12.3, `make check` completed successfully before the last clock-routing
and projection correction:

- **3613 passed, 19 skipped**, 809.55s pytest time; 811.10s complete gate time.
- Ruff: all checks passed.
- Production mypy: no issues in 152 source files.
- The 19 skips are pre-existing tests marked superseded by model-directed
  retrieval coverage; they are not newly ignored failures.
- SHA-256 checks confirmed those production sources and prompts matched that
  gate when it completed. A separate full gate covers the final correction below.
- A fresh `make package-smoke` built all five wheels, installed them
  together in an isolated environment, imported all public packages and ran the
  installed `klaude --help` successfully.
- `git diff --check` passed. No implementation commit or second push was made.

Local full-gate evidence:
`/tmp/klaude-compound-sealed-validation-sannj4qe/{result.json,check.log,pytest.xml,source-sha256.json}`.
Packaging log at that point: `/tmp/klaude-compound-final-package-smoke.log`.
The actual commands used frozen/offline dependency resolution and a writable
temporary uv cache. This is local Python 3.12 evidence; no new CI run or Python
3.11/3.13 run is claimed for these uncommitted changes.

Two later full runs were deliberately interrupted after live negative controls
exposed additional routing defects. Their evidence roots are
`/tmp/klaude-compound-clock-validation-zeg6heoy` and
`/tmp/klaude-compound-guarded-validation-4qg53ot2`; both record interruption
(`exit: -2`), not success. Only the test processes attached to those exact log
files and their descendants were stopped. A new source snapshot and complete
gate cover the final literal-response fixes below.

### Final gate on the first M0/M1 iteration

`make check` completed with exit 0 on Python 3.12.3:

- **3645 passed, 19 skipped** in 736.72s; the complete gate took 737.99s.
- Ruff: all checks passed.
- Production mypy: no issues in 152 source files.
- The same 19 pre-existing superseded retrieval tests were skipped; no new skip
  was added for this implementation.
- All 153 recorded production Python/prompt files matched their starting SHA-256
  hashes. This gate includes the clock, quoted-example, per-clause prohibition,
  literal-response and general-runtime-option corrections.
- Final `make package-smoke` passed: five wheels, isolated installation, public
  imports and installed `klaude --help`.
- Final `git diff --check` passed. The implementation remains uncommitted after
  the already-pushed starting checkpoint.

Evidence:
`/tmp/klaude-compound-final-sources-9pmf0yjj/{result.json,check.log,pytest.xml,source-sha256.json}`;
packaging: `/tmp/klaude-compound-final-sources-package.log`.
These are final local results, not CI certification or live cloud-provider tests.

## Remaining boundaries and next step

- Tool discovery outside the initial route across all built-ins/Skills/MCPs (M2)
  is still a separate step; this pass restores only the known read-only lookup
  routes. No discovery engine or programmatic tool runtime was introduced.
- Semantic entity/goal decomposition remains model-led dialogue plus limited
  lexical obligation detection. Arbitrary compound intentions are not guaranteed.
- The new outcome state and older explicit required-tool checks still coexist.
  Consolidating required retrieval under shared outcome evidence is a justified
  follow-up; this slice does not replace the workspace or provider protocols.
- Source examination is necessary but insufficient to prove an original author
  or visual match. Text search cannot guarantee an image's origin.
- Small models can still emit empty native responses; bounded existing recovery
  remains necessary. Final citation completeness and factual relevance require
  evaluation beyond whether calls executed.
- The final interactive answer still confused search leads with a successfully
  fetched source. More explicit current-goal state improved action selection but
  did not establish reliable evidence interpretation. CPU latency was substantial;
  the single GPU and CPU runs do not establish a speed improvement or regression.
- The 3B text model still repeated searches rather than reading the source. Its
  earlier invalid call mixed fields belonging to different actions. The existing
  local discovery grammar shares argument fields across tools and finish actions,
  while the mutation grammar already binds exact per-tool parameters. Canonical
  host validation correctly rejects mixed fields, but the permissive discovery
  grammar remained a Klaude limitation in this iteration. The
  [follow-up](agent-read-recovery-validation.md) evaluates exact binding for
  non-coding lookup recovery while preserving workspace discovery. Earlier
  small-model evaluation recorded intermittent Ollama grammar failures; unchanged
  CSV comparisons remain necessary before extending this change to coding.
- The measured literal reply now passes exact output after correcting the
  evaluation's storage-decoding bug. This single control does not certify every
  arbitrary formatting request; the host does not silently rewrite replies.
- No cloud quality comparison or new deadline policy was certified. Pinned versus
  dynamic OpenRouter routing and slow-local waiting policies remain measurements
  for a later adapter/recovery pass.
- The Stockroom CSV fixture and workspace planning/execution logic were not
  changed or rerun in this lookup slice. No new CSV completion claim is made.
- The next investigation from this iteration was exact argument binding for
  retrieval and selective answer grounding, now documented in the follow-up.
  Portable bounded discovery remains the proposed M2 step; it is not a remedy
  for misusing results from an already callable tool. A mandatory planner, judge
  on every turn or multi-agent supervisor remains unjustified by these results.
