"""The knowledge layer facade: learn(source) and query(question).

Query path: vector search + BM25 in parallel -> RRF merge ->
optional FlashRank rerank -> top-k chunks with sources.
This is the ONLY interface the agent (or MCP clients) ever sees.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from klaude_core import Config, Ollama

from .indexing import IndexDocument, KnowledgeIndexer, text_checksum, write_text_atomic
from .store import KnowledgeStore

RRF_K = 60
MIN_VECTOR_SIMILARITY = 0.35
MIN_LEXICAL_OVERLAP = 0.18
MIN_COMBINED_CONFIDENCE = 0.32
MIN_GLOBAL_CONFIDENCE = 0.52
CANDIDATE_OVERSAMPLE = 4


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", text.lower()) if len(term) > 1}


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _token_overlap(query: str, text: str) -> float:
    query_terms = _terms(query)
    if not query_terms:
        return 0.0
    return len(query_terms & _terms(text)) / len(query_terms)


def vector_distance_to_similarity(distance: float | None, metric: str = "l2") -> float:
    """Convert LanceDB's lower-is-better default distance into 0..1 similarity."""
    if distance is None:
        return 0.0
    try:
        value = max(0.0, float(distance))
    except (TypeError, ValueError):
        return 0.0
    if metric == "cosine":
        return max(0.0, min(1.0, 1.0 - value))
    return 1.0 / (1.0 + value)


@dataclass(frozen=True)
class LibraryRoute:
    libraries: list[str]
    confidence: float
    reason: str
    global_search_allowed: bool = False


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
        self.indexer = KnowledgeIndexer(cfg, self.store, self.ollama)
        self._reranker = None
        try:  # optional dependency: pip install flashrank
            from flashrank import Ranker

            self._reranker = Ranker(max_length=512)
        except Exception:
            self._reranker = None

    # --- ingest -------------------------------------------------------------
    def _cache_path(self, collection: str, source: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-._" else "_" for c in source)[-120:]
        return self.cfg.docs_cache_dir / collection / f"{safe}.md"

    def source_is_current(self, collection: str, text: str, source: str) -> bool:
        owner = f"learn:{source}"
        return self.indexer.active_source_checksum(collection, owner, source) == text_checksum(text)

    def learn_text(self, collection: str, text: str, source: str, title: str = "") -> int:
        if self.source_is_current(collection, text, source):
            return 0
        result = self.indexer.replace_source_atomic(
            collection,
            f"learn:{source}",
            source=source,
            text=text,
            title=title,
        )
        try:
            cache_path = self._cache_path(collection, source)
            write_text_atomic(cache_path, text)
            checksum_path = cache_path.with_suffix(cache_path.suffix + ".sha256")
            write_text_atomic(checksum_path, text_checksum(text) + "\n")
        except Exception:
            pass
        return result.chunk_count

    def learn_file(self, collection: str, path: str) -> int:
        p = Path(path)
        return self.learn_text(collection, p.read_text(), source=str(p), title=p.stem)

    def delete_sources(self, collection: str, sources: list[str]) -> None:
        self.store.delete_sources(collection, sources)

    def replace_owner_snapshot_atomic(
        self,
        collection: str,
        owner: str,
        documents: list[IndexDocument],
    ) -> int:
        return self.indexer.replace_owner_snapshot_atomic(collection, owner, documents).chunk_count

    # --- retrieve -------------------------------------------------------------
    def route_libraries(self, question: str, library: str = "") -> LibraryRoute:
        libraries = self.store.collections()
        if library:
            return LibraryRoute([library], 1.0, "explicit library")

        if not libraries:
            return LibraryRoute([], 0.0, "no libraries")

        question_terms = _terms(question)
        normalized_question = _normalized(question)
        scored: list[tuple[float, str, str]] = []

        for candidate in libraries:
            candidate_terms = _terms(candidate)
            if not candidate_terms:
                continue
            candidate_phrase = _normalized(candidate)
            score = 0.0
            reason = "library token match"
            if candidate_phrase and candidate_phrase in normalized_question:
                score += 1.0
                reason = "exact library match"
            overlap = len(question_terms & candidate_terms) / len(candidate_terms)
            if overlap >= 0.67:
                score = max(score, 0.78 + min(overlap, 1.0) * 0.1)
            elif candidate_phrase.split() and candidate_phrase.split()[0] in question_terms:
                score = max(score, 0.72)
            source_score = 0.0
            for source in self.store.library_sources(candidate):
                source_overlap = _token_overlap(question, source)
                if source_overlap >= 0.5:
                    source_score = max(source_score, 0.72 + min(source_overlap, 1.0) * 0.1)
            if source_score > score:
                score = source_score
                reason = "source metadata match"
            if score:
                scored.append((score, candidate, reason))

        if not scored:
            if len(question_terms) >= 3:
                return LibraryRoute(
                    libraries[: min(12, len(libraries))],
                    0.25,
                    "controlled global candidate search",
                    global_search_allowed=True,
                )
            return LibraryRoute([], 0.0, "no confident library route")
        scored.sort(key=lambda item: (-item[0], item[1]))
        best = scored[0][0]
        chosen = [
            candidate
            for score, candidate, _reason in scored
            if score >= max(0.7, best - 0.3)
        ]
        return LibraryRoute(chosen[:12], best, scored[0][2])

    def matching_collections(self, question: str, collection: str = "") -> list[str]:
        return self.route_libraries(question, collection).libraries

    def _threshold(self, name: str, default: float) -> float:
        return float(getattr(self.cfg, name, default))

    def _accepted_hits(
        self,
        question: str,
        route: LibraryRoute,
        hits: list[dict],
        k: int,
    ) -> list[dict]:
        accepted = []
        min_vector = self._threshold("retrieval_min_vector_similarity", MIN_VECTOR_SIMILARITY)
        min_overlap = self._threshold("retrieval_min_lexical_overlap", MIN_LEXICAL_OVERLAP)
        min_combined = self._threshold("retrieval_min_combined_confidence", MIN_COMBINED_CONFIDENCE)
        min_global = self._threshold("retrieval_min_global_confidence", MIN_GLOBAL_CONFIDENCE)
        for hit in hits:
            overlap = _token_overlap(question, hit.get("text", ""))
            vector_similarity = vector_distance_to_similarity(hit.get("vector_distance"))
            vector_rank_score = 1.0 / (1.0 + float(hit.get("vector_rank") or 999))
            keyword_rank_score = 1.0 / (1.0 + float(hit.get("keyword_rank") or 999))
            backend_score = max(vector_similarity, keyword_rank_score, vector_rank_score)
            confidence = (
                backend_score * 0.45
                + overlap * 0.35
                + route.confidence * 0.20
            )
            if route.global_search_allowed:
                confidence *= 0.85
            threshold = min_global if route.global_search_allowed else min_combined
            has_backend_evidence = (
                vector_similarity >= min_vector
                or overlap >= min_overlap
                or (hit.get("keyword_rank") is not None and overlap >= min_overlap / 2)
            )
            if confidence >= threshold and has_backend_evidence:
                hit["relevance_score"] = round(confidence, 3)
                hit["lexical_overlap"] = round(overlap, 3)
                hit["vector_similarity"] = round(vector_similarity, 3)
                hit["route_reason"] = route.reason
                accepted.append(hit)
        accepted.sort(key=lambda item: item.get("relevance_score", 0), reverse=True)
        return accepted[:k]

    def query(self, question: str, collection: str = "", k: int = 6) -> list[dict]:
        route = self.route_libraries(question, collection)
        if not route.libraries:
            return []
        oversample = int(getattr(self.cfg, "retrieval_candidate_oversample", CANDIDATE_OVERSAMPLE))
        per_backend = max(k * max(2, oversample), k)
        qvec = self.ollama.embed(self.cfg.models["embed"], [question])[0]

        merged: list[dict] = []
        for col in route.libraries:
            vec_hits = self.store.vector_search(col, qvec, per_backend)
            kw_hits = self.store.keyword_search(col, question, per_backend)
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

        return self._accepted_hits(question, route, merged, k)

    def query_as_context(self, question: str, collection: str = "", k: int = 6) -> str:
        hits = self.query(question, collection, k)
        if not hits:
            return "No relevant local knowledge found."
        parts = []
        for h in hits:
            src = h.get("source") or h.get("collection", "")
            library = h.get("collection", "")
            score = h.get("relevance_score", 0)
            parts.append(
                f"--- library: {library}; source: {src}; relevance: {score} ---\n{h['text']}"
            )
        return "\n\n".join(parts)
