# Chat and Uploads file drops

Dragging device files over the main content area of Chat or Library → Uploads
shows a theme-aware drop screen: a dashed accent frame, blurred tonal surface,
an image/document illustration with an add badge and destination-specific
instructions. The shell and side panels stay visible. Reduced motion uses the
existing system/device preference.
The chat-window interaction follows the attachment pattern described in
[Claude's file upload guide](https://support.claude.com/en/articles/8241126-upload-files-to-claude).
The artwork and styling use Klaude's existing components and theme roles.

The shared controller lives in the existing `app.js` asset. Both destinations
register their own availability and receiver. Only file drags are intercepted;
text and link drags retain native behavior. File drops outside those destinations,
while signed out or with a dialog open cannot navigate the browser to a file or
trigger an upload. Nested drag events preserve the target. Leave, drop, Escape,
blur, visibility/navigation/session/auth changes and a 1.6-second drag-inactivity
fallback remove it. The fallback covers external cancellation without a DOM leave
event; native repeated drag-over events keep it visible while hovering.

Chat shares the device picker's upload/preparation path. Files remain unsent
attachments and preserve the draft. No Library import or message is submitted.
Existing checks enforce four files, all of which may be images, within 32 MiB;
image detection and document extraction remain on the backend. Invalid counts
and sizes are rejected before uploading. Preparation errors appear inline as
well as in the existing attachment dialog, retaining previously accepted files.
Files can still be prepared during a reply and sent once it ends.

Uploads accepts up to 20 files per drop, each nonempty and no larger than 32 MiB.
It reuses the existing import form and exact per-file backend reviews, preparing
one file at a time. Each confirmation admits an independent import. The next
review waits for the prior operation to complete and release the shared import
resource, using the existing Activity receipt polling. Cancelling
stops the remainder; earlier accepted imports continue. Failed requests retain
the current file for retry, and uncertain submissions do not advance the queue.
Navigation, changing Library tab, selecting a replacement file or signing out
cancels the remaining drop batch. Stale uploads/reviews are discarded instead of
reopening a dialog. Folders are rejected without walking their contents.

Validation uses isolated temporary profiles, hosts, files and stores:

- `scripts/webui_drop_smoke.py`: real Chrome drag data containing local paths;
  light/dark overlays at 1440×900, 768×844, 390×640 and 320×480 for both destinations;
  layout fit, cancellation/inactivity, no upload on hover, unsent Chat attachments,
  count/size limits, three/four-image selections and a blocked fifth file,
  real directory rejection, inline failed-upload errors,
  stale-chat cleanup, separately confirmed multi-file imports, partial batch
  cancellation, failed-import retry, a lost submission acknowledgement,
  unrelated-page guards, in-flight logout cleanup and browser exceptions.
- `scripts/webui_attachments_smoke.py`: existing device/Library attachment,
  private input, thumbnails, picker, active-reply and logout behavior.
- `scripts/webui_library_browser_smoke.py`: existing file picker, import review,
  late-review discard, Library navigation, previews and responsive behavior.
  Its older viewer checks now use the current Download link and inline tag editor,
  and close the retained inspector before opening the import dialog.
- JavaScript syntax, focused Ruff, Python compilation and `git diff --check`.

Screenshots are written to `/tmp/klaude-file-drop-preview/`. Browser viewport
simulation does not certify physical devices or every OS/browser drag source.
No backend authorization, permission, extraction or persistence behavior changes.

Recorded results: all 16 overlay layouts and drop workflow checks passed with zero
browser exceptions. The attachment and Library browser regressions also passed
with zero browser exceptions. Syntax, focused Ruff, compilation and diff checks
passed. This is focused validation, not a full repository test-suite run.

Four-image update: the browser fixture now verifies three image drops followed by
a fourth, and that a fifth file cannot upload. All 16 overlay cases and remaining
drop workflows passed with zero browser exceptions. The shared worker, image
history and provider suites passed 318 tests, including four-image Ollama,
compatible, Anthropic, OpenAI Responses and Gemini delivery through local HTTP
fixtures. Focused Ruff, six-source-file mypy, JavaScript syntax and diff checks
passed. The idle managed host was gracefully restarted with its conversation,
workspace, LAN binding and hosting preferences preserved to load the Python change.

Icon refinement: replaced the three plain paper shapes and upload arrow with a
single local SVG combining an image, folded document and small add badge. The
artwork uses current theme roles, scales within the existing short-screen area,
and stays decorative for assistive technology. Unavailable drop states use muted
colors. Overlay layout, text and all drop handling remain unchanged.
`scripts/webui_drop_smoke.py` passed all 16 light/dark, desktop/phone layouts and
the existing real-file drop workflows with zero browser exceptions. Desktop
light and 320px dark captures were inspected. Evidence:
`/tmp/klaude-drop-icon-smoke.log` and `/tmp/klaude-file-drop-preview/`.
JavaScript syntax, loading-bundle consistency and whitespace checks passed.
Only `static/app.js`, `static/style.css` and guidance/validation notes changed
for this icon refinement; no backend changes, commit or push.
