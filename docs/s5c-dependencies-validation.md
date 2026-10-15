# S5c, first slice — Local dependencies and reviewed CPU builds

Date: 2026-10-14. Continues [S5b serving](s5b-managed-serving-validation.md).
This delivers local dependency inspection and a useful explicit llama.cpp CPU
build. S5c is **partially complete**: the later [SSH settings/diagnostics slice](s5c-ssh-validation.md)
is documented separately; remote lifecycle and additional GPU/vLLM installation
recipes remain unfinished. S6 has not started. Prior dirty S5a/S5b work is retained;
there is no commit, push, dependency, lock or version change.

Follow-up: [CUDA build and offline vLLM wheel recipes](s5c-engine-recipes-validation.md)
now extend the CPU consumer, with separate native GPU/runtime and fixture-install
evidence. The scope/counts below retain this first slice's historical validation.

## User flow

Model Manager → Dependencies offers Inspect dependencies, engine/executable
selection, Build llama.cpp CPU engine and Built engines before diagnostics.
Inspections show observed CMake/Ninja/Git/C/C++ versions and test the selected
engine through its bounded help/device protocol. Missing engines/tools remain
Unavailable, without starting package installation or generation. Actual engine
availability is independent of a present compiler.

CPU build collects a local source checkout and 1–8 build jobs (default 2).
Review resolves the exact committed HEAD, checks tools/free space, clears old
filters and initially focuses Back. It explains that build instructions execute
trusted source code. Cancelling review writes no build files. Accepting creates a
new private snapshot/build directory; uncommitted source changes are excluded,
never overwritten. Successful results offer Use in Serve models, which opens a
fresh draft with the executable filled and Local model path selected. It neither
starts serving nor selects a session/default model. Failed/cancelled builds offer
logs and retain partial files; they publish no verified executable.

Controls precede tables/metadata. Logs use bounded owned reads and a scrolling
preview; they do not enter model context or the chat transcript. Footer feedback
uses errors/warnings/success semantics. Existing draft, Back, filter and terminal
scrollback behavior is reused. Completed builds replace Cancel with the next
useful action. Active chat, Knowledge, Research and Utility work gate builds;
accepted builds gate new model work until completion or compiler cleanup.

Canonical CLI entries:

```text
klaude model-manager dependencies [--engine ENGINE] [--executable PATH]
klaude model-manager builds
klaude model-manager build SOURCE [--jobs N] [--yes]
```

Build asks for confirmation by default; `--yes` accepts the displayed source
review. Success/cancelled review/failure/Ctrl+C exit 0/0/1/130 respectively.
Metadata inspection can complete with an Unavailable engine; this is a diagnostic
result, not a claim that the engine works. No arbitrary shell arguments, apt,
driver changes, SSH key changes or package installer scripts are exposed.

## Architecture and limits

- Core `model_dependencies` owns observations, committed source snapshot,
  supported CPU recipe, validation, manifests and bounded private logs.
- CLI `dependency_panel` and model_manager_commands use the same fixed operation
  through existing OwnedBackgroundJobs. Accepted work survives page navigation;
  replaceable reads reject old request/session/draft results. Results never
  reopen a later page/private editor. Model Manager includes build/cancellation
  state in its shared model-work gate and live activity.
- Supported host: existing Ubuntu/Linux tools. Read commands use four-second
  deadlines and bounded output; the owned preflight has a 40-second outer limit.
- Build deadline: 30 minutes, with stage progress throttled to once per second.
  Compiler output stays in private logs, rather than filling chat/CLI scrollback.
- At least 2 GiB free at review/acceptance; compilation stops below 256 MiB.
  Snapshot bounds: 50,000 entries/256 MiB total/32 MiB per file. Absolute/traversal
  paths, links and special files are rejected. Extraction never writes the
  selected checkout. Tools/HEAD are rechecked before accepting execution.
- The snapshot is immutable committed source, not a copy of the dirty worktree.
  Git hooks/global configuration and ambient provider credentials are excluded.
  Build HOME is private; CMake uses fixed tool paths and argument arrays.
- The recipe builds only llama-server in Release mode with static llama/ggml
  libraries, one supported CPU profile, no embedded Web UI, and declared optional
  accelerator/SSL/cache/fetch options disabled. FetchContent is disconnected.
  This reduces unintended downloads for the supported recipe; **it is not a
  sandbox for malicious CMake/build code**. Choose a trusted source commit.
- No existing executable/system installation/default is replaced. The built
  executable must pass S5b flag checks before publication. Listings detect
  changed/missing binaries instead of continuing to offer them as verified.
- Eight retained builds maximum. Partial/failed builds and their private files
  remain under `data/model-builds/ID`; automatic deletion and an in-product build
  removal workflow are not implemented. Logs retain about 256 KiB, preview 16 KiB.
- Normal cancel/exit kills/reaps the owned compiler group. During build commands,
  unexpected client death is detected through the captured parent identity;
  failure is persisted and the worker ends its owned group. Inventory projects
  a dead worker's unfinished record as Interrupted without browsing writes.

## Actual validation

### Real local source and installed model

The real `klaude model-manager build` ran on committed source
`b7ad48ebda2287c778fd826606d7b3b3570f60ab` from the existing local llama.cpp checkout.
Compilation used two jobs and finished in **294 seconds**, exit **0**. The new
private executable passed its help/device protocol and the real manager serving
CLI loaded unchanged **qwen2.5-coder:3b** GGUF weights on CPU. OpenAI-compatible
chat returned **OK**. SIGINT stopped that server, exit **130**. The original
source worktree status and all **22 original Ollama names/digests were unchanged**.
Total build/serve/check time was 300.77 seconds. Evidence:
`/tmp/klaude-s5c-native-ex9t0f3d/result.json`, `build-cli.log`, `serve-cli.log` and
the retained private build manifest/log.

This is an actual source build and actual model-generation check, not only a
CMake fixture. The older local build with missing `libmtmd.so.0` was not modified;
the separate static-library recipe produces a usable new executable. GPU/vLLM
inference and a difficult coding benchmark are not certified by this result.

### Real CLI/TUI

Bare Klaude used **TEST KLAUDE FEATURES DEPENDENCIES** in an isolated workspace.
Six final scenarios cover read-only diagnostics at 40/70/120 columns; private
source form and Back-focused cancelled review; real Git/CMake fixture build;
bounded logs and serving draft/focus; actual compiler cancellation/cleanup; and
missing-source failure without installation. A dirty fixture source file,
workspace user file and endpoint registry bytes were retained.

Final evidence: `.klaude/data/s2-models-em_11nk6/dependency-result.json`, its SVG/
text captures and `/tmp/klaude-s5c-tui-release.log`. Visual inspection confirms
wrapped narrow diagnostics, controls above metadata and a Back-focused review.
Earlier driver attempts failed due to a nested import delimiter and an assertion
expecting an unwrapped executable path. Inspection confirmed the long path was
correctly wrapped. These driver failures are not successful runs. The walkthrough
also motivated a single fresh serving-draft initializer, preserving correct
focus and clearing old feedback before pre-filling the new executable.

### Automated gates

Focused local dependency tests initially passed **15 tests**, using real Git/CMake/compiler
processes for snapshot safety, dirty-source preservation, absent credentials,
changed commit/binary, corrupt records, disk guard, configure/compile/flag/link
failures, cancellation and actual owning-client death. Compiler-dependent tests
skip honestly if those local tools are absent. The combined dependency/native
Ollama/serving/CLI suite passed **913 tests, 1 skipped** before the last two safety
cases; that earlier count is not the final complete suite.

A previous serving regression waited for endpoint disable before immediately
asserting its separate manifest update. These are consecutive filesystem writes;
the test now waits for both completion conditions. No teardown ordering or
production success claim was weakened.

The first full `make check` passed **2,923 tests, 19 skipped**, Ruff and production
mypy (**121 source files**). A subsequent forced-cancellation case exposed an
existing probe ownership gap: an isolated help process ignoring SIGTERM could
outlive its worker's forced cleanup. The regression reproduced that failure;
owned probes now inherit the worker group, while standalone probes retain their
own group. The combined dependency/serving process suite then passed **34 tests**.
The final run also covers read-only review with an absent/new data directory.

Final gates, after the forced-cancellation fix and fresh-directory test:

- `UV_CACHE_DIR=/tmp/klaude-s5-uv-cache make check`: **2,925 passed, 19 skipped**
  in 185.02 seconds; Ruff passed; production mypy passed **121 source files**.
  Evidence: `/tmp/klaude-s5c-release-check.log`.
- Sequential `make package-smoke` with that cache: all **five wheels** built,
  installed and imported; installed `klaude --help` passed. Evidence:
  `/tmp/klaude-s5c-release-package.log`.
- The newly built actual llama.cpp executable passed the final owned probe
  implementation through `klaude model-manager engines --executable PATH`.
- `git diff --check` passed. Changes remain uncommitted; no lock/version/dependency
  metadata change or Git push was performed.

## Remaining work

- SSH server configuration, connectivity and bounded directory/resource/process
  snapshots are implemented in the [follow-up slice](s5c-ssh-validation.md).
  [Owned remote CPU serving](s5c-remote-serving-validation.md) is also implemented;
  key enrollment and additional GPU/vLLM work remain unfinished.
- GPU/vLLM package/driver/environment installation requires separate explicit
  recipes and validation; no automatic host repair is performed here.
- Build removal/space reclamation and reuse of compiled intermediates remain
  unfinished. Each accepted build snapshots a commit into a fresh directory.
- Interrupted builds cannot resume cached partial compilation through this UI;
  retry creates a new review/build. Restored metadata is not engine evidence.
- Trusted source build scripts can perform actions beyond the fixed recipe;
  this feature does not provide OS-level build isolation.

## Primary sources

- [llama.cpp build documentation](https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md)
  for CMake, parallel CPU compilation and static library builds.
- [CMake command-line manual](https://cmake.org/cmake/help/latest/manual/cmake.1.html)
  for separate source/build directories, generators and bounded parallel builds.
  Flags were checked against the actual selected commit before execution.
