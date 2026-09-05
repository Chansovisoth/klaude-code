# klaude-code

A local-first AI coding agent. The agent, models, memory, and knowledge base run on your machine by default: Ollama for models, SearXNG for web search, LanceDB for documentation you teach yourself. Optional providers such as Exa, Tavily, Hugging Face, or a remote Crawl4AI endpoint can use API keys when you choose to enable them.

```
you> add input validation to the signup route

-> read_file        src/routes/signup.ts
-> query_knowledge  "zod schema validation route handler"
-> edit_file        src/routes/signup.ts        [y/n/a]
-> run_shell        npm test                    [y/n/a]

done — committed on branch klaude/20260712-1430
```

## What it does

- **Codes with you**: reads, edits, greps, runs shell commands — each destructive action behind a y/n/always permission gate.
- **Learns documentation**: `klaude learn https://nextjs.org/docs -l nextjs` scrapes, chunks, embeds, and stores docs in a named library. For multi-page sites, `klaude crawl https://docs.example -l docs` politely follows same-domain links and stores a refreshable docs source. The agent then answers from *your* knowledge base before touching the web (hybrid BM25 + vector + rerank retrieval).
- **Searches the web privately**: self-hosted SearXNG (70+ engines, no keys, no limits) + a clean-markdown fetch cascade. Optional providers such as Exa and Tavily can be enabled with API keys in `config/.env`.
- **Learns names locally**: RapidFuzz corrects conservative country, software, and entity-name typos against stable vocabulary and a compact local SQLite cache. An optional keyless Wikidata fallback can teach Klaude new canonical names and aliases without making search depend on Wikimedia.
- **Git-native**: never touches your branch. Works on `klaude/<task>`, one commit per edit — review everything with `git diff`, or in VS Code's Source Control panel, and revert any single action.
- **Remembers you**: `klaude remember "we use Tailwind"` — durable facts injected into every session.
- **Plugs in anywhere**: the knowledge and web layers are also MCP servers, usable from OpenCode, Cline, Claude Code, or any MCP client.

## Quickstart (Ubuntu/Debian)

Prereqs: [Ollama](https://ollama.com/download), Docker, ~10GB disk for models.

```bash
git clone https://github.com/Chansovisoth/klaude-code && cd klaude-code
make setup          # docker services + uv sync + models for your RAM tier + doctor
uv run klaude chat  # or: uv tool install --editable apps/cli && klaude chat
```

`make setup` asks how you want to run Ollama — use an existing install (auto-detected, just press Enter), install system-wide, run it in Docker, point at a remote URL, or skip. Non-interactive installs (`curl | bash`, CI) skip the menu with sane defaults, or force a choice with `--ollama=existing|system|docker|url:URL|skip` and `--no-models`. Model pulls auto-detect your hardware: 32GB+ RAM pulls `qwen3-coder:30b` (30B MoE, the best local coding model that runs on CPU+RAM), 16GB pulls `gpt-oss:20b`, 8GB pulls `qwen3:4b` — and anything you already have is skipped, never re-downloaded.

## Commands

| Command | What it does |
|---|---|
| `klaude chat` | interactive agent session in the current repo |
| `klaude ask "…"` | one-shot question, tools enabled |
| `klaude learn URL -l nextjs` | ingest docs into a named library |
| `klaude docs add react https://react.dev/llms.txt -l react` | install refreshable `llms.txt` docs |
| `klaude crawl https://docs.example -l docs --sitemap --include '*/docs/*'` | crawl same-domain docs pages into a refreshable library |
| `klaude docs update react` | refresh installed docs and snapshot old files if changed |
| `klaude docs update --online` | update sources listed in the configured online docs file, skipping unchanged indexing |
| `klaude import-skill crawl4ai-skill.zip -l crawl4ai` | install a skill package and index its text |
| `klaude query "…" -l nextjs` | inspect raw retrieval from a library (no LLM) |
| `klaude libraries` | list learned libraries |
| `klaude skills` | list installed assistant skills |
| `klaude search "…"` | web search via the configured provider |
| `klaude code-search "…"` | search programming docs and code examples |
| `klaude huggingface-search model "qwen coder"` | search Hugging Face Hub models, datasets, and Spaces |
| `klaude huggingface-readme model Qwen/Qwen3-Coder-30B-A3B-Instruct` | fetch a Hub model card, dataset card, or Space README |
| `klaude remember "…"` | save a durable fact |
| `klaude memory status` | inspect memory settings and locations |
| `klaude memory list` | list durable saved memories |
| `klaude memory search "DanTDM"` | search previous conversation sessions |
| `klaude session-search "DanTDM"` | search previous conversation sessions |
| `klaude status` | show configured modes, storage, and tool permissions |
| `klaude system-info --json` | inspect normalized runtime context given to the model |
| `klaude doctor` | verify services, models, config |

`-l` / `--library` is the friendly name for a knowledge bucket. `-c` / `--collection` still works as a compatibility alias.

Inside `klaude chat`, use `/help` to print the command reference
without asking the model to summarize it.

The interactive terminal is a full-screen conversation: output stays above a
full-width input at the bottom, and the input remains usable while Klaude is
thinking, searching, or writing. Enter submits immediately or queues behind the
active turn; Ctrl+Enter (or `/steer TEXT`) prioritizes a correction and interrupts
at the next safe model/tool boundary. `/queue` shows pending turns and `/cancel`
interrupts without adding one. Queued follow-ups appear in a compact live strip
immediately above the input. Repeated Alt+Up edits them from newest to oldest;
Enter saves the current edit, while clearing all text and pressing Enter deletes
that queued input. Queue consumption pauses while an item is being edited. The status line continuously shows the model,
reasoning effort, queue, activity, context usage, and last input/output tokens.
Up/down recall prior inputs, Tab completes slash commands, and Alt+Enter inserts
a newline when the terminal reports it distinctly. Ctrl+J is the compatibility
newline shortcut for terminals such as MobaXterm that collapse modified Enter
into plain Enter. `/model` and `/effort` use inline arrow-key pickers without leaving
the chat screen, displaying the available options and highlighted selection
inside the input frame rather than replacing the input with one option at a
time. All selection menus end with reset to default and cancel; cancelling the
effort step after choosing a model restores the original model. Model lists are
sorted alphabetically. Klaude remembers the last successfully selected chat model
across launches; an explicit `--model` overrides and updates that preference.
Typing `/` as the first input character immediately opens slash-command
suggestions with descriptions. `/keybinds` lists every keyboard control and
does not include slash commands or involve the model.
`/settings` organizes appearance under Theme, Output Field, and Input Field.
The output border defaults to off and the scrollbar defaults to on; the rounded input border
defaults to on. Input Field → Height → Enter min/max accepts two whole numbers
(for example `2 10`). The composer grows between those limits; valid limits
satisfy `1 ≤ min ≤ max ≤ 12`, with defaults of 8 and 12. Enter saves, Escape or
Ctrl+C cancels, and typing `reset to default` restores both defaults.
Each category can be reset independently. Autumn is the
default interface theme, with Pastelle Pink, Hacker Green, and Neon Synth also
included. Text/code colors remain independent: VS Code Dark, GitHub Dark,
Monokai, or Solarized Light. `/theme` opens Theme settings for both color choices.
Choices persist in `.klaude/data/appearance.json`. Non-interactive and piped
output remains plain.

Navigating interface themes previews the colors immediately. Text-theme pickers
show a temporary sample in the output. Enter saves the chosen colors; cancel
restores the previous colors and removes the sample. Picker lists follow the
selected row when scrolling; PageUp/PageDown navigate and Escape cancels.

Each session starts with a session divider after the logo and intro. Each user
message is followed by its timestamped user divider; streamed assistant output
is followed by a closing Klaude divider with elapsed duration.
`/help` category names are underlined
without adding separate underline rows.

Modified Enter keys use the terminal's distinct key sequences. While the TUI is
active, Klaude enables Kitty keyboard disambiguation and xterm modifyOtherKeys,
then restores both on every exit path. It accepts both protocols' sequences.
Terminals that implement neither protocol may collapse modified Enter into
ordinary Enter before any terminal application can inspect it; use Ctrl+J for a
newline and `/steer TEXT` for terminal-independent steering in that case.

Multiline clipboard pastes are submitted as one chat turn. Explicit web or
local-library search requests get one bounded compliance retry if a small model
tries to answer from memory instead of calling the requested retrieval tool.
When a prompt explicitly requests both discovery and page reading, Klaude
requires both model-directed operations and keeps query-relevant excerpts from
long fetched pages within the local model's context. Explicit no-search wording
never becomes focused help for the `klaude search` command.
Python and GDScript are mechanically checked before display and receive at most
two diagnostic-driven repair attempts when validation finds concrete defects.

`scripts/knowledge/install-online-docs.sh` writes timestamped logs under
`logs/knowledge/online-docs/` by default. Set `KLAUDE_LOG_DIR` to store logs
somewhere else. Failed `learn` commands are saved separately for retry.

Config examples live in `config/examples/`. Local editable config lives right
beside it in `config/config.toml`, `config/.env`, `config/searxng.env`,
and `config/online-docs.txt`.

## Architecture

```
terminal TUI ──► agent engine (loop · router · permission gate)
                    │
      ┌─────────────┼──────────────────┐
   Ollama        tool layer         knowledge layer
 coder/vision   fs·git·shell       LanceDB + FTS5 hybrid
 embeddings     SearXNG+fetch      docs cache · memory
                    │
              MCP plugin servers
```

Monorepo (`uv` workspace): `packages/core` (engine), `packages/knowledge`, `packages/web`, `packages/tools_local`, `apps/cli`. Source checkouts keep local editable config in visible `config/`: `config/config.toml`, `config/.env`, `config/searxng.env`, and `config/online-docs.txt`. Runtime data stays in gitignored `.klaude/data/`, including the learned name cache at `.klaude/data/entities.sqlite`. Set `KLAUDE_CONFIG_DIR` or `KLAUDE_DATA_DIR` to override those locations; set `KLAUDE_HOME` to relocate both under one custom home. Installed packages outside a source checkout fall back to `~/.config/klaude/` and `~/.local/share/klaude/`.

Search-query normalization preserves the original text, normalized text, and
per-correction provenance. The fast path is entirely local: stable structured
vocabulary, SQLite aliases, and RapidFuzz. To opt into the free online fallback
for unresolved probable names, use:

```toml
[entities.wikimedia]
enabled = true
```

Only the minimal candidate name is sent to Wikidata. Timeouts, outages, and
ambiguous results are ignored safely; ordinary search continues unchanged.

Ollama daemon settings stay with the Ollama launcher itself, such as systemd,
Docker Compose, or `ollama run` parameters. Klaude only owns request tuning for
the chat calls it sends: `config/config.toml` has `[ollama.options]`. For
example, `num_thread = 8` asks Ollama to use all 8 logical CPU threads for
Klaude chat requests, while GPU placement remains Ollama's automatic CUDA
behavior unless you explicitly set `num_gpu`. Self-contained code generation
uses a smaller prompt and streams output immediately. Machines with additional
capacity can tune code separately without changing ordinary chat:

```toml
[ollama]
code_think = "low"

[ollama.code_options]
num_ctx = 16384
num_predict = 4096
temperature = 0.15
```

Leave those overrides unset for the bounded defaults. Klaude never silently
switches the selected model based on hardware.

Imported documentation and assistant skills are permanent user data, not repo
files:

```text
.klaude/data/docs-sources/<name>/
  manifest.json
  current/            # active llms.txt-linked docs or crawled pages
  snapshots/          # timestamped previous current/ trees

.klaude/data/skills/<name>/
  manifest.json
  source.zip          # when imported from a zip
  current/            # active SKILL.md, references, scripts, docs
  snapshots/          # timestamped previous current/ trees
```

`klaude import-skill` re-imports into the same skill name by replacing `current/`
and re-indexing text files into the selected library. `klaude docs update` does
the same for `llms.txt` and crawled documentation sources. If downloaded content is
unchanged, Klaude updates `checked_at` without creating a snapshot. By default it
keeps the last 3 snapshots. Searchable chunks live in the knowledge store;
original files stay in `docs-sources/` and `skills/`.

## Memory

Klaude keeps two memory layers:

- `memory.md`: concise durable facts that load into every chat.
- `sessions.db`: searchable prior conversation turns, kept separate from durable
  memory.

Conservative auto-memory is on by default. It only saves clear, high-signal
preferences or project decisions, prints a small notice when it saves, skips
secrets, and can be turned off:

```bash
uv run klaude memory off
uv run klaude memory on
uv run klaude memory forget "old preference"
uv run klaude session-search "DanTDM"
```

## Runtime Context

At model startup Klaude collects a short, local runtime context block so the
model knows the current directory, Git root/branch/dirty state, OS, shell,
hardware summary, local time, timezone, and approximate country when it can be
inferred from local timezone data. Fastfetch is preferred for structured JSON,
Neofetch is fallback-only, and a native local collector is used when neither is
installed.

This is volatile runtime data, not durable memory, and it is not written to
`memory.md`. Network geolocation is off by default; Klaude does not contact an
IP location service unless explicitly configured. Inspect the normalized context
with `uv run klaude system-info` or disable it with:

```toml
[runtime_context]
enabled = false
```

## Use it inside VS Code today

The MCP servers work in Cline/Continue right now — add to your MCP config:

```json
{
  "mcpServers": {
    "klaude-knowledge": { "command": "uv", "args": ["run", "--directory", "/path/to/klaude-code", "klaude-knowledge-mcp"] },
    "klaude-web":       { "command": "uv", "args": ["run", "--directory", "/path/to/klaude-code", "klaude-web-mcp"] }
  }
}
```

And because klaude commits every edit on its own branch, VS Code's built-in diff/SCM views already show and review its work. A native extension (chat sidebar over `klaude serve`) is the phase-2 roadmap.

## Secrets

All service secrets live in gitignored `config/.env` (generated by the installer from `config/examples/.env.example`, `chmod 600`). A root `.env` is still ignored as a legacy compatibility input, but new installs copy or generate secrets under `config/`. Tracked config files never contain credentials. Add future service tokens to `config/.env`, never to yaml/toml.

Container service env is kept narrow. SearXNG reads only `config/searxng.env`;
it should not receive search-provider API keys.

Do not put Ollama chat options such as `num_thread` or `num_ctx` in `.env`.
Those belong in `config/config.toml` under `[ollama.options]`. Ollama daemon
environment variables belong in Ollama's own service or container configuration.

Optional provider keys use the `PROVIDER_API_KEY` pattern:

```bash
GEMINI_API_KEY=...
PARALLEL_API_KEY=...
TAVILY_API_KEY=...
EXA_API_KEY=...
FIRECRAWL_API_KEY=...
HUGGINGFACE_API_KEY=...
CRAWL4AI_API_KEY=...
```

Klaude uses relevance-first provider routing for web search. Configured
providers are tried according to query intent, missing optional keys are skipped
quietly, DDGS is the preferred keyless fallback when installed, and SearXNG is
the final fallback. Tavily is an optional hosted Search provider: queries leave
your machine, free monthly credits are limited, and Klaude falls back to other
providers when Tavily is missing, invalid, rate-limited, unavailable, or out of
credits. Search/fetch evidence remains temporary and is not written to memory or
learned libraries.

In chat, ordinary browsing is a bounded model-directed loop: Klaude searches
for source leads, inspects snippets, selectively reads promising pages, and can
refine the query around the most important missing information. The runtime
prevents repeated equivalent searches and canonical duplicate fetches, keeps a
compact per-turn action/source trace, and enforces the configurable
`[web.search.behavior]` action, search, fetch, per-domain, and consecutive-failure
budgets. When a budget is exhausted, Klaude answers from the evidence already
gathered and identifies material uncertainty instead of discarding the work.

Tavily integration status:

- Implemented: `web_search` can use Tavily Search through the provider router.
- Postponed: Tavily Extract, Crawl, Map, and Research are not exposed as Klaude
  tools. `fetch_url` keeps using Klaude's local direct/Crawl4AI/trafilatura
  cascade, and `crawl_site` keeps using Klaude's bounded same-domain crawler.
- Disable Tavily by leaving `TAVILY_API_KEY` empty or setting
  `[web.providers.tavily] enabled = false` in `config/config.toml`.
- Test Tavily without exposing secrets with
  `uv run klaude search "test query using Tavily" -n 3`.

Firecrawl integration status:

- Implemented: `web_search` can use Firecrawl Search through the provider
  router. Klaude uses Firecrawl's v2 Search API and does not request scraped
  page content for every result.
- Postponed: Firecrawl Scrape, Crawl, Map, Monitor, Parse, Interact, and
  Research are not exposed as Klaude tools. `fetch_url` keeps using Klaude's
  local direct/Crawl4AI/trafilatura cascade, and `crawl_site` keeps using
  Klaude's bounded same-domain crawler.
- Disable Firecrawl by leaving `FIRECRAWL_API_KEY` empty or setting
  `[web.providers.firecrawl] enabled = false` in
  `config/config.toml`.
- Test Firecrawl without exposing secrets with
  `uv run klaude search "test query using Firecrawl" -n 3`.

Codex MCP access to Tavily or Firecrawl is separate from Klaude-code native
integration. MCP tools configured for this Codex coding session do not
automatically make those providers available to Klaude's Ollama models.

Billing is conservative by default:

```toml
[web.billing]
mode = "prepaid_free_search_allowance"
allow_paid_overage = false
allow_auto_recharge = false
```

To force a legacy provider for compatibility, set `[web] provider = "local"` for
SearXNG-only search or `provider = "exa"` for Exa-only search.

Hugging Face Hub lookup is separate from web search and works against public
models, datasets, and Spaces by default. Add `HUGGINGFACE_API_KEY` to `config/.env`
when you want authenticated Hub access.

## Optional: JS-heavy scraping tier

```bash
docker compose --profile heavy up -d   # starts Crawl4AI
# then in config/config.toml:
# [services] crawl4ai_url = "http://localhost:11235"
```

Without it, fetching falls back to raw HTTP + trafilatura extraction (works for most docs sites). `klaude crawl` is intentionally conservative: same-domain only, robots.txt on by default, 50-page cap, depth 2, and a randomized 2-5 second delay between pages. Use `--sitemap` to seed URLs from robots.txt Sitemap entries and `/sitemap.xml`, `--include` / `--exclude` to constrain URL patterns, and tune defaults under `[crawler]` in config when you control the target site.

## License

MIT
