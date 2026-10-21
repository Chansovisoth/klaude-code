# WebUI date, time and timezone

The browser agent now exposes the existing `current_time` tool name through its
read-only application tool registry. It reads the host clock without network or
model contact and returns the weekday, local ISO timestamp, timezone/UTC offset
and UTC timestamp. It is allowed by the standard tool policy, while explicit
availability and permission settings remain authoritative.

Settings → Agent has an initially expanded Date and time section. Its native
Timezone selector lists installed IANA names and UTC, with Automatic following
the host timezone. The existing setting-save review, private preference store,
field revision and owned worker save `time_settings.timezone`; no new endpoint
or dependency was introduced. Invalid names, paths and malformed values are
rejected. Tool calls may supply another timezone without changing preferences.
This setting governs WebUI conversation context and clock reads, not operating
system configuration or unrelated file/session timestamp presentation.

The browser's prompt builder refreshes clock context before every turn, including
long-lived or resumed chats. Old Local time/Timezone lines in cached machine
context are replaced; original collection timestamps and machine/location data
retain their meaning. A fresh bounded clock block is also present when machine
context is disabled. Timezone changes apply on the next turn and do not imply a
physical location. Standard ZoneInfo data supplies daylight-saving behavior.

Validation completed:

- **42 passed in 48.35s** across time settings, browser tools and browser
  management. Tests include year/date rollover, both DST transitions, automatic
  host time, invalid timezone rejection, explicit override without persistence,
  fresh time/tool execution through real Agent turns, permission handling,
  next-turn timezone refresh, reviewed saves and stale-revision rejection.
- WebUI registry and exact saved-session startup: **2 passed, 38 deselected**.
- The extended Settings Chrome smoke passed password and bootstrap hosts,
  **90** light/dark panel/viewport combinations at 320/390/768/1024/1440px,
  draft preservation, accessible helper text, timezone cancellation/save and
  all existing Settings regressions. Zero browser exceptions. Desktop and
  phone timezone captures were visually inspected.
- Repository Ruff, production mypy (**223 files**), modified JavaScript syntax,
  smoke Python compilation and whitespace checks passed. Seven-wheel offline
  packaging built/installed the workspace and checked assets/imports/entry points.

The initial clock integration fixture constructed a bare Config without the
production `current_time: allow` policy and waited for approval. The fixture now
declares that policy and has bounded waits; no production permission override
was introduced. A retry-after-cancel browser assertion also now waits for the
native close event to clear its pending state. Final focused checks passed.

Evidence: `/tmp/klaude-date-time-tests-final.log`,
`/tmp/klaude-date-time-host-tests.log`,
`/tmp/klaude-date-time-settings-final.{json,log}`,
`/tmp/klaude-date-time-{ruff,mypy,package}-final.log`, and captures under
`/tmp/klaude-settings-tabs/`. These tests use temporary settings, scripted model
runtimes and local fixture services; no live inference or physical-device
validation is claimed.

Implementation: new `klaude_core/time_settings.py`; application
`browser_tools.py`/`browser_settings.py`; static `management.js`, `library.js`,
`index.html` and `style.css`; focused unit tests and `webui_settings_smoke.py`.
`AGENTS.md` and `coverage.md` describe the supported behavior. Unrelated worktree
changes are preserved.

Live activation completed alongside the Model Defaults dropdown fix. Before the
graceful managed-host reload, the host had zero active turns, queued entries,
pending interactions and active domain operations. After startup, the session,
conversation digest/count, selected runtime, workspace, LAN configuration and
preference/hosting file hashes matched. The automatic host timezone is
Asia/Phnom_Penh; no timezone or tool-permission preferences were changed.
Evidence: `/tmp/klaude-model-defaults-live-reload.json`. Existing shutdown behavior
revoked browser cookies, so users must reload and sign in again.
