# S5c, fifth slice — Local CUDA builds and isolated vLLM wheel setups

Date: 2026-10-14. Extends the [committed-source CPU build](s5c-dependencies-validation.md)
and [managed local serving](s5b-managed-serving-validation.md) consumers.

This slice implements an explicit NVIDIA CUDA llama.cpp build profile and an
offline NVIDIA vLLM installation from a complete trusted local wheel set. It
reuses the owned setup worker, inventory, private logs, cancellation and model-work
gate. Reviewed setup removal is implemented in the
[follow-up slice](s5c-setup-removal-validation.md); remote llama.cpp GPU profiles
are also covered in a [follow-up](s5c-remote-gpu-validation.md). Remote vLLM/adoption
extensions remain unfinished. No commit/push, version, dependency or lock changes.

## Working CLI and TUI

Model Manager → Dependencies offers separate CPU build, CUDA build and Install
vLLM from wheels forms. Source/architecture/compiler/interpreter inputs are
private and never become chat/model turns. Reviews focus Back and page long
wrapped details. Inventory and setup logs are shared across recipes; verified
results open a fresh Serve draft with the correct engine and model path focused.
No server launch or model/default selection happens on installation/handoff.

CUDA fields: committed local source checkout, 1–8 jobs (default two), architecture
targets and optional absolute host compiler. Blank architectures use observed
NVIDIA compute capabilities; explicit numeric targets allow compilation without
a working GPU. Installed NVCC must support every target. A small fixed-code
compilation probe checks the host compiler before persistent build writes. It
never uses `--allow-unsupported-compiler`. The existing snapshot/static library/
disabled fetch/Web UI conventions apply. Uncommitted source edits are retained.

vLLM fields: trusted local wheel folder and installed Linux Python interpreter.
The recipe requires one version per package, including vLLM and CUDA PyTorch.
Preflight resolves dependency closure and Python/platform compatibility offline
before copying any persistent setup files. A fresh environment receives only
copied, exact-version/hash-pinned wheels; backend/version and required engine
help checks precede Ready publication. Ready certifies those setup checks; it
does not certify GPU inference, model fit or available GPU memory.

```text
klaude model-manager build SOURCE --profile cuda --architectures 75 --host-compiler /usr/bin/g++-12 --jobs 2
klaude model-manager install-vllm WHEELHOUSE --python /usr/bin/python3.12
klaude model-manager builds
```

Confirmations default to No; `--yes` accepts the reviewed effect. CLI Ctrl+C
returns 130 after local cleanup. Accepted setup work gates model jobs and survives
navigation; cancellation reaps the owned helper/compiler/installer group before
queue consumption. Partial/failed/interrupted files are retained for inspection.
Late callbacks cannot replace another session's result or a private editor.

## Architecture, safety and limits

- `model_recipes.py` validates CUDA targets/compiler and local wheel metadata,
  ZIP structure, hashes, Python/platform and offline dependency closure.
- `model_dependencies.py` owns setup records, shared resource/deadline checks,
  fixed commands, source snapshots, logs, worker ownership and publication.
- `dependency_panel.py`/`model_manager_commands.py` expose the recipes through
  existing typed panels and owned jobs. `serving_panel.py` retains the selected
  engine in its fresh draft; command reference entries are canonical in `main.py`.
- Installed tools/interpreter/source/wheel revisions are rechecked at acceptance.
  Copied wheel hashes are checked again, then uv enforces hashes/exact versions.
- uv runs with no network, index, ambient configuration, cache, interpreter
  download or source-distribution build. Existing app/system Python environments,
  engines, model files, endpoints and defaults are retained.
- At most 128 wheels; each at most 2 GiB, total compressed at most 8 GiB and
  expanded at most 32 GiB. ZIP directory/entry/metadata limits are checked before
  large parsing. Symlinks, traversal, encryption and URL dependencies fail closed.
- Review requires compressed bytes + twice expanded bytes + 2 GiB free. The
  existing runtime 256-MiB floor, 30-minute owned deadline and eight-retained-setup
  bound apply. Tools/probes use bounded subprocess output and deadlines; logs
  remain private/bounded and never enter model context.
- Build/package code executes under the user's account and requires trusted
  inputs. This is not an OS sandbox. API credentials/proxy configuration are not
  inherited by setup commands. Drivers, OS packages, online wheel downloading,
  other GPU platforms and vLLM source builds are outside this slice.

## Observations and improvements

The sandboxed NVIDIA probe could not communicate with the driver. The real
Klaude worker discovered GPU targets, so a separate unsandboxed read corrected
that limitation: **GTX 1650, compute 7.5, 4,096 MiB VRAM, driver 595.99.02**.
This is current metadata, not a model-fit claim. No driver/service change occurred.

Installed NVCC is CUDA 12.0; system C++ is GCC 13. The actual compiler diagnostic
rejects GNU versions above 12. Selecting installed GCC 12 passes the fixed probe
and native CUDA compilation. Compiler checks now fail before a persistent build
instead of starting a lengthy build with incompatible host tools. Architecture
targets are observed/explicit rather than guessed from a GPU name.

Initial wheel setup deferred dependency/platform rejection until installation.
The follow-up moved offline resolution before copying/venv creation. Real CLI
checks now reject an incomplete wheel closure without creating a setup directory.
No source/network fallback substitutes for missing reviewed wheels.

The original Serve handoff always assumed llama.cpp. It now carries the setup's
engine explicitly, so a vLLM result opens a vLLM draft. Setup callbacks also
reject changed session/draft/editor state. Shared reviews page safely at narrow
widths, and controls precede the inventory rather than occupying table rows.

## Real scenarios and receipts

- Six real CLI/TUI scenarios passed in session **TEST KLAUDE FEATURES ENGINE
  RECIPES**: automatic target/compiler rejection, explicit target/compiler
  recovery, native CUDA fixture compile, review cancellation, isolated offline
  wheel installation, correct Serve handoff, shared inventory and live cancellation.
- TUI layouts captured at 40/70/120 columns. Colored 70-column CUDA and 40-column
  vLLM review renders were inspected; Back stays selected, paths/values wrap, and
  long reviews page within fixed headers/footers.
- Source dirty edits, original wheel bytes, workspace content and endpoint
  definitions remained unchanged. Session database contained zero chat/model turns
  from setup. These wheel tests use **local QA vLLM/Torch protocol fixtures**;
  they do not certify installation or inference of upstream vLLM/PyTorch.
- Receipt: `.klaude/data/s2-models-d9eup7rn/recipes-result.json`; captures and
  terminal log in that isolated root. Driver: `/tmp/klaude_s5c_recipe_walkthrough.py`;
  output `/tmp/klaude-recipes-walkthrough.log`.
- After the resolver change, three more real CLI cases passed: incomplete closure
  rejected before mutation, cancelled review without mutation, and offline
  installation/help check. Receipt `/tmp/klaude-resolver-cli-arsa_5y7/result.json`;
  driver output `/tmp/klaude-recipes-resolver-cli.log`.
- A real full-source two-job CUDA build was cancelled through its verified CLI
  owner, **exit 130 after 911.74 seconds**, retaining partial source/objects/logs.
  The on-disk Building record is projected Interrupted after owner loss; cleanup
  is verified against the owned process group. `/tmp/klaude-native-cuda-jzc0hvib/result.json`.
- Full-source CUDA build from the same `b7ad48ebda2287c778fd826606d7b3b3570f60ab`
  commit completed through the real CLI: **eight jobs, 769.31 seconds, exit 0**,
  GCC 12, architecture 75 and detected `CUDA0`. It completed all 374 compiler/link
  steps. `/tmp/klaude-native-cuda-efb3djgn/result.json`, its CLI log and private
  build log contain the receipt. The default remains two jobs; eight is an
  explicit exposed setting for this 8-core/32-GiB machine, not an automatic change.
  The cancelled two-job run is not counted as a completed timing comparison.
- Newly built engine served **qwen2.5-coder:3b** through the real managed-serve
  CLI with explicit GPU 0, 99 requested GPU layers and context 512. Native logs
  confirm layer offload and a CUDA0 model buffer. Actual completion returned
  **OK**; start/generate/Ctrl+C/stop took **4.36 seconds**, exit **130**. The stopped
  owned endpoint was disabled, original weight size/mtime and all **22 original
  Ollama model digests** were retained. Receipt:
  `/tmp/klaude-cuda-inference-ebitmniv/result.json`, CLI/private native logs in that
  root; driver `/tmp/klaude_s5c_cuda_inference.py`, output
  `/tmp/klaude-recipes-cuda-inference.log`.
  The first inference run reached generation but the QA script looked for the
  wrong log filename; its finally block stopped the server. The corrected complete
  run passed without a product change. This is one short local GPU generation,
  not a full coding benchmark or a vLLM certification.

## Automated regression gates

- Existing CPU recipe regressions: **17 passed in 6.03 seconds**.
- Combined recipes/CPU checks: **37 passed in 13.19 seconds**.
- After early resolver improvement: **20 passed in 10.67 seconds**, including
  actual CUDA compile/link and offline uv installation, dirty/source-byte retention,
  credential canary, changed input/tool revisions, malformed/unsafe wheels,
  insufficient disk, incomplete/incompatible/CPU backend rejection, bad engine
  help, cancellation and stale UI/handoff checks.
- Full gate: **3,016 passed, 19 skipped in 262.63 seconds**. Ruff clean;
  production mypy clean for **131 source files**.
  `/tmp/klaude-recipes-release-check.log`.
- Sequential distribution smoke: **all five wheels built/installed, imports and
  installed `klaude --help` passed**. `/tmp/klaude-recipes-release-package.log`.
- Local Python 3.12; new CI/Python 3.11/3.13 certification is not claimed.

## Remaining boundaries

Live upstream vLLM installation/inference, remote vLLM/adoption profiles,
other GPU platforms and online/system installation still
need their own evidence/implementation. No full CSV coding benchmark is rerun in
this settings slice. Native CUDA runtime evidence is recorded above for the exact
tested build/model/context. Other model/hardware configurations remain unverified.
S6 remains unstarted.

## Primary sources

- [llama.cpp build instructions](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md):
  CUDA build controls and explicit CMake architecture targets. Installed NVCC and
  compiler behavior are verified locally rather than inferred from documentation.
- [vLLM GPU installation](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/):
  current Linux/Python/hardware requirements and separate-environment guidance.
  This local recipe intentionally resolves the supplied wheel set without an
  online index, automatic PyTorch replacement or guessed hardware fit.
