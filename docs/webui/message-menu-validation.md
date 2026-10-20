# Message menu validation

Reviewed 2026-10-20. The three-dot message action opens an anchored popover with
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

Retry copies the prefix before the selected reply's original user prompt into a
separate conversation, then submits that exact prompt through the ordinary owned
worker and turn admission. It preserves the source conversation and excludes its
old answer and later messages. Retrying the first reply correctly starts with an
empty prefix and admits the prompt once. This implementation preserves retries
as separate conversations; it does not add an in-place answer-variant selector.

The application session service and typed SessionDirectory operation call the
transactional Memory fork. The copy validates the exact source/assistant row and
rejects unresolved leases and queued work under SQLite's write transaction. Both
HTTP actions require the existing cookie, CSRF/Origin, source-session and browser
control checks, and an idle application. Message IDs cannot select another
session's records. The host retains bounded per-request receipts for duplicate
requests within its browser-session lifetime; Retry uses a deterministic request
ID for ordinary durable turn admission. A restart revokes those browser sessions.
Neither action activates tools or changes a Git branch; browser file-edit
activation is cleared before generation, as for ordinary session switching.

## Verification

Final focused run: **109 passed in 50.04s**, covering
`test_application_sessions.py`, `test_webhost.py`,
`test_application_coordination.py` and `test_memory.py`.

The isolated Chrome/CDP smoke script exercises real shared-worker SSE and saved
history with a deterministic agent, without contacting a model provider. It
passed message timestamps, exact action labels, Escape dismissal, viewport-bounded
menus at 320/390/768/1440 pixels, branching without generation, explicit Retry,
unchanged original history and a single user prompt in the retried conversation.
Existing formatting, clipboard, speech fixture, streaming/selection and six-theme
checks also passed, with no JavaScript console errors or external requests.

Focused Python tests cover exact message cutoffs, preserved private prefix data,
first/later-prompt retries, foreign and oversized row IDs, unresolved work,
CSRF and stale sessions, browser control, duplicate request rejection/replay,
workspace preservation and clearing file-edit activation. Production core,
application and WebUI mypy checks passed across 128 source files. Ruff and
JavaScript syntax checks passed. This is focused validation, not a full repository
or device accessibility acceptance run.

The idle managed host was restarted to load the new routes and timestamp
projection. Its current session, exact saved public messages, model/mode/plan,
workspace and LAN listener were verified unchanged. Its public snapshot now
advertises message actions and supplies saved timestamps. No branch, Retry or
generation was invoked on the user's live conversations during validation.

## Reference research

The user supplied the menu's timestamp/Branch/Retry layout. Official OpenAI
documentation was searched and fetched, including
[What's new](https://learn.chatgpt.com/docs/whats-new) and
[Projects and chats](https://learn.chatgpt.com/docs/projects?surface=app).
These public pages did not establish the exact current ChatGPT web message-menu
appearance. The implementation follows the supplied layout; it does not claim a
pixel-exact inspection of an authenticated ChatGPT account or identical Retry
storage behavior.
