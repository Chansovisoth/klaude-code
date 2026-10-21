# Settings tabs

Settings shows one category at a time: Account, Theme, Agent, Models and Memory.
At 851px and above, the tabs form a sticky vertical list to the left of the active
panel. Smaller layouts keep the horizontal tabs above the content, scrolling
horizontally on phones. They reuse the existing Library/Integrations theme roles
and icons. Account is unavailable on embedded bootstrap hosts, where Theme is the
initial tab. Password hosts start on Account.

The selected tab uses allowlisted `view=settings&settings=...` URL state and
tab-local storage. Reload, Back/Forward and leaving/re-entering Settings restore
selection. Desktop Up/Down and smaller-layout Left/Right, plus Home and End,
activate tabs with a single keyboard tab stop and linked accessible panels.
ARIA orientation updates on resize. The header Account shortcut selects Account.
Models contains Model Defaults followed by Image generation service, with 16px
between their cards. Former Images URLs and saved tab choices migrate to Models.
Each tab and category heading has a local outline icon; Agent's Execution, Tools,
Permissions, Web search, Web pages and Research budgets headings also have icons.
Icons are decorative, retain the visible text labels, and follow the current theme.

Tab changes retain ordinary form drafts. Leaving Account clears password fields;
leaving Settings and signing out retain their existing cleanup. A preparation
review is discarded after changing tabs, including switching away and back before
it finishes. Image generation has its own setup/recovery status inside Models.
Existing reviewed mutations and accepted background work retain their owners.

`scripts/webui_settings_smoke.py` uses isolated authenticated HTTP hosts and real
owned workers with no external model calls. Password and legacy bootstrap checks
cover 320/390/768/1024/1440px in light/dark, all tabs, active-tab visibility, single
panel selection, keyboard navigation, history/reload, chat/form drafts, reviewed
Agent and Memory saves, Model review cancellation, obsolete review disposal,
Account navigation and password cleanup. Screenshots are in
`/tmp/klaude-settings-tabs/`. These are Chrome checks, not physical-device coverage.

Final results: both authentication variants passed, with zero JavaScript
exceptions, including the combined Models card spacing and migration of old
Images URLs and stored selections. The existing `scripts/webui_loading_smoke.py` navigation/loading
regression also passed. Focused Ruff, Python compilation, all four modified
JavaScript syntax checks and `git diff --check` passed. No full-suite run is
claimed for this browser navigation change.

The icon follow-up passed the same focused Chrome checks for password and
bootstrap hosts at all four widths in light/dark, with zero JavaScript exceptions.
Phone Agent/Account and desktop Models captures were visually checked for icon
alignment, readable labels and horizontal tab scrolling. Syntax, focused Ruff,
Python compilation and `git diff --check` passed.

## Compact layout refinement

The header now contains the page title without the oversized decorative graphic
or tagline. The five established tabs, URL/history behavior, warm themes and
Material primitives remain. Settings content is bounded to 960px; cards use
16px padding, or 12px on phones, and rows use 10px vertical padding.

One shared control layout keeps inputs/selects and Review side by side. Native
container queries move the label above that pair when the actual card is narrow,
so the layout also works with the app's desktop sidebars. Numeric inputs remain
bounded; long model labels truncate visually with a full-label tooltip. Connection
catalog loading and the image-service form use the same layout. No stored model,
URL, budget or backend validation values change.

Agent's six groups are native disclosures with Execution initially open. Utility
and Vision fallback forms share an initially collapsed Fallback models section.
Their controls remain in the DOM, and switching tabs preserves draft values and
disclosure state during the current page session. Sign-out clears disclosure
preferences. Agent and Vision switches reuse the existing Material switch track
and retain the confirmed value until the existing review completes. Theme and
Memory switch rows remain inline. Password cleanup, Memory actions, revision
checks, Model Defaults recovery and image-service test/review semantics remain.

The extended `webui_settings_smoke.py` passed both password and bootstrap hosts:
**90 light/dark panel/viewport combinations**, including a short 320px viewport,
populated Memory and long saved model names. Every disclosure is expanded for
geometry checks, so hidden controls cannot conceal wrapping or overflow. It checks
input/Review alignment, usable widths, switch targets, native keyboard disclosure
activation, preserved drafts and disclosure state, tab/history/reload behavior,
real reviewed Agent/Memory saves, switch and Model cancellation, late-review
disposal, legacy Images migration and password cleanup. Zero browser exceptions.

In the password fixture at 1440px, affected desktop rows shrink from about 133px
to **65px**. The Agent card is about **606px** initially and **3221px** with all
43 fields expanded, compared with about 5040px before. At 390px, input/Review
pairs remain together with labels above and no horizontal overflow. Light/dark
desktop and phone captures were visually inspected, including Theme switches,
populated Memory, expanded Agent groups and Model Defaults.

Relevant backend integration passed: **25 tests in 58.47 seconds** across
`test_web_management.py` and `test_web_media_settings.py`. Repository Ruff,
production mypy (**222 source files**), modified JavaScript syntax checks, Python
compilation and `git diff --check` passed. Offline packaging built and installed
all **seven workspace wheels**, checked static assets/imports and both CLI help
commands. This is focused coverage, not a full-suite or physical-device claim.

Evidence: `/tmp/klaude-settings-layout-smoke.json`,
`/tmp/klaude-settings-layout-backend.log`,
`/tmp/klaude-settings-layout-ruff.log`, `/tmp/klaude-settings-layout-mypy.log`,
`/tmp/klaude-settings-layout-package.log`, and captures in
`/tmp/klaude-settings-tabs/`. The read-only before/after fixtures and measurements
are in `/tmp/klaude-settings-density-audit/` and
`/tmp/klaude-settings-layout-after/`.

Changed files: `static/index.html`, `static/style.css`, `static/management.js`,
`static/media.js`, `scripts/webui_settings_smoke.py`, `AGENTS.md` and this record.

## Desktop vertical categories

Desktop Settings now uses a two-column grid at the existing 851px desktop
breakpoint: a 152px sticky category list on the left and the active panel on the
right. Categories retain their icons and selected theme treatment, with full-width
buttons and left-aligned labels. Both columns share the existing Settings scroll
region. Below the breakpoint, the previous horizontal navigation remains.

The same DOM controls, panel identities and forms are reused. ARIA orientation
updates with the breakpoint; Up/Down navigate desktop categories and Left/Right
navigate horizontal categories. Home/End, single-tab-stop focus, URL/history,
review cancellation and unsaved drafts retain their existing behavior.

The extended Settings Chrome smoke passed **144** panel/theme/viewport cases
across password and bootstrap hosts at 320/390/768/850/851/1024/1440/1920px, with
zero JavaScript exceptions. It verifies actual left-column placement, breakpoint
orientation, control/Review alignment with all disclosures expanded, preserved
drafts during resizing, both keyboard directions and sticky navigation with the
Agent panel expanded and scrolled to the bottom. Existing reviewed saves,
timezone cancellation/save, history, reload and authentication cleanup passed.
Desktop light and phone dark screenshots were visually inspected. Focused Ruff,
JavaScript syntax, smoke Python compilation and whitespace checks passed.

The live host returned HTTP 200 for the updated CSS and JavaScript assets, with
the new layout and keyboard code present. A browser reload applies the change;
the backend and browser sessions did not need a restart. Evidence:
`/tmp/klaude-settings-vertical-smoke-final.{json,log}`,
`/tmp/klaude-settings-vertical-ruff.log` and captures under
`/tmp/klaude-settings-tabs/`. This change touches `static/style.css`,
`static/app.js`, `scripts/webui_settings_smoke.py`, `AGENTS.md` and this record.
Unrelated worktree changes are preserved.
Static paths are under `apps/webhost/src/klaude_webhost/`. Unrelated worktree
changes were preserved. No dependencies, endpoints, backend implementations,
commits or pushes were added. Reload the browser to pick up the new static assets.

## Natural card heights and denser settings

The existing five categories and vertical desktop navigation remain. Settings
uses at most 1040px across its two columns: a 160px sticky category list, a 20px
gap and content capped at 860px. Inner cards explicitly use automatic height and
zero minimum height; the Models stack aligns its cards to their content. The
main app shell and Activity panel retain their existing layouts.

Execution limits use a responsive grid with 240px minimum field groups, measured
against the available card width. Numeric controls remain bounded and every
field keeps its own Review action. Model Defaults now labels its available
models, model roles and Utility/Vision options separately. Roles and options use
the same compact grid; short role labels and the connection label sit beside
their controls on narrow cards. Fallbacks remain expandable and image service
setup retains its separate card and 16px gap. Existing model values, review
payloads, confirmation, recovery and draft handling are unchanged.

Theme palettes keep 44px swatches in four compact columns on narrow cards and
eight columns when at least 568px of content width is available. Fieldsets can
shrink with their container. All styling reuses the existing Material colors,
surfaces, switches, controls and motion.

Final isolated Chrome validation passed:

- `scripts/webui_settings_smoke.py`: **144** panel/theme/viewport cases across
  password and bootstrap hosts at 320/390/768/850/851/1024/1440/1920px, with zero
  JavaScript exceptions. Expanded disclosures have no horizontal overflow and
  maintain usable input/Review pairs. At 390px and 1440px, making the viewport
  300px taller leaves each card's height unchanged. The checks also verify
  bounded content, execution grids, palette placement, sticky navigation,
  Theme preview/reset/Apply, drafts, history, keyboard behavior, reviewed
  Agent/Memory saves, Model cancellation and account cleanup.
- `scripts/webui_model_defaults_smoke.py`: eight light/dark viewport cases,
  compatible role catalogs, connection refresh with preserved drafts, reviewed
  cancellation/save and logout races; zero inference calls or browser errors.
- Focused Ruff, Python compilation, modified JavaScript syntax checks and
  `git diff --check` passed.

Against the preceding vertical-navigation fixture, the 1440px Theme card shrinks
from 516px to 433.5px. The Agent card shrinks from 723px to 620.5px at 1920px,
and the combined Models cards shrink from 1136px to 1096.5px at 390px while adding
the section headings. Final phone and desktop captures were visually inspected
in light and dark. These are focused browser checks, not a full-suite or
physical-device claim.

Evidence: `/tmp/klaude-settings-density-smoke.json`,
`/tmp/klaude-settings-density-models.json`, screenshots in
`/tmp/klaude-settings-tabs/`, and the pre-edit static files in
`/tmp/klaude-settings-density-before/`. Changes are limited to Settings styling,
presentation grouping, the focused browser check, this record and `AGENTS.md`.
Unrelated worktree changes are preserved. Reload the WebUI to apply the assets.

## Expanded Settings width and model role icons

This refinement supersedes the earlier 1040px layout and 860px content caps.
The Settings view, heading and active panel have no maximum width. The existing
desktop grid retains its 160px vertical category list and 20px gap, while its
content track uses the remaining main-area width. Settings overrides the generic
48px large-screen page padding with 24px, or 16px on phones. Its app-shell parents
already allow flexible width and need no changes. Activity and the other app
destinations retain their existing layouts.

Control pairs are capped at 32rem independently of the cards. Numeric inputs,
the password form and palette swatches retain their compact sizes. Existing
responsive grids and natural card heights remain. The four Model Defaults roles
now use decorative 18px local SVG icons: the navigation chat bubble for Startup
chat, the existing wrench for Utility, search for Research and an eye for Vision.
The SVG helper supplies the existing rounded stroke style, with the muted theme
color and an 8px label gap. Native labels, dropdowns and Review actions retain
their IDs and behavior. Narrow role rows reserve room for both icon and label.
No icon dependency was added.

Validation passed:

- `scripts/webui_settings_smoke.py`: **162** light/dark panel/viewport cases on
  isolated password and bootstrap hosts at
  320/390/768/850/851/1024/1440/1920/2560px. Geometry checks confirm that Settings
  fills the main area with 16–24px side padding, the selected panel fills the
  content track, and controls remain bounded. All expanded sections fit without
  horizontal overflow; all four role icons remain aligned and visible, with
  native label associations. Existing keyboard/sticky navigation, draft/history,
  Theme preview/reset/Apply, reviewed Agent/Memory saves, model cancellation and
  account cleanup passed. Zero JavaScript exceptions.
- `scripts/webui_model_defaults_smoke.py`: compatible role catalogs, connection
  Refresh with preserved drafts, reviewed cancellation/save, eight responsive
  light/dark cases and logout races passed; zero inference calls or browser errors.
- Modified JavaScript syntax checks, focused Ruff, Python compilation and
  `git diff --check` passed.

The Models panel now spans 1009px at a 1920px viewport and 1649px at 2560px,
instead of stopping at 860px. Desktop and phone captures were visually inspected
for layout, icon alignment and light/dark colors. These are focused Chrome
checks, not a full-suite or physical-device claim.

Evidence: `/tmp/klaude-settings-width-smoke.json`,
`/tmp/klaude-settings-width-models.json`, screenshots in
`/tmp/klaude-settings-tabs/` and pre-edit files in
`/tmp/klaude-settings-width-before/`. Unrelated worktree changes are preserved;
no commits or pushes were made. Reload the browser to load the static changes.

## Rounded disclosure indicators

Browser-native disclosure triangles now use a shared 16px rounded triangle from
the existing SVG helper. The muted theme color follows light/dark appearance;
the triangle rotates from right to down with the native `details[open]` state.
Existing motion tokens and reduced-motion handling apply. The decorative SVG is
hidden from assistive technology, while native summary focus, click, touch and
keyboard activation remain intact.

The helper covers Agent sections, model fallbacks, workspace editing information,
technical reviews and Vision disclosures. The existing custom model picker and
agent Activity header retain their own presentation. Settings cards, role icons,
form values and reviewed actions are unchanged.

The existing Settings Chrome smoke passed all 162 responsive light/dark cases,
including native keyboard expansion and reviewed settings actions. The existing
navigation/loading smoke also passed. Both reported zero browser exceptions;
phone and desktop Settings captures were visually checked. Modified JavaScript
syntax checks and `git diff --check` passed. Evidence:
`/tmp/klaude-rounded-disclosure-settings.json`,
`/tmp/klaude-rounded-disclosure-navigation.json` and captures under
`/tmp/klaude-settings-tabs/`.

Utility fallbacks and Vision fallbacks headings also reuse the role labels'
muted 18px wrench and eye icons, with the same horizontal spacing. Fallback
ordering, selects and reviewed saves are unchanged. The existing Model Defaults
Chrome smoke passed eight light/dark viewport cases and its catalog/draft/review
checks with zero inference calls or browser exceptions. JavaScript syntax and
whitespace checks passed. Evidence: `/tmp/klaude-fallback-icons-smoke.json`.
