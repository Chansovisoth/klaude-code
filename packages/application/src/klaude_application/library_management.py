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
from klaude_core.library_artifacts import (
    MAX_BYTES,
    ArtifactStore,
    ai_tag_removals,
    image_header,
    manual_tags,
    source_link,
)

from . import browser_model_settings, model_store
from .background_jobs import OwnedBackgroundJobs
from .background_worker import execute
from .browser_jobs import OPERATIONS as GENERATED_OPERATIONS
from .browser_jobs import operation_timeout, prepare_generated_operation, run_generated_operation
from .browser_knowledge import browse_knowledge, prepare_delete
from .browser_management import OPERATIONS as PROFILE_OPERATIONS
from .browser_management import prepare_profile_operation, run_profile_operation
from .browser_media_settings import OPERATIONS as MEDIA_SETTINGS_OPERATIONS
from .browser_media_settings import WITNESSED, prepare_media_setting, run_media_setting
from .browser_vision import OPERATIONS as VISION_OPERATIONS
from .browser_vision import READ_OPERATIONS as VISION_READ_OPERATIONS
from .browser_vision import prepare_vision_operation, run_vision_operation
from .library_inventory import knowledge_inventory, knowledge_search
from .library_knowledge import KnowledgeAction, knowledge_worker_request, source_inventory
from .mcp_inventory import read_mcp_inventory
from .model_activity import ModelActivity
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
        "source_url",
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
        self._model_progress: dict[str, dict[str, Any]] = {}
        self._model_recovery: dict[str, float] = {}
        self._model_activity = ModelActivity()
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
        images_only: bool = False,
        source: str = "all",
        session: str = "",
        identities: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        result = self.artifacts.listing(
            kind, archived=archived, query=query, offset=offset, sort=sort, include_total=True,
            images_only=images_only,
            source=source,
            session=session, identities=identities,
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
        result = self.artifacts.preview(identity, include_source=True)
        return {"item": self.public_artifact(result["item"]), "lines": result["lines"],
                "truncated": result.get("truncated", False),
                **{key: result[key] for key in (
                    "source_text", "source_truncated", "source_sanitized", "fallback"
                ) if key in result}}

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

    def knowledge_contents(self, **filters: Any) -> dict[str, Any]:
        result = browse_knowledge(self.data / "knowledge.lance", **filters)
        rows = result.get("items", []) if "items" in result else [result["item"]]
        for item in rows:
            source = item.get("source", item["id"] if result.get("mode") == "sources" else "")
            label = source
            if source.startswith("upload:"):
                label = re.sub(r"^[a-f0-9]{64}:", "", source[7:])
            elif source.startswith("artifact:"):
                try:
                    label = self.artifacts.get(source[9:])["name"]
                except (OSError, ValueError, sqlite3.Error):
                    pass
            if source:
                item["source_name"] = label
        if result.get("mode") == "sources":
            from .library_knowledge import manifest

            for item in result["items"]:
                item["refresh"] = []
                for name in item.pop("managed_names", []):
                    try:
                        current, identity = manifest(self.data / "docs-sources", name)
                        if current.get("library") == filters.get("library"):
                            item["refresh"].append({"id": name, "identity": identity})
                    except (OSError, ValueError):
                        pass
        return result

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

    def skills(self, *, query: str = "", offset: int = 0,
               state: str = "all") -> dict[str, Any]:
        if state not in {"all", "enabled", "disabled"}:
            raise ValueError("Unknown Skills status")
        result = self._installed_skills()
        all_items = result["items"]
        enabled = sum(bool(item["enabled"]) for item in all_items)
        result["counts"] = {
            "all": len(all_items),
            "enabled": enabled,
            "disabled": len(all_items) - enabled,
            "limited": bool(result.get("more", False)),
        }
        needle = query[:200].casefold()
        result["items"] = [item for item in result["items"] if needle in
                           f"{item['name']} {item['description']} {item['library']}".casefold()
                           and (state == "all" or item["enabled"] == (state == "enabled"))]
        result["state"] = state
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
            "files": lambda: self.listing(kind="all", source="input"),
            "outputs": lambda: self.listing(kind="all", source="output"),
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
            if review is None or review.owner != owner:
                return
            if review.submitted:
                # Settings batches acknowledge settled snapshots individually.
                # Free their bounded preparation slots without deleting durable
                # receipts, cancelling accepted work or releasing unknown fences.
                if (review.operation not in {"setting-save", *MEDIA_SETTINGS_OPERATIONS}
                        or review.request_id in self._active):
                    return
                receipt = self.journal.status(review.request_id, OWNER)
                if receipt is None or receipt.state not in {"completed", "failed", "cancelled"}:
                    return
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
                        kind = draft.get("kind", "auto")
                        if not isinstance(kind, str) or kind not in {"auto", "document", "media"}:
                            raise ValueError("Invalid import type")
                        if kind == "auto":
                            # Classify the immutable bytes being reviewed, never
                            # the browser's MIME declaration or filename suffix.
                            with destination.open("rb") as captured:
                                header = captured.read(65536)
                            try:
                                image_header(header)
                            except ValueError:
                                kind = "document"
                            else:
                                kind = "media"
                        fields["artifact_kind"] = kind
                        file_type = "an image" if kind == "media" else "a file"
                        summary = (
                            f"Save {filename} ({size:,} bytes) to Files as {file_type}. "
                            "No indexing or execution."
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
                elif operation in {
                    "tags", "archive", "restore", "delete", "clear_ai_tags", "source_link"
                }:
                    allowed = {"operation", "target", "revision", "value"}
                    if operation == "tags":
                        allowed.add("remove_ai_tags")
                    if set(draft) - allowed:
                        raise ValueError("Unexpected artifact field")
                    item = self.artifacts.get(draft.get("target", ""))
                    if (
                        type(draft.get("revision")) is not int
                        or item["revision"] != draft["revision"]
                    ):
                        raise ValueError("Item changed; reload before reviewing")
                    fields = {"target": item["id"], "revision": item["revision"]}
                    if operation == "tags":
                        if not isinstance(draft.get("value"), str):
                            raise ValueError("Enter comma-separated tags")
                        manual_tags(draft["value"])
                        fields["value"] = draft["value"]
                        if "remove_ai_tags" in draft:
                            removals = ai_tag_removals(draft["remove_ai_tags"])
                            if not set(removals).issubset(item["ai_tags"]):
                                raise ValueError("AI tags changed; reload before reviewing")
                            fields["remove_ai_tags"] = removals
                    if operation == "source_link":
                        if not isinstance(draft.get("value"), str):
                            raise ValueError("Enter source text")
                        fields["value"] = source_link(draft["value"])
                    resource = f"artifact:{item['id']}"
                    summary = f"{operation.replace('_', ' ').capitalize()}: {item['name']}."
                    if operation == "tags":
                        summary += f" Set manual tags to: {fields['value'] or '(none)'}."
                        if fields.get("remove_ai_tags"):
                            summary += (" Remove AI tags: " +
                                        ", ".join(fields["remove_ai_tags"]) + ".")
                    if operation == "source_link":
                        summary += (
                            f" Set source to: {fields['value'] or '(none)'}. No URL is fetched."
                        )
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
                elif operation == "knowledge-delete":
                    fields, resource, summary = prepare_delete(self.data / "knowledge.lance", draft)
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
                elif operation in browser_model_settings.OPERATIONS:
                    fields, resource, summary = browser_model_settings.prepare(self.cfg, draft)
                elif operation in model_store.OPERATIONS:
                    fields, resource, summary = model_store.prepare(self.cfg, draft)
                elif operation in GENERATED_OPERATIONS:
                    fields, resource, summary = prepare_generated_operation(self.cfg, draft)
                elif operation in MEDIA_SETTINGS_OPERATIONS:
                    fields, resource, summary = prepare_media_setting(self.cfg, draft)
                elif operation in VISION_OPERATIONS:
                    fields, resource, summary = prepare_vision_operation(self.cfg, draft)
                elif operation in PROFILE_OPERATIONS:
                    fields, resource, summary = prepare_profile_operation(
                        self.cfg, draft, self.workspace,
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

    def local_review(self, owner: str, token: str) -> bool:
        with self._lock:
            review = self._reviews.get(token)
            return bool(review is not None and review.owner == owner
                        and review.operation.startswith("mcp-"))

    def model_review(self, owner: str, token: str) -> bool:
        with self._lock:
            review = self._reviews.get(token)
            return bool(review and review.owner == owner
                        and (review.operation in model_store.OPERATIONS
                             or review.operation in browser_model_settings.OPERATIONS))

    def admin_model_review(self, owner: str, token: str) -> bool:
        with self._lock:
            review = self._reviews.get(token)
            return bool(review and review.owner == owner
                        and (review.operation in model_store.OPERATIONS
                             or review.operation in browser_model_settings.OPERATIONS
                             or review.operation in MEDIA_SETTINGS_OPERATIONS))

    def model_busy(self) -> bool:
        if self._journal is None and not (self.data / "operations.db").exists():
            return False
        return self.journal.resource_busy(model_store.RESOURCE)

    def model_jobs(self) -> dict[str, Any]:
        result = model_store.jobs(self.cfg, self.journal)
        with self._lock:
            for item in result["items"]:
                item["progress"] = self._model_progress.get(item["request_id"], {})
                item["cancellable"] = item["request_id"] in self._active
        result.update(self._model_activity.read(self.cfg, result["items"]))
        return result

    def cancel_model(self, identity: str) -> dict[str, Any]:
        with self._lock:
            receipt = self.status(identity)
            if receipt["kind"] != "model-pull":
                raise ValueError("Only a model download can be cancelled")
            if receipt["state"] in {"completed", "failed", "cancelled"}:
                return receipt
            if identity not in self._active:
                raise OperationConflict("Download unconfirmed; check its inventory")
            self.journal.request_cancel(identity, OWNER)
            self._jobs.cancel(identity)
            return self.status(identity)

    def dismiss_model(self, identity: str) -> dict[str, Any]:
        with self._lock:
            if identity in self._active:
                raise OperationConflict("Stop the active download before removing its history")
            self._reconcile_stopped_model(identity)
            return model_store.dismiss(self.cfg, self.journal, identity)

    def _reconcile_stopped_model(self, identity: str) -> bool:
        # A tagged local handler completion can verify a stopped request without
        # another mutation. Missing proof leaves the normal unknown fence intact.
        try:
            receipt = self.status(identity)
            if receipt["kind"] == "model-pull" and receipt["state"] == "unknown":
                model_store.reconcile(self.cfg, self.journal, identity, require_end_proof=True)
            return True
        except Exception:
            return False

    def reconcile_model(self, identity: str) -> dict[str, Any]:
        with self._lock:
            if identity in self._active:
                raise OperationConflict("Stop the active model request before checking its outcome")
            return model_store.reconcile(self.cfg, self.journal, identity)

    def reviewed_connection(self, owner: str, token: str) -> dict[str, Any] | None:
        with self._lock:
            review = self._reviews.get(token)
            if (review and review.owner == owner
                    and review.operation in browser_model_settings.WRITES):
                return review.fields.get("expected")
            return None

    def reviewed_session_action(self, owner: str, token: str, session_id: str) -> str:
        with self._lock:
            review = self._reviews.get(token)
            if (review is not None and review.owner == owner
                    and review.operation in {"session-archive", "session-delete"}
                    and review.fields.get("target") == session_id):
                return review.operation
            return ""

    def session_busy(self, session_id: str) -> bool:
        if self._journal is None and not (self.data / "operations.db").exists():
            return False
        return self.journal.resource_busy(f"session:{session_id}")

    def submit(
        self, owner: str, token: str, request_id: str, *,
        before_start: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._purge()
            review = self._reviews.get(token)
            if self._closed or review is None or review.owner != owner:
                raise ValueError("Review expired; review the operation again")
            if review.submitted and review.request_id != request_id:
                raise OperationConflict("Review already accepted; check its operation status")
            if len(self._active) >= 4 and request_id not in self._active:
                raise OperationConflict("Library operations busy; retry when one finishes")
            model_operation = review.operation in model_store.OPERATIONS
            model_definition = review.operation in browser_model_settings.WRITES
            if ((model_operation or model_definition)
                    and any(key != request_id for key in self._active)):
                raise OperationConflict("Finish active operations before managing model weights")
            if not model_operation and self.model_busy():
                raise OperationConflict("Model work is active or unconfirmed; check Downloads")
            intent = {key: value for key, value in review.fields.items() if key != "source"}
            if review.operation in {"knowledge-url", "knowledge-refresh"}:
                intent["source"] = review.fields["source"]
            receipt = self.journal.admit(
                request_id=request_id,
                owner_id=OWNER,
                kind=review.operation,
                resource=review.resource,
                payload={"review": review.id, **intent},
                conflicts_with=() if model_operation else (model_store.RESOURCE,),
                exclusive=model_operation or model_definition,
            )
            if receipt.created:
                review.submitted = True
                review.request_id = request_id
                if before_start is not None:
                    try:
                        before_start()
                    except Exception:
                        # Admission validates the exact request/resource before the
                        # host changes chats. No worker effect has begun yet.
                        self.journal.finish(request_id, OWNER, receipt.fence,
                                            state="failed", outcome="failed")
                        raise
                if model_operation:
                    model_store.save_target(self.cfg, request_id, review.fields)
                    final_installed = review.operation == "model-pull"
                    self.journal.record_witness(
                        request_id, OWNER, receipt.fence,
                        before=model_store.witness(review.fields, not final_installed),
                        after=model_store.witness(review.fields, final_installed),
                    )
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
                if review.operation in {"knowledge-url", "knowledge-refresh", "knowledge-upload"}:
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
                if (not review.operation.startswith("mcp-")
                        and review.operation not in WITNESSED
                        and review.operation not in browser_model_settings.WRITES):
                    self.journal.start(request_id, OWNER, receipt.fence)
                self._active[request_id] = (receipt.fence, review)
                timeout = (1830 if model_operation else
                           operation_timeout(review.operation, review.fields))
                self._jobs.submit(request_id, request, timeout=timeout,
                                  notify_cancel=(model_operation or
                                                 review.operation in VISION_READ_OPERATIONS))
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
                for identity, deadline in tuple(self._model_recovery.items()):
                    if (time.monotonic() >= deadline
                            or self._reconcile_stopped_model(identity)):
                        self._model_recovery.pop(identity, None)

    def _event(self, kind: str, value: object) -> None:
        if kind == "background_progress" and isinstance(value, tuple):
            identity, _, progress = value
            with self._lock:
                active = self._active.get(identity)
                if active and active[1].operation in model_store.OPERATIONS:
                    self._model_progress[identity] = {
                        key: progress[key] for key in ("stage", "completed", "total")
                        if key in progress
                    }
            return
        if kind == "background_stopped" and isinstance(value, tuple):
            identity = value[0]
            with self._lock:
                active = self._active.get(identity)
                if active is not None and active[1].operation in model_store.OPERATIONS:
                    self._finish(identity, False)
                    if not self._reconcile_stopped_model(identity):
                        # journald may publish the handler-end entry just after
                        # the worker exits. Recheck evidence only; never replay.
                        self._model_recovery[identity] = time.monotonic() + 30
                    return
                if active is not None and active[1].operation in VISION_READ_OPERATIONS:
                    self._active.pop(identity)
                    try:
                        self.journal.finish(identity, OWNER, active[0],
                                            state="cancelled", outcome="cancelled")
                    except (OSError, sqlite3.Error, OperationFenceLost):
                        pass
            return
        if kind != "background_result" or not isinstance(value, tuple):
            return
        identity, _, result, error = value
        with self._lock:
            active = self._active.get(identity)
            if active and active[1].operation in model_store.OPERATIONS:
                message = result.get("message", "") if isinstance(result, dict) else ""
                if isinstance(message, str) and len(message) <= 300 and message.isprintable():
                    try:
                        model_store.save_message(self.cfg, identity, message)
                    except (OSError, ValueError):
                        pass
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

    def cancel_vision(self, identity: str) -> dict[str, Any]:
        with self._lock:
            receipt = self.status(identity)
            if receipt["kind"] not in VISION_READ_OPERATIONS:
                raise ValueError("Only an image analysis or tag suggestion can be stopped here")
            if receipt["state"] in {"completed", "failed", "cancelled"}:
                return receipt
            if identity not in self._active:
                raise OperationConflict("Image operation is unconfirmed; inspect its saved state")
            self.journal.request_cancel(identity, OWNER)
            self._jobs.cancel(identity)
            return self.status(identity)

    def vision_results(self, identity: str, revision: int) -> dict[str, Any]:
        from .browser_vision import results

        view = results(self.cfg, identity, revision)
        if view["pending"] is not None:
            with self._lock:
                view["pending"]["cancellable"] = view["pending"]["request_id"] in self._active
        return view

    def clear_vision_review(self, identity: str, revision: int, result: str) -> None:
        from .browser_results import BrowserResults
        from .browser_vision import _current

        _current(self.cfg, identity, revision)
        BrowserResults(self.cfg.data_dir).clear_analysis(identity, revision, result)

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


def run_management_operation(request: dict[str, Any], progress=None) -> dict[str, Any]:
    """Fixed private worker entry; no browser-supplied roots, commands or imports."""
    from klaude_core.config import load_config

    cfg = load_config()
    data = Path(request["data_dir"])
    if cfg.data_dir.resolve() != data.resolve():
        raise ValueError("Operation root changed")
    journal = OperationJournal(data / "operations.db")
    operation = request["operation"]
    if (operation.startswith("mcp-") or operation in WITNESSED
            or operation in browser_model_settings.WRITES):
        # The shared definition writer records its witness while admission is
        # still accepted, then starts and checks the effect inside the file lock.
        journal.renew(request["request_id"], OWNER, request["fence"])
    else:
        journal.check_effect(request["request_id"], OWNER, request["fence"])
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
    elif operation in {"tags", "archive", "restore", "delete", "clear_ai_tags", "source_link"}:
        try:
            store.change(
                request["target"], request["revision"], operation, request.get("value", ""),
                **({"remove_ai_tags": request["remove_ai_tags"]}
                   if "remove_ai_tags" in request else {}),
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
    elif operation == "knowledge-delete":
        from .browser_knowledge import delete_knowledge

        try:
            delete_knowledge(data / "knowledge.lance", request["library"], request["source"],
                             request["fingerprint"])
        except ValueError:
            return {"rejected": True}
    elif operation.startswith("knowledge-"):
        from .library_knowledge import run_operation

        result = run_operation(request["knowledge_request"])
        if result.get("status") == "rejected":
            return {"rejected": True}
        if result.get("status") not in {"learned", "unchanged", "refreshed"}:
            return {"ok": False}
    elif operation in browser_model_settings.OPERATIONS:
        return browser_model_settings.run(cfg, request)
    elif operation in model_store.OPERATIONS:
        return model_store.run(cfg, request, progress)
    elif operation in GENERATED_OPERATIONS:
        try:
            return run_generated_operation(cfg, request)
        except ValueError:
            return {"rejected": True}
    elif operation in MEDIA_SETTINGS_OPERATIONS:
        from klaude_core.settings_store import SettingsConflictError

        try:
            return run_media_setting(cfg, request)
        except (ValueError, SettingsConflictError):
            return {"rejected": True}
    elif operation in VISION_OPERATIONS:
        try:
            return run_vision_operation(cfg, request)
        except ValueError:
            return {"rejected": True}
    elif operation in PROFILE_OPERATIONS:
        return run_profile_operation(cfg, request)
    else:
        raise ValueError("Unknown operation")
    return {"ok": True}
