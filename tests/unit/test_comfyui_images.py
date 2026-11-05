"""ComfyUI graph ownership, publication, scoped cancellation and non-replay."""

import copy
import io
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest
from klaude_core import comfyui_managed as managed
from klaude_core import image_generation as gen
from PIL import Image


@pytest.fixture
def comfy(tmp_path, monkeypatch):
    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    pid = {"pid": 1234, "birth": "123", "port": 8188}
    remote = str(uuid.uuid4())
    state = {"prompt": None, "status": "success", "tamper": None, "lost": False}
    calls = []
    png = io.BytesIO()
    Image.new("RGB", (512, 512), "blue").save(png, format="PNG")
    evidence = {
        "endpoint": "http://127.0.0.1:8188",
        "model": managed.BUNDLE_ID,
        "provider": "comfyui",
        "server": pid,
        "installation": "verified-fixture",
        "limits": {"min_width": 256, "max_width": 768, "min_height": 256, "max_height": 768},
        "sampler": "euler",
        "scheduler": "normal",
        "cancel_queued": True,
        "cancel_generating": True,
        "img2img": False,
        "revision": "fixture",
    }
    monkeypatch.setattr(managed, "installed", lambda cfg, **kw: {"fixture": True})
    monkeypatch.setattr(managed, "server_record", lambda cfg: pid)
    monkeypatch.setattr(managed, "inspect_bundle", lambda cfg, model, launch=False: evidence)

    def respond(request):
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, path, body))
        if path == "/prompt":
            assert state["prompt"] is None, "An accepted generation was replayed"
            state["prompt"] = body
            if state["lost"]:
                raise httpx.ReadTimeout("private lost acknowledgement")
            return httpx.Response(200, json={"prompt_id": remote, "node_errors": {}})
        if path == f"/history/{remote}":
            if state.get("queue_only"):
                return httpx.Response(200, json={})
            p = state["prompt"]
            item = {
                "prompt": [1, remote, copy.deepcopy(p["prompt"]), {"client_id": p["client_id"]}],
                "status": {
                    "status_str": state["status"],
                    "completed": True,
                    "messages": [["execution_interrupted", {}]],
                },
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": p["client_id"] + "_00001_.png",
                                "subfolder": "klaude",
                                "type": "output",
                            }
                        ]
                    }
                },
            }
            if state["tamper"]:
                state["tamper"](item)
            return httpx.Response(200, json={remote: item})
        if path == "/view":
            assert request.url.params["subfolder"] == "klaude"
            return httpx.Response(200, content=png.getvalue())
        if path == "/queue":
            return httpx.Response(
                200,
                json={
                    "queue_running": [],
                    "queue_pending": [] if state.get("queue_removed") else [[1, remote]],
                },
            )
        if path == f"/api/jobs/{remote}/cancel":
            state["queue_removed"] = True
            state["status"] = "error"
            return httpx.Response(200, json={"cancelled": True})
        raise AssertionError(path)

    original = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original(**kw, transport=httpx.MockTransport(respond))
    )
    gen.save(
        cfg,
        {"enabled": True, "endpoint": "managed", "provider": "comfyui", "model": managed.BUNDLE_ID},
        "",
    )
    return cfg, state, calls, evidence, remote


def test_generation_publishes_one_exact_image_and_never_replays(comfy):
    cfg, state, calls, _, _ = comfy
    spec = gen.prepare(cfg, "A blue cat", negative_prompt="blur", seed=42)
    assert not calls  # Metadata review cannot submit inference.
    result = gen.run(cfg, spec)
    assert result["status"] == "complete" and result["artifact"]
    assert state["prompt"]["prompt"]["7"]["inputs"]["text"] == "blur"
    assert gen.history(cfg)["items"][0]["endpoint"] == "managed"
    assert gen.cancel(cfg, spec["id"])["status"] == "complete"
    with pytest.raises(ValueError, match="already accepted"):
        gen.run(cfg, spec)
    assert sum(path == "/prompt" for _, path, _ in calls) == 1


@pytest.mark.parametrize(
    "tamper",
    [
        lambda item: item["prompt"][3].update(client_id="another-owner"),
        lambda item: item["prompt"][2]["4"]["inputs"].update(ckpt_name="other.safetensors"),
        lambda item: item["outputs"]["9"]["images"][0].update(filename="../private.png"),
        lambda item: item["outputs"]["9"]["images"][0].update(subfolder="another-job"),
        lambda item: item["outputs"]["9"]["images"].append({}),
    ],
)
def test_changed_job_or_output_is_never_fetched_or_published(comfy, tamper):
    cfg, state, calls, _, _ = comfy
    state["tamper"] = tamper
    spec = gen.prepare(cfg, "cat")
    with pytest.raises(ValueError):
        gen.run(cfg, spec)
    assert gen.job(cfg, spec["id"])["status"] == "unknown"
    assert not any(path == "/view" for _, path, _ in calls)


def test_lost_submission_ack_cannot_retry_or_cancel_arbitrary_job(comfy):
    cfg, state, calls, _, _ = comfy
    state["lost"] = True
    spec = gen.prepare(cfg, "cat")
    with pytest.raises(httpx.ReadTimeout):
        gen.run(cfg, spec)
    with pytest.raises(ValueError, match="already accepted"):
        gen.run(cfg, spec)
    with pytest.raises(ValueError, match="invalid job ID"):
        gen.cancel(cfg, spec["id"])
    assert len(calls) == 1


def test_scoped_cancel_and_recover_use_only_saved_job(comfy):
    cfg, state, calls, _, remote = comfy
    spec = gen.prepare(cfg, "cat")
    # Simulate a saved acknowledgement without retrieving/publishing its output.
    from klaude_core.comfyui_images import graph

    state["prompt"] = {"prompt": graph(spec), "client_id": spec["id"]}
    gen.publish(cfg, {**spec, "status": "unknown", "remote_id": remote, "created": 1})
    assert gen.refresh(cfg, spec["id"])["status"] == "completed_remote"
    recovered = gen.recover(cfg, spec["id"], gen.recovery_review(cfg, spec["id"]))
    assert recovered["status"] == "complete"
    assert not any(path == "/prompt" for _, path, _ in calls)
    second = gen.prepare(cfg, "another cat")
    state["prompt"] = {"prompt": graph(second), "client_id": second["id"]}
    gen.publish(cfg, {**second, "status": "unknown", "remote_id": remote, "created": 2})
    assert gen.cancel(cfg, second["id"])["status"] == "cancelled"
    assert ("POST", f"/api/jobs/{remote}/cancel", {}) in calls
    assert not any(
        path in {"/interrupt", "/queue"} and method == "POST" for method, path, _ in calls
    )


def test_changed_server_rejects_control_before_contact(comfy, monkeypatch):
    cfg, state, calls, _, remote = comfy
    spec = gen.prepare(cfg, "cat")
    gen.publish(cfg, {**spec, "status": "unknown", "remote_id": remote, "created": 1})
    monkeypatch.setattr(
        managed, "server_record", lambda cfg: {"pid": 5678, "birth": "999", "port": 8188}
    )
    with pytest.raises(ValueError, match="instance changed"):
        gen.cancel(cfg, spec["id"])
    assert not calls


def test_unknown_remote_job_blocks_runtime_repair_after_worker_exit(comfy):
    cfg, _, calls, _, remote = comfy
    spec = gen.prepare(cfg, "Unconfirmed image")
    gen.publish(cfg, {**spec, "status": "unknown", "remote_id": remote, "created": 1})
    # No worker or shared lock remains, but the durable receipt still protects
    # the remote work from an installer stopping/replacing its engine.
    with pytest.raises(ValueError, match="unfinished ComfyUI jobs"):
        managed.require_idle(cfg)
    assert not calls


def test_private_inspect_uses_managed_profile_and_rejects_external_endpoint(comfy):
    cfg, _, calls, evidence, _ = comfy
    request = {
        "operation": "inspect",
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "provider": "comfyui",
        "endpoint": "managed",
        "model": managed.BUNDLE_ID,
    }
    assert gen.execute(request)["evidence"] == evidence
    request["endpoint"] = "https://arbitrary.invalid"
    assert gen.execute(request)["status"] == "error"
    assert not calls


def test_acknowledged_queued_cancel_is_durable_without_server_history(comfy):
    cfg, state, calls, _, remote = comfy
    spec = gen.prepare(cfg, "Queued request")
    gen.publish(cfg, {**spec, "status": "unknown", "remote_id": remote, "created": 1})
    state["queue_only"] = True
    result = gen.cancel(cfg, spec["id"])
    assert result["status"] == "cancelled" and result["cleanup"] == "Confirmed"
    before = len(calls)
    assert gen.refresh(cfg, spec["id"])["status"] == "cancelled"
    assert len(calls) == before
    assert not any(path == "/prompt" for _, path, _ in calls)
