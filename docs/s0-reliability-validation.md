# S0 reliability validation

Date: 2026-10-06. Status: **S0 complete; local validation and checkpoint CI passed.**
Roadmap: [S0 in the settings and feature plan](odysseus-settings-and-features-plan.md#s0--finish-the-reliability-baseline).
Baseline: `af334d5ff4c9cf4ba5835b1d58324c40cd419139` (published alpha.4).

## Observed failure and reproduction

The [alpha.4 tag CI](https://github.com/Chansovisoth/klaude-code/actions/runs/37352698919)
failed `test_settings_picker_responds_while_session_write_is_blocked[memory]`
at `SessionActionWriter.close(wait=True)`: 1 failed, 2,449 passed, 19 skipped.
The [main CI](https://github.com/Chansovisoth/klaude-code/actions/runs/37352698699)
passed for the same commit. The CI trace does not retain the worker's underlying
exception, so its precise inner failure is not independently established.

A controlled reproduction through the real Prompt Toolkit application and a
real SQLite-backed session action writer produced the same failed drain result:

1. A memory preference commits successfully and its success event is queued.
2. The worker enters `Application.invalidate()` and checks its event loop.
3. The TUI exits and clears its loop before the worker schedules the repaint.
4. The repaint raises `AttributeError`: a missing loop has no
   `call_soon_threadsafe` method.
5. The action writer catches that notification exception and reports failure,
   although the database contains the requested preference.

This establishes a real teardown bug consistent with the CI symptom; it does
not establish that every failed drain has this cause.

## Fix and regression coverage

[`PersistentChatTUI._emit`](../apps/cli/src/klaude_cli/main.py) still queues the
event first. It tolerates an `AttributeError` or `RuntimeError` from repainting
only when the application has stopped or its loop is absent/closed. Errors in
a running application propagate. Database failures and the writer's bounded
two-second drain retain their existing behavior.

New tests in [test_cli_commands.py](../tests/unit/test_cli_commands.py):

- `test_session_write_acknowledgement_survives_tui_shutdown`: synchronizes the
  actual loop-check/teardown race, verifies the stored preference and successful
  acknowledgement, and requires a successful writer drain.
- `test_tui_emit_preserves_redraw_errors_while_running`: verifies both exception
  types still propagate during a running TUI.

The original failing settings-responsiveness test remains intact. The controlled
reproduction failed before the fix and passed afterward.

## Local validation

- Locked `make check` on Python 3.12.3: **2,453 passed, 19 skipped** in 130.10s;
  Ruff passed; production mypy passed on **83 source files**.
- Focused verification: **12 repository test cases** plus the isolated
  before/after reproduction passed.
- Fresh `make package-smoke`: built and installed **five wheels** in an isolated
  environment, imported all public packages, and ran installed `klaude --help`.
- `git diff --check` passed.

The full suite includes these representative safeguards:

| Safeguard | Existing tests included in the passing suite |
| --- | --- |
| Plan approval and read-only planning | `test_workspace_plan_continuation_keeps_implementation_tools`; `test_plan_mode_blocks_writes_but_keeps_read_and_retrieval_tools` |
| Cancellation | `test_cancel_releases_permission_wait`; `test_agent_cancellation_reaches_primary_and_isolated_child_transports` |
| Malformed-call and path recovery | `test_tool_markup_recovers_without_leaking`; `test_missing_file_batch_can_discover_correct_paths_and_read_them` |
| Shell failures and validation reruns | `test_failed_shell_validation_can_rerun_the_same_command_after_an_edit`; `test_three_nonzero_shell_responses_still_stop_as_no_progress` |
| Workspace cache invalidation | `test_read_file_can_be_read_again_after_mutation_in_the_same_turn` |
| Dirty-worktree safety | `test_dirty_tree_preflight_before_approval` |
| Validation-driven repair | `test_failed_validation_cannot_finalize_before_one_bounded_repair` |
| Failure exit codes | `test_oneshot_renderer_reports_failure_after_persisting_session` |
| Stale-worker recovery | `test_killed_worker_is_recovered_by_a_new_process` |
| Genuine storage failures | `test_locked_storage_fails_once_without_unsupported_history_or_event` |

The validated production file SHA-256 is
`fbffa233f8a05753cd0431b3f3e1fdaa61238b7ddae7aa65bd86c12cb7af86f5`
for `apps/cli/src/klaude_cli/main.py`; the test file SHA-256 is
`ad853b4f6e8933319809bcfc005d5a5094ebeed55a534500ff47d7aa50241998`
for `tests/unit/test_cli_commands.py`.

Temporary logs: `/tmp/klaude-ci-shutdown-make-check-final.log` and
`/tmp/klaude-s0-package-smoke.log`. They are local evidence, not repository
artifacts. These checks do not establish completion of the small-model CSV
benchmark, whose evaluation remains in the separate orchestration track.

## Checkpoint CI and completed gate

Verified checkpoint: `02fcf48323ed857e8f289b5a8679d1ea70b3b0ef`, pushed to main
with explicit user approval. Its
[CI run 37426174871](https://github.com/Chansovisoth/klaude-code/actions/runs/37426174871)
completed successfully for that exact commit:

| Job | Result |
| --- | --- |
| Tests, Python 3.11 | 2,453 passed, 19 skipped; 93.47s |
| Tests, Python 3.12 | 2,453 passed, 19 skipped; 95.86s |
| Tests, Python 3.13 | 2,453 passed, 19 skipped; 96.67s |
| Lint and production types | Ruff passed; mypy passed on 83 source files |
| Build and installed-CLI smoke | Five wheels built/installed; imports and installed `klaude --help` passed |

The approved checkpoint push started CI through the existing workflow. The
earlier token limitation affected manual reruns and did not prevent this gate.
Temporary CI log: `/tmp/klaude-s0-checkpoint-ci.log`.

S0 is complete. The fix is on main; the published alpha.4 tag and wheel artifacts
still identify the earlier release checkpoint. S1 remains planned and unstarted.
