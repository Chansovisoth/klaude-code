import json
from dataclasses import asdict
from types import SimpleNamespace

import httpx
import pytest
from klaude_cli.model_settings import read_inventory
from klaude_cli.model_settings import test_catalog as check_catalog
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_management import (
    OFFLINE_STATUSES,
    ModelChange,
    apply_model_change,
    model_choice,
    public_snapshot,
    validate_model_reference,
)
from klaude_core.model_runtime import ModelInfo, model_cache_generation, save_model_cache
from klaude_core.settings_store import SettingsConflictError, atomic_write_private, update_settings


@pytest.fixture
def setup(tmp_path):
    cfg = SimpleNamespace(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        ollama_url="http://localhost:11434",
        models={"coder": "small:3b"},
    )
    registry = connection_registry(cfg)
    registry.migrate(cfg)
    lab = ModelConnection("lab", "Lab", "openai_compatible", "http://localhost:8080")
    registry.add(lab)
    return cfg, registry, lab


def inventory(cfg):
    return read_inventory(
        {
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "ollama_url": cfg.ollama_url,
            "roles": cfg.models,
        }
    )


def test_independent_model_fields_merge_and_missing_models_keep_choices(setup):
    cfg, registry, lab = setup
    apply_model_change(cfg, ModelChange("choice", (lab,), "vendor/model", "hidden", True, False))
    apply_model_change(cfg, ModelChange("choice", (lab,), "vendor/model", "pinned", True, False))
    result = inventory(cfg)
    assert model_choice(result["choices"], "lab", "vendor/model") == {
        "enabled": True,
        "hidden": True,
        "pinned": True,
    }
    assert result["models"][0]["model_id"] == "vendor/model"
    assert result["discovered"] == []
    with pytest.raises(SettingsConflictError):
        apply_model_change(
            cfg, ModelChange("choice", (lab,), "vendor/model", "hidden", True, False)
        )
    validate_model_reference(cfg, "openai_compatible@lab/vendor/model")


def test_disabled_model_cannot_bypass_policies_with_manual_or_legacy_reference(setup):
    cfg, registry, lab = setup
    apply_model_change(cfg, ModelChange("choice", (lab,), "vendor/model", "enabled", False, True))
    with pytest.raises(ValueError, match="Model is disabled"):
        validate_model_reference(cfg, "openai_compatible@lab/vendor/model")
    default = registry.load()["default-ollama"]
    apply_model_change(cfg, ModelChange("choice", (default,), "other:3b", "enabled", False, True))
    with pytest.raises(ValueError, match="Model is disabled"):
        validate_model_reference(cfg, "ollama/other:3b")


def test_endpoint_disable_preserves_catalog_and_per_model_choices(setup):
    cfg, registry, lab = setup
    model = ModelInfo(
        "openai_compatible", "small", "Small", connection_id="lab", connection_revision=lab.revision
    )
    save_model_cache(
        cfg.data_dir / "model-cache.json", [model], backend=lab.backend, connection_id=lab.id
    )
    apply_model_change(cfg, ModelChange("choice", (lab,), "small", "pinned", True, False))
    apply_model_change(cfg, ModelChange("enabled", (lab,), value=False))
    result = inventory(cfg)
    assert result["models"][0]["model_id"] == "small"
    assert model_choice(result["choices"], "lab", "small")["pinned"]
    with pytest.raises(ValueError, match="endpoint is disabled"):
        validate_model_reference(cfg, model.ref)
    changed = registry.load()[lab.id]
    apply_model_change(cfg, ModelChange("enabled", (changed,), value=True))
    validate_model_reference(cfg, model.ref)


def test_removal_requires_reviewed_startup_choice_and_preserves_unrelated_preferences(setup):
    cfg, registry, lab = setup
    preferences = cfg.data_dir / "chat-preferences.json"
    selected = lab.model_ref("small")
    update_settings(preferences, {("last_model",): selected, ("tools",): {"keep": True}})
    with pytest.raises(SettingsConflictError, match="startup"):
        apply_model_change(cfg, ModelChange("remove", (lab,)))
    assert registry.load()[lab.id] == lab
    result = apply_model_change(
        cfg, ModelChange("remove", (lab,), startup_last=selected, replacement="")
    )
    saved = json.loads(preferences.read_text())
    assert saved["last_model"] == "" and saved["require_model_selection"]
    assert saved["tools"] == {"keep": True}
    assert result["removed"] == 1 and lab.id not in registry.load()
    assert lab.id not in registry.migrate(cfg)
    with pytest.raises(ValueError, match="removed"):
        validate_model_reference(cfg, selected)


def test_stale_definition_and_stale_startup_review_fail_without_overwriting(setup):
    cfg, registry, lab = setup
    apply_model_change(cfg, ModelChange("enabled", (lab,), value=False))
    before = registry.path.read_bytes()
    with pytest.raises(SettingsConflictError, match="Endpoint changed"):
        apply_model_change(cfg, ModelChange("remove", (lab,)))
    assert registry.path.read_bytes() == before
    changed = registry.load()[lab.id]
    preferences = cfg.data_dir / "chat-preferences.json"
    update_settings(preferences, {("last_model",): lab.model_ref("new")})
    with pytest.raises(SettingsConflictError, match="startup choice changed"):
        apply_model_change(
            cfg,
            ModelChange("remove", (changed,), startup_last=lab.model_ref("old"), replacement=""),
        )
    assert registry.path.read_bytes() == before


def test_explicit_replacement_must_be_available_and_preserves_current_role_config(setup):
    cfg, registry, lab = setup
    default = registry.load()["default-ollama"]
    with pytest.raises(ValueError):
        apply_model_change(
            cfg, ModelChange("remove", (default,), replacement=default.model_ref("small"))
        )
    assert default.id in registry.load()
    result = apply_model_change(
        cfg, ModelChange("enabled", (default,), value=False, replacement=lab.model_ref("small"))
    )
    assert result["startup"]["last_model"] == lab.model_ref("small")
    assert not result["startup"]["require_model_selection"]
    assert cfg.models["coder"] == "small:3b"


def test_catalog_failure_persists_precise_health_but_does_not_clear_previous_catalog(
    setup, monkeypatch
):
    cfg, registry, lab = setup
    original_client = httpx.Client
    monkeypatch.setattr(
        "klaude_core.model_discovery.httpx.Client",
        lambda **kw: original_client(
            **kw,
            transport=httpx.MockTransport(
                lambda req: httpx.Response(401, text="private-server-body")
            ),
        ),
    )
    result = check_catalog(
        {
            "connection": asdict(lab),
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "ollama_url": cfg.ollama_url,
            "cache_file": str(cfg.data_dir / "model-cache.json"),
        }
    )
    snapshot = public_snapshot(registry)
    assert result["status"] == "authentication"
    assert snapshot["checks"][lab.id]["status"] == "authentication"
    assert result["status"] not in OFFLINE_STATUSES
    assert "private-server-body" not in registry.path.read_text()


def test_failed_check_for_a_replaced_endpoint_cannot_publish_false_offline_health(
    setup, monkeypatch
):
    cfg, registry, lab = setup

    def stale(_connection, _key):
        apply_model_change(cfg, ModelChange("enabled", (lab,), value=False))
        from klaude_core.model_discovery import ModelDiscoveryError

        raise ModelDiscoveryError("network", "Cannot reach model connection")

    monkeypatch.setattr("klaude_core.model_discovery.discover_connection", stale)
    result = check_catalog(
        {
            "connection": asdict(lab),
            "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir),
            "ollama_url": cfg.ollama_url,
            "cache_file": str(cfg.data_dir / "model-cache.json"),
        }
    )
    assert result["status"] == "stale"
    assert lab.id not in public_snapshot(registry)["checks"]


def test_remove_purges_only_owned_catalog_and_invalidates_its_generation(setup):
    cfg, registry, lab = setup
    cache = cfg.data_dir / "model-cache.json"
    default = registry.load()["default-ollama"]
    native = ModelInfo(
        "ollama",
        "small:3b",
        "Small",
        connection_id=default.id,
        connection_revision=default.revision,
    )
    model = ModelInfo(
        lab.backend, "small", "Small", connection_id=lab.id, connection_revision=lab.revision
    )
    save_model_cache(cache, [native], backend="ollama", connection_id=default.id)
    save_model_cache(cache, [model], backend=lab.backend, connection_id=lab.id)
    generation = model_cache_generation(cache, f"{lab.backend}@{lab.id}")
    apply_model_change(cfg, ModelChange("remove", (lab,)))
    assert model_cache_generation(cache, f"{lab.backend}@{lab.id}") != generation
    from klaude_core.model_runtime import load_model_cache

    assert [item.ref for item in load_model_cache(cache)] == [native.ref]


def test_preference_save_failure_after_removal_still_blocks_requests(setup, monkeypatch):
    cfg, registry, lab = setup
    selected = lab.model_ref("small")
    update_settings(cfg.data_dir / "chat-preferences.json", {("last_model",): selected})

    def fail(path, text):
        raise OSError("Storage failed")

    monkeypatch.setattr("klaude_core.model_management.atomic_write_private", fail)
    with pytest.raises(OSError):
        apply_model_change(
            cfg, ModelChange("remove", (lab,), startup_last=selected, replacement="")
        )
    # Registry publication failed too: no partial success is assumed.
    assert lab.id in registry.load()
    monkeypatch.setattr(
        "klaude_core.model_management.atomic_write_private",
        lambda path, text: (
            fail(path, text)
            if path.name == "chat-preferences.json"
            else atomic_write_private(path, text)
        ),
    )
    with pytest.raises(OSError):
        apply_model_change(
            cfg, ModelChange("remove", (lab,), startup_last=selected, replacement="")
        )
    with pytest.raises(ValueError, match="removed"):
        validate_model_reference(cfg, selected)


def test_offline_review_rejects_health_that_changed_since_selection(setup):
    import time

    cfg, registry, lab = setup
    checked = time.time()
    update_settings(
        registry.path,
        {
            ("checks", lab.id): {
                "status": "ok",
                "checked_at": checked + 1,
                "revision": lab.revision,
                "credential_revision": "",
                "message": "Connection reached",
            }
        },
    )
    before = registry.path.read_bytes()
    change = ModelChange("remove", (lab,), offline_checks=((lab.id, checked, "network", ""),))
    with pytest.raises(SettingsConflictError, match="Offline status changed"):
        apply_model_change(cfg, change)
    assert registry.path.read_bytes() == before


def test_environment_credentials_travel_privately_and_stored_removal_wins(setup, monkeypatch):
    from klaude_cli.model_settings import request_key
    from klaude_core.config import save_provider_secret

    cfg, registry, lab = setup
    lab = ModelConnection("env", "Environment", lab.backend, lab.base_url, key_env="MODEL_TEST_KEY")
    registry.add(lab)
    monkeypatch.delenv("MODEL_TEST_KEY", raising=False)
    request = {"environment_keys": {"MODEL_TEST_KEY": "private-canary"}}
    assert request_key(request, cfg, lab) == "private-canary"
    save_provider_secret(cfg.config_dir, "MODEL_TEST_KEY", "")
    assert request_key(request, cfg, lab) == ""
