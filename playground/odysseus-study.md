# How Odysseus keeps an agent oriented

Studied 2026-10-05. Repository: [odysseus-dev/odysseus](https://github.com/odysseus-dev/odysseus),
formerly pewdiepie-archdaemon/odysseus. Clone: `playground/odysseus`.
Curated `main` snapshot: `934d23c0be29c9721385f34565c0ae2cbd60da04`,
committed 2026-09-05. `dev` is the project's default development branch;
this study describes the pinned main snapshot. Validation also compared current
`dev`, `2992bf6d368a11472323e47d3bfed91e79cefc6b` (2026-10-01). The studied
orchestration files are identical except a `write_file` description; dev has
additional filesystem write safeguards that were not exercised here.

Scope: source inspection, helper probes, **468 focused upstream tests**, **23
real-module audit tests**, and bounded live Ollama checks with
`qwen2.5-coder:3b` and `qwen3.5:4b`. Dependencies were installed in an isolated
temporary environment. The browser/full application and CSV benchmark were not
run. These checks establish mechanisms and limitations, not superior task
completion. See [validation, coverage, and raw evidence](odysseus-validation.md).
Klaude production files and unrelated user changes were not edited.

## Answer

Much of the apparent remembering comes from **rebuilding the model's working
context from external state**. Odysseus keeps tool definitions, saved memories,
skill procedures, active editor state, and approved plans outside the model and
supplies selected information again while the relevant request path is active.
Some artifacts, especially approved plans, are not automatically restored on
every subsequent turn. This does not change the model's weights or
make its reasoning infallible.

It combines that context with narrowed tool choices, concise action contracts,
bounded recovery, optional verification, and optional stronger-model takeover.
The useful architecture is the selection and feedback loop. Its effectiveness
also depends on the endpoint's tool configuration and the model's call format.
The live 4B native-tool check worked; the 3B model failed the same small read task,
including with native schemas enabled. This is not a reliable control guarantee.

## Mechanisms traced in code

### 1. Tools are selected and declared for the current request

`src/tool_index.py:35`, `:302`, `:519`: a Chroma-backed index retrieves up to
eight relevant tool names. Keyword and structural hints add tools for named
domains. The base includes memory, clarification, and plan updates; selection can
remove competing tools, such as memory during a contact-save request. This is
deliberate reduction of choices, not universal exposure of every installed tool.

`src/agent_loop.py:845`, `:3886`, `:3983`, `:4358`, `:4771`: compact prompts list
the included tool names; API schemas carry arguments. Selection has bounded
timeouts and keyword fallbacks. Workspace requests switch to an explicit coding
toolset (18 names before route and availability filtering), dropping assistant
domains such as email and documents. Native API routes receive the schema list
on each tool round. Execution permissions are checked separately; an approval
requirement can leave the candidate schema visible. Domain instructions are
assembled from included tool names.

There is a local routing mismatch: Ollama with unknown/false `supports_tools`
gets the compact native-call prompt but no built-in schemas. Setting the
endpoint's `supports_tools=true` makes those schemas available. The real 3B run
then produced JSON-shaped tool text that the loop did not execute. Tool awareness
and an executable call are distinct. The 4B configured native route did execute.

The vector search is not the whole control mechanism: deterministic domain
selection and filtering remain important. Keyword fallback and intent detection
also have many specific heuristics, so this is not a universally general router.

### 2. Memory is retrieved and inserted, rather than remembered unaided

`src/chat_processor.py:90`, `:112`, `:158`, `:310`: at most five memory entries
are selected. A small set of pinned identity/contact facts has priority; other
pinned facts must be relevant. Remaining slots use BM25-inspired word relevance
plus optional vectors, with recency only a small tie breaker. Uses are recorded.
The selected facts are inserted as separate untrusted context messages.

This means a model can appear to remember a fact across sessions even when the
previous conversation is absent: the application retrieved and supplied it.
Vector retrieval is optional, with keyword behavior available when embeddings
are unavailable. The chat entry point also gates retrieval by preferences,
incognito/no-memory state, and request mode; it is not unconditional on every
message. Stored information is still data, not permission authority.

### 3. Skills supply actual procedures, with matching tools

`src/agent_loop.py:2619`, `:2897`: a short skill index advertises available
procedures; relevant skills can also contribute steps and pitfalls immediately.
Default injection is at most three matched skills. Full content/reference files
can be loaded through `manage_skills`. Skill content is separately wrapped as
untrusted data rather than merged into the trusted system instruction.

`src/agent_loop.py:4040`, `:5838`: selected and newly loaded skills can declare
`requires_toolsets`. Those dependencies are added to the subsequent selection,
subject to known tool identities, actual schemas, and execution policy. This
reduces mismatches for explicitly declared dependencies; it cannot guarantee
every tool named in free-form skill prose is available.

`services/memory/skills.py:584`, `:645`: the index filters by owner and status.
Platform filtering requires the caller to supply a platform; the main agent
index caller does not. Its toolset filter uses globally enabled built-ins,
not the precise current request schema set. Relevance is primarily Jaccard
token overlap, with tag, confidence, and usage adjustments.
The confidence gate applies to automatically matched draft procedures;
low-confidence teacher drafts remain advertised in the short index. The spec's claim that the
level-zero index is ownerless is stale: this snapshot passes `owner=owner`.

### 4. Plans and todo state are separate artifacts

`src/agent_loop.py:3381`, `:4340`: an approved checklist is explicitly pinned
ahead of the tool prompt. `update_plan` emits the complete updated checklist to
the frontend, which stores/displays it (`static/js/chat.js:3821`). The model's
tool result contains a completion count; its own call arguments retain the
checklist. The pinned system note still contains the original approved plan.
The frontend submits a pending approved plan separately from chat (`:1899`),
then clears that pending value. Later messages do not automatically submit the
stored checklist. This is a specific approved-plan execution path, not an
automatically maintained task ledger or evidence that a checked box was implemented.

`src/agent_tools/coding_tools.py:17`: `todowrite` persists a session JSON list
and enforces at most one `in_progress` item. Coding instructions ask for a
maintained todo list. I did not find an automatic source/validation evidence
ledger or automatic todo reinjection in the main loop. Todo persistence should
not be confused with independent completion verification.

### 5. Context is budgeted, trimmed, and sometimes summarized

`src/context_budget.py:28`: auto budget uses 85% of a known context window,
with a ceiling, while unknown windows use conservative defaults and explicit
caps are honored. The route applies output reserve and its own budget before
sending the request (`src/agent_loop.py:4209`).

`src/context_compactor.py:323`: near 85% context use, older conversation can
be summarized into goal, completed work, current state, pending work, and key
constraints. It uses a configured utility model or the current model and retains
recent messages. Failure leaves the history available for trimming. Compaction
is not universally called on every round: the route invokes it under deferred
context shaping or fallback conditions, with other callers owning pre-shaping.

`src/context_compactor.py:224`: trimming can drop extra context and older turns,
truncate a long system prompt, and shorten an oversized current message. A
sanitizer removes orphan tool messages/dangling calls. It is not a hard budget
guarantee: protected context and the recent-message protection branch can still
produce an oversized request. Message estimates omit separate native schemas.
The loop's `context_length` argument is a fallback, not a hard runtime cap;
the live runs reported 131072 despite supplying 4096. Summaries can lose facts,
and truncating arguments/instructions does not retain complete original evidence.

### 6. Recovery is bounded and optional teacher help can add capability

`src/agent_loop.py:4445`, `:5480`: short announced actions without calls receive
up to two nudges. Repeated no-progress calls force a tool-free final response;
the loop also has a round cap and a visible exhausted-rounds event.

`src/agent_loop.py:3285`, `:5440`: an optional fresh-context verifier compares
the request to a bounded actions snapshot and may ask for repairs twice. It is
off by default because weak models falsely rejected successful actions. Errors
or unrecognized verifier output return no failure reasons, so this is advisory,
not a dependable acceptance gate.

`src/teacher_escalation.py:514`, `src/settings.py:162`: with explicit teacher
configuration enabled, detected failure can trigger a visible stronger-model
takeover. A successful-looking teacher trace is distilled into a reusable skill;
saving it requires interactive approval. Teacher and tier-two evaluation are
off by default. The inline escalation path does not use the module's
`is_self_hosted` helper as a gate; explicit configuration still controls whether
it runs. This is additional inference from another model plus procedural
reuse, not the small model autonomously acquiring new reasoning ability.

The teacher success classifier is heuristic: absence of error phrases is not
proof of correctness. It does not inspect exit codes in its regex evaluation.
Both the helper probe and the imported real module classify
`{exit_code: 1, output: '3 failed, 8 passed'}` plus
`Done` as `ok`. Do not copy that criterion into Klaude's validation gate.

### 7. Some behavior is explicitly tailored to their model

`src/agent_loop.py:2207`, `:4075`: `odysseus-qwen3*` names receive special
temperature caps, minimal context builders, and document/notes tool clamps.
General turns may suppress all tools for that model path. This is evidence of
model-specific adaptation, not proof that generic 3B/4B coding models gain the
same behavior. Endpoint, model, fallback, teacher, and budgets must be matched
in any performance comparison.

## What is useful for Klaude

| Area | Current Klaude | Lesson / proposed experiment |
| --- | --- | --- |
| Tool awareness | Real per-request snapshots and canonical schemas already exist. | Keep them; reduce the choices again around the active execution subtask. |
| Skills | Enabled inventory and bounded on-demand `read_skill` already exist. | Test concise task-relevant procedures and explicit tool dependencies; do not inject every full skill or loosen permissions. |
| Plans | Model-authored scoped steps plus observed edits/check revisions, currently rebuilt per turn. | Persist a compact task record across turns; revise it against actual requirements and preserve user corrections. Checked boxes alone are insufficient. |
| Working source | Whole exchanges are omitted to bound context; reads can repeat and edit anchors are invented. | Maintain bounded current source excerpts keyed to actual file revisions, replace stale versions, and supply only the active files plus constraints/diagnostics. |
| Memory | Direct-code context uses a 2000-character prefix of `memory.facts()`; the general system prompt separately interpolates the full saved facts. | Select relevant saved facts in each path; keep task execution evidence separate from long-term preferences. |
| Completion | Known incomplete work and actual stale/failed checks block success; one-shot exits honestly. | Reserve validation/repair opportunities before the limit instead of spending every step on reads/edits. Preserve execution-based checking. |
| Stronger help | Model selection is explicit; children currently read-only. | Teacher help would be a separately disclosed, opt-in feature, not evidence that unchanged local models passed. |

**Recommended next implementation experiment:** phase-scoped working context,
current source snapshots, and reserved validation/repair, on the unchanged CSV
fixture and the same two models/budgets. That directly addresses the failures
documented in `docs/small-model-evaluation.md`. Extra reminders, broad embeddings
in the critical path, or mandatory self-verification calls are not yet justified.

## Probe evidence and limits

The follow-up [validation report](odysseus-validation.md) records imported-module
tests, upstream coverage, live outcomes, reproducible commands, and remaining gaps.

Run `python3 playground/odysseus-probes.py`. The script AST-extracts inspected
helpers into an isolated namespace; it does not import the application, load real
memories, contact an embedding backend, or execute tools/model calls.

- Keyword-only selection keeps the three base tools for a greeting; URL and
  schedule requests expose their tools; contact-save removes competing memory.
- Memory selection retains identity and the relevant PostgreSQL preference while
  excluding an unrelated garden fact.
- Input budget helper returns 6000 for unknown context, 6963 for 8K, 13926 for
  16K, and 4096 for an explicit 4096 cap. Output reserve is applied later.
- Approved-plan construction retains the complete supplied checklist.
- The regex teacher classifier recognizes explicit errors but misses the
  nonzero-exit example above.

These probes validate helper behavior, not live model performance, service
integration, whole-app correctness, or superiority on the implementation task.

## Pinned upstream sources

- [Agent loop](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/agent_loop.py)
- [Tool selection](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/tool_index.py)
- [Memory context](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/chat_processor.py)
- [Context compaction](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/context_compactor.py)
- [Teacher escalation](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/teacher_escalation.py)

The upstream clone is an ignored research checkout. The validated research
artifacts are checkpointed separately from unrelated Settings changes. No
agent architecture changes were implemented during this study.
