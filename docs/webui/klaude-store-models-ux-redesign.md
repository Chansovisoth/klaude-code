# Klaude — Store, Models, Connections & Image Setup UX Redesign

**Review date:** 2026-10-29  
**Basis:** `store-models-ux-review-handoff.md`, documenting the current working tree of Klaude 0.2.0a4.  
**Type:** Independent UX review and proposed implementation handoff, not a live browser or repository audit.

## Executive decision

Keep **Store** for discovery, acquisition, inventory, and downloads; keep **Settings → Models** for role defaults and service/provider configuration; keep **Chat** and **Image generation** for actually using models. Introduce a reusable **model readiness / guided setup** experience that can be launched from all three locations, eliminating navigation loops.

**Critical product principle:** A downloaded image weight is not an installed, ready-to-use image generator. Explicitly represent the distinctions between file presence, server visibility, complete setup, loaded runtime, saved configuration and successful generation. Do not equate a passed metadata check with an inference success.

**Preserve:** Existing Material 3 Expressive look; local-first design; administrator approvals; version/commit, destination and checksum pinning when available; safe unknown-outcome reconciliation; resumable image transfers; accessibility behavior; role drafts and Apply/Discard; and explicit protection when changing a shared image runtime. Preserve all unrelated dirty worktree changes.

## 1. Evidence versus design inference

### Confirmed by the supplied handoff (source-based, not re-tested live)

- Store has Discover / Installed / Downloads; Discover mixes model highlights with separate MCP/Skill previews.
- Store image files download to Klaude's host and may not appear in the image server's independent inventory.
- Image primary files, recipes, component slots, companion downloads, shared-runtime loading, and saving the image service are separate steps.
- Only two curated FLUX-3 setup profiles have verified recommendation sources in the handoff; category-match in the setup picker is not architecture certification.
- Downloads have Pause/Resume for supported image operations and exact-receipt reconciliation; transfers continue across page navigation.
- Settings → Models provides role defaults, independent drafts, and nested Connections and Image generation screens.
- Connection creation, secret storage, testing, and enabling are separate backend operations, with reviewed state changes.
- The handoff is not proof that the running host has the latest controls: version/feature capability checks remain necessary.

### Design inferences, not reported user-study findings

- Users are likely to interpret *Installed* as *usable*.
- Repeated cross-screen navigation increases drop-off, especially on phone.
- Icon-only Add and overflow-only Test make common connection actions harder to discover.
- A normal user likely expects download review cancellation to return to the selected model, not Downloads.
- Large image downloads make late surprise dependencies and endpoint mismatch especially costly.

These are defensible hypotheses; confirm them with the user tasks and analytics described below rather than describing them as measured outcomes.

## 2. Proposed information architecture

```text
Store
├── Discover
│   ├── Models   (search; Chat / Image; search result filters)
│   ├── Skills   (discovery; installed management stays in Integrations)
│   └── MCP servers (discovery; management stays in Integrations)
├── My Models (previously Installed)
│   ├── All
│   ├── Chat
│   └── Image
└── Downloads (host-owned model transfers and receipts)

Settings
└── Models
    ├── Model defaults (Startup chat, Utility, Research, Vision)
    ├── Connections (provider/server configuration)
    └── Image generation (technical service configuration)

Chat
└── Current model picker (use, or find a model)

Image generation
└── Ready model picker (use, or set up a model)
```

Avoid introducing an extra top-level Models item. The same model identity and readiness card should appear consistently in Store detail, My Models, and the image composer. Preserve direct links and browser back/focus history.

**Language:** `Available`, `Downloaded`, `Needs setup`, `Missing components`, `Ready to load`, `Loaded`, `Ready to generate`, `Generation verified`, with exceptional states `Checking`, `Paused`, `Failed`, `Unconfirmed`, `Service unavailable`, `Compatibility unknown`, and `Incompatible (verified)`. A single linear enum is insufficient: compute the user-facing headline from independent file/recipe/runtime/settings/test states.

## 3. Store — Discover

### Landing

```text
Store                                             Downloads (2)
[ Discover ] [ My Models ] [ Downloads ]

Find models, skills and tools
[ Search models, creators, repositories...                 ]
[ Models ] [ Skills ] [ MCP servers ]

For your work
[ Chat & coding ] [ Image generation ]

Featured (1–2 colorful, editorial tiles; no heavy autoplay carousel)
[ Featured model A ]                [ Featured model B ]

Popular models                                      See all
[ card ] [ card ] [ card ] [ card ]

Recently updated                                    See all
[ card ] [ card ] [ card ] [ card ]
```

Search is explicitly scoped to the selected content type. Do not pretend that one backend searches models, Skills and MCPs together. Initial landing has no technical filter wall. Results offer runtime, catalog source, sort order, source availability and **verified** capability filters where supported. On mobile, use a bottom-sheet filter panel. The exact-reference downloader lives behind an advanced action, not alongside ordinary search.

Model cards show descriptive title, publisher, task/category, weight size if known, runtime destination, and truthful state (`Downloaded`, `Needs setup`, etc.). Clearly label Hugging Face repository downloads as Hub downloads, not Klaude installs or fit scores. Never infer compatibility from popularity or filename alone.

### Model detail

```text
< Back to Store
[ icon ]  Model name                        [ Set up model ]
          Publisher · Image generation
          Short introduction

ABOUT / SPECS / SOURCE         SETUP SUMMARY (desktop sidebar)
Description                    Runtime: Stable Diffusion
Use cases                      Files: 3 (2 required companions)
Version details                Total download: known estimate / unknown
Source and license             Endpoint: named target
                               Compatibility: verified / unknown
                               [ Review setup ]

[ Advanced: exact variants, revisions, files, technical metadata ]
```

Desktop: two-column with main content and compact sticky summary, without obstructing the footer. Phone: single-column detail and a bottom sticky primary action with safe-area padding. Keep clear source/license and copy-reference actions. No giant artwork above essential information.

**Primary-action rules:**

| Situation | Primary action | Secondary |
|---|---|---|
| Ollama model absent | Download model | Choose variant |
| Image model not downloaded with a supported setup | Set up model | Technical files |
| Transfer active | View download | — |
| Image files downloaded, setup incomplete | Finish setup | Inspect files |
| Complete setup but runtime not loaded | Load model | Edit setup |
| Image model loaded and service configured | Generate image | Manage setup |
| Installed Ollama model | Use in chat | Manage model |
| Unsupported/unknown setup | Review requirements | Download files only (advanced, if allowed) |
| Confirmed incompatible | Explain incompatibility | View technical details |

Do not show `Ready` merely because a Store file exists.

## 4. Reusable image-model setup flow

Launch from Store, My Models, or the image composer; use the same route/identity and preserve the return destination.

### Step A: Choose the target and check prerequisites

Before a large download, display selected image server, server health, reachable/writable model directory, exact primary and companion sources, pinned identities, disk availability when known, and any supported recipe. **Do not offer a seamless installation promise** when the image server cannot see the Klaude host's downloads, or architecture/setup compatibility is unresolved.

- If no image server exists: show `Connect an image service` → Settings → Models → Image generation, then return to setup automatically.
- If the remote server cannot access the host's target directory: explain where the bytes would land, offer a verified server-writable destination only when supported, or offer file-only download with manual setup guidance.
- If setup/architecture is unknown: state `Compatibility not verified` and switch to expert/manual setup; do not guess dependencies.
- If server inventory category is wrong (`checkpoints` vs `diffusion_models`): show actionable repair only if a safe, server-supported reclassification exists. Otherwise report exact mismatch and manual instructions without pretending it is automated.

### Step B: Review an exact install plan

```text
Set up [model name]                                  Step 1 of 3

Where it will run
[ Image server: local SD service        Change ]

What is required
[x] Primary weights          5.2 GB     source/sha/revision
[x] Text encoder             2.1 GB     source/sha/revision
[x] VAE                      0.3 GB     source/sha/revision

Estimated download: 7.6 GB     Available disk: verified / unknown
Compatibility: verified / provisional / unknown
[ Show technical details ]

[ Cancel ]                          [ Download 3 files ]
```

All quantities above are **illustrative wireframe values, not actual model sizes**. The real screen must use verified metadata and show `Unknown` or a bounded estimate when appropriate.

One reviewed plan can authorize a fixed, enumerated set of exact transfers; it must not authorize silently adding future versions, substituting companion files, loading a shared runtime, or changing saved defaults. Deduplicate already-present verified files. Each file retains its own operation receipt, Pause, Resume, Stop and recovery. The plan is pinned to a destination and revision, must be revalidated for stale environments, and must be resumable without silent repinning.

### Step C: Download and recover

```text
Preparing [model name]                                2 of 3 files
Primary weights         [████████░░] 81%      [ Pause ]
Text encoder            [██████████] Complete
VAE                     [ Paused ]             [ Resume ]

Download accepted on this host. You can leave this page.
[ View downloads ]                         [ Continue when ready ]
```

- Accepted transfers continue after navigation.
- Show actionable errors inline; long logs remain in Details.
- Pausing preserves verified reusable bytes if supported. `Stop and discard partial` and `Remove from history` are distinct labels.
- An unconfirmed response shows `Check status`, not `Retry` or `Download again`.
- A finished primary file plus unfinished companions is `Needs components`, not `Installed and ready`.
- On completion, reconcile the server's inventory before showing `Ready to load`.

### Step D: Explicitly load and use

```text
Ready to load                                        Step 3 of 3
All required components are visible to the image server.

Current shared runtime: [existing model]
New runtime: [selected model]  (may replace current runtime)

[ Show exact file/recipe mapping ]

[ Not now ]                               [ Load model ]
```

Runtime loading is a separate explicit reviewed action. Recheck loaded identity and concurrent runtime changes before execution. On unknown acknowledgement, show `Check loaded state` and block conflicting replacements until reconciled. A confirmed load **does not** imply successful inference.

After successful load, show `Load complete` and an explicit `Use for image generation` action that saves the chosen image-service default (or the load review may separately include an opt-in to apply this exact default after load, if backend orchestration safely supports it). Save failure should not pretend to unload the model. The use action then opens the image composer with the selected model; optional `Generate a test image` requires an explicit user action and real inference.

### Return/resume behavior

Closing setup is not cancellation of already accepted transfers. Returning through Store, a model detail, or image composer must reopen the same persisted setup/operation identity. Completed steps should not repeat confirmations. On page reload or newer frontend/older host mismatch, show a capability-specific unavailable state and a safe restart/reload instruction; never drop receipts or fabricate progress.

## 5. My Models — readiness inventory

```text
My Models
[ All ] [ Chat ] [ Image ]                   [ Search installed models ]

Local model A        Ready for chat              [ Use in chat ]
Image model B        Missing 2 components        [ Finish setup ]
Image model C        Ready to generate           [ Generate image ]
Image model D        Downloaded; server can't see it [ Fix location ]
```

Each row: identity, runtime/host, disk usage, last verified time and one primary action. Details reveal source, pinned version, location, capability certainty and management actions. Avoid a bare `Installed` pill for incomplete image installations. Do not conflate the local host's file inventory with image-server visibility. If one runtime's inventory fails, preserve the other and say which side is unavailable.

## 6. Settings → Models overview

```text
Models                                             [ Refresh ]
Configure which models Klaude uses by default.

MODEL DEFAULTS
Startup chat        [ Qwen ...                              > ]
Utility             [ ...                                   > ]
Research            [ ...                                   > ]
Vision              [ ...                                   > ]
[ Advanced: fallbacks, output tokens, vision switch ]

CONNECTIONS
2 enabled providers · 1 needs attention           [ Manage > ]

IMAGE GENERATION
Stable Diffusion · Loaded model: ... · Ready       [ Configure > ]

[ Discard changes ]                          [ Apply changes ]
```

Keep the existing draft/Apply/Discard model for multiple preference edits. Avoid a redundant confirmation on each chooser. Distinguish `Startup chat default` from `Current chat model`. A role picker shows connection, available models, known vs unknown capability, and an explicit `Find more models` exit to Store. Make `Connected models` visible from a normal navigation link in the Connections area or its provider detail instead of a search-only secret destination.

Image settings should focus on service configuration: enable, provider, URL, current loaded identity, saved default, connection/capability test, and advanced options. Model **installation** should not require navigating through technical settings.

`Test service` becomes `Check service connection`, with supporting copy `Checks connection and capabilities; does not generate an image`. If the user loads a different runtime and then discards a preference draft, clarify: `Your settings edits were discarded. The image server remains loaded with [model].`

## 7. Settings → Models → Connections

### List

- Show readable **Add connection** button, not an icon-only action.
- Row: provider icon/name, endpoint summary, enabled/disabled state, credential presence (never value), last test result, linked model count (when known), and visible `Test` / `Manage` actions. Keep Remove and advanced operations in overflow.
- Group/filter `On this device`, `Other server`, and `Cloud API` only when actual endpoint/provider facts permit it; don't equate a local adapter with a local network route.
- Current connection should explain why edit/remove is blocked and offer `Switch current chat model` when possible.

### Add connection (guided full-screen page on phone, contained editor on desktop)

```text
Add model connection

1. Provider
[ Ollama ] [ Cloud provider ] [ OpenAI-compatible ]

2. Connection details
Name          [ ...                  ]
Server URL    [ ...                  ]
API key       [ ... optional by adapter ]
[ Advanced: routing, adapter identifier, request options ]

3. Verify and activate
[ Test connection ]
Connection check: reachable / authentication error / untested

[ Cancel ]                         [ Review and save ]
```

Only show actual adapters supported by the connected backend; do not invent OAuth or provider-specific support. When a credential is required, the user can enter it in this one flow, even if the backend stores it in a separate safe transaction. Avoid secret material in review text or logs.

**Immediate implementation:** Preserve the backend's disabled-definition → credential → test → enable sequence but retain the user in the same guided editor, displaying status and recovery between steps. One review per state-changing stage as necessary; do not launch unrelated dialogs without a reason.

**Long-term backend option:** Prepare a complete activation plan showing exact definition, secret presence, tests and requested final enabled state, then submit idempotently with per-stage receipts. Any partially completed plan leaves a truthful disabled state and `Continue setup`; no unreviewed privilege expansion or silent auto-enable.

## 8. Downloads, progress, and recovery

- Keep Downloads as the durable receipt/transfer destination.
- Add a compact global `Downloads (n)` entry and optional non-obscuring progress indicator across Store / image setup, not a large permanent Activity sidebar.
- Do **not** navigate to Downloads before a review dialog. Cancel returns to the selected variant; confirm may open an inline progress surface and expose `View downloads`.
- Show error cause and `Retry`/`Resume` only when it is safe and supported. Detailed target, IDs, timestamps and source go in Info.
- Unconfirmed = `Outcome unknown. Check status before making another change.` Reconciliation checks must not start work twice.
- Separate `Pause`, `Resume`, `Stop and discard partial`, `Remove from history`, `Remove model` and `Unload model`; never use one ambiguous × icon for unrelated effects.
- Show estimated speed only for actual byte movement; do not fabricate percent or ETA.

## 9. Model readiness data contract (proposed backend work)

Model setup should be exposed as a stable, versioned, server-generated plan that can be viewed from Store / My Models / composer:

```text
ModelSetupPlan
  identity: source + repository + immutable revision + variant
  destination: host + endpoint + verified destination/category
  recipe: exact recipe identity + server version + slot constraints
  artifacts[]: name, type/slot, exact source, checksum/size if known,
               local path, verified present/visible flag, operation receipt
  checks: source accessibility, disk budget, server reachability,
          runtime support, architecture evidence, model folder mapping,
          load-memory estimate (only where supported)
  current_runtime: identity + lease/concurrency evidence
  permissions: download / load / save default individually approved
  lifecycle: persisted plan ID, operation IDs, stage receipts,
             recovery instructions and validity epoch
```

Keep *artifact state*, *recipe state*, *runtime state*, *configured-default state*, and *inference-test state* independent. Compute a user-facing headline without claiming unsupported knowledge. If full preflight is unavailable, say `Cannot verify ahead of download` and use a manual path rather than manufacturing a compatibility result.

**State categories:**

| Axis | Example values |
|---|---|
| Artifact | absent, preparing, downloading, paused, downloaded, verified, failed, unconfirmed |
| Recipe | unknown, unsupported, incomplete, valid, invalid |
| Server visibility | unchecked, visible, wrong category, missing, unreachable |
| Runtime | unloaded, loading, loaded, wrong model, failure, unconfirmed |
| Configuration | unchanged, draft, applied, conflicted, unconfirmed |
| Inference proof | untested, succeeded with known setup, failed |

Any lost acknowledgement: status-check exact receipt, then reconcile before allowing a conflicting retry. Loading other clients' shared image runtime requires a separate explicit confirmation and race checking.

## 10. Screen behavior and accessibility

**Desktop:** Store detail uses a wide content column and a compact right setup summary. Settings remain one-column, reasonably capped, with grouped rows. Connection editor uses a broad contained sheet/page rather than stacks of dialogs. Download history uses readable rows with contextual primary actions.

**Mobile (320–390px):** One main task per screen; compact header; full-width model cards; Filters in a bottom sheet; large touch targets; summary and primary CTA visible without the keyboard; full-screen connection/setup flow; sticky bottom primary action with safe-area inset; no horizontal scrolling of filenames, IDs or buttons. Transfer rows may collapse secondary metadata but must expose progress, failure and the primary recovery action.

**Accessibility:** Native dialog focus confinement and return, keyboard navigable model lists, visible focus rings, 44px-ish targets, control names describing effects, busy states and status/live-region announcements without announcing every progress tick. Use semantic determinate/indeterminate progress based on actual counters. Respect reduced motion; do not use hue alone to indicate status. Preserve return focus/history when entering and leaving setup.

## 11. Examples of user-facing copy

| Scenario | Copy | Action |
|---|---|---|
| File downloaded, setup missing | `Weights downloaded. This model still needs 2 components before it can run.` | `Finish setup` |
| Server directory mismatch | `The file is on the Klaude host, but your image server cannot find it in its configured model folders.` | `Check model folders` |
| Unknown architecture | `We haven't verified that this version works with the selected image service.` | `Review requirements` |
| Incomplete transfer | `Download paused at 68%. Verified partial data has been kept.` | `Resume` |
| Source unavailable | `The selected file cannot be downloaded from this source. Nothing else was substituted.` | `Choose another source` |
| Load uncertain | `The server may have loaded the model, but Klaude did not receive confirmation.` | `Check loaded state` |
| Old host | `This server version does not support guided component installation.` | `View manual setup` |
| Disabled current connection action | `This connection is in use by the current chat. Switch the chat model before changing it.` | `Choose chat model` |
| Service test success | `Connection verified. Image generation has not been tested.` | `Generate test image` |
| Discard after load | `Settings edits discarded. The shared image server remains loaded with [model].` | `Done` |

## 12. Delivery plan

### P0 — UX fixes using existing capabilities

1. Fix cancel navigation: keep selection and detail context when a download review is cancelled.
2. Replace `Installed` on incomplete image files with `Downloaded` plus actionable `Finish setup`/`Configure` link.
3. Introduce a reusable readiness summary in Store detail and My Models, using only currently known evidence.
4. Provide `View download` and model return links from operation rows; reveal failure reason inline.
5. Show `Add connection`, `Test`, `Manage` as explicit text actions on the connections page.
6. Make `Connected models` discoverable in Settings → Models.
7. Clarify test-vs-generate, load-vs-save, pause-vs-stop, and history-vs-file removal in copy.
8. Ensure the image composer offers `Set up a model` and returns after setup.

**P0 acceptance:** Cancelling a transfer review never changes the active subpage. Any incomplete image model has a visible next action. Download, model and service errors remain meaningful without opening a technical Info dialog. Feature absence on an older host is honest.

### P1 — Coherent navigation and transaction flows

1. Build one model setup route used from Store/My Models/composer, including return state and receipts.
2. Group curated companion requirements before approval when known; show exact totals and missing size.
3. Keep individually resumable child transfers inside one setup progress view.
4. Make Connections Add a guided screen with in-context credential/test/enable lifecycle and partially-complete recovery.
5. Introduce common readiness state projection used by model detail, installed list, settings and composer.
6. Provide persistent non-intrusive download status plus a reliable resume entry point.

**P1 acceptance:** Supported curated image model can be prepared without manually navigating Settings after each step. No previously approved download is silently repeated. A paused companion can be recovered after reload. Provider setup remains in one place, retaining truthful disabled and tested states.

### P2 — Backend preflight and real compatibility

1. Versioned setup-plan API with exact pinned files and destination checks.
2. Server-visible directory mapping and safe category-correct placement where supported.
3. Supported architecture/recipe resolver with explicit verified/unknown/incompatible evidence.
4. Resource feasibility estimates only when backed by runtime/hardware evidence.
5. Durable grouped operation receipts, idempotency and stale-plan reconciliation.
6. Optional consolidated explicitly reviewed provider-activation plan.
7. Optional successful test-generation proof, with separate status from metadata checks.

**P2 acceptance:** Wrong directory and missing companions are disclosed before large downloads where data exists; no silent source substitution; no unchecked shared runtime replacement; and unconfirmed mutations cannot be resubmitted without reconciliation.

## 13. Test matrix and success criteria

Run on desktop (1440px) and phones (320px/390px), with keyboard, screen reader and reduced motion. Include at least:

1. New user installs one supported Ollama model and starts a chat.
2. New user finds a curated FLUX-3 image model and generates first image without losing context.
3. Existing downloaded image file is visible on Klaude host but missing on remote image server.
4. Primary file lands in `checkpoints` while required recipe expects `diffusion_models`.
5. Companion 1 completes while companion 2 fails; close, reload, resume.
6. Source is gated/unsupported; no silent alternate download.
7. Download, load, and save acknowledgement is lost independently: check first, no duplicate action.
8. Add cloud provider, save secret, test, enable; permission/token failure leaves clear partial state.
9. Try changing currently-used connection; see why blocked and how to switch.
10. Load new shared image model then Discard settings: confirm runtime remains changed and copy is honest.
11. Test service succeeds but real generation fails; do not report `Generation verified`.
12. Partial All-runtime catalog outage, stale inventory, and old host capability mismatch.

**Suggested metrics (targets to validate, not historical measurements):** setup completion rate, first-success generation rate, median number of screens/dialogs visited, misclick/cancellation rate, percentage of stalled operations recovered without restarting, support logs for path mismatch and unconfirmed receipts. Record actual baselines before setting numerical goals.

## 14. Sources and evidence from other products

- **LM Studio basic journey** — explicit discover → download → load → chat, and explanation that loading consumes RAM: https://lmstudio.ai/docs/app/basics
- **LM Studio memory estimate** — documented estimate-only option; transferable pattern is preflight *when evidence exists*, not guessed VRAM scores: https://lmstudio.ai/docs/cli/local-models/load
- **VS Code extensions** — clear installed/manage states, detail pages and visible dependency packs: https://code.visualstudio.com/docs/configure/extensions/extension-marketplace
- **Docker Desktop Images** — distinguishes local image inventory, in-use status, run action and removal: https://docs.docker.com/desktop/use-desktop/images/
- **W3C dialog focus guidance** — preserve focus/navigation for modal reviews: https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/

**Individual user reports, not consensus or validated prevalence:**

- ComfyUI issue #13676 (2026-05-02) reports missing model downloads going to browser rather than server configured path: https://github.com/Comfy-Org/ComfyUI/issues/13676
- ComfyUI-Manager issue #2284 (2025-11-15) describes some required components not appearing in missing-model installer and a destination subfolder mismatch: https://github.com/Comfy-Org/ComfyUI-Manager/issues/2284
- ComfyUI-Manager issue #2934 (2026-05-31) reports frustrating non-resumable large interrupted downloads: https://github.com/Comfy-Org/ComfyUI-Manager/issues/2934
- LM Studio issue #1442 (2026-01-30) reports mismatch between apparently loaded and selected model UI: https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1442

The outside sources are comparators and problem reports; they do not establish that Klaude has these exact failures. The supplied handoff remains the basis for claims about Klaude's current implementation.

## 15. Codex execution guidance

Implement in incremental, verified slices; do not replace the existing validated operation/security architecture with a client-only fake stepper. Inspect live source, active capabilities, and dirty worktree before editing. Avoid resetting, stashing, discarding, committing, or overwriting unrelated changes. Prefer reusable components and typed domain-state projections over duplicating status logic across media.js and management.js. Validate against old-host/new-assets compatibility, operation receipt reconciliation, role draft conflicts, automated accessibility checks, and the scenario matrix above. Keep existing Theme, Agent, Library and Integrations design language intact.
