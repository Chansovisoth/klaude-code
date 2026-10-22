"""One small adapter around the existing synchronous Agent generator."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from klaude_core import Agent, AgentEvent, TurnScope

from .activity import Activity, classify_activity, tool_outcome
from .contracts import EventKind, PublicEvent
from .inspection import tool_inspection


def iter_agent_events(
    agent: Agent, message: str | dict[str, Any], *,
    scope: TurnScope | str | None = None,
    on_activity: Callable[[PublicEvent], None] | None = None,
) -> Iterator[AgentEvent]:
    """Close provider generators on cancellation or consumer failure."""
    pending: dict[str, tuple[str, str]] = {}
    inspections: dict[str, dict[str, Any]] = {}
    previous_execution = getattr(agent, "execution_observer", None)
    responding = False

    def publish(kind: EventKind, **fields: Any) -> None:
        if on_activity is not None:
            on_activity(PublicEvent(kind, "", "", 0, **fields))

    def started(tool: str, identity: str) -> None:
        if previous_execution is not None:
            previous_execution(tool, identity)
        publish("tool.started", tool=tool, execution_id=identity,
                activity=pending.get(identity, (tool, Activity.WAITING.value))[1])

    if on_activity is not None:
        agent.execution_observer = started
    events = None
    try:
        events = agent.run(message, scope=scope)
        publish("activity.changed", activity=Activity.GENERATING_RESPONSE.value)
        for event in events:
            payload = event.payload
            metadata = payload.get("metadata") or {}
            if event.kind == "tool_start":
                tool = str(payload.get("tool") or "")
                identity = str(payload.get("execution_id") or "")
                activity = classify_activity(tool, payload.get("args") or {}, metadata).value
                pending[identity] = (tool, activity)
                inspections[identity] = tool_inspection(
                    agent, tool, payload.get("args") or {}, metadata)
                responding = False
                publish("tool.requested", tool=tool, execution_id=identity, activity=activity,
                        inspection=inspections[identity])
            elif event.kind == "tool_result":
                identity = str(metadata.get("execution_id") or "")
                pending.pop(identity, None)
                publish("tool.finished", tool=str(payload.get("tool") or ""),
                        execution_id=identity, executed=metadata.get("executed") is True,
                        status=tool_outcome(payload.get("result", ""), metadata),
                        inspection={**inspections.pop(identity, {}),
                                    **tool_inspection(
                                        agent, str(payload.get("tool") or ""), {}, metadata)})
            elif event.kind in {"text", "text_delta"} and payload.get("content"):
                identity = str(metadata.get("execution_id") or "")
                if identity:
                    tool, _ = pending.pop(identity, ("", ""))
                    publish("tool.finished", tool=tool, execution_id=identity,
                            executed=metadata.get("executed") is True,
                            status=tool_outcome(payload["content"], metadata),
                            inspection=inspections.pop(identity, {}))
                if not responding:
                    publish("activity.changed", activity=Activity.GENERATING_RESPONSE.value)
                    responding = True
            yield event
    finally:
        if on_activity is not None:
            agent.execution_observer = previous_execution
        close = getattr(events, "close", None)
        if callable(close):
            close()
