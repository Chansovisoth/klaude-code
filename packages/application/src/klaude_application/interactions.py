"""Cancellable in-process approval and user-input broker."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from klaude_core import Tool

from .contracts import ApprovalRequest, UserInputRequest

USER_INPUT_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "header": {"type": "string", "maxLength": 80},
        "question": {"type": "string", "maxLength": 1000},
        "options": {
            "type": "array", "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "maxLength": 120},
                    "description": {"type": "string", "maxLength": 240},
                },
                "required": ["label"],
            },
        },
    },
    "required": ["question"],
}


@dataclass
class _Waiter:
    public: ApprovalRequest | UserInputRequest
    arguments: dict[str, Any] = field(default_factory=dict, repr=False)
    answered: threading.Event = field(default_factory=threading.Event, repr=False)
    answer: str | None = None


class InteractionBroker:
    """The worker blocks, while a different caller can answer by exact ID."""

    def __init__(
        self,
        session_id: str,
        turn_id: str,
        cancelled: threading.Event,
        emit: Callable[[str, str, str], None],
        *,
        timeout: float = 300,
    ) -> None:
        self.session_id = session_id
        self.turn_id = turn_id
        self.cancelled = cancelled
        self.emit = emit
        self.timeout = timeout
        self._lock = threading.Lock()
        self._pending: dict[str, _Waiter] = {}
        self._closed = False

    def _await(self, waiter: _Waiter) -> str | None:
        deadline = waiter.public.expires_at
        while not waiter.answered.wait(min(0.1, max(0, deadline - time.time()))):
            if self.cancelled.is_set() or time.time() >= deadline:
                break
        with self._lock:
            self._pending.pop(waiter.public.id, None)
        if self.cancelled.is_set() or time.time() >= deadline:
            return None
        return waiter.answer

    def ask_permission(self, tool: str, _detail: str, request: dict[str, Any]) -> str:
        if self.cancelled.is_set():
            return "n"
        public = ApprovalRequest(
            uuid.uuid4().hex, self.session_id, self.turn_id,
            str(request.get("execution_id", "")), tool, time.time() + self.timeout,
        )
        waiter = _Waiter(public, dict(request.get("arguments") or {}))
        with self._lock:
            if self._closed:
                return "n"
            self._pending[public.id] = waiter
        self.emit("approval.required", public.id, tool)
        answer = self._await(waiter)
        self.emit("approval.resolved", public.id, tool)
        return "y" if answer == "allow_once" else "n"

    def request_input(
        self, question: str, options: object = None, header: str = "",
    ) -> str:
        clean_question = " ".join(str(question).split())[:1000]
        if not clean_question:
            return json.dumps({"status": "error", "message": "question is required"})
        labels: list[str] = []
        if isinstance(options, list):
            for raw in options[:8]:
                if isinstance(raw, str):
                    label = raw
                elif isinstance(raw, dict):
                    label = raw.get("label", "")
                else:
                    label = ""
                label = " ".join(str(label or "").split())[:120]
                if label and label not in labels:
                    labels.append(label)
        public = UserInputRequest(
            uuid.uuid4().hex, self.session_id, self.turn_id, clean_question,
            " ".join(str(header).split())[:80], tuple(labels), time.time() + self.timeout,
        )
        waiter = _Waiter(public)
        with self._lock:
            if self._closed:
                return json.dumps({"status": "cancelled"})
            self._pending[public.id] = waiter
        self.emit("user_input.required", public.id, "")
        answer = self._await(waiter)
        self.emit("user_input.resolved", public.id, "")
        if answer is None:
            return json.dumps({"status": "cancelled"})
        source = "option" if answer in labels else "custom"
        return json.dumps({"status": "answered", "answer": answer, "source": source})

    def pending(self) -> tuple[ApprovalRequest | UserInputRequest, ...]:
        with self._lock:
            return tuple(waiter.public for waiter in self._pending.values())

    def review(self, identity: str) -> dict[str, str] | None:
        """Bounded exact read-tool arguments for the controlling client's review."""
        with self._lock:
            waiter = self._pending.get(identity)
            if (waiter is None or waiter.answered.is_set()
                    or time.time() >= waiter.public.expires_at
                    or not isinstance(waiter.public, ApprovalRequest)):
                return None
            arguments = waiter.arguments
            fields = []
            for key in ("path", "pattern", "offset", "limit"):
                value = arguments.get(key)
                if isinstance(value, (str, int)) and not isinstance(value, bool):
                    clean = "".join(char if char.isprintable() else " " for char in str(value))
                    fields.append(f"{key}={clean[:400]}")
            if waiter.public.tool in {"write_file", "edit_file"}:
                for key in (("content",) if waiter.public.tool == "write_file"
                            else ("old_str", "new_str")):
                    value = arguments.get(key)
                    if isinstance(value, str):
                        digest = hashlib.sha256(value.encode()).hexdigest()
                        preview = "".join(char if char.isprintable() or char == "\n" else " "
                                          for char in value[:1600])
                        suffix = "\n...[truncated]" if len(value) > 1600 else ""
                        fields.append(
                            f"{key}: {len(value)} chars, sha256={digest}\n{preview}{suffix}"
                        )
                return {"tool": waiter.public.tool, "detail": "\n".join(fields)[:5000]}
            return {"tool": waiter.public.tool, "detail": ", ".join(fields)[:800]}

    def decide(self, identity: str, answer: str) -> bool:
        with self._lock:
            waiter = self._pending.get(identity)
            if waiter is None or time.time() >= waiter.public.expires_at:
                return False
            if isinstance(waiter.public, ApprovalRequest):
                if answer not in {"allow_once", "deny"}:
                    raise ValueError("invalid approval decision")
            elif len(answer) > 1000 or not answer.isprintable():
                raise ValueError("invalid user input")
            if waiter.answered.is_set():
                return False
            waiter.answer = answer
            waiter.answered.set()
            return True

    def cancel_all(self) -> None:
        with self._lock:
            for waiter in self._pending.values():
                waiter.answered.set()

    def close_interactions(self) -> None:
        """Deny outstanding and future waits without cancelling the agent turn."""
        with self._lock:
            self._closed = True
            for waiter in self._pending.values():
                waiter.answered.set()


def user_input_tool(broker: InteractionBroker) -> Tool:
    return Tool(
        "request_user_input",
        "Ask one concise question when information is required to continue.",
        USER_INPUT_PARAMETERS,
        broker.request_input,
        detail=lambda args: str(args.get("question", ""))[:200],
    )
