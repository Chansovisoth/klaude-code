# Chat-edge resizing and sidebar cleanup

Implemented 2026-10-22 using the existing app bundle, theme tokens and layout.
No dependencies, backend changes, commits or pushes.

The central surface has two invisible resize zones in its surrounding frame.
They sit outside the content so scrollbars, file drops and message controls keep
their existing targets. A short grip appears on hover, keyboard focus or drag;
there is no permanent separator line. The Context Panel's outer border and
structural row dividers are removed. Tonal selection, spacing, hover and focus
styles retain the hierarchy. Mobile drawers keep their existing sizing and
shadow, with no outline.

Dragging either edge adjusts the corresponding docked panel allocation while
holding the opposite edge still. The conversation column stays between 216 and
420px, and Context between 280 and 560px, including its existing 12px gutter.
Chat retains at least 400px at desktop sizes. Narrower windows temporarily clamp
the displayed sizes without replacing saved preferences; expanding restores
them. The navigation rail and existing 850/1240px drawer breakpoints are retained.
Resize controls disappear when the adjacent panel is collapsed or becomes a
drawer. No panel is automatically collapsed by resizing.

Widths are stored independently of settings drafts and Theme under the bounded
`klaude.webui.chat-width.v1` localStorage key. Missing, invalid or unavailable
storage falls back to responsive defaults; failed saves retain the usable layout
for the page. Other tabs can synchronize through the existing storage event
pattern. No server setting or conversation state is written.

The controls expose vertical separator semantics, labels, numeric bounds and
current chat width. Arrow keys move the selected edge; Shift uses a larger step
and Alt a one-pixel step. Home/End select minimum/maximum chat space available
from that edge. Enter or double-click resets that edge to its responsive default.
Pointer capture keeps dragging stable; Escape, pointer cancellation, losing
capture, blur and sign-out cancel unfinished drags. Changing breakpoints during
a drag also cancels it safely. Completed drags save once on release.

The Context Panel uses only its navbar toggle for its visible close action.
Library scope labels are **This chat** and **All**, retaining the compatible
internal `current|all` values. Both scope-description sentences were removed;
search and view controls now share one compact row. No stale JavaScript access
to the removed button or description remains.

Validation:

- `scripts/webui_chat_resize_smoke.py`: real Chrome native mouse drags on both
  edges, stable opposite edge, draft/session preservation, keyboard adjustment,
  Escape rollback, width constraints, restoration after viewport changes and
  reload, independent panel toggles, default reset and blocked-storage fallback.
  It verifies no permanent borders or visible idle grips, no horizontal overflow,
  and correct hidden controls across 1920/1440/1000/768/390/320px in light/dark
  themes: **12 layouts, no console errors**.
- `scripts/webui_context_panel_smoke.py`: existing lifecycle, approvals,
  session/replay, scope/search, previews, native Library drag/drop, touch/keyboard
  Attach and **24 responsive layouts**. It asserts the removed controls are
  absent and the new This chat label is present.
- Scoped Ruff, JavaScript syntax and `git diff --check` pass. Backend tests were
  not repeated for these frontend-only changes; these checks do not claim a
  full suite or physical-device run.

Evidence: `/tmp/klaude-chat-resize.log`,
`/tmp/klaude-chat-resize-context-final.log`,
`/tmp/klaude-chat-resize-preview`, `/tmp/klaude-context-panel-preview`.
