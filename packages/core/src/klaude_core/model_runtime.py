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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from .codex_auth import CODEX_RESPONSES_BASE_URL, CodexAuthError, CodexAuthManager
from .ollama import Ollama
from .settings_store import atomic_write_private, read_settings, settings_lock

BACKEND_METADATA = {
    "ollama": ("Local", "Ollama"),
    "openai_compatible": ("Local", "Compatible API"),
    "openai_api": ("Cloud", "OpenAI"),
    "openrouter": ("Cloud", "OpenRouter"),
    "gemini_api": ("Cloud", "Google"),
    "openai_codex": ("Cloud", "OpenAI Codex"),
    "deepseek": ("Cloud", "DeepSeek"),
    "anthropic": ("Cloud", "Anthropic"),
    # Reserved for later agent bridges; they are intentionally not runnable.
    "codex": ("Cloud", "OpenAI"),
    "gemini_cli": ("Cloud", "Google"),
}
MAX_MODEL_CACHE_BYTES = 8_000_000


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
    if backend not in {"openai_api", "openai_codex", "openrouter", "gemini_api"}:
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
    tools_evidence: str = "unknown"
    thinking_types: tuple[str, ...] | None = None
    max_output_tokens: int | None = None
    supports_images: bool | None = None
    images_evidence: str = "unknown"

    @property
    def requires_thinking(self) -> bool:
        return self.thinking_types is not None and bool(self.thinking_types) \
            and "disabled" not in self.thinking_types


def gemini_capabilities(model: str, current: ModelCapabilities | None = None) -> ModelCapabilities:
    """Apply exact reviewed native capabilities without catalog discovery or model changes."""
    from .image_profiles import GEMINI_ROOT, gemini_image_profile

    caps = current or ModelCapabilities()
    profile = gemini_image_profile(GEMINI_ROOT, model)
    if profile is None:
        return caps
    return replace(
        caps, supports_images=True, images_evidence="official-profile:" + profile["reviewed"],
        thinking_types=profile["thinking_types"], effort_levels=profile["effort_levels"],
        context_window=min(caps.context_window or profile["context_window"],
                           profile["context_window"]),
        max_output_tokens=min(caps.max_output_tokens or profile["max_output_tokens"],
                              profile["max_output_tokens"]),
    )


@dataclass(frozen=True)
class ModelInfo:
    backend: str
    model_id: str
    display_name: str
    capabilities: ModelCapabilities = field(default_factory=ModelCapabilities)
    released_at: int = 0
    connection_id: str = ""
    connection_revision: str = ""
    connection_source: str = ""
    credential_revision: str = ""

    @property
    def ref(self) -> str:
        prefix = f"{self.backend}@{self.connection_id}" if self.connection_id else self.backend
        return f"{prefix}/{self.model_id}"

    @property
    def request_identity(self) -> tuple[str, str]:
        scope = (f"{self.backend}@{self.connection_id}:{self.connection_revision}"
                 if self.connection_id else self.backend)
        return scope, self.model_id

    @property
    def uses_configured_context(self) -> bool:
        """Unknown compatible servers receive a bounded budget, including remote ones."""
        return self.source == "Local" or self.backend == "openai_compatible"

    @property
    def source(self) -> str:
        if self.connection_source:
            return self.connection_source
        return BACKEND_METADATA.get(self.backend, ("Cloud", self.backend))[0]

    @property
    def provider(self) -> str:
        return BACKEND_METADATA.get(self.backend, ("Cloud", self.backend))[1]


def load_model_cache(path: Path) -> list[ModelInfo]:
    """Read public cached catalogs; malformed or oversized caches are ignored."""
    try:
        if path.is_symlink() or path.stat().st_size > MAX_MODEL_CACHE_BYTES:
            return []
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    entries = raw.get("models", []) if isinstance(raw, dict) else []
    return models_from_records(entries)


def models_from_records(entries: object) -> list[ModelInfo]:
    from .model_connections import BACKENDS, split_model_ref, validate_model_id

    result: list[ModelInfo] = []
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        backend = item.get("backend")
        model_id = item.get("model_id")
        if not isinstance(backend, str) or backend not in BACKENDS \
                or not is_chat_model_id(backend, str(model_id)):
            continue
        connection_id = item.get("connection_id", "")
        try:
            model_id = validate_model_id(model_id)
            if connection_id:
                split_model_ref(f"{backend}@{connection_id}/{model_id}")
            elif backend in {"ollama", "openai_compatible"}:
                continue
            released = max(0, int(item.get("released_at") or 0))
        except (ValueError, TypeError):
            continue
        window = item.get("context_window")
        effort = item.get("effort_levels")
        thinking = item.get("thinking_types")
        output = item.get("max_output_tokens")
        result.append(ModelInfo(
            backend, model_id, str(item.get("display_name") or model_id),
            capabilities=ModelCapabilities(
                effort_levels=tuple(effort) if isinstance(effort, list)
                and effort and all(isinstance(level, str) for level in effort)
                else ModelCapabilities().effort_levels,
                supports_tools=item.get("supports_tools", True) is True,
                context_window=window if type(window) is int and window > 0 else None,
                tools_evidence=str(item.get("tools_evidence") or "unknown"),
                thinking_types=tuple(thinking) if isinstance(thinking, list)
                and len(thinking) <= 3 and all(
                    isinstance(level, str) and level in {"disabled", "enabled", "adaptive"}
                    for level in thinking) else None,
                max_output_tokens=output if type(output) is int
                and 0 < output <= 2_000_000 else None,
                supports_images=item.get("supports_images")
                if type(item.get("supports_images")) is bool else None,
                images_evidence=str(item.get("images_evidence") or "unknown")[:128],
            ), released_at=released, connection_id=connection_id,
            connection_revision=str(item.get("connection_revision") or ""),
            connection_source=item.get("connection_source", "")
            if item.get("connection_source") in {"Local", "Cloud"} else "",
            credential_revision=str(item.get("credential_revision") or ""),
        ))
    return result


def model_records(models: list[ModelInfo]) -> list[dict[str, Any]]:
    """Serialize only public catalog fields, for caches and private worker IPC."""
    return [
        {
            "backend": item.backend, "model_id": item.model_id,
            "display_name": item.display_name,
            "effort_levels": list(item.capabilities.effort_levels),
            "supports_tools": item.capabilities.supports_tools,
            "context_window": item.capabilities.context_window,
            "tools_evidence": item.capabilities.tools_evidence,
            "thinking_types": list(item.capabilities.thinking_types)
            if item.capabilities.thinking_types is not None else None,
            "max_output_tokens": item.capabilities.max_output_tokens,
            "supports_images": item.capabilities.supports_images,
            "images_evidence": item.capabilities.images_evidence,
            "released_at": item.released_at,
            "connection_id": item.connection_id,
            "connection_revision": item.connection_revision,
            "connection_source": item.connection_source,
            "credential_revision": item.credential_revision,
        }
        for item in models
        if (item.connection_id or item.backend in {
            "openai_api", "openai_codex", "openrouter", "gemini_api",
        }) and is_chat_model_id(item.backend, item.model_id)
    ]


def model_cache_generation(path: Path, backend: str) -> str:
    raw = read_settings(path).get("generations", {})
    return str(raw.get(backend, "")) if isinstance(raw, dict) else ""


def save_model_cache(
    path: Path, models: list[ModelInfo], *, backend: str | None = None,
    expected_generation: str | None = None, invalidate: bool = False,
    connection_id: str = "",
) -> bool:
    """Merge one provider under a lock and reject results invalidated during discovery.

    The unscoped form remains an explicit full snapshot for bootstrap/tests.
    Production refreshes and logout/key changes must pass a backend.
    """
    try:
        with settings_lock(path):
            if path.exists() and path.stat().st_size > MAX_MODEL_CACHE_BYTES:
                return False
            payload = read_settings(path)
            generations = payload.get("generations", {})
            generations = dict(generations) if isinstance(generations, dict) else {}
            if backend is not None:
                scope = f"{backend}@{connection_id}" if connection_id else backend
                if (
                    expected_generation is not None
                    and generations.get(scope, "") != expected_generation
                ):
                    return False
                if invalidate:
                    generations[scope] = uuid.uuid4().hex
                existing = models_from_records(payload.get("models", []))
                models = [item for item in existing if (item.backend, item.connection_id)
                          != (backend, connection_id)] + [
                    item for item in models
                    if (item.backend, item.connection_id) == (backend, connection_id)
                ]
            payload.update(models=model_records(models), generations=generations)
            serialized = json.dumps(payload, indent=2) + "\n"
            if len(serialized.encode()) > MAX_MODEL_CACHE_BYTES:
                return False
            atomic_write_private(path, serialized)
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

    def supports_structured_tool_recovery(self, model: str, tools: list[dict]) -> bool:
        supports = getattr(self.ollama, "supports_structured_tool_recovery", None)
        return bool(callable(supports) and supports(model, tools))

    @property
    def supports_bound_action_arguments(self) -> bool:
        return bool(getattr(self.ollama, "supports_bound_action_arguments", False))

    def chat_structured_action(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.ollama.chat_structured_action(*args, **kwargs)

    def chat_workspace_plan(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.ollama.chat_workspace_plan(*args, **kwargs)

    def cancel_active(self) -> bool:
        return self.ollama.cancel_active()

    def fork_for_child(self) -> OllamaRuntime:
        """Create an independent transport tracker for child model requests."""
        return OllamaRuntime(Ollama(self.ollama.base_url, timeout=self.ollama.timeout,
                   api_key=self.ollama.api_key, trust_env=self.ollama.trust_env))

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

    def __init__(self, api_key: str, *, base_url: str = "", request_timeout: float | None = None):
        self.base_url = base_url
        self.request_timeout=request_timeout
        if not api_key.strip():
            raise ValueError("OpenAI API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self._prompt_cache_key = self._cache_key(uuid.uuid4().hex)
        self._compaction_threshold: int | None = None
        self.image_model = ""
        self._image_transport: Any = None
        self.stream_response_limit, self.stream_event_limit = 16_000_000, 1_000_000
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
        return OpenAI(api_key=self.api_key, **({"base_url": self.base_url}
                                              if self.base_url else {}),
                      **({"timeout":self.request_timeout,"max_retries":0}
                         if self.request_timeout is not None else {}))

    def fork_for_child(self) -> OpenAIRuntime:
        """Keep credentials while isolating mutable stream and usage state."""
        child = OpenAIRuntime(self.api_key, base_url=self.base_url,
                              request_timeout=self.request_timeout)
        child.image_model = self.image_model
        return child

    def cancel_active(self) -> bool:
        transport = getattr(self, "_image_transport", None)
        cancelled = bool(transport and transport.cancel_active())
        return super().cancel_active() or cancelled

    def close(self) -> None:
        self.cancel_active()
        if getattr(self, "_image_transport", None) is not None:
            self._image_transport.close()

    def _request_input(self, model: str, messages: list[dict]) -> list[dict]:
        images = any(message.get("image_content") is not None for message in messages)
        if images and (self.backend != "openai_api" or self.image_model != model):
            raise RuntimeError("Image support has not been verified for this model")
        return self._input(messages, include_images=images)

    def _response_create(self, **kwargs: Any):
        if any(isinstance(item.get("content"), list) and any(
            part.get("type") == "input_image" for part in item["content"]
            if isinstance(part, dict)
        ) for item in kwargs.get("input", [])):
            from .image_profiles import OPENAI_ROOT, openai_image_profile
            from .openai_images import OpenAIImageTransport

            model = kwargs.get("model", "")
            endpoint = self.base_url or OPENAI_ROOT
            profile = openai_image_profile(endpoint, model)
            if self.image_model != model or profile is None:
                raise RuntimeError("Image support has not been verified for this model/endpoint")
            if kwargs.get("reasoning"):
                raise RuntimeError("This reviewed OpenAI image model requires Standard mode")
            limit = kwargs.get("max_output_tokens")
            limit = limit if type(limit) is int and limit > 0 else 2048
            if limit > profile["max_output_tokens"]:
                raise RuntimeError("Output budget exceeds this image model's documented limit")
            if self._image_transport is None:
                self._image_transport = OpenAIImageTransport(
                    endpoint, self.api_key, self.request_timeout or 600,
                )
            transport = self._image_transport
            transport.stream_response_limit = self.stream_response_limit
            transport.stream_event_limit = self.stream_event_limit
            kwargs["max_output_tokens"] = limit
            return transport.create(kwargs)
        if self.request_timeout is not None and not kwargs.get("stream"):
            with self._client() as client:
                return client.responses.create(**kwargs)
        return self._client().responses.create(**kwargs)

    @classmethod
    def _input(
        cls, messages: list[dict[str, Any]], *, include_images: bool = False,
    ) -> list[dict[str, Any]]:
        from .image_content import MAX_IMAGES, image_parts

        count = 0
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
            parts = image_parts(message) if include_images else []
            count += len(parts)
            if count > MAX_IMAGES:
                raise ValueError(f"Model requests accept at most {MAX_IMAGES} images")
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
                content: Any = _content(message)
                if parts:
                    content = [
                        {"type": "input_image", "detail": "auto", "image_url":
                         f"data:{part['mime_type']};base64,{part['data']}"} for part in parts
                    ] + [{"type": "input_text", "text": _content(message)}]
                result.append({"role": role, "content": content})
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
        retained_images = [
            {"role": "user", "content": [
                {"type": "input_text", "text": "Retained image pixels from this session."},
                *[part for part in item["content"] if part.get("type") == "input_image"],
            ]}
            for item in result[:latest] if isinstance(item.get("content"), list)
            and any(part.get("type") == "input_image" for part in item["content"])
        ] if include_images else []
        return [*current_instructions, result[latest], *retained_images, *result[latest + 1:]]

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
            "input": self._request_input(model, messages),
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
        if options and type(options.get("num_predict")) is int and options["num_predict"]>0:
            kwargs["max_output_tokens"] = options["num_predict"]
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
            "input": self._request_input(model, messages),
            "stream": True,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            **self._continuity_options(),
        }
        if tools:
            kwargs["tools"] = self._tools(tools)
        if options and type(options.get("num_predict")) is int and options["num_predict"] > 0:
            kwargs["max_output_tokens"] = options["num_predict"]
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


def chat_completion_messages(
    messages: list[dict[str, Any]], *, include_reasoning: bool = False,
    deepseek_scope: tuple[str, str] | None = None,
    include_images: bool = False,
) -> list[dict[str, Any]]:
    from .image_content import MAX_IMAGES, image_parts

    image_count = 0
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
        parts = image_parts(message) if include_images else []
        image_count += len(parts)
        if image_count > MAX_IMAGES:
            raise ValueError(f"Model requests accept at most {MAX_IMAGES} images")
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
        if parts:
            item["content"] = [
                {"type": "image_url", "image_url": {
                    "url": f"data:{part['mime_type']};base64,{part['data']}",
                }} for part in parts
            ] + [{"type": "text", "text": _content(message)}]
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
            include_reasoning and role == "assistant"
            and isinstance(reasoning_details, list)
            and all_calls_complete
        ):
            # OpenRouter requires this sequence to be echoed unchanged and
            # in order across tool continuations. It remains private model
            # state and is never rendered as transcript text.
            item["reasoning_details"] = reasoning_details
        if deepseek_scope is not None and role == "assistant" and all_calls_complete:
            continuation = message.get("deepseek_continuation")
            if (isinstance(continuation, dict)
                    and (continuation.get("scope"), continuation.get("model")) == deepseek_scope
                    and isinstance(continuation.get("reasoning_content"), str)):
                item["reasoning_content"] = continuation["reasoning_content"]
        result.append(item)
    return result


def validated_chat_calls(calls: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Let the agent retry a bad provider call without exposing its arguments."""
    assembled = [calls[index] for index in sorted(calls)]
    for call in assembled:
        function = call["function"]
        if not call["id"] or not function["name"]:
            return [{"function": {"name": "", "arguments": "{}"},
                     "parse_status": "malformed"}]
        try:
            arguments = json.loads(function["arguments"] or "{}")
        except json.JSONDecodeError:
            return [{"function": {"name": "", "arguments": "{}"},
                     "parse_status": "malformed"}]
        if not isinstance(arguments, dict):
            return [{"function": {"name": "", "arguments": "{}"},
                     "parse_status": "malformed"}]
    return assembled


class OpenRouterRuntime(_CancelableResponseRuntime):
    """OpenRouter Chat Completions adapter with streaming tool assembly."""

    backend = "openrouter"
    base_url = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, *, base_url: str = "", request_timeout: float | None = None):
        self.request_timeout=request_timeout
        self._bounded_client: Any = None
        if base_url:
            self.base_url = base_url
        if not api_key.strip():
            raise ValueError("OpenRouter API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self.image_model = ""
        self._image_transport: Any = None
        self._init_active_response()

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - optional cloud extra
            raise RuntimeError("OpenRouter support requires `klaude-core[cloud]`.") from exc
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            **({"timeout":self.request_timeout,"max_retries":0}
               if self.request_timeout is not None else {}),
        )

    def fork_for_child(self) -> OpenRouterRuntime:
        child = OpenRouterRuntime(self.api_key, base_url=self.base_url,
                                  request_timeout=self.request_timeout)
        child.image_model = self.image_model
        return child

    def _image_client(self, model: str, messages: list[dict]) -> Any:
        if not any(message.get("image_content") is not None for message in messages):
            return None
        if self.image_model != model:
            raise RuntimeError("Image support has not been verified for this model")
        if self._image_transport is None:
            from .openrouter_images import OpenRouterImages

            self._image_transport = OpenRouterImages(
                self.base_url, self.api_key, self.request_timeout or 600,
            )
        self._image_transport.image_model = model
        return self._image_transport

    def cancel_active(self) -> bool:
        image_cancelled = bool(self._image_transport and self._image_transport.cancel_active())
        return super().cancel_active() or image_cancelled

    def close(self) -> None:
        self.cancel_active()
        if self._image_transport is not None:
            self._image_transport.close()
        if self._bounded_client is not None:
            self._bounded_client.close()

    @staticmethod
    def _messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return chat_completion_messages(messages, include_reasoning=True)

    @staticmethod
    def _attribute(value: Any, name: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _validated_calls(calls: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
        return validated_chat_calls(calls)

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
        if think is False or think == "off":
            kwargs["extra_body"] = {"reasoning": {"enabled": False}}
        elif think is True:
            kwargs["extra_body"] = {"reasoning": {"enabled": True}}
        elif think not in {None, "auto"}:
            kwargs["extra_body"] = {"reasoning": {"effort": str(think)}}
        try:
            client=self._client()
            if self.request_timeout is not None:
                self._bounded_client=client
            return client.chat.completions.create(**kwargs)
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
                from .compatible_runtime import CompatibleModelError

                raise CompatibleModelError(
                    f"OpenRouter request rejected (HTTP {status}).",status_code=status) from None
            raise

    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> dict[str, Any]:
        self.last_chat_metadata = {}
        image_client = self._image_client(model, messages)
        if image_client is not None:
            try:
                return image_client.chat(model, messages, tools, options, think)
            finally:
                self.last_chat_metadata = dict(image_client.last_chat_metadata)
        response_stream = self._track_active_response(
            self._stream(model, messages, tools, think, options=options)
        )
        content: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        reasoning_details: list[dict[str, Any]] = []
        response_id = ""
        usage: Any = None
        completed = False
        finish_reason: str | None = None
        try:
            for chunk in response_stream:
                self._raise_chunk_error(chunk)
                response_id = str(self._attribute(chunk, "id", response_id) or response_id)
                usage = self._attribute(chunk, "usage", None) or usage
                choices = self._attribute(chunk, "choices", []) or []
                for choice in choices:
                    if self._attribute(choice, "finish_reason", None) is not None:
                        completed = True
                        finish_reason=str(self._attribute(choice,"finish_reason"))
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
            # Usage is evidence of consumed inference even when the terminal
            # status or assembled calls are invalid. Never publish partial
            # calls/private reasoning to make that accounting available.
            self.last_chat_metadata = {
                "provider": self.backend,
                **({"finish_reason": finish_reason} if finish_reason else {}),
                **({"response_id": response_id} if response_id else {}),
                "usage": _metadata_mapping(usage),
            }
        if not completed:
            raise RuntimeError("OpenRouter stream ended without a completion reason.")
        if finish_reason == "length":
            raise RuntimeError("OpenRouter output limit reached")
        if finish_reason not in {"stop", "tool_calls"}:
            raise RuntimeError("OpenRouter response did not complete successfully")
        assembled_calls = self._validated_calls(calls)
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
        self.last_chat_metadata = {}
        image_client = self._image_client(model, messages)
        if image_client is not None:
            try:
                yield from image_client.chat_stream(model, messages, tools, options, think)
            finally:
                self.last_chat_metadata = dict(image_client.last_chat_metadata)
            return
        response_stream = self._track_active_response(
            self._stream(model, messages, tools, think, options=options)
        )
        response_id = ""
        usage: Any = None
        reasoning_details: list[dict[str, Any]] = []
        calls: dict[int, dict[str, Any]] = {}
        completed = False
        finish_reason = ""
        try:
            for chunk in response_stream:
                self._raise_chunk_error(chunk)
                response_id = str(self._attribute(chunk, "id", response_id) or response_id)
                usage = self._attribute(chunk, "usage", None) or usage
                choices = self._attribute(chunk, "choices", []) or []
                for choice in choices:
                    if self._attribute(choice, "finish_reason", None) is not None:
                        completed = True
                        finish_reason = str(self._attribute(choice, "finish_reason"))
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
            if not completed:
                raise RuntimeError("OpenRouter stream ended without a completion reason.")
            if finish_reason == "length":
                raise RuntimeError("OpenRouter output limit reached")
            if finish_reason not in {"stop", "tool_calls"}:
                raise RuntimeError("OpenRouter response did not complete successfully")
            assembled_calls = self._validated_calls(calls)
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
                **({"finish_reason": finish_reason} if finish_reason else {}),
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


def discover_codex_models(
    auth: CodexAuthManager | None = None, *, strict: bool = False,
) -> list[ModelInfo]:
    """Return the account-aware model catalog from official Codex."""
    try:
        listed = (auth or CodexAuthManager()).list_models()
    except Exception:
        if strict:
            raise
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
    base_url = "https://generativelanguage.googleapis.com"

    def __init__(self, api_key: str, *, request_timeout: float | None = None):
        self.request_timeout=request_timeout
        self._bounded_client: Any = None
        if not api_key.strip():
            raise ValueError("Gemini API key is not configured.")
        self.api_key = api_key
        self.last_chat_metadata: dict[str, Any] = {}
        self.image_model = ""
        self._image_transport: Any = None
        self.stream_response_limit, self.stream_event_limit = 16_000_000, 1_000_000
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
        child = GeminiRuntime(self.api_key,request_timeout=self.request_timeout)
        child.image_model = self.image_model
        return child

    def _image_client(self, model: str, messages: list[dict]) -> Any:
        images = any(m.get("image_content") is not None for m in messages)
        continuation = any(m.get("gemini_continuation") for m in messages)
        from .image_profiles import gemini_image_profile

        profile = gemini_image_profile(self.base_url, model)
        if not images and not continuation and (
            profile is None or profile["thinking_control"] != "level"
        ):
            return None
        if profile is None:
            if images:
                raise RuntimeError("No reviewed image profile for this Gemini model/endpoint")
            return None
        if images and self.image_model != model:
            raise RuntimeError("Image support has not been verified for this model")
        if self._image_transport is None:
            from .gemini_images import GeminiImages

            self._image_transport = GeminiImages(self.api_key, self.request_timeout or 600)
        client = self._image_transport
        client.image_model = self.image_model
        client.stream_response_limit, client.stream_event_limit = (
            self.stream_response_limit, self.stream_event_limit,
        )
        return client

    def cancel_active(self) -> bool:
        cancelled = bool(self._image_transport and self._image_transport.cancel_active())
        return super().cancel_active() or cancelled

    def close(self) -> None:
        self.cancel_active()
        if self._image_transport is not None:
            self._image_transport.close()
        if self._bounded_client is not None:
            self._bounded_client.close()

    def _request(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        stream: bool,
        think: bool | str | None,
        options: dict[str, Any] | None = None,
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
        if options and type(options.get("num_predict")) is int and options["num_predict"]>0:
            config["max_output_tokens"] = options["num_predict"]
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
        client = genai.Client(api_key=self.api_key,**({"http_options":{
            "timeout":int(self.request_timeout*1000),"retry_options":{"attempts":1}}}
            if self.request_timeout is not None else {}))
        if self.request_timeout is not None:
            self._bounded_client=client
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
        image_client = self._image_client(model, messages)
        if image_client is not None:
            try:
                return image_client.chat(model, messages, tools, options, think)
            finally:
                self.last_chat_metadata = dict(image_client.last_chat_metadata)
        response = self._request(model, messages, tools, False, think, options=options)
        self.last_chat_metadata = {
            "provider": "gemini_api",
            "usage": getattr(response, "usage_metadata", None),
            "finish_reason":str(next((getattr(candidate,"finish_reason","")
                for candidate in getattr(response,"candidates",[]) or []),"")),
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
        image_client = self._image_client(model, messages)
        if image_client is not None:
            try:
                yield from image_client.chat_stream(model, messages, tools, options, think)
            finally:
                self.last_chat_metadata = dict(image_client.last_chat_metadata)
            return
        response_stream = self._track_active_response(
            self._request(model, messages, tools, True, think, options=options)
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
    from .image_profiles import OPENAI_IMAGE_REVIEW, OPENAI_ROOT, openai_image_profile
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
                    capabilities=ModelCapabilities(
                        supports_images=True if openai_image_profile(OPENAI_ROOT, model_id)
                        else None,
                        images_evidence="official-profile:" + OPENAI_IMAGE_REVIEW
                        if openai_image_profile(OPENAI_ROOT, model_id) else "unknown",
                    ),
                    released_at=int(getattr(item, "created", 0) or 0),
                )
            )
    return sorted(result, key=newest_model_first_key)


def discover_openrouter_models(api_key: str) -> list[ModelInfo]:
    """Return text chat models from OpenRouter's authenticated public catalog."""
    from .image_content import declared_images

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
        images = declared_images({"architecture": {
            **architecture,
            "input_modalities": architecture.get("input_modalities",
                                                  getattr(architecture_value,
                                                          "input_modalities", None)),
        }})
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
                    supports_images=images,
                    images_evidence="catalog:input_modalities" if images is not None else "unknown",
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


def discover_gemini_models(api_key: str, *, strict: bool = False) -> list[ModelInfo]:
    """Return Gemini generate-content models through the official SDK."""
    if not api_key:
        return []
    client = None
    try:
        runtime = GeminiRuntime(api_key)
        genai, _ = runtime._sdk()
        # The pager retains the transport, not its owning SDK Client. Keep the
        # owner alive until all pages are consumed, then explicitly close it.
        client = genai.Client(api_key=api_key, http_options={
            "timeout": 5000, "retry_options": {"attempts": 1},
        })
        result = []
        for item in client.models.list():
            name = getattr(item, "name", "")
            methods = (getattr(item, "supported_actions", None)
                       or getattr(item, "supported_generation_methods", ()) or ())
            model_id = name.removeprefix("models/") if isinstance(name, str) else ""
            if model_id and is_chat_model_id("gemini_api", model_id) \
                    and (not methods or "generateContent" in methods):
                result.append(ModelInfo(
                    "gemini_api", model_id, model_id,
                    capabilities=gemini_capabilities(model_id),
                ))
        return sorted(result, key=newest_model_first_key)
    except Exception:
        if strict:
            raise
        return []
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
