import json
from dataclasses import asdict, replace
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.session_actions import AIDefaultUpdate, SessionActionWriter, SessionTitleUpdate
from klaude_core.ai_defaults import (
    AIDefaults,
    DefaultsChange,
    defaults_from_preferences,
    migrate_defaults,
    read_defaults,
    save_defaults,
)
from klaude_core.compatible_runtime import CompatibleModelError
from klaude_core.memory import Memory
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_management import ModelChange, apply_model_change, startup_snapshot
from klaude_core.settings_store import SettingsConflictError, update_settings
from klaude_core.utility import public_dialogue, run_utility


@pytest.fixture
def setup(tmp_path):
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        models={"coder": "small:3b", "embed": "embedding:latest"},
        ollama_url="http://localhost:11434",
    )
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    lab = ModelConnection("lab", "Lab", "openai_compatible", "http://localhost:8080")
    registry.add(lab)
    migrate_defaults(cfg)
    return cfg, registry, lab


def change(setup, field, value):
    cfg, registry, _lab = setup
    previous = read_defaults(cfg)
    refs = value if isinstance(value, tuple) else (value,) if value else ()
    bindings = []
    from klaude_core.model_management import reference_parts

    for ref in refs:
        conn = registry.load()[reference_parts(ref)[1]]
        bindings.append((ref, conn.revision, ""))
    return DefaultsChange(field, value, getattr(previous, field), tuple(bindings))


def test_migration_freezes_startup_and_preserves_embedding_and_unrelated_fields(setup):
    cfg, _, _ = setup
    path = cfg.data_dir / "chat-preferences.json"
    update_settings(path, {("last_model",): "ollama/another", ("custom",): 42})
    assert migrate_defaults(cfg) == AIDefaults("ollama/small:3b")
    assert read_defaults(cfg).chat == "ollama/small:3b"
    assert json.loads(path.read_text())["custom"] == 42
    assert cfg.models["embed"] == "embedding:latest"


def test_migration_carries_legacy_explicit_unset_and_saved_cloud(tmp_path):
    cfg = SimpleNamespace(data_dir=tmp_path, models={"coder": "small"})
    path = tmp_path / "chat-preferences.json"
    path.write_text(json.dumps({"last_model": "openrouter/vendor/model", "custom": 7}))
    assert migrate_defaults(cfg).chat == "openrouter/vendor/model"
    path.write_text(json.dumps({"last_model": "ollama/small", "require_model_selection": True}))
    assert migrate_defaults(cfg).chat is None


def test_role_updates_merge_fields_and_reject_stale_same_field(setup):
    cfg, _, lab = setup
    chat = change(setup, "chat", lab.model_ref("vendor/chat"))
    utility = change(setup, "utility", lab.model_ref("vendor/utility"))
    save_defaults(cfg, chat)
    save_defaults(cfg, utility)
    assert read_defaults(cfg) == AIDefaults(
        lab.model_ref("vendor/chat"), lab.model_ref("vendor/utility")
    )
    with pytest.raises(SettingsConflictError):
        save_defaults(cfg, chat)


@pytest.mark.parametrize(
    "raw",
    [
        {"chat": None, "fallbacks": ["ollama/a", "ollama@default-ollama/a"]},
        {"chat": None, "utility": "ollama/a", "fallbacks": ["ollama@default-ollama/a"]},
        {"chat": None, "fallbacks": ["ollama/a"] * 4},
        {"chat": None, "utility": False},
    ],
)
def test_invalid_or_cyclic_utility_defaults_fail_honestly(setup, raw):
    cfg, _, _ = setup
    with pytest.raises(ValueError):
        defaults_from_preferences(cfg, {"ai_defaults": raw})


def test_selection_revisions_and_disabled_models_cannot_be_bypassed(setup):
    cfg, registry, lab = setup
    selected = change(setup, "utility", lab.model_ref("small"))
    update_settings(
        registry.path,
        {("connections", "lab"): asdict(replace(lab, base_url="http://localhost:8081"))},
    )
    with pytest.raises(SettingsConflictError):
        save_defaults(cfg, selected)
    current = registry.load()["lab"]
    selected = change(setup, "utility", current.model_ref("small"))
    apply_model_change(cfg, ModelChange("choice", (current,), "small", "enabled", False, True))
    with pytest.raises(ValueError):
        save_defaults(cfg, selected)
    assert read_defaults(cfg).utility is None


def test_endpoint_removal_requires_explicit_utility_unset_and_rejects_changed_roles(setup):
    cfg, registry, lab = setup
    save_defaults(cfg, change(setup, "utility", lab.model_ref("small")))
    save_defaults(cfg, change(setup, "fallbacks", ("ollama/other",)))
    previous = read_defaults(cfg)
    request = ModelChange(
        "remove", (lab,), defaults_expected=(previous.chat, previous.utility, previous.fallbacks)
    )
    with pytest.raises(SettingsConflictError):
        apply_model_change(cfg, request)
    assert "lab" in registry.load()
    save_defaults(cfg, change(setup, "fallbacks", ("ollama/next",)))
    with pytest.raises(SettingsConflictError):
        apply_model_change(cfg, replace(request, unset_utility=True))
    latest = read_defaults(cfg)
    apply_model_change(
        cfg,
        replace(
            request,
            unset_utility=True,
            defaults_expected=(latest.chat, latest.utility, latest.fallbacks),
        ),
    )
    assert read_defaults(cfg) == AIDefaults(previous.chat, None, ("ollama/next",))


def test_startup_replacement_targets_default_chat_not_last_session_choice(setup):
    cfg, registry, lab = setup
    selected = lab.model_ref("chat")
    save_defaults(cfg, change(setup, "chat", selected))
    update_settings(
        cfg.data_dir / "chat-preferences.json", {("last_model",): "ollama/session-only"}
    )
    assert startup_snapshot(cfg.data_dir / "chat-preferences.json")["last_model"] == selected
    apply_model_change(cfg, ModelChange("remove", (lab,), startup_last=selected, replacement=""))
    assert read_defaults(cfg).chat is None
    assert startup_snapshot(cfg.data_dir / "chat-preferences.json")["require_model_selection"]


def seed_session(cfg):
    memory = Memory(cfg.data_dir / "memory.md", cfg.data_dir / "sessions.db")
    memory.log_turn(
        "session",
        "user",
        "Build a bounded cache for the project",
        model_content="PRIVATE ATTACHMENT",
    )
    memory.log_turn("session", "assistant", "Added expiry; concurrency checks remain.")
    memory.log_turn("session", "tool", "PRIVATE TOOL OUTPUT")
    memory.log_turn("session", "system", "PRIVATE REASONING")
    return memory


def request(cfg, task="recap"):
    return {
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "roles": cfg.models,
        "ollama_url": cfg.ollama_url,
        "session_id": "session",
        "task": task,
        "chat_ref": "ollama/small:3b",
        "defaults": read_defaults(cfg).public(),
    }


@pytest.mark.parametrize("native_options", [{}, {"num_gpu": 0, "num_thread": 2}])
def test_utility_uses_public_saved_turns_and_no_tools_or_private_context(
    setup, monkeypatch, native_options
):
    cfg, _, _ = setup
    seed_session(cfg)
    calls = []

    class Runtime:
        last_chat_metadata = {"prompt_eval_count": 90, "eval_count": 20}

        def chat(self, model, messages, **kwargs):
            calls.append((model, messages, kwargs))
            return {"content": "Added cache expiry. Next: concurrency checks."}

        def close(self):
            pass

        def cancel_active(self):
            pass

    monkeypatch.setattr("klaude_core.utility.runtime_for_utility", lambda *_: Runtime())
    packet = request(cfg)
    packet["native_options"] = native_options
    result = run_utility(packet)
    assert result["usage"] == [90, 20]
    assert result["attempts"] == ["ollama@default-ollama/small:3b"]
    assert len(calls) == 1 and calls[0][2]["tools"] is None
    assert calls[0][2]["options"] == {**native_options, "num_ctx": 4096, "num_predict": 512}
    assert "PRIVATE" not in str(calls)
    assert "concurrency" in str(calls)


@pytest.mark.parametrize(
    "failure,expected_calls",
    [
        (CompatibleModelError("temporary", status_code=503), 2),
        (httpx.ConnectError("private diagnostic"), 2),
        (httpx.LocalProtocolError("private diagnostic"), 1),
        (httpx.RemoteProtocolError("private diagnostic"), 1),
        (CompatibleModelError("auth", status_code=401), 1),
        (CompatibleModelError("malformed"), 1),
    ],
)
def test_only_typed_eligible_errors_use_explicit_fallbacks(
    setup, monkeypatch, failure, expected_calls
):
    cfg, _, lab = setup
    seed_session(cfg)
    save_defaults(cfg, change(setup, "fallbacks", (lab.model_ref("fallback"),)))
    calls = []

    class Runtime:
        last_chat_metadata = {"prompt_eval_count": 10, "eval_count": 4}

        def chat(self, model, *_args, **_kwargs):
            calls.append(model)
            if len(calls) == 1:
                raise failure
            return {"content": "Cache expiry is implemented."}

        def close(self):
            pass

        def cancel_active(self):
            pass

    monkeypatch.setattr("klaude_core.utility.runtime_for_utility", lambda *_: Runtime())
    result = run_utility(request(cfg))
    assert len(calls) == expected_calls
    assert "private diagnostic" not in str(result)
    if expected_calls == 2:
        assert result["model"] == lab.model_ref("fallback")
        assert result["usage"] == [20, 8]
    else:
        assert result.get("error") and "text" not in result


def test_empty_conversation_and_invalid_response_never_launch_an_extra_attempt(setup, monkeypatch):
    cfg, _, _ = setup
    memory = Memory(cfg.data_dir / "memory.md", cfg.data_dir / "sessions.db")
    monkeypatch.setattr(
        "klaude_core.utility.runtime_for_utility", lambda *_: pytest.fail("No model call")
    )
    assert run_utility(request(cfg)).get("error")
    assert public_dialogue(memory.sessions_db, "session")[0] == ""


def test_utility_title_save_rejects_concurrent_manual_rename(setup):
    cfg, _, _ = setup
    memory = seed_session(cfg)
    assert memory.rename_session_if_current("session", "Cache task", "")
    memory.rename_session("session", "User chosen title")
    assert not memory.rename_session_if_current("session", "Stale AI title", "Cache task")
    assert memory.session_title("session") == "User chosen title"


def test_defaults_action_lane_works_without_session_database_and_drains(setup):
    cfg, _, lab = setup
    events = []
    unavailable = SimpleNamespace(
        open_session_io=lambda: pytest.fail("Defaults do not need a session DB")
    )
    writer = SessionActionWriter(unavailable, lambda kind, value: events.append((kind, value)))
    update = AIDefaultUpdate(
        "session", "change", cfg, change(setup, "utility", lab.model_ref("small"))
    )
    assert writer.submit(update)
    assert writer.close(wait=True)
    assert events[0][0] == "ai_defaults_saved"
    assert events[0][1][2]["utility"] == lab.model_ref("small")
    assert read_defaults(cfg).utility == lab.model_ref("small")


def test_title_action_acknowledges_actual_save_even_if_history_fails(setup, monkeypatch):
    cfg, _, _ = setup
    memory = seed_session(cfg)
    monkeypatch.setattr(
        Memory, "record_session_update", lambda *_: (_ for _ in ()).throw(OSError())
    )
    events = []
    writer = SessionActionWriter(memory, lambda kind, value: events.append((kind, value)))
    assert writer.submit(SessionTitleUpdate("session", "job", "Cache task", "", "AI title"))
    assert writer.close(wait=True)
    assert memory.session_title("session") == "Cache task"
    assert events[-1][0] == "session_title_saved" and events[-1][1][1]
    assert events[0][0] == "utility_history_failed"
