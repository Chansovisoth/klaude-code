# Browser feature completion validation

This pass adds working browser flows across Memory, Connections, conversation
management, configured model choice, agent settings, chat tools and Generated.
It does not establish full CLI/browser feature parity. Remaining work is tracked
in `feature-completion-plan.md` and `coverage.md`.

The initial worktree already contained substantial uncommitted WebUI/application
changes. They were retained; no commit, push, reset, stash or checkout was made.

## Behavior and ownership

- Owner cookies, Origin, CSRF and tab/session checks remain in the HTTP adapter.
  Profile mutations reuse the existing immutable review, durable receipt and
  owned worker. Uncertain effects retain their resource fence.
- Memory reads are bounded and hide sensitive entries; edits/deletions use exact
  content IDs. Automatic memory uses existing conservative rules after a committed
  browser turn. Stale automatic-memory/settings writes are rejected.
- Agent settings use allowlisted fields in the existing shared preference file.
  The shared writer rechecks each reviewed raw field under its file lock and
  preserves unrelated changes. Future turns reload effective execution limits,
  tool availability, permission policies and Search/Fetch routing. Search settings
  expose provider, result count, Tavily depth and SearXNG endpoint; Fetch exposes
  local/Exa routing, fallback and Crawl4AI/Exa switches and the Crawl4AI endpoint.
  URLs reject credentials, queries and fragments. Research defaults use their
  existing locked writer and validate output/context budgets together.
- File details offers reviewed Knowledge learning from a saved current artifact.
  UTF-8 input is capped at 2 MiB; PDF/DOCX extraction reuses the disposable parser
  and rejects truncated output beyond 32,000 characters. The worker checks the
  exact revision, saved status, byte count and checksum before any embedding.
  Indexed sources use stable artifact IDs; unchanged text is not embedded again.
  Memory prompt and code-generation contexts both refresh before a turn.
- MCP definition changes use the same witnessed receipt/resource as CLI/TUI;
  local recovery commands can inspect unknown outcomes. Remote additions start
  disabled. Enable discovers actual schemas; interactive OAuth and custom stdio
  creation remain terminal-owned. Browser definition management is loopback-only.
  Browser MCP calls require exact review and recheck the enabled definition.
- Conversation browsing filters workspace/archive state before its database
  limit. Archive/delete exclude the selected conversation; permanent deletion
  rechecks the reviewed history inside SQLite's write transaction. Markdown
  downloads bound selected input/output and exclude private model/tool content.
- Provider/model selection reads exact configured catalogs; native Ollama also
  requires fresh completion/tool declarations. Session resume checks the exact
  saved definition and credential revisions without catalog contact or generation.
  A chat model selection does not change default roles or saved startup preferences.
  The later media continuation adds separate reviewed Model Defaults changes.
- Research keeps its saved provider, credential and budget binding. Run uses the
  existing evidence-checked Research owner; stop does not replay generation.
  Images use the configured image service, immutable reviewed dimensions/model/
  seed, real generation receipts and original output checks. Recovery requests
  only acknowledged job output. Browser image-service configuration, Vision and
  AI tags are now covered by `media-controls-validation.md`.
- Existing hosts can serve new static assets before reloading Python. Missing
  capabilities disable new controls with restart guidance; capability arrival
  after authentication refreshes the selected management page.

## Evidence

- Focused HTTP/worker tests cover authentication, hidden secrets, exact reviews,
  duplicate IDs, stale Memory/settings/session/model changes, workspace scope,
  real Research queue/stop and real local image generation/persistence.
- Scripted model tests exercise actual Skill allow/deny execution, current Memory
  injection, automatic memory, effective settings and reviewed MCP calls, including
  definition changes between review and execution. Configured provider tests
  exercise transport selection, supported efforts and exact session restore.
- The Generated Research adapter completes a stored cited report through the
  existing deterministic model/source fixture. This is not live-provider evidence.
- `scripts/webui_management_smoke.py` uses real Chrome 148, isolated profile/data,
  actual HTTP and owned workers. It verifies setting review/save, Memory add and
  automatic setting, Connections add-disabled/reload, conversation rename,
  Research queue/stop, and image generation/save against a local fixture server.
  Saved-document learning also uses an actual owned worker and Knowledge index
  with a deterministic loopback embedding fixture.
  Settings, Integrations and Generated fit 320, 390, 768 and 1440px viewports;
  logout clears private management content. No console errors were observed.
- Repository Ruff, production mypy across all seven source roots, JavaScript
  syntax checks and the seven-wheel install/import/help smoke pass.

Final checks:

- The final feature batch passed **29 tests**, including the new saved-file,
  Search/Fetch/Research settings and Memory-context cases.
- Host, Web Library and Knowledge regressions passed **85 tests**.
- The broad `tests/unit` run reached **4,034 of 4,123 collected tests** before its
  explicit 900-second limit: 4,014 passed, 19 skipped and one failed. The failure
  was an older TUI assertion expecting `LEARNING`, superseded by the existing
  shared `Waiting` activity vocabulary. Its corrected assertion passes in the
  focused batch. The **89 unreached tests passed** in a separate 17-second run.
  The ten tests added after broad collection also pass in the feature batch.
  This is split validation, not an uninterrupted green full-suite run.
- Repository Ruff, production mypy (**219 source files**), JavaScript syntax,
  `git diff --check` and the final seven-wheel build/install/import/CLI smoke pass.
- The final Chrome smoke passes all recorded flows at 320/390/768/1440px, including
  actual saved-document indexing, with zero browser console errors.

No physical-device, cross-browser, live cloud-model, live public-web Research or
real GPU image-server certification is implied by deterministic/local fixtures.

## Managed host

The existing managed host was confirmed idle with no queued turns, questions,
approvals or active browser operations, then gracefully reloaded. Its selected
workspace and conversation and both loopback/LAN listeners were preserved.
The new runtime reports `profile_management` and `model_providers`; the live
index, `management.js` and `library.js` return HTTP 200 with the current controls.
Browser cookies were revoked by the normal stop path, requiring a fresh sign-in.
No user Memory, connection, preference or Library record was modified as a probe.
