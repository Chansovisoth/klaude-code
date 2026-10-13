"""Versioned model connections, private credential references and stable identities."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from .settings_store import (
    SettingsConflictError,
    atomic_write_private,
    read_settings,
    settings_lock,
)

CONNECTION_VERSION = 1
MAX_CONNECTIONS = 64
BACKENDS = frozenset(
    {
        "ollama",
        "openai_compatible",
        "openai_api",
        "openrouter",
        "gemini_api",
        "openai_codex",
        "deepseek",
        "anthropic",
    }
)
DEFAULT_URLS = {
    "openai_api": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "gemini_api": "https://generativelanguage.googleapis.com",
    "deepseek": "https://api.deepseek.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
}
DEFAULT_IDS = {backend: f"default-{backend.replace('_', '-')}" for backend in BACKENDS}
_IDENTITY = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def normalize_model_url(value: str, backend: str, source: str = "Local") -> str:
    """Normalize known API suffixes without discarding a gateway's path prefix."""
    if backend == "openai_codex":
        if value:
            raise ValueError("Codex account connections do not use an endpoint URL")
        return ""
    if not isinstance(value, str) or _CONTROL.search(value):
        raise ValueError("Endpoint URL contains invalid characters")
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid endpoint URL") from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or _CONTROL.search(unquote(value))
        or "\\" in value
        or any(char.isspace() for char in value)
    ):
        raise ValueError("Use an HTTP(S) endpoint without credentials, query or fragment")
    if source == "Cloud" and parsed.scheme != "https":
        raise ValueError("Cloud model connections require HTTPS")
    path = parsed.path.rstrip("/")
    if backend == "ollama" and path.endswith(("/api", "/v1")):
        path = path.rsplit("/", 1)[0]
    elif backend == "openai_compatible":
        if not path:
            path = "/v1"
        elif path == "/api" and port == 11434:
            path = "/v1"
    normalized = urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    if backend == "gemini_api" and normalized != DEFAULT_URLS[backend]:
        raise ValueError("Custom Gemini API addresses are not supported")
    return normalized


@dataclass(frozen=True)
class ModelConnection:
    id: str
    name: str
    backend: str
    base_url: str
    source: str = "Local"
    key_env: str = ""
    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _IDENTITY.fullmatch(self.id):
            raise ValueError("Connection ID must use 1–64 lowercase letters, digits, - or _")
        if not isinstance(self.name, str) or not 0 < len(self.name.strip()) <= 120:
            raise ValueError("Connection name must use 1–120 characters")
        if _CONTROL.search(self.name):
            raise ValueError("Connection name contains invalid characters")
        if (
            not isinstance(self.backend, str)
            or self.backend not in BACKENDS
            or not isinstance(self.source, str)
            or self.source not in {"Local", "Cloud"}
        ):
            raise ValueError("Unsupported model connection adapter or source")
        if not isinstance(self.enabled, bool):
            raise ValueError("Connection enabled state must be boolean")
        if (
            not isinstance(self.key_env, str)
            or self.key_env
            and not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", self.key_env)
        ):
            raise ValueError("Authentication must reference an environment variable")
        if self.backend == "openai_codex" and self.key_env:
            raise ValueError("Codex account authentication is separate from API keys")
        object.__setattr__(
            self, "base_url", normalize_model_url(self.base_url, self.backend, self.source)
        )
        object.__setattr__(self, "name", self.name.strip())

    @property
    def revision(self) -> str:
        # Only public configuration is hashed, never a secret or secret-derived value.
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()

    def model_ref(self, model_id: str) -> str:
        validate_model_id(model_id)
        return f"{self.backend}@{self.id}/{model_id}"

    @classmethod
    def from_record(cls, record: object) -> ModelConnection:
        if not isinstance(record, dict):
            raise ValueError("Invalid model connection record")
        if any(name in record for name in ("api_key", "secret", "password", "token")):
            raise ValueError("Model connections store credential references only")
        try:
            return cls(**{key: record[key] for key in cls.__dataclass_fields__ if key in record})
        except TypeError:
            raise ValueError("Incomplete model connection record") from None


def validate_model_id(model_id: object) -> str:
    if not isinstance(model_id, str) or not 0 < len(model_id) <= 256 or _CONTROL.search(model_id):
        raise ValueError("Invalid model ID")
    return model_id


def split_model_ref(value: str) -> tuple[str, str, str] | None:
    """Return adapter/connection/model, preserving slashes in provider model IDs."""
    prefix, separator, model_id = value.partition("/")
    if not separator or "@" not in prefix:
        return None
    backend, connection_id = prefix.split("@", 1)
    if backend not in BACKENDS or not _IDENTITY.fullmatch(connection_id):
        raise ValueError("Invalid endpoint-qualified model reference")
    validate_model_id(model_id)
    return backend, connection_id, model_id


def legacy_connections(cfg: Any) -> list[ModelConnection]:
    """Stable aliases for existing configuration; never reads account credentials."""
    result = [ModelConnection(DEFAULT_IDS["ollama"], "Ollama", "ollama", cfg.ollama_url)]
    for backend, label, variable in (
        ("openai_api", "OpenAI API", "OPENAI_API_KEY"),
        ("openrouter", "OpenRouter", "OPENROUTER_API_KEY"),
        ("gemini_api", "Gemini API", "GEMINI_API_KEY"),
    ):
        result.append(
            ModelConnection(
                DEFAULT_IDS[backend], label, backend, DEFAULT_URLS[backend], "Cloud", variable
            )
        )
    result.append(
        ModelConnection(DEFAULT_IDS["openai_codex"], "OpenAI Codex", "openai_codex", "", "Cloud")
    )
    return result


class ModelConnectionRegistry:
    """Definitions merge under the existing cross-client settings transaction."""

    def __init__(self, path: Path):
        self.path = path

    @staticmethod
    def _records(payload: dict[str, Any]) -> dict[str, ModelConnection]:
        if not payload:
            return {}
        if type(payload.get("version")) is not int or payload["version"] != CONNECTION_VERSION:
            raise ValueError("Unsupported model connection registry version")
        records = payload.get("connections")
        if not isinstance(records, dict) or len(records) > MAX_CONNECTIONS:
            raise ValueError("Invalid or oversized model connection registry")
        connections = {key: ModelConnection.from_record(value) for key, value in records.items()}
        if any(key != value.id for key, value in connections.items()):
            raise ValueError("Model connection identity does not match its registry key")
        return connections

    def _read(self) -> dict[str, Any]:
        try:
            metadata = self.path.lstat()
        except FileNotFoundError:
            return {}
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Model connection registry must be a regular file")
        if metadata.st_size > 1_000_000:
            raise ValueError("Model connection registry exceeds its size limit")
        return read_settings(self.path)

    def load(self) -> dict[str, ModelConnection]:
        return self._records(self._read())

    def migrate(self, cfg: Any, preferences: Path | None = None) -> dict[str, ModelConnection]:
        """Idempotently seed existing connections without rewriting roles or sessions."""
        with settings_lock(self.path):
            payload = self._read()
            current = self._records(payload)
            records = dict(payload.get("connections", {}))
            # Once initialized, deletion/disablement is explicit and must survive migration.
            if not payload:
                records = {item.id: asdict(item) for item in legacy_connections(cfg)}
                selected = read_settings(preferences).get("last_model") if preferences else None
                payload.update(
                    version=CONNECTION_VERSION,
                    connections=records,
                    legacy={
                        "startup_model": selected if isinstance(selected, str) else "",
                        "roles": dict(cfg.models),
                    },
                )
                atomic_write_private(self.path, json.dumps(payload, indent=2) + "\n")
                current = self._records(payload)
            return current

    def add(self, connection: ModelConnection, *, secret: str = "") -> None:
        """Publish a definition after its optional, connection-owned key is saved.

        The registry and dotenv cannot form one filesystem transaction. A known
        unpublished definition removes its newly owned key. Uncertain durability
        or a crash may leave an unused private key; an installed definition must
        retain its saved credential.
        Existing credential references are never overwritten by this operation.
        """
        from .config import _parse_env_file, provider_secret_revision, save_provider_secret

        with settings_lock(self.path):
            payload = self._read()
            current = self._records(payload)
            if connection.id in current:
                raise SettingsConflictError("Connection ID already exists; reload and retry")
            if len(current) >= MAX_CONNECTIONS:
                raise ValueError("Model connection limit reached")
            records = dict(payload.get("connections", {}))
            records[connection.id] = asdict(connection)
            payload.update(version=CONNECTION_VERSION, connections=records)
            if len((json.dumps(payload, indent=2) + "\n").encode()) > 1_000_000:
                raise ValueError("Model registry size limit reached")
            if secret:
                if (not connection.key_env.startswith("KLAUDE_MODEL_")
                        or len(secret) > 8192 or _CONTROL.search(secret)):
                    raise ValueError("Invalid connection-owned credential")
                if (connection.key_env in _parse_env_file(self.path.parent / ".env")
                        or connection.key_env in os.environ
                        or provider_secret_revision(self.path.parent, connection.key_env)):
                    raise SettingsConflictError("Credential reference exists; review again")
                save_provider_secret(self.path.parent, connection.key_env, secret)
            try:
                atomic_write_private(self.path, json.dumps(payload, indent=2) + "\n")
            except Exception:
                if secret:
                    # Atomic replacement may succeed before directory fsync
                    # fails. Never delete the key for a published definition,
                    # or when storage failure prevents confirming its absence.
                    try:
                        unpublished = self._records(self._read()).get(connection.id) != connection
                    except Exception:
                        unpublished = False
                    if unpublished:
                        save_provider_secret(self.path.parent, connection.key_env, "")
                raise


def connection_registry(cfg: Any) -> ModelConnectionRegistry:
    return ModelConnectionRegistry(cfg.config_dir / "model-connections.json")


def resolve_connection(cfg: Any, connection_id: str, backend: str) -> ModelConnection:
    connection = connection_registry(cfg).load().get(connection_id)
    if connection is None or connection.backend != backend:
        raise ValueError("Model connection is missing or its adapter changed")
    if not connection.enabled:
        raise ValueError("Model connection is disabled")
    return connection


def connection_key(cfg: Any, connection: ModelConnection) -> str:
    """Resolve private references, honoring saved removals over stale process env."""
    from .config import provider_secret_value

    if not connection.key_env:
        return ""
    return provider_secret_value(cfg.config_dir, connection.key_env)
