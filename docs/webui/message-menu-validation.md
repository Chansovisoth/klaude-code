# Message menu validation

Updated 2026-10-25. The three-dot message action opens an anchored popover with
the real saved message timestamp, then **Branch in new chat** and **Retry**.
The timestamp uses the browser's locale and timezone, with a month/day and a
12-hour time. Missing timestamps are labelled unavailable rather than invented.
The menu fits phone viewports and supports arrow keys, Home/End, Escape, Tab and
outside-click dismissal. Other response actions keep their existing positions.

## Behavior and boundaries

Branch creates and selects a new conversation containing all stored records
through the exact selected assistant row, including private continuation records
within that prefix. Later prompts and answers are excluded. Saved timestamps,
workspace binding, runtime and plan settings are retained. No generation starts.

Retry keeps the same session ID and resubmits the selected reply's original input
in the current conversation through the ordinary owned worker and fenced turn
admission. It retains current runtime/model, workspace, plan and file-edit
settings. The repeated prompt is retained in the execution transcript for normal
turn admission, but omitted from browser message display. Saved prepared private
attachment input is reused without appearing in public projections.

The previous answer becomes a collapsed **Previous response** disclosure above
the new streamed/saved answer. Its full existing bounded body, syntax colors,
previews and response actions remain accessible when expanded. Repeated retries
share one response group; earlier versions collapse and the latest answer remains
expanded. Regenerating an older reply places its replacement in that reply's group
while retaining subsequent conversation messages. Expansion choices survive
ordinary snapshots in that tab; reloading starts previous responses collapsed.
Durable grouping is shared across owner clients and survives process restarts.
Cancellation, failure or interrupted execution retain the original response and
any saved partial. An interrupted worker still requires explicit reconciliation.

Branch uses the application session service, typed SessionDirectory operation and
transactional Memory fork. Retry admits its grouping record and repeated input in
the same SQLite transaction as the worker lease. It validates the selected saved
assistant, its original prompt, controller epoch and idle queue under that write
transaction. Source IDs cannot select another session's records. Both
HTTP actions require the existing cookie, CSRF/Origin, source-session and browser
control checks, and an idle application. Message IDs cannot select another
session's records. The host retains bounded per-request receipts for duplicate
requests within its browser-session lifetime; Retry uses a deterministic request
ID and source-specific fingerprint for durable admission. Replaying an accepted
request returns its receipt without another generation, even after the host's
receipt cache is lost. A restart revokes browser sessions. Neither action
activates tools or changes a Git branch. Retry preserves the same session's edit
settings and normal tool review requirements. Forks remap response-group row IDs,
and session deletion/clear removes their metadata.

The browser requires `message_retry_in_place` before enabling Retry. An older
running host gets restart/reload guidance; the new client never falls through to
the old fork-on-Retry implementation.

## Verification

Current focused run: **118 passed in 62.46s** across `test_message_retries.py`,
`test_webhost.py`, `test_application_sessions.py`,
`test_application_coordination.py` and `test_memory.py`. This covers repeated
responses, accepted-request replay after host/application cache loss, cancelled
and failed retries, expired-worker partials, stale control and queued work,
private prepared input, older sources outside the history window, group remapping
on fork and metadata cleanup on reviewed deletion. Focused Ruff, JavaScript
syntax, mypy for the four changed production Python files and `git diff --check`
passed.

The updated Chromium fixture passed with zero console errors or external
requests. It checks the paused streaming replacement, expanding the original,
repeated Retry on an older response while retaining later exchanges, unchanged
session ID, reload persistence and 320/390/768/1440px disclosures. Screenshot:
`/tmp/klaude-markdown-preview/retry-same-chat-320.png`.

The original 2026-10-20 implementation's focused run was **109 passed**, covering
`test_application_sessions.py`, `test_webhost.py`,
`test_application_coordination.py` and `test_memory.py`.

The isolated Chrome/CDP smoke script exercises real shared-worker SSE and saved
history with a deterministic agent, without contacting a model provider. It
passed message timestamps, exact action labels, Escape dismissal, viewport-bounded
menus at 320/390/768/1440 pixels and branching without generation. The updated
fixture checks same-session Retry, a collapsed original response above the paused
streaming replacement, access to the old answer, one visible original user prompt,
reload persistence and narrow expanded/collapsed disclosures.
Existing formatting, clipboard, speech fixture, streaming/selection and six-theme
checks also passed, with no JavaScript console errors or external requests.

Focused Python tests cover exact message cutoffs, preserved private prefix data,
first/later-prompt retries, foreign and oversized row IDs, unresolved work,
CSRF and stale sessions, browser control, duplicate request rejection/replay,
workspace preservation and clearing file-edit activation. Production core,
application and WebUI mypy checks passed across 128 source files. Ruff and
JavaScript syntax checks passed. This is focused validation, not a full repository
or device accessibility acceptance run.

The 2026-10-25 checks use isolated temporary workspaces and deterministic agent
fixtures, with no live provider calls or production-host restart. Running older
hosts need a restart and browser reload for the new Retry contract and capability.

## Reference research

The user supplied the menu's timestamp/Branch/Retry layout. Official OpenAI
documentation was searched and fetched, including
[What's new](https://learn.chatgpt.com/docs/whats-new) and
[Projects and chats](https://learn.chatgpt.com/docs/projects?surface=app).
These public pages did not establish the exact current ChatGPT web message-menu
appearance. The implementation follows the supplied layout; it does not claim a
pixel-exact inspection of an authenticated ChatGPT account or identical Retry
storage behavior.
