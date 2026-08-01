"""Install assistant skill packages into Klaude's user data directory."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from klaude_core import Config

from .snapshots import utc_timestamp

TEXT_EXTENSIONS = {
    ".css",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".markdown",
    ".py",
    ".rst",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
MAX_INDEX_FILE_BYTES = 2_000_000


@dataclass
class InstalledSkill:
    name: str
    library: str
    root: Path
    current_dir: Path
    manifest_path: Path
    text_files: list[Path]
    source_checksum: str
    previous_sources: list[str]
    previous_library: str = ""
    snapshot: str = ""
    pruned_snapshots: list[str] | None = None
    version_id: str = ""
    pending_manifest_path: Path | None = None
    source_path: Path | None = None

    @property
    def source_uris(self) -> list[str]:
        return [skill_source_uri(self.name, self.current_dir, p) for p in self.text_files]


def _safe_name(value: str) -> str:
    cleaned = "".join(c.lower() if c.isalnum() else "-" for c in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    if not cleaned:
        raise ValueError("skill name cannot be empty")
    return cleaned[:80]


def _default_name(source: Path) -> str:
    name = source.name[:-4] if source.suffix.lower() == ".zip" else source.name
    for suffix in ("-skill", "_skill", ".skill"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return _safe_name(name)


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _directory_hash(path: Path) -> str:
    h = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file() and not p.is_symlink()):
        rel = file.relative_to(path).as_posix()
        h.update(rel.encode())
        h.update(b"\0")
        h.update(_file_hash(file).encode())
        h.update(b"\0")
    return h.hexdigest()


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _write_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def _is_safe_zip_member(name: str) -> bool:
    member = Path(name)
    return not member.is_absolute() and ".." not in member.parts


def _extract_zip(source: Path, dest: Path) -> None:
    with zipfile.ZipFile(source) as zf:
        for info in zf.infolist():
            if not _is_safe_zip_member(info.filename):
                raise ValueError(f"unsafe zip path: {info.filename}")
        zf.extractall(dest)


def _content_root(path: Path) -> Path:
    entries = [p for p in path.iterdir() if p.name != "__MACOSX"]
    dirs = [p for p in entries if p.is_dir()]
    files = [p for p in entries if p.is_file()]
    if len(dirs) == 1 and not files:
        return dirs[0]
    return path


def _is_indexable_text_file(path: Path) -> bool:
    if path.is_symlink():
        return False
    if path.name.startswith("."):
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    if path.stat().st_size > MAX_INDEX_FILE_BYTES:
        return False
    sample = path.read_bytes()[:4096]
    return b"\0" not in sample


def iter_skill_text_files(current_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in current_dir.rglob("*")
        if p.is_file()
        and "__MACOSX" not in p.parts
        and _is_indexable_text_file(p)
    )


def skill_source_uri(skill_name: str, current_dir: Path, path: Path) -> str:
    rel = path.relative_to(current_dir).as_posix()
    return f"skill://{skill_name}/{rel}"


def _pending_manifest_path(root: Path, version_id: str) -> Path:
    return root / f"pending-{version_id}.json"


def _active_dir_from_manifest(root: Path, manifest: dict) -> Path:
    current = manifest.get("current_dir")
    if current:
        return Path(current)
    active = root / "CURRENT"
    if active.exists():
        value = active.read_text().strip()
        if value:
            return root / "versions" / value
    return root / "current"


def install_skill_package(
    cfg: Config,
    source: str | Path,
    name: str = "",
    library: str = "",
    overwrite: bool = True,
) -> InstalledSkill:
    source_path = Path(source).expanduser()
    if not source_path.exists():
        raise FileNotFoundError(source_path)
    if not source_path.is_file() and not source_path.is_dir():
        raise ValueError(f"not a file or directory: {source_path}")

    skill_name = _safe_name(name) if name else _default_name(source_path)
    library_name = library or skill_name
    skill_root = cfg.skills_dir / skill_name
    versions_dir = skill_root / "versions"
    manifest_path = skill_root / "manifest.json"
    previous_manifest = _read_manifest(manifest_path)
    if previous_manifest and not overwrite:
        raise FileExistsError(f"skill already exists: {skill_name}")

    previous_sources = list(previous_manifest.get("indexed_sources", []))
    previous_library = previous_manifest.get("library", library_name)
    skill_root.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"{skill_name}-", dir=cfg.skills_dir) as tmp:
        tmp_path = Path(tmp)
        unpacked = tmp_path / "unpacked"
        unpacked.mkdir()
        if source_path.is_dir():
            content = source_path
            checksum = _directory_hash(source_path)
        elif source_path.suffix.lower() == ".zip":
            _extract_zip(source_path, unpacked)
            content = _content_root(unpacked)
            checksum = _file_hash(source_path)
        else:
            content = unpacked / source_path.stem
            content.mkdir()
            shutil.copy2(source_path, content / source_path.name)
            checksum = _file_hash(source_path)

        version_id = hashlib.sha256(
            f"{skill_name}\0{library_name}\0{checksum}".encode()
        ).hexdigest()[:32]
        version_dir = versions_dir / version_id
        if not version_dir.exists():
            next_current = tmp_path / "current"
            shutil.copytree(content, next_current, dirs_exist_ok=True, symlinks=True)
            shutil.move(str(next_current), version_dir)

    text_files = iter_skill_text_files(version_dir)
    indexed_sources = [skill_source_uri(skill_name, version_dir, p) for p in text_files]
    pending = {
        "name": skill_name,
        "library": library_name,
        "source": str(source_path),
        "source_checksum": checksum,
        "state": "downloaded",
        "version_id": version_id,
        "version_dir": str(version_dir),
        "current_dir": str(version_dir),
        "indexed_files": [p.relative_to(version_dir).as_posix() for p in text_files],
        "indexed_sources": indexed_sources,
        "previous_active_version": previous_manifest.get("active_version", ""),
        "snapshot_retention": cfg.snapshot_retention,
        "checked_at": utc_timestamp(),
    }
    pending_path = _pending_manifest_path(skill_root, version_id)
    _write_manifest(pending_path, pending)

    return InstalledSkill(
        name=skill_name,
        library=library_name,
        root=skill_root,
        current_dir=version_dir,
        manifest_path=manifest_path,
        text_files=text_files,
        source_checksum=checksum,
        previous_sources=previous_sources,
        previous_library=previous_library,
        version_id=version_id,
        pending_manifest_path=pending_path,
        source_path=source_path,
    )


def list_installed_skills(cfg: Config) -> list[dict]:
    if not cfg.skills_dir.exists():
        return []
    skills = []
    for manifest in sorted(cfg.skills_dir.glob("*/manifest.json")):
        data = _read_manifest(manifest)
        if data:
            skills.append(data)
    return skills


def finalize_skill_package(installed: InstalledSkill) -> None:
    if not installed.pending_manifest_path:
        return
    pending = _read_manifest(installed.pending_manifest_path)
    if not pending:
        return
    previous = _read_manifest(installed.manifest_path)
    manifest = dict(previous)
    manifest.update(pending)
    manifest["state"] = "active"
    manifest["active_version"] = installed.version_id
    manifest["current_dir"] = str(installed.current_dir)
    manifest["checked_at"] = utc_timestamp()
    if "installed_at" not in manifest:
        manifest["installed_at"] = utc_timestamp()
    current_tmp = installed.root / f".CURRENT.{os.getpid()}.tmp"
    current_tmp.write_text(installed.version_id + "\n")
    os.replace(current_tmp, installed.root / "CURRENT")
    if installed.source_path and installed.source_path.suffix.lower() == ".zip":
        shutil.copy2(installed.source_path, installed.root / "source.zip")
    _write_manifest(installed.manifest_path, manifest)
    try:
        installed.pending_manifest_path.unlink()
    except FileNotFoundError:
        pass


def recover_skill_packages(cfg: Config) -> int:
    from .store import KnowledgeStore

    store = KnowledgeStore(cfg.knowledge_dir)
    recovered = 0
    for pending_path in cfg.skills_dir.glob("*/pending-*.json"):
        pending = _read_manifest(pending_path)
        if not pending:
            continue
        root = pending_path.parent
        manifest_path = root / "manifest.json"
        manifest = _read_manifest(manifest_path)
        owner = f"skill:{pending.get('name', root.name)}"
        active = store.active_owner_checksums(pending.get("library", ""), owner)
        sources = set(pending.get("indexed_sources", []))
        if manifest.get("active_version") == pending.get("version_id"):
            try:
                pending_path.unlink()
            except FileNotFoundError:
                pass
            recovered += 1
        elif bool(sources) and set(active) == sources:
            installed = InstalledSkill(
                name=pending["name"],
                library=pending["library"],
                root=root,
                current_dir=Path(pending["current_dir"]),
                manifest_path=manifest_path,
                text_files=[
                    Path(pending["current_dir"]) / path
                    for path in pending.get("indexed_files", [])
                ],
                source_checksum=pending["source_checksum"],
                previous_sources=[],
                version_id=pending["version_id"],
                pending_manifest_path=pending_path,
            )
            finalize_skill_package(installed)
            recovered += 1
    return recovered
