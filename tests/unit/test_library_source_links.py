"""Optional source metadata uses the existing exact-revision review/effect path."""

import hashlib
import uuid

import pytest
from klaude_core.library_artifacts import PAGE_SIZE, ArtifactStore, source_link

from .test_library_management import _wait
from .test_web_library import browser_library as browser_library
from .test_webhost import _request


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        12,
        "notes\x00hidden",
        "notes\x1bhidden",
        "https://example.test/" + "a" * 2048,
    ],
)
def test_invalid_source_links_are_rejected(value):
    with pytest.raises(ValueError):
        source_link(value)


@pytest.mark.parametrize(
    "value",
    [
        "From a Discord conversation",
        "example.com/profile",
        "@artist — original creator",
        "First line\nSecond line",
        "javascript:alert(1)",
        "<script>hello</script>",
    ],
)
def test_source_notes_are_stored_as_literal_text(tmp_path, value):
    store = ArtifactStore(tmp_path / "library")
    item = store.import_bytes(b"Document", "document", "note.txt")
    saved = store.change(item["id"], item["revision"], "source_link", value)
    assert saved["source_url"] == value
    assert store.get(item["id"])["source_url"] == value


def test_optional_links_preserve_legacy_read_only_stores_and_exact_revisions(tmp_path):
    store = ArtifactStore(tmp_path / "library")
    item = store.import_bytes(b"Document", "document", "note.txt")
    with store.database(write=True) as db:
        db.execute("DROP TABLE artifact_links")
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    assert store.get(item["id"])["source_url"] == ""
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before
    linked = store.change(
        item["id"], item["revision"], "source_link", " https://example.test/image?a=1#original "
    )
    assert linked["source_url"] == "https://example.test/image?a=1#original"
    assert linked["sha256"] == item["sha256"]
    assert linked["revision"] == item["revision"] + 1
    with pytest.raises(ValueError, match="changed"):
        store.change(item["id"], item["revision"], "source_link", "https://other.test")
    archived = store.change(item["id"], linked["revision"], "archive")
    assert archived["source_url"] == linked["source_url"]
    store.change(item["id"], archived["revision"], "delete")
    with store.database() as db:
        assert db.execute("SELECT count(*) FROM artifact_links").fetchone()[0] == 0


def test_source_review_is_authenticated_private_revisioned_and_durable(browser_library):
    host, service, auth = browser_library
    item = service.artifacts.import_bytes(b"Saved document", "document", "saved.txt")
    source = "http://127.0.0.1:9/no-network-request"

    def prepare(value, revision):
        return _request(
            host,
            "POST",
            "/api/v1/library/review",
            body={
                "draft": {
                    "operation": "source_link",
                    "target": item["id"],
                    "revision": revision,
                    "value": value,
                }
            },
            **auth,
        )

    draft = {
        "draft": {
            "operation": "source_link",
            "target": item["id"],
            "revision": item["revision"],
            "value": source,
        }
    }
    assert (
        _request(host, "POST", "/api/v1/library/review", body=draft, origin=host.origin)[0] == 401
    )
    assert (
        _request(host, "POST", "/api/v1/library/review", body=draft, **{**auth, "csrf": ""})[0]
        == 403
    )
    assert prepare("notes\x00hidden", item["revision"])[0] == 400
    status, _, review = prepare(source, item["revision"])
    assert status == 200 and source in review["summary"]
    assert service.artifacts.get(item["id"])["source_url"] == ""
    identity = uuid.uuid4().hex
    body = {
        "review_id": review["review_id"],
        "request_id": identity,
        "control_epoch": host.public_snapshot(auth["client_id"])["control_epoch"],
    }
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    assert _wait(service, identity)["state"] == "completed"
    assert _request(host, "POST", "/api/v1/library/submit", body=body, **auth)[0] == 202
    current = service.detail(item["id"])["item"]
    assert current["source_url"] == source
    assert current["revision"] == item["revision"] + 1
    assert "origin" not in current
    assert prepare("https://stale.test", item["revision"])[0] == 400
    status, _, review = prepare("", current["revision"])
    assert status == 200
    identity = uuid.uuid4().hex
    assert (
        _request(
            host,
            "POST",
            "/api/v1/library/submit",
            body={
                "review_id": review["review_id"],
                "request_id": identity,
                "control_epoch": host.public_snapshot(auth["client_id"])["control_epoch"],
            },
            **auth,
        )[0]
        == 202
    )
    assert _wait(service, identity)["state"] == "completed"
    assert service.detail(item["id"])["item"]["source_url"] == ""


def test_source_note_search_is_literal_scoped_and_counted_before_paging(tmp_path):
    store = ArtifactStore(tmp_path / "library")
    identities = []
    count = PAGE_SIZE + 3
    for index in range(count):
        path = tmp_path / f"file-{index}.txt"
        path.write_text(str(index))
        item = store.import_file(path, "document", session="conversation-a")
        store.change(
            item["id"],
            item["revision"],
            "source_link",
            "From Discord\nOriginal source https://example.test/creator\n100%_literal",
        )
        identities.append(item["id"])
    first = store.listing("all", query="DISCORD", include_total=True, sort="name")
    assert first["total"] == count and first["more"]
    second = store.listing(
        "all", query="discord", offset=len(first["items"]), include_total=True, sort="name"
    )
    assert second["total"] == count and not second["more"]
    assert {item["id"] for item in first["items"] + second["items"]} == set(identities)
    assert store.listing("all", query="100%_literal", include_total=True)["total"] == count
    assert (
        store.listing("all", query="https://example.test/creator", include_total=True)["total"]
        == count
    )
    assert store.listing("all", query="%' OR 1=1 --", include_total=True)["total"] == 0
    assert (
        store.listing("all", query="discord", session="conversation-b", include_total=True)["total"]
        == 0
    )
    current = store.get(identities[0])
    store.change(current["id"], current["revision"], "archive")
    assert store.listing("all", query="discord", include_total=True)["total"] == count - 1
    assert store.listing("all", query="discord", archived=True, include_total=True)["total"] == 1


def test_searching_legacy_store_does_not_create_source_table(tmp_path):
    store = ArtifactStore(tmp_path / "library")
    store.import_bytes(b"Document", "document", "legacy.txt")
    with store.database(write=True) as db:
        db.execute("DROP TABLE artifact_links")
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    assert len(store.listing("all", query="legacy")["items"]) == 1
    assert not store.listing("all", query="missing notes")["items"]
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before
