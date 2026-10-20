"""Explicit bounded Knowledge operations, reusing the public knowledge services."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from klaude_core.fetch_settings import public_fetch_settings
from klaude_core.library_artifacts import regular_path

from .library_inventory import public_text

MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_REFRESH_BYTES = 8 * 1024 * 1024
MAX_CHUNKS = 1000


class KnowledgeRequestError(ValueError):
    """A safe user-facing error, with no provider response or private diagnostics."""


@dataclass(frozen=True)
class KnowledgeAction:
    """Reviewed user intent; worker roots and credentials are supplied separately."""

    operation: Literal["learn", "learn-report", "query", "refresh"]
    library: str
    source: str = ""
    query: str = ""
    artifact: str = ""
    revision: str = ""
    source_identity: str = ""

    @classmethod
    def from_draft(cls, draft: dict[str, Any]) -> KnowledgeAction:
        if not isinstance(draft, dict):
            raise KnowledgeRequestError("Invalid Knowledge request")
        operation = draft.get("operation")
        if not isinstance(operation, str) or operation not in {
            "learn", "learn-report", "query", "refresh"
        }:
            raise KnowledgeRequestError("Unknown Knowledge operation")
        raw_library = draft.get("library", "")
        if not isinstance(raw_library, str):
            raise KnowledgeRequestError("Invalid Knowledge library")
        library = library_name(raw_library)
        allowed = {
            "learn": {"operation", "library", "source"},
            "learn-report": {"operation", "library", "source", "artifact", "revision"},
            "query": {"operation", "library", "query"},
            "refresh": {"operation", "library", "source", "source_identity"},
        }[operation]
        if set(draft) - allowed:
            raise KnowledgeRequestError("Unexpected Knowledge request field")
        source = draft.get("source", "")
        query = draft.get("query", "")
        artifact = draft.get("artifact", "")
        revision = draft.get("revision", "")
        source_identity = draft.get("source_identity", "")
        if operation == "learn" and (
            not isinstance(source, str) or not 1 <= len(source) <= 4096
            or not source.isprintable()
        ):
            raise KnowledgeRequestError("Choose a printable source path or URL")
        if operation == "query" and (
            not isinstance(query, str) or not 1 <= len(query) <= 200 or not query.isprintable()
        ):
            raise KnowledgeRequestError("Enter a printable question of 1–200 characters")
        if operation == "refresh" and (
            not isinstance(source, str) or not re.fullmatch(r"[\w-]{1,80}", source)
            or not isinstance(source_identity, str)
            or not re.fullmatch(r"[a-f0-9]{64}", source_identity)
        ):
            raise KnowledgeRequestError("Source changed; reload before reviewing it")
        if operation == "learn-report" and (
            not isinstance(artifact, str) or not 1 <= len(artifact) <= 128
            or not artifact.isprintable() or not isinstance(revision, str)
            or not 1 <= len(revision) <= 128 or not revision.isprintable()
        ):
            raise KnowledgeRequestError("Report changed; reload before learning it")
        return cls(
            cast(Literal["learn", "learn-report", "query", "refresh"], operation),
            library, source, query, artifact, revision, source_identity,
        )

    def worker_fields(self) -> dict[str, str]:
        fields = {"operation": self.operation, "library": self.library}
        if self.operation in {"learn", "refresh"}:
            fields["source"] = self.source
        if self.operation == "refresh":
            fields["source_identity"] = self.source_identity
        if self.operation == "query":
            fields["query"] = self.query
        if self.operation == "learn-report":
            fields["artifact"] = self.artifact
            fields["revision"] = self.revision
        return fields


def knowledge_worker_request(
    action: KnowledgeAction, cfg: Any, *, data_dir: Path, workspace: Path
) -> dict[str, Any]:
    """Bind reviewed Knowledge intent to trusted runtime roots and private transport data."""
    if not isinstance(action, KnowledgeAction):
        raise KnowledgeRequestError("Invalid Knowledge action")
    reviewed_fields = KnowledgeAction.from_draft(action.worker_fields()).worker_fields()
    if not cfg.models.get("embed"):
        raise KnowledgeRequestError("Configure a local embedding model before starting this task")
    config_dir = Path(cfg.config_dir)
    data_dir = Path(data_dir)
    workspace = Path(workspace)
    if not all(path.is_absolute() for path in (config_dir, data_dir, workspace)):
        raise KnowledgeRequestError("Knowledge runtime roots must be absolute")
    reference = cfg.web_providers["exa"].api_key_env or "EXA_API_KEY"
    fetch = cfg.web_fetch
    fetch_settings = public_fetch_settings({
        "provider": fetch.settings_provider,
        "exa_fallback": fetch.exa_fallback,
        "crawl4ai_enabled": fetch.crawl4ai_enabled,
        "exa_enabled": fetch.exa_enabled,
        "crawl4ai_url": cfg.crawl4ai_url,
    })
    return {
        "kind": "library_knowledge_operation",
        **reviewed_fields,
        "config_dir": str(config_dir),
        "data_dir": str(data_dir),
        "ollama_url": cfg.ollama_url,
        "embedding_model": cfg.models["embed"],
        "fetch_settings": fetch_settings,
        "validation": getattr(cfg, "retrieval_validation_enabled", True),
        "workspace": str(workspace),
        "environment_keys": {
            "CRAWL4AI_API_KEY": os.environ.get("CRAWL4AI_API_KEY", cfg.crawl4ai_api_key),
            reference: os.environ.get(reference, cfg.exa_api_key),
        },
    }


def library_name(value: str) -> str:
    if (
        not 1 <= len(value) <= 80
        or value in {".", ".."}
        or any(char in "/\\" or not char.isprintable() for char in value)
    ):
        raise KnowledgeRequestError(
            "Use a library name of 1–80 printable characters without slashes"
        )
    return value


def read_text_file(path: Path, limit: int = MAX_SOURCE_BYTES) -> tuple[str, bytes]:
    path = path.expanduser().absolute()
    try:
        regular_path(path)
    except ValueError as exc:
        raise KnowledgeRequestError("Choose a file path without symbolic links") from exc
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise KnowledgeRequestError(
                "Choose a regular text file within the displayed size limit"
            )
        payload = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if len(payload) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise KnowledgeRequestError(
                "Source changed or exceeded its size limit; review it again"
            )
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise KnowledgeRequestError(
            "Learning requires UTF-8 text; export or convert the document first"
        ) from exc
    if "\0" in text:
        raise KnowledgeRequestError("Learning requires a text document, not binary content")
    return text, payload


def manifest(root: Path, name: str) -> tuple[dict[str, Any], str]:
    if not re.fullmatch(r"[\w-]{1,80}", name) or name in {".", ".."}:
        raise KnowledgeRequestError("Invalid managed source name")
    text, payload = read_text_file(root / name / "manifest.json", 1024 * 1024)
    try:
        value = json.loads(text)
        if not isinstance(value, dict) or value.get("name") != name:
            raise ValueError
    except ValueError as exc:
        raise KnowledgeRequestError(
            "Managed source metadata is invalid; repair it before refreshing"
        ) from exc
    return value, hashlib.sha256(payload).hexdigest()


def source_inventory(root: Path, library: str = "", offset: int = 0) -> dict[str, Any]:
    """Read manifests without store constructors, network calls or migrations."""
    regular_path(root)
    if not root.exists():
        return {"items": [], "more": False, "total": 0}
    values = []
    unavailable = 0
    # Sorting only a bounded set avoids unbounded filesystem navigation work.
    from itertools import islice

    paths = sorted(islice(root.iterdir(), 1001), key=lambda path: path.name)
    bounded = len(paths) > 1000
    for path in paths[:1000]:
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            data, digest = manifest(root, path.name)
        except (OSError, ValueError):
            unavailable += 1
            continue
        if not isinstance(data.get("library"), str) or not isinstance(data.get("files"), list):
            unavailable += 1
            continue
        if library and data.get("library") != library:
            continue
        raw_url = str(data.get("llms_url") or data.get("start_url") or "")
        try:
            parsed = urlsplit(raw_url)
            safe_url = parsed.scheme in {"http", "https"} and not (
                parsed.username or parsed.password
            )
        except ValueError:
            safe_url = False
        values.append(
            {
                "id": path.name,
                "library": public_text(data.get("library"), 80),
                "url": public_text(raw_url, 500) if safe_url else "Source URL unavailable",
                "kind": "crawl" if data.get("kind") == "crawl" else "llms.txt",
                "files": len(data.get("files", [])),
                "checked": public_text(data.get("checked_at"), 80),
                "identity": digest,
            }
        )
    start = max(0, min(offset, 1000))
    return {
        "items": values[start : start + 100],
        "more": len(values) > start + 100,
        "total": len(values),
        "bounded": bounded,
        "unavailable": unavailable,
    }


def run_operation(request: dict[str, Any]) -> dict[str, Any]:
    """Only called by an explicitly accepted owned worker, never rendering."""
    from klaude_core.config import load_config, provider_secret_value
    from klaude_core.fetch_settings import apply_fetch_settings
    from klaude_core.ollama import Ollama
    from klaude_core.settings_store import settings_lock
    from klaude_knowledge import Knowledge, index_installed_docs, update_docs_source
    from klaude_knowledge.chunker import chunk_markdown
    from klaude_web import Web
    from klaude_web.fetch import FetchPageError, UnsafeURL, canonicalize_public_url

    class BoundedEmbeddings(Ollama):
        def embed(self, model: str, texts: list[str]) -> list[list[float]]:
            if len(texts) > MAX_CHUNKS:
                raise KnowledgeRequestError(
                    "Source exceeds 1000 chunks; split it or use the CLI explicitly"
                )
            result = []
            for start in range(0, len(texts), 16):
                result.extend(super().embed(model, texts[start : start + 16]))
            return result

    cfg = load_config()
    cfg.ollama_url = request["ollama_url"]
    cfg.models["embed"] = request["embedding_model"]
    apply_fetch_settings(cfg, request.get("fetch_settings"))
    for name, value in request.get("environment_keys", {}).items():
        if (
            name in {"EXA_API_KEY", "CRAWL4AI_API_KEY"}
            or name == cfg.web_providers["exa"].api_key_env
        ):
            if isinstance(value, str) and len(value) <= 8192:
                os.environ[name] = value
    cfg.crawl4ai_api_key = provider_secret_value(
        cfg.config_dir, "CRAWL4AI_API_KEY", cfg.crawl4ai_api_key
    )
    cfg.exa_api_key = provider_secret_value(
        cfg.config_dir, cfg.web_providers["exa"].api_key_env or "EXA_API_KEY", cfg.exa_api_key
    )
    cfg.retrieval_validation_enabled = bool(request.get("validation", True))
    operation = request["operation"]
    library = library_name(request["library"]) if operation != "refresh" else ""
    ollama = BoundedEmbeddings(cfg.ollama_url, timeout=30)
    knowledge = None
    web = None
    try:
        # Serialize explicit TUI knowledge tasks across clients, independently of
        # navigation. Existing CLI and model tools keep their own service semantics.
        with settings_lock(cfg.data_dir / "library-knowledge-operation", timeout=0.2):
            if operation == "query":
                knowledge = Knowledge(cfg, ollama)
                hits = knowledge.query(request["query"][:200], library, 6)
                return {
                    "status": "queried",
                    "library": library,
                    "hits": [
                        {
                            "source": public_text(hit.get("source"), 500),
                            "text": public_text(hit.get("text"), 1200),
                        }
                        for hit in hits[:6]
                    ],
                }
            if operation in {"learn", "learn-report"}:
                if operation == "learn-report":
                    from klaude_core.library_artifacts import ArtifactStore

                    store = ArtifactStore(cfg.data_dir / "library")
                    item = store.get(request["artifact"])
                    if item["revision"] != request["revision"] or item["kind"] != "research":
                        raise KnowledgeRequestError("Report changed; reload before learning")
                    with store.database() as db:
                        payload = db.execute(
                            "SELECT content FROM artifacts WHERE id=?", (item["id"],)
                        ).fetchone()[0]
                    if len(payload) > MAX_SOURCE_BYTES:
                        raise KnowledgeRequestError("Report exceeds the learning size limit")
                    text, source, title = (
                        payload.decode("utf-8"),
                        "artifact:" + item["id"],
                        item["name"],
                    )
                else:
                    source = str(request["source"])
                if operation == "learn-report":
                    pass
                elif source.startswith(("http://", "https://")):
                    source = canonicalize_public_url(source)
                    web = Web(cfg)
                    text = web.fetch_fresh(source)
                    title = ""
                    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
                        raise KnowledgeRequestError("Source exceeds 2 MiB; use a smaller source")
                else:
                    path = Path(source).expanduser()
                    path = path if path.is_absolute() else Path(request["workspace"]) / path
                    path = path.absolute()
                    text, _payload = read_text_file(path)
                    source, title = str(path), path.stem
                    # Owned clients can snapshot an upload without retaining its
                    # temporary host path as a knowledge source. Repeated uploads
                    # of identical bytes/names address the same source.
                    upload_identity = request.get("upload_identity")
                    if upload_identity is not None:
                        if (not isinstance(upload_identity, str) or not re.fullmatch(
                            r"[a-f0-9]{64}:[A-Za-z0-9_.-]{1,100}", upload_identity
                        ) or hashlib.sha256(_payload).hexdigest() != upload_identity[:64]):
                            raise KnowledgeRequestError("Uploaded source changed")
                        source = "upload:" + upload_identity
                knowledge = Knowledge(cfg, ollama)
                if knowledge.source_is_current(library, text, source):
                    return {"status": "unchanged", "library": library, "chunks": 0}
                count = knowledge.learn_text(library, text, source=source, title=title)
                return {"status": "learned", "library": library, "chunks": count}
            if operation != "refresh":
                raise KnowledgeRequestError("Unknown Knowledge operation")
            data, identity = manifest(cfg.docs_sources_dir, request["source"])
            if identity != request["source_identity"]:
                raise KnowledgeRequestError("Source changed elsewhere; reload and review again")
            library = library_name(str(data["library"]))
            source_url = str(data.get("llms_url") or data.get("start_url") or "")
            canonicalize_public_url(source_url)
            web = Web(cfg)
            used_bytes = 0

            def fetch(url: str) -> str:
                nonlocal used_bytes
                content = web.fetch_fresh(url)
                used_bytes += len(content.encode("utf-8"))
                if used_bytes > MAX_REFRESH_BYTES:
                    raise KnowledgeRequestError(
                        "Refresh exceeds 8 MiB; previous indexed knowledge retained"
                    )
                return content

            installed = update_docs_source(
                cfg,
                request["source"],
                fetch,
                crawler=lambda url, **kwargs: web.crawl_site(
                    url, fresh=True, fetcher=fetch, **kwargs
                ),
            )
            if installed.warnings:
                raise KnowledgeRequestError(
                    "Some source pages failed; previous indexed knowledge retained"
                )
            pending = (
                json.loads(installed.pending_manifest_path.read_text())
                if installed.pending_manifest_path
                else {}
            )
            if pending.get("errors"):
                raise KnowledgeRequestError(
                    "Some crawl pages failed; previous indexed knowledge retained"
                )
            texts = [read_text_file(path, 5_000_000)[0] for path in installed.files]
            if sum(len(text.encode("utf-8")) for text in texts) > MAX_REFRESH_BYTES:
                raise KnowledgeRequestError(
                    "Refresh exceeds 8 MiB; previous indexed knowledge retained"
                )
            if sum(len(chunk_markdown(text)) for text in texts) > MAX_CHUNKS:
                raise KnowledgeRequestError(
                    "Refresh exceeds 1000 chunks; previous indexed knowledge retained"
                )
            if manifest(cfg.docs_sources_dir, request["source"])[1] != identity:
                raise KnowledgeRequestError(
                    "Source changed during refresh; reload and review again"
                )
            knowledge = Knowledge(cfg, ollama)
            count = index_installed_docs(installed, knowledge)
            return {
                "status": "refreshed",
                "library": library,
                "chunks": count,
                "files": len(installed.files),
            }
    except KnowledgeRequestError as exc:
        return {"status": "rejected", "message": str(exc)}
    except UnsafeURL:
        return {"status": "rejected", "message": "URL blocked by public-address safety rules"}
    except FetchPageError:
        return {
            "status": "rejected",
            "message": "Source read failed or exceeded URL Fetch limits; nothing was indexed",
        }
    except (FileNotFoundError, UnicodeError):
        return {
            "status": "rejected",
            "message": "Source missing or not UTF-8 text; review it again",
        }
    except Exception:
        return {
            "status": "unconfirmed",
            "message": "Knowledge operation unconfirmed; Reload to verify before retrying",
        }
    finally:
        if knowledge is not None:
            knowledge.store.fts.close()
        ollama.close()
        if web is not None and web.cache.db is not None:
            web.cache.db.close()
