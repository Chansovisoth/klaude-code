"""Provider-neutral chat model identities and runtimes.

The agent deliberately owns tool orchestration.  Runtimes only translate the
small common chat contract to a provider and return the same assistant-message
shape that the agent has always used.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .codex_auth import CODEX_RESPONSES_BASE_URL, CodexAuthError, CodexAuthManager
from .ollama import Ollama
from .settings_store import atomic_write_private, read_settings, settings_lock

BACKEND_METADATA = {
    "ollama": ("Local", "Ollama"),
    "openai_api": ("Cloud", "OpenAI"),
    "openrouter": ("Cloud", "OpenRouter"),
    "gemini_api": ("Cloud", "Google"),
    "openai_codex": ("Cloud", "OpenAI Codex"),
    # Reserved for later agent bridges; they are intentionally not runnable.
    "codex": ("Cloud", "OpenAI"),
    "gemini_cli": ("Cloud", "Google"),
}


def _metadata_mapping(value: object) -> dict[str, Any]:
    """Normalize SDK usage objects without retaining provider-private fields."""
    if isinstance(value, dict):
        return value
    dumper = getattr(value, "model_dump", None)
    if callable(dumper):
        dumped = dumper()
        return dumped if isinstance(dumped, dict) else {}
    result: dict[str, Any] = {}
    for name in (
        "input_tokens",
        "output_tokens",
        "prompt_tokens",
        "completion_tokens",
        "prompt_token_count",
        "candidates_token_count",
    ):
        item = getattr(value, name, None)
        if item is not None:
            result[name] = item
    return result


def normalize_token_usage(metadata: object) -> tuple[int, int] | None:
    """Return exact input/output counters reported by supported providers."""
    outer = _metadata_mapping(metadata)
    usage = _metadata_mapping(outer.get("usage"))
    prompt = outer.get("prompt_eval_count")
    output = outer.get("eval_count")
    if prompt is None:
        prompt = usage.get(
            "input_tokens",
            usage.get("prompt_tokens", usage.get("prompt_token_count")),
        )
    if output is None:
        output = usage.get(
            "output_tokens",
            usage.get("completion_tokens", usage.get("candidates_token_count")),
        )
    # A partial counter cannot safely enforce an aggregate total. Preserve the
    # request as explicitly unknown instead of treating the missing side as 0.
    if prompt is None or output is None:
        return None
    try:
        return max(0, int(prompt or 0)), max(0, int(output or 0))
    except (TypeError, ValueError):
        return None


def is_chat_model_id(backend: str, model_id: str) -> bool:
    """Conservatively exclude endpoint-specific models from chat pickers."""
    if backend not in {"openai_api", "openai_codex", "openrouter"}:
        return True
    value = model_id.casefold()
    return not any(
        marker in value
        for marker in (
            "audio",
            "dall-e",
            "embed",
            "gpt-image",
            "moderation",
            "realtime",
            "search-api",
            "search-preview",
            "sora",
            "transcrib",
            "tts",
            "whisper",
        )
    )


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
    return models_from_records(entries)


def models_from_records(entries: object) -> list[ModelInfo]:
    result: list[ModelInfo] = []
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        backend = item.get("backend")
        model_id = item.get("model_id")
        if (
            backend not in {"openai_api", "openai_codex", "openrouter", "gemini_api"}
            or not isinstance(model_id, str)
            or not is_chat_model_id(backend, model_id)
        ):
            continue
        result.append(
            ModelInfo(
                backend,
                model_id,
                str(item.get("display_name") or model_id),
                capabilities=ModelCapabilities(
                    effort_levels=tuple(item.get("effort_levels") or ())
                    or ModelCapabilities().effort_levels,
                    supports_tools=bool(item.get("supports_tools", True)),
                    context_window=(
                        int(item["context_window"])
                        if isinstance(item.get("context_window"), int)
                        and int(item["context_window"]) > 0
                        else None
                    ),
                ),
                released_at=int(item.get("released_at") or 0),
            )
        )
    return result


def model_records(models: list[ModelInfo]) -> list[dict[str, Any]]:
    """Serialize only public catalog fields, for caches and private worker IPC."""
    return {
        "models": [
            {
                "backend": item.backend,
                "model_id": item.model_id,
                "display_name": item.display_name,
                "effort_levels": list(item.capabilities.effort_levels),
                "supports_tools": item.capabilities.supports_tools,
                "context_window": item.capabilities.context_window,
                "released_at": item.released_at,
            }
            for item in models
            if item.backend in {"openai_api", "openai_codex", "openrouter", "gemini_api"}
            and is_chat_model_id(item.backend, item.model_id)
        ]
    }["models"]


def model_cache_generation(path: Path, backend: str) -> str:
    raw = read_settings(path).get("generations", {})
    return str(raw.get(backend, "")) if isinstance(raw, dict) else ""


def save_model_cache(
    path: Path, models: list[ModelInfo], *, backend: str | None = None,
    expected_generation: str | None = None, invalidate: bool = False,
) -> bool:
    """Merge one provider under a lock and reject results invalidated during discovery.

    The unscoped form remains an explicit full snapshot for bootstrap/tests.
    Production refreshes and logout/key changes must pass a backend.
    """
    try:
        with settings_lock(path):
            payload = read_settings(path)
            generations = payload.get("generations", {})
            generations = dict(generations) if isinstance(generations, dict) else {}
            if backend is not None:
                if (
                    expected_generation is not None
                    and generations.get(backend, "") != expected_generation
                ):
                    return False
                if invalidate:
                    generations[backend] = uuid.uuid4().hex
                existing = models_from_records(payload.get("models", []))
                models = [item for item in existing if item.backend != backend] + [
                    item for item in models if item.backend == backend
                ]
            payload.update(models=model_records(models), generations=generations)
            atomic_write_private(path, json.dumps(payload, indent=2) + "\n")
            return True
    except OSError:
        return False


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
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ): ...
    def cancel_active(self) -> bool: ...
    def fork_for_child(self) -> ModelRuntime: ...


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

    def fork_for_child(self) -> OllamaRuntime:
        """Create an independent transport tracker for child model requests."""
        return OllamaRuntime(Ollama(self.ollama.base_url, timeout=self.ollama.timeout))

    def close(self) -> None:
        self.ollama.close()

    def list_models(self) -> list[str]:
        return self.ollama.list_models()

    def is_up(self) -> bool:
        return self.ollama.is_up()


def _content(message: dict[str, Any]) -> str:
    return str(message.get("content", ""))


class _CancelableResponseRuntime:
    """Track one provider stream and make cancellation safe from UI threads."""

    def _init_active_response(self) -> None:
        self._active_response: Any = None
        self._active_response_lock = threading.Lock()

    def _track_active_response(self, response: Any) -> Any:
        with self._active_response_lock:
            self._active_response = response
        return response

    def _clear_active_response(self, response: Any) -> None:
        with self._active_response_lock:
            if self._active_response is response:
                self._active_response = None

    def cancel_active(self) -> bool:
        """Detach and close the active stream without leaking close failures."""
        with self._active_response_lock:
            response = self._active_response
            self._active_response = None
        closer = getattr(response, "close", None)
        if not callable(closer):
            return False
        try:
            closer()
        except Exception:
            # Cancellation is a best-effort wake-up path. The worker still
            # observes its cancellation flag at the next safe boundary, and a
            # broken SDK close must never escape into the terminal key handler.
            pass
        return True


class OpenAIRuntime(_CancelableResponseRuntime):
    """Official OpenAI Responses API adapter, imported only when selected."""

    backend = "openai_api"

    def __init__(self, api_key: str):
        if not api_key.strip():
            raise ValueError("OpenAI API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self._prompt_cache_key = self._cache_key(uuid.uuid4().hex)
        self._compaction_threshold: int | None = None
        self._init_active_response()

    @staticmethod
    def _cache_key(session_id: str) -> str:
        """Build a non-identifying, bounded cache-routing key."""
        digest = hashlib.sha256(session_id.encode("utf-8", errors="replace")).hexdigest()
        return f"klaude-session-{digest[:40]}"

    def set_session_context(self, session_id: str, context_window: int | None) -> None:
        """Bind cache routing and native compaction to one Klaude session."""
        self._prompt_cache_key = self._cache_key(session_id)
        window = int(context_window or 0)
        # Let provider compaction run before Agent's conservative local
        # extractive fallback. Tiny/unknown windows keep the local fallback.
        self._compaction_threshold = max(16_000, window * 3 // 4) if window >= 32_000 else None

    def _continuity_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"prompt_cache_key": self._prompt_cache_key}
        if self._compaction_threshold is not None:
            options["context_management"] = [
                {"type": "compaction", "compact_threshold": self._compaction_threshold}
            ]
        return options

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("OpenAI API support requires `klaude-core[cloud]`.") from exc
        return OpenAI(api_key=self.api_key)

    def fork_for_child(self) -> OpenAIRuntime:
        """Keep credentials while isolating mutable stream and usage state."""
        return OpenAIRuntime(self.api_key)

    def _response_create(self, **kwargs: Any):
        return self._client().responses.create(**kwargs)

    @classmethod
    def _input(cls, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Responses function calls are a protocol pair. History compaction,
        # cancellation, or restoration must never send only one side: an
        # orphaned function_call_output makes the entire conversation fail.
        call_ids = {
            str(call.get("id", ""))
            for message in messages
            if message.get("role") == "assistant"
            for call in message.get("tool_calls", []) or []
            if isinstance(call, dict) and call.get("id")
        }
        output_ids = {
            str(message.get("tool_call_id", ""))
            for message in messages
            if message.get("role") == "tool" and message.get("tool_call_id")
        }
        complete_call_ids = call_ids & output_ids
        result: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role")
            provider_items = cls._provider_input_items(message)
            has_provider_assistant_items = any(
                item.get("type") in {"message", "function_call"}
                for item in provider_items
            )
            for item in provider_items:
                if item.get("type") != "function_call" or str(
                    item.get("call_id", "")
                ) in complete_call_ids:
                    result.append(item)
            if role == "tool":
                call_id = str(message.get("tool_call_id", ""))
                if not call_id or call_id not in complete_call_ids:
                    continue
                result.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": _content(message),
                    }
                )
            elif role == "assistant" and has_provider_assistant_items:
                # Stateless Responses continuation replays the provider-issued
                # assistant items verbatim. Reconstructing the same assistant
                # text or function calls here would duplicate them.
                continue
            elif role == "assistant" and message.get("tool_calls"):
                for call in message["tool_calls"]:
                    call_id = str(call.get("id", ""))
                    if not call_id or call_id not in complete_call_ids:
                        continue
                    fn = call.get("function", {})
                    result.append(
                        {
                            "type": "function_call",
                            "call_id": call_id,
                            "name": fn.get("name", ""),
                            "arguments": fn.get("arguments", "{}"),
                        }
                    )
            elif role in {"system", "user", "assistant"}:
                result.append({"role": role, "content": _content(message)})
        compaction_indexes = [
            index for index, item in enumerate(result) if item.get("type") == "compaction"
        ]
        if not compaction_indexes:
            return result
        latest = compaction_indexes[-1]
        # The latest opaque item replaces older dialogue state, but Klaude's
        # current system contract remains authoritative and can change between
        # turns as capabilities and permissions change.
        current_instructions = [
            item
            for item in result[:latest]
            if item.get("role") in {"system", "developer"}
        ]
        return [*current_instructions, *result[latest:]]

    @staticmethod
    def _provider_input_items(message: dict[str, Any]) -> list[dict[str, Any]]:
        items = message.get("openai_response_items", [])
        return [dict(item) for item in items if isinstance(item, dict)]

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
            "include": ["reasoning.encrypted_content"],
            # Klaude is local-first. OpenAI Responses are retained by default,
            # so cloud calls explicitly opt out unless a future user setting
            # deliberately changes that privacy boundary.
            "store": False,
            **self._continuity_options(),
        }
        if think not in {None, False, "off", "auto"}:
            kwargs["reasoning"] = {"effort": str(think)}
        response = self._response_create(**kwargs)
        self._record(response)
        self._raise_for_terminal_response(response)
        return self._message(response)

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": model,
            "input": self._input(messages),
            "stream": True,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            **self._continuity_options(),
        }
        if tools:
            kwargs["tools"] = self._tools(tools)
        if think not in {None, False, "off", "auto"}:
            kwargs["reasoning"] = {"effort": str(think)}
        response_stream = self._track_active_response(self._response_create(**kwargs))
        completed = False
        streamed_text = False
        streamed_items: list[Any] = []
        try:
            for event in response_stream:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    streamed_text = True
                    yield {"role": "assistant", "content": getattr(event, "delta", "")}
                elif kind == "response.refusal.delta":
                    streamed_text = True
                    yield {"role": "assistant", "content": getattr(event, "delta", "")}
                elif kind == "response.output_item.done":
                    if (item := getattr(event, "item", None)) is not None:
                        streamed_items.append(item)
                elif kind == "response.completed":
                    response = getattr(event, "response", None)
                    if response is None:
                        raise RuntimeError(
                            "OpenAI stream completed without a terminal response."
                        )
                    self._record(response)
                    self._raise_for_terminal_response(response)
                    completed = True
                    terminal = self._message(response, streamed_items=streamed_items)
                    metadata = {
                        key: value
                        for key, value in terminal.items()
                        if key not in {"role", "content"}
                    }
                    yield {
                        "role": "assistant",
                        "content": "" if streamed_text else terminal.get("content", ""),
                        **metadata,
                    }
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
            self._clear_active_response(response_stream)
        if not completed:
            raise RuntimeError("OpenAI stream ended without a completed response.")

    def _record(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        self.last_chat_metadata = {
            "provider": self.backend,
            **(
                {"response_id": str(response_id)}
                if (response_id := getattr(response, "id", None))
                else {}
            ),
            **(
                {"status": str(status)}
                if (status := getattr(response, "status", None))
                else {}
            ),
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
    def _response_item(item: Any) -> dict[str, Any] | None:
        """Keep only provider state required for stateless Responses replay."""
        kind = str(getattr(item, "type", "") or "")
        if kind == "compaction":
            item_id = str(getattr(item, "id", "") or "").strip()
            encrypted = getattr(item, "encrypted_content", None)
            if not item_id or not encrypted:
                return None
            compaction_result: dict[str, Any] = {
                "id": item_id,
                "type": "compaction",
                "encrypted_content": str(encrypted),
            }
            if agent := getattr(item, "agent", None):
                compaction_result["agent"] = str(agent)
            return compaction_result
        if kind == "reasoning":
            item_id = str(getattr(item, "id", "") or "").strip()
            encrypted = getattr(item, "encrypted_content", None)
            if not item_id or not encrypted:
                return None
            summary: list[dict[str, Any]] = []
            for part in getattr(item, "summary", None) or []:
                if isinstance(part, dict):
                    dumped = dict(part)
                elif hasattr(part, "model_dump"):
                    dumped = part.model_dump(exclude_none=True)
                else:
                    part_type = getattr(part, "type", None)
                    text = getattr(part, "text", None)
                    dumped = {
                        **({"type": str(part_type)} if part_type else {}),
                        **({"text": str(text)} if text is not None else {}),
                    }
                if dumped:
                    summary.append(dumped)
            result: dict[str, Any] = {
                "id": item_id,
                "type": "reasoning",
                "summary": summary,
                "encrypted_content": str(encrypted),
            }
            if status := getattr(item, "status", None):
                result["status"] = str(status)
            return result
        if kind == "function_call":
            call_id = str(getattr(item, "call_id", "") or "").strip()
            name = str(getattr(item, "name", "") or "").strip()
            arguments = getattr(item, "arguments", None)
            if not call_id or not name or not isinstance(arguments, str):
                return None
            result = {
                "type": "function_call",
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            }
            if function_item_id := getattr(item, "id", None):
                result["id"] = str(function_item_id)
            if status := getattr(item, "status", None):
                result["status"] = str(status)
            return result
        if kind != "message" or getattr(item, "role", "") != "assistant":
            return None
        item_id = str(getattr(item, "id", "") or "").strip()
        if not item_id:
            return None
        content: list[dict[str, Any]] = []
        for part in getattr(item, "content", None) or []:
            part_type = str(getattr(part, "type", "") or "")
            if part_type == "output_text":
                annotations: list[dict[str, Any]] = []
                for annotation in getattr(part, "annotations", None) or []:
                    if isinstance(annotation, dict):
                        dumped_annotation = dict(annotation)
                    elif hasattr(annotation, "model_dump"):
                        dumped_annotation = annotation.model_dump(exclude_none=True)
                    else:
                        dumped_annotation = {}
                    if dumped_annotation:
                        annotations.append(dumped_annotation)
                content.append(
                    {
                        "type": "output_text",
                        "text": str(getattr(part, "text", "") or ""),
                        "annotations": annotations,
                    }
                )
            elif part_type == "refusal":
                content.append(
                    {
                        "type": "refusal",
                        "refusal": str(getattr(part, "refusal", "") or ""),
                    }
                )
        if not content:
            return None
        result = {
            "id": item_id,
            "type": "message",
            "role": "assistant",
            "content": content,
        }
        if status := getattr(item, "status", None):
            result["status"] = str(status)
        if phase := getattr(item, "phase", None):
            result["phase"] = str(phase)
        return result

    @classmethod
    def _message(cls, response: Any, *, streamed_items: list[Any] | None = None) -> dict[str, Any]:
        calls = []
        refusals: list[str] = []
        texts: list[str] = []
        response_items: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        # Some compatible Responses servers omit output from the terminal
        # envelope. Completed stream items remain authoritative evidence;
        # partial added/delta events must never become executable calls.
        for item in [*(getattr(response, "output", []) or []), *(streamed_items or [])]:
            kind = str(getattr(item, "type", ""))
            item_id = str(getattr(item, "call_id", "") or getattr(item, "id", ""))
            if item_id:
                identity = (kind, item_id)
                if identity in seen:
                    continue
                seen.add(identity)
            if replay_item := cls._response_item(item):
                response_items.append(replay_item)
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
                if kind == "message" and getattr(part, "type", "") == "output_text":
                    texts.append(str(getattr(part, "text", "") or ""))
                refusal = getattr(part, "refusal", None)
                if getattr(part, "type", "") == "refusal" and refusal:
                    refusals.append(str(refusal))
        content = getattr(response, "output_text", "") or "".join(texts)
        if not content and refusals:
            content = "\n".join(refusals)
        return {
            "role": "assistant",
            "content": content,
            **({"tool_calls": calls} if calls else {}),
            **({"openai_response_items": response_items} if response_items else {}),
        }


class OpenRouterRuntime(_CancelableResponseRuntime):
    """OpenRouter Chat Completions adapter with streaming tool assembly."""

    backend = "openrouter"
    base_url = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str):
        if not api_key.strip():
            raise ValueError("OpenRouter API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self._init_active_response()

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional cloud extra
            raise RuntimeError("OpenRouter support requires `klaude-core[cloud]`.") from exc
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    def fork_for_child(self) -> OpenRouterRuntime:
        return OpenRouterRuntime(self.api_key)

    @staticmethod
    def _messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        call_ids = {
            str(call.get("id", ""))
            for message in messages
            if message.get("role") == "assistant"
            for call in message.get("tool_calls", []) or []
            if isinstance(call, dict) and call.get("id")
        }
        output_ids = {
            str(message.get("tool_call_id", ""))
            for message in messages
            if message.get("role") == "tool" and message.get("tool_call_id")
        }
        complete_call_ids = call_ids & output_ids
        result: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", ""))
            if role == "tool":
                call_id = str(message.get("tool_call_id", ""))
                if call_id in complete_call_ids:
                    result.append(
                        {"role": "tool", "tool_call_id": call_id, "content": _content(message)}
                    )
                continue
            if role not in {"system", "user", "assistant"}:
                continue
            item: dict[str, Any] = {"role": role, "content": _content(message)}
            calls = message.get("tool_calls")
            if role == "assistant" and isinstance(calls, list) and calls:
                complete_calls = []
                for call in calls:
                    if (
                        not isinstance(call, dict)
                        or str(call.get("id", "")) not in complete_call_ids
                    ):
                        continue
                    function = call.get("function", {})
                    if not isinstance(function, dict):
                        continue
                    arguments = function.get("arguments", "{}")
                    if not isinstance(arguments, str):
                        arguments = json.dumps(arguments)
                    complete_calls.append(
                        {
                            "id": str(call["id"]),
                            "type": "function",
                            "function": {
                                "name": str(function.get("name", "")),
                                "arguments": arguments,
                            },
                        }
                    )
                if complete_calls:
                    item["tool_calls"] = complete_calls
            reasoning_details = message.get("openrouter_reasoning_details")
            all_calls_complete = not calls or (
                isinstance(calls, list)
                and all(
                    isinstance(call, dict)
                    and str(call.get("id", "")) in complete_call_ids
                    for call in calls
                )
            )
            if (
                role == "assistant"
                and isinstance(reasoning_details, list)
                and all_calls_complete
            ):
                # OpenRouter requires this sequence to be echoed unchanged and
                # in order across tool continuations. It remains private model
                # state and is never rendered as transcript text.
                item["reasoning_details"] = reasoning_details
            result.append(item)
        return result

    @staticmethod
    def _attribute(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _reasoning_details(value: Any) -> list[dict[str, Any]]:
        details: list[dict[str, Any]] = []
        for item in value or []:
            mapped = _metadata_mapping(item)
            if mapped:
                details.append(mapped)
        return details

    @classmethod
    def _raise_chunk_error(cls, chunk: Any) -> None:
        error = cls._attribute(chunk, "error", None)
        if not error:
            return
        if cls._attribute(error, "code", None) == 402:
            raise RuntimeError(
                "OpenRouter request exceeds available credits; reduce the output budget "
                "or add credits."
            )
        message = cls._attribute(error, "message", None)
        raise RuntimeError(str(message or "OpenRouter stream failed."))

    def _stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        think: bool | str | None,
        options: dict[str, Any] | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        output_limit = (options or {}).get("num_predict", 2048)
        kwargs["max_tokens"] = (
            output_limit
            if isinstance(output_limit, int)
            and not isinstance(output_limit, bool)
            and output_limit > 0
            else 2048
        )
        if tools:
            kwargs["tools"] = tools
        if think not in {None, False, "off", "auto"}:
            kwargs["extra_body"] = {"reasoning": {"effort": str(think)}}
        try:
            return self._client().chat.completions.create(**kwargs)
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status == 402:
                raise RuntimeError(
                    "OpenRouter request exceeds available credits; reduce the output budget "
                    "or add credits."
                ) from None
            if isinstance(status, int):
                # SDK exception strings can include account IDs and response
                # bodies. Keep status diagnostics without persisting that body.
                raise RuntimeError(f"OpenRouter request rejected (HTTP {status}).") from None
            raise

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        response_stream = self._track_active_response(
            self._stream(model, messages, tools, think, options=options)
        )
        content: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        reasoning_details: list[dict[str, Any]] = []
        response_id = ""
        usage: Any = None
        completed = False
        try:
            for chunk in response_stream:
                self._raise_chunk_error(chunk)
                response_id = str(self._attribute(chunk, "id", response_id) or response_id)
                usage = self._attribute(chunk, "usage", None) or usage
                choices = self._attribute(chunk, "choices", []) or []
                for choice in choices:
                    if self._attribute(choice, "finish_reason", None) is not None:
                        completed = True
                    delta = self._attribute(choice, "delta", {}) or {}
                    reasoning_details.extend(
                        self._reasoning_details(
                            self._attribute(delta, "reasoning_details", [])
                        )
                    )
                    if piece := self._attribute(delta, "content", ""):
                        content.append(str(piece))
                    for fragment in self._attribute(delta, "tool_calls", []) or []:
                        index = int(self._attribute(fragment, "index", 0) or 0)
                        current = calls.setdefault(
                            index,
                            {"id": "", "function": {"name": "", "arguments": ""}},
                        )
                        if call_id := self._attribute(fragment, "id", ""):
                            current["id"] = str(call_id)
                        function = self._attribute(fragment, "function", {}) or {}
                        if name := self._attribute(function, "name", ""):
                            current["function"]["name"] += str(name)
                        if arguments := self._attribute(function, "arguments", ""):
                            current["function"]["arguments"] += str(arguments)
        finally:
            self._clear_active_response(response_stream)
        if not completed:
            raise RuntimeError("OpenRouter stream ended without a completion reason.")
        assembled_calls = [calls[index] for index in sorted(calls)]
        for call in assembled_calls:
            if not call["id"] or not call["function"]["name"]:
                raise RuntimeError("OpenRouter returned a malformed function call.")
            try:
                arguments = json.loads(call["function"]["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                raise RuntimeError("OpenRouter returned malformed function arguments.") from exc
            if not isinstance(arguments, dict):
                raise RuntimeError("OpenRouter returned non-object function arguments.")
        self.last_chat_metadata = {
            "provider": self.backend,
            **({"response_id": response_id} if response_id else {}),
            "usage": _metadata_mapping(usage),
        }
        return {
            "role": "assistant",
            "content": "".join(content),
            **({"tool_calls": assembled_calls} if assembled_calls else {}),
            **(
                {"openrouter_reasoning_details": reasoning_details}
                if reasoning_details
                else {}
            ),
        }

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        response_stream = self._track_active_response(
            self._stream(model, messages, tools, think, options=options)
        )
        response_id = ""
        usage: Any = None
        reasoning_details: list[dict[str, Any]] = []
        calls: dict[int, dict[str, Any]] = {}
        completed = False
        try:
            for chunk in response_stream:
                self._raise_chunk_error(chunk)
                response_id = str(self._attribute(chunk, "id", response_id) or response_id)
                usage = self._attribute(chunk, "usage", None) or usage
                choices = self._attribute(chunk, "choices", []) or []
                for choice in choices:
                    if self._attribute(choice, "finish_reason", None) is not None:
                        completed = True
                    delta = self._attribute(choice, "delta", {}) or {}
                    reasoning_details.extend(
                        self._reasoning_details(
                            self._attribute(delta, "reasoning_details", [])
                        )
                    )
                    piece = self._attribute(delta, "content", "") or ""
                    if piece:
                        yield {"role": "assistant", "content": str(piece)}
                    for fragment in self._attribute(delta, "tool_calls", []) or []:
                        index = int(self._attribute(fragment, "index", 0) or 0)
                        current = calls.setdefault(
                            index,
                            {"id": "", "function": {"name": "", "arguments": ""}},
                        )
                        if call_id := self._attribute(fragment, "id", ""):
                            current["id"] = str(call_id)
                        function = self._attribute(fragment, "function", {}) or {}
                        if name := self._attribute(function, "name", ""):
                            current["function"]["name"] += str(name)
                        if arguments := self._attribute(function, "arguments", ""):
                            current["function"]["arguments"] += str(arguments)
            assembled_calls = [calls[index] for index in sorted(calls)]
            for call in assembled_calls:
                if not call["id"] or not call["function"]["name"]:
                    raise RuntimeError("OpenRouter returned a malformed function call.")
                try:
                    arguments = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError as exc:
                    raise RuntimeError("OpenRouter returned malformed function arguments.") from exc
                if not isinstance(arguments, dict):
                    raise RuntimeError("OpenRouter returned non-object function arguments.")
            if reasoning_details:
                yield {
                    "role": "assistant",
                    "content": "",
                    "openrouter_reasoning_details": reasoning_details,
                }
            if assembled_calls:
                yield {"role": "assistant", "content": "", "tool_calls": assembled_calls}
        finally:
            self._clear_active_response(response_stream)
            self.last_chat_metadata = {
                "provider": self.backend,
                **({"response_id": response_id} if response_id else {}),
                "usage": _metadata_mapping(usage),
            }
        if not completed:
            raise RuntimeError("OpenRouter stream ended without a completion reason.")


class CodexRuntime(OpenAIRuntime):
    """Responses adapter authenticated by the official Codex app-server."""

    backend = "openai_codex"

    def __init__(self, auth: CodexAuthManager | None = None):
        self.auth = auth or CodexAuthManager()
        self.last_chat_metadata: dict[str, Any] = {}
        self._init_active_response()
        self._session_id = str(uuid.uuid4())
        self._prompt_cache_key = self._cache_key(uuid.uuid4().hex)
        self._compaction_threshold: int | None = None

    def _client(self, *, refresh: bool = False):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("OpenAI Codex support requires `klaude-core[cloud]`.") from exc
        credentials = self.auth.credentials(refresh=refresh)
        version = credentials.broker_version.rsplit("/", 1)[-1]
        headers = {
            "ChatGPT-Account-ID": credentials.account_id,
            "originator": _CLIENT_ORIGINATOR,
            "session_id": self._session_id,
        }
        if version:
            headers["version"] = version
        return OpenAI(
            api_key=credentials.access_token,
            base_url=CODEX_RESPONSES_BASE_URL,
            default_headers=headers,
            max_retries=0,
        )

    def fork_for_child(self) -> CodexRuntime:
        """Use a fresh Codex session/stream tracker with the same auth broker."""
        return CodexRuntime(self.auth)

    def _response_create(self, **kwargs: Any):
        # The ChatGPT-authenticated Codex Responses backend rejects buffered
        # requests.  Enforce this at the transport boundary as well as at the
        # public chat methods so a future internal caller cannot accidentally
        # send stream=false (or omit the flag).
        kwargs["stream"] = True
        kwargs.setdefault("include", ["reasoning.encrypted_content"])
        try:
            return self._client().responses.create(**kwargs)
        except Exception as exc:
            if getattr(exc, "status_code", None) != 401:
                raise
            try:
                return self._client(refresh=True).responses.create(**kwargs)
            except Exception as refreshed_exc:
                if getattr(refreshed_exc, "status_code", None) == 401:
                    raise CodexAuthError(
                        "OpenAI Codex authentication expired or was revoked. Run "
                        "`klaude auth login openai-codex` again."
                    ) from None
                raise

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        """Assemble a mandatory Codex stream for Klaude's tool loop."""
        kwargs: dict[str, Any] = {
            "model": model,
            "input": self._input(messages),
            "stream": True,
            "store": False,
            **self._continuity_options(),
        }
        if tools:
            kwargs["tools"] = self._tools(tools)
        if think not in {None, False, "off", "auto"}:
            kwargs["reasoning"] = {"effort": str(think)}
        response_stream = self._track_active_response(self._response_create(**kwargs))
        completed = None
        text_parts: list[str] = []
        refusals: list[str] = []
        calls: list[dict[str, Any]] = []
        reasoning_items: list[dict[str, Any]] = []
        streamed_items: list[Any] = []
        try:
            for event in response_stream:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    text_parts.append(str(getattr(event, "delta", "") or ""))
                elif kind == "response.refusal.delta":
                    refusals.append(str(getattr(event, "delta", "") or ""))
                elif kind == "response.output_item.done":
                    item = getattr(event, "item", None)
                    if item is not None:
                        streamed_items.append(item)
                    call = self._tool_call_item(item)
                    if call:
                        calls.append(call)
                    reasoning = self._reasoning_item(item)
                    if reasoning:
                        reasoning_items.append(reasoning)
                elif kind == "response.completed":
                    completed = getattr(event, "response", None)
                elif kind in {"response.failed", "response.incomplete"}:
                    response = getattr(event, "response", None)
                    self._record(response)
                    self._raise_for_terminal_response(response, fallback=kind)
                elif kind == "error":
                    error = getattr(event, "error", None)
                    detail = (
                        error.get("message")
                        if isinstance(error, dict)
                        else getattr(error, "message", None)
                    )
                    raise RuntimeError(str(detail or "OpenAI Codex response failed."))
        finally:
            self._clear_active_response(response_stream)
        if completed is None:
            raise RuntimeError("OpenAI Codex stream ended without a completed response.")
        self._record(completed)
        self._raise_for_terminal_response(completed)
        terminal = self._message(completed, streamed_items=streamed_items)
        for item in getattr(completed, "output", []) or []:
            call = self._tool_call_item(item)
            if call and all(existing["id"] != call["id"] for existing in calls):
                calls.append(call)
            reasoning = self._reasoning_item(item)
            if reasoning and all(
                existing["id"] != reasoning["id"] for existing in reasoning_items
            ):
                reasoning_items.append(reasoning)
        content = "".join(text_parts) or "".join(refusals) or str(terminal["content"])
        return {
            "role": "assistant",
            "content": content,
            **({"tool_calls": calls} if calls else {}),
            **({"codex_reasoning_items": reasoning_items} if reasoning_items else {}),
            **(
                {"openai_response_items": terminal["openai_response_items"]}
                if terminal.get("openai_response_items")
                else {}
            ),
        }

    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        kwargs: dict[str, Any] = {
            "model": model,
            "input": self._input(messages),
            "tools": self._tools(tools),
            "stream": True,
            "store": False,
            **self._continuity_options(),
        }
        if think not in {None, False, "off", "auto"}:
            kwargs["reasoning"] = {"effort": str(think)}
        response_stream = self._track_active_response(self._response_create(**kwargs))
        completed = False
        streamed_text = False
        streamed_items: list[Any] = []
        try:
            for event in response_stream:
                kind = getattr(event, "type", "")
                if kind in {"response.output_text.delta", "response.refusal.delta"}:
                    streamed_text = True
                    yield {"role": "assistant", "content": getattr(event, "delta", "") or ""}
                elif kind == "response.output_item.done":
                    if (item := getattr(event, "item", None)) is not None:
                        streamed_items.append(item)
                elif kind == "response.completed":
                    response = getattr(event, "response", None)
                    if response is None:
                        raise RuntimeError(
                            "OpenAI Codex stream completed without a terminal response."
                        )
                    self._record(response)
                    self._raise_for_terminal_response(response)
                    completed = True
                    terminal = self._message(response, streamed_items=streamed_items)
                    metadata = {
                        key: value
                        for key, value in terminal.items()
                        if key not in {"role", "content"}
                    }
                    yield {
                        "role": "assistant",
                        "content": "" if streamed_text else terminal.get("content", ""),
                        **metadata,
                    }
                elif kind in {"response.failed", "response.incomplete"}:
                    response = getattr(event, "response", None)
                    self._record(response)
                    self._raise_for_terminal_response(response, fallback=kind)
                elif kind == "error":
                    error = getattr(event, "error", None)
                    detail = (
                        error.get("message")
                        if isinstance(error, dict)
                        else getattr(error, "message", None)
                    )
                    raise RuntimeError(str(detail or "OpenAI Codex response failed."))
        finally:
            self._clear_active_response(response_stream)
        if not completed:
            raise RuntimeError("OpenAI Codex stream ended without a completed response.")

    @staticmethod
    def _tool_call_item(item: Any) -> dict[str, Any] | None:
        if getattr(item, "type", "") != "function_call":
            return None
        call_id = str(getattr(item, "call_id", "") or "").strip()
        name = str(getattr(item, "name", "") or "").strip()
        arguments = getattr(item, "arguments", "{}")
        if not call_id or not name:
            raise RuntimeError("OpenAI Codex returned a malformed function call.")
        if not isinstance(arguments, str):
            raise RuntimeError("OpenAI Codex returned non-text function arguments.")
        try:
            decoded = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI Codex returned malformed function arguments.") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("OpenAI Codex returned non-object function arguments.")
        return {
            "id": call_id,
            "function": {
                "name": name,
                "arguments": arguments,
            },
        }

    @staticmethod
    def _reasoning_item(item: Any) -> dict[str, Any] | None:
        replay_item = OpenAIRuntime._response_item(item)
        return replay_item if replay_item and replay_item.get("type") == "reasoning" else None

    @staticmethod
    def _provider_input_items(message: dict[str, Any]) -> list[dict[str, Any]]:
        response_items = message.get("openai_response_items", [])
        if isinstance(response_items, list) and response_items:
            return [dict(item) for item in response_items if isinstance(item, dict)]
        items = message.get("codex_reasoning_items", [])
        return [dict(item) for item in items if isinstance(item, dict)]

    @staticmethod
    def _message(response: Any, *, streamed_items: list[Any] | None = None) -> dict[str, Any]:
        message = OpenAIRuntime._message(response, streamed_items=streamed_items)
        reasoning_items = [
            item
            for item in message.get("openai_response_items", [])
            if item.get("type") == "reasoning"
        ]
        if reasoning_items:
            message["codex_reasoning_items"] = reasoning_items
        return message


_CLIENT_ORIGINATOR = "klaude_code"


def discover_codex_models(auth: CodexAuthManager | None = None) -> list[ModelInfo]:
    """Return the account-aware model catalog from official Codex."""
    try:
        listed = (auth or CodexAuthManager()).list_models()
    except Exception:
        return []
    result: list[ModelInfo] = []
    for item in listed:
        model_id = item.get("model") or item.get("id")
        if not isinstance(model_id, str) or not model_id or item.get("hidden") is True:
            continue
        efforts = []
        for option in item.get("supportedReasoningEfforts", []) or []:
            value = option.get("reasoningEffort") if isinstance(option, dict) else option
            if isinstance(value, str) and value:
                efforts.append(value)
        capabilities = ModelCapabilities(
            effort_levels=tuple(efforts) or ModelCapabilities().effort_levels,
            supports_tools=True,
            # The stable app-server catalog does not currently publish context
            # limits. Use a deliberately conservative cloud fallback rather
            # than inheriting a much smaller local Ollama num_ctx value.
            context_window=128_000,
        )
        result.append(
            ModelInfo(
                "openai_codex",
                model_id,
                str(item.get("displayName") or model_id),
                capabilities=capabilities,
            )
        )
    return sorted(result, key=newest_model_first_key)


class GeminiRuntime(_CancelableResponseRuntime):
    """google-genai adapter using manual function calling (no auto execution)."""

    backend = "gemini_api"

    def __init__(self, api_key: str):
        if not api_key.strip():
            raise ValueError("Gemini API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self._init_active_response()

    def _sdk(self):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError("Gemini API support requires `klaude-core[cloud].") from exc
        return genai, types

    def fork_for_child(self) -> GeminiRuntime:
        """Keep the API credential while isolating mutable response state."""
        return GeminiRuntime(self.api_key)

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
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        response_stream = self._track_active_response(
            self._request(model, messages, tools, True, think)
        )
        calls: list[dict[str, Any]] = []
        try:
            for chunk in response_stream:
                yield {"role": "assistant", "content": getattr(chunk, "text", "") or ""}
                for candidate in getattr(chunk, "candidates", []) or []:
                    for part in getattr(getattr(candidate, "content", None), "parts", []) or []:
                        call = getattr(part, "function_call", None)
                        if call is None:
                            continue
                        normalized: dict[str, Any] = {
                            "id": getattr(call, "id", ""),
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(dict(call.args or {})),
                            },
                        }
                        signature = getattr(part, "thought_signature", None)
                        if isinstance(signature, bytes) and signature:
                            normalized["thought_signature"] = base64.b64encode(
                                signature
                            ).decode("ascii")
                        if normalized not in calls:
                            calls.append(normalized)
                self.last_chat_metadata = {
                    "provider": "gemini_api",
                    "usage": getattr(chunk, "usage_metadata", None),
                }
            if calls:
                yield {"role": "assistant", "content": "", "tool_calls": calls}
        finally:
            self._clear_active_response(response_stream)


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
            and is_chat_model_id("openai_api", model_id)
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


def discover_openrouter_models(api_key: str) -> list[ModelInfo]:
    """Return text chat models from OpenRouter's authenticated public catalog."""
    if not api_key:
        return []
    try:
        runtime = OpenRouterRuntime(api_key)
        models = runtime._client().models.list()
    except Exception:
        return []
    result: list[ModelInfo] = []
    for item in getattr(models, "data", models) or []:
        metadata = _metadata_mapping(item)
        model_id = metadata.get("id", getattr(item, "id", ""))
        if not isinstance(model_id, str) or not model_id or not is_chat_model_id(
            "openrouter", model_id
        ):
            continue
        supported = (
            metadata.get("supported_parameters")
            or getattr(item, "supported_parameters", None)
            or ()
        )
        architecture_value = metadata.get("architecture") or getattr(
            item, "architecture", None
        )
        architecture = _metadata_mapping(architecture_value)
        output_modalities = architecture.get("output_modalities") or getattr(
            architecture_value, "output_modalities", None
        )
        if output_modalities and "text" not in output_modalities:
            continue
        context_length = metadata.get("context_length") or getattr(
            item, "context_length", None
        )
        reasoning = _metadata_mapping(
            metadata.get("reasoning") or getattr(item, "reasoning", None)
        )
        advertised_efforts = reasoning.get("supported_efforts")
        if advertised_efforts:
            effort_levels = tuple(
                value
                for value in advertised_efforts
                if value in {"low", "medium", "high"}
            )
            if not reasoning.get("mandatory"):
                effort_levels = ("off", *effort_levels)
        else:
            effort_levels = ModelCapabilities().effort_levels
        result.append(
            ModelInfo(
                "openrouter",
                model_id,
                str(metadata.get("name") or getattr(item, "name", "") or model_id),
                capabilities=ModelCapabilities(
                    effort_levels=effort_levels,
                    supports_tools=(not supported or "tools" in supported),
                    context_window=(
                        int(context_length)
                        if isinstance(context_length, int) and context_length > 0
                        else None
                    ),
                ),
                released_at=int(metadata.get("created") or getattr(item, "created", 0) or 0),
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
