import json
import queue
from dataclasses import asdict
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.model_settings import (
    ConnectionDraft,
    ModelSettings,
    read_inventory,
)
from klaude_cli.model_settings import (
    test_catalog as check_catalog,
)
from klaude_cli.session_actions import ModelConnectionAdd, SessionActionWriter
from klaude_cli.settings_panel import PanelAction, PanelState, render_body
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_runtime import ModelInfo, save_model_cache
from klaude_core.settings_store import atomic_write_private
from prompt_toolkit.utils import get_cwidth


@pytest.fixture
def cfg(tmp_path):
    return SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        ollama_url="http://localhost:11434",
        models={"coder": "small:3b"},
    )


class Jobs:
    def __init__(self):
        self.requests = {}
        self.cancelled = []

    def submit(self, key, request, **kwargs):
        identity = str(len(self.requests))
        self.requests[identity] = (key, request)
        return identity

    def cancel(self, key):
        self.cancelled.append(key)


class Host:
    def __init__(self, cfg):
        self.cfg = cfg
        self.session_id, self.client_id = "session", "client"
        self.agent = SimpleNamespace(model="small:3b")
        self._background_jobs = Jobs()
        self._choice_kind = ""
        self._panel = None
        self.feedback = None
        self.selected = None
        self._session_actions = SimpleNamespace(submit=lambda action: True)

    def _open_panel(self, page, kind, focus):
        if self._panel and self._panel.page.id == page.id:
            self._panel.replace(page)
        else:
            self._panel = PanelState(page, focus)
        self._choice_kind = kind

    def _set_panel_feedback(self, *value):
        self.feedback = value

    def _activate_selected_model(self, info):
        self.selected = info


def draft_controller(cfg):
    host = Host(cfg)
    controller = ModelSettings(host)
    controller.draft = ConnectionDraft("Local", "openai_compatible", "http://localhost:8080/v1")
    controller.show("form")
    return controller


def test_deepseek_shortcut_starts_fresh_unsaved_draft(cfg):
    controller = draft_controller(cfg)
    controller.draft.key = "old-private-key"
    controller.test_result = {"status": "ok"}
    controller.begin_api_provider("deepseek")
    assert controller.draft.backend == "deepseek"
    assert controller.draft.url == "https://api.deepseek.com/v1"
    assert not controller.draft.key and controller.test_result is None
    assert controller.draft.connection().key_env.startswith("KLAUDE_MODEL_")
    assert not connection_registry(cfg).path.exists()
    assert not (cfg.config_dir / ".env").exists()


def test_deepseek_shortcut_preserves_accepted_save(cfg):
    controller = draft_controller(cfg)
    original = controller.draft
    controller.pending = ("accepted-save", original.connection())
    controller.begin_api_provider("deepseek")
    assert controller.draft is original
    assert controller.host.feedback[1] == "warning"


def test_deepseek_environment_reference_uses_private_inventory_pipe(cfg, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-env-canary")
    controller = draft_controller(cfg)
    controller.refresh()
    request = next(iter(controller.host._background_jobs.requests.values()))[1]
    assert request["environment_keys"]["DEEPSEEK_API_KEY"] == "private-env-canary"
    assert "private-env-canary" not in repr(controller.host._panel.page)


def test_unsaved_catalog_check_never_writes_definition_key_or_cache(cfg, monkeypatch):
    draft = ConnectionDraft(
        "Local", "openai_compatible", "http://localhost:8080/v1", key="private-canary"
    )
    client = httpx.Client
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"data": [{"id": "vendor/model"}]})

    monkeypatch.setattr(
        "klaude_core.model_discovery.httpx.Client",
        lambda **kw: client(**kw, transport=httpx.MockTransport(respond)),
    )
    result = check_catalog(
        {
            "draft": True,
            "connection": asdict(draft.connection()),
            "key": draft.key,
            "config_dir": str(cfg.config_dir),
        }
    )
    assert result["status"] == "ok"
    assert seen[0].url.path == "/v1/models"
    assert seen[0].headers["Authorization"] == "Bearer private-canary"
    assert "private-canary" not in json.dumps(result)
    assert not cfg.config_dir.exists() and not cfg.data_dir.exists()


def test_endpoint_change_clears_secret_and_rejects_late_draft_result(cfg):
    controller = draft_controller(cfg)
    controller.draft.key = "private-canary"
    controller.test()
    identity = controller.request[0]
    old = asdict(controller.draft.connection())
    controller.answer("url", "http://other-service:8080/v1")
    controller.accept(
        "model-settings:test", identity, {"status": "ok", "connection": old, "models": []}, ""
    )
    assert controller.draft.key == ""
    assert controller.test_result is None
    assert controller.request is None
    assert "private-canary" not in repr(controller.draft)


def test_cancel_discards_draft_and_cancels_test_without_saving(cfg):
    controller = draft_controller(cfg)
    controller.draft.key = "private-canary"
    controller.test()
    controller.action(PanelAction("model-settings-back", "discard"))
    assert controller.draft is None and controller.test_result is None
    assert controller.request is None
    assert "model-settings:test" in controller.jobs.cancelled
    assert not cfg.config_dir.exists()


def test_untested_add_requires_separate_review_with_cancel_initially_focused(cfg):
    controller = draft_controller(cfg)
    controller.save()
    assert controller.view == "untested"
    assert controller.host._panel.picker.selected_id == "back"
    assert controller.pending is None
    controller.action(PanelAction("model-settings-back", "form"))
    assert controller.draft is not None


def test_inventory_read_does_not_initialize_registry_or_publish_keys(cfg, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-canary")
    result = read_inventory(
        {
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "ollama_url": cfg.ollama_url,
        }
    )
    assert result["authenticated"]["default-openai-api"]
    assert "private-canary" not in json.dumps(result)
    assert not cfg.config_dir.exists()


def test_inventory_ack_does_not_interrupt_transient_editor_or_new_session(cfg):
    controller = draft_controller(cfg)
    controller.refresh()
    controller.host._choice_kind = None
    data = {"connections": [], "models": [], "authenticated": {}}
    controller.accept("model-settings:inventory", "0", data, "")
    assert controller.host._choice_kind is None
    controller.host.session_id = "other"
    controller.connections = None
    controller.accept("model-settings:inventory", "0", data, "")
    assert controller.connections is None


def test_accepted_save_drains_without_session_database_and_ack_excludes_secret(cfg, monkeypatch):
    monkeypatch.delenv("KLAUDE_MODEL_TEST_OWNED", raising=False)
    events = queue.Queue()
    memory = SimpleNamespace(
        open_session_io=lambda: pytest.fail("Model save must not open sessions")
    )
    writer = SessionActionWriter(memory, lambda *value: events.put(value))
    connection = ModelConnection(
        "lab",
        "Lab",
        "openai_compatible",
        "http://localhost:8080",
        key_env="KLAUDE_MODEL_TEST_OWNED",
    )
    update = ModelConnectionAdd("original-session", "client", cfg, connection, "private-canary")
    try:
        assert writer.submit(update)
        assert writer.close(wait=True)
        kind, payload = events.get_nowait()
        assert kind == "model_connection_saved"
        assert payload == ("original-session", connection, True)
        assert "private-canary" not in repr(update) + repr(payload)
        assert connection_registry(cfg).load()[connection.id] == connection
        assert "private-canary" not in connection_registry(cfg).path.read_text()
        secret_file = cfg.config_dir / ".env"
        assert "private-canary" in secret_file.read_text()
        assert secret_file.stat().st_mode & 0o777 == 0o600
    finally:
        monkeypatch.delenv("KLAUDE_MODEL_TEST_OWNED", raising=False)


def test_failed_definition_publication_removes_new_key_and_preserves_existing_config(
    cfg, monkeypatch
):
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    original = registry.path.read_bytes()
    atomic_write_private(cfg.config_dir / ".env", "# existing\nKEEP_ME=unrelated\n")
    connection = ModelConnection(
        "lab", "Lab", "ollama", cfg.ollama_url, key_env="KLAUDE_MODEL_TEST_ROLLBACK"
    )
    monkeypatch.delenv(connection.key_env, raising=False)

    def fail(*args):
        raise OSError("Storage unavailable")

    monkeypatch.setattr("klaude_core.model_connections.atomic_write_private", fail)
    with pytest.raises(OSError):
        registry.add(connection, secret="private-canary")
    assert registry.path.read_bytes() == original
    assert "private-canary" not in (cfg.config_dir / ".env").read_text()
    assert "KEEP_ME=unrelated" in (cfg.config_dir / ".env").read_text()


def test_manual_model_selection_captures_credential_revision_and_preserves_model_id(cfg):
    controller = draft_controller(cfg)
    connection = ModelConnection(
        "lab", "Lab", "openai_compatible", "https://host/v1", "Cloud", "KLAUDE_MODEL_TEST"
    )
    controller.connections = {"lab": connection}
    controller.credential_revisions = {"lab": "accepted-revision"}
    controller.registered = True
    controller.target = "lab"
    controller.select("vendor/model")
    assert controller.host.selected.ref == "openai_compatible@lab/vendor/model"
    assert controller.host.selected.credential_revision == "accepted-revision"


def test_uncertain_directory_fsync_keeps_key_for_published_definition(cfg, monkeypatch):
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    connection = ModelConnection(
        "lab", "Lab", "ollama", cfg.ollama_url, key_env="KLAUDE_MODEL_TEST_PUBLISHED"
    )
    monkeypatch.delenv(connection.key_env, raising=False)

    def publish_then_fail(path, payload):
        atomic_write_private(path, payload)
        raise OSError("Directory sync failed")

    monkeypatch.setattr("klaude_core.model_connections.atomic_write_private", publish_then_fail)
    try:
        with pytest.raises(OSError):
            registry.add(connection, secret="private-canary")
        assert registry.load()["lab"] == connection
        assert "private-canary" in (cfg.config_dir / ".env").read_text()
    finally:
        monkeypatch.delenv(connection.key_env, raising=False)


def test_next_prompt_selection_closes_panel_and_restores_composer_draft(cfg):
    controller = draft_controller(cfg)
    host = controller.host
    connection = ModelConnection("lab", "Lab", "ollama", cfg.ollama_url)
    controller.connections = {"lab": connection}
    controller.target = "lab"
    controller.registered = True
    restored = []
    host._restore_panel_composer_draft = lambda: restored.append("unsent draft")
    host.input = object()
    host.application = SimpleNamespace(
        layout=SimpleNamespace(focus=lambda target: None), invalidate=lambda: None
    )

    def accept_for_next_prompt(info):
        host.selected = info
        host._choice_kind = None

    host._activate_selected_model = accept_for_next_prompt
    controller.select("small:3b")
    assert host.selected.ref == "ollama@lab/small:3b"
    assert host._panel is None
    assert restored == ["unsent draft"]


@pytest.mark.parametrize("view", ["added", "catalog"])
@pytest.mark.parametrize("width", [38, 80, 120])
def test_inventory_controls_precede_headers_and_render_within_terminal_width(cfg, view, width):
    controller = draft_controller(cfg)
    connection = ModelConnection("lab", "Long endpoint label on LAN", "ollama", cfg.ollama_url)
    controller.connections = {"lab": connection}
    controller.models = [
        ModelInfo(
            "ollama",
            "vendor/long-model-name:3b",
            "model",
            connection_id="lab",
            connection_revision=connection.revision,
        )
    ]
    controller.show(view, "lab")
    page = controller.page()
    ids = [item.id for item in page.rows]
    assert ids.index("test" if view == "catalog" else "reload") < ids.index("columns")
    body = render_body(PanelState(page), width)
    assert all(get_cwidth("".join(part for _, part in line)) <= width for line in body.lines)


def test_catalog_refresh_keeps_filtered_focus_and_equal_ids_from_other_endpoint(cfg):
    controller = draft_controller(cfg)
    connection = ModelConnection("lab", "Lab", "ollama", cfg.ollama_url)
    controller.connections = {"lab": connection}
    controller.models = [
        ModelInfo("ollama", "same:3b", "Same", connection_id="lab"),
        ModelInfo("ollama", "same:3b", "Same", connection_id="other"),
    ]
    controller.show("catalog", "lab")
    controller.host._panel.filter("same")
    controller.test()
    identity = controller.request[0]
    from klaude_core.model_runtime import model_records

    model = ModelInfo("ollama", "same:3b", "Same", connection_id="lab")
    controller.accept(
        "model-settings:test",
        identity,
        {"status": "ok", "connection": asdict(connection), "models": model_records([model])},
        "",
    )
    assert controller.host._panel.picker.query == "same"
    assert controller.host._panel.picker.selected_id == "model:same:3b"
    assert len(controller.models) == 2


def test_inventory_cache_rejects_models_from_previous_endpoint_definition(cfg):
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    connection = ModelConnection("lab", "Lab", "ollama", "http://new:11434")
    registry.add(connection)
    stale = ModelInfo(
        "ollama", "small:3b", "Small", connection_id="lab", connection_revision="old-definition"
    )
    save_model_cache(
        cfg.data_dir / "model-cache.json", [stale], backend="ollama", connection_id="lab"
    )
    inventory = read_inventory(
        {
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "ollama_url": cfg.ollama_url,
        }
    )
    assert inventory["models"] == []


def test_review_clears_stale_search_and_replacement_or_unset_is_explicit(cfg):
    from klaude_core.model_management import ModelChange

    controller = draft_controller(cfg)
    lab = ModelConnection("lab", "Lab", "ollama", cfg.ollama_url)
    controller.connections = {"lab": lab}
    controller.target = "lab"
    controller.startup["last_model"] = lab.model_ref("small")
    controller.begin_review(ModelChange("enabled", (lab,), value=False), "detail")
    controller.host._panel.search_active = True
    controller.host._panel.filter("disable")
    controller.begin_review(ModelChange("remove", (lab,)), "detail")
    assert controller.host._panel.picker.query == ""
    assert not controller.host._panel.search_active
    assert controller.host._panel.picker.selected_id == "back"
    assert controller.review.replacement == ""
    assert controller.change_pending is None


def test_catalog_filter_is_endpoint_scoped_and_clears_control_navigation_search(cfg):
    controller = draft_controller(cfg)
    lab = ModelConnection("lab", "Lab", "ollama", cfg.ollama_url)
    other = ModelConnection("other", "Other", "ollama", cfg.ollama_url)
    controller.connections = {"lab": lab, "other": other}
    controller.target = "lab"
    controller.show("catalog")
    controller.host._panel.filter("filter")
    controller.maintenance_action("filter-choice:pinned", "pinned")
    assert controller.host._panel.picker.query == ""
    assert controller.catalog_filter == "pinned"
    controller.target = "other"
    assert controller.catalog_filter == "all"
