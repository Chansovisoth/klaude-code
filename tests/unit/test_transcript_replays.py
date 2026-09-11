"""Offline transcript replays for cross-layer agent behavior contracts."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from klaude_cli.main import _select_tool_names
from klaude_core import Agent, ModelCapabilities, ModelInfo, PermissionGate, Tool


class ReplayRuntime:
    def __init__(self) -> None:
        self.requests: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []

    def chat(self, _model, messages, tools=None, **_kwargs):
        self.requests.append((messages, list(tools or [])))
        return {"role": "assistant", "content": "Replay completed."}


TOOL_NAMES = (
    "read_file",
    "list_dir",
    "grep",
    "workspace_info",
    "storage_usage",
    "write_file",
    "edit_file",
    "run_shell",
    "git_status",
    "git_diff",
    "git_commit",
    "web_search",
    "fetch_url",
    "http_probe",
    "query_knowledge",
    "request_user_input",
)

MODEL_PROFILES = (
    {
        "name": "constrained-local",
        "backend": "ollama",
        "model": "small-local",
        "context_window": 8_192,
        "supports_tools": True,
    },
    {
        "name": "default-local-coder",
        "backend": "ollama",
        "model": "default-coder",
        "context_window": 32_768,
        "supports_tools": True,
    },
    {
        "name": "general-cloud",
        "backend": "openai_api",
        "model": "general-cloud",
        "context_window": 128_000,
        "supports_tools": True,
    },
    {
        "name": "codex-authenticated",
        "backend": "openai_codex",
        "model": "codex-cloud",
        "context_window": 128_000,
        "supports_tools": True,
    },
    {
        "name": "tool-less-model",
        "backend": "ollama",
        "model": "text-only-local",
        "context_window": 4_096,
        "supports_tools": False,
    },
)


def replay_cases() -> list[dict[str, Any]]:
    path = Path(__file__).with_name("fixtures") / "transcript_replays.json"
    return json.loads(path.read_text())


@pytest.mark.parametrize("profile", MODEL_PROFILES, ids=lambda profile: profile["name"])
@pytest.mark.parametrize("case", replay_cases(), ids=lambda case: case["name"])
def test_transcript_replay_keeps_schemas_prompt_and_completion_in_sync(case, profile):
    runtime = ReplayRuntime()
    tools = [Tool(name, name.replace("_", " "), {}, lambda: "ok") for name in TOOL_NAMES]
    agent = Agent(
        runtime,
        "replay-model",
        tools,
        PermissionGate({name: "allow" for name in TOOL_NAMES}, lambda *_: "n"),
        "system",
        tool_selector=_select_tool_names,
        model_info=ModelInfo(
            profile["backend"],
            profile["model"],
            profile["name"],
            capabilities=ModelCapabilities(
                context_window=profile["context_window"],
                supports_tools=profile["supports_tools"],
            ),
        ),
    )
    agent.workspace = SimpleNamespace(write_enabled=True)
    agent.messages.extend(case["prior_messages"])

    events = list(agent.run(case["user"]))

    schemas = {item["function"]["name"] for item in runtime.requests[0][1]}
    snapshot = agent.last_turn_capabilities
    assert schemas == set(snapshot["callable_tools"])
    if profile["supports_tools"]:
        assert set(case["expected_tools"]) <= schemas
    else:
        assert schemas == set()
        assert set(case["expected_tools"]) <= set(snapshot["unavailable_tools"])
        assert all(
            snapshot["unavailable_tools"][name]
            == "selected provider/model does not support tool calling"
            for name in case["expected_tools"]
        )
    assert set(case["forbidden_tools"]).isdisjoint(schemas)
    assert events[-1].payload["turn_capabilities"] == snapshot
    assert events[-1].kind == "done"
    assert len(runtime.requests) == 1
    assert snapshot["provider"] == {
        "backend": profile["backend"],
        "model": profile["model"],
        "supports_tools": profile["supports_tools"],
        "context_window": profile["context_window"],
        "effort_levels": ["off", "low", "medium", "high"],
    }
    prompt = runtime.requests[0][0][0]["content"]
    assert "Callable this request: " + ", ".join(sorted(schemas)) in prompt


def test_provider_change_keeps_public_conversation_and_refreshes_capabilities():
    local = ReplayRuntime()
    cloud = ReplayRuntime()
    agent = Agent(
        local,
        "local-model",
        [],
        PermissionGate({}, lambda *_: "n"),
        "system",
        model_info=ModelInfo("ollama", "local-model", "Local model"),
    )
    list(agent.run("Remember that the target is parser.py"))

    agent.runtime = cloud
    agent.ollama = cloud
    agent.model = "cloud-model"
    agent.model_info = ModelInfo(
        "openai_codex",
        "cloud-model",
        "Cloud model",
        capabilities=ModelCapabilities(context_window=200_000),
    )
    list(agent.run("Which file did I name?"))

    cloud_messages = cloud.requests[0][0]
    public_content = [
        message["content"]
        for message in cloud_messages
        if message.get("role") in {"user", "assistant"}
    ]
    assert public_content == [
        "Remember that the target is parser.py",
        "Replay completed.",
        "Which file did I name?",
    ]
    assert agent.last_turn_capabilities["provider"]["backend"] == "openai_codex"
    assert agent.last_turn_capabilities["provider"]["model"] == "cloud-model"
    assert agent.last_turn_capabilities["provider"]["context_window"] == 200_000
