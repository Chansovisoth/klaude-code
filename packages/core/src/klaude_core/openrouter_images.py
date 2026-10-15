"""Bounded OpenRouter image protocol, shared by chat and private Media analysis."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from .compatible_runtime import CompatibleModelError, CompatibleRuntime
from .model_runtime import chat_completion_messages


class OpenRouterImages(CompatibleRuntime):
    backend = "openrouter"

    def _request_payload(self, model, messages, tools, options, think):
        payload = super()._request_payload(model, messages, tools, options, think)
        payload["messages"] = chat_completion_messages(
            messages, include_reasoning=True, include_images=True,
        )
        payload["reasoning"] = (
            {"effort": str(think)} if think not in {None, False, "off", "auto"}
            else {"enabled": False}
        )
        return payload

    def _private_delta(self, delta: dict[str, Any], state: dict[str, Any]) -> None:
        details = delta.get("reasoning_details")
        if details is None:
            return
        if not isinstance(details, list) or any(not isinstance(item, dict) for item in details):
            raise CompatibleModelError("Malformed OpenRouter reasoning details")
        retained = state.setdefault("details", [])
        retained.extend(deepcopy(details))
        if len(retained) > 256 or len(json.dumps(retained)) > 256_000:
            raise CompatibleModelError("OpenRouter reasoning details exceed their bound")

    def _private_message(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        return {"openrouter_reasoning_details": state["details"]} if state.get("details") else {}
