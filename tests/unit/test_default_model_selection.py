from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest
from klaude_cli.ai_default_settings import AIDefaultSettings
from klaude_cli.default_model_selection import read_default_candidates
from klaude_core.ai_defaults import AIDefaults, DefaultsChange, read_defaults, save_defaults
from klaude_core.model_management import ModelChange, apply_model_change
from klaude_core.model_runtime import ModelCapabilities, ModelInfo
from klaude_core.settings_store import SettingsConflictError, update_settings

from .test_ai_defaults import setup as setup
from .test_model_capabilities import Host


def packet(cfg):
    return {
        "config_dir": str(cfg.config_dir),
        "data_dir": str(cfg.data_dir),
        "ollama_url": cfg.ollama_url,
        "roles": cfg.models,
        "requested_roles": ["chat", "utility", "research", "vision"],
        "credential_revisions": {},
        "environment_keys": {},
    }


def native(setup, monkeypatch, declarations):
    cfg, registry, _ = setup
    connection = registry.load()["default-ollama"]
    module = "klaude_application.default_model_selection."
    monkeypatch.setattr(
        module + "discover_connection",
        lambda c, _key: (
            [
                ModelInfo(
                    c.backend,
                    name,
                    name,
                    connection_id=c.id,
                    connection_revision=c.revision,
                    connection_source=c.source,
                )
                for name in declarations
            ]
            if c.id == connection.id
            else []
        ),
    )
    monkeypatch.setattr(
        module + "read_capabilities",
        lambda r: {
            "status": "ok",
            "models": [{"model": name, **declarations[name]} for name in r["models"]],
        },
    )
    monkeypatch.setattr(module + "inspect_model", lambda *_a, **_kw: {})
    return cfg, connection


def test_empty_roles_use_small_declared_models_and_leave_vision_disabled(setup, monkeypatch):
    cfg, connection = native(
        setup,
        monkeypatch,
        {
            "large": {"declared": ["completion", "vision", "tools"], "parameter_count": 30_000},
            "tiny": {"declared": ["completion", "tools"], "parameter_count": 2000},
            "eye": {"declared": ["completion", "vision"], "parameter_count": 3000},
            "embedding": {"declared": ["embedding"], "parameter_count": 1},
        },
    )
    proposals = read_default_candidates(packet(cfg))["proposals"]
    assert {p["role"]: p["reference"].split("/")[-1] for p in proposals} == {
        "utility": "tiny",
        "research": "tiny",
        "vision": "eye",
    }
    # Small verified vision models are preferred; no hardware-fit claim is made.
    for p in proposals:
        save_defaults(
            cfg,
            DefaultsChange(p["role"], p["reference"], None, (tuple(p["binding"]),), automatic=True),
        )
    saved = read_defaults(cfg)
    assert saved.chat == "ollama/small:3b" and saved.vision == connection.model_ref("eye")
    assert saved.vision_enabled is False


@pytest.mark.parametrize("declared", [[], ["embedding"], ["completion"]])
def test_no_verified_vision_keeps_role_empty(setup, monkeypatch, declared):
    cfg, _ = native(setup, monkeypatch, {"not-a-vision-model": {"declared": declared}})
    assert not any(p["role"] == "vision" for p in read_default_candidates(packet(cfg))["proposals"])
    assert read_defaults(cfg).vision is None


def test_active_legacy_reference_matches_qualified_catalog_models(setup, monkeypatch):
    cfg, _ = native(setup, monkeypatch, {
        "small:3b": {"declared": ["completion", "vision", "tools"], "parameter_count": 3000},
        "other": {"declared": ["completion", "vision"], "parameter_count": 100},
    })
    result = read_default_candidates({**packet(cfg), "chat_ref": "ollama/small:3b"})
    assert all(p["reference"].endswith("/small:3b") for p in result["proposals"])


def test_disabled_model_and_failing_verification_are_not_selected(setup, monkeypatch):
    cfg, connection = native(
        setup,
        monkeypatch,
        {
            "disabled": {"declared": ["completion", "vision"]},
            "bad": {"declared": ["completion", "vision"]},
        },
    )
    apply_model_change(
        cfg, ModelChange("choice", (connection,), "disabled", "enabled", False, True)
    )

    def reject(*_args, **_kwargs):
        raise ValueError("metadata unavailable")

    monkeypatch.setattr("klaude_application.default_model_selection.inspect_model", reject)
    proposals = read_default_candidates(packet(cfg))["proposals"]
    assert all(not p["reference"].endswith("/disabled") for p in proposals)
    assert not any(p["role"] == "vision" for p in proposals)


def test_manual_inheritance_and_concurrent_clear_are_preserved(setup, monkeypatch):
    cfg, connection = native(setup, monkeypatch, {"eye": {"declared": ["completion", "vision"]}})
    reference = connection.model_ref("eye")
    candidate = DefaultsChange(
        "vision", reference, None, ((reference, connection.revision, ""),), automatic=True
    )
    save_defaults(cfg, DefaultsChange("vision", None, None))
    assert save_defaults(cfg, candidate)["vision"] is None
    result = read_default_candidates(packet(cfg))
    assert not any(p["role"] == "vision" for p in result["proposals"])
    assert read_defaults(cfg).vision is None


def test_automatic_write_rechecks_endpoint_revision(setup):
    cfg, registry, connection = setup
    ref = connection.model_ref("eye")
    change = DefaultsChange("vision", ref, None, ((ref, connection.revision, ""),), automatic=True)
    update_settings(
        registry.path,
        {
            ("connections", connection.id): asdict(
                replace(connection, base_url="http://localhost:9191")
            )
        },
    )
    with pytest.raises(SettingsConflictError):
        save_defaults(cfg, change)
    assert read_defaults(cfg).vision is None


def test_standard_only_roles_skip_thinking_required_models(setup, monkeypatch):
    cfg, _, connection = setup
    thinking = ModelInfo(
        connection.backend,
        "thinking",
        "Thinking",
        ModelCapabilities(supports_images=True, thinking_types=("enabled",)),
        connection_id=connection.id,
    )
    monkeypatch.setattr(
        "klaude_application.default_model_selection.discover_connection",
        lambda c, _key: [thinking] if c.id == connection.id else [],
    )
    assert read_default_candidates(packet(cfg))["proposals"] == []


def test_automatic_proposals_save_in_order_without_switching_session_or_page(setup):
    cfg, registry, _ = setup
    connection = registry.load()["default-ollama"]
    host = Host(cfg)
    host._session_actions = SimpleNamespace(submit=lambda action: actions.append(action) or True)
    host._start_next = lambda: None
    controller = AIDefaultSettings(host)
    controller.defaults = AIDefaults("ollama/chat")
    controller.connections = {connection.id: connection}
    controller.show("home")
    actions = []
    controller.automatic_scan = ("job", host.session_id)
    proposals = [
        {
            "role": role,
            "reference": connection.model_ref(role),
            "binding": [connection.model_ref(role), connection.revision, ""],
        }
        for role in ("utility", "research", "vision")
    ]
    controller.accept("ai-defaults:automatic", "job", {"proposals": proposals}, "")
    for role in ("utility", "research", "vision"):
        action = actions[-1]
        assert action.change.field == role and action.change.automatic
        controller.saved((host.session_id, action.identity, controller.defaults.public(), ""))
    assert len(actions) == 3 and controller.defaults.vision
    assert not controller.defaults.vision_enabled and host.agent.model == "chat"
    assert controller.view == "home"
    controller.automatic_scan = ("late", host.session_id)
    controller.leave()
    controller.accept("ai-defaults:automatic", "late", {"proposals": proposals}, "")
    assert len(actions) == 3


def test_manual_navigation_does_not_wait_for_automatic_scan_and_rejects_its_result(setup):
    cfg, registry, _ = setup
    host = Host(cfg)
    controller = AIDefaultSettings(host)
    controller.defaults = AIDefaults("ollama/chat")
    controller.connections = registry.load()
    controller.automatic_scan = ("slow", host.session_id)
    controller.show("home")
    assert next(row for row in controller.page().rows if row.id == "chat").enabled
    controller.show("endpoints")
    assert controller.automatic_scan is None
    assert "ai-defaults:automatic" in host._background_jobs.cancelled
    controller.accept("ai-defaults:automatic", "slow", {"proposals": []}, "")
    assert controller.view == "endpoints"
