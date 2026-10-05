# Odysseus study validation

Validated 2026-10-05. Companion to [the corrected architecture study](odysseus-study.md).

## What this establishes

The study's seven mechanisms were traced through their callers, request
construction, tool execution, and result handling. The important corrections
are now in the study. Selected tests establish those contracts and expose
limitations; they do not establish whole-application correctness or better
coding-task completion than Klaude.

- Main snapshot: `934d23c0be29c9721385f34565c0ae2cbd60da04`, 2026-09-05.
- Current dev snapshot: `2992bf6d368a11472323e47d3bfed91e79cefc6b`, 2026-10-01.
- The studied agent, context, memory, skills, provider, capability, and frontend
  files are identical between these snapshots except three added/one removed
  lines clarifying `write_file`. Dev also changes filesystem implementation;
  those newer write safeguards were not tested.
- Python 3.12.3. All declared upstream requirements were installed into
  `/tmp/klaude-odysseus-audit/venv`; the installed versions are preserved in
  [dependencies.freeze](odysseus-validation/dependencies.freeze). Upstream does
  not lock this installation, so this version list matters for reproduction.
- No paid API, teacher takeover, real personal data, embedding-model download,
  or production configuration was used. The upstream checkout remains clean.

## Validation results

| Check | Result | What it covers |
| --- | --- | --- |
| Selected upstream tests | **468 passed**, 16.68s | 40 files spanning selection, memories, skills, plans, compaction, protocol threading, approvals, cancellation, path confinement, and owner isolation. These tests include upstream mocks/stubs; they are not 468 live integration scenarios. |
| Imported-module audit | **23 passed**, including the finalized harness rerun | Real agent loop with a scripted provider, actual temporary file reads, disabled-tool rejection, request schemas/results, pinned and updated plans, nudges, default completion behavior, actual memory context, skill filters, budgets, and security taint. Some passing cases deliberately characterize defects. |
| Original AST helper probes | Passed again | A smaller independent check of keyword hints, selected memory, budget arithmetic, plan-note construction, and teacher regex. This remains helper-only evidence. |
| Live local 3B, support unknown | **Failed** the read task and follow-up | Real Ollama, actual loop, explicit read-only selection; no built-in schemas supplied. |
| Live local 3B, native support enabled | **Failed** the read task and follow-up | Real endpoint configuration supplied two schemas. Model emitted JSON-shaped prose instead of an executable call. |
| Live local 4B, native support enabled | **Passed** the small read and follow-up | One actual successful read, correct answer, correct retained-content follow-up, no second read, no file changes. |

Logs and request/result receipts are in [odysseus-validation/](odysseus-validation/).
Model reasoning is omitted from shared receipts. The full upstream suite, browser
application, and exact CSV benchmark were not run. Passing the small 4B check is
not a CSV result.

### Live scenario and observations

Both models used the unmodified Odysseus loop/provider with a synthetic temporary
workspace containing:

```python
CANARY = 'river-4827-moss'
```

First request:

> Read sample.py in this workspace using your read_file tool. Report the exact string assigned to CANARY. Do not modify files or run commands.

Follow-up:

> Using the file content you just read, what are the three dash-separated parts of CANARY? Do not read the file again or call tools. Answer briefly.

This deliberately small scenario isolates tool transport and continuity; it is
an additional diagnostic, not a replacement for the unchanged CSV benchmark.
Selection was supplied explicitly to isolate the loop, so live embedding-based
tool discovery is not validated by this scenario. Only `read_file` and `ls`
were enabled. No shell or write tool could run. Model temperature was 0, output
limit 350 per round, round limit 5, overall deadline 110s.

| Model / route | First turn | Follow-up | Observed behavior |
| --- | --- | --- | --- |
| `qwen2.5-coder:3b`, supports_tools unknown | 7.59s; 1 request | 1.86s; 1 request | No read. Invented `This is a sample CANARY variable.` and repeated the invention. Zero native schemas despite a native-call system contract. |
| `qwen2.5-coder:3b`, supports_tools true | 4.94s; 1 request | 2.04s; 1 request | Two native schemas. Returned a JSON object naming `read_file` in ordinary text; no execution. Follow-up invented `123-456-789`. |
| `qwen3.5:4b`, supports_tools true | 49.56s; 2 requests | 22.90s; 1 request | Executed `read_file`, received the canary, answered correctly, then retained its three parts without more tools. |

The 4B turn reported 2915 input / 123 output tokens across its two requests;
follow-up reported 1549 / 103. The 3B unknown route reported 978 / 17 then
1036 / 9; its native route reported 1237 / 31 then 1309 / 16.
Counts come from provider usage, not the character estimate.

All runs reported a 131072 context window despite the loop call supplying
`context_length=4096`. A subsequent Ollama `/api/ps` read confirmed the loaded
4B model's actual context allocation was 131072. The argument supplies fallback
metadata; provider discovery/known-model metadata determines `num_ctx`. Do not
interpret these as controlled 4K runs. This also prevents fair latency comparison
to the previous Klaude CSV runs. First-turn load state, reasoning, output limits,
and hardware affect these timings; no general speed claim follows.

## Coverage and corrected claims

| Mechanism | Evidence | Qualification now recorded |
| --- | --- | --- |
| Tool awareness and narrowing | `tool_index.py`, schema parity/keyword/embedding-lane tests; real request capture/read/result roundtrip; live native check | Selection reduces choices, but does not guarantee calls. Unknown local tool support creates a contract/schema mismatch. Embedding backends were mocked, not live-tested. |
| Memory selection | Real `ChatProcessor` preface test and upstream pinned/owner/unreadable-file tests; `build_chat_context` caller inspection | At most five relevant/core facts; facts remain untrusted user-role context alongside a static system policy. Preferences/modes can suppress retrieval. Klaude's 2000-character direct-code prefix is not a limit on its general system prompt. |
| Skills and dependencies | Index toolset, owner, token-match, injection tests; real low-confidence/platform fixtures; startup/view caller inspection | Platform is only filtered when supplied; the main index caller omits it. Index uses enabled built-ins, not exact request schemas. Teacher draft confidence gates matched procedure injection, not index advertisement. Declared known dependencies can add tools; arbitrary prose cannot guarantee availability. |
| Approved plans and todos | Real loop pin/update test, upstream plan allowlist/update tests, actual todo JSON test, frontend Execute/send/update inspection | Execute submits the plan once. The old pinned note survives an update in the same execution; the updated checklist remains in call arguments and the UI, while the tool result gives a count. No automatic task-evidence ledger or completion enforcement was found. Frontend behavior was source-inspected, not browser-click tested. |
| Budgeting and compaction | 85% arithmetic tests; upstream compaction failure/deferred-commit/protocol tests; real overflow/boundary probes | Message estimates omit separate schemas. Protected text can exceed budget. At eleven conversation messages, recent-turn preservation can leave a request oversized; a ten-message control does fit. Summaries are model-generated, not independently verified. |
| Recovery and verification | Real two-nudge exhaustion/default-verifier/unknown-verifier tests; upstream unknown-call/threading/approval/cancellation tests | Recovery is bounded, not semantic completion proof. A failed read followed by a false success claim can terminate with verification disabled. Unrecognized verifier output yields no failure reason; it is not verified success. |
| Teacher and model-specific routing | Imported regex/default-off tests; tier-two/owner tests; inline caller inspection; real model comparisons | Regex ignores exit_code and misses ordinary failed-test counts. Inline escalation does not call the self-hosted helper. Teacher is opt-in; its enabled live takeover and skill approval were not exercised. Named fine-tune clamps do not establish generic model reliability. |

The context overflow fixture uses ten 3000-character prior messages plus the
current request, a 2048 budget, and a 512 output reserve. The protected-context
fixture uses a large `_protected` source plus a small request. These expose
budget behavior without assuming a tokenizer or an actual provider overflow.

## Test investigation and audit corrections

The first restricted-sandbox upstream runs hung at FastAPI `TestClient` async
transport; the initial custom loop also hung. They were interrupted/timed out
and are not counted as successful gates. Running the same history-compaction
tests and real file-read loop with local async transport access completed in
0.53s and 2.30s. The final selected gate completed in 16.68s. This distinguishes
the harness restriction from an Odysseus product hang.

The new audit harness initially had two incorrect expectations: it expected the
full updated plan in the tool-result text, and it used ten conversation messages
instead of the eleven needed to activate recent-message protection. Imported
module results corrected both. A memory assertion was also narrowed to retrieved
fact messages because a static trust policy legitimately uses the system role.
These were harness/claim corrections; no upstream implementation was modified.

## Reproduction

See [upstream test file selection](odysseus-validation/upstream-test-files.json).
With the isolated dependencies installed, run the 40 selected files from the
Odysseus checkout using that environment's `python -m pytest`. Set
`HF_HUB_OFFLINE=1`, `PYTHONDONTWRITEBYTECODE=1`, a separate temporary
`ODYSSEUS_DATA_DIR`, and `DATABASE_URL=sqlite:///:memory:`. Runtime test transports
must be allowed. Keep a bounded external timeout.

For the real-module audit, from Klaude's root:

```bash
HF_HUB_OFFLINE=1 PYTHONDONTWRITEBYTECODE=1 AUTH_ENABLED=false \
ODYSSEUS_DATA_DIR=/tmp/klaude-odysseus-audit/recheck \
DATABASE_URL=sqlite:///:memory: \
timeout --signal=INT --kill-after=8s 60s \
/tmp/klaude-odysseus-audit/venv/bin/python -m pytest -q -p no:cacheprovider \
playground/odysseus-audit-tests.py
```

For the live check, use [odysseus-live-check.py](odysseus-live-check.py), set
`ODYSSEUS_AUDIT_MODEL` to the chosen installed local model, and choose a unique
`ODYSSEUS_AUDIT_OUTPUT` under the temporary audit directory. Omit
`--native-tools` for unknown support; supply it and a temporary file-backed
SQLite URL to create the real `supports_tools=true` endpoint configuration.
No production endpoint is changed. Authentication is disabled only for this
isolated process so synthetic local tool calls can execute.

## Klaude regression and worktree safety

Current worktree validation completed:

- Complete frozen/offline suite: **2392 passed, 19 skipped**, 119.11s.
- Repository-wide Ruff: passed, including the research scripts.
- Production mypy: passed, **82 source files**.
- `git diff --check`: passed.
- Original helper probes and the finalized real-module harness: passed again.

The [full unit log](odysseus-validation/klaude-tests.log),
[lint log](odysseus-validation/klaude-lint.log), and
[type log](odysseus-validation/klaude-mypy.log) preserve those results.
No packaging/dependency changes were introduced; package smoke was not rerun.

This study changes only research artifacts. A playground-local ignore excludes the
foreign checkout from Klaude lint and accidental staging; the checkout remains
on disk. No production code or dependencies changed. The initial validation did
not commit or push; the user subsequently authorized a research-only checkpoint.
All 192 tracked files were hashed before and after the audit and remained
byte-identical, including the user's pre-existing settings changes.

## Remaining validation gaps and next step

Not established: browser clicks/restart persistence, live Chroma/embedding
retrieval, real external MCP connectivity, teacher takeover, production services,
latest dev filesystem changes, full upstream suite, or either model's full CSV
completion in Odysseus. No blanket security, reliability, or superiority claim
is justified by this study.

The justified Klaude experiment remains bounded source snapshots, compact
persistent execution state, and reserved validation/repair opportunities. This
recommendation comes from observed Klaude CSV failures; it is not a claim that
copying Odysseus passes them. Before comparing architectures, match tool transport,
actual runtime context, output/round budgets, reasoning mode, and teacher/fallback
configuration, then run the exact CSV acceptance harness unchanged. Retain
Klaude's execution-based failure tracking, permission boundaries, and honest
incomplete-task status.
