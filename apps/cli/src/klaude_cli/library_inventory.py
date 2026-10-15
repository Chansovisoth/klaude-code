"""Bounded read-only projections of existing stores for the Library workspace.

No store constructors, schema migrations, embedding calls or model content.
"""

from __future__ import annotations

import contextlib
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

PAGE_SIZE = 100


def public_text(value: object, limit: int = 500) -> str:
    text = str(value or "")
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)[:limit]


def public_content_sql(alias: str, limit: int | None = 800) -> str:
    # Decode before slicing: truncating encoded JSON breaks long string/Unicode
    # previews and can expose an incomplete structured attachment block.
    content = alias + ".content"
    decoded = f"json_extract({content},'$')"
    plain = content
    if limit is not None:
        decoded, plain = f"substr({decoded},1,{limit})", f"substr({content},1,{limit})"
    return (
        f"CASE WHEN json_valid({content}) THEN CASE WHEN json_type({content})='text' "
        f"THEN {decoded} ELSE '[Structured content]' END ELSE {plain} END"
    )


@contextlib.contextmanager
def readonly(database: Path):
    if database.is_symlink() or not database.is_file():
        raise ValueError("Store is not a regular database")
    with contextlib.closing(
        sqlite3.connect(database.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2)
    ) as db:
        db.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 3
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        yield db


def session_inventory(
    database: Path, *, archived: bool = False, query: str = "", offset: int = 0
) -> dict[str, Any]:
    if not database.exists():
        return {"items": [], "more": False}
    with readonly(database) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
        if "turns" not in tables:
            return {"items": [], "more": False}
        has_archive = "session_archive" in tables
        archive = (
            "EXISTS (SELECT 1 FROM session_archive a WHERE a.session_id=t.session_id)"
            if has_archive
            else "0"
        )
        names = (
            "(SELECT name FROM session_names n WHERE n.session_id=t.session_id)"
            if "session_names" in tables
            else "NULL"
        )
        first = (
            f"(SELECT {public_content_sql('f', 160)} FROM turns f WHERE f.session_id=t.session_id "
            "AND f.role='user' ORDER BY ts,rowid LIMIT 1)"
        )
        conditions = [archive if archived else "NOT (" + archive + ")"]
        params: list[Any] = []
        if query:
            # Literal substring, not SQL/FTS syntax; search public content only.
            conditions.append(
                f"(instr(lower(COALESCE({names},'')),lower(?))>0 OR EXISTS "
                "(SELECT 1 FROM turns s WHERE s.session_id=t.session_id "
                "AND s.role IN ('user','assistant') AND "
                f"instr(lower({public_content_sql('s', None)}),lower(?))>0))"
            )
            params.extend((query[:200], query[:200]))
        rows = db.execute(
            f"SELECT t.session_id,MAX(t.ts),COUNT(*),{names},{first} FROM turns t "
            "WHERE t.role IN ('user','assistant') AND "
            + " AND ".join(conditions)
            + " GROUP BY t.session_id ORDER BY MAX(t.ts) DESC,t.session_id LIMIT ? OFFSET ?",
            (*params, PAGE_SIZE + 1, max(0, min(offset, 1_000_000))),
        ).fetchall()
        active = set()
        if "session_live" in tables:
            active = {
                row[0]
                for row in db.execute(
                    "SELECT session_id FROM session_live WHERE state='running' "
                    "AND owner_lease_until>? LIMIT 1000",
                    (time.time(),),
                )
            }
    return {
        "items": [
            {
                "id": sid,
                "title": public_text(name, 160) or public_text(first, 160) or "Untitled session",
                "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                "turns": count,
                "active": sid in active,
                "archived": archived,
            }
            for sid, ts, count, name, first in rows[:PAGE_SIZE]
        ],
        "more": len(rows) > PAGE_SIZE,
    }


def session_preview(database: Path, session_id: str) -> dict[str, Any]:
    with readonly(database) as db:
        rows = db.execute(
            f"SELECT role,{public_content_sql('t')} FROM turns t WHERE session_id=? "
            "AND role IN ('user','assistant') ORDER BY ts DESC,rowid DESC LIMIT 8",
            (session_id,),
        ).fetchall()
    if not rows:
        raise ValueError("Session no longer exists")
    return {
        "turns": [
            {"role": role, "text": public_text(content, 800)} for role, content in reversed(rows)
        ]
    }


def knowledge_inventory(root: Path) -> dict[str, Any]:
    if root.is_symlink():
        raise ValueError("Unsafe knowledge store")
    database = root / "fts.db"
    if not database.exists():
        from itertools import islice

        paths = list(islice(root.glob("*.lance"), 1001)) if root.exists() else []
        legacy_items = [
            {"id": path.name.removesuffix(".lance"), "sources": None, "chunks": None}
            for path in paths
            if not path.name.startswith("kc_v2_")
        ]
        return {
            "items": legacy_items[:1000],
            "more": len(legacy_items) > 1000,
            "metadata_only": True,
        }
    with readonly(database) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
        items: dict[str, dict[str, Any]] = {}
        if {"active_sources", "source_versions"} <= tables:
            disabled = (
                "AND NOT EXISTS (SELECT 1 FROM disabled_skills d WHERE a.owner='skill:'||d.name)"
                if "disabled_skills" in tables
                else ""
            )
            for library, count, chunks in db.execute(
                "SELECT a.library,COUNT(*),SUM(v.chunk_count) FROM active_sources a "
                "JOIN source_versions v ON a.version_id=v.version_id WHERE 1=1 "
                + disabled
                + " GROUP BY a.library ORDER BY a.library LIMIT 1001"
            ):
                items[library] = {"id": library, "sources": count, "chunks": chunks or 0}
        elif "chunks" in tables:
            for library, count, chunks in db.execute(
                "SELECT collection,COUNT(DISTINCT source),COUNT(*) FROM chunks "
                "GROUP BY collection ORDER BY collection LIMIT 1001"
            ):
                items[library] = {"id": library, "sources": count, "chunks": chunks}
    # Legacy library tables can exist without source metadata, including empty
    # libraries. Read directory names only; do not open or migrate LanceDB.
    if root.is_symlink():
        raise ValueError("Unsafe knowledge store")
    for index, path in enumerate(root.iterdir()):
        if index >= 2000:
            break
        if path.name.endswith(".lance") and not path.name.startswith("kc_v2_"):
            library = path.name.removesuffix(".lance")
            items.setdefault(library, {"id": library, "sources": None, "chunks": None})
    values = [items[key] for key in sorted(items)]
    return {"items": values[:1000], "more": len(values) > 1000, "metadata_only": True}


def knowledge_search(root: Path, library: str, query: str) -> dict[str, Any]:
    terms = re.findall(r"\w+", query[:200], re.UNICODE)[:12]
    if not terms:
        raise ValueError("Enter words to search")
    match = " OR ".join('"' + term + '"' for term in terms)
    with readonly(root / "fts.db") as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master")}
        hits: list[dict[str, str]] = []
        if {"active_sources", "chunks_v2"} <= tables:
            disabled = (
                "AND NOT EXISTS (SELECT 1 FROM disabled_skills d WHERE a.owner='skill:'||d.name)"
                if "disabled_skills" in tables
                else ""
            )
            rows = db.execute(
                "SELECT source,snippet(chunks_v2,5,'','', ' … ',48) FROM chunks_v2 "
                "WHERE chunks_v2 MATCH ? AND library=? AND EXISTS "
                "(SELECT 1 FROM active_sources a WHERE a.library=chunks_v2.library "
                "AND a.owner=chunks_v2.owner AND a.source=chunks_v2.source "
                "AND a.version_id=chunks_v2.version_id " + disabled + ") "
                "ORDER BY rank LIMIT 20",
                (match, library),
            ).fetchall()
            hits.extend(
                {"source": public_text(source), "text": public_text(text, 1200)}
                for source, text in rows
            )
        if "chunks" in tables and len(hits) < 20:
            active = (
                "AND EXISTS (SELECT 1 FROM active_sources a JOIN source_versions v "
                "ON a.version_id=v.version_id WHERE a.library=chunks.collection "
                "AND a.source=chunks.source AND a.owner='legacy:'||chunks.source "
                "AND v.status='active') "
                if {"active_sources", "source_versions"} <= tables
                else ""
            )
            rows = db.execute(
                "SELECT source,snippet(chunks,3,'','', ' … ',48) FROM chunks "
                "WHERE chunks MATCH ? AND collection=? " + active + "ORDER BY rank LIMIT ?",
                (match, library, 20 - len(hits)),
            ).fetchall()
            hits.extend(
                {"source": public_text(source), "text": public_text(text, 1200)}
                for source, text in rows
            )
    return {"hits": hits}


def execute_library(request: dict[str, Any]) -> dict[str, Any]:
    operation = request["operation"]
    if operation in {"research-list", "research-detail"}:
        from types import SimpleNamespace

        from klaude_core.research import ResearchStore, read_research_defaults
        root = Path(request["database"]).parent
        research_store = ResearchStore(root / "library")
        result = (
            {"item": research_store.get(request["target"])}
            if operation == "research-detail"
            else research_store.listing(request.get("offset", 0))
        )
        result["defaults"] = read_research_defaults(SimpleNamespace(data_dir=root)).public()
        return result
    if operation == "knowledge-sources":
        from .library_knowledge import source_inventory

        return source_inventory(Path(request["database"]).parent / "docs-sources",
                                request.get("target", ""), request.get("offset", 0))
    if operation.startswith("artifact-"):
        from klaude_core.library_artifacts import ArtifactStore

        store = ArtifactStore(Path(request["database"]).parent / "library")
        if operation == "artifact-list":
            return store.listing(
                request["artifact_kind"], archived=request.get("archived", False),
                query=request.get("query", ""), offset=request.get("offset", 0),
                sort=request.get("sort", "newest"), format=request.get("format", ""),
            )
        if operation == "artifact-preview":
            return store.preview(request["target"])
        if operation == "artifact-detail":
            item = store.get(request["target"])
            provenance = store.generation_info(item["id"])
            if provenance:
                item["generation"] = provenance
            return {"item": item}
        raise ValueError("Unknown artifact read operation")
    if operation in {"sessions", "archive"}:
        return session_inventory(
            Path(request["database"]),
            archived=operation == "archive",
            query=request.get("query", ""),
            offset=request.get("offset", 0),
        )
    if operation == "preview":
        return session_preview(Path(request["database"]), request["target"])
    if operation == "knowledge":
        return knowledge_inventory(Path(request["knowledge_root"]))
    if operation == "query":
        return knowledge_search(
            Path(request["knowledge_root"]), request["target"], request["query"]
        )
    raise ValueError("Unknown Library operation")
