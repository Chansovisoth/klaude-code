# Existing FLUX 3 GGUF: remaining integration gap

Inspected on 2026-10-30. The downloaded primary is
`diffusion_models/unsloth/flux-3-image-klein-GGUF/flux-3-image-klein-Q6_K.gguf`
(4,799,886,240 bytes), with a Qwen3-VL-4B GGUF encoder (2,497,281,664 bytes)
and FLUX.2 VAE (336,213,556 bytes). Their original files were not changed.
A bounded local metadata read found GGUF v3, 359 tensors, architecture `flux`,
source format `pt` and model identifier `f3-image-small`.

The implemented managed checkpoint recipes accept complete SD1.5/SDXL safetensors,
not this split quantized pipeline. The file must not be shown as a ready managed
model merely because the download and companion files are complete.

The [publisher model card](https://huggingface.co/unsloth/flux-3-image-klein-GGUF)
documents Diffusers/Unsloth loading and original BFL tensor names. This does not
prove incompatibility with ComfyUI. The current
[ComfyUI-GGUF loader](https://github.com/city96/ComfyUI-GGUF/blob/main/loader.py)
accepts the `flux` architecture and has a GGUF text-encoder path; actual tensor
layout, node contracts and inference need verification. The
[BFL reference](https://github.com/black-forest-labs/flux-3-image-klein)
also requires its prompt upsampler for the intended prompt behavior. The current
three downloaded components do not establish that complete pipeline.

To support this exact model:

1. Pin and review a compatible GGUF extension source and its hash-locked runtime
   dependencies. Whitelist only that reviewed extension while retaining the ban
   on arbitrary custom nodes and package hooks.
2. Verify the exact primary/encoder/VAE versions and tensor layouts; resolve and
   pin the required prompt-upsampler recipe and assets. Do not infer compatibility
   from names or substitute another model without review.
3. Maintain a fixed graph and strict schema/provenance probe for those nodes,
   with exact component and job/output bindings. Keep legacy plan IDs unchanged.
4. Measure actual memory and complete real generation on GTX 1650 4 GB, with
   bounded offloading, cancellation and recovery. File size is not a VRAM estimate.
5. Only then publish an installable managed FLUX 3 recipe and picker row.

This file records unfinished work; it does not claim GGUF generation, hardware
compatibility, a complete installation or an upstream impossibility.
