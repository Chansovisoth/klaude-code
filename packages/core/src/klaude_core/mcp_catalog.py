"""Bounded client and install-plan builder for the official MCP Registry."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from .mcp_client import MCPServerConfig
from .settings_store import atomic_write_private, settings_lock

OFFICIAL_MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.io"
MAX_REGISTRY_RESPONSE_BYTES = 2_000_000
MAX_REGISTRY_CACHE_BYTES = 8_000_000
MAX_REGISTRY_CACHE_ENTRIES = 64
REGISTRY_CACHE_TTL_SECONDS = 3_600
REGISTRY_STALE_FALLBACK_SECONDS = 7 * 86_400
_INPUT_MARKER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_EXACT_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,254}$")
_REGISTRY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_NPM_PACKAGE_RE = re.compile(
    r"^(?:@[a-z0-9][a-z0-9._-]{0,213}/)?[a-z0-9][a-z0-9._-]{0,213}$"
)
_PYPI_PACKAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class MCPCatalogError(RuntimeError):
    """A registry response or install plan was unavailable or unsafe."""


@dataclass(frozen=True)
class MCPCatalogInput:
    key: str
    label: str
    description: str = ""
    secret: bool = False
    required: bool = False
    default: str = ""


@dataclass(frozen=True)
class MCPCatalogServer:
    name: str
    title: str
    description: str
    version: str
    status: str
    repository_url: str = ""
    website_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)


@dataclass(frozen=True)
class MCPInstallPlan:
    label: str
    source_name: str
    source_version: str
    transport: str
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    env_templates: tuple[tuple[str, str], ...] = ()
    header_templates: tuple[tuple[str, str], ...] = ()
    inputs: tuple[MCPCatalogInput, ...] = ()
    repository_url: str = ""
    package_sha256: str = ""

    @staticmethod
    def secret_environment_name(local_name: str, item: MCPCatalogInput) -> str:
        return _secret_env_name(local_name, item.key)

    def preview(self) -> str:
        endpoint = self.url if self.transport == "http" else " ".join(
            [self.command, *self.args]
        )
        lines = [
            f"Registry:  {self.source_name}",
            f"Version:   {self.source_version}",
            f"Transport: {self.label}",
            f"Endpoint:  {endpoint}",
        ]
        if self.repository_url:
            lines.append(f"Source:    {self.repository_url}")
        if self.package_sha256:
            lines.append(f"Published hash (not runner-verified): {self.package_sha256}")
        if self.inputs:
            lines.append(
                "Inputs:    "
                + ", ".join(
                    f"{item.label}{' (secret)' if item.secret else ''}"
                    for item in self.inputs
                )
            )
        return "\n".join(lines)

    def materialize(
        self,
        local_name: str,
        answers: dict[str, str],
    ) -> tuple[MCPServerConfig, dict[str, str]]:
        """Create a disabled config and return secrets separately for secure storage."""
        inputs = {item.key: item for item in self.inputs}

        def available(item: MCPCatalogInput) -> bool:
            if answers.get(item.key) or item.default:
                return True
            return item.secret and _secret_env_name(local_name, item.key) in os.environ

        missing = [
            item.label
            for item in self.inputs
            if item.required and not available(item)
        ]
        if missing:
            raise MCPCatalogError("missing required inputs: " + ", ".join(missing))
        secret_values: dict[str, str] = {}

        def replace(template: str) -> str:
            def substitute(match: re.Match[str]) -> str:
                key = match.group(1)
                item = inputs.get(key)
                if item is None:
                    raise MCPCatalogError(f"registry template references unknown input {key}")
                value = answers.get(key) or item.default
                if item.secret:
                    env_name = _secret_env_name(local_name, item.key)
                    if value:
                        secret_values[env_name] = value
                    elif env_name not in os.environ:
                        return ""
                    return f"${{env:{env_name}}}"
                return value

            return _INPUT_MARKER_RE.sub(substitute, template)

        def mapping(values: tuple[tuple[str, str], ...]) -> dict[str, str]:
            result: dict[str, str] = {}
            for name, template in values:
                referenced = [inputs[key] for key in _INPUT_MARKER_RE.findall(template)]
                if referenced and not all(available(item) for item in referenced):
                    continue
                value = replace(template)
                if value:
                    result[name] = value
            return result

        server = MCPServerConfig(
            name=local_name,
            transport=self.transport,
            enabled=False,
            command=self.command,
            args=[resolved for value in self.args if (resolved := replace(value))],
            url=replace(self.url),
            env=mapping(self.env_templates),
            headers=mapping(self.header_templates),
            source={
                "registry": "official",
                "name": self.source_name,
                "version": self.source_version,
                "repository": self.repository_url,
                "sha256": self.package_sha256,
            },
        )
        server.validate()
        return server, secret_values


def _secret_env_name(local_name: str, label: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", f"MCP_{local_name}_{label}").upper().strip("_")
    if not value or not value[0].isalpha():
        value = "MCP_SECRET_" + value
    return value[:96]


def _safe_https_url(value: object) -> str:
    text = str(value or "")[:2_000]
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    if parsed.hostname.casefold() == "localhost":
        return ""
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            return ""
    return text


def _public_text(value: object, maximum: int) -> str:
    """Normalize untrusted registry prose before terminal display or persistence."""
    text = " ".join(str(value or "").split())
    return "".join(character for character in text if character.isprintable())[:maximum]


def _registry_input(key: str, raw: dict[str, Any]) -> MCPCatalogInput:
    label = _public_text(raw.get("name") or key, 128)
    return MCPCatalogInput(
        key=key,
        label=label,
        description=_public_text(raw.get("description"), 500),
        secret=bool(raw.get("isSecret")),
        required=bool(raw.get("isRequired")),
        default="" if raw.get("isSecret") else str(raw.get("default") or "")[:4_000],
    )


def _value_template(raw: dict[str, Any], inputs: dict[str, MCPCatalogInput]) -> str:
    variables = raw.get("variables")
    if isinstance(variables, dict):
        for key, value in variables.items():
            if isinstance(value, dict):
                inputs[str(key)] = _registry_input(str(key), value)
    value = str(raw.get("value") or "")[:4_000]
    if value:
        return value
    key = re.sub(r"[^A-Za-z0-9_]", "_", str(raw.get("name") or "input")).strip("_")
    key = key or "input"
    inputs.setdefault(key, _registry_input(key, raw))
    return "{" + key + "}"


def _key_value_templates(
    values: object,
    inputs: dict[str, MCPCatalogInput],
) -> tuple[tuple[str, str], ...]:
    result: list[tuple[str, str]] = []
    if not isinstance(values, list):
        return ()
    for raw in values[:64]:
        if not isinstance(raw, dict):
            continue
        name = _public_text(raw.get("name"), 128)
        if not name or "\n" in name or "\r" in name:
            continue
        if raw.get("isSecret") or re.search(
            r"(?i)(authorization|api[-_]?key|token|secret|password)", name
        ):
            raw = {**raw, "isSecret": True, "isRequired": bool(raw.get("isRequired"))}
        template = _value_template(raw, inputs)
        if (
            name.casefold() == "authorization"
            and "bearer" in str(raw.get("description") or "").casefold()
            and not template.casefold().startswith("bearer ")
        ):
            template = "Bearer " + template
        result.append((name, template))
    return tuple(result)


def _argument_templates(
    values: object,
    inputs: dict[str, MCPCatalogInput],
) -> tuple[str, ...]:
    result: list[str] = []
    if not isinstance(values, list):
        return ()
    for raw in values[:64]:
        if not isinstance(raw, dict):
            continue
        if not raw.get("value") and not raw.get("default") and not raw.get("isRequired"):
            continue
        value = _value_template(raw, inputs)
        argument_type = str(raw.get("type") or "positional")
        name = str(raw.get("name") or "")[:128]
        if argument_type == "named" and name:
            result.append(name)
        if value:
            result.append(value)
    return tuple(result)


def install_plans(server: MCPCatalogServer) -> list[MCPInstallPlan]:
    """Build only transport plans Klaude can currently execute safely."""
    plans: list[MCPInstallPlan] = []
    remotes = server.raw.get("remotes")
    if isinstance(remotes, list):
        for index, raw in enumerate(remotes[:8], start=1):
            if not isinstance(raw, dict) or raw.get("type") != "streamable-http":
                continue
            url = _safe_https_url(raw.get("url"))
            if not url or "{" in url or "}" in url:
                continue
            inputs: dict[str, MCPCatalogInput] = {}
            headers = _key_value_templates(raw.get("headers"), inputs)
            plans.append(
                MCPInstallPlan(
                    label=f"remote {index} · Streamable HTTP",
                    source_name=server.name,
                    source_version=server.version,
                    transport="http",
                    url=url,
                    header_templates=headers,
                    inputs=tuple(inputs.values()),
                    repository_url=server.repository_url,
                )
            )
    packages = server.raw.get("packages")
    if isinstance(packages, list):
        for raw in packages[:16]:
            if not isinstance(raw, dict):
                continue
            registry_type = str(raw.get("registryType") or "").casefold()
            version = str(raw.get("version") or server.version)
            identifier = str(raw.get("identifier") or "")
            transport = raw.get("transport")
            if (
                not identifier
                or not _EXACT_VERSION_RE.fullmatch(version)
                or not isinstance(transport, dict)
                or transport.get("type") != "stdio"
            ):
                continue
            inputs = {}
            runtime_args = _argument_templates(raw.get("runtimeArguments"), inputs)
            package_args = _argument_templates(raw.get("packageArguments"), inputs)
            env = _key_value_templates(raw.get("environmentVariables"), inputs)
            runtime_hint = str(raw.get("runtimeHint") or "").casefold()
            if (
                registry_type == "npm"
                and runtime_hint in {"", "npx"}
                and _NPM_PACKAGE_RE.fullmatch(identifier)
                and not runtime_args
            ):
                package = f"{identifier}@{version}"
                args = runtime_args
                if not any(value in {"-y", "--yes"} for value in args):
                    args = ("--yes", *args)
                command = "npx"
                args = (*args, package, *package_args)
            elif (
                registry_type == "pypi"
                and runtime_hint in {"", "uvx"}
                and _PYPI_PACKAGE_RE.fullmatch(identifier)
                and not runtime_args
            ):
                command = "uvx"
                args = (*runtime_args, f"{identifier}=={version}", *package_args)
            else:
                continue
            digest = str(raw.get("fileSha256") or "")
            if digest and not re.fullmatch(r"[a-f0-9]{64}", digest):
                continue
            plans.append(
                MCPInstallPlan(
                    label=f"{registry_type} package · {command}",
                    source_name=server.name,
                    source_version=server.version,
                    transport="stdio",
                    command=command,
                    args=args,
                    env_templates=env,
                    inputs=tuple(inputs.values()),
                    repository_url=server.repository_url,
                    package_sha256=digest,
                )
            )
    return plans


class MCPCatalogClient:
    def __init__(
        self,
        cache_file: Path,
        *,
        base_url: str = OFFICIAL_MCP_REGISTRY_URL,
        timeout_seconds: float = 12.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.cache_file = cache_file
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            parsed.scheme not in ({"http", "https"} if local else {"https"})
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("MCP Registry URL must be a credential-free HTTPS origin")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def _cache_key(self, query: str, limit: int) -> str:
        return json.dumps([query.casefold(), limit], separators=(",", ":"))

    def _load_cache(self) -> dict[str, Any]:
        try:
            if (
                self.cache_file.is_symlink()
                or self.cache_file.stat().st_size > MAX_REGISTRY_CACHE_BYTES
            ):
                return {"version": 1, "entries": {}}
            value = json.loads(self.cache_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"version": 1, "entries": {}}
        if not isinstance(value, dict) or not isinstance(value.get("entries"), dict):
            return {"version": 1, "entries": {}}
        return value

    def _save_cache(self, cache: dict[str, Any], changed_key: str) -> None:
        with settings_lock(self.cache_file):
            latest = self._load_cache()
            latest.setdefault("entries", {})[changed_key] = cache["entries"][changed_key]
            self._save_cache_locked(latest)

    def _save_cache_locked(self, cache: dict[str, Any]) -> None:
        entries = cache.get("entries", {})
        if isinstance(entries, dict):
            newest = sorted(
                entries.items(),
                key=lambda item: float(item[1].get("saved_at", 0))
                if isinstance(item[1], dict)
                else 0,
                reverse=True,
            )[:MAX_REGISTRY_CACHE_ENTRIES]
            bounded: dict[str, Any] = {}
            for key, value in newest:
                candidate = {"version": 1, "entries": {**bounded, key: value}}
                size = len(json.dumps(candidate, ensure_ascii=False).encode())
                if size > MAX_REGISTRY_CACHE_BYTES:
                    break
                bounded[key] = value
            cache = {"version": 1, "entries": bounded}
        atomic_write_private(
            self.cache_file, json.dumps(cache, separators=(",", ":"), ensure_ascii=False) + "\n"
        )

    def _request(self, query: str, limit: int) -> dict[str, Any]:
        with httpx.Client(
            timeout=httpx.Timeout(self.timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            transport=self.transport,
            headers={"User-Agent": "klaude-code/mcp-registry"},
        ) as client:
            with client.stream(
                "GET",
                f"{self.base_url}/v0.1/servers",
                params={"search": query, "limit": limit, "version": "latest"},
            ) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_REGISTRY_RESPONSE_BYTES:
                        raise MCPCatalogError("MCP Registry response exceeded the safety limit")
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise MCPCatalogError("MCP Registry returned invalid JSON") from exc
        if not isinstance(value, dict) or not isinstance(value.get("servers"), list):
            raise MCPCatalogError("MCP Registry returned an invalid response shape")
        return value

    def search(
        self,
        query: str,
        *,
        limit: int = 20,
        refresh: bool = False,
    ) -> tuple[list[MCPCatalogServer], bool]:
        query = " ".join(query.split())
        if not 1 <= len(query) <= 120:
            raise MCPCatalogError("search query must contain 1-120 characters")
        limit = max(1, min(50, int(limit)))
        key = self._cache_key(query, limit)
        cache = self._load_cache()
        cached = cache.get("entries", {}).get(key, {})
        age = time.time() - float(cached.get("saved_at", 0)) if isinstance(cached, dict) else 1e99
        payload = cached.get("payload") if isinstance(cached, dict) else None
        from_cache = False
        if not refresh and age <= REGISTRY_CACHE_TTL_SECONDS and isinstance(payload, dict):
            from_cache = True
        else:
            try:
                payload = self._request(query, limit)
            except (httpx.HTTPError, OSError, MCPCatalogError) as exc:
                if not isinstance(payload, dict) or age > REGISTRY_STALE_FALLBACK_SECONDS:
                    raise MCPCatalogError(f"request failed: {exc}") from exc
                from_cache = True
            else:
                entries = cache.setdefault("entries", {})
                entries[key] = {"saved_at": time.time(), "payload": payload}
                try:
                    self._save_cache(cache, key)
                except OSError:
                    # Cache persistence is optional. Preserve fresh discovery
                    # without following/replacing an unsafe cache symlink.
                    pass
        return _parse_servers(payload), from_cache

    def get(self, name: str, *, refresh: bool = False) -> MCPCatalogServer:
        results, _cached = self.search(name, limit=50, refresh=refresh)
        exact = [item for item in results if item.name == name]
        if not exact:
            raise MCPCatalogError(f"MCP Registry server not found: {name}")
        return exact[0]


def _parse_servers(payload: dict[str, Any]) -> list[MCPCatalogServer]:
    result: list[MCPCatalogServer] = []
    for entry in payload.get("servers", [])[:50]:
        if not isinstance(entry, dict) or not isinstance(entry.get("server"), dict):
            continue
        raw = entry["server"]
        meta_value = entry.get("_meta")
        meta: dict[str, Any] = meta_value if isinstance(meta_value, dict) else {}
        official = meta.get("io.modelcontextprotocol.registry/official", {})
        if not isinstance(official, dict):
            official = {}
        if official.get("status") != "active" or official.get("isLatest") is not True:
            continue
        name = _public_text(raw.get("name"), 200)
        version = _public_text(raw.get("version"), 255)
        description = _public_text(raw.get("description"), 500)
        if not _REGISTRY_NAME_RE.fullmatch(name) or not version or not description:
            continue
        publisher_meta_value = raw.get("_meta")
        publisher_meta: dict[str, Any] = (
            publisher_meta_value if isinstance(publisher_meta_value, dict) else {}
        )
        publisher = publisher_meta.get(
            "io.modelcontextprotocol.registry/publisher-provided", {}
        )
        if not isinstance(publisher, dict):
            publisher = {}
        repository_value = raw.get("repository")
        repository: dict[str, Any] = (
            repository_value if isinstance(repository_value, dict) else {}
        )
        result.append(
            MCPCatalogServer(
                name=name,
                title=_public_text(
                    raw.get("title") or publisher.get("title") or name.rsplit("/", 1)[-1],
                    100,
                ),
                description=description,
                version=version,
                status="active",
                repository_url=_safe_https_url(repository.get("url")),
                website_url=_safe_https_url(raw.get("websiteUrl")),
                raw=raw,
            )
        )
    return result
