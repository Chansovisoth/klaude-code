"""Private, bounded browser task results kept outside operation receipts."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sqlite3
import stat
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from klaude_core.library_artifacts import ID, regular_path

MAX_BYTES = 262_144
MAX_ITEMS = 64
LIFETIME = 24 * 60 * 60


class BrowserResults:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "browser-results.db"

    @contextlib.contextmanager
    def database(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        regular_path(self.path)
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            os.close(fd)
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.getuid()
                or info.st_size > 24 * 1024 * 1024):
            raise ValueError("Browser result storage is unavailable")
        if write:
            os.chmod(self.path, 0o600)
        with contextlib.closing(sqlite3.connect(
            self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True, timeout=.2,
        )) as db:
            db.row_factory = sqlite3.Row
            if write:
                if db.execute("PRAGMA page_size").fetchone()[0] != 4096:
                    raise ValueError("Unsupported browser result database page size")
                db.execute("PRAGMA max_page_count=6144")
                db.execute("CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, artifact TEXT "
                           "NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL, "
                           "payload TEXT NOT NULL)")
                db.commit()
            else:
                db.execute("PRAGMA query_only=ON")
                deadline = time.monotonic() + 3
                db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            with db:
                yield db

    def put(self, identity: str, artifact: str, revision: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False)
        if (not re.fullmatch(r"[a-f0-9]{32}", identity) or not ID.fullmatch(artifact)
                or type(revision) is not int or revision < 1
                or len(encoded.encode()) > MAX_BYTES):
            raise ValueError("Browser result exceeds its storage limit")
        with self.database(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM results WHERE created<?", (time.time() - LIFETIME,))
            db.execute("INSERT INTO results VALUES(?,?,?,?,?)",
                       (identity, artifact, revision, time.time(), encoded))
            db.execute("DELETE FROM results WHERE id NOT IN "
                       "(SELECT id FROM results ORDER BY created DESC,id DESC LIMIT ?)",
                       (MAX_ITEMS,))

    def get(self, identity: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise ValueError("Invalid browser result")
        with self.database() as db:
            row = db.execute("SELECT id,artifact,revision,created,substr(payload,1,?) AS payload "
                             "FROM results WHERE id=? AND created>=?", (
                                 MAX_BYTES + 1, identity, time.time() - LIFETIME,
                             )).fetchone()
        if row is None or len(row["payload"].encode()) > MAX_BYTES:
            raise ValueError("Result expired or unavailable")
        return {**dict(row), "payload": json.loads(row["payload"])}

    def listing(self, artifact: str, revision: int) -> list[str]:
        if not self.path.exists():
            return []
        with self.database() as db:
            rows = db.execute("SELECT id FROM results WHERE artifact=? AND revision=? "
                              "AND created>=? ORDER BY created DESC,id DESC LIMIT 10", (
                                  artifact, revision, time.time() - LIFETIME,
                              )).fetchall()
        return [row["id"] for row in rows]
