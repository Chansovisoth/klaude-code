"""Shared inventory preserves independent evidence without implicit server work."""

import copy
from types import SimpleNamespace

import pytest
from klaude_application import image_readiness as readiness
from klaude_application import image_setups as setups

from .test_image_model_selection import image_browser as image_browser
from .test_image_setups import environment as environment
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def inventory(environment, monkeypatch):
    cfg, data, body = environment
    plan = {"model": "hf.co/test/model:weight.gguf", "name": "Example plan",
            "components": [{"slot": "primary", "artifact_id": "artifact",
                            "destination": "checkpoints/test/model/weight.gguf",
                            "category": "checkpoints"}]}
    monkeypatch.setattr(readiness.plans, "_document", lambda cfg: {
        "items": {"a" * 64: {"selection": copy.deepcopy(plan), "checked_at": 1}}})
    monkeypatch.setattr(readiness, "jobs", lambda *args: {"items": []})
    return cfg, data, body, plan


def test_listing_is_metadata_only_and_check_retains_independent_axes(inventory, monkeypatch):
    cfg, data, body, plan = inventory
    saved = setups.save(cfg, body)
    monkeypatch.setattr(setups, "catalog", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("Listing must not contact a server")))
    result = readiness.listing(cfg, None)
    assert len(result["items"]) == 2
    assert all(item["checked_at"] is None for item in result["items"])
    monkeypatch.setattr(setups, "catalog", lambda *args, **kwargs: copy.deepcopy(data))
    readiness.check(cfg, "setup", saved["id"])
    item = readiness.listing(cfg, None)["items"][0]
    assert item["headline"] == "Missing components" and item["checked_at"]
    assert item["readiness"]["compatibility"] == "unverified"
    assert item["readiness"]["inference"] == "untested"
    monkeypatch.setattr(setups, "catalog", lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    readiness.check(cfg, "setup", saved["id"])
    assert readiness.listing(cfg, None)["items"][0]["headline"] == "Service unavailable"
    assert not cfg.config_dir.exists()


def test_transfers_and_settings_invalidate_cached_readiness(inventory, monkeypatch):
    cfg, data, body, plan = inventory
    readiness.record(cfg, "plan:" + "a" * 64, {"headline": "Planned paths visible"})
    transfer = {"artifact_id": "artifact", "state": "unknown", "request_id": "receipt"}
    monkeypatch.setattr(readiness, "jobs", lambda *args: {"items": [transfer]})
    item = readiness.listing(cfg, None)["items"][0]
    assert item["headline"] == "Download outcome unconfirmed"
    assert item["transfers"][0]["request_id"] == "receipt"
    monkeypatch.setattr(readiness, "jobs", lambda *args: {"items": []})
    assert readiness.listing(cfg, None)["items"][0]["headline"] == "Planned paths visible"
    monkeypatch.setattr(readiness, "read",
                        lambda cfg: {"endpoint": "http://changed", "enabled": False})
    item = readiness.listing(cfg, None)["items"][0]
    assert item["headline"] == "Setup not checked" and item["checked_at"] is None


def test_changed_primary_does_not_borrow_originating_plan_readiness(inventory, monkeypatch):
    cfg, data, body, plan = inventory
    monkeypatch.setattr(readiness.plans, "get", lambda *args: {})
    saved = setups.save(cfg, {**body, "install_plan": "a" * 64})
    item = readiness.listing(cfg, None)["items"][0]
    assert item["id"] == saved["id"] and item["plan_available"]
    assert item["model_refs"] == []
    assert readiness.listing(cfg, None)["items"][1]["model_refs"] == [plan["model"]]
    monkeypatch.setattr(readiness.plans, "_document",
                        lambda cfg: (_ for _ in ()).throw(ValueError()))
    result = readiness.listing(cfg, None)
    assert len(result["items"]) == 1 and result["errors"]


def test_inventory_endpoint_requires_csrf_and_checks_only_the_chosen_setup(image_browser):
    host, service, auth, url, state = image_browser
    from klaude_application.image_model_selection import catalog

    data = catalog(service.cfg, url)
    saved = setups.save(service.cfg, {"endpoint": url, "recipe": "sd", "models": {},
                                     "catalog_revision": data["catalog_revision"]})
    route = "/api/v1/settings/models/image-readiness"
    before = len(state["calls"])
    assert _request(host, "POST", route, body={"action": "list"}, **auth)[0] == 200
    assert len(state["calls"]) == before
    assert _request(host, "POST", route, body={"action": "list"},
                    **{**auth, "csrf": "bad"})[0] == 403
    assert _request(host, "POST", route, body={"action": "check", "kind": "setup",
                                              "id": saved["id"]}, **auth)[0] == 200
    assert len(state["calls"]) > before and not state["loads"]


def test_latest_transfer_and_current_load_fence_take_precedence(inventory, monkeypatch):
    cfg, data, body, plan = inventory
    saved = setups.save(cfg, body)
    readiness.record(cfg, "setup:" + saved["id"], {"headline": "Loaded and configured"})
    transfers = [{"artifact_id": "artifact", "state": "completed", "request_id": "new"},
                 {"artifact_id": "artifact", "state": "cancelled", "paused": True,
                  "request_id": "old"}]
    monkeypatch.setattr(readiness, "jobs", lambda *args: {"items": transfers})
    assert readiness.listing(cfg, None)["items"][1]["headline"] == "Setup not checked"
    journal = SimpleNamespace(fenced_operation=lambda key: SimpleNamespace(
        receipt=SimpleNamespace(state="unknown")))
    result = readiness.listing(cfg, journal)
    assert result["items"][0]["headline"] == "Load outcome unconfirmed"
    assert result["items"][0]["live_status"]


def test_bad_settings_do_not_hide_other_metadata(inventory, monkeypatch):
    cfg, data, body, plan = inventory
    monkeypatch.setattr(readiness, "read", lambda cfg: (_ for _ in ()).throw(ValueError()))
    result = readiness.listing(cfg, None)
    assert result["items"] and "Image service settings unavailable" in result["errors"]
