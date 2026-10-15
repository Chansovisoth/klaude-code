# S6b1: reviewed local image generation

Date: 2026-10-15. Continues the
[Odysseus-inspired delivery plan](odysseus-settings-and-features-plan.md).

**Current status:** actual native CPU generation, reviewed CLI/TUI workflows,
queued/running cancellation outcomes and export passed in the S6b2 follow-up
below. CUDA inference and broad image-quality certification remain unverified.
The original S6b1 results are retained as historical protocol evidence.

## Delivered scope and evidence boundary

This first generation slice connects to an **existing stable-diffusion.cpp native
HTTP server**. Settings, CLI and real TUI paths are implemented and exercised
against a controlled HTTP fixture. The fixture returns canned PNG bytes: this is
protocol/lifecycle evidence, **not actual diffusion inference or image quality**.
At that checkpoint no suitable image server was running; no generator,
weights, service or dependency was installed. S6b was partial pending real
server generation. S6c AI tags remain unstarted. The prior paid
vision-certification gaps remain recorded separately.

The adapter follows upstream's
[native API contract](https://github.com/leejet/stable-diffusion.cpp/blob/master/examples/server/api.md),
reviewed this pass: mode-aware capabilities, asynchronous image jobs, job-scoped
poll/cancel, one PNG result. It does not reuse a chat-model name as evidence of
image generation or execute a caller-supplied workflow. Other image-service APIs,
authentication and managed image-engine installation are separate extensions.

## Product flow

- **Settings → AI Defaults → Image generation** exposes the service, an OFF-by-
  default draft switch, endpoint URL, Test connection, observed loaded model,
  Save, Reload and Back. Test inspects capabilities only. Save acknowledges its
  explicit model pin through the existing ordered settings writer, independent
  of session SQLite. Opening/cancelling a draft does not enable generation.
- This initial adapter accepts a server without authentication, including an
  explicitly configured LAN URL. It sends no ambient provider credentials,
  redirects, proxy requests, installers or model-loading commands. The pinned
  model is the server's reported loaded name; it is not weight attestation.
- **Library → Media → Generate image** exposes a private prompt, width/height,
  sampling steps, seed and Review. Model/endpoint stay explicit. Review starts
  focused on Back; paging/resizing cannot make Enter launch generation by default.
- One PNG, sizes **256–1024 in multiples of 64**, **1–50 steps**, seed -1 or a
  32-bit nonnegative integer. Random seeds are resolved before review. Native
  declared limits apply too. Default request: 512×512, 20 steps. The reviewed
  native sampler/scheduler are carried forward; other sampling defaults remain
  server-owned. There is no invented low/medium/high quality mapping.
- Acceptance rechecks settings and observed model/capabilities. Generation is
  submitted once, then polled under a five-minute deadline. Preview images,
  high-resolution second passes, batches, reference images and image metadata
  embedding are disabled. No automatic resubmission/fallback occurs on uncertainty.
- Results are bounded to 12 MB of JSON, **one PNG up to 8 MiB**, with dimensions
  matching the review. Metadata is bounded to 512 KB, connections to three seconds
  and individual reads to six seconds. The owned process supplies the outer bound.
  Header/dimension checks are not a full image decoder. Result URLs are never followed.
- Pixels and complete private provenance commit together in Library's existing
  SQLite artifact store. Provenance retains the prompt, reviewed endpoint/model,
  sampling parameters/seed, capability snapshot, local/remote job IDs and session
  association. It is available through explicit artifact detail/`library info`,
  outside ordinary list/search metadata and model context. Export retains exact
  bytes. Manual tags/archive preserve provenance; permanent artifact deletion
  removes its provenance row in the same transaction.
- Accepted work survives navigation. Chat/Knowledge/Research/Utility/Model Manager
  use the existing model-work gates. Late results cannot replace a different
  session/store's view. Accepted settings writes retain their captured destination.

## Cancellation, failure and recovery

Disposable generation workers are reaped before a separate bounded worker checks
cleanup using the captured original data/config root. Only the accepted native
job ID can be cancelled; no global interrupt is sent. Cleanup distinguishes
Confirmed, Unconfirmed and Not started. Unknown submission replies are retained
without a second generation POST. Ordinary graceful TUI exit reaps the local
worker and then performs the same scoped cleanup.

If output committed but the final job receipt write was lost, cleanup recovers
the existing artifact by its unique local job ID. It reports the already-saved
output rather than claiming rollback or cancelling a completed result.

Private owner-only job receipts allow later status inspection. Abrupt client
death or network loss can leave server work active: this API provides no client
lease, and Klaude cannot certify cancellation without a receipt. Status is local
receipt state, not proof of a live worker. Explicit `--cancel` can revisit a saved
job without resubmitting generation. Prompt-bearing receipts remain separate
from artifact deletion and have their own retention; this slice adds no automatic
history cleanup, queue scheduler or resume-and-regenerate behavior.

## CLI

Commands are registered in Klaude's canonical command reference:

```bash
klaude library image-service --endpoint http://localhost:8080 --enable
klaude library generate "A simple tool icon" --width 512 --height 512 --steps 20
klaude library generation-status JOB_ID
klaude library generation-status JOB_ID --cancel
```

Service saves, generation and explicit cancellation default to No. `--yes`
accepts the specific reviewed operation. Configuration/generation failures exit
1; declined review and completion exit 0; generation Ctrl+C exits 130 after local
worker cleanup and a scoped server-cleanup attempt. A stored image uses the
existing `library info/export/tags/archive/restore/delete` lifecycle.

## Real CLI/TUI protocol walkthrough

Final receipt:
`.klaude/data/s2-models-70eh6efh/generation-result.json`.
Driver: `/tmp/klaude_s6b_walkthrough.py`; final log:
`/tmp/klaude-s6b-walkthrough-complete.log`.

The named **TEST KLAUDE FEATURES IMAGE GENERATION** session used the actual
bare CLI, real owned subprocesses and real terminal input:

1. Disabled generation exited 1, without a generation POST.
2. Declining service save retained no definition. Declining generation sent no POST.
3. CLI acceptance submitted once, saved the private output/provenance, reported
   complete status and exported checksum-identical PNG bytes.
4. Actual SIGINT during a queued/running fixture job exited **130**, reaped the
   local worker and obtained confirmed cancellation of that exact remote ID.
5. Real Media form/review at **40/70/120 columns**: Enter on the initially selected
   Back returned to the form without submitting; subsequent explicit acceptance
   saved a second image. Narrow/wide review/settings captures were inspected.
   Values align at full width; long fields wrap and page on narrow terminals.
6. Real AI Defaults navigation tested the endpoint and acknowledged its ordered Save.
7. TUI exit **0**; two stored artifacts; exactly **three** submissions (two complete,
   one cancelled); no retries, public user/assistant turns or indexed knowledge.
   Existing workspace sentinel bytes were retained.

The first driver configured an unreachable chat endpoint and typed into Klaude's
intentional startup model picker. It was corrected to use the existing local
Ollama catalog for metadata only. The next driver completed all product steps
but incorrectly required the knowledge directory not to exist; startup creates
an empty directory. The final driver verifies no indexed files and retains a
complete receipt. Earlier raw outputs remain; neither harness issue justified
a production navigation/indexing change. An automatic permission review also
timed out on a combined setup/test command; separating file creation from the
short test command allowed normal validation to proceed.

## Automated validation and preservation

- Initial native HTTP/cancellation/storage cases: **22 passed in 10.29 seconds**.
- Image generation plus Library/artifacts/session actions/defaults/Vision:
  **122 passed in 48.14 seconds** before the final endpoint-suffix refinement.
- Regression cases include disabled/invalid inputs, metadata-only checks, stale
  model/settings, malformed output/IDs, one-submit uncertainty, owned cancellation,
  settings drain without session SQLite, post-commit receipt loss, old-root cleanup
  after a session/store change and graceful shutdown cleanup.
- Full frozen/offline `make check`: **3,456 passed, 19 skipped in 607.32 seconds**;
  Ruff passed; production mypy passed on **145 source files**. Log:
  `/tmp/klaude-s6b-make-check.log`. Local Python **3.12.3** only; no new CI claim
  for Python 3.11/3.13.
- A fresh native-only selection passed **29 tests in 13.02 seconds** after the
  endpoint-suffix refinement. A final generation/settings-writer selection then
  passed **37 tests in 16.87 seconds**, including all 30 native-generation cases
  and a storage-failure regression: an unsuccessful accepted settings write must
  make writer shutdown report failure. Log: `/tmp/klaude-s6b-final-request-state.log`.
  The full suite was already collected before these four final regression cases
  and small endpoint/status/writer refinements; this focused run validates their
  final source/test bodies rather than claiming another full-suite run.
- The actual CLI saved-job cancellation review showed its exact endpoint/model,
  declined with exit 0 and preserved all job receipts. Log:
  `.klaude/data/s2-models-70eh6efh/declined-saved-job-cancel.log`.
- Final frozen/offline `make package-smoke` passed for **all five wheels**,
  isolated installation/public imports and installed `klaude --help`. Log:
  `/tmp/klaude-s6b-package-smoke-final.log`. `git diff --check` passed.
- All 101 pre-existing changed/untracked files are retained: **86 keep their exact
  starting bytes** and the other 15 received scoped integration/documentation edits.
  Seven additional status paths are intentional new source/test/report files or
  the previously clean artifact-store/inventory integration. The final scoped
  hash review is `/tmp/klaude-s6b-worktree-receipt.json`; no reset, stash, discard,
  commit, push, dependency/version change or lock update was performed.

### Remaining S6b work at the original checkpoint

1. Actual native image generation, cancellation and export with a real installed
   model/server, including observed resource use on the available hardware.
2. Further services/authentication, if selected, with their own capability and
   protocol evidence; do not silently inherit this native contract.
3. A user-facing history inventory for interrupted image jobs, recovery of an
   already-completed remote result, and deliberate receipt cleanup if justified
   by usage. Existing receipts expose status/cancel only; they are not a scheduler.

No image editor, Gallery, image-edit/upload API, automatic tags or new agent tool
was added. S6b's real-generation gate is not complete merely because tests pass.

## S6b follow-up: cancellation race and explicit output recovery

Date: 2026-10-15. This follow-up preserves the original S6b1 protocol evidence
above and does not reinterpret fixture images as diffusion inference.

### Observed issue and implementation

Cancellation previously treated any terminal native status, including
`completed`, as `cancelled`. If a server finished just before Cancel, its image
could remain remotely available while Klaude claimed cancellation and provided
no retrieval action. Six new regression cases first failed against that code.

- Native cleanup now checks the exact ID **and** `kind=img_gen`, and retains
  `completed_remote`, `failed`, `cancelled` and unknown outcomes separately.
  A completed remote job is not silently imported by a Cancel action.
- `klaude library generation-status JOB_ID --recover` explicitly reviews the
  saved prompt, endpoint/model, dimensions, steps and seed, with No selected.
  `--cancel` and `--recover` are mutually exclusive. `--yes` accepts the exact
  recovery; it does not authorize generation resubmission.
- The current TUI result offers **Review output recovery**, followed by a
  Back-focused review and **Recover and save image**. It reuses the existing
  worker, model-work gates, scope checks and private artifact store.
- Recovery requires an acknowledged remote ID and unchanged original service
  settings/capabilities. Acceptance also rechecks the reviewed receipt. It makes
  only metadata/result GET requests, never a generation POST, global interrupt,
  model load or implicit retry. Missing/expired/incomplete/malformed results fail
  without creating an artifact.
- Ordinary generation and recovery now share the same pixel/dimension/checksum
  and atomic pixel/provenance publication boundary. An already committed result
  is returned idempotently; a receipt with a removed saved artifact cannot restore
  that deliberately deleted output. Receipt identity cannot redirect operations.
- Receipt status remains local metadata. This adds no general job history UI,
  durable scheduler, lease, unattended recovery or automatic receipt deletion.

### Real product flow with controlled native HTTP replies

Driver: `/tmp/klaude-s6b2-live/recovery_walkthrough.py`.
Final log: `/tmp/klaude-s6b2-live/recovery-walkthrough-final.log`.
Session: **TEST KLAUDE FEATURES S6B RECOVERY**.
Evidence: `.klaude/data/s2-models-rjsecsra/recovery-receipt.json`.

1. Real CLI generation accepted one fixture job; actual SIGINT exited **130**.
   The simulated completion race was recorded as `completed_remote`, not cancelled.
2. Declining recovery exited 0 without saving pixels. Explicit accepted recovery
   saved one image; repetition returned the same artifact. No generation retry.
3. Real bare-CLI TUI submitted its own second job, cancelled it and reviewed
   recovery at **40, 70 and 120 columns**. Enter on Back saved nothing; explicit
   recovery acceptance saved the second image. Exactly two generation submissions
   produced two artifacts; recovery added no generation submissions.
4. Clean TUI Ctrl+D exited **0**. The first driver had completed the same product
   checks but tried `/exit` inside an open picker; the corrected driver exits the
   client explicitly. This harness error did not justify a product change.
5. Exported screen text/SVGs were inspected. At 120 columns review labels/values
   align; at 40 columns values wrap and review scrolls with Back retaining focus.
   Local librsvg renders: `/tmp/klaude-s6b2-live/recovery-review-{40,120}.png`.

The first post-fix generation selection passed **36 tests in 17.45s**. Two
additional cases cover changed review/incomplete output and receipt identity;
the final full validation result is recorded below when complete.

### Real engine preparation and evidence boundary

An isolated test setup uses official stable-diffusion.cpp source revision
`120e3e875c5501c1babb50c0966122cb569d12d4` and its pinned ggml revision
`d25b121ce1d6ae0c7e62ad080460d9fc1e46dd93` under `/tmp/klaude-s6b2-live`.
CUDA compilation uses the installed toolkit/compiler, explicit architecture 75,
two jobs and disabled frontend/WebP/WebM; no system/app package installation,
service change or default-model change. The host GTX 1650 exposes 4096 MiB VRAM.
The native API was checked against the pinned upstream server contract.

SD1.5 Q4_0 test weights come from
[second-state/stable-diffusion-v1-5-GGUF](https://huggingface.co/second-state/stable-diffusion-v1-5-GGUF/tree/031b5f5df991f511b3f5fa8fed6d99048ababb69),
file `stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf`, published size
1,566,768,416 bytes and SHA256
`b8944e9fe0b69b36ae1b5bb0185b3a7b8ef14347fe0fa9af6c64c4829022261f`.
Downloads were isolated and range-bounded; final size and SHA256 were verified
before use. Interrupted downloads are not inference evidence. This preparation
section makes no inference claim; completed live CLI/TUI generation, cancellation,
export and resource observations are recorded in S6b2 below.

### Follow-up automated gates

- Full frozen/offline `make check`: **3,468 passed, 19 skipped in 695.31s**;
  Ruff passed; production mypy passed on **145 source files**. Log:
  `/tmp/klaude-s6b2-live/make-check.log`. Local Python 3.12 only; no new
  Python 3.11/3.13 CI claim.
- Frozen/offline `make package-smoke`: **five wheels**, isolated imports and
  installed CLI help passed. Log: `/tmp/klaude-s6b2-live/package-smoke.log`.
- The actual `library generation-status --help` exposes `--recover`, and the
  canonical CLI command reference includes the new mutually exclusive action.
  `git diff --check` passed.
- Upstream bundled CUDA compilation failed in SageAttention with installed
  CUDA 12.0 (`__float22bfloat162_rn` undefined). No engine source/driver/toolchain
  workaround was added. An explicit supported CPU build uses the same pinned
  source and default library; its inference results must be recorded separately.
  This test choice does not change Klaude/Ollama device settings or certify CUDA.

## S6b2: actual native CPU generation and protocol corrections

Date: 2026-10-15. Repository base:
`0234b116f4380cb87c1b1cf39959725493e227ee`; the extensive uncommitted S5/S6
worktree was inspected and preserved. No commit, push, application dependency
installation, default model change or global service registration was performed.

### Problems only the real server exposed

The unmodified native server rejected Klaude's assumptions before submission:

1. Its sampler and scheduler defaults were both the sentinel `default`, which
   is intentionally absent from the explicit sampler/scheduler catalogs. Klaude
   rejected this valid metadata as invalid sampler defaults.
2. Native capabilities declare queued cancellation, but **do not support
   interrupting an already-generating job**. Klaude required both capabilities,
   preventing any generation against this server. The earlier fixture advertised
   support for both and therefore did not expose this incompatibility.
3. A rejected cancellation POST prevented the subsequent status GET. A native
   HTTP 409 therefore concealed whether the exact job was still running or had
   completed during the request.
4. A TUI result offered recovery even when cancellation interrupted submission
   before its server ID was saved. No safe job-specific recovery is possible in
   that state. A walkthrough also initially cancelled at that ambiguous instant;
   the completion-race harness now waits for durable acknowledgement explicitly.

### Corrections

- Accept only the native `default` sentinel or an explicitly cataloged sampler/
  scheduler. Omit automatic fields in the request so the server resolves its
  own defaults; retain that reviewed choice in capability evidence/provenance.
  No model-name mapping or arbitrary sampler fallback was added.
- Require queued cancellation, and make running cancellation capability-aware.
  CLI and TUI generation reviews warn when only queued jobs can be cancelled:
  Cancel and the five-minute client deadline cannot stop native inference that
  has already started. The warning appears before confirmation, in the normal
  warning tone. Automatic sampling is labeled **Server defaults** in the TUI.
- After a failed scoped cancellation POST, still attempt the exact job's bounded
  GET. `running_remote`, `completed_remote`, `cancelled`, `failed` and unknown
  outcomes remain distinct. Running work retains **Unconfirmed** cleanup and an
  explicit recovery instruction; no global interrupt, server kill or retry occurs.
- Offer TUI recovery only for an acknowledged job, retaining safe retry after a
  reviewed recovery failure. An unacknowledged submission remains unknown.
- Use the explicit recovery flow described above for completed output. A local
  status read remains metadata only. Recovery requires the original binding and
  reviewed receipt, retrieves only the exact completed job and never resubmits.

Implementation: core `image_generation.inspect`, `prepare`, `cancellation_notice`,
`cancel`, `store_output`, `recovery_review`, `recover`; CLI
`library_commands.generate_image`, `generation_status`; TUI
`generation_panel.GenerationPanel.page`, `accept`.

The protocol was checked against the exact upstream source used for inference:
[capabilities and routes](https://github.com/leejet/stable-diffusion.cpp/blob/120e3e875c5501c1babb50c0966122cb569d12d4/examples/server/routes_sdcpp.cpp),
[request parsing](https://github.com/leejet/stable-diffusion.cpp/blob/120e3e875c5501c1babb50c0966122cb569d12d4/examples/common/common.cpp),
[native API](https://github.com/leejet/stable-diffusion.cpp/blob/120e3e875c5501c1babb50c0966122cb569d12d4/examples/server/api.md).

### Actual CLI/TUI evidence

The isolated server used loopback `127.0.0.1:18491`, four CPU threads and the
publisher-hash-verified SD1.5 Q4 weights recorded above. It generated real pixels;
no fixture answered its image requests. Ollama and global Klaude settings were
left intact. Test configuration, artifacts and sessions were isolated from normal
user data.

Evidence root: `.klaude/data/s2-models-9ll_4wde/`.
Drivers: `/tmp/klaude-s6b2-live/native_walkthrough.py` and
`native_tui_walkthrough.py`. The first driver completed CLI checks but failed
during TUI field navigation because it appended picker filters. The continuation
cleared filters between fields, reused those CLI artifacts and completed the
TUI run. `native-receipt.json` records the combined evidence and timing limitation.

| Scenario | Observed result |
| --- | --- |
| CLI configure/test/enable | Real capabilities and model pin accepted; no generation on Test |
| CLI generation | 256×256, 12 steps, seed 42; native inference 79.49 s; one private image/provenance record |
| CLI export | Output SHA256 exactly matched the stored artifact |
| Ctrl+C during running inference | Exit 130, local worker reaped, native 409 observed, `running_remote`, cleanup Unconfirmed |
| Ctrl+C on queued job | Exit 130, exact queued job cancelled, cleanup Confirmed; active job unaffected |
| Explicit recovery | Running job later completed; accepted `--recover` saved it without submitting generation again |
| Bare TUI generation | Session **TEST KLAUDE FEATURES S6B NATIVE**; 256×256, 12 steps, seed 77; 81.44 s from acceptance to result |
| Review and resize | 40/70/120 columns, Back initially selected; Enter on Back submitted nothing; explicit acceptance required |
| Session/workspace safety | Clean Ctrl+D exit 0; workspace sentinel unchanged; no user/assistant chat turns created by generation |

The three committed images had distinct job IDs and SHA256 values. A fourth
accepted job was cancelled while queued and produced no image. The recovered
job used native inference for 80.13 s. These are individual CPU observations
during other local checks, not a controlled performance benchmark.

A separate CLI run at **512×512, eight steps, seed 77** completed generation
and checksum-identical CLI export with exit 0. Native inference took **238.50 s**,
inside the unchanged five-minute bound. Visual inspection found a recognizable
yellow duck, but soft detail and an imperfect background. This supports a
resolution/budget limitation in the small test outputs rather than evidence that
Klaude's storage/export corrupts pixels; it is not a general quality certification.
The initial quality driver used the internal export method with an incorrect
signature after generation succeeded. A separate real CLI export completed
without regenerating. Evidence: `/tmp/klaude-s6b2-live/quality-receipt.json`,
`native-quality.png`, `finalize_quality.py`; workspace `quality-export.log`.
Four images were ultimately saved; five native jobs were acknowledged in total,
including the cancelled queued job.

The final compact review was exercised again after removing duplicate text:
`final-review-receipt.json`, driver
`/tmp/klaude-s6b2-live/final_review_walkthrough.py`. Endpoint/model are visible
together with Back at 120 columns; narrow review content is reachable by paging.
Reviewed screen exports were rendered with local librsvg and visually inspected:
`/tmp/klaude-s6b2-live/native-final-review-{40,120}.png`. The existing startup
banner clips at narrow widths; this pass assessed the generation page and did
not change the global banner. The walkthrough used monochrome output; warning
tone is additionally checked through the panel row model.

The server's sampled peak resident memory was **3,330,088,960 bytes (3.10 GiB)**
over 1,032 samples; GPU memory remained at the observed **1 MiB** idle level.
Model logs explicitly reported CPU allocation. This does not measure every
transient allocation. The verified test-owned process group was stopped and
reaped after the final export; no persistent image service was installed.
Evidence: `/tmp/klaude-s6b2-live/server-result.json`, `resources.json`,
`native-server.log`. Source/build/weights remain isolated temporary test inputs.

CLI/TUI completion-race regression also passed after the capability changes:
`.klaude/data/s2-models-kzcyst2p/recovery-receipt.json`, with exactly two fixture
generation submissions, two artifacts, declined recovery and idempotent accepted
recovery. Those pixels remain protocol fixtures, separate from native inference.

### Regression gates and preservation

- Initial full recovery gate: **3,468 passed, 19 skipped**, as recorded above.
- A subsequent frozen/offline `make check` passed **3,472 tests, 19 skipped in
  742.62 s**, Ruff and mypy on **145 production files**. Log:
  `/tmp/klaude-s6b2-live/make-check-final.log`. This run began before the final
  unacknowledged-job recovery-visibility test and compact review text changes;
  it is not presented as a complete run against those later edits.
- After those final scoped changes, **all 43 image-generation tests passed in
  35.15 s**. Log: `/tmp/klaude-s6b2-live/final-image-tests.log`. Coverage includes
  native automatic defaults, queued-only cancellation, HTTP409 observation,
  explicit recovery, failed/stale/bad-pixel recovery, idempotence, deleted output,
  private receipts, owned cleanup, changed sessions and safe review visibility.
  The full gate's Ruff/mypy stages ran after the final production edits.
- Final frozen/offline `make package-smoke` passed all **five wheels**, isolated
  imports and installed CLI help:
  `/tmp/klaude-s6b2-live/package-smoke-complete.log`. `git diff --check` passed.
- Validation was local **Python 3.12.3**; no new Python 3.11/3.13 CI claim.
- All **356** pre-existing file hashes were compared with the start snapshot.
  Only ten scoped implementation/test/documentation files changed; none were
  missing. The existing WebUI inventory, unrelated S5/S6 work, lock/dependency
  files and Git revision were preserved. Receipt:
  `/tmp/klaude-s6b2-live/worktree-receipt.json`. No reset, stash, commit or push.

### Remaining limits

- The tested native implementation cannot interrupt running inference. Closing
  the client or reaching its deadline can leave work consuming server resources.
  Remote queue ownership, leases and global process control were not invented.
- Recovery depends on server retention; the tested source retains completed and
  failed jobs for 600 seconds. A lost acknowledgement, expired job or restarted
  server cannot be reconstructed from a local receipt. No automatic resubmission
  occurs. Same-name model replacement remains outside server-name attestation.
- Visual inspection of the first two 256-pixel outputs found poor prompt fidelity
  and strong artifacts. Inference/storage success does not establish useful image
  quality for every model, resolution or step budget. No automatic quality rating,
  hidden parameter tuning or model substitution was introduced.
- CUDA compilation failed in upstream SageAttention with this machine's CUDA
  12.0 toolchain (`__float22bfloat162_rn` undefined). CPU was selected explicitly
  for this isolated test; Klaude performs no silent backend fallback. No driver,
  compiler or upstream source was modified. CUDA diffusion remains unverified.
- Additional services/authentication, a browsable job-receipt history/cleanup
  workflow and model-specific controls remain separate S6b extensions. S6c tags
  remain unstarted; paid vision-provider certification is unaffected.
