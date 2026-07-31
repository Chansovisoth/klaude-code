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
- `klaude ask`: one-shot agent run with tools enabled.
- `klaude learn`: fetch or read a source, chunk/embed it, and store it in a
  named library.
- `klaude query`: inspect raw hybrid retrieval results without an LLM answer.
- `klaude libraries`: list learned libraries.
- `klaude search`: query local SearXNG.
- `klaude remember`: append durable facts to local memory.
- `klaude doctor`: verify services, models, config, and data directories.

## Data And Config

Default config lives in `~/.config/klaude/config.toml`.

Default data lives in `~/.local/share/klaude/`:

- `memory.md`: durable remembered facts injected into the system prompt.
- `sessions.db`: episodic session turns.
- `knowledge.lance/`: LanceDB vector tables plus `fts.db`.
- `docs-cache/<library>/`: raw learned source cache.

`KLAUDE_CONFIG_DIR` and `KLAUDE_DATA_DIR` can override these locations.

## Web And Knowledge Behavior

Web search does not automatically save to RAG. `web_search` returns temporary
search snippets, and `fetch_url` returns temporary fetched content. Only
`klaude learn` writes into the knowledge store.

`packages/web/src/klaude_web/fetch.py` should fetch plain text, Markdown, JSON,
and XML responses directly before falling back to Crawl4AI or Trafilatura. This
is important for URLs such as `https://react.dev/llms.txt`.

Current `llms.txt` support learns the index itself. Recursive ingestion of every
linked Markdown page is not implemented yet.

## Agent And Tool Safety

The agent loop should execute both structured Ollama `tool_calls` and the
text-form tool-call format some local models emit, for example:

`<function=web_search> <parameter=query> Dieng city country </tool_call>`

Do not print that text-form call as normal assistant output when it can be
parsed as a known tool call.

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
