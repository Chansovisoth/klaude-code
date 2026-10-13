"""Execution controls share the actual governor across chat and one-shot paths."""

import json
from types import SimpleNamespace

import pytest
from klaude_cli.main import _apply_runtime_preferences, _load_runtime_preferences
from klaude_cli.settings_panel import PanelAction
from klaude_cli.settings_writer import public_tool_settings
from klaude_core.agent_settings import (
    EXECUTION_LIMITS,
    apply_execution_settings,
    public_execution_settings,
)
from klaude_core.execution import TurnGovernor
from klaude_core.settings_store import update_settings

from .test_cli_commands import _fake_persistent_tui


def controller(tmp_path):
    host = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
    host._open_settings_category("agent tools")
    return host._agent_settings


def action(item, kind, target=""):
    item.action(PanelAction("agent-settings-" + kind, target))


def test_execution_metadata_is_bounded_and_excludes_provider_options():
    assert (
        public_execution_settings(
            {
                "max_steps": True,
                "max_tool_calls": 257,
                "max_total_tokens": "100",
                "max_subagent_concurrency": -1,
                "key": "private-canary",
                "num_ctx": 8192,
            }
        )
        == {}
    )
    assert public_execution_settings(None) == {}
    for name, (minimum, maximum) in EXECUTION_LIMITS.items():
        assert public_execution_settings({name: maximum}) == {name: maximum}
        assert public_execution_settings({name: minimum - 1}) == {}
        assert public_execution_settings({name: None}) == {name: None}
    assert public_tool_settings({"runtime_options": {"max_tool_calls": 8, "key": "secret"}}) == {
        "execution_settings": {"max_tool_calls": 8}
    }
    assert public_tool_settings({}) == {}


def test_existing_execution_preferences_load_without_leaking_into_ollama(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(
        json.dumps(
            {
                "runtime_options": {
                    "max_steps": 31,
                    "max_tool_calls": 0,
                    "max_total_tokens": 0,
                    "max_subagent_concurrency": 3,
                    "num_ctx": 4096,
                }
            }
        )
    )
    preferences = _load_runtime_preferences(path)
    agent = SimpleNamespace(ollama_options={}, max_steps=20)
    _apply_runtime_preferences(agent, preferences)
    assert agent.max_steps == 31
    assert agent.max_tool_calls is None
    assert agent.max_total_tokens is None
    assert agent.max_subagent_concurrency == 3
    assert agent.ollama_options == {"num_ctx": 4096}


@pytest.mark.parametrize("steps,expected", [(1, 4), (12, 24), (20, 40), (64, 128)])
def test_auto_tool_call_display_matches_governor_and_has_no_unlimited(tmp_path, steps, expected):
    item = controller(tmp_path)
    item.host.agent.max_steps = steps
    item.host.agent.max_tool_calls = None
    action(item, "calls")
    page = item.page()
    assert f"{expected} calls effective" in page.rows[0].description
    assert "Unlimited" not in str(page)
    assert TurnGovernor(steps).max_tool_calls == expected


@pytest.mark.parametrize(
    "source,backend,expected",
    [("Local", "ollama", 1), ("Cloud", "openai_compatible", 1), ("Cloud", "openai_api", 2)],
)
def test_workers_auto_choice_ignores_current_custom_value(tmp_path, source, backend, expected):
    item = controller(tmp_path)
    item.host.agent.model_info = SimpleNamespace(source=source, backend=backend)
    item.host.agent.max_subagent_concurrency = 4
    action(item, "workers")
    assert item.page().rows[0].description.startswith(f"{expected} effective")
    assert item.page().rows[4].value == "Current"
    action(item, "choose:0", "0")
    assert item.worker_count() == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("steps", "0"),
        ("steps", "65"),
        ("calls", "0"),
        ("calls", "257"),
        ("tokens", "2000001"),
        ("tokens", "-1"),
        ("steps", "3.5"),
        ("tokens", "abc"),
    ],
)
def test_custom_limits_reject_invalid_input_in_private_editor(tmp_path, field, value):
    item = controller(tmp_path)
    host = item.host
    original = host.agent.max_steps
    action(item, field)
    action(item, "custom")
    assert host._settings_input_is_single_line()
    host._answer_settings_input(value)
    assert host._settings_input_request is not None
    assert "whole number" in host.status_error
    assert host.agent.max_steps == original
    assert not host.chat_preferences_path.exists()
    host._answer_settings_input(None)
    assert host._settings_input_request is None
    assert item.view == field
    assert host.agent.messages == [{"role": "system", "content": "system prompt"}]


def test_scoped_resets_preserve_device_tools_permissions_and_other_limits(tmp_path):
    item = controller(tmp_path)
    host = item.host
    update_settings(
        host.chat_preferences_path,
        {
            ("runtime_options", "num_ctx"): 16384,
            ("tool_availability", "web_search"): False,
            ("permissions", "read_file"): "deny",
        },
    )
    item.set_value("steps", 31)
    item.set_value("calls", 7)
    item.set_value("tokens", 5000)
    item.set_value("workers", 3)
    action(item, "calls")
    action(item, "reset-field")
    saved = json.loads(host.chat_preferences_path.read_text())
    assert saved["runtime_options"] == {
        "num_ctx": 16384,
        "max_steps": 31,
        "max_total_tokens": 5000,
        "max_subagent_concurrency": 3,
    }
    action(item, "execution")
    action(item, "reset")
    host._before_render(None)
    saved = json.loads(host.chat_preferences_path.read_text())
    assert saved["runtime_options"] == {"num_ctx": 16384}
    assert saved["tool_availability"] == {"web_search": False}
    assert saved["permissions"] == {"read_file": "deny"}
    assert host.agent.max_steps == host.cfg.max_agent_steps
    assert host.agent.max_tool_calls is None
    assert host.agent.max_total_tokens is None


def test_runtime_reset_preserves_execution_settings(tmp_path):
    item = controller(tmp_path)
    host = item.host
    item.set_value("steps", 31)
    item.set_value("calls", 7)
    item.set_value("tokens", 5000)
    item.set_value("workers", 3)
    host.agent.ollama_options.update(num_gpu=0, num_thread=8)
    host._open_settings_category("runtime", "reset to default")
    host._accept_choice()
    host._before_render(None)
    saved = json.loads(host.chat_preferences_path.read_text())["runtime_options"]
    assert {key: saved[key] for key in EXECUTION_LIMITS} == {
        "max_steps": 31,
        "max_tool_calls": 7,
        "max_total_tokens": 5000,
        "max_subagent_concurrency": 3,
    }
    assert host.agent.max_steps == 31
    assert host.agent.max_subagent_concurrency == 3


def test_existing_tools_back_and_escape_return_to_agent_tools(tmp_path):
    item = controller(tmp_path)
    action(item, "tools")
    assert item.host._choice_kind == "agent settings tools"
    item.host._cancel_choice()
    assert item.visible
    assert item.host._panel.picker.selected_id == "tools"
    action(item, "tools")
    item.host._choice_index = item.host._choice_values.index("Back")
    item.host._accept_choice()
    assert item.visible
    assert item.host._panel.picker.selected_id == "tools"


def test_navigation_and_failed_save_keep_live_intent_filter_and_focus(tmp_path, monkeypatch):
    item = controller(tmp_path)
    host = item.host
    monkeypatch.setattr(
        "klaude_cli.main._load_chat_preferences",
        lambda _path: pytest.fail("Navigation must use live state"),
    )
    host.chat_preferences_path.write_text("corrupt JSON")
    action(item, "execution")
    host._panel.picker.query = "Tool-call"
    host._panel.search_active = True
    item.set_value("calls", 9)
    host._before_render(None)
    assert host.agent.max_tool_calls == 9
    assert host._runtime_save_state == "failed"
    assert host._panel.picker.selected_id == "calls"
    assert host._panel.picker.query == "Tool-call"
    assert host.chat_preferences_path.read_text() == "corrupt JSON"


def test_cross_client_save_merges_limits_and_ignores_stale_acknowledgement(tmp_path):
    item = controller(tmp_path)
    host = item.host
    item.set_value("steps", 31)
    # Another client saves a disjoint field before this client makes its next edit.
    update_settings(host.chat_preferences_path, {("runtime_options", "max_total_tokens"): 5000})
    item.set_value("calls", 7)
    host._before_render(None)
    assert host.agent.max_steps == 31
    assert host.agent.max_tool_calls == 7
    assert host.agent.max_total_tokens == 5000
    revision = host._runtime_save_revision
    host._emit("settings_tools", (revision - 1, {"execution_settings": {"max_steps": 12}}))
    host._before_render(None)
    assert host.agent.max_steps == 31


def test_budget_snapshot_is_not_changed_by_settings_mid_turn(tmp_path):
    item = controller(tmp_path)
    governor = TurnGovernor(20, max_tool_calls=40)
    item.host.agent.active_turn_governor = governor
    item.set_value("steps", 12)
    item.set_value("calls", 3)
    assert governor.max_model_steps == 20
    assert governor.max_tool_calls == 40
    following = TurnGovernor(
        item.host.agent.max_steps, max_tool_calls=item.host.agent.max_tool_calls
    )
    assert following.max_model_steps == 12
    assert following.max_tool_calls == 3


def test_advanced_reports_missing_usage_without_guessing(tmp_path):
    item = controller(tmp_path)
    governor = TurnGovernor(20, max_total_tokens=1000)
    governor.observe_model_usage(None)
    item.host.agent.last_turn_budget = governor.snapshot().to_dict()
    action(item, "advanced")
    assert next(row.value for row in item.page().rows if row.id == "unknown") == "1 requests"
    assert next(row.value for row in item.page().rows if row.id == "usage") == "0 reported tokens"


def test_visible_advanced_usage_refresh_preserves_filter_and_focus(tmp_path):
    item = controller(tmp_path)
    action(item, "advanced")
    host = item.host
    host._panel.picker.query = "Total token"
    host._panel.picker.focus("tokens")
    host._panel.search_active = True
    host.agent.last_turn_budget = {"total_tokens_used": 140, "token_usage_unknown_requests": 2}
    host._before_render(None)
    assert next(row.value for row in host._panel.page.rows if row.id == "usage") == (
        "140 reported tokens"
    )
    assert host._panel.picker.query == "Total token"
    assert host._panel.picker.selected_id == "tokens"


def test_failed_custom_save_retry_does_not_leave_number_in_chat_draft(tmp_path):
    item = controller(tmp_path)
    host = item.host
    host.chat_preferences_path.write_text("corrupt JSON")
    action(item, "execution")
    action(item, "calls")
    action(item, "custom")
    host._set_input("9")
    host._submit_settings_input_response()
    host._before_render(None)
    assert host.agent.max_tool_calls == 9
    host.chat_preferences_path.write_text("{}")
    action(item, "calls")
    action(item, "custom")
    host._set_input("1")
    host._submit_settings_input_response()
    host._before_render(None)
    assert host.agent.max_tool_calls == 1
    for _ in range(6):
        if host._choice_kind is None:
            break
        host._cancel_choice()
    assert host._choice_kind is None
    assert host.input.text == ""


def test_private_number_is_not_captured_if_panel_draft_is_unset(tmp_path):
    item = controller(tmp_path)
    host = item.host
    action(item, "execution")
    action(item, "calls")
    action(item, "custom")
    host._panel_composer_draft = None
    host._set_input("9")
    host._submit_settings_input_response()
    assert host._panel_composer_draft == ("", [])
    for _ in range(6):
        if host._choice_kind is None:
            break
        host._cancel_choice()
    assert host.input.text == ""


def test_shared_agent_factory_applies_saved_governor_before_first_request(tmp_path, monkeypatch):
    from klaude_cli import main
    from klaude_core import config

    from .test_agentic_search import ScriptedOllama

    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(main, "_runtime_context_result", lambda *_a: None)
    monkeypatch.setattr(main, "_configured_mcp_tools", lambda *_a: [])
    update_settings(
        config.DATA_DIR / "chat-preferences.json",
        {
            ("runtime_options", "max_steps"): 12,
            ("runtime_options", "max_tool_calls"): 1,
            ("runtime_options", "max_total_tokens"): 5000,
            ("runtime_options", "max_subagent_concurrency"): 3,
        },
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sample.txt").write_text("workspace content")
    agent, _memory = main._build_agent(workspace)
    assert (agent.max_steps, agent.max_tool_calls, agent.max_total_tokens) == (12, 1, 5000)
    assert agent.max_subagent_concurrency == 3
    assert not set(EXECUTION_LIMITS) & agent.ollama_options.keys()
    agent.ollama = ScriptedOllama(
        [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "read-first", "function": {
                        "name": "read_file", "arguments": {"path": "sample.txt"}}},
                    {"id": "read-second", "function": {
                        "name": "read_file", "arguments": {"path": "sample.txt"}}},
                ],
            },
            {"role": "assistant", "content": "Read once; the remaining read was skipped."},
        ]
    )
    events = list(agent.run("Read sample.txt, read only; do not edit files."))
    assert not any(event.kind == "error" for event in events)
    assert agent.last_turn_budget["tool_calls_used"] == 1
    assert agent.last_turn_budget["max_tool_calls"] == 1
    assert len(agent.ollama.calls) == 2
    results = [msg for msg in agent.ollama.calls[1]["messages"] if msg["role"] == "tool"]
    assert [msg["tool_call_id"] for msg in results] == ["read-first", "read-second"]
    assert "workspace content" in results[0]["content"]
    assert "skipped execution governor" in results[1]["content"]
    main._close_agent_mcp(agent)


def test_none_step_preference_keeps_configured_default():
    agent = SimpleNamespace(max_steps=31)
    apply_execution_settings(agent, {"max_steps": None})
    assert agent.max_steps == 31


def test_step_edit_during_host_preflight_keeps_current_turn_budget():
    from klaude_core import Agent, PermissionGate, Tool

    from .test_agentic_search import ScriptedOllama, tool_call

    def inspect_workspace():
        apply_execution_settings(agent, {"max_steps": 1})
        return "Workspace contains notes.txt"

    runtime = ScriptedOllama(
        [
            tool_call("read_file", path="notes.txt"),
            {"role": "assistant", "content": "Inspected the workspace and read the notes."},
        ]
    )
    agent = Agent(
        runtime,
        "test",
        [
            Tool("workspace_info", "Inspect workspace", {"type": "object"}, inspect_workspace),
            Tool("read_file", "Read notes", {"type": "object"}, lambda **_kw: "Useful notes"),
        ],
        PermissionGate({"workspace_info": "allow", "read_file": "allow"}, lambda *_a: "n"),
        "system",
        max_steps=3,
        tool_selector=lambda _message, available: list(available),
    )
    events = list(agent.run("Inspect the current workspace without changing any files."))
    assert agent.max_steps == 1
    assert agent.last_turn_budget["max_model_steps"] == 3
    assert agent.last_turn_budget["model_steps_used"] == 2
    assert not any(event.kind == "error" for event in events)


def test_token_cap_on_required_file_read_fails_without_wasteful_retry():
    from klaude_core import Agent, PermissionGate, Tool

    from .test_agentic_search import ScriptedOllama

    class TokenRuntime(ScriptedOllama):
        last_chat_metadata = {}

        def chat(self, *args, **kwargs):
            response = super().chat(*args, **kwargs)
            self.last_chat_metadata = {"usage": {"input_tokens": 50, "output_tokens": 20}}
            return response

    runtime = TokenRuntime([
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "first", "function": {
                "name": "read_file", "arguments": {"path": "sample.txt"}}},
            {"id": "second", "function": {
                "name": "read_file", "arguments": {"path": "sample.txt"}}},
        ]},
        {"role": "assistant", "content": "Token budget stopped the reads."},
    ])
    reads = []
    agent = Agent(
        runtime, "test", [Tool(
            "read_file", "Read file", {"type": "object"},
            lambda path: reads.append(path) or "file content",
        )], PermissionGate({"read_file": "allow"}, lambda *_a: "n"),
        "system", max_total_tokens=60,
        tool_selector=lambda _message, available: list(available),
    )
    events = list(agent.run("Read sample.txt, read only; do not edit files or run shell."))
    assert reads == []
    assert len(runtime.calls) == 2
    results = [msg for msg in runtime.calls[1]["messages"] if msg["role"] == "tool"]
    assert [msg["tool_call_id"] for msg in results] == ["first", "second"]
    assert all("skipped execution governor" in msg["content"] for msg in results)
    assert agent.last_turn_budget["tool_calls_used"] == 0
    assert any("requested read_file could not run: token budget reached"
               in event.payload.get("message", "") for event in events if event.kind == "error")
    assert not any(event.kind == "retry" for event in events)
