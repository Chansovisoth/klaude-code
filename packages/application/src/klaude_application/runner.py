"""One small adapter around the existing synchronous Agent generator."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from klaude_core import Agent, AgentEvent, TurnScope


def iter_agent_events(
    agent: Agent, message: str | dict[str, Any], *,
    scope: TurnScope | str | None = None,
) -> Iterator[AgentEvent]:
    """Close provider generators on cancellation or consumer failure."""
    events = agent.run(message, scope=scope)
    try:
        yield from events
    finally:
        close = getattr(events, "close", None)
        if callable(close):
            close()
