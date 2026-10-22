"""Bounded inspection of existing public events; private tool bodies stay private."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

ERROR_TYPES = frozenset(
    {
        "ValueError",
        "TypeError",
        "KeyError",
        "OSError",
        "PermissionError",
        "FileNotFoundError",
        "RuntimeError",
        "TimeoutError",
        "ConnectionError",
        "InterruptedError",
        "GitCommandError",
    }
)


def tool_inspection(agent: Any, tool: str, arguments: dict, metadata: dict) -> dict[str, Any]:
    """Publish only verified local paths, numeric edit counts and error classes."""
    result: dict[str, Any] = {}
    workspace: Any = getattr(agent, "workspace", None)
    definition = getattr(agent, "tools", {}).get(tool)
    function = getattr(definition, "fn", None)
    # An external tool named like a built-in must not forge local edit evidence.
    owner = getattr(function, "__self__", None)
    if workspace is not None and (
        owner is workspace or getattr(owner, "workspace", None) is workspace
    ):
        assert workspace is not None
        edit = metadata.get("edit")
        path = arguments.get("path") or (edit.get("path") if isinstance(edit, dict) else None)
        if isinstance(path, str) and len(path) <= 1024:
            try:
                target = workspace._jail(path)
                relative = str(target.relative_to(workspace.root))
                if not workspace._is_sensitive_path(target) and all(
                    c.isprintable() for c in relative
                ):
                    result["path"] = relative
            except (OSError, ValueError, PermissionError):
                pass
        if (
            owner is workspace
            and tool == "write_file"
            and metadata.get("file_operation") == "create"
        ):
            result["change_type"] = "added"
        if (
            owner is workspace
            and tool in {"write_file", "edit_file"}
            and "path" in result
            and isinstance(edit, dict)
            and edit.get("changed") is True
            and metadata.get("executed") is True
            and metadata.get("status") != "failed"
        ):
            result["changed"] = True
            for key in ("added", "removed"):
                if type(edit.get(key)) is int and 0 <= edit[key] <= 10_000_000:
                    result[key] = edit[key]
    error = metadata.get("error_type")
    if isinstance(error, str) and error in ERROR_TYPES:
        result["error_type"] = error
    return result


def clean_inspection(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    path = value.get("path")
    if (
        isinstance(path, str)
        and len(path) <= 1024
        and not path.startswith(("/", "\\"))
        and ".." not in path.split("/")
        and all(c.isprintable() for c in path)
    ):
        result["path"] = path
    if value.get("changed") is True and "path" in result:
        result["changed"] = True
        for key in ("added", "removed"):
            if type(value.get(key)) is int and 0 <= value[key] <= 10_000_000:
                result[key] = value[key]
    if (
        isinstance(value.get("change_type"), str)
        and value["change_type"] in {"added", "modified", "deleted"}
        and "path" in result
    ):
        result["change_type"] = value["change_type"]
    error = value.get("error_type")
    if isinstance(error, str) and error in ERROR_TYPES:
        result["error_type"] = error
    return result


def read_inspector(db: sqlite3.Connection, session: str, turn: str) -> dict[str, Any]:
    """Called inside the same transaction as dialogue, activity and SSE watermark."""
    kinds = (
        "turn.accepted",
        "turn.started",
        "turn.completed",
        "turn.failed",
        "turn.partial",
        "turn.cancelled",
        "turn.interrupted",
        "tool.requested",
        "tool.started",
        "tool.finished",
        "approval.required",
        "approval.resolved",
        "user_input.required",
        "user_input.resolved",
    )
    rows = db.execute(
        "SELECT id,turn_id,ts,payload FROM session_events WHERE session_id=? "
        "AND kind='application.public.v1' AND json_extract(payload,'$.kind') IN ("
        + ",".join("?" for _ in kinds)
        + ") ORDER BY id DESC LIMIT 321",
        (session, *kinds),
    ).fetchall()
    events = []
    changes: dict[str, dict] = {}
    for identity, execution, timestamp, raw in reversed(rows[:320]):
        data = json.loads(raw)
        details = clean_inspection(data.get("inspection"))
        event = {
            "id": str(identity),
            "turn_id": execution,
            "timestamp": timestamp,
            "kind": data["kind"],
            "inspection": details,
        }
        for key in ("tool", "execution_id", "interaction_id", "status"):
            event[key] = str(data.get(key) or "")[:128]
        if type(data.get("executed")) is bool:
            event["executed"] = data["executed"]
        events.append(event)
        if (
            event["kind"] == "tool.finished"
            and data.get("executed") is True
            and event["status"] == "succeeded"
            and details.get("changed") is True
        ):
            status = changes.get(details["path"], {}).get("status") or details.get(
                "change_type", "modified"
            )
            changes[details["path"]] = {**details, "status": status, "turn_id": execution}
    timing = db.execute(
        "SELECT accepted_at,completed_at FROM application_turns WHERE session_id=? AND turn_id=?",
        (session, turn),
    ).fetchone()
    count = db.execute(
        "SELECT count(DISTINCT json_extract(payload,'$.execution_id')) FROM session_events "
        "WHERE session_id=? AND turn_id=? AND kind='application.public.v1' "
        "AND json_extract(payload,'$.kind')='tool.requested' "
        "AND coalesce(json_extract(payload,'$.execution_id'),'')<>''",
        (session, turn),
    ).fetchone()[0]
    complete_history = not turn or bool(
        db.execute(
            "SELECT 1 FROM session_events WHERE session_id=? AND turn_id=? "
            "AND kind='application.public.v1' AND json_extract(payload,'$.kind')='turn.accepted' "
            "LIMIT 1",
            (session, turn),
        ).fetchone()
    )
    name = db.execute("SELECT name FROM session_names WHERE session_id=?", (session,)).fetchone()
    return {
        "session_id": session,
        "turn_id": turn,
        "events": events,
        "file_changes": list(changes.values()),
        "limited": len(rows) > 320,
        "tool_count": count if complete_history else None,
        "history_missing": not complete_history,
        "started_at": timing[0] if timing else None,
        "completed_at": timing[1] if timing and timing[1] else None,
        "name": str(name[0])[:160] if name else "",
    }
