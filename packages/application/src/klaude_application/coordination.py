"""SQLite admission, fencing and public replay for application-owned chat turns.

The existing transcript remains authoritative. Real terminal and headless turns
share this journal; compatibility test doubles retain the legacy Memory seam.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any, get_args

from klaude_core.memory import Memory
from klaude_core.session_runtime import decode

from .activity import ActivityState
from .chat_attachments import ChatAttachmentInput
from .contracts import EventKind, PublicEvent


class LeaseLost(RuntimeError):
    """The accepted worker can no longer publish or start an effect."""


class CursorExpired(ValueError):
    """A replay cursor cannot be used with this stream."""


@dataclass(frozen=True)
class Admission:
    request_id: str
    session_id: str
    turn_id: str
    state: str
    fence: int
    created: bool
    cursor: str = ""


@dataclass(frozen=True)
class TerminalCommit:
    message_cursor: str
    turn_cursor: str


@dataclass(frozen=True)
class QueuedTurn:
    id: str
    request_id: str
    session_id: str
    creator_id: str
    text: str
    scope: str
    revision: int
    state: str


class DurableTurns:
    """Short transactions on Memory's SQLite connection, never a second agent loop."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        with memory._db_lock, memory.db:
            memory.db.execute("BEGIN IMMEDIATE")
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_schema ("
                "id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER NOT NULL)"
            )
            schema = memory.db.execute(
                "SELECT version FROM application_schema WHERE id=1"
            ).fetchone()
            if schema is not None and int(schema[0]) > 3:
                raise RuntimeError("application schema is newer; upgrade Klaude before execution")
            if schema is None or int(schema[0]) < 3:
                active = memory.db.execute(
                    "SELECT 1 FROM session_live WHERE owner_client_id<>'' "
                    "AND owner_lease_until>? LIMIT 1", (time.time(),),
                ).fetchone()
                if active:
                    raise RuntimeError(
                        "active terminal worker must finish before application schema upgrade"
                    )
            columns = {row[1] for row in memory.db.execute("PRAGMA table_info(session_live)")}
            if "fence_generation" not in columns:
                try:
                    memory.db.execute(
                        "ALTER TABLE session_live ADD COLUMN fence_generation "
                        "INTEGER NOT NULL DEFAULT 0"
                    )
                except sqlite3.OperationalError:
                    if "fence_generation" not in {
                        row[1] for row in memory.db.execute("PRAGMA table_info(session_live)")
                    }:
                        raise
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_turns ("
                "request_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
                "turn_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL, "
                "state TEXT NOT NULL, fence INTEGER NOT NULL, "
                "accepted_at REAL NOT NULL, completed_at REAL NOT NULL DEFAULT 0)"
            )
            memory.db.execute(
                "CREATE INDEX IF NOT EXISTS application_turns_session "
                "ON application_turns(session_id, accepted_at)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_streams ("
                "session_id TEXT PRIMARY KEY, epoch TEXT NOT NULL, "
                "minimum_id INTEGER NOT NULL DEFAULT 0, high_water INTEGER NOT NULL DEFAULT 0)"
            )
            # A disposable read projection of public execution events, updated
            # in their transaction. No private arguments or model text enter it.
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_activity ("
                "session_id TEXT PRIMARY KEY, projection TEXT NOT NULL)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_control ("
                "session_id TEXT PRIMARY KEY, controller_id TEXT NOT NULL, "
                "epoch INTEGER NOT NULL, updated_at REAL NOT NULL)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_queue ("
                "id TEXT PRIMARY KEY, session_id TEXT NOT NULL, creator_id TEXT NOT NULL, "
                "request_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL, "
                "text TEXT NOT NULL, scope TEXT NOT NULL, runtime TEXT NOT NULL, "
                "workspace_revision INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1, "
                "state TEXT NOT NULL, priority INTEGER NOT NULL DEFAULT 0, "
                "created_at REAL NOT NULL, updated_at REAL NOT NULL)"
            )
            memory.db.execute(
                "CREATE INDEX IF NOT EXISTS application_queue_session "
                "ON application_queue(session_id, state, priority, created_at)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_workspace ("
                "session_id TEXT PRIMARY KEY, path TEXT NOT NULL, revision INTEGER NOT NULL, "
                "updated_at REAL NOT NULL)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_session_options ("
                "session_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
                "plan_mode INTEGER NOT NULL CHECK(plan_mode IN (0,1)), "
                "updated_at REAL NOT NULL)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_deleted_sessions ("
                "session_id TEXT PRIMARY KEY, deleted_at REAL NOT NULL)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_decisions ("
                "interaction_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
                "turn_id TEXT NOT NULL, control_epoch INTEGER NOT NULL, "
                "accepted_at REAL NOT NULL)"
            )
            memory.db.execute(
                "CREATE TABLE IF NOT EXISTS application_mutations ("
                "request_id TEXT PRIMARY KEY, operation TEXT NOT NULL, "
                "session_id TEXT NOT NULL, fingerprint TEXT NOT NULL, "
                "result TEXT NOT NULL, accepted_at REAL NOT NULL)"
            )
            for action in ("INSERT", "UPDATE", "DELETE"):
                trigger = f"application_fenced_session_{action.lower()}"
                if schema is None or int(schema[0]) < 3:
                    memory.db.execute(f"DROP TRIGGER IF EXISTS {trigger}")
                    memory.db.execute(
                        f"CREATE TRIGGER {trigger} BEFORE {action} ON session_live BEGIN "
                        "SELECT CASE WHEN klaude_writer_v3()!=1 THEN "
                        "RAISE(ABORT,'upgrade required for session execution') END; END"
                    )
                else:
                    installed = memory.db.execute(
                        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                        (trigger,),
                    ).fetchone()
                    if installed is None or "klaude_writer_v3" not in str(installed[0]):
                        raise RuntimeError("application fence trigger is missing or outdated")
            memory.db.execute(
                "INSERT INTO application_schema(id,version) VALUES (1,3) "
                "ON CONFLICT(id) DO UPDATE SET version=excluded.version"
            )

    @staticmethod
    def fingerprint(
        session_id: str, text: str, scope: str, runtime: dict, input_key: str = "",
    ) -> str:
        canonical = json.dumps(
            [session_id, text, scope, {k: runtime[k] for k in
             ("model", "mode", "effort", "definition", "credentials")}]
            + ([input_key] if input_key else []),
            ensure_ascii=False, separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def _receipt(self, request_id: str) -> tuple[Any, ...] | None:
        return self.memory.db.execute(
            "SELECT session_id, turn_id, fingerprint, state, fence FROM application_turns "
            "WHERE request_id=?", (request_id,),
        ).fetchone()

    @staticmethod
    def _mutation_hash(operation: str, session_id: str, arguments: object) -> str:
        payload = json.dumps([operation, session_id, arguments], sort_keys=True,
                             separators=(",", ":"), ensure_ascii=False)
        return sha256(payload.encode("utf-8")).hexdigest()

    def _mutation_replay(
        self, request_id: str | None, operation: str, session_id: str,
        arguments: object,
    ) -> Any | None:
        if request_id is None:
            return None
        if (not isinstance(request_id, str) or not 0 < len(request_id) <= 128
                or not request_id.isascii() or not request_id.isprintable()
                or any(character.isspace() for character in request_id)):
            raise ValueError("invalid request ID")
        row = self.memory.db.execute(
            "SELECT operation,session_id,fingerprint,result FROM application_mutations "
            "WHERE request_id=?", (request_id,),
        ).fetchone()
        if row is None:
            return None
        if row[:3] != (operation, session_id,
                        self._mutation_hash(operation, session_id, arguments)):
            raise ValueError("request ID already used with different input")
        return json.loads(row[3])

    def _mutation_record(
        self, request_id: str | None, operation: str, session_id: str,
        arguments: object, result: object,
    ) -> None:
        if request_id is not None:
            self.memory.db.execute(
                "INSERT INTO application_mutations "
                "(request_id,operation,session_id,fingerprint,result,accepted_at) "
                "VALUES (?,?,?,?,?,?)",
                (request_id, operation, session_id,
                 self._mutation_hash(operation, session_id, arguments),
                 json.dumps(result), time.time()),
            )

    def _assert_not_deleted(self, session_id: str) -> None:
        if self.memory.db.execute(
            "SELECT 1 FROM application_deleted_sessions WHERE session_id=?",
            (session_id,),
        ).fetchone():
            raise ValueError("session was deleted; request is gone")

    def _recover_legacy_expired(self, session_id: str) -> bool:
        """Let the existing transcript recovery preserve pre-journal partials."""
        memory = self.memory
        with memory._db_lock:
            live = memory.db.execute(
                "SELECT turn_id,owner_lease_until,state FROM session_live "
                "WHERE session_id=?", (session_id,),
            ).fetchone()
            legacy = bool(
                live and live[2] == "running" and float(live[1]) <= time.time()
                and not memory.db.execute(
                    "SELECT 1 FROM application_turns WHERE session_id=? AND turn_id=? "
                    "AND state='running'", (session_id, live[0]),
                ).fetchone()
            )
        if legacy:
            memory.session_snapshot(session_id)
        return legacy

    def admit(
        self, *, request_id: str, session_id: str, turn_id: str,
        worker_id: str, text: str, scope: str, runtime: dict,
        controller_id: str | None = None,
        input_key: str = "",
        attachments: ChatAttachmentInput | None = None,
    ) -> Admission:
        if decode(runtime) is None:
            raise ValueError("explicit model/runtime selection required")
        fingerprint = self.fingerprint(session_id, text, scope, runtime, input_key)
        memory = self.memory
        self._recover_legacy_expired(session_id)
        now = time.time()
        with memory._db_lock:
            memory.db.execute("BEGIN IMMEDIATE")
            try:
                self._assert_not_deleted(session_id)
                live = memory.db.execute(
                    "SELECT owner_client_id, owner_lease_until, fence_generation, "
                    "turn_id, partial, state FROM session_live WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                if live and live[0] and float(live[1]) <= now:
                    self._interrupt_expired(
                        session_id, str(live[0]), str(live[3]), str(live[4]), now
                    )
                    memory.db.execute(
                        "UPDATE session_live SET owner_client_id='', owner_lease_until=0, "
                        "turn_id='', state='interrupted', partial='', activity='ready', "
                        "revision=revision+1, updated_at=? WHERE session_id=?",
                        (now, session_id),
                    )
                previous = self._receipt(request_id)
                if previous is not None:
                    if previous[0] != session_id or previous[2] != fingerprint:
                        raise ValueError("request ID already used with different input")
                    admission = Admission(
                        request_id, session_id, str(previous[1]), str(previous[3]),
                        int(previous[4]), False,
                    )
                    memory.db.commit()
                    return admission
                if memory.db.execute(
                    "SELECT 1 FROM session_archive WHERE session_id=?", (session_id,)
                ).fetchone():
                    raise RuntimeError("session is archived")
                live = memory.db.execute(
                    "SELECT owner_client_id, owner_lease_until, fence_generation, state "
                    "FROM session_live WHERE session_id=?", (session_id,),
                ).fetchone()
                if live and live[3] == "interrupted":
                    memory.db.commit()
                    raise RuntimeError(
                        "previous turn outcome unknown; reconcile before new work"
                    )
                if live and live[0] and float(live[1]) > now:
                    raise RuntimeError("session already has an active worker")
                fence = int(live[2]) + 1 if live else 1
                memory.db.execute(
                    "INSERT INTO session_live "
                    "(session_id, revision, owner_client_id, owner_lease_until, turn_id, "
                    "state, turn_started_at, activity, partial, updated_at, fence_generation) "
                    "VALUES (?,1,?,?,?,?,?,'thinking','',?,?) "
                    "ON CONFLICT(session_id) DO UPDATE SET "
                    "revision=session_live.revision+1, owner_client_id=excluded.owner_client_id, "
                    "owner_lease_until=excluded.owner_lease_until, turn_id=excluded.turn_id, "
                    "state='running', turn_started_at=excluded.turn_started_at, "
                    "activity='thinking', partial='', updated_at=excluded.updated_at, "
                    "fence_generation=excluded.fence_generation",
                    (session_id, worker_id, now + 60, turn_id, "running", now, now, fence),
                )
                memory.db.execute(
                    "INSERT INTO application_turns "
                    "(request_id, session_id, turn_id, fingerprint, state, fence, accepted_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (request_id, session_id, turn_id, fingerprint, "running", fence, now),
                )
                if controller_id is not None:
                    memory.db.execute(
                        "INSERT INTO application_control "
                        "(session_id,controller_id,epoch,updated_at) VALUES (?,?,1,?) "
                        "ON CONFLICT(session_id) DO UPDATE SET "
                        "controller_id=excluded.controller_id, "
                        "epoch=application_control.epoch+1, "
                        "updated_at=excluded.updated_at",
                        (session_id, controller_id, now),
                    )
                memory.db.execute(
                    "INSERT INTO turns(session_id, ts, role, content, model_content, "
                    "attachments, attachment_previews) VALUES (?,?,?,?,NULL,?,?)",
                    (session_id, now, "user", json.dumps(text, ensure_ascii=False),
                     json.dumps([file.public() for file in attachments.files])
                     if attachments else None,
                     json.dumps([base64.b64encode(file.thumbnail).decode("ascii")
                                 for file in attachments.files]) if attachments else None),
                )
                memory._store_session_runtime(session_id, runtime)
                event_id = self._append(session_id, turn_id, worker_id, "turn.accepted", {})
                epoch = memory.db.execute(
                    "SELECT epoch FROM application_streams WHERE session_id=?", (session_id,),
                ).fetchone()[0]
                memory.db.commit()
                return Admission(
                    request_id, session_id, turn_id, "running", fence, True,
                    f"{epoch}:{event_id}",
                )
            except BaseException:
                memory.db.rollback()
                raise

    def admit_claimed(
        self, *, request_id: str, session_id: str, turn_id: str,
        worker_id: str, fence: int, text: str, scope: str, runtime: dict,
        model_content: object | None = None,
    ) -> Admission:
        """Finish a terminal lease reservation before the agent can execute."""
        if decode(runtime) is None:
            raise ValueError("explicit model/runtime selection required")
        fingerprint = self.fingerprint(session_id, text, scope, runtime)
        memory = self.memory
        now = time.time()
        with memory._db_lock:
            memory.db.execute("BEGIN IMMEDIATE")
            try:
                self._assert_not_deleted(session_id)
                self._assert_fence(session_id, turn_id, worker_id, fence)
                if self._receipt(request_id) is not None:
                    raise ValueError("request ID already used")
                memory.db.execute(
                    "INSERT INTO application_turns "
                    "(request_id,session_id,turn_id,fingerprint,state,fence,accepted_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (request_id, session_id, turn_id, fingerprint, "running", fence, now),
                )
                memory.db.execute(
                    "INSERT INTO turns(session_id,ts,role,content,model_content) "
                    "VALUES (?,?,?,?,?)",
                    (session_id, now, "user", json.dumps(text, ensure_ascii=False),
                     json.dumps(model_content, ensure_ascii=False)
                     if model_content is not None else None),
                )
                memory.db.execute(
                    "INSERT INTO session_events "
                    "(session_id,turn_id,client_id,ts,kind,payload) "
                    "VALUES (?,?,?,?,?,?)",
                    (session_id, turn_id, worker_id, now, "user_started",
                     json.dumps({"text": text}, ensure_ascii=False)),
                )
                memory._store_session_runtime(session_id, runtime)
                event_id = self._append(session_id, turn_id, worker_id, "turn.accepted", {})
                epoch = memory.db.execute(
                    "SELECT epoch FROM application_streams WHERE session_id=?", (session_id,),
                ).fetchone()[0]
                memory.db.commit()
                return Admission(
                    request_id, session_id, turn_id, "running", fence, True,
                    f"{epoch}:{event_id}",
                )
            except BaseException:
                memory.db.rollback()
                raise

    def control(self, session_id: str) -> tuple[str, int] | None:
        with self.memory._db_lock:
            row = self.memory.db.execute(
                "SELECT controller_id,epoch FROM application_control WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return (str(row[0]), int(row[1])) if row else None

    def save_model_input(
        self, *, request_id: str, session_id: str, turn_id: str, worker_id: str,
        fence: int, model_content: dict[str, Any],
    ) -> None:
        """Persist prepared private input only while the admitted worker is fenced."""
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_fence(session_id, turn_id, worker_id, fence)
            result = self.memory.db.execute(
                "UPDATE turns SET model_content=? WHERE session_id=? AND role='user' "
                "AND ts=(SELECT accepted_at FROM application_turns WHERE request_id=? "
                "AND session_id=? AND turn_id=?)",
                (json.dumps(model_content, ensure_ascii=False), session_id,
                 request_id, session_id, turn_id),
            )
            if result.rowcount != 1:
                raise LeaseLost("Admitted user message changed")

    def claim_control(
        self, session_id: str, controller_id: str, *, expected_epoch: int,
        request_id: str | None = None,
    ) -> int:
        """Trusted same-profile caller takes control without changing worker lease."""
        if not controller_id or len(controller_id) > 128:
            raise ValueError("invalid controller identity")
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_not_deleted(session_id)
            arguments = [controller_id, expected_epoch]
            replay = self._mutation_replay(request_id, "control", session_id, arguments)
            if replay is not None:
                return int(replay)
            cursor = self.memory.db.execute(
                "UPDATE application_control SET controller_id=?, epoch=epoch+1, "
                "updated_at=? WHERE session_id=? AND epoch=?",
                (controller_id, time.time(), session_id, expected_epoch),
            )
            if cursor.rowcount != 1:
                raise ValueError("stale control revision")
            result = expected_epoch + 1
            self._mutation_record(request_id, "control", session_id, arguments, result)
            return result

    def controls(self, session_id: str, controller_id: str, epoch: int) -> bool:
        return self.control(session_id) == (controller_id, epoch)

    def record_decision(
        self, *, session_id: str, turn_id: str, worker_id: str, fence: int,
        controller_id: str, control_epoch: int, interaction_id: str,
    ) -> bool:
        """Serialize decision acceptance with a competing control takeover."""
        memory = self.memory
        with memory._db_lock:
            memory.db.execute("BEGIN IMMEDIATE")
            try:
                self._assert_fence(session_id, turn_id, worker_id, fence)
                row = memory.db.execute(
                    "SELECT controller_id,epoch FROM application_control "
                    "WHERE session_id=?", (session_id,),
                ).fetchone()
                if row != (controller_id, control_epoch):
                    memory.db.rollback()
                    return False
                cursor = memory.db.execute(
                    "INSERT OR IGNORE INTO application_decisions "
                    "(interaction_id,session_id,turn_id,control_epoch,accepted_at) "
                    "VALUES (?,?,?,?,?)",
                    (interaction_id, session_id, turn_id, control_epoch, time.time()),
                )
                memory.db.commit()
                return cursor.rowcount == 1
            except BaseException:
                memory.db.rollback()
                raise

    def workspace(self, session_id: str) -> tuple[str, int] | None:
        with self.memory._db_lock:
            row = self.memory.db.execute(
                "SELECT path,revision FROM application_workspace WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return (str(row[0]), int(row[1])) if row else None

    def session_options(self, session_id: str) -> tuple[int, bool]:
        with self.memory._db_lock:
            row = self.memory.db.execute(
                "SELECT revision,plan_mode FROM application_session_options WHERE session_id=?",
                (session_id,),
            ).fetchone()
        return (int(row[0]), bool(row[1])) if row else (0, False)

    def set_plan_mode(
        self, session_id: str, enabled: bool, *, expected_revision: int,
        request_id: str | None = None,
    ) -> int:
        if type(enabled) is not bool:
            raise ValueError("plan mode must be boolean")
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_not_deleted(session_id)
            arguments = [enabled, expected_revision]
            replay = self._mutation_replay(request_id, "plan", session_id, arguments)
            if replay is not None:
                return int(replay)
            live = self.memory.db.execute(
                "SELECT owner_client_id,owner_lease_until FROM session_live "
                "WHERE session_id=?", (session_id,),
            ).fetchone()
            if live and live[0] and float(live[1]) > time.time():
                raise RuntimeError("session already has an active worker")
            row = self.memory.db.execute(
                "SELECT revision FROM application_session_options WHERE session_id=?",
                (session_id,),
            ).fetchone()
            current = int(row[0]) if row else 0
            if current != expected_revision:
                raise ValueError("stale settings revision")
            revision = current + 1
            self.memory.db.execute(
                "INSERT INTO application_session_options "
                "(session_id,revision,plan_mode,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "revision=excluded.revision,plan_mode=excluded.plan_mode,"
                "updated_at=excluded.updated_at",
                (session_id, revision, int(enabled), time.time()),
            )
            self._append(
                session_id, "", "application", "settings.changed",
                {"status": "plan", "revision": revision},
            )
            self._mutation_record(request_id, "plan", session_id, arguments, revision)
            return revision

    def set_runtime_choice(
        self, session_id: str, runtime: dict[str, Any], previous_runtime: dict[str, Any],
        *, expected_revision: int, request_id: str | None = None,
    ) -> int:
        """Persist an idle model/mode choice with a session settings revision."""
        from klaude_core.session_runtime import decode

        selected = decode(runtime)
        previous = decode(previous_runtime)
        if selected is None or previous is None:
            raise ValueError("invalid session runtime")
        fields = ("model", "mode", "effort", "definition", "credentials")
        arguments = [expected_revision, *[selected[key] for key in fields]]
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_not_deleted(session_id)
            replay = self._mutation_replay(request_id, "runtime", session_id, arguments)
            if replay is not None:
                return int(replay)
            live = self.memory.db.execute(
                "SELECT owner_client_id,owner_lease_until FROM session_live "
                "WHERE session_id=?", (session_id,),
            ).fetchone()
            if live and live[0] and float(live[1]) > time.time():
                raise RuntimeError("session already has an active worker")
            row = self.memory.db.execute(
                "SELECT revision,plan_mode FROM application_session_options "
                "WHERE session_id=?", (session_id,),
            ).fetchone()
            current = int(row[0]) if row else 0
            if current != expected_revision:
                raise ValueError("stale settings revision")
            saved = self.memory.session_runtime(session_id)
            if saved is not None and any(saved[key] != previous[key] for key in fields):
                raise ValueError("session runtime changed")
            if saved is not None:
                selected["at"] = max(float(selected["at"]), float(saved["at"]) + 0.000001)
            revision = current + 1
            self.memory._store_session_runtime(session_id, selected)
            self.memory.db.execute(
                "INSERT INTO application_session_options "
                "(session_id,revision,plan_mode,updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET "
                "revision=excluded.revision,updated_at=excluded.updated_at",
                (session_id, revision, int(row[1]) if row else 0, time.time()),
            )
            self._append(
                session_id, "", "application", "settings.changed",
                {"status": "runtime", "revision": revision},
            )
            self._mutation_record(request_id, "runtime", session_id, arguments, revision)
            return revision

    def bind_workspace(
        self, session_id: str, path: str, *, expected_revision: int,
        request_id: str | None = None,
    ) -> int:
        """CAS a resolved workspace identity at an idle session boundary."""
        if not path or len(path) > 4096 or not path.startswith("/"):
            raise ValueError("workspace path must be absolute")
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_not_deleted(session_id)
            arguments = [path, expected_revision]
            replay = self._mutation_replay(request_id, "workspace", session_id, arguments)
            if replay is not None:
                return int(replay)
            live = self.memory.db.execute(
                "SELECT owner_client_id,owner_lease_until FROM session_live "
                "WHERE session_id=?", (session_id,),
            ).fetchone()
            if live and live[0] and float(live[1]) > time.time():
                raise RuntimeError("session already has an active worker")
            row = self.memory.db.execute(
                "SELECT revision FROM application_workspace WHERE session_id=?",
                (session_id,),
            ).fetchone()
            current = int(row[0]) if row else 0
            if current != expected_revision:
                raise ValueError("stale workspace revision")
            revision = current + 1
            self.memory.db.execute(
                "INSERT INTO application_workspace(session_id,path,revision,updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(session_id) DO UPDATE SET "
                "path=excluded.path,revision=excluded.revision,updated_at=excluded.updated_at",
                (session_id, path, revision, time.time()),
            )
            self._mutation_record(request_id, "workspace", session_id, arguments, revision)
            return revision

    def enqueue(
        self, *, session_id: str, creator_id: str, request_id: str,
        text: str, scope: str, runtime: dict, priority: bool = False,
        required_control_epoch: int | None = None,
    ) -> QueuedTurn:
        if decode(runtime) is None or not text.strip() or len(text) > 65_536:
            raise ValueError("invalid queued turn")
        fingerprint = self.fingerprint(session_id, text, scope, runtime)
        with self.memory._db_lock:
            self.memory.db.execute("BEGIN IMMEDIATE")
            try:
                self._assert_not_deleted(session_id)
                if required_control_epoch is not None:
                    control = self.memory.db.execute(
                        "SELECT controller_id,epoch FROM application_control "
                        "WHERE session_id=?", (session_id,),
                    ).fetchone()
                    if control != (creator_id, required_control_epoch):
                        raise ValueError("stale session control")
                prior = self.memory.db.execute(
                    "SELECT id,session_id,creator_id,fingerprint,text,scope,revision,state "
                    "FROM application_queue WHERE request_id=?", (request_id,),
                ).fetchone()
                if prior:
                    if prior[1] != session_id or prior[2] != creator_id or prior[3] != fingerprint:
                        raise ValueError("request ID already used with different input")
                    self.memory.db.commit()
                    return QueuedTurn(
                        str(prior[0]), request_id, session_id, creator_id,
                        str(prior[4]), str(prior[5]), int(prior[6]), str(prior[7]),
                    )
                if self.memory.db.execute(
                    "SELECT 1 FROM session_archive WHERE session_id=?", (session_id,)
                ).fetchone():
                    raise RuntimeError("session is archived")
                count = self.memory.db.execute(
                    "SELECT COUNT(*) FROM application_queue WHERE session_id=? AND "
                    "state IN ('queued','paused','needs_review','starting')",
                    (session_id,),
                ).fetchone()[0]
                if int(count) >= 20:
                    raise RuntimeError("session queue is full")
                workspace = self.memory.db.execute(
                    "SELECT revision FROM application_workspace WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                identity = uuid.uuid4().hex
                now = time.time()
                self.memory.db.execute(
                    "INSERT INTO application_queue "
                    "(id,session_id,creator_id,request_id,fingerprint,text,scope,runtime,"
                    "workspace_revision,state,priority,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (identity, session_id, creator_id, request_id, fingerprint,
                     text, scope, json.dumps(runtime), int(workspace[0]) if workspace else 0,
                     "queued", 1 if priority else 0, now, now),
                )
                self._append(
                    session_id, identity, creator_id, "queue.changed", {"status": "queued"}
                )
                self.memory.db.commit()
                return QueuedTurn(identity, request_id, session_id, creator_id,
                                  text, scope, 1, "queued")
            except BaseException:
                self.memory.db.rollback()
                raise

    def queue(
        self, session_id: str, viewer_id: str, *, include_submitted: bool = True,
    ) -> list[dict[str, Any]]:
        """Only a creator sees its queued prompt; observers receive metadata."""
        with self.memory._db_lock:
            rows = self.memory.db.execute(
                "SELECT id,creator_id,request_id,text,scope,revision,state,priority "
                "FROM application_queue WHERE session_id=? AND state!='removed' "
                "AND (? OR state!='submitted') "
                "ORDER BY priority DESC,created_at,id LIMIT 100",
                (session_id, include_submitted),
            ).fetchall()
        return [
            {"id": row[0], "mine": row[1] == viewer_id,
             "request_id": row[2] if row[1] == viewer_id else "",
             "text": row[3] if row[1] == viewer_id else "",
             "scope": row[4] if row[1] == viewer_id else "",
             "revision": int(row[5]), "state": row[6], "priority": bool(row[7])}
            for row in rows
        ]

    def remove_queue_item(
        self, session_id: str, item_id: str, actor_id: str, *, expected_revision: int,
        request_id: str | None = None,
    ) -> bool:
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_not_deleted(session_id)
            arguments = [item_id, actor_id, expected_revision]
            replay = self._mutation_replay(request_id, "queue.remove", session_id, arguments)
            if replay is not None:
                return bool(replay)
            cursor = self.memory.db.execute(
                "UPDATE application_queue SET state='removed', revision=revision+1, "
                "updated_at=? WHERE session_id=? AND id=? AND creator_id=? "
                "AND revision=? AND state IN ('queued','paused','needs_review')",
                (time.time(), session_id, item_id, actor_id, expected_revision),
            )
            if cursor.rowcount:
                self._append(session_id, item_id, actor_id, "queue.changed", {"status": "removed"})
            result = cursor.rowcount == 1
            self._mutation_record(request_id, "queue.remove", session_id, arguments, result)
            return result

    def recover_queue(self, session_id: str) -> int:
        """Explicit host restart step: freeze unstarted work, never auto-replay."""
        with self.memory._db_lock, self.memory.db:
            cursor = self.memory.db.execute(
                "UPDATE application_queue SET state='paused', revision=revision+1, "
                "updated_at=? WHERE session_id=? AND state IN ('queued','starting')",
                (time.time(), session_id),
            )
            if cursor.rowcount:
                self._append(session_id, "", "application", "queue.changed", {"status": "paused"})
            return cursor.rowcount

    def recover_session(self, session_id: str) -> bool:
        """Explicit owner-start reconciliation; never rerun accepted work."""
        memory = self.memory
        legacy_recovered = self._recover_legacy_expired(session_id)
        now = time.time()
        with memory._db_lock:
            memory.db.execute("BEGIN IMMEDIATE")
            try:
                live = memory.db.execute(
                    "SELECT owner_client_id,owner_lease_until,turn_id,partial "
                    "FROM session_live WHERE session_id=?", (session_id,),
                ).fetchone()
                if live and live[0] and float(live[1]) > now:
                    memory.db.commit()
                    return False
                if live and live[0]:
                    self._interrupt_expired(
                        session_id, str(live[0]), str(live[2]), str(live[3]), now,
                    )
                    memory.db.execute(
                        "UPDATE session_live SET owner_client_id='', owner_lease_until=0, "
                        "turn_id='', state='interrupted', partial='', activity='ready', "
                        "revision=revision+1,updated_at=? WHERE session_id=?",
                        (now, session_id),
                    )
                paused = memory.db.execute(
                    "UPDATE application_queue SET state='paused',revision=revision+1, "
                    "updated_at=? WHERE session_id=? AND state IN ('queued','starting')",
                    (now, session_id),
                ).rowcount
                if paused:
                    self._append(
                        session_id, "", "application", "queue.changed", {"status": "paused"}
                    )
                memory.db.commit()
                return bool(legacy_recovered or (live and live[0]) or paused)
            except BaseException:
                memory.db.rollback()
                raise

    def resume_queue_item(
        self, session_id: str, item_id: str, actor_id: str, *, expected_revision: int,
        request_id: str | None = None,
    ) -> bool:
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_not_deleted(session_id)
            arguments = [item_id, actor_id, expected_revision]
            replay = self._mutation_replay(request_id, "queue.resume", session_id, arguments)
            if replay is not None:
                return bool(replay)
            row = self.memory.db.execute(
                "SELECT creator_id,runtime,workspace_revision FROM application_queue "
                "WHERE session_id=? AND id=? AND state IN ('paused','needs_review') "
                "AND revision=?", (session_id, item_id, expected_revision),
            ).fetchone()
            if row is None or row[0] != actor_id:
                self._mutation_record(request_id, "queue.resume", session_id, arguments, False)
                return False
            workspace = self.memory.db.execute(
                "SELECT revision FROM application_workspace WHERE session_id=?",
                (session_id,),
            ).fetchone()
            saved_runtime = self.memory.session_runtime(session_id)
            if (
                (int(workspace[0]) if workspace else 0) != int(row[2])
                or saved_runtime is None
                or not self._same_runtime(json.loads(row[1]), saved_runtime)
            ):
                self.memory.db.execute(
                    "UPDATE application_queue SET state='needs_review',revision=revision+1 "
                    "WHERE id=?", (item_id,),
                )
                self._append(
                    session_id, item_id, actor_id, "queue.changed",
                    {"status": "needs_review"},
                )
                self._mutation_record(request_id, "queue.resume", session_id, arguments, False)
                return False
            self.memory.db.execute(
                "UPDATE application_queue SET state='queued',revision=revision+1, "
                "updated_at=? WHERE id=?", (time.time(), item_id),
            )
            self._append(session_id, item_id, actor_id, "queue.changed", {"status": "queued"})
            self._mutation_record(request_id, "queue.resume", session_id, arguments, True)
            return True

    @staticmethod
    def _same_runtime(left: dict, right: dict) -> bool:
        return all(left.get(key) == right.get(key) for key in
                   ("model", "mode", "effort", "definition", "credentials"))

    def claim_next_queued(self, session_id: str, runtime: dict) -> QueuedTurn | None:
        """Reserve the next queue item; a crash leaves a reviewable reservation."""
        with self.memory._db_lock:
            self.memory.db.execute("BEGIN IMMEDIATE")
            try:
                live = self.memory.db.execute(
                    "SELECT owner_client_id,owner_lease_until FROM session_live "
                    "WHERE session_id=?", (session_id,),
                ).fetchone()
                if live and live[0] and float(live[1]) > time.time():
                    self.memory.db.commit()
                    return None
                workspace = self.memory.db.execute(
                    "SELECT revision FROM application_workspace WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                workspace_revision = int(workspace[0]) if workspace else 0
                rows = self.memory.db.execute(
                    "SELECT id,request_id,creator_id,text,scope,runtime,"
                    "workspace_revision,revision "
                    "FROM application_queue WHERE session_id=? AND state='queued' "
                    "ORDER BY priority DESC,created_at,id LIMIT 20", (session_id,),
                ).fetchall()
                changed = False
                for row in rows:
                    if (int(row[6]) != workspace_revision
                            or not self._same_runtime(json.loads(row[5]), runtime)):
                        self.memory.db.execute(
                            "UPDATE application_queue SET state='needs_review', "
                            "revision=revision+1,updated_at=? WHERE id=?",
                            (time.time(), row[0]),
                        )
                        changed = True
                        continue
                    self.memory.db.execute(
                        "UPDATE application_queue SET state='starting',revision=revision+1, "
                        "updated_at=? WHERE id=?", (time.time(), row[0]),
                    )
                    if changed:
                        self._append(
                            session_id, "", "application", "queue.changed",
                            {"status": "needs_review"},
                        )
                    self.memory.db.commit()
                    return QueuedTurn(str(row[0]), str(row[1]), session_id,
                                      str(row[2]), str(row[3]), str(row[4]),
                                      int(row[7]) + 1, "starting")
                if changed:
                    self._append(
                        session_id, "", "application", "queue.changed",
                        {"status": "needs_review"},
                    )
                self.memory.db.commit()
                return None
            except BaseException:
                self.memory.db.rollback()
                raise

    def mark_queue_submitted(self, item: QueuedTurn) -> None:
        with self.memory._db_lock, self.memory.db:
            receipt = self._receipt(item.request_id)
            if receipt is None or receipt[0] != item.session_id:
                raise RuntimeError("queued turn was not admitted")
            updated = self.memory.db.execute(
                "UPDATE application_queue SET state='submitted',revision=revision+1, "
                "updated_at=? WHERE id=? AND request_id=? "
                "AND state IN ('starting','paused')",
                (time.time(), item.id, item.request_id),
            )
            if updated.rowcount != 1:
                raise RuntimeError("queued turn state changed after admission")
            self._append(
                item.session_id, item.id, item.creator_id, "queue.changed",
                {"status": "submitted"},
            )

    def pause_queue_item(self, item: QueuedTurn) -> None:
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute(
                "UPDATE application_queue SET state='paused',revision=revision+1, "
                "updated_at=? WHERE id=? AND revision=? AND state='starting'",
                (time.time(), item.id, item.revision),
            )

    def reconcile_interrupted(
        self, session_id: str, expected_fence: int, *, request_id: str | None = None,
    ) -> bool:
        """Explicitly unblock a recovered session after the caller reviews effects."""
        with self.memory._db_lock, self.memory.db:
            self.memory.db.execute("BEGIN IMMEDIATE")
            self._assert_not_deleted(session_id)
            arguments = [expected_fence]
            replay = self._mutation_replay(request_id, "reconcile", session_id, arguments)
            if replay is not None:
                return bool(replay)
            cursor = self.memory.db.execute(
                "UPDATE session_live SET state='idle', revision=revision+1, "
                "updated_at=? WHERE session_id=? AND state='interrupted' "
                "AND owner_client_id='' AND fence_generation=?",
                (time.time(), session_id, expected_fence),
            )
            result = cursor.rowcount == 1
            self._mutation_record(request_id, "reconcile", session_id, arguments, result)
            return result

    def _interrupt_expired(
        self, session_id: str, worker_id: str, live_turn_id: str,
        partial: str, now: float,
    ) -> None:
        memory = self.memory
        rows = memory.db.execute(
            "SELECT turn_id FROM application_turns WHERE session_id=? AND state='running'",
            (session_id,),
        ).fetchall()
        for (turn_id,) in rows:
            if turn_id == live_turn_id and partial:
                memory.db.execute(
                    "INSERT INTO turns(session_id,ts,role,content,model_content) "
                    "VALUES (?,?,?,?,NULL)",
                    (session_id, now, "assistant", json.dumps(partial, ensure_ascii=False)),
                )
            memory.db.execute(
                "UPDATE application_turns SET state='interrupted', completed_at=? "
                "WHERE turn_id=? AND state='running'", (now, turn_id),
            )
            self._append(session_id, str(turn_id), worker_id, "turn.interrupted", {})

    def _append(
        self, session_id: str, turn_id: str, worker_id: str,
        kind: str, payload: dict[str, Any],
    ) -> int:
        memory = self.memory
        if kind.startswith(("turn.", "tool.", "approval.", "user_input.", "message.")) or (
            kind == "activity.changed"
        ):
            row = memory.db.execute(
                "SELECT projection FROM application_activity WHERE session_id=?", (session_id,),
            ).fetchone()
            activity = ActivityState(**json.loads(row[0])) if row else ActivityState()
            activity.observe(turn_id, kind, **{k: v for k, v in payload.items() if k != "kind"})
            memory.db.execute(
                "INSERT INTO application_activity(session_id,projection) VALUES (?,?) "
                "ON CONFLICT(session_id) DO UPDATE SET projection=excluded.projection",
                (session_id, json.dumps(asdict(activity))),
            )
            memory.db.execute(
                "UPDATE session_live SET activity=?, revision=revision+1 "
                "WHERE session_id=? AND turn_id=?",
                (activity.label or activity.lifecycle.title(), session_id, turn_id),
            )
            payload = {**payload, "current_activity": activity.public()}
        memory.db.execute(
            "INSERT OR IGNORE INTO application_streams(session_id, epoch) VALUES (?,?)",
            (session_id, uuid.uuid4().hex),
        )
        cursor = memory.db.execute(
            "INSERT INTO session_events(session_id,turn_id,client_id,ts,kind,payload) "
            "VALUES (?,?,?,?,?,?)",
            (session_id, turn_id, worker_id, time.time(), "application.public.v1",
             json.dumps({"kind": kind, **payload}, ensure_ascii=False)),
        )
        event_id = int(cursor.lastrowid or 0)
        memory.db.execute(
            "UPDATE application_streams SET high_water=? WHERE session_id=?",
            (event_id, session_id),
        )
        return event_id

    def _assert_fence(self, session_id: str, turn_id: str, worker_id: str, fence: int) -> None:
        row = self.memory.db.execute(
            "SELECT 1 FROM session_live WHERE session_id=? AND turn_id=? "
            "AND owner_client_id=? AND fence_generation=? AND state='running' "
            "AND owner_lease_until>?",
            (session_id, turn_id, worker_id, fence, time.time()),
        ).fetchone()
        if row is None:
            raise LeaseLost("application turn lost its execution lease")

    def assert_fence(self, session_id: str, turn_id: str, worker_id: str, fence: int) -> None:
        with self.memory._db_lock:
            self._assert_fence(session_id, turn_id, worker_id, fence)

    def mark_started(self, session_id: str, turn_id: str, worker_id: str, fence: int) -> str:
        with self.memory._db_lock, self.memory.db:
            self._assert_fence(session_id, turn_id, worker_id, fence)
            event_id = self._append(session_id, turn_id, worker_id, "turn.started", {})
            epoch = self.memory.db.execute(
                "SELECT epoch FROM application_streams WHERE session_id=?", (session_id,),
            ).fetchone()[0]
            return f"{epoch}:{event_id}"

    def append_public(
        self, session_id: str, turn_id: str, worker_id: str,
        fence: int, event: PublicEvent,
    ) -> str:
        fields = {
            "text": event.text, "tool": event.tool,
            "execution_id": event.execution_id, "interaction_id": event.interaction_id,
            "message_id": event.message_id, "offset": event.offset,
            "executed": event.executed, "status": event.status,
            "activity": event.activity,
            "sequence": event.sequence,
        }
        with self.memory._db_lock, self.memory.db:
            self._assert_fence(session_id, turn_id, worker_id, fence)
            event_id = self._append(session_id, turn_id, worker_id, event.kind, fields)
            if event.kind == "message.delta" and event.text:
                self.memory.db.execute(
                    "UPDATE session_live SET partial=substr(partial || ?, -262144), "
                    "revision=revision+1, updated_at=? WHERE session_id=?",
                    (event.text, time.time(), session_id),
                )
            epoch = self.memory.db.execute(
                "SELECT epoch FROM application_streams WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            return f"{epoch}:{event_id}"

    def finish(
        self, *, request_id: str, session_id: str, turn_id: str,
        worker_id: str, fence: int, state: str, assistant: str | None,
        model_content: object | None = None,
        message_id: str = "",
        assistant_messages: list[tuple[str, object | None]] | None = None,
        legacy_completion: dict[str, Any] | None = None,
    ) -> TerminalCommit:
        if state not in {"completed", "partial", "failed", "cancelled"}:
            raise ValueError("invalid terminal state")
        memory = self.memory
        with memory._db_lock, memory.db:
            self._assert_fence(session_id, turn_id, worker_id, fence)
            messages = assistant_messages if assistant_messages is not None else (
                [(assistant, model_content)] if assistant is not None else []
            )
            for content, private in messages:
                memory.db.execute(
                    "INSERT INTO turns(session_id,ts,role,content,model_content) "
                    "VALUES (?,?,?,?,?)",
                    (session_id, time.time(), "assistant",
                     json.dumps(content, ensure_ascii=False),
                     json.dumps(private, ensure_ascii=False) if private is not None else None),
                )
            memory.db.execute(
                "UPDATE application_turns SET state=?, completed_at=? "
                "WHERE request_id=? AND turn_id=? AND fence=? AND state='running'",
                (state, time.time(), request_id, turn_id, fence),
            )
            message_event_id = 0
            for index, (content, _) in enumerate(messages):
                message_event_id = self._append(
                    session_id, turn_id, worker_id, "message.completed",
                    {"text": content[:65_536],
                     "message_id": message_id or f"{turn_id}:{index}", "offset": 0,
                     "status": "truncated" if len(content) > 65_536 else "complete"},
                )
            event_id = self._append(session_id, turn_id, worker_id, f"turn.{state}", {})
            if legacy_completion is not None:
                memory.db.execute(
                    "INSERT INTO session_events "
                    "(session_id,turn_id,client_id,ts,kind,payload) "
                    "VALUES (?,?,?,?,?,?)",
                    (session_id, turn_id, worker_id, time.time(), "turn_done",
                     json.dumps(legacy_completion, ensure_ascii=False)),
                )
            memory.db.execute(
                "UPDATE session_live SET revision=revision+1, owner_client_id='', "
                "owner_lease_until=0, turn_id='', state=?, turn_started_at=0, "
                "activity=?, partial='', updated_at=? WHERE session_id=?",
                ("failed" if state == "failed" else "idle",
                 "Done" if state == "completed" else "Error" if state in {"failed", "partial"}
                 else state.title(), time.time(), session_id),
            )
            epoch = memory.db.execute(
                "SELECT epoch FROM application_streams WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
            return TerminalCommit(
                f"{epoch}:{message_event_id}" if message_event_id else "",
                f"{epoch}:{event_id}",
            )

    def receipt(self, request_id: str) -> Admission | None:
        with self.memory._db_lock:
            row = self._receipt(request_id)
            if row is None:
                return None
            return Admission(request_id, str(row[0]), str(row[1]), str(row[3]), int(row[4]), False)

    def snapshot(self, session_id: str, viewer_id: str = "") -> dict[str, Any]:
        """Read public history, partial and replay watermark in one transaction."""
        memory = self.memory
        with memory._db_lock:
            memory.db.execute("BEGIN")
            try:
                self._assert_not_deleted(session_id)
                stream = memory.db.execute(
                    "SELECT epoch, high_water FROM application_streams WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                live = memory.db.execute(
                    "SELECT state, partial, turn_id, fence_generation "
                    "FROM session_live WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                control = memory.db.execute(
                    "SELECT controller_id,epoch FROM application_control WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                queue_rows = memory.db.execute(
                    "SELECT id,creator_id,request_id,text,scope,revision,state "
                    "FROM application_queue WHERE session_id=? "
                    "AND state NOT IN ('removed','submitted') "
                    "ORDER BY priority DESC,created_at,id LIMIT 100",
                    (session_id,),
                ).fetchall()
                workspace = memory.db.execute(
                    "SELECT revision FROM application_workspace WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                options = memory.db.execute(
                    "SELECT revision,plan_mode FROM application_session_options "
                    "WHERE session_id=?", (session_id,),
                ).fetchone()
                rows = memory.db.execute(
                    "SELECT rowid,role,content,ts,attachments FROM turns "
                    "WHERE session_id=? AND role IN "
                    "('user','assistant') ORDER BY rowid DESC LIMIT 500", (session_id,),
                ).fetchall()
                activity_row = memory.db.execute(
                    "SELECT projection FROM application_activity WHERE session_id=?", (session_id,),
                ).fetchone()
                memory.db.commit()
            except BaseException:
                memory.db.rollback()
                raise
        messages = []
        for row_id, role, raw, timestamp, attachments in reversed(rows):
            value = json.loads(raw)
            if isinstance(value, str):
                messages.append({"id": f"stored:{row_id}", "role": role, "content": value,
                                 "created_at": timestamp})
                if role == "user" and attachments:
                    messages[-1]["attachments"] = json.loads(attachments)
        return {
            "session_id": session_id, "messages": messages,
            "activity": (ActivityState(**json.loads(activity_row[0])).public(timeline=True)
                         if activity_row else ActivityState().public(timeline=True)),
            "state": str(live[0]) if live else "idle",
            "partial": str(live[1]) if live else "",
            "partial_message_id": f"{live[2]}:0" if live and live[2] else "",
            "fence_generation": int(live[3]) if live else 0,
            "control_epoch": int(control[1]) if control else 0,
            "has_control": bool(control and control[0] == viewer_id),
            "workspace_revision": int(workspace[0]) if workspace else 0,
            "workspace_bound": workspace is not None,
            "settings_revision": int(options[0]) if options else 0,
            "plan_mode": bool(options[1]) if options else False,
            "queue": [
                {"id": row[0], "mine": row[1] == viewer_id,
                 "request_id": row[2] if row[1] == viewer_id else "",
                 "text": row[3] if row[1] == viewer_id else "",
                 "scope": row[4] if row[1] == viewer_id else "",
                 "revision": int(row[5]), "state": row[6]}
                for row in queue_rows
            ],
            "cursor": f"{stream[0]}:{stream[1]}" if stream else "",
        }

    def replay(self, session_id: str, cursor: str, *, limit: int = 500) -> list[dict[str, Any]]:
        try:
            epoch, raw_id = cursor.split(":", 1)
            after_id = int(raw_id)
        except (ValueError, AttributeError) as exc:
            raise CursorExpired("invalid application cursor") from exc
        with self.memory._db_lock:
            self._assert_not_deleted(session_id)
            stream = self.memory.db.execute(
                "SELECT epoch,minimum_id,high_water FROM application_streams WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if (stream is None or epoch != stream[0] or after_id < int(stream[1])
                    or after_id > int(stream[2])):
                raise CursorExpired("application cursor expired; take a new snapshot")
            rows = self.memory.db.execute(
                "SELECT id,turn_id,payload FROM session_events WHERE session_id=? "
                "AND kind='application.public.v1' AND id>? AND id<=? "
                "ORDER BY id LIMIT ?",
                (session_id, after_id, int(stream[2]), max(1, min(2000, limit))),
            ).fetchall()
        public = []
        for event_id, turn_id, raw in rows:
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if not isinstance(payload, dict) or payload.get("kind") not in get_args(EventKind):
                continue
            item: dict[str, Any] = {
                "cursor": f"{epoch}:{event_id}",
                "turn_id": str(turn_id)[:64], "kind": payload["kind"],
            }
            for key, bound in (
                ("text", 65_536), ("tool", 128), ("execution_id", 64),
                ("interaction_id", 64), ("message_id", 96), ("status", 32),
            ):
                value = payload.get(key)
                if isinstance(value, str):
                    item[key] = value[:bound]
            if type(payload.get("sequence")) is int:
                item["sequence"] = max(0, int(payload["sequence"]))
            if type(payload.get("offset")) is int:
                item["offset"] = max(0, int(payload["offset"]))
            if type(payload.get("revision")) is int:
                item["revision"] = max(0, int(payload["revision"]))
            if type(payload.get("executed")) is bool:
                item["executed"] = payload["executed"]
            public.append(item)
        return public
