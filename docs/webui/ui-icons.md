# WebUI icons

Font Awesome Free **7.2.0 Solid** is the default UI icon source. The reviewed
subset contains 90 upstream glyphs, shipped as inline SVG paths in the existing
`app.js` bundle. There is no CDN, font download, React dependency, npm install or
additional HTTP route at runtime. This follows Font Awesome's [bare SVG
integration](https://docs.fontawesome.com/web/add-icons/svg-bare).

`static/icons/ui/registry.json` maps semantic names such as `chat`, `tools`,
`vision`, `refresh` and `workspace` to Font Awesome glyphs. Its documented custom
entries retain the approved rounded disclosure arrow and provide matching filled
landscape/portrait frames. Provider/model logos remain in the separate AI icon
registry. Klaude branding, Material loading/shape animations and illustrations
retain their existing artwork.

The Markdown renderer uses this same registry for response actions, code-block
Copy/Download/Preview controls, speech, branching/retry, and the Share dialog.
Social-app logos retain their existing separately licensed brand paths.

## Using and extending icons

- In the WebUI, call `libraryIcon('chat')`. Early shell modules use
  `window.KlaudeUIIcons.create('chat')` before `library.js` loads.
- Static HTML SVGs declare `data-ui-icon="chat"`. The early renderer changes
  their artwork in place, preserving IDs, classes, labels and control handlers.
- Workspace, Library, Integrations, Store and Activity page headings use
  `class="page-title" data-page-icon="workspace"` (with the respective alias).
  Store keeps its changing title in `store-title-label` so navigation preserves
  the heading icon. Title icon boxes match the heading's font size (`1em`) while
  keeping the shared reduced optical scale. Settings category headings use the
  same sizing, without changing sidebar or field icons.
- Add a semantic alias in `icons/ui/registry.json` for new controls. Reuse the
  Solid family. If no suitable Free icon exists, add a `custom` filled path with
  a 24px viewBox and a reason, matching the family's weight and rounded geometry.
- Do not paste unrelated icon sets or introduce a CDN into product pages.

To add an upstream glyph, edit the registry and run:

```sh
.venv/bin/python scripts/vendor_ui_icons.py
python3 scripts/bundle_ui_icons.py
python3 scripts/bundle_webui_loading.py
```

The maintenance downloader verifies the npm archive's published SHA-512
integrity and reads fixed members without executing JavaScript or install
scripts. `icons/ui/manifest.json` retains the package version, archive integrity
and generated asset hashes. The complete upstream notice is retained in
`icons/ui/LICENSE.txt` (Fonticons, Inc.; SVG icons CC BY 4.0, code MIT).

The renderer uses the upstream viewBox, `currentColor`, decorative ARIA and
non-focusable SVGs. A shared CSS rule prevents old stroke-based control styles
from hollowing out the filled paths. Filled glyphs render at 82% optical scale
inside their existing SVG boxes, keeping the denser artwork restrained without
shrinking control targets or moving labels. Custom chevrons retain their geometry.
Square controls use `--square-control-size`, matching the first navigation rail's
36px visible face on every viewport and pointer type, with 8px corners. This
includes shared icon buttons, view tools, pagers and icon-only Markdown actions;
labeled buttons and model tiles retain their own layout.
Intentional tile/container clipping remains
owned by those components. Native controls and accessible control names are
unchanged. Unknown dynamic names retain the generic-file fallback.

## Validation

```sh
python3 scripts/bundle_ui_icons.py --check
python3 scripts/bundle_webui_loading.py --check
python3 scripts/bundle_webui_expressive.py --check
.venv/bin/pytest tests/unit/test_webhost_ui_icons.py
.venv/bin/python scripts/webui_ui_icons_smoke.py
```

The isolated Chrome smoke blocks external HTTPS, renders every upstream glyph,
semantic alias and custom specialty, and checks Chat, Model Defaults, Agent
Settings and Library at 320/390/768/1440px in light/dark mode with bootstrap and
password authentication. It checks native model-picker activation and visible
glyph fill/stroke/geometry, keeps all data in temporary profiles, and captures
screenshots under `output/playwright/fontawesome`. This is focused UI validation;
it does not exercise every domain workflow or model service.
