# Startup theme and authentication loading screen

Refresh now restores the saved theme before the first styled paint and shows
Klaude's existing paw/wordmark with the shared 48px Material loading indicator.
The custom SVG wave/progress sweep and its CSS animations are removed.
The shell stays hidden, inert and excluded from accessibility navigation until
authentication and the existing initial session, navigation, conversations and
model reads complete. The initial HTML also hides/inerts the chat layout.
Unauthenticated or failed initialization reveals the existing sign-in/error
panel; it never uncovers the chat shell as a loading placeholder.

The cover fades out over 160ms with no minimum display delay. Both the saved
Reduced motion setting and the system preference stop indicator motion and skip
the fade. Completed startup removes its indicator and clears its recovery timer. A
missing app script or a startup longer than 15 seconds offers Reload; it does
not bypass authentication or claim completion. Shared conversation/message
links retain their focus and scroll behavior after the shell is revealed.

## Implementation

- `static/loading-indicator.js` is an existing public asset, now also loaded
  synchronously before CSS. It shares the same versioned appearance validator
  with `app.js`, avoiding duplicated palette/default definitions and retaining
  blocked/corrupt-storage fallbacks. The bundler also includes the existing pinned
  geometry in this asset, so the same renderer starts before the app downloads.
  It initializes only once and mounts when parsing supplies the splash slot,
  without waiting for deferred scripts or DOMContentLoaded. Its cleanup observer
  watches the document root, which is available during head execution. No new
  request, HTTP route, dependency or inline script is needed.
- `static/index.html` supplies the static startup screen, an indeterminate
  progressbar slot linked to the real status, and the hidden/inert shell.
- `static/style.css` reserves a centered 48px slot with current theme roles.
- `static/app.js` ends startup only after confirmed initialization or the existing
  sign-in fallback, and defers shared-message focus until the shell is usable.
  Its existing bundle retains the early renderer and indicator rather than
  creating another scheduler or resetting the visible animation.
- `scripts/webui_startup_smoke.py` delays real fixture asset/auth/session reads
  and exercises both signed-in and signed-out refreshes.

The splash now calls `MaterialLoading.create({size: "large"})`, reusing the
existing Apache-licensed matched Google geometry and end-4 motion adaptation:
seven smoothly morphed shapes, 800ms cadence, 12s continuous rotation,
90-degree/350ms leaps and 750ms zoom. The saved classic spinner is respected;
reduced motion displays a static shape/spinner. There is no simulated percentage.
Source, licensing and motion details remain in `klaude-expressive-reference.md`.

Authentication, owner checks, CSP (including no inline script/style), backend
APIs and appearance storage semantics remain unchanged. The reused public asset
is served by current hosts, so these changes require a page refresh, without a
host restart or session revocation. All unrelated dirty changes were preserved;
no commit or push.

## Validation

The focused startup browser check uses temporary accounts/profiles and no model
inference. It verifies saved dark/light/system modes across 320/390/768/1440px,
slow app downloads and authentication, no exposed shell during startup, keyboard
isolation, indeterminate semantics, live rotation and morphing while app.js is
held, saved/system reduced motion, the saved classic spinner, the same renderer
and indicator across app handoff, removal on completion,
authenticated refresh while the initial snapshot is delayed, saved chat and
shared-message focus, logout/reload, corrupt/blocked browser storage, connection
failure, blocked app assets and Reload recovery. Screenshots are written to
`/tmp/klaude-startup-preview/`.

Validated on 2026-10-22 after replacing the wave:

- `scripts/webui_startup_smoke.py` passed all five appearance/viewport cases,
  signed-in/out refresh, delayed responses, shared-message focus, storage failures
  and blocked-app recovery. Zero browser exceptions. Desktop dark and phone light
  captures were visually inspected.
- `scripts/webui_material_loading_smoke.py` passed eight responsive chat layouts,
  exact shape order, end-4 choreography, app/system reduced motion, hidden/removed
  cleanup, page/operation ownership, stable refresh content and deduplication.
  Zero browser exceptions, external requests or recorded animation long tasks.
  Evidence: `/tmp/klaude-material-loading/`.
- The focused host asset/CSP test passed (`1 passed, 39 deselected`), including
  local asset hashes, unchanged script policy and legacy bundle availability.
- Changed JavaScript syntax, focused Ruff, both bundle checks and
  `git diff --check` passed.

These are focused Chromium checks, not full-suite, live-model, physical-device
or other-browser coverage. No backend implementation or live-host restart was
part of this work. Reload is sufficient for the existing static asset routes.
