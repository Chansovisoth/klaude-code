# Klaude Expressive: source reference and licensing

Reference audited 2026-10-22:
[end-4/dots-hyprland, 2f2a376](https://github.com/end-4/dots-hyprland/tree/2f2a376fdb2ad738bf55f693dd0b474b64bb0ab8).
The read-only reference is `/tmp/klaude-end4-reference`; QML paths below are
relative to `dots/.config/quickshell/ii`. Its shape Git submodule is pinned to
`e31ec4cb4ebf6a46b267f5c42eabf6874916fa16`.

## Implementation boundary

Klaude remains MIT. The end-4 root is GPL-3.0. No GPL QML implementation, images,
icons, shader, quantization algorithm or polygon code was copied into Klaude.
The web components independently implement measured visual/state behavior with
native HTML, CSS, DOM, SVG and browser animation. End-4's rounded-polygon submodule
has its own Apache-2.0 license; Klaude nevertheless retains its existing,
independently exported Google Material/AndroidX shape pipeline.

Directly included third-party work:

- **Google Material Color Utilities 0.4.0**, Apache-2.0, Copyright Google LLC.
  Pinned npm integrity, generated asset hashes, complete license and adaptation
  notice are in `static/vendor/material-colors-{manifest.json,LICENSE.txt,NOTICE.txt}`.
  The selected exports are bundled/minified, with no algorithm modifications.
- **Google Material Components for Android**, revision
  `66b0eeb53afeb6025ffbbd37734b08e5bce197ed`, and **AndroidX graphics-shapes 1.0.1**,
  Apache-2.0. Existing pinned source hashes, license and notice remain in
  `static/vendor/material-loading-*`. The maintenance Java adapter exports
  closed cubic outlines and matched morphs; Android code does not execute in the UI.
- Existing local Roboto / JetBrains Mono OFL fonts, Markdown/Prism notices and
  application SVG artwork remain authoritative.

The published reference screenshot from `.github/README.md`,
`https://github.com/user-attachments/assets/5d4e7d07-d0b4-4406-a4c9-ed7ba90e3fe4`,
was downloaded to `/tmp/klaude-end4-reference-settings.png` and visually inspected.
It is a comparison input, not a redistributed product asset.

## Component mapping

| End-4 source examined | Measured behavior | Klaude equivalent | Surfaces | Evidence |
| --- | --- | --- | --- | --- |
| `modules/common/Appearance.qml` | Corners 2/6/8/12/17/23/30/full; main text 15/16; section/title hierarchy; tonal layers | `expressive.css` centralized corner/state/motion tokens, local fonts; `expressive-colors.js` role adapter | Entire UI | 88 viewport/theme/page cases, contrast matrix, screenshots |
| `functions/ColorUtils.qml`, `services/MaterialThemeLoader.qml`; root `dots/.config/matugen/config.toml` and templates; `scripts/colors/{generate_colors_material.py,scheme_for_image.py}` | Semantic Material roles, distinct surface levels, generated theme, bounded image sampling, selectable palette variants | Google HCT/dynamic schemes; primary/secondary/tertiary/on/container, five surface levels, inverse/outline/error/success roles; browser-local quantization | Theme and every component | Sixteen presets × nine variants × light/dark; sampled text pairs all ≥4.51:1; local image/Apply/Discard checks |
| `widgets/{GroupButton,SelectionGroupButton,ButtonGroup,FlowButtonGroup,ConfigSelectionArray}.qml` | 5px group gaps; 6px interior corners; selected/full-height outer pills; primary selected and secondary-container idle; selection variant disables width bounce; flow marks ends per rendered row | Native radios and existing button groups; 23px external/9px inner corners, actual half-height selected pills, row-aware end markers, 350ms shape transitions; wrapping variant controls | Theme, permissions, tabs, Library scope/view, Context tabs, Integrations filters | Native keyboard regression; screenshots; measured per-position/row selection roles and radii; single/hidden items, resize, RTL, motion |
| `widgets/RippleButton.qml` | 1200ms bounded ripple; hover/press layers; focus state; rounded clipping | One interruptible pseudo-element ripple per pressed button, shared delegated handlers | Shared buttons, menus, actions | Pointer/keyboard/drop regressions; reduced-motion checks |
| `widgets/StyledSwitch.qml` | 52×32 design, .75 visual scale, 16/24/28 thumb, 350ms expressive movement | 39×24 visual track within 48×44 target; 12/18/21px thumb; native checkbox | Settings and Integrations | Track measurement, native policy/state tests, accessibility scan |
| `widgets/StyledSlider.qml` | Small track 18px, radius 6px, thumb 3px/1.5px pressed, height ≥33px | Native range input, filled 18px track, 33px thumb, progress and accessible value | Theme transparency | Live preview/input and keyboard semantics |
| `widgets/MaterialTextField.qml`, `ToolbarTextField.qml` | Tonal fill/outlined container, primary focus, semantic selection | Existing labeled native inputs/selects/textarea, semantic focus/error/disabled styles | All forms, search, composer, account | Settings, composer, draft/save, accessibility checks |
| `widgets/{NavigationRail,NavigationRailButton,NavigationRailTabArray,SecondaryTabButton,SecondaryTabBar}.qml`; `settings.qml` | 56px icon zone/32px highlight, 24px icon, 56px rail item; expanded/compact selection; tabs | Existing responsive rail and conversation drawer; 56×32 highlight, 64px web item to fit labels/44px targets; connected panel tabs | Shell, Settings, Context, inspector | 320/390/850/1440 widths; history/focus/control regressions |
| `widgets/WindowDialog.qml`, `SelectionDialog.qml`, `MenuButton.qml` | 23px dialog radius, high tonal surface, 50% scrim; 200ms emphasized entrance; menu 350ms | Native dialog/popover, shared tonal styling, 200ms entrance, retained backdrop/ESC/focus logic | All reviews, account/session/file dialogs, menus | Dialog pointer/touch/backdrop tests and screenshot matrix |
| `widgets/StyledToolTip.qml` | 5px vertical/10px horizontal padding, 12px text, immediate contextual label | One top-layer tooltip, inverse roles, preserved ARIA descriptions, keyboard/hover, edge clamping | Shared icon actions | Browser exception checks and keyboard accessibility |
| `widgets/{MaterialShape,MaterialLoadingIndicator}.qml`; shape submodule `material-shapes.js` | 48px box; .7 inner shape/.2 leap enlargement; 12s continuous rotation; 800ms shape cadence; 90°/350ms InOutQuad leap; 750ms standard-curve zoom; 200ms effects morph | Existing matched Google cubics with source-measured web choreography; shared circle/pill/oval/diamond/cookie/burst/sunny/flower/soft-burst SVG | Loading, refresh, status, theme preview, welcome | Loader cadence/rotation/zoom assertions, moving paths, static strip, lifecycle/reduced-motion tests |
| `modules/ii/sidebarLeft/{AiChat,SidebarLeftContent}.qml`; `aiChat/{AiMessage,MessageCodeBlock,AttachedFileIndicator,MessageThinkBlock}.qml` | Dense technical chat, connected controls, 12px code corners, separated tonal header/body, compact actions | Existing stable Markdown renderer, content-sized user bubbles, shared composer, code/actions/attachment/status surfaces | Chat | Markdown/streaming/selection/copy and composer/drop regressions |
| `modules/ii/sidebarRight/SidebarRightContent.qml` | Layered compact sidebar, 10px content spacing, persistent controls above scroll body | Existing public-event Agent Inspector, connected tabs/task/timeline; closed-by-default responsive Context Panel | Context Panel | Real HTTP/SSE tool/approval/cancel/reconnect checks |
| `modules/ii/wallpaperSelector/{WallpaperSelectorContent,WallpaperDirectoryItem}.qml` | Image-first selector, 4:3 preview cells, thumbnails, breadcrumb/search, spatial arrow navigation, Enter activation | Shared Library square Gallery and bounded derivatives, Current/All scope, previews, spatial keys; navigable workspace rows/breadcrumbs | Full/Context Library; Workspaces | Library inventory 1058/50-image fixture, scopes, gallery keys, preview/navigation/jail tests |
| `modules/ii/cheatsheet/{CheatsheetKeybinds,CheatsheetKeybindsCategory}.qml` | Grouped shortcut reference; platform-aware key names | Searchable command/shortcuts native dialog, Ctrl/Cmd+K, Ctrl/Cmd+Shift+/, Ctrl/Cmd+,; existing action handlers | Shell/major pages/model/session navigation | Search/Enter/Escape/focus tests and screenshots |
| `modules/ii/{bar/BarGroup,dock/DockButton,sessionScreen/SessionActionButton,mediaControls/PlayerControl}.qml` | Connected tonal containers, shared rounding, focus/press corner response and artwork-first surfaces | Shared cards, state chips, button states; no Linux functionality ported | Models, Library, Integrations, Memory, sessions, empty states | Page matrix, model and management regressions |

`ColorUtils.qml` is under `modules/common/functions`, and widget paths are under
`modules/common/widgets`; the abbreviations in the table avoid repeating them.

## Explicit web adaptations

- **Shapes:** nine named static shapes are exported through the existing official
  Apache pipeline. Seven loader shapes morph with matched cubic geometry. Arbitrary
  decorative shapes are static; there is no general all-pairs morph engine.
- **Selection/press:** the reference's SelectionGroupButton disables width bounce.
  Klaude retains expressive external ends and selected pills, with user-requested
  approximately 24px outer/8–10px inner rounding adapted to the existing tokens
  (23px and 9px). Like `ConfigSelectionArray`, each rendered row has its own ends.
  A shared browser layout observer handles wrapping, hidden/dynamic items, RTL
  and container resizing. Selected radii use actual half-height, matching the
  reference and avoiding clamped 9999px shape transitions. Shapes animate with the
  shared 350ms fast spatial curve; tonal colors, focus and small press transforms
  remain. The reference's neighboring 10/20px width exchange is not imposed on
  dense forms or code. Generic hover/press feedback retains each component's
  corners instead of transitioning through a 9999px pill, whose spatial spring
  can overshoot below zero and briefly render square. Explicit segmented
  selection still morphs. Selected sessions/tags use finite 23px theme rounding;
  Send retains its 17px corners. Models shares Integrations' stable collection
  rows. Regression evidence: `hover-corners-validation.md`.
- **Loading:** geometry is Google's pinned Android implementation; timing/rotation/
  zoom now follow end-4. The previous 650ms Android spring animation is replaced.
  One shared RAF pauses for hidden/reduced/classic state; the classic spinner uses
  CSS. Both app/system reduced motion retain a static marker. Sources/markers and
  operation identity remain unchanged.
- **Dialogs:** native focus trapping and instant close/review cleanup take priority
  over animating an exit. Entrance is a 24px translation/scale, rather than resizing
  layout height through a 60px QML displacement. No review action waits for motion.
- **Palette extraction:** browser-local 96×96 RGBA sampling, Celebi quantization and
  Material scoring replace Linux Matugen/OpenCV processes. PNG/JPEG/WebP inputs are
  capped at 16 MiB and decoded at reduced size. Only a seed is stored. Transparency
  is capped at 20% over the themed application background; no desktop wallpaper,
  external image fetch, backdrop blur or image upload is introduced.
- **Responsive layout:** web targets remain at least 44px for principal controls.
  The QML settings window's 750px minimum is replaced by card container queries and
  phone layouts. Gallery remains square to preserve Klaude's shared browser contract.
- **Content rows:** connected inventory rows keep their existing outer/inner
  corner hierarchy across hover, focus and press. Their full-row action buttons
  inherit the same stable shape; state colors, ripple and focus supply feedback.
  This avoids conflicting card/pill transitions changing the pointer hit area.
  Segmented controls retain their separate selection shape animation.
- **Data:** inspector diagnostics and model metadata remain limited to actual public
  API fields. Main model rows expose real Thinking efforts as chips; unsupported
  tool/image capability claims, token counters or invented plan progress are absent.
  Connection setup/download/serving and unavailable commands retain their existing
  terminal boundary. New commands never grant permissions or bypass approval.
- **Long sessions:** stable streaming nodes, bounded inventories, paged catalogs and
  lazy authenticated thumbnails are preserved. No second virtualizer/re-render loop
  is added. The directory reader already caps rows at 300.

## Maintenance

Edit `expressive.css`, `expressive.js`, `expressive-colors.js` and the runtime below
the owned color block in `loading-indicator.js`. Run:

```sh
python3 scripts/bundle_webui_loading.py
python3 scripts/bundle_webui_expressive.py
python3 scripts/vendor_webui_loading.py --cache /tmp/klaude-official-loading --check
```

The first script refreshes the early color bootstrap and app bundle while
preserving the controller outside its marked block. The CSS script preserves all
pre-existing rules outside its owned block. All sources/licenses ship in the wheel.
No new public script route, frontend framework, runtime npm install or CSP change.

For color-library maintenance only, install pinned packages in a temporary directory
and rebuild `scripts/material_color_entry.js` with **esbuild 0.28.2**, `--bundle
--minify --format=iife --legal-comments=inline`. Verify the pinned npm integrity,
copy the license, update the manifest hashes, then rebuild the app/early bundle.
The build used `/tmp/klaude-material-build`; no `node_modules` or npm lockfile enters
the repository. Accessibility tooling is also maintenance-only.
