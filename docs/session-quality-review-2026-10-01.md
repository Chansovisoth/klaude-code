# Conversation quality repair — October 1, 2026

Reviewed the four most recently updated sessions in `sessions.db` using read-only
SQLite access. Read all public user/assistant turns, activity and error records,
completion metadata, and live/client state. No session records were changed.

## Findings

| Session prefix | Observed failure |
| --- | --- |
| `a4e72339` | A question comparing Context7 and web search for Godot received an unrelated story about Python project development. Both tools had actually been called. |
| `2e227fcd` | OpenRouter daily free quota interrupted a turn. After switching to Ollama/qwen3.5:4b, a feature summary ended with `done_reason=length`; the next reply asked the user to repeat the task. |
| `a9e056f7` | Coffee-shop context was lost in follow-ups. Executed searches included literal “bruh” and “im in Ta Khmau”. A malformed/unavailable tool call failed, and another turn was recovered after its worker lease expired. |
| `9ce225c9` | Fastfetch was confused with web scraping. Internet connectivity was asserted from enabled tools and SSH rather than a connectivity check. |

These are several distinct failure modes, not proof that session storage lost
all history. The saved conversation survives. The records do not preserve the
exact prompt sent on every model request, so the precise context visible to
each bad answer cannot be reconstructed conclusively. The worker's reason for
ending is also unknown; lease recovery is confirmed, a specific crash is not.

## Implemented repairs

- Preserve separately composed, substantive model search queries for short
  follow-ups instead of replacing them with a reaction or location statement.
  Explicit new lookup subjects still override stale query state; referential
  queries still receive contextual rewriting.
- Reserve bounded recap space before retaining large older tool exchanges.
  Compaction continues to preserve whole call/result units. Bounded tool names
  survive in recaps, with no arguments or output and no implied success.
- Budget Ollama history against its configured context allocation when that is
  smaller than its advertised model maximum.
- Extend the existing bounded output-limit continuation to prose. If the final
  response is still truncated, report it visibly rather than silently treating
  it as a complete answer. The existing turn governor still applies.
- Strengthen full and compact prompts: resolve recent dialogue, distinguish
  actual tool evidence from generic project context, start local recommendations
  with a stated approximate-region assumption, and do not infer connectivity
  from configured capabilities.

## Limits and next quality work

Prompt guidance reduces but cannot guarantee correctness, especially for small
models. Country-level recommendations still require usable search results.
Provider cooldown/config warnings appear in the saved assistant response, but
the exact underlying provider failures are not durably available in these
records. No provider toggles, credentials, model selection, or quota were changed.

Next: add a reproducible multi-turn evaluation covering region → city refinement,
tool comparison, and continuation after provider/model changes. Then measure
the input budget consumed by instructions and MCP schemas on small contexts;
the current recap reservation cannot fix a system prompt that alone exceeds
the context window. Keep retrieval model-directed and permissions unchanged.
Live follow-up probes are recorded below; they do not yet establish real search
provider quality or robustness across models.

## Validation

- `timeout 180s uv run --frozen --offline pytest -q tests/unit -o faulthandler_timeout=45`:
  **1,526 passed, 19 skipped**, 64.68 seconds, with loopback access.
- `uv run --frozen --offline ruff check .`: passed.
- `uv run --frozen --offline mypy packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src`:
  passed, 58 source files.
- `git diff --check`: passed.

Commands used `UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache`. An earlier restricted
combined knowledge run timed out at 90 seconds; the final loopback-enabled full
suite above passed. Regression failures during development exposed referential
leadership and explicit topic-switch cases; both are fixed in the final result.

## Live follow-up checks

OpenRouter Free was available. A three-turn probe using a generic synthetic
prompt and fictional cafe tool results searched `coffee shop Cambodia`, retained
the supplied Ta Khmau location, and correctly recalled both the coffee-shop task
and city. The initial fixture already matched that city, so this run did not
test whether a new city forces a revised search.

The stronger test used the actual Klaude system prompt with synthetic placeholders
for all private context, and returned a Phnom Penh fixture unless the query
mentioned Ta Khmau. Automatic review blocked sending the repository prompt to
OpenRouter, so this test ran through local `gemma4:e2b` instead:

- First query: `local coffee shop`. It omitted Cambodia and asked for a location.
- After `I'm in Ta Khmau.`: `coffee shop in Ta Khmau`. The task survived the
  correction and the query was not overwritten with the bare user reply.
- Asked to recall the task and city without tools, it answered both correctly.
- It honestly identified fictional results, but framed them as an inability to
  help. These fixtures cannot validate real local recommendations.

Separately, the standard isolated harness's `conversation-continuation` scenario
completed on `ollama/gemma4:e2b` in 63.996 seconds, one model request, no tools,
5,617 reported input tokens and 358 output tokens. Its PASS checks completion and
tool behavior, not semantic correctness; the raw answer was not retained.

Added reusable `conversation-continuation` and `local-search-followup` scenarios
to `scripts/evaluate_agent_behavior.py`. The latter requires `--include-network`.
Evaluation-script regressions: **10 passed**; Ruff and `git diff --check` passed.
No real sessions, saved model preferences, or provider credentials were changed.
An interrupted full-prompt OpenRouter attempt has no recoverable result and is
not counted as passing. No further cloud export was attempted after rejection.

Next: measure semantic success (task, city, and actual query) explicitly in the
reusable evaluator, then compare a stronger small model against the E2B baseline.
Real provider retrieval remains a separate test from synthetic conversation
continuity. Avoid treating a single successful conversation as a reliability rate.

## Follow-up implementation: routing and outcome checks

The reported session `8d6fe2cc75944cf7af95c0cb97b42d0b` exposed a further
routing gap: a local recommendation can omit the literal words previously used
to select search tools. Discovery/recommendation intent now exposes read-only
web tools, with workspace subjects excluded from this added rule. Location-only
replies inherit relevant safe tools from dialogue. Per-request instructions
tell the model to execute an already-requested lookup and use reasonable broad
location assumptions instead of asking for the same approval again.

A scripted three-turn regression exercises the real CLI selector and agent:
initial local coffee-shop request → “Can you find them for me” → “I'm in Ta Khmau”.
It verifies callable search tools, retained dialogue, and the narrowed executed
query. This tests the harness; scripted model calls do not measure live model
compliance.

The evaluator now accepts optional groups of answer and search-query terms.
All query groups must match the same executed query, so a response that says
Ta Khmau after searching only Phnom Penh cannot pass that check. Reports expose
only `answer_expectation` or `search_expectation`, not raw query content.
The reusable follow-up scenarios use these checks. This is a lexical baseline,
not a general semantic judge or proof of truthful recommendations.

Validation after these changes: the full frozen unit command recorded above
passed **1,537 tests, 19 skipped** in 64.23 seconds. Ruff passed across the
repository, production mypy passed on 58 files, and `git diff --check` passed.
No live provider run was repeated in this step; the next comparison should use
the strengthened checks and inspect whether unnecessary clarification remains.

## Live comparison with strengthened checks

Ran the isolated evaluator in `/home/klaude/draft/playground` with a 120-second
per-scenario deadline. `ollama/gemma4:e2b` and `ollama/qwen3.5:4b` were selected
as lightweight local baselines. No production session or model preference was
changed. The location scenario used `--include-network` and the configured
web-search stack.

| Scenario | Gemma 4 E2B | Qwen 3.5 4B |
| --- | --- | --- |
| Conversation continuation | FAIL, 30.592s: completed answer but `answer_expectation` failed | PASS, 92.043s: completed answer with no tools or retries |
| Ta Khmau search follow-up | FAIL, 73.541s: completed search and answer, but did not pass retrieval support | FAIL, 120.022s: timed out after one successful `web_search`, without a final answer |

A bounded repeat of the E2B location scenario took 84.921s and confirmed the
retrieval failure: one successful `web_search`, a completed 361-character answer,
zero source references, and `retrieval_support: unsupported`. Its
`error_categories` list was empty because missing retrieval support is a
separate success condition, not an error category. This repeat therefore
passed the lexical answer and same-query coffee/Ta Khmau checks. The report
does not retain answer text or raw search queries, so those checks do not
establish whether it recommended a real shop. The Qwen run shows that a search
executed, not that its query was correct.

Commands:

```text
UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache timeout 300s uv run --frozen --offline python scripts/evaluate_agent_behavior.py --model ollama/gemma4:e2b --model ollama/qwen3.5:4b --scenario conversation-continuation --workspace /home/klaude/draft/playground --timeout 120 --yes
UV_CACHE_DIR=/tmp/klaude-mcp-reuse-cache timeout 270s uv run --frozen --offline python scripts/evaluate_agent_behavior.py --model ollama/gemma4:e2b --model ollama/qwen3.5:4b --scenario local-search-followup --include-network --workspace /home/klaude/draft/playground --timeout 120 --yes
```

Both evaluator invocations returned exit code 1 for scenario failures, not a
harness crash. The E2B repeat completed and wrote a sanitized report under
`/tmp/klaude-live-comparison-20261001/`. These are individual stochastic model
runs, not success-rate estimates. Next, capture privacy-safe query-match and
answer-reason flags in the report, then compare a cloud/free or stronger model
only through an approved data boundary; tune routing or prompt policy only
after failures can be attributed more precisely.
