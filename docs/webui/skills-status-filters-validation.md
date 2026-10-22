# Skills status filters — 2026-10-22

Skills now offers All, Enabled and Disabled below its search/import toolbar,
matching the existing Connections control. It reuses the shared expressive
segments, 44px targets, selected tonal roles, focus and arrow/Home/End behavior.
Collection rows keep their stable shapes.

The existing Skills read service accepts an allowlisted `state` of `all`,
`enabled` or `disabled`. It combines status with search before calculating totals
and returning the existing 20-item pages. Responses identify the applied state;
the default remains All. Tab counts remain unfiltered, and no stored enable
state or mutation/review behavior changes.

Changing status resets pagination while retaining search. Allowlisted
`skills-state` URLs integrate with the existing search/page history and reload
behavior. The selected filter survives switching Integration sections. Sign-out
clears the loaded inventory and in-memory filter state. Empty views name the
active status. A paginated older host that rejects or ignores the status filter
shows restart guidance; it never presents an unfiltered page as Enabled/Disabled.
Older full-inventory responses can be filtered before local paging.

Validation:

- **5 passed, 26 deselected:** focused Library management tests, including
  90-item mixed-state inventory/search counts and pagination, invalid states,
  unchanged enable values, existing search paging, unfiltered tab counts and
  read-only metadata behavior.
- `scripts/webui_skills_filters_smoke.py` passed against the real isolated HTTP
  route and service with a 90-Skill fixture inventory. All 90/60/30 All/Enabled/
  Disabled results are reachable across pages; status switches reset the page.
- Search/status combinations, Back/Forward, reload, section navigation,
  arrow/Home/End keyboard selection, empty results, old-host rejection guidance,
  invalid HTTP status filter and sign-out passed with no browser exceptions.
- **24 layout/filter cases:** three states × light/dark × 320/390/850/1440px.
  Controls fit one row with 44px targets and no page overflow. Four desktop/phone
  captures were produced for visual inspection.
- Focused Ruff, JavaScript syntax and `git diff --check` passed.

Evidence: `/tmp/klaude-skills-filters-validation/`.

All data is isolated fixture content. No model/provider calls, user configuration
changes, live-host restart, commit or push occurred. The full repository suite and
physical-device tests were not run. An existing running host needs a restart and
page reload to provide the added read filter.
