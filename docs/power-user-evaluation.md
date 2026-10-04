# Klaude power-user evaluation

The follow-up on complex implementation with weaker local models is documented
in [Small-model implementation follow-up](small-model-evaluation.md). It reuses
this pass's exact CSV task and both small models; this original reliability
evaluation remains the baseline.

Date: 2026-10-04. Evaluated the real CLI and Prompt Toolkit chat against local
Ollama, then traced observed defects into the implementation. This is a product
evaluation, not a claim that the tested local models completed the coding task.

## Environment and safety

- Inspected the existing dirty repository before edits and retained unrelated
  MCP/Skills/settings work. No commits, pushes, stashes, resets, or discards.
- Created isolated config/data directories and disposable projects under
  `/tmp/klaude-power-user`. Coding projects were deliberately outside Git so
  Klaude's normal automatic commit behavior could not create a commit.
- Used `uv run --project /home/klaude/klaude-code --frozen --offline klaude`.
  Interactive runs used the full TUI through its documented `chat` alias;
  one-shot runs used `ask`.
- Models: `qwen3.5:4b`, `qwen2.5-coder:3b`, and an incomplete cold-start probe
  with `qwen3-coder:30b`. The 3B model's live Ollama metadata advertised tool
  support; its invalid call format was not inferred from its size.
- Test settings: thinking off; general context/output 8,192/2,048 tokens;
  code context/output 16,384/4,096. File tools and shell were permitted in the
  isolated projects. No cloud credentials or paid model requests were used.
- Some initial evaluations shared one Ollama runner. Wall times include model
  loading, CPU offload, and contention; they are not isolated latency benchmarks.

## Black-box coding task

The fixture was a small, dependency-free Python inventory CLI, **Stockroom**:
`stockroom/store.py` loaded/saved a legacy SKU-to-quantity JSON map;
`stockroom/cli.py` implemented `add` and `list`; `__main__.py` exposed
`python3 -m stockroom`; README and two unittest regressions described the public
contract. Both original tests passed before the task. `add` printed the new
integer quantity; `list` printed the stock map.

The task was selected before inspecting Klaude's routing implementation. The
same full task was given to both local models:

> Implement production-quality CSV stock adjustments in this project. Inspect
> the existing code and tests first. Add `python3 -m stockroom --store PATH
> import-csv INPUT [--dry-run]`. CSV columns must be transaction_id,sku,delta
> (allow a UTF-8 BOM). Each ID/SKU must be nonempty and delta must be a signed
> integer. Validate the entire batch before changing state; reject duplicate IDs
> within one batch, conflicting reuses of a persisted ID, missing/extra fields,
> and adjustments that would make stock negative. Reimporting an identical
> transaction is an idempotent skip. Save stock and the transaction history
> atomically in the same store; read existing legacy SKU-to-quantity JSON without
> losing data and keep add/list behavior compatible. Dry-run returns the same
> JSON summary as a real run (applied, skipped, stock) but creates or changes no
> files. Failed input returns exit code 2 with a useful stderr message and no
> traceback or partial changes. Add tests for these guarantees and update README
> with realistic examples. Use only the standard library. Complete and validate
> the implementation, and report actual test results and any remaining
> limitations. Do not commit or push.

This requires inspection, persistence design, migration, transaction semantics,
CLI compatibility, failure recovery, tests, and documentation across files.
Independent acceptance checks were kept outside the project and were not shown
to the model before its first attempt.

## Live observations

| Scenario | Observed behavior | Assessment |
| --- | --- | --- |
| Interactive project review | Read README, source, and tests; used batched reads and produced a public plan. Some findings contradicted the code, and one proposed example was corrected within the same answer. | Actual inspection worked; review accuracy and verbosity remain variable. |
| Queued follow-up | “Go ahead with that plan” was queued normally, then asked the user to restate the plan. | Host routing omitted implementation tools and switched to the smaller general context. Further inspection found the compactor dropping the entire preceding objective/plan. |
| Session resume | Named sessions survived multiple TUI restarts and `/resume`. | Saved public context was intact in SQLite; the failure was request preparation, not missing session storage. Tool audits were never promoted into file-content evidence. |
| Cancellation during model loading/request wait | Initial 30B request stayed INTERRUPTING for over 50 seconds. After the transport fix, a real 4B cancellation returned to Ready and saved a cancelled turn. | Cancellation improved before response headers, not only during streamed output. The 30B capability comparison remains incomplete. |
| MCP/Skills settings at 80 columns | Opened entry/manage pages, local filter, Escape-to-clear, Back, and Settings home. Empty isolated inventories showed clear controls above the inventory and stable headers/footers. | Navigation worked. This run did not test live catalog search, installations, authentication, or populated wide inventories. |
| Initial full one-shot, 4B | No tools were supplied. Model printed a long purported implementation, changed no files, and performed no validation. | Failed. “Use only the standard library” had been misread as a named tool-only restriction. |
| Full one-shot after routing fixes, 4B | Inspected the project and wrote the store and CLI. Recovered once from an invalid filename. Later request hit the 600-second model transport timeout. Added no tests or README update and ran no validation command. | Failed. Independent validation found one of the two original tests failing, valid CSV rejected as header-as-data, ignored dry-run behavior, non-atomic writes, separate/stubbed history, and changed CLI output. |
| Same full task, 3B | Printed a fenced JSON object naming `read_file` with an invented placeholder path. No tool executed and no file changed; CLI initially returned 0. | Failed. Host treated printed tool protocol as an ordinary completed answer. |
| 3B tool-format retest | Real CLI retried once with native schemas still available. Model repeated invalid protocol; no tool executed and CLI returned 1. | Honest bounded failure now replaces false completion. Successful native retry is additionally covered by scripted integration; this model did not recover live. |
| Already-dirty Git project | Write/edit/commit schemas were omitted, startup warned about the boundary, and all fixture/user-note file hashes remained unchanged. Model nevertheless spent many read calls and ended in an invalid-tool error. | Safety passed. Fast, natural explanation of a blocked task did not pass. |
| Controlled malformed provider through real CLI | Local HTTP fixture returned malformed native arguments repeatedly. Before fix: error printed with exit 0. After fix: error printed with exit 1 and failed session retained. | Verified without cloud quota. This is provider-shaped failure injection, not a live OpenRouter request. |
| Real CLI repair cycle with controlled provider | Scripted native calls used the actual file/shell tools to observe a failed check, edit a file, reread it, and rerun the identical check successfully. | Passed after named-file routing and duplicate-guard fixes. The first fixture attempt exposed inspection prematurely returning a read-only tool subset; the unchanged fixture then passed. This validates host behavior, not model intelligence. |

The independent importer harness checks BOM/signed deltas, legacy migration,
dry-run parity, idempotent replay, preserved history after `add`, conflicts,
duplicate IDs, negative-stock rollback, malformed fields/integers, and missing
input. The generated importer rejects valid input, so apparent rejection-case
passes are **inconclusive**, not evidence that its validation guarantees work.
No importer success percentage is reported.

## Root causes and implemented changes

| Cause | Improvement |
| --- | --- |
| Tool-only intent accepted arbitrary resource nouns as tool names | Resource constraints such as standard-library-only retain workspace tools; explicit unknown tool identifiers still fail closed. |
| Knowledge-ingestion regex crossed unrelated sentences and matched `import-csv` | Bound ingestion actions/source targets to a clause and whole verb, retaining explicit learn/import behavior. Ordinary CSV work does not select persistent ingestion. |
| Workspace mutations exposed web tools without a research need | Require a research action, URL, or external freshness request for web discovery. “Current CLI behavior” does not imply fresh external facts. Positive research and relevant MCP/Skill matching remain available. |
| Named-file inspection returned before other task intents were considered | Share the mutation-intent check and retain requested edits/execution for compound inspect/fix/validate tasks. Explicit read-only instructions still select the read-only path. |
| Short continuation was routed as a fresh lookup and used smaller context | Resolve the nearest substantive user objective, skipping dependent continuation chains; inherit its code settings and implementation tools. Assistant prose cannot authorize mutation. Scope, disabled tools, dirty-tree rules, and Git prohibitions remain enforced. |
| Fixed prompt estimation erased all earlier dialogue | Omit the detailed web policy when no web/MCP schema is callable; estimate natural-language system prose at three characters/token while keeping Ollama dialogue/schemas at two and preserving output headroom. Real captured request now retains the objective and public plan. |
| Cancellation tracked the response only after headers | Use the documented [HTTPX trace extension](https://www.python-httpx.org/advanced/extensions/) to track the owned socket during connection/model wait. Shut it down on cancellation; request identity guards prevent old cleanup or late response attachment from interfering with a newer request. |
| Periodic progress entered streamed answers mid-line | Line renderer emits stage changes before public streaming, then suppresses progress traces inside code/prose. |
| One-shot runtime errors still exited successfully | `ask` returns exit 1 after failure persistence and cleanup. Interactive rendering retains its in-process behavior. |
| Whole-response JSON tool envelope was mistaken for an answer | Detect a known-name/argument-object envelope only when tools are callable and text has not streamed; never execute it as text. Retry native protocol once, then fail explicitly. Embedded examples and tool-free JSON answers remain ordinary text. |
| Two missing filenames retired the reader; one failed batch exhausted recovery | Typed lookup errors keep file tools available and request directory/path discovery. The no-progress streak counts unsuccessful model-response batches; every tool call still consumes the hard budget, and three unsuccessful responses still stop. Other operational/permission failures retain bounded retirement. |
| An approved review plan remained a planning-only request to the model | When the user explicitly approves the preceding plan and mutation tools are callable, request context identifies the transition to implementation and validation. Other user constraints and all host boundaries remain effective. |
| Nonzero shell exits were treated as progress; duplicate guards survived edits | Extract typed exit/failure metadata, give corrective validation feedback, and keep ordinary command failures recoverable. Invalidate earlier workspace-dependent guards after mutations so fresh reads and identical test reruns can execute. Immediate duplicate and hard governor bounds remain effective. |
| Footer used general context capacity for larger code requests | Track the most recent request allocation per provider/model; use it for the footer, request capabilities, and manual compaction. General configuration summaries retain their general tuning value. |
| Model omitted implementation and validation obligations | Added general coding guidance: preserve public contracts, complete file edits, avoid unrelated stubs, inspect validation exit codes, repair/rerun failures, and report actual results/gaps. Prompt guidance is not proof of model compliance. |

Implementation is in the existing CLI, intent router, agent loop, execution
governor, Ollama adapter, and system prompt. `AGENTS.md` describes the changed
behavior. No new dependencies or speculative orchestration subsystem were added.

## Evidence and reproduction

Live projects, task, independent harness, and logs are currently retained under
`/tmp/klaude-power-user`; temporary files are not durable repository artifacts.
Config/data are isolated from the user's normal Klaude session storage.

Key session IDs:

- Interactive named **TEST KLAUDE FEATURES**:
  `a853c0d7b042458593459a23dcff016e` and
  `e56ca74600ff44a5bb55e10a7e2e2335` in `interactive-data/sessions.db`.
- Original 4B task: `2ab2fcdddab64501a67adfbb99f563d2` in
  `oneshot-data/sessions.db`; `oneshot-before.log`.
- 4B task after tool fixes: `549f8ca85fff4d90963fc841eded189c` in
  `rerun-data/sessions.db`; `oneshot-after.log`.
- Dirty-tree boundary: `ca87fd816fb04a4083eb79781fb1d188` in
  `dirty-data/sessions.db`; `dirty.log`.
- 3B full task: `88cfae7941a34d12a2cade7439c91ff5`; format retest:
  `712cbca6bc924d67a401d7469bb8d938`, both in `alternate-data/sessions.db`.
- Failure injection: `provider-failure.py`, `provider-failure-before.log`,
  and `provider-failure-after.log`.
- Actual-tool repair cycle: `repair-cycle.py` and `repair-cycle-after.json`.
- Independent atomic-write checks: `verify-atomic.py`, `atomic-before.json`,
  and `atomic-after.json`.

The sessions' public answers and observed tool execution are distinct from saved
audit metadata. For the importer, the generated files and independently executed
commands establish the failures; audit records alone do not prove correctness.

## Validation and final retest

Final repository validation passed:

- Complete locked unit suite: **2,342 passed, 19 skipped**, 113.58 seconds.
  Command: `UV_CACHE_DIR=/tmp/klaude-ux-uv-cache uv run --frozen --offline
  pytest -q tests/unit`. Local HTTP/OAuth tests ran outside the restricted
  network sandbox; log: `/tmp/klaude-power-user/power-user-final-tests.log`.
- Ruff: `uv run --frozen --offline ruff check .` passed.
- Production mypy across all five source packages: **80 source files passed**.
- `git diff --check` passed. No packaging/dependency change was introduced;
  the earlier package smoke is not represented as a fresh run here.
- Focused tests cover cancellation before headers for streaming/non-streaming
  requests, stale-request races, intent/routing boundaries, context/plan
  retention, native protocol retry without text execution, failure exit status,
  path discovery after failed batches, and unchanged hard execution ceilings.

In the final interactive recovery run, the same short approval now retained the
original objective and plan, recovered from **three missing-file calls in one
batch** through directory discovery, read the actual source/tests, and executed
`edit_file` to implement replacement-based stock persistence. Its first test
command failed with exit 127; it then corrected the runner and successfully ran
`python3 -m unittest tests.test_stockroom -v`, with both original tests passing.
The saved final answer named those actual tests. Previously it
asked for the plan again, disabled the reader, or repeated the review without
editing. Independent checks in `verify-atomic.py` passed the original **two
regression tests**, verified that save replaced the target inode, and injected
rename/replace failure to verify that the original bytes remained intact.
The two atomicity checks failed for the non-atomic baseline. This is a passing smaller
atomic-persistence scenario, not a successful CSV transaction benchmark.
The implementation still uses a fixed sibling temp name, does not fsync, and
does not establish concurrency or power-loss durability; the checks above prove
only the stated replacement/failure behavior. It added no new regression test
for atomicity itself.

The footer allocation/manual-compaction fix is verified by request/CLI
integration assertions, not a subsequent long live-model TUI turn. An initial
full rerun caught nine provider-snapshot compatibility failures when local
allocation was unspecified; the fallback to known provider metadata was
restored without weakening the assertions.

Earlier MCP/Skill/subagent live coverage remains in
[the feature ledger](test-klaude-features.md); it is not counted as a fresh live
probe in this evaluation.

## Remaining limits

- Neither tested small local model completed the full coding benchmark. Host
  repairs improve available tools, continuity, and honest failure; they do not
  establish production-quality autonomous coding on those models.
- The 4B implementation changed public behavior, missed transaction guarantees,
  and skipped tests. A stronger-model comparison is still needed before claiming
  the product handles this task well. No automatic model switch was introduced.
- Context sizing remains an estimate, especially with large injected repository
  guidance or dense content. No exact local tokenizer was added, and this run
  does not establish arbitrary-long-session continuity.
- The 600-second per-request timeout and 30-minute turn governor remain bounded.
  Slow CPU generation can still time out after partial edits; no timeout was
  silently increased to make a failed benchmark look successful.
- Missing-path recovery changes do not authorize access outside the workspace
  or changes to a dirty tree. Graceful reasoning when a task is blocked remains
  a model-quality concern.
- Intent routing still uses bounded heuristics. This evaluation fixes observed
  resource, compound-task, and continuation errors; it does not establish
  correct interpretation of every ambiguous or targeted constraint.
- Cloud/OpenRouter protocol regressions use controlled fixtures; live paid cloud
  capability/performance was deliberately not tested. Existing subagent, MCP,
  and Skill regression suites are included in the complete unit gate.
- No automatic semantic completion detector was added. A completed but incorrect
  ordinary answer can still return 0; reported validation must be checked.
