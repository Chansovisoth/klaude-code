# Store layout overhaul

Implemented 2026-11-06. References: [Flathub](https://flathub.org/en) and
[GNOME Software](https://apps.gnome.org/Software/). These inform the category,
catalog, installed-list and detail hierarchy; Klaude keeps its own Material
theme, navigation and reviewed operations.

The Store now has descriptive page headings, a search field with an icon,
compact category cards, consistent shelf spacing and model cards that separate
identity from source metadata. Cards retain provider icons, download counts,
source dates and runtime labels. Installed uses one divided surface with
aligned name, size and action columns. Narrow screens keep the size visible
and make the whole row the action.

Downloads separates Active transfers from Download history. Paused work,
unconfirmed outcomes and observed external transfers remain in Active
transfers; this grouping makes no new claim about external byte progress.
Owned progress, Pause/Resume, Stop, recovery and history removal retain their
existing contracts. Controls have 44px targets, including on compact desktops.
An empty or fully dismissed history offers an Explore action.

Model, MCP and Skill details share the same identity/action surface and spacing.
Model facts have distinct labels and values; variant selection is grouped below.
Exact-file reviews, permissions, technical disclosures and installation plans
remain in their existing workflows. Choosing a card never installs a model.

`static/store.css` contains the scoped presentation and is bundled into
`static/style.css` by `scripts/bundle_webui_expressive.py`. Container queries
respond to the Store's available width when both desktop sidebars are open;
mobile keeps the native location chooser. No extra CSS request, framework,
remote font or hosted application is introduced. Shared shell and Theme
settings retain their existing behavior.

## Verification

- `scripts/webui_store_ux_smoke.py`: existing Store/MCP/Skill navigation, detail
  pages, review cancellation, model selection restoration across reload and
  independent Settings drafts; 320, 390 and 1440px, zero browser exceptions.
- `scripts/webui_store_layout_smoke.py`: isolated synthetic catalogs, installed
  models and receipts at 320, 390, 768 and 1440px, light/dark themes. Checks
  page/card overflow, download target sizes, variant review cancellation and
  download-detail dialogs. All 48 layouts passed with zero browser exceptions.
  Screenshots go to
  `output/playwright/store-overhaul/`.
- JavaScript syntax, CSS bundle freshness, focused Ruff and whitespace checks.

Browser evidence uses a temporary profile and local fixture services. It does
not verify production catalogs, real transfers, installation or inference.
Existing workspace changes are preserved; no commit, deployment or production
host restart is part of this change.
