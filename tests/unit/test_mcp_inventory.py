import json
import os

import pytest
from klaude_cli.mcp_inventory import read_mcp_inventory
from klaude_core.mcp_client import MAX_MCP_CONFIG_FILE_BYTES


def test_mcp_inventory_returns_metadata_only_without_connecting(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"browser": {
        "transport": "stdio", "command": "never-execute-this",
        "args": ["secret-argument"],
        "env": {"TOKEN": "${env:PRIVATE_TOKEN}", "PUBLIC_VALUE": "private-value"},
        "enabled": False,
    }}}))
    before = path.read_bytes()
    result = read_mcp_inventory(path)
    fingerprint = result["servers"][0].pop("fingerprint")
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    assert "private-value" not in json.dumps(result)
    assert result == {"servers": [{
        "name": "browser", "enabled": False, "transport": "stdio",
        "oauth": False, "tool_count": 0,
        "source_label": "Local configuration", "description": "", "update_kind": "",
    }], "truncated": False}
    assert path.read_bytes() == before


@pytest.mark.parametrize("unsafe", ["symlink", "oversized", "fifo", "malformed"])
def test_mcp_inventory_rejects_unsafe_configuration(tmp_path, unsafe):
    path = tmp_path / "mcp.json"
    if unsafe == "symlink":
        target = tmp_path / "target"
        target.write_text("{}")
        path.symlink_to(target)
    elif unsafe == "oversized":
        with path.open("wb") as stream:
            stream.truncate(MAX_MCP_CONFIG_FILE_BYTES + 1)
    elif unsafe == "fifo":
        os.mkfifo(path)
    else:
        path.write_text("not json")
    with pytest.raises((ValueError, OSError)):
        read_mcp_inventory(path)


def test_missing_mcp_config_is_not_created_and_large_inventory_is_explicit(tmp_path):
    path = tmp_path / "mcp.json"
    assert read_mcp_inventory(path) == {"servers": [], "truncated": False}
    assert not path.exists()
    path.write_text(json.dumps({"servers": {
        f"server-{i}": {"command": "never-execute", "enabled": False} for i in range(1001)
    }}))
    result = read_mcp_inventory(path)
    assert len(result["servers"]) == 1000 and result["truncated"] is True


def test_review_fingerprint_binds_private_definition_without_disclosing_it(tmp_path):
    from klaude_cli.mcp_inventory import definition_digest, read_mcp_review
    from klaude_core.mcp_client import MCPRegistry

    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"browser": {
        "command": "never-execute", "args": ["private-argument"], "enabled": False,
        "env": {"TOKEN": "${env:PRIVATE_TOKEN}"},
    }}}))
    review = read_mcp_review(path, "browser")
    server = MCPRegistry(path).load()["browser"]
    assert review["fingerprint"] == definition_digest(server)
    assert "private-argument" not in json.dumps(review)
    assert "PRIVATE_TOKEN" not in json.dumps(review)
    server.args.append("changed")
    assert review["fingerprint"] != definition_digest(server)


def test_review_http_endpoint_hides_path_and_query(tmp_path):
    from klaude_cli.mcp_inventory import read_mcp_review

    path = tmp_path / "mcp.json"
    path.write_text(json.dumps({"servers": {"docs": {
        "url": "https://example.com/private-path?tenant=private-tenant", "enabled": False,
    }}}))
    review = read_mcp_review(path, "docs")
    assert str(review["endpoint"]).startswith("https://example.com")
    assert "private-path" not in json.dumps(review) and "private-tenant" not in json.dumps(review)


def test_normal_registry_read_rejects_fifo_without_waiting(tmp_path):
    from klaude_core.mcp_client import MCPRegistry

    path = tmp_path / "mcp.json"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular file"):
        MCPRegistry(path).load()
