"""Fixed, ordered MCP mutations; accepted writes are never cancelled as rollback."""

from __future__ import annotations

import json
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from klaude_core.mcp_client import (
    MAX_MCP_CONFIG_FILE_BYTES,
    MAX_MCP_TOOL_SCHEMA_CHARS,
    MCPRegistry,
    MCPServerConfig,
)

from .mcp_inventory import definition_digest
from .mcp_updates import registry_package_source, valid_version_only_change


@dataclass(frozen=True)
class MCPToggle:
    identity: str
    session_id: str
    name: str
    fingerprint: str
    enabled: bool


@dataclass(frozen=True)
class MCPEnable:
    identity: str
    session_id: str
    name: str
    fingerprint: str
    tools_json: str = field(repr=False)  # private immutable discovery snapshot


@dataclass(frozen=True)
class MCPReload:
    identity: str
    session_id: str
    name: str = field(default="catalog", init=False)


@dataclass(frozen=True)
class MCPRemove:
    identity: str
    session_id: str
    name: str
    fingerprint: str


@dataclass(frozen=True)
class MCPUpdateDisabled:
    identity: str
    session_id: str
    name: str
    fingerprint: str
    old_arg: str
    new_arg: str
    registry_version: str
    description: str


@dataclass(frozen=True)
class MCPAddDisabled:
    identity: str
    session_id: str
    name: str
    definition_json: str = field(repr=False)


@dataclass(frozen=True)
class MCPImport:
    identity: str
    session_id: str
    source_path: str = field(repr=False)
    name: str = field(default="import", init=False)


MCPMutation = (MCPToggle | MCPEnable | MCPReload | MCPAddDisabled | MCPImport
               | MCPRemove | MCPUpdateDisabled)


@dataclass(frozen=True)
class MCPMutationResult:
    request: MCPMutation
    path: str
    state: str  # saved, loaded, rejected, or unconfirmed
    catalog: Any = field(default=None, repr=False)  # private tools, never IPC/transcript
    count: int = 0
    cleanup_failed: bool = False


class MCPMutationWriter:
    """One daemon lane with bounded acceptance and bounded shutdown waiting.

    A filesystem stall cannot be killed safely. Ownership stays with this lane;
    close returns unconfirmed instead of claiming an accepted write rolled back.
    The fixed prepare callback constructs cached tools only, never transports.
    """

    def __init__(self, path: Path, emit, prepare, *, auth_dir: Path | None = None):
        self.path = Path(path)
        self.auth_dir = auth_dir
        self.emit = emit
        self.prepare = prepare
        self._condition = threading.Condition()
        self._pending: deque[MCPMutation] = deque()
        self._active = False
        self._closed = False
        self._unconfirmed = False
        self._thread: threading.Thread | None = None

    def submit(self, request: MCPMutation) -> bool:
        if (
            not isinstance(request, (
                MCPToggle, MCPEnable, MCPReload, MCPAddDisabled, MCPImport, MCPRemove,
                MCPUpdateDisabled,
            ))
            or not all(isinstance(value, str) and 0 < len(value) <= 128 for value in (
                request.identity, request.session_id, request.name,
            ))
            or isinstance(request, (MCPToggle, MCPEnable, MCPRemove, MCPUpdateDisabled)) and (
                not isinstance(request.fingerprint, str)
                or not re.fullmatch(r"[a-f0-9]{64}", request.fingerprint)
            )
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", request.name)
            or isinstance(request, MCPToggle) and type(request.enabled) is not bool
            or isinstance(request, MCPEnable) and (
                not isinstance(request.tools_json, str)
                or len(request.tools_json) > MAX_MCP_CONFIG_FILE_BYTES
            )
            or isinstance(request, MCPAddDisabled) and (
                not isinstance(request.definition_json, str)
                or len(request.definition_json) > MAX_MCP_CONFIG_FILE_BYTES
            )
            or isinstance(request, MCPImport) and (
                not isinstance(request.source_path, str) or not request.source_path
                or len(request.source_path) > 4096 or "\x00" in request.source_path
                or not Path(request.source_path).is_absolute()
            )
            or isinstance(request, MCPUpdateDisabled) and (
                not all(isinstance(value, str) and value and len(value) <= 500
                        for value in (request.old_arg, request.new_arg,
                                      request.registry_version))
                or not isinstance(request.description, str)
                or len(request.description) > 500
                or not all(char.isprintable() for char in (
                    request.old_arg + request.new_arg + request.registry_version
                    + request.description
                ))
            )
        ):
            return False
        with self._condition:
            if self._closed or len(self._pending) + int(self._active) >= 16:
                return False
            self._pending.append(request)
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name="klaude-mcp-mutations", daemon=True
                )
                self._thread.start()
            self._condition.notify()
            return True

    def _apply(self, request: MCPMutation) -> MCPMutationResult:
        registry = MCPRegistry(self.path)
        saving = False
        state = "rejected"
        catalog = None
        count = 0
        cleanup_failed = False
        try:
            servers = registry.load()
            if isinstance(request, MCPReload):
                snapshot = {name: definition_digest(item) for name, item in servers.items()}
                prepared = self.prepare(servers)
                verified = {name: definition_digest(item) for name, item in registry.load().items()}
                if snapshot != verified or prepared is None:
                    return MCPMutationResult(request, str(self.path), "rejected")
                return MCPMutationResult(request, str(self.path), "loaded", prepared)
            if isinstance(request, MCPImport):
                imported = registry.import_file(Path(request.source_path))
                if not imported or set(servers).intersection(imported):
                    return MCPMutationResult(request, str(self.path), "rejected")
                for item in imported.values():
                    item.enabled = False
                    item.tools = []
                servers.update(imported)
                count = len(imported)
            elif isinstance(request, MCPAddDisabled):
                if request.name in servers:
                    return MCPMutationResult(request, str(self.path), "rejected")
                definition = json.loads(request.definition_json)
                if not isinstance(definition, dict):
                    return MCPMutationResult(request, str(self.path), "rejected")
                server = MCPServerConfig.from_dict(request.name, definition)
                server.enabled = False
                server.tools = []
                servers[request.name] = server
            else:
                existing = servers.get(request.name)
                if existing is None or definition_digest(existing) != request.fingerprint:
                    return MCPMutationResult(request, str(self.path), "rejected")
                server = existing
            if isinstance(request, MCPEnable):
                tools = json.loads(request.tools_json)
                if not isinstance(tools, list) or len(tools) > 128 or not all(
                    isinstance(tool, dict) and isinstance(tool.get("name"), str)
                    and tool["name"] and isinstance(tool.get("inputSchema"), dict)
                    and tool["inputSchema"].get("type", "object") == "object"
                    and len(json.dumps(tool)) <= MAX_MCP_TOOL_SCHEMA_CHARS
                    for tool in tools
                ):
                    return MCPMutationResult(request, str(self.path), "rejected")
                server.tools = tools
                server.enabled = True
            elif isinstance(request, MCPToggle):
                if request.enabled and not server.tools:
                    return MCPMutationResult(request, str(self.path), "rejected")
                server.enabled = request.enabled
            elif isinstance(request, MCPUpdateDisabled):
                if not registry_package_source(server) or (
                    server.args.count(request.old_arg) != 1
                    or not valid_version_only_change(
                        server.command, request.old_arg, request.new_arg
                    )
                ):
                    return MCPMutationResult(request, str(self.path), "rejected")
                server.args = [request.new_arg if arg == request.old_arg else arg
                               for arg in server.args]
                server.source["version"] = request.registry_version
                server.source["description"] = request.description
                server.enabled = False
                server.tools = []
            elif isinstance(request, MCPRemove):
                del servers[request.name]
            saving = True
            registry.save(servers)
            state = "saved"
            if isinstance(request, MCPRemove) and server.oauth and self.auth_dir is not None:
                from klaude_core.mcp_client import MCPTokenStorage, mcp_auth_file

                try:
                    MCPTokenStorage(mcp_auth_file(self.auth_dir, request.name)).clear()
                except OSError:
                    cleanup_failed = True
            # Fresh snapshot includes unrelated changes merged by registry CAS.
            catalog = self.prepare(registry.load())
        except Exception:
            # Do not disclose private definitions or assume an atomic-replace
            # failure happened before publication. No automatic retry.
            if saving and state != "saved":
                state = "unconfirmed"
        return MCPMutationResult(request, str(self.path), state, catalog, count, cleanup_failed)

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._pending)
                if not self._pending:
                    return
                request = self._pending.popleft()
                self._active = True
            result = self._apply(request)
            with self._condition:
                self._active = False
                self._unconfirmed |= result.state == "unconfirmed"
                if result.state == "loaded":
                    self._unconfirmed = False
            self.emit("mcp_mutation_saved", result)

    def close(self, *, wait: bool = False) -> bool:
        with self._condition:
            self._closed = True
            self._condition.notify()
        if wait and self._thread is not None:
            self._thread.join(2)
        with self._condition:
            return not self._unconfirmed and not self._active and not self._pending
