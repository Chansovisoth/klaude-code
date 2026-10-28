"""Native SD selection uses metadata reads, exact review and one fenced load."""

import copy
import json
import socket
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from klaude_application.image_model_selection import catalog, resource
from klaude_application.operation_journal import OperationConflict
from klaude_core.image_generation import read

from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@contextmanager
def model_server():
    state = {
        "runtime": {"state": "ready", "recipe": None, "models": {},
                    "origin": "command_line", "revision": 1},
        "model": "original-model", "loads": [], "calls": [],
        "files": [
            {"id": "checkpoints/first.safetensors", "name": "First model",
             "category": "checkpoints"},
            {"id": "checkpoints/second.gguf", "name": "Second model", "category": "checkpoints"},
            {"id": "vae/component.safetensors", "name": "Component VAE", "category": "vae"},
        ],
        "recipes": [
            {"id": "sd", "name": "Stable Diffusion", "description": "Checkpoint image model",
             "slots": [{"id": "model", "label": "Checkpoint", "required": True,
                        "categories": ["checkpoints"]}]},
            {"id": "components", "name": "Image model with VAE", "description": "Component setup",
             "slots": [{"id": "model", "label": "Checkpoint", "required": True,
                        "categories": ["checkpoints"]},
                       {"id": "vae", "label": "VAE", "required": False, "categories": ["vae"]}],
             "required_any": [["vae"]]},
        ],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            state["calls"].append(("GET", self.path))
            if self.path.endswith("/models/status"):
                self.reply(state["runtime"])
            elif self.path.endswith("/recipes"):
                self.reply({"recipes": state["recipes"], "errors": []})
            elif self.path.endswith("/model-files"):
                self.reply({"files": state["files"], "errors": []})
            elif self.path.endswith("/capabilities"):
                self.reply({
                    "model": {"name": state["model"]}, "supported_modes": ["img_gen"],
                    "output_formats_by_mode": {"img_gen": ["png"]},
                    "defaults_by_mode": {"img_gen": {"sample_params": {
                        "sample_method": "euler", "scheduler": "discrete"}}},
                    "samplers": ["euler"], "schedulers": ["discrete"],
                    "features_by_mode": {"img_gen": {}},
                    "limits": {"min_width": 256, "max_width": 2048,
                               "min_height": 256, "max_height": 2048},
                })
            else:
                self.reply({}, 404)

        def do_POST(self):
            state["calls"].append(("POST", self.path))
            if self.path == "/sdcpp/v1/models/refresh":
                self.reply({"errors": []})
                return
            assert self.path == "/sdcpp/v1/models/load"
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["loads"].append(value)
            if state.get("reject"):
                self.reply({"error": "Busy", "code": "model_busy"}, 409)
                return
            state["runtime"] = {"state": "ready", "recipe": value["recipe"],
                                "models": {key: item for key, item in value["models"].items()
                                           if item}, "origin": "recipe",
                                "revision": state["runtime"]["revision"] + 1}
            state["model"] = value["models"]["model"].split("/")[-1]
            if state.get("lost"):
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
            else:
                self.reply(state["runtime"])

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def image_browser(profile_browser):
    host, service, _, auth = profile_browser
    with model_server() as (url, state):
        yield host, service, auth, url, state


def draft(service, url, **changes):
    data = catalog(service.cfg, url)
    return {"operation": "image-model-load", "endpoint": url, "recipe": "sd",
            "models": {"model": "checkpoints/second.gguf"},
            "catalog_revision": data["catalog_revision"],
            "runtime_revision": data["runtime_revision"], **changes}


def test_picker_reads_metadata_and_both_review_and_submit_require_admin(image_browser):
    host, service, auth, url, state = image_browser
    api = "/api/v1/settings/models/image-models"
    assert _request(host, "GET", "/api/v1/session", **auth)[2]["image_model_selection"]
    status, _, data = _request(host, "POST", api, body={"endpoint": url}, **auth)
    assert status == 200 and len(data["files"]) == 3 and data["model"] == "original-model"
    assert not state["loads"] and all(method == "GET" for method, _ in state["calls"])
    assert _request(host, "POST", api, body={"endpoint": url, "refresh": True}, **auth)[0] == 200
    assert ("POST", "/sdcpp/v1/models/refresh") in state["calls"] and not state["loads"]
    for fields in ({"endpoint": url, "path": "/tmp/model"}, {"endpoint": "file:///tmp"}):
        assert _request(host, "POST", api, body=fields, **auth)[0] == 400
    assert _request(host, "POST", api, body={"endpoint": url}, origin=host.origin)[0] == 401
    assert _request(host, "POST", api, body={"endpoint": url},
                    **{**auth, "csrf": "invalid"})[0] == 403
    value = draft(service, url)
    review = _review(host, auth, value)
    host.http.host_lan = True
    assert _request(host, "POST", api, body={"endpoint": url}, **auth)[0] == 403
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": value},
                    **auth)[0] == 403
    assert _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": "b" * 32, "control_epoch": 0,
    }, **auth)[0] == 403
    assert not state["loads"]


def test_exact_selection_loads_once_and_saving_defaults_remains_separate(image_browser):
    host, service, auth, url, state = image_browser
    before = read(service.cfg)
    review = _review(host, auth, draft(service, url))
    assert "Second model" in review["summary"] and "Other clients" in review["summary"]
    assert not state["loads"]
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    assert state["loads"] == [{"recipe": "sd", "models": {"model": "checkpoints/second.gguf"}}]
    assert read(service.cfg) == before
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert len(state["loads"]) == 1
    assert not service.journal.resource_busy(resource(url))
    with pytest.raises(ValueError, match="selected image model is not loaded"):
        service.prepare("owner", {
            "operation": "image-settings-save", "endpoint": url, "enabled": True,
            "revision": read(service.cfg)["revision"], "provider": "sdcpp", "model": "other.gguf",
        })


def test_selection_validates_exact_catalog_slots_and_rechecks_before_loading(image_browser):
    host, service, auth, url, state = image_browser
    for value in (
        {"models": {"model": "/tmp/second.gguf"}},
        {"models": {"model": "vae/component.safetensors"}},
        {"models": {"extra": "checkpoints/second.gguf"}},
        {"recipe": "components"}, {"recipe": "@command-line"},
        {"runtime_revision": "stale"},
    ):
        with pytest.raises(ValueError):
            service.prepare("owner", draft(service, url, **value))
    review = _review(host, auth, draft(service, url))
    state["recipes"][0]["description"] = "Changed recipe defaults"
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not state["loads"]
    review = _review(host, auth, draft(service, url))
    state["runtime"]["revision"] += 1
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not state["loads"]


def test_lost_load_ack_stays_fenced_until_exact_read_only_recovery(image_browser):
    host, service, auth, url, state = image_browser
    review = _review(host, auth, draft(service, url))
    state["lost"] = True
    receipt, _ = _submit(host, service, auth, review)
    assert receipt["state"] == "unknown" and len(state["loads"]) == 1
    assert catalog(service.cfg, url)["pending"]["request_id"] == receipt["request_id"]
    with pytest.raises(ValueError):
        service.prepare("owner", draft(service, url))
    recover = {"operation": "image-model-recover", "endpoint": url,
               "target": receipt["request_id"]}
    selection = copy.deepcopy(state["runtime"])
    state["runtime"]["models"] = {"model": "checkpoints/first.safetensors"}
    with pytest.raises(ValueError, match="not confirmed"):
        service.prepare("owner", recover)
    assert service.journal.resource_busy(resource(url))
    state["runtime"] = selection
    recovery = _review(host, auth, recover)
    assert _submit(host, service, auth, recovery)[0]["state"] == "completed"
    assert len(state["loads"]) == 1 and not service.journal.resource_busy(resource(url))
    with pytest.raises((ValueError, OperationConflict)):
        service.prepare("owner", recover)


def test_explicit_busy_rejection_is_terminal_and_empty_catalog_keeps_loaded_choice(image_browser):
    host, service, auth, url, state = image_browser
    state["reject"] = True
    review = _review(host, auth, draft(service, url))
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not service.journal.resource_busy(resource(url))
    state["files"] = []
    data = catalog(service.cfg, url)
    assert data["files"] == [] and data["model"] == "original-model"
