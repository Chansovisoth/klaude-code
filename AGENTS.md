# Agent Guidance

This file applies to the whole repository. Keep it current when project
behavior changes; future agents should be able to understand the product from
this file before diving into implementation details.

## Project Summary

`klaude-code` is a local-first AI coding agent, version `0.2.0a4`. It runs as a
Python `uv` workspace with a Typer/Rich CLI, Ollama model runtime, local memory,
refreshable knowledge libraries, multi-provider web search, local-first URL
fetching, an external MCP client, and MCP servers for the web and knowledge
layers.

The main user-facing executable is `klaude`, which launches the full interactive
agent with no subcommand. `klaude chat` remains a compatibility alias; the MCP
servers expose Klaude's web and knowledge tools to other agents, but they are
not the full Klaude chat agent.

Workspace layout:

- `apps/cli`: Typer commands, Rich terminal rendering, deterministic command
  reference/help, chat loop wiring, tool display formatting, docs/session/memory
  CLI commands.
- `packages/core`: config loading, Ollama HTTP client, system prompt, agent
  loop, permission gate, memory/session store, runtime context, follow-up and
  retrieval planning.
- `packages/tools_local`: workspace file, grep, shell, and git tools with a
  workspace jail, dirty-tree write lockout, command risk classification, and
  auto-commit support when writes are enabled. `read_file` accepts optional
  one-based `offset` and bounded `limit` for numbered later-line reads; an
  unpaged read retains its existing output. Shell commands prefer the active
  workspace's `.venv/bin` and `node_modules/.bin`, then use a deterministic
  system `PATH`, without Klaude's launcher virtualenv or Python-path variables.
- `packages/knowledge`: chunking, LanceDB vector storage, SQLite FTS5, atomic
  indexing, refreshable docs sources, skill package imports, hybrid retrieval,
  and the knowledge MCP server.
- `packages/web`: relevance-first search routing, provider clients, Brave Search, SearXNG
  compatibility, web cache, direct/Crawl4AI/trafilatura/Exa fetch cascade,
  bounded same-domain crawler, Hugging Face Hub helpers, and the web MCP server.
- `config/examples`: tracked examples for local app config, provider secrets,
  SearXNG service env, online docs seeds, and preset config profiles.
- `deploy/searxng`: tracked SearXNG config mounted into the local container.
- `scripts`: installer and online-docs helper scripts.
- `tests/unit`: unit coverage for config, tools, memory, runtime context, docs,
  skills, knowledge, search, providers, fetch, CLI commands, and dates.

GitHub Actions runs the locked unit suite on Python 3.11, 3.12, and 3.13, then
runs Ruff and production-source mypy in a separate least-privilege quality job.
A packaging job also builds all five workspace wheels, installs them together
in an isolated temporary virtual environment, imports each public package, and
runs the installed `klaude --help`. Jobs use bounded timeouts and cancel
superseded runs. `make check` mirrors the local unit, lint, and production-type
validation surface; `make package-smoke` runs the separate distribution check.
The root `uv.lock` is tracked release input; update it deliberately whenever
workspace metadata or dependencies change, and keep CI installation frozen.
`.github/workflows/release-candidate.yml` is a non-publishing release gate,
started by manual dispatch or by pushing an alpha release tag (`v*-alpha.*`).
The tag trigger permits verified release preparation through Git push when API
authentication cannot dispatch workflows. It builds all five wheels twice with
one source timestamp, validates their metadata and archive structure, requires
byte-identical output, writes
`SHA256SUMS`, creates GitHub/Sigstore build-provenance attestations with the
official `actions/attest` action, and uploads the verified candidate for 14 days.
Keep release actions pinned to immutable commit SHAs. Publishing to PyPI remains
a separate explicitly authorized operation.

## User-Facing Terms

Use `library` in CLI help, README examples, prompts, and user-facing text for a
named knowledge bucket. Keep `collection` only where compatibility or existing
storage APIs require it.

Preferred public examples:

- `klaude learn URL -l react`
- `klaude query "hooks" -l react`
- `klaude libraries`

Compatibility that must keep working:

- `-c` / `--collection`
- `klaude collections`
- MCP tool parameters named `collection` should still work, but prefer
  `library` where both exist.

## CLI And Chat Commands

The canonical command registry lives in
`apps/cli/src/klaude_cli/main.py`. Never invent Klaude CLI commands, chat slash
commands, aliases, syntax, or examples. Command information shown to the user
must come from this registry or from the Typer command implementation.
Every new chat slash-command handler must add or update its `CHAT_COMMANDS`
entry in the same change, so `/`, `/help`, focused help, and unknown-command
suggestions stay synchronized.

Top-level commands currently include:

- `klaude`: interactive agent session in the current directory; `klaude chat`
  remains a compatibility alias. `klaude chat --no-tui` uses a simple
  line-oriented mode for terminal-native text selection/copying.
- `klaude ask`: one-shot question with tools enabled. Model/runtime failure
  returns exit code 1 after saving available session records and releasing
  resources; a completed answer returns 0. A request to read a
  named local file such as `challenge1.md` exposes `read_file` even when the
  prompt does not say "file". A request to follow that file's instructions
  also exposes permission-gated workspace tools for the same turn; an explicit
  read-only constraint keeps write and shell tools out. An explicit named-file
  read gets one bounded retry if the model answers without reading it.
- `klaude learn`: ingest a URL or local file into a knowledge library.
- `klaude crawl`: same-domain documentation crawl into a refreshable library.
- `klaude docs add/update/list`: manage refreshable docs sources.
- `klaude import-skill`: install a skill ZIP/folder/file and index text files.
- `klaude query`: raw hybrid search over local knowledge, no LLM answer.
- `klaude libraries` and `klaude collections`: list learned libraries.
- `klaude skills`: list installed assistant skills.
- `klaude search`: web search via the configured provider router.
- `klaude code-search`: search programming docs, examples, and debugging refs.
- `klaude huggingface-search/details/readme`: Hugging Face Hub integration.
- `klaude models`: list installed Ollama models and Klaude role assignment.
- `klaude remember`: append a durable fact.
- `klaude auth login/status/logout openai-codex`: manage ChatGPT account
  authentication through the installed official Codex app-server. This is
  separate from `OPENAI_API_KEY` authentication.
- `klaude mcp list/search/info/install/add/import/enable/disable/refresh/remove`
  and `klaude mcp auth login/status/logout`:
  discover active servers through the official public MCP Registry and manage external
  stdio and Streamable HTTP MCP servers. Imports from VS Code/OpenCode start
  disabled and are never executed until the user explicitly enables them.
  Registry search is read-only, bounded, cached for one hour with a seven-day
  stale fallback, and filters to active latest entries. Registry install accepts
  only credential-free HTTPS Streamable HTTP endpoints or exact-version npm/PyPI
  stdio definitions, records their provenance, and saves them disabled without
  connecting, downloading, or executing. Registry metadata is not a security
  endorsement; enabling remains a separate explicit trust boundary.
  `klaude mcp add NAME` provides an interactive transport/endpoint wizard;
  explicit flags remain available for scripts.
  `klaude mcp secret VARIABLE` collects a masked value into private
  `config/.env`; configurations retain only environment references.
  Remote OAuth uses the official SDK's protected-resource/authorization-server
  discovery, PKCE, state validation, dynamic registration or an explicitly
  configured HTTPS Client ID Metadata Document, and automatic refresh. Owner-only
  token and issued-client files live under `.klaude/data/mcp-auth/`, never in
  configuration, transcript, logs, status output, model context, or command
  arguments. Desktop login uses a loopback callback; `--manual` accepts the full
  callback URL through a masked prompt for SSH/headless use. Logout removes the
  local OAuth file and disables the server, but does not claim remote revocation.
- `klaude memory status/on/off/list/add/forget/search`: durable memory and
  session recall controls.
- `klaude sessions`: list recent sessions by effective name and prefix sessions
  with an unexpired running worker lease using the same green `[ACTIVE]` badge.
- `klaude sessions delete SESSION_ID`: delete one session after confirmation.
- `klaude sessions clear`: delete all sessions after confirmation.
- `klaude session-search`: search prior conversation sessions.
- `klaude status`: show configured modes, storage, and permission policies.
- `klaude system-info`: show normalized runtime-context diagnostics.
- `klaude doctor`: verify services, models, config, and data directories.

Chat slash commands currently include:

- `/help`: print the deterministic command reference directly.
- `/init`: start a scoped model turn that inspects the current workspace and
  creates or carefully updates its root `AGENTS.md`. It may use repository read,
  search, workspace-info, and file write/edit tools, but never shell, web, or Git
  mutation tools. It modifies no other file, preserves useful existing guidance,
  and reports honestly when permissions or the dirty-worktree boundary prevent
  writing. It takes no arguments and queues in input order while work is active.
- `/keybinds`: print only keyboard controls directly. Slash commands belong in
  `/help` and the `/` completion popup.
- `/settings [CATEGORY]`: configure categorized Theme, Input Field, Divider, Spinner, Models,
  Providers, Tools, MCPs, Skills, Memory, Permissions, and Runtime controls. Its
  home page is a grouped, aligned overview that shows the live value or a
  concise status for every category. Theme and Spinner parent summaries display
  Default when values match their defaults; selection pages retain actual choices.
  Input Field shows `6-6, border` by default (live min/max and border state); Divider shows
  `ON, default, default` (live visibility and color names, with default colors
  labeled default).
  The Height subpage's Reset to default restores only the 6–6 height range,
  persists both height fields and returns to Input Field with Height selected;
  the border setting is retained.
  Tools shows enabled/registered counts from
  the live tool registry and availability state. Skills shows enabled/installed
  counts from its existing owned background inventory, with loading/unavailable states.
  Memory shows the bounded saved-fact count and automatic-memory flag as
  `1 saved, ON`; its overview worker returns counts without exposing fact text.
  ASSISTANT groups Models, Providers,
  Tools, MCPs, Skills, and Memory in that order. Inside MCPs, the MCP Servers
  heading shows `2 installed, 1 enabled` beside the snapshot age, independently
  of discovered tool counts. The Settings home keeps enabled/total counts.
  MCPs retains `/mcp` and
  `/settings mcp servers`; `/settings mcps` also opens that page.
  APPEARANCE includes Divider (also `/settings divider`): Show divider hides or
  reveals the separator line while retaining speaker/time/session/duration text.
  The Divider page lists Show divider, Line color, Text color, Custom,
  then the built-in `━`, `─`, `━ `, and `─ ` patterns. Presets change only the
  pattern; the footer Reset restores all divider defaults. Built-in rows mark the active pattern
  Current; Custom opens the Line pattern editor and is Current for other patterns.
  Line pattern accepts 1–24 characters and repeats them to fill the separator's
  terminal width. Control characters, blank-only patterns, and leading
  zero-width characters are rejected; spaces inside a visible pattern are kept.
  Editing uses the transient settings composer, never a model/chat turn.
  Line color and Text color are independent; each offers Accent, Normal text,
  the 16 terminal palette colors, Orange, Purple, Pink, and their bright variants.
  Line color also offers Same as text and Same as input field (the
  active theme's composer background). Accent follows the active
  interface theme. Line color begins with Accent, Same as text, and
  Same as input field; regular hues follow in rainbow order, then bright hues
  in the same order, and finally neutral colors and Normal text. Text color
  uses the same hue ordering after its Accent and Normal text choices.
  Line color defaults to Same as input field and restores that value through a
  scoped Reset to default footer action. Text color also uses a scoped Reset to
  default footer action to restore Gray (terminal palette), with no standalone Default choice.
  Existing saved colors remain unchanged.
  Reset restores visible lines, the `━ ` pattern, Same as input field line color,
  and Gray text color.
  These typed controls apply to new output and replayed session history.
  Applied appearance changes automatically replay existing output with the
  current styling, as `/refresh` does, while retaining the open page and live
  work. Theme navigation remains a temporary preview until applied. Saved
  turns and exports are unchanged.
  Divider color and interface/text-theme choices stay open after Enter applies
  a color, with the applied row marked Current. Later theme previews do not move
  that marker; Escape/Back restores the most recently applied theme. Applying
  preserves the current filter, focus, and viewport, including save failures.
  Spinner (also `/settings spinner`) offers the bundled 90-entry cli-spinners
  catalog plus `claude` (· ✢ ✳ ✶ ✻ ✽ at 100 ms) and a custom animation editor.
  Its single selection page lists Custom (opens the editor), then every bundled
  animation, followed by a Reset to default footer action; there is no separate
  catalog page or Default choice. The active animation carries the Current tag.
  The unmodified upstream catalog and Sindre
  Sorhus's MIT license are vendored at commit
  `f0450952b30c960dda79f9d17ef8f1b8684db16c`, including original frame intervals.
  Catalog focus animates a temporary fixed-header preview without saving or
  changing active progress indicators; Enter applies the selected animation.
  Custom frames accept compact Unicode grapheme clusters or comma-separated
  double-quoted JSON strings, retaining intentional spaces and multi-character
  frames. Custom interval defaults to 100 ms and accepts 16–10000 ms. Frames
  are bounded to 256 entries and 80 terminal cells each; terminal control text
  is rejected. Custom edits remain a draft until Apply spinner applies it.
  Spinner frame/interval and Divider line-pattern editors are single-line inputs:
  modified Enter cannot insert a newline, and pasted line breaks become spaces.
  Retained parent panels do not intercept editor typing or Backspace; setup
  editors also do not navigate chat history with Up/Down.
  All TUI work/setup/permission/input indicators share this animation renderer;
  frames pad to a stable width and unsupported encodings fall back to ASCII.
  Faster animations adjust the application's redraw cadence while idle chat
  retains its existing cadence. Reset restores the built-in dots spinner.
  Spinner saves use the existing field-scoped appearance writer and footer
  acknowledgements; failed saves keep the chosen live animation active.
  Enter opens that category, and returning
  with Back or Escape keeps the selector on the same logical summary row even
  when its displayed value changed. Every Settings category and its selection
  subpages use a Prompt Toolkit panel with a fixed breadcrumb/header and
  help/status footer around a scrolling body. The Settings home and Permissions
  MCP server/detail pages have typed actions; other Settings pages adapt their
  existing picker identities and action handlers into typed presentation rows.
  Row IDs, values, and descriptions are separate from rendered labels in the
  panel. Footer controls have one non-selectable blank row above their group,
  including Back/Cancel/Close without a preceding Reset. Explicit control types
  determine spacing and keep exit controls visible through filtering.
  Category headings start with `▪` before an underlined title, without a
  separate rule row, and remain non-selectable. Trailing heading colons are not
  underlined; inline comments and counts
  stay muted. Table headers use uppercase
  words; only the words are underlined, with spaces and alignment padding unstyled.
  Enabled panel toggles color only
  their square with the active theme's primary accent; brackets and value text
  retain normal value styling. Reset and MCP bulk-policy actions use plain
  labels without bracketed controls. Panel navigation controls show `← BACK`,
  `× CLOSE`, or `× CANCEL`; scoped resets show `⏻ RESET TO DEFAULT` and the
  overall reset remains explicitly `⏻ RESET APPEARANCE SETTINGS`. These are presentation
  labels only; stable row IDs and action semantics remain unchanged.
  Reset appearance settings requires a confirmation with Cancel focused by default;
  Escape/Cancel returns to the Settings reset row without saving. The confirmation
  states its existing scope: Theme, Input Field, Divider, and Spinner defaults.
  Memory and Runtime persistence feedback appears only in the fixed footer.
  Model provider labels consistently use OpenAI API and Gemini API; tool-provider
  rows omit the redundant Provider prefix. Skills keeps concise import guidance
  above its inventory; user-facing memory management calls saved facts memories.
  `/settings reset` uses the same confirmation.
  The focused selectable row uses a subtle theme
  background across wrapped lines. A blank, non-interactive row separates the
  Reset and Back/Close controls from page content, without doubling an existing gap.
  Focus does not recolor labels, values, or muted descriptions.
  Permission policy values use semantic green ALLOW, yellow ASK,
  and red DENY text without recoloring the rest of the row. Slash activates
  page-local search; Escape clears search before
  navigating back. The live row below Settings keeps the ordinary ready/activity,
  queue, context, and token counters; panel titles and navigation hints stay in
  the panel. Errors shown in the page footer are omitted from the live status row,
  including its compact error badge. Transient editors retain their own feedback
  while the parent panel is hidden. Transient masked input
  and setup-progress screens retain their specialized composers. The panel
  preserves an unsent composer draft when it closes and leaves the transcript
  in ordinary terminal scrollback.
  Overview memory/MCP metadata comes from an owned eight-second read-only job,
  never synchronous SQLite/config parsing in
  navigation or rendering. It returns only the automatic-memory flag, saved-fact count, and MCP
  enabled/total counts, without connecting to servers or publishing definitions,
  credentials, tools, or conversation content. The summary shows loading,
  unavailable, or aged cached values honestly. Successful snapshots and failed
  attempts are cached/throttled for 30 seconds; failures retain the true age of
  previous successful fields, and independent fields can succeed separately.
  Refresh while open preserves the query and stable selector. Leaving the page,
  memory/MCP changes, session/source changes, and exit cancel or invalidate jobs;
  late results cannot replace newer state. Category detail pages and other saved-setting
  writes still have separate synchronous paths pending responsiveness work.
  Models
  opens the same source, provider, model, mode, and effort selection flow as
  `/model`. The active model's source, cloud provider, and model rows show Current;
  browsing other providers does not change these markers.
  Selecting a model during local or observed remote work queues it
  for the next prompt without changing the running turn's runtime. Cloud
  dependency/auth validation remains cancellable background work and may run
  alongside the turn. The latest accepted selection wins, stays scoped to the
  current session, and is applied in standard mode before subsequent prompts;
  the transcript explicitly reports the pending selection. Idle selection
  retains the mode/effort picker. Conversation history is preserved. Login and
  other setup operations retain their separate active-work restrictions.
  Every Cloud provider remains enterable when signed out. Its model
  page begins with `Login`, which uses the masked API-key composer or the
  official Codex device flow as appropriate; it becomes `Logout` after sign-in,
  and logout requires confirmation. API-platform keys remain separate from
  ChatGPT/Codex account authentication. Codex login/logout and MCP connection
  use owned background setup jobs, leaving the TUI responsive with a transient
  progress/cancel picker and an animated waiting footer. Escape, Ctrl+C, and
  the visible cancel row stop setup; exit also requests resource cleanup.
  Codex cancellation wakes broker waits and requests cancellation of the device
  login before closing that owned app-server. MCP discovery is asynchronous and
  cancellation unwinds its transport and loopback listener. Login has a bounded
  15-minute wait; MCP setup has a five-minute outer deadline and discovery's
  transport deadline. Setup pauses queue consumption and cannot start during
  a local model turn. Login URLs/codes remain in the transient picker, never
  saved transcript/shared session output. MCP enabling commits only after
  successful discovery and rechecks the definition after the network wait.
  Remote OAuth in settings currently uses loopback; the top-level manual CLI
  flow remains available for SSH/headless authorization.
  Tools persists independent
  validation toggles for web-search
  and local-knowledge candidates; turning validation off exposes unvalidated
  leads only and does not bypass transport, provenance, or fetch safety bounds.
  Tools also persists independent availability toggles for web search, URL fetch,
  restricted HTTP endpoint probing, code search, persistent source learning,
  crawl, Hugging Face search/details/README, and the local knowledge library.
  Disabled tools are omitted from model schemas and cannot be reinstated
  by explicit retrieval routing or text-form calls. Tools also persists individual
  on/off settings for every configured web provider, shown in `provider_order`;
  disabled providers are excluded from routing without changing their priority order.
  Tools also has an Activity Updates toggle, enabled by default, for concise
  high-level live stages and completed milestones. Tools navigation, filtering,
  and toggle/reset actions use authoritative in-memory preference snapshots, not
  disk reads. Changes apply to the live tool configuration immediately and save
  through the serialized preferences writer; rapid toggles and reset-then-edit
  preserve their chronological intent. Saving/saved/unconfirmed feedback retains
  picker selection and filtering. Latest-revision acknowledgements merge bounded
  boolean tool/provider/display metadata from the atomic cross-client save; stale
  acknowledgements cannot restore earlier values. Unconfirmed saves keep current
  choices active and retain failed intent for the next explicit save. Availability
  changes never relax transport, permission, or workspace safety boundaries.
  The footer uses the selected Spinner animation (Braille dots by default)
  while active, with progressive states and a
  compact unit-based elapsed value such as `⠋ WORKING 4s`, `⠙ EXPLORING 7s`,
  `⠹ EDITING 11s`, `⠸ RUNNING 16s`, `⠼ LEARNING 18s`, and `⠴ WAITING 20s`.
  Transcript badges retain only completed outcomes such as `[EXPLORED] (9s)`,
  `[EDITED] (30s)`, `[RAN]`, `[LEARNED]`,
  `APPROVED`, `DENIED`, and `CANCELLED`; never persist generic `WORKING` or
  `WAITING` milestones. Updates must come from real model/tool/permission events and
  must never reveal a model's private chain-of-thought or scratchpad text. They
  are persisted with the session and mirrored to clients following via `/resume`.
  `WAITING` is a live footer state when Klaude needs user input, including a
  permission decision, or after a running command has remained without a result
  for five seconds. A command begins as `RUNNING`, becomes `WAITING` only while
  quiet, and completes as `RAN` or `FAILED`. Permission waits complete as
  `APPROVED`, `DENIED`, or `CANCELLED`; never persist `WAITED`.
  Permissions presents one `Current configuration` row above grouped, aligned
  per-tool rows. Entering it opens Custom, Balanced, Cautious, Read Only, and
  Full Access presets. Custom is first and selected whenever the effective map
  does not exactly match a preset. Moving through presets updates a temporary,
  scrollable preview containing every registered tool, grouped with blank lines
  and its exact ask/allow/deny policy; PageUp/PageDown scroll that preview.
  Highlighting `reset to default` previews the configured default policy map
  before Enter applies it.
  Enter applies and persists a preset. Enter or Space on an individual tool row cycles
  ask -> allow -> deny -> ask and persists the custom map; exact preset matches
  are detected automatically. Reset restores configured defaults.
  Permission changes apply to the live gate immediately and save through the
  serialized preferences writer; pending/failed saves never cause the next toggle
  to reread stale disk policy. Saving/saved/unconfirmed feedback preserves selection
  and filtering. Single-tool edits remain field scoped; presets/reset intentionally
  replace/remove the whole override map. Coalescing preserves the chronological
  order of section resets and later child edits and freezes mutable preset input.
  Confirmed saves return bounded valid policy metadata, allowing cross-client
  merged policies to refresh on the UI thread; stale acknowledgements are ignored.
  This acknowledgement never clears or persists process-lifetime `always` grants.
  Explicit permission configuration changes retain their existing grant-reset
  behavior. Persistence failure keeps the explicitly requested live policy active
  for this process with unconfirmed feedback; it does not bypass any hard boundary.
  Hard workspace,
  transport, and command-safety boundaries remain effective under Full Access.
  `delegate_task` appears under Orchestration and defaults to ask. Read Only also
  keeps it at ask because delegation can consume model quota even though the
  child cannot mutate state.
  Memory shows a persistent Automatic Memory toggle and the durable-fact count,
  without a Recent Facts preview; reset restores automatic memory to on. It has
  a visible Manage memories entry for editing or deleting individual facts.
  That entry remains inert with Loading or Unavailable feedback until a sanitized
  inventory is available. Editing uses a private settings composer; deletion
  requires confirmation. Exact fact-ID mutations run on the ordered background
  action lane, with saving/saved/unconfirmed feedback and stale-ID rejection.
  Its page opens immediately with loading or a 30-second cached snapshot. An owned
  eight-second read-only job reads the existing database with a 200ms busy timeout
  and at most 1 MiB of regular, non-symlink memory-file content, without initializing
  or migrating storage. It returns bounded sanitized facts and hides detected
  sensitive facts; hidden counts are explicit. Leaving cancels the read and drops
  late results. Failures retain the snapshot's real age; Back/reopen retries.
  While the toggle value is unknown it remains focusable but inert; Reset can
  explicitly enable memory. Toggle/reset and TUI `/memory on|off` use live intent
  and queue ordered writes on the session action worker, never synchronous reads
  or writes in the key handler. The current process applies that intent immediately
  through an in-memory override. Pending/failed writes cannot be undone by stale
  inventory, overview, or status results. Latest acknowledgements show saved or
  unconfirmed feedback without clearing filtering or moving selection; a confirmed
  save clears the override, while failure keeps the requested value process-local
  and visibly unconfirmed. Settings overview also marks pending/failed persistence.
  Accepted writes survive navigation and use the action lane's bounded queue and
  two-second shutdown drain. Worker acknowledgements remain queued through TUI
  shutdown; a repaint racing with event-loop teardown cannot turn a committed
  write into a reported save failure. Redraw errors while the application is
  running still propagate. Bare `/memory` and line-oriented controls remain
  separate synchronous compatibility paths. Manage memories opens a typed,
  searchable list of up to 200 sanitized facts with stable content IDs. Enter
  opens edit/delete actions; deletion requires a separate confirmation that
  initially focuses Back. Editing uses the settings input composer without
  adding the fact to chat/history. Exact-ID mutations use the same ordered
  action lane and cross-client file lock, reject stale IDs, duplicate or
  sensitive replacements, and report saved/unconfirmed only after acknowledgement.
  Sensitive facts stay hidden; the inventory ceiling is explicit. MCPs and Skills
  use compact typed entry pages with Manage installed first, followed by Search
  catalog and setup/import actions. Manage remains enterable while inventory loads
  or a save is pending. MCPs retains its global Permissions entry after setup actions.
  Both categories use stable action IDs and preserve focus, local filtering, and
  viewport through refresh and Back. Escape clears active filtering first, then
  follows the explicit typed Back/Cancel action where available.
  Search and source resolution are read-only:
  Skills → Search → Results → Skill detail. SkillsMP is the default anonymous
  provider with Repository stars/Recent sorting and bounded pagination (20 per
  page, at most 10 pages). skills.sh is an explicitly selected provisional
  `/api/search` adapter with Installs metadata, relevance ordering and one page;
  its OIDC API is not required. Sources never switch automatically on failure.
  Empty entry shows local SUGGESTIONS rather than fabricated live popularity.
  Search query opens the existing private single-line settings editor; `/`
  filters displayed rows locally. Source and Sort open explicit choice pages;
  applying a choice returns with its control focused, while Back leaves the
  choice unchanged. Search result column headings appear directly above result
  rows in the scrolling body. Refresh results reruns a successful query; Retry
  search appears after a failure. Provider update times and verified source commit
  times display in UTC; a source commit date is not a claim about current
  repository activity. Queries stay out of chat history/shared drafts.
  Source/sort/query changes cancel owned read-only jobs. Network work runs in
  fixed-operation background workers with 3-second connect, 5-second read,
  12-second checked request-chain budget and 15-second outer process deadline, a 1 MB response
  bound, fixed HTTPS origins, no redirects/proxies or ambient credentials.
  Only intentional queries/filters or an explicitly selected public source
  identity are sent; no workspace, conversation, installed-skill or secret data.
  Errors distinguish no matches, network failure, timeout, authentication,
  quota/rate limits, service failure and malformed responses. Up to 64 successful
  metadata pages are cached in process for one hour with seven-day stale fallback
  and real cache-age/error labels. Failures never become successful cache entries.
  Reopening Search shows the retained result's actual age, refreshes expired
  metadata in the background, and drops results beyond the stale fallback limit.
  Request identity and session scope reject late results. Shared PanelState
  retains focus/filter/viewport through refresh and detail/back navigation.
  PageUp/PageDown read wrapped results and long informational detail bodies;
  headings and information remain non-selectable. Explicit Resolve original
  source reads a catalog-supplied GitHub path at an exact verified commit, never
  guesses a path from a skill name. Single-line license/compatibility frontmatter
  is shown with its pinned source; missing or complex unsupported fields remain
  Unknown. Repository publicness/stars are not individual-skill licensing or trust.
  First-party/audit status remains Unknown unless established; no combined score
  is invented. Identity is provider plus item ID, never the displayed name;
  cross-provider grouping requires a verified repository/path and keeps metrics
  separate. Skill catalog details lead with description, repository, license,
  resolution and installation actions; Source details expands the full bounded
  metadata. A resolved detail offers Install skill. Its confirmation initially
  focuses Back and shows the pinned GitHub source and individual-skill license
  state. Only explicit confirmation queues a bounded download of that exact
  commit's skill folder. Git tree/blob identity is verified; symlinks, submodules,
  oversized or unsafe packages are rejected. The existing ordered skill action
  lane indexes the staged folder without executing scripts, granting permissions,
  or replacing an installed skill. Installation records pinned source attribution
  in the manifest and reports success only after the import/index acknowledgement.
  A completed catalog install offers Open installed skill; when inventory is
  still loading, that action waits for the owned inventory result before opening
  the installed detail.
  Catalog entries without a verified skill path cannot offer installation.
  Runtime compatibility is not implied by discovery or installation.
  Skills home shows only the detected-file count beside Import skills. Opening it
  enters a dedicated Import page containing the drop-folder instructions, detected
  filenames, and an explicit Import skills action. Navigation never starts an import.
  The no-files notice stays on that page. Accepted imports retain their background
  lane and feedback; navigation or late acknowledgements do not reopen that page.
  Both Manage lists have a Filter selector with All, Enabled, and Disabled choices.
  This status filter is independent of the page-local text filter and survives
  detail navigation and inventory refresh. Empty inventories offer Search catalog;
  Skills also offers Import skills. Back returns to the actual entry point.
  Skills Manage has Refresh list directly above Check for updates.
  Both Skills and MCPs use Check for update on item details and Check for updates
  on Manage lists; these actions check sources and open review before applying.
  Both Manage page headings show installed and enabled counts from their inventories.
  Manage tables show SKILL/MCP, STATUS, and SUMMARY columns. Summary previews
  show the source type and are bounded for scanning; full bounded descriptions
  and source labels remain
  in item details and in local filtering. Medium-width table controls show
  concise inline descriptions, and table pages reserve their rendered
  fixed-header height.
  Manage actions appear above the installed-item table. Column headings belong
  directly above inventory rows in the scrolling body, never above the page's
  Filter/refresh/update controls. Table headings are non-selectable and follow
  matching inventory rows through local filtering; other navigation actions
  remain outside the table layout.
  Settings feedback uses muted text for progress, green for acknowledged saves
  and successful checks, yellow for warnings/unconfirmed saves, and red for
  errors. Skills and MCP update outcomes carry explicit tones; checking sources
  is muted and all-current results are green. Same-page refreshes retain this
  feedback; navigating to another page clears page-local notices. Skill detail
  feedback uses the same outcome tone as the footer. A save-warning label and
  accompanying error text retain their separate yellow/red styles.
  Skill workers report the outcome tone explicitly: partial imports, existing
  installations, and unconfirmed changes are warnings rather than successes.
  Search failures without usable results and source-resolution failures are
  errors; stale results retained after a failed refresh use warnings.
  Item details label removal as Remove server for MCPs and Delete skill for Skills.
  Both destructive confirmations focus Cancel initially. Installed details lead
  with description, Enabled and update actions, then source/content information
  and removal. MCP details offer Tools & permissions when tools are loaded;
  Back returns to that server detail. General Permissions also links to MCP
  tool permissions and returns to General Permissions when entered from there.
  Setup Back/Escape follows the preceding MCP transport, name, endpoint,
  authentication or catalog-input step and restores entered nonsecret answers.
  Review confirmation actions retain their Update labels. Refresh list
  refreshes the inventory asynchronously. The list shows
  with each skill's name, bounded source label, and description. Selecting a skill
  opens its detail page, where Enter or Space toggles Enabled and Delete opens a
  separate confirmation initially focused on Back. Installed skills are no longer
  directly selectable from the Skills home page. Update checks the original
  GitHub source only for a pinned, verified installation; a newer exact commit
  requires review before the existing ordered import lane replaces that skill.
  Update all checks up to ten eligible sources, previews available revisions,
  and applies confirmed updates one at a time with exact manifest rechecks.
  Unsupported or unverifiable sources are never silently included. A local
  reindex is not described as an upstream update.
  Confirmation binds the exact manifest hash; a changed package requires review
  again. Deletion removes only that skill's owner across its libraries and its
  installed directory, preserving other owners in shared libraries. Imports and
  deletions use one ordered background lane and a cross-client skill lock;
  accepted work survives navigation and exit attempts a two-second drain.
  Drop ZIPs or supported text files directly into `.klaude/data/skills/`.
  While the TUI is running, its ordered skill worker polls up to 1,000 entries
  and waits for two seconds of unchanged metadata before displaying pending
  filenames and a detected count. Detection never imports or indexes files.
  Press Import skills to start explicitly; with no files it reports the exact
  folder to add them to. Installed directories, hidden entries, symlinks, empty
  and oversized files are ignored. Imports execute no skill content and use the
  configured embedding model and an immutable private copy. Successful originals
  move into `skills/.imports/`; failed or changed files remain for explicit retry.
  An existing legacy skills-inbox is also supported by the import action. Imports
  never silently replace installed packages. The watcher starts with the TUI,
  shares its mutation lane and stops on exit; accepted imports use the lane's
  bounded shutdown drain. Folders/custom names remain supported through
  `klaude import-skill`.
  Its optional
  manifest scan runs in an owned bounded worker without importing the knowledge
  indexing stack, so the
  picker opens immediately with a loading row and then refreshes from a short-lived
  cache without blocking input. Scans skip symlinked or oversized manifests,
  return public inventory metadata and per-skill enabled state only, and visibly
  report the 1,000-manifest ceiling. Leaving Skills cancels its job and drops
  late results. Each installed skill has an ON/OFF toggle in its Manage detail page;
  Enter and Space both toggle it. A disabled
  skill remains installed and indexed but its sources are excluded from keyword
  and vector retrieval. Activation changes run on the ordered skill action lane,
  verify the manifest identity, persist in knowledge metadata, and do not affect
  other owners. The Settings parent and Skills heading show enabled/installed counts.
  Runtime controls persist for
  future chats in `chat-preferences.json`: Auto and GPU-preferred leave CPU/GPU placement to Ollama,
  CPU-only sets no GPU layers, and GPU-only persists an explicit maximum-offload
  request (`num_gpu = -1`). Ollama has no
  separate hard no-CPU flag, so unsupported hardware may still reject or fall
  back from that request. CPU threads/context size offer presets and custom
  numeric input. Auto Calibrate
  derives bounded thread and context targets from local CPU, RAM, and VRAM,
  while keeping device placement automatic. Hardware collection is an owned
  eight-second subprocess job; it never collects repository/location context,
  requests a model, or probes network services. Its fixed local probes use CPU
  affinity, root cgroup-v2 limits when present, RAM, dedicated DRM VRAM, and an
  optional two-second `/usr/bin/nvidia-smi` numeric-memory query with a scrubbed
  environment. Only numeric thread/context recommendations cross IPC. The
  calibration row becomes Cancel while pending, retaining stable picker identity,
  selection, filtering, and navigation. Back/Escape/Ctrl+C, another page, runtime
  changes, session switches, and exit cancel or invalidate it; stale results cannot
  replace later choices. Failure keeps existing options. It cannot start during
  active local/observed work. Recommendations are hardware heuristics, not model-fit
  tests or guarantees of Ollama placement; user overrides remain available.
  Runtime preference changes apply immediately and persist through one serialized
  background settings writer, using the existing field-scoped merge, private
  atomic file publication, and cross-client lock. Pending changes coalesce by field;
  older acknowledgements cannot override newer save state. The picker shows saving,
  saved, or save-unconfirmed feedback without resetting selection/filtering.
  A failed save retains unconfirmed intent for the next explicit settings change,
  with newer values winning; it never spins indefinitely. Accepted writes are not
  cancelled by navigation or session changes, and exit attempts to drain them for
  at most two seconds, warning if persistence is unconfirmed. A failure after file
  publication is not treated as rollback. A kernel-blocked filesystem thread cannot
  be forcibly stopped. The preferences editor waits for pending saves to prevent
  racing those accepted writes. Appearance uses a separate writer for its own
  file; Tools and remembered-model selections share the preferences writer.
  Startup and line-oriented chat still use synchronous compatibility saves.
  Runtime also exposes the per-turn
  model/tool ceiling through Safe (12), Balanced (20), Extended (40), and
  custom 1-64 step choices. The selected value applies immediately, persists
  for later chats, and appears in the model-facing live configuration. Reset
  restores `[agent].max_steps` from `config.toml`; the ceiling remains an
  emergency safety boundary with one additional tool-free finalization request.
  `[agent].max_tool_calls` independently caps tool invocations (0 derives two
  calls per step, bounded to 256), and the effective ceiling appears in the
  status budget and model-facing configuration.
  `[agent].max_total_tokens` optionally caps exact input plus output tokens
  (0 keeps the provider/context default, bounded to 2,000,000); missing provider
  usage remains explicitly unknown rather than estimated.
  Runtime also exposes Subagent Workers: Auto uses one worker for Ollama and two
  for cloud providers, while explicit 1-4 choices support stronger hardware or
  stricter quota control. The choice applies immediately, persists in
  `chat-preferences.json`, and reset restores
  `[agent].max_subagent_concurrency` (`0` means Auto). This setting never widens
  the audited concurrent-tool allowlist or any permission boundary.
  Providers securely collects cloud-model keys plus the API keys for Brave,
  Parallel, Tavily, Exa, Firecrawl, Crawl4AI Cloud, and Hugging Face in the
  existing masked-secret composer. The provider list has one status row per
  provider; Enter opens a detail page with a short purpose, its environment
  variable, and explicit Add/Update and Remove actions. It atomically writes
  only the corresponding
  environment assignment to private, gitignored `config/.env` with mode `0600`,
  preserving comments and unrelated values. Secrets never enter transcript,
  sessions, shared drafts, completion, input history, or preferences. Removing
  a model key clears its cached catalog; saving one refreshes discovery in the
  background without blocking picker input. Gemini remains one shared key for
  Gemini chat and Google web search. SearXNG's deployment secret stays in its
  separate `config/searxng.env` configuration.
  Input border defaults on. Pages with supported defaults include a reset action.
  Providers, provider credentials, and MCP server management have no generic
  reset action; their existing explicit credential/server actions define scope.
  Runtime also offers scoped external
  Nano editors for Klaude's `config.toml` and saved runtime preferences; they
  return to the chat after exit and changes apply to the next chat.
- `/vim`: toggle Vim editing controls in the TUI composer; invoke it again to
  return to standard composer controls. The selected mode persists in
  `chat-preferences.json`.
  Composer changes become effective immediately and save asynchronously through
  the same revision-scoped preferences writer; failure leaves the current mode
  active and reports unconfirmed persistence. Runtime turn/subagent reset actions
  use the same writer rather than synchronous special-case writes.
- `/permission`: open the Permissions settings page directly. It takes no
  arguments; permission changes are made and persisted through that page.
  MCP tool permissions are available under `/mcp` → Permissions, directly from
  an installed MCP detail, and through a link in general Permissions. Active
  MCP tools appear under one row per server there. Entering a server shows
  its individual ask/allow/deny policies and scoped Allow all, Ask for each
  tool, and Deny all actions. Server-wide changes save only that server's tool
  policies and preserve unrelated permissions. Back returns to the entry path.
  General permission presets and reset retain their existing policy scope.
- `/mcp`: open the external MCP server settings page directly. Its
  `Delete MCP` action lists configured servers, including disabled servers, and
  requires confirmation with Cancel focused initially. Removal revalidates the
  complete definition in the existing ordered mutation lane, preserves unrelated
  servers and shared environment secrets, and removes dedicated local OAuth
  credentials. Only acknowledged saves publish the updated tool catalog; uncertain
  outcomes retain the existing queued-work hold. Packages are not uninstalled.
  It can search the official MCP Registry asynchronously, inspect supported plans, and save plans
  as disabled definitions. Required registry inputs are collected in-place.
  Search uses the typed Settings panel: query, explicit Official MCP Registry
  source, Registry order or local name sorting, results, and a wrapped detail
  page. Cached results show their actual age in seconds, which advances on
  reopening; results older than the one-hour fresh cache window use warning
  color. Name sorting applies to at most 50 loaded results, not the whole Registry.
  Opening a detail with an exact GitHub repository URL fetches its repository
  star count in an owned, cancellable background job. The result is labeled
  `Repository stars` in detail and, once fetched, in the search row; it is not
  an MCP-specific popularity or trust score. Other repository hosts and unsafe
  or missing URLs do not trigger a lookup. No GitHub request runs in a key handler.
  Empty entry shows local suggested searches; these are prompts, not Registry
  results or popularity/security endorsements. The older composer completion
  path remains a compatibility helper, not the Settings entry point.
  Registry results use MCP Name, Version, and Description columns with fixed
  headings; all fields wrap without display truncation, and narrow terminals
  stack the fields. PageUp/PageDown scroll a focused result's wrapped content
  before moving between results. Filtering includes names, friendly titles,
  versions, and descriptions while preserving stable registry identity.
  Secrets use the masked composer and private `config/.env` references. The same
  settings page can add custom Streamable HTTP or stdio servers, import VS Code,
  OpenCode, or standard MCP JSON, and review then connect/enable a saved server.
  Custom and Registry setup show a final review before saving; Back restores
  previous nonsecret answers, and secret values appear only as masked presence.
  The review starts with Back focused. After a successful save, the result page
  confirms the server is disabled and links to its installed detail, including
  while a fresh inventory loads. A failed save never shows that success page.
  Settings and registry-detail navigation read configured names/status through an
  owned eight-second read-only inventory job, not synchronous registry loads.
  It parses at most 16 MB of regular, non-symlink configuration and previews at
  most 1,000 definitions, using the existing server validator. Only names,
  enabled/transport/OAuth flags, and tool counts cross IPC; endpoints, command
  arguments, environment/header values, credentials and schemas stay private.
  Configured server rows show the same boolean ON/OFF switch as other Settings
  toggles; Space and Enter use the existing server change or review flow.
  Successful snapshots cache for 30 seconds with visible real age. Read failures
  retain that age and use neutral feedback; Back/reopen retries. Leaving cancels
  reads and drops stale session/path/job results. Filter and logical selection
  survive completion. Registry install choices remain focusable but inert until
  the configured-name inventory is known and complete; a truncated preview gives
  a CLI hint. Snapshot metadata is not authorization or a substitute for live
  mutation preflight. Successful add/import/install/reload invalidates the cache.
  Selecting a cached disabled server with no discovered tools starts a cancellable
  eight-second definition-review job instead of synchronously reading the registry.
  The confirmation binds an opaque SHA-256 identity of the complete effective
  definition. It shows only an HTTP origin or a private-stdio hint and points to
  the config for full review, keeping URL path/query and command arguments private.
  Enable re-reads the definition off the UI thread and rejects any changed identity
  before discovery/OAuth, then retains its existing post-discovery identity check
  and registry CAS publication. Cancellation/session/path/job changes discard late
  review results. Registry reads themselves use no-follow, nonblocking descriptors,
  reject non-regular files, and enforce the byte bound during reading.
  After discovery, the cancellable setup task creates a private immutable schema
  snapshot and hands a fixed enable request to the same ordered mutation lane
  used by cached toggles. Setup then finishes without waiting on filesystem I/O;
  its transcript says discovery completed/save pending, never enabled success.
  Definition revalidation, CAS save, and replacement-tool preparation run in
  the lane. Leaving/cancelling the setup UI cannot roll back an accepted save;
  its actual acknowledgement settles later. A failed save never reports enable
  success; a completed save with failed catalog preparation reports saved
  configuration but retains the
  old live tools and asks for reload/restart. Prepared tools publish without I/O
  only in the originating session/config scope, preserving local tools and
  explicit permission overrides. Reload also prepares before replacing tools.
  Cached/discovered-server toggles use a fixed serialized daemon mutation lane
  with at most 16 accepted active/pending operations, shared with discovered-server
  enable publication. Navigation snapshots carry opaque complete-definition
  identities; the worker revalidates before CAS save
  and prepares the catalog from a fresh merged snapshot without connecting.
  The TUI accepts one toggle at a time, preventing duplicate stale-snapshot flips.
  Unknown/old metadata triggers asynchronous refresh rather than a UI registry
  read. Accepted writes are not cancelled by leaving the picker. Eight seconds
  without acknowledgement visibly reports pending/outcome-unknown; late results
  still settle the original request. Exit waits at most two seconds for this lane
  and warns if completion remains unconfirmed. Queued model work waits for the
  acknowledgement and stays paused after uncertain persistence, failed catalog
  preparation, or a stale-scope saved result until verified publication/reload.
  MCPs Manage separates Refresh list (metadata-only inventory refresh) from
  Refresh tools (the existing reload operation), directly above Check for updates.
  Refresh list does not connect or queue a tool reload; either action retains
  the selected row and filters through acknowledgement.
  It runs a fixed
  read-only operation on the same lane. It prepares tools without connecting,
  then verifies the complete configuration still matches its read snapshot before
  acknowledgement. Successful current reload clears the queue hold and prior
  lane uncertainty; failed/stale reload retains old tools and any existing hold.
  Refresh tools does not rewrite configuration or toggle a server. Ack refresh preserves
  the currently highlighted logical row, not a stale request's former selection.
  MCPs settings has Manage installed and Permissions. Manage opens a searchable
  list with each server's name, bounded Registry identity or local source label,
  and bounded description;
  selecting a server opens Enabled, Tools & permissions when available,
  Check for update, and Remove server controls. Cached tool counts do not imply
  a live connection.
  Remove server keeps its
  exact-definition confirmation and ordered mutation. Update is available for
  official Registry stdio packages only when a fresh Registry plan changes one
  exact npm/PyPI package version and keeps every other argument. It requires
  review, exact-definition recheck, and an ordered save that disables the server
  and clears cached tools until separately enabled. Update all checks at most ten
  eligible servers, previews the available changes, then saves them sequentially.
  Unsupported, changed, or unverifiable sources are not silently updated. Reload
  is not described as an upstream version update.
  Successful current acknowledgements publish tools and retain the logical row;
  late results never reopen an unrelated picker. Registry install plans requiring
  no secret input submit private immutable definitions to a fixed disabled-add
  operation on that lane. It validates and rejects duplicates before saving,
  strips discovered tools, forces disabled state, and retains provenance.
  Only acknowledgement reports install success; no package download, execution,
  transport connection, or implicit enable occurs. Custom stdio, unauthenticated
  HTTP, and OAuth definitions now use the same disabled-add operation.
  Import uses a fixed lane operation that reads the explicitly entered local
  file off-thread with no-follow/nonblocking descriptors, regular-file checks,
  and a 4 MB bound enforced during reading. Missing shapes, malformed entries,
  invalid definitions, or any existing-name duplicate reject the entire batch
  before save. Valid imports atomically merge with CAS, force every imported
  server disabled, discard cached tools, and report their count only after
  acknowledgement. No transport/package execution occurs. Import paths and
  contents never enter mutation reprs or feedback. Bearer-token custom setup
  and secret-bearing install publication still use synchronous local I/O and
  cannot overlap a pending lane operation through settings. The legacy private reload
  helper remains synchronous, but current TUI reload actions use the lane.
  Discovery snapshots are bounded and schema-checked before writing. Registry
  saves enforce the read-byte ceiling against the fully merged encoded payload
  under the existing lock, preventing a successful oversized save from making
  configuration unreadable. A kernel-stalled accepted write remains outcome-unknown
  and may be cut short by process exit; shutdown warns rather than claiming rollback.
  Bearer-token custom setup and secret-bearing installs still need this lane.
  The enable preflight read uses a bounded-file thread, which cannot
  be forcibly stopped if kernel filesystem I/O stalls; it is read-only and late
  results after cancellation cannot initiate discovery.
  Remote custom setup supports no authentication, OAuth, or an environment-backed
  bearer token. New and imported definitions never execute until the separate
  confirmation to enable them. The top-level `klaude mcp` commands remain
  available for scripting and advanced OAuth/headless controls.
- `/plan [on|off]`: toggle planning mode. Planning keeps read-only workspace
  tools and retrieval available while disabling writes and shell execution.
- `/compact`: compact stale model context immediately while retaining visible
  and saved transcript history.
  Manual compaction runs even below the automatic pressure threshold, retains
  the two newest complete user-turn/tool exchanges within the existing budget,
  and recaps older public dialogue locally. Long-message excerpts retain both
  the beginning and ending so late corrections survive. The bounded recap admits
  whole attributed excerpts, reserving the initial request and recent user
  corrections before assistant prose. Repeated passes reuse original excerpts
  without re-summarizing summaries; legacy recaps recover only attributed lines.
  Assistant claims remain attributed and unverified. Tool results and private
  provider state never enter the extractive recap; omitted evidence must be
  re-fetched. Manual compaction may also drop an oversized latest complete exchange,
  preserving its public request in the recap rather than leaving the large result
  in context. Automatic compaction includes tool-call arguments in its budget
  estimate and preserves the current user request. Neither path rewrites saved
  transcript history. Excerpts remain lossy, and budgets use conservative character
  estimates rather than claiming exact provider token counts.
- `/recap`: show a concise local recap of the current session's recent turns.
- `/status`: available immediately even while a local or remote model turn is
  working. Show session ID and effective name, model, reasoning mode and effort,
  workspace, context estimate and approximate remaining context tokens, the
  effective turn limit and reserved finalization, plan mode,
  effective permission-policy counts,
  memory mode, tool count, and applicable repository `AGENTS.md` paths.
  Successfully loaded files are labeled `injected` or `injected (bounded)`;
  detected files with no readable content are labeled honestly rather than
  implying that the model received them. The effective session name is a saved
  assigned/generated name
  when one exists, otherwise the normalized first user input (up to 160
  characters). Capture that fallback synchronously when the first turn starts
  so live `/status` never races the worker's database write. Render status as
  grouped aligned label/value columns, with the session, model/runtime,
  workspace/guidance, and permission/memory/tool sections separated by blank
  lines. The TUI badge renders as `[STATUS]`; line-oriented output prints that
  header. Policy words ALLOW, ASK, and DENY receive semantic colors without
  coloring their counts. The estimated Context value turns yellow from 70%
  usage and red from 90%; its label and Context left row keep normal styling.
  Additional `AGENTS.md` paths use blank-label continuation rows.
  Status never reloads repository guidance or changes the agent's injection
  bookkeeping. Use the latest request's capability snapshot, falling back to
  the last prompt-build snapshot; newly created files are not called injected.
  Before any prompt snapshot exists, report that explicitly. TUI session names
  use the synchronous first-input/rename hint. Automatic memory mode shows
  Loading until its snapshot arrives, or Unavailable after a failed read; it
  never guesses On or Off. An owned eight-second read-only SQLite job starts
  when the TUI opens and refreshes assigned names and memory mode with a 30-second
  cache; it never initializes/migrates storage or reads conversation content.
  Late results are scoped to the originating session and title, and local memory
  changes invalidate pending metadata reads. Line-oriented status retains direct
  session metadata reads but also uses the real guidance snapshot.
  When the active provider is OpenAI Codex, also read the official app-server's
  current non-secret rate-limit buckets and show the five-hour, weekly, and Luna
  Reserve weekly percentages remaining with local reset times when reported.
  Link to `https://chatgpt.com/codex/settings/usage`; never infer missing windows
  or expose credentials when the app-server is unavailable.
  In the TUI, account-limit retrieval runs in an owned eight-second job, never
  in the key handler. Status prints immediately with an explicitly loading or
  aged cached snapshot; completed limits print separately only if the originating
  session is still open on Codex. Failed refreshes preserve the snapshot's true
  age and are throttled for 30 seconds. Login/logout clears cached account limits.
- `/debug_label`: show all temporary visual diagnostics in one place. It prints
  the complete transcript-label vocabulary, grouped into neutral information,
  activity outcomes, input outcomes, warnings/failures, and success. Include
  realistic `INPUT`, `SECRET`, permission, session, workspace, queue, tool
  outcome, interruption, and saved-memory examples through the real renderer,
  plus a real closing-divider sample with `worked for 1m 11s`. When no worker is
  active it also starts a model-free footer preview using the real Braille
  animation, beginning at `1m 11s` and cycling through Working, Exploring,
  Editing, Running, and Waiting. Invoke it again or press Ctrl+C to stop the live
  preview. It takes no arguments and may be removed after styling stabilizes.
- `/memory [on|off]`: show durable memory status and facts, or toggle automatic
  memory generation.
- `/skills`: list installed assistant skills and indexed file counts.
- `/new`: start a fresh session with the current model and workspace, retaining
  saved conversations but clearing the terminal view and scrollback. Clears draft attachments and
  model conversation context.
- `/clear`: erase only the current terminal view and scrollback. Keep the same
  session ID, saved turns, model context, attachments, queue, and active work;
  later messages continue in the same session, and `/resume` can replay saved
  sessions. It takes no arguments and does not wait for the worker to become idle.
- `/rename NAME`: persist a 1–160 character name for the current session. Named
  sessions use that name in `/resume` and Markdown exports.
- `/fork`: copy saved turns to a new session ID and continue with the current
  context; future turns do not modify the original session. Copies a saved name
  with a `(fork)` suffix. Empty chats become a new empty session.
- `/export [PATH]`: export saved session turns, timestamps, and code fences as
  Markdown. Without PATH, create a unique file under the data directory's
  `exports/`. Explicit paths must be inside the agent workspace; existing files
  are never overwritten.
- `/diff`: display staged and unstaged Git patches, plus untracked filenames
  (not their contents). Each section is limited to 100,000 displayed characters
  with an explicit truncation notice. Ignored files remain excluded.
- `/review`: review workspace changes for bugs and regressions with severity
  and file references. The turn exposes only read_file, list_dir, grep,
  workspace_info, git_status, and git_diff; write and shell tools are unavailable,
  even if normal permissions allow them. Tool availability is restored afterward.
  These six commands work in both TUI and line-oriented chat. `/diff` is a live,
  read-only snapshot and may run during active work; finish active and queued
  work before using the other state-dependent actions in the TUI.
- `/resume [SESSION_ID]`: list all saved sessions newest first in a scrollable
  panel using the Settings presentation, with a fixed Sessions header, column
  headings, and help footer. Session names, ages, and IDs are separate typed
  fields; names and IDs wrap on narrow terminals. Slash searches the list;
  Escape clears search first, then cancels. Focus and muted metadata use the
  same styling as Settings. Names derive from the first user turn unless renamed.
  Sessions whose unexpired renewable worker lease is still running prefix the
  name with an `[ACTIVE]` badge. The badge uses a green background and green
  bracket glyphs with dark label text, matching Klaude's compact semantic-label
  treatment. Refresh active badges while the picker remains open and preserve
  the currently selected session as labels change.
  Enter resumes the selected session; Escape or cancel leaves the current
  session unchanged. This picker has no reset action. An explicit ID resumes
  directly. A successful resume clears the terminal view and scrollback before
  replaying the selected session's saved user/assistant turns and transcript,
  then measures the live UI's cursor origin after replay so delayed terminal
  cursor reports cannot reserve the cleared screen and hide the latest messages.
  Older history remains available through ordinary terminal scrolling. Resume
  retains the current model and workspace, and saves new turns under the selected
  ID. Bare `/resume` opens the picker immediately during local or remote work
  without interrupting that work; cancelling the picker leaves the active turn
  and its queue untouched. Selecting a different valid session during a local
  turn requests cooperative cancellation, discards queued items belonging to
  the old session with a visible notice, and switches only after the worker
  reaches its safe completion boundary. Invalid IDs and the already-open session
  do not interrupt the worker. A client only observing a remote worker may detach
  and switch immediately because it owns no model worker state. In line-oriented
  mode, `/resume` prints the list and prompts for an ID when stdin is interactive;
  `/resume SESSION_ID` works with non-interactive stdin too. It never switches
  shared agent state while a local worker is active. `/resume` dispatch also
  remains available while the composer is showing a permission, masked-secret,
  or structured user-input wait; cancelling its picker returns to that prompt.
  Cancellation denies pending permission requests and shuts down an active
  Ollama response socket to wake blocked reads; tools already executing may
  still need to finish before the switch can proceed. Resuming a session from
  another process follows its live model activity and emitted response deltas.
  A renewable SQLite lease with a 60-second expiry permits only one model
  worker per session, while
  every connected client keeps an independent shared draft and pending queue;
  one client's composer must never overwrite another's. Session and turn IDs
  use full random UUID hex values rather than display-truncated identifiers.
  TUI render polling submits immutable snapshots to one coalescing session-I/O
  thread with a separate existing-database connection and a 200 ms SQLite busy
  timeout. It handles lease renewal, public drafts, shared events, stale-worker
  recovery, and resume-picker badges without polling SQLite on the render path.
  Session switches discard pending old snapshots and serialize old-client cleanup
  after in-flight writes; late results cannot update a different session or turn.
  Secret/modal composer values are excluded. Lease-renewal failure requests safe
  interruption, including when no successful renewal is observed for 12 seconds.
  Shutdown requests cleanup and joins for at most two seconds; a kernel-blocked
  filesystem thread cannot be forcibly terminated, and abandoned presence expires.
  This does not yet make session actions, queued-turn starts, or settings writes
  asynchronous; those remain separate responsiveness work.
  An observing client must show the shared progressive activity (`WORKING`,
  `EXPLORING`, `EDITING`, `RUNNING`, `LEARNING`, or `WAITING`) while that remote worker lease
  is active with the same animated Braille indicator even though its own local
  worker flag is false, and return to `★ READY` after the remote lease is
  released or expires. Before every provider request the worker publishes the
  same sanitized `TurnCapabilities` snapshot supplied to that model. An observer
  joining mid-turn receives the latest snapshot atomically with its session
  snapshot; later updates refresh its live `/status` without changing the
  observer's own saved model selection.
- `/model`: open an arrow-key model picker, then an effort picker.
  The TUI Ollama catalog also uses an owned eight-second job (three-second HTTP
  timeout), reading `/api/tags` only without loading/inferencing a model. Show
  the active model and an explicit loading row immediately; refresh preserves
  the user's filter/selection, and Back/Escape discards late results. Successful
  catalogs and failures are cached for 30 seconds. Reset uses that inventory,
  never a synchronous daemon call; if it is unknown, ask the user to retry reset
  after discovery. An uncached local `/model NAME` opens the filtered picker
  rather than blocking or silently switching models.
  Cloud selections and explicit cloud `/model NAME` commands prepare optional
  SDK dependencies and Codex account credentials in an owned fixed-operation
  worker (20-second worker deadline, 25-second outer setup deadline). The live
  runtime is created lazily on the UI thread only after a current readiness
  result; no tokens, SDK clients, or provider response data cross worker IPC.
  API-key providers check dependency/key configuration, not remote key validity;
  the first real chat request may still fail. Escape/Ctrl+C/exit cancel setup.
  Session/model/key changes, remote work, or a superseding modal prevent commit.
  Pending turns pause during setup. Cancellation/failure keeps the old model,
  while cancelling mode/effort restores the exact old runtime and reasoning
  settings without another SDK initialization or credential check.
- `/model NAME`: switch the active chat model, then choose effort while keeping
  chat history. After reasoning selection is confirmed, the TUI queues a scoped
  remembered-model save on the shared preferences writer, not a key-handler disk
  write. The model applies immediately, and settings overview shows saving,
  saved, or unconfirmed feedback without losing selection/filtering. Failed saves
  retain the current runtime and history; the existing writer retains failed
  intent for the next explicit save. Cancellation at either mode or effort restores
  the prior runtime/reasoning settings and queues no remembered-model save.
  Mode/effort-only changes remain session-only; this does not introduce persistence
  for them. A successfully saved selection is reused at the next chat launch and
  saved as a session update so `/resume` and observing clients show the change.
  TUI reasoning completion queues its public session-setting update on a separate
  ordered worker with an independent existing-database connection (200ms busy
  timeout). History and its observer event commit in one SQLite transaction, never
  two independently successful writes. Accepted updates keep their originating
  session/client, survive navigation, and are not coalesced with draft snapshots.
  The lane bounds pending updates to 128 and details to 2,048 characters; rejection
  and unconfirmed publication warn visibly without changing the active runtime.
  Failures are not blindly retried. Exit attempts a two-second drain and warns if
  any update failed or completion is unconfirmed; kernel-blocked threads cannot
  be forcibly stopped. This lane orders its own setting updates, not every model
  event or session action; broader lifecycle ordering remains separate work.
- `/mode [standard|thinking]`: choose whether the active model uses its
  normal response path or its reasoning path.
- `/effort` and `/effort LEVEL`: set `low`, `medium`, or `high` reasoning
  effort only while Thinking mode is active.
- `/queue [TEXT]`: show pending turns or explicitly append one to the queue.
- `/steer TEXT`: prioritize a new instruction and interrupt the active turn at
  the next safe model/tool boundary.
- `/cancel`: interrupt the active turn at the next safe boundary.
- `/start`, `/restart`, and `/stop`: start, restart, or stop the local
  Ollama service after confirmation; these controls do not exit the chat
  session. Starting an already-running service is non-disruptive. When a
  response is active, restart and stop ask
  for confirmation before setting its cancellation flag, then close the active
  model transport and perform the service action. Socket-close errors caused by
  that requested cancellation are interruption details, not saved runtime
  failures. If unprivileged systemctl reports that `sudo` is required, the TUI
  may request the administrator password through the generic masked-secret
  composer. Authenticate with `sudo -S -v`, then run only the fixed allowlisted
  systemctl command through `sudo -n`; never place the secret in argv, the child
  service stdin, environment variables, transcript, sessions, preferences,
  shared drafts, completion, or input history. Clear the composer on submit,
  Escape, Ctrl+C, and exit. The same modal is the foundation for future API-key
  entry, but secret persistence still belongs only in private `config/.env`.
- `/refresh`: clear the terminal view/scrollback and replay its retained transcript
  with current theme/divider styling and terminal width, then redraw the live UI.
  Preserve session/model state, active work, pending inputs, and queued work;
  do not restore from storage or recover output removed by `/clear`. Partial
  streaming text stays live. Ordinary redraws remain incremental.
- `/cd [PATH]`: show or change the agent workspace directory. Relative paths
  resolve from the current agent directory; the process cwd is unchanged.
  Typing `/cd ` uses the ordinary completion box for directories only, with
  the `../` shortcut. Home suggestions appear when typing `~`. Parent, home, absolute, and quoted paths retain
  their typed form; completion never changes the workspace until submission.
- `/pwd`: show the current agent workspace directory.
- `/ls [OPTIONS] [PATH ...]`: run the colorized Linux `ls` command at explicit
  user-selected paths, or in the current workspace when omitted. Flags may come
  before or after paths (`/ls -lsha ~` or `/ls ~ -lsha`); quoted paths and `~`
  expansion are supported. This read-only user command runs without a shell and
  does not change the workspace or widen agent tool permissions.
- `/attach PATH`: attach a file or folder as bounded context for the next
  message. Typing `/attach ` offers paths from the current agent workspace;
  absolute paths are also accepted. Typing `~` offers `~/`, and `~/` searches
  the user's home without converting it to a workspace-relative path. Parent
  directory and trailing-slash path suggestions retain their typed path form.
  Inline `@PATH` mentions work anywhere in a
  TUI message and offer the same suggestions; quote paths containing spaces,
  such as `@"project notes/brief.md"`.
- `/theme [NAME]`: open Theme settings for interface and text/code colors;
  an optional NAME sets persistent TUI chrome independently from content
  colors. The default is Pastelle Azure. Built-ins include Crimson Red, Autumn, Egg Yolk, Hacker
  Green, Neon Synth, and a contiguous rainbow-ordered Pastelle family: Red,
  Orange, Yellow, Lime, Green, Cyan, Azure, Blue, Lavender, Purple, Magenta,
  and Pink. Every Pastelle theme uses the same neutral, non-hued background;
  the picker and `/theme reset` restore the default.
- Theme settings also choose persistent Markdown/code syntax colors. Built-ins
  are VS Code Dark (default), GitHub Dark, Monokai, and Solarized Light; the
  picker reset restores the default. There is no separate `/text-theme` command.
- `/quit`, `/exit`, `/q`: exit the chat session.

All picker modes render their available options inside the input field with a
visible selected row; long lists scroll with the selection. Picker height obeys
the same configured input minimum and maximum as the text composer, padding
short lists to the minimum and scrolling long lists within the maximum.
When a settings action rebuilds its picker, keep the selector on the same
logical row even when that row's displayed value changes. The shared pure
`klaude_cli.pickers.PickerController` owns stable option identity, ranked
filtering, and viewport state; the TUI adapter binds settings names, model
references, session IDs, and registry names separately from displayed labels.
Background refreshes reapply the current filter and preserve the selected
identity and its viewport offset. Clearing a filter restores its prior logical
selection, or a manually selected filtered result. Back/Escape restores cached
parent navigation state; unchanged permission previews retain their scroll
position. When selection is on the first option below a heading or note, the
viewport reveals that preceding context when the configured height permits it.
An empty search shows a non-selectable no-match row: Enter never
automatically activates Back/Cancel, although those rows remain explicitly
selectable and Escape still works. Mouse confirmation requires two clicks on
the same option identity, not merely the same position after a refresh.
Transient setup-job rows containing device codes are not cached.
Settings pickers group related options under visible, non-selectable section
titles; keyboard, typed-option, and mouse selection skip those titles.
Typing in a picker filters and ranks selectable rows by exact, prefix, token,
substring, and conservative fuzzy similarity; Enter chooses the highlighted
closest match, Backspace restores matches dynamically, and Escape still follows
the visible back/cancel action.
Unavailable actions remain gray but can be highlighted with the keyboard or
mouse; pressing Enter or confirming them performs no action and keeps the picker
open. This rule applies consistently to missing provider credentials, empty
model catalogs, unavailable external editors, and unavailable generated choices
such as Custom before a custom permission map exists. Blank spacer, section,
loading, and informational tip rows remain non-selectable. Endpoint-specific OpenAI media, transcription, embedding,
moderation, realtime, and search-only models are excluded from live and cached
chat catalogs.
Cloud model options are sorted case-insensitively by full model name. Local
model options and the `klaude models` listing are grouped by model family, with the
family that has the largest tagged model first and variants largest-first. Model,
effort, theme, settings, and input-height pickers end with `reset to default`
and `cancel`, except settings submenus with a parent end with `back` instead
of a redundant cancel option. Cancelling the effort step of a model change restores the prior
model. Resetting a model selects the configured coder role if installed;
resetting effort selects medium. The picker control cursor tracks the selected
row so Prompt Toolkit does not reset scrolling to row zero. PageUp/PageDown
navigate and Escape cancels. Theme navigation previews colors without saving;
cancel restores the original colors. Text previews use a temporary dedicated,
scrollable pane (PageUp/PageDown scroll the samples while Up/Down select a
theme) that is removed without discarding intervening output.

Interactive chat writes its transcript to ordinary terminal scrollback rather
than taking over the terminal's alternate screen. This lets the terminal handle
wheel scrolling and native drag-to-select without Shift. Every interactive
startup first clears the visible terminal and its scrollback, then reserves one
terminal viewport so the composer begins at the terminal bottom. Once appearance
configuration is available, early system/Git setup messages and the reserved
blank viewport use the active output background; terminal attributes are reset
after printing, including on setup failure. The composer remains a
Prompt Toolkit input below the printed transcript. Alt+Enter inserts a
newline when distinguishable, Ctrl+J is the legacy-terminal newline fallback,
repeated Alt+Up edits queued follow-ups from newest to oldest, and Ctrl+C
interrupts the active response. Ctrl+D exits the chat and discards any unsent
input. Enter saves a queue edit; Alt+Backslash promotes the selected edited
follow-up to the front of the queue and steers the active turn at its next safe
boundary, without losing that follow-up's attachments or leaving a duplicate.
Queued session actions cannot be converted into model steering messages. Empty
text plus Enter deletes that item. Pending inputs render in a compact live strip
headed `⏳ Queued follow-up inputs` immediately above the input field, and
automatic queue consumption pauses during editing.
Permission prompts accept `y`/`yes`, `n`/`no`, or `a`/`always` typed in the
composer and confirmed with Enter. Pressing Enter on an empty permission prompt
allows only that invocation, exactly like `y`; it does not activate process-wide
`always`. Picker prompts also accept a full option or
unique prefix typed into the composer and confirmed with Enter.
The model-facing `request_user_input` tool presents its public question above a
modal composer with bounded options below the still-editable text area. Up/Down
changes the highlighted option without overwriting typed text. Enter submits
the typed custom response when non-empty, otherwise the highlighted option;
Alt+Enter inserts a newline. Escape first clears a non-empty draft, then cancels
when the draft is empty. Requests and answers are persisted and mirrored so a
client following an active resumed session can see and answer the same prompt.
Line-oriented interactive chat accepts an option number or arbitrary text,
while non-interactive clients return an unavailable result instead of blocking.
Direct greetings, transformations, and self-contained code generation omit the
input tool schema when no decision is indicated. Decision-oriented or
tool-using turns retain it; after one answer its schema is removed for the rest
of that turn so a model cannot reopen the same modal repeatedly.
Bracketed clipboard pastes of 1,000 characters or more render as a compact
`[Pasted 1,234 chars]` marker in the composer while retaining the complete text
for submission, history, queued turns, attachments, and the model. Smaller
pastes remain directly visible and editable. Cancellation is cooperative at
the next emitted model/tool event, so an in-flight Ollama HTTP request or tool
call may finish before the steering turn starts. Bracketed multiline paste is
one logical turn. Snapshot commands (`/status`, `/recap`, `/skills`, `/diff`,
and bare `/memory`) run immediately during local or remote work. State-changing
or turn-starting actions that require an idle worker
(including `/plan`, `/compact`, `/init`, `/new`, `/rename`,
`/fork`, `/export`, and `/review`) queue in input order instead of being rejected;
a picker pauses later queued input until it is completed or cancelled. `/resume`
is the exception described above: its picker is always available, and selecting
a different session safely interrupts local work before switching. Up/down
navigate input history, Tab completes slash commands,
and the live status line shows activity,
queue depth, model, effort, context-window use, and last input/output token
counts. The TUI renders actual provider fragments as they arrive; it must not
simulate streaming character by character. Cloud requests stream public text
even when tools are available, while structured calls assemble and validate
before execution. Ollama requests with tool schemas still assemble before
structured calls are resolved. Non-interactive stdin retains line-oriented compatibility and plain
output. Line-oriented and one-shot turns keep the renewable session lease alive
with a dedicated five-second heartbeat throughout the synchronous model loop;
TUI lease renewal remains on its asynchronous session-I/O path. The 60-second
expiry still recovers crashed workers instead of leaving an infinite lock.
Line-oriented turns use the same durable start/result/completion events,
partial-output preservation, and failed/interrupted finalization as TUI turns.
If a process disappears before
finalization, the first client observing its expired lease performs one
transactional recovery under `BEGIN IMMEDIATE`: public partial output is
promoted to the durable transcript when no assistant turn was already saved,
one interruption system turn and recovered `turn_done` event are recorded, and
only the expired owner lease is cleared. Concurrent observers cannot duplicate
recovery. Recovery never invents tool results or completed activity labels; a
start-only tool audit remains start-only. If cancellation or a provider failure
interrupts a text stream while its unpublished suffix might be text-form tool
markup, keep only the already-safe prose prefix in model history. Never feed a
half-written tool tag into the next request as assistant prose. An
interrupted turn retains its last user objective for an explicit
`continue`/`resume`/`finish` follow-up, including after restoring a saved session.
The model-facing recovery note says completed tool audits are not tool-result
evidence and that needed sources must be checked again. A new unrelated request
does not inherit that objective. A short request to try or compare the previously
discussed sources inherits only safe built-in retrieval capabilities such as
web search and local knowledge; it cannot inherit write, shell, or arbitrary
MCP tools from assistant prose. Research tools also save bounded typed receipts
separate from audit outcomes: query/library or a public fetch URL/source ID,
status, and counts, never an arbitrary full result. Successful local-knowledge
and URL-fetch results may additionally retain up to three sanitized, query-relevant
public-source excerpts of 1,200 characters each, with capture time, hash, source
and offset. Local file contents and arbitrary MCP bodies are not retained this
way. Recovery treats these as partial historical, untrusted source text; current
claims and missing details still require refetching. Recovery context is bounded
to 8,000 characters; an audit alone never reconstructs missing evidence.
When asked which sources were actually used for an answer, Klaude answers from
executed result records, including saved audits after
resume and completed bounded research receipts from older line-oriented
sessions. A bounded in-memory index of the last 128 answers supports explicit
older-answer references across compaction and model switches and is rebuilt from
saved turns on restore. Ambiguous or missing references are reported honestly;
the index cannot recover unsaved execution records. Source-use questions remain
distinct from questions about available capabilities. Line-oriented chat saves
the same bounded start/result audits
to session turns as the TUI. An audit or receipt confirms execution, not the
tool's full result or the answer's specific evidence. A question about which
sources could be used remains a capability question. In the TUI,
`/help` category names are underlined, and each user or
assistant message has a full-width divider (gray by default) containing the speaker
name and local date/time. Each session starts with a `Session: <id>` divider
after the logo and intro; the composer is labeled `you`, and each turn closes
the actual user message with its `you` divider and the streamed assistant output
with its Klaude divider; the
closing Klaude divider includes a compact unit-based duration such as
`worked for 11s`, `worked for 1m 11s`, or `worked for 1h 01m 11s`.
The intro displays the current agent workspace path. `/cd` updates that path,
the workspace jail, repository context, and the next system-prompt runtime
context; it validates that the target exists and is a directory.

Leading bracketed transcript labels render as compact semantic badges without
changing their copyable text width. Informational labels such as `status`,
`appearance`, and `runtime` use neutral gray; `warning` uses amber; `failed` and
`error` use red; and `success` plus saved-memory notices use green. Label words
are uppercase and use the same foreground as the footer version badge. The
bracket glyphs use the badge background as their foreground so they act as
one-cell visual padding, while text after the label keeps the normal transcript
color.
High-level completed activity labels (`explored`, `edited`, and `ran`) use the
neutral informational badge treatment. Permission outcomes use `APPROVED`,
`DENIED`, or `CANCELLED`, never `WAITED`. They summarize only observable actions
and their public arguments; they never contain hidden model reasoning. Failed
tool milestones use the existing red `FAILED` badge.
MCP documentation/query/read operations complete as `EXPLORED`; other MCP
operations complete as `RAN`, with failures retaining `FAILED`.
Consecutive built-in file edits show grouped file counts, added/removed line
totals, and bounded line-numbered patch previews with filename-based syntax
colors. Counts describe the operations in the group (repeated edits accumulate).
Capture edit metadata before auto-commit clears the working-tree diff. Persist
and mirror these summaries for resume and export; omit patch metadata from model
context. No-op edits show `UNCHANGED`, commits show `COMMITTED`, and unsuccessful
shell exit codes show `FAILED`. Completed activity rows include whole-turn
elapsed time, for example `[EDITED] (30s) 3 files (+53 -0)`. The live footer
uses the theme's original static status styling and animates only its Braille
frame while a local or remote worker is active; printed history is static. The elapsed clock starts once per
turn and is shared through session live state so `/resume` observers do not
restart it. Generic `WORKING` disappears without becoming `WORKED`. Patch
previews cover write_file/edit_file; shell-driven edits are reported as command
execution.
Mechanical fenced-code validation applies only when the user explicitly asks
for a standalone code artifact in the answer. Language names, filenames,
attachments, reviews, explanations, and workspace edits do not turn prose into
a code-only response; rejected repair candidates never remain in model history.
The keybind footer omits the default Standard composer label; it shows a `Vim
composer` prefix only while Vim mode is enabled.

Typing `/` at the beginning of the input must immediately offer every registered
chat slash command with its registry description. Keep completion sourced from
`CHAT_COMMANDS`; do not maintain a second command-name list.
While the completion popup is open, Up/Down navigate suggestions instead of
input history; history navigation resumes when the popup is closed.
Escape closes the completion popup without altering the current input.
An exact slash-command match stays visible after its final character is typed.
Completion rows change only the text color of characters matching the typed
command or path prefix. Unmatched characters use the muted status-row text
color; when no path fragment is typed, the entire unselected `/attach` or `@`
candidate uses that muted color. Matched characters get no separate background,
font weight, or underline. The shared command, `/attach`, and `@`
completion popup uses a background slightly lighter than the composer; its
selected row and metadata are slightly lighter than the popup.
The currently selected suggestion displays its entire candidate text using the
normal composer input text color; it does not recolor the composer text itself.
Inline attachment completion stays anchored at its original `@` position while
typing or navigating suggestions, including quoted paths and wrapped input.
Enter accepts the highlighted completion and executes the command in one press;
Tab completes without executing so users can add arguments.
After a command executes, clear its composer text and completion state so an
exact-match suggestion cannot remain visible over an empty or completed input.
Left and Right move continuously across logical newline boundaries: Left at the
start of a later line lands at the end of the previous line, and Right at the
end of an earlier line lands at the start of the next line.
Mouse capture is enabled only for clickable completion and picker menus; outside
those menus, terminal scrolling and native dragging select and copy transcript
text without requiring Shift. On Termux, Klaude disables mouse capture even for
menus so Android swipe scrolling remains native; use keyboard navigation there.

Modified Enter combinations support both Kitty CSI-u and xterm modifyOtherKeys
escape sequences. The TUI enables both protocols on entry and must restore both
in a `finally` path on exit. Ctrl+J inserts a newline as a compatibility fallback.
A legacy terminal may collapse modified Enter into ordinary Enter before Klaude
receives it, which cannot be disambiguated in the application; `/steer TEXT`
remains the terminal-independent steering fallback.

Interactive appearance is stored in `.klaude/data/appearance.json` (or the
configured data directory) as categorized `theme`, `input_field`, `divider`, and `spinner` objects.
Legacy `output_field` values are ignored because the terminal owns transcript
rendering and scrolling. Chrome and content syntax themes are deliberately
separate settings. Theme, border, height, divider, and appearance resets apply immediately
and automatically repaint retained transcript output using the current styling,
and save asynchronously through their own serialized, field-scoped writer.
Legacy flat-theme migration runs inside the same cross-client file lock, preserving
unrelated values. Theme/Input Field/Divider pages show saving, saved, or save-unconfirmed
feedback in the fixed footer without moving the selector or clearing its filter.
Routine appearance changes add no transcript notices or duplicate saved-status rows.
Only the latest
appearance revision can acknowledge persistence; acknowledgements never replace
live appearance values or affect permission policies. Failed intent remains for
the next explicit save. Navigation does not cancel accepted writes; exit drains
this writer for at most two seconds and warns if unconfirmed, with the same
kernel-blocked-thread limitation as the preferences writer.
`/theme` opens the Theme category. Input height grows between `input_field.min_height`
and `input_field.max_height` (defaults 6 and 6); legacy `height` is accepted as
the minimum. Input Field → Height → Enter min/max accepts two integers with
`1 <= min <= max <= 12`. Invalid input stays in the editor without saving;
invalid persisted ranges fall back to defaults. Escape/Ctrl+C cancels the editor.
Numbered height presets are fixed heights: selecting `8 lines` sets both the
minimum and maximum to 8. `Enter min/max` is the flexible-range option.
The terminal composer must not enter the alternate screen; transcript history
belongs to the terminal's normal scrollback buffer.
Keep the complete transcript in the TUI for the lifetime of a chat session;
never prune older messages or replace them with a truncation marker.
Completed transcript lines must be printed once above the live composer, with
the renderer origin reset below them. `full_screen=False` alone does not retain
history: never put the full transcript in a redrawable TextArea. Only the
unfinished streaming line and temporary theme preview belong in the live output
area. One blank output-background row follows that area before the queue and
composer gaps; it never inherits user-message or code-row background colors. Ordinary redraws, resize, and picker changes must not rewrite printed history.
Explicit `/refresh` clears and reprints the retained view once with current styling.
Applied appearance changes use this same replay; persistence acknowledgements do not replay it.
The live layout aligns its footer at the bottom of available space, placing
unused layout height above the composer. Explicit replay and session-view clears
reuse startup's themed viewport reservation so terminals without cursor-position
reports also keep the footer at the bottom after a short replay.
Printed transcript rows inherit the output background; user and code rows use
their surface background across the full terminal width, including blank cells.
Fill trailing cells without inserting copyable padding or erasing a full row's
last character while terminal wrapping is pending.
The terminal's configured scrollback capacity controls how far back it can scroll.
Explicit `/new` and successful `/resume` switches clear the prior terminal view
and scrollback; this does not delete saved sessions. Cancelled, missing, or blocked
resume requests do not clear anything. Ordinary redraws never clear scrollback.

The last successfully selected chat model is stored separately in
`.klaude/data/chat-preferences.json`. Chat startup uses explicit `--model`
first, then that saved model, then the configured coder role. If the saved model
is no longer installed, startup falls back to the configured coder role. Do not
silently choose a different model for performance reasons.

Every model turn receives a refreshed, machine-generated, secret-free active
configuration block in its system prompt. It identifies the selected model and
backend, reasoning mode and effort, plan mode, allowlisted runtime options,
configured chat providers, enabled and disabled tools, effective permission
counts, web-provider toggle count and routing order, retrieval validation, memory mode, workspace and
  applicable injected `AGENTS.md` paths and bounded-truncation state, plus current appearance,
composer, and activity-update settings. Refresh it from effective in-memory
state before each turn so changes made through `/settings`, `/permission`,
`/model`, `/mode`, and `/plan` are visible to the next model request. Provider
toggles describe configuration, not live reachability. Never include API keys,
secret values, environment contents, or repository-instruction file contents
  in this block; the schemas attached to the current request remain the authority
  for which tools the model may call. A frozen `TurnCapabilities` snapshot is
  rebuilt before every provider request from the global enabled registry, actual
  schemas, effective process-local permission overrides, hard constraints,
  workspace write state, provider/model capabilities, injected instruction paths,
  and the live execution budget. Policy-denied tools are omitted from schemas and
  listed as unavailable instead of being invited to fail. The model prompt,
  `/status`, agent completion event, and shared `turn_done` event serialize this
  same snapshot; permission changes are therefore visible on the next request.
  The permission gate and immutable tool preflight remain the execution authority.
  A provider/model declaring that it does not support tools receives no tool
  schemas even when turn routing selected candidates; the capability snapshot
  reports those candidates as unavailable for that request.

When the user explicitly asks for the complete command list, use the
deterministic command-reference handler and preserve its formatting. When the
user asks about one command, use focused command help from the registry. If a
requested command is unsupported, say so and suggest only close registry matches.
Slash command matching excludes embedded filesystem paths and URL components.
Focused command-help subjects stay in their explanatory clause, so a later
restriction such as "Do not use web search" does not turn workspace inspection
into search-command help. Workspace inspection exposes the bounded read/search
tools even when the user names a path without the literal word "file".

## Config, Data, And Secrets

Klaude settings writers coordinate through `klaude_core.settings_store`:
hold a stable owner-only advisory lock before reading the latest file, apply
only the explicitly edited fields, and publish a unique owner-only temporary
file with file and directory fsync plus atomic replacement. Lock acquisition
waits at most 200 ms before a retryable busy error; lock files must not be
deleted because their inode is the coordination boundary. Appearance and chat
preferences preserve unrelated fields, including nested runtime, permission,
tool, and display settings. Assignments to the same settings field are ordered
by transaction completion; the last explicit assignment wins. Presets/resets
intentionally replace their own scope only. Device mode and GPU override save
together. Provider-key saves serialize the dotenv read/modify/write and preserve
comments and other keys; secrets never enter lock files or diagnostics.
MCP registry instances retain a detached baseline from their last load/save:
unrelated server changes merge, while an edit, removal, or duplicate addition
conflicting with another client's newer definition fails with reload-and-retry.
No stale discovery result can overwrite a replaced server definition. The
scoped Nano editor holds the same advisory lock for its editing lifetime.
Symlinked settings/locks and malformed JSON are rejected on writes rather than
silently discarded. Locks coordinate cooperating Klaude writers, not arbitrary
external editors. Saved-file coordination does not automatically synchronize
other processes' live settings or OAuth refresh state; model catalog caches
use the provider-scoped coordination described below. Broader modal/lifecycle
coordination and simultaneous OAuth refresh remain separate follow-up work.

Read-only model catalog, Codex account-status, MCP Registry search, and skill
inventory jobs use `klaude_cli.background_jobs.OwnedBackgroundJobs`. Replaceable
request IDs reject late results; background supervisors own fixed-operation
worker processes rather than uninterruptible SDK/import threads. Deadlines are
30 seconds for provider/status work, 20 seconds for registry search, and 15
seconds for skills. Cancel/replace/exit signals the owned process group, closes
private pipes, and reaps the worker; normal TUI teardown drains supervisors.
These jobs do not run tools or model turns, grant permissions, consume queued
messages, or replace an unrelated input modal. Credentials travel through
private stdin only, not arguments or inherited provider-key environment values;
worker logs/provider exceptions never enter transcripts or public events.
Each model refresh writes only its provider cache from the worker, guarded by
cache invalidation generations and a locked credential-revision comparison.
Private `config/.env.revisions.json` contains random revisions, never secrets or
secret-derived hashes; replacing/removing even re-adding the same key invalidates
older work. Generations reject delayed Codex results after Klaude logout.
Other clients' provider catalogs are preserved, and empty/failed discovery keeps
the prior catalog. Cloud picker refresh never queries the local Ollama daemon.
Registry cache writes merge only the refreshed query under a lock; optional
cache failure does not discard valid fresh discovery. Background status/model
results affect only their matching open page. Skills and registry searches stop
on Back/Escape; model caches may finish in the background while chat continues.
Abrupt parent death, externally initiated Codex auth changes, and comprehensive
cross-modal latency remain separate lifecycle acceptance work.

Source checkouts keep local editable config in visible `config/` and runtime
data in gitignored `.klaude/data/` by default. Installed packages outside a
source checkout fall back to `~/.config/klaude/` and `~/.local/share/klaude/`.

Source-checkout config:

- `config/config.toml`: live local app configuration, gitignored.
- `config/.env`: live provider/API secrets, gitignored and expected `chmod 600`.
- `config/searxng.env`: narrow SearXNG service secret only, gitignored.
- `config/online-docs.txt`: live docs seed list, gitignored.
- `config/examples/`: tracked examples for all of the above.

Override locations:

- `KLAUDE_CONFIG_DIR`: override config directory.
- `KLAUDE_DATA_DIR`: override data directory.
- `KLAUDE_HOME`: relocate both under one custom home as `config/` and `data/`.
- `KLAUDE_LOG_DIR`: override helper-script log root.

Source-checkout runtime data:

- `.klaude/data/memory.md`: durable facts injected into every system prompt.
- `.klaude/data/sessions.db`: episodic session turns and session search.
- `.klaude/data/knowledge.lance/`: LanceDB tables plus SQLite `fts.db`.
- `.klaude/data/docs-cache/<library>/`: raw learned source cache.
- `.klaude/data/docs-sources/<name>/`: refreshable docs manifests and versions.
- `.klaude/data/skills/<name>/`: installed skill manifests and versions.
- `.klaude/data/runtime-context.json`: volatile cached machine context.
- `.klaude/data/appearance.json`: persistent TUI chrome and text-theme choices.
- `.klaude/data/chat-preferences.json`: last selected interactive chat model and
  persistent interactive runtime overrides (CPU/GPU preference, CPU threads,
  and context size).
- `.klaude/data/webcache.db`: cached search/fetch/Hugging Face results.
- `.klaude/data/web-provider-state.json`: provider health/cooldown state.
- `.klaude/data/entities.sqlite`: compact learned canonical names, aliases,
  entity types, confidence, and successful-resolution history.

Never commit real secrets. Use `config/.env` for provider API keys. Root `.env`
is ignored for legacy compatibility only. Keep container env files narrow:
SearXNG should read only `config/searxng.env`; do not pass all provider API keys
into Docker services that only need one secret. Do not print `.env`,
`searxng.env`, or expanded Docker Compose configs containing values.

The default `brave` provider is keyless website search through the local DDGS
adapter with `backend="brave"`; it is distinct from the optional paid
`brave_api` provider, which uses `BRAVE_SEARCH_API_KEY` and the official Brave
Web Search API. Keyless Brave, generic DDGS, and local SearXNG precede paid
providers by default. Website-backed adapters may still be throttled or changed
externally, so preserve bounded retries and provider fallbacks. Keep
`brave_api` subject to the conservative billing policy.

Use `docker compose config --no-env-resolution --no-interpolate` when validating
Compose shape without exposing secrets.

## Ollama

Klaude talks to Ollama directly over HTTP, using `/api/chat`, `/api/embed`, and
`/api/tags` from `packages/core/src/klaude_core/ollama.py`.

Model tier defaults are in `packages/core/src/klaude_core/config.py`:

- `lite`: `qwen3:4b`, `qwen3:1.7b`, no vision, `nomic-embed-text`.
- `standard`: `gpt-oss:20b`, `qwen3:4b`, `minicpm-v`, `nomic-embed-text`.
- `full`: `qwen3-coder:30b`, `qwen3:4b`, `minicpm-v`, `nomic-embed-text`.

The user can override roles in `config/config.toml` under `[models.override]`.
Klaude request tuning belongs under `[ollama.options]` and is sent with each
`/api/chat` request. Supported options currently parsed by config are
`num_ctx`, `num_thread`, `num_gpu`, `num_predict`, `top_k`, `seed`,
`temperature`, `top_p`, `min_p`, `presence_penalty`, `frequency_penalty`, and
`repeat_penalty`. `[ollama.code_options]` can override these only for code
requests, and `[ollama] code_think` can override general `think` only for code.
This keeps constrained defaults while allowing stronger machines to spend more
context and reasoning without silently switching models. `num_predict` is the
per-response output-token ceiling; Klaude detects an explicit length stop in
nonempty prose or code and may request up to
`[agent] max_code_continuations` (default 2) continuations. It does not
guess at truncation without provider metadata. Continuations remain subject to
the turn governor and request a concise finish without repeating prior text.
Python and GDScript responses are buffered for dependency-free mechanical
validation and may receive up to `[agent] max_code_repairs` (default 2)
diagnostic-driven repairs. Unsupported languages remain single-pass.

Do not put Ollama chat options in `.env`. Do not require Modelfiles for ordinary
tuning. Host-level Ollama daemon settings such as model storage path, keepalive,
parallelism, and daemon context length belong to the Ollama systemd service,
Docker service, or whatever launcher the user chose.

Ollama chat cancellation tracks the connection through HTTPX's trace extension
before response headers arrive, so queued requests and model-loading waits can
be cancelled without waiting for the 600-second transport deadline. Cancellation
shuts down the owned socket and guards response attachment/cleanup by request
identity; a cancelled request cannot reattach or clear a newer request.

Cloud runtime requests are stateless: OpenAI Responses calls set `store=false`
and surface refusal and failed-stream events instead of silently producing an
empty reply. Streaming OpenAI and Codex requests require an explicit completed
terminal event; malformed terminal events and native function-call items fail
closed instead of being treated as successful output. Codex reconciles streamed
tool/reasoning items against the completed response, deduplicates
items by provider ID, and retains completed stream items when the terminal
envelope omits its output array. Both adapters use completed message text when
the terminal convenience field or text deltas are absent; partial tool items
never execute without terminal completion. Both OpenAI Responses adapters request encrypted reasoning
content and retain a strict, non-rendered replay envelope containing only
provider-issued reasoning, compaction, assistant-message, and function-call items. This
preserves opaque reasoning and exact assistant `phase` values across stateless
requests without retaining responses server-side. Provider items suppress
locally reconstructed duplicates; incomplete function-call pairs are still
dropped before the next request. Completed-turn replay envelopes are stored only
in the owner-only session database's private `model_content`; `/resume` restores
them, while transcript text, session search, exports, and shared live events
remain public-content-only. Non-secret response IDs and terminal status are retained as
runtime metadata for diagnostics. Exact Ollama, OpenAI/Codex, OpenRouter, and
Gemini input/output token counts feed the local footer and are mirrored to `/resume`
observers through a bounded, whitelisted completion payload. Missing or malformed
provider usage must not erase an existing estimated context count. Runtime
metadata is not used as server-side continuation
while `store=false`; conversation continuity remains local replay plus the
Responses adapters' encrypted provider state. Cloud context accounting uses discovered provider
model metadata
and never inherits saved Ollama `num_ctx` or GPU/thread tuning; when the Codex
catalog omits a limit, discovery records a conservative 128K fallback. Responses
history emits function calls and outputs only as complete call-ID pairs so a
cancelled or compacted turn cannot send an orphaned protocol item. Responses
runtimes bind a SHA-256-derived, non-identifying `prompt_cache_key` to the full
Klaude session ID. The key remains stable across turns and `/resume`, changes for
`/new` and `/fork`, stays below the provider's 64-character limit, and never
contains the raw session ID, workspace, user input, or credentials. OpenAI API
and Codex requests enable server-side compaction at 75 percent of a known cloud
context window while retaining `store=false`. Provider-emitted encrypted
compaction items are validated, kept private, replayed verbatim, and replace
older dialogue items on later requests; the current generated system and
capability contract is always re-sent. Unknown or small contexts retain Klaude's
local extractive user-boundary compactor. Provider-reported cached and cache-write
input-token counters are whitelisted for observers and shown by `/status`; missing
counters remain absent rather than estimated. Do not request an extended cache
retention policy implicitly: provider defaults preserve the conservative privacy
boundary. Streaming runtimes detach an active transport before closing it;
cancellation is thread-safe, idempotent, and best-effort, so an SDK/HTTP close
failure cannot escape into a TUI key handler or session switch. The cooperative
cancellation flag remains authoritative and is observed at the next safe
model/tool boundary.
OpenAI Codex
account auth is a distinct `openai_codex` backend:
the official Codex app-server owns device-code login, credential persistence,
refresh, logout, and account-aware model discovery; Klaude requests an in-memory
access token from that broker and keeps its own agent/tool loop. Never copy or
log those credentials, hardcode the official OAuth client identity, or merge
this provider with `openai_api`. Gemini 3 models use thinking levels; Gemini 2.5
models use bounded thinking budgets, including budget zero for supported Flash
requests. Provider model discovery must reject blank keys and filter obviously
incompatible audio, image, moderation, realtime, transcription, TTS, and
search-preview models.
OpenRouter is a distinct `openrouter` backend using the OpenAI-compatible
streaming Chat Completions endpoint. Its authenticated live catalog supplies
model IDs, context limits, tool support, and reasoning capabilities. Klaude
executes only its own permission-controlled tools; OpenRouter server tools and
plugins are not enabled. Streamed function-call fragments are validated and
assembled locally, and complete `reasoning_details` sequences are preserved
privately and in order for provider tool continuations without rendering private
reasoning in the transcript.
Malformed OpenRouter function arguments become a private, non-executable
invalid-call marker so the agent can request one corrected native call with the
same tools. A repeated invalid call ends with an explicit error; malformed raw
arguments never enter model history or the public transcript.

OpenRouter requests map a positive configured `num_predict` to `max_tokens`;
unset, invalid, or Ollama-only unlimited values use a bounded 2,048-token default.
This limit includes reasoning tokens where the upstream provider counts them.
Credit-limit errors report the budget remedy without SDK account IDs or response
bodies; other HTTP rejections expose their status rather than the raw body.

## Agent And Tool Routing

Resource constraints such as `Use only the standard library` do not restrict
tool schemas. Explicit named tool-only requests still fail closed for unknown
tool identifiers. Knowledge-ingestion intent keeps actions and source targets
within the same bounded clause; CSV imports, source-code changes, and README
updates do not imply persistent knowledge ingestion. Implementation requests
that also name a file for inspection retain the requested edit and
execution tools; the named-file read shortcut cannot discard those actions.
Explicit read-only requests retain the read-only path.
Workspace implementation requests expose web discovery only when research,
a URL, or current information
is requested; relevant Skills and configured MCP matching remain available.
Preserving current project behavior does not imply external freshness research.
Short continuations such as `Go ahead with that plan` resolve the nearest
substantive user objective before generic lookup hints or earlier continuation
replies. They retain that objective's code request overrides and ordinary
implementation tools when already selected by the objective; they never widen
scope, disabled tools, dirty-worktree rules, or Git mutation permissions.
The footer, per-request capability snapshot, and manual compaction use the
most recent request's actual local context allocation, including code overrides,
scoped to the provider/model. General configuration summaries retain the general
request setting; switching providers/models cannot reuse an old allocation.
When the user explicitly approves a prior plan and mutation tools are actually
callable, request context identifies the transition from temporary review to
implementation. It retains the user's other constraints and does not override
plan mode or permission boundaries.
Workspace-only model requests omit the bundled detailed web-research policy
when no web or MCP schema is callable, retaining universal safety rules and
the global capability inventory. The canonical saved prompt remains intact.
Context compaction estimates natural-language system prose at three characters
per token and Ollama dialogue/tool schemas at two, reserving code output space
without letting the prose estimate erase a continuation's objective or plan.
Whole-response JSON objects containing a known tool name and argument object
are treated as a protocol failure when tools are callable and the response has
not streamed. They never execute as text; one native-call retry is allowed,
then an explicit failure. Embedded examples and tool-free JSON answers remain
ordinary text.
Line-oriented streamed answers suppress repeated progress traces once public
text starts, so progress does not interrupt code or prose mid-line.
Missing-file, directory-as-file, and non-directory lookup errors keep file tools
available and instruct the model to discover actual paths before retrying.
They do not retire the entire reader after two unrelated missing filenames.
The no-progress governor counts unsuccessful batches by model response while
charging every tool call against the existing hard ceiling; three unsuccessful
responses still stop. Permission and other operational failures retain their
bounded retirement rules.
Nonzero local shell exits carry typed failed-status/exit-code metadata and count
as failed validation in the governor. The model receives corrective diagnostics;
an ordinary failing command does not retire the shell tool across repair attempts.
Workspace mutations invalidate earlier local read/validation duplicate guards,
permitting fresh reads and the same test command after an edit. The current
call remains guarded, and stateless retrieval duplicate limits remain effective.

The system prompt is `packages/core/src/klaude_core/prompts/system.md`.

The agent loop in `packages/core/src/klaude_core/agent.py` handles:

- structured Ollama `tool_calls`;
- local-model text tool calls such as
  `<function=web_search> <parameter=query> ... </tool_call>`;
- tool aliases like `search` mapped back to canonical `web_search`;
- provider directives such as `using exa`, `provider: tavily`, or
  `prefer ddgs`;
- deterministic tool exposure for casual turns, command-help requests,
  workspace requests, local knowledge, web lookup, and follow-ups;
- explicit workspace inspection requests receive a bounded host-side
  `workspace_info` preflight before the model answers, so weak local models
  cannot silently substitute a guess for real workspace evidence; the result
  is persisted as an ordinary tool start/result pair. A completed host preflight
  is removed from the provider's callable schemas, and the model consumes the
  attached result rather than repeating the same tool;
- bounded hierarchical repository guidance. Applicable `AGENTS.md` files load
  root-to-leaf into the refreshed system prompt with a combined
  12,000-character budget. Every readable file receives a share and the closest
  file receives remaining capacity first, so a large root guide cannot hide a
  nested override. Repository guidance cannot elevate tool permissions or
  bypass system safety boundaries;
- conversation entity state for resolved/unresolved entities, corrections,
  rejected interpretations, active official domains, claim intent, evidence
  gaps, and topic switches;
- a bounded, model-directed retrieval loop; the host preserves safety,
  provenance, deduplication, and budgets but does not synthesize a first search
  or fallback query.
- explicit retrieval requirements are cumulative: a user request to search and
  fetch must perform both model-directed operations, and a requested source URL
  receives one answer-only compliance retry if omitted.
- a configurable per-turn model/tool step ceiling (`[agent] max_steps`, default
  20 and clamped to 1-64) so malformed or weak-model tool behavior cannot run
  indefinitely. When completed tool work reaches the ceiling, make one final
  tool-free synthesis request. If it cannot produce an answer, report that the
  safety limit was reached, preserve completed work, and tell the user how to
  continue instead of exposing an internal `step budget exhausted` error.
- a provider-independent turn governor in `klaude_core.execution`. It tracks
  model steps, tool calls, safe-boundary wall time, repeated outcomes, and
  consecutive non-progress results. Three failed, skipped, unexecuted, or
  duplicate outcomes across tools stop further tool activity and reserve the
  next model request for a factual tool-free finalization. A successful new
  result resets the non-progress streak. The live snapshot is included in the
  per-request capability block and `/status`; switching sessions clears it.
- normalized Codex usage-limit failures that show the account plan and reset
  time when supplied, link to the official usage page, and suggest waiting or
  selecting another configured provider without printing the raw API payload.
- context-window protection at each user-turn boundary: stale dialogue is
  compacted in whole user-turn units so tool calls never separate from their
  outputs. A bounded extractive recap preserves public user/assistant context;
  tool output, private metadata, and opaque reasoning are excluded. Bounded
  tool names survive with an explicit warning that invocation does not prove
  success; arguments and results are not copied into the recap. The
  canonical system prompt, newest turn, and separate entity state are retained.
  Recap space is reserved before admitting bulky older tool exchanges, so
  follow-ups retain the public task and corrections under context pressure.
  Routing decisions that require recent context, such as a `run them` storage
  follow-up, are captured before compaction and remain effective even when the
  source exchange is reduced to the bounded recap.
- if an Ollama CUDA runner aborts while placement is automatic, retry the
  request once with `num_gpu = 0` and emit only a high-level fallback activity.
  Never override an explicit CPU-only or GPU-only runtime choice.

Complex workspace execution uses `klaude_core.workspace_execution` when the
resolved coding objective is at least 600 characters, writes and shell are
available, and the user has not prohibited execution. Simple requests and
read-only/plan scopes retain their direct path. The bounded state records
observed paths, file-tool edits, typed command exits, validation revisions, and
recent failures; assistant claims cannot establish success. A failing check or
missing implementation/validation receives one completion recovery attempt.
Known incomplete work still emits an error after a governor's factual final
report or the step limit, allowing `ask` to return nonzero while preserving
completed work without another unverified model finalization request.
Passing a recognized check is execution evidence, not proof that every requested
behavior was implemented. Unknown custom commands retain their exact outcomes
without being accepted as passing project checks. A successful wrapper command
alone cannot authorize task completion.
For Python, empty/docstring/import-only modules and simple imported entry
forwarders do not alone establish implementation inspection while other
observed source candidates remain unread. A fully inspected import-only project
still permits new implementation. A numbered page containing only imports does
not count as a complete file; such partial sources remain available in discovery
choices until useful implementation or the complete file is inspected. Read
coverage comes from the executed result, independently of excerpt-cache eviction
or alias resolution. Empty files remain valid complete inspections. This is an exploration guard, not a code
quality or semantic coverage verdict. Next-action guidance remains inspection
until that discovery state permits implementation.

An assembled Ollama response ending without its completion marker returns a
typed failure and no tool calls. When tools remain callable and no public text
was streamed, one fresh action may be retried within the same turn budget and
transport-recovery allowance. Cancellation takes precedence. Completed calls
are retained, partial calls never execute, and a second failure remains an error.
Healthy responses incur no retry; runtime/model choices stay unchanged.
Recovery, protocol, and governor instructions expire when their turn completes,
fails, or is cancelled. Follow-ups retain actual dialogue and complete tool
exchanges without inheriting the previous turn's temporary response format.

Supported local Ollama runtimes use constrained actions for these complex turns
from the start. Discovery allows up to four independent read actions per response.
Once workspace mutation or shell tools are callable, the response grammar limits
execution to one action and normalization rejects oversized batches before
returning any calls. This prevents an appended edit/test rewrite from truncating
the earlier action. Execution binds each tool name to its canonical argument
schema, preventing arguments from a different tool from entering that action.
It avoids repeating the full catalog beside those schemas. Discovery retains
its shared field grammar. Simple native turns keep their existing behavior.
The local action protocol declares a 100-line default when a paged `read_file`
schema is available and the model omits `limit`. The copied local schema carries
this default without changing canonical schemas. Normalized calls record that
actual range; explicit offsets/limits are retained. Native unpaged reads keep
their original output. This bounds ordinary generated-file reads without adding
automatic file reads or raising context allocation; long lines and explicitly
large pages can still exceed the conservative request estimate.
After observed implementation/test inspection, one optional model request
proposes one to four coherent changes, one target file per change. The adapter appends project-check
execution and final review, rather than asking the model to classify application
requirements as implementation or validation. Up to sixteen exact request spans
provide stable navigation references; a long tail remains one span, and the
original objective is retained verbatim. Plan links are advisory. Unlinked spans
remain visible, and review sees every span; linking or editing never proves
semantic coverage. Discovery omits reference excerpts until planning needs them.
Actual
file-tool changes and current passing checks gate implementation/validation step
completion. A failed optional plan does not prevent ordinary tool execution.
During constrained local implementation, write/edit path choices follow the
active plan's files. Canonical arguments and the immutable response scope are
validated before permission or execution. Failed checks and review reopen file
choices for recovery without changing permissions or workspace boundaries.
Once the active file has an actual edit since planning, the next planned
implementation file is also offered. A successful action on it can express
subtask movement through the existing inferred cursor handling, even when the
model left its completion flag false. This neither completes unedited steps
nor proves semantic coverage, and the response scope stays immutable.
A scope-rejected, unexecuted call may be retried if its exact arguments become
valid under a later response scope; completed-call guards remain intact.
Mutation/check responses require the completion flag in their declared grammar;
normalization still accepts older compatible adapters that omit it. Completion
applies after successful execution to the subtask that produced that response.
The local history adapter preserves this flag in previous JSON actions instead
of presenting incomplete protocol examples to the next request.
The same adapter attributes read results to the actual paired read's requested
path/range before presenting batched bodies. It preserves the body and canonical
call/result history, includes failed results, and never guesses a missing pair.
A passing check's inferred cursor movement cannot also consume the following
review step. The cursor follows actual edits and current passing checks. A final
answer can complete review bookkeeping only when actual edit/check prerequisites
are met. Missing scoped edits and stale checks still block completion.
Constrained execution omits the final-answer choice until this existing gate
permits it, avoiding an inference request for an answer the host would reject.
The plan remains turn-local; it is not a durable requirements proof. Simple turns
and other providers keep their existing native path and do not incur this call.

`klaude_core.request_context` selects policy modules from the canonical prompt
using the actual callable schemas. Workspace implementation omits unrelated
configuration/runtime and standalone-answer detail, retaining host boundaries,
applicable repository guidance, and enabled Skill metadata. Coding tasks do not
admit product configuration merely because they mention tools or commands.
Initial compaction uses the selected execution contract without
provider admission; admission happens inside the guarded loop after compaction.
This keeps an initial context constraint on the same clean failure path as a
later oversized result. A separate request
projection bounds long in-turn dialogue in whole assistant/tool exchanges while
retaining the current objective and newest exchange. Canonical session payloads
remain intact. Complex execution also keeps an ephemeral, bounded source store
from successful permission-approved built-in file reads. Each excerpt records
its actual workspace-relative path, line coverage, truncation, execution ID and
filesystem identity. Identity is checked before request reuse; changed, removed,
secret, or escaped paths lose their excerpts. Active-step source has priority,
and source already retained in tool exchanges is not duplicated. Paged
excerpts retain literal code without their display line numbers for edit anchors.
Excerpts appear as attributed untrusted context, never as new tool executions
or restored audit evidence. Normal tool exchanges remain intact while they fit;
snapshots are admitted only when budget pressure would otherwise omit source.
Eager replacement was rejected after both small models stopped implementing
and reread already-visible files. Missing excerpts and omitted read guards
permit fresh reads; fully admitted current excerpts retain duplicate guards.
Read guards track the actual source path, including reads through workspace
symlinks, so an external source change permits an authorized fresh read.
File edits invalidate their target excerpts, except confirmed no-ops and typed
anchor conflicts; shell execution invalidates all excerpts even on failure.
External changes and unclassified shell commands also stale previous checks.
The store holds at most eight excerpts and 32,000 characters, with at most 8,000
characters admitted within the current request's remaining estimated budget.
It is turn-local, does not read files automatically, and adds no model call or
larger context allocation. Simple/read-only turns retain their direct path.
The original complex objective survives short continuations. Exchanges are never
partially truncated by this projection. Under pressure, constrained local
execution may omit the entire latest successful built-in edit exchange rather
than retain its large historical arguments. A host-owned changed marker and
exact call/result pairing establish eligibility; mixed batches, failures, no-ops,
unexecuted edits, reads, shell results and corrective feedback remain protected.
Execution state retains the actual edit status, and a notice states that omitted
arguments are unavailable as current source. Canonical history and completed-edit
duplicate guards remain intact; fresh paged reads can recover needed contents.
Native and other-provider paths retain their latest exchange. Estimated request
admission accounts for policy/task context, schemas, protocol overhead and output
reserve before projecting complete dialogue exchanges and optional excerpts.
Projection reserves its own omission notice before choosing retained exchanges;
an optional older exchange must not cause an avoidable admission failure.
If essential dialogue still cannot fit, a typed host failure stops before the
provider request, reports the constraint, retains actual history, and adds no
fabricated provider usage. The allocation is not raised. This conservative
character estimate is not a tokenizer-level guarantee; oversized essential
results currently require a smaller paged action or explicit narrower task.

After a native protocol failure, other eligible local turns can also use this
declared JSON action response format with reference-free tool schemas. It is separate from
ordinary printed JSON, which is never executed. The adapter normalizes only
responses to its explicit constrained requests; core argument validation,
permissions, workspace restrictions, and budgets still apply. A single object
grammar avoids observed ambiguous-union runner failures. Up to four independent
reads can share one response; edits/checks should remain small coherent actions.
The callable schema snapshot remains fixed while executing a response's batch,
while live permissions, availability controls, and budgets remain effective.
Constrained recovery
initially offers directory/file exploration until observed implementation and
existing test paths have been read, then restores the normal tool choices.
Exploration's response grammar enforces observed path choices and excludes
premature finalization until inspection or an actual permission block. This
does not replace canonical argument validation or workspace boundaries.
Actual callable snapshots describe these temporary restrictions. Empty installed
Skills inventories omit `read_skill`; clients without an input handler omit
`request_user_input`. Ollama streams require a completion marker, and partial
calls are discarded on EOF or stream error. An unfinished workspace call at the
output limit gets one fresh smaller-action retry, never a continuation of unseen
arguments. Cloud Ollama and schemas containing `$ref` retain native recovery.
Exact-edit conflicts allow a fresh target-file read and corrected unique anchor;
wrong outside shell paths remain blocked but do not retire valid in-workspace
validation. Duplicate failures retain their typed recovery cause. Dirty-tree,
secret-path, command-risk, and permission restrictions never receive this retry
exemption. All retries retain the existing governor limits.
Canonical argument errors are typed separately from operational and permission
failures. They do not retire an otherwise valid tool; the model must correct its
declared fields and types, and the ordinary no-progress and hard budgets still
bound retries. Recoverable failures do not consume the unrelated tool-retirement
counter. Constrained argument grammars restrict fields to the declared schemas;
individual canonical schemas remain authoritative for required fields and types.

The TUI publishes normalized actual model usage after requests. A failed request
with unavailable counts retains the last known counters with an explicit
previous-request marker; it does not charge the earlier request again or invent
the failed request's usage.

Do not use tools for greetings, thanks, introductions, ordinary casual
conversation, or basic identity questions. Answer identity questions directly as
Klaude, a local-first coding assistant.

Treat explicit prohibitions as constraints, not positive intent. `Do not inspect`,
`without editing`, and `do not modify` must not route inspection or mutation
tools merely because the prohibited verb appears in the request. An explicit
`do not use tools`, `without calling tools`, or `no tools` removes every model
tool schema for that turn. Positive actions in separate clauses remain effective.
`Use only TOOL_NAME` limits that turn's schemas to named callable tools,
including excluding the usual structured-user-input control tool; an unknown
name does not reopen unrelated tools.
Tool-use prohibitions are constraints rather than the subject of a request:
adding `Do not use tools` to a conversational continuation does not cause the
full repository/product guide to replace its compact conversation prompt.
Actual questions about Klaude settings or commands retain product context.

Explicit requests to quote/excerpt at most a specified number of code lines
are enforced across fenced quotations, with an omission notice if needed.
These responses buffer until the quotation constraint has been applied; ordinary
streaming and complete-program generation are unchanged. Partial quotations are
not treated as standalone programs for automatic code validation.

Use tools when they materially improve correctness or perform a requested
action. The model, not a keyword router, decides whether to call an exposed
tool except for the bounded `workspace_info` preflight above. The system prompt requires retrieval for fresh public facts and explicit
lookups, while ordinary conversation and stable explanations should answer
directly. The runtime bounds and deduplicates calls but never fabricates a
search merely because the model did not ask for one.

Self-contained code-generation requests use a compact code prompt with no tool
schemas while retaining bounded durable user/project preferences. Unsupported
languages stream tool-free output. Python and GDScript are buffered until
dependency-free validation succeeds, with safe reasoning/drafting progress and
bounded diagnostic repairs, then persist one completed assistant turn.
Read-only questions about code use the ordinary output budget. A local model
that exhausts its output limit without a visible answer stops with an explicit
error instead of blindly repeating the same request.
Retrieval remains available when the user explicitly requests search, current
documentation, or workspace inspection. Explicit `do not search` language
removes knowledge and web tools for the turn. If Ollama rejects malformed Qwen
tool XML, retry once with tools disabled, then surface any repeated error.

For follow-ups, resolve the subject from the current conversation and preserve
explicit clarifications such as entity type, location, official domain, and
selected meaning. If the user changes the target entity or type, discard
incompatible prior meanings. Never reuse "school" when the clarified target is
"university", and never let an older acronym interpretation steer later queries.
Local discovery/recommendation requests expose read-only web search and fetch
even without literal search terminology; workspace subjects remain separately
routed. Short location replies can inherit safe tools from preceding dialogue.
The per-request search guidance treats explicit lookup requests as instructions
to act, permits stated broad location assumptions, and avoids redundant approval
questions without bypassing the host permission gate.

## Tool Safety And Git Discipline

Diagnostic and execution routing separates inspection from edit/commit intent.
OS disk questions expose `storage_usage`, a metadata-only inspection of root
filesystem capacity and fixed system categories plus the current account's home.
It accepts no model-supplied paths or commands, reads no file contents, follows
no directory symlinks, skips other filesystems, and bounds each category to
8,000 entries and 0.5 seconds with at most 128 pending directory descriptors.
Incomplete totals are labeled lower bounds; other users' homes are excluded.
The tool defaults to ask and appears in Permissions as OS storage usage.
Ordinary shell paths, including glob expansions, remain workspace-scoped.

Each model request receives an immutable capability block derived from its actual
schemas, with reasons for unavailable tools and a separate global-enabled inventory.
Tools omitted only by turn routing are described as enabled but not callable in
that request, never as globally unavailable. A false unavailable claim about a
currently callable web, local-knowledge, file-reading, or named MCP tool receives one bounded correction
attempt before a nonstreamed answer; streamed answers receive an explicit
capability correction. Public news, social-profile, and GitHub discovery route to web retrieval
without incidental documentation-MCP matches; explicit local-library questions
expose `query_knowledge`. Generic MCP word overlap excludes common words.
Required local-retrieval checks distinguish learned/indexed/local documentation
from external library documentation. Context7 library resolution and references
to general documentation do not force an additional local-knowledge call.
The assistant's `query_knowledge` schema exposes one required nonempty `query`
and an optional `library`, with descriptions of local indexed content, returned
passages/source references, automatic library selection, and read-only scope.
Legacy `question` and `collection` arguments normalize before validation and
permission checks, retaining the existing question-first/library-first precedence.
Malformed supplied canonical or legacy fields cannot be hidden by a valid
preferred field; they fail validation before approval or execution.
The canonical tool ID, permission keys, audits, and knowledge MCP API remain
unchanged; alternate names are not added to the production registry.
Routing words and phrases match token boundaries, so `profile` cannot imply
`file` and `runtime` cannot imply `time`; remote social/repository targets do
not implicitly receive workspace tools. Explicit workspace targets retain them.
Web-search result messages carry the successful providers from execution metadata;
an explicit conflicting provider claim receives a host-generated correction.
It records effective ask/allow/deny policies, provider tool/context/effort support,
injected guidance paths, workspace state, hard safety constraints, and remaining
turn budgets. Every turn has one typed scope: `standard`, `plan`, `review`, `init`,
`evaluation`, or `subagent`. Scope allowlists are enforced before provider schemas are built;
plan and review are read-only, evaluation also omits interactive input, and init
may write only the workspace-root `AGENTS.md` even if a model supplies another
path. Plan mode overrides standard and init turns with the stricter plan scope.
`DENY` tools are not exposed as callable schemas. `/status` and durable completion
events use the same sanitized snapshot. Short repair follow-ups retain the previous
request's selected capabilities when they contain no new tool intent. Short
execution follow-ups use preceding fenced commands as disambiguating context.
Explicit continuation of workspace work resolves tools from the prior user
request before assistant summary prose and never infers Git mutation.
Dependent research follow-ups likewise check the nearest user objective before
assistant summaries. A question about whether existing knowledge contains code
snippets is a retrieval question, not a standalone code-generation request.
An explicit positive request to use or test `crawl_site` keeps that exact tool
callable during URL ingestion; when it is unavailable, the selector does not
silently substitute `learn_source`.
Short dependent follow-ups to an explicitly local-library request retain that
local source scope; public web/code search and external MCP tools are not
inferred from the phrase "code snippets". A new unrelated topic ends the scope.
Alternate bare tool XML is detected, never evaluated; one structured-call repair
is permitted before a visible error. Arguments are checked against the built-in
schema subset before preflight and approval. Repeated non-web tool failures stop
the approach; skipped duplicate calls render SKIPPED rather than RAN.

Explicit requests for a subagent, delegation, an independent review, or a second
opinion route `delegate_task` first and tell the model to use it before direct
inspection; ordinary turns do not receive it automatically. Independent tasks
may be batched through `additional_tasks` or sent as separate bounded calls.
The tool defaults to ask and accepts one primary task plus at most two genuinely
independent additional tasks. Children receive only a bounded objective/context
handoff, never the parent transcript. Host-defined
read/research and test/diagnostic roles intersect the current parent-callable tools
with effective user policies: allow and active process grants may pass through,
deny always wins, and unresolved ask policies are omitted rather than prompting
inside a child. The child receives that prepared tool set directly; the parent
intent router must not hide a permitted read tool based on wording in the
short child objective. Children cannot write, run shell, mutate Git, ask the user, remember,
learn, crawl, or delegate. Their successful and failed usage is charged to the
parent governor. Model steps and tool calls have both per-child and aggregate
caps; delegation preserves a parent tool-result slot, and a provider response
containing multiple calls stops at the first exhausted tool boundary. Ctrl+C
and steering use the same host cancellation flag and fan out transport
cancellation to the primary and active child runtimes. Each
built-in provider forks independent mutable stream, usage, and session state for
the child while retaining only the provider configuration or authentication
broker needed to connect. Custom providers that cannot fork fail closed instead
of silently sharing a transport. Sanitized start/finish events and a bounded
public final summary are persisted and mirrored to `/resume`; private reasoning and raw tool
output are never stored as subagent activity. Local Ollama execution remains
single-worker. Cloud providers may run two children concurrently only when every
callable capability is in the audited stateless workspace set (`read_file`,
`list_dir`, `grep`, `workspace_info`, and `current_time`). Fixed model-step,
tool-call, and provider-token shares are reserved before concurrent launch, and
results return in input order even when completion order differs. Web, knowledge,
Git inspection, shell, mutation, and every unknown capability force sequential
execution until their shared-state behavior is explicitly proven safe.

The turn governor normalizes exact input/output usage reported by Ollama,
OpenAI API, OpenAI Codex, and Gemini after every successful provider request.
Subagents have per-child and aggregate reported-token caps; reaching one blocks
subsequent tool execution and reserves a tool-free final report. Finalization
usage is still counted and may exceed the nominal cap because the final report
is an explicit safety reserve. Missing or partial provider counters increment an
unknown-request count and are never treated as zero or replaced with estimates.
Subagent lifecycle metadata exposes only these numeric counters, never tokens or
provider-private payloads.

Every supervised child batch owns a random full-length batch ID and a monotonic
event sequence. A thread-safe dispatcher serializes host callbacks in that exact
order, permits one `subagent_started` followed by one `subagent_finished` per
started task, and drops duplicate or impossible transitions. A task blocked by
cancellation or budget before its worker begins emits `subagent_rejected`
instead of a misleading finished event. Rejected work renders as rejected in
local output, saved transcript, exports, and `/resume`. Batch sequence numbers
are scoped to their batch ID; durable session event IDs remain the total order
across separate delegations.

Tool preflight checks paths and write locks before asking permission, and execution
rechecks mutable conditions. Read-only pipelines are classified component by
component; unknown evaluation/control syntax and output redirection remain risky.
Only stderr redirection to `/dev/null` is accepted as read-only. Shell pipelines
run without login/startup configuration and with pipefail. Dirty user changes
must never be staged, committed, stashed, reset, or cleaned by the model to
unblock execution. The user resolves that state; read-only work can continue.

`a`/`always` grants are kept separately from saved policies for this process only.
Explicit Permissions settings changes/reset clear those temporary grants; saving
settings cannot accidentally make a process grant permanent.

Tool audit records contain an execution ID, phase, executed flag, exit code,
output character count, and outcome; they omit arguments and output content.
These system records stay out of model context. Resume snapshots identify
user_started events without turn_done (excluding an active lease), recover saved
public deltas, and show an interruption notice without rewriting historical rows.
Observers report an expired remote lease. Runtime failures and cancellations
preserve partial public output and replay a corresponding failure/interruption.
This cannot recover deltas never written before an abrupt process kill.

Workspace tools are jailed to the workspace root. `read_file`, `list_dir`,
`grep`, `workspace_info`, `git_status`, and `git_diff` are read-only. Write
tools include `write_file`, `edit_file`, `run_shell` when classified as
non-read-only, and `git_commit`.
If a model omits the leading slash from an otherwise exact workspace path,
file tools resolve it to the same workspace file instead of creating a nested
`home/...` directory. Other outside paths remain blocked by the workspace jail.

`klaude chat` calls `Workspace.ensure_work_branch()` at startup. If the worktree
is clean, Klaude works on a `klaude/<timestamp>` branch and file writes can be
auto-committed. If the worktree is dirty, write tools are disabled and Klaude
must not edit or commit until the user commits or stashes their changes.

`run_shell` classifies commands before execution:

- read-only inspection commands pass the workspace write-lock check, but still
  follow the configured `run_shell` permission policy;
- test/build commands can run when permitted, but require a write-enabled
  workspace because they are not classified as purely read-only;
- workspace-writing commands require write-enabled workspace;
- destructive commands such as `rm`, `rmdir`, `shred`, and `truncate` are
  denied by the tool implementation.

On Linux, model-initiated shell commands run in a fresh fail-closed Landlock
process. Read-only commands can read the workspace; mutating commands can write
only there and to an isolated temporary home. Explicit outside paths and common
destructive nested commands are rejected before execution. Secret files are
denied through file tools and explicit shell paths, sensitive environment
variables are removed, and returned shell/grep output is redacted. Successful
shell mutations are auto-committed under the repository mutation lock; a failed
command that leaves changes disables further writes for safety.

Do not expose file write or shell tools merely because the user asks a tutorial
or framework question. Favor `query_knowledge`, `code_search`, and `web_search`
until the user asks to inspect or modify workspace files.

## Memory And Sessions

Durable memory and episodic session recall are separate:

- `memory.md` stores concise durable facts injected into every chat.
- `sessions.db` stores previous conversation turns for `klaude sessions`,
  `klaude session-search`, `klaude memory search`, and follow-up recall.

The session database uses WAL mode, a busy timeout, process-safe worker leases,
ordered live events, and per-client composer rows. Visible transcript content is
stored separately from attachment-enriched model content so search and exports
do not disclose private attachment text. Durable `memory.md` mutations use an
advisory process lock plus atomic replacement. Ephemeral event replay is bounded;
saved turns remain the canonical transcript.

Save only high-signal preferences, repeated corrections, project decisions,
durable goals, and important external references. Do not save one-off trivia,
temporary debugging details, raw transcripts, secrets, passwords, or API key
values.

When the user explicitly says `remember that ...` with a clear durable fact,
save it. Broad requests such as `remember this` require a concise summary and
confirmation. If the user asks whether they mentioned something before, use
session search rather than claiming no prior-session access.

`sessions delete` and `sessions clear` require confirmation unless `--yes` or
`-y` is passed.

## Runtime Context

Runtime context is privacy-safe, local, volatile machine context collected by
`packages/core/src/klaude_core/runtime_context.py`. It may include working
directory, Git root/branch/dirty state, OS, shell, hardware summary, displays,
disks, local IPs, local time, timezone, and approximate country inferred from
local timezone data. Fastfetch is preferred, Neofetch is fallback-only, and a
native collector is available.

Runtime context is cached in `.klaude/data/runtime-context.json`; users should
not edit that cache to change hardware facts. Change runtime behavior in
`config/config.toml` under `[runtime_context]` and
`[runtime_context.location]`.

Do not recite runtime specs for casual conversation or simple "where am I?"
questions. `workspace_info` should answer only working directory, repository
root, and write-tool status. Mention approximate physical location only when the
user asks about physical location. Network geolocation is off unless explicitly
configured.

## Knowledge And Atomic Indexing

All learned content should pass through the shared indexing service in
`packages/knowledge/src/klaude_knowledge/indexing.py`. Do not create a new
side-channel writer for docs, skills, CLI, MCP, or `learn_text()`.

The storage invariant is versioned, non-destructive replacement:

- old active chunks remain queryable until all replacement chunks are embedded
  and stored successfully;
- staged rows are not returned by search;
- activation swaps `active_sources` atomically for one owner snapshot;
- manifests and cache files are not proof that indexing succeeded;
- deleting old rows is garbage collection, not part of the critical activation
  path;
- interrupted staging operations can be marked failed/recovered.

SQLite metadata tables:

- `source_versions(version_id, library, owner, source, checksum, status,
  chunk_count, operation_id, created_at, activated_at, error)`
- `active_sources(library, owner, source, version_id)`

Owner examples:

- `learn:<source>`
- `docs:<docs-source-name>`
- `skill:<skill-name>`
- `legacy:<source>` for pre-v2 rows

Retrieval must only return chunks whose `version_id` is referenced by
`active_sources`. Legacy per-library LanceDB tables remain compatible until
their sources are replaced.

Hybrid retrieval in `packages/knowledge/src/klaude_knowledge/hybrid.py` does
vector search plus SQLite FTS5, merges with reciprocal-rank fusion, optionally
reranks with FlashRank, then applies confidence thresholds before returning
context. Fusion retains both vector and lexical ranks for matching chunks, and
an enabled reranker's order remains authoritative after thresholding.
Library routing normalizes punctuation-bearing language names such as C#, C++,
and F# to `csharp`, `cpp`, and `fsharp` so short local-library questions can
reach the indexed source.

## Docs, Crawling, And Skills

`klaude learn` fetches or reads one source and stores it under owner
`learn:<source>`. It is idempotent for unchanged content and writes raw cache
files under `docs-cache/<library>/` after successful indexing.

Natural-language chat requests can perform the same persistent action through
the native `learn_source` tool. Expose it only for explicit learn/save/ingest/
index/archive intent, never for ordinary reading or “learn about” questions.
The tool accepts public HTTP(S) sources and rejects credentials embedded in a
URL before permission is requested. It infers a library from the hostname when
the user omits one, indexes one page by default, and uses site scope only when
the user explicitly asks for a documentation set, website crawl, or multiple
pages. Site scope reuses the bounded same-domain crawler and, absent explicit
include patterns, stays within the URL subtree supplied by the user. Persistent
learning defaults to `ask`; approval is distinct from temporary web retrieval.
When an explicit persistence request names a public product, project, skill, or
documentation source without a URL, expose only the bounded discovery path:
web search, URL fetch, persistent source learning, and structured user input.
The model must locate and verify a canonical official URL before learning it;
search snippets are never persisted as source content. A learned skill file is
knowledge text, not an installed or executable third-party package.

`klaude docs add` installs an `llms.txt` source by fetching the index plus
same-domain Markdown/text links. `klaude docs update` refreshes `llms.txt` and
crawled sources. `klaude docs update --online` processes the configured
`config/online-docs.txt`.

Docs sources live under `.klaude/data/docs-sources/<name>/`:

- `manifest.json`
- `CURRENT`
- `versions/<version_id>/`
- `pending-<version_id>.json` while activation is in progress

`klaude crawl` uses the bounded same-domain crawler in `packages/web`. It honors
robots.txt by default, skips binary/media assets, supports sitemap seeding,
include/exclude patterns, max depth/page caps, retry-after handling, randomized
delays, and stores crawl options so docs update can refresh it later.

`klaude import-skill` installs a folder, ZIP, or single file into
`.klaude/data/skills/<name>/`, indexes text-like files only, skips symlinks,
hidden files, binary files, `__MACOSX`, and files above the indexing byte limit.
ZIP extraction rejects unsafe paths and symlink entries, with ceilings of
2,000 entries and 64 MiB expanded content. Re-imports create content-addressed
versions and finalize the manifest only after knowledge indexing succeeds.
At agent startup, the configuration snapshot names enabled installed Skills and
their short descriptions alongside the available tool registry, external MCP
count, and bounded read-only delegation capability. Full Skill instructions are
loaded only when the model calls `read_skill` with an exact installed name.
The tool returns at most 2,000 characters by default, supports bounded offset
reads and supporting files, and never follows symlinks or reads outside that
Skill's current package. Disabled or unreadable Skills are omitted. Skill text
is untrusted guidance and cannot grant permissions or override the user's task.
Current request schemas, not the startup snapshot, determine callable tools.
Explicit requests to use a Skill or any installed guidance require a successful
`read_skill` call before a final answer; the agent gives one model retry if it
tries to answer without that call. A request not to read a Skill removes the
tool schema for that turn. Unknown catalog descriptions must remain Unknown
until the Skill is read. Code review findings must name actual identifiers,
expressions, or behavior in the inspected file, and unsupported issue counts
must not be invented.

## Web Search

The web facade is `packages/web/src/klaude_web/facade.py`. The search router is
`packages/web/src/klaude_web/providers.py`.

Search-query name normalization is centralized in
`packages/core/src/klaude_core/entities.py`. It uses compact stable vocabulary,
the local `entities.sqlite` cache, and RapidFuzz before intent/location/
ambiguity planning. It preserves original and normalized query text plus
correction provenance. Exact short acronyms are not fuzzy-expanded without
strong contextual evidence. Optional `[entities.wikimedia] enabled = true`
uses the public, keyless Wikidata entity-search API only for unresolved probable
names, sends only the minimal name phrase, caches accepted canonical names, and
fails closed to the local path on errors or ambiguity.

Search providers use stable lowercase labels:

- `google`
- `parallel`
- `exa`
- `ddgs`
- `tavily`
- `firecrawl`
- `searxng`

Default provider order in code is:

```toml
["google", "parallel", "exa", "ddgs", "tavily", "firecrawl", "searxng"]
```

Users can override order in `config/config.toml` under `[web.search]` with
`provider_order = [...]`. Unknown names are ignored and missing defaults are
appended. Legacy `[web] provider = "local"` means SearXNG-only compatibility,
`"exa"` means Exa compatibility, and `"quality"`/`"auto"` use the
relevance-first router.

Optional API keys use `PROVIDER_API_KEY` names in `config/.env`:

- `GEMINI_API_KEY` for Google Search Grounding label `google`;
- `PARALLEL_API_KEY`;
- `TAVILY_API_KEY`;
- `EXA_API_KEY`;
- `FIRECRAWL_API_KEY`;
- `CRAWL4AI_API_KEY` for fetch/crawl extraction endpoints;
- `HUGGINGFACE_API_KEY` for Hugging Face Hub, separate from web search.

DDGS is keyless when the optional package is installed. SearXNG is local and
uses `config/searxng.env` for its container secret, not `config/.env`.

Search behavior is relevance-first:

- classify query intent and ambiguity;
- treat broad/category searches as source discovery, returning relevant SERP leads without
  requiring each result to prove a final claim;
- keep exact single-entity lookups on the stricter entity-evidence path;
- apply runtime location as a soft signal only when appropriate;
- use lower thresholds for broad candidate discovery;
- return stable runtime result IDs with promising leads, then let the model
  explicitly select which pages to read with `fetch_url`;
- never automatically fetch every result or a script-selected top result;
- apply stricter final verification after fetched evidence;
- skip unconfigured providers silently during ordinary successful searches;
- show concise attempted-provider failures only when fallback occurs or all
  providers fail;
- do not expose provider-specific internal tool names to the model or user.
- fingerprint attempts by normalized query, provider, and options, and skip repeated
  strategies while detecting identical or near-identical result sets.
- treat provider health as a recoverable circuit breaker: one operational
  failure remains eligible, repeated failures enter a timed cooldown, and stale
  degraded states become probeable again;
- cache only searches that return evidence-bearing results, so outages and
  temporary zero-result responses cannot poison later queries;
- preserve the underlying academic, research, or documentation intent when
  freshness words or years are also present.

Ordinary chat web research is a bounded, model-directed loop in
`packages/core/src/klaude_core/agent.py`: the model chooses concise searches,
inspects leads, selectively fetches pages, assesses the remaining information
gap, and stops when evidence is sufficient. `AgenticSearchState` stores only
observable orchestration data and compact functional gaps, never private
chain-of-thought. The runtime enforces `[web.search.behavior]` limits for total
web actions, search calls, fetch calls, pages per domain, and consecutive
failures; exhaustion disables further web actions and gives the model one
best-effort finishing opportunity with gathered evidence.

Search diagnostics remain structured rather than verbose by default. They include the
query, provider, raw count, post-light-filter count, duplicate count, and categorized
rejection reasons.

CLI/TUI rendering must show provider metadata from structured execution data:

- `-> web_search [google]`
- `-> web_search [exa + searxng]` only when results were genuinely combined;
- failed attempts should show the provider labels that actually ran;
- `none` is a structured metadata label for the no-configured-provider case.

The canonical tool name remains `web_search`. Provider labels must come from
structured metadata, not parsed response text. Never log or display API keys,
headers, tokens, sensitive response metadata, or secret fingerprints outside
safe debug logs.

Tavily and Firecrawl are implemented as search providers only. Tavily Extract,
Crawl, Map, and Research are not exposed as Klaude tools. Firecrawl Scrape,
Crawl, Map, Monitor, Parse, Interact, and Research are not exposed as Klaude
tools. `crawl_site` remains Klaude's own bounded same-domain crawler.

Hugging Face Hub lookup is its own integration, not a default web provider.

## URL Fetching

`fetch_url` should render as `-> fetch_url [provider]` in CLI/TUI output. Fetch
metadata should stay structured so CLI, TUI, logs, MCP responses, and tests can
use it consistently.

Search and page reading are separate model-visible operations. Each `Web`
runtime owns an in-memory source registry: SERP leads receive
`search_result_NNN` IDs and successfully fetched documents receive `src_NNN`
IDs. Canonically equivalent URLs reuse the same source, while the existing
SQLite TTL cache avoids repeat downloads across runtimes. Search-query/provider
provenance is attached to fetched sources when available.

Long fetched pages are reduced to bounded, query-relevant evidence windows
while retaining source identity and the untrusted-content boundary. Do not
blindly keep only the beginning of a page, because decisive API signatures or
claim evidence may occur later in the document.

The untrusted public `fetch_url` boundary accepts only HTTP(S), rejects URL
credentials and local/private/link-local/metadata targets, resolves hostnames
before connecting, and revalidates every redirect. Download bytes, extracted
content, timeouts, redirect counts, and cache TTL are bounded under
`[web.fetch]`. Webpage text remains a lower-authority tool message marked as
untrusted external evidence; instruction-like text inside a page is data, not
an instruction to the agent.

Fetch providers are:

- `cache`: cached fetch result.
- `direct`: direct HTTP for plain text, Markdown, JSON, and XML.
- `crawl4ai`: optional configured Crawl4AI `/md` endpoint.
- `trafilatura`: local Python HTML extraction fallback.
- `exa`: Exa `/contents` when `[web] provider = "exa"` or `auto` fallback uses
  Exa after local extraction fails.

The preferred default cascade is direct text first, then Crawl4AI when
configured, then trafilatura. This is important for files like
`https://react.dev/llms.txt`, which should not go through HTML extraction.

`http_probe` is a metadata-only endpoint diagnostic, not a page-reading or
search fallback. It accepts only HEAD or GET to public HTTP(S) targets on ports
80 and 443, follows the same DNS and redirect safety boundary, ignores ambient
proxy configuration, and exposes no model-controlled headers, credentials,
bodies, cookies, or TLS settings. It returns status, final URL, content type,
declared content length, redirect count, and elapsed time without retaining a
response body. Never invoke `curl`, `wget`, or shell networking automatically
when web tools fail or are disabled; shell networking remains an explicitly
requested action behind the ordinary `run_shell` permission gate.

## MCP Surfaces

`klaude-web-mcp` exposes:

- `web_search`
- `code_search`
- `fetch_url`
- `http_probe`
- `crawl_site`
- `huggingface_search`
- `huggingface_details`
- `huggingface_readme`

`klaude-knowledge-mcp` exposes:

- `learn_url`
- `learn_file`
- `docs_add`
- `docs_update`
- `crawl_site`
- `import_skill`
- `query_knowledge`
- `list_libraries`
- `list_collections`
- `list_skills`
- `docs_list`

Knowledge MCP mutations are disabled unless its process receives
`KLAUDE_MCP_ALLOW_WRITES=1`. Local file and skill-package inputs remain jailed to
`KLAUDE_MCP_WORKSPACE`, or the MCP server working directory when it is unset.

MCP access from Codex, Claude Code, OpenCode, Cline, Roo, or Continue is
separate from native Klaude chat. Adding Klaude MCP servers to another agent
gives that agent Klaude's web/knowledge tools, not Klaude's whole agent loop,
permission model, or conversation state.

Klaude chat is also an MCP client. The official public MCP Registry is the
canonical discovery source; Klaude uses its versioned API rather than scraping
vendor galleries. Search results are bounded, cached privately, sanitized for
terminal display, and filtered to active latest records. Only supported HTTPS
Streamable HTTP and exact-version npm/PyPI stdio plans can be saved, always
disabled and with registry provenance. Discovery/install never implies trust or
launches third-party code; enablement remains explicit. External server definitions live in the
private `.klaude/data/mcp-servers.json` registry and support local stdio or
remote Streamable HTTP. VS Code/OpenCode imports start disabled; explicit enable
performs bounded tool discovery. Cached schemas avoid startup connections,
namespaced tool identifiers prevent collisions, every external tool defaults to
ASK, and enabled connections remain alive for the current Klaude process so
stateful browser tools retain their session. Tokens are accepted only through
environment references (including Bearer headers) and can be collected with the
masked `klaude mcp secret` command into private `config/.env`. Server prompts and
resources are not injected into the model. Tool descriptions and results are
untrusted external content, remain output-bounded, and cannot override system,
permission, workspace, or command-safety policy. OAuth-protected remotes use the
official SDK flow with private per-server token/client storage and automatic
refresh; they never reuse model-provider credentials.

The MCP search composer offers at most eight locally ranked actual registry names.
After a 350ms typing pause, an owned bounded background search updates suggestions;
completion itself reads only memory. Stale results are discarded and leaving the
composer cancels its search. Registry listing is not a trust endorsement.
The popup sits two columns farther right in this composer. New search results
select the first server instead of retaining the loading screen's Back selection.
Arrow keys/Tab select or complete a name;
Enter performs the existing bounded registry search. Queries do not enter shared
drafts or chat-history autosuggestions, and secrets disable completion entirely.

`scripts/compare_mcp_clients.py` is an opt-in synthetic reuse experiment, not a
second production MCP stack. Run it in isolated, non-project uv environments;
it uses only repository-owned local fixtures and synthetic in-memory auth.
`docs/mcp-reuse.md` records measured SDK/FastMCP results and migration validation.
Production uses official MCP SDK v2 through one shared high-level client factory
for discovery and persistent connections. Handshake mode remains `legacy` to
preserve existing session behavior. Web and knowledge servers use SDK `MCPServer`.
Discovery follows at most 16 pages and retains at most 128 tools; repeated cursors
fail visibly. Text and structured tool results share the existing bounded output
budget; structured-only results remain available to the agent. Disabled servers cannot
execute tools; explicit setup discovery
remains available before enablement. A closed connection fails its current call
without replay and is retired; a later request opens a fresh connection.
The existing per-server worker bridge remains for the synchronous agent runtime.
OAuth callbacks retain `iss` for SDK issuer checks and reject duplicate security
parameters. Saved credentials are bound to the exact server URL; legacy records
without matching resource discovery require login again. Expired stored tokens
restore their remaining lifetime before the first request, with a narrow SDK 2.2
initialization workaround. Credential reads reject symlinks, non-regular files
and oversized content. The comparison script's synthetic refresh test is separate
from production storage/refresh regression tests in `tests/unit/test_mcp_v2.py`.

## Current Boundaries

- There is no native VS Code extension or `klaude serve` IDE backend yet.
- The CLI/TUI is the full agent surface today.
- Klaude's built-in MCP servers expose only web and knowledge capabilities;
  external MCP client tools are individually permission-gated.
- Optional hosted providers may send queries/URLs to third-party services.
- Web search and URL fetch evidence are temporary; they are not written to
  memory or knowledge unless a learn/docs/crawl/import command explicitly does
  so.
- Runtime context is local and volatile; it is not durable memory.

## Development Commands

Use focused checks after relevant changes:

- `uv run pytest tests/unit -q`
- `uv run ruff check .`
- `uv run python -m py_compile <changed-python-files>`
- `bash -n scripts/install.sh`

Live behavioral model comparisons are deliberately separate from deterministic
CI. Run `uv run python scripts/evaluate_agent_behavior.py --model MODEL --yes`
to evaluate direct response, workspace inspection, contextual diagnostics, and
synthetic learned-document grounding. Additional `conversation-continuation` and
network-opt-in `local-search-followup` scenarios exercise seeded conversational
context. Optional answer/query term groups require at least one alternative in
each group; query expectations must match one actual executed web-search query.
Unrelated answers and wrong-city searches fail with bounded expectation categories.
Raw queries remain local to scoring and are not included in reports. These lexical
checks are not a complete semantic guarantee; inspect live answers and executed
queries when assessing whether a model retained the intended task.
Each model/scenario pair runs read-only in
an isolated child process with a hard timeout and a private temporary Klaude data
directory. Model selection explicitly applies Standard mode, matching the
ordinary interactive default rather than inheriting the startup model's reasoning
settings. Real memory, sessions, and learned libraries are neither read nor
modified. Only the public model-capability cache is copied into that directory so
transient catalog discovery does not invalidate a configured model. The learned
document scenario seeds synthetic text locally and passes only when the answer
uses `query_knowledge`, states the expected claim, and includes its exact source
URL. Reports include grounded/expected claim counts and a grounding score. Raw
answers, tool output, provider errors, and credentials are not written to the
report. Schema-versioned comparison sections aggregate pass rate, elapsed time,
grounding, reported token totals, and unknown-token counts by model and scenario.
Ask-policy tools are approved only when the
scenario explicitly declares them as expected evidence; every other unattended
prompt is denied, and evaluation scope remains read-only. Direct-answer scenarios
can forbid all tool activity. A private atomic progress sidecar lets timeout and
worker-failure reports retain bounded event counts, tool names, request counts,
permission counts, and available token counters without retaining content.
Network retrieval requires an explicit scenario plus `--include-network`; report
schema version 2 paths must be new files inside the evaluated workspace.
`--knowledge-interface baseline|description|schema|name` compares the historical
interface, description-only improvement, simplified schema, and the candidate
`search_local_knowledge` wire name. Repeat the flag to compare variants and use
`--repetitions 1-5` for bounded repeated runs. Each repetition is isolated; naming
experiments currently support Ollama only, since cloud continuation formats need
separate compatibility verification. They translate structured tool names at the
runtime seam and explain the mapping in a separate system instruction without
rewriting user text or retrieved evidence. Canonical routing, permissions,
execution records, and session messages remain intact. Switching variants restores
the original runtime and contract before applying the next variant. Reports
include variant/repetition and aggregates by interface, without raw content;
Ctrl+C preserves completed comparison results in a report marked cancelled.
These are opt-in evaluations, not a production rename or permission migration.

For secret-safe Compose validation:

- `docker compose config --no-env-resolution --no-interpolate`

Before committing or pushing, inspect:

- `git status --short --branch`
- `git branch -vv`

Before publishing a prerelease, require successful CI and the Release candidate
workflow for the exact commit, then verify the candidate's checksums and provenance.
Start the candidate by manual dispatch or an alpha-tag push; the tag must match
the workspace package version. Candidate/tag creation does not publish a GitHub
Release. `scripts/verify_release_artifacts.py` is the dependency-free artifact
validator used by that workflow. Public release creation remains a separate action.

The worktree may already be dirty with user or generated changes. Never revert
changes you did not make unless the user explicitly requests it.

## Current Development Handoff (2026-09-11)

Treat the Ubuntu server checkout at `/home/klaude/klaude-code` as the canonical
development environment. Windows and VS Code are remote access clients only.
Do not add Windows compatibility unless the user explicitly requests it. Before
acting, inspect the live Ubuntu environment, repository, configuration,
dependencies, documentation, and Git state rather than relying on this snapshot.

Development state at handoff:

- Workspace package identities are `0.2.0a4`; verify the live branch and remote
  before making release claims.
- Locked multi-version CI, production mypy, wheel smoke tests, and the manual
  reproducible release-candidate attestation workflow are implemented.
- Agent execution now has immutable per-request capability snapshots, bounded
  non-progress recovery, durable stale-worker recovery, provider-safe stream
  cancellation, and offline transcript capability matrices.
- The opt-in live behavioral harness records comparable sanitized metrics across
  configured local and cloud models without adding paid/network calls to CI.
- Core exports the initial controlled-subagent contracts and bounded supervisor.
  Child roles are host-defined and read-only, intersect the parent
  callable set with effective user permissions, cannot turn a denied policy into
  a process grant, have independent and aggregate budgets, return bounded
  structured results, and emit public lifecycle events without reasoning text.
  Its isolated child adapter receives only the bounded task handoff,
  not the parent transcript, runs under a dedicated non-interactive scope, and
  uses an independent built-in provider transport. Host cancellation reaches the
  primary and child transports. Completed usage—including failed child usage—is
  charged to the parent governor.
  Narrow explicit-intent routing now exposes one permission-controlled
  delegation, with up to three independent tasks and conservative cloud
  concurrency; host cancellation and durable, resumable public child outcomes
  are connected. Runtime settings expose Auto or explicit 1-4 worker limits.
- Full validation can hang in the optional LanceDB roundtrip under some
  restricted sandboxes. Report the focused and non-LanceDB results separately;
  never describe the knowledge suite as green unless it completed.
- Continue controlled subagent orchestration with live behavioral evaluation
  before considering an implementation-worker role. Do not add
  background/cloud workers or broad write concurrency as part of that work.
