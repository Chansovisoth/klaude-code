# Chat Canvas, conversation search and duration — 2026-10-26

The phone Chat view has 8px less combined bottom spacing, retaining navigation
and keyboard safe areas. Successful assistant replies show `Worked for 1m 11s`
from recorded application turn admission/completion times. Only the final public
assistant message in a completed turn receives its duration. Untimed legacy
history stays unlabeled; an older host can still supply the latest inspector timing.

Conversation search now queries saved user/assistant dialogue and conversation
names before workspace/archive filtering and the result limit. Phrase/term
ranking and matching excerpts locate text beyond the recent 30 conversation
previews. Requests debounce by 250ms; generation and authentication guards discard
late results. Queries are bounded to 200 characters/eight terms. The database
reader excludes tool/system rows and the private model_content column. An older
host rejecting query filters falls back to recent title/preview matching.
This is text relevance ranking, not semantic embedding search.

Canvas is available from the Chat header/menu and code/response actions. Desktop
uses a dock beside Chat; phone/tablet uses a native fullscreen dialog. The editor
supports named code/writing drafts, a document switcher, Edit/Preview keyboard tabs,
syntax preview, Markdown rendering and the existing owner-authenticated HTML/SVG
preview route in an empty-sandbox iframe. Downloads contain the edited source.
Ask Klaude appends selected text or the draft to the existing composer without
submitting or replacing an existing prompt. Closing retains the drafts in the
current tab; Discard removes the selected draft. Session changes, sign-out and
page exit clear the documents and previews. Drafts are bounded to 20 documents
and 128,000 characters each; chat excerpts are bounded to 16,000 characters.

Focused isolated Chromium fixture `/tmp/klaude_canvas_search_check.py` passed:

- 1440/390/320px canvas bounds, desktop height, mobile reflow and no overflow.
- Search finds a saved message beyond its first 2,000 characters despite 35 newer
  conversations; matching snippets are visible in the drawer.
- Tool-only and other-workspace search markers are excluded.
- A recorded 71-second completed turn displays `Worked for 1m 11s`.
- Code edits, syntax preview, close/reopen retention and session cleanup.
- Markdown preview, sandboxed HTML preview, exact source/filename download, and
  Ask Klaude preserving the existing unsent prompt without starting a turn.
- No browser exceptions. Screenshots: `/tmp/klaude-chat-layout/canvas-{width}.png`.

Focused unit checks: 27 application bridge, four parallel session, and 37
coordination/session tests passed (68 total). The four local-server tests initially
could not open sockets in the sandbox and passed after rerunning with sockets
allowed. Scoped Ruff, JavaScript syntax, both generated asset bundle checks and
`git diff --check` passed.

The Python host must restart to enable full saved-dialogue search and historical
turn duration projection. This slice did not restart the live host. No actual
model generation, workspace file mutation or real model download was performed.
Persistent Canvas history, automatic AI document revisions and conversation
embedding indexing remain future work. Physical-device keyboard/touch behavior
and the full repository suite were not exercised.

## Average generation rate — 2026-10-26

The completed reply footer adds `Avg 25.0 tokens/s` beside Worked for. The rate is
sum(reported output tokens) / sum(generation seconds) across completed model
requests in the turn, including reported thinking output. Provider evaluation
nanoseconds are preferred. Providers without that timing use the monotonic model
request duration, including prompt/transport overhead; the tooltip identifies
the timing basis. Tool execution/wait time is excluded. Missing token accounting
omits the rate rather than estimating tokens from text. Provider metadata is
cleared before synthesis calls so an earlier request cannot supply stale usage.

The shared Agent emits only validated numeric statistics and a fixed timing
classification. The application persists those fields in its completion record
and projects them onto the final saved assistant message. The projection
revalidates and recomputes the rate; arbitrary provider fields and stored claimed
rates are not exposed. Untimed or older replies without reported counts have no
rate. A host restart enables this backend change; new replies then retain their
rates across reloads.

Focused calculation/application/coordination checks: 65 passed. The isolated
`/tmp/klaude_chat_token_rate_check.py` passed at 1440/390/320px with the duration
label retained, persisted rate recomputation, private-field exclusion, no
overflow and zero browser exceptions. Screenshots are under
`/tmp/klaude-chat-layout/chat-token-rate-{width}.png`. Scoped Ruff, helper typing,
JavaScript syntax, bundle and diff checks passed. No live host restart or real
model generation was performed for this validation.

### Response menu duration placement — 2026-10-26

Worked for is now a compact metadata row below the timestamp in the response's
three-dot Branch/Retry menu. Only average tokens/s remains below the response.
Opening/updating the menu retains its existing actions, keyboard behavior and
viewport positioning. The isolated `/tmp/klaude_chat_worked_menu_check.py` passed
at 1440/390/320px: duration absent from the transcript and present in the menu,
rate footer intact, Branch/Retry retained, menu within the viewport, Escape
closure and zero browser exceptions. JS syntax, CSS bundle and diff checks passed.

### Contextual Canvas and Sources — 2026-10-26

Sources is visible only when the reply contains parsed HTTP(S) references. The
response Canvas shortcut is limited to writing of at least 600 characters without
code fences; code blocks keep their own Canvas action. Header/menu Canvas stays
hidden until the conversation has eligible content or the current tab has drafts.
Existing drafts remain accessible even if the source reply no longer qualifies.
Visibility follows rendered streaming updates, navigation and session cleanup.

The isolated `/tmp/klaude_contextual_actions_check.py` passed at 1440/390/320px:
short replies hide both shortcuts, links reveal Sources, code/writing reveal the
appropriate Canvas entry, updates remove obsolete actions, retained drafts keep
Canvas accessible and session changes clear it. No overflow or browser exceptions.
JS syntax, app bundle and diff checks passed.

### Writing-request gating — 2026-10-27

Canvas eligibility now uses the corresponding preceding user message, including
when restoring history and updating streamed replies. A document shortcut requires
an explicit writing/revision request plus at least 600 characters in three rendered
paragraphs. Length alone does not qualify an explanatory answer. Code shortcuts
also require an explicit creation/rewriting request. Negative requests and questions
about how to write are excluded by the local intent heuristic. Existing drafts
retain their manual launcher. Nothing automatically opens the panel.

The isolated `/tmp/klaude_canvas_writing_intent_check.py` passed at 1440/390/320px:
restored writing versus explanation replies, paragraph gating, negative requests,
revision requests, explicit code creation, no automatic opening, no overflow and
zero browser exceptions. JS syntax, bundle consistency and diff checks passed.
