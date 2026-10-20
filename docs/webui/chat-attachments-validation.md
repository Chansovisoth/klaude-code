# Browser chat attachments

Implemented and checked 2026-10-20.

The composer paperclip opens **Attach files**, with **From device** and
**From Library**. Device selection uses the browser file picker and the existing
authenticated upload route. Library selection searches and pages through saved
files, then captures the exact unarchived artifact revision and verifies its
checksum. Attaching does not modify the original file, Learn/index its contents,
or perform an ordinary Library import. Images retain the existing private Media
snapshot behavior needed for later chat turns.

Selections appear as removable file cards. They remain in the unsent draft
when submission fails. Snapshots preserve the chips and their keyboard focus.
Session changes and sign-out clear selections. A pending model reply allows file
preparation and Cancel; sending files waits until the current reply finishes.
Attachment queueing and steering are not implemented in this slice.

Supported inputs and bounds:

- Four files per message, including at most two images, within 32 MiB total.
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
