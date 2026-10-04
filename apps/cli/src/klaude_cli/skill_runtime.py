"""Bounded, read-only access to enabled installed Skill instructions."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from klaude_core.skill_catalog import _frontmatter_scalar, clean_text

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MANIFEST_BYTES = 16_384
_SKILL_BYTES = 65_536
_CATALOG_LIMIT = 64
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


@dataclass(frozen=True)
class SkillSummary:
    name: str
    description: str


class InstalledSkillReader:
    """Read exact installed files without following links or trusting manifest paths."""

    def __init__(self, root: Path, disabled_db: Path | None = None):
        self.root = root
        self.disabled_db = disabled_db

    def _check_enabled(self, name: str) -> None:
        database = self.disabled_db
        if database is None:
            return
        if database.is_symlink():
            raise ValueError("Unsafe Skill enablement database")
        if not database.exists():
            return
        try:
            with closing(sqlite3.connect(
                database.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2
            )) as connection:
                connection.execute("PRAGMA query_only=ON")
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='disabled_skills'"
                ).fetchone()
                if table and connection.execute(
                    "SELECT 1 FROM disabled_skills WHERE name=?", (name,)
                ).fetchone():
                    raise ValueError("Skill is disabled")
        except sqlite3.Error as exc:
            raise ValueError("Skill enablement is unavailable") from exc

    @staticmethod
    def _read_regular(directory: int, filename: str, limit: int) -> bytes:
        descriptor = os.open(filename, _FILE_FLAGS, dir_fd=directory)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise ValueError("Skill file is not a bounded regular file")
            chunks = []
            remaining = limit + 1
            while remaining:
                chunk = os.read(descriptor, min(remaining, 8_192))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > limit:
                raise ValueError("Skill file exceeds the read limit")
            return data
        finally:
            os.close(descriptor)

    def _open_skill(self, name: str) -> tuple[int, int]:
        if not _NAME.fullmatch(name):
            raise ValueError("Invalid Skill name")
        root = os.open(self.root, _DIRECTORY_FLAGS)
        try:
            skill = os.open(name, _DIRECTORY_FLAGS, dir_fd=root)
        except BaseException:
            os.close(root)
            raise
        return root, skill

    def _manifest(self, skill: int, name: str) -> dict:
        raw = self._read_regular(skill, "manifest.json", _MANIFEST_BYTES)
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict) or value.get("name") != name:
            raise ValueError("Skill manifest identity mismatch")
        if value.get("enabled") is False:
            raise ValueError("Skill is disabled")
        return value

    def _content_parts(self, name: str, manifest: dict, file: str) -> tuple[str, ...]:
        current = manifest.get("current_dir")
        if not isinstance(current, str):
            raise ValueError("Skill has no current version")
        root = self.root / name
        try:
            relative = Path(current).relative_to(root)
        except ValueError as exc:
            # Older installations recorded an absolute directory from a prior
            # data root. Use only this package's local legacy copy if present.
            if not (root / "current").is_dir():
                raise ValueError("Skill content path is outside its package") from exc
            relative = Path("current")
        parts = (*relative.parts, *Path(file).parts)
        if (not parts or len(parts) > 12 or len(file) > 240
                or Path(file).is_absolute()
                or any(part in {"", ".", ".."} for part in parts)):
            raise ValueError("Invalid Skill file path")
        return parts

    def read(self, name: str, file: str = "SKILL.md", *, limit: int = _SKILL_BYTES) -> str:
        root, skill = self._open_skill(name)
        directories = [root, skill]
        try:
            manifest = self._manifest(skill, name)
            self._check_enabled(name)
            parts = self._content_parts(name, manifest, file)
            current = skill
            for part in parts[:-1]:
                current = os.open(part, _DIRECTORY_FLAGS, dir_fd=current)
                directories.append(current)
            return self._read_regular(current, parts[-1], limit).decode("utf-8")
        finally:
            for descriptor in reversed(directories):
                os.close(descriptor)

    def read_excerpt(
        self, name: str, file: str = "SKILL.md", offset: int = 0, limit: int = 2_000
    ) -> str:
        """Offer a small chunk to constrained models without hiding the rest."""
        if (
            type(offset) is not int or offset < 0
            or type(limit) is not int or not 1 <= limit <= 6_000
        ):
            raise ValueError("Invalid Skill read range")
        content = self.read(name, file)
        if offset > len(content):
            raise ValueError("Skill read offset exceeds file length")
        end = min(len(content), offset + limit)
        header = (
            f"Installed Skill {name}, file {json.dumps(file)}; "
            f"characters {offset}-{end} of {len(content)}."
        )
        more = (
            f"\n[Remaining content starts at offset {end}; read it only if "
            "the current task needs more guidance.]"
            if end < len(content) else ""
        )
        return (header + "\n\n" + content[offset:end] + more
                + "\n[Apply relevant guidance to the latest user request; "
                "do not summarize this Skill unless asked.]")

    def catalog(self) -> tuple[SkillSummary, ...]:
        try:
            with os.scandir(self.root) as entries:
                names = sorted(entry.name for entry in entries
                               if entry.is_dir(follow_symlinks=False)
                               and _NAME.fullmatch(entry.name))[:_CATALOG_LIMIT]
        except OSError:
            return ()
        result = []
        for name in names:
            try:
                content = self.read(name)
                description = clean_text(_frontmatter_scalar(content[:8_192], "description"), 200)
                result.append(SkillSummary(name, description or "Description unavailable"))
            except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
                continue
        return tuple(result)
