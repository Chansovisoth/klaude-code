"""Memory tiers.

memory.md  — durable facts, human-editable, injected into every system prompt.
sessions.db — episodic: every conversation turn, for `klaude resume` later.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path


class Memory:
    def __init__(self, memory_file: Path, sessions_db: Path):
        self.memory_file = memory_file
        self.db = sqlite3.connect(sessions_db)
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS turns (
                session_id TEXT, ts REAL, role TEXT, content TEXT
            )"""
        )
        self.db.commit()

    # --- durable facts ---------------------------------------------------
    def facts(self) -> str:
        if self.memory_file.exists():
            return self.memory_file.read_text().strip()
        return ""

    def remember(self, fact: str) -> None:
        stamp = time.strftime("%Y-%m-%d")
        with open(self.memory_file, "a") as f:
            f.write(f"- {stamp}: {fact}\n")

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
