# MCPs and Skills settings UI/UX plan

Date: 2026-10-04
Status: First entry-page and Manage navigation milestone implemented and validated.

## Objective and scope

Improve the complete MCPs and Skills settings journeys: entry pages, search,
discovery details, installation and import, installed-item management, updates,
removal, permissions, setup, feedback, and return navigation.

Give both categories the same navigation structure and interaction rules.
Show their differences inside item details and setup steps.

This plan follows a code-based inspection of the current working tree. An
interactive terminal walkthrough has not yet been performed. Existing dirty
working-tree changes were left untouched during analysis. The user subsequently
authorized implementation; completed work and remaining gaps are tracked below.

## Current assessment

| Area | Current behavior | UX problem |
| --- | --- | --- |
| Entry pages | Skills uses Discovery / Add Skills / Skills; MCPs uses Discover / Set Up / MCP Servers | Similar tasks have different organization and wording. |
| Manage lists | Both show name, source, and description | Enabled status is hidden inside each item's detail page. |
| Search | Both have query controls and results, with different cache information, sorting, and paging | Users must learn two slightly different interfaces. |
| Skill discovery details | Roughly 15 metadata fields, source-resolution controls, installation controls, and explanatory text | The main decision competes with too much information. |
| MCP details | Discovery, installed-server management, and permissions are separate branches | Managing one server requires moving between disconnected places. |
| Updates | Update and Update all first check for updates and open a review | Labels imply that a change happens immediately. |
| Reload | Skills refreshes inventory; MCPs reloads and verifies configured tools | Identical labels describe materially different operations. |
| Installation | Skills has explicit confirmation; MCP setup collects inputs and can save afterward | Review and completion behavior differ. |
| Back navigation | Return behavior is spread across typed actions, page-ID checks, legacy picker kinds, and special return variables | Additional screens make consistent navigation harder to maintain. |

Retain and extend the existing panel foundation: fixed headers and footers,
stable row identities, local filtering, wrapped text, background jobs, and focus
restoration.

### Inspected implementation

- `apps/cli/src/klaude_cli/main.py`: category entry pages, setup, permissions,
  installation, action routing, and cancellation/return behavior.
- `apps/cli/src/klaude_cli/settings_panel.py`: shared panel presentation and state.
- `apps/cli/src/klaude_cli/skills_panel.py`: Skills entry and management pages.
- `apps/cli/src/klaude_cli/skill_discovery.py`: Skills search, source resolution,
  discovery details, installation confirmation, and cached results.
- `apps/cli/src/klaude_cli/mcp_management.py`: MCP management, update reviews,
  and removal pages.
- `apps/cli/src/klaude_cli/mcp_search_panel.py`: MCP search and discovery details.
- Relevant existing tests cover panels, search, inventory, updates, source
  resolution, installation confirmation, stale responses, and view restoration.

## 1. Simplify both entry pages

Use compact, matching layouts:

```text
Settings › MCPs                   Settings › Skills
3 installed · 2 enabled           8 installed · 6 enabled

Manage installed                  Manage installed
Search catalog                    Search catalog
Add custom server                 Import skills
Import configuration

← Back                            ← Back
```

- Put Manage installed first for returning users.
- Show installed and enabled counts beside the title.
- Remove section headings that contain only one action.
- Move Skills drop-folder instructions and detected files into Import skills.
- Keep category pages enterable while inventory loads; show loading in the
  destination instead of making navigation unavailable.
- Preserve existing command aliases.

## 2. Make Manage useful without opening every item

Use the same list structure for both:

```text
Manage installed                  8 installed · 6 enabled

Filter: All
Refresh list
Check for updates

NAME              STATUS          DESCRIPTION
example           Enabled         ...
another           Disabled        ...

← Back
```

- Show enabled status directly.
- Add All / Enabled / Disabled filtering; include Needs attention where actual
  state supports it.
- Keep source attribution in details and searchable locally.
- Use bounded description previews in lists and full descriptions in details.
- Preserve selection, filter, and viewport after refresh and actions.
- After deletion, focus the next nearby item.
- Provide Search catalog and Import/Add actions in empty states.
- Separate Refresh list from MCP Reconnect / refresh tools, which may contact
  or execute a configured server.

## 3. Standardize installed-item details

Use this order:

1. Name, description, and enabled state.
2. Primary controls.
3. Source and version/revision summary.
4. Additional information.
5. Removal action and Back.

For MCPs:

- Add Tools & permissions directly to each server's detail page.
- Include authentication/setup status and a connection action when applicable.
- Distinguish configured-enabled state from observed connection health. An old
  tool count must not imply a live connection.
- Retain the global permissions overview as a secondary route; return to the
  actual originating page.

For Skills:

- Show indexed-file count, source, and revision.
- Put longer attribution and compatibility information behind Source details.

## 4. Standardize search interactions

Use a consistent arrangement:

```text
Search catalog

Search query      ...
Source            ...
Sort              ...

Results           count / page / freshness
...

Refresh results
Previous page / Next page

← Back
```

- Label `/` as Filter this list. Online search remains an explicit query action.
- Retain query, source, sort, result page, selection, and viewport when returning
  from details.
- Match loading, cached, stale, empty, and error presentations.
- Show Retry after failure and Refresh results after success.
- Show pagination only where supported; state result limits clearly.
- Explain when sorting applies only to loaded results.
- Keep local query suggestions on an empty search page.
- Mark installed results when verified identity matching is available; offer
  Open installed item.
- Use choice pages for source and sort selection so available options are visible.
- Preserve the actual meaning of provider metrics, including repository stars
  and installation counts.

## 5. Reduce discovery-detail clutter

Show decision information first:

- Name and description.
- Source and installation availability.
- Version/revision and relevant license information.
- One clear next action.

Move full URLs, timestamps, detailed provenance, and additional metadata into
Source details.

For Skills, introduce an explicit Review source step that resolves the pinned
source and then presents installation review. Preserve source verification.

For MCPs, show supported installation methods clearly, followed by any required
configuration and a final review.

## 6. Complete installation and import journeys

Use: Choose → Configure if needed → Review → Install/import → Result.

- Give custom MCP setup visible steps and editable previous answers.
- Keep secrets masked and out of history.
- Resolve local-name conflicts within setup.
- Preview import items, conflicts, and skipped items before committing.
- Show progress and per-item outcomes for batch imports.
- Report completion only after operation acknowledgement.
- Offer Open installed item and Return to results / Return to import afterward.
- MCP installations continue to save disabled; enabling is an explicit
  subsequent action.

## 7. Make updates, removal, and feedback predictable

- Rename initial actions Check for update and Check for updates.
- Show current → available versions before applying changes.
- Allow users to choose eligible updates in batch review.
- Explain MCP's disabled-after-update behavior in both review and result.
- Use Remove server and Delete skill, with their exact effects stated.
- Initially focus Cancel on destructive confirmations.
- Put short progress, success, and error messages consistently in the fixed
  footer; use result pages for detailed batch outcomes.
- Keep browsing available during work where safe; disable conflicting actions.

## 8. Consolidate navigation behavior

Introduce explicit page routes with return destinations and saved view state,
using the existing panel infrastructure.

Rules:

- Enter opens or activates the selected row.
- Space operates an explicit toggle.
- `/` filters the current list.
- Escape clears an active filter first, then follows visible Back.
- Back returns exactly one level and restores previous selection and viewport.
- Setup cancellation has a clear destination.
- Background results update the relevant page without unexpectedly opening it.
- Leaving an accepted save explains that it continues; leaving a search cancels
  its owned work.

## Implementation phases

| Phase | Work | Completion criteria |
| --- | --- | --- |
| 1 | Define page map, terminology, return rules, and terminal mockups | Every search, setup, management, and cancellation path has a defined destination. |
| 2 | Implement shared navigation state and matching entry/manage pages | Back, filtering, refresh, and item selection behave consistently in both sections. |
| 3 | Improve search and discovery details | Results are easy to scan; details preserve context and expose a clear next action. |
| 4 | Complete setup/import/install and update/removal flows | Reviews, progress, completion, partial failure, and retry are covered end to end. |
| 5 | Integrate MCP permissions/authentication and finish validation | One server can be managed from its detail page; documentation matches behavior. |

First implementation milestone: matching entry pages, informative Manage lists,
and reliable Back behavior. This establishes the structure for deeper search and
setup changes.

## Validation and documentation

- Walk through both complete journeys in a terminal at narrow and normal widths.
- Verify keyboard and mouse navigation, long lists, wrapped descriptions,
  loading failures, stale results, cancellation, and active background work.
- Extend existing navigation tests to cover complete journeys and origin-aware
  return behavior.
- Check partial batch failures and acknowledged versus unconfirmed saves.
- Run required unit, lint, and production-type checks; report incomplete or
  timed-out runs honestly.
- Update `AGENTS.md` and relevant user documentation when behavior changes.
- Preserve current transport, source-verification, permission, credential, and
  workspace boundaries throughout the redesign.

## Resume instructions

Before implementation, recheck the working-tree state and current code because
this plan was recorded against an already modified checkout. Preserve existing
user changes. Follow the agreed phase boundary and track completed work,
validation results, and remaining gaps in this document as implementation proceeds.

## Implementation progress

### 2026-10-04: Clarify update action labels

- Completed one small task from section 7: both Manage lists now show Check for
  updates, and both installed-item details show Check for update.
- Review confirmation actions retain Update skill, Update MCP, and Update all,
  since those actions apply the reviewed changes.
- Stable row IDs, action handlers, and update behavior are unchanged.
- Updated `AGENTS.md` to describe the labels and review behavior.
- Validation: `UV_CACHE_DIR=/tmp/klaude-ux-uv-cache uv run --frozen --offline
  pytest tests/unit/test_settings_panel.py -q` completed with 42 passed.
- Remaining: all larger entry-page, navigation, management, search, setup, and
  feedback changes in this plan. No full suite or interactive walkthrough was run
  for this label-only task.

### 2026-10-04: Add Manage heading enabled counts

- Both Manage headings now show `N installed · M enabled` using their existing
  inventory snapshots. Loading labels and MCP inventory truncation warnings remain.
- Skills retains its existing enabled-default interpretation; MCPs uses the
  configured enabled flag. No connections or extra inventory reads are introduced.
- Updated `AGENTS.md` to document the heading counts.
- Validation: the focused settings-panel suite passed all 42 tests; Ruff passed
  for both changed Python files. No interactive walkthrough or full suite run.
- Larger navigation and list-row improvements remain pending.

### 2026-10-04: Show enabled state in Manage rows

- Both installed-item lists now display Enabled or Disabled beside their source
  under STATUS / SOURCE. Names, descriptions, stable identities, and detail
  navigation are retained.
- This completes the initial per-item status visibility improvement in section 2.
- Validation: 42 focused panel tests passed; Ruff passed for both changed files.
- Larger entry-page, filtering, and navigation changes remain pending.

### 2026-10-04: Clarify removal action labels

- MCP item details and Manage removal confirmation now use Remove server.
- Skills item details now use Delete skill; the existing confirmation already
  describes deleting the skill's files and indexed content.
- Existing action identities, confirmation requirements, and removal scope remain.
- Validation: 42 focused panel tests passed; Ruff passed for both changed files.

### 2026-10-04: Entry pages and Manage navigation milestone

- Completed the unfinished typed MCP entry-page migration and made Manage installed
  the first action in both categories. Each compact entry has one inventory heading,
  Search catalog, setup/import actions, and Back. MCPs retains global Permissions.
- Moved Skills drop-folder instructions and filenames to a dedicated Import page.
  Opening that page never imports; its explicit action uses the existing ordered
  worker. Home shows the detected-file count only. Import progress remains visible
  while open; accepted writes survive navigation without reopening closed pages.
- Added shared All / Enabled / Disabled filtering to both Manage lists. Status
  selection, text filtering, selected item, and viewport survive detail/Back and
  refresh using the existing shared PanelState.
- Added empty-inventory search actions and a Skills import action. Their return
  paths retain the actual originating page. Category Manage remains enterable
  while inventory is loading or a write is pending.
- Separated MCP Refresh list from Refresh tools. Metadata refresh never connects
  or submits a tool reload. Refresh tools retains the existing read-only reload
  operation and does not imply reconnecting a server.
- Typed pages now follow their explicit Back/Cancel actions on Escape after
  clearing active filtering, reducing dependence on page-ID cancellation cases.
- Added navigation tests for status filters, filtered detail return, both search
  origins, import completion after closing, retained drafts, and metadata-only
  MCP refresh. Updated legacy expectations to the new labels and first row.
- Broader validation found one existing MCP inventory expectation missing the
  source/description/update metadata already supplied by the working-tree code;
  corrected that expectation while retaining secret and read-only assertions.
- Validation: all tests in `test_cli_commands.py`, `test_settings_panel.py`,
  `test_mcp_search_panel.py`, `test_skill_discovery.py`, `test_mcp_inventory.py`,
  and `test_mcp_updates.py` completed with 885 passed and 1 skipped. This is the
  CLI/settings validation surface, not the full repository unit suite.
- Repository-wide Ruff passed. Production-source mypy passed across all 79 source
  files. `git diff --check` passed. Automated Prompt Toolkit keyboard/resize tests
  cover widths 24, 70, and 120; a manual terminal walkthrough remains pending.

### Remaining work

- Entry counts currently use the inventory heading beneath the fixed breadcrumb;
  moving them into the fixed header remains a presentation follow-up.
- Section 2 still needs bounded description previews, next-neighbor selection
  after deletion, and Needs attention filtering if supported by reliable state.
- Complete the explicit route map for all setup/update/cancellation paths before
  deeper restructuring. Legacy setup/editor paths still have specialized returns.
- Sections 3–6 remain pending: unified details and permissions, search controls
  and cache presentation, source-detail simplification, and complete installation
  and import reviews/results.
- Section 7 still needs selectable batch updates, consistent footer/result
  feedback throughout, and confirmation-label/focus consistency.
- Run a manual terminal walkthrough in addition to automated keyboard/resize tests.

### 2026-10-04: Correct Manage table placement

- Moved both Manage table headers out of the fixed breadcrumb/header area and
  placed them immediately before installed items, below Filter, refresh, and update
  actions. A blank row separates those controls from the table.
- Added an explicit inventory table section so ordinary navigation actions never
  inherit the installed-item column layout. Headers are non-selectable and stay
  with matching inventory rows during filtering; filtering only controls hides
  the unrelated table header. Narrow terminals retain a stacked inventory layout.
- Existing search-result table presentation is unchanged.
- Reserved enough column width for STATUS / SOURCE at medium widths, using the
  same widths for headings and item cells.
- Validation: 193 focused panel, table, Manage-navigation, and discovery checks
  passed; repository-wide Ruff and production mypy (79 source files) passed.
  Rendered sample Manage pages at 70 and 120 columns to verify the actual control /
  table ordering. No full repository suite or manual live-terminal walkthrough.

### 2026-10-04: Rename Manage selector

- Renamed Show to Filter in both Manage pages, retaining All / Enabled / Disabled
  choices and existing navigation behavior.

### 2026-10-04: Use outcome colors for settings feedback

- Progress such as Checking verified Skill sources and MCP Registry checks now
  uses muted text. Successful all-current checks and acknowledged Skill changes
  use green; warnings use yellow, and errors use red.
- Skill actions and update checks carry explicit outcome tones rather than
  guessing success from message prefixes. Skill detail notices match the footer.
- Worker outcomes distinguish partial imports, already-installed Skills, and
  unconfirmed changes as warnings, including when part of an operation succeeded.
- Page-local update notices survive same-page refreshes and clear when navigating
  elsewhere. MCP reload/save progress is replaced after its acknowledgement.
- Corrected the shared warning style to yellow and gave errors a separate red
  style. Save unconfirmed remains yellow when an accompanying error is red.
- Validation: 88 focused CLI feedback/navigation, worker-outcome, and shared
  panel tests passed; repository-wide Ruff and production mypy (79 source files)
  passed. A broader combined run stopped advancing at the knowledge-store tests
  and was interrupted; it is not a passing full suite. No manual live-terminal
  walkthrough was performed.

### Next task

Improve installed-item details, starting with MCP Tools & permissions and an
origin-aware return path. Preserve the enabled-versus-connected distinction and
existing setup, permission, transport, and exact-definition checks.
