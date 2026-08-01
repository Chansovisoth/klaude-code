# Changelog

## Unreleased

- Add optional web provider configuration with local default and Exa support via
  `EXA_API_KEY`.
- Add `code_search` / `klaude code-search` for programming docs and examples.
- Add Hugging Face Hub search, metadata, and README tools using
  `HUGGINGFACE_API_KEY` for optional authenticated access.
- Add skill package installation with permanent `skills/<name>/current` storage,
  manifests, stale-index cleanup, `klaude import-skill`, and `klaude skills`.
- Add refreshable `llms.txt` documentation sources with `klaude docs add`,
  `klaude docs update`, same-domain Markdown fetching, manifests, checksum
  comparison, snapshots, and retention.
- Add polite same-domain multi-page crawling with `klaude crawl`, saved crawl
  manifests, refresh through `klaude docs update`, and Crawl4AI auth support via
  `CRAWL4AI_API_KEY`.
- Add optional sitemap seeding, include/exclude URL filters, and crawl progress
  output for documentation ingestion.
- Add conservative automatic memory, explicit memory management commands, and
  searchable prior-session recall tools.
- Skip re-embedding and re-indexing unchanged learned sources, and report
  unchanged entries separately in the online-docs installer.
- Add `klaude docs update --online` for refreshing `online-docs.txt` sources
  without invoking the shell installer directly.
- Add `klaude status` for configured modes, storage locations, and tool
  permission policies.

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
