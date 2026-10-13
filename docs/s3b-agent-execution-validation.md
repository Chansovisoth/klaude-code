# S3b Agent Tools execution validation

Date: 2026-10-13. Python 3.12.3. Worktree based on
`0db42b4b60ce955f9dd4e424098210b66da08bd6`; earlier S1–S3a changes were
already present and deliberately dirty. This is S3b's execution slice.
Registry-derived tool groups and the wider Settings migration remain next.
No commit, push, release, dependency, version or machine-service change was made.

## Delivered behavior

- `/settings tools`, `/settings agent tools` and `/settings agent` open a typed
  Agent Tools home with Execution, Existing tool controls and Activity Updates.
  Runtime keeps device, threads, context and calibration, and links to Execution.
  Back/Escape from Existing tool controls returns to Agent Tools.
- Execution has 12/20/40 step presets and custom 1–64, finite Auto tool calls
  (`max(4, steps × 2)`) or custom 1–256, and Auto/1–4 subagent workers.
  Compatible endpoints use one Auto worker even when remote; native cloud uses
  two. Advanced has **No total-token cap** or custom 1–2,000,000, a live
  provider-reported input/output count and an explicit count of requests with
  unreported usage. Zero legacy values keep their Auto/no-cap meanings.
- Limits apply before the first model request in both chat and `klaude ask`.
  They stay outside Ollama/compatible inference options. A running turn uses
  the step and tool budget captured at its start. Individual and Execution
  resets preserve unrelated device/context, tool and permission settings;
  Runtime reset preserves execution controls. Saves use the existing ordered,
  atomic preference writer with latest-revision metadata and cross-client
  merges. Failed saves retain live intent and report unconfirmed persistence.
- The 80-column Execution page shows the Back action without scrolling after
  removing redundant explanatory rows. Its fixed breadcrumb/footer, aligned
  values, muted descriptions and scoped reset were inspected visually.

## Problems found in real use

| Observation | Cause | Change |
| --- | --- | --- |
| A transient custom number reappeared as a chat draft on leaving Settings and could be submitted to the model. | Reopening a panel from a suspended input editor could capture the editor's number as the panel's chat draft. | Clear valid/cancelled numeric editor input before reopening the panel; regress the unset-draft path. |
| A compatible provider received one tool result for a two-call response when the call limit stopped after the first. | The agent loop broke out of the batch at the governor boundary, leaving an assistant tool-call ID without its matching result. | Return a skipped result for every remaining ID without invoking or charging a tool; retain complete provider protocol pairs. |
| Two skipped reads at the token cap were treated as repeated tool failures, and a required-file recovery made one futile extra model request. | Budget skips entered ordinary failure-retirement and retrieval-retry paths. | Exclude governor skips from tool retirement; fail the unmet read with the actual limit reason before another model request. |
| An active settings change could change text and iteration count used at the end of an earlier turn. | The loop reread `agent.max_steps` after its governor had already captured the initial budget. | Use the governor's immutable step ceiling for the running loop and end-of-turn messages. |

## Real CLI and terminal evidence

The isolated PTY walkthrough used bare `klaude` and a session named
**TEST KLAUDE FEATURES AGENT EXECUTION**. It exercised custom range errors,
scoped resets, Back/Escape, a deliberately corrupt preferences file, recovery
on the next save, restart, live reported usage, chat, and `klaude ask`.
The saved [result and protocol records](../.klaude/data/s2-models-8fozy64x/execution-result.json)
show two clean TUI exits, two model requests per chat/ask turn and matched
results for both provider tool-call IDs. The model was a local Chat Completions
protocol fixture that requested two `read_file` calls against a real temporary
workspace. At a one-call limit, exactly one read ran and the second result was
explicitly skipped. The TUI showed 140 provider-reported tokens after two
70-token responses. The one-shot call-limit run exited 0 in about 1.5 seconds.

At a 60-token total budget, the first 70-token response crossed the cap at a
safe boundary; both reads were skipped and paired. The requested read remained
unfulfilled, so [the one-shot output](../.klaude/data/s2-models-8fozy64x/ask-tokens.log)
reported `token budget reached` and exited 1 in about 1.5 seconds. It issued
no impossible third model request. A limit remains advisory per request when
provider usage is late or missing; a tool-free finalization may add usage.

Earlier in the live run, the same token-cap case made an unnecessary third
model request and blamed the model for failing to perform the read. The
call-limit case failed the strict compatible-protocol fixture because only one
tool result was sent. The second run completed the call-limit scenario and
failed the token-cap scenario for the correct reason. Ordinary successful turns
did not gain extra model requests. The fixture establishes agent orchestration
and provider protocol behavior, not the coding ability of a small local model.
No paid cloud endpoint was called.

## Automated validation and remaining scope

Focused tests cover bounds/legacy values, Auto policies, editor isolation,
field/page/Runtime resets, live intent on failed saves, cross-client merges,
stale acknowledgements, captured turns, missing usage, provider tool-result
pairs, and no futile retry at the token cap. Final `make check` completed with
**2,731 passed, 19 skipped** in 145 seconds, followed by Ruff and production
mypy (102 source files) without errors. Five-wheel `make package-smoke` passed
package imports and installed `klaude --help`. The logs are in
`/tmp/klaude-s3b-complete-check.log` and
`/tmp/klaude-s3b-complete-package.log`. The 62-path initial dirty-worktree
hash inventory had no unrelated changes or missing files at the final check;
`git diff --check` passed. All checks used isolated temporary data/config
directories. No cloud API or native local model generation was certified.

This execution slice is followed by the completed
[registry groups and navigation evaluation](s3b-agent-tools-validation.md),
which adds mixed-state switches, MCP/Skills links and Settings regrouping.
The common terminal chrome still crowds 40-column displays; this slice only
improves the 80-column Execution page. The live fixture does not certify a
native Ollama generation, paid cloud endpoint or actual multi-worker
delegation. Existing read-only delegation and permission boundaries remain
covered by the automated suite.
