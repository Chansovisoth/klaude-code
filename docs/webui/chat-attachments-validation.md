# Browser chat attachments

Implemented and checked 2026-10-20.

The composer paperclip opens **Attach files**, with **From device** and
**From Library**. Device selection uses the browser file picker and the existing
authenticated upload route. Library selection searches and pages through saved
files with the Library's file-type icons, concise type/size labels and authenticated
image thumbnails, then captures the exact unarchived artifact revision and verifies its
checksum. Attaching does not modify the original file, Learn/index its contents,
or perform an ordinary Library import. Library images reuse their original artifact
ID and captured checksum, including images stored as Documents or Generated; sending
or reattaching them never creates another Uploads record. The send path rejects an
archived or changed source rather than sending different bytes. Later image turns
and restored sessions use that same reference, so removing the original makes its
pixels unavailable. Device images retain the existing private Media snapshot
behavior needed for later chat turns.

Selections appear as removable file cards. They remain in the unsent draft
when submission fails. Snapshots preserve the chips and their keyboard focus.
Session changes and sign-out clear selections. A pending model reply allows file
preparation and Cancel; sending files waits until the current reply finishes.
Attachment queueing and steering are not implemented in this slice.

Supported inputs and bounds:

- Four files per message, all of which may be images, within 32 MiB total.
  The shared private-reference, request-projection and provider serializers also
  accept up to four images, including restored/follow-up requests. This replaces
  the original two-image cap; existing image preparation and provider byte/token
  budgets remain enforced. Running Python hosts must restart to load the change.
- UTF-8 text/code: at most 1 MiB of source bytes, 32,000 extracted characters per
  file and 64,000 across the message. Truncation is visible in the picker and in
  model context. Binary and empty inputs receive an actionable rejection.
- PDF: unencrypted, text-extractable documents, at most 50 pages and 32,000 text
  characters. Scanned PDFs need OCR and are rejected when they contain no text.
- DOCX: `word/document.xml` within 2 MiB, with entity/DOCTYPE declarations
  rejected, and the same 32,000-character output limit. Legacy `.doc` is not
  supported. PDF/DOCX parsing uses a disposable subprocess with a 15-second parent
  deadline, CPU/memory limits, bounded output and a minimal environment.
- PNG/JPEG/WebP/GIF: source headers within 40 megapixels and 32,768 pixels per
  side. The shared Vision path then fully decodes/prepares the image and checks
  enabled Vision and the exact active chat model's declared image capability.
  Browser frame/crop/detail controls are not included; animated sources needing
  an explicit frame receive the existing preparation error.

The prompt and filenames are public dialogue. Extracted source text and immutable
image references are saved only as private `model_content` under the admitted
worker's session fence. The Agent receives the original prompt for tool routing
and separate file context for generation. Public snapshots, SSE replay, session
search and export do not expose that private context. Generated replies can
still quote or summarize the file when requested.

Selections are bound to the authenticated owner, browser tab and chat session,
expire after 30 minutes, and have a 32-selection / 64 MiB host-wide memory cap.
Two document preparations may run concurrently. Consumed and rejected device
uploads are removed from staging; logout/shutdown revoke unaccepted selections
and staged uploads. An accepted worker retains immutable captured bytes. Durable
request fingerprints include file names, byte hashes and extracted content, so
an identical request ID cannot silently submit different files.

Validation:

- `tests/unit/test_chat_attachments.py`: seven tests covering real PDF/DOCX
  extraction, text/binary/aggregate limits, private model input and public
  projections, request deduplication, exact Library revisions, owner/tab/session
  isolation, rejected-upload cleanup, and real pixel delivery to an isolated
  Ollama HTTP fixture through the shared fenced worker.
- Focused attachment, webhost, accounts, Library, application bridge,
  coordination and session suite: **116 passed in 61.19s**. This is a focused
  regression suite, not the full repository suite.
- Attachment plus core chat-image history/transport suite: **38 passed in
  30.49s**, including text-only retry after restore without a Vision requirement.
- `scripts/webui_attachments_smoke.py`: real headless Chrome login, device
  upload, Library search and pagination, unsupported format rejection, filename
  chip focus retention, successful model delivery with private source canaries,
  active-reply behavior, removal and logout cleanup. At 1440×900, 768×900,
  390×640 and 320×480, the composer and dialog fit without horizontal overflow,
  and Attach/Send targets are 44×44px. No JavaScript exceptions were observed.
  Screenshots: `/tmp/klaude-attachments-preview/`.
- Python production type checks passed for all 210 production source files;
  Ruff and JavaScript syntax checks passed for the changed surface. All seven
  workspace wheels built and installed in an isolated environment, including
  the new attachment asset and PDF dependency; imports and both CLI help
  commands passed. `pypdf` is explicit in the frozen workspace lock.

The image HTTP fixture verifies serialized pixels and capability checks, not
live-model quality. Chrome device emulation does not certify physical iOS or
Android file pickers or every accessibility interaction. A running host must
reload its Python backend to expose the new attachment capability.

Current Library organization is documented in
`navigation-organization-validation.md`; attaching a saved file uses the same
underlying artifact inventory, independently of Library's selected filters.

## Running-host attachment repair

The live host was still running Python code from before attachments were added.
It served the updated HTML from disk, but returned 401 for `/attachments.js` and
omitted the attachment capability from its snapshot. The paperclip consequently
appeared without a click handler. This was reproduced on the running server;
the same attachment flow passed against a newly started isolated host.

The idle managed host was gracefully restarted with its exact selected session,
workspace and LAN address. Public dialogue hashes, model/runtime, composer and
plan settings were compared across restart. Afterwards the script returned 200
and the public snapshot advertised attachment support.

The browser now disables an unavailable paperclip and explains when either the
attachment script or server capability is missing. The attachment smoke passed
again, including both mismatch cases, device/Library preparation and delivery to
the deterministic model fixture, cleanup, and all four viewport sizes. A separate
live-host check uploaded and prepared a disposable text attachment, discarded
it, and signed out its temporary client without model generation or conversation
changes. JavaScript syntax checks, focused Ruff and `git diff --check` passed.
The full Python suite was not rerun for this static guard and host reload.

Reload the browser after the host restart; existing browser cookies are revoked
by the graceful shutdown, so signing in again may be necessary.

## Attachment cards and image thumbnails

Added 2026-10-20. Composer selections and newly sent user messages show rounded,
theme-aware file cards with a filename, file type and size. PDFs have a document
icon with a PDF badge. Images replace the icon with a thumbnail; other formats
keep a document icon and their extension label. Remove buttons remain 44px.
Sent messages show the prompt above their cards instead of the bracketed list.
The underlying public transcript and export keep their original text.

Image previews reuse the disposable, bounded pixel decoder, select frame zero
for presentation, normalize orientation, remove metadata and produce PNGs no
larger than 128 pixels per side. These small derivatives are separate from the
image delivered to the model; preview generation does not enable Vision or
change its capability checks. Failed previews retain the image icon.

Two additive dialogue columns store safe descriptors and bounded thumbnail
bytes, separately from private model input. Admission saves them atomically with
the user message. Forks copy both columns; deletion removes them with the row.
Snapshots and exact linked-message reads project descriptors only. Authenticated,
no-store thumbnail requests check the exact current session and message; unsent
previews additionally check the selecting owner and tab. Existing text-only rows
remain literal rather than interpreting ordinary user text as real attachments.

Validation for this change:

- Attachment, session, coordination and HTTP host regressions: **84 passed in
  52.08s**. Tests include real pixel delivery, public reads with SQLite access to
  `model_content` denied, reopen/fork/deletion of cards, owner/tab/session preview
  isolation, anonymous rejection, discard invalidation and metadata removal.
- Core memory, image preparation and chat-image regressions: **80 passed in
  44.88s**. These focused runs are not the full repository suite. The first run
  inside the restricted sandbox could not open HTTP fixture sockets; the
  subsequent runs used approved local socket access.
- `scripts/webui_attachments_smoke.py` passed in real headless Chrome: image
  thumbnails in composer and saved messages, stable thumbnail DOM across
  snapshots, PDF badges, actual PDF/text delivery to the deterministic runtime,
  page reload, selection removal and sign-out cleanup. The completed image turn
  is seeded for presentation checks; the HTTP unit fixture separately verifies
  actual model pixel delivery. All four viewport sizes fit without horizontal
  overflow and primary targets remain 44px. No JavaScript exceptions occurred.
- Production mypy passed all 210 source files; focused Ruff and JavaScript
  syntax checks passed. Screenshots: `/tmp/klaude-attachments-preview/cards-*.png`.
- The broader Markdown Chrome smoke also passed its streaming, selection,
  literal-user-text, sharing, history and sixteen theme checks with no browser
  exceptions. One model-catalog request aborted during navigation logged a
  server-side broken pipe; the smoke completed successfully.

The running Python host must restart to expose persisted attachment descriptors
and the thumbnail endpoint, followed by a browser refresh. Historical text-only
attachment messages do not acquire previews retroactively.

## Library attachment reuse repair

The Library picker captured the selected bytes but discarded their artifact ID.
Sending an image therefore created a chat Media snapshot that appeared as a new
Upload. The private selection now carries the original ID and captured checksum
through image preparation; existing Library images skip snapshot insertion.
Document image references verify the actual image header, including when the
stored filename has a text extension. Device snapshot behavior is unchanged.

Validation on 2026-10-20:

- Attachment, chat-image, image-recovery and artifact regressions: **96 passed in
  60.47s**, using isolated local HTTP fixtures. This is a focused suite.
- The 13 attachment tests cover repeated Library sends, exact original IDs,
  unchanged Uploads/Generated inventories and metadata, restored-chat pixels,
  images stored as Documents, and rejection of changed/archived image selections.
- Production mypy passed all 211 source files; scoped Ruff and `git diff --check`
  passed. No live model or browser smoke was run for this backend repair.

Restart the Python Web UI host to load this change. Existing chat snapshots are
retained because older conversation references may depend on them.

## Library picker artwork

The attachment Library picker now uses the same `fileIcon`, `artifactImage` and
preview-eligibility helpers as the main Library. Compact 44px artwork shows PDF,
document and code icons or authenticated, revision-checked image thumbnails;
type/size labels use the Library's formatting.

`scripts/webui_attachments_smoke.py` passed in real headless Chrome with decoded
Library thumbnails, PDF badges and document/code icons. Picker artwork and Attach
controls fit at 1440, 390 and 320px widths without horizontal overflow; the existing
attachment flow also passed at 1440, 768, 390 and 320px. There were no JavaScript
exceptions. JavaScript syntax, scoped Ruff and `git diff --check` passed.
Screenshots: `/tmp/klaude-attachments-preview/library-picker-{1440,390,320}.png`.
This browser fixture does not certify physical mobile devices or live-model quality.

Reload the browser page to load the updated static assets.

## Attachment source icons

From device now has a leading laptop icon, switching to a smartphone at the
existing 560px phone breakpoint. From Library copies the Library navigation
icon. The decorative SVGs retain the existing button labels and both controls
fit on one row at 320px.

The real Chrome attachment smoke passed with responsive device icons at 1440,
390 and 320px, matching Library icon paths, leading placement, and no browser
exceptions. Existing device/Library attachment, thumbnail, reload and cleanup
checks also passed. JavaScript syntax, scoped Ruff and `git diff --check` passed.
Screenshots: `/tmp/klaude-attachments-preview/library-picker-{1440,390,320}.png`.
Refresh the page to load these static asset changes.

## Sent attachment previews

Added 2026-10-22. Sent file cards are keyboard-accessible buttons that open the
existing Library image/file preview dialog. Image zoom, fit, mobile details,
safe Markdown/source rendering and Copy reuse the current viewer. Chat previews
show Sent metadata and original Download, with Library editing and previous/next
file navigation hidden. Closing restores focus to the attachment card; session
changes close the preview, and late responses cannot reopen it.

Admission now atomically captures original attachment bytes and SHA-256 checksums
in the private `attachment_contents` dialogue column, separately from
`model_content`. The existing four-file/32 MiB aggregate bound applies; base64
encoding adds storage overhead. Forks retain originals, and session deletion
removes them with the dialogue. Public snapshots, exports, replay and search
continue to expose descriptors rather than private bytes. Library selections
retain their original artifact identity and do not create another Library import.
This copy supports preview/download after the Library original is removed; model
image follow-up references retain their existing Library availability semantics.

The authenticated `/api/v1/chat/attachments/content` read validates the exact
current session, stored user message and attachment index. Two concurrent reads
are allowed. It checks stored size before loading, verifies checksums, returns
no-store responses, and rechecks authority before delivery. Image presentation
uses the existing disposable, metadata-free bounded decoder. PDF/DOCX use the
existing bounded extraction subprocess; the preview explains that downloading
preserves the document layout. Downloads preserve original bytes and use an
attachment disposition. Uploaded HTML executes neither scripts nor remote images.

Older messages did not retain all originals. Available Library files can still
be read; old device images can show their retained thumbnail with a clear notice.
Other older device files explain that the original must be attached again.

Validation:

- `tests/unit/test_sent_attachment_previews.py`: **4 passed**, covering real
  image/text/DOCX previews and exact downloads, metadata removal, no public content
  leakage, denied `model_content` access, exact scope/authentication, legacy
  fallback, corrupted checksums, reopen/fork/deletion, and logout or message
  deletion during image decoding.
- Final attachment, Memory and sent-preview regressions: **52 passed in 38.24s**,
  including the four preview tests above. This is a focused suite.
- The real Chrome attachment smoke passed sent image/text/Markdown/PDF previews,
  original downloads, safe rendering, keyboard activation, zoom, focus restoration,
  reload, stale-response dismissal, restoration of Library editing controls after
  chat previews, and existing device/Library send behavior.
  Previews fit at 1440, 390 and 320px; the existing attachment flow also covers
  768px. No JavaScript exceptions occurred. Screenshots are in
  `/tmp/klaude-attachments-preview/`.
- The full Context panel smoke passed its existing Library preview, drag/attach,
  session isolation and 24 responsive layouts with zero JavaScript exceptions.
- A separate real Chrome check exercised List/Grid/Gallery controls in the main
  Library and Context panel across light/dark themes and 1440/768/390/320px:
  **48 layouts passed**, with visible gaps, consistent 12px radii, one selected
  view and no horizontal overflow. Screenshots are in
  `/tmp/klaude-view-controls-preview/`.
- Focused Ruff, four-file production mypy, JavaScript syntax, both static asset
  bundle checks and `git diff --check` passed.

This does not certify physical mobile devices, live-model behavior or the full
repository suite. A running Python host must reload to advertise
`attachment_content`; the UI explains missing backend support on older hosts.

The idle managed host was gracefully reloaded with its exact selected session,
model, workspace and listeners. Public dialogue and account/preference files were
compared across reload and remained unchanged. The live snapshot now advertises
`attachment_content`. Reload the page; signing in again may be necessary because
the managed shutdown revokes browser cookies.
