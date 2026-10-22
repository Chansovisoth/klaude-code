# Unified Tools & Permissions

The subsequent [staged save workflow](settings-save-workflow-validation.md)
replaces the individual Review actions and confirmed-state Settings switches
described below. This document records the original UI merge and backend audit;
the tool registry and independent availability/approval semantics remain valid.
The current segmented-control refinement is documented at the end of this file.

Settings → Agent replaces its separate Tools and Permissions disclosures with
one **Tools & Permissions** disclosure. The 12 supported browser read tools are
grouped into File Operations, Git, Web, Knowledge & Skills, and Utilities. Each
row has its existing tool name, a local SVG icon, a short description, a
confirmed-state enable switch, and its approval preference with Review.

The UI pairs existing fields from `/api/v1/settings/agent`. It only creates a
control when the response supplies the corresponding supported field type.
The presentation metadata does not add tools to the registry. Unknown future
supported fields have a generic Other tools group. Existing field IDs, values,
revisions, reviewed worker requests and persistence are retained.

## Verified backend semantics

| UI control | Existing stored value/mechanism | What remains independently enforced |
| --- | --- | --- |
| Enable switch | `tool_availability.<name>`; refreshed into `disabled_tool_names` | Disabled tools are excluded from selection and blocked if requested |
| Automatic | `permissions.<name> = allow` | Skips that tool's approval prompt; workspace boundaries, protected files, network validation and other access checks still apply |
| Ask first | `permissions.<name> = ask` | Uses the existing injected approval path and its current decision semantics |
| Deny | `permissions.<name> = deny` | PermissionGate blocks execution even if availability is enabled |

Inspection sources:

- `packages/application/src/klaude_application/browser_settings.py`: the 12-tool
  settings allowlist, boolean/policy validation, exact review and field-level CAS.
- `packages/application/src/klaude_application/browser_tools.py`: availability
  application, permission refresh, and forced ask for configured MCP/file edits.
- `packages/core/src/klaude_core/agent.py`: disabled tools are filtered and rejected.
- `packages/core/src/klaude_core/permissions.py`: existing allow/ask/deny gate.
- `apps/webhost/src/klaude_webhost/host.py`: browser read-tool allowlist, bounded
  reviews, loopback edit activation and LAN restrictions.

Changing availability does not rewrite the approval preference. Disabled tools
retain and display that preference, while its selector and Review are disabled.
Both controls are unavailable while either field has a pending or unconfirmed
operation, preventing conflicting row interactions. Switches retain the confirmed
value until review and persistence complete. Policy selection remains a draft
until Review/Confirm; cancellation does not save it. The existing operation
receipts, field revisions and stale-save handling remain in place. No new mode,
API, field, authorization path or backend behavior was introduced.

## Additional rules and responsive presentation

The MCP section links to Integrations → Connections, where availability remains
managed per server. Configured MCP calls retain their required review unless
denied; there is no Automatic selector for MCP in this panel.

The collapsed **Advanced permission rules** disclosure explains independent
workspace/network protections and links to the existing Workspaces controls for
file editing. Edit activation retains clean-worktree/branch checks, loopback-only
activation and exact review for each edit. LAN cannot activate or approve edits.
Shell execution and Git mutations remain unavailable in the WebUI. Additional
terminal policies remain in terminal settings; the panel does not offer fake
enable or approval controls for these operations.

Rows reuse Material switches, tonal surfaces, borders, rounded disclosure icons,
native selects, Review buttons and existing colors. Tool groups use responsive
grids; row contents stack based on the actual card width. Tool names and
descriptions wrap, controls retain their existing targets, and saved policy
values remain readable while disabled. Labels identify each tool independently;
pending-state messages use a polite status and are only replaced when changed.

Changed implementation files: `static/management.js` and `static/style.css` under
`apps/webhost/src/klaude_webhost/`. The focused browser check and `AGENTS.md` are
updated. The existing untracked Models UX/reliability review is preserved.

## Validation

- `.venv/bin/pytest tests/unit/test_browser_tools.py tests/unit/test_web_management.py -q`:
  **27 passed in 47.95s**. Includes shared availability/policy application,
  authenticated settings, reviewed writes, field-level CAS and rejected unsupported
  shell policy requests. These are existing backend tests; enforcement code is
  unchanged.
- `scripts/webui_settings_smoke.py`: **162** light/dark panel/viewport cases on
  password and bootstrap hosts, from 320px through 2560px, with zero JavaScript
  exceptions. It expands all groups for overflow and control-alignment checks,
  verifies the single combined section and supported policy values/labels, and
  exercises native keyboard expansion, cancellation and real reviewed writes.
  Deny survives disabling/re-enabling; approval controls and submission are blocked
  while disabled; cancelling leaves the stored policy unchanged. Workspace and
  MCP links reach their existing destinations. Other category drafts, Theme Apply,
  history, model cancellation and account cleanup also pass.
- Phone and desktop Tools & Permissions captures were visually inspected in
  light/dark. Focused Ruff, Python compilation, modified JavaScript syntax and
  `git diff --check` passed.

Evidence: `/tmp/klaude-tools-permissions-backend.log`,
`/tmp/klaude-tools-permissions-settings.json`, and captures in
`/tmp/klaude-settings-tabs/*-tools.png`.

This is focused contract and Chrome validation, not a full-suite or physical-device
claim. No stash, reset, discard, commit or push was performed. Reload the WebUI to
load the updated static assets; no backend restart is required by this change.

## Segmented approval controls

Settings → Agent → Tools & Permissions now uses compact **Auto | Ask first |
Deny** segments. Each tool presents its existing local icon, name and enable
switch on one header row, followed by its muted description and approval choices.
Individual outlined cards and repeated Approval/Enabled labels are removed;
transparent rows use subtle bottom dividers. Existing tool groups, Connections
and advanced workspace-rule links remain.

The tool grid has two columns when desktop card content is at least 496px wide,
and one column on mobile (768px and below) or narrower cards. Names/descriptions
wrap, each segment has a 44px touch target, and styles use the existing Material
outline, surface, secondary-container and text roles. These selectors are scoped
to tool settings and do not alter Appearance's segmented controls.

The existing `.segmented` native radio primitive is reused, with one fieldset and
tool-specific visually hidden legend per approval policy. Radio values remain
`allow`, `ask` and `deny`; Auto is only the visible label for `allow`. Native
Space/arrow selection, labeled click targets and visible keyboard focus are
preserved. Group descriptions explain the existing permission semantics.

Changing either control stages the existing category-local draft. Disabling a
tool disables its fieldset without rewriting the checked approval value. The
draft and confirmed preference survive re-enabling; disabled controls cannot
stage a policy change. Both controls lock during pending/unconfirmed saves.
Discard, Save changes, access-relaxation confirmation, conflict handling,
restrictive-policy-before-activation ordering, receipts and field revisions use
their existing paths. No backend API, permission enum or enforcement changes.

Validation:

- Existing browser-tool and WebUI settings tests: **31 passed in 54.38s**.
  Availability, permissions, reviewed persistence and backend rejection behavior
  remain intact; production backend files were not changed for this refinement.
- The updated real-worker save smoke passed native Space/arrow policy selection,
  staged changes without writes, Discard/navigation, save and access confirmation,
  independent availability/policy persistence, disabled policy retention,
  restrictive-policy ordering, batches over 16 changes, concurrent writers,
  partial success, lost acknowledgements, exact unknown-result recovery and
  logout cleanup, with zero browser exceptions.
- The extended Settings layout smoke passed **162** light/dark category/viewport
  cases across password/bootstrap hosts at 320–2560px. It verifies column counts,
  first-row name/switch alignment, 44px segments, wrapping and transparent rows,
  selected policy retention while disabled and preservation of the broader
  Settings workflows. Desktop/mobile captures were visually inspected.
- Draft-store Node tests, modified JavaScript syntax, focused Ruff, smoke Python
  compilation and whitespace checks passed.

Evidence: `/tmp/klaude-tool-segments-backend.log`,
`/tmp/klaude-tool-segments-save.{json,log}`, `/tmp/klaude-tool-segments-drafts.log`
and layout checks under `/tmp/klaude-tool-segments-settings-final.{json,log}`.
Changed files: static `management.js`/`style.css`, both Settings smoke scripts,
`AGENTS.md` and this record. Unrelated worktree changes remain intact; no stash,
reset, commit or push.
