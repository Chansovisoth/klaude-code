"""Embedded session reads and actions shared by terminal clients."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from klaude_core.memory import Memory

from .activity_text import completed_activity_text, subagent_activity_text


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    updated_at: float
    date: str
    turns: int
    preview: str
    title: str
    active: bool


@dataclass(frozen=True)
class SessionMatch:
    session_id: str
    timestamp: float
    date: str
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class PublicSessionMessage:
    id: str
    role: Literal["user", "assistant"]
    content: str
    created_at: float
    attachments: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class SessionArtifactReferences:
    identities: tuple[str, ...]
    limited: bool


@dataclass(frozen=True)
class SessionArchiveChange:
    session_id: str
    action: Literal["archive", "restore", "delete"]

    @classmethod
    def from_values(cls, session_id: str, action: str) -> SessionArchiveChange:
        if action not in {"archive", "restore", "delete"}:
            raise ValueError("Invalid session archive action")
        return cls(session_id, cast(Literal["archive", "restore", "delete"], action))


@dataclass(frozen=True)
class SessionArchiveReceipt:
    session_id: str
    action: Literal["archive", "restore", "delete"]
    state: Literal["archived", "active", "deleted"]


@dataclass(frozen=True)
class SessionRenameChange:
    session_id: str
    name: str


@dataclass(frozen=True)
class SessionForkChange:
    source_id: str
    target_id: str


@dataclass(frozen=True)
class SessionMessageForkChange:
    source_id: str
    target_id: str
    message_row_id: int
    retry: bool = False


@dataclass(frozen=True)
class SessionDeleteChange:
    session_id: str
    expected_total_turns: int | None = None


@dataclass(frozen=True)
class SessionDeleteReceipt:
    session_id: str
    removed_turns: int


@dataclass(frozen=True)
class SessionsClearReceipt:
    removed_sessions: int
    removed_turns: int


@dataclass(frozen=True)
class SessionsClearChange:
    expected_sessions: int
    expected_turns: int


class SessionDirectory:
    """Project bounded public records and reuse Memory's session lifecycle guards.

    The caller owns identity, review, and durable request admission; these methods
    are not an independently authorized browser mutation API.
    """

    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    @staticmethod
    def _limit(value: int) -> int:
        if type(value) is not int or not 1 <= value <= 100:
            raise ValueError("session page size must be between 1 and 100")
        return value

    def recent(self, limit: int = 10) -> tuple[SessionSummary, ...]:
        rows = self.memory.recent_sessions(self._limit(limit))
        return tuple(SessionSummary(
            session_id=str(row["session_id"]), updated_at=float(row["ts"]),
            date=str(row["date"]), turns=int(row["turns"]),
            preview=str(row["preview"])[:160], title=str(row["title"])[:160],
            active=bool(row["active"]),
        ) for row in rows)

    def search(self, query: str, limit: int = 8) -> tuple[SessionMatch, ...]:
        if not isinstance(query, str) or len(query) > 500:
            raise ValueError("session search query must be at most 500 characters")
        rows = self.memory.search_sessions(query, self._limit(limit))
        return tuple(SessionMatch(
            session_id=str(row["session_id"]), timestamp=float(row["ts"]),
            date=str(row["date"]), role=row["role"], content=str(row["content"])[:1000],
        ) for row in rows if row["role"] in ("user", "assistant"))

    def public_message(self, session_id: str, row_id: int) -> PublicSessionMessage | None:
        """Read one exact public dialogue row, including outside recent history."""
        if type(row_id) is not int or not 0 < row_id <= 9_223_372_036_854_775_807:
            raise ValueError("Invalid message ID")
        with self.memory._db_lock:
            row = self.memory.db.execute(
                "SELECT role,substr(json_extract(content,'$'),1,16000),ts,attachments FROM turns "
                "WHERE session_id=? AND rowid=? AND role IN ('user','assistant') "
                "AND json_type(content)='text'",
                (session_id, row_id),
            ).fetchone()
        if row is None:
            return None
        return PublicSessionMessage(
            id=f"stored:{row_id}", role=cast(Literal["user", "assistant"], row[0]),
            content=str(row[1]), created_at=float(row[2]),
            attachments=tuple(json.loads(row[3])) if row[0] == "user" and row[3] else (),
        )

    def artifact_references(self, session_id: str) -> SessionArtifactReferences:
        """Bounded original Library IDs from public attachment descriptors only."""
        with self.memory._db_lock:
            rows = self.memory.db.execute(
                "SELECT attachments FROM turns WHERE session_id=? AND role='user' "
                "AND attachments IS NOT NULL AND attachments NOT IN ('','[]') "
                "ORDER BY rowid DESC LIMIT 501", (session_id,),
            ).fetchall()
        identities: set[str] = set()
        for (raw,) in rows[:500]:
            for item in json.loads(raw or "[]")[:4]:
                identity = item.get("artifact_id") if isinstance(item, dict) else None
                if (isinstance(identity, str)
                        and re.fullmatch(r"(?:document|media|research):[a-f0-9]{32}", identity)):
                    identities.add(identity)
                if len(identities) >= 508:
                    return SessionArtifactReferences(tuple(sorted(identities)), True)
        return SessionArtifactReferences(tuple(sorted(identities)), len(rows) > 500)

    def attachment_preview(self, session_id: str, row_id: int, index: int) -> bytes:
        """Read only the small, decoded thumbnail; never load private model input."""
        if (type(row_id) is not int or not 0 < row_id <= 9_223_372_036_854_775_807
                or type(index) is not int or not 0 <= index < 4):
            raise ValueError("Invalid attachment")
        with self.memory._db_lock:
            row = self.memory.db.execute(
                "SELECT substr(json_extract(attachment_previews,?),1,90000) FROM turns "
                "WHERE session_id=? AND rowid=? AND role='user'",
                (f"$[{index}]", session_id, row_id),
            ).fetchone()
        if row is None or not row[0]:
            raise ValueError("Preview unavailable")
        data = base64.b64decode(row[0], validate=True)
        if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) > 65536:
            raise ValueError("Preview unavailable")
        return data

    def attachment_content(
        self, session_id: str, row_id: int, index: int,
    ) -> tuple[dict[str, Any], bytes]:
        """Read one captured original, independently of private model input.

        Originals share the dialogue row's fork/deletion lifetime and the input's
        32 MiB bound. Public snapshots/export never select this private column.
        """
        if (type(row_id) is not int or not 0 < row_id <= 9_223_372_036_854_775_807
                or type(index) is not int or not 0 <= index < 4):
            raise ValueError("Invalid attachment")
        message = self.public_message(session_id, row_id)
        if message is None or message.role != "user" or index >= len(message.attachments):
            raise ValueError("Attachment unavailable")
        maximum = 32 * 1024 * 1024
        encoded_maximum = (maximum + 2) // 3 * 4 + 1024
        with self.memory._db_lock:
            size = self.memory.db.execute(
                "SELECT length(attachment_contents) FROM turns "
                "WHERE session_id=? AND rowid=? AND role='user'", (session_id, row_id),
            ).fetchone()
            if size is None:
                raise ValueError("Attachment unavailable")
            if not size[0]:
                raise FileNotFoundError(
                    "Original attachment was not retained in this older message"
                )
            if size[0] > encoded_maximum:
                raise ValueError("Attachment exceeds its storage bound")
            row = self.memory.db.execute(
                "SELECT substr(json_extract(attachment_contents,?),1,?) FROM turns "
                "WHERE session_id=? AND rowid=? AND role='user'",
                (f"$[{index}]", encoded_maximum + 1, session_id, row_id),
            ).fetchone()
        if row is None or not row[0]:
            raise ValueError("Attachment unavailable")
        record = json.loads(row[0])
        if (not isinstance(record, dict) or set(record) != {"data", "sha256"}
                or not isinstance(record["data"], str)
                or not isinstance(record["sha256"], str)):
            raise ValueError("Invalid stored attachment")
        data = base64.b64decode(record["data"], validate=True)
        descriptor = message.attachments[index]
        if (not data or len(data) > maximum or len(data) != descriptor.get("size")
                or hashlib.sha256(data).hexdigest() != record["sha256"]):
            raise ValueError("Attachment checksum failed")
        return dict(descriptor), data

    def change_archive(self, change: SessionArchiveChange) -> SessionArchiveReceipt:
        """Apply a reviewed archive action through Memory's transactional lease checks."""
        if (
            not isinstance(change, SessionArchiveChange)
            or not isinstance(change.session_id, str)
            or change.action not in {"archive", "restore", "delete"}
        ):
            raise ValueError("Invalid session archive action")
        self.memory.change_session_archive(change.session_id, change.action)
        state: Literal["archived", "active", "deleted"] = (
            "archived" if change.action == "archive" else
            "active" if change.action == "restore" else "deleted"
        )
        return SessionArchiveReceipt(change.session_id, change.action, state)

    def rename(self, change: SessionRenameChange) -> str:
        """Apply the existing manual-title validation and return the saved title."""
        self.memory.rename_session(change.session_id, change.name)
        return " ".join(change.name.split())

    def fork(self, change: SessionForkChange) -> str:
        """Copy an idle session through Memory's transactional runtime projection."""
        self.memory.fork_session(change.source_id, change.target_id)
        return change.target_id

    def fork_message(self, change: SessionMessageForkChange) -> str | None:
        """Branch at an exact reply, or return its original prompt for retry."""
        return self.memory.fork_session(
            change.source_id, change.target_id, through_row_id=change.message_row_id,
            retry=change.retry,
        )

    def delete(self, change: SessionDeleteChange) -> SessionDeleteReceipt:
        """Delete after caller-owned review using Memory's unresolved-work guard."""
        removed = self.memory.delete_session(
            change.session_id, expected_total_turns=change.expected_total_turns
        )
        return SessionDeleteReceipt(change.session_id, removed)

    def clear(self, change: SessionsClearChange | None = None) -> SessionsClearReceipt:
        """Clear after caller-owned review using Memory's all-session work guard."""
        if change is not None and (
            type(change.expected_sessions) is not int
            or type(change.expected_turns) is not int
        ):
            raise ValueError("Reviewed session counts are required")
        counts = self.memory.clear_sessions(
            expected_counts=(change.expected_sessions, change.expected_turns)
            if change is not None else None
        )
        return SessionsClearReceipt(counts["sessions"], counts["turns"])

    def markdown_chunks(self, session_id: str) -> Iterator[str]:
        """Yield the public conversation Markdown; never read model_content."""
        title = self.memory.session_title(session_id)
        yield f"# {title}\n\nSession: {session_id}\n"
        for turn in self.memory.public_session_records(session_id):
            content = turn.get("content", "")
            if turn.get("role") == "system" and isinstance(content, dict):
                if content.get("event") == "edit_summary":
                    yield "\n```text\n" + str(content.get("text", "")) + "\n```\n"
                if content.get("event") == "activity_update":
                    activity = completed_activity_text(
                        content.get("label"), content.get("detail"),
                        content.get("elapsed_seconds"),
                    )
                    if activity:
                        timestamp = datetime.fromtimestamp(turn["ts"]).astimezone().isoformat()
                        yield f"\n> {activity} · {timestamp}\n"
                if content.get("event") == "input_request":
                    yield f"\n> [INPUT · KLAUDE] {content.get('question', '')}\n"
                if content.get("event") == "input_answer" and content.get("answer") is not None:
                    yield f"\n> [INPUT · YOU] {content.get('answer', '')}\n"
                if content.get("event") == "subagent_activity":
                    activity = subagent_activity_text(content)
                    if activity:
                        yield f"\n> {activity}\n"
                continue
            if turn.get("role") not in {"user", "assistant"}:
                continue
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            timestamp = datetime.fromtimestamp(turn["ts"]).astimezone().isoformat()
            yield f"\n## {turn['role']} · {timestamp}\n\n{content}\n"
