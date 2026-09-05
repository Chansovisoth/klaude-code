# Klaude-Code Frontier Search & Deep Research — Revised Phases 4–7

## Canonical checkpoint this revision assumes

Current canonical branch:

```text
master
```

Current checkpoint commit:

```text
779b7b6 feat: harden model-led retrieval and runtime resilience
```

This document intentionally revises **only Phases 4–7**.

Phases 1–3 are considered complete and already established the following invariants:

```text
USER
 ↓
MODEL
 ├─ answer directly
 ├─ web_search
 ├─ fetch_url
 └─ knowledge tools
      ↓
HOST/RUNTIME ONLY ENFORCES
- safety
- budgets
- dedupe
- provider fallback
- provenance
- protocol correctness
- context management
```

The host must NOT synthesize or force retrieval merely because a prompt looks searchable.

Examples:

```text
Reply with exactly: OK
→ direct model answer
→ no forced tool use
```

```text
What is Python?
→ model may answer directly
```

```text
What is the latest stable Python version?
→ freshness matters
→ model decides whether current web evidence is needed
→ model may call web_search
```

The permanent invariant from this checkpoint onward is:

> Structured semantics may inform the model, but they must never become a host-side automatic retrieval router.

Other completed reliability work that must be preserved:

- valid Ollama tool sequencing;
- no fake host-generated tool messages;
- top-level Ollama `think` support;
- `qwen3.5:*` defaults to `think = false` unless explicitly overridden;
- one-time recovery when the model returns neither prose nor a tool call;
- runtime error persistence in session history;
- long fenced-code continuation after genuine output-limit stops;
- configurable `[ollama.options] num_predict`;
- configurable `[agent] max_code_continuations`;
- conversation-context compaction before Ollama silently truncates arbitrary old history;
- canonical system prompt / newest turn / entity state preservation;
- actionable CUDA runner failure messaging.

Do not regress any of these behaviors.

---

# Global Rules for Phases 4–7

Before editing in any phase:

1. Run `git status`.
2. Review the entire current diff.
3. Preserve unrelated dirty-worktree changes.
4. Do NOT:
   - commit;
   - push;
   - stash;
   - reset;
   - checkout/discard unrelated files;
   - overwrite user work.
5. Do not automatically continue into the next phase.
6. Run focused tests first, then broader relevant tests.
7. Clearly separate new failures from pre-existing issues.
8. Keep local-model context pressure in mind, especially for `qwen3.5:4b`.

## Anti-overfitting / anti-cheating rule

Do not hardcode example entities, domains, expected answers, or fixture-specific search logic into production code.

Examples such as:

```text
AIS
American Intercon School
PIU
Paragon International University
Rhett and Link
Cambodia
Asteron Labs
Nova Meridian Academy
Testland
```

may appear in tests.

Production behavior must derive from generic semantics, conversation state, entity aliases, normalization, location, relationship semantics, search evidence, fetched evidence, and model decisions.

If replacing the example names with unseen entities of the same semantic shape breaks the behavior, the implementation is overfit.

---

# PHASE 4 — Compact Structured InformationNeed Without Forced Retrieval

## Goal

Introduce a compact, conversation-aware semantic representation of what the user is asking for.

This object should improve:

```text
conversation continuity
entity/relationship resolution
model context
search-query quality
freshness awareness
discovery cardinality
later deep-research planning
```

but it must NOT become another deterministic host-side retrieval router.

The correct high-level flow is:

```text
raw user request
↓
safe normalization + conversation/entity context
↓
compact InformationNeed
↓
MODEL
 ├─ answer directly
 ├─ use knowledge tools
 ├─ web_search
 ├─ fetch_url
 └─ finish
```

NOT:

```text
InformationNeed
→ host decides "search required"
→ automatic web_search
```

That old pattern is explicitly prohibited.

---

## 1. First-class `InformationNeed`

Create a compact structured semantic type.

Adapt to existing project conventions, but conceptually capture:

```python
InformationNeed(
    mode=...,
    entity=...,
    category=...,
    topic=...,
    relationship=...,
    role=...,
    locations=[...],
    freshness=...,
    desired_count=...,
    comparison_targets=[...],
    constraints=[...],
    original_text=...,
    normalized_text=...,
    provenance=...,
)
```

Do not mechanically copy this exact schema if a smaller representation fits better.

Because `qwen3.5:4b` is an important target, keep the model-facing form concise.

---

## 2. Keep modes small

Recommended broad modes:

```text
LOOKUP
DISCOVERY
RESEARCH
```

Do not create:

```text
STARTUP_DISCOVERY
SCHOOL_LOOKUP
PERSON_LOOKUP
SOFTWARE_LOOKUP
LOCAL_RESTAURANT_DISCOVERY
...
```

Mode describes the shape of the information need, not whether a tool must be used.

### LOOKUP

One main target/fact/relationship.

Examples:

```text
What is OpenAI?
Who founded ExampleCo?
Who is its chairman?
Where is University X?
What is the latest stable version of ExampleLib?
```

Important:

```text
LOOKUP != MUST SEARCH
```

The model may answer directly when appropriate.

### DISCOVERY

Multiple candidates/options satisfying constraints.

Examples:

```text
show me some startups in Cambodia
find restaurants in Bangkok
list universities in Singapore
find Rust GUI libraries
show open-source note-taking apps
```

Important:

```text
DISCOVERY != HOST AUTO-SEARCH
```

The model decides whether web search, local knowledge, another tool, or direct response is appropriate.

### RESEARCH

Broad investigation/comparison/synthesis.

Examples:

```text
research Cambodia's startup ecosystem
compare Cambodia and Vietnam startup ecosystems
investigate how project X implements feature Y
give me a comprehensive overview of protocol Z
```

Do not start planner/subagent deep research yet.

Phase 6 consumes this mode.

---

## 3. `InformationNeed` is semantic context, not an action plan

This distinction is critical.

Bad:

```python
if info.mode == DISCOVERY:
    run_web_search(...)
```

Bad:

```python
if info.freshness == "current":
    force_web_search = True
```

Bad:

```python
if info.relationship == "chairman":
    query = f"{info.entity} chairman"
    run_web_search(query)
```

Correct:

```text
InformationNeed
→ compactly exposed to the model
→ model decides whether any tool is needed
→ if searching, model chooses the actual query
```

Host logic may:

```text
validate tool calls
enforce budgets
dedupe queries
route providers
protect URLs
```

but must not become the semantic search planner.

---

## 4. Preserve trivial direct-answer behavior

Add regression coverage that ensures semantic parsing does not trigger retrieval.

Examples:

```text
Reply with exactly: OK
→ no retrieval
```

```text
Say hello
→ no retrieval
```

```text
Rewrite this sentence: ...
→ no retrieval
```

Even if an `InformationNeed` object exists internally, it must not force a tool call.

This is a hard regression test.

---

## 5. Build semantics from multiple evidence sources

Use, where available:

```text
current user text
normalized text
active conversation entity
known aliases
previous successful entity resolution
relationship-slot semantics
explicit user constraints
runtime/explicit location
freshness language
plural/list/cardinality language
comparison language
```

Do not derive everything from the literal current sentence.

---

## 6. Conversation follow-up invariant

Example:

```text
Turn 1:
What is AIS Cambodia?

resolved active entity:
American Intercon School
```

Then:

```text
Turn 2:
Who was the chairman?
```

Should resolve approximately to:

```text
mode = LOOKUP
entity = American Intercon School
relationship = leadership
role = chairman
location = Cambodia
```

NOT:

```text
entity = chairman
```

and NOT:

```text
entity = "the chairman"
```

A relationship/attribute phrase must never replace a confidently resolved active entity.

---

## 7. Centralize relationship semantics

Create or consolidate one generic relationship semantic layer.

Normalize concepts such as:

```text
identity
leadership
founder
ownership
location
release_version
```

Optional role detail:

```text
relationship = leadership
role = chairman
```

Recognize useful lexical signals such as:

```text
chair
chairman
chairwoman
chairperson
president
principal
director
dean
rector
head
CEO
founder
founded
established
owner
owned by
where
headquarters
based
campus
address
latest version
stable version
release
```

Do not maintain multiple overlapping vocabularies across unrelated helper functions.

---

## 8. Normalize before semantic construction

Preferred flow:

```text
raw text
↓
safe typo/name normalization hints
↓
conversation/entity resolution
↓
InformationNeed
↓
model-led tool loop
```

Preserve:

```text
original_text
normalized_text
correction provenance
```

Low-confidence fuzzy matches must remain candidates/hints.

Do not silently rewrite arbitrary legitimate proper nouns.

---

## 9. Discovery semantics

For:

```text
show me some startups in Cambodia
```

represent roughly:

```text
mode: DISCOVERY
category/topic: startup
location: Cambodia
desired_count: None or central bounded default
```

Do NOT create:

```text
entity = "startups in Cambodia"
```

For:

```text
find Rust game engines
```

represent roughly:

```text
mode: DISCOVERY
category/topic: game engine
constraint: Rust
```

---

## 10. Cardinality

Recognize explicit counts:

```text
show me 5 startups
top 10 libraries
give me three alternatives
```

Store structurally.

For vague language:

```text
some
a few
several
```

either leave unspecified or use a central bounded policy.

Do not hide result-count assumptions inside generated search strings.

---

## 11. Comparison

Recognize:

```text
compare X and Y
X vs Y
differences between A and B
```

Store targets structurally.

Example:

```text
compare Cambodia and Vietnam startup ecosystems
```

might become:

```text
mode: RESEARCH
topic: startup ecosystem
comparison_targets:
- Cambodia
- Vietnam
```

Do not launch deep research yet.

---

## 12. Freshness

Represent freshness semantically:

```text
latest
current
today
recent
stable version
current CEO
```

But preserve the model-led rule:

```text
freshness matters
→ model is informed
→ model decides whether web search is necessary
```

Do NOT implement:

```text
freshness != None
→ automatic web_search
```

---

## 13. Generic location

Support arbitrary locations.

Do not make Cambodia the architecture.

Reuse existing explicit/runtime location context for:

```text
in Cambodia
in Bangkok
near me
in my city
within Thailand
```

---

## 14. Provenance

Track meaningful sources for semantic fields:

```text
current_user_text
conversation_active_entity
runtime_location
explicit_location
fuzzy_normalization
model_semantic_inference
```

Prefer provenance labels over fake confidence decimals.

---

## 15. Integrate compactly into `AgenticSearchState`

Add the semantic object or a compact reference to existing Phase 3 state.

Avoid duplicating equivalent semantics in multiple structures.

For the model, prefer concise context like:

```text
Information need:
Mode: discovery
Category: startup
Location: Cambodia
Desired results: several
```

or:

```text
Information need:
Mode: lookup
Entity: American Intercon School
Relationship: leadership
Role: chairman
Location: Cambodia
```

Do not dump large serialized objects.

---

## 16. Preserve local-model context efficiency

Because `qwen3.5:4b` is a primary interactive model:

- keep semantic summaries short;
- avoid verbose duplicated schema text every turn;
- avoid unconditional semantic-classifier model calls;
- reuse deterministic resolution when confidence is high;
- compact stale semantic state with the rest of conversation context;
- preserve active entity state separately from stale transcript prose.

Do not undo the existing conversation compaction work.

---

## 17. `SearchIntent` compatibility

Do not necessarily delete existing lower-level routing abstractions.

Prefer:

```text
InformationNeed = high-level semantic context
SearchIntent = provider/search-layer compatibility hint where still needed
```

Avoid independently classifying both in incompatible ways.

But most importantly:

> Neither `InformationNeed` nor `SearchIntent` may automatically trigger retrieval.

The model remains the decision-maker.

---

## 18. Deterministic vs model semantic inference

Deterministic code is appropriate for obvious:

```text
numeric counts
explicit location
active entity
known aliases
clear relationship terms
comparison syntax
freshness markers
```

Use model inference only for genuinely ambiguous semantics.

Do not add an unconditional extra LLM classification call to every simple user message.

---

## 19. Ambiguity

For:

```text
Tell me about Mercury
```

do not force a popular meaning.

Represent unresolved ambiguity and allow the model to answer from context, ask for clarification, use local knowledge, or search if it decides that is useful.

Do not automatically search solely because the term is ambiguous.

---

## 20. Tests

Add/adjust tests for:

### Direct no-tool behavior

```text
Reply with exactly: OK
Say hello
Rewrite this sentence
```

Assert no host-forced retrieval.

### LOOKUP

```text
Who founded ExampleCorp?
Where is Example University?
What is Project Alpha?
What is the latest stable version of ExampleLib?
```

Assert semantic structure, not forced tool calls.

### DISCOVERY

```text
show me some startups in Testland
find restaurants in Example City
list universities in Sampleland
find Rust GUI libraries
```

Assert no fake single entity.

### RESEARCH

```text
research the robotics ecosystem in Testland
compare Country A and Country B startup ecosystems
```

Assert RESEARCH semantics without starting Phase 6.

### Follow-up

```text
What is Nova Meridian Academy?
Who was the chairman?
Who founded it?
Where is its main campus?
Who is the director?
```

Assert active entity preservation.

### Typo/name normalization

Preserve original/normalized/provenance.

Protect valid names such as:

```text
Qwen
Hyprland
DeepSeek
OpenAI
NumPy
PyTorch
FlazeSlayer
```

### Cardinality / comparison / freshness / ambiguity

Test semantic capture without asserting automatic retrieval.

---

## 21. Final report for Phase 4

Report:

- final `InformationNeed` structure;
- compact model-facing representation;
- mode semantics;
- relationship semantics;
- conversation follow-up behavior;
- original vs normalized text;
- provenance;
- how direct answers remain possible;
- proof that neither `InformationNeed` nor freshness automatically triggers search;
- local-model context-cost considerations;
- SearchIntent compatibility;
- tests/results;
- existing issues;
- Phase 5 readiness.

Do not start Phase 5.

---

# PHASE 5 — Compact Evidence, Claims, Verification, and Structural Citations

## Goal

Build a structured evidence/claim layer on top of the existing source registry while preserving model-led retrieval.

Important architectural rule:

> Evidence/claim machinery evaluates what has been gathered. It must not itself force browsing.

Correct:

```text
model decides to search/fetch
↓
runtime/source registry records evidence
↓
claim/evidence layer evaluates support
↓
model may decide another tool call is useful
```

Incorrect:

```text
claim verifier sees weak support
→ host automatically web_searches
```

Any further retrieval remains model-initiated unless a later explicit deep-research orchestrator phase owns a bounded researcher loop.

---

## 1. Reuse the existing source registry

Do not create a parallel source storage system.

Build on existing:

```text
search_result_NNN
src_NNN
canonical URL
fetch metadata
provenance
cache
```

---

## 2. Evidence representation

Create a compact evidence structure conceptually containing:

```text
source_id
relevant excerpt/reference
claim/topic relation
source quality hint
freshness metadata
```

Avoid duplicating full page content.

Because local-model context is constrained, store rich detail internally and expose compact summaries to the model.

---

## 3. Claim representation

Conceptually:

```text
claim ID
claim text
claim type
supporting source IDs
verification status
freshness requirement
conflict state
```

Examples:

```text
ExampleCo was founded in 2021.
Company X operates in Cambodia.
The current CEO is Y.
Version 4.2 is the latest stable release.
```

Do not overcomplicate schema if simpler types fit the repository.

---

## 4. Search leads vs fetched evidence vs verified claims

Preserve a clear hierarchy:

```text
SERP snippet
= discovery lead

fetched document
= stronger source evidence

verified claim
= supported proposition used confidently in final answer
```

Do not regress into strict claim verification before the model can inspect useful sources.

---

## 5. Source quality

Use source quality as a confidence signal, not a blanket visibility gate.

Possible ordering:

```text
official/primary
government/standards
major reputable reporting
industry publication
blog
forum/social
```

Weak sources can discover leads.

Important claims should prefer strong evidence.

---

## 6. Claim-sensitive freshness

Freshness depends on claim type.

Examples:

```text
founding date          stable
location               relatively stable
current CEO            dynamic
latest software        highly dynamic
breaking news          extremely dynamic
```

Do not use one query-level freshness rule for every claim.

---

## 7. Structural citations

Source IDs are runtime-generated.

The model must not invent citation IDs.

The final renderer should accept only registered source IDs.

Reject/impossible:

```text
src_999
```

if it does not exist.

This must work even when the model is small.

Prefer deterministic validation at the renderer/runtime boundary.

---

## 8. Conflict handling

When sources disagree, evaluate:

```text
publication date
primary-source status
source authority
freshness
independence
```

Represent unresolved conflicts when necessary.

Do not silently pick whichever appeared first.

---

## 9. Discovery candidate identity

For discovery tasks, distinguish:

```text
3 pages about Company A
```

from:

```text
3 distinct companies
```

Use generic identity clues and source/entity metadata.

Do not create hardcoded company lists.

---

## 10. Model-led retrieval remains intact

This phase must not reintroduce host-forced retrieval.

Examples:

```text
Claim support weak
→ expose uncertainty/evidence gap to model
→ model decides whether to search/fetch again
```

not:

```text
Claim support weak
→ Python automatically searches
```

For ordinary Phase 3/4 interaction, this boundary is mandatory.

---

## 11. Compact model context

Do not dump every claim/evidence object into Qwen.

Prefer short summaries such as:

```text
Known evidence:
- Claim c_001 supported by src_001 (primary)
- Claim c_002 supported by src_003 (secondary, recent)
- Claim c_003 conflicting: src_004 vs src_005
```

Keep full data internal.

Integrate with conversation compaction so stale evidence prose is not repeatedly replayed when compact structured state can be preserved instead.

---

## 12. Final-answer validation

Before rendering:

- every cited source must exist;
- every structural citation must resolve;
- unsupported/high-risk claims should be marked uncertain or omitted according to policy;
- no citation may be fabricated by free-form prose.

Do not require every casual sentence to become a formal claim object if that makes responses unnatural.

Focus structural verification on externally sourced factual claims.

---

## 13. Tests

Cover:

1. Discovery source → candidate.
2. Candidate → stronger fetched evidence.
3. Unsupported claim remains uncertain/rejected.
4. Registered source IDs only.
5. Duplicate source reuse.
6. Fake citation ID rejected.
7. Current leadership requires fresher evidence than founding date.
8. Weak source useful for discovery but not conclusive.
9. Conflicting sources.
10. Multiple pages for one entity do not count as multiple discovery candidates.
11. Evidence gap does not automatically trigger host-side search.
12. Model may choose another web action after receiving an evidence-gap summary.
13. Compact evidence state survives context compaction appropriately.
14. Synthetic unseen entities.

---

## 14. Final report for Phase 5

Report:

- evidence/claim structures;
- source-registry reuse;
- freshness model;
- conflict handling;
- citation validation;
- discovery identity handling;
- compact local-model representation;
- proof that evidence verification does not force retrieval;
- tests/results;
- Phase 6 readiness.

Do not start Phase 6.

---

# PHASE 6 — GPT-Researcher-Style Deep Research With Local-Model-Safe Contexts

## Goal

Add a dedicated deep-research execution path for genuinely broad RESEARCH tasks.

Architecture:

```text
RESEARCH InformationNeed
↓
model-led decision to enter deep research
↓
planner
↓
focused research questions
↓
bounded focused researchers
↓
shared evidence/claims
↓
coverage evaluator
↓
targeted follow-up if needed
↓
writer/synthesizer
```

Critical new checkpoint rule:

> The presence of `mode = RESEARCH` alone must not silently force deep research.

The top-level model/orchestrator should decide whether the user request warrants the deep-research path, unless the user explicitly requested research/deep investigation.

Examples:

```text
"Research X comprehensively"
→ deep research is strongly indicated
```

```text
"Tell me about X"
→ RESEARCH classification should not automatically happen merely because X is broad
```

Do not rebuild host-forced retrieval at a larger scale.

---

## 1. Explicit deep-research entry decision

Implement a clear decision boundary.

Deep research may be entered when:

- the user explicitly asks for research, investigation, comprehensive comparison, etc.; or
- the model explicitly selects the deep-research capability based on semantic context.

Avoid:

```text
InformationNeed.mode == RESEARCH
→ Python automatically launches subagents
```

unless the user explicitly requested that behavior and project policy intentionally treats it as authorization.

Prefer model/tool-mediated entry.

---

## 2. Planner

Input:

```text
original request
compact InformationNeed
relevant active entity/context
current known evidence if any
```

Output a bounded set of focused research questions.

Conceptually:

```text
question
purpose
dependencies
```

Do not request chain-of-thought.

Use concise functional planning fields.

Because Qwen 3.5 4B is a target, keep planner output compact.

---

## 3. Researcher contexts must be focused

This is especially important for local-model reliability.

Each researcher should receive only:

```text
one focused question
minimal relevant semantic context
tool schemas actually needed
compact source/evidence state
```

Do NOT give every researcher the entire long conversation and every tool schema.

This helps prevent:

```text
40k-token prompts
silent message dropping
CUDA stress
small-model confusion
```

The existing conversation compaction work should be reused.

---

## 4. Progressive / minimal tool exposure

Strongly prefer that research workers see only tools they need.

Typical researcher:

```text
web_search
fetch_url
finish
```

If a knowledge tool is genuinely needed, expose it deliberately.

Do not expose unrelated shell/code/filesystem tools merely because they exist globally.

Consider progressive tool exposure if tool schemas materially increase prompt pressure.

Do not over-engineer a full tool-discovery marketplace in this phase unless necessary.

---

## 5. Parallel vs sequential research

Run independent questions concurrently.

Keep dependent questions sequential.

Examples of independent:

```text
Cambodian startup landscape
Cambodian funding environment
Vietnam startup landscape
Vietnam funding environment
```

Example dependent:

```text
identify what AIS refers to
→ then investigate leadership of the resolved entity
```

Do not parallelize dependent semantic steps.

---

## 6. Per-researcher bounded loop

Each researcher uses the already-built model-led loop:

```text
web_search
→ inspect
→ fetch_url
→ assess
→ refine or finish
```

Researchers do not receive a host-generated first search.

They must initiate their own web tool actions.

Do not reintroduce automatic search inside workers.

---

## 7. Shared source/evidence infrastructure

All researchers should share or reconcile against the same canonical source registry/evidence store.

Avoid:

```text
same URL
→ src_001 in researcher A
→ src_001 unrelated in researcher B
```

Use stable global/task-scoped source identity.

Deduplicate claims and sources where practical.

---

## 8. Researcher output compression

Researchers should return compact findings:

```text
question
summary
claim IDs
source IDs
unresolved gaps
```

Do not dump full pages into the parent writer.

This is essential for local models and GPU/context pressure.

---

## 9. Budgets

Central config should bound:

```text
max_subquestions
max_parallel_researchers
max_searches_per_researcher
max_fetches_per_researcher
max_research_rounds
max_total_sources
max_total_claims
```

Also respect existing:

```text
max_web_actions
max_consecutive_failures
query dedupe
fetch dedupe
```

Never allow unbounded recursive research.

---

## 10. Coverage evaluator

After first round, evaluate:

```text
sufficient
missing information
weak claims
conflicting claims
```

The evaluator must not automatically browse.

It may recommend:

```text
targeted follow-up question(s)
```

The orchestrator/model then decides whether another bounded research round is justified and allowed.

Avoid:

```text
coverage insufficient
→ host silently starts more searches
```

Keep model/orchestrator agency.

---

## 11. Targeted follow-up only

If another round occurs, research only the unresolved gaps.

Do not restart all original researchers.

Example:

```text
Missing:
current 2026 funding data for Cambodia
```

Launch one focused follow-up.

---

## 12. Writer/synthesizer

The final writer receives only compact relevant material:

```text
original request
InformationNeed
research findings
verified claims
source registry summaries
coverage assessment
known limitations
```

Do not give it entire raw web pages unless absolutely necessary.

The writer should not arbitrarily browse outside the orchestrated research loop.

If new browsing is truly needed, route it through the research/evaluation loop.

---

## 13. Empty-response resilience

Preserve the Phase 3/runtime reliability behavior in subagents and writer calls.

If a model returns neither prose nor a tool call:

- use the existing one-time recovery mechanism;
- do not inject fake tool messages;
- preserve valid Ollama sequencing.

Do not create separate inconsistent recovery behavior inside deep research.

---

## 14. Output-limit continuation

If researchers/writer produce long fenced code and hit a genuine output limit:

- reuse the existing fenced-code continuation mechanism;
- respect `max_code_continuations`;
- continue from exact cutoff;
- do not repeat fences/code.

Do not create a competing continuation system.

---

## 15. Failure handling

One failed researcher must not fail the whole research task.

Record:

```text
question
failure reason
partial findings
```

Coverage evaluator decides materiality.

Provider/CUDA/runtime failures must remain distinguishable.

Do not misclassify a CUDA runner crash as "research found nothing."

---

## 16. Tests

Cover:

### Entry behavior

```text
Reply with exactly: OK
→ no deep research
```

```text
What is Python?
→ no automatic deep research
```

```text
Research X comprehensively
→ deep-research path can be selected
```

### Planner

Bounded, compact questions.

### Worker tool behavior

Researchers initiate their own `web_search`.

No host-generated initial search.

### Parallelism

Independent questions parallel.

Dependent questions sequential.

### Context bounds

Workers receive compact context, not full stale transcript.

### Budgets

Per-worker/global bounds enforced.

### Coverage

Evaluator recommends targeted follow-up only.

### Failure

One worker fails, task can still complete.

### Empty response

Valid recovery without fake tool sequencing.

### Source integrity

Writer only cites registered sources.

### No forced second round

Insufficient coverage recommendation does not itself perform host-forced retrieval.

### Simple lookup/discovery

Normal chat stays on fast path unless model/user explicitly chooses deep research.

---

## 17. Manual validation when environment permits

Use real local-model scenarios after a clean Ollama restart:

```text
direct answer
explicit current-fact search
search → fetch → final prose
broad deep research
long code output
```

For deep research, inspect prompt/context sizes.

Do not accept a design that routinely produces giant worker prompts.

---

## 18. Final report for Phase 6

Report:

- deep-research entry decision;
- how host-forced research was prevented;
- planner structure;
- worker context minimization;
- progressive/minimal tool exposure;
- parallel/dependent scheduling;
- budgets;
- shared source/evidence registry;
- coverage evaluation;
- follow-up policy;
- writer context;
- empty-response/tool-sequencing resilience;
- context-compaction behavior;
- tests/results;
- Phase 7 readiness.

Do not start Phase 7.

---

# PHASE 7 — Frontier Hardening, Local-Model Evals, and Shortcut Cleanup

## Goal

Stabilize the complete architecture around the new canonical model-led principle.

Audit:

```text
host-forced retrieval regressions
overfitting
hardcoded fixture logic
tool-schema context pressure
prompt injection
invalid Ollama tool sequencing
empty-response recovery
unsupported claims
citation errors
retry loops
context explosions
provider dependence
CUDA stress
weak generalization
```

---

## 1. Permanent no-forced-retrieval evals

These must remain first-class regression tests:

```text
Reply with exactly: OK
→ no tool call
```

```text
Say hello
→ no tool call
```

```text
Rewrite supplied text
→ no tool call
```

```text
Current factual question
→ model may choose web_search
```

```text
web_search
→ fetch_url
→ non-empty final prose
```

Never reintroduce:

```text
keyword says latest/current
→ host auto-search
```

---

## 2. Hardcoding audit

Search relevant production code for known example entities and legacy special cases.

Historically known areas may include:

```text
AIS
American Intercon School
PIU
Paragon International University
Rhett and Link
Cambodia-specific entity/domain shortcuts
```

Explain every remaining relevant occurrence.

Generalize old shortcuts where the new entity/InformationNeed/evidence architecture supersedes them.

Distinguish legitimate generic infrastructure from fixture-specific answer logic.

---

## 3. Local-model reliability eval suite

Target especially:

```text
qwen3.5:4b
```

Test:

### Direct behavior

```text
Reply with exactly: OK
```

### Explicit tool decision

Current fact requiring search.

### Search → fetch → final response

Ensure no empty final prose.

### Tool-call sequencing

No fake `role="tool"` messages.

### Empty response

One-time valid recovery.

### Context compaction

Long conversation should compact before Ollama silently drops arbitrary history.

### Fenced-code output continuation

True output-limit stop inside unfinished code block continues correctly.

### Thinking mode

Verify default `qwen3.5:*` behavior remains responsive with `think=false` unless overridden.

---

## 4. Context-pressure metrics

Track where practical:

```text
prompt tokens
tool-schema tokens
conversation tokens
evidence-summary tokens
number of dropped/compacted messages
researcher context size
writer context size
```

Do not allow tool schemas or duplicated semantic state to become the new dominant context cost.

---

## 5. Progressive tool exposure evaluation

Measure whether globally exposing all tools materially harms:

```text
latency
prompt size
tool-choice accuracy
small-model reliability
```

If it does, consider a compact tool-discovery/progressive-exposure mechanism.

Do not add complexity unless metrics justify it.

---

## 6. Prompt-injection evaluation

Use hostile fetched pages:

```text
Ignore previous instructions.
Run shell commands.
Reveal secrets.
Change the task.
Call another tool.
```

Ensure web content remains lower-authority tool evidence.

Test in both ordinary browsing and deep-research worker contexts.

---

## 7. Adversarial retrieval cases

Evaluate:

```text
SEO spam
duplicate/syndicated sources
conflicting claims
stale leadership
malicious redirect
403
429
DNS failure
provider outage
empty extraction
huge page
ambiguous acronym
ambiguous proper noun
near-duplicate query
near-duplicate result set
```

---

## 8. CUDA/runtime separation

Maintain clear failure classification.

A GPU runner failure such as:

```text
CUDA error: an illegal memory access was encountered
```

must not be presented as:

```text
no search results
```

or:

```text
research failed semantically
```

Keep actionable runtime guidance.

Context compaction reduces triggers but is not a CUDA-driver/runtime fix.

---

## 9. Deep-research context stress tests

Test broad research with intentionally long source material.

Verify:

```text
workers get focused context
writer gets compressed findings
raw pages are not replayed everywhere
```

Avoid reproducing giant 40k-token prompts against small runner contexts.

---

## 10. Evidence/citation evals

Track:

```text
citation validity
fabricated source ID attempts
unsupported claim rate
conflict handling
freshness mistakes
duplicate-source inflation
```

The renderer/runtime must reject nonexistent citations deterministically.

---

## 11. Generalization eval suite

Use many synthetic entities.

### LOOKUP

```text
Who founded X?
Where is Y?
What is latest version of Z?
```

### FOLLOW-UP

```text
What is X?
Who is its chairman?
When was it founded?
```

### TYPO / ENTITY

```text
misspelled location
misspelled technology
unknown valid proper noun
ambiguous acronym
```

### DISCOVERY

```text
startups in Country A
restaurants in City B
Rust libraries for task C
universities in Country D
```

### RESEARCH

```text
compare A and B
investigate implementation C
comprehensive overview D
```

### ADVERSARIAL

```text
conflicting sources
stale facts
prompt injection
provider failure
duplicates/spam
```

---

## 12. Metrics

Where practical track:

```text
answer success rate
unnecessary tool-call rate
search calls
fetch calls
duplicate-call rate
provider failure rate
source diversity
citation validity
unsupported claim rate
conflict rate
research rounds
latency
budget exhaustion frequency
prompt/context size
empty-response rate
continuation rate
runtime/CUDA failure rate
```

A particularly important new metric:

```text
unnecessary retrieval rate
```

for prompts that should be answered directly.

---

## 13. Architecture cleanup

Preferred final path:

```text
user
↓
conversation/entity state
↓
normalization
↓
compact InformationNeed
↓
MODEL
 ├─ direct answer
 ├─ knowledge tool
 ├─ fast web tool loop
 └─ explicit/model-selected deep research
      ↓
source/evidence registry
↓
claim verification
↓
synthesis
↓
structural citations
```

The host must remain thin.

Remove obsolete host-side automatic routing logic if any remains.

Do not remove useful safety/budget/provenance infrastructure.

---

## 14. Documentation

Document the final responsibility split.

### Model

Decides:

```text
whether a tool is needed
what information is missing
what to search
how to refine
which source to read
whether deep research is warranted
when enough evidence exists
how to synthesize
```

### Runtime

Enforces:

```text
tool protocol correctness
permissions
provider routing
timeouts
network safety
SSRF protection
budgets
dedupe
retry limits
cache
source IDs
citation validity
parallelism bounds
context compaction
termination
runtime error reporting
```

### Provider layer

Provides:

```text
search/fetch capabilities
metadata
health/fallback
```

It is not the semantic brain.

### Evidence layer

Handles:

```text
source identity
source dedupe
claim support
freshness
corroboration
conflict
citation integrity
```

---

## 15. Full validation

Run the broadest reasonable:

```text
unit tests
agent/tool-loop tests
search tests
fetch tests
source/evidence tests
entity/conversation tests
deep-research tests
CLI tests
lint
format checks
type checks
byte compilation
git diff --check
```

Clearly report known boundaries such as:

```text
LanceDB hang
legacy mypy backlog
environment DNS/provider availability
Ollama/SearXNG service availability
CUDA instability
```

Do not misattribute them.

---

## 16. Final report for Phase 7

Provide:

- final architecture;
- proof host-forced retrieval is gone;
- InformationNeed role;
- fast browsing path;
- deep-research entry path;
- local-model context strategy;
- tool exposure strategy;
- source/evidence/claim/citation model;
- runtime/tool-sequencing reliability;
- context compaction;
- long-code continuation;
- provider/runtime failure handling;
- remaining hardcoded exceptions;
- eval metrics/results;
- known limitations;
- recommended future work.

Do not commit or push unless explicitly instructed.

---

# Final Target Architecture

```text
                               USER
                                │
                                ▼
                    Conversation / Entity State
                                │
                                ▼
                    Normalization / Entity Hints
                                │
                                ▼
                    Compact InformationNeed
                                │
                                ▼
                              MODEL
                ┌───────────────┼────────────────┐
                │               │                │
         Direct Answer      Fast Tool Loop   Deep Research
                                │                │
                           web_search         Planner
                                │                │
                           inspect leads     Researchers
                                │                │
                           fetch_url         Evidence
                                │                │
                           Evidence         Evaluator
                                │                │
                           Claims           Writer
                └───────────────┼────────────────┘
                                │
                                ▼
                       Claim Verification
                                │
                                ▼
                      Structural Citations
                                │
                                ▼
                              ANSWER
```

# Final Invariants

1. The host never forces retrieval from keywords or semantic labels alone.
2. The model decides whether to use `web_search`, `fetch_url`, knowledge tools, or no tool.
3. `InformationNeed` informs the model; it does not execute actions.
4. Search and fetch remain separate.
5. Search results are discovery leads.
6. Strong final claims rely on stronger evidence.
7. Runtime-generated source IDs are the only valid citation targets.
8. Web content remains untrusted evidence.
9. Python enforces safety, budgets, dedupe, protocol correctness, cache, and termination.
10. Small local-model context pressure is a first-class design constraint.
11. Focused worker contexts are preferred over giant shared transcripts.
12. No fake tool-message sequencing.
13. Empty-model-response recovery stays valid and bounded.
14. Conversation compaction happens before Ollama silently drops arbitrary messages.
15. Code continuation only occurs for genuine output-limit stops inside unfinished fenced code.
16. Deep research is explicit/model-selected and bounded.
17. Tests use unseen synthetic entities to prove generalization.
18. Do not solve regressions by memorizing examples.
19. Preserve the user's dirty worktree unless explicitly told otherwise.

# End of Revised Phases 4–7
