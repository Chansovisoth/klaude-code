"""Research execution, real store ownership, evidence and navigation boundaries."""

import json
import time
from types import SimpleNamespace

import pytest
from klaude_application.research import (
    ResearchCreate,
    ResearchRun,
    ResearchService,
    research_control_from_worker,
)
from klaude_cli.library_inventory import execute_library
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.ai_defaults import DefaultsChange, migrate_defaults, read_defaults, save_defaults
from klaude_core.config import Config
from klaude_core.library_artifacts import ArtifactStore
from klaude_core.model_connections import connection_registry
from klaude_core.model_management import ModelChange, apply_model_change
from klaude_core.research import (
    ResearchDefaults,
    ResearchError,
    ResearchStore,
    execute_research_request,
    make_spec,
    read_research_defaults,
    research_defaults,
    run_research,
    save_research_defaults,
    validated_claims,
)
from klaude_core.settings_store import SettingsConflictError, update_settings
from prompt_toolkit.utils import get_cwidth

from .test_library_workspace import library_host  # noqa: F401
from .test_library_workspace import memory as memory


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    item = Config()
    item.models["coder"] = "fixture"
    item.data_dir.mkdir(parents=True, exist_ok=True)
    connection_registry(item).migrate(item)
    migrate_defaults(item)
    monkeypatch.setattr(config, "load_config", lambda: item)
    return item


@pytest.fixture
def services(monkeypatch):
    from klaude_core import utility
    from klaude_web import Web

    calls = []
    fetched = []

    class Runtime:
        last_chat_metadata = {}

        def chat(self, model, messages, **kwargs):
            data = json.loads(messages[-1]["content"])
            calls.append((data, kwargs))
            if "searched" in data:
                result = {
                    "queries": ["reliable transactions", "transaction recovery"],
                    "done": bool(data["sources"]),
                }
            else:
                result = {
                    "claims": [
                        {
                            "text": "Transactions retain the previous state on failure.",
                            "source": source["id"],
                            "quote": source["content"][:90],
                        }
                        for source in data["sources"]
                    ]
                }
            return {"content": json.dumps(result)}

        def cancel_active(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(utility, "runtime_for_utility", lambda *_: Runtime())
    monkeypatch.setattr(
        Web,
        "search_detailed",
        lambda *a, **k: SimpleNamespace(
            results=[
                {"url": "https://example.com/transactions"},
                {"url": "https://example.org/recovery"},
            ]
        ),
    )

    def fetch(_self, url):
        fetched.append(url)
        return {
            "content": "Atomic transactions keep old data until replacement succeeds. " + url,
            "final_url": url,
            "title": "Transaction documentation",
        }

    monkeypatch.setattr(Web, "_fetch_uncached_detailed", fetch)
    return calls, fetched


def job(cfg, **kwargs):
    settings = ResearchDefaults().public()
    settings.update(kwargs)
    spec = make_spec(cfg, "Compare atomic writes and recovery", "ollama/fixture", settings)
    return ResearchStore(cfg.data_dir / "library").create(spec)


def test_completed_job_citations_and_metadata_not_replayable(cfg, services):
    item = job(cfg)
    result = run_research(cfg, item["id"])
    assert result["status"] == "completed", result
    assert result["report"].startswith("research:")
    calls, fetched = services
    assert len(calls) == 3 and len(fetched) == 2
    assert all(call[1]["tools"] is None and call[1]["think"] is False for call in calls)
    assert all("content" not in source for source in result["sources"])
    assert "Atomic transactions keep" not in json.dumps(result)
    preview = ArtifactStore(cfg.data_dir / "library").preview(result["report"])
    text = "\n".join(preview["lines"])
    assert "https://example.com/transactions" in text and "> Atomic transactions" in text
    assert ResearchStore(cfg.data_dir / "library").stop(item["id"])["status"] == "completed"


def test_cancelled_recovery_re_fetches_receipts_before_synthesis(cfg, services):
    item = job(cfg)
    store = ResearchStore(cfg.data_dir / "library")
    store.update(
        item["id"],
        status="cancelled",
        round=2,
        sources=[{"id": "old", "url": "https://example.com/transactions", "sha256": "old-hash"}],
    )
    result = run_research(cfg, item["id"])
    assert result["status"] == "partial" and services[1] == ["https://example.com/transactions"]
    assert services[0][0][0]["sources"][0]["id"] != "old"
    assert "old-hash" not in json.dumps(services[0])


def test_output_repair_is_bounded_and_rejects_unread_source(cfg, services, monkeypatch):
    from klaude_core import research

    original = research.validated_claims
    checks = []

    def validate(value, sources):
        checks.append(value)
        if len(checks) == 1:
            raise ResearchError("Unread source")
        return original(value, sources)

    monkeypatch.setattr(research, "validated_claims", validate)
    result = run_research(cfg, job(cfg)["id"])
    assert result["status"] == "completed" and len(checks) == 2
    assert services[0][-1][0]["validation_error"] == "Unread source"


def test_failed_citation_repair_saves_no_report(cfg, services, monkeypatch):
    from klaude_core import research

    monkeypatch.setattr(
        research,
        "validated_claims",
        lambda *_: (_ for _ in ()).throw(ResearchError("Unsupported quote")),
    )
    result = run_research(cfg, job(cfg)["id"])
    assert result["status"] == "error" and result["report"] == ""
    assert not ArtifactStore(cfg.data_dir / "library").listing("research")["items"]
    assert len(services[0]) == 4


@pytest.mark.parametrize(
    "claim",
    [
        {"text": "Claim", "source": "unknown", "quote": "Atomic transactions keep"},
        {"text": "Claim", "source": "src", "quote": "This quote was never fetched"},
        {"text": "https://invented.example", "source": "src", "quote": "Atomic transactions keep"},
    ],
)
def test_evidence_validation_rejects_fabrication(claim):
    with pytest.raises(ResearchError):
        validated_claims(
            {"claims": [claim]}, [{"id": "src", "content": "Atomic transactions keep old data"}]
        )


def test_small_budget_bounds_queries_sources_and_output(cfg, services):
    result = run_research(
        cfg, job(cfg, rounds=4, queries=1, sources=1, context_tokens=4096, output_tokens=512)["id"]
    )
    assert result["status"] == "partial" and len(services[1]) == 1
    assert len(result["queries"]) == 1 and len(services[0]) == 2
    assert max(len(json.dumps(data)) for data, _ in services[0]) < 5000


def test_report_and_job_publish_roll_back_together(cfg, services, monkeypatch):
    original = ArtifactStore.store_report

    def fail(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise OSError("fsync")

    monkeypatch.setattr(ArtifactStore, "store_report", fail)
    result = run_research(cfg, job(cfg)["id"])
    assert result["status"] == "error" and result["report"] == ""
    assert ArtifactStore(cfg.data_dir / "library").listing("research")["items"] == []


def test_settings_merge_and_stale_saves(cfg):
    update_settings(cfg.data_dir / "chat-preferences.json", {("unrelated",): True})
    original = read_research_defaults(cfg).public()
    save_research_defaults(cfg, {**original, "rounds": 3}, original)
    with pytest.raises(SettingsConflictError):
        save_research_defaults(cfg, {**original, "parallel": 1}, original)
    assert json.loads((cfg.data_dir / "chat-preferences.json").read_text())["unrelated"] is True
    with pytest.raises(ResearchError):
        research_defaults({"output_tokens": 16000, "context_tokens": 4096})


def test_research_role_survives_utility_edits_and_requires_removal_review(cfg):
    registry = connection_registry(cfg)
    connection = registry.load()["default-ollama"]
    reference = connection.model_ref("fixture")
    save_defaults(
        cfg, DefaultsChange("research", reference, None, ((reference, connection.revision, ""),))
    )
    assert read_defaults(cfg).research == reference
    with pytest.raises(SettingsConflictError):
        apply_model_change(cfg, ModelChange("enabled", (connection,), expected=True, value=False))
    # Startup defaults also need review; intentionally leave them unaffected.
    update_settings(cfg.data_dir / "chat-preferences.json", {("ai_defaults", "chat"): None})
    change = ModelChange(
        "enabled",
        (connection,),
        expected=True,
        value=False,
        unset_research=True,
        research_expected=reference,
    )
    apply_model_change(cfg, change)
    assert read_defaults(cfg).research is None


def test_metadata_browse_no_store_creation_and_expired_lease(cfg):
    root = cfg.data_dir / "library"
    store = ResearchStore(root)
    assert store.listing() == {"items": [], "more": False} and not root.exists()
    item = job(cfg)
    store.update(item["id"], status="running", lease_until=time.time() - 1)
    assert store.listing()["items"][0]["status"] == "interrupted"
    assert store.get(item["id"])["status"] == "running"  # read projection only


def test_queue_has_no_generation_and_respects_tool_availability(cfg, services):
    request = {
        "kind": "research_control",
        "operation": "create",
        "draft": {"question": "Atomic writes", "model": "ollama/fixture", "format": "report"},
        "settings": ResearchDefaults().public(),
    }
    reviewed = ResearchCreate.from_worker({
        **request,
        "draft": {**request["draft"], "queued": True},
    })
    assert "queued" not in reviewed.worker_fields()["draft"]
    result = ResearchService().create(reviewed)
    assert result["item"]["status"] == "queued" and services == ([], [])
    with pytest.raises(ValueError, match="Invalid Research create action"):
        ResearchCreate.from_worker({**request, "draft": {**request["draft"], "extra": "bad"}})
    update_settings(
        cfg.data_dir / "chat-preferences.json", {("tool_availability", "web_search"): False}
    )
    assert execute_research_request(request).get("error") and services == ([], [])


def test_research_run_contract_requires_exact_job_and_owner_ids():
    request = ResearchRun("a" * 32, "b" * 32).worker_fields()
    assert ResearchRun.from_worker(request).worker_fields() == request
    with pytest.raises(ValueError, match="Invalid Research run action"):
        ResearchRun.from_worker({**request, "owner": "another-client"})


def test_shared_research_controls_route_existing_job_guards(cfg):
    item = job(cfg)
    service = ResearchService()
    load = research_control_from_worker({
        "kind": "research_control", "operation": "load", "target": item["id"],
    })
    assert service.control(load)["item"]["id"] == item["id"]
    stop = research_control_from_worker({
        "kind": "research_control", "operation": "stop", "target": item["id"],
        "queued_only": True,
    })
    assert service.control(stop)["item"]["status"] == "cancelled"
    with pytest.raises(ValueError, match="Invalid Research defaults action"):
        research_control_from_worker({
            "kind": "research_control", "operation": "defaults", "values": {},
        })


def test_form_review_widths_and_report_views(memory, monkeypatch):
    host, calls = library_host(memory)
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", memory.sessions_db.parent)
    host._library.open("research")
    identity = host._library.pending[0]
    host._library.accept(identity, execute_library(calls[-1][1]), "")
    assert "New research" in str(host._panel.page)
    panel = host._library.research
    panel.draft = {
        "question": "Compare transactions",
        "format": "comparison",
        "model": "ollama/fixture",
    }
    host._library.show("research-form")
    panel.handle(PanelAction("library-research-start"))
    assert host._panel.picker.selected_id == "back"
    for width in (40, 70, 120):
        body = render_body(PanelState(host._panel.page), width)
        assert all(get_cwidth("".join(text for _, text in line)) <= width for line in body.lines)
    panel.handle(PanelAction("library-research-reports"))
    assert host._library.artifacts.kind == "research"
    panel.open()
    assert "RESEARCH JOBS" in str(host._panel.page)  # no artifact/job view collision


def test_native_reference_without_registry_does_not_create_one(cfg):
    registry = connection_registry(cfg)
    registry.path.unlink()
    spec = make_spec(cfg, "Read a public page", "ollama/fixture", ResearchDefaults().public())
    assert spec["model"] == "ollama/fixture" and not registry.path.exists()


def test_queued_cancellation_and_live_owner_are_checked(cfg):
    store = ResearchStore(cfg.data_dir / "library")
    item = job(cfg)
    store.update(item["id"], status="running", owner="other-client", lease_until=time.time() + 30)
    with pytest.raises(ResearchError, match="changed"):
        store.stop(item["id"], queued_only=True)
    with pytest.raises(ResearchError, match="Another client"):
        store.stop(item["id"], owner="this-client")
    assert store.stop(item["id"], owner="other-client")["status"] == "cancelled"


def test_rejected_run_cannot_overwrite_another_clients_live_job(cfg, services):
    store = ResearchStore(cfg.data_dir / "library")
    item = job(cfg)
    running = store.update(
        item["id"], status="running", owner="other-client", lease_until=time.time() + 30
    )
    result = execute_research_request(
        {"kind": "research_run", "target": item["id"], "owner": "this-client"}
    )
    assert result.get("error")
    assert store.get(item["id"]) == running
    assert services == ([], [])


def test_completed_run_is_idempotent_after_endpoint_changes(cfg, services, monkeypatch):
    from klaude_core import research

    completed = run_research(cfg, job(cfg)["id"])
    calls_before = len(services[0])

    def unavailable(*_):
        raise ResearchError("Endpoint disabled")

    monkeypatch.setattr(research, "model_binding", unavailable)
    assert (
        execute_research_request({"kind": "research_run", "target": completed["id"]}) == completed
    )
    assert len(services[0]) == calls_before


def test_preflight_failure_rejects_stale_revision_and_keeps_partial_report(cfg):
    store = ResearchStore(cfg.data_dir / "library")
    item = job(cfg)
    changed = store.update(item["id"], phase="Updated by another client")
    with pytest.raises(ResearchError, match="changed"):
        store.fail_unstarted(item["id"], item["revision"], "Preflight failed")
    assert store.get(item["id"]) == changed
    partial = store.update(item["id"], status="partial", report="research:retained")
    with pytest.raises(ResearchError, match="changed"):
        store.fail_unstarted(item["id"], partial["revision"], "Preflight failed")
    assert store.get(item["id"]) == partial


def test_cancelled_partial_resume_keeps_report_and_releases_live_lease(cfg):
    store = ResearchStore(cfg.data_dir / "library")
    item = job(cfg)
    store.update(
        item["id"],
        status="running",
        report="research:previous-partial",
        owner="this-client",
        lease_until=time.time() + 30,
    )
    stopped = store.stop(item["id"], owner="this-client")
    assert stopped["status"] == "cancelled" and stopped["lease_until"] == 0
    assert stopped["report"] == "research:previous-partial"


def test_late_research_result_does_not_replace_another_open_job(memory):
    host, _ = library_host(memory)
    panel = host._library.research
    panel.task = ("run", host.session_id, host._library.scope)
    panel.running_id = "first-job"
    panel.item = {"id": "second-job", "question": "Open question", "status": "queued"}
    host._library.show("research-job")
    panel.accept("run", {"id": "first-job", "status": "completed", "report": "research:x"}, "")
    assert panel.item["id"] == "second-job" and not panel.busy


def test_report_metadata_loading_does_not_offer_premature_actions(memory):
    host, _ = library_host(memory)
    host._library.artifacts.open("research-reports")
    host._library.artifacts.detail = {"id": "research:" + "a" * 32}
    host._library.show("artifact-detail")
    assert "Loading report metadata" in str(host._panel.page)
    assert not any(row.id == "discuss" for row in host._panel.page.rows)


def test_planned_public_urls_are_fetched_without_searching(cfg, services, monkeypatch):
    from klaude_core import utility

    class Runtime:
        last_chat_metadata = {}

        def chat(self, _model, messages, **_kwargs):
            data = json.loads(messages[-1]["content"])
            value = (
                {
                    "queries": ["https://example.com/transactions", "https://example.org/recovery"],
                    "done": bool(data["sources"]),
                }
                if "searched" in data
                else {
                    "claims": [
                        {
                            "text": "Atomic activation retains old data.",
                            "source": source["id"],
                            "quote": source["content"][:90],
                        }
                        for source in data["sources"]
                    ]
                }
            )
            return {"content": json.dumps(value)}

        def cancel_active(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(utility, "runtime_for_utility", lambda *_: Runtime())
    from klaude_web import Web

    monkeypatch.setattr(Web, "search_detailed", lambda *a, **k: pytest.fail("URL was searched"))
    result = run_research(cfg, job(cfg)["id"])
    assert result["status"] == "completed" and len(services[1]) == 2


def test_discuss_closes_library_and_preserves_unsent_attachments(memory, monkeypatch):
    host, _ = library_host(memory)
    panel = host._library.research
    host._library.artifacts.open("research-reports")
    host._panel_composer_draft = ("Unsent project notes", [])
    host._pending_attachments = ["attachment-canary"]
    panel.control = ("control", host.session_id, "report-action")
    panel.control_context = (host._library.view, "", host._library.scope)
    panel.report_kind = "discuss"
    monkeypatch.setattr(host, "_start_next", lambda: None)
    panel.accept_control(
        "control",
        {"prompt": "Private stored report context", "public_message": "Discuss stored report"},
        "",
    )
    assert host._choice_kind is None and host._panel is None
    assert host._pending_attachments == ["attachment-canary"]
    assert host.pending[-1].attachments == ()
    assert host.pending[-1].model_message == "Private stored report context"
    assert "Private stored" not in str(host.pending[-1])
    assert host.input.buffer.text == "Unsent project notes"


def test_new_research_can_queue_during_owned_job(memory):
    host, calls = library_host(memory)
    panel = host._library.research
    panel.task = ("run", host.session_id, host._library.scope)
    panel.running_id = "first-job"
    panel.item = {"id": "first-job", "status": "running"}
    panel.draft = {
        "question": "Second independent question",
        "format": "report",
        "model": "ollama/fixture",
        "queued": True,
    }
    host._library.show("research-form")
    queue_row = next(row for row in host._panel.page.rows if row.id == "queue")
    start_row = next(row for row in host._panel.page.rows if row.id == "start")
    assert queue_row.enabled and not start_row.enabled
    panel.submit_control("create", draft=panel.draft, settings=panel.defaults)
    assert panel.task[0] == "run" and calls[-1][0] == "research:control"


@pytest.mark.parametrize("status,code", [("completed", 0), ("partial", 2), ("error", 1)])
def test_research_cli_exit_codes_distinguish_partial_reports(cfg, monkeypatch, status, code):
    from klaude_cli import research_commands
    from typer.testing import CliRunner

    item = job(cfg)

    class Jobs:
        def __init__(self, emit):
            self.emit = emit

        def submit(self, *_args, **_kwargs):
            self.emit(
                "background_result",
                (
                    "research",
                    "run",
                    {"status": status, "report": "research:report", "phase": "Failed validation"},
                    "",
                ),
            )

        def close(self, **_kwargs):
            pass

    monkeypatch.setattr(research_commands, "load_config", lambda: cfg)
    monkeypatch.setattr(research_commands, "OwnedBackgroundJobs", Jobs)
    result = CliRunner().invoke(research_commands.app, ["resume", item["id"]])
    assert result.exit_code == code
    if status == "error":
        assert "Failed validation" in result.stdout


def test_report_discussion_scope_blocks_workspace_mcp_and_delegation():
    from klaude_core import Agent, PermissionGate, Tool, TurnScope

    from .test_agentic_search import ScriptedOllama, tool_call

    executed = []
    names = (
        "query_knowledge",
        "web_search",
        "fetch_url",
        "read_file",
        "run_shell",
        "write_file",
        "delegate_task",
        "mcp_custom",
    )
    tools = [
        Tool(name, name, {"type": "object"}, lambda **_kwargs: executed.append(True) or "ok")
        for name in names
    ]
    model = ScriptedOllama(
        [tool_call("run_shell"), {"role": "assistant", "content": "Stored report discussion"}]
    )
    agent = Agent(
        model,
        "fake-model",
        tools,
        PermissionGate({name: "allow" for name in names}, lambda *_: "y"),
        "system",
        tool_selector=lambda _msg, available: list(available),
    )
    list(agent.run("Discuss report data", scope=TurnScope.RESEARCH))
    assert not executed
    assert {tool["function"]["name"] for tool in model.calls[0]["tools"]} == {
        "query_knowledge",
        "web_search",
        "fetch_url",
    }
    assert agent.last_turn_capabilities["scope"] == "research"
    assert set(agent.tools) == set(names)
