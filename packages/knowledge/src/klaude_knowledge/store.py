"""Knowledge store: one legacy LanceDB table per collection plus versioned v2 rows.

LanceDB serves vector search; a plain SQLite FTS5 table mirrors the same
chunks for BM25 keyword search — stdlib, zero server, zero API drift.

The v2 path is deliberately non-destructive. Existing per-library LanceDB
tables are left in place and registered as active legacy versions in SQLite
metadata. New writes go to side-by-side v2 tables with a version_id column, then
SQLite atomically swaps active_sources. Retrieval only returns rows whose
version is active; legacy rows remain queryable until their source is replaced.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import lancedb


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _table_slug(collection: str) -> str:
    cleaned = "".join(c.lower() if c.isalnum() else "_" for c in collection.strip())
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    prefix = cleaned[:48] or "library"
    suffix = hashlib.sha256(collection.encode()).hexdigest()[:12]
    return f"kc_v2_{prefix}_{suffix}"


def _legacy_version_id(collection: str, source: str) -> str:
    digest = hashlib.sha256(f"{collection}\0{source}".encode()).hexdigest()[:24]
    return f"legacy:{digest}"


class KnowledgeStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(root))
        # Hybrid retrieval can execute on Klaude's serialized TUI worker.
        self.fts = sqlite3.connect(root / "fts.db", check_same_thread=False)
        self.fts.row_factory = sqlite3.Row
        self.fts.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
                id UNINDEXED, collection UNINDEXED, source UNINDEXED, text
            )"""
        )
        columns = {
            row[1]
            for row in self.fts.execute("PRAGMA table_info(chunks)").fetchall()
        }
        if "source" not in columns:
            self.fts.execute("DROP TABLE chunks")
            self.fts.execute(
                """CREATE VIRTUAL TABLE chunks USING fts5(
                    id UNINDEXED, collection UNINDEXED, source UNINDEXED, text
                )"""
            )
        self.fts.execute(
            """CREATE TABLE IF NOT EXISTS chunk_sources (
                id TEXT NOT NULL,
                collection TEXT NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY (id, collection, source)
            )"""
        )
        self.fts.execute(
            """CREATE TABLE IF NOT EXISTS source_versions (
                version_id TEXT PRIMARY KEY,
                library TEXT NOT NULL,
                owner TEXT NOT NULL,
                source TEXT NOT NULL,
                checksum TEXT NOT NULL,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                operation_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                activated_at REAL,
                error TEXT
            )"""
        )
        self.fts.execute(
            """CREATE TABLE IF NOT EXISTS active_sources (
                library TEXT NOT NULL,
                owner TEXT NOT NULL,
                source TEXT NOT NULL,
                version_id TEXT NOT NULL,
                PRIMARY KEY (library, owner, source)
            )"""
        )
        self.fts.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS chunks_v2 USING fts5(
                id UNINDEXED,
                library UNINDEXED,
                owner UNINDEXED,
                source UNINDEXED,
                version_id UNINDEXED,
                text
            )"""
        )
        if "source" not in columns:
            self._rebuild_fts_from_lance()
        self._register_legacy_active_sources()
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

    def _library_tables(self) -> list[str]:
        return [name for name in self._tables() if not name.startswith("kc_v2_")]

    def _v2_table(self, library: str) -> str:
        return _table_slug(library)

    def _rebuild_fts_from_lance(self) -> None:
        """Rebuild keyword-search rows when upgrading from the source-less FTS schema."""
        for collection in self._library_tables():
            table = self.db.open_table(collection)
            for row in table.to_arrow().to_pylist():
                source = row.get("source")
                text = row.get("text")
                chunk_id = row.get("id")
                if not source or not text or not chunk_id:
                    continue
                self.fts.execute(
                    "INSERT INTO chunks (id, collection, source, text) VALUES (?,?,?,?)",
                    (chunk_id, collection, source, text),
                )
                self.fts.execute(
                    "INSERT OR REPLACE INTO chunk_sources (id, collection, source) VALUES (?,?,?)",
                    (chunk_id, collection, source),
                )

    def _register_legacy_active_sources(self) -> None:
        """Expose existing unversioned rows through metadata without rewriting them."""
        rows = self.fts.execute(
            "SELECT collection, source, COUNT(*) AS chunk_count "
            "FROM chunks GROUP BY collection, source"
        ).fetchall()
        now = time.time()
        for row in rows:
            library = row["collection"]
            source = row["source"]
            if not source:
                continue
            version_id = _legacy_version_id(library, source)
            owner = f"legacy:{source}"
            self.fts.execute(
                """INSERT OR IGNORE INTO source_versions
                   (version_id, library, owner, source, checksum, status, chunk_count,
                    operation_id, created_at, activated_at, error)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    version_id,
                    library,
                    owner,
                    source,
                    "",
                    "active",
                    int(row["chunk_count"]),
                    "legacy-migration",
                    now,
                    now,
                    None,
                ),
            )
            self.fts.execute(
                """INSERT OR IGNORE INTO active_sources
                   (library, owner, source, version_id) VALUES (?,?,?,?)""",
                (library, owner, source, version_id),
            )

    # --- write ------------------------------------------------------------
    def add(
        self,
        collection: str,
        chunks: list[str],
        vectors: list[list[float]],
        source: str,
        sections: list[str] | None = None,
    ) -> int:
        checksum = hashlib.sha256("\n".join(chunks).encode()).hexdigest()
        version_id = self.stage_version(
            collection,
            f"learn:{source}",
            source,
            chunks,
            vectors,
            checksum,
            sections=sections,
        )
        self.activate_versions(collection, f"learn:{source}", {source: version_id})
        self.garbage_collect_obsolete_versions(collection)
        return len(chunks)

    def stage_version(
        self,
        library: str,
        owner: str,
        source: str,
        chunks: list[str],
        vectors: list[list[float]],
        checksum: str,
        *,
        sections: list[str] | None = None,
        operation_id: str = "",
        version_id: str = "",
    ) -> str:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        sections = sections or [""] * len(chunks)
        if len(sections) != len(chunks):
            raise ValueError("chunk/section count mismatch")
        operation_id = operation_id or str(uuid4())
        version_id = version_id or hashlib.sha256(
            f"{operation_id}\0{library}\0{owner}\0{source}\0{checksum}".encode()
        ).hexdigest()[:32]
        now = time.time()
        rows = [
            {
                "id": _hash(f"{version_id}\0{index}\0{text}"),
                "text": text,
                "vector": vec,
                "library": library,
                "owner": owner,
                "source": source,
                "version_id": version_id,
                "section": section,
                "learned_at": now,
            }
            for index, (text, vec, section) in enumerate(
                zip(chunks, vectors, sections, strict=False)
            )
        ]
        self.fts.execute(
            """INSERT OR REPLACE INTO source_versions
               (version_id, library, owner, source, checksum, status, chunk_count,
                operation_id, created_at, activated_at, error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                version_id,
                library,
                owner,
                source,
                checksum,
                "staging",
                len(rows),
                operation_id,
                now,
                None,
                None,
            ),
        )
        self.fts.commit()
        try:
            self._insert_v2_rows(library, rows)
            with self.fts:
                for row in rows:
                    self.fts.execute(
                        """INSERT INTO chunks_v2
                           (id, library, owner, source, version_id, text)
                           VALUES (?,?,?,?,?,?)""",
                        (
                            row["id"],
                            library,
                            owner,
                            source,
                            version_id,
                            row["text"],
                        ),
                    )
            self.verify_version_rows(library, version_id, len(rows))
        except Exception as exc:
            self.mark_version_failed(version_id, str(exc))
            raise
        return version_id

    def _insert_v2_rows(self, library: str, rows: list[dict]) -> None:
        if not rows:
            return
        table = self._v2_table(library)
        if table in self._tables():
            self.db.open_table(table).add(rows)
        else:
            self.db.create_table(table, rows)

    def verify_version_rows(self, library: str, version_id: str, expected: int) -> None:
        fts_count = self.fts.execute(
            "SELECT COUNT(*) FROM chunks_v2 WHERE library=? AND version_id=?",
            (library, version_id),
        ).fetchone()[0]
        if fts_count != expected:
            raise RuntimeError(
                f"FTS staged row count mismatch for {version_id}: {fts_count} != {expected}"
            )
        if expected == 0:
            return
        table = self._v2_table(library)
        if table not in self._tables():
            raise RuntimeError(f"missing LanceDB v2 table for {library}")
        lance_count = sum(
            1
            for row in self.db.open_table(table).to_arrow().to_pylist()
            if row.get("version_id") == version_id
        )
        if lance_count != expected:
            raise RuntimeError(
                f"LanceDB staged row count mismatch for {version_id}: {lance_count} != {expected}"
            )

    def activate_versions(self, library: str, owner: str, source_versions: dict[str, str]) -> None:
        now = time.time()
        with self.fts:
            previous_rows = self.fts.execute(
                "SELECT source, version_id FROM active_sources WHERE library=? AND owner=?",
                (library, owner),
            ).fetchall()
            previous = {row["source"]: row["version_id"] for row in previous_rows}
            for source, version_id in source_versions.items():
                row = self.fts.execute(
                    """SELECT status FROM source_versions
                       WHERE library=? AND owner=? AND source=? AND version_id=?""",
                    (library, owner, source, version_id),
                ).fetchone()
                if row is None:
                    raise RuntimeError(f"unknown staged version: {version_id}")
                if row["status"] != "staging":
                    raise RuntimeError(f"version {version_id} is not staging")

            self.fts.execute(
                "DELETE FROM active_sources WHERE library=? AND owner=?",
                (library, owner),
            )
            for source, version_id in source_versions.items():
                self.fts.execute(
                    """INSERT INTO active_sources
                       (library, owner, source, version_id) VALUES (?,?,?,?)""",
                    (library, owner, source, version_id),
                )
                self.fts.execute(
                    """UPDATE source_versions
                       SET status='active', activated_at=?, error=NULL
                       WHERE version_id=?""",
                    (now, version_id),
                )
                # Once a managed owner replaces a legacy source, the legacy row
                # becomes historical but the original LanceDB table is untouched.
                self.fts.execute(
                    """DELETE FROM active_sources
                       WHERE library=? AND source=? AND owner LIKE 'legacy:%'""",
                    (library, source),
                )

            obsolete = [
                version_id
                for source, version_id in previous.items()
                if source not in source_versions or source_versions[source] != version_id
            ]
            for version_id in obsolete:
                self.fts.execute(
                    "UPDATE source_versions SET status='obsolete' WHERE version_id=?",
                    (version_id,),
                )

            replaced_sources = set(source_versions)
            if replaced_sources:
                placeholders = ",".join("?" for _ in replaced_sources)
                self.fts.execute(
                    f"""UPDATE source_versions
                        SET status='obsolete'
                        WHERE library=? AND owner LIKE 'legacy:%'
                          AND source IN ({placeholders})""",
                    (library, *replaced_sources),
                )

    def mark_version_failed(self, version_id: str, error: str) -> None:
        with self.fts:
            self.fts.execute(
                "UPDATE source_versions SET status='failed', error=? WHERE version_id=?",
                (error[:1000], version_id),
            )

    def recover_incomplete_operations(self) -> int:
        with self.fts:
            cursor = self.fts.execute(
                "UPDATE source_versions SET status='failed', error=? WHERE status='staging'",
                ("recovered incomplete staging operation",),
            )
        return cursor.rowcount if cursor.rowcount is not None else 0

    def garbage_collect_obsolete_versions(self, library: str | None = None) -> int:
        params = [library] if library else []
        where = "WHERE status IN ('obsolete', 'failed')"
        if library:
            where += " AND library=?"
        rows = self.fts.execute(
            f"SELECT version_id, library FROM source_versions {where}",
            params,
        ).fetchall()
        removed = 0
        for row in rows:
            version_id = row["version_id"]
            version_library = row["library"]
            with self.fts:
                self.fts.execute("DELETE FROM chunks_v2 WHERE version_id=?", (version_id,))
                self.fts.execute(
                    "DELETE FROM source_versions WHERE version_id=? "
                    "AND version_id NOT IN (SELECT version_id FROM active_sources)",
                    (version_id,),
                )
            table = self._v2_table(version_library)
            if table in self._tables():
                try:
                    self.db.open_table(table).delete(f"version_id = '{version_id}'")
                except Exception:
                    pass
            removed += 1
        return removed

    def delete_sources(self, collection: str, sources: list[str]) -> None:
        if not sources:
            return
        with self.fts:
            for source in sources:
                active_rows = self.fts.execute(
                    "SELECT version_id FROM active_sources WHERE library=? AND source=?",
                    (collection, source),
                ).fetchall()
                self.fts.execute(
                    "DELETE FROM active_sources WHERE library=? AND source=?",
                    (collection, source),
                )
                for row in active_rows:
                    self.fts.execute(
                        "UPDATE source_versions SET status='obsolete' WHERE version_id=?",
                        (row["version_id"],),
                    )
                self.fts.execute(
                    "DELETE FROM chunks WHERE collection=? AND source=?",
                    (collection, source),
                )
                self.fts.execute(
                    "DELETE FROM chunk_sources WHERE collection=? AND source=?",
                    (collection, source),
                )

        names = self._tables()
        if collection in names:
            tbl = self.db.open_table(collection)
            for source in sources:
                escaped = source.replace("'", "''")
                tbl.delete(f"source = '{escaped}'")

    # --- read ---------------------------------------------------------------
    def source_exists(self, collection: str, source: str, owner: str = "") -> bool:
        if owner:
            row = self.fts.execute(
                """SELECT 1 FROM active_sources
                   WHERE library=? AND owner=? AND source=? LIMIT 1""",
                (collection, owner, source),
            ).fetchone()
            return row is not None
        row = self.fts.execute(
            "SELECT 1 FROM active_sources WHERE library=? AND source=? LIMIT 1",
            (collection, source),
        ).fetchone()
        return row is not None

    def active_source_checksum(self, collection: str, owner: str, source: str) -> str | None:
        row = self.fts.execute(
            """SELECT sv.checksum
               FROM active_sources ac
               JOIN source_versions sv ON sv.version_id=ac.version_id
               WHERE ac.library=? AND ac.owner=? AND ac.source=? LIMIT 1""",
            (collection, owner, source),
        ).fetchone()
        return row["checksum"] if row else None

    def active_owner_checksums(self, collection: str, owner: str) -> dict[str, str]:
        rows = self.fts.execute(
            """SELECT ac.source, sv.checksum
               FROM active_sources ac
               JOIN source_versions sv ON sv.version_id=ac.version_id
               WHERE ac.library=? AND ac.owner=?""",
            (collection, owner),
        ).fetchall()
        return {row["source"]: row["checksum"] for row in rows}

    def _active_versions(self, collection: str) -> set[str]:
        rows = self.fts.execute(
            "SELECT version_id FROM active_sources WHERE library=?",
            (collection,),
        ).fetchall()
        return {row["version_id"] for row in rows}

    def _active_legacy_sources(self, collection: str) -> set[str]:
        rows = self.fts.execute(
            """SELECT source FROM active_sources
               WHERE library=? AND version_id LIKE 'legacy:%'""",
            (collection,),
        ).fetchall()
        return {row["source"] for row in rows}

    def vector_search(self, collection: str, vector: list[float], k: int) -> list[dict]:
        hits: list[dict] = []
        active_versions = self._active_versions(collection)
        table = self._v2_table(collection)
        if table in self._tables() and active_versions:
            try:
                v2_hits = self.db.open_table(table).search(vector).limit(max(k * 20, k)).to_list()
            except Exception:
                v2_hits = []
            for h in v2_hits:
                if h.get("version_id") in active_versions:
                    hits.append(
                        {
                            "id": h["id"],
                            "text": h["text"],
                            "source": h["source"],
                            "section": h.get("section", ""),
                            "version_id": h.get("version_id", ""),
                            "vector_distance": h.get("_distance"),
                            "vector_rank": len(hits) + 1,
                        }
                    )
                    if len(hits) >= k:
                        break
        legacy_sources = self._active_legacy_sources(collection)
        if len(hits) < k and collection in self._library_tables() and legacy_sources:
            tbl = self.db.open_table(collection)
            try:
                legacy_hits = tbl.search(vector).limit(max(k * 20, k)).to_list()
            except Exception:
                legacy_hits = []
            for h in legacy_hits:
                if h.get("source") in legacy_sources:
                    hits.append(
                        {
                            "id": h["id"],
                            "text": h["text"],
                            "source": h["source"],
                            "section": h.get("section", ""),
                            "version_id": _legacy_version_id(collection, h["source"]),
                            "vector_distance": h.get("_distance"),
                            "vector_rank": len(hits) + 1,
                        }
                    )
                    if len(hits) >= k:
                        break
        return hits[:k]

    def keyword_search(self, collection: str, query: str, k: int) -> list[dict]:
        # FTS5 MATCH syntax chokes on punctuation; quote each term.
        terms = [t for t in "".join(c if c.isalnum() else " " for c in query).split() if t]
        if not terms:
            return []
        match = " OR ".join(f'"{t}"' for t in terms)
        hits: list[dict] = []
        active_versions = self._active_versions(collection)
        if active_versions:
            rows = self.fts.execute(
                """SELECT id, text, source, version_id FROM chunks_v2
                   WHERE library=? AND chunks_v2 MATCH ?
                   ORDER BY rank LIMIT ?""",
                (collection, match, max(k * 20, k)),
            ).fetchall()
            for row in rows:
                if row["version_id"] in active_versions:
                    hits.append(
                        {
                            "id": row["id"],
                            "text": row["text"],
                            "source": row["source"],
                            "section": "",
                            "version_id": row["version_id"],
                            "keyword_rank": len(hits) + 1,
                        }
                    )
                    if len(hits) >= k:
                        return hits
        legacy_sources = self._active_legacy_sources(collection)
        if legacy_sources:
            rows = self.fts.execute(
                "SELECT id, text, source FROM chunks WHERE collection=? AND chunks MATCH ? "
                "ORDER BY rank LIMIT ?",
                (collection, match, max(k * 20, k)),
            ).fetchall()
            for row in rows:
                if row["source"] in legacy_sources:
                    hits.append(
                        {
                            "id": row["id"],
                            "text": row["text"],
                            "source": row["source"],
                            "section": "",
                            "version_id": _legacy_version_id(collection, row["source"]),
                            "keyword_rank": len(hits) + 1,
                        }
                    )
                    if len(hits) >= k:
                        return hits
        return hits

    def collections(self) -> list[str]:
        legacy = set(self._library_tables())
        active = {
            row["library"]
            for row in self.fts.execute("SELECT DISTINCT library FROM active_sources").fetchall()
        }
        return sorted(legacy | active)

    def library_sources(self, collection: str) -> list[str]:
        rows = self.fts.execute(
            "SELECT DISTINCT source FROM active_sources WHERE library=? ORDER BY source",
            (collection,),
        ).fetchall()
        return [row["source"] for row in rows]

    def debug_versions(self) -> list[dict]:
        return [
            dict(row)
            for row in self.fts.execute(
                "SELECT * FROM source_versions ORDER BY created_at, version_id"
            ).fetchall()
        ]
