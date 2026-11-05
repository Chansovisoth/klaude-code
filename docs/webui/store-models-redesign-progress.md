# Store / Models redesign implementation progress

## Slice 1 — entry points and honest file state (2026-10-29)

Implemented from `klaude-store-models-ux-redesign.md`:

- Download review cancellation retains the model detail, exact variant, history
  context and initiating control focus. Accepted transfers open Downloads.
  Unconfirmed submission still directs the user to Downloads to check status.
- Exact-reference review cancellation restores the input dialog and its draft.
- Opening a detail cancels delayed search navigation so a fast selection cannot
  be replaced by the pending search callback while preparing its review.
- Image file badges say Downloaded. Inventory explicitly says Setup not checked;
  detail explains that service visibility, components and runtime need checking.
  Its enabled Configure model action opens Image generation settings. It does
  not infer a recipe, load weights or save defaults.
- Connections has visible Add connection, Test and Manage actions. Manage opens
  the existing keyboard-accessible menu; current-chat edit restrictions are
  explained in the row. Actions have at least 44px targets and wrap beneath the
  content on phones, remaining alongside content on desktop.
- Connected models is accessible from the overview. Connections still precedes
  Defaults and Image generation, preserving the established workflow.
- Check service connection clarifies the capability-only test. Download control
  accessible names/tooltips distinguish Stop and discard partial (image files)
  from Remove from history. Ollama Stop retains its own semantics.
- Failed and unconfirmed download rows expose a message inline, with extended
  details still available through Info.

Existing reviewed operations, file receipts, dependency downloads, pause/resume,
load/save separation and authorization remain in use. No new backend route or
database state was added by this slice. Existing uncommitted implementation work
was retained. No commit, push, production restart or real model operation was
performed for this slice.

## Validation

- `scripts/webui_image_model_store_smoke.py` passed at 320/390/768/1440px,
  including Ollama and image review cancellation, retained variant/focus,
  exact-reference draft restoration, All-runtime browsing, detail reload,
  two small real fixture transfers, pause/resume and image configuration labels.
- `scripts/webui_model_settings_smoke.py` passed at 320/390/768/1440px in
  light/dark layouts, including visible Manage menu/Test, Add, credentials,
  reviewed enable/remove, role drafts, image testing and Connected models.
  Additional assertions check connection action bounds and minimum touch size.
- Both browser runs reported zero console errors. Desktop and phone Connections
  screenshots were visually inspected.
- JavaScript syntax, Expressive source/bundle consistency and whitespace checks
  passed. Image Store smoke Ruff passed. Settings smoke retains four pre-existing
  E501 findings in its older image-capability checks; newly added lines pass.
- Initial sandbox execution could not open loopback sockets. Browser fixtures
  were rerun with permitted local socket access. Early assertions were corrected
  to focus scripted buttons and await menu settlement; the Store walkthrough
  also exposed the delayed-search race fixed above.

Evidence: `/tmp/klaude-ux-p0-store.log`, `/tmp/klaude-ux-p0-settings.log`,
`/tmp/klaude-image-model-store-evidence/` and
`/tmp/klaude-model-settings-evidence/`.

These are isolated fixture checks, not a full repository test run or a fresh
production walkthrough. Static asset changes are available on browser reload;
this does not activate pre-existing uncommitted backend work in a running host.

## Slice 2 — persistent setup drafts and readiness checks (2026-10-29)

The Stable Diffusion picker now offers Save setup after choosing a recipe and
components, including incomplete selections. Saved setups appear when reopening
that server's picker and survive browser reloads. Check setup refreshes metadata
and restores the exact selection without loading a model or changing defaults.
Forget saved setup removes only the saved selection.

`image_setups.py` owns versioned, immutable draft identities derived from the
normalized endpoint, recipe metadata, selected opaque file IDs and their reported
categories/names. The bounded private inventory uses the existing file lock and
atomic writer; duplicate saves reuse the same identity. Changed selections create
new identities. The inventory permits 50 drafts and at most 8 MB; users can forget
old drafts. These are metadata identities, not verified weight-content hashes or
download authorizations.

Readiness separates recipe validity, missing components/alternatives, selected
file visibility, exact loaded runtime, matching enabled saved default, pending
load receipts, compatibility and inference evidence. Recipe changes and missing
files block the restored load action. Unreachable services invalidate previous
success. Unknown load receipts remain fenced and use the existing recovery flow.
Architecture support and actual image generation remain explicitly unverified.
Existing load review still rechecks the current catalog/runtime before execution.

The owner/admin/Origin/CSRF-protected `image-setups` endpoint supports explicit
save/list/check/forget actions. `image_setup_drafts` gates this UI on older hosts.
No automatic transfer/load/default-save action is added. This is the foundation
inside the existing picker, not yet the shared Store/composer setup route or a
pre-download artifact plan.

Validation:

- 19 focused setup/selection/dependency tests passed, covering restart persistence,
  duplicate saves, changed recipes, missing files, service outages, independent
  runtime/default state, unknown receipts, malformed selections, tampering,
  symlink rejection, capacity, draft-only forgetting and HTTP authorization.
- Six non-network setup checks passed again after enforcing the inventory byte
  limit. No production preferences or model files were modified.
- Native picker browser checks cover saved selection across reload, restored
  component identity, load/default separation, missing-file blocking, responsive
  layouts at 320/390/768/1440px, independent old-host gating and forgetting drafts.
- The dependency browser regression passed with two reviewed component transfers,
  concurrent workers, independent pause/resume, auto-filled component slots and
  zero automatic loads. It reported zero console errors.
- JavaScript syntax and focused Ruff passed. Focused mypy with imported modules
  silenced passed for the new service; normal import-following mypy reported an
  existing missing `files` annotation in `skill_store_operations.py:168`.

Evidence: `/tmp/klaude-setup-tests.log`, `/tmp/klaude-setup-browser.log`,
`/tmp/klaude-setup-dependencies.log`, `/tmp/klaude-sd-model-picker-evidence/`.
This backend capability requires a WebUI host restart and browser reload to
activate. The production host was not restarted during this work.

## Slice 3 — Store and composer setup handoff (2026-10-29)

Store's Configure model and Choose or resume setup actions now enter a contextual
Image generation handoff and open the existing picker when a service endpoint is
available. The image composer offers Set up a model through the same path. The
handoff identifies the originating Store model and provides a Return action.
It does not guess a server file or recipe from the Store filename.

Selecting/saving a setup retains its immutable ID in `models-setup`. After reload,
Choose or resume setup checks that exact selection again. The source URL and
navigation context survive in the tab's history; returning to Store restores its
detail/variant, and detail Back returns to inventory rather than reopening setup.
Composer prompt and options are captured in memory for the same-page round trip,
never in URL/history/storage. Reload retains the setup/return path but opens an
empty composer; the handoff explains this limit. Sign-out clears the active
handoff and in-memory callback.

Missing service endpoints focus URL configuration. Capability gating retains
older-host guidance and avoids unsupported saved-setup requests. Existing dirty
settings navigation checks still apply before returning. Accepted transfers,
runtime-load reviews and Apply changes keep their independent ownership.

Validation uses the extended isolated Store and native picker browser fixtures:
Store detail return across reload, missing-endpoint draft, inventory Back,
composer prompt/seed preservation, exact setup reopen after reload, empty prompt
after reload, unchanged defaults/load count, and phone/desktop handoff bounds.
Evidence: `/tmp/klaude-setup-route-store.log`,
`/tmp/klaude-setup-route-browser.log`, and handoff screenshots under
`/tmp/klaude-sd-model-picker-evidence/`.
Both walkthroughs passed with zero console errors; focused Ruff, JavaScript
syntax, CSS bundle consistency and whitespace checks passed.
The Store walkthrough exposed and fixed the detail Back/setup history loop.
No backend contract change or production restart was added in this slice;
saved setups still require the previous slice's backend capability.

## Slice 4 — pre-download artifact plans (2026-10-29)

Store image detail now offers Plan installation after choosing an exact variant.
The user explicitly chooses Selected file only, FLUX.3 Klein or FLUX.3 Klein Base;
no architecture is inferred from names. Preview resolves the primary and curated
companions before any download. It shows pinned source links, published exact
bytes, SHA256, commit revisions, destination categories and full-plan total size.
Curated profiles place the primary in diffusion_models, the encoder in
text_encoders and the decoder in vae. Existing direct downloads remain available.

The bounded private plan inventory retains the 50 most recent immutable metadata
selections. `models-plan` restores the plan on reload without refreshing its
source metadata. Rebuild plan explicitly resolves new evidence. File-presence
and free-space observations are dated; existing destinations are unverified,
full-file totals do not deduct them or partial data, and disk is not reserved.
Compatibility, remote directory access and memory requirements remain unchecked.

Each Install has its own existing reviewed download. Before review, the current
metadata and local destination identity must match the plan's exact fingerprint,
including source revision/hash/size, root inode/device and destination category.
Changes reject review and require rebuilding; the backend never silently replaces
an artifact. Accepted transfers keep their existing pinned worker/resume contract.
No file, model runtime or image default changes merely from creating a plan.

The existing recent-download projection now includes an opaque exact-artifact
fingerprint without exposing host paths. Plan rows match that fingerprint to child
receipts and expose independent progress, Pause, Resume/Retry, Stop and discard
partial, Check status and transfer details. Completed receipts are labeled as last
transfer evidence, not current readiness. Missing recent receipts do not prove a
file is absent now. Accepted plan transfers stay in the plan; View Downloads and
Return to installation plan preserve the exact plan/variant across reloads.
Configure model enters the previous slice's explicit service/setup handoff.

The new administrator/Origin/CSRF-protected image-install-plans endpoint accepts
create/get only. The `image_install_plans` capability hides the feature on older
hosts. There is no grouped approval, automatic model load, default save or
architecture certification.

Validation:

- 50 focused install-plan and image-download tests passed, including drift of
  revision/hash/size/root, explicit categories, metadata-only persistence,
  bounded retention, malformed metadata/tampering, existing-file protection,
  HTTP CSRF, exact child receipt matching and existing worker/recovery regressions.
- The new plan browser walkthrough passed at 320/390/768/1440px: saved plan
  reload, exact totals/categories, cancelled review/focus, concurrent companion
  transfers, independent pause/resume, Downloads return across reload, primary
  transfer, unchanged image settings and old-host capability gating. Phone and
  desktop screenshots were visually inspected; controls wrap and align right.
- Existing Store and native picker/composer walkthroughs also passed at those
  widths. All three runs reported zero console errors.
- Browser checks exposed and fixed two state races: an initially empty download
  history needed to invalidate the detail rendering cache, and setup handoff was
  starting a competing settings read. The handoff now waits for the latest
  settings read without cancelling it. Tests wait for field readiness before
  editing drafts and dispatch capability events with their normal snapshot data.
- Focused Ruff, JavaScript syntax, CSS bundle consistency, whitespace checks and
  new-service mypy (imports silenced) passed. These are focused fixture checks,
  not a full repository suite or live-production validation.

Evidence: `/tmp/klaude-install-plan-tests.log`,
`/tmp/klaude-install-plan-browser.log`,
`/tmp/klaude-install-plan-store-regression.log`,
`/tmp/klaude-install-plan-picker-regression.log`, and
`/tmp/klaude-image-install-plan-evidence/`.
This backend capability requires a host restart and browser reload. The production
host was not restarted, and no real model operation, commit or push was performed.

## Slice 5 — connect plans to server setup drafts (2026-10-29)

Configure model carries the current matching installation plan into the image
picker, including across reloads. Check planned files refreshes the server catalog
and compares category plus exact planned relative path (optionally beneath a server
prefix). It reports one candidate, ambiguous matches or a path not visible. Server
metadata does not verify file contents, hashes or remote directory equivalence.

Use visible files explicitly fills the curated recipe's matching component slots.
Absent/ambiguous components stay empty for manual selection. File-only plans use
the ordinary primary-file and recipe chooser. Nothing is selected automatically
on entry; loading retains its existing exact review. Refreshing invalidates stale
plan evidence, and service failures invalidate the catalog. Missing/evicted plans
allow choosing files without the plan.

Save setup can retain the originating immutable plan ID. This changes the new
selection identity while preserving all legacy identities and drafts. The link
records provenance; users may edit the recipe/files and it does not assert those
edits are compatible or equivalent to the plan. Reopening a linked setup retains
its source context and offers a new server check. Return restores Store's exact
plan/variant. Older hosts gate the bridge with `image_install_plan_setup`.

Validation: 25 focused plan/setup/selection tests passed, including missing and
ambiguous server paths, category agreement, unverified content, optional linked
identity and unchanged legacy identity. The extended plan browser walkthrough
passed at 320/390/768/1440px, including explicit candidate adoption, linked setup
save/reload, unchanged runtime/defaults, missing-file rescan, blocked stale loading,
and detaching an unavailable plan to the manual chooser. The existing native
picker/composer regression also passed at those widths. Both reported zero console
errors. Focused Ruff, JavaScript syntax, source/bundle consistency, whitespace and
mypy (imports silenced) passed. These are fixture checks, not a full suite or
production validation. Evidence: `/tmp/klaude-plan-setup-tests.log`,
`/tmp/klaude-plan-setup-browser.log`, `/tmp/klaude-plan-setup-picker.log`.
The production host was not restarted; fixtures perform no real model operations.

## Slice 6 — shared readiness and saved setup inventory (2026-10-30)

Implemented the next two priorities: a shared image readiness projection and a
saved plan/setup inventory. Store detail shows matching readiness and Continue
setup/Check setup; Installed model rows reuse its headline. Saved image setups
appears below image inventory, in Image generation settings and in the composer.
It lists saved server selections and installation plans with their link, server,
last-check timestamp, recent child transfer status, inline failures and Continue
setup / Check setup / View downloads actions. Search is local, pages contain ten
rows and metadata sources retain their existing 50-item bounds.

The image-readiness endpoint lists local metadata and receipts only. It never
fans out to saved servers. Explicit Check setup refreshes just the selected server
and persists a bounded observation. Picker Save/Check also contributes evidence
through a best-effort cache that cannot change its existing save outcome. All
cached statuses are labeled Last check with a date; settings changes invalidate
those observations. Current transfers and load fences override cached success.
Latest child receipts prevent an old paused attempt from masking a completed
resume. Partial source failures preserve other inventory results.

Store matching requires the selected primary's category/path to correspond to the
originating plan. Editing a setup to use another primary cannot borrow the plan's
readiness. Server path matching remains metadata evidence, with compatibility and
image-generation verification explicitly unverified. No Ready to generate claim
is inferred from file presence, transfer completion or connection capability.

Continue setup carries the exact saved setup/plan and server context into the
existing picker. A different endpoint is staged as a service draft; conflicting
service edits are retained with guidance to apply/discard them first. Loading and
Apply remain separate. Settings returns to its source screen; composer return
preserves prompt/options in memory. Older hosts gate the inventory through
image_readiness_inventory, and sign-out clears browser copies.

Validation: 24 focused readiness/setup/plan tests passed, including metadata-only
listing, explicit checks, unavailable service replacement of prior success,
settings invalidation, exact latest-receipt precedence, unknown load fences,
partial inventories and HTTP CSRF protection. The extended inventory/plan
walkthrough passed at 320/390/768/1440px, covering shared Installed status,
metadata refresh, explicit checks, download links, exact setup resume, search focus,
Settings return, composer draft retention, capability gating and sign-out cleanup.
The existing native picker/composer walkthrough also passed at those widths. Both
reported zero console errors. Phone/desktop inventory screenshots were inspected.
Focused Ruff, mypy with imports silenced, JavaScript syntax, CSS bundle consistency
and whitespace checks passed. These are fixture checks rather than a full suite
or a live-production validation. Evidence: `/tmp/klaude-readiness-tests.log`,
`/tmp/klaude-readiness-plan-browser.log`, `/tmp/klaude-readiness-picker-browser.log`,
and readiness screenshots in `/tmp/klaude-image-install-plan-evidence/`.
No production restart, model operation, commit or push was performed.

## Slice 7 — guided Connections setup (2026-10-30)

Add connection now retains one editor through disabled-definition review, credential
review, explicit connection test and enable review. Completed definition fields
collapse into an expandable summary so phone users can reach the next stage.
Supported adapters come from the backend; routing and authentication remain
explicit. Credential fields retain their native input and shared shape masking.
No secret is carried between reviews, put in navigation state or read back.
Cancelled definition reviews retain the form; cancelled credential reviews require
re-entry. Tests report reachability/model count without generating a response.

Disabled entries expose Continue setup. Exact generated connection IDs from Add
reviews and accepted request IDs preserve the workflow across reloads without
matching names. The editor follows each receipt and refreshes saved inventory;
unknown outcomes remain blocked and use the existing exact witnessed recovery.
Accepted work is not replayed automatically. Existing Edit/Credential/Enable/Remove
management actions and current-chat restrictions remain available. The feature is
gated through model_connection_setup for older hosts.

The native editor fills phone screens, retains the shared desktop dialog, keeps
Close at top right and actions at bottom right, and advances focus to the next
credential/test/enable control. Closing clears route state synchronously to prevent
late inventory reads reopening the editor. One existing smoke menu dismissal now
tolerates a menu that a settled refresh has already closed.

Validation: 12 focused connection tests passed, including exact generated Add
identity, write-only credential publication, current-chat/CSRF/stale-review guards,
credential drift and existing unknown-outcome recovery. Guided and full Settings
browser walkthroughs passed at 320/390/768/1440px with zero console errors. The
guided check covers retained cancellation drafts, exact ID reload, credential
privacy and re-entry, explicit Test/Enable, disabled-connection resume, minimum
touch targets, unchanged current-chat model, Done route cleanup and sign-out.
It also drops an acknowledgement after a real fixture acceptance and verifies
receipt inspection with exactly one submission. Phone/desktop screenshots were
inspected. Focused Ruff, JavaScript syntax, CSS bundle consistency and whitespace
checks passed. The broader Settings script retains its pre-existing unrelated
line-length findings; changed code passes focused checks. These are fixture checks,
not a full repository suite or live-production validation. Evidence:
`/tmp/klaude-guided-connections-tests.log`,
`/tmp/klaude-guided-connections-browser.log`,
`/tmp/klaude-guided-connections-settings.log`, and
`/tmp/klaude-connection-setup-evidence/`.
No production restart, real provider mutation, commit or push was performed.

## Slice 8 — one approval for a pinned install plan (2026-10-30)

Store image plans now offer Install remaining files when the host advertises
`image_install_plan_group`. One native review names every selected file and
destination and shows the full byte total. Review checks the immutable plan,
each current source/destination identity, absence of transfer history and
full-file free space before approval. Existing per-file Install remains.

Approval derives stable 32-character child request IDs from its request ID,
plan ID and file slot. Each child uses the existing witnessed image download
journal, worker, progress and independent Pause/Resume/Stop/Check controls.
A partial dispatch lists accepted and unsubmitted children; submitting the same
approval again reads existing child receipts and starts only missing children.
The UI refreshes Downloads after an accepted or uncertain submission and does
not automatically repeat a download. Group approval is not a model load or
image-default save. Files still need server mapping and setup before selection.

Validation: 13 focused install-plan tests passed, including real local-fixture
transfer, duplicate approval and a simulated failure between two child
admissions. The existing plan browser walkthrough passed at 320/390/768/1440px,
including group review/cancellation, one approval for two companions,
independent Pause/Resume and setup handoff, with zero console errors.
JavaScript syntax and whitespace checks passed. No production restart, real
model download, commit or push was performed.

## Slice 9 — clearer image model selection (2026-10-30)

Settings > Models > Image generation now puts Image model, its saved-default
or draft state and saved setups before Service connection. An unset server URL disables the
picker with a connection prompt. The shared image picker shows the current loaded
server model first, saved setups second and downloaded files requiring setup
last. Rows expose Select, Continue or Set up actions. Choosing a raw file opens
its own recipe/component screen with a Back action, keeping technical choices
out of the first screen. Search covers visible setup and file names. The picker
fills narrow phone screens and retains its native dialog, focus and keyboard
behavior. Nothing labels a downloaded file ready to generate.

The native picker walkthrough passed at 320/390/768/1440px, including reviewed
load, independent Apply, empty catalog and older-host states, with zero console
errors. First-screen screenshots at 320/390/1440px were inspected. The plan
handoff and Models settings walkthroughs also passed at those widths with zero
console errors. JavaScript syntax, CSS bundle and whitespace checks passed.
No production restart, real generation, commit or push was performed.

The proposed managed-runtime path and its verification gates are in
`docs/webui/managed-image-runtime-plan.md`. ComfyUI is now the user-selected
local, free/open-source integration target. The first implemented bundle is
described in Slice 11 below.

## ComfyUI bundle decision (2026-10-30; design only)

The user selected ComfyUI and delegated bundle-installation decisions. The
implementation contract is `docs/webui/comfyui-bundle-installation-design.md`.
Klaude will maintain immutable complete-bundle recipes, manage an isolated
pinned runtime and shared verified components, and present one Install review.
Installed bundles become ordinary picker choices after installation checks;
the first explicit Generate records actual inference evidence. Runtime setup,
custom supported architectures, recovery, repairs, updates, removal and scoped
generation ownership are defined in that document. The first implementation
gate is one SD1.5 bundle installed, selected and genuinely generated on the target
machine. This decision adds no runtime adapter, downloads, enabled provider or
live-generation validation. Documentation links and whitespace were checked.

## Slice 10 — ComfyUI preflight and control graph (2026-10-30)

Implemented the bounded read-only core probe, private application/worker command,
development probe script and fixed SD1.5 workflow/control-bundle metadata. Verified
the exact upstream runtime/model identities and confirmed that the existing
checkpoint's full SHA-256 matches the pinned source. A matching filename or node
schema does not certify installation or inference; result fields remain explicit.
The existing checkpoint is a reuse candidate without a duplicate transfer.

52 focused tests passed, plus focused Ruff and source mypy with imported errors
suppressed. Normal mypy traversal found unrelated existing errors in integration
and skill-store modules. The real local ComfyUI probe returned unavailable; no
runtime was installed, weights loaded or actual generation verified. Product
provider selection remains gated. Full evidence and next work:
`docs/webui/comfyui-validation.md`.

## Slice 11 — Managed ComfyUI SD1.5 end to end (2026-10-30)

Implemented the isolated hash-locked runtime installer, verified checkpoint
materialization, installed inventory, pause/check/continue controls, managed
process ownership, shared model picker and reviewed image defaults. Advanced
image service retains the legacy providers. One fixed owned graph supports
text-to-image, exact UUID receipts, scoped cancellation and Library publication.
Unknown work never replays. An interrupted repair cannot advertise an old bundle
as installed, and unfinished jobs prevent engine replacement.

The installer and real 512px generation passed on GTX 1650 4 GB. A real browser
walkthrough cancelled an install review, chose the bundle without saving,
selected it in the shared picker, applied/reloaded its defaults and generated
another real image into the isolated Library. Responsive evidence covers
320/390/768/1440px. Production services/defaults remain unchanged.
Full validation and limits: `docs/webui/comfyui-validation.md`.

## Slice 12 — Custom checkpoints and model lifecycle (2026-10-30)

Implemented complete safetensors family detection, direct one-review Store
installation, adoption of witnessed downloads, immutable multiple-model inventory,
shared assets and runtime reuse. The normal picker lists managed models; legacy
service models remain an explicit advanced destination. No image model stages
clearing the default and disabling generation. Model removal retains Store
originals, shared weights, runtime and Library outputs, with exact checked
recovery of interrupted cleanup. Partial drafts retain an explicit repair path.

159 focused tests passed. Real SD1.5 Store adoption and pinned-source browser
install/select/Apply/reload/generate/remove flows passed at 320/390/768/1440px,
with no JavaScript errors; legacy advanced setup also passed. SDXL is implemented
as a device-unverified recipe, not a claimed success on the 4 GB GPU. Evidence:
`docs/webui/comfyui-validation.md`.

## Remaining work

Runtime version updates/removal, platform-specific builds and additional model
architectures remain outside the managed checkpoint recipes. The user's existing
Unsloth FLUX 3 GGUF still requires its own maintained loader, component/workflow
and device validation; `docs/webui/comfyui-gguf-gap.md` records that exact gap.
Legacy plans/setups retain their identities. Broader Store navigation and arbitrary
workflow/custom-node installation remain separate from this checkpoint lifecycle.


## Package manager layout revision (2026-10-30)

Store now has a dedicated sidebar workspace, explicit category navigation and a
phone location chooser. Models uses responsive model cards, and Image generation
centers the selected model. The reference review, implemented information
architecture and focused browser evidence are recorded in
[Store package manager redesign](store-package-manager-redesign.md).
