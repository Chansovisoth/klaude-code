"""Plans bind exact artifacts without admitting transfers or claiming readiness."""

import copy
import json
import uuid
from types import SimpleNamespace

import pytest
from klaude_application import image_install_plans as plans
from klaude_application import image_model_store as store
from klaude_application.image_dependencies import FLUX3

from .test_image_model_store import MODEL, PAYLOAD
from .test_image_model_store import image_store as image_store
from .test_library_management import _wait
from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def environment(tmp_path, monkeypatch):
    root = tmp_path / "models"
    root.mkdir()
    monkeypatch.setenv("KLAUDE_IMAGE_MODEL_DIR", str(root))
    cfg = SimpleNamespace(data_dir=tmp_path / "data", huggingface_base_url="https://huggingface.co")
    state = {"revision": "a" * 40, "sha256": "b" * 64, "size": 1234, "calls": []}

    def metadata(base, key, repo, *, image):
        state["calls"].append(repo)
        filename = "checkpoint.safetensors" if repo == "fixture/Image" else next(
            row[2] for row in FLUX3.values() if row[1] == repo)
        return {"revision": state["revision"], "files": [{
            "filename": filename, "sha256": state["sha256"], "size": state["size"],
        }]}

    monkeypatch.setattr(store, "hub_gguf_files", metadata)
    return cfg, root, state


def test_plan_has_exact_primary_companions_and_no_weight_effects(environment):
    cfg, root, state = environment
    plan = plans.create(cfg, MODEL, "flux3-klein")
    assert plan["selection"]["total_bytes"] == 3702
    rows = plan["selection"]["components"]
    assert [row["category"] for row in rows] == ["diffusion_models", "text_encoders", "vae"]
    assert len({row["artifact_id"] for row in rows}) == 3
    assert all(row["revision"] == "a" * 40 and row["sha256"] == "b" * 64 for row in rows)
    assert all("/blob/" + "a" * 40 in row["source_url"] for row in rows)
    assert not list(root.iterdir())
    calls = state["calls"].copy()
    restarted = SimpleNamespace(data_dir=cfg.data_dir)
    assert plans.get(restarted, plan["id"]) == plan
    assert calls == state["calls"]  # Reopening keeps the original metadata; no repinning.
    assert plans.create(cfg, MODEL, "flux3-klein")["id"] == plan["id"]
    assert plans.create(cfg, MODEL, "file-only")["selection"]["total_bytes"] == 1234


@pytest.mark.parametrize("change", ["revision", "sha256", "size", "root"])
def test_review_rejects_source_or_destination_drift(environment, monkeypatch, change):
    cfg, root, state = environment
    row = plans.create(cfg, MODEL, "file-only")["selection"]["components"][0]
    fields, _, _ = store.prepare(cfg, row["draft"])
    assert store.artifact_identity(fields) == row["artifact_id"]
    if change == "root":
        alternate = root.parent / "alternate"
        alternate.mkdir()
        monkeypatch.setenv("KLAUDE_IMAGE_MODEL_DIR", str(alternate))
    else:
        state[change] = {"revision": "c" * 40, "sha256": "d" * 64, "size": 999}[change]
    with pytest.raises(ValueError, match="changed"):
        store.prepare(cfg, row["draft"])
    assert not list(root.iterdir())


def test_existing_destination_is_unverified_and_cannot_be_overwritten(environment):
    cfg, root, state = environment
    destination = root / "diffusion_models/fixture/Image/checkpoint.safetensors"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"different content")
    plan = plans.create(cfg, MODEL, "flux3-klein")
    assert plan["existing_unverified"] == ["primary"]
    assert plan["selection"]["total_bytes"] == 3702  # Never deduct unverified files.
    with pytest.raises(ValueError, match="already installed"):
        store.prepare(cfg, plan["selection"]["components"][0]["draft"])
    assert destination.read_bytes() == b"different content"


def test_plan_rejects_unknown_profiles_bad_metadata_and_tampering(environment):
    cfg, root, state = environment
    with pytest.raises(ValueError):
        plans.create(cfg, MODEL, "guessed-architecture")
    assert not state["calls"]
    state["sha256"] = "missing"
    with pytest.raises(ValueError):
        plans.create(cfg, MODEL, "file-only")
    state["sha256"] = "b" * 64
    plan = plans.create(cfg, MODEL, "file-only")
    path = cfg.data_dir / "image-install-plans.json"
    record = json.loads(path.read_text())
    record["items"][plan["id"]]["selection"]["components"][0]["draft"]["category"] = "vae"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="identity"):
        plans.get(cfg, plan["id"])


def test_bounded_recent_metadata_does_not_touch_weights(environment, monkeypatch):
    cfg, root, state = environment
    monkeypatch.setattr(plans, "MAX_PLANS", 2)
    original = plans.create(cfg, MODEL, "file-only")
    for revision in ("c" * 40, "d" * 40):
        state["revision"] = revision
        plans.create(cfg, MODEL, "file-only")
    with pytest.raises(ValueError, match="unavailable"):
        plans.get(cfg, original["id"])
    assert not list(root.iterdir())


def test_http_plan_review_child_receipt_and_protection(image_store):
    host, service, auth, state, directory = image_store
    route = "/api/v1/settings/models/image-install-plans"
    body = {"action": "create", "model": MODEL, "profile": "file-only"}
    assert _request(host, "POST", route, body=body, **{**auth, "csrf": "bad"})[0] == 403
    code, _, plan = _request(host, "POST", route, body=body, **auth)
    assert code == 200
    assert not service.operations()["items"]
    assert not state["started"]
    component = plan["selection"]["components"][0]
    assert _request(host, "POST", route, body={"action": "get", "id": plan["id"]},
                    **auth)[2] == plan
    changed = copy.deepcopy(component["draft"])
    changed["category"] = "vae"
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": changed},
                    **auth)[0] == 400
    receipt, body = _submit(host, service, auth, _review(host, auth, component["draft"]))
    assert receipt["state"] == "completed"
    assert (directory / "checkpoints/fixture/Image/checkpoint.safetensors").read_bytes() == PAYLOAD
    jobs = _request(host, "GET", "/api/v1/models/downloads", **auth)[2]["items"]
    child = next(row for row in jobs if row["request_id"] == body["request_id"])
    assert child["artifact_id"] == component["artifact_id"]
    assert str(directory) not in json.dumps(jobs)
    assert not (service.cfg.config_dir / "image-generation.json").exists()


def test_group_approval_uses_one_review_and_stable_child_receipt(image_store):
    host, service, auth, state, directory = image_store
    plan = _request(host, "POST", "/api/v1/settings/models/image-install-plans",
                    body={"action": "create", "model": MODEL, "profile": "file-only"},
                    **auth)[2]
    draft = {"operation": "model-image-install-plan", "plan_id": plan["id"],
             "slots": ["primary"]}
    review = _review(host, auth, draft)
    assert "checkpoint.safetensors" in review["summary"]
    assert not state["started"]
    body = {"review_id": review["review_id"], "request_id": uuid.uuid4().hex,
            "control_epoch": 0}
    status, _, result = _request(host, "POST", "/api/v1/library/submit",
                                 body=body, **auth)
    assert status == 202, result
    assert result["state"] == "accepted", result
    child = result["children"][0]
    assert child["request_id"] == plans.child_request_id(body["request_id"], plan["id"],
                                                        "primary")
    assert _wait(service, child["request_id"])["state"] == "completed"
    second = _request(host, "POST", "/api/v1/library/submit", body=body, **auth)
    assert second[0] == 202
    assert second[2]["children"][0]["request_id"] == child["request_id"]
    assert len(state["started"]) == 1
    assert (directory / "checkpoints/fixture/Image/checkpoint.safetensors").read_bytes() == PAYLOAD


def test_group_preflight_rejects_existing_file_before_admission(image_store):
    host, service, auth, state, directory = image_store
    plan = _request(host, "POST", "/api/v1/settings/models/image-install-plans",
                    body={"action": "create", "model": MODEL, "profile": "file-only"},
                    **auth)[2]
    target = directory / "checkpoints/fixture/Image/checkpoint.safetensors"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"other file")
    status, _, response = _request(host, "POST", "/api/v1/library/review",
                                   body={"draft": {"operation": "model-image-install-plan",
                                                   "plan_id": plan["id"], "slots": ["primary"]}},
                                   **auth)
    assert status == 400, response
    assert not service.model_jobs()["items"]
    assert not state["started"]
    assert target.read_bytes() == b"other file"


def test_group_partial_dispatch_resumes_only_unsubmitted_child(image_store, monkeypatch):
    host, service, auth, state, directory = image_store
    state["include_second"] = True
    first = plans.create(service.cfg, MODEL, "file-only")
    second = plans.create(service.cfg, "hf.co/fixture/Image:another.safetensors",
                          "file-only")
    selection = copy.deepcopy(first["selection"])
    extra = copy.deepcopy(second["selection"]["components"][0])
    extra["slot"] = "llm"
    extra["label"] = "Second file"
    selection["components"].append(extra)
    selection["total_bytes"] += extra["size"]
    identity = plans.digest(selection)
    path = service.cfg.data_dir / "image-install-plans.json"
    document = json.loads(path.read_text())
    document["items"][identity] = {"selection": selection, "checked_at": first["checked_at"],
                                   "existing_unverified": [], "free_bytes": first["free_bytes"]}
    path.write_text(json.dumps(document))
    review = _review(host, auth, {"operation": "model-image-install-plan",
                                  "plan_id": identity, "slots": ["primary", "llm"]})
    original = service.submit
    failures = {"remaining": 1}

    def fail_second(owner, token, request_id, **kwargs):
        if (service._reviews[token].operation == "model-image-download"
                and request_id == plans.child_request_id(parent, identity, "llm")
                and failures["remaining"]):
            failures["remaining"] -= 1
            raise ValueError("temporary child admission failure")
        return original(owner, token, request_id, **kwargs)

    parent = uuid.uuid4().hex
    monkeypatch.setattr(service, "submit", fail_second)
    body = {"review_id": review["review_id"], "request_id": parent, "control_epoch": 0}
    status, _, partial = _request(host, "POST", "/api/v1/library/submit", body=body, **auth)
    assert status == 202
    assert partial["state"] == "partial"
    assert [row["slot"] for row in partial["children"]] == ["primary", "llm"]
    assert partial["children"][1]["state"] == "not_submitted"
    assert _wait(service, partial["children"][0]["request_id"])["state"] == "completed"
    status, _, resumed = _request(host, "POST", "/api/v1/library/submit", body=body,
                                  **auth)
    assert status == 202
    assert resumed["state"] == "accepted"
    assert _wait(service, resumed["children"][1]["request_id"])["state"] == "completed"
    assert len(state["started"]) == 2
    assert (directory / "checkpoints/fixture/Image/another.safetensors").read_bytes() == PAYLOAD


def test_server_candidates_are_category_scoped_and_never_content_verified(environment, monkeypatch):
    from klaude_application import image_model_selection

    cfg, root, state = environment
    plan = plans.create(cfg, MODEL, "flux3-klein")
    destination = plan["selection"]["components"][0]["destination"]
    files = [{"id": destination, "name": "Primary", "category": "diffusion_models"},
             {"id": "elsewhere/" + destination, "name": "Duplicate", "category": "vae"}]
    calls = []

    def catalog(*args, **kwargs):
        calls.append(kwargs)
        return {"files": copy.deepcopy(files)}

    monkeypatch.setattr(image_model_selection, "catalog", catalog)
    result = plans.check_server(cfg, plan["id"], "http://example.test")
    assert calls == [{"refresh": True}]
    assert [row["visibility"] for row in result["components"]] == [
        "candidate", "not_visible", "not_visible"]
    assert all(row["content"] == "unverified" for row in result["components"])
    files.append({"id": "other/" + destination, "name": "Duplicate",
                  "category": "diffusion_models"})
    assert plans.check_server(cfg, plan["id"], "url")["components"][0]["visibility"] == "ambiguous"
    files.clear()
    result = plans.check_server(cfg, plan["id"], "url")
    assert result["components"][0]["visibility"] == "not_visible"
    assert not list(root.iterdir())
