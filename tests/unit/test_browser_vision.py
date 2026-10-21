"""Actual browser pixel requests, private results, reviews and cancellation."""

import json
import time
import uuid

import pytest
from klaude_application.browser_results import BrowserResults
from klaude_core.library_artifacts import ArtifactStore

from .test_library_management import _wait
from .test_vision import vision_lab as vision_lab
from .test_web_management import _review, _submit
from .test_web_management import profile_browser as profile_browser
from .test_webhost import _request


@pytest.fixture
def image_browser(profile_browser, vision_lab):
    host, service, memory, auth = profile_browser
    cfg, connection, store, item, calls, mode, arrived, _ = vision_lab
    service.cfg.ollama_url = cfg.ollama_url
    service.cfg.config_dir.mkdir(parents=True, exist_ok=True)
    (service.cfg.config_dir / "config.toml").write_text(
        f'[services]\nollama_url="{cfg.ollama_url}"\n'
    )
    yield host, service, auth, store, item, calls, mode, arrived


def _draft(item, operation="vision-analyze"):
    return {"operation": operation, "target": item["id"], "revision": item["revision"],
            "context": 4096, "output_tokens": 512,
            **({"question": "Describe the visible shapes"}
               if operation == "vision-analyze" else {})}


def _results(host, auth, item):
    return _request(host, "GET", f"/api/v1/library/vision?artifact={item['id']}"
                                 f"&revision={item['revision']}", **auth)


def test_browser_analysis_sends_pixels_only_after_review_and_keeps_results_private(image_browser):
    host, service, auth, store, item, calls, _, _ = image_browser
    route = f"/api/v1/library/vision?artifact={item['id']}&revision=1"
    assert _request(host, "GET", route)[0] == 401
    assert _request(host, "GET", route, fetch_site="cross-site", **auth)[0] == 403
    assert _results(host, auth, item)[2]["items"] == []
    before = store.get(item["id"])
    review = _review(host, auth, _draft(item))
    assert not calls
    receipt, body = _submit(host, service, auth, review)
    assert receipt["state"] == "completed"
    sent = [body for path, body in calls if path == "/api/chat"]
    assert len(sent) == 1 and sent[0]["messages"][1]["images"]
    response = _results(host, auth, item)[2]
    assert response["items"][0]["text"] == "Three colored rectangles."
    assert response["items"][0]["kind"] == "analysis"
    assert "endpoint" not in json.dumps(response) and "provenance" not in json.dumps(response)
    assert store.get(item["id"]) == before
    assert not host.application.memory.load_session(host.application.session_id)
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert len([body for path, body in calls if path == "/api/chat"]) == 1
    assert BrowserResults(service.data).path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("kind", ["media", "document"])
def test_tag_suggestions_are_unselected_and_only_reviewed_offers_are_saved(image_browser, kind):
    host, service, auth, store, item, calls, mode, _ = image_browser
    if kind == "document":
        data = store.read_content(item["id"], item["revision"])
        item = store.import_bytes(data, "document", "image-as-document.png")
    item = store.change(item["id"], item["revision"], "tags", "manual")
    mode["text"] = '["amber", "diagram", "manual"]'
    receipt, _ = _submit(host, service, auth, _review(host, auth, _draft(item, "vision-tags")))
    assert receipt["state"] == "completed"
    proposal = _results(host, auth, item)[2]["items"][0]
    assert proposal["tags"] == ["amber", "diagram", "manual"]
    assert "selected" not in proposal and "proposal" not in proposal
    assert store.get(item["id"])["ai_tags"] == []
    for selected in ([], ["invented"]):
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
            "operation": "vision-tags-apply", "result": proposal["id"], "selected": selected,
        }}, **auth)[0] == 400
    review = _review(host, auth, {"operation": "vision-tags-apply", "result": proposal["id"],
                                 "selected": ["amber", "manual"]})
    assert _submit(host, service, auth, review)[0]["state"] == "completed"
    current = store.get(item["id"])
    assert current["tags"] == ["manual"] and current["ai_tags"] == ["amber"]
    assert len([body for path, body in calls if path == "/api/chat"]) == 1
    assert _results(host, auth, item)[0] == 400


def test_changed_or_corrupt_image_rejects_before_model_work(image_browser):
    host, service, auth, store, item, calls, _, _ = image_browser
    review = _review(host, auth, _draft(item))
    store.change(item["id"], item["revision"], "archive")
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not calls
    item = store.get(item["id"])
    item = store.change(item["id"], item["revision"], "restore")
    review = _review(host, auth, _draft(item))
    with store.database(write=True) as db:
        db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"corrupt", item["id"]))
    assert _submit(host, service, auth, review)[0]["state"] == "failed"
    assert not calls


def test_cancel_waits_for_owned_worker_stop_before_releasing_vision_resource(image_browser):
    host, service, auth, _, item, _, mode, arrived = image_browser
    mode["value"] = "slow"
    review = _review(host, auth, _draft(item))
    identity = uuid.uuid4().hex
    status, _, receipt = _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": identity, "control_epoch": 0,
    }, **auth)
    assert status == 202 and arrived.wait(8)
    assert _results(host, auth, item)[2]["pending"]["cancellable"]
    status, _, cancelled = _request(host, "POST", "/api/v1/library/cancel", body={
        "request_id": identity,
    }, **auth)
    assert status == 200 and cancelled["state"] in {"cancelling", "cancelled"}
    assert _wait(service, identity)["state"] == "cancelled"
    assert not service.journal.resource_busy("vision:" + item["id"])
    assert _results(host, auth, item)[2] == {
        "items": [], "pending": None, "available_hours": 24,
    }
    assert _request(host, "POST", "/api/v1/library/cancel", body={
        "request_id": identity,
    }, **auth)[2]["state"] == "cancelled"


def test_result_store_is_bounded_and_expired_results_cannot_be_read(tmp_path, monkeypatch):
    import klaude_application.browser_results as results_module

    artifact = ArtifactStore(tmp_path / "library").import_bytes(b"hello", "document", "x.txt")
    store = BrowserResults(tmp_path)
    monkeypatch.setattr(results_module, "MAX_ITEMS", 3)
    identities = [uuid.uuid4().hex for _ in range(5)]
    for identity in identities:
        store.put(identity, artifact["id"], 1, {"text": "private output"})
    assert len(store.listing(artifact["id"], 1)) == 3
    with pytest.raises(ValueError):
        store.get(identities[0])
    monkeypatch.setattr(results_module.time, "time", lambda: time.time_ns() / 1e9 + 90_000)
    with pytest.raises(ValueError):
        store.get(identities[-1])
