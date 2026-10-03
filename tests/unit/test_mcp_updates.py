"""MCP package updates must keep the reviewed definition's identity and scope."""

from klaude_cli.mcp_inventory import definition_digest
from klaude_cli.mcp_mutations import MCPMutationWriter, MCPUpdateDisabled
from klaude_cli.mcp_updates import package_update_candidate, valid_candidate_payload
from klaude_core.mcp_catalog import MCPCatalogServer
from klaude_core.mcp_client import MCPRegistry, MCPServerConfig


def _registry_server(version: str = "1.2.4", *, extra: str = "--safe") -> MCPCatalogServer:
    return MCPCatalogServer(
        "io.github.example/docs", "Docs", "Documentation MCP", version, "active",
        raw={"packages": [{"registryType": "npm", "identifier": "@example/docs",
                           "version": version, "runtimeHint": "npx",
                           "transport": {"type": "stdio"},
                           "packageArguments": [{"type": "positional", "value": extra}]}]},
    )


def _installed() -> MCPServerConfig:
    return MCPServerConfig(
        "docs", "stdio", True, command="npx",
        args=["--yes", "@example/docs@1.2.3", "--safe"],
        tools=[{"name": "search", "inputSchema": {"type": "object"}}],
        source={"registry": "official", "name": "io.github.example/docs",
                "version": "1.2.3", "description": "Old description"},
    )


def test_mcp_update_candidate_requires_only_one_newer_package_version():
    server = _installed()
    candidate = package_update_candidate(server, _registry_server())
    assert candidate is not None
    assert candidate.old_arg == "@example/docs@1.2.3"
    assert candidate.new_arg == "@example/docs@1.2.4"
    assert package_update_candidate(server, _registry_server("1.2.2")) is None
    assert package_update_candidate(server, _registry_server(extra="--changed")) is None
    server.source["registry"] = "import"
    assert package_update_candidate(server, _registry_server()) is None


def test_mcp_update_preview_rejects_mismatched_or_terminal_control_metadata():
    candidate = package_update_candidate(_installed(), _registry_server())
    assert candidate is not None
    payload = candidate.__dict__
    assert valid_candidate_payload(payload)
    assert not valid_candidate_payload({**payload, "new_version": "9.9.9"})
    assert not valid_candidate_payload({**payload, "description": "\x1b[31mhidden"})


def test_mcp_update_writer_rechecks_definition_and_disables_updated_server(tmp_path):
    registry = MCPRegistry(tmp_path / "mcp.json")
    server = _installed()
    registry.save({"docs": server})
    candidate = package_update_candidate(server, _registry_server())
    assert candidate is not None
    writer = MCPMutationWriter(registry.path, lambda *_: None,
                               lambda servers: (servers, None))
    fingerprint = definition_digest(server)
    request = MCPUpdateDisabled(
        "job", "session", "docs", fingerprint, candidate.old_arg,
        candidate.new_arg, candidate.registry_version, candidate.description,
    )
    changed = _installed()
    changed.args.append("--different")
    registry.save({"docs": changed})
    assert writer._apply(request).state == "rejected"
    assert registry.load()["docs"].args[-1] == "--different"
    registry.save({"docs": server})
    assert writer._apply(request).state == "saved"
    updated = registry.load()["docs"]
    assert updated.args == ["--yes", "@example/docs@1.2.4", "--safe"]
    assert not updated.enabled and not updated.tools
    assert updated.source["version"] == "1.2.4"
