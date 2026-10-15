"""Bounded catalog checks for explicitly configured model connections."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any

import httpx

from .image_content import declared_images
from .model_connections import ModelConnection, validate_model_id
from .model_runtime import (
    ModelCapabilities,
    ModelInfo,
    discover_codex_models,
    discover_gemini_models,
    is_chat_model_id,
)


class ModelDiscoveryError(RuntimeError):
    def __init__(self, status: str, message: str):
        self.status = status
        super().__init__(message)


def _anthropic_catalog(connection: ModelConnection, key: str) -> list[ModelInfo]:
    from .anthropic_runtime import API_VERSION, catalog_capabilities

    entries: list[dict[str, Any]] = []
    cursors: set[str] = set()
    size = 0
    cursor = ""
    try:
        with httpx.Client(
            base_url=connection.base_url,
            trust_env=False,
            follow_redirects=False,
            headers={"x-api-key": key, "anthropic-version": API_VERSION},
            timeout=httpx.Timeout(5.0, connect=3.0),
        ) as client:
            for _ in range(10):
                params: dict[str, Any] = {"limit": 100}
                if cursor:
                    params["after_id"] = cursor
                with client.stream("GET", "/models", params=params) as response:
                    code = response.status_code
                    if code != 200:
                        category = (
                            "authentication"
                            if code in {401, 403}
                            else "rate_limit"
                            if code == 429
                            else "missing_catalog"
                            if code == 404
                            else "service"
                        )
                        raise ModelDiscoveryError(
                            category, f"Anthropic catalog unavailable (HTTP {code})"
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        size += len(chunk)
                        if size > 1_000_000:
                            raise ModelDiscoveryError(
                                "malformed", "Anthropic catalog exceeds its size limit"
                            )
                payload = json.loads(body)
                page = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(page, list) or type(payload.get("has_more")) is not bool:
                    raise ValueError("Invalid catalog page")
                if any(not isinstance(item, dict) for item in page):
                    raise ValueError("Invalid model record")
                entries.extend(page)
                if len(entries) > 1000:
                    raise ValueError("Catalog exceeds 1000 models")
                if not payload["has_more"]:
                    break
                cursor = validate_model_id(payload.get("last_id"))
                if not page or cursor in cursors or cursor != page[-1].get("id"):
                    raise ValueError("Invalid pagination cursor")
                cursors.add(cursor)
            else:
                raise ValueError("Catalog exceeds 10 pages")
        result = []
        for entry in entries:
            model_id = validate_model_id(entry.get("id"))
            label = entry.get("display_name") or model_id
            validate_model_id(label)
            result.append(
                ModelInfo(
                    connection.backend,
                    model_id,
                    label,
                    catalog_capabilities(entry),
                    connection_id=connection.id,
                    connection_revision=connection.revision,
                    connection_source=connection.source,
                )
            )
        return list({item.ref: item for item in result}.values())
    except httpx.TimeoutException:
        raise ModelDiscoveryError("timeout", "Anthropic catalog timed out") from None
    except httpx.HTTPError:
        raise ModelDiscoveryError("network", "Cannot reach Anthropic connection") from None
    except (ValueError, UnicodeError):
        raise ModelDiscoveryError("malformed", "Malformed Anthropic catalog") from None


def discover_connection(connection: ModelConnection, key: str = "") -> list[ModelInfo]:
    """Read metadata only. The CLI owns an outer cancellable process deadline."""
    if not connection.enabled:
        raise ModelDiscoveryError("disabled", "Connection is disabled")
    if connection.key_env and not key:
        raise ModelDiscoveryError("authentication", "Referenced API key is not configured")
    if connection.backend == "anthropic":
        return _anthropic_catalog(connection, key)
    if connection.backend in {"gemini_api", "openai_codex"}:
        from .codex_auth import CodexAuthError

        try:
            models = (
                discover_gemini_models(key, strict=True)
                if connection.backend == "gemini_api"
                else discover_codex_models(strict=True)
            )
        except CodexAuthError:
            raise ModelDiscoveryError(
                "authentication", "Codex account unavailable; sign in"
            ) from None
        except Exception as exc:
            code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
            if code in {401, 403}:
                raise ModelDiscoveryError("authentication", "Model authentication failed") from None
            if code == 429:
                raise ModelDiscoveryError("rate_limit", "Model catalog is rate limited") from None
            raise ModelDiscoveryError(
                "service", "Native model catalog unavailable; check setup"
            ) from None
        return [
            replace(
                model,
                connection_id=connection.id,
                connection_revision=connection.revision,
                connection_source=connection.source,
            )
            for model in models[:1000]
        ]
    path = "/api/tags" if connection.backend == "ollama" else "/models"
    headers = {"Authorization": f"Bearer {key}"} if key else None
    try:
        with httpx.Client(
            base_url=connection.base_url,
            headers=headers,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(5.0, connect=3.0),
        ) as client:
            with client.stream("GET", path) as response:
                code = response.status_code
                if code in {401, 403}:
                    raise ModelDiscoveryError(
                        "authentication", f"Authentication failed (HTTP {code})"
                    )
                if code == 404:
                    raise ModelDiscoveryError("missing_catalog", "Model catalog endpoint not found")
                if code == 429:
                    raise ModelDiscoveryError("rate_limit", "Model catalog is rate limited")
                if code != 200:
                    raise ModelDiscoveryError("service", f"Model catalog unavailable (HTTP {code})")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 1_000_000:
                        raise ModelDiscoveryError(
                            "malformed", "Model catalog exceeds its size limit"
                        )
        payload = json.loads(body)
    except httpx.TimeoutException:
        raise ModelDiscoveryError("timeout", "Model catalog request timed out") from None
    except httpx.HTTPError:
        raise ModelDiscoveryError("network", "Cannot reach model connection") from None
    except (ValueError, UnicodeError):
        raise ModelDiscoveryError("malformed", "Malformed model catalog") from None
    field = "models" if connection.backend == "ollama" else "data"
    entries = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ModelDiscoveryError("malformed", "Model catalog has no model list")
    if len(entries) > 1000:
        raise ModelDiscoveryError("malformed", "Model catalog exceeds 1000 models")
    models_by_id: dict[str, ModelInfo] = {}
    for entry in entries:
        model_id = (
            entry.get("name" if field == "models" else "id") if isinstance(entry, dict) else None
        )
        try:
            model_id = validate_model_id(model_id)
        except ValueError:
            raise ModelDiscoveryError(
                "malformed", "Model catalog contains an invalid model ID"
            ) from None
        if not is_chat_model_id(connection.backend, model_id):
            continue
        try:
            images = declared_images(entry) \
                if connection.backend in {"openai_compatible", "openrouter"} else None
        except ValueError:
            raise ModelDiscoveryError("malformed", "Malformed image capability metadata") from None
        if connection.backend == "openai_api":
            from .image_profiles import OPENAI_IMAGE_REVIEW, openai_image_profile

            images = True if openai_image_profile(connection.base_url, model_id) else None
        # A catalog listing proves neither tool support nor available context.
        models_by_id[model_id] = ModelInfo(
            connection.backend,
            model_id,
            model_id,
            ModelCapabilities(
                effort_levels=("off", "low", "high", "max")
                if connection.backend == "deepseek"
                else ("off",),
                supports_images=images,
                images_evidence="official-profile:" + OPENAI_IMAGE_REVIEW
                if connection.backend == "openai_api" and images is True
                else "catalog:input_modalities" if images is not None else "unknown",
            ),
            connection_id=connection.id,
            connection_revision=connection.revision,
            connection_source=connection.source,
        )
    return sorted(models_by_id.values(), key=lambda model: model.model_id)


def probe_connection(request: dict[str, Any]) -> dict[str, Any]:
    """Private worker operation: reject stale definitions/keys before publishing."""
    from pathlib import Path
    from types import SimpleNamespace

    from .config import provider_credential_current
    from .model_connections import connection_registry
    from .model_management import write_registry
    from .model_runtime import model_records, save_model_cache
    from .settings_store import settings_lock

    cfg = SimpleNamespace(config_dir=Path(request["config_dir"]))
    connection = ModelConnection.from_record(request["connection"])
    key = str(request.get("key", ""))
    credential_revision = str(request.get("credential_revision", ""))
    start = time.monotonic()
    result: dict[str, Any] = {"status": "ok", "message": "Connection reached"}
    try:
        checked = (
            replace(connection, enabled=True) if request.get("include_disabled") else connection
        )
        models = discover_connection(checked, key)
        result["status"] = "ok" if models else "empty"
    except ModelDiscoveryError as exc:
        models = []
        result = {"status": exc.status, "message": str(exc)}
    except Exception:
        # SDK/account errors can include URLs/credentials; never relay them.
        models = []
        result = {"status": "service", "message": "Model catalog check failed"}
    models = [
        replace(
            model, credential_revision=credential_revision, connection_revision=connection.revision
        )
        for model in models
    ]
    registry = connection_registry(cfg)
    # Registry -> credentials -> cache is the single lock order for publication.
    with settings_lock(registry.path), settings_lock(cfg.config_dir / ".env"):
        current = registry.load().get(connection.id)
        if current != connection or (
            connection.key_env
            and not provider_credential_current(
                cfg.config_dir,
                connection.key_env,
                key,
                credential_revision,
            )
        ):
            return {"status": "stale", "message": "Connection changed; test again", "models": []}
        if result["status"] in {"ok", "empty"}:
            updated = save_model_cache(
                Path(request["cache_file"]),
                models,
                backend=connection.backend,
                connection_id=connection.id,
                expected_generation=request["generation"],
            )
            if not updated:
                return {"status": "stale", "message": "Catalog changed; test again", "models": []}
        payload = registry._read()
        check = {
            **result,
            "revision": connection.revision,
            "credential_revision": credential_revision,
            "checked_at": time.time(),
            "elapsed": round(time.monotonic() - start, 1),
        }
        payload.setdefault("checks", {})[connection.id] = check
        write_registry(registry, payload)
    return {
        **check,
        "models": model_records(models),
    }
