# S1: model connection foundation

Date: 2026-10-13. Parent checkpoint: `0db42b4`.

S1 implementation, live connection scenarios and final automated validation are
complete. S2 settings forms and AI Defaults were unstarted at this checkpoint.
The subsequent [S2 connection UI pass](s2-model-settings-validation.md) records
the first settings slice and its remaining work.

## Changes

- Version 1 connection registry: stable IDs, adapter/source, normalized URL,
  enabled state and private environment references. Writes reuse the existing
  cross-client lock and atomic owner-only settings writer. Invalid versions,
  credential-bearing URLs, symlinks, special files and oversized input fail.
- Idempotent migration snapshots existing Ollama/native choices and startup/role
  selection without replacing configuration, embedding settings, preferences or
  saved sessions. Existing native aliases bind to stable default connections;
  qualified references use `backend@connection_id/model_id`.
- Model identity, request budgets, catalogs and pending activation retain endpoint
  identity. Catalog generations are adapter/endpoint scoped; publication rejects
  changed definitions or credential revisions. Native refresh cannot erase another
  endpoint's records. A byte bound replaces silent aggregate catalog slicing.
- Fixed-operation catalog checks use the existing owned process worker and private
  pipe. Ctrl+C cancels; checks have bounded network/response/model/outer deadlines,
  no redirects or ambient proxies, and precise sanitized failure categories.
  No model is loaded by Test. Native SDK errors cannot masquerade as a successful
  empty catalog. Listing models leaves tool and context evidence unknown.
- An HTTPX Chat Completions runtime adds streaming text, complete tool assembly,
  exact reported usage, bounded malformed-call repair and explicit output-limit/
  incomplete-stream errors. It strips provider-private reasoning from generic
  requests and requires completed calls before execution. Native adapters remain
  separate. Native and compatible HTTP clients share cancellation before headers
  and independent child transports.
- Compatible servers use bounded configured conversation budgets and one automatic
  worker, including remote servers. This does not allocate server context or change
  GPU, threads, reasoning, templates or tool parsers. Explicit worker overrides remain.
- Real testing found a cross-provider HTTP 400: retained compatible tool arguments
  were JSON strings, while native Ollama requires objects. The native adapter now
  translates arguments on each request without mutating the shared conversation.

The core implementation is in `model_connections.py`, `model_discovery.py`,
`compatible_runtime.py`, and `http_model_transport.py`, with model identity/cache
and native-argument translation in existing runtime modules. A focused CLI module
owns `model-connections list/add/test`; `main.py` wires selection/startup and the
existing TUI ownership/continuity machinery. No new settings page was added.

## Real CLI and TUI evidence

Test configuration/data: private, gitignored
`.klaude/data/s1-connections-_pwfvqoa/`. The final smoke workspace was a separate
temporary directory, without the repository's large inherited agent guidance.
The repository's user configuration and unrelated files were untouched.

Server: **Ollama 0.33.3**. Model: **`gemma4:e2b`**. Observed final allocation:
8192 context, 1,708,035,930 bytes of GPU memory. This allocation observation applies
to this run, not arbitrary compatible servers.

| Scenario | Evidence/outcome |
| --- | --- |
| Register and Test a second endpoint | Real `model-connections add compatible-local --adapter openai_compatible --url http://127.0.0.1:11434/v1`; Test returned 22 listed models, with tool capability explicitly unknown. |
| Native one-shot with tools | `ask --model ollama@default-ollama/gemma4:e2b` read `endpoint-proof.txt` and returned its verification code `cobalt-731`; exit 0, 88.72 seconds. |
| Compatible one-shot with tools | The same task with `openai_compatible@compatible-local/gemma4:e2b` performed `read_file` and returned `cobalt-731`; exit 0, 40.39 seconds. |
| Interactive streaming/tool execution | Real Prompt Toolkit TUI, session renamed **TEST KLAUDE FEATURES S1**, read the same file with an observed completed tool milestone and final answer. |
| Compatible to native switch after tools | Before repair: native HTTP 400. After repair: repeated the file read in a new process, switched to native without clearing the conversation, and received `cobalt-731`. |
| Change model during work and cancel | While native generation was active, selected the compatible endpoint, then Ctrl+C. The saved session records the interrupted native response and the subsequent compatible session update. A follow-up returned `cobalt-731`. |
| Restart and resume | Exited cleanly, launched bare `klaude` with no model override, then `/resume daea65e274a74c788fa57eb53268293a`. The remembered reference stayed `openai_compatible@compatible-local/gemma4:e2b`; the resumed answer was `cobalt-731`, followed by clean exit 0. |
| Output budget exhaustion | Asking for 1500 numbers under a 512-token budget produced a visible incomplete-response error and retained partial output. The TUI remained usable. The adapter now names output-limit exhaustion explicitly. |

Session ID: `daea65e274a74c788fa57eb53268293a`. The saved public conversation
and audit/interruption records support continuity and lifecycle checks; audit
metadata is not replayable tool evidence. The repeated live read re-established
the file evidence before the repaired provider-switch test.

The two connections use **different API adapters/addresses on the same actual
Ollama daemon**. This validates the native-plus-compatible gate, not two physical
servers or live llama.cpp/vLLM certification. Their same-named model identities
remain distinct. The timings include different cold/warm state and are not a
performance comparison between adapters.

Earlier attempts were interrupted by the environment restart; their temporary
logs disappeared. They are not counted as successful validation. An early test
under this repository inherited its lengthy `AGENTS.md`; the final isolated
workspace avoided that extra input while keeping the task identical.

## Automated validation

Regression coverage includes:

- Duplicate model IDs across endpoints, native alias binding, independent refresh
  and generation invalidation, stale definitions/credentials and large merged catalogs.
- Private/idempotent migration, untouched preferences, unsafe registry inputs and
  saved key removal overriding stale process environment.
- Fragmented SSE tool calls, private-state filtering, usage, malformed arguments
  through the actual Agent repair loop, missing completion and output-limit stops.
- Actual loopback cancellation while awaiting headers, both assembled and streamed
  requests, plus existing native cancellation/worker ownership tests.
- Frozen pending endpoint selection, current runtime/history retention, configured
  context budgets, conservative workers and changed-default catalog provenance.
- Native request translation after compatible tools, in both native request paths.

The initial full gate passed **2492 tests, 19 skipped**, Ruff, and mypy over 88
production files. After the live provider-switch repair and additional regressions,
the final-source gates passed:

| Gate | Final result |
| --- | --- |
| `make check` | Exit 0; **2505 passed, 19 skipped**, 126.56 seconds for pytest, 130.12 seconds overall. |
| Ruff | All checks passed. |
| Production mypy | No issues in 88 source files. |
| `make package-smoke` | Exit 0; five freshly built wheels installed together; all public imports and installed `klaude --help` passed, 7.73 seconds. |
| `git diff --check` | Passed. |

Persistent local evidence: `make-check-final.log`, `make-check-final-result.json`,
`package-final.log`, `package-final-result.json`, native/compatible ask logs/results,
and the test session database under the test data root above. The temporary build
cache had been cleared at restart; the first offline packaging attempt could not
find hatchling. Restoring build dependencies and rerunning fresh packaging passed.

Validation runs use Python **3.12.3** locally. This work has not been committed or
pushed; new Python 3.11/3.13 CI results are not claimed. The S0 checkpoint's CI is
separate evidence for its earlier source snapshot.

## Remaining boundaries and next phase

- S2 owns Add/Added Models forms, per-endpoint GUI inventories/visibility,
  enable/delete workflows and AI Defaults consumers. S1 provides registration,
  testing and explicit selection through the real CLI/session flow.
- Unknown compatible servers may require engine-side tool templates/parsers;
  catalog success does not establish those capabilities. Official references:
  [Ollama compatibility](https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx),
  [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md),
  [vLLM tool calling](https://docs.vllm.ai/en/latest/features/tool_calling/).
- The compatible adapter intentionally forwards portable temperature/output
  controls. Server-specific allocation and reasoning controls need declared
  capability/configuration support; no vendor-specific options are guessed.
- Native paid cloud calls, actual llama.cpp/vLLM engines and a second physical
  server were not exercised. Their protocol and preserved native adapters have
  automated coverage, not live certification.
- This connection work does not resolve or re-score the separate complex CSV
  benchmark and small-model orchestration evaluation.

Continue with S2 after reviewing/checkpointing S1. No release/tag/package version
was changed, and nothing was committed, pushed or published during this pass.
