from copy import deepcopy

import pytest
from klaude_cli.main import (
    _completed_tool_activity,
    _render,
    _select_tool_names,
    resolve_command_help_request,
)
from klaude_core import Agent, AgentEvent, PermissionGate, Tool
from klaude_core.memory import Memory
from klaude_core.model_runtime import ModelCapabilities, ModelInfo
from klaude_tools import Workspace, build_tools, classify_command


class Runtime:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self, model, messages, tools=None, **kwargs):
        self.requests.append((deepcopy(messages), tools))
        return next(self.responses)


def call(name, **args):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args}}],
    }


def make_agent(runtime, tools, ask=lambda *_: "y", selector=None):
    return Agent(runtime, "fake", tools, PermissionGate({}, ask), "system", tool_selector=selector)


@pytest.mark.parametrize(
    "message",
    [
        "What's filling my OS drive?",
        "Check storage capacity",
        "Inspect disk usage",
        "Why is the filesystem full?",
        "run those commands",
        "run them",
        "run theme",
    ],
)
def test_diagnostic_routing_excludes_writes(tmp_path, message):
    tools = {t.name: t for t in build_tools(Workspace(tmp_path))}
    selected = set(_select_tool_names(message, tools))
    assert selected & {"storage_usage", "run_shell"}
    assert not selected & {"write_file", "edit_file", "git_commit"}


@pytest.mark.parametrize(
    "message",
    [
        "Update the Python file",
        "editing README.md",
        "repair this project",
        "fixing the parser",
        "use write_file to add the documentation",
        "do final cleanup",
        "finish editing the project",
        "finalize the files",
    ],
)
def test_mutation_routing_includes_edit_tools_but_not_implicit_commit(tmp_path, message):
    tools = {t.name: t for t in build_tools(Workspace(tmp_path))}
    selected = set(_select_tool_names(message, tools))
    assert {"read_file", "write_file", "edit_file"} <= selected
    assert "git_commit" not in selected


def test_slash_inside_workspace_path_is_not_command_help():
    assert resolve_command_help_request("Review app/tests/test_api.py") is None
    assert resolve_command_help_request("what does /init do") is not None


def test_image_request_does_not_expose_text_reader_as_pixel_vision(tmp_path):
    tools = {t.name: t for t in build_tools(Workspace(tmp_path))}
    selected = set(_select_tool_names("What is shown in this image file?", tools))
    assert "read_file" not in selected
    assert "workspace_info" in selected


@pytest.mark.parametrize(
    "command",
    [
        "df -h / | head -2",
        "du -sh /* 2>/dev/null | sort -hr | head -15",
        "du -sh ~/* 2>/dev/null | sort -hr | head -10",
        "df -h .",
        "find . -type f | sort | tail -10",
        "grep hello *.txt | head -2",
    ],
)
def test_read_only_pipeline_classification(command):
    assert classify_command(command).risk == "read-only inspection"


@pytest.mark.parametrize(
    "command",
    [
        "du . | tee result",
        "du . > result",
        "du . | sort -o result",
        "du . | sort --compress-program=evil",
        "find . -fprint result",
        "du $(touch changed)",
        "du .; touch changed",
        "du . | rm file",
        "du . | unknown",
        "du . && rm -rf .",
        "du . |",
    ],
)
def test_unsafe_pipeline_not_read_only(command):
    assert classify_command(command).risk != "read-only inspection"


def test_dirty_tree_preflight_before_approval(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.write_enabled = False
    tools = build_tools(workspace)
    approvals = []
    runtime = Runtime(
        [
            call("run_shell", command="touch generated"),
            {"role": "assistant", "content": "The user must resolve the dirty tree."},
        ]
    )
    events = list(
        make_agent(runtime, tools, lambda *args: approvals.append(args)).run("run command")
    )
    assert not approvals
    result = next(e.payload for e in events if e.kind == "tool_result")
    assert "user-owned" in result["result"]
    assert result["metadata"]["executed"] is False
    workspace.preflight_shell("du -sh . | sort -hr | head -5")
    with pytest.raises(PermissionError, match="escapes workspace"):
        workspace.preflight_shell("du -sh /")


def test_tool_markup_recovers_without_leaking():
    runtime = Runtime(
        [
            {"role": "assistant", "content": '<web_search query="a" num_results="10">'},
            call("web_search", query="a"),
            {"role": "assistant", "content": "Found evidence."},
        ]
    )
    tool = Tool(
        "web_search",
        "search",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        lambda query: "Evidence",
    )
    events = list(make_agent(runtime, [tool]).run("Find evidence"))
    assert any(e.kind == "retry" for e in events)
    assert any(e.kind == "tool_result" for e in events)
    assert all("<web_search" not in str(e.payload) for e in events)


def test_unavailable_tool_recovery_bounded():
    runtime = Runtime([call("run_shell", command="pwd")] * 5)
    tool = Tool("run_shell", "shell", {}, lambda: pytest.fail("must not execute"))
    events = list(make_agent(runtime, [tool], selector=lambda *_: []).run("inspect"))
    assert len(runtime.requests) == 2
    assert events[-1].kind == "error"
    assert "Callable this request: (none)" in runtime.requests[0][0][0]["content"]
    assert "Unavailable this request: run_shell" in runtime.requests[0][0][0]["content"]


def test_repeated_tool_failure_retires_tool_and_finalizes_without_looping():
    runtime = Runtime(
        [
            call("inspect", path="/tmp/missing"),
            call("inspect", path="/tmp/missing"),
            {"role": "assistant", "content": "The inspection could not be completed."},
        ]
    )
    tool = Tool(
        "inspect",
        "inspect a path",
        {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        lambda **_: (_ for _ in ()).throw(RuntimeError("diagnostic unavailable")),
    )

    events = list(make_agent(runtime, [tool]).run("inspect the path"))

    assert len(runtime.requests) == 3
    assert any(
        event.kind == "retry"
        and "retired repeatedly unsuccessful tool inspect" in event.payload["reason"]
        for event in events
    )
    assert events[-1].kind == "done"
    assert "could not be completed" in events[-2].payload["content"]
    assert runtime.requests[2][1] == []


def test_cross_tool_no_progress_forces_tool_free_finalization():
    runtime = Runtime(
        [
            call("one"),
            call("two"),
            call("three"),
            {"role": "assistant", "content": "All available approaches were blocked."},
        ]
    )

    def fail(name):
        def run():
            raise RuntimeError(f"{name} unavailable")

        return run

    tools = [
        Tool(name, name, {"type": "object", "properties": {}}, fail(name))
        for name in ("one", "two", "three")
    ]

    events = list(make_agent(runtime, tools).run("try the available diagnostics"))

    assert len(runtime.requests) == 4
    assert runtime.requests[3][1] == []
    assert events[-1].kind == "done"
    assert "blocked" in events[-2].payload["content"]


def test_request_user_input_is_removed_after_one_answer():
    responses = [
        call("request_user_input", question="Which fruit?"),
        call("request_user_input", question="Which fruit?"),
        {"role": "assistant", "content": "You selected Apple."},
    ]
    runtime = Runtime(responses)
    tool = Tool(
        "request_user_input",
        "ask",
        {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
        lambda question: '{"status":"answered","answer":"Apple"}',
    )
    events = list(make_agent(runtime, [tool]).run("Help me choose fruit"))
    assert len(runtime.requests) == 3
    assert runtime.requests[1][1] == []
    assert any(event.kind == "retry" for event in events)
    assert events[-2].payload["content"] == "You selected Apple."


def test_prose_about_python_is_not_rewritten_as_missing_code():
    runtime = Runtime([{"role": "assistant", "content": "The Python tests all pass."}])
    events = list(make_agent(runtime, []).run("Summarize the Python test results"))
    assert len(runtime.requests) == 1
    assert events[-2].payload["content"] == "The Python tests all pass."
    assert runtime.requests[0][1] == []
    assert len(runtime.requests[0][0][0]["content"]) < 1_000


def test_argument_schema_checked_before_approval():
    approvals = []
    tool = Tool(
        "inspect",
        "inspect",
        {
            "type": "object",
            "properties": {"count": {"type": "integer", "maximum": 3}},
            "required": ["count"],
        },
        lambda count: pytest.fail("must not execute"),
    )
    runtime = Runtime([call("inspect", count=100), {"role": "assistant", "content": "Invalid."}])
    list(make_agent(runtime, [tool], lambda *args: approvals.append(args)).run("inspect"))
    assert not approvals


def test_always_is_only_gate_lifetime():
    configured = {"run_shell": "ask"}
    gate = PermissionGate(configured, lambda *_: "a")
    gate.check("run_shell", "first")
    gate.set_ask_callback(lambda *_: pytest.fail("should not ask again"))
    gate.check("run_shell", "second")
    assert configured == {"run_shell": "ask"}
    assert PermissionGate(configured, lambda *_: "n").policies["run_shell"] == "ask"


def test_skipped_duplicate_is_not_ran():
    assert (
        _completed_tool_activity(
            "run_shell", {"command": "du ."}, "skipped duplicate tool call", {}
        )[0]
        == "skipped"
    )


def test_snapshot_durably_recovers_abandoned_turn_once(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.acquire_session_lease("s", "client", "t")
    memory.start_session_turn("s", "client", "t", "inspect storage")
    memory.publish_session_event(
        "s", "client", "assistant_delta", {"text": "Partial answer"}, turn_id="t"
    )
    memory.update_session_live("s", owner_lease_until=0)
    snapshot = memory.session_snapshot("s")
    assert snapshot["live"]["state"] == "interrupted"
    assert any(t["content"] == "Partial answer" for t in snapshot["turns"])
    assert "Interrupted:" in snapshot["turns"][-1]["content"]["message"]
    assert snapshot["recovered_turn_ids"] == ["t"]
    before_second_snapshot = memory.db.total_changes
    second = memory.session_snapshot("s")
    assert memory.db.total_changes == before_second_snapshot
    assert second["turns"] == snapshot["turns"]
    assert second["live"] == snapshot["live"]
    assert second["event_cursor"] == snapshot["event_cursor"]
    assert second["recovered_turn_ids"] == []


def test_snapshot_does_not_interrupt_active_turn(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.acquire_session_lease("s", "client", "t")
    memory.start_session_turn("s", "client", "t", "inspect storage")
    assert len(memory.session_snapshot("s")["turns"]) == 1


def test_execution_events_correlate(tmp_path):
    tool = Tool("inspect", "inspect", {}, lambda: "exit=0\nresult")
    runtime = Runtime([call("inspect"), {"role": "assistant", "content": "done"}])
    events = list(make_agent(runtime, [tool]).run("inspect"))
    start = next(e.payload for e in events if e.kind == "tool_start")
    result = next(e.payload for e in events if e.kind == "tool_result")
    assert start["execution_id"] == result["metadata"]["execution_id"]
    assert result["metadata"]["executed"] is True


def test_line_renderer_uses_durable_turn_lifecycle(tmp_path, monkeypatch):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    class LineAgent:
        model = "fake"

        def run(self, _message):
            yield AgentEvent("text", {"content": "Completed answer."})
            yield AgentEvent("done", {})

    monkeypatch.setattr("klaude_cli.main._print_trace", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("klaude_cli.main._print_assistant_text", lambda *_args, **_kwargs: None)

    assert _render(LineAgent(), memory, "session", "question") == "Completed answer."
    snapshot = memory.session_snapshot("session")
    assert [turn["role"] for turn in snapshot["turns"]] == ["user", "assistant"]
    assert snapshot["live"]["state"] == "idle"
    assert any(
        event["kind"] == "turn_done"
        for event in memory.session_events_since("session", 0)
    )


def test_line_renderer_marks_silent_turn_failed(tmp_path, monkeypatch):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    class SilentAgent:
        model = "fake"

        def run(self, _message):
            if False:
                yield

    monkeypatch.setattr("klaude_cli.main._print_trace", lambda *_args, **_kwargs: None)

    assert _render(SilentAgent(), memory, "session", "question") == ""
    snapshot = memory.session_snapshot("session")
    assert snapshot["live"]["state"] == "failed"
    assert "without a completed answer" in snapshot["turns"][-1]["content"]["message"]


def test_expired_worker_cannot_resurrect_or_overlap(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    assert memory.acquire_session_lease("s", "client", "first")
    assert not memory.acquire_session_lease("s", "client", "second")
    memory.update_session_live("s", owner_lease_until=0)
    assert not memory.renew_session_lease("s", "client", "first")
    assert memory.acquire_session_lease("s", "other", "second")
    assert not memory.release_session_lease("s", "client", "first")


def test_short_execution_followup_has_command_context(tmp_path):
    runtime = Runtime([{"role": "assistant", "content": "Ready."}])
    agent = make_agent(runtime, build_tools(Workspace(tmp_path)), selector=_select_tool_names)
    agent.messages.append({"role": "assistant", "content": "Inspect with:\n```bash\ndu -sh .\n```"})
    list(agent.run("execute those"))
    assert "preceding assistant supplied shell commands" in runtime.requests[0][0][0]["content"]


def test_followup_retains_research_capability():
    runtime = Runtime([{"role": "assistant", "content": "Ready."}])
    tool = Tool("web_search", "search", {}, lambda: "evidence")
    agent = make_agent(runtime, [tool], selector=_select_tool_names)
    agent.messages.append({"role": "user", "content": "look up a public biography"})
    agent.messages.append({"role": "assistant", "content": "I will search."})
    list(agent.run("you failed"))
    assert "web_search" in {t["function"]["name"] for t in runtime.requests[0][1]}


def test_continue_workspace_task_inherits_edits_but_not_git_mutation(tmp_path):
    runtime = Runtime([{"role": "assistant", "content": "Cleanup completed."}])
    agent = make_agent(runtime, build_tools(Workspace(tmp_path)), selector=_select_tool_names)
    agent.messages.extend(
        [
            {"role": "user", "content": "Update and test the project files."},
            {"role": "assistant", "content": "I updated most of the implementation."},
        ]
    )

    list(agent.run("continue where you left off"))

    names = {item["function"]["name"] for item in runtime.requests[0][1]}
    assert {"write_file", "edit_file", "run_shell"} <= names
    assert "git_commit" not in names


def test_live_permission_policy_is_explicit_in_turn_capabilities():
    runtime = Runtime([{"role": "assistant", "content": "Done."}])
    tools = [
        Tool("write_file", "write", {}, lambda: "ok"),
        Tool("edit_file", "edit", {}, lambda: "ok"),
    ]
    gate = PermissionGate({"write_file": "allow", "edit_file": "deny"}, lambda *_: "n")
    agent = Agent(
        runtime,
        "fake",
        tools,
        gate,
        "system",
        tool_selector=lambda *_: ["write_file", "edit_file"],
    )

    list(agent.run("continue editing"))

    prompt = runtime.requests[0][0][0]["content"]
    assert "ALLOW=write_file" in prompt
    assert "DENY=edit_file" in prompt
    assert "current live settings for this turn" in prompt
    assert {item["function"]["name"] for item in runtime.requests[0][1]} == {"write_file"}
    assert agent.last_turn_capabilities["callable_tools"] == ["write_file"]
    assert agent.last_turn_capabilities["unavailable_tools"]["edit_file"] == (
        "permission policy deny"
    )


def test_provider_without_tool_support_receives_no_schemas():
    runtime = Runtime([{"role": "assistant", "content": "I cannot call tools here."}])
    agent = Agent(
        runtime,
        "text-only",
        [Tool("inspect", "inspect", {}, lambda: pytest.fail("must not execute"))],
        PermissionGate({"inspect": "allow"}, lambda *_: pytest.fail("must not prompt")),
        "system",
        tool_selector=lambda *_: ["inspect"],
        model_info=ModelInfo(
            "fake",
            "text-only",
            "Text only",
            ModelCapabilities(supports_tools=False),
        ),
    )

    events = list(agent.run("inspect this"))

    assert runtime.requests[0][1] == []
    assert [event.kind for event in events] == ["text", "done"]
    assert agent.last_turn_capabilities["provider"]["supports_tools"] is False
    assert agent.last_turn_capabilities["callable_tools"] == []
    assert agent.last_turn_capabilities["unavailable_tools"]["inspect"] == (
        "selected provider/model does not support tool calling"
    )


def test_done_event_contains_same_sanitized_capability_snapshot():
    runtime = Runtime([{"role": "assistant", "content": "Done."}])
    observed_capabilities = []
    agent = Agent(
        runtime,
        "fake",
        [Tool("inspect", "inspect", {}, lambda: "ok")],
        PermissionGate({"inspect": "allow"}, lambda *_: "n"),
        "system",
    )
    agent.capability_observer = observed_capabilities.append

    events = list(agent.run("inspect this"))

    snapshot = events[-1].payload["turn_capabilities"]
    assert snapshot == agent.last_turn_capabilities
    assert snapshot["callable_tools"] == ["inspect"]
    assert "budget" in snapshot
    assert observed_capabilities[0]["callable_tools"] == ["inspect"]
    assert [event.kind for event in events] == ["text", "done"]


def test_permission_setting_change_rebuilds_next_request_capabilities():
    runtime = Runtime(
        [
            {"role": "assistant", "content": "Writing is currently unavailable."},
            {"role": "assistant", "content": "Writing is now available."},
        ]
    )
    gate = PermissionGate({"write_file": "deny"}, lambda *_: "n")
    agent = Agent(
        runtime,
        "fake",
        [Tool("write_file", "write", {}, lambda: "ok")],
        gate,
        "system",
        tool_selector=lambda *_: ["write_file"],
    )

    list(agent.run("edit the file"))
    gate.policies["write_file"] = "allow"
    list(agent.run("continue editing"))

    assert runtime.requests[0][1] == []
    assert {item["function"]["name"] for item in runtime.requests[1][1]} == {
        "write_file"
    }
    assert "DENY=write_file" in runtime.requests[0][0][0]["content"]
    assert "ALLOW=write_file" in runtime.requests[1][0][0]["content"]
    assert agent.last_turn_capabilities["effective_permissions"] == {
        "write_file": "allow"
    }


def test_session_restore_clears_live_capability_snapshot():
    runtime = Runtime([{"role": "assistant", "content": "Done."}])
    agent = Agent(
        runtime,
        "fake",
        [Tool("inspect", "inspect", {}, lambda: "ok")],
        PermissionGate({"inspect": "allow"}, lambda *_: "n"),
        "system",
    )
    list(agent.run("inspect this"))
    assert agent.last_turn_capabilities

    agent.restore_session([{"role": "user", "content": "new session"}])

    assert agent.last_turn_capabilities == {}
    assert agent.last_turn_budget == {}


def test_text_or_native_call_cannot_bypass_denied_schema_filter():
    executed = False

    def forbidden_tool():
        nonlocal executed
        executed = True
        return "should not run"

    runtime = Runtime(
        [
            call("write_file"),
            {"role": "assistant", "content": "Writing is denied."},
        ]
    )
    agent = Agent(
        runtime,
        "fake",
        [Tool("write_file", "write", {}, forbidden_tool)],
        PermissionGate({"write_file": "deny"}, lambda *_: pytest.fail("must not prompt")),
        "system",
        tool_selector=lambda *_: ["write_file"],
    )

    events = list(agent.run("edit the file"))

    assert executed is False
    assert any(
        event.kind == "retry" and "unavailable tool call" in event.payload["reason"]
        for event in events
    )
    assert not any(event.kind in {"tool_start", "tool_result"} for event in events)
    assert agent.last_turn_capabilities["unavailable_tools"]["write_file"] == (
        "permission policy deny"
    )


def test_step_limit_gets_one_tool_free_final_synthesis():
    runtime = Runtime(
        [
            call("inspect"),
            {"role": "assistant", "content": "Inspection completed; one item remains."},
        ]
    )
    tool = Tool("inspect", "inspect", {}, lambda: "observed result")
    agent = Agent(
        runtime,
        "fake",
        [tool],
        PermissionGate({"inspect": "allow"}, lambda *_: "y"),
        "system",
        max_steps=1,
    )

    events = list(agent.run("inspect this"))

    assert len(runtime.requests) == 2
    assert runtime.requests[1][1] == []
    assert any(
        event.kind == "text" and "one item remains" in event.payload["content"]
        for event in events
    )
    assert events[-1].kind == "done"


def test_streamed_markup_is_quarantined():
    class Streaming(Runtime):
        def chat_stream(self, *args, **kwargs):
            yield {"content": "<web_"}
            yield {"content": 'search query="test">'}

    runtime = Streaming([])
    agent = make_agent(
        runtime, [Tool("web_search", "search", {}, lambda: "evidence")], selector=lambda *_: []
    )
    events = list(agent.run("inspect"))
    assert not any(e.kind in {"text", "text_delta"} for e in events)
    assert events[-1].kind == "error"


def test_invalid_shell_syntax_never_prompts(tmp_path):
    workspace = Workspace(tmp_path)
    tool = next(t for t in build_tools(workspace) if t.name == "run_shell")
    runtime = Runtime(
        [call("run_shell", command="ls |"), {"role": "assistant", "content": "Invalid syntax."}]
    )
    events = list(make_agent(runtime, [tool], lambda *_: pytest.fail("no approval")).run("run"))
    assert "invalid shell syntax" in next(
        e.payload["result"] for e in events if e.kind == "tool_result"
    )


def test_storage_scans_metadata_without_following_symlinks(tmp_path, monkeypatch):
    import os

    from klaude_tools import diagnostics

    category = tmp_path / "category"
    category.mkdir()
    (category / "data").write_bytes(b"x" * 4096)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("never read this")
    (category / "link").symlink_to(outside, target_is_directory=True)
    real_open = os.open
    calls = []

    def open_category(path, flags, **kwargs):
        calls.append(str(path))
        return real_open(category if str(path).startswith("/") else path, flags, **kwargs)

    monkeypatch.setattr(diagnostics.os, "open", open_category)
    result = diagnostics.storage_usage()
    assert "Metadata only" in result
    assert "link" not in calls and "secret" not in calls
    assert "never read this" not in result


def test_read_pipeline_executes_under_landlock_in_dirty_workspace(tmp_path):
    workspace = Workspace(tmp_path)
    workspace.write_enabled = False
    (tmp_path / "example.txt").write_text("test\n")
    result = workspace.run_shell("du -s . | sort -nr | head -1")
    assert result.startswith("exit=0\n"), result
    assert "." in result
    with pytest.raises(PermissionError, match="user-owned"):
        workspace.run_shell("du -s . | tee result.txt")


@pytest.mark.parametrize("command", ["du . &>result", "du . | sort -nro result"])
def test_combined_output_syntax_not_read_only(command):
    assert classify_command(command).risk != "read-only inspection"
