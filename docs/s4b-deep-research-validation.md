# S4b — Deep Research implementation and validation

Date: 2026-10-13. This follows the [Library foundation](s4a-library-validation.md),
[artifact storage](s4a-artifacts-validation.md) and
[explicit Knowledge consumers](s4a-knowledge-validation.md), completing the
[S4 plan](odysseus-settings-and-features-plan.md#s4--library-then-deep-research).
S5 Model Manager and S6 vision/generation remain unstarted.

## Delivered interaction

- Library retains **Sessions, Knowledge, Documents, Research, Media, Archive**.
  Research puts New research, Saved reports, Research defaults and Reload jobs
  above its wrapped job inventory. Inventories use bounded 100-record pages.
- A private job form collects question, Report/Brief/Comparison format,
  endpoint/model, provider and rounds. Queue/Start reviews initially focus Back;
  cancelling the review does no generation, discovery or extraction.
- Queue persists metadata only, with at most ten queued jobs. Starting is
  explicit, without a background queue daemon. Another job may be queued while
  the client's research runs; a second model run is not started concurrently.
- Job details show stage, rounds, query/source counts and source receipts, with
  owned cancellation and explicit resume. A visible running job polls metadata
  every two seconds. Progress uses the shared spinner and fixed status footer.
- Saved reports reuse Library preview, export, tags, archive/restore and
  confirmed deletion. Names derive from the question rather than UUID filenames.
  Detail actions wait for full metadata, preventing premature report actions.
- Discuss report submits a normal scoped chat turn. The public transcript
  contains the report name and user question; a bounded report preview is private
  model_content. Unsent composer text and attachments survive the handoff.
  The RESEARCH scope exposes only query_knowledge, web_search and fetch_url,
  intersected with the existing availability/permission gates. Report/source text
  cannot authorize workspace writes, shell, MCP or delegated work.
- Learn report reviews its destination library before using immutable stored
  bytes through the existing Knowledge/indexing task. It requires an exact
  artifact revision and does not require a temporary export. Storage, discussion
  and learning remain distinct actions.
- CLI registry and actual Typer commands agree: `research run QUESTION` supports
  `--model`, `--provider`, `--rounds`, `--format` and `--queue`; `research list`
  supports `--offset`; `research resume JOB_ID` re-fetches evidence.
  Completed/partial/error/Ctrl+C outcomes exit **0/2/1/130** respectively.

## Defaults and execution bounds

Research endpoint/model lives in AI Defaults. An unset TUI role inherits the
accepted session model; CLI research uses configured Research/Default Chat.
There is no silent fallback to another endpoint or Utility model. Endpoint and
credential revisions are captured before execution; changed selections require
a reviewed new job. Legacy native models work without creating a connection
registry. Existing compatible/native/cloud adapters remain their single owners.

Search → Deep Research owns one field-scoped preference object:

| Setting | Default | Allowed range |
| --- | --- | --- |
| Search provider | Same as Web Search | Existing provider IDs |
| Max report tokens | 2,048 | 256–16,384 |
| Extraction timeout | 30 seconds | 5–90 seconds |
| Extraction parallelism | 2 | 1–3 |
| Run timeout | 300 seconds | 30–3,600 seconds |
| Rounds | 2 | 1–4 |
| Queries | 6 | 1–12 |
| Sources | 8 | 1–16 |
| Context tokens | 8,192 | 4,096–65,536 |

Output must fit within half the configured context. Saves merge unrelated
preferences under the existing settings lock and reject stale research fields.
Accepted jobs retain their captured settings; later defaults affect future jobs.

The executor uses the existing runtime factory and HTTP/provider clients, with
Standard mode and no arbitrary tool schema. Codex account generation cannot
enforce these bounds and is explicitly unavailable here; known always-on
Anthropic models are ineligible. A model request receives two bounded messages
containing question and current structured state, without accumulated chat/tool
history. Native Ollama receives actual required-property JSON schemas with
query/claim/source bounds. Other providers retain their established protocol.

Each request has a cancellation timer of at most 90 seconds and the remaining
run budget; an owned worker deadline bounds the whole run. Extraction timeout
caps **HTTP requests**, not a complete multi-provider page cascade. The worker's
run deadline also bounds extraction/shutdown. Extraction uses at most three
independent clients, five discovery results per query, one router rewrite and
at most two configured provider fallbacks. A logical query budget is therefore
not a one-to-one upstream HTTP request count.

Question length is at most 1,500 printable characters. Planning proposes at
most two queries/public URLs per round. Queries and URL reads are deduplicated;
identical fetched content is not counted twice. Planned public URLs go directly
through the public-URL fetch guard instead of becoming search strings. Native
early completion requires at least two distinct sources, or the configured
single-source budget. A malformed plan has one bounded original-question
search recovery. Fetch bodies are bounded, and the model sees at most 1,800
characters from each page, further reduced to fit the configured context.

These are numeric bounds and approximate prompt sizing, not a guarantee of
exact tokenizer fit or remote-server allocation. Native GPU/thread overrides
are captured; compatible/remote allocation remains server-owned.

## Ownership, recovery and evidence

- Research jobs and report artifacts share private `data/library/artifacts.db`.
  Report bytes, metadata and the completed/partial job checkpoint publish in
  one SQLite transaction. A publication failure cannot leave a successful job
  without its report.
- One stable process lock serializes research workers across clients. A
  five-second heartbeat renews a fifteen-second owner lease. Read-only inventory
  projects expired running leases as interrupted without rewriting the record.
- Cancellation uses the existing OwnedBackgroundJobs process cleanup/reap
  acknowledgement, then a conditional stop write against the captured job and
  owner. Another client's live job cannot be cancelled by a stale view. A late
  cancellation does not erase an already committed report.
- Preflight failure writes compare the accepted revision and refuse to overwrite
  live leases or published reports. A completed request is idempotent even after
  endpoint changes. Stale rejection is displayed without replacing job metadata.
- Navigation/session changes reject late presentation results; accepted work
  retains its target and store identity. Research does not start while chat,
  Knowledge or AI Utility owns conflicting model work.
- Durable checkpoints retain bounded question/spec/status/query/failure and
  URL/title/time/excerpt-hash receipts. Fetch receipts identify read, duplicate
  or unavailable pages, with `result_replayable: false`. Page bodies and quotes
  are not checkpoint evidence. Resume **re-fetches receipt URLs** before synthesis.
- Discovery snippets never become report evidence. Claims must reference an
  actually read source ID and supply an exact normalized 12–600 character quote
  occurring in its current excerpt. Unknown sources, invented quotes and unsafe
  claim links are rejected. Findings get at most one citation repair.
- No readable evidence or unrepaired citation failure saves no report. Missing
  pages/search results or fewer than two distinct sources save an explicitly
  partial report when valid findings exist. Reports expose model, source URLs,
  fetch timestamps, excerpt hashes and limits.
- Exact quote matching checks evidence provenance. It **does not prove semantic
  entailment, comprehensive topic coverage or a small model's reasoning quality**.
  The report makes this limitation visible; a completed status describes the
  bounded job, not a guarantee that every requested research dimension is solved.
- Knowledge learning rejects a freshly fetched body flagged as truncated instead
  of silently indexing partial replacement content. The detailed extraction
  interface remains available for explicitly bounded research excerpts.

## Problems found through actual use

| Observation | Cause | Improvement |
| --- | --- | --- |
| Slow/unexpected routing despite saved provider choices | Job captured obsolete preference keys | Capture/apply the existing search_settings and fetch_settings owners |
| Native planner searched literal page URLs | Planner output accepted only as search text | Guard and fetch planned HTTP(S) URLs directly |
| Small native model returned poor structured planning | Generic object format had no required fields | Native required-property schemas, bounded source enum and early-stop rules |
| Open report failed or stayed loading | Actions ran against summary metadata; full detail lookup missed the report view | Separate jobs/reports identities, load exact metadata and gate actions |
| Queue acknowledgement disappeared | Automatic reload cleared the footer | Retain the action acknowledgement through the refresh |
| Discuss remained behind Library or dumped full report into history | Escape followed parent Back; public message contained the excerpt | Close the panel explicitly and reuse private model_message with scoped tools |
| Second attempt could replace live job status | Early error handling unconditionally wrote error | Revision/lease/report-guarded preflight error transaction |
| Partial CLI report returned success | Partial and completed outcomes shared an exit path | Dedicated exit 2 and status regressions |
| Help rows became very wide | Long new registry syntax changed all command alignment | Bound name-column width and wrap long usage independently |
| Invalid media import created an empty store | Artifact transaction opened before input validation | Validate before opening shared storage |

The first broad suite found three failures (help alignment, empty-store import
and a test fixture lacking Web configuration). These were corrected, then
focused and full gates rerun. Terminal-driver filter/close expectations and a
discussion fixture that incorrectly prohibited normal chat tool schemas were
test-driver errors; they are not counted as product successes or model limits.

## Real CLI/TUI evidence

The isolated session **TEST KLAUDE FEATURES DEEP RESEARCH** uses the real bare
`klaude` process, Prompt Toolkit keyboard navigation, owned workers, SQLite,
Library artifacts and explicit LanceDB/FTS indexing. The main walkthrough uses
local compatible-model, discovery and embedding **protocol fixtures**, alongside
actual public fetching of the CPython README and SQLite About page. It certifies
product flow and protocol handling, not frontier/small-model research quality.

The recorded ten-step walkthrough covers:

1. Private form, format/provider selection and Back-focused cancelled review.
2. Durable queue with no generation/search work.
3. Multi-round owned planning/search/read, deliberate bad quote, bounded repair
   and atomic report publication from two public sources.
4. Report preview at 40/70/120 columns and export to a new workspace file.
5. Explicit report discussion through the real interactive session.
6. Separately reviewed learning of the stored report.
7. Worker cancellation, cleanup acknowledgement and retained job checkpoint.
8. Resume with newly fetched source evidence.
9. Search → Deep Research default save without launching a model.
10. Real `klaude research run` one-shot completion and exit 0.

The final-code walkthrough is retained at
`.klaude/data/s2-models-uvdl3r70/research-result.json`: ten steps,
fourteen model requests across the walkthrough, TUI and one-shot exit 0.
Log: `/tmp/klaude-s4b-sealed-live.log`. The earlier private-discussion run at
`.klaude/data/s2-models-oih1obtc/research-result.json` also passed. A retry at
`.klaude/data/s2-models-tu5s5zph` produced an honest partial report after only one
discovery page reached extraction; it is not a successful ten-step walkthrough.
The local discovery fixture was corrected to use distinct, query-specific
page titles/descriptions rather than sharing mixed CPython/SQLite labels.
Temporary drivers/logs remain local QA evidence, not shipped runtime dependencies.
The user's original project file remained unchanged. Protocol fixtures include
deliberate repair/cancellation calls, so fourteen is not a per-job model budget.

Visual review used actual terminal captures at 40/70/120 columns. Controls stay
above inventories, wide defaults align, report prose wraps and previews start
at the beginning. At 40 columns the general chat chrome remains cramped.
Captures inherited NO_COLOR, so they prove geometry rather than a full color
certification. Footer semantic colors are covered by existing panel behavior.

### Actual small local model

The installed **qwen3.5:4b**, served by native Ollama, was also exercised through
the real one-shot CLI. Question:

> Compare SQLite WAL and rollback journaling: concurrent readers and writers,
> durability tradeoffs, and when WAL is unsuitable. Use official SQLite documentation.

The first run had no readable evidence after searching proposed URLs; the direct
URL path was corrected. A second run combined weak structured planning with
unavailable public search. Required native schemas were added. A controlled
native run then used a deterministic local discovery fixture and actual public
SQLite fetching, isolating discovery availability from generation quality.

Evidence: `/tmp/klaude-s4b-native-controlled/native-result.json`. This produced
an honest **partial** report in **34.2 seconds wall-clock**, with **3 model calls**,
one distinct SQLite WAL page and a quote-supported finding about concurrent
readers/writers. Recorded usage was 1,162 input and 165 output tokens. It did
**not** adequately cover requested durability and unsuitable-use conditions.
That historical run returned 0 for partial output; the final CLI fix instead
returns 2, verified by the exit-status regression cases. The historical result
has not been relabelled as a complete or final-code benchmark pass.

A final-code native rerun is separately retained at
`/tmp/klaude-s4b-native-final/native-result.json` and
`/tmp/klaude-s4b-native-final.log`. It took **78.2 seconds**, performed three
discovery requests and read **two official SQLite pages**. The model still
failed exact citation validation after the single repair attempt. Klaude saved
no report, kept fresh source receipts and exited **1**. Failed-job model-call
and usage totals are not retained by this implementation, so these totals are
not claimed. This run confirms honest failure handling, not reliable 4B research
completion. The remaining problem combines small-model structured citation
quality with the bounded beginning-excerpt selection; this pass does not prove
that either alone explains every failure.

There was no paid-cloud generation, live Anthropic/DeepSeek quality certification,
or CSV implementation benchmark in this S4 feature pass.

## Automated validation and preservation

Final ownership cases verify live-client isolation, completed-run idempotency,
stale revision rejection and retained partial reports. Other dedicated cases
cover bounded schemas/calls, quote rejection/repair, atomic rollback, fresh
resume, shared settings, role removal, no-store browsing, queue availability,
late navigation, report loading, discussion tool scope and CLI exit statuses.

Final executed gates:

| Validation | Result | Local evidence |
| --- | --- | --- |
| Frozen/offline `make check`, isolated config/data | **2,853 passed, 19 skipped**, 171.50 seconds; Ruff passed; mypy passed for 113 production files | `/tmp/klaude-s4b-checkpoint-final-check.log` |
| Five-wheel `make package-smoke` | Passed builds, isolated installation/imports and installed `klaude --help` | `/tmp/klaude-s4b-checkpoint-final-package.log` |
| Real CLI/TUI ten-step walkthrough | Passed, 14 fixture model requests; TUI and one-shot exit 0 | `/tmp/klaude-s4b-sealed-live.log` |
| Final installed native 4B run | Citation error, no report, exit 1; limitation retained | `/tmp/klaude-s4b-native-final/native-result.json` |
| `git diff --check` and new-document local links | Passed | Final checkpoint review |

These results do not count sandbox-aborted, failed-driver or incomplete earlier
runs as passes. The suite covers prior plan approval, cancellation, malformed
calls, path/shell recovery, workspace cache, dirty-worktree and validation/exit
regressions alongside the added features.

The S4b entry baseline contains **87 dirty files** from the authorized preceding
phase work. It is retained locally in `/tmp/klaude-s4b-baseline.json`. The final
audit compares hashes, scopes additions and checks for missing/unrelated files.
The final audit found **no missing files, no unexpected baseline changes and no
unexpected additions**: 23 baseline files changed for S4b/documentation, 64
retained their entry hashes, and six explicit research additions bring the
reviewed checkpoint to 93 paths. Evidence: `/tmp/klaude-s4b-worktree-audit.json`.
No reset, stash, discarded file, production credential or QA data is part of
the checkpoint. No dependency, lockfile or version change is introduced here.

## Remaining limits and next step

- Small native models may give narrow findings despite valid schemas/citations.
  Exact-quote checks cannot substitute for model judgment or coverage review.
  The final native rerun also failed structured citation repair; model-side exact
  quote copying is not reliable. Failed-job model usage accounting remains absent.
- Only short beginning excerpts fit the bounded local profile; deeper page
  selection and explicit coverage tracking could improve difficult questions,
  but are not certified by this pass and should follow measured evidence.
- Sources can fail or change; bounded provider routing and HTTP extraction are
  not a guarantee of available sources. Resume re-fetches instead of pretending
  receipts are reusable content.
- Context sizing is approximate. Report output limits and request/run timeouts
  remain explicit; remote context allocation is unknown without adapter evidence.
- Jobs start/resume explicitly; no unattended queue scheduling is implemented.
- Python 3.11–3.13 GitHub CI is separate from the local gate; a local pass must
  not be described as completed remote CI before the checkpoint runs there.

The next planned feature phase is **S5a Model Manager: local Ollama lifecycle**.
S5 and S6 require a subsequent task; this checkpoint completes S4 only.
