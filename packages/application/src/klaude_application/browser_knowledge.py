"""Browse exact active indexed text without starting the knowledge engine or a model."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .library_inventory import public_text, readonly

PAGE_SIZE = 20
MAX_CHUNK = 65_536


def _validate(library: str, source: str, query: str, offset: int) -> None:
    for value, limit in ((library, 160), (source, 8192), (query, 200)):
        if (
            not isinstance(value, str)
            or len(value) > limit
            or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)
        ):
            raise ValueError("Invalid Knowledge filter")
    if type(offset) is not int or not 0 <= offset <= 1_000_000 or source and not library:
        raise ValueError("Choose a library and valid page")


def _active(db: sqlite3.Connection) -> str:
    """One projection for browse, counts, search and readers, including legacy FTS."""
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
    selects = []
    disabled = (
        "AND NOT EXISTS (SELECT 1 FROM disabled_skills d WHERE a.owner='skill:'||d.name)"
        if "disabled_skills" in tables
        else ""
    )
    if {"chunks_v2", "active_sources"} <= tables:
        selects.append(
            "SELECT 'v2' AS kind,c.rowid AS position,c.id,c.library,c.source,c.text,c.owner "
            "FROM chunks_v2 c WHERE EXISTS (SELECT 1 FROM active_sources a "
            "WHERE a.library=c.library AND a.owner=c.owner AND a.source=c.source "
            "AND a.version_id=c.version_id " + disabled + ")"
        )
    if "chunks" in tables:
        active = (
            "WHERE EXISTS (SELECT 1 FROM active_sources a WHERE a.library=c.collection "
            "AND a.source=c.source AND a.owner='legacy:'||c.source " + disabled + ")"
            if "active_sources" in tables
            else ""
        )
        selects.append(
            "SELECT 'legacy' AS kind,c.rowid AS position,c.id,c.collection AS library,"
            "c.source,c.text,'legacy:'||c.source AS owner FROM chunks c " + active
        )
    return " UNION ALL ".join(selects) or (
        "SELECT '' AS kind,0 AS position,'' AS id,'' AS library,'' AS source,'' AS text,"
        "'' AS owner WHERE 0"
    )


def _page(items: list[dict[str, Any]], total: int, offset: int) -> dict[str, Any]:
    return {
        "items": items,
        "total": total,
        "known_total": total,
        "offset": offset,
        "page_size": PAGE_SIZE,
        "more": offset + len(items) < total,
    }


def _token(kind: str, position: int, identity: str) -> str:
    return f"{kind}:{position}:" + hashlib.sha256(identity.encode()).hexdigest()[:24]


def browse_knowledge(
    root: Path,
    *,
    library: str = "",
    source: str = "",
    query: str = "",
    offset: int = 0,
    sources: bool = False,
    chunk: str = "",
) -> dict[str, Any]:
    _validate(library, source, query, offset)
    if not isinstance(chunk, str) or len(chunk) > 80:
        raise ValueError("Invalid chunk identity")
    if sources and (not library or chunk):
        raise ValueError("Choose a library to browse sources")
    if root.is_symlink():
        raise ValueError("Unsafe knowledge store")
    database = root / "fts.db"
    mode = "sources" if sources else "chunks" if library or query or chunk else "libraries"
    if not database.exists():
        if chunk:
            raise ValueError("Chunk is no longer available; reload Knowledge")
        return {
            **_page([], 0, offset),
            "mode": mode,
            "library": library,
            "source": source,
            "summary": {"sources": 0, "chunks": 0},
            "available": not root.exists(),
        }
    with readonly(database) as db:
        db.create_function(
            "casefold", 1, lambda text: str(text or "").casefold(), deterministic=True
        )
        db.execute("BEGIN")
        active = "WITH active AS (" + _active(db) + ") "
        scope, parameters = "1=1", []
        if library:
            scope += " AND library=?"
            parameters.append(library)
        summary = db.execute(
            active + "SELECT COUNT(DISTINCT source),COUNT(*) FROM active WHERE " + scope, parameters
        ).fetchone()
        if source:
            scope += " AND source=?"
            parameters.append(source)
        if chunk:
            if not library or not re.fullmatch(
                r"(?:v2|legacy):[1-9][0-9]{0,18}:[a-f0-9]{24}", chunk
            ):
                raise ValueError("Invalid chunk identity")
            kind, position, _ = chunk.split(":")
            row = db.execute(
                active + "SELECT kind,position,id,library,source,"
                "substr(text,1,?),length(text) FROM active WHERE "
                + scope
                + " AND kind=? AND position=?",
                [MAX_CHUNK, *parameters, kind, int(position)],
            ).fetchone()
            if row is None or _token(row[0], row[1], row[2]) != chunk:
                raise ValueError("Chunk changed or was deleted; reload Knowledge")
            # Preserve whitespace and line breaks; content is always rendered as DOM text.
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", row[5])
            return {
                "item": {
                    "id": chunk,
                    "library": row[3],
                    "source": public_text(row[4], 8192),
                    "text": text,
                    "characters": row[6],
                    "truncated": row[6] > MAX_CHUNK,
                }
            }
        if query:
            scope += (
                " AND (instr(casefold(library),casefold(?))>0 OR "
                "instr(casefold(source),casefold(?))>0 OR instr(casefold(text),casefold(?))>0)"
            )
            parameters.extend((query, query, query))
        if mode in {"libraries", "sources"}:
            key = "library" if mode == "libraries" else "source"
            grouped = (
                active
                + f"SELECT {key},COUNT(DISTINCT source),COUNT(*),"
                + (
                    "GROUP_CONCAT(DISTINCT CASE WHEN owner LIKE 'docs:%' THEN substr(owner,6) END)"
                    if sources
                    else "NULL"
                )
                + " FROM active WHERE "
            )
            grouped += scope + f" GROUP BY {key}"
            total = db.execute("SELECT COUNT(*) FROM (" + grouped + ")", parameters).fetchone()[0]
            rows = db.execute(
                grouped + f" ORDER BY {key} COLLATE NOCASE,{key} LIMIT ? OFFSET ?",
                [*parameters, PAGE_SIZE, offset],
            ).fetchall()
            items = [
                {
                    "id": row[0],
                    "sources": row[1],
                    "chunks": row[2],
                    **({"managed_names": (row[3] or "").split(",")[:10]} if sources else {}),
                }
                for row in rows
            ]
        else:
            total = db.execute(
                active + "SELECT COUNT(*) FROM active WHERE " + scope, parameters
            ).fetchone()[0]
            rows = db.execute(
                active + "SELECT kind,position,id,library,source,length(text),"
                "substr(text,MAX(1,instr(casefold(text),casefold(?))-120),700) "
                "FROM active WHERE "
                + scope
                + " ORDER BY library,source,kind,position LIMIT ? OFFSET ?",
                [query, *parameters, PAGE_SIZE, offset],
            ).fetchall()
            items = [
                {
                    "id": _token(row[0], row[1], row[2]),
                    "library": row[3],
                    "source": public_text(row[4], 8192),
                    "characters": row[5],
                    "text": public_text(row[6], 700),
                }
                for row in rows
            ]
    return {
        **_page(items, total, offset),
        "mode": mode,
        "library": library,
        "source": source,
        "summary": {"sources": summary[0], "chunks": summary[1]},
        "available": True,
    }


def _snapshot(db: sqlite3.Connection, library: str, source: str) -> tuple[str, int, int]:
    """Include historical/staging metadata so concurrent replacements invalidate review."""
    digest = hashlib.sha256()
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
    scope, args = "library=?", [library]
    if source:
        scope += " AND source=?"
        args.append(source)
    for table in ("active_sources", "source_versions", "chunks_v2", "chunks"):
        if table not in tables:
            continue
        where = scope.replace("library", "collection") if table == "chunks" else scope
        # Do not hash vectors or initialize LanceDB while preparing a review.
        for row in db.execute(f"SELECT * FROM {table} WHERE {where} ORDER BY rowid", args):
            digest.update(json.dumps([table, *row], ensure_ascii=True).encode())
    active = "WITH active AS (" + _active(db) + ") "
    count = db.execute(
        active + "SELECT COUNT(DISTINCT source),COUNT(*) FROM active WHERE " + scope, args
    ).fetchone()
    return digest.hexdigest(), count[0], count[1]


def prepare_delete(root: Path, draft: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    if set(draft) != {"operation", "library", "source"}:
        raise ValueError("Choose the exact knowledge to delete")
    library, source = draft["library"], draft["source"]
    _validate(library, source, "", 0)
    if not library or root.is_symlink():
        raise ValueError("Choose a Knowledge library")
    with readonly(root / "fts.db") as db:
        db.execute("BEGIN")
        fingerprint, sources, chunks = _snapshot(db, library, source)
    if not chunks:
        raise ValueError("Knowledge changed; reload before deleting")
    target = f"source {source} in {library}" if source else f"knowledge library {library}"
    return (
        {"library": library, "source": source, "fingerprint": fingerprint},
        "knowledge-index",
        (
            f"Delete {target}? This removes {sources:,} "
            f"{'source' if sources == 1 else 'sources'} and {chunks:,} active "
            f"{'chunk' if chunks == 1 else 'chunks'} "
            "from indexed knowledge, plus their stored index versions. Original files, uploads "
            "and installed Skills are retained. Learning or refreshing can add it again. "
            "This cannot be undone."
        ),
    )


def delete_knowledge(root: Path, library: str, source: str, fingerprint: str) -> None:
    """Recheck the reviewed snapshot under the SQLite write lock, then remove retrieval rows."""
    from klaude_knowledge.store import KnowledgeStore

    _validate(library, source, "", 0)
    if not library or root.is_symlink():
        raise ValueError("Invalid Knowledge target")
    store = KnowledgeStore(root)
    try:
        db = store.fts
        with db:
            db.execute("BEGIN IMMEDIATE")
            if _snapshot(db, library, source)[0] != fingerprint:
                raise ValueError("Knowledge changed; reload and review deletion again")
            args = [library, source] if source else [library]
            scope = "library=?" + (" AND source=?" if source else "")
            versions = [
                row[0]
                for row in db.execute("SELECT version_id FROM source_versions WHERE " + scope, args)
            ]
            old_sources = [
                row[0]
                for row in db.execute(
                    "SELECT DISTINCT source FROM chunks WHERE "
                    + scope.replace("library", "collection"),
                    args,
                )
            ]
            for table in ("active_sources", "chunks_v2", "source_versions"):
                db.execute(f"DELETE FROM {table} WHERE {scope}", args)
            for table in ("chunks", "chunk_sources"):
                db.execute(
                    f"DELETE FROM {table} WHERE " + scope.replace("library", "collection"), args
                )
        # SQLite is authoritative for visibility. Vector cleanup follows the same
        # disposable GC contract as replacement; never replay a committed delete.
        names = store._tables()
        for table, column, values in (
            (store._v2_table(library), "version_id", versions),
            (library, "source", old_sources),
        ):
            if table in names:
                for value in values:
                    try:
                        escaped = value.replace("'", "''")
                        store.db.open_table(table).delete(f"{column} = '{escaped}'")
                    except Exception:
                        pass
    finally:
        store.fts.close()
