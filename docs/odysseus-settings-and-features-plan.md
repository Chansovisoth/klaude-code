# Odysseus settings and feature plan for Klaude

Status: reviewed and proposed; requested feature implementation has not started.
Reviewed: 2026-10-05. Klaude baseline: `fdb2386`.
Product direction updated: 2026-10-06; artifact/media management belongs in Library.
Phase grouping updated: 2026-10-06; S0 complete, S1–S6 planned and unstarted.

## 1. Objective and scope

Add the requested model, AI-default, search, and agent-tool settings with clear
navigation, then introduce Model Manager, Deep Research, and Library with a Media
view for coding artifacts. Reuse Klaude's working settings panel, runtime, permission,
retrieval, and persistence components. Keep ordinary chat fast and local model
defaults bounded.

Klaude remains a coding/agent environment. Library is its durable information
workspace; Media manages screenshots and image artifacts used or produced by
that work. A standalone Gallery and canvas/layer editing are outside this plan.

This document records an implementation plan, not implemented functionality.
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
    MCPs · Skills · Memory · Permissions
  ADVANCED
    Runtime
```

Keep **Add Models** and **Added Models** as real pages with the requested names;
group them under Models rather than adding multiple competing model entries to
the Settings home. Manage/Added comes first, consistent with MCPs and Skills.
The Models summary shows connected/enabled endpoint counts and the default
chat model. Add Models offers two entry actions, so only one form is edited at
a time. Added Models leads with its inventory controls and endpoint list.

Model Manager, Deep Research, and Library are feature workspaces reached through
a proposed feature launcher, outside Settings. Library contains Sessions,
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
| Providers Hugging Face token | Model Manager → Settings | Existing Providers entry can link here until Model Manager is implemented. |
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

- [ ] Store multiple connections with stable endpoint IDs, adapter type,
  normalized URL, enabled state and private credential references.
- [ ] Migrate the current Ollama URL, startup model and native-provider choices;
  retain session resume and field-scoped preferences.
- [ ] Identify/cache a model by endpoint plus model ID; keep same-named models
  on different servers distinct.
- [ ] Add owned, cancellable discovery/health checks with precise authentication,
  network, missing-catalog and malformed-response feedback.
- [ ] Add the compatible runtime needed for explicitly configured llama.cpp,
  vLLM or other compatible servers; retain native provider continuation/tools.

**Gate:** use the existing Ollama connection and a second manually entered local
endpoint through real chat and tool calls; verify identity, restart/resume,
streaming, cancellation and malformed-call recovery. Clearly distinguish mocked
protocol coverage from a server that was actually available and tested.

### S2 — Models pages and AI Defaults

**S2a: Connect and manage models**

- [ ] Models landing page with Added Models, Add Models and session selection.
- [ ] Add Local Models and Add API Models forms: name, adapter/provider,
  endpoint, masked authentication, Test, Add and Cancel.
- [ ] Added Models: probe, endpoint detail, enable/disable, reviewed removal and
  acknowledged outcomes; authentication errors stay distinct from offline state.
- [ ] Per-endpoint model inventory: Filter, Reload, enabled/total count,
  per-model visibility/pinning and observed/unknown capability metadata.

**S2b: Defaults with functioning consumers**

- [ ] Default Chat endpoint/model for new sessions; preserve the current
  session's independent model choice and pending changes during a running turn.
- [ ] Utility endpoint/model, Same as chat inheritance and ordered explicit
  fallbacks, paired with bounded optional naming/summary consumers.
- [ ] Display effective selections and fallback use. Keep deterministic
  compaction and avoid extra model calls for simple requests.
- [ ] Add Research, Vision and Image generation controls when their S4/S6
  consumers work; preserve the existing embedding role and migration boundary.

**S2c: Additional cloud adapters**

- [ ] Add DeepSeek, then native Anthropic and other supported presets in
  separately validated slices. Existing OpenAI API, Gemini API, OpenRouter and
  Codex account paths remain available.

**Gate:** keyboard walkthroughs of draft test/add/cancel, multiple endpoints,
auth/offline states, removal, restart persistence and session/default differences;
verify that credentials stay bound to their intended service. Provider presets
become selectable only with an implemented, validated adapter.

### S3 — Search and Agent Tools

**S3a: Search**

- [ ] Web Search: Auto/pinned provider, relevant provider fields and masked
  credentials, results per query, Test, enabled state and fallback ordering.
- [ ] URL Fetch: its own provider configuration, credentials and availability.
- [ ] Move existing web-provider controls to their single owning page; retain
  current routing/validation semantics and compatibility links.
- [ ] Add Google PSE/Serper or other new search adapters only as complete,
  separately tested slices with their actual credential fields.

**S3b: Agent Tools and navigation migration**

- [ ] Execution: maximum steps, Auto/Custom tool-call limits, advanced token
  budget and provider-aware subagent worker limits. Migrate current zero to Auto;
  an Unlimited option requires separately implemented and verified semantics.
- [ ] Registry-derived groups, enabled/total counts, individual/group toggles
  with mixed state, permission links and Activity Updates.
- [ ] Link MCPs and Skills to their existing managed-capability pages; retain
  their search/manage navigation and the existing Memory/Permissions ownership.
- [ ] Move only the relevant controls from Tools, Providers and Runtime; keep
  device/context/calibration in Runtime and update canonical help/aliases.
- [ ] Apply the proposed Settings grouping and shared width, filtering,
  focus/Back, table-header and footer conventions across migrated pages.

**Gate:** rapid edits, failed saves and Back/filtering preserve authoritative
state; disabled tools stay absent on every execution path; current search routing,
permissions, read-only delegation and all existing entry routes keep working.

### S4 — Library, then Deep Research

**S4a: Library and durable artifacts**

- [ ] Build the Library workspace in this order: **Sessions, Knowledge,
  Documents, Research, Media, Archive**. Add working actions as their consumers
  arrive; prepare report storage for S4b.
- [ ] Sessions/Knowledge first: browse, search, resume, explicit learning/query
  and refresh, preserving existing library IDs and compatibility commands.
- [ ] Documents: import/store, metadata, filters, open and export; learning into
  a named knowledge library remains explicit.
- [ ] Media: screenshots and uploaded/imported images, previews with terminal
  fallbacks, metadata, manual tags, open externally and export.
- [ ] Archive: start with sessions, search/restore retained content, separate
  confirmed permanent deletion; extend to artifact types with supported lifecycle.
- [ ] Maintain **Stored ≠ indexed; Imported ≠ learned; Archived ≠ deleted**.

**S4b: Deep Research**

- [ ] Job form: question, format, bounded rounds, search provider, endpoint/model
  overrides, Queue and Start.
- [ ] AI Defaults research role plus Search research defaults: max report
  tokens, extraction timeout/parallelism, run deadline and advanced budgets.
- [ ] Owned jobs with public progress, sources, cancel, partial/error outcomes
  and bounded recovery/checkpoints using the canonical runtime.
- [ ] Sourced reports saved into Library → Research, with view/discuss/export
  and explicit learning; re-fetch required evidence on recovery.

**Gate:** imports preserve originals and launch no indexing/model calls; archive
restores content; Media works without vision/generation. A real multi-step
research job produces supported citations, saves its report and handles
cancellation/recovery honestly, with bounded local-model work.

### S5 — Model Manager

**S5a: Local Ollama lifecycle**

- [ ] Installed-model inventory, discovery/download, progress/cancel, hardware
  information and Hugging Face credential/settings ownership where relevant.
- [ ] Native Ollama pull/remove and service health/status; distinguish removing
  a connection from explicitly deleting a downloaded model.

**S5b: Managed serving**

- [ ] Integrate already-installed llama.cpp/vLLM, then owned launch/stop/logs,
  validated model/port/device/context fields and supported engine options.
- [ ] Register served endpoints after a successful health check; explicitly
  adopt existing processes and stop only owned processes.

**S5c: Dependencies and remote servers**

- [ ] Dependency inspection and explicitly requested installation/rebuild.
- [ ] SSH server configuration, connection testing, model directories and
  server-scoped hardware/process settings as a separate extension.

**Gate:** verify actual download cancellation, disk/port/engine failures,
unavailable hardware, owned-process cleanup, endpoint registration and explicit
file deletion for each supported slice. Configuration must not imply untested
hardware fit or tool reliability.

### S6 — Vision and image generation through Library → Media

**S6a: Vision**

- [ ] Working image/screenshot input, analysis adapter, enable switch,
  capability-aware model selection and explicit role fallbacks.

**S6b: Image generation**

- [ ] Working image-service connections and generation jobs; enabled state,
  selected model and only quality options supported by that adapter.
- [ ] Save generated output, provenance and session/task associations into Media.

**S6c: Optional AI tags**

- [ ] Explicit image-tagging action after vision works; distinguish generated
  tags from manual tags and preserve manual choices.

**Gate:** actual analysis/generation, cancellation/errors and artifact export;
selected endpoint and budgets remain explicit. Importing/viewing Media starts
no automatic model calls or knowledge indexing.

### Deferred product extensions

- Email writing style and speech controls need separately designed consumers.
- AI Tidy needs a reviewable proposal and selected, acknowledged changes.
- A standalone Gallery, photo/album workspace or canvas/layer editor needs a
  future product decision; it has no delivery milestone in S0–S6.

### First implementation slice

With **S0 complete**, the next implementation slice is **S1 for the existing
Ollama configuration and a second manually entered local endpoint**.
Establish migration, identity, ownership and testing before wiring the full
Add/Added forms. S2 then delivers
the immediately useful model-settings flow. Subsequent slices follow the order
above and their individual gates.

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

No application test suite was run for this planning-only change. Current source
inspection does not prove the planned feature behavior. Future completion
requires real UI/session evidence alongside automated checks.

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
