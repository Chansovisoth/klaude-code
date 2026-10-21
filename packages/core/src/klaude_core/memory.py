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


class SessionLeaseLost(RuntimeError):
    """A stale terminal worker may no longer start effects or write its turn."""


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
    SESSION_LEASE_TTL_SECONDS = 60.0

    def open_session_io(self) -> Memory:
        """Independent existing-database connection for short UI I/O operations."""
        clone = object.__new__(Memory)
        clone.__dict__.update(self.__dict__)
        clone.db = sqlite3.connect(
            self.sessions_db.absolute().as_uri() + "?mode=rw", uri=True,
            timeout=0.2, check_same_thread=False,
        )
        clone.db.create_function("klaude_writer_v2", 0, lambda: 1)
        clone.db.create_function("klaude_writer_v3", 0, lambda: 1)
        clone._db_lock = threading.RLock()
        return clone

    def __init__(self, memory_file: Path, sessions_db: Path):
        self._auto_memory_override: bool | None = None
        self.memory_file = memory_file
        self.sessions_db = sessions_db
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
        self.db.create_function("klaude_writer_v2", 0, lambda: 1)
        self.db.create_function("klaude_writer_v3", 0, lambda: 1)
        self._db_lock = threading.RLock()
        self.db.execute("PRAGMA busy_timeout=5000")
        for attempt in range(100):
            try:
                self.db.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == 99:
                    raise
                time.sleep(0.05)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                session_id TEXT, ts REAL, role TEXT, content TEXT, model_content TEXT
            )"""
        )
        # A browser worker and terminal can open an older database together.
        # Inspect and migrate under the same SQLite write transaction so neither
        # uses a stale column list after another process publishes the migration.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            turn_columns = {row[1] for row in self.db.execute("PRAGMA table_info(turns)")}
            for column in ("model_content", "attachments", "attachment_previews"):
                if column not in turn_columns:
                    self.db.execute(f"ALTER TABLE turns ADD COLUMN {column} TEXT")
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
            "CREATE TABLE IF NOT EXISTS session_archive "
            "(session_id TEXT PRIMARY KEY, archived_at REAL NOT NULL)"
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
                turn_started_at REAL NOT NULL DEFAULT 0,
                draft_client_id TEXT NOT NULL DEFAULT '',
                draft TEXT NOT NULL DEFAULT '',
                activity TEXT NOT NULL DEFAULT 'ready',
                partial TEXT NOT NULL DEFAULT '',
                queue_json TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL
            )"""
        )
        live_columns = {
            row[1] for row in self.db.execute("PRAGMA table_info(session_live)").fetchall()
        }
        if "turn_started_at" not in live_columns:
            try:
                self.db.execute(
                    "ALTER TABLE session_live ADD COLUMN turn_started_at REAL NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                # Another resumed client may finish the additive migration
                # after this process inspected the legacy schema.
                migrated_columns = {
                    row[1] for row in self.db.execute("PRAGMA table_info(session_live)").fetchall()
                }
                if "turn_started_at" not in migrated_columns:
                    raise
        if "fence_generation" not in live_columns:
            try:
                self.db.execute(
                    "ALTER TABLE session_live ADD COLUMN fence_generation "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                if "fence_generation" not in {
                    row[1] for row in self.db.execute("PRAGMA table_info(session_live)")
                }:
                    raise
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

    def update_fact(self, memory_id: str, replacement: str | None) -> bool:
        """Edit/delete one exact fact under the existing cross-client lock.

        IDs derive from content, so a stale selection cannot edit a newer fact.
        None deletes; empty, sensitive, or duplicate replacements are rejected.
        """
        if not re.fullmatch(r"[0-9a-f]{12}", memory_id):
            return False
        fact = _clean_fact(replacement) if replacement is not None else None
        if fact is not None and (not fact or is_sensitive_memory(fact)):
            return False
        with self._db_lock, self._memory_mutation_lock():
            entries = self._load_entries()
            index = next((i for i, entry in enumerate(entries) if entry.id == memory_id), None)
            if index is None:
                return False
            if fact is not None and any(
                i != index and _normalize_fact(entry.fact) == _normalize_fact(fact)
                for i, entry in enumerate(entries)
            ):
                return False
            lines = [entry.raw for entry in entries]
            if fact is None:
                del lines[index]
            else:
                lines[index] = f"- [memory:{_memory_id(fact)}] {fact}"
            self._write_memory_file("\n".join(lines) + ("\n" if lines else ""))
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
        override = self._auto_memory_override
        if override is not None:
            return override
        with self._db_lock:
            row = self.db.execute(
                "SELECT value FROM settings WHERE key='auto_memory_enabled'"
            ).fetchone()
        if not row:
            return True
        return row[0] == "1"

    def set_auto_memory_override(self, enabled: bool | None) -> None:
        """Process-local intent while an asynchronous preference save is unconfirmed."""
        self._auto_memory_override = enabled

    def set_auto_memory(self, enabled: bool, *, expected_enabled: bool | None = None) -> None:
        with self._db_lock, self.db:
            if expected_enabled is not None:
                self.db.execute("BEGIN IMMEDIATE")
                row = self.db.execute(
                    "SELECT value FROM settings WHERE key='auto_memory_enabled'"
                ).fetchone()
                if (not row or row[0] == "1") != expected_enabled:
                    raise ValueError("Memory setting changed; reload before saving")
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

    def session_lease_fence(self, session_id: str, client_id: str, turn_id: str) -> int:
        with self._db_lock:
            row = self.db.execute(
                "SELECT fence_generation FROM session_live WHERE session_id=? "
                "AND owner_client_id=? AND turn_id=? AND state='running' "
                "AND owner_lease_until>?",
                (session_id, client_id, turn_id, time.time()),
            ).fetchone()
        if row is None:
            raise SessionLeaseLost("session worker lost its lease")
        return int(row[0])

    def _assert_session_lease(
        self, session_id: str, client_id: str, turn_id: str, fence: int,
    ) -> None:
        row = self.db.execute(
            "SELECT 1 FROM session_live WHERE session_id=? AND owner_client_id=? "
            "AND turn_id=? AND fence_generation=? AND state='running' "
            "AND owner_lease_until>?",
            (session_id, client_id, turn_id, fence, time.time()),
        ).fetchone()
        if row is None:
            raise SessionLeaseLost("session worker lost its lease")

    def assert_session_lease(
        self, session_id: str, client_id: str, turn_id: str, fence: int,
    ) -> None:
        with self._db_lock:
            self._assert_session_lease(session_id, client_id, turn_id, fence)

    def log_turn_fenced(
        self, session_id: str, client_id: str, turn_id: str, fence: int,
        role: str, content: object, *, model_content: object | None = None,
    ) -> None:
        with self._db_lock, self.db:
            self._assert_session_lease(session_id, client_id, turn_id, fence)
            self.db.execute(
                "INSERT INTO turns(session_id,ts,role,content,model_content) "
                "VALUES (?,?,?,?,?)",
                (session_id, time.time(), role, json.dumps(content, ensure_ascii=False),
                 json.dumps(model_content, ensure_ascii=False)
                 if model_content is not None else None),
            )

    def record_session_update(
        self, session_id: str, client_id: str, detail: str, *, runtime: dict | None = None
    ) -> None:
        """Publish setting history and observer event in one transaction."""
        if not detail or len(detail) > 2048:
            raise ValueError("Session setting detail must contain 1-2048 characters")
        now = time.time()
        with self._db_lock, self.db:
            if runtime is not None:
                self._store_session_runtime(session_id, runtime)
            self.db.execute(
                "INSERT INTO turns (session_id, ts, role, content, model_content) "
                "VALUES (?,?,?,?,NULL)",
                (session_id, now, "system", json.dumps(
                    {"event": "session_update", "detail": detail}, ensure_ascii=False
                )),
            )
            self.db.execute(
                "INSERT INTO session_events "
                "(session_id, turn_id, client_id, ts, kind, payload) VALUES (?,?,?,?,?,?)",
                (session_id, "", client_id, now, "session_update",
                 json.dumps({"detail": detail}, ensure_ascii=False)),
            )

    def publish_session_event(
        self,
        session_id: str,
        client_id: str,
        kind: str,
        payload: object,
        *,
        turn_id: str = "",
        fence: int | None = None,
    ) -> int:
        """Append one ordered cross-process session event and return its cursor."""
        encoded = json.dumps(payload, ensure_ascii=False)
        with self._db_lock, self.db:
            if fence is not None:
                self._assert_session_lease(session_id, client_id, turn_id, fence)
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
        runtime: dict | None = None,
        fence: int | None = None,
    ) -> int:
        """Save a user turn and announce it as one atomic database change."""
        payload = json.dumps({"text": _as_text(visible_content)}, ensure_ascii=False)
        from .session_runtime import decode

        if runtime is not None and decode(runtime) is None:
            raise ValueError("Invalid session runtime state")
        with self._db_lock, self.db:
            if fence is not None:
                self._assert_session_lease(session_id, client_id, turn_id, fence)
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
            if runtime is not None:
                self._store_session_runtime(session_id, runtime)
        return int(cursor.lastrowid or 0)

    def _store_session_runtime(self, session_id: str, runtime: dict) -> None:
        from .session_runtime import PREFIX, decode

        if decode(runtime) is None:
            raise ValueError("Invalid session runtime state")
        previous = self.session_runtime(session_id)
        if previous is None or previous["at"] <= runtime["at"]:
            self.db.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
                (PREFIX + session_id, json.dumps(runtime)),
            )

    def session_runtime(self, session_id: str) -> dict | None:
        from .session_runtime import PREFIX, decode

        with self._db_lock:
            row = self.db.execute(
                "SELECT value FROM settings WHERE key=?", (PREFIX + session_id,),
            ).fetchone()
        if row is None or len(row[0]) > 2048:
            return None
        try:
            return decode(json.loads(row[0]))
        except (ValueError, TypeError):
            return None

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
            has_application_streams = bool(self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='application_streams'"
            ).fetchone())
            pruned_application_id = 0
            if has_application_streams:
                row = self.db.execute(
                    "SELECT COALESCE(MAX(id),0) FROM session_events "
                    "WHERE session_id=? AND ts<? AND kind='application.public.v1'",
                    (session_id, cutoff),
                ).fetchone()
                pruned_application_id = int(row[0] or 0)
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
                if has_application_streams:
                    row = self.db.execute(
                        "SELECT COALESCE(MAX(id),0) FROM ("
                        "SELECT id,kind FROM session_events WHERE session_id=? "
                        "ORDER BY id LIMIT ?) WHERE kind='application.public.v1'",
                        (session_id, excess_count),
                    ).fetchone()
                    pruned_application_id = max(pruned_application_id, int(row[0] or 0))
                capped = self.db.execute(
                    "DELETE FROM session_events WHERE id IN ("
                    "SELECT id FROM session_events WHERE session_id=? ORDER BY id LIMIT ?"
                    ")",
                    (session_id, excess_count),
                ).rowcount
            if pruned_application_id:
                self.db.execute(
                    "UPDATE application_streams SET minimum_id=MAX(minimum_id, ?) "
                    "WHERE session_id=?",
                    (pruned_application_id, session_id),
                )
            self.db.execute(
                "DELETE FROM session_clients WHERE session_id=? AND updated_at<?",
                (session_id, cutoff),
            )
        return max(0, old) + max(0, capped)

    def session_snapshot(self, session_id: str) -> dict:
        """Read one session snapshot and durably finalize expired worker turns.

        Recovery is serialized with ``BEGIN IMMEDIATE`` so multiple resumed
        clients cannot each record the same interruption. Public partial output
        is promoted to the durable transcript before the expired lease is
        cleared; tool results are never fabricated during recovery.
        """
        with self._db_lock:
            now = time.time()
            preflight_live = self.session_live_state(session_id)
            preflight_active = (
                str(preflight_live.get("turn_id") or "")
                if preflight_live.get("state") == "running"
                and float(preflight_live.get("owner_lease_until") or 0) > now
                else ""
            )
            unfinished = self.db.execute(
                "SELECT 1 FROM session_events AS started "
                "WHERE started.session_id=? AND started.kind='user_started' "
                "AND started.turn_id<>? AND NOT EXISTS ("
                "SELECT 1 FROM session_events AS finished "
                "WHERE finished.session_id=started.session_id "
                "AND finished.turn_id=started.turn_id AND finished.kind='turn_done'"
                ") LIMIT 1",
                (session_id, preflight_active),
            ).fetchone()
            expired_live = (
                preflight_live.get("state") == "running"
                and float(preflight_live.get("owner_lease_until") or 0) <= now
            )
            application_owned = bool(
                expired_live
                and self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='application_turns'"
                ).fetchone()
                and self.db.execute(
                    "SELECT 1 FROM application_turns WHERE session_id=? AND turn_id=? "
                    "AND state='running'",
                    (session_id, preflight_live.get("turn_id")),
                ).fetchone()
            )
            self.db.execute(
                "BEGIN IMMEDIATE" if unfinished or (expired_live and not application_owned)
                else "BEGIN"
            )
            try:
                turns = self.load_session(session_id, timestamps=True)
                live = self.session_live_state(session_id)
                clients = self.session_client_states(session_id)
                events = []
                after = 0
                while True:
                    batch = self.session_events_since(session_id, after, limit=2_000)
                    events.extend(batch)
                    if len(batch) < 2_000:
                        break
                    after = batch[-1]["id"]
                started = {e["turn_id"]: e for e in events if e["kind"] == "user_started"}
                finished = {e["turn_id"] for e in events if e["kind"] == "turn_done"}
                by_turn: dict[str, list[dict]] = {}
                for event in events:
                    by_turn.setdefault(event["turn_id"], []).append(event)
                active = (
                    live.get("turn_id")
                    if live.get("state") == "running"
                    and live.get("owner_lease_until", 0) > time.time()
                    else None
                )
                live_capabilities: dict = {}
                if active:
                    for event in reversed(by_turn.get(str(active), [])):
                        if event["kind"] != "capabilities":
                            continue
                        payload = event.get("payload")
                        snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
                        if isinstance(snapshot, dict):
                            live_capabilities = snapshot
                        break
                recovered_turn_ids: list[str] = []
                for turn_id, start_event in started.items():
                    if application_owned and turn_id == preflight_live.get("turn_id"):
                        continue
                    if turn_id in finished or turn_id == active:
                        continue
                    related = by_turn[turn_id]
                    stamp = max(e["ts"] for e in related) + 0.000001
                    next_turn_started_at = min(
                        (
                            float(event["ts"])
                            for other_id, event in started.items()
                            if other_id != turn_id
                            and float(event["ts"]) > float(start_event["ts"])
                        ),
                        default=float("inf"),
                    )
                    partial = "".join(
                        str(e["payload"].get("text", ""))
                        for e in related
                        if e["kind"] == "assistant_delta"
                    )
                    durable_assistant_exists = any(
                        turn.get("role") == "assistant"
                        and float(turn.get("ts", 0)) >= float(start_event["ts"])
                        and float(turn.get("ts", 0)) < next_turn_started_at
                        for turn in turns
                    )
                    if partial and not durable_assistant_exists:
                        self.db.execute(
                            "INSERT INTO turns "
                            "(session_id, ts, role, content, model_content) VALUES (?,?,?,?,NULL)",
                            (
                                session_id,
                                stamp,
                                "assistant",
                                json.dumps(partial, ensure_ascii=False),
                            ),
                        )
                        turns.append({"role": "assistant", "content": partial, "ts": stamp})
                        stamp += 0.000001
                    message = (
                        "Interrupted: this turn has no completion record. Its worker ended "
                        "or lost its lease; saved output above is preserved."
                    )
                    system_content = {"event": "runtime_error", "message": message}
                    interruption_exists = any(
                        turn.get("role") == "system"
                        and float(turn.get("ts", 0)) >= float(start_event["ts"])
                        and float(turn.get("ts", 0)) < next_turn_started_at
                        and turn.get("content") == system_content
                        for turn in turns
                    )
                    if not interruption_exists:
                        self.db.execute(
                            "INSERT INTO turns "
                            "(session_id, ts, role, content, model_content) "
                            "VALUES (?,?,?,?,NULL)",
                            (
                                session_id,
                                stamp,
                                "system",
                                json.dumps(system_content, ensure_ascii=False),
                            ),
                        )
                        turns.append(
                            {"role": "system", "ts": stamp, "content": system_content}
                        )
                    self.db.execute(
                        "INSERT INTO session_events "
                        "(session_id, turn_id, client_id, ts, kind, payload) "
                        "VALUES (?,?,?,?,?,?)",
                        (
                            session_id,
                            turn_id,
                            str(start_event.get("client_id", "")),
                            stamp + 0.000001,
                            "turn_done",
                            json.dumps(
                                {
                                    "suffix": "interrupted",
                                    "cancelled": True,
                                    "failed": True,
                                    "recovered": True,
                                    "reason": "worker lease expired before completion",
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )
                    recovered_turn_ids.append(turn_id)

                if live.get("state") == "running" and not active and not application_owned:
                    recovery_now = time.time()
                    self.db.execute(
                        "UPDATE session_live SET revision=revision+1, owner_client_id='', "
                        "owner_lease_until=0, turn_id='', state='interrupted', "
                        "turn_started_at=0, activity='ready', partial='', updated_at=? "
                        "WHERE session_id=? AND state='running' AND owner_lease_until<=?",
                        (recovery_now, session_id, recovery_now),
                    )
                    live = self.session_live_state(session_id)
                turns.sort(key=lambda item: item["ts"])
                cursor = self.latest_session_event_id(session_id)
                runtime = self.session_runtime(session_id)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
        return {
            "turns": turns,
            "runtime": runtime,
            "live": live,
            "clients": clients,
            "event_cursor": cursor,
            "recovered_turn_ids": recovered_turn_ids,
            "live_capabilities": live_capabilities,
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
            "turn_started_at",
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
                "turn_started_at, draft_client_id, draft, activity, partial, queue_json, "
                "updated_at "
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
                "turn_started_at": 0.0,
                "draft_client_id": "",
                "draft": "",
                "activity": "ready",
                "partial": "",
                "queue": [],
                "updated_at": 0.0,
            }
        queue_value = _decode_content(row[10])
        return {
            "session_id": session_id,
            "revision": int(row[0]),
            "owner_client_id": row[1],
            "owner_lease_until": float(row[2]),
            "turn_id": row[3],
            "state": row[4],
            "turn_started_at": float(row[5]),
            "draft_client_id": row[6],
            "draft": row[7],
            "activity": row[8],
            "partial": row[9],
            "queue": queue_value if isinstance(queue_value, list) else [],
            "updated_at": float(row[11]),
        }

    def acquire_session_lease(
        self,
        session_id: str,
        client_id: str,
        turn_id: str,
        *,
        ttl: float = SESSION_LEASE_TTL_SECONDS,
    ) -> bool:
        """Claim the single active model worker for a session, with crash expiry."""
        now = time.time()
        lease_until = now + max(5.0, float(ttl))
        with self._db_lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if self.db.execute(
                    "SELECT 1 FROM session_archive WHERE session_id=?", (session_id,)
                ).fetchone():
                    self.db.rollback()
                    return False
                if self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='application_deleted_sessions'"
                ).fetchone() and self.db.execute(
                    "SELECT 1 FROM application_deleted_sessions WHERE session_id=?",
                    (session_id,),
                ).fetchone():
                    self.db.rollback()
                    return False
                row = self.db.execute(
                    "SELECT owner_client_id, owner_lease_until, turn_id, state FROM session_live "
                    "WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                if row and row[3] == "interrupted":
                    self.db.rollback()
                    return False
                if (
                    row
                    and row[0]
                    and float(row[1]) > now
                    and (row[0] != client_id or row[2] != turn_id)
                ):
                    self.db.rollback()
                    return False
                self.db.execute(
                    "INSERT INTO session_live "
                    "(session_id, revision, owner_client_id, owner_lease_until, turn_id, "
                    "state, turn_started_at, activity, partial, updated_at, fence_generation) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,1) "
                    "ON CONFLICT(session_id) DO UPDATE SET "
                    "revision=session_live.revision+1, owner_client_id=excluded.owner_client_id, "
                    "owner_lease_until=excluded.owner_lease_until, turn_id=excluded.turn_id, "
                    "state='running', turn_started_at=excluded.turn_started_at, "
                    "activity='thinking', partial='', "
                    "updated_at=excluded.updated_at, "
                    "fence_generation=session_live.fence_generation+1",
                    (
                        session_id,
                        1,
                        client_id,
                        lease_until,
                        turn_id,
                        "running",
                        now,
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
        ttl: float = SESSION_LEASE_TTL_SECONDS,
        fence: int | None = None,
    ) -> bool:
        with self._db_lock, self.db:
            cursor = self.db.execute(
                "UPDATE session_live SET owner_lease_until=?, updated_at=? "
                "WHERE session_id=? AND owner_client_id=? AND turn_id=? AND state='running' "
                "AND owner_lease_until>?" + (
                    " AND fence_generation=?" if fence is not None else ""
                ),
                (
                    time.time() + max(5.0, float(ttl)),
                    time.time(),
                    session_id,
                    client_id,
                    turn_id,
                    time.time(),
                ) + ((fence,) if fence is not None else ()),
            )
        return cursor.rowcount == 1

    def release_session_lease(
        self,
        session_id: str,
        client_id: str,
        turn_id: str,
        *,
        state: str = "idle",
        fence: int | None = None,
    ) -> bool:
        with self._db_lock, self.db:
            cursor = self.db.execute(
                "UPDATE session_live SET revision=revision+1, owner_client_id='', "
                "owner_lease_until=0, turn_id='', state=?, turn_started_at=0, "
                "activity='ready', partial='', "
                "updated_at=? WHERE session_id=? AND owner_client_id=? AND turn_id=?" + (
                    " AND fence_generation=?" if fence is not None else ""
                ),
                (state, time.time(), session_id, client_id, turn_id)
                + ((fence,) if fence is not None else ()),
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
                "SELECT session_id FROM turns WHERE NOT EXISTS "
                "(SELECT 1 FROM session_archive AS a WHERE a.session_id=turns.session_id) "
                "ORDER BY ts DESC LIMIT 1"
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

    def public_session_records(self, session_id: str) -> list[dict]:
        """Read exportable columns without loading private model continuation data."""
        with self._db_lock:
            rows = self.db.execute(
                "SELECT role,content,ts FROM turns WHERE session_id=? AND ("
                "role IN ('user','assistant') OR (role='system' AND "
                "CASE WHEN json_valid(content) THEN json_extract(content,'$.event') "
                "IN ('edit_summary','activity_update','input_request','input_answer',"
                "'subagent_activity') ELSE 0 END)) ORDER BY ts,rowid",
                (session_id,),
            ).fetchall()
        return [
            {"role": role, "content": _decode_content(content), "ts": ts}
            for role, content, ts in rows
        ]

    def resumable_sessions(self) -> list[dict]:
        """List every saved session newest first, named by its first user turn."""
        with self._db_lock:
            rows = self.db.execute(
                "SELECT t.session_id, MAX(t.ts), "
                "(SELECT content FROM turns AS first WHERE first.session_id=t.session_id "
                "AND first.role='user' ORDER BY first.ts, first.rowid LIMIT 1) "
                "FROM turns AS t WHERE NOT EXISTS "
                "(SELECT 1 FROM session_archive AS a WHERE a.session_id=t.session_id) "
                "GROUP BY t.session_id ORDER BY MAX(t.ts) DESC, t.session_id"
            ).fetchall()
            names = dict(self.db.execute("SELECT session_id, name FROM session_names"))
            active = {
                row[0]
                for row in self.db.execute(
                    "SELECT session_id FROM session_live "
                    "WHERE state='running' AND owner_lease_until>?",
                    (time.time(),),
                )
            }
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
                "active": session_id in active,
            }
            for session_id, ts, content in rows
        ]

    def session_title(self, session_id: str) -> str:
        """Return the explicit name or the same derived title used by `/resume`."""
        with self._db_lock:
            named = self.db.execute(
                "SELECT name FROM session_names WHERE session_id=?", (session_id,)
            ).fetchone()
            if named:
                return str(named[0])
            first = self.db.execute(
                "SELECT content FROM turns WHERE session_id=? AND role='user' "
                "ORDER BY ts, rowid LIMIT 1",
                (session_id,),
            ).fetchone()
        if not first:
            return "Untitled session"
        return " ".join(_as_text(_decode_content(first[0])).split())[:160] or "Untitled session"

    def rename_session(
        self, session_id: str, name: str, *, expected_name: str | None = None,
        expected_workspace: str | None = None,
    ) -> None:
        name = " ".join(name.split())
        if not name or len(name) > 160:
            raise ValueError("Session name must contain 1–160 characters.")
        with self._db_lock, self.db:
            if expected_name is not None or expected_workspace is not None:
                self.db.execute("BEGIN IMMEDIATE")
            if expected_workspace is not None:
                binding = self.db.execute(
                    "SELECT path FROM application_workspace WHERE session_id=?", (session_id,),
                ).fetchone()
                if binding is None or binding[0] != expected_workspace:
                    raise ValueError("Session workspace changed; reload before saving")
            if expected_name is not None:
                named = self.db.execute(
                    "SELECT name FROM session_names WHERE session_id=?", (session_id,),
                ).fetchone()
                if (str(named[0]) if named else "") != expected_name:
                    raise ValueError("Session name changed; review again")
            self.db.execute(
                "INSERT OR REPLACE INTO session_names VALUES (?, ?)",
                (session_id, name),
            )

    def rename_session_if_current(self, session_id: str, name: str, expected_name: str) -> bool:
        name = " ".join(name.split())
        if not name or len(name)>80:
            raise ValueError("AI session name must contain 1–80 characters")
        # One conditional statement: concurrent manual rename wins, including
        # the race where the session previously had no explicit title.
        with self._db_lock, self.db:
            cursor = self.db.execute(
                "INSERT INTO session_names (session_id,name) SELECT ?,? "
                "WHERE COALESCE((SELECT name FROM session_names WHERE session_id=?),'')=? "
                "ON CONFLICT(session_id) DO UPDATE SET name=excluded.name "
                "WHERE session_names.name=?",
                (session_id,name,session_id,expected_name,expected_name),
            )
            return cursor.rowcount==1

    def fork_session(
        self, source: str, target: str, *, through_row_id: int | None = None,
        retry: bool = False,
    ) -> str | None:
        """Copy an idle session, optionally at one exact saved assistant reply.

        Retry copies only the prefix before that reply's user prompt and returns
        the prompt for a new admission. Original records are never changed.
        """
        if (through_row_id is not None and
                (type(through_row_id) is not int or not 0 < through_row_id <= 2**63 - 1)):
            raise ValueError("Invalid message boundary")
        if type(retry) is not bool or (retry and through_row_id is None):
            raise ValueError("Retry requires a message boundary")
        with self._db_lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute(
                "SELECT 1 FROM session_live WHERE session_id=? "
                "AND (owner_client_id<>'' OR state='interrupted')", (source,),
            ).fetchone():
                raise ValueError("Source session has unresolved work; reconcile it first")
            prompt: str | None = None
            cutoff = through_row_id
            if cutoff is not None:
                if self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='application_queue'"
                ).fetchone() and self.db.execute(
                    "SELECT 1 FROM application_queue WHERE session_id=? "
                    "AND state NOT IN ('removed','submitted')", (source,),
                ).fetchone():
                    raise ValueError("Source session has queued work")
                selected = self.db.execute(
                    "SELECT role FROM turns WHERE session_id=? AND rowid=?",
                    (source, cutoff),
                ).fetchone()
                if selected != ("assistant",):
                    raise ValueError("Saved assistant message not found")
                if retry:
                    user = self.db.execute(
                        "SELECT rowid,content FROM turns WHERE session_id=? AND role='user' "
                        "AND rowid<? ORDER BY rowid DESC LIMIT 1", (source, cutoff),
                    ).fetchone()
                    if user is None:
                        raise ValueError("Original prompt unavailable")
                    decoded = _decode_content(user[1])
                    if (not isinstance(decoded, str) or not decoded.strip()
                            or len(decoded) > 65_536):
                        raise ValueError("Original prompt unavailable")
                    prompt = decoded
                    cutoff = int(user[0]) - 1
            if self.db.execute("SELECT 1 FROM turns WHERE session_id=?", (target,)).fetchone():
                raise ValueError("Target session already exists.")
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='application_deleted_sessions'"
            ).fetchone() and self.db.execute(
                "SELECT 1 FROM application_deleted_sessions WHERE session_id=?", (target,)
            ).fetchone():
                raise ValueError("Target session ID was deleted")
            self.db.execute(
                "INSERT INTO turns (session_id, ts, role, content, model_content, "
                "attachments, attachment_previews) "
                "SELECT ?, ts, role, content, model_content, attachments, attachment_previews "
                "FROM turns "
                "WHERE session_id=? AND (? IS NULL OR rowid<=?) ORDER BY ts, rowid",
                (target, source, cutoff, cutoff),
            )
            self.db.execute(
                "INSERT INTO session_names SELECT ?, name || ' (fork)' "
                "FROM session_names WHERE session_id=?",
                (target, source),
            )
            runtime = self.session_runtime(source)
            if runtime is not None:
                self._store_session_runtime(target, runtime)
            if self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='application_workspace'"
            ).fetchone():
                self.db.execute(
                    "INSERT INTO application_workspace(session_id,path,revision,updated_at) "
                    "SELECT ?,path,1,? FROM application_workspace WHERE session_id=?",
                    (target, time.time(), source),
                )
                self.db.execute(
                    "INSERT INTO application_session_options "
                    "(session_id,revision,plan_mode,updated_at) "
                    "SELECT ?,1,plan_mode,? FROM application_session_options "
                    "WHERE session_id=?", (target, time.time(), source),
                )
            return prompt

    def delete_session(
        self, session_id: str, *, expected_total_turns: int | None = None
    ) -> int:
        session_id = session_id.strip()
        if not session_id:
            return 0
        if expected_total_turns is not None and (
            type(expected_total_turns) is not int or expected_total_turns < 0
        ):
            raise ValueError("Invalid reviewed session count")
        with self._db_lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute(
                "SELECT 1 FROM session_live WHERE session_id=? "
                "AND (owner_client_id<>'' OR state='interrupted')",
                (session_id,),
            ).fetchone():
                raise ValueError("Session has unresolved work; reconcile it before deletion")
            if expected_total_turns is not None:
                actual = self.db.execute(
                    "SELECT COUNT(*) FROM turns WHERE session_id=?", (session_id,)
                ).fetchone()[0]
                if actual != expected_total_turns:
                    raise ValueError("Session changed; review deletion again")
            row = self.db.execute(
                "SELECT COUNT(*) FROM turns WHERE session_id=? AND role IN ('user','assistant')",
                (session_id,),
            ).fetchone()
            turns = int(row[0]) if row else 0
            self.db.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_names WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_events WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_live WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_clients WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM session_archive WHERE session_id=?", (session_id,))
            self.db.execute("DELETE FROM settings WHERE key=?", ("session.runtime." + session_id,))
            self._delete_application_session(session_id)
        return turns

    def _delete_application_session(self, session_id: str) -> None:
        """Retain request tombstones while removing live application projections."""
        tables = {
            str(row[0]) for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'application_%'"
            )
        }
        if "application_deleted_sessions" not in tables:
            return
        self.db.execute(
            "INSERT OR IGNORE INTO application_deleted_sessions(session_id,deleted_at) "
            "VALUES (?,?)", (session_id, time.time()),
        )
        if "application_turns" in tables:
            self.db.execute(
                "UPDATE application_turns SET fingerprint='',state='gone' "
                "WHERE session_id=?", (session_id,),
            )
        for table in (
            "application_queue", "application_control", "application_workspace",
            "application_session_options", "application_streams", "application_decisions",
            "application_activity",
        ):
            if table in tables:
                self.db.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))

    def session_archived(self, session_id: str) -> bool:
        with self._db_lock:
            return self.db.execute(
                "SELECT 1 FROM session_archive WHERE session_id=?", (session_id,)
            ).fetchone() is not None

    def change_session_archive(
        self, session_id: str, operation: str, *, expected_total_turns: int | None = None,
        expected_last_row: int | None = None,
        expected_workspace: str | None = None,
    ) -> None:
        """Atomically archive/restore/delete, excluding active worker leases.

        Archive changes browsing visibility only. Turns, events, names and recall
        remain intact. Deletion requires the record to still be archived; a stale
        confirmation cannot delete a session another client has restored.
        """
        if operation not in {"archive", "restore", "delete"}:
            raise ValueError("Unknown session action")
        with self._db_lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if expected_workspace is not None:
                    binding = self.db.execute(
                        "SELECT path FROM application_workspace WHERE session_id=?", (session_id,),
                    ).fetchone()
                    if binding is None or binding[0] != expected_workspace:
                        raise ValueError("Session workspace changed; reload before saving")
                if expected_total_turns is not None:
                    actual = self.db.execute(
                        "SELECT COUNT(*),COALESCE(MAX(rowid),0) FROM turns WHERE session_id=?",
                        (session_id,),
                    ).fetchone()
                    if (actual[0] != expected_total_turns
                            or expected_last_row is not None and actual[1] != expected_last_row):
                        raise ValueError("Session changed; review the action again")
                if not self.db.execute(
                    "SELECT 1 FROM turns WHERE session_id=? LIMIT 1", (session_id,)
                ).fetchone():
                    raise ValueError("Session no longer exists; reload the list")
                active = self.db.execute(
                    "SELECT owner_client_id, owner_lease_until FROM session_live "
                    "WHERE session_id=? "
                    "AND (owner_client_id<>'' OR state='interrupted')",
                    (session_id,),
                ).fetchone()
                if active:
                    if active[0] and float(active[1]) > time.time():
                        raise ValueError("Session has an active worker")
                    raise ValueError("Session has unresolved work; reconcile it first")
                archived = self.session_archived(session_id)
                if archived != (operation != "archive"):
                    raise ValueError("Session archive state changed; reload the list")
                if operation == "archive":
                    self.db.execute(
                        "INSERT INTO session_archive VALUES (?, ?)", (session_id, time.time())
                    )
                elif operation == "restore":
                    self.db.execute("DELETE FROM session_archive WHERE session_id=?", (session_id,))
                else:
                    # Same transaction and lock as the state/lease checks above.
                    for table in ("turns", "session_names", "session_events", "session_live",
                                  "session_clients", "session_archive"):
                        self.db.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
                    self.db.execute(
                        "DELETE FROM settings WHERE key=?", ("session.runtime." + session_id,)
                    )
                    self._delete_application_session(session_id)
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def session_counts(self) -> dict[str, int]:
        with self._db_lock:
            row = self.db.execute(
                "SELECT COUNT(DISTINCT session_id), COUNT(*) FROM turns "
                "WHERE role IN ('user','assistant')"
            ).fetchone()
        return {
            "sessions": int(row[0]) if row else 0,
            "turns": int(row[1]) if row else 0,
        }

    def clear_sessions(
        self, *, expected_counts: tuple[int, int] | None = None
    ) -> dict[str, int]:
        if expected_counts is not None and (
            not isinstance(expected_counts, tuple)
            or len(expected_counts) != 2
            or any(type(value) is not int or value < 0 for value in expected_counts)
        ):
            raise ValueError("Invalid reviewed session counts")
        with self._db_lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            if self.db.execute(
                "SELECT 1 FROM session_live WHERE owner_client_id<>'' "
                "OR state='interrupted' LIMIT 1",
            ).fetchone():
                raise ValueError("A session has unresolved work; reconcile it first")
            session_ids = [str(row[0]) for row in self.db.execute(
                "SELECT DISTINCT session_id FROM turns UNION "
                "SELECT DISTINCT session_id FROM session_live"
            )]
            tables = {
                str(row[0]) for row in self.db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name LIKE 'application_%'"
                )
            }
            for table in (
                "application_queue", "application_workspace", "application_control",
                "application_streams", "application_session_options",
                "application_activity",
            ):
                if table in tables:
                    session_ids.extend(str(row[0]) for row in self.db.execute(
                        f"SELECT DISTINCT session_id FROM {table}"
                    ))
            row = self.db.execute(
                "SELECT COUNT(DISTINCT session_id), COUNT(*) FROM turns "
                "WHERE role IN ('user','assistant')"
            ).fetchone()
            sessions = int(row[0]) if row else 0
            turns = int(row[1]) if row else 0
            if expected_counts is not None and (sessions, turns) != expected_counts:
                raise ValueError("Session history changed; review deletion again")
            self.db.execute("DELETE FROM turns")
            self.db.execute("DELETE FROM session_names")
            self.db.execute("DELETE FROM session_events")
            self.db.execute("DELETE FROM session_live")
            self.db.execute("DELETE FROM session_clients")
            self.db.execute("DELETE FROM session_archive")
            self.db.execute("DELETE FROM settings WHERE key GLOB 'session.runtime.*'")
            for session_id in set(session_ids):
                self._delete_application_session(session_id)
        return {"sessions": sessions, "turns": turns}

    def session_tail(self, session_id: str, limit: int = 8) -> list[dict]:
        with self._db_lock:
            rows = self.db.execute(
                "SELECT role, content FROM turns WHERE session_id=? "
                "AND role IN ('user','assistant') ORDER BY ts DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        out = []
        for role, content in reversed(rows):
            out.append({"role": role, "content": _decode_content(content)})
        return out

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        with self._db_lock:
            rows = self.db.execute(
                "SELECT session_id, MAX(ts), "
                "SUM(CASE WHEN role IN ('user','assistant') THEN 1 ELSE 0 END) FROM turns "
                "WHERE NOT EXISTS (SELECT 1 FROM session_archive AS a "
                "WHERE a.session_id=turns.session_id) "
                "GROUP BY session_id "
                "HAVING SUM(CASE WHEN role IN ('user','assistant') THEN 1 ELSE 0 END) > 0 "
                "ORDER BY MAX(ts) DESC LIMIT ?",
                (limit,),
            ).fetchall()
            preview_rows = {
                session_id: self.db.execute(
                    "SELECT role, content FROM turns WHERE session_id=? "
                    "AND role IN ('user','assistant') ORDER BY ts DESC LIMIT 1",
                    (session_id,),
                ).fetchone()
                for session_id, _ts, _count in rows
            }
            first_user_rows = {
                session_id: self.db.execute(
                    "SELECT content FROM turns WHERE session_id=? AND role='user' "
                    "ORDER BY ts, rowid LIMIT 1",
                    (session_id,),
                ).fetchone()
                for session_id, _ts, _count in rows
            }
            names = dict(self.db.execute("SELECT session_id, name FROM session_names"))
            active = {
                row[0]
                for row in self.db.execute(
                    "SELECT session_id FROM session_live "
                    "WHERE state='running' AND owner_lease_until>?",
                    (time.time(),),
                )
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
                    "title": names.get(session_id)
                    or (
                        " ".join(_as_text(_decode_content(first_user_rows[session_id][0])).split())[
                            :160
                        ]
                        if first_user_rows[session_id]
                        else "Untitled session"
                    ),
                    "active": session_id in active,
                }
            )
        return sessions

    def search_sessions(self, query: str, limit: int = 8) -> list[dict]:
        stopwords = {
            "a",
            "about",
            "all",
            "any",
            "did",
            "do",
            "from",
            "have",
            "i",
            "in",
            "it",
            "me",
            "my",
            "of",
            "other",
            "please",
            "remember",
            "remembered",
            "session",
            "sessions",
            "something",
            "tell",
            "that",
            "the",
            "this",
            "to",
            "what",
            "which",
            "you",
        }
        raw_terms = [t.casefold() for t in re.findall(r"[\w.-]+", query) if len(t) > 1]
        terms = [term for term in raw_terms if term not in stopwords]
        if not terms:
            terms = [
                re.sub(r"(?:ing|ed|s)$", "", term)
                for term in raw_terms
                if term not in {"other", "session", "sessions"}
            ]
            terms = [term for term in terms if len(term) > 2]
        if not terms:
            return []
        where = " OR ".join("lower(content) LIKE ?" for _ in terms)
        params = [f"%{term}%" for term in terms]
        with self._db_lock:
            rows = self.db.execute(
                f"SELECT session_id, ts, role, content FROM turns WHERE "
                f"role IN ('user','assistant') AND {where} "
                "ORDER BY ts DESC LIMIT ?",
                (*params, max(limit * 20, 100)),
            ).fetchall()
        ranked: list[tuple[int, float, dict]] = []
        for session_id, ts, role, content in rows:
            text = _as_text(_decode_content(content))
            folded = text.casefold()
            matches = sum(term in folded for term in terms)
            ranked.append(
                (
                    matches,
                    float(ts),
                    {
                        "session_id": session_id,
                        "ts": ts,
                        "date": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                        "role": role,
                        "content": text[:1000],
                    },
                )
            )
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in ranked[:limit]]
