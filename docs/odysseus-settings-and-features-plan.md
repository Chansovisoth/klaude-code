# Odysseus settings and feature plan for Klaude

2026-10-16 follow-up: Model Defaults is the current public name; empty role initialization and the Models → Agent → Advanced → Appearance order are implemented. [Validation](model-defaults-navigation-validation.md). Image attachment reliability is implemented separately: [evidence](image-attachment-reliability-validation.md). Historical phase labels below are retained.

Status: S0 reliability and S1 model connection foundation implemented and validated locally;
S2a connection pages/maintenance and S2b AI Defaults are implemented and validated locally.
S2c's DeepSeek and native Anthropic slices are implemented and validated locally.
S3a Web Search and URL Fetch are implemented and validated locally.
S3b execution controls, registry-derived tool groups and navigation migration are implemented
and validated locally. [S3b follow-up evidence](s3b-agent-tools-validation.md).
S4a/S4b Library and Research, and S5a/S5b Model Manager are implemented and locally
validated. S5c's local dependency/CPU-build, SSH settings/diagnostics and owned
remote CPU serving and reviewed existing-public-key/host-trust slices are
implemented. CUDA build profiles and offline NVIDIA vLLM wheel setups are also
implemented; reviewed retained setup removal is also implemented.
Remote llama.cpp GPU/vLLM profiles and reviewed remote adoption are implemented
and exercised through actual CLI/TUI inference. S6a1 native Ollama image analysis
is implemented and exercised through actual CLI/TUI pixels. S6a2 coding-chat
images and private restore are also implemented and locally validated. S6a3a adds
native Anthropic/declared compatible HTTP chat images; S6a3b extends reviewed
Media analysis through the same HTTP adapters. S6a3c adds verified OpenRouter
chat/Media images with actual free-model generation and resume. S6a3d adds reviewed
OpenAI Responses chat/Media with real CLI/TUI TLS fixtures; live account generation
remains unverified; the earlier account probe exhausted credits and current
rechecks have not produced successful generation. S6a3e adds reviewed Gemini 2.5
Flash/Flash-Lite native chat/Media with CLI/TUI TLS fixtures; live generation is
unverified because both legacy IDs returned HTTP 404. S6a3f adds current Gemini
3.5 Flash-Lite/3.8 Flash Thinking chat with real Google RGB generation and live
Flash-Lite tool/image/process-resume evidence. S6a remains partial. S6b1 adds a
reviewed local stable-diffusion.cpp generation consumer with CLI/TUI protocol
fixtures. S6b2 adds real CPU inference, cancellation/recovery and exact-export
evidence; the final S6 pass also validated native CUDA CLI/TUI inference. Broader
image-quality certification remains open. S6b3 adds
private image-job management. S6c optional AI tags are implemented and verified
with actual native Gemma CLI/TUI calls. The final combined gate passed: 3,496 tests,
19 skips, Ruff, production mypy and fresh five-wheel packaging.
Original review: 2026-10-05. Klaude baseline at review: `fdb2386`.
Product direction updated: 2026-10-06; artifact/media management belongs in Library.
Delivery status updated: 2026-10-15; S0–S5 complete for the supported local scope;
S6a1/S6a2/S6a3a/S6a3b/S6a3c/S6a3d/S6a3e/S6a3f are implemented for their supported scopes;
remaining paid-provider certification and separately scoped generation extensions follow.

**Latest S6 gate (2026-10-15):** implementation is delivered for the recorded
scope; account certification is blocked. A fresh real Media CLI run confirms
OpenAI credits are exhausted; native Anthropic access is not configured, legacy
Gemini Flash returns HTTP 404 and Flash-Lite preparation timed out.
[Exact outcomes and unblock requirements](s6-completion-validation.md#final-account-access-audit).

**Feature verification (2026-10-15):** all 71 delivery checklist entries are
mapped to current source, tests and scoped runtime evidence in the
[S0–S6 verification report](odysseus-feature-verification.md). Fresh actual
Gemma/Library/settings/job/CUDA flows and the full local regression gate passed;
the two nested S6 certification entries remain unchecked.

Physical LAN/platforms and additional installer recipes
remain separately scoped extensions.
Live paid-provider certification remains unverified.

## 1. Objective and scope

Add the requested model, AI-default, search, and agent-tool settings with clear
navigation, then introduce Model Manager, Deep Research, and Library with a Media
view for coding artifacts. Reuse Klaude's working settings panel, runtime, permission,
retrieval, and persistence components. Keep ordinary chat fast and local model
defaults bounded.

Klaude remains a coding/agent environment. Library is its durable information
workspace; Media manages screenshots and image artifacts used or produced by
that work. A standalone Gallery and canvas/layer editing are outside this plan.

This document records the original scope and dated implementation/validation
updates; the status and delivery gates below distinguish them.
It does not advance the separate [agent orchestration plan](agent-orchestration-plan.md):
its final Phase 1 GPU comparisons remain pending and its later phases remain
unstarted. Coordinate future runtime changes with that plan's regression gates.

### Evidence and limits

The review covered the Odysseus frontend forms, their event handlers, backend
defaults, endpoint routes, research engine, feature modules, and specifications.
It compared these with Klaude's actual settings, configuration, runtime adapters,
execution governor, and existing storage. It also checked current official
server/provider documentation.

- Odysseus checked-out main: `934d23c0be29c9721385f34565c0ae2cbd60da04`.
- Latest fetched dev: `2992bf6d368a11472323e47d3bfed91e79cefc6b`.
- Compared the relevant settings and model/research files between those branches;
  the inspected page structure remains materially the same.
- The supplied endpoint addresses, installed-model counts, and chosen model are
  examples from the user's configuration. They were not probed during this review.
- This was source inspection, not a live Odysseus browser walkthrough or a test
  of paid providers. Visual polish and transport compatibility require later
  live validation; neither is established by this document.

## 2. What the review established

| Area | Finding | Consequence for Klaude |
| --- | --- | --- |
| Model connections | Odysseus separates adding endpoints, managing endpoints/models, and choosing defaults. | Adopt that separation. Klaude currently primarily offers session model selection and one configured Ollama URL. |
| Provider compatibility | Similar endpoint URLs can represent different API contracts and capabilities. | Keep native provider adapters; add explicit compatible-server support rather than routing every provider through one payload format. |
| Utility model | A separate endpoint/model and ordered fallbacks handle secondary AI work. | Add a role with real consumers and budgets. Klaude's deterministic context recap does not currently need an extra model call. |
| Search | Provider, credentials, results, tests, and fallback ordering share one page. | Move web-provider configuration out of the current mixed Tools/Providers pages. Preserve relevance routing and current fallback policy. |
| Agent tools | Tool availability and agent execution limits are grouped together. | Move step/worker limits from Runtime, retain separate permission policies, and derive groups from Klaude's actual registry. |
| Zero tool-call limit | Odysseus: unlimited. Klaude: automatic ceiling, normally 40 calls at 20 steps. | Preserve existing zero semantics through migration. Use named modes instead of an ambiguous numeric sentinel. |
| Research token limit | Odysseus's `research_max_tokens` reaches final report generation as `max_report_tokens`. | Label it **Max report tokens**; separate it from context size and the total run's usage budget. |
| Cookbook | Hardware-aware model discovery, download, serving, dependencies, and server management. | Build **Model Manager**, a model lifecycle workspace. This is a different workflow from installing Skills. |
| Library | Chats, Documents, Research, and Archive; the inspected Archive view contains archived sessions. | Build a durable information workspace with Sessions, Knowledge, Documents, Research, Media, and Archive, preserving named knowledge-library semantics. |
| Gallery | Media inventory, albums, tagging, saved edits, and a browser image editor. | Adopt artifact/media management inside Library → Media. A standalone Gallery and canvas/layer editing are outside the current scope. |
| Writing style | Odysseus scopes this to email replies and can extract it from sent emails. | Defer email-specific controls until Klaude has an email workflow. Do not apply that text to coding-agent instructions automatically. |

One implementation pattern should not be copied: the inspected Odysseus
**Clear offline** handler can optimistically remove rows and report a removed
count while swallowing delete failures. Klaude should acknowledge actual writes
and report partial failures. A transient offline result must not automatically
delete a configured endpoint.

## 3. Review of the requested settings

These tables describe observed Odysseus controls. Defaults below come from
backend settings when available, not screenshots or placeholder text.

### 3.1 Add Models

| Section/control | Input or action | Purpose |
| --- | --- | --- |
| Add Local Models: type | LLM / Image choice | Describes the service being connected. |
| Endpoint | URL editor | Connects an existing Ollama or compatible model server, including a LAN server. |
| Optional API key | Masked password input, initially tucked away | Supports protected local services. |
| Test | Cancellable connection check | Checks the draft connection before adding it. |
| Add | Save endpoint | Registers the service for later model selection. |
| Add API Models: provider | Provider preset / custom URL | Prefills provider-specific connection details; the preset list includes OpenAI, Anthropic, DeepSeek, OpenRouter, Gemini, and others. |
| Endpoint | Editable provider URL | Allows the selected service's API base URL. |
| API key | Masked password input | Supplies that endpoint's authentication. |
| Proxy / API mode | Browser-oriented connection mode | Chooses server proxy versus browser-direct access; not a necessary CLI control. |
| Test / Add | Check draft / save connection | Separates connection validation from persistence. |

Additional local-menu actions include network scanning and Ollama setup.
Those are optional discovery/installation workflows, not prerequisites for
connecting a URL. Klaude's first version should support explicit URLs.

### 3.2 Added Models

| Control or information | Purpose |
| --- | --- |
| Local / cloud grouping | Separates the configured service kinds. |
| Endpoint name, URL, status, enabled/total model count | Summarizes a connection without opening it. |
| Expand/manage models | Shows the service's model inventory and individual visibility/enabled choices. |
| Enable / Disable endpoint | Controls whether its models are selectable. |
| Delete endpoint | Removes configuration; distinct from deleting downloaded model files. |
| Probe | Re-tests connections and refreshes inventory. |
| Clear offline | Removes offline connection records after confirmation. |
| Per-model pin/hide and inventory refresh settings | Manages the selectable catalog and discovery behavior. |

Endpoint enabled state, connection health, and individual model visibility are
separate concepts. A model listed by a server has not necessarily demonstrated
working tool calls, vision, or acceptable coding performance.

### 3.3 AI Defaults

| Role/control | Observed behavior/default | Dependency |
| --- | --- | --- |
| Default Chat endpoint + model | Used when creating a chat; selections reflect the saved configuration. | Connected model inventory. |
| Utility endpoint + model | Unset means use the chat model. | Compaction, naming, cleanup, and other secondary AI consumers. |
| Utility fallbacks | Ordered endpoint/model choices. | Explicit role fallback handling. |
| Vision enabled | Backend default on. | Image analysis/vision-capable model pipeline. |
| Vision model | Auto-detect or explicit model. | Capability-aware model selection. |
| Vision fallbacks | Ordered alternatives. | Vision requests and fallback policy. |
| Research endpoint + model | Same as chat when unset. | Deep Research runtime. |
| Research runtime summary | Displays report tokens, extraction timeout/concurrency, and run timeout; refers users to Search. | Shared research settings. |
| Image generation enabled | Backend default off. | Image generation runtime. |
| Image model | Auto-detect or explicit model. | Image-service capability inventory. |
| Image quality | Low / Medium / High; medium default. | Provider/model-specific quality support. |
| Email writing style | Multiline text, Save, extract from 15 sent emails. | Email integration and email-specific prompt construction. |

The source also contains speech controls: TTS enable/provider/model/voice/speed
and Preview, plus backend STT settings. They are outside the requested first
settings scope and should be separately designed if speech is requested.

### 3.4 Search

| Control | Observed behavior/default |
| --- | --- |
| Provider | SearXNG, DuckDuckGo, Brave Search, Google PSE, Tavily, Serper.dev, Disabled. Backend default is SearXNG, not the screenshot's selected Tavily. |
| Results per query | 3 / 5 / 10 / 20 / Custom; default 5; custom input 1–100. |
| Service URL | Conditional SearXNG/custom service URL. |
| API key | Masked, conditional on provider. |
| Google PSE engine ID | Additional `cx` input; separate from the API key. |
| Test | Provider check and feedback. |
| Fallbacks | Ordered list with add/remove/reorder; backend default includes DuckDuckGo. |
| Current configuration summary | Provider and result count; credential availability needs separate indication. |
| Research search provider | Same as web search or explicit provider. |
| Research max report tokens | Backend default 16,384. The HTML placeholder says 8,192, so the placeholder is not authoritative. |
| Extraction timeout | Backend default 90 seconds. |
| Extraction parallelism | Backend default 3; engine bounds this to 1–12. |
| Run timeout | Backend default 1,800 seconds; upstream also supports 0 for unlimited. |

The backend additionally supports SafeSearch and separate planning/query
timeouts. The reviewed main form does not expose every backend setting.

Klaude's existing Google search adapter is not Google PSE. PSE and Serper need
their own adapters and credentials if added; relabeling an existing adapter
would not implement them.

### 3.5 Agent Tools

| Control | Observed behavior/default |
| --- | --- |
| Tool call limit | Numeric text input; 0 means unlimited upstream. |
| Max steps per message | Default 20; upstream range 1–200. |
| Summary | Reflects the configured step and call limits. |
| Built-in tool groups | Expandable registry-derived categories with enabled/total counts. |
| Individual/group toggles | Enable or disable tools made available to the model. |

The supplied Code/Search/Documents/Media/Knowledge/Multi-Agent/Sessions/System/
Other counts describe Odysseus's registry. Klaude must show its own registered
tools and counts. Availability does not imply permission to execute a tool.

## 4. Review of the four feature workspaces

### 4.1 Model Manager: models from discovery to serving

Use **Model Manager** as the Klaude feature name. Odysseus calls this feature Cookbook.

The inspected tabs are **Scan/Download, Serve, Dependencies, Settings**.

| Workflow | Important fields and actions |
| --- | --- |
| Scan/Download | Server selector, model query, Standard/Vision/Image type, engine/quantization/context filters, hardware selection/manual overrides, sort, download artifact selection, download progress/cancel. |
| Hardware fit | GPU pool/device count, per-device VRAM, RAM, backend, estimated fit/context; sorting includes latest, fit, score, VRAM, speed, parameters, and context. These estimates are not benchmarks of tool reliability. |
| Serve | Server, cached-model filter/sort/refresh, model file, engine, environment, port, GPU selection, context, launch presets; running process status/logs/stop/adopt actions. |
| Dependencies | Inspect/install/rebuild engine dependencies on the selected server. |
| Settings | Masked Hugging Face token; local/SSH servers; server name/host/SSH port, model directories, connectivity/key setup, default-server selection. |

Serve expands engine-specific advanced inputs rather than displaying them all
in one generic form:

- vLLM/SGLang: dtype, tensor parallelism, maximum concurrent sequences, GPU
  memory fraction, tool/reasoning parsers, caching, graph options, and extra
  environment/arguments. vLLM also exposes served name/model path, KV cache,
  attention/block size, optional swap, LoRA, expert parallelism, and speculation.
- llama.cpp: CPU/GPU/unified inference, GGUF artifact, GPU placement/split,
  main GPU, KV cache precision, CPU MoE/offload, fit, batch/microbatch/slots,
  flash attention, vision projection, mmap/warmup, and speculative options.
- Image engines: precision, device placement, steps, guidance, dimensions,
  negative prompt, model/style/LoRA options, and offload/slicing controls.
- Cross-engine switches include remote-code trust where applicable. These are
  executable model/server decisions, not harmless appearance preferences.

Klaude already has Hugging Face discovery and hardware/runtime information.
It does not have this complete download/process/SSH/dependency manager. Initial
support should target Ubuntu and the requested Ollama, llama.cpp, and vLLM
services; inspected upstream engines do not imply a commitment to add every
engine or another operating system.

### 4.2 Deep Research: a managed research job

The workflow is query → planning → search/read/reflect rounds → sourced report.
The new-job form contains:

- A multiline research question.
- Collapsible advanced choices: Rounds Auto or 1–20; Format Auto, Product,
  Compare, How-to, or Fact-check; search provider; endpoint; model.
- Queue and Start actions.
- Job cards with progress, sources, cancellation and result actions.
- Saved results reachable through Library → Research.

Settings supply defaults; per-job overrides do not silently rewrite them.
Auto rounds must still respect overall budgets. Web extraction concurrency and
model-request concurrency are separate limits, especially on a small GPU.

Klaude already supplies bounded research/retrieval state, fetch safety, source
identities, and research receipts. Receipts retain metadata rather than complete
replayable evidence. A job/report store and resumable job lifecycle are additional
work. Extend the canonical runtime with a research profile; do not reproduce
Odysseus's duplicate legacy/compatibility research handlers.

### 4.3 Odysseus Gallery reference and Klaude's Media scope

The inspected Odysseus navigation is **Photos, Albums, Edit, Settings**. The table
describes upstream features for reference, not Klaude's implementation scope.

| View | Fields/actions |
| --- | --- |
| Photos | Search photos/tags, tag filters, source/model filter, album/favorite filters, random/newest/oldest sort, pagination, selection and bulk operations. |
| Import | Upload/drop media or folders into the media library/albums. |
| Photo detail | Name, tags, album, favorite, preview and file/EXIF metadata; edit/download/delete actions. |
| Albums | Search, create/manage albums, import, select/bulk actions. |
| Edit | Image chooser, templates, saved projects, visual editing/layers and optional AI generation/editing/enhancement operations. |
| Settings | AI-tagging status and progress, Start AI tag, Cancel, Clear AI tags, link to Vision defaults. User-created tags are retained. |

Klaude's initial implementation is **Library → Media**:

- Screenshots associated with project, session, or task work.
- Uploaded/imported images and generated images from supported workflows.
- A searchable list with artifact-type/source filters and useful chronological
  sorting, followed by detail and best-effort previews.
- Metadata: name, type, size, dimensions, creation/import time, origin, and known
  session/task/model associations. Unknown provenance remains unknown.
- Manual tags, open externally, and export actions.

Basic Media storage, import, metadata, tags, preview and export do not depend on
a vision or image-generation model. Capture available provenance when an artifact
is saved; storing it does not add it to model context or a knowledge index.
Terminal image protocols can enhance previews, with file-path/export fallbacks
on headless or unsupported terminals.

Vision and generation can later consume or produce these artifacts. Optional AI
tagging follows a working vision pipeline, remains an explicit action, and keeps
generated tags separate from manual tags. Photos/albums/favorites navigation,
canvas/layers and AI editing are not part of the initial coding-artifact workflow.

Media can become a separate Gallery only if substantial image workflows justify
that product decision. This is a possible future direction, not a delivery
milestone or a commitment to build a desktop image editor.

### 4.4 Library: the durable information workspace

Odysseus's inspected Library has these views:

| Tab | Purpose and controls |
| --- | --- |
| Chats | Open/resume sessions; search, folder organization, recent/oldest/most-messages/A–Z sort, select, archive/delete; optional AI Tidy. |
| Documents | Browse/edit/import/create documents; search, language filter, recent/oldest/most-edits/A–Z sort, disk rescan, selection and export/delete actions. |
| Research | Browse saved research reports and open/discuss/export results. |
| Archive | Browse archived sessions; search, sort, restore/delete. |

Use this exact hierarchy for Klaude:

```text
Library
  Sessions
  Knowledge
  Documents
  Research
  Media
  Archive
```

| Klaude view | Purpose |
| --- | --- |
| Sessions | Durable conversations, resume, search, organization and archive actions. |
| Knowledge | Existing named knowledge libraries, learned sources, querying and explicit indexing/refresh management. |
| Documents | Stored/imported documents with search, metadata and export; learning into a knowledge library is a separate action. |
| Research | Durable reports, sources and job associations; view/discuss/export with explicit learning when supported. |
| Media | Screenshots, uploaded/generated images, previews, metadata, tags, external open and export. |
| Archive | Archived supported records with content retained, searchable history and explicit restore/delete. Start with sessions and add artifact types with their lifecycle support. |

The **Knowledge** view contains Klaude's existing named **knowledge libraries**.
Keep `klaude libraries`, `klaude query`, library identifiers, storage APIs, and
`collection` compatibility. Library is a navigation workspace over distinct
stores; it does not redefine a knowledge library or make every record retrievable
by the AI. Use action labels such as Import document, Learn into knowledge library,
Archive session, and Delete artifact to make their effects clear.

### Durable-information rules

- **Stored ≠ indexed:** retaining an artifact does not automatically populate a
  knowledge library's vector or full-text index or grant new model access to its
  content. Existing session/inventory search indexes support browsing; they are
  separate from knowledge indexing and learning. Existing conversation history,
  resume and configured Memory recall retain their own behavior and controls.
- **Imported ≠ learned:** Library import makes an artifact available there.
  Learning/indexing into a named knowledge library is an explicit separate action.
  Import a managed copy or retain an explicitly described file reference without
  mutating the original project file.
- **Archived ≠ deleted:** archive changes normal-list visibility while retaining
  content and a restore action. It does not erase stored content or silently
  remove learned/indexed copies. Permanent deletion is a separate confirmed
  operation with its affected records and index implications stated.

Maintain independent storage, indexing and archive state, with type/origin
information and IDs tied to the appropriate store. Defer AI Tidy until it can
present a reviewable proposal and apply selected changes; a utility model cannot
independently delete durable information.

## 5. Proposed navigation and migration

### Settings hierarchy

```text
Settings
  APPEARANCE
    Theme · Input Field · Divider · Spinner
  MODELS & AI
    Models
      Added Models
      Add Models
        Add Local Models
        Add API Models
      Choose model for this session
    AI Defaults
    Search
      Web Search
      URL Fetch
      Deep Research defaults
  AGENT
    Agent Tools
      Execution
      Built-in Tools
      Activity Updates
    MCPs · Skills · Memory · Library · Permissions
  ADVANCED
    Runtime
```

Keep **Add Models** and **Added Models** as real pages with the requested names;
group them under Models rather than adding multiple competing model entries to
the Settings home. Manage/Added comes first, consistent with MCPs and Skills.
The Models summary shows connected/enabled endpoint counts and the default
chat model. Add Models offers two entry actions, so only one form is edited at
a time. Added Models leads with its inventory controls and endpoint list.

Model Manager, Deep Research, and Library are feature workspaces. Library is also
reachable directly below Memory in Settings, as requested on 2026-10-15;
`/settings library` opens the same workspace and Back returns to its Settings
row. Direct `/library` entry closes to chat. Library contains Sessions,
Knowledge, Documents, Research, Media, and Archive in that order. Media is a
Library view, not a separate feature-launcher entry. Configuration links open
the relevant Settings page and return to the caller. New command entry points,
if introduced, must be implemented in the canonical command registry; this
document does not advertise nonexistent slash commands.

### Where current Klaude controls move

| Current location | Proposed owner | Compatibility |
| --- | --- | --- |
| Models session picker / `/model` | Models → Choose model for this session | Preserve the source/provider/model/mode/effort flow and pending-selection semantics. |
| Provider model API credentials | Add/Added Models → endpoint authentication | Reuse private credential storage; maintain existing native providers and Codex account authentication. |
| Providers web-search credentials | Search → provider detail | One editor and one persistence owner per credential. |
| Providers URL-fetch credentials | Search → URL Fetch → provider detail | Keep fetch availability and transport rules distinct. |
| Providers Hugging Face token | Model Manager → Discover → Hugging Face credentials | S5a links to the existing credential owner with Back to Discover; keep a single store. |
| Tools web-provider toggles | Search → Providers | Preserve enabled state and existing routing order. |
| Tools web result validation | Search → Web Search → Advanced | Preserve current behavior and explain that discovery leads are not fetched evidence. |
| Tools knowledge availability/validation | Agent Tools → Knowledge | Link to Library → Knowledge; keep the existing field semantics. |
| Tools other availability toggles | Agent Tools → registry-derived groups | No duplicate switch in two pages; context-specific pages link to the owner. |
| Tools Activity Updates | Agent Tools → Activity Updates | Retain existing default and event-driven behavior. |
| Runtime turn limit/subagent workers | Agent Tools → Execution | Preserve bounded defaults and read-only child constraints. |
| Runtime device/threads/context/calibration | Runtime | Show which machine/endpoint a value affects. |
| MCPs, Skills, Memory, Permissions | Existing pages | Retain their navigation, trust, and persistence behavior. |

Keep `/settings models`, `/settings providers`, `/settings tools`, and
`/settings runtime` working. Old Providers/Tools routes become compatible
landing pages with links to the new owners where necessary. Update all help,
category aliases, completion, and AGENTS guidance in the same implementation
change. Do not remove a credentials editor before its replacement works.

## 6. Detailed Klaude page contracts

### 6.1 Shared interaction and layout

1. Reuse `PanelPage`, typed rows/actions, stable IDs, and retained `PanelState`.
   Keep a fixed breadcrumb/header and help/status footer around the scrolling
   body. Leave completed chat in ordinary terminal scrollback.
2. Place Filter, Reload/Refresh, Probe/Test, Sort, and page-level actions above
   the inventory. Place column headings immediately above their data rows.
   Forms and actions never appear under an inventory's column headers.
3. Use available panel width: align compact values; wrap descriptions and URLs
   into the detail area. At narrow widths use stacked rows instead of squeezed
   multi-column tables. Avoid rendering a full endpoint URL on every model row.
4. Enter opens a detail/editor or applies a choice as indicated. Space toggles
   only toggle rows. Escape clears local filtering, then follows the explicit
   Back/Cancel action. Restore the caller's focus/filter/viewport.
5. `/` filters displayed rows locally. **Search query** explicitly performs a
   catalog/provider search. Query editors and masked credentials remain private
   settings inputs rather than chat messages or shared session drafts.
6. Use muted/normal text for checking, current, loading and informational states;
   green for acknowledged saved/success states, yellow for warnings/partial
   results/unconfirmed saves, red for errors. Retain readable text without color.
7. Network, discovery, hardware and storage jobs are owned, bounded background
   jobs with cancellation, scoped request IDs, and stale-result rejection.
   Key handlers/rendering do not perform network or blocking database work.
8. Edits use authoritative live snapshots and the existing ordered persistence
   writer. Failed saves retain the chosen live intent with unconfirmed feedback.
   Late acknowledgements cannot replace newer choices.
9. Large inventories use bounded pagination; detail loads only when opened.
   Preserve real cache ages and distinguish Loading, Unavailable, empty, stale,
   authentication failure, and partial success. Make long errors expandable.
10. Reset is scoped and has a separate blank row above footer controls. Endpoint
    removal and destructive data actions use a confirmation with Back/Cancel
    focused. Confirmation names the affected records and default bindings.

The existing Reset appearance settings action retains its exact Theme, Input
Field, Divider, and Spinner scope. It does not reset connections, credentials,
AI defaults, tools, or other new pages.

An example of the intended Added Models hierarchy:

```text
Settings › Models › Added Models

  Filter                All
  Reload                Refresh saved endpoint list
  Probe                 Test enabled endpoints
  Clear offline         Review unavailable endpoints

  ENDPOINT              STATUS          MODELS
  Office Ollama         Reachable       20 enabled / 20 listed
  Laptop llama.cpp      Not tested       1 enabled / 1 listed

  Add Models

  ← BACK
```

This is a structural wireframe, not a screenshot or a claim that those servers
or model counts are currently available.

### 6.2 Add Models form and connection testing

| Field/action | Klaude contract |
| --- | --- |
| Name | Human-readable label; stable endpoint ID is separate. Suggest a host/provider label without requiring one. |
| Local server type | Ollama native / OpenAI-compatible (llama.cpp, vLLM, other). Server type determines API construction, not whether the address is loopback. |
| API provider | Existing native OpenAI API, Gemini API, OpenRouter; add DeepSeek and Anthropic with appropriate adapters; Custom compatible endpoint. Only implemented adapters are selectable. Codex account connection retains its separate account flow. |
| Endpoint URL | Trim/validate, show the normalized API address, reject embedded credentials/control text. Permit explicit loopback/LAN model servers; cloud presets use HTTPS. Normalize known Ollama root, `/api`, `/v1` forms according to the selected adapter; preserve unknown proxy base paths. |
| Authentication | None / API key / supported account flow. Masked replacement editor and configured/not-configured state. Native Codex account login remains distinct from API keys. |
| Service capabilities | Initial LLM connection; image-specific connection appears when an image adapter is available. Do not accept a nonfunctional image configuration as usable. |
| Test connection | Bounded cancellable health/catalog check against this draft; no full workspace/session data and no chat generation. Show URL used, auth result, model count, elapsed time, and precise failure. |
| Optional test generation/tools | Separate explicit action on a selected model using a tiny synthetic prompt; label that it invokes the model. Mark observed capabilities with the test type/time. |
| Add | Persist endpoint and secret reference atomically as far as the storage contract allows. A successful draft test does not itself save settings. Offer Add untested explicitly if discovery is unavailable. |
| Cancel | Discard unsaved draft and cancel owned checks; leave installed endpoints unchanged. |

Do not append `/v1` or `/api` twice. Editing the URL or authentication invalidates
the previous test result. Bind credentials to the intended connection; a URL
change must not silently send the old service's secret to another host. Do not
forward model-server credentials through redirects to another origin.

Models listed by `/models` or native discovery have unknown tool/vision/image
capability unless there is trustworthy metadata or an explicit test. A manual
model-ID option is needed for services without catalog discovery. Adding a
connection does not pull models, install engines, scan the LAN, or change the
current chat model.

Codex account login does not require an API endpoint or API key. Retain its
existing broker-backed model/account page rather than forcing it into this form.

### 6.3 Added Models and model inventory

- The list shows name, Local/Cloud, enabled state, last check/result age, and
  enabled/listed model counts. URL and diagnostics belong in detail.
- Detail leads with Manage models, Test, Enabled, Authentication, then Remove;
  connection metadata and advanced refresh controls follow.
- Manage models has Filter, Reload models, enabled/total count, then model rows.
  Use `(endpoint_id, model_id)` for identity so equal model IDs on two servers
  are distinct. Keep returned model IDs intact.
- Track enabled, pinned/hidden, discovered/missing and capability status
  independently. Missing catalog data does not erase saved per-model choices.
- Probe works from a snapshot with bounded concurrency and cancellation. First
  version probes enabled endpoints by default; checking disabled ones is explicit.
  Report per-endpoint successes/failures without invoking generation.
- Clear offline opens a review of failed endpoints and their actual error/age.
  User selects records to remove; authentication errors are labeled separately
  from network unreachability. Show the acknowledged removed count and failures.
- Removing/disabling an endpoint shows affected defaults. Offer an explicit
  replacement or unset choice; never silently choose a different provider.
- A running turn retains its accepted immutable runtime snapshot. Changes
  affect new requests; close transports after their owners finish/cancel.

### 6.4 AI Defaults with explicit consumers

| Setting | Proposed default and behavior |
| --- | --- |
| Default Chat | Migrate existing effective startup choice. Endpoint then model selectors; used for a new session, not retroactively for the open one. |
| Utility | Same as chat; optional explicit endpoint/model and ordered fallbacks. Display the resolved model and its purpose. |
| Utility consumers | Initially only clearly identified, separately bounded optional naming/summary work where a model is useful. Retain deterministic compaction first and avoid an extra AI call for simple requests. Add other consumers only with observed value. |
| Vision | Auto-detect from configured, enabled, capable endpoints or explicit choice; show Unavailable when no supported image input pipeline/model exists. Provide an enable switch when the pipeline is implemented. |
| Research | Same as chat, resolved when the job is accepted; explicit endpoint/model override and a link to Search → Deep Research defaults. |
| Image generation | Off by default; capable model/service selector and only quality options supported by that adapter. Add its switch with the functioning generation pipeline. |
| Embedding model | Preserve Klaude's existing embedding configuration through Library → Knowledge → Advanced. Changing embedding dimensions/model needs a deliberate index migration/rebuild; a utility fallback cannot silently replace it. |
| Email writing style | Future email-specific integration; not a global system-prompt editor. |

All role selections display inheritance as **Same as chat → endpoint/model**,
and distinguish a saved default from the current session's model. Selectors use
cached inventories and background refresh. Preserve pending session model
changes and mode/effort behavior.

Fallbacks are ordered explicit endpoint/model pairs with Add, Move up/down,
Remove, and enabled/configured status. Deduplicate entries, reject cycles, bound
attempts, and share aggregate usage/cancellation accounting. No default switch
from local processing to a paid/cloud service. Show any accepted fallback in the
public activity/final result. Define eligible failures per role; a model giving
an unsatisfactory answer is not automatically a transport failure.

### 6.5 Search and Deep Research defaults

- Web Search begins with enabled state, provider/routing choice, provider detail,
  results count, Test, fallback order, and a concise usable-configuration summary.
- Keep Klaude's relevance-based **Auto** routing as the migrated default. A
  pinned provider and explicit fallbacks are an alternative, not a hidden
  replacement for the current router. Preserve policy for explicit provider
  fallback, quota/unavailability, and low relevance.
- Provider detail owns enabled state, masked key, and only relevant fields:
  SearXNG URL, Google PSE engine ID, supported locale/filter settings, etc.
  Preserve existing adapters; add PSE/Serper independently if desired.
- Results presets can match 3/5/10/20/Custom, but inherit the current effective
  value on migration. A large result count does not enlarge model context or
  bypass discovery/fetch/relevance budgets.
- Fallback ordering operates only on enabled, eligible providers. Avoid repeating
  the primary provider, duplicates, loops, and unbounded retries. Test reports
  the actual provider used; configured versus usable must be clear.
- URL Fetch owns its availability, provider configuration, and safe transport
  behavior. Search-provider selection does not implicitly select a fetch engine.
- Advanced exposes the existing result-validation preference. Disabling it
  changes candidate validation, not provenance, permission or fetch safety.

Proposed research defaults:

| Field | Contract |
| --- | --- |
| Search provider | Same as web search or an explicitly configured provider. |
| Max report tokens | Auto using the selected runtime's bounded output setting; explicit custom override constrained by model/provider limits. The Odysseus 16,384 default is not imposed on small local models. |
| Extraction timeout | Initial proposed 90 seconds; validated positive duration with units. |
| Extraction parallelism | Initial proposed 3 network extraction workers, bounded; separate model-call lane defaults to 1 local request and existing cloud policy. |
| Run timeout | Initial proposed 30 minutes with actual cancellation/deadline handling; distinguish this from the current boundary-checked turn governor. |
| Advanced budgets | Total calls/tokens, search/read/round limits, planning/query deadlines; show inherited effective values rather than unrelated magic defaults. |

A settings page is not a request to launch research. Keep report tokens, input
context capacity, total token consumption, and elapsed deadlines separately
labeled. Auto never means unlimited.

### 6.6 Agent Tools

| Control | Contract |
| --- | --- |
| Tool call limit | Named Auto / Custom modes; migrate numeric 0 to Auto. Show Auto's effective ceiling, e.g. 40 for 20 steps. Custom initially retains 1–256. If Unlimited is exposed, implement a separate explicit mode that removes only this cap; keep finite step/time and non-progress bounds. |
| Max steps per message | Retain current default 20 and 1–64 supported range initially. Explain a step as a model iteration, not one shell command. |
| Total token budget | Advanced existing setting with its actual semantics; show unknown usage honestly. Do not relabel existing unlimited total-token configuration as Auto. |
| Subagent workers | Auto or 1–4; retain existing provider-aware local/cloud concurrency and aggregate budgets. |
| Built-in Tools | Registered groups, enabled/total counts, per-tool switches; expandable detail with purpose and permission-policy link. |
| Group toggle | Applies to registered tools in that group without changing permission grants; accurately represent mixed state. |
| Activity Updates | Existing toggle; default retained. |

Availability filtering must apply to every schema, explicit routing, text-form
tool recovery, and delegated child intersection. Disabled tools do not return
because a prompt names them. Session control/slash commands and host bookkeeping
are not model-callable tools just because they exist in the application.

Show MCP tools and Skills as linked managed capabilities rather than duplicating
their inventories. Preserve read-only delegation roles and ask/allow/deny gates.
A tool being enabled never bypasses workspace boundaries or grants permission.

## 7. Backend work and implementation boundaries

### Shared model connection architecture

- Add a versioned endpoint registry with stable IDs, adapter/provider type,
  normalized base URL where the transport uses one, enabled state, credential
  reference, refresh preferences, model choices, and bounded health/capability
  metadata. Account-backed connections retain their broker/auth identity without
  a fabricated HTTP endpoint.
- Keep secrets in the existing private credential mechanism. Registry,
  transcripts, model context, reports, cached diagnostics, and list output store
  references/status only. Preserve separate Codex account-token ownership.
- Scope catalog caches to endpoint identity/configuration revision and adapter;
  the current backend-only cache is insufficient for two Ollama services.
- Extend model references/session persistence to include endpoint identity.
  Migrate old `backend/model_id` references without losing resume compatibility.
- Preserve native Ollama options, OpenAI Responses continuation, OpenRouter
  recovery, Gemini native behavior, and Codex broker lifecycle. Add an explicit
  compatible chat adapter with correct streaming/tool-result/cancellation logic.
- Treat capabilities as observed/declared/unknown. Do not default an untested
  custom connection to verified tool or vision support.
- Loopback/LAN access is confined to explicitly configured model connections;
  it does not relax the public-URL restrictions of web-fetch tools.
- Migrate the single `ollama_url`, existing provider credentials, startup model,
  and embedding choice into equivalent records. Migration must be idempotent,
  field scoped, and preserve unrelated config and cross-client intent.
- Distinguish CLI overrides, persisted defaults, session choices, and accepted
  running-turn snapshots. Removing a connection must not corrupt old transcripts.

### Feature services

- Deep Research needs an owned job state machine: queued/running/cancelling/
  cancelled/failed/partial/completed, bounded checkpoints, runtime snapshot,
  explicit public progress, and durable report/source records.
- Saved receipts do not substitute for source content. Re-fetch required
  evidence on recovery, or identify a report as partial/stale. Keep search leads
  separate from verified fetched sources; never invent citations.
- Library initially projects existing session/knowledge stores with typed IDs.
  Documents, reports and Media share bounded artifact metadata where useful,
  while retaining their own content/provenance contracts. Storage/import never
  implies knowledge indexing or automatic model-context inclusion. Keep archive
  visibility, indexing and permanent deletion independent, with explicit restore
  and deletion effects. Retain active-worker/session compatibility.
- Model Manager needs owned download/process jobs, disk-space/progress/cancellation
  handling, cache metadata and backend adapters. Start with native Ollama
  inventory/pull/remove and already-installed engine integration. Arbitrary
  installer scripts, SSH key installation and remote dependency changes are
  separately scoped explicit actions.
- Register a served endpoint only after successful health verification. Stop
  only owned processes; adopting an existing process is explicit. Respect port
  conflicts and server/device-specific settings. Hardware detection failure
  yields Unavailable, not invented memory capacity or fit scores.
- Build launch commands from validated structured fields/argument lists rather
  than evaluating form text as shell code. Advanced engine options appear only
  when the supported engine/version can consume them.
- Library → Media requires managed artifact storage/import/export, metadata,
  manual tags, bounded image decoding and external-viewer handling. It works
  before vision/generation adapters exist. Later image workflows save outputs
  into this view and optional AI tagging retains manual tags. Cloud media
  transfers follow explicit role selection; neither import nor viewing starts
  a model request or silently selects another endpoint.

### UI organization

Introduce focused page/controller modules for model connections, defaults,
search, and agent tools. Reuse the shared panel state and owned workers. Keep
`main.py` as command/flow wiring rather than adding every form and lifecycle
handler to its already large chat/settings implementation. Do not create a
second preference writer, permission system, model loop, or secret store.

## 8. Delivery sequence and acceptance gates

Use the existing **S1–S6** settings phase IDs and add **S0** for the current
reliability gate. These IDs are independent of the numbered
[agent-orchestration phases](agent-orchestration-plan.md). Each slice below
needs its own working user flow and evidence before the next slice starts.
Planning does not mark a phase implemented or authorize a commit/push.
For phases with several slices, apply the relevant gate checks as each slice
finishes; all listed checks are required before the whole phase is complete.

| Phase | Feature group | Delivery order within the phase | Depends on |
| --- | --- | --- | --- |
| S0 | Reliability baseline | Current shutdown fix and regression verification | Existing release baseline |
| S1 | Model connections | Migration/identity → connection discovery/testing → compatible runtime | S0 |
| S2 | Models settings and AI Defaults | Add/Added pages → chat/utility defaults → provider expansion | S1 |
| S3 | Search and Agent Tools | S3a Search → S3b Agent Tools and settings reorganization | S2 |
| S4 | Library and Deep Research | S4a Library/storage → S4b research jobs, defaults and reports | S1–S3 |
| S5 | Model Manager | S5a Ollama lifecycle → S5b managed engines → S5c dependencies/SSH | S1–S2; scheduled after S4 |
| S6 | Vision and image generation | S6a image analysis → S6b generation → S6c optional AI tags | S2 and S4a; managed engines use S5 |

### S0 — Finish the reliability baseline

Status: **complete**. Verified checkpoint: `02fcf48`; full CI passed on 2026-10-06.

- [x] Verify the current TUI shutdown fix locally: a late redraw must
  not change the reported outcome of an already committed memory/session write.
- [x] Require successful Python 3.11–3.13 CI for the checkpoint containing the
  fix, including lint, production types and the existing packaging gate.
- [x] Verify existing plan approval, cancellation, malformed-call/path recovery,
  shell failure tracking, workspace-cache invalidation, dirty-worktree safety,
  validation reruns and exit-code behavior in the local suite; retain these gates
  throughout this roadmap.

Current evidence: the local fix and deterministic regression passed `make check`
with 2,453 passed, 19 skipped, Ruff passing and mypy passing on 83 source files.
Fresh five-wheel installation/import/CLI smoke also passed. The
[S0 validation record](s0-reliability-validation.md) maps the regression coverage
and records the reproduced race and completed CI gate.
The [checkpoint CI](https://github.com/Chansovisoth/klaude-code/actions/runs/37426174871)
passed for `02fcf48323ed857e8f289b5a8679d1ea70b3b0ef`: each Python 3.11, 3.12
and 3.13 job reported 2,453 passed and 19 skipped; lint/types and packaging passed.
The fix was committed and pushed to main with explicit approval. The published
alpha.4 checkpoint remains the earlier release snapshot.

**Gate:** the checkpoint containing the fix passes the full CI matrix; accurately
record any unavailable checks. The separate small-model CSV/GPU evaluation keeps
its existing status and completion gates in the agent-orchestration plan.

### S1 — Model connection foundation

- [x] Store multiple connections with stable endpoint IDs, adapter type,
  normalized URL, enabled state and private credential references.
- [x] Migrate the current Ollama URL, startup model and native-provider choices;
  retain session resume and field-scoped preferences.
- [x] Identify/cache a model by endpoint plus model ID; keep same-named models
  on different servers distinct.
- [x] Add owned, cancellable discovery/health checks with precise authentication,
  network, missing-catalog and malformed-response feedback.
- [x] Add the compatible runtime needed for explicitly configured llama.cpp,
  vLLM or other compatible servers; retain native provider continuation/tools.

**Gate:** use the existing Ollama connection and a second manually entered local
endpoint through real chat and tool calls; verify identity, restart/resume,
streaming, cancellation and malformed-call recovery. Clearly distinguish mocked
protocol coverage from a server that was actually available and tested.

**Completed 2026-10-13.** Native Ollama and its separately registered compatible
endpoint passed real one-shot tools, interactive switching, cancellation and
restart/resume checks. Full tests/static checks and fresh wheel smoke passed.
See [S1 validation and limits](s1-model-connections-validation.md); live
llama.cpp/vLLM certification and S2 forms are separate work.

### S2 — Models pages and AI Defaults

**S2a: Connect and manage models**

- [x] Models landing page with Added Models, Add Models and session selection.
- [x] Add Local Models and Add API Models forms: name, adapter/provider,
  endpoint, masked authentication, Test, Add and Cancel.
- [x] Added Models: probe, endpoint detail, enable/disable, reviewed removal and
  acknowledged outcomes; authentication errors stay distinct from offline state.
- [x] Per-endpoint model inventory: Filter, Reload, enabled/total count,
  per-model visibility/pinning and observed/unknown capability metadata.

**First working slice, 2026-10-13:** typed landing/add/detail pages, private
drafts and masked keys, catalog-only draft tests, acknowledged ordered Add,
read-only Added Models snapshots, per-endpoint catalog reload/filter and manual
model selection. Controls precede table headers; capabilities remain unknown
unless existing cache metadata supplies evidence. Cancel does not save a draft.
The current session and embedding choice remain unchanged by Add. See
[S2 connection UI validation](s2-model-settings-validation.md).

**Maintenance slice complete, 2026-10-13:** cancellable serial Probe of enabled
endpoints; durable scoped check status/age; endpoint enable/disable and reviewed
removal; Clear offline reviews only network/timeout failures and rejects changed
health. Affected startup choices require explicit replacement/unset. Running
turns retain their model; new prompts reject removed/disabled endpoints/models.
An unset startup opens Models without selecting a fallback. Per-model enabled,
hidden and pinned fields merge independently, survive missing catalogs, and
affect session pickers. Filters are endpoint scoped; fresh reviews clear stale
search and initially focus Cancel. Real TUI evidence and regression gates are
in the [S2 validation record](s2-model-settings-validation.md#s2a-maintenance-follow-up).

**AI Defaults slice complete, 2026-10-13:** Default Chat is independent of the
active session; Utility inherits the session model or uses an explicit endpoint,
with up to three ordered fallbacks and a visible bounded output budget. Optional
AI recap and title consumers use public dialogue only, no tools, owned
cancellation and finite generation deadlines. Ordinary chat and deterministic
compaction add no Utility calls. Removal reviews include affected roles.
Real native/compatible CLI sessions, fallback/cancellation/restart checks and
regressions are recorded in the [S2b validation record](s2b-ai-defaults-validation.md).

**Phase numbering:** S4 is Library, then Deep Research; Model Manager is S5.
S4a, S4b, S5a and S5b are complete locally. S5c's local dependency/build and SSH
settings/diagnostics, owned remote CPU serving and reviewed existing-public-key/
host-trust, CUDA build and offline NVIDIA vLLM wheel slices are implemented;
retained setup removal and remote llama.cpp GPU profiles are also implemented;
remote NVIDIA vLLM serving and reviewed remote adoption are implemented and
locally validated. S6a1/S6a2/S6a3a/S6a3b/S6a3c/S6a3d/S6a3e/S6a3f native/HTTP analysis and
chat images are implemented for their scopes; paid-provider generation evidence,
native CPU/CUDA generation, image jobs and optional tagging are implemented and
locally validated. Remaining paid-provider certification requires account access.

**S2b: Defaults with functioning consumers**

- [x] Default Chat endpoint/model for new sessions; preserve the current
  session's independent model choice and pending changes during a running turn.
- [x] Utility endpoint/model, Same as chat inheritance and ordered explicit
  fallbacks, paired with bounded optional naming/summary consumers.
- [x] Display effective selections and fallback use. Keep deterministic
  compaction and avoid extra model calls for simple requests.
- [x] Add Research endpoint/model controls with its functioning S4b consumer.
- [x] Add Vision and Image generation controls with their S6 consumers;
  S6a supplies analysis and S6b1 supplies the first local generation workflow.
  Actual native CPU/CUDA diffusion inference is validated under S6b.
  Preserve the existing embedding role and migration boundary.

**S2c: Additional cloud adapters**

- [x] Add DeepSeek as an explicit connection preset, with a dedicated reasoning
  continuation adapter, session/default/Utility consumers and local protocol
  validation. [Evidence and cloud limits](s2c-deepseek-validation.md).
- [x] Add native Anthropic with explicit endpoint settings, paginated catalogs,
  Messages/tool continuation, declared mode/effort controls and Utility consumers.
  [Local evidence and cloud limits](s2c-anthropic-validation.md).
  Existing OpenAI API, Gemini API, OpenRouter and Codex account paths remain available.
  Additional providers require their own implemented and validated adapters.

**Gate:** keyboard walkthroughs of draft test/add/cancel, multiple endpoints,
auth/offline states, removal, restart persistence and session/default differences;
verify that credentials stay bound to their intended service. Provider presets
become selectable only with an implemented, validated adapter.

### S3 — Search and Agent Tools

**S3a: Search**

- [x] Web Search: Auto/pinned provider, relevant provider fields and masked
  credentials, results per query, Test, enabled state and fallback ordering.
- [x] URL Fetch: its own provider configuration, credentials and availability.
- [x] Move existing web-provider controls to their single owning page; retain
  current routing/validation semantics and compatibility links.
- Deferred extension: add Google PSE/Serper or other new search adapters only as
  complete, separately tested slices with their actual credential fields.

**Web Search slice, 2026-10-13:** typed Search entry and provider/detail/result/
fallback pages, immediate intent and acknowledged non-secret saves, ordered
masked key writes, user-reviewed cancellable tests and compatibility links.
Real chat/ask tests found and fixed one-shot availability bypass, negated-code
repair routing and duplicated SearXNG expansion (24 → 3 HTTP requests for the
same five leads). [Evidence and remaining scope](s3a-web-search-validation.md).
**URL Fetch slice, 2026-10-13:** independent Local/Exa routing and cloud fallback,
Crawl4AI service/keys and separate provider availability, ordered private saves,
owned uncached diagnostics, read-only transport limits and compatibility links.
Real terminal/one-shot checks found and fixed the masked editor transition,
crowded validation errors and a search-prohibition rule that removed explicit
URL reads. Extraction responses and cache/failure reuse obey current limits.
[Evidence and remaining limits](s3a-url-fetch-validation.md).
Optional new provider adapters remain deferred complete slices.

**S3b: Agent Tools and navigation migration**

- [x] Execution: maximum steps, Auto/Custom tool-call limits, advanced token
  budget and provider-aware subagent worker limits. Migrate current zero to Auto;
  an Unlimited option requires separately implemented and verified semantics.
- [x] Registry-derived groups, enabled/total counts, individual/group toggles
  with mixed state, permission links and Activity Updates.
- [x] Link MCPs and Skills to their existing managed-capability pages; retain
  their search/manage navigation and the existing Memory/Permissions ownership.
- [x] Move only the relevant controls from Tools, Providers and Runtime; keep
  device/context/calibration in Runtime and update canonical help/aliases.
- [x] Apply the proposed Settings grouping and shared width, filtering,
  focus/Back, table-header and footer conventions across migrated pages.

**Execution slice, 2026-10-13:** Agent Tools home and typed Execution/Advanced
pages own steps, finite Auto/custom calls, reported-token cap/usage and workers.
Runtime retains hardware/context/calibration with a compatibility link. Old
execution preferences retain their keys and apply before both chat and ask.
Scoped ordered saves/resets preserve tools, permissions, hardware and live intent;
running turns use their captured step budget. A stopped batch receives one
skipped result per remaining call ID, and a budget-blocked required read fails
without an impossible retry. Its legacy tool-controls landing is now replaced
by the registry-derived Built-in Tools page. [Evidence](s3b-agent-execution-validation.md).

**Registry/navigation slice complete, 2026-10-13:** Built-in groups use the live
registry, omit MCP inventories and unregistered tools, and show enabled/total
counts. Group switches accurately show mixed state; tools support Space toggles
and Enter for purpose/availability/permission detail. MCPs/Skills links return
to their existing owners; Search/URL Fetch link to one availability owner.
Knowledge validation remains distinct from Search validation and permission grants.
Settings uses Appearance, Models & AI, Agent and Advanced; Provider credentials
remain under Advanced; Model Manager → Discover links to the same Hugging Face
credential owner with contextual Back navigation.
All built-in availability loads before chat/ask, and live disables are rechecked
in later schemas, capability snapshots and delegated child intersections.
[Interaction, protocol and regression evidence](s3b-agent-tools-validation.md).

**Gate:** rapid edits, failed saves and Back/filtering preserve authoritative
state; disabled tools stay absent on every execution path; current search routing,
permissions, read-only delegation and all existing entry routes keep working.

### S4 — Library, then Deep Research

**S4a: Library and durable artifacts**

- [x] Build Library navigation in this order: **Sessions, Knowledge,
  Documents, Research, Media, Archive**. Sessions/Knowledge/Documents/Media/Archive
  work; the subsequent S4b slice supplies Research jobs/reports.
- [x] Sessions: browse, full-store search, bounded pages/public previews and resume.
- [x] Knowledge: browse existing named libraries and search active/enabled indexed
  text without model calls, preserving existing IDs and compatibility commands.
- [x] Add TUI consumers for explicit learning, hybrid query and managed-source
  refresh, reusing existing service owners and CLI compatibility.
- [x] Prepare durable report/artifact storage for S4b.
- [x] Documents: import/store, metadata, filters, open and export; learning into
  a named knowledge library remains explicit.
- [x] Media: screenshots and uploaded/imported images, previews with terminal
  fallbacks, metadata, manual tags, open externally and export.
- [x] Archive: start with sessions, search/restore retained content, separate
  confirmed permanent deletion; extend to artifact types with supported lifecycle.
- [x] Maintain **Stored ≠ indexed; Imported ≠ learned; Archived ≠ deleted**
  for the implemented session/document/media stores.

**Foundation complete locally, 2026-10-13:** typed Library pages outside Settings,
read-only inventories/search, session lifecycle and cross-client guards passed
the real `TEST KLAUDE FEATURES LIBRARY` CLI/TUI run. Archive retains content and
configured recall; browsing adds no model/embedding/indexing work. A subsequent
Documents/Media slice adds managed imports, metadata/tags/filters/previews/export,
artifact archive/restore/delete and durable report storage. Explicit Knowledge
TUI actions were pending at that checkpoint and are supplied below.
[Artifact scope and validation](s4a-artifacts-validation.md).
[Scope, interaction and regression evidence](s4a-library-validation.md).

**Artifact slice validated locally, 2026-10-13:** real
`TEST KLAUDE FEATURES LIBRARY ARTIFACTS` CLI/TUI run passed with unchanged original
and knowledge-file hashes, zero generation requests and 40/70/120-column layouts.
Final checks: **2,797 passed, 19 skipped**, Ruff/mypy and five-wheel packaging passed.
The subsequent Knowledge slice supplies the remaining TUI actions; S4b had not
started at that artifact checkpoint.
[Knowledge interaction and validation evidence](s4a-knowledge-validation.md).

**S4a complete locally, 2026-10-13:** explicit learning, hybrid query and
managed-source refresh passed the real `TEST KLAUDE FEATURES KNOWLEDGE ACTIONS`
CLI/TUI run, including cancellation, fresh public-source replacement and resize
at 40/70/120 columns. Final gate: **2,823 passed, 19 skipped**, Ruff/mypy and
five-wheel packaging passed. No commit or push was performed in this slice.

**S4b: Deep Research**

- [x] Job form: question, format, bounded rounds, search provider, endpoint/model
  overrides, Queue and Start.
- [x] AI Defaults research role plus Search research defaults: max report
  tokens, extraction timeout/parallelism, run deadline and advanced budgets.
- [x] Owned jobs with public progress, sources, cancel, partial/error outcomes
  and bounded recovery/checkpoints using the canonical runtime.
- [x] Sourced reports saved into Library → Research, with view/discuss/export
  and explicit learning; re-fetch required evidence on recovery.

**S4b complete locally, 2026-10-13:** real bare CLI/TUI and one-shot research
walkthroughs cover reviewed queue/start, public-source extraction, citation
repair, atomic publication, cancellation/resume, report discussion/export and
explicit learning. Research defaults use bounded local values rather than the
earlier larger proposals: 2048 output, 8192 context, 2 rounds, 6 queries, 8 sources,
30-second extraction requests, 2 extraction workers and a 300-second run deadline.
There is no automatic model fallback or queue daemon. An actual qwen3.5:4b run
produced a supported partial report, not complete requested topic coverage.
[Scope, exact checks, real-model limits and final validation](s4b-deep-research-validation.md).

**Gate:** imports preserve originals and launch no indexing/model calls; archive
restores content; Media works without vision/generation. A real multi-step
research job produces supported citations, saves its report and handles
cancellation/recovery honestly, with bounded local-model work.

### S5 — Model Manager

**S5a: Local Ollama lifecycle**

- [x] Installed-model inventory, discovery/download, progress/cancel, hardware
  information and Hugging Face credential/settings ownership where relevant.
- [x] Native Ollama pull/remove and service health/status; distinguish removing
  a connection from explicitly deleting a downloaded model.

**S5a complete locally (2026-10-14):** typed Model Manager workspace and CLI,
reviewed endpoint-scoped lifecycle, bounded owned progress/cancellation and
existing Hugging Face credential ownership. The real CLI/TUI walkthrough passed;
actual Ollama cancellation, retry and QA-tag deletion preserved all 22 original
models and digests. Hardware measurements remain local and unknown where absent.
[Scope, validation, evidence and limits](s5a-model-manager-validation.md).

**S5b: Managed serving**

- [x] Integrate already-installed llama.cpp/vLLM, then owned launch/stop/logs,
  validated model/port/device/context fields and supported engine options.
- [x] Register served endpoints after a successful health check; explicitly
  adopt existing processes and stop only owned processes.

**S5b complete locally (2026-10-14):** typed launch/adoption reviews, installed
engine/device checks, bounded local model/resource fields, client-owned helpers,
health/listener-gated registration, retained status/logs and reviewed owned stop.
Real llama.cpp CPU serving and `klaude ask` passed; nine real TUI scenarios and
owner/helper crash regressions passed. All 22 existing Ollama digests were retained.
At that checkpoint GPU inference was unverified because the driver was unavailable;
vLLM is protocol-fixture validated, not live-inference validated. The real short
agent request needed about 191 seconds of CPU prefill for 5,708 prompt tokens.
[Exact evidence, regression gates and remaining limits](s5b-managed-serving-validation.md).

**S5c: Dependencies and remote servers**

- [x] Local dependency inspection and reviewed llama.cpp CPU build from a
  committed local snapshot, with owned compilation, logs, cancellation and
  verified handoff to Serve models.
- [x] Explicit local NVIDIA CUDA build and isolated vLLM wheel-install recipes,
  with compiler/target/platform/dependency/hash checks and owned cancellation.
- [x] Reviewed retained build/install removal and storage reclamation.
- [x] SSH definitions, strict connection testing, bounded resource/model-directory/
  process snapshots and a diagnostics default with an explicit consumer.
- [x] Owned SSH CPU llama.cpp serving, renewable remote lease, verified loopback
  endpoint/tunnel, confirmed/unconfirmed cleanup and reviewed stop/cancel.
- [x] Reviewed enrollment of existing Ed25519 public keys and independently
  verified host pinning, preserving existing trust files/key policies.
- [x] Owned remote llama.cpp GPU profiles with observed engine device mapping,
  stale-device rejection, explicit layer/device reviews and native CUDA inference.
- [x] Reviewed remote NVIDIA vLLM serving with environment-specific CUDA checks,
  stable GPU UUIDs, local safetensors bundle revisions and explicit resources.
- [x] Upstream remote vLLM GPU inference validated through actual CLI/TUI over
  loopback SSH on GTX 1650, with pinned SmolLM2-135M-Instruct and confirmed cleanup.
- [x] Reviewed remote adoption with exact process/model/listener identity,
  exclusive acknowledged takeover and witnessed-group cleanup. Observed PIDs
  alone do not authorize mutation.

**S5c first slice implemented locally (2026-10-14):** actual llama.cpp source
compilation at `b7ad48ebda2287c778fd826606d7b3b3570f60ab` passed in 294 seconds;
its separate CPU executable served qwen2.5-coder:3b and returned OK. The source
worktree and all 22 original Ollama digests were retained. Real TUI walkthroughs
cover review/cancel, build, bounded logs, serving-draft focus and compiler cleanup.
At this first-slice milestone, key enrollment, extra installer recipes and build
removal were unfinished; the follow-up slices below cover them. **S5c is not
complete as a whole**. [Evidence and boundaries](s5c-dependencies-validation.md).

**S5c SSH settings/diagnostics slice implemented locally (2026-10-14):** reviewed
private forms, revisioned owner-only definitions, explicit public-key/verified-host
checks, bounded resource/model/process snapshots and a working diagnostics
default. Actual OpenSSH CLI/TUI workflows passed, preserving dirty workspace,
remote original/key files and endpoint selections. Visual inspection caught and
fixed shared inventory row alignment. GPU measurements, physical LAN-host
validation, key enrollment and extra installers remain unfinished.
[Exact evidence and limits](s5c-ssh-validation.md).

**S5c owned remote CPU serving implemented locally (2026-10-14):** reviewed
server-scoped forms and additive serve CLI options, strict SSH/tunnel ownership,
remote heartbeats/owned cleanup, health/model/listener-gated endpoint publication,
private logs, Cancel loading and Back-focused scrolling reviews. Actual
qwen2.5-coder:3b generation over real loopback SSH returned OK; final run took
8.11 seconds, confirmed cleanup and preserved 22 original Ollama digests. Real
restart testing found and fixed TIME_WAIT port-probe behavior; CLI preflight
scope is now retained. Physical LAN, GPU/vLLM/adoption/key enrollment and extra
recipes remain uncertified/unfinished. [Evidence](s5c-remote-serving-validation.md).

**S5c reviewed key setup implemented locally (2026-10-14):** candidate Ed25519
fingerprint discovery, independently verified private host pins and reviewed
enrollment of one existing public key through current verified authentication.
Original trust/identity files and authorized-key prefixes/restrictions are
retained; stale definitions/files and revoked host keys are rejected. Real CLI/
TUI runs verified new-key authentication, Back-focused reviews, three widths,
stale remote policy handling and live cancellation with honest uncertain outcomes.
Key generation/password bootstrap, certificate/jump-host flows, remote GPU/vLLM
and additional recipes remain outside this slice. **S5c is still partial.**
[Evidence and remaining limits](s5c-ssh-key-setup-validation.md).

**S5c local engine recipes implemented (2026-10-14):** CUDA architecture/host
compiler controls, fixed-code compiler checks and separate NVIDIA vLLM environments
from complete trusted local wheels. Offline dependency/platform checks precede
copying; installation uses immutable hashes and no ambient credentials/indexes.
Real CLI/TUI runs cover rejection/recovery, Back-focused reviews, three widths,
offline fixture installation, engine-correct Serve handoff and cancellation.
Existing engines, models, source edits and defaults are retained. Setup verification
does not certify GPU inference/model fit. A real full-source CUDA build at target
75/GCC 12/eight explicit jobs completed in 769.31 seconds; its managed local GPU
server returned OK using qwen2.5-coder:3b, stopped cleanly and preserved 22 original
Ollama digests. Upstream vLLM inference was unverified at that checkpoint; the
remote-vLLM follow-up below now records actual GPU validation. Setup removal is
documented below; remote extensions remain unfinished. [Evidence](s5c-engine-recipes-validation.md).

**S5c reviewed setup removal implemented (2026-10-14):** exact ID/path/storage
reviews, Back/No defaults and shared CLI/TUI owned removal. Recheck filesystem
receipts, active workers/servers, configured/session/default model roles and
endpoint aliases. Serialize with server startup and unlink venv symlinks without
following targets. Preserve original sources/wheels, external weights, roles and
server history. Interrupted cleanup stays unservable and requires a fresh review;
restricted Linux process visibility is disclosed. Real CLI/TUI review/removal and
Ctrl+C partial-removal retry evidence: [validation](s5c-setup-removal-validation.md).

**Gate:** verify actual download cancellation, disk/port/engine failures,
unavailable hardware, owned-process cleanup, endpoint registration and explicit
file deletion for each supported slice. Configuration must not imply untested
hardware fit or tool reliability.

**S5c remote llama.cpp GPU profiles implemented (2026-10-14):** engine-reported
device mapping, CPU default, explicit layers/IDs, bounded metadata checks and
fresh device verification before loading. Reuse SSH lease/tunnel/health/cleanup
with no automatic model or CPU fallback. Real CUDA qwen2.5-coder:3b generation
over encrypted loopback SSH returned OK, offloaded 37/37 layers, stopped with a
confirmed receipt and retained 22 Ollama digests. TUI recovery, cancellation and
40/70/120-column reviews passed. [Evidence](s5c-remote-gpu-validation.md).
Physical LAN hosts, other backends and remote vLLM/adoption remain separate work.

**S5c reviewed remote NVIDIA vLLM serving implemented (2026-10-14):** reuse the
existing SSH supervisor/lease/tunnel/worker lifecycle, with an explicit engine
choice and reviewed local safetensors directory. Remote NVIDIA UUIDs and CUDA in
the selected environment authorize the GPU profile; stale bundle/environment
revisions and unavailable/incompatible hardware fail before model loading.
Precision/memory/eager controls remain user-visible and bounded. Readiness requires
an owned group listener, including frontend children; no remote installation,
model/default switch or CPU fallback is introduced. Real TUI reviews/recovery at
40/70/120 columns and multiprocess SSH fixtures passed. The initial upstream
install timed out; the follow-up completed verified offline installation and
real CLI/TUI CUDA inference. Cold-help and cleanup timing failures were corrected.
Full gates and exact attempt outcomes are in [validation](s5c-remote-vllm-validation.md).
The following adoption slice covers takeover; physical LAN/other accelerators
remain uncertified extensions.

**S5c reviewed remote adoption implemented (2026-10-14):** private SSH PID/model/
port forms, nonmutating inspections and Back/No reviews. Exact same-account,
isolated process/session, tested executable, owned loopback listener/model and
tunnel checks precede acknowledged takeover. An exclusive remote ownership guard
rejects competing clients; failed takeover retains the external server. Existing
settings/logs are retained; Stop/client/lease loss ends only the witnessed group,
including ignoring descendants, with honest confirmed/unconfirmed receipts.
The local client never interprets remote PIDs as local cleanup targets. Actual
upstream vLLM CLI generation returned Hello!; native CUDA llama.cpp TUI returned
OK. Review cancellation, three terminal widths, cleanup and retention of all 22
Ollama digests passed. [Evidence](s5c-remote-adoption-validation.md).
**S5c is complete locally for the supported Linux recipes and SSH workflows.**
Physical LAN/other platforms and additional installers need separately scoped
work; S6's native Vision slice follows below.

### S6 — Vision and image generation through Library → Media

**S6a: Vision**

- [x] S6a1: explicit native Ollama image/screenshot analysis through Library →
  Media and CLI, off-by-default switch, declared capability checks, explicit
  qualified model/fallbacks, reviewed budgets and owned cancellation.
- [x] S6a2: provider-neutral image messages and image attachments in ordinary
  coding chat, with private persistence/restore/compaction, provider switches and
  truthful per-turn pixel capabilities.
- [ ] S6a3: additional image-capable provider adapters with explicit capability
  evidence, endpoint/credential reviews and actual protocol/generation validation.
  - [x] S6a3a: native Anthropic and declared compatible HTTP **chat** image paths;
    actual compatible Ollama generation, native Anthropic TLS/TUI fixtures,
    independent session model restoration and bounded follow-up routing.
  - [x] S6a3b: extend reviewed Media analysis to the supported HTTP adapters,
    preserving explicit budgets/fallbacks, owned jobs and endpoint reviews.
  - [x] S6a3c: OpenRouter chat and reviewed Media through verified image/text
    declarations, bounded transport, private protocol state and actual free-model
    CLI/TUI generation, follow-ups and process resume.
  - [x] S6a3d: reviewed exact-ID OpenAI Responses chat/Media profiles and bounded
    native delivery; real TLS CLI/TUI/settings/cancel/resume fixtures. Live
    generation remains unverified due to exhausted account credits.
  - [x] S6a3e: exact reviewed Gemini 2.5 Flash/Flash-Lite profiles and bounded
    native images/signed continuation; real CLI/TUI TLS fixtures. Live generation
    remains unverified: both legacy IDs returned HTTP 404 for this account.
  - [x] S6a3f: exact reviewed current Gemini Thinking chat profiles, native signed
    text/tool/image continuity and actual Google one-shot/TUI/resume generation.
    Standard-only consumers remain unavailable to these models.
  - [ ] Remaining OpenAI/native Anthropic paid-provider generation certification
    and legacy Gemini access require actual successful generation evidence.

**S6a1 implemented locally (2026-10-14):** actual qwen3.5:4b identified the pixels
in a synthetic red/green/blue PNG through CLI and the real TUI. Unsupported
text-only models are rejected during selection; disabled analysis and declined
reviews send no pixels. Reviews at 40/70/120 columns, private results and clean
exit passed; all 22 Ollama digests/original image/workspace bytes were retained.
Fixed typed HTTPX fallback eligibility and an incorrectly short image-request
read timeout. No chat turns, indexing or tags are created. S6a is partial;
S6b/S6c remain unstarted. [Evidence](s6a-local-vision-validation.md).

**S6a2 implemented locally (2026-10-15):** image attachments in chat/one-shot
input use the active, explicitly selected image-capable native Ollama model.
Enabled Vision, declared capabilities, existing Runtime budgets and private
endpoint-scoped Media snapshots precede pixel delivery. Private references survive
source deletion, follow-ups and process restart; public history/export omit pixels.
Other providers omit historical pixels honestly. Failed preparation retains drafts/
attachments. Intent separation reduced an observed one-shot request from about
15,600 to 1,500 text characters; native qwen3.5:4b answered the actual pixels.
The unchanged text-reader-as-vision regression remains covered. Full local unit,
Ruff and production mypy gates passed. [Evidence](s6a2-chat-images-validation.md).

**S6a3a implemented locally (2026-10-15):** native Anthropic and compatible HTTP
chat images require fresh declared capabilities at the exact endpoint/model.
Existing private Media references, approval scopes, Runtime bounds and complete
tool protocols are reused. Real compatible Ollama gemma4:e2b passed one-shot,
interactive follow-ups and process resume after source removal. Anthropic passed
real CLI/TUI TLS protocol fixtures, with no paid generation claim. Resume now
restores the session model/mode instead of Default Chat; tool-free follow-ups
retain the user objective instead of turning assistant color names into lookup
topics. Media analysis remains native Ollama. [Evidence](s6a3-http-chat-images-validation.md).

**S6a3b implemented locally (2026-10-15):** reviewed Media analysis uses shared
exact-model capability inspection and native Anthropic/compatible runtimes,
without tools or chat/index/tag writes. Fallbacks, endpoint revisions and image
identity remain explicit. Context estimates/provider limits precede review/send;
shared worker bounds include metadata time without enlarging generation budgets.
Actual compatible Ollama gemma4:e2b identified the pixels through CLI/TUI;
Anthropic passed native protocol/owned-worker fixtures with canned answers.
Native model deletion protects compatible role aliases at the same server root.
Additional SDK adapters and paid certification remain open.
[Evidence](s6a3b-http-media-validation.md).

**S6a3c implemented (2026-10-15):** OpenRouter chat and reviewed Media require
fresh exact-model image-input/text-output declarations and preserve private
snapshots, endpoint/credential scope and existing budgets. Mandatory-reasoning
models need explicit Thinking mode and cannot serve the Media consumer. A shared
bounded HTTP image adapter retains complete tool pairs and signed private state;
text SDK responses also reject failed completion before releasing buffered calls.
Actual catalog-verified free-model one-shot/TUI/Media, source deletion and process
resume passed. A live large-catalog failure exposed and fixed a metadata/event
bound mix-up. A separate rate-limited model failed honestly without a fallback.
At that slice's completion OpenAI/Gemini still needed exact-model capability
evidence; S6a3d below adds reviewed OpenAI profiles without model-ID guesses.
[Evidence](s6a3c-openrouter-vision-validation.md).

**S6a3d implemented locally (2026-10-15):** exact-ID official model documentation
and fresh authenticated availability checks enable GPT-4.1 Mini images only on
the official OpenAI endpoint. UI distinguishes documented from declared support.
Native Responses image transport reuses private continuation and complete tools,
with bounded cancellation, explicit output and retained pixels across compaction.
Fix positive streaming output budgets, clean metadata timeouts and quota failure
classification. Real CLI/TUI TLS fixtures covered settings, review/decline, owned
Media/cancel, follow-ups and process resume; canned answers do not certify cloud
generation. Live generation remains unverified: the native API returned HTTP 429
credit_balance_exhausted. Gemini native images were still unstarted at that point.
[Evidence](s6a3d-openai-vision-validation.md).

**S6a3e implemented locally (2026-10-15):** official exact-ID profiles and fresh
identity/method/token-limit checks enable native Gemini 2.5 Flash/Flash-Lite images.
The existing chat/Media architecture owns pixels, cancellation and settings;
bounded HTTP handles inlineData, explicit thinking/output budgets, native tools
and private signed text/function continuation. STOP plus clean EOF precedes tool
publication; no SDK automatic continuation or Files upload runs. Fix a shared
HTTP Media usage-envelope bug and include thought tokens in native image output
usage. TLS one-shot/Media CLI and TUI settings/review/decline/cancel/follow-up/
process-resume fixtures passed. Live generation is unverified: both IDs returned
HTTP 404 despite visible metadata; Google's Flash error explicitly restricts new
users. No newer model was substituted. Newer thinking-required models need their
own chat/Media contract; S6a3 remains partial. [Evidence](s6a3e-gemini-vision-validation.md).
Final gates: **3,393 passed, 19 skipped**; Ruff, production mypy on 142 source
files and all five-wheel packaging/import/installed-CLI smoke checks passed.

**S6a3f implemented locally (2026-10-15):** exact reviewed Gemini 3.5 Flash-Lite
and 3.8 Flash profiles use native thinking levels and capability-derived session
mode/effort controls, with bounded minimal effort persisted where supported.
Native text from the first turn retains signed parts before images arrive;
parallel call/results remain atomic and grouped, while earlier foreign tool
results stay historical context without fake signatures. Standard-only consumers
reject incompatible model choices before generation. Both models completed real
RGB one-shot tasks. A real Flash-Lite TUI session listed/read a file through
signed tools, analyzed pixels, retained them after source deletion and resumed
in a fresh process with minimal effort. [Evidence](s6a3f-current-gemini-validation.md).
Final full gate: **3,430 passed, 19 skipped**, Ruff and production mypy on 142
source files passed. A fresh **191-test** native/session/runtime selection covers
the final request-counter refinement. All five-wheel packaging/import/installed-CLI
smoke checks passed. Catalog client lifetime/filtering and role availability
labels were also repaired; mandatory-thinking models remain unavailable to
Standard-only Media, Utility and Research consumers.

**Local Gemma follow-up validated (2026-10-15):** installed Gemma 4 E2B/E4B passed
actual native chat/owned Media RGB tasks and screenshot reading. The real TUI
also retained pixels after original-file deletion, explicit E2B→E4B selection
and fresh-process resume. No provider adapter or model-name exception was needed;
existing declared capabilities and bounded Standard-mode requests were sufficient.
All six CLI commands and both TUI processes exited 0; 130 relevant automated
regressions passed. E4B's first chat took 66.51 seconds versus 8.12 seconds for
its next screenshot request; these individual observations are not a controlled
performance benchmark. Larger Gemma variants were metadata-checked only.
[Evidence and limits](s6a-gemma-local-validation.md). The subsequent S6b1 slice
is described below; S6c remains unstarted.

**S6b: Image generation — native CPU/CUDA consumer validated; service extensions remain**

- [x] S6b1: existing native stable-diffusion.cpp endpoint, OFF-by-default settings,
  tested loaded-model pin, reviewed size/steps/seed, one owned asynchronous job
  and scoped cancellation. Separate generation settings do not alter chat roles.
- [x] Atomic private PNG/provenance/session/job storage in Media; existing
  detail/export/tags/archive/delete lifecycle. Actual CLI/TUI fixture walkthrough
  covers declines, acceptance, Ctrl+C 130, settings saves and three widths.
- [x] Actual native CPU image-server inference, queued/running cancellation
  outcomes and exact export through CLI/TUI. Protocol fixtures are recorded separately.
- [x] Actual native CUDA CLI/TUI inference, explicit device allocation and exact
  export on GTX 1650 through the supported upstream-GGML build configuration.
- Further certification: other model/budget/hardware profiles and broader image
  quality. The tested model missed requested background colors.
- Deferred extensions: further services/authentication and model-specific controls
  require their own evidence; the native adapter does not infer a quality scale.

**S6b1 implemented (2026-10-15):** core image_generation and CLI generation_panel/
generation_commands reuse the existing owned worker, ordered settings writer and
artifact store. Unknown replies are retained without resubmission, cancellation
checks only the accepted native ID, late results cannot replace new session/store
state, and receipt loss after output commit recovers the already-saved artifact.
At that checkpoint no image service/weights/installers were introduced; S6b was partial.
[Implementation, actual CLI/TUI protocol evidence and limits](s6b-local-generation-validation.md).
Full gate: **3,456 passed, 19 skipped**, Ruff and production mypy on 145 source
files passed. A final **37-test** generation/settings-writer selection covers
the last request-state refinements; final five-wheel packaging/import/installed-CLI
smoke checks passed. These checks do not close the real diffusion-inference gate.

**S6b follow-up (2026-10-15):** corrected completed-during-Cancel outcomes and
added explicitly reviewed retrieval of already-completed native output through
`generation-status --recover` and the current TUI result. Recovery shares pixel,
receipt/binding and atomic publication checks and never submits generation.
Real CLI/TUI fixture walkthrough (40/70/120 columns), declines, idempotence and
Ctrl+C/clean exit passed. Initial local gates passed: 3,468 tests, 19 skips, Ruff,
production mypy on 145 files, and five-wheel packaging.
[Follow-up evidence](s6b-local-generation-validation.md#s6b-follow-up-cancellation-race-and-explicit-output-recovery).

**S6b2 native validation (2026-10-15):** real stable-diffusion.cpp CPU generation
and export passed through CLI and bare TUI. Actual capabilities exposed automatic
sampler defaults and unsupported running cancellation, which the fixture had
missed. Requests now retain automatic defaults; reviews warn that only queued
jobs can be stopped. Rejected cancellation still observes the exact job; running,
completed and cancelled remain distinct. Explicit completed-output recovery never
resubmits generation. Final review at 40/70/120 columns defaults to Back, with
endpoint/model visible at 120 columns and paging at narrow widths. The tested
256-pixel outputs had poor fidelity; inference success is not a quality guarantee.
An additional 512×512/eight-step CLI image completed in 238.50 seconds of native
inference and exported exactly; visual inspection found a recognizable but soft
yellow duck. Sampled peak server RSS was 3.10 GiB with no observed GPU allocation.
The isolated server was stopped after validation. Full gate: 3,472 passed,
19 skipped, Ruff/mypy (145 files); final scoped image suite: 43 passed after the
last review/visibility edits. Final five-wheel packaging passed; exact gate
timing/snapshot boundaries are recorded in the evidence.
Upstream CUDA12.0 compilation failed and CUDA diffusion remains unverified; CPU
was explicitly selected for the isolated test. Further services/authentication,
model-specific controls remain extensions. The subsequent history/tag slice is below.
[Native evidence and limits](s6b-local-generation-validation.md#s6b2-actual-native-cpu-generation-and-protocol-corrections).

**S6c: Optional AI tags**

- [x] Explicit image-tagging action after vision works; distinguish generated
  tags from manual tags and preserve manual choices.
- [x] Back-focused Vision request, initially unselected suggestions, selected save
  and separate AI-tag clearing, search and provenance/lifecycle support.
- [x] Actual Gemma E2B CLI/TUI pixel-to-tag generation and selected persistence;
  manual-tag retention, declined clear, three widths and clean exit.

**S6b3/S6c implemented (2026-10-15):** image jobs now have a private inventory,
explicit server status checks, existing output recovery and reviewed receipt
cleanup, independent of saved images. CLI lists keep full IDs and omit prompts.
Native Gemma tagging reuses the existing Vision worker/model/budget controls;
proposals never save automatically and manual choices are retained. Old stores
stay read-only on browse; accepted writes migrate atomically. Focused regressions
and actual CLI/TUI flows passed. Final full checks passed: 3,496 tests, 19 skips,
Ruff, mypy on 146 production files and fresh five-wheel packaging. Native CUDA
CLI/TUI generation also passed (96.80/62.79 seconds for the two tested budgets);
the exact test server was stopped afterward. Paid/legacy-provider generation
certification still requires external account access. S6 is implemented for these
scopes, but is not fully certified across all provider accounts.
[Implementation, real-model evidence and limits](s6-completion-validation.md).

**Gate:** actual analysis/generation, cancellation/errors and artifact export;
selected endpoint and budgets remain explicit. Importing/viewing Media starts
no automatic model calls or knowledge indexing.

**Resumed certification/reliability follow-up (2026-10-15):** the published
checkpoint's CI exposed uv discovery failing outside standard install paths.
The explicit launcher hint now survives owned workers, retaining executable
review/revision checks and restricted subprocess PATH. Media preserves known
redacted provider reasons, wraps errors at narrow widths, retains retry input
and loads unknown Vision-role labels through owned metadata inventory. Actual
CLI/TUI fixture checks passed; checkpoint `86f57a3` passed fresh Python 3.11–3.13
CI, lint/types and five-wheel packaging. The corrected valid-image OpenAI recheck
timed out; Anthropic credentials remain absent. Those results do not close the paid/
legacy-provider generation gate. Exact local/CI snapshot boundaries and results:
[S6 follow-up](s6-completion-validation.md#resumed-s6-verification-ci-tool-discovery-and-provider-diagnostics).

### Deferred product extensions

- Email writing style and speech controls need separately designed consumers.
- AI Tidy needs a reviewable proposal and selected, acknowledged changes.
- A standalone Gallery, photo/album workspace or canvas/layer editor needs a
  future product decision; it has no delivery milestone in S0–S6.

### Remaining S6 certification gates

With **S0–S5 and S6a1/S6a2/S6a3a/S6a3b/S6a3c/S6a3d/S6a3e/S6a3f implemented for their scopes**,
the remaining **S6a3 OpenAI/native Anthropic and legacy Gemini certification**
requires funded/authorized account access and actual successful generation.
The adapters and protocol/recovery paths already exist. The final account-access
audit above identifies external blockers; no further S6 implementation slice is
currently identified. Once access changes, use explicit endpoint/model reviews
and the existing CLI/TUI scenarios, without substituting models to claim a pass.
S6a3 remains partial until those live gates pass.
S6b1/S6b2's native local consumer now has actual CPU generation/cancellation/export
evidence. The final pass also validates a supported upstream-GGML CUDA build and
real native GPU CLI/TUI generation. Broader model/budget quality evidence and
additional services/authentication remain separately scoped extensions.
Job-history/cleanup and S6c tagging are implemented and locally exercised.
The upstream remote-vLLM validation now covers actual CLI/TUI CUDA generation
on GTX 1650 over loopback SSH. Other hosts/models/hardware need separate evidence.
Local dependency/CPU builds, SSH settings/diagnostics, owned remote CPU serving
and reviewed existing-public-key/host-trust setup, CUDA build profiles and
offline NVIDIA vLLM wheel installations, reviewed retained setup removal and
remote llama.cpp GPU profiles, reviewed remote NVIDIA vLLM serving and reviewed
remote adoption are implemented and locally validated.
Additional remote serving profiles need
their own observed hardware/engine evidence; observed processes do not authorize
adoption. Library's foundation,
artifact workflows, explicit Knowledge actions and Deep Research consumers
passed their recorded local validation gates.
**S5c's supported Linux scope and S6a1 native image analysis are complete locally.**
Reviewed legacy Gemini delivery is implemented but generation access is unverified.
Reviewed current Gemini Thinking chat has real generation evidence; Standard-only
Media/Utility/Research retain their existing contracts. S6a3 is partial.
S6b local generation has native CPU/CUDA inference and protocol evidence; broader
image-quality validation remains open. S6c tags and S6b3 job management
are implemented with actual CLI/TUI validation recorded separately.
Additional online/system/other-platform
installation paths remain outside the delivered local recipes. See the
[S1 evidence](s1-model-connections-validation.md) and
[S2 connection UI evidence](s2-model-settings-validation.md), followed by the
[S2b AI Defaults evidence](s2b-ai-defaults-validation.md) and
[S2c DeepSeek evidence](s2c-deepseek-validation.md) and
[native Anthropic evidence](s2c-anthropic-validation.md) and
[S3a Web Search evidence](s3a-web-search-validation.md) and
[URL Fetch evidence](s3a-url-fetch-validation.md) and
[Agent execution evidence](s3b-agent-execution-validation.md) and
[Agent Tools/navigation evidence](s3b-agent-tools-validation.md) and
[Library foundation evidence](s4a-library-validation.md) and
[artifact workflow evidence](s4a-artifacts-validation.md) and
[Knowledge action evidence](s4a-knowledge-validation.md) and
[Deep Research evidence](s4b-deep-research-validation.md) and
[Model Manager lifecycle evidence](s5a-model-manager-validation.md) and
[managed serving evidence](s5b-managed-serving-validation.md) and
[local dependency/build evidence](s5c-dependencies-validation.md) and
[SSH settings/diagnostic evidence](s5c-ssh-validation.md) and
[owned SSH CPU serving evidence](s5c-remote-serving-validation.md) and
[reviewed SSH key setup evidence](s5c-ssh-key-setup-validation.md) and
[local engine recipe evidence](s5c-engine-recipes-validation.md).

## 9. Validation plan

### Interaction checks

- Test 40-, 70-, and 120-column terminals, small heights, long URLs/model names,
  Unicode names, wrapped descriptions, and a large inventory.
- Walk every path with keyboard only: entry, form edit, test/cancel, apply/save,
  filter, pagination, detail, nested Back, Escape and scoped Reset.
- Check controls above tables, actual data headers, stable focus/viewport, fixed
  footer, preserved composer draft, ordinary scrollback and semantic colors.
- Slow/failing jobs, rapid source changes, closing/reopening pages, stale results,
  cross-client writes, unconfirmed saves and partial probe/remove outcomes.
- Empty/unconfigured and offline/authentication states offer useful actions;
  disabled/unimplemented services do not present misleading active controls.

### Runtime and regression checks

- Real interactive and one-shot sessions through the CLI, including tools on
  local Ollama and an available compatible endpoint. Mocked API tests cover
  protocol/error cases but do not establish live server/provider support.
- Multiple endpoints with identical model IDs, invalid base paths, missing model
  catalogs, protected LAN endpoints and changed credentials.
- Existing provider continuation, cancellation, malformed-call recovery, path
  recovery, shell failure tracking, workspace-cache invalidation, dirty-worktree
  safety, plan approval, validation reruns and exit-code correctness.
- Utility/research/fallback calls obey aggregate budgets; small local models do
  not gain unnecessary calls, duplicate schemas, larger default context or
  parallel generation merely because the pages exist.
- Session switch/resume, model change during work, endpoint deletion during work,
  shutdown resource cleanup and active-worker ownership.
- Model/server probes and provider tests use explicit user actions and private
  test inputs; failures do not leak secrets or claim success.
- Library lifecycle checks: store/import without knowledge indexing or model
  calls; explicit learning into a named library; archive/restore without content
  deletion; permanent deletion shows its scope and any indexed-copy implications.
- Media checks: screenshots and uploaded/generated artifacts, metadata and manual
  tags, supported/unsupported previews, headless external-open fallback, export
  and source-file preservation. Basic management works without vision/generation.

For implementation changes, run the relevant focused tests, then the project's
existing locked unit, Ruff, and production-source mypy validation via `make check`.
Run `make package-smoke` when package/dependency/entrypoint changes warrant it.
Report hanging, unavailable-service, or incomplete checks separately.

The original planning-only change ran no application tests. Subsequent
implementation and fresh feature verification are recorded in the
[S0–S6 verification report](odysseus-feature-verification.md), including exact
runtime/test scope and the remaining account-blocked S6 gates. Source inspection
alone does not prove feature behavior.

## 10. Source index

### Odysseus source inspected

Pinned paths below identify the reviewed main snapshot. The fetched dev diff
was also checked for the settings/model/research surface.

- [Settings forms](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/index.html),
  [page registry](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/settings/registry.js),
  [settings bindings](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/settings.js),
  [endpoint/tool actions](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/admin.js).
- [Backend defaults](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/settings.py),
  [model routes](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/routes/model_routes.py),
  [endpoint resolver](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/endpoint_resolver.py).
- [Cookbook](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/cookbook.js),
  [hardware-fit controls](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/cookbook-hwfit.js),
  [serving controls](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/cookbookServe.js),
  [Cookbook routes](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/routes/cookbook_routes.py).
- [Research form](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/research/panel.js),
  [research engine](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/deep_research.py),
  [research handler](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/src/research_handler.py).
- [Gallery views and tagging](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/gallery.js),
  [visual editor](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/galleryEditor.js),
  [Library views](https://github.com/odysseus-dev/odysseus/blob/934d23c0be29c9721385f34565c0ae2cbd60da04/static/js/documentLibrary.js).

### Current server/provider documentation

The following support keeping API compatibility and capability discovery
explicit. Their current documentation was browsed during this review.

- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility):
  a compatibility surface does not replace all native Ollama behavior.
- [llama.cpp server](https://github.com/ggml-org/llama.cpp/tree/master/tools/server):
  compatible serving and model/server configuration.
- [vLLM compatible server](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/):
  API support and chat-template/model-dependent behavior.
- [Claude SDK compatibility](https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk):
  its documented compatibility limitations support using a native adapter for
  production tool/continuation behavior.
- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/) and
  [Responses support](https://api-docs.deepseek.com/guides/responses_api/):
  choose a supported contract deliberately rather than assuming one universal
  OpenAI-style API.

### Klaude implementation inspected

- [Command/settings wiring](../apps/cli/src/klaude_cli/main.py),
  [shared panel](../apps/cli/src/klaude_cli/settings_panel.py),
  [overview jobs](../apps/cli/src/klaude_cli/settings_overview.py).
- [Configuration](../packages/core/src/klaude_core/config.py),
  [runtime adapters and model identity](../packages/core/src/klaude_core/model_runtime.py),
  [execution governor](../packages/core/src/klaude_core/execution.py),
  [deterministic compaction](../packages/core/src/klaude_core/context_compaction.py),
  [research receipts](../packages/core/src/klaude_core/research_receipts.py).
- [Settings UX audit](settings-ux-audit.md),
  [MCPs/Skills UX plan](mcp-skills-settings-ux-plan.md),
  [agent orchestration plan](agent-orchestration-plan.md),
  [power-user evaluation](power-user-evaluation.md).
