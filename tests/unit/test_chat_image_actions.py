"""Conversational images: real bridge/worker/storage, recording diffusion fixture."""

import asyncio
import json
import time
import uuid

import pytest
from klaude_application.chat_image_actions import image_intent
from klaude_core import image_generation as generation

from .test_image_generation import generation_lab as generation_lab
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def image_chat(profile_browser, generation_lab):
    host, service, _, auth = profile_browser
    _, url, caps, calls, state = generation_lab
    caps["features_by_mode"]["img_gen"]["init_image"] = True
    generation.save(
        service.cfg,
        {"endpoint": url, "enabled": True, "model": "local-test-model"},
        generation.read(service.cfg)["revision"],
    )
    return host, service, auth, calls, state


def finish(handle):
    assert asyncio.run(handle.join(timeout=20))
    assert handle.failure is None, handle.failure


def action(app):
    return next(
        message["image_action"]
        for message in reversed(app.snapshot()["messages"])
        if message.get("image_action")
    )


@pytest.mark.parametrize(
    "text",
    [
        "Explain how Stable Diffusion works",
        "Write an image prompt for a forest",
        "Find images of Phnom Penh",
        "Analyze this screenshot",
        "Make an SVG icon component",
        "Do not generate an image yet",
        "Build an HTML image gallery",
    ],
)
def test_intent_negatives(text):
    assert image_intent(text, True) is None


def test_intent_parameters_and_localized_edit():
    request = image_intent("Generate three images of a city, 16:9, 8 steps seed 42")
    assert request["count"] == 3 and request["width"] == 1024 and request["height"] == 576
    assert request["steps"] == 8 and request["seed"] == 42
    assert image_intent("Make it darker") is None
    assert image_intent("Change only the sky", True).get("clarify")
    assert image_intent("Why can't you generate an image?") is None
    assert image_intent("Draw a cat")["operation"] == "generate"


def test_explicit_skill_image_request_does_not_bypass_the_agent(image_chat):
    from types import SimpleNamespace

    from klaude_core import Tool

    from .test_application_bridge import ScriptedRuntime

    host, _, _, calls, _ = image_chat
    app = host.application
    reads = []
    app.agent.skill_reader = SimpleNamespace(catalog=lambda: (
        SimpleNamespace(name="meme-maker", description="Meme instructions"),
    ))
    app.agent.tools["read_skill"] = Tool(
        "read_skill", "Read installed Skill", {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]},
        lambda name: reads.append(name) or "Use a reviewed template; never invent execution.",
    )
    app.agent.gate.policies["read_skill"] = "allow"
    runtime = ScriptedRuntime([
        {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "read_skill", "arguments": {"name": "meme-maker"},
        }}]},
        {"role": "assistant", "content": "The requested Skill needs a template renderer."},
    ])
    app.agent.runtime = app.agent.ollama = runtime
    handle = app.submit("Use the meme maker to generate an image", request_id=uuid.uuid4().hex)
    finish(handle)
    assert runtime.calls == 2 and reads == ["meme-maker"]
    assert not [call for call in calls if call[1] == "/sdcpp/v1/img_gen"]
    assert app.snapshot()["messages"][-1]["content"] == (
        "The requested Skill needs a template renderer."
    )


def test_generation_persists_structured_results_and_deduplicates(image_chat):
    host, service, auth, calls, _ = image_chat
    app = host.application
    identity = uuid.uuid4().hex
    handle = app.submit("Generate an image of an apple", request_id=identity)
    finish(handle)
    assert action(app)["state"] == "completed"
    assert len(action(app)["assets"]) == 1
    assert len([call for call in calls if call[1] == "/sdcpp/v1/img_gen"]) == 1
    assert (
        app.submit("Generate an image of an apple", request_id=identity).turn_id == handle.turn_id
    )
    # Repeated tool execution in that same accepted turn cannot admit a second job.
    same = app.images.reserve(handle, app.client_id, 0, {"prompt": "Duplicate tool reply"})
    assert same["id"] == action(app)["id"]
    app.images.tick()
    assert len([call for call in calls if call[1] == "/sdcpp/v1/img_gen"]) == 1
    status, _, snapshot = _request(host, "GET", "/api/v1/session", **auth)
    assert status == 200
    public = next(m["image_action"] for m in snapshot["messages"] if "image_action" in m)
    assert public == action(app)
    assert public["outputs"] == [{"width": 512, "height": 512}]
    assert public["position"] == 0
    assert str(service.cfg.data_dir) not in json.dumps(public)
    assert "prompt" not in json.dumps(public) and "b64" not in json.dumps(public)
    cursor = app.snapshot()["cursor"].split(":")[0] + ":0"
    assert any(event["kind"] == "image.changed" for event in app.replay(cursor))
    # A fresh application/SQLite connection must deduplicate without its old
    # in-memory request cache or monitor, and reconstruct the same public assets.
    from .test_webhost import _app

    reopened = _app(service.cfg.data_dir)
    reopened.session_id = app.session_id
    reopened.agent.workdir = app.agent.workdir
    reopened.agent.workspace = app.agent.workspace
    reopened.agent.tool_config = service.cfg
    reopened.agent.set_session_context(app.session_id)
    reopened.bind_image_operations(service)
    try:
        replay = reopened.submit("Generate an image of an apple", request_id=identity)
        assert replay.turn_id == handle.turn_id and replay.detached
        assert action(reopened) == action(app)
        assert sum(path == "/sdcpp/v1/img_gen" for _, path, _ in calls) == 1
    finally:
        asyncio.run(reopened.close())


def test_edit_sends_real_source_and_retains_lineage(image_chat):
    host, service, _, calls, _ = image_chat
    app = host.application
    finish(app.submit("Generate an image of an apple"))
    parent = action(app)["assets"][0]["id"]
    finish(app.submit("Make the last image darker"))
    child = action(app)["assets"][0]["id"]
    assert parent != child
    posts = [body for _, path, body in calls if path == "/sdcpp/v1/img_gen"]
    assert not posts[0].get("init_image") and posts[1]["init_image"]
    assert posts[1]["strength"] == 0.35
    info = service.artifacts.generation_info(child)
    assert info["source"]["id"] == parent and info["user_prompt"] == "Make the last image darker"
    with pytest.raises(ValueError, match="conversation"):
        app.images._source("another-session", "edit", parent)


def test_denied_generation_has_no_side_effect(image_chat):
    host, _, _, calls, _ = image_chat
    host.application.agent.gate.policies["generate_image"] = "deny"
    finish(host.application.submit("Generate an image of an apple"))
    assert not [call for call in calls if call[1] == "/sdcpp/v1/img_gen"]
    assert "denied" in host.application.snapshot()["messages"][-1]["content"]


def test_stop_turn_keeps_job_and_explicit_cancel_is_scoped(image_chat):
    host, _, auth, calls, state = image_chat
    state["wait"] = True
    app = host.application
    handle = app.submit("Generate an image of an apple")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not any(c[1] == "/sdcpp/v1/img_gen" for c in calls):
        time.sleep(0.05)
    handle.cancel()
    finish(handle)
    assert not any(c[1].endswith("/cancel") for c in calls)
    status, _, _ = _request(
        host,
        "POST",
        "/api/v1/chat/images/control",
        body={
            "id": action(app)["id"],
            "operation": "cancel",
            "request_id": uuid.uuid4().hex,
        },
        **auth,
    )
    assert status == 200
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and action(app)["state"] != "cancelled":
        time.sleep(0.1)
    assert action(app)["state"] == "cancelled"
    assert any(c[1] == "/sdcpp/v1/jobs/job_test/cancel" for c in calls)


def wait_for(predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("Condition did not become true")


def test_image_approval_is_required_before_reservation(image_chat):
    host, _, _, calls, _ = image_chat
    app = host.application
    app.allow_approvals = True
    app.agent.gate.policies["generate_image"] = "ask"
    handle = app.submit("Generate an image of an apple")
    wait_for(lambda: app.pending_interactions())
    pending = app.pending_interactions()[0]
    assert pending.tool == "generate_image"
    assert app.images.for_turn(handle.turn_id) is None
    assert not any(path == "/sdcpp/v1/img_gen" for _, path, _ in calls)
    assert app.decide(pending.id, "allow_once")
    finish(handle)
    assert action(app)["state"] == "completed"


def test_model_tool_uses_the_same_durable_executor(image_chat):
    from .test_application_bridge import ScriptedRuntime, _tool_call

    host, _, _, calls, _ = image_chat
    app = host.application
    runtime = ScriptedRuntime([_tool_call("generate_image", prompt="A red apple")])
    app.agent.runtime = app.agent.ollama = runtime
    finish(app.submit("A watercolor please"))
    assert runtime.calls == 1
    assert action(app)["state"] == "completed"
    assert sum(path == "/sdcpp/v1/img_gen" for _, path, _ in calls) == 1


def test_multiple_images_have_ordered_sources_and_missing_source_fails(image_chat):
    host, service, _, calls, _ = image_chat
    app = host.application
    finish(app.submit("Generate two images of an apple"))
    gallery = action(app)["assets"]
    assert len(gallery) == 2
    finish(app.submit("Make the second image darker"))
    child = action(app)["assets"][0]["id"]
    assert service.artifacts.generation_info(child)["source"]["id"] == gallery[1]["id"]
    row = app.images.for_turn(app._active.turn_id)
    source_id = action(app)["assets"][0]["id"]
    # A revision change cannot silently select different pixels.
    item = service.artifacts.get(source_id)
    with service.artifacts.database(write=True) as db:
        db.execute("UPDATE artifacts SET revision=revision+1 WHERE id=?", (source_id,))
    with pytest.raises(ValueError, match="changed"):
        generation.source_pixels(
            service.cfg,
            {"id": source_id, "revision": item["revision"], "sha256": item["sha256"]},
            app.session_id,
        )
    assert row["state"] == "completed"
    assert sum(path == "/sdcpp/v1/img_gen" for _, path, _ in calls) == 3


def test_attached_image_is_snapshotted_and_used_for_edit(image_chat):
    from klaude_application.chat_attachments import ChatAttachment, ChatAttachmentInput

    host, service, _, calls, _ = image_chat
    app = host.application
    finish(app.submit("Generate an image of an apple"))
    asset = action(app)["assets"][0]
    pixels = service.artifacts.read_content(asset["id"], asset["revision"])
    attachment = ChatAttachmentInput(
        (ChatAttachment("source.png", pixels, image=True, mime="image/png"),)
    )
    finish(app.submit("Make it darker", attachments=attachment))
    child = action(app)["assets"][0]["id"]
    parent = service.artifacts.generation_info(child)["source"]["id"]
    assert parent != asset["id"]  # explicit input has its own immutable snapshot
    assert service.artifacts.get(parent)["session"] == app.session_id
    assert [body for _, path, body in calls if path == "/sdcpp/v1/img_gen"][-1]["init_image"]


def test_pixels_survive_a_lost_chat_publication_without_regeneration(image_chat, monkeypatch):
    from klaude_application.chat_image_actions import ChatImageActions

    host, service, _, calls, _ = image_chat
    app = host.application
    original = app.images._update
    monkeypatch.setattr(
        app.images,
        "_update",
        lambda row, state, **kw: False if state == "completed" else original(row, state, **kw),
    )
    handle = app.submit("Generate an image of an apple")
    wait_for(
        lambda: (
            app.images.for_turn(handle.turn_id)
            and service.artifacts.generated_for_job(
                json.loads(app.images.for_turn(handle.turn_id)["specs"])[0]["id"]
            )
        )
    )
    handle.cancel()
    finish(handle)
    app.images.close()
    replacement = ChatImageActions(service.cfg, app.memory, app.turns, app.agent.workdir)
    replacement.operations = service
    app.images = replacement
    replacement.tick()
    assert action(app)["state"] == "completed"
    replacement.tick()
    assert sum(path == "/sdcpp/v1/img_gen" for _, path, _ in calls) == 1


def test_uncertain_admission_and_resume_never_blindly_resubmit(image_chat, monkeypatch):
    host, _, _, calls, _ = image_chat
    app = host.application
    monkeypatch.setattr(app.images, "start", lambda: None)
    handle = app.submit("Generate an image of an apple")
    wait_for(lambda: app.images.for_turn(handle.turn_id))
    row = app.images.for_turn(handle.turn_id)
    assert app.images._update(row, "starting")
    with app.memory._db_lock, app.memory.db:
        app.memory.db.execute(
            "UPDATE application_image_actions SET lease=0 WHERE id=?", (row["id"],)
        )
    handle.cancel()
    finish(handle)
    app.images.tick()
    assert action(app)["state"] == "unknown"
    for _ in range(3):
        app.images.tick()
        app.snapshot()
    assert not any(path == "/sdcpp/v1/img_gen" for _, path, _ in calls)
    with pytest.raises(ValueError, match="original image outcome"):
        app.submit("Generate an image of an apple", _retry_source_row_id=row["message_row"])
    with pytest.raises(ValueError, match="conversation"):
        app.images.control(row["id"], "other-session", "cancel")


def test_cancel_before_native_acknowledgement_is_retained(image_chat, monkeypatch):
    host, _, _, calls, _ = image_chat
    app = host.application
    monkeypatch.setattr(app.images, "start", lambda: None)
    handle = app.submit("Generate an image of an apple")
    wait_for(lambda: app.images.for_turn(handle.turn_id))
    row = app.images.for_turn(handle.turn_id)
    spec = json.loads(row["specs"])[0]
    assert app.images._update(row, "running", operation_id=spec["id"])
    result = app.images.control(row["id"], app.session_id, "cancel")
    assert result["state"] == "cancelling"
    assert not any(path.endswith("/cancel") for _, path, _ in calls)
    assert not any(path == "/sdcpp/v1/img_gen" for _, path, _ in calls)
    handle.cancel()
    finish(handle)


def test_backend_failure_is_terminal_but_invalid_output_remains_unknown(image_chat):
    host, _, _, calls, state = image_chat
    app = host.application
    state["failed"] = True
    finish(app.submit("Generate an image of an apple"))
    assert action(app)["state"] == "failed"
    state["failed"], state["bad_image"] = False, True
    finish(app.submit("Generate an image of a tree"))
    assert action(app)["state"] == "unknown"
    assert not action(app)["assets"]
    for _ in range(3):
        app.images.tick()
    assert sum(path == "/sdcpp/v1/img_gen" for _, path, _ in calls) == 2


def test_plan_mode_never_uses_the_image_fast_path(image_chat):
    host, _, _, calls, _ = image_chat
    app = host.application
    app.agent.plan_mode = True
    finish(app.submit("Generate an image of an apple"))
    assert not any(path == "/sdcpp/v1/img_gen" for _, path, _ in calls)
    assert not any(message.get("image_action") for message in app.snapshot()["messages"])


def test_cancel_racing_with_queue_admission_keeps_the_intent(image_chat, monkeypatch):
    host, _, _, calls, _ = image_chat
    app = host.application
    monkeypatch.setattr(app.images, "start", lambda: None)
    handle = app.submit("Generate an image of an apple")
    wait_for(lambda: app.images.for_turn(handle.turn_id))
    row = app.images.for_turn(handle.turn_id)
    original = app.images._update
    raced = False

    def update(current, state, **kwargs):
        nonlocal raced
        if state == "cancelled" and not raced:
            raced = True
            assert original(current, "starting")
        return original(current, state, **kwargs)

    monkeypatch.setattr(app.images, "_update", update)
    result = app.images.control(row["id"], app.session_id, "cancel")
    assert raced and result["state"] == "cancelling"
    assert not any(path == "/sdcpp/v1/img_gen" for _, path, _ in calls)
    handle.cancel()
    finish(handle)
