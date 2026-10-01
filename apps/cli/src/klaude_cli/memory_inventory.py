"""Bounded, read-only Memory settings inventory; never initialize storage."""

from __future__ import annotations

import contextlib
import os
import re
import sqlite3
import stat
from pathlib import Path

from klaude_core.memory import _parse_memory_line, is_sensitive_memory


def read_memory_inventory(database: Path, memory_file: Path) -> dict[str, object]:
    if database.is_symlink():
        raise ValueError("Unsafe memory database")
    with contextlib.closing(sqlite3.connect(
        database.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2
    )) as db:
        db.execute("PRAGMA query_only=ON")
        row = db.execute("SELECT value FROM settings WHERE key='auto_memory_enabled'").fetchone()
    try:
        descriptor = os.open(memory_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        text = ""
    else:
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1_048_576:
                raise ValueError("Memory file is not a bounded regular file")
            raw = source.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ValueError("Memory file exceeds inventory limit")
            text = raw.decode("utf-8", errors="replace")
    count = hidden = 0
    facts: list[str] = []
    for line in text.splitlines():
        entry = _parse_memory_line(line)
        if entry is None:
            continue
        count += 1
        if is_sensitive_memory(entry.fact):
            hidden += 1
        elif len(facts) < 8:
            facts.append(re.sub(r"[\x00-\x1f\x7f-\x9f]", "", entry.fact)[:120])
    return {"enabled": not row or row[0] == "1", "count": count, "facts": facts, "hidden": hidden}
