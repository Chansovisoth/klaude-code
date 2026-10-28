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

The Hugging Face text-to-image catalog is metadata-only. Details offer top-level
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
symbolic links; an exclusive root lock serializes workers and recovery. Stop
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
