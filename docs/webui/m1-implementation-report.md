# M1 shared application bridge implementation report

**Date:** 2026-10-17  
**Status:** **M1 complete for the scoped in-process chat slice.** Headless, line and TUI clients now share Agent construction, turn admission/persistence and execution seams. One deterministic read → Ask-policy write fixture passes through all three, for both approval and denial, with headless resume. Terminal presentation and many domain controllers remain CLI-owned by design. M2 remains a separate authorization gate.

## Scope delivered

- Added the sixth workspace distribution, `klaude-application`, in `packages/application`. `composition.py` constructs the existing `Agent` from injected runtime, tools, gate and model settings. `open_local_session` creates a local-tool headless session without console initialization, model catalog access or Git branch activation; writes are disabled until explicit `activate_workspace()` runs the existing `Workspace.ensure_work_branch` guard.
- `runner.py` is a small adapter over the **same synchronous `Agent.run` generator**. It closes the generator when a consumer exits. It does not create another agent loop. Both CLI `_render` and TUI `_run_turn` now use it; `_build_agent` uses `compose_agent`. Existing terminal commands, routing/tool registration and display code remain in `klaude_cli.main` for incremental migration.
- `lifecycle.py` provides `SessionTurn` for lease claim, accepted-user persistence, assistant/private-continuation persistence and release. Headless, line and TUI use it; terminal lease renewal and UI presentation stay with their existing owners.
- `contracts.py` defines bounded public event, turn receipt, approval and user-input records. `service.py` owns one turn worker and one bounded 128-event channel per turn. The async consumer uses nonblocking queue reads, so synchronous model/tool work and a slow producer cannot block the event loop. Cancellation wakes approval waiters, calls the Agent transport-cancellation hook and joins the worker before resource shutdown. A dropped event consumer cancels its turn. Duplicate request IDs return the original in-process handle only when the session, text and scope match; a changed payload is rejected.
- `interactions.py` brokers exact-ID allow-once/deny decisions and structured user input with deadlines. The core permission gate receives the execution ID and validated arguments privately. Denial, expiry and cancellation map to deny. A new execution observer emits `tool.started` immediately before invocation, after argument validation, preflight and permission checks; existing `tool_start` remains a **request**. Host-side preflight tools follow the same distinction. `tool.finished.executed` reflects the existing Agent execution metadata. Public events project only allowlisted text/tool/ID/status fields, never tool arguments/results or private model continuation.
- The headless service persists accepted user and assistant turns in the existing `Memory` store, captures session runtime on acceptance, and restores a session only when the injected explicit model, mode, effort and captured connection/credential revisions match. It uses existing session leases within this process; durable deduplication, fencing and crash recovery remain M2 work.
- Updated workspace dependency/lock metadata, six-wheel release/package checks, CI and local mypy paths, and `AGENTS.md`. The feature inventory has a dated M1 source update without relabeling planned WebUI work as implemented.

## Files changed for this slice

| Area | Files |
| --- | --- |
| Application package | `packages/application/pyproject.toml`; `src/klaude_application/{__init__,composition,contracts,interactions,lifecycle,runner,service}.py` |
| Existing execution/terminal seams | `packages/core/src/klaude_core/{agent,permissions}.py`; `apps/cli/src/klaude_cli/main.py` |
| Workspace/distribution checks | `pyproject.toml`, `uv.lock`, `apps/cli/pyproject.toml`, `Makefile`, `.github/workflows/ci.yml`, `scripts/{package_smoke,verify_release_artifacts}.py`, `AGENTS.md` |
| Evidence | `tests/unit/test_application_bridge.py`, two parity fixtures in `tests/unit/test_cli_commands.py`, `docs/webui-feature-inventory.md`, this report |

All other pre-existing dirty files retained their baseline bytes. No stash, reset, commit, push, HTTP server or frontend work was done.

## Validation performed

| Check | Result |
| --- | --- |
| New deterministic bridge tests | **14 passed**: headless construction, admission-failure lease cleanup, in-process deduplication, public stream and private-canary projection, exact approval allow/deny/expiry, structured input, cancellation during stream/approval/full channel, exception propagation, resume/runtime mismatch, dirty-tree write rejection, and headless/line answer parity. |
| Full `test_cli_commands.py` | **873 passed, 1 skipped** with local loopback fixtures available. The added two-case fixture drives the same read → Ask-policy write workflow through headless, line and TUI; allow-once writes, denial does not, and headless resume retains the exact session/model. Existing permission/rendering paths remain covered. |
| Session/workspace/capability regression group | **367 passed** with local loopback fixtures available (`test_memory`, `test_session_runtime`, `test_session_io`, `test_session_actions`, `test_capability_routing`, `test_reliability_repair`, `test_workspace_execution`, `test_compound_tasks`, `test_tool_discovery`, transcript replays). The first sandboxed run had 14 fixture setup errors because AF_INET socket creation was denied; the loopback rerun passed. |
| Bridge, release artifact, execution and local-tool group | **59 passed**. |
| Ruff and production mypy | `ruff check .` passed; `mypy packages/application/src packages/core/src packages/knowledge/src packages/tools_local/src packages/web/src apps/cli/src` passed (160 source files). |
| Lock/install/packaging | `uv lock --check --offline` passed (119 packages). Frozen base install passed. The isolated package smoke built and installed **six wheels**, imported each distribution and ran installed `klaude --help` successfully. Its first sandboxed attempts lacked cached build/dependency wheels; the network-enabled rerun passed. Optional cloud SDKs removed by the base-only sync were restored with frozen `--extra cloud`. |
| Worktree integrity | `git diff --check` passed. A checksum comparison against the pre-edit dirty-file snapshot found no missing files and only the intended pre-existing edits to `AGENTS.md`, `main.py`, `agent.py` and `test_cli_commands.py`; new and previously clean bridge/package files are listed above. |

These are fixture and package checks, **not** a full repository unit-suite run or live Ollama/cloud-model validation. The earlier broad CLI run was interrupted while waiting in fixture-heavy tests; the complete loopback rerun above is the result to use. No real external service, multi-process race or browser request was exercised.

## Compatibility and remaining M1 work

`Agent.run`, its tool registry/capability routing, the terminal permission callback, model runtimes, local Workspace jail and dirty-tree guard, and Memory format remain the existing authorities. Line and TUI retain their original rendering, session commands, prompt handling, UI-specific approval presentation and lease renewal. The shared `SessionTurn` now owns the accepted turn's lease and transcript writes in all three paths. The three-client fixture covers real local read/write tools, approval/denial and exact headless resume; focused cancellation and dirty-tree tests remain in the bridge suite. Model Manager, Knowledge, MCP, Skills, Media and Research controllers remain later work.

The headless broker currently returns only tool name and execution identity for approval display; it retains validated arguments privately, but a future interactive UI needs a reviewed, safely redacted action summary before approving mutations. The in-process request map is unbounded and valid only for this application's lifetime. Event queues have one consumer; no replay or reconnect contract exists. A cancelled provider must honor its cancellation hook for prompt shutdown. The application does not yet renew long-running leases or apply live endpoint/policy revision checks at an approval boundary; therefore it is **not a browser mutation boundary**.

## M2 boundary

M2 must add durable request admission and deduplication, multi-process fencing, lease renewal/loss handling, replayable public event cursors, atomic terminal receipts, cross-client control/decision ownership, safe recovery after process loss, and revision checks for workspace/runtime/policy changes. Those guarantees were not implemented or claimed here. Do not expose HTTP/browser-driven writes until the M2 coordination and security gates pass.
