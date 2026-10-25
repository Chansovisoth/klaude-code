# Codex Handoff — Klaude Model Store and Image Generation Studio

## Mission

Implement **only these two product goals** for Klaude WebUI:

1. **Model Store:** an Apple App Store-inspired *layout* for discovering, searching, downloading, and managing local Ollama models.
2. **Image Generation Studio:** a coherent, local-first image-generation experience that builds on Klaude's current `stable-diffusion.cpp` integration and can support other verified generation backends (including Ollama where actually available).

**Visual direction:** borrow the **Apple App Store's information architecture, editorial hierarchy, featured collections, rankings, and browse-to-detail flow**, **not** Apple's visual styling. All colors, typography, icon treatments, components, spacing conventions, expressive corners, transitions, and responsive behavior must use Klaude's existing **Material Design 3 Expressive / Klaude Expressive** system.

This is an **implementation assignment**, not just a mockup. Begin by inspecting the current repository and integrations; implement in reviewable, tested slices. If a backend capability is genuinely unavailable, expose an honest disabled state rather than simulating success.

## Mandatory repository rules

- Repository: `/home/klaude/klaude-code`.
- **Read root `AGENTS.md` first**, then inspect the live code, existing tests, design tokens, and relevant documentation. Treat `AGENTS.md` as architecture/history guidance, not proof that the current checkout is identical.
- **The worktree may be intentionally dirty.** Inspect `git status` and the relevant diffs before changes. Preserve all existing user work. Do not stash, reset, discard, overwrite unrelated changes, commit, or push.
- Extend the **shared application services, fixed workers, durable receipts, permission/review boundaries, and existing HTTP contracts**. Do not create a second model downloader, separate image artifact database, or ad-hoc subprocess/websocket job system.
- Preserve CLI/TUI functionality and backward compatibility. Add browser-facing typed contracts only where needed. Do not expose private prompts, local paths, credentials, raw Ollama responses, secrets, or unrestricted host endpoints through browser APIs.
- Respect existing browser auth, CSRF/Origin, ownership, session/revision, idle/model-work gating, cancellation, resource fencing, and uncertain-outcome recovery semantics.
- Work within the current build/bundle pipeline. If modifying the existing WebUI expressive/loading sources, run their documented bundling scripts before testing.

## Inspect and reuse before implementation

The attached repository guidance identifies these existing capabilities. **Verify their real current behavior and call paths before coding**:

- `apps/webhost`: current **Models** destination, model picker, installed/configured model catalogs, paging, responsive navigation, and **Settings → Models**.
- `packages/application`: typed fixed-operation workers, background jobs, receipts, model management, media generation, review and recovery services.
- `packages/core` and `apps/cli`: native Ollama model manager for installed-model inventory, search, pull/download, progress, cancellation, deletion, endpoint validation, and hardware info. Relevant CLI surface: `klaude model-manager ...`.
- **Library → Generated**: existing Create image/Research UI, image job history, cancellation/recovery, artifact storage and previews.
- **Settings → Models → Image generation service**: existing opt-in `stable-diffusion.cpp` server configuration, test, observed model identity, and save semantics.
- Existing locally bundled **Lobe AI SVG logos**, aliases, fallback icons, license and provenance. Do not create a competing logo system.

Read the relevant existing validation docs, especially `docs/webui/models-page-validation.md`, `docs/webui/media-controls-validation.md`, `docs/s5a-model-manager-validation.md`, `docs/s6b-local-generation-validation.md`, and the current WebUI design reference docs. Check which contracts are terminal-only today and extend them minimally and safely.

---

# Goal 1 — Model Store

## Navigation and information architecture

Keep the existing **Models** top-level destination. Do not add a new top-level **Store** item.

Within Models provide these destinations (tabs/sections, responsive to the real available width):

- **Discover** — the App Store-inspired browsing homepage.
- **Top charts** — ranked model collections when ranking signals are verified.
- **Categories** — curated entry points such as Coding, Reasoning, Vision, General-purpose, Lightweight. Categories may overlap.
- **Installed** — the real installed-model inventory for the selected, enabled native Ollama endpoint.
- **Downloads** — active/recent pull jobs and their honest lifecycle states. Merge with Installed when the limited content/viewport makes this more usable, but retain a clear path to active downloads.

Keep existing configured **cloud/API models** available in the Models experience as appropriate, but do **not** present them as locally downloadable Ollama packages. Avoid breaking the existing per-conversation **Use model** action or Settings → Models → Model Defaults link. Distinguish **browse/download** from **activate for this conversation**.

## Discover layout (Apple App Store-style, Klaude design language)

Build a realistic responsive layout in this approximate order:

1. Compact **Model Store** heading + one prominent search field.
2. A **featured editorial area**: one large feature card plus smaller companion cards (stack/swipe appropriately on mobile). Cards should describe actual, curated models or task collections, never invented capability claims.
3. **Popular models**: ranked compact rows with icon, name, one-line purpose, verified metadata, and context-appropriate action (`Get`, `Installed`, `View`, `Use`).
4. **New & noteworthy / Recently updated**: horizontally browsable collection or responsive cards, only if freshness data is trustworthy.
5. **Explore by category**: visual category tiles, filters, and concise descriptions.
6. Useful **recommended for this device** *only if* a credible compatibility heuristic exists; otherwise omit it rather than claiming a model will run well.

Design for desktop, tablet, and phone. On mobile, prioritize search, swipeable feature cards, compact ranked rows, visible download state, and readable details. Follow existing keyboard patterns, 44px accessible target expectations, reduced motion, focus restoration, URL/back navigation, and theme roles.

No misleading interactive decoration: every card and CTA needs a defined action. Prefer familiar App Store browse-to-detail and detail-to-download flows rather than overly dense settings-like tables.

## Search, catalog, metadata and truthfulness

- Search by model/family name and relevant use cases, with filters where supported: capabilities, size, downloaded/installed, and source.
- Browse **real model data** from Ollama's public model catalog or a verified equivalent. The official Ollama website currently offers searchable models and sorting, but **research its supported access method, stability, usage terms, schema, and freshness** before choosing an integration. Do not assume a public stable catalog JSON API exists; avoid brittle, unbounded scraping.
- Cache public discovery data with a clear age and bounded stale/offline fallback. **Installed models must remain browsable offline**. Keep catalog/network failure independent of native Ollama availability.
- Labels such as **Popular**, **Newest**, **Updated**, downloads count, parameter count, quantization, disk size, tool support, vision, thinking, license, and context limit must be backed by actual metadata or explicitly marked **Unknown/Not verified**. Never rank alphabetically and call it popularity. Never fabricate release dates or download counts.
- Distinguish an Ollama model *family* from an actual pullable `model:tag` variant. Validate exact tag/endpoint before download. A page might have discoverable variants without a known local size; reflect that honestly.
- Keep licensing/attribution links when available. Do not treat a catalog listing, brand logo, or a model's family name as a security or hardware compatibility guarantee.
- Prefer first-class native Ollama local endpoints for downloads. Do not turn generic cloud/HTTP connections into write-capable pull targets.

## Model detail page

A selected model should open a detail view with:

- Official/known model identity, logo, concise purpose, **verified** capabilities and publisher/source link.
- Variant/tag picker with parameter count, quantization, size and other known details; indicate missing values.
- Plain-language hardware guidance based on observed system resources if available, explicitly labeled **estimate, not guaranteed fit**. Do not auto-download, load into RAM/VRAM, or switch the user's model just to inspect details.
- **Download/Get** for not-installed exact variants; **Use model** for suitable installed models; **Manage/Delete** only through existing protected operations and reviews.
- A real download status section and helpful failure/offline/insufficient-disk messaging.

## Downloads and installation

- Reuse the existing native Ollama pull worker and its **streaming progress**, endpoint revision checks, operation ownership, and cancellation semantics. Provide observable bytes/total or stage text where supplied, not fictional percentage or ETA.
- A download should remain visible through navigation/reload/reconnect to the extent existing job/receipt ownership supports it. Reconcile with the authoritative installed inventory and durable receipt instead of restarting uncertain pulls.
- Cancelling must not claim remote transfer or partial layers were definitely removed unless Ollama confirms that. Show distinctions between **queued, downloading, complete, failed, cancelled, and outcome unknown**.
- Avoid two clients launching duplicate conflicting pull/delete operations. Respect global/endpoint model-work gates and explicit conflicts.
- Successful installation **does not** silently update chat, default model roles, image generation setup, or Vision.
- Deleting models must preserve protections for loaded models, active conversations and default roles, and keep an explicit destructive confirmation.

## Artwork and image sources

The editorial layout must not rely on arbitrary web image links:

1. **Model logos:** reuse the locally bundled, licensed Lobe SVG assets and matching family aliases; unknown models use Klaude's generic model glyph.
2. **Featured banners:** create a **small curated set of original, lightweight CSS/SVG compositions**, combined with logos, real titles, and category labels. Use semantic theme colors; ensure text contrast in dark/light/forced colors.
3. **Category tiles:** reuse Material/Klaude icons with simple themed abstract graphics, rather than unrelated stock photography.
4. **Official publisher artwork:** optional only when its distribution/license is verified and provenance recorded. Never hotlink or redistribute images by default.

No runtime image-generation calls to decorate the Store. Preserve local-first loading and avoid adding large image bundles, remote trackers, or an asset CDN. Make editorial content maintainable as small structured data with stable links to real model identities.

---

# Goal 2 — Image Generation Studio

## Location and primary flow

Keep **Library → Generated** as the primary destination, with its existing **Create** action. Upgrade **Create image** into a roomy, responsive **image studio** experience (dialog/sheet or dedicated nested view as appropriate to current routing). Research creation must continue to work; do not create a new top-level Image app.

The happy path is:

**Choose available generation backend/model → describe image → select aspect ratio → Generate → observe job → view/save output in Generated → preview/download or generate another image.**

### Default controls

- **Generator/model**: selected configured image-generation service and observed model identity; never confuse this with the chat/Vision model picker.
- **Prompt**: empty with a helpful placeholder, multiline, easy to edit; preserve draft during ordinary navigation within the studio.
- **Aspect ratio**: useful presets (1:1, 3:2, 2:3, 16:9), mapped to supported actual dimensions while respecting the backend's 256–1024 bounds and any stricter observed limits. Explicitly show final pixel dimensions.
- Primary **Generate image** action, with clear prerequisite guidance when generation is disabled, unconfigured, disconnected, or unavailable.

### Advanced settings

Use one native, keyboard-accessible disclosure. Include **only settings truly supported and validated by the selected backend**: width/height, steps, seed/random seed, negative prompt, guidance, sampler/scheduler, etc. Do not expose nonfunctional controls or silently drop advanced user values. Clamp/validate before review and before job admission. Keep an obvious reset-to-recommended/default behavior for this local draft.

### Generation progress and outputs

- Reuse existing owned job/receipt and Library artifact flows. Job cards show real queued/generating/completed/failed/cancelled/unknown status; elapsed time when available; progress only when the server provides meaningful metrics.
- Avoid displaying fake real-time preview frames; include server-supported previews only if they can be delivered through the existing bounded, authenticated image pipeline without leaking private data.
- **Cancel** should be accessible from a running job but retain server capability caveats and confirmed/unconfirmed results. Preserve correct behavior when completion races cancellation or acknowledgement is lost.
- Save confirmed outputs in **Library → Generated**, preserving private generation provenance and existing artifact revision, image viewer, archive, export, and deletion behavior.
- Finished outputs expose **Preview**, **Download**, and **Generate again** (reuses the user's parameters as a new draft, never automatically resubmits).
- Accepted jobs must not vanish merely because the user navigates, signs out, or the browser reloads. Use existing explicit receipt recovery; never resubmit a potentially completed generation to recover its image.

## Image-generation backend strategy

**First implement the complete UX against the existing verified `stable-diffusion.cpp` consumer.** Klaude already has an opt-in server, capability checks, bounded jobs, cancellation and output recovery; do not replace them with a separate image engine implementation.

Then design the provider boundary so additional engines can be integrated **only when their actual APIs are verified**, including:

- **Ollama image generation:** first inspect current Ollama release/API behavior and the connected local server's declared image-*output* capability. Image *input*/Vision/chat multimodality does **not** imply image generation. Wire it up only for a supported, tested image-output interface; otherwise show a precise unavailable explanation and leave generation to the existing image service.
- **Other local services (for example ComfyUI):** optional future integration, **not** an excuse to expand this task into arbitrary workflow execution or a full node editor. Define no fake providers in the selection UI.

No automatic model-weight installation, hidden server startup, arbitrary graph execution, background model switching, provider credential copying, or cloud image service is in scope. Keep all existing local-first, privacy, resource and network protections.

---

# Delivery approach

Implement in reviewable slices, not a wholesale rewrite:

1. **Architecture/UI audit:** report existing entry points, reusable service operations, missing browser contracts, real metadata sources, capability caveats, and planned tests. Continue to implementation without waiting for further product approval; choose the smallest compatible design.
2. **Model Store read path:** Discover layout, curated artwork, search/categories/charts, live catalog/offline states, installed inventory, model detail/variant picker.
3. **Model Store write path:** owner-authorized native Ollama downloads, status/reconnect, safe cancel/retry semantics, activation and existing deletion protections.
4. **Image Studio UX:** generator setup guidance, basic/advanced generation form, existing `stable-diffusion.cpp` job lifecycle and saved-output viewer.
5. **Additional image adapter only if actually supported:** verify current Ollama image-output capability and implement a bounded adapter with live/fixture validation where feasible; otherwise document the limitation without claiming Ollama generation works.
6. **Polish and regression tests:** responsive, accessible, keyboard, theme, network failure, concurrency, job ownership, privacy, model gate and recovery.

## Acceptance tests and evidence

At minimum, verify:

- Desktop/tablet/phone Model Store layouts, keyboard/tab/focus interactions, app theme switching, reduced motion and forced colors.
- Search, filters, sections and deep links/back navigation; curated cards always lead to valid model/detail/collection destinations.
- Offline catalog failure still permits installed-model browsing; no fabricated popularity, model specs or GPU-fit claims.
- Exact model/tag and endpoint selection; download progress, cancellation, error, duplicate requests, reload/reconnect and outcome-unknown behavior.
- The active chat and Model Defaults remain unchanged after a download; explicit Use model retains existing runtime constraints.
- Existing delete protections, local-only ownership, auth/CSRF checks and LAN restrictions remain intact.
- Image Studio enabled/disabled/unavailable states; generation with real supported parameters; responsive controls, drafts, duplicate-click prevention and validation.
- Job navigation/reload, cancellation race, recovery without duplicate generation, output provenance, Generated listing, image Preview/Download.
- Distinguish fixture evidence from real Ollama/`stable-diffusion.cpp` behavior. Do not claim hardware/provider support not exercised.
- Existing CLI/TUI tests, WebUI bundles, `make check` / focused unit and integration tests, and relevant smoke tests. Record commands run and any environment-dependent tests not run.

## Scope guardrails

Do **not** redesign Chat, Workspaces, Account, the global sidebar, Theme or unrelated Settings. Do not add ads, payments, accounts, reviews/ratings, social features, license-unsafe cover art, or an unrelated third-party marketplace. Don't introduce unrelated image editing, video generation, bulk model hosting, or ComfyUI workflow editing. Respect the existing app architecture and prefer one polished end-to-end path over an expansive but fake interface.

## Final response expected from Codex

Summarize:

- What shipped for **Model Store** and **Image Studio**.
- Files/contracts affected, reused application services, and any new worker/HTTP contract.
- What real catalog and image-generation capabilities were verified, and what remains unavailable.
- Tests and UI evidence performed, with limitations and follow-up gaps.
- Confirmation that preexisting work was preserved and **nothing was committed or pushed**.

## Technical references to check, not blindly trust

- Repo root: `AGENTS.md` and the validation docs above.
- Ollama public catalog: https://ollama.com/search
- Ollama API documentation: https://docs.ollama.com/api
- `stable-diffusion.cpp` documented server API: https://github.com/leejet/stable-diffusion.cpp/blob/master/examples/server/api.md
- Lobe icons catalog: https://icons.lobehub.com/
