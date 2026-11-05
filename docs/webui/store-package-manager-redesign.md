# Store and model preferences: package manager redesign

Implemented 2026-10-30 after reviewing the rendered Store, model details,
MCP/Skill details, Models, and Image generation pages. The earlier copy and
surface changes retained too much of the original structure; this revision
changes the navigation and page composition.

## Reference review

Sources inspected directly, including the official interface screenshots:

- [Flathub](https://flathub.org/en) and an actual
  [app detail page](https://flathub.org/en/apps/io.github.db_mobile.resonance):
  clear app identity and install action, short summaries, category collections,
  source/options subordinate to the main decision.
- [Flathub quality guidelines](https://docs.flathub.org/docs/for-app-authors/metainfo-guidelines/quality-guidelines):
  concise, understandable summaries; technical information in separate fields;
  descriptions that add information rather than repeating the summary.
- [KDE Discover](https://apps.kde.org/discover/) and its
  [official screenshot](https://cdn.kde.org/screenshots/plasma-discover/plasma-discover.png):
  persistent sidebar destinations, category browsing, compact application cards,
  and a main content area dedicated to the current destination.
- [GNOME Software](https://apps.gnome.org/Software/), including its Explore,
  Details and Installed screenshots: distinct browsing and installed views,
  clear install actions, consistent rows for installed items.
- [GNOME navigation guidance](https://developer.gnome.org/hig/guidelines/navigation.html)
  and [sidebars](https://developer.gnome.org/hig/patterns/nav/sidebars.html):
  a stable location hierarchy and explicit parent/back navigation.

These are design references, not evidence of usability testing of Klaude.
Klaude retains its Material colors, components and review contracts. Models do
not supply verified app screenshots or user ratings; the UI does not fabricate
those, or interpret repository popularity as compatibility.

## Implemented structure

### Store

Desktop has a dedicated two-pane workspace. Its sidebar replaces the
conversation sidebar while Store is open. It contains Explore, Installed,
Downloads, Chat models, Image models, MCP servers, Skills, and Advanced model
files. It remains available while viewing details. On phones, a native location
chooser replaces the sidebar; details have an explicit parent/back action.

Explore provides four visual category entries and bounded catalog shelves.
Search stays scoped to the current catalog. Native model catalog controls and
exact-reference installation are inside Filters. Image models exposes complete
managed installs; raw image files have their own Advanced destination.

Installed shows model inventories and explicit links to installed MCP and Skill
management. It does not claim those separate inventories are merged. Downloads
retains owned transfer progress/recovery and managed installation controls.

Cards use an icon, name, short purpose and useful source/status metadata. Detail
pages use a shared identity header with one primary install/use action. Long
source text, technical facts, permissions and install-name options are available
through native disclosures. Full permissions and exact targets remain in the
installation review. A completed MCP add explicitly shows that it is disabled.

### Settings > Models

Connections remains first. The four primary defaults are individual model cards,
in two columns on desktop and one column on phones. Advanced defaults keeps
fallbacks, token controls and Vision enable separate. Image generation is a
clear destination below these controls. The conversation sidebar is omitted
while this Models workspace is open.

The picker shows names and exceptional capability states without repeating a
full internal reference and compatibility paragraph on every row. Exact IDs
remain available through titles, the selected field and existing save reviews.

### Settings > Models > Image generation

The selected model is the main card: image icon, model identity, service type
and Change action. Below it are generation on/off, Get more image models, and
Advanced. Manual model IDs and service configuration live in Advanced. Opening
an explicitly chosen advanced provider uses that provider's catalog.

Complete managed installation and model management live in Store; Settings no
longer repeats the installer catalog. Installation/unknown-outcome progress
remains visible when relevant. Choosing a model stages a draft; Apply and
Discard remain separate from downloading, repair, runtime loading and the
current conversation.

## Interaction and validation

The redesign preserves the existing operation owners, review endpoints,
credentials, exact-artifact validation, recovery fences and default-save
contracts. Merely browsing still does not download or load weights.

Focused browser evidence:

- `scripts/webui_store_ux_smoke.py`: 320, 390 and 1440px, light/dark Explore,
  category navigation, native keyboard activation, model/MCP/Skill details,
  reviewed MCP add-disabled, managed install review cancellation, exact model
  variant cancellation/reload, independent image drafts and installed details.
- `scripts/webui_comfyui_smoke.py --profile /tmp/klaude-comfy-live-profile --layout-only`:
  actual installed bundle selection, Apply/reload and responsive layout, using
  only the isolated profile. No new weights or inference were requested.
- `scripts/webui_model_settings_smoke.py`: complete defaults/picker/save, image
  service checks, connection add-disabled/credentials/enable/test/remove, and
  account/logout walkthrough at 320, 390, 768 and 1440px. Zero console errors.
- JavaScript syntax, focused smoke-script Ruff, CSS source/bundle consistency
  and whitespace checks passed.
- Screenshots: `/tmp/klaude-store-ux/`, `/tmp/klaude-model-settings-evidence/`
  and `/tmp/klaude-comfyui-evidence/`.

This is focused UI verification, not a full repository suite or a new GPU
inference certification. No production settings or running services were
changed. The host reads static files on request; reloading the browser loads
this frontend revision.
