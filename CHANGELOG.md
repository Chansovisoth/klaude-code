# Changelog

## Unreleased

- Fix picker scrolling by tracking the selected row in the renderer; add
  PageUp/PageDown navigation and Escape cancellation. Standardize reset and
  cancel rows across selection menus, preview theme changes, and support
  validated, persistent minimum/maximum composer heights.

- Keep multiline terminal pastes together as one `klaude chat` request instead
  of generating once per pasted line.
- Prevent Enter from crashing `/model` or another slash command when its
  completion menu is open but no suggestion is selected.
- Add a bordered interactive chat surface with input history, slash-command
  completion, model and reasoning-effort pickers, context/token telemetry,
  deliberate multiline editing, and terminal-only styled Markdown/code panels.
- Render all picker options as a highlighted, scrollable list inside the input
  field, add visible cancellation to model/effort/theme flows, and sort model
  pickers and model listings alphabetically.
- Replace the blocking terminal chat loop with a persistent full-screen layout:
  output stays above a full-width live input, background turns leave typing
  available, multiple inputs queue, Ctrl+Enter or `/steer` can prioritize a new
  instruction, Alt+Enter inserts a newline, and Ctrl+C interrupts at the next
  safe boundary. Enable Kitty and xterm modified-key reporting only while the
  TUI is active, restore both on exit, and provide Ctrl+J as a newline fallback
  for terminals such as MobaXterm that collapse modified Enter into plain Enter.
- Show queued follow-up inputs in a compact live strip above the composer and
  provide a queue editor: repeated Alt+Up walks from newest to oldest, Enter
  saves, empty text plus Enter deletes, and queue consumption pauses during edits.
- Add a branded alternate-screen welcome view with a boxed block Klaude logo
  and current package version, plus persistent, independent TUI appearance
  controls: Autumn chrome by default plus Pastelle Pink, Hacker
  Green, and Neon Synth; separate VS Code Dark, GitHub Dark, Monokai, and
  Solarized Light Markdown/code colors; and reset-to-default actions for both.
- Render `/help` category names with underline styling and separate each user
  and Klaude message with a full-width gray divider containing its local date
  and time.
- Centralize appearance under Theme, Output Field, and Input Field settings;
  default the output border and scrollbar off, keep the rounded input border
  independently configurable, add a persistent 1–12 line input-height control
  with an 8-line default, migrate legacy flat preferences, and remove redundant
  dashed rows beneath command-reference category names.
- Reuse the last successfully selected model on the next `klaude chat` launch,
  while keeping explicit `--model` and the configured coder role as overrides
  and fallback respectively.
- Add `/keybinds` for a deterministic keyboard-only reference, and
  show described slash-command suggestions immediately when input starts with
  `/`.
- Bound the default agent loop to eight model steps per turn and recover from
  Qwen/Ollama tool-XML `unexpected EOF` failures with one tool-free retry.
- Show safe reasoning/drafting progress, prevent reasoning-only blind retries,
  and validate Python/GDScript before displaying code, with at most two
  diagnostic-driven repair attempts.
- Preserve concise model-authored search queries, require every explicitly
  requested search/fetch operation, retain query-relevant excerpts from long
  fetched pages, and retry once when an explicitly requested source URL is
  omitted.
- Keep explicit no-search prompts out of focused CLI command help, and restore
  `git_status` when current branch or dirty-worktree inspection is requested.

- Route self-contained code generation without retrieval tools, honor explicit
  no-search requests, use a compact code prompt with live output streaming, and
  retain durable user/project preferences in that prompt.
- Add independent `[ollama.code_options]` and `code_think` tuning so constrained
  and high-end machines can choose different code budgets without silent model
  switching, plus one tool-free recovery for malformed Qwen tool XML.
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
