# Mobile Settings layout

Completed 2026-10-22. The Settings category row and staged-change actions reuse
the existing Material 3 Expressive surfaces, theme roles, native buttons and
draft/save controllers.

The overlap came from two existing constraints: Expressive CSS replaced the
sticky category row's solid background with transparency, and each sticky save
bar lived inside a Settings card with its own container context and padding.

## Layout changes

- Settings navigation uses its own `settings-tabs` container, separate from
  theme-style chips. Through 850px it is one horizontally scrolling sticky row,
  with an opaque Material surface, opaque selected tonal background, contained
  horizontal scrolling, focus clearance and no wrapping. Keyboard arrows,
  Home/End, selected states and responsive ARIA orientation retain their existing
  handlers. Forced colors retain a visible selected-tab outline.
- An application-level `settings-action-dock`, outside the scrolling Settings
  cards, holds the active dirty category's existing action DOM on mobile/tablet.
  This preserves handlers, button identities, pending locks, receipt polling and
  conflict controls. Switching category/page or returning to desktop restores
  the original bar to its card; other categories' drafts remain independent.
- Phones span the viewport above the measured bottom navigation. Tablet layouts
  with a side rail span the available main application area. The opaque dock has
  a subtle top separator, right-aligned actions and safe-area-aware padding.
- Border-box ResizeObservers measure the dock, category row and navigation,
  including padding-only navigation changes. Visual viewport resize/scroll
  events account for overlay keyboards; native layout resizing remains intact.
  Focused fields are checked after padding and native scroll anchoring settle.
  Measured bottom padding keeps the last settings reachable above the dock.
- Long status and conflict content have bounded scroll areas so recovery actions
  remain available in short viewports. The dock appears only for dirty/pending
  Agent or Models changes, or a Theme preview differing from saved appearance.
  Leaving Settings or signing out hides it. Desktop retains the existing
  vertical categories and card-local bars. Theme Apply/Discard appears only for
  unsaved changes at every viewport size, including desktop.

No backend APIs, permission rules, persistence formats or dependencies changed.
Agent/Models still use the existing staged saves, exact reviews, field-level
conflicts, sequential submissions and durable receipts. Theme retains its local
preview, Apply and Discard behavior.

## Validation

All browser runs used isolated local hosts, temporary profiles and deterministic
fixtures without live inference or external provider calls.

- `scripts/webui_settings_layout_smoke.py`: **96 layout cases passed** across
  light/dark, Agent/Models/Theme, top/end scroll positions, and
  320×568, 390×844, 560×700, 768×1024, 850×768, 844×390,
  851×700 and 1440×900. Long category labels and maximum theme transparency
  were enabled. Checks cover opaque surfaces, one-row tabs, page/content bounds,
  dock width and navigation alignment, reserved content space, button geometry,
  keyboard focus and desktop restoration.
- The same run passed high-contrast selection, visual-viewport keyboard overlay
  emulation, resized keyboard layouts, enlarged navigation padding, long errors,
  the pending-save recovery action at 320px, category-local drafts, Discard,
  Theme Apply, clean-bar hiding and leaving Settings. **Zero JavaScript errors.**
  Report: `/tmp/klaude-mobile-settings-layout-final.log`; measurements:
  `/tmp/klaude-settings-layout.json`; screenshots:
  `/tmp/klaude-settings-layout/`. Mobile light/dark captures were inspected.
- `scripts/webui_settings_save_smoke.py` passed staging/discard, independent
  availability/policy, large batches, security confirmation/cancel, concurrent
  writers, partial success, lost acknowledgements, confirming reads, exact
  unknown image-settings recovery, responsive bars and logout races.
  **Zero JavaScript errors.** Evidence:
  `/tmp/klaude-mobile-settings-save-final.log`.
- `scripts/webui_settings_smoke.py` passed on password and bootstrap hosts:
  responsive navigation at 320/390/768/850/851/1024/1440/1920/2560px,
  keyboard/sticky navigation, theme preview/Discard/Apply, chat density,
  history, draft preservation and saves. **Zero JavaScript errors.** Evidence:
  `/tmp/klaude-mobile-settings-regression.log`.
- `node --test scripts/webui_settings_drafts.test.cjs`, JavaScript syntax,
  scoped Ruff, both static asset bundle checks and `git diff --check` passed.

The initial geometry fixture needed startup and local-variable fixes. Its
keyboard case then exposed a real native-scroll-anchoring race, fixed by checking
field clearance in the following frame. The navigation-padding case exposed
content-box observation, fixed by measuring border boxes. Final runs above pass.
An automatic approval-review usage limit interrupted the last high-contrast
rerun; after resume, that same reviewed browser command completed successfully.

Changed files for this refinement: `static/index.html`, `static/app.js`,
`static/management.js`, `static/expressive.css`, generated `static/style.css`,
`scripts/webui_settings_layout_smoke.py`, the responsive assertion in
`scripts/webui_settings_save_smoke.py`, `AGENTS.md`, the staged-save validation
record and this document. Unrelated dirty work was preserved; no commit or push.

Keyboard and safe-area geometry are emulated. Physical iOS/Android keyboards,
cross-browser behavior and the full repository suite were not certified.
No backend tests were repeated for this frontend change. Static assets only
require a page refresh, without restarting the Python host.

## Desktop Theme footer follow-up

The desktop Apply/Discard row had an opaque background but its box still ended
28px above the Settings scroll region's bottom edge, with 20px card insets on
both sides. Scrolling controls remained visible through those uncovered strips.
The desktop Theme footer now extends across the card padding and compensates
for the scroll region's bottom inset. Shared spacing variables keep these offsets
in sync with the actual card/page padding. The footer stays in its existing
desktop card; mobile/tablet continue using the application-level dock.

The focused browser diagnostic measured the footer flush with both card edges
and the scroll area's bottom at initial, intermediate and final scroll positions.
The updated Settings layout smoke adds desktop footer bounds, opaque color and
hit-testing checks, including a midpoint scroll case: **100 layout cases passed**
across light/dark desktop and mobile, with zero JavaScript errors. Scoped Ruff,
the CSS bundle check and whitespace checks passed. The light desktop capture
was inspected. Evidence:
`/tmp/klaude-desktop-settings-gap-fixed.log` and
`/tmp/klaude-settings-desktop-footer-final.log`. The original uncovered bounds
are recorded in `/tmp/klaude-desktop-settings-gap.log`.

## Dirty-only Theme actions

Theme Discard/Apply now follows the same unsaved-change comparison at every
viewport size. An untouched Theme page has no action row. Editing reveals it;
Apply, Discard, or manually returning controls to their saved values hides it.
A failed local-storage save retains both the preview and the action row so users
can retry or discard. This removes the former desktop exception without changing
the card-local desktop placement or the mobile dock.

The appearance regression passed on password and bootstrap hosts, including
live preview, manual value restoration, Discard, successful Apply, failed storage,
category navigation and reload. The responsive layout smoke passed all **100
cases**, including dirty desktop footer coverage and mobile docking, with zero
JavaScript errors. Evidence: `/tmp/klaude-theme-dirty-settings.log` and
`/tmp/klaude-theme-dirty-layout.log`. JavaScript syntax, scoped Ruff, both static
bundle checks and whitespace checks passed. Refresh the page to load the update.

## Shared Theme footer styling

Agent and Models now use the same footer class as Theme: the tonal divider
surface, square footer edges, quiet Discard and filled Apply changes buttons.
Agent spans its card padding like Theme; Models spans its combined settings
panel. Mobile bars retain the existing measured application dock. Unsaved counts,
conflict resolution and Check save status keep their original transaction flow.

The responsive smoke passed all 100 light/dark layouts with zero browser errors,
including shared footer/button assertions, desktop placement, mobile safe areas,
keyboard overlay geometry, draft retention and Discard/Apply. It also exposed an
optional AI Review description being dereferenced after its removal; the renderer
now checks that the description exists before updating it. The Expressive bundler
preserves existing CSS appended after its owned block when regenerating styles.

## Agent Help dialogs

Settings → Agents question-mark controls open their existing explanatory text in
one shared native dialog, with the setting name as its title and a single OK
button. No inline note expands. Escape dismisses it and focus returns to the
invoking Help button. The sign-in Help popup retains its original behavior.
The isolated browser smoke passed all 100 layouts and checked every Agent Help
control at 390px and 1440px in light/dark mode, including modal focus, viewport
bounds, OK/Escape dismissal and focus restoration; no browser errors occurred.

The custom accent hex value is a borderless inline text editor with the same
font, dimensions, colors and zero padding at rest and on focus. Blur or Enter
updates the existing accent preview; Escape cancels the edit. Three-digit and
six-digit hex values are accepted, with invalid drafts restored to the current
accent. Theme Apply/Discard continues to control persistence.
