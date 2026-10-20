"""Durable admission and resource ownership for non-chat operations.

The journal records intent before dispatch. It never stores request bodies or
secrets and never retries an operation whose effect may have reached a remote
service. Callers must check the fence immediately before each side effect.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

OperationState = Literal[
    "accepted", "running", "cancelling", "completed", "failed", "cancelled", "unknown"
]
TERMINAL = frozenset({"completed", "failed", "cancelled"})
ACTIVE = frozenset({"accepted", "running", "cancelling"})
REQUEST_ID = re.compile(r"[a-f0-9]{32}")
IDENTITY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


class OperationConflict(RuntimeError):
    """A request ID or resource belongs to another operation."""


class OperationFenceLost(RuntimeError):
    """An operation can no longer safely begin another effect."""


@dataclass(frozen=True)
class OperationReceipt:
    request_id: str
    kind: str
    resource: str
    state: OperationState
    fence: int
    created: bool
    updated_at: float
    outcome: str = ""


@dataclass(frozen=True)
class FencedOperation:
    owner_id: str
    receipt: OperationReceipt


class OperationJournal:
    """SQLite-backed request receipts with explicit unknown-outcome recovery."""

    def __init__(self, path: Path, *, clock=time.time) -> None:
        self.path = Path(path)
        self._clock = clock
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError("Operation journal must be a regular private file")
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if not self.path.is_file():
                raise ValueError("Operation journal must be a regular private file") from None
        else:
            os.close(descriptor)
        info = self.path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Operation journal must be owner-only")
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS operation_secret (id INTEGER PRIMARY KEY "
                "CHECK(id=1), value BLOB NOT NULL)"
            )
            db.execute(
                "INSERT OR IGNORE INTO operation_secret VALUES (1, ?)", (secrets.token_bytes(32),)
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS operations ("
                "request_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, kind TEXT NOT NULL, "
                "resource TEXT NOT NULL, fingerprint TEXT NOT NULL, state TEXT NOT NULL, "
                "fence INTEGER NOT NULL, lease_until REAL NOT NULL, updated_at REAL NOT NULL, "
                "outcome TEXT NOT NULL DEFAULT '', reconciliation TEXT NOT NULL DEFAULT '', "
                "witness_before TEXT NOT NULL DEFAULT '', witness_after TEXT NOT NULL DEFAULT '')"
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(operations)")}
            for column in ("reconciliation", "witness_before", "witness_after"):
                if column not in columns:
                    db.execute(
                        f"ALTER TABLE operations ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
                    )
            db.execute(
                "CREATE TABLE IF NOT EXISTS operation_resources ("
                "resource TEXT PRIMARY KEY, generation INTEGER NOT NULL, "
                "request_id TEXT NOT NULL DEFAULT '')"
            )

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=2, isolation_level=None)
        db.execute("PRAGMA busy_timeout=2000")
        return db

    @staticmethod
    def _validate(request_id: str, owner_id: str, kind: str, resource: str) -> None:
        if (
            not isinstance(request_id, str)
            or not REQUEST_ID.fullmatch(request_id)
            or not all(
                isinstance(value, str) and IDENTITY.fullmatch(value)
                for value in (owner_id, kind, resource)
            )
        ):
            raise ValueError("Invalid operation identity")

    @staticmethod
    def _receipt(row: tuple[Any, ...], *, created: bool = False) -> OperationReceipt:
        return OperationReceipt(
            row[0], row[2], row[3], row[5], int(row[6]), created, float(row[8]), row[9]
        )

    def _fingerprint(
        self, db: sqlite3.Connection, kind: str, resource: str, payload: object
    ) -> str:
        try:
            content = json.dumps(
                [kind, resource, payload], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError("Operation payload must be JSON compatible") from exc
        if len(content) > 128_000:
            raise ValueError("Operation payload exceeds admission limit")
        secret = db.execute("SELECT value FROM operation_secret WHERE id=1").fetchone()[0]
        return hmac.new(secret, content, hashlib.sha256).hexdigest()

    def _witness_digest(self, db: sqlite3.Connection, value: object) -> str:
        """Bounded private HMAC; a receipt cannot reveal configuration values."""
        try:
            content = json.dumps(value, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError("Recovery witness must be JSON compatible") from exc
        if len(content) > 2_000_000:
            raise ValueError("Recovery witness exceeds limit")
        secret = db.execute("SELECT value FROM operation_secret WHERE id=1").fetchone()[0]
        return hmac.new(secret, b"witness-v1:" + content, hashlib.sha256).hexdigest()

    def record_witness(
        self, request_id: str, owner_id: str, fence: int, *, before: object, after: object
    ) -> None:
        """Persist expected states before the effect gate; never replace a witness."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = self._live(db, request_id, owner_id, fence, self._clock())
            if row[5] != "accepted" or row[11] or row[12]:
                raise OperationFenceLost("Recovery witness can only be recorded once")
            before_digest = self._witness_digest(db, before)
            after_digest = self._witness_digest(db, after)
            if before_digest == after_digest:
                raise ValueError("Recovery witness must describe a change")
            db.execute(
                "UPDATE operations SET witness_before=?,witness_after=? WHERE request_id=?",
                (before_digest, after_digest, request_id),
            )

    def reconcile_witness(
        self, request_id: str, owner_id: str, *, current: object
    ) -> OperationReceipt:
        """Resolve only an exact before/after match; mismatches retain the fence.

        The domain caller must hold its configuration lock while obtaining
        ``current`` and calling this method. Unknown effects without a witness
        or with additional changes require separate manual investigation.
        """
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, self._clock())
            row = db.execute(
                "SELECT * FROM operations WHERE request_id=? AND owner_id=?",
                (request_id, owner_id),
            ).fetchone()
            if row is None or row[5] != "unknown":
                raise OperationConflict("Only unknown operations can be reconciled")
            owned = db.execute(
                "SELECT request_id,generation FROM operation_resources WHERE resource=?",
                (row[3],),
            ).fetchone()
            if owned != (request_id, row[6]) or not row[11] or not row[12]:
                raise OperationConflict("Recovery witness or resource fence unavailable")
            digest = self._witness_digest(db, current)
            if hmac.compare_digest(digest, row[12]):
                state = "completed"
            elif hmac.compare_digest(digest, row[11]):
                state = "failed"
            else:
                raise OperationConflict("Configuration differs from both reviewed states")
            db.execute(
                "UPDATE operations SET state=?,outcome='reconciled',updated_at=? "
                "WHERE request_id=?", (state, self._clock(), request_id),
            )
            db.execute(
                "UPDATE operation_resources SET request_id='' WHERE resource=? "
                "AND request_id=? AND generation=?",
                (row[3], request_id, row[6]),
            )
            updated = db.execute(
                "SELECT * FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            return self._receipt(updated)

    def witness_after_matches(
        self, request_id: str, owner_id: str, *, candidate: object
    ) -> bool:
        """Check a proposed recovery effect without changing its unknown fence."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, self._clock())
            row = db.execute(
                "SELECT * FROM operations WHERE request_id=? AND owner_id=?",
                (request_id, owner_id),
            ).fetchone()
            if row is None or row[5] != "unknown" or not row[12]:
                raise OperationConflict("Matching unknown recovery witness unavailable")
            owned = db.execute(
                "SELECT request_id,generation FROM operation_resources WHERE resource=?",
                (row[3],),
            ).fetchone()
            if owned != (request_id, row[6]):
                raise OperationConflict("Recovery resource fence changed")
            return hmac.compare_digest(self._witness_digest(db, candidate), row[12])

    def _expire(self, db: sqlite3.Connection, now: float) -> None:
        # An accepted operation has not passed the effect gate. Expiration can
        # release its resource without asking an owner to reconcile an effect
        # that never started. Running/cancelling work remains ambiguous.
        db.execute(
            "UPDATE operation_resources SET request_id='' WHERE request_id<>'' "
            "AND EXISTS (SELECT 1 FROM operations WHERE "
            "operations.request_id=operation_resources.request_id AND "
            "operations.resource=operation_resources.resource AND "
            "operations.fence=operation_resources.generation AND "
            "operations.state='accepted' AND operations.lease_until<=?)", (now,),
        )
        db.execute(
            "UPDATE operations SET state='cancelled',outcome='cancelled',updated_at=? "
            "WHERE state='accepted' AND lease_until<=?", (now, now),
        )
        db.execute(
            "UPDATE operations SET state='unknown', updated_at=? "
            "WHERE state IN ('running','cancelling') AND lease_until<=?",
            (now, now),
        )

    def admit(
        self,
        *,
        request_id: str,
        owner_id: str,
        kind: str,
        resource: str,
        payload: object,
        lease_seconds: float = 15,
    ) -> OperationReceipt:
        self._validate(request_id, owner_id, kind, resource)
        if not 1 <= lease_seconds <= 60:
            raise ValueError("Invalid operation lease")
        now = self._clock()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            fingerprint = self._fingerprint(db, kind, resource, payload)
            self._expire(db, now)
            row = db.execute(
                "SELECT * FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            if row:
                if row[1] != owner_id or row[4] != fingerprint:
                    raise OperationConflict("Request ID already belongs to another intent")
                return self._receipt(row)
            owned = db.execute(
                "SELECT generation,request_id FROM operation_resources WHERE resource=?",
                (resource,),
            ).fetchone()
            if owned and owned[1]:
                raise OperationConflict("Resource has active or unresolved work")
            fence = int(owned[0]) + 1 if owned else 1
            db.execute(
                "INSERT INTO operation_resources(resource,generation,request_id) VALUES(?,?,?) "
                "ON CONFLICT(resource) DO UPDATE SET generation=excluded.generation, "
                "request_id=excluded.request_id",
                (resource, fence, request_id),
            )
            db.execute(
                "INSERT INTO operations(request_id,owner_id,kind,resource,fingerprint,state,"
                "fence,lease_until,updated_at) VALUES(?,?,?,?,?,'accepted',?,?,?)",
                (
                    request_id,
                    owner_id,
                    kind,
                    resource,
                    fingerprint,
                    fence,
                    now + lease_seconds,
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            assert row is not None
            return self._receipt(row, created=True)

    def status(self, request_id: str, owner_id: str) -> OperationReceipt | None:
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, self._clock())
            row = db.execute(
                "SELECT * FROM operations WHERE request_id=? AND owner_id=?",
                (request_id, owner_id),
            ).fetchone()
            return self._receipt(row) if row else None

    def recent(
        self, owner_id: str, *, limit: int = 50, offset: int = 0
    ) -> tuple[OperationReceipt, ...]:
        """Return a bounded owner-scoped activity page without private intent."""
        if (
            not isinstance(owner_id, str)
            or not IDENTITY.fullmatch(owner_id)
            or not 1 <= limit <= 100
            or not 0 <= offset <= 1000
        ):
            raise ValueError("Invalid operation activity query")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, self._clock())
            rows = db.execute(
                "SELECT * FROM operations WHERE owner_id=? "
                "ORDER BY updated_at DESC, request_id DESC LIMIT ? OFFSET ?",
                (owner_id, limit, offset),
            ).fetchall()
            return tuple(self._receipt(row) for row in rows)

    def resource_busy(self, resource: str) -> bool:
        """Check whether a resource still has active or unresolved work."""
        if not isinstance(resource, str) or not IDENTITY.fullmatch(resource):
            raise ValueError("Invalid operation resource")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, self._clock())
            row = db.execute(
                "SELECT request_id FROM operation_resources WHERE resource=?", (resource,)
            ).fetchone()
            return bool(row and row[0])

    def fenced_operation(self, resource: str) -> FencedOperation | None:
        """Identify the exact resource owner without revealing private intent."""
        if not isinstance(resource, str) or not IDENTITY.fullmatch(resource):
            raise ValueError("Invalid operation resource")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, self._clock())
            row = db.execute(
                "SELECT o.* FROM operation_resources AS r "
                "JOIN operations AS o ON o.request_id=r.request_id "
                "AND o.fence=r.generation AND o.resource=r.resource "
                "WHERE r.resource=? AND r.request_id<>''", (resource,),
            ).fetchone()
            return FencedOperation(str(row[1]), self._receipt(row)) if row else None

    def _live(
        self, db: sqlite3.Connection, request_id: str, owner_id: str, fence: int, now: float
    ) -> tuple[Any, ...]:
        self._expire(db, now)
        row = db.execute(
            "SELECT * FROM operations WHERE request_id=? AND owner_id=? AND fence=?",
            (request_id, owner_id, fence),
        ).fetchone()
        if row is None or row[5] not in ACTIVE:
            raise OperationFenceLost("Operation lease is no longer active")
        owned = db.execute(
            "SELECT request_id,generation FROM operation_resources WHERE resource=?", (row[3],)
        ).fetchone()
        if owned != (request_id, fence):
            raise OperationFenceLost("Operation resource fence changed")
        return row

    def start(self, request_id: str, owner_id: str, fence: int) -> OperationReceipt:
        now = self._clock()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = self._live(db, request_id, owner_id, fence, now)
            if row[5] == "cancelling":
                raise OperationFenceLost("Cancelled operation cannot start")
            if row[5] == "accepted":
                db.execute(
                    "UPDATE operations SET state='running',updated_at=? WHERE request_id=?",
                    (now, request_id),
                )
            updated = db.execute(
                "SELECT * FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            return self._receipt(updated)

    def renew(
        self, request_id: str, owner_id: str, fence: int, *, lease_seconds: float = 15
    ) -> None:
        if not 1 <= lease_seconds <= 60:
            raise ValueError("Invalid operation lease")
        now = self._clock()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._live(db, request_id, owner_id, fence, now)
            db.execute(
                "UPDATE operations SET lease_until=?,updated_at=? WHERE request_id=?",
                (now + lease_seconds, now, request_id),
            )

    def check_effect(self, request_id: str, owner_id: str, fence: int) -> None:
        """Reject a new side effect after cancellation or lease/fence loss."""
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = self._live(db, request_id, owner_id, fence, self._clock())
            if row[5] != "running":
                raise OperationFenceLost("Operation cannot begin another effect")

    def request_cancel(self, request_id: str, owner_id: str) -> OperationReceipt:
        now = self._clock()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, now)
            row = db.execute(
                "SELECT * FROM operations WHERE request_id=? AND owner_id=?",
                (request_id, owner_id),
            ).fetchone()
            if row is None:
                raise ValueError("Operation not found")
            if row[5] == "accepted":
                db.execute(
                    "UPDATE operations SET state='cancelled',outcome='cancelled',updated_at=? "
                    "WHERE request_id=?", (now, request_id),
                )
                db.execute(
                    "UPDATE operation_resources SET request_id='' WHERE resource=? "
                    "AND request_id=? AND generation=?", (row[3], request_id, row[6]),
                )
                row = db.execute(
                    "SELECT * FROM operations WHERE request_id=?", (request_id,)
                ).fetchone()
            elif row[5] == "running":
                db.execute(
                    "UPDATE operations SET state='cancelling',updated_at=? WHERE request_id=?",
                    (now, request_id),
                )
                row = db.execute(
                    "SELECT * FROM operations WHERE request_id=?", (request_id,)
                ).fetchone()
            return self._receipt(row)

    def mark_unknown(self, request_id: str, owner_id: str, fence: int) -> OperationReceipt:
        """Keep the resource fenced when an effect may have happened."""
        now = self._clock()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._live(db, request_id, owner_id, fence, now)
            db.execute(
                "UPDATE operations SET state='unknown',updated_at=? WHERE request_id=?",
                (now, request_id),
            )
            updated = db.execute(
                "SELECT * FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            return self._receipt(updated)

    def finish(
        self,
        request_id: str,
        owner_id: str,
        fence: int,
        *,
        state: Literal["completed", "failed", "cancelled"],
        outcome: str = "",
    ) -> OperationReceipt:
        if state not in TERMINAL or outcome not in {
            "",
            "ok",
            "failed",
            "cancelled",
            "partial",
            "unconfirmed",
        }:
            raise ValueError("Invalid public operation outcome")
        now = self._clock()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = self._live(db, request_id, owner_id, fence, now)
            db.execute(
                "UPDATE operations SET state=?,outcome=?,updated_at=? WHERE request_id=?",
                (state, outcome, now, request_id),
            )
            db.execute(
                "UPDATE operation_resources SET request_id='' WHERE resource=? "
                "AND request_id=? AND generation=?",
                (row[3], request_id, fence),
            )
            updated = db.execute(
                "SELECT * FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            return self._receipt(updated)

    def reconcile(
        self,
        request_id: str,
        owner_id: str,
        *,
        state: Literal["completed", "failed", "cancelled"],
        evidence: str,
    ) -> OperationReceipt:
        """Release an unknown resource only after a domain-specific external check."""
        if state not in TERMINAL or not 1 <= len(evidence) <= 256 or not evidence.isprintable():
            raise ValueError("Explicit bounded reconciliation evidence required")
        now = self._clock()
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            self._expire(db, now)
            row = db.execute(
                "SELECT * FROM operations WHERE request_id=? AND owner_id=?",
                (request_id, owner_id),
            ).fetchone()
            if row is None or row[5] != "unknown":
                raise OperationConflict("Only unknown operations can be reconciled")
            digest = self._fingerprint(db, "reconcile", row[3], evidence)
            db.execute(
                "UPDATE operations SET state=?,outcome='reconciled',reconciliation=?,"
                "updated_at=? WHERE request_id=?",
                (state, digest, now, request_id),
            )
            db.execute(
                "UPDATE operation_resources SET request_id='' WHERE resource=? "
                "AND request_id=? AND generation=?",
                (row[3], request_id, row[6]),
            )
            updated = db.execute(
                "SELECT * FROM operations WHERE request_id=?", (request_id,)
            ).fetchone()
            return self._receipt(updated)
