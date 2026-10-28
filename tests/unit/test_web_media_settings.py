"""Browser media setup uses real metadata requests and shared witnessed saves."""

import asyncio
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from klaude_application.image_settings import (
    ImageSettingsUnconfirmed,
    image_settings_resource,
    save_image_settings,
)
from klaude_application.model_default_settings import model_defaults_resource
from klaude_core.ai_defaults import DefaultsChange, read_defaults, save_defaults
from klaude_core.image_generation import read
from klaude_core.model_connections import DEFAULT_IDS, ModelConnection, connection_registry
from klaude_core.model_runtime import ModelCapabilities, ModelInfo
from klaude_core.settings_store import update_settings

from .test_image_generation import generation_lab as generation_lab
from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def media_browser(profile_browser):
    calls = []

    class Models(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, value):
            body = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            calls.append((self.path, {}))
            assert self.path == "/api/tags"
            self.reply({"models": [{"name": name, "model": name} for name in (
                "vision", "alternative", "text", "embedding",
            )]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            assert self.path == "/api/show"
            if body["model"] == "embedding":
                self.reply({})
                return
            self.reply({"capabilities": ["embedding"] if body["model"] == "embedding" else
                        ["completion"] + (
                ["vision"] if body["model"] != "text" else ["tools"]
            ) + (["image"] if body["model"] == "alternative" else [])})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Models)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, service, memory, auth = profile_browser
    service.cfg.models.setdefault("coder", "fixture")
    service.cfg.ollama_url = f"http://127.0.0.1:{server.server_port}"
    service.cfg.config_dir.mkdir(parents=True, exist_ok=True)
    (service.cfg.config_dir / "config.toml").write_text(
        f'[services]\nollama_url="{service.cfg.ollama_url}"\n'
        f'[models.override]\ncoder={json.dumps(service.cfg.models["coder"])}\n'
    )
    try:
        yield host, service, memory, auth, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _role(host, auth, cfg, field, value):
    return _review(host, auth, {"operation": "defaults-save", "field": field, "value": value,
                               "expected": read_defaults(cfg).public()[field]})


def test_media_inventory_is_private_and_does_not_discover_or_initialize(media_browser):
    host, service, _, auth, calls = media_browser
    route = "/api/v1/settings/models"
    assert _request(host, "GET", route)[0] == 401
    assert _request(host, "GET", route, fetch_site="cross-site", **auth)[0] == 403
    status, _, view = _request(host, "GET", route, **auth)
    assert status == 200 and view["defaults"]["vision_enabled"] is False
    assert view["image_service"]["enabled"] is False
    assert not view["pending"] and not calls
    assert not connection_registry(service.cfg).path.exists()
    assert not (service.data / "operations.db").exists()
    assert _request(host, "GET", route + "?secret=bad", **auth)[0] == 400


def test_default_catalog_uses_real_capabilities_for_every_role_without_saving(media_browser):
    host, service, _, auth, calls = media_browser
    route = f"/api/v1/models/catalog?connection={DEFAULT_IDS['ollama']}&purpose=defaults"
    assert _request(host, "GET", route)[0] == 401
    assert not calls
    status, _, result = _request(host, "GET", route, **auth)
    assert status == 200
    roles = {item["id"].split("/")[-1]: item["roles"] for item in result["models"]}
    assert roles["vision"] == {"chat": False, "utility": True, "research": False,
                                "vision": True}
    assert roles["text"] == {"chat": True, "utility": True, "research": True, "vision": False}
    assert roles["embedding"] == dict.fromkeys(("chat", "utility", "research", "vision"), None)
    assert {body["model"] for path, body in calls if path == "/api/show"} == set(roles)
    assert all(path in {"/api/tags", "/api/show"} for path, _ in calls)
    assert not (service.data / "operations.db").exists()
    assert not (service.data / "chat-preferences.json").exists()
    assert not connection_registry(service.cfg).path.exists()
    # Ordinary catalog clients keep their existing response and discovery cost.
    calls.clear()
    regular = _request(host, "GET", route.replace("&purpose=defaults", ""), **auth)[2]
    assert all("roles" not in item for item in regular["models"])
    assert [path for path, _ in calls] == ["/api/tags"]
    assert _request(host, "GET", route + "&purpose=defaults", **auth)[0] == 503


def test_image_catalog_distinguishes_generation_vision_and_unknown(media_browser):
    host, _, _, auth, _ = media_browser
    route = f"/api/v1/models/catalog?connection={DEFAULT_IDS['ollama']}&purpose=image-generation"
    status, _, result = _request(host, "GET", route, **auth)
    assert status == 200
    roles = {item["name"]: item["roles"]["image-generation"] for item in result["models"]}
    assert roles == {"alternative": True, "vision": False, "text": False, "embedding": None}


def test_default_catalog_preserves_unknowns_and_filters_cloud_roles(profile_browser, monkeypatch):
    from klaude_application.browser_models import BrowserModels

    host, service, _, auth = profile_browser
    connection = ModelConnection("cloud", "Cloud", "openai_compatible",
                                 "http://127.0.0.1:12345/v1")
    models = [
        ModelInfo("openai_compatible", "image", "Image", ModelCapabilities(
            supports_images=True, supports_tools=False, tools_evidence="catalog",
        )),
        ModelInfo("openai_compatible", "thinking", "Thinking", ModelCapabilities(
            supports_images=True, thinking_types=("enabled",), tools_evidence="catalog",
        )),
        ModelInfo("openai_compatible", "unknown", "Unknown"),
        ModelInfo("openai_codex", "codex", "Codex", ModelCapabilities(tools_evidence="catalog")),
    ]
    monkeypatch.setattr(BrowserModels, "connection", lambda self, identity: connection)
    monkeypatch.setattr(BrowserModels, "catalog", lambda self, identity: models)
    monkeypatch.setattr(BrowserModels, "current", lambda self, info: connection)
    status, _, view = _request(host, "GET",
                              "/api/v1/models/catalog?connection=cloud&purpose=defaults", **auth)
    assert status == 200
    roles = {item["name"]: item["roles"] for item in view["models"]}
    assert roles["Image"] == {"chat": False, "utility": True, "research": False, "vision": True}
    assert roles["Thinking"] == {"chat": True, "utility": False, "research": False,
                                  "vision": False}
    assert roles["Unknown"] == {"chat": None, "utility": True, "research": None, "vision": None}
    assert roles["Codex"] == {"chat": True, "utility": False, "research": False, "vision": False}


def test_default_catalog_rejects_metadata_races_and_does_not_guess(media_browser, monkeypatch):
    from klaude_application import browser_media_settings as module

    host, _, _, auth, _ = media_browser
    route = f"/api/v1/models/catalog?connection={DEFAULT_IDS['ollama']}&purpose=defaults"
    monkeypatch.setattr(module, "read_capabilities", lambda request: {
        "status": "ok", "models": [{"model": name} for name in request["models"]],
    })
    result = _request(host, "GET", route, **auth)[2]
    assert all(set(item["roles"].values()) == {None} for item in result["models"])
    monkeypatch.setattr(module, "read_capabilities", lambda request: {"status": "stale"})
    assert _request(host, "GET", route, **auth)[0] == 503


def test_default_catalog_bounds_inspection_and_labels_remaining_models(media_browser, monkeypatch):
    from klaude_application import browser_media_settings as module

    host, _, _, auth, calls = media_browser
    times = iter((0, 21))
    monkeypatch.setattr(module, "monotonic", lambda: next(times, 21))
    route = f"/api/v1/models/catalog?connection={DEFAULT_IDS['ollama']}&purpose=defaults"
    status, _, result = _request(host, "GET", route, **auth)
    assert status == 200
    assert all(set(item["roles"].values()) == {None} for item in result["models"])
    assert calls == [("/api/tags", {})]


@pytest.mark.parametrize(("backend", "field", "caps"), [
    ("openai_codex", "utility", ModelCapabilities()),
    ("openai_codex", "research", ModelCapabilities()),
    ("gemini_api", "research", ModelCapabilities(thinking_types=("enabled",))),
])
def test_default_review_rejects_roles_unsupported_by_their_worker(
    profile_browser, monkeypatch, backend, field, caps,
):
    from klaude_application.browser_models import BrowserModels

    host, service, _, auth = profile_browser
    info = ModelInfo(backend, "fixture", "Fixture", caps, connection_id="fixture")
    monkeypatch.setattr(BrowserModels, "verify", lambda self, *args, **kwargs: info)
    status, _, _ = _request(host, "POST", "/api/v1/library/review", body={"draft": {
        "operation": "defaults-save", "field": field, "value": info.ref, "expected": None,
    }}, **auth)
    assert status == 400
    assert read_defaults(service.cfg).public()[field] is None


def test_role_saves_use_one_shared_receipt_and_preserve_current_chat(media_browser):
    host, service, _, auth, calls = media_browser
    reference = f"ollama@{DEFAULT_IDS['ollama']}/vision"
    current_model = host.application.agent.model_info
    for field in ("utility", "research", "vision"):
        # Research requires tool declarations; this exact image model lacks them.
        if field == "research":
            assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
                "operation": "defaults-save", "field": field,
                "value": reference, "expected": None,
            }}, **auth)[0] == 400
            continue
        review = _role(host, auth, service.cfg, field, reference)
        assert read_defaults(service.cfg).public()[field] is None
        receipt, request = _submit(host, service, auth, review)
        assert receipt["state"] == "completed"
        assert receipt["resource"] == model_defaults_resource(service.data)
        assert _request(host, "POST", "/api/v1/library/submit", body=request, **auth)[0] == 202
        assert read_defaults(service.cfg).public()[field] == reference
    review = _role(host, auth, service.cfg, "vision_enabled", True)
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert read_defaults(service.cfg).vision_enabled
    assert host.application.agent.model_info == current_model
    assert calls and all(path in {"/api/show", "/api/tags"} for path, _ in calls)
    assert service.journal.fenced_operation(model_defaults_resource(service.data)) is None


def test_vision_enable_rechecks_changed_primary_inside_shared_writer(media_browser):
    host, service, _, auth, _ = media_browser
    primary = f"ollama@{DEFAULT_IDS['ollama']}/vision"
    assert _submit(host, service, auth, _role(host, auth, service.cfg, "vision", primary))[0][
        "state"
    ] == "completed"
    review = _role(host, auth, service.cfg, "vision_enabled", True)
    connection = connection_registry(service.cfg).load()[DEFAULT_IDS["ollama"]]
    replacement = connection.model_ref("alternative")
    save_defaults(service.cfg, DefaultsChange("vision", replacement, primary,
                                              ((replacement, connection.revision, ""),)))
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not read_defaults(service.cfg).vision_enabled


def test_default_numeric_cas_and_unrelated_fields(media_browser):
    host, service, _, auth, _ = media_browser
    review = _role(host, auth, service.cfg, "output_tokens", 256)
    update_settings(service.data / "chat-preferences.json",
                    {("display", "activity_updates"): False})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert read_defaults(service.cfg).output_tokens == 256
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
        "operation": "defaults-save", "field": "output_tokens", "value": 512, "expected": 512,
    }}, **auth)[0] == 400
    for field, value in (("output_tokens", True), ("output_tokens", 3000),
                          ("vision_enabled", True), ("fallbacks", ["bad"] * 4)):
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
            "operation": "defaults-save", "field": field, "value": value,
            "expected": read_defaults(service.cfg).public()[field],
        }}, **auth)[0] == 400


def test_fresh_chat_uses_explicit_startup_role_and_unset_requires_selection(media_browser):
    from klaude_application.browser_models import BrowserModels

    host, service, _, auth, _ = media_browser
    reference = f"ollama@{DEFAULT_IDS['ollama']}/text"
    original = host.application.session_id
    review = _role(host, auth, service.cfg, "chat", reference)
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert host.application.session_id == original
    assert host.application.agent.model_info.ref != reference
    selected = host.switch_session("test-owner", uuid.uuid4().hex, original, "", 0)
    assert selected != original and host.application.agent.model_info.ref == reference
    assert host.application.memory.session_runtime(selected)["model"] == reference
    assert not host.application.requires_model_selection
    save_defaults(service.cfg, DefaultsChange("chat", None, reference))
    next_session = host.switch_session("test-owner", uuid.uuid4().hex, selected, "", 0)
    assert next_session != selected and host.application.requires_model_selection
    assert host.public_snapshot()["requires_model_selection"]
    with pytest.raises(ValueError, match="Choose a model"):
        host.application.submit("Do not run without a selection")
    with pytest.raises(ValueError, match="Choose a model"):
        host.application.enqueue("Do not queue without a selection", request_id="unselected")
    host.application.choose_configured_model(BrowserModels(service.cfg).verify_ref(reference),
                                             expected_revision=0, request_id="select-startup")
    assert not host.application.requires_model_selection


def test_image_service_test_save_and_deduplication(media_browser, generation_lab):
    host, service, _, auth, _ = media_browser
    _, url, _, calls, _ = generation_lab
    draft = {"operation": "image-settings-save", "endpoint": url, "enabled": True,
             "revision": read(service.cfg)["revision"]}
    review = _review(host, auth, draft)
    assert review["image_settings"] == {"endpoint": url, "enabled": True,
                                         "provider": "sdcpp", "model": "local-test-model"}
    assert not read(service.cfg)["enabled"]
    assert not any(path.endswith("/jobs") for _, path, _ in calls)
    receipt, request = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert receipt["resource"] == image_settings_resource(service.cfg.config_dir)
    assert read(service.cfg)["enabled"] and read(service.cfg)["model"]
    assert _request(host, "POST", "/api/v1/library/submit", body=request, **auth)[0] == 202
    assert not any(path.endswith("/jobs") for _, path, _ in calls)
    assert service.journal.fenced_operation(image_settings_resource(service.cfg.config_dir)) is None


def test_image_service_recovers_exact_shared_unknown_without_network(media_browser, monkeypatch):
    host, service, _, auth, calls = media_browser
    journal = service.journal
    original_finish = journal.finish
    candidate = {"enabled": False, "endpoint": "http://127.0.0.1:1234", "model": "fixture"}
    identity = uuid.uuid4().hex

    def lost_ack(*args, **kwargs):
        raise OSError("lost acknowledgement")

    monkeypatch.setattr(journal, "finish", lost_ack)
    with pytest.raises(ImageSettingsUnconfirmed):
        save_image_settings(service.cfg, candidate, "", journal, identity, "cli")
    monkeypatch.setattr(journal, "finish", original_finish)
    view = _request(host, "GET", "/api/v1/settings/models", **auth)[2]
    assert view["pending"]["image_service"] == {"request_id": identity, "state": "unknown"}
    review = _review(host, auth, {"operation": "image-settings-recover", "target": identity})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    assert journal.status(identity, "cli").state == "completed"
    assert not calls


def test_launcher_uses_explicit_chat_default_and_respects_unset(media_browser, monkeypatch):
    from klaude_webhost import main

    host, service, _, auth, calls = media_browser
    reference = f"ollama@{DEFAULT_IDS['ollama']}/text"
    review = _role(host, auth, service.cfg, "chat", reference)
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    monkeypatch.setattr(main, "load_config", lambda: service.cfg)
    app = main.create_application(service.workspace)
    try:
        assert app.agent.model_info.ref == reference
        assert not app.requires_model_selection
        assert app.memory.session_runtime(app.session_id)["model"] == reference
    finally:
        asyncio.run(app.close())
    with monkeypatch.context() as unavailable:
        unavailable.setattr(main.BrowserModels, "verify_ref",
                            lambda *_args: (_ for _ in ()).throw(ValueError("offline")))
        app = main.create_application(service.workspace)
        try:
            assert app.requires_model_selection
            assert read_defaults(service.cfg).chat == reference
            with pytest.raises(ValueError, match="Choose a model"):
                app.submit("No silent runtime replacement")
        finally:
            asyncio.run(app.close())
    save_defaults(service.cfg, DefaultsChange("chat", None, reference))
    app = main.create_application(service.workspace)
    try:
        assert app.requires_model_selection
        with pytest.raises(ValueError, match="Choose a model"):
            app.submit("No inference without explicit selection")
    finally:
        asyncio.run(app.close())
    assert not any(path == "/api/chat" for path, _ in calls)
