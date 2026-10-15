# Adaptive tool use and compound requests: research and proposed design

Research date: **2026-10-16**, Asia/Phnom_Penh. Base repository revision:
`4a64ce696ba0e0825fa5670609d2449955304648`, including the current dirty worktree.
**Status: research/proposal only. No production behavior changed in this pass.**

## Recommendation

Keep Klaude's existing agent and give it a compact representation of the complete
user objective, capabilities it can discover when needed, and completion checks
grounded in executed results. Let the model choose dependent actions and revise
its approach as evidence arrives. Keep permission and resource decisions in the
host. Simple conversation and ordinary image description should remain direct.

This is a recommendation for Klaude, based on current public documentation and
its observed failures. Public API guidance does not reveal the complete internal
architecture of ChatGPT or Claude, and no architecture guarantees frontier-model
reasoning from a small local model. The proposed changes need comparative evals.

## 1. The actual failure to solve

Session `e590f24185454f818bdc099c7a5025fa` contains two relevant turns:

| Request | Saved behavior | What this establishes |
| --- | --- | --- |
| “can you look up where this is from” with an image | Completed in 13s; `openrouter/free` reported `dots-studio/dots-3-note-preview:free`; response claimed the credit read Tubupipi; zero executed tools | Pixels were supplied and search/fetch tools were offered, but the requested lookup was not performed. The artist name remains a model-derived lead. |
| “look them up” | Failed after 4m29s with `Model connection interrupted; retry`; no tool calls or answer; no responding-model metadata | A transport request failed. The saved error cannot identify timeout versus disconnect, or establish the second routed model. |

Both request projections declared one supplied image and a 200000-token provider
context. No context-limit error was recorded. This evidence does not certify the
model's visual interpretation or explain the upstream network failure.

An appropriate dynamic path could be:

```text
Inspect supplied image → identify candidate credit/subject → search relevant terms
→ inspect promising sources → compare evidence → answer with links or state uncertainty
```

These are dependencies for this task, not a compulsory sequence for every request.
“Describe the colors” should not trigger web research. Finding an image's origin
can sometimes use visible text; Klaude's text search is not a reverse-image search
service. Do not claim pixel matching or upload the image to another service
without an actual supported, authorized capability.

## 2. What the primary sources support as of October 2026

Current documentation was opened during this research. Dates below distinguish
dated articles from living API documentation; access now does not mean every
feature was introduced this month.

| Source | Verified guidance | Application to Klaude |
| --- | --- | --- |
| [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) — current docs | The model/application loop can continue through multiple calls; schemas, tool choice and initial tool count affect behavior. Current native API requirements differ across models. | Preserve native protocols and validate calls; avoid treating one text response as proof the user's work is finished. |
| [OpenAI tool search](https://developers.openai.com/api/docs/guides/tools-tool-search) — current docs | Tools can be deferred and loaded through hosted or client-executed discovery; discovery has a latency tradeoff. | Keep common schemas small and make other enabled capabilities reachable. Benchmark eager versus deferred exposure. |
| [Claude tool-use loop](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works) — current docs | Client tools require a repeated model/call/result loop; server tools and paused turns have different continuation semantics. | Normalize provider events without flattening pauses, truncation, refusals and successful completion into one result. |
| [Claude tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool) — current docs | Relevant definitions can be loaded on demand; a custom client-side implementation is possible. | Apply the principle to Ollama and compatible endpoints without assuming support for Anthropic's hosted tool. |
| [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — 2025-09-29 | Compact references and targeted retrieval support long-running work; exhaustive context has costs. | Retain the goal, constraints, current evidence and next decision, with bounded source bodies. |
| [Anthropic tool design](https://www.anthropic.com/engineering/writing-tools-for-agents) — 2025-09-11 | Tool boundaries, descriptions, relevant output and evaluations matter. | Improve input/output contracts and actionable failures alongside orchestration. |
| [Anthropic harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps) — 2026-03-24 | Long tasks can benefit from explicit deliverables and evaluation; its demonstrated larger harness also costs substantially more. | Introduce structure where it improves measured outcomes, rather than adding several agents to each chat turn. |
| [Anthropic agent evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — 2026-01-09 | Assess actual outcomes, transcripts and efficiency together. | Test whether the compound objective was achieved, not whether a particular canned tool sequence appeared. |

### Programmatic calling is useful, with limits

[OpenAI's current programmatic calling](https://developers.openai.com/api/docs/guides/tools-programmatic-tool-calling)
lets supported models compose tool calls in an isolated JavaScript runtime.
Its runtime does not provide ordinary OS/network access; enabled tools remain
the interface to external systems. Klaude cannot obtain those guarantees by
exposing unrestricted `eval`, shell or Python execution under a new name.

[Anthropic's current programmatic calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)
helps with fan-out and large results that code can filter. Its documentation
explicitly identifies small requests and sequences requiring fresh model reasoning
between calls as weaker fits. Model/tool compatibility and data controls must be
checked. This is a later optimization, not a prerequisite for image → lookup.

[OpenRouter's free-router documentation](https://openrouter.ai/docs/guides/routing/routers/free-router)
describes capability filtering followed by random selection, variable availability
and latency, and a returned actual-model field. Therefore do not conclude that the
first routed model lacked tool support simply because it did not call a tool.
Compare pinned explicit models separately from dynamic routing.

## 3. Current implementation: reuse and gaps

These are code-backed facts, not proposed new features:

| Existing component | Reuse / relevant gap |
| --- | --- |
| [CLI tool selection](../apps/cli/src/klaude_cli/main.py), `_select_tool_names`, `_matching_mcp_tool_names` | Chooses initial schemas using wording and bounded MCP matches. A route should guide initial exposure without permanently excluding an enabled capability needed later. |
| [Core agent](../packages/core/src/klaude_core/agent.py), `_explicit_retrieval_tools`, `_needs_contextual_tool_route`, `_run` | Already has repeated tool rounds, follow-up handling and bounded missing-tool correction. Required lookup detection accepts a limited set of phrases; the two session requests are not covered by its web-required patterns. |
| [WorkspaceExecution](../packages/core/src/klaude_core/workspace_execution.py) | Tracks objective, inspected/changed files, plan references, revisions, validation and failures. Its code-specific rules should stay specialized; do not impose file-edit completion on research. |
| [TurnGovernor](../packages/core/src/klaude_core/execution.py) | Retain model/tool/time/token and no-progress budgets. A budget exhausted answer must retain incomplete status. |
| [AgenticSearchState](../packages/core/src/klaude_core/agent.py), [source use](../packages/core/src/klaude_core/source_use.py), [research receipts](../packages/core/src/klaude_core/research_receipts.py) | Preserve distinction between discovery leads, fetched evidence and audit metadata. A saved receipt is not replayable source content. |
| [Model runtime](../packages/core/src/klaude_core/model_runtime.py), [request context](../packages/core/src/klaude_core/request_context.py), [request budget](../packages/core/src/klaude_core/request_budget.py) | Reuse provider capability, native continuation and bounded request projection. Avoid a second independent agent/context engine. |
| [Compatible runtime](../packages/core/src/klaude_core/compatible_runtime.py), [HTTP transport](../packages/core/src/klaude_core/http_model_transport.py) | Typed provider envelopes exist, but the generic HTTPX catch still discards transport classification. |

Prior local-model findings also matter: [power-user evaluation](power-user-evaluation.md),
[small-model follow-up](small-model-evaluation.md), [source-context work](agent-source-context-evaluation.md)
and [task-state work](agent-task-state-evaluation.md) document real limitations.
No CSV completion or model-quality improvement is established by this research.

## 4. Proposed architecture

### 4.1 Retain the full goal and action dependencies

Use a compact task record shared with the existing loop, initially scoped to the
current user objective. Suggested fields, subject to prototyping:

```text
goal: the full user objective
constraints: user restrictions plus authoritative host scope
entities: candidates with their origin and uncertainty
pending_actions: required outcomes and dependencies
evidence: actual tool-result/source references and current revisions
blockers: permissions, unavailable capabilities, unresolved failures
completion: pending | complete | partial | blocked | cancelled
```

For this session, “Tubupipi” would be a candidate reported from the image answer,
not a verified artist identity. “Them” should resolve against that candidate and
the unfinished lookup goal. A genuinely ambiguous referent requires a concise
clarification; otherwise continue. Explicit changes of subject cancel or replace
the pending objective rather than keeping an obsolete plan active.

The model proposes intent and decomposition. Tool observations establish executed
actions; the model cannot declare that a search, write or test ran when it did not.
Task records never grant permission, select a different model, or turn untrusted
tool text into instructions. Keep hidden reasoning out of public state.

**Intent understanding remains a model problem.** A structured schema can still
contain an incorrect goal. Compare the original request against the proposed goal
and evidence in evaluation; do not present a valid JSON plan as semantic success.

### 4.2 Make tool exposure revisable

Keep a small initial set of likely tools plus a compact route to discover other
enabled capabilities. Existing routing can remain a prefetch optimization during
migration. It should not be the correctness boundary for what the agent can do.

- Expose concise capability metadata for built-ins, installed Skills and connected
  MCPs. Search/load the relevant schema or Skill instructions on demand.
- Common operations should not pay a discovery round trip unnecessarily.
- Loading a definition does not enable a disabled tool, authenticate a server,
  override a permission, authorize writes, or widen the workspace jail.
- Recompute the actual callable subset and TurnCapabilities after discovery.
- Bound loaded schemas and retain their identities across current tool rounds;
  preserve provider-required call/result pairs and private continuation.
- Use native hosted discovery only when the selected provider/model supports it;
  a portable local implementation must work through existing native tool calls.

### 4.3 Check requested outcomes before declaring completion

Represent obligations by outcome, not an exact preferred function name. A valid
research MCP may satisfy a lookup as well as a built-in search tool. Inspect its
real result and provenance rather than trusting an “executed” label alone.

| User outcome | Necessary evidence / honest alternative |
| --- | --- |
| Look someone up | Actual relevant external retrieval, or an explicit unavailable/failed result |
| Find an original source | Candidate source examined and identity/origin corroborated; otherwise report a lead or uncertainty |
| Modify a project | Actual authorized changes; preserve unrelated work |
| Validate a change | Relevant checks after the latest applicable edit, with actual exit status |
| Read attached pixels | Current request supplied pixels; text recaps cannot substitute |

On a missing obligation, give the model one bounded corrective opportunity with
the missing outcome and currently available capabilities. Let it choose the query
or next action. If it still fails, preserve partial results and report unfinished
work. A permission denial or policy refusal is not an invitation to try bypasses.

Mechanical checks can reject unsupported execution claims. They cannot prove
that a fetched page establishes authorship or that a plan captures every nuance.
Use a small semantic completion check selectively where needed and evaluate its
accuracy/cost. Do not invoke a separate classifier/planner/judge on every greeting.

For action-bearing requests, final-answer buffering needs a bounded policy so
an unsupported success claim is not streamed before its completion check. Retain
prompt live activity and honest partial output; avoid buffering ordinary chat.

### 4.4 Improve transport failures and waiting behavior

[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/) distinguish
connect/read/write/pool operations; its [exception hierarchy](https://www.python-httpx.org/exceptions/)
also distinguishes transport and protocol failures. These are usable categories,
not evidence that the session's unknown historical error was any one of them.

Capture safe error type, response/output phase, elapsed time, requested/actual model
when known, and retry eligibility. Add distinct connect, inactivity and total
request deadlines, with visible waiting/cancel state. Set numerical defaults from
measured local/cloud behavior; four minutes of silence should not be presented as
four minutes of demonstrated useful work. Preserve user control over slower local
loading/thinking instead of globally imposing a short cloud-oriented deadline.

Retry only where outcomes permit it. Partial output, uncertain remote execution,
quota/auth/policy rejection and a successful side effect require distinct handling.
Never repeat a write, submission or paid generation merely because no answer text
arrived. Cancellation must stop owned work and retain honest continuation state.

### 4.5 Keep planning and parallel work adaptive

An image source lookup usually needs one model selecting several successive
actions. Independent read-only lookups may run concurrently within a small bound;
dependent reasoning and conflicting edits must remain ordered. Existing subagents
are appropriate for separable work, without becoming compulsory supervisors.

Long implementations can reuse specialized workspace plans and validation-driven
repair. Grow a shared goal/evidence interface only after research and code paths
have equivalent tested needs. Avoid replacing working architecture wholesale.

## 5. Proposed delivery order and acceptance gates

These are new proposal labels, not authorization to start a previously restricted
phase or to implement this document now.

| Step | Deliverable | Gate before expanding scope |
| --- | --- | --- |
| M0 — Record the failure reliably | Compound-task fixtures, real CLI/TUI baseline; typed transport diagnostics/deadline design | Can distinguish skipped action, tool failure, transport failure and model limitation; no private data in logs |
| M1 — Complete compound goals | Minimal goal/entity/obligation state and bounded completion repair in the current loop | Image → lookup and “look them up” succeed or honestly report partial/blocked; ordinary chat stays direct |
| M2 — Discover and combine capabilities | Revisable tool exposure across built-ins, Skills and MCPs | Can discover a needed enabled capability outside the initial route; permissions and context bounds remain intact |
| M3 — Broader workflows and recovery | Research → edit → validate, task changes, resume, adapter and waiting improvements | Real outcomes improve across models; previous reliability fixes pass |
| M4 — Optional execution optimization | Bounded safe read parallelism/programmatic orchestration where supported | Measured token/latency gains with unchanged correctness, cancellation and authority boundaries |

Prototype the ordinary loop with task state first. Compare it against the same
loop with a selective semantic completion check. Use a mandatory separate planner
only as an evaluated alternative, not the initial default. Stop expanding if the
extra orchestration adds cost without improving real completion.

## 6. Evaluation required before claiming improvement

- Replay the exact two user requests with synthetic images and controlled search
  sources; accept equivalent valid strategies rather than one fixed tool order.
- Include paraphrases, spelling errors, pronouns and multi-turn corrections.
- Negative controls: greeting, exact `OK`, colors-only image question, no-search,
  read-only and tool-disabled requests. No irrelevant research or planning calls.
- Test file → instructions → implementation → validation, knowledge + web
  comparison, Skill-guided edits and MCP discovery with actual tool permissions.
- Retain the unchanged Stockroom CSV benchmark when modifying its orchestration;
  do not substitute a simplified coding task for it.
- Use the same prior small local text models (`qwen2.5-coder:3b`, `qwen3.5:4b`)
  where capabilities fit; use installed Gemma E2B/E4B for vision. Unsupported
  modality is a capability gap, not a failed vision reasoning trial.
- Compare a pinned explicit cloud model with the dynamic free router separately,
  only when credentials/budget and generation are authorized. Record actual route.
- Inject failed tools, stalls before headers, interrupted/partial streams and
  uncertain side effects. Test cancellation, resume and changed endpoint scopes.
- Keep plan approval, malformed-call/path recovery, dirty-worktree safety, cache
  invalidation, validation reruns and exit codes in the regression surface.
- Grade goal coverage, evidence relevance, false completion, correct tool/entity
  selection, duplicate reads/calls, recovery, model rounds, context growth, tokens,
  time to useful action and total p50/p95 latency. Include repeated live trials.

No benchmark, provider-quality comparison or implementation was run for this
research-only pass. Previously passing host tests do not establish that this
proposal improves model behavior. The first engineering task should be M0 plus
a narrowly reviewable M1 prototype against the observed failure, then comparison.
