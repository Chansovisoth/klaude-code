"""Memory tiers.

memory.md  — durable facts, human-editable, injected into every system prompt.
sessions.db — episodic turns for `klaude sessions` and `klaude session-search`.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret)\b\s*"
    r"(?::|=|\bis\b|\bwas\b)\s*[\"']?(?!\.\.\.)"
    r"([A-Za-z0-9_\-./+=]{8,})"
)
KNOWN_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{12,}|"
    r"AIza[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9._~+/-]{12,})\b"
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
    return bool(SECRET_RE.search(text) or KNOWN_SECRET_VALUE_RE.search(text))


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
        try:
            descriptor = os.open(
                sessions_db,
                os.O_CREAT | os.O_EXCL | os.O_RDWR,
                0o600,
            )
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        # Interactive TUI model turns run on a background worker so the input
        # remains usable. Turns are serialized, but the connection crosses the
        # UI/worker boundary.
        self.db = sqlite3.connect(sessions_db, check_same_thread=False)
        self._db_lock = threading.RLock()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                session_id TEXT, ts REAL, role TEXT, content TEXT, model_content TEXT
            )"""
        )
        turn_columns = {row[1] for row in self.db.execute("PRAGMA table_info(turns)").fetchall()}
        if "model_content" not in turn_columns:
            self.db.execute("ALTER TABLE turns ADD COLUMN model_content TEXT")
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"""
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS session_names "
            "(session_id TEXT PRIMARY KEY, name TEXT NOT NULL)"
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS session_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL DEFAULT '',
                client_id TEXT NOT NULL,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                payload TEXT NOT NULL
            )"""
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS session_events_session_id_id "
            "ON session_events(session_id, id)"
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS session_live (
                session_id TEXT PRIMARY KEY,
                revision INTEGER NOT NULL DEFAULT 0,
                owner_client_id TEXT NOT NULL DEFAULT '',
                owner_lease_until REAL NOT NULL DEFAULT 0,
                turn_id TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT 'idle',
                draft_client_id TEXT NOT NULL DEFAULT '',
                draft TEXT NOT NULL DEFAULT '',
                activity TEXT NOT NULL DEFAULT 'ready',
                partial TEXT NOT NULL DEFAULT '',
                queue_json TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL
            )"""
        )
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS session_clients (
                session_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                draft TEXT NOT NULL DEFAULT '',
                queue_json TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL,
                PRIMARY KEY (session_id, client_id)
            )"""
        )
        self.db.commit()
        try:
            sessions_db.chmod(0o600)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(sessions_db) + suffix)
                if sidecar.exists():
                    sidecar.chmod(0o600)
            if self.memory_file.exists():
                self.memory_file.chmod(0o600)
        except OSError:
            pass
        # Normalize legacy memory lines once at startup while holding the same
        # process-wide lock used by mutations. Read paths must stay read-only:
        # two resumed clients may otherwise race while merely loading facts.
        with self._memory_mutation_lock():
            self._migrate_memory_file()

    @contextmanager
    def _memory_mutation_lock(self):
        """Serialize durable-memory edits across resumed client processes."""
        lock_path = self.memory_file.with_suffix(self.memory_file.suffix + ".lock")
        with lock_path.open("a+") as lock:
            try:
                lock_path.chmod(0o600)
            except OSError:
                pass
            if os.name == "posix":
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if os.name == "posix":
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _write_memory_file(self, text: str) -> None:
        temporary = self.memory_file.with_name(
            f".{self.memory_file.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            temporary.write_text(text, encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, self.memory_file)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    # --- durable facts ---------------------------------------------------
    def facts(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text().strip()
        return ""

    def list_facts(self) -> list[str]:
        return [entry.raw for entry in self._load_entries()]

    def _load_entries(self) -> list[MemoryEntry]:
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
            self._write_memory_file("\n".join(migrated) + ("\n" if migrated else ""))

    def remember(self, fact: str, source: str = "manual") -> bool:
        fact = _clean_fact(fact)
        if not fact or is_sensitive_memory(fact):
            return False
        with self._db_lock, self._memory_mutation_lock():
            normalized = _normalize_fact(fact)
            entries = self._load_entries()
            if any(_normalize_fact(entry.fact) == normalized for entry in entries):
                return False
            lines = [entry.raw for entry in entries]
            lines.append(f"- [memory:{_memory_id(fact)}] {fact}")
            self._write_memory_file("\n".join(lines) + "\n")
        return True

    def forget(self, query: str) -> ForgetResult:
        query = query.strip()
        if not query or not self.memory_file.exists():
            return ForgetResult(0, [], "empty query")
        with self._db_lock, self._memory_mutation_lock():
            entries = self._load_entries()
            normalized = _normalize_fact(query)
            query_id = query.removeprefix("memory:").strip().lower()

            target_index = next(
                (i for i, entry in enumerate(entries) if entry.id == query_id), None
            )
            if target_index is None:
                exact_indexes = [
                    i
                    for i, entry in enumerate(entries)
                    if _normalize_fact(entry.fact) == normalized
                ]
                if len(exact_indexes) == 1:
                    target_index = exact_indexes[0]
                elif len(exact_indexes) > 1:
                    matches = [entries[i] for i in exact_indexes]
                    return ForgetResult(0, matches, "multiple exact matches")

            if target_index is None:
                matches = [
                    entry
                    for entry in entries
                    if normalized and normalized in _normalize_fact(entry.fact)
                ]
                return ForgetResult(
                    0,
                    matches,
                    "substring match requires an exact memory ID or text",
                )

            kept = [entry.raw for i, entry in enumerate(entries) if i != target_index]
            self._write_memory_file("\n".join(kept) + ("\n" if kept else ""))
            return ForgetResult(1, [entries[target_index]], "removed")

    def search_facts(self, query: str) -> list[MemoryEntry]:
        normalized = _normalize_fact(query)
        if not normalized:
            return []
        return [
            entry
            for entry in self._load_entries()
            if normalized in _normalize_fact(entry.fact) or normalized == entry.id
        ]

    # --- memory settings ---------------------------------------------------
    def auto_memory_enabled(self) -> bool:
        with self._db_lock:
            row = self.db.execute(
                "SELECT value FROM settings WHERE key='auto_memory_enabled'"
            ).fetchone()
        if not row:
            return True
        return row[0] == "1"

    def set_auto_memory(self, enabled: bool) -> None:
        with self._db_lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                ("auto_memory_enabled", "1" if enabled else "0"),
            )

    def auto_remember_turn(self, user_text: str) -> list[str]:
        if not self.auto_memory_enabled():
            return []
        saved = []
        for fact in auto_memory_candidates(user_text):
            if self.remember(fact, source="auto"):
                saved.append(fact)
        return saved

    # --- episodic --------------------------------------------------------
    def log_turn(
        self,
        session_id: str,
        role: str,
        content: object,
        *,
        model_content: object | None = None,
    ) -> None:
        with self._db_lock:
            self.db.execute(
                "INSERT INTO turns "
                "(session_id, ts, role, content, model_content) VALUES (?,?,?,?,?)",
                (
                    session_id,
                    time.time(),
                    role,
                    json.dumps(content, ensure_ascii=False),
                    (
                        json.dumps(model_content, ensure_ascii=False)
                        if model_content is not None
                        else None
                    ),
                ),
            )
            self.db.commit()

    def publish_session_event(
        self,
        session_id: str,
        client_id: str,
        kind: str,
        payload: object,
        *,
        turn_id: str = "",
    ) -> int:
        """Append one ordered cross-process session event and return its cursor."""
        encoded = json.dumps(payload, ensure_ascii=False)
        with self._db_lock, self.db:
            cursor = self.db.execute(
                "INSERT INTO session_events "
                "(session_id, turn_id, client_id, ts, kind, payload) "
                "VALUES (?,?,?,?,?,?)",
                (session_id, turn_id, client_id, time.time(), kind, encoded),
            )
            text = payload.get("text", "") if isinstance(payload, dict) else ""
            if kind == "assistant_delta" and isinstance(text, str):
                self.db.execute(
                    "UPDATE session_live SET revision=revision+1, partial=partial || ?, "
                    "activity='drafting response', updated_at=? "
                    "WHERE session_id=? AND owner_client_id=? AND turn_id=?",
                    (text, time.time(), session_id, client_id, turn_id),
                )
            elif kind == "activity" and isinstance(text, str):
                self.db.execute(
                    "UPDATE session_live SET revision=revision+1, activity=?, updated_at=? "
                    "WHERE session_id=? AND owner_client_id=? AND turn_id=?",
                    (text[:160], time.time(), session_id, client_id, turn_id),
                )
            return int(cursor.lastrowid or 0)

    def start_session_turn(
        self,
        session_id: str,
        client_id: str,
        turn_id: str,
        visible_content: object,
        *,
        model_content: object | None = None,
    ) -> int:
        """Save a user turn and announce it as one atomic database change."""
        payload = json.dumps({"text": _as_text(visible_content)}, ensure_ascii=False)
        with self._db_lock, self.db:
            self.db.execute(
                "INSERT INTO turns "
                "(session_id, ts, role, content, model_content) VALUES (?,?,?,?,?)",
                (
                    session_id,
                    time.time(),
                    "user",
                    json.dumps(visible_content, ensure_ascii=False),
                    (
                        json.dumps(model_content, ensure_ascii=False)
                        if model_content is not None
                        else None
                    ),
                ),
            )
            cursor = self.db.execute(
                "INSERT INTO session_events "
                "(session_id, turn_id, client_id, ts, kind, payload) "
                "VALUES (?,?,?,?,?,?)",
                (session_id, turn_id, client_id, time.time(), "user_started", payload),
            )
        return int(cursor.lastrowid or 0)

    def session_events_since(
        self,
        session_id: str,
        after_id: int,
        *,
        limit: int = 500,
    ) -> list[dict]:
        bounded_limit = max(1, min(2_000, int(limit)))
        with self._db_lock:
            rows = self.db.execute(
                "SELECT id, turn_id, client_id, ts, kind, payload "
                "FROM session_events WHERE session_id=? AND id>? "
                "ORDER BY id LIMIT ?",
                (session_id, max(0, int(after_id)), bounded_limit),
            ).fetchall()
        return [
            {
                "id": event_id,
                "turn_id": turn_id,
                "client_id": client_id,
                "ts": ts,
                "kind": kind,
                "payload": _decode_content(payload),
            }
            for event_id, turn_id, client_id, ts, kind, payload in rows
        ]

    def latest_session_event_id(self, session_id: str) -> int:
        with self._db_lock:
            row = self.db.execute(
                "SELECT COALESCE(MAX(id), 0) FROM session_events WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return int(row[0] or 0) if row else 0

    def prune_session_events(
        self,
        session_id: str,
        *,
        retention_seconds: float = 7 * 24 * 60 * 60,
        max_events: int = 100_000,
    ) -> int:
        """Bound ephemeral replay data; completed turns remain canonical in turns."""
        cutoff = time.time() - max(60.0, float(retention_seconds))
        bounded_max = max(1_000, int(max_events))
        with self._db_lock, self.db:
            old = self.db.execute(
                "DELETE FROM session_events WHERE session_id=? AND ts<?",
                (session_id, cutoff),
            ).rowcount
            excess = self.db.execute(
                "SELECT MAX(0, COUNT(*) - ?) FROM session_events WHERE session_id=?",
                (bounded_max, session_id),
            ).fetchone()
            excess_count = int(excess[0] or 0) if excess else 0
            capped = 0
            if excess_count:
                capped = self.db.execute(
                    "DELETE FROM session_events WHERE id IN ("
                    "SELECT id FROM session_events WHERE session_id=? ORDER BY id LIMIT ?"
                    ")",
                    (session_id, excess_count),
                ).rowcount
            self.db.execute(
                "DELETE FROM session_clients WHERE session_id=? AND updated_at<?",
                (session_id, cutoff),
            )
        return max(0, old) + max(0, capped)

    def session_snapshot(self, session_id: str) -> dict:
        """Read saved turns, live state, and event cursor from one snapshot."""
        with self._db_lock:
            self.db.execute("BEGIN")
            try:
                turns = self.load_session(session_id, timestamps=True)
                live = self.session_live_state(session_id)
                clients = self.session_client_states(session_id)
                cursor = self.latest_session_event_id(session_id)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        return {
            "turns": turns,
            "live": live,
            "clients": clients,
            "event_cursor": cursor,
        }

    def update_session_client(
        self,
        session_id: str,
        client_id: str,
        *,
        draft: str,
        queue: list[str],
    ) -> None:
        """Publish one client's composer without overwriting other clients."""
        with self._db_lock, self.db:
            self.db.execute(
                "INSERT INTO session_clients "
                "(session_id, client_id, draft, queue_json, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(session_id, client_id) DO UPDATE SET "
                "draft=excluded.draft, queue_json=excluded.queue_json, "
                "updated_at=excluded.updated_at",
                (
                    session_id,
                    client_id,
                    draft,
                    json.dumps(queue, ensure_ascii=False),
                    time.time(),
                ),
            )

    def session_client_states(self, session_id: str) -> list[dict]:
        with self._db_lock:
            rows = self.db.execute(
                "SELECT client_id, draft, queue_json, updated_at FROM session_clients "
                "WHERE session_id=? ORDER BY updated_at DESC, client_id",
                (session_id,),
            ).fetchall()
        return [
            {
                "client_id": client_id,
                "draft": draft,
                "queue": (
                    decoded if isinstance((decoded := _decode_content(queue_json)), list) else []
                ),
                "updated_at": float(updated_at),
            }
            for client_id, draft, queue_json, updated_at in rows
        ]

    def update_session_live(self, session_id: str, **updates: object) -> dict:
        """Atomically patch ephemeral session state and advance its revision."""
        allowed = {
            "owner_client_id",
            "owner_lease_until",
            "turn_id",
            "state",
            "draft_client_id",
            "draft",
            "activity",
            "partial",
            "queue_json",
        }
        unknown = set(updates) - allowed
        if unknown:
            raise ValueError(f"unknown live-session fields: {', '.join(sorted(unknown))}")
        normalized = dict(updates)
        if "queue_json" in normalized and not isinstance(normalized["queue_json"], str):
            normalized["queue_json"] = json.dumps(normalized["queue_json"], ensure_ascii=False)
        with self._db_lock, self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO session_live(session_id, updated_at) VALUES (?,?)",
                (session_id, time.time()),
            )
            assignments = [f"{name}=?" for name in normalized]
            values = list(normalized.values())
            assignments.extend(["revision=revision+1", "updated_at=?"])
            values.extend([time.time(), session_id])
            self.db.execute(
                f"UPDATE session_live SET {', '.join(assignments)} WHERE session_id=?",
                values,
            )
        return self.session_live_state(session_id)

    def session_live_state(self, session_id: str) -> dict:
        with self._db_lock:
            row = self.db.execute(
                "SELECT revision, owner_client_id, owner_lease_until, turn_id, state, "
                "draft_client_id, draft, activity, partial, queue_json, updated_at "
                "FROM session_live WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if not row:
            return {
                "session_id": session_id,
                "revision": 0,
                "owner_client_id": "",
                "owner_lease_until": 0.0,
                "turn_id": "",
                "state": "idle",
                "draft_client_id": "",
                "draft": "",
                "activity": "ready",
                "partial": "",
                "queue": [],
                "updated_at": 0.0,
            }
        queue_value = _decode_content(row[9])
        return {
            "session_id": session_id,
            "revision": int(row[0]),
            "owner_client_id": row[1],
            "owner_lease_until": float(row[2]),
            "turn_id": row[3],
            "state": row[4],
            "draft_client_id": row[5],
            "draft": row[6],
            "activity": row[7],
            "partial": row[8],
            "queue": queue_value if isinstance(queue_value, list) else [],
            "updated_at": float(row[10]),
        }

    def acquire_session_lease(
        self,
        session_id: str,
        client_id: str,
        turn_id: str,
        *,
        ttl: float = 15.0,
    ) -> bool:
        """Claim the single active model worker for a session, with crash expiry."""
        now = time.time()
        lease_until = now + max(5.0, float(ttl))
        with self._db_lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT owner_client_id, owner_lease_until FROM session_live "
                    "WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                if row and row[0] not in {"", client_id} and float(row[1]) > now:
                    self.db.rollback()
                    return False
                self.db.execute(
                    "INSERT INTO session_live "
                    "(session_id, revision, owner_client_id, owner_lease_until, turn_id, "
                    "state, activity, partial, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(session_id) DO UPDATE SET "
                    "revision=session_live.revision+1, owner_client_id=excluded.owner_client_id, "
                    "owner_lease_until=excluded.owner_lease_until, turn_id=excluded.turn_id, "
                    "state='running', activity='thinking', partial='', "
                    "updated_at=excluded.updated_at",
                    (
                        session_id,
                        1,
                        client_id,
                        lease_until,
                        turn_id,
                        "running",
                        "thinking",
                        "",
                        now,
                    ),
                )
                self.db.commit()
                return True
            except Exception:
                self.db.rollback()
                raise

    def renew_session_lease(
        self,
        session_id: str,
        client_id: str,
        turn_id: str,
        *,
        ttl: float = 15.0,
    ) -> bool:
        with self._db_lock, self.db:
            cursor = self.db.execute(
                "UPDATE session_live SET owner_lease_until=?, updated_at=? "
                "WHERE session_id=? AND owner_client_id=? AND turn_id=? AND state='running'",
                (time.time() + max(5.0, float(ttl)), time.time(), session_id, client_id, turn_id),
            )
        return cursor.rowcount == 1

    def release_session_lease(
        self,
        session_id: str,
        client_id: str,
        turn_id: str,
        *,
        state: str = "idle",
    ) -> bool:
        with self._db_lock, self.db:
            cursor = self.db.execute(
                "UPDATE session_live SET revision=revision+1, owner_client_id='', "
                "owner_lease_until=0, turn_id='', state=?, activity='ready', partial='', "
                "updated_at=? WHERE session_id=? AND owner_client_id=? AND turn_id=?",
                (state, time.time(), session_id, client_id, turn_id),
            )
        return cursor.rowcount == 1

    def clear_session_client(self, session_id: str, client_id: str) -> None:
        """Remove only this client's ephemeral composer presence."""
        with self._db_lock, self.db:
            self.db.execute(
                "DELETE FROM session_clients WHERE session_id=? AND client_id=?",
                (session_id, client_id),
            )
            self.db.execute(
                "UPDATE session_live SET revision=revision+1, draft_client_id='', "
                "draft='', queue_json='[]', updated_at=? "
                "WHERE session_id=? AND draft_client_id=?",
                (time.time(), session_id, client_id),
            )

    def last_session_id(self) -> str | None:
        with self._db_lock:
            row = self.db.execute(
                "SELECT session_id FROM turns ORDER BY ts DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def load_session(self, session_id: str, *, timestamps: bool = False) -> list[dict]:
        with self._db_lock:
            rows = self.db.execute(
                "SELECT role, content, model_content, ts FROM turns "
                "WHERE session_id=? ORDER BY ts, rowid",
                (session_id,),
            ).fetchall()
        out = []
        for role, content, model_content, ts in rows:
            try:
                out.append({"role": role, "content": json.loads(content)})
            except json.JSONDecodeError:
                out.append({"role": role, "content": content})
            if model_content is not None:
                out[-1]["model_content"] = _decode_content(model_content)
            if timestamps:
                out[-1]["ts"] = ts
        return out

    def resumable_sessions(self) -> list[dict]:
        """List every saved session newest first, named by its first user turn."""
        with self._db_lock:
            rows = self.db.execute(
                "SELECT t.session_id, MAX(t.ts), "
                "(SELECT content FROM turns AS first WHERE first.session_id=t.session_id "
                "AND first.role='user' ORDER BY first.ts, first.rowid LIMIT 1) "
                "FROM turns AS t GROUP BY t.session_id ORDER BY MAX(t.ts) DESC, t.session_id"
            ).fetchall()
            names = dict(self.db.execute("SELECT session_id, name FROM session_names"))
        return [
            {
                "session_id": session_id,
                "ts": ts,
                "title": names.get(session_id)
                or (
                    " ".join(_as_text(_decode_content(content)).split())[:160]
                    if content is not None
                    else "Untitled session"
                ),
            }
            for session_id, ts, content in rows
        ]

    def rename_session(self, session_id: str, name: str) -> None:
        name = " ".join(name.split())
        if not name or len(name) > 160:
            raise ValueError("Session name must contain 1–160 characters.")
        with self._db_lock, self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO session_names VALUES (?, ?)",
                (session_id, name),
            )

    def fork_session(self, source: str, target: str) -> None:
        with self._db_lock, self.db:
            if self.db.execute("SELECT 1 FROM turns WHERE session_id=?", (target,)).fetchone():
                raise ValueError("Target session already exists.")
            self.db.execute(
                "INSERT INTO turns (session_id, ts, role, content, model_content) "
                "SELECT ?, ts, role, content, model_content FROM turns "
                "WHERE session_id=? ORDER BY ts, rowid",
                (target, source),
            )
            self.db.execute(
                "INSERT INTO session_names SELECT ?, name || ' (fork)' "
                "FROM session_names WHERE session_id=?",
                (target, source),
            )

    def delete_session(self, session_id: str) -> int:
        session_id = session_id.strip()
        if not session_id:
            return 0
        with self._db_lock, self.db:
            row = self.db.execute(
                "SELECT COUNT(*) FROM turns WHERE session_id=?",
                (session_id,),
            ).fetchone()
            turns = int(row[0]) if row else 0
            if turns:
                self.db.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_names WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_events WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_live WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_clients WHERE session_id=?", (session_id,))
        return turns

    def session_counts(self) -> dict[str, int]:
        with self._db_lock:
            row = self.db.execute(
                "SELECT COUNT(DISTINCT session_id), COUNT(*) FROM turns"
            ).fetchone()
        return {
            "sessions": int(row[0]) if row else 0,
            "turns": int(row[1]) if row else 0,
        }

    def clear_sessions(self) -> dict[str, int]:
        with self._db_lock, self.db:
            row = self.db.execute(
                "SELECT COUNT(DISTINCT session_id), COUNT(*) FROM turns"
            ).fetchone()
            sessions = int(row[0]) if row else 0
            turns = int(row[1]) if row else 0
            if turns:
                self.db.execute("DELETE FROM turns")
            self.db.execute("DELETE FROM session_names")
            self.db.execute("DELETE FROM session_events")
            self.db.execute("DELETE FROM session_live")
            self.db.execute("DELETE FROM session_clients")
        return {"sessions": sessions, "turns": turns}

    def session_tail(self, session_id: str, limit: int = 8) -> list[dict]:
        with self._db_lock:
            rows = self.db.execute(
                "SELECT role, content FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out = []
        for role, content in reversed(rows):
            out.append({"role": role, "content": _decode_content(content)})
        return out

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        with self._db_lock:
            rows = self.db.execute(
                "SELECT session_id, MAX(ts), COUNT(*) FROM turns "
                "GROUP BY session_id ORDER BY MAX(ts) DESC LIMIT ?",
                (limit,),
            ).fetchall()
            preview_rows = {
                session_id: self.db.execute(
                    "SELECT role, content FROM turns WHERE session_id=? ORDER BY ts DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
                for session_id, _ts, _count in rows
            }
        sessions = []
        for session_id, ts, count in rows:
            preview_row = preview_rows[session_id]
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
        with self._db_lock:
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
