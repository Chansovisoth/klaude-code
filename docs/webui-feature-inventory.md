# Klaude WebUI Preparation — Feature and Settings Inventory

**Audit date:** 2026-10-15 · **Product:** klaude-code 0.2.0a4
**Repository:** `/home/klaude/klaude-code` · **Branch:** `klaude/20260908-1448`
**Base revision:** `0234b116f4380cb87c1b1cf39959725493e227ee`
**Source of truth:** the live worktree, including 108 pre-existing modified/untracked paths. This document is not a description of the base commit alone. Source line references describe this worktree and may shift after subsequent changes.

**Purpose:** handoff for browser UX/navigation and feature mapping. Research/documentation only; no WebUI, server, settings toggle, frontend framework, component architecture or production behavior is implemented by this audit.

**S6 maintenance update (2026-10-15):** subsequent implementation delivered optional
AI tags, native CPU/CUDA generation/recovery and private image-job management. Relevant
feature/command entries and registry totals below are updated; original audit
verification remains historical. Current evidence and remaining provider/hardware
gates: [S6 completion validation](s6-completion-validation.md).

## Contents

1. [Executive Summary](#1-executive-summary)
2. [Complete Feature Inventory](#2-complete-feature-inventory)
3. [Complete Settings Inventory](#3-complete-settings-inventory)
4. [CLI, slash commands and keyboard actions](#4-cli-commands-slash-commands-and-keyboard-actions)
5. [Core User Workflows](#5-core-user-workflows)
6. [TUI-only exclusions](#6-tui-only-features-to-exclude)
7. [Browser adaptation](#7-features-requiring-webui-adaptation)
8. [Backend architecture](#8-existing-backend-architecture-and-reusable-components)
9. [Readiness gaps](#9-webui-readiness-gaps)
10. [Proposed logical grouping](#10-proposed-webui-feature-and-settings-grouping)
11. [Coverage and verification](#11-coverage-and-verification-checklist)

## 1. Executive Summary

Klaude is a local-first coding/agent environment with interactive and one-shot execution, scoped tools and permissions, bounded read-only subagents, eight model connection backends, local knowledge and web retrieval, durable sessions/memory, Skills, external MCP clients and two restricted MCP servers. Model Manager includes native Ollama lifecycle operations, installed **llama.cpp and vLLM**, trusted CPU/CUDA source builds, offline vLLM wheel installation, local/remote serving, SSH diagnostics/key trust/enrollment and existing-server adoption. Library separates Sessions, Knowledge, Documents, Research, Media and Archive. Image analysis/chat attachments support declared-capability provider paths; the native local image-generation consumer has actual CPU generation/export evidence. Optional AI tagging and private image-job management are now implemented; GPU/cloud certification boundaries remain explicit.

### Scope and evidence levels

- **Source-confirmed:** production declarations, command handlers, request validation, persistence, provider adapters, worker orchestration and relevant test assertions were inspected. All 145 production Python files were parsed to enumerate symbols/configuration/environment access, with targeted reads of feature implementations. Parsing is not a claim that every line was manually read.
- **Registry-confirmed:** the real Typer application was imported under an isolated temporary config/data root and its Click command tree inspected without executing command handlers or contacting providers. The slash-command/keybinding registries and actual picker/settings handlers were cross-checked.
- **Focused regression validation:** see §11 for this audit’s exact run and result. This is not a full application certification, full-suite run or new live model/SSH/GPU benchmark.
- **Historical runtime evidence:** linked validation reports describe prior live/fixture runs and their limitations; they are not new measurements from this audit. Model/provider availability and machine state may have changed.
- **Not verified:** browser behavior, absent WebUI endpoints, every provider/model/account/hardware combination, current upstream service availability, and end-to-end success on arbitrary complex coding tasks. Previous small-model CSV failures are not erased by the presence of execution-state machinery.

### WebUI readiness

There is substantial reusable backend functionality, including model transports, Agent events, permission/preflight boundaries, revisioned settings, session event cursors and writer leases. There is **no full-agent browser HTTP/WebSocket/SSE API or WebUI host lifecycle**. CLI `main.py` still owns substantial agent construction, tool registration, selection, prompt enrichment, input brokers and session orchestration. A browser must reuse these semantics through adapters rather than reproduce a second agent loop. Existing MCP servers expose limited web/knowledge services; the MCP OAuth callback and model-serving HTTP listeners are not a WebUI.

### Reading and counting conventions

- **Status:** Implemented = an actual execution path exists; Partial = a bounded subset exists or a stated validation gate remains open; Planned = no current execution path; Broken = observed implementation defect (none newly established by this documentation audit); Deprecated = compatibility surface to preserve, not a new UI feature.
- **Classification:** REQUIRED = expose capability; ADAPT = preserve it using browser-native interaction; OPTIONAL = can be deferred initially; TUI-ONLY = terminal-specific; INTERNAL = backend ownership with no direct user control; DEPRECATED = compatibility only. A tool accessed through a terminal is not automatically TUI-only.
- Feature IDs count distinct functional **groups**, not every provider, command alias, button or code symbol. Settings IDs count exact stored keys or dynamic field families once per scope; compatibility aliases are noted, not counted again. Request controls and transient filters are explicitly identified as nonpersistent. Environment aliases and CLI input parameters are separately counted to prevent inflation.
- Every settings row inherits its group’s persistence/effect convention only where stated; an unset field is not a fabricated saved value. Internal constructor defaults are separated from configurable TOML/JSON keys.

**Inventory totals:** **103 feature groups**, **279 settings/control keys or field families**, **16 TUI-only exclusions**, **97 leaf CLI subcommands**, **240 CLI input parameters**, **44 slash registry records**, **10 registered keyboard actions**. Environment input groups are enumerated separately in §3.3 (not double-counted as stored settings). S6 adds no stored settings; it reuses Vision budgets and image-generation configuration. The 240 CLI parameters include 238 leaf inputs and two existing Sessions group inputs, verified by importing the real Typer tree under an isolated config root.

## 2. Complete Feature Inventory

Each entry gives its current behavior, entry point, configuration, dependencies, classification/surface, implementation references and practical limits. “Implemented” is source status, not a promise of live-provider certification.

### Agent and coding interaction

#### F001. Interactive agent and one-shot requests

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Chat / task composer

Iterative model/tool execution with persisted public dialogue and private continuation content; bare executable launches chat.

- **Current entry:** klaude; klaude chat; klaude ask QUESTION
- **Configuration/defaults:** agent.*; active session model/runtime
- **Dependencies:** Selected provider; workspace; Memory
- **Implementation:** [packages/core/src/klaude_core/agent.py:Agent](../packages/core/src/klaude_core/agent.py#L3864); [apps/cli/src/klaude_cli/main.py:chat](../apps/cli/src/klaude_cli/main.py#L20055); [apps/cli/src/klaude_cli/main.py:ask](../apps/cli/src/klaude_cli/main.py#L20563)
- **Limits/notes:** A one-shot model/runtime failure exits 1; completed answer exits 0. This audit did not run a new autonomous coding benchmark. --no-tui retains a simple line-oriented mode; --legacy requests chunk-style streamed rendering; these presentation choices are captured in CLI inputs.

#### F002. Plan mode and approval

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Agent and coding interaction

Read-only Plan mode removes mutation capabilities. Conversational approval follow-ups retain the preceding objective/plan and can expose implementation tools under normal scope and permissions.

- **Current entry:** /plan [on|off]; plan review/approval interaction
- **Configuration/defaults:** agent.plan_mode (session state, initially false)
- **Dependencies:** Agent scopes; user decision broker
- **Implementation:** [packages/core/src/klaude_core/capabilities.py:TurnScope](../packages/core/src/klaude_core/capabilities.py#L14); [apps/cli/src/klaude_cli/main.py:_build_agent](../apps/cli/src/klaude_cli/main.py#L7126)
- **Limits/notes:** The user must leave Plan mode before implementation (/plan off); a conversational approval does not override that scope. No standalone structured plan-approval dialog was found. Browser may adapt the approval conversation while preserving exact intent and permissions.

#### F003. Adaptive structured execution state

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Backend; optionally task progress

Workspace execution tracks observed files/revisions, plan cursor, changes, validation and failures; bounded working context supports inspect/implement/validate/repair sequences.

- **Current entry:** Automatic for applicable implementation turns
- **Configuration/defaults:** agent.max_steps/max_code_continuations/max_code_repairs
- **Dependencies:** Provider structured-action support; tool execution receipts
- **Implementation:** [packages/core/src/klaude_core/workspace_execution.py:WorkspaceExecution](../packages/core/src/klaude_core/workspace_execution.py#L115); [packages/core/src/klaude_core/ollama.py:chat_workspace_plan](../packages/core/src/klaude_core/ollama.py#L373); [packages/core/src/klaude_core/working_sources.py](../packages/core/src/klaude_core/working_sources.py#L1)
- **Limits/notes:** Not a universal planner or proof that every requested requirement is complete. See prior power-user evaluation; do not advertise guaranteed small-model task completion.

#### F004. Standard/Thinking modes and reasoning effort

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Agent and coding interaction

Provider/model capabilities determine supported reasoning controls and whether Standard is available. Choice is saved with the session.

- **Current entry:** /mode; /effort; Models → current model
- **Configuration/defaults:** session runtime mode standard/thinking; effort model-dependent minimal/low/medium/high/max
- **Dependencies:** Declared ModelCapabilities; selected runtime
- **Implementation:** [packages/core/src/klaude_core/model_runtime.py:ModelCapabilities](../packages/core/src/klaude_core/model_runtime.py#L114); [packages/core/src/klaude_core/session_runtime.py](../packages/core/src/klaude_core/session_runtime.py#L1); [packages/core/src/klaude_core/anthropic_runtime.py](../packages/core/src/klaude_core/anthropic_runtime.py#L1); [packages/core/src/klaude_core/deepseek_runtime.py](../packages/core/src/klaude_core/deepseek_runtime.py#L1)
- **Limits/notes:** Unsupported controls are unavailable. Provider-specific wire mappings and required-thinking constraints must survive browser selection.

#### F005. Execution budgets and usage

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Agent and coding interaction

Bounds model steps, tool calls, optional token use and subagent concurrency; reports known usage without treating missing provider counters as zero.

- **Current entry:** Settings → Agent Tools → execution controls; /status
- **Configuration/defaults:** 20 steps; tool calls 0=Auto (normally 2×steps, minimum 4); tokens 0=no cap; concurrency 0=Auto
- **Dependencies:** TurnGovernor; provider usage metadata
- **Implementation:** [packages/core/src/klaude_core/execution.py:TurnGovernor](../packages/core/src/klaude_core/execution.py#L69); [packages/core/src/klaude_core/agent_settings.py:EXECUTION_LIMITS](../packages/core/src/klaude_core/agent_settings.py#L7)
- **Limits/notes:** Includes bounded elapsed/no-progress safeguards and a finalization reserve; not a billing enforcement guarantee.

#### F006. Tool selection and capability awareness

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Agent and coding interaction

Selects per-turn schemas from enabled registered tools, intent and scope; supplies truthful capability and skill guidance to the model.

- **Current entry:** Automatic; Agent Tools switches
- **Configuration/defaults:** tool_availability; permissions; enabled MCP/Skills
- **Dependencies:** CLI tool registry; core capability snapshot
- **Implementation:** [packages/core/src/klaude_core/capabilities.py](../packages/core/src/klaude_core/capabilities.py#L1); [packages/core/src/klaude_core/agent.py:active_schemas](../packages/core/src/klaude_core/agent.py#L4764); [packages/core/src/klaude_core/agent.py:capability_snapshot](../packages/core/src/klaude_core/agent.py#L4803); [apps/cli/src/klaude_cli/main.py:_build_agent](../apps/cli/src/klaude_cli/main.py#L7126)
- **Limits/notes:** Installed, enabled, authorized and callable are separate states. No automatic web retrieval is required for a simple direct answer.

#### F007. Streaming and tool/subagent progress

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Chat stream / task activity / expandable output

Emits public text and structured execution events, sanitizes tool summaries and retains useful partial public text on interruption.

- **Current entry:** Chat stream; activity display; tool result rendering
- **Configuration/defaults:** display.activity_updates=true
- **Dependencies:** AgentEvent; runtime streaming; CLI event bridge
- **Implementation:** [packages/core/src/klaude_core/agent.py:AgentEvent](../packages/core/src/klaude_core/agent.py#L457); [apps/cli/src/klaude_cli/main.py:PersistentChatTUI](../apps/cli/src/klaude_cli/main.py#L9144); [packages/core/src/klaude_core/subagents.py:SubagentEvent](../packages/core/src/klaude_core/subagents.py#L191)
- **Limits/notes:** Private reasoning/provider signatures must remain private; tool markup and incomplete calls are not public answers.

#### F008. Cancellation and transport recovery

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Agent and coding interaction

Cancels active model/metadata/tool workers, closes transports, preserves valid history and separates interrupted, failed and unknown outcomes.

- **Current entry:** /cancel; Ctrl+C; job Cancel/Stop
- **Configuration/defaults:** Subsystem deadlines; cancellation observers
- **Dependencies:** HTTP transport; process ownership; worker cleanup
- **Implementation:** [packages/core/src/klaude_core/http_model_transport.py](../packages/core/src/klaude_core/http_model_transport.py#L1); [packages/core/src/klaude_core/agent.py:run](../packages/core/src/klaude_core/agent.py#L4258); [apps/cli/src/klaude_cli/background_jobs.py](../apps/cli/src/klaude_cli/background_jobs.py#L1); [apps/cli/src/klaude_cli/setup_jobs.py](../apps/cli/src/klaude_cli/setup_jobs.py#L1)
- **Limits/notes:** Cancellation cannot undo an already completed external write. Browser disconnect and explicit Cancel need separate ownership semantics.

#### F009. Malformed calls, path recovery and bounded retries

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Agent and coding interaction

Repairs malformed tool calls, resolves observed-path spelling mistakes, suppresses duplicates, tracks shell exit failures and bounds empty-answer/continuation/repair retries.

- **Current entry:** Automatic errors and retry feedback
- **Configuration/defaults:** agent.max_code_continuations=2; max_code_repairs=2
- **Dependencies:** Tool execution metadata; provider finish reasons
- **Implementation:** [packages/core/src/klaude_core/agent.py:execute_tool_call](../packages/core/src/klaude_core/agent.py#L5287); [packages/core/src/klaude_core/ollama.py:chat_structured_action](../packages/core/src/klaude_core/ollama.py#L176); [packages/core/src/klaude_core/workspace_execution.py](../packages/core/src/klaude_core/workspace_execution.py#L1)
- **Limits/notes:** GPU runner failure may retry CPU only when placement is automatic; an explicit GPU choice is not silently overridden.

#### F010. Context compaction and recap

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Conversation context / recap

Prunes/bounds working context, creates deterministic public recaps, retains tool call/output pairing and refreshes stale observed source revisions.

- **Current entry:** Automatic; /compact; /recap [--ai]
- **Configuration/defaults:** Runtime context size; working-source bounds; Utility settings
- **Dependencies:** context_compaction; request projection
- **Implementation:** [packages/core/src/klaude_core/context_compaction.py:build_recap](../packages/core/src/klaude_core/context_compaction.py#L77); [packages/core/src/klaude_core/request_context.py](../packages/core/src/klaude_core/request_context.py#L1); [packages/core/src/klaude_core/working_sources.py](../packages/core/src/klaude_core/working_sources.py#L1); [packages/core/src/klaude_core/agent.py:model_messages](../packages/core/src/klaude_core/agent.py#L5124)
- **Limits/notes:** A saved recap or research receipt is not source/pixel evidence. /recap --ai uses explicit Utility generation; it does not replace original history.

#### F011. Clarifying questions and structured user input

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Agent and coding interaction

Agent can ask bounded questions/options through an interactive broker and resume the same turn after the response.

- **Current entry:** request_user_input tool
- **Configuration/defaults:** Tool availability/policy; broker-supported interactive mode
- **Dependencies:** CLI input broker; active turn
- **Implementation:** [apps/cli/src/klaude_cli/main.py:_build_agent](../apps/cli/src/klaude_cli/main.py#L7126); [packages/core/src/klaude_core/agent.py:execute_tool_call](../packages/core/src/klaude_core/agent.py#L5287)
- **Limits/notes:** One-shot/noninteractive paths cannot assume a live human response. Browser must correlate request, session and turn and support cancellation.

#### F012. Read-only delegated workers

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Task activity / worker detail

Supervisor delegates bounded independent read/research or test/diagnostic tasks and merges summaries, usage and lifecycle events.

- **Current entry:** delegate_task; explicit delegation intent
- **Configuration/defaults:** Local Auto concurrency 1; cloud Auto up to 2; override 0–4, role/tool intersections and aggregate caps
- **Dependencies:** Forkable provider runtime; parent capabilities/governor
- **Implementation:** [packages/core/src/klaude_core/subagents.py:supervise_agent_tasks](../packages/core/src/klaude_core/subagents.py#L819); [apps/cli/src/klaude_cli/main.py:_delegate_task_result](../apps/cli/src/klaude_cli/main.py#L5345)
- **Limits/notes:** No recursive delegation, writes, shell, Git mutation or independent approval escalation. Despite the diagnostic role name, children do not execute arbitrary test commands. Actual parallelism also depends on audited tools.

#### F013. Generated code response checks

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Agent and coding interaction

Applies response constraints/mechanical checks and bounded repairs to applicable generated code answers, in addition to workspace validation tracking.

- **Current entry:** Automatic on applicable code requests
- **Configuration/defaults:** max_code_continuations/max_code_repairs; code_options/code_think
- **Dependencies:** Response constraint detection; available validators
- **Implementation:** [packages/core/src/klaude_core/response_constraints.py](../packages/core/src/klaude_core/response_constraints.py#L1); [packages/core/src/klaude_core/agent.py](../packages/core/src/klaude_core/agent.py#L1)
- **Limits/notes:** Validation is selective and mechanical, not proof of application correctness.

### Workspace and developer tools

#### F014. Workspace selection and awareness

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Workspace selector / file explorer

Maintains current project root, repository information and model-visible bounded workspace context; supports directory switching and listing.

- **Current entry:** /cd [PATH]; /pwd; /ls [OPTIONS] [PATH ...]; startup cwd
- **Configuration/defaults:** Workspace path per client/session interaction
- **Dependencies:** Host filesystem; Git when present
- **Implementation:** [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089); [packages/tools_local/src/klaude_tools/toolkit.py:Workspace](../packages/tools_local/src/klaude_tools/toolkit.py#L350); [packages/core/src/klaude_core/runtime_context.py](../packages/core/src/klaude_core/runtime_context.py#L1)
- **Limits/notes:** A browser client path is not a server path. Text/image attachment permissions differ from workspace tool jail.

#### F015. Repository instructions and initialization

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Workspace and developer tools

Reads bounded repository AGENTS.md guidance; /init helps create/update root project instructions through a restricted initialization scope.

- **Current entry:** /init; automatic project instruction loading
- **Configuration/defaults:** Root/nested guidance bounds; TurnScope.INIT
- **Dependencies:** Workspace reads; authorized root AGENTS.md write
- **Implementation:** [apps/cli/src/klaude_cli/main.py:_build_agent](../apps/cli/src/klaude_cli/main.py#L7126); [packages/core/src/klaude_core/capabilities.py:TurnScope](../packages/core/src/klaude_core/capabilities.py#L14); [packages/core/src/klaude_core/request_context.py](../packages/core/src/klaude_core/request_context.py#L1)
- **Limits/notes:** Project instructions are untrusted relative to user permission boundaries; init scope does not grant arbitrary writes.

#### F016. Read and search project files

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** File explorer / source viewer / search

Provides read_file, list_dir, grep and workspace_info, including bounded numbered later-line file reads.

- **Current entry:** Agent tools; explicit file requests
- **Configuration/defaults:** read_file offset 1–1,000,000; limit 1–500 (paged default 200); output 60,000 chars; list cap 300
- **Dependencies:** Workspace jail; system grep
- **Implementation:** [packages/tools_local/src/klaude_tools/toolkit.py:read_file](../packages/tools_local/src/klaude_tools/toolkit.py#L608); [packages/tools_local/src/klaude_tools/toolkit.py:list_dir](../packages/tools_local/src/klaude_tools/toolkit.py#L665); [packages/tools_local/src/klaude_tools/toolkit.py:grep](../packages/tools_local/src/klaude_tools/toolkit.py#L675)
- **Limits/notes:** Secret paths are blocked/redacted; grep output cap 10,000 chars, 30s timeout. Unpaged read preserves plain output.

#### F017. Edit and create project files

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Change review / file diff

write_file creates/replaces a file; edit_file requires an exact unique old string and returns structured change/diff metadata.

- **Current entry:** Agent tool requests; file-write approvals
- **Configuration/defaults:** permissions.write_file/edit_file; Workspace.auto_commit=true constructor default
- **Dependencies:** Clean authorized work branch; mutation lock
- **Implementation:** [packages/tools_local/src/klaude_tools/toolkit.py:write_file](../packages/tools_local/src/klaude_tools/toolkit.py#L631); [packages/tools_local/src/klaude_tools/toolkit.py:edit_file](../packages/tools_local/src/klaude_tools/toolkit.py#L644); [packages/tools_local/src/klaude_tools/toolkit.py:_mutation_lock](../packages/tools_local/src/klaude_tools/toolkit.py#L464)
- **Limits/notes:** Not an independent public editor API. Dirty worktree lockout and unique-anchor conflict feedback apply; browser edits must not bypass them.

#### F018. Shell, builds and project validation

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Command approval / command output / validation

Executes classified workspace commands with exit code/output, project-local executable priority, isolated environment and Linux Landlock filesystem restrictions.

- **Current entry:** run_shell tool
- **Configuration/defaults:** 120s shell deadline; permissions.run_shell; risk classification
- **Dependencies:** Linux Landlock; bash for permitted shell syntax; project tools
- **Implementation:** [packages/tools_local/src/klaude_tools/toolkit.py:run_shell](../packages/tools_local/src/klaude_tools/toolkit.py#L718); [packages/tools_local/src/klaude_tools/toolkit.py:classify_command](../packages/tools_local/src/klaude_tools/toolkit.py#L235); [packages/tools_local/src/klaude_tools/sandbox.py:restrict_filesystem](../packages/tools_local/src/klaude_tools/sandbox.py#L134)
- **Limits/notes:** Destructive commands are denied; unsupported secure shell environment fails explicitly. This is not a general interactive PTY terminal or network sandbox.

#### F019. Dirty-tree safety and guarded Git mutations

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Workspace and developer tools

Refuses writes for pre-existing user changes; uses work branches, clean-tree rechecks, repository mutation flock and scoped auto-commits when enabled.

- **Current entry:** Automatic Workspace setup; git_commit tool
- **Configuration/defaults:** Workspace.auto_commit=true is a Python constructor choice, not a documented persistent UI toggle
- **Dependencies:** Git executable/repository
- **Implementation:** [packages/tools_local/src/klaude_tools/toolkit.py:ensure_work_branch](../packages/tools_local/src/klaude_tools/toolkit.py#L423); [packages/tools_local/src/klaude_tools/toolkit.py:_commit](../packages/tools_local/src/klaude_tools/toolkit.py#L491); [packages/tools_local/src/klaude_tools/toolkit.py:_require_clean_repo](../packages/tools_local/src/klaude_tools/toolkit.py#L454)
- **Limits/notes:** A lock protects tool mutations, but shared checkout branch changes and several clients still need explicit product coordination. Do not infer support for parallel independent coding on one checkout.

#### F020. Git status, diff and read-only review

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Changes / review

Shows workspace Git state/diffs and asks the model to review changes under a read-only scope.

- **Current entry:** git_status; git_diff; /diff; /review
- **Configuration/defaults:** Permission policies; review scope
- **Dependencies:** Git; selected model for AI review
- **Implementation:** [packages/tools_local/src/klaude_tools/toolkit.py:git_status](../packages/tools_local/src/klaude_tools/toolkit.py#L791); [packages/tools_local/src/klaude_tools/toolkit.py:git_diff](../packages/tools_local/src/klaude_tools/toolkit.py#L797); [packages/core/src/klaude_core/capabilities.py:TurnScope](../packages/core/src/klaude_core/capabilities.py#L14); [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089)
- **Limits/notes:** No first-class PR/issue/merge GitHub client found; GitHub repository metadata used by catalogs is a separate capability.

#### F021. Permission policy and decision prompts

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Security settings / approval dialog

Per-tool allow/ask/deny policies, presets, one-time decisions and temporary process grants; preflight can deny before asking.

- **Current entry:** /permission; Settings → Permissions; y/n/a prompt
- **Configuration/defaults:** Default tool map; persistent policy overrides; Balanced/Cautious/Read-only/Full access/Custom
- **Dependencies:** PermissionGate; preflight; availability; active scope
- **Implementation:** [packages/core/src/klaude_core/permissions.py:PermissionGate](../packages/core/src/klaude_core/permissions.py#L22); [packages/core/src/klaude_core/config.py:DEFAULT_PERMISSIONS](../packages/core/src/klaude_core/config.py#L666); [apps/cli/src/klaude_cli/main.py:_permission_preset_name](../apps/cli/src/klaude_cli/main.py#L1875)
- **Limits/notes:** Empty Enter currently allows once; a means process-level always, not a silently persisted global policy. Browser defaults should be explicitly reviewed.

#### F022. Built-in tool enable/disable and validation toggles

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Workspace and developer tools

Global/per-group switches control future callable schemas without changing permission grants; separate web/knowledge result validation switches.

- **Current entry:** Settings → Agent Tools
- **Configuration/defaults:** tool_availability.<name> default true; tool_validation.web_search/knowledge_search true
- **Dependencies:** Actual live registered tools
- **Implementation:** [packages/core/src/klaude_core/tool_settings.py:BUILTIN_TOOL_GROUPS](../packages/core/src/klaude_core/tool_settings.py#L10); [packages/core/src/klaude_core/agent_settings.py](../packages/core/src/klaude_core/agent_settings.py#L1); [apps/cli/src/klaude_cli/main.py:_apply_tool_availability_preferences](../apps/cli/src/klaude_cli/main.py#L1785)
- **Limits/notes:** 30 named built-in presentation entries; runtime registry is authoritative and external MCP tools retain their own owner.

#### F023. Runtime and storage diagnostics

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Diagnostics / status

Shows normalized system info, configured services/models, host storage totals, health checks and local hardware hints.

- **Current entry:** status; system-info; doctor; storage_usage; Model Manager → Hardware
- **Configuration/defaults:** runtime_context.*; permissions.storage_usage
- **Dependencies:** Local probes; optional fastfetch/neofetch; service requests
- **Implementation:** [packages/core/src/klaude_core/runtime_context.py](../packages/core/src/klaude_core/runtime_context.py#L1); [packages/tools_local/src/klaude_tools/diagnostics.py:storage_usage](../packages/tools_local/src/klaude_tools/diagnostics.py#L9); [packages/core/src/klaude_core/runtime_calibration.py](../packages/core/src/klaude_core/runtime_calibration.py#L1); [apps/cli/src/klaude_cli/main.py:doctor](../apps/cli/src/klaude_cli/main.py#L22278)
- **Limits/notes:** May reveal host/IP/path metadata; model-fit and real GPU inference are not established by a hardware report.

#### F024. Ollama service controls

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model service diagnostics

Supports explicit start/restart/stop operations with system/service detection and administrator prompt where necessary.

- **Current entry:** /start; /restart; /stop
- **Configuration/defaults:** Host service behavior, not a WebUI hosting setting
- **Dependencies:** Local OS service control; potentially sudo
- **Implementation:** [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089)
- **Limits/notes:** Host administrative action requires browser-specific credentials/consent design. It is not a generic control for remote cloud endpoints.

### Models and provider connections

#### F025. Native Ollama chat, embeddings and discovery

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Native HTTP chat/stream/embed APIs, installed-model metadata and declared capabilities support local or explicitly configured LAN servers.

- **Current entry:** Models; model-connections; models; native runtime
- **Configuration/defaults:** services.ollama_url=http://localhost:11434; models roles; ollama options
- **Dependencies:** Reachable Ollama daemon; installed model
- **Implementation:** [packages/core/src/klaude_core/ollama.py:Ollama](../packages/core/src/klaude_core/ollama.py#L71); [packages/core/src/klaude_core/model_discovery.py](../packages/core/src/klaude_core/model_discovery.py#L1); [packages/core/src/klaude_core/model_runtime.py:OllamaRuntime](../packages/core/src/klaude_core/model_runtime.py#L455)
- **Limits/notes:** Klaude does not infer images/tools from a friendly model name. Ollama daemon bind/port/GPU environment is externally managed.

#### F026. Compatible HTTP model endpoints

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Connects OpenAI-compatible servers, including existing llama.cpp and vLLM servers; normalizes model catalogs and Chat Completions streaming/tools.

- **Current entry:** Settings → Models → Add Local/API Models; model-connections add/test
- **Configuration/defaults:** ModelConnection.backend=openai_compatible; explicit base_url/key_env
- **Dependencies:** Compatible HTTP implementation and exact model ID
- **Implementation:** [packages/core/src/klaude_core/compatible_runtime.py](../packages/core/src/klaude_core/compatible_runtime.py#L1); [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91)
- **Limits/notes:** Compatibility is capability-dependent; a compatible endpoint is not necessarily a native Ollama endpoint.

#### F027. Cloud model providers

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Provider adapters cover OpenAI API, OpenRouter, Gemini API, DeepSeek and Anthropic with provider-specific streaming/reasoning/tools.

- **Current entry:** Settings → Models; model-connections add; /model
- **Configuration/defaults:** Eight backend identifiers including local/compatible/Codex; separate key references
- **Dependencies:** HTTP endpoints; optional cloud SDK extra for applicable adapters
- **Implementation:** [packages/core/src/klaude_core/model_runtime.py](../packages/core/src/klaude_core/model_runtime.py#L1); [packages/core/src/klaude_core/deepseek_runtime.py](../packages/core/src/klaude_core/deepseek_runtime.py#L1); [packages/core/src/klaude_core/anthropic_runtime.py](../packages/core/src/klaude_core/anthropic_runtime.py#L1); [packages/core/src/klaude_core/model_connections.py:BACKENDS](../packages/core/src/klaude_core/model_connections.py#L24)
- **Limits/notes:** Implementation does not certify every model ID, plan, region, account or capability. Provider errors and unsupported modes remain visible.

#### F028. OpenAI Codex account authentication

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Connections / authentication

External Codex account broker supports login/status/logout and account-backed model/runtime access; distinct from OpenAI API-key configuration.

- **Current entry:** auth login/status/logout; Models → OpenAI Codex
- **Configuration/defaults:** KLAUDE_CODEX_BIN optional executable; external auth state
- **Dependencies:** Installed supported Codex executable/app-server; account authentication
- **Implementation:** [packages/core/src/klaude_core/codex_auth.py](../packages/core/src/klaude_core/codex_auth.py#L1); [packages/core/src/klaude_core/model_runtime.py:CodexRuntime](../packages/core/src/klaude_core/model_runtime.py#L1488); [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089)
- **Limits/notes:** Do not equate this current implementation with old docs saying Codex OAuth is absent. Browser/device-login handling and host credential custody require adaptation.

#### F029. Add, test and maintain endpoints

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Draft Test probes catalog without generation; saved endpoints support Probe all, enable/disable, reviewed delete and Clear offline maintenance.

- **Current entry:** Models → Add Models / Added Models; model-connections list/add/test
- **Configuration/defaults:** Up to 64 connections; definition and credential revisions
- **Dependencies:** Connection registry; metadata workers
- **Implementation:** [apps/cli/src/klaude_cli/model_settings.py:ModelSettings](../apps/cli/src/klaude_cli/model_settings.py#L282); [packages/core/src/klaude_core/model_connections.py:ModelConnectionRegistry](../packages/core/src/klaude_core/model_connections.py#L187); [packages/core/src/klaude_core/model_management.py:apply_model_change](../packages/core/src/klaude_core/model_management.py#L180)
- **Limits/notes:** Authentication, malformed catalog and rate limits are distinct from offline. Destructive operations protect configured roles and explicit selections.

#### F030. Model inventory choices and picker

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Lists qualified models per endpoint with capabilities, filtering/grouping, enabled/hidden/pinned preferences and cached catalogs.

- **Current entry:** /model; Models → current model / endpoint models
- **Configuration/defaults:** model_choices.<connection>.<model>.enabled=true/hidden=false/pinned=false
- **Dependencies:** Declared catalog metadata; revision-scoped cache
- **Implementation:** [apps/cli/src/klaude_cli/model_settings.py](../apps/cli/src/klaude_cli/model_settings.py#L1); [packages/core/src/klaude_core/model_management.py:choices_from_payload](../packages/core/src/klaude_core/model_management.py#L43); [packages/core/src/klaude_core/model_runtime.py:ModelInfo](../packages/core/src/klaude_core/model_runtime.py#L149)
- **Limits/notes:** No automatic substitution when an explicit model or endpoint becomes unavailable. Cache freshness and unknown capabilities need visible states.

#### F031. AI Defaults and role inheritance

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Default Chat governs new sessions; optional Utility and Research inherit chat when unset; Vision has explicit enable/model and ordered fallbacks.

- **Current entry:** Settings → AI Defaults
- **Configuration/defaults:** ai_defaults chat/utility/research/vision; output_tokens512; up to 3 explicit utility/vision fallbacks
- **Dependencies:** Valid enabled connections/models; capability eligibility
- **Implementation:** [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1)
- **Limits/notes:** Changing Default Chat does not replace the current session model. Research and chat do not silently fall back to another model.

#### F032. Explicit Utility naming and recaps

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Runs bounded title/recap generation using public recent dialogue only; supports explicit reviewed fallback chain and usage result.

- **Current entry:** /rename --ai; /recap --ai; AI Defaults → Utility test
- **Configuration/defaults:** 512 output tokens, 128–2048; up to 24 turns/6000 chars of public dialogue
- **Dependencies:** Utility-eligible runtime; owned worker
- **Implementation:** [packages/core/src/klaude_core/utility.py:public_dialogue](../packages/core/src/klaude_core/utility.py#L29); [packages/core/src/klaude_core/utility.py:runtime_for_utility](../packages/core/src/klaude_core/utility.py#L56); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1)
- **Limits/notes:** No tools, full private history, automatic memory extraction or background periodic compaction is implied.

#### F033. Runtime resource and sampling controls

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

CPU/GPU placement, thread/context overrides and hardware-derived bounded recommendations; config sampling/output/thinking controls.

- **Current entry:** Settings → Runtime; ollama TOML; model-specific settings
- **Configuration/defaults:** Auto/cpu-only/gpu-preferred/gpu-only; num_ctx/num_thread/num_gpu; general num_predict2048, code >=4096
- **Dependencies:** Runtime capabilities; calibration probes
- **Implementation:** [packages/core/src/klaude_core/runtime_calibration.py:recommend_runtime_options](../packages/core/src/klaude_core/runtime_calibration.py#L73); [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [apps/cli/src/klaude_cli/main.py:_load_runtime_preferences](../apps/cli/src/klaude_cli/main.py#L1696)
- **Limits/notes:** Recommendations are hints, not model-fit guarantees. HTTP providers generally own allocation; local input estimates are not remote context reconfiguration.

#### F034. Per-session runtime continuity

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Models and provider connections

Accepted turns/settings atomically capture explicit model, mode, effort and connection/credential revisions for resume and fork.

- **Current entry:** Resume/fork; model/mode/effort changes
- **Configuration/defaults:** SQLite session-runtime version 1 record
- **Dependencies:** Memory transaction; connection identity
- **Implementation:** [packages/core/src/klaude_core/session_runtime.py](../packages/core/src/klaude_core/session_runtime.py#L1); [packages/core/src/klaude_core/memory.py:_store_session_runtime](../packages/core/src/klaude_core/memory.py#L627); [apps/cli/src/klaude_cli/main.py:_restore_session_runtime](../apps/cli/src/klaude_cli/main.py#L8785)
- **Limits/notes:** Restoration does not probe catalogs or change Default Chat. Stale credentials/definitions require a new explicit selection.

### Model Manager, serving and setup

#### F035. Downloaded Ollama inventory and loaded state

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Model Manager, serving and setup

Lists installed native Ollama models and current loaded models/resources with endpoint selection and bounded pages.

- **Current entry:** model-manager list/status; Model Manager
- **Configuration/defaults:** 100 rows per page; enabled Local native Ollama endpoints
- **Dependencies:** Ollama tags/ps/version
- **Implementation:** [packages/core/src/klaude_core/ollama_manager.py](../packages/core/src/klaude_core/ollama_manager.py#L1); [apps/cli/src/klaude_cli/model_manager.py](../apps/cli/src/klaude_cli/model_manager.py#L1)
- **Limits/notes:** Read-only inventory does not generate or load a model.

#### F036. Ollama pull and deletion

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Reviews exact server/model; streams pull progress and safely deletes eligible downloaded models after identity/digest rechecks.

- **Current entry:** model-manager pull/delete; Model Manager → pull/delete
- **Configuration/defaults:** 30min pull deadline; 30s read stall; explicit --yes bypasses interactive confirmation
- **Dependencies:** Native Ollama; shared owned worker
- **Implementation:** [packages/core/src/klaude_core/ollama_manager.py](../packages/core/src/klaude_core/ollama_manager.py#L1); [apps/cli/src/klaude_cli/model_manager_commands.py](../apps/cli/src/klaude_cli/model_manager_commands.py#L1)
- **Limits/notes:** Loaded/configured/default/session/Utility/Research/Vision models and normalized endpoint aliases are protected. Unknown mutation outcome requires Reload.

#### F037. Hugging Face GGUF discovery

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Model Manager, serving and setup

Searches Hub model metadata for GGUF candidates and model-manager workflows using existing private credential references.

- **Current entry:** model-manager search; manager search panel
- **Configuration/defaults:** HF credentials/base URL; bounded search parameters
- **Dependencies:** HF API; native Ollama server for eventual pulls
- **Implementation:** [packages/core/src/klaude_core/ollama_manager.py](../packages/core/src/klaude_core/ollama_manager.py#L1); [packages/web/src/klaude_web/huggingface.py](../packages/web/src/klaude_web/huggingface.py#L1)
- **Limits/notes:** Not a generic arbitrary weight downloader; private pulls depend on the Ollama server’s own access.

#### F038. Installed engine and dependency inspection

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Model Manager, serving and setup

Finds llama.cpp/vLLM executables and required installed Git/CMake/Ninja/compiler/CUDA/Python/uv tools; reads help/device support.

- **Current entry:** model-manager engines/dependencies; Dependencies
- **Configuration/defaults:** Explicit executable paths and engine recipe
- **Dependencies:** Installed binaries; bounded preflight worker
- **Implementation:** [packages/core/src/klaude_core/model_dependencies.py:inspection](../packages/core/src/klaude_core/model_dependencies.py#L97); [packages/core/src/klaude_core/managed_serving.py](../packages/core/src/klaude_core/managed_serving.py#L1); [apps/cli/src/klaude_cli/dependency_panel.py](../apps/cli/src/klaude_cli/dependency_panel.py#L1)
- **Limits/notes:** No automatic OS packages, drivers or engine installers during inspection; help success is not inference certification.

#### F039. Trusted local llama.cpp CPU/CUDA builds

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Builds exact committed local source snapshots into fresh retained private directories using fixed CMake/Ninja recipes.

- **Current entry:** model-manager build; Dependencies → CPU/CUDA recipe
- **Configuration/defaults:** profile cpu default; jobs2 (1–8); architectures/host_compiler optional; 30min deadline
- **Dependencies:** Trusted local Git source; CMake/Ninja/compiler; installed NVCC for CUDA
- **Implementation:** [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_dependencies.py:build](../packages/core/src/klaude_core/model_dependencies.py#L280); [packages/core/src/klaude_core/model_recipes.py:cuda](../packages/core/src/klaude_core/model_recipes.py#L35)
- **Limits/notes:** Uncommitted source excluded. Trusted source code executes outside an OS sandbox. No unsupported-host-compiler override, automatic drivers or weights downloads.

#### F040. Offline vLLM environment installation

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Reviews a complete local trusted binary wheel closure, resolves offline and installs exact hashes into a new private environment.

- **Current entry:** model-manager install-vllm; Dependencies → NVIDIA vLLM
- **Configuration/defaults:** Linux Python3.10–3.13; up to128 wheels /8GiB compressed /32GiB expanded; setup disk review
- **Dependencies:** Installed uv (explicit `UV` launcher hint or standard locations) and supported Python; trusted wheels; installed CUDA runtime requirements
- **Implementation:** [packages/core/src/klaude_core/model_recipes.py:wheels](../packages/core/src/klaude_core/model_recipes.py#L166); [packages/core/src/klaude_core/model_recipes.py:install](../packages/core/src/klaude_core/model_recipes.py#L278); [apps/cli/src/klaude_cli/dependency_panel.py](../apps/cli/src/klaude_cli/dependency_panel.py#L1)
- **Limits/notes:** Does not mutate app/system environments or fetch interpreters/packages. Engine checks do not prove GPU inference/model fit.

#### F041. Retained build inventory, logs and guarded removal

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Shows ready/failed/interrupted setups, bounded private logs, Serve handoff and reviewed retained-directory removal.

- **Current entry:** model-manager builds/logs/remove-build; Dependencies → Built/installed engines
- **Configuration/defaults:** At most8 retained setups; removal deadline120s; source/model directories retained
- **Dependencies:** Process/reference checks; revision locks; owned worker
- **Implementation:** [packages/core/src/klaude_core/model_dependencies.py:builds](../packages/core/src/klaude_core/model_dependencies.py#L222); [packages/core/src/klaude_core/model_setup_removal.py](../packages/core/src/klaude_core/model_setup_removal.py#L1); [apps/cli/src/klaude_cli/dependency_panel.py](../apps/cli/src/klaude_cli/dependency_panel.py#L1)
- **Limits/notes:** Removal protects live references and reports incomplete process inspection/partial cleanup. Only verified executable publication enables serving.

#### F042. Managed local llama.cpp and vLLM serving

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager / running servers

Starts an installed engine on loopback with reviewed model/context/CPU/GPU settings; verifies exact model ID, health and owned listener before registering a compatible endpoint.

- **Current entry:** model-manager serve; Model Manager → Serve models
- **Configuration/defaults:** LaunchSpec: port8080/context8192/threads4/gpu_layers0/GPU0/memory0.5; vLLM dtype/eager controls
- **Dependencies:** Installed engine; GGUF or complete safetensors bundle; owned helper
- **Implementation:** [packages/core/src/klaude_core/managed_serving.py:LaunchSpec](../packages/core/src/klaude_core/managed_serving.py#L148); [packages/core/src/klaude_core/managed_serving.py](../packages/core/src/klaude_core/managed_serving.py#L1); [apps/cli/src/klaude_cli/serving_jobs.py](../apps/cli/src/klaude_cli/serving_jobs.py#L1); [apps/cli/src/klaude_cli/model_manager.py](../apps/cli/src/klaude_cli/model_manager.py#L1)
- **Limits/notes:** CLI foreground; client exit stops owned servers. Two live servers per client, 32 retained server records. Ready does not automatically select model.

#### F043. Managed server stop, progress and private logs

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Uses leases/owned process groups and bounded redacted logs; preserves weights/roles/history and disables unchanged manager-created endpoint on cleanup.

- **Current entry:** Model Manager → server detail → Stop; model-manager servers/logs; Ctrl+C foreground
- **Configuration/defaults:** 256KiB log retention /16KiB tail; startup and cleanup bounds
- **Dependencies:** ServingJobs; helper process; connection revisions
- **Implementation:** [packages/core/src/klaude_core/managed_serving.py](../packages/core/src/klaude_core/managed_serving.py#L1); [apps/cli/src/klaude_cli/serving_jobs.py](../apps/cli/src/klaude_cli/serving_jobs.py#L1)
- **Limits/notes:** Not started, confirmed and unconfirmed remote cleanup are distinct. Browser tab lifetime must not accidentally become backend ownership.

#### F044. Reviewed adoption of existing servers

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Inspects same-account isolated Linux server identity/ports and takes ownership only after acknowledgement; failed adoption leaves original process running.

- **Current entry:** model-manager adopt PID MODEL_ID; local/SSH Adopt existing server
- **Configuration/defaults:** Exact PID/start/session/group/executable/argv/model/ports; 10s acknowledgement bound
- **Dependencies:** Linux process inspection; healthy owned listener; helper/tunnel
- **Implementation:** [packages/core/src/klaude_core/managed_serving.py](../packages/core/src/klaude_core/managed_serving.py#L1); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1); [packages/core/src/klaude_core/ssh_serving_program.py](../packages/core/src/klaude_core/ssh_serving_program.py#L1)
- **Limits/notes:** Original logs remain unattached; role/resource configuration is not rewritten. Competing owners/stale/reused identities are rejected.

#### F045. Saved SSH servers and diagnostics default

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Model Manager, serving and setup

Stores private SSH server definitions; separately selects This machine or a remote diagnostics default; test/inspect are nonmutating bounded checks.

- **Current entry:** model-manager ssh list/add/default/remove/test/inspect; Model Manager → Servers
- **Configuration/defaults:** config/model-servers.json; SSHServer fields; max32 definitions
- **Dependencies:** Installed OpenSSH; remote Python3; strict existing host-key/key or opt-in agent
- **Implementation:** [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32); [packages/core/src/klaude_core/ssh_servers.py:load](../packages/core/src/klaude_core/ssh_servers.py#L92); [packages/core/src/klaude_core/ssh_diagnostics.py](../packages/core/src/klaude_core/ssh_diagnostics.py#L1); [apps/cli/src/klaude_cli/ssh_panel.py](../apps/cli/src/klaude_cli/ssh_panel.py#L1)
- **Limits/notes:** Saving never connects or changes model roles/endpoints. Diagnostics process metadata does not certify ownership; GPU is Not checked until engine-specific probes.

#### F046. SSH host-key trust and public-key enrollment

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Discovers Ed25519 candidates, requires independent SHA256 fingerprint review before private pinning, and can enroll a reviewed existing public key.

- **Current entry:** model-manager ssh host-key/trust/enroll; Servers → Key setup
- **Configuration/defaults:** Existing absolute identity/.pub/known-hosts paths; opt-in agent
- **Dependencies:** OpenSSH keyscan; authenticated remote account for enrollment
- **Implementation:** [packages/core/src/klaude_core/ssh_setup.py](../packages/core/src/klaude_core/ssh_setup.py#L1); [packages/core/src/klaude_core/ssh_enrollment_program.py](../packages/core/src/klaude_core/ssh_enrollment_program.py#L1); [apps/cli/src/klaude_cli/ssh_panel.py](../apps/cli/src/klaude_cli/ssh_panel.py#L1)
- **Limits/notes:** No private key generation, password bootstrap or general remote shell UI; a scan alone is not proof of host authenticity.

#### F047. Remote llama.cpp CPU and GPU serving

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Runs reviewed installed remote GGUF engines through a leased remote supervisor and owned loopback SSH tunnel; explicit offload maps fresh device inventory.

- **Current entry:** model-manager serve --ssh-server ID; Servers → Serve model
- **Configuration/defaults:** Remote/tunnel ports; CPU threads/context; gpu_layers0–999; up to8 selected device indices
- **Dependencies:** Linux remote host; llama.cpp; OpenSSH/Python; verified model under remote directory
- **Implementation:** [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1); [packages/core/src/klaude_core/ssh_serving_program.py](../packages/core/src/klaude_core/ssh_serving_program.py#L1); [apps/cli/src/klaude_cli/ssh_panel.py](../apps/cli/src/klaude_cli/ssh_panel.py#L1)
- **Limits/notes:** GPU requests reject missing/reordered devices; no automatic CPU fallback. Lost channel disables local endpoint without fabricating remote cleanup receipt.

#### F048. Remote vLLM serving

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Model Manager, serving and setup

Reviews installed remote vLLM console launcher and safetensors bundle; probes exact environment CUDA capabilities and maps NVIDIA GPU UUIDs before startup.

- **Current entry:** Remote Serve → Engine vLLM; model-manager serve --engine vllm --ssh-server ID
- **Configuration/defaults:** dtype auto/half/bfloat16/float32; memory0.1–0.95; one sequence; TUI remote eager enabled initially, CLI false unless flag
- **Dependencies:** Trusted remote Linux venv/runtime; supported NVIDIA/CUDA; bundle revision checks
- **Implementation:** [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1); [packages/core/src/klaude_core/ssh_serving_program.py](../packages/core/src/klaude_core/ssh_serving_program.py#L1); [packages/core/src/klaude_core/managed_serving.py:LaunchSpec](../packages/core/src/klaude_core/managed_serving.py#L148); [apps/cli/src/klaude_cli/ssh_panel.py](../apps/cli/src/klaude_cli/ssh_panel.py#L1)
- **Limits/notes:** Offline and telemetry opt-outs are not an OS network sandbox. Physical LAN/other accelerator coverage is not certified by loopback SSH evidence.

### Sessions, memory and input

#### F049. Session creation, names and organization

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Sessions, memory and input

Persists conversations; creates new sessions, renames explicitly/manually or with optional Utility, lists/searches recent sessions and shows archive state.

- **Current entry:** /new; /rename NAME|--ai; /resume; /library Sessions; session-search
- **Configuration/defaults:** Private sessions.db; persistent names/archive flags
- **Dependencies:** Memory SQLite WAL; optional Utility
- **Implementation:** [packages/core/src/klaude_core/memory.py:Memory](../packages/core/src/klaude_core/memory.py#L170); [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089); [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1)
- **Limits/notes:** /clear clears presentation without being a permanent deletion operation. Search is bounded local session recall, not remote shared-account sync.

#### F050. Resume, fork and session continuity

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Sessions, memory and input

Loads saved public/private history and runtime selections; forks into a new conversation retaining existing state.

- **Current entry:** /resume [SESSION_ID]; /fork
- **Configuration/defaults:** Saved session model/mode/effort and private continuation data
- **Dependencies:** Memory; session runtime; current connection revisions
- **Implementation:** [packages/core/src/klaude_core/memory.py:load_session](../packages/core/src/klaude_core/memory.py#L1152); [packages/core/src/klaude_core/memory.py:fork_session](../packages/core/src/klaude_core/memory.py#L1249); [packages/core/src/klaude_core/session_runtime.py](../packages/core/src/klaude_core/session_runtime.py#L1)
- **Limits/notes:** No arbitrary historical-message editing/retry/branch-at-message workflow was found; fork is a session-level operation.

#### F051. Session archive, restore, permanent deletion and clear

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Sessions, memory and input

Supports reversible archive and explicit permanent deletion/clearing with confirmation and active ownership checks.

- **Current entry:** sessions archive/restore/delete/clear; Library → Sessions/Archive
- **Configuration/defaults:** Archived metadata; bounded session action requests
- **Dependencies:** SessionActionWriter; Memory transactions
- **Implementation:** [packages/core/src/klaude_core/memory.py:change_session_archive](../packages/core/src/klaude_core/memory.py#L1293); [packages/core/src/klaude_core/memory.py:delete_session](../packages/core/src/klaude_core/memory.py#L1268); [apps/cli/src/klaude_cli/session_actions.py](../apps/cli/src/klaude_cli/session_actions.py#L1); [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1)
- **Limits/notes:** Artifacts/knowledge have independent lifetimes; session deletion is not universal media/knowledge erasure.

#### F052. Session export and unsupported import boundary

**Status:** Partial · **WebUI:** ADAPT · **Suggested surface:** Conversation export / download

Exports visible conversation to Markdown in a reviewed/default path.

- **Current entry:** /export [PATH]
- **Configuration/defaults:** Export path; public history only
- **Dependencies:** Host filesystem; active session
- **Implementation:** [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1)
- **Limits/notes:** No public session import command/parser was found. MCP JSON import and document import are unrelated.

#### F053. Cross-client watching and writer ownership

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Sessions, memory and input

SQLite live state/events, client presence, per-client drafts/queue snapshots and renewable writer leases support watching and crash recovery.

- **Current entry:** Automatic session IO; /resume active session
- **Configuration/defaults:** 60s default writer lease; event cursors/revisions; private per-client records
- **Dependencies:** Memory/session IO coordinator; ordered writes
- **Implementation:** [packages/core/src/klaude_core/memory.py:acquire_session_lease](../packages/core/src/klaude_core/memory.py#L1025); [packages/core/src/klaude_core/memory.py:session_events_since](../packages/core/src/klaude_core/memory.py#L653); [apps/cli/src/klaude_cli/session_io.py:SessionIOCoordinator](../apps/cli/src/klaude_cli/session_io.py#L72)
- **Limits/notes:** Confirmed local same-store coordination, not a network account sync API. Event history is bounded/pruned; browser clients need ownership-safe cursor recovery.

#### F054. Queued follow-ups and steering

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Composer / pending messages

During active work, queues messages/session actions; can edit/delete pending entries or steer the active task; preserves draft attachments.

- **Current entry:** /queue [TEXT]; /steer TEXT; Alt+Up pending edit; Alt+\ steering
- **Configuration/defaults:** Client pending deque; queue snapshots for presence
- **Dependencies:** TUI turn worker; session ownership
- **Implementation:** [apps/cli/src/klaude_cli/main.py:_edit_previous_queued](../apps/cli/src/klaude_cli/main.py#L11804); [apps/cli/src/klaude_cli/main.py:_finish_queue_edit](../apps/cli/src/klaude_cli/main.py#L11834); [apps/cli/src/klaude_cli/session_io.py](../apps/cli/src/klaude_cli/session_io.py#L1)
- **Limits/notes:** Not a durable general task scheduler. No completed-message edit/retry controls were found.

#### F055. Text/file/folder attachments and inline references

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Sessions, memory and input

Composer /attach and @PATH collect bounded context; large pasted text uses a compact marker while preserving full submitted text.

- **Current entry:** /attach PATH; inline @PATH; bracketed paste
- **Configuration/defaults:** Text attachment bounds; marker threshold1000chars; workspace/path completion
- **Dependencies:** Host filesystem; attachment preparation
- **Implementation:** [packages/core/src/klaude_core/chat_images.py:text_attachments](../packages/core/src/klaude_core/chat_images.py#L103); [packages/core/src/klaude_core/chat_images.py:inline_paths](../packages/core/src/klaude_core/chat_images.py#L131); [apps/cli/src/klaude_cli/main.py:_insert_bracketed_paste](../apps/cli/src/klaude_cli/main.py#L11724)
- **Limits/notes:** Browser upload, host-file selection and text paste are different interactions. Collapsed paste markers are presentation; exact content must survive.

#### F056. Durable facts and automatic memory

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Memory / personal context

Maintains local facts with list/search/add/edit/forget; optional automatic capture uses bounded explicit fact patterns, sensitivity filtering and dedupe.

- **Current entry:** remember; memory commands; /memory; Settings → Memory
- **Configuration/defaults:** SQLite auto_memory_enabled default true; private memory.md; edit fact <=500chars
- **Dependencies:** Memory locks/storage; permission remember_fact
- **Implementation:** [packages/core/src/klaude_core/memory.py:auto_memory_enabled](../packages/core/src/klaude_core/memory.py#L468); [packages/core/src/klaude_core/memory.py:remember](../packages/core/src/klaude_core/memory.py#L374); [apps/cli/src/klaude_cli/memory_panel.py](../apps/cli/src/klaude_cli/memory_panel.py#L1); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1)
- **Limits/notes:** This is not an always-running AI memory extraction service. Turning capture off does not delete saved facts.

#### F057. Session recall tools

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Sessions, memory and input

Agent can search public prior conversation snippets and list recent sessions without reading private reasoning/image payloads.

- **Current entry:** search_sessions; list_recent_sessions; session-search
- **Configuration/defaults:** Bounded result counts and query lengths
- **Dependencies:** SQLite Memory; permission gates
- **Implementation:** [packages/core/src/klaude_core/memory.py:search_sessions](../packages/core/src/klaude_core/memory.py#L1441); [packages/core/src/klaude_core/memory.py:recent_sessions](../packages/core/src/klaude_core/memory.py#L1378); [apps/cli/src/klaude_cli/main.py:_build_agent](../apps/cli/src/klaude_cli/main.py#L7126)
- **Limits/notes:** Cross-session search is local and privacy-sensitive; browser exposure should preserve current public/private separation.

### Knowledge, search and research

#### F058. Named knowledge libraries and hybrid retrieval

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Knowledge, search and research

Indexes source chunks in LanceDB vectors and SQLite FTS5; routes library-specific queries, reciprocal-rank merges, confidence filters and optional reranking.

- **Current entry:** learn; query; libraries; query_knowledge; Library → Knowledge
- **Configuration/defaults:** models.embed; retrieval_k6; validation true; chunk target2400chars
- **Dependencies:** Ollama embeddings; LanceDB; FTS5; optional FlashRank
- **Implementation:** [packages/knowledge/src/klaude_knowledge/hybrid.py:Knowledge](../packages/knowledge/src/klaude_knowledge/hybrid.py#L128); [packages/knowledge/src/klaude_knowledge/store.py:KnowledgeStore](../packages/knowledge/src/klaude_knowledge/store.py#L41); [packages/knowledge/src/klaude_knowledge/chunker.py:chunk_markdown](../packages/knowledge/src/klaude_knowledge/chunker.py#L55); [packages/knowledge/src/klaude_knowledge/indexing.py](../packages/knowledge/src/klaude_knowledge/indexing.py#L1)
- **Limits/notes:** Use library publicly; collection remains compatibility/storage vocabulary. No existing browser API. Imported documents are not automatically indexed.

#### F059. URL/file learning and atomic indexing

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Knowledge, search and research

Learns explicit local text or fetched URL content, retains source/cache/checksum metadata and replaces owner snapshots atomically.

- **Current entry:** learn URL|FILE -l NAME; learn_source; Library → Knowledge → Learn
- **Configuration/defaults:** Library/source identity; snapshot_retention3
- **Dependencies:** KnowledgeIndexer; embedding model; fetch for URLs
- **Implementation:** [packages/knowledge/src/klaude_knowledge/indexing.py:KnowledgeIndexer](../packages/knowledge/src/klaude_knowledge/indexing.py#L38); [packages/knowledge/src/klaude_knowledge/hybrid.py:Knowledge](../packages/knowledge/src/klaude_knowledge/hybrid.py#L128); [apps/cli/src/klaude_cli/main.py:learn](../apps/cli/src/klaude_cli/main.py#L20607)
- **Limits/notes:** Failure/interruption must not publish a partially indexed source as current. Retained artifacts and indexed copies are distinct.

#### F060. Refreshable docs sources

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Knowledge, search and research

Installs llms.txt/linked docs or crawl-based sources, retains version manifests and explicitly updates selected/all/online seeds.

- **Current entry:** docs add/update/list; Library → Knowledge → Sources
- **Configuration/defaults:** Name/library; max pages; snapshot retention; online-docs file
- **Dependencies:** Docs installer; fetch/crawler; atomic knowledge indexing
- **Implementation:** [packages/knowledge/src/klaude_knowledge/docs.py:install_docs_source](../packages/knowledge/src/klaude_knowledge/docs.py#L274); [packages/knowledge/src/klaude_knowledge/docs.py:update_docs_source](../packages/knowledge/src/klaude_knowledge/docs.py#L469); [packages/knowledge/src/klaude_knowledge/docs.py:recover_docs_sources](../packages/knowledge/src/klaude_knowledge/docs.py#L229)
- **Limits/notes:** Online seeds are inputs, not preinstalled knowledge. Source refresh does not require model-generated answers.

#### F061. Polite bounded website crawling

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Knowledge, search and research

Traverses same-domain pages with depth/page/include/exclude controls, robots/sitemaps/delays/retry metadata and incremental source installation.

- **Current entry:** crawl; crawl_site; docs crawl sources
- **Configuration/defaults:** depth2; pages50; delay2–5s; robots true; user_agent
- **Dependencies:** Public URL fetch; robots; knowledge embedding for ingestion
- **Implementation:** [packages/web/src/klaude_web/crawler.py:crawl_site](../packages/web/src/klaude_web/crawler.py#L383); [packages/knowledge/src/klaude_knowledge/docs.py:install_crawl_source](../packages/knowledge/src/klaude_knowledge/docs.py#L381)
- **Limits/notes:** No arbitrary headless browser automation UI. Partial crawl failures must remain visible.

#### F062. Web search routing and providers

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Search settings / sources

Quality/legacy routing merges/ranks relevant results across configured free/keyed providers with explicit provider selection, fallback order and cache.

- **Current entry:** search; web_search; Settings → Search
- **Configuration/defaults:** auto plus brave/ddgs/searxng/brave_api/google/parallel/tavily/exa/firecrawl; results12 default settings
- **Dependencies:** Provider services; keys where required; billing policy
- **Implementation:** [packages/web/src/klaude_web/providers.py:quality_search](../packages/web/src/klaude_web/providers.py#L3868); [packages/web/src/klaude_web/facade.py:Web](../packages/web/src/klaude_web/facade.py#L49); [packages/core/src/klaude_core/search_settings.py](../packages/core/src/klaude_core/search_settings.py#L1)
- **Limits/notes:** 9 actual providers; Google here uses Gemini search integration, not an invented Google PSE setting. No unconditional search for every chat answer.

#### F063. Search cost, relevance and location policy

**Status:** Implemented · **WebUI:** OPTIONAL · **Suggested surface:** Advanced Search / privacy / diagnostics

Tracks provider availability, quotas/cooldowns/retries, entity resolution, candidate versus verified evidence and bounded location hints.

- **Current entry:** Automatic search planning; config-only advanced web settings
- **Configuration/defaults:** web.billing/search/providers/verification; entity cache; location network opt-in false
- **Dependencies:** Search provider metadata; runtime location; optional Wikimedia
- **Implementation:** [packages/web/src/klaude_web/providers.py](../packages/web/src/klaude_web/providers.py#L1); [packages/core/src/klaude_core/entities.py](../packages/core/src/klaude_core/entities.py#L1); [packages/core/src/klaude_core/config.py:WebSearchConfig](../packages/core/src/klaude_core/config.py#L384)
- **Limits/notes:** Local request limits are estimates, not authoritative provider billing. Runtime country hint is not permission to send exact location.

#### F064. Local-first URL extraction and HTTP diagnostics

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Knowledge, search and research

Direct fetch with content extraction, Crawl4AI/local fallback and opt-in/configured Exa; HTTP probe inspects URL status/headers without arbitrary tools.

- **Current entry:** fetch_url; http_probe; Settings → Search → URL Fetch
- **Configuration/defaults:** local default; timeout30s;2MB download;20k chars;5redirects;24h cache
- **Dependencies:** HTTPX; trafilatura; optional Crawl4AI/Exa
- **Implementation:** [packages/web/src/klaude_web/fetch.py:fetch_page_detailed](../packages/web/src/klaude_web/fetch.py#L605); [packages/web/src/klaude_web/fetch.py:probe_public_url](../packages/web/src/klaude_web/fetch.py#L397); [packages/core/src/klaude_core/fetch_settings.py](../packages/core/src/klaude_core/fetch_settings.py#L1); [packages/web/src/klaude_web/facade.py](../packages/web/src/klaude_web/facade.py#L1)
- **Limits/notes:** Public URL/DNS/redirect guards reject private destinations; configured service endpoints are separate trusted inputs. Probe supports bounded HEAD/GET.

#### F065. Code/documentation search and Hugging Face tools

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Knowledge, search and research

Provides programming-oriented search and Hub models/datasets/Spaces metadata/details/README retrieval.

- **Current entry:** code-search; huggingface-search/details/readme; corresponding tools
- **Configuration/defaults:** HF token/base URL; bounded results/revision/file controls
- **Dependencies:** Web facade; HF API/README endpoints
- **Implementation:** [packages/web/src/klaude_web/facade.py](../packages/web/src/klaude_web/facade.py#L1); [packages/web/src/klaude_web/huggingface.py](../packages/web/src/klaude_web/huggingface.py#L1); [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089)
- **Limits/notes:** Hub metadata discovery is not model installation. Code search is web retrieval, not the workspace grep tool.

#### F066. Time and weather tools

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Knowledge, search and research

Provides current local/zone time and weather lookup through purpose-specific bounded tools.

- **Current entry:** current_time; weather_lookup
- **Configuration/defaults:** Tool availability and permission; validated location/time arguments
- **Dependencies:** Host date/time; configured implementation weather service
- **Implementation:** [apps/cli/src/klaude_cli/main.py:_build_agent](../apps/cli/src/klaude_cli/main.py#L7126); [packages/core/src/klaude_core/dates.py](../packages/core/src/klaude_core/dates.py#L1)
- **Limits/notes:** These are built-in tools, not a proposed dashboard widget or calendar feature.

#### F067. Evidence sources and resumable research receipts

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Backend; source/citation inspector

Separates search-result leads from fetched sources; preserves bounded provenance/receipts and honestly re-fetches required evidence on continuation.

- **Current entry:** Automatic tool/source use; research/session recovery
- **Configuration/defaults:** Source IDs, bounded excerpts and durable receipt metadata
- **Dependencies:** SourceRegistry; source_use; research_receipts
- **Implementation:** [packages/web/src/klaude_web/sources.py:SourceRegistry](../packages/web/src/klaude_web/sources.py#L54); [packages/core/src/klaude_core/source_use.py](../packages/core/src/klaude_core/source_use.py#L1); [packages/core/src/klaude_core/research_receipts.py](../packages/core/src/klaude_core/research_receipts.py#L1)
- **Limits/notes:** Audit metadata is not replayable tool output; images and fetched content need actual availability checks.

#### F068. Bounded Deep Research jobs

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Research workspace

Runs bounded search/extract/synthesis rounds using selected Research/default chat connection and saves complete/partial reports and provenance.

- **Current entry:** research run; Library → Research → New research
- **Configuration/defaults:** ResearchDefaults:2048output/8192context/30sextract/parallel2/300stimeout/rounds2/queries6/sources8
- **Dependencies:** Search/fetch; selected runtime; owned worker; ArtifactStore
- **Implementation:** [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:run_research](../packages/core/src/klaude_core/research.py#L376); [apps/cli/src/klaude_cli/research_panel.py](../apps/cli/src/klaude_cli/research_panel.py#L1)
- **Limits/notes:** Not the same as an unrestricted coding Agent turn; no silent model fallback; completed/partial/error/cancel outcomes distinct.

#### F069. Research queue, resume and report lifecycle

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Knowledge, search and research

Queues metadata only (max10), starts explicitly, resumes receipt URLs by re-fetching and retains reports with normal Library lifecycle.

- **Current entry:** research list/resume; research run --queue; Library Research
- **Configuration/defaults:** Accepted model/provider/credential revisions; explicit format/round overrides
- **Dependencies:** ResearchStore; artifact storage; worker ownership
- **Implementation:** [packages/core/src/klaude_core/research.py:ResearchStore](../packages/core/src/klaude_core/research.py#L106); [apps/cli/src/klaude_cli/research_commands.py](../apps/cli/src/klaude_cli/research_commands.py#L1); [apps/cli/src/klaude_cli/research_panel.py](../apps/cli/src/klaude_cli/research_panel.py#L1)
- **Limits/notes:** CLI complete0/partial2/error1/Ctrl+C130. Queue is not an unattended daemon; saved metadata does not substitute for retrieved evidence.

#### F102. Explicitly learn a saved research report

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Research report / Learn action

Loads an exact stored research artifact revision and indexes its text into the chosen knowledge library only after explicit action.

- **Current entry:** Library → research report → Learn report
- **Configuration/defaults:** Existing Knowledge library/source size and embedding bounds
- **Dependencies:** ArtifactStore; Library Knowledge worker; embedding model
- **Implementation:** [apps/cli/src/klaude_cli/library_knowledge.py:run_operation](../apps/cli/src/klaude_cli/library_knowledge.py#L141); [apps/cli/src/klaude_cli/research_panel.py](../apps/cli/src/klaude_cli/research_panel.py#L1)
- **Limits/notes:** Saving a Research report does not learn it automatically; explicit learning creates independent knowledge content.

#### F103. Declared advanced controls with unverified active effect

**Status:** Partial · **WebUI:** OPTIONAL · **Suggested surface:** Advanced settings only after consumer verification

Several advanced TOML fields are declared/loaded without a located production consumer; declarations alone do not establish working feature switches.

- **Current entry:** Config-only web search/location/verification fields; legacy searxng_secret
- **Configuration/defaults:** Specific rows marked Partial in §3; max_pages_per_domain does have an active consumer
- **Dependencies:** Config schema and intended search policy
- **Implementation:** [packages/core/src/klaude_core/config.py:load_config](../packages/core/src/klaude_core/config.py#L730); [packages/web/src/klaude_web/providers.py](../packages/web/src/klaude_web/providers.py#L1); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1)
- **Limits/notes:** Examples: skip_unconfigured_providers, fallback_on_quota/unavailable, return_unrelated_results, send_country_for_local_intent_only and several web.verification keys. No implementation was changed during this audit.

### Skills and MCP integrations

#### F070. Installed Skills and model-led reading

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Skills and MCP integrations

Lists enabled installed skill metadata; read_skill loads an enabled package’s SKILL.md or authorized supporting file on demand with bounded catalog/guidance.

- **Current entry:** skills; /skills; Settings → Skills → Manage; read_skill
- **Configuration/defaults:** Enabled manifest flag; bounded64catalog/65536byte skill text
- **Dependencies:** InstalledSkillReader; skill manifests; tool gate
- **Implementation:** [apps/cli/src/klaude_cli/skill_runtime.py:InstalledSkillReader](../apps/cli/src/klaude_cli/skill_runtime.py#L30); [packages/knowledge/src/klaude_knowledge/skills.py:list_installed_skills](../packages/knowledge/src/klaude_knowledge/skills.py#L256); [apps/cli/src/klaude_cli/main.py:_build_agent](../apps/cli/src/klaude_cli/main.py#L7126)
- **Limits/notes:** Installation does not grant shell/write permissions or execute skill code. Guidance cannot override user/scoped permissions.

#### F071. Skills discovery and verified remote installation

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Skills and MCP integrations

Searches SkillsMP or provisional skills.sh, resolves original GitHub source/revision, reviews trust/source/package bounds and imports indexed copies.

- **Current entry:** Settings → Skills → Search/Install
- **Configuration/defaults:** Source skillsmp/skills.sh; stars/recent where supported; page1–10,20results
- **Dependencies:** Catalog HTTP; public GitHub; knowledge index/embeddings
- **Implementation:** [packages/core/src/klaude_core/skill_catalog.py](../packages/core/src/klaude_core/skill_catalog.py#L1); [apps/cli/src/klaude_cli/skill_discovery.py](../apps/cli/src/klaude_cli/skill_discovery.py#L1); [packages/knowledge/src/klaude_knowledge/skill_management.py:import_remote_skill](../packages/knowledge/src/klaude_knowledge/skill_management.py#L105)
- **Limits/notes:** Repository stars are a metric, not trust/security. skills.sh is explicitly provisional; unavailable upstreams must be shown honestly.

#### F072. Skills local import and drop inbox

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Skills and MCP integrations

Imports ZIP/folder/text packages with safe paths and atomic indexing; watches bounded settled files in a drop inbox without executing them.

- **Current entry:** import-skill; Settings → Skills → Import; inbox detector
- **Configuration/defaults:** Name/library/overwrite;64MiB drop limit;2s settle default
- **Dependencies:** Skill installer; indexer; filesystem
- **Implementation:** [packages/knowledge/src/klaude_knowledge/skills.py:install_skill_package](../packages/knowledge/src/klaude_knowledge/skills.py#L164); [packages/knowledge/src/klaude_knowledge/skill_management.py](../packages/knowledge/src/klaude_knowledge/skill_management.py#L1); [packages/core/src/klaude_core/skill_drop.py:SkillDropDetector](../packages/core/src/klaude_core/skill_drop.py#L20)
- **Limits/notes:** Folders/scripts may be stored/indexed as text; no package installer execution is implied.

#### F073. Skills manage, updates and deletion

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Skills and MCP integrations

Filter All/Enabled/Disabled, Reload, review verified GitHub updates individually/all, enable/disable and delete with identity checks.

- **Current entry:** Settings → Skills → Manage
- **Configuration/defaults:** Installed manifest enabled/source/revision/library; transient query/filter
- **Dependencies:** SkillActionWriter; manifests/index snapshots
- **Implementation:** [apps/cli/src/klaude_cli/skills_panel.py](../apps/cli/src/klaude_cli/skills_panel.py#L1); [apps/cli/src/klaude_cli/skill_actions.py](../apps/cli/src/klaude_cli/skill_actions.py#L1); [packages/core/src/klaude_core/skill_catalog.py:check_github_skill_update](../packages/core/src/klaude_core/skill_catalog.py#L482)
- **Limits/notes:** Only verified sources support update checks; local ZIP/imports can lack descriptions. Check/current status is informational; errors/warnings/success distinct.

#### F074. External MCP server connections

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Skills and MCP integrations

Supports stdio and remote Streamable HTTP servers, discovers/namespaces schemas, enables/disables servers and invokes tools through shared permissions.

- **Current entry:** mcp list/add/info/enable/disable/refresh/remove; /mcp; Settings → MCPs
- **Configuration/defaults:** data/mcp-servers.json MCPServerConfig; default new server setup may be disabled pending review
- **Dependencies:** MCP SDK; local command runtime or HTTP service
- **Implementation:** [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93); [packages/core/src/klaude_core/mcp_client.py:MCPClientManager](../packages/core/src/klaude_core/mcp_client.py#L778)
- **Limits/notes:** No SSE transport enum found; streamable-http aliases normalize to http. Remote HTTPS required except exact localhost HTTP. MCP tools are not built-in tool toggles.

#### F075. MCP Registry search and reviewed installation

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Skills and MCP integrations

Searches official registry, filters/sorts/detail-inspects entries, resolves supported pinned package/HTTP setup and stores reviewed disabled definitions.

- **Current entry:** mcp search/info/install; Settings → MCPs → Search
- **Configuration/defaults:** Registry cache1h/64entries; stale fallback7days; package inputs; repository stars detail lookup
- **Dependencies:** Official registry; npx/uvx or declared package runner where applicable
- **Implementation:** [packages/core/src/klaude_core/mcp_catalog.py:MCPCatalogClient](../packages/core/src/klaude_core/mcp_catalog.py#L427); [packages/core/src/klaude_core/mcp_catalog.py:install_plans](../packages/core/src/klaude_core/mcp_catalog.py#L337); [apps/cli/src/klaude_cli/mcp_search_panel.py](../apps/cli/src/klaude_cli/mcp_search_panel.py#L1); [apps/cli/src/klaude_cli/mcp_management.py](../apps/cli/src/klaude_cli/mcp_management.py#L1)
- **Limits/notes:** Installing/connecting trusted local servers can execute third-party code. Metadata stars and registry presence are not a safety certificate.

#### F076. MCP import, maintenance and updates

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Skills and MCP integrations

Imports standard/VS Code/OpenCode-compatible MCP JSON, previews changes, manages enabled/filter/reload/update/remove workflows.

- **Current entry:** mcp import; Settings → MCPs → Import/Manage
- **Configuration/defaults:** Config alias mcpServers; scoped definitions/source metadata
- **Dependencies:** MCPRegistry; serialized mutation writer
- **Implementation:** [packages/core/src/klaude_core/mcp_client.py:MCPRegistry](../packages/core/src/klaude_core/mcp_client.py#L516); [apps/cli/src/klaude_cli/mcp_mutations.py](../apps/cli/src/klaude_cli/mcp_mutations.py#L1); [apps/cli/src/klaude_cli/mcp_updates.py](../apps/cli/src/klaude_cli/mcp_updates.py#L1); [apps/cli/src/klaude_cli/mcp_management.py](../apps/cli/src/klaude_cli/mcp_management.py#L1)
- **Limits/notes:** Changed updates remain disabled for review; no blind definition rollback if effects are unconfirmed.

#### F077. MCP secrets and remote OAuth

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Skills and MCP integrations

Environment-backed secrets/static headers and remote OAuth login/status/logout with private token storage and loopback callback.

- **Current entry:** mcp secret; mcp auth login/status/logout; server authentication screens
- **Configuration/defaults:** oauth=false; scope/metadata URL; callback127.0.0.1:8765/callback; env/header refs
- **Dependencies:** MCP OAuth discovery; browser; local callback server
- **Implementation:** [packages/core/src/klaude_core/mcp_client.py:MCPTokenStorage](../packages/core/src/klaude_core/mcp_client.py#L247); [packages/core/src/klaude_core/mcp_client.py:MCP_OAUTH_REDIRECT_URI](../packages/core/src/klaude_core/mcp_client.py#L56); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1)
- **Limits/notes:** OAuth callback HTTP server is not a WebUI server. Browser-hosted redirects, session binding and callback ownership need adaptation; do not expose tokens.

#### F078. Klaude web and knowledge MCP servers

**Status:** Implemented · **WebUI:** OPTIONAL · **Suggested surface:** Integrations / developer setup

Exposes reusable web/search/fetch/Hub and knowledge/query/learn/docs/skills tools to external MCP clients; separate from full chat agent.

- **Current entry:** Installed klaude-web-mcp; klaude-knowledge-mcp entrypoints
- **Configuration/defaults:** KLAUDE_MCP_ALLOW_WRITES opt-in; KLAUDE_MCP_WORKSPACE; library/collection compatibility
- **Dependencies:** MCP SDK; web/knowledge core services
- **Implementation:** [packages/web/src/klaude_web/mcp_server.py](../packages/web/src/klaude_web/mcp_server.py#L1); [packages/knowledge/src/klaude_knowledge/mcp_server.py](../packages/knowledge/src/klaude_knowledge/mcp_server.py#L1)
- **Limits/notes:** Knowledge ingestion writes are gated; browser agent orchestration cannot be obtained merely by wrapping these restricted MCP surfaces.

### Library artifacts and media

#### F079. Unified Library navigation

**Status:** Implemented · **WebUI:** REQUIRED · **Suggested surface:** Library artifacts and media

Durable-information workspace separates Sessions, Knowledge, Documents, Research, Media and Archive while retaining each subsystem’s meaning.

- **Current entry:** /library [VIEW]; Library panel; library commands
- **Configuration/defaults:** VIEWS constant; view filters/sort/query state
- **Dependencies:** Sessions; knowledge; ArtifactStore; research
- **Implementation:** [apps/cli/src/klaude_cli/library_workspace.py:VIEWS](../apps/cli/src/klaude_cli/library_workspace.py#L19); [apps/cli/src/klaude_cli/library_workspace.py:LibraryWorkspace](../apps/cli/src/klaude_cli/library_workspace.py#L32)
- **Limits/notes:** Stored ≠ indexed; imported ≠ learned; archived ≠ deleted. No separate full Gallery/canvas workspace exists.

#### F080. Private document/media import and browsing

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Library / upload / artifact detail

Copies regular non-symlink files into private storage; lists searchable metadata with bounded pages, explicit type and archive filters.

- **Current entry:** library import/list/info; Library → Documents/Media
- **Configuration/defaults:** 32MiB import cap;100record pages; name/tag/MIME/origin search
- **Dependencies:** ArtifactStore; owner-private filesystem/SQLite
- **Implementation:** [packages/core/src/klaude_core/library_artifacts.py:ArtifactStore](../packages/core/src/klaude_core/library_artifacts.py#L90); [apps/cli/src/klaude_cli/library_commands.py](../apps/cli/src/klaude_cli/library_commands.py#L1); [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1)
- **Limits/notes:** Does not index or learn automatically. Supported storage MIME does not imply every format can be analyzed by Vision.

#### F081. Artifact preview, host open and export

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Library artifacts and media

Checks revisions/checksums; bounded text/metadata previews; opens explicit private temporary host copies and exports new workspace files without overwrite.

- **Current entry:** Library artifact detail → Preview/Open/Export; library export
- **Configuration/defaults:** Safe destination; checksum/revision; preview bounds
- **Dependencies:** Host opener; workspace jail; artifact byte store
- **Implementation:** [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1); [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1)
- **Limits/notes:** Browser download/preview must replace host desktop launch where appropriate; exported/opened copies have independent lifetimes.

#### F082. Manual tags, archive, restore and delete

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Library artifacts and media

Applies manual tags, reversible archive and confirmed permanent deletion of archived records with content/revision checks.

- **Current entry:** library tags/archive/restore/delete; artifact detail/Archive
- **Configuration/defaults:** Up to20tags;1–40chars each; archived prerequisite for delete
- **Dependencies:** ArtifactStore; serialized lifecycle actions
- **Implementation:** [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1); [apps/cli/src/klaude_cli/session_actions.py](../apps/cli/src/klaude_cli/session_actions.py#L1); [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1)
- **Limits/notes:** Optional AI suggestions are a separate explicit consumer (F098); manual tags remain independent. Deleting a stored copy does not delete original/exports or independently learned knowledge.

#### F083. Reviewed Media image analysis

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Library artifacts and media

Reviews exact pixels/endpoints/models/context/output and invokes Vision with declared support, cancellation and eligible explicit fallbacks; results stay private/unsaved.

- **Current entry:** library analyze MEDIA_ID QUESTION; Media → Analyze image
- **Configuration/defaults:** Vision off by default;4096context/512output; PNG/JPEG≤8MiB/4MP/4096side;90s generation
- **Dependencies:** Configured supported Vision model; exact image revision; owned worker
- **Implementation:** [packages/core/src/klaude_core/vision.py](../packages/core/src/klaude_core/vision.py#L1); [apps/cli/src/klaude_cli/vision_panel.py](../apps/cli/src/klaude_cli/vision_panel.py#L1); [packages/core/src/klaude_core/image_content.py](../packages/core/src/klaude_core/image_content.py#L1); [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1)
- **Limits/notes:** HTTP context is conservative local admission, not server allocation. Thinking-required models unavailable to thinking-disabled Media consumer; no tools/history/indexing/tag mutations. Forms load unknown role metadata without claiming disabled state; host-written redacted failures wrap visibly and retain input for explicit retry.

#### F084. Chat and one-shot image attachments

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Library artifacts and media

Supplies actual immutable PNG/JPEG snapshots to explicitly selected image-capable chat model; saved refs support follow-ups/resume after original source deletion.

- **Current entry:** /attach PATH; inline @PATH; ask inline image path
- **Configuration/defaults:** Vision enabled; max2distinct images per request; same pixel limits; chat runtime budget
- **Dependencies:** Fresh exact-model image evidence; private Media snapshots; provider image adapter
- **Implementation:** [packages/core/src/klaude_core/chat_images.py:ChatImages](../packages/core/src/klaude_core/chat_images.py#L145); [packages/core/src/klaude_core/chat_image_support.py](../packages/core/src/klaude_core/chat_image_support.py#L1); [packages/core/src/klaude_core/openai_images.py](../packages/core/src/klaude_core/openai_images.py#L1); [packages/core/src/klaude_core/gemini_images.py](../packages/core/src/klaude_core/gemini_images.py#L1); [packages/core/src/klaude_core/openrouter_images.py](../packages/core/src/klaude_core/openrouter_images.py#L1)
- **Limits/notes:** No silent switch to Vision model/fallbacks in chat. Endpoint/credential changes require reattachment; deleted/corrupt bytes unavailable, recaps not visual evidence.

#### F085. Vision provider capability verification

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Library artifacts and media

Shared inspector checks native Ollama, compatible/native-peer, Anthropic, exact OpenAI/Gemini profiles and OpenRouter modalities before pixels are sent.

- **Current entry:** AI Defaults → Vision selection; analysis/attachment preparation
- **Configuration/defaults:** Exact IDs/root/auth scope;30s metadata cache; provider context/output limits
- **Dependencies:** Model catalog/show endpoints; checked-in reviewed profiles
- **Implementation:** [packages/core/src/klaude_core/vision.py:inspect_model](../packages/core/src/klaude_core/vision.py#L155); [packages/core/src/klaude_core/image_profiles.py](../packages/core/src/klaude_core/image_profiles.py#L1); [packages/core/src/klaude_core/image_content.py](../packages/core/src/klaude_core/image_content.py#L1); [packages/core/src/klaude_core/chat_image_support.py](../packages/core/src/klaude_core/chat_image_support.py#L1)
- **Limits/notes:** Models may be tools-capable but image-unknown or vice versa. Current code profiles are a whitelist, not general provider/model-name inference.

#### F086. Local image-service settings

**Status:** Partial · **WebUI:** ADAPT · **Suggested surface:** Library artifacts and media

Connects an already running stable-diffusion.cpp native image API, tests capabilities without generation, saves explicit enabled endpoint and pinned loaded model.

- **Current entry:** library image-service; AI Defaults → Image generation; Media → Generate image settings
- **Configuration/defaults:** config/image-generation.json: enabled false, endpoint/model/revision empty
- **Dependencies:** Existing unauthenticated trusted local/LAN native service
- **Implementation:** [packages/core/src/klaude_core/image_generation.py:read](../packages/core/src/klaude_core/image_generation.py#L52); [packages/core/src/klaude_core/image_generation.py:inspect](../packages/core/src/klaude_core/image_generation.py#L115); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1)
- **Limits/notes:** Protocol/CLI/TUI fixture coverage exists; no real diffusion inference validated in current prior report. No authentication, engine install, workflow import or automatic model load.

#### F087. Reviewed image generation and provenance

**Status:** Partial · **WebUI:** ADAPT · **Suggested surface:** Library artifacts and media

Reviews prompt/model/dimensions/steps/seed; submits one native image job, polls, imports one bounded PNG and records provenance atomically.

- **Current entry:** library generate; Media → Generate image
- **Configuration/defaults:** 512×512,20steps,seed-1;256–1024multiples64;steps1–50;prompt1–2000;300s generation
- **Dependencies:** Enabled pinned service; owned worker; ArtifactStore
- **Implementation:** [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [packages/core/src/klaude_core/image_generation.py:run](../packages/core/src/klaude_core/image_generation.py#L274); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1); [apps/cli/src/klaude_cli/generation_commands.py](../apps/cli/src/klaude_cli/generation_commands.py#L1)
- **Limits/notes:** Actual native CPU/CUDA generation, CLI/TUI review and exact export passed for the tested profiles. Broader hardware/quality certification remains separate. Not editing/inpainting/layers/upscaling/batch generation; no automatic request retry.

#### F088. Generation status, scoped cancel and result recovery

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Library artifacts and media / image jobs

Retains private job receipts; local status reads, supported per-job cancellation and artifact receipt recovery avoid duplicate publishes after late completion.

- **Current entry:** library generation-jobs; generation-status --refresh/--cancel/--recover/--forget; Media → Image jobs; active generation Cancel
- **Configuration/defaults:** data/image-generation/UUID.json; unique artifact job ID; 100-record pages, 1000-receipt scan; explicit abandonment required to forget unknown/active tracking
- **Dependencies:** Native service cancellation support; saved job record
- **Implementation:** [packages/core/src/klaude_core/image_generation.py:cancel](../packages/core/src/klaude_core/image_generation.py#L231); [packages/core/src/klaude_core/image_generation.py:publish](../packages/core/src/klaude_core/image_generation.py#L225); [apps/cli/src/klaude_cli/generation_commands.py](../apps/cli/src/klaude_cli/generation_commands.py#L1)
- **Limits/notes:** No service-global stop fallback; unknown remote effects remain unknown after lost process/channel. Queued-only native cancellation is reviewed honestly. Explicit completed-output recovery never resubmits. Receipt removal retains images and server work; unknown tracking requires additional abandonment consent. Final pixels live separately from job metadata. [Live CLI/TUI evidence](s6-completion-validation.md).

### Interface, diagnostics and maintenance

#### F089. Structured settings navigation

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Settings and dialogs

Shared PanelPage/Row/Action/State gives typed navigation, info/toggle/action/table sections, search/filter, status tones, review focus and background result scoping.

- **Current entry:** /settings [CATEGORY]; setting subpages
- **Configuration/defaults:** Current categories: Appearance, Models & AI, Agent, Advanced
- **Dependencies:** CLI settings adapters; settings writers; owned workers
- **Implementation:** [apps/cli/src/klaude_cli/settings_panel.py:PanelPage](../apps/cli/src/klaude_cli/settings_panel.py#L122); [apps/cli/src/klaude_cli/settings_panel.py:PanelState](../apps/cli/src/klaude_cli/settings_panel.py#L148); [apps/cli/src/klaude_cli/main.py:_settings_home_page](../apps/cli/src/klaude_cli/main.py#L13537)
- **Limits/notes:** Logical action/state semantics reusable; prompt_toolkit rendering, terminal cell measurement and picker keys are terminal-specific.

#### F090. Atomic settings and credential revisions

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Interface, diagnostics and maintenance

Private atomic field-scoped saves, file locks, expected revisions and ordered writer acknowledgements protect independent updates and reject stale results.

- **Current entry:** Automatic on settings/model/MCP/skill writes
- **Configuration/defaults:** TOML/env/JSON/SQLite stores; secret tombstone/revision sidecar
- **Dependencies:** settings_store; per-subsystem writers; fcntl
- **Implementation:** [packages/core/src/klaude_core/settings_store.py](../packages/core/src/klaude_core/settings_store.py#L1); [apps/cli/src/klaude_cli/settings_writer.py](../apps/cli/src/klaude_cli/settings_writer.py#L1); [packages/core/src/klaude_core/config.py:save_provider_secret](../packages/core/src/klaude_core/config.py#L204)
- **Limits/notes:** No unified browser settings service/schema yet. A saved status requires an acknowledgement; errors must not appear as successful persistence.

#### F091. Command help, completion and discoverability

**Status:** Implemented · **WebUI:** ADAPT · **Suggested surface:** Interface, diagnostics and maintenance

One registry synchronizes slash help, focused help, suggestions and deterministic reference text; Typer supplies CLI commands/options.

- **Current entry:** /; /help; /keybinds; --help; list_commands
- **Configuration/defaults:** CHAT_COMMANDS; parameter help; hidden compatibility exits
- **Dependencies:** CLI command registry; path/model completion
- **Implementation:** [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089); [apps/cli/src/klaude_cli/main.py:format_chat_keybind_reference](../apps/cli/src/klaude_cli/main.py#L3956)
- **Limits/notes:** Browser command palette can reuse logical registry; do not copy terminal escape sequences or undocumented synthetic commands.

#### F092. Terminal appearance and previews

**Status:** Implemented · **WebUI:** TUI-ONLY · **Suggested surface:** Exclude from browser settings

Terminal interface/syntax themes, input geometry/border, divider pattern/colors and spinner/custom frames with previews and scoped reset.

- **Current entry:** Settings → Appearance; /theme
- **Configuration/defaults:** appearance.json theme/input_field/divider/spinner
- **Dependencies:** prompt_toolkit/Rich/Pygments; terminal geometry
- **Implementation:** [apps/cli/src/klaude_cli/main.py:TUIAppearance](../apps/cli/src/klaude_cli/main.py#L1559); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1)
- **Limits/notes:** Browser appearance is separate planned design; terminal settings must remain intact for TUI users.

#### F093. Terminal composer and rendering controls

**Status:** Implemented · **WebUI:** TUI-ONLY · **Suggested surface:** Exclude terminal mechanics

Vim editing mode, terminal key protocols/completion, persistent scrollback, repaint/debug animation and large-paste markers.

- **Current entry:** /vim; /refresh; /debug_label; terminal keys
- **Configuration/defaults:** composer_mode standard/vim; animation/render constants
- **Dependencies:** Terminal emulator; prompt_toolkit
- **Implementation:** [apps/cli/src/klaude_cli/main.py:PersistentChatTUI](../apps/cli/src/klaude_cli/main.py#L9144); [apps/cli/src/klaude_cli/terminal_surface.py](../apps/cli/src/klaude_cli/terminal_surface.py#L1)
- **Limits/notes:** Underlying messages/queue/Cancel remain browser-relevant; only terminal mechanics are excluded.

#### F094. Diagnostics, evaluation hooks and packaging

**Status:** Implemented · **WebUI:** INTERNAL · **Suggested surface:** Diagnostics selectively; development tooling

Developer test/evaluation interfaces, behavior runner, quality/package/release-candidate verification and setup scripts exist outside normal chat UX.

- **Current entry:** doctor/status; scripts/evaluate_agent_behavior.py; make check/package-smoke; CI
- **Configuration/defaults:** Evaluation harness controls; frozen workspace dependencies; release inputs
- **Dependencies:** Python>=3.11; uv; GitHub Actions; optional tool runtimes
- **Implementation:** [packages/core/src/klaude_core/evaluation.py](../packages/core/src/klaude_core/evaluation.py#L1); [packages/core/src/klaude_core/evaluation_interfaces.py](../packages/core/src/klaude_core/evaluation_interfaces.py#L1); [scripts/evaluate_agent_behavior.py](../scripts/evaluate_agent_behavior.py#L1)
- **Limits/notes:** Evaluation scripts/CI are developer tooling, not a browser task scheduler or production API. No new release/build test was run for this doc-only audit.

#### F095. Library/collection compatibility aliases

**Status:** Implemented · **WebUI:** DEPRECATED · **Suggested surface:** Compatibility only

Retains collection-named flags/storage/MCP arguments for compatibility while public language uses library.

- **Current entry:** collections alias; -c/--collection; compatible MCP arguments
- **Configuration/defaults:** Alias precedence/parameter mapping
- **Dependencies:** Existing CLI/MCP contracts
- **Implementation:** [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089); [packages/knowledge/src/klaude_knowledge/mcp_server.py](../packages/knowledge/src/klaude_knowledge/mcp_server.py#L1)
- **Limits/notes:** Preserve backend compatibility; present library terminology in browser. These aliases remain supported; DEPRECATED is the browser mapping (avoid duplicate navigation), not an announced CLI removal.

#### F101. Installation, configuration presets and optional local services

**Status:** Implemented · **WebUI:** OPTIONAL · **Suggested surface:** Setup diagnostics / documentation

Bootstrap handles existing/system/Docker/remote/skipped Ollama, optional model pulls and example config/secrets/docs seeds; Compose supplies loopback SearXNG and optional Crawl4AI/Ollama profiles.

- **Current entry:** scripts/install.sh; scripts/knowledge/install-online-docs.sh; docker-compose.yml
- **Configuration/defaults:** --ollama=existing|system|docker|url:URL|skip; --no-models; heavy/selfhosted Compose profiles
- **Dependencies:** uv/Python; optional Docker/system installers/network
- **Implementation:** [scripts/install.sh](../scripts/install.sh#L1); [docker-compose.yml](../docker-compose.yml#L1); [config/examples/config.toml](../config/examples/config.toml#L1)
- **Limits/notes:** Bootstrap can install external software and is a distinct explicitly invoked operation; not an existing autonomous browser setup API.

### Planned WebUI Integration

#### F096. INTERFACE → Web UI → Enable / Disable

**Status:** Planned · **WebUI:** REQUIRED · **Suggested surface:** TUI Interface settings / hosting status

Proposed persistent control hosts/stops Klaude’s local browser interface independently of CLI/TUI core; remains operable from TUI while hosting is off.

- **Current entry:** Planned SETTINGS → INTERFACE → Web UI
- **Configuration/defaults:** No implemented key/default/port/bind/startup/security policy; all undecided
- **Dependencies:** Future server lifecycle adapter reusing current agent/services/stores
- **Implementation:** [apps/cli/src/klaude_cli/main.py:_settings_home_page](../apps/cli/src/klaude_cli/main.py#L13537); [packages/core/src/klaude_core/settings_store.py](../packages/core/src/klaude_core/settings_store.py#L1); [apps/cli/src/klaude_cli/settings_writer.py](../apps/cli/src/klaude_cli/settings_writer.py#L1)
- **Limits/notes:** User-specified planned requirement. Enabling hosts a browser UI; it does not enable internet access/search or imply public exposure. See dedicated integration notes.

#### F097. Browser visual design and responsive accessibility

**Status:** Planned · **WebUI:** OPTIONAL · **Suggested surface:** Future browser appearance

User direction: Material Design3/MaterialYou, Roboto UI, JetBrains Mono code/logs; inspiration from dots-hyprland, Odysseus, Open WebUI and optionally Impeccable.

- **Current entry:** Planning brief only
- **Configuration/defaults:** No implemented browser appearance settings or frontend stack
- **Dependencies:** Future accessible responsive browser presentation
- **Implementation:** [apps/cli/src/klaude_cli/main.py:_settings_home_page](../apps/cli/src/klaude_cli/main.py#L13537)
- **Limits/notes:** References are visual/navigation inspiration only; no frontend framework, final component architecture or implementation plan is selected here.

### Optional, deferred or unsupported product scope

#### F098. Optional AI media tag suggestions

**Status:** Implemented · **WebUI:** OPTIONAL · **Suggested surface:** Media detail / review and multiselect dialog

Explicit Vision requests propose bounded JSON tags. Users select suggestions before saving them as separate AI metadata; manual choices remain intact.

- **Current entry:** Media detail → Suggest AI tags / Clear AI tags; library suggest-tags / clear-ai-tags
- **Configuration/defaults:** Reuses OFF-by-default Vision and its explicit model/fallbacks; 4096 context/512 output; no automatic tagging; suggestions initially unselected; at most 20 retained AI tags, 40 printable characters each
- **Dependencies:** Existing Vision capability/budget/owned-worker boundary, explicit request and save, private ArtifactStore
- **Implementation:** [core image_tags](../packages/core/src/klaude_core/image_tags.py), [ArtifactStore](../packages/core/src/klaude_core/library_artifacts.py), [VisionPanel](../apps/cli/src/klaude_cli/vision_panel.py), [CLI](../apps/cli/src/klaude_cli/library_commands.py)
- **Limits/notes:** AI tags have per-tag model/endpoint/time/budget provenance. Search/archive/export/delete preserve their documented independence; clear retains manual tags and pixels. Read-only old-store browsing does not migrate. Stale image revisions/checksums reject proposals. Actual native Gemma CLI/TUI passed; all Vision provider limits still apply. Browser interaction needs request review, unchecked multiselection and explicit save. [Evidence](s6-completion-validation.md).

#### F099. Additional media consumers and provider certification

**Status:** Partial · **WebUI:** OPTIONAL · **Suggested surface:** Future capabilities after validation

Generation adapters beyond the first native local consumer and paid OpenAI/Anthropic image inference certification remain open in current implementation notes.

- **Current entry:** Future adapters/validation, not new existing settings
- **Configuration/defaults:** No invented provider/key/quality settings
- **Dependencies:** Explicit service/model capabilities and live validation
- **Implementation:** [docs/odysseus-settings-and-features-plan.md](../docs/odysseus-settings-and-features-plan.md#L1); [docs/s6b-local-generation-validation.md](../docs/s6b-local-generation-validation.md#L1)
- **Limits/notes:** OpenAI/Anthropic adapters already exist for supported Vision scopes; absence of live paid generation evidence is not proof adapters are broken.

#### F100. Gallery canvas, speech and email writing style

**Status:** Planned · **WebUI:** OPTIONAL · **Suggested surface:** Outside current WebUI coverage

Prior plan explicitly defers standalone photo/album/canvas/layer editing, speech and email-specific writing-style consumers.

- **Current entry:** None in current Klaude product
- **Configuration/defaults:** No existing settings/defaults to recreate
- **Dependencies:** Separate future product decisions
- **Implementation:** [docs/odysseus-settings-and-features-plan.md](../docs/odysseus-settings-and-features-plan.md#L1)
- **Limits/notes:** Not imported from Odysseus. Media artifacts already belong in Library; no promise these extensions will be built.

### Planned WebUI Integration — settings and lifecycle seam

The proposed hierarchy is exactly:

```text
SETTINGS
└── INTERFACE
    └── Web UI
        └── Enable / Disable
```

**Planned, not implemented.** Existing settings home sections are APPEARANCE, MODELS & AI, AGENT and ADVANCED; INTERFACE and a hosting preference do not currently exist. `PersistentChatTUI._settings_home_page` constructs typed navigation rows, `_open_settings_category` dispatches controllers, `PanelPage`/`PanelAction` model pages/actions, and `SettingsWriter` plus `settings_store` implement ordered private atomic persistence. These are concrete integration seams for a future TUI hosting control. They are not an authorization to add the field here.

The new toggle must persist across restarts, remain reachable from the TUI while the WebUI is disabled, start/stop only browser hosting and leave core CLI/TUI functionality available. It should reuse existing model connections, Agent/tool semantics, sessions and configuration authorities. **Default enabled state, exact persistence key/file, port, bind address, startup/daemon ownership and security controls remain undecided.** No current `web.provider`, Search switch, MCP callback or managed-model server flag is this preference. Enabling browser hosting neither enables internet access nor authorizes public exposure.

Design context only: Material Design 3/Material You; Roboto for interface; JetBrains Mono for code/terminal/logs; expressive visual inspiration from [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland); navigation inspiration from Odysseus and [Open WebUI](https://github.com/open-webui/open-webui); Impeccable where useful. These references impose no frontend framework or backend architecture.

### Built-in tool contracts and external tool boundary

All 30 literal built-in registrations are enumerated below directly from Tool constructor schemas. Required versus optional is the JSON schema contract; omitted optional defaults can also be applied by the called function. Numeric schema bounds and consumer validation both matter. These are agent call arguments, not 30 new settings pages. External MCP schemas are discovered dynamically and remain server-owned.

| Tool | Declared arguments/schema | Default permission | WebUI | Registration |
| --- | --- | --- | --- | --- |
| `read_skill` | `name` required: `{"type": "string", "description": "Exact installed Skill name"}`; `file` optional: `{"type": "string", "description": "Relative file within the Skill; defaults to SKILL.md"}`; `offset` optional: `{"type": "integer", "minimum": 0, "description": "Character offset for a later part; default 0"}`; `limit` optional: `{"type": "integer", "minimum": 1, "maximum": 6000, "description": "Characters to read; default 2000"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7166](../apps/cli/src/klaude_cli/main.py#L7166) |
| `current_time` | `timezone` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7188](../apps/cli/src/klaude_cli/main.py#L7188) |
| `weather_lookup` | `location` optional: `{"type": "string"}`; `days` optional: `{"type": "integer"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7194](../apps/cli/src/klaude_cli/main.py#L7194) |
| `web_search` | `query` required: `{"type": "string"}`; `purpose` optional: `{"type": "string"}`; `missing_information` optional: `{"type": "string"}`; `provider` optional: `{"type": "string"}`; `provider_strict` optional: `{"type": "boolean"}`; `max_results` optional: `{"type": "integer", "minimum": 1, "maximum": 50}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7204](../apps/cli/src/klaude_cli/main.py#L7204) |
| `fetch_url` | `url` required: `{"type": "string"}`; `purpose` optional: `{"type": "string"}`; `missing_information` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7239](../apps/cli/src/klaude_cli/main.py#L7239) |
| `http_probe` | `url` required: `{"type": "string"}`; `method` optional: `{"type": "string", "enum": ["HEAD", "GET"]}`; `purpose` optional: `{"type": "string"}`; `missing_information` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7253](../apps/cli/src/klaude_cli/main.py#L7253) |
| `list_commands` | No parameters | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7268](../apps/cli/src/klaude_cli/main.py#L7268) |
| `learn_source` | `url` required: `{"type": "string"}`; `library` optional: `{"type": "string", "maxLength": 80}`; `scope` optional: `{"type": "string", "enum": ["page", "site"]}`; `name` optional: `{"type": "string", "maxLength": 80}`; `max_depth` optional: `{"type": "integer", "minimum": 0, "maximum": 5}`; `max_pages` optional: `{"type": "integer", "minimum": 1, "maximum": 500}`; `include_patterns` optional: `{"type": "array", "maxItems": 20, "items": {"type": "string"}}`; `exclude_patterns` optional: `{"type": "array", "maxItems": 20, "items": {"type": "string"}}`; `use_sitemap` optional: `{"type": "boolean"}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7275](../apps/cli/src/klaude_cli/main.py#L7275) |
| `crawl_site` | `url` required: `{"type": "string"}`; `library` optional: `{"type": "string"}`; `collection` optional: `{"type": "string"}`; `name` optional: `{"type": "string"}`; `max_depth` optional: `{"type": "integer"}`; `max_pages` optional: `{"type": "integer"}`; `pattern` optional: `{"type": "string"}`; `include_patterns` optional: `{"type": "array", "items": {"type": "string"}}`; `exclude_patterns` optional: `{"type": "array", "items": {"type": "string"}}`; `use_sitemap` optional: `{"type": "boolean"}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7324](../apps/cli/src/klaude_cli/main.py#L7324) |
| `code_search` | `query` required: `{"type": "string"}`; `max_results` optional: `{"type": "integer", "minimum": 1, "maximum": 50}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7360](../apps/cli/src/klaude_cli/main.py#L7360) |
| `huggingface_search` | `repo_type` optional: `{"type": "string"}`; `type` optional: `{"type": "string"}`; `kind` optional: `{"type": "string"}`; `query` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7376](../apps/cli/src/klaude_cli/main.py#L7376) |
| `huggingface_details` | `repo_type` optional: `{"type": "string"}`; `type` optional: `{"type": "string"}`; `kind` optional: `{"type": "string"}`; `repo_id` optional: `{"type": "string"}`; `id` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7393](../apps/cli/src/klaude_cli/main.py#L7393) |
| `huggingface_readme` | `repo_type` optional: `{"type": "string"}`; `type` optional: `{"type": "string"}`; `kind` optional: `{"type": "string"}`; `repo_id` optional: `{"type": "string"}`; `id` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7411](../apps/cli/src/klaude_cli/main.py#L7411) |
| `query_knowledge` | `query` required: `{"type": "string", "minLength": 1, "description": "Question or search terms to find in locally indexed content."}`; `library` optional: `{"type": "string", "description": "Optional existing library name, such as godot-2d. Omit or leave empty for automatic library selection."}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7428](../apps/cli/src/klaude_cli/main.py#L7428) |
| `search_sessions` | `query` optional: `{"type": "string"}`; `question` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7444](../apps/cli/src/klaude_cli/main.py#L7444) |
| `list_recent_sessions` | No parameters | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7453](../apps/cli/src/klaude_cli/main.py#L7453) |
| `remember_fact` | `fact` required: `{"type": "string"}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7459](../apps/cli/src/klaude_cli/main.py#L7459) |
| `request_user_input` | `header` optional: `{"type": "string", "maxLength": 80}`; `question` required: `{"type": "string", "maxLength": 1000}`; `options` optional: `{"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {"label": {"type": "string", "maxLength": 120}, "description": {"type": "string", "maxLength": 240}}, "required": ["label"]}}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7469](../apps/cli/src/klaude_cli/main.py#L7469) |
| `delegate_task` | `objective` required: `{"type": "string", "minLength": 1, "maxLength": 2000}`; `role` optional: `{"type": "string", "enum": ["read_research", "test_diagnostic"]}`; `context` optional: `{"type": "string", "maxLength": 8000}`; `requested_tools` optional: `{"type": "array", "maxItems": 16, "items": {"type": "string", "maxLength": 128}}`; `additional_tasks` optional: `{"type": "array", "maxItems": 2, "items": {"type": "object", "properties": {"objective": {"type": "string", "minLength": 1, "maxLength": 2000}, "role": {"type": "string", "enum": ["read_research", "test_diagnostic"]}, "context": {"type": "string", "maxLength": 8000}, "requested_tools": {"type": "array", "maxItems": 16, "items": {"type": "string", "maxLength": 128}}}, "required": ["objective"], "additionalProperties": false}}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [apps/cli/src/klaude_cli/main.py:7498](../apps/cli/src/klaude_cli/main.py#L7498) |
| `storage_usage` | No parameters | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:839](../packages/tools_local/src/klaude_tools/toolkit.py#L839) |
| `read_file` | `path` required: `{"type": "string"}`; `offset` optional: `{"type": "integer", "minimum": 1, "maximum": 1000000}`; `limit` optional: `{"type": "integer", "minimum": 1, "maximum": 500}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:846](../packages/tools_local/src/klaude_tools/toolkit.py#L846) |
| `list_dir` | `path` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:860](../packages/tools_local/src/klaude_tools/toolkit.py#L860) |
| `workspace_info` | No parameters | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:863](../packages/tools_local/src/klaude_tools/toolkit.py#L863) |
| `grep` | `pattern` required: `{"type": "string"}`; `path` optional: `{"type": "string"}` | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:870](../packages/tools_local/src/klaude_tools/toolkit.py#L870) |
| `write_file` | `path` required: `{"type": "string"}`; `content` required: `{"type": "string"}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:876](../packages/tools_local/src/klaude_tools/toolkit.py#L876) |
| `edit_file` | `path` required: `{"type": "string"}`; `old_str` required: `{"type": "string"}`; `new_str` required: `{"type": "string"}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:884](../packages/tools_local/src/klaude_tools/toolkit.py#L884) |
| `run_shell` | `command` required: `{"type": "string"}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:892](../packages/tools_local/src/klaude_tools/toolkit.py#L892) |
| `git_status` | No parameters | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:902](../packages/tools_local/src/klaude_tools/toolkit.py#L902) |
| `git_diff` | No parameters | allow | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:903](../packages/tools_local/src/klaude_tools/toolkit.py#L903) |
| `git_commit` | `message` required: `{"type": "string"}` | ask | ADAPT output/approval; callable only when enabled/permitted/in scope | [packages/tools_local/src/klaude_tools/toolkit.py:904](../packages/tools_local/src/klaude_tools/toolkit.py#L904) |

## 3. Complete Settings Inventory

### 3.1 Authorities, precedence, scope and reload rules

`config/` and `data/` below are **resolved roots**, not a promise that every installed user stores data inside this repository.

1. `KLAUDE_CONFIG_DIR` / `KLAUDE_DATA_DIR` override paths. Explicit `KLAUDE_HOME` supplies their config/data children. A source checkout otherwise uses repository `config` and `.klaude/data`; installed defaults resolve to the user’s Klaude config/local-share directories. See config path functions; do not invent XDG environment support.
2. Main config loading combines dataclass defaults, `config.toml`, environment/dotenv secrets, tier detection/role overrides, and selected private JSON preference overlays. `load_config` calls `apply_search_settings` and `apply_fetch_settings`, then persisted provider availability. Tool/runtime/permission preferences are applied later by agent/UI construction.
3. `config/.env` is loaded before source-root `.env` (installed fallback uses cwd); existing inherited env is initially retained. Explicit private stored credential revisions/tombstones subsequently override stale inherited values in revision-aware consumers. Do not flatten this into a universal “env always wins” rule; `web.searxng_secret` has its own precedence expression.
4. `data/chat-preferences.json` stores field-scoped runtime/execution/tool/search/fetch/AI-role/research preferences. `data/appearance.json` stores terminal visuals. SQLite `sessions.db` owns sessions/live events/names/archive/memory preference/session runtime. Endpoint, SSH, MCP and generation definitions have separate revisioned JSON authorities.
5. UI saves commonly update current-client intent immediately, then report Saving/Saved/Unconfirmed via serialized acknowledgements. Accepted jobs capture definition/credential revisions and reject stale state. Editing a config file does **not** guarantee that every already-running client reloads it; use the actual loader/controller boundary. Changes to active model/runtime do not mutate an already accepted request.
6. Secrets live in private dotenv/token stores, not public event payloads. API responses for a browser should expose configured/missing/revision metadata, never raw existing secrets. No browser secret API exists yet.

The following tables list **actual exact paths/keys**, type, source default, validation, scope, effect, sensitivity, exposure and WebUI classification. Where the loader only coerces a type without enforcing a range, that limitation is explicit. Defaults in checked-in examples do not override class/loader defaults automatically.

### 3.2 Shared default maps and special validation

**Tier model role defaults** (automatic RAM selection only when `models.tier` omitted):

| Tier | coder | fast | vision (legacy role) | embed |
| --- | --- | --- | --- | --- |
| lite | qwen3:4b | qwen3:1.7b | empty | nomic-embed-text |
| standard | gpt-oss:20b | qwen3:4b | minicpm-v | nomic-embed-text |
| full | qwen3-coder:30b | qwen3:4b | minicpm-v | nomic-embed-text |

`models.override.<role>` replaces preset roles. The legacy `vision` preset **does not enable** AI Defaults → Vision or authorize pixel transmission. `models.fast` does not by itself imply a periodic Utility task. General `num_predict` defaults to 2048; effective code output defaults to at least 4096 unless explicitly overridden. Model/provider reasoning behavior remains capability-dependent.

**Complete built-in permission defaults** (unknown/external tools default Ask; presets operate on current registry):

| Policy | Exact tools |
| --- | --- |
| allow | `read_file`, `read_skill`, `list_dir`, `workspace_info`, `grep`, `git_status`, `git_diff`, `current_time`, `weather_lookup`, `web_search`, `fetch_url`, `http_probe`, `code_search`, `huggingface_search`, `huggingface_details`, `huggingface_readme`, `query_knowledge`, `search_sessions`, `list_recent_sessions`, `list_commands`, `request_user_input` |
| ask | `run_shell`, `storage_usage`, `write_file`, `edit_file`, `git_commit`, `crawl_site`, `learn_source`, `remember_fact`, `delegate_task` |
| deny |  |

**Search provider defaults:** generic defaults are enabled=true, depth=basic, timeout=20 seconds, cooldown=300 seconds and local_request_limit=950; these are local policy inputs, not remote entitlement or billing guarantees.

| Provider ID | Default api_key_env | Last resort only | Automatic merge |
| --- | --- | --- | --- |
| brave | (keyless) | false | true |
| brave_api | BRAVE_SEARCH_API_KEY | false | true |
| google | GEMINI_API_KEY | false | true |
| parallel | PARALLEL_API_KEY | false | true |
| tavily | TAVILY_API_KEY | false | true |
| exa | EXA_API_KEY | false | true |
| firecrawl | FIRECRAWL_API_KEY | false | true |
| ddgs | (keyless) | false | true |
| searxng | (keyless) | true | false |

**Provider connection defaults and image boundaries (current source, not live availability claims):**

| Backend | Preset root / auth | Current pixel support boundary |
| --- | --- | --- |
| ollama | services.ollama_url default http://localhost:11434; native endpoint may have explicit key ref | Fresh /api/show declares image support |
| openai_compatible | Explicit normalized HTTP(S) root, usually /v1; key ref optional | Exact catalog modalities or explicitly configured native peer at same normalized server/auth scope |
| openai_api | https://api.openai.com/v1; OPENAI_API_KEY | Exact official-root profiles gpt-4.1-mini and gpt-4.1-mini-2025-04-14 plus fresh authenticated availability; no inherited aliases |
| openrouter | https://openrouter.ai/api/v1; OPENROUTER_API_KEY | Exact input image/output text modality evidence; signed private continuation retained |
| gemini_api | https://generativelanguage.googleapis.com; GEMINI_API_KEY | Exact profiles gemini-2.5-flash, gemini-2.5-flash-lite, gemini-3.5-flash-lite, gemini-3.8-flash with fresh identity/method/limits |
| anthropic | https://api.anthropic.com/v1; ANTHROPIC_API_KEY | Exact native capabilities.image_input.supported; Media cannot use thinking-required model; raw image ≤7,500,000bytes |
| deepseek | https://api.deepseek.com/v1; DEEPSEEK_API_KEY | No current chat/Media pixel backend in IMAGE_BACKENDS; text/tools provider remains supported |
| openai_codex | No custom URL; official Codex broker account owns tokens | Not a current IMAGE_BACKENDS consumer; do not infer pixel support from underlying model name |

Sources: [packages/core/src/klaude_core/model_connections.py:DEFAULT_URLS](../packages/core/src/klaude_core/model_connections.py#L36); [packages/core/src/klaude_core/image_profiles.py](../packages/core/src/klaude_core/image_profiles.py#L1); [packages/core/src/klaude_core/image_content.py:IMAGE_BACKENDS](../packages/core/src/klaude_core/image_content.py#L10); [packages/core/src/klaude_core/model_runtime.py](../packages/core/src/klaude_core/model_runtime.py#L1); [packages/core/src/klaude_core/vision.py](../packages/core/src/klaude_core/vision.py#L1). Runtime resource recommendation is explicit: CPU threads max(1,min(16,available_threads//2)); context8192/16384/32768/65536 at observed budget thresholds <8/≥8/≥12/≥24GiB (VRAM or RAM, bounded by RAM). It is not an automatic model-fit test; active default depends on saved/configured values and explicit calibration.

Default provider order: `["brave", "ddgs", "searxng", "brave_api", "google", "parallel", "exa", "tavily", "firecrawl"]`. Saved Search fallback order can override it. Per-provider availability is independent of the built-in web_search tool switch.

**Validation caution:** most TOML booleans use `bool(value)` and several numeric fields only `int`/`float` conversion; that is not a comprehensive schema validator. Runtime/JSON forms often enforce stricter allowlists. A browser adapter must call the same consumer validation and should not claim all config text has a shared validated schema. Dynamic families below represent all current registered names, not permission to inject arbitrary settings.

**TUI_THEME_LABELS accepted IDs (TUI-only):** `crimson-red`, `autumn`, `egg-yolk`, `hacker-green`, `neon-synth`, `pastelle-red`, `pastelle-orange`, `pastelle-yellow`, `pastelle-lime`, `pastelle-green`, `pastelle-cyan`, `pastelle-azure`, `pastelle-blue`, `pastelle-lavender`, `pastelle-purple`, `pastelle-magenta`, `pastelle-pink`.

**TEXT_THEME_LABELS accepted IDs (TUI-only):** `vscode-dark`, `github-dark`, `monokai`, `solarized-light`.

**Divider text-color IDs (TUI-only):** `default`, `accent`, `text`, `red`, `orange`, `yellow`, `green`, `cyan`, `blue`, `purple`, `magenta`, `pink`, `bright-red`, `bright-orange`, `bright-yellow`, `bright-green`, `bright-cyan`, `bright-blue`, `bright-purple`, `bright-magenta`, `bright-pink`, `black`, `bright-black`, `white`, `bright-white`. Line colors accept these plus same-as-text and same-as-input-field.

**Spinner names (TUI-only):** `dots`, `dots2`, `dots3`, `dots4`, `dots5`, `dots6`, `dots7`, `dots8`, `dots9`, `dots10`, `dots11`, `dots12`, `dots13`, `dots14`, `dots8Bit`, `dotsCircle`, `sand`, `line`, `line2`, `rollingLine`, `pipe`, `simpleDots`, `simpleDotsScrolling`, `star`, `star2`, `flip`, `hamburger`, `growVertical`, `growHorizontal`, `balloon`, `balloon2`, `noise`, `bounce`, `boxBounce`, `boxBounce2`, `triangle`, `binary`, `arc`, `circle`, `squareCorners`, `circleQuarters`, `circleHalves`, `squish`, `toggle`, `toggle2`, `toggle3`, `toggle4`, `toggle5`, `toggle6`, `toggle7`, `toggle8`, `toggle9`, `toggle10`, `toggle11`, `toggle12`, `toggle13`, `arrow`, `arrow2`, `arrow3`, `bouncingBar`, `bouncingBall`, `smiley`, `monkey`, `hearts`, `clock`, `earth`, `material`, `moon`, `runner`, `pong`, `shark`, `dqpb`, `weather`, `christmas`, `grenade`, `point`, `layer`, `betaWave`, `fingerDance`, `fistBump`, `soccerHeader`, `mindblown`, `speaker`, `orangePulse`, `bluePulse`, `orangeBluePulse`, `timeTravel`, `aesthetic`, `dwarfFortress`, `fish`, `claude`, `custom`. Default dots frames: `["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]`; built-in dots interval 80ms. Custom interval default100ms is a different stored field.

### Global services, models and agent

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S001 `models.tier` | Implemented | str | `RAM detection: full≥28GiB; standard≥12GiB; otherwise lite (constructor empty)` | lite \| standard \| full; omitted selects RAM tier; unknown preset falls back standard | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:457](../packages/core/src/klaude_core/config.py#L457); [packages/core/src/klaude_core/config.py:739](../packages/core/src/klaude_core/config.py#L739) |
| S002 `services.ollama_url` | Implemented | str | `http://localhost:11434` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:458](../packages/core/src/klaude_core/config.py#L458); [packages/core/src/klaude_core/config.py:755](../packages/core/src/klaude_core/config.py#L755) |
| S003 `services.searxng_url` | Implemented | str | `http://localhost:8888` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:459](../packages/core/src/klaude_core/config.py#L459); [packages/core/src/klaude_core/config.py:756](../packages/core/src/klaude_core/config.py#L756) |
| S004 `services.crawl4ai_url` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:460](../packages/core/src/klaude_core/config.py#L460); [packages/core/src/klaude_core/config.py:757](../packages/core/src/klaude_core/config.py#L757) |
| S005 `services.crawl4ai_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:461](../packages/core/src/klaude_core/config.py#L461); [packages/core/src/klaude_core/config.py:1240](../packages/core/src/klaude_core/config.py#L1240) |
| S007 `web.provider` | Implemented | str | `quality` | quality \| local \| brave \| brave_api \| exa \| auto | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:463](../packages/core/src/klaude_core/config.py#L463); [packages/core/src/klaude_core/config.py:765](../packages/core/src/klaude_core/config.py#L765) |
| S008 `web.gemini_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:464](../packages/core/src/klaude_core/config.py#L464); [packages/core/src/klaude_core/config.py:1071](../packages/core/src/klaude_core/config.py#L1071) |
| S009 `cloud.openai_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:465](../packages/core/src/klaude_core/config.py#L465); [packages/core/src/klaude_core/config.py:1077](../packages/core/src/klaude_core/config.py#L1077) |
| S010 `cloud.openrouter_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:466](../packages/core/src/klaude_core/config.py#L466); [packages/core/src/klaude_core/config.py:1081](../packages/core/src/klaude_core/config.py#L1081) |
| S011 `web.brave_search_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:467](../packages/core/src/klaude_core/config.py#L467); [packages/core/src/klaude_core/config.py:1085](../packages/core/src/klaude_core/config.py#L1085) |
| S012 `web.parallel_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:468](../packages/core/src/klaude_core/config.py#L468); [packages/core/src/klaude_core/config.py:1089](../packages/core/src/klaude_core/config.py#L1089) |
| S013 `web.tavily_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:469](../packages/core/src/klaude_core/config.py#L469); [packages/core/src/klaude_core/config.py:1093](../packages/core/src/klaude_core/config.py#L1093) |
| S014 `web.firecrawl_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:470](../packages/core/src/klaude_core/config.py#L470); [packages/core/src/klaude_core/config.py:1097](../packages/core/src/klaude_core/config.py#L1097) |
| S015 `web.searxng_secret` | Partial | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | SECRET; Config file; dotenv/env and masked TUI provider fields | OPTIONAL | [packages/core/src/klaude_core/config.py:471](../packages/core/src/klaude_core/config.py#L471); [packages/core/src/klaude_core/config.py:1101](../packages/core/src/klaude_core/config.py#L1101) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S016 `web.exa_api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:472](../packages/core/src/klaude_core/config.py#L472); [packages/core/src/klaude_core/config.py:1236](../packages/core/src/klaude_core/config.py#L1236) |
| S017 `web.exa_base_url` | Implemented | str | `https://api.exa.ai` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:473](../packages/core/src/klaude_core/config.py#L473); [packages/core/src/klaude_core/config.py:1109](../packages/core/src/klaude_core/config.py#L1109) |
| S018 `huggingface.api_key` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Credential revision rechecks for captured work; active clients may require reload/reselection | SECRET; Config file; dotenv/env and masked TUI provider fields | REQUIRED | [packages/core/src/klaude_core/config.py:474](../packages/core/src/klaude_core/config.py#L474); [packages/core/src/klaude_core/config.py:1112](../packages/core/src/klaude_core/config.py#L1112) |
| S019 `huggingface.base_url` | Implemented | str | `https://huggingface.co` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:475](../packages/core/src/klaude_core/config.py#L475); [packages/core/src/klaude_core/config.py:1116](../packages/core/src/klaude_core/config.py#L1116) |
| S020 `models.override.<role>` | Implemented | dict[str, str] | `Tier role map; see §3.2 role defaults` | Role string map; shipped coder/fast/vision/embed defaults are tier-dependent | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:476](../packages/core/src/klaude_core/config.py#L476); [packages/core/src/klaude_core/config.py:742](../packages/core/src/klaude_core/config.py#L742) |
| S021 `ollama.think` | Implemented | bool \| str \| None | `null / unset` | Boolean or low/medium/high; unset automatic based on selected model/runtime | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:437](../packages/core/src/klaude_core/config.py#L437) |
| S022 `ollama.code_think` | Implemented | bool \| str \| None | `null / unset` | Boolean or low/medium/high; code override or inherited automatic choice | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:438](../packages/core/src/klaude_core/config.py#L438) |
| S023 `permissions.<tool>` | Implemented | dict[str, str] | `DEFAULT_PERMISSIONS; see §3.2 complete map` | Tool name→allow/ask/deny; DEFAULT_PERMISSIONS merged with overrides | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:479](../packages/core/src/klaude_core/config.py#L479); [packages/core/src/klaude_core/config.py:1118](../packages/core/src/klaude_core/config.py#L1118) |
| S024 `agent.max_steps` | Implemented | int | `20` | Integer clamped 1–64; saved execution override applies | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:480](../packages/core/src/klaude_core/config.py#L480); [packages/core/src/klaude_core/config.py:1121](../packages/core/src/klaude_core/config.py#L1121) |
| S025 `agent.max_tool_calls` | Implemented | int | `0` | Integer clamped 0–256; 0 means Auto, not unlimited | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:482](../packages/core/src/klaude_core/config.py#L482); [packages/core/src/klaude_core/config.py:1122](../packages/core/src/klaude_core/config.py#L1122) |
| S026 `agent.max_total_tokens` | Implemented | int | `0` | Integer clamped 0–2,000,000; 0 means no token cap | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:484](../packages/core/src/klaude_core/config.py#L484); [packages/core/src/klaude_core/config.py:1126](../packages/core/src/klaude_core/config.py#L1126) |
| S027 `agent.max_subagent_concurrency` | Implemented | int | `0` | Integer clamped 0–4; 0 auto | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:486](../packages/core/src/klaude_core/config.py#L486); [packages/core/src/klaude_core/config.py:1130](../packages/core/src/klaude_core/config.py#L1130) |
| S028 `agent.max_code_continuations` | Implemented | int | `2` | Integer clamped 0–3 | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:487](../packages/core/src/klaude_core/config.py#L487); [packages/core/src/klaude_core/config.py:1142](../packages/core/src/klaude_core/config.py#L1142) |
| S029 `agent.max_code_repairs` | Implemented | int | `2` | Integer clamped 0–3 | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:488](../packages/core/src/klaude_core/config.py#L488); [packages/core/src/klaude_core/config.py:1145](../packages/core/src/klaude_core/config.py#L1145) |
| S030 `agent.retrieval_k` | Implemented | int | `6` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:489](../packages/core/src/klaude_core/config.py#L489); [packages/core/src/klaude_core/config.py:1146](../packages/core/src/klaude_core/config.py#L1146) |
| S031 `tool_validation.knowledge_search` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/config.py:492](../packages/core/src/klaude_core/config.py#L492); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1) — Internal Config.retrieval_validation_enabled is not a TOML key. |

### Knowledge and crawling

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S006 `crawler.user_agent` | Implemented | str | `KlaudeBot/0.2 (+local documentation crawler)` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:462](../packages/core/src/klaude_core/config.py#L462); [packages/core/src/klaude_core/config.py:1152](../packages/core/src/klaude_core/config.py#L1152) |
| S032 `knowledge.snapshot_retention` | Implemented | int | `3` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:493](../packages/core/src/klaude_core/config.py#L493); [packages/core/src/klaude_core/config.py:1149](../packages/core/src/klaude_core/config.py#L1149) |
| S033 `crawler.max_depth` | Implemented | int | `2` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:494](../packages/core/src/klaude_core/config.py#L494); [packages/core/src/klaude_core/config.py:1153](../packages/core/src/klaude_core/config.py#L1153) |
| S034 `crawler.max_pages` | Implemented | int | `50` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:495](../packages/core/src/klaude_core/config.py#L495); [packages/core/src/klaude_core/config.py:1154](../packages/core/src/klaude_core/config.py#L1154) |
| S035 `crawler.delay_min` | Implemented | float | `2.0` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:496](../packages/core/src/klaude_core/config.py#L496); [packages/core/src/klaude_core/config.py:1155](../packages/core/src/klaude_core/config.py#L1155) |
| S036 `crawler.delay_max` | Implemented | float | `5.0` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:497](../packages/core/src/klaude_core/config.py#L497); [packages/core/src/klaude_core/config.py:1156](../packages/core/src/klaude_core/config.py#L1156) |
| S037 `crawler.respect_robots` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:498](../packages/core/src/klaude_core/config.py#L498); [packages/core/src/klaude_core/config.py:1157](../packages/core/src/klaude_core/config.py#L1157) |

### Runtime context and privacy

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S038 `runtime_context.enabled` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:307](../packages/core/src/klaude_core/config.py#L307); [packages/core/src/klaude_core/config.py:1160](../packages/core/src/klaude_core/config.py#L1160) |
| S039 `runtime_context.provider` | Implemented | str | `auto` | auto \| fastfetch \| neofetch \| native \| off | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:308](../packages/core/src/klaude_core/config.py#L308); [packages/core/src/klaude_core/config.py:1161](../packages/core/src/klaude_core/config.py#L1161) |
| S040 `runtime_context.refresh_seconds` | Implemented | int | `300` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:309](../packages/core/src/klaude_core/config.py#L309); [packages/core/src/klaude_core/config.py:1166](../packages/core/src/klaude_core/config.py#L1166) |
| S041 `runtime_context.command_timeout_seconds` | Implemented | int | `3` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:310](../packages/core/src/klaude_core/config.py#L310); [packages/core/src/klaude_core/config.py:1169](../packages/core/src/klaude_core/config.py#L1169) |
| S042 `runtime_context.max_prompt_characters` | Implemented | int | `3500` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:311](../packages/core/src/klaude_core/config.py#L311); [packages/core/src/klaude_core/config.py:1175](../packages/core/src/klaude_core/config.py#L1175) |
| S043 `runtime_context.include_workspace` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:312](../packages/core/src/klaude_core/config.py#L312); [packages/core/src/klaude_core/config.py:1178](../packages/core/src/klaude_core/config.py#L1178) |
| S044 `runtime_context.include_git` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:313](../packages/core/src/klaude_core/config.py#L313); [packages/core/src/klaude_core/config.py:1181](../packages/core/src/klaude_core/config.py#L1181) |
| S045 `runtime_context.include_displays` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:314](../packages/core/src/klaude_core/config.py#L314); [packages/core/src/klaude_core/config.py:1184](../packages/core/src/klaude_core/config.py#L1184) |
| S046 `runtime_context.include_disks` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:315](../packages/core/src/klaude_core/config.py#L315); [packages/core/src/klaude_core/config.py:1187](../packages/core/src/klaude_core/config.py#L1187) |
| S047 `runtime_context.include_local_ip` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:316](../packages/core/src/klaude_core/config.py#L316); [packages/core/src/klaude_core/config.py:1190](../packages/core/src/klaude_core/config.py#L1190) |
| S048 `runtime_context.show_install_suggestion` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:317](../packages/core/src/klaude_core/config.py#L317); [packages/core/src/klaude_core/config.py:1193](../packages/core/src/klaude_core/config.py#L1193) |
| S049 `runtime_context.location.mode` | Implemented | str | `local` | configured \| local \| network \| off | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:299](../packages/core/src/klaude_core/config.py#L299); [packages/core/src/klaude_core/config.py:1197](../packages/core/src/klaude_core/config.py#L1197) |
| S050 `runtime_context.location.configured_country` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:300](../packages/core/src/klaude_core/config.py#L300); [packages/core/src/klaude_core/config.py:1205](../packages/core/src/klaude_core/config.py#L1205) |
| S051 `runtime_context.location.configured_region` | Implemented | str | `""` | String; no general loader enum/range; consumer validation still applies | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:301](../packages/core/src/klaude_core/config.py#L301); [packages/core/src/klaude_core/config.py:1209](../packages/core/src/klaude_core/config.py#L1209) |
| S052 `runtime_context.location.allow_network_lookup` | Implemented | bool | `false` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | Host/location metadata; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:302](../packages/core/src/klaude_core/config.py#L302); [packages/core/src/klaude_core/config.py:1213](../packages/core/src/klaude_core/config.py#L1213) |

### Search, fetch, relevance and advanced web

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S053 `entities.wikimedia.enabled` | Implemented | bool | `false` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:354](../packages/core/src/klaude_core/config.py#L354); [packages/core/src/klaude_core/config.py:1021](../packages/core/src/klaude_core/config.py#L1021) |
| S054 `entities.wikimedia.timeout_seconds` | Implemented | float | `3.0` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:355](../packages/core/src/klaude_core/config.py#L355); [packages/core/src/klaude_core/config.py:1024](../packages/core/src/klaude_core/config.py#L1024) |
| S055 `entities.wikimedia.max_results` | Implemented | int | `5` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:356](../packages/core/src/klaude_core/config.py#L356); [packages/core/src/klaude_core/config.py:1030](../packages/core/src/klaude_core/config.py#L1030) |
| S056 `entities.metadata_refresh_days` | Implemented | int | `90` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:357](../packages/core/src/klaude_core/config.py#L357); [packages/core/src/klaude_core/config.py:1033](../packages/core/src/klaude_core/config.py#L1033) |
| S057 `web.billing.mode` | Implemented | str | `prepaid_free_search_allowance` | strict_zero_cost \| prepaid_free_search_allowance \| manual_paid_opt_in | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:323](../packages/core/src/klaude_core/config.py#L323); [packages/core/src/klaude_core/config.py:771](../packages/core/src/klaude_core/config.py#L771) |
| S058 `web.billing.allow_paid_overage` | Implemented | bool | `false` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:324](../packages/core/src/klaude_core/config.py#L324); [packages/core/src/klaude_core/config.py:781](../packages/core/src/klaude_core/config.py#L781) |
| S059 `web.billing.allow_auto_recharge` | Implemented | bool | `false` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:325](../packages/core/src/klaude_core/config.py#L325); [packages/core/src/klaude_core/config.py:784](../packages/core/src/klaude_core/config.py#L784) |
| S060 `web.search.strategy` | Implemented | str | `quality` | quality \| legacy | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:385](../packages/core/src/klaude_core/config.py#L385); [packages/core/src/klaude_core/config.py:789](../packages/core/src/klaude_core/config.py#L789) |
| S061 `search_settings.provider` | Implemented | str \| None | `Unset; effective auto unless legacy provider selects explicit provider` | auto \| brave \| brave_api \| google \| parallel \| exa \| ddgs \| tavily \| firecrawl \| searxng | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | OPTIONAL | [packages/core/src/klaude_core/config.py:387](../packages/core/src/klaude_core/config.py#L387); [packages/core/src/klaude_core/search_settings.py](../packages/core/src/klaude_core/search_settings.py#L1) — Internal Config.web_search.settings_provider is not a TOML key. |
| S062 `search_settings.fallbacks` | Implemented | list[str] \| None | `Unset/inherit provider_order` | Unique ordered provider IDs; list length ≤9; unset inherits order | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | OPTIONAL | [packages/core/src/klaude_core/config.py:388](../packages/core/src/klaude_core/config.py#L388); [packages/core/src/klaude_core/search_settings.py](../packages/core/src/klaude_core/search_settings.py#L1) — Internal Config.web_search.settings_fallbacks is not a TOML key. |
| S063 `search_settings.results` | Implemented | int | `12` | Integer 1–50 | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | OPTIONAL | [packages/core/src/klaude_core/config.py:389](../packages/core/src/klaude_core/config.py#L389); [packages/core/src/klaude_core/search_settings.py](../packages/core/src/klaude_core/search_settings.py#L1) — Internal Config.web_search.default_results is not a TOML key. |
| S064 `web.search.stop_when_sufficient` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:390](../packages/core/src/klaude_core/config.py#L390); [packages/core/src/klaude_core/config.py:792](../packages/core/src/klaude_core/config.py#L792) |
| S065 `web.search.provider_order` | Implemented | list[str] | `["brave", "ddgs", "searxng", "brave_api", "google", "parallel", "exa", "tavily", "firecrawl"]` | List of known provider IDs; unknown entries ignored; omitted known providers appended | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:391](../packages/core/src/klaude_core/config.py#L391); [packages/core/src/klaude_core/config.py:810](../packages/core/src/klaude_core/config.py#L810) |
| S066 `web.search.allow_explicit_provider_fallback` | Implemented | bool | `false` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:392](../packages/core/src/klaude_core/config.py#L392); [packages/core/src/klaude_core/config.py:811](../packages/core/src/klaude_core/config.py#L811) |
| S067 `web.search.skip_unconfigured_providers` | Partial | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:393](../packages/core/src/klaude_core/config.py#L393); [packages/core/src/klaude_core/config.py:817](../packages/core/src/klaude_core/config.py#L817) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S068 `web.search.fallback_on_quota` | Partial | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:394](../packages/core/src/klaude_core/config.py#L394); [packages/core/src/klaude_core/config.py:820](../packages/core/src/klaude_core/config.py#L820) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S069 `web.search.fallback_on_unavailable` | Partial | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:395](../packages/core/src/klaude_core/config.py#L395); [packages/core/src/klaude_core/config.py:823](../packages/core/src/klaude_core/config.py#L823) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S070 `web.search.fallback_on_low_relevance` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:396](../packages/core/src/klaude_core/config.py#L396); [packages/core/src/klaude_core/config.py:826](../packages/core/src/klaude_core/config.py#L826) |
| S071 `web.search.strict_result_filtering` | Implemented | bool | `false` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:397](../packages/core/src/klaude_core/config.py#L397); [packages/core/src/klaude_core/config.py:795](../packages/core/src/klaude_core/config.py#L795) |
| S072 `tool_validation.web_search` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | OPTIONAL | [packages/core/src/klaude_core/config.py:400](../packages/core/src/klaude_core/config.py#L400); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1) — Internal Config.web_search.result_validation_enabled is not a TOML key. |
| S073 `web.search.return_unrelated_results` | Partial | bool | `false` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:401](../packages/core/src/klaude_core/config.py#L401); [packages/core/src/klaude_core/config.py:829](../packages/core/src/klaude_core/config.py#L829) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S074 `web.search.max_provider_attempts` | Implemented | int | `3` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:402](../packages/core/src/klaude_core/config.py#L402); [packages/core/src/klaude_core/config.py:832](../packages/core/src/klaude_core/config.py#L832) |
| S075 `web.search.max_results_per_domain` | Implemented | int | `2` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:403](../packages/core/src/klaude_core/config.py#L403); [packages/core/src/klaude_core/config.py:835](../packages/core/src/klaude_core/config.py#L835) |
| S076 `web.search.relevance.candidate_discovery_threshold` | Implemented | float | `0.38` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:404](../packages/core/src/klaude_core/config.py#L404); [packages/core/src/klaude_core/config.py:839](../packages/core/src/klaude_core/config.py#L839) — Accepted compatibility key(s): web.search.candidate_discovery_threshold |
| S077 `web.search.relevance.final_verification_threshold` | Implemented | float | `0.72` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:405](../packages/core/src/klaude_core/config.py#L405); [packages/core/src/klaude_core/config.py:848](../packages/core/src/klaude_core/config.py#L848) — Accepted compatibility key(s): web.search.final_verification_threshold |
| S078 `web.search.minimum_relevance` | Implemented | float | `0.62` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:406](../packages/core/src/klaude_core/config.py#L406); [packages/core/src/klaude_core/config.py:857](../packages/core/src/klaude_core/config.py#L857) |
| S079 `web.search.relevance.strict_entity_threshold` | Implemented | float | `0.78` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:407](../packages/core/src/klaude_core/config.py#L407); [packages/core/src/klaude_core/config.py:860](../packages/core/src/klaude_core/config.py#L860) — Accepted compatibility key(s): web.search.strict_entity_relevance |
| S080 `web.search.minimum_authority` | Implemented | float | `0.45` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:408](../packages/core/src/klaude_core/config.py#L408); [packages/core/src/klaude_core/config.py:866](../packages/core/src/klaude_core/config.py#L866) |
| S081 `web.search.max_attempts_per_provider` | Implemented | int | `2` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:409](../packages/core/src/klaude_core/config.py#L409); [packages/core/src/klaude_core/config.py:869](../packages/core/src/klaude_core/config.py#L869) |
| S082 `web.search.base_retry_delay_ms` | Implemented | int | `500` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:410](../packages/core/src/klaude_core/config.py#L410); [packages/core/src/klaude_core/config.py:872](../packages/core/src/klaude_core/config.py#L872) |
| S083 `web.search.maximum_retry_delay_seconds` | Implemented | int | `10` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:411](../packages/core/src/klaude_core/config.py#L411); [packages/core/src/klaude_core/config.py:875](../packages/core/src/klaude_core/config.py#L875) |
| S084 `web.search.honor_retry_after` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:412](../packages/core/src/klaude_core/config.py#L412); [packages/core/src/klaude_core/config.py:881](../packages/core/src/klaude_core/config.py#L881) |
| S085 `web.search.cache_enabled` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:413](../packages/core/src/klaude_core/config.py#L413); [packages/core/src/klaude_core/config.py:884](../packages/core/src/klaude_core/config.py#L884) |
| S086 `web.search.max_disambiguation_queries` | Implemented | int | `4` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:414](../packages/core/src/klaude_core/config.py#L414); [packages/core/src/klaude_core/config.py:885](../packages/core/src/klaude_core/config.py#L885) |
| S087 `web.search.minimum_confident_entity_score` | Implemented | float | `0.68` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:415](../packages/core/src/klaude_core/config.py#L415); [packages/core/src/klaude_core/config.py:888](../packages/core/src/klaude_core/config.py#L888) |
| S088 `web.search.minimum_winner_margin` | Implemented | float | `0.18` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:416](../packages/core/src/klaude_core/config.py#L416); [packages/core/src/klaude_core/config.py:894](../packages/core/src/klaude_core/config.py#L894) |
| S089 `web.search.location.enabled` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:330](../packages/core/src/klaude_core/config.py#L330); [packages/core/src/klaude_core/config.py:898](../packages/core/src/klaude_core/config.py#L898) |
| S090 `web.search.location.use_runtime_country` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:331](../packages/core/src/klaude_core/config.py#L331); [packages/core/src/klaude_core/config.py:901](../packages/core/src/klaude_core/config.py#L901) |
| S091 `web.search.location.send_country_for_local_intent_only` | Partial | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:332](../packages/core/src/klaude_core/config.py#L332); [packages/core/src/klaude_core/config.py:907](../packages/core/src/klaude_core/config.py#L907) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S092 `web.search.location.maximum_inferred_location_weight` | Implemented | float | `0.1` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:333](../packages/core/src/klaude_core/config.py#L333); [packages/core/src/klaude_core/config.py:913](../packages/core/src/klaude_core/config.py#L913) |
| S093 `web.search.behavior.max_query_rewrites` | Implemented | int | `3` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:338](../packages/core/src/klaude_core/config.py#L338); [packages/core/src/klaude_core/config.py:920](../packages/core/src/klaude_core/config.py#L920) |
| S094 `web.search.behavior.max_provider_fallbacks` | Implemented | int | `4` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:339](../packages/core/src/klaude_core/config.py#L339); [packages/core/src/klaude_core/config.py:926](../packages/core/src/klaude_core/config.py#L926) |
| S095 `web.search.behavior.max_web_actions` | Implemented | int | `6` | Loader expression: max(1, int(search_behavior.get('max_web_actions', Config.web_search.behavior.max_web_actions))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:340](../packages/core/src/klaude_core/config.py#L340); [packages/core/src/klaude_core/config.py:932](../packages/core/src/klaude_core/config.py#L932) |
| S096 `web.search.behavior.max_search_calls` | Implemented | int | `3` | Loader expression: max(1, int(search_behavior.get('max_search_calls', legacy_search_calls if legacy_search_calls is not None else Config.web_search.behavior.max_search_calls))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:341](../packages/core/src/klaude_core/config.py#L341); [packages/core/src/klaude_core/config.py:942](../packages/core/src/klaude_core/config.py#L942) |
| S097 `web.search.behavior.max_fetch_calls` | Implemented | int | `4` | Loader expression: max(1, int(search_behavior.get('max_fetch_calls', legacy_fetch_calls if legacy_fetch_calls is not None else Config.web_search.behavior.max_fetch_calls))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:342](../packages/core/src/klaude_core/config.py#L342); [packages/core/src/klaude_core/config.py:954](../packages/core/src/klaude_core/config.py#L954) |
| S098 `web.search.behavior.max_pages_per_domain` | Implemented | int | `2` | Loader expression: max(1, int(search_behavior.get('max_pages_per_domain', Config.web_search.behavior.max_pages_per_domain))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:343](../packages/core/src/klaude_core/config.py#L343); [packages/core/src/klaude_core/config.py:965](../packages/core/src/klaude_core/config.py#L965) |
| S099 `web.search.behavior.max_consecutive_failures` | Implemented | int | `3` | Loader expression: max(1, int(search_behavior.get('max_consecutive_failures', Config.web_search.behavior.max_consecutive_failures))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:344](../packages/core/src/klaude_core/config.py#L344); [packages/core/src/klaude_core/config.py:974](../packages/core/src/klaude_core/config.py#L974) |
| S100 `web.search.behavior.max_total_search_calls` | Implemented | int | `6` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | DEPRECATED | [packages/core/src/klaude_core/config.py:347](../packages/core/src/klaude_core/config.py#L347); [packages/core/src/klaude_core/config.py:983](../packages/core/src/klaude_core/config.py#L983) —  Compatibility key feeds new search/fetch limit only when the newer key is absent; do not duplicate as separate browser control. Supported compatibility input; DEPRECATED is the browser mapping recommendation, not an announced CLI removal. |
| S101 `web.search.behavior.max_fetch_attempts` | Implemented | int | `4` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | DEPRECATED | [packages/core/src/klaude_core/config.py:348](../packages/core/src/klaude_core/config.py#L348); [packages/core/src/klaude_core/config.py:989](../packages/core/src/klaude_core/config.py#L989) —  Compatibility key feeds new search/fetch limit only when the newer key is absent; do not duplicate as separate browser control. Supported compatibility input; DEPRECATED is the browser mapping recommendation, not an announced CLI removal. |
| S102 `web.search.behavior.max_repeated_query_similarity` | Implemented | float | `0.9` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:349](../packages/core/src/klaude_core/config.py#L349); [packages/core/src/klaude_core/config.py:995](../packages/core/src/klaude_core/config.py#L995) —  Legacy declared threshold; current agent also has its own duplicate guards. No universal user-facing guarantee. |
| S103 `fetch_settings.provider` | Implemented | str \| None | `Unset; effective local unless legacy provider is exa` | local \| exa; unset inherits legacy web.provider | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/config.py:372](../packages/core/src/klaude_core/config.py#L372); [packages/core/src/klaude_core/fetch_settings.py](../packages/core/src/klaude_core/fetch_settings.py#L1) — Internal Config.web_fetch.settings_provider is not a TOML key. |
| S104 `fetch_settings.exa_fallback` | Implemented | bool \| None | `null / unset` | Boolean; unset derives from legacy web.provider == auto | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/config.py:373](../packages/core/src/klaude_core/config.py#L373); [packages/core/src/klaude_core/fetch_settings.py](../packages/core/src/klaude_core/fetch_settings.py#L1) — Internal Config.web_fetch.exa_fallback is not a TOML key. |
| S105 `fetch_settings.crawl4ai_enabled` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/config.py:374](../packages/core/src/klaude_core/config.py#L374); [packages/core/src/klaude_core/fetch_settings.py](../packages/core/src/klaude_core/fetch_settings.py#L1) — Internal Config.web_fetch.crawl4ai_enabled is not a TOML key. |
| S106 `fetch_settings.exa_enabled` | Implemented | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | data/chat-preferences.json; Successful save updates this client; new readers reload | No secret value; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/config.py:375](../packages/core/src/klaude_core/config.py#L375); [packages/core/src/klaude_core/fetch_settings.py](../packages/core/src/klaude_core/fetch_settings.py#L1) — Internal Config.web_fetch.exa_enabled is not a TOML key. |
| S107 `web.fetch.timeout_seconds` | Implemented | float | `30.0` | Loader expression: max(0.1, float(fetch.get('timeout_seconds', Config.web_fetch.timeout_seconds))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:376](../packages/core/src/klaude_core/config.py#L376); [packages/core/src/klaude_core/config.py:1003](../packages/core/src/klaude_core/config.py#L1003) |
| S108 `web.fetch.max_download_bytes` | Implemented | int | `2000000` | Loader expression: max(1, int(fetch.get('max_download_bytes', Config.web_fetch.max_download_bytes))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:377](../packages/core/src/klaude_core/config.py#L377); [packages/core/src/klaude_core/config.py:1006](../packages/core/src/klaude_core/config.py#L1006) |
| S109 `web.fetch.max_content_characters` | Implemented | int | `20000` | Loader expression: max(1, int(fetch.get('max_content_characters', Config.web_fetch.max_content_characters))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:378](../packages/core/src/klaude_core/config.py#L378); [packages/core/src/klaude_core/config.py:1009](../packages/core/src/klaude_core/config.py#L1009) |
| S110 `web.fetch.max_redirects` | Implemented | int | `5` | Loader expression: max(0, int(fetch.get('max_redirects', Config.web_fetch.max_redirects))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:379](../packages/core/src/klaude_core/config.py#L379); [packages/core/src/klaude_core/config.py:1012](../packages/core/src/klaude_core/config.py#L1012) |
| S111 `web.fetch.cache_ttl_seconds` | Implemented | int | `86400` | Loader expression: max(0, int(fetch.get('cache_ttl_seconds', Config.web_fetch.cache_ttl_seconds))) | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | REQUIRED | [packages/core/src/klaude_core/config.py:380](../packages/core/src/klaude_core/config.py#L380); [packages/core/src/klaude_core/config.py:1015](../packages/core/src/klaude_core/config.py#L1015) |
| S112 `web.verification.max_domains` | Partial | int | `2` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:362](../packages/core/src/klaude_core/config.py#L362); [packages/core/src/klaude_core/config.py:1041](../packages/core/src/klaude_core/config.py#L1041) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S113 `web.verification.max_pages_per_domain` | Implemented | int | `4` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Next load_config/process; not a universal hot reload | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:363](../packages/core/src/klaude_core/config.py#L363); [packages/core/src/klaude_core/config.py:1044](../packages/core/src/klaude_core/config.py#L1044) |
| S114 `web.verification.max_total_verification_pages` | Partial | int | `6` | Numeric conversion; no general schema range in this loader | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:364](../packages/core/src/klaude_core/config.py#L364); [packages/core/src/klaude_core/config.py:1050](../packages/core/src/klaude_core/config.py#L1050) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S115 `web.verification.same_domain_only` | Partial | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:365](../packages/core/src/klaude_core/config.py#L365); [packages/core/src/klaude_core/config.py:1056](../packages/core/src/klaude_core/config.py#L1056) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |
| S116 `web.verification.respect_robots` | Partial | bool | `true` | Boolean; TOML loader uses bool(value); JSON controls enforce actual bool | Global config/config.toml; Loaded, but no corresponding production consumer located; effect unverified | No secret value; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:366](../packages/core/src/klaude_core/config.py#L366); [packages/core/src/klaude_core/config.py:1059](../packages/core/src/klaude_core/config.py#L1059) —  Declared/loaded compatibility or unfinished control. Do not recreate as a claimed functional switch without tracing a consumer. |

### Search provider field families

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S117 `web.providers.<provider>.enabled` | Implemented | bool | `true` | Boolean; saved web_provider_availability overrides | Global config/config.toml; Next config load | No; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |
| S118 `web.providers.<provider>.api_key_env` | Implemented | str | `Provider-specific; see provider table` | Environment variable name; resolved private credential, not raw key | Global config/config.toml; Next config load | Credential reference; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |
| S119 `web.providers.<provider>.last_resort_only` | Implemented | bool | `false; searxng true` | Boolean | Global config/config.toml; Next config load | No; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |
| S120 `web.providers.<provider>.automatic_merge` | Implemented | bool | `true; searxng false` | Boolean | Global config/config.toml; Next config load | No; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |
| S121 `web.providers.<provider>.default_depth` | Implemented | str | `basic` | TUI basic \| advanced; TOML coerces string without enum validation; primarily Tavily | Global config/config.toml; Next config load | No; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |
| S122 `web.providers.<provider>.timeout_seconds` | Implemented | int | `20` | Integer conversion in loader; consumer request deadline | Global config/config.toml; Next config load | No; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |
| S123 `web.providers.<provider>.cooldown_seconds` | Implemented | int | `300` | Integer; provider cooldown | Global config/config.toml; Next config load | No; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |
| S124 `web.providers.<provider>.local_request_limit` | Implemented | int | `950` | Integer; local estimate, not remote bill guarantee | Global config/config.toml; Next config load | No; Config; enabled/depth also TUI | OPTIONAL | [packages/core/src/klaude_core/config.py:WebProviderConfig](../packages/core/src/klaude_core/config.py#L422); [packages/core/src/klaude_core/config.py:_provider_config_from_dict](../packages/core/src/klaude_core/config.py#L281) |

### Ollama sampling and output

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S125 `ollama.options.num_ctx` | Implemented | int | `Unspecified; provider default / general option inherited for code` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S126 `ollama.options.num_thread` | Implemented | int | `Unspecified; provider default / general option inherited for code` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S127 `ollama.options.num_gpu` | Implemented | int | `Unspecified; provider default / general option inherited for code` | ≥0 in TOML (runtime override permits -1) | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S128 `ollama.options.num_predict` | Implemented | int | `2048 effective general` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S129 `ollama.options.top_k` | Implemented | int | `Unspecified; provider default / general option inherited for code` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S130 `ollama.options.seed` | Implemented | int | `Unspecified; provider default / general option inherited for code` | ≥0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S131 `ollama.options.temperature` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S132 `ollama.options.top_p` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–1 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S133 `ollama.options.min_p` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–1 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S134 `ollama.options.presence_penalty` | Implemented | float | `Unspecified; provider default / general option inherited for code` | -2–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S135 `ollama.options.frequency_penalty` | Implemented | float | `Unspecified; provider default / general option inherited for code` | -2–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S136 `ollama.options.repeat_penalty` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S137 `ollama.code_options.num_ctx` | Implemented | int | `Unspecified; provider default / general option inherited for code` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S138 `ollama.code_options.num_thread` | Implemented | int | `Unspecified; provider default / general option inherited for code` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S139 `ollama.code_options.num_gpu` | Implemented | int | `Unspecified; provider default / general option inherited for code` | ≥0 in TOML (runtime override permits -1) | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S140 `ollama.code_options.num_predict` | Implemented | int | `max(4096, general num_predict) unless explicitly set` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S141 `ollama.code_options.top_k` | Implemented | int | `Unspecified; provider default / general option inherited for code` | >0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S142 `ollama.code_options.seed` | Implemented | int | `Unspecified; provider default / general option inherited for code` | ≥0 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S143 `ollama.code_options.temperature` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S144 `ollama.code_options.top_p` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–1 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S145 `ollama.code_options.min_p` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–1 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S146 `ollama.code_options.presence_penalty` | Implemented | float | `Unspecified; provider default / general option inherited for code` | -2–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S147 `ollama.code_options.frequency_penalty` | Implemented | float | `Unspecified; provider default / general option inherited for code` | -2–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |
| S148 `ollama.code_options.repeat_penalty` | Implemented | float | `Unspecified; provider default / general option inherited for code` | 0–2 | Global config/config.toml; Next request after config/runtime reload | No; Config file | OPTIONAL | [packages/core/src/klaude_core/config.py:_validated_ollama_options](../packages/core/src/klaude_core/config.py#L701); [packages/core/src/klaude_core/config.py:OllamaConfig](../packages/core/src/klaude_core/config.py#L434) |

### Persisted chat/runtime preferences

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S149 `runtime_device_mode` | Implemented | str | `auto` | auto \| cpu-only \| gpu-preferred \| gpu-only | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [apps/cli/src/klaude_cli/main.py:_runtime_device_mode](../apps/cli/src/klaude_cli/main.py#L1711) — Device mode and numeric GPU overrides interact; explicit GPU requirements cannot silently downgrade. |
| S150 `runtime_options.num_ctx` | Implemented | int\|null | `Unset; inherit config/calibration` | Integer ≥1; null removes override | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [apps/cli/src/klaude_cli/main.py:_load_runtime_preferences](../apps/cli/src/klaude_cli/main.py#L1696) |
| S151 `runtime_options.num_thread` | Implemented | int\|null | `Unset; inherit config/calibration` | Integer ≥1; null removes override | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [apps/cli/src/klaude_cli/main.py:_load_runtime_preferences](../apps/cli/src/klaude_cli/main.py#L1696) |
| S152 `runtime_options.num_gpu` | Implemented | int\|null | `Unset; inherit config/calibration` | Integer ≥-1; null removes override | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [apps/cli/src/klaude_cli/main.py:_load_runtime_preferences](../apps/cli/src/klaude_cli/main.py#L1696) |
| S153 `runtime_options.max_steps` | Implemented | int\|null | `Unset; config effective 20` | 1–64; null=inherited | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/agent_settings.py:EXECUTION_LIMITS](../packages/core/src/klaude_core/agent_settings.py#L7); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1) — Stored alongside native runtime overrides; execution_settings is an acknowledgement field, not the persisted container. |
| S154 `runtime_options.max_tool_calls` | Implemented | int\|null | `Unset; config effective 0` | 0–256;0=Auto; null=inherited | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/agent_settings.py:EXECUTION_LIMITS](../packages/core/src/klaude_core/agent_settings.py#L7); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1) — Stored alongside native runtime overrides; execution_settings is an acknowledgement field, not the persisted container. |
| S155 `runtime_options.max_total_tokens` | Implemented | int\|null | `Unset; config effective 0` | 0–2,000,000;0=no cap; null=inherited | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/agent_settings.py:EXECUTION_LIMITS](../packages/core/src/klaude_core/agent_settings.py#L7); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1) — Stored alongside native runtime overrides; execution_settings is an acknowledgement field, not the persisted container. |
| S156 `runtime_options.max_subagent_concurrency` | Implemented | int\|null | `Unset; config effective 0` | 0–4;0=Auto; null=inherited | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/agent_settings.py:EXECUTION_LIMITS](../packages/core/src/klaude_core/agent_settings.py#L7); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1) — Stored alongside native runtime overrides; execution_settings is an acknowledgement field, not the persisted container. |
| S157 `tool_availability.<builtin_name>` | Implemented | bool | `true` | Registered built-in names; group writes expand exact names | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/tool_settings.py](../packages/core/src/klaude_core/tool_settings.py#L1); [apps/cli/src/klaude_cli/main.py:_apply_tool_availability_preferences](../apps/cli/src/klaude_cli/main.py#L1785) |
| S158 `web_provider_availability.<provider>` | Implemented | bool | `Inherited web.providers enabled` | Known provider IDs only | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/config.py:load_config](../packages/core/src/klaude_core/config.py#L730); [apps/cli/src/klaude_cli/main.py:_apply_web_provider_preferences](../apps/cli/src/klaude_cli/main.py#L1802) |
| S159 `permissions.<tool>` | Implemented | str | `Inherited DEFAULT_PERMISSIONS/TOML` | allow \| ask \| deny; only applicable registered names | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/permissions.py](../packages/core/src/klaude_core/permissions.py#L1); [apps/cli/src/klaude_cli/main.py:_apply_saved_permissions](../apps/cli/src/klaude_cli/main.py#L1828) — Unknown/MCP tools default ask; availability remains independent. |
| S160 `display.activity_updates` | Implemented | bool | `true` | Boolean; old display.reasoning_activity accepted as fallback | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | ADAPT | [apps/cli/src/klaude_cli/main.py:_activity_updates_enabled](../apps/cli/src/klaude_cli/main.py#L1812) — Controls useful activity summaries; it is separate from terminal spinner animation. |
| S161 `composer_mode` | Implemented | str | `standard` | standard \| vim | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_composer_mode](../apps/cli/src/klaude_cli/main.py#L1823) |
| S162 `last_model` | Implemented | str\|null | `Absent; migration uses configured coder` | Qualified model reference or legacy model ID | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | INTERNAL | [packages/core/src/klaude_core/ai_defaults.py:defaults_from_preferences](../packages/core/src/klaude_core/ai_defaults.py#L47); [apps/cli/src/klaude_cli/main.py:_save_last_chat_model](../apps/cli/src/klaude_cli/main.py#L1692) — Legacy startup/migration record; AI Defaults.chat and saved session runtime are newer authoritative choices. |
| S163 `require_model_selection` | Implemented | bool | `Absent/false` | True requires explicit startup selection | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | INTERNAL | [packages/core/src/klaude_core/ai_defaults.py:defaults_from_preferences](../packages/core/src/klaude_core/ai_defaults.py#L47); [packages/core/src/klaude_core/model_management.py](../packages/core/src/klaude_core/model_management.py#L1) |
| S164 `search_settings.tavily_depth` | Implemented | str | `basic (provider config may override)` | basic \| advanced | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/search_settings.py:public_search_settings](../packages/core/src/klaude_core/search_settings.py#L55) |
| S165 `search_settings.searxng_url` | Implemented | str | `Inherited services.searxng_url` | HTTP(S)≤2048; no auth/query/fragment; valid nonzero port | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/search_settings.py:service_url](../packages/core/src/klaude_core/search_settings.py#L32) — Separate override of the same service; not a new search provider. |
| S166 `fetch_settings.crawl4ai_url` | Implemented | str | `Inherited services.crawl4ai_url` | Empty or validated HTTP(S) service URL | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/fetch_settings.py:public_fetch_settings](../packages/core/src/klaude_core/fetch_settings.py#L13) |
| S167 `ai_defaults.chat` | Implemented | str\|null | `Frozen migration of old explicit last_model or configured coder; unset can require selection` | Valid model reference or null | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S168 `ai_defaults.utility` | Implemented | str\|null | `null / unset` | Eligible explicit model; null=Same as chat | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S169 `ai_defaults.fallbacks` | Implemented | list[str] | `[]` | At most3 unique eligible model refs, excluding primary | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S170 `ai_defaults.output_tokens` | Implemented | int | `512` | 128–2048 | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S171 `ai_defaults.research` | Implemented | str\|null | `null / unset` | Eligible explicit model; null=Same as chat | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S172 `ai_defaults.vision` | Implemented | str\|null | `null / unset` | Explicit image-supported model for Media consumer | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S173 `ai_defaults.vision_enabled` | Implemented | bool | `false` | Cannot send pixels unless enabled with valid binding | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S174 `ai_defaults.vision_fallbacks` | Implemented | list[str] | `[]` | At most3 ordered explicit image-capable refs | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1) |
| S175 `research.provider` | Implemented | str | `auto` | auto or actual web provider ID | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S176 `research.output_tokens` | Implemented | int | `2048` | 256–16384 and ≤context_tokens/2 | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S177 `research.extract_timeout` | Implemented | int | `30` | 5–90 seconds | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S178 `research.parallel` | Implemented | int | `2` | 1–3 | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S179 `research.timeout` | Implemented | int | `300` | 30–3600 seconds | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S180 `research.rounds` | Implemented | int | `2` | 1–4 | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S181 `research.queries` | Implemented | int | `6` | 1–12 | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S182 `research.sources` | Implemented | int | `8` | 1–16 | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |
| S183 `research.context_tokens` | Implemented | int | `8192` | 4096–65536 | data/chat-preferences.json; After successful acknowledged save; next applicable request | Metadata / private dialogue when relevant; TUI; persisted JSON | REQUIRED | [packages/core/src/klaude_core/research.py:ResearchDefaults](../packages/core/src/klaude_core/research.py#L31); [packages/core/src/klaude_core/research.py:research_defaults](../packages/core/src/klaude_core/research.py#L58) |

### Model endpoint definitions

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S184 `connections.<id>.id` | Implemented | str | `Required` | [a-z0-9][a-z0-9_-]{0,63}; stable connection identity | config/model-connections.json; After reviewed write/reload; captured requests recheck revisions | Host/provider metadata; TUI Add/Added Models; CLI model-connections; JSON | REQUIRED | [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91); [packages/core/src/klaude_core/model_connections.py:normalize_model_url](../packages/core/src/klaude_core/model_connections.py#L48) |
| S185 `connections.<id>.name` | Implemented | str | `Required` | 1–120 printable chars | config/model-connections.json; After reviewed write/reload; captured requests recheck revisions | Host/provider metadata; TUI Add/Added Models; CLI model-connections; JSON | REQUIRED | [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91); [packages/core/src/klaude_core/model_connections.py:normalize_model_url](../packages/core/src/klaude_core/model_connections.py#L48) |
| S186 `connections.<id>.backend` | Implemented | str | `Required` | ollama \| openai_compatible \| openai_api \| openrouter \| gemini_api \| openai_codex \| deepseek \| anthropic | config/model-connections.json; After reviewed write/reload; captured requests recheck revisions | Host/provider metadata; TUI Add/Added Models; CLI model-connections; JSON | REQUIRED | [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91); [packages/core/src/klaude_core/model_connections.py:normalize_model_url](../packages/core/src/klaude_core/model_connections.py#L48) |
| S187 `connections.<id>.base_url` | Implemented | str | `Backend preset/explicit` | Normalized URL; Cloud HTTPS; no auth/query/fragment/control; Codex no URL; Gemini fixed official root | config/model-connections.json; After reviewed write/reload; captured requests recheck revisions | Host/provider metadata; TUI Add/Added Models; CLI model-connections; JSON | REQUIRED | [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91); [packages/core/src/klaude_core/model_connections.py:normalize_model_url](../packages/core/src/klaude_core/model_connections.py#L48) |
| S188 `connections.<id>.source` | Implemented | str | `Local` | Local \| Cloud | config/model-connections.json; After reviewed write/reload; captured requests recheck revisions | Host/provider metadata; TUI Add/Added Models; CLI model-connections; JSON | REQUIRED | [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91); [packages/core/src/klaude_core/model_connections.py:normalize_model_url](../packages/core/src/klaude_core/model_connections.py#L48) |
| S189 `connections.<id>.key_env` | Implemented | str | `""` | Valid environment variable reference, not raw key | config/model-connections.json; After reviewed write/reload; captured requests recheck revisions | Credential reference; TUI Add/Added Models; CLI model-connections; JSON | REQUIRED | [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91); [packages/core/src/klaude_core/model_connections.py:normalize_model_url](../packages/core/src/klaude_core/model_connections.py#L48) |
| S190 `connections.<id>.enabled` | Implemented | bool | `true` | Boolean; protected references block disable | config/model-connections.json; After reviewed write/reload; captured requests recheck revisions | Host/provider metadata; TUI Add/Added Models; CLI model-connections; JSON | REQUIRED | [packages/core/src/klaude_core/model_connections.py:ModelConnection](../packages/core/src/klaude_core/model_connections.py#L91); [packages/core/src/klaude_core/model_connections.py:normalize_model_url](../packages/core/src/klaude_core/model_connections.py#L48) |

### Per-model inventory preferences

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S191 `model_choices.<connection>.<model>.enabled` | Implemented | bool | `true` | Known model ID; max1000 choices per connection | config/model-connections.json; Next inventory/selection after acknowledged save | Model metadata; TUI Added Models; JSON | REQUIRED | [packages/core/src/klaude_core/model_management.py:choices_from_payload](../packages/core/src/klaude_core/model_management.py#L43) |
| S192 `model_choices.<connection>.<model>.hidden` | Implemented | bool | `false` | Known model ID; max1000 choices per connection | config/model-connections.json; Next inventory/selection after acknowledged save | Model metadata; TUI Added Models; JSON | REQUIRED | [packages/core/src/klaude_core/model_management.py:choices_from_payload](../packages/core/src/klaude_core/model_management.py#L43) |
| S193 `model_choices.<connection>.<model>.pinned` | Implemented | bool | `false` | Known model ID; max1000 choices per connection | config/model-connections.json; Next inventory/selection after acknowledged save | Model metadata; TUI Added Models; JSON | REQUIRED | [packages/core/src/klaude_core/model_management.py:choices_from_payload](../packages/core/src/klaude_core/model_management.py#L43) |

### SSH server definitions

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S194 `servers.<id>.definition.id` | Implemented | str | `Required` | [a-z][a-z0-9_-]{0,47}; not local | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S195 `servers.<id>.definition.name` | Implemented | str | `Required` | 1–120 printable | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S196 `servers.<id>.definition.host` | Implemented | str | `Required` | IP or DNS≤253; no URL/SSH shell syntax | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S197 `servers.<id>.definition.user` | Implemented | str | `Required` | [A-Za-z_][A-Za-z0-9_.-]{0,63} | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S198 `servers.<id>.definition.port` | Implemented | int | `22` | 1–65535 | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S199 `servers.<id>.definition.identity_file` | Implemented | str | `""` | Absolute path≤4096; no variables; required unless opted-in agent | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S200 `servers.<id>.definition.known_hosts` | Implemented | str | `""` | Required absolute verified local path≤4096 | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S201 `servers.<id>.definition.models_dir` | Implemented | str | `/opt/models` | Absolute remote path≤512; no .. traversal | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S202 `servers.<id>.definition.use_agent` | Implemented | bool | `false` | Explicit opt-in; otherwise agent omitted | config/model-servers.json; Accepted save does not connect; next explicit test/serve captures new revision | Private host/account/path metadata; TUI Servers; CLI ssh add; JSON | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:SSHServer](../packages/core/src/klaude_core/ssh_servers.py#L32) |
| S203 `default` | Implemented | str | `local` | local \| existing saved server ID; independent diagnostics default | config/model-servers.json; After acknowledged save; next Inspect default | Host reference; TUI; CLI ssh default | REQUIRED | [packages/core/src/klaude_core/ssh_servers.py:load](../packages/core/src/klaude_core/ssh_servers.py#L92) |

### MCP server definitions

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S204 `servers.<name>.name` | Implemented | str | `Required` | [a-zA-Z0-9][a-zA-Z0-9_.-]{0,63} | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S205 `servers.<name>.transport` | Implemented | str | `Infer http if URL else stdio` | stdio \| http; streamable-http/streamable_http aliases | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S206 `servers.<name>.enabled` | Implemented | bool | `true` | Stored default true; reviewed install/update lane can explicitly save false | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S207 `servers.<name>.command` | Implemented | str | `""` | Required stdio only;≤4096 printable | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S208 `servers.<name>.args` | Implemented | list[str] | `[]` | ≤256 args; each≤16384 printable; fixed argv, not implicit shell | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S209 `servers.<name>.url` | Implemented | str | `""` | Required http only;≤8192; remote HTTPS, localhost HTTP allowed; no embedded/query secrets | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S210 `servers.<name>.env` | Implemented | dict[str,str] | `{}` | ≤64 single-line entries; secret names require env-reference syntax | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S211 `servers.<name>.headers` | Implemented | dict[str,str] | `{}` | ≤64 single-line entries; sensitive values require environment refs | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S212 `servers.<name>.cwd` | Implemented | str | `""` | ≤4096 printable; stdio working directory | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S213 `servers.<name>.tools` | Implemented | list[dict] | `[]` | Cached schemas≤128; each≤100000chars; internal discovery state | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | INTERNAL | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S214 `servers.<name>.source` | Implemented | dict[str,str] | `{}` | ≤16 bounded source metadata entries; internal update provenance | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | INTERNAL | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S215 `servers.<name>.oauth` | Implemented | bool | `false` | HTTP only; incompatible with static Authorization header | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S216 `servers.<name>.oauth_scope` | Implemented | str | `""` | ≤2000 printable | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |
| S217 `servers.<name>.oauth_client_metadata_url` | Implemented | str | `""` | Credential-free HTTPS with non-root path;≤8192 | data/mcp-servers.json; Refresh/reconnect/next eligible call; enabled and revisions rechecked | Secret references/private command/header metadata; CLI mcp; TUI forms/import; JSON | REQUIRED | [packages/core/src/klaude_core/mcp_client.py:MCPServerConfig](../packages/core/src/klaude_core/mcp_client.py#L93) |

### Installed Skills

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S218 `manifest.enabled` | Implemented | bool | `true` | False disables catalog/read eligibility; old missing flag means enabled | data/skills/<name>/manifest.json; Next refreshed skill inventory/request capability | Installed instructions/provenance; TUI Manage; manifest action writer | REQUIRED | [packages/knowledge/src/klaude_knowledge/skills.py:list_installed_skills](../packages/knowledge/src/klaude_knowledge/skills.py#L256); [apps/cli/src/klaude_cli/skill_actions.py](../apps/cli/src/klaude_cli/skill_actions.py#L1) |

### Terminal appearance exclusions

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S219 `theme.interface` | Implemented | str | `pastelle-azure` | 17 TUI palette IDs; see theme map | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S220 `theme.text` | Implemented | str | `vscode-dark` | vscode-dark \| github-dark \| monokai \| solarized-light | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S221 `input_field.border` | Implemented | bool | `true` | Boolean | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S222 `input_field.min_height` | Implemented | int | `6` | 1≤min≤max≤12; writes legacy height alias too | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S223 `input_field.max_height` | Implemented | int | `6` | min≤max≤12 | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S224 `divider.visible` | Implemented | bool | `true` | Boolean | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S225 `divider.color` | Implemented | str | `same-as-input-field` | LINE_COLORS keys; see source map | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S226 `divider.text_color` | Implemented | str | `bright-black` | DIVIDER_COLORS keys | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S227 `divider.pattern` | Implemented | str | `━ ` | 1–24 visible/control-free chars | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S228 `spinner.name` | Implemented | str | `dots` | CATALOG IDs or custom | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S229 `spinner.custom_frames` | Implemented | list[str] | `dots frames` | 1–256 frames;1–256chars and1–80terminalcells each | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |
| S230 `spinner.custom_interval` | Implemented | int | `100` | 16–10000 milliseconds | data/appearance.json; After validated appearance save/preview; survives restart | No; TUI; appearance JSON | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:_load_tui_appearance](../apps/cli/src/klaude_cli/main.py#L1572); [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1); [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1) |

### Memory

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S231 `auto_memory_enabled` | Implemented | bool | `true` | SQLite 1/0; transient override while save pending | data/sessions.db settings table; Immediate client intent; confirmed DB setting shared on reload | Saved facts/private dialogue; TUI /memory/settings; CLI memory on/off | REQUIRED | [packages/core/src/klaude_core/memory.py:auto_memory_enabled](../packages/core/src/klaude_core/memory.py#L468) |

### Image-service preferences

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S232 `enabled` | Partial | bool | `false` | Enabled requires tested endpoint and pinned model | config/image-generation.json; Acknowledged save; prepare/send recheck exact model/revision | Trusted host/model metadata; AI Defaults/Media; CLI library image-service; JSON | REQUIRED | [packages/core/src/klaude_core/image_generation.py:DEFAULTS](../packages/core/src/klaude_core/image_generation.py#L29); [packages/core/src/klaude_core/image_generation.py:save](../packages/core/src/klaude_core/image_generation.py#L66) — Partial native service consumer; real model inference not yet validated in existing report. |
| S233 `endpoint` | Partial | str | `""` | HTTP(S)≤500; normalized native root; no credentials/query/fragment; trusted local/LAN | config/image-generation.json; Acknowledged save; prepare/send recheck exact model/revision | Trusted host/model metadata; AI Defaults/Media; CLI library image-service; JSON | REQUIRED | [packages/core/src/klaude_core/image_generation.py:DEFAULTS](../packages/core/src/klaude_core/image_generation.py#L29); [packages/core/src/klaude_core/image_generation.py:save](../packages/core/src/klaude_core/image_generation.py#L66) — Partial native service consumer; real model inference not yet validated in existing report. |
| S234 `model` | Partial | str | `""` | Pinned loaded model≤200printable; enabled requires nonempty | config/image-generation.json; Acknowledged save; prepare/send recheck exact model/revision | Trusted host/model metadata; AI Defaults/Media; CLI library image-service; JSON | REQUIRED | [packages/core/src/klaude_core/image_generation.py:DEFAULTS](../packages/core/src/klaude_core/image_generation.py#L29); [packages/core/src/klaude_core/image_generation.py:save](../packages/core/src/klaude_core/image_generation.py#L66) — Partial native service consumer; real model inference not yet validated in existing report. |
| S235 `revision` | Partial | str | `""` | Opaque random save revision; not a user-editable choice | config/image-generation.json; Acknowledged save; prepare/send recheck exact model/revision | Trusted host/model metadata; AI Defaults/Media; CLI library image-service; JSON | INTERNAL | [packages/core/src/klaude_core/image_generation.py:DEFAULTS](../packages/core/src/klaude_core/image_generation.py#L29); [packages/core/src/klaude_core/image_generation.py:save](../packages/core/src/klaude_core/image_generation.py#L66) — Partial native service consumer; real model inference not yet validated in existing report. |

### Serving/adoption request controls

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S236 `LaunchSpec.engine` | Implemented | str | `required` | llama_cpp \| vllm | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:149](../packages/core/src/klaude_core/managed_serving.py#L149); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S237 `LaunchSpec.executable` | Implemented | str | `required` | Installed absolute engine executable; identity/help rechecked | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:150](../packages/core/src/klaude_core/managed_serving.py#L150); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S238 `LaunchSpec.model` | Implemented | str | `required` | Absolute regular GGUF file or safetensors bundle; SSH within configured remote model root | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:151](../packages/core/src/klaude_core/managed_serving.py#L151); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S239 `LaunchSpec.name` | Implemented | str | `'Local model server'` | 1–120 printable chars | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:152](../packages/core/src/klaude_core/managed_serving.py#L152); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S240 `LaunchSpec.port` | Implemented | int | `8080` | 1024–65535; remote port in SSH flow | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:153](../packages/core/src/klaude_core/managed_serving.py#L153); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S241 `LaunchSpec.context` | Implemented | int | `8192` | 512–65536; capability/fit validation still applies | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:154](../packages/core/src/klaude_core/managed_serving.py#L154); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S242 `LaunchSpec.threads` | Implemented | int | `4` | 1–256 | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:155](../packages/core/src/klaude_core/managed_serving.py#L155); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S243 `LaunchSpec.gpu_layers` | Implemented | int | `0` | 0–999;0=CPU for llama.cpp | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:156](../packages/core/src/klaude_core/managed_serving.py#L156); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S244 `LaunchSpec.gpu` | Implemented | str | `'0'` | 1–8 distinct numeric indices0–99, freshly observed inventory | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:157](../packages/core/src/klaude_core/managed_serving.py#L157); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S245 `LaunchSpec.memory` | Implemented | float | `0.5` | 0.1–0.95 GPU memory fraction for vLLM | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:158](../packages/core/src/klaude_core/managed_serving.py#L158); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S246 `LaunchSpec.adopt_pid` | Implemented | int | `0` | 0 or reviewed exact isolated PID | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:159](../packages/core/src/klaude_core/managed_serving.py#L159); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S247 `LaunchSpec.model_id` | Implemented | str | `''` | Exact advertised ID≤200 without whitespace for adoption | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:160](../packages/core/src/klaude_core/managed_serving.py#L160); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S248 `LaunchSpec.ssh_server` | Implemented | str | `''` | Saved server ID; empty=local | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:161](../packages/core/src/klaude_core/managed_serving.py#L161); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S249 `LaunchSpec.local_port` | Implemented | int | `18080` | Reviewed loopback tunnel port1024–65535 | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:162](../packages/core/src/klaude_core/managed_serving.py#L162); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S250 `LaunchSpec.dtype` | Implemented | str | `'auto'` | auto \| half \| bfloat16 \| float32; CUDA/BF16 evidence checks | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:163](../packages/core/src/klaude_core/managed_serving.py#L163); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |
| S251 `LaunchSpec.enforce_eager` | Implemented | bool | `False` | Boolean; remote TUI starts true, CLI/LaunchSpec false | Private per-client form; accepted server job/record, not global preference; Only next explicit reviewed Start/Adopt | Host/model/process/path metadata; TUI Model Manager/Servers; CLI serve/adopt | ADAPT | [packages/core/src/klaude_core/managed_serving.py:164](../packages/core/src/klaude_core/managed_serving.py#L164); [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1) |

### Setup request controls

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S252 `build.source` | Implemented | str | `Required` | Trusted absolute committed llama.cpp checkout, not dirty working edits | Private form/accepted immutable build evidence; Next explicitly reviewed setup job | Trusted executable/source/wheel paths; TUI Dependencies; CLI build/install-vllm | ADAPT | [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1) |
| S253 `build.profile` | Implemented | str | `cpu` | cpu \| cuda; internal vllm_cuda recipe selected by vLLM install flow | Private form/accepted immutable build evidence; Next explicitly reviewed setup job | Trusted executable/source/wheel paths; TUI Dependencies; CLI build/install-vllm | ADAPT | [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1) |
| S254 `build.jobs` | Implemented | int | `2` | 1–8 | Private form/accepted immutable build evidence; Next explicitly reviewed setup job | Trusted executable/source/wheel paths; TUI Dependencies; CLI build/install-vllm | ADAPT | [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1) |
| S255 `build.architectures` | Implemented | str | `""` | Explicit installed NVCC-supported IDs; otherwise observed capabilities | Private form/accepted immutable build evidence; Next explicitly reviewed setup job | Trusted executable/source/wheel paths; TUI Dependencies; CLI build/install-vllm | ADAPT | [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1) |
| S256 `build.host_compiler` | Implemented | str | `""` | Installed compiler accepted by NVCC; no unsupported override | Private form/accepted immutable build evidence; Next explicitly reviewed setup job | Trusted executable/source/wheel paths; TUI Dependencies; CLI build/install-vllm | ADAPT | [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1) |
| S257 `vllm.wheelhouse` | Implemented | str | `Required` | Complete trusted local wheel closure with bounds | Private form/accepted immutable build evidence; Next explicitly reviewed setup job | Trusted executable/source/wheel paths; TUI Dependencies; CLI build/install-vllm | ADAPT | [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1) |
| S258 `vllm.python` | Implemented | str | `""` | Installed supported Linux Python3.10–3.13; no download | Private form/accepted immutable build evidence; Next explicitly reviewed setup job | Trusted executable/source/wheel paths; TUI Dependencies; CLI build/install-vllm | ADAPT | [packages/core/src/klaude_core/model_dependencies.py:prepare](../packages/core/src/klaude_core/model_dependencies.py#L126); [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1) |

### Media request controls

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S259 `vision.question` | Implemented | str | `Required` | 1–1000 printable chars | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |
| S260 `vision.context` | Implemented | int | `4096` | 2048–32768; provider declared maximum and conservative admission | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |
| S261 `vision.output_tokens` | Implemented | int | `512` | 128–2048; provider output/context bounds | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |
| S262 `generation.prompt` | Implemented | str | `Required` | 1–2000 printable chars; newline allowed | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |
| S263 `generation.width` | Implemented | int | `512` | 256–1024 multiple64 | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |
| S264 `generation.height` | Implemented | int | `512` | 256–1024 multiple64 | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |
| S265 `generation.steps` | Implemented | int | `20` | 1–50 | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |
| S266 `generation.seed` | Implemented | int | `-1` | -1=random resolved at review;0–4294967295 explicit | Private per-client form/accepted request; generation provenance stores reviewed values; Next reviewed analysis/generation only | Private image/question/prompt; TUI Media; CLI analyze/generate | ADAPT | [packages/core/src/klaude_core/vision.py:budget](../packages/core/src/klaude_core/vision.py#L351); [packages/core/src/klaude_core/vision.py:question_text](../packages/core/src/klaude_core/vision.py#L361); [packages/core/src/klaude_core/image_generation.py:prepare](../packages/core/src/klaude_core/image_generation.py#L159); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1) |

### Session execution selections

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S267 `plan_mode` | Implemented | bool | `false` | Boolean; affects scope, not global permission | Session runtime SQLite; plan mode is client/session in-memory state; After accepted setting/turn; immutable active request | Session model/provider metadata; TUI/slash; restore/fork; internal state | REQUIRED | [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1); [packages/core/src/klaude_core/agent.py:Agent](../packages/core/src/klaude_core/agent.py#L3864) |
| S268 `session_runtime.model` | Implemented | str | `Explicit startup selection` | Valid qualified model reference; captured connection/credential revision | Session runtime SQLite; plan mode is client/session in-memory state; After accepted setting/turn; immutable active request | Session model/provider metadata; TUI/slash; restore/fork; internal state | REQUIRED | [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1); [packages/core/src/klaude_core/session_runtime.py](../packages/core/src/klaude_core/session_runtime.py#L1) |
| S269 `session_runtime.mode` | Implemented | str | `standard` | standard \| thinking subject to model requirements | Session runtime SQLite; plan mode is client/session in-memory state; After accepted setting/turn; immutable active request | Session model/provider metadata; TUI/slash; restore/fork; internal state | REQUIRED | [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1); [packages/core/src/klaude_core/session_runtime.py](../packages/core/src/klaude_core/session_runtime.py#L1) |
| S270 `session_runtime.effort` | Implemented | str\|null | `null / unset` | minimal \| low \| medium \| high \| max when supported | Session runtime SQLite; plan mode is client/session in-memory state; After accepted setting/turn; immutable active request | Session model/provider metadata; TUI/slash; restore/fork; internal state | REQUIRED | [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1); [packages/core/src/klaude_core/session_runtime.py](../packages/core/src/klaude_core/session_runtime.py#L1) |

### Transient browsing controls

| ID / key or field family | Status | Type | Source default / effective fallback | Accepted values / validation | Persistence scope / effect | Sensitivity / exposure | WebUI | Source / dependencies and notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S271 `installed.filter` | Implemented | enum | `All` | All \| Enabled \| Disabled (MCP and Skills independently) | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [apps/cli/src/klaude_cli/installed_settings.py](../apps/cli/src/klaude_cli/installed_settings.py#L1) |
| S272 `skill_search.provider` | Implemented | str | `skillsmp` | skillsmp \| skills.sh provisional | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [apps/cli/src/klaude_cli/skill_discovery.py](../apps/cli/src/klaude_cli/skill_discovery.py#L1) |
| S273 `skill_search.sort` | Implemented | str | `stars` | stars \| recent; skills.sh uses relevance | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [apps/cli/src/klaude_cli/skill_discovery.py](../apps/cli/src/klaude_cli/skill_discovery.py#L1) |
| S274 `skill_search.page` | Implemented | int | `1` | 1–10;20results/page | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [packages/core/src/klaude_core/skill_catalog.py](../packages/core/src/klaude_core/skill_catalog.py#L1) |
| S275 `mcp_search.sort` | Implemented | str | `Registry order` | Registry order \| Name A–Z \| Name Z–A | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [apps/cli/src/klaude_cli/mcp_search_panel.py](../apps/cli/src/klaude_cli/mcp_search_panel.py#L1) |
| S276 `library.view` | Implemented | str | `sessions` | Sessions \| Knowledge \| Documents \| Research \| Media \| Archive | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1) |
| S277 `library.query` | Implemented | str | `""` | Bounded metadata query; exact CLI/query limits see §4 | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1) |
| S278 `library.sort` | Implemented | str | `newest` | newest \| oldest \| name | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1) |
| S279 `library.offset` | Implemented | int | `0` | Nonnegative100-record pages | Per-client in-memory controller/draft; not advertised as persistent preference; Immediately changes local view; does not mutate model/knowledge | Search/query metadata; TUI controls; applicable CLI options | ADAPT | [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1) |

### 3.3 Environment variables and externally owned service configuration

Environment inputs below are not all persistent UI settings. Credential variables alias the setting/connection secret reference above; do not create duplicate browser controls for the TOML and env spelling. Ambient operating-system variables are context inputs, not Klaude preferences. Child-process env values are fixed execution hygiene, not user-editable model options.

| Environment input/family | Default | Actual role | Scope / sensitivity / effect | WebUI | Source |
| --- | --- | --- | --- | --- | --- |
| `KLAUDE_HOME` | Unset; resolver defaults in §3.1 | Root fallback for config/data; evaluated during module path setup | Process/startup; changing requires constructing/restarting root-bound services; host paths private | OPTIONAL | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1) |
| `KLAUDE_CONFIG_DIR` | Unset; resolver defaults in §3.1 | Explicit config authority root | Process/startup; changing requires constructing/restarting root-bound services; host paths private | OPTIONAL | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1) |
| `KLAUDE_DATA_DIR` | Unset; resolver defaults in §3.1 | Explicit data/session/artifact root | Process/startup; changing requires constructing/restarting root-bound services; host paths private | OPTIONAL | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1) |
| `KLAUDE_WEB_PROVIDER` | quality fallback when config web.provider absent | Legacy provider preference; TOML explicit provider takes precedence | Process/env; alias of web.provider | DEPRECATED | [packages/core/src/klaude_core/config.py:load_config](../packages/core/src/klaude_core/config.py#L730) |
| `KLAUDE_CODEX_BIN` | Executable discovery when unset | External Codex broker binary override | Process/auth setup; executable trust | OPTIONAL | [packages/core/src/klaude_core/codex_auth.py](../packages/core/src/klaude_core/codex_auth.py#L1); [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1) |
| `UV` | Launching uv supplies its absolute executable path; otherwise standard installed locations | Locate the exact installer for offline vLLM setup, including managed tool caches | Non-secret process/owned-worker hint; resolved, fingerprinted and rechecked at review/execution; relative/missing explicit paths fail; does not expand child PATH or install software automatically | INTERNAL | [packages/core/src/klaude_core/model_recipes.py:wheels](../packages/core/src/klaude_core/model_recipes.py#L172); [apps/cli/src/klaude_cli/background_jobs.py](../apps/cli/src/klaude_cli/background_jobs.py#L75) |
| `KLAUDE_ONLINE_DOCS_FILE` | Resolved config/online-docs.txt | Explicit online docs seed list path | CLI/docs setup; read next invocation | OPTIONAL | [apps/cli/src/klaude_cli/main.py:_online_docs_file](../apps/cli/src/klaude_cli/main.py#L8267); [scripts/knowledge/install-online-docs.sh](../scripts/knowledge/install-online-docs.sh#L1) |
| `KLAUDE_LOG_DIR` | Repository logs directory in helper script | Online-docs helper log destination, not a universal app logging preference | scripts/knowledge/install-online-docs.sh only | OPTIONAL | [scripts/knowledge/install-online-docs.sh](../scripts/knowledge/install-online-docs.sh#L1) |
| `KLAUDE_MCP_ALLOW_WRITES` | Empty/disabled; only exact 1 enables | Enables restricted knowledge MCP ingestion mutations | Knowledge MCP process startup; permissions still workspace-bound | OPTIONAL | [packages/knowledge/src/klaude_knowledge/mcp_server.py:_mcp_writes_enabled](../packages/knowledge/src/klaude_knowledge/mcp_server.py#L24) |
| `KLAUDE_MCP_WORKSPACE` | Process cwd | Jail root for knowledge MCP local-file ingestion | Knowledge MCP process; explicit trusted host directory | OPTIONAL | [packages/knowledge/src/klaude_knowledge/mcp_server.py:main](../packages/knowledge/src/klaude_knowledge/mcp_server.py#L38) |
| `OPENAI_API_KEY` | Empty/unconfigured | OpenAI API | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `OPENROUTER_API_KEY` | Empty/unconfigured | OpenRouter | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `GEMINI_API_KEY` | Empty/unconfigured | Gemini chat and Google Grounding search | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `DEEPSEEK_API_KEY` | Empty/unconfigured | Explicit DeepSeek connection reference | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `ANTHROPIC_API_KEY` | Empty/unconfigured | Explicit Anthropic connection reference | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `BRAVE_SEARCH_API_KEY` | Empty/unconfigured | Paid Brave API; keyless Brave does not need this | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `PARALLEL_API_KEY` | Empty/unconfigured | Parallel search | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `TAVILY_API_KEY` | Empty/unconfigured | Tavily search | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `EXA_API_KEY` | Empty/unconfigured | Exa search/fetch shared reference | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `FIRECRAWL_API_KEY` | Empty/unconfigured | Firecrawl provider | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `CRAWL4AI_API_KEY` | Empty/unconfigured | Crawl4AI configured service | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `HUGGINGFACE_API_KEY` | Empty/unconfigured | HF Hub API; not automatic remote Ollama auth | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `SEARXNG_SECRET` | Empty/unconfigured | SearXNG integration/service secret with distinct service env authority | SECRET; private dotenv/env; masked entry; revisions invalidate captured requests; endpoint eligibility varies | REQUIRED | [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1); [config/examples/.env.example](../config/examples/.env.example#L1) |
| `ModelConnection.key_env / web.providers.<id>.api_key_env / MCP env refs` | Explicit arbitrary validated variable name | Dynamic environment-backed credential aliases including generated KLAUDE_MODEL_* and per-MCP secret names | SECRET; use private writer and revision checks, not public payloads | INTERNAL | [packages/core/src/klaude_core/model_connections.py](../packages/core/src/klaude_core/model_connections.py#L1); [packages/core/src/klaude_core/mcp_client.py:_resolve_values](../packages/core/src/klaude_core/mcp_client.py#L495); [packages/core/src/klaude_core/config.py:save_provider_secret](../packages/core/src/klaude_core/config.py#L204) |
| `SSH_AUTH_SOCK` | Not passed unless use_agent=true | Optional existing SSH agent socket | Host process environment; explicit SSH opt-in | INTERNAL | [packages/core/src/klaude_core/ssh_servers.py](../packages/core/src/klaude_core/ssh_servers.py#L1) |
| `HOME / PATH / SHELL / COMSPEC / LANG / LC_ALL / TZ / TERM / TERM_PROGRAM / TERMUX_VERSION / PREFIX / TMPDIR` | Inherited OS values or fixed safe child defaults | Runtime context, executable lookup, timezone and terminal diagnostics; shell tools deliberately sanitize HOME/PATH and sensitive vars | Ambient metadata; terminal identity is TUI-only; not independent application toggles | INTERNAL | [packages/core/src/klaude_core/runtime_context.py](../packages/core/src/klaude_core/runtime_context.py#L1); [packages/tools_local/src/klaude_tools/toolkit.py:run_shell](../packages/tools_local/src/klaude_tools/toolkit.py#L718) |
| `DISPLAY / WAYLAND_DISPLAY` | OS desktop session | Host artifact opener availability | Ambient host desktop; browser download should not depend on it | INTERNAL | [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1) |
| `CODEX_HOME` | External Codex default when unset | External broker auth/config location; selective broker environment handling | External dependency, sensitive account store; not a Klaude browser config field | INTERNAL | [packages/core/src/klaude_core/codex_auth.py](../packages/core/src/klaude_core/codex_auth.py#L1) |
| `HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE / HF_DATASETS_OFFLINE / HF_HUB_DISABLE_TELEMETRY / VLLM_NO_USAGE_STATS / DO_NOT_TRACK / TOKENIZERS_PARALLELISM` | Fixed by managed engine environment | Offline/telemetry/tokenizer child-process controls; provider keys and ambient GPU overrides are omitted | Fixed trusted-engine launch environment; not an OS network sandbox | INTERNAL | [packages/core/src/klaude_core/managed_serving.py](../packages/core/src/klaude_core/managed_serving.py#L1); [packages/core/src/klaude_core/ssh_serving_program.py](../packages/core/src/klaude_core/ssh_serving_program.py#L1) |
| `CUDA_VISIBLE_DEVICES and engine-specific GPU mapping` | Computed explicit reviewed device/UUID selection | Restricts engine-visible GPU selection after fresh inventory checks | Child-process env/argv; not ambient override authorization | INTERNAL | [packages/core/src/klaude_core/managed_serving.py](../packages/core/src/klaude_core/managed_serving.py#L1); [packages/core/src/klaude_core/ssh_serving_program.py](../packages/core/src/klaude_core/ssh_serving_program.py#L1) |
| `SEARXNG_BASE_URL / SEARXNG_SECRET service environment` | Compose URL http://localhost:8888/; service secret from config/searxng.env | Externally owned SearXNG container/service config | docker-compose/deploy config; separate from Agent settings | OPTIONAL | [docker-compose.yml](../docker-compose.yml#L1); [config/examples/searxng.env](../config/examples/searxng.env#L1); [deploy/searxng/settings.yml](../deploy/searxng/settings.yml#L1) |
| `Ollama daemon bind/port/GPU controls` | Externally configured; not selected here | OLLAMA_HOST and daemon resource env are not read as native Klaude config switches; Klaude uses explicit service/connection URL | External daemon/service; require separate operations if later exposed | OPTIONAL | [packages/core/src/klaude_core/ollama.py](../packages/core/src/klaude_core/ollama.py#L1); [docker-compose.yml](../docker-compose.yml#L1) |

### 3.4 Internal bounds, form state and settings that do not exist

These are backend API/implementation controls, not hidden global preference keys:
| Control family | Actual defaults/bounds | Classification / source |
| --- | --- | --- |
| SubagentBudget | children1/concurrency1; steps6 per child,8 total; tools8 per child,12 total; tokens96,000 per child/total; result8000chars. Supervisor overrides children/concurrency for accepted batch; bounded maxima in source. | INTERNAL — [packages/core/src/klaude_core/subagents.py:SubagentBudget](../packages/core/src/klaude_core/subagents.py#L106) |
| TurnGovernor | Elapsed1800s; no-progress streak3; limits checked at safe boundaries, finalization reserve. | INTERNAL — [packages/core/src/klaude_core/execution.py:TurnGovernor](../packages/core/src/klaude_core/execution.py#L69) |
| Agent scopes | standard/plan/review/init/evaluation/subagent/research; scope restricts capabilities independently of permission choices. | INTERNAL — [packages/core/src/klaude_core/capabilities.py:TurnScope](../packages/core/src/klaude_core/capabilities.py#L14) |
| Working source/context budgets | Bounded recent dialogue/excerpts, current source revision receipts, paired tool outputs and image admission. No general exposed slider for every cache/threshold. | INTERNAL — [packages/core/src/klaude_core/workspace_execution.py](../packages/core/src/klaude_core/workspace_execution.py#L1); [packages/core/src/klaude_core/working_sources.py](../packages/core/src/klaude_core/working_sources.py#L1); [packages/core/src/klaude_core/request_context.py](../packages/core/src/klaude_core/request_context.py#L1) |
| Research question and queue | Question1–1500 printable; queue≤10; explicit start/resume; accepted model/provider/revisions retained. | ADAPT — [packages/core/src/klaude_core/research.py](../packages/core/src/klaude_core/research.py#L1) |
| Media/attachment bounds | PNG/JPEG≤8MiB,≤4MP,≤4096side;≤2 distinct chat images; source bytes private; header checks are not full client decoding. | INTERNAL — [packages/core/src/klaude_core/image_content.py](../packages/core/src/klaude_core/image_content.py#L1); [packages/core/src/klaude_core/chat_images.py](../packages/core/src/klaude_core/chat_images.py#L1) |
| Native Media HTTP bounds | 90s generation;15/60/110s applicable metadata/prepare/outer workers; response1MB/event256KB/text32kchars; Anthropic raw7,500,000byte limit. | INTERNAL — [packages/core/src/klaude_core/vision.py](../packages/core/src/klaude_core/vision.py#L1); [apps/cli/src/klaude_cli/vision_panel.py](../apps/cli/src/klaude_cli/vision_panel.py#L1) |
| Library import/list/preview | 32MiB regular file import;100record pages; bounded metadata/text previews; exact typed artifact IDs; no auto-indexing. | ADAPT — [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1) |
| Owned jobs/build/servers | Different bounded per-operation workers; two live servers/client; retained builds8; serving history32; revision/time/byte/disk guards. Not user-editable arbitrary worker payloads. | INTERNAL — [apps/cli/src/klaude_cli/background_jobs.py](../apps/cli/src/klaude_cli/background_jobs.py#L1); [apps/cli/src/klaude_cli/setup_jobs.py](../apps/cli/src/klaude_cli/setup_jobs.py#L1); [apps/cli/src/klaude_cli/serving_jobs.py](../apps/cli/src/klaude_cli/serving_jobs.py#L1); [packages/core/src/klaude_core/model_dependencies.py](../packages/core/src/klaude_core/model_dependencies.py#L1) |
| Cache/provenance metadata | Endpoint checks/digests, source/credential/cache revisions, MCP schema cache, job IDs and timestamps are read-only/internal metadata, not configurable preferences. | INTERNAL — [packages/core/src/klaude_core/model_management.py](../packages/core/src/klaude_core/model_management.py#L1); [packages/core/src/klaude_core/mcp_client.py](../packages/core/src/klaude_core/mcp_client.py#L1); [packages/core/src/klaude_core/source_use.py](../packages/core/src/klaude_core/source_use.py#L1) |
| Persistent fields not implemented | No current WebUI enable/port/bind/auth setting; AI email writing style, speech and Gallery albums/layers are not existing settings. AI tags reuse existing Vision controls; no separate automatic-tagging preference exists. | Planned or outside scope — [apps/cli/src/klaude_cli/main.py:_settings_home_page](../apps/cli/src/klaude_cli/main.py#L13537); [docs/odysseus-settings-and-features-plan.md](../docs/odysseus-settings-and-features-plan.md#L1) |

## 4. CLI Commands, Slash Commands, and Keyboard Actions

### 4.1 Full CLI command tree and parameters

This table comes from **the imported live Typer/Click tree**, not the top-of-file command summary. There are 97 leaf subcommands and 12 groups including root (109 nodes total). It preserves all 240 declared arguments/options, aliases, required status, defaults and Click ranges/choices. Automatic `--help` is framework-provided, not an extra application setting. A boolean’s `--yes` affects that command’s confirmation, not permanent permissions. CLI input parameters below are not additional persistent settings unless §3 identifies their storage.

Browser mapping: model-connections → Connections; model-manager → Model Manager/Servers/Dependencies; library → Library/Media; research → Research; docs/learn/crawl/query → Knowledge; mcp/skills → Integrations; memory → Memory; sessions/session-search → Sessions; auth → Connections/authentication; status/system-info/doctor → Diagnostics; chat/ask → Chat/task composer. Shell words and paths are host-side request inputs; a browser must submit structured validated operations.

#### klaude (group)

Launch the interactive session when no subcommand is supplied.

**WebUI:** ADAPT → Chat · **Implementation:** [apps/cli/src/klaude_cli/main.py:379](../apps/cli/src/klaude_cli/main.py#L379)

**Arguments/options:** none declared beyond automatic help.

#### klaude chat

Interactive agent session in the current directory.

**WebUI:** ADAPT → Chat · **Implementation:** [apps/cli/src/klaude_cli/main.py:20054](../apps/cli/src/klaude_cli/main.py#L20054)

**Arguments/options:**

- `--model` — default=''; STRING — override the coder model
- `--legacy` — default=False; BOOL — render streamed output in legacy chunks
- `--no-tui` — default=False; BOOL — use the simple line-oriented chat without the terminal TUI

#### klaude ask

One-shot question with tools enabled.

**WebUI:** ADAPT → Chat · **Implementation:** [apps/cli/src/klaude_cli/main.py:20562](../apps/cli/src/klaude_cli/main.py#L20562)

**Arguments/options:**

- `question` — REQUIRED; STRING
- `--model` — default=''; STRING — override model

#### klaude learn

Ingest a URL or local file into the knowledge base.

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20606](../apps/cli/src/klaude_cli/main.py#L20606)

**Arguments/options:**

- `source` — REQUIRED; STRING
- `-l / --library / -c / --collection` — REQUIRED; STRING — library name

#### klaude crawl

Politely crawl same-domain pages and index them into a knowledge library.

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20627](../apps/cli/src/klaude_cli/main.py#L20627)

**Arguments/options:**

- `url` — REQUIRED; STRING
- `-l / --library / -c / --collection` — REQUIRED; STRING — library name
- `--name` — default=''; STRING — docs source name; defaults to the library
- `--max-depth` — default=-1; INT — link depth; default from config
- `--max-pages` — default=-1; INT — page cap; default from config
- `--pattern` — default='*'; STRING — fnmatch URL pattern to include
- `--include` — default=None; STRING; multiple — repeatable fnmatch URL/path include pattern
- `--exclude` — default=None; STRING; multiple — repeatable fnmatch URL/path exclude pattern
- `--sitemap` — default=False; BOOL — seed URLs from robots.txt Sitemap entries and /sitemap.xml
- `--respect-robots / --ignore-robots` — default=None; BOOL — honor robots.txt before fetching pages; default from config
- `--delay-min` — default=-1.0; FLOAT — minimum seconds between pages
- `--delay-max` — default=-1.0; FLOAT — maximum seconds between pages

#### klaude import-skill

Install a skill ZIP/folder and index its text into a knowledge library.

**WebUI:** ADAPT → Chat / Knowledge / tools · **Implementation:** [apps/cli/src/klaude_cli/main.py:20846](../apps/cli/src/klaude_cli/main.py#L20846)

**Arguments/options:**

- `source` — REQUIRED; STRING
- `-l / --library / -c / --collection` — default=''; STRING — library name; defaults to the skill name
- `--name` — default=''; STRING — installed skill name

#### klaude query

Hybrid-search the knowledge base (no LLM, raw chunks).

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20879](../apps/cli/src/klaude_cli/main.py#L20879)

**Arguments/options:**

- `question` — REQUIRED; STRING
- `-l / --library / -c / --collection` — default=''; STRING — library name; omit to search all
- `-k` — default=6; INT

#### klaude libraries

List learned knowledge libraries.

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20912](../apps/cli/src/klaude_cli/main.py#L20912)

**Arguments/options:** none declared beyond automatic help.

#### klaude collections

List learned knowledge libraries.

**WebUI:** DEPRECATED (libraries alias) · **Implementation:** [apps/cli/src/klaude_cli/main.py:20918](../apps/cli/src/klaude_cli/main.py#L20918)

**Arguments/options:** none declared beyond automatic help.

#### klaude skills

List installed assistant skills.

**WebUI:** ADAPT → Skills · **Implementation:** [apps/cli/src/klaude_cli/main.py:20924](../apps/cli/src/klaude_cli/main.py#L20924)

**Arguments/options:** none declared beyond automatic help.

#### klaude search

Web search via the configured provider.

**WebUI:** ADAPT → Search · **Implementation:** [apps/cli/src/klaude_cli/main.py:20941](../apps/cli/src/klaude_cli/main.py#L20941)

**Arguments/options:**

- `q` — REQUIRED; STRING
- `-n` — default=8; INT

#### klaude code-search

Search programming docs, code examples, and debugging references.

**WebUI:** ADAPT → Search · **Implementation:** [apps/cli/src/klaude_cli/main.py:20964](../apps/cli/src/klaude_cli/main.py#L20964)

**Arguments/options:**

- `q` — REQUIRED; STRING
- `-n` — default=8; INT

#### klaude huggingface-search

Search Hugging Face Hub models, datasets, or Spaces.

**WebUI:** ADAPT → Hugging Face · **Implementation:** [apps/cli/src/klaude_cli/main.py:20973](../apps/cli/src/klaude_cli/main.py#L20973)

**Arguments/options:**

- `repo_type` — REQUIRED; STRING — model, dataset, or space
- `query` — default=''; STRING — search query; omit for trending repos
- `-n` — default=10; INT
- `--sort` — default='downloads'; STRING

#### klaude huggingface-details

Print Hugging Face Hub metadata for a model, dataset, or Space.

**WebUI:** ADAPT → Hugging Face · **Implementation:** [apps/cli/src/klaude_cli/main.py:20993](../apps/cli/src/klaude_cli/main.py#L20993)

**Arguments/options:**

- `repo_type` — REQUIRED; STRING
- `repo_id` — REQUIRED; STRING

#### klaude huggingface-readme

Fetch a Hugging Face model card, dataset card, or Space README.

**WebUI:** ADAPT → Hugging Face · **Implementation:** [apps/cli/src/klaude_cli/main.py:21006](../apps/cli/src/klaude_cli/main.py#L21006)

**Arguments/options:**

- `repo_type` — REQUIRED; STRING
- `repo_id` — REQUIRED; STRING

#### klaude models

List every model installed in Ollama and which role klaude assigns it.

**WebUI:** ADAPT → Models · **Implementation:** [apps/cli/src/klaude_cli/main.py:21014](../apps/cli/src/klaude_cli/main.py#L21014)

**Arguments/options:** none declared beyond automatic help.

#### klaude remember

Append a durable fact to memory.md (goes into every system prompt).

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21036](../apps/cli/src/klaude_cli/main.py#L21036)

**Arguments/options:**

- `fact` — REQUIRED; STRING

#### klaude session-search

Search previous conversation sessions.

**WebUI:** ADAPT → Sessions · **Implementation:** [apps/cli/src/klaude_cli/main.py:21217](../apps/cli/src/klaude_cli/main.py#L21217)

**Arguments/options:**

- `query` — REQUIRED; STRING
- `-n` — default=8; INT

#### klaude status

Show configured modes, storage, and tool permissions.

**WebUI:** ADAPT → Diagnostics · **Implementation:** [apps/cli/src/klaude_cli/main.py:22055](../apps/cli/src/klaude_cli/main.py#L22055)

**Arguments/options:** none declared beyond automatic help.

#### klaude system-info

Show normalized runtime context diagnostics.

**WebUI:** ADAPT → Diagnostics · **Implementation:** [apps/cli/src/klaude_cli/main.py:22259](../apps/cli/src/klaude_cli/main.py#L22259)

**Arguments/options:**

- `--json` — default=False; BOOL — emit normalized context as JSON
- `--refresh` — default=False; BOOL — refresh cached stable context

#### klaude doctor

Check every service, model, and directory klaude needs.

**WebUI:** ADAPT → Diagnostics · **Implementation:** [apps/cli/src/klaude_cli/main.py:22277](../apps/cli/src/klaude_cli/main.py#L22277)

**Arguments/options:** none declared beyond automatic help.

#### klaude docs (group)

Manage refreshable documentation sources.

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20725](../apps/cli/src/klaude_cli/main.py#L20725)

**Arguments/options:** none declared beyond automatic help.

#### klaude docs add

Install a refreshable llms.txt documentation source.

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20732](../apps/cli/src/klaude_cli/main.py#L20732)

**Arguments/options:**

- `name` — REQUIRED; STRING
- `llms_url` — REQUIRED; STRING
- `-l / --library / -c / --collection` — default=''; STRING — library name; defaults to the docs source name
- `--max-pages` — default=200; INT — maximum linked docs to fetch

#### klaude docs update

Refresh installed documentation, snapshotting the old current files first.

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20775](../apps/cli/src/klaude_cli/main.py#L20775)

**Arguments/options:**

- `name` — default=''; STRING — docs source name; omit when using --sources or --all
- `--sources` — default=False; BOOL — update every installed docs source
- `--all` — default=False; BOOL — update installed docs sources and the configured online docs file
- `--online / --online-docs` — default=False; BOOL — update sources listed in the configured online docs file
- `--max-pages` — default=-1; INT — page cap; default per source

#### klaude docs list

List installed refreshable documentation sources.

**WebUI:** ADAPT → Knowledge · **Implementation:** [apps/cli/src/klaude_cli/main.py:20826](../apps/cli/src/klaude_cli/main.py#L20826)

**Arguments/options:** none declared beyond automatic help.

#### klaude memory (group)

Manage durable memory and session recall.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21049](../apps/cli/src/klaude_cli/main.py#L21049)

**Arguments/options:** none declared beyond automatic help.

#### klaude memory status

Show memory status and storage locations.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21056](../apps/cli/src/klaude_cli/main.py#L21056)

**Arguments/options:** none declared beyond automatic help.

#### klaude memory on

Enable conservative automatic memory.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21066](../apps/cli/src/klaude_cli/main.py#L21066)

**Arguments/options:** none declared beyond automatic help.

#### klaude memory off

Disable automatic memory.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21074](../apps/cli/src/klaude_cli/main.py#L21074)

**Arguments/options:** none declared beyond automatic help.

#### klaude memory list

List durable saved memories.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21082](../apps/cli/src/klaude_cli/main.py#L21082)

**Arguments/options:** none declared beyond automatic help.

#### klaude memory add

Save a durable memory.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21093](../apps/cli/src/klaude_cli/main.py#L21093)

**Arguments/options:**

- `fact` — REQUIRED; STRING

#### klaude memory forget

Remove one saved memory by exact ID or exact text.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21100](../apps/cli/src/klaude_cli/main.py#L21100)

**Arguments/options:**

- `query` — REQUIRED; STRING

#### klaude memory search

Search previous conversation sessions.

**WebUI:** ADAPT → Memory · **Implementation:** [apps/cli/src/klaude_cli/main.py:21115](../apps/cli/src/klaude_cli/main.py#L21115)

**Arguments/options:**

- `query` — REQUIRED; STRING
- `-n` — default=8; INT

#### klaude sessions (group)

Manage previous conversation sessions.

**WebUI:** ADAPT → Sessions · **Implementation:** [apps/cli/src/klaude_cli/main.py:21121](../apps/cli/src/klaude_cli/main.py#L21121)

**Arguments/options:**

- `-n` — default=10; INT
- `--archived` — default=False; BOOL

#### klaude sessions archive

Archive an idle conversation without deleting its content.

**WebUI:** ADAPT → Sessions · **Implementation:** [apps/cli/src/klaude_cli/main.py:21153](../apps/cli/src/klaude_cli/main.py#L21153)

**Arguments/options:**

- `session_id` — REQUIRED; STRING

#### klaude sessions restore

Restore an archived conversation to normal session lists.

**WebUI:** ADAPT → Sessions · **Implementation:** [apps/cli/src/klaude_cli/main.py:21159](../apps/cli/src/klaude_cli/main.py#L21159)

**Arguments/options:**

- `session_id` — REQUIRED; STRING

#### klaude sessions delete

Delete one previous conversation session.

**WebUI:** ADAPT → Sessions · **Implementation:** [apps/cli/src/klaude_cli/main.py:21165](../apps/cli/src/klaude_cli/main.py#L21165)

**Arguments/options:**

- `session_id` — REQUIRED; STRING
- `--yes / -y` — default=False; BOOL — Delete without prompting for confirmation.

#### klaude sessions clear

Delete all previous conversation sessions.

**WebUI:** ADAPT → Sessions · **Implementation:** [apps/cli/src/klaude_cli/main.py:21191](../apps/cli/src/klaude_cli/main.py#L21191)

**Arguments/options:**

- `--yes / -y` — default=False; BOOL — Delete all sessions without prompting for confirmation.

#### klaude auth (group)

Manage cloud account authentication.

**WebUI:** ADAPT → Connections/auth · **Implementation:** [apps/cli/src/klaude_cli/main.py:21295](../apps/cli/src/klaude_cli/main.py#L21295)

**Arguments/options:** none declared beyond automatic help.

#### klaude auth login

Sign in to a Cloud AI provider.

**WebUI:** ADAPT → Connections/auth · **Implementation:** [apps/cli/src/klaude_cli/main.py:21302](../apps/cli/src/klaude_cli/main.py#L21302)

**Arguments/options:**

- `provider` — REQUIRED; STRING — provider name: openai-codex

#### klaude auth status

Show Cloud AI authentication status without exposing credentials.

**WebUI:** ADAPT → Connections/auth · **Implementation:** [apps/cli/src/klaude_cli/main.py:21330](../apps/cli/src/klaude_cli/main.py#L21330)

**Arguments/options:**

- `provider` — REQUIRED; STRING — provider name: openai-codex

#### klaude auth logout

Remove credentials managed by the official Codex installation.

**WebUI:** ADAPT → Connections/auth · **Implementation:** [apps/cli/src/klaude_cli/main.py:21352](../apps/cli/src/klaude_cli/main.py#L21352)

**Arguments/options:**

- `provider` — REQUIRED; STRING — provider name: openai-codex

#### klaude mcp (group)

Connect and manage external Model Context Protocol servers.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21460](../apps/cli/src/klaude_cli/main.py#L21460)

**Arguments/options:** none declared beyond automatic help.

#### klaude mcp list

List configured MCP servers and cached tool counts.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21613](../apps/cli/src/klaude_cli/main.py#L21613)

**Arguments/options:** none declared beyond automatic help.

#### klaude mcp search

Search the official public MCP Registry without installing anything.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21643](../apps/cli/src/klaude_cli/main.py#L21643)

**Arguments/options:**

- `query` — REQUIRED; STRING
- `--limit` — default=20; <IntRange 1<=x<=50>; range=1..50 — Maximum results
- `--refresh` — default=False; BOOL — Ignore the one-hour cache

#### klaude mcp info

Show registry provenance and supported installation choices.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21675](../apps/cli/src/klaude_cli/main.py#L21675)

**Arguments/options:**

- `name` — REQUIRED; STRING
- `--refresh` — default=False; BOOL — Ignore the one-hour cache

#### klaude mcp install

Save an exact-version registry server disabled; never execute it.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21712](../apps/cli/src/klaude_cli/main.py#L21712)

**Arguments/options:**

- `registry_name` — REQUIRED; STRING
- `--name` — default=''; STRING — Local name used in Klaude
- `--transport` — default=''; STRING — Choose remote, npm, pypi, npx, or uvx
- `--refresh` — default=False; BOOL — Ignore the one-hour cache
- `--yes / -y` — default=False; BOOL — Accept the displayed plan

#### klaude mcp add

Add and verify one local or remote MCP server.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21798](../apps/cli/src/klaude_cli/main.py#L21798)

**Arguments/options:**

- `name` — REQUIRED; STRING
- `--url` — default=''; STRING — Streamable HTTP MCP endpoint
- `--command` — default=''; STRING — Local stdio server executable
- `--arg` — default=None; STRING; multiple — Repeat for each command argument
- `--env` — default=None; STRING; multiple — NAME=VALUE or NAME=${env:VARIABLE}
- `--header` — default=None; STRING; multiple — NAME=VALUE; secrets must use ${env:VARIABLE}
- `--cwd` — default=''; STRING — Working directory for a stdio server
- `--oauth` — default=False; BOOL — Configure remote OAuth + PKCE
- `--oauth-scope` — default=''; STRING — Optional OAuth scopes
- `--client-metadata-url` — default=''; STRING — Optional public HTTPS Client ID Metadata Document URL
- `--skip-test` — default=False; BOOL — Save disabled without launching or connecting
- `--yes / -y` — default=False; BOOL — Confirm this server definition

#### klaude mcp import

Import VS Code/OpenCode MCP JSON safely; imported servers start disabled.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21891](../apps/cli/src/klaude_cli/main.py#L21891)

**Arguments/options:**

- `path` — REQUIRED; <typer.models.TyperPath object at 0x7247120cec60>
- `--yes / -y` — default=False; BOOL

#### klaude mcp enable

Connect, discover tools, and enable one configured server.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21917](../apps/cli/src/klaude_cli/main.py#L21917)

**Arguments/options:**

- `name` — REQUIRED; STRING
- `--yes / -y` — default=False; BOOL — Trust and launch/connect

#### klaude mcp disable

Disable a server without deleting its configuration.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21966](../apps/cli/src/klaude_cli/main.py#L21966)

**Arguments/options:**

- `name` — REQUIRED; STRING

#### klaude mcp refresh

Refresh cached tool schemas for one or all enabled servers.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21978](../apps/cli/src/klaude_cli/main.py#L21978)

**Arguments/options:**

- `name` — default=''; STRING

#### klaude mcp remove

Remove one MCP server and its dedicated OAuth file; shared env secrets remain.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:22001](../apps/cli/src/klaude_cli/main.py#L22001)

**Arguments/options:**

- `name` — REQUIRED; STRING
- `--yes / -y` — default=False; BOOL — Skip confirmation

#### klaude mcp secret

Securely add, update, or remove an environment variable used by MCP.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:22023](../apps/cli/src/klaude_cli/main.py#L22023)

**Arguments/options:**

- `variable` — REQUIRED; STRING
- `--remove` — default=False; BOOL — Remove this saved secret
- `--yes / -y` — default=False; BOOL — Skip removal confirmation

#### klaude mcp auth (group)

Manage OAuth for remote MCP servers.

**WebUI:** ADAPT → MCPs · **Implementation:** Typer generated group; child handlers below

**Arguments/options:** none declared beyond automatic help.

#### klaude mcp auth login

Sign in to a protected remote MCP server using OAuth + PKCE.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21467](../apps/cli/src/klaude_cli/main.py#L21467)

**Arguments/options:**

- `name` — REQUIRED; STRING
- `--manual` — default=False; BOOL — Paste the final callback URL (recommended over SSH/headless sessions)
- `--open-browser / --no-open-browser` — default=True; BOOL — Open the authorization URL in the default browser
- `--scope` — default=''; STRING — Optional OAuth scopes requested from the server
- `--client-metadata-url` — default=''; STRING — Optional public HTTPS Client ID Metadata Document URL

#### klaude mcp auth status

Show non-secret OAuth state for one remote MCP server.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21570](../apps/cli/src/klaude_cli/main.py#L21570)

**Arguments/options:**

- `name` — REQUIRED; STRING

#### klaude mcp auth logout

Remove local OAuth credentials and disable the server.

**WebUI:** ADAPT → MCPs · **Implementation:** [apps/cli/src/klaude_cli/main.py:21594](../apps/cli/src/klaude_cli/main.py#L21594)

**Arguments/options:**

- `name` — REQUIRED; STRING
- `--yes / -y` — default=False; BOOL — Remove local OAuth credentials

#### klaude model-connections (group)

Register and test model endpoints.

**WebUI:** ADAPT → Connections · **Implementation:** Typer generated group; child handlers below

**Arguments/options:** none declared beyond automatic help.

#### klaude model-connections list

List endpoint identities without connecting or displaying credentials.

**WebUI:** ADAPT → Connections · **Implementation:** [apps/cli/src/klaude_cli/model_connections.py:28](../apps/cli/src/klaude_cli/model_connections.py#L28)

**Arguments/options:** none declared beyond automatic help.

#### klaude model-connections add

Register a model endpoint without generation or downloading models.

**WebUI:** ADAPT → Connections · **Implementation:** [apps/cli/src/klaude_cli/model_connections.py:53](../apps/cli/src/klaude_cli/model_connections.py#L53)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Stable lowercase connection ID
- `--adapter` — REQUIRED; STRING — ollama, openai_compatible, deepseek or anthropic
- `--url` — REQUIRED; STRING — HTTP(S) model API endpoint
- `--name` — default=''; STRING — Display name; defaults to ID
- `--key-env` — default=''; STRING — Private API-key environment reference
- `--cloud` — default=False; BOOL — Require HTTPS and use cloud budgeting

#### klaude model-connections test

Check a catalog in a cancellable worker; never generate or load a model.

**WebUI:** ADAPT → Connections · **Implementation:** [apps/cli/src/klaude_cli/model_connections.py:96](../apps/cli/src/klaude_cli/model_connections.py#L96)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Connection ID

#### klaude library (group)

Manage document and image copies; no automatic indexing.

**WebUI:** ADAPT → Library · **Implementation:** Typer generated group; child handlers below

**Arguments/options:** none declared beyond automatic help.

#### klaude library analyze

Review explicit image analysis using AI Defaults Vision; no indexing or tools.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:99](../apps/cli/src/klaude_cli/library_commands.py#L99)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact typed artifact ID from library list
- `question` — REQUIRED; STRING
- `--yes / --no-yes` — default=False; BOOL
- `--context` — default=4096; INT
- `--output-tokens` — default=512; INT

#### klaude library list

Browse metadata without reading content, calling models or indexing.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:142](../apps/cli/src/klaude_cli/library_commands.py#L142)

**Arguments/options:**

- `--type` — default='all'; STRING — all, document, media or research
- `--archived` — default=False; BOOL — Show archived copies only
- `--search` — default=''; STRING — Names, tags, file types or source paths
- `--offset` — default=0; <IntRange 0<=x<=1000000>; range=0..1000000 — Skip records; page size 100
- `--sort` — default='newest'; STRING — newest, oldest or name

#### klaude library import

Store a private copy up to 32 MiB; imported does not mean learned.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:167](../apps/cli/src/klaude_cli/library_commands.py#L167)

**Arguments/options:**

- `path` — REQUIRED; <typer.models.TyperPath object at 0x7247120ec4d0> — Regular file to copy; original retained
- `--type` — default='document'; STRING — document or media

#### klaude library info

Show bounded metadata and a text or image-metadata preview.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:177](../apps/cli/src/klaude_cli/library_commands.py#L177)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact typed artifact ID from library list

#### klaude library export

Export exact bytes; existing files are never overwritten.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:197](../apps/cli/src/klaude_cli/library_commands.py#L197)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact typed artifact ID from library list
- `destination` — REQUIRED; <typer.models.TyperPath object at 0x7247120ecc50> — New file inside current workspace

#### klaude library tags

Replace manual tags without generating tags or altering content.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:216](../apps/cli/src/klaude_cli/library_commands.py#L216)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact typed artifact ID from library list
- `value` — REQUIRED; STRING — Comma-separated tags; empty string removes tags

#### klaude library archive

Hide the managed copy; retain content for restore.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:252](../apps/cli/src/klaude_cli/library_commands.py#L252)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact typed artifact ID from library list

#### klaude library restore

Return an archived managed copy to its original view.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:258](../apps/cli/src/klaude_cli/library_commands.py#L258)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact typed artifact ID from library list

#### klaude library delete

Confirm permanent deletion of an archived managed copy.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:264](../apps/cli/src/klaude_cli/library_commands.py#L264)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact typed artifact ID from library list

#### klaude library image-service

Inspect or review/save a local image service; no generation or model loading.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:270](../apps/cli/src/klaude_cli/library_commands.py#L270)

**Arguments/options:**

- `--endpoint` — default=''; STRING — Existing stable-diffusion.cpp native server root
- `--enable / --no-enable` — default=False; BOOL — Enable this tested service explicitly
- `--disable / --no-disable` — default=False; BOOL — Disable generation; retain endpoint/model
- `--yes / --no-yes` — default=False; BOOL — Confirm saving this exact service and model

#### klaude library generate

Review one local image generation; save PNG/provenance privately in Media.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:305](../apps/cli/src/klaude_cli/library_commands.py#L305)

**Arguments/options:**

- `prompt` — REQUIRED; STRING
- `--width` — default=512; INT
- `--height` — default=512; INT
- `--steps` — default=20; INT
- `--seed` — default=-1; INT
- `--yes / --no-yes` — default=False; BOOL — Accept the exact reviewed generation and Media save

#### klaude library generation-status

Read a private local job receipt; never resubmit an unknown generation.

**WebUI:** ADAPT → Library · **Implementation:** [apps/cli/src/klaude_cli/library_commands.py:334](../apps/cli/src/klaude_cli/library_commands.py#L334)

**Arguments/options:**

- `identity` — REQUIRED; STRING
- `--cancel / --no-cancel` — default=False; BOOL
- `--recover / --no-recover` — default=False; BOOL; review completed output retrieval without resubmission
- `--refresh / --no-refresh` — default=False; BOOL; explicit exact-job server check
- `--forget / --no-forget` — default=False; BOOL; reviewed private receipt removal only
- `--abandon / --no-abandon` — default=False; BOOL; requires --forget; explicitly discard unknown/active tracking without stopping remote work
- `--yes / --no-yes` — default=False; BOOL

#### klaude library generation-jobs

**WebUI:** ADAPT → Media / Image jobs · **Implementation:** library_commands.generation_jobs

- `--offset` — INT, default 0, 0–1000; pages contain at most 100 receipts
- Local metadata only; full IDs, no prompt text or network access. CLI layout adapts to terminal width.

#### klaude library suggest-tags

**WebUI:** ADAPT → Media / tag proposal review · **Implementation:** library_commands.suggest_image_tags

- `identity` — required typed Media artifact ID
- `--save / --no-save` — BOOL, default False; explicitly retain AI suggestions after approval
- `--select` — STRING, default empty; comma-separated suggestion numbers 1–20, requires --save; empty selects all only when saving explicitly
- `--yes / --no-yes` — BOOL, default False; accept displayed operations; alone does not save
- `--context` — INT, default 4096; 2048–32768
- `--output-tokens` — INT, default 512; 128–2048
- Existing Vision model/fallback, capability, image and request bounds apply. No manual-tag replacement or indexing.

#### klaude library clear-ai-tags

**WebUI:** ADAPT → Media detail / clear AI labels · **Implementation:** library_commands.clear_image_tags

- `identity` — required typed Media artifact ID
- `--yes / --no-yes` — BOOL, default False; confirm clearing AI tags/provenance only
- Manual tags, image content, exports and learned knowledge are retained.

#### klaude research (group)

Run bounded web research and manage durable jobs.

**WebUI:** ADAPT → Research · **Implementation:** Typer generated group; child handlers below

**Arguments/options:** none declared beyond automatic help.

#### klaude research list

Read saved job metadata without model or network work.

**WebUI:** ADAPT → Research · **Implementation:** [apps/cli/src/klaude_cli/research_commands.py:110](../apps/cli/src/klaude_cli/research_commands.py#L110)

**Arguments/options:**

- `--offset` — default=0; <IntRange 0<=x<=1000000>; range=0..1000000

#### klaude research run

Create a captured job; generate and save a cited report unless queued.

**WebUI:** ADAPT → Research · **Implementation:** [apps/cli/src/klaude_cli/research_commands.py:121](../apps/cli/src/klaude_cli/research_commands.py#L121)

**Arguments/options:**

- `question` — REQUIRED; STRING — Research question
- `--model` — default=''; STRING — Qualified model override; otherwise Research/Chat default
- `--provider` — default=''; STRING — Search override; auto follows Web Search
- `--rounds` — default=0; <IntRange 0<=x<=4>; range=0..4 — Round override; 0 keeps defaults
- `--format` — default='report'; STRING — report, brief or comparison
- `--queue` — default=False; BOOL — Save without model/search work

#### klaude research resume

Resume bounded work; required evidence is fetched again.

**WebUI:** ADAPT → Research · **Implementation:** [apps/cli/src/klaude_cli/research_commands.py:166](../apps/cli/src/klaude_cli/research_commands.py#L166)

**Arguments/options:**

- `identity` — REQUIRED; STRING — Exact job ID from research list

#### klaude model-manager (group)

Manage model downloads, local serving and SSH settings.

**WebUI:** ADAPT → Model Manager · **Implementation:** Typer generated group; child handlers below

**Arguments/options:** none declared beyond automatic help.

#### klaude model-manager dependencies

Inspect local tools and test an installed engine without installation/generation.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:99](../apps/cli/src/klaude_cli/model_manager_commands.py#L99)

**Arguments/options:**

- `--engine` — default='llama_cpp'; STRING
- `--executable` — default='llama-server'; STRING

#### klaude model-manager builds

List retained local build results; interrupted records remain unverified.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:119](../apps/cli/src/klaude_cli/model_manager_commands.py#L119)

**Arguments/options:** none declared beyond automatic help.

#### klaude model-manager remove-build

Review permanent removal of one unused retained build/install; keep originals.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:134](../apps/cli/src/klaude_cli/model_manager_commands.py#L134)

**Arguments/options:**

- `identity` — REQUIRED; STRING
- `--yes / --no-yes` — default=False; BOOL

#### klaude model-manager build

Review a separate CPU/CUDA engine build from committed local llama.cpp source.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:175](../apps/cli/src/klaude_cli/model_manager_commands.py#L175)

**Arguments/options:**

- `source` — REQUIRED; STRING
- `--jobs` — default=2; <IntRange 1<=x<=8>; range=1..8
- `--yes / --no-yes` — default=False; BOOL
- `--profile` — default='cpu'; STRING
- `--architectures` — default=''; STRING
- `--host-compiler` — default=''; STRING

#### klaude model-manager install-vllm

Review a separate NVIDIA vLLM environment from trusted local wheels; no downloads.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:233](../apps/cli/src/klaude_cli/model_manager_commands.py#L233)

**Arguments/options:**

- `wheelhouse` — REQUIRED; STRING
- `--python` — default=''; STRING
- `--yes / --no-yes` — default=False; BOOL

#### klaude model-manager list

List up to 100 downloaded models on one enabled native endpoint.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:345](../apps/cli/src/klaude_cli/model_manager_commands.py#L345)

**Arguments/options:**

- `--endpoint` — default='default-ollama'; STRING
- `--offset` — default=0; <IntRange 0<=x<=1000>; range=0..1000

#### klaude model-manager status

Check catalog, loaded-model status and server version without generation.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:364](../apps/cli/src/klaude_cli/model_manager_commands.py#L364)

**Arguments/options:**

- `--endpoint` — default='default-ollama'; STRING

#### klaude model-manager pull

Review a download; do not load or select the model.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:404](../apps/cli/src/klaude_cli/model_manager_commands.py#L404)

**Arguments/options:**

- `model` — REQUIRED; STRING
- `--endpoint` — default='default-ollama'; STRING
- `--yes / --no-yes` — default=False; BOOL

#### klaude model-manager delete

Review server-side deletion; selected or loaded models are protected.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:414](../apps/cli/src/klaude_cli/model_manager_commands.py#L414)

**Arguments/options:**

- `model` — REQUIRED; STRING
- `--endpoint` — default='default-ollama'; STRING
- `--yes / --no-yes` — default=False; BOOL

#### klaude model-manager hardware

Inspect this machine's hardware, not a remote server or model-fit guarantee.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:424](../apps/cli/src/klaude_cli/model_manager_commands.py#L424)

**Arguments/options:** none declared beyond automatic help.

#### klaude model-manager search

Search up to 20 Hugging Face GGUF repositories using existing credentials.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:444](../apps/cli/src/klaude_cli/model_manager_commands.py#L444)

**Arguments/options:**

- `query` — REQUIRED; STRING

#### klaude model-manager adopt

Review ownership of a standalone server; stopping/exiting ends that process.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:489](../apps/cli/src/klaude_cli/model_manager_commands.py#L489)

**Arguments/options:**

- `pid` — REQUIRED; INT
- `model_id` — REQUIRED; STRING
- `--engine` — default='llama_cpp'; STRING
- `--executable` — default='llama-server'; STRING
- `--port` — default=8080; INT
- `--name` — default='Adopted model server'; STRING
- `--yes / --no-yes` — default=False; BOOL
- `--ssh-server` — default=''; STRING
- `--local-port` — default=18080; INT

#### klaude model-manager engines

Test an installed engine's help/flags without loading a model.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:516](../apps/cli/src/klaude_cli/model_manager_commands.py#L516)

**Arguments/options:**

- `--engine` — default='llama_cpp'; STRING
- `--executable` — default='llama-server'; STRING

#### klaude model-manager servers

List managed server records; status remains scoped to the owning client.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:523](../apps/cli/src/klaude_cli/model_manager_commands.py#L523)

**Arguments/options:** none declared beyond automatic help.

#### klaude model-manager logs

Read a bounded private log tail without adding it to model context.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:538](../apps/cli/src/klaude_cli/model_manager_commands.py#L538)

**Arguments/options:**

- `identity` — REQUIRED; STRING

#### klaude model-manager serve

Review an installed local/SSH llama.cpp or NVIDIA vLLM server; run until Ctrl+C.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/model_manager_commands.py:544](../apps/cli/src/klaude_cli/model_manager_commands.py#L544)

**Arguments/options:**

- `model` — REQUIRED; STRING
- `--engine` — default='llama_cpp'; STRING
- `--executable` — default='llama-server'; STRING
- `--name` — default='Local model server'; STRING
- `--port` — default=8080; INT
- `--context` — default=8192; INT
- `--threads` — default=4; INT
- `--gpu-layers` — default=0; INT
- `--gpu` — default='0'; STRING
- `--memory` — default=0.5; FLOAT
- `--adopt-pid` — default=0; INT
- `--model-id` — default=''; STRING
- `--yes / --no-yes` — default=False; BOOL
- `--ssh-server` — default=''; STRING
- `--local-port` — default=18080; INT
- `--dtype` — default='auto'; STRING
- `--enforce-eager / --no-enforce-eager` — default=False; BOOL

#### klaude model-manager ssh (group)

SSH definitions, reviewed key setup and server diagnostics.

**WebUI:** ADAPT → Model Manager · **Implementation:** Typer generated group; child handlers below

**Arguments/options:** none declared beyond automatic help.

#### klaude model-manager ssh list

List definitions without connecting.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:53](../apps/cli/src/klaude_cli/ssh_commands.py#L53)

**Arguments/options:** none declared beyond automatic help.

#### klaude model-manager ssh add

Save metadata and existing key/known-hosts references; test explicitly afterwards.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:72](../apps/cli/src/klaude_cli/ssh_commands.py#L72)

**Arguments/options:**

- `identity` — REQUIRED; STRING
- `--host` — REQUIRED; STRING
- `--user` — REQUIRED; STRING
- `--name` — default='SSH server'; STRING
- `--port` — default=22; <IntRange 1<=x<=65535>; range=1..65535
- `--identity-file` — default=''; STRING
- `--known-hosts` — default=''; STRING
- `--models-dir` — default='/opt/models'; STRING
- `--agent / --no-agent` — default=False; BOOL

#### klaude model-manager ssh default

Choose the diagnostics default; local means This machine.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:102](../apps/cli/src/klaude_cli/ssh_commands.py#L102)

**Arguments/options:**

- `identity` — REQUIRED; STRING

#### klaude model-manager ssh remove

Remove only settings; retain remote files/processes and local keys.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:109](../apps/cli/src/klaude_cli/ssh_commands.py#L109)

**Arguments/options:**

- `identity` — REQUIRED; STRING
- `--yes / --no-yes` — default=False; BOOL

#### klaude model-manager ssh test

Verify host key, authentication and the fixed diagnostic protocol.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:173](../apps/cli/src/klaude_cli/ssh_commands.py#L173)

**Arguments/options:**

- `identity` — REQUIRED; STRING

#### klaude model-manager ssh inspect

Read bounded remote resource/model/process metadata without mutations.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:179](../apps/cli/src/klaude_cli/ssh_commands.py#L179)

**Arguments/options:**

- `identity` — REQUIRED; STRING

#### klaude model-manager ssh host-key

Discover candidate public fingerprints; this does not establish trust.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:240](../apps/cli/src/klaude_cli/ssh_commands.py#L240)

**Arguments/options:**

- `identity` — REQUIRED; STRING

#### klaude model-manager ssh trust

Pin an independently verified host fingerprint in private app storage.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:249](../apps/cli/src/klaude_cli/ssh_commands.py#L249)

**Arguments/options:**

- `identity` — REQUIRED; STRING
- `fingerprint` — REQUIRED; STRING
- `--yes / --no-yes` — default=False; BOOL

#### klaude model-manager ssh enroll

Review and append one existing public key using current verified SSH authentication.

**WebUI:** ADAPT → Model Manager · **Implementation:** [apps/cli/src/klaude_cli/ssh_commands.py:284](../apps/cli/src/klaude_cli/ssh_commands.py#L284)

**Arguments/options:**

- `identity` — REQUIRED; STRING
- `public_key` — REQUIRED; STRING
- `--yes / --no-yes` — default=False; BOOL

### 4.2 Complete slash registry

All 44 records are retained, including usage variants and hidden exit aliases. A registry entry’s short description can lag implementation (`/library` still says “in development”); feature status above follows handlers/services, not that stale label. Browser equivalents preserve the underlying action; slash syntax need not be the only access path.

| Current usage | Registry description | Visibility / aliases | WebUI | Registry source |
| --- | --- | --- | --- | --- |
| `/help` | Show this command reference. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/init` | Create or update repository guidance in the workspace AGENTS.md. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/permission` | Open persistent ask, allow, and deny tool permission settings. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/mcp` | Search the official registry and manage MCP servers. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/plan [on\|off]` | Toggle read-only planning; disables implementation tools. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/compact` | Compact stale context now. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/recap [--ai]` | Show a deterministic recap; --ai uses the configured Utility model. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/status` | Show session, context, model, and memory status. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/debug_label` | Preview every transcript label style. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/memory [on\|off]` | Show or toggle automatic memory. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/skills` | List installed assistant skills. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/vim` | Toggle Vim composer keybindings. | public | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/new` | Start a fresh chat and clear terminal history. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/clear` | Clear only the terminal view; keep the current chat session. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/rename NAME\|--ai` | Rename this session; --ai uses the Utility model. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/fork` | Continue a copy of this conversation. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/export [PATH]` | Export this chat as Markdown. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/diff` | Show Git changes and untracked files. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/review` | Review workspace changes read-only. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/resume [SESSION_ID]` | Resume a saved conversation; list all sessions with age, ID, and name. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/library [VIEW]` | Browse Sessions, Knowledge, Documents, Research, Media and Archive; artifact storage is still in development. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/model-manager` | Open Model Manager for downloads, serving and server settings. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/keybinds` | Show keyboard shortcuts. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/settings [CATEGORY]` | Configure Appearance, Models & AI, Agent Tools, MCPs, Skills, Memory, Permissions, provider credentials, and Runtime. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/model` | Select an available Cloud or Local chat model and reasoning effort. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/model NAME` | Switch to an available Cloud or Local chat model while keeping history. | public ; aliases ['/model [NAME]'] | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/mode [standard\|thinking]` | Choose Standard or Thinking mode for the active model. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/effort` | Set Thinking-mode effort, or use /effort LEVEL directly. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/effort LEVEL` | Set a supported Thinking effort; some models also offer minimal or max. | public ; aliases ['/effort [LEVEL]'] | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/queue [TEXT]` | Show pending turns, or add a turn without interrupting the active response. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/steer TEXT` | Prioritize a new instruction and interrupt at the next safe boundary. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/cancel` | Interrupt the active response at the next safe boundary. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/start` | Start the local Ollama service after confirmation. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/restart` | Restart the local Ollama service after confirmation. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/stop` | Stop the local Ollama service after confirmation. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/refresh` | Repaint the TUI and visible chat history with current styling without changing the session. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/cd [PATH]` | Change the agent workspace directory, or show the current path. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/pwd` | Show the current agent workspace directory. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/ls [OPTIONS] [PATH ...]` | List files and directories at the given paths, or in the current workspace. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/attach PATH` | Attach a file or folder as context; @PATH also works inline. | public | ADAPT | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/theme [NAME]` | Open Theme settings for interface and text/code colors; NAME sets interface colors. | public | TUI-ONLY | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/quit` | Exit the interactive chat session. | hidden | ADAPT → close/disconnect client | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/exit` | Exit the interactive chat session. (Alternatives: /quit /q) | public | ADAPT → close/disconnect client | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |
| `/q` | Exit the interactive chat session. | hidden | ADAPT → close/disconnect client | [apps/cli/src/klaude_cli/main.py:CHAT_COMMANDS](../apps/cli/src/klaude_cli/main.py#L3089) |

### 4.3 Keyboard actions and interaction semantics

The ten registered help actions are below. Their key sequences are terminal-specific; the **send/queue/newline/steer/edit/cancel/select/help semantics** need browser-native controls and accessible shortcuts.

| Key/help action | Current behavior | WebUI equivalent/classification | Source |
| --- | --- | --- | --- |
| `Enter` | Send now, or queue behind an active turn. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3328](../apps/cli/src/klaude_cli/main.py#L3328) |
| `Alt+\` | Prioritize the input or selected queued follow-up and interrupt safely. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3329](../apps/cli/src/klaude_cli/main.py#L3329) |
| `Alt+Enter` | Insert a deliberate newline without sending. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3335](../apps/cli/src/klaude_cli/main.py#L3335) |
| `Ctrl+J` | Insert a newline when the terminal collapses modified Enter into Enter. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3341](../apps/cli/src/klaude_cli/main.py#L3341) |
| `Alt+Up` | Edit queued follow-ups; Enter saves, Alt+\ steers, empty Enter deletes. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3347](../apps/cli/src/klaude_cli/main.py#L3347) |
| `Up` | Choose the previous input or picker option. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3353](../apps/cli/src/klaude_cli/main.py#L3353) |
| `Down` | Choose the next input or picker option. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3359](../apps/cli/src/klaude_cli/main.py#L3359) |
| `Tab` | Accept or navigate slash-command suggestions. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3360](../apps/cli/src/klaude_cli/main.py#L3360) |
| `Ctrl+C` | Stop or interrupt the active response; otherwise cancel a picker or clear input. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3366](../apps/cli/src/klaude_cli/main.py#L3366) |
| `Ctrl+D` | Exit and discard any unsent input. | ADAPT (close/disconnect for exit; accessible composer/navigation for editing) | [apps/cli/src/klaude_cli/main.py:3372](../apps/cli/src/klaude_cli/main.py#L3372) |

Additional implemented bindings/gestures in `_build_key_bindings`, composer and picker controllers:

| Current action | Actual behavior / state | WebUI relevance |
| --- | --- | --- |
| Escape in nested picker | Follows visible Back first; terminal picker without parent cancels. Query/completion/secret/form modes have their own cancellation. | ADAPT: dialog/back-stack rules; preserve draft and safe review focus |
| `/` within structured panel | Starts panel search; typing can filter legacy-action pages. | ADAPT: visible filter/search field |
| Space on toggle row | Toggles available group/item; mixed group state is represented separately. | ADAPT: accessible checkbox/switch |
| PageUp/PageDown | Pages table/body/review without moving Back to a dangerous action at boundaries. | ADAPT: scrollable review/list with stable buttons |
| Up/Down | Picker/options/history selection or multiline cursor, depending on active mode. | ADAPT: normal accessible list/composer behavior |
| Left/Right | Moves through logical newline boundaries. | TUI-ONLY mechanics; browser editor handles text |
| Enter during approval | Applies typed y/n/a; empty input currently allows once. | ADAPT: explicit labeled consent controls; document current default |
| y/n/a (typed then Enter) | Yes once, No, or process Always; does not bypass scope/preflight. | ADAPT: per-request permission choice |
| Escape then Enter / Ctrl+J | Deliberate newline; supported Shift+Enter terminal sequences normalize to newline; modified Ctrl+Enter normalizes through terminal protocol mapping. | TUI-ONLY escape plumbing; retain browser multiline editing |
| Bracketed paste | Normalizes newlines; large paste marker preserves exact private payload; modal fields use normal paste. | ADAPT: upload/paste context and expandable preview |
| Mouse picker interaction | Focus/activate typed rows where terminal mouse support applies; ordinary transcript selection uses terminal behavior. | ADAPT: normal pointer/touch selection |
| Ctrl+C | Cancels most specific active job/form/input/turn; idle clears input. Cleanup gates new work. | ADAPT: explicit contextual Cancel; browser copy must remain copy |
| Ctrl+D | Exits current client and triggers owned-resource cleanup. | ADAPT: explicit disconnect/server ownership policy |
| Vim mode / Tab completion / terminal protocols | prompt_toolkit editing bindings, completion, terminal escape negotiations. | TUI-ONLY implementation; optional independent browser shortcuts |

Exact implementation: [apps/cli/src/klaude_cli/main.py:_build_key_bindings](../apps/cli/src/klaude_cli/main.py#L11412); [apps/cli/src/klaude_cli/main.py:CHAT_KEYBINDINGS](../apps/cli/src/klaude_cli/main.py#L3327); [apps/cli/src/klaude_cli/settings_panel.py:PanelState](../apps/cli/src/klaude_cli/settings_panel.py#L148).

### 4.4 Menus and review surfaces cross-check

| Menu/controller | Existing pages and actions | WebUI classification / suggested surface |
| --- | --- | --- |
| Settings home | Appearance: Theme, Input Field, Divider, Spinner; Models & AI: Models, AI Defaults, Search; Agent: Agent Tools, MCPs, Skills, Memory, Permissions; Advanced: Provider credentials, Runtime; scoped Reset appearance | ADAPT Settings; terminal appearance excluded; INTERFACE absent |
| Models | Current model/mode/effort, Add Local/API endpoint draft, Test/Add, Added Models/Probe/Clear offline, endpoint detail, enable/disable/delete reviews, model enable/hidden/pin inventory | REQUIRED Connections / model selector |
| AI Defaults | Chat, Utility + fallbacks/output/test, Research, Vision enable/model/fallbacks, image-service settings, explicit Utility session actions | REQUIRED AI Defaults; ADAPT tests/reviews |
| Search | Provider/results/fallback order/provider keys/Tavily depth/SearXNG URL; URL Fetch submenu and connection tests; Deep Research parameters/role link | REQUIRED Search settings |
| Agent Tools | Execution/advanced budgets, current usage, grouped tool switches/mixed state, tool detail and permission link, web/knowledge validation, managed MCP/Skills links | REQUIRED tools/settings; ADAPT progress |
| MCPs | Search registry/query/sort/detail/repository stars/setup inputs/install review; Add command/HTTP/bearer/OAuth; Import; Manage Filter/Reload/Update all/detail/toggle/update/removal/auth | ADAPT Integrations |
| Skills | Search source/query/sort/paging/detail/source verification/install; Import/drop inbox; Manage Filter/Reload/Update all/detail/toggle/update/delete | ADAPT Integrations |
| Memory/Permissions | Facts list/search/add/edit/delete; automatic capture; presets/per-tool/MCP server group policies; reset/custom states | REQUIRED Memory and Permissions |
| Runtime/Providers | Placement/threads/context/GPU hints/calibration; masked key entry/update/removal; validation/error/save states | REQUIRED runtime/connections |
| Library | Six durable-information views; search/filter/paging/detail; session resume/fork/rename/archive/delete/export; knowledge hybrid queries/sources/learn/refresh; artifacts import/preview/open/export/tags/archive/restore/delete; report Learn | ADAPT Library |
| Research | Defaults/question/model/provider/rounds/format/queue; exact review; active elapsed/progress/Cancel; complete/partial/error; saved report/resume | ADAPT Research |
| Media Vision | Private question/budgets, image/model review, role settings return with retained draft, elapsed result/cancel/error; no automatic saving | ADAPT Media analysis |
| Media generation | Service draft/Test/pinned model/Save/Reload; prompt/size/steps/seed; exact review; task/status/cancel/result; artifact/provenance | ADAPT; partial live validation |
| Model Manager | Ollama endpoint/inventory/loaded/pull/delete/search/hardware; engine preflight/Serve draft/review/startup/cancel; server detail/logs/Stop/adoption | ADAPT Model Manager |
| Dependencies | CPU/CUDA source recipes, offline vLLM wheel closure/Python, paged trust reviews, setup task/cancel/logs/retained builds/removal/Serve handoff | ADAPT setup workflows |
| Servers/SSH | This machine/default diagnostics; saved definitions/save/test/inspect/default/remove; key scan/fingerprint trust/enrollment; remote Engine/CPU/GPU/vLLM Serve; remote adoption/review/tunnel/startup/Stop | ADAPT Servers / remote resources |
| Approval/input brokers | Tool decision, plan approval, structured user question/options, secret input, settings input, pending queue edit | ADAPT request-correlated dialogs/composer |

Sources: [apps/cli/src/klaude_cli/main.py:_settings_home_page](../apps/cli/src/klaude_cli/main.py#L13537); [apps/cli/src/klaude_cli/model_settings.py:ModelSettings](../apps/cli/src/klaude_cli/model_settings.py#L282); [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1); [apps/cli/src/klaude_cli/agent_settings.py](../apps/cli/src/klaude_cli/agent_settings.py#L1); [apps/cli/src/klaude_cli/search_settings.py](../apps/cli/src/klaude_cli/search_settings.py#L1); [apps/cli/src/klaude_cli/fetch_settings.py](../apps/cli/src/klaude_cli/fetch_settings.py#L1); [apps/cli/src/klaude_cli/mcp_management.py](../apps/cli/src/klaude_cli/mcp_management.py#L1); [apps/cli/src/klaude_cli/skill_discovery.py](../apps/cli/src/klaude_cli/skill_discovery.py#L1); [apps/cli/src/klaude_cli/skills_panel.py](../apps/cli/src/klaude_cli/skills_panel.py#L1); [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1); [apps/cli/src/klaude_cli/library_knowledge_panel.py](../apps/cli/src/klaude_cli/library_knowledge_panel.py#L1); [apps/cli/src/klaude_cli/research_panel.py](../apps/cli/src/klaude_cli/research_panel.py#L1); [apps/cli/src/klaude_cli/vision_panel.py](../apps/cli/src/klaude_cli/vision_panel.py#L1); [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1); [apps/cli/src/klaude_cli/model_manager.py](../apps/cli/src/klaude_cli/model_manager.py#L1); [apps/cli/src/klaude_cli/dependency_panel.py](../apps/cli/src/klaude_cli/dependency_panel.py#L1); [apps/cli/src/klaude_cli/ssh_panel.py](../apps/cli/src/klaude_cli/ssh_panel.py#L1).

## 5. Core User Workflows

These are current supported sequences, not a WebUI implementation plan. A browser interaction must preserve acceptance/review, ownership, cancellation, failure and persistence boundaries.

### W01. First launch and connect a model

1. Install Python/uv workspace or distribution; choose explicit bootstrap only if desired. Bootstrap can use existing/system/Docker/remote/skipped Ollama and skip model pulls. It is not automatically executed by chat.
2. Resolve config/data and load private settings. Select model from explicit session/default choice or open selection when required. Missing daemon, missing SDK, absent key/catalog/model or disabled connection is an actionable state, not permission to select a different model.
3. For Ollama use Models → Add Local Models or validated connection CLI with native/compatible backend and exact URL. Test catalog, review identity, Add; download via native Model Manager only if needed.
4. For cloud choose actual provider/backend; enter a private key reference/secret or use explicit Codex auth. Test catalogs and choose qualified model. Required Thinking/capability constraints can disable incompatible controls.
5. Set Default Chat for future sessions separately from current model. Native Ollama embeddings may still be required for Knowledge even when chat is cloud-backed. New client must not silently enable Vision or image generation.

### W02. Open a project and request code changes

1. Choose host workspace/cwd (`/cd` in TUI); inspect actual files/Git state and bounded AGENTS guidance.
2. Clean Git checkout can enter an owned Klaude work branch; dirty user tree locks write tools and mutation commands. Do not stash/reset/commit user-owned work to clear the gate.
3. Submit multi-file request or use plan mode. Plan scope stays read-only; a conversational approval can continue implementation under normal per-tool policies after leaving Plan mode with `/plan off`; it does not override the read-only Plan scope.
4. Observe actual selected tools/calls/worker events. Approve only the exact request if Ask; deny or cancel leaves corresponding constraints intact.
5. Review structured edit/diff metadata and shell exit/validation results. A failed edit/command should trigger bounded repair/revalidation, not a success banner. Execution budget/no-progress/cancellation may end partial; final description must match observed state.
6. Use `/diff` and read-only `/review` or their browser equivalents. Existing automatic scoped Git commits are source behavior; there is no documented persistent “disable auto-commit” settings field to invent.

### W03. Approvals and clarifications

1. Agent/preflight emits a correlated permission or structured input request. TUI can remain navigable, including session navigation.
2. User chooses allow once, deny, temporary Always, or an input option/custom response; secrets use masked fields and are not conversation text.
3. Recheck active session/turn, scope, tool availability and definitions before execution. Browser stale dialogs must not approve another client’s new request.
4. Cancel wakes waiting work and performs owned cleanup; a completed external side effect cannot be rolled back by claiming cancellation.

### W04. Session continuity and concurrent clients

1. Create `/new` or resume selected active/archived-eligible session; `/clear` is presentation clearing, not deletion.
2. Restore public history, private continuation and explicit model/mode/effort revisions; stale endpoint/key requires explicit reselection. Fork creates a new session retaining state; rename manually or explicitly use bounded Utility.
3. A live writer owns a renewable lease; another client can watch sanitized events and live/client snapshots. Poll/cursor reconciliation handles new completed turns and expired owners. No cloud account synchronization is implied.
4. During active work, queue follow-ups or steer; edit/delete pending entries. Draft/queue visibility snapshots are not a general restart-safe scheduler.
5. Archive/restore or reviewed permanent delete. Export public Markdown; **there is no public session import workflow**. No verified completed-message edit/retry/branch-at-message UI exists.

### W05. Manage knowledge and saved information

1. Choose Library → Knowledge, list existing named libraries, query raw hybrid hits or explicitly Learn URL/file/report. Keep Library → Documents private import separate.
2. Ingest uses configured embedding model; failures do not publish a half-current snapshot. Query results preserve source/relevance and may honestly return no relevant evidence.
3. Add a managed docs/llms.txt or crawl source; choose library/depth/pages/patterns/robots/delays, review action and observe progress/error/partial states.
4. Refresh explicitly, selected/all/online as supported by CLI. Do not assume helper seed lists have already been downloaded or indexed.
5. Saving a document/media/research artifact does not automatically teach the AI; explicit report learning creates independent knowledge content. No universal knowledge-library archive/export/import lifecycle matching artifact actions is implemented.

### W06. Skills and MCPs

1. Skills: search chosen source, inspect declared source/description/metric, resolve original pinned GitHub folder, review trust/content/name/library, install/index; or import local package/drop file.
2. Manage uses Filter above inventories; Reload, Update all and detail reviews; enable/disable is separate from tool permissions. Unverified/local sources cannot promise remote update support.
3. MCP: search official registry or manually define stdio/Streamable HTTP; review exact command/args/cwd/env or URL/auth scope. New reviewed installs/updates can stay disabled until explicit enable.
4. Provide environment-backed secret, bearer header or OAuth login; remote auth can fail/cancel independently of server definition. OAuth callback is host-local with fixed current callback port.
5. Refresh actual schema; tools appear namespaced with owning server, permissions and scope. Installed/advertised tools are not necessarily callable on every turn. Inspect errors, disable/remove safely; no remote metadata is a trust guarantee.

### W07. Research

1. Configure Research role or Same as chat, Search provider/fallbacks and bounded research defaults.
2. Enter question, select explicit applicable overrides/format; queue saves metadata only, or review/start now.
3. Worker performs bounded rounds/search/extract/synthesis with progress. Cancel/error/partial outcomes remain distinct; partial CLI outcome exits2.
4. Save report/provenance in Library Research; preview/export/tag/archive separately. Resume re-fetches source URLs; saved receipts alone never become evidence. Explicit Learn report indexes a chosen copy.

### W08. Model Manager and local serving

1. Select native Ollama endpoint for installed/loaded inventory, pull/delete/search. Review exact model/server; loaded/role/session references block deletion; pull progress and unknown outcomes are visible.
2. For llama.cpp/vLLM inspect installed executable/capabilities. Select regular local weights; configure bounded context/threads/GPU settings and review exact launch. Missing GPU/device evidence or incompatible BF16 fails explicitly.
3. Start helper-owned server, watch startup/cancel. Only owned listener + health + exact model permits compatible endpoint publication; choose that model explicitly afterward.
4. Stop via reviewed action or foreground Ctrl+C; retain weights/roles/history. Logs are bounded/private/redacted. Client ownership and two-server limit are current semantics, not unattended service hosting.
5. If engine absent, Dependencies can build trusted committed local CPU/CUDA source or install trusted complete offline vLLM wheels into a new retained setup. Review disk/trust/tool revisions. Cancel waits compiler group cleanup; partial build files remain.
6. Review removal of unused retained setup; references/process checks can block it, incomplete process inspection is visible. Original source/wheels/model weights are independent.

### W09. SSH resources, remote serving and adoption

1. Save definition without connecting; choose strict verified known_hosts and existing key or explicit agent. Diagnostics default is independent of model defaults/endpoints.
2. Optional key scan yields untrusted Ed25519 candidates; independently verify fingerprint before Trust. Enroll an existing public key only using already authenticated reviewed operation; no password/bootstrap/keygen wizard is implemented.
3. Test connection then Inspect bounded CPU/RAM/disk/model/process metadata; stale/error status invalidates old checks. GPU remains unchecked by general diagnostics.
4. Remote Serve chooses llama.cpp GGUF or vLLM bundle/executable, exact remote and local tunnel ports, fresh devices/UUIDs and explicit resource controls. Review Start; fixed SSH program and lease supervise owned engine group.
5. Ready requires remote listener, local owned tunnel, health/model and captured definition/credential checks. Lost lease/channel ends group; cleanup receipt can be unconfirmed, never fabricated.
6. Adoption first inspects exact same-account isolated process identity and healthy listener without mutation. Confirmed takeover requires acknowledgement; failed takeover leaves external process running. Original logs stay unattached; successful adoption then uses owned Stop/lease lifecycle.

### W10. Artifacts, images and generation

1. Import a regular document/media file into private Library; original retained, stored checksum/revision assigned. Browse/filter/preview metadata, export new file, or open explicit host copy. Browser requires upload/download/preview adapters.
2. Manually tag; archive hides but keeps bytes; restore re-exposes; permanent delete requires archived state and confirmation. Research/generated artifacts use same lifecycle with separate provenance/jobs.
3. To analyze: enable Vision explicitly, choose exact supported model/fallbacks, enter private question/budgets, review exact image/model/endpoints, run/cancel. Result stays private/unsaved and does not index/tag/chat.
4. To send chat pixels: active Chat model itself must declare support, Vision policy enabled, file snapshots within bounds. At most2 images; no automatic model switch. Follow-up/resume uses private immutable snapshots if still available; endpoint/key changes require reattachment.
5. To generate: an **existing** native stable-diffusion.cpp service is required. Test capability-only draft, Save pinned model + enabled state, enter prompt/size/steps/seed, review and submit one job. Inspect job-specific progress/cancel/status, then Library result/provenance. No global-stop/retry fallback. Real diffusion-server inference remains unverified by this audit/prior gate.

### W11. Failure and recovery

- Distinguish empty list, unavailable server, missing credential, unsupported capability, stale revision, permission denial, dirty-tree protection, rate limit, malformed response, validation failure, cancelled, partial and unknown side effect.
- Reload/review again after stale identity/digest/key/definition, rather than replaying old permission or silently switching models.
- Failed attachment preparation preserves prompt/attachments for retry; clean one-shot preparation failure exits1. Tool pairs/private continuation and actual source/pixel availability govern resumed requests.
- Work is accepted only into its captured root/session/draft scope; stale background results must not replace another session/form. Cleanup gates conflicting work; server process/group ownership is explicit.
- Scope of each timeout/retry differs; do not create a second browser retry loop around non-idempotent pull/serve/write/enroll/generate operations.

## 6. TUI-Only Features to Exclude

**16 explicit exclusions** below (13 terminal preference keys and three terminal behavior groups). This does not remove equivalent functionality such as composing text, viewing progress, navigating dialogs or cancelling work.

| ID | Excluded existing setting/behavior | Reason |
| --- | --- | --- |
| X01 | `theme.interface` | ANSI/prompt_toolkit interface palette; browser has own Material colors |
| X02 | `theme.text` | Terminal Pygments theme selection; browser code styling is independent |
| X03 | `input_field.border` | Terminal border drawing |
| X04 | `input_field.min_height` | Terminal line count; browser composer sizing is independent |
| X05 | `input_field.max_height` | Terminal maximum line count |
| X06 | `divider.visible` | Terminal transcript divider visibility |
| X07 | `divider.color` | Terminal rail/ANSI color |
| X08 | `divider.text_color` | Terminal divider annotation color |
| X09 | `divider.pattern` | Repeated terminal cell pattern |
| X10 | `spinner.name` | Terminal character animation catalog |
| X11 | `spinner.custom_frames` | Terminal animation cell frames |
| X12 | `spinner.custom_interval` | Terminal spinner interval |
| X13 | `composer_mode=vim` | prompt_toolkit Vim editing; independent browser shortcut policy |
| X14 | `Terminal scrollback/surface lifecycle` | Printing completed transcript to emulator scrollback and terminal clearing, not browser history semantics |
| X15 | `Terminal key/mouse/escape plumbing` | Kitty/xterm/ANSI negotiation, bracketed-paste marker rendering, terminal cell widths and emulator mouse capture; preserve actions/content |
| X16 | `/refresh and /debug_label rendering` | Repaint and animation/status label test; retain real Diagnostics/activity separately |

## 7. Features Requiring WebUI Adaptation

| Existing boundary | Browser-native equivalent required | Semantics to retain |
| --- | --- | --- |
| Text streaming, Rich Markdown/tool output | Sanitized message/event stream; expandable tool/command output; escaped code/log text | Public/private separation; partial/error/cancel; bounded payloads; no HTML/ANSI execution |
| Tool permission/input/secret prompts; conversational plan approval | Correlated accessible dialogs/forms | Exact captured request; stable Back/No focus; no stale approval; secret redaction |
| `/attach`, host file paths, folder context | Explicit host picker versus browser upload; bounded previews | Workspace jail versus user-selected attachment; no browser path trust; immutable images |
| `/diff`, review, scoped edits and shell | Change review, approval, validation/command output views | Dirty-tree/write lock/preflight; exact diffs/exit codes; tools not unconstrained remote shell |
| Model discovery and settings saves | Cancellable forms with Test/Save and visible current/pending/unconfirmed values | No automatic selection/model switch; definition/key revisions; separate connection/default/session roles |
| Library import/export/open | Upload/download and safe browser viewers | Checksum/revision/no-overwrite; independent artifact/knowledge lifecycle; untrusted MIME/text |
| Worker elapsed/progress/cancel | Server-owned operation IDs with scoped subscriptions | Owned cleanup/reaping; cancellation ≠ rollback; no duplicated submission on reconnect |
| Managed engines/SSH foreground lifetime | Deliberately specified backend resource owner | Tab closure ≠ arbitrary process ownership; preserve ready/stop/lease/receipt distinctions |
| OAuth browser launch and callback | Auth flow appropriate to host/browser origin | Host token custody, callback ownership, user account linking; current fixed8765 constraint |
| Session watches/drafts/queue | Client identity, writer ownership and cursor reconciliation | Existing lease/events public serialization; drafts privacy; reconnect does not restart task blindly |
| Settings categories and picker search | Responsive accessible navigation, forms/filter/table controls | Logical grouping, disabled reasons, safe confirmation, exact statuses; avoid terminal key mimicry |
| OS service control and host desktop actions | Explicit privileged host operation or documented unavailable action | Sudo/password boundary; no credentials in chat; browser is not host desktop |

## 8. Existing Backend Architecture and Reusable Components

### 8.1 Confirmed service and adapter boundaries

| Layer | Existing reusable interfaces | Current coupling / integration note |
| --- | --- | --- |
| Core Agent | `Agent.run` event iteration, registered `Tool`, capability snapshots, scopes, Governor, working sources, validation receipts, transport cancellation | CLI constructs tools/selectors/context and owns many brokers; extracting adapter seams should preserve semantics, not duplicate execution |
| Provider runtimes | `ModelRuntime`, native Ollama, Compatible/DeepSeek/Anthropic adapters, OpenAI/OpenRouter/Gemini/Codex transports; normalized capabilities/usage/errors | Optional SDKs/auth broker and exact image-profile evidence; no universal capability inference |
| Permissions/workspace | `PermissionGate`, tool preflight, jailed Workspace, command classification, Linux Landlock, repository mutation flock and dirty-tree guard | Policy grant alone cannot override scope/path/preflight; permission prompts currently UI callbacks |
| Session/memory | `Memory` public/private turns, transactions, names/archive, runtime selection, event cursors/live snapshots/client records/writer lease | Durable SQLite coordination exists; public HTTP DTO/event schemas and account authorization do not |
| Settings/config | `load_config`, `settings_store`, connection/AI defaults/SSH/model maintenance services and private revisioned secret writer | Multiple authorities and partial hot-update logic; TUI settings writer acknowledgements not a network API |
| Knowledge | `Knowledge`, `KnowledgeIndexer`, `KnowledgeStore`, docs/skills installers, atomic owner snapshots | Embedding/runtime and FTS/LanceDB lifetimes need ownership; higher-level Library Knowledge operations partly in CLI |
| Web | `Web.search_detailed`, fetch/probe/crawler, SourceRegistry, TTL cache, provider routing/metadata | Search-result discovery and fetched evidence distinct; public URL trust boundary not interchangeable with trusted service URL config |
| Research/artifacts | `ResearchStore`, bounded research pipeline, `ArtifactStore` with SQLite content BLOBs and provenance, Vision and image-generation services | TUI workers/reviews/scope checks are important; no automatic library ingestion |
| Model Manager/setup | `ollama_manager`, `managed_serving`, `model_dependencies`, `model_recipes`, `model_setup_removal`, SSH services/programs | Local process/helper ownership and trusted-code operations; Linux scope; not generalized cloud orchestration |
| UI infrastructure | `PanelPage/Row/Action/State`, owned background/setup/serving jobs, settings/session/skill/MCP writers and session IO coordinator | Logical metadata/action contracts useful; prompt_toolkit surface, local callbacks, drafts/picker caches and client resource lifetime require adapters |
| Restricted MCP servers | Web and knowledge MCP entrypoints | Tool-oriented integration; neither runs full Chat Agent or serves browser assets |

### 8.2 Event streams, state and ownership

- Core `AgentEvent`/tool/subagent events are in-process objects/generator events. Runtime streaming has provider-specific deltas/termination/private continuation. Browser streaming transport, schema versioning, backpressure and reconnect are **not yet implemented**.
- `Memory` stores public `content` separately from owner-private `model_content`; private data can contain image references/provider continuation/reasoning state. Session events have IDs/cursors/session/client/turn/kind/payload, with bounded retention. Session IO also loads private history internally; it is not a public serialized response.
- `session_live` and `session_clients` hold owner lease, revisions, active turn state, partial public text and client draft/queue snapshots. Writer lease acquisition/renew/release and crash recovery are already implemented; do not introduce a conflicting second session lock.
- Client controllers still own pending deque consumption, attachment preparations, form drafts, selected/filter/sort/page state, brokers, caches, timers, cancellation events, workers and serving helper handles. Some draft/queue data is mirrored for presence, not a durable independent execution engine.
- Owned worker IPC uses bounded metadata/results and additive progress events. Disposable metadata jobs differ from long-lived lease-owned serving helpers. Requests capture root/session/draft/request and definition/credential revisions; late results are rejected.
- Writes have several scopes: per-session SQLite ownership; private JSON `fcntl` field locks; serialized settings/session/MCP/skill writers; repository mutation flock for Workspace tool edits; index/build/serving inventory locks. These are **not one universal transaction across filesystem, Git, DB, remote server and UI**.

### 8.3 Persistence and lifecycle map

| Authority (resolved root) | Content / lifecycle | Browser integration consideration |
| --- | --- | --- |
| config/config.toml | Global service/model/agent/search/fetch/runtime/crawler inputs | Loader validation and process reload boundary; examples are not active settings |
| config/.env + .env.revisions.json | Private credentials plus opaque revisions/tombstones | Never expose value/revision as authentication; setters need trusted host-side authorization |
| config/model-connections.json | Connections, per-model choices, checks/cache metadata | Protected role refs, stable IDs, revisions; probe does not generate |
| config/model-servers.json + trusted pin material | SSH definitions/default revisions and explicit trust references | Read/write != connect; host-key trust and existing credentials are separate |
| config/image-generation.json | Off-by-default service binding/pinned model/revision | Independent of Chat/Search/Vision/server-host toggle |
| data/appearance.json | Terminal-only visual keys | Preserve for TUI; do not mix browser appearance |
| data/chat-preferences.json | Runtime/execution, defaults, permissions/tool availability, Search/Fetch/Research/composer preferences | Field-scoped merge, acknowledgement and freshness |
| data/sessions.db (+ WAL sidecars), memory.md | Public/private turns, session names/archive/live/events/clients/runtime, memory flag/facts | Shared local store, secret/private data, cursor/lease semantics; no network account ACL |
| data/library/artifacts.db | Private artifact metadata and **content BLOBs**; generated image provenance; Research job/report-related storage | Byte access must use content/revision/checksum gates; session deletion does not erase independent artifact copies |
| data/knowledge.lance and FTS/source stores, docs-cache/docs-sources/skills | Indexed knowledge, original normalized text/version manifests, installed Skill copies | Lifecycles differ from artifact archive; owner snapshots and embedding model dependence |
| data/webcache.db, entities.sqlite, web-provider-state.json | TTL search/fetch cache, entity aliases/claims, provider cooldown/quota metadata | Sensitive queries may persist locally; no assumption every cache has public clear/export setting |
| data/mcp-servers.json, mcp-registry-cache.json, mcp-auth | Definitions/schema/source/cache and private OAuth tokens | Local third-party code/server trust; no token exposure |
| data/model-builds and serving records/log paths | Trusted setup snapshots/venvs/executables and bounded owned server records/logs | Reviewed removal/protected refs; host filesystem changes need real validation |
| data/image-generation/UUID.json | Private generation job receipt and remote/artifact association | Remote outcome can outlive worker; status local-only; no automatic resubmit |

Exact names/paths are owned by source resolvers; arbitrary host paths and environment overrides mean the browser should not construct them from user strings. Persistence internals are useful adapter contracts, not a replacement for service calls.

## 9. WebUI Readiness Gaps

### Confirmed current gaps / constraints

1. **No browser host or full agent API.** INTERFACE hosting preference, static UI, browser auth/session transport, agent command endpoints, streaming subscriptions and safe upload/download routes do not exist. Existing model HTTP/MCP callback/listeners serve other purposes.
2. **CLI orchestration coupling.** Tool registration/selection, project prompts, permission/input brokers and significant session/worker orchestration remain in `klaude_cli.main`; a reusable service façade for full interaction has not been extracted.
3. **Settings authorities are distributed.** Config/TOML, private dotenv/revisions, JSON registries/preferences and SQLite settings have different validation and reload behavior. Some legacy/compatibility fields and stale help descriptions remain. There is no single complete external schema or API.
4. **Browser security/multi-user policy absent.** Existing local private-file modes and same-account process checks are designed for local clients. They do not provide HTTP user identity, browser origin/CSRF policy or authorization per workspace/session/resource.
5. **Lifecycle tied to launching clients.** Ready managed servers, SSH channels, accepted jobs, cancellation and cleanup are owned by existing processes/helpers. Hosting Disable, tab closure, reconnect and multiple browser tabs need explicit semantics before exposure.
6. **Public/private payload separation is not a browser serializer.** Private model_content, raw auth/storage paths, image bytes and worker payloads must not be serialized indiscriminately. Existing UI uses sanitized public views.
7. **Cross-client support has a defined scope.** Session event/watch/lease support is real, but there is no general remote account sync, multi-user ACL, or transaction serializing every model operation and concurrent Git checkout change. Repository tool mutations do have a flock; preserve it.
8. **Some requested interaction expectations are absent.** No public conversation import or completed-message edit/retry/branch-at-message UI; no general PTY terminal; no photo canvas/layers; speech/email writing consumers deferred. Optional AI tags are implemented as described in F098. Do not label these implemented by analogy to other products.
9. **Provider and hardware validation remains scoped.** Implemented cloud/vision adapters do not imply all paid providers/models were live-tested. Native generation’s real diffusion gate remains open; Linux/loopback SSH validation is not universal LAN/GPU certification.
10. **Coding success remains model-dependent.** Prior benchmark failure for small local models is a known limitation; planner/repair/validation infrastructure improves orchestration but does not prove full task semantics. This audit did not repeat that benchmark.

### Potential risks and preliminary integration recommendations (not newly observed vulnerabilities)

- Browser exposure increases the impact of local shell/file/SSH/model management. Define auth, same-origin/CSRF and streaming-origin controls, session ownership and permission request correlation before enabling routes; loopback binding alone is not an authorization mechanism.
- Treat generated Markdown, source HTML, MCP catalog text, logs, filenames, image metadata and remote output as untrusted data. Escape/sanitize rendering; do not execute tool output or widen URL access to privileged local services.
- Keep explicit trusted endpoint URLs separate from public `fetch_url` destinations. Prevent a generic browser fetch/proxy route from bypassing existing public URL/DNS/redirect guards.
- Preserve jailed path resolution, secret-file restrictions, dirty-tree lockout, Linux shell limitations, Git mutation locks, declared capability checks and role/deletion protections in the backend; UI disabled buttons are not enforcement.
- Bound event/result/upload/download sizes; reconnect with event cursor and current state, not replayed non-idempotent commands. Require fresh review after revised credentials/endpoints/model digests/file/process identities.
- Specify background task/server ownership independently from page navigation and client disconnect. Never turn a Stop/Cancel uncertainty into a claimed rollback; retain operation IDs and recovery evidence.
- Reuse the existing Agent/services, runtime adapters, event/lease/revision logic and validation services. Adapt UI-dependent brokers and writers; do not copy their policy into a second browser agent implementation.
- Frontend framework, final component architecture, server binding/port, auth scheme, startup integration and WebUI toggle defaults remain architecture-planning decisions outside this document.

## 10. Proposed WebUI Feature and Settings Grouping

Preliminary logical grouping only; this is **not** a final navigation tree, component architecture or implementation plan.

- **Chat / tasks**
  - Sessions, composer, host workspace, attachments, current model/mode/effort.
  - Plan discussion/review, permissions/questions, streaming, sources, tool/worker activity, pending follow-ups, context/recap, validation and change review.
- **Workspace / changes**
  - File tree/read/search, diff/review, guarded commands and validation output, project instructions, dirty-tree/protected state.
- **Library**
  - Sessions · Knowledge · Documents · Research · Media · Archive.
  - Keep artifact import/export/tag/archive separate from learning/indexing. Media includes screenshots/uploads/generated images/analysis/provenance, not a full canvas editor.
- **Model Manager**
  - Downloaded/loaded Ollama models, pull/delete and Hub discovery.
  - Engines/Serve, owned running servers/logs/Stop/adoption.
  - Dependencies/builds/offline vLLM environments/removal.
  - Servers: local/default diagnostics, SSH definitions/keys/inspection/remote CPU/GPU/vLLM/adoption.
- **Integrations**
  - MCP Search/Add/Import/Manage/auth/update; Skills Search/Import/Manage/source/update.
- **Settings**
  - **INTERFACE → Web UI → Enable/Disable (planned hosting control, available from TUI even off).** Browser appearance/accessibility can be separate from terminal Appearance.
  - **Models & AI:** Connections/Added Models, active versus Default Chat, Utility/Research/Vision roles/fallbacks, image-generation service, provider credentials.
  - **Agent:** execution budgets, built-in tool availability, validation, permissions, memory capture.
  - **Search & Knowledge:** Search provider/results/fallbacks/credentials, URL Fetch, Research defaults, ingestion/crawler/embedding and advanced relevance/location policy.
  - **Runtime & privacy:** placement/context/threads/GPU hints, model reasoning/sampling compatibility, runtime context/location, storage/diagnostic metadata.
  - **Advanced / diagnostics:** service health, explicit setup guidance, cache/status metadata and developer integration where useful; expose only real controls, not every internal constant.

## 11. Coverage and Verification Checklist

### 11.1 Audited coverage

| Surface | Evidence / coverage | Limits |
| --- | --- | --- |
| Repository identity/dirty state | Exact revision/branch/version and pre-existing status captured;355 original tracked/dirty files hashed | New documentation only; original work preserved as checked below |
| Production source |145 Python modules parsed for class/function/annotated-field/environment sites; targeted implementation reads across all packages | Static inventory, not all-line manual review or runtime certification |
| CLI |109 runtime Click nodes =97 leaf commands +12 groups;240 declared arguments/options captured in §4.1; executable entrypoints checked in package metadata | No command handlers executed merely to enumerate registry |
| Slash commands |44 live registry records, aliases/hidden exits included; relevant handlers and scoped modes cross-checked | Browser shortcuts not implemented |
| Keyboard |10 registry records plus contextual picker/composer/permission bindings and mouse/paging semantics | Terminal-native default editor bindings are library behavior, not extra product controls |
| Settings |All119 Config dataclass leaves mapped to loader/JSON overlays/internal declarations; provider families, sampling, registries, SSH, appearance, memory, Media and transient controls added | Internal models/cache/job schemas are not all direct user-editable settings; no invented hot-reload guarantee |
| Environment |98 production Python access sites scanned; literal/dynamic keys collapsed and supplemented by examples, child env, scripts and Compose | No actual secret values included; arbitrary user-selected env refs are a field family |
| Menus/hidden capabilities |Settings/Models/AI/Search/Agent/MCP/Skills/Library/Research/Media/Model Manager/Dependencies/SSH reviewed through controllers and action handlers | Navigation inspected from source; no new visual/browser/accessibility certification |
| Intended behavior tests |Read relevant assertions and ran exact focused existing tests below | Focused tests can use fixture HTTP services; not live provider/model evidence |
| Prior implementation evidence |S0–S6 reports and current plan used to resolve partial/planned/live-versus-fixture distinctions | Historical reports not repeated and can drift |
| Planned toggle |Dedicated planned subsection; no existing preference/server default invented | Requires later architecture/security/lifecycle decisions |
| All discovered inventory entries |Each F/S item classified; CLI/slash/key/menu surfaces mapped;16 explicit terminal exclusions | Feature groups/counting rules do not equate to exhaustive count of internal functions |

### 11.2 Validation performed during this audit

Exact command (isolated temporary config/data roots; frozen/offline uv dependencies):

```bash
KLAUDE_HOME=/tmp/klaude-webui-audit/test-home \
KLAUDE_CONFIG_DIR=/tmp/klaude-webui-audit/test-home/config \
KLAUDE_DATA_DIR=/tmp/klaude-webui-audit/test-home/data \
UV_CACHE_DIR=/tmp/klaude-s5-uv-cache \
uv run --frozen --offline pytest -q \
  tests/unit/test_config.py tests/unit/test_session_runtime.py \
  tests/unit/test_session_io.py tests/unit/test_settings_store.py \
  tests/unit/test_search_settings.py tests/unit/test_fetch_settings.py \
  tests/unit/test_tool_interfaces.py tests/unit/test_image_generation.py
```

Initial sandbox run: **158 passed,35 fixture setup errors** because AF_INET socket creation was denied (`PermissionError: [Errno 1] Operation not permitted`). These were not asserted product failures. Rerun with local loopback sockets allowed: **193 passed in 29.92s**. Provider/image responses are fixture-controlled; this does not certify live model inference. Registry extraction and AST/schema/link checks are separate from these tests.

**No full unit suite, `make check`, static production checks, packaging, live cloud/local generation, SSH serving or CSV benchmark was run as part of this documentation-only task.** Existing test/validation reports remain scoped historical evidence. No production code fixes were attempted for unrelated behavior.

Documentation checks: source links resolve to existing files and valid line numbers; CLI counts/parameter counts and slash/key registries cross-check generated manifests; settings keys are checked for duplicate IDs and source mapping; all required sections and Planned WebUI Integration are present; no unresolved placeholder markers remain. Original worktree bytes are compared against the captured baseline at completion; the preservation result is recorded below.

**Worktree preservation:** all 355 originally snapshotted tracked/dirty files remain byte-identical. Only this new documentation deliverable was added by the audit; no commit or push was performed.

### 11.3 Coverage gaps and uncertainties to carry into planning

- Broad source discovery and registry coverage are verified; **full behavior coverage is not certified**. External services, optional SDK installs, account permissions and hardware may differ from historical reports.
- No current-user secrets were opened or printed. Effective values from that user’s private dotenv/config are intentionally not reproduced; documented defaults come from declarations/loaders and safe isolated imports.
- Some legacy config inputs have weak coercion-only validation or narrowly used consumers; tables identify internal/deprecated defaults rather than inventing modern controls. Future API design needs a verified settings contract, not direct JSON editing from the browser.
- Planned/deferred features are not implemented. New WebUI/hosting/security settings have no settled key/default/port/binding/startup policy. Session import and completed-message editing are missing rather than hidden supported workflows.
- Native image generation’s protocol path is implemented; actual model inference/cancellation/resource evidence remains open. Provider Vision exact-ID profiles are bounded checked-in evidence, not support for every model alias. Paid-provider live generation and physical remote-machine coverage remain limited.
- File imports/header checks do not constitute a browser-safe full media decoder or document sanitizer. Browser content handling/security remains unimplemented.
- Multi-client session coordination exists; cross-workspace shared Git, daemon ownership, multi-user authorization and tab reconnect behavior need deliberate integration testing. Do not assume every existing local mutex is a universal distributed lock.
- Small-model complex implementation competence remains unproven by this audit. See [docs/power-user-evaluation.md](../docs/power-user-evaluation.md#L1); [docs/small-model-evaluation.md](../docs/small-model-evaluation.md#L1); [docs/agent-source-context-evaluation.md](../docs/agent-source-context-evaluation.md#L1); [docs/agent-task-state-evaluation.md](../docs/agent-task-state-evaluation.md#L1) for the historical benchmark; UI planning must show honest partial/validation/blocked states.

### 11.4 Source/evidence index

Primary implementation verification links are attached to each feature/setting/command. Useful historical validation reports (scope-specific, not a blanket green certificate):

- [docs/s0-reliability-validation.md](../docs/s0-reliability-validation.md#L1)
- [docs/s1-model-connections-validation.md](../docs/s1-model-connections-validation.md#L1)
- [docs/s2-model-settings-validation.md](../docs/s2-model-settings-validation.md#L1)
- [docs/s2b-ai-defaults-validation.md](../docs/s2b-ai-defaults-validation.md#L1)
- [docs/s2c-anthropic-validation.md](../docs/s2c-anthropic-validation.md#L1)
- [docs/s2c-deepseek-validation.md](../docs/s2c-deepseek-validation.md#L1)
- [docs/s3a-url-fetch-validation.md](../docs/s3a-url-fetch-validation.md#L1)
- [docs/s3a-web-search-validation.md](../docs/s3a-web-search-validation.md#L1)
- [docs/s3b-agent-execution-validation.md](../docs/s3b-agent-execution-validation.md#L1)
- [docs/s3b-agent-tools-validation.md](../docs/s3b-agent-tools-validation.md#L1)
- [docs/s4a-artifacts-validation.md](../docs/s4a-artifacts-validation.md#L1)
- [docs/s4a-knowledge-validation.md](../docs/s4a-knowledge-validation.md#L1)
- [docs/s4a-library-validation.md](../docs/s4a-library-validation.md#L1)
- [docs/s4b-deep-research-validation.md](../docs/s4b-deep-research-validation.md#L1)
- [docs/s5a-model-manager-validation.md](../docs/s5a-model-manager-validation.md#L1)
- [docs/s5b-managed-serving-validation.md](../docs/s5b-managed-serving-validation.md#L1)
- [docs/s5c-dependencies-validation.md](../docs/s5c-dependencies-validation.md#L1)
- [docs/s5c-engine-recipes-validation.md](../docs/s5c-engine-recipes-validation.md#L1)
- [docs/s5c-remote-adoption-validation.md](../docs/s5c-remote-adoption-validation.md#L1)
- [docs/s5c-remote-gpu-validation.md](../docs/s5c-remote-gpu-validation.md#L1)
- [docs/s5c-remote-serving-validation.md](../docs/s5c-remote-serving-validation.md#L1)
- [docs/s5c-remote-vllm-validation.md](../docs/s5c-remote-vllm-validation.md#L1)
- [docs/s5c-setup-removal-validation.md](../docs/s5c-setup-removal-validation.md#L1)
- [docs/s5c-ssh-key-setup-validation.md](../docs/s5c-ssh-key-setup-validation.md#L1)
- [docs/s5c-ssh-validation.md](../docs/s5c-ssh-validation.md#L1)
- [docs/s6a-gemma-local-validation.md](../docs/s6a-gemma-local-validation.md#L1)
- [docs/s6a-local-vision-validation.md](../docs/s6a-local-vision-validation.md#L1)
- [docs/s6a2-chat-images-validation.md](../docs/s6a2-chat-images-validation.md#L1)
- [docs/s6a3-http-chat-images-validation.md](../docs/s6a3-http-chat-images-validation.md#L1)
- [docs/s6a3b-http-media-validation.md](../docs/s6a3b-http-media-validation.md#L1)
- [docs/s6a3c-openrouter-vision-validation.md](../docs/s6a3c-openrouter-vision-validation.md#L1)
- [docs/s6a3d-openai-vision-validation.md](../docs/s6a3d-openai-vision-validation.md#L1)
- [docs/s6a3e-gemini-vision-validation.md](../docs/s6a3e-gemini-vision-validation.md#L1)
- [docs/s6a3f-current-gemini-validation.md](../docs/s6a3f-current-gemini-validation.md#L1)
- [docs/s6b-local-generation-validation.md](../docs/s6b-local-generation-validation.md#L1)

Production modules discovered in the audit, grouped by package, are listed below as a coverage index. A link means discovery/parsing plus targeted group inspection, not an assertion that every branch is live-tested.

**apps/cli**

[apps/cli/src/klaude_cli/__init__.py](../apps/cli/src/klaude_cli/__init__.py), [apps/cli/src/klaude_cli/agent_settings.py](../apps/cli/src/klaude_cli/agent_settings.py#L1), [apps/cli/src/klaude_cli/ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py#L1), [apps/cli/src/klaude_cli/background_jobs.py](../apps/cli/src/klaude_cli/background_jobs.py#L1), [apps/cli/src/klaude_cli/background_worker.py](../apps/cli/src/klaude_cli/background_worker.py#L1), [apps/cli/src/klaude_cli/dependency_panel.py](../apps/cli/src/klaude_cli/dependency_panel.py#L1), [apps/cli/src/klaude_cli/dividers.py](../apps/cli/src/klaude_cli/dividers.py#L1), [apps/cli/src/klaude_cli/fetch_settings.py](../apps/cli/src/klaude_cli/fetch_settings.py#L1), [apps/cli/src/klaude_cli/generation_commands.py](../apps/cli/src/klaude_cli/generation_commands.py#L1), [apps/cli/src/klaude_cli/generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py#L1), [apps/cli/src/klaude_cli/installed_settings.py](../apps/cli/src/klaude_cli/installed_settings.py#L1), [apps/cli/src/klaude_cli/library_artifact_panel.py](../apps/cli/src/klaude_cli/library_artifact_panel.py#L1), [apps/cli/src/klaude_cli/library_commands.py](../apps/cli/src/klaude_cli/library_commands.py#L1), [apps/cli/src/klaude_cli/library_inventory.py](../apps/cli/src/klaude_cli/library_inventory.py#L1), [apps/cli/src/klaude_cli/library_knowledge.py](../apps/cli/src/klaude_cli/library_knowledge.py#L1), [apps/cli/src/klaude_cli/library_knowledge_panel.py](../apps/cli/src/klaude_cli/library_knowledge_panel.py#L1), [apps/cli/src/klaude_cli/library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py#L1), [apps/cli/src/klaude_cli/main.py](../apps/cli/src/klaude_cli/main.py#L1), [apps/cli/src/klaude_cli/mcp_inventory.py](../apps/cli/src/klaude_cli/mcp_inventory.py#L1), [apps/cli/src/klaude_cli/mcp_management.py](../apps/cli/src/klaude_cli/mcp_management.py#L1), [apps/cli/src/klaude_cli/mcp_mutations.py](../apps/cli/src/klaude_cli/mcp_mutations.py#L1), [apps/cli/src/klaude_cli/mcp_search_panel.py](../apps/cli/src/klaude_cli/mcp_search_panel.py#L1), [apps/cli/src/klaude_cli/mcp_suggestions.py](../apps/cli/src/klaude_cli/mcp_suggestions.py#L1), [apps/cli/src/klaude_cli/mcp_updates.py](../apps/cli/src/klaude_cli/mcp_updates.py#L1), [apps/cli/src/klaude_cli/memory_inventory.py](../apps/cli/src/klaude_cli/memory_inventory.py#L1), [apps/cli/src/klaude_cli/memory_panel.py](../apps/cli/src/klaude_cli/memory_panel.py#L1), [apps/cli/src/klaude_cli/model_connections.py](../apps/cli/src/klaude_cli/model_connections.py#L1), [apps/cli/src/klaude_cli/model_manager.py](../apps/cli/src/klaude_cli/model_manager.py#L1), [apps/cli/src/klaude_cli/model_manager_commands.py](../apps/cli/src/klaude_cli/model_manager_commands.py#L1), [apps/cli/src/klaude_cli/model_settings.py](../apps/cli/src/klaude_cli/model_settings.py#L1), [apps/cli/src/klaude_cli/pickers.py](../apps/cli/src/klaude_cli/pickers.py#L1), [apps/cli/src/klaude_cli/research_commands.py](../apps/cli/src/klaude_cli/research_commands.py#L1), [apps/cli/src/klaude_cli/research_panel.py](../apps/cli/src/klaude_cli/research_panel.py#L1), [apps/cli/src/klaude_cli/search_settings.py](../apps/cli/src/klaude_cli/search_settings.py#L1), [apps/cli/src/klaude_cli/serving_jobs.py](../apps/cli/src/klaude_cli/serving_jobs.py#L1), [apps/cli/src/klaude_cli/serving_panel.py](../apps/cli/src/klaude_cli/serving_panel.py#L1), [apps/cli/src/klaude_cli/session_actions.py](../apps/cli/src/klaude_cli/session_actions.py#L1), [apps/cli/src/klaude_cli/session_io.py](../apps/cli/src/klaude_cli/session_io.py#L1), [apps/cli/src/klaude_cli/settings_overview.py](../apps/cli/src/klaude_cli/settings_overview.py#L1), [apps/cli/src/klaude_cli/settings_panel.py](../apps/cli/src/klaude_cli/settings_panel.py#L1), [apps/cli/src/klaude_cli/settings_writer.py](../apps/cli/src/klaude_cli/settings_writer.py#L1), [apps/cli/src/klaude_cli/setup_jobs.py](../apps/cli/src/klaude_cli/setup_jobs.py#L1), [apps/cli/src/klaude_cli/skill_actions.py](../apps/cli/src/klaude_cli/skill_actions.py#L1), [apps/cli/src/klaude_cli/skill_discovery.py](../apps/cli/src/klaude_cli/skill_discovery.py#L1), [apps/cli/src/klaude_cli/skill_runtime.py](../apps/cli/src/klaude_cli/skill_runtime.py#L1), [apps/cli/src/klaude_cli/skills_panel.py](../apps/cli/src/klaude_cli/skills_panel.py#L1), [apps/cli/src/klaude_cli/spinners.py](../apps/cli/src/klaude_cli/spinners.py#L1), [apps/cli/src/klaude_cli/ssh_commands.py](../apps/cli/src/klaude_cli/ssh_commands.py#L1), [apps/cli/src/klaude_cli/ssh_panel.py](../apps/cli/src/klaude_cli/ssh_panel.py#L1), [apps/cli/src/klaude_cli/ssh_setup_panel.py](../apps/cli/src/klaude_cli/ssh_setup_panel.py#L1), [apps/cli/src/klaude_cli/terminal_surface.py](../apps/cli/src/klaude_cli/terminal_surface.py#L1), [apps/cli/src/klaude_cli/vision_panel.py](../apps/cli/src/klaude_cli/vision_panel.py#L1)

**packages/core**

[packages/core/src/klaude_core/__init__.py](../packages/core/src/klaude_core/__init__.py#L1), [packages/core/src/klaude_core/agent.py](../packages/core/src/klaude_core/agent.py#L1), [packages/core/src/klaude_core/agent_settings.py](../packages/core/src/klaude_core/agent_settings.py#L1), [packages/core/src/klaude_core/ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py#L1), [packages/core/src/klaude_core/anthropic_runtime.py](../packages/core/src/klaude_core/anthropic_runtime.py#L1), [packages/core/src/klaude_core/capabilities.py](../packages/core/src/klaude_core/capabilities.py#L1), [packages/core/src/klaude_core/chat_image_support.py](../packages/core/src/klaude_core/chat_image_support.py#L1), [packages/core/src/klaude_core/chat_images.py](../packages/core/src/klaude_core/chat_images.py#L1), [packages/core/src/klaude_core/codex_auth.py](../packages/core/src/klaude_core/codex_auth.py#L1), [packages/core/src/klaude_core/compatible_runtime.py](../packages/core/src/klaude_core/compatible_runtime.py#L1), [packages/core/src/klaude_core/config.py](../packages/core/src/klaude_core/config.py#L1), [packages/core/src/klaude_core/context_compaction.py](../packages/core/src/klaude_core/context_compaction.py#L1), [packages/core/src/klaude_core/dates.py](../packages/core/src/klaude_core/dates.py#L1), [packages/core/src/klaude_core/deepseek_runtime.py](../packages/core/src/klaude_core/deepseek_runtime.py#L1), [packages/core/src/klaude_core/entities.py](../packages/core/src/klaude_core/entities.py#L1), [packages/core/src/klaude_core/evaluation.py](../packages/core/src/klaude_core/evaluation.py#L1), [packages/core/src/klaude_core/evaluation_interfaces.py](../packages/core/src/klaude_core/evaluation_interfaces.py#L1), [packages/core/src/klaude_core/execution.py](../packages/core/src/klaude_core/execution.py#L1), [packages/core/src/klaude_core/fetch_settings.py](../packages/core/src/klaude_core/fetch_settings.py#L1), [packages/core/src/klaude_core/gemini_images.py](../packages/core/src/klaude_core/gemini_images.py#L1), [packages/core/src/klaude_core/http_model_transport.py](../packages/core/src/klaude_core/http_model_transport.py#L1), [packages/core/src/klaude_core/image_content.py](../packages/core/src/klaude_core/image_content.py#L1), [packages/core/src/klaude_core/image_generation.py](../packages/core/src/klaude_core/image_generation.py#L1), [packages/core/src/klaude_core/image_profiles.py](../packages/core/src/klaude_core/image_profiles.py#L1), [packages/core/src/klaude_core/intent.py](../packages/core/src/klaude_core/intent.py#L1), [packages/core/src/klaude_core/knowledge_tool_contract.py](../packages/core/src/klaude_core/knowledge_tool_contract.py#L1), [packages/core/src/klaude_core/library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py#L1), [packages/core/src/klaude_core/managed_serving.py](../packages/core/src/klaude_core/managed_serving.py#L1), [packages/core/src/klaude_core/mcp_catalog.py](../packages/core/src/klaude_core/mcp_catalog.py#L1), [packages/core/src/klaude_core/mcp_client.py](../packages/core/src/klaude_core/mcp_client.py#L1), [packages/core/src/klaude_core/memory.py](../packages/core/src/klaude_core/memory.py#L1), [packages/core/src/klaude_core/model_connections.py](../packages/core/src/klaude_core/model_connections.py#L1), [packages/core/src/klaude_core/model_dependencies.py](../packages/core/src/klaude_core/model_dependencies.py#L1), [packages/core/src/klaude_core/model_discovery.py](../packages/core/src/klaude_core/model_discovery.py#L1), [packages/core/src/klaude_core/model_management.py](../packages/core/src/klaude_core/model_management.py#L1), [packages/core/src/klaude_core/model_recipes.py](../packages/core/src/klaude_core/model_recipes.py#L1), [packages/core/src/klaude_core/model_runtime.py](../packages/core/src/klaude_core/model_runtime.py#L1), [packages/core/src/klaude_core/model_setup_removal.py](../packages/core/src/klaude_core/model_setup_removal.py#L1), [packages/core/src/klaude_core/ollama.py](../packages/core/src/klaude_core/ollama.py#L1), [packages/core/src/klaude_core/ollama_manager.py](../packages/core/src/klaude_core/ollama_manager.py#L1), [packages/core/src/klaude_core/openai_images.py](../packages/core/src/klaude_core/openai_images.py#L1), [packages/core/src/klaude_core/openrouter_images.py](../packages/core/src/klaude_core/openrouter_images.py#L1), [packages/core/src/klaude_core/permissions.py](../packages/core/src/klaude_core/permissions.py#L1), [packages/core/src/klaude_core/request_context.py](../packages/core/src/klaude_core/request_context.py#L1), [packages/core/src/klaude_core/research.py](../packages/core/src/klaude_core/research.py#L1), [packages/core/src/klaude_core/research_receipts.py](../packages/core/src/klaude_core/research_receipts.py#L1), [packages/core/src/klaude_core/response_constraints.py](../packages/core/src/klaude_core/response_constraints.py#L1), [packages/core/src/klaude_core/runtime_calibration.py](../packages/core/src/klaude_core/runtime_calibration.py#L1), [packages/core/src/klaude_core/runtime_context.py](../packages/core/src/klaude_core/runtime_context.py#L1), [packages/core/src/klaude_core/search_settings.py](../packages/core/src/klaude_core/search_settings.py#L1), [packages/core/src/klaude_core/session_runtime.py](../packages/core/src/klaude_core/session_runtime.py#L1), [packages/core/src/klaude_core/settings_store.py](../packages/core/src/klaude_core/settings_store.py#L1), [packages/core/src/klaude_core/skill_catalog.py](../packages/core/src/klaude_core/skill_catalog.py#L1), [packages/core/src/klaude_core/skill_drop.py](../packages/core/src/klaude_core/skill_drop.py#L1), [packages/core/src/klaude_core/source_use.py](../packages/core/src/klaude_core/source_use.py#L1), [packages/core/src/klaude_core/ssh_diagnostics.py](../packages/core/src/klaude_core/ssh_diagnostics.py#L1), [packages/core/src/klaude_core/ssh_enrollment_program.py](../packages/core/src/klaude_core/ssh_enrollment_program.py#L1), [packages/core/src/klaude_core/ssh_servers.py](../packages/core/src/klaude_core/ssh_servers.py#L1), [packages/core/src/klaude_core/ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py#L1), [packages/core/src/klaude_core/ssh_serving_program.py](../packages/core/src/klaude_core/ssh_serving_program.py#L1), [packages/core/src/klaude_core/ssh_setup.py](../packages/core/src/klaude_core/ssh_setup.py#L1), [packages/core/src/klaude_core/subagents.py](../packages/core/src/klaude_core/subagents.py#L1), [packages/core/src/klaude_core/tool_settings.py](../packages/core/src/klaude_core/tool_settings.py#L1), [packages/core/src/klaude_core/utility.py](../packages/core/src/klaude_core/utility.py#L1), [packages/core/src/klaude_core/vision.py](../packages/core/src/klaude_core/vision.py#L1), [packages/core/src/klaude_core/working_sources.py](../packages/core/src/klaude_core/working_sources.py#L1), [packages/core/src/klaude_core/workspace_execution.py](../packages/core/src/klaude_core/workspace_execution.py#L1)

**packages/knowledge**

[packages/knowledge/src/klaude_knowledge/__init__.py](../packages/knowledge/src/klaude_knowledge/__init__.py#L1), [packages/knowledge/src/klaude_knowledge/chunker.py](../packages/knowledge/src/klaude_knowledge/chunker.py#L1), [packages/knowledge/src/klaude_knowledge/docs.py](../packages/knowledge/src/klaude_knowledge/docs.py#L1), [packages/knowledge/src/klaude_knowledge/hybrid.py](../packages/knowledge/src/klaude_knowledge/hybrid.py#L1), [packages/knowledge/src/klaude_knowledge/indexing.py](../packages/knowledge/src/klaude_knowledge/indexing.py#L1), [packages/knowledge/src/klaude_knowledge/mcp_server.py](../packages/knowledge/src/klaude_knowledge/mcp_server.py#L1), [packages/knowledge/src/klaude_knowledge/skill_management.py](../packages/knowledge/src/klaude_knowledge/skill_management.py#L1), [packages/knowledge/src/klaude_knowledge/skills.py](../packages/knowledge/src/klaude_knowledge/skills.py#L1), [packages/knowledge/src/klaude_knowledge/snapshots.py](../packages/knowledge/src/klaude_knowledge/snapshots.py#L1), [packages/knowledge/src/klaude_knowledge/store.py](../packages/knowledge/src/klaude_knowledge/store.py#L1)

**packages/tools_local**

[packages/tools_local/src/klaude_tools/__init__.py](../packages/tools_local/src/klaude_tools/__init__.py#L1), [packages/tools_local/src/klaude_tools/diagnostics.py](../packages/tools_local/src/klaude_tools/diagnostics.py#L1), [packages/tools_local/src/klaude_tools/sandbox.py](../packages/tools_local/src/klaude_tools/sandbox.py#L1), [packages/tools_local/src/klaude_tools/toolkit.py](../packages/tools_local/src/klaude_tools/toolkit.py#L1)

**packages/web**

[packages/web/src/klaude_web/__init__.py](../packages/web/src/klaude_web/__init__.py#L1), [packages/web/src/klaude_web/cache.py](../packages/web/src/klaude_web/cache.py#L1), [packages/web/src/klaude_web/crawler.py](../packages/web/src/klaude_web/crawler.py#L1), [packages/web/src/klaude_web/exa.py](../packages/web/src/klaude_web/exa.py#L1), [packages/web/src/klaude_web/facade.py](../packages/web/src/klaude_web/facade.py#L1), [packages/web/src/klaude_web/fetch.py](../packages/web/src/klaude_web/fetch.py#L1), [packages/web/src/klaude_web/huggingface.py](../packages/web/src/klaude_web/huggingface.py#L1), [packages/web/src/klaude_web/mcp_server.py](../packages/web/src/klaude_web/mcp_server.py#L1), [packages/web/src/klaude_web/provider_http.py](../packages/web/src/klaude_web/provider_http.py#L1), [packages/web/src/klaude_web/providers.py](../packages/web/src/klaude_web/providers.py#L1), [packages/web/src/klaude_web/search.py](../packages/web/src/klaude_web/search.py#L1), [packages/web/src/klaude_web/sources.py](../packages/web/src/klaude_web/sources.py#L1)

**Handoff boundary:** use this inventory to plan UX/navigation and backend adapters. Preserve all existing local changes. Do not introduce a second agent, silently widen permissions/capabilities or treat planned entries as delivered features.
