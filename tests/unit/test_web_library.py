"""Authenticated browser Library routes using shared stores and real owned jobs."""

import hashlib
import http.client
import io
import threading
import time
import uuid
from urllib.parse import urlencode

import pytest
from klaude_application.library_management import LibraryManagement
from klaude_core.config import Config
from klaude_webhost.host import LocalWebHost
from PIL import Image

from .test_library_management import _wait
from .test_webhost import _app, _request


@pytest.fixture
def browser_library(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    service = LibraryManagement(Config(), tmp_path)
    host = LocalWebHost(_app(tmp_path), library=service, staging_dir=tmp_path / "staging")
    thread = threading.Thread(target=host.serve_forever, daemon=True)
    thread.start()
    try:
        _, headers, login = _request(host, "POST", "/api/v1/auth/exchange",
                                     body={"code": host.bootstrap_url.partition("#")[2]},
                                     origin=host.origin)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        auth = {"cookie": cookie, "csrf": login["csrf"], "origin": host.origin}
        _, _, client = _request(host, "POST", "/api/v1/clients", body={}, **auth)
        auth["client_id"] = client["client_id"]
        yield host, service, auth
    finally:
        host.stop()
        thread.join(timeout=3)


def _bytes_request(host, path, cookie):
    conn = http.client.HTTPConnection("127.0.0.1", host.http.server_port, timeout=3)
    conn.request("GET", path, headers={"Cookie": cookie})
    result = conn.getresponse()
    response = result.status, dict(result.getheaders()), result.read()
    conn.close()
    return response


def test_library_assets_navigation_and_reads_require_authentication(browser_library):
    host, service, auth = browser_library
    for path in ("/api/v1/library/items", "/api/v1/library/knowledge",
                 "/api/v1/library/operations", "/api/v1/integrations/skills"):
        assert _request(host, "GET", path)[0] == 401
        assert _request(host, "GET", path, **auth)[0] == 200
        assert _request(host, "GET", path, fetch_site="cross-site", **auth)[0] == 403
    status, _, payload = _bytes_request(host, "/", "")
    assert status == 200 and b'id="library-view"' in payload
    assert b'id="integrations-view"' in payload
    assert b'id="nav-library" class="nav-item" type="button">' in payload
    status, headers, payload = _bytes_request(host, "/library.js", "")
    assert status == 200 and "javascript" in headers["Content-Type"]
    assert "img-src 'self'" in headers["Content-Security-Policy"]
    assert b"innerHTML" not in payload
    assert not (service.data / "knowledge.lance").exists()


def test_read_routes_support_twenty_item_pages_and_reject_invalid_offsets(browser_library):
    host, service, auth = browser_library
    for index in range(21):
        service.artifacts.import_bytes(b"Saved", "document", f"file-{index:02}.txt")
    first = _request(host, "GET", "/api/v1/library/items?sort=name", **auth)[2]
    last = _request(host, "GET", "/api/v1/library/items?sort=name&offset=20", **auth)[2]
    assert len(first["items"]) == 20 and first["more"]
    assert len(last["items"]) == 1 and not last["more"]
    assert last["offset"] == last["page_size"] == 20
    for route in ("/api/v1/library/items", "/api/v1/library/knowledge",
                  "/api/v1/library/sources", "/api/v1/integrations/skills"):
        assert _request(host, "GET", route + "?offset=20", **auth)[0] == 200
        for offset in ("-1", "true", "1000001", "0&offset=20"):
            assert _request(host, "GET", route + "?offset=" + offset, **auth)[0] == 400


@pytest.mark.parametrize("image_format,filename", [
    (None, "notes.txt"),
    ("PNG", "renamed.txt"),
    ("JPEG", "photo.jpeg"),
    ("WEBP", "picture.webp"),
    ("GIF", "animation.gif"),
])
def test_browser_import_review_confirm_status_and_logout_ownership(
    browser_library, image_format, filename,
):
    host, service, auth = browser_library
    content = b"Hello from browser"
    if image_format:
        output = io.BytesIO()
        Image.new("RGB", (3, 2), "red").save(output, format=image_format)
        content = output.getvalue()
    owner = hashlib.sha256(auth["cookie"].split("=", 1)[1].encode()).hexdigest()
    staged = host.transfers.upload(owner, io.BytesIO(content), len(content), filename)
    draft = {"operation": "import", "upload_id": staged.id}
    no_csrf = {**auth, "csrf": ""}
    assert _request(host, "POST", "/api/v1/library/review", body={"draft": draft},
                    **no_csrf)[0] == 403
    status, _, review = _request(host, "POST", "/api/v1/library/review",
                                 body={"draft": draft}, **auth)
    assert status == 200
    assert ("as an image" if image_format else "as a file") in review["summary"]
    assert service.listing()["items"] == []
    with pytest.raises(FileNotFoundError):
        host.transfers.open_download(owner, staged.id)
    identity = uuid.uuid4().hex
    epoch = host.public_snapshot(auth["client_id"])["control_epoch"]
    body = {"review_id": review["review_id"], "request_id": identity, "control_epoch": epoch}
    status, _, result = _request(host, "POST", "/api/v1/library/submit", body=body, **auth)
    assert status == 202
    assert result["request_id"] == identity
    assert _wait(service, identity)["state"] == "completed"
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    items = service.listing(kind="all")["items"]
    assert len(items) == 1
    item = items[0]
    assert item["kind"] == ("media" if image_format else "document")
    assert item["filename"] == filename
    assert item["sha256"] == hashlib.sha256(content).hexdigest()
    if image_format:
        assert item["mime"] == "image/" + image_format.lower()
        assert (item["width"], item["height"]) == (3, 2)
        assert service.listing(kind="all", images_only=True)["items"][0]["id"] == item["id"]
    assert _request(host, "GET", "/api/v1/library/operation?" + urlencode({"id": identity}),
                    **auth)[2]["state"] == "completed"
    assert _request(host, "POST", "/api/v1/auth/logout", body={}, **auth)[0] == 200
    assert _request(host, "GET", "/api/v1/library/items", **auth)[0] == 401
    assert len(service.listing(kind="all")["items"]) == 1


@pytest.mark.parametrize("image_format", ["PNG", "JPEG", "WEBP"])
def test_reupload_image_preserves_added_time_in_library_reads(browser_library, image_format):
    host, service, auth = browser_library
    output = io.BytesIO()
    Image.new("RGB", (3, 2), "red").save(output, image_format)
    content = output.getvalue()
    original = service.artifacts.import_bytes(content, "media", "original.png")
    original = service.artifacts.change(original["id"], original["revision"], "tags", "saved")
    with service.artifacts.database(write=True) as db:
        db.execute("UPDATE artifacts SET created=? WHERE id=?", (1_700_000_000, original["id"]))
    original = service.artifacts.get(original["id"])
    owner = hashlib.sha256(auth["cookie"].split("=", 1)[1].encode()).hexdigest()
    staged = host.transfers.upload(owner, io.BytesIO(content), len(content), "renamed.png")
    status, _, review = _request(host, "POST", "/api/v1/library/review",
                                 body={"draft": {"operation": "import", "upload_id": staged.id}},
                                 **auth)
    assert status == 200
    identity = uuid.uuid4().hex
    epoch = host.public_snapshot(auth["client_id"])["control_epoch"]
    status, _, _ = _request(host, "POST", "/api/v1/library/submit", body={
        "review_id": review["review_id"], "request_id": identity, "control_epoch": epoch,
    }, **auth)
    assert status == 202
    assert _wait(service, identity)["state"] == "completed"
    assert service.artifacts.get(original["id"]) == original
    items = _request(host, "GET", "/api/v1/library/items?kind=all", **auth)[2]["items"]
    assert len(items) == 1
    assert items[0]["id"] == original["id"]
    assert items[0]["created"] == original["created"]
    detail = _request(host, "GET", "/api/v1/library/item?" + urlencode({"id": original["id"]}),
                      **auth)[2]["item"]
    assert detail["created"] == original["created"]
    assert detail["revision"] == original["revision"] and detail["tags"] == ["saved"]


@pytest.mark.parametrize("kind", ["document", "media", "research"])
def test_saved_files_delete_after_review_without_archiving(browser_library, kind):
    host, service, auth = browser_library
    if kind == "research":
        item = service.artifacts.store_report("report.md", "Saved report", job="fixture")
    elif kind == "media":
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "teal").save(output, format="PNG")
        item = service.artifacts.import_bytes(output.getvalue(), kind, "saved.png")
    else:
        item = service.artifacts.import_bytes(b"Saved bytes", kind, "saved.txt")
    draft = {"operation": "delete", "target": item["id"], "revision": item["revision"]}
    status, _, review = _request(host, "POST", "/api/v1/library/review",
                                 body={"draft": draft}, **auth)
    assert status == 200 and "cannot be undone" in review["summary"]
    assert not service.artifacts.get(item["id"])["archived"]
    assert _request(host, "POST", "/api/v1/library/discard",
                    body={"review_id": review["review_id"]}, **auth)[0] == 200
    assert service.artifacts.get(item["id"])["revision"] == item["revision"]

    _, _, review = _request(host, "POST", "/api/v1/library/review",
                            body={"draft": draft}, **auth)
    identity = uuid.uuid4().hex
    body = {"review_id": review["review_id"], "request_id": identity,
            "control_epoch": host.public_snapshot(auth["client_id"])["control_epoch"]}
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert _wait(service, identity)["state"] == "completed"
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    with pytest.raises(ValueError, match="no longer exists"):
        service.artifacts.get(item["id"])


@pytest.mark.parametrize("changed", [False, True])
def test_selected_delete_is_reviewed_atomic_and_deduplicated(browser_library, changed):
    host, service, auth = browser_library
    items = [service.artifacts.import_bytes(f"Saved {index}".encode(), "document",
                                            f"selected-{index}.txt") for index in range(10)]
    items.append(service.artifacts.store_report("selected.md", "Report", job="fixture"))
    untouched = service.artifacts.import_bytes(b"Keep", "document", "keep.txt")
    draft = {"operation": "delete-selected", "targets": [
        {"target": item["id"], "revision": item["revision"]} for item in items
    ]}
    status, _, review = _request(host, "POST", "/api/v1/library/review",
                                 body={"draft": draft}, **auth)
    assert status == 200 and "11 selected files" in review["summary"]
    assert all(item["name"] in review["summary"] for item in items)
    # Discarding a selection review never deletes anything.
    assert _request(host, "POST", "/api/v1/library/discard",
                    body={"review_id": review["review_id"]}, **auth)[0] == 200
    assert all(service.artifacts.get(item["id"]) for item in items)
    _, _, review = _request(host, "POST", "/api/v1/library/review",
                            body={"draft": draft}, **auth)
    if changed:
        item = items[-1]
        service.artifacts.change(item["id"], item["revision"], "tags", "changed")
    identity = uuid.uuid4().hex
    body = {"review_id": review["review_id"], "request_id": identity,
            "control_epoch": host.public_snapshot(auth["client_id"])["control_epoch"]}
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert _wait(service, identity)["state"] == ("failed" if changed else "completed")
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert service.artifacts.get(untouched["id"]) == untouched
    for item in items:
        if changed:
            assert service.artifacts.get(item["id"])
        else:
            with pytest.raises(ValueError, match="no longer exists"):
                service.artifacts.get(item["id"])


def test_selected_delete_rejects_invalid_or_stale_selections(browser_library):
    host, service, auth = browser_library
    item = service.artifacts.import_bytes(b"Saved", "document", "saved.txt")
    target = {"target": item["id"], "revision": item["revision"]}
    for targets in ([], [target] * 101, [target, target],
                    [{**target, "revision": True}], [{**target, "revision": -1}],
                    [{**target, "extra": "field"}], [None]):
        assert _request(host, "POST", "/api/v1/library/review", body={"draft": {
            "operation": "delete-selected", "targets": targets,
        }}, **auth)[0] == 400
    assert service.artifacts.get(item["id"]) == item


def test_selected_delete_fences_other_artifact_changes(browser_library, monkeypatch):
    host, service, auth = browser_library
    item = service.artifacts.import_bytes(b"Saved", "document", "saved.txt")
    owner = "fixture-owner"
    draft = {"operation": "delete-selected", "targets": [
        {"target": item["id"], "revision": item["revision"]},
    ]}
    review = service.prepare(owner, draft)
    single = service.prepare(owner, {"operation": "delete", "target": item["id"],
                                    "revision": item["revision"]})
    # Keep the owned worker at admission to check both directions of the fence.
    monkeypatch.setattr(service._jobs, "submit", lambda *args, **kwargs: None)
    from klaude_application.operation_journal import OperationConflict

    prior = service.journal.admit(request_id=uuid.uuid4().hex, owner_id="web-admin",
                                  kind="tags", resource=f"artifact:{item['id']}", payload={})
    with pytest.raises(OperationConflict):
        service.submit(owner, review["review_id"], uuid.uuid4().hex)
    service.journal.finish(prior.request_id, "web-admin", prior.fence,
                           state="cancelled", outcome="cancelled")
    service.submit(owner, review["review_id"], uuid.uuid4().hex)
    with pytest.raises(OperationConflict):
        service.submit(owner, single["review_id"], uuid.uuid4().hex)


def test_previews_downloads_and_revisions_do_not_execute_documents(browser_library):
    host, service, auth = browser_library
    item = service.artifacts.import_bytes(b"<script>secret()</script>", "document", "unsafe.html")
    path = "/api/v1/library/content?" + urlencode({"id": item["id"], "revision": item["revision"]})
    status, headers, payload = _bytes_request(host, path, auth["cookie"])
    assert status == 200 and payload == b"<script>secret()</script>"
    assert headers["Content-Type"] == "application/octet-stream"
    assert headers["Content-Disposition"] == 'attachment; filename="unsafe.html"'
    assert _bytes_request(host, path + "&inline=1", auth["cookie"])[0] == 400
    service.artifacts.change(item["id"], item["revision"], "archive")
    assert _bytes_request(host, path, auth["cookie"])[0] == 400
    assert _bytes_request(host, path, "")[0] == 401
    data = io.BytesIO()
    Image.new("RGB", (32, 32), "red").save(data, format="PNG")
    image = service.artifacts.import_bytes(data.getvalue(), "media", "red.png")
    path = "/api/v1/library/content?" + urlencode({"id": image["id"],
                                                   "revision": image["revision"], "inline": "1"})
    status, headers, payload = _bytes_request(host, path, auth["cookie"])
    assert status == 200 and headers["Content-Type"] == "image/png"
    assert "Content-Disposition" not in headers and payload == data.getvalue()
    with service.artifacts.database(write=True) as db:
        db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"corrupt", image["id"]))
    assert _bytes_request(host, path, auth["cookie"])[0] == 400


def test_authenticated_source_preview_preserves_text_and_public_projection(browser_library):
    host, service, auth = browser_library
    source = "<script>unsafe()</script>\r\n\t  " + "long line " * 90 + "\r\n"
    item = service.artifacts.import_bytes(source.encode(), "document", "source.html")
    path = "/api/v1/library/item?" + urlencode({"id": item["id"]})
    assert _request(host, "GET", path)[0] == 401
    assert _request(host, "GET", path, fetch_site="cross-site", **auth)[0] == 403
    status, _, detail = _request(host, "GET", path, **auth)
    assert status == 200
    assert detail["source_text"] == source
    assert not detail["source_truncated"] and not detail["source_sanitized"]
    assert detail["truncated"]  # Legacy terminal lines retain their own limit.
    assert "origin" not in detail["item"] and "content" not in detail["item"]
    download = "/api/v1/library/content?" + urlencode({
        "id": item["id"], "revision": item["revision"],
    })
    result, headers, content = _bytes_request(host, download, auth["cookie"])
    assert result == 200 and content == source.encode()
    assert headers["Content-Type"] == "application/octet-stream"


@pytest.mark.parametrize("kind", ["document", "media"])
@pytest.mark.parametrize("lossless", [False, True])
def test_existing_webp_files_preview_with_bounded_recovered_dimensions(
    browser_library, kind, lossless,
):
    host, service, auth = browser_library
    output = io.BytesIO()
    Image.new("RGB", (37, 23), "teal").save(output, "WEBP", lossless=lossless)
    original = output.getvalue()
    item = service.artifacts.import_bytes(original, kind, "existing.webp")
    with service.artifacts.database(write=True) as db:
        db.execute("UPDATE artifacts SET width=NULL,height=NULL WHERE id=?", (item["id"],))
    listed = _request(host, "GET", "/api/v1/library/items?kind=all", **auth)[2]["items"][0]
    detail = _request(host, "GET", "/api/v1/library/item?" + urlencode({"id": item["id"]}),
                      **auth)[2]["item"]
    assert (listed["width"], listed["height"]) == (37, 23)
    assert detail == {**listed, "source_url": ""}
    path = "/api/v1/library/content?" + urlencode({
        "id": item["id"], "revision": item["revision"], "inline": "1",
    })
    status, headers, payload = _bytes_request(host, path, auth["cookie"])
    assert status == 200 and headers["Content-Type"] == "image/webp"
    assert "Content-Disposition" not in headers and payload == original
    assert headers["X-Content-Type-Options"] == "nosniff"
    with service.artifacts.database() as db:
        stored = db.execute("SELECT width,height,revision FROM artifacts WHERE id=?",
                            (item["id"],)).fetchone()
        assert tuple(stored) == (None, None, item["revision"])


def test_webp_preview_keeps_existing_dimension_limit(browser_library):
    host, service, auth = browser_library
    output = io.BytesIO()
    Image.new("RGB", (4097, 1), "teal").save(output, "WEBP", lossless=True)
    item = service.artifacts.import_bytes(output.getvalue(), "media", "too-wide.webp")
    with service.artifacts.database(write=True) as db:
        db.execute("UPDATE artifacts SET width=NULL,height=NULL WHERE id=?", (item["id"],))
    path = "/api/v1/library/content?" + urlencode({
        "id": item["id"], "revision": item["revision"], "inline": "1",
    })
    assert _bytes_request(host, path, auth["cookie"])[0] == 400
    download = path.replace("&inline=1", "")
    assert _bytes_request(host, download, auth["cookie"])[2] == output.getvalue()


def test_reviews_are_tab_bound_and_control_epoch_is_required(browser_library):
    host, service, auth = browser_library
    item = service.artifacts.import_bytes(b"Saved", "document", "saved.txt")
    _, _, review = _request(host, "POST", "/api/v1/library/review", body={"draft": {
        "operation": "archive", "target": item["id"], "revision": item["revision"],
    }}, **auth)
    _, _, another = _request(host, "POST", "/api/v1/clients", body={}, **auth)
    body = {"review_id": review["review_id"], "request_id": uuid.uuid4().hex, "control_epoch": 0}
    other_auth = {**auth, "client_id": another["client_id"]}
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **other_auth)[0] == 400
    turn_id = uuid.uuid4().hex
    assert _request(host, "POST", "/api/v1/turns", body={
        "request_id": turn_id, "text": "Create session control",
    }, **auth)[0] == 202
    deadline = time.monotonic() + 3
    while host.application.receipt(turn_id).state != "completed" and time.monotonic() < deadline:
        time.sleep(0.02)
    epoch = host.public_snapshot(auth["client_id"])["control_epoch"]
    _, _, control = _request(host, "POST", "/api/v1/control/claim", body={
        "request_id": uuid.uuid4().hex, "expected_epoch": epoch,
    }, **auth)
    assert "error" not in control
    body["control_epoch"] = -1
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 409
    assert not service.artifacts.get(item["id"])["archived"]


def test_tab_count_route_is_authenticated_unfiltered_and_read_only(browser_library):
    host, service, auth = browser_library
    route = "/api/v1/library/counts"
    assert _request(host, "GET", route)[0] == 401
    assert _request(host, "GET", route, fetch_site="cross-site", **auth)[0] == 403
    assert _request(host, "GET", route + "?query=anything", **auth)[0] == 400
    status, _, counts = _request(host, "GET", route, **auth)
    assert status == 200 and all(value["total"] == 0 for value in counts.values())
    assert not service.data.exists() or list(service.data.iterdir()) == []
    service.artifacts.import_bytes(b"Saved", "document", "example.txt")
    assert _request(host, "GET", route, **auth)[2]["document"]["total"] == 1
    assert _request(host, "GET", route, **auth)[2]["archive"]["total"] == 0
