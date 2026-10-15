# Image attachment reliability follow-up

Date: 2026-10-16. Base `4a64ce696ba0e0825fa5670609d2449955304648`.
Existing uncommitted Library/navigation/model-capability changes were preserved.
No commit, push, real-user image upload, production provider/default change or local context increase.

## Scope and causes

This implements the bounded attachment work in
[the diagnosis/plan](image-attachment-reliability-plan.md). The investigated session
is `075e753a2edc4e7a9fbbb3e9995c11a0`; its historical generic provider errors
cannot retrospectively establish an upstream cause or routed model.

Confirmed causes repaired:

1. Image admission and compaction used different context authorities; fresh image
   metadata did not update the active model limits. Both now use `request_budget`.
   Configured local allocation remains explicit. Declared cloud limits stay separate
   from Ollama `num_ctx`; unknown cloud capacity is a labeled 32768-token estimate.
2. Ordinary phone images were rejected without preparation. `image_preparation`
   fully decodes in a private, cancellable process, retains original Media bytes,
   normalizes orientation/color/transparency, removes metadata and makes a bounded
   PNG/JPEG derivative. Source caps: 32 MiB, 40 MP, 32768 side. Delivery caps:
   7,500,000 bytes, 4 MP, 4096 side, additionally constrained by request capacity.
3. Accepted failed image turns lost explicit retry state. Private references and the
   question now survive local/provider failure and process restore. `try again`
   replays that attempt; named stored images can be activated without source files.
4. Compatible/OpenRouter errors discarded typed causes. Host-written allowlisted
   context/image, rate/service, quota/auth/policy diagnostics replace raw bodies.
   One smaller preparation or one short transient retry is allowed before output.
   Partial output/private continuation/positive usage prevents automatic repeats.
   Long Retry-After, quota/auth and policy failures require explicit action.
5. Preflight could inherit earlier measured usage. Metadata is cleared before
   preparation/request validation. Safe actual routed model and response ID are
   recorded when returned; the requested model is not silently replaced.
6. A real small-context run found attachment directory names activating coding and
   Hugging Face tools. Only delivered image mentions are removed from intent
   routing; original text stays in history/model input. Explicit coding, text-file
   reads and research remain available. In the observed pure-image request,
   system text fell from 14994 to 1203 characters and schema estimate from 1851
   to 1 token, without changing its 4096 context or 512 output configuration.
7. Large binary/JSON private worker input could deadlock: after communicate timed
   out, polling with no input stopped servicing partially written stdin. The shared
   `PrivateProcessInput` writer services input independently and is reaped with the
   worker. A 7.5 MB input reproduction changed from the 15-second timeout to about
   0.3 seconds. An actual owned metadata-worker large-input regression also passed.

## User interaction and limits

- Auto uses a bounded overview (1024 side); text/screenshots/diagrams request more
  detail (2048 side) when they fit. `--detail original` is still bounded to provider
  and context limits; it is not an API promise of unmodified pixels.
- `/attach --crop x,y,width,height PATH` uses oriented original coordinates;
  `/attach --frame N PATH` explicitly chooses animation frames (0–255).
- Static WebP/GIF join PNG/JPEG. Animated sources require explicit frame selection
  in chat; reviewed Media does not select a frame automatically. HEIC/AVIF/BMP/TIFF
  remain unsupported and fail as images, never as misleading binary text context.
- Explicit `media:ID` reattachment rechecks current scope/checksum/archive state;
  a known filename works after source deletion. Derivatives are bounded in-memory
  cache entries, not replacement originals. Endpoint/key changes still require
  explicit approval via reattachment; no model or provider fallback is inferred.
- At most two distinct images are delivered per request. Old tool rounds can be
  compacted together to admit a current image; essential current content and tool
  pairs remain intact. There is no new autonomous zoom tool or image batch loop.
  Follow-ups can still project the latest two approved snapshots; no dedicated
  active-image picker or per-image detach control was added in this pass.
- Dimensions/detail/crop are supplied with actual pixels. Recaps are not pixels.
  A delivered image count does not prove model comprehension or answer accuracy.

## Real CLI and interactive evidence

All images were synthetic. Test config/store were isolated beneath
`.klaude/data/s2-models-8l04hzu1`; workspace `/tmp/klaude-s2-workspace-sjnk3lgf`.
The original source was a 3000×4000 (12 MP) lossless WebP with red/green/blue
regions and the small text `BUILD 742`. Local Ollama, Standard, num_ctx=4096,
num_predict=512; production preferences unchanged.

| Scenario | Actual result |
| --- | --- |
| `klaude ask "Name the three large colored regions from left to right. Reply briefly. @PATH" --model ollama/gemma4:e2b` | Exit 0, red/green/blue, 11.30s |
| Same one-shot, `ollama/gemma4:e4b` | Exit 0, red/green/blue, 21.38s |
| Bare `klaude`, session `TEST KLAUDE FEATURES IMAGE ATTACHMENTS`, `/attach` source then color question | Correct red/green/blue |
| Delete source; `/attach --detail detailed --crop 1800,2800,1200,600 phone.webp`; read BUILD | Correct BUILD 742 from saved original |
| Exit client, new process `/resume 8dee2452bb164602898bc2576e96373c`; ask previous image's BUILD again | Correct 742; no original file |
| `library analyze` saved 12 MP WebP through reviewed Vision role, Gemma E2B | Exit 0, correct colors, 8.28s |
| TUI widths 40/80/120 and resumed view | Captured; inspected 40/120 renderings. Composer/status remain usable; existing terminal scrollback lines can clip on shrinking a previously wide terminal. |

Machine-local receipt: `image-fix-live-result.json`, per-model one-shot transcripts,
`large-webp-media-cli.txt`, SVG/PNG captures and private terminal logs under that
isolated root. An initial resume harness waited for a nonexistent `Resumed` label;
actual restored history was correct. The corrected harness verified a fresh answer
and clean exit; no product change was made for that harness assertion.

## Automated validation

Focused additions cover all four supported codecs, EXIF orientation, transparency,
metadata removal, no upscaling, explicit frames/crops, corrupt/truncated input,
resource/cancellation limits, large pipe input, stored originals, verified cloud
budgets, local admission retry/restore, typed context/transient recovery and
quota/policy/partial-output no-retry. Existing multi-provider chat/Media, tool-pair,
compaction, background cancellation, restore and configured-context tests remain.
The old tiny PNG fixture had an invalid IDAT CRC; it was replaced with a fully
valid image and retained separately as a corrupt-input regression.

Final focused verification: 148 image preparation/chat/provider/recovery/HTTP Media
tests passed in 158.97s after the final always-reencode hardening. A broader image
pass including native Media had 168 passing tests before that final hardening.
CLI/settings: 883 passed, one skipped (85.41s). Defaults/capabilities/core defaults:
60 passed (9.65s), including manual navigation while discovery is still running.
Ruff and production mypy passed on all 151 source files; `git diff --check` passed.

### Complete integration gate and distribution check

`UV_FROZEN=1 UV_OFFLINE=1 UV_CACHE_DIR=/tmp/klaude-roadmap-uv-cache make check`
passed: **3572 tests passed, 19 skipped** in 774.65s; Ruff passed; production mypy
passed on 151 files. Log and JUnit evidence:
`/tmp/klaude-image-fix-validation-e5u687bt/{check.log,pytest.xml,result.json}`.

Two final hardening tests (manual navigation during discovery and small-container
trailing-data removal) were added while that integration run was in progress, so
its count excludes those additions. Final relevant source was separately verified
by the 148 image tests above, **21 native Media tests** (26.16s) and the 60
defaults/capability tests. Final source lint/types and diff checks passed again.

`make package-smoke` then passed: all **five wheels** built, installed together in
an isolated environment, public imports and installed `klaude --help` succeeded
(6.53s). Its final run was frozen/offline after missing cached dependencies were
obtained using exact `uv.lock` constraints; no unbounded dependency upgrade was
used to make the distribution test pass. The core Pillow dependency and lockfile
are part of this change.

An earlier complete development run had three test failures: one expected
unchanged routing text, while two fake runtimes preloaded completion metadata
instead of publishing it on completion. The routing expectation and fixture
producers now reflect actual request behavior; lost-native-call recovery and
normalized usage checks pass. The fresh complete gate above passed afterwards.

### Final-source real rerun

The complete one-shot/TUI/deleted-source/crop/process-resume flow was repeated
after the Model Defaults changes. Receipt `.klaude/data/s2-models-802p5glc/`
`image-fix-live-result.json` records PASS: Gemma E2B exit 0 in 12.44s and E4B
exit 0 in 22.04s; interactive session `21fee3d6001b4bd68b436d1b01187473` read
colors and BUILD 742, including fresh process resume after source deletion.

An additional real CLI/TUI path used a local compatible-provider **fixture**,
not a paid inference service. Its first image request returned typed HTTP 402
quota exhaustion: exactly one request and no automatic retry. After deleting the
source and restarting/resuming, `try again` supplied the saved original question
and pixels (747×1024). A typed context rejection then caused exactly one smaller
request (457×628), which completed. All three requests retained the same model;
private provider body text was absent from the transcript. Receipt:
`.klaude/data/s2-models-x3ub7a52/retry-fixture-result.json`, session
`b4fbd738ba2648f0b77f6de08e07c6dc`. This verifies client orchestration and
projection, not upstream model comprehension.

## External guidance and boundaries

- [OpenAI vision guide](https://developers.openai.com/api/docs/guides/images-vision):
  use documented per-model sizing/token rules. Exact reviewed GPT-4.1-mini profiles
  use 32-pixel patches and a 1.62 multiplier; other adapters retain explicitly
  conservative estimates rather than inheriting that formula.
- [Pillow security](https://pillow.readthedocs.io/en/stable/handbook/security.html):
  Pillow 12.3 is locked; source/pixel/text/output/time/memory bounds and an owned
  process reduce decoder exposure. This is not an OS sandbox or network security
  boundary; the process receives no provider credentials.
- [OpenRouter errors](https://openrouter.ai/docs/api/reference/errors-and-debugging):
  HTTP 200 streams may carry typed errors. Never treat HTTP success as completed
  inference or echo raw provider diagnostics/credentials.

Paid-cloud generation was not certified in this follow-up. Existing native/HTTP
protocol fixtures exercise those paths; OpenRouter route/content quality and
provider availability remain external. Tiny local contexts with essential coding
tools/text can still legitimately reject an image. The user can explicitly crop,
shorten context, adjust Runtime or select another model; none happens silently.
