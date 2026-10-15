"""Chat pixels across actual HTTP requests, restore, context and endpoint changes."""

import base64
import json
import threading
import time
from copy import deepcopy
from dataclasses import replace

import httpx
import pytest
from klaude_cli.main import _export_session, _render, _select_tool_names
from klaude_core import Agent, PermissionGate, Tool
from klaude_core.chat_images import ChatImages, image_cost, inline_paths, references, unpack_input
from klaude_core.memory import Memory
from klaude_core.model_runtime import ModelInfo, OllamaRuntime
from klaude_core.ollama import Ollama, OllamaError, _native_messages
from typer import Exit

from .test_library_artifacts import png
from .test_vision import vision_lab as vision_lab


def agent_for(lab):
    cfg, connection, *_ = lab
    runtime = OllamaRuntime(Ollama(cfg.ollama_url, trust_env=False))
    info = ModelInfo(
        "ollama",
        "vision",
        "Vision",
        connection_id=connection.id,
        connection_revision=connection.revision,
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
    agent.workdir = cfg.config_dir.parent
    agent.image_context = ChatImages(cfg, agent)
    return agent


def envelope(lab, agent, name="input.png"):
    return agent.image_context.compose("Describe this attachment", (agent.workdir / name,), "chat")


def test_real_chat_projection_is_pixels_without_binary_text_or_private_refs(vision_lab):
    agent = agent_for(vision_lab)
    _, _, store, _, calls, *_ = vision_lab
    try:
        value = envelope(vision_lab, agent)
        assert len(json.dumps(value)) < 1000
        assert "PNG" not in value["content"] and "pixels are separate" in value["content"]
        observed = []
        agent.capability_observer = observed.append
        events = list(agent.run(value))
        assert not [e for e in events if e.kind == "error"]
        assert any(e.kind == "text" and "rectangles" in e.payload["content"] for e in events)
        sent = next(data for path, data in calls if path == "/api/chat")
        assert base64.b64decode(sent["messages"][-1]["images"][0]) == png()
        assert "1 image pixel inputs" in sent["messages"][0]["content"]
        assert "untrusted data" in sent["messages"][0]["content"]
        assert all("image_inputs" not in m and "image_content" not in m for m in sent["messages"])
        assert all(not m.get("images") for m in agent.messages)
        assert observed[-1]["input_modalities"] == {
            "image_pixels_available": True,
            "image_count": 1,
        }
        assert sum(path == "/api/show" for path, _ in calls) == 1
        stored = store.get(value["image_inputs"][0]["id"])
        assert stored["origin"] == "Chat image attachment" and stored["session"] == "chat"
        assert not stored["tags"] and not stored["archived"]
        assert (agent.workdir / "input.png").read_bytes() == png()
        assert not (vision_lab[0].data_dir / "knowledge").exists()
    finally:
        agent.runtime.close()


def test_private_restore_keeps_snapshot_after_original_removal_and_deduplicates(vision_lab):
    cfg, _, store, *_ = vision_lab
    agent = agent_for(vision_lab)
    memory = Memory(cfg.data_dir / "memory.md", cfg.data_dir / "sessions.db")
    restored = agent_for(vision_lab)
    try:
        value = envelope(vision_lab, agent)
        assert envelope(vision_lab, agent) == value
        items = [i for i in store.listing("media")["items"] if i["session"] == "chat"]
        assert len(items) == 1
        memory.log_turn("chat", "user", "Describe @input.png", model_content=value)
        memory.log_turn("chat", "assistant", "Three colors.")
        public = memory.db.execute("SELECT content FROM turns WHERE session_id='chat'").fetchall()
        assert "image_inputs" not in str(public)
        assert "Chat image attachment" not in str(memory.search_sessions("image_inputs"))
        (agent.workdir / "input.png").unlink()
        restored.restore_session(memory.load_session("chat"))
        events = list(restored.run("Which is the middle color?"))
        assert not [e for e in events if e.kind == "error"]
        sent = [d for path, d in vision_lab[4] if path == "/api/chat"][-1]
        assert any(m.get("images") for m in sent["messages"])
        assert restored.last_turn_capabilities["input_modalities"]["image_count"] == 1
        assert "image_content" not in str(memory.load_session("chat"))
        exported = _export_session(memory, "chat", restored, cfg, "public.md").read_text()
        assert "image_inputs" not in exported and "media:" not in exported
        assert base64.b64encode(png()).decode() not in exported
    finally:
        agent.runtime.close()
        restored.runtime.close()
        memory.db.close()


@pytest.mark.parametrize("change", ["archive", "tags", "delete", "checksum"])
def test_stored_lifecycle_is_honest_and_does_not_rewrite_history(vision_lab, change):
    agent = agent_for(vision_lab)
    store = vision_lab[2]
    try:
        value = envelope(vision_lab, agent)
        ref = value["image_inputs"][0]
        item = store.get(ref["id"])
        if change == "delete":
            item = store.change(item["id"], item["revision"], "archive")
            store.change(item["id"], item["revision"], "delete")
        elif change == "checksum":
            with store.database(write=True) as db:
                db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"corrupt", item["id"]))
        else:
            store.change(item["id"], item["revision"], change, "manual" if change == "tags" else "")
        messages = [
            {"role": "user", "content": "Previous", "image_inputs": [ref]},
            {"role": "assistant", "content": "A picture"},
            {"role": "user", "content": "Follow up"},
        ]
        snapshot = deepcopy(messages)
        projected, count = agent.image_context.project(messages)
        assert messages == snapshot
        assert count == (0 if change in {"delete", "checksum"} else 1)
        if not count:
            assert "not fresh visual evidence" in projected[0]["content"]
            with pytest.raises(ValueError, match="unavailable"):
                agent.image_context.project([messages[0]])
    finally:
        agent.runtime.close()


@pytest.mark.parametrize("switch", ["backend", "endpoint", "credential", "disabled", "text"])
def test_history_pixels_do_not_leak_on_provider_switch_or_disabled_vision(vision_lab, switch):
    agent = agent_for(vision_lab)
    try:
        value = envelope(vision_lab, agent)
        history = [
            {"role": "user", "content": value["content"], "image_inputs": value["image_inputs"]},
            {"role": "user", "content": "Continue"},
        ]
        if switch == "backend":
            agent.model_info = replace(agent.model_info, backend="openai_compatible")
        elif switch == "endpoint":
            agent.runtime.ollama.base_url = "http://127.0.0.1:1"
        elif switch == "credential":
            agent.runtime.ollama.api_key = "different-private-key"
        elif switch == "disabled":
            vision_lab[-1]("vision_enabled", False)
        else:
            agent.model_info = replace(agent.model_info, model_id="text")
        projected, count = agent.image_context.project(history)
        assert count == 0
        assert all(
            not any(k in m for k in ("images", "image_content", "image_inputs")) for m in projected
        )
        assert "pixels omitted" in projected[0]["content"]
        assert history[0]["image_inputs"] == value["image_inputs"]
    finally:
        agent.runtime.close()


def test_same_endpoint_model_switch_retains_approved_pixels(vision_lab):
    agent = agent_for(vision_lab)
    try:
        value = envelope(vision_lab, agent)
        agent.model_info = replace(agent.model_info, model_id="other")
        projected, count = agent.image_context.project(
            [
                {"role": "user", "content": "Old", "image_inputs": value["image_inputs"]},
                {"role": "user", "content": "Continue"},
            ]
        )
        assert count == 1 and projected[0]["image_content"]
    finally:
        agent.runtime.close()


@pytest.mark.parametrize("failure", ["disabled", "text", "provider", "count", "format"])
def test_invalid_new_images_never_generate_or_create_media(vision_lab, failure):
    cfg, _, store, _, calls, *_ = vision_lab
    agent = agent_for(vision_lab)
    try:
        paths = (agent.workdir / "input.png",)
        if failure == "disabled":
            vision_lab[-1]("vision_enabled", False)
        elif failure == "text":
            agent.model_info = replace(agent.model_info, model_id="text")
        elif failure == "provider":
            agent.model_info = replace(agent.model_info, backend="anthropic")
        elif failure == "count":
            paths = tuple(agent.workdir / f"over{n}.png" for n in range(3))
            for source in paths:
                source.write_bytes(png())
        else:
            source = agent.workdir / "wrong.gif"
            source.write_bytes(b"GIF89a" + b"x" * 20)
            paths = (source,)
        before = store.listing("media")
        with pytest.raises(ValueError):
            agent.image_context.compose("Inspect", paths, "chat")
        assert store.listing("media") == before
        assert not any(path == "/api/chat" for path, _ in calls)
        assert read_defaults_enabled(cfg) == (failure != "disabled")
    finally:
        agent.runtime.close()


def read_defaults_enabled(cfg):
    from klaude_core.ai_defaults import read_defaults

    return read_defaults(cfg).vision_enabled


def test_image_context_bound_drops_old_pixels_and_rejects_new_oversize(vision_lab):
    agent = agent_for(vision_lab)
    try:
        value = envelope(vision_lab, agent)
        image_message = {
            "role": "user",
            "content": "Picture",
            "image_inputs": value["image_inputs"],
        }
        assert image_cost(image_message) == 512
        agent.ollama_options["num_ctx"] = 1200
        projected, count = agent.image_context.project(
            [
                image_message,
                {"role": "user", "content": "Follow up"},
            ]
        )
        assert count == 0 and "pixels omitted" in projected[0]["content"]
        with pytest.raises(ValueError, match="allocated context"):
            agent.image_context.project([image_message])
        assert agent.ollama_options["num_ctx"] == 1200
    finally:
        agent.runtime.close()


def test_compaction_counts_images_and_preserves_tool_pairs(vision_lab):
    agent = agent_for(vision_lab)
    try:
        value = envelope(vision_lab, agent)
        ref = {**value["image_inputs"][0], "width": 2048, "height": 2048}
        agent.messages += [
            {"role": "user", "content": "Study this screenshot", "image_inputs": [ref]},
            {"role": "assistant", "content": "Earlier visual description"},
            {"role": "user", "content": "Keep the code correct"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call-1", "function": {"name": "read_file", "arguments": {}}},
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "source code"},
        ]
        agent._compact_history([])
        assert not any(m.get("image_inputs") for m in agent.messages)
        assert "recap text is not visual evidence" in str(agent.messages)
        assert len([m for m in agent.messages if m.get("tool_calls")]) == 1
        assert len([m for m in agent.messages if m.get("role") == "tool"]) == 1
        assert not any(m.get("image_content") for m in agent.messages)
    finally:
        agent.runtime.close()


@pytest.mark.parametrize("field,value", [("mime", []), ("width", True), ("scope", "bad")])
def test_malformed_restored_reference_uses_public_input(vision_lab, field, value):
    agent = agent_for(vision_lab)
    try:
        private = envelope(vision_lab, agent)
        private["image_inputs"][0][field] = value
        with pytest.raises(ValueError):
            unpack_input(private)
        agent.restore_session(
            [{"role": "user", "content": "Public question", "model_content": private}]
        )
        assert agent.messages[-1] == {"role": "user", "content": "Public question"}
    finally:
        agent.runtime.close()


def test_metadata_failure_is_clean_in_one_shot_and_keeps_public_store_empty(vision_lab, capsys):
    cfg = vision_lab[0]
    agent = agent_for(vision_lab)
    memory = Memory(cfg.data_dir / "memory.md", cfg.data_dir / "sessions.db")
    try:
        vision_lab[-1]("vision_enabled", False)
        with pytest.raises(Exit) as error:
            _render(agent, memory, "chat", "Describe @input.png", raise_on_error=True)
        assert error.value.exit_code == 1
        assert "Enable Vision" in capsys.readouterr().out
        assert memory.load_session("chat") == []
    finally:
        memory.db.close()
        agent.runtime.close()


def test_text_and_inline_paths_remain_plain_and_bounded(vision_lab):
    agent = agent_for(vision_lab)
    try:
        file = agent.workdir / "notes with spaces.txt"
        file.write_text("Text-only notes")
        paths = inline_paths('Use @"notes with spaces.txt" and @input.png. x@y.test', agent.workdir)
        assert paths == (file, agent.workdir / "input.png")
        text = agent.image_context.compose("Read notes", (file,), "chat")
        assert isinstance(text, str) and "Text-only notes" in text
        assert references([]) == []
    finally:
        agent.runtime.close()


def test_image_metadata_does_not_route_tools_and_coding_intent_retains_tools(vision_lab):
    agent = agent_for(vision_lab)
    try:
        value = envelope(vision_lab, agent)
        routed = []
        agent.tool_selector = lambda text, _tools: routed.append(text) or []
        list(agent.run(value))
        assert routed[0] == value["request"]
        assert "Attached image" not in routed[0]
        names = ("read_file", "list_dir", "workspace_info", "grep", "write_file", "edit_file")
        tools = {name: Tool(name, name, {"type": "object"}, lambda: "") for name in names}
        assert _select_tool_names("Describe the attached image", tools) == []
        assert {"write_file", "read_file", "edit_file"} <= set(
            _select_tool_names("Implement the screenshot layout in this project", tools)
        )
    finally:
        agent.runtime.close()


def test_latest_two_distinct_snapshots_and_duplicate_inputs_have_a_fixed_bound(vision_lab):
    agent = agent_for(vision_lab)
    try:
        first = envelope(vision_lab, agent)
        duplicate = agent.image_context.compose(
            "Picture", (agent.workdir / "input.png",) * 3, "chat"
        )
        assert len(duplicate["image_inputs"]) == 1
        messages = []
        for n in range(3):
            source = agent.workdir / f"different{n}.png"
            source.write_bytes(png() + bytes([n]))
            value = agent.image_context.compose("Picture", (source,), "chat")
            messages.append(
                {"role": "user", "content": "Picture", "image_inputs": value["image_inputs"]}
            )
        projected, count = agent.image_context.project(messages)
        assert count == 2 and "image_content" not in projected[0]
        assert all(m["image_content"] for m in projected[-2:])
        same = {"role": "user", "content": "Picture", "image_inputs": first["image_inputs"] * 2}
        assert agent.image_context.project([same])[1] == 1
    finally:
        agent.runtime.close()


def test_pixels_survive_tool_results_without_breaking_native_protocol_pairs(vision_lab):
    agent = agent_for(vision_lab)
    sent, reads = [], []

    def native(request):
        packet = json.loads(request.content)
        sent.append(packet)
        message = (
            {
                "tool_calls": [
                    {"function": {"name": "read_file", "arguments": {"path": "notes.txt"}}}
                ]
            }
            if len(sent) == 1
            else {"content": "Inspected notes and supplied image."}
        )
        return httpx.Response(
            200,
            content=(
                json.dumps({"message": message})
                + "\n"
                + json.dumps({"done": True, "message": {"content": ""}})
                + "\n"
            ).encode(),
        )

    try:
        tool = Tool(
            "read_file",
            "Read file",
            {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
            lambda path: reads.append(path) or "Actual notes",
        )
        agent.tools = {"read_file": tool}
        agent.gate.policies["read_file"] = "allow"
        agent.tool_selector = lambda *_: ["read_file"]
        agent.runtime.ollama._chat_client_factory = lambda: httpx.Client(
            base_url=vision_lab[0].ollama_url, transport=httpx.MockTransport(native)
        )
        value = envelope(vision_lab, agent)
        events = list(agent.run(value))
        assert reads == ["notes.txt"] and len(sent) == 2
        assert not [e for e in events if e.kind == "error"]
        assert all(
            sum(len(m.get("images", [])) for m in request["messages"]) == 1 for request in sent
        )
        assert sent[-1]["messages"][-1]["role"] == "tool"
        assert sent[-1]["messages"][-2]["tool_calls"][0]["function"]["arguments"] == {
            "path": "notes.txt"
        }
        assert agent.last_turn_capabilities["input_modalities"]["image_count"] == 1
    finally:
        agent.runtime.close()


def test_switch_to_compatible_adapter_never_sends_private_pixels(vision_lab):
    from klaude_core.compatible_runtime import CompatibleRuntime

    agent = agent_for(vision_lab)
    native_runtime = agent.runtime
    captured = []

    def compatible(request):
        captured.append(json.loads(request.content))
        events = [
            {"choices": [{"delta": {"content": "Pixels unavailable."}, "finish_reason": "stop"}]}
        ]
        return httpx.Response(
            200,
            content="".join("data: " + json.dumps(e) + "\n\n" for e in events) + "data: [DONE]\n\n",
        )

    runtime = CompatibleRuntime("http://127.0.0.1:1/v1")
    runtime._chat_client_factory = lambda: httpx.Client(
        base_url=runtime.base_url, transport=httpx.MockTransport(compatible)
    )
    try:
        value = envelope(vision_lab, agent)
        agent.restore_session([{"role": "user", "content": "Image", "model_content": value}])
        agent.runtime = agent.ollama = runtime
        agent.model_info = ModelInfo("openai_compatible", "test", "Test")
        list(agent.run("Continue describing the image"))
        assert captured and "Image pixels are unavailable" in captured[-1]["messages"][0]["content"]
        assert not any(
            k in m
            for m in captured[-1]["messages"]
            for k in ("images", "image_content", "image_inputs")
        )
        assert agent.last_turn_capabilities["input_modalities"]["image_count"] == 0
        assert agent.messages[1]["image_inputs"] == value["image_inputs"]
    finally:
        native_runtime.close()
        runtime.close()


@pytest.mark.parametrize("role", ["system", "assistant", "tool"])
def test_native_adapter_rejects_pixels_outside_user_messages(role):
    with pytest.raises(OllamaError):
        _native_messages(
            [
                {
                    "role": role,
                    "content": "",
                    "image_content": [
                        {
                            "type": "image",
                            "mime_type": "image/png",
                            "data": base64.b64encode(png()).decode(),
                        },
                    ],
                }
            ]
        )


def test_image_chat_transport_cancellation_wakes_before_headers(vision_lab):
    agent = agent_for(vision_lab)
    try:
        value = envelope(vision_lab, agent)
        vision_lab[5]["value"] = "slow"
        events = []
        cancelled = threading.Event()
        agent.cancellation_check = cancelled.is_set
        worker = threading.Thread(target=lambda: events.extend(agent.run(value)))
        worker.start()
        assert vision_lab[6].wait(2)
        started = time.monotonic()
        cancelled.set()
        assert agent.cancel_active_transports()
        worker.join(2)
        assert not worker.is_alive() and time.monotonic() - started < 2
        assert not any(e.kind == "text" for e in events)
    finally:
        agent.runtime.close()
