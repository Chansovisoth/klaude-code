"""Bounded workspace session inventory, reviews and public Markdown downloads."""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from klaude_core.memory import Memory

from .sessions import SessionDirectory


def session_view(database: Path, workspace: Path, identity: str) -> dict[str, Any]:
    if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", identity):
        raise ValueError("Invalid conversation")
    if database.is_symlink():
        raise ValueError("Unsafe session database")
    with closing(sqlite3.connect(database.absolute().as_uri() + "?mode=ro", uri=True,
                                 timeout=0.2)) as db:
        binding = db.execute("SELECT path FROM application_workspace WHERE session_id=?",
                             (identity,)).fetchone()
        if binding is None or binding[0] != str(workspace.resolve()):
            raise ValueError("Conversation belongs to another workspace")
        count, last = db.execute(
            "SELECT COUNT(*),COALESCE(MAX(rowid),0) FROM turns WHERE session_id=?", (identity,),
        ).fetchone()
        if not count:
            raise ValueError("Conversation is unavailable")
        named = db.execute("SELECT name FROM session_names WHERE session_id=?",
                           (identity,)).fetchone()
        archived = db.execute("SELECT 1 FROM session_archive WHERE session_id=?",
                              (identity,)).fetchone() is not None
    return {"target": identity, "expected_count": count, "expected_last": last,
            "expected_name": str(named[0]) if named else "", "archived": archived}


def prepare_session_operation(
    database: Path, workspace: Path, draft: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    operation = draft["operation"]
    if set(draft) != ({"operation", "target", "name"} if operation == "session-rename"
                      else {"operation", "target"}):
        raise ValueError("Invalid conversation action")
    fields = session_view(database, workspace, draft["target"])
    if operation == "session-rename":
        name = draft["name"]
        if not isinstance(name, str) or any(not char.isprintable() for char in name):
            raise ValueError("Enter a conversation name")
        name = " ".join(name.split())
        if not 1 <= len(name) <= 160:
            raise ValueError("Conversation names must contain 1–160 characters")
        fields["name"] = name
        summary = f"Rename this conversation to: {name}"
    else:
        if operation not in {"session-archive", "session-restore", "session-delete"}:
            raise ValueError("Unknown conversation action")
        if operation != "session-delete" and fields["archived"] != (operation != "session-archive"):
            raise ValueError("Conversation status changed; refresh before reviewing")
        verb = operation.removeprefix("session-").capitalize()
        summary = f"{verb} conversation {draft['target']}."
        if operation == "session-archive":
            summary += " Archiving the current conversation opens a new chat."
        if operation == "session-delete":
            summary += (
                " Permanently removes its saved messages and attachments. This cannot be undone."
            )
    return fields, f"session:{draft['target']}", summary


def run_session_operation(memory: Memory, workspace: Path, request: dict[str, Any]) -> bool:
    fields = session_view(memory.sessions_db, workspace, request["target"])
    if any(fields[key] != request[key] for key in fields):
        return False
    if request["operation"] == "session-rename":
        memory.rename_session(request["target"], request["name"],
                              expected_name=request["expected_name"],
                              expected_workspace=str(workspace.resolve()))
    else:
        memory.change_session_archive(
            request["target"], request["operation"].removeprefix("session-"),
            expected_total_turns=request["expected_count"],
            expected_last_row=request["expected_last"],
            expected_workspace=str(workspace.resolve()),
            expected_archived=(request["archived"]
                               if request["operation"] == "session-delete" else None),
        )
    return True


def public_markdown(memory: Memory, workspace: Path, identity: str) -> bytes:
    session_view(memory.sessions_db, workspace, identity)
    # Bound the input before the existing export formatter materializes records.
    with memory._db_lock:
        size, count = memory.db.execute(
            "SELECT COALESCE(SUM(length(CAST(content AS BLOB))),0),COUNT(*) "
            "FROM turns WHERE session_id=? AND role IN ('user','assistant','system')", (identity,),
        ).fetchone()
        if size > 4 * 1024 * 1024 or count > 10000:
            raise ValueError("Conversation exceeds browser export limits; use the CLI export")
        output = bytearray()
        for chunk in SessionDirectory(memory).markdown_chunks(identity):
            output.extend(chunk.encode("utf-8"))
            if len(output) > 8 * 1024 * 1024:
                raise ValueError("Conversation exceeds browser export limits; use the CLI export")
    return bytes(output)


def workspace_sessions(
    memory: Memory, workspace: Path, *, archived: bool = False, query: str = "",
) -> list[dict[str, Any]]:
    """Filter workspace and archive state before the bounded database page."""
    if not isinstance(query, str) or len(query) > 200 or any(not c.isprintable() for c in query):
        raise ValueError("Enter a search of at most 200 characters")
    terms = list(dict.fromkeys([
        query.casefold().strip(), *re.findall(r"[\w.+#-]+", query.casefold()),
    ]))
    terms = [term for term in terms if term][:8]
    public_text = (
        "CASE WHEN json_valid(t.content) AND json_type(t.content)='text' "
        "THEN json_extract(t.content,'$') ELSE '' END"
    )

    def rank(text: str) -> str:
        return " + ".join(f"CASE WHEN instr(lower({text}),?)>0 THEN 1 ELSE 0 END" for _ in terms)

    with memory._db_lock:
        if terms:
            title_rank = rank("coalesce(n.name,'') || ' ' || t.session_id")
            rows = memory.db.execute(
                f"SELECT t.session_id,MAX(t.ts),COUNT(*),MAX({rank(public_text)}) "
                f"+ 2*MAX({title_rank}) AS relevance FROM turns t "
                "JOIN application_workspace w ON w.session_id=t.session_id "
                "LEFT JOIN session_names n ON n.session_id=t.session_id "
                "WHERE w.path=? AND t.role IN ('user','assistant') AND "
                "EXISTS(SELECT 1 FROM session_archive a WHERE a.session_id=t.session_id)=? "
                "GROUP BY t.session_id HAVING relevance>0 "
                "ORDER BY relevance DESC,MAX(t.ts) DESC LIMIT 100",
                (*terms, *terms, str(workspace.resolve()), int(archived)),
            ).fetchall()
            rows = [row[:3] for row in rows]
        else:
            rows = memory.db.execute(
                "SELECT t.session_id,MAX(t.ts),COUNT(*) FROM turns t "
                "JOIN application_workspace w ON w.session_id=t.session_id "
                "WHERE w.path=? AND t.role IN ('user','assistant') AND "
                "EXISTS(SELECT 1 FROM session_archive a WHERE a.session_id=t.session_id)=? "
                "GROUP BY t.session_id ORDER BY MAX(t.ts) DESC LIMIT 100",
                (str(workspace.resolve()), int(archived)),
            ).fetchall()
        items = []
        for identity, updated, count in rows:
            preview = memory.db.execute(
                "SELECT CASE WHEN json_valid(content) AND json_type(content)='text' "
                "THEN substr(json_extract(content,'$'),1,160) ELSE '' END FROM turns "
                "WHERE session_id=? AND role IN ('user','assistant') ORDER BY ts DESC,rowid DESC "
                "LIMIT 1", (identity,),
            ).fetchone()
            if terms:
                positions = ",".join(f"nullif(instr(lower({public_text}),?),0)" for _ in terms)
                match = memory.db.execute(
                    f"SELECT substr({public_text},max(1,coalesce({positions},1)-48),240) "
                    "FROM turns t WHERE t.session_id=? AND t.role IN ('user','assistant') "
                    f"AND ({rank(public_text)})>0 "
                    f"ORDER BY ({rank(public_text)}) DESC,t.ts DESC LIMIT 1",
                    (*terms, identity, *terms, *terms),
                ).fetchone()
                if match:
                    preview = match
            title = memory.db.execute(
                "SELECT substr(name,1,160) FROM session_names WHERE session_id=?", (identity,),
            ).fetchone()
            if title is None:
                title = memory.db.execute(
                    "SELECT CASE WHEN json_valid(content) AND json_type(content)='text' "
                    "THEN substr(json_extract(content,'$'),1,160) ELSE '' END FROM turns "
                    "WHERE session_id=? AND role='user' ORDER BY ts,rowid LIMIT 1", (identity,),
                ).fetchone()
            items.append({"session_id": identity, "updated_at": updated, "turns": count,
                          "title": " ".join(title[0].split()) if title else "Untitled session",
                          "preview": preview[0],
                          "archived": archived})
    return items
