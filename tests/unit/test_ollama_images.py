"""Ollama image capabilities, bounded streams and non-replayable outcomes."""

import base64
import json
import struct
import uuid
import zlib
from types import SimpleNamespace

import httpx
import pytest
from klaude_application.browser_jobs import image_capabilities, prepare_generated_operation
from klaude_core import image_generation as gen


def png(width=512, height=512):
    def part(kind, content):
        return (
            struct.pack(">I", len(content))
            + kind
            + content
            + struct.pack(">I", zlib.crc32(kind + content))
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + part(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + part(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0" * width) * height))
        + part(b"IEND", b"")
    )



@pytest.fixture
def ollama(tmp_path, monkeypatch):
    cfg = SimpleNamespace(config_dir=tmp_path / "config", data_dir=tmp_path / "data")
    state = {"capabilities": ["image"], "digest": "sha256:installed", "events": None}
    calls = []

    def request(req):
        calls.append((req.url.path, json.loads(req.content) if req.content else None))
        if req.url.path == "/api/show":
            return httpx.Response(200, json={"capabilities": state["capabilities"]})
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": "x/image:latest", "digest": state["digest"]},
            ]})
        assert req.url.path == "/api/generate"
        events = state["events"]
        if events is None:
            events = [{"completed": 1, "total": 2, "done": False}, {
                "image": base64.b64encode(png()).decode(), "done": True,
            }]
        return httpx.Response(200, content=b"".join(json.dumps(e).encode() + b"\n" for e in events))

    client = httpx.Client
    transport = httpx.MockTransport(request)
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client(transport=transport, **kwargs))
    gen.save(cfg, {"enabled": True, "endpoint": "http://localhost:11434",
                   "provider": "ollama", "model": "x/image"}, "")
    return cfg, state, calls


def test_ollama_review_and_save_use_installed_image_model(ollama):
    cfg, _, calls = ollama
    caps = image_capabilities(cfg)
    assert caps["available"] and caps["backend"] == "Ollama (experimental)"
    assert "cannot recover" in caps["cancellation_notice"]
    request, _, summary = prepare_generated_operation(cfg, {
        "operation": "image-generate", "prompt": "A fox", "width": 512,
        "height": 512, "steps": 2, "seed": 42,
    })
    assert "cannot recover" in summary
    assert not any(path == "/api/generate" for path, _ in calls)
    spec = request["spec"]
    result = gen.run(cfg, spec)
    assert result["status"] == "complete" and result["artifact"]
    submitted = [body for path, body in calls if path == "/api/generate"]
    assert submitted == [{"model": "x/image", "prompt": "A fox", "stream": True,
                          "width": 512, "height": 512, "steps": 2, "options": {"seed": 42}}]
    assert gen.history(cfg)["items"][0]["recoverable"] is False
    assert gen.cancel(cfg, spec["id"])["status"] == "complete"
    with pytest.raises(ValueError, match="already accepted"):
        gen.run(cfg, spec)
    assert sum(path == "/api/generate" for path, _ in calls) == 1


def test_ollama_rejects_vision_only_and_changed_digest(ollama):
    cfg, state, calls = ollama
    state["capabilities"] = ["vision", "completion"]
    with pytest.raises(ValueError, match="does not advertise image"):
        gen.prepare(cfg, "A fox")
    state["capabilities"] = ["image"]
    spec = gen.prepare(cfg, "A fox")
    state["digest"] = "sha256:replacement"
    with pytest.raises(ValueError, match="capabilities changed"):
        gen.run(cfg, spec)
    assert not any(path == "/api/generate" for path, _ in calls)


@pytest.mark.parametrize("events", [
    [{"done": False}], [{"done": True}], [{"error": "private provider error"}],
    [{"done": True, "image": "invalid base64"}],
    [{"done": True, "image": base64.b64encode(png(256, 256)).decode()}],
])
def test_ollama_failed_stream_never_replays_or_offers_fake_recovery(ollama, events):
    cfg, state, calls = ollama
    state["events"] = events
    spec = gen.prepare(cfg, "A fox")
    with pytest.raises(ValueError):
        gen.run(cfg, spec)
    assert gen.job(cfg, spec["id"])["status"] == "unknown"
    before = len(calls)
    assert gen.cancel(cfg, spec["id"])["recoverable"] is False
    with pytest.raises(ValueError, match="no generation job lookup"):
        gen.refresh(cfg, spec["id"])
    with pytest.raises(ValueError, match="cannot recover"):
        gen.recovery_review(cfg, spec["id"])
    assert len(calls) == before
    assert sum(path == "/api/generate" for path, _ in calls) == 1


def test_ollama_stream_byte_limit(ollama, monkeypatch):
    cfg, state, _ = ollama
    state["events"] = [{"image": "x" * 100, "done": True}]
    monkeypatch.setattr(gen, "RESULT_LIMIT", 50)
    spec = gen.prepare(cfg, "A fox")
    with pytest.raises(ValueError, match="byte or time limit"):
        gen.run(cfg, spec)
    assert gen.job(cfg, spec["id"])["status"] == "unknown"


def test_ollama_browser_settings_keep_provider_through_journaled_save(ollama):
    from klaude_application.browser_media_settings import prepare_media_setting
    from klaude_application.image_generation import ImageGenerationCommand

    cfg, _, calls = ollama
    prepared, _, _ = prepare_media_setting(cfg, {
        "operation": "image-settings-save", "enabled": True,
        "endpoint": "http://localhost:11434", "provider": "ollama", "model": "x/image",
        "revision": gen.read(cfg)["revision"],
    })
    result = ImageGenerationCommand.for_client(
        cfg, "save", settings=prepared["candidate"], revision=prepared["revision"],
        request_id=uuid.uuid4().hex, owner_id="web-admin",
    ).execute()
    assert result["settings"]["provider"] == "ollama"
    assert gen.read(cfg) == result["settings"]
    assert not any(path == "/api/generate" for path, _ in calls)
