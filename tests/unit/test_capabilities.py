from dataclasses import FrozenInstanceError

import pytest
from klaude_core.capabilities import TurnCapabilities
from klaude_core.execution import TurnBudgetSnapshot


def budget() -> TurnBudgetSnapshot:
    return TurnBudgetSnapshot(
        max_model_steps=20,
        model_steps_used=2,
        max_tool_calls=40,
        tool_calls_used=3,
        max_elapsed_seconds=1_800,
        elapsed_seconds=4.5,
        no_progress_streak=0,
        max_no_progress=3,
    )


def test_capability_snapshot_is_sorted_immutable_and_serializable():
    snapshot = TurnCapabilities.create(
        globally_enabled_tools={"write_file", "read_file"},
        callable_tools={"read_file"},
        unavailable_tools={"write_file": "permission policy deny"},
        effective_permissions={"write_file": "deny", "read_file": "allow"},
        hard_constraints=["Use only supplied schemas.", "Use only supplied schemas."],
        provider_backend="ollama",
        provider_model="qwen",
        provider_supports_tools=True,
        provider_context_window=8_192,
        provider_effort_levels=("low", "medium", "high"),
        injected_instructions=("/repo/AGENTS.md",),
        instructions_truncated=False,
        plan_mode=False,
        workspace_write_enabled=True,
        budget=budget(),
    )

    assert snapshot.globally_enabled_tools == ("read_file", "write_file")
    assert snapshot.callable_tools == ("read_file",)
    assert snapshot.to_dict()["unavailable_tools"] == {
        "write_file": "permission policy deny"
    }
    assert snapshot.hard_constraints == ("Use only supplied schemas.",)
    assert snapshot.to_dict()["provider"]["context_window"] == 8_192
    assert snapshot.injected_instructions == ("/repo/AGENTS.md",)
    with pytest.raises(FrozenInstanceError):
        snapshot.plan_mode = True  # type: ignore[misc]


def test_capability_prompt_distinguishes_registry_callable_and_denied_tools():
    snapshot = TurnCapabilities.create(
        globally_enabled_tools={"read_file", "write_file"},
        callable_tools={"read_file"},
        unavailable_tools={"write_file": "permission policy deny"},
        effective_permissions={"read_file": "ask", "write_file": "deny"},
        hard_constraints=["Permissions never override the workspace jail."],
        provider_backend="openai_codex",
        provider_model="gpt-5.5",
        provider_supports_tools=True,
        provider_context_window=200_000,
        provider_effort_levels=("low", "medium", "high"),
        injected_instructions=("/repo/AGENTS.md",),
        instructions_truncated=True,
        plan_mode=False,
        workspace_write_enabled=True,
        budget=budget(),
    )

    rendered = snapshot.render_for_model()
    assert "Globally enabled registry: read_file, write_file" in rendered
    assert "Provider: openai_codex/gpt-5.5" in rendered
    assert "Injected repository instructions: /repo/AGENTS.md (bounded)" in rendered
    assert "Callable this request: read_file" in rendered
    assert '"write_file": "permission policy deny"' in rendered
    assert "ASK=read_file" in rendered
    assert "DENY=write_file" in rendered
    assert "2/20 model steps and 3/40 tool calls used" in rendered
