"""Read-only bounded MCP metadata for navigation; no definitions cross IPC."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from klaude_core.mcp_client import MAX_MCP_CONFIG_FILE_BYTES, MCPRegistry, MCPServerConfig


def read_mcp_inventory(path: Path) -> dict[str, object]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return {"servers": [], "truncated": False}
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_MCP_CONFIG_FILE_BYTES:
            raise ValueError("MCP inventory requires bounded regular configuration")
        data = source.read(MAX_MCP_CONFIG_FILE_BYTES + 1)
        if len(data) > MAX_MCP_CONFIG_FILE_BYTES:
            raise ValueError("MCP configuration exceeds inventory limit")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("Invalid MCP configuration")
    raw = value.get("servers", value.get("mcpServers", {}))
    if not isinstance(raw, dict):
        raise ValueError("Invalid MCP server definitions")
    servers = []
    for name, definition in list(raw.items())[:1000]:
        if not isinstance(definition, dict):
            continue
        server = MCPServerConfig.from_dict(str(name), definition)
        servers.append({
            "name": server.name, "enabled": server.enabled, "transport": server.transport,
            "oauth": server.oauth, "tool_count": len(server.tools),
            "fingerprint": definition_digest(server),
        })
    return {"servers": servers, "truncated": len(raw) > 1000}


def definition_digest(server: MCPServerConfig) -> str:
    """Opaque identity for the complete reviewed definition, including cached tools."""
    return hashlib.sha256(json.dumps(
        server.to_dict(), sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def read_mcp_review(path: Path, name: str) -> dict[str, object]:
    server = MCPRegistry(path).load()[name]
    from urllib.parse import urlsplit

    if server.transport == "http":
        parsed = urlsplit(server.url)
        endpoint = f"{parsed.scheme}://{parsed.hostname}"
        if parsed.port:
            endpoint += f":{parsed.port}"
        endpoint += " (path/query hidden; review configuration for full endpoint)"
    else:
        endpoint = (
            "Local stdio command (arguments stay private; review configuration before enabling)"
        )
    return {
        "name": server.name, "enabled": server.enabled, "tool_count": len(server.tools),
        "oauth": server.oauth, "fingerprint": definition_digest(server), "endpoint": endpoint[:512],
    }
