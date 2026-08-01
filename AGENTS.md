# Agent Guidance

This file applies to the whole repository. Keep it concise and update it when
project behavior changes.

## Project Summary

`klaude-code` is a local-first AI coding agent. It runs against local services:
Ollama for models, SearXNG for web search, LanceDB plus SQLite FTS5 for learned
documentation, and a Typer/Rich CLI for user interaction.

The repository is a Python `uv` workspace:

- `apps/cli`: `klaude` CLI commands and terminal rendering.
- `packages/core`: agent loop, Ollama client, config, permissions, and memory.
- `packages/tools_local`: workspace tools for read/list/grep/edit/shell/git.
- `packages/knowledge`: document chunking, hybrid retrieval, LanceDB/FTS5 store,
  and the knowledge MCP server.
- `packages/web`: SearXNG search, page fetch cascade, cache, and web MCP server.
- `scripts`: setup and helper scripts.
- `deploy/searxng`: tracked SearXNG config.

## User-Facing Terms

Use `library` in CLI help, README examples, and user-facing text for a named
knowledge bucket. Keep `collection` internally where the storage layer already
uses that term.

Public commands should prefer:

- `klaude learn URL -l react`
- `klaude query "hooks" -l react`
- `klaude libraries`

Keep these compatibility aliases working:

- `-c` / `--collection`
- `klaude collections`

## Core Features

- `klaude chat`: interactive local agent session in the current repo.
  In chat, `/help` and `/commands` print the public command reference directly;
  `/models`, `/model NAME`, and `/quit` remain the core chat controls.
- `klaude ask`: one-shot agent run with tools enabled.
- `klaude learn`: fetch or read a source, chunk/embed it, and store it in a
  named library.
- `klaude docs add`: install refreshable `llms.txt` documentation, preserve raw
  files, and index same-domain Markdown/text pages into a library.
- `klaude crawl`: politely crawl same-domain documentation pages, preserve raw
  Markdown output as a refreshable docs source, and index it into a library.
- `klaude docs update`: refresh installed documentation sources, snapshot old
  files if content changed, and re-index the library sources.
- `klaude docs update --online`: update `online-docs.txt` learn sources,
  skipping embedding/indexing for unchanged content.
- `klaude docs list`: list installed refreshable documentation sources.
- `klaude import-skill`: permanently install a skill ZIP/folder, preserve its
  files under user data, and index text files into a named library.
- `klaude query`: inspect raw hybrid retrieval results without an LLM answer.
- `klaude libraries`: list learned libraries.
- `klaude skills`: list installed assistant skills.
- `klaude search`: query the configured web provider; local SearXNG is the
  default.
- `klaude code-search`: search programming docs, code examples, and debugging
  references through the configured web provider.
- Chat tools include allowed read-only `current_time` and `weather_lookup`
  capabilities for date/time, weather, forecasts, and temperature questions.
- `klaude huggingface-search`: search Hugging Face Hub models, datasets, and
  Spaces.
- `klaude huggingface-details`: inspect Hub metadata for a model, dataset, or
  Space.
- `klaude huggingface-readme`: fetch a Hub model card, dataset card, or Space
  README as Markdown.
- `klaude remember`: append durable facts to local memory.
- `klaude memory status/on/off/list/add/forget/search`: inspect, control, edit,
  and search memory.
- `klaude sessions`: list recent conversation sessions.
- `klaude session-search`: search previous conversation sessions.
- `klaude status`: show configured modes, storage locations, and all agent tool
  permission policies without running service health checks.
- `klaude doctor`: verify services, models, config, and data directories.

## Data And Config

Default config lives in `~/.config/klaude/config.toml`.

Default data lives in `~/.local/share/klaude/`:

- `memory.md`: durable remembered facts injected into the system prompt.
- `sessions.db`: episodic session turns.
- `knowledge.lance/`: LanceDB vector tables plus `fts.db`.
- `docs-cache/<library>/`: raw learned source cache.
- `docs-sources/<name>/`: refreshable docs with `manifest.json`, `current/`, and
  timestamped `snapshots/`.
- `skills/<name>/`: installed assistant skill packages with `manifest.json`,
  optional `source.zip`, active files under `current/`, and timestamped
  `snapshots/`.

`KLAUDE_CONFIG_DIR` and `KLAUDE_DATA_DIR` can override these locations.

Project helper logs live under gitignored `logs/` by default. The online docs
installer writes timestamped files under `logs/knowledge/online-docs/`, including
a full run log, failed command list, failed output details, and skipped lines.
`KLAUDE_LOG_DIR` can override the log root for scripts.

## Memory Behavior

Keep durable memory concise and useful across sessions. Automatically save only
high-signal preferences, repeated corrections, project decisions, durable goals,
and important external references. Do not save one-off trivia, temporary
debugging details, raw transcripts, secrets, passwords, or API key values.

When the user says `remember that ...` with a clear durable fact, save it. When
the user says broad phrases such as `remember this`, `remember what I said`, or
`don't forget this topic`, summarize recent context into one concise memory and
ask before saving. If the user asks whether they mentioned something before, use
session search instead of claiming there is no prior-session access.

Session history is searchable recall, not durable memory. Keep it in
`sessions.db`; keep always-loaded facts in `memory.md`.

## Web And Knowledge Behavior

Web search does not automatically save to RAG. `web_search` returns temporary
search snippets, and `fetch_url` returns temporary fetched content. Only
`klaude learn`, `klaude docs add/update`, `klaude crawl`, and
`klaude import-skill` write into the knowledge store.

`klaude learn` is idempotent for unchanged content: if the raw cached source
matches the fetched/read text and that source is already indexed in the target
library, it skips embedding and indexing instead of replacing identical chunks.

Documentation source refreshes download into a temporary directory first,
validate/fetch same-domain Markdown/text links from `llms.txt`, compare
checksums, then snapshot and replace `current/` only when content changed.
Default retention is the last 3 snapshots, configurable with
`[knowledge] snapshot_retention`.

Crawled documentation sources are same-domain only, honor robots.txt by default,
follow HTML and Markdown/plain-text links, optionally seed URLs from robots.txt
Sitemap entries and `/sitemap.xml`, support include/exclude URL patterns, cap
page count/depth, use randomized delays between pages, and save the crawl
options in the docs source manifest so `klaude docs update` can refresh them
later.

Skill package imports use temporary directories only for unzip/validation. The
installed package is permanent user data under `~/.local/share/klaude/skills/`.
Re-importing the same skill name compares checksums, snapshots changed
`current/` trees, updates `manifest.json`, and removes previously indexed skill
sources before learning the new files.

The default web search strategy is relevance-first provider routing. Optional
providers use the `PROVIDER_API_KEY` pattern in `.env`, for example
`GEMINI_API_KEY`, `PARALLEL_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY`,
`FIRECRAWL_API_KEY`, `CRAWL4AI_API_KEY`, or `HUGGINGFACE_API_KEY`. Missing
optional keys are normal and should be skipped quietly. DDGS is the preferred
keyless fallback when its optional Python package is installed. SearXNG remains
available as an explicit `web.provider = "local"` compatibility mode and as the
final fallback for quality search. Klaude's local fetch cascade remains the
preferred page extraction path before external extraction providers.

`packages/web/src/klaude_web/fetch.py` should fetch plain text, Markdown, JSON,
and XML responses directly before falling back to Crawl4AI or Trafilatura. This
is important for URLs such as `https://react.dev/llms.txt`.

Hugging Face Hub support is its own integration, not the default web provider.
Use the full secret name `HUGGINGFACE_API_KEY` in `.env`; do not abbreviate it to
`HF_TOKEN` in user-facing docs or examples.

`llms.txt` support learns the index plus same-domain linked Markdown/text pages.
Use `klaude crawl` for documentation sites that do not publish a useful
`llms.txt`.

## Agent And Tool Safety

The agent loop should execute both structured Ollama `tool_calls` and the
text-form tool-call format some local models emit, for example:

`<function=web_search> <parameter=query> Dieng city country </tool_call>`

Do not print that text-form call as normal assistant output when it can be
parsed as a known tool call.

When a user asks what Klaude can do or which commands exist, expose public CLI
and slash commands only. Internal tool names should stay implementation details.

Do not expose file write/shell tools just because the user says "how to code".
Tutorial and framework questions should favor `query_knowledge`, `code_search`,
and web lookup until the user asks to inspect or modify workspace files.

`klaude chat` creates or switches to a `klaude/<timestamp>` branch when the
worktree is clean. If the worktree is dirty, chat may still answer/read/search,
but write tools must not modify files or commit until the user commits or
stashes their changes.

Never commit `.env`. Service secrets belong in gitignored `.env`, generated from
`.env.example`. Tracked YAML/TOML files should not contain credentials.

Be careful with `run_shell`: it is powerful and currently uses shell execution.
Prefer read-only commands for investigation and keep destructive actions behind
explicit user intent.

## Development Commands

Use these checks after relevant changes:

- `uv run pytest tests/unit`
- `uv run python -m py_compile <changed-python-files>`
- `bash -n scripts/install.sh`

Ruff may not be installed in all local environments even though project config
exists for it. If available, use `uv run ruff check ...` and
`uv run ruff format ...`.

## Git Notes

Before committing or pushing, always inspect:

- `git status --short --branch`
- `git branch -vv`

The user may use VS Code for commits/pushes. If a change lands on a
`klaude/...` branch but should be on `master`, merge or cherry-pick deliberately;
do not rewrite `master` unless the user explicitly asks.
