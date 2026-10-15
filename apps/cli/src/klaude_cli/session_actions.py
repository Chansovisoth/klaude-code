"""Ordered, bounded session-setting writes, separate from coalesced snapshots."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from klaude_core.ai_defaults import DefaultsChange, save_defaults
from klaude_core.config import save_provider_secret
from klaude_core.library_artifacts import execute_artifact_change
from klaude_core.model_connections import ModelConnection, connection_registry
from klaude_core.model_management import ModelChange, apply_model_change
from klaude_core.ssh_servers import change as change_ssh_server


@dataclass(frozen=True)
class SessionSettingUpdate:
    session_id: str
    client_id: str
    detail: str
    runtime: dict | None = None


@dataclass(frozen=True)
class AutomaticMemoryUpdate:
    session_id: str
    client_id: str
    revision: int
    enabled: bool


@dataclass(frozen=True)
class MemoryFactUpdate:
    session_id: str
    client_id: str
    memory_id: str
    replacement: str | None


@dataclass(frozen=True)
class LibrarySessionChange:
    session_id: str
    identity: str
    target: str
    operation: str


@dataclass(frozen=True)
class LibraryArtifactChange:
    session_id: str
    identity: str
    root: str
    operation: str
    target: str = ""
    revision: int = 0
    value: str = field(default="", repr=False)
    kind: str = "document"
    workspace: str = ""


@dataclass(frozen=True)
class ModelConnectionAdd:
    session_id: str
    client_id: str
    cfg: Any = field(repr=False, compare=False)
    connection: ModelConnection
    secret: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True)
class ModelConnectionUpdate:
    session_id: str
    identity: str
    cfg: Any = field(repr=False, compare=False)
    change: ModelChange


@dataclass(frozen=True)
class AIDefaultUpdate:
    session_id: str
    identity: str
    cfg: Any = field(repr=False, compare=False)
    change: DefaultsChange


@dataclass(frozen=True)
class ImageGenerationUpdate:
    session_id: str
    identity: str
    cfg: Any = field(repr=False, compare=False)
    candidate: dict
    revision: str


@dataclass(frozen=True)
class SessionTitleUpdate:
    session_id: str
    identity: str
    name: str
    expected_name: str
    detail: str


@dataclass(frozen=True)
class SearchProviderSecret:
    session_id: str
    identity: str
    cfg: Any = field(repr=False, compare=False)
    name: str
    value: str = field(repr=False, compare=False)
    catalog_backend: str = ""
    owner: str = "search"


@dataclass(frozen=True)
class SSHServerChange:
    session_id: str
    identity: str
    root: str
    operation: str
    definition: dict | None = None
    target: str = ""
    revision: str = ""
    default_revision: str = ""


class SessionActionWriter:
    """Accepted actions retain their original scope and drain on close."""

    def __init__(self, memory, emit):
        self.memory = memory
        self.emit = emit
        self._condition = threading.Condition()
        self._pending: deque[
            SessionSettingUpdate
            | AutomaticMemoryUpdate
            | MemoryFactUpdate
            | LibrarySessionChange
            | LibraryArtifactChange
            | ModelConnectionAdd
            | ModelConnectionUpdate
            | AIDefaultUpdate
            | ImageGenerationUpdate
            | SessionTitleUpdate
            | SearchProviderSecret
            | SSHServerChange
        ] = deque()
        self._closed = False
        self._failed = False
        self._unavailable = False
        self._session_unavailable = False
        self._thread: threading.Thread | None = None

    def submit(
        self,
        update: SessionSettingUpdate
        | AutomaticMemoryUpdate
        | MemoryFactUpdate
        | LibrarySessionChange
        | LibraryArtifactChange
        | ModelConnectionAdd
        | ModelConnectionUpdate
        | AIDefaultUpdate
        | ImageGenerationUpdate
        | SessionTitleUpdate
        | SearchProviderSecret | SSHServerChange,
    ) -> bool:
        with self._condition:
            if (
                self._closed
                or self._unavailable
                or len(self._pending) >= 128
                or self._session_unavailable
                and not isinstance(
                    update, (LibraryArtifactChange, ModelConnectionAdd, ModelConnectionUpdate,
                             AIDefaultUpdate, ImageGenerationUpdate, SearchProviderSecret,
                             SSHServerChange)
                )
            ):
                self._failed = True
                return False
            if isinstance(update, SessionSettingUpdate) and (
                not update.detail or len(update.detail) > 2048
            ):
                self._failed = True
                return False
            self._pending.append(update)
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, daemon=True, name="klaude-session-actions"
                )
                self._thread.start()
            self._condition.notify()
            return True

    def _run(self) -> None:
        connection = None
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closed or self._pending)
                    if not self._pending:
                        return
                    update = self._pending.popleft()
                saved = False
                if isinstance(update, SSHServerChange):
                    from pathlib import Path

                    result, error = None, ""
                    try:
                        result = change_ssh_server(
                            Path(update.root), update.operation, definition=update.definition,
                            target=update.target, revision=update.revision,
                            default_revision=update.default_revision,
                        )
                    except ValueError as exc:
                        error = str(exc)
                    except Exception:
                        error = "SSH setting save unconfirmed; reload before retrying"
                    if error:
                        with self._condition:
                            self._failed = True
                    self.emit("ssh_server_saved", (update, result, error))
                    continue
                if isinstance(update, LibraryArtifactChange):
                    from pathlib import Path

                    result, error = None, ""
                    try:
                        result = execute_artifact_change(
                            Path(update.root), update.operation, target=update.target,
                            revision=update.revision, value=update.value, kind=update.kind,
                            session=update.session_id, workspace=Path(update.workspace),
                        )
                    except ValueError as exc:
                        error = str(exc)
                    except FileExistsError:
                        error = "Export file already exists; choose a new filename"
                    except FileNotFoundError:
                        error = "File or directory no longer exists; reload before retrying"
                    except Exception:
                        error = "Artifact change unconfirmed; reload before retrying"
                        with self._condition:
                            self._failed = True
                    self.emit("library_artifact_saved", (update, result, error))
                    continue
                if isinstance(update, LibrarySessionChange):
                    error = ""
                    try:
                        if update.target == update.session_id and update.operation != "restore":
                            raise ValueError(
                                "Open another session before archiving or deleting this one"
                            )
                        if connection is None:
                            connection = self.memory.open_session_io()
                        connection.change_session_archive(update.target, update.operation)
                    except ValueError as exc:
                        error = str(exc)
                    except Exception:
                        error = "Session change unconfirmed; reload before retrying"
                        with self._condition:
                            self._failed = True
                    self.emit("library_session_saved", (update, error))
                    continue
                if isinstance(update, SearchProviderSecret):
                    catalog_ok = True
                    try:
                        save_provider_secret(update.cfg.config_dir, update.name, update.value)
                        saved = True
                    except Exception:
                        with self._condition:
                            self._failed = True
                    if saved and update.catalog_backend == "gemini_api":
                        try:
                            from klaude_core.model_runtime import save_model_cache

                            save_model_cache(update.cfg.data_dir / "model-cache.json", [],
                                             backend="gemini_api", invalidate=True)
                        except Exception:
                            catalog_ok = False
                    self.emit("fetch_provider_saved" if update.owner == "fetch"
                              else "search_provider_saved",
                              (update.session_id, update.identity, saved, catalog_ok))
                    continue
                if isinstance(update, ImageGenerationUpdate):
                    from klaude_core.image_generation import save

                    result, error = None, ""
                    try:
                        result = save(update.cfg, update.candidate, update.revision)
                    except ValueError as exc:
                        error = str(exc)
                    except Exception:
                        error = "Image settings save unconfirmed; Reload before retrying"
                    if error:
                        with self._condition:
                            self._failed = True
                    self.emit("image_generation_saved", (update, result, error))
                    continue
                if isinstance(update, AIDefaultUpdate):
                    result, error = None, ""
                    try:
                        result = save_defaults(update.cfg, update.change)
                    except Exception:
                        error = "AI Defaults save unconfirmed; reload before retrying"
                        with self._condition:
                            self._failed = True
                    self.emit(
                        "ai_defaults_saved", (update.session_id, update.identity, result, error)
                    )
                    continue
                if isinstance(update, ModelConnectionUpdate):
                    result, error = None, ""
                    try:
                        result = apply_model_change(update.cfg, update.change)
                    except ValueError as exc:
                        error = str(exc)
                    except Exception:
                        error = "Model change unconfirmed; reload and review before retrying"
                    if error:
                        with self._condition:
                            self._failed = True
                    self.emit(
                        "model_connection_updated",
                        (
                            update.session_id,
                            update.identity,
                            result,
                            error,
                        ),
                    )
                    continue
                if isinstance(update, ModelConnectionAdd):
                    try:
                        registry = connection_registry(update.cfg)
                        registry.migrate(update.cfg, update.cfg.data_dir / "chat-preferences.json")
                        registry.add(update.connection, secret=update.secret)
                        saved = True
                    except Exception:
                        with self._condition:
                            self._failed = True
                    # The secret never travels back through an acknowledgement.
                    self.emit(
                        "model_connection_saved",
                        (
                            update.session_id,
                            update.connection,
                            saved,
                        ),
                    )
                    continue
                try:
                    if connection is None:
                        try:
                            if self._session_unavailable:
                                raise RuntimeError("Session storage unavailable")
                            connection = self.memory.open_session_io()
                        except Exception:
                            with self._condition:
                                self._session_unavailable = True
                            raise
                    if isinstance(update, SessionTitleUpdate):
                        saved = connection.rename_session_if_current(
                            update.session_id, update.name, update.expected_name
                        )
                        if saved:
                            try:
                                connection.record_session_update(
                                    update.session_id,
                                    "utility",
                                    update.detail + " · " + update.name,
                                )
                            except Exception:
                                self.emit("utility_history_failed", update.session_id)
                    elif isinstance(update, MemoryFactUpdate):
                        saved = connection.update_fact(update.memory_id, update.replacement)
                        if not saved:
                            with self._condition:
                                self._failed = True
                    elif isinstance(update, AutomaticMemoryUpdate):
                        connection.set_auto_memory(update.enabled)
                        saved = True
                    else:
                        connection.record_session_update(
                            update.session_id, update.client_id, update.detail,
                            **({"runtime": update.runtime} if update.runtime is not None else {}),
                        )
                        saved = True
                except Exception:
                    # Never blindly retry a possibly published transaction.
                    with self._condition:
                        self._failed = True
                self.emit(
                    "session_title_saved"
                    if isinstance(update, SessionTitleUpdate)
                    else "memory_fact_saved"
                    if isinstance(update, MemoryFactUpdate)
                    else "memory_setting_saved"
                    if isinstance(update, AutomaticMemoryUpdate)
                    else "session_setting_saved",
                    (update, saved),
                )
        except Exception:
            with self._condition:
                self._failed = self._unavailable = True
                updates = list(self._pending)
                self._pending.clear()
            for update in updates:
                if isinstance(update, SSHServerChange):
                    self.emit("ssh_server_saved", (
                        update, None, "SSH setting save unconfirmed; reload before retrying"
                    ))
                    continue
                if isinstance(update, LibraryArtifactChange):
                    self.emit("library_artifact_saved", (
                        update, None, "Artifact change unconfirmed; reload before retrying"
                    ))
                    continue
                if isinstance(update, LibrarySessionChange):
                    self.emit("library_session_saved", (
                        update, "Session change unconfirmed; reload before retrying"
                    ))
                    continue
                if isinstance(update, ImageGenerationUpdate):
                    self.emit("image_generation_saved", (
                        update, None, "Image settings save unconfirmed; Reload"
                    ))
                    continue
                if isinstance(update, AIDefaultUpdate):
                    self.emit(
                        "ai_defaults_saved",
                        (
                            update.session_id,
                            update.identity,
                            None,
                            "AI Defaults save unconfirmed; reload to verify",
                        ),
                    )
                    continue
                if isinstance(update, ModelConnectionUpdate):
                    self.emit(
                        "model_connection_updated",
                        (
                            update.session_id,
                            update.identity,
                            None,
                            "Model change unconfirmed; reload to verify",
                        ),
                    )
                    continue
                if isinstance(update, ModelConnectionAdd):
                    self.emit(
                        "model_connection_saved",
                        (
                            update.session_id,
                            update.connection,
                            False,
                        ),
                    )
                    continue
                self.emit(
                    "session_title_saved"
                    if isinstance(update, SessionTitleUpdate)
                    else "memory_fact_saved"
                    if isinstance(update, MemoryFactUpdate)
                    else "memory_setting_saved"
                    if isinstance(update, AutomaticMemoryUpdate)
                    else "session_setting_saved",
                    (update, False),
                )
        finally:
            if connection is not None:
                connection.db.close()

    def close(self, *, wait: bool = False) -> bool:
        with self._condition:
            self._closed = True
            self._condition.notify()
        if wait and self._thread is not None:
            self._thread.join(2)
        with self._condition:
            return (
                not self._failed
                and not self._pending
                and (self._thread is None or not self._thread.is_alive())
            )
