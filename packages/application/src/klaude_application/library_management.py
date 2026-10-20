"""Reviewed Library/Skills operations shared by nonterminal clients.

Reads never initialize the knowledge engine. Accepted mutations use the existing
fixed, owned subprocess worker and a private durable operation receipt. Uploads
are immutable private snapshots, not caller-selected filesystem paths.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

from klaude_core.config import Config
from klaude_core.library_artifacts import MAX_BYTES, ArtifactStore, manual_tags

from .background_jobs import OwnedBackgroundJobs
from .background_worker import execute
from .library_inventory import knowledge_inventory, knowledge_search
from .library_knowledge import KnowledgeAction, knowledge_worker_request, source_inventory
from .mcp_inventory import read_mcp_inventory
from .operation_journal import OperationConflict, OperationFenceLost, OperationJournal

OWNER = "web-admin"
PAGE_SIZE = 20
PUBLIC_ARTIFACT = frozenset(
    {
        "id",
        "kind",
        "name",
        "filename",
        "mime",
        "size",
        "sha256",
        "created",
        "width",
        "height",
        "tags",
        "ai_tags",
        "archived",
        "revision",
    }
)


@dataclass
class ManagementReview:
    id: str
    owner: str
    operation: str
    resource: str
    fields: dict[str, Any] = field(repr=False)
    summary: str = ""
    expires_at: float = 0
    upload: Any = field(default=None, repr=False)
    submitted: bool = False
    request_id: str = ""

    def public(self) -> dict[str, Any]:
        return {
            "review_id": self.id,
            "operation": self.operation,
            "summary": self.summary,
            "expires_at": self.expires_at,
        }


class LibraryManagement:
    """One profile's bounded review, operation and read service.

    A lost worker is conservatively unknown and keeps its resource fenced. This
    does not claim transactional coordination with every legacy CLI writer.
    """

    def __init__(self, cfg: Config, workspace: Path) -> None:
        self.cfg = cfg
        self.workspace = workspace.resolve()
        self.data = cfg.data_dir
        self.artifacts = ArtifactStore(self.data / "library")
        self._lock = threading.RLock()
        self._reviews: dict[str, ManagementReview] = {}
        self._active: dict[str, tuple[int, ManagementReview]] = {}
        self._journal: OperationJournal | None = None
        self._jobs = OwnedBackgroundJobs(self._event)
        self._closed = False
        self._stop = threading.Event()
        self._keeper: threading.Thread | None = None

    @property
    def journal(self) -> OperationJournal:
        with self._lock:
            if self._journal is None:
                self._journal = OperationJournal(self.data / "operations.db")
            return self._journal

    @staticmethod
    def public_artifact(item: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in item.items() if key in PUBLIC_ARTIFACT}

    def listing(
        self,
        *,
        kind: str = "document",
        archived: bool = False,
        query: str = "",
        offset: int = 0,
        sort: str = "newest",
    ) -> dict[str, Any]:
        result = self.artifacts.listing(
            kind, archived=archived, query=query, offset=offset, sort=sort, include_total=True
        )
        return self._page({**result, "items": [self.public_artifact(item)
                                               for item in result["items"]]}, offset)

    @staticmethod
    def _page(result: dict[str, Any], offset: int) -> dict[str, Any]:
        """Project bounded store batches into consistent browser-sized pages."""
        if type(offset) is not int or not 0 <= offset <= 1_000_000:
            raise ValueError("Invalid page offset")
        items = result["items"]
        total = result.get("total")
        if total is None and not result.get("more") and (items or offset == 0):
            total = offset + len(items)
        known_total = total if total is not None else (
            offset + len(items) + int(bool(result.get("more"))) if items else 0
        )
        return {**result, "items": items[:PAGE_SIZE],
                "more": len(items) > PAGE_SIZE or result.get("more", False),
                "offset": offset, "page_size": PAGE_SIZE,
                "total": total, "known_total": known_total}

    @classmethod
    def _inventory_page(cls, result: dict[str, Any], offset: int) -> dict[str, Any]:
        items = result["items"]
        # An inventory's upper scan bound is distinct from another available page.
        return cls._page({**result, "items": items[offset:], "more": False,
                          "total": len(items), "limited": result.get("more", False)}, offset)

    def detail(self, identity: str) -> dict[str, Any]:
        result = self.artifacts.preview(identity)
        return {"item": self.public_artifact(result["item"]), "lines": result["lines"],
                "truncated": result.get("truncated", False)}

    def knowledge(self, library: str = "", query: str = "", *,
                  offset: int = 0) -> dict[str, Any]:
        root = self.data / "knowledge.lance"
        if query:
            return knowledge_search(root, library, query, offset=offset)
        result = knowledge_inventory(root)
        result["items"] = sorted(result["items"], key=lambda item: item["id"])
        return self._inventory_page(result, offset)

    def sources(self, library: str, offset: int = 0) -> dict[str, Any]:
        return self._page(source_inventory(self.data / "docs-sources", library,
                                            offset=offset), offset)

    def _installed_skills(self) -> dict[str, Any]:
        result = execute(
            {
                "kind": "skills",
                "skills_dir": str(self.data / "skills"),
                "knowledge_dir": str(self.data / "knowledge.lance"),
            }
        )
        if not isinstance(result, dict):
            raise ValueError("Skills unavailable")
        return {"items": result["skills"], "more": result["truncated"]}

    def skills(self, *, query: str = "", offset: int = 0) -> dict[str, Any]:
        result = self._installed_skills()
        needle = query[:200].casefold()
        result["items"] = [item for item in result["items"] if needle in
                           f"{item['name']} {item['description']} {item['library']}".casefold()]
        return self._inventory_page(result, offset)

    def tab_counts(self) -> dict[str, dict[str, int | bool | None]]:
        """Unfiltered section totals, with bounded inventories marked as lower bounds."""
        def mcp_count() -> dict[str, Any]:
            inventory = read_mcp_inventory(self.cfg.mcp_servers_file)
            servers = inventory["servers"]
            if not isinstance(servers, list):
                raise ValueError("Invalid MCP inventory")
            return {"total": len(servers), "limited": inventory["truncated"]}

        readers: dict[str, Callable[[], dict[str, Any]]] = {
            "knowledge": self.knowledge,
            "document": lambda: self.listing(kind="document"),
            "research": lambda: self.listing(kind="research"),
            "media": lambda: self.listing(kind="media"),
            "archive": lambda: self.listing(kind="all", archived=True),
            "skills": self.skills,
            "mcp": mcp_count,
        }
        counts: dict[str, dict[str, int | bool | None]] = {}
        for name, read in readers.items():
            try:
                result = read()
                counts[name] = {"total": result["total"],
                                "limited": bool(result.get("limited", False))}
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, sqlite3.Error):
                # A broken inventory is unknown, not an empty section. Other totals
                # remain useful, and private failure details never cross this seam.
                counts[name] = {"total": None, "limited": False}
        return counts

    def _purge(self) -> None:
        for token, review in tuple(self._reviews.items()):
            if review.expires_at <= time.time() and review.request_id not in self._active:
                if review.upload is not None:
                    review.upload.cleanup()
                del self._reviews[token]

    def revoke(self, owner: str) -> None:
        """Discard unaccepted reviews; accepted work belongs to the profile."""
        with self._lock:
            for review in self._reviews.values():
                if review.owner == owner and not review.submitted:
                    review.expires_at = 0
            self._purge()

    def discard(self, owner: str, token: str) -> None:
        with self._lock:
            review = self._reviews.get(token)
            if review is not None and review.owner == owner and not review.submitted:
                review.expires_at = 0
                self._purge()

    def prepare(
        self, owner: str, draft: dict[str, Any], *, upload: tuple[str, BinaryIO] | None = None
    ) -> dict[str, Any]:
        with self._lock:
            self._purge()
            if self._closed or len(self._reviews) >= 16:
                raise OperationConflict(
                    "Reviews busy; close an earlier review or wait five minutes"
                )
            if not isinstance(draft, dict) or not isinstance(draft.get("operation"), str):
                raise ValueError("Choose an operation")
            operation = draft["operation"]
            fields: dict[str, Any] = {}
            snapshot = None
            try:
                if operation in {"import", "skill-import", "knowledge-upload"}:
                    allowed = {"operation", "upload_id", "kind", "library", "name"}
                    if set(draft) - allowed or upload is None:
                        raise ValueError("Upload a file before reviewing it")
                    # At most two 32 MiB private upload snapshots, in addition to
                    # the separately bounded browser transfer staging area.
                    if sum(r.upload is not None for r in self._reviews.values()) >= 2:
                        raise OperationConflict("Upload reviews busy; finish an earlier import")
                    filename, source = upload
                    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", filename):
                        raise ValueError("Invalid upload name")
                    snapshot = tempfile.TemporaryDirectory(prefix="klaude-library-review-")
                    destination = Path(snapshot.name) / filename
                    digest = hashlib.sha256()
                    size = 0
                    with destination.open("xb") as out:
                        os.chmod(destination, 0o600)
                        while chunk := source.read(65536):
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError("Uploads must be at most 32 MiB")
                            digest.update(chunk)
                            out.write(chunk)
                    if size == 0:
                        raise ValueError("Upload is empty")
                    os.chmod(destination, 0o400)
                    fields = {
                        "filename": filename,
                        "size": size,
                        "sha256": digest.hexdigest(),
                        "source": str(destination),
                    }
                    resource = "library-import"
                    if operation == "import":
                        kind = draft.get("kind")
                        if kind not in {"document", "media"}:
                            raise ValueError("Choose Documents or Media")
                        fields["artifact_kind"] = kind
                        summary = (
                            f"Save {filename} ({size:,} bytes) to {kind}. No indexing or execution."
                        )
                    else:
                        if size > 2 * 1024 * 1024:
                            raise ValueError("Knowledge and Skill uploads are limited to 2 MiB")
                        library = draft.get("library", "")
                        action = KnowledgeAction.from_draft(
                            {"operation": "learn", "library": library, "source": str(destination)}
                        )
                        knowledge_worker_request(
                            action, self.cfg, data_dir=self.data, workspace=self.workspace
                        )
                        fields["library"] = action.library
                        if operation == "skill-import":
                            name = draft.get("name", "")
                            if (
                                not isinstance(name, str)
                                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name)
                                or name in {".", ".."}
                            ):
                                raise ValueError(
                                    "Enter a skill name using letters, numbers, dots or dashes"
                                )
                            if not filename.lower().endswith((".zip", ".md")):
                                raise ValueError("Choose a Skill ZIP or Markdown file")
                            fields["name"] = name
                            if (self.data / "skills" / name).exists():
                                raise ValueError("Skill already exists; choose another name")
                            resource = f"skill:{name}"
                            summary = (
                                f"Install {filename} as {name} and index its text into {library}. "
                                "Existing skills are never overwritten. No scripts run."
                            )
                        else:
                            resource = "knowledge-index"
                            summary = (
                                f"Index {filename} into {library} "
                                "using the configured embedding model."
                            )
                elif operation in {"tags", "archive", "restore", "delete", "clear_ai_tags"}:
                    if set(draft) - {"operation", "target", "revision", "value"}:
                        raise ValueError("Unexpected artifact field")
                    item = self.artifacts.get(draft.get("target", ""))
                    if (
                        type(draft.get("revision")) is not int
                        or item["revision"] != draft["revision"]
                    ):
                        raise ValueError("Item changed; reload before reviewing")
                    if operation == "delete" and not item["archived"]:
                        raise ValueError("Archive the item before permanent deletion")
                    fields = {"target": item["id"], "revision": item["revision"]}
                    if operation == "tags":
                        if not isinstance(draft.get("value"), str):
                            raise ValueError("Enter comma-separated tags")
                        manual_tags(draft["value"])
                        fields["value"] = draft["value"]
                    resource = f"artifact:{item['id']}"
                    summary = f"{operation.replace('_', ' ').capitalize()}: {item['name']}."
                    if operation == "tags":
                        summary += f" Set manual tags to: {fields['value'] or '(none)'}."
                    if operation == "delete":
                        summary += (
                            " Permanently removes the private saved copy. This cannot be undone."
                        )
                elif operation in {"skill-enabled", "skill-delete"}:
                    if set(draft) - {
                        "operation",
                        "name",
                        "identity",
                        "enabled",
                        "expected_enabled",
                    }:
                        raise ValueError("Unexpected Skill field")
                    items = self._installed_skills()["items"]
                    skill = next(
                        (item for item in items if item["name"] == draft.get("name")), None
                    )
                    if (
                        skill is None
                        or skill["identity"] != draft.get("identity")
                        or type(draft.get("expected_enabled")) is not bool
                        or skill["enabled"] != draft["expected_enabled"]
                    ):
                        raise ValueError("Skill changed; reload before reviewing")
                    fields = {
                        "name": skill["name"],
                        "identity": skill["identity"],
                        "expected_enabled": skill["enabled"],
                    }
                    resource = f"skill:{skill['name']}"
                    if operation == "skill-enabled":
                        if type(draft.get("enabled")) is not bool:
                            raise ValueError("Choose enabled or disabled")
                        fields["enabled"] = draft["enabled"]
                        verb = "Enable" if draft["enabled"] else "Disable"
                        summary = f"{verb} Skill {skill['name']} for future retrieval."
                    else:
                        summary = (
                            f"Delete Skill {skill['name']} and its indexed knowledge. "
                            "Original source files are retained. This cannot be undone."
                        )
                elif operation in {"knowledge-url", "knowledge-refresh"}:
                    action_fields = {
                        **draft,
                        "operation": "learn" if operation == "knowledge-url" else "refresh",
                    }
                    if operation == "knowledge-url":
                        source = draft.get("source", "")
                        parsed = urlsplit(source) if isinstance(source, str) else None
                        if (
                            parsed is None
                            or parsed.scheme not in {"http", "https"}
                            or not parsed.hostname
                            or parsed.username
                            or parsed.password
                        ):
                            raise ValueError("Enter a public HTTP(S) URL without credentials")
                    action = KnowledgeAction.from_draft(action_fields)
                    if operation == "knowledge-refresh":
                        from .library_knowledge import manifest

                        current, identity = manifest(self.data / "docs-sources", action.source)
                        if (identity != action.source_identity
                                or current.get("library") != action.library):
                            raise ValueError("Source changed; reload and review again")
                    knowledge_worker_request(
                        action, self.cfg, data_dir=self.data, workspace=self.workspace
                    )
                    fields = action.worker_fields()
                    fields.pop("operation")
                    resource = "knowledge-index"
                    verb = "Learn" if operation == "knowledge-url" else "Refresh"
                    summary = (
                        f"{verb} {action.source} into {action.library}. "
                        "Fetches public URLs and uses the configured embedding model."
                    )
                else:
                    raise ValueError("Unsupported Library operation")
                token = secrets.token_hex(16)
                review = ManagementReview(
                    token, owner, operation, resource, fields, summary, time.time() + 300, snapshot
                )
                self._reviews[token] = review
                return review.public()
            except BaseException:
                if snapshot is not None:
                    snapshot.cleanup()
                raise

    def submit(self, owner: str, token: str, request_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge()
            review = self._reviews.get(token)
            if self._closed or review is None or review.owner != owner:
                raise ValueError("Review expired; review the operation again")
            if review.submitted and review.request_id != request_id:
                raise OperationConflict("Review already accepted; check its operation status")
            if len(self._active) >= 4 and request_id not in self._active:
                raise OperationConflict("Library operations busy; retry when one finishes")
            intent = {key: value for key, value in review.fields.items() if key != "source"}
            if review.operation in {"knowledge-url", "knowledge-refresh"}:
                intent["source"] = review.fields["source"]
            receipt = self.journal.admit(
                request_id=request_id,
                owner_id=OWNER,
                kind=review.operation,
                resource=review.resource,
                payload={"review": review.id, **intent},
            )
            if receipt.created:
                request = {
                    "kind": "library_management_operation",
                    "config_dir": str(self.cfg.config_dir),
                    "data_dir": str(self.data),
                    "workspace": str(self.workspace),
                    "request_id": request_id,
                    "fence": receipt.fence,
                    "operation": review.operation,
                    **review.fields,
                }
                if review.operation.startswith("knowledge-"):
                    action = KnowledgeAction.from_draft(
                        {
                            "operation": "refresh"
                            if review.operation == "knowledge-refresh"
                            else "learn",
                            **review.fields,
                        }
                        if review.operation != "knowledge-upload"
                        else {
                            "operation": "learn",
                            "library": review.fields["library"],
                            "source": review.fields["source"],
                        }
                    )
                    request["knowledge_request"] = knowledge_worker_request(
                        action,
                        self.cfg,
                        data_dir=self.data,
                        workspace=self.workspace,
                    )
                    if review.operation == "knowledge-upload":
                        request["knowledge_request"]["upload_identity"] = (
                            review.fields["sha256"] + ":" + review.fields["filename"]
                        )
                review.submitted = True
                review.request_id = request_id
                self.journal.start(request_id, OWNER, receipt.fence)
                self._active[request_id] = (receipt.fence, review)
                self._jobs.submit(request_id, request, timeout=180)
                if self._keeper is None:
                    self._keeper = threading.Thread(
                        target=self._keep_leases, name="klaude-library-leases", daemon=True
                    )
                    self._keeper.start()
            return self.status(request_id)

    def _keep_leases(self) -> None:
        while not self._stop.wait(3):
            with self._lock:
                for identity, (fence, _) in tuple(self._active.items()):
                    try:
                        self.journal.renew(identity, OWNER, fence)
                    except Exception:
                        self._jobs.cancel(identity)
                        self._finish(identity, False)

    def _event(self, kind: str, value: object) -> None:
        if kind != "background_result" or not isinstance(value, tuple):
            return
        identity, _, result, error = value
        with self._lock:
            self._finish(
                identity,
                not error and isinstance(result, dict) and result.get("ok") is True,
                rejected=isinstance(result, dict) and result.get("rejected") is True,
            )

    def _finish(self, identity: str, success: bool, *, rejected: bool = False) -> None:
        active = self._active.pop(identity, None)
        if active is None:
            return
        fence, review = active
        try:
            if success or rejected:
                self.journal.finish(
                    identity,
                    OWNER,
                    fence,
                    state="completed" if success else "failed",
                    outcome="ok" if success else "failed",
                )
            else:
                self.journal.mark_unknown(identity, OWNER, fence)
        except (OSError, sqlite3.Error, OperationFenceLost):
            # Never publish success after a lost receipt. The durable lease
            # expires to unknown; the resource stays fenced until local review.
            pass
        finally:
            if review.upload is not None:
                review.upload.cleanup()
                review.upload = None

    def status(self, identity: str) -> dict[str, Any]:
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise ValueError("Invalid operation ID")
        receipt = self.journal.status(identity, OWNER)
        if receipt is None:
            raise ValueError("Operation unavailable")
        return asdict(receipt)

    def operations(self) -> dict[str, Any]:
        if self._journal is None and not (self.data / "operations.db").exists():
            return {"items": []}
        return {"items": [asdict(item) for item in self.journal.recent(OWNER, limit=30)]}

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self._stop.set()
        if self._keeper is not None:
            self._keeper.join(timeout=4)
        self._jobs.close(wait=True)
        with self._lock:
            for identity in tuple(self._active):
                self._finish(identity, False)
            for review in self._reviews.values():
                if review.upload is not None:
                    review.upload.cleanup()
            self._reviews.clear()


def run_management_operation(request: dict[str, Any]) -> dict[str, Any]:
    """Fixed private worker entry; no browser-supplied roots, commands or imports."""
    from klaude_core.config import load_config

    cfg = load_config()
    data = Path(request["data_dir"])
    if cfg.data_dir.resolve() != data.resolve():
        raise ValueError("Operation root changed")
    journal = OperationJournal(data / "operations.db")
    journal.check_effect(request["request_id"], OWNER, request["fence"])
    operation = request["operation"]
    store = ArtifactStore(data / "library")
    if operation in {"import", "knowledge-upload", "skill-import"}:
        source = Path(request["source"])
        with source.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if (
            len(content) != request["size"]
            or hashlib.sha256(content).hexdigest() != request["sha256"]
        ):
            return {"rejected": True}
    if operation == "import":
        try:
            store.import_bytes(content, request["artifact_kind"], request["filename"])
        except ValueError:
            return {"rejected": True}
    elif operation in {"tags", "archive", "restore", "delete", "clear_ai_tags"}:
        try:
            store.change(
                request["target"], request["revision"], operation, request.get("value", "")
            )
        except ValueError:
            return {"rejected": True}
    elif operation in {"skill-enabled", "skill-delete", "skill-import"}:
        from klaude_knowledge.skill_management import (
            delete_installed_skill,
            import_indexed_skill,
            set_installed_skill_enabled,
        )

        if operation == "skill-enabled":
            try:
                set_installed_skill_enabled(
                    cfg,
                    request["name"],
                    request["identity"],
                    request["enabled"],
                    expected_enabled=request["expected_enabled"],
                )
            except ValueError:
                return {"rejected": True}
        elif operation == "skill-delete":
            delete_installed_skill(cfg, request["name"], request["identity"],
                                   expected_enabled=request["expected_enabled"])
        else:
            import_indexed_skill(
                cfg,
                Path(request["source"]),
                name=request["name"],
                library=request["library"],
                overwrite=False,
            )
    elif operation.startswith("knowledge-"):
        from .library_knowledge import run_operation

        result = run_operation(request["knowledge_request"])
        if result.get("status") == "rejected":
            return {"rejected": True}
        if result.get("status") not in {"learned", "unchanged", "refreshed"}:
            return {"ok": False}
    else:
        raise ValueError("Unknown operation")
    return {"ok": True}
