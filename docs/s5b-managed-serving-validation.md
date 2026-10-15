# S5b — Managed local model serving

Date: 2026-10-14. Follows [S5a native Ollama lifecycle](s5a-model-manager-validation.md)
and implements the [S5b serving slice](odysseus-settings-and-features-plan.md#s5--model-manager).
S5c installation/rebuilds/SSH and S6 are not started. No dependencies, lock or
version changed; prior dirty S5a work is retained without commit/push.

## Product flow

Model Manager → **Serve models** opens Launch server, Reload servers and Adopt
existing server before the SERVER/STATE/ENGINE inventory. Forms collect name,
engine, installed executable, local model path, port and context. llama.cpp offers
CPU threads/GPU layers and GPU IDs when offloading; vLLM offers GPU memory fraction
and device IDs. Test engine runs bounded help/device queries without loading a
model. Review launch checks local weights and initially selects Back.

Accepted launch loads a local model. It does not download weights, install an
engine, select a session/default model or change the configured Ollama service.
After health/catalog and listener ownership checks, a new compatible endpoint
appears in Added Models. Select it through the existing model flow. Detail actions
precede status, endpoint and model identity; Logs shows a bounded private tail.
Stop requires another Back-focused review. Closing that review leaves the server
running; accepting Stop disconnects its users, disables the unchanged generated
endpoint and retains model files/roles/history.

Servers belong to the current **client**, rather than one conversation. Ready
servers can be used across session changes; starting/stopping gates new model work.
They stop when that owning Klaude client exits. Another client's retained record
does not grant stop permission. Logs and launch fields are never injected into
model context. Existing normal terminal scrollback and composer/editor behavior
are retained; long metadata/logs wrap within the shared scrolling panel.

Adoption is explicit process ownership transfer. It requires a live same-account
PID, matching tested executable, an isolated process group/session, the actual
model ID, and a ready local endpoint whose listener belongs to that group.
Internal Ollama runners, another helper's children and shared shell groups are
rejected. Failed adoption leaves the original process running. Accepted adoption
stops that server on Stop/client exit. Its original stdout cannot be acquired;
the Logs action explains that its original log destination remains in use.
Adoption review shows the actual existing model ID/PID and omits context/device
settings, since taking ownership does not change that process's launch settings.

CLI commands are registered with the canonical command reference:

```text
klaude model-manager engines [--engine ENGINE] [--executable PATH]
klaude model-manager servers
klaude model-manager logs SERVER_ID
klaude model-manager serve MODEL [--engine ENGINE] [--executable PATH] [--yes]
klaude model-manager adopt PID MODEL_ID [--executable PATH] [--port N] [--yes]
```

Serve also offers `--name`, `--port`, `--context`, `--threads`, `--gpu-layers`,
`--gpu` and `--memory`; actual help is authoritative. It remains foreground until
interrupted. Mutations confirm unless `--yes` explicitly accepts the review.
Startup/helper failures exit 1; SIGINT cleanup exits 130. A successful metadata
inspection exits 0. There is no detached launch daemon or cross-client stop command.

## Ownership and bounds

Core `managed_serving.py` owns validation, fixed argument construction, metadata,
health checks, registration and cleanup. CLI `serving_jobs.py` owns persistent
helper processes; `serving_panel.py` adapts the shared panels. Existing
OwnedBackgroundJobs handles replaceable preflight/inventory/log reads. Its normal
completion kills descendants, so it is deliberately not used as a long-lived
server owner. A dedicated helper retains a private stdin lease: EOF means its
client ended, even after parent process loss. Supervisors reap their group and
conditionally disable unchanged generated definitions after unexpected helper exit.
Helpers persist and flush terminal acknowledgements before terminating their own
isolated group, including workers that ignore graceful termination. Cancellable
raw log reads prevent inherited stdout pipes from blocking shutdown.

- Loopback only (`127.0.0.1`), ports 1024–65535; startup deadline 180 seconds.
- Engine help/device commands: 8 seconds each, 512 KB output; preflight job 15 seconds.
- Context 512–65,536 (default 8,192); threads 1–256 (default 4).
- llama.cpp GPU layers 0–999, default 0/CPU. Requested offload requires a tested
  device inventory and selects exact engine device labels. No silent CPU fallback.
- vLLM memory fraction 0.1–0.95, default 0.5; one sequence and explicit visible
  GPU IDs/tensor parallel count. Actual allocator/backend support stays engine-owned.
- Two owned live servers per client; 32 retained records. Expiring terminal records
  removes their private log file. Logs retain at most 256 KiB, preview at most 16 KiB.
- HTTP health/catalog: connect 0.5 seconds/read 2 seconds, 1 MB body, 1,000 models,
  no ambient proxies or redirects. Exact reviewed/generated model ID is required.

Executables are checked by file identity and supported flags. Local GGUF headers
or local safetensors/config files are required; executable/model metadata is
rechecked after review. Arguments are lists rather than shell input; arbitrary
extra arguments, remote-code switches, credentials and installer commands are not
accepted. Engine environments omit ambient provider secrets and Python-path
variables; Hub/Transformers are offline. Jinja is explicitly enabled when the
tested llama.cpp supports it; tool quality remains unknown rather than inferred.

Registration is performed only after a ready API/catalog plus owned socket check.
Existing native definitions are seeded through the existing registry migration
only as part of accepted registration; defaults/session preferences are retained.
Shutdown disables only the exact unchanged generated definition and invalidates
its catalog scope. User edits/removal are preserved rather than overwritten.
Retained starting/ready records whose helper identity no longer matches show
Interrupted without silently mutating configuration during browsing.

## Validation

### Actual installed engine

PATH did not contain llama-server/vLLM. Read-only inspection found an installed
`/usr/local/lib/ollama/llama-server` launcher with the required standard server
flags. A separate build in `/home/klaude/draft/llama` failed its help check because
`libmtmd.so.0` was missing; it was neither modified nor rebuilt. vLLM is not installed.

The real foreground manager CLI served read-only installed **qwen2.5-coder:3b**
GGUF weights on CPU, with 512 context and two threads. It registered only after
readiness, exposed the correct model alias, and returned **OK** over actual
OpenAI-compatible chat. SIGINT exited **130**, stopped the QA server and disabled
its endpoint. All **22 original Ollama names/digests were unchanged**. Evidence:
`/tmp/klaude-s5b-native-vibsuv20/result.json` and its private `cli.log`.

The real `klaude ask "Reply with exactly OK." --model QUALIFIED_REFERENCE`
consumer also **passed**, returned **OK**, and exited **0** with 8,192 context,
four CPU threads and no GPU offload. Engine logs show **5,708 input tokens** and
**191.1 seconds of prompt processing**, without truncation or provider retries.
This demonstrates endpoint/runtime interoperability, not coding-task capability.
SIGINT subsequently returned 130, disabled the endpoint and preserved all 22
original Ollama names/digests. Evidence:
`/tmp/klaude-s5b-native-j14_ksnv/result.json`, `ask.log` and private engine log.

The first 8,192-context/two-thread attempt hit the QA driver's 90-second deadline
while the engine was still processing the initial prompt. Logs showed roughly
5,700 prompt tokens, not provider retries. The successful four-thread retry used
a 240-second QA deadline with the unchanged prompt. That timed-out attempt is
not a pass. After the final shutdown changes, a separate actual-engine CLI/API
run again returned OK, stopped cleanly and retained the same 22 digests:
`/tmp/klaude-s5b-native-ig5jn2hy/result.json`.

NVIDIA-SMI could not communicate with the driver; the engine's actual device
probe returned **Available devices: (none)**. Real GPU inference is unverified.
Requested GPU offload now fails explicitly when that inventory is unavailable.
No GPU service, driver or dependency was repaired as part of S5b.

### Real TUI walkthrough

Bare Klaude used an isolated workspace/config/data store and session **TEST KLAUDE
FEATURES MANAGED SERVING**. Nine final scenarios passed: private field editors and
engine test; Back-focused review/cancel without launch; owned startup and
health-gated registration; redacted bounded log and cancelled Stop review;
accepted Stop/cleanup with history retained; 40/70/120-column inventories;
adoption review showing the existing model ID without unapplied launch settings;
explicit adoption/owned stop; and missing-engine error without download/install.
A pre-existing workspace file was retained. Evidence:
`.klaude/data/s2-models-wpz6cqkw/serving-result.json`, its SVG/text captures and
`/tmp/klaude-s5b-final-tui.log`. Visual inspection confirms aligned fields at 120
columns and wrapped inventory at narrow widths; controls precede headers/records.

Earlier driver attempts awaited an offscreen editor hint and initially lacked
the test module's import path. The missing absolute executable test also exposed
an actual generic-error issue, now normalized to actionable Engine unavailable
feedback. These failed attempts are not successful walkthroughs.

### Automated regression gates

Actual worker/process fixtures verify health registration, lease cancellation,
port conflict, changed model/executable, engine failure, helper death/group cleanup,
abrupt client death with a worker ignoring SIGTERM, preservation of user-edited
endpoint definitions, adopted identity/session safety and failed adoption
preserving an external process. A vLLM protocol fixture verifies local safetensors,
explicit GPU/tensor settings, offline environment and registration/cleanup. This
is protocol evidence, not live vLLM inference. GPU-unavailable rejection is covered.
Existing Ollama lifecycle, model settings and CLI tests retain their gates.

The final focused serving suite passed **18 tests** in 8.79 seconds. A prior
combined run failed helper-crash notification intermittently: pipe EOF could
precede a visible exit status. Waiting for exit classification fixes that race.
The new abrupt-client-death test then exposed a real shutdown deadlock: a worker
inheriting stdout kept a buffered readline open, blocking close before endpoint
disable. Cancellable raw reads and final helper group termination repair it.
Both scenarios passed again through real processes, not only mocked state.

Final local gates, after the implementation and crash fixes:

- `UV_CACHE_DIR=/tmp/klaude-s5-uv-cache make check`: **2,908 passed, 19 skipped**
  in 175.79 seconds; Ruff passed and production mypy passed **119 source files**.
  Log: `/tmp/klaude-s5b-final-check.log`.
- Sequential `make package-smoke` with that cache: **all five wheels built,
  installed and imported**, and installed `klaude --help` passed. Log:
  `/tmp/klaude-s5b-final-package.log`.
- `git diff --check`: passed. No lock/dependency/version change, commit or push.

## Remaining limits

- GPU inference and real vLLM serving are unverified on this machine; neither is
  available now. S5c owns explicitly requested installs/rebuilds and SSH settings.
- Servers are client-owned and stop on exit; detached/durable serving and remote
  process adoption are not implemented. Linux `/proc` ownership is required.
- Adoption only controls a validated isolated group. Identity loss is handled
  conservatively; it does not authorize killing an unrelated reused PID/group.
- A launched model's configured context can be insufficient for a full agent
  prompt. Catalog listings still do not prove model limits, tool quality or fit;
  there is no automatic context enlargement/model switch. CPU prompt prefill can
  be slow, as the real consumer attempt demonstrates.
  The existing initial agent prompt was about 5,700 tokens even for the short OK
  task. Reducing that context is a separate agent-efficiency investigation;
  S5b does not claim to resolve it or to accelerate CPU-only inference.
- Advanced options are limited to verified supported fields. Native environment
  setup, custom libraries, backend compilation, remote-code models and launch
  presets are later scoped work. No arbitrary environment/shell option is exposed.
- Ready records represent successful startup plus process continuity; they do
  not certify every subsequent request. Existing endpoint Test/Probe remains the
  catalog diagnostic owner. No model-fit, throughput or general coding benchmark
  claim follows from a working endpoint.

## Primary sources inspected

- [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
  for supported flags, health, aliases and OpenAI-compatible routes.
- [llama.cpp function calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)
  for explicit Jinja support; model tool quality is independently unverified.
- [vLLM serve](https://docs.vllm.ai/en/latest/cli/serve/) for local model/served name,
  context, tensor parallelism, safetensors and memory controls.
