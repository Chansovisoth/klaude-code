# klaude-code

A local-first AI coding agent. The agent, models, memory, and knowledge base run on your machine by default: Ollama for models, SearXNG for web search, LanceDB for documentation you teach yourself. Optional providers such as Exa, Hugging Face, or a remote Crawl4AI endpoint can use API keys when you choose to enable them.

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
- **Searches the web privately**: self-hosted SearXNG (70+ engines, no keys, no limits) + a clean-markdown fetch cascade. Optional providers such as Exa can be enabled with API keys in `.env`.
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
| `klaude docs update --online` | update sources listed in `online-docs.txt`, skipping unchanged indexing |
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

Inside `klaude chat`, use `/help` or `/commands` to print the command reference
without asking the model to summarize it.

`scripts/knowledge/install-online-docs.sh` writes timestamped logs under
`logs/knowledge/online-docs/` by default. Set `KLAUDE_LOG_DIR` to store logs
somewhere else. Failed `learn` commands are saved separately for retry.

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

Monorepo (`uv` workspace): `packages/core` (engine), `packages/knowledge`, `packages/web`, `packages/tools_local`, `apps/cli`. Data lives in `~/.local/share/klaude/`, config in `~/.config/klaude/config.toml`.

Imported documentation and assistant skills are permanent user data, not repo
files:

```text
~/.local/share/klaude/docs-sources/<name>/
  manifest.json
  current/            # active llms.txt-linked docs or crawled pages
  snapshots/          # timestamped previous current/ trees

~/.local/share/klaude/skills/<name>/
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

All service secrets live in a gitignored `.env` file (generated by the installer from `.env.example`, `chmod 600`). Tracked config files never contain credentials — `deploy/searxng/settings.yml` is safe to commit and share as-is. Add future service tokens to `.env`, never to yaml/toml.

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
the final fallback. Search/fetch evidence remains temporary and is not written
to memory or learned libraries.

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
models, datasets, and Spaces by default. Add `HUGGINGFACE_API_KEY` to `.env`
when you want authenticated Hub access.

## Optional: JS-heavy scraping tier

```bash
docker compose --profile heavy up -d   # starts Crawl4AI
# then in ~/.config/klaude/config.toml:
# [services] crawl4ai_url = "http://localhost:11235"
```

Without it, fetching falls back to raw HTTP + trafilatura extraction (works for most docs sites). `klaude crawl` is intentionally conservative: same-domain only, robots.txt on by default, 50-page cap, depth 2, and a randomized 2-5 second delay between pages. Use `--sitemap` to seed URLs from robots.txt Sitemap entries and `/sitemap.xml`, `--include` / `--exclude` to constrain URL patterns, and tune defaults under `[crawler]` in config when you control the target site.

## License

MIT
