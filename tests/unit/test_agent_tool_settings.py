"""Registry-scoped availability, shared execution paths and navigation owners."""

import json
from types import SimpleNamespace

import pytest
from klaude_cli.main import _apply_tool_availability_preferences
from klaude_cli.settings_panel import PanelRow, PanelState, RowKind, render_body
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.settings_store import update_settings
from klaude_core.tool_settings import tool_groups

from .test_agent_settings import action, controller
from .test_agentic_search import ScriptedOllama, tool_call


def tools_controller(tmp_path):
    item = controller(tmp_path)
    item.host.agent.tools = {
        name: SimpleNamespace(description="Purpose of " + name)
        for name in (
            "read_file",
            "write_file",
            "run_shell",
            "web_search",
            "read_skill",
            "query_knowledge",
            "delegate_task",
            "custom_builtin",
            "mcp__test__read",
        )
    }
    item.host.agent.gate.policies = {"run_shell": "deny", "read_file": "ask"}
    item.host.agent.gate.process_grants = {"read_file"}
    action(item, "tools")
    return item


def test_inventory_uses_only_registered_tools_and_excludes_mcp(tmp_path):
    item = tools_controller(tmp_path)
    assert item.groups() == {
        "WORKSPACE": ("read_file", "write_file", "run_shell"),
        "WEB & RESEARCH": ("web_search",),
        "KNOWLEDGE & SESSIONS": ("query_knowledge", "read_skill"),
        "ORCHESTRATION": ("delegate_task",),
        "OTHER": ("custom_builtin",),
    }
    assert tool_groups({}) == []
    assert "list_dir" not in str(item.page())
    assert "mcp__test__read" not in str(item.page())
    item.host.agent.tools.pop("custom_builtin")
    item.show()
    assert "OTHER" not in str(item.page())


def test_group_mixed_switch_preserves_grants_permissions_and_other_settings(tmp_path):
    item = tools_controller(tmp_path)
    host = item.host
    host.agent.disabled_tool_names = {"mcp__test__read", "host_internal"}
    action(item, "group:WORKSPACE", "WORKSPACE")
    item.toggle_tools(("read_file",), "tool:read_file")
    toggle = next(row for row in item.page().rows if row.id == "group-toggle")
    assert toggle.mixed and toggle.effective_value == "[ ■ ] MIXED"
    action(item, "group-toggle")  # Mixed -> all enabled -> all disabled.
    assert not next(row for row in item.page().rows if row.id == "group-toggle").mixed
    action(item, "group-toggle")
    assert host.agent.disabled_tool_names == {
        "read_file",
        "write_file",
        "run_shell",
        "mcp__test__read",
        "host_internal",
    }
    assert host.agent.gate.policies == {"run_shell": "deny", "read_file": "ask"}
    assert host.agent.gate.process_grants == {"read_file"}
    host._before_render(None)
    saved = json.loads(host.chat_preferences_path.read_text())
    assert saved["tool_availability"] == dict.fromkeys(
        ("read_file", "write_file", "run_shell"), False
    )
    assert "permissions" not in saved and "runtime_options" not in saved
    action(item, "back", "tools")
    assert host._panel.picker.selected_id == "group:WORKSPACE"
    action(item, "reset-tools")
    assert host.agent.disabled_tool_names == {"mcp__test__read", "host_internal"}


def test_group_space_toggle_and_detail_permission_link_restore_exact_selection(tmp_path):
    item = tools_controller(tmp_path)
    host = item.host
    action(item, "group:WORKSPACE", "WORKSPACE")
    host._panel.filter("Run shell")
    host._panel.picker.focus("tool:run_shell")
    host._apply_picker_state()
    host._activate_panel_toggle()
    assert "run_shell" in host.agent.disabled_tool_names
    assert host._panel.picker.query == "run shell"
    host._accept_choice()
    assert item.view == "tool" and item.tool == "run_shell"
    purpose = next(row for row in item.page().rows if row.id == "purpose")
    assert purpose.description == "Purpose of run_shell"
    action(item, "permissions")
    assert host._choice_kind == "permission settings"
    assert host._panel.picker.selected_id == "tool:run_shell"

    host._cancel_choice()
    assert item.visible and item.view == "tool"
    assert host._panel.picker.selected_id == "permissions"
    action(item, "back", "tool-parent")
    assert host._panel.picker.query == "run shell"
    assert host._panel.picker.selected_id == "tool:run_shell"


def test_builtin_reset_is_visible_to_another_clients_save_ack(tmp_path):
    first = tools_controller(tmp_path)
    first.toggle_tools(("read_file",), "tool:read_file")
    first.host._before_render(None)
    second = tools_controller(tmp_path)
    assert not second.host._tool_availability["read_file"]
    action(second, "reset-tools")
    second.host._before_render(None)
    first.show("home")
    action(first, "activity")
    first.host._before_render(None)
    assert first.host._tool_availability["read_file"]
    assert "read_file" not in first.host.agent.disabled_tool_names
    assert first.host.agent.gate.process_grants == {"read_file"}


@pytest.mark.parametrize(
    "owner,kind", [("mcp servers", "mcp settings"), ("skills", "skills settings")]
)
@pytest.mark.parametrize("escape", [False, True])
def test_managed_capability_links_keep_existing_inventory_and_return(tmp_path, owner, kind, escape):
    item = tools_controller(tmp_path)
    item.open()
    action(item, owner)
    host = item.host
    assert host._choice_kind == kind
    if escape:
        host._cancel_choice()
    else:
        host._panel.picker.focus("back")
        host._apply_picker_state()
        host._accept_choice()
    assert item.visible and item.view == "home"
    assert host._panel.picker.selected_id == owner


def test_pending_failed_and_stale_group_saves_keep_live_intent(tmp_path, monkeypatch):
    item = tools_controller(tmp_path)
    host = item.host
    requests = []
    host._settings_writer = SimpleNamespace(
        submit=lambda change: requests.append(change) or len(requests)
    )
    monkeypatch.setattr(
        "klaude_cli.main._load_chat_preferences", lambda *_a: pytest.fail("UI disk read")
    )
    action(item, "group:WORKSPACE", "WORKSPACE")
    action(item, "group-toggle")
    action(item, "group-toggle")
    item.toggle_tools(("read_file",), "tool:read_file")
    host._emit("settings_tools", (1, {"tool_availability": {"read_file": True}}))
    host._emit("settings_saved", (1, True))
    host._emit("settings_saved", (3, False))
    host._before_render(None)
    assert host.agent.disabled_tool_names == {"read_file"}
    assert host._runtime_save_state == "failed"
    assert host._panel.picker.selected_id == "tool:read_file"
    assert requests[-1] == {("tool_availability", "read_file"): False}


@pytest.mark.parametrize("form", ["native", "text"])
def test_disabled_workspace_tool_cannot_be_recovered_from_model_output(tmp_path, form):
    path = tmp_path / "prefs.json"
    update_settings(
        path,
        {
            ("tool_availability", "read_file"): False,
            ("tool_availability", "mcp__test__read"): False,
        },
    )
    attempted = []
    response = (
        tool_call("read_file", path="sample.txt")
        if form == "native"
        else {
            "role": "assistant",
            "content": '<function=read_file>{"path":"sample.txt"}</tool_call>',
        }
    )
    runtime = ScriptedOllama([response, {"role": "assistant", "content": "Read is disabled."}])
    agent = Agent(
        runtime,
        "fake",
        [
            Tool(
                "read_file",
                "Read file",
                {"type": "object", "properties": {"path": {"type": "string"}}},
                lambda **kw: attempted.append(kw) or "private file",
            )
        ],
        PermissionGate({"read_file": "allow"}, lambda *_a: "n"),
        "system",
    )
    _apply_tool_availability_preferences(agent, path)
    list(agent.run("Read sample.txt with read_file, read only."))
    assert not attempted
    assert "mcp__test__read" not in agent.disabled_tool_names
    assert all(not call["tools"] for call in runtime.calls)
    assert len(runtime.calls) == 2  # One bounded recovery request, then the answer.


def test_mixed_toggle_render_has_bounded_width_and_does_not_use_error_color(tmp_path):
    item = tools_controller(tmp_path)
    action(item, "group:WORKSPACE", "WORKSPACE")
    item.toggle_tools(("read_file",), "tool:read_file")
    from prompt_toolkit.utils import get_cwidth

    for width in (40, 80, 120):
        body = render_body(PanelState(item.page()), width)
        assert all(
            get_cwidth("".join(text for _style, text in line)) <= width for line in body.lines
        )
        assert "MIXED" in "".join(text for line in body.lines for _style, text in line)
        assert not any("error" in style for line in body.lines for style, _text in line)
    with pytest.raises(ValueError, match="toggle"):
        PanelRow("bad", RowKind.INFO, "Bad", mixed=True)


def test_live_disable_updates_next_schema_and_capability_snapshot():
    def disable_read():
        agent.disabled_tool_names.add("read_file")
        return "Read disabled during this turn"

    runtime = ScriptedOllama(
        [
            tool_call("workspace_info"),
            tool_call("read_file", path="sample.txt"),
            {"role": "assistant", "content": "Read is disabled."},
        ]
    )
    reads = []
    agent = Agent(
        runtime,
        "fake",
        [
            Tool("workspace_info", "Inspect workspace", {"type": "object"}, disable_read),
            Tool("read_file", "Read", {"type": "object"}, lambda **kw: reads.append(kw)),
        ],
        PermissionGate({"workspace_info": "allow", "read_file": "allow"}, lambda *_a: "n"),
        "system",
        tool_selector=lambda _message, available: list(available),
    )
    list(agent.run("Inspect the repository, read only."))
    assert not reads
    assert "read_file" not in {
        schema["function"]["name"] for call in runtime.calls[1:] for schema in call["tools"]
    }
    assert agent.last_turn_capabilities["unavailable_tools"]["read_file"] == "disabled in settings"


def test_delegation_rechecks_live_availability_even_with_old_parent_snapshot(monkeypatch):
    from klaude_core import SubagentTask, SubagentWorkerOutput, supervise_agent_tasks

    runtime = ScriptedOllama([])
    parent = Agent(
        runtime,
        "fake",
        [
            Tool("read_file", "Read file", {"type": "object"}, lambda **_kw: "private file"),
        ],
        PermissionGate({"read_file": "allow"}, lambda *_a: "n"),
        "system",
    )
    parent.last_turn_capabilities = {"callable_tools": ["read_file"]}
    parent.disabled_tool_names = {"read_file"}
    assignments = []

    def worker(_parent, assignment):
        assignments.append(assignment)
        return SubagentWorkerOutput("No reads available")

    monkeypatch.setattr("klaude_core.subagents.run_agent_assignment", worker)
    supervise_agent_tasks(
        parent, [SubagentTask("Inspect repository", requested_tools=("read_file",))]
    )
    assert len(assignments) == 1 and assignments[0].callable_tools == ()
    assert dict(assignments[0].unavailable_tools)["read_file"] == "not callable by parent turn"
