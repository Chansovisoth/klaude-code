"""Knowledge browsing reads the real active index; deletion checks the reviewed snapshot."""

from __future__ import annotations

import uuid

import pytest
from klaude_application.browser_knowledge import MAX_CHUNK, browse_knowledge, delete_knowledge
from klaude_application.library_management import OWNER, run_management_operation
from klaude_knowledge.store import KnowledgeStore

from .test_library_management import _wait
from .test_library_management import manager as manager


@pytest.fixture
def indexed(manager):
    store = KnowledgeStore(manager.data / "knowledge.lance")
    yield store
    store.fts.close()


def add(store, library="guides", source="https://example.com/guide", texts=None):
    texts = texts or [f"Paragraph {i}: C++ uses atomic transactions. Straße.\n" for i in range(45)]
    store.add(library, texts, [[1.0, 0.0] for _ in texts], source)


def test_browse_is_readonly_and_never_initializes_missing_stores(manager, monkeypatch):
    monkeypatch.setattr(KnowledgeStore, "__init__", lambda *_: pytest.fail("store initialized"))
    assert manager.knowledge_contents()["items"] == []
    assert manager.knowledge_contents(query="unseen")["total"] == 0
    assert list(manager.data.iterdir()) == []


def test_library_source_and_chunk_pages_use_exact_active_content(manager, indexed):
    add(indexed)
    add(indexed, source="artifact:document-1", texts=["Uploaded notes"])
    add(indexed, "other", texts=["Unrelated"])
    libraries = manager.knowledge_contents()
    assert [(item["id"], item["chunks"]) for item in libraries["items"]] == [
        ("guides", 46),
        ("other", 1),
    ]
    sources = manager.knowledge_contents(library="guides", sources=True)
    assert sources["total"] == 2
    pages = [manager.knowledge_contents(library="guides", offset=offset) for offset in (0, 20, 40)]
    assert [len(page["items"]) for page in pages] == [20, 20, 6]
    assert all(page["total"] == 46 for page in pages)
    assert len({item["id"] for page in pages for item in page["items"]}) == 46
    assert not pages[-1]["more"]
    assert manager.knowledge_contents(library="guides", source="artifact:document-1")["total"] == 1


def test_global_and_scoped_search_are_literal_unicode_and_search_full_text(manager, indexed):
    add(indexed, texts=["Intro " * 300 + "Deep needle: C++ Straße foo OR *"])
    add(indexed, "other", source="upload:notes", texts=["A second needle"])
    assert manager.knowledge_contents(query="needle")["total"] == 2
    assert manager.knowledge_contents(library="guides", query="needle")["total"] == 1
    for query in ("guides", "example.com", "C++", "STRASSE", "foo OR *"):
        result = manager.knowledge_contents(query=query)
        assert result["total"] == 1, query
    assert "Deep needle" in manager.knowledge_contents(query="needle")["items"][0]["text"]
    assert manager.knowledge_contents(query='" OR 1=1 --')["total"] == 0


def test_reader_preserves_whitespace_and_bounds_oversized_chunks(manager, indexed):
    text = 'Line one\r\n\t<script>alert("test")</script>\n' + "界" * MAX_CHUNK
    add(indexed, texts=[text])
    hit = manager.knowledge_contents(library="guides")["items"][0]
    item = manager.knowledge_contents(library="guides", chunk=hit["id"])["item"]
    assert item["text"] == text[:MAX_CHUNK]
    assert item["characters"] == len(text) and item["truncated"]
    with pytest.raises(ValueError):
        manager.knowledge_contents(library="other", chunk=hit["id"])
    with pytest.raises(ValueError):
        manager.knowledge_contents(library="guides", chunk=hit["id"][:-1] + "z")


def test_staging_obsolete_and_disabled_content_stay_out_of_browse_and_reader(manager, indexed):
    add(indexed, texts=["Old active passage"])
    old = manager.knowledge_contents(library="guides")["items"][0]
    version = indexed.stage_version(
        "guides",
        "learn:https://example.com/guide",
        "https://example.com/guide",
        ["New passage"],
        [[1.0, 0.0]],
        "new",
    )
    assert manager.knowledge_contents(query="New passage")["total"] == 0
    indexed.activate_versions(
        "guides", "learn:https://example.com/guide", {"https://example.com/guide": version}
    )
    assert manager.knowledge_contents(query="Old active")["total"] == 0
    with pytest.raises(ValueError):
        manager.knowledge_contents(library="guides", chunk=old["id"])
    hidden = indexed.stage_version(
        "guides", "skill:hidden", "secret", ["Hidden passage"], [[1.0, 0.0]], "hidden"
    )
    indexed.activate_versions("guides", "skill:hidden", {"secret": hidden})
    with indexed.fts:
        indexed.fts.execute("INSERT INTO disabled_skills VALUES('hidden')")
    assert manager.knowledge_contents(query="Hidden")["total"] == 0
    assert manager.knowledge_contents(library="guides", sources=True)["total"] == 1


def test_legacy_rows_and_modern_rows_are_browsable_without_migration(manager, indexed):
    add(indexed, texts=["Modern passage"])
    with indexed.fts:
        indexed.fts.execute(
            "INSERT INTO chunks VALUES('old','guides','legacy-file','Legacy passage')"
        )
    indexed._register_legacy_active_sources()
    indexed.fts.commit()
    before = (indexed.root / "fts.db").read_bytes()
    hits = manager.knowledge_contents(library="guides")["items"]
    assert len(hits) == 2
    legacy = next(item for item in hits if item["source"] == "legacy-file")
    assert (
        manager.knowledge_contents(library="guides", chunk=legacy["id"])["item"]["text"]
        == "Legacy passage"
    )
    assert (indexed.root / "fts.db").read_bytes() == before


def test_reviewed_source_delete_keeps_other_sources_and_no_model_required(manager, indexed):
    add(indexed)
    add(indexed, source="keep", texts=["Retained"])
    manager.cfg.models["embed"] = ""
    draft = {
        "operation": "knowledge-delete",
        "library": "guides",
        "source": "https://example.com/guide",
    }
    review = manager.prepare("browser", draft)
    assert "45 active chunks" in review["summary"]
    assert manager.knowledge_contents(library="guides")["total"] == 46
    identity = uuid.uuid4().hex
    manager.submit("browser", review["review_id"], identity)
    assert _wait(manager, identity)["state"] == "completed"
    assert manager.knowledge_contents(library="guides")["total"] == 1
    assert manager.knowledge_contents(library="guides")["items"][0]["source"] == "keep"
    assert manager.submit("browser", review["review_id"], identity)["state"] == "completed"


def test_stale_delete_is_rejected_without_removing_replacement(manager, indexed):
    add(indexed, texts=["Before"])
    review = manager.prepare(
        "browser", {"operation": "knowledge-delete", "library": "guides", "source": ""}
    )
    fields = manager._reviews[review["review_id"]].fields
    add(indexed, texts=["Changed after review"])
    identity = uuid.uuid4().hex
    receipt = manager.journal.admit(
        request_id=identity,
        owner_id=OWNER,
        kind="knowledge-delete",
        resource="knowledge-index",
        payload={},
    )
    manager.journal.start(identity, OWNER, receipt.fence)
    request = {
        "operation": "knowledge-delete",
        "data_dir": str(manager.data),
        "request_id": identity,
        "fence": receipt.fence,
        **fields,
    }
    assert run_management_operation(request) == {"rejected": True}
    assert (
        manager.knowledge_contents(library="guides")["items"][0]["text"] == "Changed after review"
    )


def test_library_delete_removes_fts_history_and_legacy_without_touching_other_library(
    manager, indexed
):
    add(indexed)
    add(indexed, "other", texts=["Keep"])
    with indexed.fts:
        indexed.fts.execute(
            "INSERT INTO chunks VALUES('old','guides','legacy-file','Legacy passage')"
        )
    indexed._register_legacy_active_sources()
    indexed.fts.commit()
    review = manager.prepare(
        "browser", {"operation": "knowledge-delete", "library": "guides", "source": ""}
    )
    fields = manager._reviews[review["review_id"]].fields
    delete_knowledge(indexed.root, **fields)
    assert manager.knowledge_contents(library="guides")["total"] == 0
    assert manager.knowledge_contents(query="atomic")["total"] == 0
    assert manager.knowledge_contents()["items"][0]["id"] == "other"
    for table, column in (
        ("active_sources", "library"),
        ("source_versions", "library"),
        ("chunks_v2", "library"),
        ("chunks", "collection"),
    ):
        assert (
            indexed.fts.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}='guides'").fetchone()[
                0
            ]
            == 0
        )


@pytest.mark.parametrize(
    "filters",
    [
        {"source": "missing-library"},
        {"offset": -1},
        {"offset": True},
        {"query": "x" * 201},
        {"query": "bad\nquery"},
        {"library": "x" * 161},
        {"chunk": "invalid"},
    ],
)
def test_invalid_filters_fail_before_reading(manager, filters):
    with pytest.raises(ValueError):
        # Chunk validation requires a present DB, otherwise this fails as no-longer-available.
        browse_knowledge(manager.data / "knowledge.lance", **filters)


def test_sources_use_original_upload_filenames_and_saved_file_names(manager, indexed):
    item = manager.artifacts.import_bytes(b"Readable original", "document", "Architecture notes.md")
    add(indexed, source="artifact:" + item["id"], texts=["Imported content"])
    upload = "upload:" + "a" * 64 + ":team-notes.txt"
    add(indexed, source=upload, texts=["Uploaded content"])
    sources = manager.knowledge_contents(library="guides", sources=True)["items"]
    assert {row["source_name"] for row in sources} == {"Architecture notes.md", "team-notes.txt"}
    hit = manager.knowledge_contents(library="guides", source="artifact:" + item["id"])["items"][0]
    assert hit["source"] == "artifact:" + item["id"]
    assert hit["source_name"] == "Architecture notes.md"
    assert (
        manager.knowledge_contents(library="guides", chunk=hit["id"])["item"]["source_name"]
        == "Architecture notes.md"
    )


def test_source_pagination_and_managed_refresh_keep_the_exact_manifest(manager, indexed):
    import json

    for index in range(25):
        add(indexed, source=f"source-{index:02}", texts=["One chunk"])
    version = indexed.stage_version(
        "guides",
        "docs:official",
        "https://example.com/official",
        ["Official guide"],
        [[1.0, 0.0]],
        "checksum",
    )
    indexed.activate_versions("guides", "docs:official", {"https://example.com/official": version})
    folder = manager.data / "docs-sources" / "official"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps({"name": "official", "library": "guides", "files": []})
    )
    pages = [manager.knowledge_contents(library="guides", sources=True, offset=n) for n in (0, 20)]
    assert [len(page["items"]) for page in pages] == [20, 6]
    assert all(page["total"] == 26 for page in pages)
    managed = next(row for page in pages for row in page["items"] if row["id"].startswith("https:"))
    assert managed["refresh"][0]["id"] == "official"
    assert len(managed["refresh"][0]["identity"]) == 64
