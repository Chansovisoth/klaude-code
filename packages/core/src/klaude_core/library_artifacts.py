"""Private managed copies, independent of sessions and knowledge indexing.

Content and metadata share one SQLite transaction. Browsing reads metadata and
bounded headers for images missing dimensions; importing, tagging and archiving
never invoke a model or an indexer.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from itertools import islice
from pathlib import Path
from typing import Any

MAX_BYTES = 32 * 1024 * 1024
PAGE_SIZE = 100
KINDS = ("document", "media", "research")
ID = re.compile(r"^(document|media|research):[0-9a-f]{32}$")
_IMAGE_HEADER_COLUMN = (
    "CASE WHEN mime IN ('image/png','image/jpeg','image/webp','image/gif') "
    "AND (width IS NULL OR height IS NULL) THEN substr(content,1,65536) "
    "END AS _image_header"
)


def plain(value: str, limit: int = 500) -> str:
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value)[:limit]


def manual_tags(value: str) -> list[str]:
    if len(value) > 1000:
        raise ValueError("Tags must fit in 1000 characters")
    tags = list(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    if len(tags) > 20 or any(len(tag) > 40 or plain(tag) != tag for tag in tags):
        raise ValueError("Use up to 20 comma-separated tags, each 1–40 printable characters")
    return tags


def regular_path(path: Path) -> None:
    """Reject symlink components before opening a private store or user file."""
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("Choose a path without symbolic links")


def image_header(data: bytes) -> tuple[str, int | None, int | None]:
    """Inspect bounded headers only; no image decoder, decompression or EXIF."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        return "image/png", *struct.unpack(">II", data[16:24])
    if data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        return "image/gif", *struct.unpack("<HH", data[6:10])
    if data.startswith(b"\xff\xd8"):
        pos = 2
        while pos + 4 < len(data):
            if data[pos] != 255:
                break
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data):
                break
            marker, pos = data[pos], pos + 1
            if marker in {0xD8, 0xD9, 0x01, *range(0xD0, 0xD8)}:
                continue
            length = int.from_bytes(data[pos : pos + 2], "big")
            if length < 2 or pos + length > len(data):
                break
            if marker in {0xC0, 0xC1, 0xC2} and length >= 7:
                height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
                return "image/jpeg", width, height
            pos += length
        return "image/jpeg", None, None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        if data[12:16] == b"VP8X" and len(data) >= 30:
            return (
                "image/webp",
                1 + int.from_bytes(data[24:27], "little"),
                1 + int.from_bytes(data[27:30], "little"),
            )
        chunk_size = int.from_bytes(data[16:20], "little")
        if (data[12:16] == b"VP8 " and len(data) >= 30 and chunk_size >= 10
                and not data[20] & 1 and data[23:26] == b"\x9d\x01\x2a"):
            return (
                "image/webp",
                int.from_bytes(data[26:28], "little") & 0x3FFF,
                int.from_bytes(data[28:30], "little") & 0x3FFF,
            )
        if (data[12:16] == b"VP8L" and len(data) >= 25 and chunk_size >= 5
                and data[20] == 0x2F and data[24] >> 5 == 0):
            dimensions = int.from_bytes(data[21:25], "little")
            return "image/webp", (dimensions & 0x3FFF) + 1, ((dimensions >> 14) & 0x3FFF) + 1
        return "image/webp", None, None
    raise ValueError("Media accepts PNG, JPEG, GIF or WebP image headers")


class ArtifactStore:
    def __init__(self, root: Path):
        self.root = root.absolute()
        self.path = self.root / "artifacts.db"

    @contextlib.contextmanager
    def database(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        regular_path(self.path)
        if write:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(self.root, 0o700)
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
        info = self.path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Artifact store must be a regular private database")
        if write:
            os.chmod(self.path, 0o600)
        with contextlib.closing(
            sqlite3.connect(
                self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                uri=True,
                timeout=0.2,
            )
        ) as db:
            db.row_factory = sqlite3.Row
            if not write:
                db.execute("PRAGMA query_only=ON")
                deadline = time.monotonic() + 3
                db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            else:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS artifacts (id TEXT UNIQUE NOT NULL, "
                    "kind TEXT NOT NULL, name TEXT NOT NULL, filename TEXT NOT NULL, "
                    "mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, "
                    "created REAL NOT NULL, origin TEXT NOT NULL, session TEXT NOT NULL, "
                    "job TEXT NOT NULL, model TEXT NOT NULL, width INTEGER, height INTEGER, "
                    "tags TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0, "
                    "revision INTEGER NOT NULL DEFAULT 1, content BLOB NOT NULL)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS generated_images (artifact TEXT UNIQUE NOT NULL, "
                    "job TEXT UNIQUE NOT NULL, provenance TEXT NOT NULL)"
                )
                db.execute(
                    "CREATE TABLE IF NOT EXISTS image_tags (artifact TEXT UNIQUE NOT NULL, "
                    "generated_tags TEXT NOT NULL, provenance TEXT NOT NULL)"
                )
                db.commit()
            try:
                yield db
                if write:
                    db.commit()
            except BaseException:
                if write:
                    db.rollback()
                raise

    @staticmethod
    def metadata(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result.pop("content", None)
        result.pop("rowid", None)
        header = result.pop("_image_header", None)
        # Older imports may lack dimensions. Derive only missing metadata from
        # a bounded header, without decoding pixels or writing during browse.
        if isinstance(header, bytes):
            with contextlib.suppress(ValueError):
                mime, width, height = image_header(header)
                if mime == result["mime"]:
                    result["width"], result["height"] = width, height
        result["tags"] = json.loads(result["tags"])
        # Imported names and provenance are untrusted terminal text.
        for key in ("name", "filename", "origin", "session", "job", "model"):
            result[key] = plain(str(result[key]))
        result["tags"] = [plain(str(tag), 40) for tag in result["tags"][:20]]
        result["ai_tags"] = [plain(str(tag), 40) for tag in
                             json.loads(result.get("ai_tags", "[]"))[:20]]
        result["date"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(result["created"]))
        return result

    @staticmethod
    def tag_columns(db: sqlite3.Connection) -> tuple[str, str]:
        # Old stores remain readable without a migration or other write on browse.
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='image_tags' "
                            "AND type='table'").fetchone()
        return (
            "coalesce(generated_tags,'[]') AS ai_tags",
            " LEFT JOIN image_tags ON image_tags.artifact=artifacts.id",
        ) if exists else ("'[]' AS ai_tags", "")

    def listing(
        self,
        kind: str,
        *,
        archived: bool = False,
        query: str = "",
        offset: int = 0,
        sort: str = "newest",
        format: str = "",
        include_total: bool = False,
    ) -> dict[str, Any]:
        if kind not in (*KINDS, "all") or sort not in {"newest", "oldest", "name"}:
            raise ValueError("Unknown artifact filter or order")
        regular_path(self.path)
        if not self.path.exists():
            return {"items": [], "more": False, **({"total": 0} if include_total else {})}
        where = "archived=?"
        values: list[Any] = [int(archived)]
        if kind != "all":
            where += " AND kind=?"
            values.append(kind)
        if format:
            where += " AND instr(mime,?)=1"
            values.append(format[:100])
        order = {"newest": "created DESC", "oldest": "created ASC", "name": "name COLLATE NOCASE"}[
            sort
        ]
        with self.database() as db:
            if include_total:
                db.execute("BEGIN")
            ai, join = self.tag_columns(db)
            if query:
                columns = ["name", "tags", "origin", "mime"] + (["generated_tags"] if join else [])
                where += " AND (" + " OR ".join(
                    f"instr(lower({column}),lower(?))>0" for column in columns
                ) + ")"
                values += [query[:200]] * len(columns)
            total = db.execute(
                "SELECT count(*) FROM artifacts" + join + " WHERE " + where, values
            ).fetchone()[0] if include_total else None
            rows = db.execute(
                "SELECT artifacts.rowid,id,kind,name,filename,mime,size,sha256,created,origin,"
                "session,job,model,width,height,tags,archived,revision," + ai
                + "," + _IMAGE_HEADER_COLUMN
                + " FROM artifacts" + join + " "
                "WHERE " + where + " ORDER BY " + order + ",id LIMIT ? OFFSET ?",
                (*values, PAGE_SIZE + 1, max(0, min(offset, 1_000_000))),
            ).fetchall()
        return {
            "items": [self.metadata(row) for row in rows[:PAGE_SIZE]],
            "more": len(rows) > PAGE_SIZE,
            **({"total": total} if include_total else {}),
        }

    def get(self, identity: str) -> dict[str, Any]:
        if not ID.fullmatch(identity):
            raise ValueError("Invalid artifact ID")
        with self.database() as db:
            ai, join = self.tag_columns(db)
            row = db.execute(
                "SELECT artifacts.rowid,id,kind,name,filename,mime,size,sha256,created,origin,"
                "session,job,model,width,height,tags,archived,revision," + ai
                + "," + _IMAGE_HEADER_COLUMN + " "
                "FROM artifacts" + join + " WHERE id=?",
                (identity,),
            ).fetchone()
        if row is None:
            raise ValueError("Artifact no longer exists; reload the list")
        return self.metadata(row)

    def store_generated_image(self, data: bytes, spec: dict, remote: str) -> dict[str, Any]:
        """Atomically retain pixels and private reviewed generation provenance."""
        with self.database(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT artifact FROM generated_images WHERE job=?", (spec["id"],)
            ).fetchone()
            if existing is not None:
                return self.get(existing["artifact"])
            item = self._insert(
                data, "media", "generated-" + spec["id"][:12] + ".png",
                "Generated image · stable-diffusion.cpp", spec["session"], spec["id"],
                spec["settings"]["model"], db=db,
            )
            db.execute(
                "INSERT INTO generated_images (artifact,job,provenance) VALUES (?,?,?)",
                (item["id"], spec["id"], json.dumps({**spec, "remote_id": remote})),
            )
        return item

    def generated_for_job(self, identity: str) -> dict[str, Any] | None:
        regular_path(self.path)
        if not self.path.exists():
            return None
        with self.database() as db:
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generated_images'"
            ).fetchone():
                return None
            row = db.execute(
                "SELECT artifact FROM generated_images WHERE job=?", (identity,)
            ).fetchone()
        return self.get(row[0]) if row is not None else None

    def generation_info(self, identity: str) -> dict[str, Any]:
        """Read provenance only on explicit generated-image inspection."""
        self.get(identity)
        with self.database() as db:
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='generated_images'"
            ).fetchone():
                return {}
            row = db.execute(
                "SELECT provenance FROM generated_images WHERE artifact=?", (identity,)
            ).fetchone()
        return json.loads(row[0]) if row is not None else {}

    def _insert(
        self,
        data: bytes,
        kind: str,
        filename: str,
        origin: str,
        session: str = "",
        job: str = "",
        model: str = "",
        db: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        if kind not in KINDS or len(data) > MAX_BYTES:
            raise ValueError("Artifacts must be at most 32 MiB")
        if kind == "media":
            mime, width, height = image_header(data[:65536])
        else:
            mime, width, height = (
                mimetypes.guess_type(filename)[0] or "application/octet-stream",
                None,
                None,
            )
            if mime.startswith("image/"):
                with contextlib.suppress(ValueError):
                    detected = image_header(data[:65536])
                    if detected[0] == mime:
                        _, width, height = detected
        if db is None:
            with self.database(write=True) as owned:
                return self._insert(data, kind, filename, origin, session, job, model, db=owned)
        identity = kind + ":" + uuid.uuid4().hex
        db.execute(
            "INSERT INTO artifacts (id,kind,name,filename,mime,size,sha256,created,"
            "origin,session,job,model,width,height,tags,content) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                identity,
                kind,
                plain(filename, 160),
                plain(filename, 160),
                mime,
                len(data),
                hashlib.sha256(data).hexdigest(),
                time.time(),
                plain(origin),
                plain(session, 100),
                plain(job, 100),
                plain(model, 200),
                width,
                height,
                "[]",
                data,
            ),
        )
        row = db.execute("SELECT * FROM artifacts WHERE id=?", (identity,)).fetchone()
        return self.metadata(row)

    def import_bytes(self, data: bytes, kind: str, filename: str) -> dict[str, Any]:
        """Import an already captured upload, without trusting a caller's host path."""
        if kind not in {"document", "media"} or not isinstance(data, bytes):
            raise ValueError("Choose document or media")
        if not filename or len(filename) > 160 or any(c in filename for c in "/\\\x00"):
            raise ValueError("Invalid upload filename")
        return self._insert(data, kind, filename, "Browser upload")

    def import_file(self, source: Path, kind: str, *, session: str = "") -> dict[str, Any]:
        if kind not in {"document", "media"}:
            raise ValueError("Choose document or media")
        source = source.expanduser().absolute()
        regular_path(source)
        fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as opened:
            before = os.fstat(opened.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("Import requires a regular file")
            if before.st_size > MAX_BYTES:
                raise ValueError("Artifacts must be at most 32 MiB")
            data = opened.read(MAX_BYTES + 1)
            after = os.fstat(opened.fileno())
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise ValueError("Source changed during import; retry when it is stable")
        return self._insert(data, kind, source.name, str(source), session)

    def store_report(
        self, name: str, text: str, *, job: str, session: str = "", model: str = "",
        db: sqlite3.Connection | None = None
    ) -> dict[str, Any]:
        """S4b storage primitive; callers own evidence, report generation and jobs."""
        if not name.endswith(".md") or Path(name).name != name:
            raise ValueError("Report name must be a Markdown filename")
        return self._insert(
            text.encode("utf-8"), "research", name, "Research report", session, job, model, db=db
        )

    def change(
        self, identity: str, revision: int, operation: str, value: str = ""
    ) -> dict[str, Any]:
        if not ID.fullmatch(identity) or operation not in {
            "tags", "clear_ai_tags", "archive", "restore", "delete"
        }:
            raise ValueError("Unknown artifact change")
        tags = manual_tags(value) if operation == "tags" else []
        with self.database(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT revision,archived FROM artifacts WHERE id=?", (identity,)
            ).fetchone()
            if row is None or row["revision"] != revision:
                raise ValueError("Artifact changed elsewhere; reload before retrying")
            if (
                operation in {"restore", "delete"}
                and not row["archived"]
                or operation == "archive"
                and row["archived"]
            ):
                raise ValueError("Archive state changed; reload before retrying")
            if operation == "delete":
                db.execute("DELETE FROM generated_images WHERE artifact=?", (identity,))
                db.execute("DELETE FROM image_tags WHERE artifact=?", (identity,))
                db.execute("DELETE FROM artifacts WHERE id=?", (identity,))
            elif operation == "clear_ai_tags":
                db.execute("DELETE FROM image_tags WHERE artifact=?", (identity,))
                db.execute("UPDATE artifacts SET revision=revision+1 WHERE id=?", (identity,))
            elif operation == "tags":
                db.execute(
                    "UPDATE artifacts SET tags=?,revision=revision+1 WHERE id=?",
                    (json.dumps(tags, ensure_ascii=False), identity),
                )
                prior = db.execute("SELECT generated_tags,provenance FROM image_tags "
                                   "WHERE artifact=?", (identity,)).fetchone()
                if prior:
                    manual = {tag.casefold() for tag in tags}
                    retained = [tag for tag in json.loads(prior[0]) if tag.casefold() not in manual]
                    sources = json.loads(prior[1])
                    db.execute("UPDATE image_tags SET generated_tags=?,provenance=? "
                               "WHERE artifact=?",
                               (json.dumps(retained), json.dumps({t: sources[t] for t in retained}),
                                identity))
            else:
                db.execute(
                    "UPDATE artifacts SET archived=?,revision=revision+1 WHERE id=?",
                    (int(operation == "archive"), identity),
                )
        return {"id": identity} if operation == "delete" else self.get(identity)

    def tagging_info(self, identity: str) -> dict:
        self.get(identity)
        with self.database() as db:
            _, join = self.tag_columns(db)
            if not join:
                return {}
            row = db.execute("SELECT provenance FROM image_tags WHERE artifact=?",
                             (identity,)).fetchone()
        return json.loads(row[0]) if row else {}

    def apply_ai_tags(
        self, identity: str, revision: int, checksum: str, tags: list[str], provenance: dict
    ) -> dict:
        from .image_tags import checked_tags

        tags = checked_tags(tags)
        encoded = json.dumps(provenance)
        if len(encoded) > 4000:
            raise ValueError("Tag provenance exceeds its bound")
        with self.database(write=True) as db:
            db.execute("BEGIN IMMEDIATE")
            item = db.execute("SELECT revision,sha256,kind,archived,tags FROM artifacts WHERE id=?",
                              (identity,)).fetchone()
            if (item is None or item["revision"] != revision or item["sha256"] != checksum
                    or item["kind"] != "media" or item["archived"]):
                raise ValueError("Image changed; reload and review tags again")
            old = db.execute("SELECT generated_tags,provenance FROM image_tags WHERE artifact=?",
                             (identity,)).fetchone()
            saved, sources = (json.loads(old[0]), json.loads(old[1])) if old else ([], {})
            manual = {tag.casefold() for tag in json.loads(item["tags"])}
            saved = [tag for tag in saved if tag.casefold() not in manual]
            known = {tag.casefold() for tag in saved} | manual
            for tag in tags:
                if tag.casefold() not in known:
                    saved.append(tag)
                    sources[tag] = provenance
                    known.add(tag.casefold())
            if len(saved) > 20:
                raise ValueError("Keep at most 20 AI tags; clear existing AI tags before retrying")
            sources = {tag: sources[tag] for tag in saved}
            db.execute("INSERT OR REPLACE INTO image_tags VALUES (?,?,?)",
                       (identity, json.dumps(saved), json.dumps(sources)))
            db.execute("UPDATE artifacts SET revision=revision+1 WHERE id=?", (identity,))
        return self.get(identity)

    def preview(self, identity: str) -> dict[str, Any]:
        item = self.get(identity)
        with self.database() as db:
            row = db.execute(
                "SELECT substr(content,1,16384) FROM artifacts WHERE id=?", (identity,)
            ).fetchone()
        if row is None:
            raise ValueError("Artifact no longer exists; reload the list")
        data = row[0]
        if item["kind"] != "media" and b"\0" not in data:
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                # A bounded read can end in the middle of a Unicode character.
                text = data.decode("utf-8", errors="replace")
            if sum(char.isprintable() or char in "\r\n\t" for char in text) >= len(text) * 0.95:
                original_lines = text.splitlines()
                lines = [plain(line, 500) for line in original_lines[:100]]
                return {
                    "item": item,
                    "lines": lines,
                    "truncated": item["size"] > len(data)
                    or len(original_lines) > 100
                    or any(len(line) > 500 for line in original_lines[:100]),
                }
        return {"item": item, "lines": [], "fallback": "Binary preview · export or open externally"}

    def export(self, identity: str, destination: Path, *, revision: int | None = None) -> Path:
        item = self.get(identity)
        destination = destination.expanduser().absolute()
        regular_path(destination)
        if not destination.parent.is_dir():
            raise ValueError("Export directory must already exist")
        created = False
        try:
            with self.database() as db:
                db.execute("BEGIN")
                row = db.execute(
                    "SELECT rowid,revision FROM artifacts WHERE id=?", (identity,)
                ).fetchone()
                if row is None or revision is not None and revision != row["revision"]:
                    raise ValueError("Artifact changed elsewhere; reload before exporting")
                with db.blobopen("artifacts", "content", row["rowid"], readonly=True) as blob:
                    fd = os.open(
                        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
                    )
                    created = True
                    with os.fdopen(fd, "wb") as output:
                        digest = hashlib.sha256()
                        while chunk := blob.read(65536):
                            output.write(chunk)
                            digest.update(chunk)
                        if digest.hexdigest() != item["sha256"]:
                            raise ValueError("Stored content checksum failed; export removed")
                        output.flush()
                        os.fsync(output.fileno())
            return destination
        except BaseException:
            if created:
                destination.unlink(missing_ok=True)
            raise

    def open_external(self, identity: str, revision: int) -> Path:
        if sys.platform != "darwin" and not (
            os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        ):
            raise ValueError("No desktop display available; use Export instead")
        opener = shutil.which("open" if sys.platform == "darwin" else "xdg-open")
        if not opener:
            raise ValueError("No desktop opener available; use Export instead")
        item = self.get(identity)
        suffix = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
        }.get(item["mime"], ".txt")
        directory = self.root / "opened"
        regular_path(directory)
        directory.mkdir(mode=0o700, exist_ok=True)
        os.chmod(directory, 0o700)
        # Desktop applications may keep reading asynchronously. Retain copies,
        # but bound this cache rather than silently deleting a file still open.
        if len(list(islice(directory.iterdir(), 8))) >= 8:
            raise ValueError("Private opened-copy cache is full; remove old copies or use Export")
        path = directory / (uuid.uuid4().hex + suffix)
        self.export(identity, path, revision=revision)
        try:
            result = subprocess.run(
                [opener, str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            path.unlink(missing_ok=True)
            raise ValueError("Desktop opener timed out; use Export instead") from exc
        except OSError as exc:
            path.unlink(missing_ok=True)
            raise ValueError("Desktop opener failed; use Export instead") from exc
        if result.returncode:
            path.unlink(missing_ok=True)
            raise ValueError("Desktop opener failed; use Export instead")
        return path


def execute_artifact_change(
    root: Path,
    operation: str,
    *,
    target: str = "",
    revision: int = 0,
    value: str = "",
    kind: str = "document",
    session: str = "",
    workspace: Path | None = None,
) -> dict[str, Any]:
    store = ArtifactStore(root)
    if operation == "import":
        source = Path(value).expanduser()
        if not source.is_absolute():
            source = (workspace or Path.cwd()) / source
        return store.import_file(source, kind, session=session)
    if operation == "export":
        if not workspace:
            raise ValueError("Export requires an active workspace")
        path = Path(value).expanduser()
        path = path if path.is_absolute() else workspace / path
        if plain(str(path), 4096) != str(path):
            raise ValueError("Export path must use printable characters")
        regular_path(path.absolute())
        if not path.resolve().is_relative_to(workspace.resolve()):
            raise ValueError("Export path must be inside the current workspace")
        return {"path": str(store.export(target, path, revision=revision))}
    if operation == "open":
        return {"path": str(store.open_external(target, revision))}
    return store.change(target, revision, operation, value)
