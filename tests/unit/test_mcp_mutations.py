import json
import queue
import threading

import pytest
from klaude_cli.mcp_inventory import definition_digest
from klaude_cli.mcp_mutations import (
    MCPAddDisabled,
    MCPEnable,
    MCPImport,
    MCPMutationWriter,
    MCPReload,
    MCPToggle,
)
from klaude_core.mcp_client import MCPRegistry, MCPServerConfig


def configured(tmp_path):
    path = tmp_path / "mcp.json"
    server = MCPServerConfig(
        name="docs", transport="http", url="https://example.com/mcp", enabled=False,
        tools=[{"name": "read", "inputSchema": {"type": "object"}}],
    )
    MCPRegistry(path).save({"docs": server})
    return path, server


def test_mcp_mutations_are_ordered_and_close_drains_accepted_requests(tmp_path):
    path, server = configured(tmp_path)
    events = queue.Queue()
    entered, release = threading.Event(), threading.Event()

    def prepare(servers):
        if servers["docs"].enabled:
            entered.set()
            assert release.wait(2)
        return "private-prepared-catalog"

    writer = MCPMutationWriter(path, lambda *event: events.put(event), prepare)
    first = MCPToggle("first", "original", "docs", definition_digest(server), True)
    server.enabled = True
    second = MCPToggle("second", "other", "docs", definition_digest(server), False)
    try:
        assert writer.submit(first)
        assert entered.wait(2)
        assert writer.submit(second)
        assert not writer.close()  # accepted requests remain owned, not rolled back
        assert not writer.submit(second)
    finally:
        release.set()
    assert writer.close(wait=True)
    results = [events.get_nowait()[1] for _ in range(2)]
    assert [result.request for result in results] == [first, second]
    assert [result.state for result in results] == ["saved", "saved"]
    assert all(result.catalog == "private-prepared-catalog" for result in results)
    assert not MCPRegistry(path).load()["docs"].enabled


def test_mcp_mutation_rejects_stale_definition_without_saving(tmp_path):
    path, server = configured(tmp_path)
    events = queue.Queue()
    request = MCPToggle("one", "session", "docs", definition_digest(server), True)
    server.url = "https://changed.example/mcp"
    registry = MCPRegistry(path)
    registry.load()
    registry.save({"docs": server})
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: None)
    assert writer.submit(request)
    assert writer.close(wait=True)
    assert events.get_nowait()[1].state == "rejected"
    assert not MCPRegistry(path).load()["docs"].enabled


def test_mcp_mutation_failed_catalog_still_acknowledges_completed_save(tmp_path):
    path, server = configured(tmp_path)
    events = queue.Queue()

    def fail(_):
        raise RuntimeError("private-value-must-not-leak")

    writer = MCPMutationWriter(path, lambda *event: events.put(event), fail)
    assert writer.submit(MCPToggle("one", "session", "docs", definition_digest(server), True))
    assert writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == "saved" and result.catalog is None
    assert "private-value" not in repr(result)
    assert MCPRegistry(path).load()["docs"].enabled


def test_mcp_mutation_save_exception_is_unconfirmed_not_rolled_back(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    events = queue.Queue()
    original = MCPRegistry.save

    def save_then_fail(registry, servers):
        original(registry, servers)
        raise OSError("private-value")

    monkeypatch.setattr(MCPRegistry, "save", save_then_fail)
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: None)
    assert writer.submit(MCPToggle("one", "session", "docs", definition_digest(server), True))
    assert not writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == "unconfirmed" and "private-value" not in repr(result)
    assert MCPRegistry(path).load()["docs"].enabled


def test_mcp_mutation_backpressure_bounds_active_and_pending(tmp_path):
    path, server = configured(tmp_path)
    entered, release = threading.Event(), threading.Event()

    def prepare(_):
        entered.set()
        assert release.wait(2)

    writer = MCPMutationWriter(path, lambda *_: None, prepare)
    request = MCPToggle("one", "session", "docs", definition_digest(server), True)
    try:
        assert writer.submit(request)
        assert entered.wait(2)
        assert all(writer.submit(request) for _ in range(15))
        assert not writer.submit(request)
    finally:
        release.set()
    assert writer.close(wait=True)


def test_mcp_mutation_shutdown_is_bounded_and_does_not_abandon_accepted_save(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    entered, release = threading.Event(), threading.Event()
    events = queue.Queue()

    def prepare(_):
        entered.set()
        assert release.wait(2)

    writer = MCPMutationWriter(path, lambda *event: events.put(event), prepare)
    assert writer.submit(MCPToggle("one", "session", "docs", definition_digest(server), True))
    assert entered.wait(2)
    joins = []
    original = writer._thread.join
    monkeypatch.setattr(writer._thread, "join", joins.append)
    try:
        assert not writer.close(wait=True)
        assert joins == [2]
        assert MCPRegistry(path).load()["docs"].enabled
    finally:
        release.set()
        original(2)
    assert writer.close(wait=True)
    assert events.get_nowait()[1].state == "saved"


def test_mcp_discovery_snapshot_and_toggle_share_ordered_lane(tmp_path):
    path, server = configured(tmp_path)
    events = queue.Queue()
    tools = [{"name": "new", "inputSchema": {"type": "object"}}]
    enable = MCPEnable("enable", "session", "docs", definition_digest(server), json.dumps(tools))
    server.tools = tools
    server.enabled = True
    toggle = MCPToggle("disable", "session", "docs", definition_digest(server), False)
    tools[0]["name"] = "mutated-after-request"
    assert "mutated" not in repr(enable) and "inputSchema" not in repr(enable)
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: ([], None))
    assert writer.submit(enable) and writer.submit(toggle)
    assert writer.close(wait=True)
    assert [events.get_nowait()[1].state for _ in range(2)] == ["saved", "saved"]
    saved = MCPRegistry(path).load()["docs"]
    assert not saved.enabled and saved.tools[0]["name"] == "new"


@pytest.mark.parametrize("tools", ["not-json", "{}", '[{"name":"x"}]'])
def test_mcp_invalid_discovery_payload_never_enables_or_writes(tmp_path, tools):
    path, server = configured(tmp_path)
    before = path.read_bytes()
    events = queue.Queue()
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: ([], None))
    assert writer.submit(MCPEnable("enable", "session", "docs", definition_digest(server), tools))
    assert writer.close(wait=True)
    assert events.get_nowait()[1].state == "rejected"
    assert path.read_bytes() == before


def test_mcp_save_size_limit_keeps_existing_registry_readable(tmp_path, monkeypatch):
    import klaude_core.mcp_client as client

    path, _ = configured(tmp_path)
    before = path.read_bytes()
    monkeypatch.setattr(client, "MAX_MCP_CONFIG_FILE_BYTES", len(before) + 100)
    registry = MCPRegistry(path)
    servers = registry.load()
    servers["docs"].tools[0]["description"] = "x" * 1000
    with pytest.raises(ValueError, match="storage limit"):
        registry.save(servers)
    assert path.read_bytes() == before
    assert MCPRegistry(path).load()["docs"].tools[0].get("description") is None


def test_verified_reload_reconciles_uncertain_save_without_writing(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    events = queue.Queue()
    original = MCPRegistry.save

    def save_then_fail(registry, servers):
        original(registry, servers)
        raise OSError("late failure")

    monkeypatch.setattr(MCPRegistry, "save", save_then_fail)
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: ([], None))
    assert writer.submit(MCPToggle("one", "session", "docs", definition_digest(server), True))
    assert writer.submit(MCPReload("reload", "session"))
    assert writer.close(wait=True)
    assert [events.get_nowait()[1].state for _ in range(2)] == ["unconfirmed", "loaded"]
    assert MCPRegistry(path).load()["docs"].enabled


def test_reload_changed_during_preparation_never_publishes_stale_tools(tmp_path):
    path, _ = configured(tmp_path)
    events = queue.Queue()

    def prepare(_):
        registry = MCPRegistry(path)
        servers = registry.load()
        servers["docs"].url = "https://changed.example/mcp"
        registry.save(servers)
        return ([], None)

    writer = MCPMutationWriter(path, lambda *event: events.put(event), prepare)
    assert writer.submit(MCPReload("reload", "session"))
    assert writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == "rejected" and result.catalog is None


def test_add_forces_disabled_strips_tools_and_rejects_duplicates(tmp_path):
    path, server = configured(tmp_path)
    events = queue.Queue()
    server.enabled = True
    server.source = {"name": "test-registry-provenance"}
    request = MCPAddDisabled("add", "session", "new", json.dumps(server.to_dict()))
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: ([], None))
    assert writer.submit(request) and writer.submit(request)
    assert writer.close(wait=True)
    assert [events.get_nowait()[1].state for _ in range(2)] == ["saved", "rejected"]
    saved = MCPRegistry(path).load()["new"]
    assert not saved.enabled and saved.tools == []
    assert saved.source == server.source


@pytest.mark.parametrize("invalid", ["duplicate", "bad_entry", "missing_shape", "secret"])
def test_import_failure_is_atomic_and_does_not_disclose_source(tmp_path, invalid):
    path, _ = configured(tmp_path)
    before = path.read_bytes()
    source = tmp_path / "private-source.json"
    definitions = {"new": {"command": "never-execute", "enabled": True}}
    if invalid == "duplicate":
        definitions["docs"] = {"command": "never-execute"}
    elif invalid == "bad_entry":
        definitions["bad"] = "invalid"
    elif invalid == "secret":
        definitions["bad"] = {"url": "https://example.com/mcp",
                              "headers": {"Authorization": "Bearer private-token"}}
    source.write_text(json.dumps({} if invalid == "missing_shape" else {"servers": definitions}))
    events = queue.Queue()
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: ([], None))
    request = MCPImport("import", "session", str(source))
    assert "private-source" not in repr(request)
    assert writer.submit(request) and writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == "rejected"
    assert "private-token" not in repr(result)
    assert path.read_bytes() == before


def test_import_saves_all_valid_entries_disabled_without_cached_tools(tmp_path):
    path, _ = configured(tmp_path)
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"mcpServers": {
        "one": {"command": "never-execute", "enabled": True,
                "tools": [{"name": "untrusted", "inputSchema": {"type": "object"}}]},
        "two": {"url": "https://example.com/mcp", "enabled": True},
    }}))
    events = queue.Queue()
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: ([], None))
    assert writer.submit(MCPImport("import", "session", str(source)))
    assert writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == "saved" and result.count == 2
    servers = MCPRegistry(path).load()
    assert set(servers) == {"docs", "one", "two"}
    assert all(not servers[name].enabled and not servers[name].tools for name in ("one", "two"))
