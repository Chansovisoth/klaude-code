# Chat layout refinement — 2026-10-26

The chat page now gives the conversation a bounded reading column and places
frequent controls at the header and composer edges. Model selection no longer
competes with the message actions, and turn controls no longer float over text.

## Design and behavior

- The existing Model split selector sits in a quiet chat header. Both halves
  still open the same connection/model picker. XS faces, extended hit targets,
  top-layer placement, runtime revisions and idle/queue locks remain.
- Messages, pending decisions, queued messages and the composer share an 800px
  maximum column. The input uses the full composer width. Attachment plus,
  Thinking and Plan sit below it; existing device/Library attachment handling
  and effort selection retain their original controls and handlers.
- During an active reply, Stop occupies the primary right corner. A draft
  reveals Queue and Steer beside it. On composers up to 430px wide, unavailable
  Thinking/Plan controls yield space until idle. Their current values remain
  available in Conversation details. Wider controls wrap if necessary.
- The passive native Conversation details popover holds permissions, status,
  Thinking/effort, Plan and session identity. It clamps to the visual viewport,
  follows header resizing, closes on outside interaction, and restores focus on
  Escape. Opening another selector, navigation, session change or sign-out closes
  it. Opening details never claims chat control or submits a mutation.
- Notices remain visible below the composer. AI activity stays in the
  conversation, retaining the existing indicator identity and lifecycle.
- The welcome screen keeps the existing heading and prompt actions with a
  smaller emblem and compact outlined shortcuts, without the extra marketing
  paragraph or large suggestion cards.

Klaude's Material semantic colors, typography, local icons, finite corners,
focus/state feedback and reduced-motion settings remain authoritative. No
framework, dependency, route, provider call or backend permission change was added.

The placement adapts the model/submit hierarchy described in
[Claude's getting-started guide](https://support.claude.com/en/articles/8114491-get-started-with-claude)
and the grouped composer actions described in
[ChatGPT release notes](https://help.openai.com/en/articles/6825453-chatgpt-release-notes).
It uses Klaude's own controls and capabilities; these are design inputs, not a
claim of reproducing either service's current interface.

## Validation

- `scripts/webui_chat_layout_smoke.py` passed **56** layout cases: light/dark,
  empty/conversation/active/active-draft, and 1440×960, 1024×768, 768×900,
  390×844, 320×640, 844×390 and 390×430. It checks page/composer overflow,
  bounds, reading width, input width, action overlap and contextual action
  visibility. Details checks cover viewport fit, Escape/focus return, selector
  exclusion, navigation/session/sign-out cleanup and passive operation. A
  desktop Context Panel check also passes. Zero browser exceptions.
- `scripts/webui_composer_smoke.py` passed desktop/mobile input, Shift+Enter,
  IME/repeat guards, duplicate-send suppression, actual sending/activity motion,
  retained indicator identity, legacy asset/activity fallback, failed-send draft
  retention and sign-out cleanup. Its test login now explicitly supplies the
  fixture account's required username.
- `scripts/webui_models_smoke.py` passed configured and legacy catalogs, actual
  fixture runtime changes, Thinking/effort/Plan behavior, responsive selectors,
  failures, navigation/history and sign-out checks. Zero browser exceptions.
- `scripts/webui_control_smoke.py` passed real two-client reviews, questions,
  queue/steer/cancel, terminal control acquisition, Library changes, navigation
  and fencing races. Its old floating-control checks now verify real composer
  hit targets and transcript readability in **10** responsive light/dark cases.
  Its fixture login also explicitly supplies the required username.
- Focused host/account tests: **49 passed**. Changed Python files pass Ruff;
  JavaScript syntax, both deterministic asset bundle checks and `git diff --check`
  pass.

Screenshots and measurements: `/tmp/klaude-chat-layout-validation/`; initial
before/after captures: `/tmp/klaude-chat-layout/`. Desktop conversation, phone
welcome, narrow active-draft and Context Panel captures were visually inspected.
Early checks caught and corrected native Escape handling, a narrow active-draft
flex overlap and an inherited emblem SVG size. The final matrix passed after
the compact phone refinement.

## Limits

Browser checks use isolated temporary accounts, fixture conversations/runtimes
and Chromium emulation. They do not exercise real models, personal sessions,
physical touch devices, Safari or a full accessibility acceptance audit. Layout
fixtures verify presentation; the separate composer/model/control scripts verify
the existing functional paths.

Repository-wide Ruff remains failing with **63 E501 errors in 11 untouched files**;
none are in changed files. The full repository test suite and packaging were not
run. No live host was restarted, and no commit or push was made.

Implementation: `static/index.html`, `static/app.js`, source `static/expressive.css`
and generated `static/style.css`, plus the browser checks named above. Product
guidance and coverage are updated in `AGENTS.md`, `coverage.md` and
`chat-split-controls-validation.md`.
