# WebUI v2 coverage

Current browser implementation: **partial**. The planning specification describes
the target, not completed functionality. This checklist supersedes the original
inventory's historical statements that no host/browser API exists.

| Surface | Available in the browser | Remaining |
| --- | --- | --- |
| Chat | CommonMark replies with tables/tasks, local code highlighting and copy, stable streaming, response actions, timestamp/Branch/Retry menu, shared Agent, conversation rename/archive/restore/delete and Markdown download, configured local/cloud model selection and supported effort controls, explicit startup defaults, tool reviews, questions, queue/control, device/Library text, PDF, DOCX and image attachments | In-place answer variants, model connection management, queued attachments and image frame/crop controls |
| Workspaces | Bounded reads/search/Git views; opt-in local edits | Full workspace lifecycle and coding controls |
| Library → Uploads | List/Grid/Gallery, image-only month-added groups, bounded cached thumbnails, adaptive image preview with zoom/touch controls, reviewed source links/tag chips, URL history, independent type/archive filters and sorting, reviewed imports with automatic image detection, text preview/download/tags/archive/restore/delete, reviewed saved-file Learn, image analysis and selected AI tags | Directory trees, original modification/capture dates, rich document rendering and bulk management |
| Library → Generated | Separate inventory of saved reports/images, existing file views/actions, reviewed report Learn, Research queue/start/stop with configurable saved budgets and image-service generation/cancel/output recovery, image analysis and selected AI tags, separate saved Research model | Arbitrary generated workspace files and broader job history/control |
| Integrations → Knowledge | Compact paged library/source rows, source/chunk counts, indexed-text search, reviewed public-URL/text-upload Learn, exact existing-source refresh and URL history; legacy Library Knowledge links migrate here | Hybrid/model queries, crawl/source creation and broader management |
| Integrations → Skills | Compact paged rows/filter, direct confirmed-state enable/disable switches, native metadata/deletion details, reviewed local ZIP/Markdown import and deletion | Discovery, remote installation, update checks and updates |
| Integrations → Connections | Compact MCP inventory with search/status filters, native add/details dialogs, reviewed remote connection creation (disabled) and removal, direct discovery/enable and disable switches, next-turn tool loading; password-authenticated owners can manage through local and LAN listeners; shared definition journal and CLI recovery | Registry discovery, custom stdio creation, secret entry, interactive OAuth and browser recovery; bootstrap-only LAN hosts remain read-only |
| Activity | Public chat events and persisted Library, profile/settings and Generated operation states, shared Model Defaults/image-service recovery and owned Vision stop | General browser domain reconciliation/recovery and broader operation controls |
| Settings | Browser appearance/password change, WebUI timezone selection, Memory inventory/filter/add/edit/forget and automatic memory, shared execution limits, read-tool availability/permissions including current_time, Search/Fetch routing/endpoints and Research budgets with conflict checks, Model Defaults/fallbacks/Vision activation, image-service setup and exact-state recovery | Remaining model/provider/runtime/domain settings, search fallback ordering and provider credentials, custom/image-derived colors and additional account controls |
| Models | Main navigation page with configured local/cloud connections, searchable 20-item catalog pages, exact current-chat model selection, Model Defaults shortcut; supported reasoning efforts and exact saved-runtime resume without generation or catalog contact, reviewed shared default-role changes | Model Manager, connection creation/credentials and serving/download/SSH operations |

Initial Library/Skills actions cover parts of inventory F058–F060, F069–F070,
F072–F073 and F080–F082. They do not establish whole-feature parity. Desktop and
mobile reuse the existing Material 3 Expressive shell, tokens and reduced motion.
Shared page loading uses Google's seven-shape Material indicator, with compiled
official morph geometry and native spring/rotation constants. Chat activity,
refresh and pending operations use compact uncontained variants; pages use a
contained variant beside real loading descriptions and static skeletons.
System/app reduced motion and hidden content stop animation. Provenance,
maintenance and verification: `material-loading-indicator.md`.
Uploads has a compact search/filter/sort/add toolbar with 48px action targets.
Mobile lists omit desktop column headers, use 70px rows and place the first file
4px below the toolbar. The plus button opens the existing reviewed upload flow
in a native dialog; desktop retains its sortable columns and inline filters.
File previews share the existing header, scroll region, contextual toolbar and
details panel. Supported source files have line numbers and bundled syntax
highlighting; Markdown offers safe Preview/Source modes. Source text preserves
indentation and line endings within the existing 16 KiB/100-line preview bound,
with an explicit truncation notice and a complete original-file download.
Wrap/No wrap and Copy stay inside the viewer without page overflow. Image zoom,
navigation and gestures retain the existing implementation. Validation and
encoding/highlighting limits: `file-preview-refinement.md`.
Uploads contains imported documents/media only. Generated uses stored research
records and generated-image provenance, with separate counts and tab state.
AI tagging an imported image leaves it in Uploads. Existing artifacts stay in their
current store; the split is applied before search, sorting and pagination.
Uploads and Generated share All types/Documents/Media filters. Saved research
reports appear under Generated → Documents using their existing Research records.
Refresh re-fetches without clearing tab, type, status, search, sort or view;
concurrent clicks are deduplicated and failed refreshes keep existing content.
The single Library search field debounces backend reads. On phones, four frequent
destinations and More replace the small bottom labels; More retains Models,
Activity and Settings through a native keyboard-accessible popover. Desktop
navigation keeps every destination visible. Primary view URLs support reload and browser history alongside the
existing Library/Knowledge state. Validation: `ux-refinement-validation.md`.
Skills URLs also retain their bounded search query and page. Navigation and
collection headings wrap enlarged text, with phone content reserving the bar's
actual height; forced-color Skill switches preserve visible state cues.
WebUI conversations have fresh date/time context each turn and a network-free
`current_time` tool. Settings → Agent → Date and time selects a named IANA zone
or follows the host automatically. Explicit tool overrides leave the saved zone
unchanged. Validation: `date-time-validation.md`.

## Boundaries

- Shared `application.library_management` composes existing artifact, knowledge
  and Skill services. Reads avoid knowledge engine initialization and model/network
  work. Uploads uses stable 24-item pages across List/Grid/Gallery, with an eight-page
  short metadata cache and abortable reads. Grids use two/three/four/six columns;
  Gallery uses three/four/six and month boundaries may end in partial rows.
  Knowledge inventories/matches/sources and installed Skills use compact rows
  with 20-item pages, with chevrons,
  persistent first/last page numbers and ellipses around the current range.
  Filtered counts and the page size determine the actual final page.
  Mobile uses up to five numbered pages with 36–38px wide, 40px tall controls and
  wider rows, retaining first/last and nearby pages with centered-dot gaps;
  resizing reloads cards only when capacity changes and keeps the page containing
  the former first item.
  Search/filtering applies before paging;
  the browser composes at most two bounded reads per card page, including
  indexed-text/FTS matches. CLI/TUI batch sizes remain unchanged.
  Updated browser assets also paginate the previous host's bounded inventories,
  so active chat work can continue until a safe host restart. Its older text
  search retains the previous 20-match cap until that restart.
  Management changes affect the shared CLI stores. Browser chat adds lazy Knowledge,
  installed Skill and web read tools; configured MCP schemas load at each turn
  boundary without startup connections. External calls require exact browser
  review and recheck the current definition. File edits retain local activation
  and every-action review; shell and Git writes remain unavailable.
- Same-origin requests retain cookie, CSRF and tab ownership checks. Confirmation
  acquires session control automatically and checks an idle chat boundary. Browser
  actions refresh control and acquire it only when needed; watching, polling and
  tab focus never take control. Pending reviews/questions are visible across
  authenticated owner clients; each response still uses the fenced decision path.
  Hosted terminal reviews/cancellation also acquire on action. Only a competing
  control acquisition may be retried; mutations with uncertain outcomes are never
  automatically repeated. Session/revision checks and independent client drafts
  remain in force. Reviews expire after
  five minutes. Uploads become bounded private immutable snapshots; no browser
  host path, root or callable is accepted. Import remains separate from indexing.
- Submitted queue receipts remain in history without blocking idle controls or
  appearing as pending work. Handoff behavior and focused evidence:
  [Session control validation](session-control-validation.md).
- Documents download as attachments. Inline previews allow only bounded
  PNG/JPEG/WebP/GIF images. HTML/SVG and Markdown never execute. Downloads verify
  stored checksums and never launch a host application.
  Library thumbnails and expanded image previews are separately decoded derivatives
  (320/2048px), with 32 MiB/40MP sources and the shared decoder limits. Exact
  revision/hash checks and owner authentication precede access; a private bounded
  cache avoids repeated decoding. HTTP cache storage remains disabled.
- Mutations use existing revision/manifest checks and owned subprocesses with a
  180-second owner timeout for ordinary operations; Research uses its saved
  deadline plus 30 seconds, and image generation has a 330-second owner limit. Durable receipts deduplicate supplied request IDs.
  Accepted work continues through navigation/logout; host shutdown stops workers.
  Loss/timeout can leave an **unknown** outcome and a fenced resource. Browser
  recovery is unfinished; do not automatically resubmit unknown work.
- This is one profile's admin surface, not multi-user isolation or transactional
  coordination with every legacy CLI writer. LAN retains the existing trusted
  network HTTP boundary and warning.

## Validation

- 102 focused WebUI/accounts/application Library/Knowledge/Skills tests passed.
- 93 existing artifact/workspace/Skill/knowledge/operation regressions passed.
- Ruff and production mypy passed; seven-wheel offline package smoke passed.
- Chrome 148 exercised upload/review/import, inert document preview, image
  thumbnails/detail, tags, archive/restore, knowledge search/file learning, Skill
  import/disable, Activity and logout clearing. Indexing used real services with
  a deterministic loopback embedding fixture. Layouts: 320, 390, 768, 1024 and
  1440 pixels. No external-model/provider certification is implied. The full
  repository suite was not rerun for this slice.

## Feature completion work (2026-10-21)

The browser now uses the shared settings writer, Memory mutations, session
lifecycle guards, MCP definition writer, Research owner and image job operations.
Automatic memory uses the existing conservative candidate rules after a committed
browser turn. Sensitive saved facts stay hidden. New browser settings affect the
next turn and preserve unrelated terminal settings. Native boolean Thinking stays
at medium; other adapters offer only their supported effort levels.

MCP definitions use one witnessed receipt/fence shared with CLI/TUI. Existing
`klaude mcp recover` / `recover-oauth` can inspect an unknown save. Browser recovery
controls, Registry installation and interactive OAuth remain separate work.
Research reports use current source fetching and exact saved provider/budget
bindings. Image generation uses an already configured image service; recovery
fetches acknowledged output without submitting generation again.

Evidence and remaining work: [feature completion validation](feature-completion-validation.md)
and [implementation plan](feature-completion-plan.md). Browser feature parity is
still partial; the remaining column above is intentional.

Media continuation: [Model Defaults, image service and Vision validation](media-controls-validation.md).

Model Defaults automatically loads models from the selected configured connection,
including on connection changes. Per-role metadata filters Startup chat, Utility,
Research, Vision and Utility/Vision fallbacks. Native Ollama capabilities come from
bounded `/api/show` batches, not model-name guesses; Vision does not require tool
support. Unknown capabilities remain labeled for verification during the existing
review. Saved choices, drafts and previously loaded models survive catalog errors.
See [Model Defaults dropdown validation](model-defaults-validation.md).
