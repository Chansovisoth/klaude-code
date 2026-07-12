"""Knowledge store: one LanceDB table per collection + an FTS5 mirror.

LanceDB serves vector search; a plain SQLite FTS5 table mirrors the same
chunks for BM25 keyword search — stdlib, zero server, zero API drift.
Rows are deduped by content hash; re-learning a source replaces its rows.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path

import lancedb


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class KnowledgeStore:
    def __init__(self, root: Path):
        self.root = root
        self.db = lancedb.connect(str(root))
        self.fts = sqlite3.connect(root / "fts.db")
        self.fts.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                id UNINDEXED, collection UNINDEXED, text
            )"""
        )
        self.fts.commit()


    def _tables(self) -> list[str]:
        """List table names across lancedb versions (list_tables API changed)."""
        try:
            resp = self.db.list_tables()
        except AttributeError:  # older lancedb
            return list(self.db.table_names())
        if hasattr(resp, "tables"):
            return list(resp.tables)
        return [t.name if hasattr(t, "name") else str(t) for t in resp]

    # --- write ------------------------------------------------------------
    def add(
        self,
        collection: str,
        chunks: list[str],
        vectors: list[list[float]],
        source: str,
        sections: list[str] | None = None,
    ) -> int:
        sections = sections or [""] * len(chunks)
        now = time.time()
        rows = []
        for text, vec, section in zip(chunks, vectors, sections):
            rows.append(
                {
                    "id": _hash(text),
                    "text": text,
                    "vector": vec,
                    "source": source,
                    "section": section,
                    "learned_at": now,
                }
            )
        # replace anything previously learned from this source
        names = self._tables()
        if collection in names:
            tbl = self.db.open_table(collection)
            tbl.delete(f"source = '{source}'")
            tbl.add(rows)
        else:
            tbl = self.db.create_table(collection, rows)

        for r in rows:
            self.fts.execute("DELETE FROM chunks WHERE id=?", (r["id"],))
            self.fts.execute(
                "INSERT INTO chunks (id, collection, text) VALUES (?,?,?)",
                (r["id"], collection, r["text"]),
            )
        self.fts.commit()
        return len(rows)

    # --- read ---------------------------------------------------------------
    def vector_search(self, collection: str, vector: list[float], k: int) -> list[dict]:
        if collection not in self._tables():
            return []
        tbl = self.db.open_table(collection)
        hits = tbl.search(vector).limit(k).to_list()
        return [
            {"id": h["id"], "text": h["text"], "source": h["source"], "section": h["section"]}
            for h in hits
        ]

    def keyword_search(self, collection: str, query: str, k: int) -> list[dict]:
        # FTS5 MATCH syntax chokes on punctuation; quote each term.
        terms = [t for t in "".join(c if c.isalnum() else " " for c in query).split() if t]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        rows = self.fts.execute(
            "SELECT id, text FROM chunks WHERE collection=? AND chunks MATCH ? "
            "ORDER BY rank LIMIT ?",
            (collection, match, k),
        ).fetchall()
        return [{"id": rid, "text": text, "source": "", "section": ""} for rid, text in rows]

    def collections(self) -> list[str]:
        return sorted(self._tables())
