"""The klaude agent loop.

Deliberately small and dependency-free: messages in, tool calls out,
results appended, repeat until the model answers in plain text or the
step budget runs out. Everything interesting (models, tools, permissions)
is injected, so this file is the single seam for a future swap to a
typed agent framework.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .ollama import Ollama
from .permissions import PermissionDenied, PermissionGate

ToolFn = Callable[..., str]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for the arguments object
    fn: ToolFn
    detail: Callable[[dict], str] = field(default=lambda args: json.dumps(args)[:200])

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class AgentEvent:
    """Emitted to the client so any UI (TUI, VS Code) can render progress."""

    kind: str  # "text" | "tool_start" | "tool_result" | "error" | "done"
    payload: dict[str, Any]


class Agent:
    def __init__(
        self,
        ollama: Ollama,
        model: str,
        tools: list[Tool],
        gate: PermissionGate,
        system_prompt: str,
        max_steps: int = 20,
    ):
        self.ollama = ollama
        self.model = model
        self.tools = {t.name: t for t in tools}
        self.gate = gate
        self.max_steps = max_steps
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    def run(self, user_message: str):
        """Generator of AgentEvent — clients iterate and render."""
        self.messages.append({"role": "user", "content": user_message})
        schemas = [t.schema() for t in self.tools.values()]

        for _step in range(self.max_steps):
            try:
                msg = self.ollama.chat(self.model, self.messages, tools=schemas)
            except Exception as e:  # surface, don't crash the session
                yield AgentEvent("error", {"message": str(e)})
                return

            self.messages.append(msg)
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                yield AgentEvent("text", {"content": msg.get("content", "")})
                yield AgentEvent("done", {})
                return

            if msg.get("content"):
                yield AgentEvent("text", {"content": msg["content"]})

            for call in tool_calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}

                tool = self.tools.get(name)
                if tool is None:
                    result = f"error: unknown tool '{name}'"
                else:
                    yield AgentEvent("tool_start", {"tool": name, "args": args})
                    try:
                        self.gate.check(name, tool.detail(args))
                        result = tool.fn(**args)
                    except PermissionDenied as e:
                        result = f"permission denied: {e}"
                    except Exception as e:
                        result = f"tool error: {type(e).__name__}: {e}"

                result = str(result)
                if len(result) > 12000:  # keep small-model context healthy
                    result = result[:12000] + "\n...[truncated]"
                yield AgentEvent("tool_result", {"tool": name, "result": result})
                self.messages.append({"role": "tool", "tool_name": name, "content": result})

        yield AgentEvent("error", {"message": f"step budget ({self.max_steps}) exhausted"})
