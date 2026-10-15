"""Declared OpenRouter images retain the same approval, recovery and private Media contracts."""

from types import SimpleNamespace

import pytest
from klaude_core.ai_defaults import read_defaults
from klaude_core.compatible_runtime import CompatibleModelError
from klaude_core.model_discovery import discover_connection
from klaude_core.model_runtime import OpenRouterRuntime, discover_openrouter_models
from klaude_core.openrouter_images import OpenRouterImages

from . import test_chat_image_providers as providers
from . import test_vision_http as media

image_lab = providers.image_lab


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_declared_catalog_and_complete_chat_image_with_private_restore(image_lab):
    cfg, conn, agent, source, calls, *_ = image_lab
    models = discover_connection(conn, "fixture-private-key")
    assert next(m for m in models if m.model_id == "vision").capabilities.supports_images is True
    assert next(m for m in models if m.model_id == "text").capabilities.supports_images is False
    prepared = providers.compose(image_lab)
    events = list(agent.run(prepared))
    assert not [e for e in events if e.kind == "error"]
    source.unlink()
    stored = [{"role": "user", "content": prepared["request"], "model_content": prepared},
              {"role": "assistant", "content": "Earlier description"}]
    agent.restore_session(stored)
    events = list(agent.run("Look at the pixels again."))
    assert not [e for e in events if e.kind == "error"]
    packets = [p for _, p, _ in calls if "messages" in p]
    assert len(packets) == 2
    assert all(len(providers.pixel_blocks(image_lab, p)) == 1 for p in packets)
    assert all(p["reasoning"] == {"enabled": False} for p in packets)
    assert any("input_modalities=image" in path for path, _, _ in calls)
    assert read_defaults(cfg).vision_enabled


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
@pytest.mark.parametrize("case", ["negative", "unknown", "missing_text", "image_only"])
def test_unknown_negative_and_non_text_models_send_no_pixels(image_lab, case):
    mode = image_lab[5]
    if case == "negative":
        mode["support"] = False
    elif case == "unknown":
        mode["support"] = None
    else:
        mode["output_modalities"] = None if case == "missing_text" else ["image"]
    with pytest.raises(ValueError):
        providers.compose(image_lab)
    assert not [p for _, p, _ in image_lab[4] if "messages" in p]


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_reasoning_and_tool_protocol_pairs_survive_image_execution(image_lab):
    from klaude_core import Tool

    _, _, agent, _, calls, mode, _ = image_lab
    details = [{"type": "reasoning.encrypted", "data": "private-signature", "index": 0}]
    mode.update(value="tools", reasoning_details=details)
    ran = []
    agent.tools = {"inspect": Tool("inspect", "", {"type": "object"},
                                    lambda: ran.append(True) or "observed")}
    agent.gate.policies["inspect"] = "allow"
    events = list(agent.run(providers.compose(image_lab)))
    assert ran == [True] and not [e for e in events if e.kind == "error"]
    packets = [p for _, p, _ in calls if "messages" in p]
    assert packets[-1]["messages"][-1]["tool_call_id"] == "c1"
    assert packets[-1]["messages"][-2]["reasoning_details"] == details
    text = [e.payload for e in events if e.kind == "text"]
    assert "private-signature" not in str([
        {k: v for k, v in item.items() if k != "model_message"} for item in text
    ])
    assert text[-1]["model_message"]["openrouter_reasoning_details"] == details


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
@pytest.mark.parametrize("case", ["incomplete", "length", "401"])
def test_image_failure_never_publishes_success_or_switches_model(image_lab, case):
    agent, mode = image_lab[2], image_lab[5]
    mode["value"] = case
    events = list(agent.run(providers.compose(image_lab)))
    assert any(e.kind == "error" for e in events)
    assert agent.model_info.backend == "openrouter"


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_private_media_uses_same_reviewed_openrouter_endpoint(image_lab):
    media.test_media_http_pixels_are_private_without_tools_or_chat(image_lab)


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_media_cancel_reaps_the_openrouter_request(image_lab):
    media.test_owned_http_cancel_reaps_worker_without_partial_result(image_lab)


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_image_cancel_wakes_wait_before_headers(image_lab):
    providers.test_image_transport_cancel_wakes_before_headers(image_lab, "slow")


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
@pytest.mark.parametrize("change", ["credential", "definition", "disabled", "artifact", "defaults"])
def test_media_revision_guard_before_openrouter_pixels(image_lab, change):
    media.test_stale_reviews_send_no_pixels(image_lab, change)


@pytest.mark.parametrize("finish", [None, "length", "content_filter"])
@pytest.mark.parametrize("streaming", [True, False])
def test_sdk_text_path_never_releases_tools_or_reasoning_without_success(
    monkeypatch, finish, streaming,
):
    runtime = OpenRouterRuntime("fixture-key")
    event = {"choices": [{"finish_reason": finish, "delta": {
        "reasoning_details": [{"type": "reasoning.text", "text": "private"}],
        "tool_calls": [{"index": 0, "id": "c", "function": {"name": "inspect", "arguments": "{}"}}],
    }}]}
    monkeypatch.setattr(runtime, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **_: iter([event])))))
    emitted = []
    with pytest.raises(RuntimeError):
        if streaming:
            for part in runtime.chat_stream("any", []):
                emitted.append(part)
        else:
            runtime.chat("any", [])
    assert not emitted


def test_legacy_sdk_catalog_retains_explicit_images_without_guessing(monkeypatch):
    entries = [{"id": "unknown/arbitrary", "architecture": {
        "input_modalities": ["image", "text"], "output_modalities": ["text"]}},
        {"id": "vision-name-only", "architecture": {"output_modalities": ["text"]}}]
    monkeypatch.setattr(OpenRouterRuntime, "_client", lambda _: SimpleNamespace(
        models=SimpleNamespace(list=lambda: entries)))
    found = discover_openrouter_models("fixture-key")
    assert next(m for m in found if m.model_id == "unknown/arbitrary").capabilities.supports_images
    unknown = next(m for m in found if m.model_id == "vision-name-only")
    assert unknown.capabilities.supports_images is None


def test_private_reasoning_is_bounded_before_publication():
    runtime = OpenRouterImages("http://127.0.0.1:1", "fixture-key")
    try:
        with pytest.raises(CompatibleModelError, match="bound"):
            runtime._private_delta({"reasoning_details": [{"data": "x" * 256_001}]}, {})
    finally:
        runtime.close()


def test_unverified_openrouter_runtime_rejects_raw_images_before_network():
    runtime = OpenRouterRuntime("fixture-key", base_url="http://127.0.0.1:1/v1")
    with pytest.raises(RuntimeError, match="not been verified"):
        list(runtime.chat_stream("vision", [{"role": "user", "content": "", "image_content": []}]))
    assert runtime._image_transport is None


def test_large_bounded_catalog_does_not_use_stream_event_limit():
    import httpx
    from klaude_core.vision import VisionHTTP

    payload = {"data": [{"id": "image", "description": "x" * 300_000}]}
    client = VisionHTTP("http://fixture", trust_env=False)
    client._chat_client_factory = lambda: httpx.Client(
        base_url="http://fixture", transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=payload)))
    try:
        assert client.request("/models", method="GET") == payload
    finally:
        client.close()


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_mandatory_reasoning_cannot_be_silently_disabled(image_lab):
    image_lab[5]["mandatory"] = True
    with pytest.raises(ValueError, match="requires Thinking"):
        media.reviewed(image_lab)
    with pytest.raises(ValueError, match="requires Thinking"):
        providers.compose(image_lab)
    image_lab[2].reasoning_mode = "thinking"
    assert providers.compose(image_lab)["image_inputs"]
    assert not [p for _, p, _ in image_lab[4] if "messages" in p]
