"""DeepSeek Chat Completions with private, endpoint-scoped reasoning continuation."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .compatible_runtime import CompatibleModelError, CompatibleRuntime
from .model_connections import DEFAULT_URLS
from .model_runtime import chat_completion_messages

MAX_REASONING_CHARS = 256_000


class DeepSeekRuntime(CompatibleRuntime):
    backend = "deepseek"

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: float = 600.0,
        *,
        connection_scope: str = "",
    ):
        if not api_key:
            raise ValueError("DeepSeek API key is not configured")
        super().__init__(base_url or DEFAULT_URLS[self.backend], api_key, timeout)
        self.connection_scope = connection_scope
        self.continuation_scope = hashlib.sha256(
            json.dumps((self.base_url, connection_scope)).encode()
        ).hexdigest()

    def fork_for_child(self) -> DeepSeekRuntime:
        return DeepSeekRuntime(
            self.base_url, self.api_key, self.timeout, connection_scope=self.connection_scope
        )

    def _request_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any],
        think: bool | str | None,
    ) -> dict[str, Any]:
        payload = super()._request_payload(model, messages, tools, options, think)
        # Standard mode is explicit: the upstream default enables thinking.
        enabled = think is True or isinstance(think, str) and think not in {"off", "none"}
        payload["thinking"] = {"type": "enabled" if enabled else "disabled"}
        if enabled:
            requested = think if isinstance(think, str) else "high"
            payload["reasoning_effort"] = {
                "minimal": "low",
                "low": "low",
                "medium": "high",
                "high": "high",
                "xhigh": "high",
                "max": "max",
                "ultra": "max",
            }.get(requested, "high")
            payload.pop("temperature", None)
        if tools:
            payload["messages"] = chat_completion_messages(
                messages,
                deepseek_scope=(self.continuation_scope, model),
            )
        return payload

    def _private_delta(self, delta: dict[str, Any], state: dict[str, Any]) -> None:
        value = delta.get("reasoning_content")
        if value is None:
            return
        if not isinstance(value, str):
            raise CompatibleModelError("Malformed DeepSeek reasoning continuation")
        size = state.get("size", 0) + len(value)
        if size > MAX_REASONING_CHARS:
            raise CompatibleModelError("DeepSeek reasoning continuation exceeds its size limit")
        state["size"] = size
        state.setdefault("parts", []).append(value)

    def _private_message(
        self,
        state: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not state.get("parts"):
            return {}
        return {
            "deepseek_continuation": {
                "scope": self.continuation_scope,
                "model": payload["model"],
                "reasoning_content": "".join(state["parts"]),
            }
        }
