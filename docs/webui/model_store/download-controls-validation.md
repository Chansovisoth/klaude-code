# Downloads Remove/Stop and shared thin progress

Owned live pulls offer **Stop** through the existing cancellation endpoint.
Stopping keeps the native manager's existing unknown-outcome/recovery semantics;
it never assumes that remote partial-layer cleanup succeeded. Foreign observed
transfers remain controlled by their original client.

Completed, failed, cancelled and unconfirmed history entries offer **Remove**.
The administrator-only, Origin/CSRF-protected `/api/v1/models/dismiss` operation
persists a local presentation flag on the exact private target. It rejects active
workers/receipts and is idempotent. It makes no Ollama request, deletes no model
weights, and never changes or deletes the durable operation receipt or witness.
Message updates and dismissal share the target file lock.

Dismissed terminal entries disappear across service/browser reloads. Dismissed
unknown entries become compact **Check outcome** notices, retaining the exact
request and its admission fence. Successful witnessed reconciliation removes that
notice; dismissal alone cannot enable conflicting model work. Browsers served by
an old host show restart guidance rather than calling an unsupported dismissal
route.

Both owned and shared observed byte progress now use
`MaterialProgress.create({thickness: 'thin', value: percentage, label})`.
Material wavy, Material wavy static, Classic linear and Classic wavy static retain
the selected Theme style. Explicit byte-derived values disable elapsed-time
advancement; unknown byte counts are not replaced with invented percentages.
Thin is the existing 4px stroke variant. Model Store destroys progress instances
on rerender, details navigation, leaving Models and sign-out. The canonical
loading source is rebundled into `app.js` for current/legacy static delivery.

Validation uses actual isolated HTTP fixture workers and Chrome, with no real
model weights or inference. Backend coverage includes durable/idempotent removal,
CSRF/admin access, rejecting active removal, retaining unknown fences and exact
recovery, and no additional pull/delete HTTP effects. Browser coverage includes
four determinate bar presets, phone/desktop light/dark rendering, failed Remove,
active Stop, removal of an unknown row into its compact recovery notice, reload
and sign-out cleanup. Results are recorded in
`/tmp/klaude-download-controls-tests.log`,
`/tmp/klaude-download-controls-browser.log`, and
`/tmp/klaude-download-controls-store-browser.log`.

The focused Model Store/model settings tests pass: **26 passed**. The Downloads
browser walkthrough passes all four progress styles at 320/390/1440 pixels in
light/dark themes, including real fixture Stop/Remove/reload interactions and no
console errors. The complete Model Store/Image Studio walkthrough also passes
at 320–1440 pixels with no console errors. Mypy passes for the three affected
production Python modules. Focused Ruff, JavaScript syntax, bundle consistency
and `git diff --check` pass; `host.py` retains its pre-existing unrelated E501
on the static route map.
The pinned/local asset and CSP regression adds **1 passed**. The shared Theme
walkthrough passes **88 layouts**, including startup, all existing bar previews,
reduced motion and cleanup, with no browser exceptions or accessibility failures:
`/tmp/klaude-download-controls-theme-browser.log`.

Activation remains separate from implementation: the previously observed live
host could not pass exact-session restart preflight because its current empty
conversation had no saved model choice. That host has not been restarted or its
session identity changed for this request.
