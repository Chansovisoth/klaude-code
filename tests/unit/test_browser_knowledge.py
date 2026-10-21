"""Saved-file learning uses exact revisions and the real Knowledge index."""

import io
import zipfile

import pytest
from klaude_application.browser_management import prepare_profile_operation
from klaude_application.library_knowledge import (
    KnowledgeAction,
    artifact_text,
    knowledge_worker_request,
    run_operation,
)
from klaude_core.library_artifacts import ArtifactStore
from klaude_knowledge import Knowledge

from .test_library_knowledge import cfg as cfg
from .test_library_knowledge import embeddings as embeddings


def test_saved_document_learns_into_real_index_and_deduplicates(cfg, embeddings):
    store = ArtifactStore(cfg.data_dir / "library")
    item = store.import_bytes(b"# Widgets\nAmber widgets use atomic transactions.",
                              "document", "widgets.md")
    draft = {"operation": "artifact-learn", "target": item["id"],
             "revision": item["revision"], "library": "widgets"}
    fields, resource, summary = prepare_profile_operation(cfg, draft, cfg.data_dir.parent)
    assert resource == "knowledge-index" and "widgets.md" in summary
    assert not embeddings
    action = KnowledgeAction.from_draft({"operation": "learn-artifact", **fields})
    request = knowledge_worker_request(action, cfg, data_dir=cfg.data_dir,
                                       workspace=cfg.data_dir.parent)
    assert run_operation(request)["status"] == "learned"
    assert embeddings
    count = len(embeddings)
    assert run_operation(request)["status"] == "unchanged"
    assert len(embeddings) == count
    knowledge = Knowledge(cfg, None)
    try:
        found = knowledge.store.keyword_search("widgets", "atomic", 6)
        assert found and found[0]["source"] == "artifact:" + item["id"]
    finally:
        knowledge.store.fts.close()


@pytest.mark.parametrize("change", ["revision", "archive", "checksum", "size"])
def test_changed_file_is_rejected_before_embedding(cfg, embeddings, change):
    store = ArtifactStore(cfg.data_dir / "library")
    item = store.import_bytes(b"Public widget instructions", "document", "notes.txt")
    action = KnowledgeAction.from_draft({"operation": "learn-artifact", "library": "widgets",
                                        "artifact": item["id"], "revision": item["revision"]})
    if change in {"revision", "archive"}:
        store.change(item["id"], item["revision"], "tags" if change == "revision" else "archive")
    else:
        with store.database(write=True) as db:
            if change == "checksum":
                db.execute("UPDATE artifacts SET content=? WHERE id=?", (b"changed", item["id"]))
            else:
                db.execute("UPDATE artifacts SET size=? WHERE id=?", (2_097_153, item["id"]))
    request = knowledge_worker_request(action, cfg, data_dir=cfg.data_dir,
                                       workspace=cfg.data_dir.parent)
    assert run_operation(request)["status"] == "rejected"
    assert not embeddings
    assert not (cfg.data_dir / "knowledge.lance").exists()


def test_docx_learning_reuses_disposable_document_parser(cfg):
    document = io.BytesIO()
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats'
                         '.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Amber widget'
                         ' instructions</w:t></w:r></w:p></w:body></w:document>')
    item = ArtifactStore(cfg.data_dir / "library").import_bytes(
        document.getvalue(), "document", "instructions.docx",
    )
    text, title = artifact_text(cfg.data_dir, item["id"], item["revision"])
    assert "Amber widget instructions" in text and title == "instructions.docx"


@pytest.mark.parametrize("data", [b"", b"binary\0content", b"\xff\xff"])
def test_unreadable_saved_file_cannot_be_learned(cfg, data):
    item = ArtifactStore(cfg.data_dir / "library").import_bytes(data, "document", "notes.txt")
    with pytest.raises(ValueError):
        artifact_text(cfg.data_dir, item["id"], item["revision"])
