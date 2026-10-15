"""Session choices survive resume; dialogue and defaults cannot override them."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from klaude_cli import main as cli
from klaude_core import Tool
from klaude_core.config import save_provider_secret
from klaude_core.memory import Memory
from klaude_core.model_connections import connection_registry
from klaude_core.model_management import write_registry
from klaude_core.model_runtime import ModelInfo
from klaude_core.session_runtime import PREFIX, capture, decode, legacy

from . import test_chat_image_providers as providers

image_lab = providers.image_lab


def state(**updates):
    return {"version": 1, "model": "ollama/default", "mode": "standard", "effort": None,
            "definition": "", "credentials": "", "at": 100, **updates}


@pytest.mark.parametrize("update", [
    {"version": True}, {"at": True}, {"at": float("nan")}, {"at": float("inf")},
    {"model": "invented/model"}, {"model": "ollama/\nmodel"}, {"model": "ollama@!/model"},
    {"model": "ollama/" + "x" * 800}, {"credentials": "x" * 129},
    {"mode": "thinking"}, {"effort": "unlimited"}, {"key": "secret"},
])
def test_session_runtime_codec_rejects_unbounded_or_unrecognized_state(update):
    assert decode(state(**update)) is None


def test_runtime_is_atomic_private_and_older_writer_cannot_override_new_turn(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        with pytest.raises(ValueError):
            memory.start_session_turn("s", "c", "t", "question", runtime=state(key="bad"))
        assert memory.load_session("s") == []
        memory.start_session_turn("s", "c", "t", "question", runtime=state(at=200))
        memory.record_session_update("s", "c", "earlier selection", runtime=state(at=100))
        assert memory.session_snapshot("s")["runtime"]["at"] == 200
        assert all("definition" not in str(e["payload"])
                   for e in memory.session_events_since("s", 0))
        assert "credentials" not in str(memory.load_session("s"))
        memory.record_session_update("s", "c", "new selection", runtime=state(at=300))
        assert memory.session_runtime("s")["at"] == 300
    finally:
        memory.db.close()


@pytest.mark.parametrize("operation", ["delete", "archived_delete", "clear"])
def test_runtime_lifecycle_fork_archive_and_permanent_delete(tmp_path, operation):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        memory.db.execute("INSERT INTO settings VALUES ('unrelated', 'retained')")
        memory.db.commit()
        memory.start_session_turn("s", "c", "t", "question", runtime=state())
        memory.fork_session("s", "fork")
        assert memory.session_runtime("fork") == state()
        memory.change_session_archive("s", "archive")
        assert memory.session_runtime("s") == state()
        if operation == "delete":
            memory.delete_session("s")
        elif operation == "archived_delete":
            memory.change_session_archive("s", "delete")
        else:
            memory.clear_sessions()
        assert memory.session_runtime("s") is None
        assert memory.db.execute("SELECT value FROM settings WHERE key='unrelated'").fetchone()
        assert memory.session_runtime("fork") == (None if operation == "clear" else state())
        memory.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)",
                          (PREFIX + "bad", json.dumps({"model": "bad"})))
        assert memory.session_runtime("bad") is None
    finally:
        memory.db.close()


def test_legacy_inference_uses_only_klaudes_model_setting_event():
    detail = "model openai_compatible@image/vision · thinking · low · conversation retained"
    for role in ("user", "assistant"):
        assert legacy([{"role": role, "content": {"event": "session_update", "detail": detail}}]) \
            is None
    recovered = legacy([{"role": "system", "content": {
        "event": "session_update", "detail": detail}}])
    assert recovered["model"] == "openai_compatible@image/vision"
    assert recovered["mode"] == "thinking" and recovered["effort"] == "low"
    assert legacy([{"role": "system", "content": {"event": "other", "detail": detail}}]) is None


def prepare_restore(lab, monkeypatch):
    cfg, _, agent, _, calls, *_ = lab
    cfg.openai_api_key = cfg.openrouter_api_key = cfg.gemini_api_key = ""
    original = agent.model_info
    saved = capture(agent)
    monkeypatch.setattr(cli, "_available_chat_models", lambda *args: [original])
    agent.model_info = ModelInfo("ollama", "default", "Default Chat")
    agent.model = "default"
    return cfg, agent, calls, saved


@pytest.mark.parametrize("mode", ["standard", "thinking"])
def test_explicit_resume_restores_model_without_generation_or_changing_defaults(
    image_lab, monkeypatch, mode,
):
    cfg, agent, calls, saved = prepare_restore(image_lab, monkeypatch)
    saved.update(mode=mode, effort="low" if mode == "thinking" else None)
    before = {p.name: p.read_bytes() for p in cfg.config_dir.glob("*.json")}
    old = agent.runtime
    try:
        assert cli._restore_session_runtime(agent, cfg, saved, [])
        assert agent.model_info.ref == saved["model"]
        assert agent.reasoning_mode == mode
        if mode == "thinking":
            assert agent.reasoning_effort == "low"
        assert calls == []
        assert {p.name: p.read_bytes() for p in cfg.config_dir.glob("*.json")} == before
    finally:
        if agent.runtime is not old:
            agent.runtime.close()


@pytest.mark.parametrize("change", ["definition", "credential", "disabled", "removed"])
def test_stale_resume_requires_selection_instead_of_default_fallback(
    image_lab, monkeypatch, change,
):
    cfg, agent, calls, saved = prepare_restore(image_lab, monkeypatch)
    connection = image_lab[1]
    registry = connection_registry(cfg)
    if change == "credential":
        save_provider_secret(cfg.config_dir, connection.key_env, "changed-private-key")
    elif change == "removed":
        payload = registry._read()
        del payload["connections"][connection.id]
        write_registry(registry, payload)
    else:
        from dataclasses import asdict

        payload = registry._read()
        payload["connections"][connection.id] = asdict(
            replace(connection, enabled=False) if change == "disabled" else
            replace(connection, base_url=connection.base_url + "/changed")
        )
        write_registry(registry, payload)
    with pytest.raises(ValueError):
        cli._restore_session_runtime(agent, cfg, saved, [])
    assert agent.model == "default" and calls == []


def test_followup_without_tool_match_does_not_add_skills_but_explicit_skills_still_work():
    tools = {n: Tool(n, "", {}, lambda: None)
             for n in ("read_skill", "read_file", "web_search", "run_shell", "workspace_info")}
    assert cli._select_tool_names("Using the attached pixels again, name the center color only.",
                                  tools) == []
    assert "read_skill" in cli._select_tool_names("Read the coding standards skill", tools)
    assert "read_skill" in cli._select_tool_names("Fix the implementation in this project", tools)


def test_capture_contains_only_model_state():
    agent = SimpleNamespace(model_info=ModelInfo("ollama", "small", "Small"),
                            reasoning_mode="thinking", reasoning_effort="low", api_key="private")
    saved = capture(agent)
    assert saved["model"] == "ollama/small" and saved["effort"] == "low"
    assert "private" not in str(saved)


def test_visual_followup_keeps_pixels_without_reinterpreting_assistant_as_lookup(
    image_lab,
):
    agent = image_lab[2]
    agent.tools = {n: Tool(n, "", {}, lambda: None) for n in (
        "read_skill", "read_file", "search_sessions", "query_knowledge",
        "web_search", "fetch_url", "request_user_input",
    )}
    agent.tool_selector = cli._select_tool_names
    events = list(agent.run(providers.compose(image_lab)))
    assert not [e for e in events if e.kind == "error"]
    agent.messages[-1]["content"] = "Red, Green, Blue."
    events = list(agent.run("Using the attached pixels again, name the center color only."))
    assert not [e for e in events if e.kind == "error"]
    packets = [p for _, p, _ in image_lab[4] if "messages" in p]
    assert len(packets) == 2
    assert len(providers.pixel_blocks(image_lab, packets[-1])) == 1
    assert not packets[-1].get("tools")
