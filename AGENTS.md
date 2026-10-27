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

- `packages/application`: in-process chat composition, typed public events,
  bounded headless turn worker, structured interaction broker, and an additive
  SQLite admission/fencing/replay journal shared by real CLI, TUI and headless
  chat turns. An expired turn preserves its public partial, becomes interrupted,
  and blocks new work until explicit reconciliation (`klaude sessions reconcile
  SESSION_ID`). The in-process application also owns bounded queue/control,
  workspace binding, plan-mode revisions and explicit restart recovery. Durable
  request receipts deduplicate supplied IDs for persistent coordination mutations
  and the two shared chat-preference fields; embedded callers remain compatible
  without supplying IDs. Old
  binaries cannot claim a lease after schema migration. Compatibility test
  doubles retain the earlier Memory seam; other application domains still need
  M3 service extraction. Headless and terminal turns use the same fenced lease
  keeper and storage-outage grace. A typed settings seam offers compare-and-set
  writes for chat composer mode and activity updates; the TUI chat-preferences
  writer checks stale fields under the same file lock while merging unrelated
  fields. Other domain settings and appearance retain their existing writers.
  Terminal presentation stays in the CLI. The experimental browser host is
  separate. M3 has begun with a typed, bounded SessionDirectory shared by
  headless, CLI and TUI session list/search paths. Its transactional
  rename/fork/archive/restore/delete methods are shared by CLI and TUI; legacy
  CLI delete/clear also use that embedded service. Session Markdown export
  formatting and public activity wording now live in the application package;
  its Memory query reads only dialogue and allowlisted public events, never
  model_content. Terminal clients still own export path/no-overwrite handling.
  Legacy CLI delete/clear use reviewed turn/session counts rechecked inside
  SQLite's write transaction, rejecting cross-client changes before deletion.
  A KnowledgeReader is used by CLI raw queries/library listing and TUI
  knowledge tool results. Both reuse existing stores and retrieval without
  browser routes. The bounded Library inventory and reviewed artifact changes,
  typed TUI Knowledge action and trusted worker request construction (including
  effective URL Fetch routing), Knowledge operations,
  typed Research create/run/control actions shared by CLI and TUI worker,
  model connection definitions/reviewed writes and catalog/capability reads,
  write-only provider credential changes, typed private model activation and
  Utility requests, fixed Model Manager, dependency, serving-read, SSH diagnostic,
  key-setup and definition commands, private image-generation and Vision
  analysis/tagging requests, the client-owned serving process lifecycle, and
  the bounded subprocess owner now live in the application package. The shared
  fixed-operation worker dispatches existing Library, Knowledge, Research,
  Media, model, SSH, serving, MCP, Skills, Web diagnostic and Utility requests;
  CLI compatibility adapters keep terminal call sites working. The worker binds
  config/data roots before importing the application package. The coalescing
  atomic settings writer, ordered session/domain action writer, ordered MCP
  mutation writer, ordered Skills action owner and bounded installed Skill
  reader also live in the application package. The RFC M3 embedded-service
  exit gate is met for the currently supported chat/read browser surface;
  unsupported domain mutations remain unavailable over HTTP until their
  public authorization and lifecycle contracts are built in later milestones.
  Terminal review presentation stays in the CLI. CLI MCP enable/disable/remove
  and reviewed add/install use the writer's
  fixed effect logic through a synchronous embedded adapter; connected add
  requires nonempty discovered tool schemas. CLI refresh and OAuth logout use
  the same reviewed definition checks. CLI import saves an immutable preview
  snapshot through the shared writer, so a source-file swap at confirmation
  cannot change the imported definitions. OAuth login also uses the reviewed
  definition effect after credential storage and requires a saved access token;
  its interactive authorization remains in the CLI. An ambiguous definition
  save retains newly stored OAuth credentials for explicit inspection rather
  than treating the save as rejected. An opt-in private SQLite
  non-chat operation journal has cross-process
  admission, resource fencing, hashed intent and explicit unknown-outcome
  reconciliation. CLI and production TUI MCP definition saves use the journal;
  a registry reload cannot clear an unresolved fence. The TUI keeps chat usable
  but rejects MCP saves if the journal cannot open. Accepted non-chat requests
  cancelled or expired before their effect gate release their resource;
  started or cancelling requests remain unknown and fenced on expiry. A
  resource-scoped read identifies the exact fenced request after an owner
  session changes, without releasing it or exposing private intent.
  CLI and production TUI SSH add/edit/remove/default definition writes now
  use the same non-chat journal, with a private exact before/after witness
  recorded under the SSH file lock before atomic publication. Unknown writes
  stay fenced until `klaude model-manager ssh recover` checks the current
  definitions without replay. The TUI rejects SSH definition saves if the
  journal cannot open. SSH host trust/key enrollment is a separate multi-file
  path and does not use this definition journal yet.
  CLI worker and production TUI image-service settings saves now share a
  journaled, revisioned file effect. A lost acknowledgement retains the
  image-settings fence until `klaude library image-service-recover` confirms
  the exact prior or saved state without re-testing or contacting the image
  server. Existing generation job receipts/cancellation remain separate.
  Production TUI Model Defaults saves now fence their three owned chat-
  preference fields under the existing registry/preference/credential locks;
  unrelated preference edits do not invalidate recovery. An unknown role save
  requires `klaude model-manager defaults-recover` to compare exact prior/final
  fields without replay or model work. Other chat-preference writers retain
  their existing field-level compare-and-set semantics.
  TUI custom bearer-token and catalog-plan MCP installs submit disabled
  definitions through the ordered mutation writer; reviewed secret capture
  remains in the terminal flow.
  Journaled MCP definition saves persist private before/after HMAC witnesses
  before the effect gate, which the registry checks inside its file lock.
  The gate also rejects an unrelated direct/old-binary registry edit that
  would otherwise produce an unwitnessed merged result. An unconfirmed TUI
  save directs the user to `klaude mcp recover` before another attempt.
  `klaude mcp recover` reconciles an unknown definition save only when the
  current registry matches a witnessed state; changed or unwitnessed files
  remain fenced. OAuth login/removal additionally witness bounded private
  credential-file hashes and serialize token writes/cleanup with recovery;
  partial configuration/credential outcomes remain fenced until
  `klaude mcp recover-oauth NAME` verifies the exact reviewed final state and
  finishes the one credential deletion. OAuth login discovery and token exchange
  occur before definition admission; other credential changes and older binaries
  do not participate in the resource fence. Browser owner actions now support
  local and password-authenticated LAN MCP add-disabled, discovery/enable, disable and removal through this
  same witnessed journal; interactive OAuth and browser recovery remain deferred.
- `apps/cli`: Typer commands, Rich terminal rendering, deterministic command
  reference/help, chat loop wiring, tool display formatting, docs/session/memory
  CLI commands.
- Settings > Agents > Web search provides question-mark help buttons for Search
  provider, Tavily search depth and SearXNG URL; click, touch or keyboard
  activation opens the existing help in a native dialog with a single OK button.
  Escape dismisses the dialog and focus returns to its Help button. The same
  help is available for all Web pages and Research budgets settings, plus
  Execution limits. Search results
  has no help button.
- Settings retains Account, Theme, Agent, Models and Memory. Models opens a
  single-column Defaults overview with Connections and Image generation summaries;
  Manage connections, Connected models and Image generation are dedicated
  destinations under Models, restored by `models-screen` URL state. Connected
  models browses configured providers with search, connection filtering and paging;
  conversation selection stays in Chat. Primary default roles use whole-row model
  choosers; fallbacks, token tuning and Vision enable live in Advanced defaults.
  Each fallback uses the same full-width chooser row as the primary roles.
  Defaults and image-service drafts have independent Apply/Discard scopes and
  preserve the existing reviewed saves, recovery witnesses and current-chat runtime.
  Account shows read-only identity, Security and a separate Sign out action;
  password fields live in a native dialog. Memory puts its preference and saved
  text rows first, with overflow Edit/Forget actions and a shared Add/Edit dialog
  retaining review. These editors fill narrow phone screens and clear on dismissal
  or sign-out. Account, Agent, Models and Memory use compact, divided settings
  groups inspired by the saved GPT reference, adapted to Klaude Material roles.
  Theme retains its existing layout apart from the shared page-bottom actions.
- WebUI spacing follows the existing Material surfaces and a 4px-based rhythm:
  preserve responsive page gutters, inset text and controls within interactive
  rows, group related controls tightly and separate distinct sections. Check
  horizontal padding and alignment with long content at narrow and wide sizes,
  including safe areas and keyboard/focus geometry; do not stretch a phone
  layout or replace the established Material identity with a reference style.
- Dialog header close actions use the shared cross icon with an accessible Close
  label and tooltip. Model download/details dialogs follow the same top-right
  control; confirmation footer actions retain their explicit action wording.
- WebUI bundles Noto Sans Khmer locally as the Khmer fallback for UI, chat,
  readers and code, retaining the existing Latin fonts and offline font delivery.
- Assistant Markdown supports inline/display LaTeX with `$…$`, `$$…$$`,
  `\(…\)` and `\[…\]`, using bundled KaTeX 0.19.1 and native MathML.
  Code fences offer Copy and Download with language-derived extensions and optional
  `filename=…` names; HTML/SVG fences also offer Preview. The native viewer loads
  an owner-authenticated, short-lived passive document in an opaque sandbox with
  scripts, navigation and external resources blocked. Original downloads retain
  the exact displayed source. Markdown images offer Preview/Download; local and
  embedded raster images have inline thumbnails, while external images load only
  on explicit preview/download. Browser downloads are bounded and respect CORS;
  blocked sources retain their original link with visible save guidance. Common
  file links have Download and supported image/HTML/SVG Preview actions. Valid
  base64 raster fences download decoded image bytes. Preview/download work never
  claims chat control or imports Library files. Sign-out/session changes discard
  late results and clear private viewers. See `docs/webui/chat-output-validation.md`.
- Chat code coloring bundles Prism 1.30.0 with over 75 language grammars, including
  C/C++, C#, Python, GDScript, Java, HTML/XML/SVG, CSS, JavaScript/TypeScript and
  JSX/TSX. Common extension aliases, filename fences, case-insensitive names and
  `language-`/`lang-` prefixes are recognized. `jar` is a Java-source fence alias;
  binary JAR archives are not treated as text. JSX/PHP tokenize hooks restore
  embedded-language tokens before the existing bounded DOM-only span renderer.
  Slate alone maps Prism tokens to VS Code's current Dark+/Light+ syntax colors;
  the other palettes keep their Material role-based token colors.
  Vendor refresh resolves required, selected optional and modified grammar order
  from Prism's pinned metadata; its local manifest records all 80 components and
  bundle hashes. Unknown languages and oversized blocks retain literal source.
- `apps/webhost`: experimental `klaude-webui` loopback launcher, persistent local
  admin account, owner cookie/CSRF/Origin checks, public snapshot/SSE replay and a
  minimal chat and workspace page. Its shared Agent begins with only
  read/list/search/status/diff tools, lazy Knowledge/Skills/web reads and
  configured MCP calls with per-server Auto, Ask first and Deny controls in
  Integrations → MCP connection details. These update the same discovered-tool
  permission fields as the terminal, atomically with exact-definition and
  field-revision checks. New tools retain their own default (normally Ask first),
  mixed policies remain visible, and changes apply to future turns. Browser MCP
  calls honor saved Auto/Ask/Deny while preserving definition rechecks and fences;
  changing a setting never answers an already pending review. File edits retain
  their exact-review guard. Evidence: `docs/webui/mcp-permissions-validation.md`.
  M5 adds browser queue/steer/cancel,
  structured question replies, per-tab control handles and bounded workspace
  browsing, same-workspace session list/new/resume with exact saved-runtime
  checks, a live local Ollama model picker, and idle-boundary Standard/Thinking
  and Plan mode changes. Browser actions acquire session control automatically;
  there is no separate Take control step. Watching, polling and focusing a tab
  never claim control. Every authenticated owner client sees pending reviews and
  questions; explicit responses still use the fenced decision path. Hosted
  terminal review/cancel actions also reacquire automatically. Client drafts,
  action request IDs, session/revision checks and the single worker lease remain
  independent of control handoff. Submitted queue receipts remain available as
  history but do not block idle controls or appear as pending work. Model
  selection requires an exact configured catalog entry and fresh `/api/show`
  completion/tool declarations for native Ollama. Browser Thinking uses supported
  adapter efforts; native boolean Thinking retains medium. Configured local/cloud
  choices share typed revisioned runtime controls, and exact saved-runtime resume
  checks definition/credential revisions without catalog or generation calls.
  Model selection remains separate from connection definitions and default roles.
  Model changes are accepted during a hosted response and apply to the next prompt,
  including queued/paused prompts with the previous exact runtime binding. The
  current worker retains its original model/transport through completion, tool
  calls and cancellation. Revisioned desired selection is saved immediately;
  installation and credential/definition revalidation occur at the next idle
  boundary. Starting/submitted and already mismatched queue entries are not
  retargeted. Thinking/Plan retain their idle guards. Other worker leases remain
  fenced. Browser snapshots expose the next selected model and pending status;
  mobile/desktop pickers stay usable during generation, with an older-host fallback.
  Evidence: `docs/webui/deferred-model-selection.md`.
  An empty conversation can resume when it has an exact saved runtime and matching
  workspace binding; no dialogue is fabricated. Unknown sessions, missing choices,
  changed runtime identities and mismatched workspaces remain rejected.
  Browser snapshots declare Model Store, live catalog, Model settings and Image studio capabilities. Updated
  assets served by an older host show restart/reload guidance, link to Model
  settings and avoid unsupported endpoint polling or endless loading states.
  Model Store has Discover, Installed and Downloads navigation, using the exact
  Library/Integrations section-chips component: native aria-pressed buttons, shared
  keyboard navigation, responsive layout, selected colors and animated positional
  corner shapes. There are no Store-specific tab sizing or grid overrides. Installed and
  Downloads show shared count badges for the selected endpoint inventory and
  visible download entries, including observed transfers; unknown counts stay hidden.
  Discover defaults to the live Hugging Face GGUF catalog, with responsive Popular
  and Recently updated cards (complete rows near twenty items, deduplicated across the landing
  collections). Their See all lists use shared numbered pagination backed by the
  Hub continuation cursor and retain the selected page in Store history.
  Entering the Store or refreshing requests fresh metadata; cached cards stay
  available during refresh and provider failures. Search uses the live catalog
  by default, including cursor-backed pagination beyond the first 20 results.
  Changing a search cancels obsolete reads and clears results from the previous
  query immediately. Placeholders distinguish community, offline and installed
  searches. The bundled collection is an explicit offline filter and fallback
  when live discovery is unavailable; fixed editorial promotions are no longer
  shown on the default Discover page.
  Charts remains a Discover drill-down; legacy category URLs open the offline collection. Catalog/order/capability
  and installed-size choices use Library's shared dropdown filter chips beneath
  Search. Search uses the shared domain-toolbar field styling, 48px controls and
  4px action gap; filter-chip padding and alignment match Library.
  The Model Store heading links back to Discover, clearing drill-down, search,
  filter and paging state, including Popular/Recently updated See all views.
  Discover cards include a separate Ollama runtime badge using the shared
  platform icon; multiple enabled endpoints additionally show the selected server
  name. Creator/family icons remain separate. A Library-style plus button opens the exact-model download dialog
  with Escape/focus return. Endpoint selection appears only for multiple
  enabled native connections on inventory/job views and operation/detail dialogs.
  Downloads has a centered empty state with Discover models and no unused toolbar.
  Connections and the collapsed configured cloud/local catalog live in Settings →
  Models; the Store header omits Current chat/Model Defaults. Chat retains its model
  picker and the command palette's Switch model opens it directly. The configured
  catalog preserves activation, filters, shared paging and tab-local disclosure
  choice; sign-out clears private state. Old Connections URLs migrate to Settings.
  Discovery retains a dated, bundled three-family/four-variant collection with
  official sources. Popular and Recently updated preview grids adapt their card
  counts to complete rows near twenty items using the shared CSS minimum/gap and
  actual available width, including fractional widths. Bounded cursor reads fill
  missing slots after filtering/deduplication; Recent excludes only displayed
  Popular entries. At most four pages per collection are read, with retained pools
  reused across resize. Older hosts retain their supported 20-row cursor reads;
  See all and search grids request a complete-row page size near twenty items
  (bounded to fifty), with cursor caches isolated by size. Short/invalid/duplicate
  provider batches are topped up with at most four metadata reads. Unknown
  download counts stay visible without a fabricated rank. Page URLs retain their
  page size; a column-count change starts a new cursor chain at page one. User search
  text is sent to Hugging Face only when its catalog is selected. That source uses
  real repository download counts/recent updates and exact single-file GGUF
  variants supported by Ollama.
  Model details use a full Store page with Back: large local identity/logo,
  separate Ollama destination badge, model-card link and
  compact icon/text strip of known facts (unknown
  metadata is not padded with placeholder tiles). About precedes compact file
  choices with right-aligned sizes and a right-aligned footer button that says Choose model
  until selection, then Download with the formatted size. The hero action also includes the selected size. While exact files load, the disabled footer button says Loading. Generic placeholder About text is omitted; substantive source
  descriptions remain available. Hub pipeline/task labels are retained across
  discovery/detail reads and shown as Task metadata, separately from verified
  runtime capabilities. The footer owns the reviewed download action. Exact
  model references remain in the technical disclosure and install review. It retains lower
  technical/source links. The image carousel and its artwork, controls and layout
  observers are removed.
  Details retains one page scroll owner and the full-page reference composition.
  Choose model focuses the exact selector; the count reports available variants. After a choice the footer changes to
  Download. Only explicit selection can lead to the existing review. Installed activation and
  reviewed deletion remain separate. Variants reuse shared 20-row pagination;
  URL state retains the selected exact tag and History retains Store scroll,
  filters, selected page and focus. Unknown metadata stays unknown; source errors
  disable installation and offer an explicit read-only retry. Refreshing a detail URL
  restores the Store after the authenticated snapshot and reloads source details.
  Detail caches and
  DOM clear on sign-out. Evidence:
  `docs/webui/model_store/model_details/implementation-validation.md`.
  Charts describes Hub downloads, never Ollama usage. Cards place Updated
  beside download counts and repeat it in details, using the repository's actual
  timestamp or Unknown. Catalog requests explicitly expand lastModified; older
  metadata caches refresh on read while retaining their offline fallback.
  Metadata has a one-hour,
  timestamped private cache with visible stale/offline fallback. Split/projector
  files are excluded; unknown capabilities, size, license and device fit stay
  unknown. No model weights are fetched while browsing. Installed inventory uses
  the existing native Ollama manager and a revision-scoped, timestamped private
  offline cache. Installed uses shared rounded collection cards, with compact
  truncated names/full-name tooltips, plus shared numbered pagination and chevrons.
  Signed-in administrators on local or LAN browsers can review exact native-endpoint pulls
  and protected deletion through the existing operation journal and owned worker.
  Downloads use the shared rounded collection-card backgrounds, corner shapes
  and row spacing, retaining real file progress, durable targets and uncertain outcomes;
  cards show parameter count and size from exact cached catalog/installed metadata.
  Missing metadata stays unknown; a current layer total is labeled File rather
  than model size. Active transfers show estimated decimal MB/s from successive
  reported byte samples, resetting on stage/total/counter changes or stale gaps.
  Missing comparable progress shows an unavailable rate; no browsing weight fetch
  or model-name inference supplies these fields.
  shared native-manager pulls started in other Klaude clients appear as read-only
  observations. On a local standard Linux Ollama system service, bounded partial-file
  metadata checks also show recent external transfer activity, without guessing
  its model identity, byte progress or final outcome. Sparse preallocated file size
  is never progress. Observations cannot cancel, replay or reconcile a journaled
  request. Remote Ollama has no active-transfer-list API; inaccessible local
  monitoring is explicitly unavailable. Definite pre-effect failures and terminal
  native pull errors with fresh unchanged inventory now fail normally; transport
  loss, missing final events and failed verification remain unknown and fenced.
  Downloads uses compact rows: model/file name, one status or byte-count line,
  the shared thin progress bar and 44px icon actions. Connection names, exact
  references, errors and external-transfer explanations live behind an Info
  button in a shared native details dialog. Escape/outside dismissal returns
  focus; polling preserves dialog and row-control focus; sign-out clears it.
  There is no explanatory empty-state paragraph or permanent monitoring prose.
  Owned live downloads offer Stop. Finished/error entries offer Remove, which
  persistently dismisses history without deleting model weights or journal
  receipts. Dismissing an unknown entry leaves a compact Needs check row
  and its resource fence intact. Other clients' observed transfers stay read-only.
  Download byte progress uses the shared thin loading bar in the selected Theme
  preset, with explicit determinate values and observer/animation cleanup.
  Check outcome verifies the exact endpoint and private target witness without
  resubmitting. A stable standard local daemon generation newer than the unknown
  request proves the original server request ended: fresh exact prior inventory
  can then reconcile as Failed and release its fence. Replaced deletion digests,
  active workers, same/unknown daemon generations and unreachable endpoints do
  not provide this restart proof. Tagged native pulls also support exact HTTP
  handler-end evidence from the matching local daemon journal, allowing fresh
  prior inventory to resolve a stopped request without restarting Ollama. Stop
  rechecks delayed handler-end evidence for up to 30 seconds through the existing
  owner keeper; Remove also attempts this bounded read-only recovery. Missing or
  mismatched evidence keeps the unknown fence. No mutation is replayed. Native
  pull streaming uses its 1800-second read budget, independently of short metadata
  reads. Removed failed history stays gone.
  Transfer-monitoring details stay in the Info dialog rather than as permanent
  explanatory paragraphs in Downloads.
  Cancellation stops the owned request and keeps an unconfirmed
  fence until the requested inventory is witnessed. Starting model mutations is
  gated against hosted conversations and browser profile operations. Unrelated
  model pulls, including unknown stopped pulls, do not block chat or selecting
  another runtime. Admission verifies the private target against its journal
  witness before establishing independence; matching native pull targets and
  native deletion remain protected. Cloud chat is independent of native weights.
  The snapshot exposes actual chat blocking before submission and the composer
  keeps drafts with a direct Downloads or new-chat action when attention is needed.
  Capability-gated automatic turn admission chooses start/queue under the shared
  application lock, preserving one durable request ID across stale tab state,
  completion and removed/submitted queue history. Explicit start/queue callers
  retain their existing contracts. Evidence: `docs/webui/chat-admission-validation.md`.
  Account role,
  rather than listener address, authorizes model management. Downloads never
  select a chat/default model.
  Generated's Create image tab now contains a roomy Image studio with an explicit
  saved-service capability check, supported aspect-ratio presets, pixel dimensions
  and a native Advanced disclosure for width, height, steps and seed. It retains
  the existing generation review, receipts, cancellation, output recovery and
  Library storage. Generate again reuses at most twenty in-memory browser drafts;
  after reload, Generate another starts from the current draft without exposing
  historical private prompts. Sign-out clears these drafts. Chat's attachment dialog
  and mobile menu also open this same Image studio without leaving Chat.
  Settings → Models selects stable-diffusion.cpp or experimental Ollama with an
  exact installed image-model name. Ollama requires `/api/show` capability `image`
  and pins its `/api/tags` digest across review/submission/save; Vision alone is
  insufficient. It submits one bounded `/api/generate` NDJSON stream and saves
  only a validated PNG through the existing Library boundary. Stop closes the
  owned stream; cleanup remains unconfirmed, and lost Ollama output has no job-ID
  recovery or automatic retry. SD native jobs retain scoped cancellation/recovery.
  See `docs/webui/image-provider-support.md` for setup and validation.
  Settings → Models uses shared tonal Settings cards, grouped Library-style
  connection/model rows, a 48px Search/Add toolbar and icon refresh controls.
  Connection actions use the same icon context-menu treatment as Chat, with
  keyboard navigation, Escape/focus return and native outside dismissal.
  Configured models has a matching collapsible Settings card. Search stays local;
  existing connection/credential reviews, locks and saves remain authoritative.
  Evidence: `docs/webui/model-settings-components-validation.md`.
  Settings → Models keeps staged Apply/Discard for default roles and fallbacks,
  using a searchable native model picker with role-capability labels and shared
  numbered pagination. Enabled Vision requires a primary model. Image service
  Test reads capabilities independently of saving or generation and retains the
  result through background settings refreshes.
  Signed-in administrators can add disabled connections, edit routing/name/URL,
  explicitly choose saved-key authentication, test, enable/disable, remove and
  replace/remove write-only credentials. New local Ollama connections need no key
  unless authentication is selected. Interactive Codex login and arbitrary env
  variables remain terminal-only. Existing current-connection/shared-key and
  default-role protections apply. Connection changes use the shared definition
  service and fixed worker, with exact review revisions and witnessed journal
  effects. Unknown acknowledgements remain fenced until Check saved state
  compares exact local configuration/credential state without provider requests
  or replay. Secrets never enter public responses or plaintext journal records.
  Evidence: `docs/webui/model_store/implementation-validation.md` and
  `docs/webui/model_store/completion-validation.md` and
  `docs/webui/model_store/layout-v2-validation.md`.
  AI creator/model/platform icons use a centralized JSON registry in
  static/icons/ai/registry.json, bundled by scripts/bundle_ai_icons.py into
  ai-icons.js. LobeHub, Simple Icons and pinned first-party vectors are sanitized,
  licensed and hashed in the packaged manifest. Family icons precede creator
  icons; unknown or conflicting identities use the generic model icon. Runtime
  and API identity never substitutes for a model creator: Ollama/OpenRouter
  appear separately in the picker and Models catalog. Chat and AI Review use
  theme-colored masks; catalog marks use verified color variants when available.
  Native options remain text-only. The manifest explicitly allowlists served
  SVG names; unrelated files in static/icons are not published. Provider/family
  additions change registry data rather than selector rendering. Verified icon
  gaps and extension instructions live in docs/webui/ai-model-icons.md.
  Desktop Chat places its quiet Model split control in a compact header, with 32px faces
  and extended 44px hit areas. Either Model half opens the existing model picker.
  The centered conversation/composer column is bounded to 800px. Attachment plus,
  Thinking and Plan sit below the full-width input. Thinking retains XS split controls:
  its main action toggles the mode and its trailing selector owns effort.
  The effort selector directly lists supported levels as icon-bearing radio menu
  items with a selected check, using the header menu's tonal styling; there is
  no nested visible select. Keyboard navigation and Escape focus return remain.
  Thinking is hidden when the current runtime declares no non-off effort.
  Plan also uses an XS 32px face. Thinking and Plan share a tonal off state
  and filled primary on state, including both halves of Thinking.
  These controls preserve idle/queue fencing, revision checks and private model
  selection. Their top-layer selectors escape chat/sidebar clipping, track the
  visual viewport and support outside dismissal and Escape focus return.
  Stop occupies the composer's primary corner during a reply; entering a draft
  reveals Queue and Steer beside it. Narrow active composers omit their unavailable
  mode controls until idle. A passive native Conversation details popover retains
  permissions, status, current Thinking/Plan state and session identity, with
  Escape/focus return and navigation/session/sign-out cleanup. Transient errors
  use the shared toast stack. The welcome screen uses compact prompt shortcuts.
  Evidence: `docs/webui/chat-layout-validation.md`.
  Completed assistant replies include Worked for in their three-dot options menu,
  beside the timestamp and Branch/Retry actions, using the successful turn's recorded
  acceptance-to-completion duration; older records without timing stay unlabeled.
  The reply footer shows Avg tokens/s from the turn's reported output-token sum
  divided by total generation time. Provider eval timing is preferred; otherwise
  a measured model-request duration is used and identified in the tooltip. Tool
  waits are excluded. Incomplete token accounting omits the rate; no character
  estimate is used. Only numeric counters/timing persist in the completion event,
  so new replies retain the metric on reload without exposing provider payloads.
  Conversation search ranks names and full saved user/assistant dialogue before
  the workspace/archive result limit, with matching snippets and debounced reads.
  Tool records and private model content are excluded. This is local text ranking;
  conversation embedding/semantic indexing remains deferred. Older hosts retain
  the recent-title/preview fallback until restarted.
  Canvas opens code blocks or assistant writing into editable tab-local drafts,
  using a local request/output policy adapted from official ChatGPT/Claude guidance.
  Requested reusable drafts (including short emails), substantial writing and
  standalone code qualify. Tiny unnamed examples and ordinary Q&A stay inline.
  Revision follow-ups inherit the prior artifact context until an unrelated request;
  explicit use Canvas overrides size gates, while keep inline/no Canvas opts out.
  Header/menu Canvas opens an existing draft or the latest eligible artifact and appears only
  when eligible content or an existing draft is present. Sources appears only
  for parsed HTTP(S) references, including as replies update during streaming.
  Canvas docks beside Chat on desktop and uses a fullscreen native dialog on smaller
  screens. It supports multiple documents, syntax/Markdown and passive HTML/SVG
  previews, Download, Discard and Ask Klaude, which appends a revision request to
  the unsent composer. It does not automatically submit or edit workspace files.
  Drafts clear on session change/sign-out. The bundled chat-canvas.js uses the
  existing authenticated preview route and opaque sandbox without script access.
  Evidence: `docs/webui/chat-canvas-search-validation.md`.
  Trigger rationale and focused checks: `docs/webui/canvas-trigger-research.md`.
  `KlaudeToast.show` supports top (default) and bottom notifications, selected
  info/success/error appearance, a close button and a five-second fade-out.
  Hover/focus pauses dismissal; active duplicates coalesce and each position is
  bounded to five notifications. Toasts remain operable above native dialogs,
  honor reduced motion and clear on session change/sign-out. Chat and domain
  errors use this feedback; contextual form/recovery states keep their existing
  inline details. `static/toast.js` is bundled into app.js. Evidence:
  `docs/webui/toast-validation.md`.
  Busy conversation rows reuse the shared Generating indicator, retaining its
  node across list refreshes and its existing hidden/reduced-motion lifecycle.
  At widths up to 850px, Chat instead has one 56px app bar: tapping the Klaude
  title/model/mode subtitle opens a native searchable model sheet with connection
  selection, shared pagination and the existing revisioned runtime action. There
  is a shared compact brand across pages: its circular paw and title keep their
  horizontal positions while Chat raises the title and fades in the subtitle;
  leaving Chat reverses the motion, respecting reduced-motion settings. There
  is no separate model row. The empty composer is 104px and grows with its input.
  Mobile Send uses an XS 32px face and 18px icon with a 44px touch target.
  Search, context and conversation details move into the header menu, with tonal
  icon tiles, 48px targets and a divider before the user's account entry
  (circular initial, signed-in username and Account label); mobile
  sign-out lives in Account settings. At phone widths up to 560px, actual viewport
  contraction while editing hides bottom navigation and keeps the composer above
  the keyboard; focus alone leaves navigation visible. Desktop model selection
  uses the same searchable, paginated model list in a centered native dialog;
  mobile retains its bottom sheet. Both Model halves and command-palette Switch
  model open this picker. It stays open when resizing between layouts and retains
  existing revision/queue safeguards. `static/mobile-chat.js` is bundled into the existing app asset by
  `scripts/bundle_webui_loading.py`. Evidence:
  `docs/webui/mobile-chat-layout-validation.md`.
  Loopback clients may explicitly
  activate file edits only after the
  existing clean-worktree/branch check; `write_file` and `edit_file` then use
  exact allow-once/deny review with content preview and hash. LAN cannot
  activate or approve edits, and an edit-enabled host cannot start LAN preview.
  Shell and Git mutations remain unavailable.
  The right Context Panel has Agent Inspector and Library tabs. Its task summary
  stays above Activity/Changes/Details. Activity rows share Settings' rounded
  disclosure chevrons; lifecycle, tool identities, approval
  outcomes and timestamps come from the existing public session journal, with
  at most 320 recent events and an exact current-turn tool-call count. Verified
  native edits publish only workspace-relative nonsensitive paths, numeric line
  counts and allowlisted error classes; raw arguments, outputs and patches stay
  private. Changes never treats generated artifacts or general Git status as
  agent edits. Inspect reuses authorized workspace reads; Current workspace diff
  is explicitly the current uncommitted diff, including other edits. Missing
  token, plan-progress and subagent diagnostics remain unavailable. Pending
  approvals retain their single chat decision path. The panel preserves the
  user's open/closed choice across viewport changes and supports a phone drawer.
  Tapping its outside scrim on mobile closes it and returns focus to the header menu.
  Docked panel space is adjustable from the chat surface's two edges, with
  invisible resize zones and hover/focus grips instead of permanent dividers.
  Widths are saved locally, constrained to keep chat at least 400px wide, and
  temporarily clamped on smaller windows without losing saved sizes. Keyboard
  arrows/Home/End adjust chat width; Enter/double-click resets an edge and Escape
  cancels a drag. Drawer layouts keep their existing widths and hide chat resize
  controls. The Context Panel has no extra close button; its navbar toggle remains
  authoritative. Evidence: `docs/webui/chat-resize-validation.md`.
  Its Library has Current/All scopes, independent List/Grid/Gallery preferences,
  search, pagination and the existing authenticated preview. Current filters
  stored session ownership plus original Library IDs in up to 500 recent public
  attachment records and current unsent selections before counts/paging. Older
  descriptors without those IDs cannot establish a historical association.
  The scope's explanatory sentences are omitted. Current/All tabs divide their
  full row equally; search and view controls share the compact row below, without
  a refresh button. Failed reads can be retried by selecting Library again.
  File rows and tiles offer only Preview, without individual Attach buttons.
  The composer's Library picker remains available for keyboard/touch attachment.
  Gallery shares Library's file tile renderer, square thumbnails, compact spacing,
  filename overlays and month grouping. Native Library drags and the composer
  picker reuse exact artifact IDs/revisions
  through the existing unsent attachment pipeline without imports or submission.
  Context previews restore focus to their originating row. Evidence:
  `docs/webui/context-panel-validation.md`.
  The authenticated Library has two destinations: Uploads and Generated.
  Uploads contains imported Documents and Media. Generated contains
  saved Research reports and generated images. Both tabs use All types, Documents
  and Media filters; Generated Documents includes existing Research records,
  while Media retains generated images. The browser maps this category to the
  existing `research` read filter without changing stored kinds or record IDs.
  Legacy Research filter preferences/URLs migrate to Generated Documents.
  The shared bounded inventory filters inputs/outputs before counts, search,
  sorting and pagination: Research records and records in generated_images are
  outputs; names, model labels and AI tags never determine authorship. Both tabs
  reuse the existing List/Grid/Gallery, previews and reviewed artifact actions.
  Only Uploads offers uploads. Each tab restores its own active filters/search/page
  when switching; Library URLs remain authoritative for reload/back/forward.
  Generated empty states render in the content area below its toolbar, with an
  accessible status message and no empty list column header.
  Page-level collection empty states fill the remaining vertical content area
  and center their icon/text group. Shared flex/grid rules account for controls
  and footnotes without fixed heights; populated inventories retain their normal
  layouts, and short viewports can scroll rather than clip the empty message.
  Generated shares Uploads' always-visible Type, Status and Sort dropdown chips
  below Search; there is no expandable Filters button. The shared adapter uses
  the existing filter-chip face and native popover menus, with radio-menu choices,
  selected checks, arrow/Home/End/typeahead navigation, Escape focus restoration
  and outside dismissal. Native selects remain the internal value/change seam
  and the visible fallback if popovers are unavailable. Its 48px plus button
  sits to the right of Search and opens
  a native Create dialog with Image and Research tabs. Each tab contains its
  existing form and job history below it, preserving drafts when switching tabs
  and retaining explicit generation/Research reviews. Tabs support arrow and
  Home/End navigation. Closing, switching tabs, navigation or sign-out discards
  late preparation reviews; sign-out clears both drafts.
  Legacy Research tabs and Uploads report filters migrate to Generated. Existing
  kind=all API and CLI/TUI reads remain compatible. Missing source-filter support
  on a running old host shows restart guidance instead of mixing inventories.
  Saved/Archived is an independent status filter, not a separate tab.
  Imports detect supported images from bounded headers of the immutable upload;
  other files use Document storage, independently of the current filters. One
  unrestricted picker opens from the toolbar's labeled plus button in the shared
  native dialog style, with no type selector. The existing import review remains
  required; closing an in-flight import discards its late review. Compact Uploads
  toolbars use 48px search/action/view controls, with type/status/all sort directions
  in a single horizontally scrolling row of dropdown chips underneath Search,
  with its scrollbar hidden. Below the existing 650px content
  breakpoint, list column headers disappear and two-line file rows are 70px tall;
  desktop keeps sortable columns. List loading uses matching row placeholders.
  Explicit document/media API drafts remain compatible. Old saved tab
  selections migrate to file filters or Generated; section, type and status
  survive page refresh within the tab.
  Saving owner-scoped uploads to Library needs an explicit import review;
  previews/downloads never launch a host desktop opener. Tags, archive/restore
  and deletion use artifact revisions. Knowledge opens libraries into their actual
  active indexed sources and paginated chunks, including learned URLs, uploads,
  Library files and legacy FTS content. Sources sit beside chunks on desktop and
  in a compact disclosure on phones. Global and scoped literal text search match
  library/source identities and full chunk text without inference. An inert
  native reader preserves chunk whitespace, supports Copy and cross-page
  Previous/Next, and explicitly marks its 65,536-character display bound.
  Original upload/Library filenames label sources without changing their identity.
  Source and whole-library deletion require Cancel-focused reviews with exact
  counts, durable request IDs and a snapshot rechecked under SQLite's write lock;
  original files and installed Skills are retained. Late reads cannot restore
  obsolete content, and sign-out clears private views. Existing reviewed
  URL/text-upload Learn and exact managed-source refresh remain available.
  Evidence: `docs/webui/knowledge-browser-validation.md`.
  Uploads image previews recognize lossy VP8, lossless VP8L and extended VP8X WebP
  headers. Existing images missing stored dimensions derive them from at most
  64 KiB of private headers on read, without decoding pixels, rewriting the
  artifact or changing its revision. Recognized images imported as Documents
  retain their type and record dimensions for preview. Original inline-content
  responses retain their 8 MiB, 4-megapixel and 4096px-side limits. Evidence:
  `docs/webui/webp-preview-validation.md`.
  Uploads now offers List, Grid and Gallery with compact shared type icons and
  image thumbnails. Library images disable native image dragging to prevent
  accidental reimports; Context Panel rows retain their explicit attachment drag.
  Gallery filters supported PNG/JPEG/WebP/GIF before paging;
  date sorts group by month added. The store has no directory tree, modification
  times or capture dates; type/status are controlled separately and dates are
  labeled Added. List/Grid/Gallery controls share the heading action row directly
  before Refresh; the redundant Library breadcrumb is omitted.
  These are application sections, independent of the selected workspace's folders.
  View choice uses the existing sessionStorage
  navigation seam; allowlisted Library URL state owns filters/search/sort/page
  when present and supports back/forward. Leaving Library clears its URL state
  so refresh restores the explicitly selected application page.
  Native item details use a shared image-first viewer: a spacious desktop stage
  and collapsible details sidebar, or a fullscreen phone/tablet stage with a
  closed/partial/full details sheet. Existing tonal roles, Roboto, local SVG icons,
  expressive radii and motion remain authoritative. Image and file previews have
  one Close cross at the top right; the inspector header places its sidebar
  toggle immediately before File options. Hiding the inspector expands the image;
  sidebar actions stay in the inspector; a Details button below the picture
  reopens it when collapsed.
  There is no separate Expand image preview button or duplicate details Close button. Compact controls offer
  download and 1–8x zoom relative to fit; tapping the zoom percentage fits the
  image to screen, without a separate Fit button. The derivative remains bounded to
  2048px. Pointer pinch/pan, double-tap and fit-only swipe navigation complement
  keyboard zoom/pan/previous/next. Details gestures never navigate the image.
  Escape dismisses a menu/sheet before the viewer; closing restores Uploads focus
  and scroll. Metadata reports only filename, MIME, size, dimensions and Added.
  Inspector Details/AI Review use md3.io primary-tabs CSS and the upstream
  animated indicator, bridged to existing theme roles and native tab state.
  Tabs have 48px targets, 14px labels and a rounded 3px label-width indicator;
  keyboard selection, disabled AI Review and tab-local drafts/scroll persist.
  AI Review has a centered
  introduction, ghost tag action and a filled split Review button. Its three-dot
  action opens a native context/output-token dialog. Its empty
  question field retains the existing default prompt on submission.
  Beneath the introduction, a live summary shows the selected model and requested
  context/output token limits. Review settings can use the global Vision role or
  an explicit model for the current conversation only. Temporary choices stay in
  browser memory by session ID, survive switching image previews, and clear on
  sign-out/reload; global model defaults are never written. The catalog marks
  unknown image capabilities, and the worker still checks fresh capabilities,
  enabled Vision, exact model/connection/credential revisions and image identity.
  A temporary model has no implicit global fallback chain; selecting the Settings
  default restores that role's configured model and ordered fallbacks.
  Review settings has Reset default on the bottom left, alongside Done on the
  right. Reset clears the conversation's temporary model and restores the
  4096-context/512-output token defaults without writing global settings.
  The inspector has Details and AI Review tabs, with keyboard arrows/Home/End,
  separate remembered scroll positions and preserved form drafts. Details owns
  compact metadata (separate file type and MIME rows), source links, tags and
  existing Learn controls. AI Review is available for current saved images and
  shows the latest analysis, exact model-reference disclosure, creation/expiry
  metadata, Copy/Expand actions, latest tag suggestions and the question form.
  Context/output token controls live in the Review settings dialog; budgets and prompts
  retain their existing semantics. Analysis uses the shared allowlisted Markdown
  renderer, including literal HTML and safe links, without additional truncation.
  Expand opens a native full-review reader; Copy preserves the complete stored
  Markdown through the existing secure/HTTP clipboard paths. AI Review has an
  expressive empty state, full-width Review image action and an explicitly named
  Generate tag suggestions action. While reviewing, the empty-state layout shows
  the configured generating indicator and Generating review; the primary action
  becomes Cancel review through the existing cancellation endpoint.
  Fetching saved AI Review data reuses that centered layout with Loading AI
  Review… and the normal 48px circular loading indicator. The old inline loading
  row is omitted, and review inputs remain busy until the read succeeds or fails.
  Tag generation uses the same introduction with Generating tag suggestions
  and a Cancel tag suggestions action. Suggested chips appear immediately below
  Generate new tag suggestions and share Details' 32px height, padding and gaps;
  result metadata follows the tag-selection controls.
  Previous results remain stored for failure/cancellation. Clear beside Copy/Read full
  review removes local analysis results through the exact displayed review,
  retaining newer work, tag suggestions and the image itself. Clearing is an
  authenticated, Origin/CSRF-protected, idempotent private-result operation.
  Actual suggestions use wrapping multi-select
  filter chips and right-aligned Clear/Save actions. Clear deselects draft
  suggestions; Save retains selected-tag counts in its accessible label. Existing
  manual/AI tags are excluded case-insensitively; choices stay in memory through
  cancelled/rejected saves and require a separate reviewed save. Generate tag
  suggestions and Review image start directly on click without a confirmation
  dialog. Both retain the validated model snapshot, budgets, capability checks,
  continuation behavior and durable request tracking. Suggestions are never
  automatically stored. Pending/failed requests keep the previous
  review available until expiry; the open inspector/tab returns after reviews.
  The UI retains only the current image's cached results in memory, checks the
  existing 24-hour retention and clears private content on sign-out. There is no
  persistent history UI. Phone/tablet inspectors use the existing full-height
  sheet with one content scroll region, safe areas and handle/Escape dismissal.
  Evidence: `docs/webui/file-inspector-validation.md`.
  Readable text/code previews reuse the viewer header, scroll region, fixed
  contextual toolbar and details sheet. Bundled DOM-only Prism adds syntax
  highlighting and decorative line numbers; Markdown offers safe Preview/Source
  modes without executing uploaded HTML or fetching embedded images. Wrap is the
  default; No wrap scrolls internally. Copy preserves the bounded source text
  with its indentation, tabs and original line endings through the existing
  HTTP/LAN clipboard fallback. The authenticated detail projection adds optional
  source fields (16 KiB / 100 lines), with truncation/control-sanitization notices
  and complete-file Download. Legacy terminal lines keep their existing limits;
  older hosts retain that normalized fallback until restart. Empty files preview
  without error. Evidence: `docs/webui/file-preview-refinement.md`.
  Manual/AI tags use wrapping Material input chips and Show more. They reuse the
  shared 32px chip face, 8px corners and 14px labels; removable manual chips keep
  a 48px-high native close target in edit mode. AI and manual tags use identical
  colors and chip styling while retaining their stored provenance. AI Review's
  selectable tags and suggested-tag actions use the shared filter-chip button;
  selected AI Review chips use the shared secondary-container roles.
  Edit tags offers the same remove control for manual and AI chips. AI removals
  remain local drafts until Save tags submits directly without a confirmation dialog; Cancel restores
  them. The tags operation accepts a bounded, exact `remove_ai_tags` list alongside
  manual values and applies both in one revision-checked transaction, pruning
  only the removed tags' provenance. Remaining AI tags retain their origin and
  provenance. Old hosts without `library_ai_tag_edit` keep the draft and show
  explicit restart guidance rather than saving an incomplete change.
  Escape cancels tag editing, restores the saved tags and focuses Edit tags
  while keeping the preview and details sheet open, matching source editing.
  Details offers an inline
  manual-tag draft with removable chips, Enter/+ additions, case-insensitive
  duplicates and whitespace normalization, retaining its 20-tag/40-character
  bounds and explicit Save tags with no confirmation dialog. Opening it never runs inference;
  available backend suggestions add only to the draft. Source has compact
  Add/Edit/Remove actions, safe external links with visual URL truncation and an
  inline text editor for source notes or URLs. Add/Edit opens the source text in place; input
  saves on blur or Ctrl/Cmd+Enter without Save/Cancel controls, status copy or a review
  dialog. Enter adds a line; Escape restores the prior value. Notes and multiple
  safe HTTP(S) sources can share the text, and a committed blur save continues
  if the viewer closes.
  Source text uses the existing private artifact_links table, a 2048-character bound, control-character
  validation and the existing fixed, revision-checked worker. Shared Library
  inventory search also matches source notes and links as literal substrings,
  before pagination/counting, including the Context Panel's existing scope.
  Old stores stay
  read-only on browse; links are never
  fetched and private origin paths remain excluded. Archive/Restore and Delete
  live in the Details heading's native popover using the chat menu's styling/keyboard
  convention. Saved and archived files both offer a Cancel-focused permanent
  deletion review, with exact revision checks and no archive prerequisite.
  Preview metadata has a 24-item/30-second cache, invalidated on
  refresh, operations and sign-out. Source editing is disabled on older hosts.
  Gallery preview navigation crosses page boundaries without moving the grid.
  Library image derivatives use only authenticated typed IDs and exact revisions,
  bounded checksummed SQLite blob reads and the existing disposable decoder.
  Thumbnails fit 320px; expanded previews fit 2048px and existing delivery bounds.
  Image search sits immediately before Download. Clicking it activates optional
  cropping directly on the preview image, with the full image selected and an
  icon-plus-Search button at bottom center. Drag to select, move inside a crop
  or drag its corners to resize. Arrow/Shift-arrow keys move/resize; Home selects
  all, Enter searches, and submitting Search exits crop mode and restores focus
  to the image-search button. Escape cancels crop mode before closing the preview.
  No extra dialog, mode tabs or screen-capture permission is needed. Only Search
  submits the image or exact crop directly to Google's Lens upload form in a new
  tab, with no backend upload or public artifact URL. Preview pixels are bounded
  to a 2048px side and prepared PNGs to 8 MiB; crop preparation is debounced.
  Temporary pixels clear on cancellation, navigation, closure, session change
  or sign-out. A custom theme-colored image-search SVG and provenance live in
  static/icons. Evidence: docs/webui/google-lens-validation.md.
  Animated sources show frame zero. Browser derivatives and new attachment
  thumbnails preserve alpha instead of compositing onto white, and image stages
  use the surrounding surface without an extra backdrop. Model preparation keeps
  its existing RGB compositing default. Originals remain unchanged. The private
  15-minute LRU cache caps 128 entries/32 MiB with two decoders; owner/revision
  checks remain active for cached results. HTTP responses stay no-store.
  Implementation and evidence: `docs/webui/library-browser-validation.md`.
  Viewer implementation and evidence: `docs/webui/image-preview-validation.md`.
  Integrations navigation orders MCPs, Skills, then Knowledge while
  retaining saved or URL-selected sections. Connections now
  lists configured MCP servers and offers owner-reviewed remote add-disabled,
  discovery/enable, disable and removal. Its keyed compact rows share the Skills
  layout and confirmed-state switches. Clicking a row opens native details for
  status, transport, tool count, source and OAuth metadata; Enable/Disable and
  Remove server live there too. Pending/unconfirmed changes keep switches
  unavailable, while cancelled or rejected changes retain the confirmed state.
  Skills and configured Connections enable/disable switches apply directly from
  the click, without a confirmation dialog. Details switches behave the same way
  and keep their dialog open. Only these state changes use the direct path;
  add/import/removal and other actions keep their existing confirmation.
  While a toggle is pending, its row status reads Updating in place of
  Enabled/Disabled, without a second status line. Failures and unconfirmed
  outcomes retain their separate actionable notices.
  Successful Library/Integrations changes do not leave routine Saved banners
  beneath navigation tabs; errors, pending states and inventory limits remain visible.
  The direct path still prepares an exact backend snapshot and submits one durable
  request ID, preserving stale-write checks, pending locks and receipt polling.
  Lost acknowledgements retain their original ID and lock until resolved; they
  are never resubmitted automatically.
  Password-authenticated admin sessions can use these actions on both the
  local and LAN listeners. Bootstrap-only embedded hosts retain local-only MCP
  management. Both review preparation and submission enforce this rule; cookie,
  Origin/CSRF, idle-turn, fingerprint and journal checks remain in force.
  All/Enabled/Disabled filters combine with the name/description search and use
  shared md3.io-inspired filter chips: 32px outlined or selected tonal faces
  inside 48px native button targets, 8px corners, selected checkmarks and
  wrapping rows. MCP and Skills chips show All/Enabled/Disabled inventory counts,
  with `+` when their bounded inventories are truncated. No unconfigured-server catalog
  is exposed by the browser API. Only one filter is selected at a time. Empty Skills guidance
  appears in the list content, without a duplicate line below the navigation.
  Compact rows omit absent descriptions and show confirmed status, transport and tool
  count. Add/details dialogs use bounded compact layouts; successful updates
  remain visible after inventory reload. Filters and notices clear on sign-out.
  Evidence: `docs/webui/connections-layout-validation.md`.
  Skills, Knowledge and Connections use Library-style search toolbars with 48px
  plus buttons. Import Skill, Add to Knowledge and Add an MCP connection open
  their forms in a shared native dialog before the existing explicit review.
  Closing, navigating or signing out invalidates preparation so late reviews
  cannot reopen it. Knowledge text search is debounced; search fields retain
  Enter submission without a separate Search button.
  Evidence: `docs/webui/integrations-toolbars-validation.md`.
  Enabled cached schemas load at browser
  turn boundaries, default to exact review and recheck their definition before
  execution; unresolved definition fences suppress tool loading. Registry
  discovery, secret capture and interactive OAuth remain in the CLI.
  Knowledge retains inventories, text search, reviewed learning and source
  refresh, with its own status, responsive pagination and cancellable reads.
  `integrations=knowledge` URLs preserve selection/search/pages and browser history;
  old `library=knowledge` links and saved Library Knowledge selections migrate
  there. Switching between Knowledge and Skills preserves Knowledge state, and
  leaving the panel rejects obsolete reads while accepted work continues.
  Existing Library Knowledge HTTP services and CLI/TUI navigation remain compatible.
  Skills, Knowledge libraries and indexed sources use compact, keyed rows with
  20-item browser pages. Skills show a bounded description and confirmed-state
  switch; installation/index metadata and deletion live in a native details
  dialog. Switches apply directly, show pending operations and retain
  the prior confirmed value on failure. Unconfirmed operations stay unavailable
  for retry pending local inspection. Library search is debounced in its single
  field; Refresh deduplicates reads, retains active filters/view/tab/search/sort
  and keeps loaded content on failure.
  Refresh controls across chat, Library, Integrations, Models and Settings share
  the conversation refresh icon with descriptive accessible labels and tooltips;
  source refresh retains its exact review. Loading replaces the icon in place.
  Mobile navigation keeps Chat, Workspaces,
  Library and Integrations plus a native More menu for Models/Activity/Settings; desktop
  destinations remain visible. Allowlisted primary view URLs extend existing
  Library/Integrations history without clearing unsent chat text. Settings uses
  Account, Theme, Agent, Models and Memory tabs, showing one category at
  a time. Keyboard arrows/Home/End select tabs; the phone tab strip scrolls.
  Allowlisted settings URLs and tab-local storage restore selection on reload,
  navigation and Back/Forward. Tab changes preserve ordinary form drafts and
  discard obsolete preparation reviews; Account is absent on bootstrap hosts.
  Models groups Model Defaults and Image generation service in separate cards
  with 16px spacing. Former Images URLs and saved selections migrate to Models.
  The main Models destination browses configured connections and their existing
  bounded catalogs, with search and 20-item browser pages. Use model changes only
  the current idle conversation through the composer's fenced runtime action;
  Model Defaults opens Settings for new-chat defaults. Duplicate submissions are
  blocked while preserving the selected thinking effort. Failed refreshes retain
  loaded models; aborted/obsolete reads cannot restore data after sign-out.
  Legacy local-only hosts retain their catalog path. The subsequent Model Store
  adds reviewed downloads/deletion and Settings connection/credential management
  for admin accounts on local and LAN listeners. Serving and SSH remain terminal
  operations.
  Evidence: `docs/webui/models-page-validation.md`.
  Settings uses a compact heading, full-width cards and shared label/control
  rows with 10px vertical padding. Controls use bounded widths; narrow cards put
  the label above the control. Native container
  queries respond to the available card width, including desktop sidebars.
  At desktop widths (851px and above), Settings categories form a sticky vertical
  list on the left of the active panel. Smaller layouts retain the horizontal
  categories. The same tab controls preserve drafts, URLs/history and linked
  panels; their ARIA orientation and arrow-key direction update on resize.
  Desktop uses Up/Down, smaller layouts Left/Right, with Home/End in both.
  Settings navigation has its own container, separate from theme chips. Through
  850px it remains a single horizontally scrolling sticky row with an opaque
  Material surface and opaque selected tonal tab. Dirty Agent, Model Defaults,
  Image generation and Theme actions use the shared page-bottom dock on all
  screen sizes. On phones the dock sits above the measured bottom navigation;
  tablet and desktop docks span the main application area. ResizeObserver and
  visualViewport measurements account for viewport and keyboard changes, and
  scroll clearance keeps the final controls reachable above the dock. Clean
  bars and bars outside the active category or screen stay hidden. Each draft
  retains its own Discard, Apply changes, conflict and recovery behavior.
  Theme shows its actions only while appearance differs from the saved value.
  Evidence: `docs/webui/settings-structure-validation.md`.
  The Settings columns fill the available main area, with 24px outer padding
  (16px on phones), a compact 160px category list and the remaining width for
  content. Account, Agent, Models and Memory use a bounded single content
  column; cards and the Models stack use natural heights rather than filling
  the scroll region. Agent controls adapt to the available width; Model roles
  and fallbacks use full-width rows. Control pairs remain bounded and number inputs
  retain their smaller limit. Models separates available models, model roles,
  Utility/Vision options, fallbacks and image service setup without changing
  their backend save contracts. Short model-role labels stay beside their controls
  on narrow cards. Startup chat, Utility, Research and Vision labels have
  decorative 18px chat, wrench, search and eye icons from the local SVG helper,
  using the muted theme color and retaining their native input associations.
  Theme palettes use four compact columns, or eight when the
  card has room, retaining the existing swatches, theme tokens and Apply flow.
  Agent groups use native expandable sections, with Date and time and Execution
  initially open. Tools & Permissions pairs each supported browser read tool's
  availability switch with separate Auto/Ask first/Deny segmented radio controls.
  The first row shows the icon, name and switch; a muted description and native
  policy segments follow. Subtle dividers replace individual cards. Groups use
  two columns when the desktop content has room and one column on mobile or
  narrow cards, retaining 44px targets. Each radio group has a tool-specific
  accessible legend and native arrow/Space keyboard selection. Both changes retain
  independent field-level persistence. Disabled tools keep their
  draft/saved policy while approval controls are unavailable, and use the shared
  Discard / Save changes workflow. Auto retains the existing `allow` value,
  Ask first uses `ask` and Deny uses `deny`. Auto skips the tool
  prompt, not workspace/network protections. MCP availability stays in Connections
  and configured calls retain review; advanced rules link to existing workspace
  edit controls and explain mandatory edit review, LAN restrictions and unavailable
  shell/Git mutations. No edit, shell or MCP allow policy is added by this layout.
  Browser-native disclosure markers are replaced by decorative
  rounded SVG triangles that rotate with the native open state and use the muted
  theme color; click, touch and keyboard behavior remain native. Date and time
  offers an IANA timezone selector with Automatic
  following the host timezone. It uses the existing revision-checked settings
  save path and applies to future WebUI turns without changing the OS timezone.
  The browser now includes the local `current_time` read tool, allowed by default
  and governed by the existing availability/permission controls. It returns the
  current weekday, offset-aware local time, timezone and UTC time; an explicit
  timezone override does not change the saved preference. Browser prompts refresh
  clock context before every turn, replacing cached runtime clock lines while
  preserving machine/location metadata. Named zones use standard ZoneInfo DST
  rules and invalid names fail validation. No network service is used for time.
  Evidence: `docs/webui/date-time-validation.md`.
  Optional Utility/Vision fallbacks start collapsed below the primary model
  controls; their headings reuse the muted 18px wrench and eye role icons.
  Disclosure state and ordinary input drafts survive tab changes in the
  current page; sign-out resets disclosure state. Agent and Models switches stage
  drafts using the existing Material track. Integrations switches retain their
  existing immediate, exact-snapshot save behavior.
  Source/model values remain complete; long model labels truncate only visually
  and disclose their selected label in a tooltip. Existing token semantics,
  settings revisions and recovery remain unchanged.
  Evidence: `docs/webui/settings-tabs-validation.md`.
  Model Defaults automatically loads the selected connection's catalog on entry
  and connection changes; Refresh models repeats that metadata read. Its existing
  catalog route accepts `purpose=defaults` for per-role hints. Native Ollama uses
  bounded `/api/show` batches to separate completion, tool and image support;
  embedding-only models are excluded. Chat/Research require tools, while Vision
  does not. Utility, Research and Vision exclude known mandatory-Thinking models
  and unsupported adapters; unknown capabilities are verified when saving.
  Exact existing backend checks remain authoritative. Utility/Vision fallbacks
  share their primary role's choices. Saved references and unsaved drafts survive
  catalog changes; failed refreshes retain loaded models. No inference or default
  save runs automatically. Evidence: `docs/webui/model-defaults-validation.md`.
  The disabled-generation hint links Model Defaults to its card in Settings →
  Models, closing Create and preserving chat and generation drafts.
  Settings tabs, category headings and Agent section headings use decorative
  local outline icons while retaining their visible text labels.
  Agent and Models keep separate in-memory drafts across category and page
  navigation until Discard, confirmed save or sign-out. A category action bar
  shows unsaved changes and Discard/Save changes, replacing individual Review
  actions. Saves use the existing exact snapshot and durable operation APIs,
  sequentially; independent fields are not an atomic transaction. A terminal
  success and confirming settings read are required before clearing each draft.
  Settled Settings preparation tokens are released through the existing discard
  endpoint so a batch can exceed 16 changes without increasing the snapshot cap;
  durable receipts and running/unknown fences remain intact.
  Partial failures retain remaining drafts. Concurrent edits require Use saved
  value or Keep my change before another save. Lost acknowledgements keep the
  exact snapshot/request ID and expose Check save status; unknown outcomes remain
  fenced. Models retains exact saved-state recovery without replay or model work.
  Ordinary saves have no dialog; granting tool access, relaxing approval and
  enabling image service/Vision routing require a setting-specific confirmation.
  Availability and authorization remain separate backend checks. Theme keeps
  live preview with Discard restoring its last applied appearance and Apply saving
  on this device. Account and Memory retain operation-specific behavior.
  The draft module loads inside the existing `management.js` asset, before its
  Agent consumer and `media.js`. Do not add a new required script route: a
  long-running host can serve new HTML before its Python route allowlist updates.
  Draft copies use their JSON values without requiring structuredClone.
  Theme retains the existing `theme` navigation key/URLs and now includes
  Comfortable/Compact chat views. Comfortable preserves the existing transcript;
  Compact tightens message, paragraph, list, code and table spacing while keeping
  text sizes and 44px actions. The device-local appearance v1 preference adds
  optional `chatDensity`, defaulting missing/invalid values to Compact while
  preserving explicitly saved Comfortable and color/motion settings.
  Live preview, Discard and Apply include density;
  reload and cross-tab preference updates restore the saved choice. Density styles
  apply only inside Chat, preserving Library previews and the surrounding shell.
  Active Cancel turn and Steer controls float above the composer's right edge as
  accessible 44px icon buttons alongside the centered Go to latest control.
  They reserve no toolbar row; scroll-end spacing keeps final messages/queued
  content readable beneath the buttons. Existing turn/control actions are unchanged.
  Evidence: `docs/webui/settings-save-workflow-validation.md`.
  Settings has
  bounded Memory inventory/filter/add/edit/forget and automatic memory controls,
  plus reviewed shared execution limits, read-tool availability and permissions,
  Web search provider/result/depth and service endpoint settings, page-reader
  routing/fallback switches and saved Research budgets. Search/Fetch preferences
  and sanitized Memory/code-generation contexts refresh before each browser turn.
  File details offers reviewed Learn for current saved UTF-8 text/code, PDF/DOCX
  and Research reports. Learning checks exact revisions, saved status, bounded
  content and checksums before embeddings, retaining stable artifact source IDs.
  Text input is limited to 2 MiB; disposable PDF/DOCX extraction rejects truncated
  output beyond 32,000 characters.
  Field-level expected values reject stale saves while preserving unrelated
  terminal preferences. Prompt refresh loads current public facts and installed
  Skill metadata. Evidence: `docs/webui/feature-completion-validation.md`.
  Skills search/page URLs use bounded `skills-q`/`skills-page` fields and restore
  through refresh, tab changes and Back/Forward. Enlarged text wraps navigation
  labels and collection headings; the phone bar's intrinsic ResizeObserver
  reserves its actual height, retaining safe areas and native keyboard/viewport
  behavior. Collection controls expose their metadata as accessible descriptions,
  and Skill switches retain visible checked/unchecked cues in forced colors.
  Integrations exposes installed Skills, reviewed local ZIP/Markdown import,
  activation and deletion. Uploads uses stable 24-item pages across its three modes;
  grids use two/three/four/six columns and Gallery uses three/four/six. Month groups
  can end in partial rows. An eight-page, 30-second metadata cache avoids repeated
  reads when presentation changes and clears on refresh, operations and sign-out.
  Knowledge matches/sources and installed Skills use compact rows with 20-item
  pages, with filters applied before paging. Legacy card hosts remain readable.
  The browser composes at most
  two bounded reads without changing CLI/TUI store batches or requiring a host
  restart. Pagination follows the actual card capacity, and resizing preserves
  the page containing the former first item.
  Pagination keeps the first/last pages visible, with ellipses around the current
  range and chevron controls. Filtered totals determine the actual last page.
  Mobile shows up to five page numbers with 36–38px wide, 40px tall controls and
  wider pagination rows, adapting on resize; card pages reload only when their
  capacity changes. Pagination gaps use centered dots.
  CLI/TUI store batch sizes remain unchanged.
  Library and Integrations tabs show unfiltered totals in small leading pills,
  refreshed on entry, explicit refresh and completed operations. Bounded inventory
  counts use a plus sign; unavailable counts are omitted. Uploads and Generated
  count their own saved artifacts across all types using stored provenance.
  Integrations keeps Skills
  and Connections distinct; Connections shows the configured MCP server count
  and opens its working management panel in the browser. MCP remains the protocol/server term.
  Persistent Memory management lives under Settings; this includes the reviewed
  browser Memory operations added by feature completion work.
  Populated Library and Skills lists omit redundant per-page count summaries;
  delayed skeletons represent pending reads; status text reports empty results,
  inventory limits and errors.
  `application.library_management` owns bounded private
  reviews/snapshots and fixed owned workers with durable operation receipts.
  Accepted work survives page changes/logout. Worker loss is unknown and fences
  the resource; browser reconciliation remains deferred. These operations do
  not accept arbitrary host paths or write workspace files. Current v2 coverage:
  `docs/webui/coverage.md`.
  `/settings web` adds an owner-only detached host toggle. Desired state lives
  in private `config/webui.json`; a private Unix control socket reports status,
  reports stable sign-in URLs, and stops only the owning host.
  Enabled hosts restart on the next `klaude` launch and survive TUI exit.
  `klaude-webui` remains available as a separate foreground launcher. The
  optional LAN toggle binds a selected private IPv4 address to a separate HTTP
  listener with exact Host/Origin checks and a sign-in URL shown in the TUI.
  LAN defaults off; HTTP transmits chats, cookies and approvals without network
  encryption, so the UI warns users to use only a trusted private network.
  Both managed
  listeners use TCP port 50000. Settings can probe each listener locally and
  records a nonlocal LAN request as recent positive device reachability evidence;
  absent requests cannot identify firewall blocking. The wider
  RFC hosting lifecycle and browser mutation surface remain unfinished.
  The M4 host revokes browser sessions/bootstrap and denies
  pending/future browser reviews before a managed stop is acknowledged. Accepted
  chat turns drain before the host releases its runtime. Re-enable reports a
  still-draining owner promptly, and the settings toggle can retry stop if the
  preference is off while the host still runs. The Unix control protocol checks a
  version, same-account peer, process start identity and profile; it exposes bounded
  shared-session snapshot/replay, turn submission, exact read-tool review and
  cancellation for terminal clients. A pre-versioned managed host is recognized
  only for status and graceful stop after verifying its module command, account,
  process birth identity and held profile lock; settings retain Disable and show
  that re-enabling updates the host. Other legacy commands remain unavailable.
  Production browser authorization now uses username/password: a single local
  `admin` account has a generated 32-character initial password, salted scrypt
  hashes in owner-only `config/webui-accounts.json`, and a private initial-password
  file retained until password change. TUI `/settings web` → Account shows admin
  information and reveals/hides the initial password only on explicit selection,
  outside chat history. The Account page reads local storage independently of
  host status, remains available with hosting stopped or control errors, and
  Back/Escape restores focus to Account in Web UI settings. Login work is bounded to two
  verifiers and five attempts per peer / thirty globally per minute. Password
  changes and `klaude-webui --reset-admin-password` rotate the account revision,
  invalidating all browser cookies and SSE; accepted agent work remains owned.
  Bootstrap exchanges are disabled on account-enabled hosts. Embedded fixtures
  retain the older bootstrap seam. The browser header's Account shortcut opens
  Settings → Account directly. Password forms clear on leaving Account,
  leaving Settings or signing out; authentication epochs reject stale snapshot/error
  responses after sign-out. Foreground startup prints the credential-file path,
  never the initial password; local reveal toggles back to hidden. Account
  password changes revoke sessions, and sign-out returns to the sign-in form.
  The actual sign-in screen follows the supplied end-4 lockscreen: warm supplied
  blurred wallpaper, a live 230px cookie clock with date bubbles, a short quote and
  three bottom toolbar islands. All UI colors inherit Theme Settings' generated
  Material roles, including light/dark/system, preset/custom/image accents and
  palette variants, restored before sign-in by the existing appearance bootstrap.
  The wallpaper keeps its source image with a themed tint; text containers are
  opaque and floating toolbar opacity is bounded for readable contrast.
  Phone layouts put the full-width password on the
  bottom row below secondary controls. Through 768px, a two-row grid centers the
  complete clock/quote/status group in the space left above the natural-height
  footer, including any login notices. Safe-area padding and the existing
  visualViewport measurements keep controls above the keyboard. Compact regions
  hide decorations before the password; long feedback scrolls inside its own
  bounded area. Username and password remain visible in separate rows with the
  keyboard open, including compact layout-viewport resizing; hiding a focused
  credential must never dismiss the keyboard. Desktop positioning and clock sizes
  remain unchanged. Quotes
  rotate only on actual screen openings through a shuffled
  bag, persisted as public IDs locally when storage is available. The bundled
  collection has 19 source-verified English proverbs from the requested 30-row
  PositiveQuotation snapshot plus 50 clearly separate local Easter eggs (25 pop
  culture riffs and 25 memes), with accessible attribution and retained provenance;
  the visible English Proverb label is omitted.
  No quote request uses the network at runtime; missing data uses original Klaude
  copy. Source/license/curation and verification: `docs/webui/lockscreen-quotes.md`.
  The native password field retains autocomplete, editing and selection under a
  decorative seven-shape Material mask. Only lengths/offsets reach that layer;
  failures and timeouts clear the input. Missing vectors and forced colors use native masking.
  Pending submissions deduplicate and time out after 15s. Expiry returns to the
  locked screen, closes app overlays and keeps the protected shell hidden/inert,
  including through asynchronous splash completion. This is a login/reauth screen,
  not a local-only lock or a replacement authentication mechanism. Fixed public
  wallpaper/font asset routes are the only host additions. Reference/license,
  source mapping, browser evidence and platform limits:
  `docs/webui/lockscreen-validation.md`.
  Account files are protected from workspace tools/reads/search/diff. The generated
  first account stores role `admin`; legacy version-1 singleton admin files remain
  compatible without password reset. Authenticated sessions bind the server-owned
  username, role and credential revision and revalidate all three; role changes
  revoke stale sessions. Model Store writes/cancel/reconciliation, connection and
  credential management, Model Defaults/image-service saves/recovery/tests and
  MCP definition management require the current admin role on either listener.
  Non-admin accounts may browse models; they cannot gain management permission
  through loopback access or request-supplied role fields. Bootstrap-only embedded
  hosts retain existing loopback authority and cannot manage over LAN. This adds
  the role boundary, not multi-user creation or workspace ACLs; 2FA is deferred.
  Evidence: `docs/webui/model_store/admin-role-validation.md`.
  TUI settings display host/session/turn status.
  HTTP rejects duplicate authority/framing headers and caps concurrent request
  handlers. Authenticated browser uploads stage bounded private files with a
  per-profile quota and expiry; owner-scoped downloads verify checksums and force
  attachments. Logout and shutdown revoke staged files. The terminal chat path
  still runs embedded. Configured provider selection, supported efforts and
  workspace-scoped conversation rename/archive/restore/delete and bounded public
  Markdown download are now available. The conversation panel uses an Archive
  action for the current conversation at an idle boundary: after exact review,
  request/resource admission opens a new chat before the owned archive worker
  starts. Replayed requests do not open another chat; failure to start a new chat
  rejects the archive without starting its worker. Active replies and queued
  messages retain their existing guards. Reviewed deletion also works for saved
  conversations without archiving first; deleting the current idle conversation
  opens a fresh chat through the same admission path. The effect transaction
  rechecks the reviewed archive state, workspace and history, and refuses active,
  unresolved or queued work. Archived history and attachments remain restorable.
  The compact Conversation dialog saves names with Enter through the existing
  reviewed backend snapshot and durable receipt, without a second confirmation.
  Inline status reports pending/errors. A divider separates the name from compact
  Download .md, Archive/Restore and Delete actions share one evenly spaced row
  with identical quiet text-button styling; only Delete's foreground is red.
  Actions wrap on narrow screens; permanent deletion retains explicit review.
  Production hosts can keep up to four independent conversation applications
  running. Switching retains background Agents, runtimes, interaction brokers,
  queues and leases; idle instances are evicted before allocating another slot.
  The host's selected conversation remains shared across owner clients. Running
  rows have a reduced-motion-aware status icon, refreshed while work is active.
  New conversations preserve configured defaults or the source runtime choice
  using separate runtime objects. In-flight edit permissions remain with their
  original conversation, and LAN activation checks every retained application.
  Logout closes that client's interactions across applications; shutdown drains
  every application. Embedded hosts without a factory retain idle-only switching.
  Evidence: `docs/webui/conversation-dialog-validation.md`.
  The conversation panel also uses an Archive toggle for saved/archived lists;
  its drawer closes on outside tap or Escape,
  with no separate close button or status dropdown.
  Conversation rows use one centered 16px vertical-dot management icon; only
  conversation titles use overflow ellipses, never the icon button.
  Session lists use compact 36px rows with 2px gaps, a 36px search field and
  reduced vertical spacing around the drawer controls.
  Remaining model/domain settings and coding
  controls still need browser contracts. Switching idle sessions clears browser
  file-edit activation and requires explicit activation again; a background worker
  retains only its own existing activation and exact per-edit approval gates.
  The chat paperclip offers device uploads and revision-checked Library files.
  From device has a leading laptop icon, switching to a smartphone in the existing
  phone layout at 560px; From Library uses the Library navigation icon.
  Its Library picker reuses Library file-type icons, concise type/size labels and
  authenticated image thumbnails in compact rows.
  A message accepts four files or images within 32 MiB total.
  Selected and sent attachments use tonal file cards with filename, type and size;
  PDFs have a PDF badge and images show a decoded, metadata-free 128px thumbnail.
  Library descriptors include the opaque original artifact ID for conversation
  scope association, without origin paths, checksums or private content.
  New attachment descriptors and thumbnails persist with their dialogue row,
  survive reloads and forks, and share session deletion. Preview requests require
  owner authentication and the exact current chat; unsent previews also check the
  selecting tab. Public snapshots expose only descriptors, never thumbnail bytes
  or private model input. Text-only legacy records keep their literal transcript.
  Sent attachment cards open the existing file/image viewer with keyboard and
  pointer activation. Newly admitted messages retain checksummed originals in a
  separate private dialogue column (32 MiB total input, base64 storage overhead);
  forks copy them and session deletion removes them. Exact owner/session/message
  reads offer metadata-free bounded image previews, safe text/Markdown and
  extracted PDF/DOCX text, plus original downloads. These reads never select
  model_content or create Library imports. Older messages use their available
  Library original or retained image thumbnail; missing device originals need
  reattaching. Chat previews hide Library metadata management and file navigation.
  Library List/Grid/Gallery controls use separate 12px-radius buttons with small
  gaps in both the main Library and Context panel; only the selected view is filled.
  UTF-8 text/code and bounded PDF/DOCX extraction become private model input;
  public dialogue contains the prompt and filenames only. PDF/DOCX parsers run
  in disposable resource-limited processes. Images use the existing enabled
  Vision and exact active-model capability checks, pixel preparation and private
  artifact references. Library images reuse their original artifact ID and captured
  checksum without adding an Uploads record, including images stored as Documents
  or Generated. Changed/archived image selections must be chosen again; later chat
  image references depend on the original remaining available. Device images retain
  the existing private Media snapshots. Owner/tab/session-scoped selections expire
  after 30 minutes; logout and shutdown revoke them, while accepted turns retain
  their captured bytes. Text and image input hashes participate in durable request
  deduplication.
  Chat and Library Uploads accept device file drops over the main content panel.
  A shared theme-aware drop overlay uses local image/document artwork with an
  add badge, reduced-motion styling and destination/limit hints, without covering
  the surrounding panels.
  Only file drags are intercepted; text/link drags retain native behavior.
  The overlay clears on leave, drop, Escape, blur, navigation/session/auth changes
  and drag inactivity. Open dialogs and unrelated destinations do not accept drops.
  Chat drops use the same picker preparation and 4-file/32-MiB limits (all four may be images),
  preserve unsent text and never submit a message or import into Library.
  Uploads reviews each dropped file separately, up to 20 files per drop and
  32 MiB per file. Cancelling a review stops remaining files; accepted imports
  continue independently. Folder drops are rejected without traversal. Dropped
  batches are cancelled on navigation/sign-out; stale preparations cannot reopen
  reviews. This uses existing assets and APIs without requiring a new host route.
  Evidence: `docs/webui/file-drop-validation.md`.
  Attachments can be prepared during a reply; sending them waits for an idle turn.
  Sending does not Learn/index text or enable Vision. If the attachment script
  or server capability is missing, the paperclip is disabled with an explicit
  restart/reload explanation. Static assets can update before a running Python
  host; that host must reload before new attachment routes become available.
  Validation and format
  limits: `docs/webui/chat-attachments-validation.md`.
  Generated now has reviewed Research queue/start/stop and configured-image-
  service generation/cancellation/output recovery. These use existing typed
  Research/Image commands and durable stores; accepted jobs outlive navigation
  and logout. Research keeps saved provider/budget bindings and fresh evidence;
  image recovery never submits another generation. Ordinary management workers
  retain 180-second limits; Research uses its saved deadline plus 30 seconds and
  generation uses 330 seconds. Settings now exposes reviewed shared Model Defaults,
  ordered Utility/Vision fallbacks, Utility output budget, Vision activation and
  image-service test/save. Explicit Chat defaults apply to fresh chats/startup;
  unset or unavailable startup choices require model selection without generating
  through a replacement. Existing conversations retain their exact runtime.
  Research can use its separate saved role or the current chat model.
  Defaults/image-service saves use the same witnessed receipt as CLI/TUI and have
  reviewed exact-state browser recovery without replay or model contact.
  Library image details offers reviewed analysis and AI-tag suggestions, followed
  by a separate review of explicitly selected offered tags. Images stored as
  Documents retain their original ID/type. Source reads check stored size before
  allocation, revision and checksum. Tag writes recheck the operation fence inside
  the artifact transaction. Owned Vision requests use a 300-second worker limit;
  Stop releases their resource only after the owned process group is reaped.
  Private results stay outside chat/journal bodies, with 64 records, a 24 MiB
  SQLite cap and 24-hour availability; exact owner receipt/image revisions guard
  result reads. Broader domain reconciliation remains separate work.
  Media evidence: `docs/webui/media-controls-validation.md`.
  Evidence: `docs/webui/feature-completion-validation.md`.
  Its read-only workspace file and search tools use the shared application
  WorkspaceReadService, which caps underlying input/output, anchors directory
  listing and search to opened descriptors, and anchors bounded Git status/diff
  to the selected workspace descriptor. Protected secret names are hidden from
  browser directory listings and Git path output; Git redaction reads bounded
  secret sources and fails closed when they are unsafe or oversized.
  It stops owned processes at their output limits. Browser principal and
  workspace-grant authorization remain separate work.
- `packages/core`: config loading, Ollama HTTP client, system prompt, agent
  loop, permission gate, memory/session store, runtime context, follow-up and
  retrieval planning.
- `packages/tools_local`: workspace file, grep, shell, and git tools with a
  workspace jail, dirty-tree write lockout, command risk classification, and
  auto-commit support when writes are enabled. `read_file` accepts optional
  one-based `offset` and bounded `limit` for numbered later-line reads; an
  unpaged read retains its existing output. Underlying reads are bounded;
  paging rejects files above its scan cap, and the opened file identity is
  rechecked before use. Directory listing scans at most 2,000 entries. Shell
  commands prefer the active
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
A packaging job also builds all seven workspace wheels, installs them together
in an isolated temporary virtual environment, imports each public package, and
runs the installed `klaude --help`. Jobs use bounded timeouts and cancel
superseded runs. `make check` mirrors the local unit, lint, and production-type
validation surface; `make package-smoke` runs the separate distribution check.
The root `uv.lock` is tracked release input; update it deliberately whenever
workspace metadata or dependencies change, and keep CI installation frozen.
`.github/workflows/release-candidate.yml` is a non-publishing release gate,
started by manual dispatch or by pushing an alpha release tag (`v*-alpha.*`).
The tag trigger permits verified release preparation through Git push when API
authentication cannot dispatch workflows. It builds all seven wheels twice with
one source timestamp, validates their metadata and archive structure, requires
byte-identical output, writes
`SHA256SUMS`, creates GitHub/Sigstore build-provenance attestations with the
official `actions/attest` action, and uploads the verified candidate for 14 days.
Keep release actions pinned to immutable commit SHAs. Publishing to PyPI remains
a separate explicitly authorized operation.

## User-Facing Terms

The WebUI now shares **Klaude Expressive**, independently adapted from the audited
end-4 reference at `2f2a376fdb2ad738bf55f693dd0b474b64bb0ab8`. Semantic Google
Material Color Utilities 0.4.0 roles drive all sixteen presets, light/dark/system,
nine palette variants, custom accents and local image-derived palettes. Theme
retains versioned appearance preferences, live preview and Discard / Apply changes;
image pixels never leave the browser and only the extracted accent is saved.
Surface transparency is bounded to 0–50%; original files are not persisted as
wallpaper. The shared shell background uses a subtle 10% theme tint at the bottom
edge, fading to 4% within the bottom quarter so the lighter glow stays localized.
Phone section-navigation rows in Library and Integrations fill the available
width; buttons share each row's space and wrap when needed.
Shared grouped buttons and segmented radios retain expressive corners:
unselected row ends use 23px external corners (`--segment-outer-radius`, from
`--round-lg`), with 9px inner corners derived from `--round-xs`/`--round-sm`.
Selected segments are pills at every position. A shared layout observer marks
visible row ends after resize, visibility/content changes and font loading;
single-item rows get both outer ends. The pill radius uses actual half-height
for smooth 350ms shape transitions, alongside tonal selection and scale press
feedback. Small gaps (`--segment-gap`, 5px), reduced motion, native radio keyboard
behavior and multi-row palette wrapping remain. Account/Theme/Agent/
Models/Memory remain the Settings categories. Tools & Permissions keeps its
separate enable switch, Automatic / Ask first / Deny policy and staged save flow.
Generic button feedback retains component corners on hover and press; state
layers, ripples, focus rings and press scaling remain. Generic hover rules must not
interpolate a 9999px pill through the spatial spring: it can overshoot to zero
on exit and flash square. Selected session/tag corners use finite theme radii;
segmented selection retains its measured pill animation. Evidence:
`docs/webui/hover-corners-validation.md`.
Shared collection rows (Models, Skills, Knowledge libraries/sources and Connections)
keep their 12px inner and 23px outer corners through hover, focus and press.
Their full-row buttons, where present, inherit that geometry without pill morphing
or scaling, retaining tonal feedback, ripple and visible keyboard focus. This prevents
conflicting generic card/button transitions from changing the pointer hit area.
Evidence: `docs/webui/collection-shapes-validation.md`.
Models reuses the collection list's surfaces, icon tiles, spacing and row-end
corners, with a tonal current-model row and the existing explicit Use model
action. Catalog references, provider grouping and actual Thinking effort labels
retain their existing data and runtime-selection contracts.
Skills also shares Connections' All / Enabled / Disabled status controls and
keyboard navigation. Skills status and search filter the bounded inventory before
counts/pagination through the existing read route (`state=enabled|disabled`);
changing status resets the page. Allowlisted `skills-state` URLs restore the
selection alongside search/page history. Older hosts that cannot filter status
show restart guidance rather than an unfiltered page under a selected filter.
Enable/disable/import/delete still use their existing confirmed-state workflows.
Evidence: `docs/webui/skills-status-filters-validation.md`.
The Context Panel is closed by default and retains an explicitly saved choice.
Its Library retains Current / All scope. The main Library's Uploads and Generated
always span conversations and have no scope controls; legacy `file-scope`
preferences are ignored and `files-scope` URLs normalize to the full inventory.
Context Library rows and tiles open Preview without separate Attach buttons;
drag-to-chat and the composer's Library picker retain attachment access.
The shared Gallery uses 8px gaps and 23px corners in both destinations.
The command button and Ctrl/Cmd+K open searchable existing actions and resumable
sessions; Ctrl/Cmd+Shift+/ shows searchable shortcuts and Ctrl/Cmd+, opens Settings.
No command bypasses the existing runtime, session, review or permission handlers.
Workspaces renders the existing bounded d/f directory response as navigable rows,
retaining raw text for ambiguous listings and the server jail for every read.
Diff colors derive from actual diff prefixes. No host file writes were added.
The loader retains the Apache-licensed matched Google geometry with end-4's
800ms cadence, 12-second continuous rotation, 90-degree/350ms leaps, 750ms zoom
and 200ms smooth morphs. Settings also offers a classic spinner; system/app
reduced motion stops both. New shared runtime/colors are bundled into `app.js`,
and shared CSS into `style.css`, using the existing static routes. After edits,
run `scripts/bundle_webui_loading.py` and `scripts/bundle_webui_expressive.py`.
Source, licensing, deviations and evidence: `docs/webui/klaude-expressive-reference.md`,
`docs/webui/klaude-expressive-validation.md`, `docs/webui/klaude-expressive-progress.md`.


WebUI dialog close controls use the shared local SVG cross with accessible
names and icon-button styling, including conversation, attachment, message and
file-preview dialogs. Labeled Download and Archive/Restore actions place their
local SVG icon before the text and retain it across state changes.
All native dialogs share backdrop click/tap dismissal, including dynamically
created message dialogs. A press must begin and end on the exposed backdrop;
inside clicks, multi-touch, cancelled gestures and drags do not dismiss it.
Only the targeted dialog closes, using its existing cleanup/review-discard path.

The planned product WebUI must use Material Design 3 Expressive, with LineageOS
and end-4/dots-hyprland as user-requested visual references. Use cohesive tonal
palettes, expressive shapes, grouped controls and fluid, interruptible motion.
Preserve stable streaming/code reading, immediate approval/cancel actions and
reduced-motion support. The v2 planning spec owns the detailed design direction;
the initial Expressive shell now provides Chat/Workspaces, a tab-local Activity
view, responsive conversation drawer and activity panel, and browser-only
Settings → Theme. System/Light/Dark and sixteen palettes
(Slate, Lavender, Sage, Peach, Ocean, Rose, Teal, Amber, Crimson, Coral, Violet,
Indigo, Emerald, Lime, Sky, Cocoa) preview before Apply
and persist under a versioned localStorage key with same-origin tab updates.
Fresh or invalid browser preferences use Fidelity, Dark and Cocoa. Existing
saved selections remain authoritative. The live Theme preview contains a
scrollable, long syntax-highlighted Python example so palette token colors are
visible while changing themes. Material shapes and animated Material
wavy are the Generating indicator and Loading bar defaults. Theme's bottom Reset default action
previews all appearance defaults through the existing Apply changes / Discard
workflow, clearing any obsolete image preparation without changing other settings.
The Generating indicator selector has a live, themed preview using the shared
renderer for Material shapes and Classic spinner. It follows draft selections,
Discard/Reset/Apply and reduced motion; leaving Theme removes the preview so it
does not retain an active renderer in hidden settings.
The separate Loading bar selector uses the same progress component as the splash
screen, switching between thin and thick variants of Classic wavy static, Classic
linear, Material wavy static, and the vendored `material` 3.2.4 animated Wavy
preset. Weight is part of the selected reusable style variant rather than a
separate setting; Theme stacks both live samples and highlights the selected
weight. Existing saved thickness values migrate to the matching thick style.
The Material static bar uses the vendor geometry with a fixed wave phase,
resizing only when its container changes. The animated Material preset cycles
and stops under reduced motion. The splash uses the selected bar style at Thick
weight regardless of the saved style variant's weight; normal app loading uses
the selected Thin/Thick variant. The first Theme
preview also reflects Comfortable/Compact chat spacing as the choice changes.
Loading circle independently selects a 48px thin Material wavy static, Classic, or vendored
`material` Wavy circular progress arc. The static option uses the Material
progress arc geometry without animation; the animated option uses the bundled
factory. Both expose an accessible determinate component API and a decorative
51% preview. Fresh/reset and missing-field defaults use animated Material wavy;
explicitly saved choices, including the older static setting, remain unchanged.
The shared Loading circle renderer powers non-AI page loading feedback, including
Models, Libraries, Settings reads and operations. It follows the selected circle
style and rotates as an indeterminate indicator. The morphing Generating
indicator is reserved for AI work such as chat responses, image reviews and tag
generation.
The MIT-licensed progress factory and stylesheet are bundled locally into the
existing app assets with their license; no runtime network request is needed.
Theme Settings groups the chat and loading-bar previews in the left column; the
Generating indicator and Loading circle previews share a row. All controls are in the
right, with Reset default at the bottom of that column and Apply/Discard below
the studio. Generating indicator spans the controls row above the side-by-side
Loading circle and Loading bar selectors; Surface transparency follows below.
Color mode's System icon shows a monitor on wider layouts and the same phone
glyph as From device through the shared 560px phone breakpoint.
The custom accent swatch/value and Choose an image action stay on one row in
narrow Theme controls; the button label may wrap inside the button, while the
swatch remains aligned with the first preset palette column.
Narrow cards stack previews above controls. Palette density follows
the controls' own width, so a wide Settings card cannot squeeze eight swatches
into a narrow control column.
Slate uses neutral white/charcoal surfaces, accents, text and outlines. Cocoa
uses the original lockscreen's soft brown/beige family: its default
Tonal spot variant derives coordinated primary, secondary, tertiary and neutral
palettes from those reference colors while Material utilities assign role tones
and contrast. Other variants transform the warm brown seed normally. The saved
`cocoa` ID is unchanged; the swatch, app and lockscreen share the revised palette.
The palette picker uses four columns, or eight when the settings card has room,
with 44px swatches and coordinated light/dark roles for every preset.
Validation: `docs/webui/theme-palettes-validation.md`. Roboto and JetBrains Mono
plus their OFL licenses ship in the webhost wheel and are served locally.
The public loading asset restores validated appearance preferences synchronously
before the stylesheet and is also bundled into the deferred app. Startup keeps
the shell hidden/inert behind Klaude's logo and the shared 48px Material shape
loader until authentication and initial session/navigation reads settle. The
existing public loading asset includes the pinned geometry, initializes once
before the app downloads and mounts as the parser provides the splash slot. Its
thick progress bar advances to 90% over 800ms, holds there while startup is
pending, and completes only when startup is ready. The deferred app retains that
renderer; startup completion removes its indicator. App/system reduced motion
also applies here. Roboto is preloaded and splash copy stays hidden until the
font is loaded, preventing a fallback-font swap on screen.
Signed-out HTML starts with the chat layout hidden; failure reveals the existing
sign-in/retry state. The splash stays visible at least 500ms so its progress is
visible before the cover fades out in 160ms; it respects reduced motion and
offers Reload on a missing app asset or after 15 seconds without readiness.
Shared-message keyboard focus waits until the shell becomes available.
Validation: `docs/webui/startup-loading-validation.md`.
Assistant chat replies render CommonMark Markdown with tables, task lists and
strikethrough through a pinned local parser; user messages stay literal text.
User bubbles fit their content and align right, capped at the smaller of 85% of
the chat content width or 720px; viewports up to 600px use a 90% limit. Existing
tonal colors, corner shapes and Comfortable/Compact padding remain. Line breaks,
literal Markdown/code, long URLs and attachment cards stay within the bubble;
assistant replies keep their existing full-width layout. The chat scroll region
keeps an 8px gap before its thin, theme-colored scrollbar. All WebUI scrollbars
share this thin outline-colored thumb and transparent track through the shared
Expressive CSS; forced colors use native scrollbar colors. Intentionally hidden
mobile tab scrollbars retain their existing behavior. Validation:
`docs/webui/user-message-bubbles-validation.md` and
`docs/webui/shared-scrollbars-validation.md`.
Locally bundled Prism grammars highlight bounded code blocks, with code and raw
response Copy controls. Code headers keep an icon-only Copy control pinned
within their block during conversation scrolling, with checkmark feedback and
an accessible Copy code label. The DOM renderer disables raw HTML, permits only explicit
HTTP/HTTPS/mail links, and turns Markdown images into links without automatic
fetches. Completed blocks retain identity during streaming; selected/focused
blocks defer replacement, and terminal snapshots promote the partial article in
place. Streaming changes coalesce; oversized replies remain readable plain text.
The browser-only system instruction requests useful Markdown while respecting
explicit user formats. Source, stored dialogue, public snapshots and export stay
text. Vendor licenses/hashes ship in the wheel; refresh them only with the pinned
maintenance script. Validation: `docs/webui/markdown-chat-validation.md`.
Each assistant reply has a compact action row beneath it: icon-only Copy,
Read aloud/Stop, Share message, More options, and a book icon with Sources.
Read aloud uses browser speech voices in bounded chunks and stops when its
message is removed or the user signs out. Share opens a dialog with Copy link
and Share via. Links identify the selected saved message and its conversation
on the current Klaude server and require sign-in; they contain no bootstrap
token or copied dialogue. The dialog shows local WhatsApp, Telegram, Discord
and Email icons with text labels in a two-column app grid. WhatsApp, Telegram
and Email prefill the exact message link. Discord invokes the native device
share sheet directly from its click, with guidance to choose Discord there.
Browsers control which apps appear and cannot preselect the target. If system
sharing is unavailable or blocked, the dialog explains the restriction and
points to browser Share/Copy link; Discord never copies automatically. The three
social logos use pinned Simple Icons 15.13.0 paths with source hashes and CC0
license in `static/share-icons-LICENSE.txt`. Share via calls the native share
API directly from the click when available in a secure context. The app grid
remains usable when unavailable or denied. Native cancellation is silent.
Plain HTTP LAN origins cannot use the native sheet; localhost may. Opening a
conversation link waits for sign-in and
uses normal controlled, idle-boundary session selection. Reload retains the tab's
selected page after a link is handled. Message links focus, highlight and scroll
to their exact reply. The arrival border holds for three seconds, then fades
over 400 ms; reduced motion clears it after the same hold without the fade.
A session-scoped, bounded public-message read retrieves
older targets outside the recent window, with an explicit gap before recent
messages; it never reads provider/model content. Missing targets report an
unavailable message. Explicit session changes clear the old message target.
More opens an anchored, keyboard-operable
menu with the saved message's local timestamp, Branch in new chat and Retry.
Branch copies the conversation only through the selected saved reply and clears
browser file-edit activation. Retry stays in the same conversation, resubmits the
selected reply's original input through the normal fenced worker, and keeps
earlier responses in collapsed, keyboard-accessible Previous response disclosures
above the new streamed/saved answer. Durable response-group metadata hides the
repeat prompt in browser history, survives reload/reconnect, preserves prepared
private attachment input, and deduplicates uncertain request acknowledgements.
Retry retains current model/runtime, workspace, plan and file-edit settings and
the existing review gates. Both actions require cookie/CSRF/Origin, exact source
session, browser control and idle work/queue checks. Old hosts without the
in-place Retry capability show restart guidance instead of forking. Forks remap
response groups and reviewed deletion removes their metadata. Evidence:
`docs/webui/message-menu-validation.md`.
Sources lists deduplicated HTTP/HTTPS references linked in
the reply, with an explicit empty state; it does not claim verified tool-source
provenance. Actions wait for streaming to finish; unsupported speech stays
disabled with a descriptive title. These controls also apply to saved replies.
Browser reads use shared, request-owned skeletons after a 120 ms delay: initial
chat/history, session lists, local model inventory, Library/Skills cards, tab
counts, source lists, workspace reads, item previews and operation inventory.
Known content remains visible during same-context refreshes; changed contexts
clear outdated content. Library, Knowledge and Skills omit redundant Refreshing
status text while retaining refresh busy indicators and error messages.
Preview dialogs open immediately, and closing one rejects
late results. Busy state clears on completion/errors/sign-out, and old requests
cannot remove a newer loader. Workspace/session/model reads reject stale auth
results. Page loading uses the official Material seven-shape indicator beside
meaningful status text and static content skeletons. Its matched cubic morphs are
exported from pinned Google Material/AndroidX sources; a small SVG adaptation
uses the audited end-4 800ms cadence, 200ms morph, 90°/350ms leap,
12-second rotation and 750ms zoom. Contained
48px page indicators and uncontained 24/32px chat, refresh and operation indicators
use existing primary/container theme roles. One animation scheduler stops for
hidden content and system/app reduced motion; removed nodes release their state.
Chat retains real activity labels and static completion/error/input states.
When scrolled above the latest messages, the jump-to-latest button replaces its
down arrow with the same 24px Material indicator while chat is sending or working.
It remains a clickable 44px navigation button, restores the arrow when idle or
input is needed, and removes hidden indicators on reaching the bottom/sign-out.
Operation polls preserve active indicator identity. Static settings and live
work progress retain their real controls/status. Indicator geometry and runtime
are bundled into the existing external `app.js` asset so older running hosts
need only a browser reload. Send displays an immediate uncontained Sending
indicator inside the conversation output; chat activity uses a readable 32px
indicator below the user message and above the assistant response, retaining
its animation through snapshots. The composer contains no loading row.
Completed execution details remain beside that response. Their container has a
480px maximum width and shrinks to the available chat width, open or collapsed.
Hosts without typed
activity retain a Generating response indicator until idle or input is required. Failed sends
keep the draft and clear the pending indicator. Auth/session changes reject
stale send cleanup. Regenerate the bundle with
`python3 scripts/bundle_webui_loading.py` after editing its indicator sources.
Validation: `docs/webui/loading-states-validation.md` and
`docs/webui/material-loading-indicator.md`.
The navbar's leading hamburger toggles conversations on desktop and mobile.
Page refresh restores the selected page and Library/Integrations section after sign-in,
using allowlisted identifiers in optional sessionStorage; new tabs default to Chat.
Account is a circular username initial; Sign out and Send are icon-only with
accessible names (Send becomes Queue message while a turn is active).
Desktop composer Enter sends; Shift+Enter inserts a newline. IME composition,
modified/repeated Enter and disabled sends are guarded. Touch-only software
keyboards retain multiline Enter with the Send button available; desktop pointer
or non-touch devices use the shortcut. The keyboard hint is screen-reader text.
Chat places model, Thinking and Plan controls to the left of Send. The Chat title
is screen-reader-only; status and tool policy share the composer footer with the
session ID. Cancel and Steer occupy a compact top toolbar only during an active
turn, leaving no heading row while idle. The model picker closes on outside
clicks or taps and Escape; controls inside the picker remain usable.
When the conversation is at least 100px from its bottom, a floating Go to latest
down-arrow appears above the composer. It returns to the newest message with
smooth scrolling (instant with reduced motion or without scroll-end support),
then hides near the bottom. Scrolling by hand interrupts the jump.
New content preserves the existing position while reading older messages.
Compact phone layouts use native CSS
viewport sizing and safe areas; the browser owns focused-input keyboard scrolling.
They retain 44px primary touch targets, grow the composer within a bound, and
scroll reviews separately from the composer. Do not resize the shell from
visualViewport events or add an extra focused-input scroll adjustment.
Custom seed/image palettes are browser-local; unsupported domain controls remain deferred;
disabled navigation marks unsupported
screens. Browser smoke checks cover layout and interactions, not final product
or complete accessibility acceptance.

Settings groups are Interface, Models, Agent, Advanced, then Appearance. Web UI is
the first Interface row. Search is the first
Agent row, directly above Tools. Model Defaults is the public name; existing
`ai_defaults` storage/controller IDs and `/settings ai defaults` remain compatible.
`/settings model defaults` is the preferred spelling. Opening Model Defaults checks
live enabled endpoints for missing Chat/Utility/Research/Vision roles in an owned
metadata-only job. Local and already-selected compatible models are preferred;
declared parameter counts order remaining local choices, without claiming hardware
fit. Vision requires fresh exact-model image/Standard-mode verification. Empty roles
stay empty when no verified candidate is found. Existing choices and explicitly
saved inheritance/clears are preserved using `model_default_selections` markers in
chat-preferences.json. Ordered compare-and-save writes recheck endpoint, credentials
and disabled models; they do not enable Vision, change the active session, select
fallbacks, load models or generate. Scans cover at most 8 endpoints and 32 native
models per endpoint with 4 concurrent catalog reads, existing 8-model/4-read capability
batches, 40s scheduling and a 60s owned-worker bound. Leaving rejects unaccepted
results; accepted writes drain. Image generation retains its separate server setup.
Implementation: CLI default_model_selection/ai_default_settings, core ai_defaults;
evidence: `docs/model-defaults-navigation-validation.md`.

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
- `klaude library list/import/info/export/tags/archive/restore/delete`: manage
  private document/image copies, separately from knowledge libraries. Import
  copies one regular non-symlink file up to 32 MiB (`--type document|media`),
  retaining originals and launching no indexing/model work. List searches names,
  tags, MIME types and origins, supports type/sort/archived filters and bounded
  100-record pages. Exact typed IDs distinguish document/media/research records.
  Export creates a new file inside the current workspace, never overwrites and
  verifies stored checksums. Tags are manual; archive retains content; restore
  changes visibility; permanent deletion requires archive and confirmation.
  Originals, exported/opened copies and learned knowledge remain independent.
  Research reports use the same private store and artifact lifecycle.
- `klaude library analyze MEDIA_ID QUESTION [--context N] [--output-tokens N]
  [--yes]`: reviewed pixel analysis using Model Defaults → Vision on native Ollama,
  Anthropic Messages, OpenRouter, reviewed OpenAI Responses models or declared
  compatible HTTP endpoints.
  Vision starts disabled, with an explicit endpoint/model and at most three
  ordered explicit fallbacks. Selection checks exact-model declared image support
  through the shared core vision inspector: `/api/show`, native Anthropic model
  capabilities or compatible catalog modalities/configured native peers;
  model names never imply capability. Unarchived PNG/JPEG/static WebP/GIF sources
  accept up to 32 MiB, 40 megapixels and 32768 pixels per side. A fully decoding,
  bounded cancellable subprocess prepares private RGB derivatives, normalizes EXIF
  orientation/transparency and strips metadata. Source bytes remain unchanged.
  Prepared PNG/JPEG fits the request budget, 4 megapixels/4096 side and 7,500,000
  bytes; Auto uses at most 1024 side, detailed 2048, original 4096 subject to provider
  limits. Animated sources need an explicit frame in chat. Questions are private and
  at most 1000 printable characters. Back/No reviews show exact image/endpoints/
  models and budgets: default 4096 context/512 output, editable 2048–32768/128–2048.
  The shared owned worker and cancellable HTTP transport bound each attempt to
  90 seconds, with 3-second connects, bounded metadata/response/event/text reads,
  complete provider termination and no tools/history/indexing/tag changes. HTTP
  adapters reuse the chat runtimes with tighter 1 MB response/256 KB event/32,000
  text-character limits. Native Ollama allocates the reviewed context; HTTP
  endpoints use it as a conservative local input estimate, retaining server-owned
  allocation. Anthropic's 7,500,000-byte raw limit and declared context/output
  limits are checked before review/send. Thinking-required Anthropic models are
  unavailable to this thinking-disabled Media consumer, while chat retains its
  supported Thinking modes. Shared metadata/prepare/analysis worker bounds are
  15/120/130 seconds per applicable operation/model, retaining 90-second generation.
  Only
  reviewed network/temporary failures permit fallbacks; typed HTTPX statuses join
  the existing policy. Roles/image/endpoint/credentials are rechecked; Vision
  models/fallbacks are protected from disable/remove/deletion until changed/cleared.
  Native model deletion also protects compatible role references at the same
  normalized server root, including Vision and its explicit fallbacks.
  CLI exits 0/1/130 for complete/error/Ctrl+C. Library → Media → Analyze image
  provides private forms, Back-focused reviews, elapsed state, model/queue gates,
  cleanup-aware Cancel and bounded private results. Navigation retains accepted
  work; session/store changes reject stale results. Settings returns to the Media
  form retaining its question. Results are not saved, indexed or added to chat.
  Uninitialized role labels load through the existing owned defaults inventory,
  without reporting unknown settings as OFF or starting model work. Known
  redacted provider failures retain their actionable reasons through workers;
  full failure text wraps in the form, stale picker filters clear, and accepted
  questions/budgets remain available for explicit retry.
  Core vision and CLI vision_panel own S6a1; real qwen3.5:4b CLI/TUI pixel evidence
  and limits: `docs/s6a-local-vision-validation.md`. Installed local Gemma 4 E2B/E4B
  also passed real native one-shot/Media colors and screenshot reading, plus TUI
  source-deletion follow-ups, explicit model switching and process resume through
  the existing declared-capability path. No model-name exceptions were added;
  larger installed Gemma variants have metadata-only evidence. Scope, timings
  and limits: `docs/s6a-gemma-local-validation.md`. S6a2 also permits ordinary chat
  `/attach PATH`/inline `@PATH` and one-shot inline images when Vision is enabled
  and the explicitly selected active Chat model declares image support. S6a3a
  extends chat to native Anthropic Messages and compatible HTTP endpoints:
  fresh exact-model `capabilities.image_input.supported` or
  `architecture.input_modalities` evidence is required. An enabled, configured
  native Ollama peer at the same root/auth scope can verify an otherwise unknown
  compatible catalog through `/api/show`; explicit negative evidence is retained.
  Model inventories label Images as declared, unsupported or unknown; tool support
  remains independent. Model Defaults and Models settings additionally inspect native
  Ollama `/api/show` capabilities in owned metadata-only batches (8 models, 4
  concurrent reads, 20s per job, at most 1000 models per endpoint). Scoped results
  remain stable during browsing and are reused for 60s across navigation; refresh
  is explicit. Vision/text-only/tool/thinking/embedding labels follow declarations,
  never model names. Image generation/audio are labeled server capabilities, not
  additional Klaude consumers. Known non-vision entries cannot select the Vision
  role; unknown checks remain retryable and selection still verifies fresh support.
  Session/endpoint/credential changes reject stale results; leaving cancels work.
  Evidence: `docs/model-capabilities-validation.md`.
  Anthropic uses image-before-text native base64 sources,
  compatible requests use image_url data URIs. Anthropic bounds raw images to
  7,500,000 bytes; other existing PNG/JPEG dimensions/count bounds remain intact.
  Metadata verification is bounded, cancellable and cached for 30 seconds.
  Chat uses its own Runtime budget, with no model/fallback switch. It privately
  saves immutable Media snapshots associated with the session and stores bounded
  references in owner-only model_content, never base64 in public history/search/
  export. Source/preparation bounds match Media analysis; at most four distinct images are
  supplied per request. Restore/follow-ups retain pixels after source deletion;
  tags/archive preserve bytes, deletion/corruption removes availability. Endpoint/
  credential changes require reattachment; unsupported providers omit old pixels
  honestly. Request projection declares actual supplied pixels, counts dimensions
  for compaction/admission and retains tool pairs; recaps are not visual evidence.
  Preparation runs in the turn worker; cancellation wakes metadata/generation
  requests. Failed preparation retains attachments and an empty-composer prompt
  for retry; clean one-shot preparation failures exit 1. Stored snapshots may
  remain after later failure/cancellation and are managed independently in Media.
  Core chat_images/agent/ollama and CLI main own S6a2.
  The attachment reliability follow-up adds `/attach --detail auto|detailed|original`,
  `--frame N` and `--crop x,y,width,height`, plus explicit stored `media:ID` reuse
  and filename reactivation after source deletion. Only delivered image mentions
  are excluded from intent routing; coding and named text-file tools remain intact.
  Compaction and image admission share core request_budget, with verified cloud
  limits and a labeled 32768 unknown-cloud estimate, never a silent local allocation
  increase. Failed image attempts retain private references/question through retry
  and resume. Compatible/OpenRouter typed context failures allow one smaller
  preparation; short transient pre-output failures allow one bounded retry. Partial
  output, quota, auth and policy errors require explicit user retry. Actual routed
  model and allowlisted error type remain visible; failed preflight clears old usage.
  Private worker input uses an owned writer to avoid large-pipe polling deadlocks.
  Current evidence: `docs/image-attachment-reliability-validation.md`; historical:
  `docs/s6a2-chat-images-validation.md`. Core image_content/chat_image_support and
  the Anthropic/compatible runtimes own S6a3a; evidence and fixture/live distinctions:
  `docs/s6a3-http-chat-images-validation.md`. S6a3b extends reviewed Media through
  the same HTTP adapters and existing owned worker/settings/review flow; actual
  compatible Ollama and native Anthropic CLI/TUI fixture evidence:
  `docs/s6a3b-http-media-validation.md`. S6a3c adds OpenRouter chat and reviewed
  Media pixels. Fresh filtered catalog metadata must identify the exact model and
  declare image input and text output; declared context/output limits apply.
  Mandatory-reasoning models require an explicit Thinking chat mode and cannot
  serve the thinking-disabled Media consumer. OpenRouterRuntime delegates only
  image requests to the bounded cancellable OpenRouterImages HTTP adapter at the
  same endpoint/model/credentials; ordinary SDK text requests remain intact.
  Complete responses precede tool/private-reasoning publication on both paths.
  Catalog responses use the 1 MB metadata bound, separately from 256 KB stream
  events. Live free-model one-shot/TUI/Media/resume evidence and limits:
  `docs/s6a3c-openrouter-vision-validation.md`. S6a3d adds native OpenAI Responses
  chat/Media for two exact reviewed IDs: gpt-4.1-mini and
  gpt-4.1-mini-2025-04-14, only at https://api.openai.com/v1. Core image_profiles
  links official documentation and its review date; a fresh authenticated exact-ID
  lookup verifies metadata access before delivery. UI labels this evidence documented,
  distinct from live modality declarations. Unknown IDs/fine-tunes/custom URLs and
  Codex account auth do not inherit these profiles. These non-reasoning models
  require Standard mode; the request boundary also rejects unsupported reasoning
  or output above the documented limit after cached inspection. OpenAIRuntime
  uses OpenAIImageTransport only for actual image-bearing inputs, retaining its
  native Responses parser, stateless private continuation, tool pairs, cache keys
  and compaction. Compaction re-supplies approved older pixels without replaying
  the old task text; a recap is never pixel evidence. Transport bounds apply to
  streamed/nonstreamed responses and private state publishes after clean terminal
  completion. Positive streaming output limits are forwarded, with bounded image
  defaults. Quota envelopes are bounded/redacted and exhausted credit does not
  trigger a temporary-failure fallback. Metadata deadlines classify as timeouts,
  producing clean preparation failures instead of uncaught cancellation tracebacks.
  TLS CLI/TUI/settings/owned Media/cancel/resume fixtures passed; live OpenAI
  generation remains unverified because the account returned credit_balance_exhausted.
  Evidence: `docs/s6a3d-openai-vision-validation.md`. S6a3e adds native Gemini
  chat/Media images for exact gemini-2.5-flash and gemini-2.5-flash-lite IDs at
  https://generativelanguage.googleapis.com only. Official profiles and fresh
  authenticated model identity/generation-method/token-limit checks document
  support; metadata access does not establish generation access. Newer models,
  aliases and custom roots do not inherit support. Native inlineData requests
  retain explicit output, thinkingBudget and store=false with a 20 MB total
  encoded-request ceiling; no Files API upload or SDK automatic continuation runs.
  Image requests and their native continuations use core gemini_images; ordinary
  SDK text requests retain their existing path. Signed text/thought/function
  parts remain private, exact, model/root/key scoped and bounded to 512 parts/
  256 KB; compaction counts them and session restore retains them. Complete STOP
  and clean stream termination precede tool/private-state publication. Thought
  tokens join native image output usage, and shared HTTP Media usage now feeds
  the normalizer the complete metadata envelope. Existing Media ownership,
  thinking-off reviews, cancellation, explicit fallbacks and private results apply.
  TLS CLI/TUI/settings/Media/cancel/resume fixtures passed. Real generation is
  unverified: both tested IDs returned HTTP 404; Google explicitly restricts 2.5
  Flash to previously active users. No automatic newer-model substitution occurs.
  Evidence: `docs/s6a3e-gemini-vision-validation.md`. S6a3f extends exact reviewed
  native chat profiles to gemini-3.5-flash-lite and gemini-3.8-flash. Their explicit
  Thinking controls use thinkingLevel, with minimal/low/medium/high on Flash-Lite
  and low/medium/high on Flash; minimal is not thinking-off. Current profiles use
  the bounded native adapter from the first text turn, retaining signatures before
  a later image attachment. Unknown IDs and ordinary legacy SDK-only text paths
  retain their previous routing. Capability-derived session modes/efforts also
  apply to direct selection, restored sessions and TUI commands; minimal is bounded
  private session state. Standard-only Media, Utility and Research reject these
  profiles without generation; manual role selection cannot bypass the guard.
  Native parallel function responses share one user content block. An interrupted
  parallel round is omitted atomically, preserving the first function signature
  for complete rounds. Foreign/unscoped earlier tool results become explicitly
  historical text, without fabricated signatures or native call claims. Missing
  signatures in scoped current native call history fail explicitly. Real Google
  one-shot RGB analysis passed for both current IDs; Flash-Lite TUI read_file,
  signed continuation, source-deletion follow-ups and process resume/minimal passed.
  Existing request/image bounds and privacy/cancellation remain in force.
  Gemini catalog discovery retains its SDK client through lazy iteration, closes
  on every outcome and uses five-second/one-attempt requests. Current
  supported_actions and the older method field are supported; embedding/TTS/audio
  entries are filtered. The real catalog check returned 39 compatible models.
  Native request metadata resets before local validation, so rejected efforts or
  payloads cannot reuse successful usage from an earlier request.
  Evidence:
  `docs/s6a3f-current-gemini-validation.md`. OpenAI/native Anthropic paid generation
  and legacy Gemini access remain uncertified; S6a3 remains partial for that gate.
  S6b1 adds a separate OFF-by-default local image-service consumer, described below;
  S6b2 validates actual native CPU generation. The final S6 pass also validates
  native CUDA CLI/TUI generation on GTX 1650 using upstream GGML, explicit
  CUDA diffusion and CPU text/VAE/parameter storage; broader quality remains open.
  Optional S6c AI tags are implemented below.
  Session runtime state stores bounded model/mode/effort and
  captured connection/credential revisions atomically with accepted turns/settings.
  Resume restores that explicit choice without changing Default Chat or discovering
  catalogs; stale connections require new selection before sending. Fork retains
  state, archive keeps it, permanent deletion removes it. Historical sessions may
  recover Klaude's own model-setting events; dialogue never authorizes a selection.
- `klaude library image-service [--endpoint URL] [--provider sdcpp|ollama]
  [--model MODEL] [--enable|--disable] [--yes]`,
  `library generate PROMPT [--width N] [--height N] [--steps N] [--seed N] [--yes]`
  `library generation-jobs [--offset N]` and
  `library generation-status JOB_ID [--cancel|--recover|--refresh|--forget]
  [--abandon] [--yes]`:
  The native SD adapter connects an
  existing unauthenticated stable-diffusion.cpp native HTTP server. Settings →
  Model Defaults → Image generation owns the separate draft enable/endpoint/Test/
  observed loaded-model pin/Save/Reload controls. Library → Media → Generate image
  supplies the prompt, bounded dimensions/steps/seed and Back-focused review.
  Native capability checks precede acceptance; automatic sampler/scheduler defaults
  are retained by omitting those fields. One asynchronous job is submitted
  without retry, then polled for at most five minutes. One PNG up to 8 MiB and
  256–1024 pixels per side commits atomically with private provenance in the
  existing artifact store. Metadata/results are bounded to 512 KB/12 MB;
  connections/reads use 3/6 seconds, with the existing owned worker's outer bound.
  No model loading, arbitrary workflow, preview/batch, ambient credentials,
  indexing/tags or new agent tool is added. Model names are reported server
  identity, not weight attestation. Worker cleanup precedes job-scoped server
  cancellation; Confirmed/Unconfirmed/Not started remain distinct. Queued
  cancellation is required; running cancellation follows declared capabilities.
  Reviews warn when Cancel/deadline cannot stop remote inference. A rejected
  cancellation still checks the exact job; running_remote and completed_remote
  remain distinct from cancelled. Graceful exit
  checks cleanup; abrupt client loss can leave remote work active. Private job
  receipts retain local status and permit explicit cancellation without resubmission.
  Post-commit receipt loss recovers the existing artifact by unique job ID.
  Completion racing with Cancel is recorded as completed_remote, not cancelled.
  Explicit CLI recovery and the current TUI result's Review output recovery
  action use Back/No-focused reviews and the same owned worker/pixel/store checks.
  Recovery rechecks the exact receipt and original settings/capabilities, reads
  only the acknowledged remote ID and never submits generation. Repeated recovery
  returns the existing artifact; a receipt cannot restore deleted saved output.
  TUI recovery is offered only for an acknowledged job ID.
  S6b3 adds Media → Image jobs and a bounded private metadata inventory, 100 records
  per page and a 1000-receipt inventory scan bound. Exact IDs remain inspectable
  beyond that bound. Ordinary list/status send no network requests
  or prompt text. Explicit refresh checks only the acknowledged native ID without
  importing output, cancelling or resubmitting. Separate Back-focused cancellation
  and receipt-removal reviews retain exact endpoints and effects. Receipt removal
  requires an unchanged reviewed record; images/provenance and server jobs are
  retained. Unknown/active records require a fresh check or separate explicit
  abandonment consent (CLI --abandon, TUI unchecked confirmation). This discards
  local tracking only; remote work can continue and an active client can recreate
  its receipt. Terminal records need no abandonment override.
  Removing a receipt clears its stale picker filter and returns to the first page.
  Artifact archive/tags retain provenance; artifact deletion removes it but not
  independent job receipts. Native model-work gates and captured roots reject
  stale results; ordered settings saves drain independently of session SQLite.
  Core image_generation/library_artifacts and CLI generation_panel/
  generation_commands own this slice. Actual CLI/TUI fixtures and native CPU
  generation, queued/running cancellation outcomes and exact export passed. The
  final pass also validates actual CUDA CLI/TUI generation, while broader
  model/image-quality claims remain unverified. Evidence/limits:
  `docs/s6b-local-generation-validation.md`. Additional S6b services/auth remain
  extensions. Receipt history and S6c evidence: `docs/s6-completion-validation.md`.
- `klaude library suggest-tags MEDIA_ID [--save] [--select 1,3] [--context N]
  [--output-tokens N] [--yes]` and `library clear-ai-tags MEDIA_ID [--yes]`:
  S6c reuses the explicit Vision provider/budget/owned-worker boundary. Nothing
  tags automatically. Media → image detail → Suggest AI tags supplies a Back-focused
  pixel review, then initially unselected suggestions and an explicit selected save.
  CLI proposals stay unsaved unless --save is supplied; --select addresses numbered
  suggestions. Tags are bounded printable JSON strings, case-insensitively deduped.
  Manual tags and AI tags remain separate, searchable metadata. Existing manual tags
  are never overwritten; promoting an AI tag to manual removes its AI duplicate.
  Up to 20 AI tags retain per-tag model/endpoint/time/budget provenance privately.
  Clearing removes only AI metadata; archive retains it and artifact deletion removes
  it atomically. Old stores remain read-only on browse. Apply rechecks actual pixels,
  checksum, archive state and metadata revision; no model call, tool, chat history or
  knowledge indexing occurs during save. Interrupted saves require metadata reload;
  no rollback is claimed. Actual Gemma E2B CLI/TUI suggestions and selected save,
  three review widths, manual-tag preservation and clearing passed. Implementation:
  core image_tags/vision/library_artifacts and CLI vision_panel/library_commands.
  Evidence and remaining provider limits: `docs/s6-completion-validation.md`.
- `klaude research run QUESTION [--model MODEL] [--provider PROVIDER]
  [--rounds N] [--format FORMAT] [--queue]`, `research list [--offset N]` and
  `research resume JOB_ID`: bounded web research through the same owned worker
  used by Library. Queue saves metadata only, with at most ten queued jobs;
  jobs start explicitly. Capture Research/Chat defaults and endpoint/credential
  revisions at acceptance, never silently fall back. Completed/partial/error/
  Ctrl+C CLI outcomes exit 0/2/1/130 respectively. Resume re-fetches receipt
  URLs; saved metadata never substitutes for evidence. Core research and CLI
  research_commands/research_panel own this feature; evidence and limitations:
  `docs/s4b-deep-research-validation.md`.
- `klaude skills`: list installed assistant skills.
- `klaude search`: web search via the configured provider router.
- `klaude code-search`: search programming docs, examples, and debugging refs.
- `klaude huggingface-search/details/readme`: Hugging Face Hub integration.
- `klaude models`: list installed Ollama models and Klaude role assignment.
- `klaude model-manager list/status/pull/delete/hardware/search`: inspect and
  manage downloaded models on enabled Local native Ollama endpoints. List uses
  100-record pages (`--offset`); endpoint operations accept `--endpoint ID`.
  Pull/Delete confirm the exact model and server unless `--yes` is supplied;
  failures/unknown outcomes exit 1 and Ctrl+C exits 130. The shared fixed worker
  uses native tags/ps/version/pull/delete APIs without generation, service control
  or automatic model selection. Definition/credential revisions and installed
  digests are rechecked; loaded models and configured/session/default roles are
  protected from deletion, including normalized endpoint aliases. Metadata is
  bounded to 2 MB/1000 models, with 3-second connect/5-second read deadlines;
  streamed pull has bounded NDJSON events, a 30-second read stall and a 30-minute
  worker deadline. Safe progress uses an additive owned-worker protocol, retaining
  the existing final-result bound. Cancellation closes/reaps the owned worker
  request; shared/partial downloads remain Ollama-owned. Unknown outcomes require
  Reload rather than a rollback claim. HF GGUF discovery reuses existing private
  credentials; private pulls use the Ollama server's own access. Hardware uses
  existing local probes and makes no model-fit claim. Implementation: core
  ollama_manager and CLI model_manager/model_manager_commands. S5a is locally
  validated; S5b is described below and dependencies/SSH remain S5c. Evidence:
  `docs/s5a-model-manager-validation.md`.
  S5b adds `model-manager engines/servers/logs/serve/adopt` and Model Manager →
  Serve models for installed llama.cpp/vLLM engines and local weights. Serve stays
  foreground until Ctrl+C; TUI servers belong to their launching client and stop
  on its exit. Structured reviewed fields control name, executable, model path,
  loopback port, context and supported CPU/GPU settings. Cancellable 15-second
  preflight jobs bound help/device output to 512 KB, verify executable revisions
  and model metadata, and execute no installers. GPU offload needs observed engine
  devices; missing devices fail explicitly. Engines receive offline Hub/Transformers
  settings, no ambient provider keys, fixed argument arrays and no shell text.
  Lease-owned helpers supervise engines separately from disposable metadata jobs;
  a closed client pipe ends the server and cleanup rejects changed endpoint definitions.
  Terminal acknowledgements precede helper group termination. Cancellable raw log
  reads prevent inherited worker stdout from blocking cleanup after client death;
  supervisor exit classification waits for the process status after pipe EOF.
  A ready health endpoint, exact model ID and owned listener precede connection
  registration. Stop retains model files/roles/history and disables only unchanged
  manager-created definitions. Private logs are bounded to 256 KiB with 16 KiB
  tails, control stripping and credential-label redaction; they never enter model
  context. Up to two live servers per client and 32 retained records are supported.
  Explicit adoption requires the same account, matching tested executable and an
  isolated PID/session; failed adoption leaves the external process running.
  Adopted servers stop on client exit and retain their original log destination.
  Ubuntu/Linux ownership, live-engine limits and evidence are documented in
  `docs/s5b-managed-serving-validation.md`.
  S5c's first slice adds `model-manager dependencies/builds/build` and the
  Dependencies panel. It inspects existing CMake/Ninja/Git/C/C++ tools and
  installed engine flags, without generation or package installation. Reviewed
  CPU builds use an exact committed local llama.cpp HEAD snapshot in a fresh
  owner-only `data/model-builds/ID` directory; uncommitted source edits are excluded
  and existing engines/defaults stay intact. Back is initially selected; build
  instructions execute source code and require an explicitly trusted source review.
  Fixed CMake/Ninja arguments produce a Release CPU server with static llama/ggml
  libraries and supported accelerator/Web UI/fetch options disabled. This is not
  an OS sandbox for build code. Jobs default to two and permit 1–8; build deadline
  is 30 minutes, source bounds are 50,000 entries/256 MiB/32 MiB per file and links
  or special paths are rejected. Review requires 2 GiB free and execution stops
  below 256 MiB. Tools/commit identities are rechecked at acceptance; engine help
  must pass before a verified executable is published. Ready builds open a fresh
  Serve draft with Local model path focused; serving/selection remain explicit.
  Owned build work gates chat/Knowledge/Research/Utility and survives navigation;
  cancellation waits for compiler-group cleanup. Client loss is checked during
  build commands, retaining failed metadata and ending the owned group. Scoped
  read jobs reject late request/session/draft results. Engine probes inside owned
  workers inherit that group, so forced cancellation also kills a help/device
  child that ignores SIGTERM; standalone probes retain their own isolated group.
  Failed/partial files are retained, with at most eight builds and bounded private
  log previews. Inventory detects interrupted work and changed/missing executables.
  Reviewed removal is documented below. Build implementation:
  core model_dependencies and CLI dependency_panel/model_manager_commands.
  Actual source build, native model generation and TUI evidence:
  `docs/s5c-dependencies-validation.md`. Further S5c slices are described below.
  S5c engine recipes extend `model-manager build` with `--profile cpu|cuda`,
  `--architectures` and `--host-compiler`; add `model-manager install-vllm
  WHEELHOUSE [--python PATH] [--yes]`. Dependencies exposes separate CPU/CUDA and
  NVIDIA vLLM recipe forms, Back-focused paged reviews, shared retained setup
  inventory/logs and explicit engine-aware Serve handoff. CUDA uses installed NVCC
  supported-target discovery and a bounded fixed-code compiler probe; target IDs
  are explicit or come from observed GPU compute capabilities. Unsupported host
  compilers fail rather than using an override flag. CUDA builds retain the same
  snapshot, static library, 1–8 job and 30-minute deadline conventions as CPU.
  vLLM uses one complete trusted local wheel closure, selected installed Linux
  Python 3.10–3.13 and installed uv. Discovery honors the absolute `UV` launcher
  supplied by `uv run`, including managed tool caches, or searches the existing
  standard locations when unset. Owned metadata workers retain this non-secret
  hint; executable resolution/fingerprints and review rechecks still apply.
  Build/install subprocesses retain their restricted PATH and omit provider keys.
  Bounded ZIP/metadata/hash checks and offline
  dependency/platform resolution precede persistent writes. At most 128 wheels,
  2 GiB per wheel, 8 GiB compressed and 32 GiB expanded are accepted; disk review
  requires compressed + twice expanded + 2 GiB free, with the shared runtime disk
  floor. Fixed commands create a fresh venv and install only copied wheels with
  no index/config/cache, binary-only and exact-version/hash requirements. No
  interpreter download, system/app environment mutation or driver installation
  is performed. CUDA backend/version and required engine help precede publication;
  setup checks never certify GPU inference or model fit. Source/wheel/tool revisions
  are checked again at acceptance; partial/failed/cancelled setups are retained.
  Owned work gates model jobs, rejects stale page/session/editor results and reaps
  helper groups before queue consumption. Wheel/package/build code requires trust;
  this is not an OS sandbox. Core model_dependencies/model_recipes and CLI
  dependency_panel/model_manager_commands own this slice. Native compilation,
  fixture versus real-runtime limits and regression gates:
  `docs/s5c-engine-recipes-validation.md`.
  S5c retained setup removal adds `model-manager remove-build ID [--yes]` and
  Dependencies → Built/installed engines → Review removal. Read-only reviews show
  exact UUID/directory/recipe and estimated uniquely linked storage; confirmation
  defaults to Back/No. An owned 120-second mutation rechecks bounded tree/metadata
  revisions, current/saved/configured/default/Utility/Research selections and
  endpoint aliases, active workers/helpers and accessible same-account process
  executable/argv/cwd/maps/open-file references. Protected Linux processes produce
  an explicit incomplete-inspection warning, not a universal removal lockout.
  Local server acceptance and build creation share the inventory lock; removal
  also locks connection definitions and preferences. Descriptor-relative traversal
  rejects unsafe ancestry, mounts, special files and foreign-owned entries; venv
  symlinks are unlinked without following targets. Trees are bounded to 100,000
  entries, depth 64 and 25 seconds of review. Original source/wheel folders,
  referenced model weights, roles, server history and other setups are retained.
  A removing record prevents partially cleaned environments from being served;
  cancelled/failed cleanup reports partial effects and needs a fresh review.
  Cleanup reaps its owned worker before new model work; Ctrl+C exits 130, verified
  removal 0 and failures/unknown outcomes 1. Core model_setup_removal and shared
  dependency CLI/TUI workers own the behavior. Validation/limits:
  `docs/s5c-setup-removal-validation.md`. Remote GPU/vLLM/adoption extensions
  are implemented below; S6a1 native Vision is documented above.
  S5c's SSH slice adds `model-manager ssh list/add/test/inspect/default/remove`
  and Model Manager → Servers. Reviewed private fields retain only name/host/user/
  port, absolute key/known-hosts references, model directory and an opt-in agent
  flag. Saving never connects or changes model roles/HTTP endpoints. A separate
  diagnostics default drives Inspect default server; removing its definition
  restores This machine and retains remote files/processes/local keys. Ordered
  settings writes drain independently of session SQLite. Nonce/default revisions
  and captured request/root/session/draft/target state reject stale writes/results.
  Checks use the existing owned worker, installed OpenSSH and remote Python 3;
  strict existing host-key trust and public-key authentication disable prompts,
  ambient SSH configuration/proxies, multiplexing and forwarding. Agent use is
  explicit. Fixed quoted code receives JSON stdin, uses a 7-second remote alarm,
  3-second connect/10-second operation/15-second outer deadlines and 64 KiB output.
  CPU/RAM/disk/model-directory/process metadata is bounded and sanitized, without
  model loading or remote mutation. GPU stays Not checked; observed processes do
  not certify ownership. Connection retests preserve original inspection ages;
  failed checks/edited definitions invalidate old data. Up to 32 definitions,
  100 model entries and 32 observed processes are supported. Cancel/navigation
  reaps owned checks; accepted saves drain. Shared explicit table sections align
  read-only/action rows while controls remain above inventories. Extra installers
  remain pending; real loopback OpenSSH CLI/
  TUI evidence and limits: `docs/s5c-ssh-validation.md`.
  S5c remote CPU serving adds `model-manager serve MODEL --ssh-server ID
  --executable REMOTE_PATH --port REMOTE_PORT --local-port TUNNEL_PORT` and
  Servers → saved server → Serve model. Private reviewed fields use installed
  absolute llama.cpp executables, regular GGUF weights inside the configured
  remote directory, CPU threads/context and explicit remote/tunnel loopback ports.
  Reviewed remote adoption and the vLLM extension are described below. Prepared
  flags are reused; definition,
  credential, executable/model revisions are checked before execution/publication.
  The existing ServingJobs/helper owns the SSH channel and a self-contained remote
  supervisor; no second scheduler or remote installation is added. Heartbeats renew
  a six-second remote lease. EOF/client/helper/channel loss ends the owned engine
  group, with bounded TERM/KILL and live-group checks before confirmation. Not
  started, Confirmed and Unconfirmed cleanup remain distinct; lost channels disable
  local endpoints without claiming a remote receipt. One daemon health check per
  side prevents HTTP from blocking heartbeats/cancel. Exact model ID, owned remote
  listener and owned local tunnel precede endpoint registration. Startup/cleanup
  use the existing model-work gate; ready servers retain two-server client ownership, endpoint equality
  cleanup, private redacted logs and explicit model selection. Cancel loading is a
  visible local/remote startup control; ready Stop uses Back-focused review. Long
  reviews support PageUp/PageDown with Back still selected. Shared port probes use
  SO_REUSEADDR for TIME_WAIT while rejecting live listeners, allowing immediate
  restart. Fixed SSH preflight requests retain config_dir in both CLI/TUI paths.
  CLI remains foreground; Ctrl+C exits 130. Owned remote CPU serving/real inference
  evidence: `docs/s5c-remote-serving-validation.md`. GPU profiles are described
  below, followed by reviewed remote adoption.
  Remote llama.cpp GPU profiles add the existing `--gpu-layers N --gpu IDS`
  controls to SSH serving. Layers 0 keeps CPU; 1–999 explicitly requests offload
  to up to eight distinct indices from the tested remote engine device list.
  Bounded `--list-devices` checks provide at most 32 validated device names;
  unavailable/unknown devices never authorize GPU launch. Help/device checks
  share an eight-second probe budget; device reads use four seconds/64 KiB.
  Review reuses verified flags and refreshes devices; acceptance refreshes again
  and rejects lost/reordered inventory or changed selected names before loading.
  Engines receive exact --device names and --n-gpu-layers arrays with no ambient
  GPU overrides/provider keys; no CPU fallback or model selection is automatic.
  Request metadata, progress and bounded specific preflight/launch errors stay
  separate from actual allocation/inference proof. GPU availability/fit is not
  inferred from system diagnostics or help flags alone. TUI mapping sits beside
  GPU fields; forms/reviews page long content, retain short selected values and
  never move safe Back focus at paging boundaries. Cancellation immediately
  reaps checks rather than waiting out their deadline. Existing owner lease,
  tunnel/health/model checks, cleanup, two-server cap and model-work gates apply.
  Real native CUDA over loopback SSH and fixture/TUI/regression boundaries:
  `docs/s5c-remote-gpu-validation.md`. Physical LAN hosts and other GPU backends
  remain uncertified extensions; vLLM/adoption follow below and S6a1 Vision is documented above.
  S5c remote vLLM adds an explicit Engine choice in the saved SSH serving form.
  Installed absolute Python-console vLLM launchers and local regular safetensors
  directories are reviewed; serving executes no installers or Hub downloads.
  GPU IDs map to fresh remote NVIDIA UUIDs, with CUDA availability/capabilities
  checked in that launcher's exact environment, preserving venv interpreter paths.
  Unsupported/missing CUDA and incompatible BF16 fail without CPU fallback.
  Precision, memory fraction and Eager execution are visible controls; TUI remote
  vLLM begins eager, while CLI requires --enforce-eager to enable it. Context stays
  bounded/user-editable and concurrency is one sequence, with one-host mp workers.
  All visible model-bundle file metadata is revision-checked, with complete local
  shard references and no bundle symlinks. Torch/vLLM metadata/interpreter identity
  is rechecked before spawn; this is not full environment or weight attestation.
  Fixed help/NVIDIA/CUDA preflights share 45 seconds (30/3/10 sublimits), with
  50-second SSH and 60-second owned read deadlines; llama.cpp retains its budgets.
  Local vLLM uses the same 30-second help headroom and a 40-second owned read
  budget. Only used flags are carried forward, keeping launch payloads bounded. Remote
  readiness accepts a listener only in the created engine group, including vLLM
  frontend children. Owned leases/cancel/log/endpoint/model-work gates are reused.
  Provider keys/ambient overrides are omitted; offline settings and telemetry
  opt-outs apply. These are trusted-engine settings, not an OS network sandbox.
  Aligned review metadata stacks complete labels/values on narrow terminals; Back
  focus remains safe during paging. Evidence: `docs/s5c-remote-vllm-validation.md`.
  Upstream vLLM 0.31.0/Torch 2.13.0 served SmolLM2-135M-Instruct on GTX 1650
  over loopback SSH through the real CLI/TUI, with confirmed cleanup and preserved
  model roles/files. Initial cold-help and interrupted-cleanup failures prompted
  bounded preflight headroom and nested cancellation windows (remote receipt 6 s,
  helper 8 s, client 12 s); normal successful cleanup returns immediately. Exact model,
  context/precision/hardware and validation limits are recorded in the evidence.
  Physical LAN and other accelerators remain uncertified extensions.
  S5c remote adoption extends `model-manager adopt PID MODEL_ID` with
  `--ssh-server ID --local-port N` and Servers → saved server → Adopt existing
  server. Private fields capture the installed executable, exact advertised model
  ID, isolated PID and remote/tunnel ports; no resource/model settings are changed.
  Inspect/Review remain nonmutating, with Back/No focused. Same-account Linux PID
  start/group/session/executable/argv identity and an owned healthy loopback
  listener precede takeover. The client verifies its tunnel and current definitions/
  credentials, publishes an endpoint and sends a fixed acknowledgement; Ready
  requires the remote ownership receipt. A ten-second acknowledgement deadline
  bounds pending takeover. An abstract Unix socket rejects competing owners without
  lock files; failed takeover leaves the external process running. Original logs
  remain unattached. The shared six-second owner lease and shutdown windows apply
  after takeover; exact witnessed group members anchor TERM/KILL even when the
  leader exits first. Stale/reused identities reject signals; lost receipts remain
  Unconfirmed. Remote PIDs are explicitly excluded from local adopted cleanup.
  Actual upstream vLLM CLI and native CUDA llama.cpp TUI generation, review
  cancellation, three widths and confirmed Stop passed. S5c's supported Linux
  recipes/SSH scope is complete locally. S6a1 Vision is documented above. Evidence/limits:
  `docs/s5c-remote-adoption-validation.md`.
  S5c reviewed key setup adds `model-manager ssh host-key/trust/enroll` and
  Servers → saved server → Key setup. Ed25519 scans discover candidates without
  authentication; an independently verified SHA256 fingerprint and explicit
  review precede saving a content-addressed owner-only host pin. Definition nonce,
  host/port and a 120-second discovery receipt reject stale saves. Selected
  known-hosts revocations are retained; old trust files and identity selection
  stay intact. Private pins are bounded to 64 files. Enrollment accepts one
  bounded non-symlink Ed25519 .pub file through existing verified authentication,
  with a read-only review of the remote account/path, public fingerprint and file
  revision. Acceptance rechecks definition, authentication/public-file references
  and remote authorized-key metadata/content. Fixed remote Python anchors account
  SSH paths to directory descriptors, rejects unsafe permissions/symlinks/hardlinks,
  takes a bounded advisory lock and uses one O_APPEND write without replacing or
  chmodding existing key files. Existing restricted keys are never duplicated.
  Post-write receipt failure and lost transports are Unconfirmed, with no rollback
  claim; cancellation waits for owned-worker cleanup. CLI Ctrl+C exits 130 and
  Trust/Enroll confirmations default to No. Remote work has a ten-second alarm,
  15-second transport/20-second owned-job deadline and 256-KiB authorized-file bound.
  Setup fields/results stay out of chat/model context; no private-key contents,
  passwords/passphrases, key generation or automatic identity switch are added.
  Accepted enrollment/trust writes gate model work, survive navigation and reject
  late page/session/draft/target callbacks. Implementation: core ssh_setup and
  ssh_enrollment_program, CLI ssh_setup_panel/ssh_commands. Real CLI/TUI/new-key
  login and limits: `docs/s5c-ssh-key-setup-validation.md`.
- `klaude model-connections list/add/test`: register additional native Ollama,
  Chat Completions or Anthropic Messages endpoints and inspect their catalogs. Add requires an ID,
  `--adapter ollama|openai_compatible|deepseek|anthropic` and `--url`; optional `--key-env` stores a
  private credential reference, never a key value, and `--cloud` requires HTTPS.
  List is read-only; Add/Test idempotently seed existing native connections in
  owner-only `config/model-connections.json` without rewriting config roles or
  session preferences. Records have stable IDs, normalized URLs, enabled state,
  adapter/source and environment references; Codex retains account ownership.
  Qualified references use `backend@connection_id/model_id`, keeping slashes in
  model IDs. Native aliases remain valid for defaults, while qualified selections
  persist through chat restart. Missing/disabled qualified endpoints fail without
  silently choosing another model. Running/pending selections capture definition
  and credential revisions; stale activation cannot change a turn's runtime.
  Test runs the fixed `connection_models` operation through OwnedBackgroundJobs,
  with a 15-second outer deadline, 3-second connect/5-second read deadlines,
  no ambient proxy credentials/redirects, 1 MB response and 1000-model bounds.
  Authentication, network, timeout, missing catalog, malformed data and rate-limit
  failures remain distinct. No generation/model loading occurs. Catalog publication
  locks registry -> private credentials -> cache, rejects stale revisions and
  scopes cache generations to adapter plus endpoint. Native legacy cache refresh
  never replaces another endpoint's records; the merged cache is bounded to 8 MB.
  Catalog listings leave tool/context capability evidence unknown.
  CompatibleRuntime uses HTTPX without optional cloud SDKs, preserves complete
  tool protocol pairs, strips provider-private reasoning from generic requests,
  bounds SSE events/responses and publishes tool calls only after completion.
  Malformed arguments enter the existing bounded agent recovery path; output-limit
  and incomplete streams fail honestly. Native Ollama converts retained JSON-string
  tool arguments to native objects without mutating shared history, supporting
  provider switches after tools. HTTP adapters share cancellation that can wake
  requests before response headers and fork independent child transports.
  Compatible endpoints use configured bounded conversation budgets and default
  to one worker, including remote endpoints; their actual allocation, reasoning,
  GPU/thread controls remain server-owned. Native runtimes and local embeddings
  remain separate. S2a Add/Added settings, endpoint maintenance and model
  visibility/pinning and S2b Model Defaults are implemented. S2c's DeepSeek and
  native Anthropic slices are implemented and validated locally. S3a Web Search
  and URL Fetch settings are implemented and validated locally. S3b Tools
  execution, registry groups and Settings navigation migration are implemented.
  Evidence: `docs/s3b-agent-tools-validation.md`. S4a's Library session/knowledge
  foundation, Documents/Media storage and explicit Knowledge TUI consumers are
  implemented. S4b research jobs/defaults/reports are also implemented and locally
  validated; S5a's native Ollama lifecycle is also implemented and locally
  validated. S5b managed serving is implemented; S5c dependency inspection/CPU
  builds, SSH settings/diagnostics, owned remote CPU serving and reviewed existing
  public-key/host-trust setup, CUDA build profiles and offline NVIDIA vLLM wheel
  environments, reviewed retained setup removal and remote llama.cpp GPU profiles
  and remote NVIDIA vLLM serving and reviewed remote adoption are implemented;
  S5c's supported Linux scope is complete locally. S6 supplies native/HTTP Vision
  and chat images, CPU/CUDA generation, image-job management and selected AI tags;
  paid/legacy-provider generation access remains uncertified. See
  `docs/s6-completion-validation.md` and
  `docs/s4a-library-validation.md`, `docs/s4a-artifacts-validation.md` and
  `docs/s4a-knowledge-validation.md` and `docs/s4b-deep-research-validation.md`.
  DeepSeek is an explicit Add API Models preset and `/model` Cloud provider.
  Add DeepSeek endpoint opens an unsaved draft, rather than another global
  login store. CLI registration with `--adapter deepseek` requires HTTPS and
  defaults to the private `DEEPSEEK_API_KEY` reference. No DeepSeek connection is
  silently seeded into an existing registry; legacy defaults/deletions remain intact.
  Registered DeepSeek models use qualified `deepseek@CONNECTION/MODEL` identities
  in session selection and Model Defaults. DeepSeekRuntime reuses the bounded HTTPX
  stream/cancellation transport without the optional cloud SDKs. Standard mode
  explicitly disables upstream thinking; thinking maps low to low and medium/high
  to high. It retains at most 256,000 reasoning characters privately, publishing
  continuation only after a complete response. Tool-enabled requests echo that
  state only for the same endpoint, connection/credential revision and model.
  Final continuation survives owner-only model_content restore and counts toward
  compaction; public transcript, recap, generic compatible/Ollama requests and
  other providers omit it. Incomplete streams never publish buffered calls, and
  malformed arguments use the existing bounded agent recovery. Utility uses the
  same adapter with thinking off and the existing explicit budgets/fallback policy.
  Catalog tests remain metadata-only with unknown tool capability evidence.
  Local protocol fixtures, keyboard/one-shot evidence and live-cloud limits are
  recorded in `docs/s2c-deepseek-validation.md`.
  Anthropic uses an explicit Add API Models preset and Cloud endpoint shortcut,
  qualified `anthropic@CONNECTION/MODEL` references and the same private draft
  lifecycle. `--adapter anthropic` requires HTTPS and defaults to the private
  `ANTHROPIC_API_KEY` reference; existing registries gain no unsolicited endpoint.
  Catalog checks use native x-api-key/version headers and bounded pagination,
  never generation. Declared thinking types, effort levels and output limits
  are cached publicly; absent metadata stays unknown, and context/tool evidence
  is not inferred. Model IDs are not used to guess API capabilities.
  AnthropicRuntime uses the bounded HTTPX transport and native Messages blocks
  without cloud SDKs. Signed/redacted thinking and complete tool blocks are
  retained privately, unmodified, for the same endpoint, connection/credential
  revision and model. Owner-only model_content restore retains them and
  compaction counts them; public output, Utility and other providers omit them.
  Calls publish only after complete native message termination; malformed
  arguments use bounded agent recovery. Output-limit/incomplete responses fail
  honestly. Usage includes cache input and cumulative output without doubling it.
  Declared modes/efforts constrain the model picker and direct mode controls.
  Known always-on models visibly select Thinking with the lowest supported
  effort and unchanged output budget, and cannot serve as thinking-disabled
  Utility/fallback choices. Unknown Thinking profiles require catalog metadata;
  manual thinking needs a configured output cap above 1,024 tokens. No extra
  discovery or budget enlargement occurs during generation. Utility uses the
  same native adapter with thinking off and existing explicit fallback bounds;
  typed overload failures include HTTP 529. Local CLI/TUI, protocol and
  regression evidence, with live paid-generation limits, is recorded in
  `docs/s2c-anthropic-validation.md`.
  Implementation: core model_connections/model_discovery/compatible_runtime and
  http_model_transport modules; CLI model_connections and background-worker wiring.
  Live/mocked coverage and remaining limits are recorded in
  `docs/s1-model-connections-validation.md`.
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
  `--archived` lists retained archived sessions; `sessions archive SESSION_ID`
  and `sessions restore SESSION_ID` use the same transactional lifecycle as Library.
- `klaude sessions reconcile SESSION_ID [--yes]`: after a crashed or expired
  chat turn, explicitly acknowledge possible external effects before new turns.
  The session fence is checked again when the acknowledgement commits.
- `klaude sessions delete SESSION_ID`: delete one session after confirmation.
- `klaude sessions clear`: delete all sessions after confirmation.
- `klaude session-search`: search prior conversation sessions.
- `klaude status`: show configured modes, storage, and permission policies.
- `klaude system-info`: show normalized runtime-context diagnostics.
- `klaude doctor`: verify services, models, config, and data directories.

Chat slash commands currently include:

- `/model-manager`: open Model Manager outside Settings; Settings → Models
  provides the same workspace link. Endpoint, Installed models, Download,
  Discover, Service status and Hardware use typed panels with fixed headers and
  footers, controls above wrapped tables, stable IDs, shared Back/filter/draft
  behavior and owned read jobs. Inventory caches retain their true age for
  30 seconds; explicit Reload bypasses reuse and failed reads mark old snapshots
  stale. Private model/query inputs do not enter chat. Download/Delete reviews
  start with Back focused and clear old review filters. Accepted mutations retain
  endpoint/model identity through navigation; progress is bounded/throttled and
  cancellation waits for worker cleanup. Active chat, Knowledge, Research and
  Utility work gate mutations, and accepted mutations gate new model work.
  Hugging Face credentials reuse Provider credentials and return to Discover.
  Native CLI and real terminal/Ollama evidence: `docs/s5a-model-manager-validation.md`.
  Dependencies adds bounded tool/engine diagnostics, trusted committed-source
  CPU/CUDA build and local vLLM wheel reviews, logs and retained setup inventory.
  S5c's local build slice
  shares the model-work gate and opens verified results in a fresh Serve draft;
  evidence and remaining scope: `docs/s5c-dependencies-validation.md`.
  Servers adds reviewed SSH definitions and explicit connection/resource/model/
  process checks with a functioning diagnostics default. Its read-only checks
  share owned cancellation without gating unrelated model work. Serve model
  uses reviewed SSH/tunnel ownership, Cancel loading and existing ready-server
  Stop/log/inventory workflows, without changing defaults. Key setup adds
  independently verified host pinning and reviewed existing-public-key enrollment;
  Back is initially focused on reviews, with paged long details and controls
  above fingerprint tables. Explicit read/cancel state and semantic feedback use
  the shared panel conventions. Reviewed setup removal and remote llama.cpp GPU
  and remote NVIDIA vLLM profiles and reviewed remote adoption are implemented.
  Local recipe evidence:
  `docs/s5c-engine-recipes-validation.md`; removal evidence:
  `docs/s5c-setup-removal-validation.md`; SSH evidence:
  `docs/s5c-ssh-validation.md`, `docs/s5c-remote-serving-validation.md` and
  `docs/s5c-ssh-key-setup-validation.md`, `docs/s5c-remote-gpu-validation.md` and
  `docs/s5c-remote-vllm-validation.md` and `docs/s5c-remote-adoption-validation.md`.

- `/library [VIEW]`: open the Library workspace, also reached from Settings →
  Library directly below Memory (`/settings library`). Settings entry returns
  through Back to the Library row; direct `/library` entry closes to chat. Ordered
  Sessions, Knowledge, Documents, Research, Media, Archive. Sessions/Archive have
  bounded 100-record pages, full-store search over names/public turns, last-eight
  public-turn previews, resume, archive/restore and confirmed archived deletion
  with Back initially focused. Knowledge projects existing active-source metadata
  and legacy library names and searches active/enabled indexed text locally;
  existing learn/query/docs refresh commands retain ownership and compatibility.
  Learn source and Hybrid query are explicit actions; Managed sources reviews
  installed docs/crawls before refreshing. Private single-line editors never
  add their inputs/results to chat. Reviewed learning supports UTF-8 local text
  and public HTTP(S) pages, with the destination library/model/effect visible
  and Back initially focused. Hybrid queries run only on explicit request and
  use the existing embedding/vector/FTS/validation service, returning six bounded
  source excerpts without chat generation. Learning/refresh use the shared atomic
  indexer and retain originals and independent stored artifacts.
  Knowledge tasks reuse owned worker processes, with a five-minute outer deadline,
  30-second embedding requests, batches of at most 16 and 1000-chunk bounds.
  Learning is capped at 2 MiB; refresh at 8 MiB cumulative text and its existing
  page/crawl settings. Failed/partial/oversized refreshes retain previous indexed
  knowledge. These UI bounds do not silently truncate a replacement or alter CLI
  limits. Per-client acceptance and a cross-client task lock serialize TUI work;
  existing CLI/model services retain their own concurrency semantics. Starting
  requires idle model/setup/skill work; accepted tasks survive navigation and pause
  model queue consumption. Cancel/Ctrl+C reaps the owned process before unblocking
  the queue and reports that completed indexing may remain; no rollback is claimed.
  Model queue/context counters and live spinner/elapsed state remain visible.
  Session/store changes reject stale results, and task return state is captured.
  Metadata browsing and local indexed-text search call no models, embeddings,
  index writers or store constructors; explicit Hybrid query uses embeddings.
  Documents/Media provide import, metadata/type/source/tag search, sorting,
  manual tags, bounded preview, explicit desktop open and new-file export.
  Artifact controls precede tables; detail actions precede extended metadata;
  long previews start at the beginning and scroll with PageUp/PageDown. Media
  accepts bounded PNG/JPEG/GIF/WebP headers, reports available dimensions and
  offers a file export/open fallback without a decoder or vision model. Research
  opens a typed job form, saved reports and defaults above the job inventory.
  Queue/Start reviews initially focus Back. Progress shows bounded stages, source
  receipts, cancel and explicit resume; no automatic queue runner is started.
  A process lock serializes research across clients, owner leases detect interrupted
  jobs, and cancellation waits for owned-worker cleanup. Stale failures cannot
  overwrite a live owner or a published report. Recovery reads receipt URLs freshly;
  checkpoints store bounded URL/title/time/hash metadata, never page bodies.
  Job/report publication shares one SQLite transaction. Reports provide previews,
  export, tags/archive and explicit reviewed learning through the existing indexer.
  Discuss report preserves the unsent draft/attachments, stores its excerpt only
  in private model_content and publishes only the report name and user question.
  Its RESEARCH turn scope permits only query_knowledge, web_search and fetch_url,
  intersected with availability and permission gates; no workspace/MCP/delegation
  tools. Stored model synthesis is not fresh evidence or authorization.
  Owned eight-second read jobs use read-only
  SQLite, a 200ms busy timeout and three-second query deadline, bounded results
  and 30-second snapshots;
  Reload preserves true snapshot timestamps on failure. Leaving/navigation/session
  changes reject late results. Writes reuse the ordered session action lane;
  accepted actions retain target/session identity and do not steal later navigation.
  Library uses typed rows, controls above wrapped tables, fixed header/footer,
  stable record IDs and common draft/scrollback/Back/filter behavior. Implementation:
  CLI library_workspace/library_inventory/library_artifact_panel/library_commands,
  research_panel/research_commands and core library_artifacts/research;
  validation: docs/s4a-library-validation.md and
  docs/s4a-artifacts-validation.md. Content/metadata share atomic SQLite writes in
  owner-only data/library/artifacts.db. Archive/tags/delete require current record
  revisions; stale confirmations cannot delete restored artifacts. No operations
  implicitly learn content or add it to model context. Desktop open uses a fixed
  opener with a five-second deadline and private copies capped at eight; these
  are retained for asynchronous viewers. Headless/failed open suggests Export.
  Knowledge modules: CLI library_knowledge/library_knowledge_panel; evidence:
  docs/s4a-knowledge-validation.md. Panel text and cursor use one render snapshot,
  preventing resized long results from addressing absent text lines. Two-column
  inventories use their spare width for values.

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
  Providers, Search, Tools, MCPs, Skills, Memory, Permissions, and Runtime controls. Its
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
  INTERFACE appears first and contains Web UI. MODELS groups Models and Model Defaults. AGENT groups
  Search, Tools, MCPs, Skills, Memory, Library and Permissions. ADVANCED contains Provider
  credentials (the legacy Providers landing page) and Runtime. Inside MCPs, the MCP Servers
  heading shows `2 installed, 1 enabled` beside the snapshot age, independently
  of discovered tool counts. The Settings home keeps enabled/total counts.
  MCPs retains `/mcp` and
  `/settings mcp servers`; `/settings mcps` also opens that page.
  APPEARANCE follows ADVANCED and includes Divider (also `/settings divider`): Show divider hides or
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
  Models opens a typed landing page with Added Models, Add Models, Model Manager
  and Session model. Session model retains `/model`'s source/provider/model/mode/effort flow;
  returning from it opens the Models landing page. Add Models has Local and API
  drafts for implemented adapters only. Name, server type/provider, normalized
  URL, masked key, Test, Add and Cancel use shared panels/private editors.
  Changing an endpoint or adapter clears the entered key and test result. A new
  draft starts unfiltered; editing an existing draft retains its page state.
  Draft tests are cancellable 15-second catalog-only jobs: no generation and no
  registry, key or cache publication. Untested Add requires a separate review
  with Cancel focused. Accepted Adds use the ordered session action lane,
  independently of session database availability, and drain through navigation
  and exit; acknowledgements contain definitions/status only. A key is saved to
  a unique connection-owned private environment reference before publication;
  confirmed unpublished definitions remove that new key. Uncertain durability
  retains the key, since atomic replacement may succeed before directory fsync
  fails; a crash between files may leave an unused private key. Add retains
  current chat and embedding choices.
  Added Models opens from an eight-second read-only snapshot; endpoint detail
  offers Manage models and Test. Per-endpoint Filter, Reload models and manual
  model-ID entry precede catalog headers. IDs preserve provider slashes, and
  capability evidence remains unknown for untested catalog listings. Refresh
  retains filtering/focus and cannot interrupt transient field editing. Late
  results are scoped to session, definition and draft revision. Live keyboard
  evidence and remaining S2 scope are in `docs/s2-model-settings-validation.md`.
  Added Models also offers cancellable serial Probe of enabled endpoints and
  Clear offline. Checks persist bounded public status, age, definition and
  credential revisions; stale successes and failures cannot replace newer
  state. Disabled endpoints require an explicit detail-page Test. Clear offline
  reviews network/timeout failures only and rechecks their exact health snapshot
  before removal; authentication/rate/service errors are retained. Endpoint
  detail has Enabled and reviewed Remove actions on the ordered action lane.
  Reviews start unfiltered with Cancel focused. Affected startup choices require
  an explicit enabled replacement or Unset; no implicit provider/model switch.
  Removal retains credentials and conversation history, purges scoped catalogs
  and model preferences, and never recreates deleted definitions on migration.
  Startup unset persists a require-selection marker: interactive startup opens
  Models showing Not selected; line-oriented startup refuses generation until an
  explicit model is supplied. Session selection clears only the live unselected
  state; S2b keeps a saved Default Chat unset until explicitly configured.
  The current session remains independent of a maintenance replacement for its
  saved startup choice. An accepted turn keeps its immutable runtime; new queued
  prompts check endpoint/model availability without discarding pending input.
  Pending/unconfirmed maintenance pauses new turns until acknowledged or reloaded.
  Multi-file registry/preferences/cache updates do not claim crash atomicity;
  partial failures are unconfirmed and reload verifies the actual definitions.
  Per-model detail offers Use for this session, Enabled, Pinned and Hide from
  session picker. Hidden/pinned state is independent of availability; disabled
  models cannot be reinstated by manual/qualified selections. Preferences merge
  per field under the registry lock and persist when a model disappears from
  discovery. Catalogs include these missing choices with unknown capability
  evidence. Filter offers All/Enabled/Disabled/Hidden/Pinned per endpoint;
  applying it clears a navigation search, while reload retains search/focus.
  Environment-only keys cross owned jobs through their private request pipe;
  stored replacements/removals override launch environment values.
  Core maintenance lives in model_management, and the UI reuses model_settings
  and the existing session action lane without another writer or secret store.
  Model Defaults is a separate typed page (`/settings model defaults`, also
  `/settings ai defaults` and `/settings defaults`) with Default Chat, Utility, ordered Utility fallbacks
  and Utility output, plus Research endpoint/model inheritance. It migrates the
  effective legacy startup preference once
  into `ai_defaults` in chat-preferences.json, preserving explicit unset and
  unrelated fields. Default Chat applies at bare startup, `/new` and `ask` when
  configured; an explicit CLI model override wins. Session choices and queued
  selections now record their own history without rewriting Default Chat.
  Utility inherits the current session model or uses its explicit endpoint/model.
  Only `/recap --ai` and `/rename --ai` invoke it; ordinary chat, automatic
  first-input titles, deterministic `/recap` and compaction add no model calls.
  The owned job reads at most 24 recent saved public dialogue records and 6000
  characters, excluding model_content, tools, system events and private reasoning.
  It has no tools, a 40-second aggregate generation budget, a TUI 45-second outer
  kill deadline and at most four logical attempts. Earlier candidates get at
  most 12 seconds; the final eligible candidate may use the remaining budget.
  SDK Utility clients explicitly disable hidden retries, bound output and close
  owned resources. Native Ollama inherits the active GPU/thread overrides and
  requests 4096 context tokens and thinking off;
  compatible allocation/reasoning stays server-owned. Utility output defaults to
  512, with visible 128/256/512/1024/2048 presets; provider reasoning can consume
  the cap. Native title calls use at most 128. Recaps stay separately bounded
  public output, never injected compaction state; generated titles must fit 80
  characters. Only typed network/timeout, 429 or temporary 5xx failures use an
  explicitly configured fallback. Authentication/configuration, protocol,
  output-limit and quality failures never silently switch models. Unavailable
  fallback entries are skipped and canonical aliases are deduplicated.
  TUI receipts show actual model, fallback use, elapsed time and aggregate usage
  or unknown usage; line-oriented output names the actual model/fallback.
  The progress panel and shared spinner remain responsive; cancellation/exit
  drop late results and kill the owned group, retaining the unsent composer.
  Defaults writes use the existing ordered action lane, field comparisons and
  captured definition/credential revisions. Pending reads cannot restore older
  intent; failed saves remain unconfirmed without changing the active runtime.
  Removal reviews include affected Utility overrides/fallbacks and Research
  selections and require explicit role unset; changed snapshots reject the
  reviewed mutation.
  AI naming uses a conditional SQLite action, so concurrent manual renames win.
  Title saves and history-entry failures are acknowledged separately. Codex
  account Utility is unavailable until its broker can enforce these bounds;
  Default Chat retains that existing account adapter. Core configuration lives
  in ai_defaults, generation in utility, and UI ownership in ai_default_settings.
  Live and automated evidence/remaining limits are in
  `docs/s2b-ai-defaults-validation.md`.
  Research likewise inherits the accepted session model or its own explicit
  override, with no fallback list. Search → Deep Research owns its runtime
  defaults: provider auto, 2048 output tokens, 30-second extraction request timeout,
  2 extraction workers, 300-second run deadline, 2 rounds, 6 queries, 8 sources
  and 8192 context tokens. Visible bounded overrides scale these values; output
  must fit half the configured context. Extraction timeout bounds HTTP requests,
  while the owned worker bounds the full cascade/run. Research uses Standard
  mode through existing runtime adapters; native Ollama gets bounded planning
  and findings JSON schemas. Always-on Anthropic and unbounded Codex account
  generation are ineligible. Model calls receive bounded state rather than a
  growing transcript, at most one citation repair, no arbitrary tools or shell.
  Exact normalized quotes must occur in freshly fetched excerpts with actual
  source IDs. This checks citation evidence, not semantic correctness or complete
  topic coverage; smaller models may still produce partial/narrow reports.
  The active model's source, cloud provider, and model rows show Current;
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
  Search owns Web Search availability and result validation; Tools retains
  local-knowledge validation. Turning validation off exposes unvalidated
  leads only and does not bypass transport, provenance, or fetch safety bounds.
  Availability preferences cover web search, URL fetch,
  restricted HTTP endpoint probing, code search, persistent source learning,
  crawl, Hugging Face search/details/README, and the local knowledge library.
  Disabled tools are omitted from model schemas and cannot be reinstated
  by explicit retrieval routing or text-form calls. Shared agent construction
  applies availability/validation before the first request in both chat and ask.
  Search owns individual on/off settings for every configured web provider;
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
  `/settings search` (also `/settings web search`) currently opens Web Search
  directly. Its typed page has Enabled, Provider, Results per query, Manage
  providers, Test search, Fallback order, Validate search results and scoped
  Reset/Back. The Settings overview shows live ON/OFF, provider and result count.
  Providers and Tools retain links to the migrated owner. Existing config routing
  and saved provider/tool/validation booleans are retained on migration.
  Auto retains configured routing; pinned providers lead an exact, deduplicated
  fallback order. Unavailable/disabled/ineligible entries are skipped under
  existing relevance, billing, quota and attempt policies. Explicit provider
  directives and strict fallback policy still win. Provider choices affect
  Search without changing independent URL Fetch routing. Default agent results stay
  12; presets/custom support 1–50, and an explicit tool count takes precedence.
  Provider detail owns enabled state, masked keys, SearXNG URL and Tavily depth
  where applicable. Google Grounding shares the Gemini key; Exa shares its key
  with URL Fetch. Removing a key requires confirmation initially focused on
  Cancel. Accepted key writes drain through the ordered action lane, without
  session storage, and return only public acknowledgement flags. Gemini changes
  invalidate its model catalog outside the UI thread, with distinct feedback if
  credential saving succeeded but invalidation failed. Private worker credential
  resolution honors saved replacements/removals over stale launch values.
  Non-secret controls use the serialized preferences writer, immediate live
  intent and allowlisted cross-client acknowledgements. Scoped Reset clears
  routing/fallback/count overrides, retaining keys, enabled state, validation,
  endpoint and depth. Navigation/rendering do not read preference or credential
  files. Single-line editors never create model turns or chat/history entries.
  Test sends a user-reviewed query through an owned 25-second worker. Provider
  detail tests never substitute a fallback; overall tests use current routing.
  Tests respect availability, dependencies, billing and existing provider health;
  they return bounded provider/count/error metadata without snippets or raw
  upstream errors. Leaving, cancel, session or configuration changes invalidate
  delayed results. Credentials use the private pipe, never arguments or public
  messages. Search caches include routing, SearXNG URL and Tavily depth.
  The SearXNG quality adapter executes already-planned variants once, without a
  second legacy expansion; standalone legacy SearXNG search retains expansion.
  Technical source-only prompts with negated code actions do not enter code
  generation or require a standalone fenced artifact. Positive code requests
  remain supported. Evidence/limits: `docs/s3a-web-search-validation.md`.
  URL Fetch opens from Search's visible URL Fetch settings link, from Tools,
  or `/settings fetch` and `/settings url fetch`. Its typed page owns availability,
  Local cascade versus Exa cloud routing, provider details, an explicit Exa
  cloud fallback, uncached Test and current read-only transport limits.
  Existing `[web] provider` fetch behavior is retained until overridden;
  selecting a Web Search provider never selects a fetch engine. Reset restores
  config routing/fallback only, retaining endpoints, keys and availability.
  Crawl4AI detail owns its optional local/LAN service root, masked key and
  independent fetch enable toggle. Blank removes the service endpoint. Exa
  detail shares Search's private key/reference while its fetch enable state
  remains separate from search eligibility. Saved credential replacements and
  removals override stale environment/TOML values on restart. Custom Exa
  environment references work in fetch and both diagnostic workers.
  Provider-key writes use the same ordered private action lane. Navigation uses
  live state; field-scoped saves and public acknowledgements retain focus/query.
  Tools links to the owning page and its reset preserves migrated fetch controls;
  Providers' existing Crawl4AI entry opens the same detail page.
  Test reviews a public URL, uses the real uncached fetch route in an owned
  40-second worker, saves no page content, performs no learning/model call and
  publishes only bounded provider/count/failure metadata. Crawl4AI detail Test
  uses that extractor after the safe public download, without substituting local
  extraction or cloud fallback. Local cascade still takes direct text first.
  Cancel, navigation/session/config changes prevent late publication. Extraction
  HTTP requests reject redirects and ambient proxy credentials, bound decoded
  response bytes and use configured request timeouts. Provider errors do not
  reveal upstream bodies/keys. Live progress is neutral; success is green,
  warnings yellow and errors red. Transient input errors take precedence over
  crowded input hints; masked key entry suspends navigation before typing.
  Fetch cache identity includes routing/service/limits/credential identity;
  configuration changes clear failed-attempt reuse without losing verified source
  IDs. Reused documents still obey the current content limit, and zero cache TTL
  bypasses disk-cache reads/writes. An explicit read of a named public URL
  retains `fetch_url` when searching is forbidden; disabled/no-tools boundaries
  still win. Evidence: `docs/s3a-url-fetch-validation.md`.
  New PSE/Serper adapters remain separate work; S3b registry grouping is implemented.
  Chat activity uses the shared execution-event projection in
  `klaude_application.activity`: Writing code, Editing, Applying changes,
  Generating images, Creating files, Analyzing data, Running tests, Validating,
  Waiting, Generating response, Done, Error and Needs input. Activities remain
  separate from turn lifecycle states. The TUI keeps the selected Spinner
  animation and whole-turn elapsed time; WebUI offers a compact current label
  with an expandable, bounded execution timeline. Its checkpoint is committed
  atomically with existing public events and survives reconnect/resume.
  Transcript badges retain only completed outcomes such as `[EXPLORED] (9s)`,
  `[EDITED] (30s)`, `[RAN]`, `[LEARNED]`,
  `APPROVED`, `DENIED`, and `CANCELLED`; never persist generic `WORKING` or
  `WAITING` milestones. Updates must come from real model/tool/permission events and
  must never reveal a model's private chain-of-thought or scratchpad text. They
  are persisted with the session and mirrored to clients following via `/resume`.
  Needs input means an actual blocking question or permission decision. Waiting
  means a pending operation whose activity cannot be classified safely. Quiet
  test runners keep Running tests. Known file operations and single shell
  commands are classified deterministically; arbitrary scripts and MCP names
  stay generic. Requested tools do not count as executed. Overlapping executions
  retain the oldest active label; child-agent details never replace the parent.
  Done requires a successfully committed overall turn, never a tool result.
  Recoverable tool failures remain in history; terminal failures show Error.
  Cancellation/interruption retain their lifecycle labels. Permission waits complete as
  `APPROVED`, `DENIED`, or `CANCELLED`; never persist `WAITED`.
  Mapping, limitations and validation: `docs/agent-activity-validation.md`.
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
  Tools owns execution and built-in tool availability. `/settings tools`,
  `/settings agent tools` and `/settings agent` open its typed home: Execution,
  Built-in Tools, Activity Updates and links to the existing MCPs/Skills pages.
  Groups derive from `Agent.tools`, exclude external `mcp__` tools and omit
  unregistered capabilities; known labels/classification are shared with Permissions.
  Counts describe enabled/registered built-ins, not permission or transport readiness.
  Group switches show ON/OFF/MIXED; a mixed group first enables all its registered
  tools. Enter on a tool opens purpose, Enabled and its focused Permission policy
  link; Space on a group tool row toggles it. Enabling never modifies permission
  grants or workspace safety. Built-in reset enables only current registered
  built-ins, retaining MCP state, Search/provider settings and permission grants.
  Knowledge result validation lives in Knowledge & Sessions; web result validation
  remains in Search. Search/URL Fetch link to the availability owner and Back returns
  with their filter/focus intact. MCP/Skills links retain their management/search flows
  and return to Tools. Inventory rendering and toggles use in-memory snapshots,
  and field-scoped ordered saves retain failed intent and reject stale acknowledgements.
  All builtin preferences apply before chat and ask model requests. Live disables
  are rechecked in later schemas, native/text recovered calls, capability snapshots,
  delegation preparation and child tool construction. `docs/s3b-agent-tools-validation.md`
  records real TUI/protocol evidence and remaining limits.
  Runtime retains device, threads, context, calibration and editors, with an
  Agent execution settings link. Its reset preserves execution limits.
  Execution offers Max steps per message (12/20/40, custom 1-64), Tool-call limit
  (Auto or custom 1-256), Subagent workers and Advanced. Auto tool calls is
  `max(4, steps * 2)`, a finite ceiling; zero/None legacy values retain Auto.
  There is no Unlimited tool-call setting. Advanced offers a Total token budget
  (No total-token cap or custom 1-2,000,000), reported usage and the count of
  requests whose provider omitted usage. Zero means no total-token cap, not Auto.
  Tokens count provider-reported input plus output, including repeated context
  and child usage. Safe-boundary enforcement can overshoot by a request and
  tool-free finalization; missing usage remains unknown, never estimated as exact.
  Usage refresh is a bounded in-memory check only while Advanced is visible.
  Auto workers uses one for local/native Ollama and compatible endpoints,
  including remote compatible servers, and two for native cloud providers;
  explicit 1-4 choices support hardware/quota control. Workers apply to the next
  delegation without widening the read-only child allowlist, aggregate budgets
  or permissions. Other limits are captured when a new message starts; a setting
  edit cannot change the running turn's loop or reported step ceiling.
  All four limits persist under existing `runtime_options` keys through the
  serialized preferences writer. Latest-revision bounded acknowledgements merge
  disjoint cross-client limits, preserving live intent on failed saves. Per-field
  resets restore configured defaults; Execution reset removes only these four
  overrides, preserving hardware/context, tool availability and permission policy.
  Both chat and one-shot agent construction apply saved limits before the first
  request, without forwarding governor keys as provider inference options.
  Custom editors are private single-line inputs; invalid values retain the editor
  and cancellation adds no chat turn. The editor number is cleared before its
  panel returns so it cannot become the saved chat draft. Filtering and logical
  focus survive saves. A stopped governor returns a skipped result for every
  remaining call in the current provider batch, preserving complete tool-call
  ID pairs without executing or charging those calls. Governor skips do not
  count as repeated tool failures or retire a tool. If a required file read was
  blocked by a reached limit, Klaude reports that limit without asking the
  model to retry an impossible call; `klaude ask` exits nonzero.
  Evidence: `docs/s3b-agent-execution-validation.md`.
  Providers securely collects cloud-model, Crawl4AI Cloud and Hugging Face keys;
  Brave API, Parallel, Tavily, Exa and Firecrawl entries link to Search detail.
  The provider list has one status row per
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
  active and reports unconfirmed persistence. Agent execution reset actions
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
- `/recap [--ai]`: deterministic local recap by default; `--ai` explicitly uses
  the bounded Utility job for recent saved public dialogue.
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
- `/new`: start a fresh session with Default Chat and the current workspace, retaining
  saved conversations but clearing the terminal view and scrollback. Clears draft attachments and
  model conversation context.
- `/clear`: erase only the current terminal view and scrollback. Keep the same
  session ID, saved turns, model context, attachments, queue, and active work;
  later messages continue in the same session, and `/resume` can replay saved
  sessions. It takes no arguments and does not wait for the worker to become idle.
- `/rename NAME`: persist a 1–160 character name for the current session. Named
  sessions use that name in `/resume` and Markdown exports.
  `/rename --ai` explicitly generates an at-most-80-character Utility title and
  conditionally saves it without overwriting a concurrent manual rename.
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
  An observing client shows the shared canonical activity while the remote
  worker lease is active, using its selected spinner even when its own local
  worker flag is false. Confirmed terminal outcomes retain Done, Error,
  Cancelled or Interrupted; legacy sessions without these events stay generic.
  Before every provider request the worker publishes the
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
- ordinary explicit lookups also keep bounded, turn-local outcome evidence in
  `task_progress`: usable external retrieval, and candidate source examination
  for image-associated/origin requests and explicitly requested page reads.
  A direct source read can satisfy lookup;
  an observed MCP source-provenance result can also satisfy the relevant outcome.
  Search leads do not establish source examination. Missing actions get at most
  one model-directed correction per outcome; blocked, failed, empty or repeated
  omissions produce an honest incomplete/error result. Pending action responses
  are buffered up to 64,000 characters before publication, retaining live progress
  and direct ordinary-chat streaming. Detection is a bounded lexical bootstrap,
  not a general semantic planner; execution evidence cannot prove attribution.
  Quoted examples/code and individually negated lookup clauses do not create
  host-enforced obligations; the original request still reaches the model.
  Current goal and bounded unverified prior-answer context remain explicit;
  one ephemeral post-result note keeps follow-ups on that objective. Supported
  local runtimes reuse the existing constrained-action protocol on the bounded
  corrective attempt, exposing only the missing outcome's routes with no finish
  action. Permissions and argument validation remain authoritative. Budget-end
  synthesis cannot bypass an outstanding source-examination obligation.
  Current CLI/TUI/local-model and fixture boundaries are documented in
  `docs/agent-multi-action-validation.md`.
- native Ollama lookup recovery can opt into exact per-action argument schemas;
  final-answer fields cannot be reused as source-read arguments. The existing
  workspace discovery grammar and canonical host argument/permission checks stay
  authoritative. Bound interactive recovery takes one action before reconsidering
  dependent questions; ordinary read-only batches retain their existing bound.
  Unsupported runtimes receive no new recovery argument. No extra planner or
  normal-turn model call is introduced. Model pre-call information requests are
  retained as bounded audit metadata, rather than restated as unresolved gaps
  after a result arrives; actual host failures and limits remain visible.
  Retrospective source answers include at most four sanitized public fetched URLs
  when recorded, including restored receipts. They retain the distinction between
  recorded execution and actual evidence: source bodies are not replayed by this
  feature. Query/fragment values, credentialed URLs and private hosts are excluded.
  Follow-up evidence: `docs/agent-read-recovery-validation.md`.
- `discover_tools(query)` performs bounded metadata search across the current
  enabled, scoped registry and installed Skill summaries. It is a normal
  permission-controlled tool (default allow), configurable under Orchestration.
  Up to four matches per call load canonical schemas for the next response;
  discovery never invokes a target or authorizes a same-response call. Four
  discovery calls, twelve newly loaded tools and a context-derived schema byte
  limit bound each turn; oversized schemas are rejected whole. An initially
  omitted write/shell/commit/persistence/delegation route cannot be restored this
  way. Settings, scope, user tool-only/no-tools/search/Skill restrictions, live
  permission changes, definition identity, dirty-workspace and research budgets
  remain authoritative. Skill matches identify exact names for a separate
  `read_skill` call; metadata is not instruction authority. Loaded choices and
  the callback are turn-local, cleared on completion/cancellation and never
  restored as grants. Large model-facing registry summaries are bounded while
  full immutable status/audit snapshots are retained. Implementation and ongoing
  real CLI/MCP/Skill evaluation: `docs/agent-capability-discovery-validation.md`.
  Native Ollama non-coding recovery with discovery available also binds exact
  per-action arguments, retaining workspace discovery's existing default grammar.
  Valid native calls to enabled but deferred tools get one bounded discovery
  routing correction rather than a protocol switch; the rejected batch executes
  nothing. Malformed/unknown calls retain protocol recovery. Non-coding file/MCP
  investigations use the compact policy projection while preserving repository
  guidance, permissions and source-trust rules.
- MCP application errors retain the server's `is_error` flag as typed failed
  tool metadata. A completed remote call is not necessarily successful progress.
  Returned diagnostics stay visible; changed inputs can recover within existing
  permissions, duplicate guards and no-progress budgets, without automatic remote
  retries or claims that side effects were rolled back. Rediscovering the same
  schema does not repair invalid task identifiers. Evidence:
  `docs/agent-capability-discovery-validation.md`.
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
  A no-progress stop preserves the final factual explanation and emits a failed
  turn event, so one-shot `ask` exits 1 rather than presenting execution failure
  as a successful command. Successful recovery resets the streak; reaching an
  ordinary call/step budget alone does not introduce this failure event.
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
proposes one to three small behavior changes, grouping one to three files needing
edits with their focused tests. The adapter inserts project-check execution after
each behavior and appends final review, rather than asking the model to classify application
requirements as implementation or validation. Up to sixteen exact request spans
provide stable navigation references; a long tail remains one span, and the
original objective is retained verbatim. Plan links are advisory. Unlinked spans
remain visible, and review sees every span; linking or editing never proves
semantic coverage. Discovery omits reference excerpts until planning needs them.
Actual
file-tool changes and current passing checks gate implementation/validation step
completion. A failed optional plan does not prevent ordinary tool execution.
During constrained local implementation, write/edit path choices include the
active plan's files and already observed project files. A model proposal cannot
hide omitted existing tests, documentation or repair files. Canonical arguments
and the immutable response scope are
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
Phased plans require fresh edits when reusing files after the preceding phase's
check. Their bounded state exposes those fresh changed files; an older phase's
edit/check cannot complete the next phase. Active phase validation offers
inspection/check tools before further writes, with existing failure-driven repair
and permission boundaries. Older unphased plan contracts remain compatible.
The plan remains turn-local; it is not a durable requirements proof. Simple turns
and other providers keep their existing native path and do not incur this call.
The optional local planner is skipped when fewer than six steps remain or
exploration used 35% of the elapsed budget. Validation checkpoints prioritize
checks after test edits, two source-file edits since the last check, or budget
pressure (four steps remaining or 55% elapsed). Constrained local checkpoints
offer inspection/check tools before more edits. Under budget pressure they offer
only the available shell/check tool, avoiding another inspection loop; failed
checks reopen inspection and repair paths.
Failed shell probes also reopen repair even when their commands are not
recognized as project tests; successful help/smoke output is never a suite pass.
Validation checkpoints prioritize already-read documentation/configuration in
the existing version-checked excerpt cache, retaining check instructions within
the same request budget rather than reading files automatically.
No command executes automatically or bypasses permissions, and budgets do not grow.
Built-in Python file writes/edits up to 65,536 characters include passive AST
syntax feedback without imports, code execution or bytecode files. An applied
write remains applied; known syntax errors block completion until repaired.
Unrecoverable workspace transport failures save a factual incomplete-work summary
with actual edits and validation state before emitting the normal error.
Validation/recovery follow-up: `docs/agent-validation-recovery-followup.md`.
Cloud controls and smaller-phase follow-up: `docs/agent-phased-execution-validation.md`.
Ollama preserves native prompt-evaluation and generation durations alongside
existing total/load duration and token counts, without extra requests. OpenRouter
explicit thinking on/off overrides provider defaults; automatic/unspecified
thinking retains those defaults. Usage observed before failed/truncated buffered
responses remains available without publishing partial calls/private reasoning;
new request failures cannot reuse older usage.

`klaude_core.request_context` selects policy modules from the canonical prompt
using the actual callable schemas. Workspace implementation omits unrelated
configuration/runtime and standalone-answer detail, retaining host boundaries,
applicable repository guidance, and enabled Skill metadata. Coding tasks do not
admit product configuration merely because they mention tools or commands.
Retrieval-only requests use concise research policies and capability rendering,
omitting unrelated coding/presentation details while retaining authority,
repository/Skill guidance, runtime dates/location and source trust boundaries.
Historical/publication dates and event timings do not automatically select the
local clock. Explicit clock/weather requests retain their tools, and research
with those tools can still use the compact retrieval projection.
Whole-request quoted echo/reply/print operations use direct context and general
runtime options with no callable tools; their payload is not an instruction to
search or execute code. Compound actions and explicit file destinations retain
normal routing. Unconditional whole-request literal echoes are resolved directly
from bounded printable user text, preserving quoted spaces and punctuation,
without a model or tool request. Unquoted output requires `exactly` and one token;
conditions, transformations, destinations, additional actions and new image
attachments keep their normal model path. Direct echoes record zero model/tool use.
Local context remains explicitly configured; it is never silently increased.
Compatible HTTP/OpenRouter image transports retain safe timeout/connection/
protocol categories, response phase, generation-started state and request elapsed
time. CLI metadata preserves these diagnostics alongside explicitly labeled prior
usage. Failed/cancelled turns refresh elapsed budgets at their actual boundary;
completed request snapshots remain stable. Raw HTTPX messages, URLs and secrets
are not serialized. No new automatic transport retry or deadline policy applies.
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
Application chat admission and terminal finalization additionally use an additive
versioned journal: lease/fence, user input and runtime binding commit together;
assistant messages, terminal receipt and public completion commit together. The
public replay cursor includes a stream epoch and retention watermark. Expired
turns are interrupted and require reconciliation; old binaries cannot claim
execution leases after the migration. Explicit cancellation remains a terminal
receipt and does not automatically replay tools.

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

Session archive uses an additive `session_archive` table in the existing database.
It changes normal-list/default-resume visibility, retaining turns, events, names,
attachments' separate model content and configured recall. Restore is explicit;
archived sessions cannot acquire a worker lease. Archive/restore/delete check
state and unexpired worker ownership in the same `BEGIN IMMEDIATE` transaction
used for lease acquisition, so another client's restore invalidates deletion.
Library protects its current session; CLI archive can affect idle attached clients,
which report the archive and return their unrun prompt to the composer instead
of watching an imaginary worker. Permanent deletion removes only that session's
turns/events/name/live/client/archive rows; durable memories and learned knowledge
remain separate. Existing delete/clear commands also remove archive metadata.

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
- interrupted docs recovery verifies the downloaded files' exact checksums
  against active owner metadata; matching source URLs alone are insufficient.

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

Managed-source refresh uses fresh fetching through the existing guarded web
cascade, bypassing page/turn caches. CLI and Library TUI indexing share
`klaude_knowledge.docs.index_installed_docs`; manifest finalization follows
successful atomic owner activation.

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

- `brave` (keyless)
- `brave_api`
- `google`
- `parallel`
- `exa`
- `ddgs`
- `tavily`
- `firecrawl`
- `searxng`

Default provider order in code is:

```toml
["brave", "ddgs", "searxng", "brave_api", "google", "parallel", "exa", "tavily", "firecrawl"]
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
- preserve complete short proper names in provider queries; ordinary person and
  organization names are not rewritten into first-word acronym definitions;
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

The WebUI formats search leads within an 11,000-character model-input budget,
reserving source IDs, complete URLs, provider labels and available publication
dates before allocating snippet excerpts. Provider scoring/debug metadata stays
in structured execution data. Failed searches give the model bounded, redacted
provider attempts, actual queries and warnings so outages and filtered results
can be distinguished from missing information. Existing public-event privacy
rules remain in force. Evidence: `docs/webui/web-search-reliability-validation.md`.

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
- `exa`: Exa `/contents` when explicitly selected in URL Fetch, or after an
  eligible local extraction failure with its cloud fallback enabled. Inherited
  `[web] provider = "exa"` / `auto` behavior remains until overridden.

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
CI. Use an authorized cloud model whenever local inference would make an
evaluation slow; do not spend hours waiting on CPU-only local generations.
This preference applies to future evaluations as well. Keep user model defaults
unchanged and record the exact provider, model, mode and budgets. Cloud results
do not certify local-provider behavior: use bounded local checks or deterministic
protocol fixtures for those contracts, and document any remaining live-model gap.
Run `uv run python scripts/evaluate_agent_behavior.py --model MODEL --yes`
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
  are connected. Tools settings expose Auto or explicit 1-4 worker limits.
- Full validation can hang in the optional LanceDB roundtrip under some
  restricted sandboxes. Report the focused and non-LanceDB results separately;
  never describe the knowledge suite as green unless it completed.
- Continue controlled subagent orchestration with live behavioral evaluation
  before considering an implementation-worker role. Do not add
  background/cloud workers or broad write concurrency as part of that work.
