# Compact workspace styling

The supplied Windows Codex screenshots guide the shell and shared Settings
styling: smaller chrome, quiet selection surfaces, restrained corners and a
bounded reading column. This is a local WebUI change using Klaude's existing
components, native controls, themes and reviewed actions.

## Changes

- Desktop header: 48px; navigation rail: 52px with 44px buttons, preserved
  accessible names and the existing tooltip system.
- Settings gets dedicated category navigation, without conversation and context
  sidebars. Its content uses bounded 800–840px columns and aligns with the Settings heading.
- Desktop Settings controls use 36px targets when no coarse pointer is present.
  Touch devices retain native 44px controls; desktop touch category tabs use 44px.
- Shared groups, menus, conversation rows and composer use quieter corners and
  surfaces. Model chooser cards retain their existing selection and draft behavior.
- Palette choices and saved appearance preferences remain intact. The Slate
  palette provides the neutral appearance shown in the design preview.

`apps/webhost/src/klaude_webhost/static/compact.css` is bundled after the existing
rules by `scripts/bundle_webui_expressive.py`. The generated block is replaced
on regeneration; rebuilding does not duplicate it.

## Focused validation

On 2026-11-05, isolated profile fixtures in Linux headless Chrome passed:

- `scripts/webui_settings_layout_smoke.py`: 100 layouts; light/dark, 320–1440px,
  long labels, keyboard navigation, help dialogs, Apply/Discard, bottom action
  clearance and viewport keyboard emulation; zero console errors.
- `scripts/webui_chat_layout_smoke.py`: 56 layouts; transcript scrolling,
  composer/draft clearance, passive details and mobile keyboard layouts;
  zero browser exceptions.
- Expressive CSS and loading bundle checks, targeted Ruff checks and
  `git diff --check`.

The layout smoke now expects the 48px desktop header. Settings assertions measure
the actual CSS query container and account for an Advanced disclosure between
separate image-service row groups.

REA inspected the isolated WebUI's DOM and accessibility structure before and
after the styling. Those passive captures do not certify prior console or network
activity. Screenshot review covered desktop and phone Settings; the neutral
desktop preview is `/tmp/klaude-compact-after.png`, with additional suite images
under `/tmp/klaude-settings-layout` and `/tmp/klaude-chat-layout-validation`.

This is focused browser validation, not the full Python suite, physical touch
hardware testing or native Windows testing. Production host lifecycle and model
defaults were not changed.


## Conversation sidebar refinement

The follow-up reference uses the desktop Codex arrangement: a 52px full-height
rail, a 288px conversation panel, and the current page header in the content
column. Collapsing the panel retains the rail. Existing controls relocate across
850px instead of creating competing account or session actions. The current
conversation title is retained while searching or showing archived chats.

The panel leads with Klaude and Search, then New chat and Chats. Desktop
collapse/expand and New chat icon controls sit in the left rail below Chat, and
stay available with the panel collapsed. Phone controls return to their original
header positions.
Search opens a centered native dialog with a search input, close control and
Recent chats/results list; Escape clears it before returning focus.
Conversation options contains the existing Refresh and archived/saved toggles;
Escape closes that popover before the phone drawer. Row menus stay available on
hover/focus and are always visible on touch devices. Existing rename, archive,
restore, delete and background-turn behavior remains in the session services.
The reference's project and pinned groups are omitted because this inventory is
scoped to Klaude's current workspace.

Additional focused checks: `scripts/webui_sidebar_smoke.py` covers ten light/dark
layouts at 320/390/768/1000/1440px using actual pointer events, search/filter/clear,
Escape, popovers, collapse focus, scrolling and responsive control ownership.
Its generated rows are explicitly presentation fixtures and produce no writes.
Screenshots and report are under `/tmp/klaude-sidebar-validation`.
`scripts/webui_sessions_smoke.py` exercises real isolated session mutations.
The resize smoke uses explicit fixture login and waits for startup readiness
before keyboard interaction after reload; its reset expectation is now 288px.


## Store and Settings sidebars

Store and Settings now reuse the desktop conversation panel's width, surface,
heading, row typography, quiet selection, divider and scrollbar treatment.
Their actual navigation nodes move to the shared panel on desktop and return to
original parents below 851px. Collapse uses the same existing control and keeps
keyboard focus on it. Settings retains native tab semantics and its independent
Apply/Discard dock; Store retains its category routes and native phone chooser.

The sidebar smoke additionally checks twenty Store/Settings light/dark layouts
at 320/390/768/1000/1440px, node ownership, fit and collapse focus. Its screenshots
use `settings-` and `store-` prefixes under `/tmp/klaude-sidebar-validation`.
The Settings layout smoke passed 100 cases. The Store UX walkthrough passed
320/390/1440px category/detail navigation, installation reviews and Settings
handoffs, with zero console errors. These remain isolated fixtures, not production
installs or model downloads.


The desktop model picker now leads the top bar. Conversation titles are omitted, and the former second chat toolbar is hidden. Conversation details
moves to the left edge of the context panel header; closing the panel closes its
popover. Existing model and details controls restore to their phone locations.
The focused chat layout smoke passed 56 cases, and the sidebar smoke passed ten
chat plus twenty Store/Settings layouts after this move, with zero console errors.


## Search and action popovers

Conversation search uses a centered 720px dialog, Recent chats, compact speech
bubble rows and a right-aligned close control. Narrow screens use the available
width. The sidebar stays visible behind the modal. Filtering uses the existing
bounded session endpoint and selection preserves session admission checks.
Escape, Close, outside dismissal and sign-out clear transient search state.

Session overflow opens an anchored menu with existing Rename, Download,
Archive/Restore and Delete actions. Rename retains its native editor and all
writes retain existing reviewed operations. The profile popover includes actual
identity and local-account status, Personalization (Memory), Profile (Account),
Settings, Help (keyboard shortcuts) and Log out. The separate rail logout control
is removed. Unsupported reference-only plan/pin/share/project entries are omitted.
Conversation names are no longer displayed in the top bar.

Focused Chrome checks passed search filtering and geometry, responsive ownership,
menu dismissal, profile navigation and existing session mutation reviews. The
sidebar fixture has presentation data and no Library backend; its incidental
Library unavailable toast is fixture-specific. Native session mutation checks use
the full isolated service fixture. Menu/search screenshots are under
`/tmp/klaude-sidebar-validation`. Full application tests and native Windows testing
were not run for this styling slice.
