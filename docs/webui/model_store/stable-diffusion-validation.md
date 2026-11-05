# Stable Diffusion Model Store

Model Store's Runtime filter selects Ollama or Stable Diffusion. Stable Diffusion
reuses Discover, Popular/Recently updated collections, search and cursor paging,
the full model-details page, exact-file confirmation, Downloads progress/Stop,
history dismissal and Check status. Runtime and selected files survive detail
reloads; metadata/cursors are isolated between the two runtimes.

Runtime also offers All. It combines bounded pages from both existing catalogs,
splits the requested page size between their independent cursor chains, and sorts
the visible metadata by the chosen ordering. Each card retains its runtime badge;
the same repository can appear for both runtimes without losing either entry.
Exhausted-source page markers survive reloads in tab history. Combined results
omit global rank numbers because each runtime contributes its own bounded page.
All Installed combines the selected native Ollama endpoint with the local image
directory. A partial failure retains the available inventory, explains the missing
results and hides an unknown total. Opening a card enters its existing single-
runtime detail/review flow; Back restores All. No new backend route or restart is
needed, and the existing Ollama default remains.

The browser requires `model_store_sdcpp_revision: 1`, including for restored detail
URLs. An early host that advertises only `model_store_sdcpp: true` cannot handle
the final `image:sdcpp` target contract. It now shows restart guidance and sends
no image Store requests. This prevents fresh static assets from showing a generic
server error against an older in-memory backend.

The Hugging Face text-to-image catalog is metadata-only. Details offer bounded nested
GGUF and Safetensors files with known size and LFS SHA256, excluding split files,
subdirectory weights, projector files, pickle checkpoints and files over 64 GiB.
The review freshly resolves the exact file and pins its repository commit,
checksum, size and host-directory identity. A catalog entry is not a guarantee
that stable-diffusion.cpp supports that architecture or that the file contains all
required components. Source model cards remain linked.

Downloads require an administrator and the existing CSRF/Origin/review guards.
The host's `KLAUDE_IMAGE_MODEL_DIR` must be an absolute existing writable directory;
its default is `/mnt/HDD1/klaude-image/models`. Downloaded files are stored under
`checkpoints/OWNER/REPOSITORY/FILENAME`. These are host downloads: remote image
servers need access to that directory. Downloading never changes the active
image server, image settings, chat model or model defaults. Load the file and any
required components using the image server, then test/save the image service in
Settings → Models → Image generation.

The shared operation journal and owned subprocess retain durable receipts,
private exact targets and unknown-outcome fences. Transfers have an 1800-second
deadline, bounded chunks, progress and preflight disk checks. Redirects stay on
the configured Hub origin or HTTPS Hugging Face CDN domains; ambient proxy and
credential settings are excluded. The worker validates length and SHA256 before
atomic no-overwrite publication. Descriptor-relative filesystem operations reject
symbolic links; per-target exclusive locks serialize each file's worker and recovery. A shared
root migration gate excludes legacy workers; independent targets can transfer
concurrently within the shared four-worker capacity. Stop
reaps the process before checking its local outcome. Recovery verifies a matching
private journal witness and complete file hash, or exact absence, without replay
or network calls. Changed files/targets, replaced or missing roots and active
workers retain their fences. Dismissing history never deletes weights.

Installed lists bounded local metadata, including existing `.ckpt`/`.sft` files;
it does not infer architecture or read model contents. Gated repositories requiring
credentials, directory bundles, split downloads, automatic loading and image-file
deletion remain unsupported.

Validation uses tiny synthetic weights and temporary directories, never the real
host model directory or an inference service:

- Focused Store backend checks: 57 passed, plus 4 Hugging Face integration tests.
- New real-worker coverage includes metadata-only browsing/review, pinned transfer,
  exact inventory, duplicate request IDs, checksum failure, rejected redirects,
  no overwrite, symlink swaps, Stop/partial cleanup, durable history dismissal,
  exact unknown recovery, changed targets/files/roots, active-worker locks,
  admin/CSRF guards and rejection of arbitrary sources.
- Ruff, JavaScript syntax and focused production mypy checks passed.
- Browser smoke passed at 320/390/768/1440px in light/dark themes with zero console
  errors, including detail reload, reviewed download, Stop/partial cleanup, retry,
  Installed, return to Ollama and the old-host capability fallback. The smoke uses
  `scripts/webui_image_model_store_smoke.py`; captures are stored in
  `/tmp/klaude-image-model-store-evidence`.
  Additional All checks cover mixed/runtime-labelled cards, shared repository
  identities, independent continuation chains with one exhausted source, search,
  page-two reload, correct detail/review routing, Back, combined Installed and a
  temporarily unavailable image inventory. No real weights are fetched.

References checked during implementation:

- [Hugging Face Hub API](https://huggingface.co/docs/hub/en/api) for bounded catalog
  and exact repository/file metadata.
- [stable-diffusion.cpp native model management](https://github.com/leejet/stable-diffusion.cpp/blob/master/examples/server/api.md#model-management)
  for checkpoint directories and the separate model-loading contract.

The initial fixture checks performed no production restart. After the reported
inventory failure, live inspection confirmed that the managed host had started
before the final namespaced download contract. It was idle with an empty queue
and no leased background operations. The owner control socket stopped it, and
the supported managed launcher resumed the exact saved session and workspace,
retaining LAN exposure. The updated host reports image Store revision 1.

A temporary local administrator login verified HTTP 200 for the actual host's
image inventory (one existing file), the live image catalog (one fresh metadata
result) and the same saved session. The test login was signed out afterward.
The browser smoke also passed with an early host that declares the old boolean
capability but lacks the required contract revision, sending no image requests.

No real multi-gigabyte transfer or live inference was performed.

## Unrelated Skill fences and MLX variants, 2026-10-29

A live user download was rejected before admission by journal-wide exclusivity.
Read-only inspection found three unknown Skill receipts and no pending model
operation. Image file downloads now retain the model-work resource fence and
locked, checksum-verified publication without journal-wide exclusivity. Other
model operations keep their existing coordination. Unknown Skills are untouched.

Explicit MLX filename variants are excluded from SD metadata and cannot be
reviewed as image downloads. SD detail metadata has a versioned cache to refresh
older variant listings. This narrow exclusion does not promise compatibility of
all other Safetensors files or install companion encoders/VAE automatically.

Regression coverage includes successful publication alongside an unchanged
unknown Skill, MLX review rejection, and continued refusal of a second download
when the model-work resource is unknown. Backend source changes require a WebUI
restart. No historical receipt was settled and no large user model was downloaded.

## Retry and retained byte ranges, 2026-10-29

Failed/cancelled owned image-download rows offer Retry download. This opens the
normal exact-file review with a new request ID; it does not replay an unknown
receipt. Fresh source metadata is pinned again. Retained bytes are keyed by the
reviewed SHA256, so changed content does not adopt an older prefix.

The locked worker rehashes a regular, owner-owned, singly-linked partial before
issuing Range. A 206 must identify the exact requested start, final offset and
reviewed total size. A 200 restarts rather than appending a full response.
Complete partials are verified without redownloading. Incomplete transfers retain
nonempty partials; checksum/oversize failures discard corrupt data. Final verified
publication remains no-overwrite. Disk checks account for retained bytes.
Explicit Stop and uncertain-operation reconciliation retain their existing owned
partial cleanup. Older failed downloads may have no remaining bytes to resume.

Validation: 24 download tests passed, including interrupted transfer/resume,
Range-ignored fallback and malformed Content-Range rejection. The browser smoke
clicked Retry on a stopped download, reviewed a new attempt and completed it at
320/390/768/1440px with zero console errors. Additional tests check complete and
corrupted retained prefixes. JavaScript syntax, Ruff and whitespace checks passed.
The user's old FLUX-3 directory had no remaining partial file. No live download
was started and the production host was not restarted.

## Pause/Resume controls, 2026-10-29

Supersedes the earlier Retry review interaction above. Running image-download
rows show Pause immediately left of the Stop cross. Settled rows show Resume
immediately left of the history-removal cross. Paused state uses existing terminal
journal states plus private durable metadata; no parallel job registry is added.
Pause saves intent, requests cancellation and reaps the owned worker, then
reconciles under the directory lock while preserving its partial bytes. An
uncertain stop remains fenced and needs checking before Resume is offered.

Resume authenticates the terminal receipt's target against its original HMAC
witness and starts a new request for the identical pinned revision/checksum.
It performs no fresh source lookup or confirmation. A deterministic internal
review identity makes repeated new request IDs deduplicate correctly. The old
worker stays terminal. Altered targets and active conversations are rejected;
admin/Origin/CSRF, file verification and resource/root checks remain in force.
On admission the old row is dismissed without discarding bytes. Explicit Stop
keeps its discard-partial behavior. Older hosts omit Pause until restarted.

Validation: 35 image-download/shared-journal tests passed, plus focused follow-ups
for changed targets and active-conversation guards. The responsive Store browser
smoke passed with zero console errors; it checks left-to-right button geometry,
retained files after Pause, direct Resume without confirmation, and successful
publication. No production download was paused, stopped or resumed during testing.


Explicit companion downloads can now carry a validated category (checkpoints,
diffusion_models, text_encoders, vae, vae_approx). Category is included in new
private target witnesses; older receipts retain their exact original witness
shape. Bounded nested image files are read as metadata and installed through
no-follow directory descriptors. Full directory bundles, split weights and
scripts remain unsupported. See `../image-model-dependencies-validation.md`.
