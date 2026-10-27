# Mobile chat layout — 2026-10-26

Compact layouts up to 850px use one 56px app bar with a tappable Klaude title and
model/mode subtitle. The separate 64px model-controls layer is removed. The empty
composer measures 104px and expands with text. Thinking/Plan remain directly
accessible where they fit; existing active-turn controls and admission protections
remain. Desktop above 850px retains its header layout and now opens the same
model picker as a centered native dialog, with search focused. Both desktop
Model halves and command-palette Switch model use this shared picker.

Model selection uses a native bottom sheet with local search, the existing
connection/catalog data, shared 20-row pagination, current/available/installed
labels based on actual source, and Browse model store. Selection reuses existing
revisioned runtime requests; failed selection keeps the current runtime and shows
the error. Native focus, Escape, lifecycle cleanup and sign-out clearing remain.
Header secondary actions use a native menu with tonal icon tiles, 48px rows and
an Account divider. The account entry uses the signed-in username and circular
initial above the Account label; mobile sign-out is in Account settings. Focused Chromium
checks at 320px/390px in light/dark verified icons, viewport fit, arrow navigation
and Escape focus return, with no browser errors.

Thinking's effort selector uses the same menu styling and directly lists the
runtime's supported efforts, with icons and a selected check. Focused Chromium
checks at 320px/390px/1440px verified option selection through a stubbed runtime
action, keyboard navigation, Escape, focus retention across refreshes, viewport
fit, busy/unsupported states and no browser errors. Backend behavior was unchanged.

Phone navigation hides when editing reduces the usable viewport by more than
120px, covering resized and overlay keyboards. It returns when the viewport
recovers. Focus alone and hardware-keyboard input retain navigation. The work is
event-driven and honors existing motion/theme roles, without new dependencies,
backend routes or runtime calls for presentation.

Validation:

- Shared desktop/mobile picker: focused Chromium at 1440px/390px verified search,
  20-row pagination, stubbed runtime selection, both desktop triggers, resize
  continuity, focus return, busy fencing and auth cleanup. No browser errors;
  no real model activation was performed by this UI check.
- Focused Chromium check at 320px and 390px: Chat/Library retain identical paw
  and title horizontal positions and a 30px circular paw. The title moves 8px
  vertically; subtitle opacity animates in both directions. No browser errors.
- `webui_chat_layout_smoke.py`: 56 responsive light/dark cases, 56px header,
  absent mobile model row, 104–120px composer, growth bounds, resized/overlay
  keyboard behavior, navigation restoration, menu focus, Account sign-out,
  blocked-state draft retention and private cleanup. Zero browser exceptions.
- `webui_models_smoke.py`: native local and configured local/cloud sheets,
  search/pagination, exact HTTP selection, failed-selection retention, busy locks,
  header mode state, selector focus, internal overflow and existing desktop flows.
- `webui_composer_smoke.py` and `webui_control_smoke.py`: sending, keyboard input,
  stale-tab queue admission, drafts, two-client control, steering and cancellation.
- Focused host/account tests: 49 passed. JavaScript syntax, deterministic bundles,
  changed helper lint and whitespace checks pass. The models smoke script retains
  its pre-existing long-line lint findings; no new findings are intended.

Visual inspection caught inherited pagination negative margins causing internal
horizontal overflow. Sheet-specific margins fix it; the final overflow check and
settled screenshots pass. Phone conversation, keyboard and model-sheet screenshots
were inspected. Evidence: `/tmp/klaude-chat-layout-validation/` and
`/tmp/klaude-models-mcp-preview/chat-model-sheet-all-390.png`.

The live host serves HTML, app and CSS byte-identically with the worktree;
`/tmp/klaude-mobile-chat-assets.json` records hashes and the unchanged host instance.
No restart, model generation or download was performed. Reload picks up the assets.

These are Chromium fixtures/emulation, not physical iOS/Android, Safari, a full
accessibility audit or the full repository suite. Prior chat/admission edits remain
preserved. No commit or push was made.
