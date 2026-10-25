# Agent activity status

The WebUI and TUI use one deterministic activity vocabulary over the existing
execution events. Activities describe an operation in progress; they do not
assert that an edit, image, file or test succeeded. Turn lifecycle remains
authoritative for successful completion, failure, cancellation and interruption.

## Event mapping

| Label | Confirming event or operation |
| --- | --- |
| Writing code | An executing `write_file` targeting a recognized source extension; native workspace metadata distinguishes an existing target. |
| Editing | Executing `edit_file`, native `write_file` over an existing target, or a recognized formatter/fix command. |
| Applying changes | Executing `apply_patch` or a single `git apply` command without `--check`. |
| Generating images | Executing known image-generation/edit operations; existing TUI image job activity. |
| Creating files | Executing `write_file` for other artifacts. |
| Analyzing data | An explicitly registered `analyze_data` operation; arbitrary Python scripts do not qualify. |
| Running tests | Executing a known test operation or recognized single pytest/unittest/Jest/Vitest/npm test/cargo test/go test/make test command. |
| Validating | Executing a known validation operation or recognized lint, type-check, compilation, check-only or HTTP probe command. |
| Waiting | Requested but unstarted tools, pending delegation/unknown operations, and the interval following a tool result before further response activity. |
| Generating response | Accepted/started model turn or actual public response output. Internal model progress and private reasoning do not classify activity. |
| Done | Successfully committed overall turn. A single tool result never sets Done. |
| Error | Confirmed failed tool result, marked recoverable while the turn remains active; or committed failed/partial turn. |
| Needs input | An actual outstanding approval or clarification, cleared only by its matching resolution or terminal turn event. |

Unknown MCP tool names, arbitrary scripts, shell pipelines/substitutions, custom
package scripts and ambiguous commands use Waiting. Tool-name substrings and
prompt text never qualify an operation. Help/version commands do not count as
tests; collection-only test commands count as validation. File-operation
metadata records target existence before execution, not a claim of a successful
write. Filesystem races remain subject to the existing mutation guards.

## Integration and persistence

- The chat Execution details container is capped at 480px and fills narrower
  available chat space. Its expanded timeline retains its existing internal
  scrolling and wrapping.
- `PublicEvent.activity` adds only an allowlisted label. Requested, started and
  finished events retain their execution IDs; finished status distinguishes
  succeeded, failed and rejected, independently of the existing executed flag.
- `ActivityState` is a read projection, not another agent or task orchestrator.
  Its bounded checkpoint lives in `application_activity`, updated in the same
  SQLite transaction as public events. Snapshots and SSE include current activity;
  session deletion/clear remove the checkpoint. No arguments, result bodies,
  provider continuation data or private reasoning are copied into it.
- The compact timeline retains the latest 80 relevant events for the current
  turn. Existing tool events, transcript outcomes and their retention policies
  remain separate. Return-direct tools close their exact execution before the
  final answer; failed direct results cannot produce Done.
- Execution IDs distinguish overlapping calls, including calls to the same tool.
  The oldest active call keeps the compact label until it finishes. Questions
  and approvals have priority. Child events remain in the existing subagent
  history; parent delegation stays Waiting rather than borrowing a child's label.
- The TUI adapter uses the actual pre-effect execution observer, after permission
  and execution guards. Its terminal session publishes through the same fenced
  journal. Existing transcript output, custom spinner frames/cadence, input,
  cancellation, streaming and session lease handling remain in place.
- WebUI uses a native details control and a polite current-label announcement.
  Timeline rows use text nodes. Reduced motion disables its activity pulse.
  Reconnect/reload restores the checkpoint and timeline; sign-out clears them.

## Limits

Browser chat retains its existing read/file-edit authorization surface. This
change does not enable shell, image generation, dataset processing or new tools
over HTTP. All labels can render in both clients, but unsupported operations
cannot arise through browser chat until their existing product boundaries expand.
The native TUI image workflow already supplies confirmed job activity; data
analysis has no built-in generic dataset tool today. Unknown custom/MCP analysis
or image calls therefore remain Waiting.

Done confirms successful completion at the existing orchestration boundary.
Existing core incomplete-task/runtime errors prevent it. This projection cannot
independently verify a natural-language claim or infer an unrecorded external
effect. Older sessions lacking activity events are not retroactively classified.
Restart an older running host to obtain the new snapshot/SSE fields.

## Validation

Automated checks are deterministic and use isolated stores/workspaces and a
fixture runtime, without model inference or image-provider requests.

- `test_activity.py`: known operation/command mapping, conservative fallbacks,
  recoverable errors, overlapping executions, foreign child events, late events,
  interaction identity, lifecycle separation and checkpoint round trips.
- Bridge/session/TUI/tool regressions: actual approval gates, started execution,
  independent reader reconnect, cancellation, terminal/direct failures, retained
  output, existing file observation, all 13 TUI labels and custom spinners.
- `scripts/webui_activity_smoke.py`: headless Chrome, actual approval and question
  flows, completion/failure/cancellation, reload and SSE reconnect, sign-out and
  reduced motion. Presentation fixtures cover all 13 labels at 1280px and 390px;
  these fixtures do not claim unavailable browser tools executed.

Results on 2026-10-20:

- Bounded activity/bridge/coordination/session/CLI/WebUI/spinner/workspace-tool
  regression set: **1120 passed, 1 skipped, 2 deselected** in 124.63 seconds.
  This selected set excluded two unrelated OAuth tests following an earlier
  broader run that was interrupted without completing; it is not a full-suite
  or `make check` result.
- Final activity/bridge/coordination/session/tool checks after the last classifier
  changes: **142 passed** in 15.40 seconds. The additional lease-expiry checkpoint
  assertion passed separately (**1 passed**).
- Headless Chrome activity smoke: **passed**, including all 13 presentation labels
  at desktop/phone widths and actual permission/question/cancel/failure/reconnect
  flows. No browser exceptions were observed.
- Full production mypy: **212 source files passed**. Activity-scope Ruff,
  JavaScript syntax and `git diff --check` passed.
- Final repository-wide Ruff still reports an unrelated E501 at
  `scripts/webui_library_browser_smoke.py:80`, in concurrent Library-preview work.
  Those changes were preserved. No repository commit or push was made.
