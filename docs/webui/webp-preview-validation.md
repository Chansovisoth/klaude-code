# WebP previews in Files

Fixed 2026-10-20.

The shared image-header reader previously recognized WebP dimensions only in
the extended `VP8X` container. Ordinary lossy `VP8 ` and lossless `VP8L` files
were stored with unknown dimensions. Files requires dimensions before creating
a thumbnail or detail image, so those files appeared without a preview.

The reader now extracts dimensions from all three formats using bounded header
reads. Truncated headers, invalid lossy frame signatures and unsupported
lossless bitstream versions retain unknown dimensions. Format references:
[WebP containers](https://developers.google.com/speed/webp/docs/riff_container),
[lossless image headers](https://developers.google.com/speed/webp/docs/webp_lossless_bitstream_specification),
and [VP8 frame headers](https://datatracker.ietf.org/doc/html/rfc6386#section-9.1).

Existing files work without re-import: list/detail metadata derives missing
dimensions from a SQLite `substr` read of at most 65,536 bytes per image.
These private header bytes are removed before metadata leaves the store.
Reads neither decode pixels nor change source bytes, hashes, revisions or
stored metadata. Recognized PNG/JPEG/WebP/GIF files imported as Documents now
also record dimensions without changing the selected artifact type.

The existing browser preview gates remain: only PNG/JPEG/WebP/GIF, at most
8 MiB, 4 megapixels and 4096 pixels per side. The authenticated content route
still checks the artifact revision and checksum and serves the exact bytes with
the image MIME type. Oversized images retain the Download action.

A running Python host needs a restart to load this fix; no data migration or
re-import is required.

Validation:

- `pytest tests/unit/test_library_artifacts.py tests/unit/test_web_library.py
  -q`: **46 passed**. Actual Pillow-encoded lossy/lossless/extended WebP files
  cover dimension extraction and malformed/truncated headers. Existing
  Document/Media fixtures with null dimensions recover during reads, retain
  identical stored rows and expose no header bytes. Real authenticated image
  responses preserve the original payload and MIME. A 4097px-wide WebP remains
  blocked for inline preview and downloads intact.
- Ruff passed for changed Python files, and production mypy passed for all
  **210 source files**. The full repository suite was not run.
- Shared image preparation, chat attachments, image history and application
  Library regressions: **56 passed in 40.38s**.
- Real Chrome decoded all six legacy WebP thumbnails and detail views (the
  three container variants saved as both Documents and Media). Detail images
  fit 768, 390 and 320px viewports; the Files grid was checked at 1440px. The
  oversized fixture retained its generic image/download treatment. No
  JavaScript exceptions were observed. Diagnostic:
  `/tmp/klaude-webp-check.py`; screenshots: `/tmp/klaude-webp-preview/`.

## Live-host verification after the reported fallback

The reported 1219.9 KiB lossless WebP has dimensions 1598 × 1763, within all
existing preview limits. The updated store reader returned those dimensions,
but the still-running host returned null width/height for the same artifact.
The browser consequently created the generic `Image` fallback instead of an
image element. This was a stale Python host, not another WebP decoding failure.

The updated application first reopened the exact idle session successfully,
without model generation. The managed host was then gracefully restarted with
its existing workspace, session and LAN address. Public dialogue hashes and
model, mode, effort, plan and composer settings matched across the restart.

Real headless Chrome against the running host verified the user's exact file:
the authenticated inline response returned 200 with `image/webp` and identical
source checksum; the Files thumbnail and item detail both decoded at 1598 ×
1763. Preview bounds fit 1440, 390 and 320px widths, and the thumbnail still
decoded after a browser reload. No browser exceptions occurred. The temporary
verification client signed out, and conversation content remained unchanged.
No re-import or artifact revision change was needed. Existing browser clients
must sign in again after the graceful host restart.

Diagnostic: `/tmp/klaude-webp-live-browser-check.py`. No implementation changed
in this follow-up, so the focused unit suites were not repeated.
