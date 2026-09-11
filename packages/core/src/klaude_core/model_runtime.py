"""Provider-neutral chat model identities and runtimes.

The agent deliberately owns tool orchestration.  Runtimes only translate the
small common chat contract to a provider and return the same assistant-message
shape that the agent has always used.
"""

from __future__ import annotations

import base64
import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .codex_auth import CODEX_RESPONSES_BASE_URL, CodexAuthError, CodexAuthManager
from .ollama import Ollama

BACKEND_METADATA = {
    "ollama": ("Local", "Ollama"),
    "openai_api": ("Cloud", "OpenAI"),
    "gemini_api": ("Cloud", "Google"),
    "openai_codex": ("Cloud", "OpenAI Codex"),
    # Reserved for later agent bridges; they are intentionally not runnable.
    "codex": ("Cloud", "OpenAI"),
    "gemini_cli": ("Cloud", "Google"),
}


def is_chat_model_id(backend: str, model_id: str) -> bool:
    """Conservatively exclude endpoint-specific models from chat pickers."""
    if backend not in {"openai_api", "openai_codex"}:
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
    result: list[ModelInfo] = []
    for item in entries if isinstance(entries, list) else []:
        if not isinstance(item, dict):
            continue
        backend = item.get("backend")
        model_id = item.get("model_id")
        if (
            backend not in {"openai_api", "openai_codex", "gemini_api"}
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


def save_model_cache(path: Path, models: list[ModelInfo]) -> None:
    """Atomically cache public model identifiers only—never credentials."""
    payload = {
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
            if item.backend in {"openai_api", "openai_codex", "gemini_api"}
            and is_chat_model_id(item.backend, item.model_id)
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
        self._init_active_response()

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
            result.extend(cls._provider_input_items(message))
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
        return result

    @staticmethod
    def _provider_input_items(_message: dict[str, Any]) -> list[dict[str, Any]]:
        return []

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
        response = self._response_create(**kwargs)
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
        response_stream = self._track_active_response(self._response_create(**kwargs))
        completed = False
        try:
            for event in response_stream:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    yield {"role": "assistant", "content": getattr(event, "delta", "")}
                elif kind == "response.refusal.delta":
                    yield {"role": "assistant", "content": getattr(event, "delta", "")}
                elif kind == "response.completed":
                    response = getattr(event, "response", None)
                    if response is None:
                        raise RuntimeError(
                            "OpenAI stream completed without a terminal response."
                        )
                    self._record(response)
                    self._raise_for_terminal_response(response)
                    completed = True
                    terminal = self._message(response)
                    metadata = {
                        key: value
                        for key, value in terminal.items()
                        if key not in {"role", "content"}
                    }
                    if metadata:
                        yield {"role": "assistant", "content": "", **metadata}
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

class CodexRuntime(OpenAIRuntime):
    """Responses adapter authenticated by the official Codex app-server."""

    backend = "openai_codex"

    def __init__(self, auth: CodexAuthManager | None = None):
        self.auth = auth or CodexAuthManager()
        self.last_chat_metadata: dict[str, Any] = {}
        self._init_active_response()
        self._session_id = str(uuid.uuid4())

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
            "tools": self._tools(tools),
            "stream": True,
            "store": False,
        }
        if think not in {None, False, "off", "auto"}:
            kwargs["reasoning"] = {"effort": str(think)}
        response_stream = self._track_active_response(self._response_create(**kwargs))
        completed = None
        text_parts: list[str] = []
        refusals: list[str] = []
        calls: list[dict[str, Any]] = []
        reasoning_items: list[dict[str, Any]] = []
        try:
            for event in response_stream:
                kind = getattr(event, "type", "")
                if kind == "response.output_text.delta":
                    text_parts.append(str(getattr(event, "delta", "") or ""))
                elif kind == "response.refusal.delta":
                    refusals.append(str(getattr(event, "delta", "") or ""))
                elif kind == "response.output_item.done":
                    item = getattr(event, "item", None)
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
        terminal = self._message(completed)
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
        }

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
        response_stream = self._track_active_response(self._response_create(**kwargs))
        completed = False
        try:
            for event in response_stream:
                kind = getattr(event, "type", "")
                if kind in {"response.output_text.delta", "response.refusal.delta"}:
                    yield {"role": "assistant", "content": getattr(event, "delta", "") or ""}
                elif kind == "response.output_item.done":
                    reasoning = self._reasoning_item(getattr(event, "item", None))
                    if reasoning:
                        yield {
                            "role": "assistant",
                            "content": "",
                            "codex_reasoning_items": [reasoning],
                        }
                elif kind == "response.completed":
                    response = getattr(event, "response", None)
                    if response is None:
                        raise RuntimeError(
                            "OpenAI Codex stream completed without a terminal response."
                        )
                    self._record(response)
                    self._raise_for_terminal_response(response)
                    completed = True
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
        if getattr(item, "type", "") != "reasoning":
            return None
        item_id = getattr(item, "id", None)
        encrypted = getattr(item, "encrypted_content", None)
        if not item_id or not encrypted:
            return None
        # Responses reasoning input items require both `id` and `summary`, even
        # when the summary is empty. Preserve only the provider-issued opaque
        # continuation state; it stays in message metadata and is never
        # rendered as assistant text.
        summary: list[dict[str, Any]] = []
        for part in getattr(item, "summary", None) or []:
            if isinstance(part, dict):
                dumped = dict(part)
            elif hasattr(part, "model_dump"):
                dumped = part.model_dump(exclude_none=True)
            else:
                kind = getattr(part, "type", None)
                text = getattr(part, "text", None)
                dumped = {
                    **({"type": str(kind)} if kind else {}),
                    **({"text": str(text)} if text is not None else {}),
                }
            if dumped:
                summary.append(dumped)
        return {
            "id": str(item_id),
            "type": "reasoning",
            "summary": summary,
            "encrypted_content": str(encrypted),
        }

    @staticmethod
    def _provider_input_items(message: dict[str, Any]) -> list[dict[str, Any]]:
        items = message.get("codex_reasoning_items", [])
        return [dict(item) for item in items if isinstance(item, dict)]

    @staticmethod
    def _message(response: Any) -> dict[str, Any]:
        message = OpenAIRuntime._message(response)
        reasoning_items = []
        for item in getattr(response, "output", []) or []:
            reasoning = CodexRuntime._reasoning_item(item)
            if reasoning:
                reasoning_items.append(reasoning)
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
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ):
        response_stream = self._track_active_response(
            self._request(model, messages, None, True, think)
        )
        try:
            for chunk in response_stream:
                yield {"role": "assistant", "content": getattr(chunk, "text", "") or ""}
                self.last_chat_metadata = {
                    "provider": "gemini_api",
                    "usage": getattr(chunk, "usage_metadata", None),
                }
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
