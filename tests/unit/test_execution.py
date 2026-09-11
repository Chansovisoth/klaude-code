from klaude_core.execution import TurnGovernor


def test_turn_governor_tracks_steps_calls_and_remaining_budget():
    now = [100.0]
    governor = TurnGovernor(
        4,
        max_tool_calls=3,
        max_elapsed_seconds=60,
        clock=lambda: now[0],
    )

    assert governor.begin_model_step() == ""
    assert governor.observe_tool_result("inspect", "first evidence") == ""
    now[0] += 2.5
    snapshot = governor.snapshot()

    assert snapshot.model_steps_used == 1
    assert snapshot.model_steps_left == 3
    assert snapshot.tool_calls_used == 1
    assert snapshot.tool_calls_left == 2
    assert snapshot.elapsed_seconds == 2.5


def test_turn_governor_stops_after_cross_tool_no_progress_streak():
    governor = TurnGovernor(20, max_tool_calls=20, max_no_progress=3)

    assert governor.observe_tool_result("read_file", "tool error: missing") == ""
    assert governor.observe_tool_result("grep", "permission denied: blocked") == ""
    assert (
        governor.observe_tool_result("run_shell", "skipped unsafe command")
        == "tool activity stopped making progress"
    )
    assert governor.snapshot().stop_reason == "tool activity stopped making progress"


def test_turn_governor_resets_no_progress_after_new_evidence():
    governor = TurnGovernor(20, max_tool_calls=20, max_no_progress=3)

    governor.observe_tool_result("read_file", "tool error: missing")
    governor.observe_tool_result("grep", "permission denied: blocked")
    assert governor.observe_tool_result("workspace_info", "new workspace evidence") == ""

    assert governor.snapshot().no_progress_streak == 0


def test_turn_governor_stops_at_safe_boundary_after_wall_time():
    now = [10.0]
    governor = TurnGovernor(20, max_elapsed_seconds=5, clock=lambda: now[0])
    assert governor.begin_model_step() == ""

    now[0] = 15.0

    assert governor.begin_model_step() == "turn wall-time budget reached"
    assert governor.snapshot().model_steps_used == 1


def test_delegated_usage_is_charged_to_parent_budget():
    governor = TurnGovernor(5, max_tool_calls=6)
    assert governor.begin_model_step() == ""

    assert governor.charge_delegated_usage(model_steps=3, tool_calls=2) == ""
    assert governor.snapshot().model_steps_used == 4
    assert governor.snapshot().tool_calls_used == 2
    assert (
        governor.charge_delegated_usage(model_steps=1, tool_calls=0)
        == "model/tool step budget reached"
    )


def test_turn_governor_enforces_exact_tokens_and_marks_unknown_usage():
    governor = TurnGovernor(5, max_total_tokens=100)

    assert governor.observe_model_usage((60, 39)) == ""
    assert governor.observe_model_usage(None) == ""
    assert governor.observe_model_usage((1, 0)) == "token budget reached"

    snapshot = governor.snapshot()
    assert snapshot.input_tokens_used == 61
    assert snapshot.output_tokens_used == 39
    assert snapshot.total_tokens_used == 100
    assert snapshot.tokens_left == 0
    assert snapshot.token_usage_unknown_requests == 1
