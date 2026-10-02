"""Bounded metadata-only detection of settled skill files; no indexing imports."""

from __future__ import annotations

import os
import stat
from pathlib import Path

SKILL_TEXT_EXTENSIONS = {
    ".css", ".csv", ".html", ".ini", ".js", ".json", ".jsx", ".md", ".markdown",
    ".py", ".rst", ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
MAX_SKILL_DROP_BYTES = 64 * 1024 * 1024


def file_signature(value: os.stat_result) -> str:
    return f"{value.st_dev}:{value.st_ino}:{value.st_size}:{value.st_mtime_ns}:{value.st_ctime_ns}"


class SkillDropDetector:
    def __init__(self, *, settle_seconds: float = 2):
        self.settle_seconds = settle_seconds
        self._seen: dict[str, tuple[str, float]] = {}

    def ready(self, root: Path, now: float) -> list[tuple[Path, str]]:
        if root.is_symlink():
            return []
        observed = {}
        ready = []
        try:
            with os.scandir(root) as entries:
                for index, entry in enumerate(entries):
                    if index >= 1000:
                        break
                    if entry.name.startswith(".") or Path(entry.name).suffix.lower() not in (
                        SKILL_TEXT_EXTENSIONS | {".zip"}
                    ):
                        continue
                    try:
                        value = entry.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if (
                        not stat.S_ISREG(value.st_mode)
                        or not 0 < value.st_size <= MAX_SKILL_DROP_BYTES
                    ):
                        continue
                    signature = file_signature(value)
                    previous, since = self._seen.get(entry.name, ("", now))
                    if previous != signature:
                        since = now
                    observed[entry.name] = (signature, since)
                    if now - since >= self.settle_seconds:
                        ready.append((Path(entry.path), signature))
        except OSError:
            return []
        self._seen = observed
        ready.sort(key=lambda item: item[0].name)
        return ready
