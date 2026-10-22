# Adaptive user message bubbles

User messages now use `width: fit-content`, right alignment and a maximum width
of `min(85%, 720px)`. Viewports up to 600px use 90% of the chat content width.
The previous fixed percentage left margins are removed, including the phone
override. Existing Material tonal colors, asymmetric corners and Comfortable /
Compact padding remain.

The existing article/body structure, text rendering and attachments are reused.
User text retains its literal Markdown, code fences, blank lines, tabs and line
breaks; this change does not enable Markdown execution in user messages. Long
URLs/unbroken strings wrap, while user preformatted/prompt/attachment containers
have bounded widths. Nested code and Markdown tables retain their existing
internal scrolling. Assistant layout, actions and message persistence are
unchanged.

Validation completed with temporary profiles and deterministic runtimes:

- `/tmp/klaude-user-bubbles-smoke.py`: **28** light/dark, Comfortable/Compact and
  viewport combinations at 320/390/600/601/768/1440/2560px. Every combination
  checks 12 user-message shapes: short text, emoji, normal text, long prose,
  long URL, unbroken string, multiline/tabbed text, literal fenced code, a file,
  four files without prompt text, legacy preformatted fallback and nested
  Markdown/code/table content. All bubbles are right-aligned and within their
  width cap, without page/chat/card overflow. Short Hi bubbles measure 47–59px;
  the largest messages stop at 720px. Five attachment cards fit in every case.
  Original text, line breaks and tabs remain intact. Assistant articles retain
  their full width. Updating the same message node grows/shrinks its bubble.
  Zero browser exceptions. Phone dark and desktop light captures inspected.
- Existing `scripts/webui_markdown_smoke.py` passed streaming, stable code and
  selection, Copy, message actions, literal user text, history, parser fallback,
  responsive layouts and logout with zero browser exceptions.
- Existing `scripts/webui_attachments_smoke.py` passed device/Library selection,
  private input, image thumbnails, sent cards/reload, active replies and logout,
  with zero browser exceptions.
- `/tmp/klaude-chat-scroll-working-smoke.py` passed jump-to-latest, reading
  position during real SSE, smooth-scroll interruption, loading animation,
  reduced motion and mouse/touch/keyboard behavior, including a short viewport.
- JavaScript syntax, indicator bundle consistency and whitespace checks passed.
  No backend/dependency changes; backend suites and package builds were not
  repeated for this browser layout change.

The initial broader Markdown regression exposed an existing scroll-indicator
lookup error when its status nodes were temporarily detached. A small null guard
in `app.js` now treats absent status nodes as inactive instead of throwing; the
rerun and scrolling regression passed. The original failure is retained in
`/tmp/klaude-user-bubbles-markdown.log`; final evidence is in
`/tmp/klaude-user-bubbles-markdown-final.log`.

Other evidence: `/tmp/klaude-user-bubbles-smoke.{json,log}`,
`/tmp/klaude-user-bubbles-attachments.log`,
`/tmp/klaude-user-bubbles-scroll.log`, and captures in
`/tmp/klaude-user-bubbles-preview/`. The running host served updated CSS and
JavaScript with HTTP 200. Only a browser refresh is required; no session or host
restart was needed.

Changed files: static `style.css`, the small `app.js` scroll guard, `AGENTS.md` and
this record. Unrelated changes were preserved; no commit or push. These are
focused Chrome checks, not a full-suite or physical-device claim.

Follow-up: the chat viewport now has an 8px inline-end inset between messages
and the scrollbar. Its native scrollbar uses `thin` width, the theme's outline
color and a transparent track. The stable gutter remains; browsers without
these scrollbar properties keep their native appearance and the message inset.
Forced-colors mode restores native scrollbar colors automatically.

`/tmp/klaude-chat-scrollbar-smoke.py` passed the same 28 layout combinations,
checking the 8px gap, thin themed scrollbar, bounded bubbles/attachments,
unchanged text and assistant article behavior, and high-contrast colors, with
zero browser exceptions. The desktop light capture was inspected in
`/tmp/klaude-chat-scrollbar-preview/`. The phone screenshot fixture displayed
the welcome screen after a background refresh, so it is not visual evidence
for the chat spacing. A final capture rerun was blocked on import by an
unrelated `IndentationError` in `chat_attachments.py:50`; that file was left
untouched. Evidence: `/tmp/klaude-chat-scrollbar-capture-blocked.log`. The earlier
successful layout measurements are recorded in the tool output; the later
failed attempt replaced the temporary JSON output.

The scrolling regression passed on an isolated rerun, including real SSE,
reading-position preservation, jump-to-latest, mouse/touch/keyboard controls,
loading states and logout (`/tmp/klaude-chat-scrollbar-scroll-rerun.log`). The
first concurrent run failed its live-reply follow assertion; that failure is
retained in `/tmp/klaude-chat-scrollbar-scroll.log`. The initial layout diagnostic
also needed its color assertion corrected to compare computed RGB colors.
Whitespace checks passed and the running host serves the updated CSS with
HTTP 200. This follow-up changes only CSS and these guidance/validation notes;
no backend suites or builds were repeated for the spacing change.
