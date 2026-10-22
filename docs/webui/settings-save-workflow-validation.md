# Settings staged save workflow

Agent and Models now use category-local in-memory drafts and the same reusable
Discard / Save changes bar. Per-field Review buttons are removed, including
fallback and image-service actions. Drafts survive category changes, metadata
refreshes and main-page navigation during the current browser session. Refreshing
the whole document or signing out clears these private drafts; they are never
written to browser storage.

Appearance retains live preview; Discard restores the last applied appearance instead
of the default palette. Apply remains device-local. Account password changes and
Memory operations retain their existing operation-specific behavior. Library,
Integrations and execution-time tool approvals are unchanged.

## Persistence and failure behavior

- The reusable draft module at the start of `static/management.js` owns draft
  baselines, comparisons, conflict decisions, security confirmation, sequential
  submission, exact receipt polling and bars. It loads before both consumers.
- Agent adapters use the existing field revision in `setting-save`. Models use
  existing `defaults-save` expected values and the image-service revision. Image
  endpoint/enabled edits share their existing one settings effect; its two changed
  controls still count separately. Role/fallback saves remain independent.
- `/api/v1/library/review` prepares the same bounded immutable backend snapshot.
  The frontend submits it without a generic review modal for ordinary settings.
  CSRF, owner/control checks, compare-and-set writes, workers and resource fences
  remain in force. No permissions backend or new authorization mode is added.
- The existing discard endpoint can release a settled Settings preparation token
  after a terminal outcome. It cannot cancel running work, erase durable receipts,
  release unknown fences, affect another browser owner or discard other domains'
  accepted operations. This keeps the existing 16-snapshot bound while allowing
  a category with more than 16 changed fields to save sequentially. Exact operation
  status remains readable after its preparation token is released.
- Fields save sequentially. The bar reports individual progress. The first failure
  stops the batch: confirmed earlier successes stay saved; remaining drafts stay
  editable. This is **not** a transaction spanning multiple API calls.
  Restrictive approval changes precede tool enabling, so enabling with a staged
  Ask first policy cannot temporarily use an older Automatic policy.
- Each completed receipt is followed by a fresh settings read before advancing its
  baseline. A failed read retains the receipt and draft. Known URL normalization
  is compared against that read; an unexpected final value becomes a conflict.
- A refresh does not silently rebase a dirty field changed elsewhere. Inline
  **Use saved value** and **Keep my change** actions resolve it explicitly. Discard
  restores the latest confirmed backend read. A concurrent change after snapshot
  preparation is still rejected by the backend writer.
- Failed/lost submission acknowledgements retain the exact request ID and snapshot.
  **Check save status** uses the exact operation endpoint, independent of the
  bounded recent Activity list. If admission never happened, retry uses that same
  snapshot and ID. There is no automatic new mutation to recover an uncertain save.
- Requests and confirming reads have a 30-second frontend bound. An operation
  still running after bounded polling remains pending. Neither Discard nor a new
  Save can erase an unconfirmed receipt. The Activity feed and existing resource
  fences remain authoritative for unknown outcomes.
- Models' existing **Check saved state** recovery uses its witnessed recovery
  operation, without replaying the save, contacting a model, or opening a generic
  review. An uncertain recovery retains its own receipt. Unknown Agent outcomes
  remain fenced for local inspection; no browser recovery contract is added.
- Signing out clears drafts and rejects stale UI updates. Accepted backend work
  continues under its existing lifecycle.

## Confirmations and layout

Ordinary changes, including restrictive tool policies and disabling access, save
directly. A focused access confirmation lists the exact settings for tool enabling,
Deny → Ask first/Automatic, Ask first → Automatic, Exa fallback/page-reader
activation, and Vision/image-service activation or an enabled image endpoint
change. The copy describes skipped prompts or the image/service data route and
states that independent protections remain. Cancel preserves the drafts.

On desktop, the shared bar stays sticky inside its category content. Through
850px, the same DOM controls move to an application-level dock outside the cards'
container contexts, spanning the main application area (the full viewport on
phones). Measured dock/navigation/visual viewport sizes position it above the
bottom navigation or keyboard and reserve scroll padding. It disappears when
clean, keeps 44px actions, wraps on phones, and bounds long status/conflict text.
The mobile Theme Apply/Discard controls share this dock only while their preview
differs from the saved appearance. Desktop Theme controls follow the same dirty-only
visibility rule and retain their existing placement. Details:
`mobile-settings-layout-validation.md`.
Agent and Models capture each live disclosure's open state before replacing its
DOM, preserving fast tab changes even if a native toggle event is still queued.

## Validation

All tests use temporary config/data roots; no owner profile, inference, external
provider, commit or push is involved.

- `node scripts/webui_settings_drafts.test.cjs`: JSON draft copies without
  structuredClone, draft undo/discard, explicit
  conflict resolution, field-local partial success, unconfirmed locks, ordered
  fallback comparisons, category isolation, matching external writes and security
  warning classification.
- `.venv/bin/python scripts/webui_settings_save_smoke.py`: real temporary host and
  Chrome; Tools & Permissions first, save/discard/navigation, security cancellation,
  category isolation, partial rejection, lost acknowledgement, failed confirming
  read, bounded hung response, original-ID retry before admission, backend CAS
  rejection after preparation, a real witnessed unknown-save recovery, batches
  over 16 edits, restrictive-policy ordering before tool activation, logout race,
  light/dark security dialogs, and sticky bar geometry at 320, 390, 768 and 1440px.
- `.venv/bin/python scripts/webui_settings_smoke.py`: 162 light/dark category and
  viewport combinations across password/bootstrap hosts, 320–2560px; natural
  heights, width/overflow, category and disclosure keyboards, role icons, history,
  staged Agent saves, Appearance Discard/Apply and existing Memory confirmations.
  The regression blocks `/settings.js` and removes structuredClone before any
  page script runs, verifying initialization through existing assets.
- `.venv/bin/python scripts/webui_model_defaults_smoke.py`: real temporary local
  metadata HTTP servers, verified role choices, catalog changes/failure, staged
  Models discard/save, eight light/dark responsive cases, stale logout response;
  Vision activation confirmation and ordered fallback saves; zero inference calls.
- `.venv/bin/pytest tests/unit/test_library_management.py
  tests/unit/test_browser_tools.py tests/unit/test_web_management.py
  tests/unit/test_web_media_settings.py
  tests/unit/test_webhost.py::test_webhost_markdown_assets_are_local_pinned_and_keep_csp -q`:
  **72 passed**, covering settled snapshot capacity, retained receipts and unknown
  fences, existing Library behavior, availability/permissions, stale settings,
  model compatibility, field-level concurrency, exact image-settings recovery
  and the existing CSP, MIME/security headers and Settings asset bootstrap.
- Focused Ruff, Python compilation, JavaScript syntax and whitespace checks.

This is focused regression coverage, not the full repository or physical-device
suite.

## Running-host compatibility correction

The initial implementation required `/settings.js`. The actual managed host was
still running an older Python route allowlist: `/` and `/management.js` returned
200, while `/settings.js` returned 401. The new HTML therefore referenced a script
the running host could not serve, preventing management initialization. Fresh-host
tests missed this. The draft module now lives in the longstanding management
asset; HTML does not request a new route and does not need a host restart for
JavaScript initialization. A restart is still needed to load changed Python
behavior such as settled-snapshot cleanup.

A read-only Chrome check on both actual loopback and LAN sign-in pages verified
that the draft store, Agent/Models controllers and save bars initialize, that
draft/discard round trips work, and that no JavaScript exception occurs. It did
not sign in, modify the owner profile or read chats. Chrome exposed structuredClone
on both origins; removing that unnecessary dependency is a compatibility measure,
not the diagnosed cause of the live failure.
