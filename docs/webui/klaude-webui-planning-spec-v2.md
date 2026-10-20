# Klaude WebUI — Architecture and UX Planning Specification

**Status:** Proposed planning baseline, revised for WebUI themes and bridge-first delivery; **not an implementation instruction**  
**Date:** 2026-10-15  
**Inventory source:** `webui-feature-inventory.md` (Klaude 0.2.0a4, worktree audit; base revision `0234b116f4380cb87c1b1cf39959725493e227ee`)  
**Primary design:** Google Material Design 3 Expressive / Material You, with LineageOS and end-4/dots-hyprland as user-requested visual references  
**Design direction confirmed:** 2026-10-20; Expressive shapes, color, controls and fluid motion are requirements for the forthcoming product UI, beyond the existing functional browser client.  
**Fonts:** Roboto for UI; JetBrains Mono for code, diffs, commands and logs  
**Scope:** All implemented user-facing Klaude capabilities and effective settings except strictly TUI-specific presentation; partial capabilities must be honestly labeled. No unimplemented features are presumed to exist.

## 1. Outcome and principles

Build a **local-first browser client for the existing Klaude agent**, not a separate chat service or a webpage that imitates the TUI. Preserve the same local model/cloud provider selection, tools, permissions, session continuity, state and resource limits that exist in the audited backend. Use browser-native interfaces for text, approvals, files, images, research, settings, long-running operations and model setup.

Principles:

1. **One Klaude brain, multiple clients:** TUI and WebUI call the same application-layer services/policies; avoid duplicating the agent loop or using CLI screens as APIs.
2. **Complete functional coverage:** Do not discard a working setting because the inventory marks its visibility `OPTIONAL`. Expose normal controls in context and advanced controls through progressive disclosure. A truly internal constant, transient form state, deprecated alias or unverified/no-op field is not an independent settings toggle.
3. **Safety is enforced on the server:** Workspace jail, Git dirty-tree guard, read-only plan/review scope, permission decisions, tool availability, safe URL rules, credentials and explicit model/SSH identity validation all apply regardless of UI affordance.
4. **Keep model intent explicit:** Current chat model, Default Chat, Utility, Research, Vision and image-generation service are distinct; do not silently switch/fallback across roles.
5. **Honest outcomes:** Saved vs pending vs unconfirmed; completed vs partial vs cancelled vs unknown external side effects; loaded vs available vs reachable; no invented progress or success.
6. **Fast by default:** Chat remains visible while a long-running operation is tracked; powerful tools are accessible but do not crowd the composer.
7. **Accessible and responsive:** Design desktop first for coding productivity, then adapt fully for tablets/mobile; maintain keyboard navigation and reduced-motion support.

### Known non-goals / not currently implemented

No promise of an interactive PTY, browser desktop/file explorer with unconstrained host access, PR/issue client, session import, editing/regenerating arbitrary completed messages, canvas/layer editing, speech, AI auto-tags, unrestricted web automation or generalized multi-user remote cloud sync. Do not infer these from Open WebUI or Odysseus references. The existing local image-generation path is **partial** until real inference is validated. These can be separate future product proposals.

## 2. Reference interpretation

- **Google Material Design 3 Expressive:** The primary design system, including semantic color roles, tonal surfaces, adaptive navigation, state layers, expressive shapes, grouped controls, typography, emphasis and fluid motion. Expressive treatment must be visible in the application shell and everyday interactions. The design system is not the same thing as the **MUI React component library**; selecting a library alone does not satisfy this requirement.
- **LineageOS:** User-requested reference for an Android-like Material feel, cohesive settings, clear hierarchy and rounded control groups. This defines the desired direction; it is not a claim that every LineageOS release implements Material 3 Expressive or a requirement to copy a particular screen.
- **end-4/dots-hyprland:** Inspiration for expressive clocks, cookie/organic shapes, rounded control groups, tonal contrast, smooth transitions, and character. Its Hyprland/Quickshell widgets are not browser components to copy directly. Focus on principles and verify source license before adapting source assets or code.
- **Odysseus:** Requested reference for navigation placement, dialogs, tab structure and settings ergonomics. **Design details are provisional until the exact repo/build/screenshots are supplied and reviewed**; no unverifiable specific Odysseus UI claims are made in this spec.
- **Open WebUI:** Conversational navigation, searchable model selection, workspace panels, progressively disclosed advanced controls and approachable Library-like management. Its features are references, not automatic Klaude feature requests.
- **Impeccable:** Use as a design quality/audit lens for interaction clarity, responsive details, typography, color, empty states, focus, and disciplined restraint. Respect user's explicit Roboto choice despite generic font opinions in design guides.

### Visual character

Call the design direction **"Expressive Precision"**: friendly Material geometry around a serious coding workspace. Prefer asymmetric rounded surfaces, carefully grouped controls, legible hierarchy, fluid responsive motion and colorful but accessible states. The requested end-4-inspired character should carry through the shell, theme palettes and grouped controls. Give distinctive treatment to a few landmarks (home/overview, model service state, task progress). Avoid ornamental widgets, giant empty hero cards, uniform card grids, busy gradients or shape-morph animation distracting from code reading.

**Suggested tokens for exploration, not locked values:** shape classes small 8, medium 12, large 20, extra-large 28 CSS px and full/organic shapes for highlighted controls; 4px spacing increments; semantic status + surface color roles; light/dark/system themes; tonal elevation with minimal shadows; typography as Material-like type roles in Roboto. Code/diff/log text JetBrains Mono and never auto-ligature path/code tokens if that harms readability. Respect minimum 44x44 CSS px touch targets when feasible; keyboard focus visible; `prefers-reduced-motion` respected; WCAG 2.2 AA contrast/interaction audit.

**Expressive clock suggestion:** Put an optional organic/cookie clock with live local time and service uptime on an *Overview/Status* surface or new-session welcome state—not permanently competing with an active editor/chat. The clock is a visual direction; it is not an existing Klaude clock widget requirement. Code, logs and settings remain rectangular/scan-friendly.

### Motion requirements

Modern, fluid animation is part of the product requirement. Use shared duration, easing and spring tokens so navigation, drawers, inspector panels, dialogs, grouped controls and task-state changes feel coherent. These are Klaude interaction requirements; exact values must be tuned in the browser rather than presented as official Material constants.

- Use responsive spring-like settling for expanding panels and selected expressive controls, with clear enter/exit transitions and immediate pressed/focus feedback. Keep overshoot subtle and away from text/code reading surfaces.
- Transitions must be interruptible and reverse smoothly when users change direction. Rapid navigation must settle on the latest requested state without queued animation or delayed input.
- Prefer transform and opacity for movement; bound any layout/shape animation to small surfaces. Avoid blanket `transition: all`, animating large blurred surfaces or per-token chat animations.
- Preserve transcript scroll position, selection, keyboard focus and readable diffs during streaming and panel changes. Approvals, cancellation and server acknowledgements must remain immediately actionable; animation must never delay or imply an operation succeeded.
- Respect `prefers-reduced-motion` and an explicit reduced-motion preference: remove spring overshoot, morphing and nonessential travel while retaining immediate state changes and essential progress feedback.
- Validate the shell on desktop and narrow touch layouts, including interrupted transitions, rapid repeated input and reduced motion. Record actual browser observations before claiming smoothness or visual acceptance.

## 3. Proposed navigation and page map

### Primary application frame

Desktop: a collapsible Material navigation **rail/drawer** on the left; central content pane; conditional inspector on the right; slim contextual top bar. Main rail contains **Chat, Workspaces, Library, Models, Integrations, Activity, Settings**. Avoid nesting a separate permanent sidebar inside every screen; use one local subnavigation panel for the selected primary area. Mobile: drawer plus route-level bottom sheets and expandable inspect panes, without hiding approvals or cancelling tasks.

Persistent top/context controls: current workspace, current active chat model, mode/effort where supported, active task/connection status, contextual search/command palette and settings access. Show when current chat's model differs from Default Chat. Global task state must remain visible on route changes.

| Primary area | Pages / subnavigation | Critical user workflows |
| --- | --- | --- |
| **Chat** | New Chat; session list/search; active conversation; archived sessions link; session details; contextual inspector tabs **Activity / Changes / Sources / Context** | Stream replies, attachments, user questions, plan mode, model selection, permissions, queue/steer/cancel, resume/fork/rename/export, recap/context, tool traces, subagents |
| **Workspaces** | Workspace selector; Files; Search; Changes & Review; Project Instructions; validation/command receipts | Choose host root, read/search, inspect changes, approve file/shell tools through same gate, review diff, init AGENTS.md, respect dirty-tree lockout |
| **Library** | **Knowledge / Documents / Research / Media / Archive**; Sessions management can appear via Chat and cross-link to Library Sessions | Libraries/sources/indexing/crawl/docs updates, import/preview/export/tags/archive, bounded research and reports, analyze/generate images, receipts/provenance; distinguish imported from learned |
| **Models** | **Use a Model / Connections / Downloaded Models / Model Manager / Running Servers / Dependencies & Builds / SSH Servers / Hardware** | Select qualified chat model, configure/test endpoints, role defaults cross-link, Ollama pulls/deletes, trusted engine builds, local/SSH serving/adoption, logs/stop, key trust |
| **Integrations** | **Skills / MCP Servers**, each with **Installed / Discover / Add or Import / Updates**; MCP auth detail | Search, review source, install, enable/disable, update/remove, secrets/OAuth; distinguish installed from enabled and callable |
| **Activity** | In-progress/finished owned operations; filter by type, status and resource; detail/logs | Inspect research, generation, model pull, dependency build, serving, tool/subagent and cancellation receipts. Not a claim of a durable general job scheduler |
| **Settings** | Grouped categories in §4, setting search and effective-value provenance | Configure every effective non-TUI setting, see saved/overridden/unsupported states, manage sensitive inputs safely |

### Reuse routes rather than duplicate records

A research report opens from Library > Research even when its operation appears in Activity. Model selection is available in Chat, while endpoint/engine lifecycle lives under Models. Settings > Models & AI links to Models; it does not create a second independent connection registry. Sessions are first-class in Chat, with archive/export lifecycle in session actions/Library. Changes inspected during a tool run are the *same* Git diffs as Workspaces > Changes. Research-source receipts appear in the Sources inspector and Library report detail.

### Chat view layout

- **Left contextual nav:** searchable conversations, New Chat, active/archived filters, session overflow menu, session/watch ownership indicators and workspace context.
- **Center:** public conversation only; streamed text/code/math as supported; citations/sources; explicit tool calls with sanitized summary, expand-for-output, duration/exit code and errors; request-user-input questions inline or in a focused dialog; clear cancellation/partial states.
- **Composer:** upload/attach, workspace path reference, current model, Standard/Thinking and effort, Plan mode, Send/Queue/Steer state, multiline entry and accessible keyboard help. No raw terminal escape/key hacks.
- **Right inspector (collapsible):** Activity tree (including read-only subagents); Changes (diff/review); Sources; Context (token estimates, recap, model/runtime). On narrow layouts use tabs/bottom sheet.
- **Task safety:** closing a tab or navigating away must not resend a request, implicitly approve a tool or blindly kill an accepted long-running operation. Reconnect by server operation ID and cursor.

## 4. Settings information architecture

A settings **category is a navigational concept**, not necessarily a TOML section. Preserve underlying keys/scopes rather than inventing a new monolithic config store. Search should find exact keys and readable labels; detail rows show **effective value, inherited default, persistence scope, validation, availability, and whether a restart/new turn is required**. Keep basic controls short and reveal advanced fields explicitly.

| Settings category | Subpages and content | Inventory ownership |
| --- | --- | --- |
| **INTERFACE** | **Web UI → Enable/Disable** (hosting control; see §5); **Themes & Colors** (light/dark/system, Material tonal palettes, presets, custom seed color, optional locally derived image palette); browser Appearance (density, shape, motion, code font size); Accessibility; client shortcuts | F096–097 planned; existing TUI Appearance is **not** reused |
| **MODELS & AI** | Active chat controls cross-link; Default Chat / Utility / Research / Vision and eligible fallbacks; Model connections/credentials cross-link; Ollama sampling + reasoning; Image generation service | F025–034, F083–087, S001–005,S008–010,S020–022,S125–148,S162–174,S184–193,S232–235 |
| **AGENT** | Execution budgets, plan state explanation, tools availability, read-only delegation limits, tool result validation, usage/context options | F002–013, F022, S024–031,S149–157,S267–270 |
| **TOOLS & PERMISSIONS** | Presets + per-tool Ask/Allow/Deny; effective capability matrix, MCP tools linked to owning servers, workspace jail information; browser approval behavior | F016–022, F070–078, S023,S159, dynamic tool configs |
| **SEARCH & KNOWLEDGE** | Search provider selection and fallback, per-provider control and credentials, fetching, polite crawl, ingestion/knowledge retention, Research defaults; advanced relevance, billing and location policies | F058–069, F102–103, S003–004,S006–007,S011–019,S030,S032–037,S053–124,S164–166,S175–183 |
| **MEMORY & PRIVACY** | Automatic memory capture; manage existing facts (cross-link); runtime host/context and location data sharing; private/public data boundaries; exporting records | F049–057, S038–052,S231 |
| **RUNTIME & RESOURCES** | Local placement CPU/GPU, context/threads, model manager hardware, native Ollama service operations, engine/server status and limits | F023–048, S149–156,S194–203,S236–258 (request forms rather than global settings) |
| **INTEGRATIONS** | Skills/MCP management and authorized credentials (cross-link), installed/enabled state, transport/OAuth controls | F070–078, S204–218 |
| **ADVANCED & DIAGNOSTICS** | Service health, actual status, process-scoped and config-file-only controls, legacy key explanation, developer support/export logs, version/build info; *verified* advanced behavior only | F089–095,F101,F103; status surfaces and internal operational metadata |

**Important rule:** All supported non-TUI controls remain discoverable somewhere, but do **not** add an editable global toggle for fields that are request inputs (`S236–270`), temporary list filters (`S271–279`), process-external environment settings, or internal invariant bounds. Render these inside their relevant action forms or as diagnostics. Dynamic secret references are edited via authorized host-side secret operations; do not display saved values. Expose documented no-op/Partial fields as disabled/unavailable with explanation until the backend consumer is verified, or show them under an expert read-only status section—never present a pretend working switch.

### WebUI Themes & Colors — explicit product requirement (planned)

Expose a **separate WebUI theme system** under `Settings → INTERFACE → Themes & Colors` alongside `Settings → INTERFACE → Web UI`. Do not reuse or overwrite TUI appearance keys in `data/appearance.json`; terminal themes, ANSI spinner frames and dividers remain TUI-only. The browser settings should be adjustable from the WebUI independently of the hosting toggle.

- **Appearance mode:** System / Light / Dark, with system color-mode tracking and an explicit manual override.
- **Color source:** Curated Material color presets, an arbitrary user-selected seed color, and optionally a local image/wallpaper-derived seed or palette. End-4 generates Material colors from wallpaper; this is inspiration for behavior, not a requirement to import its scripts.
- **Full semantic palettes:** Generate synchronized Material tonal roles for primary, on-primary, secondary, tertiary, surfaces, outlines, inverse and error states. Do not merely substitute a single accent CSS variable or hardcode foreground contrast.
- **Live preview:** Show palette swatches and a small representative Chat/Settings preview with Apply, Reset, and safe failure handling; don't let a preview change the running agent or TUI.
- **Theme persistence:** Persist browser UI preferences per local profile/client using a separate, versioned preference namespace; define how another tab receives updates and how device-local overrides work. The exact store is a future architecture decision.
- **Optional refinements:** UI density, expressive vs restrained shape treatment, motion level/reduced motion, and code/log font scale. Keep Roboto and JetBrains Mono defaults. Import/export and named user-created presets can be later enhancements.
- **Accessibility:** Validate contrast and focus states for every palette, support reduced motion and forced-colors/high-contrast environments, and preserve readable code/diff syntax independently of decorative accents.

These are **new planned WebUI settings**, not existing inventory settings S001–S279. Do not inflate audited implementation counts or label them implemented. For an initial build, System/Light/Dark + preset/seed palettes + semantic tokens + persistence are enough; image-derived colors and import/export can follow.

### Source of truth and validation

Klaude currently spans `config.toml`, private dotenv/revision stores, JSON registries, `chat-preferences.json`, `appearance.json` (TUI only), and SQLite. The WebUI must use validated service operations that retain revision/lock semantics. Display **Inherited / Custom / Unsaved / Saving / Saved / Failed / Unconfirmed / Requires new request or restart** when applicable. No optimistic *success* label until the server acknowledges persistence. Unknown model capability ≠ supported. An accepted job keeps its original captured model/credential/endpoint version until finished or interrupted.

## 5. INTERFACE → Web UI (hosting)

**Later user decision (2026-10-20):** Use local username/password sign-in at the
plain local/LAN address. The default `admin` account receives a random initial
password, revealed locally through TUI Web UI settings. Password changes live
under browser Settings → Account and revoke browser sessions; local recovery uses
`klaude-webui --reset-admin-password`. This supersedes one-use-link sign-in in the
earlier bridge baseline. Account credentials stay outside chat/model data. The
first account is the existing single local owner; registration, multi-user
workspace authorization and 2FA are not implemented. Future 2FA must extend the
account authentication boundary rather than a frontend-only gate.

Exact user-requested structure:

```text
SETTINGS
└── INTERFACE
    └── Web UI
        └── Enable / Disable
```

**Product requirement:** TUI must expose this persistent switch while WebUI is off. When enabled, Klaude hosts the browser interface; when disabled, browser hosting stops without removing CLI/TUI ability, model services, sessions, knowledge or settings. Browser settings may show the same host state, with a confirmation before disabling itself.

**Recommended baseline (not implemented and not mandated by inventory):** default **Off**; bind to **127.0.0.1** only; randomized/token-protected local credential or similarly robust authenticated browser access even on loopback; same-origin/Origin + CSRF checks; narrowly scoped cookie/session settings; no wildcard CORS; explicit review required to enable LAN. Hosting URL/port should be detected and shown, not confused with `services.ollama_url`, `web.provider`, MCP OAuth `127.0.0.1:8765`, or model-serving port `8080`.

**Do not conflate persistent preference with running process.** The Web UI settings row should represent: Disabled; Starting; Running (open/copy URL); Stopping; Failed (diagnostic/retry); Enabled but not currently hosted (if startup mode defers launch). Specify who owns the server process and how it persists after a TUI exit. Prefer a host-owned service/lifecycle independent from a browser tab and chat turn. Explicit Stop/Disable should revoke new access and perform reviewed cancellation/drain, **not** automatically terminate separately owned model servers or claim to roll back executed edits.

**Open decisions before implementation:** startup service/daemon method per OS, port selection and collisions, host exit semantics, authentication bootstrap and logout, remote/LAN access policy, server updates, multi-user access (not currently supported), and exact persistent key/path. Do not assume a listening loopback port is sufficient authorization for dangerous local tools.

## 6. Operational interaction specifications

### Tool approval and human input

Server issues stable, short-lived approvals correlated to **session + turn + operation + tool + exact arguments + policy revisions**. Browser shows clear Allow once / Deny / applicable remembered choice; default focus on safer action for destructive operations. Timeout, stale prompts and permission changes produce explicit rejection/re-evaluation. Scope, preflight and filesystem restrictions remain enforced after any displayed decision. Handle user-input options as the same turn, not an invented new message/request.

### Streaming, cancellation, reconnect

Define versioned public DTO/event contract and typed events: `turn.started`, `message.delta`, `tool.requested`, `approval.required`, `tool.started`, `tool.finished`, `subagent.progress`, `user_input.required`, `turn.partial`, `turn.completed`, `turn.failed`, `turn.cancelled`, `session.state`. Event names are **proposed**, not existing Python API. Publish no provider signatures/private chain/model_content/secret values. Reconnect by snapshot + event cursor; if history pruned, reconcile from current state, never replay writes/commands by default. Cancel means request to stop at safe boundary; executed effects may remain.

### Workspaces and file boundaries

Browser-selected/uploaded file ≠ host filesystem path. Support explicit host-root workspace selection through a restricted server-side chooser, attach-as-copy upload with size/MIME limits, and safe bounded previews. Filesystem edits use existing tool execution path and Git dirty-tree/mutation lock, not a second unrestricted editor. Provide exact path/diff/line-number references and source freshness states. Do not create a generic localhost fetch/proxy that bypasses protected web-fetch destinations.

### Models, auth and resource management

Connections: **Add → Test (without generation) → Save → Discover models → Enable/Hide/Pin → Select chat/role**. Show saved connection/provider capabilities and failure reasons independently. Handle Codex auth separately from OpenAI API keys. For model downloads/builds/serving/SSH trust, show review of identity/ports/paths/resources and status/receipt/progress. Adopt/Stop/Delete/Build are high-impact actions; require exact targets and fresh revision checks. Tab close ≠ process death; outcomes `unknown` remain unknown until refreshed/verified. Make Linux-only steps explicit with unsupported-host explanations.

### Library and research

A document imported into private Library is not automatically knowledge. Knowledge Learn and research report Learn are explicit separate operations. Research has its own bounded queue/job/result/partial/re-fetch semantics; images generated through the partial native consumer must show availability and validation limitations. Artifacts keep original/provenance/export lifetimes distinct. The browser can preview/download without invoking a host desktop opener.

## 7. API/service seams to plan before choosing frontend tech

Propose an **application façade** sitting above existing core services and below CLI/TUI/WebUI adapters:

```text
      Browser UI  ─┐
                   ├── shared application/use-case layer ── Agent / Providers /
      Terminal UI ─┘       │                              Tools / Knowledge /
                          ├── permission + user-input     Memory / Research /
                          │   brokers                    Model Manager
                          ├── session event/lease manager
                          ├── server-owned operations
                          └── config/secret revision services

              Web transport adapter = auth + validated DTOs +
              HTTP operations + server-side events, NOT a new agent loop
```

Evaluate extracting from CLI: `_build_agent` orchestration, registered tool construction and selectors, prompt enrichment, permission/input brokers, model picker/runtime changes, session IO coordinator, settings writers, long-running operation ownership. Preserve `Agent.run` and actual service semantics; refactor in small verification-backed slices. Existing web/knowledge MCP servers are limited integrations, not substitutes for a full-agent API.

### Bridge-first architecture and implementation gate

Before selecting UI components or implementing frontend screens, Codex should produce an **architecture RFC** scoped to the existing source and current dirty worktree. This is an inspection/documentation deliverable rather than permission for a broad refactor. The RFC should specify:

1. **Current call map** from CLI orchestration (`_build_agent`, session IO, permission/user-input brokers, worker/process owners and settings writers) to `Agent.run` and durable stores; distinguish already reusable code from UI-coupled code.
2. **Shared application interface** callable from the CLI, a test harness and a future Web adapter: session lifecycle, model/session options, submit/cancel/queue/steer, approval/input, public event streams, and settings read/write.
3. **Versioned contracts** with sanitized public DTOs; unique operation/request IDs, sequence cursors, leases, ownership, snapshots, backpressure, terminal states, partial/unknown outcomes, and idempotency/reconnect semantics. Do not surface private model continuation, unredacted logs or stored credentials.
4. **Host boundary and threat model** covering authorization even on localhost, same-origin/CSRF, browser downloads/uploads, file and URL jails, tool permission replay, network binding, credential storage and per-operation scopes. Explicitly separate future HTTP transport from the in-process application façade.
5. **Runtime/host lifecycle** independent of browser tab and TUI, with enabling/disabling, recovery, default-off loopback binding, process ownership, worker cancellation/drain, and handling of separately owned model services.
6. **Incremental migration sequence and tests** with the smallest first proof: headless sessions + one chat turn + streamed sanitized public events + approval/denial + cancellation + resume. Preserve CLI/TUI behavior and existing locks/leases; no big-bang move of `main.py`.

**Gate:** Approve the RFC before extracting shared application services. After extraction, prove the same model/tool workflow works via headless service and existing TUI before shipping a Web host, then validate host security before mounting a frontend. Dynamic WebUI theme preferences are a frontend-facing independent feature and must not affect agent state.

### Proposed service capabilities (contract sketch, not URL spec)

`Sessions` (list/search/create/resume/fork/archive/delete/export/watch/lease), `Turns` (submit/queue/steer/cancel/status/stream/approve/input), `Workspaces` (select/read/search/status/diff/review/init), `Models` (connection CRUD/test/discovery/default roles), `ModelOperations` (pull/build/serve/adopt/stop/SSH), `Settings` (read effective/schema/write with revision), `Integrations` (Skills/MCP/search/OAuth), `Library` (knowledge/docs/artifacts/media), `Research` (submit/progress/resume/report/learn), `Hosting` (status/enable/disable), `Diagnostics` (health/storage/model/resource usage).

Security must be settled **before** exposing mutation endpoints: local authentication bootstrap, binding/origin/CSRF checks, credentials never returned raw, non-idempotent operation IDs, rate/size limits, text/Markdown sanitization, permission ownership, path/URL input validation, logs redaction, and fail-closed behavior. Model-serving and SSH supervisor lifetime cannot be silently tied to a web request or tab.

## 8. Implementation sequencing proposal (gated)

This is **not** approval to start coding. Request architecture review/sign-off before implementation.

| Phase | Focus | Gate to advance |
| --- | --- | --- |
| 0. Bridge RFC and design sign-off | Confirm shared app-service contracts, CLI extraction seams, public event DTOs, security/lifecycle, routes, hosting semantics and theme requirements | Reviewed bridge RFC, feature-route matrix and explicit decisions; no frontend code |
| 1. Shared service extraction | Move CLI-owned use cases/brokers into shared layer with TUI behavior unchanged | Current CLI and focused regression tests still pass |
| 2. Secure local Web host foundation | TUI INTERFACE toggle, host lifecycle, auth, session DTO/event protocols, state reattachment | Loopback/Origin/CSRF, disconnect/disable and stale event tests pass |
| 3. Core Chat and Workspaces | Sessions, model/mode, composer, streaming, queue/steer/cancel, approvals, files/diff/review | Real local agent run with tools, cancellation and second-client resume passes |
| 4. Settings and Models | All supported effective preferences, revisions, roles, endpoint tests, local Ollama inventory | Settings cross-client stale writes, masked credentials, endpoint identity tests pass |
| 5. Knowledge/Library/Integrations | Skills, MCP, memory, indexing/crawl, documents, Research, image analysis/generation with truthful partial status | Separate lifecycle/unknown outcome and file-safety tests pass |
| 6. Advanced Model Manager & polish | Trusted build/install/serve/SSH, process ownership, logs, accessibility, responsive visual QA | Safe reviewed operations, refresh/reconnect/lease tests, keyboard/mobile/a11y audits pass |

**Release coverage is not a justification to silently omit advanced capabilities.** If a phase is incomplete, clearly label the WebUI as partial and retain accessible TUI controls; keep a tracked parity checklist.

## 9. Review questions requiring product decisions

1. Is the WebUI always **single local owner**, with any remote/LAN mode explicitly deferred? Recommended yes initially.
2. Should the host **continue after exiting the TUI** when enabled? Recommended yes, but this implies a durable local host/daemon owner.
3. Does **Enabled** mean start automatically on machine login, start when Klaude launches, or only through a service command? Recommend separating "preference enabled" from "host running" and documenting startup clearly.
4. Should an **Overview** page exist? Recommended optional later; use its clock/shapes/status without displacing Chat as the landing page.
5. Should an in-browser **interactive PTY** be a new feature later? Inventory does not contain one; exclude initially.
6. Do we have **Odysseus screenshots or source** approved as a direct UX reference? Needed before specifying detailed tab/button placement.
7. Which WebUI themes should ship first (preset/seed-color palettes), and should image-derived palettes arrive after basic light/dark/system? Recommended stage it.
8. Preferred technology stack? Decide only after server/application boundaries and Material 3 Expressive component coverage are understood; possible React/TypeScript with Material-themed primitives, but **no library is mandated here**.

## 10. Quality and acceptance criteria

- The application visibly follows **Material Design 3 Expressive**, with cohesive tonal surfaces, expressive shapes, grouped controls and shared fluid motion, guided by the user's LineageOS and end-4 references.
- Navigation, drawers, inspector panels, dialogs and controls have responsive, interruptible transitions; streaming text and code remain stable and reduced-motion behavior is verified.
- End-to-end parity: feature-route mapping covers **all 103 audited feature groups** with conscious location or exclusion, and setting-field mapping covers **all 279 audited keys/families** according to actual scope.
- No terminal theme, custom ANSI spinner, divider or terminal-prompt geometry settings exposed as WebUI settings; browser styles may be separately configured.
- `INTERFACE → Themes & Colors` provides independent, persistent WebUI-only Material seed/preset palettes and System/Light/Dark behavior, with accessible semantic contrast; no existing TUI appearance storage is overwritten.
- Web UI Enable/Disable appears under `INTERFACE` in TUI and is persistent; current host URL/state and failures are visible; core stays usable with hosting off.
- No model/tool/workspace permission escalation, silent fallback, session data leak, raw credential read API, untrusted Markdown execution or duplicate non-idempotent actions on reconnect.
- All model request, research, media, download/build/serve/SSH and write operations accurately expose pending, result, partial/unknown, failure and cancellation semantics.
- Responsive navigation works at phone/tablet/desktop, keyboard-only and screen reader, with reduced motion and contrast checked; a clock graphic is never critical path.
- Docs/tests explicitly separate shipped, partial, planned and unavailable features.

## 11. Feature traceability — source IDs to proposed primary surface

Every feature ID comes from the uploaded audit. Several features also have secondary links, as described earlier. Source statuses/classifications remain authoritative; this table maps navigation, not implementation proof.

| ID | Audited feature | Status | Inventory UI class | Proposed primary surface |
| --- | --- | --- | --- | --- |
| F001 | Interactive agent and one-shot requests | Implemented | ADAPT | Chat / Activity inspector / Context |
| F002 | Plan mode and approval | Implemented | ADAPT | Chat / Activity inspector / Context |
| F003 | Adaptive structured execution state | Implemented | INTERNAL | Shared services / existing applicable inspector |
| F004 | Standard/Thinking modes and reasoning effort | Implemented | REQUIRED | Chat / Activity inspector / Context |
| F005 | Execution budgets and usage | Implemented | REQUIRED | Chat / Activity inspector / Context |
| F006 | Tool selection and capability awareness | Implemented | INTERNAL | Shared services / existing applicable inspector |
| F007 | Streaming and tool/subagent progress | Implemented | ADAPT | Chat / Activity inspector / Context |
| F008 | Cancellation and transport recovery | Implemented | ADAPT | Chat / Activity inspector / Context |
| F009 | Malformed calls, path recovery and bounded retries | Implemented | INTERNAL | Shared services / existing applicable inspector |
| F010 | Context compaction and recap | Implemented | ADAPT | Chat / Activity inspector / Context |
| F011 | Clarifying questions and structured user input | Implemented | ADAPT | Chat / Activity inspector / Context |
| F012 | Read-only delegated workers | Implemented | REQUIRED | Chat / Activity inspector / Context |
| F013 | Generated code response checks | Implemented | INTERNAL | Shared services / existing applicable inspector |
| F014 | Workspace selection and awareness | Implemented | ADAPT | Workspaces / Changes & Review |
| F015 | Repository instructions and initialization | Implemented | REQUIRED | Workspaces / Changes & Review |
| F016 | Read and search project files | Implemented | ADAPT | Workspaces / Changes & Review |
| F017 | Edit and create project files | Implemented | ADAPT | Workspaces / Changes & Review |
| F018 | Shell, builds and project validation | Implemented | ADAPT | Workspaces / Changes & Review |
| F019 | Dirty-tree safety and guarded Git mutations | Implemented | REQUIRED | Workspaces / Changes & Review |
| F020 | Git status, diff and read-only review | Implemented | ADAPT | Workspaces / Changes & Review |
| F021 | Permission policy and decision prompts | Implemented | ADAPT | Settings > Tools & Permissions |
| F022 | Built-in tool enable/disable and validation toggles | Implemented | REQUIRED | Settings > Tools & Permissions |
| F023 | Runtime and storage diagnostics | Implemented | ADAPT | Models > Hardware / Advanced Diagnostics |
| F024 | Ollama service controls | Implemented | ADAPT | Models > Hardware / Advanced Diagnostics |
| F025 | Native Ollama chat, embeddings and discovery | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F026 | Compatible HTTP model endpoints | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F027 | Cloud model providers | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F028 | OpenAI Codex account authentication | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F029 | Add, test and maintain endpoints | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F030 | Model inventory choices and picker | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F031 | AI Defaults and role inheritance | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F032 | Explicit Utility naming and recaps | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F033 | Runtime resource and sampling controls | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F034 | Per-session runtime continuity | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F035 | Downloaded Ollama inventory and loaded state | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F036 | Ollama pull and deletion | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F037 | Hugging Face GGUF discovery | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F038 | Installed engine and dependency inspection | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F039 | Trusted local llama.cpp CPU/CUDA builds | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F040 | Offline vLLM environment installation | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F041 | Retained build inventory, logs and guarded removal | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F042 | Managed local llama.cpp and vLLM serving | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F043 | Managed server stop, progress and private logs | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F044 | Reviewed adoption of existing servers | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F045 | Saved SSH servers and diagnostics default | Implemented | REQUIRED | Models / Model Manager / Runtime settings |
| F046 | SSH host-key trust and public-key enrollment | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F047 | Remote llama.cpp CPU and GPU serving | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F048 | Remote vLLM serving | Implemented | ADAPT | Models / Model Manager / Runtime settings |
| F049 | Session creation, names and organization | Implemented | REQUIRED | Chat > Sessions / Library Sessions |
| F050 | Resume, fork and session continuity | Implemented | REQUIRED | Chat > Sessions / Library Sessions |
| F051 | Session archive, restore, permanent deletion and clear | Implemented | ADAPT | Chat > Sessions / Library Sessions |
| F052 | Session export and unsupported import boundary | Partial | ADAPT | Chat > Sessions / Library Sessions |
| F053 | Cross-client watching and writer ownership | Implemented | ADAPT | Chat > Sessions / Library Sessions |
| F054 | Queued follow-ups and steering | Implemented | ADAPT | Chat > Sessions / Library Sessions |
| F055 | Text/file/folder attachments and inline references | Implemented | ADAPT | Chat > Sessions / Library Sessions |
| F056 | Durable facts and automatic memory | Implemented | REQUIRED | Memory & Privacy / Chat Sessions |
| F057 | Session recall tools | Implemented | REQUIRED | Memory & Privacy / Chat Sessions |
| F058 | Named knowledge libraries and hybrid retrieval | Implemented | REQUIRED | Library > Knowledge |
| F059 | URL/file learning and atomic indexing | Implemented | ADAPT | Library > Knowledge |
| F060 | Refreshable docs sources | Implemented | ADAPT | Library > Knowledge |
| F061 | Polite bounded website crawling | Implemented | ADAPT | Library > Knowledge |
| F062 | Web search routing and providers | Implemented | REQUIRED | Settings > Search & Knowledge / Chat sources |
| F063 | Search cost, relevance and location policy | Implemented | OPTIONAL | Settings > Search & Knowledge / Chat sources |
| F064 | Local-first URL extraction and HTTP diagnostics | Implemented | ADAPT | Settings > Search & Knowledge / Chat sources |
| F065 | Code/documentation search and Hugging Face tools | Implemented | REQUIRED | Settings > Search & Knowledge / Chat sources |
| F066 | Time and weather tools | Implemented | REQUIRED | Settings > Search & Knowledge / Chat sources |
| F067 | Evidence sources and resumable research receipts | Implemented | INTERNAL | Shared services / existing applicable inspector |
| F068 | Bounded Deep Research jobs | Implemented | ADAPT | Library > Research / Activity |
| F069 | Research queue, resume and report lifecycle | Implemented | ADAPT | Library > Research / Activity |
| F070 | Installed Skills and model-led reading | Implemented | REQUIRED | Integrations > Skills / MCP |
| F071 | Skills discovery and verified remote installation | Implemented | ADAPT | Integrations > Skills / MCP |
| F072 | Skills local import and drop inbox | Implemented | ADAPT | Integrations > Skills / MCP |
| F073 | Skills manage, updates and deletion | Implemented | ADAPT | Integrations > Skills / MCP |
| F074 | External MCP server connections | Implemented | REQUIRED | Integrations > Skills / MCP |
| F075 | MCP Registry search and reviewed installation | Implemented | ADAPT | Integrations > Skills / MCP |
| F076 | MCP import, maintenance and updates | Implemented | ADAPT | Integrations > Skills / MCP |
| F077 | MCP secrets and remote OAuth | Implemented | ADAPT | Integrations > Skills / MCP |
| F078 | Klaude web and knowledge MCP servers | Implemented | OPTIONAL | Integrations > Skills / MCP |
| F079 | Unified Library navigation | Implemented | REQUIRED | Library > Documents / Media / Research |
| F080 | Private document/media import and browsing | Implemented | ADAPT | Library > Documents / Media / Research |
| F081 | Artifact preview, host open and export | Implemented | ADAPT | Library > Documents / Media / Research |
| F082 | Manual tags, archive, restore and delete | Implemented | ADAPT | Library > Documents / Media / Research |
| F083 | Reviewed Media image analysis | Implemented | ADAPT | Library > Documents / Media / Research |
| F084 | Chat and one-shot image attachments | Implemented | ADAPT | Library > Documents / Media / Research |
| F085 | Vision provider capability verification | Implemented | INTERNAL | Shared services / existing applicable inspector |
| F086 | Local image-service settings | Partial | ADAPT | Library > Documents / Media / Research |
| F087 | Reviewed image generation and provenance | Partial | ADAPT | Library > Documents / Media / Research |
| F088 | Generation status, scoped cancel and result recovery | Partial | ADAPT | Library > Documents / Media / Research |
| F089 | Structured settings navigation | Implemented | ADAPT | Settings / Command palette / Help |
| F090 | Atomic settings and credential revisions | Implemented | INTERNAL | Shared services / existing applicable inspector |
| F091 | Command help, completion and discoverability | Implemented | ADAPT | Settings / Command palette / Help |
| F092 | Terminal appearance and previews | Implemented | TUI-ONLY | Exclude TUI mechanics |
| F093 | Terminal composer and rendering controls | Implemented | TUI-ONLY | Exclude TUI mechanics |
| F094 | Diagnostics, evaluation hooks and packaging | Implemented | INTERNAL | Advanced diagnostics (developer-only) |
| F095 | Library/collection compatibility aliases | Implemented | DEPRECATED | Backend compatibility; no separate UI |
| F096 | INTERFACE → Web UI → Enable / Disable | Planned | REQUIRED | INTERFACE / WebUI design (planned) |
| F097 | Browser visual design and responsive accessibility | Planned | OPTIONAL | INTERFACE / WebUI design (planned) |
| F098 | Optional AI media tag suggestions | Planned | OPTIONAL | Future scope only; do not claim shipped |
| F099 | Additional media consumers and provider certification | Partial | OPTIONAL | Future scope only; do not claim shipped |
| F100 | Gallery canvas, speech and email writing style | Planned | OPTIONAL | Future scope only; do not claim shipped |
| F101 | Installation, configuration presets and optional local services | Implemented | OPTIONAL | Advanced > Setup guidance |
| F102 | Explicitly learn a saved research report | Implemented | ADAPT | Library > Research / Activity |
| F103 | Declared advanced controls with unverified active effect | Partial | OPTIONAL | Advanced > Unverified controls (not active UI toggles) |

## 12. Settings traceability — source IDs to place/control type

Every setting/control ID from the source inventory is included. These are **not all persistent user preferences**: many are connection definition fields, reviewed operation inputs or temporary view state. TUI-only and internal settings are deliberately not made general browser switches.

| ID | Exact source key / control | Status | Inventory UI class | WebUI location / type |
| --- | --- | --- | --- | --- |
| S001 | `models.tier` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S002 | `services.ollama_url` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S003 | `services.searxng_url` | Implemented | REQUIRED | Settings > Advanced (source-validated) |
| S004 | `services.crawl4ai_url` | Implemented | REQUIRED | Settings > Advanced (source-validated) |
| S005 | `services.crawl4ai_api_key` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S006 | `crawler.user_agent` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S007 | `web.provider` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S008 | `web.gemini_api_key` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S009 | `cloud.openai_api_key` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S010 | `cloud.openrouter_api_key` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S011 | `web.brave_search_api_key` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S012 | `web.parallel_api_key` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S013 | `web.tavily_api_key` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S014 | `web.firecrawl_api_key` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S015 | `web.searxng_secret` | Partial | OPTIONAL | Settings > Search & Knowledge > Services/Credentials |
| S016 | `web.exa_api_key` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S017 | `web.exa_base_url` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S018 | `huggingface.api_key` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S019 | `huggingface.base_url` | Implemented | REQUIRED | Settings > Search & Knowledge > Services/Credentials |
| S020 | `models.override.<role>` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S021 | `ollama.think` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S022 | `ollama.code_think` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S023 | `permissions.<tool>` | Implemented | REQUIRED | Settings > Tools & Permissions |
| S024 | `agent.max_steps` | Implemented | REQUIRED | Settings > Agent > Budgets/Recovery |
| S025 | `agent.max_tool_calls` | Implemented | REQUIRED | Settings > Agent > Budgets/Recovery |
| S026 | `agent.max_total_tokens` | Implemented | REQUIRED | Settings > Agent > Budgets/Recovery |
| S027 | `agent.max_subagent_concurrency` | Implemented | REQUIRED | Settings > Agent > Budgets/Recovery |
| S028 | `agent.max_code_continuations` | Implemented | REQUIRED | Settings > Agent > Budgets/Recovery |
| S029 | `agent.max_code_repairs` | Implemented | REQUIRED | Settings > Agent > Budgets/Recovery |
| S030 | `agent.retrieval_k` | Implemented | REQUIRED | Settings > Models & AI / Agent |
| S031 | `tool_validation.knowledge_search` | Implemented | REQUIRED | Settings > Tools & Permissions |
| S032 | `knowledge.snapshot_retention` | Implemented | REQUIRED | Settings > Search & Knowledge > Knowledge/Crawler |
| S033 | `crawler.max_depth` | Implemented | REQUIRED | Settings > Search & Knowledge > Knowledge/Crawler |
| S034 | `crawler.max_pages` | Implemented | REQUIRED | Settings > Search & Knowledge > Knowledge/Crawler |
| S035 | `crawler.delay_min` | Implemented | REQUIRED | Settings > Search & Knowledge > Knowledge/Crawler |
| S036 | `crawler.delay_max` | Implemented | REQUIRED | Settings > Search & Knowledge > Knowledge/Crawler |
| S037 | `crawler.respect_robots` | Implemented | REQUIRED | Settings > Search & Knowledge > Knowledge/Crawler |
| S038 | `runtime_context.enabled` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S039 | `runtime_context.provider` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S040 | `runtime_context.refresh_seconds` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S041 | `runtime_context.command_timeout_seconds` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S042 | `runtime_context.max_prompt_characters` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S043 | `runtime_context.include_workspace` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S044 | `runtime_context.include_git` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S045 | `runtime_context.include_displays` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S046 | `runtime_context.include_disks` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S047 | `runtime_context.include_local_ip` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S048 | `runtime_context.show_install_suggestion` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S049 | `runtime_context.location.mode` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S050 | `runtime_context.location.configured_country` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S051 | `runtime_context.location.configured_region` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S052 | `runtime_context.location.allow_network_lookup` | Implemented | OPTIONAL | Settings > Memory & Privacy > Runtime context |
| S053 | `entities.wikimedia.enabled` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S054 | `entities.wikimedia.timeout_seconds` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S055 | `entities.wikimedia.max_results` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S056 | `entities.metadata_refresh_days` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S057 | `web.billing.mode` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S058 | `web.billing.allow_paid_overage` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S059 | `web.billing.allow_auto_recharge` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S060 | `web.search.strategy` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S061 | `search_settings.provider` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S062 | `search_settings.fallbacks` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S063 | `search_settings.results` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S064 | `web.search.stop_when_sufficient` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S065 | `web.search.provider_order` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S066 | `web.search.allow_explicit_provider_fallback` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S067 | `web.search.skip_unconfigured_providers` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S068 | `web.search.fallback_on_quota` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S069 | `web.search.fallback_on_unavailable` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S070 | `web.search.fallback_on_low_relevance` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S071 | `web.search.strict_result_filtering` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S072 | `tool_validation.web_search` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S073 | `web.search.return_unrelated_results` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S074 | `web.search.max_provider_attempts` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S075 | `web.search.max_results_per_domain` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S076 | `web.search.relevance.candidate_discovery_threshold` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S077 | `web.search.relevance.final_verification_threshold` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S078 | `web.search.minimum_relevance` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S079 | `web.search.relevance.strict_entity_threshold` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S080 | `web.search.minimum_authority` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S081 | `web.search.max_attempts_per_provider` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S082 | `web.search.base_retry_delay_ms` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S083 | `web.search.maximum_retry_delay_seconds` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S084 | `web.search.honor_retry_after` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S085 | `web.search.cache_enabled` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S086 | `web.search.max_disambiguation_queries` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S087 | `web.search.minimum_confident_entity_score` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S088 | `web.search.minimum_winner_margin` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S089 | `web.search.location.enabled` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S090 | `web.search.location.use_runtime_country` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S091 | `web.search.location.send_country_for_local_intent_only` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S092 | `web.search.location.maximum_inferred_location_weight` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S093 | `web.search.behavior.max_query_rewrites` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S094 | `web.search.behavior.max_provider_fallbacks` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S095 | `web.search.behavior.max_web_actions` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S096 | `web.search.behavior.max_search_calls` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S097 | `web.search.behavior.max_fetch_calls` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S098 | `web.search.behavior.max_pages_per_domain` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S099 | `web.search.behavior.max_consecutive_failures` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S100 | `web.search.behavior.max_total_search_calls` | Implemented | DEPRECATED | Settings > Search & Knowledge (Advanced when needed) |
| S101 | `web.search.behavior.max_fetch_attempts` | Implemented | DEPRECATED | Settings > Search & Knowledge (Advanced when needed) |
| S102 | `web.search.behavior.max_repeated_query_similarity` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S103 | `fetch_settings.provider` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S104 | `fetch_settings.exa_fallback` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S105 | `fetch_settings.crawl4ai_enabled` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S106 | `fetch_settings.exa_enabled` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S107 | `web.fetch.timeout_seconds` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S108 | `web.fetch.max_download_bytes` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S109 | `web.fetch.max_content_characters` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S110 | `web.fetch.max_redirects` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S111 | `web.fetch.cache_ttl_seconds` | Implemented | REQUIRED | Settings > Search & Knowledge (Advanced when needed) |
| S112 | `web.verification.max_domains` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S113 | `web.verification.max_pages_per_domain` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S114 | `web.verification.max_total_verification_pages` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S115 | `web.verification.same_domain_only` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S116 | `web.verification.respect_robots` | Partial | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S117 | `web.providers.<provider>.enabled` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S118 | `web.providers.<provider>.api_key_env` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S119 | `web.providers.<provider>.last_resort_only` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S120 | `web.providers.<provider>.automatic_merge` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S121 | `web.providers.<provider>.default_depth` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S122 | `web.providers.<provider>.timeout_seconds` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S123 | `web.providers.<provider>.cooldown_seconds` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S124 | `web.providers.<provider>.local_request_limit` | Implemented | OPTIONAL | Settings > Search & Knowledge (Advanced when needed) |
| S125 | `ollama.options.num_ctx` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S126 | `ollama.options.num_thread` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S127 | `ollama.options.num_gpu` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S128 | `ollama.options.num_predict` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S129 | `ollama.options.top_k` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S130 | `ollama.options.seed` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S131 | `ollama.options.temperature` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S132 | `ollama.options.top_p` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S133 | `ollama.options.min_p` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S134 | `ollama.options.presence_penalty` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S135 | `ollama.options.frequency_penalty` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S136 | `ollama.options.repeat_penalty` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S137 | `ollama.code_options.num_ctx` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S138 | `ollama.code_options.num_thread` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S139 | `ollama.code_options.num_gpu` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S140 | `ollama.code_options.num_predict` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S141 | `ollama.code_options.top_k` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S142 | `ollama.code_options.seed` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S143 | `ollama.code_options.temperature` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S144 | `ollama.code_options.top_p` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S145 | `ollama.code_options.min_p` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S146 | `ollama.code_options.presence_penalty` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S147 | `ollama.code_options.frequency_penalty` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S148 | `ollama.code_options.repeat_penalty` | Implemented | OPTIONAL | Settings > Models & AI > Ollama parameters |
| S149 | `runtime_device_mode` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S150 | `runtime_options.num_ctx` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S151 | `runtime_options.num_thread` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S152 | `runtime_options.num_gpu` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S153 | `runtime_options.max_steps` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S154 | `runtime_options.max_tool_calls` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S155 | `runtime_options.max_total_tokens` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S156 | `runtime_options.max_subagent_concurrency` | Implemented | REQUIRED | Settings > Runtime / Agent execution |
| S157 | `tool_availability.<builtin_name>` | Implemented | REQUIRED | Settings > Tools & Permissions |
| S158 | `web_provider_availability.<provider>` | Implemented | REQUIRED | Settings > Search & Knowledge > Providers |
| S159 | `permissions.<tool>` | Implemented | REQUIRED | Settings > Tools & Permissions |
| S160 | `display.activity_updates` | Implemented | ADAPT | Settings > Agent > Activity |
| S161 | `composer_mode` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S162 | `last_model` | Implemented | INTERNAL | Settings > Models & AI > Model selection |
| S163 | `require_model_selection` | Implemented | INTERNAL | Settings > Models & AI > Model selection |
| S164 | `search_settings.tavily_depth` | Implemented | REQUIRED | Settings > Search & Knowledge |
| S165 | `search_settings.searxng_url` | Implemented | REQUIRED | Settings > Search & Knowledge |
| S166 | `fetch_settings.crawl4ai_url` | Implemented | REQUIRED | Settings > Search & Knowledge |
| S167 | `ai_defaults.chat` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S168 | `ai_defaults.utility` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S169 | `ai_defaults.fallbacks` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S170 | `ai_defaults.output_tokens` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S171 | `ai_defaults.research` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S172 | `ai_defaults.vision` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S173 | `ai_defaults.vision_enabled` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S174 | `ai_defaults.vision_fallbacks` | Implemented | REQUIRED | Settings > Models & AI > AI Defaults |
| S175 | `research.provider` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S176 | `research.output_tokens` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S177 | `research.extract_timeout` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S178 | `research.parallel` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S179 | `research.timeout` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S180 | `research.rounds` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S181 | `research.queries` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S182 | `research.sources` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S183 | `research.context_tokens` | Implemented | REQUIRED | Settings > Search & Knowledge > Research |
| S184 | `connections.<id>.id` | Implemented | REQUIRED | Models > Connections / Model choices |
| S185 | `connections.<id>.name` | Implemented | REQUIRED | Models > Connections / Model choices |
| S186 | `connections.<id>.backend` | Implemented | REQUIRED | Models > Connections / Model choices |
| S187 | `connections.<id>.base_url` | Implemented | REQUIRED | Models > Connections / Model choices |
| S188 | `connections.<id>.source` | Implemented | REQUIRED | Models > Connections / Model choices |
| S189 | `connections.<id>.key_env` | Implemented | REQUIRED | Models > Connections / Model choices |
| S190 | `connections.<id>.enabled` | Implemented | REQUIRED | Models > Connections / Model choices |
| S191 | `model_choices.<connection>.<model>.enabled` | Implemented | REQUIRED | Models > Connections / Model choices |
| S192 | `model_choices.<connection>.<model>.hidden` | Implemented | REQUIRED | Models > Connections / Model choices |
| S193 | `model_choices.<connection>.<model>.pinned` | Implemented | REQUIRED | Models > Connections / Model choices |
| S194 | `servers.<id>.definition.id` | Implemented | REQUIRED | Models > SSH server definitions |
| S195 | `servers.<id>.definition.name` | Implemented | REQUIRED | Models > SSH server definitions |
| S196 | `servers.<id>.definition.host` | Implemented | REQUIRED | Models > SSH server definitions |
| S197 | `servers.<id>.definition.user` | Implemented | REQUIRED | Models > SSH server definitions |
| S198 | `servers.<id>.definition.port` | Implemented | REQUIRED | Models > SSH server definitions |
| S199 | `servers.<id>.definition.identity_file` | Implemented | REQUIRED | Models > SSH server definitions |
| S200 | `servers.<id>.definition.known_hosts` | Implemented | REQUIRED | Models > SSH server definitions |
| S201 | `servers.<id>.definition.models_dir` | Implemented | REQUIRED | Models > SSH server definitions |
| S202 | `servers.<id>.definition.use_agent` | Implemented | REQUIRED | Models > SSH server definitions |
| S203 | `default` | Implemented | REQUIRED | Models > SSH server definitions |
| S204 | `servers.<name>.name` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S205 | `servers.<name>.transport` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S206 | `servers.<name>.enabled` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S207 | `servers.<name>.command` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S208 | `servers.<name>.args` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S209 | `servers.<name>.url` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S210 | `servers.<name>.env` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S211 | `servers.<name>.headers` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S212 | `servers.<name>.cwd` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S213 | `servers.<name>.tools` | Implemented | INTERNAL | Integrations > MCP / Skills definition |
| S214 | `servers.<name>.source` | Implemented | INTERNAL | Integrations > MCP / Skills definition |
| S215 | `servers.<name>.oauth` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S216 | `servers.<name>.oauth_scope` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S217 | `servers.<name>.oauth_client_metadata_url` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S218 | `manifest.enabled` | Implemented | REQUIRED | Integrations > MCP / Skills definition |
| S219 | `theme.interface` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S220 | `theme.text` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S221 | `input_field.border` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S222 | `input_field.min_height` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S223 | `input_field.max_height` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S224 | `divider.visible` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S225 | `divider.color` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S226 | `divider.text_color` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S227 | `divider.pattern` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S228 | `spinner.name` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S229 | `spinner.custom_frames` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S230 | `spinner.custom_interval` | Implemented | TUI-ONLY | Exclude: TUI appearance/composer |
| S231 | `auto_memory_enabled` | Implemented | REQUIRED | Settings > Memory & Privacy |
| S232 | `enabled` | Partial | REQUIRED | Settings > Models & AI > Image Generation |
| S233 | `endpoint` | Partial | REQUIRED | Settings > Models & AI > Image Generation |
| S234 | `model` | Partial | REQUIRED | Settings > Models & AI > Image Generation |
| S235 | `revision` | Partial | INTERNAL | Settings > Models & AI > Image Generation |
| S236 | `LaunchSpec.engine` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S237 | `LaunchSpec.executable` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S238 | `LaunchSpec.model` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S239 | `LaunchSpec.name` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S240 | `LaunchSpec.port` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S241 | `LaunchSpec.context` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S242 | `LaunchSpec.threads` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S243 | `LaunchSpec.gpu_layers` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S244 | `LaunchSpec.gpu` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S245 | `LaunchSpec.memory` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S246 | `LaunchSpec.adopt_pid` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S247 | `LaunchSpec.model_id` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S248 | `LaunchSpec.ssh_server` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S249 | `LaunchSpec.local_port` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S250 | `LaunchSpec.dtype` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S251 | `LaunchSpec.enforce_eager` | Implemented | ADAPT | Models > Serve/Adopt request form |
| S252 | `build.source` | Implemented | ADAPT | Models > Dependencies build/install form |
| S253 | `build.profile` | Implemented | ADAPT | Models > Dependencies build/install form |
| S254 | `build.jobs` | Implemented | ADAPT | Models > Dependencies build/install form |
| S255 | `build.architectures` | Implemented | ADAPT | Models > Dependencies build/install form |
| S256 | `build.host_compiler` | Implemented | ADAPT | Models > Dependencies build/install form |
| S257 | `vllm.wheelhouse` | Implemented | ADAPT | Models > Dependencies build/install form |
| S258 | `vllm.python` | Implemented | ADAPT | Models > Dependencies build/install form |
| S259 | `vision.question` | Implemented | ADAPT | Library > Media action form |
| S260 | `vision.context` | Implemented | ADAPT | Library > Media action form |
| S261 | `vision.output_tokens` | Implemented | ADAPT | Library > Media action form |
| S262 | `generation.prompt` | Implemented | ADAPT | Library > Media action form |
| S263 | `generation.width` | Implemented | ADAPT | Library > Media action form |
| S264 | `generation.height` | Implemented | ADAPT | Library > Media action form |
| S265 | `generation.steps` | Implemented | ADAPT | Library > Media action form |
| S266 | `generation.seed` | Implemented | ADAPT | Library > Media action form |
| S267 | `plan_mode` | Implemented | REQUIRED | Chat > Session controls (per-session) |
| S268 | `session_runtime.model` | Implemented | REQUIRED | Chat > Session controls (per-session) |
| S269 | `session_runtime.mode` | Implemented | REQUIRED | Chat > Session controls (per-session) |
| S270 | `session_runtime.effort` | Implemented | REQUIRED | Chat > Session controls (per-session) |
| S271 | `installed.filter` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S272 | `skill_search.provider` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S273 | `skill_search.sort` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S274 | `skill_search.page` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S275 | `mcp_search.sort` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S276 | `library.view` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S277 | `library.query` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S278 | `library.sort` | Implemented | ADAPT | Transient filter / own page (not global preference) |
| S279 | `library.offset` | Implemented | ADAPT | Transient filter / own page (not global preference) |

## 13. Reference and provenance

**Inventory (audited worktree):** `webui-feature-inventory.md`. Feature IDs, stored keys, validation, source paths and current implementation statuses in this planning spec are derived from that file—not from a fresh examination of the repository. Its audit explicitly has limitations regarding live models/hardware and previously observed small-model coding benchmark failures.

**External design research:**

- [end-4/dots-hyprland](https://github.com/end-4/dots-hyprland) — requested inspiration; use visual principles, not unchecked source copies.
- [Google Material 3 Expressive — design research](https://design.google/library/expressive-material-design-google-research) — official expressive use of color, shape, size, motion and containment.
- [Google Developers — Material 3 Expressive shape and motion](https://developer.android.com/design/ui/wear/guides/get-started/design-language) — specific shape/morphing examples apply to Wear OS; adapt appropriately to desktop web.
- [Open WebUI — Chat Features](https://docs.openwebui.com/features/chat-conversations/chat-features/) and [Workspace](https://docs.openwebui.com/features/workspace/) — public documented navigation/capability references, not feature parity obligations.
- [Impeccable](https://github.com/pbakaus/impeccable) — optional design QA guidance. 

**Do not implement yet.** Next concrete output should be low-/mid-fidelity navigation and two screen prototypes (Chat, Settings > INTERFACE) plus a reviewed application-layer interface contract; then obtain product sign-off.
