# S5c, eighth slice — Reviewed remote NVIDIA vLLM serving

Date: 2026-10-14. **Implemented and validated with upstream CUDA inference
through the real CLI/TUI over loopback SSH.** Follows [remote llama.cpp GPU serving](s5c-remote-gpu-validation.md).
Existing dirty S5 work is preserved. No commit/push, app dependency, version or
lockfile changes. Remote adoption and S6 remain unstarted; S5c is still partial.

## User flow

Model Manager → Servers → saved SSH server → **Serve model** → **Engine** switches
between llama.cpp and vLLM, retaining the captured SSH definition while clearing
incompatible model/evidence fields. llama.cpp still begins CPU. Remote vLLM begins
with Eager execution ON; choose an installed absolute console-script executable
and a local safetensors directory inside the configured remote models directory.

Private fields include Name, Remote executable/model directory, Remote/Tunnel
port, Context, GPU memory fraction, Precision, Eager execution and GPU IDs.
Test engine displays remote NVIDIA UUIDs next to GPU fields. IDs select that
mapping, independently of the client's hardware and ambient CUDA visibility.

Review shows exact model/server/ports, selected UUIDs, verified vLLM/CUDA versions,
precision/memory/eager/context and one-sequence concurrency. Back is initially
focused; paging never moves it to Launch. Values align on wider terminals;
complete labels and values stack on narrow screens. No fields/results become
chat turns. Accepted work retains its server/model identity through navigation.

CLI uses the existing registered command:

```bash
klaude model-manager serve /remote/models/model --engine vllm --executable /remote/env/bin/vllm --ssh-server ID --gpu 0 --memory 0.5 --dtype half --enforce-eager --context 512
```

Confirmation defaults to No. `--yes` skips that confirmation, retaining all fresh
checks. CLI eager is OFF unless explicitly enabled; TUI remote vLLM starts ON.
Serving stays foreground and Ctrl+C waits for owned cleanup before exit 130.
Failures exit 1. No automatic install/download/CPU fallback/model selection.

## Architecture, checks and bounds

- Extend LaunchSpec and the existing CLI/TUI, ServingJobs and self-contained SSH
  program. One owner/tunnel/lease lifecycle, not a parallel remote scheduler.
- Require installed vLLM's observed help flags. Help has a 30-second/512-KB bound;
  only supported launch controls are retained in evidence, keeping request size
  below the existing 16-KiB remote request limit. llama.cpp budgets are retained.
- Fixed NVIDIA UUID query has a three-second/64-KiB bound and 32-device limit.
  Select 1–8 distinct tested indices; use exact UUIDs in CUDA_VISIBLE_DEVICES.
  Fresh inventories reject device disappearance/reordering before spawn.
- Preserve the console launcher's lexical absolute Python path, including venv
  symlinks. A fixed isolated Python script checks installed Torch CUDA availability,
  selected device count/capabilities and vLLM/Torch version/metadata/interpreter
  revisions. CUDA probe: ten seconds/64 KiB. GPU compute capability below 7.5 and
  BF16 on pre-Ampere hardware fail explicitly; model Auto BF16 requests require
  an explicit compatible precision. Driver inventory alone is insufficient.
- Fresh remote tests share a 45-second budget; SSH waits at most 50 seconds, owned
  CLI/TUI read jobs 60. Local vLLM help uses 30 seconds with a 40-second owned
  read deadline, through the same CLI/TUI timeout policy. Review refreshes device/runtime evidence; launch refreshes
  again. Remote startup retains its 180-second health bound, with client headroom
  for vLLM preflight (215 seconds). Cancellation reaps owned probes/engines.
- Model bundles require regular local config.json and 1–1000 root safetensors
  files, complete bounded shard-index references and no visible symlinks/special
  files. Inventory is at most 10,000 entries, depth 16 and three seconds; config
  and shard JSON are capped at 1 MB each. Hidden root .cache/.git metadata is
  excluded. Fingerprint all visible bundle metadata, including tokenizer files,
  rather than tensor bodies. Recheck immediately before spawning after CUDA work.
- Environment identity checks cover launcher/interpreter, Torch/vLLM entry module
  metadata and distribution METADATA/RECORD. These and file stat fingerprints are
  change detectors, not cryptographic attestation of all installed code/weights.
  A hostile concurrent filesystem writer is outside this trusted-engine profile.
- Fixed argv selects safetensors, reviewed precision/memory/context, one sequence,
  selected-device tensor parallelism and one-host `mp`; optional eager skips graphs.
  No shell text, Ray cluster, custom code-trust toggle or automatic network loading.
- Engine environments omit provider keys, proxies, Python-path variables and
  ambient GPU overrides. Existing offline Hub/Transformers flags remain; disable
  vLLM/HF telemetry and use spawn for vLLM workers. These are engine settings,
  not a kernel-enforced network sandbox; installed engines remain trusted code.
- Readiness requires exact model ID, healthy loopback endpoint and a listener in
  the process group created by the remote supervisor, including frontend children.
  Scans are bounded to 4096 processes/64 members/512 FDs each. An unrelated healthy
  listener or observed PID never authorizes ownership or remote adoption.
- Retain strict SSH/definition/credential revisions, six-second owner lease,
  two-server cap, model-work gate, private bounded/redacted logs and endpoint
  registration only after ownership/health. Confirmed, Not started and Unconfirmed
  cleanup remain distinct. Stop/cancel retain models, roles and history. The
  remote receipt window is six seconds, the outer helper window eight, and client
  close/reap/reconciliation twelve; acknowledgements return immediately when ready.

## Problems observed and fixed

1. Both remote sides hard-rejected vLLM despite shared serving fields/lifecycle.
   Extend explicit engine profiles without duplicating ownership orchestration.
2. llama.cpp's device API cannot prove vLLM CUDA support. Check remote UUIDs and
   CUDA in the selected vLLM environment, with explicit precision and no fallback.
3. File-only revision tracking omitted weight shards/tokenizer changes. Use a
   bounded bundle manifest; recheck after GPU/runtime preflight before spawn.
4. A listener restricted to the engine leader rejects owned vLLM API children.
   Check the created group with bounded membership; keep unrelated PIDs excluded.
5. Returning every help flag needlessly enlarged SSH requests. Carry only controls
   this fixed profile uses, retaining the existing protocol and output limits.
6. Actual terminal captures showed ragged review values and clipped narrow labels.
   Opt in to aligned metadata for serving reviews, stacking complete fields on
   narrow screens. Ordinary Settings/table layout remains under its prior rules.
7. The long CUDA failure hid “no CPU fallback” in the footer. Shorten it to
   **vLLM CUDA unavailable; no CPU fallback**, verified in the real terminal.

## Actual terminal and SSH behavior

Bare session **TEST KLAUDE FEATURES REMOTE VLLM**, temporary real loopback OpenSSH,
synthetic vLLM/Torch wheel environment and synthetic UUID inventory. Five scenarios:

1. Engine switch, private resource inputs/eager default and observed mapping.
2. Invalid IDs and CUDA failure recover without CPU fallback or model selection.
3. Back-focused safe review/cancel and paging at 40/70/120 columns.
4. Owned frontend child listener, exact argv/UUIDs and encrypted loopback tunnel.
5. Redacted private logs, safe Stop review and confirmed multiprocess cleanup.

Final receipt: `.klaude/data/s2-models-sgjv89td/remote-vllm-result.json`, raw terminal
log and text/SVG captures beside it; `/tmp/klaude-ssh-vllm-tui-aligned.log` and
`/tmp/klaude_s5c_remote_vllm_walkthrough.py`. Exit 0, zero public model turns;
original endpoint definitions, QA key/known-host bytes, executable/weights and
workspace content retained. Visual captures were inspected after alignment.
Fixture CUDA/device evidence validates protocol/ownership, **not upstream inference**.
A bounded, explicitly framed CUDA record also tolerates benign import warnings;
those diagnostics stay private and cannot obscure a valid capability reply.

## Upstream GPU attempt

The machine had no installed vLLM/Torch environment, a GTX 1650 with 4 GiB,
and only 7.8 GiB initially free on root. A separate HDD had 528 GiB free.
An explicitly isolated QA install of **upstream vLLM 0.31.0** used PyPI binary
wheels in `/mnt/HDD1/klaude-vllm-qa-1t11fozo`, never the app/system environment.
The public **SmolLM2-135M-Instruct** safetensors copy completed: **272,496,399 bytes**,
pinned to Hub commit `12fd25f77366fa6b3b4b768ec3050bf629380bac`.

The upstream dependency downloads **hit the 1,200-second deadline**, before a
vLLM executable was installed. The installer was killed/reaped; no managed engine
was started and no native inference claim is made. Private partial environment,
cache/model and install log remain in that QA directory (about 3.3 GiB at stop)
for a subsequent explicit attempt. App metadata still reports neither vLLM nor
Torch installed; dependency/lock/version files are unchanged.

Actual CLI/loopback SSH then checked the incomplete environment: **exit 1 in
2.13 seconds**, displaying **Choose an absolute installed remote executable**.
No endpoint registration/model loading/default change/CPU fallback occurred.
All **22 Ollama names/digests**, weights/executable metadata, QA identity/known-host
bytes and workspace content were preserved. This validates graceful preflight
failure, **not vLLM execution or GPU inference**.

Receipts: `/tmp/klaude-remote-vllm-native-qnjmtpb4/result.json`, `serve-cli.log`,
`/tmp/klaude-ssh-vllm-native-attempt.log`, `/tmp/klaude-vllm-qa-install-result.json`,
the HDD `install.log`/`model-receipt.json` and `/tmp/klaude-vllm-qa-model.log`.
QA drivers: `/tmp/klaude_vllm_qa_install.py`, `/tmp/klaude_vllm_qa_model.py`,
`/tmp/klaude_s5c_remote_vllm_native.py`. No real physical LAN host is certified.

## Follow-up: completed upstream installation and real GPU validation

The original download timeout was an environment/transfer bottleneck. Completed
uv cache artifacts covered 176 dependencies. A private uv pylock pinned all 199;
23 missing wheels totalled **3,625,571,150 bytes**. One-MiB HTTPS sampling took
27.55 seconds over one connection versus 5.39 seconds over four parallel ranges.
The installed aria2c fetched missing official PyPI artifacts using bounded parallel
ranges and each published SHA-256; Python independently verified every final size
and hash. The resumed download stage completed in **2,716.56 seconds**.

Offline, hash-required installation took **32.33 seconds**, with exact local-file
references/hashes for fetched wheels and verified cache artifacts for the others.
vLLM **0.31.0**, Torch **2.13.0**, CUDA **13.0**, Ubuntu/Python 3.12, GTX 1650
4 GiB/compute 7.5. The app/system environments and project dependency/lock/version
files remain unchanged. These manual QA downloads are separate from product
serving, which never installs or downloads models/packages.

Two real failures exposed orchestration issues:

1. **Cold engine-help timeout:** first CLI failed before loading after 17.63 seconds.
   The installed command subsequently completed in 12.39 seconds, leaving almost
   no margin under 15 seconds. The local CLI also failed its older eight-second
   bound. Use explicit vLLM-only preflight headroom and one CLI/TUI policy;
   llama.cpp retains its shorter budgets. Real local `model-manager engines`
   now succeeds. A real 16-second delayed-help fixture covers both local and SSH.
2. **Shutdown under load:** CUDA generation returned HTTP 200 but the first
   interrupted run left Ready/Unconfirmed metadata at process exit. A following
   isolated run returned confirmed cleanup, demonstrating the timing gap. Outer
   four-second helper termination and seven-second close limits had insufficient
   room for remote receipt, reap and reconciliation under load. Align nested
   six/eight/twelve-second cancellation windows. A five-second delayed helper
   acknowledgement now completes before the outer client exits. No routine waits
   are inserted; unresolved remote cleanup still cannot be called confirmed.

**Final real CLI under concurrent full-test CPU load:** **Hello!**, exit **130**
after Ctrl+C, **51.53 seconds** including startup/generation/shutdown, Stopped with
Confirmed cleanup, endpoint disabled. Original **22 Ollama names/digests**, model
and executable stat, QA identity/known-host bytes and workspace file retained.
Receipt: `/tmp/klaude-remote-vllm-native-s8jee1at/result.json`, `serve-cli.log`,
`upstream-engine.log`; `/tmp/klaude-vllm-native-final.log`.

Earlier diagnostic success: `/tmp/klaude-remote-vllm-native-o1snsbyl/result.json`,
50.52 seconds, same response/cleanup; first cold failure at
`/tmp/klaude-remote-vllm-native-szo40zwq/result.json`. The first successful inference
with incomplete cleanup is retained at `/tmp/klaude-remote-vllm-native-ul706yik/`;
its result is explicitly incomplete. The owned processes exited; that QA endpoint
metadata is reconciled separately rather than mislabelled as a successful run.

**Actual bare TUI: TEST KLAUDE FEATURES LIVE VLLM.** Installed engine/CUDA/UUID
check; reviewed real versions, paths and resources with safe Back at 40/70/120
columns; real **Hello!** through the owned SSH tunnel; reviewed Stop with Confirmed
cleanup; exit **0**, zero public model turns. Original endpoint/model choices,
weights/executable metadata, QA keys and workspace content retained.
Receipt: `.klaude/data/s2-models-dgwk0kgl/real-vllm-result.json`, raw log and text/SVG
captures alongside it; `/tmp/klaude-vllm-real-tui.log`. Wide and narrow rendered
captures were inspected. Native driver scripts:
`/tmp/klaude_s5c_remote_vllm_native.py`, `/tmp/klaude_s5c_remote_vllm_real_tui.py`.

QA environment/cache/wheel/model/log retention: `/mnt/HDD1/klaude-vllm-qa-1t11fozo`,
including `pylock.toml`, `missing-wheels.json`, `wheel-download-result.json` and
`offline-install-result.json`. Sources, pinned model commit and exact verification
steps make the results repeatable. Only the new private QA data is retained.
This validates this serving configuration; it is not a complex coding benchmark,
a physical LAN certification, other-model hardware-fit guarantee or proof of
model tool capability. No remote adoption or S6 implementation was started.

## Automated validation

- Initial SSH/vLLM/GPU/CPU run: 62 passed, one test harness view setup error;
  corrected and rerun. Final profile: 25 passed in 45.43 seconds, including slow
  loading cancellation and helper-death frontend/worker cleanup.
- Shared serving/recipe/panel run: 111 passed, one local cleanup wait timed out
  during concurrent QA installation/testing. It passed in isolation (with the
  corrected review test, two passed in 1.49 seconds). The live follow-up exposed
  the shutdown-budget issue above and verifies its correction.
- Final aligned review/panel subset: 53 passed in 1.33 seconds.
- **Full `make check`: 3,102 passed, 19 skipped in 356.81 seconds**, Ruff clean,
  production mypy clean across 132 source files. No cleanup timeout recurred in
  this run. `/tmp/klaude-ssh-vllm-full-check.log`.
- A subsequent small CUDA framing/module-identity refinement was verified by
  **all 27 final vLLM profile tests, 44.58 seconds**, then current Ruff and all
  production mypy. `/tmp/klaude-ssh-vllm-profile-current.log`. The 3,102 count is
  from the preceding full run; it does not include the newly added warning test.
- **`make package-smoke` passed**: five wheels, isolated installation/public imports
  and installed `klaude --help`. `/tmp/klaude-ssh-vllm-package.log`. Run after the
  complete suite. `git diff --check` also passed. Python 3.12 locally; no new CI
  Python 3.11/3.13 result is claimed.

## Follow-up regression gates

- Cold-start SSH/vLLM/CPU/GPU regressions: **68 passed in 146.04 seconds**.
- Shutdown group: **43 passed**, one new fixture incorrectly intercepted the
  engine preflight. Corrected; isolated slow-helper test **passed in 16.63 seconds**.
- Full gate before extending the same budget to local vLLM: **3,105 passed,
  19 skipped, 360.54 seconds**, Ruff and production mypy (132 sources) passed.
  `/tmp/klaude-vllm-native-full-check.log`.
- **Final exact-tree `make check`: 3,106 passed, 19 skipped in 375.53 seconds**,
  Ruff clean and production mypy clean (132 source files). Includes the final local/
  remote 16-second help and five-second cleanup regressions.
  `/tmp/klaude-vllm-final-full-check.log`.
- The real local metadata-only CLI now reports Engine ready:
  `/tmp/klaude-vllm-local-engine-final.log`.
- **Final `make package-smoke` passed**: five workspace wheels, isolated install/
  public imports and installed `klaude --help`, after the full suite.
  `/tmp/klaude-vllm-final-package.log`. `git diff --check` passed.
- All 44 unrelated previously changed/untracked files retained their beginning-
  of-turn SHA-256. Only seven implementation/test files and five relevant docs
  changed in this continuation. No commit or push. Python 3.12 locally; no new CI
  Python 3.11/3.13 claim.

## Scope and next step

This profile supports existing Linux NVIDIA CUDA vLLM environments with standard
absolute Python console launchers, local regular safetensors bundles and one-host
workers. Shell-wrapper launchers, alternate accelerators, multi-node/Ray serving,
remote installation/upload/download, physical LAN certification and remote adoption
are outside it. Generic ready-model tool/context capability is still unknown;
metadata/health must not imply coding-agent tool reliability or hardware fit.
Very narrow chat status/banner layout remains a separate shared TUI limitation.

The next step is **reviewed remote adoption**, requiring separate ownership
evidence and permission; observed processes are diagnostics only.
S6 remains unstarted. Additional install/platform recipes are separately scoped.

## Primary references

- [vLLM serve CLI](https://docs.vllm.ai/en/stable/cli/serve/): fixed flags,
  precision, tensor parallelism and executor selection.
- [GPU installation requirements](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/).
- [Memory controls and eager execution](https://docs.vllm.ai/en/stable/configuration/conserving_memory/).
- [Environment variables](https://docs.vllm.ai/en/stable/configuration/env_vars/).
- [OpenAI-compatible server](https://docs.vllm.ai/en/stable/serving/online_serving/openai_compatible_server/).
- [Published vLLM package](https://pypi.org/project/vllm/).
