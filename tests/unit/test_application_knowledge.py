"""Knowledge application projection preserves retrieval while hiding engine internals."""

from __future__ import annotations

import pytest
from klaude_application.knowledge import KnowledgeReader


class _Store:
    def collections(self):
        return ["react", "python"]


class _Knowledge:
    store = _Store()

    def __init__(self):
        self.calls = []

    def query(self, question, library, k):
        self.calls.append(("query", question, library, k))
        return [{"collection": library, "source": "https://example.test/docs",
                 "text": "Useful public text", "relevance_score": 0.8,
                 "private_vector": [1, 2, 3], "provider_secret": "never-publish"}]

    def query_with_evidence(self, question, library, k):
        self.calls.append(("context", question, library, k))
        return "--- library: react; source: https://example.test/docs ---\nUseful public text", [
            {"source": "https://example.test/docs", "source_id": "chunk-1",
             "excerpt": "Useful public text", "sha256": "a" * 64,
             "captured_at": 1, "partial": True, "offset": 0,
             "provider_secret": "never-publish"},
        ]


def test_knowledge_reader_projects_only_public_fields_and_preserves_route():
    knowledge = _Knowledge()
    reader = KnowledgeReader(knowledge)
    assert reader.libraries() == ("react", "python")
    hits = reader.query("hooks", "react", 4)
    assert knowledge.calls[-1] == ("query", "hooks", "react", 4)
    assert hits[0].text == "Useful public text"
    assert "never-publish" not in repr(hits)
    context = reader.context("hooks", "react", 4)
    assert knowledge.calls[-1] == ("context", "hooks", "react", 4)
    assert context.evidence[0].source_id == "chunk-1"
    assert "never-publish" not in repr(context)


def test_knowledge_reader_rejects_unbounded_queries_without_model_work():
    knowledge = _Knowledge()
    reader = KnowledgeReader(knowledge)
    with pytest.raises(ValueError, match="query"):
        reader.query("x" * 4001)
    with pytest.raises(ValueError, match="count"):
        reader.context("hooks", k=51)
    assert knowledge.calls == []
