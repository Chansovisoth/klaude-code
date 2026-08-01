"""Refreshable documentation sources backed by permanent local snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse, urlunparse

from klaude_core import Config

from .snapshots import utc_timestamp

DOC_EXTENSIONS = {".md", ".markdown", ".txt"}
MAX_DOC_BYTES = 5_000_000


@dataclass
class InstalledDocs:
    name: str
    library: str
    root: Path
    current_dir: Path
    manifest_path: Path
    files: list[Path]
    source_urls: list[str]
    previous_sources: list[str]
    previous_library: str = ""
    snapshot: str = ""
    pruned_snapshots: list[str] | None = None
    version_id: str = ""
    warnings: list[dict] | None = None
    pending_manifest_path: Path | None = None


def _safe_name(value: str) -> str:
    cleaned = "".join(c.lower() if c.isalnum() else "-" for c in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    if not cleaned:
        raise ValueError("docs source name cannot be empty")
    return cleaned[:80]


def _default_name(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.removeprefix("www.")
    path = parsed.path.strip("/").rsplit("/", 1)[0]
    return _safe_name(path or host)


def _read_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def _write_manifest(path: Path, data: dict) -> None:
    _write_json_atomic(path, data)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    path = parsed.path or "/"
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))


def _same_domain(a: str, b: str) -> bool:
    return urlparse(a).netloc.lower() == urlparse(b).netloc.lower()


def _looks_like_doc_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in DOC_EXTENSIONS)


def extract_doc_links(llms_url: str, text: str) -> list[str]:
    candidates: list[str] = []
    candidates.extend(match.strip() for match in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text))
    candidates.extend(match.strip() for match in re.findall(r"https?://[^\s<>)\"']+", text))

    links = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.strip("`'\"").rstrip(".,;]")
        if not candidate or candidate.startswith("#"):
            continue
        absolute = _normalize_url(urljoin(llms_url, candidate))
        if not absolute.startswith(("http://", "https://")):
            continue
        if not _same_domain(llms_url, absolute):
            continue
        if not _looks_like_doc_url(absolute):
            continue
        if absolute == _normalize_url(llms_url):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        links.append(absolute)
    return links


def _path_for_url(current_dir: Path, url: str) -> Path:
    canonical = _normalize_url(url)
    parsed = urlparse(canonical)
    raw_path = unquote(parsed.path).strip("/")
    last = next((part for part in reversed(raw_path.split("/")) if part), "index")
    last = "".join(c.lower() if c.isalnum() else "-" for c in last)
    last = "-".join(part for part in last.split("-") if part) or "index"
    suffix = Path(urlparse(canonical).path).suffix.lower()
    if suffix not in DOC_EXTENSIONS:
        suffix = ".md"
    stem = Path(last).stem if Path(last).suffix else last
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    path = current_dir / f"{stem[:60]}__{digest}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def _version_id(kind: str, source_url: str, file_entries: list[dict]) -> str:
    payload = json.dumps(
        {"kind": kind, "source": source_url, "files": file_entries},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


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


def _write_doc(current_dir: Path, url: str, text: str) -> Path:
    if len(text.encode()) > MAX_DOC_BYTES:
        raise ValueError(f"documentation page is too large: {url}")
    path = _path_for_url(current_dir, url)
    path.write_text(text.strip() + "\n")
    return path


def _install_file_entries(
    cfg: Config,
    *,
    root: Path,
    current_dir: Path,
    previous_manifest: dict,
    library_name: str,
    source_urls: list[str],
    file_entries: list[dict],
    tmp_current: Path,
) -> tuple[str, list[str], list[str], str, dict]:
    _ = (cfg, root, current_dir, library_name, source_urls, file_entries, tmp_current)
    previous_sources = list(previous_manifest.get("indexed_sources", []))
    previous_library = previous_manifest.get("library", library_name)
    return "", [], previous_sources, previous_library, dict(previous_manifest)


def finalize_docs_source(installed: InstalledDocs) -> None:
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
    _write_manifest(installed.manifest_path, manifest)
    try:
        installed.pending_manifest_path.unlink()
    except FileNotFoundError:
        pass


def recover_docs_sources(cfg: Config) -> int:
    from .store import KnowledgeStore

    store = KnowledgeStore(cfg.knowledge_dir)
    recovered = 0
    for pending_path in cfg.docs_sources_dir.glob("*/pending-*.json"):
        pending = _read_manifest(pending_path)
        if not pending:
            continue
        root = pending_path.parent
        manifest_path = root / "manifest.json"
        manifest = _read_manifest(manifest_path)
        owner = f"docs:{pending.get('name', root.name)}"
        active = store.active_owner_checksums(pending.get("library", ""), owner)
        sources = set(pending.get("indexed_sources", []))
        is_active = bool(sources) and set(active) == sources
        if manifest.get("active_version") == pending.get("version_id"):
            try:
                pending_path.unlink()
            except FileNotFoundError:
                pass
            recovered += 1
        elif is_active:
            installed = InstalledDocs(
                name=pending["name"],
                library=pending["library"],
                root=root,
                current_dir=Path(pending["current_dir"]),
                manifest_path=manifest_path,
                files=[Path(pending["current_dir"]) / entry["path"] for entry in pending["files"]],
                source_urls=list(pending.get("indexed_sources", [])),
                previous_sources=[],
                version_id=pending["version_id"],
                warnings=pending.get("warnings", []),
                pending_manifest_path=pending_path,
            )
            finalize_docs_source(installed)
            recovered += 1
    return recovered


def install_docs_source(
    cfg: Config,
    llms_url: str,
    fetcher,
    name: str = "",
    library: str = "",
    max_pages: int = 200,
) -> InstalledDocs:
    original_source_url = llms_url.strip()
    source_url = _normalize_url(original_source_url)
    docs_name = _safe_name(name) if name else _default_name(source_url)
    library_name = library or docs_name
    root = cfg.docs_sources_dir / docs_name
    versions_dir = root / "versions"
    manifest_path = root / "manifest.json"
    previous_manifest = _read_manifest(manifest_path)
    previous_sources = list(previous_manifest.get("indexed_sources", []))
    previous_library = previous_manifest.get("library", library_name)
    root.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"{docs_name}-", dir=cfg.docs_sources_dir) as tmp:
        tmp_current = Path(tmp) / "current"
        tmp_current.mkdir()
        index_text = fetcher(source_url)
        index_path = _write_doc(tmp_current, source_url, index_text)
        downloaded: list[tuple[Path, str, str]] = [
            (index_path.relative_to(tmp_current), source_url, original_source_url)
        ]
        warnings: list[dict] = []

        links = extract_doc_links(source_url, index_text)[:max_pages]
        for url in links:
            try:
                text = fetcher(url)
            except Exception as exc:
                warnings.append(
                    {
                        "url": url,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                        "timestamp": utc_timestamp(),
                    }
                )
                continue
            downloaded.append(
                (_write_doc(tmp_current, url, text).relative_to(tmp_current), url, url)
            )

        if not downloaded:
            raise RuntimeError(f"no usable documents downloaded for {source_url}")

        file_entries = []
        source_urls = []
        for rel_path, url, original_url in downloaded:
            downloaded_path = tmp_current / rel_path
            file_entries.append(
                {
                    "path": rel_path.as_posix(),
                    "url": url,
                    "original_url": original_url,
                    "checksum": _hash_text(downloaded_path.read_text(errors="replace")),
                }
            )
            source_urls.append(url)
        version_id = _version_id("llms", source_url, file_entries)
        version_dir = versions_dir / version_id
        if not version_dir.exists():
            tmp_current.rename(version_dir)

    indexed_sources = [entry["url"] for entry in file_entries]
    pending = {
        "name": docs_name,
        "library": library_name,
        "llms_url": source_url,
        "original_llms_url": original_source_url,
        "kind": "llms",
        "state": "downloaded",
        "version_id": version_id,
        "version_dir": str(version_dir),
        "current_dir": str(version_dir),
        "files": file_entries,
        "indexed_sources": indexed_sources,
        "previous_active_version": previous_manifest.get("active_version", ""),
        "snapshot_retention": cfg.snapshot_retention,
        "warnings": warnings,
        "checked_at": utc_timestamp(),
    }
    pending_path = _pending_manifest_path(root, version_id)
    _write_manifest(pending_path, pending)

    return InstalledDocs(
        name=docs_name,
        library=library_name,
        root=root,
        current_dir=version_dir,
        manifest_path=manifest_path,
        files=[version_dir / entry["path"] for entry in file_entries],
        source_urls=source_urls,
        previous_sources=previous_sources,
        previous_library=previous_library,
        version_id=version_id,
        warnings=warnings,
        pending_manifest_path=pending_path,
    )


def install_crawl_source(
    cfg: Config,
    name: str,
    library: str,
    start_url: str,
    pages: list[dict],
    errors: list[dict] | None = None,
    skipped: list[str] | None = None,
    seeded: list[str] | None = None,
    options: dict | None = None,
) -> InstalledDocs:
    docs_name = _safe_name(name)
    library_name = library or docs_name
    source_url = _normalize_url(start_url)
    root = cfg.docs_sources_dir / docs_name
    versions_dir = root / "versions"
    manifest_path = root / "manifest.json"
    previous_manifest = _read_manifest(manifest_path)
    previous_sources = list(previous_manifest.get("indexed_sources", []))
    previous_library = previous_manifest.get("library", library_name)
    root.mkdir(parents=True, exist_ok=True)
    versions_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"{docs_name}-", dir=cfg.docs_sources_dir) as tmp:
        tmp_current = Path(tmp) / "current"
        tmp_current.mkdir()
        file_entries = []
        source_urls = []
        for page in pages:
            page_url = _normalize_url(page["url"])
            path = _write_doc(tmp_current, page_url, page["markdown"])
            rel_path = path.relative_to(tmp_current)
            file_entries.append(
                {
                    "path": rel_path.as_posix(),
                    "url": page_url,
                    "original_url": page["url"],
                    "checksum": _hash_text(path.read_text(errors="replace")),
                    "depth": page.get("depth", 0),
                }
            )
            source_urls.append(page_url)

        if not file_entries:
            raise RuntimeError(f"no usable crawl documents downloaded for {source_url}")
        version_id = _version_id("crawl", source_url, file_entries)
        version_dir = versions_dir / version_id
        if not version_dir.exists():
            tmp_current.rename(version_dir)

    indexed_sources = [entry["url"] for entry in file_entries]
    pending = {
        "name": docs_name,
        "library": library_name,
        "kind": "crawl",
        "start_url": source_url,
        "state": "downloaded",
        "version_id": version_id,
        "version_dir": str(version_dir),
        "current_dir": str(version_dir),
        "files": file_entries,
        "indexed_sources": indexed_sources,
        "errors": errors or [],
        "skipped": skipped or [],
        "seeded": seeded or [],
        "options": options or {},
        "previous_active_version": previous_manifest.get("active_version", ""),
        "snapshot_retention": cfg.snapshot_retention,
        "checked_at": utc_timestamp(),
    }
    pending_path = _pending_manifest_path(root, version_id)
    _write_manifest(pending_path, pending)

    return InstalledDocs(
        name=docs_name,
        library=library_name,
        root=root,
        current_dir=version_dir,
        manifest_path=manifest_path,
        files=[version_dir / entry["path"] for entry in file_entries],
        source_urls=source_urls,
        previous_sources=previous_sources,
        previous_library=previous_library,
        version_id=version_id,
        pending_manifest_path=pending_path,
    )


def update_docs_source(
    cfg: Config,
    name: str,
    fetcher,
    max_pages: int | None = None,
    crawler=None,
) -> InstalledDocs:
    docs_name = _safe_name(name)
    manifest = _read_manifest(cfg.docs_sources_dir / docs_name / "manifest.json")
    if not manifest:
        raise FileNotFoundError(f"docs source is not installed: {docs_name}")
    if manifest.get("kind") == "crawl":
        if crawler is None:
            raise ValueError("crawler is required to update crawl docs sources")
        options = dict(manifest.get("options", {}))
        saved_max_pages = int(options.get("max_pages", cfg.crawl_max_pages))
        effective_max_pages = saved_max_pages if max_pages is None else max_pages
        options["max_pages"] = effective_max_pages
        crawled = crawler(
            manifest["start_url"],
            max_depth=int(options.get("max_depth", cfg.crawl_max_depth)),
            max_pages=effective_max_pages,
            pattern=options.get("pattern", "*"),
            include_patterns=list(options.get("include_patterns", [])),
            exclude_patterns=list(options.get("exclude_patterns", [])),
            use_sitemap=bool(options.get("use_sitemap", False)),
            respect_robots=bool(options.get("respect_robots", cfg.crawl_respect_robots)),
            delay_min=float(options.get("delay_min", cfg.crawl_delay_min)),
            delay_max=float(options.get("delay_max", cfg.crawl_delay_max)),
        )
        if not crawled.get("pages"):
            raise RuntimeError(
                f"crawl refresh found no indexable pages for {docs_name}; "
                f"errors={len(crawled.get('errors', []))}, "
                f"skipped={len(crawled.get('skipped', []))}"
            )
        return install_crawl_source(
            cfg,
            docs_name,
            manifest.get("library", docs_name),
            manifest["start_url"],
            crawled["pages"],
            errors=crawled.get("errors", []),
            skipped=crawled.get("skipped", []),
            seeded=crawled.get("seeded", []),
            options=options,
        )
    return install_docs_source(
        cfg,
        manifest["llms_url"],
        fetcher,
        name=docs_name,
        library=manifest.get("library", docs_name),
        max_pages=200 if max_pages is None else max_pages,
    )


def list_docs_sources(cfg: Config) -> list[dict]:
    if not cfg.docs_sources_dir.exists():
        return []
    sources = []
    for manifest in sorted(cfg.docs_sources_dir.glob("*/manifest.json")):
        data = _read_manifest(manifest)
        if data:
            sources.append(data)
    return sources
