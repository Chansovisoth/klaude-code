# ComfyUI implementation evidence

Date: 2026-10-30. The first complete managed bundle is **Stable Diffusion 1.5**.
This now includes the custom checkpoint lifecycle and a direct, one-review
Store install/select/generate path, with actual GPU and browser validation in an
isolated profile. Production services/defaults were not switched.
Complete SD1.5 and SDXL checkpoint recipes are implemented; SDXL has metadata
and fixture coverage and remains device-unverified. Runtime updates/removal and
FLUX/GGUF are separate work, described below.

## Exact runtime and model

| Item | Verified identity |
| --- | --- |
| ComfyUI | v0.43.0 |
| Source commit | `426f5eea52a7ece1dd599fff4cb6cd1f352ddd24` |
| Source archive bytes | `12830180` |
| Source archive SHA-256 | `96c0680fa97ae0f6a0cb23ae8f24347e076eb535b9b3292efcb4a98d72d67ce1` |
| Runtime build | Linux x86_64, Python 3.12, Torch 2.9.1+cu126, torchvision 0.24.1+cu126 |
| Packaged dependency lock | `packages/core/src/klaude_core/data/comfyui/linux-cu126.lock` |
| Lock SHA-256 | `8c1ebbe4d8f08347557478b049933d508c21e5e1e7e348b05b3a6ab8f901c335` |
| Model repository | `stable-diffusion-v1-5/stable-diffusion-v1-5` |
| Model revision | `451f4fe16113bff5a5d2269ed5ad43b0592e9a14` |
| Model file | `v1-5-pruned-emaonly.safetensors` |
| Model bytes | `4265146304` |
| Model SHA-256 | `6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa` |
| Weights license | CreativeML OpenRAIL-M |
| Managed model identity | `sd15-control@1` |

The target is GTX 1650, 4096 MiB VRAM, driver 595.99.02, compute capability 7.5.
Native Torch reported CUDA available, included `sm_75`, and completed a GPU tensor
operation. The application environment was not given Torch dependencies; ComfyUI
uses its own environment. In-sandbox NVIDIA failures did not describe the host.

The existing checkpoint under `/mnt/HDD1/klaude-image/models` matched the pinned
SHA-256 in full. The installer copied and reverified it into its controlled model
category; the source was not moved, overwritten or downloaded again. ComfyUI
starts on private loopback with low-VRAM settings, offline APIs and custom nodes
disabled. Pinned source extraction retains the upstream license/notices.

## Implemented product flow

Store and Image generation settings expose a complete bundle install. One exact
review covers the pinned source, dependency lock and checkpoint, actual model
bytes/license, unknown runtime download size and a minimum 12 GiB setup allowance.
Installation uses hash-required binary packages in an isolated environment and
verifies the checkpoint, server version, built-in schemas and file visibility
before publishing its private installed record. It does not load weights, run a
hidden test image or change defaults.

The shared Image model picker lists the installed bundle. Choose model creates
an image-settings draft; Apply uses the existing reviewed, witnessed settings
writer. The endpoint is the symbolic `managed`, not a user-supplied server URL.
Settings retains a model row and generation toggle; legacy service controls are
under Advanced image service. Additional installation/repair controls remain in
Store. Legacy downloaded-file plans and saved setups retain their identities.

The owned installer reports stages/byte progress and retains partial transfers.
Pause stops owned work; Check installation compares the exact installed/prior
record under the exclusive installer lock before another explicit attempt.
Installer subprocesses inherit that lock, so a surviving installer prevents an
unsafe recovery. An interrupted repair marks the old installation unavailable
until setup finishes. Active workers, unfinished managed receipts and queued or
running engine work prevent repair from replacing a live engine.

Generation submits exactly one fixed built-in SD1.5 graph and persists the
acknowledged UUID. History must match the reviewed graph and client ID. One output
node, controlled filename/subfolder and bounded PNG retrieval feed the existing
pixel/dimension, settings-binding, provenance and Library publication checks.
There is no automatic replay after an uncertain submission. Explicit recovery
retrieves only the saved job. Cancellation uses only `/api/jobs/{id}/cancel`;
there is no global interrupt or clear-queue fallback. Successful output records
inference evidence for that exact installation; repair invalidates old evidence.

## Actual generation and browser evidence

The installer ran through the application journal in
`/tmp/klaude-comfy-live-profile`. A real 512×512, 20-step, seed-42 image completed
and was saved into that profile's Library. Output:
`/tmp/klaude-comfy-live-profile/comfyui-sd15-verified.png`.
The first source-shaped schema check exposed SaveImage's actual `IMAGE` return
contract in this pinned release; the contract and fixture were corrected before
installation passed. Metadata matching alone was never treated as inference.

The real browser walkthrough cancelled an installation review without changing
defaults, chose the bundle, opened the shared picker, applied its exact defaults,
reloaded and generated another real 512×512 image into Library. Screenshots cover
320/390/768/1440px, including phone layouts with navigation closed. No browser
JavaScript errors were recorded. Reproduce against an explicitly prepared test
profile using `scripts/webui_comfyui_smoke.py --profile /tmp/...`.
`--exercise-install` also passed the actual worker's pause, checked recovery,
continued installation and subsequent real generation. This exposed and fixed a
refresh/polling race while the original install remained unconfirmed; `--layout-only` avoids another generation.
The script refuses profiles outside `/tmp`.

A separate real-server cancellation check submitted two exact test jobs. The
second was queued; cancelling it left the first running. Cancelling that running
job reached a confirmed cancelled history state. No global interruption was used.
The pinned server removes a cancelled queued item without history. The adapter
now confirms an acknowledged removal after repeated bounded queue/history checks
and persists that receipt; refresh does not turn a confirmed cancellation unknown.
The earlier conservative abandonment behavior has been replaced and regression tested. Production jobs were not
targeted.

The existing SD picker browser smoke also passed at 320/390/768/1440px: reviewed
load, independent default save, empty catalog and older-host fallback, with zero
JavaScript errors. This confirms the retained advanced path still works.

## Focused automated checks

159 tests passed together across the ComfyUI installer, probe, image adapter,
web authorization, existing Ollama/image generation and model-settings suites.
The suite includes the custom checkpoint lifecycle, bounded remote header reads,
runtime reuse, interrupted cleanup and checked-read recovery tests. Coverage includes lost acknowledgements/non-replay, exact recovery,
retained partial work, pause/fence checks, interrupted-repair visibility, unfinished
job protection, cross-job output rejection, scoped cancellation and metadata-route
authorization. Focused Ruff, source mypy with imported errors suppressed, Node
syntax, the CSS bundle check and `git diff --check` are the validation scope.
This is not a full repository test run or a production deployment.

## Boundaries

- Maintained recipes cover the starter SD1.5 bundle and complete SD1.5/SDXL
  safetensors checkpoints. SDXL remains unverified on this GPU. Split weights,
  GGUF, LoRA and other architectures do not become selectable bundles implicitly.
  The existing Unsloth FLUX 3 GGUF needs the separate work in
  [GGUF compatibility gap](comfyui-gguf-gap.md).
- The tested build targets Linux x86_64 with NVIDIA CUDA. CPU, AMD, Windows and
  macOS builds, other devices and larger resolutions require their own evidence.
- Runtime transfer size remains unknown in the review. Free disk is not reserved;
  cache/staging needs may vary, and dependency tools can report insufficient space.
- Runtime version updates/removal, other architecture recipes, a larger curated
  catalog and distribution packaging remain separate work. Model removal and
  shared checkpoint retention are implemented. Existing model files
  and stable-diffusion.cpp service have been retained.
- Initial preflight-only evidence was 52 tests and an unavailable server before
  this runtime was installed. It is superseded by the real evidence above. The
  read-only development probe remains deliberately unable to certify installation
  or inference by itself.

Sources: [pinned server](https://github.com/Comfy-Org/ComfyUI/blob/v0.43.0/server.py),
[pinned nodes](https://github.com/Comfy-Org/ComfyUI/blob/v0.43.0/nodes.py),
[API example](https://github.com/Comfy-Org/ComfyUI/blob/v0.43.0/script_examples/basic_api_example.py),
[model card](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5).


## Custom checkpoint lifecycle validation

Store now offers Install for image generation for a supported exact safetensors
variant before its primary download. Review reads only two bounded pinned Range
responses (8-byte length and at most 8 MiB of tensor metadata), verifies the
complete maintained family, and includes the runtime when missing. A real read
against the pinned public Hugging Face checkpoint passed. Sources without a
bounded Range response retain Download file and explicit unsupported-setup guidance.
The same header parser checks local Store files without importing tensor libraries.

Completed Store downloads are adopted only through their settled private witness,
exact root identity and stable file signature. The owned worker carries that
reviewed directory snapshot rather than relying on ambient environment variables.
The final whole-file checksum and architecture are checked before publication.
A new checkpoint reuses the existing runtime and verified same-content assets;
it does not install an unnecessary starter model. Incomplete drafts survive for
explicit repair, including re-downloading the original immutable source if the
Store copy is unavailable. Unsupported files never appear as selectable models.

The live browser test `--exercise-custom` passed local Store adoption, picker
selection, Apply/reload, actual generation, clearing the default and shared-file
removal. `--remote-custom` additionally passed the one-review pinned-source path
against the real source, reusing already verified model bytes. The test uses the
verified SD1.5 weights as a second exact Store recipe to exercise shared ownership;
it is not a claim of independent-model or SDXL inference validation. Original
Store bytes and the starter's shared checkpoint survived removal, as did Library
output. These tests and legacy advanced-picker checks recorded zero JavaScript
errors. The updated pause/check/continue browser check also observes checked reads
across their separate operation state.

Removal is serialized with image-default writes. A selected model must first be
changed or cleared through No image model and Apply. An interrupted removal keeps
its resource fenced and can finish only its reviewed managed-file cleanup after
checking current references, idle state and exact file signatures. No original
Store file, other model or Library artifact is a deletion target. Historical
inference observations are bounded and keyed to the exact installation.
