"""Memory tiers.

memory.md  — durable facts, human-editable, injected into every system prompt.
sessions.db — episodic turns for `klaude sessions` and `klaude session-search`.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*(?!\.\.\.)([A-Za-z0-9_\-./+=]{8,})"
)
DIRECT_MEMORY_PATTERNS = [
    re.compile(r"(?is)\bremember that\s+(.+)"),
    re.compile(r"(?is)\bplease remember that\s+(.+)"),
    re.compile(r"(?is)\bremember\s+(.+)"),
    re.compile(r"(?is)\bdon't forget that\s+(.+)"),
    re.compile(r"(?is)\bdont forget that\s+(.+)"),
    re.compile(r"(?is)\bnote that\s+(.+)"),
]
BROAD_MEMORY_RE = re.compile(
    r"(?i)^(this|that|it|what i said|what we said|what i mentioned|this topic|everything)$"
)
AUTO_MEMORY_HINTS = (
    "i prefer ",
    "i'd rather ",
    "i would rather ",
    "from now on ",
    "for future ",
    "my goal is ",
    "my goals are ",
    "always ",
    "never ",
    "don't abbreviate ",
    "dont abbreviate ",
)
MEMORY_LINE_RE = re.compile(r"^\s*-\s+\[memory:(?P<id>[0-9a-f]{12})\]\s+(?P<fact>.+?)\s*$")
LEGACY_MEMORY_LINE_RE = re.compile(
    r"^\s*-\s+(?P<date>\d{4}-\d{2}-\d{2})\s+\[[^\]]+\]:\s+(?P<fact>.+?)\s*$"
)


def _clean_fact(text: str) -> str:
    text = " ".join(text.strip().split())
    return text.rstrip(" .")[:500]


def _normalize_fact(text: str) -> str:
    return _clean_fact(text).casefold()


def _memory_id(fact: str) -> str:
    return sha256(_normalize_fact(fact).encode("utf-8")).hexdigest()[:12]


def is_sensitive_memory(text: str) -> bool:
    return bool(SECRET_RE.search(text))


def explicit_memory_candidate(text: str) -> tuple[str, bool] | None:
    """Return (fact, needs_confirmation) for explicit remember-like requests."""
    if is_sensitive_memory(text):
        return None
    if re.match(r"(?is)^\s*(do|did|can|could|would|will)\s+you\s+remember\b", text):
        return None
    for pattern in DIRECT_MEMORY_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        fact = _clean_fact(match.group(1))
        if not fact:
            return None
        broad = bool(BROAD_MEMORY_RE.match(fact.lower())) or fact.lower().startswith(
            ("what i said", "what we said", "what i mentioned", "this topic")
        )
        return fact, broad or len(fact) < 8
    return None


def auto_memory_candidates(user_text: str) -> list[str]:
    """Conservative rule-based candidates from a user turn."""
    if is_sensitive_memory(user_text):
        return []

    explicit = explicit_memory_candidate(user_text)
    if explicit and not explicit[1]:
        return [explicit[0]]

    lowered = user_text.lower()
    if not any(hint in lowered for hint in AUTO_MEMORY_HINTS):
        return []

    fact = _clean_fact(user_text)
    if len(fact) < 12 or len(fact) > 500:
        return []
    return [fact]


def _decode_content(raw: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _as_text(content: object) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


@dataclass(frozen=True)
class MemoryEntry:
    id: str
    fact: str
    raw: str


@dataclass(frozen=True)
class ForgetResult:
    removed: int
    matches: list[MemoryEntry]
    reason: str = ""

    @property
    def ambiguous(self) -> bool:
        return self.removed == 0 and bool(self.matches)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self.removed == other
        return super().__eq__(other)


def _parse_memory_line(line: str) -> MemoryEntry | None:
    stripped = line.strip()
    if not stripped:
        return None
    match = MEMORY_LINE_RE.match(stripped)
    if match:
        fact = _clean_fact(match.group("fact"))
        return MemoryEntry(match.group("id"), fact, stripped)
    legacy = LEGACY_MEMORY_LINE_RE.match(stripped)
    if legacy:
        fact = _clean_fact(legacy.group("fact"))
        return MemoryEntry(_memory_id(fact), fact, stripped)
    if stripped.startswith("- "):
        fact = _clean_fact(stripped[2:])
    else:
        fact = _clean_fact(stripped)
    return MemoryEntry(_memory_id(fact), fact, stripped) if fact else None


class Memory:
    def __init__(self, memory_file: Path, sessions_db: Path):
        self.memory_file = memory_file
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        sessions_db.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(sessions_db)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                session_id TEXT, ts REAL, role TEXT, content TEXT
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )
        self.db.commit()

    # --- durable facts ---------------------------------------------------
    def facts(self) -> str:
        self._migrate_memory_file()
        if self.memory_file.exists():
            return self.memory_file.read_text().strip()
        return ""

    def list_facts(self) -> list[str]:
        return [entry.raw for entry in self._load_entries()]

    def _load_entries(self) -> list[MemoryEntry]:
        self._migrate_memory_file()
        if not self.memory_file.exists():
            return []
        entries = []
        for line in self.memory_file.read_text().splitlines():
            entry = _parse_memory_line(line)
            if entry:
                entries.append(entry)
        return entries

    def _migrate_memory_file(self) -> None:
        if not self.memory_file.exists():
            return
        raw_lines = self.memory_file.read_text().splitlines()
        migrated = []
        changed = False
        for line in raw_lines:
            entry = _parse_memory_line(line)
            if not entry:
                if line.strip():
                    changed = True
                continue
            formatted = f"- [memory:{entry.id}] {entry.fact}"
            migrated.append(formatted)
            changed = changed or formatted != line.strip()
        if changed:
            self.memory_file.write_text("\n".join(migrated) + ("\n" if migrated else ""))

    def remember(self, fact: str, source: str = "manual") -> bool:
        fact = _clean_fact(fact)
        if not fact or is_sensitive_memory(fact):
            return False
        normalized = _normalize_fact(fact)
        if any(_normalize_fact(entry.fact) == normalized for entry in self._load_entries()):
            return False
        with open(self.memory_file, "a", encoding="utf-8") as f:
            f.write(f"- [memory:{_memory_id(fact)}] {fact}\n")
        return True

    def forget(self, query: str) -> ForgetResult:
        query = query.strip()
        if not query or not self.memory_file.exists():
            return ForgetResult(0, [], "empty query")
        entries = self._load_entries()
        normalized = _normalize_fact(query)
        query_id = query.removeprefix("memory:").strip().lower()

        target_index = next((i for i, entry in enumerate(entries) if entry.id == query_id), None)
        if target_index is None:
            exact_indexes = [
                i for i, entry in enumerate(entries)
                if _normalize_fact(entry.fact) == normalized
            ]
            if len(exact_indexes) == 1:
                target_index = exact_indexes[0]
            elif len(exact_indexes) > 1:
                matches = [entries[i] for i in exact_indexes]
                return ForgetResult(0, matches, "multiple exact matches")

        if target_index is None:
            matches = [
                entry for entry in entries
                if normalized and normalized in _normalize_fact(entry.fact)
            ]
            return ForgetResult(0, matches, "substring match requires an exact memory ID or text")

        kept = [entry.raw for i, entry in enumerate(entries) if i != target_index]
        self.memory_file.write_text("\n".join(kept) + ("\n" if kept else ""))
        return ForgetResult(1, [entries[target_index]], "removed")

    def search_facts(self, query: str) -> list[MemoryEntry]:
        normalized = _normalize_fact(query)
        if not normalized:
            return []
        return [
            entry for entry in self._load_entries()
            if normalized in _normalize_fact(entry.fact) or normalized == entry.id
        ]

    # --- memory settings ---------------------------------------------------
    def auto_memory_enabled(self) -> bool:
        row = self.db.execute(
            "SELECT value FROM settings WHERE key='auto_memory_enabled'"
        ).fetchone()
        if not row:
            return True
        return row[0] == "1"

    def set_auto_memory(self, enabled: bool) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            ("auto_memory_enabled", "1" if enabled else "0"),
        )
        self.db.commit()

    def auto_remember_turn(self, user_text: str) -> list[str]:
        if not self.auto_memory_enabled():
            return []
        saved = []
        for fact in auto_memory_candidates(user_text):
            if self.remember(fact, source="auto"):
                saved.append(fact)
        return saved

    # --- episodic --------------------------------------------------------
    def log_turn(self, session_id: str, role: str, content: object) -> None:
        self.db.execute(
            "INSERT INTO turns VALUES (?,?,?,?)",
            (session_id, time.time(), role, json.dumps(content, ensure_ascii=False)),
        )
        self.db.commit()

    def last_session_id(self) -> str | None:
        row = self.db.execute("SELECT session_id FROM turns ORDER BY ts DESC LIMIT 1").fetchone()
        return row[0] if row else None

    def load_session(self, session_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM turns WHERE session_id=? ORDER BY ts", (session_id,)
        ).fetchall()
        out = []
        for role, content in rows:
            try:
                out.append({"role": role, "content": json.loads(content)})
            except json.JSONDecodeError:
                out.append({"role": role, "content": content})
        return out

    def session_tail(self, session_id: str, limit: int = 8) -> list[dict]:
        rows = self.db.execute(
            "SELECT role, content FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        out = []
        for role, content in reversed(rows):
            out.append({"role": role, "content": _decode_content(content)})
        return out

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        rows = self.db.execute(
            "SELECT session_id, MAX(ts), COUNT(*) FROM turns "
            "GROUP BY session_id ORDER BY MAX(ts) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        sessions = []
        for session_id, ts, count in rows:
            preview_row = self.db.execute(
                "SELECT role, content FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            preview = ""
            if preview_row:
                preview = _as_text(_decode_content(preview_row[1]))[:160].replace("\n", " ")
            sessions.append(
                {
                    "session_id": session_id,
                    "ts": ts,
                    "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                    "turns": count,
                    "preview": preview,
                }
            )
        return sessions

    def search_sessions(self, query: str, limit: int = 8) -> list[dict]:
        terms = [t.lower() for t in re.findall(r"[\w.-]+", query) if len(t) > 1]
        if not terms:
            return []
        where = " AND ".join("lower(content) LIKE ?" for _ in terms)
        params = [f"%{term}%" for term in terms]
        rows = self.db.execute(
            f"SELECT session_id, ts, role, content FROM turns WHERE {where} "
            "ORDER BY ts DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        hits = []
        for session_id, ts, role, content in rows:
            text = _as_text(_decode_content(content))
            hits.append(
                {
                    "session_id": session_id,
                    "ts": ts,
                    "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                    "role": role,
                    "content": text[:1000],
                }
            )
        return hits
