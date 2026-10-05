# Whole Settings UX audit

Date: 2026-10-04
Baseline: checkpoint `17dfd05`, followed by the reported Input Field height reset fix.
Status: Baseline analysis. Implementation progress is recorded in
[MCPs and Skills settings UX plan](mcp-skills-settings-ux-plan.md).

## Assessment

Settings has a usable shared foundation, but its workflows are not yet equally
predictable. MCPs and Skills entry pages now follow that foundation well. Their
search, detail, installation, and permission journeys still require more effort
than the simpler appearance pages.

The planned improvements should make information easier to scan and make actions
and return destinations predictable. The existing panel infrastructure is a
suitable base for this work.

This comparison covers the application's own TUI pages and familiar interaction
principles: visible location, consistent controls, clear action consequences,
preserved context, and recoverable failures. It is not a benchmark against
specific external TUI products or a user study.

## Inspection and evidence

- Inspected the Settings overview, all 12 categories, shared panel/picker code,
  category actions, search, setup, confirmations, and cancellation handlers.
- Rendered 26 representative pages through the current page builders at panel
  widths of 40, 70, and 120 terminal cells. These are seeded examples, not live
  server or installed-skill inventories. Samples use three Skills, two MCPs,
  default permission-tool names, and a 240-character Skill description matching
  the inventory reader's existing bound.
- Rendered body lengths measure content density, not the number of lines visible
  at once. The actual scrolling panel body has a preferred height of 12 lines
  and a maximum of 18, subject to available terminal space.
- Existing panel/picker tests: 54 passed. Selected category, keyboard, mouse,
  resize, filtering, setup, confirmation, and return-navigation tests: 40 passed.
- The reported height reset crash was separately reproduced with Enter and mouse
  activation, then fixed and covered by regression tests. All 17 selected
  height/reset/appearance tests passed; repository-wide Ruff and production
  mypy (79 source files) passed.
- No live-network discovery, credential operations, or manual live-terminal
  walkthrough was performed for this audit. The full repository suite was not run.

## 1. Review of every Settings category

| Page | What works | Remaining UX concern |
| --- | --- | --- |
| Settings home | Grouped overview, current summaries, stable category selection on return | Summary formats vary by domain; users need clear distinctions between configured, enabled, available, and active. |
| Theme | Small parent page, temporary preview, Current markers, scoped reset | Keyboard behavior comes through the legacy picker adapter, unlike newer typed pages. |
| Input Field | Compact border/height controls, presets and custom range | Height-page reset crashed by parsing the reset label as a number. Fixed during this audit; reset restores only height and returns to the parent. |
| Divider | Typed rows, independent colors, retained selection, explicit reset scope | Multiple subpages are reasonable; keep their Current and preview conventions as the reference for other selection pages. |
| Spinner | Preview, Current marker, custom draft before Apply | Its 94 selectable rows produce substantial scrolling; at medium widths metadata stacks below almost every choice. Back is a scrolling body row. |
| Models | Source/provider/model hierarchy, authentication controls, active-model markers | Current choice, preview, and queued next-prompt selection are different states; keep each explicit when borrowing conventions for MCP enabled/connected state. |
| Providers | Keys grouped by purpose, masked editing, configured state | Relationship to Models and Tools is indirect. Codex account login is described through static CLI guidance despite the model flow offering an interactive route. |
| Tools | Clear sections, direct toggles, immediate live preference updates | Long page; an enabled provider/tool is not necessarily configured or currently usable. Related provider-key and permission pages lack direct links. |
| MCPs | Compact Manage-first home, explicit discovery/setup/import actions, installed/enabled counts | Installed detail and permissions are separate branches; setup and completion often return to the category home. |
| Skills | Compact Manage-first home, separate import page, explicit source verification | Manage rows remain dense, catalog detail contains too much metadata, and installed/catalog identities are not joined into useful navigation. |
| Memory | Familiar list → detail → edit/delete flow, private editor, confirmation and exact-ID writes | Loading can disable management; the reason should remain visible. Its negative confirmation action is Back, which differs from MCP Cancel. |
| Permissions | Grouped policies, preset preview, scoped persistence | Individual MCP rows are omitted from the root page and live under MCPs. Global presets operate on registered tools, so this relationship should be visible. |
| Runtime | Execution/device/performance/files grouping, bounded presets and custom input | Calibration and external Nano editing are different interaction modes; provide clear progress and a predictable return destination. |

Dense pages are not automatically poor UX. Spinner, Tools, and Permissions contain
many legitimate choices. The distinction is whether each row is concise and the
next action remains clear. MCP/Skills workflows need better information hierarchy
and coordination in addition to shorter lists.

## 2. Shared layout and keyboard conventions

### Keep

- Fixed breadcrumb/header and help/status footer around the scrolling body.
- Stable row IDs, retained filtering, selection, and viewport on normal returns.
- Non-selectable headings, semantic toggle rows, clear Current markers.
- Enter to activate, Space for explicit toggles, slash for local filtering.
- Escape clears filtering before following the visible Back/Cancel action.
- Safe initial focus for destructive confirmations and preserved composer drafts.
- Existing distinctions between preview, applied live intent, and acknowledged save.

### Resolve

1. **Typing behaves differently between page families.** Legacy panels begin
   filtering when ordinary characters are typed. Typed panels require slash first
   and ignore ordinary characters outside filter mode. Choose one documented
   convention and apply it consistently without intercepting private editors.
2. **Table placement is only partly fixed.** Manage headers now belong to their
   inventory body sections. Both Search pages still render table headers above
   Search query, Source, and Sort controls.
3. **Manage header height is stale.** `_panel_header_height()` reserves three
   lines for any wide table page, while `render_header()` emits only two when
   the table header lives in the body. This wastes one fixed-header line.
4. **Breadcrumb compaction loses context.** When a breadcrumb is too wide,
   `render_header()` retains only the last segment. Keep enough parent context
   to distinguish catalog detail, installed detail, and setup.
5. **Help does not describe every page accurately.** Generic Enter/open/apply and
   Escape/back text is reused for confirmations and cancellations. Derive hints
   from the page's actual actions; distinguish local filtering from remote search.
6. **Back is not a sticky action.** Back/Reset rows sit in the scrolling body;
   only the help/status footer is fixed. Preserve Escape as a reliable shortcut
   and evaluate a compact persistent navigation hint before changing focus layout.
7. **Long feedback is clipped.** Footer status is limited to half the page width.
   Important failure and recovery details need an accessible expanded notice or
   result view rather than relying on a truncated sentence.

## 3. MCPs and Skills: concrete remaining problems

| Finding | Evidence | Consequence | Priority |
| --- | --- | --- | --- |
| Search headers precede controls | Both search builders set `column_headers` without a results table section | The same visual confusion previously fixed in Manage remains in Search | First |
| Manage combines status and long source attribution | Repository paths wrap in STATUS / SOURCE; descriptions wrap independently | Three representative Skills consume 28 body lines at 70 columns, versus 17 at 120 | First |
| Installed details lead with metadata | Source/description/files or transport/tool count precede primary actions | Users must read past secondary information to change state | Next |
| MCP detail has no tool-permission entry | `manage_detail_page()` exposes Enabled, update, removal and Back | Managing one server's policies requires leaving its detail and browsing a separate server list | Next |
| Global Permissions hides the individual MCP branch | `_permission_panel_page()` skips MCP SERVERS | Users may not discover where external-tool policies are managed | Next |
| Skill catalog detail exposes 15 metadata fields | URLs, timestamps, audit/first-party Unknown fields and compatibility notices are always expanded | Representative detail has 41 body lines at 70 columns | Next |
| Provider/sort choices cycle on Enter | SkillDiscovery switches providers/sorts directly; MCP sort cycles its known choices | Available alternatives are not visible before the setting changes | Next |
| Refresh and error presentation differs | Both Search pages use Search again; MCP cache notice lacks the Skills page's visible age; discovery failure rows use warning tones broadly | Users cannot predict refresh, retry, freshness or error meaning across the two catalogs | Next |
| Installation review differs | Skills requires pinned-source confirmation; MCP plan inputs previously finished directly in a save | MCP now presents a disabled-install review and saved-result page | Implemented; import review remains |
| Setup Back is not always one step | MCP authentication Back and cancelled setup inputs return to MCPs home | Users lose entered setup context rather than editing the preceding answer | Later |
| Completion lacks a useful destination | MCP save returns to home; catalog Skill installation marks Installed without an Open installed item action | Users must find the newly installed item manually | Later |
| Removal conventions differ | MCP uses Cancel; Skill deletion uses Back and a Confirm deletion title | Both are safe initially, but the vocabulary for abandoning a destructive action differs | Next |
| Batch review is all-or-nothing | Update candidates are information rows followed by Update all | Users cannot choose a subset without checking items individually | Later |

The description reader already limits installed Skill descriptions to 240
characters. That is a data bound, not a readable row-height limit. Rendering
should provide a short preview; any fuller source metadata needs a separate
bounded read rather than pretending the inventory contains the entire text.

Search/source-resolution/install status colors also need to inherit the explicit
outcome contract already added to Manage: muted progress, green acknowledged
success, yellow warnings, red errors. A stale result with a failed refresh can
carry a warning; a failed operation without usable results needs error feedback.

## 4. Recommended coordinated journeys

```text
Settings
  MCPs / Skills
    Manage installed → Item detail
      Enabled toggle
      Check for update → Review → Acknowledged result
      Source details
      Remove/Delete → Confirm or Cancel → Nearby remaining item
      MCP: Tools & permissions → Tool policies → Same item detail
    Search catalog → Catalog detail → Review source/setup → Install → Result
      Open installed item
      Return to the same results, query, filter, page and viewport
    Add/Import → Configure or preview → Review → Apply → Result
```

- Keep the existing category names and Manage-first entry structure.
- Use the same visual order for detail pages: identity/summary, state and primary
  actions, source/version summary, secondary details, destructive action, Back.
- MCP remains disabled after install/update until explicit review and enabling.
- Distinguish enabled configuration, cached tool definitions, observed connection
  state, authentication and permission policy. Do not invent a live health state.
- Reuse the existing MCP permission page from item detail and from a visible
  global Permissions link. Both routes return to their actual origin.
- Preserve source identity and provider metric meanings across catalog views.
- After success, show the acknowledged outcome with an actionable next step.

## 5. Implementation order after this analysis

### A. Shared presentation corrections

Move both Search table headers directly above results; correct Manage fixed-header
height; bound inventory previews by visible lines; shorten inline source labels
while keeping full attribution searchable and available in details. Use existing
typed table sections and renderer state.

Acceptance: controls stay above tables at 40/70/120 columns; no empty reserved
header row; long descriptions no longer consume most of the viewport; filtering
and focus restoration still work.

### B. Details, permissions, and negative actions

Give installed details a common order. Add MCP Tools & permissions and a global
Permissions cross-link with explicit return origins. Use Cancel for rejecting a
destructive confirmation and Back for ordinary navigation. Restore a nearby
remaining item after deletion.

Acceptance: a server's policy page is reachable directly from its detail; all
entry paths return correctly; Cancel never mutates; deletion does not reset
selection to an unrelated first control.

### C. Search and source detail

Use visible Source/Sort selection pages. Normalize Refresh results versus Retry,
result counts, supported pagination/limits and freshness. Present concise catalog
detail and put additional provenance behind Source details. Carry semantic
feedback outcomes through search and installation pages.

Acceptance: online query and local filter remain distinct; sorting keeps its
actual provider meaning; errors are distinguishable from cached/stale warnings;
Back restores the complete results context.

### D. Setup, import, updates, and completion

Add meaningful setup steps with editable earlier answers, final review, import
preview/outcomes, selectable batch updates, and completion routes to the installed
item or the original results. Retain exact-definition checks and ordered writes.

Acceptance: every apply action has clear scope; accepted background work remains
acknowledged honestly; returning or cancelling does not discard unrelated drafts;
secrets never appear in review, transcript or exported state.

### E. Whole-Settings consistency pass

Apply the chosen typing/filter rule and accurate page hints across typed and
legacy panels. Improve Models/Providers/Tools coordination with links to existing
flows. Review dense Spinner, Tools and Permissions rows at realistic terminal
sizes. Keep scoped resets and current/live/saved state distinctions explicit.

Before considering the work complete, perform a live keyboard/mouse walkthrough
in addition to focused automated navigation, resize and outcome tests.

## 6. Implementation references

- [main.py](../apps/cli/src/klaude_cli/main.py): `_settings_home_page`,
  `_open_settings_category`, `_build_key_bindings`, `_panel_header_height`,
  `_panel_footer_fragments`, `_cancel_choice`, setup and permission routes.
- [settings_panel.py](../apps/cli/src/klaude_cli/settings_panel.py): header/body/footer
  layout, width thresholds, body table sections and retained PanelState.
- [pickers.py](../apps/cli/src/klaude_cli/pickers.py): stable IDs, fuzzy filtering,
  exit-row retention and missing-item selection fallback.
- [skills_panel.py](../apps/cli/src/klaude_cli/skills_panel.py) and
  [mcp_management.py](../apps/cli/src/klaude_cli/mcp_management.py): installed pages,
  update/removal reviews and controls.
- [skill_discovery.py](../apps/cli/src/klaude_cli/skill_discovery.py) and
  [mcp_search_panel.py](../apps/cli/src/klaude_cli/mcp_search_panel.py): catalog
  controls, result tables, source/detail and install feedback.
- [MCPs/Skills plan](mcp-skills-settings-ux-plan.md): original analysis and the
  chronological implementation record. Earlier findings there are historical;
  this audit describes the current checkpoint.
