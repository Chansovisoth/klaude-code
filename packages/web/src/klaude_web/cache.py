"""SQLite TTL cache for search results and fetched pages."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class TTLCache:
    def __init__(self, db_path: Path):
        self.db = sqlite3.connect(db_path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT, expires REAL)"
        )
        self.db.commit()

    def get(self, key: str):
        row = self.db.execute(
            "SELECT value, expires FROM cache WHERE key=?", (key,)
        ).fetchone()
        if not row:
            return None
        value, expires = row
        if time.time() > expires:
            self.db.execute("DELETE FROM cache WHERE key=?", (key,))
            self.db.commit()
            return None
        return json.loads(value)

    def set(self, key: str, value, ttl_seconds: float) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
            (key, json.dumps(value, ensure_ascii=False), time.time() + ttl_seconds),
        )
        self.db.commit()
