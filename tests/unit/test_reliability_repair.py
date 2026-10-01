from copy import deepcopy

import pytest
from klaude_cli.main import (
    _completed_tool_activity,
    _render,
    _select_tool_names,
    resolve_command_help_request,
)
from klaude_core import Agent, AgentEvent, PermissionGate, Tool, TurnScope
from klaude_core.memory import Memory
from klaude_core.model_runtime import ModelCapabilities, ModelInfo
from klaude_core.research_receipts import research_receipt
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


def test_provider_continuation_state_is_private_and_restorable():
    provider_message = {
        "role": "assistant",
        "content": "Done.",
        "openai_response_items": [
            {
                "id": "rs_123",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": "opaque-state",
            },
            {
                "id": "msg_123",
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "Done.", "annotations": []}
                ],
                "phase": "final_answer",
            },
        ],
    }
    agent = make_agent(Runtime([provider_message]), [])

    events = list(agent.run("finish"))

    text_event = next(event for event in events if event.kind == "text")
    assert text_event.payload["content"] == "Done."
    assert text_event.payload["model_message"] == provider_message

    restored = make_agent(Runtime([]), [])
    restored.restore_session(
        [
            {"role": "user", "content": "finish"},
            {
                "role": "assistant",
                "content": "Done.",
                "model_content": provider_message,
            },
        ]
    )
    assert restored.messages[-1] == provider_message


def test_restored_interrupted_research_preserves_objective_without_inventing_results():
    runtime = Runtime([{"role": "assistant", "content": "I need to re-check the sources."}])
    agent = make_agent(runtime, [])
    request = (
        "Compare local knowledge, web search, and Context7 for Godot 2D "
        "player code with melee and ranged weapon switching."
    )
    agent.restore_session(
        [
            {"role": "user", "content": request},
            {"role": "system", "content": {
                "event": "tool_audit", "tool": "web_search", "phase": "result",
                "executed": True,
            }},
            {"role": "assistant", "content": "I found some sources but have not compared"},
            {"role": "system", "content": {
                "event": "interruption", "message": "Interrupted at a safe boundary.",
            }},
        ]
    )

    list(agent.run("continue where left off"))

    prompt = runtime.requests[0][0]
    assert prompt[-1]["role"] == "user"
    assert request in prompt[-1]["content"]
    assert "Prior tool audit entries are not their results" in prompt[-1]["content"]
    assert "No durable research receipts are available" in prompt[-1]["content"]
    assert agent.messages[-2]["content"] == "continue where left off"
    assert agent._restored_unfinished_task == ""


def test_restored_interruption_does_not_hijack_new_topic_or_completed_turn():
    interrupted = [
        {"role": "user", "content": "Research Godot code."},
        {"role": "system", "content": {"event": "interruption"}},
    ]
    runtime = Runtime([{"role": "assistant", "content": "Hello."}])
    agent = make_agent(runtime, [])
    agent.restore_session(interrupted)
    list(agent.run("Tell me about Python instead"))
    assert "Research Godot code" not in runtime.requests[0][0][-1]["content"]

    completed = make_agent(Runtime([]), [])
    completed.restore_session([*interrupted, {"role": "assistant", "content": "Done."}])
    assert completed._restored_unfinished_task == ""


def test_same_process_interrupted_turn_survives_model_change():
    runtime = Runtime([{"role": "assistant", "content": "Continuing the comparison."}])
    agent = make_agent(runtime, [])
    agent.messages.append({"role": "user", "content": "Compare Godot examples from each source."})
    agent.mark_interrupted_turn()
    agent.model = "replacement-model"

    list(agent.run("continue where left off"))

    assert "Compare Godot examples from each source" in runtime.requests[0][0][-1]["content"]
    assert agent.messages[-2]["content"] == "continue where left off"


def test_multi_source_followup_inherits_safe_retrieval_without_mcp_or_writes():
    runtime = Runtime([{"role": "assistant", "content": "I will compare them."}])
    names = (
        "web_search", "fetch_url", "query_knowledge", "write_file", "run_shell",
        "mcp__example__delete_records",
    )
    tools = [Tool(name, name, {}, lambda: "ok") for name in names]
    agent = make_agent(runtime, tools, selector=_select_tool_names)
    agent.messages.extend([
        {"role": "user", "content": "Which knowledge sources did you use?"},
        {"role": "assistant", "content": (
            "I can use local knowledge (query_knowledge), web search "
            "(web_search/fetch_url), or the example MCP source."
        )},
    ])

    list(agent.run("Try getting from each sources, see if you like it"))

    callable_names = {item["function"]["name"] for item in runtime.requests[0][1]}
    assert {"query_knowledge", "web_search", "fetch_url"} <= callable_names
    assert not callable_names & {"write_file", "run_shell", "mcp__example__delete_records"}


@pytest.mark.parametrize("source_question", [
    "Which source did you use for that answer?",
    "Which knowledge sources did you use?",
    "did u use your local knowledge library, did research, use context7, or "
    "simply with general intelligence/knowledge",
])
def test_actual_source_use_question_differs_from_available_sources_after_restore(
    source_question,
):
    request = "code a simple Godot 4.7 player character movement for a topdown 2d rpg game"
    answer = "Here is a Godot movement example."
    turns = [
        {"role": "user", "content": request},
        {"role": "assistant", "content": answer},
    ]
    runtime = Runtime([{"role": "assistant", "content": "I could use local knowledge or web."}])
    agent = make_agent(runtime, [])
    agent.restore_session([
        *turns,
        {"role": "system", "content": {"event": "session_update", "detail": "saved"}},
    ])
    agent.model = "replacement-model"

    actual = list(agent.run(source_question))

    assert not runtime.requests
    assert actual[0].kind == "text"
    assert "No retrieval tool was used" in actual[0].payload["content"]
    assert "model's existing knowledge" in actual[0].payload["content"]
    assert "local knowledge" not in actual[0].payload["content"]

    agent.restore_session(turns)
    list(agent.run("What sources could you use for this task?"))
    assert len(runtime.requests) == 1


def test_source_use_tracks_completed_results_not_started_calls_or_missing_evidence():
    turns = [
        {"role": "user", "content": "Compare Godot code from local, web, and Context7."},
        {"role": "system", "content": {
            "event": "tool_audit", "tool": "query_knowledge", "phase": "start",
        }},
        {"role": "system", "content": {
            "event": "tool_audit", "tool": "web_search", "phase": "result",
            "executed": True,
        }},
        {"role": "system", "content": {
            "event": "tool_audit", "tool": "mcp__context7__get_docs", "phase": "result",
            "executed": True,
        }},
        {"role": "assistant", "content": "The comparison is incomplete."},
        {"role": "system", "content": {"event": "interruption"}},
    ]
    agent = make_agent(Runtime([]), [])
    agent.restore_session([
        *turns,
        {"role": "system", "content": {"event": "session_update", "detail": "saved"}},
    ])
    result = list(agent.run("Which sources did you use?"))[0].payload["content"]
    assert "interrupted" in result
    assert "evidence returned" in result

    completed = make_agent(Runtime([]), [])
    completed.restore_session(turns[:-1])
    result = list(completed.run("Which sources did you use?"))[0].payload["content"]
    assert "web search" in result
    assert "MCP tool mcp__context7__get_docs" in result
    assert "local knowledge" not in result
    assert "do not by themselves preserve" in result

    workspace_answer = make_agent(Runtime([]), [])
    workspace_answer.restore_session([
        {"role": "user", "content": "What is in my file?"},
        {"role": "system", "content": {
            "event": "tool_audit", "tool": "read_file", "phase": "result",
            "executed": True,
        }},
        {"role": "assistant", "content": "It contains a config."},
    ])
    result = list(workspace_answer.run("Which sources did you use?"))[0].payload["content"]
    assert "read_file" in result
    assert "No retrieval tool was used" not in result


def test_research_receipt_is_bounded_metadata_and_recovery_requires_refetch():
    receipt = research_receipt(
        "fetch_url",
        {"url": "https://example.com/private?token=secret"},
        {
            "executed": True,
            "source_id": "src_42",
            "canonical_url": "https://example.com/guide?token=secret#section",
        },
        "PRIVATE FULL TOOL RESULT",
    )
    assert receipt is not None
    assert receipt["public_url"] == "https://example.com/guide"
    assert receipt["result_replayable"] is False
    assert "PRIVATE" not in str(receipt)
    assert "secret" not in str(receipt)

    runtime = Runtime([{"role": "assistant", "content": "I will fetch it again."}])
    agent = make_agent(runtime, [])
    agent.restore_session([
        {"role": "user", "content": "Compare Godot examples from the web and Context7."},
        {"role": "system", "content": receipt},
        {"role": "system", "content": {
            "event": "tool_audit", "tool": "mcp__context7__get_docs",
            "phase": "result", "executed": True,
        }},
        {"role": "system", "content": {"event": "interruption"}},
    ])
    list(agent.run("continue where left off"))
    prompt = runtime.requests[0][0][-1]["content"]
    assert "fetch_url" in prompt
    assert "https://example.com/guide" in prompt
    assert "results must be fetched again" in prompt
    assert "PRIVATE FULL TOOL RESULT" not in prompt
    assert "mcp__context7__get_docs" not in prompt  # audit alone is not a receipt


def test_line_chat_persists_research_receipt_separately_from_tool_audit(tmp_path):
    runtime = Runtime([
        call("query_knowledge", query="Godot movement", library="godot"),
        {"role": "assistant", "content": "I found one relevant chunk."},
    ])
    tool = Tool(
        "query_knowledge", "knowledge", {"type": "object", "properties": {
            "query": {"type": "string"}, "library": {"type": "string"},
        }},
        lambda query, library: {
            "content": "PRIVATE GODOT CHUNK",
            "metadata": {"library": library, "found": True, "result_count": 1},
        },
    )
    agent = make_agent(runtime, [tool])
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    _render(agent, memory, "session-1", "Compare Godot knowledge", plain=True)

    turns = memory.load_session("session-1")
    receipts = [
        turn["content"] for turn in turns
        if turn["role"] == "system" and isinstance(turn["content"], dict)
        and turn["content"].get("event") == "research_receipt"
    ]
    assert len(receipts) == 1
    assert receipts[0]["tool"] == "query_knowledge"
    assert receipts[0]["library"] == "godot"
    assert receipts[0]["result_count"] == 1
    assert "PRIVATE GODOT CHUNK" not in str(receipts[0])
    source_answer = list(agent.run("Which sources did you use?"))[0].payload["content"]
    assert "local knowledge" in source_answer
    assert "No retrieval tool was used" not in source_answer


def test_line_chat_persists_provider_state_only_as_model_content(tmp_path):
    provider_message = {
        "role": "assistant",
        "content": "Done.",
        "openai_response_items": [
            {
                "id": "rs_123",
                "type": "reasoning",
                "summary": [],
                "encrypted_content": "opaque-state",
            }
        ],
    }
    agent = make_agent(Runtime([provider_message]), [])
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert _render(agent, memory, "session-1", "finish", plain=True) == "Done."

    assistant = memory.load_session("session-1")[-1]
    assert assistant["content"] == "Done."
    assert assistant["model_content"] == provider_message
    assert "opaque-state" not in str(assistant["content"])


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

        def run(self, _message, *, scope=None):
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

        def run(self, _message, *, scope=None):
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


def test_named_learning_source_gets_bounded_discovery_and_ingestion_capabilities():
    runtime = Runtime([{"role": "assistant", "content": "I will verify the source first."}])
    tools = [
        Tool(name, name, {}, lambda: "ok")
        for name in (
            "web_search",
            "fetch_url",
            "learn_source",
            "request_user_input",
            "write_file",
            "run_shell",
            "git_commit",
        )
    ]
    agent = make_agent(runtime, tools, selector=_select_tool_names)

    list(agent.run("learn from Context7"))

    assert {item["function"]["name"] for item in runtime.requests[0][1]} == {
        "web_search",
        "fetch_url",
        "learn_source",
        "request_user_input",
    }
    assert agent.last_turn_capabilities["callable_tools"] == [
        "fetch_url",
        "learn_source",
        "request_user_input",
        "web_search",
    ]


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


def test_explicit_workspace_inspection_preflights_bounded_evidence():
    runtime = Runtime([{"role": "assistant", "content": "Python is used here."}])
    tool = Tool("workspace_info", "inspect workspace", {}, lambda: "language: Python")
    agent = make_agent(
        runtime,
        [tool],
        selector=lambda *_: ["workspace_info"],
    )

    events = list(agent.run("Inspect this workspace read-only and identify its language."))

    assert [event.kind for event in events[:2]] == ["tool_start", "tool_result"]
    assert events[1].payload["metadata"]["host_preflight"] is True
    assert runtime.requests[0][0][-1]["role"] == "tool"
    assert runtime.requests[0][0][-1]["content"] == "language: Python"
    assert runtime.requests[0][1] == []
    assert agent.last_turn_capabilities["unavailable_tools"]["workspace_info"] == (
        "host preflight already completed"
    )


def test_contextual_storage_followup_retains_bounded_diagnostic_tool():
    runtime = Runtime([{"role": "assistant", "content": "Use storage diagnostics."}])
    tool = Tool("storage_usage", "inspect storage", {}, lambda: "root: 10G")
    agent = make_agent(runtime, [tool], selector=lambda *_: [])
    agent.messages.extend(
        [
            {"role": "user", "content": "How can I inspect disk usage safely?"},
            {
                "role": "assistant",
                "content": "Use read-only storage diagnostics such as df and du.",
            },
        ]
    )

    events = list(agent.run("Run them"))

    assert runtime.requests[0][1] == []
    assert [event.kind for event in events[:2]] == ["tool_start", "tool_result"]
    assert events[1].payload["metadata"]["host_preflight"] is True


def test_contextual_storage_followup_ignores_unavailable_shell_hint_in_scoped_turn():
    runtime = Runtime([{"role": "assistant", "content": "Storage inspected."}])
    tools = [
        Tool("storage_usage", "inspect storage", {}, lambda: "root: 10G"),
        Tool("workspace_info", "inspect workspace", {}, lambda: "workspace"),
        Tool("run_shell", "run shell", {}, lambda: pytest.fail("shell unavailable")),
    ]
    agent = make_agent(runtime, tools, selector=_select_tool_names)
    # Force user-boundary compaction to drop the earlier exchange. The routing
    # decision and required host preflight must survive independently.
    agent.messages[0]["content"] = "system " + ("x" * 20_000)
    agent.messages.extend(
        [
            {"role": "user", "content": "How can I inspect disk usage safely?"},
            {
                "role": "assistant",
                "content": "Use read-only storage diagnostics such as df and du.",
            },
        ]
    )

    events = list(agent.run("Run them", scope=TurnScope.EVALUATION))

    assert [event.kind for event in events[:2]] == ["tool_start", "tool_result"]
    assert events[0].payload["tool"] == "storage_usage"
    assert runtime.requests[0][1] == []


def test_contextual_storage_followup_ignores_negated_mutation_clause():
    runtime = Runtime([{"role": "assistant", "content": "Storage inspected."}])
    tools = [
        Tool("storage_usage", "inspect storage", {}, lambda: "root: 10G"),
        Tool("workspace_info", "inspect workspace", {}, lambda: "workspace"),
        Tool("run_shell", "run shell", {}, lambda: pytest.fail("shell unavailable")),
        Tool("edit_file", "edit", {}, lambda: pytest.fail("editing unavailable")),
    ]
    agent = make_agent(runtime, tools, selector=_select_tool_names)
    agent.messages.extend(
        [
            {"role": "user", "content": "How can I inspect disk usage safely?"},
            {
                "role": "assistant",
                "content": "Use read-only storage diagnostics such as df and du.",
            },
        ]
    )

    events = list(
        agent.run(
            "Run them and summarize the evidence. Do not modify anything.",
            scope=TurnScope.EVALUATION,
        )
    )

    assert [event.kind for event in events[:2]] == ["tool_start", "tool_result"]
    assert events[0].payload["tool"] == "storage_usage"
    assert runtime.requests[0][1] == []


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
