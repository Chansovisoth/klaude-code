# Consistent Refresh icons

Refresh actions now reuse the conversation drawer's refresh SVG across Library,
Integrations, Models, chat model selection, Agent settings, Model Defaults,
available model catalogs and Memory. Every icon button retains a descriptive
accessible label and matching tooltip. Knowledge source refresh also uses the
icon and retains its reviewed indexing action.

The Library/Integrations loading indicator overlays the icon in place, retaining
the button's target size. Existing disabled/busy states, request deduplication,
retained content and logout cleanup remain in use. Ordinary status/help text
continues to describe Refresh in words.

Isolated Chrome checks passed:

- `scripts/webui_loading_smoke.py`: navigation, loading, reviewed source refresh
  and stale/logout handling, with zero JavaScript exceptions.
- `scripts/webui_material_loading_smoke.py`: busy indicators, retained content,
  duplicate-click handling and cleanup, with zero JavaScript exceptions.
- `scripts/webui_settings_smoke.py`: accessible labels and single refresh icons,
  responsive layouts from 320 to 1920px, both authentication variants and
  light/dark themes, with zero JavaScript exceptions.

Phone Library and Agent settings screenshots were visually checked. Focused
Ruff, Python compilation, JavaScript syntax and `git diff --check` passed.
This is static UI work; browser refresh loads it without a host restart.
