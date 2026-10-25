# Codex Handoff — Klaude Model Store and Image Generation Studio

## Mission

Implement **only these two product goals** for Klaude WebUI:

1. **Model Store:** an Apple App Store-inspired *layout* for discovering, searching, downloading, and managing local Ollama models.
2. **Image Generation Studio:** a coherent, local-first image-generation experience that builds on Klaude's current `stable-diffusion.cpp` integration and can support other verified generation backends (including Ollama where actually available).

**Updated visual direction (supersedes the earlier Material-only restriction):** borrow the **Apple App Store's editorial marketplace layout** *and* its willingness to use **bold, colorful, image-led billboard artwork**. The store must still feel integrated with Klaude: keep the shared app shell, navigation, search inputs, selection behavior, accessible controls, typography where appropriate, and mobile patterns that already work in **Library** and **Integrations**. But **featured banners, editorial art, and category illustrations do NOT have to follow Material Design 3's restrained surface/color conventions**. Vivid purples, electric blues, coral, lime, gradients, 3D illustrations, illustrated scenes, and immersive typography are welcome **inside editorial content**. Never copy Apple's proprietary artwork; create original assets and verify licenses for third-party images.

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

## Navigation and information architecture — revised after real mobile screenshots

**The mobile screenshots show the current implementation is too cluttered. Fix the existing UI rather than building another store.** In particular: a long horizontally scrolling tab rail, a redundant Current chat/Model Defaults header row, an above-the-fold stack of Catalog/Order/Download size/Endpoint/Download-by-tag controls, oversized ranked cards, inconsistent installed rows, overlapped/duplicated chart content, and an empty Downloads tab full of technical controls. Library and Integrations are the reference for **compactness, consistent row primitives, 3-way full-width segmented navigation, mobile padding, and centered empty states**.

Keep the existing **Models** top-level destination, renamed/displayed as Model Store if already approved. Its primary tabs are **exactly**:

1. **Discover** — editorial feature billboards, compact top charts, categories, curated model rows and search.
2. **Installed** — the real inventory for the chosen enabled native Ollama endpoint, with compact manageable rows.
3. **Downloads** — durable active/recent pull and deletion outcomes, with a centered informative empty state when nothing exists.

**Top charts and Categories are sections/drill-downs within Discover, not top-level tabs.** Put **Connections** under Settings → Models; provide a contextual Settings link if a local endpoint is unavailable. Remove **Current chat** and **Model Defaults** from the Store header. Model Defaults already belongs to Settings and current-chat selection belongs to Chat. Do not remove those functions from their real owners.

On the Discover landing page, show, in this order:

1. Compact **Model Store** title and Refresh at the upper right.
2. Three **equal-width** Discover / Installed / Downloads tabs (not a clipped horizontal scroller).
3. One search field with a compact **Filters** button alongside it.
4. **Colorful image-led featured billboards immediately after search** — one main editorial feature and supporting tiles/peekable carousel; ensure the first billboard appears above the fold on typical phones.
5. **Popular models** as compact **ranked rows** (number, icon, model name, one brief purpose line, small Get/View/Installed action). No full-height cards for each rank.
6. **Explore by category** with compact illustrated tiles and straightforward drill-downs.
7. Recently updated or curated additional sections **only if trustworthy metadata exists**, and only when they improve browsing rather than adding clutter.

Advanced Catalog, Order, Download size and capability controls belong in contextual Filters, opening the appropriate filtering sheet/popover; don't permanently consume most of the screen. Endpoint selection appears where it matters (Installed, Downloads, model detail, or when multiple native endpoints are available), **not four times across a Discover page**. Keep advanced **Download exact tag** as a secondary action inside Search, Filters or model details; never place an enormous disabled pill on the discovery landing page.

On mobile, billboards can use **horizontal scroll snap with the next colorful card visibly peeking in**. On desktop, use an asymmetric editorial grid with one larger billboard and smaller companions. Avoid independent nested scroll containers for the overall page. Respect 320/360/390/430px viewports, safe areas, dynamic browser chrome, enlarged text, focus, touch, keyboard, and reduced motion.

### Editorial imagery: go bold, beyond strict Material

**This is an explicit product requirement.** Avoid muted brown/tan blank billboard cards with just an enlarged brand logo, generic monochrome glyph, or simple colored rectangle. A featured card must read as a real **image-led editorial cover**: original **illustrated or rendered subjects**, layered foreground/background, interesting lighting, vivid color and visual storytelling. Good examples of subjects: a holographic coding workspace, an iridescent glass/metal reasoning sculpture, and a glowing photographic lens/prism for vision. Using gradients **as backgrounds or lighting** is good; a **gradient-only banner is not enough**.

Artwork policy:

- For high-impact hero images, prefer a small curated set of **original, visually rich** illustrations/renders bundled locally as optimized WebP/AVIF/PNG, or carefully hand-authored SVG illustrations. Static original graphics can be created specifically for model categories; they need not be literal publisher imagery.
- Visual cover art is **curation**, not an automated generated image per search result. No runtime image-generation requests, external hotlinks, trackers or asset CDN. If making AI-generated imagery for curated editorial assets, bundle the approved result and record its provenance.
- Reuse local **Lobe logos** for small model list/detail identities (respect their license). Publisher product artwork is optional and only redistributed after checking explicit rights. Preserve generic icons for unknown models, but **not** as a substitute for rich hero artwork.
- Allow curated vivid artwork colors independent of Cocoa/Theme seeds **inside the media frame**. Keep the adjacent store chrome theme-aware, accessible and predictable. Gradient/overlay scrims must protect text readability and contrast over every supplied artwork. Light/dark/forced-color fallbacks and missing-image fallback must remain legible.
- Give each featured cover a meaningful editorial title, short description, actual model/collection destination and a consistent CTA. No invented popularity/release/capability claims.
- Don't rely on intricate animations to make the cover attractive. Optimize images, reserve their aspect-ratio boxes to avoid layout shifts, lazy-load below-fold art, respect reduced motion, and avoid excessive bundle weight.

### Layout reference — follow the attached HTML example

The handoff includes a complete standalone, mobile-first HTML/CSS/JS example in an appendix and as a separate file **`klaude-model-store-layout-reference.html`**. It demonstrates the desired page hierarchy, colorful **original SVG illustration art** within hero banners (not plain gradient cards), 3-way full-width tabs, contextual Filters, ranked rows, compact category tiles, installed list and Downloads empty state. Its fake model data, rankings, icon placeholders and JS are **prototyping only**. Do not copy a parallel JS application, fake catalog, download behavior or app shell into production; adapt the **layout, artwork approach and sizing** to Klaude's current components, state and server contracts.

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

## Artwork and image sources — authoritative direction

Use the **editorial imagery** requirements above and the full HTML reference below. **Colorful, visual, original billboard art is now mandatory**, not optional or strictly Material-tonal. Model logos still reuse Klaude's pinned local Lobe assets. Do not replace original/editorial art with bland logo-on-solid-color cards merely because the shared design tokens are restrained.

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

- Screenshot validation on **320, 360, 390 and 430px phones**, tablet and desktop, including dynamic browser chrome: 3 tabs fit the content width, no clipped tab rail, no horizontal overflow (except the intentional featured carousel), consistent rows/padding and no overlapping/duplicated chart cards.
- **Image-led and visually colorful billboards** are present on Discover, with original illustrated content (not just flat tint or logo); their overlay text stays readable in light/dark/system themes, forced colors and missing-image fallbacks.
- Keyboard/tab/focus interactions, app theme switching, reduced motion and forced colors.
- Discover first viewport prioritizes search and image-led featured content instead of technical control stacks. Filters reveal advanced controls contextually; Get/View/Manage actions consistently open the verified detail/operation path.
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


---

# Appendix A — runnable HTML layout example (visual reference; not production code)

This example is intentionally a self-contained HTML file with original multi-layered vector **illustrations inside the billboards**, rather than blank gradients or hotlinked images. It has a minimal demo script for tabs, filters and a fake detail dialog. It contains no real download or generation logic and uses illustrative model rankings. **Do not use these fake model identities or data as verified backend content**. The production implementation must adapt the page/hero/row structure to existing Klaude components and preserve the actual server APIs and operation lifecycle.

To preview, open the accompanying `klaude-model-store-layout-reference.html` in a browser. The same complete source is included below so this Markdown handoff remains self-contained.

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="dark">
  <title>Klaude Model Store — Editorial Layout Reference</title>
  <style>
    /* VISUAL REFERENCE ONLY. Reuse Klaude's real application shell, typography,
       theme roles, auth, navigation, dialogs, and APIs in production. */
    :root {
      --surface: #151110;
      --surface-raised: #211b19;
      --surface-low: #29221f;
      --border: #4c403a;
      --text: #f6eeea;
      --muted: #c0ada2;
      --accent: #edd0ba;
      --max-content: 1150px;
    }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    html { scroll-behavior: smooth; }
    body { margin: 0; color: var(--text); background: var(--surface); font: 15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
    button, input { font: inherit; }
    button { cursor: pointer; }
    button:focus-visible, input:focus-visible, a:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
    .shell-header { height: 72px; border-bottom: 1px solid #2a2421; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 0 max(20px, calc((100vw - var(--max-content))/2)); }
    .brand { font-size: 21px; font-weight: 800; letter-spacing: -.8px; }
    .brand-mark { display: inline-grid; place-items: center; background: #605047; width: 36px; height: 36px; border-radius: 50%; margin-right: 7px; font-size: 21px; }
    .shell-actions { display: flex; gap: 12px; color: var(--muted); }
    .shell-actions span { border: 1px solid #4c403a; border-radius: 50%; width: 34px; height: 34px; display: grid; place-items: center; }
    main { max-width: var(--max-content); margin: auto; padding: 28px 24px 72px; }
    .page-heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
    .eyebrow { font-size: 11px; text-transform: uppercase; letter-spacing: .14em; color: var(--muted); font-weight: 700; }
    h1 { font-size: clamp(25px,3.4vw,36px); letter-spacing: -.045em; margin: 4px 0 0; line-height: 1.15; }
    h2 { margin: 0; font-size: clamp(20px,2.5vw,26px); letter-spacing: -.035em; }
    .icon-button { border: 0; color: var(--text); background: var(--surface-low); border-radius: 14px; height: 44px; width: 44px; font-size: 22px; }
    .tabs { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 6px; margin-bottom: 22px; }
    .tab { height: 48px; min-width: 0; padding: 0 7px; color: var(--muted); background: #342b27; border: none; border-radius: 23px; font-size: 14px; font-weight: 600; }
    .tab[aria-selected=true] { color: #211913; background: var(--accent); }
    .tab-panel[hidden] { display: none !important; }
    .search-row { display: flex; gap: 10px; margin-bottom: 25px; }
    .search { display: flex; align-items: center; flex: 1; min-width: 0; gap: 10px; height: 50px; border: 1px solid var(--border); background: #2d2623; border-radius: 14px; padding: 0 15px; }
    .search svg { flex: none; color: var(--muted); }
    .search input { min-width: 0; flex: 1; color: var(--text); background: transparent; border: 0; outline: 0; }
    .search input::placeholder { color: #b6a49a; }
    .filter-btn { border: 1px solid var(--border); background: #342b27; color: var(--text); border-radius: 14px; padding: 0 15px; min-height: 50px; }
    .filter-panel { display: none; padding: 16px; background: var(--surface-raised); border: 1px solid var(--border); border-radius: 16px; margin: -12px 0 22px; color: var(--muted); }
    .filter-panel.is-open { display: block; }
    .filter-panel button { border: 1px solid var(--border); background: #41342e; color: var(--text); border-radius: 999px; padding: 9px 12px; margin: 6px 6px 0 0; }
    .section-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin: 28px 0 14px; }
    .section-heading:first-of-type { margin-top: 0; }
    .subheading { color: var(--muted); font-size: 13px; }
    .quiet-link { color: var(--accent); text-decoration: none; font-size: 13px; font-weight: 650; white-space: nowrap; }
    .billboards { display: grid; grid-template-columns: 1.55fr 1fr 1fr; gap: 13px; }
    .billboard { isolation: isolate; position: relative; min-height: 335px; overflow: hidden; background: #1f2445; border-radius: 24px; }
    .billboard .art { position: absolute; inset: 0; width: 100%; height: 100%; z-index: -2; }
    .billboard::after { content: ''; position: absolute; inset: 0; z-index: -1; background: linear-gradient(0deg,rgba(8,9,21,.92) 0%,rgba(8,9,21,.28) 60%,rgba(8,9,21,.02) 100%); }
    .billboard--main::after { background: linear-gradient(90deg,rgba(13,12,32,.94) 0%,rgba(13,12,32,.8) 38%,rgba(13,12,32,.1) 100%); }
    .billboard__copy { display: flex; flex-direction: column; align-items: flex-start; justify-content: flex-end; height: 100%; padding: 22px; color: white; }
    .billboard--main .billboard__copy { justify-content: center; max-width: 75%; }
    .billboard__label { font-size: 10px; font-weight: 850; letter-spacing: .16em; text-transform: uppercase; color: #ffce9d; }
    .billboard h3 { font-size: clamp(23px,2.4vw,32px); letter-spacing: -.045em; line-height: 1.04; max-width: 15ch; margin: 10px 0 9px; }
    .billboard:not(.billboard--main) h3 { font-size: clamp(22px,2vw,27px); }
    .billboard p { max-width: 28ch; font-size: 13px; color: #f4ebee; margin: 0 0 16px; }
    .billboard__cta { padding: 10px 15px; border-radius: 999px; color: #221a19; background: white; border: 0; font-weight: 700; font-size: 12px; }
    .billboard--orange { background: #ff6e32; }
    .billboard--green { background: #18766e; }
    .rank-list { display: grid; gap: 0; }
    .rank-row { display: grid; grid-template-columns: 25px 48px minmax(0,1fr) auto; align-items: center; gap: 12px; min-height: 74px; padding: 9px 1px; border-bottom: 1px solid #352b27; }
    .rank { color: #d0b5a6; text-align: center; font-size: 15px; font-weight: 700; }
    .model-icon { width: 48px; height: 48px; border-radius: 13px; display: grid; place-items: center; font-weight: 900; font-size: 23px; background: #3c3455; color: #bfbcff; }
    .model-icon--orange { color: #ffb489; background: #542c24; }
    .model-icon--teal { color: #76e4c8; background: #1f463e; }
    .model-icon--blue { color: #7fb6ff; background: #1c3552; }
    .model-name { font-weight: 720; font-size: 14px; overflow-wrap: anywhere; }
    .model-desc { font-size: 12px; color: var(--muted); margin-top: 3px; }
    .pill { border: 0; border-radius: 999px; padding: 9px 16px; background: #3e332e; color: var(--accent); font-weight: 800; font-size: 12px; min-height: 38px; }
    .categories { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; }
    .category { position: relative; min-width: 0; padding: 17px 16px 19px; border-radius: 19px; border: 1px solid #4c403a; overflow: hidden; background: #2b2332; text-align: left; color: white; min-height: 138px; display: flex; flex-direction: column; justify-content: end; }
    .category::before { content: ''; position: absolute; width: 105px; height: 105px; top: -23px; right: -19px; opacity: .9; border-radius: 24px; transform: rotate(22deg); background: repeating-linear-gradient(135deg,rgba(255,255,255,.24) 0 5px,transparent 5px 14px), radial-gradient(circle at 25% 25%, #c7a5ff,#4f3e8a); }
    .category--reason { background: #503027; }
    .category--reason::before { border-radius: 50%; background: radial-gradient(circle at 36% 30%,#ffed6a, #ff7a42 48%,#a7437c 72%); }
    .category--vision { background: #173e42; }
    .category--vision::before { border-radius: 50% 14% 50% 14%; background: conic-gradient(from 80deg,#85fbd0,#38a4ff,#eab6ff,#85fbd0); }
    .category--light { background: #403d21; }
    .category--light::before { border-radius: 30%; background: radial-gradient(circle,#f2ffad 12%,#b1d445 30%,#63924c 69%); }
    .category strong { position: relative; font-size: 17px; letter-spacing: -.03em; text-shadow: 0 1px 8px rgba(0,0,0,.45); }
    .category small { position: relative; font-size: 12px; color: #eee4e0; margin-top: 3px; text-shadow: 0 1px 8px rgba(0,0,0,.45); }
    .info { border: 1px solid var(--border); border-radius: 18px; background: var(--surface-raised); padding: 18px; }
    .empty { min-height: 360px; display: grid; align-content: center; justify-items: center; text-align: center; gap: 10px; }
    .empty-icon { width: 68px; height: 68px; border-radius: 24px; background: #3d322b; display: grid; place-items: center; font-size: 30px; }
    .empty h3 { margin: 8px 0 0; font-size: 21px; }
    .empty p { margin: 0; color: var(--muted); max-width: 35ch; }
    .demo-note { margin-top: 35px; font-size: 12px; color: #a5958d; }
    @media (max-width: 850px) {
      main { padding: 22px 20px 80px; }
      .billboards { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(245px,65vw); grid-template-columns: none; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-inline: contain; padding-bottom: 7px; }
      .billboard { min-height: 300px; scroll-snap-align: start; }
      .billboard--main .billboard__copy { max-width: 84%; justify-content: flex-end; }
      .billboard--main::after { background: linear-gradient(0deg,rgba(10,8,25,.95),rgba(10,8,25,.1) 85%); }
      .categories { grid-template-columns: repeat(2,minmax(0,1fr)); }
    }
    @media (max-width: 480px) {
      .shell-header { height: 58px; padding: 0 18px; }
      .shell-actions { gap: 7px; }
      .shell-actions span { width: 30px; height: 30px; }
      main { padding: 20px 17px 92px; }
      .tab { font-size: 13px; }
      .billboards { margin-right: -17px; padding-right: 17px; grid-auto-columns: 84%; gap: 10px; }
      .billboard { min-height: 270px; border-radius: 21px; }
      .billboard__copy { padding: 18px; }
      .billboard h3 { font-size: 29px; }
      .billboard p { font-size: 12px; }
      .rank-row { grid-template-columns: 16px 45px minmax(0,1fr) auto; gap: 8px; }
      .model-icon { width: 45px; height: 45px; }
      .pill { padding: 8px 12px; }
      .category { min-height: 126px; }
      .search { padding: 0 12px; }
      .filter-btn { padding: 0 12px; }
    }
    @media (prefers-reduced-motion: reduce) { *,*::before,*::after { scroll-behavior: auto !important; animation: none !important; transition: none !important; } }
  </style>
</head>
<body>
  <header class="shell-header" aria-label="Example application header">
    <div class="brand"><span class="brand-mark" aria-hidden="true">✦</span>klaude.</div>
    <div class="shell-actions" aria-hidden="true"><span>⌕</span><span>☰</span></div>
  </header>
  <main>
    <div class="page-heading">
      <div><div class="eyebrow">Explore local AI</div><h1>Model Store</h1></div>
      <button class="icon-button" type="button" aria-label="Refresh" title="Example only" id="refresh">↻</button>
    </div>
    <div class="tabs" role="tablist" aria-label="Model Store sections">
      <button class="tab" type="button" role="tab" aria-selected="true" aria-controls="discover-panel" id="discover-tab" data-tab="discover">Discover</button>
      <button class="tab" type="button" role="tab" aria-selected="false" aria-controls="installed-panel" id="installed-tab" data-tab="installed">Installed</button>
      <button class="tab" type="button" role="tab" aria-selected="false" aria-controls="downloads-panel" id="downloads-tab" data-tab="downloads">Downloads</button>
    </div>

    <section class="tab-panel" id="discover-panel" role="tabpanel" aria-labelledby="discover-tab">
      <div class="search-row">
        <label class="search">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="10.7" cy="10.7" r="6.7"/><path d="m16 16 5 5"/></svg>
          <input type="search" id="model-search" placeholder="Search models or a use case" aria-label="Search sample models">
        </label>
        <button class="filter-btn" id="filter-toggle" aria-expanded="false" aria-controls="filters" type="button">Filters ☷</button>
      </div>
      <div class="filter-panel" id="filters"><strong>Browse by use case</strong><br><button type="button" data-search-term="coding">Coding</button><button type="button" data-search-term="reasoning">Reasoning</button><button type="button" data-search-term="vision">Vision</button><button type="button" data-search-term="">Clear filters</button><p style="margin-bottom:0;font-size:12px">Real implementation: add verified capability, size, source and ordering controls here, not above the artwork.</p></div>

      <div class="section-heading"><h2>Featured</h2><span class="subheading">Illustrative collections</span></div>
      <div class="billboards" aria-label="Featured model collections">
        <article class="billboard billboard--main" data-model="qwen coder coding">
          <!-- Original, image-led vector artwork. Production may replace it with curated, bundled WebP/AVIF assets. -->
          <svg class="art" viewBox="0 0 800 520" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Colorful original editorial artwork with floating holographic computer screens">
            <defs>
              <radialGradient id="bg-a" cx="78%" cy="36%" r="84%"><stop stop-color="#e33bff"/><stop offset=".36" stop-color="#4939ef"/><stop offset=".8" stop-color="#141749"/><stop offset="1" stop-color="#080a1e"/></radialGradient>
              <linearGradient id="glass-a" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#76f9fa"/><stop offset=".45" stop-color="#9387ff"/><stop offset="1" stop-color="#ff68cf"/></linearGradient>
              <linearGradient id="warm-a" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffd775"/><stop offset="1" stop-color="#ff578d"/></linearGradient>
              <filter id="blur-a"><feGaussianBlur stdDeviation="32"/></filter>
            </defs>
            <rect width="800" height="520" fill="url(#bg-a)"/>
            <circle cx="615" cy="125" r="160" fill="#fa6de2" opacity=".52" filter="url(#blur-a)"/>
            <circle cx="695" cy="380" r="150" fill="#00e9f2" opacity=".45" filter="url(#blur-a)"/>
            <g opacity=".45" stroke="#c3d7ff" stroke-width="2" fill="none"><path d="M390 500 715-8M430 520 755 12M470 540 795 32"/><path d="M480 90 790 300M450 130 760 340"/></g>
            <g transform="translate(494 96) rotate(-12 112 135)">
              <rect x="8" y="10" width="237" height="304" rx="24" fill="#041b47" opacity=".65"/>
              <rect width="237" height="304" rx="24" fill="#1c265c" stroke="url(#glass-a)" stroke-width="8"/>
              <rect x="20" y="23" width="197" height="258" rx="13" fill="#192d75"/>
              <circle cx="42" cy="42" r="6" fill="#ff7599"/><circle cx="62" cy="42" r="6" fill="#ffe36f"/><circle cx="82" cy="42" r="6" fill="#79eddf"/>
              <path d="M48 104 92 142 48 180M152 104 111 180" fill="none" stroke="#b4fdfa" stroke-width="15" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M53 220h132" stroke="#ff79cf" stroke-width="9" stroke-linecap="round"/>
              <path d="M53 243h83" stroke="#a991fa" stroke-width="9" stroke-linecap="round"/>
            </g>
            <g transform="translate(620 275) rotate(15)"><rect width="145" height="107" rx="17" fill="#ec73ff" stroke="#ffeabc" stroke-width="7"/><path d="M25 35h90M25 61h68" stroke="#2b246c" stroke-width="12" stroke-linecap="round"/></g>
            <g transform="translate(435 380) rotate(-22)"><ellipse cx="80" cy="33" rx="100" ry="34" fill="url(#warm-a)"/><path d="M-20 33Q80 118 180 33" fill="#fd8e8d"/><ellipse cx="80" cy="33" rx="55" ry="17" fill="#491883"/></g>
            <g fill="#fff2af"><path d="m438 63 9 25 25 9-25 9-9 25-9-25-25-9 25-9z"/><circle cx="700" cy="89" r="9"/><circle cx="755" cy="210" r="5"/></g>
          </svg>
          <div class="billboard__copy"><span class="billboard__label">Featured · Coding</span><h3>Ideas to working code.</h3><p>Discover the Qwen coding model family.</p><button type="button" class="billboard__cta" data-detail="Qwen coding family">Explore family ↗</button></div>
        </article>
        <article class="billboard billboard--orange" data-model="deepseek reasoning">
          <svg class="art" viewBox="0 0 450 520" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Vivid orange and magenta illustrated glass sculpture resembling a blossoming idea">
            <defs><radialGradient id="bg-b"><stop stop-color="#ffe98b"/><stop offset=".42" stop-color="#f86540"/><stop offset="1" stop-color="#6c185a"/></radialGradient><linearGradient id="petal-b"><stop stop-color="#fff0ba"/><stop offset=".55" stop-color="#ff74ad"/><stop offset="1" stop-color="#b952d5"/></linearGradient></defs>
            <rect width="450" height="520" fill="url(#bg-b)"/>
            <circle cx="235" cy="185" r="137" fill="#ffea9b" opacity=".5"/>
            <g transform="translate(236 180)">
              <g fill="url(#petal-b)" stroke="#ffe9c2" stroke-width="5" opacity=".96">
                <ellipse cx="0" cy="-92" rx="56" ry="115"/><ellipse cx="0" cy="-92" rx="56" ry="115" transform="rotate(60)"/><ellipse cx="0" cy="-92" rx="56" ry="115" transform="rotate(120)"/><ellipse cx="0" cy="-92" rx="56" ry="115" transform="rotate(180)"/><ellipse cx="0" cy="-92" rx="56" ry="115" transform="rotate(240)"/><ellipse cx="0" cy="-92" rx="56" ry="115" transform="rotate(300)"/>
              </g><circle r="45" fill="#ffc855" stroke="#fff0bc" stroke-width="9"/><circle r="14" fill="#a62d61"/>
            </g><path d="M30 65q30-40 58-10M340 310q48-45 84-8" stroke="#ffeeaa" stroke-width="6" fill="none" stroke-linecap="round"/>
          </svg>
          <div class="billboard__copy"><span class="billboard__label">Reasoning</span><h3>Think in new directions.</h3><p>Explore reasoning models.</p><button type="button" class="billboard__cta" data-detail="Reasoning models">Discover ↗</button></div>
        </article>
        <article class="billboard billboard--green" data-model="vision multimodal gemma">
          <svg class="art" viewBox="0 0 450 520" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Colorful teal illustrated optical lens with luminous geometric shapes">
            <defs><radialGradient id="bg-c"><stop stop-color="#a7ff7b"/><stop offset=".48" stop-color="#00b5b3"/><stop offset="1" stop-color="#123d71"/></radialGradient><radialGradient id="iris-c"><stop stop-color="#101a49"/><stop offset=".19" stop-color="#9b70ff"/><stop offset=".56" stop-color="#62fdcf"/><stop offset="1" stop-color="#fdf6a1"/></radialGradient></defs>
            <rect width="450" height="520" fill="url(#bg-c)"/>
            <g transform="translate(235 172) rotate(-14)"><rect x="-133" y="-99" width="266" height="198" rx="68" fill="#e4fff1" opacity=".88"/><ellipse rx="98" ry="91" fill="url(#iris-c)" stroke="#fff" stroke-width="13"/><circle r="35" fill="#142448" stroke="#a4ffee" stroke-width="13"/><circle cx="-20" cy="-21" r="16" fill="white" opacity=".8"/></g>
            <path d="m60 78 29 40-29 40-29-40z" fill="#e3b8ff"/><path d="m364 267 43 27-43 27-43-27z" fill="#fff0b1"/><circle cx="375" cy="82" r="20" fill="#ff9eca"/>
          </svg>
          <div class="billboard__copy"><span class="billboard__label">Multimodal</span><h3>See what AI sees.</h3><p>Explore image-capable models.</p><button type="button" class="billboard__cta" data-detail="Vision models">Explore ↗</button></div>
        </article>
      </div>

      <div class="section-heading"><h2>Popular models</h2><a href="#categories" class="quiet-link">See categories ›</a></div>
      <div class="rank-list" aria-label="Example popular model rows — not live rankings">
        <div class="rank-row" data-model="qwen3 coder coding"><span class="rank">1</span><div class="model-icon" aria-hidden="true">⌘</div><div><div class="model-name">Qwen3-Coder</div><div class="model-desc">Coding · Agent tasks</div></div><button class="pill" data-detail="Qwen3-Coder">GET</button></div>
        <div class="rank-row" data-model="deepseek r1 reasoning"><span class="rank">2</span><div class="model-icon model-icon--orange" aria-hidden="true">✺</div><div><div class="model-name">DeepSeek-R1</div><div class="model-desc">Reasoning</div></div><button class="pill" data-detail="DeepSeek-R1">GET</button></div>
        <div class="rank-row" data-model="gemma3 vision general"><span class="rank">3</span><div class="model-icon model-icon--teal" aria-hidden="true">◉</div><div><div class="model-name">Gemma 3</div><div class="model-desc">General · Vision variants</div></div><button class="pill" data-detail="Gemma 3">GET</button></div>
        <div class="rank-row" data-model="llama general"><span class="rank">4</span><div class="model-icon model-icon--blue" aria-hidden="true">◈</div><div><div class="model-name">Llama</div><div class="model-desc">General purpose</div></div><button class="pill" data-detail="Llama family">GET</button></div>
      </div>

      <div class="section-heading" id="categories"><h2>Explore by category</h2><span class="subheading">Find your use case</span></div>
      <div class="categories">
        <button class="category" data-category="coding"><strong>Coding</strong><small>Build and debug</small></button>
        <button class="category category--reason" data-category="reasoning"><strong>Reasoning</strong><small>Solve complex tasks</small></button>
        <button class="category category--vision" data-category="vision"><strong>Vision</strong><small>Understand images</small></button>
        <button class="category category--light" data-category="lightweight"><strong>Lightweight</strong><small>Smaller models</small></button>
      </div>
      <p class="demo-note">Design/reference only. Model ranks, names and category associations are illustrative. The production UI must use verified catalog metadata and actual Ollama tags. Colored artwork is original SVG illustration, not just a gradient surface.</p>
    </section>

    <section class="tab-panel" id="installed-panel" role="tabpanel" aria-labelledby="installed-tab" hidden>
      <div class="section-heading"><h2>Installed models</h2><span class="subheading">Example inventory</span></div>
      <div class="rank-list">
        <div class="rank-row"><span class="rank">●</span><div class="model-icon" aria-hidden="true">⌘</div><div><div class="model-name">qwen3-coder:30b</div><div class="model-desc">Installed · Exact local model</div></div><button class="pill" data-detail="qwen3-coder:30b">Manage</button></div>
        <div class="rank-row"><span class="rank">●</span><div class="model-icon model-icon--teal" aria-hidden="true">◉</div><div><div class="model-name">gemma3:4b</div><div class="model-desc">Installed · Exact local model</div></div><button class="pill" data-detail="gemma3:4b">Manage</button></div>
      </div>
      <p class="demo-note">Production: select Ollama endpoint only when more than one native endpoint exists; installed inventory comes from real endpoint service.</p>
    </section>
    <section class="tab-panel" id="downloads-panel" role="tabpanel" aria-labelledby="downloads-tab" hidden>
      <div class="empty" role="status"><div class="empty-icon" aria-hidden="true">⇩</div><h3>No downloads yet</h3><p>When you download an Ollama model, its progress and status will appear here.</p><button type="button" class="pill" data-tab-switch="discover">Discover models</button></div>
      <p class="demo-note">Do not show unused endpoint selectors or an inactive “Download by tag” form in this empty state.</p>
    </section>
  </main>
  <dialog id="detail" style="width:min(92vw,440px);border-radius:22px;border:1px solid #54423a;background:#2e2521;color:#f8ede5;padding:24px;box-shadow:0 20px 100px #0009">
    <form method="dialog"><div class="eyebrow">Design prototype · No model operation</div><h2 id="detail-name" style="margin:8px 0">Model details</h2><p style="color:#c4afa3">Production: this opens the real model detail view with verified model tags, sizes, capabilities, exact endpoint and Download/Use actions.</p><button class="pill" style="margin-top:12px">Close</button></form>
  </dialog>
  <script>
    // Only for the standalone prototype. The production WebUI must use its
    // existing router, state, accessible dialogs and fixed application services.
    const tabs = [...document.querySelectorAll('[data-tab]')];
    function activateTab(id) {
      for (const tab of tabs) {
        const selected = tab.dataset.tab === id;
        tab.setAttribute('aria-selected', String(selected));
        document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
      }
    }
    tabs.forEach(t => t.addEventListener('click', () => activateTab(t.dataset.tab)));
    document.querySelectorAll('[data-tab-switch]').forEach(b => b.addEventListener('click', () => activateTab(b.dataset.tabSwitch)));
    const filterToggle = document.getElementById('filter-toggle');
    filterToggle.addEventListener('click', () => {
      const visible = document.getElementById('filters').classList.toggle('is-open');
      filterToggle.setAttribute('aria-expanded', String(visible));
    });
    const search = document.getElementById('model-search');
    search.addEventListener('input', () => {
      const term = search.value.trim().toLowerCase();
      document.querySelectorAll('[data-model]').forEach(el => { el.hidden = !!term && !el.dataset.model.includes(term); });
    });
    document.querySelectorAll('[data-category],[data-search-term]').forEach(b => b.addEventListener('click', () => {
      search.value = b.dataset.category || b.dataset.searchTerm || '';
      search.dispatchEvent(new Event('input'));
      search.focus();
      window.scrollTo({top: 0,behavior: 'smooth'});
    }));
    const detail = document.getElementById('detail');
    document.querySelectorAll('[data-detail]').forEach(b => b.addEventListener('click', () => {
      document.getElementById('detail-name').textContent = b.dataset.detail;
      detail.showModal();
    }));
    document.getElementById('refresh').addEventListener('click', () => { search.value=''; search.dispatchEvent(new Event('input')); activateTab('discover'); });
  </script>
</body>
</html>

```
