import json
import queue
import threading
import uuid

import pytest
from klaude_application.mcp_mutations import (
    MCPAddVerified,
    MCPImportSnapshot,
    MCPOAuthEnable,
    MCPRemove,
    apply_embedded_mcp_mutation,
    finish_mcp_oauth_cleanup,
    recover_mcp_mutation,
)
from klaude_application.operation_journal import OperationJournal
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
from klaude_core.settings_store import settings_lock


def configured(tmp_path):
    path = tmp_path / "mcp.json"
    server = MCPServerConfig(
        name="docs",
        transport="http",
        url="https://example.com/mcp",
        enabled=False,
        tools=[{"name": "read", "inputSchema": {"type": "object"}}],
    )
    MCPRegistry(path).save({"docs": server})
    return path, server


def test_embedded_mcp_toggle_and_remove_use_shared_reviewed_effect(tmp_path):
    from klaude_application.mcp_mutations import MCPRemove

    path, server = configured(tmp_path)
    enabled = apply_embedded_mcp_mutation(
        path, MCPToggle(uuid.uuid4().hex, "cli", "docs", definition_digest(server), True)
    )
    assert enabled.state == "saved"
    current = MCPRegistry(path).load()["docs"]
    assert current.enabled
    removed = apply_embedded_mcp_mutation(
        path, MCPRemove(uuid.uuid4().hex, "cli", "docs", definition_digest(current))
    )
    assert removed.state == "saved" and MCPRegistry(path).load() == {}


def test_embedded_mcp_stale_review_rejects_without_write(tmp_path):
    path, server = configured(tmp_path)
    stale = definition_digest(server)
    registry = MCPRegistry(path)
    current = registry.load()
    current["docs"].url = "https://changed.example/mcp"
    registry.save(current)
    before = path.read_bytes()
    result = apply_embedded_mcp_mutation(
        path, MCPToggle(uuid.uuid4().hex, "cli", "docs", stale, True)
    )
    assert result.state == "rejected" and path.read_bytes() == before


def test_embedded_mcp_add_forces_disabled_and_preserves_existing(tmp_path):
    path, _server = configured(tmp_path)
    candidate = MCPServerConfig(
        name="new", transport="http", url="https://new.example/mcp", enabled=True,
        tools=[{"name": "untrusted", "inputSchema": {"type": "object"}}],
    )
    request = MCPAddDisabled(
        uuid.uuid4().hex, "cli", "new", json.dumps(candidate.to_dict())
    )
    result = apply_embedded_mcp_mutation(path, request)
    assert result.state == "saved"
    saved = MCPRegistry(path).load()
    assert set(saved) == {"docs", "new"}
    assert not saved["new"].enabled and saved["new"].tools == []
    assert apply_embedded_mcp_mutation(path, request).state == "rejected"


def test_embedded_mcp_verified_add_requires_discovered_tools(tmp_path):
    path, _server = configured(tmp_path)
    candidate = MCPServerConfig(
        name="new", transport="http", url="https://new.example/mcp", enabled=True,
    )
    request = MCPAddVerified(uuid.uuid4().hex, "cli", "new", json.dumps(candidate.to_dict()))
    assert apply_embedded_mcp_mutation(path, request).state == "rejected"
    assert "new" not in MCPRegistry(path).load()
    candidate.tools = [{"name": "read", "inputSchema": {"type": "object"}}]
    request = MCPAddVerified(uuid.uuid4().hex, "cli", "new", json.dumps(candidate.to_dict()))
    assert apply_embedded_mcp_mutation(path, request).state == "saved"
    assert MCPRegistry(path).load()["new"].enabled


def test_embedded_mcp_import_uses_reviewed_snapshot_and_strips_tools(tmp_path):
    path, _server = configured(tmp_path)
    candidate = MCPServerConfig(
        name="new", transport="http", url="https://new.example/mcp", enabled=True,
        tools=[{"name": "untrusted", "inputSchema": {"type": "object"}}],
    )
    request = MCPImportSnapshot(
        uuid.uuid4().hex, "cli", json.dumps({"new": candidate.to_dict()})
    )
    assert "new.example" not in repr(request)
    assert apply_embedded_mcp_mutation(path, request).state == "saved"
    saved = MCPRegistry(path).load()["new"]
    assert not saved.enabled and saved.tools == []
    assert apply_embedded_mcp_mutation(path, request).state == "rejected"


def test_embedded_mcp_oauth_enable_requires_persisted_access_token(tmp_path):
    path, server = configured(tmp_path)
    request = MCPOAuthEnable(
        uuid.uuid4().hex, "cli", "docs", definition_digest(server), "repo", "",
        json.dumps([{"name": "read", "inputSchema": {"type": "object"}}]),
    )
    before = path.read_bytes()
    assert apply_embedded_mcp_mutation(path, request, auth_dir=tmp_path / "auth").state == (
        "rejected"
    )
    assert path.read_bytes() == before


def test_journalled_mcp_save_deduplicates_and_releases_fence(tmp_path):
    path, server = configured(tmp_path)
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal
    )
    request = MCPToggle(uuid.uuid4().hex, "session", "docs", definition_digest(server), True)
    assert writer.submit(request)
    assert not writer.submit(request)
    assert writer.close(wait=True)
    assert events.get_nowait()[1].state == "saved"
    assert journal.status(request.identity, "session").state == "completed"
    assert MCPRegistry(path).load()["docs"].enabled
    assert b"https://example.com/mcp" not in journal.path.read_bytes()


def test_journalled_ambiguous_mcp_save_retains_resource_fence(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()
    original = MCPRegistry.save

    def save_then_fail(registry, servers, *, before_publish=None):
        original(registry, servers, before_publish=before_publish)
        raise OSError("private-value")

    monkeypatch.setattr(MCPRegistry, "save", save_then_fail)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal
    )
    request = MCPToggle(uuid.uuid4().hex, "session", "docs", definition_digest(server), True)
    assert writer.submit(request)
    assert not writer.close(wait=True)
    assert events.get_nowait()[1].state == "unconfirmed"
    assert journal.status(request.identity, "session").state == "unknown"
    assert MCPRegistry(path).load()["docs"].enabled
    second = MCPMutationWriter(path, lambda *_: None, lambda _: None, journal=journal)
    assert not second.submit(
        MCPToggle(
            uuid.uuid4().hex,
            "other",
            "docs",
            definition_digest(MCPRegistry(path).load()["docs"]),
            False,
        )
    )
    reload_events = queue.Queue()
    reload_writer = MCPMutationWriter(
        path, lambda *event: reload_events.put(event),
        lambda _: "verified-catalog", journal=journal,
    )
    assert reload_writer.submit(MCPReload(uuid.uuid4().hex, "session"))
    assert not reload_writer.close(wait=True)
    assert reload_events.get_nowait()[1].state == "loaded"
    assert journal.resource_busy(reload_writer._resource)
    recovered = OperationJournal(journal.path)
    receipt = recover_mcp_mutation(path, recovered, request.identity, "session")
    assert receipt.state == "completed" and receipt.outcome == "reconciled"
    assert not recovered.resource_busy(reload_writer._resource)


def test_mcp_recovery_identifies_no_effect_without_retry(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()

    def fail_before_save(_registry, _servers, *, before_publish=None):
        if before_publish is not None:
            before_publish()
        raise OSError("private-value")

    monkeypatch.setattr(MCPRegistry, "save", fail_before_save)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal
    )
    request = MCPToggle(uuid.uuid4().hex, "session", "docs", definition_digest(server), True)
    assert writer.submit(request)
    assert not writer.close(wait=True)
    assert events.get_nowait()[1].state == "unconfirmed"
    assert journal.status(request.identity, "session").state == "unknown"
    receipt = recover_mcp_mutation(path, OperationJournal(journal.path),
                                   request.identity, "session")
    assert receipt.state == "failed" and receipt.outcome == "reconciled"
    assert not MCPRegistry(path).load()["docs"].enabled


def test_mcp_recovery_keeps_changed_configuration_fenced(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()
    original = MCPRegistry.save

    def save_then_fail(registry, servers, *, before_publish=None):
        original(registry, servers, before_publish=before_publish)
        raise OSError("private-value")

    monkeypatch.setattr(MCPRegistry, "save", save_then_fail)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal
    )
    request = MCPToggle(uuid.uuid4().hex, "session", "docs", definition_digest(server), True)
    assert writer.submit(request)
    assert not writer.close(wait=True)
    assert events.get_nowait()[1].state == "unconfirmed"
    changed = MCPRegistry(path)
    definitions = changed.load()
    definitions["docs"].url = "https://different.example/mcp"
    original(changed, definitions)
    with pytest.raises(Exception, match="differs from both reviewed states"):
        recover_mcp_mutation(path, OperationJournal(journal.path), request.identity,
                             "session")
    assert journal.resource_busy(writer._resource)


def test_oauth_removal_requires_separate_credential_recovery(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import klaude_cli.main as cli_main
    from klaude_core.mcp_client import mcp_auth_file

    path, _server = configured(tmp_path)
    registry = MCPRegistry(path)
    definitions = registry.load()
    definitions["docs"].oauth = True
    registry.save(definitions)
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(mode=0o700)
    token_path = mcp_auth_file(auth_dir, "docs")
    token_path.write_text('{"tokens":{"access_token":"private-token"}}')
    token_path.chmod(0o600)
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()
    original = MCPRegistry.save

    def save_then_fail(registry, servers, *, before_publish=None):
        original(registry, servers, before_publish=before_publish)
        raise OSError("private-value")

    monkeypatch.setattr(MCPRegistry, "save", save_then_fail)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal,
        auth_dir=auth_dir,
    )
    request = MCPRemove(
        uuid.uuid4().hex, "session", "docs", definition_digest(definitions["docs"])
    )
    assert writer.submit(request)
    assert not writer.close(wait=True)
    assert events.get_nowait()[1].state == "unconfirmed"
    with pytest.raises(Exception, match="differs from both reviewed states"):
        recover_mcp_mutation(path, OperationJournal(journal.path), request.identity,
                             "session", auth_dir=auth_dir)
    assert journal.resource_busy(writer._resource)
    assert token_path.exists()
    with pytest.raises(Exception, match="credential is not present"):
        finish_mcp_oauth_cleanup(
            path, auth_dir, OperationJournal(journal.path), request.identity,
            "session", "other",
        )
    assert token_path.exists() and journal.resource_busy(writer._resource)
    monkeypatch.setattr(
        cli_main, "load_config",
        lambda: SimpleNamespace(
            data_dir=tmp_path, mcp_servers_file=path, mcp_auth_dir=auth_dir,
        ),
    )
    cli_main.mcp_recover_oauth("docs", yes=True)
    assert not token_path.exists() and not journal.resource_busy(writer._resource)


def test_oauth_removal_recovery_checks_definition_and_credentials(tmp_path, monkeypatch):
    from klaude_core.mcp_client import mcp_auth_file

    path, _server = configured(tmp_path)
    registry = MCPRegistry(path)
    definitions = registry.load()
    definitions["docs"].oauth = True
    registry.save(definitions)
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(mode=0o700)
    token_path = mcp_auth_file(auth_dir, "docs")
    token_path.write_text('{"tokens":{"access_token":"private-token"}}')
    token_path.chmod(0o600)
    now = [1000.0]
    journal = OperationJournal(tmp_path / "operations.db", clock=lambda: now[0])
    events = queue.Queue()

    def lose_ack(*_args, **_kwargs):
        raise OSError("ack lost")

    monkeypatch.setattr(journal, "finish", lose_ack)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal,
        auth_dir=auth_dir,
    )
    request = MCPRemove(
        uuid.uuid4().hex, "session", "docs", definition_digest(definitions["docs"])
    )
    assert writer.submit(request)
    assert not writer.close(wait=True)
    assert events.get_nowait()[1].state == "unconfirmed"
    assert MCPRegistry(path).load() == {} and not token_path.exists()
    assert b"private-token" not in journal.path.read_bytes()
    now[0] += 61
    recovered = OperationJournal(journal.path, clock=lambda: now[0])
    result = recover_mcp_mutation(
        path, recovered, request.identity, "session", auth_dir=auth_dir
    )
    assert result.state == "completed" and not recovered.resource_busy(writer._resource)


def test_journaled_oauth_cleanup_failure_stays_fenced(tmp_path, monkeypatch):
    from klaude_core.mcp_client import MCPTokenStorage, mcp_auth_file

    path, _server = configured(tmp_path)
    registry = MCPRegistry(path)
    definitions = registry.load()
    definitions["docs"].oauth = True
    registry.save(definitions)
    auth_dir = tmp_path / "auth"
    auth_dir.mkdir(mode=0o700)
    token_path = mcp_auth_file(auth_dir, "docs")
    token_path.write_text('{"tokens":{"access_token":"private-token"}}')
    token_path.chmod(0o600)
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()

    def failed_clear(_storage, *, before_clear=None):
        if before_clear is not None:
            before_clear()
        raise OSError("private-secret")

    monkeypatch.setattr(MCPTokenStorage, "clear", failed_clear)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None,
        auth_dir=auth_dir, journal=journal,
    )
    request = MCPRemove(
        uuid.uuid4().hex, "session", "docs", definition_digest(definitions["docs"])
    )
    assert writer.submit(request)
    assert not writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == "unconfirmed" and result.cleanup_failed
    assert journal.status(request.identity, "session").state == "unknown"
    assert journal.resource_busy(writer._resource)
    assert token_path.exists() and MCPRegistry(path).load() == {}


def test_journal_effect_gate_runs_inside_registry_lock(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    now = [1000.0]
    journal = OperationJournal(tmp_path / "operations.db", clock=lambda: now[0])
    events = queue.Queue()
    entered = threading.Event()
    original = MCPRegistry.save

    def signal_before_lock(registry, servers, *, before_publish=None):
        entered.set()
        return original(registry, servers, before_publish=before_publish)

    monkeypatch.setattr(MCPRegistry, "save", signal_before_lock)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal
    )
    request = MCPToggle(uuid.uuid4().hex, "session", "docs", definition_digest(server), True)
    with settings_lock(path):
        assert writer.submit(request)
        assert entered.wait(2)
        now[0] += 61
    assert not writer.close(wait=True)
    assert events.get_nowait()[1].state == "unconfirmed"
    assert journal.status(request.identity, "session").state == "unknown"
    assert not MCPRegistry(path).load()["docs"].enabled


def test_journal_rejects_unwitnessed_legacy_registry_merge(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    journal = OperationJournal(tmp_path / "operations.db")
    events = queue.Queue()
    original_save = MCPRegistry.save
    changed = False

    def change_other_definition_before_save(registry, servers, *, before_publish=None):
        nonlocal changed
        if not changed:
            changed = True
            legacy = MCPRegistry(path)
            current = legacy.load()
            current["other"] = MCPServerConfig(
                name="other", transport="http", url="https://other.example/mcp",
            )
            original_save(legacy, current)
        return original_save(registry, servers, before_publish=before_publish)

    monkeypatch.setattr(MCPRegistry, "save", change_other_definition_before_save)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal
    )
    request = MCPToggle(uuid.uuid4().hex, "session", "docs", definition_digest(server), True)
    assert writer.submit(request)
    assert writer.close(wait=True)
    assert events.get_nowait()[1].state == "rejected"
    assert journal.status(request.identity, "session").state == "failed"
    assert not journal.resource_busy(writer._resource)
    current = MCPRegistry(path).load()
    assert not current["docs"].enabled and "other" in current


def test_journalled_mcp_expired_before_start_rejects_without_unknown(tmp_path, monkeypatch):
    path, server = configured(tmp_path)
    now = [1000.0]
    journal = OperationJournal(tmp_path / "operations.db", clock=lambda: now[0])
    events = queue.Queue()
    original_load = MCPRegistry.load

    def load_after_expiry(registry):
        now[0] += 61
        return original_load(registry)

    monkeypatch.setattr(MCPRegistry, "load", load_after_expiry)
    writer = MCPMutationWriter(
        path, lambda *event: events.put(event), lambda _: None, journal=journal
    )
    request = MCPToggle(uuid.uuid4().hex, "session", "docs", definition_digest(server), True)
    assert writer.submit(request)
    assert writer.close(wait=True)
    assert events.get_nowait()[1].state == "rejected"
    assert journal.status(request.identity, "session").state == "cancelled"
    assert not journal.resource_busy(writer._resource)
    assert not original_load(MCPRegistry(path))["docs"].enabled


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
        definitions["bad"] = {
            "url": "https://example.com/mcp",
            "headers": {"Authorization": "Bearer private-token"},
        }
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
    source.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "one": {
                        "command": "never-execute",
                        "enabled": True,
                        "tools": [{"name": "untrusted", "inputSchema": {"type": "object"}}],
                    },
                    "two": {"url": "https://example.com/mcp", "enabled": True},
                }
            }
        )
    )
    events = queue.Queue()
    writer = MCPMutationWriter(path, lambda *event: events.put(event), lambda _: ([], None))
    assert writer.submit(MCPImport("import", "session", str(source)))
    assert writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == "saved" and result.count == 2
    servers = MCPRegistry(path).load()
    assert set(servers) == {"docs", "one", "two"}
    assert all(not servers[name].enabled and not servers[name].tools for name in ("one", "two"))


@pytest.mark.parametrize("changed", [False, True])
def test_remove_revalidates_definition_and_preserves_other_servers(tmp_path, changed):
    from klaude_cli.mcp_mutations import MCPRemove

    path, server = configured(tmp_path)
    fingerprint = definition_digest(server)
    registry = MCPRegistry(path)
    servers = registry.load()
    servers["other"] = MCPServerConfig(
        name="other", transport="http", url="https://other.example/mcp"
    )
    if changed:
        servers["docs"].url = "https://changed.example/mcp"
    registry.save(servers)
    events = queue.Queue()
    prepared = []
    writer = MCPMutationWriter(
        path,
        lambda *event: events.put(event),
        lambda values: prepared.append(set(values)) or ([], None),
    )
    assert writer.submit(MCPRemove("remove", "session", "docs", fingerprint))
    assert writer.close(wait=True)
    result = events.get_nowait()[1]
    assert result.state == ("rejected" if changed else "saved")
    remaining = MCPRegistry(path).load()
    assert "other" in remaining
    assert ("docs" in remaining) is changed
    assert prepared == ([] if changed else [{"other"}])


@pytest.mark.parametrize("cleanup_error", [False, True])
def test_remove_oauth_cleanup_is_scoped_and_failure_is_honest(tmp_path, monkeypatch, cleanup_error):
    from klaude_cli.mcp_mutations import MCPRemove
    from klaude_core.mcp_client import MCPTokenStorage, mcp_auth_file

    path, server = configured(tmp_path)
    server.oauth = True
    registry = MCPRegistry(path)
    registry.load()
    registry.save({"docs": server})
    cleared = []

    def clear(storage):
        cleared.append(storage.path)
        if cleanup_error:
            raise OSError("private-secret")

    monkeypatch.setattr(MCPTokenStorage, "clear", clear)
    auth_dir = tmp_path / "auth"
    writer = MCPMutationWriter(path, lambda *args: None, lambda _: ([], None), auth_dir=auth_dir)
    result = writer._apply(MCPRemove("remove", "session", "docs", definition_digest(server)))
    assert result.state == "saved"
    assert result.cleanup_failed is cleanup_error
    assert result.catalog == ([], None)
    assert cleared == [mcp_auth_file(auth_dir, "docs")]
    assert MCPRegistry(path).load() == {}
    assert "private-secret" not in repr(result)
