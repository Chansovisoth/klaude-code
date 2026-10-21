# Connections layout validation

Validated on 2026-10-21.

Connections now shares Skills' compact collection rows, descriptions, confirmed-state
switches and native details layout. Rows use keyed reconciliation so an unchanged
refresh preserves their identity. Removal lives in details. The existing public
MCP inventory and reviewed mutation worker remain the source of truth; details
show status, transport, tool count, source and OAuth metadata.

Skills retains its existing DOM aliases while both destinations use shared
`integration-*` styles. Connections search supports typing and Enter submission.

Validation completed:

- Isolated Chrome at 320, 390, 768 and 1440px: rows, switch targets, details,
  Escape dismissal and focus restoration; settled phone screenshots inspected.
- Real local stdio MCP fixture: reviewed disable, enable/discovery and removal;
  cancelled reviews retain confirmed state, and changed definitions reject stale
  reviews without changing the switch value.
- Browser fixtures: OAuth restrictions, read-only presentation, unconfirmed
  acknowledgement locking, search/empty state, forced colors and sign-out cleanup.
  Read-only and lost-acknowledgement responses were simulated for these UI checks.
- Updated `scripts/webui_management_smoke.py` passed, including Connections
  details and cancelled-toggle regression, with zero console exceptions.
- Focused MCP inventory/mutation tests: 2 passed, 11 deselected.
- JavaScript syntax, focused Ruff and changed-file whitespace checks passed.

These checks use isolated data and fixture services. No external MCP server,
user configuration or physical device was used.

## Compact interface follow-up

Connections now combines All/Enabled/Disabled filters with search. A small
configured/enabled summary uses the same bounded inventory. Rows show confirmed
status, transport and tool count; an absent description no longer occupies a
separate line. Native Add and Details dialogs use a 480px maximum width and 20px
padding. The Add form explains HTTP setup, disabled-first creation and the
terminal entry points for local programs and sign-in. Successful operation
feedback remains visible after the inventory reload. Sign-out clears filters,
counts, notices and private details.

The existing reviewed add/enable/discover/disable/remove worker, fingerprints,
pending and unknown locks, OAuth restrictions and loopback boundary are unchanged.
No new backend API or credential surface was introduced.

Validation:

- `/tmp/klaude-mcp-finish-smoke.py` passed: status filters/counts, reviewed HTTP
  add-disabled, real stdio discovery/enable, disable/removal, stale rejection,
  cancellation, focus restoration and sign-out. OAuth, read-only and lost-ack
  cases include simulated HTTP responses; no external MCP server was contacted.
- `KLAUDE_TEST_INTEGRATIONS_ONLY=1 .venv/bin/python
  scripts/webui_management_smoke.py` passed at 320/390/768/1440px, including
  form dismissal, obsolete reviews and shared Skill/Knowledge regressions.
  An initial concurrent run exceeded the fixture's five-second Skill import
  wait; the isolated rerun passed. This was not a full management-suite run.
- Settled list/add/details screens passed overflow checks at 320/390/1440px
  in light/dark themes. Phone captures were visually inspected.
- The focused browser management/media backend suite passed **25 tests** in
  56.57 seconds. Repository Ruff, production mypy (222 files), modified JS syntax,
  whitespace checks and seven-wheel offline packaging passed.

Evidence: `/tmp/klaude-mcp-finish-smoke.log`,
`/tmp/klaude-mcp-integration-forms.log`, `/tmp/klaude-mcp-finish-visual.log`,
`/tmp/klaude-models-mcp-backend.log`, and
`/tmp/klaude-models-mcp-preview/`. Remaining browser gaps stay listed in
`coverage.md`; interactive OAuth, registry search and new local program setup
remain terminal operations.

## Password-authenticated LAN management

A live-host investigation found that the earlier UI pass did not make MCP actions
available on the production LAN listener: inventory advertised
`management_allowed: false`, and both review preparation and submission rejected
MCP operations solely because the request arrived over LAN. The running host had
current assets and profile-management capability, so reloading the page could
not resolve this restriction.

The HTTP adapter now applies one authorization rule at all three points. Local
sessions retain existing behavior. LAN sessions may manage MCP connections when
the host uses its owner password account; bootstrap-only embedded LAN hosts stay
read-only. Cookie/account-revision, exact Origin/CSRF, idle-turn, review ownership,
fingerprint, operation fence and durable receipt checks are unchanged. No new
mutation, shell capability or OAuth flow was added.

Focused regression covers both password and bootstrap LAN policy, including a
locally prepared review submitted through LAN, unauthenticated/cross-origin/invalid
CSRF rejection, explicit cancellation, HTTP add-disabled, real configured stdio
discovery/enable, disable, removal and stale-review rejection. The policy tests
set the isolated listener's LAN flag; the separate Chrome check uses an actual
private-address listener and a temporary password account.

Validation evidence:

- MCP-focused tests: **3 passed, 16 deselected in 14.25s**.
- `/tmp/klaude-mcp-owner-lan-smoke.py`: real LAN sign-in, enabled controls,
  reviewed add/enable/discovery/disable/remove, cancellation, sign-out and
  320/390/1440px layouts passed with zero console errors. Only a local MCP
  fixture ran; no user's definitions or external MCP service was changed.
- Repository Ruff and relevant production mypy (69 files) passed; seven-wheel
  offline package build/import/entry-point checks passed.
- Full focused management/media regression: **27 passed in 63.22s**.

The idle live managed host was gracefully reloaded after confirming no active
chat or background operations. Before/after witnesses verified the same session,
public message digest, model, mode/effort, revision, workspace and LAN address.
Browser cookies were revoked by the normal shutdown, so signing in again is
required. Reload evidence: `/tmp/klaude-mcp-live-reload.json`.

Implementation: `host.py`, focused regression in `test_web_management.py`, this
record, `coverage.md` and `AGENTS.md`. Logs:
`/tmp/klaude-mcp-lan-tests.log`, `/tmp/klaude-mcp-lan-regression.log`,
`/tmp/klaude-mcp-owner-lan-smoke.{json,log}`, and
`/tmp/klaude-mcp-lan-{ruff,mypy,package}.log`.

## Direct enable/disable switches

Skills and Connections now apply enable/disable directly from their row or
details switch. No confirmation dialog opens for `skill-enabled`, `mcp-enable`
or `mcp-disable`. Details stay open and update the confirmed status. Add/import
and deletion/removal retain their separate confirmation flows; configured OAuth
enable restrictions are unchanged.

The shared `submitToggleChange` helper accepts only those three operations. It
uses the existing snapshot/preparation and durable submission APIs, retaining
authentication, revisions/fingerprints, resource fences and operation receipts.
The switch remains at its saved value and is unavailable while pending. A
definitive failure restores availability without changing the saved state.
Lost acknowledgements keep the original request ID: polling resolves an accepted
effect, while an unresolved outcome stays locked without an automatic resubmit.
Leaving the section before preparation finishes discards the obsolete snapshot;
accepted effects retain existing background ownership.

Validation:

- `scripts/webui_refinement_smoke.py` passed with zero browser exceptions,
  including direct Skill saves, preparation and submission failures, navigation
  during preparation, a real stale worker rejection, and confirmed deletion.
  Its existing collection, theme, responsive, history and keyboard checks passed.
- `/tmp/klaude-direct-mcp-toggle-smoke.py` passed through an actual LAN listener
  with a temporary owner account: direct enable/discovery and disable, a double
  click producing one submission, no modal opening, details remaining open,
  definite failure, lost acknowledgement resolved from the real receipt, and
  unresolved-outcome locking. Add/removal still opened confirmation. The MCP
  process is a local fixture; failure responses are injected for those states.
- The maintained `KLAUDE_TEST_CONNECTIONS_ONLY=1` management smoke covers reviewed
  Add and rejected direct toggle behavior without contacting an external server.
- Modified JavaScript syntax, repository Ruff, Python smoke compilation,
  `git diff --check` and offline seven-wheel packaging passed.

Only static browser code, smoke expectations and documentation changed; the
running host serves the updated scripts. Reloading the browser loads the new
behavior without a host restart. Evidence:
`/tmp/klaude-direct-toggles-refinement.{json,log}`,
`/tmp/klaude-direct-mcp-toggle-smoke.{json,log}`,
`/tmp/klaude-direct-connection-regression.{json,log}`, and
`/tmp/klaude-direct-toggles-{ruff,package}.log`.
