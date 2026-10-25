# md3.io material reference for Klaude

Checked 2026-10-23 against https://md3.io/docs/ and npm package `material@3.2.4`.
The package is MIT-licensed, zero-dependency, and offers vanilla factories,
web components, and framework adapters. Klaude uses its vanilla progress factory
only. Other components below are design references, not installed Klaude widgets.

## Component catalog

| Family | Documented components | Klaude design use |
| --- | --- | --- |
| Actions | Button, icon button, button group, split button, FAB, extended FAB, FAB menu | Intent and grouping, size and state behavior |
| Selection/input | Checkbox, switch, radio buttons, chips, slider, text field, select, search, date picker, time picker | Accessible control semantics and validation |
| Navigation | Navigation rail, navigation bar, drawer, tabs, menu, top app bar, bottom app bar, toolbar | Responsive destinations and focus/selection behavior |
| Containment | Card, list, carousel, divider, dialog, bottom sheet, side sheet | Tonal hierarchy and compact information density |
| Communication | Badge, progress, loading indicator, snackbar, tooltip | Honest status and feedback |
| Additional references | Form, color picker | Reviewed setting flows and theme controls |

Browse the [full component reference](https://md3.io/docs/) before adapting any
additional widget; each page specifies its options, methods, events, accessibility
and styling. Use Klaude's current contracts and shared components where possible.
The library's [vanilla guide](https://md3.io/docs/vanilla/) recommends importing
only the component stylesheet needed and destroying factory instances when a
view goes away. Its color system uses `--mtrl-sys-color-*` custom properties.
Klaude bridges the progress roles to its live primary, primary-container,
secondary-container and muted tokens rather than importing a second theme.

## Installed progress preset

The [progress reference](https://md3.io/docs/components/progress/) defines
linear/circular and flat/wavy variants. Thin is 4px; the active indicator uses
primary with round caps, the track uses secondary-container, and the gap is 4px.
The linear wavy form has 3px amplitude and 40px wavelength; circular wavy has
1.6px amplitude and 15px wavelength at 40px, scaled with size. Circular wavy
defaults to 48px. The package animates value changes over 500ms, honors the
system reduced-motion preference, and exposes `progressbar` ARIA state.
Klaude's additional in-app reduced-motion setting freezes the preview's last
frame as well. `destroy()` releases its observers and animation frame work.

Theme offers `Material wavy` and `Material wavy static` alongside the existing
Classic wavy static/Classic linear loading bar, plus Material wavy static/Classic
loading circle. The selected Material bar also runs on the splash
screen when selected; the Material circle is available through
`MaterialCircularProgress.create` for determinate work and its Theme preview.
Both are offline at runtime.

The `Material wavy static` circle is a fixed SVG translation of the circular
path in `material@3.2.4/dist/components/progress/features/circular.js` and
its progress measurements in `constants.js`: the same radius, 4px stroke,
1.6px scaled amplitude, 15px scaled wavelength, rounded caps and track gap.
It does not run a frame loop. The separate `Material wavy` option still uses
the library's animated canvas. The MIT notice is bundled in
`static/vendor/material-progress-LICENSE.txt`.
The static bar similarly translates `features/linear.js`: thin uses a 4px stroke
and 3px amplitude; thick uses 8px and 6px. Both use a 40px wavelength, the
Material 4px base gap plus stroke width, rounded caps and stop indicator. Its
wave phase is fixed; only progress value and container width update the path.
Thin and Thick are context variants of the selected bar design, not saved
appearance choices. Splash explicitly requests Thick; ordinary progress uses
Thin unless its caller requests otherwise. The saved `material-static` value is distinct from the
animated `material` value and works offline before the main app bundle loads.

Source: npm `material@3.2.4`, progress factory and its transitive core imports,
bundled with esbuild 0.25.12 from
`node_modules/material/dist/components/progress/index.js` as a minified IIFE
(`KlaudeMD3`). The exact library CSS is copied from
`dist/styles/progress.css`. Source archive: npm package `material@3.2.4`.
The bundle command is
`esbuild node_modules/material/dist/components/progress/index.js --bundle --minify --format=iife --global-name=KlaudeMD3`;
the resulting JS is prefixed with its MIT attribution before vendoring.
Vendored files: `static/vendor/material-progress.min.js`,
`static/vendor/material-progress.css`, and
`static/vendor/material-progress-LICENSE.txt`; the MIT notice remains in the
JS/CSS headers and license file. The JS is embedded into `loading-indicator.js`
and `app.js` by `scripts/bundle_webui_loading.py`, while CSS is embedded into
`style.css` by `scripts/bundle_webui_expressive.py`. No external service or
runtime package install is required.

## Integrations filter chips

The [Chips documentation](https://md3.io/docs/components/chips/) and the
installed package's `dist/styles/chips.css` and
`dist/components/chips/chip/chip.js` guided the Skills and MCP Connections
All/Enabled/Disabled filters. Filter chips have a 32px visual face, 8px corners,
an inset 1px outline, 14px label, selected `secondary-container` surface,
18px checkmark and 48px touch target. Klaude uses its existing semantic color
roles and native buttons, with a small shared CSS implementation in
`static/expressive.css`; no chip package code or assets were copied or vendored.

Klaude's status filters remain single-select and required, despite the
documentation page's multi-select demo: All, Enabled and Disabled are mutually
exclusive query scopes. Existing `aria-pressed` buttons and arrow/Home/End
selection remain available, along with click, Space and Enter. The chips wrap
on narrow layouts, keep focus and forced-colors indicators, and honor reduced
motion. The standalone md3.io set uses a grid with focus-only arrow navigation;
Klaude retains its established group/button semantics and arrow-to-select
behavior to avoid changing the filter workflow.

## Library dropdown filter chips

The same Chips component page and `material@3.2.4`'s
`dist/components/chips/chip/chip.js` and `src/styles/components/_chips.scss`
guide Library's always-visible Type, Status and Sort dropdown chips. They reuse
Klaude's shared 32px chip faces, 8px corners, 14px labels, 18px trailing arrows
and 48px touch targets. Non-default values and open menus use secondary-container
roles. Menus reuse the existing native popover/message-menu surfaces, with
single-choice radio semantics and checkmarks.
The chip row never wraps: it scrolls horizontally with its scrollbar hidden,
and popovers follow their trigger while scrolling without being clipped by the row.

The upstream component has a separate trailing action button when `trailingMenu`
is configured. Klaude uses the entire chip as one menu trigger: these controls
choose one value rather than independently toggling a filter and opening a
secondary action. This avoids two competing selection actions for one field.
Native selects preserve existing values, disabled choices, change handlers,
per-tab preferences and URL navigation, and remain visible in browsers without
popover support. No Chips package code or assets were vendored. See
`scripts/webui_library_filter_chips_smoke.py` for focused browser validation.

## Library file-tag input chips

File details use the existing tag renderer with the shared chip face for manual
and AI tags: 32px faces, 8px corners, 14px labels and 18px close icons. Manual tags
are outlined; AI tags use the exact same colors and styling. Read-only tags
remain plain text spans. During editing, a native close button has a 48px-high
target while the chip face stays compact; hover, press and focus feedback paint
the face rather than the invisible touch target. Long labels still wrap safely.
Suggested tag actions reuse the existing filter-chip button and never save on
selection. Reviewed Save tags, Cancel, validation and pending locks are unchanged.

`scripts/webui_metadata_smoke.py` passed real temporary-store editing/removal,
duplicate/limit handling, cancellation, stale/failed saves and AI suggestion
drafts. It checked input-chip geometry and overflow at 320/390/768/1440px in
light and dark modes, with zero browser exceptions. No Chips runtime was vendored.

AI Review's multi-select tags use the same filter-chip face, 48px button target,
8px corners and checkmark behavior as the other filter chips. Unselected AI chips
use the shared text/outlines; selected chips use secondary-container and its on-color.
The existing selection counts, Clear selection, retained drafts and separately
reviewed Save tags flow are preserved.
The isolated inspector probe passed selection, keyboard toggling, clear,
cancelled/expired/rejected reviews and confirmed saves. It checked chip geometry
and overflow in light/dark at 320/390/768/1440px, and compared saved manual/AI
Details faces for matching geometry, background and typography. Zero browser
exceptions. The later removal of AI-specific colors uses the same shared role
rules for both tag origins; the comparison also checks foreground/outline equality.

## Settings slider

The [Slider documentation](https://md3.io/docs/components/slider/) and
`material@3.2.4`'s `src/styles/components/_slider.scss`,
`dist/components/slider/features/tracks.js` and `constants.js` guide the
Surface transparency slider. It uses the documented S size: a 24px track,
8px outside corners, 2px inside corners, 4px by 44px handle, 8px resting
handle gap (7px when pressed/focused), and a 4px stop dot near the inactive
end. The active track/handle use primary and the inactive track uses
secondary-container; a focused value indicator uses inverse-surface roles.

Klaude's native `input[type=range]` remains the interactive and accessible
control, with its existing 0–20% setting and staged Apply/Discard behavior.
The shared `.material-slider` visual layer provides the track, stop dot and
value indicator without copying package code or installing its component
runtime. The md3.io component uses a custom `role=slider` handle and spring
positioning; this adaptation uses native pointer/keyboard behavior and only
animates the value indicator. The package is MIT-licensed; no Slider source
or asset was copied into Klaude.
