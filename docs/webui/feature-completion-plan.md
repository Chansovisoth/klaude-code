# WebUI feature completion

The requested goal is browser parity with Klaude's supported CLI features. The
existing `coverage.md` records shipped behavior; the feature inventory and v2
specification describe the larger target. Preserve the uncommitted starting work.

Work order (each item needs application, HTTP, UI and validation together):

1. Memory: bounded inventory/search, automatic-memory setting, reviewed add,
   edit and exact deletion, sensitive-fact rejection and stale-selection checks.
2. Connections: real MCP inventory, reviewed add/enable/disable/remove using the
   shared definition writer and operation journal; discovery and tool invocation
   remain separate operations. Registry discovery, secrets and OAuth follow.
3. Conversations: rename, archive/restore, reviewed permanent deletion and public
   Markdown downloads, scoped to the selected workspace.
4. Agent tools: connect Knowledge/Skills and web retrieval to the browser agent
   through the existing permission, execution and lifecycle contracts.
5. Models/settings: configured provider selection, effort, connection/default
   management and field-scoped application settings.
6. Generated: Research job creation/control, image generation/analysis/tagging,
   stored-document learning and job recovery.
7. Workspaces/coding: workspace lifecycle, file revisions/diffs, shell/build/Git
   actions with their existing reviews and workspace protections.
8. Remaining inventory: remote Skill discovery/updates, operation recovery,
   bulk artifact actions and additional supported settings.

Do not count a visible control, private worker kind or a CLI implementation as a
working browser feature. Never retry an unknown mutation as a new request. Tests
must distinguish deterministic protocol evidence from live-provider evidence.

Implemented in this pass:

- Memory inventory/filter, automatic memory, reviewed add/edit/exact deletion.
- Connections inventory, remote add-disabled, discovery/enable, disable/remove,
  shared witnessed MCP receipts and reviewed calls through cached schemas.
- Workspace-scoped conversation rename/archive/restore/delete and public Markdown
  downloads, with history rechecked before permanent deletion.
- Knowledge, installed Skills and web read tools in browser chat; current public
  Memory, Skill metadata and shared tool/permission/execution preferences refresh
  at each turn boundary.
- Configured local/cloud model choice, supported reasoning efforts, exact runtime
  revisions and offline saved-session resume.
- Reviewed execution limits, read-tool switches and per-tool permissions using
  the shared field-level compare-and-set writer.
- Reviewed Web search provider/results/depth, SearXNG and Crawl4AI endpoints,
  page-reader routing/fallbacks and all saved Research budgets. Research saves
  validate coupled token limits and reject concurrent changes to its defaults.
- Saved UTF-8 text/code, PDF/DOCX and Research-report learning from File details,
  with exact revisions, bounded checksummed bytes and the shared Knowledge index.
- Memory changes refresh both the browser prompt and code-generation context.
- Generated Research queue/start/stop and image generation/cancel/output recovery
  using an already configured image service. Existing source verification,
  provider binding and generation receipts remain authoritative.
- Concurrent attachment-column migration now uses a SQLite write transaction.
- Reviewed shared Model Defaults for Chat, Utility, Research and Vision, explicit
  ordered fallbacks, Utility output budget and confirmed-state Vision activation.
  Fresh browser chats/startup use an explicitly selected Chat default; unset or
  unavailable startup choices require model selection. Existing chats keep their
  runtime. Research offers its separate saved role or the current chat model.
- Image-service test/review/save, with exact model/capability evidence and the same
  witnessed journal used by CLI/TUI. Defaults and image-service unknown saves have
  reviewed exact-state browser recovery without replay or model contact.
- Reviewed image analysis and tag suggestions, persistent bounded private results,
  owned-worker cancellation and a separate review to save selected offered tags.
  Images stored as Documents work without re-importing or changing their type.
  Source byte reads check stored size before allocation, revision and checksum.

Still open: Model Manager and model/provider definitions/secrets,
interactive MCP OAuth and Registry/stdio setup, remote Skill discovery/updates,
Knowledge crawl/source management, workspace lifecycle,
shell/build/Git controls and general browser operation reconciliation. These are
not counted as complete by the new controls.

Validation and exact limitations: `feature-completion-validation.md`.
Media continuation: `media-controls-validation.md`.
