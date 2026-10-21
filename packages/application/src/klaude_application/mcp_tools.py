"""Cached external MCP tool construction shared by terminal and browser agents."""

from __future__ import annotations

import json

from klaude_core import Tool
from klaude_core.mcp_client import MCPServerConfig


def configured_mcp_tools(
    cfg, *, servers: dict[str, MCPServerConfig] | None = None, strict: bool = False,
    recheck_definition: bool = False,
) -> list[Tool]:
    """Load cached external MCP schemas without connecting during TUI startup."""
    from klaude_core.mcp_client import (
        MCPClientManager,
        MCPRegistry,
        namespaced_tool_name,
    )

    if servers is None:
        registry = MCPRegistry(cfg.mcp_servers_file)
        try:
            servers = registry.load()
        except ValueError:
            if strict:
                raise
            return []
    if not any(server.enabled and server.tools for server in servers.values()):
        return []
    client = getattr(cfg, "_mcp_client_manager", None)
    if client is None:
        auth_dir = getattr(cfg, "mcp_auth_dir", cfg.mcp_servers_file.parent / "mcp-auth")
        client = MCPClientManager(auth_dir=auth_dir)
        cfg._mcp_client_manager = client

    def make_invoke(server, remote_name: str):
        def invoke(**arguments):
            # A review can outlive a definition reload. Never execute a stale
            # captured command or endpoint after the reviewed definition changed.
            if recheck_definition:
                current = MCPRegistry(cfg.mcp_servers_file).load().get(server.name)
                if current is None or current.to_dict() != server.to_dict() or not current.enabled:
                    raise ValueError("MCP connection changed; reload and review the tool again")
            response = client.call(server, remote_name, arguments)
            failed = response.get("is_error") is True
            return {"content": json.dumps(response, ensure_ascii=False), "metadata": {
                "is_error": failed, "status": "failed" if failed else "succeeded",
                "mcp_server": server.name, "mcp_tool": remote_name,
            }}

        return invoke

    def make_detail(server_name: str, remote_name: str):
        return lambda args: (
            f"{server_name}.{remote_name} " + json.dumps(args, ensure_ascii=False)[:160]
        )

    result: list[Tool] = []
    used_names: set[str] = set()
    for server in servers.values():
        if not server.enabled:
            continue
        for remote in server.tools:
            remote_name = str(remote.get("name") or "")
            if not remote_name:
                continue
            local_name = namespaced_tool_name(server.name, remote_name)
            if local_name in used_names:
                continue
            used_names.add(local_name)
            schema = remote.get("inputSchema")
            parameters = (
                dict(schema)
                if isinstance(schema, dict)
                else {"type": "object", "properties": {}}
            )

            result.append(
                Tool(
                    local_name,
                    f"MCP server {server.name}: {str(remote.get('description') or remote_name)}",
                    parameters,
                    make_invoke(server, remote_name),
                    detail=make_detail(server.name, remote_name),
                )
            )
    return result
