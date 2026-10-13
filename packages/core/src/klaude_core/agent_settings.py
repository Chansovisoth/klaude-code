"""Bounded execution preferences shared by chat, one-shot and settings UI."""

from __future__ import annotations

from typing import Any

EXECUTION_LIMITS = {
    "max_steps": (1, 64),
    "max_tool_calls": (0, 256),
    "max_total_tokens": (0, 2_000_000),
    "max_subagent_concurrency": (0, 4),
}


def public_execution_settings(raw: Any) -> dict[str, int | None]:
    """Only effective governor settings; never provider options or arbitrary data."""
    if not isinstance(raw, dict):
        return {}
    values = {}
    for name, (minimum, maximum) in EXECUTION_LIMITS.items():
        if name not in raw:
            continue
        value = raw[name]
        if value is None or type(value) is int and minimum <= value <= maximum:
            values[name] = value
    return values


def apply_execution_settings(agent: Any, raw: Any) -> None:
    for name, value in public_execution_settings(raw).items():
        if name == "max_steps":
            if value is not None:
                agent.max_steps = value
        elif name == "max_subagent_concurrency":
            agent.max_subagent_concurrency = value or 0
        else:
            # Zero tool calls means Auto. Zero total tokens means no token cap.
            setattr(agent, name, value or None)


def execution_defaults(cfg: Any) -> dict[str, int]:
    return {
        "max_steps": cfg.max_agent_steps,
        "max_tool_calls": cfg.max_agent_tool_calls,
        "max_total_tokens": cfg.max_agent_tokens,
        "max_subagent_concurrency": cfg.max_subagent_concurrency,
    }
