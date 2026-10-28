# Chat scroll placement — 2026-10-28

The full-width `.chat-content` pane owns vertical conversation scrolling. Its
scrollbar reaches the chat pane's right and bottom edges while the reading column
stays centered and capped at 800px. Header and composer remain stationary. The
model/details bar retains its surface background and uses 4px vertical and 16px
horizontal padding around 44px controls (52px total height). This replaces the earlier 8px outer
top inset, keeping the same overall header space. The conversation starts below
this row, so the opaque background does not cover scrolling text. Messages,
pending decisions and queued messages share the outer viewport. Code toolbars
stick at its top edge instead of inheriting the old message inset offset.

The composer, availability notice and caption share a bottom overlay in the same
grid area as the scrolling viewport. A ResizeObserver reserves their measured
height at the end of the conversation, including growing drafts and attachments.
This keeps the last message above the composer while the scroll track extends
behind it to the pane's bottom. Space around the controls passes pointer events
through to the conversation.

Automatic following, distance checks, smooth-scroll interruption and Go to latest
use the same outer scroll owner. Message DOM, live regions and focus remain in
the conversation log. Existing control, Markdown and density fixtures now scroll
the outer pane. The layout fixture retains its snapshot promise during CDP
evaluation and disables live reconnection for deterministic presentation reads;
its model-picker check uses the current shared dialog.

Focused validation:

- `scripts/webui_chat_layout_smoke.py` passed 56 existing layout cases plus 14
  long-conversation cases: light/dark at 1440×960, 1024×768, 768×900, 390×844,
  320×640, 844×390 and 390×430. Checks cover scrollbar placement, one scroll
  owner, full-height track, centered content, no horizontal overflow, automatic following,
  preserving an earlier reading position, Go to latest, stationary controls, compact header height,
  final-message clearance with growing drafts, keyboard viewports, dialogs and
  sign-out cleanup. Zero browser exceptions.
- Desktop and phone screenshots were inspected. Evidence is in
  `/tmp/klaude-chat-layout-validation/`, including `report.json`.
- The Markdown smoke passed its initial streaming, code-scroll preservation and
  sticky-toolbar checks, then stopped at its pre-existing response-action count
  assertion (expects five buttons; the current renderer creates six, including
  the hidden Canvas action). The broader Markdown smoke is not green.
- Scoped Ruff for the layout/control scripts, JavaScript syntax, both bundle
  consistency checks and `git diff --check` passed. Existing E501 findings in
  the Markdown and Settings scripts remain outside this change.

These are isolated Chromium fixtures without live model calls. No full-suite,
cross-browser, physical-device or live-host verification is claimed. Existing
worktree changes were preserved.
