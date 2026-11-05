"""Saved drafts persist identities without authorizing or replaying model work."""

import copy
import json
from types import SimpleNamespace

import pytest
from klaude_application import image_setups as setups
from klaude_application.image_model_selection import digest

from .test_image_model_selection import image_browser as image_browser
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def environment(tmp_path, monkeypatch):
    cfg = SimpleNamespace(data_dir=tmp_path, config_dir=tmp_path / "config")
    recipe = {"id": "test", "name": "Test setup", "models": {}, "required_any": [["vae"]],
              "slots": [{"id": "model", "required": True, "categories": ["checkpoints"]},
                        {"id": "vae", "required": False, "categories": ["vae"]}]}
    data = {"endpoint": "http://127.0.0.1:1234", "recipes": [recipe],
            "files": [{"id": "main", "name": "Main", "category": "checkpoints"},
                      {"id": "vae", "name": "Decoder", "category": "vae"}],
            "runtime": {"state": "empty", "recipe": "", "models": {}},
            "model": "", "pending": None, "catalog_revision": "original"}
    monkeypatch.setattr(setups, "catalog", lambda *a, **kw: copy.deepcopy(data))
    body = {"endpoint": data["endpoint"], "recipe": "test", "models": {"model": "main"},
            "catalog_revision": "original"}
    return cfg, data, body


def test_partial_draft_identity_persists_and_is_idempotent(environment):
    cfg, data, body = environment
    result = setups.save(cfg, body)
    assert result["readiness"]["headline"] == "Missing components"
    assert result["readiness"]["missing_alternatives"] == [["vae"]]
    saved = (cfg.data_dir / "image-setups.json").read_bytes()
    assert setups.save(cfg, body)["id"] == result["id"]
    assert (cfg.data_dir / "image-setups.json").read_bytes() == saved
    restarted = SimpleNamespace(data_dir=cfg.data_dir, config_dir=cfg.config_dir)
    assert setups.listing(restarted, body["endpoint"])["items"][0]["id"] == result["id"]
    assert setups.check(restarted, result["id"])["selection"] == result["selection"]
    assert not cfg.config_dir.exists()  # No preference save or runtime operation.
    assert setups.listing(cfg, "http://127.0.0.1:9999")["items"] == []
    changed = setups.save(cfg, {**body, "models": {"model": "main", "vae": "vae"}})
    assert changed["id"] != result["id"]
    assert changed["readiness"]["can_review_load"]


def test_current_evidence_downgrades_and_never_repins(environment, monkeypatch):
    cfg, data, body = environment
    result = setups.save(cfg, {**body, "models": {"model": "main", "vae": "vae"}})
    original = (cfg.data_dir / "image-setups.json").read_bytes()
    data["files"].pop()
    checked = setups.check(cfg, result["id"])
    assert checked["readiness"]["unavailable_slots"] == ["vae"]
    assert not checked["readiness"]["can_review_load"]
    data["recipes"][0]["name"] = "Changed"
    assert setups.check(cfg, result["id"])["readiness"]["recipe"] == "changed"
    monkeypatch.setattr(setups, "catalog", lambda *a, **kw: (_ for _ in ()).throw(OSError()))
    assert setups.check(cfg, result["id"])["readiness"]["headline"] == "Service unavailable"
    assert (cfg.data_dir / "image-setups.json").read_bytes() == original


def test_runtime_configuration_and_inference_are_independent(environment):
    cfg, data, body = environment
    result = setups.save(cfg, {**body, "models": {"model": "main", "vae": "vae"}})
    selection = result["selection"]
    data["runtime"] = {"state": "ready", "recipe": "test",
                       "models": {"model": "main", "vae": "vae"}}
    data["model"] = "Model name"
    settings = {"enabled": True, "endpoint": data["endpoint"], "model": "Other model"}
    assert setups.project(selection, data, settings)["configuration"] == "not_applied"
    settings["model"] = data["model"]
    ready = setups.project(selection, data, settings)
    assert ready["headline"] == "Loaded and configured"
    assert ready["inference"] == "untested" and ready["compatibility"] == "unverified"
    data["pending"] = {"state": "unknown", "request_id": "a" * 32}
    ready = setups.project(selection, data, settings)
    assert ready["runtime"] == "unconfirmed" and not ready["can_review_load"]
    assert ready["pending"]["request_id"] == "a" * 32


def test_stale_inputs_tampering_and_limits_fail_closed(environment):
    cfg, data, body = environment
    for bad in ({**body, "catalog_revision": "old"},
                {**body, "models": {"model": "vae"}},
                {**body, "models": {"unknown": "main"}},
                {**body, "models": {"model": "/private/guessed"}}):
        with pytest.raises(ValueError):
            setups.save(cfg, bad)
    result = setups.save(cfg, body)
    path = cfg.data_dir / "image-setups.json"
    document = json.loads(path.read_text())
    document["items"][result["id"]]["selection"]["endpoint"] = "http://other:1234"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="identity"):
        setups.check(cfg, result["id"])
    path.unlink()
    path.symlink_to(cfg.data_dir / "missing")
    with pytest.raises((ValueError, OSError)):
        setups.save(cfg, body)


def test_inventory_capacity_preserves_existing_drafts(environment):
    cfg, data, body = environment
    for i in range(setups.MAX_SETUPS):
        data["recipes"][0]["name"] = str(i)
        setups.save(cfg, body)
    data["recipes"][0]["name"] = "another"
    with pytest.raises(ValueError, match="limit"):
        setups.save(cfg, body)
    assert len(setups.listing(cfg, body["endpoint"])["items"]) == setups.MAX_SETUPS


def test_endpoint_is_admin_csrf_protected_and_performs_no_load(image_browser):
    host, service, auth, url, state = image_browser
    api = "/api/v1/settings/models/image-setups"
    status, _, catalog = _request(host, "POST", "/api/v1/settings/models/image-models",
                                  body={"endpoint": url}, **auth)
    assert status == 200
    body = {"action": "save", "endpoint": url, "recipe": "sd",
            "models": {"model": "checkpoints/second.gguf"},
            "catalog_revision": catalog["catalog_revision"]}
    assert _request(host, "POST", api, body=body, **{**auth, "csrf": "wrong"})[0] == 403
    assert _request(host, "POST", api, body=body, origin=host.origin)[0] == 401
    status, _, saved = _request(host, "POST", api, body=body, **auth)
    assert status == 200 and digest(saved["selection"]) == saved["id"]
    assert _request(host, "POST", api, body={"action": "check", "id": saved["id"]},
                    **auth)[0] == 200
    host.http.host_lan = True
    assert _request(host, "POST", api, body=body, **auth)[0] == 403
    assert not state["loads"]


def test_forgetting_draft_never_changes_runtime_or_configuration(environment):
    cfg, data, body = environment
    before = copy.deepcopy(data)
    result = setups.save(cfg, body)
    setups.forget(cfg, result["id"])
    assert setups.listing(cfg, body["endpoint"])["items"] == []
    assert data == before and not cfg.config_dir.exists()
    assert setups.save(cfg, body)["id"] == result["id"]


def test_setup_retains_plan_without_changing_legacy_identity(environment, monkeypatch):
    from klaude_application import image_install_plans

    cfg, data, body = environment
    original = setups.save(cfg, body)
    identity = "a" * 64
    calls = []

    def get(cfg, value):
        calls.append(value)
        if value != identity:
            raise ValueError("Plan unavailable")
        return {"id": identity}

    monkeypatch.setattr(image_install_plans, "get", get)
    linked = setups.save(cfg, {**body, "install_plan": identity})
    assert linked["id"] != original["id"]
    assert linked["selection"]["install_plan"] == identity
    assert setups.check(cfg, linked["id"])["selection"]["install_plan"] == identity
    assert setups.save(cfg, body)["id"] == original["id"]
    with pytest.raises(ValueError, match="unavailable"):
        setups.save(cfg, {**body, "install_plan": "b" * 64})
    assert calls == [identity, "b" * 64]
    assert not cfg.config_dir.exists()
