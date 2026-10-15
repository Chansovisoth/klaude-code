# S5c: reviewed adoption of an existing remote model server

Implemented and exercised locally on 2026-10-14. This completes the supported
Linux S5c delivery scope; S6 has not started. Physical LAN hosts, other platforms
and additional installation recipes remain uncertified extensions.

## User flow

- Model Manager → Servers → a saved SSH server → **Adopt existing server**.
- Enter the installed remote engine executable, existing server PID, exact
  advertised model ID, remote loopback port and a free local tunnel port.
- **Inspect server** checks installed-engine flags and process identity without
  taking ownership, loading weights, changing engine settings or attaching logs.
- **Review adoption** verifies the exact model and listening process. Back starts
  focused; PageUp/PageDown scroll the whole review at 40, 70 and 120 columns.
- **Adopt server** verifies the tunnel and endpoint, then acknowledges takeover.
  Ready appears only after the remote supervisor confirms ownership.
- The original process group stops on reviewed Stop, client exit or owner lease
  loss. Model files, defaults, roles, historical records and the original log
  destination remain independent. Selecting the registered model is explicit.

The canonical CLI also accepts the SSH options on the existing adoption command:

```bash
klaude model-manager adopt PID MODEL_ID --engine llama_cpp --executable /remote/bin/llama-server --ssh-server ID --port 8080 --local-port 18080
```

Use `--engine vllm` for an installed Python-console vLLM server. The review
defaults to No; `--yes` explicitly accepts takeover for scripted use. The command
stays foreground. Ctrl+C closes the owned request, waits for cleanup and exits
130. Declining review exits 0 and leaves the external server running.

## Ownership and implementation

This extends the existing fixed SSH program, ServingJobs and owned-worker flow;
there is no installer, arbitrary SSH command input or separate scheduler.

1. Process observation captures Linux PID start time, process group, session,
   actual executable and a hash of bounded argv. The process must be live, owned
   by the SSH account, and lead its own isolated group/session. Native executable
   identity or an exact Python console-script interpreter/path must match the
   tested engine. A string elsewhere in argv is insufficient.
2. Preparation checks that the listener belongs to that group and is bound to
   remote loopback, and that `/health` and `/v1/models` expose the exact requested
   model ID. HTTP is bounded, with no redirects or ambient proxies. Adoption
   retains existing engine settings and does not claim a context size, GPU device
   allocation, model fit or environment profile from unused launch defaults.
3. Acceptance rechecks executable/process identity and endpoint ownership. The
   remote supervisor first sends readiness **without ownership**. The client
   verifies its tunnel, current SSH definition/credential revisions and model,
   and publishes a new endpoint before sending the fixed takeover acknowledgement.
4. A Linux abstract Unix socket prevents competing adoption owners for the same
   account/PID/start time. It creates no remote lock file. The remote supervisor
   rechecks the process/listener/model before acknowledging ownership. Failed
   readiness, registry publication, duplicate ownership or channel closure before
   acknowledgement leaves the original process running.
5. A missing takeover acknowledgement has a ten-second client deadline. The
   six-second renewable owner lease and bounded remote/helper/client shutdown
   windows remain shared with remote serving. Fixed line framing handles split
   acknowledgement bytes; the channel accepts no runtime commands or replacement
   PIDs. Post-takeover channel loss stops the adopted group when its lease ends.
6. Shutdown signals only the witnessed group. Start-time/executable/argv identity
   checks reject stale or reused identities. Previously witnessed descendants
   anchor escalation if the leader exits on TERM, allowing an ignoring child to
   be reaped without targeting a new process group. Cleanup is Confirmed only
   after no live group members remain; inaccessible/changed identities remain
   Unconfirmed. Lost receipts never become inferred confirmations.
7. The local client explicitly excludes SSH adoption from local adopted-process
   cleanup. A remote PID can never be interpreted as a PID on the client machine.
   Endpoint disable still requires the unchanged manager-created definition.

Installed-engine flag evidence is reused between Inspect and Review when its
revision matches. No CUDA subprocess, GPU reselection or safetensors directory
walk is needed to adopt an already-running vLLM server. Existing bounded launch
preflights and CPU/GPU serving behavior remain intact.

Implementation:

- Core `ssh_serving_program.py`: observed identity, two-stage takeover, exclusive
  ownership, renewable lease and witnessed-group termination.
- Core `ssh_serving.py`: bounded evidence decoding, revision checks, exact existing
  model identity, tunnel verification and ownership acknowledgement.
- CLI `serving_panel.py`, `ssh_panel.py`, `model_manager_commands.py` and `main.py`:
  private typed fields, safe reviews, SSH adoption options and synchronized help.
- CLI `serving_jobs.py`: keep remote PIDs out of the local cleanup path.
- `tests/unit/test_ssh_adoption.py`: real loopback SSH and controlled external
  process regressions, alongside existing local/remote engine coverage.

## Actual CLI: upstream vLLM

Private receipt: `/tmp/klaude-remote-adoption-native-6rebzjfg/result.json`.
Driver/output: `/tmp/klaude_s5c_remote_adoption_native.py` and
`/tmp/klaude-adoption-native.log`; exact review and accepted command output are
retained under the private receipt directory.

- GTX 1650, 4 GiB; upstream vLLM 0.31.0/Torch 2.13.0/CUDA 13.0 from the already
  retained isolated QA installation. No new install or model download.
- SmolLM2-135M-Instruct, Hub commit
  `12fd25f77366fa6b3b4b768ec3050bf629380bac`.
- A new external server was launched outside Klaude's ownership with context
  512, half precision, eager execution and one GPU/sequence. The original model
  ID was `qa-existing/model`, deliberately containing a slash.
- Actual `klaude model-manager adopt` over temporary pinned loopback OpenSSH:
  first decline the review and verify the original process/store are unchanged;
  then accept the visible review and generate **Hello!** through the tunnel.
- External engine readiness: **31.57 seconds**. Accepted CLI invocation through
  owned readiness: **13.61 seconds**, including installed-engine help/imports.
- Ctrl+C: exit **130**, final Stopped and **Confirmed** remote cleanup; the
  manager-created endpoint was disabled. Original engine logs stayed at their
  original destination; no managed engine log was attached.
- All **22 original Ollama names/digests**, executable/model/key metadata and
  dirty workspace content were retained. Default/session models were not selected
  or changed automatically.

This is backend/lifecycle evidence, not a claim about the small model's coding
ability or the earlier CSV benchmark.

## Actual terminal: native CUDA llama.cpp

Final receipt:
`.klaude/data/s2-models-1gf0s40q/adoption-real-tui-result.json`.
Driver/output: `/tmp/klaude_s5c_remote_adoption_real_tui.py` and
`/tmp/klaude-adoption-real-tui-final.log`; text/SVG captures and raw terminal
output are retained beside the receipt.

- Bare `klaude`, session **TEST KLAUDE FEATURES REMOTE ADOPTION**; temporary dirty
  workspace and private configuration. Chat's unrelated model catalog used a
  metadata fixture; no chat generation was requested.
- A new isolated native CUDA llama.cpp process at retained commit
  `b7ad48ebda2287c778fd826606d7b3b3570f60ab`, existing qwen2.5-coder:3b GGUF,
  context 512, GPU layers 99/CUDA0. Actual pinned loopback OpenSSH.
- Private PID/model/tunnel fields, nonmutating inspection, Back-focused review,
  cancellation retaining the external process, accepted takeover, actual GPU
  HTTP generation **OK**, and reviewed Stop with confirmed cleanup all passed.
- Review/paging were exercised at **40, 70 and 120 columns**. Rendered wide/narrow
  captures were visually inspected: aligned wide values, complete stacked narrow
  labels/values, long paths and effects reachable by paging, fixed header/footer.
  Existing narrow chat banner/status cropping is outside this serving slice.
- Terminal exit **0**; public model turns **0**. All 22 actual Ollama digests,
  initial connections/roles, original weights/executable/SSH keys and dirty
  workspace content were retained. Adopted server logs were not attached.

The first terminal driver run stopped at a case-sensitive assertion expecting
`Original log destination`; the UI correctly showed `original log destination`.
Its incomplete receipt is retained under `.klaude/data/s2-models-8grc1x9y` and
`/tmp/klaude-adoption-real-tui.log`. The corrected driver completed the full flow;
this was a QA expectation error, not an engine or product failure.

## Automated validation

- Initial focused run: **48 passed, 2 failed** in 71.24 seconds. The competing
  owner test reused the first owner's occupied tunnel port; the paging test
  started at its already-focused bottom. Corrected fixtures retained the intended
  duplicate-ownership and paging checks. Rerun: **16 passed** in 26.40 seconds.
- Expanded local/remote CPU/GPU/vLLM/adoption regressions: **107 passed** in
  **196.52 seconds**, `/tmp/klaude-adoption-all-serving.log`.
- Cases include failed path/PID/model/listener checks, wrong account, stale start
  time/definition, registry failure before takeover, EOF before/after takeover,
  fragmented acknowledgement, competing owners, original logs/defaults, safe
  local-vs-remote cleanup, helper death, ignoring descendants and evidence bounds.
- Complete locked `make check`: **3,125 passed, 19 skipped** in **401.75 seconds**;
  Ruff clean, production mypy clean across **132 source files**.
  `/tmp/klaude-adoption-full-check.log`. Local Python 3.12 only; no new CI claim
  for Python 3.11/3.13.
- Separate `make package-smoke`, started after the complete check gate: **passed**
  for all **five wheels**, isolated installation/public imports and installed
  `klaude --help`. `/tmp/klaude-adoption-package.log`.
- `git diff --check` passed. All **45 unrelated pre-existing changed/untracked
  files** retained exact contents against this turn's baseline. This slice edits
  11 existing files and adds the adoption regression file and this record. No
  dependency/lock/version change, commit or push was performed.

## Limits and next phase

- Linux `/proc`, same-account isolated sessions and loopback listeners are required.
  Service-managed/shared process groups, public-bound listeners, arbitrary shell
  wrappers, other operating systems and PIDs inferred from diagnostics fail closed.
- An exact advertised model ID is required. Klaude does not rewrite the adopted
  server's arguments, auth policy, resources or model identity. Protected endpoints
  lacking the existing unauthenticated loopback health/catalog contract cannot be
  adopted by this slice.
- An already-trusted remote account/engine is an explicit prerequisite. Observed
  metadata is identity evidence, not binary/weight security attestation. Restricted
  process visibility or changed identity may prevent confirmed termination.
- On lost transport the bounded lease performs remote cleanup, but the local UI
  retains Unconfirmed without a receipt. Explicit takeover means network/client
  loss ends the formerly external server; this effect is visible before approval.
- Actual evidence uses loopback OpenSSH on this machine. No physical LAN-host,
  other-GPU/platform or coding-quality certification is implied.
- S5c's delivered CPU/CUDA/build/offline-install/SSH/remote-adoption scope is now
  implemented locally. The next planned phase is **S6a Vision**, through Library
  → Media, with capability evidence and explicit model/role choices. S6 remains
  unstarted; further installers/platforms require a separately scoped extension.
