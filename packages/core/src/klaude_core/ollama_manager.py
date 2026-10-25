"""Reviewed native Ollama lifecycle; no generation, process or filesystem deletion."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from contextlib import ExitStack, closing
from dataclasses import asdict
from typing import Any

import httpx

from .config import provider_secret_revision
from .http_model_transport import CancellableHTTPTransport
from .model_connections import (
    DEFAULT_IDS,
    connection_key,
    connection_registry,
    legacy_connections,
    normalize_model_url,
)
from .model_management import reference_parts
from .settings_store import read_settings, settings_lock

MAX_BODY = 2_000_000
MAX_MODELS = 1000
MAX_STREAM = 32_000_000
MAX_LINE = 8192
PULL_TIMEOUT = 1800


class ManagerError(ValueError):
    def __init__(self, status: str, message: str):
        super().__init__(message)
        self.status = status


def text(value: Any, limit: int = 160) -> str:
    return "".join(c for c in str(value or "") if c.isprintable())[:limit]


def model_name(value: Any) -> str:
    part = r"[A-Za-z0-9][A-Za-z0-9._-]*"
    if (
        not isinstance(value, str)
        or len(value) > 200
        or not re.fullmatch(rf"{part}(?:/{part}){{0,3}}(?::{part})?", value)
    ):
        raise ManagerError("invalid", "Use an Ollama model:tag or hf.co/owner/repository:tag")
    if ":" not in value:
        value += ":latest"
    return value


def connections(cfg: Any) -> dict:
    registry = connection_registry(cfg)
    return registry.load() if registry.path.exists() else {c.id: c for c in legacy_connections(cfg)}


def endpoint(cfg: Any, identity: str, request: dict | None = None):
    item = connections(cfg).get(identity)
    if item is None or item.backend != "ollama" or item.source != "Local" or not item.enabled:
        raise ManagerError("unavailable", "Choose an enabled native Ollama endpoint")
    revision = provider_secret_revision(cfg.config_dir, item.key_env) if item.key_env else ""
    if request is not None and (
        request.get("revision") != item.revision
        or request.get("credential_revision", "") != revision
    ):
        raise ManagerError("changed", "Endpoint or credentials changed; reload and review again")
    return item, revision


def _number(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value < 2**63 else None


def _failure(status: int, payload: Any = None) -> ManagerError:
    # Provider error prose may contain keys, local paths or terminal controls.
    message = str(payload.get("error", "")).casefold() if isinstance(payload, dict) else ""
    if status in {401, 403}:
        return ManagerError(
            "authentication", "Ollama authentication failed; review endpoint access"
        )
    if "no space left" in message or "disk full" in message:
        return ManagerError("disk", "Ollama storage is full; free space on the selected server")
    if status == 404 or "not found" in message:
        return ManagerError("not_found", "Model or API operation unavailable on this Ollama server")
    if status == 429:
        return ManagerError("rate_limit", "Ollama request rate limited; retry later")
    return ManagerError("service", "Ollama rejected the operation; inspect the server")


class ManagerTransport(CancellableHTTPTransport):
    def __init__(self, connection: Any, key: str):
        super().__init__(
            connection.base_url,
            30,
            headers={"Authorization": f"Bearer {key}"} if key else None,
            trust_env=False,
        )

    def read(self, method: str, path: str, body: dict | None = None, *, empty: bool = False):
        with self._client.stream(
            method, path, json=body, timeout=httpx.Timeout(5, connect=3)
        ) as response:
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BODY:
                    raise ManagerError("malformed", "Ollama response exceeded its size limit")
            try:
                result = json.loads(data) if data else {} if empty else None
            except (ValueError, UnicodeError):
                result = None
            if response.status_code != 200:
                raise _failure(response.status_code, result)
            if not isinstance(result, dict):
                raise ManagerError("malformed", "Ollama returned malformed metadata")
            if result.get("error"):
                raise _failure(200, result)
            return result

    def models(self, path: str = "/api/tags") -> list[dict]:
        rows = self.read("GET", path).get("models")
        if not isinstance(rows, list) or len(rows) > MAX_MODELS:
            raise ManagerError("malformed", "Ollama returned an oversized or invalid model list")
        result = []
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ManagerError("malformed", "Ollama returned invalid model metadata")
            name = model_name(row.get("name") or row.get("model"))
            digest = row.get("digest", "")
            if not isinstance(digest, str) or not re.fullmatch(r"(?:sha256:)?[a-f0-9]{64}", digest):
                raise ManagerError("malformed", "Ollama returned an invalid model digest")
            if name in seen:
                raise ManagerError("malformed", "Ollama returned duplicate model identities")
            seen.add(name)
            details = row.get("details", {})
            if not isinstance(details, dict):
                raise ManagerError("malformed", "Ollama returned invalid model details")
            result.append(
                {
                    "name": name,
                    "digest": digest,
                    "size": _number(row.get("size")),
                    "modified": text(row.get("modified_at"), 80),
                    "parameters": text(details.get("parameter_size"), 40),
                    "quantization": text(details.get("quantization_level"), 40),
                    "family": text(details.get("family"), 60),
                    "vram": _number(row.get("size_vram")),
                    "context": _number(row.get("context_length")),
                }
            )
        return result

    def pull(self, name: str, emit: Callable[[dict], None]) -> None:
        client = self._chat_client_factory()
        self._track_request(client)
        pending = b""
        total_bytes = 0
        last = 0.0
        try:
            with client.stream(
                "POST",
                "/api/pull",
                json={"model": name, "stream": True},
                extensions={"trace": self._request_trace(client)},
            ) as response:
                self._attach_response(client, response)
                if response.status_code != 200:
                    error_body = bytearray()
                    for chunk in response.iter_bytes():
                        error_body.extend(chunk)
                        if len(error_body) > MAX_BODY:
                            raise _failure(response.status_code)
                    try:
                        error_data = json.loads(error_body)
                    except (ValueError, UnicodeError):
                        error_data = None
                    raise _failure(response.status_code, error_data)
                for chunk in response.iter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > MAX_STREAM:
                        raise ManagerError("malformed", "Ollama progress exceeded its stream limit")
                    pending += chunk
                    while b"\n" in pending:
                        raw, pending = pending.split(b"\n", 1)
                        if not raw.strip():
                            continue
                        if len(raw) > MAX_LINE:
                            raise ManagerError(
                                "malformed", "Ollama progress line exceeded its limit"
                            )
                        try:
                            item = json.loads(raw)
                        except (ValueError, UnicodeError):
                            raise ManagerError(
                                "malformed", "Ollama returned invalid progress"
                            ) from None
                        if not isinstance(item, dict):
                            raise ManagerError("malformed", "Ollama returned invalid progress")
                        if item.get("error"):
                            raise _failure(200, item)
                        status = item.get("status")
                        if not isinstance(status, str) or len(status) > 256:
                            raise ManagerError(
                                "malformed", "Ollama returned invalid progress status"
                            )
                        stage = (
                            "Complete"
                            if status == "success"
                            else "Downloading file"
                            if status.startswith("pulling ") and item.get("digest")
                            else "Checking manifest"
                            if status == "pulling manifest"
                            else "Verifying download"
                            if "verif" in status
                            else "Saving model"
                            if "manifest" in status
                            else "Preparing download"
                        )
                        completed, size = _number(item.get("completed")), _number(item.get("total"))
                        if completed is not None and size is not None and completed > size:
                            raise ManagerError("malformed", "Ollama progress exceeds file size")
                        now = time.monotonic()
                        if now - last >= 0.5 or status == "success":
                            emit({"stage": stage, "completed": completed, "total": size})
                            last = now
                        if status == "success":
                            return
                    if len(pending) > MAX_LINE:
                        raise ManagerError("malformed", "Ollama progress line exceeded its limit")
                # JSON streams must finish with the documented success event.
                raise ManagerError(
                    "incomplete", "Download stream ended without success; reload models"
                )
        finally:
            self._finish_request(client)
            client.close()


def role_models(cfg: Any, connection: Any, current: str = "") -> dict[str, list[str]]:
    from .ai_defaults import defaults_from_preferences

    saved = read_settings(cfg.data_dir / "chat-preferences.json")
    roles = {"Session model": current, **{f"Configured {k}": v for k, v in cfg.models.items()}}
    defaults = defaults_from_preferences(cfg, saved)
    roles.update(
        {"Default Chat": defaults.chat, "Utility": defaults.utility, "Research": defaults.research,
         "Vision": defaults.vision}
    )
    for index, ref in enumerate(defaults.fallbacks):
        roles[f"Utility fallback {index + 1}"] = ref
    for index, ref in enumerate(defaults.vision_fallbacks):
        roles[f"Vision fallback {index + 1}"] = ref
    definitions = connections(cfg)
    matched: dict[str, list[str]] = {}
    for label, reference in roles.items():
        if not isinstance(reference, str) or not reference:
            continue
        backend, identity, model = reference_parts(reference)
        other = definitions.get(identity)
        if backend in {"ollama", "openai_compatible"} and other \
                and normalize_model_url(other.base_url, "ollama") == connection.base_url:
            try:
                matched.setdefault(model_name(model), []).append(label)
            except ManagerError:
                pass
    return matched


def invalidate(cfg: Any, connection: Any) -> bool:
    from .model_runtime import save_model_cache

    registry = connection_registry(cfg)
    with settings_lock(registry.path):
        if connections(cfg).get(connection.id) != connection:
            return False
        path = cfg.data_dir / "model-cache.json"
        aliases = [
            c.id
            for c in connections(cfg).values()
            if c.backend == "ollama" and c.base_url == connection.base_url
        ]
        ok = True
        for identity in aliases:
            ok = (
                save_model_cache(
                    path, [], backend="ollama", connection_id=identity, invalidate=True
                )
                and ok
            )
        if DEFAULT_IDS["ollama"] in aliases:
            ok = save_model_cache(path, [], backend="ollama", invalidate=True) and ok
        return ok


def execute_manager(
    cfg: Any, request: dict, emit: Callable[[dict], None] = lambda _: None, *,
    before_effect: Callable[[], None] | None = None,
) -> dict:
    """Fixed operations shared by CLI and TUI owned workers."""
    operation = request.get("operation")
    try:
        if operation == "connections":
            return {
                "connections": [
                    {
                        **asdict(c),
                        "revision": c.revision,
                        "credential_revision": provider_secret_revision(cfg.config_dir, c.key_env)
                        if c.key_env
                        else "",
                    }
                    for c in connections(cfg).values()
                    if c.backend == "ollama" and c.source == "Local" and c.enabled
                ]
            }
        if operation == "hardware":
            from .runtime_context import collect_runtime_context

            hardware_result = collect_runtime_context(cfg, cfg.data_dir, force_refresh=True)
            system = hardware_result.context.system
            return {
                "hardware": {
                    "cpu": [asdict(c) for c in system.cpu[:8]],
                    "gpu": [asdict(g) for g in system.gpu[:8]],
                    "ram": system.memory_total_bytes,
                    "provider": hardware_result.context.provider,
                }
            }
        if operation == "search":
            from klaude_web.huggingface import hub_repo_search

            query = request.get("query", "")
            if (
                not isinstance(query, str)
                or not 1 <= len(query.strip()) <= 200
                or text(query, 200) != query
            ):
                raise ManagerError("invalid", "Enter a printable model query of 1–200 characters")
            found = hub_repo_search(
                cfg.huggingface_base_url,
                cfg.huggingface_api_key,
                "model",
                query,
                20,
                "downloads",
                filter_tag="gguf",
            )
            return {
                "results": [
                    {
                        "id": text(r["id"], 180),
                        "downloads": _number(r.get("downloads")),
                        "summary": text(r.get("summary"), 240),
                    }
                    for r in found
                ]
            }
        connection, credential = endpoint(
            cfg,
            request.get("endpoint", DEFAULT_IDS["ollama"]),
            request if operation in {"pull", "delete"} else None,
        )
        with closing(ManagerTransport(connection, connection_key(cfg, connection))) as client:
            if operation == "inventory":
                result: dict = {
                    "endpoint": {
                        **asdict(connection),
                        "revision": connection.revision,
                        "credential_revision": credential,
                    },
                    "checked_at": time.time(),
                }
                for field, path in (("models", "/api/tags"), ("running", "/api/ps")):
                    try:
                        result[field] = client.models(path)
                    except ManagerError as exc:
                        result[field] = None
                        result[field + "_error"] = str(exc)
                    except httpx.HTTPError:
                        result[field] = None
                        result[field + "_error"] = (
                            "Ollama metadata request failed; reload this server"
                        )
                try:
                    result["version"] = text(client.read("GET", "/api/version").get("version"), 80)
                except (ManagerError, httpx.HTTPError):
                    result["version"] = "Unavailable"
                result["bindings"] = role_models(cfg, connection, request.get("current", ""))
                return result
            if operation not in {"pull", "delete"}:
                raise ManagerError("invalid", "Unknown Model Manager operation")
            name = model_name(request.get("model"))
            lock = (
                cfg.data_dir
                / "model-manager"
                / hashlib.sha256(connection.base_url.encode()).hexdigest()
            )
            attempted = False
            cache = False
            try:
                with settings_lock(lock), ExitStack() as guards:
                    if operation == "delete":
                        guards.enter_context(settings_lock(connection_registry(cfg).path))
                        guards.enter_context(settings_lock(cfg.data_dir / "chat-preferences.json"))
                        guards.enter_context(settings_lock(cfg.config_dir / ".env"))
                    endpoint(cfg, connection.id, request)
                    models = client.models()
                    existing = next((m for m in models if m["name"] == name), None)
                    expected = request.get("digest", "")
                    if expected != (existing["digest"] if existing else ""):
                        raise ManagerError(
                            "changed", "Installed model changed; reload and review again"
                        )
                    running = client.models("/api/ps")
                    if any(
                        m["name"] == name or existing and m["digest"] == existing["digest"]
                        for m in running
                    ):
                        raise ManagerError(
                            "busy", "Model is loaded by Ollama; finish its work and unload it first"
                        )
                    if operation == "delete":
                        if existing is None:
                            raise ManagerError("not_found", "Model is no longer installed")
                        affected = role_models(cfg, connection, request.get("current", "")).get(
                            name, []
                        )
                        if affected:
                            raise ManagerError(
                                "bound", "Model is still selected: " + ", ".join(affected)
                            )
                        if before_effect is not None:
                            before_effect()
                        attempted = True
                        client.read("DELETE", "/api/delete", {"model": name}, empty=True)
                    else:
                        if before_effect is not None:
                            before_effect()
                        attempted = True
                        client.pull(name, emit)
                    after = client.models()
                    installed = any(m["name"] == name for m in after)
                    if installed != (operation == "pull"):
                        raise ManagerError(
                            "unconfirmed", "Ollama outcome unconfirmed; reload the selected server"
                        )
            finally:
                if attempted:
                    cache = invalidate(cfg, connection)
            return {
                "status": "ok",
                "operation": operation,
                "model": name,
                "endpoint": connection.id,
                "cache_invalidated": cache,
                "message": "Download verified"
                if operation == "pull"
                else "Model deletion verified",
            }
    except ManagerError as exc:
        return {"status": exc.status, "message": str(exc)}
    except httpx.TimeoutException:
        return {
            "status": "timeout",
            "message": "Model discovery timed out"
            if operation == "search"
            else "Ollama request timed out; reload to check its outcome",
        }
    except httpx.HTTPStatusError as exc:
        return {
            "status": "authentication" if exc.response.status_code in {401, 403} else "service",
            "message": "Hugging Face discovery rejected; review provider access",
        }
    except httpx.HTTPError:
        return {
            "status": "network",
            "message": "Hugging Face discovery connection failed; review provider setup"
            if operation == "search"
            else "Ollama connection failed; check the selected endpoint",
        }
    except (ValueError, OSError):
        return {
            "status": "unavailable",
            "message": "Model Manager unavailable; reload or inspect server setup",
        }
