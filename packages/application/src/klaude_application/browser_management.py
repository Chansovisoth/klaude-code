"""Fixed, reviewed profile operations for the authenticated local owner.

HTTP adapters supply only drafts. Trusted config selects every storage path;
effects run in the existing owned, journaled management worker.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from klaude_core.config import Config
from klaude_core.mcp_client import MCPClient, MCPRegistry, MCPServerConfig
from klaude_core.memory import Memory, is_sensitive_memory

from .browser_sessions import prepare_session_operation, run_session_operation
from .browser_settings import prepare_setting, save_setting
from .mcp_inventory import definition_digest, read_mcp_inventory
from .mcp_mutations import (
    MCPAddDisabled,
    MCPEnable,
    MCPRemove,
    MCPToggle,
    apply_embedded_mcp_mutation,
    mcp_resource,
)
from .memory_inventory import read_memory_inventory
from .operation_journal import OperationJournal

OPERATIONS = frozenset({
    "memory-add", "memory-edit", "memory-delete", "memory-auto",
    "mcp-add", "mcp-enable", "mcp-disable", "mcp-remove",
    "session-rename", "session-archive", "session-restore", "session-delete",
    "setting-save",
    "artifact-learn",
})


def _fact(value: object) -> str:
    if (not isinstance(value, str) or not 1 <= len(value.strip()) <= 500
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)):
        raise ValueError("Enter one memory fact, up to 500 characters")
    value = value.strip()
    if is_sensitive_memory(value):
        raise ValueError("Passwords, tokens and other sensitive values cannot be saved as memory")
    return value


def prepare_profile_operation(
    cfg: Config, draft: dict[str, Any], workspace: Path | None = None,
) -> tuple[dict[str, Any], str, str]:
    operation = draft["operation"]
    fields: dict[str, Any]
    if operation == "artifact-learn":
        from klaude_core.library_artifacts import ArtifactStore

        from .library_knowledge import MAX_SOURCE_BYTES, KnowledgeAction, knowledge_worker_request

        if workspace is None or set(draft) != {"operation", "target", "revision", "library"}:
            raise ValueError("Choose a saved file and Knowledge library")
        action = KnowledgeAction.from_draft({"operation": "learn-artifact",
                                            "artifact": draft["target"],
                                            "revision": draft["revision"],
                                            "library": draft["library"]})
        item = ArtifactStore(cfg.data_dir / "library").get(action.artifact)
        if (item["revision"] != action.revision or item["archived"]
                or item["size"] > MAX_SOURCE_BYTES or item["mime"].startswith("image/")):
            raise ValueError("Choose a saved text, PDF or DOCX file of at most 2 MiB")
        knowledge_worker_request(action, cfg, data_dir=cfg.data_dir, workspace=workspace)
        return {"artifact": action.artifact, "revision": action.revision,
                "library": action.library}, "knowledge-index", (
            f"Learn {item['name']} into {action.library} using the configured embedding model. "
            "Text files are limited to 2 MiB. PDF/DOCX text is limited to 32,000 characters."
        )
    if operation == "setting-save":
        return prepare_setting(cfg, draft)
    if operation.startswith("session-"):
        if workspace is None:
            raise ValueError("Workspace unavailable")
        return prepare_session_operation(cfg.sessions_db, workspace, draft)
    if operation.startswith("memory-"):
        inventory = read_memory_inventory(cfg.sessions_db, cfg.memory_file)
        if operation == "memory-auto":
            if (set(draft) != {"operation", "enabled", "expected_enabled"}
                    or type(draft["enabled"]) is not bool
                    or type(draft["expected_enabled"]) is not bool
                    or inventory["enabled"] != draft["expected_enabled"]):
                raise ValueError("Memory setting changed; reload before reviewing")
            fields = {"enabled": draft["enabled"], "expected_enabled": draft["expected_enabled"]}
            return fields, "memory-settings", (
                f"{'Enable' if draft['enabled'] else 'Disable'} automatic memory for future turns."
            )
        if operation == "memory-add":
            if set(draft) != {"operation", "fact"}:
                raise ValueError("Invalid memory draft")
            fact = _fact(draft["fact"])
            return {"fact": fact}, "memory-facts", f"Remember: {fact}"
        if set(draft) != ({"operation", "id", "fact"} if operation == "memory-edit"
                          else {"operation", "id"}):
            raise ValueError("Invalid memory draft")
        entries = inventory["entries"]
        assert isinstance(entries, list)
        entry = next((item for item in entries if item["id"] == draft["id"]), None)
        if entry is None:
            raise ValueError("Memory changed; reload before reviewing")
        fields = {"id": entry["id"]}
        summary = f"Forget this exact memory: {entry['fact']}"
        if operation == "memory-edit":
            fields["fact"] = _fact(draft["fact"])
            summary = f"Replace memory: {entry['fact']}\n\nWith: {fields['fact']}"
        return fields, "memory-facts", summary
    if operation == "mcp-add":
        if set(draft) != {"operation", "name", "url"} or not all(
            isinstance(draft[key], str) for key in ("name", "url")
        ):
            raise ValueError("Enter an MCP connection name and URL")
        server = MCPServerConfig.from_dict(draft["name"], {
            "transport": "http", "url": draft["url"], "enabled": False,
        })
        if server.name in MCPRegistry(cfg.mcp_servers_file).load():
            raise ValueError("Connection already exists; choose another name")
        return {"name": server.name, "url": server.url}, mcp_resource(cfg.mcp_servers_file), (
            f"Add MCP connection {server.name} at {server.url}, disabled. "
            "Enabling it requires a separate review."
        )
    if operation not in {"mcp-enable", "mcp-disable", "mcp-remove"} or set(draft) != {
        "operation", "name", "fingerprint"
    }:
        raise ValueError("Invalid connection action")
    inventory = read_mcp_inventory(cfg.mcp_servers_file)
    servers = inventory["servers"]
    assert isinstance(servers, list)
    server_view = next((item for item in servers if item["name"] == draft["name"]), None)
    if server_view is None or server_view["fingerprint"] != draft["fingerprint"]:
        raise ValueError("Connection changed; reload before reviewing")
    if operation == "mcp-enable" and server_view["oauth"]:
        raise ValueError("Sign in to this OAuth connection through Klaude's CLI first")
    verb = operation.removeprefix("mcp-").capitalize()
    summary = f"{verb} MCP connection {server_view['name']}."
    if operation == "mcp-enable":
        summary += " Connects to the configured server to discover tools."
        if server_view["transport"] == "stdio":
            summary += " This launches its configured program on the Klaude server."
    if operation == "mcp-remove":
        summary += " Removes its definition and saved OAuth credentials."
    return {"name": server_view["name"], "fingerprint": server_view["fingerprint"]}, (
        mcp_resource(cfg.mcp_servers_file)
    ), summary


def run_profile_operation(cfg: Config, request: dict[str, Any]) -> dict[str, bool]:
    operation = request["operation"]
    if operation == "artifact-learn":
        from .library_knowledge import KnowledgeAction, knowledge_worker_request, run_operation

        action = KnowledgeAction.from_draft({"operation": "learn-artifact",
                                            **{key: request[key] for key in (
                                                "artifact", "revision", "library"
                                            )}})
        learning = run_operation(knowledge_worker_request(
            action, cfg, data_dir=cfg.data_dir, workspace=Path(request["workspace"]),
        ))
        if learning.get("status") == "rejected":
            return {"rejected": True}
        return {"ok": learning.get("status") in {"learned", "unchanged"}}
    if operation == "setting-save":
        from klaude_core.settings_store import SettingsConflictError

        try:
            save_setting(cfg, request)
        except (ValueError, SettingsConflictError):
            return {"rejected": True}
        return {"ok": True}
    if operation.startswith("session-"):
        memory = Memory(cfg.memory_file, cfg.sessions_db)
        try:
            return {"ok": True} if run_session_operation(
                memory, Path(request["workspace"]), request
            ) else {"rejected": True}
        except ValueError:
            return {"rejected": True}
        finally:
            memory.db.close()
    if operation.startswith("memory-"):
        # The bounded reader also rejects unsafe or oversized storage before the
        # existing core mutation opens it. No browser path reaches this boundary.
        read_memory_inventory(cfg.sessions_db, cfg.memory_file)
        for path in (cfg.memory_file, cfg.memory_file.with_suffix(".md.lock")):
            if path.is_symlink():
                return {"rejected": True}
        memory = Memory(cfg.memory_file, cfg.sessions_db)
        try:
            if operation == "memory-add":
                changed = memory.remember(_fact(request["fact"]))
            elif operation == "memory-auto":
                memory.set_auto_memory(request["enabled"],
                                       expected_enabled=request["expected_enabled"])
                changed = True
            else:
                if not re.fullmatch(r"[a-f0-9]{12}", request["id"]):
                    return {"rejected": True}
                changed = memory.update_fact(
                    request["id"], _fact(request["fact"]) if operation == "memory-edit" else None,
                )
            return {"ok": True} if changed else {"rejected": True}
        except ValueError:
            return {"rejected": True}
        finally:
            memory.db.close()
    # Discovery precedes the writer's witnessed effect gate. The same receipt
    # and registry fence are recoverable by the existing CLI recovery command.
    identity = request["request_id"]
    owner = "web-admin"
    if operation == "mcp-add":
        server = MCPServerConfig.from_dict(request["name"], {
            "transport": "http", "url": request["url"], "enabled": False,
        })
        mutation: Any = MCPAddDisabled(identity, owner, server.name, json.dumps(server.to_dict()))
    else:
        existing = MCPRegistry(cfg.mcp_servers_file).load().get(request["name"])
        if existing is None or definition_digest(existing) != request["fingerprint"]:
            return {"rejected": True}
        server = existing
        fields = (identity, owner, server.name, request["fingerprint"])
        if operation == "mcp-enable":
            if server.oauth:
                return {"rejected": True}
            try:
                tools = MCPClient(timeout_seconds=20, auth_dir=cfg.data_dir / "mcp-auth").discover(
                    server
                )
            except RuntimeError:
                return {"rejected": True}
            if not tools:
                return {"rejected": True}
            mutation = MCPEnable(*fields, json.dumps(tools))
        elif operation == "mcp-disable":
            mutation = MCPToggle(*fields, False)
        else:
            mutation = MCPRemove(*fields)
    result = apply_embedded_mcp_mutation(
        cfg.mcp_servers_file, mutation, auth_dir=cfg.data_dir / "mcp-auth",
        journal=OperationJournal(cfg.data_dir / "operations.db"),
        admitted=True,
    )
    if result.state == "saved":
        return {"ok": True}
    return {"rejected": True} if result.state == "rejected" else {"ok": False}
