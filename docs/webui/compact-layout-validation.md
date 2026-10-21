# Compact WebUI layout validation — 2026-10-20

The existing WebUI now keeps the model picker, Thinking and Plan controls on the
left of Send. Their labels stay short and their pressed state remains exposed to
assistive technology. The picker opens above the composer. The composer tagline
has been removed, and Cancel/Steer remain immediately available in a compact
toolbar during an active turn.

## Chat title trial

The visible Chat heading is removed; a screen-reader-only heading retains the
page's accessible structure. Tool policy, turn state and the session ID share a
compact footer below the composer. Error notices wrap onto their own line.
Cancel/Steer occupy a compact toolbar at the top only during an active turn;
the toolbar consumes no space while idle.

Chrome 148 checked idle and active states at 1440×900, 768×650, 390×640, 320×480,
390×320 and 844×390. All 12 combinations kept the footer, Send and active turn
controls within the main panel, preserved 44px action targets and had no
horizontal page overflow or console exceptions. The existing two-client/terminal
control smoke also passed, including actual Cancel/Steer, approvals, question
answers and Library confirmation. These used temporary state and deterministic
model fixtures, not live inference or a full repository suite.

Trial screenshots: `/tmp/klaude-chat-heading-preview/`.
Layout harness/log: `/tmp/klaude-chat-heading-preview.py` and
`/tmp/klaude-chat-heading-preview.log`.

Shared page headings, form fields, card padding, disclosure spacing, dialogs and
workspace controls use tighter spacing. Phone navigation is shorter; Library
section chips scroll horizontally instead of consuming another row. Scrollable
page content does not compress cards or forms. Chat reviews scroll separately
from the composer. The input grows within a bound and resets after sending;
very short viewports keep it to one visible line. Mobile inputs retain 16px text,
and primary chat controls retain 44px touch targets. The shell follows the
native CSS viewport and includes safe-area insets; the browser owns keyboard
scrolling for focused inputs.

## Validation

- Focused existing tests: `tests/unit/test_webhost.py`,
  `tests/unit/test_web_library.py`, `tests/unit/test_web_accounts.py`:
  **50 passed in 40.23s**, with loopback networking enabled. The initial sandbox
  run could not open local server sockets; its failures were not product failures.
- Headless Chrome 148 exercised Chat, Workspaces, Library, Integrations, Activity
  and Settings at 1440×900, 1024×768, 768×650, 560×650, 390×640, 360×560,
  320×480 and 844×390. All 48 page/viewport combinations had no unintended
  horizontal page overflow. The three composer controls aligned with Send,
  and the model popup stayed within the viewport.
- Expanded Knowledge/Skill forms, all five Library sections, saved-item and
  review dialogs, account fields, conversation drawer, long model names and
  sign-in received additional narrow-screen checks. A 390×320 viewport with a
  multiline draft and simultaneous review/question presentation fixtures kept
  Send in bounds. Dialogs also fit at 320×320.
- Existing isolated chat browser checks passed: real shared-Agent fixture
  streaming, approval/answer handling, question draft retention, navigation,
  account access, appearance preview/apply/reload, cross-tab preferences and
  reduced motion. All 42 checked semantic foreground/background pairs exceeded
  4.5:1 (lowest 5.28:1).
- Existing isolated Library browser checks passed: reviewed document import,
  inert preview, image display, tags, archive/restore, knowledge search/learning,
  Skill import/disable, operation status and logout cleanup. Its older harness
  needed to clear the retained knowledge search before looking for a newly
  created library; production retrieval behavior was unchanged.
- JavaScript syntax, unique HTML IDs, CSS block balance and `git diff --check`
  passed. No full repository suite is claimed for this presentation change.

Browser checks used temporary profiles/data, deterministic model/embedding
fixtures and loopback servers, not live provider inference. Layout screenshots
and logs are under `/tmp/klaude-spacing-preview` and `/tmp/klaude-spacing-*.log`
in this workspace session. Physical phone browsers, native keyboard/chrome
transitions, safe-area hardware and complete accessibility acceptance remain
unverified; reduced viewport checks simulate their space constraints.

## Page refresh follow-up

The selected main page and Library section now survive reload through two
allowlisted identifiers in versioned, tab-local sessionStorage. Authentication
completes before the saved page is shown or its data loads. Restoring Workspaces
also reloads its initial directory listing; Library restores the selected section
and its pressed chip. Missing/invalid saved values use Chat/Knowledge, and denied
storage access leaves ordinary navigation usable. Bootstrap fragments are unchanged.

A dedicated Chrome 148 check reloaded all six main pages and all five Library
sections, including Media at a phone viewport. It also verified independent tabs,
sign-out/reload/sign-in restoration, invalid stored identifiers and a browser
storage getter that throws SecurityError. All passed with no console exceptions.
The isolated harness and output are `/tmp/klaude-navigation-browser-check.py` and
`/tmp/klaude-navigation-browser.log`. Only page/section identifiers persist;
workspace output, search filters, drafts and dialog contents are not saved by this
change.
The focused WebUI/auth/Library test files were rerun after this follow-up:
**50 passed in 40.76s**. JavaScript syntax and `git diff --check` also passed.

## Focus and keyboard resize follow-up

Removed `syncViewportHeight`, its visualViewport/window resize listeners and the
`--viewport-height` override from shell/popover/dialog sizing. Removed the
`interactive-widget=resizes-content` viewport directive. Native CSS viewport
units and normal browser focus scrolling now own sizing and keyboard positioning;
no application focus handler scrolls the page or resizes the shell. Composer
autosizing still runs when the draft changes, not when it receives focus.

The isolated Chrome regression check focused inputs in Chat, Workspaces, Library
and Settings, then simulated a visual-only viewport shrink from 640px to 320px
without changing the layout viewport. Before the fix, the app resized its shell
from 640px to 320px in all four cases. After the fix, the shell stayed at 640px
and focus stayed on the input. Actual layout viewport changes still resized the
shell at 320×480, 390×320, 768×650 and 1440×900; Send stayed in bounds. All checks
passed without console exceptions. JavaScript syntax and `git diff --check`
also passed. Harness/logs: `/tmp/klaude-input-focus-check.py` and
`/tmp/klaude-input-focus-{before,after}.log`. This reproduces the extra app resize;
physical mobile keyboard behavior still needs device verification.

## Library and Integrations count pills

All five Library tabs and the Skills/MCP integration tabs now display small
leading count pills. Selected pills use the active tonal palette. Totals cover
the complete unfiltered section, not the current page or a search result. Documents,
Research and Media exclude archived items; Archive counts all archived artifact
types. Knowledge counts visible libraries, Skills counts installed Skills, and
MCP counts configured servers without connecting or enabling browser management.

The authenticated `/api/v1/library/counts` read returns only totals and bounded-
inventory flags through the shared application service. Existing read bounds
remain intact: a capped inventory displays `1,000+`, and an unavailable count is
omitted rather than shown as zero. Older running hosts reuse available inventory
routes; their unavailable MCP count stays omitted. Counts refresh on page entry,
explicit Refresh and completed domain operations, and clear on logout. Request
ordering rejects obsolete replies.

Focused Library management, WebUI Library, account and host tests passed:
**75 passed in 70.16s**. Coverage includes totals beyond a page, archive visibility,
filter independence, empty stores without initialization, limited/unavailable
inventories, authentication, cross-site rejection and count-only projection.
Ruff and mypy passed for the changed Python source; JavaScript syntax and
`git diff --check` passed.

## Model picker dismissal

The model picker closes on clicks or taps outside its disclosure. Inside controls
remain usable, the trigger still toggles it, and Escape still closes it. Outside
actions retain their normal behavior, including focusing the message field and
toggling conversations.

An isolated Chrome 148 check passed with real mouse input at 1440×900 and
simulated touch input at 390×640, with no console exceptions. It covered opening,
inside clicks/taps, Refresh, outside headings and controls, message-field focus,
trigger toggling and Escape. JavaScript syntax and `git diff --check` passed.
Harness/log: `/tmp/klaude-model-dismiss-check.{py,log}`. No live inference or
physical phone validation was performed.

The isolated Chrome check passed all seven counts using real temporary stores
(100 Knowledge libraries, 125 initial Documents, 45 Skills and two configured MCP
servers). It verified pagination and filtering, explicit Refresh, browser import,
archive/restore, selected pills at 320/390/768/1440px, capped/unknown/zero rendering,
older-host fallback and logout with a pending count reply. No console exceptions
were observed. Harness/log: `/tmp/klaude-tab-count-browser-check.py` and
`/tmp/klaude-tab-count-browser.log`; screenshots:
`/tmp/klaude-spacing-preview/count-pills-*.png`. This uses fixture stores and
embedding responses, not live model/provider work.

## Responsive card pages

Library inventories, saved items, Knowledge text matches, refreshable sources and
installed Skills now size pages to complete grid rows near 20 cards. Three-column
grids use 21 cards, six-column grids 18, and eight-column grids 24. The final page
shows only remaining items. Page numbers and Previous/Next use the actual capacity;
the redundant per-page summaries remain removed. Loading, empty-result, inventory
limit and error messages remain available.

The browser measures the actual grid, including changes from the conversation and
Activity panels. A debounced ResizeObserver reloads cards only when capacity
changes. Resizing selects the new page containing the former first item, preserves
filters and rejects late results from the old layout. The browser composes at most
two existing bounded reads per card page, capped at 40 cards, so installed hosts
need no restart and CLI/TUI store batches stay unchanged.

Isolated Chrome 148 checks passed against current and earlier host contracts at
320, 390, 560, 768, 1024, 1240, 1440, 1700, 1920, 2320, 2560, 2800 and 3840px.
They covered complete non-final rows, exact last pages, numbered/Previous/Next
navigation, no repeated or skipped items, full-inventory filtering, empty states,
resizing from a later page, panel toggles, unchanged-capacity resizes, late replies
and logout cleanup. Fixtures included 125 Documents, 85 Knowledge libraries,
85 sources, 85 Skills and 45 indexed text matches. Earlier hosts' unpaged text
search keeps its original 20-result cap; no extra matches are invented. No console
exceptions or horizontal page overflow were observed.

JavaScript syntax and `git diff --check` passed. No full repository suite or
physical-device validation is claimed for this browser-only change. Harnesses and
logs: `/tmp/klaude-adaptive-page-check.{py,log}` and
`/tmp/klaude-adaptive-legacy-check.{py,log}`. Screenshot:
`/tmp/klaude-webui-preview/responsive-pages-3-columns.png`.

## Settings category spacing

Superseded by the single-category Settings tabs described in
`settings-tabs-validation.md`; the evidence below records the earlier stacked layout.

Adjacent Settings cards now have a 24px vertical gap, including Model Defaults,
image generation, Account and Memory. The Interface label retains its existing
spacing above Themes & Colors. The rule is scoped to Settings.

Isolated authenticated Chrome checks passed at 320/390/768/1440px in light and
dark: all visible cards remain separated, hiding Account retains the gap before
Memory, and Settings has no horizontal overflow or JavaScript exceptions.
Screenshots: `/tmp/klaude-settings-spacing/`; harness:
`/tmp/klaude-settings-spacing-check.py`. `git diff --check` passed.
