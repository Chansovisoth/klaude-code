# Model Store V2 editorial layout

Date: 2026-10-25. Implements the updated
[handoff](klaude-model-store-image-studio-codex-handoff%20v2.md) and
[layout reference](klaude-model-store-layout-reference.html). This slice changes
frontend layout and navigation, retaining the existing model/settings APIs,
workers, reviews, journal and admin-role policy.

## Result

Model Store has exactly three equal-width tabs: Discover, Installed and Downloads.
They use tab/tabpanel semantics, roving focus, arrows/Home/End and the existing
selection styling. The header contains Model Store and Refresh. Current chat and
Model Defaults are removed from this header; their existing owners remain.

Discover renders Search plus Filters, then Featured immediately. Original layered
SVG subjects from the supplied reference provide a coding workspace, reasoning
sculpture and vision lens. They are embedded locally as three HTML templates,
cloned only into the three editorial covers. There is no asset CDN, image hotlink,
runtime image generation, publisher artwork substitution or dependency. Their
provenance is the original SVG illustration source in the supplied reference;
no additional third-party artwork was introduced. Theme-aware chrome surrounds
vivid media colors, text scrims and white CTAs. The cover background remains
readable if artwork is hidden; forced colors hides decorative art and restores
system text/surface roles. On phones/tablets the next cover peeks into a horizontal
snap carousel. Desktop uses an asymmetric three-cover grid.

Compact Popular rows show verified Hub repository download counts, a rank, local
model identity icon, readable name and View/Installed pill. These counts describe
Hub repositories, never Ollama usage. The landing makes one fixed anonymous
public-catalog query; user search text is sent only after explicitly selecting
the Hugging Face catalog. Cached/stale/unavailable metadata is identified;
rankings are not fabricated. See all opens a Discover charts drill-down. Illustrated
category tiles open curated use-case results. Curated rows retain the dated offline
collection and exact verified variants. No capabilities or hardware-fit claims
are inferred from art, names or quantization filenames.

Native Filters owns source, order, capability, installed-size choices and the
secondary Download exact tag action. Choices retain URL state and have contextual
enabled/disabled states; unknown Hub capabilities are not filtered as known.
Escape/Done restores focus to Filters. The direct-tag dialog retains its exact
native destination and existing review; it offers an endpoint choice only when
multiple enabled native connections exist. Detail has the same contextual choice.

Installed uses compact icon/name/metadata/Manage rows, an optional multiple-endpoint
selector and the existing numbered pager/chevrons. Pager nodes remain mounted and
visible through same-view renders so the selected numbered button keeps focus.
Empty Downloads centers its status/icon/text and Discover models action in the
remaining page area; Search, Filters, endpoint and direct-tag controls are absent.
Existing populated jobs retain actual progress, cancellation, recovery and history.

Connection management stays in Settings → Models. The configured local/cloud
catalog moves there into Browse configured models, preserving exact current-chat
activation, search, pagination, revision checks and legacy-host behavior. Its
native disclosure choice uses the existing tab-local navigation storage and
clears on sign-out. Container sizing stacks the connection/catalog columns at
narrow widths. The shared pager's inherited −8px outer margins are reset in this
Settings container; its buttons and spacing are unchanged. The command palette's
Switch model opens Chat's own picker. Old Store Connections URLs migrate to
Settings without creating a Back-navigation loop; chart/category URLs remain
Discover drill-downs.

A browser check also exposed a credential draft cleanup race. The field now clears
synchronously before opening its review, in addition to the existing dialog-close
and sign-out clearing. The private prepared request and write-only API are unchanged.

## Files and validation

Production changes: static `index.html`, `media.js`, `app.js`, `expressive.css` and
generated `style.css`. No production Python, HTTP route, journal schema or model
worker changed. Tests adapt `webui_model_store_smoke.py`,
`webui_model_settings_smoke.py` and `webui_models_smoke.py` to the new owners.

The Store/Studio walkthrough passes with a password-admin session under LAN policy:

- Exactly three equal-width, unclipped 48px tabs; Search/Filters followed by three
  real illustrated covers; no Current chat/Model Defaults or single-endpoint
  toolbar in the Store header. First cover appears in the first phone viewport.
- Light/dark at **320/360/390/430/768/1440px**, with screenshots inspected at phone
  and desktop sizes. Keyboard End selects Downloads; Filters Escape returns focus.
- Centered Downloads empty geometry, compact category filtering, capability filter
  state, real-count charts/exact GGUF detail, detail Back/focus restoration,
  direct-tag review/cancel, reviewed native pull and receipt reload.
- Eight-page native inventory with direct selection, boundary actions and numbered
  focus preservation; search resets paging; cached offline inventory remains usable.
- Reduced-motion/forced-color presentation, existing Studio parameters/drafts,
  fixture PNG generation/output preview, Generate again and sign-out cleanup.

The admin-settings walkthrough passes role selection/Apply, independent service
Test, connection creation, credential privacy, enable/Test, multiple-endpoint
visibility in Store/detail/inventory, removal and logout. It checks
320/390/768/1440px light/dark layouts. The configured-catalog walkthrough passes
configured/legacy discovery, activation/dedup/effort, failure/refresh, disabled and
empty connections, busy controls, Settings history/reload, keyboard More navigation
and late-read sign-out cleanup at 320/390/768/1024/1440px in light/dark.
All three report zero JavaScript exceptions.

Screenshots: `/tmp/klaude-model-store-evidence/`,
`/tmp/klaude-model-settings-evidence/` and the configured-catalog harness's existing
output directory. JavaScript syntax, focused Store/settings smoke Ruff,
Expressive bundle verification and `git diff --check` pass. The configured-model
smoke retains preexisting long-line lint findings; this is not a full-repository
lint or test-suite pass. Backend validation from the preceding slice remains
recorded separately (204 model/settings tests, 107 admin/auth/model tests and
229 production files passing mypy). Those broad suites were not rerun for this
frontend-only change.

Chrome uses isolated fixtures for pull/generation/settings effects. Real weight
transfers, image inference, physical phones and real mobile browser chrome were
not exercised; emulated viewports are not physical-device coverage. Existing
unsupported image adapters/hardware-fit estimates remain unavailable. Dirty work
was preserved, and nothing was committed or pushed for this slice.

## Live UI check

The final authenticated Chrome check against `http://127.0.0.1:50000` passed at
320/390/1440px with zero JavaScript errors. The managed instance at verification
was `3352385:70856194`. It rendered all three illustrated features and three tabs,
the first 20 installed rows and the existing one-row download history. The saved
session/model/mode/effort were unchanged, and the final temporary verification
client signed out. No production settings, model weights or generation jobs were
changed. Evidence: `/tmp/klaude-store-v2-live-result.json` and
`/tmp/klaude-store-v2-live-evidence/`.

The running host serves these static assets directly; no backend restart was
needed for this slice. Reloading the page loads the new UI.

The subsequent [model-details handoff implementation](model_details/implementation-validation.md)
replaces the earlier detail modal with the requested Flathub-composed full page.
Discover, Installed, Downloads and the shared backend contracts remain intact.

## Shared navigation tab styling correction

Model Store's tablist now uses the existing `section-chips` class, enrolling its
dynamically created tabs in `setupSegments()` without a second styling engine.
The isolated fixed pill radii, idle/selected colors and gap overrides were removed.
The shared primary selected state, tonal idle state, measured half-height selected
pill and positional outer/interior corners now match the other application tabs.
The Store retains three equal columns, 48px targets and its existing tab/tabpanel,
roving focus, arrow/Home/End and URL navigation behavior.

The complete Model Store/Image Studio Chrome walkthrough passes at 320, 360, 390,
430, 768 and 1440px in light/dark themes. It measures shared colors, edge markers
and actual corner radii, covering first/middle/last selected tabs. Console errors:
zero. Result: `/tmp/klaude-store-shared-tabs-browser.log`.

A separate authenticated read-only check confirms all three tab selections on
the running host at 320/390/1440px, with no console errors, model mutations,
session/model/mode changes or host restart. Evidence:
`/tmp/klaude-store-tabs-live-result.json` and
`/tmp/klaude-store-tabs-live-evidence/`. Reload suffices for this static change.
Both static bundle consistency checks, focused Ruff and `git diff --check` pass.

2026-10-26 control consistency: Model Store Search now uses the same domain-toolbar
field styling as Library/Integrations, with a 48px field/action, 4px action gap,
and matching filter-row padding. Focused isolated Chromium comparisons at 320px,
390px and 1440px verified identical Library/Store search computed styles and chip
geometry, viewport fit, and no browser errors. This does not replace full Store
workflow validation.

The Model Store title is a keyboard-accessible Discover link. Focused Chromium
checks at 390px/1440px verified return from Popular (Charts) and Recently updated
See all URL states, with drill-down/sort/page reset and scroll returned to top.

2026-10-26 community search: ordinary Hugging Face searches now expose the shared
cursor-backed pager, alongside Popular/Recently updated paging. Search input
immediately cancels superseded reads and clears the previous query's results.
Community/offline/installed placeholders identify the active catalog; network
errors are not reported as zero matches. Live owner-browser verification returned
20 public GGUF repositories for qwen, 20 distinct second-page entries, and 20
results for a fresh gemma query at page one. No browser errors, host restart,
model activation or weight requests. The host runtime/session was preserved.
Six focused catalog/Hugging Face unit tests passed. This is not full-suite or
physical-device validation.

2026-10-26 Installed/card metadata: Installed rows now use shared collection-card
backgrounds/corners and compact model names (full names remain in tooltips and
Details). Existing Manage actions and pagination retain their original paths.
Discover cards show Updated alongside download counts, and Details includes
the same date. Invalid/missing timestamps remain Unknown. The catalog explicitly
requests Hugging Face's lastModified field; metadata version 2 refreshes older
cached records without discarding their offline fallback. Source reference:
https://huggingface.co/docs/huggingface_hub/package_reference/cli

Seven focused catalog/Hugging Face tests passed, including cache upgrades and
offline fallback. Scoped Ruff, JavaScript syntax and diff whitespace checks pass.
Live Chromium checks passed at 320px/390px/1440px for Installed card backgrounds,
rounded corners and no horizontal overflow, plus Updated beside downloads
and in Details. No browser errors. The metadata change was activated after an
idle preflight; the original conversation was explicitly restored afterward,
including Mistral, Standard, Plan and revision 6. Workspace, LAN and account mode
remain unchanged. No weights were downloaded or generated. These are focused
checks, not a full repository suite.

### Downloads cards — 2026-10-26

Downloads now reuse `collection-row library-card` for the shared tonal background,
row spacing and positional corner shapes, with 12px content padding. Their grid
rule explicitly overrides the shared Library row's zero-padding/flex defaults.
A focused isolated browser check passed at 1440/390/320px: completed, running and
unknown cards have no overflow, retain Stop/Remove/Check/Info controls, and retain
the existing progress node across refresh. No model operation was submitted and
no browser exceptions were recorded. CSS bundle, JS syntax and diff checks passed.

### Downloads metadata and transfer speed — 2026-10-26

Cards and their Info dialog show exact catalog/installed parameter count and size.
Missing values remain unknown. If the only available size is the active layer's
reported total, it is labeled File. MB/s is decimal bytes/1,000,000 per second,
estimated from successive monotonic browser samples of reported byte progress.
The first sample, counter decreases, stage/total changes and gaps over 15 seconds
reset the estimate; inactive or removed jobs discard samples. Sign-out and leaving
Model Store clear the sampling state. No model name is parsed for metadata, no
weights are fetched, and observed transfers without byte counters have no rate.

The isolated `/tmp/klaude_download_metadata_check.py` passed at 1440/390/320px:
known 4.02B/2.5 GB metadata, explicit unknowns, positive MB/s from simulated byte
updates, counter-reset handling, preserved actions/progress-node identity, no
overflow and zero browser exceptions. No model download was submitted.

### Complete Popular/Recent preview rows — 2026-10-27

The previews now choose a complete-row capacity near twenty cards from the
available fractional width and the same CSS minimum-card width/gap used by the
grid. Three columns show 21 cards, four show 20, six show 18 and eight show 24.
A width observer reflows the previews only when that geometry changes.

Bounded cursor reads retain up to four metadata pages per collection. Popular
fills after excluding records without download counts; Recent fills after
removing duplicates of the displayed Popular cards. Extra results remain in the
browser pool for later resize, avoiding repeated reads for already-filled sizes.
Modern 21-row and legacy 20-row routes both retain their actual cursor chain;
unsupported limit filters fall back once per collection. Discovery errors retain
available cached rows without fabricating cards. Finite/failed sources may show
fewer complete preview rows; See all retains the full collection's browser path.

`/tmp/klaude_discovery_rows_check.py` passed against modern and older-host response
shapes at 320/390/768/1000/1200/1440/1920/2200/2400/2560/3840px, including repeated
resize cycles and fractional width boundaries. Both collections reached complete
rows, missing-count records and overlapping Recent entries were replaced, no
card appeared twice, cached resize needed no repeat catalog fetch, every cursor
page had a previous page, and no browser overflow or exceptions were recorded.
JS syntax, CSS bundle and diff checks passed. No weights/model operations or live
host restart were involved.


## See all responsive rows (2026-10-27)

Top GGUF and Recently updated drill-downs now use the shared measured column
count to choose a complete-row page size near twenty, rather than fixed twenty.
The catalog accepts bounded 1–50 result requests and isolates continuation caches
by query/order/page size. Short or filtered batches are topped up through the Hub
cursor, at most four metadata calls, without skipping valid results. Unknown
download counts remain visible without an invented rank. Genuine source exhaustion
can still leave a partial final page.

Next/Previous and numbered paging use the actual capacity, and page URLs retain
the size. Changing columns starts at page one because the Hub cursor chain belongs
to the prior size; it never reuses a cursor with another size or drops overflow
models. The visible results-per-page label follows capacity.

Isolated Chromium verified both actual See all entry points at 320, 390, 1200,
1440, 1920, 2200, 2400, 2560 and 3840px: complete rows, no overflow, ordered distinct
second-page results, correct Previous behavior and URL size, no browser errors.
Focused catalog tests cover bounded adaptive sizes and short/duplicate/invalid
batch continuation with a disjoint second page. No live-host restart is claimed;
the expanded catalog limit requires the updated backend.
