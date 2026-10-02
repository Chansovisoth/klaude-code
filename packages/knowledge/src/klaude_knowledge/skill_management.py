"""Serialized skill import/deletion and a non-executing local drop inbox."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from klaude_core import Config
from klaude_core.skill_drop import MAX_SKILL_DROP_BYTES, file_signature

from .skills import (
    TEXT_EXTENSIONS,
    _default_name,
    _safe_name,
    finalize_skill_package,
    install_skill_package,
)


def manifest_identity(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@contextmanager
def skill_mutation_lock(cfg: Config) -> Iterator[None]:
    path = cfg.skills_dir / ".mutation.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a+") as lock:
        import fcntl

        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def import_indexed_skill(
    cfg: Config,
    source: Path,
    *,
    name: str = "",
    library: str = "",
    overwrite: bool = True,
    knowledge=None,
):
    from .hybrid import Knowledge
    from .indexing import IndexDocument

    with skill_mutation_lock(cfg):
        if source.is_symlink():
            raise ValueError("Symlinked skill packages are not supported")
        root = cfg.skills_dir / (_safe_name(name) if name else _default_name(source))
        if any(path.is_symlink() for path in (root, root / "versions", root / "manifest.json")):
            raise ValueError("Unsafe installed skill path")
        installed = install_skill_package(
            cfg, source, name=name, library=library, overwrite=overwrite
        )
        kn = knowledge if knowledge is not None else Knowledge(cfg)
        try:
            documents = [
                IndexDocument(
                    uri,
                    path.read_text(errors="replace"),
                    path.relative_to(installed.current_dir).as_posix(),
                )
                for path, uri in zip(installed.text_files, installed.source_uris, strict=True)
            ]
            total = kn.replace_owner_snapshot_atomic(
                installed.library, f"skill:{installed.name}", documents
            )
            finalize_skill_package(installed)
            return installed, total
        finally:
            if knowledge is None:
                kn.store.fts.close()


def delete_installed_skill(cfg: Config, name: str, identity: str) -> None:
    """Delete only the reviewed package and its owner, including old libraries."""
    from .store import KnowledgeStore

    if name != _safe_name(name):
        raise ValueError("Invalid skill name")
    with skill_mutation_lock(cfg):
        root = cfg.skills_dir / name
        manifest = root / "manifest.json"
        if root.is_symlink() or manifest.is_symlink():
            raise ValueError("Unsafe skill path")
        descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Unsafe manifest")
            raw = stream.read(256_001)
        if len(raw) > 256_000 or manifest_identity(raw) != identity:
            raise ValueError("Skill changed; review it again")
        data = json.loads(raw)
        if data.get("name") != name:
            raise ValueError("Skill identity mismatch")
        store = KnowledgeStore(cfg.knowledge_dir)
        try:
            # One transaction disables only this owner across every library.
            owner = f"skill:{name}"
            with store.fts:
                store.fts.execute(
                    "UPDATE source_versions SET status='obsolete' WHERE owner=?", (owner,)
                )
                store.fts.execute("DELETE FROM active_sources WHERE owner=?", (owner,))
            shutil.rmtree(root)
            store.garbage_collect_obsolete_versions(owner=owner)
        finally:
            store.fts.close()


def prepare_skill_inbox(cfg: Config) -> Path:
    """Create a private inbox without indexing or executing anything."""
    inbox = cfg.skills_dir.parent / "skills-inbox"
    if inbox.is_symlink():
        raise ValueError("Unsafe inbox path")
    inbox.mkdir(mode=0o700, parents=True, exist_ok=True)
    return inbox


def import_dropped_skill(cfg: Config, source: Path, signature: str) -> None:
    """Index an immutable private copy, then archive only the unchanged original."""
    root = cfg.skills_dir
    if root.is_symlink() or source.parent != root or source.suffix.lower() not in (
        TEXT_EXTENSIONS | {".zip"}
    ):
        raise ValueError("Unsafe dropped skill path")
    archive = root / ".imports"
    if archive.is_symlink():
        raise ValueError("Unsafe archive path")
    archive.mkdir(mode=0o700, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".drop-", dir=root) as temporary:
        snapshot = Path(temporary) / source.name
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            value = os.fstat(stream.fileno())
            if not stat.S_ISREG(value.st_mode) or file_signature(value) != signature:
                raise ValueError("Dropped file changed")
            with snapshot.open("wb") as output:
                total = 0
                while chunk := stream.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_SKILL_DROP_BYTES:
                        raise ValueError("Package too large")
                    output.write(chunk)
            if file_signature(os.fstat(stream.fileno())) != signature:
                raise ValueError("Dropped file changed during copy")
        import_indexed_skill(cfg, snapshot, overwrite=False)
        # An edited/replaced original is a new candidate, never delete it.
        if file_signature(source.stat(follow_symlinks=False)) != signature:
            raise ValueError("Imported snapshot; original changed and remains for review")
        source.rename(archive / f"{uuid.uuid4().hex}-{source.name}")


def _import_legacy_skill_inbox(cfg: Config) -> tuple[int, int]:
    """Explicitly import up to 20 dropped files; retain originals and failed inputs."""
    inbox = prepare_skill_inbox(cfg)
    imported = failed = 0
    archive = inbox / "imported"
    if archive.is_symlink():
        raise ValueError("Unsafe archive path")
    archive.mkdir(mode=0o700, exist_ok=True)
    # Keep originals in the inbox archive, so reopening cannot reinstall a deleted skill.
    candidates = sorted(
        source
        for source in inbox.iterdir()
        if not source.is_symlink()
        and source.is_file()
        and not source.name.startswith(".")
        and source.suffix.lower() in TEXT_EXTENSIONS | {".zip"}
    )
    for source in candidates[:20]:
        try:
            if source.stat().st_size > 64 * 1024 * 1024:
                raise ValueError("Package too large")
            import_indexed_skill(cfg, source, overwrite=False)
            imported += 1
            destination = archive / source.name
            if not destination.exists():
                source.rename(destination)
        except FileExistsError:
            # Never silently replace installed skills from a drop folder.
            failed += 1
        except Exception:
            failed += 1
    return imported, failed


def import_skill_inbox(cfg: Config) -> tuple[int, int]:
    """Explicit retry for current drops and an existing legacy inbox."""
    imported, failed = (
        _import_legacy_skill_inbox(cfg)
        if (cfg.skills_dir.parent / "skills-inbox").exists() else (0, 0)
    )
    # Compatibility: old inbox imports remain supported, but new drops live
    # directly beside installed package directories (which are never candidates).
    dropped = sorted(path for path in cfg.skills_dir.iterdir()
                     if not path.name.startswith(".") and not path.is_symlink()
                     and path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS | {".zip"})
    for source in dropped[:20]:
        try:
            import_dropped_skill(cfg, source, file_signature(source.stat()))
            imported += 1
        except Exception:
            failed += 1
    return imported, failed
