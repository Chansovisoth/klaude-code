# WebUI v2 coverage

Current browser implementation: **partial**. The planning specification describes
the target, not completed functionality. This checklist supersedes the original
inventory's historical statements that no host/browser API exists.

| Surface | Available in the browser | Remaining |
| --- | --- | --- |
| Chat | CommonMark replies with tables/tasks, local code highlighting and copy, stable streaming, response actions, timestamp/Branch/Retry menu, shared Agent, sessions, local model selection, tool reviews, questions, queue/control, device/Library text, PDF, DOCX and image attachments | In-place answer variants, Knowledge/Skill tools, full model/provider, queued attachments, image frame/crop controls and session-management parity |
| Workspaces | Bounded reads/search/Git views; opt-in local edits | Full workspace lifecycle and coding controls |
| Library → Files | Unified saved artifacts; All/Documents/Media/Reports type filters, separate Saved/Archived status, search/sort/pages, reviewed Document/Image import, text/image preview, download and tags; archived items support restore and reviewed deletion | Rich document rendering, direct stored-document Learn, research jobs, image generation/analysis and bulk management |
| Library → Knowledge | Inventories, indexed-text search, reviewed public-URL/text-upload Learn, exact existing-source refresh | Hybrid/model queries, crawl/source creation and broader management |
| Integrations → Skills | Installed inventory/filter, reviewed local ZIP/Markdown import, enable/disable, deletion | Discovery, remote installation, update checks and updates |
| Integrations → Connections | Visible deferred control with configured MCP server count; MCP retained as the server/protocol term | Server/Registry management, secret entry and OAuth |
| Activity | Public chat events and persisted Library/Skills operation states | Browser domain reconciliation/recovery and broader operation controls |
| Settings | Browser appearance, curated palettes, light/dark/system, reduced motion, admin password change | Memory management, complete settings coverage, custom/image-derived colors, additional account controls |
| Models | Local chat selection | Model Manager and other defaults/connections/operations |

Initial Library/Skills actions cover parts of inventory F058–F060, F069–F070,
F072–F073 and F080–F082. They do not establish whole-feature parity. Desktop and
mobile reuse the existing Material 3 Expressive shell, tokens and reduced motion.

## Boundaries

- Shared `application.library_management` composes existing artifact, knowledge
  and Skill services. Reads avoid knowledge engine initialization and model/network
  work. Library items, knowledge inventories/matches/sources and installed Skills
  use pages sized to complete grid rows near 20 cards (at most 40), with chevrons,
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
