# S3a URL Fetch settings validation

Date: 2026-10-13. Python 3.12.3, working tree based on
`0db42b4b60ce955f9dd4e424098210b66da08bd6`.

This completes URL Fetch for S3a's existing adapters. The previous
[Web Search evaluation](s3a-web-search-validation.md) remains the baseline;
S3b Agent Tools, new PSE/Serper adapters and S4–S6 are unstarted.
No commit/push, release, dependency, version or machine-service change was made.

## Delivered behavior

- Search's **URL Fetch settings** link, Tools' equivalent link, `/settings fetch`
  and `/settings url fetch` open the same typed page. The existing Providers →
  Crawl4AI entry opens its detail page. The page owns fetch availability,
  Local cascade/Exa cloud routing, provider details, explicit Exa cloud fallback,
  uncached Test and a read-only view of current transport limits.
- Migration retains legacy `[web] provider` behavior until an override is saved.
  Default quality/local remains the direct-text → optional Crawl4AI → local
  trafilatura cascade. Inherited `exa` and `auto` behavior is retained honestly;
  search-provider choices never select an extraction engine.
- Crawl4AI detail configures an HTTP(S) service root, optional masked API key and
  fetch enable state. Explicit local/LAN service roots are supported. Service
  URLs reject credentials, query/fragment, controls and invalid ports. Blank
  removes the endpoint; worker snapshots carry that empty value authoritatively.
  This service configuration never makes private *page targets* fetchable.
- Exa extraction enable state is separate from search eligibility. Search and
  fetch share one private Exa key and configured environment reference, including
  custom references. Explicit cloud selection/fallback has visible charge hints;
  no new automatic switch to paid extraction is introduced. Missing/disabled
  Exa fails without contacting its API or choosing another engine.
- Non-secret choices apply to live configuration, then save through the existing
  serialized, field-scoped writer. Latest public acknowledgements merge other
  clients' fields; stale acknowledgements cannot undo newer intent. Failed saves
  retain active choices, selection and filtering. Navigation reads live state.
- Keys use the same bounded ordered action lane as Search. Only public save
  flags return. Owner-only dotenv writes preserve unrelated entries/comments;
  keys never enter preferences, chat history, model context or public results.
  Removal requires confirmation initially focused on Cancel. Accepted writes
  drain after navigation/shutdown without opening session storage. Saved changes
  and removals override stale inherited environment/TOML keys on restart.
- Reset restores inherited routing/fallback, retaining endpoints, keys and all
  availability choices. Tools reset retains migrated search/fetch settings.
- Test reviews a public URL, then exercises the actual uncached route in an owned
  worker with a 40-second outer deadline. It performs no model call, learning or
  persistent page-cache write. Results contain only bounded actual-provider,
  attempted-provider/count/elapsed/failure metadata. Page text, credentials and
  upstream error bodies stay private. Crawl4AI detail tests use that extractor
  after the safe direct download and never hide its failure behind trafilatura
  or Exa. Overall cascade tests report the actual successful extractor.
- Cancel, navigation/session changes and live configuration changes reject delayed
  results. Progress/cancel feedback is neutral, success green, warnings yellow
  and errors red. Transient editor errors take precedence over long navigation
  hints. Masked entry suspends navigation before accepting key input.

## Problems found and fixes

| Evidence | Cause | Improvement |
| --- | --- | --- |
| Fetch implementation selected engines from `cfg.web_provider`, the old shared search field. | Search/fetch configuration ownership was coupled. | Independent allowlisted fetch preferences, preserving inherited routes until explicitly changed. |
| A failed URL was returned from the in-memory failure registry after service/credential configuration changed. | Failure identity ignored effective fetch configuration. | Scope failure reuse to the current configuration; retain verified source identities. |
| Cached/registered documents could exceed a newly tightened content limit; TTL zero still consulted disk cache. | Reuse bypassed the current limits. | Bound reused documents, include service/routing/limits/credential identity in cache keys, bypass disk cache at zero TTL. |
| Crawl4AI and Exa buffered authenticated response JSON without a byte limit; Exa used a fixed timeout. | The safe direct-download limits did not cover extraction-service responses. | Shared bounded streaming POST, configured timeout/byte limit, no service redirects or ambient proxy credentials, sanitized categorized errors. |
| New terminal key entry stayed in page filtering and exposed the fixture canary onscreen. | The new entry handler did not suspend choice navigation. | Clear choice mode before masked input; state regression and repeated real terminal canary checks. No real user key was used. |
| At 80 columns, long editor hints crowded out endpoint validation errors. | Status fragments put hints before errors. | Prioritize the transient error; shorten the service-URL error and retain the private editor for correction. |
| Real `ask` did not expose `fetch_url` for “Fetch this URL … Do not search …”. | The heuristic treated a search prohibition as removal of every retrieval tool. | Recognize a positive named URL read separately and preserve its fetch schema; disabled/no-tools boundaries still win. |
| Custom Exa references worked differently across Search/fetch diagnostics; saved removals could revive inherited fetch keys on restart. | Workers forwarded only canonical variable names and ordinary startup did not resolve removal revisions. | Forward only configured references through the private pipe, resolve current stored revisions and share Exa's effective credential reference on startup. |

Exa fallback metadata now uses the failed download's actual attempted-provider
list, rather than inventing an HTML extractor attempt for unsupported content.
Changing Exa's service endpoint also invalidates failure/cache identity.

The improvements preserve the public URL/DNS/redirect checks, untrusted evidence,
`search_result_NNN` discovery versus `src_NNN` fetched-document identities,
permission gates and existing cascade behavior. They add no model calls or
forced retrieval. Normal plain-text reads still bypass HTML extraction.

## Real CLI and terminal evidence

The walkthrough used bare `klaude` through a real PTY and isolated configuration
and session directories. Its session is named **TEST KLAUDE FEATURES URL FETCH**.
It used a public `https://example.com` download through the normal safety path,
a local HTTP Crawl4AI `/md` fixture and a local Chat Completions model fixture.
The fixture checks the actual exposed schemas, invokes the real tool and checks
its fetched source result. It is protocol/orchestration evidence, not a local
model capability benchmark or paid-provider certification.

The final fetch evidence root is `.klaude/data/s2-models-g31ych4p/`: its
`fetch-result.json` records nine completed walkthrough stages, two clean TUI
exits and the real one-shot protocol. The completed Search regression is in
`.klaude/data/s2-models-zgy7ucf_/s3a-result.json`. These are ignored local evidence
directories; this document preserves the outcomes for other checkouts.

Scenarios exercised:

1. Search → URL Fetch navigation; 120/80/40-column resize and scrolling layouts.
2. Invalid service URL rejection, correcting it to an explicit loopback service;
   private page target rejection before the test; correcting it to a public URL.
3. Masked key cancel/save, owner-only storage, unrelated dotenv preservation and
   confirmation initially cancelling key removal.
4. Owned-worker public download plus Crawl4AI extraction; successful 46-character
   outcome and a strict 401 provider test with sanitized red footer.
5. Slow test cancellation in under two seconds; no delayed success publication.
6. Explicit Exa route with missing configuration; local route and explicit cloud
   fallback toggles without sending a paid extraction request.
7. Real one-shot disabled-fetch schema, then enabled `fetch_url` tool execution
   yielding a fetched source. Exit code 0 for each successful one-shot.
8. Exit/restart retaining the route, endpoint, private key and enabled state;
   blank endpoint removal followed by honest missing-configuration feedback.
9. Completed Web Search walkthrough rerun: real SearXNG protocol, five-result
   default, validation/editor/cancellation/error/key/fallback/restart checks and
   disabled/enabled one-shot schemas. No duplicated SearXNG query expansion.

Reconstructed images from actual terminal-cell/color captures were inspected.
At 80/120 columns the pages have aligned values, full-width wrapped URL/content
rows, muted explanations, stable breadcrumbs/footer and subtle focused rows.
At 40 columns the body wraps/scrolls, while the inherited shared status/brand
chrome is still crowded. No claim of pixel-identical behavior across terminals.

## Automated validation

Coverage includes migration, search/fetch independence, allowlisted metadata,
non-blocking navigation, focus/filter retention, cross-client saves, failed saves,
scoped resets, single-line editor cancellation, stale tests, ordered private
writes, secret masking/removal, public target safety, strict extraction tests,
response-size/auth/rate-limit/redirect/malformed-data handling, repaired failure
reuse, scoped cache, current content limits, zero TTL, custom credential
references, saved removal after restart and accurate Exa fallback attempt metadata.

An initial focused run passed 227 existing search/fetch tests. An initial full
sandboxed run found one old layout assertion expecting the moved fetch toggle;
that assertion now checks a toggle still owned by Tools. The sandboxed run also
stalled around knowledge-store tests and was interrupted: **1372 passed,
1 failed, 1 skipped**, not a green suite. The subsequent isolated full run with
local socket access completed: **2693 passed, 19 skipped**, Ruff and production
mypy passed. After shared credential fixes, another full run completed:
**2697 passed, 19 skipped**, Ruff and mypy passed. Final validation after the
endpoint-removal regression is listed below.

Commands use isolated config/data and the locked offline environment:

```sh
KLAUDE_HOME=/tmp/klaude-fetch-last \
KLAUDE_CONFIG_DIR=/tmp/klaude-fetch-last/config \
KLAUDE_DATA_DIR=/tmp/klaude-fetch-last/data \
UV_CACHE_DIR=/tmp/klaude-ux-uv-cache UV_FROZEN=1 UV_OFFLINE=1 make check

UV_CACHE_DIR=/tmp/klaude-ux-uv-cache UV_FROZEN=1 UV_OFFLINE=1 make package-smoke
```

## Limits and next slice

- Live paid Exa extraction and a real deployed Crawl4AI installation are not
  certified. Fixtures establish request/response, error, privacy and cancellation
  behavior. The public direct-download path was exercised live.
- Timeout remains a per-request transport limit; settings Test additionally has
  its killable outer deadline. This does not introduce a new whole-turn deadline.
- Transport-limit editing remains in `[web.fetch]` config; the settings page shows
  effective limits read-only. Existing trust/provenance rules are not optional.
- Existing verified in-session content may be reused after a route change,
  bounded by current content limits; Test always exercises the uncached route.
- Legacy `auto` can retain an existing Exa fallback on migration. Its visible
  toggle can explicitly turn it off; this pass does not silently rewrite config.
- Existing broad Providers labels/navigation and shared 40-column chrome still
  need the separately planned S3b navigation work. Optional new search adapters
  remain deferred complete slices. S3b and S4–S6 were not started here.
- The previous CSV/local-model benchmark was not rerun in this settings slice.

## Final evidence

- The nine-stage final fetch walkthrough and the completed eight-stage Search
  regression both passed, each with two clean TUI exits and successful enabled/
  disabled `ask` exits. The fetch model fixture received no tools while disabled
  and exactly `fetch_url` when enabled; three total model protocol calls were
  recorded (one disabled reply, one tool call, one completion after the real
  fetched result). Settings tests generated no model calls.
- Visual captures at 120/80/40 columns and success/error/provider/limits/restart
  screens are retained beside `fetch-result.json`. The 80-column home/provider/
  error captures were rendered and visually inspected; the earlier inspected
  `.klaude/data/s2-models-vtcdkqeg/` captures have the same page structure.
- New fetch coverage: **36 passed** in 2.97s after the final cache/provenance
  corrections (`/tmp/klaude-fetch-final-focused.log`).
- Final full checks: **2700 passed, 19 skipped** in 136.02s; Ruff passed and
  production mypy found no issues in 100 source files
  (`/tmp/klaude-fetch-complete-check.log`).
- Final packaging: all five workspace wheels built, installed together in an
  isolated environment, public imports and installed `klaude --help` passed
  (`/tmp/klaude-fetch-complete-package.log`).
- `git diff --check` passed. Starting dirty-file hashes were recorded in
  `/tmp/klaude-s3a-fetch-baseline.json`: 38 pre-existing dirty files remained
  byte-identical, 14 were intentionally extended for this slice and none removed.
  Five previously clean tracked implementation/test files and five new files
  implement/document fetch. Unrelated private machine configuration was retained.
- Evidence drivers/logs are copied into the final fetch directory for local
  reproducibility. They require the existing local `pyte` test dependency and a
  real terminal/socket environment; no project dependency was added for them.
