# Changelog

## Unreleased

- Add the experimental local WebUI and shared application foundation, with an
  expressive responsive chat shell, eight color palettes, shared-session controls,
  message links and device sharing, file attachments and image thumbnails,
  Files/Knowledge/Skills pages, and local admin sign-in. Browser coverage remains
  partial; see the [WebUI checklist](docs/webui/coverage.md).

- Pair complex local behavior changes with their tests and checks between phases;
  require fresh edit/check evidence when files recur in later phases.
- Honor explicit OpenRouter thinking controls, preserve usage from failed replies,
  and retain Ollama prefill/generation stage durations without extra model calls.

- Keep observed project files available when a proposed plan omits tests/docs;
  reserve complex local execution for earlier validation and repairs, and skip
  late optional planning. Report passive Python syntax diagnostics after actual
  edits without executing code. Preserve a factual workspace summary on terminal
  provider errors. Resolve unambiguous user-supplied literal echoes without model
  generation, extra punctuation or tool calls.

- Add bounded, permission-controlled discovery of enabled tools and installed
  Skills, including deferred MCP schemas. Load definitions for the next response
  without executing targets or restoring omitted mutation/delegation routes.
  Bound large registry summaries while retaining complete audit snapshots, and
  show concise tool/Skill discovery activity in chat.
- Preserve typed MCP application failures through the CLI tool adapter, count
  them as failed progress and retain bounded recovery with corrected inputs.
  Keep valid deferred native calls on native routing recovery and reduce
  unrelated policy context for read-only file/MCP investigations.
- Mark exhausted no-progress execution as a failed turn while preserving its
  final explanation. One-shot chat now exits 1 for that host-detected stop;
  recovered tools and ordinary budget finalization retain their existing paths.
- Bind native Ollama lookup-recovery arguments to the chosen action's schema,
  and sequence interactive recovery reads before dependent questions. Keep model
  information requests separate from observed research limitations, and require
  explicitly requested page reads before budget-end completion. Retrospective
  source answers now include bounded sanitized public fetched URLs without
  replaying source bodies. Reject all URL userinfo, including empty usernames.
  [Follow-up evaluation](docs/agent-read-recovery-validation.md).
- Track explicit lookup outcomes and source examination, retain bounded current
  goal/referent context, and use bounded native action recovery for omitted work.
  Reduce retrieval-only prompt overhead and buffer replies until required retrieval runs.
  Keep literal replies direct and avoid clock tools for historical-date research.
  Preserve typed transport failures, response phase and actual failure elapsed time
  without automatic transport retries. [Evaluation](docs/agent-multi-action-validation.md).
- Rename Models & AI to Models, AI Defaults to Model Defaults, and Agent Tools
  to Tools. Move Search into Agent directly above Tools, and Appearance below
  Advanced. Fill empty model roles from verified available metadata in owned
  background work while preserving current selections, explicit inheritance,
  Vision's enable switch and the active chat model.
- Prepare large PNG/JPEG/static WebP/GIF attachments automatically while preserving
  private originals: full bounded decoding, orientation/transparency normalization,
  metadata stripping, task-sensitive detail, explicit frames and source-pixel crops.
  Share verified request budgets with compaction, retain failed image attempts
  through retry/resume, report typed provider failures and actual routed models,
  and keep image paths from activating unrelated coding tools. Fix cancellable
  private-worker input stalling on payloads larger than the pipe buffer.
- Discover native Ollama capabilities automatically in AI Defaults and Manage
  Models settings. Show Vision, text-only, tools, thinking and embedding support;
  distinguish server image generation/audio from Klaude consumers. Keep checks
  bounded and cancellable, label failed checks as unverified, and disable known
  incompatible Vision choices without loading models for inference.
- Add Library directly below Memory in Settings, with `/settings library` access
  and Back returning to the same Settings row. Reuse the existing workspace;
  direct `/library` entry continues to close to chat.
- Fix offline vLLM setup discovery when uv is installed in a managed tool cache.
  Retain its explicit launcher path through owned workers and keep restricted
  subprocess PATH, executable revision checks and secret isolation.
- Preserve host-written, redacted provider diagnostics in Media analysis and
  AI-tag workers, including exhausted-credit and authentication failures.
  Provider bodies stay private; fallback and explicit-retry rules are unchanged.
- Wrap Media failure details in narrow forms and clear stale picker filters
  without losing the question/budgets. Load saved Vision roles through owned
  metadata inventory instead of displaying uninitialized settings as OFF.
- Validate actual native CUDA image generation through CLI and bare TUI on
  GTX 1650 using the engine's supported upstream-GGML configuration, without
  patching upstream sources or changing Klaude's runtime defaults. Final full
  local checks pass: 3,496 tests, 19 skips, lint/types and five-wheel packaging.
  Paid/legacy-provider access and broader image-quality certification remain open.
  [Final S6 phase audit](docs/s6-completion-validation.md).
- Add optional S6c AI tag suggestions through existing Vision endpoints and
  budgets. Review pixels, select tags and save explicitly; retain manual tags and
  per-tag AI provenance separately. Add CLI suggestion/selection/clear commands,
  metadata search, stale-proposal checks and archive/delete lifecycle support.
  Actual native Gemma CLI/TUI flows passed.
- Add Media → Image jobs and CLI generation-jobs, explicit server refresh and
  reviewed terminal-receipt removal. Preserve full job IDs in narrow CLI output,
  hide prompts from lists, retain images independently and clear stale removal
  filters. Actual CLI/TUI protocol walkthrough passed.
  [S6 follow-up evidence](docs/s6-completion-validation.md).

- Fix native image jobs that complete during cancellation being labeled cancelled.
  Add reviewed completed-output recovery through CLI `generation-status --recover`
  and the current TUI result, without resubmitting generation. Reuse atomic Media
  publication, exact binding/receipt checks and deletion protections. Handle native
  automatic sampler defaults and queued-only cancellation with explicit review
  warnings; retain observed running-job state after a rejected cancellation.

- Add S6b1 reviewed local image generation through an existing native
  stable-diffusion.cpp service. OFF-by-default settings and Library Media reuse
  owned workers, scoped cancellation, captured roots and ordered settings saves.
  Store one bounded PNG atomically with private provenance; expose CLI review,
  status/cancel and the existing artifact lifecycle. Real CLI/TUI protocol
  fixtures and actual native CPU inference/export passed. Subsequent CUDA
  CLI/TUI validation is recorded in the final S6 phase audit above.
  [Evidence](docs/s6b-local-generation-validation.md).

- Add S6a3f current native Gemini image chat for exact reviewed
  `gemini-3.5-flash-lite` and `gemini-3.8-flash` IDs. Apply declared Thinking
  modes/efforts to selection, commands and private session restore, including
  minimal where supported. Preserve native signatures from the first text turn,
  group parallel tool responses and omit interrupted rounds atomically. Earlier
  foreign tool results remain historical context without forged signatures.
  Standard-only Media/Utility/Research reject incompatible roles before model work.
  Both models passed actual Google RGB analysis; Flash-Lite also passed real TUI
  read_file, signed continuation, retained-image follow-ups and process resume.
  [Evidence](docs/s6a3f-current-gemini-validation.md).

- Add S6a3e native Gemini image chat and private Media for exact reviewed
  `gemini-2.5-flash` and `gemini-2.5-flash-lite` IDs on Google's official root.
  Fresh metadata checks, bounded inline requests, explicit thinking/output
  controls, complete-stream tool gates and scoped signed-part replay reuse the
  existing private image lifecycle and owned Media worker. Fix shared HTTP Media
  usage normalization and count Gemini image thought tokens in output usage.
  Real TLS CLI/TUI settings/review/cancel/follow-up/resume fixtures passed.
  Live generation remains unverified: both legacy IDs returned HTTP 404 and
  Google reports 2.5 Flash is unavailable to new users. Newer profiles remain
  separately scoped; no silent model substitution.
  [Evidence](docs/s6a3e-gemini-vision-validation.md).

- Add S6a3d reviewed native OpenAI Responses images in chat and private Media.
  Exact source-linked profiles plus authenticated availability checks enable two
  documented GPT-4.1 Mini IDs only on the official API; unknown/custom/fine-tuned
  models remain unavailable. Preserve private Responses continuation, complete
  tool pairs and actual pixels across compaction. Forward streaming output limits,
  reject incompatible reasoning/budgets and report metadata timeouts cleanly.
  Distinguish exhausted credits from temporary fallback failures without exposing
  provider messages. Real CLI/TUI TLS fixtures passed; live generation remains
  unverified due to exhausted OpenAI credits.
  [Evidence](docs/s6a3d-openai-vision-validation.md).
- Add S6a3c OpenRouter chat images and reviewed Media analysis using fresh
  image-input/text-output declarations, existing private snapshots and bounded
  cancellable HTTP delivery. Keep endpoint/model selection explicit and reject
  mandatory reasoning in standard chat or thinking-disabled Media. Fix metadata
  catalogs incorrectly using the smaller stream-event bound, and prevent SDK
  tool/private-reasoning publication after incomplete or truncated responses.
  Actual free-model one-shot, interactive follow-ups, process resume and reviewed
  Media analysis passed. OpenAI/Gemini image adapters remain pending.
  [Evidence](docs/s6a3c-openrouter-vision-validation.md).
- Add S6a3b reviewed Media analysis through Anthropic and declared compatible
  HTTP endpoints using shared capability inspection, owned workers and explicit
  fallback reviews. Reuse native provider protocols with tighter response bounds;
  distinguish local context estimates from server allocation. Reject stale
  reviews, oversized inputs and thinking-required Media models before sending.
  Protect native models referenced through compatible endpoint aliases. Real
  compatible Ollama CLI/TUI analysis and Anthropic protocol fixtures passed,
  retaining images/model digests and creating no chat turns or saved results.
  [Evidence](docs/s6a3b-http-media-validation.md).
- Add S6a3a chat images through native Anthropic Messages and declared compatible
  HTTP endpoints, with exact-model capability evidence, provider-aware input
  bounds and preserved private/tool protocols. Model rows show image evidence.
  Restore explicit session model/mode/revisions independently of Default Chat.
  Keep tool-free follow-ups anchored to user intent instead of interpreting
  assistant answers as lookup topics. Real compatible Ollama one-shot, TUI and
  restart/resume passed; Anthropic TLS protocol/TUI fixtures passed, with paid
  generation unverified. [Evidence](docs/s6a3-http-chat-images-validation.md).
- Add S6a2 provider-neutral image messages and native Ollama image attachments
  in coding chat/one-shot input, with explicit Vision enable/capability checks,
  private Media snapshots, restore/compaction bounds and endpoint-scoped approval.
  Preserve failed attachment drafts, tool protocol pairs and public export privacy.
  Separate intent from image metadata to avoid unnecessary workspace discovery.
  Real qwen3.5:4b CLI/TUI follow-ups and process resume retained pixels after source
  deletion. [Evidence](docs/s6a2-chat-images-validation.md).
- Add S6a1 reviewed native Ollama Vision through Library → Media and
  `library analyze`, with explicit off-by-default settings/model/fallbacks,
  declared capability checks, private pixel input/results, bounded editable
  budgets and owned cancellation. Preserve chat, original artifacts and knowledge.
  Fix typed HTTPX fallback eligibility and premature Vision read timeouts.
  Real qwen3.5:4b CLI/TUI pixel analysis passed; other adapters remain S6a3.
  [Evidence](docs/s6a-local-vision-validation.md).
- Add reviewed SSH adoption of existing llama.cpp/vLLM servers, with exact
  process/model/listener checks, exclusive acknowledged ownership, bounded lease
  cleanup and original log/settings retention. Keep remote PIDs out of local
  cleanup. Real upstream vLLM CLI and native CUDA llama.cpp TUI generation,
  cancellation and confirmed Stop passed; evidence:
  [remote adoption](docs/s5c-remote-adoption-validation.md).
- Validate upstream vLLM GPU serving through the actual CLI/TUI on GTX 1650.
  Give heavy vLLM cold imports bounded preflight headroom, reuse one CLI/TUI
  timeout policy, and align remote/helper/client shutdown windows so delayed
  cleanup acknowledgements are not preempted by the outer client.
- Add reviewed remote NVIDIA vLLM serving through the existing SSH owner lease,
  with environment-specific CUDA checks, stable GPU UUID selection, local bundle
  revision checks and explicit precision/memory/eager controls. Owned frontend
  children can provide the verified listener; cancellation/cleanup remain shared.
  Review values align on wide screens and complete labels stack on narrow ones;
  offline/telemetry settings and bounded preflight payloads are retained.
  Evidence and remaining limits: [remote vLLM](docs/s5c-remote-vllm-validation.md).
- Add reviewed remote llama.cpp GPU offload with explicit layer/device fields,
  bounded engine device discovery, and fresh inventory checks at review/launch.
  Keep CPU defaults, exact argument arrays, private minimal environments and the
  existing SSH owner lease/tunnel/cleanup architecture. Preserve specific remote
  errors and correct GPU progress; retain requested devices in server details.
  Move mappings beside GPU fields, page long forms, show short selected values
  and keep Back focus at paging boundaries. Cancelled probes reap immediately.
  Real CUDA inference over loopback SSH returned OK with 37/37 layers offloaded;
  CLI/TUI and regression evidence: `docs/s5c-remote-gpu-validation.md`.

- Add reviewed retained CPU/CUDA build and vLLM environment removal through
  `model-manager remove-build ID` and Dependencies → Built/installed engines.
  Show exact scope and estimated storage; default to Back/No. Recheck filesystem
  revisions, workers, managed servers, model roles and accessible external
  processes. Serialize acceptance with local server startup; do not follow venv
  symlinks. Retain an unservable cleanup record after partial removal, with honest
  cancellation/retry behavior. Preserve original sources/wheels, external weights,
  model defaults and server history. Fix removal-worker configuration ordering,
  restricted Linux process inspection and narrow review controls. Evidence:
  `docs/s5c-setup-removal-validation.md`.

- Add reviewed local CUDA llama.cpp builds with explicit/observed architectures,
  compiler compatibility probes and a selected CUDA host compiler. Add offline
  NVIDIA vLLM setup from bounded trusted local wheels into a separate environment,
  with early dependency/platform resolution, exact-version/hash installation and
  CUDA/backend/help checks. Reuse the owned setup worker, safe resource defaults,
  private logs, cancellation, dirty-source snapshots and model-work gates. Add
  typed recipe forms, paged Back-focused reviews and engine-aware Serve handoff;
  preserve models, existing environments and defaults. Distinguish setup checks
  from GPU inference certification. Real full-source CUDA compilation passed;
  managed qwen2.5-coder:3b GPU generation returned OK and retained 22 Ollama digests.
  Upstream vLLM inference remains unverified. Evidence and remaining S5c scope:
  `docs/s5c-engine-recipes-validation.md`.

- Add S5c reviewed Ed25519 host pinning and enrollment of existing public keys
  through current verified SSH authentication. Add canonical host-key/trust/enroll
  commands and private Key setup panels. Preserve known-hosts revocations, original
  trust/identity files and existing authorized-key bytes/restrictions; reject stale
  definitions/reviews, unsafe paths and ambiguous keys. Use bounded owned jobs,
  account-anchored descriptors, an advisory lock and a single append. Keep lost
  receipts/cancelled remote effects explicitly unconfirmed, with no rollback claim.
  Fix late results interrupting newer setup forms and cramped fingerprint columns.
  Real CLI/TUI key enrollment, new-key login and Ctrl+C/exit-130 flows are recorded
  in `docs/s5c-ssh-key-setup-validation.md`. Key generation/password bootstrap,
  local CUDA/vLLM recipes are recorded above; remote GPU/vLLM profiles remain unfinished.

- Add S5c reviewed remote CPU llama.cpp serving over verified SSH and an owned
  loopback tunnel, reusing the existing ServingJobs/helper lifecycle. Add
  --ssh-server/--local-port options to serve and a server-scoped TUI form. Verify
  executable/model/credential revisions, owned listeners and exact model identity
  before registering an endpoint. Renew remote owner leases; distinguish confirmed,
  not-started and unconfirmed cleanup and disable unchanged owned endpoints.
  Keep HTTP checks off the heartbeat/cancellation loop. Add visible Cancel loading
  and scrolling for long reviews. Fix CLI preflight config scope and false busy
  ports after stop by matching reusable bind semantics. Real qwen2.5-coder:3b CPU
  generation over SSH returned OK and preserved all 22 original Ollama digests.
  Reviewed key setup/local recipes are recorded above; remote GPU/vLLM work remains pending.

- Add S5c SSH server settings, explicit strict-host-key connection tests and
  bounded read-only CPU/RAM/disk/model/process diagnostics. Reuse owned workers,
  private forms and ordered revisioned settings writes; support existing keys
  or an explicitly selected SSH agent. Add canonical model-manager ssh commands
  and a diagnostics default with a working Inspect default server consumer.
  Preserve key/remote-file/model-connection state, reject stale results and retain
  the true age of inspections across connection retests. Fix shared table
  alignment for read-only/action rows in declared inventory sections. Real
  OpenSSH CLI/TUI workflows passed; remote lifecycle and reviewed key setup are
  recorded above. Online/system installer paths remain outside these local recipes.
  See the S5c SSH
  validation record.

- Start S5c with local dependency diagnostics and reviewed llama.cpp CPU builds
  from immutable committed source snapshots. Add canonical dependencies/builds/
  build CLI commands and a Model Manager panel, private logs, disk/source/resource
  bounds, compiler cancellation and verified executable handoff to Serve models.
  Preserve dirty source and existing engines/models/defaults; reject changed tools,
  commits and binaries. Real source compilation and model serving passed, retaining
  all 22 existing Ollama digests. Fix forced-cancel engine probes escaping the
  owned worker group. Additional GPU/vLLM installers remain pending; the SSH
  settings/diagnostics slice is recorded above.

- Implement S5b managed serving for installed llama.cpp/vLLM engines: private
  structured launch/adoption forms, bounded flag/device tests, local weights,
  loopback ports, explicit CPU/GPU limits, owned helpers and health-gated endpoint
  registration. Add foreground serve/adopt CLI commands, retained server metadata,
  bounded redacted logs and reviewed stop. End servers on client lease loss; reap
  owned groups and reconcile unchanged endpoints after helper failure. Failed
  adoption preserves external processes, and unavailable GPUs cannot silently
  fall back to CPU. Test the real installed llama.cpp engine and preserve the
  existing native fleet; vLLM inference remains unverified because it is not
  installed. Dependencies/rebuilds/SSH remain S5c.

- Implement S5a Model Manager: endpoint-scoped native Ollama inventory, reviewed
  downloads/deletion, live progress/cancellation, service status, local hardware
  and bounded Hugging Face GGUF discovery through existing credentials. Add
  `/model-manager`, its Models settings link and matching CLI commands. Preserve
  roles, endpoint aliases and existing models; recheck definitions, credentials,
  digests and loaded state before mutations. Reuse owned workers with bounded
  progress and compatible final results, scoped cache invalidation and model-work
  gates. Fix reused review filters, credential-owner Back navigation and missing
  table headers. Keep terminal progress in place and captured logs concise.
  Real Ollama cancellation/retry/deletion preserved all 22 original model digests.
  Dependencies/SSH (S5c) and S6 remain pending; see the S5a
  validation record.

- Complete S4b Deep Research: reviewed job forms, durable queues, a Research
  model role and bounded Search defaults, owned execution with progress/cancel,
  metadata-only recovery checkpoints and fresh evidence on resume. Reuse model
  adapters and the Library store; atomically publish reports with job completion.
  Check exact citation quotes, repair invalid findings once, retain honest partial
  outcomes and distinguish CLI exit codes. Add report preview/export, private
  scoped discussion and reviewed learning. Fix stale cross-client error writes,
  report-loading/navigation feedback, persisted search/fetch settings and native
  structured planning; preserve model changes and published reports. Reject
  truncated source bodies during Knowledge learning. S4 is complete locally;
  the S5a slice above follows it. See the S4b validation record for
  actual CLI/TUI evidence and the remaining small-model coverage limitation.

- Finish S4a's Knowledge consumers: reviewed source learning, hybrid queries and
  managed-source refresh through bounded owned tasks, retaining the shared indexer,
  existing retrieval and CLI compatibility. Add live progress and cancellation
  feedback without chat generation; preserve old indexed knowledge on failed or
  oversized refreshes. Fetch refreshed pages freshly and verify content checksums
  during interrupted-docs recovery. Fix repeated-query/Back state, long-result
  terminal-resize crashes, and two-column inventory width use. This completed S4a.

- Continue S4a with Documents/Media managed copies, metadata search/type filters,
  sorting, tags, bounded text/image-metadata previews, explicit desktop open and
  byte-preserving export. Store content and metadata atomically in a private
  SQLite artifact store; import launches no indexing or model calls. Add artifact
  archive/restore and confirmed deletion, stale-revision guards, workspace export
  boundaries and matching `klaude library` commands. Move detail actions above
  metadata and open previews at their beginning. Prepare report storage for the
  subsequent S4b slice; the Knowledge slice above adds its actions.

- Start S4a with Library's Sessions/Knowledge/Archive foundation. Add typed
  navigation, bounded read-only store inventories, session search/paging/previews,
  resume, local indexed-text search, archive/restore and confirmed permanent
  deletion. Keep controls above wrapped tables, logical Back/filter/draft state,
  and accurate loading/save feedback. Serialize archive state and worker leases
  across clients, preserve saved turns/recall, reject stale deletion, and avoid
  phantom-worker waits in clients whose session was archived elsewhere. Retain
  existing knowledge commands. This foundation precedes the artifact slice above;
  S4b Deep Research follows in the slice above.

- Complete S3b with live-registry built-in groups, enabled/total counts,
  mixed-state bulk switches, individual availability controls, purpose and
  permission links, and links to existing MCP/Skills owners. Regroup Settings
  into Appearance, Models & AI, Agent, and Advanced; retain Providers/Tools
  routes and link Search/URL Fetch to the single availability owner.
  Apply availability preferences to all built-ins in chat and ask, preserve
  ordered live intent and permission grants, and recheck current disables in
  subsequent schemas and delegated child capability intersections.

- Start S3b with typed Agent Tools execution settings: bounded step presets and
  custom values, finite Auto/custom tool-call limits, optional reported-token
  budget/usage and provider-aware worker controls. Preserve existing Tools links,
  move execution ownership from Runtime, and scope resets by field/page.
  Apply saved governor limits to both chat and ask before the first request,
  keep them out of inference options and retain a running turn's captured ceiling.
  Preserve live intent, filtering and focus through ordered saves/failures;
  clear transient numeric input before returning to the chat composer. Complete
  skipped tool-result pairs when a provider batch exceeds the governor, without
  charging or retiring skipped calls. Report a reached limit directly when a
  required file read cannot run, avoiding an impossible retry.
  Registry groups and the remaining Settings reorganization are still pending.

- Complete S3a URL Fetch settings with independent routing/availability, Crawl4AI
  service/key controls, shared Exa credentials, explicit cloud fallback,
  cancellable uncached diagnostics and current transport limits. Preserve
  migration behavior, field-scoped saves and Tools/Providers links. Bound
  authenticated extraction responses, repair configuration-scoped failure reuse,
  enforce current limits on cached sources and honor zero cache TTL.
  Retain explicit URL reads when searching is prohibited. Fix the new masked
  editor transition, prioritize transient validation errors, and honor custom
  shared credential references and saved removals on restart.

- Start S3a with a Web Search settings owner: Auto/pinned routing, result presets
  and custom counts, provider details, private masked credentials, SearXNG URL,
  Tavily depth, exact fallback ordering and cancellable provider diagnostics.
  Preserve existing Tools/Providers entry routes, live state and scoped resets.
  Apply saved availability/validation in shared chat/ask agent construction.
  Prevent negated code actions in source-only searches from forcing code repair.
  Avoid expanding SearXNG's planned queries twice; the real fixture search now
  makes 3 requests instead of 24 with the same five leads.
- Start S2 model settings with Added Models, Add Models and Session model pages,
  private Local/API drafts, cancellable catalog-only tests, acknowledged Add,
  endpoint details, catalog filtering/reload and manual model selection.
  Add probe, scoped health metadata, endpoint toggles/reviewed removals, safe
  Clear offline and independent per-model enabled/hidden/pinned preferences.
  Explicitly handle affected startup choices, preserve running model snapshots
  and block new requests to removed/disabled models.
- Add S2b AI Defaults with separate Default Chat/session choices, Utility
  inheritance, ordered explicit fallbacks and bounded output presets. Provide
  opt-in AI recap/naming with public-only context, no tools, cancellation,
  explicit fallback receipts and concurrent-rename protection. Keep ordinary
  chat, first-input naming and compaction free of extra Utility calls. Wrap long
  informational setting values at narrow terminal widths.
- Add S2c's DeepSeek endpoint preset, Cloud picker shortcut, CLI registration and
  dedicated Chat Completions runtime without cloud SDK dependencies. Explicitly
  map thinking modes and retain bounded private reasoning only for the same
  endpoint/model and connection revision. Reuse cancellation, tool recovery,
  session restore and Utility bounds; keep generic providers free of that state.
  Validate real terminal/one-shot paths against local protocol fixtures; live
  DeepSeek generation remains unverified.
- Add native Anthropic endpoint settings, paginated catalogs and an SDK-free
  Messages runtime. Preserve signed thinking/tool blocks privately across
  same-model continuation and session restore, reject incomplete streams, and
  reuse owned cancellation and malformed-call recovery. Use declared catalog
  metadata for modes/efforts, show required thinking explicitly, and exclude
  known always-on models from tool-free Utility. Validate real CLI/TUI paths
  against local protocol fixtures; live paid Anthropic generation is unverified.
- Add versioned model connections, endpoint-qualified model references,
  revision-scoped catalogs and cancellable catalog checks through
  `klaude model-connections list/add/test`. Preserve native model choices,
  session preferences, private credential references and embedding configuration.
- Add an SDK-free Chat Completions runtime for explicitly configured compatible
  endpoints, with streamed tool assembly, incomplete-response rejection,
  malformed-call recovery, bounded context and shared transport cancellation.
- Translate retained compatible tool arguments when switching to native Ollama,
  preserving conversation history without the observed HTTP 400.
- Prevent a worker's late TUI repaint during shutdown from reporting a committed
  session or memory-setting write as failed. Keep redraw errors visible while
  the application is running, and cover the teardown race deterministically.

## v0.2.0-alpha.4 - 2026-10-06

- Make bare `klaude` the primary interactive entry point while retaining
  `klaude chat`; keep completed output in ordinary terminal scrollback and
  preserve queued commands, session continuity, and model changes during work.
- Improve the typed Settings navigation, appearance controls, MCPs/Skills
  search and management, permission links, background inventories, and
  field-scoped persistence feedback. Fix Input Field height reset handling.
- Add external MCP management, bounded public Registry discovery, explicit
  enablement, and private remote OAuth authentication. Keep imports and Registry
  installs disabled until explicitly enabled.
- Add OpenRouter and secure provider-key settings alongside the existing
  OpenAI API, Gemini API, and Codex account runtimes; preserve provider-specific
  continuation, cancellation, and usage accounting.
- Add controlled read-only delegation with intersected capabilities, permission
  checks, conservative concurrency, aggregate budgets, and durable public
  worker outcomes.
- Improve malformed-call/path recovery, shell and validation failure tracking,
  bounded working-source context, task-state continuity, and factual incomplete
  results. Preserve dirty-worktree boundaries.
- Add locked Python 3.11–3.13 CI, lint/types and installed-wheel smoke gates,
  plus reproducible release-candidate builds and provenance attestations.
  Start the non-publishing candidate gate through manual dispatch or an alpha-tag
  push before verifying and publishing the prerelease.
- Record the proposed model connection, AI Defaults, Search, Agent Tools,
  Model Manager, Deep Research, and Library (including Media) work in
  [the settings and feature plan](docs/odysseus-settings-and-features-plan.md).
  These planned additions are not shipped feature claims.

### Known limitations

- Neither `qwen3.5:4b` nor `qwen2.5-coder:3b` has demonstrated completion of the
  unchanged Stockroom CSV benchmark. Final-candidate comparisons remain pending;
  automated host checks do not establish autonomous task completion. See the
  [task-state evaluation](docs/agent-task-state-evaluation.md).
- Delegated workers remain read-only; unrestricted implementation workers are
  not included. Model/server behavior still depends on the configured provider,
  model capabilities, and available hardware.

## Earlier development notes

- Add a native external MCP client with local stdio and remote Streamable HTTP
  transports, safe VS Code/OpenCode JSON import, explicit trust before launch,
  cached bounded tool discovery, collision-safe namespacing, per-tool ASK
  permissions, persistent process-scoped sessions for browser/stateful servers,
  bounded untrusted results, and masked environment-backed secret storage.
  Expose management through `klaude mcp` and `/mcp` in Settings without slowing
  chat startup or injecting remote prompts/resources into model context.
  Add bounded asynchronous discovery through the official public MCP Registry
  in `/mcp` and `klaude mcp search/info/install`. Filter to active latest
  records, cache them privately with stale fallback, sanitize untrusted display
  metadata, accept only HTTPS Streamable HTTP or exact-version npm/PyPI plans,
  preserve provenance, and save every registry install disabled without
  connecting, downloading, or executing third-party code.
  Complete protected remote-server authentication with the official SDK's OAuth
  discovery, PKCE/state validation, dynamic registration or optional Client ID
  Metadata Documents, automatic refresh, private per-server token/client storage,
  loopback and masked manual callbacks, and explicit auth status/logout commands.
  Complete the in-chat MCP setup path: collect required registry values and
  secrets, add custom HTTP/stdio definitions, import compatible JSON, and
  confirm connection/enablement without leaving Settings. Fix a redraw crash
  caused by evaluating a static-only registry type at runtime.
- Preserve OpenAI Responses continuity without changing Klaude's local-first
  privacy boundary: API and Codex requests continue to use `store=false`, request
  encrypted reasoning state, and replay only validated provider-issued reasoning,
  assistant-message, and function-call items. Assistant `phase` values survive
  stateless continuation, while orphaned provider function calls remain excluded.
  Store this opaque replay envelope only as private model context in the
  owner-only session database so `/resume` can restore it without exposing it in
  transcript text or shared session events. Bind a hashed, per-session prompt
  cache routing key across turns and resume, rotate it for new/forked sessions,
  and enable ZDR-friendly server-side compaction before Klaude's local fallback
  threshold. Strictly retain and replay encrypted compaction items, prune older
  provider dialogue before the latest item while re-sending Klaude's current
  system/capability contract, and expose only exact provider-reported cache hit
  and cache-write token counters in `/status` and shared completion metadata.
- Make routing prohibition-aware so negated inspection, execution, and mutation
  verbs do not expose unintended tools. Preserve contextual storage intent across
  user-boundary compaction, prefer the bounded `storage_usage` capability over
  generic shell/workspace hints, and retire completed host-preflight tools before
  the provider request to prevent duplicate calls. Strengthen live evaluations
  so direct scenarios can forbid every tool, expected read-only evidence can be
  approved unattended, and timed-out workers retain only sanitized partial
  counters and tool activity.
- Add OpenRouter as a first-class Cloud model provider with authenticated live
  model discovery, truthful tool/context/reasoning capabilities, SSE streaming,
  native Klaude tool calls, usage accounting, cancellation, and private
  reasoning-continuation state. Add Settings > Providers for masked API-key
  entry/removal across cloud models and all configured web, hosted-fetch/crawl,
  and Hugging Face providers, with atomic owner-only `config/.env` persistence
  that never exposes values in transcript or session state. Rework Settings as
  a grouped, aligned live overview; preserve logical selection across dynamic
  updates and navigation; and give each provider a descriptive Add/Update/Remove
  detail page instead of mixing key actions into the provider list. Load the
  Skills inventory asynchronously with an immediate loading state and a
  short-lived cache, avoiding the first-use knowledge-package import stall.
  Standardize unavailable picker actions as gray but focusable rows whose Enter
  and mouse confirmation are safe no-ops, including missing credentials, empty
  model catalogs, absent Nano editors, and an unavailable Custom permission map.
  Add ranked type-to-filter behavior to selection screens, and put Login/Logout
  at the top of every Cloud model page with masked API-key entry, official Codex
  device login, and confirmation before logout.
- Fix explicit workspace-inspection routing for weak local models: recognize
  natural inspection/review wording, keep the selected schema read-only, and
  run one bounded `workspace_info` preflight before synthesis. Persist its
  real start/result events and evidence so a model cannot silently guess the
  implementation language without inspecting the workspace.
- Add the first controlled-subagent foundation: typed read/research and
  test/diagnostic child tasks, parent-intersected read-only capability
  envelopes, conservative permission inheritance, independent and aggregate
  budgets, bounded structured results, cancellation checks, and public
  lifecycle events. Add an isolated sequential child-agent adapter that receives
  only bounded task context, runs under a dedicated non-interactive scope and
  independently forked provider transport, and charges successful or failed
  child usage to the parent governor. Host cancellation fans out to the primary
  and active child transports. Child tool calls now have independent and
  aggregate caps, reserve the enclosing parent tool-result slot, and stop
  provider-emitted parallel call batches at the first exhausted safe boundary.
  Exact Ollama, OpenAI/Codex, and Gemini input/output counters now accumulate
  across every child request under per-child and aggregate token caps; missing
  or partial provider counters remain explicitly unknown rather than estimated.
  Public child events now carry a host-issued batch ID and monotonic batch
  sequence, serialize callbacks across worker threads, reject duplicate or
  impossible lifecycle transitions, and distinguish work rejected before start
  from work that actually started and finished. Explicit delegation and
  second-opinion requests now narrowly expose one permission-controlled
  `delegate_task` accepting up to three independent tasks; completed public
  child summaries and sanitized lifecycle metadata persist for local and resumed
  clients. Ollama stays single-worker. Cloud providers may run two children at
  once only for an audited stateless workspace-tool subset, with fixed aggregate
  reservations made before launch and input-ordered results. Shared web,
  knowledge, Git, shell, mutation, and unknown capabilities remain sequential.
  Runtime settings expose the provider-aware Auto policy and explicit 1-4
  worker overrides without widening capability or permission boundaries.
  Normal turns also accept an explicit `[agent].max_tool_calls` ceiling, while
  retaining the derived two-calls-per-step default when it is zero.
  An optional `[agent].max_total_tokens` ceiling now uses the existing exact
  provider-usage governor without changing the unlimited default.
- Add typed standard, plan, review, init, and evaluation turn scopes to the
  immutable capability contract. Enforce each scope's tool allowlist before
  provider requests, hard-limit `/init` writes to the workspace-root
  `AGENTS.md`, and expose the effective scope through `/status` and durable
  capability snapshots.
- Add a privacy-bounded live behavioral evaluation harness with isolated
  read-only model/scenario workers, hard timeouts, explicit network opt-in,
  non-overwriting report paths, sanitized provider failure categories, and
  comparable tool/retry/permission/token/finalization/retrieval metrics. Isolate
  every worker from real saved memory, sessions, and knowledge, copying only the
  public model catalog. Add an offline synthetic learned-document scenario and
  deterministic claim-plus-source grounding expectations, counts, and scores so
  retrieval is not credited merely because a tool ran. Add content-free per-model
  and per-scenario comparison aggregates, and classify repeated required-retrieval
  omissions separately from generic runtime failures. Expand
  deterministic transcript replays across local, cloud, Codex-authenticated,
  and tool-less capability profiles.
- Make provider stream cancellation best-effort and idempotent across Ollama,
  OpenAI/Codex, and Gemini so transport teardown failures cannot escape into TUI
  controls or session switching.
- Advance development package identities to `0.2.0a4` so unreleased work never
  reuses the published alpha.3 artifacts. Run CI for every pushed branch as well
  as pull requests and manual dispatches.
- Normalize exact Ollama, OpenAI/Codex, and Gemini token usage in the live
  footer, retain estimates when a provider omits usage, and mirror only bounded,
  whitelisted provider metadata to clients following a session through
  `/resume`.
- Enforce provider/model tool capability declarations when building each
  request: models without native tool support receive no tool schemas, and the
  same per-turn capability snapshot explains why those tools are unavailable.
- Add a provider-independent progress governor, immutable per-request capability
  snapshots, bounded unavailable-tool recovery, durable stale-worker recovery,
  crash/interruption fixtures, and stricter OpenAI/Codex stream completion and
  tool-item validation.
- Add Python 3.11-3.13 CI, production mypy, Ruff, and a five-wheel isolated
  installation/CLI smoke gate. Track the workspace `uv.lock` so frozen CI and
  clean-checkout builds use the exact dependency graph validated for release;
  keep path-rendering tests independent of a developer-specific home layout.
- Add a manual, non-publishing release-candidate gate that builds all five
  wheels twice with a fixed source timestamp, validates wheel metadata and
  archive structure, requires byte-identical artifacts, emits SHA-256 sums,
  creates Sigstore-backed GitHub provenance attestations, and retains the
  verified candidate for review.
- Fix picker scrolling by tracking the selected row in the renderer; add
  PageUp/PageDown navigation and Escape cancellation. Standardize reset and
  cancel rows across selection menus, preview theme changes, and support
  validated, persistent minimum/maximum composer heights.

- Keep multiline terminal pastes together as one `klaude chat` request instead
  of generating once per pasted line.
- Prevent Enter from crashing `/model` or another slash command when its
  completion menu is open but no suggestion is selected.
- Add a bordered interactive chat surface with input history, slash-command
  completion, model and reasoning-effort pickers, context/token telemetry,
  deliberate multiline editing, and terminal-only styled Markdown/code panels.
- Render all picker options as a highlighted, scrollable list inside the input
  field, add visible cancellation to model/effort/theme flows, and sort model
  pickers and model listings alphabetically.
- Replace the blocking terminal chat loop with a persistent normal-screen layout:
  output stays above a full-width live input, background turns leave typing
  available, multiple inputs queue, Alt+Backslash or `/steer` can prioritize a new
  instruction, Alt+Enter inserts a newline, and Ctrl+C interrupts at the next
  safe boundary. Enable Kitty and xterm modified-key reporting only while the
  TUI is active, restore both on exit, and provide Ctrl+J as a newline fallback
  for terminals such as MobaXterm that collapse modified Enter into plain Enter.
- Show queued follow-up inputs in a compact live strip above the composer and
  provide a queue editor: repeated Alt+Up walks from newest to oldest, Enter
  saves, empty text plus Enter deletes, and queue consumption pauses during edits.
- Add a branded normal-screen welcome view with a boxed block Klaude logo
  and current package version, plus persistent, independent TUI appearance
  controls: Autumn chrome by default plus Pastelle Pink, Hacker
  Green, and Neon Synth; separate VS Code Dark, GitHub Dark, Monokai, and
  Solarized Light Markdown/code colors; and reset-to-default actions for both.
- Render `/help` category names with underline styling and separate each user
  and Klaude message with a full-width gray divider containing its local date
  and time.
- Centralize appearance under Theme, Output Field, and Input Field settings;
  default the output border and scrollbar off, keep the rounded input border
  independently configurable, add a persistent 1–12 line input-height control
  with an 8-line default, migrate legacy flat preferences, and remove redundant
  dashed rows beneath command-reference category names.
- Reuse the last successfully selected model on the next `klaude chat` launch,
  while keeping explicit `--model` and the configured coder role as overrides
  and fallback respectively.
- Add `/keybinds` for a deterministic keyboard-only reference, and
  show described slash-command suggestions immediately when input starts with
  `/`.
- Bound the default agent loop to 20 model steps per turn, expose persistent
  Safe/Balanced/Extended/Custom limits from 1-64, and recover from
  Qwen/Ollama tool-XML `unexpected EOF` failures with one tool-free retry.
- Show safe reasoning/drafting progress, prevent reasoning-only blind retries,
  and validate Python/GDScript before displaying code, with at most two
  diagnostic-driven repair attempts.
- Preserve concise model-authored search queries, require every explicitly
  requested search/fetch operation, retain query-relevant excerpts from long
  fetched pages, and retry once when an explicitly requested source URL is
  omitted.
- Keep explicit no-search prompts out of focused CLI command help, and restore
  `git_status` when current branch or dirty-worktree inspection is requested.

- Route self-contained code generation without retrieval tools, honor explicit
  no-search requests, use a compact code prompt with live output streaming, and
  retain durable user/project preferences in that prompt.
- Add independent `[ollama.code_options]` and `code_think` tuning so constrained
  and high-end machines can choose different code budgets without silent model
  switching, plus one tool-free recovery for malformed Qwen tool XML.
- Make provider health recoverable: a single operational failure no longer
  disables later searches, repeated failures enter a timed cooldown, stale
  legacy failures expire, and successful low-relevance responses still prove
  the provider is healthy.
- Stop caching empty or failed web searches, ignore previously cached failures,
  and preserve academic, research, and documentation intent when queries also
  contain freshness terms such as `latest`, `current`, or a year.
- Preserve dense and lexical backend evidence during reciprocal-rank fusion,
  expose RRF/reranker provenance, and keep the optional reranker's final order.
- Add a bounded single-agent web research loop with per-turn structured state,
  model-directed search/refine/fetch decisions, configurable action/search/fetch/
  per-domain/failure budgets, graceful best-effort exhaustion, duplicate-query and
  duplicate-fetch prevention, and compact action traces.
- Separate web source discovery from page reading with runtime-generated search
  result/source IDs, selective `fetch_url`, canonical URL/content deduplication,
  structured failures, public-network redirect validation, bounded extraction,
  and an explicit untrusted-web-content boundary.
- Add conservative local-first search-query typo correction and entity-name
  learning with RapidFuzz, a compact SQLite alias cache, correction provenance,
  protected short acronyms/proper names, and an optional keyless Wikidata
  fallback that fails safely when offline or ambiguous.

## v0.2.0-alpha.2 - 2026-08-02

Second preview release focused on durable storage invariants, retrieval quality,
provider observability, project-local configuration, and chat behavior.

- Add atomic knowledge indexing with versioned staged rows, `active_sources`
  activation, failed-operation recovery, and active-version-only retrieval.
- Route `learn`, docs sources, crawled docs, skill imports, CLI, and MCP indexing
  through the shared indexing service.
- Add refreshable `llms.txt` docs sources, polite same-domain crawling, skill
  package imports, unchanged-source skip logic, and `docs update --online`.
- Add relevance-first web search routing across Google, Parallel, Exa, DDGS,
  Tavily, Firecrawl, and SearXNG with explicit provider overrides and fallback
  metadata.
- Show structured provider labels in chat output for `web_search` and
  `fetch_url`, including multi-provider searches and fetch providers.
- Fix Exa authentication to load `EXA_API_KEY` from local dotenv config, strip
  whitespace, and send the key through `x-api-key` without a bearer prefix.
- Add Tavily and Firecrawl as optional search providers while keeping hosted
  extract/crawl/research features out of Klaude's tool surface for now.
- Improve ambiguous acronym and local-entity lookup behavior with softer
  candidate discovery, fetched-page verification, location-aware query planning,
  and model-chosen search queries.
- Improve follow-up entity state so user corrections, entity type changes, and
  claim verification queries do not reuse incompatible earlier meanings.
- Improve command discovery with a canonical command registry, deterministic
  command-reference rendering, focused command help, typo-tolerant command-list
  requests, and no invented command syntax.
- Add `sessions delete` and `sessions clear` with confirmation prompts.
- Add runtime context collection plus concise behavior rules so greetings and
  directory questions do not dump full machine specs.
- Add conservative automatic memory, explicit memory controls, session recall,
  and sensitive-memory filtering.
- Move source-checkout config into visible `config/`, runtime data into
  `.klaude/data/`, and tracked examples into `config/examples/`.
- Split SearXNG's service secret into `config/searxng.env` so provider API keys
  in `config/.env` are not passed into the container.
- Add `[ollama.options]` request tuning for Klaude chat calls without requiring
  Modelfiles or moving host-level Ollama daemon settings into the app config.
- Update README and `AGENTS.md` to describe the current architecture, provider
  behavior, config layout, MCP boundaries, and development workflow.

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
