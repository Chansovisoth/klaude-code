# Store and Models: current UX handoff for independent review

Prepared 2026-10-29 from the current working tree of `klaude-code` (0.2.0a4).

## Read this first: scope and evidence

This describes the implemented browser interface, including uncommitted work currently in the repository. It is a source-based walkthrough, not a new live-browser audit. The running host can have older backend code while serving newer static assets. Features therefore depend on host capabilities; some newer controls require a host restart and browser reload. Existing validation documents describe fixture and selected live checks, but do not prove that every flow below is active in the user's current session.

No model was downloaded, loaded, deleted or generated for this description. No settings were changed. Earlier design documents contain superseded layouts; current JavaScript and HTML take precedence here. In particular, the live Store no longer has its old featured artwork carousel, and image downloads now have Pause/Resume.

The requested review concerns Store, Settings → Models, Settings → Models → Connections, and the full journey from finding an image model to generating with it. Store also contains MCP and Skill discovery, described briefly so its information architecture is complete. Model Connections and MCP connections are different systems.

## 1. Product concepts the user must understand

| Concept | Meaning | Main UI owner |
|---|---|---|
| Store catalog entry | Public repository metadata and downloadable variants; not a compatibility certification | Store → Discover |
| Downloaded/installed Ollama model | A model available on a selected native Ollama endpoint | Store → Installed |
| Downloaded/installed image model | A weight file on the Klaude host; potentially only one part of a usable setup | Store → Installed |
| Model connection | An existing local server or cloud API, its adapter, URL, enabled state and optional credential | Settings → Models → Connections |
| Model role/default | Saved model choice for startup chat, Utility, Research or Vision | Settings → Models |
| Current chat model | Runtime selection for this conversation, distinct from startup defaults | Chat; installed Ollama Store details also offer Use model |
| Image service | Separate image-generation provider, endpoint, enable flag and saved model | Settings → Models → Image generation |
| Image setup/recipe | Image server's loading configuration, with exact component slots and alternative requirements | Image model picker |
| Loaded image runtime | Weights currently occupying the shared image server's memory | Image model picker / image server |
| Image dependencies | Companion model weights such as a text encoder and VAE | Required components inside the image model picker |

The dependency installer described below installs companion weights. It does not install Python packages, CUDA, stable-diffusion.cpp, or an inference server. A working service must already exist.

## 2. Navigation and visual conventions

- Store is a main navigation destination, available through desktop navigation, mobile navigation/More and the command palette. Canonical URL: `?view=store`. Older `view=models` links migrate to Store.
- Settings has a Models category. Inside it, Connections and Image generation are dedicated destinations with a clickable Models return breadcrumb. Connected models is another destination reachable through Settings search/existing links; it is not a prominent overview link.
- Store sections are Discover, Installed and Downloads. They use the shared Library/Integrations section chips, selected colors and animated corner treatment, with native buttons, pressed state and shared keyboard navigation.
- Layout uses Klaude's Material surfaces, locally bundled model/provider icons, light/dark themes, grouped settings rows, muted supporting text, shared menus and tooltips. It is not a separate marketplace design system.
- The top-level Store heading has Refresh on the right. Models overview has its own Refresh; nested management screens have their own relevant refresh actions.
- Settings role choosers are full-width rows: role icon/label, selected value and chevron. Advanced fallback choosers follow the same pattern, with a 64px minimum height. Group dividers span the card while controls/text stay inset.
- Dialogs use native modal behavior. Header close controls use a cross at the top right. Footer actions align right, with Cancel before the confirming action where present. Icon controls have accessible labels and shared tooltips.
- Narrow screens stack or wrap content within the existing page gutters. Long model references are shortened in compact rows and exposed in detail. Prior fixture smoke covers 320/390/768/1440px for newer image flows; this document adds no new visual verification.

## 3. Store → Discover

### Entry and page structure

The normal initial runtime is Ollama; runtime selection is restored from URL state where supplied. The Runtime filter offers All, Ollama and Stable Diffusion. All combines two bounded catalogs rather than querying one universal catalog.

The normal live landing page contains:

1. Store heading and Refresh.
2. Discover / Installed / Downloads section chips; the last two can show count badges when counts are known.
3. Search field and an icon action for downloading an exact model reference.
4. Contextual dropdown filter chips.
5. Popular models, with “By Hugging Face downloads” and See all.
6. Recently updated, with See all.
7. Integrations previews for MCPs and Skills, each with See all.

There is no current-chat selector or defaults editor in the Store header. The live landing has no featured promotional carousel. Popular and Recent use compact card/row grids, adapting preview capacity to complete rows near twenty items. Available sources and failures can produce shorter collections. Recent avoids duplicating displayed Popular entries.

### Search and filters

- Search defaults to the public Hugging Face catalog. Search text is sent to that catalog. This is remote discovery, distinct from local installed-model filtering.
- Runtime: All / Ollama / Stable Diffusion.
- Catalog: Hugging Face / Offline collection where applicable. Stable Diffusion uses its image catalog and hides this choice.
- Order: Hub downloads / Recently updated. Charts drill-downs own their ordering and disable irrelevant controls.
- Capability: Any / Tools / Vision / Thinking for the offline discovery path; hidden for live Hub discovery because exact capabilities are not established there.
- Installed download size: Any / Up to 8 GB / Up to 16 GB / Up to 32 GB; appears in Installed rather than Discover. This filters file size, not hardware fitness.
- An Ollama endpoint selector appears when context requires choosing among multiple enabled native endpoints. Cloud APIs are not weight-download targets.

See all opens a full results/collection page under Store with a Discover return action. Search, runtime, source, order, collection, paging and selected detail/variant use URL/history state. Results use previous/next and numbered paging; responsive capacity and upstream continuation chains bound what is fetched. All preserves separate continuation chains, identifies runtime on each card and keeps identical repository names distinct across runtimes. It is not a globally ranked unified universe.

### Model cards and source states

Cards show a model identity icon, readable name, available repository download count and update date, task where supplied, runtime badge and View/Installed pill. Rankings/counts describe Hugging Face repositories, not Klaude users or Ollama installs. Unknown metadata remains unknown. An Installed badge means inventory contains a known variant; it does not certify image readiness.

Loading states use the shared loader. Cached results remain identifiable and can remain visible during refresh/outages. Error/empty states offer Refresh or different searches. Offline collection remains a separate available path/fallback. No hardware-fit score, benchmark result, verified compatibility badge or complete dependency budget is computed for general Hub models.

Image-task cards discovered through the Ollama GGUF search path are routed to Stable Diffusion details/downloads, rather than pulled into Ollama.

## 4. Store model detail and download review

Model detail is a full Store subpage with Back/history/focus restoration, rather than the old image-carousel detail design.

### Detail layout

- Large model icon, model name, publisher/profile link, runtime badge and source model-card link.
- Primary action: Choose model before a variant is selected; Download with size after selection; Installed for a local image file; Use model for an eligible installed Ollama model; Current model when already selected.
- Contextual blocker/status text and View downloads, Refresh inventory or Model settings links as applicable.
- Available facts such as task, Hub downloads, updated date, variant count, parameters, format and license. Missing facts are not invented.
- About this model, with Show more/Show less for descriptions longer than the compact preview.
- Choose your download: destination, exact-variant radio rows, filenames, quantization/parameter metadata where supplied, size, Selected/Installed/Cached state, and paging after twenty variants. A second download action is placed below the variants.
- Details disclosures: Exact model reference, compatibility/technical information, source/license. Links include the exact variant source where known.
- Eligible installed Ollama models expose Delete model. Installed image models expose Image generation settings; browser image-weight deletion is unavailable.

Download size is not a RAM/VRAM requirement. Store metadata does not establish context limits, exact tool/vision support or architecture compatibility. Some current explanatory copy still says “top-level” even though newer backend paths support bounded nested files; that copy should be reconciled during review.

### Download interaction

1. Open a repository/card.
2. Choose an exact variant/file, and an Ollama endpoint if necessary.
3. Press Download.
4. The application prepares an exact review. The Store moves to Downloads before showing the shared review dialog; cancelling therefore leaves the user on Downloads rather than automatically returning to the variant page.
5. The dialog is titled Download model? and visibly lists Model, File for Hub references, and Destination/Server. More details contains the backend's prepared technical summary. Cancel receives initial focus; Download is the confirming action. Backend image review pins commit, size, checksum and destination identity; these backend checks should not be mistaken for a prominent visual compatibility report.
6. Confirm with Download, or cancel without starting a transfer.
7. Accepted work appears as an owned operation in Downloads and continues on the host when the user leaves the page.

The exact-reference download dialog is a separate advanced shortcut for the native Ollama path. It does not act as a universal guided image-dependency installer.

Mutations require an administrator and an idle conversation/queue. Missing or stale inventory, disabled/missing endpoint, unsupported host, active conflicting work or an unresolved outcome can disable actions. The UI shows explanatory status and relevant refresh/settings/download links. Independent image-file downloads have newer concurrency allowances; this does not make every model operation concurrently available.

## 5. Store → Installed

- Search changes to Search installed models.
- Runtime remains available; the size filter replaces discovery-only filters.
- Ollama lists the selected endpoint's installed inventory. Stable Diffusion lists bounded local image-file metadata. All combines those inventories.
- Rows show icon, model/file name, known parameters, size, runtime when combined, and Manage. Manage opens the existing detail page.
- Inventory includes Checked/Cached timestamps and bounded/truncated guidance when relevant. Twenty-row local paging is used.
- No installed files, no search matches and unavailable inventory have distinct empty states. All keeps the available side of a partial failure and hides an unknown total rather than reporting zero.

For image files, Installed does not mean the service sees the file, the setup is compatible, companions exist, the model is loaded, defaults are saved, or a real generation has succeeded.

## 6. Store → Downloads

Downloads removes Search, filters, endpoint selection and exact-download shortcut. Empty state: No downloads yet and Discover models.

Populated downloads use compact tonal list cards with:

- Filename/readable model name; full target is in the Info dialog.
- Parameter metadata when known.
- Status or transferred/total bytes; thin theme-selected progress bar when measurable.
- Estimated MB/s during measurable activity, calculated from reported byte changes. No fabricated speed/progress for transfers lacking counters.
- Essential icon actions and an Info action. Errors and longer ownership/source/target/timestamp explanations live in Info.

| Situation | Controls / behavior |
|---|---|
| Owned running Ollama pull | Stop; Info |
| Owned running image download | Pause, then Stop cross; Info, when host supports pause |
| Paused/failed/cancelled image transfer | Resume before history-removal cross; Info |
| Completed history | Remove download; Info |
| Unknown outcome | Needs check / Check download status; conflicting work can remain blocked |
| Externally observed transfer | Read-only status and Info; control stays with its original client |

Pause preserves a verified resumable partial after stopping the owned worker. Stop uses discard-partial cleanup. Resume starts another owned request for the same originally pinned file without a new source-selection confirmation; it does not silently switch to a newer revision. Failed attempts may retain bytes, depending on failure/cleanup. Resume can still be rejected by changed targets, active conversation or unresolved state.

Remove download dismisses presentation history; it does not delete weights. Unknown-outcome recovery checks exact existing evidence without starting a second transfer. Where dismissal of an unknown record is supported, a compact Check outcome notice retains its fence.

The native Info dialog supports keyboard/touch dismissal and returns focus to the row's current Info button across polling. Leaving Store/signing out clears private UI state; accepted host operations retain their receipts. External image activity may be only recent/quiet filesystem activity: it is not proof of completion and does not supply reliable percentage or cancellation.

## 7. Store integration discovery

Discover includes independent MCP and Skills previews, up to four complete responsive rows per collection. Catalog reads begin near the viewport, with separate loading/error/retry states. These are not mixed into model search results.

See all opens a Store catalog with search, refresh, source attribution and paging. MCP uses the official Registry; Skills offers SkillsMP and skills.sh. Order offers Stars/Recently updated where supported. GitHub stars come from the declared repository, independently cached; unknown is not zero. Some Stars orders apply only to the bounded returned collection. skills.sh has no updated dates, so Recently updated is disabled with guidance.

Details show About/source and available catalog/version/commit/license/endpoint facts. Supported remote HTTP MCPs without setup inputs can be reviewed and added **disabled**, then managed/enabled in Integrations. Credentials, local packages, other transports and OAuth retain terminal setup. A Skill source is verified to an exact GitHub SKILL.md/commit, optionally using an explicit source URL, before a reviewed folder installation. Existing Skills are not overwritten and scripts are not run. Detail feedback distinguishes installing, completed, failed and unconfirmed, with Manage and View Activity links.

These catalogs are browsed inside Store, but installed MCP/Skill management belongs to Integrations. Store Installed/Downloads primarily describe models, so integration lifecycle feedback also appears in detail/Activity.

## 8. Settings → Models overview

The page is a single column in this visual and DOM order:

1. Models heading, Refresh and description of model defaults/service management.
2. Connections section: configured/enabled count and Manage connections navigation row.
3. AI model defaults / Model roles.
4. Advanced defaults disclosure.
5. Image generation section: service summary and Configure service navigation row.

The main roles are Startup chat, Utility, Research and Vision. Each whole-row chooser opens the shared Choose model dialog containing Connection, Refresh, search, model rows, current-choice state and paging. Models are filtered for the role; unknown capability is explicitly labeled, not treated as verified. Selecting a row closes the dialog and stages a draft. It does not immediately change the current conversation or save the default.

Advanced defaults contains:

- Utility fallbacks: three ordered chooser slots.
- Vision fallbacks: three ordered chooser slots.
- Explanation that fallbacks run in order when the primary cannot complete a request.
- Utility output tokens numeric control, 128–2048.
- Enable Vision for image input and analysis switch.

Unset this role is available where allowed; enabled Vision prevents clearing its required primary. The disclosure preserves its open state during rerenders. Saved references outside the latest catalog remain representable instead of disappearing.

### Drafts, Apply and conflicts

Changes show an unsaved count and page-bottom Discard / Apply changes actions. Choosing a model is a draft operation; refresh merges saved state without silently erasing a dirty draft. Default roles and image-service settings have independent Apply/Discard scopes.

Apply uses the shared exact preparation/receipt machinery without requiring a separate ordinary confirmation dialog for every field. Access-expanding changes, such as enabling Vision or enabling/changing an image endpoint, can show an additional “Allow these access changes?” dialog with Cancel / Save changes. Saving multiple defaults proceeds in an ordered sequence, so a failure can report some saved changes and retain the remaining drafts; this is not one atomic all-fields save.

Conflicting external edits show saved and draft values with Use saved value / Keep my change. An unconfirmed save exposes Check save status or Check saved state, rather than treating a network timeout as definitive failure. Some operations remain locked until resolved. Navigating between Models screens with unsaved work can ask: “You have pending changes. Leave this screen and keep your draft?” Drafts are held in memory and clear at sign-out; they are not durable browser-storage drafts.

Connected models, the less prominent nested destination, shows models exposed by enabled configured providers, connection filtering, search, refresh and paging. Its copy points users to Chat to choose the current conversation model. It is separate from downloadable Store inventory.

## 9. Settings → Models → Connections

### Screen layout and list

Models breadcrumb → Connections, followed by a Connections heading and Refresh. Introductory copy: “Connect an existing local server or cloud API. New connections start disabled; test and enable them explicitly.”

Below status/recovery notices, a Search connections field sits beside an icon-only Add connection button. Search matches name, backend, Local/Cloud classification and URL. Empty states distinguish No connections yet and No matching connections.

Each row contains provider/adapter icon; connection name; Enabled/Disabled badge; backend and Local/Cloud text; URL; Credential saved/No saved credential; Current marker when used by the hosted chat; and an overflow menu. There is no inline setup wizard or primary Connect button per row.

### Add a connection

1. Press Add connection.
2. A native Add model connection dialog opens, initially focused on Name.
3. Fill Name, Adapter, Server URL, Configured routing (Local/Cloud), and Use a saved API key / token checkbox.
4. The default adapter is Ollama, with `http://127.0.0.1:11434` and Local. Adapter choices come from the backend and currently display adapter identifiers. Changing adapter selects its suggested URL; non-Ollama defaults to Cloud/authentication enabled.
5. Help explains that credentials must be saved separately before enabling an authenticated connection.
6. Review change prepares the definition and closes the editor before opening the shared confirmation.
7. Confirm creates the connection disabled. Cancellation discards the prepared change; the editor is not a persistent onboarding wizard.

This connects an existing service. It does not install Ollama, launch a server, obtain a cloud API key, or guide a full OAuth login.

### Per-connection overflow actions

| Action | Interaction |
|---|---|
| Test | Executes a metadata/connectivity test; page says Testing connection… then shows the returned message/error. Does not enable it. |
| Edit | Opens name/URL/routing/authentication fields; adapter cannot change after creation. Review change then confirmation. Some managed adapters, such as openai_codex, omit Edit. |
| Enable / Disable | Separate reviewed change; not a direct inline switch on this page. |
| Credential | Separate credential dialog, only where editable. Enter replacement and Review change, or Remove credential when one exists. |
| Remove | Separate reviewed removal; styled as destructive. |

Current connection restrictions disable Edit, Enable/Disable, Credential and Remove, while allowing Test if otherwise idle. Active chat/queue, pending changes, unknown state or missing administrator permission can lock management. Thus changing/removing a current connection can require choosing another conversation model first.

Credential values are write-only. The list reports presence, never the saved value. Secret fields use native password input behavior with Klaude's visual masking. Draft secrets clear before review, on editor close and sign-out. Creating the definition, adding a credential, testing, and enabling are distinct actions; there is no combined credential-and-enable transaction.

The overflow menu supports arrows, Home/End and Escape with focus return; it is positioned within the viewport and closes on navigation/resize. Editor close returns focus to its opener. Pending shared changes show in-progress text; unknown saves show Check saved state and block another write until the exact outcome is known. Older hosts show restart/reload guidance; non-admins get read-only guidance.

Model Connections are not Integrations → MCP connections: their controls, credentials and review rules differ. In particular, MCP direct switches do not imply model Connections has direct switches.

## 10. Settings → Models → Image generation

The screen contains Image generation service heading and explanation that testing checks capabilities without generating an image. Grouped controls appear in this order:

1. Enable generation switch.
2. Provider: Stable Diffusion (stable-diffusion.cpp) or Ollama (experimental).
3. Image model.
4. Server URL.
5. Saved model summary.
6. Test service.
7. Recovery notices and the independent Discard / Apply changes actions when needed.

For Stable Diffusion, Image model is the shared full-width label/value/chevron chooser. For Ollama, there is a model-name input plus Choose model. The Ollama chooser looks for an enabled native Ollama connection matching the image endpoint; if none exists, it asks the user to enter the name manually. This makes the image endpoint and ordinary connection systems related but not unified.

Test service contacts the entered service and reports its model and supported width/height bounds, explicitly saying no image was generated. It does not save. Editing the fields invalidates the displayed test evidence. Apply persists the reviewed candidate; an explicit SD model must still agree with the current loaded server model. Service reachability/capabilities are not proof of successful inference.

## 11. Complete image-model installation journey

### A. Discover and download the primary weight

1. In Store choose Stable Diffusion, or open an image card from All.
2. Inspect source, architecture, license, variants and file sizes.
3. Select one supported GGUF/Safetensors file and approve its exact download.
4. Follow Downloads progress; Pause/Resume/Stop as needed.
5. On completion the primary file is installed on the Klaude host, normally under `checkpoints/OWNER/REPOSITORY/FILENAME` beneath `KLAUDE_IMAGE_MODEL_DIR` (default `/mnt/HDD1/klaude-image/models`).

The root must already exist and be writable. A remote image server must access this directory. General Store discovery does not create a complete application-like package or choose all companions. Unsupported sources include gated-auth downloads, directory bundles and split model shards; explicit MLX variants are excluded. Other architecture incompatibilities can remain.

### B. Find that file from Image generation settings

1. Open Settings → Models → Image generation, using the installed detail's Image generation settings link or the overview.
2. Select Stable Diffusion and set the existing service URL.
3. Open Image model.
4. Opening the picker refreshes server metadata, then reads its inventory; Refresh can rescan explicitly again. Browsing does not load weights.
5. The picker lists the currently loaded model, if any, and installed primary checkpoint/diffusion files with search and twenty-row paging. Rows distinguish Checkpoint from Diffusion weights.
6. An empty server inventory explains that the server's model folder must contain the downloaded weights; a currently loaded model can still be usable.

The source of truth here is the image server's categorized inventory, not Store's local directory listing. A download can exist on disk but be absent from this picker because the service sees another directory or stale/incompatible categories.

### C. Choose a compatible setup

1. Select an installed primary file.
2. A Model setup dropdown appears with “Choose a compatible setup.” Candidate setups come from the server and are filtered by primary-slot category, not verified architecture matching.
3. Select a setup. The corresponding primary slot is prefilled when category allows it.
4. The picker now shows setup name, an Installed models return action, and a selector for every component slot.
5. Each slot says Required or Optional and offers exact files exposed in acceptable server categories.
6. Alternative requirements say “Choose at least one: … or …”. For example, a VAE alternative can be satisfied by a selected TAE.
7. Load and use model remains disabled until required slots and alternative groups are satisfied, and pending/runtime locks permit loading.

The user currently needs enough knowledge to select the right architecture/setup. Category matching alone is not proof of compatibility. Normal Store downloads go to checkpoints; some recipes require diffusion_models instead. A documented FLUX-3 case required a manual filesystem hard link into diffusion_models. There is no general browser move/reclassify flow, and Store does not automatically organize the primary weight for a selected recipe.

### D. Install missing companion weights

For an incomplete setup, newer hosts show Required components inside the same picker. The first curated profiles cover **flux3-klein** and **flux3-klein-base** only:

| Offered component | Source file | Destination category |
|---|---|---|
| Qwen 3 VL 4B Text Encoder | `Qwen/Qwen3-VL-4B-Instruct-GGUF` → `Qwen3VL-4B-Instruct-Q4_K_M.gguf` | text_encoders |
| FLUX.2 VAE | `Comfy-Org/Flux-2-Dev` → `split_files/vae/flux2-vae.safetensors` | vae |

The panel shows component label, exact filename, individual size, Source link and total missing bytes. A historical metadata check resolved about 2.83 GB total; sizes are resolved from metadata rather than hardcoded as a permanent estimate.

Each missing component offers Install:

1. Install opens the existing exact-file review for that one component.
2. Approve Download, or cancel with no transfer.
3. Accepted rows retain their identity and show queued/downloading/byte state plus Pause and Stop.
4. Install the other component through a second review. Independent files can download together within the shared four-worker capacity on supporting hosts.
5. Paused/failed/cancelled rows offer Resume; unknown outcomes offer Check download status. Progress failures offer Refresh downloads.
6. Completion refreshes the server catalog and fills the empty matching slot for this recipe, while preserving a user's selected alternative.
7. Existing recommended files offer Use installed. A completed set can say “All required components are ready. Review loading below.”

There is no Install all bundle or automatic dependency continuation. Closing the picker leaves accepted transfers running, but does not approve/install other components later. Store → Downloads also exposes these transfers.

If the setup is unknown, missing files are reported without guessed download sources: “No verified download recommendation is available. Select compatible installed files.” Some unresolved slots add “Other required files need manual selection.” Metadata errors offer Retry dependency check. A selected TAE suppresses the extra VAE recommendation when it satisfies the alternative. On older hosts the panel is hidden or concurrency guidance asks for a restart after pausing active downloads.

### E. Load the runtime

1. After selecting all required files, press Load and use model.
2. Review the exact endpoint, setup and component filenames. The operation replaces the shared image-server runtime and consumes its memory.
3. Confirm. One owned worker requests the load and tracks the result; it has a bounded ten-minute wait.
4. Changed catalog/runtime selection can reject the operation before load. An explicit server failure reports failure. A lost acknowledgement can leave “Model loading is unconfirmed.”
5. Check loaded state inspects the exact expected ready runtime without issuing another load. A different/empty/loading runtime can remain unresolved and locked.
6. On confirmed successful load, the picker checks the loaded model and stages it as the image-service draft, then closes.

Choosing the already loaded model skips a new weight load, checks its identity and stages its name. Loading affects a shared service, potentially used by other clients. Discarding a settings draft does not unload or restore the previous runtime.

### F. Save defaults and actually generate

1. Back on Image generation, use Test service if desired; it is still a capability check, not generation.
2. Apply changes saves the selected endpoint/provider/model/enable flag. It remains separate from downloading and loading.
3. Resolve any access confirmation, save conflict or unknown receipt.
4. Open the image-generation flow, enter a prompt and generate an image to establish practical readiness.

The UI currently has no single Store-to-first-image task tracker spanning all these stages. Dependency-download completion does not automatically load, save defaults or generate.

## 12. Failure and recovery scenarios the review must include

- User downloads an image file and sees Installed, then cannot find it in the server picker.
- Correct file appears under Checkpoint, while the needed setup expects Diffusion weights.
- User chooses a category-compatible but architecture-incompatible setup.
- Primary download completes, but companion sources are gated, unavailable or unsupported by the curated profiles.
- One companion finishes while another is paused/failed; the user closes/reopens the picker.
- User tries to change a current model connection and finds its actions disabled.
- User adds a cloud connection and must separately add credentials, test and enable it.
- User cancels a Store download review and lands in Downloads, away from the selected variant.
- User loads a model, then presses Discard on settings and expects the old runtime to return.
- Service test succeeds but real generation fails from memory, architecture or component incompatibility.
- The browser disconnects after a transfer/load/save may have taken effect: status check must precede a new conflicting attempt.
- New frontend assets encounter an older host; restart may itself be blocked by active work.
- Remote image endpoint cannot see files downloaded to the local Klaude host.
- All-runtime search/inventory partially fails while the other runtime remains available.

These are flow consequences and review scenarios, not claims that each occurred in a new test run.

## 13. Observed UX tensions to analyze, not predetermined redesigns

1. **Installation vocabulary:** image Installed describes file presence while readiness requires several later decisions.
2. **Fragmented ownership:** Store, model Connections, image endpoint, server recipes, runtime and saved defaults have different screens and state owners.
3. **Late dependency disclosure:** complete component requirements and missing size appear after download, in a setup picker, rather than as a reliable purchase/install-style summary on Store detail.
4. **Technical decisions:** file category, setup/recipe, encoder/VAE/TAE, quantization and endpoint are exposed without a general compatibility resolver.
5. **Inconsistent activation:** installed Ollama detail offers Use model; installed image detail offers a settings link and a further setup/load/save journey.
6. **Confirmation cost:** definition/credential/enable and primary/each companion/load/save can require separate deliberate actions. Some separation protects real shared effects; its presentation is still reviewable.
7. **Visibility vs density:** compact Downloads reduces clutter but puts causes and ownership in Info; connections hide most actions in overflow.
8. **Save semantics:** Apply/Discard concerns preferences, while loading and accepted downloads have independent effects. Discard cannot be a universal Undo.
9. **Recovery language:** unknown outcome, Check saved state, Check save status, Check loaded state and Check download status represent different checks that users must distinguish.
10. **No complete readiness proof:** file integrity, server capability and successful inference are distinct; the UI lacks one consolidated readiness view.

## 14. Copyable request for ChatGPT's research and redesign

> Review the attached description as the current implementation, not as a proposed design. I want an independent, evidence-based UX analysis of Store, Settings → Models, Settings → Models → Connections, and image-model installation through first successful generation.
>
> Research current professional app stores, package managers, model managers and creative/AI suites. Choose comparators based on the problem they solve. Distinguish transferable interaction patterns from attractive screenshots. Include real people's experiences from relevant community discussions, issue trackers or reviews, with direct links, dates and context; distinguish anecdote from broader evidence. Do not invent consensus or imply a source proves more than it does.
>
> First map the current information architecture and end-to-end tasks. Identify friction, inconsistent terminology, hidden prerequisites, error/recovery gaps and unnecessary decisions. Assess novice and expert paths, desktop and phone layouts, keyboard/screen-reader use, large downloads, low-memory hardware, remote servers, interrupted operations and shared runtimes.
>
> Propose a coherent target information architecture and explain the placement of discovery, installed inventory, connections, defaults, image-service setup, dependencies and downloads. Define the lifecycle vocabulary and UI states from Available through Ready, including incompatible, partial, paused, failed and unconfirmed outcomes.
>
> Provide annotated page layouts/wireframes, detailed user journeys, exact primary/secondary action labels, transition rules and examples of empty/loading/error/recovery copy. Address whether dependency planning belongs before the primary download, how to expose total size and compatibility, whether one reviewed install plan should cover multiple files, how individual recovery works, and how to preserve expert overrides without making them the default path.
>
> Preserve the product's local-first model, explicit authorization, exact artifact/source checks, honest capability claims, shared-runtime warnings, resumable transfers and safe unknown-outcome recovery. You may propose service/API changes; identify them separately from presentation changes. Do not assume that bundling steps permits silently switching models, replacing files, loading a shared runtime or changing defaults.
>
> Finish with a prioritized implementation plan: immediate copy/layout improvements, interaction and state-model improvements, and larger backend work. Include acceptance criteria and user-test tasks. Cite internet inspirations beside the recommendations they support. Clearly separate verified facts, user opinions, your inferences and design proposals.

## 15. Implementation references

Current source anchors:

- `apps/webhost/src/klaude_webhost/static/index.html`: Store controls, connection editor, role picker, Models and image-service sections.
- `apps/webhost/src/klaude_webhost/static/media.js`: `ModelsSettingsNavigation`, `BrowserMedia`, `IntegrationStoreUI`, `ModelStoreUI`, `RoleModelPicker`, `ModelConnectionsUI`.
- `apps/webhost/src/klaude_webhost/static/management.js`: `SettingsDraftState`, `SettingsDrafts`, Apply/Discard, conflicts and receipt checks.
- `apps/webhost/src/klaude_webhost/static/library.js`: `prepareChange`, shared review presentation/submission.
- `packages/application/src/klaude_application/image_dependencies.py`: exact curated companion coverage and unresolved requirements.
- `packages/application/src/klaude_application/image_model_store.py`: file-transfer lifecycle and destinations.
- `packages/application/src/klaude_application/image_model_selection.py`: server catalog, component/load/recovery contracts.

Relevant existing evidence, including historical changes and limits:

- `docs/webui/model_store/stable-diffusion-validation.md`
- `docs/webui/stable-diffusion-model-picker-validation.md`
- `docs/webui/image-model-dependencies-validation.md`
- `docs/webui/model_store/downloads-simplification-validation.md`
- `docs/webui/model_store/download-controls-validation.md`
- `docs/webui/model-defaults-validation.md`
- `docs/webui/store-integrations-validation.md`

Use current source to resolve differences between dated validation notes. No competitive research or fresh user-opinion survey is included in this descriptive handoff.
