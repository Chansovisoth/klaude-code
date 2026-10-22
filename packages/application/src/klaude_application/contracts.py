"""Bounded, explicit public contracts for the first in-process bridge slice."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EventKind = Literal[
    "turn.accepted", "turn.started", "message.delta", "message.completed", "tool.requested",
    "tool.started", "tool.finished", "approval.required", "approval.resolved",
    "user_input.required", "user_input.resolved", "turn.completed",
    "turn.partial", "turn.failed", "turn.cancelled", "turn.interrupted",
    "queue.changed", "settings.changed", "stream.reset_required", "activity.changed",
]


@dataclass(frozen=True)
class PublicEvent:
    kind: EventKind
    session_id: str
    turn_id: str
    sequence: int
    text: str = ""
    tool: str = ""
    execution_id: str = ""
    interaction_id: str = ""
    message_id: str = ""
    offset: int = 0
    executed: bool | None = None
    status: str = ""
    cursor: str = ""
    activity: str = ""
    inspection: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TurnReceipt:
    request_id: str
    session_id: str
    turn_id: str
    state: Literal[
        "running", "completed", "partial", "failed", "cancelled", "interrupted", "gone"
    ]


@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    session_id: str
    turn_id: str
    execution_id: str
    tool: str
    expires_at: float
    # Exact arguments stay private in the broker. This initial public contract
    # intentionally does not echo a tool's possibly credential-bearing detail.


@dataclass(frozen=True)
class UserInputRequest:
    id: str
    session_id: str
    turn_id: str
    question: str
    header: str
    options: tuple[str, ...]
    expires_at: float
