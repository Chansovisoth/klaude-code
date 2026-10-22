"""Native bounded Gemini image requests and scoped signed-part continuation."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from copy import deepcopy
from typing import Any
from urllib.parse import quote

import httpx

from .compatible_runtime import CompatibleModelError, CompatibleRuntime
from .http_model_transport import CancellableHTTPTransport
from .image_content import MAX_IMAGES, image_parts
from .image_profiles import GEMINI_ROOT, gemini_image_profile
from .model_runtime import validated_chat_calls

MAX_REQUEST_BYTES = 20_000_000
MAX_PARTS = 512
MAX_CONTINUATION_BYTES = 256_000


class GeminiImages(CancellableHTTPTransport):
    backend = "gemini_api"

    def __init__(self, key: str, timeout: float | httpx.Timeout = 600):
        self.api_key = key
        self.image_model = ""
        timeout = (
            httpx.Timeout(timeout, connect=3) if isinstance(timeout, (int, float)) else timeout
        )
        super().__init__(GEMINI_ROOT, timeout, headers={"x-goog-api-key": key}, trust_env=False)

    def scope(self, model: str) -> str:
        return hashlib.sha256(json.dumps((self.base_url, model, self.api_key)).encode()).hexdigest()

    @staticmethod
    def _parts(parts: Any) -> list[dict]:
        if not isinstance(parts, list) or len(parts) > MAX_PARTS:
            raise CompatibleModelError("Invalid Gemini continuation parts")
        for part in parts:
            if not isinstance(part, dict) or set(part) - {
                "text",
                "functionCall",
                "thought",
                "thoughtSignature",
            }:
                raise CompatibleModelError("Unexpected Gemini output part")
            if "text" in part and not isinstance(part["text"], str):
                raise CompatibleModelError("Invalid Gemini text")
            if "thought" in part and type(part["thought"]) is not bool:
                raise CompatibleModelError("Invalid Gemini thought metadata")
            if "functionCall" in part:
                call = part["functionCall"]
                if (
                    not isinstance(call, dict)
                    or not isinstance(call.get("name"), str)
                    or not isinstance(call.get("args", {}), dict)
                    or "id" in call
                    and not isinstance(call["id"], str)
                ):
                    raise CompatibleModelError("Malformed Gemini function call")
            if "thoughtSignature" in part:
                signature = part["thoughtSignature"]
                if not isinstance(signature, str) or not signature:
                    raise CompatibleModelError("Invalid Gemini thought signature")
                try:
                    base64.b64decode(signature, validate=True)
                except ValueError:
                    raise CompatibleModelError("Invalid Gemini thought signature") from None
        if len(json.dumps(parts).encode()) > MAX_CONTINUATION_BYTES:
            raise CompatibleModelError("Gemini continuation exceeds its bound")
        return deepcopy(parts)

    def _contents(self, model: str, messages: list[dict]) -> list[dict]:
        profile = gemini_image_profile(self.base_url, model)
        strict = profile is not None and profile["thinking_control"] == "level"
        outputs = {
            str(m.get("tool_call_id"))
            for m in messages
            if m.get("role") == "tool" and m.get("tool_call_id")
        }
        complete: set[str] = set()
        for message in messages:
            calls = message.get("tool_calls", []) or []
            if (
                message.get("role") == "assistant"
                and calls
                and all(call.get("id") and str(call["id"]) in outputs for call in calls)
            ):
                complete.update(str(call["id"]) for call in calls)
        provider_ids: dict[str, str] = {}
        historical: set[str] = set()
        contents: list[dict[str, Any]] = []
        count = 0
        for message in messages:
            role = message.get("role")
            if role == "tool":
                identity = str(message.get("tool_call_id", ""))
                if identity not in complete:
                    continue
                if identity in historical:
                    contents.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": "[Historical tool result; context only]\n"
                                    + str(message.get("tool_name", "tool"))
                                    + "\n"
                                    + str(message.get("content", ""))
                                }
                            ],
                        }
                    )
                    continue
                response = {
                    "name": message.get("tool_name", "tool"),
                    "response": {"result": str(message.get("content", ""))},
                }
                if provider_ids.get(identity):
                    response["id"] = provider_ids[identity]
                part = {"functionResponse": response}
                if (
                    contents
                    and contents[-1]["role"] == "user"
                    and all("functionResponse" in p for p in contents[-1]["parts"])
                ):
                    contents[-1]["parts"].append(part)
                else:
                    contents.append({"role": "user", "parts": [part]})
                continue
            if role not in {"user", "assistant"}:
                continue
            state = message.get("gemini_continuation")
            calls = message.get("tool_calls", []) or []
            if (
                role == "assistant"
                and calls
                and any(str(call.get("id", "")) not in complete for call in calls)
            ):
                continue
            if (
                role == "assistant"
                and isinstance(state, dict)
                and state.get("scope") == self.scope(model)
            ):
                parts = self._parts(state.get("parts"))
                if sum("functionCall" in part for part in parts) != len(calls):
                    continue
                first = next((p for p in parts if "functionCall" in p), None)
                if strict and first is not None and not first.get("thoughtSignature"):
                    raise CompatibleModelError(
                        "Gemini native tool history is missing its signature"
                    )
                kept = []
                call_index = 0
                for part in parts:
                    if "functionCall" in part:
                        local = calls[call_index] if call_index < len(calls) else {}
                        call_index += 1
                        identity = str(local.get("id", ""))
                        if identity not in complete:
                            continue
                        provider_ids[identity] = part["functionCall"].get("id", "")
                    kept.append(part)
                parts = kept
            else:
                parts = []
                pixels = image_parts(message)
                count += len(pixels)
                if count > MAX_IMAGES:
                    raise CompatibleModelError(f"Model requests accept at most {MAX_IMAGES} images")
                parts.extend(
                    {"inlineData": {"mimeType": p["mime_type"], "data": p["data"]}} for p in pixels
                )
                if message.get("content"):
                    parts.append({"text": str(message["content"])})
                if strict and role == "assistant" and calls:
                    historical.update(str(call["id"]) for call in calls)
                    parts.append(
                        {
                            "text": "[Historical tool calls from an earlier runtime: "
                            + ", ".join(
                                str(c.get("function", {}).get("name", "tool")) for c in calls
                            )
                            + "]"
                        }
                    )
                    calls = []
                for call in calls:
                    identity = str(call.get("id", ""))
                    if identity not in complete:
                        continue
                    fn = call.get("function", {})
                    args = fn.get("arguments", "{}")
                    args = json.loads(args) if isinstance(args, str) else args
                    if not isinstance(args, dict):
                        raise CompatibleModelError("Invalid Gemini tool history")
                    # Unsigned history is reconstructed without borrowing signatures
                    # from another provider/model or an unscoped legacy SDK call.
                    parts.append({"functionCall": {"name": fn.get("name", ""), "args": args}})
            if parts:
                contents.append(
                    {"role": "model" if role == "assistant" else "user", "parts": parts}
                )
        return contents

    def _payload(
        self,
        model: str,
        messages: list[dict],
        tools: list | None,
        options: dict,
        think: bool | str | None,
    ) -> bytes:
        profile = gemini_image_profile(self.base_url, model)
        if profile is None:
            raise CompatibleModelError("No reviewed image profile for this Gemini model/endpoint")
        if any(m.get("image_content") is not None for m in messages) and self.image_model != model:
            raise CompatibleModelError("Image support has not been verified for this model")
        output = options.get("num_predict")
        output = output if type(output) is int and output > 0 else 2048
        if output > profile["max_output_tokens"]:
            raise CompatibleModelError("Output budget exceeds the documented Gemini limit")
        if profile["thinking_control"] == "level":
            effort = think.lower() if isinstance(think, str) else ""
            if effort not in profile["effort_levels"]:
                raise CompatibleModelError(
                    "This Gemini model requires Thinking; explicitly choose a supported effort"
                )
            thinking: dict[str, Any] = {"thinkingLevel": effort}
        else:
            effort = (
                "off"
                if think in {None, False, "off", "none", "auto"}
                else ("medium" if think is True else str(think).lower())
            )
            budgets = {"off": 0, "low": 1024, "medium": 8192, "high": 24576}
            if effort not in budgets:
                raise CompatibleModelError("Choose a supported Gemini thinking effort")
            thinking = {"thinkingBudget": budgets[effort]}
        payload: dict[str, Any] = {
            "contents": self._contents(model, messages),
            "generationConfig": {
                "maxOutputTokens": output,
                "candidateCount": 1,
                "thinkingConfig": thinking,
            },
            "store": False,
        }
        instructions = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
        if instructions:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(instructions)}]}
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["function"]["name"],
                            "description": t["function"].get("description", ""),
                            "parametersJsonSchema": t["function"].get("parameters", {}),
                        }
                        for t in tools
                    ]
                }
            ]
        raw = json.dumps(payload, separators=(",", ":")).encode()
        if len(raw) > MAX_REQUEST_BYTES:
            raise CompatibleModelError(
                "Gemini inline request exceeds 20 MB; reduce image/context size"
            )
        return raw

    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list | None = None,
        options: dict | None = None,
        think: bool | str | None = None,
    ):
        self.last_chat_metadata = {}
        payload = self._payload(model, messages, tools, options or {}, think)
        client = self._chat_client_factory()
        self._track_request(client)
        parts: list[dict] = []
        part_bytes = 2
        finish = ""
        try:
            with client.stream(
                "POST",
                "/v1beta/models/" + quote(model, safe="") + ":streamGenerateContent?alt=sse",
                content=payload,
                headers={"Content-Type": "application/json"},
                extensions={"trace": self._request_trace(client)},
            ) as response:
                self._attach_response(client, response)
                if response.status_code != 200:
                    raise CompatibleModelError(
                        "Gemini model unavailable for generation (HTTP 404); "
                        "metadata visibility does not guarantee account access"
                        if response.status_code == 404
                        else f"Gemini request rejected (HTTP {response.status_code})",
                        status_code=response.status_code,
                    )
                for event in CompatibleRuntime._events(
                    response,
                    response_limit=self.stream_response_limit,
                    event_limit=self.stream_event_limit,
                ):
                    if event.get("error"):
                        raise CompatibleModelError("Gemini server reported a generation error")
                    if isinstance(event.get("usageMetadata"), dict):
                        self.last_chat_metadata["usage"] = {
                            target: event["usageMetadata"][source]
                            for source, target in (
                                ("promptTokenCount", "prompt_token_count"),
                                ("candidatesTokenCount", "candidates_token_count"),
                                ("thoughtsTokenCount", "thoughts_token_count"),
                                ("cachedContentTokenCount", "cached_content_token_count"),
                            )
                            if type(event["usageMetadata"].get(source)) is int
                            and event["usageMetadata"][source] >= 0
                        }
                        usage = self.last_chat_metadata["usage"]
                        if "candidates_token_count" in usage:
                            usage["output_tokens"] = usage["candidates_token_count"] + usage.get(
                                "thoughts_token_count", 0
                            )
                    candidates = event.get("candidates", [])
                    if not isinstance(candidates, list) or len(candidates) > 1:
                        raise CompatibleModelError("Invalid Gemini candidates")
                    if (event.get("promptFeedback") or {}).get("blockReason"):
                        raise CompatibleModelError("Gemini declined the input")
                    for candidate in candidates:
                        if (
                            finish
                            or not isinstance(candidate, dict)
                            or candidate.get("index", 0) != 0
                        ):
                            raise CompatibleModelError(
                                "Unexpected Gemini candidate after completion"
                            )
                        content = candidate.get("content") or {}
                        incoming = self._parts(content.get("parts", []))
                        for part in incoming:
                            part_bytes += len(json.dumps(part).encode()) + 1
                            if part_bytes > MAX_CONTINUATION_BYTES:
                                raise CompatibleModelError("Gemini continuation exceeds its bound")
                            if "text" in part and not part.get("thought"):
                                yield {"role": "assistant", "content": part["text"]}
                            if (
                                parts
                                and set(part) <= {"text", "thought"}
                                and "text" in part
                                and set(parts[-1]) <= {"text", "thought"}
                                and "text" in parts[-1]
                                and part.get("thought", False) == parts[-1].get("thought", False)
                            ):
                                parts[-1]["text"] += part["text"]
                            else:
                                parts.append(part)
                        if len(parts) > MAX_PARTS:
                            raise CompatibleModelError("Gemini continuation exceeds its part bound")
                        finish = candidate.get("finishReason", "")
            if finish != "STOP":
                raise CompatibleModelError(
                    "Gemini output limit reached"
                    if finish == "MAX_TOKENS"
                    else "Gemini response did not complete successfully"
                )
            parts = self._parts(parts)
            calls = []
            for part in parts:
                if "functionCall" in part:
                    call = part["functionCall"]
                    calls.append(
                        {
                            "id": call.get("id") or "gemini_" + uuid.uuid4().hex,
                            "function": {
                                "name": call["name"],
                                "arguments": json.dumps(call.get("args", {})),
                            },
                        }
                    )
            self.last_chat_metadata.update(provider=self.backend, finish_reason=finish)
            yield {
                "role": "assistant",
                "content": "",
                **({"tool_calls": validated_chat_calls(dict(enumerate(calls)))} if calls else {}),
                "gemini_continuation": {"scope": self.scope(model), "parts": parts},
            }
        finally:
            self._finish_request(client)
            client.close()

    def chat(
        self,
        model: str,
        messages: list[dict],
        tools: list | None = None,
        options: dict | None = None,
        think: bool | str | None = None,
    ) -> dict:
        result: dict[str, Any] = {"role": "assistant", "content": ""}
        for delta in self.chat_stream(model, messages, tools, options, think):
            result["content"] += delta.get("content", "")
            result.update({k: v for k, v in delta.items() if k not in {"role", "content"}})
        return result
