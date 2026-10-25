"""Shared browser Library consumers: real owned workers, reviews and boundaries."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from klaude_application.library_management import (
    OWNER,
    LibraryManagement,
    run_management_operation,
)
from klaude_application.operation_journal import OperationConflict
from klaude_core.config import Config
from PIL import Image


@pytest.fixture
def manager(tmp_path, monkeypatch):
    from klaude_core import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    cfg = Config()
    cfg.models["embed"] = "fixture-embedding"
    monkeypatch.setattr(config, "load_config", lambda: cfg)
    result = LibraryManagement(cfg, tmp_path)
    yield result
    result.close()


def _wait(manager, identity):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = manager.status(identity)
        if result["state"] not in {"accepted", "running", "cancelling"}:
            return result
        time.sleep(0.02)
    pytest.fail("Owned Library worker did not finish")


def _change(manager, item, operation, **extra):
    review = manager.prepare("browser", {
        "operation": operation, "target": item["id"], "revision": item["revision"], **extra,
    })
    identity = uuid.uuid4().hex
    manager.submit("browser", review["review_id"], identity)
    return _wait(manager, identity)


def test_reviewed_tag_edit_removes_only_chosen_ai_tags_and_preserves_provenance(manager):
    item = manager.artifacts.import_bytes(b"Fixture", "document", "tagged.txt")
    item = manager.artifacts.apply_ai_tags(item["id"], item["revision"], item["sha256"],
                                           ["first", "keep"], {"model": "fixture"})
    prior = manager.artifacts.tagging_info(item["id"])
    result = _change(manager, item, "tags", value="manual", remove_ai_tags=["first"])
    assert result["state"] == "completed"
    saved = manager.artifacts.get(item["id"])
    assert saved["tags"] == ["manual"] and saved["ai_tags"] == ["keep"]
    assert manager.artifacts.tagging_info(item["id"]) == {"keep": prior["keep"]}
    result = _change(manager, saved, "tags", value="manual", remove_ai_tags=["keep"])
    assert result["state"] == "completed"
    assert manager.artifacts.get(item["id"])["ai_tags"] == []
    assert manager.artifacts.get(item["id"])["tags"] == ["manual"]


@pytest.mark.parametrize("removals", ["first", ["missing"], ["x" * 41], [1], ["first"] * 21])
def test_ai_tag_removal_rejects_invalid_or_unknown_choices_without_changes(manager, removals):
    item = manager.artifacts.import_bytes(b"Fixture", "document", "tagged.txt")
    item = manager.artifacts.apply_ai_tags(item["id"], item["revision"], item["sha256"],
                                           ["first", "keep"], {"model": "fixture"})
    with pytest.raises(ValueError):
        manager.prepare("browser", {"operation": "tags", "target": item["id"],
                                    "revision": item["revision"], "value": "manual",
                                    "remove_ai_tags": removals})
    assert manager.artifacts.get(item["id"]) == item


def test_ai_tag_removal_rechecks_revision_in_worker_and_is_atomic(manager):
    item = manager.artifacts.import_bytes(b"Fixture", "document", "tagged.txt")
    item = manager.artifacts.apply_ai_tags(item["id"], item["revision"], item["sha256"],
                                           ["first", "keep"], {"model": "fixture"})
    review = manager.prepare("browser", {"operation": "tags", "target": item["id"],
                                        "revision": item["revision"], "value": "manual",
                                        "remove_ai_tags": ["first"]})
    assert "Remove AI tags: first" in review["summary"]
    saved = manager.artifacts.change(item["id"], item["revision"], "tags", "another client")
    identity = uuid.uuid4().hex
    manager.submit("browser", review["review_id"], identity)
    assert _wait(manager, identity)["state"] == "failed"
    assert manager.artifacts.get(item["id"]) == saved
    with pytest.raises(ValueError, match="AI tags changed"):
        manager.artifacts.change(item["id"], saved["revision"], "tags", "must not save",
                                 remove_ai_tags=["missing"])
    assert manager.artifacts.get(item["id"]) == saved


def test_metadata_reads_do_not_start_workers_or_initialize_stores(manager, monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Browsing must not start a worker or model")

    monkeypatch.setattr(manager._jobs, "submit", unexpected)
    assert manager.listing()["items"] == []
    assert manager.knowledge()["items"] == []
    assert manager.skills()["items"] == []
    assert manager.sources("")["items"] == []
    assert manager.operations()["items"] == []
    assert list(manager.data.iterdir()) == []


def test_context_scope_filters_before_paging_and_keeps_original_identity(manager):
    selected = manager.artifacts.import_bytes(b"Shared text", "document", "selected.txt")
    unrelated = manager.artifacts.import_bytes(b"Other text", "document", "other.txt")
    linked = [manager.artifacts.import_bytes(b"Context", "document", f"linked-{i:02}.txt")
              for i in range(26)]
    with manager.artifacts.database(write=True) as db:
        db.executemany("UPDATE artifacts SET session=? WHERE id=?",
                       [("current", item["id"]) for item in linked])
    before = manager.listing(kind="all")["total"]
    pages = [manager.listing(kind="all", session="current", identities=(selected["id"],),
                             sort="name", offset=offset) for offset in (0, 20)]
    assert [len(page["items"]) for page in pages] == [20, 7]
    assert all(page["total"] == 27 for page in pages)
    ids = {item["id"] for page in pages for item in page["items"]}
    assert selected["id"] in ids and unrelated["id"] not in ids
    assert manager.listing(kind="all", session="current", query="other")["total"] == 0
    assert manager.listing(kind="all", session="current", images_only=True)["total"] == 0
    assert manager.listing(kind="all")["total"] == before
    assert manager.artifacts.get(selected["id"]) == selected
    for identity in ("not-an-id", 3):
        with pytest.raises(ValueError):
            manager.listing(kind="all", session="current", identities=(identity,))


@pytest.mark.parametrize("count", [45, 125])
def test_artifact_browser_pages_are_twenty_and_keep_filters_and_cli_batches(manager, count):
    for index in range(count):
        manager.artifacts.import_bytes(b"Saved", "document", f"item-{index:02}.txt")
    offsets = range(0, count, 20)
    pages = [manager.listing(sort="name", offset=offset) for offset in offsets]
    assert [len(page["items"]) for page in pages] == [min(20, count - n) for n in offsets]
    assert all(page["more"] for page in pages[:-1]) and not pages[-1]["more"]
    assert all(page["page_size"] == 20 for page in pages)
    assert all(page["total"] == page["known_total"] == count for page in pages)
    assert len({item["id"] for page in pages for item in page["items"]}) == count
    filtered = manager.listing(query="item-4", sort="name")
    assert len(filtered["items"]) == filtered["total"] == min(10, count - 40)
    assert not filtered["more"]
    for item in pages[0]["items"]:
        manager.artifacts.change(item["id"], item["revision"], "archive")
    archived = manager.listing(kind="all", archived=True)
    assert len(archived["items"]) == archived["total"] == 20 and not archived["more"]
    # The embedded CLI/TUI continues to receive its original store batch size.
    embedded = manager.artifacts.listing("document")
    assert len(embedded["items"]) == min(100, count - 20)
    assert "total" not in embedded


def test_numbered_pages_distinguish_observed_lookahead_from_exact_total():
    first = LibraryManagement._page({"items": [{}] * 100, "more": True}, 0)
    assert first["total"] is None and first["known_total"] == 101
    assert len(first["items"]) == 20
    last_batch = LibraryManagement._page({"items": [{}] * 57, "more": False}, 80)
    assert last_batch["total"] == last_batch["known_total"] == 137


def test_skill_filtering_precedes_paging_and_later_pages_remain_manageable(manager, monkeypatch):
    items = [{"name": f"skill-{index:02}", "identity": str(index), "enabled": True,
              "description": "review" if index % 2 else "coding", "library": "skills"}
             for index in range(45)]
    monkeypatch.setattr(manager, "_installed_skills", lambda: {"items": items, "more": False})
    pages = [manager.skills(offset=offset) for offset in (0, 20, 40)]
    assert [len(page["items"]) for page in pages] == [20, 20, 5]
    assert [page["more"] for page in pages] == [True, True, False]
    filtered = [manager.skills(query="REVIEW", offset=offset) for offset in (0, 20)]
    assert [len(page["items"]) for page in filtered] == [20, 2]
    assert all(page["total"] == 22 for page in filtered)
    assert not filtered[-1]["more"]
    last = items[-1]
    review = manager.prepare("browser", {"operation": "skill-enabled", **{
        key: last[key] for key in ("name", "identity")}, "enabled": False,
        "expected_enabled": True})
    assert "skill-44" in review["summary"]


def test_skill_status_and_search_filter_before_counts_and_pagination(manager, monkeypatch):
    items = [{"name": f"skill-{index:02}", "identity": str(index), "enabled": index % 3 != 0,
              "description": "review" if index % 2 else "coding", "library": "skills"}
             for index in range(90)]
    monkeypatch.setattr(manager, "_installed_skills", lambda: {"items": items, "more": False})
    for state in ("all", "enabled", "disabled"):
        for query in ("", "REVIEW"):
            expected = [item for item in items
                        if (state == "all" or item["enabled"] == (state == "enabled"))
                        and (not query or item["description"] == "review")]
            pages = [manager.skills(query=query, state=state, offset=offset)
                     for offset in range(0, len(expected), 20)]
            assert [item for page in pages for item in page["items"]] == expected
            assert all(page["total"] == page["known_total"] == len(expected) for page in pages)
            assert all(page["state"] == state for page in pages)
            assert all(page["more"] for page in pages[:-1]) and not pages[-1]["more"]
    assert manager.skills(state="disabled", query="missing")["total"] == 0
    assert manager.skills(state="enabled", offset=100)["items"] == []
    with pytest.raises(ValueError, match="Skills status"):
        manager.skills(state="unexpected")
    # Status filtering is a read projection; confirmed enable state is unchanged.
    assert sum(item["enabled"] for item in items) == 60


def test_knowledge_and_source_inventories_page_twenty_with_exact_last_page(manager):
    for index in range(140):
        (manager.data / "knowledge.lance" / f"docs-{index:02}.lance").mkdir(parents=True)
        source = manager.data / "docs-sources" / f"source-{index:02}"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text(json.dumps({
            "name": source.name, "library": "docs", "files": ["docs.md"],
            "llms_url": "https://example.test/llms.txt",
        }))
    for listing in (manager.knowledge, lambda **kw: manager.sources("docs", **kw)):
        first, last = listing(offset=0), listing(offset=120)
        assert len(first["items"]) == len(last["items"]) == 20
        assert first["more"] and not last["more"]
        assert first["total"] == last["total"] == 140
        assert {item["id"] for item in first["items"]}.isdisjoint(
            item["id"] for item in last["items"]
        )


@pytest.mark.parametrize("count", [45, 125])
def test_knowledge_search_pages_modern_and_legacy_matches_without_duplicates(manager, count):
    from klaude_application.library_inventory import knowledge_search

    root = manager.data / "knowledge.lance"
    root.mkdir()
    with sqlite3.connect(root / "fts.db") as db:
        db.executescript("""
            CREATE VIRTUAL TABLE chunks_v2 USING fts5(
                id UNINDEXED, library UNINDEXED, owner UNINDEXED,
                source UNINDEXED, version_id UNINDEXED, text);
            CREATE TABLE active_sources(library,owner,source,version_id);
            CREATE TABLE source_versions(version_id,status);
            CREATE TABLE disabled_skills(name);
            CREATE VIRTUAL TABLE chunks USING fts5(
                id UNINDEXED, collection UNINDEXED, source UNINDEXED, text);
        """)
        for index in range(count):
            source, version = f"source-{index:02}", f"version-{index:02}"
            owner = "modern" if index < 23 else "legacy:" + source
            db.execute("INSERT INTO active_sources VALUES(?,?,?,?)",
                       ("docs", owner, source, version))
            db.execute("INSERT INTO source_versions VALUES(?,'active')", (version,))
            if index < 23:
                db.execute("INSERT INTO chunks_v2 VALUES(?,?,?,?,?,?)",
                           (str(index), "docs", owner, source, version, "rainbow colors"))
            else:
                db.execute("INSERT INTO chunks VALUES(?,?,?,?)",
                           (str(index), "docs", source, "rainbow colors"))
        db.execute("INSERT INTO chunks_v2 VALUES('private','docs','skill:hidden',"
                   "'hidden-source','hidden-version','rainbow colors')")
        db.execute("INSERT INTO active_sources VALUES('docs','skill:hidden',"
                   "'hidden-source','hidden-version')")
        db.execute("INSERT INTO disabled_skills VALUES('hidden')")
    offsets = range(0, count, 20)
    pages = [manager.knowledge("docs", "rainbow", offset=offset) for offset in offsets]
    assert [len(page["hits"]) for page in pages] == [min(20, count - n) for n in offsets]
    assert all(page["more"] for page in pages[:-1]) and not pages[-1]["more"]
    assert all(page["total"] == count for page in pages)
    sources = [hit["source"] for page in pages for hit in page["hits"]]
    assert len(set(sources)) == count and "hidden-source" not in sources
    assert len(knowledge_search(root, "docs", "rainbow")["hits"]) == 20
    assert "more" not in knowledge_search(root, "docs", "rainbow")


def test_owned_import_is_reviewed_immutable_deduplicated_and_shared(manager):
    original = io.BytesIO(b"# Browser document\nPrivate saved copy\n")
    review = manager.prepare("browser", {"operation": "import", "kind": "document"},
                             upload=("notes.md", original))
    assert manager.listing()["items"] == []
    assert "source" not in review and "config" not in json.dumps(review)
    original.seek(0)
    original.write(b"CHANGED")
    identity = uuid.uuid4().hex
    manager.submit("browser", review["review_id"], identity)
    assert _wait(manager, identity)["state"] == "completed"
    assert manager.submit("browser", review["review_id"], identity)["state"] == "completed"
    with pytest.raises(OperationConflict, match="already accepted"):
        manager.submit("browser", review["review_id"], uuid.uuid4().hex)
    items = manager.listing()["items"]
    assert len(items) == 1
    assert items[0]["filename"] == "notes.md"
    assert "origin" not in items[0] and "model" not in items[0]
    assert "Browser document" in "\n".join(manager.detail(items[0]["id"])["lines"])
    exported = manager.artifacts.export(items[0]["id"], manager.workspace / "exported.md")
    assert exported.read_bytes().startswith(b"# Browser document")
    assert not manager._jobs._active
    assert manager._reviews[review["review_id"]].upload is None


def test_artifact_lifecycle_uses_atomic_revisions_and_retains_originals(manager):
    source = manager.workspace / "original.md"
    source.write_text("Original workspace file")
    item = manager.artifacts.import_file(source, "document")
    stale = manager.prepare("browser", {"operation": "archive", "target": item["id"],
                                        "revision": item["revision"]})
    assert _change(manager, item, "tags", value="project, review")["state"] == "completed"
    identity = uuid.uuid4().hex
    manager.submit("browser", stale["review_id"], identity)
    assert _wait(manager, identity)["state"] == "failed"
    current = manager.artifacts.get(item["id"])
    assert current["tags"] == ["project", "review"] and not current["archived"]
    assert _change(manager, current, "archive")["state"] == "completed"
    current = manager.artifacts.get(item["id"])
    assert _change(manager, current, "restore")["state"] == "completed"
    current = manager.artifacts.get(item["id"])
    review = manager.prepare("browser", {"operation": "delete", "target": current["id"],
                                         "revision": current["revision"]})
    manager.discard("browser", review["review_id"])
    assert not manager.artifacts.get(current["id"])["archived"]
    assert _change(manager, current, "archive")["state"] == "completed"
    current = manager.artifacts.get(item["id"])
    assert manager.listing(kind="all", archived=True)["items"][0]["id"] == item["id"]
    assert _change(manager, current, "delete")["state"] == "completed"
    assert source.read_text() == "Original workspace file"
    assert manager.listing(kind="all", archived=True)["items"] == []


@pytest.mark.parametrize("kind", ["document", "media", "research"])
def test_saved_artifact_delete_rechecks_review_revision_without_archiving(manager, kind):
    if kind == "research":
        item = manager.artifacts.store_report("report.md", "Saved report", job="fixture")
    elif kind == "media":
        output = io.BytesIO()
        Image.new("RGB", (2, 2), "teal").save(output, format="PNG")
        item = manager.artifacts.import_bytes(output.getvalue(), kind, "saved.png")
    else:
        item = manager.artifacts.import_bytes(b"Saved bytes", kind, "saved.txt")
    draft = {"operation": "delete", "target": item["id"], "revision": item["revision"]}
    review = manager.prepare("browser", draft)
    assert "cannot be undone" in review["summary"]
    assert not manager.artifacts.get(item["id"])["archived"]
    manager.discard("browser", review["review_id"])
    assert manager.artifacts.get(item["id"])["revision"] == item["revision"]

    stale = manager.prepare("browser", draft)
    current = manager.artifacts.change(item["id"], item["revision"], "tags", "changed")
    identity = uuid.uuid4().hex
    manager.submit("browser", stale["review_id"], identity)
    assert _wait(manager, identity)["state"] == "failed"
    assert manager.artifacts.get(item["id"])["revision"] == current["revision"]
    assert not current["archived"]
    assert _change(manager, current, "delete")["state"] == "completed"
    with pytest.raises(ValueError, match="no longer exists"):
        manager.artifacts.get(item["id"])


def test_reviews_expire_are_owner_bound_and_release_private_snapshots(manager):
    review = manager.prepare("browser", {"operation": "import", "kind": "document"},
                             upload=("notes.txt", io.BytesIO(b"secret")))
    captured = Path(manager._reviews[review["review_id"]].upload.name)
    assert captured.stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError, match="expired"):
        manager.submit("another-browser", review["review_id"], uuid.uuid4().hex)
    manager.discard("another-browser", review["review_id"])
    assert captured.exists()
    manager.discard("browser", review["review_id"])
    assert not captured.exists()
    with pytest.raises(ValueError, match="expired"):
        manager.submit("browser", review["review_id"], uuid.uuid4().hex)
    review = manager.prepare("browser", {"operation": "import", "kind": "document"},
                             upload=("notes.txt", io.BytesIO(b"secret")))
    manager.revoke("browser")
    assert not manager._reviews
    assert manager.listing()["items"] == []


def test_settled_settings_snapshots_release_capacity_without_deleting_receipts(manager):
    from klaude_application.browser_settings import read_browser_settings
    from klaude_core.settings_store import read_settings

    for value in range(1, 19):
        field = next(item for item in read_browser_settings(manager.cfg)["fields"]
                     if item["id"] == "runtime_options.max_steps")
        review = manager.prepare("browser", {"operation": "setting-save", "id": field["id"],
                                            "value": value, "revision": field["revision"]})
        token, identity = review["review_id"], uuid.uuid4().hex
        manager.submit("browser", token, identity)
        assert _wait(manager, identity)["state"] == "completed"
        manager.discard("another-browser", token)
        assert token in manager._reviews
        manager.discard("browser", token)
        assert token not in manager._reviews
        assert manager.status(identity)["state"] == "completed"
    saved = read_settings(manager.data / "chat-preferences.json")
    assert saved["runtime_options"]["max_steps"] == 18


def test_settings_discard_cannot_cancel_pending_work_or_clear_unknown_fences(manager, monkeypatch):
    from klaude_application.browser_settings import read_browser_settings

    # Hold the process boundary; the real operation journal still owns admission,
    # state transitions and the resource fence.
    monkeypatch.setattr(manager._jobs, "submit", lambda *_args, **_kwargs: None)
    field = read_browser_settings(manager.cfg)["fields"][0]
    review = manager.prepare("browser", {"operation": "setting-save", "id": field["id"],
                                        "value": "UTC", "revision": field["revision"]})
    token, identity = review["review_id"], uuid.uuid4().hex
    manager.submit("browser", token, identity)
    manager.discard("browser", token)
    assert token in manager._reviews and manager.status(identity)["state"] == "running"
    with manager._lock:
        manager._finish(identity, False)
    manager.discard("browser", token)
    assert token in manager._reviews and manager.status(identity)["state"] == "unknown"
    assert manager.journal.fenced_operation(f"setting:{field['id']}") is not None


@pytest.mark.parametrize("draft", [
    {"operation": "open", "target": "/etc/passwd"},
    {"operation": "knowledge-url", "library": "test", "source": "/etc/passwd"},
    {"operation": "knowledge-url", "library": "test", "source": "https://user:secret@example.com"},
    {"operation": "knowledge-url", "library": "test", "source": "https://example.com",
     "config_dir": "/tmp"},
    {"operation": "import", "kind": "document", "source": "/etc/passwd"},
    {"operation": "skill-enabled", "name": "../secret", "identity": "a" * 64, "enabled": True},
])
def test_browser_intent_cannot_choose_host_paths_roots_or_openers(manager, draft):
    with pytest.raises(ValueError):
        manager.prepare("browser", draft)
    assert manager.listing()["items"] == []


def _installed(manager):
    root = manager.data / "skills" / "review"
    current = root / "versions" / "one"
    current.mkdir(parents=True)
    (current / "SKILL.md").write_text("# Review\nUse project style.")
    (root / "manifest.json").write_text(json.dumps({
        "name": "review", "current_dir": str(current), "state": "active", "library": "skills",
    }))
    return manager.skills()["items"][0]


def test_installed_skill_enable_cas_and_delete_use_existing_services(manager):
    skill = _installed(manager)
    drafts = [{"operation": "skill-enabled", "name": skill["name"],
               "identity": skill["identity"], "expected_enabled": True, "enabled": enabled}
              for enabled in (False, True)]
    reviews = [manager.prepare("browser", draft) for draft in drafts]
    first = uuid.uuid4().hex
    manager.submit("browser", reviews[0]["review_id"], first)
    assert _wait(manager, first)["state"] == "completed"
    assert manager.skills()["items"][0]["enabled"] is False
    second = uuid.uuid4().hex
    manager.submit("browser", reviews[1]["review_id"], second)
    assert _wait(manager, second)["state"] == "failed"
    assert manager.skills()["items"][0]["enabled"] is False
    review = manager.prepare("browser", {"operation": "skill-delete", "name": skill["name"],
                                         "identity": skill["identity"], "expected_enabled": False})
    third = uuid.uuid4().hex
    manager.submit("browser", review["review_id"], third)
    assert _wait(manager, third)["state"] == "completed"
    assert manager.skills()["items"] == []


def test_worker_loss_marks_unknown_blocks_retry_and_shutdown_reaps(manager, monkeypatch):
    monkeypatch.setattr(manager._jobs, "submit", lambda *_args, **_kwargs: "fixture")
    review = manager.prepare("browser", {"operation": "import", "kind": "document"},
                             upload=("notes.txt", io.BytesIO(b"captured")))
    identity = uuid.uuid4().hex
    manager.submit("browser", review["review_id"], identity)
    manager._event("background_result", (identity, "fixture", None, "provider-secret"))
    status = manager.status(identity)
    assert status["state"] == "unknown"
    assert "secret" not in json.dumps(manager.operations())
    next_review = manager.prepare("browser", {"operation": "import", "kind": "document"},
                                  upload=("another.txt", io.BytesIO(b"next")))
    with pytest.raises(OperationConflict, match="unresolved"):
        manager.submit("browser", next_review["review_id"], uuid.uuid4().hex)
    manager.close()
    assert not manager._keeper.is_alive()
    assert not manager._jobs._active


def test_knowledge_rejection_is_not_reported_as_success(manager, monkeypatch):
    from klaude_application import library_knowledge

    identity = uuid.uuid4().hex
    receipt = manager.journal.admit(request_id=identity, owner_id=OWNER, kind="knowledge-url",
                                     resource="knowledge-index", payload={})
    manager.journal.start(identity, OWNER, receipt.fence)
    request = {"data_dir": str(manager.data), "request_id": identity, "fence": receipt.fence,
               "operation": "knowledge-url", "knowledge_request": {}}
    monkeypatch.setattr(library_knowledge, "run_operation", lambda _: {"status": "rejected"})
    assert run_management_operation(request) == {"rejected": True}
    monkeypatch.setattr(library_knowledge, "run_operation", lambda _: {"status": "unconfirmed"})
    assert run_management_operation(request) == {"ok": False}


def test_skill_upload_checksum_is_rechecked_before_install_or_model_work(manager):
    review = manager.prepare("browser", {
        "operation": "skill-import", "name": "review", "library": "skills",
    }, upload=("SKILL.md", io.BytesIO(b"# Reviewed instructions\n")))
    snapshot = Path(manager._reviews[review["review_id"]].fields["source"])
    assert snapshot.stat().st_mode & 0o777 == 0o400
    snapshot.chmod(0o600)
    snapshot.write_bytes(b"Different instructions")
    identity = uuid.uuid4().hex
    manager.submit("browser", review["review_id"], identity)
    assert _wait(manager, identity)["state"] == "failed"
    assert manager.skills()["items"] == []
    assert not (manager.data / "knowledge.lance").exists()


def test_knowledge_upload_uses_stable_content_source_not_temporary_path(manager, monkeypatch):
    from klaude_application.library_knowledge import KnowledgeAction, knowledge_worker_request
    from klaude_application.library_knowledge import run_operation as learn

    observed = []

    class Knowledge:
        store = SimpleNamespace(fts=SimpleNamespace(close=lambda: None))

        def __init__(self, *_args):
            pass

        def source_is_current(self, *_args):
            return False

        def learn_text(self, library, text, *, source, title):
            observed.append((library, text, source))
            return 1

    monkeypatch.setattr("klaude_knowledge.Knowledge", Knowledge)
    source = manager.workspace / "upload.md"
    payload = b"# Useful knowledge\n"
    source.write_bytes(payload)
    action = KnowledgeAction.from_draft({"operation": "learn", "library": "docs",
                                         "source": str(source)})
    request = knowledge_worker_request(action, manager.cfg, data_dir=manager.data,
                                       workspace=manager.workspace)
    identity = hashlib.sha256(payload).hexdigest() + ":upload.md"
    assert learn({**request, "upload_identity": identity})["status"] == "learned"
    assert observed == [("docs", payload.decode(), "upload:" + identity)]
    assert learn({**request, "upload_identity": "0" * 64 + ":upload.md"})["status"] == "rejected"


def test_tab_counts_use_full_unfiltered_inventories_and_archive_visibility(manager):
    for index in range(125):
        manager.artifacts.import_bytes(b"Saved", "document", f"item-{index:03}.txt")
    archived = manager.listing()["items"][0]
    manager.artifacts.change(archived["id"], archived["revision"], "archive")
    manager.artifacts.store_report("report.md", "Report", job="fixture")
    media = manager.artifacts.import_bytes(b"GIF89a\x01\x00\x01\x00", "media", "image.gif")
    manager.artifacts.change(media["id"], media["revision"], "archive")
    for index in range(45):
        (manager.data / "knowledge.lance" / f"docs-{index}.lance").mkdir(parents=True)
        skill = manager.data / "skills" / f"skill-{index}"
        skill.mkdir(parents=True)
        (skill / "manifest.json").write_text(json.dumps({
            "name": skill.name, "library": "skills", "files": [],
        }))
    manager.cfg.mcp_servers_file.write_text(json.dumps({"servers": {
        "private-name": {"transport": "stdio", "command": "never-run",
                         "args": ["private-argument"], "enabled": False},
    }}))
    counts = manager.tab_counts()
    assert counts == {name: {"total": total, "limited": False} for name, total in {
        "knowledge": 45, "document": 124, "research": 1, "media": 0,
        "archive": 2, "skills": 45, "mcp": 1, "files": 124, "outputs": 1,
    }.items()}
    manager.listing(query="missing", offset=20)
    manager.skills(query="missing", offset=20)
    assert manager.tab_counts() == counts
    assert "private" not in json.dumps(counts)


def test_tab_counts_distinguish_missing_bounded_and_unavailable_inventories(manager, monkeypatch):
    assert all(value == {"total": 0, "limited": False}
               for value in manager.tab_counts().values())
    assert not manager.data.exists() or list(manager.data.iterdir()) == []
    monkeypatch.setattr(manager, "knowledge", lambda: {"total": 1000, "limited": True})
    def unavailable():
        raise ValueError("private source failure")
    monkeypatch.setattr(manager, "skills", unavailable)
    counts = manager.tab_counts()
    assert counts["knowledge"] == {"total": 1000, "limited": True}
    assert counts["skills"] == {"total": None, "limited": False}
    assert counts["document"] == {"total": 0, "limited": False}
    assert "private" not in json.dumps(counts)
