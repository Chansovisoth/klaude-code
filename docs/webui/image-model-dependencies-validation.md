# Image model dependency offers

Choosing a recognized setup with unfilled requirements shows **Required components** in the Image Model picker. Offers show source links, filenames,
individual sizes and the total missing size. Each component has an Install
button using the existing exact-file review; declining has no effect. This first
version intentionally reviews individual files rather than submitting a bundle
that could leave an ambiguous multi-file outcome.

Initial curated profiles are FLUX.3 Image Klein and its Base variant:

- Qwen3VL-4B-Instruct-Q4_K_M.gguf from Qwen/Qwen3-VL-4B-Instruct-GGUF,
  installed in text_encoders.
- split_files/vae/flux2-vae.safetensors from canonical repository
  Comfy-Org/Flux-2-Dev, installed in vae.

These follow the native [FLUX-3 component documentation](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/flux3.md).
No model-card instruction parsing, arbitrary scripts or guessed dependencies are
used. Metadata is bounded and resolved to an immutable revision/checksum again
at review. A selected TAE satisfies the VAE alternative and suppresses that
extra offer. Unknown recipes report unresolved requirements without downloads.

The admin-only, CSRF/Origin-protected image-dependencies endpoint validates the
partial selection against the server's current recipe and file inventory. It
only reads metadata. The image_model_dependencies capability hides the feature
on older hosts. Failed reads offer Retry dependency check using safe errors.

Approved transfers retain the existing owned worker, journal/resource fence,
Pause/Resume, checksum/size verification, disk checks and no-overwrite publication.
Category is authenticated as an optional new private target field. Older targets
without it still mean checkpoints and retain their original HMAC witness shape.
Image metadata can include bounded nested weight paths; every destination path
component is opened relative to a no-follow descriptor. Source subfolders are
preserved, and inventory traversal stays bounded. Neither complete directory
bundles nor split model shards are installed automatically.

Independent components can download together within the shared four-worker
capacity. The picker retains each component row with its own progress and
Pause/Resume controls, and Store → Downloads remains available. Completing a file
rescans server metadata and fills its empty component slot without replacing a
user-selected alternative. Existing files still offer Use installed. Loading
weights and saving defaults stay separate reviewed actions.

New transfers fence and lock the physical root identity plus destination path,
so aliases cannot bypass duplicate-target protection. A shared migration lock
excludes older workers holding the legacy exclusive root lock. Legacy unknown
global receipts remain fenced. New partial names distinguish same-content files
with different filenames; an older checksum-only partial can be adopted under
the target lock. No accepted download is automatically replayed.
Closing the picker leaves accepted work owned by the host; there is no hidden
client retry or automatic dependency continuation. Unknown outcomes stay fenced.

Validation:

- 69 focused checks passed across dependency offers, transfers, model selection,
  application operations and catalogs, including legacy-lock compatibility.
  They cover explicit read-only offers, no guessed sources, selected TAE, installed
  alternatives, CSRF, partial-selection validation, nested category publication,
  traversal rejection and old download/recovery behavior.
- scripts/webui_image_dependencies_smoke.py passed at 320/390/768/1440px with zero
  console errors. It declined the first offer with zero transfers, approved two
  separate reviews, ran actual small worker downloads into the correct folders,
  transferred both files concurrently, paused/resumed one while the other remained
  running, refreshed the picker and automatically filled both slots. Automatic
  runtime loads: zero.
- Live metadata planning against the installed FLUX-3 setup resolved the actual
  public encoder (2,497,281,664 bytes) and VAE (336,213,556 bytes), total
  2,833,495,220 bytes. No production weights were downloaded or loaded. This check
  caught and corrected a canonical-case repository redirect.
- Touched Python passed Ruff; JavaScript syntax and whitespace checks passed.

To activate this backend change, pause any active downloads, use Settings →
System → Restart Klaude, then reload and resume the paused downloads. Production
workers were not interrupted during validation. This validation does not claim that a full FLUX-3 generation
has run or that every architecture has a dependency profile.
