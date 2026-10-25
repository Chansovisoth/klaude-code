# Reference lockscreen / login — 2026-10-22

## Reference and implementation

Reference checkout: `/tmp/klaude-end4-reference`, commit
`2f2a376fdb2ad738bf55f693dd0b474b64bb0ab8`. Screenshot and supplied wallpaper:
`docs/webui/lockscreen/`. The wallpaper is copied byte-for-byte into the WebUI
static package as `lockscreen-bg.jpg`, served from a fixed public image route.
Client code never contains host filesystem paths. Its existing heavy blur is
preserved with centered cover framing and a small tint from the active theme.

The root end-4 license is GPL-3.0; Klaude remains MIT. No GPL QML or wallpaper
asset from that repository was copied. The layout/state parameters below inform
an independent native HTML/CSS/SVG implementation. The user supplied the image;
no separate creator attribution was supplied with it.

| Inspected end-4 source (relative to `dots/.config/quickshell/ii`) | Extracted behavior | Klaude equivalent |
| --- | --- | --- |
| `modules/ii/background/widgets/clock/{ClockWidget,CookieClock}.qml` and `modules/common/Config.qml` | 230px clock; default 14 lobes, full dial, filled hour/medium minute hands; whole clock/quote/status column centered with 10px gaps | Reusable `KlaudeLockScreen` renderer and `.lock-center`; static cookie, live local time |
| Clock `{HourHand,MinuteHand,SecondHand,HourMarks,TimeColumn}.qml`, `minuteMarks/{MinuteMarks,Lines}.qml` | 72×20 hour hand, 95×12 medium minute hand, 300ms clockwise transitions; 18×4 hour and 7×2 minute marks; 68px expressive numerals | SVG marks and rounded hands, unwrapped rotation, Space Grotesk text; minute precision matching the screenshot/default |
| `dateIndicator/{DateIndicator,BubbleDate}.qml` | 64px bubbles at top-left/bottom-right, Pentagon day and Pill month, 30px black expressive text | Existing Material vector helper with generated Pentagon/Pill, local date/month |
| `CookieQuote.qml` and clock status row | Quote, 8px horizontal/4px vertical padding, 4px icon gap, 12px rounding; 2px/12px shadow | Quote icon and tonal secondary container with locked/session status; offline curated rotation with attribution per the subsequent user request |
| `modules/ii/lock/{Lock,LockSurface,PasswordChars}.qml`, `modules/common/panels/lock/{LockScreen,LockContext}.qml` | Bottom margin 20px, 10px island gaps, scale .9→1/opacity entrance, focused native password control and wrong-password shake; clear on failure | Three floating desktop islands and responsive mobile form using actual account login; no PAM/system controls |
| `modules/common/widgets/{Toolbar,ToolbarTextField,ErrorShakeAnimation}.qml` | 56px toolbar, 8px padding, 4px internal gap, 40px inner field/button; 200–500ms motion and 210ms error feedback | Scoped `.lock-island`, retained native input/form, transform-only error shake |
| `modules/common/widgets/{MaterialCookie,SineCookie,MaterialShape}.qml`, `shapes/material-shapes.js` and its Apache license | Rounded 14-point star, radii 1/.8, rounding 1.5/14, 30° rotation; canonical named password shapes | Apache Google/AndroidX export, never a copied GPL geometry algorithm; no constantly rotating clock |
| `modules/common/Appearance.qml` | Material tonal roles, 12px small rounding, 17px large text, 22px icons, expressive spatial/effects curves | Shared generated Material roles from Theme Settings and existing Klaude motion/corner tokens |

`static/lockscreen.js` is bundled into the existing `/app.js` route. Its shared
SVG helper uses an additive `MaterialLoadingGeometry.lockShapes` export, leaving
the existing nine general shapes and seven loading morphs unchanged. The clock
and exact password shapes come from the pinned Apache-2.0 Google Material /
AndroidX export already maintained by `scripts/vendor_webui_loading.py`:
Clover4Leaf → Arrow → Pill → SoftBurst → Diamond → ClamShell → Pentagon, repeating.
Each slot is 20px; shape size 18px; opacity 50ms, scale 200ms, color 1000ms.

Reference fonts are served locally: **Space Grotesk** for expressive clock/date
type and **Readex Pro** for reading text. Both are unmodified fonts from the
official [Space Grotesk](https://github.com/google/fonts/tree/main/ofl/spacegrotesk)
and [Readex Pro](https://github.com/google/fonts/tree/main/ofl/readexpro) Google
Fonts directories. Complete SIL OFL notices and source URL/SHA-256 records ship
under `static/fonts/`. Existing Apache Material notices/manifests remain beside
the generated geometry. No new runtime library or external browser request.

## Authentication and input behavior

- The native password input and existing login form/IDs remain authoritative.
  Only the real account endpoint and subsequent authenticated initialization can
  unlock the application. Cookie, Origin/CSRF, login limiter, session and client
  control contracts remain unchanged. The only host additions are fixed public
  wallpaper/font asset routes, checked after the existing host/source guards.
- The account username remains editable with native `autocomplete="username"`
  and form association. Password retains `type="password"`, required/maxlength,
  `autocomplete="current-password"`, native editing, selection and IME behavior.
  The decorative layer is `aria-hidden` and stores only length/selection offsets,
  never password text. It renders no text characters. Autofill without an input
  event is detected on the existing visible screen's bounded 1Hz check.
- Native text/bullets are hidden only after all vector shapes are available.
  Missing geometry keeps native password masking; forced colors explicitly
  restores native text/selection/caret and hides decorative rendering.
- Input/selection updates retain slots by position; only changed slots render.
  Native scrolling moves shapes/caret together. No credential logging or extra
  storage is introduced. Every completed/rejected/failed/timed-out submission
  clears the password and mask. Pending requests lock editing and deduplicate
  submission; a 15s request timeout allows explicit retry without auto-resubmission.
- The protected shell is hidden, inert and excluded from accessibility navigation
  while unauthenticated. Open app dialogs/popovers close on expiry. The lockscreen
  sits outside that shell; asynchronous splash completion preserves its isolation.
  Actual expiry displays **Session expired**; intentional logout displays
  **Signed out**. Bootstrap-only hosts retain their existing browser-link flow.

## Responsive behavior and web differences

Desktop reproduces the reference column, 56px islands and center-anchored 260px
password island, with neighboring 164/220px islands and 10px gaps, 20px above the
bottom. Phones put the full-width password island on the bottom row below
secondary controls and retain date bubbles and the existing compact clock sizes.
Through 768px, a two-row native grid gives `.lock-main` exactly the space left by
the natural-height `.lock-bottom`; the complete clock/quote/status group is
centered inside that region with no positional offset. The wrappers use
`display: contents` on desktop to preserve its positioning. Mobile error/Caps Lock
notices occupy real footer space, with long feedback scrolling internally inside
a bounded region. Safe areas and existing `visualViewport` height/offset keep the
form above the keyboard.

The quote uses normal wrapping and a content-sized tonal container. Its clock
group permits up to 440px of line space within 12px viewport margins; a single
layout measurement trims spare width from multiline quotes after selection, font
load or viewport-width changes while retaining their line count. The quote icon
stays aligned with the first line and visible attribution remains below the text.
Container-height fallbacks hide the clock, then quote,
then status only as space becomes constrained; keyboard mode hides the utility
island while retaining both credential fields in separate rows. Username stays
visible/focused through both visual-viewport and layout-viewport resizing. The
previous account-island hiding rule was reproduced dismissing focus, then fixed.
The footer bounds/shrinks long notices before either login field, while the main
region may collapse completely on very short keyboards. The visible English
Proverb label is removed, retaining accessible cite
metadata, source tooltip, JSON provenance and notices.

The username regression failed before the fix and passed afterward: native typing
continues after the visual viewport shrinks, a 360px layout viewport keeps focus,
and switching between username/password keeps both controls visible. All eleven
layout cases, 210px keyboard/error bounds, wide keyboard notice placement and
the existing real-login flow pass. A fresh unauthenticated browser also verified
the current stylesheet and username editing on the running host, without sending
credentials. Physical software keyboards remain outside the automated fixture.

The right island has the actual clock timezone, sign-in help and functional page
reload. Browser locale is not represented as a keyboard layout. Battery, sleep,
shutdown, reboot, fingerprint, PAM, global keyboard capture and Hyprland behavior
are deliberately absent. The username is the actual login field rather than the
Linux system username. Per the subsequent theme request, colors use the same
generated roles as the rest of Klaude instead of the reference's fixed warm
scheme. The original warm brown/beige family is available throughout the app
through Theme → Cocoa with the Tonal spot variant; see
`theme-palettes-validation.md`. Large decorative
clock numerals preserve the reference's muted hierarchy; a complete accessible
local date/time label is available independently of the analog face.

## Theme integration

The lockscreen inherits the existing appearance bootstrap and controller without
an independent palette or theme preference. Light, dark and system mode, all
presets/Material variants, and saved custom/image-derived accent seeds apply
before sign-in, after session expiry, and on reload. Live theme previews and
system-mode changes update CSS roles without rebuilding the clock or inputs.

| Surface | Material roles |
| --- | --- |
| Clock face, numerals and hands | Primary container and on-primary-container; numerals/minute hand use 80%/90% tonal blends to retain hierarchy |
| Day and month bubbles | Tertiary and secondary container pairs |
| Quote and Locked status | Opaque secondary container/on-secondary-container |
| Floating toolbar | Surface container with on-surface/on-surface-variant; theme transparency limited to 90% minimum opacity |
| Password field, mask and caret | Surface container highest, on-surface and primary |
| Submit | Primary/on-primary |
| Error feedback | Error container/on-error-container |
| Caps Lock, help and connection fallback | Tertiary container pair and surface container levels |
| Wallpaper tint and shadows | Surface and shadow roles; original image unchanged |

Quote/status containers remain opaque because translucent Fidelity containers
can fall below readable contrast over bright wallpaper. This follows the
generated role pairs instead of introducing special colors for each palette.
No new storage, API, asset route, dependency, or authentication behavior.

The isolated browser passed 648 cases: 16 presets plus custom and image accent
seeds, nine Material variants, both light/dark modes and both transparency
extremes. Measurements use actual computed paints over worst-case black/white
wallpaper pixels: minimum normal-text contrast 4.513:1, large clock text/hands
3.472:1, with no invalid/nonfinite measurements. The real Theme Settings Apply
flow, system light/dark changes, expiry and login reload preserve the selected
scheme. Quote rotation, geometry, native username focus and password animation
checks continue to pass. Light/dark phone and desktop captures are under
`/tmp/klaude-lockscreen-validation/theme-*.png`.

Clock values derive from local wall time and Intl/browser timezone, with a 1Hz
visible-screen check and DOM updates only when the minute/date changes. Hidden
tabs and unlocked screens stop timers. Focus/pageshow/visibility changes resync;
the next tick detects wall-clock/timezone changes. There is no permanently
rotating cookie or high-frequency clock rendering. App/system reduced motion
also disables entrance, hand, password and unlock transitions and error shake.

## Validation record

The isolated browser uses temporary accounts/profiles and fixture credentials,
with real account HTTP, protected-route rejection and cookie expiry. Reference
captures freeze browser time only, not production time. Output:
`/tmp/klaude-lockscreen-validation/`; desktop and phone screenshots are compared
against the supplied screenshot, including real toolbar heights and spacing.

Account/host regressions: **48 passed in 42.96s**, covering password verification,
rate limiting, cookie/session revocation, CSRF/Origin policy and static assets.
The first browser pass found splash completion clearing the locked shell's inert
state; that timing issue is fixed. Early test failures also exposed native input
focus missing from the script's synthetic click helper and native Enter needing
its character event; these fixture calls now use actual focused editing.

The startup smoke still expected the older `.material-loading` widget, whereas
the pre-task code uses `.md3-linear-progress`. Its selectors/assertions now follow
that existing widget, verify the renderer is retained across app loading, and
ensure visual progress completion never reveals the unauthenticated shell.
That separate production splash animation is preserved.

The updated lockscreen browser run passed all **eleven** viewport cases:
320×740, 390×844, 390×650, 390×568, 320×480, 390×360, 768×1024, 768×600,
1440×900, 1920×1080 and short 844×390. Mobile group midpoint error was 0px in
all measured main regions, with no overlap or page scrolling. Nonzero safe-area
padding, growing notices, the bootstrap-only presentation and 340px/210px visual
viewports (including a 48px pan offset) were exercised. It also verified
the exact seven-shape order, native insertion/selection/replacement, real rejected
and accepted login, silent autofill detection, Enter submission, bounded caret
scrolling, duplicate submission suppression, pending/read-only states, a real 15s
client timeout, explicit retry, cookie-expiry relocking, midnight/month rollover,
timezone conversion and live-time reload. Simulated visualViewport keyboard
clearance, native-mask fallback, forced colors and reduced motion passed. Zero
browser exceptions. The wallpaper/clock/date/quote/island proportions and final
desktop/phone captures were visually compared with the supplied reference.
The quote follow-up measured rendered text and container bounds at 320, 390, 768
and 1440px for 34, 37 and 79-character samples, plus a visible author. The
37-character sample stayed on one line from 390px upward; quote and icon remained
centered and inside the viewport at all four widths. The same isolated browser
run passed the login, theme, keyboard and session-expiry checks above.

The existing startup regression passed its five appearance/viewport cases,
delayed app/auth/session reads, saved-session refresh and shared-message focus,
keyboard isolation, sign-out/reload, corrupt/blocked storage, connection failure
and missing-app recovery. The existing Material loading regression also passed
its **eight** responsive chat layouts, exact shape order/choreography,
app/system reduced motion, hidden/removed cleanup, page/operation ownership,
refresh-content retention and deduplication: no browser exceptions, external
requests or recorded animation long tasks. The existing splash implementation
was not replaced as part of this login work.

Offline `klaude-webhost` wheel build passed; its seven new component/image/font/
license/manifest assets were compared byte-for-byte with the source package.
Font SHA-256 records and the exact supplied wallpaper bytes match. Focused Ruff,
changed JavaScript syntax, cached-source geometry regeneration checks, both
deterministic bundle checks and `git diff --check` pass.

Web adaptations include browser/native-font rasterization and CSS shadow kernels
instead of Qt's sampled shadows, fixed slot geometry with SVG scale entrance
instead of QML implicit-size layout animation, a 300ms CSS deceleration curve
instead of Qt's compound emphasized hand curve, and a 200ms opacity/scale exit that
never authorizes access itself. Keyboard checks use a simulated visualViewport,
not a physical device keyboard. Full repository suite, physical devices, Safari/
Firefox, real password-manager extensions and screen-reader acceptance were not
run; native autocomplete/fallback/ARIA behavior is preserved but those platform
checks remain outside this scoped validation.

New static asset routes require restarting an already-running older WebUI host.
The initial implementation and layout checks used isolated fresh hosts; they
did not verify the user's already-running Python process. When the missing
wallpaper was reported, the live host returned 401 for `/lockscreen-bg.jpg` and
the new fonts while serving the current CSS. Its process predated these routes.
The idle host was gracefully restarted with its exact session, workspace,
environment and LAN settings. Before/after checks confirmed unchanged history,
model runtime, account revision and settings. Browser cookies require signing in
again after the restart. Wallpaper/font HTTP responses and actual image decoding
are now checked before authentication, beyond merely checking the CSS family.
Live verification returned 200 with exact packaged bytes for the wallpaper and
both new fonts on loopback and the existing LAN listener. A fresh unauthenticated
Chromium profile decoded the 1919×1079 wallpaper, loaded both font faces and
rendered the background on phone/desktop with no browser exceptions. Captures
and report: `/tmp/klaude-lockscreen-live/`. No message or model action was run.
Unrelated work and the supplied source assets are preserved. No commit or push.
