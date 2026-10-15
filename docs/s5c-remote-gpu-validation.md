# S5c, seventh slice — Reviewed remote llama.cpp GPU serving

Date: 2026-10-14. Extends [owned SSH CPU serving](s5c-remote-serving-validation.md)
and follows [retained setup removal](s5c-setup-removal-validation.md).
No commit/push, dependency, version or lockfile changes. Existing dirty S5 work is
preserved. S5c remains partial; remote vLLM/adoption and S6 are unstarted.

## User flow

Servers → saved SSH server → **Serve model** keeps CPU as the default. Private
fields include Name, Remote executable, Remote GGUF path, Remote/Tunnel port,
Context, CPU threads and GPU layers. A positive layer count reveals GPU IDs.
Test engine reports that executable's remote devices, with indices beside the
fields. GPU IDs refer to this mapping, never the client machine's hardware.

Layers 0 requests CPU; 1–999 requests offload to 1–8 distinct device indices.
Review displays the exact selected device names and layer request, alongside the
model/server/loopback ports/context. Back is initially selected; long forms and
reviews page without losing safe focus. No automatic CPU fallback or model/default
selection is introduced. Missing/reordered inventory requires a new engine test.

CLI uses the existing command and resource options:

```text
klaude model-manager serve /remote/model.gguf --ssh-server ID --executable /remote/llama-server --gpu-layers 99 --gpu 0 --context 512 --port 8080 --local-port 18080
```

Confirmation defaults to No. Accepted launch stays foreground; Ctrl+C exits 130
after owned cleanup. Failures exit 1. Device availability is not a model-fit,
GPU-allocation or inference certificate; server details label it **GPU request**.
Cancel loading and reviewed Stop retain the existing acknowledged owner cleanup.

## Architecture and bounds

- Extend LaunchSpec, existing CLI/TUI controls and the same ServingJobs/SSH
  supervisor. No second scheduler, installer, daemon or provider adapter.
- Remote engine help/device reads execute only explicit trusted installed engine
  checks. Help and initial devices share eight seconds; device refresh is bounded
  to four seconds/64 KiB. At most 32 validated unique device names are published.
  Missing flags, missing headers, errors or duplicate/oversized inventories remain
  unknown, and cannot authorize a GPU launch. CPU stays usable explicitly.
- Review reuses verified help flags and rechecks the device list. Acceptance
  verifies model/executable fingerprints and refreshes devices again, rejecting
  loss/reordering or changed selected names before spawning the model engine.
- Exact `--device NAME[,NAME]` and `--n-gpu-layers N` argument arrays pass to
  the remote engine. CPU uses `--device none --n-gpu-layers 0`. Provider keys,
  ambient CUDA visibility/engine overrides, Python-path variables and proxies are
  not copied into the engine environment; existing offline flags are retained.
- Specific bounded fixed-program preflight errors are distinct from SSH network,
  authentication/trust and protocol failures. Actual GPU progress uses the GPU
  label; failed launch events retain their cause rather than a generic wrapper.
- Existing strict SSH/credential revisions, six-second owner lease, loopback
  tunnel/listener/exact-model health checks, two-server cap, model-work gate,
  log bounds/redaction and Confirmed/Not started/Unconfirmed cleanup remain.
  No observed external PID can be adopted or stopped by this profile.
- Accepted metadata retains selected device names as a request, independently
  of future device enumeration. That metadata never claims actual layer allocation.

## Problems found and fixes

1. **GPU support was hard-rejected on both sides.** Reuse existing local resource
   fields, but make remote authorization depend on the engine's device inventory
   and fresh selection evidence. Do not infer it from a flag or generic GPU probe.
2. **Specific errors were hidden.** Completed remote metadata errors returned a
   generic diagnostic failure, and launch errors were wrapped again on the client.
   Typed bounded error replies and retained launch causes now explain invalid IDs,
   lost devices and stale reviews without publishing raw SSH stderr.
3. **Progress still said CPU.** The first native GPU run correctly offloaded but
   the client label was hardcoded. Select progress from the accepted profile;
   final native/TUI runs show GPU loading.
4. **Device mapping was below the visible fields.** An actual 120-column session
   verified the engine but could not see its mapping. Move it beside GPU fields
   and make long forms pageable; input values stay private.
5. **Paging at a boundary could change safe focus.** Review paging fell through
   to moving between controls when already at the top/bottom. Whole-body paging
   now clamps without moving Back to Launch. Ordinary table row navigation keeps
   its existing behavior; direct real key-handler regressions cover repeated keys.
6. **Narrow selected fields hid their value.** A 40-column capture showed GPU IDs
   with its value below the viewport. Short selected fields in scrollable forms
   now keep label/value visible. An initially broad adjustment broke one existing
   section-heading test; scope it to whole-body forms/reviews. All 55 focused
   panel/boundary/cancel regressions then passed, retaining ordinary headings.
7. **Cancelled checks could wait out their deadline.** The command reader noticed
   cancellation but still waited before cleanup. Reap immediately; a real child
   ignoring SIGTERM is cancelled/reaped in the focused regression.

## Real native CUDA over SSH

Temporary real loopback OpenSSH, existing GTX 1650 (4 GiB, compute 7.5), retained
CUDA llama.cpp executable built from commit
`b7ad48ebda2287c778fd826606d7b3b3570f60ab`, and unchanged qwen2.5-coder:3b GGUF.
CLI requests CUDA0, 99 layers, context 512 and two threads. No rebuild/install.

Final run: **6.39 seconds**, Chat Completions returned **OK**, engine logs report
**37/37 layers offloaded to GPU**. Ctrl+C exited **130**, remote cleanup was
**confirmed**, endpoint disabled. All **22 Ollama names/digests**, model/executable
size+mtime, QA keys/known-hosts bytes and the existing workspace file were retained.

Evidence: `/tmp/klaude-remote-gpu-native-41ntvgb_/result.json`, `gpu-engine.log`,
`serve-cli.log`; `/tmp/klaude-ssh-gpu-native-final.log` and
`/tmp/klaude_s5c_remote_gpu_native.py`. The first successful run was 6.24 seconds
at `/tmp/klaude-remote-gpu-native-pncw_ag5/result.json`, before fixing its CPU label.
These certify the exact local CUDA runtime over encrypted loopback SSH; they do
not certify a physical LAN host, another backend/model/context or vLLM.

## Actual TUI and failure recovery

Bare Klaude session **TEST KLAUDE FEATURES REMOTE GPU SERVING**, real temporary
OpenSSH and a trusted protocol fixture engine with two reported QA devices.
Six scenarios:

1. Private fields, CPU default and remote device mapping.
2. Invalid ID and changed/reordered inventory recovery before any launch.
3. Back-focused review/cancel and 40/70/120-column paging; no implicit launch.
4. Explicit selected names/layers reach the remote child; owned tunnel registers
   only after exact model/listener/health checks. Details show GPU request.
5. Private redacted logs, cancelled stop review and confirmed reviewed stop.
6. Slow GPU loading shows GPU progress, accepts visible Cancel loading and waits
   for cleanup before model work.

Final receipt: `.klaude/data/s2-models-tjrq25r6/remote-gpu-result.json`, raw terminal
log and text/SVG captures alongside it; `/tmp/klaude-ssh-gpu-tui-final.log` and
`/tmp/klaude_s5c_remote_gpu_walkthrough.py`. Exit **0**, all retained servers Stopped
with Confirmed cleanup. Original definitions, key/host bytes, model/executable and
workspace content retained; zero public model turns. Fixture devices certify
selection/protocol/lifecycle only, not GPU inference. Native evidence is separate.

70-column review and 40-column form captures were rendered and visually inspected.
Final captures additionally assert the selected `1,0` value is visible after
resize. Early walkthrough failures are retained in `/tmp/klaude-ssh-gpu-tui.log`
history artifacts and not counted as passed scenarios.

## Automated validation

New GPU coverage: selection/environment, device loss/reordering/duplicates,
invalid indices/injection-shaped strings, unknown/empty availability, malformed
evidence on both sides, specific errors, CLI No review, failed startup without
fallback/default selection, bounded probe timeout/reaping, scoped TUI controls,
repeated paging boundaries, immediate check cancellation and narrow field values.

- First focused GPU+CPU/local pass: **5 failed, 48 passed**, 72.63 seconds;
  `/tmp/klaude-ssh-gpu-focused.log`. Four failures exposed the generic launch-error
  wrapper; the fifth was a test double that did not update its page view.
- After those fixes, original new GPU cases: **20 passed**, 33.10 seconds;
  `/tmp/klaude-ssh-gpu-focused-final.log`.
- Expanded GPU/CPU/SSH/local/setup-removal regressions: **118 passed**, 101.10
  seconds, before the last probe-cancel and narrow-field tests;
  `/tmp/klaude-ssh-gpu-regressions.log`.
- Final panel/paging/cancel subset: **55 passed**, 2.07 seconds;
  `/tmp/klaude-ssh-gpu-panel-regressions.log`.
- Final `UV_CACHE_DIR=/tmp/klaude-s5-uv-cache make check`: **3076 passed,
  19 skipped**, 288.94 seconds; Ruff clean and production mypy clean across
  **132 source files**. `/tmp/klaude-ssh-gpu-full-check.log`.
- Sequential `make package-smoke`: **all five wheels built/installed, public
  imports and installed `klaude --help` passed**; `/tmp/klaude-ssh-gpu-package.log`.
  Local Python 3.12 only; no new CI/3.11/3.13 claim.

## Remaining boundaries and next slice

Remote vLLM/adoption, physical LAN-host validation, other GPU backends and GPU-fit
guarantees remain absent. CPU/GPU execution still trusts the installed engine and
remote account shell; it is not a host sandbox. Detached malicious children,
unverifiable cleanup and lost SSH receipts retain their documented limitations.
No automatic reconnect/takeover, upload/download or installation is added.

Next: reviewed remote vLLM serving, requiring its own observed engine flags,
local safetensors/model-directory checks and actual runtime evidence. S6 remains
unstarted. No full CSV coding benchmark was repeated in this settings slice.

## Primary source

[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/tree/master/tools/server)
describes device listing/selection and offload-layer controls. Installed-engine
flags, device output and real runtime behavior were verified directly; documentation
was not treated as proof that this machine or an arbitrary remote model would work.
