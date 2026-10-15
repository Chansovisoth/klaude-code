# Odysseus-inspired feature verification: S0–S6

**Date:** 2026-10-15 · **Base revision:** `4a64ce696ba0e0825fa5670609d2449955304648` · **Product:** klaude-code 0.2.0a4

Checklist: [delivery sequence and acceptance gates](odysseus-settings-and-features-plan.md#8-delivery-sequence-and-acceptance-gates). This audit inspected the live worktree, including three pre-existing documentation edits. Their original contents were saved before verification and retained. The initial verification changed no application source/tests. The later requested Settings → Library navigation change and its separate validation are recorded at the end; user configuration and dependencies remain unchanged.

## Result

- The roadmap contains **71 checkbox entries: 69 checked and two unchecked**. These are nested plan entries, not 71 independently certified products. The two open entries are the S6a3 parent and its remaining paid/legacy-provider generation gate.
- Every entry is mapped below to current implementation/test files and its prior runtime record. All mapped test modules were actually collected in the fresh full run. This is traceability, not a claim that tests cover every possible input or provider.
- Fresh frozen/offline `make check`: **3,505 passed, 19 skipped in 661.60 s**; Ruff passed; production mypy passed on **146 files**. Wrapper elapsed: **662.95 s**. The tracked-file snapshot was unchanged throughout the run.
- Actual Gemma E2B/E4B image CLI checks, interactive attachment/follow-up/model switch/process resume, AI-tag CLI/TUI, settings and controlled recovery/job walkthroughs passed.
- Actual native CUDA generation, checksum-identical export, archive/restore and completed-job inspection passed; the owned test server was stopped.
- **S6 is still not fully cross-account certified.** Existing OpenAI credit, missing native Anthropic access and legacy Gemini availability gates remain open. They were not reclassified as implementation success or retested with different models.

## Evidence levels

- **Automated now:** the current unit suite and source/static checks. Many provider, process, SSH and failure cases intentionally use controlled fixtures; a green result is not new upstream inference evidence.
- **Real model now:** actual installed native Ollama Gemma E2B/E4B and stable-diffusion.cpp CUDA requests through Klaude CLI/session flows.
- **Interactive now:** real bare-TUI keyboard flows. Some contact the actual local model; others contact a named protocol fixture to exercise deterministic failure/recovery safely.
- **Historical runtime:** linked phase reports describe earlier exact services/models/hardware. Those runs were reviewed but were not all repeated here.
- **Blocked:** successful native paid/legacy generation needs usable external account access. Protocol tests do not remove that requirement.

## Phase summary

| Phase | Checklist entries | Checked / open in plan | Fresh verification |
| --- | ---: | --- | --- |
| S0 — Reliability | 3 | 3 / 0 | Full reliability regressions and static checks; prior exact-source multi-version CI retained. |
| S1 — Model connection foundation | 5 | 5 / 0 | Identity/migration/compatible-runtime tests; actual native Ollama metadata and connection-settings walkthrough. |
| S2 — Models and AI Defaults | 11 | 11 / 0 | Settings/key masking/error/restart walkthrough plus defaults/provider/session tests. Paid provider generation remains separately scoped. |
| S3 — Search, Agent Tools and settings navigation | 8 | 8 / 0 | Current search/fetch/agent/subagent/tool/permission/MCP/Skills/navigation tests; all CLI help surfaces inspected. |
| S4 — Library and Deep Research | 13 | 13 / 0 | Actual document CLI lifecycle and image-session resume; Library/Knowledge/Research automated coverage. |
| S5 — Model Manager, dependencies and SSH | 14 | 14 / 0 | Actual native model list/status/hardware; build/install/serving/SSH/adoption regressions. Earlier upstream engine/SSH inference remains historical. |
| S6 — Vision, generation, image jobs and AI tags | 17 | 15 / 2 | Actual two-model image CLI, interactive pixels/resume, tagging, native CUDA generation; controlled recovery/job UI and all image-protocol regressions. |

## Fresh end-to-end scenarios

### 1. Native Gemma vision and session continuity

Installed Ollama 0.33.3 reported 22 model records. Exact selected models were `gemma4:e2b` and `gemma4:e4b`; native metadata declared vision support. No model was downloaded or silently substituted.

For **each model**, actual `klaude ask` correctly identified red/green/blue bands and read a synthetic build screenshot: **18 passed, 2 failed, Unit tests**. Actual reviewed `library analyze` also identified the RGB bands. All six processes exited 0.

One old harness expected literal digits and initially marked the correct E4B answer, “Eighteen checks passed and two failed,” as failed. The raw run/receipt was retained. A separate semantic review normalized number words and verified the unchanged answer; the application, image and expected counts were not changed, and no model rerun was needed.

The real bare TUI then passed four image-bearing turns: attach screenshot on E2B; delete the source and ask again; explicitly select E4B and retain approved pixels; exit, start a new process and resume with E4B/pixels intact. Each actual native request contained one image, zero tools, `think=false`, context 8192 and output limit 128. Existing model digests and the unrelated workspace sentinel were retained. Public history contained neither base64 pixels nor private image references.

Evidence: `.klaude/data/s6a-gemma-vq1libln/result.json`, the separate `gemma-cli-semantic-review.json` in this audit’s evidence directory, and `.klaude/data/s2-models-6nnmjmty/gemma-vision-result.json`. Session: **TEST KLAUDE FEATURES GEMMA VISION**.

### 2. Optional AI tags with actual local inference

Gemma E2B actual CLI proposal returned without saving. Explicit `--save --select 1` saved one suggestion, metadata search found it, declined clearing retained it, and confirmed clearing removed only AI tags. Manual `keep-manual` remained.

The actual TUI checked Back-focused reviews at 40/70/120 columns, declined a request without saving, generated initially unselected suggestions, explicitly selected/saved tags and exited cleanly. The image/sentinel and zero chat turns were retained. This verifies selection/lifecycle behavior, not universal tag quality.

Evidence: `.klaude/data/s2-models-tzdlkjib/s6c-receipt.json`. Session: **TEST KLAUDE FEATURES S6C TAGS**.

### 3. Models settings, safe failure/retry and image-job workflows

All four fresh actual CLI/TUI drivers exited 0:

| Walkthrough | Outcome | Elapsed |
| --- | --- | ---: |
| model-settings | Passed | 52.99 s |
| vision-recovery | Passed | 16.20 s |
| image-jobs | Passed | 23.21 s |
| unknown-jobs | Passed | 20.71 s |

- Models: unsaved test/cancel, actual local endpoint/catalog, acknowledged Add, masked API input, authentication versus network failures, no credential in registry/transcript, clean exit and restart persistence. The cloud-looking credential strings are synthetic canaries against a local catalog fixture, not real paid authentication.
- Vision recovery: declared compatible HTTP fixture returns 401 with a private body; CLI exits 1 with the safe reason, TUI wraps it at 40/70/120 columns and retains inputs, explicit retry succeeds. Exactly three POSTs cover CLI failure, TUI failure and accepted retry. No raw error/key leak or automatic retry.
- Completed image job: metadata listing omits the prompt; declined receipt removal retains it; accepted removal retains the image, makes no new generation request and returns to an empty list.
- Unknown job: an unacknowledged submission creates no artifact, ordinary forget is protected, explicit abandonment removes local tracking without cancellation or resubmission. This does not imply unknown remote work was stopped.

These image-job and error responses are **protocol fixtures, not diffusion/cloud inference**. The audit directory contains the four walkthrough logs and `ui-checks.json`; each log identifies its isolated root and detailed receipt.

### 4. Native CUDA image generation and Library lifecycle

Used the existing verified SD1.5 Q4 GGUF and existing stable-diffusion.cpp CUDA executable. No weights, engine, driver or package was installed. Weight SHA256: `b8944e9fe0b69b36ae1b5bb0185b3a7b8ef14347fe0fa9af6c64c4829022261f`; executable SHA256: `0e4e18bbaa1dcc42b7e39cbebcbda359c42b310a3f25804cb16f6f07249c811e`.

The worker waited **140.38 s** for test-loaded models to expire naturally; no shared model was forcibly unloaded. The owned loopback server used explicit `diffusion=CUDA0`, CPU text/VAE and CPU parameter storage on GTX 1650. Actual CLI generation used **512×512, 20 steps, seed 42**, then exported exact bytes, archived/restored the stored image, listed its job and inspected its completed status.

Generation CLI elapsed: **100.58 s**. Output: **249,283 bytes**, SHA256 `f5ccaae2962c91a6b5f81aba8080b544fde07c3442f8a29a5d593ba2c3491f18`. Manual/AI tags stayed empty, and the unrelated sentinel was retained. The owned server exited after SIGTERM; cleanup receipt confirms it stopped.

Visual inspection found a recognizable pale blue/gray teapot, but the requested white background was red. Transport, storage and generation execution passed; background-color fidelity remains a model-quality limitation. No prompt-specific compensation was added. This is not a controlled performance comparison with earlier runs, since the full suite ran concurrently.

Fresh evidence: `native-generation-result.json` and its private root under the audit evidence directory; native log identifies actual CUDA diffusion steps. Earlier real CPU and CUDA TUI/cancellation runs remain linked from [S6 completion](s6-completion-validation.md), rather than being relabeled as new runs.

### 5. Real model metadata and document-only CLI lifecycle

Actual native `model-manager list`, `status` and `hardware` succeeded. In another isolated workspace, actual document CLI commands passed import/list/info/manual tags/search/export, rejection of overwrite, rejection of unarchived deletion, archive/restore, declined deletion and accepted permanent deletion. The original and exported bytes remained intact.

All 16 command outcomes matched expectations, including the two intentional exit-1 rejections. The resulting data root contained only Library storage and runtime metadata: **no chat session database or knowledge index**. This directly checks Stored ≠ indexed, Imported ≠ learned and Archived ≠ deleted for documents. Evidence: `storage-cli-result.json`.

### 6. CLI/slash registry coverage

All **109 command-tree nodes**, including **97 leaf commands**, returned exit 0 for help under isolated settings. The canonical registry contains **44 slash-command entries**, matching the feature inventory. Help execution does not test each command’s operational behavior; real operational cases are listed above and automated cases are mapped below.

The initial audit helper incorrectly assumed a `CommandSpec.syntax` attribute. Inspection showed the real field is `usage`; the helper was corrected and the full traversal passed. This was a QA helper error, not an application failure. Evidence: `commands.json`.

## Every roadmap checkbox mapped

IDs below are audit-local references to the existing checkbox order; they do not create new product phases. **Mapped** means current source/test traceability with the fresh full suite, plus only the runtime evidence explicitly described above or in the linked historical report. **Blocked** means its mandatory live gate is still open. A checked implementation item does not certify every provider/account/hardware combination.

### S0 — Reliability

| Entry | Existing requirement | Evidence group | Audit outcome |
| --- | --- | --- | --- |
| S0-01 | Verify the current TUI shutdown fix locally: a late redraw must not change the reported outcome of an already committed memory/session write. | [R0](#r0) | Mapped; scopes below apply |
| S0-02 | Require successful Python 3.11–3.13 CI for the checkpoint containing the fix, including lint, production types and the existing packaging gate. | [CI](#ci) | Mapped; scopes below apply |
| S0-03 | Verify existing plan approval, cancellation, malformed-call/path recovery, shell failure tracking, workspace-cache invalidation, dirty-worktree safety, validation reruns and exit-code behavior in the local suite; retain these gates throughout this roadmap. | [R0](#r0) | Mapped; scopes below apply |

### S1 — Model connection foundation

| Entry | Existing requirement | Evidence group | Audit outcome |
| --- | --- | --- | --- |
| S1-01 | Store multiple connections with stable endpoint IDs, adapter type, normalized URL, enabled state and private credential references. | [M1](#m1) | Mapped; scopes below apply |
| S1-02 | Migrate the current Ollama URL, startup model and native-provider choices; retain session resume and field-scoped preferences. | [M1](#m1) | Mapped; scopes below apply |
| S1-03 | Identify/cache a model by endpoint plus model ID; keep same-named models on different servers distinct. | [M1](#m1) | Mapped; scopes below apply |
| S1-04 | Add owned, cancellable discovery/health checks with precise authentication, network, missing-catalog and malformed-response feedback. | [M1](#m1) | Mapped; scopes below apply |
| S1-05 | Add the compatible runtime needed for explicitly configured llama.cpp, vLLM or other compatible servers; retain native provider continuation/tools. | [M1](#m1) | Mapped; scopes below apply |

### S2 — Models and AI Defaults

| Entry | Existing requirement | Evidence group | Audit outcome |
| --- | --- | --- | --- |
| S2-01 | Models landing page with Added Models, Add Models and session selection. | [M1](#m1) | Mapped; scopes below apply |
| S2-02 | Add Local Models and Add API Models forms: name, adapter/provider, endpoint, masked authentication, Test, Add and Cancel. | [M1](#m1) | Mapped; scopes below apply |
| S2-03 | Added Models: probe, endpoint detail, enable/disable, reviewed removal and acknowledged outcomes; authentication errors stay distinct from offline state. | [M1](#m1) | Mapped; scopes below apply |
| S2-04 | Per-endpoint model inventory: Filter, Reload, enabled/total count, per-model visibility/pinning and observed/unknown capability metadata. | [M1](#m1) | Mapped; scopes below apply |
| S2-05 | Default Chat endpoint/model for new sessions; preserve the current session's independent model choice and pending changes during a running turn. | [D2](#d2) | Mapped; scopes below apply |
| S2-06 | Utility endpoint/model, Same as chat inheritance and ordered explicit fallbacks, paired with bounded optional naming/summary consumers. | [D2](#d2) | Mapped; scopes below apply |
| S2-07 | Display effective selections and fallback use. Keep deterministic compaction and avoid extra model calls for simple requests. | [D2](#d2) | Mapped; scopes below apply |
| S2-08 | Add Research endpoint/model controls with its functioning S4b consumer. | [Q4](#q4) | Mapped; scopes below apply |
| S2-09 | Add Vision and Image generation controls with their S6 consumers; S6a supplies analysis and S6b1 supplies the first local generation workflow. Actual native CPU/CUDA diffusion inference is validated under S6b. Preserve the existing embedding role and migration boundary. | [V6](#v6) | Mapped; scopes below apply |
| S2-10 | Add DeepSeek as an explicit connection preset, with a dedicated reasoning continuation adapter, session/default/Utility consumers and local protocol validation. [Evidence and cloud limits](s2c-deepseek-validation.md). | [P2](#p2) | Mapped; scopes below apply |
| S2-11 | Add native Anthropic with explicit endpoint settings, paginated catalogs, Messages/tool continuation, declared mode/effort controls and Utility consumers. [Local evidence and cloud limits](s2c-anthropic-validation.md). Existing OpenAI API, Gemini API, OpenRouter and Codex account paths remain available. Additional providers require their own implemented and validated adapters. | [P2](#p2) | Mapped; scopes below apply |

### S3 — Search, Agent Tools and settings navigation

| Entry | Existing requirement | Evidence group | Audit outcome |
| --- | --- | --- | --- |
| S3-01 | Web Search: Auto/pinned provider, relevant provider fields and masked credentials, results per query, Test, enabled state and fallback ordering. | [W3](#w3) | Mapped; scopes below apply |
| S3-02 | URL Fetch: its own provider configuration, credentials and availability. | [W3](#w3) | Mapped; scopes below apply |
| S3-03 | Move existing web-provider controls to their single owning page; retain current routing/validation semantics and compatibility links. | [W3](#w3) | Mapped; scopes below apply |
| S3-04 | Execution: maximum steps, Auto/Custom tool-call limits, advanced token budget and provider-aware subagent worker limits. Migrate current zero to Auto; an Unlimited option requires separately implemented and verified semantics. | [A3](#a3) | Mapped; scopes below apply |
| S3-05 | Registry-derived groups, enabled/total counts, individual/group toggles with mixed state, permission links and Activity Updates. | [A3](#a3) | Mapped; scopes below apply |
| S3-06 | Link MCPs and Skills to their existing managed-capability pages; retain their search/manage navigation and the existing Memory/Permissions ownership. | [A3](#a3) | Mapped; scopes below apply |
| S3-07 | Move only the relevant controls from Tools, Providers and Runtime; keep device/context/calibration in Runtime and update canonical help/aliases. | [A3](#a3) | Mapped; scopes below apply |
| S3-08 | Apply the proposed Settings grouping and shared width, filtering, focus/Back, table-header and footer conventions across migrated pages. | [A3](#a3) | Mapped; scopes below apply |

### S4 — Library and Deep Research

| Entry | Existing requirement | Evidence group | Audit outcome |
| --- | --- | --- | --- |
| S4-01 | Build Library navigation in this order: **Sessions, Knowledge, Documents, Research, Media, Archive**. Sessions/Knowledge/Documents/Media/Archive work; the subsequent S4b slice supplies Research jobs/reports. | [L4](#l4) | Mapped; scopes below apply |
| S4-02 | Sessions: browse, full-store search, bounded pages/public previews and resume. | [L4](#l4) | Mapped; scopes below apply |
| S4-03 | Knowledge: browse existing named libraries and search active/enabled indexed text without model calls, preserving existing IDs and compatibility commands. | [K4](#k4) | Mapped; scopes below apply |
| S4-04 | Add TUI consumers for explicit learning, hybrid query and managed-source refresh, reusing existing service owners and CLI compatibility. | [K4](#k4) | Mapped; scopes below apply |
| S4-05 | Prepare durable report/artifact storage for S4b. | [L4](#l4) | Mapped; scopes below apply |
| S4-06 | Documents: import/store, metadata, filters, open and export; learning into a named knowledge library remains explicit. | [L4](#l4) | Mapped; scopes below apply |
| S4-07 | Media: screenshots and uploaded/imported images, previews with terminal fallbacks, metadata, manual tags, open externally and export. | [L4](#l4) | Mapped; scopes below apply |
| S4-08 | Archive: start with sessions, search/restore retained content, separate confirmed permanent deletion; extend to artifact types with supported lifecycle. | [L4](#l4) | Mapped; scopes below apply |
| S4-09 | Maintain **Stored ≠ indexed; Imported ≠ learned; Archived ≠ deleted** for the implemented session/document/media stores. | [L4](#l4) | Mapped; scopes below apply |
| S4-10 | Job form: question, format, bounded rounds, search provider, endpoint/model overrides, Queue and Start. | [Q4](#q4) | Mapped; scopes below apply |
| S4-11 | AI Defaults research role plus Search research defaults: max report tokens, extraction timeout/parallelism, run deadline and advanced budgets. | [Q4](#q4) | Mapped; scopes below apply |
| S4-12 | Owned jobs with public progress, sources, cancel, partial/error outcomes and bounded recovery/checkpoints using the canonical runtime. | [Q4](#q4) | Mapped; scopes below apply |
| S4-13 | Sourced reports saved into Library → Research, with view/discuss/export and explicit learning; re-fetch required evidence on recovery. | [Q4](#q4) | Mapped; scopes below apply |

### S5 — Model Manager, dependencies and SSH

| Entry | Existing requirement | Evidence group | Audit outcome |
| --- | --- | --- | --- |
| S5-01 | Installed-model inventory, discovery/download, progress/cancel, hardware information and Hugging Face credential/settings ownership where relevant. | [O5](#o5) | Mapped; scopes below apply |
| S5-02 | Native Ollama pull/remove and service health/status; distinguish removing a connection from explicitly deleting a downloaded model. | [O5](#o5) | Mapped; scopes below apply |
| S5-03 | Integrate already-installed llama.cpp/vLLM, then owned launch/stop/logs, validated model/port/device/context fields and supported engine options. | [S5](#s5) | Mapped; scopes below apply |
| S5-04 | Register served endpoints after a successful health check; explicitly adopt existing processes and stop only owned processes. | [S5](#s5) | Mapped; scopes below apply |
| S5-05 | Local dependency inspection and reviewed llama.cpp CPU build from a committed local snapshot, with owned compilation, logs, cancellation and verified handoff to Serve models. | [B5](#b5) | Mapped; scopes below apply |
| S5-06 | Explicit local NVIDIA CUDA build and isolated vLLM wheel-install recipes, with compiler/target/platform/dependency/hash checks and owned cancellation. | [B5](#b5) | Mapped; scopes below apply |
| S5-07 | Reviewed retained build/install removal and storage reclamation. | [B5](#b5) | Mapped; scopes below apply |
| S5-08 | SSH definitions, strict connection testing, bounded resource/model-directory/ process snapshots and a diagnostics default with an explicit consumer. | [H5](#h5) | Mapped; scopes below apply |
| S5-09 | Owned SSH CPU llama.cpp serving, renewable remote lease, verified loopback endpoint/tunnel, confirmed/unconfirmed cleanup and reviewed stop/cancel. | [H5](#h5) | Mapped; scopes below apply |
| S5-10 | Reviewed enrollment of existing Ed25519 public keys and independently verified host pinning, preserving existing trust files/key policies. | [H5](#h5) | Mapped; scopes below apply |
| S5-11 | Owned remote llama.cpp GPU profiles with observed engine device mapping, stale-device rejection, explicit layer/device reviews and native CUDA inference. | [H5](#h5) | Mapped; scopes below apply |
| S5-12 | Reviewed remote NVIDIA vLLM serving with environment-specific CUDA checks, stable GPU UUIDs, local safetensors bundle revisions and explicit resources. | [H5](#h5) | Mapped; scopes below apply |
| S5-13 | Upstream remote vLLM GPU inference validated through actual CLI/TUI over loopback SSH on GTX 1650, with pinned SmolLM2-135M-Instruct and confirmed cleanup. | [H5](#h5) | Mapped; scopes below apply |
| S5-14 | Reviewed remote adoption with exact process/model/listener identity, exclusive acknowledged takeover and witnessed-group cleanup. Observed PIDs alone do not authorize mutation. | [H5](#h5) | Mapped; scopes below apply |

### S6 — Vision, generation, image jobs and AI tags

| Entry | Existing requirement | Evidence group | Audit outcome |
| --- | --- | --- | --- |
| S6-01 | S6a1: explicit native Ollama image/screenshot analysis through Library → Media and CLI, off-by-default switch, declared capability checks, explicit qualified model/fallbacks, reviewed budgets and owned cancellation. | [V6](#v6) | Mapped; scopes below apply |
| S6-02 | S6a2: provider-neutral image messages and image attachments in ordinary coding chat, with private persistence/restore/compaction, provider switches and truthful per-turn pixel capabilities. | [I6](#i6) | Mapped; scopes below apply |
| S6-03 | S6a3: additional image-capable provider adapters with explicit capability evidence, endpoint/credential reviews and actual protocol/generation validation. | [C6](#c6) | **Blocked: live provider access** |
| S6-04 | S6a3a: native Anthropic and declared compatible HTTP **chat** image paths; actual compatible Ollama generation, native Anthropic TLS/TUI fixtures, independent session model restoration and bounded follow-up routing. | [I6](#i6) | Mapped; scopes below apply |
| S6-05 | S6a3b: extend reviewed Media analysis to the supported HTTP adapters, preserving explicit budgets/fallbacks, owned jobs and endpoint reviews. | [V6](#v6) | Mapped; scopes below apply |
| S6-06 | S6a3c: OpenRouter chat and reviewed Media through verified image/text declarations, bounded transport, private protocol state and actual free-model CLI/TUI generation, follow-ups and process resume. | [C6](#c6) | Mapped; scopes below apply |
| S6-07 | S6a3d: reviewed exact-ID OpenAI Responses chat/Media profiles and bounded native delivery; real TLS CLI/TUI/settings/cancel/resume fixtures. Live generation remains unverified due to exhausted account credits. | [C6](#c6) | Mapped; live account gate open |
| S6-08 | S6a3e: exact reviewed Gemini 2.5 Flash/Flash-Lite profiles and bounded native images/signed continuation; real CLI/TUI TLS fixtures. Live generation remains unverified: both legacy IDs returned HTTP 404 for this account. | [C6](#c6) | Mapped; live account gate open |
| S6-09 | S6a3f: exact reviewed current Gemini Thinking chat profiles, native signed text/tool/image continuity and actual Google one-shot/TUI/resume generation. Standard-only consumers remain unavailable to these models. | [C6](#c6) | Mapped; scopes below apply |
| S6-10 | Remaining OpenAI/native Anthropic paid-provider generation certification and legacy Gemini access require actual successful generation evidence. | [C6](#c6) | **Blocked: live provider access** |
| S6-11 | S6b1: existing native stable-diffusion.cpp endpoint, OFF-by-default settings, tested loaded-model pin, reviewed size/steps/seed, one owned asynchronous job and scoped cancellation. Separate generation settings do not alter chat roles. | [G6](#g6) | Mapped; scopes below apply |
| S6-12 | Atomic private PNG/provenance/session/job storage in Media; existing detail/export/tags/archive/delete lifecycle. Actual CLI/TUI fixture walkthrough covers declines, acceptance, Ctrl+C 130, settings saves and three widths. | [G6](#g6) | Mapped; scopes below apply |
| S6-13 | Actual native CPU image-server inference, queued/running cancellation outcomes and exact export through CLI/TUI. Protocol fixtures are recorded separately. | [G6](#g6) | Mapped; scopes below apply |
| S6-14 | Actual native CUDA CLI/TUI inference, explicit device allocation and exact export on GTX 1650 through the supported upstream-GGML build configuration. | [G6](#g6) | Mapped; scopes below apply |
| S6-15 | Explicit image-tagging action after vision works; distinguish generated tags from manual tags and preserve manual choices. | [T6](#t6) | Mapped; scopes below apply |
| S6-16 | Back-focused Vision request, initially unselected suggestions, selected save and separate AI-tag clearing, search and provenance/lifecycle support. | [T6](#t6) | Mapped; scopes below apply |
| S6-17 | Actual Gemma E2B CLI/TUI pixel-to-tag generation and selected persistence; manual-tag retention, declined clear, three widths and clean exit. | [T6](#t6) | Mapped; scopes below apply |

## Implementation and test evidence index

Every listed source/test path exists. Every listed test module was collected in the current full run; that does not turn controlled responses into real upstream evidence. Suites overlap between groups and their counts must not be added as distinct features.

### R0

Shutdown acknowledgement, approval/cancellation/recovery, write safety and validation reruns.

- Implementation: [main.py](../apps/cli/src/klaude_cli/main.py), [session_actions.py](../apps/cli/src/klaude_cli/session_actions.py).
- Current tests: [test_session_actions.py](../tests/unit/test_session_actions.py), [test_cli_commands.py](../tests/unit/test_cli_commands.py), [test_reliability_evidence.py](../tests/unit/test_reliability_evidence.py), [test_reliability_repair.py](../tests/unit/test_reliability_repair.py), [test_tools.py](../tests/unit/test_tools.py), [test_process_recovery.py](../tests/unit/test_process_recovery.py), [test_execution.py](../tests/unit/test_execution.py), [test_workspace_execution.py](../tests/unit/test_workspace_execution.py).
- Earlier runtime/scope: [s0-reliability-validation.md](s0-reliability-validation.md).

### CI

Historical exact-source Python 3.11–3.13 CI; current local full suite/static checks. No fresh multi-version matrix dispatched.

- Implementation: [ci.yml](../.github/workflows/ci.yml), [package_smoke.py](../scripts/package_smoke.py).
- Current tests: [test_release_artifacts.py](../tests/unit/test_release_artifacts.py).
- Earlier runtime/scope: [s0-reliability-validation.md](s0-reliability-validation.md).

### M1

Connection identity/migration/discovery, scoped errors and compatible tools/continuation. Current protocol tests; fresh native metadata/settings TUI.

- Implementation: [model_connections.py](../packages/core/src/klaude_core/model_connections.py), [session_runtime.py](../packages/core/src/klaude_core/session_runtime.py), [model_runtime.py](../packages/core/src/klaude_core/model_runtime.py), [model_connections.py](../apps/cli/src/klaude_cli/model_connections.py), [model_settings.py](../apps/cli/src/klaude_cli/model_settings.py).
- Current tests: [test_model_connections.py](../tests/unit/test_model_connections.py), [test_session_runtime.py](../tests/unit/test_session_runtime.py), [test_model_settings.py](../tests/unit/test_model_settings.py).
- Earlier runtime/scope: [s1-model-connections-validation.md](s1-model-connections-validation.md).

### D2

Independent defaults/session choice, bounded Utility/fallback behavior and deterministic compaction; runtime resume exercised separately.

- Implementation: [ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py), [session_runtime.py](../packages/core/src/klaude_core/session_runtime.py), [context_compaction.py](../packages/core/src/klaude_core/context_compaction.py), [ai_default_settings.py](../apps/cli/src/klaude_cli/ai_default_settings.py).
- Current tests: [test_ai_defaults.py](../tests/unit/test_ai_defaults.py), [test_session_runtime.py](../tests/unit/test_session_runtime.py), [test_context_compaction.py](../tests/unit/test_context_compaction.py).
- Earlier runtime/scope: [s2b-ai-defaults-validation.md](s2b-ai-defaults-validation.md).

### Q4

Research role, queue, budgets, source validation, cancellation/recovery, report storage. Current controlled-service tests; prior research runtime evidence remains scoped.

- Implementation: [research.py](../packages/core/src/klaude_core/research.py), [research_receipts.py](../packages/core/src/klaude_core/research_receipts.py), [research_panel.py](../apps/cli/src/klaude_cli/research_panel.py), [research_commands.py](../apps/cli/src/klaude_cli/research_commands.py).
- Current tests: [test_research.py](../tests/unit/test_research.py).
- Earlier runtime/scope: [s4b-deep-research-validation.md](s4b-deep-research-validation.md).

### V6

Reviewed roles/consumers, budgets, errors, explicit fallbacks and owned cancellation. Fresh Gemma and native generation evidence; cloud certification stays separate.

- Implementation: [vision.py](../packages/core/src/klaude_core/vision.py), [ai_defaults.py](../packages/core/src/klaude_core/ai_defaults.py), [image_generation.py](../packages/core/src/klaude_core/image_generation.py), [vision_panel.py](../apps/cli/src/klaude_cli/vision_panel.py), [generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py).
- Current tests: [test_vision.py](../tests/unit/test_vision.py), [test_vision_http.py](../tests/unit/test_vision_http.py), [test_ai_defaults.py](../tests/unit/test_ai_defaults.py), [test_image_generation.py](../tests/unit/test_image_generation.py).
- Earlier runtime/scope: [s6-completion-validation.md](s6-completion-validation.md).

### P2

Implemented native provider contracts and fixture coverage; no new paid DeepSeek/Anthropic generation.

- Implementation: [deepseek_runtime.py](../packages/core/src/klaude_core/deepseek_runtime.py), [anthropic_runtime.py](../packages/core/src/klaude_core/anthropic_runtime.py), [model_settings.py](../apps/cli/src/klaude_cli/model_settings.py).
- Current tests: [test_deepseek.py](../tests/unit/test_deepseek.py), [test_anthropic.py](../tests/unit/test_anthropic.py).
- Earlier runtime/scope: [s2c-anthropic-validation.md](s2c-anthropic-validation.md).

### W3

Search/fetch ownership, routing, masked settings, fallbacks, stale results and compatibility links. Fresh automated coverage, not new upstream search-provider certification.

- Implementation: [search_settings.py](../packages/core/src/klaude_core/search_settings.py), [fetch_settings.py](../packages/core/src/klaude_core/fetch_settings.py), [search_settings.py](../apps/cli/src/klaude_cli/search_settings.py), [fetch_settings.py](../apps/cli/src/klaude_cli/fetch_settings.py).
- Current tests: [test_search_settings.py](../tests/unit/test_search_settings.py), [test_fetch_settings.py](../tests/unit/test_fetch_settings.py), [test_search.py](../tests/unit/test_search.py), [test_web_fetch.py](../tests/unit/test_web_fetch.py).
- Earlier runtime/scope: [s3a-web-search-validation.md](s3a-web-search-validation.md).

### A3

Execution/tool groups, permissions, MCP/Skills links and common settings width/navigation. Fresh automated coverage; current Models/S6 TUI walks cover shared presentation, not every page visually.

- Implementation: [agent_settings.py](../packages/core/src/klaude_core/agent_settings.py), [subagents.py](../packages/core/src/klaude_core/subagents.py), [agent_settings.py](../apps/cli/src/klaude_cli/agent_settings.py), [main.py](../apps/cli/src/klaude_cli/main.py), [settings_panel.py](../apps/cli/src/klaude_cli/settings_panel.py).
- Current tests: [test_agent_settings.py](../tests/unit/test_agent_settings.py), [test_agent_tool_settings.py](../tests/unit/test_agent_tool_settings.py), [test_subagents.py](../tests/unit/test_subagents.py), [test_settings_panel.py](../tests/unit/test_settings_panel.py), [test_cli_commands.py](../tests/unit/test_cli_commands.py), [test_skill_management.py](../tests/unit/test_skill_management.py), [test_mcp_search_panel.py](../tests/unit/test_mcp_search_panel.py).
- Earlier runtime/scope: [s3b-agent-tools-validation.md](s3b-agent-tools-validation.md).

### L4

Library navigation, sessions, private documents/media, lifecycle and durable-information boundaries. Fresh actual document CLI lifecycle and image-session resume.

- Implementation: [memory.py](../packages/core/src/klaude_core/memory.py), [library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py), [library_workspace.py](../apps/cli/src/klaude_cli/library_workspace.py), [library_inventory.py](../apps/cli/src/klaude_cli/library_inventory.py), [library_artifact_panel.py](../apps/cli/src/klaude_cli/library_artifact_panel.py).
- Current tests: [test_library_workspace.py](../tests/unit/test_library_workspace.py), [test_library_artifacts.py](../tests/unit/test_library_artifacts.py), [test_session_actions.py](../tests/unit/test_session_actions.py).
- Earlier runtime/scope: [s4a-library-validation.md](s4a-library-validation.md).

### K4

Explicit Knowledge ingestion/query/refresh and compatibility. Current automated real-store/controlled-service coverage; no new large ingestion or upstream crawl benchmark.

- Implementation: [indexing.py](../packages/knowledge/src/klaude_knowledge/indexing.py), [library_knowledge.py](../apps/cli/src/klaude_cli/library_knowledge.py), [library_knowledge_panel.py](../apps/cli/src/klaude_cli/library_knowledge_panel.py).
- Current tests: [test_library_knowledge.py](../tests/unit/test_library_knowledge.py), [test_knowledge.py](../tests/unit/test_knowledge.py), [test_docs.py](../tests/unit/test_docs.py).
- Earlier runtime/scope: [s4a-library-validation.md](s4a-library-validation.md).

### O5

Native model inventory/pull/remove, protected roles and cancellable work. Fresh real list/status/hardware only; destructive/download paths use controlled fixtures.

- Implementation: [ollama_manager.py](../packages/core/src/klaude_core/ollama_manager.py), [model_manager.py](../apps/cli/src/klaude_cli/model_manager.py), [model_manager_commands.py](../apps/cli/src/klaude_cli/model_manager_commands.py).
- Current tests: [test_ollama_manager.py](../tests/unit/test_ollama_manager.py), [test_model_management.py](../tests/unit/test_model_management.py), [test_huggingface.py](../tests/unit/test_huggingface.py).
- Earlier runtime/scope: [s5a-model-manager-validation.md](s5a-model-manager-validation.md).

### S5

Owned launch/readiness/registration, adoption and cleanup against process fixtures. Earlier installed-engine inference is historical; no new upstream llama.cpp/vLLM generation.

- Implementation: [managed_serving.py](../packages/core/src/klaude_core/managed_serving.py), [model_manager.py](../apps/cli/src/klaude_cli/model_manager.py), [serving_jobs.py](../apps/cli/src/klaude_cli/serving_jobs.py).
- Current tests: [test_managed_serving.py](../tests/unit/test_managed_serving.py).
- Earlier runtime/scope: [s5b-managed-serving-validation.md](s5b-managed-serving-validation.md).

### B5

Trusted setup, offline wheels, CPU/CUDA checks and safe retained setup removal. Current synthetic build/install/process tests; earlier upstream engine validation remains historical.

- Implementation: [model_dependencies.py](../packages/core/src/klaude_core/model_dependencies.py), [model_recipes.py](../packages/core/src/klaude_core/model_recipes.py), [dependency_panel.py](../apps/cli/src/klaude_cli/dependency_panel.py).
- Current tests: [test_model_dependencies.py](../tests/unit/test_model_dependencies.py), [test_model_recipes.py](../tests/unit/test_model_recipes.py), [test_model_setup_removal.py](../tests/unit/test_model_setup_removal.py).
- Earlier runtime/scope: [s5c-dependencies-validation.md](s5c-dependencies-validation.md).

### H5

Strict SSH definitions/trust, lease/tunnel/device/adoption policies via current fixtures. Earlier actual loopback SSH/engine CUDA inference is historical, not a new remote-host test.

- Implementation: [ssh_servers.py](../packages/core/src/klaude_core/ssh_servers.py), [ssh_setup.py](../packages/core/src/klaude_core/ssh_setup.py), [ssh_serving.py](../packages/core/src/klaude_core/ssh_serving.py), [ssh_panel.py](../apps/cli/src/klaude_cli/ssh_panel.py), [ssh_setup_panel.py](../apps/cli/src/klaude_cli/ssh_setup_panel.py).
- Current tests: [test_ssh_servers.py](../tests/unit/test_ssh_servers.py), [test_ssh_setup.py](../tests/unit/test_ssh_setup.py), [test_ssh_serving.py](../tests/unit/test_ssh_serving.py), [test_ssh_gpu_serving.py](../tests/unit/test_ssh_gpu_serving.py), [test_ssh_vllm_serving.py](../tests/unit/test_ssh_vllm_serving.py), [test_ssh_adoption.py](../tests/unit/test_ssh_adoption.py).
- Earlier runtime/scope: [s5c-remote-vllm-validation.md](s5c-remote-vllm-validation.md).

### I6

Actual immutable pixels, private restore, compaction, capability/revision guards and provider changes. Fresh Gemma CLI/TUI/source-deletion/resume plus HTTP fixtures.

- Implementation: [chat_images.py](../packages/core/src/klaude_core/chat_images.py), [chat_image_support.py](../packages/core/src/klaude_core/chat_image_support.py), [image_content.py](../packages/core/src/klaude_core/image_content.py), [main.py](../apps/cli/src/klaude_cli/main.py).
- Current tests: [test_chat_images.py](../tests/unit/test_chat_images.py), [test_chat_image_providers.py](../tests/unit/test_chat_image_providers.py).
- Earlier runtime/scope: [s6a2-chat-images-validation.md](s6a2-chat-images-validation.md).

### C6

Exact profile/capability/native continuation and cancellation coverage. Live OpenRouter/current Gemini successes remain historical; paid/legacy generation certification is blocked.

- Implementation: [openrouter_images.py](../packages/core/src/klaude_core/openrouter_images.py), [openai_images.py](../packages/core/src/klaude_core/openai_images.py), [gemini_images.py](../packages/core/src/klaude_core/gemini_images.py), [image_profiles.py](../packages/core/src/klaude_core/image_profiles.py).
- Current tests: [test_openrouter_images.py](../tests/unit/test_openrouter_images.py), [test_openai_images.py](../tests/unit/test_openai_images.py), [test_gemini_images.py](../tests/unit/test_gemini_images.py).
- Earlier runtime/scope: [s6-completion-validation.md](s6-completion-validation.md).

### G6

Native service/settings, one job, provenance/export/lifecycle, cancel/recovery/receipt cleanup. Fresh controlled TUI and native CUDA CLI; earlier actual CPU/native CUDA TUI results remain historical.

- Implementation: [image_generation.py](../packages/core/src/klaude_core/image_generation.py), [library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py), [generation_panel.py](../apps/cli/src/klaude_cli/generation_panel.py), [generation_commands.py](../apps/cli/src/klaude_cli/generation_commands.py).
- Current tests: [test_image_generation.py](../tests/unit/test_image_generation.py), [test_library_artifacts.py](../tests/unit/test_library_artifacts.py).
- Earlier runtime/scope: [s6b-local-generation-validation.md](s6b-local-generation-validation.md).

### T6

Explicit suggestions, unchecked selection, manual-tag independence and reviewed clearing. Fresh actual Gemma CLI/TUI and 40/70/120-column captures.

- Implementation: [image_tags.py](../packages/core/src/klaude_core/image_tags.py), [vision.py](../packages/core/src/klaude_core/vision.py), [library_artifacts.py](../packages/core/src/klaude_core/library_artifacts.py), [vision_panel.py](../apps/cli/src/klaude_cli/vision_panel.py), [library_commands.py](../apps/cli/src/klaude_cli/library_commands.py).
- Current tests: [test_image_tags.py](../tests/unit/test_image_tags.py), [test_vision.py](../tests/unit/test_vision.py).
- Earlier runtime/scope: [s6-completion-validation.md](s6-completion-validation.md).

## Visual review and limits

Fresh exported terminal captures were rendered and inspected: narrow Vision error form, narrow tag review and wide job-receipt review. Live form text wraps, failure details remain readable, and Back is the safe initial review action. Reviews are paged at narrow widths. These captures were monochrome; they do not newly certify live color rendering. Automated renderer tests cover semantic status/error classes.

Previously printed startup/banner/transcript text can clip after shrinking the terminal. It belongs to permanent scrollback and is not reflowed by live-panel redraw; the current settings/review region remains width bounded. This is a presentation limitation, not a failed image/tool request. No blanket visual/accessibility certification is claimed.

## Remaining gates and deliberate coverage limits

- **Native OpenAI:** the preceding real valid-image CLI audit returned exhausted credits. No further generation retry was made without a changed account state.
- **Native Anthropic:** no configured native connection/key at the preceding audit; no paid generation claim. Protocol/worker tests ran now.
- **Legacy Gemini:** the preceding Flash generation returned HTTP 404 and Flash-Lite preparation timed out. Current Thinking-chat historical success does not certify those exact Standard-only Media profiles.
- Exact live outcomes and required account changes remain in the [final account-access audit](s6-completion-validation.md#final-account-access-audit). These are the two unchecked nested roadmap entries; their boxes remain unchecked.
- Broader search-provider availability, other cloud models/accounts, new upstream llama.cpp/vLLM builds/downloads, physical-LAN SSH hosts and other hardware were not newly certified. Current fixture/build/process tests and earlier exact-runtime evidence retain their separate scopes.
- General complex coding success and the earlier small-model CSV benchmark are separate from this feature audit. No new CSV completion, arbitrary-task autonomy or model-quality claim is made.
- Optional image-service/auth adapters, Gallery/canvas editing and the planned INTERFACE → Web UI server/toggle remain outside delivered S6 scope. They have not become implemented by this audit.

## Regression, preservation and local evidence

Run: frozen/offline `make check`, with a task-specific writable uv cache and JUnit output. All **3,505 passed / 19 skipped** outcomes were read from the completed log and XML. The 19 skips are 18 superseded model-directed retrieval cases plus one superseded chat-selector-synthesis case; they are not newly disabled or silently failed tests. Ruff and mypy completed afterward.

At the initial verification snapshot, production source/tests/dependencies/CI were identical to the earlier passing [`86f57a3` Python 3.11–3.13 and packaging matrix](https://github.com/Chansovisoth/klaude-code/actions/runs/38749647608). That run adds a fresh local full gate, not a newly dispatched multi-version CI or packaging run. The later Library navigation change has separate validation below. No package metadata, lockfile or executable entrypoint changed.

Machine-local evidence directory: `/tmp/klaude-roadmap-verification-ompl_91m`. Receipts and logs are local diagnostic artifacts and may later be removed; the outcomes and scope needed for handoff are recorded in this document. Key files:

- `baseline.json`, original copies of the three dirty documents, `roadmap-items.json`, `coverage-map.json`.
- `make-check.log`, `make-check-result.json`, `pytest.xml`, `pytest-summary.json`.
- `commands.json`, `ui-checks.json`, four actual walkthrough logs.
- `gemma-cli-semantic-review.json`, `storage-cli-result.json`, `native-generation-result.json`.
- `vision-error-40.png`, `tag-review-40.png`, `job-cleanup-120.png`, with original SVG/text captures in their isolated QA roots.

Initial feature-audit application-source changes: **none**. Findings were QA helper assumptions and documentation traceability. The subsequent requested Library navigation change is described below. Existing dirty documentation was retained.

## Follow-up: Library directly below Memory in Settings

The user requested this navigation change during the audit. Settings now has a
Library entry immediately after Memory. It opens the existing Sessions,
Knowledge, Documents, Research, Media and Archive workspace. Nested Back returns
through Library home, then to the Library row in Settings; direct `/library`
entry still closes to chat. The canonical `/settings` registry, examples and
category dispatch also support `/settings library`.

Implementation: [settings home and dispatch](../apps/cli/src/klaude_cli/main.py),
[LibraryWorkspace](../apps/cli/src/klaude_cli/library_workspace.py). The focused
navigation regression checks row order, nested return, preserved composer draft
and direct chat entry. Focused Library/CLI settings/help selection: **57 passed,
817 deselected in 9.09 s**. A broader run exposed a stale test's assumption that
`unknown` could never match a Settings row: it legitimately fuzzy-matches the
new `knowledge` summary. The no-match regression now uses an actually unmatched
sentinel, preserving its invalid-input assertions without changing picker logic.
The corrected no-match check and complete Library module passed **24 tests in
13.60 s**. The known-red full run was interrupted after isolating that failure;
it is not reported as a passing full gate.

Actual bare TUI session **TEST KLAUDE FEATURES LIBRARY SETTINGS** passed at
40/70/120 columns: one Down from Memory selects Library, nested Documents Back
returns through Library to Settings, `/settings library` opens the same page,
and direct `/library` exposes Close and returns to chat. Process exit was 0.
Evidence: `.klaude/data/s2-models-smehla7o/library-settings-result.json` and width
captures; `/tmp/klaude-library-settings-tui-passed.log`. Earlier QA helper
attempts assumed an offscreen row was visible, skipped the existing Escape-to-
clear-filter step or expected mixed-case Close instead of the rendered CLOSE;
their incomplete receipts were retained. The final driver follows actual
scrolling/filter/navigation semantics; these were not application failures.

The initial 3,505-test gate predates this requested change. The final complete
source/test gate passed: **3,506 passed, 19 skipped in 643.16 s**, Ruff passed,
and production mypy passed on **146 files**. Wrapper elapsed: **646.35 s**.
The tracked-file snapshot was unchanged throughout this final run. Evidence:
`library-settings-final-make-check.log`,
`library-settings-final-make-check-result.json`,
`library-settings-final-pytest.xml` and
`library-settings-final-pytest-summary.json` in the audit evidence directory.
The requested navigation change, corrected assertion and added return/draft
regression are included in this run. No new multi-version CI or packaging run
is claimed for the uncommitted navigation follow-up.
