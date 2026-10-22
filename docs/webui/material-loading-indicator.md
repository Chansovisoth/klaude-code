# Official Material loading indicator

## 2026-10-22 Klaude Expressive update

The older Android-native timing below is historical. The shared loader now uses
the audited end-4 800ms cadence, 90-degree/350ms InOutQuad leap, 12-second
continuous rotation, 750ms standard zoom envelope and 200ms effects morph.
Geometry remains the pinned Apache-licensed Google/AndroidX export. Nine named
static shapes share that pipeline. The optional classic spinner and app/system
reduced motion retain their behavior; held shapes no longer rewrite SVG paths
every frame. Current source mapping and checks: `klaude-expressive-reference.md`
and `klaude-expressive-validation.md`.

## Implementation plan

Reviewed the official M3 overview/specs/guidelines data and its demonstration
video, Google Material Android's animator/drawing delegates and MaterialShapes,
and Klaude's owned delayed loaders, chat activity, motion/theme tokens and static
asset packaging. Preserve all existing dirty changes; no commit or push.

1. Export Google's seven exact rounded shapes and matched cubic morphs using
   the pinned official Material source and its actual AndroidX graphics-shapes
   1.0.1 dependency. Check source hashes and retain Apache notices. Java tools
   are maintenance-only; no new browser/Python package dependency.
2. Port the official 650 ms cadence, 200 stiffness / 0.6 damping spring, 50°
   constant plus 90° spring rotation and -90° drawing orientation. Use the
   official 38/48 active-size ratio and theme roles for optional containers.
3. Reuse delayed request ownership/cancellation for page loaders. Keep content
   skeletons static, real status labels visible, and refresh content intact.
   Replace the running chat activity dot with a small uncontained indicator;
   retain meaningful activity descriptions and stopped/error/input states.
4. Use one shared animation scheduler with visibility/reduced-motion handling.
   Verify geometry against the official export, compare with the official video,
   and test light/dark, narrow/desktop layouts, lifecycle and packaging.

## Official sources and fidelity

The source of truth is Google's [M3 Loading indicator](https://m3.material.io/components/loading-indicator/overview),
including its Specs and Guidelines tabs. Its published design JSON and overview
MP4 were downloaded for inspection, and seven reference-video frames were viewed
alongside Klaude screenshots. Reference media stays under `/tmp`, outside the
product assets.

Google's [Material Web repository](https://github.com/material-components/material-web)
contains loading-indicator tokens but currently no loading-indicator browser
component. The implementation therefore adapts the official native source to
Klaude's existing vanilla JavaScript/SVG rather than adding a framework or an
unofficial third-party indicator.

Pinned Material Android revision: `66b0eeb53afeb6025ffbbd37734b08e5bce197ed`.

- [Drawing delegate and official sequence](https://github.com/material-components/material-components-android/blob/66b0eeb53afeb6025ffbbd37734b08e5bce197ed/lib/java/com/google/android/material/loadingindicator/LoadingIndicatorDrawingDelegate.java)
- [Official animator](https://github.com/material-components/material-components-android/blob/66b0eeb53afeb6025ffbbd37734b08e5bce197ed/lib/java/com/google/android/material/loadingindicator/LoadingIndicatorAnimatorDelegate.java)
- [Official rounded shape construction](https://github.com/material-components/material-components-android/blob/66b0eeb53afeb6025ffbbd37734b08e5bce197ed/lib/java/com/google/android/material/shape/MaterialShapes.java)
- [Native SpringForce solution and equilibrium thresholds](https://github.com/androidx/androidx/blob/androidx-main/dynamicanimation/dynamicanimation/src/main/java/androidx/dynamicanimation/animation/SpringForce.java)
- [Official size and color roles](https://github.com/androidx/androidx/blob/androidx-main/compose/material3/material3/src/commonMain/kotlin/androidx/compose/material3/tokens/LoadingIndicatorTokens.kt)

The sequence is **Soft burst → Cookie 9 → Pentagon → Pill → Sunny → Cookie 4 →
Oval**, returning to Soft burst. The maintenance exporter compiles the unmodified
Google MaterialShapes source against the same AndroidX graphics-shapes **1.0.1**
version declared by that Material revision. AndroidX `Morph.asCubics(0/1)` supplies
the matched Bézier endpoints for each pair. The browser interpolates these exact
matched curves, without redrawing silhouettes, resampling outlines or substituting
CSS shapes. A small maintenance-only JVM adapter provides Android's affine matrix
operations; no Android/JVM code is shipped as a runtime dependency.

The native animation uses a **650ms** shape interval and an under-damped spring
with **stiffness 200**, **damping ratio 0.6**, and minimum visible change **0.01**.
The JavaScript uses the same analytical SpringForce solution, including overshoot
and native equilibrium thresholds. For interval number `n`, local time `t` in
milliseconds and spring fraction `s(t)`, clockwise rotation is:

`-90° + 140° × n + 50° × t / 650 + 90° × s(t)`.

Morph progress is `n + s(t)`, including the native behavior of entering the next
matched morph during overshoot. Contraction/expansion comes from the official
curves; no extra pulse/scale keyframes or guessed easing are layered on top.
The container remains still. Native frame scheduling and SVG rasterization can
differ from Android; this is a source-based browser port, not a claim of
pixel-identical rendering. Equilibrium is located at 1ms resolution; Android
settles on an animation frame.

## Integration and lifecycle

The floating jump-to-latest button now shows the same uncontained 24px Material
indicator instead of its down arrow while the existing chat Send/activity status
is working. It keeps its 44px target, native button/keyboard behavior, focus
return and jump action. Its accessible name retains Go to latest and adds Klaude
is working. The arrow returns on completion, failure, cancellation or Needs input;
the button retains its existing visibility rules and remains hidden at the bottom.
Repeated snapshots retain the visible indicator, while reaching the bottom,
leaving Chat or signing out removes it. Shared reduced-motion behavior applies.

Validation: `/tmp/klaude-chat-scroll-working-smoke.py` uses an isolated browser,
saved fixture dialogue and actual streamed turn/SSE updates. It passed visibility,
position, 44px targets, reading-position preservation and mouse/touch/keyboard
jumps at 320/390/768/1440px, including a short 390×520 viewport. Working-state
checks cover live SVG motion, reduced motion, stable identity across snapshots,
light/dark mobile/desktop layouts, arrow restoration and stopped/input states,
streaming during a jump, user interruption and sign-out cleanup. The existing
composer smoke also passed immediate Send feedback, activity motion, legacy-host
fallback, failed Send and logout, with zero browser exceptions. Evidence:
`/tmp/klaude-chat-scroll-working-smoke.log`,
`/tmp/klaude-chat-scroll-composer-regression.log`, and
`/tmp/klaude-chat-scroll-working-{light,dark}-{390,1440}.png`. JavaScript syntax,
indicator bundle consistency and whitespace checks passed. The running host
served both updated assets with HTTP 200; only a page reload is needed.

`MaterialLoading.create()` returns one reusable SVG element. Default sizing is
48px with a 38px active shape; 24px and 32px variants preserve that proportion.
Uncontained indicators use `--primary`. Contained indicators use
`--primary-container` and `--on-primary-container`. All existing palettes and
light/dark/system modes retain their current tokens.

- Chat's running activity summary uses a 32px uncontained indicator beside the
  real label, including response preparation and tool activity. Repeated status
  updates retain its element. Needs input, completion, errors and cancellation
  retain static markers and their existing controls. The summary lives inside
  the conversation output below the latest user message and above the reply.
- Send shows an immediate uncontained indicator inside the conversation while its request is
  pending, then hands off to real activity. Older hosts without the activity
  field show a generation indicator until the turn ends or input is required.
  A rejected send keeps the draft and clears the pending status.
- Delayed page/read placeholders show one contained indicator with the real
  loading description and static content skeletons. Tiny count placeholders
  remain static. Existing request ownership, 120ms delay, cancellation, retained
  content and errors are preserved.
- Library/Integrations Refresh keeps its text and loaded content, adding a small
  uncontained indicator after 120ms. Repeated refresh requests are deduplicated;
  completion and sign-out remove the indicator and timer.
- Active Library/Skills operations use a 32px uncontained indicator alongside
  the existing operation kind/state. Unchanged polls retain DOM identity rather
  than restarting the sequence; completed/failed/unknown operations stop.

One `requestAnimationFrame` loop services visible indicators. Intersection and
document visibility suspend hidden animation; disconnected nodes are released
even when reduced motion has stopped the loop. System `prefers-reduced-motion`
and Klaude's reduced-motion setting display a static official shape. No layout,
blur, filter, external fetch or CSS shape animation runs per frame. Decorative
SVGs are hidden from assistive technology; existing status/live text communicates
the actual wait, without adding focusable controls.

## Maintenance, packaging and changed files

Regenerate or check the geometry with a JDK installed:

```sh
python3 scripts/vendor_webui_loading.py
python3 scripts/vendor_webui_loading.py --check
```

The exporter verifies every pinned source/artifact SHA-256, uses a temporary JVM
build, and writes a separate geometry manifest plus Apache license/notice. It
does not install dependencies or modify the existing Markdown vendor manifest.
The shape source is approximately 37 KB. A deterministic maintenance step bundles
the geometry/runtime into the existing external `app.js` asset, preserving the
controller outside its marked block. Index markup needs no newly allowlisted
script URL, so an already-running older host can serve the complete indicator.
All source assets still ship in the wheel and their fixed routes remain available
on new hosts. CSP retains external same-origin scripts, without inline HTML script
or eval. No application API or permission behavior changed.

The geometry exporter also rebuilds/checks this bundle. After runtime-only edits:

```sh
python3 scripts/bundle_webui_loading.py
python3 scripts/bundle_webui_loading.py --check
```

| Files | Purpose |
| --- | --- |
| `apps/webhost/src/klaude_webhost/static/loading-indicator.js` | Shared native-motion SVG component and lifecycle |
| `apps/webhost/src/klaude_webhost/static/vendor/material-loading-shapes.js` | Generated official matched cubic geometry |
| `apps/webhost/src/klaude_webhost/static/vendor/material-loading-{LICENSE.txt,NOTICE.txt,manifest.json}` | License, attribution, source hashes and provenance |
| `apps/webhost/src/klaude_webhost/static/app.js` | Page loaders and real chat activity integration |
| `apps/webhost/src/klaude_webhost/static/library.js` | Refresh/operations and stable polling identity |
| `apps/webhost/src/klaude_webhost/static/style.css` | Sizes, official color roles and compact layouts |
| `apps/webhost/src/klaude_webhost/static/index.html` | Local deferred script ordering |
| `apps/webhost/src/klaude_webhost/host.py` | Fixed static asset routes |
| `scripts/vendor_webui_loading.py`, `scripts/material_loading_export/Export.java`, `scripts/material_loading_export/Matrix.java` | Verified maintenance-only geometry export |
| `scripts/bundle_webui_loading.py` | Deterministic dependency-free app bundle for older hosts |
| `scripts/webui_material_loading_smoke.py` | Browser motion, lifecycle, theme and reference checks |
| `scripts/webui_composer_smoke.py` | Immediate Send, desktop/mobile keyboard, failed-send and legacy-host checks |
| `tests/unit/test_webhost.py`, `scripts/package_smoke.py` | Route/CSP/hash/geometry and installed-asset checks |
| `AGENTS.md`, `docs/webui/coverage.md`, `docs/webui/loading-states-validation.md`, this file | Behavior, source provenance and validation |

No runtime dependencies, lockfile changes, commit or push. Unrelated dirty work
was preserved. Reload the browser to load the bundled indicator; a host restart
is no longer required for this component.

## Validation

- Verified byte-identical regeneration from the pinned official inputs using
  `vendor_webui_loading.py --cache /tmp/klaude-official-loading --check`.
- **40 passed** in `tests/unit/test_webhost.py`, including local asset routing,
  CSP/no-sniff, source hashes, seven-shape order and closed matched cubic paths.
- `webui_material_loading_smoke.py`: eight light/dark layouts at
  **360/390/768/1280px**, native cadence/rotation/overshoot assertions,
  moving paths, stable activity identity, stopped input/done/error/cancel states,
  contained page loader, both reduced-motion settings, hidden-content suspension,
  removal cleanup and 100 transient indicator removals. Also checks unchanged
  operation-poll identity/completion and deduplicated Refresh with retained content.
  Zero browser exceptions, external resource requests or recorded >50ms tasks in
  the isolated indicator run. This is not a low-end-device performance benchmark.
- `webui_loading_smoke.py`: all **19** existing lifecycle/layout/retained-data,
  stale-response, preview-cancellation and sign-out checks passed, including
  narrow widths from 320px.
- `webui_activity_smoke.py`: all **13** labels at desktop/phone widths plus real
  approvals, questions, completion, failure, cancellation, reload, SSE reconnect
  and reduced motion passed.
- `webui_markdown_smoke.py`: all **24** existing checks passed, including real
  shared-worker streaming, stable code blocks/selection/scroll through snapshots,
  clipboard and message actions, theme layouts and sign-out cleanup.
- Repository Ruff, production mypy (**212 files**), changed JavaScript syntax
  checks and `git diff --check` passed.
- All **seven workspace wheels** built/installed, packaged indicator assets and
  notices were present, all imports and both installed CLI help checks passed.

Screenshots and machine-readable results: `/tmp/klaude-material-loading/`.
Visually inspected the seven-shape strip, desktop page loading, mobile chat
status and captured frames from Google's official overview video. The existing
loading suite also produced `/tmp/klaude-loading-preview/` captures.

The full repository unit suite, physical iOS/Android, Safari, screen-reader and
low-end-hardware testing were not performed. Google-native/browser frame timing
is not asserted to be pixel-identical.

## Send and desktop keyboard follow-up — 2026-10-21

The running local host was directly checked: `/app.js` returned 200, while
`/loading-indicator.js` and `/vendor/material-loading-shapes.js` returned 401.
Its older in-memory static allowlist could not serve the new scripts, despite
reading the updated app and markup from disk. The bundled delivery above fixes
that failure without interrupting the host. Public `/app.js` and `/` responses
were then verified byte-identical to the updated workspace files. No private
session data or credentials were accessed for this check.

The Send handler now displays status synchronously before its first network wait.
Draft text is retained on error. Status switches to actual typed activity on new
hosts and a generation fallback on old hosts; it clears on idle, logout or a
session change. Only real pending work uses the indicator.

Desktop Enter submits through the same form/Send path. Shift+Enter remains native
multiline input. Composition confirmation, modifier keys, repeats, duplicate
pending sends and attachment-preparation restrictions do not submit accidentally.
Touch-only software keyboards retain native Enter/newline behavior. An accessible
hint describes the current behavior.

Validation for this follow-up:

- `webui_composer_smoke.py` passed with an isolated authenticated turn worker and
  held fixture runtime. Native CDP key events verified desktop Enter, exact
  Shift+Enter line breaks, IME/repeat guards, mobile multiline Enter and the Send
  button. Delayed Send feedback was visible at 390/1280px in light/dark themes;
  duplicate sends were blocked. A legacy fixture blocked the two script URLs and
  removed typed activity from real snapshot reads; the bundled indicator remained
  available. Failed sends kept their draft, and logout cleared pending status
  before a deliberately late response. Zero browser exceptions.
- Existing Material motion/lifecycle, loading (19 checks) and real activity
  (13 labels plus review/cancel/reconnect) browser suites passed again.
- The asset/CSP/geometry unit test passed, including new assertions that `app.js`
  contains the exact geometry/runtime sources and markup has no new script URLs.
- Ruff, JavaScript syntax, deterministic bundle/source checks and
  `git diff --check` passed. Seven-wheel packaging/import/CLI checks passed.

Captures and results: `/tmp/klaude-composer-preview/`. Physical-device keyboards,
Safari and full accessibility acceptance were not tested.


## Conversation placement and verified motion — 2026-10-21

Reviewed Claude's official [response-processing presentation](https://support.claude.com/en/articles/8664678-change-the-model-effort-and-thinking-settings),
which places the expandable processing section above the response. Klaude now
places pending Send feedback and existing execution details inside the scrollable
conversation, below the user's message and above the assistant reply. The composer
has no status row. These are presentation nodes, not saved messages; snapshots
retain them without modifying streamed articles or exported conversation content.
Completed details remain with the latest response, and sign-out/password changes
park and clear the feedback before clearing private messages.

Rechecked the downloaded official Android animator/drawing source and verified
all pinned source hashes plus exact regenerated AndroidX matched curves. The
existing official spring/rotation algorithm was retained. Chat uses a clearer
32px uncontained indicator. Real authenticated Send tests now assert both changing
SVG curves and rotation during request admission and active response generation,
as well as a single activity indicator below the user message and stable SVG
identity through snapshots. No synthetic CSS pulse or substitute shape was added.
App/system reduced motion deliberately retains a static official shape.

Current verification:

- Composer fixture: native desktop/mobile keys, inline Sending feedback in four
  light/dark layouts, real response morph/rotation, snapshot identity, legacy-host
  fallback, duplicate-send protection, failed-send draft retention and late logout
  cleanup passed with zero browser exceptions.
- Activity fixture: all 13 labels plus real reviews, questions, cancellation,
  completion, failure, reload, reconnection and reduced motion passed.
- Material fixture: eight layouts at 360/390/768/1280px, official sequence and
  physics, app/system reduced motion, hidden/removal cleanup, page loaders,
  operation identity and retained/deduplicated refresh passed.
- Markdown fixture: 24 checks passed, including real worker streaming, stable
  selection/code scrolling through completion and snapshots, reader scroll,
  message actions, theme layouts and private sign-out cleanup.
- Focused asset/CSP/geometry unit test: 1 passed, 39 deselected.
- Loading fixture: all 19 loading/layout/retained-data and late sign-out checks
  passed. Focused Ruff, JavaScript syntax, deterministic bundle/source checks
  and `git diff --check` passed.

Inspected settled desktop/mobile captures and recorded real response motion in
`/tmp/klaude-composer-preview/response-motion-mobile.gif`. The running host's
public app.js, style.css and index responses were checked byte-identical to the
workspace, with no-store headers. Reload loads this change without restarting
or accessing the live session. Full unit-suite and physical iOS/Android/Safari
verification were not performed for this follow-up.
