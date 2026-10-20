"""Fixed, ordered MCP mutations; accepted writes are never cancelled as rollback."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from klaude_core.mcp_client import (
    MAX_MCP_AUTH_FILE_BYTES,
    MAX_MCP_CONFIG_FILE_BYTES,
    MAX_MCP_TOOL_SCHEMA_CHARS,
    MCPRegistry,
    MCPServerConfig,
    MCPTokenStorage,
    mcp_auth_file,
)
from klaude_core.settings_store import settings_lock

from .mcp_inventory import definition_digest
from .mcp_updates import registry_package_source, valid_version_only_change
from .operation_journal import (
    OperationConflict,
    OperationFenceLost,
    OperationJournal,
    OperationReceipt,
)


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
class MCPOAuthEnable:
    identity: str
    session_id: str
    name: str
    fingerprint: str
    scope: str
    client_metadata_url: str
    tools_json: str = field(repr=False)


@dataclass(frozen=True)
class MCPOAuthLogout:
    identity: str
    session_id: str
    name: str
    fingerprint: str


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
class MCPAddVerified:
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


@dataclass(frozen=True)
class MCPImportSnapshot:
    identity: str
    session_id: str
    definitions_json: str = field(repr=False)
    name: str = field(default="import", init=False)


MCPMutation = (
    MCPToggle | MCPEnable | MCPOAuthEnable | MCPOAuthLogout | MCPReload
    | MCPAddDisabled | MCPAddVerified
    | MCPImport | MCPImportSnapshot | MCPRemove | MCPUpdateDisabled
)


@dataclass(frozen=True)
class MCPMutationResult:
    request: MCPMutation
    path: str
    state: str  # saved, loaded, rejected, or unconfirmed
    catalog: Any = field(default=None, repr=False)  # private tools, never IPC/transcript
    count: int = 0
    cleanup_failed: bool = False


def mcp_resource(path: Path) -> str:
    """Stable journal resource identity for the selected private registry."""
    return "mcp:" + hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()


def _auth_snapshot(auth_dir: Path) -> tuple[tuple[str, str], ...]:
    """Hash bounded private OAuth files while sharing their cross-process lock."""
    if auth_dir.is_symlink():
        raise ValueError("Unsafe MCP credential directory")
    with settings_lock(auth_dir / ".mcp-auth", timeout=2):
        return _auth_snapshot_locked(auth_dir)


def _auth_snapshot_locked(auth_dir: Path) -> tuple[tuple[str, str], ...]:
    """Caller holds the shared credential lock."""
    descriptor = os.open(auth_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        directory = os.fstat(descriptor)
        if directory.st_uid != os.getuid() or directory.st_mode & 0o077:
            raise ValueError("MCP credential directory must be owner-only")
        values: list[tuple[str, str]] = []
        total = 0
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                if len(values) >= 256:
                    raise ValueError("Too many MCP credential files for recovery")
                item_fd = os.open(
                    entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=descriptor,
                )
                try:
                    info = os.fstat(item_fd)
                    if (
                        not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                        or info.st_mode & 0o077
                        or info.st_size > MAX_MCP_AUTH_FILE_BYTES
                    ):
                        raise ValueError("Unsafe MCP credential file")
                    data = os.read(item_fd, MAX_MCP_AUTH_FILE_BYTES + 1)
                    if len(data) > MAX_MCP_AUTH_FILE_BYTES:
                        raise ValueError("MCP credential file exceeds recovery limit")
                    total += len(data)
                    if total > 8_000_000:
                        raise ValueError("MCP credentials exceed recovery scan limit")
                    values.append((entry.name, hashlib.sha256(data).hexdigest()))
                finally:
                    os.close(item_fd)
        return tuple(sorted(values))
    finally:
        os.close(descriptor)


class MCPMutationWriter:
    """One daemon lane with bounded acceptance and bounded shutdown waiting.

    A filesystem stall cannot be killed safely. Ownership stays with this lane;
    close returns unconfirmed instead of claiming an accepted write rolled back.
    The fixed prepare callback constructs cached tools only, never transports.
    """

    def __init__(
        self,
        path: Path,
        emit,
        prepare,
        *,
        auth_dir: Path | None = None,
        journal: OperationJournal | None = None,
        require_journal: bool = False,
    ):
        self.path = Path(path)
        self.auth_dir = auth_dir
        self.emit = emit
        self.prepare = prepare
        self.journal = journal
        self._require_journal = require_journal
        self._resource = mcp_resource(self.path)
        self._condition = threading.Condition()
        self._pending: deque[MCPMutation] = deque()
        self._active = False
        self._closed = False
        self._unconfirmed = False
        self._thread: threading.Thread | None = None

    def _admit_journal(self, request: MCPMutation) -> bool:
        if self.journal is None or isinstance(request, MCPReload):
            return True
        try:
            intent = json.dumps(asdict(request), sort_keys=True,
                                separators=(",", ":"), ensure_ascii=False).encode()
            if len(intent) > 2_000_000:
                return False
            receipt = self.journal.admit(
                request_id=request.identity,
                owner_id=request.session_id,
                kind=type(request).__name__,
                resource=self._resource,
                payload={"sha256": hashlib.sha256(intent).hexdigest()},
                lease_seconds=60,
            )
            return receipt.created
        except (ValueError, OSError, sqlite3.Error, OperationConflict):
            return False

    def submit(self, request: MCPMutation) -> bool:
        if (
            not isinstance(
                request,
                (
                    MCPToggle,
                    MCPEnable,
                    MCPOAuthEnable,
                    MCPOAuthLogout,
                    MCPReload,
                    MCPAddDisabled,
                    MCPAddVerified,
                    MCPImport,
                    MCPImportSnapshot,
                    MCPRemove,
                    MCPUpdateDisabled,
                ),
            )
            or not all(
                isinstance(value, str) and 0 < len(value) <= 128
                for value in (
                    request.identity,
                    request.session_id,
                    request.name,
                )
            )
            or isinstance(request, (MCPToggle, MCPEnable, MCPOAuthEnable,
                                    MCPOAuthLogout,
                                    MCPRemove, MCPUpdateDisabled))
            and (
                not isinstance(request.fingerprint, str)
                or not re.fullmatch(r"[a-f0-9]{64}", request.fingerprint)
            )
            or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", request.name)
            or isinstance(request, MCPToggle)
            and type(request.enabled) is not bool
            or isinstance(request, (MCPEnable, MCPOAuthEnable))
            and (
                not isinstance(request.tools_json, str)
                or len(request.tools_json) > MAX_MCP_CONFIG_FILE_BYTES
            )
            or isinstance(request, MCPOAuthEnable)
            and (
                not isinstance(request.scope, str) or len(request.scope) > 2_000
                or not isinstance(request.client_metadata_url, str)
                or len(request.client_metadata_url) > 8_192
            )
            or isinstance(request, (MCPAddDisabled, MCPAddVerified))
            and (
                not isinstance(request.definition_json, str)
                or len(request.definition_json) > MAX_MCP_CONFIG_FILE_BYTES
            )
            or isinstance(request, MCPImport)
            and (
                not isinstance(request.source_path, str)
                or not request.source_path
                or len(request.source_path) > 4096
                or "\x00" in request.source_path
                or not Path(request.source_path).is_absolute()
            )
            or isinstance(request, MCPImportSnapshot)
            and (
                not isinstance(request.definitions_json, str)
                or not 0 < len(request.definitions_json) <= MAX_MCP_CONFIG_FILE_BYTES
            )
            or isinstance(request, MCPUpdateDisabled)
            and (
                not all(
                    isinstance(value, str) and value and len(value) <= 500
                    for value in (request.old_arg, request.new_arg, request.registry_version)
                )
                or not isinstance(request.description, str)
                or len(request.description) > 500
                or not all(
                    char.isprintable()
                    for char in (
                        request.old_arg
                        + request.new_arg
                        + request.registry_version
                        + request.description
                    )
                )
            )
        ):
            return False
        with self._condition:
            if self._closed or len(self._pending) + int(self._active) >= 16:
                return False
            if self._require_journal and self.journal is None \
                    and not isinstance(request, MCPReload):
                return False
            if not self._admit_journal(request):
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
        fence = 0
        try:
            servers = registry.load()
            if isinstance(request, MCPReload):
                snapshot = {name: definition_digest(item) for name, item in servers.items()}
                prepared = self.prepare(servers)
                verified = {name: definition_digest(item) for name, item in registry.load().items()}
                if snapshot != verified or prepared is None:
                    return MCPMutationResult(request, str(self.path), "rejected")
                return MCPMutationResult(request, str(self.path), "loaded", prepared)
            before = {name: item.to_dict() for name, item in servers.items()}
            if isinstance(request, (MCPImport, MCPImportSnapshot)):
                if isinstance(request, MCPImport):
                    imported = registry.import_file(Path(request.source_path))
                else:
                    raw = json.loads(request.definitions_json)
                    if (
                        not isinstance(raw, dict) or not 0 < len(raw) <= 256
                        or not all(isinstance(name, str) and isinstance(value, dict)
                                   for name, value in raw.items())
                    ):
                        return MCPMutationResult(request, str(self.path), "rejected")
                    imported = {
                        name: MCPServerConfig.from_dict(name, value)
                        for name, value in raw.items()
                    }
                if not imported or set(servers).intersection(imported):
                    return MCPMutationResult(request, str(self.path), "rejected")
                for item in imported.values():
                    item.enabled = False
                    item.tools = []
                servers.update(imported)
                count = len(imported)
            elif isinstance(request, (MCPAddDisabled, MCPAddVerified)):
                if request.name in servers:
                    return MCPMutationResult(request, str(self.path), "rejected")
                definition = json.loads(request.definition_json)
                if not isinstance(definition, dict):
                    return MCPMutationResult(request, str(self.path), "rejected")
                server = MCPServerConfig.from_dict(request.name, definition)
                if isinstance(request, MCPAddDisabled):
                    server.enabled = False
                    server.tools = []
                elif (
                    not server.enabled or server.oauth or not server.tools
                    or len(server.tools) > 128
                    or not all(
                        isinstance(tool, dict)
                        and isinstance(tool.get("name"), str) and tool["name"]
                        and isinstance(tool.get("inputSchema"), dict)
                        and tool["inputSchema"].get("type", "object") == "object"
                        and len(json.dumps(tool)) <= MAX_MCP_TOOL_SCHEMA_CHARS
                        for tool in server.tools
                    )
                ):
                    return MCPMutationResult(request, str(self.path), "rejected")
                servers[request.name] = server
            else:
                existing = servers.get(request.name)
                if existing is None or definition_digest(existing) != request.fingerprint:
                    return MCPMutationResult(request, str(self.path), "rejected")
                server = existing
            if isinstance(request, (MCPEnable, MCPOAuthEnable)):
                tools = json.loads(request.tools_json)
                if (
                    not isinstance(tools, list)
                    or len(tools) > 128
                    or not all(
                        isinstance(tool, dict)
                        and isinstance(tool.get("name"), str)
                        and tool["name"]
                        and isinstance(tool.get("inputSchema"), dict)
                        and tool["inputSchema"].get("type", "object") == "object"
                        and len(json.dumps(tool)) <= MAX_MCP_TOOL_SCHEMA_CHARS
                        for tool in tools
                    )
                ):
                    return MCPMutationResult(request, str(self.path), "rejected")
                if isinstance(request, MCPOAuthEnable):
                    if self.auth_dir is None or not MCPTokenStorage(
                        mcp_auth_file(self.auth_dir, request.name)
                    ).status().access_token_present:
                        return MCPMutationResult(request, str(self.path), "rejected")
                    server.oauth = True
                    server.oauth_scope = request.scope
                    server.oauth_client_metadata_url = request.client_metadata_url
                    server.validate()
                server.tools = tools
                server.enabled = True
            elif isinstance(request, MCPToggle):
                if request.enabled and not server.tools:
                    return MCPMutationResult(request, str(self.path), "rejected")
                server.enabled = request.enabled
            elif isinstance(request, MCPOAuthLogout):
                if not server.oauth or self.auth_dir is None:
                    return MCPMutationResult(request, str(self.path), "rejected")
                server.enabled = False
            elif isinstance(request, MCPUpdateDisabled):
                if not registry_package_source(server) or (
                    server.args.count(request.old_arg) != 1
                    or not valid_version_only_change(
                        server.command, request.old_arg, request.new_arg
                    )
                ):
                    return MCPMutationResult(request, str(self.path), "rejected")
                server.args = [
                    request.new_arg if arg == request.old_arg else arg for arg in server.args
                ]
                server.source["version"] = request.registry_version
                server.source["description"] = request.description
                server.enabled = False
                server.tools = []
            elif isinstance(request, MCPRemove):
                del servers[request.name]
            if self.journal is not None:
                receipt = self.journal.status(request.identity, request.session_id)
                if receipt is None:
                    raise OperationFenceLost("Operation admission unavailable")
                fence = receipt.fence
                after = {name: item.to_dict() for name, item in servers.items()}
                if isinstance(request, (MCPOAuthEnable, MCPOAuthLogout)) or (
                    isinstance(request, MCPRemove) and server.oauth
                ):
                    if self.auth_dir is None:
                        return MCPMutationResult(request, str(self.path), "rejected")
                    auth_before = _auth_snapshot(self.auth_dir)
                    auth_after = auth_before
                    if isinstance(request, (MCPRemove, MCPOAuthLogout)):
                        filename = mcp_auth_file(self.auth_dir, request.name).name
                        auth_after = tuple(
                            item for item in auth_before if item[0] != filename
                        )
                    witness_before: object = {"registry": before, "auth": auth_before}
                    witness_after: object = {"registry": after, "auth": auth_after}
                else:
                    witness_before = before
                    witness_after = after
                self.journal.record_witness(
                    request.identity, request.session_id, fence,
                    before=witness_before, after=witness_after,
                )
                self.journal.start(request.identity, request.session_id, fence)
            saving = True
            if self.journal is None:
                registry.save(servers)
            else:
                journal = self.journal

                def before_publish() -> None:
                    journal.check_effect(request.identity, request.session_id, fence)
                    # The witness describes the whole registry. A legacy or
                    # direct writer may have changed an unrelated definition
                    # while this request waited for the file lock; do not
                    # publish an unwitnessed merged state.
                    current = {
                        name: item.to_dict()
                        for name, item in MCPRegistry(self.path).load().items()
                    }
                    if current != before:
                        raise OperationFenceLost(
                            "MCP configuration changed after reviewed snapshot"
                        )

                registry.save(
                    servers,
                    before_publish=before_publish,
                )
            state = "saved"
            if isinstance(request, (MCPRemove, MCPOAuthLogout)) and server.oauth \
                    and self.auth_dir is not None:
                try:
                    token_store = MCPTokenStorage(mcp_auth_file(self.auth_dir, request.name))
                    if self.journal is None:
                        cleared = token_store.clear()
                    else:
                        journal = self.journal
                        expected_auth = auth_before
                        auth_dir = self.auth_dir

                        def before_clear() -> None:
                            journal.check_effect(request.identity, request.session_id, fence)
                            if _auth_snapshot_locked(auth_dir) != expected_auth:
                                raise OperationFenceLost(
                                    "MCP credentials changed after reviewed snapshot"
                                )

                        cleared = token_store.clear(
                            before_clear=before_clear
                        )
                    if not cleared and token_store.path.is_symlink():
                        cleanup_failed = True
                except (OSError, OperationFenceLost):
                    cleanup_failed = True
            # Refresh the prepared catalog from the durable result.
            catalog = self.prepare(registry.load())
        except OperationFenceLost:
            # The effect gate runs before atomic publication. A failed gate
            # cannot have published this request's configuration change.
            state = "rejected"
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
            result = self._settle_journal(request, result)
            with self._condition:
                self._active = False
                self._unconfirmed |= result.state == "unconfirmed"
                if result.state == "loaded":
                    if self.journal is None:
                        self._unconfirmed = False
                    else:
                        try:
                            self._unconfirmed = self.journal.resource_busy(self._resource)
                        except (OSError, sqlite3.Error):
                            self._unconfirmed = True
            self.emit("mcp_mutation_saved", result)

    def _settle_journal(
        self, request: MCPMutation, result: MCPMutationResult
    ) -> MCPMutationResult:
        if self.journal is None or isinstance(request, MCPReload):
            return result
        try:
            receipt = self.journal.status(request.identity, request.session_id)
            if receipt is None:
                raise OperationFenceLost("Operation admission unavailable")
            if receipt.state == "cancelled" and result.state == "rejected":
                # Admission expired before start; no effect passed the gate.
                pass
            elif result.state == "unconfirmed" or result.cleanup_failed:
                self.journal.mark_unknown(request.identity, request.session_id,
                                          receipt.fence)
                if result.cleanup_failed and result.state == "saved":
                    result = MCPMutationResult(
                        request, str(self.path), "unconfirmed", cleanup_failed=True
                    )
            else:
                self.journal.finish(
                    request.identity, request.session_id, receipt.fence,
                    state="completed" if result.state == "saved" else "failed",
                    outcome=("partial" if result.cleanup_failed else "ok")
                    if result.state == "saved" else "failed",
                )
        except (OSError, sqlite3.Error, OperationFenceLost):
            return MCPMutationResult(
                request, str(self.path), "unconfirmed", cleanup_failed=True
            )
        return result

    def close(self, *, wait: bool = False) -> bool:
        with self._condition:
            self._closed = True
            self._condition.notify()
        if wait and self._thread is not None:
            self._thread.join(2)
        with self._condition:
            return not self._unconfirmed and not self._active and not self._pending


def apply_embedded_mcp_mutation(
    path: Path, request: MCPToggle | MCPEnable | MCPOAuthEnable | MCPOAuthLogout | MCPRemove
    | MCPAddDisabled | MCPAddVerified | MCPImportSnapshot, *,
    auth_dir: Path | None = None, journal: OperationJournal | None = None,
) -> MCPMutationResult:
    """Run one reviewed terminal mutation through the same fixed effect path.

    The optional journal gives CLI callers the same fenced effect path as the
    TUI. This is not a browser authorization boundary; the caller owns review
    and discovery.
    """
    if (
        not isinstance(request, (MCPToggle, MCPEnable, MCPOAuthEnable,
                                 MCPOAuthLogout, MCPRemove,
                                 MCPAddDisabled, MCPAddVerified, MCPImportSnapshot))
        or not all(
            isinstance(value, str) and 0 < len(value) <= 128
            for value in (request.identity, request.session_id)
        )
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", request.name)
        or isinstance(request, (MCPToggle, MCPEnable, MCPOAuthEnable,
                                MCPOAuthLogout, MCPRemove))
        and not re.fullmatch(r"[a-f0-9]{64}", request.fingerprint)
        or isinstance(request, MCPToggle) and type(request.enabled) is not bool
        or isinstance(request, (MCPEnable, MCPOAuthEnable)) and (
            not isinstance(request.tools_json, str)
            or len(request.tools_json) > MAX_MCP_CONFIG_FILE_BYTES
        )
        or isinstance(request, MCPOAuthEnable) and (
            not isinstance(request.scope, str) or len(request.scope) > 2_000
            or not isinstance(request.client_metadata_url, str)
            or len(request.client_metadata_url) > 8_192
        )
        or isinstance(request, (MCPAddDisabled, MCPAddVerified)) and (
            not isinstance(request.definition_json, str)
            or len(request.definition_json) > MAX_MCP_CONFIG_FILE_BYTES
        )
        or isinstance(request, MCPImportSnapshot) and (
            not isinstance(request.definitions_json, str)
            or not 0 < len(request.definitions_json) <= MAX_MCP_CONFIG_FILE_BYTES
        )
    ):
        raise ValueError("Invalid reviewed MCP mutation")
    writer = MCPMutationWriter(path, lambda *_: None, lambda _servers: None,
                               auth_dir=auth_dir, journal=journal)
    if not writer._admit_journal(request):
        return MCPMutationResult(request, str(path), "rejected")
    return writer._settle_journal(request, writer._apply(request))


def recover_mcp_mutation(
    path: Path, journal: OperationJournal, request_id: str, owner_id: str, *,
    auth_dir: Path | None = None,
) -> OperationReceipt:
    """Reconcile an uncertain definition write from an exact private snapshot.

    OAuth login/removal also compare a bounded credential-file snapshot. A
    partial configuration/credential change stays fenced for review.
    """
    fenced = journal.fenced_operation(mcp_resource(path))
    if (
        fenced is None or fenced.owner_id != owner_id
        or fenced.receipt.request_id != request_id
        or fenced.receipt.state != "unknown"
    ):
        raise OperationConflict("Matching uncertain MCP operation unavailable")
    with settings_lock(Path(path), timeout=2):
        current = {
            name: item.to_dict() for name, item in MCPRegistry(Path(path)).load().items()
        }
        try:
            return journal.reconcile_witness(request_id, owner_id, current=current)
        except OperationConflict as exc:
            if auth_dir is None or "differs from both reviewed states" not in str(exc):
                raise
        if auth_dir.is_symlink():
            raise ValueError("Unsafe MCP credential directory")
        with settings_lock(auth_dir / ".mcp-auth", timeout=2):
            auth_current = _auth_snapshot_locked(auth_dir)
            return journal.reconcile_witness(
                request_id, owner_id,
                current={"registry": current, "auth": auth_current},
            )


def finish_mcp_oauth_cleanup(
    path: Path, auth_dir: Path, journal: OperationJournal,
    request_id: str, owner_id: str, name: str,
) -> OperationReceipt:
    """Finish only the exact credential deletion witnessed by an uncertain remove.

    The caller owns the explicit user review. No definition is written or
    remote request sent; a mismatch leaves both files and the fence intact.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
        raise ValueError("Invalid MCP server name")
    fenced = journal.fenced_operation(mcp_resource(path))
    if (
        fenced is None or fenced.owner_id != owner_id
        or fenced.receipt.request_id != request_id
        or fenced.receipt.kind not in {"MCPRemove", "MCPOAuthLogout"}
        or fenced.receipt.state != "unknown"
    ):
        raise OperationConflict("Matching uncertain MCP removal unavailable")
    if auth_dir.is_symlink():
        raise ValueError("Unsafe MCP credential directory")
    with settings_lock(Path(path), timeout=2), settings_lock(
        auth_dir / ".mcp-auth", timeout=2
    ):
        current = {
            item: server.to_dict()
            for item, server in MCPRegistry(Path(path)).load().items()
        }
        auth_current = _auth_snapshot_locked(auth_dir)
        filename = mcp_auth_file(auth_dir, name).name
        if filename not in {item[0] for item in auth_current}:
            raise OperationConflict("Reviewed OAuth credential is not present")
        predicted = tuple(item for item in auth_current if item[0] != filename)
        if not journal.witness_after_matches(
            request_id, owner_id,
            candidate={"registry": current, "auth": predicted},
        ):
            raise OperationConflict("OAuth cleanup does not match reviewed final state")
        credential = mcp_auth_file(auth_dir, name)
        if credential.is_symlink():
            raise ValueError("Unsafe MCP credential file")
        credential.unlink()
        return journal.reconcile_witness(
            request_id, owner_id,
            current={"registry": current, "auth": _auth_snapshot_locked(auth_dir)},
        )
