"""Browser profile controls use real shared stores and owned worker effects."""

import json
import sys
import threading
import uuid

import pytest
from klaude_application.library_management import LibraryManagement
from klaude_core.config import Config
from klaude_core.mcp_client import MCPRegistry, MCPServerConfig
from klaude_core.memory import Memory
from klaude_tools import Workspace
from klaude_webhost.host import LocalWebHost

from .test_image_generation import generation_lab as generation_lab
from .test_library_management import _wait
from .test_webhost import _app, _request


@pytest.fixture
def profile_browser(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config()
    memory = Memory(cfg.memory_file, cfg.sessions_db)
    service = LibraryManagement(cfg, tmp_path)
    app = _app(cfg.data_dir)
    app.agent.workdir, app.agent.workspace = tmp_path, Workspace(tmp_path)
    app.agent.tool_config = cfg
    app.turns.bind_workspace(app.session_id, str(tmp_path), expected_revision=0)
    host = LocalWebHost(app, library=service)
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        _, headers, login = _request(host, "POST", "/api/v1/auth/exchange",
                                     body={"code": host.bootstrap_url.partition("#")[2]},
                                     origin=host.origin)
        auth = {"cookie": headers["Set-Cookie"].split(";", 1)[0],
                "csrf": login["csrf"], "origin": host.origin}
        _, _, client = _request(host, "POST", "/api/v1/clients", body={}, **auth)
        auth["client_id"] = client["client_id"]
        yield host, service, memory, auth
    finally:
        host.stop()
        thread.join(timeout=3)
        memory.db.close()


def _review(host, auth, draft):
    status, _, review = _request(host, "POST", "/api/v1/library/review",
                                 body={"draft": draft}, **auth)
    assert status == 200, review
    return review


def _submit(host, service, auth, review, identity=None):
    identity = identity or uuid.uuid4().hex
    body = {"review_id": review["review_id"], "request_id": identity, "control_epoch": 0}
    status, _, receipt = _request(host, "POST", "/api/v1/library/submit", body=body, **auth)
    assert status == 202, receipt
    return _wait(service, identity), body


@pytest.mark.parametrize("password", [False, True])
def test_lan_mcp_management_requires_owner_password_and_exact_review(profile_browser, password):
    from klaude_webhost.accounts import AccountStore

    host, service, _, auth = profile_browser
    if password:
        accounts = AccountStore(service.cfg.config_dir)
        accounts.initialize()
        host.accounts = accounts
        status, headers, login = _request(host, "POST", "/api/v1/auth/login", body={
            "username": "admin", "password": accounts.initial_password(),
        }, origin=host.origin)
        assert status == 200
        auth = {"cookie": headers["Set-Cookie"].split(";", 1)[0],
                "csrf": login["csrf"], "origin": host.origin}
        client = _request(host, "POST", "/api/v1/clients", body={}, **auth)[2]
        auth["client_id"] = client["client_id"]
    draft = {"operation": "mcp-add", "name": "remote-fixture",
             "url": "https://example.test/mcp"}
    # A review prepared locally must still recheck LAN authorization at submit.
    local = _review(host, auth, draft)
    host.http.host_lan = True
    route = "/api/v1/integrations/connections"
    assert _request(host, "GET", route, **auth)[2]["management_allowed"] is password
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft},
                    origin=host.origin)[0] == 401
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft},
                    **{**auth, "origin": "http://attacker.test"})[0] == 403
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft},
                    **{**auth, "csrf": "wrong"})[0] == 403
    submitted = {"review_id": local["review_id"], "request_id": uuid.uuid4().hex,
                 "control_epoch": 0}
    if not password:
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft},
                        **auth)[0] == 403
        assert _request(host, "POST", "/api/v1/library/submit", body=submitted,
                        **auth)[0] == 403
        assert not MCPRegistry(service.cfg.mcp_servers_file).load()
        return

    review = _review(host, auth, draft)
    assert not MCPRegistry(service.cfg.mcp_servers_file).load()
    assert _request(host, "POST", "/api/v1/library/discard",
                    body={"review_id": review["review_id"]}, **auth)[0] == 200
    assert not MCPRegistry(service.cfg.mcp_servers_file).load()
    assert _submit(host, service, auth, local)[0]["state"] == "completed"
    assert not MCPRegistry(service.cfg.mcp_servers_file).load()["remote-fixture"].enabled

    program = service.workspace / "mcp-fixture.py"
    program.write_text('''import json, sys
for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    if message.get("method") == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "fixture", "version": "1"}}
    elif message.get("method") == "tools/list":
        result = {"tools": [{"name": "inspect", "inputSchema": {"type": "object"}}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
''')
    registry = MCPRegistry(service.cfg.mcp_servers_file)
    servers = registry.load()
    servers["local-fixture"] = MCPServerConfig(
        "local-fixture", "stdio", False, command=sys.executable, args=[str(program)],
    )
    registry.save(servers)

    def prepare(operation):
        item = next(item for item in _request(host, "GET", route, **auth)[2]["servers"]
                    if item["name"] == "local-fixture")
        return _review(host, auth, {"operation": operation, "name": item["name"],
                                   "fingerprint": item["fingerprint"]})

    review = prepare("mcp-enable")
    assert "launches its configured program" in review["summary"]
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert registry.load()["local-fixture"].enabled
    assert registry.load()["local-fixture"].tools[0]["name"] == "inspect"
    review = prepare("mcp-disable")
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert not registry.load()["local-fixture"].enabled
    review = prepare("mcp-remove")
    servers = registry.load()
    servers["local-fixture"].source["description"] = "Changed after review"
    registry.save(servers)
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert "local-fixture" in registry.load()
    assert _submit(host, service, auth, prepare("mcp-remove"))[0]["state"] == "completed"
    assert "local-fixture" not in registry.load()


def test_profile_inventory_is_authenticated_bounded_and_private(profile_browser):
    host, service, memory, auth = profile_browser
    memory.remember("Use small readable functions")
    # Existing sensitive records must remain private even if an old writer saved them.
    memory.memory_file.write_text(memory.memory_file.read_text() + "- api_key=sk-private-value\n")
    registry = MCPRegistry(service.cfg.mcp_servers_file)
    registry.save({"fixture": MCPServerConfig(
        "fixture", "http", False, url="https://example.test/mcp",
        headers={"Authorization": "Bearer ${env:FIXTURE_TOKEN}"},
    )})
    for route in ("/api/v1/settings/memory", "/api/v1/integrations/connections"):
        assert _request(host, "GET", route)[0] == 401
        assert _request(host, "GET", route, fetch_site="cross-site", **auth)[0] == 403
        status, _, result = _request(host, "GET", route, **auth)
        assert status == 200
        assert "sk-private-value" not in json.dumps(result)
        assert "FIXTURE_TOKEN" not in json.dumps(result)
        assert _request(host, "GET", route + "?unknown=1", **auth)[0] == 400
    result = _request(host, "GET", "/api/v1/settings/memory", **auth)[2]
    assert result["hidden"] == 1 and len(result["entries"]) == 1
    assert not (service.data / "knowledge.lance").exists()


def test_memory_review_edit_delete_auto_and_deduplication(profile_browser):
    host, service, memory, auth = profile_browser
    review = _review(host, auth, {"operation": "memory-add", "fact": "Prefer concise replies"})
    assert not memory.search_facts("concise")
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert len(memory.search_facts("concise")) == 1
    entry = memory.search_facts("concise")[0]
    stale = _review(host, auth, {"operation": "memory-edit", "id": entry.id,
                                "fact": "Prefer detailed replies"})
    assert memory.update_fact(entry.id, "Prefer short replies")
    assert _submit(host, service, auth, stale)[0]["state"] == "failed"
    entry = memory.search_facts("short")[0]
    review = _review(host, auth, {"operation": "memory-delete", "id": entry.id})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert not memory.search_facts("short")
    review = _review(host, auth, {"operation": "memory-auto", "enabled": False,
                                "expected_enabled": True})
    assert memory.auto_memory_enabled()
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert not memory.auto_memory_enabled()


def test_profile_rejects_secret_unknown_field_stale_setting_and_csrf(profile_browser):
    host, service, memory, auth = profile_browser
    for draft in ({"operation": "memory-add", "fact": "api_key=sk-private-secret"},
                  {"operation": "memory-add", "fact": "Useful fact", "path": "/tmp/escape"},
                  {"operation": "memory-auto", "enabled": False, "expected_enabled": False}):
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft},
                        **auth)[0] == 400
    assert _request(host, "POST", "/api/v1/library/review",
                    body={"draft": {"operation": "memory-add", "fact": "Useful fact"}},
                    **{**auth, "csrf": ""})[0] == 403
    review = _review(host, auth, {"operation": "memory-auto", "enabled": False,
                                "expected_enabled": True})
    memory.set_auto_memory(False)
    assert _submit(host, service, auth, review)[0]["state"] == "failed"


def test_connections_add_disabled_disable_remove_and_stale_review(profile_browser):
    host, service, _, auth = profile_browser
    route = "/api/v1/integrations/connections"
    review = _review(host, auth, {"operation": "mcp-add", "name": "fixture",
                                "url": "https://example.test/mcp"})
    assert _request(host, "GET", route, **auth)[2]["servers"] == []

    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    server = _request(host, "GET", route, **auth)[2]["servers"][0]
    assert server["enabled"] is False
    registry = MCPRegistry(service.cfg.mcp_servers_file)
    values = registry.load()
    values["fixture"].enabled = True
    values["fixture"].tools = [{"name": "read", "inputSchema": {"type": "object"}}]
    registry.save(values)
    server = _request(host, "GET", route, **auth)[2]["servers"][0]
    draft = {"operation": "mcp-disable", "name": server["name"],
             "fingerprint": server["fingerprint"]}
    review = _review(host, auth, draft)
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    server = _request(host, "GET", route, **auth)[2]["servers"][0]
    stale = _review(host, auth, {"operation": "mcp-remove", "name": server["name"],
                               "fingerprint": server["fingerprint"]})
    registry = MCPRegistry(service.cfg.mcp_servers_file)
    values = registry.load()
    values["fixture"].url = "https://changed.test/mcp"
    registry.save(values)
    assert _submit(host, service, auth, stale)[0]["state"] == "failed"
    server = _request(host, "GET", route, **auth)[2]["servers"][0]
    review = _review(host, auth, {"operation": "mcp-remove", "name": server["name"],
                                "fingerprint": server["fingerprint"]})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert _request(host, "GET", route, **auth)[2]["servers"] == []


def test_session_management_is_workspace_scoped_and_deletion_rechecks_history(profile_browser):
    from .test_web_library import _bytes_request

    host, service, memory, auth = profile_browser
    app = host.application
    identity = uuid.uuid4().hex
    app.turns.bind_workspace(identity, str(service.workspace), expected_revision=0)
    memory.log_turn(identity, "user", "Public question", model_content="PRIVATE MODEL INPUT")
    memory.log_turn(identity, "assistant", "Public answer")
    memory.log_turn(identity, "tool", "PRIVATE TOOL OUTPUT")
    items = _request(host, "GET", "/api/v1/sessions", **auth)[2]["sessions"]
    assert any(item["session_id"] == identity for item in items)
    status, headers, content = _bytes_request(host, f"/api/v1/sessions/export?id={identity}",
                                             auth["cookie"])
    assert status == 200 and "attachment" in headers["Content-Disposition"]
    assert b"Public question" in content and b"Public answer" in content
    assert b"PRIVATE" not in content
    review = _review(host, auth, {"operation": "session-rename", "target": identity,
                                 "name": "Project notes"})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert memory.session_title(identity) == "Project notes"
    review = _review(host, auth, {"operation": "session-archive", "target": identity})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert memory.session_archived(identity)
    items = _request(host, "GET", "/api/v1/sessions?archived=true", **auth)[2]["sessions"]
    assert any(item["session_id"] == identity and item["archived"] for item in items)
    review = _review(host, auth, {"operation": "session-delete", "target": identity})
    memory.log_turn(identity, "assistant", "Arrived after review")
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert memory.load_session(identity)
    review = _review(host, auth, {"operation": "session-restore", "target": identity})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert not memory.session_archived(identity)
    review = _review(host, auth, {"operation": "session-archive", "target": identity})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    review = _review(host, auth, {"operation": "session-delete", "target": identity})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert not memory.load_session(identity)


def test_session_management_rejects_other_workspaces_and_stale_names(profile_browser):
    host, service, memory, auth = profile_browser
    identity = uuid.uuid4().hex
    memory.log_turn(identity, "user", "Other workspace")
    host.application.turns.bind_workspace(identity, str(service.workspace / "other"),
                                         expected_revision=0)
    draft = {"operation": "session-rename", "target": identity, "name": "Changed"}
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft}, **auth)[0] == 400
    assert _request(host, "GET", f"/api/v1/sessions/export?id={identity}", **auth)[0] == 400
    identity = uuid.uuid4().hex
    memory.log_turn(identity, "user", "Original name")
    host.application.turns.bind_workspace(identity, str(service.workspace), expected_revision=0)
    review = _review(host, auth, {**draft, "target": identity})
    memory.rename_session(identity, "Named elsewhere")
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert memory.session_title(identity) == "Named elsewhere"


@pytest.mark.parametrize("current", [False, True])
def test_saved_conversation_can_be_deleted_without_archiving(profile_browser, current):
    host, service, memory, auth = profile_browser
    identity = host.application.session_id if current else uuid.uuid4().hex
    if not current:
        host.application.turns.bind_workspace(identity, str(service.workspace), expected_revision=0)
    memory.log_turn(identity, "user", "Delete this saved conversation")
    assert not memory.session_archived(identity)
    review = _review(host, auth, {"operation": "session-delete", "target": identity})
    assert "cannot be undone" in review["summary"]
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert not memory.load_session(identity)
    selected = host.application.session_id
    if current:
        assert selected != identity
        assert host.application.snapshot()["messages"] == []
    status, _, replay = _request(host, "POST", "/api/v1/library/submit", body=body, **auth)
    assert status == 202 and replay["session_id"] == selected
    assert host.application.session_id == selected


def test_saved_conversation_deletion_rechecks_archive_state(profile_browser):
    host, service, memory, auth = profile_browser
    identity = uuid.uuid4().hex
    host.application.turns.bind_workspace(identity, str(service.workspace), expected_revision=0)
    memory.log_turn(identity, "user", "Keep if the reviewed state changes")
    review = _review(host, auth, {"operation": "session-delete", "target": identity})
    memory.change_session_archive(identity, "archive")
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert memory.load_session(identity)


def test_archiving_current_conversation_opens_one_new_chat_and_keeps_history(profile_browser):
    host, service, memory, auth = profile_browser
    original = host.application.session_id
    memory.log_turn(original, "user", "Keep this history")
    memory.log_turn(original, "assistant", "Saved answer")
    host.application.agent.restore_session(memory.load_session(original))
    review = _review(host, auth, {"operation": "session-archive", "target": original})
    assert "new chat" in review["summary"]
    assert host.application.session_id == original
    assert not memory.session_archived(original)
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    selected = host.application.session_id
    assert selected != original
    assert memory.session_archived(original)
    assert [turn["content"] for turn in memory.load_session(original)] == [
        "Keep this history", "Saved answer",
    ]
    assert not memory.load_session(selected)
    assert host.application.snapshot()["messages"] == []
    assert host.application.turns.workspace(selected)[0] == str(service.workspace)
    assert not host.application.agent.workspace.write_enabled
    status, _, replay = _request(host, "POST", "/api/v1/library/submit", body=body, **auth)
    assert status == 202 and replay["session_id"] == selected
    assert host.application.session_id == selected
    assert _request(host, "GET", "/api/v1/sessions", **auth)[2]["sessions"] == []
    archived = _request(host, "GET", "/api/v1/sessions?archived=true", **auth)[2]["sessions"]
    assert archived[0]["session_id"] == original


def test_current_archive_waits_for_work_and_does_not_switch_on_invalid_admission(
    profile_browser, monkeypatch,
):
    host, service, memory, auth = profile_browser
    original = host.application.session_id
    memory.log_turn(original, "user", "Wait for this conversation")
    review = _review(host, auth, {"operation": "session-archive", "target": original})
    body = {"review_id": review["review_id"], "request_id": uuid.uuid4().hex,
            "control_epoch": 0}
    snapshot = host.application.snapshot
    for pending in ({"active_turn_id": "working"}, {"queue": [{"state": "accepted"}]}):
        monkeypatch.setattr(host.application, "snapshot", lambda pending=pending: {
            **snapshot(), **pending,
        })
        assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 409
        assert host.application.session_id == original
        assert not memory.session_archived(original)
    monkeypatch.setattr(host.application, "snapshot", snapshot)
    invalid = {**body, "review_id": "expired"}
    assert _request(host, "POST", "/api/v1/library/submit", body=invalid, **auth)[0] == 400
    assert host.application.session_id == original
    # A conflicting resource is rejected before a new chat is created.
    service.journal.admit(request_id=uuid.uuid4().hex, owner_id="other", kind="session-archive",
                          resource=f"session:{original}", payload={})
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 409
    assert host.application.session_id == original
    assert not memory.session_archived(original)


def test_current_archive_does_not_run_if_new_chat_cannot_start(profile_browser, monkeypatch):
    host, service, memory, auth = profile_browser
    original = host.application.session_id
    memory.log_turn(original, "user", "Keep me available")
    review = _review(host, auth, {"operation": "session-archive", "target": original})
    body = {"review_id": review["review_id"], "request_id": uuid.uuid4().hex,
            "control_epoch": 0}

    def unavailable(**_kwargs):
        raise ValueError("Startup model is unavailable")

    monkeypatch.setattr(host.application, "start_session", unavailable)
    status, _, error = _request(host, "POST", "/api/v1/library/submit", body=body, **auth)
    assert status == 400 and "Startup model" in error["error"]["message"]
    assert host.application.session_id == original and not memory.session_archived(original)
    assert service.status(body["request_id"])["state"] == "failed"
    assert not service.session_busy(original)
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert not memory.session_archived(original)


def test_archive_review_does_not_replace_a_chat_selected_before_confirmation(profile_browser):
    host, service, memory, auth = profile_browser
    original = host.application.session_id
    memory.log_turn(original, "user", "Archive this one")
    review = _review(host, auth, {"operation": "session-archive", "target": original})
    status, _, choice = _request(host, "POST", "/api/v1/session/select", body={
        "request_id": uuid.uuid4().hex, "expected_session_id": original,
        "session_id": "", "control_epoch": 0,
    }, **auth)
    assert status == 200
    selected = choice["session_id"]
    assert selected != original
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert host.application.session_id == selected
    assert memory.session_archived(original)


def test_configured_provider_selection_effort_and_stale_revision(profile_browser, monkeypatch):
    import asyncio

    from klaude_application.browser_models import BrowserModels
    from klaude_core.model_connections import ModelConnection, connection_registry
    from klaude_core.model_runtime import ModelCapabilities, ModelInfo

    from .test_application_bridge import ScriptedRuntime

    host, service, memory, auth = profile_browser
    app = host.application
    connection = ModelConnection("fixture", "Fixture endpoint", "openai_compatible",
                                 "http://127.0.0.1:8089/v1")
    connection_registry(service.cfg).add(connection)
    info = ModelInfo("openai_compatible", "fixture-model", "Fixture model", ModelCapabilities(
        effort_levels=("off", "low", "medium", "high"), thinking_types=("disabled", "enabled"),
    ), connection_id=connection.id, connection_revision=connection.revision,
        connection_source=connection.source)
    monkeypatch.setattr("klaude_application.browser_models.discover_connection",
                        lambda *_args: [info])
    runtimes = []

    def runtime(_self, _info):
        result = ScriptedRuntime([{"role": "assistant", "content": "Provider fixture ready."}])
        result.backend = "openai_compatible"
        runtimes.append(result)
        return result

    monkeypatch.setattr(BrowserModels, "runtime", runtime)
    app.agent.browser_models = BrowserModels(service.cfg)
    inventory = _request(host, "GET", "/api/v1/models/connections", **auth)[2]
    assert inventory["connections"][0]["id"] == connection.id
    catalog = _request(host, "GET", "/api/v1/models/catalog?connection=fixture", **auth)[2]
    assert catalog["models"][0]["id"] == info.ref
    snapshot = _request(host, "GET", "/api/v1/session", **auth)[2]
    assert snapshot["model_providers"]
    body = {"request_id": uuid.uuid4().hex, "model_ref": info.ref,
            "expected_revision": snapshot["settings_revision"], "control_epoch": 0}
    status, _, result = _request(
        host, "POST", "/api/v1/session/configured-model", body=body, **auth,
    )
    assert status == 200, result
    assert app.agent.runtime.backend == "openai_compatible"
    assert app.agent.model_info.ref == info.ref
    assert app.agent.reasoning_mode == "standard"
    assert not (service.data / "chat-preferences.json").exists()
    mode = {"request_id": uuid.uuid4().hex, "mode": "thinking", "effort": "high",
            "expected_revision": result["revision"], "control_epoch": 0}
    status, _, result = _request(host, "POST", "/api/v1/session/mode", body=mode, **auth)
    assert status == 200, result
    assert app.agent.reasoning_effort == "high"
    # An old revision cannot replace the newly selected mode or transport.
    old_runtime = app.agent.runtime
    assert _request(host, "POST", "/api/v1/session/configured-model",
                    body={**body, "request_id": uuid.uuid4().hex}, **auth)[0] == 409
    assert app.agent.runtime is old_runtime and runtimes[-1].closed
    assert memory.session_runtime(app.session_id)["effort"] == "high"

    async def exercise():
        handle = app.submit("Say ready", request_id=uuid.uuid4().hex)
        await handle.result()
        assert handle.state == "completed"

    asyncio.run(exercise())
    assert "Provider fixture ready." in repr(memory.load_session(app.session_id))
    saved_session = app.session_id
    app.start_session()
    app.resume_configured(saved_session)
    assert app.session_id == saved_session and app.agent.reasoning_effort == "high"


def test_agent_settings_use_field_cas_and_preserve_unrelated_preferences(profile_browser):
    from klaude_core.settings_store import read_settings, update_settings

    host, service, _, auth = profile_browser
    path = service.data / "chat-preferences.json"
    fields = _request(host, "GET", "/api/v1/settings/agent", **auth)[2]["fields"]
    field = next(item for item in fields if item["id"] == "runtime_options.max_steps")
    review = _review(host, auth, {"operation": "setting-save", "id": field["id"],
                                 "value": 7, "revision": field["revision"]})
    update_settings(path, {("runtime_options", "num_ctx"): 4096,
                           ("display", "activity_updates"): False})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    saved = read_settings(path)
    assert saved["runtime_options"] == {"num_ctx": 4096, "max_steps": 7}
    assert saved["display"]["activity_updates"] is False
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
        "operation": "setting-save", "id": field["id"], "value": 8,
        "revision": field["revision"],
    }}, **auth)[0] == 400
    for identity, value in (("runtime_options.max_steps", 65),
                            ("runtime_options.max_steps", True),
                            ("permissions.run_shell", "allow"),
                            ("tool_availability.web_search", "true")):
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
            "operation": "setting-save", "id": identity, "value": value,
            "revision": "invalid",
        }}, **auth)[0] == 400


def test_timezone_setting_validates_and_saves_through_existing_worker(profile_browser):
    from klaude_core.settings_store import read_settings, update_settings
    from klaude_core.time_settings import clock_reading

    host, service, _, auth = profile_browser
    route = "/api/v1/settings/agent"
    fields = _request(host, "GET", route, **auth)[2]["fields"]
    field = next(item for item in fields if item["id"] == "time_settings.timezone")
    assert field["value"] == "auto" and field["type"] == "choice"
    assert {"auto", "UTC", "Asia/Phnom_Penh", "America/New_York"} <= {
        choice["value"] for choice in field["choices"]
    }
    assert any(item["id"] == "tool_availability.current_time" for item in fields)
    for value in (True, None, "Mars/Olympus", "../../UTC", "Asia/Phnom_Penh\n"):
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
            "operation": "setting-save", "id": field["id"], "value": value,
            "revision": field["revision"],
        }}, **auth)[0] == 400
    draft = {"operation": "setting-save", "id": field["id"],
             "value": "Asia/Phnom_Penh", "revision": field["revision"]}
    review = _review(host, auth, draft)
    path = service.data / "chat-preferences.json"
    update_settings(path, {("display", "activity_updates"): False})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert read_settings(path)["time_settings"] == {"timezone": "Asia/Phnom_Penh"}
    assert read_settings(path)["display"]["activity_updates"] is False
    assert clock_reading(service.data)["timezone"] == "Asia/Phnom_Penh"
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft},
                    **auth)[0] == 400


def test_web_and_research_settings_validate_budgets_and_stale_changes(profile_browser):
    from klaude_core.research import read_research_defaults
    from klaude_core.settings_store import update_settings

    host, service, _, auth = profile_browser
    path = service.data / "chat-preferences.json"

    def field(identity):
        return next(item for item in _request(host, "GET", "/api/v1/settings/agent", **auth)[2][
            "fields"
        ] if item["id"] == identity)

    for identity, value in (("search_settings.provider", "brave"),
                            ("fetch_settings.crawl4ai_url", "http://127.0.0.1:11235"),
                            ("research.queries", 3)):
        selected = field(identity)
        review = _review(host, auth, {"operation": "setting-save", "id": identity,
                                     "value": value, "revision": selected["revision"]})
        assert _submit(host, service, auth, review)[0]["state"] == "completed"
        assert field(identity)["value"] == value
    selected = field("research.queries")
    review = _review(host, auth, {"operation": "setting-save", "id": selected["id"],
                                 "value": 4, "revision": selected["revision"]})
    update_settings(path, {("research", "rounds"): 3})
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert read_research_defaults(service.cfg).queries == 3
    assert read_research_defaults(service.cfg).rounds == 3
    for identity, value in (("research.output_tokens", 8000),
                            ("research.parallel", 4),
                            ("search_settings.provider", "invented"),
                            ("fetch_settings.crawl4ai_url", "https://admin:secret@example.test"),
                            ("search_settings.searxng_url", "https://example.test?key=secret")):
        selected = field(identity)
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
            "operation": "setting-save", "id": identity, "value": value,
            "revision": selected["revision"],
        }}, **auth)[0] == 400


def test_browser_research_queue_and_stop_use_real_store(profile_browser):
    from klaude_core.research import ResearchStore

    host, service, _, auth = profile_browser
    route = "/api/v1/library/jobs"
    assert _request(host, "GET", route)[0] == 401
    assert _request(host, "GET", route, **auth)[2]["research"] == []
    review = _review(host, auth, {"operation": "research-create",
        "question": "How do database transactions recover?", "model": "ollama/fixture",
        "format": "brief"})
    assert not ResearchStore(service.data / "library").listing()["items"]
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    jobs = _request(host, "GET", route, **auth)[2]["research"]
    assert len(jobs) == 1 and jobs[0]["status"] == "queued"
    assert "spec" not in jobs[0] and "owner" not in jobs[0]
    review = _review(host, auth, {"operation": "research-stop", "target": jobs[0]["id"],
                                "revision": jobs[0]["revision"]})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert ResearchStore(service.data / "library").get(jobs[0]["id"])["status"] == "cancelled"
    # A changed queued/resumed job cannot be started from a stale review.
    item = ResearchStore(service.data / "library").get(jobs[0]["id"])
    review = _review(host, auth, {"operation": "research-run", "target": item["id"],
                                "revision": item["revision"]})
    ResearchStore(service.data / "library").update(item["id"], status="queued")
    assert _submit(host, service, auth, review)[0]["state"] == "failed"


def test_browser_image_generation_review_real_pixels_and_deduplication(
    profile_browser, generation_lab,
):
    from .test_image_generation import enable

    host, service, _, auth = profile_browser
    enable(generation_lab)
    calls = generation_lab[3]
    review = _review(host, auth, {"operation": "image-generate", "prompt": "Amber mountain",
                                "width": 512, "height": 512, "steps": 10})
    assert not any(method == "POST" for method, _, _ in calls)
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert len([call for call in calls if call[1] == "/sdcpp/v1/img_gen"]) == 1
    images = _request(host, "GET", "/api/v1/library/jobs", **auth)[2]["images"]
    assert len(images) == 1 and images[0]["status"] == "complete"
    item = service.artifacts.get(images[0]["artifact"])
    assert item["mime"] == "image/png" and item["width"] > 0
    generated = service.listing(kind="all", source="output")["items"]
    assert any(row["id"] == item["id"] for row in generated)


@pytest.mark.parametrize("operation", ["session-rename", "session-delete"])
def test_session_workspace_is_rechecked_inside_the_effect_transaction(
    profile_browser, monkeypatch, operation,
):
    from klaude_application import browser_sessions

    host, service, memory, _ = profile_browser
    identity = uuid.uuid4().hex
    memory.log_turn(identity, "user", "Preserve this conversation")
    host.application.turns.bind_workspace(identity, str(service.workspace), expected_revision=0)
    if operation == "session-delete":
        memory.change_session_archive(identity, "archive")
    fields, _, _ = browser_sessions.prepare_session_operation(
        memory.sessions_db, service.workspace, {
            "operation": operation, "target": identity,
            **({"name": "New title"} if operation == "session-rename" else {}),
        },
    )
    original = browser_sessions.session_view

    def move_after_read(*args):
        result = original(*args)
        with memory._db_lock, memory.db:
            memory.db.execute("UPDATE application_workspace SET path=? WHERE session_id=?",
                              (str(service.workspace / "other"), identity))
        return result

    monkeypatch.setattr(browser_sessions, "session_view", move_after_read)
    with pytest.raises(ValueError, match="workspace changed"):
        browser_sessions.run_session_operation(memory, service.workspace,
                                                {"operation": operation, **fields})
    assert memory.load_session(identity)
    assert memory.session_title(identity) == "Preserve this conversation"
