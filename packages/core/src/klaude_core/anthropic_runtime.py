"""Native Anthropic Messages transport and private signed block continuation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from copy import deepcopy
from typing import Any

import httpx

from .compatible_runtime import CompatibleModelError, CompatibleRuntime
from .http_model_transport import CancellableHTTPTransport
from .image_content import ANTHROPIC_IMAGE_BYTES, MAX_IMAGES, image_parts
from .model_connections import DEFAULT_URLS
from .model_runtime import ModelCapabilities, chat_completion_messages, validated_chat_calls

API_VERSION = "2023-06-01"
MAX_CONTINUATION_BYTES = 1_000_000
MAX_THINKING_CHARS = 256_000


class AnthropicModelError(CompatibleModelError):
    pass


def catalog_capabilities(entry: dict[str, Any]) -> ModelCapabilities:
    """Use declared capability metadata; never infer a protocol from a model ID."""
    capabilities = entry.get("capabilities") or {}
    if not isinstance(capabilities, dict):
        raise ValueError("Invalid Anthropic capability metadata")
    thinking = capabilities.get("thinking") or {}
    if not isinstance(thinking, dict):
        raise ValueError("Invalid Anthropic thinking metadata")
    types = thinking.get("types")
    thinking_types = None
    if types is not None:
        if not isinstance(types, dict):
            raise ValueError("Invalid Anthropic thinking types")
        known = []
        for name in ("disabled", "enabled", "adaptive"):
            value = types.get(name)
            if value is None:
                continue
            if not isinstance(value, dict) or type(value.get("supported")) is not bool:
                raise ValueError("Invalid Anthropic thinking support")
            if value["supported"]:
                known.append(name)
        # Older catalogs omit disabled. Absence does not prove always-on thinking.
        if "disabled" in types:
            thinking_types = tuple(known)
            if not thinking_types:
                raise ValueError("Anthropic declares no supported thinking configuration")
    effort = capabilities.get("effort") or {}
    if not isinstance(effort, dict):
        raise ValueError("Invalid Anthropic effort metadata")
    levels = [
        name
        for name in ("low", "medium", "high", "max")
        if isinstance(effort.get(name), dict) and effort[name].get("supported") is True
    ]
    output = entry.get("max_tokens")
    context = entry.get("max_input_tokens")
    images = capabilities.get("image_input")
    if images is not None and (
        not isinstance(images, dict) or type(images.get("supported")) is not bool
    ):
        raise ValueError("Invalid Anthropic image support")
    return ModelCapabilities(
        effort_levels=tuple(["off", *levels]) if levels else ("off", "low", "medium", "high"),
        thinking_types=thinking_types,
        max_output_tokens=output if type(output) is int and 0 < output <= 2_000_000 else None,
        context_window=context if type(context) is int and 0 < context <= 2_000_000 else None,
        supports_images=images["supported"] if images is not None else None,
        images_evidence="catalog:image_input" if images is not None else "unknown",
    )


class AnthropicRuntime(CancellableHTTPTransport):
    backend = "anthropic"

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: float | httpx.Timeout = 600.0,
        *,
        connection_scope: str = "",
        model: str = "",
        capabilities: ModelCapabilities | None = None,
    ):
        if not api_key:
            raise ValueError("Anthropic API key is not configured")
        self.api_key, self.connection_scope, self.model = api_key, connection_scope, model
        self.capabilities = capabilities or ModelCapabilities()
        self.image_model = model if self.capabilities.supports_images is True else ""
        super().__init__(
            base_url or DEFAULT_URLS[self.backend],
            timeout,
            headers={"x-api-key": api_key, "anthropic-version": API_VERSION},
            trust_env=False,
        )
        self.continuation_scope = hashlib.sha256(
            json.dumps((self.base_url, connection_scope)).encode()
        ).hexdigest()

    def _cancel_error(self) -> RuntimeError:
        return AnthropicModelError("Model request cancelled")

    def fork_for_child(self) -> AnthropicRuntime:
        child = AnthropicRuntime(
            self.base_url,
            self.api_key,
            self.timeout,
            connection_scope=self.connection_scope,
            model=self.model,
            capabilities=self.capabilities,
        )
        child.image_model = self.image_model
        return child

    def _messages(
        self, model: str, messages: list[dict[str, Any]]
    ) -> tuple[str, list[dict[str, Any]]]:
        if any(m.get("image_content") is not None and m.get("role") != "user" for m in messages):
            raise AnthropicModelError("Image input requires a user message")
        originals = iter(
            item for item in messages if item.get("role") in {"system", "user", "assistant"}
        )
        result: list[dict[str, Any]] = []
        system: list[str] = []
        image_count = 0
        for message in chat_completion_messages(messages):
            role = message["role"]
            source = next(originals) if role != "tool" else {}
            parts = image_parts(source, max_bytes=ANTHROPIC_IMAGE_BYTES)
            image_count += len(parts)
            if image_count > MAX_IMAGES or (parts and self.image_model != model):
                raise AnthropicModelError("Image support or image count is invalid for this model")
            if role == "system":
                system.append(message["content"])
                continue
            blocks: list[dict[str, Any]] = []
            if role == "tool":
                blocks = [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message["content"],
                    }
                ]
                role = "user"
            elif role == "assistant":
                state = source.get("anthropic_continuation")
                calls = message.get("tool_calls", [])
                if (
                    isinstance(state, dict)
                    and state.get("scope") == self.continuation_scope
                    and state.get("model") == model
                    and isinstance(state.get("blocks"), list)
                    and {
                        item.get("id")
                        for item in state["blocks"]
                        if isinstance(item, dict) and item.get("type") == "tool_use"
                    }
                    == {item["id"] for item in calls}
                ):
                    blocks = deepcopy(state["blocks"])
                    if len(json.dumps(blocks).encode()) > MAX_CONTINUATION_BYTES:
                        raise AnthropicModelError("Anthropic continuation exceeds its size limit")
                else:
                    if message["content"]:
                        blocks.append({"type": "text", "text": message["content"]})
                    for call in calls:
                        function = call["function"]
                        try:
                            arguments = json.loads(function["arguments"])
                        except ValueError:
                            raise AnthropicModelError(
                                "Invalid tool arguments in retained history"
                            ) from None
                        if not isinstance(arguments, dict):
                            raise AnthropicModelError("Invalid tool arguments in retained history")
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": call["id"],
                                "name": function["name"],
                                "input": arguments,
                            }
                        )
            else:
                blocks = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": part["mime_type"],
                            "data": part["data"],
                        },
                    }
                    for part in parts
                ]
                if message["content"]:
                    blocks.append({"type": "text", "text": message["content"]})
            if not blocks:
                continue
            if result and result[-1]["role"] == role:
                result[-1]["content"].extend(blocks)
            else:
                result.append({"role": role, "content": blocks})
        return "\n\n".join(system), result

    def _request_payload(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        options: dict[str, Any],
        think: bool | str | None,
    ) -> dict[str, Any]:
        system, dialogue = self._messages(model, messages)
        cap = self.capabilities if model == self.model else ModelCapabilities()
        limit = options.get("num_predict")
        limit = limit if type(limit) is int and limit > 0 else 2048
        if cap.max_output_tokens:
            limit = min(limit, cap.max_output_tokens)
        payload: dict[str, Any] = {
            "model": model,
            "messages": dialogue,
            "stream": True,
            "max_tokens": limit,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = [
                {
                    "name": tool["function"]["name"],
                    "description": tool["function"].get("description", ""),
                    "input_schema": tool["function"].get("parameters", {"type": "object"}),
                }
                for tool in tools
            ]
        enabled = think is True or isinstance(think, str) and think not in {"off", "none"}
        if not enabled:
            if cap.requires_thinking:
                raise AnthropicModelError(
                    "This Anthropic model requires Thinking; "
                    "choose a supported Utility model or Thinking mode"
                )
            payload["thinking"] = {"type": "disabled"}
        elif cap.thinking_types is None:
            raise AnthropicModelError(
                "Reload this model's catalog to discover its supported thinking modes"
            )
        elif "adaptive" in cap.thinking_types:
            effort = think if isinstance(think, str) else "high"
            if effort not in cap.effort_levels:
                raise AnthropicModelError("Selected effort is unavailable for this Anthropic model")
            payload["thinking"] = {"type": "adaptive"}
            payload["output_config"] = {"effort": effort}
        elif "enabled" in cap.thinking_types:
            if limit <= 1024:
                raise AnthropicModelError(
                    "Manual Anthropic thinking needs an output budget above 1024 tokens"
                )
            target = {"low": 1024, "medium": 2048, "high": 4096}.get(str(think), 2048)
            payload["thinking"] = {"type": "enabled", "budget_tokens": min(target, limit - 1)}
        else:
            raise AnthropicModelError("This Anthropic model does not support Thinking")
        return payload

    def _usage(self, value: Any) -> None:
        if not isinstance(value, dict):
            return
        raw = self.last_chat_metadata.setdefault("anthropic_usage", {})
        raw.update(
            {
                key: item
                for key, item in value.items()
                if key
                in {
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                }
                and type(item) is int
                and item >= 0
            }
        )
        usage = {}
        if "input_tokens" in raw:
            usage["input_tokens"] = sum(
                raw.get(key, 0)
                for key in (
                    "input_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            )
        if "output_tokens" in raw:
            usage["output_tokens"] = raw["output_tokens"]
        self.last_chat_metadata["usage"] = usage

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> Iterator[dict[str, Any]]:
        self.last_chat_metadata = {}
        payload = self._request_payload(model, messages, tools, options or {}, think)
        blocks: list[dict[str, Any]] = []
        active: int | None = None
        started = stopped = False
        finish = None
        private_size = 0
        client = self._chat_client_factory()
        self._track_request(client)
        try:
            with client.stream(
                "POST", "/messages", json=payload, extensions={"trace": self._request_trace(client)}
            ) as response:
                self._attach_response(client, response)
                if response.status_code != 200:
                    raise AnthropicModelError(
                        f"Anthropic request failed (HTTP {response.status_code})",
                        status_code=response.status_code,
                    )
                for event in CompatibleRuntime._events(
                    response, response_limit=self.stream_response_limit,
                    event_limit=self.stream_event_limit,
                ):
                    kind = event.get("type")
                    if kind == "error":
                        code = (
                            529
                            if isinstance(event.get("error"), dict)
                            and event["error"].get("type") == "overloaded_error"
                            else None
                        )
                        raise AnthropicModelError(
                            "Anthropic stream reported a generation error", status_code=code
                        )
                    if kind == "message_start":
                        if started or not isinstance(event.get("message"), dict):
                            raise AnthropicModelError("Malformed Anthropic message start")
                        started = True
                        self._usage(event["message"].get("usage"))
                    elif kind == "content_block_start":
                        index, block = event.get("index"), event.get("content_block")
                        if (
                            not started
                            or active is not None
                            or type(index) is not int
                            or index != len(blocks)
                            or index >= 64
                            or not isinstance(block, dict)
                        ):
                            raise AnthropicModelError("Malformed Anthropic content block")
                        if block.get("type") not in {
                            "text",
                            "thinking",
                            "redacted_thinking",
                            "tool_use",
                        }:
                            raise AnthropicModelError("Unsupported Anthropic response block")
                        fields = {
                            "text": ("text",),
                            "thinking": ("thinking", "signature"),
                            "redacted_thinking": ("data",),
                        }.get(block["type"], ())
                        if any(not isinstance(block.get(field, ""), str) for field in fields):
                            raise AnthropicModelError("Malformed Anthropic block content")
                        private_size += sum(
                            len(block.get(field, "")) for field in fields if field != "text"
                        )
                        if private_size > MAX_THINKING_CHARS:
                            raise AnthropicModelError("Anthropic thinking exceeds its size limit")
                        blocks.append(deepcopy(block))
                        active = index
                        if (
                            block["type"] == "text"
                            and isinstance(block.get("text"), str)
                            and block["text"]
                        ):
                            yield {"role": "assistant", "content": block["text"]}
                    elif kind == "content_block_delta":
                        delta = event.get("delta")
                        if (
                            active is None
                            or event.get("index") != active
                            or not isinstance(delta, dict)
                        ):
                            raise AnthropicModelError("Malformed Anthropic block delta")
                        block = blocks[active]
                        field = {
                            "text_delta": "text",
                            "thinking_delta": "thinking",
                            "signature_delta": "signature",
                            "input_json_delta": "partial_json",
                        }.get(str(delta.get("type")))
                        if field is None:
                            continue
                        if (
                            (field == "text" and block["type"] != "text")
                            or (field in {"thinking", "signature"} and block["type"] != "thinking")
                            or (field == "partial_json" and block["type"] != "tool_use")
                            or not isinstance(delta.get(field), str)
                        ):
                            raise AnthropicModelError("Malformed Anthropic block fragment")
                        value = delta[field]
                        block[field] = block.get(field, "") + value
                        if field in {"thinking", "signature"}:
                            private_size += len(value)
                            if private_size > MAX_THINKING_CHARS:
                                raise AnthropicModelError(
                                    "Anthropic thinking exceeds its size limit"
                                )
                        if field == "text" and value:
                            yield {"role": "assistant", "content": value}
                    elif kind == "content_block_stop":
                        if active is None or event.get("index") != active:
                            raise AnthropicModelError("Malformed Anthropic block stop")
                        if blocks[active]["type"] == "thinking" and not blocks[active].get(
                            "signature"
                        ):
                            raise AnthropicModelError("Anthropic thinking signature is missing")
                        active = None
                    elif kind == "message_delta":
                        delta = event.get("delta")
                        if not started or active is not None or not isinstance(delta, dict):
                            raise AnthropicModelError("Malformed Anthropic message delta")
                        finish = delta.get("stop_reason") or finish
                        self._usage(event.get("usage"))
                    elif kind == "message_stop":
                        if not started or active is not None:
                            raise AnthropicModelError("Incomplete Anthropic message")
                        stopped = True
                        break
            if not stopped or finish not in {"end_turn", "stop_sequence", "tool_use", "refusal"}:
                raise AnthropicModelError(
                    "Anthropic output limit reached"
                    if finish == "max_tokens"
                    else "Anthropic response ended without completion"
                )
            calls: dict[int, dict[str, Any]] = {}
            for block in blocks:
                if block["type"] == "tool_use":
                    arguments = block.pop("partial_json", None)
                    calls[len(calls)] = {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": arguments
                            if arguments is not None
                            else json.dumps(block.get("input", {})),
                        },
                    }
            validated = validated_chat_calls(calls) if calls else []
            if bool(calls) != (finish == "tool_use"):
                raise AnthropicModelError("Anthropic stop reason disagrees with its tool calls")
            if validated and not any(item.get("parse_status") == "malformed" for item in validated):
                if len({item["id"] for item in validated}) != len(validated):
                    raise AnthropicModelError("Anthropic returned duplicate tool IDs")
                for block, call in zip(
                    [b for b in blocks if b["type"] == "tool_use"], validated, strict=True
                ):
                    block["input"] = json.loads(call["function"]["arguments"])
            if len(json.dumps(blocks).encode()) > MAX_CONTINUATION_BYTES:
                raise AnthropicModelError("Anthropic continuation exceeds its size limit")
            self.last_chat_metadata["finish_reason"] = finish
            result: dict[str, Any] = {"role": "assistant", "content": ""}
            if validated:
                result["tool_calls"] = validated
            if blocks and not any(item.get("parse_status") == "malformed" for item in validated):
                result["anthropic_continuation"] = {
                    "scope": self.continuation_scope,
                    "model": model,
                    "blocks": blocks,
                }
            yield result
        except httpx.HTTPError as exc:
            raise AnthropicModelError("Anthropic connection interrupted; retry") from exc
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
            message.update(
                {key: value for key, value in event.items() if key not in {"role", "content"}}
            )
        return message
