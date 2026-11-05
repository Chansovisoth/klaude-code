# ComfyUI managed image bundles

Status: the managed checkpoint lifecycle is implemented: starter and custom
SD1.5/SDXL recipes, one-review Store installs, runtime reuse, picker/defaults,
repair, shared-file-aware model removal and checked recovery. SD1.5 has real GPU
and browser evidence; SDXL is explicitly device-unverified. FLUX/GGUF, additional
architectures and runtime version updates/removal remain outside these recipes.
Evidence: [ComfyUI validation](comfyui-validation.md).
The user selected ComfyUI and delegated bundle-installation decisions to Klaude.
This supersedes the LocalAI runtime direction.

## Product contract

The ordinary flow is **Store → Install → Choose model → Generate**. Klaude owns
the complete installation and builds the ComfyUI workflow internally. Users do
not select encoders, place files in directories or edit node graphs for a
supported bundle. Technical file and workflow details remain available in
Details. A bundle can share assets with other bundles; it need not be one archive.

Use Klaude-maintained, versioned recipes initially. Do not treat arbitrary
Hugging Face files, model-card instructions or downloaded workflows as recipes.
ComfyUI's own templates provide useful upstream references, but they are not
Klaude's executable installation authority. Its browser installation flow can
still require manually placing model files. Sources:
[templates](https://docs.comfy.org/interface/features/template),
[local API](https://docs.comfy.org/development/comfyui-server/comms_routes).

## The bundle and runtime are separate managed resources

- Runtime: a pinned ComfyUI release/commit, isolated Python environment, locked
  dependencies and a tested device-specific PyTorch build. Install this once,
  outside Klaude's own Python environment. Start a private loopback service on
  demand and retain its logs and exact process identity. Driver installation is
  a separate host action, never a surprise dependency operation.
- Bundle: primary weights, every required encoder/VAE/tokenizer/configuration,
  fixed workflow template, supported generation controls and tested defaults.
  Use built-in ComfyUI nodes in the first release. Custom-node installers and
  arbitrary Python/pip hooks are outside the ordinary bundle contract.
- The first model installation includes any missing runtime in the same review,
  with its download/storage requirements listed separately from model files.
  An unavailable size is displayed as unknown; it never contributes a fake zero
  to the total. Runtime package sources are pinned and reviewed before execution.

ComfyUI is GPLv3; preserve its license and notices when packaging it. Local
generation requires no subscription or paid API. Model licenses are separate
and shown before install. Prefer permissive weights for recommended bundles;
show actual restrictions and any source-site acceptance requirement before
starting a gated download. A pinned open-source version remains usable under
its license; ongoing upstream maintenance is not promised.
Sources: [license](https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE),
[isolated installation](https://docs.comfy.org/installation/manual_install).

## Immutable recipe contract

Each reviewed recipe contains the following bounded data, validated before use:

| Field | Contract |
| --- | --- |
| Identity | Stable bundle ID, immutable version, manifest digest, display name and architecture |
| Runtime | Exact tested ComfyUI/Python/PyTorch environment identity and node-schema expectations |
| Components | Role, pinned repository commit and file, SHA-256, exact bytes, license and source page |
| Mapping | Controlled ComfyUI model category and generated filename; no caller-supplied host paths |
| Workflow | Reviewed API graph template and digest; fixed output node and one output image |
| Controls | Allowlisted prompt, negative prompt, size, steps and seed bindings with validated ranges |
| Device profile | Tested device/runtime, RAM/VRAM observations, resolution and memory settings |
| Provenance | Recipe author/review version and compatibility/generation test evidence |

Never execute JavaScript, Python, package commands or arbitrary node graphs from
a model repository. Template placeholders are typed values, not text substitution
into executable code. Preserve a private exact binding from settings and jobs to
the bundle version, file digests, runtime and workflow; a friendly model name is
not an executable identity. Quantization presets are distinct bundle variants.

## Install interaction and lifecycle

1. Store detail offers one recommended preset when hardware evidence supports
   it, with other compatible presets under More options. Show additional
   download size, disk required including staging, and dated device evidence.
   Unknown hardware says Compatibility not checked and permits an explicit
   supported-profile choice. Do not infer VRAM needs from file size.
2. Install opens one review of the exact runtime/bundle version, required files,
   reusable files, licenses, storage and source links. Dependency rows are
   expanded in Details and retain individual progress and Pause/Resume controls.
   Required components cannot be unchecked in an installable bundle.
3. Accepted work progresses through Preparing, Downloading and Verifying.
   Reuse the owned transfer journal, bounded independent transfers and exact
   child receipts. Refresh/reload resumes observation; it never silently repeats
   an uncertain install. Show overall bytes only when all transfer sizes are known.
4. Verify actual bytes and hashes, runtime import/startup, required node schemas,
   and exact server file visibility. Publish the installed bundle record
   atomically only after the complete binding passes. A partially installed
   bundle offers Continue installation and cannot be selected for generation.
5. Completion shows Installed, Not yet generated and an explicit Choose model
   action. Installation does not load weights or change defaults. Choosing the
   bundle creates the existing Image model draft; Apply saves it.
6. The user's first explicit Generate is the inference test. Save successful
   output in Library and record dated generation evidence for that exact
   runtime/bundle/device/settings binding. No extra mandatory test image is
   generated during installation. An optional Generate test image is an explicit
   action. Distinguish installation checks from successful inference in all copy.

Usable installed bundles appear as ordinary model rows in the shared picker.
The selected row is first, followed by other installed models; incomplete
installs live in a separate Needs attention disclosure with Continue or Repair.
Do not mix raw files into the normal selectable-model list. Runtime connection
and process controls live under Advanced image settings; managed-local users
should not need to type a URL. Existing externally managed services retain an
explicit connection setup.

## Reuse, failure, updates and removal

- Keep an artifact registry keyed by SHA-256 and category, with controlled names
  visible to the managed ComfyUI model folders. Components shared across bundles
  download once. Track bundle references and exact materializations; filename or
  matching byte size is insufficient evidence of identity.
- Existing Klaude downloads are candidates for reuse. After explicit import,
  hash the regular file and match the recipe. Reuse it in place only if its root
  can be durably managed and read by this runtime; otherwise offer a reviewed
  copy and account for its full disk requirement. Never silently move or replace
  existing weights. Do not require symlinks in the initial implementation.
- Keep partial transfers in staging. Stop offers Keep partial downloads or
  Discard partial downloads with exact affected bytes. Completed verified shared
  files remain reusable. An acknowledgement loss retains the relevant fence and
  offers Check installation before any resubmission.
- Repair rechecks the exact installed version and retrieves only missing or
  corrupt components after review. Updates create a new bundle/runtime version;
  retain the working version until the replacement is installed and explicitly
  selected. Do not silently replace defaults or reinterpret old generation jobs.
- Remove bundle reviews exclusive files, shared files retained, active use and
  the currently selected default. Require an explicit default change if needed.
  Garbage collection removes only reviewed, unreferenced artifacts and staging;
  Library outputs and imported originals are independent resources.

## Compatibility and custom Store models

Start the vertical implementation with a small SD1.5 safetensors checkpoint and
only built-in nodes, using existing weights if their exact hash matches a
reviewed recipe. This is the control model for proving the complete lifecycle,
not a quality recommendation or a claim that it fits the current GPU. Then add
SDXL and a compact modern architecture after real device validation. Exact
source revisions, hashes and hardware recommendations must be established at
implementation time; this document does not authorize guessed model metadata.

For custom models, offer Set up model only when a maintained architecture recipe
can describe all requirements. Determine architecture from bounded supported
metadata and validate it against the selected recipe; never infer it solely
from a filename. Ask for a family only when detection is ambiguous, then validate
the candidate. Resolve/pin the complete dependency set before Install, including
mandatory model configuration where needed. Reject incompatible combinations.
Unknown architectures remain Download file with Setup not supported and a clear
reason. Start with safetensors; legacy pickle checkpoints need a separate,
explicitly supported import path. Importing an arbitrary ComfyUI workflow remains
Advanced work and cannot create a Recommended bundle automatically.

Read device/RAM/VRAM evidence from the actual ComfyUI server, not the browser or
Klaude host when remote. Recommend only tested device profiles with a documented
memory margin. An OOM offers a supported smaller preset or changed size after
review; it never silently switches models, installs another variant or stops
the user's Ollama/chat runtime. Installation checks are not a VRAM reservation.

## Generation ownership

Use the exact API graph and model bindings saved with the reviewed job. Poll
only its acknowledged prompt ID and fetch only its designated output from the
configured server, with bounded responses and image validation. Publish through
the existing Library generation boundary. Revalidate changed settings and
bundle/runtime bindings before submission and publication.

ComfyUI's documented interrupt operation targets current execution. A shared
server must not receive global interrupt/queue-clear calls as if they belonged
to one Klaude job. A private managed worker initially admits one owned generation
at a time. Prove exact process/execution ownership before a running cancel;
where scoped cancellation cannot be established, report tracking stopped and
cleanup unconfirmed. Lost submission acknowledgements remain unknown without
automatic replay. Prompt IDs and graph client IDs are not presumed idempotency
keys. These contracts must be checked against the pinned running API.
Source inspection of the v0.43.0 prototype target found a scoped
`/api/jobs/{job_id}/cancel` operation with atomic matching of the running job.
Prefer that contract after live verification; its presence does not authorize
a fallback to global interruption on an older server.

## Build sequence and acceptance gate

1. Read-only ComfyUI probe: version/node schemas, server/device inventory and
   model folders. Verify against a real pinned server plus malformed/older-host
   fixtures; keep ComfyUI unavailable in product pickers until generation works.
2. One complete vertical slice: immutable SD1.5 recipe, reviewed runtime setup,
   journaled bundle install/reuse/repair, atomic installed inventory, settings
   selection, exact graph generation, Library output and owned cancellation.
3. Connect Store and the shared picker to that single bundle inventory; remove
   the ordinary-flow need to open saved setups, select companions or load a
   shared server model separately. Preserve legacy file plans as their own data.
4. Add architecture recipes, custom-model setup, updates and removal after the
   first end-to-end slice passes. Expand the catalog based on real evidence.

Release gate: install from empty state, reuse verified existing files, select and
save a default, generate an actual image on the target machine, reload/restart,
recover a partial install, reject changed/corrupt components, preserve uncertain
outcomes, avoid cancelling unrelated work, and verify desktop/phone/keyboard UX.
Fixture success alone does not meet the live-generation gate.
