"""Declared image capabilities, real HTTP adapters and private endpoint continuity."""

import base64
import json
import threading
import time
from copy import deepcopy
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.ai_defaults import DefaultsChange, migrate_defaults, save_defaults
from klaude_core.anthropic_runtime import AnthropicRuntime, catalog_capabilities
from klaude_core.chat_images import ChatImages
from klaude_core.compatible_runtime import CompatibleRuntime
from klaude_core.config import provider_secret_revision, save_provider_secret
from klaude_core.image_content import ANTHROPIC_IMAGE_BYTES, image_parts
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_discovery import discover_connection
from klaude_core.model_runtime import (
    ModelInfo,
    OpenRouterRuntime,
    model_records,
    models_from_records,
)
from klaude_core.settings_store import update_settings

from .test_anthropic import stream, thinking
from .test_library_artifacts import png


@pytest.fixture(params=["openai_compatible", "anthropic"])
def image_lab(tmp_path, request):
    backend = request.param
    calls, mode = [], {"support": True, "value": "good"}
    arrived = threading.Event()

    def entry(model):
        support = mode["support"] if model == "vision" else mode.get("fallback_support", False)
        data = {"id": model, "display_name": model}
        if backend == "anthropic" and mode.get("requires_thinking"):
            data["capabilities"] = {"thinking": {"types": {
                "disabled": {"supported": False}, "adaptive": {"supported": True},
            }}}
        if backend == "openrouter" and "mandatory" in mode:
            data["reasoning"] = {"mandatory": mode["mandatory"]}
        if mode["value"] == "wrong_identity":
            data["id"] = "another-model"
        if support is not None:
            if backend == "anthropic":
                data.setdefault("capabilities", {})["image_input"] = {"supported": support}
            else:
                data["architecture"] = {
                    "input_modalities": ["text", "image"] if support else ["text"],
                    "output_modalities": mode.get("output_modalities", ["text"]),
                }
        return data

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_body(self, body, status=200):
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            calls.append((self.path, {}, dict(self.headers)))
            if mode["value"] == "slow_catalog":
                arrived.set()
                time.sleep(3)
            if self.path.split("?", 1)[0] == "/v1/models":
                value = {"data": [entry("vision"), entry("text")], "has_more": False}
            else:
                value = entry(self.path.rsplit("/", 1)[-1])
            self.send_body(json.dumps(value).encode())

        def do_POST(self):
            packet = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, packet, dict(self.headers)))
            if self.path == "/api/show":
                self.send_body(json.dumps({"capabilities": ["vision"]}).encode())
                return
            arrived.set()
            if mode["value"] == "slow":
                time.sleep(3)
            if packet["model"] == "vision" and mode["value"] in {"401", "503", "529", "429"}:
                self.send_body(b"{}", int(mode["value"]))
                return
            text = ("x" * 300_000 if mode["value"] == "huge_event"
                    else "x" * 32_001 if mode["value"] == "huge_text"
                    else "" if mode["value"] == "empty" else "Observed three colored rectangles.")
            tools = mode["value"] == "tools" and not any(
                m["role"] == "assistant" for m in packet["messages"]
            )
            if backend == "anthropic":
                blocks = (
                    [thinking(), {"type": "tool_use", "id": "c1", "name": "inspect", "input": "{}"}]
                    if tools
                    else [{"type": "text", "text": text}]
                )
                body = stream(
                    blocks,
                    finish="tool_use"
                    if tools
                    else "max_tokens"
                    if mode["value"] == "length"
                    else "end_turn",
                    stop=mode["value"] != "incomplete",
                )
            else:
                delta = (
                    {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {"name": "inspect", "arguments": "{}"},
                            }
                        ]
                    }
                    if tools
                    else {"content": text}
                )
                finish = (
                    "tool_calls" if tools else "length" if mode["value"] == "length" else "stop"
                )
                event = {
                    "choices": [{"delta": delta, "finish_reason": finish}],
                    "usage": {"prompt_tokens": 19, "completion_tokens": 9},
                }
                if backend == "openrouter" and mode.get("reasoning_details"):
                    event["choices"][0]["delta"]["reasoning_details"] = mode["reasoning_details"]
                if mode["value"] == "incomplete":
                    event["choices"][0]["finish_reason"] = None
                body = ("data: " + json.dumps(event) + "\n\n").encode()
                if mode["value"] != "incomplete":
                    body += b"data: [DONE]\n\n"
            self.send_body(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "vision"},
        ollama_url="http://127.0.0.1:1",
    )
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    connection = ModelConnection(
        "image", "Image endpoint", backend, url + "/v1", key_env="IMAGE_FIXTURE_KEY"
    )
    registry.add(connection)
    save_provider_secret(cfg.config_dir, "IMAGE_FIXTURE_KEY", "fixture-private-key")
    credentials = provider_secret_revision(cfg.config_dir, connection.key_env)
    migrate_defaults(cfg)
    save_defaults(cfg, DefaultsChange("vision_enabled", True, False))
    runtime = (
        AnthropicRuntime(connection.base_url, "fixture-private-key", model="vision")
        if backend == "anthropic"
        else OpenRouterRuntime("fixture-private-key", base_url=connection.base_url)
        if backend == "openrouter"
        else CompatibleRuntime(connection.base_url, "fixture-private-key")
    )
    info = ModelInfo(
        backend,
        "vision",
        "Vision",
        connection_id=connection.id,
        connection_revision=connection.revision,
        credential_revision=credentials,
        connection_source="Local",
    )
    agent = Agent(
        runtime,
        "vision",
        [],
        PermissionGate({}, lambda *_: "n"),
        "Describe supplied pixels.",
        model_info=info,
        ollama_options={"num_ctx": 8192, "num_predict": 128},
    )
    agent.image_context = ChatImages(cfg, agent)
    agent.workdir = tmp_path
    source = tmp_path / "input.png"
    source.write_bytes(png())
    yield cfg, connection, agent, source, calls, mode, arrived
    runtime.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def compose(lab):
    return lab[2].image_context.compose("Describe the attachment", (lab[3],), "image-chat")


@pytest.mark.parametrize("image_lab", ["anthropic"], indirect=True)
def test_capability_metadata_must_identify_the_selected_model(image_lab):
    image_lab[5]["value"] = "wrong_identity"
    with pytest.raises(ValueError, match="different model"):
        compose(image_lab)
    assert not [p for _, p, _ in image_lab[4] if "messages" in p]


def pixel_blocks(lab, packet):
    if lab[1].backend == "anthropic":
        return [
            b["source"]["data"]
            for m in packet["messages"]
            for b in m["content"]
            if b["type"] == "image"
        ]
    return [
        b["image_url"]["url"].split(",", 1)[1]
        for m in packet["messages"]
        if isinstance(m.get("content"), list)
        for b in m["content"]
        if b["type"] == "image_url"
    ]


def test_real_image_request_and_catalog_metadata_survive_private_restore(image_lab):
    cfg, connection, agent, source, calls, *_ = image_lab
    discovered = discover_connection(connection, "fixture-private-key")
    assert (
        next(m for m in discovered if m.model_id == "vision").capabilities.supports_images is True
    )
    assert next(m for m in discovered if m.model_id == "text").capabilities.supports_images is False
    assert models_from_records(model_records(discovered)) == discovered
    value = compose(image_lab)
    assert all(path not in {"/v1/messages", "/v1/chat/completions"} for path, *_ in calls)
    events = list(agent.run(value))
    assert not [e for e in events if e.kind == "error"]
    packet = [p for _, p, _ in calls if "messages" in p][-1]
    assert [base64.b64decode(x) for x in pixel_blocks(image_lab, packet)] == [png()]
    assert "image_inputs" not in str(packet) and "image_content" not in str(packet)
    if connection.backend == "anthropic":
        assert packet["messages"][-1]["content"][0]["type"] == "image"
        assert calls[-1][2]["x-api-key"] == "fixture-private-key"
        assert "Authorization" not in calls[-1][2]
    else:
        assert calls[-1][2]["Authorization"] == "Bearer fixture-private-key"
        assert "think" not in packet and "num_ctx" not in packet
    source.unlink()
    agent.restore_session([{"role": "user", "content": "Image question", "model_content": value}])
    events = list(agent.run("Describe it again"))
    assert not [e for e in events if e.kind == "error"]
    packet = [p for _, p, _ in calls if "messages" in p][-1]
    assert pixel_blocks(image_lab, packet)
    assert agent.last_turn_capabilities["input_modalities"]["image_count"] == 1
    assert not (cfg.data_dir / "sessions.db").exists()


@pytest.mark.parametrize("support", [None, False])
def test_unknown_or_false_capability_cannot_save_or_send_pixels(image_lab, support):
    _, _, agent, _, calls, mode, _ = image_lab
    mode["support"] = support
    with pytest.raises(ValueError, match="declare image support"):
        compose(image_lab)
    assert not agent.image_context.store.path.exists()
    assert not any("messages" in p for _, p, _ in calls)


@pytest.mark.parametrize("change", ["definition", "credential", "runtime", "adapter"])
def test_changed_endpoint_credentials_or_transport_fail_before_pixels(image_lab, change):
    cfg, connection, agent, _, calls, *_ = image_lab
    if change == "definition":
        update_settings(
            connection_registry(cfg).path, {("connections", connection.id, "name"): "Edited"}
        )
    elif change == "credential":
        save_provider_secret(cfg.config_dir, connection.key_env, "new-fixture-key")
    elif change == "runtime":
        agent.runtime.base_url = "http://127.0.0.1:1/v1"
    else:
        agent.model_info = replace(agent.model_info, backend="deepseek")
    with pytest.raises(ValueError):
        compose(image_lab)
    assert calls == [] and not agent.image_context.store.path.exists()


def test_native_tool_pairs_and_signed_thinking_survive_images(image_lab):
    _, connection, agent, _, calls, mode, _ = image_lab
    executed = []
    tool = Tool(
        "inspect", "Inspect", {"type": "object"}, lambda: executed.append(True) or "Actual result"
    )
    agent.tools = {"inspect": tool}
    agent.gate.policies["inspect"] = "allow"
    agent.tool_selector = lambda *_: ["inspect"]
    mode["value"] = "tools"
    events = list(agent.run(compose(image_lab)))
    assert executed == [True] and not [e for e in events if e.kind == "error"]
    packets = [p for _, p, _ in calls if "messages" in p]
    assert len(packets) == 2 and all(len(pixel_blocks(image_lab, p)) == 1 for p in packets)
    if connection.backend == "anthropic":
        assert packets[-1]["messages"][-2]["content"][0] == thinking()
        assert packets[-1]["messages"][-1]["content"][0]["type"] == "tool_result"
        assert "private-reasoning-canary" not in str(
            [e.payload for e in events if e.kind == "text"]
        )
    else:
        assert packets[-1]["messages"][-1]["tool_call_id"] == "c1"
        assert packets[-1]["messages"][-2]["tool_calls"][0]["id"] == "c1"


@pytest.mark.parametrize("failure", ["incomplete", "length", "401"])
def test_image_generation_failure_never_changes_model_or_claims_success(image_lab, failure):
    _, _, agent, _, calls, mode, _ = image_lab
    mode["value"] = failure
    events = list(agent.run(compose(image_lab)))
    assert any(e.kind == "error" for e in events)
    assert all(p["model"] == "vision" for _, p, _ in calls if "messages" in p)


@pytest.mark.parametrize("stage", ["slow", "slow_catalog"])
def test_image_transport_cancel_wakes_before_headers(image_lab, stage):
    _, _, agent, _, _, mode, arrived = image_lab
    value = compose(image_lab) if stage == "slow" else None
    mode["value"] = stage
    if stage == "slow_catalog":
        agent.image_context.checked = None
    cancelled, failures = threading.Event(), []
    agent.cancellation_check = cancelled.is_set

    def work():
        try:
            list(agent.run(value)) if value is not None else compose(image_lab)
        except Exception as exc:
            failures.append(type(exc).__name__)

    worker = threading.Thread(target=work)
    worker.start()
    assert arrived.wait(2)
    cancelled.set()
    assert agent.cancel_active_transports()
    worker.join(2)
    assert not worker.is_alive()
    if value is None:
        assert failures and not agent.image_context.store.path.exists()


def test_cancelling_historical_image_inspection_never_starts_generation(image_lab):
    _, _, agent, _, calls, mode, arrived = image_lab
    value = compose(image_lab)
    agent.restore_session([{"role": "user", "content": "Old image", "model_content": value}])
    agent.image_context.checked = None
    mode["value"] = "slow_catalog"
    cancelled = threading.Event()
    agent.cancellation_check = cancelled.is_set
    worker = threading.Thread(target=lambda: list(agent.run("Look at the old pixels again")))
    worker.start()
    assert arrived.wait(2)
    cancelled.set()
    agent.cancel_active_transports()
    worker.join(2)
    assert not worker.is_alive() and not any("messages" in p for _, p, _ in calls)


@pytest.mark.parametrize("image_lab", ["openai_compatible"], indirect=True)
def test_explicit_native_peer_supplies_unknown_compatible_capability(image_lab):
    cfg, connection, agent, _, calls, mode, _ = image_lab
    mode["support"] = None
    peer = ModelConnection("peer", "Known native peer", "ollama", connection.base_url)
    peer = replace(peer, key_env=connection.key_env)
    connection_registry(cfg).add(peer)
    value = compose(image_lab)
    assert value["image_inputs"]
    assert any(path == "/api/show" for path, *_ in calls)
    assert agent.image_context.checked["evidence"] == "configured-ollama-peer:api/show"
    assert not any("messages" in p for _, p, _ in calls)


@pytest.mark.parametrize("image_lab", ["openai_compatible"], indirect=True)
def test_false_compatible_declaration_is_not_overridden_by_native_peer(image_lab):
    cfg, connection, _, _, calls, mode, _ = image_lab
    mode["support"] = False
    connection_registry(cfg).add(
        ModelConnection(
            "peer", "Known peer", "ollama", connection.base_url, key_env=connection.key_env
        )
    )
    with pytest.raises(ValueError):
        compose(image_lab)
    assert all(path != "/api/show" for path, *_ in calls)


def test_endpoint_switch_requires_new_snapshot_authorization(image_lab):
    _, _, agent, _, _, _, _ = image_lab
    value = compose(image_lab)
    messages = [
        {"role": "user", "content": "Old", "image_inputs": value["image_inputs"]},
        {"role": "user", "content": "Follow up"},
    ]
    snapshot = deepcopy(messages)
    agent.runtime.api_key = "different-key"
    projected, count = agent.image_context.project(messages)
    assert count == 0 and all("image_content" not in m for m in projected)
    assert messages == snapshot


@pytest.mark.parametrize("image_lab", ["anthropic"], indirect=True)
def test_anthropic_size_limit_is_applied_before_snapshot_save(image_lab):
    _, connection, agent, source, _, _, _ = image_lab
    source.write_bytes(png() + b"x" * ANTHROPIC_IMAGE_BYTES)
    with pytest.raises(ValueError, match="7,500,000"):
        compose(image_lab)
    assert not agent.image_context.store.path.exists()


def test_malformed_capability_is_never_promoted_to_supported():
    for value in ("true", 1, None, []):
        with pytest.raises(ValueError):
            catalog_capabilities({"capabilities": {"image_input": {"supported": value}}})
    assert catalog_capabilities({}).supports_images is None


@pytest.mark.parametrize("role", ["system", "assistant", "tool"])
def test_neutral_images_cannot_be_attached_to_non_user_roles(role):
    with pytest.raises(ValueError):
        image_parts(
            {
                "role": role,
                "image_content": [
                    {
                        "type": "image",
                        "mime_type": "image/png",
                        "data": base64.b64encode(png()).decode(),
                    }
                ],
            }
        )
