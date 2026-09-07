"""Provider-neutral chat model identities and runtimes.

The agent deliberately owns tool orchestration.  Runtimes only translate the
small common chat contract to a provider and return the same assistant-message
shape that the agent has always used.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .ollama import Ollama

BACKEND_METADATA = {
    "ollama": ("Local", "Ollama"),
    "openai_api": ("Cloud", "OpenAI"),
    "gemini_api": ("Cloud", "Google"),
    # Reserved for later agent bridges; they are intentionally not runnable.
    "codex": ("Cloud", "OpenAI"),
    "gemini_cli": ("Cloud", "Google"),
}


@dataclass(frozen=True)
class ModelCapabilities:
    effort_levels: tuple[str, ...] = ("off", "low", "medium", "high")
    supports_tools: bool = True
    context_window: int | None = None


@dataclass(frozen=True)
class ModelInfo:
    backend: str
    model_id: str
    display_name: str
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    released_at: int = 0

    @property
    def ref(self) -> str:
        return f"{self.backend}/{self.model_id}"

    @property
    def source(self) -> str:
        return BACKEND_METADATA.get(self.backend, ("Cloud", self.backend))[0]

    @property
    def provider(self) -> str:
        return BACKEND_METADATA.get(self.backend, ("Cloud", self.backend))[1]


def load_model_cache(path: Path) -> list[ModelInfo]:
    """Read a non-sensitive cached cloud catalog; malformed caches are ignored."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    entries = raw.get("models", []) if isinstance(raw, dict) else []
    result: list[ModelInfo] = []
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        backend = item.get("backend")
        model_id = item.get("model_id")
        if backend not in {"openai_api", "gemini_api"} or not isinstance(model_id, str):
            continue
        result.append(
            ModelInfo(
                backend,
                model_id,
                str(item.get("display_name") or model_id),
                released_at=int(item.get("released_at") or 0),
            )
        )
    return result


def save_model_cache(path: Path, models: list[ModelInfo]) -> None:
    """Atomically cache public model identifiers only—never credentials."""
    payload = {
        "models": [
            {
                "backend": item.backend,
                "model_id": item.model_id,
                "display_name": item.display_name,
                "released_at": item.released_at,
            }
            for item in models
            if item.backend in {"openai_api", "gemini_api"}
        ]
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n")
        temporary.replace(path)
    except OSError:
        pass


def newest_model_first_key(item: ModelInfo) -> tuple[object, ...]:
    """Rank generation first, then capability tier and release recency.

    OpenAI exposes a creation timestamp. Gemini's listing does not guarantee a
    comparable timestamp, so version numbers embedded in its canonical ID are
    used as a future-proof fallback (for example 3.1 before 2.5).
    """
    identifier = item.model_id.casefold()
    tokens = set(re.split(r"[^a-z0-9]+", identifier))
    # Provider APIs do not expose a universal parameter-count/quality field.
    # Keep the policy declarative and model-family agnostic where possible;
    # named runtime tiers are intentionally ordered Sol > Terra > Luna.
    tier_rank = 0
    for marker, rank in (
        ("sol", 100),
        ("terra", 90),
        ("luna", 80),
        ("max", 70),
        ("pro", 60),
        ("mini", 30),
        ("nano", 20),
    ):
        if marker in tokens:
            tier_rank = rank
            break
    # Only use the generation immediately following the model family. Release
    # dates such as ``gpt-5-pro-2025-10-06`` must never outrank ``gpt-5.6``.
    generation = re.search(r"(?:^|[-_/])(?:gpt|gemini)[-_]?(\d+(?:\.\d+)*)", identifier)
    generation_parts = generation.group(1).split(".") if generation else []
    version = tuple(
        [-int(value) for value in generation_parts[:6]] + [0] * max(0, 6 - len(generation_parts))
    )
    return (version, -tier_rank, -item.released_at, identifier)


def local_model_weight_first_key(item: ModelInfo) -> tuple[object, ...]:
    """Order Ollama tags by declared parameter count, largest first.

    Ollama tags conventionally carry a size suffix after the colon (``:30b``,
    ``:1.7b``, or ``:0.5t``). Models without one stay usable but sort after
    size-tagged models.
    """
    parameter_count = local_model_parameter_count(item)
    if parameter_count is not None:
        return (0, -parameter_count, newest_model_first_key(item))
    return (1, 0.0, newest_model_first_key(item))


def local_model_parameter_count(item: ModelInfo) -> float | None:
    """Return a local model's declared parameter count in billions, if tagged."""
    match = re.search(r":.*?(\d+(?:\.\d+)?)([bmt])(?:\b|$)", item.model_id.casefold())
    if not match:
        return None
    value = float(match.group(1))
    return value * {"m": 0.001, "b": 1.0, "t": 1_000.0}[match.group(2)]


# Model IDs do not carry a universal publisher field. These are stable model
# family roots rather than individual model names; unknown families still get
# a useful generated heading and remain grouped by their root.
_LOCAL_MODEL_FAMILY_NAMES = {
    "gpt": "OpenAI",
    "llama": "Meta Llama",
    "gemma": "Google Gemma",
    "phi": "Microsoft Phi",
    "granite": "IBM Granite",
    "mistral": "Mistral",
    "mixtral": "Mistral",
    "codestral": "Mistral",
    "ministral": "Mistral",
}


def local_model_family(item: ModelInfo) -> str:
    """Derive a displayable publisher/family from an Ollama model ID."""
    stem = item.model_id.partition(":")[0].casefold()
    match = re.match(r"[a-z]+", stem)
    root = match.group(0) if match else stem
    # qwen3, llama3.2, and gemma3 share the alphabetic family root naturally.
    return _LOCAL_MODEL_FAMILY_NAMES.get(root, root.title() or "Other")


def grouped_local_models(models: list[ModelInfo]) -> list[tuple[str, list[ModelInfo]]]:
    """Group Ollama models by family, strongest family and variant first."""
    families: dict[str, list[ModelInfo]] = {}
    for item in models:
        families.setdefault(local_model_family(item), []).append(item)

    def group_key(entry: tuple[str, list[ModelInfo]]) -> tuple[float, str]:
        family, members = entry
        strongest = max(
            (local_model_parameter_count(item) or -1.0 for item in members),
            default=-1.0,
        )
        return (-strongest, family.casefold())

    return [
        (family, sorted(members, key=local_model_weight_first_key))
        for family, members in sorted(families.items(), key=group_key)
    ]


class ModelRuntime(Protocol):
    backend: str

    @property
    def last_chat_metadata(self) -> dict[str, Any]: ...

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]: ...
    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ): ...
    def cancel_active(self) -> bool: ...


class OllamaRuntime:
    backend = "ollama"

    def __init__(self, ollama: Ollama):
        self.ollama = ollama

    @property
    def last_chat_metadata(self) -> dict[str, Any]:
        return self.ollama.last_chat_metadata

    def chat(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.ollama.chat(*args, **kwargs)

    def chat_stream(self, *args: Any, **kwargs: Any):
        return self.ollama.chat_stream(*args, **kwargs)

    def cancel_active(self) -> bool:
        return self.ollama.cancel_active()

    def list_models(self) -> list[str]:
        return self.ollama.list_models()

    def is_up(self) -> bool:
        return self.ollama.is_up()


def _content(message: dict[str, Any]) -> str:
    return str(message.get("content", ""))


class OpenAIRuntime:
    """Official OpenAI Responses API adapter, imported only when selected."""

    backend = "openai_api"

    def __init__(self, api_key: str):
        if not api_key.strip():
            raise ValueError("OpenAI API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self._active_response: Any = None

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("OpenAI API support requires `klaude-core[cloud]`.") from exc
        return OpenAI(api_key=self.api_key)

    @staticmethod
    def _input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            if role == "tool":
                result.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.get("tool_call_id", ""),
                        "output": _content(message),
                    }
                )
            elif role == "assistant" and message.get("tool_calls"):
                for call in message["tool_calls"]:
                    fn = call.get("function", {})
                    result.append(
                        {
                            "type": "function_call",
                            "call_id": call.get("id", ""),
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", "{}"),
                        }
                    )
            elif role in {"system", "user", "assistant"}:
                result.append({"role": role, "content": _content(message)})
        return result

    @staticmethod
    def _tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": item.get("function", {}).get("name"),
                "description": item.get("function", {}).get("description", ""),
                "parameters": item.get("function", {}).get("parameters", {}),
            }
            for item in tools or []
        ]

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "input": self._input(messages),
            "tools": self._tools(tools),
            # Klaude is local-first. OpenAI Responses are retained by default,
            # so cloud calls explicitly opt out unless a future user setting
            # deliberately changes that privacy boundary.
            "store": False,
        }
        if think not in {None, False, "off", "auto"}:
            kwargs["reasoning"] = {"effort": str(think)}
        response = self._client().responses.create(**kwargs)
        self._record(response)
        self._raise_for_terminal_response(response)
        return self._message(response)

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": model,
            "input": self._input(messages),
            "stream": True,
            "store": False,
        }
        if think not in {None, False, "off", "auto"}:
            kwargs["reasoning"] = {"effort": str(think)}
        self._active_response = self._client().responses.create(**kwargs)
        try:
            for event in self._active_response:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    yield {"role": "assistant", "content": getattr(event, "delta", "")}
                elif kind == "response.refusal.delta":
                    yield {"role": "assistant", "content": getattr(event, "delta", "")}
                elif kind == "response.completed":
                    response = getattr(event, "response", None)
                    self._record(response)
                    self._raise_for_terminal_response(response)
                elif kind in {"response.failed", "response.incomplete"}:
                    response = getattr(event, "response", None)
                    self._record(response)
                    self._raise_for_terminal_response(response, fallback=kind)
                elif kind == "error":
                    error = getattr(event, "error", None)
                    message = (
                        error.get("message")
                        if isinstance(error, dict)
                        else getattr(error, "message", None)
                    )
                    raise RuntimeError(str(message or "OpenAI response failed."))
        finally:
            self._active_response = None

    def _record(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        self.last_chat_metadata = {
            "provider": "openai_api",
            "usage": usage.model_dump()
            if usage is not None and hasattr(usage, "model_dump")
            else usage,
        }

    @staticmethod
    def _raise_for_terminal_response(response: Any, *, fallback: str = "") -> None:
        status = str(getattr(response, "status", "") or "").casefold()
        if status not in {"failed", "incomplete", "cancelled"} and not fallback:
            return
        error = getattr(response, "error", None)
        message = (
            error.get("message") if isinstance(error, dict) else getattr(error, "message", None)
        )
        if not message:
            details = getattr(response, "incomplete_details", None)
            reason = (
                details.get("reason")
                if isinstance(details, dict)
                else getattr(details, "reason", None)
            )
            message = f"OpenAI response {status or fallback}: {reason or 'no reason provided'}."
        raise RuntimeError(str(message))

    @staticmethod
    def _message(response: Any) -> dict[str, Any]:
        calls = []
        refusals: list[str] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", "") == "function_call":
                calls.append(
                    {
                        "id": getattr(item, "call_id", ""),
                        "function": {
                            "name": getattr(item, "name", ""),
                            "arguments": getattr(item, "arguments", "{}"),
                        },
                    }
                )
            for part in getattr(item, "content", []) or []:
                refusal = getattr(part, "refusal", None)
                if getattr(part, "type", "") == "refusal" and refusal:
                    refusals.append(str(refusal))
        content = getattr(response, "output_text", "") or ""
        if not content and refusals:
            content = "\n".join(refusals)
        return {
            "role": "assistant",
            "content": content,
            **({"tool_calls": calls} if calls else {}),
        }

    def cancel_active(self) -> bool:
        closer = getattr(self._active_response, "close", None)
        if callable(closer):
            closer()
            return True
        return False


class GeminiRuntime:
    """google-genai adapter using manual function calling (no auto execution)."""

    backend = "gemini_api"

    def __init__(self, api_key: str):
        if not api_key.strip():
            raise ValueError("Gemini API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self._active_response: Any = None

    def _sdk(self):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("Gemini API support requires `klaude-core[cloud].") from exc
        return genai, types

    def _request(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        think: bool | str | None,
    ):
        genai, types = self._sdk()
        contents = []
        for message in messages:
            role = message.get("role")
            if role in {"user", "assistant"}:
                parts: list[dict[str, Any]] = []
                if _content(message):
                    parts.append({"text": _content(message)})
                for call in message.get("tool_calls", []) or []:
                    function = call.get("function", {})
                    try:
                        arguments = json.loads(function.get("arguments", "{}"))
                    except (TypeError, json.JSONDecodeError):
                        arguments = {}
                    part: dict[str, Any] = {
                        "function_call": {"name": function.get("name", ""), "args": arguments}
                    }
                    signature = call.get("thought_signature")
                    if isinstance(signature, str) and signature:
                        try:
                            part["thought_signature"] = base64.b64decode(signature, validate=True)
                        except ValueError:
                            raise ValueError("invalid Gemini thought signature") from None
                    parts.append(part)
                if parts:
                    contents.append(
                        {"role": "model" if role == "assistant" else "user", "parts": parts}
                    )
            elif role == "tool":
                function_response = {
                    "name": message.get("tool_name", "tool"),
                    "response": {"result": _content(message)},
                }
                if message.get("tool_call_id"):
                    function_response["id"] = message["tool_call_id"]
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"function_response": function_response}],
                    }
                )
        system = next((_content(m) for m in messages if m.get("role") == "system"), "")
        declarations = [
            {
                "name": t.get("function", {}).get("name"),
                "description": t.get("function", {}).get("description", ""),
                "parameters_json_schema": t.get("function", {}).get("parameters", {}),
            }
            for t in tools or []
        ]
        config: dict[str, Any] = {"system_instruction": system}
        effort = str(think).lower() if isinstance(think, str) else ""
        if effort in {"low", "medium", "high"}:
            if model.casefold().startswith("gemini-2.5"):
                config["thinking_config"] = {
                    "thinking_budget": {"low": 1024, "medium": 8192, "high": 24576}[effort]
                }
            else:
                config["thinking_config"] = {"thinking_level": effort}
        elif think is False or effort in {"off", "none"}:
            lowered_model = model.casefold()
            if "gemini-2.5-flash" in lowered_model and "pro" not in lowered_model:
                config["thinking_config"] = {"thinking_budget": 0}
        if declarations:
            config["tools"] = [{"function_declarations": declarations}]
            config["automatic_function_calling"] = {"disable": True}
        client = genai.Client(api_key=self.api_key)
        method = client.models.generate_content_stream if stream else client.models.generate_content
        return method(model=model, contents=contents, config=config)

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        response = self._request(model, messages, tools, False, think)
        self.last_chat_metadata = {
            "provider": "gemini_api",
            "usage": getattr(response, "usage_metadata", None),
        }
        calls = []
        for candidate in getattr(response, "candidates", []) or []:
            for part in getattr(getattr(candidate, "content", None), "parts", []) or []:
                call = getattr(part, "function_call", None)
                if call:
                    normalized_call: dict[str, Any] = {
                        "id": getattr(call, "id", ""),
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(dict(call.args or {})),
                        },
                    }
                    signature = getattr(part, "thought_signature", None)
                    if isinstance(signature, bytes) and signature:
                        normalized_call["thought_signature"] = base64.b64encode(signature).decode(
                            "ascii"
                        )
                    calls.append(normalized_call)
        return {
            "role": "assistant",
            "content": getattr(response, "text", "") or "",
            **({"tool_calls": calls} if calls else {}),
        }

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        self._active_response = self._request(model, messages, None, True, think)
        try:
            for chunk in self._active_response:
                yield {"role": "assistant", "content": getattr(chunk, "text", "") or ""}
                self.last_chat_metadata = {
                    "provider": "gemini_api",
                    "usage": getattr(chunk, "usage_metadata", None),
                }
        finally:
            self._active_response = None

    def cancel_active(self) -> bool:
        closer = getattr(self._active_response, "close", None)
        if callable(closer):
            closer()
            return True
        return False


def discover_openai_models(api_key: str) -> list[ModelInfo]:
    """Return chat-capable OpenAI API models; an unavailable API is non-fatal."""
    if not api_key:
        return []
    try:
        runtime = OpenAIRuntime(api_key)
        models = runtime._client().models.list()
    except Exception:
        return []
    result = []
    for item in getattr(models, "data", models) or []:
        model_id = getattr(item, "id", "")
        if (
            isinstance(model_id, str)
            and model_id
            and not any(
                marker in model_id.casefold()
                for marker in (
                    "embed",
                    "audio",
                    "image",
                    "moderation",
                    "realtime",
                    "transcrib",
                    "tts",
                    "search-preview",
                )
            )
        ):
            result.append(
                ModelInfo(
                    "openai_api",
                    model_id,
                    model_id,
                    released_at=int(getattr(item, "created", 0) or 0),
                )
            )
    return sorted(result, key=newest_model_first_key)


def discover_gemini_models(api_key: str) -> list[ModelInfo]:
    """Return Gemini generate-content models through the official SDK."""
    if not api_key:
        return []
    try:
        runtime = GeminiRuntime(api_key)
        genai, _ = runtime._sdk()
        listed = genai.Client(api_key=api_key).models.list()
    except Exception:
        return []
    result = []
    for item in listed:
        name = getattr(item, "name", "")
        methods = getattr(item, "supported_generation_methods", ()) or ()
        model_id = name.removeprefix("models/") if isinstance(name, str) else ""
        if model_id and (not methods or "generateContent" in methods):
            result.append(ModelInfo("gemini_api", model_id, model_id))
    return sorted(result, key=newest_model_first_key)
