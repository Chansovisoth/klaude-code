"""The knowledge layer facade: learn(source) and query(question).

Query path: vector search + BM25 in parallel -> RRF merge ->
optional FlashRank rerank -> top-k chunks with sources.
This is the ONLY interface the agent (or MCP clients) ever sees.
"""

from __future__ import annotations

from pathlib import Path

from klaude_core import Config, Ollama

from .chunker import chunk_markdown
from .store import KnowledgeStore

RRF_K = 60


def _rrf(ranked_lists: list[list[dict]]) -> list[dict]:
    scores: dict[str, float] = {}
    by_id: dict[str, dict] = {}
    for hits in ranked_lists:
        for rank, hit in enumerate(hits):
            hid = hit["id"]
            scores[hid] = scores.get(hid, 0.0) + 1.0 / (RRF_K + rank + 1)
            if hid not in by_id or hit.get("source"):
                by_id[hid] = hit
    order = sorted(scores, key=scores.get, reverse=True)
    return [by_id[h] for h in order]


class Knowledge:
    def __init__(self, cfg: Config, ollama: Ollama | None = None):
        self.cfg = cfg
        self.ollama = ollama or Ollama(cfg.ollama_url)
        self.store = KnowledgeStore(cfg.knowledge_dir)
        self._reranker = None
        try:  # optional dependency: pip install flashrank
            from flashrank import Ranker

            self._reranker = Ranker(max_length=512)
        except Exception:
            self._reranker = None

    # --- ingest -------------------------------------------------------------
    def learn_text(self, collection: str, text: str, source: str, title: str = "") -> int:
        # 1. keep raw material so re-indexing never needs re-scraping
        safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in source)[-120:]
        cache = self.cfg.docs_cache_dir / collection
        cache.mkdir(parents=True, exist_ok=True)
        (cache / f"{safe}.md").write_text(text)

        # 2. chunk -> embed -> store
        chunks = chunk_markdown(text, title=title)
        if not chunks:
            return 0
        vectors = self.ollama.embed(self.cfg.models["embed"], [c.text for c in chunks])
        return self.store.add(
            collection,
            [c.text for c in chunks],
            vectors,
            source=source,
            sections=[c.section for c in chunks],
        )

    def learn_file(self, collection: str, path: str) -> int:
        p = Path(path)
        return self.learn_text(collection, p.read_text(), source=str(p), title=p.stem)

    # --- retrieve -------------------------------------------------------------
    def query(self, question: str, collection: str = "", k: int = 6) -> list[dict]:
        collections = [collection] if collection else self.store.collections()
        qvec = self.ollama.embed(self.cfg.models["embed"], [question])[0]

        merged: list[dict] = []
        for col in collections:
            vec_hits = self.store.vector_search(col, qvec, k * 2)
            kw_hits = self.store.keyword_search(col, question, k * 2)
            for hit in _rrf([vec_hits, kw_hits]):
                hit["collection"] = col
                merged.append(hit)

        if self._reranker and merged:
            from flashrank import RerankRequest

            req = RerankRequest(
                query=question,
                passages=[{"id": i, "text": h["text"]} for i, h in enumerate(merged)],
            )
            ranked = self._reranker.rerank(req)
            merged = [merged[r["id"]] for r in ranked]

        return merged[:k]

    def query_as_context(self, question: str, collection: str = "", k: int = 6) -> str:
        hits = self.query(question, collection, k)
        if not hits:
            return "No relevant local knowledge found."
        parts = []
        for h in hits:
            src = h.get("source") or h.get("collection", "")
            parts.append(f"--- source: {src} ---\n{h['text']}")
        return "\n\n".join(parts)
