# S3a: Web Search settings

Date: 2026-10-13. Parent checkpoint: `0db42b4`.

The first S3a slice is implemented: Web Search settings and migration of its
existing controls. URL Fetch is the next separate slice. New Google PSE/Serper
adapters, S3b Agent Tools and S4–S6 have not started. This follows
[native Anthropic](s2c-anthropic-validation.md).

## Delivered behavior

- `/settings search` and `/settings web search` open the typed Web Search page.
  Settings home summarizes live enabled state, provider and result count.
  The page has Enabled, Provider, Results per query, Manage providers, Test
  search, Fallback order, Validate search results, Reset to default and Back.
- Auto retains existing configured routing. A pin leads the selected fallback
  order, with duplicates and the primary excluded from fallback presentation.
  Disabled/unconfigured/ineligible services are skipped; empty fallback lists
  remain empty. Existing strict explicit-provider, relevance, quota, billing,
  health, retry and attempt policies stay effective. Pins do not enable providers.
- Agent default results remain **12**, with 3/5/10/12/20 presets and Custom
  **1–50**. Explicit tool counts still win. These controls do not enlarge context,
  research budgets or model output. Raw CLI/facade calls with their own count
  retain that explicit count.
- Provider detail owns enabled state and masked API-key actions. SearXNG has its
  service URL; Tavily has basic/advanced depth. Google Grounding shares Gemini's
  key; Exa shares its key with URL Fetch. Detail states distinguish missing keys
  from configured/keyless but untested services. No working-service claim follows
  merely from having a key.
- Tools links to Web Search; its duplicate web-provider, search availability and
  search-validation rows are moved. Existing Providers search-key entries link
  to the same detail owner. Other Tools/provider controls remain available.
  Tools reset now applies to its own controls and preserves migrated Search
  choices. Search reset clears routing/fallback/count overrides while retaining
  keys, availability, validation, endpoint and depth.
- Non-secret changes apply immediately and use the existing serialized writer.
  Saves remain field scoped; the latest acknowledgement merges allowlisted public
  metadata without restoring stale intent. Failed saves keep active values and
  exact focus/filtering. Navigation and rendering use live state without disk I/O.
- Keys use the masked composer and ordered action lane, with no session-storage
  dependency. Remove requires confirmation initially focused on Cancel. Accepted
  writes survive navigation and drain on shutdown. Only public save flags return;
  keys do not enter preferences, chat, model context or public diagnostics.
  Gemini changes invalidate its model catalog outside the UI thread. Key success
  and a failed catalog invalidation have distinct feedback.
- Tests open a private single-line query editor, then run in an owned worker with
  a **25-second** outer deadline. Overall tests use current routing; detail tests
  use that provider only. Tests respect enabled state, dependencies, billing and
  existing provider-health eligibility. They return bounded actual-provider,
  count and categorized outcome metadata, without snippets or upstream errors.
  Cancel/leaving/settings/session changes prevent late publication. Credentials
  travel through the private pipe; saved replacements/removals override stale
  launch values. No model call, fetch or learning occurs during a settings Test.
- Search-only preferences do not change legacy URL Fetch routing. Search cache
  identity includes routing, fallback order, SearXNG URL and Tavily depth.
  Public-URL fetch, provenance, permissions and dirty-worktree boundaries remain.

## Problems found through real use

### Custom editor crash

The first PTY run crashed when opening Custom results: the controller passed an
unsupported `single_line` keyword to the existing editor. Direct state tests had
not exercised that action. The controller now uses the established callback API,
and Search callbacks participate in its existing single-line behavior. Regression
coverage opens/cancels all four editor actions through the real TUI host.

### One-shot availability bypass

An actual `klaude ask` advertised `web_search` while preferences contained
`tool_availability.web_search = false`. Availability/validation loading happened
only in interactive chat setup. Both are now applied in shared agent construction
before its first model request and capability context. Existing live UI changes
remain immediate. A durable regression drives the shared factory/model interface,
and the repeated CLI fixture rejects any disabled Search schema.

### Negated actions triggered code repairs

The unchanged test prompt was:

> Search for Python asyncio documentation. Return source leads only; do not fetch pages, write files or run shell.

`Python` plus the prohibited `write` matched the code-work heuristic; standalone
output validation independently matched `Return` plus `Python`. The fixture's
ordinary response was forced through two fenced-code repairs and failed.
Code-work routing now uses the shared nonnegated-action predicate, including
short comma-coordinated prohibitions and positive clauses after `but`.
Standalone validation requires a positive code request or explicit returned code
artifact. Positive code-generation/repair paths remain covered. The identical
disabled-search prompt now finishes with one model request and no repairs.

### SearXNG performed nested query expansion

The HTTP log recorded **24 requests** for the simple documentation Test: the
quality adapter planned three variants, then the legacy transport expanded each
again into eight variants, including unrelated handle/video/typo lookups.
The quality adapter now passes each planned variant once. Legacy standalone
SearXNG expansion remains available. An actual HTTP-bound regression verifies
`max_query_rewrites = 2` produces exactly two requests without secondary expansion.

## Real CLI/TUI evidence

Final successful isolated run:
`.klaude/data/s2-models-6j_ykfha/s3a-result.json`.
Session: **TEST KLAUDE FEATURES SEARCH**.

This used the bare executable in a real PTY, an isolated workspace/config/data
directory, an HTTP SearXNG fixture and a compatible model protocol fixture.
All other providers were disabled and billing was strict zero cost. No live paid
search or live model capability is certified by this integration test.

1. Opened Search, rejected a custom count of 100, accepted 5, edited the SearXNG
   endpoint and ran a successful owned-worker provider Test.
2. Cancelled a deliberately slow HTTP Test in under two seconds; navigation stayed
   responsive. A failed HTTP Test displayed sanitized error feedback in the footer.
3. Cancelled masked key input without saving; saved a key in owner-only `.env`;
   cancelled removal with the key intact; confirmed removal; changed Tavily depth.
   No key canary appeared in public terminal or one-shot output.
4. Pinned SearXNG and removed/re-added a fallback. Disabled Web Search and ran
   the exact one-shot prompt above: no Search schema or HTTP request. Re-enabled
   it and repeated the prompt: a real Search tool call returned **five** stable
   source leads, followed by completion. No pages were fetched or learned.
5. Exited and restarted the TUI. Provider, result count and endpoint persisted.
   Interactive, restarted interactive and one-shot paths exited **0**.

### Before/after efficiency

| Same scenario | Before double-expansion fix | After |
| --- | ---: | ---: |
| Initial successful provider Test | 24 HTTP requests | 3 |
| Entire walkthrough, including slow/failing Test and one-shot Search | 61 HTTP requests | 10 |
| Successful one-shot Search results | 5 leads | 5 leads |
| Enabled one-shot model calls | 2 | 2 |
| Disabled one-shot after availability and intent fixes | 1 | 1 |

Before run: `s2-models-8zqhs94m`; after: `s2-models-6j_ykfha`. These are request
counts from the actual fixture log, not estimated API billing or internet latency.
The earlier availability/intent failures are retained separately and are not
counted as successes. No additional orchestration/model call was added.

### Visual review

Inspected captured Web Search/provider pages at **120, 80 and 40 columns**.
Values align at ordinary widths; narrower values/URLs/descriptions wrap inside
the scrollable body. Fixed breadcrumbs and feedback remain separate from chat;
Save/Test success is green, progress neutral and failures red. Filtering and
selection survive edits, and completed history stays in ordinary scrollback.
At 40 columns, the shared global status/navigation hints are cramped/truncated;
this slice improves the page body but does not certify all shared chrome at that
width. Wider 80/120-column layouts are the usable reference.

Captures include `search-home-120`, `search-home-80`, `search-home-40`,
`searxng-detail-80`, success/error Test footers, Tavily detail, fallback order and
restart. SVG previews reconstruct terminal geometry/colors with a local font,
not another terminal's exact pixels. Drivers, logs and source/baseline hashes
are retained with the final run.

## Automated validation

Final functional source, Python 3.12.3:

- Full locked unit suite through `make check`: **2,664 passed, 19 skipped** in
  **134.78 seconds**. This invocation subsequently stopped on new import ordering
  in Ruff. A scoped import-sort fix followed; final `make lint typecheck` passed
  separately, with production mypy checking **97 files**. There were no functional
  changes after that full unit run.
- `make package-smoke`: all **five wheels**, isolated install, public imports and
  installed `klaude --help` passed.
- Final search/settings regressions: **199 passed** in **3.50 seconds**; prior
  focused intent/agentic checks: **123 passed**. Shared-startup and editor cases
  are included in the full suite.
- Existing model-connection/credential regressions passed in the focused
  **80-case** run and the full suite. Prior cancellation, malformed-call/path
  recovery, validation, source handling, permissions, session restore and
  dirty-tree tests remain included.
- `git diff --check` passed. Suite defaults were isolated to `/tmp`; original
  live settings and unrelated dirty changes were preserved. No dependency/lock,
  version, commit, push, release or worktree cleanup was performed.

Early failures included assertions for migrated row locations, the unsupported
editor argument, actual one-shot bugs, and a test using a nonexistent Memory
cleanup method. Those failed runs are retained and are not passing gate evidence.

## Remaining scope and limits

- URL Fetch settings/credential ownership are next. New PSE/Serper adapters and
  S3b registry/execution/navigation migration are separate slices.
- Tests report current provider eligibility, including cooldown/quota states;
  there is no force-health reset action in this page. Configure/enable/key presence
  does not prove connectivity or relevance. Live paid-provider checks are unverified.
- This keeps existing search fallback/relevance/billing behavior; it does not
  introduce Deep Research, automatic fetching or model-led provider reconfiguration.
  The bounded lexical intent predicates still have limits on complex phrasing.
- Credential writes remain independent from non-secret preferences; unconfirmed
  outcomes are visible. Accepted mutations cannot be undone by cancelling a read
  or leaving the page. Other clients' credential changes require a fresh Test or
  process reload for full UI visibility.
- Very narrow shared TUI chrome remains cramped. Current-source Python 3.11/3.13
  CI is pending; local validation is Python 3.12.3.
