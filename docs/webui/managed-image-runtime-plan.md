# Image generation: ComfyUI and managed model bundles

## Decision

The user selected ComfyUI and delegated bundle-installation decisions to Klaude.
ComfyUI is the chosen local, free, open-source runtime integration target.
This supersedes LocalAI and InvokeAI as the intended ordinary image path.
The managed SD1.5/SDXL checkpoint lifecycle is implemented behind the
`image_comfyui` host capability. It has been installed and generated real output
on the target GTX 1650 in an isolated test profile; the production host and
defaults have not been switched.

The implementation contract is
[ComfyUI managed image bundles](comfyui-bundle-installation-design.md).

## User outcome

**Store → Install → Choose model → Generate.**

A Klaude-maintained bundle contains all required weights/configuration and a
reviewed ComfyUI workflow. One install approval covers missing dependencies and,
on first use, the managed runtime. Verified shared components download once.
Installed bundles appear in the ordinary Image model picker without manual
folder placement, encoder selection, node editing or a separate Load action.
Selecting creates a settings draft; Apply saves the exact bundle selection.
The first explicit Generate supplies actual inference evidence. Installation
alone never claims successful generation.

ComfyUI runs in an isolated, pinned environment as a managed local service.
The normal path requires no URL entry, subscription or external paid API.
Model licenses and host hardware/electricity costs remain separate. Built-in
nodes are the initial scope; arbitrary custom-node/package installers are not
part of ordinary model installation. Sources:
[license](https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE),
[isolated installation](https://docs.comfy.org/installation/manual_install),
[server API](https://docs.comfy.org/development/comfyui-server/comms_routes).

## Existing implementation and migration

The current stable-diffusion.cpp path downloads individual files into Klaude's
host directory. The image server may not see that directory, may need separate
encoders or a VAE, and holds a shared loaded runtime. Group approval improves
transfer control but does not make those files directly selectable bundles.

Reuse its reviewed download fingerprints, per-file transfer ownership, progress,
pause/resume, recovery, settings reviews and Library output validation. Bundle
records require a distinct versioned schema and resource ownership; never
reinterpret legacy install-plan or saved-setup identities as ComfyUI bundles.
Existing files are reuse candidates only after exact hash and runtime visibility
checks. Provider switching and imported-file reuse remain explicit user actions.

Settings leads with Image model and complete managed bundles. Service
connection controls, including stable-diffusion.cpp, live in Advanced image
service. The stable-diffusion.cpp picker groups loaded models, saved setups
and downloaded files requiring setup. This legacy path remains available while the managed bundle path requires
no server URL or component selection.

## Native Ollama status

Ollama's [image-generation announcement](https://ollama.com/blog/image-generation)
describes native image models as experimental and macOS-only, with Linux and
Windows planned. Its [0.32.6 release](https://github.com/ollama/ollama/releases/tag/v0.32.6)
temporarily removed the experimental runner. Klaude already has an experimental
Ollama image adapter, but advertised model metadata does not prove the runner
works. Reconsider after documented support and actual generation on the configured
server. A ComfyUI/Open WebUI integration still needs an image backend and does
not make arbitrary Stable Diffusion files into native Ollama models.

## Current acceptance and next work

The pinned SD1.5 bundle now covers runtime installation, selection, reviewed
default saving, actual generation and Library output. See
[validation](comfyui-validation.md) for the exact runtime and evidence.
SDXL still requires real device inference validation. Additional architectures,
including the existing Unsloth FLUX 3 GGUF, and a richer bundle catalog require
separate maintained recipes and device tests. See `comfyui-gguf-gap.md`. Use existing weights
only if their hash matches the reviewed recipe. Confirm the actual target GPU,
driver, RAM and disk before selecting the runtime build or recommending a model.
Implement the lifecycle and acceptance gate in the bundle design before expanding
the catalog. A connection check, file download or fixture image is insufficient
to claim that the real installed model works.
