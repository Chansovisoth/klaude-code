# Agent Guidance

This file applies to the whole repository. Keep it current when project
behavior changes; future agents should be able to understand the product from
this file before diving into implementation details.

## Project Summary

`klaude-code` is a local-first AI coding agent, version `0.2.0a4`. It runs as a
Python `uv` workspace with a Typer/Rich CLI, Ollama model runtime, local memory,
refreshable knowledge libraries, multi-provider web search, local-first URL
fetching, and MCP servers for the web and knowledge layers.

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
  auto-commit support when writes are enabled. Shell commands prefer the active
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
`.github/workflows/release-candidate.yml` is a manual, non-publishing release
gate. It builds all five wheels twice with one source timestamp, validates their
metadata and archive structure, requires byte-identical output, writes
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
- `klaude ask`: one-shot question with tools enabled.
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
- `/settings [CATEGORY]`: configure categorized Theme, Input Field, Models,
  Memory, Skills, Tools, Permissions, and Runtime controls. Models opens the same source, provider, model,
  mode, and effort selection flow as `/model`. Tools persists independent
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
  high-level live stages and completed milestones. The footer keeps its compact
  Braille-spinner presentation while active, with progressive states and a
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
  Enter applies and persists a preset. Enter on a tool row cycles
  ask -> allow -> deny -> ask and persists the custom map; exact preset matches
  are detected automatically. Reset restores configured defaults. Hard workspace,
  transport, and command-safety boundaries remain effective under Full Access.
  `delegate_task` appears under Orchestration and defaults to ask. Read Only also
  keeps it at ask because delegation can consume model quota even though the
  child cannot mutate state.
  Memory shows a persistent Automatic Memory toggle, the durable-fact count,
  and up to eight recent facts; reset restores automatic memory to on. Skills
  is a read-only inventory of installed skills with their library and indexed
  file counts, plus the canonical `klaude import-skill` hint. It does not expose
  a fake enable/disable control because per-skill activation is not implemented.
  Runtime controls persist for
  future chats in `chat-preferences.json`: Auto and GPU-preferred leave CPU/GPU placement to Ollama,
  CPU-only sets no GPU layers, and GPU-only persists an explicit maximum-offload
  request (`num_gpu = -1`). Ollama has no
  separate hard no-CPU flag, so unsupported hardware may still reject or fall
  back from that request. CPU threads/context size offer presets and custom
  numeric input. Auto Calibrate
  derives bounded thread and context targets from local CPU, RAM, and VRAM,
  while keeping device placement automatic. Runtime also exposes the per-turn
  model/tool ceiling through Safe (12), Balanced (20), Extended (40), and
  custom 1-64 step choices. The selected value applies immediately, persists
  for later chats, and appears in the model-facing live configuration. Reset
  restores `[agent].max_steps` from `config.toml`; the ceiling remains an
  emergency safety boundary with one additional tool-free finalization request.
  Input border defaults on. Every category includes its own reset action.
  Runtime also offers scoped external
  Nano editors for Klaude's `config.toml` and saved runtime preferences; they
  return to the chat after exit and changes apply to the next chat.
- `/vim`: toggle Vim editing controls in the TUI composer; invoke it again to
  return to standard composer controls. The selected mode persists in
  `chat-preferences.json`.
- `/permission`: open the Permissions settings page directly. It takes no
  arguments; permission changes are made and persisted through that page.
- `/plan [on|off]`: toggle planning mode. Planning keeps read-only workspace
  tools and retrieval available while disabling writes and shell execution.
- `/compact`: compact stale model context immediately while retaining visible
  and saved transcript history.
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
  aligned label/value columns, with additional `AGENTS.md` paths on blank-label
  continuation rows.
  When the active provider is OpenAI Codex, also read the official app-server's
  current non-secret rate-limit buckets and show the five-hour, weekly, and Luna
  Reserve weekly percentages remaining with local reset times when reported.
  Link to `https://chatgpt.com/codex/settings/usage`; never infer missing windows
  or expose credentials when the app-server is unavailable.
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
  input picker with age, session ID, and a name derived from the first user turn.
  Sessions whose unexpired renewable worker lease is still running prefix the
  name with an `[ACTIVE]` badge. The badge uses a green background and green
  bracket glyphs with dark label text, matching Klaude's compact semantic-label
  treatment. Refresh active badges while the picker remains open and preserve
  the currently selected session as labels change.
  Enter resumes the selected session; Escape or cancel leaves the current
  session unchanged. This picker has no reset action. An explicit ID resumes
  directly. A successful resume clears the terminal view and scrollback before
  replaying the selected session's saved user/assistant turns and transcript,
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
  A renewable SQLite lease permits only one model worker per session, while
  every connected client keeps an independent shared draft and pending queue;
  one client's composer must never overwrite another's. Session and turn IDs
  use full random UUID hex values rather than display-truncated identifiers.
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
- `/model NAME`: switch the active chat model, then choose effort while keeping
  chat history. A successful selection is reused at the next chat launch and
  saved as a session update so `/resume` and observing clients show the change.
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
- `/refresh`: discard and redraw the current TUI frame without changing session state, for clearing terminal-render artifacts.
- `/cd [PATH]`: show or change the agent workspace directory. Relative paths
  resolve from the current agent directory; the process cwd is unchanged.
- `/pwd`: show the current agent workspace directory.
- `/ls [OPTIONS]`: run the colorized Linux `ls` command in the current agent
  workspace (for example, `/ls -lha`); positional paths remain jailed there.
- `/attach PATH`: attach a file or folder as bounded context for the next
  message. Typing `/attach ` offers paths from the current agent workspace;
  absolute paths are also accepted. Inline `@PATH` mentions work anywhere in a
  TUI message and offer the same suggestions; quote paths containing spaces,
  such as `@"project notes/brief.md"`.
- `/theme [NAME]`: open Theme settings for interface and text/code colors;
  an optional NAME sets persistent TUI chrome independently from content
  colors. Built-ins include Crimson Red, Autumn (default), Egg Yolk, Hacker
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
logical row even when that row's displayed value changes.
Settings pickers group related options under visible, non-selectable section
titles; keyboard, typed-option, and mouse selection skip those titles.
Unavailable provider and model options remain gray but can be highlighted with
the keyboard or mouse; pressing Enter or confirming them performs no action and
keeps the picker open. Blank spacer and informational tip rows remain
non-selectable. Endpoint-specific OpenAI media, transcription, embedding,
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
terminal viewport so the composer begins at the terminal bottom; it remains a
Prompt Toolkit input below the printed transcript. Alt+Enter inserts a
newline when distinguishable, Ctrl+J is the legacy-terminal newline fallback,
repeated Alt+Up edits queued follow-ups from newest to oldest, and Ctrl+C
interrupts the active response. Ctrl+D exits the chat and discards any unsent
input. Enter saves a queue edit; Alt+Backslash promotes the selected edited
follow-up to the front of the queue and steers the active turn at its next safe
boundary, without losing that follow-up's attachments or leaving a duplicate.
Queued session actions cannot be converted into model steering messages. Empty
text plus Enter deletes that item. Pending inputs render in a compact live strip immediately
above the input field, and automatic queue consumption pauses during editing.
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
counts. The TUI renders actual fragments emitted by Ollama as they arrive; it
must not simulate streaming character by character. Tool-enabled responses may
still need to assemble before their structured calls are resolved. Non-interactive stdin retains line-oriented compatibility and plain
output. Line-oriented and one-shot turns use the same renewable session lease,
durable start/result/completion events, partial-output preservation, and
failed/interrupted finalization as TUI turns. If a process disappears before
finalization, the first client observing its expired lease performs one
transactional recovery under `BEGIN IMMEDIATE`: public partial output is
promoted to the durable transcript when no assistant turn was already saved,
one interruption system turn and recovered `turn_done` event are recorded, and
only the expired owner lease is cleared. Concurrent observers cannot duplicate
recovery. Recovery never invents tool results or completed activity labels; a
start-only tool audit remains start-only. If cancellation or a provider failure
interrupts a text stream while its unpublished suffix might be text-form tool
markup, keep only the already-safe prose prefix in model history. Never feed a
half-written tool tag into the next request as assistant prose. In the TUI,
`/help` category names are underlined, and each user or
assistant message begins with a full-width gray divider containing the speaker
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
color. Selection adds no background, font weight, or underline.
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
configured data directory) as categorized `theme` and `input_field` objects.
Legacy `output_field` values are ignored because the terminal owns transcript
rendering and scrolling. Chrome and content syntax themes are deliberately
separate settings. `/theme` opens the Theme category. Input height grows between `input_field.min_height`
and `input_field.max_height` (defaults 8 and 12); legacy `height` is accepted as
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
area. Refresh, resize, and picker changes must not rewrite printed history.
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

## Config, Data, And Secrets

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
per-response output-token ceiling; Klaude detects an Ollama length stop inside
an unfinished fenced code block and may request up to
`[agent] max_code_continuations` (default 2) continuations. It does not
continue ordinary prose or guess at truncation without Ollama metadata.
Python and GDScript responses are buffered for dependency-free mechanical
validation and may receive up to `[agent] max_code_repairs` (default 2)
diagnostic-driven repairs. Unsupported languages remain single-pass.

Do not put Ollama chat options in `.env`. Do not require Modelfiles for ordinary
tuning. Host-level Ollama daemon settings such as model storage path, keepalive,
parallelism, and daemon context length belong to the Ollama systemd service,
Docker service, or whatever launcher the user chose.

Cloud runtime requests are stateless: OpenAI Responses calls set `store=false`
and surface refusal and failed-stream events instead of silently producing an
empty reply. Streaming OpenAI and Codex requests require an explicit completed
terminal event; malformed terminal events and native function-call items fail
closed instead of being treated as successful output. Codex reconciles streamed
tool/reasoning items against the authoritative completed response, deduplicates
items by provider ID, and falls back to completed response text when a transport
omits text deltas. Non-secret response IDs and terminal status are retained as
runtime metadata for diagnostics. Exact Ollama, OpenAI/Codex, and Gemini
input/output token counts feed the local footer and are mirrored to `/resume`
observers through a bounded, whitelisted completion payload. Missing or malformed
provider usage must not erase an existing estimated context count. Runtime
metadata is not used as server-side continuation
while `store=false`; conversation continuity remains local replay plus Codex's
encrypted reasoning items. Cloud context accounting uses discovered provider
model metadata
and never inherits saved Ollama `num_ctx` or GPU/thread tuning; when the Codex
catalog omits a limit, discovery records a conservative 128K fallback. Responses
history emits function calls and outputs only as complete call-ID pairs so a
cancelled or compacted turn cannot send an orphaned protocol item. Streaming
runtimes detach an active transport before closing it;
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

## Agent And Tool Routing

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
  tool output, private metadata, and opaque reasoning are excluded. The
  canonical system prompt, newest turn, and separate entity state are retained.
- if an Ollama CUDA runner aborts while placement is automatic, retry the
  request once with `num_gpu = 0` and emit only a high-level fallback activity.
  Never override an explicit CPU-only or GPU-only runtime choice.

Do not use tools for greetings, thanks, introductions, ordinary casual
conversation, or basic identity questions. Answer identity questions directly as
Klaude, a local-first coding assistant.

Use tools when they materially improve correctness or perform a requested
action. The model, not a keyword router, decides whether to call an exposed
tool. The system prompt requires retrieval for fresh public facts and explicit
lookups, while ordinary conversation and stable explanations should answer
directly. The runtime bounds and deduplicates calls but never fabricates a
search merely because the model did not ask for one.

Self-contained code-generation requests use a compact code prompt with no tool
schemas while retaining bounded durable user/project preferences. Unsupported
languages stream tool-free output. Python and GDScript are buffered until
dependency-free validation succeeds, with safe reasoning/drafting progress and
bounded diagnostic repairs, then persist one completed assistant turn.
Retrieval remains available when the user explicitly requests search, current
documentation, or workspace inspection. Explicit `do not search` language
removes knowledge and web tools for the turn. If Ollama rejects malformed Qwen
tool XML, retry once with tools disabled, then surface any repeated error.

For follow-ups, resolve the subject from the current conversation and preserve
explicit clarifications such as entity type, location, official domain, and
selected meaning. If the user changes the target entity or type, discard
incompatible prior meanings. Never reuse "school" when the clarified target is
"university", and never let an older acronym interpretation steer later queries.

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
Alternate bare tool XML is detected, never evaluated; one structured-call repair
is permitted before a visible error. Arguments are checked against the built-in
schema subset before preflight and approval. Repeated non-web tool failures stop
the approach; skipped duplicate calls render SKIPPED rather than RAN.

Explicit requests for a subagent, delegation, an independent review, or a second
opinion may route `delegate_task`; ordinary turns do not receive it automatically.
The tool defaults to ask and starts at most one sequential child. Children receive
only a bounded objective/context handoff, never the parent transcript. Host-defined
read/research and test/diagnostic roles intersect the current parent-callable tools
with effective user policies: allow and active process grants may pass through,
deny always wins, and unresolved ask policies are omitted rather than prompting
inside a child. Children cannot write, run shell, mutate Git, ask the user, remember,
learn, crawl, or delegate. Their successful and failed usage is charged to the
parent governor. Model steps and tool calls have both per-child and aggregate
caps; delegation preserves a parent tool-result slot, and a provider response
containing multiple calls stops at the first exhausted tool boundary. Ctrl+C
and steering use the same host cancellation flag and
fan out transport cancellation to the primary and active child runtimes. Each
built-in provider forks independent mutable stream, usage, and session state for
the child while retaining only the provider configuration or authentication
broker needed to connect. Custom providers that cannot fork fail closed instead
of silently sharing a transport. Sanitized start/finish events and a bounded public final
summary are persisted and mirrored to `/resume`; private reasoning and raw tool
output are never stored as subagent activity. Execution remains sequential until
aggregate budgets and lifecycle ordering are concurrency-safe.

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
ZIP extraction rejects unsafe paths. Re-imports create content-addressed
versions and finalize the manifest only after knowledge indexing succeeds.

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

## Current Boundaries

- There is no native VS Code extension or `klaude serve` IDE backend yet.
- The CLI/TUI is the full agent surface today.
- MCP servers expose only web and knowledge capabilities.
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
to evaluate direct response, workspace inspection, and contextual diagnostic
behavior. Each model/scenario pair runs read-only in an isolated child process
with a hard timeout. Raw answers, tool output, provider errors, and credentials
are not written to the report. Network retrieval requires an explicit scenario
plus `--include-network`; report paths must be new files inside the evaluated
workspace.

For secret-safe Compose validation:

- `docker compose config --no-env-resolution --no-interpolate`

Before committing or pushing, inspect:

- `git status --short --branch`
- `git branch -vv`

Before a prerelease, run the manual Release candidate workflow for the exact
commit and verify its checksums and provenance. `scripts/verify_release_artifacts.py`
is the dependency-free artifact validator used by that workflow.

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
- Core exports the initial controlled-subagent contracts and sequential
  supervisor. Child roles are host-defined and read-only, intersect the parent
  callable set with effective user permissions, cannot turn a denied policy into
  a process grant, have independent and aggregate budgets, return bounded
  structured results, and emit public lifecycle events without reasoning text.
  Its isolated sequential child adapter receives only the bounded task handoff,
  not the parent transcript, runs under a dedicated non-interactive scope, and
  uses an independent built-in provider transport. Host cancellation reaches the
  primary and child transports. Completed usage—including failed child usage—is
  charged to the parent governor.
  Narrow explicit-intent routing now exposes one permission-controlled delegation;
  host cancellation and durable, resumable public child outcomes are connected.
- Full validation can hang in the optional LanceDB roundtrip under some
  restricted sandboxes. Report the focused and non-LanceDB results separately;
  never describe the knowledge suite as green unless it completed.
- Continue controlled subagent orchestration with exact aggregate token budgets,
  concurrency-safe lifecycle ordering, adaptive concurrency, and live behavioral
  evaluation before considering an implementation-worker role. Do not add
  background/cloud workers or broad write concurrency as part of that work.
