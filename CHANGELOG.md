# Changelog

## Unreleased

- Make provider health recoverable: a single operational failure no longer
  disables later searches, repeated failures enter a timed cooldown, stale
  legacy failures expire, and successful low-relevance responses still prove
  the provider is healthy.
- Stop caching empty or failed web searches, ignore previously cached failures,
  and preserve academic, research, and documentation intent when queries also
  contain freshness terms such as `latest`, `current`, or a year.
- Preserve dense and lexical backend evidence during reciprocal-rank fusion,
  expose RRF/reranker provenance, and keep the optional reranker's final order.
- Add a bounded single-agent web research loop with per-turn structured state,
  model-directed search/refine/fetch decisions, configurable action/search/fetch/
  per-domain/failure budgets, graceful best-effort exhaustion, duplicate-query and
  duplicate-fetch prevention, and compact action traces.
- Separate web source discovery from page reading with runtime-generated search
  result/source IDs, selective `fetch_url`, canonical URL/content deduplication,
  structured failures, public-network redirect validation, bounded extraction,
  and an explicit untrusted-web-content boundary.
- Add conservative local-first search-query typo correction and entity-name
  learning with RapidFuzz, a compact SQLite alias cache, correction provenance,
  protected short acronyms/proper names, and an optional keyless Wikidata
  fallback that fails safely when offline or ambiguous.

## v0.2.0-alpha.2 - 2026-08-02

Second preview release focused on durable storage invariants, retrieval quality,
provider observability, project-local configuration, and chat behavior.

- Add atomic knowledge indexing with versioned staged rows, `active_sources`
  activation, failed-operation recovery, and active-version-only retrieval.
- Route `learn`, docs sources, crawled docs, skill imports, CLI, and MCP indexing
  through the shared indexing service.
- Add refreshable `llms.txt` docs sources, polite same-domain crawling, skill
  package imports, unchanged-source skip logic, and `docs update --online`.
- Add relevance-first web search routing across Google, Parallel, Exa, DDGS,
  Tavily, Firecrawl, and SearXNG with explicit provider overrides and fallback
  metadata.
- Show structured provider labels in chat output for `web_search` and
  `fetch_url`, including multi-provider searches and fetch providers.
- Fix Exa authentication to load `EXA_API_KEY` from local dotenv config, strip
  whitespace, and send the key through `x-api-key` without a bearer prefix.
- Add Tavily and Firecrawl as optional search providers while keeping hosted
  extract/crawl/research features out of Klaude's tool surface for now.
- Improve ambiguous acronym and local-entity lookup behavior with softer
  candidate discovery, fetched-page verification, location-aware query planning,
  and model-chosen search queries.
- Improve follow-up entity state so user corrections, entity type changes, and
  claim verification queries do not reuse incompatible earlier meanings.
- Improve command discovery with a canonical command registry, deterministic
  command-reference rendering, focused command help, typo-tolerant command-list
  requests, and no invented command syntax.
- Add `sessions delete` and `sessions clear` with confirmation prompts.
- Add runtime context collection plus concise behavior rules so greetings and
  directory questions do not dump full machine specs.
- Add conservative automatic memory, explicit memory controls, session recall,
  and sensitive-memory filtering.
- Move source-checkout config into visible `config/`, runtime data into
  `.klaude/data/`, and tracked examples into `config/examples/`.
- Split SearXNG's service secret into `config/searxng.env` so provider API keys
  in `config/.env` are not passed into the container.
- Add `[ollama.options]` request tuning for Klaude chat calls without requiring
  Modelfiles or moving host-level Ollama daemon settings into the app config.
- Update README and `AGENTS.md` to describe the current architecture, provider
  behavior, config layout, MCP boundaries, and development workflow.

## v0.2.0-alpha.1

First preview release of `klaude-code`.

- Add local-first agent scaffold with Ollama, SearXNG, LanceDB, and FTS5.
- Add CLI commands for chat, one-shot ask, learn, query, libraries, search,
  memory, model listing, and doctor checks.
- Add public `library` terminology while keeping `collection` compatibility.
- Add local knowledge MCP and web MCP servers.
- Add direct plain-text and Markdown fetch handling for docs such as
  `https://react.dev/llms.txt`.
- Add text-form tool-call parsing for local models that do not return structured
  tool calls.
- Add dirty-worktree protection for AI write and commit tools.
- Add online documentation source list and installer helper.
- Add repository guidance for future agent sessions.
