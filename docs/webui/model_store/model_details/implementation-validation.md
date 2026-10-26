# Full-page model details implementation

Current update (2026-10-26): the user requested removal of the image carousel.
Its artwork templates, controls, handlers, resize observer and CSS are removed.
Stats now lead directly into About and variants. The historical implementation
and evidence below describe the earlier gallery version; current validation is
in [Downloads simplification and carousel removal](../downloads-simplification-validation.md).

Date: 2026-10-25. Implements the detail-specific requirements in
[klaude-model-store-image-studio-codex-handoff.md](klaude-model-store-image-studio-codex-handoff.md)
and the supplied [HTML reference](klaude-model-detail-flathub-reference.html) and
[desktop reference image](model-detail-flathub-desktop.png). Earlier Discover V2
work remains intact and uncommitted.

## Reference inspection and delivered composition

Before implementation, the live [Calculator](https://flathub.org/en/apps/org.gnome.Calculator)
and [OBS Studio](https://flathub.org/en/apps/com.obsproject.Studio) pages were read
and viewed in Chrome at 1440px and 390px. Captures are in
`/tmp/klaude-flathub-reference/`. Remote image-proxy content stayed as placeholders
in that browser; the surrounding live composition and media geometry were visible.
The supplied complete HTML/PNG provided the permitted illustration reference.
No Flathub CSS, application screenshots, icons or branding were copied.

The former native detail dialog is replaced with a full page inside the existing
Models destination and its single vertical scroller. Its exact DOM order is:

1. Model Store Back action.
2. Large local model icon, model name and source/publisher byline, with a filled
   Install/Use action at the right on desktop. Phones retain the handoff's
   horizontal icon/name pairing and a full-width action below it. Selected exact
   tag and installation blockers stay inside this identity area.
3. One metadata strip directly beneath identity: selected download, documented
   parameters, known format, catalog license and catalog capability declarations.
   Phone tiles reflow to two rows; unknown values remain explicitly Unknown.
4. Wide three-image gallery with previous/next, 44px-target position indicators,
   keyboard arrows/Home/End, native horizontal touch scrolling and scroll snap.
5. Readable About; long descriptions get native Show more/less disclosure.
6. Exact variant rows, optional native destination selector and shared 20-row
   pagination, plus the selected-variant action near the selector.
7. Lower compatibility/source/license disclosures and exact/broad source links
   labeled according to the data actually available. Installed deletion remains
   a separate reviewed action.

The gallery uses the original orbit/ribbon/crystal SVG illustrations from the
user-supplied HTML, embedded as static local templates. Visible copy labels these
as decorative artwork, without presenting them as model output or capability
proof. Forced colors provides a system-colored text fallback. Gallery index is
preserved across resize/render updates, reduced motion disables smooth scrolling,
and observers disconnect when leaving/replacing the page or signing out. Existing
licensed AI model/family marks and generic fallbacks remain authoritative.

## Exact choice, navigation and lifecycle

Install never chooses the first family/GGUF file implicitly. With no selected exact
variant, it focuses the inline selector. Choosing a radio row updates the explicit
URL state and enables the selected-variant review path. A local installed model
has an already exact identity; Use model remains a separate current-chat runtime
operation. Changing variant, inspecting metadata or moving the gallery never
installs, starts generation, selects a chat model or changes Model Defaults.

`models-detail` retains the existing detail identity and `models-variant` retains
the selected tag. The same Store URL state owns tab/query/category/source/order/
capability/size. A bounded History context holds the originating scroll/focus and
inventory page. Page Back uses natural browser history for in-app entries, with
replacement navigation for standalone deep links. Back/Forward and reload preserve
context; focus returns to the originating card/row without scrolling it away.
The selected variant's containing page is restored after metadata loads.

The full-page body renders only when its relevant metadata/control signature
changes, preserving native disclosure, gallery and focus state during snapshots.
Model/queue busy states, native inventory freshness, active/unknown operation
fences, admin authorization and exact endpoint/credential checks remain unchanged.
Preparation/runtime errors surface beside the primary action. A source failure
leaves a navigable, disabled page and offers explicit read-only Retry source
details. Cached source metadata is labeled, with checked time in supporting
source details. Unsupported split/projector/subdirectory files remain excluded
with the existing integration explanation and source link.

## Files and tests

Production files: `static/index.html`, `media.js`, `expressive.css` and generated
`style.css`. No Python HTTP route, worker, downloader, persistence schema, model
backend or authorization contract changed. All effects still use existing
`prepareChange`, the fixed worker, durable receipts and runtime selection.

The new `scripts/webui_model_detail_smoke.py` uses real isolated metadata HTTP and
browser requests with password-admin LAN policy. It checks:

- Page semantics and icon/name/action → stats → gallery ordering; full-width phone
  Install, desktop title scale, body overflow, light/dark screenshots at
  **320/360/390/430/768/1440px**.
- Header Install before selection creates no review/download; exact selected tags,
  metadata, large identifiers and explicit Unknown states.
- Gallery arrows/dots/Home and an emulated touch swipe; Show more/less.
- Card focus and measured scroll restoration, Back/Forward, shared 25-file variant
  pagination and selected-file restoration through reload.
- Unavailable source metadata, explicit source retry, forced colors/reduced motion,
  sign-out DOM cleanup, zero native pulls and zero JavaScript exceptions.

The adapted Store/Studio walkthrough preserves categories/charts, direct-tag review,
reviewed native pull, receipt reload, native inventory pager/focus, offline browsing,
Studio seed/drafts, fixture PNG generation and output preview. The settings
walkthrough preserves role saves, image-service Test, credentials, enable/Test,
multiple endpoint choices in the full detail page, removal and sign-out. These
also use isolated fixture effects and report zero JavaScript errors.

Evidence directories: `/tmp/klaude-model-detail-evidence/`,
`/tmp/klaude-model-store-evidence/`, `/tmp/klaude-model-settings-evidence/`.
JavaScript syntax, focused Ruff for all three changed/new walkthroughs, Expressive
bundle verification and `git diff --check` pass. Broad Python suites were not
repeated for this static-only slice; previous backend validation is recorded in
[completion-validation.md](../completion-validation.md) and
[admin-role-validation.md](../admin-role-validation.md). This is not a new full
repository test-suite pass.

## Live evidence and limits

An authenticated Chrome check against the running host passed at 320/390/1440px,
rendering full-page Qwen 3 details, explicit local tag selection, gallery and Back,
then the real inventory and existing download history. The saved session/model/
mode/effort remained unchanged; no saved settings, model weights or generation
jobs were changed. Final verification signed out its temporary client. Evidence:
`/tmp/klaude-model-detail-live-result.json` and
`/tmp/klaude-model-detail-live-evidence/`. The observed host retained its existing
active/unconfirmed model-work blocker; the live check did not bypass it.

Real weight downloads, image inference, physical-device touch/mobile chrome and
the whole repository suite were not exercised here. Gallery artwork conveys no
new model capabilities; unknown hardware fit, unsupported file sets and additional
image-output adapters remain unavailable. Existing dirty work and the supplied
reference files were preserved. Nothing was committed or pushed for this slice.
The host serves static assets directly, so reloading loads the updated UI without
a backend restart.

## Details flow refinement — 2026-10-26

The variant footer says Choose variant before selection, then Download with the
formatted size. The reviewed download action stays beside the file choices. Installed models
retain explicit Use model. Shared Ollama runtime/server badges distinguish the
destination from creator identity. Known facts use a compact strip with the Hub
download icon; generic placeholder About copy and repeated source links are omitted.
Variant pagination precedes the download footer. Native radio labels, fieldset
naming, keyboard focus restoration and reviewed exact-target mutations remain.
The layout follows Material 3 list guidance for concise, consistent row content:
https://m3.material.io/components/lists/overview

A focused live browser check passed at 320/390/1440px: no horizontal overflow,
shared runtime mark present, header shortcut focuses the selected file without
opening a review, footer includes Download and size, and no JavaScript errors.
No model operations or host restart. Syntax and whitespace checks passed.
