"""Explicit Chat Completions connections without a cloud SDK dependency."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from .http_model_transport import CancellableHTTPTransport
from .model_runtime import chat_completion_messages, validated_chat_calls


class CompatibleModelError(RuntimeError):
    """Host-written, redacted diagnostics; never include raw provider bodies."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str = "unknown",
        output_started: bool = False,
        retry_after: float | None = None,
        phase: str = "provider",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.output_started = output_started
        self.retry_after = retry_after
        self.phase = phase


def transport_error(error: httpx.HTTPError, *, partial: bool, phase: str) -> CompatibleModelError:
    """Retain HTTPX categories without serializing URLs, credentials or bodies."""
    categories = (
        (httpx.ConnectTimeout, "connect_timeout", "Model connection timed out"),
        (httpx.ReadTimeout, "read_timeout", "Model response stalled (read timeout)"),
        (httpx.WriteTimeout, "write_timeout", "Model request upload timed out"),
        (httpx.PoolTimeout, "pool_timeout", "Model connection pool timed out"),
        (httpx.ConnectError, "connect_error", "Model connection could not be established"),
        (httpx.ReadError, "read_error", "Model connection interrupted while reading"),
        (httpx.WriteError, "write_error", "Model connection interrupted while uploading"),
        (httpx.RemoteProtocolError, "remote_protocol_error", "Model server protocol interrupted"),
        (httpx.LocalProtocolError, "local_protocol_error", "Invalid model request protocol"),
        (httpx.ProxyError, "proxy_error", "Model proxy connection failed"),
    )
    code, message = next(((code, label) for kind, code, label in categories
                          if isinstance(error, kind)),
                         ("transport_error", "Model transport failed"))
    suffix = "; generation already started; retry explicitly" if partial else (
        "; remote outcome is unconfirmed; retry explicitly"
        if code in {"read_timeout", "read_error", "write_timeout", "write_error",
                    "remote_protocol_error", "transport_error"}
        else "; explicit retry is available"
    )
    return CompatibleModelError(message + suffix, error_type=code,
                                output_started=partial, phase=phase)


def provider_error(
    value: Any, *, status: int | None = None, partial: bool = False, retry_after: str = ""
) -> CompatibleModelError:
    """Project a typed allowlist; raw server messages and metadata stay private."""
    error = value.get("error", value) if isinstance(value, dict) else {}
    error = error if isinstance(error, dict) else {}
    metadata = error.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    messages = {
        "context_length_exceeded": "Model context limit exceeded; image preparation can be reduced",
        "image_too_large": "Model image size limit exceeded",
        "invalid_image": "Model rejected the prepared image",
        "rate_limit_exceeded": "Model rate limited; retry after the provider delay",
        "provider_overloaded": "Model provider is temporarily overloaded",
        "provider_unavailable": "Model provider is temporarily unavailable",
        "payment_required": "Model credits exhausted; check the provider balance",
        "insufficient_credits": "Model credits exhausted; check the provider balance",
        "authentication": "Model authentication failed; check the provider credentials",
        "content_policy_violation": "Model refused the image under its content policy",
        "refusal": "Model refused this request",
        "server": "Model provider reported an internal error",
        "timeout": "Model provider timed out; explicit retry is available",
    }
    code = next(
        (
            c
            for c in (
                metadata.get("error_type"),
                error.get("error_type"),
                error.get("code"),
                error.get("type"),
                metadata.get("provider_code"),
            )
            if isinstance(c, str) and c in messages
        ),
        "unknown",
    )
    raw_status = error.get("code")
    if type(raw_status) is int and 400 <= raw_status <= 599:
        status = raw_status
    if code == "unknown":
        code = {
            401: "authentication",
            403: "authentication",
            402: "payment_required",
            429: "rate_limit_exceeded",
            503: "provider_unavailable",
        }.get(status or 0, "unknown")
    delay = None
    if retry_after:
        try:
            parsed_delay = float(retry_after)
            delay = max(0.0, parsed_delay) if math.isfinite(parsed_delay) else None
        except ValueError:
            try:
                delay = max(
                    0.0, (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
                )
            except (ValueError, TypeError, OverflowError):
                pass
    message = messages.get(code, "Model server reported a generation error")
    if delay is not None and not math.isfinite(delay):
        delay = None
    if status is not None:
        message += f" (HTTP {status})"
    if partial:
        message += "; request already started; retry explicitly"
    return CompatibleModelError(
        message, status_code=status, error_type=code, output_started=partial, retry_after=delay
    )


class CompatibleRuntime(CancellableHTTPTransport):
    """Translate the common agent contract; do not infer capabilities from names."""

    backend = "openai_compatible"

    def __init__(self, base_url: str, api_key: str = "", timeout: float | httpx.Timeout = 600.0):
        self.api_key = api_key
        self.image_model = ""
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        super().__init__(base_url, timeout, headers=headers, trust_env=False)

    def _cancel_error(self) -> RuntimeError:
        return CompatibleModelError("Model request cancelled", error_type="cancelled")

    def fork_for_child(self) -> CompatibleRuntime:
        child = CompatibleRuntime(self.base_url, self.api_key, self.timeout)
        child.image_model = self.image_model
        return child

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
        has_images = any(message.get("image_content") is not None for message in messages)
        if has_images and self.image_model != model:
            raise CompatibleModelError("Image support has not been verified for this model")
        payload: dict[str, Any] = {
            "model": model,
            "messages": chat_completion_messages(messages, include_images=has_images),
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
    def _events(
        response: httpx.Response,
        *,
        response_limit: int = 16_000_000,
        event_limit: int = 1_000_000,
    ) -> Iterator[dict[str, Any]]:
        # Bound individual events as well as the complete response; malformed
        # servers must not accumulate unbounded lines in httpx.iter_lines().
        buffer = b""
        data: list[bytes] = []
        total = 0
        for chunk in response.iter_bytes():
            total += len(chunk)
            buffer += chunk
            if total > response_limit or len(buffer) > event_limit:
                raise CompatibleModelError("Model response exceeds its size limit")
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line = line.rstrip(b"\r")
                if line.startswith(b"data:"):
                    data.append(line[5:].lstrip())
                    if sum(map(len, data)) > event_limit:
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
        self.last_chat_metadata = {}
        options = options or {}
        payload = self._request_payload(model, messages, tools, options, think)
        private_state: dict[str, Any] = {}
        calls: dict[int, dict[str, Any]] = {}
        finish: str | None = None
        started = False
        request_started_at = time.monotonic()
        phase = "awaiting_headers"
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
                phase = "streaming"
                if response.status_code != 200:
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        body.extend(chunk)
                        if len(body) > 65536:
                            break
                    try:
                        error = json.loads(body) if len(body) <= 65536 else {}
                    except (ValueError, UnicodeError):
                        error = {}
                    failure = provider_error(
                        error,
                        status=response.status_code,
                        retry_after=response.headers.get("retry-after", ""),
                    )
                    self.last_chat_metadata["error_type"] = failure.error_type
                    raise failure
                for event in self._events(
                    response,
                    response_limit=self.stream_response_limit,
                    event_limit=self.stream_event_limit,
                ):
                    routed = event.get("model")
                    if (
                        isinstance(routed, str)
                        and re.fullmatch(r"[A-Za-z0-9_./:@+-]{1,200}", routed)
                        and not (self.api_key and self.api_key in routed)
                    ):
                        self.last_chat_metadata["routed_model"] = routed
                    response_id = event.get("id")
                    if isinstance(response_id, str) and re.fullmatch(
                        r"[A-Za-z0-9_-]{1,160}", response_id
                    ):
                        self.last_chat_metadata["response_id"] = response_id
                    if event.get("error"):
                        failure = provider_error(event, partial=started)
                        self.last_chat_metadata["error_type"] = failure.error_type
                        raise failure
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                        self.last_chat_metadata["usage"] = {
                            key: value
                            for key, value in usage.items()
                            if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                            and isinstance(value, int)
                            and value >= 0
                        }
                        started |= any(
                            value > 0 for value in self.last_chat_metadata["usage"].values()
                        )
                    choices = event.get("choices", [])
                    if not isinstance(choices, list):
                        raise CompatibleModelError("Malformed model choices")
                    for choice in choices:
                        if not isinstance(choice, dict) or choice.get("index", 0) != 0:
                            continue
                        if choice.get("error"):
                            failure = provider_error(choice, partial=started)
                            self.last_chat_metadata["error_type"] = failure.error_type
                            raise failure
                        delta = choice.get("delta") or {}
                        if not isinstance(delta, dict):
                            raise CompatibleModelError("Malformed model delta")
                        started |= any(
                            delta.get(k) for k in ("content", "tool_calls", "reasoning_details")
                        )
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
            # Closing a cancelled owned transport can surface as an HTTPX error.
            # Cancellation remains a terminal user action, never a retry signal.
            with self._active_response_lock:
                cancelled = self._active_client is not client
            if cancelled:
                self.last_chat_metadata["error_type"] = "cancelled"
                raise self._cancel_error() from exc
            failure = transport_error(exc, partial=started, phase=phase)
            self.last_chat_metadata.update(error_type=failure.error_type,
                                           request_phase=phase, output_started=started)
            raise failure from exc
        finally:
            self.last_chat_metadata["request_elapsed_seconds"] = round(
                time.monotonic() - request_started_at, 3
            )
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
