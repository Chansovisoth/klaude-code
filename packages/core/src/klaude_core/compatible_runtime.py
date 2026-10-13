"""Explicit Chat Completions connections without a cloud SDK dependency."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from .http_model_transport import CancellableHTTPTransport
from .model_runtime import chat_completion_messages, validated_chat_calls


class CompatibleModelError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CompatibleRuntime(CancellableHTTPTransport):
    """Translate the common agent contract; do not infer capabilities from names."""

    backend = "openai_compatible"

    def __init__(self, base_url: str, api_key: str = "", timeout: float = 600.0):
        self.api_key = api_key
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        super().__init__(base_url, timeout, headers=headers, trust_env=False)

    def _cancel_error(self) -> RuntimeError:
        return CompatibleModelError("Model request cancelled")

    def fork_for_child(self) -> CompatibleRuntime:
        return CompatibleRuntime(self.base_url, self.api_key, self.timeout)

    def _request_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any],
        think: bool | str | None,
    ) -> dict[str, Any]:
        limit = options.get("num_predict")
        limit = limit if type(limit) is int and limit > 0 else 2048
        payload: dict[str, Any] = {
            "model": model,
            "messages": chat_completion_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": limit,
        }
        if "temperature" in options:
            payload["temperature"] = options["temperature"]
        if tools:
            payload["tools"] = tools
        # Generic servers have no portable reasoning/context allocation contract.
        return payload

    def _private_delta(self, delta: dict[str, Any], state: dict[str, Any]) -> None:
        """Native adapters may retain bounded continuation, never public text."""

    def _private_message(
        self,
        state: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Publish continuation only after a complete provider response."""
        return {}

    @staticmethod
    def _events(response: httpx.Response) -> Iterator[dict[str, Any]]:
        # Bound individual events as well as the complete response; malformed
        # servers must not accumulate unbounded lines in httpx.iter_lines().
        buffer = b""
        data: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            buffer += chunk
            if total > 16_000_000 or len(buffer) > 1_000_000:
                raise CompatibleModelError("Model response exceeds its size limit")
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.rstrip(b"\r")
                if line.startswith(b"data:"):
                    data.append(line[5:].lstrip())
                    if sum(map(len, data)) > 1_000_000:
                        raise CompatibleModelError("Model event exceeds its size limit")
                elif not line and data:
                    raw = b"\n".join(data)
                    data.clear()
                    if raw == b"[DONE]":
                        return
                    try:
                        event = json.loads(raw)
                    except (ValueError, UnicodeError):
                        raise CompatibleModelError("Malformed model stream event") from None
                    if not isinstance(event, dict):
                        raise CompatibleModelError("Malformed model stream event")
                    yield event
        if buffer.strip() or data:
            raise CompatibleModelError("Model stream ended inside an event")

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> Iterator[dict[str, Any]]:
        options = options or {}
        payload = self._request_payload(model, messages, tools, options, think)
        private_state: dict[str, Any] = {}
        calls: dict[int, dict[str, Any]] = {}
        finish: str | None = None
        self.last_chat_metadata = {}
        client = self._chat_client_factory()
        self._track_request(client)
        try:
            with client.stream(
                "POST",
                "/chat/completions",
                json=payload,
                extensions={"trace": self._request_trace(client)},
            ) as response:
                self._attach_response(client, response)
                if response.status_code != 200:
                    status = response.status_code
                    label = (
                        "authentication failed"
                        if status in {401, 403}
                        else "rate limited"
                        if status == 429
                        else "request failed"
                    )
                    raise CompatibleModelError(f"Model {label} (HTTP {status})", status_code=status)
                for event in self._events(response):
                    if event.get("error"):
                        raise CompatibleModelError("Model server reported a generation error")
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                        self.last_chat_metadata["usage"] = {
                            key: value
                            for key, value in usage.items()
                            if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                            and isinstance(value, int)
                            and value >= 0
                        }
                    choices = event.get("choices", [])
                    if not isinstance(choices, list):
                        raise CompatibleModelError("Malformed model choices")
                    for choice in choices:
                        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                            continue
                        delta = choice.get("delta") or {}
                        if not isinstance(delta, dict):
                            raise CompatibleModelError("Malformed model delta")
                        self._private_delta(delta, private_state)
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            yield {"role": "assistant", "content": content}
                        fragments = delta.get("tool_calls") or []
                        if not isinstance(fragments, list):
                            raise CompatibleModelError("Malformed model tool calls")
                        for fragment in fragments:
                            if not isinstance(fragment, dict):
                                raise CompatibleModelError("Malformed model tool call")
                            index = fragment.get("index", 0)
                            if type(index) is not int or not 0 <= index < 64:
                                raise CompatibleModelError("Invalid model tool call index")
                            call = calls.setdefault(
                                index,
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                },
                            )
                            if fragment.get("id"):
                                call["id"] += str(fragment["id"])
                            function = fragment.get("function") or {}
                            if not isinstance(function, dict):
                                raise CompatibleModelError("Malformed model tool function")
                            for key in ("name", "arguments"):
                                value = function.get(key)
                                if value is not None:
                                    if not isinstance(value, str):
                                        raise CompatibleModelError("Malformed model tool fragment")
                                    call["function"][key] += value
                        if choice.get("finish_reason") is not None:
                            finish = str(choice["finish_reason"])
            if finish == "length":
                raise CompatibleModelError(
                    "Model output limit reached; raise the budget or shorten the request"
                )
            if finish not in {"stop", "tool_calls"}:
                raise CompatibleModelError("Model response ended without a complete answer")
            self.last_chat_metadata["finish_reason"] = finish
            continuation = self._private_message(private_state, payload)
            if calls:
                yield {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": validated_chat_calls(calls),
                    **continuation,
                }
            elif finish == "tool_calls":
                yield {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {"function": {"name": "", "arguments": "{}"}, "parse_status": "malformed"},
                    ],
                    **continuation,
                }
            elif continuation:
                yield {"role": "assistant", "content": "", **continuation}
        except httpx.HTTPError as exc:
            raise CompatibleModelError("Model connection interrupted; retry") from exc
        finally:
            self._finish_request(client)
            client.close()

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {"role": "assistant", "content": ""}
        for event in self.chat_stream(model, messages, tools, options, think):
            message["content"] += event.get("content", "")
            if event.get("tool_calls"):
                message["tool_calls"] = event["tool_calls"]
            message.update(
                {
                    key: value
                    for key, value in event.items()
                    if key not in {"role", "content", "tool_calls"}
                }
            )
        return message
