"""Secret-safe MCP registry plus transient and persistent client adapters."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import stat
import tempfile
import threading
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import AsyncExitStack, asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import anyio
import httpx2 as httpx
from mcp import StdioServerParameters
from mcp.client import Client as SDKClient
from mcp.client.auth import OAuthClientProvider
from mcp.client.stdio import get_default_environment, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import (
    AuthorizationCodeResult,
    OAuthClientInformationFull,
    OAuthClientMetadata,
    OAuthMetadata,
    OAuthToken,
    ProtectedResourceMetadata,
)
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED
from pydantic import AnyUrl, ValidationError

from .settings_store import SettingsConflictError, atomic_write_private, settings_lock

_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
_ENV_REF_RE = re.compile(
    r"^(?P<prefix>Bearer\s+)?\$\{(?:env:)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\}$",
    re.IGNORECASE,
)
_SENSITIVE_NAME_RE = re.compile(r"(?i)(authorization|api[-_]?key|token|secret|password)")
MAX_MCP_OUTPUT_CHARS = 50_000
MAX_MCP_TOOL_SCHEMA_CHARS = 100_000
MAX_MCP_AUTH_FILE_BYTES = 256_000
MAX_MCP_CONFIG_FILE_BYTES = 16_000_000
MAX_MCP_IMPORT_FILE_BYTES = 4_000_000
MCP_OAUTH_REDIRECT_URI = "http://127.0.0.1:8765/callback"
_MCP_ERROR_SECRET_RE = re.compile(
    r"(?i)(?P<label>(?:access_token|refresh_token|client_secret|authorization_code|"
    r"[?&](?:code|state))\s*[=:]\s*)(?P<value>[^\s&,'\"}]+)"
)
_MCP_ERROR_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")


def safe_mcp_error(error: BaseException) -> str:
    """Bound and redact errors crossing the untrusted MCP/OAuth boundary."""
    for _ in range(8):
        if not isinstance(error, BaseExceptionGroup) or not error.exceptions:
            break
        error = error.exceptions[0]
    text = " ".join(str(error).split())
    text = _MCP_ERROR_BEARER_RE.sub(r"\1[REDACTED]", text)
    text = _MCP_ERROR_SECRET_RE.sub(r"\g<label>[REDACTED]", text)
    text = "".join(character for character in text if character.isprintable())
    return text[:500] or type(error).__name__


def _bounded_tool_record(tool: Any) -> dict[str, Any] | None:
    schema = dict(tool.input_schema or {"type": "object", "properties": {}})
    if schema.get("type", "object") != "object":
        return None
    schema.setdefault("type", "object")
    record = {
        "name": str(tool.name),
        "description": str(tool.description or "")[:4_000],
        "inputSchema": schema,
    }
    if len(json.dumps(record, ensure_ascii=False)) > MAX_MCP_TOOL_SCHEMA_CHARS:
        return None
    return record


@dataclass
class MCPServerConfig:
    name: str
    transport: str
    enabled: bool = True
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    source: dict[str, str] = field(default_factory=dict)
    oauth: bool = False
    oauth_scope: str = ""
    oauth_client_metadata_url: str = ""

    @classmethod
    def from_dict(cls, name: str, raw: dict[str, Any]) -> MCPServerConfig:
        transport = str(raw.get("transport") or raw.get("type") or "").casefold()
        if not transport:
            transport = "http" if raw.get("url") else "stdio"
        if transport in {"streamable-http", "streamable_http"}:
            transport = "http"
        server = cls(
            name=name,
            transport=transport,
            enabled=raw.get("enabled") is not False,
            command=str(raw.get("command") or ""),
            args=[str(value) for value in raw.get("args", [])],
            url=str(raw.get("url") or ""),
            env={str(k): str(v) for k, v in dict(raw.get("env") or {}).items()},
            headers={str(k): str(v) for k, v in dict(raw.get("headers") or {}).items()},
            cwd=str(raw.get("cwd") or ""),
            tools=[
                dict(value)
                for value in raw.get("tools", [])[:128]
                if isinstance(value, dict)
                and len(json.dumps(value, ensure_ascii=False)) <= 100_000
            ],
            source={
                str(k): str(v)[:2_000]
                for k, v in list(dict(raw.get("source") or {}).items())[:16]
                if isinstance(k, str) and isinstance(v, str)
            },
            oauth=bool(raw.get("oauth")),
            oauth_scope=str(raw.get("oauth_scope") or "")[:2_000],
            oauth_client_metadata_url=str(raw.get("oauth_client_metadata_url") or "")[:8_192],
        )
        server.validate()
        return server

    def validate(self) -> None:
        if not _NAME_RE.fullmatch(self.name):
            raise ValueError("MCP server name must use letters, numbers, '.', '_', or '-'")
        if self.transport not in {"stdio", "http"}:
            raise ValueError("MCP transport must be stdio or http")
        if self.transport == "stdio" and (not self.command or self.url):
            raise ValueError("stdio MCP servers require command and must not set url")
        if self.oauth and self.transport != "http":
            raise ValueError("MCP OAuth is supported only for remote HTTP servers")
        if self.oauth and any(key.casefold() == "authorization" for key in self.headers):
            raise ValueError("MCP OAuth cannot be combined with a static Authorization header")
        if any(not char.isprintable() for char in self.oauth_scope):
            raise ValueError("MCP OAuth scope must be printable")
        if self.oauth_client_metadata_url:
            metadata_url = urlparse(self.oauth_client_metadata_url)
            if (
                metadata_url.scheme != "https"
                or not metadata_url.hostname
                or metadata_url.path in {"", "/"}
                or metadata_url.username
                or metadata_url.password
            ):
                raise ValueError("MCP OAuth client metadata URL must be credential-free HTTPS")
        if len(self.command) > 4_096 or any(not char.isprintable() for char in self.command):
            raise ValueError("MCP command must be printable and at most 4,096 characters")
        if len(self.args) > 256 or any(
            len(value) > 16_384 or any(not char.isprintable() for char in value)
            for value in self.args
        ):
            raise ValueError("MCP arguments must be printable and within safety limits")
        if len(self.cwd) > 4_096 or any(not char.isprintable() for char in self.cwd):
            raise ValueError("MCP working directory must be printable and within safety limits")
        if self.transport == "http":
            parsed = urlparse(self.url)
            local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            allowed_schemes = {"http", "https"} if local else {"https"}
            if parsed.scheme not in allowed_schemes or not parsed.hostname:
                raise ValueError(
                    "remote MCP URL must use HTTPS (HTTP is allowed only for localhost)"
                )
            if self.command:
                raise ValueError("HTTP MCP servers must not set command")
            if parsed.username or parsed.password:
                raise ValueError("MCP URLs must not contain credentials")
            if len(self.url) > 8_192 or any(not char.isprintable() for char in self.url):
                raise ValueError("MCP URL must be printable and within safety limits")
            if any(
                _SENSITIVE_NAME_RE.search(part.split("=", 1)[0])
                for part in parsed.query.split("&")
                if part
            ):
                raise ValueError("MCP URL secrets must use an environment-backed header")
        for mapping in (self.env, self.headers):
            if len(mapping) > 64:
                raise ValueError("MCP environment/header map is too large")
            for key, value in mapping.items():
                if not key or "\n" in key or "\r" in key or "\n" in value or "\r" in value:
                    raise ValueError("MCP environment/header entries must be single-line")
                if len(key) > 256 or len(value) > 16_384 or "\x1b" in key or "\x1b" in value:
                    raise ValueError("MCP environment/header entries exceed safety limits")
                if _SENSITIVE_NAME_RE.search(key) and not _ENV_REF_RE.fullmatch(value):
                    raise ValueError(
                        f"sensitive MCP value {key!r} must reference ${{env:VARIABLE}}"
                    )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "transport": self.transport,
            "enabled": self.enabled,
        }
        if self.transport == "stdio":
            data.update(command=self.command, args=self.args)
            if self.cwd:
                data["cwd"] = self.cwd
            if self.env:
                data["env"] = self.env
        else:
            data["url"] = self.url
            if self.headers:
                data["headers"] = self.headers
        if self.tools:
            data["tools"] = self.tools
        if self.source:
            data["source"] = self.source
        if self.oauth:
            data["oauth"] = True
            if self.oauth_scope:
                data["oauth_scope"] = self.oauth_scope
            if self.oauth_client_metadata_url:
                data["oauth_client_metadata_url"] = self.oauth_client_metadata_url
        return data


@dataclass(frozen=True)
class MCPAuthStatus:
    configured: bool
    client_registered: bool
    access_token_present: bool
    refresh_token_present: bool
    expires_at: float | None
    scope: str


class MCPTokenStorage:
    """Owner-only durable OAuth tokens and dynamic client registration metadata."""

    def __init__(self, path: Path, *, server_url: str = ""):
        self.path = path
        self.server_url = server_url
        self._lock = threading.RLock()

    def _matches_server(self, value: dict[str, Any]) -> bool:
        if not self.server_url:
            return True
        bound = value.get("server_url")
        if bound:
            return bound == self.server_url
        # Migrate legacy credentials only when their discovery record proves
        # which resource they belonged to. Otherwise perform a fresh login.
        resource = value.get("protected_resource_metadata")
        return isinstance(resource, dict) and resource.get("resource") == self.server_url

    def _read(self) -> dict[str, Any]:
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MCP_AUTH_FILE_BYTES:
                    return {}
                data = stream.read(MAX_MCP_AUTH_FILE_BYTES + 1)
            if len(data) > MAX_MCP_AUTH_FILE_BYTES:
                return {}
            value = json.loads(data)
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _write(self, updates: dict[str, Any]) -> None:
        with self._lock:
            value = self._read()
            if self.server_url:
                if not self._matches_server(value):
                    value = {}
                value["server_url"] = self.server_url
            value.update(updates)
            value["version"] = 1
            encoded = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
            if len(encoded.encode()) > MAX_MCP_AUTH_FILE_BYTES:
                raise ValueError("MCP OAuth credentials exceeded the safety limit")
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.path.parent.chmod(0o700)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".mcp-auth-", dir=self.path.parent
            )
            temporary = Path(temporary_name)
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(encoded + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, self.path)
                self.path.chmod(0o600)
            finally:
                temporary.unlink(missing_ok=True)

    async def get_tokens(self) -> OAuthToken | None:
        with self._lock:
            value = self._read()
        if not self._matches_server(value):
            return None
        raw = value.get("tokens")
        if not isinstance(raw, dict):
            return None
        try:
            token = OAuthToken.model_validate(raw)
        except ValidationError:
            return None
        if token.expires_in is not None:
            try:
                saved_at = float(value.get("token_saved_at", 0))
            except (TypeError, ValueError):
                saved_at = 0
            elapsed = max(0, int(time.time() - saved_at))
            token.expires_in = max(0, int(token.expires_in) - elapsed)
        return token

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write(
            {
                "tokens": tokens.model_dump(mode="json", exclude_none=True),
                "token_saved_at": time.time(),
            }
        )

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        with self._lock:
            value = self._read()
        if not self._matches_server(value):
            return None
        raw = value.get("client_info")
        if not isinstance(raw, dict):
            return None
        try:
            return OAuthClientInformationFull.model_validate(raw)
        except ValidationError:
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._write(
            {"client_info": client_info.model_dump(mode="json", exclude_none=True)}
        )

    def set_discovery(
        self,
        oauth_metadata: OAuthMetadata | None,
        protected_resource_metadata: ProtectedResourceMetadata | None,
        auth_server_url: str | None,
    ) -> None:
        if oauth_metadata is None and protected_resource_metadata is None:
            return
        self._write(
            {
                "oauth_metadata": oauth_metadata.model_dump(mode="json", exclude_none=True)
                if oauth_metadata is not None
                else None,
                "protected_resource_metadata": protected_resource_metadata.model_dump(
                    mode="json", exclude_none=True
                )
                if protected_resource_metadata is not None
                else None,
                "auth_server_url": auth_server_url or "",
            }
        )

    def restore_discovery(self, provider: OAuthClientProvider) -> None:
        value = self._read()
        if not self._matches_server(value):
            return
        try:
            raw_oauth = value.get("oauth_metadata")
            raw_resource = value.get("protected_resource_metadata")
            if isinstance(raw_oauth, dict):
                provider.context.oauth_metadata = OAuthMetadata.model_validate(raw_oauth)
            if isinstance(raw_resource, dict):
                provider.context.protected_resource_metadata = (
                    ProtectedResourceMetadata.model_validate(raw_resource)
                )
            auth_server_url = value.get("auth_server_url")
            if isinstance(auth_server_url, str):
                provider.context.auth_server_url = auth_server_url
        except ValidationError:
            # Invalid cached public discovery metadata is ignored. The SDK will
            # rediscover it after an authorization challenge.
            return

    def status(self) -> MCPAuthStatus:
        value = self._read()
        raw_tokens = value.get("tokens")
        raw_client = value.get("client_info")
        expires_at: float | None = None
        scope = ""
        if isinstance(raw_tokens, dict):
            expires_in = raw_tokens.get("expires_in")
            if isinstance(expires_in, (int, float)):
                try:
                    saved_at = float(value.get("token_saved_at", 0))
                except (TypeError, ValueError):
                    saved_at = 0
                expires_at = saved_at + float(expires_in)
            scope = str(raw_tokens.get("scope") or "")[:2_000]
        return MCPAuthStatus(
            configured=self.path.is_file() and bool(value),
            client_registered=isinstance(raw_client, dict) and bool(raw_client.get("client_id")),
            access_token_present=isinstance(raw_tokens, dict)
            and bool(raw_tokens.get("access_token")),
            refresh_token_present=isinstance(raw_tokens, dict)
            and bool(raw_tokens.get("refresh_token")),
            expires_at=expires_at,
            scope=scope,
        )

    def clear(self) -> bool:
        try:
            if self.path.is_symlink():
                return False
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True


def mcp_auth_file(auth_dir: Path, server_name: str) -> Path:
    digest = hashlib.sha256(server_name.encode()).hexdigest()[:16]
    return auth_dir / f"{server_name}-{digest}.json"


class _StoredTokenOAuthProvider(OAuthClientProvider):
    """Restore remaining lifetime omitted by SDK 2.2's storage initialization.

    Keep this workaround limited to initialization; discovery, PKCE, issuer
    validation, refresh and authorization remain SDK responsibilities.
    """

    async def _initialize(self) -> None:
        await super()._initialize()
        if self.context.current_tokens is not None:
            self.context.update_token_expiry(self.context.current_tokens)


def _oauth_provider(
    server: MCPServerConfig,
    auth_dir: Path,
    redirect_handler: Any = None,
    callback_handler: Any = None,
    redirect_uri: str = MCP_OAUTH_REDIRECT_URI,
) -> OAuthClientProvider:
    async def unavailable_redirect(_url: str) -> None:
        raise RuntimeError(f"MCP OAuth sign-in required; run klaude mcp auth login {server.name}")

    async def unavailable_callback() -> AuthorizationCodeResult:
        raise RuntimeError(f"MCP OAuth sign-in required; run klaude mcp auth login {server.name}")

    metadata = OAuthClientMetadata(
        client_name="Klaude",
        redirect_uris=[AnyUrl(redirect_uri)],
        scope=server.oauth_scope or None,
    )
    storage = MCPTokenStorage(mcp_auth_file(auth_dir, server.name), server_url=server.url)
    provider = _StoredTokenOAuthProvider(
        server_url=server.url,
        client_metadata=metadata,
        storage=storage,
        redirect_handler=redirect_handler or unavailable_redirect,
        callback_handler=callback_handler or unavailable_callback,
        client_metadata_url=server.oauth_client_metadata_url or None,
    )
    storage.restore_discovery(provider)
    return provider


def _persist_oauth_discovery(provider: OAuthClientProvider | None) -> None:
    if provider is None or not isinstance(provider.context.storage, MCPTokenStorage):
        return
    provider.context.storage.set_discovery(
        provider.context.oauth_metadata,
        provider.context.protected_resource_metadata,
        provider.context.auth_server_url,
    )


def _resolve_values(values: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, value in values.items():
        match = _ENV_REF_RE.fullmatch(value)
        if match:
            env_name = match.group("name")
            env_value = os.environ.get(env_name)
            if env_value is None:
                raise ValueError(f"required environment variable {env_name} is not configured")
            resolved[key] = f"{match.group('prefix') or ''}{env_value}"
        else:
            resolved[key] = value
    return resolved


def _stdio_environment(values: dict[str, str]) -> dict[str, str]:
    environment = get_default_environment()
    environment.update(_resolve_values(values))
    return environment


class MCPRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._baseline: dict[str, dict[str, Any]] = {}

    def load(self) -> dict[str, MCPServerConfig]:
        servers = self._load()
        self._baseline = deepcopy({name: item.to_dict() for name, item in servers.items()})
        return servers

    def _load(self) -> dict[str, MCPServerConfig]:
        if self.path.is_symlink():
            raise PermissionError("Refusing symlinked MCP settings")
        try:
            descriptor = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError("MCP configuration must be a regular file")
                if info.st_size > MAX_MCP_CONFIG_FILE_BYTES:
                    raise ValueError("MCP configuration exceeds the safety limit")
                content = source.read(MAX_MCP_CONFIG_FILE_BYTES + 1)
                if len(content) > MAX_MCP_CONFIG_FILE_BYTES:
                    raise ValueError("MCP configuration exceeds the safety limit")
            raw = json.loads(content.decode("utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"could not read MCP configuration: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("MCP configuration must be an object")
        servers = raw.get("servers", raw.get("mcpServers", {}))
        if not isinstance(servers, dict):
            raise ValueError("MCP configuration must contain a servers object")
        return {
            str(name): MCPServerConfig.from_dict(str(name), value)
            for name, value in servers.items()
            if isinstance(value, dict)
        }

    def save(self, servers: dict[str, MCPServerConfig]) -> None:
        proposed = deepcopy({name: item.to_dict() for name, item in servers.items()})
        changed = {
            name for name in self._baseline.keys() | proposed.keys()
            if self._baseline.get(name) != proposed.get(name)
        }
        with settings_lock(self.path):
            current = {name: item.to_dict() for name, item in self._load().items()}
            for name in changed:
                if current.get(name) != self._baseline.get(name):
                    raise SettingsConflictError(
                        "MCP configuration changed in another client; reload and retry"
                    )
            for name in changed:
                if name in proposed:
                    current[name] = proposed[name]
                else:
                    current.pop(name, None)
            payload = {"version": 1, "servers": current}
            encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            if len(encoded.encode()) > MAX_MCP_CONFIG_FILE_BYTES:
                raise ValueError("MCP configuration exceeds storage limit")
            atomic_write_private(self.path, encoded)
            # Retain the caller's snapshot, not unseen rows merged from another
            # client: a subsequent save must not interpret unseen rows as deletions.
            self._baseline = proposed

    def import_file(self, source: Path) -> dict[str, MCPServerConfig]:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MCP_IMPORT_FILE_BYTES:
                raise ValueError("MCP import requires a bounded regular file")
            data = stream.read(MAX_MCP_IMPORT_FILE_BYTES + 1)
            if len(data) > MAX_MCP_IMPORT_FILE_BYTES:
                raise ValueError("MCP import exceeds the safety limit")
        raw = json.loads(data)
        candidates: Any = None
        source_kind = "standard"
        if isinstance(raw, dict):
            if isinstance(raw.get("mcpServers"), dict):
                candidates = raw["mcpServers"]
            elif isinstance(raw.get("servers"), dict):
                candidates = raw["servers"]
            elif isinstance(raw.get("mcp"), dict):
                candidates = raw["mcp"]
                source_kind = "opencode"
        if not isinstance(candidates, dict):
            raise ValueError("imported file has no mcpServers, servers, or mcp object")
        imported: dict[str, MCPServerConfig] = {}
        for name, value in candidates.items():
            if not isinstance(value, dict):
                raise ValueError("Every imported MCP definition must be an object")
            normalized = dict(value)
            if source_kind == "opencode":
                external_type = str(normalized.get("type") or "").casefold()
                if external_type == "local":
                    command = normalized.get("command")
                    if not isinstance(command, list) or not command:
                        raise ValueError(f"OpenCode MCP server {name!r} has no command")
                    normalized["transport"] = "stdio"
                    normalized["command"] = str(command[0])
                    normalized["args"] = [str(item) for item in command[1:]]
                    normalized["env"] = normalized.get("environment", {})
                elif external_type == "remote":
                    oauth = normalized.get("oauth")
                    if isinstance(oauth, dict):
                        normalized["oauth"] = True
                        normalized["oauth_scope"] = str(oauth.get("scope") or "")
                        normalized["oauth_client_metadata_url"] = str(
                            oauth.get("clientMetadataUrl") or ""
                        )
                    normalized["transport"] = "http"
                else:
                    raise ValueError(
                        f"OpenCode MCP server {name!r} must have type local or remote"
                    )
            imported[str(name)] = MCPServerConfig.from_dict(str(name), normalized)
        return imported


@asynccontextmanager
async def _connected_client(
    server: MCPServerConfig,
    timeout_seconds: float,
    auth_dir: Path | None,
    redirect_handler: Any = None,
    callback_handler: Any = None,
    redirect_uri: str = MCP_OAUTH_REDIRECT_URI,
):
    """One connection factory for discovery and process-lived tool sessions."""
    server.validate()
    async with AsyncExitStack() as stack:
        oauth = None
        if server.transport == "stdio":
            errlog = stack.enter_context(open(os.devnull, "w", encoding="utf-8"))
            transport = stdio_client(StdioServerParameters(
                command=server.command, args=server.args,
                env=_stdio_environment(server.env), cwd=server.cwd or None,
            ), errlog=errlog)
        else:
            if server.oauth:
                if auth_dir is None:
                    raise RuntimeError("MCP OAuth credential storage is unavailable")
                oauth = _oauth_provider(
                    server, auth_dir, redirect_handler, callback_handler, redirect_uri
                )
            http_client = await stack.enter_async_context(httpx.AsyncClient(
                headers=_resolve_values(server.headers) or None, auth=oauth,
                timeout=httpx.Timeout(timeout_seconds), follow_redirects=False,
            ))
            transport = streamable_http_client(server.url, http_client=http_client)
        # Keep the existing handshake behavior during the v2 migration. SDK v2
        # servers support it; modern negotiation can be enabled independently.
        client = await stack.enter_async_context(SDKClient(
            transport, mode="legacy", read_timeout_seconds=timeout_seconds
        ))
        try:
            yield client
        finally:
            _persist_oauth_discovery(oauth)


async def _list_tools(client: SDKClient):
    """Follow bounded pagination without looping on a hostile repeated cursor."""
    from mcp.types import ListToolsResult

    tools: list[Any] = []
    cursor = None
    seen = set()
    for _ in range(16):
        result = await client.list_tools(cursor=cursor)
        tools.extend(result.tools[:128 - len(tools)])
        cursor = result.next_cursor
        if not cursor or len(tools) >= 128:
            return ListToolsResult(tools=tools)
        if cursor in seen:
            raise RuntimeError("MCP tool listing repeated its pagination cursor")
        seen.add(cursor)
    raise RuntimeError("MCP tool listing exceeded the page limit")


def _tool_result(server: MCPServerConfig, name: str, result: Any) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    used = 0
    for block in result.content:
        item = block.model_dump(mode="json", exclude_none=True, by_alias=True)
        encoded = json.dumps(item, ensure_ascii=False)
        if used + len(encoded) > MAX_MCP_OUTPUT_CHARS:
            break
        content.append(item)
        used += len(encoded)
    payload = {
        "server": server.name, "tool": name, "is_error": bool(result.is_error),
        "content": content, "truncated": len(content) < len(result.content),
    }
    structured = result.structured_content
    if structured is not None:
        if used + len(json.dumps(structured, ensure_ascii=False)) <= MAX_MCP_OUTPUT_CHARS:
            payload["structured_content"] = structured
        else:
            payload["truncated"] = True
    return payload


class MCPClient:
    def __init__(
        self,
        timeout_seconds: float = 30.0,
        *,
        auth_dir: Path | None = None,
        oauth_redirect_handler: Any = None,
        oauth_callback_handler: Any = None,
        oauth_redirect_uri: str = MCP_OAUTH_REDIRECT_URI,
    ):
        self.timeout_seconds = timeout_seconds
        self.auth_dir = auth_dir
        self.oauth_redirect_handler = oauth_redirect_handler
        self.oauth_callback_handler = oauth_callback_handler
        self.oauth_redirect_uri = oauth_redirect_uri

    async def _run(self, server: MCPServerConfig, operation: str, **kwargs: Any) -> Any:
        if operation != "list" and not server.enabled:
            raise PermissionError("MCP server is disabled")
        with anyio.fail_after(self.timeout_seconds):
            async with _connected_client(
                server, self.timeout_seconds, self.auth_dir,
                self.oauth_redirect_handler, self.oauth_callback_handler, self.oauth_redirect_uri,
            ) as client:
                if operation == "list":
                    return await _list_tools(client)
                return await client.call_tool(str(kwargs["name"]), kwargs.get("arguments") or {})

    def discover(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        try:
            result = anyio.run(self._run, server, "list")
        except Exception as exc:
            raise RuntimeError(safe_mcp_error(exc)) from None
        records = (_bounded_tool_record(tool) for tool in result.tools[:128])
        return [record for record in records if record is not None]

    async def discover_async(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        """Discover on the caller's loop; cancellation unwinds owned transports."""
        try:
            result = await self._run(server, "list")
        except TimeoutError:
            raise TimeoutError("MCP connection timed out") from None
        except Exception as exc:
            raise RuntimeError(safe_mcp_error(exc)) from None
        records = (_bounded_tool_record(tool) for tool in result.tools[:128])
        return [record for record in records if record is not None]

    def call(self, server: MCPServerConfig, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            result = anyio.run(
                partial(self._run, server, "call", name=name, arguments=arguments)
            )
        except Exception as exc:
            raise RuntimeError(safe_mcp_error(exc)) from None
        return _tool_result(server, name, result)


class MCPClientManager:
    """Keep MCP sessions alive for stateful browser and developer tools."""

    def __init__(self, timeout_seconds: float = 60.0, *, auth_dir: Path | None = None):
        self.timeout_seconds = timeout_seconds
        self.auth_dir = auth_dir
        self._closed = False
        self._actors: dict[
            str,
            tuple[str, queue.Queue, threading.Thread],
        ] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _fingerprint(server: MCPServerConfig) -> str:
        value = server.to_dict()
        value.pop("tools", None)
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    async def _actor(
        self,
        server: MCPServerConfig,
        requests: queue.Queue,
        ready: Future,
    ) -> None:
        try:
            async with AsyncExitStack() as stack:
                session = await stack.enter_async_context(_connected_client(
                    server, self.timeout_seconds, self.auth_dir
                ))
                if ready.cancelled():
                    return
                if not ready.done():
                    ready.set_result(None)
                while True:
                    try:
                        operation, arguments, response = requests.get_nowait()
                    except queue.Empty:
                        await anyio.sleep(0.01)
                        continue
                    if operation == "close":
                        if not response.done():
                            response.set_result(None)
                        return
                    if response.cancelled():
                        continue
                    try:
                        with anyio.fail_after(self.timeout_seconds):
                            if operation == "list":
                                result = await _list_tools(session)
                            else:
                                result = await session.call_tool(
                                    str(arguments["name"]),
                                    arguments.get("arguments") or {},
                                    read_timeout_seconds=self.timeout_seconds,
                                )
                    except BaseException as exc:
                        if not response.done():
                            response.set_exception(exc)
                        if isinstance(exc, MCPError) and exc.code == CONNECTION_CLOSED:
                            raise
                    else:
                        if not response.done():
                            response.set_result(result)
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc)
            while True:
                try:
                    _operation, _arguments, response = requests.get_nowait()
                except queue.Empty:
                    break
                if not response.done():
                    response.set_exception(exc)

    def _run_actor(
        self,
        server: MCPServerConfig,
        requests: queue.Queue,
        ready: Future,
    ) -> None:
        anyio.run(self._actor, server, requests, ready)

    def _ensure_actor(
        self, server: MCPServerConfig
    ) -> tuple[queue.Queue, threading.Thread]:
        fingerprint = self._fingerprint(server)
        with self._lock:
            current = self._actors.get(server.name)
            if current and current[0] == fingerprint and current[2].is_alive():
                return current[1], current[2]
            if current:
                self._stop_actor(server.name, current)
            requests: queue.Queue = queue.Queue()
            ready: Future = Future()
            thread = threading.Thread(
                target=self._run_actor,
                args=(server, requests, ready),
                name=f"klaude-mcp-{server.name}",
                daemon=True,
            )
            self._actors[server.name] = (fingerprint, requests, thread)
            thread.start()
        try:
            ready.result(timeout=self.timeout_seconds)
        except BaseException:
            ready.cancel()
            with self._lock:
                actor = self._actors.get(server.name)
                if actor and actor[2] is thread:
                    self._actors.pop(server.name, None)
            raise
        return requests, thread

    def _request(self, server: MCPServerConfig, operation: str, **arguments: Any) -> Any:
        if self._closed:
            raise RuntimeError("MCP client is closed")
        if not server.enabled:
            raise PermissionError("MCP server is disabled")
        requests, thread = self._ensure_actor(server)
        response: Future = Future()
        requests.put((operation, arguments, response))
        try:
            return response.result(timeout=self.timeout_seconds + 1)
        except FutureTimeoutError:
            response.cancel()
            if not thread.is_alive():
                with self._lock:
                    self._actors.pop(server.name, None)
            raise TimeoutError("MCP operation timed out") from None
        except BaseException as exc:
            if isinstance(exc, MCPError) and exc.code == CONNECTION_CLOSED:
                with self._lock:
                    actor = self._actors.get(server.name)
                    if actor and actor[2] is thread:
                        self._actors.pop(server.name, None)
                # The worker is already unwinding after EOF. Do not queue a
                # close request on that dead connection or retry the failed call.
                thread.join(timeout=1)
            if not thread.is_alive():
                with self._lock:
                    actor = self._actors.get(server.name)
                    if actor and actor[2] is thread:
                        self._actors.pop(server.name, None)
            raise

    def discover(self, server: MCPServerConfig) -> list[dict[str, Any]]:
        try:
            result = self._request(server, "list")
        except Exception as exc:
            raise RuntimeError(safe_mcp_error(exc)) from None
        records = (_bounded_tool_record(tool) for tool in result.tools[:128])
        return [record for record in records if record is not None]

    def call(
        self, server: MCPServerConfig, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            result = self._request(server, "call", name=name, arguments=arguments)
        except Exception as exc:
            raise RuntimeError(safe_mcp_error(exc)) from None
        return _tool_result(server, name, result)

    def _stop_actor(
        self,
        name: str,
        actor: tuple[str, queue.Queue, threading.Thread],
    ) -> None:
        _fingerprint, requests, thread = actor
        if thread.is_alive():
            response: Future = Future()
            requests.put(("close", {}, response))
            try:
                response.result(timeout=5)
            except Exception:
                pass
            thread.join(timeout=5)
        self._actors.pop(name, None)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            for name, actor in reversed(tuple(self._actors.items())):
                self._stop_actor(name, actor)


def namespaced_tool_name(server: str, tool: str) -> str:
    safe_server = re.sub(r"[^A-Za-z0-9_-]", "_", server)[:20]
    safe_tool = re.sub(r"[^A-Za-z0-9_-]", "_", tool)[:25]
    digest = hashlib.sha256(f"{server}\0{tool}".encode()).hexdigest()[:8]
    return f"mcp__{safe_server}__{safe_tool}_{digest}"
