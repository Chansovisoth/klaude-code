# Model Store and Image Studio implementation

Date: 2026-10-25. Implements reviewable paths from
[klaude-model-store-image-studio-codex-handoff.md](klaude-model-store-image-studio-codex-handoff.md).
This records the initial implementation slice; later live verification is recorded
below. See [completion-validation.md](completion-validation.md) for the subsequent
live catalog and Models settings work and current deployment evidence.

## Delivered behavior

**Models → Model Store** has Discover, Top charts, Categories, Installed,
Downloads and Connections. Discover combines one large feature and two companion
cards, original CSS compositions, existing licensed local model marks, use-case
search and overlapping categories. Cards open native details with exact variants,
verified snapshot metadata and official source/license links. Mobile features
scroll horizontally; section controls support arrows/Home/End. Store section,
query, category and detail use URL/history state. Leaving Models removes its URL
parameters. The existing current-chat summary, Model Defaults link and configured
cloud/API catalog remain available; Connections retains its original activation,
search and pagination. Installed native models have 20-row pages.

The curated catalog contains Qwen 3 (`0.6b`, `4b`), Qwen 2.5 Coder (`7b`) and
Gemma 3 (`4b`). Its visible verification date applies to the bundled facts.
Catalog facts are not advertised as fresh server declarations. Exact installed
activation still uses the existing capability/revision-checked runtime action.
Installed pagination reuses `updateDomainPager` with the shared chevron buttons,
numbered pages, selected-page state, compact responsive spacing and `···` gaps.
Models without verified Klaude tool support can be rejected by that action.

Installed models come from the shared native Ollama manager. A private cache is
keyed by connection/credential revisions and retains its original checked time.
Unavailable servers return visibly stale inventory, including after browser or
host restart. A stale cache cannot authorize mutation: preparation and the worker
both need fresh native metadata. Discovery remains independent of native-server
availability. Hardware fit/context limits remain explicitly unverified.

Local owner browsers can review exact native-endpoint pulls and deletion.
Review shows the endpoint's configured display name and exact tag, and starts on
Cancel. Deletion uses the existing loaded-model/digest/role/session checks again
at the worker effect boundary. The existing pull consumer supplies stage and
**current file** bytes; no overall percentage, ETA or synthetic preview is added.
Download completion requires terminal success plus fresh installed inventory.
Neither completion nor browsing changes conversation/default roles.

Downloads combines the existing private journal with small private target records,
not a second downloader/job database. At most 30 recent native operations are
projected, and a currently fenced native request remains discoverable even when
older than the recent-receipt scan. Live progress survives browser navigation and
reload while its owning host is running. After host loss, the receipt conservatively
becomes unknown. Cancellation kills/reaps only the owned worker and explicitly
leaves remote transfer/partial-layer cleanup unconfirmed. Check outcome performs
no pull: it checks the exact endpoint revisions and observed requested inventory
against a private HMAC witness recorded before dispatch. Altered adjunct targets
cannot release a fence. A missing requested final state remains fenced.

Profile operation admission atomically excludes native model mutations from
other browser operations. Hosted active/queued conversations block model writes;
The original gate blocked new hosted turns/runtime changes during any active or
unknown model work. The 2026-10-26 refinement scopes chat independently of unrelated
pulls while retaining mutation fences and native deletion protection; see
`../chat-admission-validation.md` for current behavior and validation.
The shared terminal manager adapter also rejects new mutations behind the browser
fence, and the existing endpoint lock continues to serialize native effects.
These additions do not claim atomic coordination with every legacy/direct caller
or every independent terminal inference path.

**Library → Generated → Create → Image** now contains Image studio. Its existing
Research tab and creation/review flow remain. The studio shows the saved
stable-diffusion.cpp service/model, checks current capabilities, preserves its
prompt draft and offers 1:1 (512×512), 3:2 (768×512), 2:3 (512×768) and 16:9
(1024×576). Unsupported presets are disabled against the observed bounds.
Dimensions stay visible. A native Advanced disclosure exposes only implemented
width, height, steps and seed controls. Reset retains the prompt and resets local
options. Preparation and admission reuse existing exact service/model/capability
validation. Seed is additive; old browser requests without seed keep random seed.

Generate image opens the existing explicit review. Jobs continue to use existing
image receipts, cancellation, recovery, private provenance and Generated artifacts.
Outputs retain Open output/preview and gain Download plus Generate again when
this browser retains the original draft. At most twenty draft snapshots stay in
memory. Reload clears them; Generate another uses the current draft instead of
exposing historical private prompts through a new API. Sign-out clears drafts.
Image output recovery never resubmits generation.

## Capability/source investigation

The official [Ollama documentation index](https://docs.ollama.com/llms.txt) and
[API introduction](https://docs.ollama.com/api/introduction) were inspected.
No documented stable public discovery-catalog API was established. The
[public search page](https://ollama.com/search) is a website with filter/ranking
presentation, not a contracted JSON schema. The published
[terms](https://ollama.com/terms) restrict automated access without permission.
Accordingly this slice ships a bounded editorial snapshot and official outbound
links. It does not scrape, poll or copy publisher artwork. A live catalog adapter,
verified charts, freshness collections, size/capability filter controls and
broader catalog coverage remain follow-ups, not simulated features.

Snapshot sources checked on this date:

- [qwen3:0.6b](https://ollama.com/library/qwen3:0.6b): 752M, Q4_K_M, 523 MB.
- [qwen3:4b](https://ollama.com/library/qwen3:4b): 4.02B, Q4_K_M, 2.5 GB.
- [qwen2.5-coder:7b](https://ollama.com/library/qwen2.5-coder:7b): 7.62B,
  Q4_K_M, 4.7 GB.
- [gemma3:4b](https://ollama.com/library/gemma3:4b): 3.88B plus 420M projector,
  Q4_K_M, 3.4 GB. Its vision label means image input.

The current upstream [Ollama generate handler](https://github.com/ollama/ollama/blob/main/server/routes.go)
explicitly rejects image-generation models. A bounded read-only check of this
machine's configured server reported Ollama **0.33.3**, **27 installed models**;
none of the first **20** inspected models declared `image` output capability.
This did not load, download, generate or switch any model. The configured image
service was disabled. Production stable-diffusion.cpp generation was therefore
not exercised in this run. The existing adapter's
[documented native API](https://github.com/leejet/stable-diffusion.cpp/blob/master/examples/server/api.md)
and repository capability validation remain authoritative. No Ollama or other
image-output provider was added or implied to work.

The [md3.io Card reference](https://md3.io/docs/components/card/) guided editorial
containment, adapted to existing Klaude colors, expressive radii and native
controls. No additional component package, artwork service or logo system was
installed. Existing `AIIcons` supplies local licensed marks. CSS changes were
bundled through `scripts/bundle_webui_expressive.py`.

## Contracts and files

| Contract | Purpose |
| --- | --- |
| `GET /api/v1/models/store` | Dated bounded editorial catalog; local-mutation availability |
| `GET /api/v1/models/installed?connection=ID` | Allowlisted native installed inventory/cache |
| `GET /api/v1/models/downloads` | Bounded journal receipts, display targets, real progress/status |
| Existing `POST /api/v1/library/review` and `/submit` | Add fixed `model-pull`/`model-delete` operations |
| `POST /api/v1/models/cancel` | Stop exact owned native pull request |
| `POST /api/v1/models/reconcile` | Observe witnessed requested inventory without replay |
| `GET /api/v1/library/image-capabilities` | Check only the saved opt-in image service; allowlisted evidence |
| Existing `image-generate` review | Optional validated seed; existing requests remain compatible |

Native reads require owner authentication and a valid browser client. All effects
retain CSRF/Origin/session validation, and native mutations are denied over LAN,
including a review prepared locally and later submitted over LAN. Browser input
cannot supply endpoint URLs, roots, commands or raw worker requests. Provider
credentials use the existing private worker pipe; target records and public job
projections omit them. Public model progress/error messages are the native
manager's existing sanitized classifications.

Primary changes: application `model_store.py`, `library_management.py`,
`browser_jobs.py`, `model_manager.py`, `operation_journal.py` and
`background_worker.py`; core `ollama_manager.py` gains an optional effect-fence
callback; WebUI `host.py`, `media.js`, `management.js`, `index.html`, `library.js`,
`expressive.css`/bundled `style.css` and URL cleanup in `app.js`.
No new arbitrary worker operation family, subprocess owner or HTTP provider proxy
was introduced. Tests are in `tests/unit/test_model_store.py` and
`scripts/webui_model_store_smoke.py`. Existing model/management smoke scripts were
adapted for the retained Connections destination and explicit studio readiness.

## Validation evidence and limits

- Existing focused tests: **160 passed** for `test_ollama_manager.py`,
  `test_image_generation.py`, `test_web_management.py`, `test_library_management.py`.
- Subsequent native/journal/new lifecycle run: **56 passed** across
  `test_model_store.py`, `test_application_operations.py`, `test_ollama_manager.py`.
  Earlier test-fixture setup used a nonexistent registry `.save()` method; it was
  corrected to migrate/add before this passing run.
- The new lifecycle tests cover owner/CSRF/LAN boundaries, explicit tags,
  reviewed effects, duplicate receipts, role/loaded protection, real owned-worker
  progress/cancel, restart-visible receipts, unknown-state reconciliation,
  credential exclusion, seeded generation and atomic competing admissions.
- The dedicated Chrome walkthrough passed store browsing/categories/details,
  exact-variant reviewed pull, chat-default preservation, history, offline
  inventory, back navigation, studio presets/seed/drafts/review, fixture PNG
  generation, output preview and sign-out clearing. Light/dark layouts at
  **320/390/768/1440px**, reduced-motion/forced-color checks, zero JavaScript
  exceptions. Screenshots: `/tmp/klaude-model-store-evidence/`.
- Existing `scripts/webui_models_smoke.py` passed configured selection/dedup,
  effort controls, failures, paging, history/reload, keyboard/navigation/logout
  and legacy catalog behavior, with zero browser exceptions.
- The broad management smoke stops in its earlier Settings role-save setup
  waiting for a review at line 317; it does not reach its Generated section.
  This is not reported as a passing Research/management end-to-end run.
- Final new lifecycle run: **8 passed**, including recovery-target tampering,
  offline cache projection, exact-credential capture and competing admission.
  The final dedicated Chrome rerun also passed browser reload/receipt recovery,
  detail focus restoration with the final current-revision download action present.
- Final production mypy passed **227 source files**. Focused Ruff, JavaScript
  syntax checks, the Expressive bundle check and `git diff --check` passed.
- `make check` first stopped during collection because preexisting tests import
  `tests.*` without the repository on `PYTHONPATH`. A bounded rerun with
  `PYTHONPATH=.` progressed to roughly **40%** with no displayed failures before
  its **240-second timeout**. It is not a full-suite pass.
- Full-repository Ruff reported **54 existing style errors**, mostly long lines
  in prior WebUI scripts, including a prior static-route line in `host.py`.
  New application/test/smoke files are checked separately. No unrelated style
  work was rewritten to mask this result.

At the end of the initial slice, remaining scope included live catalog integration/verified rankings, broader catalog
curation, trustworthy device-fit guidance and supported extra image controls or
engines. Unknown native outcomes whose desired final inventory cannot be observed
stay fenced; there is no browser force-release or automatic retry. Historical
image parameters are not recovered after reload. Physical touch devices and real
weight download/deletion/generation were not exercised. The running production
host was not restarted or deployed. Existing dirty work was retained; nothing
was committed or pushed.

## Old-host route mismatch follow-up

The reported “Route not found” states came from updated static assets served by
a process that did not have the new routes. Snapshots now explicitly declare
`model_store` and `image_studio`; clients gate requests on these capabilities,
show restart/reload guidance on older hosts and retain configured Connections.
The first post-load snapshot rechecks capability availability, including after
reload. The dedicated Chrome regression covers this fallback and normal reload.

A live inspection confirmed the old host was idle and lacked these declarations.
Before the attempted controlled restart, another restart changed its process
and session identity; the identity guard stopped without sending a shutdown.
The newer host advertises both capabilities. Existing workspace, password-account
mode and LAN origin remained available. Live endpoint results are recorded below.

Authenticated live checks returned HTTP 200 for the curated catalog (3 families),
native inventory (28 installed models), download history (0 jobs), and image
capabilities (service disabled). The temporary verification login was signed out.
No model downloads, generation, credential resets or runtime changes were made.
The follow-up unit run passed 8 tests; the capability/reload Chrome walkthrough
passed at 320/390/768/1440px with zero browser exceptions.

Installed pagination follow-up: replaced the custom Previous/Page/Next row with
the existing shared numbered pager and local chevron icons. The isolated Chrome
walkthrough passed an eight-page inventory, direct last-page selection, boundary
controls, numbered-button focus retention, filter reset and matching shared
control widths at 320/390/768/1440px, with zero browser exceptions.
