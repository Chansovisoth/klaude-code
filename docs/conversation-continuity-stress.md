# Hard conversation-continuity validation

This extends `conversation-continuity-audit.md`. The earlier three-turn recall
smoke was insufficient to establish behavior on long, corrected conversations.

## Live protocol

`scripts/continuity_stress_live.py` creates isolated browser-application profiles
and drives real streamed inference against installed local Ollama models. It uses
the normal browser prompt builder, tool registry, Agent, application workers and
SQLite dialogue persistence. All prompts are synthetic. Production conversations,
model selections, credentials and settings are untouched; no cloud API is used.

The ten-turn conversation has four initial choices, four explicit replacements,
a math detour, a three-item action list followed by a bare numbered choice,
another topic detour, manual compaction, a delimiter change and restoration from
persisted dialogue. Final prompts do not repeat the values being recalled.
No prior assistant answers are injected or repaired. Each checkpoint has one
attempt; raw answers, request payloads, tool observations and failures are saved.

The first complete run is preserved under
`/tmp/klaude-continuity-stress-hard-1/`. The same prompts after the additional
fixes are under `/tmp/klaude-continuity-stress-hard-2/`. Both runs include
`mistral:7b` and `qwen3.5:4b`, at context 8,192, output 256, temperature zero,
and Standard mode. A 27-entry synthetic external MCP registry supplies realistic
schema pressure without contacting or executing actual external servers.
An additional identical matrix after the durable-memory fix is retained under
`/tmp/klaude-continuity-stress-hard-3/`. Earlier failures were not overwritten.

Scoring checks corrected facts, exact math output, the selected numbered action,
CSV validation, the no-upload/offline restriction, the delimiter, implementation
status and unrequested tool use. Different legitimate phrasings of no external
contact, no implementation and semicolon delimiters are accepted. False-positive
and false-negative scorer cases have regression tests. Raw first-pass results are
retained; any revised scoring is stored separately and applied to both runs.
Word limits, the requested two-sentence detour and explanations that repeat
unselected options are checked too. Manual inspection caught the earlier scorer
accepting a three-option answer to a single-option selection; regression tests
now reject that answer. Consistent final scores for every run are retained in
`strict-format-scoring-review.json`, without changing original results.
Keyword checks are not a substitute for inspecting answers: an omitted fact in
a summary, a wrong remembered value and a format violation are reported separately.

A separate five-turn variant changes local models through
`HeadlessApplication.choose_local_model` and uses the application's actual
`resume` method. Its artifacts are under
`/tmp/klaude-continuity-stress-switch-1/`. This tests a real control transition,
not just assignment to a model-name field.

Reproduction:

```sh
uv run --frozen --offline python scripts/continuity_stress_live.py \
  --models mistral:7b qwen3.5:4b --output /tmp/continuity-run --yes
uv run --frozen --offline python scripts/continuity_stress_live.py \
  --models mistral:7b --switch-to qwen3.5:4b \
  --output /tmp/continuity-switch --yes
```

## Additional faults exposed and fixed

- A critical requirement in the middle of a long prompt disappeared because
  extractive recaps kept only its beginning and end. Recaps now reserve bounded
  verbatim excerpts of explicit constraints/corrections. They remain incomplete,
  attributed dialogue, not invented semantic summaries or tool evidence.
- Filtering MCP schemas still left verbose lists of omitted names, reasons and
  permissions in the capability prompt. Browser requests now use a compact
  capability projection; full audit snapshots remain available. The first live
  request's system text fell from 7,782 to 4,244 characters, with the same
  built-in schemas. This does not hide or relax execution policies.
- Historical recaps were sent as system messages, allowing obsolete quoted
  choices to appear more authoritative than later user corrections. Their
  request projection now has user-dialogue authority; canonical compaction
  metadata and attribution are preserved. Browser guidance also states that
  later user corrections supersede earlier choices.
- An oversized current message could destroy older working context and still
  reach a truncating backend. Essential-input admission now rejects it before
  compaction or a model call. Accumulating tool rounds are checked again before
  each request. Errors preserve prior dialogue and completed effects, and retain
  the existing workspace incomplete-report/completion-event contract.
- Fixed character-count assumptions and a minimum compaction allowance could
  exceed a small allocation, especially for non-Latin text. Compaction/admission
  now use conservative non-ASCII byte accounting and respect the actual bounded
  allocation. These are estimates, not claims of exact provider tokenization.
- A valid large-search regression initially failed under stricter admission.
  Request projection now shrinks optional snippet text first, preserving later
  source URLs, source identities and execution provenance. Canonical tool output
  is unchanged. An irreducibly oversized request fails explicitly rather than
  silently losing the objective or inventing omitted evidence.
- The full browser test exposed automatic durable-memory contamination. A single
  "never" anywhere in a task caused the entire task to be saved as a global fact,
  including its obsolete configuration and immediate response request. Those
  notes were then injected into later system prompts. Automatic capture now
  extracts only bounded, explicitly durable preference clauses; task-scoped,
  quoted and fenced examples are excluded. Explicit remember requests remain.
  Browser and terminal memory blocks are safely delimited/encoded, then projected
  as historical user-level data rather than system authority. Current corrections
  take precedence. Existing memories are preserved; forgetting a note clears the
  next request's projection instead of reviving a stale fallback. Memory data is
  budgeted separately so this change cannot evade context admission.

## Deterministic coverage

`tests/unit/test_continuity_stress.py` adds repeated compaction with corrected
requirements, numerous acknowledgements, large complete tool rounds, middle-of-
prompt constraints, budgets 4,096/8,192/16,384, provider changes/restoration,
interruption/resume, fresh-session isolation, oversized current inputs,
multilingual pressure, accumulated tool results, recap authority and scorer
correctness. Protocol assertions require complete call/output pairs and preserve
tool evidence boundaries. Backend callbacks fail tests if an oversized request
would be sent.

The final combined affected-engine/memory/browser/provider/workspace/terminal
suite passed **1,524 tests, with one skipped**. An additional real browser-worker
regression confirms that a legacy task-like memory remains data, and forgetting it
removes it from subsequent model requests. Earlier stress/subagent/evaluation
follow-ups also passed. Touched-file Ruff and syntax checks are recorded with the
final results. This is not a full-repository suite claim.

After the final memory-boundary changes, **77 focused tests passed**. After
tightening the scorer, all **20 stress tests passed** again. These follow-ups
overlap the combined suite; their counts must not be added as unique coverage.
Touched Python files passed Ruff and compilation; `git diff --check` passed.

## Completed live results

All **65 actual model turns** completed. The table uses the same final scorer for
all three ten-turn matrices and the separate five-turn transition run.

| Run | Mistral 7B | Qwen 3.5 4B |
| --- | --- | --- |
| Initial hard matrix | 3/10 | 10/10 |
| Recap/capability fixes | 7/10 | 9/10 |
| Automatic-memory and memory-authority fixes | 6/10 | 10/10 |

The actual Mistral-to-Qwen switch plus application resume variant passed 4/5:
Mistral failed the correction response before the switch; the corrected-fact,
delimiter and final resume checkpoints on Qwen all passed. No production model
selection changed.

The final matrix's Mistral failures were the correction summary (it repeated the
old milestone), number-only formatting (`42 tokens.`), restating unselected steps
and exceeding the word limit, and a four-sentence answer when two were requested.
Manual inspection also found its option-list answer used the obsolete amber theme;
the automated checklist did not flag that incidental contradiction. Qwen's
correction answer retained every changed fact but framed it as an updated
milestone rather than strictly listing only changes. Thus a passing checklist is
not proof of perfect instruction following.

Both models recalled the corrected name, theme, currency and filename after
the detour and compaction, and retained the added delimiter, offline restriction
and honest not-implemented/not-tested status after restoration in the final run.
No model tool calls, model file edits or external-service calls occurred in these
synthetic conversations. The initial Mistral run had returned obsolete values at
both direct recall and final restore checkpoints. Results do not show monotonic
improvement on every prompt, and the remaining model failures are unresolved.

## Remaining limits

No output filter replaces a model's answer to manufacture a passing score. Model
compliance can still fail with correctly supplied context. Context remains finite,
and extractive recaps cannot preserve every detail of arbitrarily long history.
If current policies, tools and required text cannot fit, an explicit limit is
reported; local context defaults are never silently increased.

The running production webhost was not restarted. These source changes require a
new host process to become active. Live score details and remaining model failures
are reported separately from the deterministic engine checks.
