"""Authenticated HTTP/SSE adapter for bounded workspace conversations."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from klaude_application import HeadlessApplication
from klaude_application.browser_jobs import generated_jobs
from klaude_application.browser_media_settings import OPERATIONS as MODEL_SETTINGS_OPERATIONS
from klaude_application.browser_models import BrowserModels
from klaude_application.browser_sessions import public_markdown, workspace_sessions
from klaude_application.browser_settings import read_browser_settings
from klaude_application.browser_tools import ASSISTANT_READ_TOOLS
from klaude_application.chat_attachments import prepare_attachment
from klaude_application.contracts import UserInputRequest
from klaude_application.coordination import CursorExpired
from klaude_application.library_artifacts import ArtifactService
from klaude_application.library_management import LibraryManagement
from klaude_application.local_runtime import saved_local_choice
from klaude_application.mcp_inventory import read_mcp_inventory
from klaude_application.memory_inventory import read_memory_inventory
from klaude_application.model_capabilities import read_capabilities
from klaude_application.operation_journal import OperationConflict
from klaude_application.workspace_reads import WorkspaceReadService
from klaude_core.config import Config
from klaude_core.image_preparation import prepare_image
from klaude_core.library_artifacts import image_header
from klaude_core.model_connections import (
    DEFAULT_IDS,
    ModelConnection,
    connection_registry,
    legacy_connections,
)
from klaude_core.model_discovery import ModelDiscoveryError, discover_connection
from klaude_core.model_runtime import ModelInfo
from klaude_tools import build_tools

from .accounts import AccountIdentity, AccountStore, LoginLimited, LoginLimiter
from .attachments import ChatAttachments
from .chat_previews import PREVIEW_CSP, ChatPreviews
from .lan import lan_ipv4_addresses, private_lan_ip
from .library_images import ImageBusy, LibraryImages
from .transfers import MAX_UPLOAD, BrowserTransfers, display_filename

COOKIE = "klaude_webui_session"
MAX_BODY = 256 * 1024
STATIC = Path(__file__).with_name("static")
# Packaged manifest is the explicit publication allowlist; directory contents are not.
AI_ICON_NAMES = frozenset(
    name for name in json.loads((STATIC / "icons" / "ai" / "manifest.json").read_text())["icons"]
    if re.fullmatch(r"[a-z0-9-]+", name)
)

READ_ONLY_TOOLS = frozenset({
    "read_file", "list_dir", "workspace_info", "grep", "git_status", "git_diff",
}) | ASSISTANT_READ_TOOLS
FILE_EDIT_TOOLS = frozenset({"write_file", "edit_file"})


@dataclass
class _BrowserSession:
    csrf: str
    created: float
    touched: float
    clients: dict[str, float] = field(default_factory=dict)
    account_revision: int | None = None
    account: AccountIdentity | None = None


class _BoundedHTTPServer(ThreadingHTTPServer):
    """Limit live request threads before creating a handler."""

    request_queue_size = 32

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._admission = threading.BoundedSemaphore(64)
        super().__init__(*args, **kwargs)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._admission.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._admission.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._admission.release()


class LocalWebHost:
    """Own a loopback listener and an optional private-network HTTP listener."""

    def __init__(
        self, application: HeadlessApplication, *, port: int = 0,
        staging_dir: Path | None = None,
        accounts: AccountStore | None = None,
        library: LibraryManagement | None = None,
        application_factory: Callable[[], HeadlessApplication] | None = None,
    ) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("invalid port")
        self.application = application
        self._application_factory = application_factory
        self._applications = [application]
        self._application_edits: dict[int, bool] = {}
        self.accounts = accounts
        self.library = library
        self._library_downloads = threading.BoundedSemaphore(2)
        self._attachment_reads = threading.BoundedSemaphore(2)
        self.library_images = LibraryImages()
        self.chat_previews = ChatPreviews()
        self.login_limiter = LoginLimiter()
        self.transfers: BrowserTransfers | None = None
        self.attachments = ChatAttachments()
        self._lock = threading.RLock()
        self._bootstrap = secrets.token_urlsafe(32)
        self._bootstrap_until = time.monotonic() + 60
        self._bootstrap_attempts = 0
        self._stopping = False
        self._sessions: dict[str, _BrowserSession] = {}
        self._decision_receipts: dict[str, tuple[str, str, str, bool]] = {}
        self._activation_receipts: dict[str, tuple[str, int, dict[str, Any]]] = {}
        self._session_receipts: dict[str, tuple[str, str, str]] = {}
        self._message_receipts: dict[
            str, tuple[str, str, str, str, str, str | None]
        ] = {}
        self._edits_activated = False
        self._streams = threading.BoundedSemaphore(32)
        self._stream_condition = threading.Condition()
        self._stream_count = 0
        self.http = _BoundedHTTPServer(("127.0.0.1", port), _Handler)
        try:
            self.transfers = BrowserTransfers(staging_dir) if staging_dir is not None else None
        except BaseException:
            self.http.server_close()
            raise
        self.http.daemon_threads = True
        self.http.host_owner = self  # type: ignore[attr-defined]
        self.authority = f"127.0.0.1:{self.http.server_port}"
        self.origin = f"http://{self.authority}"
        self.http.host_authority = self.authority  # type: ignore[attr-defined]
        self.http.host_origin = self.origin  # type: ignore[attr-defined]
        self.http.host_lan = False  # type: ignore[attr-defined]
        self._lan_http: _BoundedHTTPServer | None = None
        self._lan_thread: threading.Thread | None = None
        self.lan_ip = ""
        self.lan_origin = ""
        self.lan_fingerprint = ""
        self.lan_remote_peer = ""
        self.lan_remote_seen_at = 0.0
        self._local_ipv4s: frozenset[str] = frozenset({"127.0.0.1"})

    @property
    def bootstrap_url(self) -> str:
        return self.bootstrap_url_for()

    def bootstrap_url_for(self, *, lan: bool = False) -> str:
        with self._lock:
            origin = self.lan_origin if lan else self.origin
            if not origin:
                raise RuntimeError("LAN listener is unavailable")
            return origin + '/' if self.accounts is not None else f"{origin}/#{self._bootstrap}"

    def new_bootstrap_url(self, *, lan: bool = False) -> str:
        """Issue a fresh, short-lived one-use URL for the local owner."""
        with self._lock:
            if self._stopping:
                raise RuntimeError("Web UI is stopping")
            self._bootstrap = secrets.token_urlsafe(32)
            self._bootstrap_until = time.monotonic() + 60
            self._bootstrap_attempts = 0
            return self.bootstrap_url_for(lan=lan)

    def start_lan(self, ip: str, directory: Path) -> None:
        private_lan_ip(ip)
        with self._lock:
            if any(app.agent.workspace.write_enabled for app in self._applications):
                raise RuntimeError("Disable file edits by restarting the host before LAN preview")
            if self._lan_http is not None:
                if self.lan_ip == ip:
                    return
                raise RuntimeError("Disable the current LAN listener before changing its IP")
            listener = _BoundedHTTPServer((ip, self.http.server_port), _Handler)
            listener.daemon_threads = True
            listener.host_owner = self  # type: ignore[attr-defined]
            listener.host_authority = f"{ip}:{listener.server_port}"  # type: ignore[attr-defined]
            listener.host_origin = f"http://{ip}:{listener.server_port}"  # type: ignore[attr-defined]
            listener.host_lan = True  # type: ignore[attr-defined]
            self._lan_http = listener
            self.lan_ip = ip
            self.lan_origin = listener.host_origin  # type: ignore[attr-defined]
            self.lan_fingerprint = ""
            self.lan_remote_peer = ""
            self.lan_remote_seen_at = 0.0
            self._local_ipv4s = frozenset({"127.0.0.1", ip, *lan_ipv4_addresses()})
            self._lan_thread = threading.Thread(
                target=listener.serve_forever, kwargs={"poll_interval": 0.2},
                name="klaude-webui-lan", daemon=True,
            )
            self._lan_thread.start()

    def stop_lan(self) -> None:
        with self._lock:
            listener, thread = self._lan_http, self._lan_thread
            self._lan_http = None
            self._lan_thread = None
            self.lan_ip = ""
            self.lan_origin = ""
            self.lan_fingerprint = ""
            self.lan_remote_peer = ""
            self.lan_remote_seen_at = 0.0
        if listener is not None:
            listener.shutdown()
            listener.server_close()
        if thread is not None:
            thread.join(timeout=2)

    def exchange(self, code: str) -> tuple[str, str] | None:
        with self._lock:
            if self._stopping or self.accounts is not None:
                return None
            if self._bootstrap_attempts >= 5:
                return None
            self._bootstrap_attempts += 1
            if (time.monotonic() > self._bootstrap_until
                    or not hmac.compare_digest(code, self._bootstrap)):
                return None
            self._bootstrap = ""
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            now = time.monotonic()
            self._sessions[hashlib.sha256(token.encode()).hexdigest()] = (
                _BrowserSession(csrf, now, now)
            )
            return token, csrf

    def login(self, username: str, password: str, peer: str) -> tuple[str, str] | None:
        if self.accounts is None:
            return None
        self.login_limiter.admit(peer)
        if not self.login_limiter.workers.acquire(blocking=False):
            raise LoginLimited
        try:
            account = self.accounts.verify(username, password)
        finally:
            self.login_limiter.workers.release()
        if account is None:
            return None
        with self._lock:
            if self._stopping or self.accounts.identity(account.username) != account:
                return None
            now = time.monotonic()
            # Retain a bounded number of sessions, including abandoned browser logins.
            expired = [key for key, item in self._sessions.items()
                       if now - item.touched > 1800 or now - item.created > 43200]
            for key in expired:
                self.logout(key)
            if len(self._sessions) >= 64:
                raise LoginLimited
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self._sessions[hashlib.sha256(token.encode()).hexdigest()] = _BrowserSession(
                csrf, now, now, account_revision=account.revision, account=account,
            )
            return token, csrf

    def _account_current(self, session: _BrowserSession) -> bool:
        if self.accounts is None:
            return session.account_revision is None
        try:
            return (session.account is not None
                    and self.accounts.identity(session.account.username) == session.account)
        except (OSError, ValueError):
            return False

    def note_lan_peer(self, peer: str) -> None:
        with self._lock:
            if self.lan_ip and peer not in self._local_ipv4s:
                self.lan_remote_peer = peer
                self.lan_remote_seen_at = time.time()

    def authenticate(self, cookie_header: str) -> tuple[str, _BrowserSession] | None:
        if len(cookie_header) > 4096:
            return None
        jar = SimpleCookie()
        try:
            jar.load(cookie_header)
        except Exception:
            return None
        if COOKIE not in jar:
            return None
        token = jar[COOKIE].value
        if len(token) > 128:
            return None
        identity = hashlib.sha256(token.encode()).hexdigest()
        with self._lock:
            session = self._sessions.get(identity)
            if session is None:
                return None
            if not self._account_current(session):
                self.logout(identity)
                return None
            now = time.monotonic()
            if now - session.touched > 1800 or now - session.created > 43200:
                self._sessions.pop(identity, None)
                return None
            session.touched = now
            return identity, session

    def logout(self, identity: str) -> None:
        with self._lock:
            self.chat_previews.revoke(identity)
            session = self._sessions.pop(identity, None)
            if self.transfers is not None:
                self.transfers.revoke(identity)
            self.attachments.revoke(identity)
            if self.library is not None and session is not None:
                for client in session.clients:
                    self.library.revoke(client)
            for app in self._applications:
                control = app.control()
                if control is not None and (control[0] == identity or
                                            session is not None and control[0] in session.clients):
                    app.close_interactions()

    def session_active(self, identity: str) -> bool:
        with self._lock:
            if self._stopping:
                return False
            session = self._sessions.get(identity)
            if session is None:
                return False
            now = time.monotonic()
            return (self._account_current(session) and now - session.touched <= 1800
                    and now - session.created <= 43200)

    def attach_client(self, identity: str) -> str:
        with self._lock:
            session = self._sessions.get(identity)
            if session is None or self._stopping:
                raise RuntimeError("Browser session is unavailable")
            now = time.monotonic()
            session.clients = {
                key: touched for key, touched in session.clients.items()
                if now - touched <= 1800
            }
            if len(session.clients) >= 16:
                raise RuntimeError("Too many browser clients")
            client_id = secrets.token_hex(16)
            session.clients[client_id] = now
            return client_id

    def browser_client(self, identity: str, client_id: str | None) -> str | None:
        with self._lock:
            session = self._sessions.get(identity)
            if session is None:
                return None
            if not session.clients:
                return identity if client_id is None else None
            if client_id is None:
                return None
            touched = session.clients.get(client_id)
            if touched is None or time.monotonic() - touched > 1800:
                return None
            session.clients[client_id] = time.monotonic()
            return client_id

    def public_snapshot(self, viewer_id: str | None = None) -> dict[str, Any]:
        """One bounded public projection for browser and same-account IPC."""
        with self._lock:
            return self._public_snapshot(viewer_id)

    def _public_snapshot(self, viewer_id: str | None = None) -> dict[str, Any]:
        snapshot = self.application.snapshot(viewer_id=viewer_id)
        edits_enabled = self._edits_activated and self.application.agent.workspace.write_enabled
        messages = []
        budget = 700_000
        candidates = {item["id"]: item for item in snapshot["messages"]}
        selected_ids: set[str] = set()
        pending_messages = list(reversed(snapshot["messages"][-100:]))
        active_root = snapshot["retry_root"]
        if active_root:
            original = candidates.get(active_root)
            if original is None:
                saved = self.application.sessions.public_message(
                    snapshot["session_id"], int(active_root.removeprefix("stored:")),
                )
                if saved is not None:
                    original = asdict(saved)
                    original.update(retry_root=active_root, previous_response=True)
            if original is not None:
                pending_messages.insert(0, original)
        while pending_messages:
            item = pending_messages.pop(0)
            if item["id"] in selected_ids:
                continue
            root = item.get("retry_root")
            if root and root != item["id"] and root not in selected_ids:
                original = candidates.get(root)
                if original is None:
                    saved = self.application.sessions.public_message(
                        snapshot["session_id"], int(root.removeprefix("stored:")),
                    )
                    if saved is not None:
                        original = asdict(saved)
                        original.update(retry_root=root, previous_response=True)
                if original is not None:
                    pending_messages.insert(0, original)
            content = item["content"][:16_000]
            size = len(content.encode("utf-8"))
            if item.get("attachments"):
                size += len(json.dumps(item["attachments"]).encode("utf-8"))
            if size > budget:
                break
            messages.append({"id": item["id"], "role": item["role"],
                             "content": content, "created_at": item["created_at"]})
            selected_ids.add(item["id"])
            for attribute in ("retry_root", "previous_response"):
                if attribute in item:
                    messages[-1][attribute] = item[attribute]
            if item.get("attachments"):
                messages[-1]["attachments"] = item["attachments"]
            budget -= size
        messages.sort(key=lambda item: int(item["id"].removeprefix("stored:")))
        approvals = []
        questions = []
        # Authenticated clients belong to the same local owner. Show the exact
        # pending review to each client; its explicit response acquires control
        # before using the existing fenced decision path.
        control = self.application.control()
        review_identity = control[0] if control else viewer_id
        review_epoch = control[1] if control else snapshot["control_epoch"]
        for pending in self.application.pending_interactions(
            controller_id=review_identity,
            control_epoch=review_epoch,
        ):
            if isinstance(pending, UserInputRequest):
                questions.append({
                    "id": pending.id, "header": pending.header,
                    "question": pending.question, "options": list(pending.options),
                })
            else:
                review = self.application.review_interaction(
                    pending.id, controller_id=review_identity,
                    control_epoch=review_epoch,
                )
                external: frozenset[str] = getattr(
                    getattr(self.application.agent, "browser_tools", None),
                    "mcp_names", frozenset(),
                )
                allowed = READ_ONLY_TOOLS | external | (
                    FILE_EDIT_TOOLS if edits_enabled else frozenset()
                )
                if review is not None and review["tool"] in allowed:
                    approvals.append({"id": pending.id, **review})
        return {
            "api_version": "1", "session_id": snapshot["session_id"],
            "message_actions": True,
            "message_retry_in_place": True,
            "retry_root": snapshot["retry_root"],
            "attachments": True,
            "attachment_content": True,
            "library_images": True,
            "library_source_links": True,
            "library_source_notes": True,
            "library_ai_tag_edit": self.library is not None,
            "library_artifact_sources": True,
            "profile_management": self.library is not None,
            "media_management": self.library is not None,
            "model_store": self.library is not None,
            "model_download_dismissal": self.library is not None,
            "model_download_recovery": self.library is not None,
            "image_studio": self.library is not None,
            "model_settings": self.library is not None,
            "model_store_catalog": self.library is not None,
            "requires_model_selection": snapshot.get("requires_model_selection", False),
            "model_providers": getattr(self.application.agent, "browser_models", None) is not None,
            "model_connection": self.application.agent.model_info.connection_id,
            "effort_levels": list(self.application.agent.model_info.capabilities.effort_levels),
            "messages": messages, "state": snapshot["state"],
            "activity": snapshot["activity"],
            "inspector": snapshot.get("inspector"),
            "context_panel": True,
            "partial": snapshot["partial"][:64_000],
            "cursor": snapshot["cursor"],
            "model": self.application.agent.model,
            "model_ref": self.application.agent.model_info.ref,
            "provider": self.application.agent.model_info.backend,
            "mode": self.application.agent.reasoning_mode,
            "effort": (self.application.agent.reasoning_effort
                       if self.application.agent.reasoning_mode == "thinking" else None),
            "tools": "file edits enabled" if edits_enabled else (
                "Workspace read-only · MCP reviews"
                if getattr(getattr(self.application.agent, "browser_tools", None), "mcp_names", ())
                else "read-only"
            ),
            "approvals": approvals, "questions": questions,
            "active_turn_id": self.application.active_turn_id(),
            "parallel_sessions": self._application_factory is not None,
            "has_control": snapshot["has_control"],
            "control_epoch": snapshot["control_epoch"],
            "queue": snapshot["queue"],
            "plan_mode": snapshot["plan_mode"],
            "settings_revision": snapshot["settings_revision"],
            "workspace_bound": snapshot["workspace_bound"],
            "workspace_revision": snapshot["workspace_revision"],
            "history_truncated": len(messages) < len(snapshot["messages"]),
        }

    def sessions(self, *, archived: bool = False) -> list[dict[str, Any]]:
        """Show only bounded sessions bound to this host's workspace."""
        with self._lock:
            rows = []
            for item in workspace_sessions(
                self.application.memory, self.application.agent.workdir, archived=archived,
            ):
                try:
                    models = getattr(self.application.agent, "browser_models", None)
                    if models is not None:
                        try:
                            models.saved(self.application.memory, item["session_id"])
                        except ValueError:
                            saved_local_choice(
                                self.application.agent, self.application.memory, item["session_id"],
                            )
                    else:
                        saved_local_choice(
                            self.application.agent, self.application.memory, item["session_id"],
                        )
                    compatible = True
                except ValueError:
                    compatible = False
                running = next((app for app in self._applications
                                if app.session_id == item["session_id"]), None)
                active = bool(running and running.active_turn_id())
                rows.append({**item, "resumable": compatible or active, "active": active})
                if len(rows) >= 30:
                    break
            return rows

    def _local_connection(self) -> tuple[Config, ModelConnection]:
        cfg = self.application.agent.tool_config
        if not isinstance(cfg, Config):
            raise ValueError("local model configuration unavailable")
        registry = connection_registry(cfg)
        choices = (
            registry.load() if registry.path.exists()
            else {item.id: item for item in legacy_connections(cfg)}
        )
        connection = choices.get(DEFAULT_IDS["ollama"])
        if (connection is None or not connection.enabled or connection.backend != "ollama"
                or connection.base_url != cfg.ollama_url or connection.key_env):
            raise ValueError("configured local Ollama connection unavailable")
        return cfg, connection

    def local_models(self) -> list[dict[str, str]]:
        """List bounded, live local catalog metadata without generation."""
        _cfg, connection = self._local_connection()
        return [
            {"id": info.model_id, "name": info.display_name}
            for info in discover_connection(connection)[:100]
        ]

    def verified_local_model(self, model_id: str) -> ModelInfo:
        """Require the exact installed model and declared tools before selection."""
        cfg, connection = self._local_connection()
        found = next((info for info in discover_connection(connection)
                      if info.model_id == model_id), None)
        if found is None:
            raise ValueError("model is not in the current local catalog")
        check = read_capabilities({
            "connection": asdict(connection), "models": [model_id],
            "credential_revision": "", "config_dir": str(cfg.config_dir),
            "data_dir": str(cfg.data_dir), "ollama_url": cfg.ollama_url,
            "roles": dict(cfg.models),
        })
        records = check.get("models", [])
        declared = records[0].get("declared") if check.get("status") == "ok" and records else None
        if (not isinstance(declared, list)
                or "completion" not in declared or "tools" not in declared):
            raise ValueError("exact model tool capability is unavailable")
        thinking = "thinking" in declared
        caps = replace(
            found.capabilities,
            thinking_types=("disabled", "enabled") if thinking else ("disabled",),
            effort_levels=("off", "medium") if thinking else ("off",),
            supports_tools=True, tools_evidence="api/show",
            supports_images="vision" in declared, images_evidence="api/show",
        )
        return replace(found, capabilities=caps)

    @staticmethod
    def _application_busy(app: HeadlessApplication) -> bool:
        return bool(app.active_turn_id() or app.turns.queue(
            app.session_id, app.controller_id, include_submitted=False,
        ))

    def _new_application(self) -> HeadlessApplication:
        if self._application_factory is None:
            raise RuntimeError("Finish active work before switching sessions")
        # Each live conversation owns its Agent, runtime, broker, queue and lease.
        # Evict only idle, unselected instances; never cancel work to free a slot.
        if len(self._applications) >= 4:
            idle = next((app for app in self._applications
                         if app is not self.application and not self._application_busy(app)), None)
            if idle is None:
                raise RuntimeError("Four conversations are running; wait for a reply or cancel one")
            asyncio.run(idle.close())
            self._applications.remove(idle)
            self._application_edits.pop(id(idle), None)
        return self._application_factory()

    def switch_session(
        self, viewer: str, request_id: str, expected_session_id: str,
        session_id: str, control_epoch: int,
    ) -> str:
        """Select a conversation without mutating another conversation's worker."""
        with self._lock:
            previous = self._session_receipts.get(request_id)
            if previous is not None:
                if previous[:2] != (viewer, session_id):
                    raise ValueError("request ID conflict")
                if self.application.session_id != previous[2]:
                    raise ValueError("session changed after request")
                return previous[2]
            source = self.application
            if self._stopping or source.session_id != expected_session_id:
                raise ValueError("session changed")
            control = source.control()
            if control is not None and control != (viewer, control_epoch):
                raise ValueError("session control changed")
            if session_id:
                if self.library is not None and self.library.session_busy(session_id):
                    raise RuntimeError("Conversation management change is active or unconfirmed")
                binding = source.turns.workspace(session_id)
                if binding is None or binding[0] != str(source.agent.workdir.resolve()):
                    raise ValueError("session belongs to another workspace")
            candidate = next((app for app in self._applications
                              if session_id and app.session_id == session_id), None)
            created = False
            if candidate is None:
                if self._application_busy(source):
                    candidate = self._new_application()
                    created = True
                else:
                    candidate = source
            running = self._application_busy(candidate)
            try:
                if running:
                    if candidate.session_id != session_id:
                        raise RuntimeError("Finish active work before switching sessions")
                    selected = session_id
                else:
                    if session_id:
                        if self.library is not None and self.library.session_busy(session_id):
                            raise RuntimeError(
                                "Conversation management change is active or unconfirmed"
                            )
                        binding = candidate.turns.workspace(session_id)
                        if (binding is None or binding[0] !=
                                str(candidate.agent.workdir.resolve())):
                            raise ValueError("session belongs to another workspace")
                        models = getattr(candidate.agent, "browser_models", None)
                        if models is not None:
                            try:
                                models.saved(candidate.memory, session_id)
                            except ValueError:
                                candidate.resume_local(session_id)
                            else:
                                candidate.resume_configured(session_id)
                        else:
                            candidate.resume_local(session_id)
                        selected = session_id
                    else:
                        from klaude_core.ai_defaults import read_defaults
                        from klaude_core.settings_store import read_settings

                        cfg = candidate.agent.tool_config
                        info, require_selection = None, False
                        if isinstance(cfg, Config):
                            preferences = read_settings(cfg.data_dir / "chat-preferences.json")
                            selections = preferences.get("model_default_selections", {})
                            if isinstance(selections, dict) and selections.get("chat") in {
                                "manual", "automatic"
                            }:
                                reference = read_defaults(cfg).chat
                                if reference:
                                    info = BrowserModels(cfg).verify_ref(reference)
                                else:
                                    require_selection = True
                        if created and info is None and not require_selection:
                            # With no new-chat default, preserve the source choice
                            # using a fresh runtime, never the running runtime object.
                            source_info = source.agent.model_info
                            if candidate.agent.model_info != source_info:
                                revision = candidate.snapshot()["settings_revision"]
                                if source_info.connection_id:
                                    candidate.choose_configured_model(
                                        source_info, expected_revision=revision,
                                        request_id=secrets.token_hex(16),
                                    )
                                else:
                                    candidate.choose_local_model(
                                        source_info, expected_revision=revision,
                                        request_id=secrets.token_hex(16),
                                    )
                            source_effort = (source.agent.reasoning_effort
                                             if source.agent.reasoning_mode == "thinking" else None)
                            candidate_effort = (candidate.agent.reasoning_effort
                                                if candidate.agent.reasoning_mode == "thinking"
                                                else None)
                            if (candidate.agent.reasoning_mode != source.agent.reasoning_mode
                                    or candidate_effort != source_effort):
                                candidate.choose_reasoning(
                                    source.agent.reasoning_mode, source_effort,
                                    expected_revision=candidate.snapshot()["settings_revision"],
                                    request_id=secrets.token_hex(16),
                                )
                        selected = candidate.start_session(
                            model_info=info, require_selection=require_selection,
                        )
            except BaseException:
                if created:
                    asyncio.run(candidate.close())
                raise
            if created:
                self._applications.append(candidate)
            # Idle switches revoke edit activation as before. An in-flight worker
            # retains its own reviewed tools; returning to it restores that state.
            self._application_edits[id(source)] = self._edits_activated
            if candidate is not source and not self._application_busy(source):
                source.agent.workspace.write_enabled = False
                for name in FILE_EDIT_TOOLS:
                    source.agent.tools.pop(name, None)
                self._application_edits[id(source)] = False
            self.application = candidate
            if not running:
                if session_id:
                    candidate.requires_model_selection = False
                candidate.agent.workspace.write_enabled = False
                for name in FILE_EDIT_TOOLS:
                    candidate.agent.tools.pop(name, None)
            self._edits_activated = bool(
                running and self._application_edits.get(id(candidate), False)
            )
            self._activation_receipts.clear()
            self._decision_receipts.clear()
            if len(self._session_receipts) >= 128:
                self._session_receipts.pop(next(iter(self._session_receipts)))
            self._session_receipts[request_id] = (viewer, session_id, selected)
            return selected

    def message_action(
        self, viewer: str, request_id: str, source: str, message_id: str,
        action: str, control_epoch: int,
    ) -> str:
        """Branch explicitly, or retry in place while preserving saved replies."""
        with self._lock:
            if action not in ("branch", "retry"):
                raise ValueError("Invalid message action")
            key = (viewer, source, message_id, action)
            previous = self._message_receipts.get(request_id)
            if previous is not None:
                if previous[:4] != key or self.application.session_id != previous[4]:
                    raise ValueError("Message action changed; reload")
                selected, prompt = previous[4:]
            else:
                if self._stopping or source != self.application.session_id:
                    raise ValueError("Session changed; reload")
                control = self.application.control()
                if (action != "retry" and control is not None
                        and control != (viewer, control_epoch)):
                    raise ValueError("Session control changed")
                if not message_id.startswith("stored:") or not message_id[7:].isdigit():
                    raise ValueError("Choose a saved assistant reply")
                row_id = int(message_id[7:])
                if not 0 < row_id <= 2**63 - 1:
                    raise ValueError("Choose a saved assistant reply")
                if action == "retry":
                    self.application.retry_message(
                        row_id,
                        request_id="retry:" + hashlib.sha256(request_id.encode()).hexdigest(),
                        controller_id=viewer,
                        control_epoch=control_epoch,
                    )
                    selected, prompt = source, None
                else:
                    selected, prompt = self.application.branch_message(row_id)
                    self.application.agent.workspace.write_enabled = False
                    for name in FILE_EDIT_TOOLS:
                        self.application.agent.tools.pop(name, None)
                    self._edits_activated = False
                    self._activation_receipts.clear()
                    self._decision_receipts.clear()
                if len(self._message_receipts) >= 128:
                    self._message_receipts.pop(next(iter(self._message_receipts)))
                self._message_receipts[request_id] = (*key, selected, prompt)
            return selected

    def activate_edits(
        self, owner: str, request_id: str, expected_revision: int,
        expected_session_id: str | None = None,
    ) -> dict[str, Any]:
        """Explicit clean-worktree branch activation before file tools exist."""
        with self._lock:
            if self._stopping:
                raise RuntimeError("Web UI is stopping")
            if (expected_session_id is not None
                    and expected_session_id != self.application.session_id):
                raise ValueError("session changed")
            if self._lan_http is not None:
                raise RuntimeError("Disable LAN preview before enabling file edits")
            previous = self._activation_receipts.get(request_id)
            if previous is not None:
                if previous[:2] != (owner, expected_revision):
                    raise ValueError("activation request ID conflict")
                return previous[2]
            control = self.application.control()
            if control is not None and control[0] != owner:
                raise RuntimeError("Session control changed; try the action again")
            snapshot = self.application.snapshot(viewer_id=owner)
            if snapshot["workspace_revision"] != expected_revision:
                raise ValueError("stale workspace revision")
            if self._edits_activated and self.application.agent.workspace.write_enabled:
                result = {"enabled": True, "status": "File edits already enabled"}
            else:
                status = self.application.activate_workspace()
                enabled = self.application.agent.workspace.write_enabled
                if enabled:
                    tools = {tool.name: tool for tool in build_tools(
                        self.application.agent.workspace
                    ) if tool.name in FILE_EDIT_TOOLS}
                    self.application.agent.tools.update(tools)
                    for name in FILE_EDIT_TOOLS:
                        if self.application.agent.gate.policies.get(name) != "deny":
                            self.application.agent.gate.policies[name] = "ask"
                        self.application.agent.gate.process_grants.discard(name)
                    self._edits_activated = True
                result = {"enabled": enabled, "status": status[:500]}
            if len(self._activation_receipts) >= 128:
                self._activation_receipts.pop(next(iter(self._activation_receipts)))
            self._activation_receipts[request_id] = (owner, expected_revision, result)
            return result

    def serve_forever(self) -> None:
        self.http.serve_forever(poll_interval=0.2)

    def begin_shutdown(self) -> None:
        """Revoke browser authority before acknowledging listener shutdown."""
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            self._bootstrap = ""
            self._sessions.clear()
            self._decision_receipts.clear()
            self._activation_receipts.clear()
            for app in self._applications:
                app.close_interactions()
            if self.transfers is not None:
                self.transfers.revoke_all()
            self.attachments.revoke()
            self.library_images.clear()
            self.chat_previews.revoke()

    def stop(self) -> None:
        self.begin_shutdown()
        self.stop_lan()
        self.http.shutdown()
        self.http.server_close()
        deadline = time.monotonic() + 3
        with self._stream_condition:
            while self._stream_count and time.monotonic() < deadline:
                self._stream_condition.wait(deadline - time.monotonic())
        try:
            for app in self._applications:
                asyncio.run(app.close(drain=True))
        finally:
            if self.library is not None:
                self.library.close()
            if self.transfers is not None:
                self.transfers.close()


class _Handler(BaseHTTPRequestHandler):
    server_version = "KlaudeWebUI/0.1"

    def handle(self) -> None:
        try:
            super().handle()
        except (ConnectionResetError, BrokenPipeError):
            self.close_connection = True
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    @property
    def owner(self) -> LocalWebHost:
        return self.server.host_owner  # type: ignore[attr-defined,return-value]

    def log_message(self, _format: str, *_args: object) -> None:
        # No paths, cookies, bootstrap fragments or prompt bodies enter access logs.
        return

    def _headers(self, status: int, content_type: str, length: int | None = None,
                 *, cookie: str = "", attachment: str = "", preview: bool = False) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if not preview:
            self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            PREVIEW_CSP if preview else
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self' https: http:; font-src 'self'; "
            "img-src 'self' data: blob: https: http:; "
            "frame-src 'self'; "
            "form-action 'self' https://lens.google.com https://www.google.com; base-uri 'none'; "
            "object-src 'none'; frame-ancestors 'none'",
        )
        if length is not None:
            self.send_header("Content-Length", str(length))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()

    def _json(self, status: int, value: dict[str, Any], *, cookie: str = "") -> None:
        payload = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
        try:
            self._headers(status, "application/json; charset=utf-8", len(payload), cookie=cookie)
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    def _error(self, status: int, code: str, message: str) -> None:
        self.close_connection = True
        self._json(status, {"error": {"code": code, "message": message}})

    def _same_host(self) -> bool:
        lan = getattr(self.server, "host_lan", False)
        valid = ((lan or self.client_address[0] == "127.0.0.1")
                 and self.headers.get_all("Host", []) == [
                     getattr(self.server, "host_authority", "")
                 ])
        if valid and lan:
            self.owner.note_lan_peer(self.client_address[0])
        return valid

    def _browser_source_ok(self, *, mutation: bool) -> bool:
        sites = self.headers.get_all("Sec-Fetch-Site", [])
        if len(sites) > 1:
            return False
        site = sites[0] if sites else None
        if site not in (None, "same-origin", "none"):
            return False
        origins = self.headers.get_all("Origin", [])
        if len(origins) > 1:
            return False
        origin = origins[0] if origins else None
        expected = getattr(self.server, "host_origin", "")
        return origin == expected if mutation else origin in (None, expected)

    def _admin_management_allowed(self) -> bool:
        # Embedded bootstrap hosts preserve their existing loopback authority.
        # Account-backed hosts always authorize the validated principal's role,
        # independently of listener/address, username or client-supplied fields.
        if self.owner.accounts is None:
            return not bool(getattr(self.server, "host_lan", False))
        auth = self.owner.authenticate(self.headers.get("Cookie", ""))
        return bool(auth and auth[1].account and auth[1].account.role == "admin")

    def _mcp_management_allowed(self) -> bool:
        return self._admin_management_allowed()

    def _authenticated(self, *, mutation: bool = False) -> tuple[str, _BrowserSession] | None:
        if self.owner._stopping:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "host_stopping", "Web UI is stopping")
            return None
        if not self._same_host() or not self._browser_source_ok(mutation=mutation):
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "Request origin rejected")
            return None
        cookies = self.headers.get_all("Cookie", [])
        if len(cookies) > 1:
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "Ambiguous cookie")
            return None
        authenticated = self.owner.authenticate(cookies[0] if cookies else "")
        if authenticated is None:
            self._error(HTTPStatus.UNAUTHORIZED, "unauthenticated", "Sign in locally")
            return None
        csrf = self.headers.get_all("X-Klaude-CSRF", [])
        if mutation and (len(csrf) != 1 or not hmac.compare_digest(
            csrf[0], authenticated[1].csrf
        )):
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "CSRF token rejected")
            return None
        return authenticated

    def _viewer(self, identity: str) -> str | None:
        headers = self.headers.get_all("X-Klaude-Client", [])
        if len(headers) > 1 or headers and (len(headers[0]) != 32 or
                                           any(char not in "0123456789abcdef"
                                               for char in headers[0])):
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "Invalid browser client")
            return None
        viewer = self.owner.browser_client(identity, headers[0] if headers else None)
        if viewer is None:
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "Attach this browser tab again")
        return viewer

    def _body(self) -> dict[str, Any] | None:
        types = self.headers.get_all("Content-Type", [])
        if len(types) != 1 or types[0].lower() != "application/json":
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "invalid_argument", "JSON required")
            return None
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or self.headers.get_all("Transfer-Encoding"):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Ambiguous request body")
            return None
        raw_length = lengths[0]
        try:
            length = int(raw_length)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "invalid_argument",
                        "Invalid or oversized request")
            return None
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            value = None
        if not isinstance(value, dict):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid JSON object")
            return None
        return value

    def do_GET(self) -> None:
        if not self._same_host() or not self._browser_source_ok(mutation=False):
            self._error(HTTPStatus.FORBIDDEN, "forbidden", "Request origin rejected")
            return
        path = urlsplit(self.path).path
        if path in ("/fonts/Roboto.ttf", "/fonts/JetBrainsMono.ttf",
                    "/fonts/SpaceGrotesk.ttf", "/fonts/ReadexPro.ttf",
                    "/fonts/NotoSansKhmer.ttf"):
            payload = (STATIC / path.removeprefix("/")).read_bytes()
            self._headers(HTTPStatus.OK, "font/ttf", len(payload))
            self.wfile.write(payload)
            return
        if path.startswith("/icons/ai/") and path.removeprefix("/icons/ai/") in {
            f"{name}.svg" for name in AI_ICON_NAMES
        }:
            payload = (STATIC / path.removeprefix("/")).read_bytes()
            self._headers(HTTPStatus.OK, "image/svg+xml; charset=utf-8", len(payload))
            self.wfile.write(payload)
            return
        if path == "/icons/google-lens.svg":
            payload = (STATIC / "icons/google-lens.svg").read_bytes()
            self._headers(HTTPStatus.OK, "image/svg+xml; charset=utf-8", len(payload))
            self.wfile.write(payload)
            return
        if path == "/lockscreen-bg.jpg":
            payload = (STATIC / "lockscreen-bg.jpg").read_bytes()
            self._headers(HTTPStatus.OK, "image/jpeg", len(payload))
            self.wfile.write(payload)
            return
        if path in ("/", "/app.js", "/library.js", "/management.js", "/media.js", "/attachments.js",
                    "/style.css", "/markdown.js", "/lens.js", "/ai-icons.js",
                    "/loading-indicator.js", "/vendor/material-loading-shapes.js",
                    "/vendor/markdown-it.min.js", "/vendor/prism.min.js", "/vendor/katex.min.js"):
            name = {"/": "index.html", "/app.js": "app.js", "/library.js": "library.js",
                    "/attachments.js": "attachments.js",
                    "/management.js": "management.js",
                    "/media.js": "media.js",
                    "/ai-icons.js": "ai-icons.js", "/style.css": "style.css", "/markdown.js": "markdown.js", "/lens.js": "lens.js",
                    "/loading-indicator.js": "loading-indicator.js",
                    "/vendor/material-loading-shapes.js": "vendor/material-loading-shapes.js",
                    "/vendor/markdown-it.min.js": "vendor/markdown-it.min.js",
                    "/vendor/prism.min.js": "vendor/prism.min.js",
                    "/vendor/katex.min.js": "vendor/katex.min.js"}[path]
            payload = (STATIC / name).read_bytes()
            media = "text/html" if path == "/" else (
                "text/javascript" if path.endswith(".js") else "text/css"
            )
            self._headers(HTTPStatus.OK, f"{media}; charset=utf-8", len(payload))
            self.wfile.write(payload)
            return
        if path == "/api/v1/auth/method":
            self._json(HTTPStatus.OK, {
                "method": "password" if self.owner.accounts else "bootstrap",
            })
            return
        auth = self._authenticated()
        if auth is None:
            return
        if path.startswith("/api/v1/chat-previews/"):
            try:
                payload = self.owner.chat_previews.read(auth[0], path.rsplit("/", 1)[-1])
            except FileNotFoundError:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Preview expired; open it again")
                return
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(payload), preview=True)
            self.wfile.write(payload)
            return
        if path == "/api/v1/auth":
            self._json(HTTPStatus.OK, {"api_version": "1", "csrf": auth[1].csrf,
                                     "username": (auth[1].account.username
                                                  if auth[1].account else None),
                                     "role": auth[1].account.role if auth[1].account else None})
        elif path == "/api/v1/session":
            viewer = self._viewer(auth[0])
            if viewer is None:
                return
            query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            row_id = None
            if query:
                valid_query = (
                    set(query) == {"session", "message"}
                    and all(len(values) == 1 for values in query.values())
                )
                message_id = query.get("message", [""])[0]
                digits = message_id.removeprefix("stored:")
                if (not valid_query or not message_id.startswith("stored:")
                        or not digits.isascii() or not digits.isdecimal()
                        or not 0 < len(digits) <= 19 or digits.startswith("0")
                        or int(digits) > 9_223_372_036_854_775_807):
                    self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid message link")
                    return
                row_id = int(digits)
            try:
                with self.owner._lock:
                    if query and query["session"][0] != self.owner.application.session_id:
                        self._error(HTTPStatus.CONFLICT, "stale_session", "Session changed; reload")
                        return
                    snapshot = self.owner.public_snapshot(viewer)
                    if row_id is not None:
                        message = self.owner.application.sessions.public_message(
                            self.owner.application.session_id, row_id,
                        )
                        if message is None:
                            self._error(HTTPStatus.NOT_FOUND, "message_not_found",
                                        "This message is no longer available in this conversation")
                            return
                        snapshot["linked_message"] = asdict(message)
            except ValueError:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Session unavailable")
                return
            except (OSError, RuntimeError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                            "Session temporarily unavailable")
                return
            self._json(HTTPStatus.OK, snapshot)
        elif path == "/api/v1/sessions":
            if self._viewer(auth[0]) is None:
                return
            try:
                params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(params) - {"archived"} or params.get("archived", ["false"]) not in (
                    ["true"], ["false"],
                ):
                    raise ValueError("Invalid session filter")
                items = self.owner.sessions(archived=params.get("archived") == ["true"])
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid session filter")
                return
            except (OSError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                            "Sessions temporarily unavailable")
                return
            self._json(HTTPStatus.OK, {"sessions": items})
        elif path == "/api/v1/sessions/export":
            try:
                params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if set(params) != {"id"} or len(params["id"]) != 1:
                    raise ValueError("Choose a conversation")
                identity = params["id"][0]
                with self.owner._lock:
                    payload = public_markdown(
                        self.owner.application.memory,
                        self.owner.application.agent.workdir, identity,
                    )
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument",
                            "Conversation unavailable or exceeds browser export limits")
                return
            except (OSError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                            "Conversation export temporarily unavailable")
                return
            self._headers(HTTPStatus.OK, "text/markdown; charset=utf-8", len(payload),
                          attachment=f"klaude-{identity}.md")
            self.wfile.write(payload)
        elif path in {
            "/api/v1/models/store", "/api/v1/models/store/detail",
            "/api/v1/models/installed", "/api/v1/models/downloads",
        }:
            if self._viewer(auth[0]) is None:
                return
            from klaude_application import model_store

            try:
                service = self.owner.library
                if service is None:
                    raise ValueError("Model Store requires a current host")
                params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if path.endswith("/installed"):
                    if set(params) != {"connection"} or len(params["connection"]) != 1:
                        raise ValueError("Choose one native Ollama connection")
                    result = model_store.inventory(service.cfg, params["connection"][0])
                elif path.endswith("/detail"):
                    from klaude_application.model_store_catalog import detail

                    if set(params) != {"id"} or len(params["id"]) != 1:
                        raise ValueError("Choose one exact catalog model")
                    result = detail(service.cfg, params["id"][0])
                else:
                    if path.endswith("/store") and params:
                        from klaude_application.model_store_catalog import catalog

                        if (set(params) - {"source", "query", "sort", "refresh", "page"}
                                or params.get("source") != ["huggingface"]
                                or any(len(v) != 1 for v in params.values())
                                or params.get("refresh", ["0"])[0] not in {"0", "1"}):
                            raise ValueError("Unknown Model Store filter")
                        result = catalog(service.cfg, params.get("query", [""])[0],
                                         params.get("sort", ["downloads"])[0],
                                         refresh=params.get("refresh") == ["1"],
                                         page=int(params.get("page", ["1"])[0]))
                    else:
                        if params:
                            raise ValueError("Unknown Model Store filter")
                        result = (model_store.discovery() if path.endswith("/store")
                                  else service.model_jobs())
                    result["management_allowed"] = self._admin_management_allowed()
                self._json(HTTPStatus.OK, result)
            except (ValueError, OSError, RuntimeError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "model_unavailable",
                            "Model Store read unavailable; check the configured server")
        elif path in {"/api/v1/models/connections", "/api/v1/models/catalog"}:
            if self._viewer(auth[0]) is None:
                return
            try:
                cfg = self.owner.application.agent.tool_config
                if not isinstance(cfg, Config):
                    raise ValueError("Model configuration unavailable")
                models_service = BrowserModels(cfg)
                params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
                if path.endswith("/connections"):
                    if params:
                        raise ValueError("Unknown model filter")
                    model_result = {"connections": models_service.inventory()}
                else:
                    if (set(params) not in ({"connection"}, {"connection", "purpose"})
                            or len(params["connection"]) != 1
                            or ("purpose" in params and params["purpose"] != ["defaults"])):
                        raise ValueError("Choose a configured connection")
                    if "purpose" in params:
                        from klaude_application.browser_media_settings import default_model_catalog

                        model_result = {"models": default_model_catalog(
                            cfg, params["connection"][0],
                        )}
                    else:
                        model_result = {"models": [
                            {"id": item.ref, "name": item.display_name,
                             "effort_levels": list(item.capabilities.effort_levels)}
                            for item in models_service.catalog(params["connection"][0])
                        ]}
            except (ValueError, RuntimeError, OSError):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "model_unavailable",
                            "Model catalog unavailable; check the connection and credentials")
                return
            self._json(HTTPStatus.OK, model_result)
        elif path == "/api/v1/models/local":
            if self._viewer(auth[0]) is None:
                return
            try:
                models = self.owner.local_models()
            except ValueError:
                self._error(HTTPStatus.CONFLICT, "model_unavailable",
                            "Configured local model connection unavailable")
                return
            except (OSError, RuntimeError):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "model_unavailable",
                            "Local model catalog unavailable")
                return
            self._json(HTTPStatus.OK, {"models": models})
        elif path == "/api/v1/events":
            query = parse_qs(urlsplit(self.path).query)
            cursor = self.headers.get("Last-Event-ID") or query.get("after", [""])[0]
            if len(cursor) > 128:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid cursor")
                return
            self._events(auth[0], cursor)
        elif path in {"/api/v1/workspace/files", "/api/v1/workspace/file",
                      "/api/v1/workspace/search",
                      "/api/v1/workspace/status", "/api/v1/workspace/diff"}:
            self._workspace_read(path)
        elif path.startswith("/api/v1/uploads/") and path.endswith("/download"):
            self._download(auth[0], path)
        elif path == "/api/v1/chat/attachments/preview":
            self._attachment_preview(auth[0])
        elif path == "/api/v1/chat/attachments/content":
            self._attachment_content(auth[0])
        elif path.startswith("/api/v1/library/") or path in {
            "/api/v1/integrations/skills", "/api/v1/integrations/connections",
            "/api/v1/settings/memory",
            "/api/v1/settings/agent",
            "/api/v1/settings/models", "/api/v1/settings/model-connections",
        }:
            self._library_read(path, auth[0])
        else:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "Route not found")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/v1/auth/login":
            if not self._same_host() or not self._browser_source_ok(mutation=True):
                self._error(HTTPStatus.FORBIDDEN, "forbidden", "Request origin rejected")
                return
            body = self._body()
            if body is None:
                return
            if (set(body) != {"username", "password"}
                    or not isinstance(body["username"], str) or len(body["username"]) > 64
                    or not isinstance(body["password"], str) or len(body["password"]) > 256):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid login fields")
                return
            try:
                session = self.owner.login(
                    body["username"], body["password"], self.client_address[0],
                )
            except LoginLimited:
                self._error(HTTPStatus.TOO_MANY_REQUESTS, "rate_limited",
                            "Too many sign-in attempts. Try again in a minute.")
                return
            except (OSError, ValueError):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "account_unavailable",
                            "Local account storage is unavailable")
                return
            if session is None:
                self._error(HTTPStatus.UNAUTHORIZED, "invalid_credentials",
                            "Incorrect username or password")
                return
            principal = self.owner.authenticate(f"{COOKIE}={session[0]}")
            if principal is None or principal[1].account is None:
                self._error(HTTPStatus.UNAUTHORIZED, "invalid_credentials",
                            "Account changed; sign in again")
                return
            self._json(HTTPStatus.OK, {"csrf": session[1],
                                     "username": principal[1].account.username,
                                     "role": principal[1].account.role},
                       cookie=f"{COOKIE}={session[0]}; HttpOnly; SameSite=Strict; Path=/")
            return
        if path == "/api/v1/auth/exchange":
            if not self._same_host() or not self._browser_source_ok(mutation=True):
                self._error(HTTPStatus.FORBIDDEN, "forbidden", "Request origin rejected")
                return
            body = self._body()
            if body is None:
                return
            if set(body) != {"code"} or not isinstance(body["code"], str):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid bootstrap")
                return
            session = self.owner.exchange(body["code"])
            if session is None:
                self._error(HTTPStatus.UNAUTHORIZED, "unauthenticated", "Bootstrap expired")
                return
            cookie = f"{COOKIE}={session[0]}; HttpOnly; SameSite=Strict; Path=/"
            self._json(HTTPStatus.OK, {"api_version": "1", "csrf": session[1]},
                       cookie=cookie)
            return
        auth = self._authenticated(mutation=True)
        if auth is None:
            return
        if path == "/api/v1/uploads":
            self._upload(auth[0])
            return
        body = self._body()
        if body is None:
            return
        if path == "/api/v1/chat-previews":
            try:
                if set(body) != {"source"}:
                    raise ValueError("Invalid preview fields")
                with self.owner._lock:
                    if not self.owner.session_active(auth[0]):
                        self._error(HTTPStatus.UNAUTHORIZED, "unauthenticated", "Sign in locally")
                        return
                    identity = self.owner.chat_previews.create(auth[0], body["source"])
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument",
                            "Invalid or oversized preview")
                return
            self._json(HTTPStatus.CREATED, {"url": f"/api/v1/chat-previews/{identity}"})
            return
        if path == "/api/v1/clients":
            if body:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Unexpected fields")
                return
            try:
                client_id = self.owner.attach_client(auth[0])
            except RuntimeError:
                self._error(HTTPStatus.TOO_MANY_REQUESTS, "resource_busy",
                            "Browser client limit reached")
                return
            self._json(HTTPStatus.CREATED, {"client_id": client_id})
            return
        if path == "/api/v1/auth/password":
            if (set(body) != {"current_password", "new_password"}
                    or not isinstance(body["current_password"], str)
                    or not isinstance(body["new_password"], str)
                    or len(body["current_password"]) > 256):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid password fields")
                return
            accounts = self.owner.accounts
            if accounts is None or auth[1].account_revision is None:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Account login unavailable")
                return
            acquired = False
            try:
                self.owner.login_limiter.admit(self.client_address[0])
                acquired = self.owner.login_limiter.workers.acquire(blocking=False)
                if not acquired:
                    raise LoginLimited
                changed = accounts.change_password(
                    body["current_password"], body["new_password"],
                    revision=auth[1].account_revision,
                )
            except LoginLimited:
                self._error(HTTPStatus.TOO_MANY_REQUESTS, "rate_limited",
                            "Too many attempts. Try again in a minute.")
                return
            except ValueError:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument",
                            "Use a password between 12 and 256 characters")
                return
            except OSError:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "account_unavailable",
                            "Password save not confirmed. Sign in again or use local recovery.")
                return
            finally:
                if acquired:
                    self.owner.login_limiter.workers.release()
            if not changed:
                self._error(HTTPStatus.FORBIDDEN, "invalid_credentials",
                            "Current password is incorrect or the account changed")
                return
            with self.owner._lock:
                for identity in list(self.owner._sessions):
                    self.owner.logout(identity)
            self._json(HTTPStatus.OK, {"status": "password_changed"},
                       cookie=f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
            return
        viewer = auth[0] if path == "/api/v1/auth/logout" else self._viewer(auth[0])
        if viewer is None:
            return
        session_headers = self.headers.get_all("X-Klaude-Session", [])
        if len(session_headers) > 1:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Ambiguous session")
            return
        expected_session = session_headers[0] if session_headers else None
        if (expected_session is not None and path != "/api/v1/auth/logout"
                and expected_session != self.owner.application.session_id):
            self._error(HTTPStatus.CONFLICT, "stale_session", "Session changed; reload")
            return
        if path in {"/api/v1/chat/attachments", "/api/v1/chat/attachments/discard"}:
            self._attachment_change(path, body, auth[0], viewer)
        elif path in {
            "/api/v1/library/review", "/api/v1/library/submit", "/api/v1/library/discard",
            "/api/v1/library/cancel", "/api/v1/library/vision/clear",
        }:
            self._library_change(path, body, auth[0], viewer)
        elif path in {"/api/v1/settings/model-connections/test",
                      "/api/v1/settings/models/image-test"}:
            if not self._admin_management_allowed():
                self._error(HTTPStatus.FORBIDDEN, "forbidden",
                            "Model service tests require an admin account")
                return
            try:
                service = self.owner.library
                if service is None:
                    raise ValueError("Model settings unavailable")
                if path.endswith("image-test"):
                    from klaude_core.image_generation import inspect

                    if set(body) != {"endpoint"} or not isinstance(body["endpoint"], str):
                        raise ValueError("Choose an image-service address")
                    evidence = inspect(body["endpoint"])
                    result = {key: evidence[key] for key in (
                        "model", "limits", "sampler", "scheduler",
                        "cancel_queued", "cancel_generating",
                    )}
                else:
                    from klaude_application.browser_model_settings import test_connection

                    result = test_connection(service.cfg, body)
                self._json(HTTPStatus.OK, result)
            except Exception:
                self._error(HTTPStatus.BAD_REQUEST, "model_unavailable",
                            "Service test unavailable; check its address and credentials")
        elif path in {"/api/v1/models/cancel", "/api/v1/models/reconcile",
                      "/api/v1/models/dismiss"}:
            if not self._admin_management_allowed():
                self._error(HTTPStatus.FORBIDDEN, "forbidden",
                            "Model management requires an admin account")
                return
            try:
                with self.owner._lock:
                    service = self.owner.library
                    if (service is None or set(body) != {"request_id"}
                            or not isinstance(body["request_id"], str)):
                        raise ValueError("Choose an exact model operation")
                    if path.endswith("/dismiss"):
                        result = service.dismiss_model(body["request_id"])
                    elif path.endswith("/cancel"):
                        result = service.cancel_model(body["request_id"])
                    else:
                        result = service.reconcile_model(body["request_id"])
                    self._json(HTTPStatus.OK, result)
            except (ValueError, RuntimeError, OSError, sqlite3.Error):
                self._error(HTTPStatus.CONFLICT, "model_unconfirmed",
                            "Stop the active download before removing its history."
                            if path.endswith("/dismiss") else
                            "Model outcome not confirmed. Check Downloads and the Ollama server.")
        elif path == "/api/v1/auth/logout":
            if body:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Unexpected fields")
                return
            self.owner.logout(auth[0])
            self._json(HTTPStatus.OK, {"status": "signed_out"},
                       cookie=f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")
        elif path == "/api/v1/workspace/activate-edits":
            if (set(body) != {"request_id", "expected_revision", "acknowledge"}
                    or not isinstance(body["request_id"], str)
                    or not 0 < len(body["request_id"]) <= 128
                    or not body["request_id"].isascii()
                    or not body["request_id"].isprintable()
                    or any(char.isspace() for char in body["request_id"])
                    or type(body["expected_revision"]) is not int
                    or body["expected_revision"] < 0
                    or body["acknowledge"] is not True):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument",
                            "Explicit edit review required")
                return
            if getattr(self.server, "host_lan", False):
                self._error(HTTPStatus.FORBIDDEN, "forbidden",
                            "File edits require the local browser")
                return
            try:
                result = self.owner.activate_edits(
                    viewer, body["request_id"], body["expected_revision"],
                    expected_session,
                )
            except ValueError:
                self._error(HTTPStatus.CONFLICT, "stale_revision", "Workspace changed")
                return
            except RuntimeError as exc:
                self._error(HTTPStatus.CONFLICT, "resource_busy", str(exc)[:200])
                return
            except (OSError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "workspace_unavailable",
                            "Workspace activation unavailable")
                return
            self._json(HTTPStatus.OK, result)
        elif path == "/api/v1/turns":
            if (not {"request_id", "text"} <= set(body)
                    or set(body) - {"request_id", "text", "disposition", "attachments"}):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Unexpected fields")
                return
            text = body["text"]
            request_id = body["request_id"]
            disposition = body.get("disposition", "start")
            if (not isinstance(text, str) or not text.strip() or len(text) > 65_536
                    or not isinstance(request_id, str)
                    or disposition not in ("start", "queue")):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid turn")
                return
            try:
                with self.owner._lock:
                    if (expected_session is not None
                            and expected_session != self.owner.application.session_id):
                        raise ValueError("session changed")
                    if self.owner._stopping or not self.owner.session_active(auth[0]):
                        self._error(HTTPStatus.SERVICE_UNAVAILABLE, "host_stopping",
                                    "Web UI is stopping")
                        return
                    if self.owner.library is not None and self.owner.library.model_busy():
                        raise RuntimeError("Model work active or unconfirmed; check Downloads")
                    if disposition == "queue":
                        if body.get("attachments"):
                            raise ValueError("Send attachments when the current reply finishes")
                        if not self.owner.application.active_turn_id():
                            raise ValueError("No active turn to queue behind")
                        queued = self.owner.application.enqueue(
                            text, request_id=request_id, creator_id=viewer,
                        )
                        receipt = {"request_id": queued.request_id, "queue_id": queued.id,
                                   "state": queued.state, "session_id": queued.session_id}
                    else:
                        attachments = self.owner.attachments.capture(
                            auth[0], viewer, self.owner.application.session_id,
                            body["attachments"],
                        ) if "attachments" in body else None
                        handle = self.owner.application.submit(
                            text, request_id=request_id, _controller_id=viewer,
                            attachments=attachments,
                        )
                        receipt = {"request_id": handle.request_id,
                                   "turn_id": handle.turn_id, "state": handle.state,
                                   "session_id": handle.session_id}
            except ValueError as exc:
                if "request ID already used" in str(exc):
                    self._error(HTTPStatus.CONFLICT, "stale_revision", "Request ID conflict")
                elif str(exc) == "session changed":
                    self._error(HTTPStatus.CONFLICT, "stale_session", "Session changed; reload")
                else:
                    self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", str(exc)[:240])
                return
            except RuntimeError:
                self._error(HTTPStatus.CONFLICT, "session_busy", "Session is busy")
                return
            except (OSError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                            "Session temporarily unavailable")
                return
            self._json(HTTPStatus.ACCEPTED, receipt)
        elif path == "/api/v1/control/claim":
            if (set(body) != {"request_id", "expected_epoch"}
                    or not isinstance(body["request_id"], str)
                    or type(body["expected_epoch"]) is not int
                    or body["expected_epoch"] < 0):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid control claim")
                return
            try:
                with self.owner._lock:
                    if (expected_session is not None
                            and expected_session != self.owner.application.session_id):
                        raise ValueError("session changed")
                    epoch = self.owner.application.take_control(
                        viewer, expected_epoch=body["expected_epoch"],
                        request_id=body["request_id"],
                    )
            except ValueError:
                self._error(HTTPStatus.CONFLICT, "stale_revision", "Control changed")
                return
            self._json(HTTPStatus.OK, {"control_epoch": epoch, "has_control": True})
        elif path == "/api/v1/session/plan-mode":
            if (set(body) != {"request_id", "enabled", "expected_revision", "control_epoch"}
                    or not isinstance(body["request_id"], str)
                    or not 0 < len(body["request_id"]) <= 128
                    or not body["request_id"].isascii()
                    or not body["request_id"].isprintable()
                    or any(char.isspace() for char in body["request_id"])
                    or type(body["enabled"]) is not bool
                    or type(body["expected_revision"]) is not int
                    or type(body["control_epoch"]) is not int
                    or body["expected_revision"] < 0 or body["control_epoch"] < 0):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid Plan change")
                return
            try:
                with self.owner._lock:
                    if (expected_session is not None
                            and expected_session != self.owner.application.session_id):
                        raise ValueError("session changed")
                    control = self.owner.application.control()
                    if control is not None and control != (viewer, body["control_epoch"]):
                        raise ValueError("session control changed")
                    revision = self.owner.application.set_plan_mode(
                        body["enabled"], expected_revision=body["expected_revision"],
                        request_id=body["request_id"],
                    )
            except ValueError:
                self._error(HTTPStatus.CONFLICT, "stale_revision", "Plan setting changed")
                return
            except RuntimeError:
                self._error(HTTPStatus.CONFLICT, "session_busy", "Session is busy")
                return
            self._json(HTTPStatus.OK, {"enabled": body["enabled"], "revision": revision})
        elif path == "/api/v1/messages/action":
            if (set(body) != {"request_id", "source_session_id", "message_id", "action",
                             "control_epoch"}
                    or not isinstance(body["request_id"], str)
                    or not 0 < len(body["request_id"]) <= 128
                    or not body["request_id"].isascii()
                    or not body["request_id"].isprintable()
                    or any(char.isspace() for char in body["request_id"])
                    or not isinstance(body["source_session_id"], str)
                    or not 0 < len(body["source_session_id"]) <= 128
                    or not isinstance(body["message_id"], str)
                    or not 0 < len(body["message_id"]) <= 40
                    or body["action"] not in ("branch", "retry")
                    or type(body["control_epoch"]) is not int
                    or body["control_epoch"] < 0):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid message action")
                return
            try:
                selected = self.owner.message_action(
                    viewer, body["request_id"], body["source_session_id"],
                    body["message_id"], body["action"], body["control_epoch"],
                )
            except ValueError as exc:
                self._error(HTTPStatus.CONFLICT, "stale_revision", str(exc)[:200])
                return
            except RuntimeError:
                self._error(HTTPStatus.CONFLICT, "session_busy", "Finish active work first")
                return
            except (OSError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                            "Message action not confirmed; reload before trying again")
                return
            self._json(HTTPStatus.OK, {"session_id": selected})
        elif path == "/api/v1/session/select":
            if (set(body) != {"request_id", "expected_session_id", "session_id",
                             "control_epoch"}
                    or not isinstance(body["request_id"], str)
                    or not 0 < len(body["request_id"]) <= 128
                    or not body["request_id"].isascii()
                    or not body["request_id"].isprintable()
                    or any(char.isspace() for char in body["request_id"])
                    or not isinstance(body["expected_session_id"], str)
                    or not isinstance(body["session_id"], str)
                    or len(body["session_id"]) > 128
                    or type(body["control_epoch"]) is not int
                    or body["control_epoch"] < 0):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid session choice")
                return
            try:
                selected = self.owner.switch_session(
                    viewer, body["request_id"], body["expected_session_id"],
                    body["session_id"], body["control_epoch"],
                )
            except ValueError as exc:
                self._error(HTTPStatus.CONFLICT, "stale_revision", str(exc)[:200])
                return
            except RuntimeError as exc:
                self._error(HTTPStatus.CONFLICT, "session_busy", str(exc)[:200])
                return
            except (OSError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                            "Session temporarily unavailable")
                return
            self._json(HTTPStatus.OK, {"session_id": selected})
        elif path in {"/api/v1/session/model", "/api/v1/session/mode",
                      "/api/v1/session/configured-model"}:
            key = ("model_ref" if path.endswith("/configured-model")
                   else "model_id" if path.endswith("/model") else "mode")
            required = {"request_id", key, "expected_revision", "control_epoch"}
            if (not required <= set(body)
                    or set(body) - required - ({"effort"} if key == "mode" else set())
                    or not isinstance(body["request_id"], str)
                    or not 0 < len(body["request_id"]) <= 128
                    or not body["request_id"].isascii()
                    or not body["request_id"].isprintable()
                    or any(char.isspace() for char in body["request_id"])
                    or not isinstance(body[key], str)
                    or not 0 < len(body[key]) <= 768
                    or type(body["expected_revision"]) is not int
                    or body["expected_revision"] < 0
                    or type(body["control_epoch"]) is not int
                    or body["control_epoch"] < 0):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid model choice")
                return
            if key == "mode" and body[key] not in {"standard", "thinking"}:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid mode")
                return
            if "effort" in body and (body["effort"] is not None and (
                not isinstance(body["effort"], str)
                or body["effort"] not in {"minimal", "low", "medium", "high", "max"}
            )):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid thinking effort")
                return
            try:
                cfg = self.owner.application.agent.tool_config
                current = self.owner.application.agent.model_info
                if key == "model_ref":
                    if not isinstance(cfg, Config):
                        raise ValueError("Model configuration unavailable")
                    info = BrowserModels(cfg).verify_ref(body[key])
                elif (key == "mode" and current.connection_id
                      and (current.backend != "ollama"
                           or current.connection_id != DEFAULT_IDS["ollama"])):
                    if not isinstance(cfg, Config):
                        raise ValueError("Model configuration unavailable")
                    info = BrowserModels(cfg).verify_ref(current.ref)
                else:
                    info = self.owner.verified_local_model(
                        body[key] if key == "model_id" else self.owner.application.agent.model
                    )
                with self.owner._lock:
                    if (expected_session is not None
                            and expected_session != self.owner.application.session_id):
                        raise ValueError("session changed")
                    control = self.owner.application.control()
                    if control is not None and control != (viewer, body["control_epoch"]):
                        raise ValueError("session control changed")
                    if self.owner.library is not None and self.owner.library.model_busy():
                        raise RuntimeError("Model work active or unconfirmed; check Downloads")
                    if key == "model_ref":
                        revision = self.owner.application.choose_configured_model(
                            info, expected_revision=body["expected_revision"],
                            request_id=body["request_id"],
                        )
                    elif key == "model_id":
                        revision = self.owner.application.choose_local_model(
                            info, expected_revision=body["expected_revision"],
                            request_id=body["request_id"],
                        )
                    else:
                        current = self.owner.application.agent.model_info
                        info = replace(
                            info, connection_id=current.connection_id,
                            connection_revision=current.connection_revision,
                            connection_source=current.connection_source,
                            credential_revision=current.credential_revision,
                        )
                        revision = self.owner.application.choose_reasoning(
                            body["mode"], body.get("effort", "medium")
                            if body["mode"] == "thinking" else None,
                            expected_revision=body["expected_revision"],
                            request_id=body["request_id"], info=info,
                        )
            except ModelDiscoveryError:
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "model_unavailable",
                            "Configured model catalog unavailable")
                return
            except ValueError as exc:
                self._error(HTTPStatus.CONFLICT, "model_unavailable", str(exc)[:200])
                return
            except RuntimeError as exc:
                self._error(HTTPStatus.CONFLICT, "session_busy", str(exc)[:200])
                return
            except (OSError, sqlite3.Error):
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "model_unavailable",
                            "Local model metadata unavailable")
                return
            self._json(HTTPStatus.OK, {"revision": revision})
        elif path.startswith("/api/v1/turns/") and path.endswith("/cancel"):
            turn_id = path.removeprefix("/api/v1/turns/").removesuffix("/cancel")
            if (not turn_id or "/" in turn_id or set(body) != {"request_id", "control_epoch"}
                    or not isinstance(body["request_id"], str)
                    or type(body["control_epoch"]) is not int):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid cancellation")
                return
            accepted = self.owner.application.cancel_active(
                turn_id, controller_id=viewer, control_epoch=body["control_epoch"],
            )
            self._json(HTTPStatus.OK if accepted else HTTPStatus.CONFLICT,
                       {"accepted": accepted})
        elif path.startswith("/api/v1/turns/") and path.endswith("/steer"):
            turn_id = path.removeprefix("/api/v1/turns/").removesuffix("/steer")
            if (not turn_id or "/" in turn_id
                    or set(body) != {"request_id", "control_epoch", "text"}
                    or not isinstance(body["request_id"], str)
                    or type(body["control_epoch"]) is not int
                    or not isinstance(body["text"], str)
                    or not body["text"].strip() or len(body["text"]) > 65_536):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid steering")
                return
            try:
                queued = self.owner.application.steer(
                    body["text"], request_id=body["request_id"], turn_id=turn_id,
                    controller_id=viewer, control_epoch=body["control_epoch"],
                )
            except (ValueError, RuntimeError):
                self._error(HTTPStatus.CONFLICT, "stale_revision", "Turn or control changed")
                return
            self._json(HTTPStatus.ACCEPTED, {"request_id": queued.request_id,
                       "queue_id": queued.id, "state": queued.state})
        elif path.startswith("/api/v1/interactions/") and path.endswith("/answer"):
            interaction_id = path.removeprefix("/api/v1/interactions/").removesuffix(
                "/answer"
            )
            if (not interaction_id or "/" in interaction_id
                    or set(body) != {"request_id", "control_epoch", "answer"}
                    or not isinstance(body["request_id"], str)
                    or type(body["control_epoch"]) is not int
                    or not isinstance(body["answer"], str)
                    or not body["answer"].strip() or len(body["answer"]) > 1000
                    or not body["answer"].isprintable()):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid answer")
                return
            request_id = body["request_id"]
            if (not 0 < len(request_id) <= 128 or not request_id.isascii()
                    or not request_id.isprintable() or any(c.isspace() for c in request_id)):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid request ID")
                return
            with self.owner._lock:
                receipt_key = f"answer:{interaction_id}"
                previous = self.owner._decision_receipts.get(request_id)
                if previous is not None:
                    if previous[:3] != (viewer, receipt_key, body["answer"]):
                        self._error(HTTPStatus.CONFLICT, "stale_revision",
                                    "Request ID conflict")
                        return
                    accepted = previous[3]
                else:
                    pending = self.owner.application.pending_interactions(
                        controller_id=viewer, control_epoch=body["control_epoch"],
                    )
                    if not any(isinstance(item, UserInputRequest) and item.id == interaction_id
                               for item in pending):
                        self._error(HTTPStatus.GONE, "interaction_expired",
                                    "Question is no longer available")
                        return
                    accepted = self.owner.application.decide(
                        interaction_id, body["answer"], controller_id=viewer,
                        control_epoch=body["control_epoch"],
                    )
                    if len(self.owner._decision_receipts) >= 1024:
                        self.owner._decision_receipts.pop(next(iter(self.owner._decision_receipts)))
                    self.owner._decision_receipts[request_id] = (
                        viewer, receipt_key, body["answer"], accepted,
                    )
            self._json(HTTPStatus.OK if accepted else HTTPStatus.GONE,
                       {"accepted": accepted})
        elif path.startswith("/api/v1/interactions/") and path.endswith("/decision"):
            interaction_id = path.removeprefix("/api/v1/interactions/").removesuffix(
                "/decision"
            )
            if (not interaction_id or "/" in interaction_id
                    or set(body) not in ({"request_id", "decision"},
                                         {"request_id", "decision", "control_epoch"})
                    or not isinstance(body["request_id"], str)
                    or ("control_epoch" in body and type(body["control_epoch"]) is not int)
                    or body["decision"] not in ("allow_once", "deny")):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid decision")
                return
            request_id = body["request_id"]
            if (not 0 < len(request_id) <= 128 or not request_id.isascii()
                    or not request_id.isprintable() or any(c.isspace() for c in request_id)):
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid request ID")
                return
            with self.owner._lock:
                if self.owner._stopping or not self.owner.session_active(auth[0]):
                    self._error(HTTPStatus.SERVICE_UNAVAILABLE, "host_stopping",
                                "Web UI is stopping")
                    return
                previous = self.owner._decision_receipts.get(request_id)
                if previous is not None:
                    if previous[:3] != (viewer, interaction_id, body["decision"]):
                        self._error(HTTPStatus.CONFLICT, "stale_revision",
                                    "Request ID conflict")
                        return
                    decided = previous[3]
                else:
                    control = self.owner.application.control()
                    epoch = body.get("control_epoch", control[1] if control else -1)
                    review = self.owner.application.review_interaction(
                        interaction_id, controller_id=viewer,
                        control_epoch=epoch,
                    )
                    external: frozenset[str] = getattr(
                        getattr(self.owner.application.agent, "browser_tools", None),
                        "mcp_names", frozenset(),
                    )
                    allowed = READ_ONLY_TOOLS | external | (
                        FILE_EDIT_TOOLS if self.owner._edits_activated
                        and self.owner.application.agent.workspace.write_enabled
                        and not getattr(self.server, "host_lan", False) else frozenset()
                    )
                    if review is None or review["tool"] not in allowed:
                        self._error(HTTPStatus.GONE, "interaction_expired",
                                    "Approval is no longer available")
                        return
                    decided = self.owner.application.decide(
                        interaction_id, body["decision"], controller_id=viewer,
                        control_epoch=epoch,
                    )
                    if len(self.owner._decision_receipts) >= 1024:
                        self.owner._decision_receipts.pop(next(iter(self.owner._decision_receipts)))
                    self.owner._decision_receipts[request_id] = (
                        viewer, interaction_id, body["decision"], decided,
                    )
            self._json(HTTPStatus.OK if decided else HTTPStatus.GONE,
                       {"accepted": decided})
        else:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "Route not found")

    def _library_read(self, path: str, identity: str) -> None:
        service = self.owner.library
        if service is None:
            self._error(
                HTTPStatus.NOT_FOUND, "not_found", "Library unavailable; restart the Web UI"
            )
            return
        params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if any(len(value) != 1 for value in params.values()):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Ambiguous filter")
            return
        query = {key: value[0] for key, value in params.items()}
        result: dict[str, Any]
        try:
            offset = int(query.get("offset", "0"))
            if not 0 <= offset <= 1_000_000 or any(
                len(value) > (8192 if key == "source" and path.startswith(
                    "/api/v1/library/knowledge/"
                ) else 256) for key, value in query.items()
            ):
                raise ValueError("Invalid filter")
            if path == "/api/v1/library/vision":
                if set(query) != {"artifact", "revision"}:
                    raise ValueError("Choose an exact saved image")
                result = service.vision_results(query["artifact"], int(query["revision"]))
            elif path == "/api/v1/library/jobs":
                if query:
                    raise ValueError("Unknown job filter")
                result = generated_jobs(service.cfg)
            elif path == "/api/v1/library/counts":
                if query:
                    raise ValueError("Unknown count filter")
                result = service.tab_counts()
            elif path == "/api/v1/library/items":
                if set(query) - {"kind", "archived", "query", "offset", "sort", "images",
                                 "source", "scope", "references"}:
                    raise ValueError("Unknown filter")
                if query.get("archived", "false") not in {"true", "false"}:
                    raise ValueError("Invalid archive filter")
                if query.get("images", "0") not in {"0", "1"}:
                    raise ValueError("Invalid image filter")
                scope = query.get("scope", "all")
                if scope not in {"current", "all"}:
                    raise ValueError("Invalid Library scope")
                references = tuple(filter(None, query.get("references", "").split(",")))
                if len(references) > 4 or any(
                    not re.fullmatch(r"(?:document|media|research):[a-f0-9]{32}", item)
                    for item in references
                ):
                    raise ValueError("Invalid Library references")
                session = self.owner.application.session_id
                scope_limited = False
                if scope == "current":
                    saved = self.owner.application.sessions.artifact_references(session)
                    references = tuple(set(references) | set(saved.identities))
                    scope_limited = saved.limited
                result = service.listing(
                    kind=query.get("kind", "document"),
                    archived=query.get("archived") == "true",
                    query=query.get("query", ""),
                    offset=offset,
                    sort=query.get("sort", "newest"),
                    images_only=query.get("images") == "1",
                    source=query.get("source", "all"),
                    session=session if scope == "current" else "",
                    identities=references if scope == "current" else (),
                )
                result.update(scope=scope, session_id=session, scope_limited=scope_limited)
            elif path == "/api/v1/library/image-capabilities":
                if query:
                    raise ValueError("Unknown image-service filter")
                from klaude_application.browser_jobs import image_capabilities

                result = image_capabilities(service.cfg)
            elif path == "/api/v1/library/item":
                if set(query) != {"id"}:
                    raise ValueError("Choose an item")
                result = service.detail(query["id"])
            elif path == "/api/v1/library/content":
                if set(query) - {"id", "revision", "inline"} or not {"id", "revision"} <= set(
                    query
                ):
                    raise ValueError("Choose an item revision")
                self._library_content(service, identity, query)
                return
            elif path == "/api/v1/library/image":
                if set(query) != {"id", "revision", "size"}:
                    raise ValueError("Choose an image revision and size")
                mime, output = self.owner.library_images.read(
                    service.artifacts, query["id"], int(query["revision"]), query["size"],
                    cancelled=lambda: (self.owner._stopping
                                       or not self.owner.session_active(identity)),
                )
                if self.owner._stopping or not self.owner.session_active(identity):
                    raise ValueError("Image request ended")
                self._headers(HTTPStatus.OK, mime, len(output))
                for start in range(0, len(output), 65536):
                    if self.owner._stopping or not self.owner.session_active(identity):
                        self.close_connection = True
                        return
                    self.wfile.write(output[start:start + 65536])
                return
            elif path in {
                "/api/v1/library/knowledge/contents", "/api/v1/library/knowledge/sources",
            }:
                if set(query) - {"library", "source", "query", "offset", "chunk"}:
                    raise ValueError("Unknown Knowledge filter")
                result = service.knowledge_contents(
                    library=query.get("library", ""), source=query.get("source", ""),
                    query=query.get("query", ""), offset=offset, chunk=query.get("chunk", ""),
                    sources=path.endswith("/sources"),
                )
            elif path == "/api/v1/library/knowledge":
                if set(query) - {"library", "query", "offset"}:
                    raise ValueError("Unknown Knowledge filter")
                result = service.knowledge(query.get("library", ""), query.get("query", ""),
                                           offset=offset)
            elif path == "/api/v1/library/sources":
                if set(query) - {"library", "offset"}:
                    raise ValueError("Unknown source filter")
                result = service.sources(query.get("library", ""), offset)
            elif path == "/api/v1/integrations/skills":
                if set(query) - {"query", "offset", "state"}:
                    raise ValueError("Unknown Skills filter")
                result = service.skills(query=query.get("query", ""), offset=offset,
                                        state=query.get("state", "all"))
            elif path == "/api/v1/integrations/connections":
                if query:
                    raise ValueError("Unknown connection filter")
                result = read_mcp_inventory(service.cfg.mcp_servers_file)
                result["management_allowed"] = self._mcp_management_allowed()
            elif path == "/api/v1/settings/memory":
                if query:
                    raise ValueError("Unknown memory filter")
                result = read_memory_inventory(service.cfg.sessions_db, service.cfg.memory_file)
            elif path == "/api/v1/settings/agent":
                if query:
                    raise ValueError("Unknown setting filter")
                result = read_browser_settings(service.cfg)
            elif path == "/api/v1/settings/model-connections":
                from klaude_application.browser_model_settings import inventory

                if query:
                    raise ValueError("Unknown model-connection filter")
                result = inventory(
                    service.cfg, management_allowed=self._admin_management_allowed()
                )
            elif path == "/api/v1/settings/models":
                from klaude_application.browser_media_settings import media_settings

                if query:
                    raise ValueError("Unknown model setting filter")
                result = media_settings(service.cfg)
                result["management_allowed"] = self._admin_management_allowed()
            elif path == "/api/v1/library/operations":
                if query:
                    raise ValueError("Unknown operation filter")
                result = service.operations()
            elif path == "/api/v1/library/operation":
                if set(query) != {"id"}:
                    raise ValueError("Choose an operation")
                result = service.status(query["id"])
            else:
                self._error(HTTPStatus.NOT_FOUND, "not_found", "Route not found")
                return
            self._json(HTTPStatus.OK, result)
        except (BrokenPipeError, ConnectionResetError):
            # View changes cancel obsolete thumbnail/inventory requests.
            self.close_connection = True
        except ImageBusy:
            self._error(HTTPStatus.TOO_MANY_REQUESTS, "resource_busy", "Image previews busy; retry")
        except (ValueError, TypeError, KeyError):
            self._error(
                HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid filter or item changed; reload"
            )
        except (OSError, RuntimeError, sqlite3.Error):
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "storage_unavailable",
                "Library temporarily unavailable",
            )

    def _library_content(
        self, service: LibraryManagement, identity: str, query: dict[str, str]
    ) -> None:
        if not self.owner._library_downloads.acquire(timeout=2):
            self._error(
                HTTPStatus.TOO_MANY_REQUESTS, "resource_busy", "Downloads busy; retry shortly"
            )
            return
        try:
            item = service.artifacts.get(query["id"])
            revision = int(query["revision"])
            if item["revision"] != revision:
                raise ValueError("Item changed")
            inline = query.get("inline", "0") == "1"
            if inline and (
                item["mime"] not in {"image/png", "image/jpeg", "image/webp", "image/gif"}
                or not item["width"]
                or not item["height"]
                or max(item["width"], item["height"]) > 4096
                or item["width"] * item["height"] > 4_000_000
                or item["size"] > 8 * 1024 * 1024
            ):
                raise ValueError("Image exceeds preview limits; download it instead")
            with tempfile.TemporaryDirectory(prefix="klaude-library-download-") as directory:
                exported = service.artifacts.export(
                    item["id"], Path(directory) / "content", revision=revision
                )
                with exported.open("rb") as source:
                    self._headers(
                        HTTPStatus.OK,
                        item["mime"] if inline else "application/octet-stream",
                        item["size"],
                        attachment="" if inline else display_filename(item["filename"]),
                    )
                    while chunk := source.read(65536):
                        if self.owner._stopping or not self.owner.session_active(identity):
                            self.close_connection = True
                            return
                        self.wfile.write(chunk)
        finally:
            self.owner._library_downloads.release()

    def _attachment_preview(self, identity: str) -> None:
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        try:
            if any(len(values) != 1 for values in query.values()):
                raise ValueError("Invalid preview")
            with self.owner._lock:
                session = self.owner.application.session_id
                if (query.get("session") != [session] or not self.owner.session_active(identity)
                        or self.owner._stopping):
                    raise ValueError("Chat changed")
                if set(query) == {"session", "selection", "client"}:
                    client = query["client"][0]
                    if self.owner.browser_client(identity, client) is None:
                        raise ValueError("Attach this browser tab again")
                    captured = self.owner.attachments.capture(
                        identity, client, session, [query["selection"][0]],
                    )
                    data = captured.files[0].thumbnail
                elif set(query) == {"session", "message", "file"}:
                    message, index = query["message"][0], query["file"][0]
                    digits = message.removeprefix("stored:")
                    if (not message.startswith("stored:") or not digits.isascii()
                            or not digits.isdecimal() or not 1 <= len(digits) <= 19
                            or index not in {"0", "1", "2", "3"}):
                        raise ValueError("Invalid preview")
                    data = self.owner.application.sessions.attachment_preview(
                        session, int(digits), int(index),
                    )
                else:
                    raise ValueError("Invalid preview")
                if not data or len(data) > 65536:
                    raise ValueError("Preview unavailable")
            self._headers(HTTPStatus.OK, "image/png", len(data))
            self.wfile.write(data)
        except (ValueError, FileNotFoundError):
            self._error(HTTPStatus.NOT_FOUND, "not_found", "Attachment preview unavailable")
        except (OSError, sqlite3.Error):
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                        "Attachment preview temporarily unavailable")

    def _attachment_content(self, identity: str) -> None:
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        if not self.owner._attachment_reads.acquire(blocking=False):
            self._error(HTTPStatus.TOO_MANY_REQUESTS, "resource_busy",
                        "Attachment previews busy; try again")
            return
        try:
            if (set(query) != {"session", "message", "file", "view"}
                    or any(len(values) != 1 for values in query.values())):
                raise ValueError("Invalid attachment preview")
            session, message, index, view = (
                query[key][0] for key in ("session", "message", "file", "view")
            )
            if (not re.fullmatch(r"stored:[1-9][0-9]{0,18}", message)
                    or int(message[7:]) > 9_223_372_036_854_775_807
                    or index not in {"0", "1", "2", "3"}
                    or view not in {"info", "image", "download"}):
                raise ValueError("Invalid attachment preview")

            def current() -> bool:
                return (not self.owner._stopping and self.owner.session_active(identity)
                        and self.owner.application.session_id == session)

            thumbnail_only = False
            with self.owner._lock:
                if not current():
                    raise ValueError("Chat changed; reopen the attachment")
                try:
                    descriptor, data = self.owner.application.sessions.attachment_content(
                        session, int(message[7:]), int(index),
                    )
                except FileNotFoundError:
                    saved = self.owner.application.sessions.public_message(
                        session, int(message[7:]),
                    )
                    if saved is None or int(index) >= len(saved.attachments):
                        raise ValueError("Attachment unavailable") from None
                    descriptor = saved.attachments[int(index)]
                    artifact = descriptor.get("artifact_id")
                    if artifact and self.owner.library is not None:
                        service = ArtifactService(self.owner.library.artifacts.root)
                        item = service.get(artifact)
                        name, data = service.attachment(artifact, item["revision"])
                        if name != descriptor.get("name") or len(data) != descriptor.get("size"):
                            raise ValueError("Original Library attachment changed") from None
                    elif descriptor.get("image") and descriptor.get("preview"):
                        data = self.owner.application.sessions.attachment_preview(
                            session, int(message[7:]), int(index),
                        )
                        thumbnail_only = True
                    else:
                        raise FileNotFoundError(
                            "Original file was not retained in this older message. "
                            "Attach it again to preview it."
                        ) from None
            name = descriptor["name"]
            if view == "download":
                if thumbnail_only:
                    raise ValueError("Only a thumbnail is available for this older attachment")
                mime, output = "application/octet-stream", data
            elif descriptor.get("image"):
                if view == "image":
                    if thumbnail_only:
                        mime, output = "image/png", data
                    else:
                        metadata, output = prepare_image(
                            data, detail="detailed", frame=0, preserve_alpha=True,
                            cancelled=lambda: not current(),
                        )
                        mime = metadata["mime"]
                else:
                    _, width, height = image_header(data[:65536])
                    result = {"item": {**descriptor, "filename": name,
                                       "width": width, "height": height},
                              "lines": [], "thumbnail_only": thumbnail_only}
            elif view == "image":
                raise ValueError("This attachment is not an image")
            else:
                prepared = prepare_attachment(name, data)
                source = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "\ufffd", prepared.text)
                result = {"item": {**descriptor, "filename": name}, "lines": [],
                          "source_text": source, "source_truncated": prepared.truncated,
                          "source_sanitized": source != prepared.text,
                          "extracted": prepared.mime in {
                              "application/pdf",
                              "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                          }}
            with self.owner._lock:
                if (not current() or self.owner.application.sessions.public_message(
                        session, int(message[7:])) is None):
                    raise ValueError("Chat changed; reopen the attachment")
                if view == "info":
                    self._json(HTTPStatus.OK, result)
                    return
                self._headers(HTTPStatus.OK, mime, len(output),
                              attachment=display_filename(name) if view == "download" else "")
            for offset in range(0, len(output), 65536):
                if not current():
                    self.close_connection = True
                    return
                self.wfile.write(output[offset:offset + 65536])
        except (ValueError, FileNotFoundError) as error:
            self._error(HTTPStatus.NOT_FOUND, "not_found", str(error)[:240])
        except (OSError, sqlite3.Error):
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                        "Attachment preview temporarily unavailable")
        finally:
            self.owner._attachment_reads.release()

    def _attachment_change(
        self, path: str, body: dict[str, Any], identity: str, viewer: str,
    ) -> None:
        if path.endswith("/discard"):
            if set(body) == {"upload_id"} and isinstance(body["upload_id"], str):
                if self.owner.transfers is not None:
                    self.owner.transfers.discard(identity, body["upload_id"])
            elif set(body) == {"id"} and isinstance(body["id"], str):
                self.owner.attachments.discard(identity, viewer, body["id"])
            else:
                self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid attachment")
                return
            self._json(HTTPStatus.OK, {"discarded": True})
            return
        if not self.owner.attachments.preparing.acquire(blocking=False):
            self._error(HTTPStatus.TOO_MANY_REQUESTS, "resource_busy", "Preparing files; try again")
            return
        try:
            session_id = self.owner.application.session_id
            artifact_id = ""
            if set(body) == {"upload_id"} and isinstance(body["upload_id"], str):
                if self.owner.transfers is None:
                    raise ValueError("Uploads unavailable")
                try:
                    record, stream = self.owner.transfers.open_download(identity, body["upload_id"])
                    with stream:
                        data = stream.read(MAX_UPLOAD + 1)
                finally:
                    self.owner.transfers.discard(identity, body["upload_id"])
                name = record.filename
            elif (set(body) == {"artifact_id", "revision"}
                    and isinstance(body["artifact_id"], str) and self.owner.library is not None):
                name, data = ArtifactService(self.owner.library.artifacts.root).attachment(
                    body["artifact_id"], body["revision"],
                )
                artifact_id = body["artifact_id"]
            else:
                raise ValueError("Choose a device upload or a current Library file")
            attachment = prepare_attachment(name, data, preview=True, artifact_id=artifact_id)
            with self.owner._lock:
                if (not self.owner.session_active(identity) or self.owner._stopping
                        or self.owner.application.session_id != session_id):
                    raise ValueError("Chat changed; choose the attachment again")
                result = self.owner.attachments.add(identity, viewer, session_id, attachment)
            self._json(HTTPStatus.CREATED, result)
        except (ValueError, FileNotFoundError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", str(exc)[:240])
        except (OSError, sqlite3.Error):
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                        "Attachment preparation unavailable")
        finally:
            self.owner.attachments.preparing.release()

    def _library_change(self, path: str, body: dict[str, Any], identity: str, viewer: str) -> None:
        service = self.owner.library
        if service is None:
            self._error(
                HTTPStatus.NOT_FOUND, "not_found", "Library unavailable; restart the Web UI"
            )
            return
        try:
            with self.owner._lock:
                if self.owner._stopping or not self.owner.session_active(identity):
                    raise OperationConflict("Sign in again")
                if path == "/api/v1/library/vision/clear":
                    if (set(body) != {"artifact", "revision", "result"}
                            or not isinstance(body["artifact"], str)
                            or type(body["revision"]) is not int
                            or not isinstance(body["result"], str)):
                        raise ValueError("Choose an exact image review")
                    service.clear_vision_review(body["artifact"], body["revision"], body["result"])
                    self._json(HTTPStatus.OK, {"status": "cleared"})
                elif path.endswith("/cancel"):
                    if set(body) != {"request_id"} or not isinstance(body["request_id"], str):
                        raise ValueError("Choose an exact image operation")
                    self._json(HTTPStatus.OK, service.cancel_vision(body["request_id"]))
                elif path.endswith("/discard"):
                    if set(body) != {"review_id"} or not isinstance(body["review_id"], str):
                        raise ValueError("Invalid review")
                    service.discard(viewer, body["review_id"])
                    self._json(HTTPStatus.OK, {"status": "discarded"})
                elif path.endswith("/review"):
                    if set(body) != {"draft"} or not isinstance(body["draft"], dict):
                        raise ValueError("Invalid review")
                    draft = body["draft"]
                    if (str(draft.get("operation", "")).startswith("model-")
                            or str(draft.get("operation", "")) in MODEL_SETTINGS_OPERATIONS):
                        if not self._admin_management_allowed():
                            self._error(HTTPStatus.FORBIDDEN, "forbidden",
                                        "Model management requires an admin account")
                            return
                    if (str(draft.get("operation", "")).startswith("mcp-")
                            and not self._mcp_management_allowed()):
                        self._error(HTTPStatus.FORBIDDEN, "forbidden",
                                    "MCP management requires an admin account")
                        return
                    upload_id = draft.get("upload_id")
                    if upload_id is not None:
                        if not isinstance(upload_id, str) or self.owner.transfers is None:
                            raise ValueError("Upload unavailable")
                        record, source = self.owner.transfers.open_download(identity, upload_id)
                        try:
                            with source:
                                result = service.prepare(
                                    viewer, draft, upload=(record.filename, source)
                                )
                        finally:
                            self.owner.transfers.discard(identity, upload_id)
                    else:
                        result = service.prepare(viewer, draft)
                    self._json(HTTPStatus.OK, result)
                else:
                    if (
                        set(body) != {"review_id", "request_id", "control_epoch"}
                        or not isinstance(body["review_id"], str)
                        or not isinstance(body["request_id"], str)
                        or type(body["control_epoch"]) is not int
                    ):
                        raise ValueError("Invalid reviewed submission")
                    control = self.owner.application.control()
                    if control is not None and control != (viewer, body["control_epoch"]):
                        raise OperationConflict("Session control changed; try the action again")
                    snapshot = self.owner.application.snapshot()
                    if snapshot.get("active_turn_id") or snapshot.get("queue"):
                        raise OperationConflict(
                            "Wait for the chat turn and queue to finish before making changes"
                        )
                    if (not self._mcp_management_allowed()
                            and service.local_review(viewer, body["review_id"])):
                        self._error(HTTPStatus.FORBIDDEN, "forbidden",
                                    "MCP management requires an admin account")
                        return
                    if (service.admin_model_review(viewer, body["review_id"])
                            and not self._admin_management_allowed()):
                        self._error(HTTPStatus.FORBIDDEN, "forbidden",
                                    "Model management requires an admin account")
                        return
                    connection_review = service.reviewed_connection(viewer, body["review_id"])
                    if connection_review is not None:
                        info = self.owner.application.agent.model_info
                        current_identity = info.connection_id or DEFAULT_IDS.get(info.backend, "")
                        current_connection = (
                            BrowserModels(service.cfg).connections().get(current_identity)
                        )
                        if (connection_review["id"] == current_identity or
                                current_connection and current_connection.key_env and
                                current_connection.key_env == connection_review.get("key_env")):
                            raise OperationConflict(
                                "Choose a different conversation model before changing "
                                "its connection or credential"
                            )
                    if service.model_review(viewer, body["review_id"]):
                        if any(self.owner._application_busy(app)
                               for app in self.owner._applications):
                            raise OperationConflict("Finish active conversations before model work")
                    current = self.owner.application.session_id
                    action = service.reviewed_session_action(viewer, body["review_id"], current)
                    def new_chat() -> None:
                        self.owner.switch_session(
                            viewer, f"archive-{body['request_id']}", current, "",
                            body["control_epoch"],
                        )

                    result = service.submit(
                        viewer, body["review_id"], body["request_id"],
                        before_start=(new_chat if action in {
                            "session-archive", "session-delete",
                        } else None),
                    )
                    if result["kind"] in {"session-archive", "session-delete"}:
                        result["session_id"] = self.owner.application.session_id
                    self._json(HTTPStatus.ACCEPTED, result)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except OperationConflict as exc:
            self._error(HTTPStatus.CONFLICT, "resource_busy", str(exc)[:240])
        except (ValueError, TypeError, KeyError) as exc:
            # The application only emits local validation messages here; worker
            # errors/provider internals never pass through this boundary.
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", str(exc)[:240])
        except (OSError, RuntimeError, sqlite3.Error):
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "storage_unavailable",
                "Operation not confirmed; check Activity before retrying",
            )

    def _workspace_read(self, route: str) -> None:
        query = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
        operation = route.rsplit("/", 1)[-1]
        allowed = ({"path", "offset", "limit"} if operation == "file" else
                   {"path", "pattern"} if operation == "search" else
                   {"path"} if operation == "files" else set())
        if (set(query) - allowed or any(len(value) != 1 for value in query.values())
                or any(len(value[0]) > 1024 for value in query.values())):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid workspace query")
            return
        reads = WorkspaceReadService(self.owner.application.agent.workspace)
        try:
            path = query.get("path", ["."])[0]
            if operation == "files":
                result = reads.list_dir(path)
            elif operation == "file":
                if "path" not in query or not path:
                    raise ValueError("File path required")
                offset = int(query["offset"][0]) if "offset" in query else None
                limit = int(query["limit"][0]) if "limit" in query else None
                result = reads.read_file(path, offset, limit)
            elif operation == "search":
                pattern = query.get("pattern", [""])[0]
                result = reads.grep(pattern, path)
            elif operation == "status":
                result = reads.git_status()
            else:
                result = reads.git_diff()
        except (ValueError, PermissionError, FileNotFoundError, NotADirectoryError):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Workspace read rejected")
            return
        except (OSError, RuntimeError):
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "workspace_unavailable",
                        "Workspace read unavailable")
            return
        self._json(HTTPStatus.OK, {"operation": operation, "text": result})

    def _upload(self, identity: str) -> None:
        transfers = self.owner.transfers
        if transfers is None:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "Uploads unavailable")
            return
        types = self.headers.get_all("Content-Type", [])
        lengths = self.headers.get_all("Content-Length", [])
        names = self.headers.get_all("X-Klaude-Filename", [])
        if (types != ["application/octet-stream"] or len(lengths) != 1
                or self.headers.get_all("Transfer-Encoding") or len(names) > 1):
            self._error(HTTPStatus.BAD_REQUEST, "invalid_argument", "Invalid upload framing")
            return
        try:
            length = int(lengths[0])
        except ValueError:
            length = -1
        if not 0 < length <= MAX_UPLOAD:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "invalid_argument",
                        "Invalid upload size")
            return
        try:
            with self.owner._lock:
                if self.owner._stopping or not self.owner.session_active(identity):
                    self._error(HTTPStatus.SERVICE_UNAVAILABLE, "host_stopping",
                                "Web UI is stopping")
                    return
                record = transfers.upload(
                    identity, self.rfile, length, names[0] if names else "upload.bin",
                )
        except TimeoutError:
            self._error(HTTPStatus.REQUEST_TIMEOUT, "upload_timeout", "Upload timed out")
            return
        except ValueError:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "upload_rejected",
                        "Upload rejected by size or quota")
            return
        except OSError:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, "storage_unavailable",
                        "Upload storage unavailable")
            return
        self._json(HTTPStatus.CREATED, {
            "id": record.id, "size": record.size, "sha256": record.sha256,
            "filename": record.filename, "expires_at": record.expires_at,
        })
        self.close_connection = True

    def _download(self, identity: str, path: str) -> None:
        transfers = self.owner.transfers
        parts = path.split("/")
        if transfers is None or len(parts) != 6 or parts[-1] != "download":
            self._error(HTTPStatus.NOT_FOUND, "not_found", "Download unavailable")
            return
        try:
            record, source = transfers.open_download(identity, parts[-2])
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "not_found", "Download unavailable")
            return
        except (OSError, ValueError):
            self._error(HTTPStatus.CONFLICT, "stale_revision", "Staged file changed")
            return
        with source:
            self._headers(HTTPStatus.OK, "application/octet-stream", record.size,
                          attachment=record.filename)
            while True:
                if self.owner._stopping or not self.owner.session_active(identity):
                    self.close_connection = True
                    return
                chunk = source.read(65536)
                if not chunk:
                    return
                self.wfile.write(chunk)

    def _events(self, identity: str, cursor: str) -> None:
        if not self.owner._streams.acquire(blocking=False):
            self._error(HTTPStatus.TOO_MANY_REQUESTS, "resource_busy", "Too many streams")
            return
        with self.owner._stream_condition:
            self.owner._stream_count += 1
        try:
            try:
                self.owner.application.replay(cursor, limit=1)
            except CursorExpired:
                self._error(HTTPStatus.GONE, "cursor_expired", "Reload session snapshot")
                return
            self.close_connection = True
            self._headers(HTTPStatus.OK, "text/event-stream; charset=utf-8")
            self.connection.settimeout(2)
            self.wfile.flush()
            deadline = time.monotonic() + 30
            heartbeat = time.monotonic()
            while self.owner.session_active(identity) and time.monotonic() < deadline:
                events = self.owner.application.replay(cursor, limit=100)
                for event in events:
                    cursor = event["cursor"]
                    payload = json.dumps(event, separators=(",", ":"), ensure_ascii=False)
                    if len(payload.encode("utf-8")) > 65_536:
                        reset = json.dumps({"kind": "stream.reset_required", "cursor": cursor})
                        self.wfile.write(f"id: {cursor}\ndata: {reset}\n\n".encode())
                        self.wfile.flush()
                        return
                    self.wfile.write(f"id: {cursor}\ndata: {payload}\n\n".encode())
                if events:
                    self.wfile.flush()
                now = time.monotonic()
                if now - heartbeat >= 15:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    heartbeat = now
                time.sleep(0.15)
        except (OSError, CursorExpired, sqlite3.Error):
            pass
        finally:
            with self.owner._stream_condition:
                self.owner._stream_count -= 1
                self.owner._stream_condition.notify_all()
            self.owner._streams.release()
