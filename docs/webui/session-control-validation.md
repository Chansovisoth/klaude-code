# Session control without a separate handoff

Validated on 2026-10-20 with isolated state, the shared Agent, deterministic model
responses, real loopback HTTP, the managed Unix socket, and Chrome 148.

Browser actions now acquire control as part of the chosen action. The browser
refreshes control, claims it if another client owns it, and submits the original
action through the existing API. There is no Take control button or observer
lockout on idle model/mode/session controls, Cancel, Steer, or reviewed Library
changes. Opening, focusing, polling and watching a tab never claim control.

Authenticated owner clients see the same pending tool reviews and questions.
Responses acquire control before the existing fenced decision checks. A control
change alone leaves the question form and its local draft intact. Hosted terminal
review and cancel actions also acquire control; invalid target IDs do not.

The browser may retry a competing acquisition once, before the action. It never
automatically repeats a mutation with an uncertain outcome. Authentication and
session changes abort the action; target IDs, settings/artifact revisions, request
receipts, cookie/CSRF checks, LAN restrictions and the single model-worker lease
remain enforced.

Submitted queue records are retained for receipt/history reads. They are excluded
from pending snapshots and idle-boundary guards, so finished queued turns do not
leave model selection, navigation or Library confirmation blocked.

## Product references

[ChatGPT's cross-device documentation](https://learn.chatgpt.com/docs/enterprise/cloud-local-access)
describes continuing a Work conversation across devices.
[Claude's unified experience documentation](https://support.claude.com/en/articles/17444462-set-up-and-manage-the-new-unified-claude-experience-for-your-enterprise-organization)
describes starting work on desktop and picking it up on web or mobile. These
sources establish continuity across clients, but do not document their arbitration
of simultaneous actions. Automatic acquisition on explicit action is Klaude's
implementation choice for that experience.

## Checks

`scripts/webui_control_smoke.py` passed with two tabs sharing one account cookie
and separate client IDs. It exercised:

- Idle Plan changes, approvals and question replies from the other tab.
- Watching/focus without takeover and question-draft retention after takeover.
- Cancel and Steer on another client's live turn, with queued follow-up completion.
- Hosted terminal approval/cancel, including an invalid target without takeover.
- Reviewed Library tags and new-session navigation after queued work.
- Deterministic competing-claim, lost-acknowledgement, session-change and sign-out
  races in the real page; mutations execute at most once per attempt.

106 tests passed across WebUI host/accounts/Library and application coordination,
bridge and session suites. The existing Chrome Markdown/streaming/layout smoke
also passed with no console errors. Ruff, JavaScript syntax checks and production
mypy for the application and WebUI packages passed. These are focused checks,
not a full repository test run or live
model evaluation. No production host, sessions, credentials or model settings were
changed by the checks.
