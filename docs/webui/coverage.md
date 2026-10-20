# WebUI v2 coverage

Current browser implementation: **partial**. The planning specification describes
the target, not completed functionality. This checklist supersedes the original
inventory's historical statements that no host/browser API exists.

| Surface | Available in the browser | Remaining |
| --- | --- | --- |
| Chat | CommonMark replies with tables/tasks, local code highlighting and copy, stable streaming, response actions, timestamp/Branch/Retry menu, shared Agent, sessions, local model selection, tool reviews, questions, queue/control, device/Library text, PDF, DOCX and image attachments | In-place answer variants, Knowledge/Skill tools, full model/provider, queued attachments, image frame/crop controls and session-management parity |
| Workspaces | Bounded reads/search/Git views; opt-in local edits | Full workspace lifecycle and coding controls |
| Library → Uploads | List/Grid/Gallery, image-only month-added groups, bounded cached thumbnails, adaptive image preview with zoom/touch controls, reviewed source links/tag chips, URL history, independent type/archive filters and sorting, reviewed imports with automatic image detection, text preview/download/tags/archive/restore/delete | Directory trees, original modification/capture dates, rich document rendering, direct stored-document Learn, research jobs, image generation/analysis and bulk management |
| Library → Generated | Separate inventory of saved research reports/generated images, List/Grid/Gallery, search/type/archive/sort controls, existing previews/downloads and reviewed tags/archive/restore/delete | Starting Research or image-generation jobs in the browser, arbitrary generated workspace files |
| Integrations → Knowledge | Inventories, indexed-text search, reviewed public-URL/text-upload Learn, exact existing-source refresh, responsive paging and URL history; legacy Library Knowledge links migrate here | Hybrid/model queries, crawl/source creation and broader management |
| Integrations → Skills | Installed inventory/filter, reviewed local ZIP/Markdown import, enable/disable, deletion | Discovery, remote installation, update checks and updates |
| Integrations → Connections | Visible deferred control with configured MCP server count; MCP retained as the server/protocol term | Server/Registry management, secret entry and OAuth |
| Activity | Public chat events and persisted Library/Skills operation states | Browser domain reconciliation/recovery and broader operation controls |
| Settings | Browser appearance, curated palettes, light/dark/system, reduced motion, admin password change | Memory management, complete settings coverage, custom/image-derived colors, additional account controls |
| Models | Local chat selection | Model Manager and other defaults/connections/operations |

Initial Library/Skills actions cover parts of inventory F058–F060, F069–F070,
F072–F073 and F080–F082. They do not establish whole-feature parity. Desktop and
mobile reuse the existing Material 3 Expressive shell, tokens and reduced motion.
Uploads has a compact search/filter/sort/add toolbar with 48px action targets.
Mobile lists omit desktop column headers, use 70px rows and place the first file
4px below the toolbar. The plus button opens the existing reviewed upload flow
in a native dialog; desktop retains its sortable columns and inline filters.
Uploads contains imported documents/media only. Generated uses stored research
records and generated-image provenance, with separate counts and tab state.
AI tagging an imported image leaves it in Uploads. Existing artifacts stay in their
current store; the split is applied before search, sorting and pagination.
Uploads and Generated share All types/Documents/Media filters. Saved research
reports appear under Generated → Documents using their existing Research records.

## Boundaries

- Shared `application.library_management` composes existing artifact, knowledge
  and Skill services. Reads avoid knowledge engine initialization and model/network
  work. Uploads uses stable 24-item pages across List/Grid/Gallery, with an eight-page
  short metadata cache and abortable reads. Grids use two/three/four/six columns;
  Gallery uses three/four/six and month boundaries may end in partial rows.
  Knowledge inventories/matches/sources and installed Skills retain pages sized
  to complete grid rows near 20 cards (at most 40), with chevrons,
  persistent first/last page numbers and ellipses around the current range.
  Filtered counts and the current card capacity determine the actual final page.
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
  Management changes affect the shared CLI stores; browser chat still uses its
  existing restricted workspace tool set, without Knowledge/Skill invocation.
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
  180-second owner timeout. Durable receipts deduplicate supplied request IDs.
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
