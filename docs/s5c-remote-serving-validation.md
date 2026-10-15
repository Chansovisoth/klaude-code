# S5c, third slice — Owned SSH CPU serving

Date: 2026-10-14. Continues [SSH settings/diagnostics](s5c-ssh-validation.md) and
reuses [local managed serving](s5b-managed-serving-validation.md).
This slice implements reviewed remote **CPU llama.cpp** serving and an owned
loopback SSH tunnel. S5c is still partial: key enrollment, additional GPU/vLLM
installation recipes and remote GPU/vLLM serving remain unfinished. S6 is unstarted.
Existing dirty S5 work is retained; there is no commit/push or dependency/version change.

Follow-up: [reviewed existing-public-key enrollment and verified host-trust
setup](s5c-ssh-key-setup-validation.md) now implements that separate slice. The
scope, counts and evidence below describe this third slice's original validation.
Local CUDA/vLLM recipes and setup removal are now covered by their linked
follow-ups. [Remote llama.cpp GPU profiles](s5c-remote-gpu-validation.md) also extend
the CPU flow; remote vLLM/adoption remain unstarted. The historical CPU-only
rejection and counts below describe the third-slice implementation at that time.

## Working user flow

Model Manager → Servers → saved SSH server → Serve CPU model opens a private
form for Name, Remote executable, Remote GGUF path, Remote port, Tunnel port,
Context and CPU threads. The model must be a regular GGUF inside the configured
remote model directory. The executable must be an installed absolute path.
No model upload, download, package installation or model selection is automatic.

Test engine checks bounded help/flags without loading a model. Review launch
reuses those flags and verifies executable/model metadata, SSH/credential
revisions and both ports. Review initially selects Back and supports PageUp/
PageDown through long wrapped details while retaining that safe selection.
Acceptance explicitly executes the selected remote engine and loads its weights.

Both engine and tunnel bind to 127.0.0.1. The endpoint enters Added Models only
after remote listener ownership, the exact generated model ID, SSH tunnel
ownership and tunneled health all pass. Select its qualified model explicitly;
Default Chat and existing session choices are retained. Progress is bounded;
private redacted log tails are available without entering chat/model context.

During startup, Cancel loading directly requests cleanup. Active servers use a
Back-focused Stop server review. Existing global startup cancellation remains;
inside a settings panel `/` starts filtering, so the visible Cancel loading
action is the direct panel control. Accepted work survives navigation; startup
gates model work until Ready and cancellation until owned helper cleanup. Ready
servers share the existing client-owned local/remote inventory and two-server
limit, then end when that client exits.

CLI uses the existing command, with additive options:

```text
klaude model-manager serve /absolute/remote/model.gguf --ssh-server ID --executable /absolute/remote/llama-server --port 8080 --local-port 18080
```

Context/threads/name and `--yes` retain their existing meanings. A remote server
requires CPU llama.cpp; remote GPU settings, vLLM and adoption fail explicitly.
Review cancellation exits 0 without launching. Failure exits 1 and foreground
Ctrl+C exits 130 after owned cleanup. `model-manager servers` and `logs ID`
cover both local and SSH records. Existing local serve/adopt commands remain valid.

## Ownership and reliability architecture

- Extend LaunchSpec and the existing ServingJobs/helper process lifecycle;
  there is no second background scheduler or model orchestration loop. Core
  `ssh_serving` owns preflight, tunnel validation, endpoint publication and local
  records; `ssh_serving_program` is self-contained standard-library Python sent
  over the verified SSH connection. It is not installed on the remote host.
- Reuse the private SSH definitions, strict known-host/public-key/opt-in-agent
  controls, fixed quoted code and JSON stdin. User fields do not become shell
  commands. Only the explicitly requested loopback port forward is enabled;
  proxies, ambient SSH config, multiplexing and agent/X11 forwarding stay disabled.
- Preflight captures definition nonces and credential-file/socket references.
  The helper rechecks them at launch and before endpoint publication. Remote
  executable/model metadata is rechecked immediately before execution. Prepared
  flags are reused during review rather than executing help redundantly.
- Remote engines receive fixed argument arrays, CPU-only device/layer settings,
  offline Hub/Transformers flags and a minimal environment without provider keys.
  This executes a trusted installed engine; it is not an OS sandbox for malicious
  binaries or engines that deliberately escape their process group.
- The remote supervisor creates an isolated process group. It accepts only
  heartbeat bytes after its initial request, never arbitrary commands or PIDs.
  Heartbeats renew a six-second owner lease. EOF, client/helper/SSH death, missing
  heartbeats or remote termination triggers TERM/KILL of that owned group.
  Observed unrelated processes are never adopted or stopped.
- Cleanup acknowledges only after reaping the leader and bounded inspection
  finds no live owned-group members. Confirmed, Not started and Unconfirmed
  outcomes are distinct. A lost channel cannot provide a receipt; it disables
  the local endpoint and reports the bounded lease rather than claiming rollback
  or confirmed remote termination. OS-blocked processes can remain unconfirmed.
- One daemon health request per side keeps stalled HTTP headers/body reads from
  blocking heartbeat handling or cancellation. Registration still requires a
  completed successful health result, exact alias and current owned listeners.
- SSH connection timeout is three seconds; preflight has a 20-second outer/
  15-second operation bound, eight-second help bound and 512 KB help limit.
  Initial requests are at most 16 KiB; SSH events/stderr are at most 64 KiB.
  Remote startup is capped at 180 seconds (185 on the client); normal stop waits
  for a receipt, while the existing outer helper supervisor bounds forced cleanup.
  The six-second lease plus bounded TERM/KILL checks normally completes within
  eight seconds of the last heartbeat, with Unconfirmed for unverifiable outcomes.
- Private logs retain about 256 KiB, with existing 16 KiB tails, control stripping
  and credential-label redaction; updates are throttled to once per second. Raw
  SSH stderr and provider credentials are not published or added to model context.
  Endpoint disable retains the existing definition-equality guard, preserving
  user-replaced endpoints, roles, model files and history.

## Actual findings and improvements

1. **CLI preflight lost its configuration root.** Direct transport fixtures and
   the TUI worked, but the real CLI could not find the saved definition. The
   shared CLI worker request now captures config_dir; a fresh-process actual CLI
   review/cancel regression covers production import-time configuration.
2. **Immediate restart falsely reported a busy port.** The second TUI launch
   failed after an acknowledged stop. A controlled encrypted start/stop/review
   reproduced TCP state 06 (TIME_WAIT): plain bind returned errno 98, while
   SO_REUSEADDR bind succeeded. Shared local/tunnel and remote port probes now
   match server bind semantics. Live listening ports still fail; immediate
   same-port restart is covered with real SSH. A probe is not a reservation.
3. **Startup cancellation lacked a direct panel control.** `/cancel` inside
   settings was a search filter; the completed first server was stoppable, but
   loading required a stop review. Shared local/remote detail pages now offer
   Cancel loading while startup is active and retain Stop review once ready.
4. **Long review metadata could not be paged independently.** Review pages now
   use the shared scrolling behavior without changing initially selected Back.
   Real captures and regressions cover wrapped 40/120-column details.

Several walkthrough retries also corrected driver behavior: waiting for the
asynchronous second review before selecting Launch, using the visible panel
cancel action, and returning through Back/Close before issuing `/exit`. Failed
attempts are not claimed as complete successful sessions.

## Actual validation

### Installed engine/model through the real CLI

The real `klaude model-manager serve` used the prior verified CPU executable
from committed llama.cpp source `b7ad48ebda2287c778fd826606d7b3b3570f60ab`, unchanged
qwen2.5-coder:3b GGUF weights, context 512 and two CPU threads. A temporary real
loopback sshd provided encrypted transport with private QA keys and verified
known hosts. Chat Completions over the owned tunnel returned **OK**. Ctrl+C exited
**130**, the endpoint was disabled and remote cleanup was **confirmed**.

The final build-independent run finished in **8.11 seconds**. All **22 original
Ollama names/digests**, model/executable size and modification time, QA key/known-
hosts bytes and the workspace user file were retained. Evidence:
`/tmp/klaude-remote-native-414ptcum/result.json`, `serve-cli.log` and
`/tmp/klaude-remote-native-final.log`. This certifies real CPU inference over
loopback SSH, not a physical LAN host, GPU, vLLM or a full coding benchmark.

### Real TUI and failure boundaries

Bare Klaude used **TEST KLAUDE FEATURES REMOTE SERVING** with an isolated workspace
containing an existing user file, real OpenSSH and a protocol fixture engine. Seven scenarios
cover server-scoped private fields at 40/70/120 columns; engine test; Back-focused
cancelled launch review and scrolling; accepted launch/progress/owned tunnel;
bounded redacted logs and cancelled stop review; confirmed stop and retained
inventory; then immediate reuse with visible cancellation during slow loading.
Final evidence: `.klaude/data/s2-models-rxudzu9n/remote-result.json`, its text/SVG
captures and `/tmp/klaude-remote-tui-complete.log`. All seven steps passed and
the interactive client exited 0; all retained jobs were Stopped with Confirmed
remote cleanup. Existing connection definitions, workspace user file, remote
model/executable and QA key/known-hosts bytes were preserved.

The focused suite passed **60 tests**: 15 remote tests plus existing SSH and
local serving regressions. Coverage includes actual tunnel/model identity,
acknowledged stop, busy local/remote ports, changed binary/model/definition,
CPU-only profile rejection, real CLI review cancellation, safe scrolling, immediate
restart, missing heartbeats with an open SSH connection, local helper death,
lost SSH channels, startup cancellation and a descendant ignoring SIGTERM.
Stalled-health control is tested separately without adding a stuck live server.

### Final local gates

- `UV_CACHE_DIR=/tmp/klaude-s5-uv-cache make check`: **2,971 passed, 19 skipped**,
  in **211.88 seconds**; Ruff passed and production mypy passed **127 source
  files**. Evidence: `/tmp/klaude-remote-release-check-complete.log`.
- The earlier full-suite entry point exposed a fixture import-path issue not
  present under the focused Python-module invocation. Shared fixtures now use
  relative imports within the existing unit-test package. Failed collection
  attempts are not counted as successful full-suite runs.
- Sequential `make package-smoke` passed all **five wheel** builds, isolated
  installation/imports and installed `klaude --help`. Evidence:
  `/tmp/klaude-remote-release-package.log`.
- `git diff --check` passed. No commit, push, dependency metadata, lock or version
  change was made. This pass uses local Python 3.12.3; Python 3.11/3.13 CI and
  physical LAN-host validation were not run.

## Remaining scope

- Physical LAN-host behavior and remote GPU/vLLM serving are not certified.
  Remote CPU support intentionally requires the tested device/serving flags.
- No remote adoption, persistent daemon, automatic reconnect or cross-client
  takeover is provided. A lost connection ends the owner lease. Restart requires
  a new explicit review; retained receipts do not authorize remote mutation.
- Key generation/enrollment, host-key trust setup, jump hosts, aliases,
  certificates and password authentication remain separate work.
- Additional GPU/vLLM installation recipes and local build deletion/reclamation
  remain unfinished. S6 is unstarted.
- Shell startup on the selected remote account and deliberately detached engine
  processes remain outside Klaude's isolation guarantee. Its requested engine
  environment and owned group are bounded, but this is not a host sandbox.

## Primary sources

- [OpenSSH client manual](https://man.openbsd.org/ssh.1) for explicit loopback
  forwarding and configured command execution.
- [OpenSSH configuration manual](https://man.openbsd.org/ssh_config.5) for strict
  host trust and forward-failure handling.
- [Python subprocess documentation](https://docs.python.org/3/library/subprocess.html)
  for process sessions, pipes, termination and reaping. Installed OpenSSH/Linux
  behavior was also tested directly; source metadata alone was not treated as proof.
