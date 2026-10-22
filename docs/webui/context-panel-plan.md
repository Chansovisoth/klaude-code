# Context Panel implementation

Completed. Implementation, data limits and validation evidence are recorded in
[`context-panel-validation.md`](context-panel-validation.md).

The existing right sidebar contains transient strings. Authoritative lifecycle and
tool events already persist in `session_events` and `application_activity`; the
session snapshot and SSE cursor own replay. Tool arguments/results remain private.
Workspace writes return verified operation-local `metadata.edit` changes. Existing
workspace reads/diffs enforce the workspace jail, protected paths and redaction.

Implementation uses those seams:

1. Add bounded, allowlisted inspection metadata to existing public tool events
   and a read projection to the existing snapshot. Keep raw arguments, command
   strings, output bodies, private model content and edit lines private. Display
   unavailable diagnostics explicitly. Confirm file changes only from successful
   executed edits with `changed=true`; never from a tool name or Git status.
2. Replace the sidebar presentation with Context Panel tabs and a persistent task
   summary plus Activity/Changes/Details subtabs. Keep pending approvals in chat.
   Preserve desktop control and provide a keyboard-accessible mobile drawer.
3. Add bounded Current/All Library reads. Current means artifacts owned by the
   selected conversation or referenced by its sent/selected Library attachments.
   Keep the Library independent of workspace folders. Reuse authenticated previews,
   thumbnails, List/Grid/Gallery, exact artifact IDs/revisions and attachment APIs.
4. Route internal Library drags and explicit Attach through the existing unsent
   attachment pipeline; no upload duplication or automatic message submission.
5. Validate lifecycle/history/replay, session isolation, bounds/privacy, confirmed
   edits, Library scopes and attachment identity, responsive layouts and keyboard
   interactions using isolated stores and model/browser fixtures.

No new frontend dependency or required static-asset route. Preserve all unrelated
worktree changes; do not stash, reset, commit or push. Explicit plans, raw tool
output, subagent details and token usage are shown only when a supported public
contract supplies them. The initial snapshot does not provide those diagnostics.
