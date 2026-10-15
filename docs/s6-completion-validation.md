# S6 completion work: AI tags, image jobs and native CUDA validation

Date: 2026-10-15. Continues the
[S6 delivery plan](odysseus-settings-and-features-plan.md#s6--vision-and-image-generation-through-library--media)
and [native CPU generation evidence](s6b-local-generation-validation.md).
Base revision: `0234b116f4380cb87c1b1cf39959725493e227ee`, with the existing
uncommitted S5/S6 implementation retained as the source of truth.

The original S6 continuation authorized work across the remaining slices without
another “continue” at each boundary. The subsequent phase-verification request
explicitly authorizes a reviewed checkpoint commit/push to main. WebUI
implementation and unrelated worktree cleanup remain outside this work.

## S6c: optional AI tags

### Product behavior

- **Library → Media → image detail → Suggest AI tags** reuses the existing
  explicit Vision model/fallback selection, capability inspection, budgets,
  private image reads and owned cancellable worker. Vision starts OFF; there is
  no background tagging on import, generation, browsing, indexing or session load.
- The form exposes context/output budgets and Vision settings. A Back-focused
  review identifies the exact image, endpoint/models and deadline before pixels
  are sent. The fixed request asks for visible objects, colors and style only;
  image text remains untrusted input. No agent tools or history are supplied.
- Proposals require a bounded JSON array, optionally inside one exact JSON
  Markdown fence. Tags are deduplicated without case, printable, at most 40
  characters each and cannot contain commas. Noisy/truncated/invalid responses
  fail without saving tags or automatically repeating a model call.
- Suggestions initially remain **unselected**. Save is disabled until the user
  selects a tag; manual duplicates cannot be selected. Saving selected tags is
  an explicit, local-only operation and does not call the model again.
- Manual tags retain their existing `tags` field. AI tags use a separate
  `ai_tags` projection, backed by the private artifact SQLite `image_tags` table.
  Up to 20 retained AI tags can be appended across accepted proposals. Each tag
  retains its actual model/endpoint, timestamp, method and reviewed budgets.
- Manual tags are never overwritten. A later manual edit that promotes an AI
  tag removes its AI duplicate/provenance. **Clear AI tags** removes only AI
  labels and their provenance, retaining manual tags and image bytes.
- Artifact detail and metadata search/listing distinguish manual and AI tags.
  Archive/restore retains both; permanent artifact deletion removes associated
  AI metadata in the same transaction. Exported image bytes remain unchanged.
- Read-only browsing of an older store does not migrate or modify it. An
  explicit artifact write creates the additional table. Applying proposals
  rechecks image checksum, revision and archive state, followed by an atomic
  database comparison. A stale proposal cannot overwrite newer user changes.
- Model suggestions are fallible metadata, not facts or learned knowledge.
  No embeddings, knowledge index, automatic chat context or additional role is
  created. Existing Vision provider restrictions and privacy bounds remain.

### CLI

```bash
klaude library suggest-tags MEDIA_ID
klaude library suggest-tags MEDIA_ID --save --select 1,3
klaude library clear-ai-tags MEDIA_ID
```

`--context` defaults to 4096; `--output-tokens` to 512. Existing Vision bounds
apply: 2048–32768 context, 128–2048 output, PNG/JPEG up to 8 MiB, 4 megapixels,
4096 pixels per side and 90 seconds generation per reviewed model. The CLI's
`--yes` accepts the displayed operation; `--save` must additionally be present
to retain tags. Without `--save`, suggestions are displayed only. `--select`
uses numbered suggestions and requires `--save`; absent selection saves all
suggestions after explicit approval. CLI completion/decline/error/Ctrl+C use
0/0/1/130 through the existing owned worker.

### Real local-model evidence

Driver: `/tmp/klaude_s6c_live.py`.
Final log: `/tmp/klaude-s6c-live-final.log`.
Receipt: `.klaude/data/s2-models-rcb3p2_y/s6c-receipt.json`.

This used the **actual installed native Ollama `gemma4:e2b`** and the real
512-pixel diffusion-generated duck from S6b2, not canned model responses.

- CLI proposal-only generation: **4.66 s**, no AI metadata mutation.
- CLI explicitly saved one numbered tag: **4.59 s**, manual `keep-manual`
  retained; AI metadata search found the stored image.
- Declined clearing retained tags; accepted clearing removed only AI tags.
- Bare TUI session **TEST KLAUDE FEATURES S6C TAGS** exercised request reviews
  at 40/70/120 columns, Enter on Back, initially unchecked suggestions, explicit
  checkbox selection/save and clean Ctrl+D exit 0.
- The TUI retained the explicitly selected `plastic` tag alongside the manual
  tag. Other suggestions were not implicitly saved. Workspace sentinel and
  image checksum were unchanged; no user/assistant chat turns were created.
- Early harness attempts used the wrong initial settings comparison or waited
  for a result heading that was above the viewport. The corrected harness waits
  for the visible save row. These were harness failures, not claimed passes.
- A real navigation regression introduced during implementation was caught by
  the existing artifact-detail test: duplicate `manual-tags` row IDs prevented
  opening detail. The duplicate was removed and the 46-test affected selection
  passed afterward. Separate manual/AI metadata remains visible exactly once.

Implementation: core `image_tags`, `vision.execute`,
`library_artifacts.ArtifactStore`; CLI `library_commands`, `vision_panel`,
`library_artifact_panel`; canonical command definitions in `main`.

## S6b3: image-job inventory, status and deliberate receipt cleanup

### Product behavior

- **Library → Media → Image jobs** lists saved private receipt metadata, including
  job identity, saved state, date/model. Merely opening/reloading the inventory
  performs no network or generation, and list output never includes prompts.
- A selected job reveals its original endpoint/model/prompt and saved artifact.
  **Check server status** explicitly GETs only the acknowledged native ID;
  status checks neither cancel nor resubmit generation or import completed pixels.
- **Review job cancellation** and **Review receipt removal** are separate,
  Back-focused reviews. Cancellation remains job-scoped and honest about native
  running-cancel limitations. Completed output uses the existing explicit
  recovery flow rather than resubmission.
- Removal deletes only the exact private job receipt, including its prompt and
  recovery reference. Media images/provenance and server jobs remain independent.
  Active or unknown receipts are protected by default. If a server expired/lost
  the job or no ID was acknowledged, an additional unchecked **Abandon local
  tracking** confirmation permits deliberate cleanup without claiming the remote
  work stopped. An active client may recreate its receipt. Completed remote
  output can be abandoned after review of the lost recovery reference.
- Removal rechecks the complete reviewed receipt inside its write lock. A
  concurrent update requires a fresh review. The inventory is paged in groups of
  100 with a 1000-receipt scan bound; malformed receipts are counted and omitted.
  Exact-ID inspection remains available if the inventory exceeds its bound.
- After removal, the inventory returns to its first page with the removed job's
  old picker filter cleared. A live walkthrough caught that stale filter hiding
  the empty-state message; this was corrected before the successful rerun.

```bash
klaude library generation-jobs
klaude library generation-jobs --offset 100
klaude library generation-status JOB_ID
klaude library generation-status JOB_ID --refresh
klaude library generation-status JOB_ID --cancel
klaude library generation-status JOB_ID --recover
klaude library generation-status JOB_ID --forget
klaude library generation-status JOB_ID --forget --abandon
```

The four action flags are mutually exclusive; --abandon requires --forget and
explicitly accepts unknown/active local-tracking loss. Ordinary status remains a local
read. Full job IDs remain readable at 40/80/120 columns: narrow CLI output uses
stacked records, wider output a two-column table. An initial four-column table
clipped IDs and was replaced after the actual CLI regression exposed it.

### Actual CLI/TUI protocol evidence

Driver: `/tmp/klaude_s6_jobs_live.py`.
Final log: `/tmp/klaude-s6-jobs-live-complete.log`.
Receipt: `.klaude/data/s2-models-49i02n81/jobs-receipt.json`.

This uses the real CLI and bare TUI with a controlled native HTTP fixture;
it is **not additional diffusion-inference evidence**.

- One accepted generation produced one stored artifact. Listing exposed its
  complete job ID without prompt text or network activity.
- Declining CLI removal retained the receipt. Explicit server refresh retained
  the image and submitted no new generation.
- Session **TEST KLAUDE FEATURES IMAGE JOBS** opened the saved job after the
  original generation process exited. Removal reviews at 40/70/120 columns
  defaulted to Back. Enter on Back retained the receipt.
- Accepted removal deleted the receipt, showed the empty inventory, retained
  the artifact and exited cleanly. Exactly **one generation POST** occurred.
- A separate actual CLI submission lost its acknowledgement through a fixture
  HTTP500, exiting 1 and leaving `unknown` with no remote ID. Normal removal was
  rejected. TUI Back retained the receipt; enabling the separate abandonment
  confirmation then removed local tracking without cancellation or resubmission.
  Evidence: `.klaude/data/s2-models-549v35ar/jobs-unknown-receipt.json`,
  `/tmp/klaude_s6_jobs_unknown.py`, `/tmp/klaude-s6-jobs-unknown.log`.

Implementation: core `image_generation.history`, `refresh`, `forget`; CLI
`library_commands.generation_jobs`, `generation_status`; TUI `generation_panel`.

## Remaining certification and extension boundaries

- Anthropic credentials are absent in the current configuration. No paid
  Anthropic generation claim is made. The user has been asked to configure
  credentials through Klaude, without pasting keys into chat.
- OpenAI credentials are configured, but current actual CLI rechecks returned a
  preparation timeout and HTTP400; a subsequent bounded diagnostic had no usable
  error identifier. A separate minimal valid-image native request could not
  connect (`Network is unreachable`). These are not generation passes. The prior
  account-credit failure remains historical evidence, not a verified current
  diagnosis for HTTP400. Tests preserve native error/cancellation behavior.
- Legacy Gemini account access remains unverified as recorded in S6a3e; current
  Gemini chat evidence does not certify legacy Media models. No silent newer
  model, Thinking mode or provider substitution is introduced.
- Additional image-service APIs/authentication and unrelated managed image-engine
  installation are extensions requiring a concrete provider contract. The
  delivered native adapter retains its explicitly unauthenticated service scope.
- Native CUDA inference and the final regression gates passed as recorded below.
  Wider hardware/model/quality certification remains separate.

## S6b CUDA: actual native CLI and bare-TUI generation

The earlier bundled SageAttention failure was an upstream build-configuration
issue, rather than a Klaude request failure. The inspected engine's
`docs/sage_attention.md` requires SM80 for SageAttention and documents its optional
status. The engine supports `SD_USE_UPSTREAM_GGML=ON`; this uses upstream GGML
without the bundled SageAttention path. No engine source, driver, system package
or Klaude device defaults were modified.

- Engine source: `120e3e875c5501c1babb50c0966122cb569d12d4`.
- Upstream GGML: `3612c0af93f2cfc8f048295300a61187723b12ae`; downloaded archive
  SHA256 `e916a9f76772b89bcc566f5d76de875943c2f3abb73df97ff589ab787843ebfe`.
- Build: installed CUDA 12.0, GCC/G++12, Release, architecture 75, explicit
  `SD_GGML_SOURCE_DIR`, frontend/WebP/WebM disabled. The initial two-job build
  was deliberately interrupted and its remaining targets completed with four
  jobs. The original older local GGML checkout was API-incompatible; no source
  patch was used to force compatibility.
- Native device inspection identified GTX 1650, compute capability 7.5. The
  isolated loopback server explicitly used `diffusion=CUDA0`, `clip=cpu`,
  `vae=cpu` and CPU parameter storage, appropriate to this test's 4 GiB GPU.
- Weights: the same 1,566,768,416-byte SD1.5 Q4 GGUF used for CPU validation,
  SHA256 `b8944e9fe0b69b36ae1b5bb0185b3a7b8ef14347fe0fa9af6c64c4829022261f`.

Actual application results:

| Scenario | Result | Observed elapsed |
| --- | --- | --- |
| CLI, 512×512, 20 steps, seed 42, blue ceramic teapot | Saved to Media and checksum-identical export | 96.80 s end to end; native generation 94.47 s |
| Bare TUI, 512×384, 16 steps, seed 7, red apple | Saved to Media and exported | 62.79 s accepted request to result |
| TUI reviews, 40/70/120 columns | Back initially focused; declining retained the single prior image | Passed |
| Isolation/exit | Sentinel retained; no chat turns or automatic tags; exit 0 | Passed |

The session was **TEST KLAUDE FEATURES S6 GPU**. Both exported images were
visually inspected: the teapot/apple were recognizable, but the requested white
and green backgrounds became red and brown respectively. This is evidence of
working inference with imperfect prompt fidelity, not broad quality certification.
The tested GPU sample is not a controlled performance comparison with the earlier
CPU duck prompt, dimensions and step count.

Sampled peak server RSS was **3,675,422,720 bytes**, with **1,602 MiB** sampled
GPU memory in use. Native logs identify CUDA convolution/attention and actual
diffusion steps; GPU availability alone is not the inference evidence. The exact
test-server PID/start identity was rechecked and stopped after the walkthrough;
the final ownership receipt confirms it is no longer running. An earlier
automatic approval-review usage limit delayed this walkthrough; the later
authorized execution completed successfully.

Evidence: `/tmp/klaude-s6-cuda-{configure,build,devices}.log`,
`/tmp/klaude-s6-ggml-source.json`, `/tmp/klaude_s6_gpu_finish.py`,
`/tmp/klaude_s6_gpu_walkthrough.py`, `/tmp/klaude-s6-gpu-walkthrough.log`,
`/tmp/klaude-s6-gpu-live/gpu-finish-result.json`, and
`.klaude/data/s2-models-3n47jg1n/gpu-receipt.json` with the three review captures.
The temporary test binaries/weights are private validation assets, not bundled
application dependencies or a new managed image-engine installer.

## Final regression and phase audit

- Final unchanged-source `make check`: **3,496 passed, 19 skipped**, 705.84 s
  for pytest; Ruff passed; production mypy passed on **146 source files**.
  The wrapper completed in 707.09 s and its before/after hashes reported no
  changed Python files. Log: `/tmp/klaude-s6-final-check.log`; receipt:
  `/tmp/klaude-s6-final-check-receipt.json`.
- Final frozen/offline `make package-smoke`: all **five wheels** built, installed
  together in a fresh environment, imported and ran installed `klaude --help`.
  Log: `/tmp/klaude-s6-final-package.log`.
- The earlier 3,495-test gate predated the last unknown-job abandonment guard;
  it is superseded by the final 3,496-test gate. Focused image-generation tests
  passed **49/49** after that guard. No Python source changed for CUDA validation.
- These are local Python **3.12** results. A fresh Python 3.11–3.13 CI run has
  not been observed for this worktree; the earlier S0 matrix remains historical.

The audit cross-checked current entry points, implementation, tests and existing
phase evidence. Previous live walkthroughs are retained as dated evidence, not
described as newly rerun sessions in this final audit.

| Phase | Delivered scope checked | Status and evidence |
| --- | --- | --- |
| S0 | Shutdown acknowledgements and reliability regressions | Complete; [S0](s0-reliability-validation.md), current full suite |
| S1 | Endpoint identity, native/compatible discovery/runtime and persistence | Complete for delivered adapters; [S1](s1-model-connections-validation.md) |
| S2 | Add/Added Models, role defaults, Utility, DeepSeek/Anthropic adapters | Implemented; [S2](s2-model-settings-validation.md), [AI Defaults](s2b-ai-defaults-validation.md); paid live access remains a certification limit |
| S3 | Search/URL Fetch, execution budgets, built-in tools and settings navigation | Complete for delivered providers; [Search](s3a-web-search-validation.md), [Fetch](s3a-url-fetch-validation.md), [Agent Tools](s3b-agent-tools-validation.md) |
| S4 | Library lifecycle, explicit Knowledge actions and owned Research | Complete supported local scope; [Library](s4a-library-validation.md), [Research](s4b-deep-research-validation.md) |
| S5 | Ollama management, local/SSH serving, trusted setup/removal, CUDA/vLLM and adoption | Complete supported Linux scope; [Model Manager](s5a-model-manager-validation.md), [remote vLLM](s5c-remote-vllm-validation.md), [adoption](s5c-remote-adoption-validation.md) |
| S6 | Reviewed Vision/chat pixels, native CPU/CUDA image generation, jobs and selected AI tags | Implemented and locally validated as above; paid/legacy-provider generation access remains open |

S6 is **not fully certified across all planned provider accounts**. The remaining
unchecked mandatory gate is successful native OpenAI/Anthropic and legacy Gemini
generation with authorized account access. Optional search adapters, additional
image-service/auth profiles, other platforms and broader model-quality studies
remain explicit extensions, rather than silently claimed completed features.
The planned WebUI toggle/server, Gallery/canvas editing and AI Tidy are not
implemented by this checkpoint.
