# Inline image search

Image search sits immediately before Download in the preview toolbar. Clicking
it activates optional cropping directly on the displayed image, without a second
dialog, tabs, screen capture, screenshot selection or permission prompt. The
viewer fits the image, snapshots its existing bounded preview, and selects all
pixels by default. A filled Material Search button with a search icon stays at
the bottom center of the image stage. Cancel sits at its top right. The image
search button toggles the mode and exposes aria-pressed.

Search immediately uses the whole image unless the user adjusts the selection.
Drag to select, drag within a partial selection to move it, and drag a corner to
resize. Corner hit regions are larger than their visible handles. Arrow keys
move a selection and Shift-arrows resize it; Home selects all and Enter searches.
The focusable canvas describes those keys and announces selection bounds.
Submitting Search exits crop mode and restores focus to the image-search toolbar
button after handing the selected pixels to the new tab. Escape also exits crop
mode and restores toolbar focus while preserving the preview. Viewer gestures and
image navigation remain out of the crop surface's way.

The overlay tracks image fit and stage resizing, including letterboxing. Its
annotated display canvas is separate from the source canvas used for output,
so dimming, outlines and handles never enter uploaded pixels. PNG preparation
is debounced after adjustments, with stale callbacks rejected. No Library file
or model setting changes. No external request occurs before Search.

Only Search submits multipart encoded_image to the fixed Google Lens upload
endpoint in a new tab with noopener/noreferrer and a generic filename. No local
URL, page text or source filename accompanies it. Preview pixels are bounded to
a 2048px side and prepared PNGs to 8 MiB. Cancellation, preview navigation,
closure, session changes and sign-out clear temporary pixels and file inputs.
The form-action policy permits self, lens.google.com and www.google.com for its
results redirect. Google results remain an external service.

## Sources and provenance

- Google visual-search help: https://support.google.com/websearch/answer/1325808
- Current Chromium upload endpoint/field behavior was checked against:
  https://chromium.googlesource.com/chromium/src/+/HEAD/chrome/browser/resources/new_tab_page/lens_form.ts
  and the matching lens_form.html. The integration is implemented independently.
- Lens icon: original 24px SVG drawn for Klaude, using monochrome Lens-style
  viewfinder corners, a lens ring and a lower-right dot. Rounded 1.7px strokes
  match the existing toolbar icons and inherit the toolbar text color. Its provenance
  and checksum are recorded in static/icons/google-lens-source.json.


## Verification

- The prior generated solid-color 32px PNG upload received HTTP 303 to
  www.google.com/search. No user image was used in that live endpoint check.
- scripts/webui_lens_smoke.py uses isolated Chrome, a generated red/blue image,
  private fixture storage and intercepted external uploads. It checks the
  default full-image upload, exact cropped dimensions/pixels, drag/move/resize,
  keyboard adjustments, centered Search geometry at 320/390/768/1440px,
  Escape/focus, rapid cancellation/reopening and sign-out cleanup.
- tests/unit/test_webhost_lens.py covers fixed assets, icon provenance/MIME,
  nosniff and the narrow form-action policy. No physical-device testing or
  recognition-quality testing is claimed. Package smoke requires the script,
  icon and provenance files; no full package build was run for this change.
