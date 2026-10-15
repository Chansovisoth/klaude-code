"""Actual agent-loop admission and typed provider failures, without paid generation."""

import base64
import io
import json
import queue
from dataclasses import replace

import httpx
import pytest
from klaude_cli.background_jobs import OwnedBackgroundJobs
from klaude_cli.main import _agent_model_metadata, _public_model_metadata, _select_tool_names
from klaude_core.agent import _needs_full_product_context
from klaude_core.chat_images import attachment_path, image_request_text
from klaude_core.compatible_runtime import provider_error
from klaude_core.openrouter_images import OpenRouterImages
from PIL import Image

from .test_chat_image_providers import image_lab as image_lab


def large_source(lab):
    stream = io.BytesIO()
    Image.new("RGB", (864, 1184), "orange").save(stream, format="PNG")
    lab[3].write_bytes(stream.getvalue())
    return lab[2].image_context.compose("Describe this image", (lab[3],), "session")


def install_transport(lab, handler):
    _, connection, agent, *_ = lab
    runtime = OpenRouterImages(connection.base_url, "fixture-private-key")
    runtime.image_model = "vision"
    runtime._chat_client_factory = lambda: httpx.Client(
        base_url=connection.base_url, transport=httpx.MockTransport(handler)
    )
    agent.runtime._image_transport = runtime


def success():
    event = {
        "model": "fixture/actual-vision",
        "id": "gen-fixture",
        "choices": [{"delta": {"content": "Orange image."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 5},
    }
    return httpx.Response(
        200, content=("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode()
    )


def wire_size(packet):
    image = next(
        part["image_url"]["url"]
        for m in packet["messages"]
        for part in m.get("content", [])
        if isinstance(part, dict) and part.get("type") == "image_url"
    )
    with Image.open(io.BytesIO(base64.b64decode(image.split(",", 1)[1]))) as decoded:
        return decoded.size


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_fresh_cloud_context_metadata_reaches_the_shared_budget(image_lab, monkeypatch):
    import klaude_core.chat_images as images

    agent = image_lab[2]
    agent.model_info = replace(agent.model_info, connection_source="Cloud")
    original = images.inspect_support

    def inspect(*args, **kwargs):
        result = original(*args, **kwargs)
        result["capabilities"]["context_window"] = 200000
        return result

    monkeypatch.setattr(images, "inspect_support", inspect)
    value = large_source(image_lab)
    assert agent.request_context_window == 200000
    assert agent.request_budget.context == 200000
    assert agent.ollama_options["num_ctx"] == 8192
    projected, count = agent.image_context.project(
        [
            {"role": "system", "content": "Policy" * 1500},
            {"role": "user", "content": "Inspect", "image_inputs": value["image_inputs"]},
        ]
    )
    assert count == 1 and projected[-1]["image_content"]


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_typed_context_error_gets_one_smaller_request_and_reports_actual_route(image_lab):
    value = large_source(image_lab)
    packets = []

    def respond(request):
        packets.append(json.loads(request.content))
        if len(packets) == 1:
            return httpx.Response(
                200,
                content=b'data: {"error":{"code":400,"message":"PRIVATE KEY",'
                b'"metadata":{"error_type":"context_length_exceeded"}}}\n\n',
            )
        return success()

    install_transport(image_lab, respond)
    agent = image_lab[2]
    events = list(agent.run(value))
    assert not [e for e in events if e.kind == "error"]
    assert len(packets) == 2
    assert wire_size(packets[1])[0] < wire_size(packets[0])[0]
    assert {p["model"] for p in packets} == {"vision"}
    assert agent.ollama_options["num_ctx"] == 8192
    assert "PRIVATE" not in str(events)
    assert _agent_model_metadata(agent)["routed_model"] == "fixture/actual-vision"


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_local_admission_failure_has_no_stale_usage_and_retry_survives_source_deletion(image_lab):
    value = large_source(image_lab)
    agent = image_lab[2]
    agent.ollama_options["num_ctx"] = 1200
    agent.runtime.last_chat_metadata = {"usage": {"prompt_tokens": 777, "completion_tokens": 10}}
    packets = []
    install_transport(image_lab, lambda request: packets.append(request) or success())
    events = list(agent.run(value))
    assert [e for e in events if e.kind == "error"] and not packets
    assert _agent_model_metadata(agent) == {}
    assert agent.image_context.failed["image_inputs"] == value["image_inputs"]
    image_lab[3].unlink()
    agent.ollama_options["num_ctx"] = 8192
    retry = agent.image_context.compose("try again", (), "session")
    events = list(agent.run(retry))
    assert not [e for e in events if e.kind == "error"] and len(packets) == 1
    assert agent.image_context.failed is None


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_failed_snapshot_restores_privately_without_replaying_partial_success(image_lab):
    value = large_source(image_lab)
    agent = image_lab[2]
    image_lab[3].unlink()
    agent.restore_session(
        [
            {"role": "user", "content": "Original", "model_content": value},
            {"role": "system", "content": {"event": "runtime_error"}},
            {"role": "assistant", "content": "Partial output"},
        ]
    )
    retry = agent.image_context.resolve_retry("Please retry.")
    assert retry["image_inputs"] == value["image_inputs"]
    agent.ollama_options["num_ctx"] = 8192
    install_transport(image_lab, lambda _: success())
    assert not [e for e in agent.run(retry) if e.kind == "error"]


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
@pytest.mark.parametrize(
    "case,expected",
    [("quota", 1), ("policy", 1), ("partial", 1), ("transient", 2), ("long_delay", 1)],
)
def test_image_recovery_is_typed_bounded_and_never_retries_partial_output(
    image_lab, case, expected
):
    value = large_source(image_lab)
    packets = []

    def respond(request):
        packets.append(request)
        if len(packets) == 2:
            return success()
        code = {
            "quota": "payment_required",
            "policy": "content_policy_violation",
            "partial": "context_length_exceeded",
            "transient": "provider_unavailable",
            "long_delay": "rate_limit_exceeded",
        }[case]
        error = {"error": {"message": "PRIVATE KEY", "metadata": {"error_type": code}}}
        if case == "long_delay":
            return httpx.Response(429, json=error, headers={"retry-after": "30"})
        prefix = (
            'data: {"choices":[{"delta":{"content":"Partial image answer"}}]}\n\n'
            if case == "partial"
            else ""
        )
        return httpx.Response(
            200, content=(prefix + "data: " + json.dumps(error) + "\n\n").encode()
        )

    install_transport(image_lab, respond)
    events = list(image_lab[2].run(value))
    assert len(packets) == expected
    assert bool([e for e in events if e.kind == "error"]) == (case != "transient")
    assert "PRIVATE KEY" not in str(events)


def test_large_private_background_input_completes_without_returning_keys(tmp_path):
    cfg = {
        "kind": "model_settings_inventory",
        "config_dir": str(tmp_path / "config"),
        "data_dir": str(tmp_path / "data"),
        "ollama_url": "http://localhost:1",
        "roles": {},
        "environment_keys": {"UNUSED_PRIVATE_KEY": "private-canary" * 4000},
    }
    events = queue.Queue()
    jobs = OwnedBackgroundJobs(lambda *event: events.put(event))
    try:
        jobs.submit("large-input", cfg, timeout=8)
        _, (_, _, result, error) = events.get(timeout=10)
        assert not error and isinstance(result, dict)
        assert "private-canary" not in str(result)
    finally:
        jobs.close(wait=True)


def test_only_allowlisted_error_codes_and_usage_metadata_are_public():
    error = provider_error(
        {
            "error": {
                "code": 402,
                "message": "PRIVATE KEY",
                "metadata": {"error_type": "payment_required"},
            }
        }
    )
    assert error.error_type == "payment_required" and error.status_code == 402
    assert "PRIVATE" not in str(error)
    assert _public_model_metadata({"routed_model": "public/model", "secret": "PRIVATE"}) == {
        "routed_model": "public/model"
    }


def test_delivered_image_paths_do_not_select_coding_tools_or_full_product_prompt():
    from klaude_core.agent import Tool

    tools = {
        name: Tool(name, name, {}, lambda: "")
        for name in (
            "read_file",
            "workspace_info",
            "list_dir",
            "run_shell",
            "write_file",
            "query_knowledge",
            "huggingface_search",
        )
    }
    request = 'Name the colors. @"/tmp/workspace/models/BUILD742.webp"'
    refs = [{"name": "BUILD742.webp"}]
    routed = image_request_text(request, refs)
    assert _select_tool_names(routed, tools) == []
    assert not _needs_full_product_context(routed)
    # Image delivery does not suppress explicit coding or text-file requests.
    editing = image_request_text(request + " Fix the project to match it.", refs)
    assert "write_file" in _select_tool_names(editing, tools)
    reading = image_request_text(request + " Read challenge1.md too.", refs)
    assert "read_file" in _select_tool_names(reading, tools)
    assert "challenge1.md" in reading


@pytest.mark.parametrize("delay", ["nan", "inf", "-inf"])
def test_nonfinite_retry_delay_is_not_automatically_retried(delay):
    assert provider_error({}, status=429, retry_after=delay).retry_after is None


@pytest.mark.parametrize("image_lab", ["openrouter"], indirect=True)
def test_crop_from_private_original_survives_source_deletion_without_new_artifact(image_lab):
    value = large_source(image_lab)
    ctx = image_lab[2].image_context
    before = ctx.store.get(value["image_inputs"][0]["id"])
    image_lab[3].unlink()
    path = attachment_path("--crop 10,20,100,200 input.png", image_lab[2].workdir, ctx)
    cropped = ctx.compose("Read this image", (path,), "session")
    assert cropped["image_inputs"][0]["id"] == before["id"]
    assert ctx.store.get(before["id"]) == before
    projected, count = ctx.project(
        [{"role": "user", "content": "Inspect", "image_inputs": cropped["image_inputs"]}]
    )
    assert count == 1
    assert ctx.prepared[-1]["crop"] == [10, 20, 100, 200]
    assert "crop [10, 20, 100, 200]" in projected[-1]["content"]
