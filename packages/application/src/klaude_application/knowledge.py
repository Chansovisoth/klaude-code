"""Typed, bounded read adapter for the existing knowledge engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class KnowledgeHit:
    library: str
    source: str
    text: str
    relevance_score: float


@dataclass(frozen=True)
class KnowledgeEvidence:
    source: str
    source_id: str
    excerpt: str
    sha256: str
    captured_at: int
    partial: bool
    offset: int


@dataclass(frozen=True)
class KnowledgeContext:
    content: str
    evidence: tuple[KnowledgeEvidence, ...]


class KnowledgeReader:
    """Use one injected Knowledge instance; never start indexing or model work on init."""

    def __init__(self, knowledge: Any) -> None:
        self.knowledge = knowledge

    @staticmethod
    def _args(question: str, library: str, k: int) -> None:
        if not isinstance(question, str) or not 0 < len(question) <= 4000:
            raise ValueError("knowledge query must contain 1-4000 characters")
        if not isinstance(library, str) or len(library) > 160:
            raise ValueError("library name is too long")
        if type(k) is not int or not 1 <= k <= 50:
            raise ValueError("knowledge result count must be between 1 and 50")

    def libraries(self) -> tuple[str, ...]:
        return tuple(str(name)[:160] for name in self.knowledge.store.collections()[:1000])

    def query(self, question: str, library: str = "", k: int = 6) -> tuple[KnowledgeHit, ...]:
        self._args(question, library, k)
        rows = self.knowledge.query(question, library, k)
        return tuple(KnowledgeHit(
            library=str(row.get("collection", ""))[:160],
            source=str(row.get("source") or row.get("collection", ""))[:1000],
            text=str(row.get("text", ""))[:8000],
            relevance_score=float(row.get("relevance_score") or 0),
        ) for row in rows[:k])

    def context(self, question: str, library: str = "", k: int = 6) -> KnowledgeContext:
        self._args(question, library, k)
        method = getattr(self.knowledge, "query_with_evidence", None)
        if callable(method):
            content, rows = method(question, library, k)
        else:
            content = self.knowledge.query_as_context(question, library, k)
            rows = []
        evidence = tuple(KnowledgeEvidence(
            source=str(row.get("source", ""))[:1000],
            source_id=str(row.get("source_id", ""))[:80],
            excerpt=str(row.get("excerpt", ""))[:1200],
            sha256=str(row.get("sha256", ""))[:64],
            captured_at=int(row.get("captured_at") or 0),
            partial=bool(row.get("partial", True)),
            offset=max(0, int(row.get("offset") or 0)),
        ) for row in rows[:3] if isinstance(row, dict))
        return KnowledgeContext(str(content)[:100_000], evidence)
