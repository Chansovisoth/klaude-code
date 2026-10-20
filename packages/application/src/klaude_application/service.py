"""In-process chat service with an owned synchronous Agent worker."""

from __future__ import annotations

import asyncio
import dataclasses
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from klaude_core import Agent, AgentEvent, TurnScope
from klaude_core.config import Config
from klaude_core.memory import Memory
from klaude_core.model_runtime import ModelInfo
from klaude_core.session_runtime import capture

from .chat_attachments import ChatAttachmentInput
from .composition import open_local_session
from .contracts import ApprovalRequest, EventKind, PublicEvent, TurnReceipt, UserInputRequest
from .coordination import DurableTurns, LeaseLost, QueuedTurn
from .interactions import InteractionBroker, user_input_tool
from .lease import SessionLeaseKeeper
from .local_runtime import local_runtime_matches, saved_local_choice
from .runner import iter_agent_events
from .sessions import SessionDirectory, SessionMessageForkChange
from .settings import ChatSettings


@dataclass
class TurnHandle:
    """One accepted turn with replayable, nonblocking public delivery."""

    request_id: str
    session_id: str
    turn_id: str
    agent: Agent = field(repr=False)
    events_queue: queue.Queue[PublicEvent] = field(
        default_factory=lambda: queue.Queue(maxsize=128), repr=False
    )
    cancelled: threading.Event = field(default_factory=threading.Event, repr=False)
    finished: threading.Event = field(default_factory=threading.Event, repr=False)
    worker: threading.Thread | None = field(default=None, repr=False)
    renewer: threading.Thread | None = field(default=None, repr=False)
    broker: InteractionBroker | None = field(default=None, repr=False)
    state: Literal[
        "running", "completed", "partial", "failed", "cancelled", "interrupted"
    ] = "running"
    failure: BaseException | None = field(default=None, repr=False)
    event_sink: Callable[[PublicEvent], str] | None = field(default=None, repr=False)
    detached: bool = False
    reset_required: bool = False
    _sequence: int = 0
    _message_index: int = 0
    _message_offset: int = 0
    _pending_text: str = ""
    _pending_offset: int = 0
    _pending_message_id: str = ""
    _final_message_id: str = ""
    _last_flush: float = field(default_factory=time.monotonic, repr=False)

    def flush_delta(self) -> str:
        """Coalesce small public fragments before a durable event write."""
        if not self._pending_text or self.event_sink is None:
            return ""
        event = PublicEvent(
            kind="message.delta", session_id=self.session_id, turn_id=self.turn_id,
            sequence=self._sequence + 1, text=self._pending_text,
            message_id=self._pending_message_id, offset=self._pending_offset,
        )
        cursor = self.event_sink(event)
        self._pending_text = ""
        self._last_flush = time.monotonic()
        self.emit(
            "message.delta", persist=False, cursor=cursor, text=event.text,
            message_id=event.message_id, offset=event.offset,
        )
        return cursor

    def emit(self, kind: EventKind, *, persist: bool = True, **fields: Any) -> None:
        self._sequence += 1
        event = PublicEvent(
            kind=kind, session_id=self.session_id, turn_id=self.turn_id,
            sequence=self._sequence, **fields,
        )
        if persist and self.event_sink is not None:
            cursor = self.event_sink(event)
            event = dataclasses.replace(event, cursor=cursor)
        if self.reset_required or self.detached:
            return
        try:
            self.events_queue.put_nowait(event)
        except queue.Full:
            self.reset_required = True
            cursor = self.flush_delta() or event.cursor
            while True:
                try:
                    self.events_queue.get_nowait()
                except queue.Empty:
                    break
            self.events_queue.put_nowait(PublicEvent(
                kind="stream.reset_required", session_id=self.session_id,
                turn_id=self.turn_id, sequence=self._sequence, cursor=cursor,
            ))

    def cancel(self) -> None:
        if self.detached:
            raise RuntimeError("another worker owns this request")
        self.cancelled.set()
        if self.broker is not None:
            self.broker.cancel_all()
        self.agent.cancel_active_transports()

    async def events(self):
        """Yield bounded public events without running Agent on the event loop."""
        while True:
            try:
                item = self.events_queue.get_nowait()
            except queue.Empty:
                if self.finished.is_set():
                    return
                await asyncio.sleep(0.01)
                continue
            yield item
            if item.kind == "stream.reset_required":
                return

    async def result(self) -> TurnReceipt:
        while not self.finished.is_set():
            await asyncio.sleep(0.01)
        if self.failure is not None:
            raise self.failure
        return TurnReceipt(self.request_id, self.session_id, self.turn_id, self.state)

    async def join(self, timeout: float = 5.0) -> bool:
        worker = self.worker
        deadline = time.monotonic() + timeout
        while worker is not None and worker.is_alive() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        return worker is None or not worker.is_alive()


class HeadlessApplication:
    """Local chat owner with durable admission; no HTTP or terminal dependency."""

    def __init__(
        self, agent: Agent, memory: Memory, session_id: str | None = None,
        *, allow_user_input_tool: bool = True, allow_approvals: bool = True,
    ) -> None:
        self.agent = agent
        self.memory = memory
        self.session_id = session_id or uuid.uuid4().hex
        self.client_id = uuid.uuid4().hex
        self.controller_id = uuid.uuid4().hex
        self.allow_user_input_tool = allow_user_input_tool
        self.allow_approvals = allow_approvals
        self.turns = DurableTurns(memory)
        self.sessions = SessionDirectory(memory)
        config = getattr(agent, "tool_config", None)
        self.settings = (
            ChatSettings(config.data_dir / "chat-preferences.json")
            if isinstance(config, Config) else None
        )
        self._lock = threading.RLock()
        self._requests: dict[str, tuple[tuple[str, str, str, str], TurnHandle]] = {}
        self._active: TurnHandle | None = None
        self._closed = False
        self.agent.set_session_context(self.session_id)

    @classmethod
    def open_local(
        cls, workdir: Path, runtime: Any, *, config: Config | None = None,
        model: str | None = None, tool_selector: Any = None,
        session_id: str | None = None,
    ) -> HeadlessApplication:
        agent, memory = open_local_session(
            workdir, runtime, config=config, model=model, tool_selector=tool_selector
        )
        return cls(agent, memory, session_id)

    def activate_workspace(self, slug: str = "session") -> str:
        """Explicitly invoke existing Git branch/dirty-tree protection."""
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            path = str(self.agent.workdir.resolve())
            binding = self.turns.workspace(self.session_id)
            if binding is not None and binding[0] != path:
                raise ValueError("session is bound to another workspace")
            result = self.agent.workspace.ensure_work_branch(slug)
            if binding is None:
                self.turns.bind_workspace(self.session_id, path, expected_revision=0)
            return result

    def rebind_workspace(self, *, expected_revision: int, slug: str = "session") -> str:
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            current = self.turns.workspace(self.session_id)
            if current is None or current[1] != expected_revision:
                raise ValueError("stale workspace revision")
            result = self.agent.workspace.ensure_work_branch(slug)
            self.turns.bind_workspace(
                self.session_id, str(self.agent.workdir.resolve()),
                expected_revision=expected_revision,
            )
            return result

    def set_plan_mode(
        self, enabled: bool, *, expected_revision: int, request_id: str | None = None,
    ) -> int:
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            revision = self.turns.set_plan_mode(
                self.session_id, enabled, expected_revision=expected_revision,
                request_id=request_id,
            )
            self.agent.plan_mode = self.turns.session_options(self.session_id)[1]
            return revision

    def choose_local_model(
        self, info: ModelInfo, *, expected_revision: int,
        request_id: str | None = None,
    ) -> int:
        """Select a metadata-verified local model at an idle boundary."""
        if not isinstance(info, ModelInfo) or info.backend != "ollama":
            raise ValueError("only the configured local Ollama model can be selected")
        return self._choose_runtime(
            info, self.agent.reasoning_mode,
            self.agent.reasoning_effort if self.agent.reasoning_mode == "thinking" else None,
            expected_revision=expected_revision, request_id=request_id,
        )

    def choose_reasoning(
        self, mode: str, effort: str | None, *, expected_revision: int,
        request_id: str | None = None, info: ModelInfo | None = None,
    ) -> int:
        """Set Standard or a supported Thinking effort for the current model."""
        selected = info or self.agent.model_info
        if selected.ref != self.agent.model_info.ref:
            raise ValueError("model changed")
        return self._choose_runtime(
            selected, mode, effort,
            expected_revision=expected_revision, request_id=request_id,
        )

    def _choose_runtime(
        self, info: ModelInfo, mode: str, effort: str | None, *,
        expected_revision: int, request_id: str | None,
    ) -> int:
        if request_id is not None:
            self._validate_request_id(request_id)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("invalid settings revision")
        if info.backend != "ollama" or self.agent.model_info.backend != "ollama":
            raise ValueError("browser model controls currently require Ollama")
        cfg = self.agent.tool_config
        if not isinstance(cfg, Config):
            raise ValueError("local model configuration unavailable")
        local_runtime_matches(self.agent, cfg)
        types = info.capabilities.thinking_types
        if mode == "standard":
            if effort is not None or (types is not None and "disabled" not in types):
                raise ValueError("Standard mode is unsupported by this model")
        elif mode == "thinking":
            if (effort not in info.capabilities.effort_levels or effort == "off"
                    or (types is not None
                        and not any(value in types for value in ("enabled", "adaptive")))):
                raise ValueError("Thinking effort is unsupported by this model")
        else:
            raise ValueError("invalid reasoning mode")
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            if self.turns.queue(self.session_id, self.controller_id, include_submitted=False):
                raise RuntimeError("queued work must finish before changing models")
            previous = capture(self.agent)
            if previous is None:
                raise ValueError("current model is not selected")
            selected = {
                **previous, "model": info.ref, "mode": mode, "effort": effort,
                "definition": info.connection_revision,
                "credentials": info.credential_revision, "at": time.time(),
            }
            revision = self.turns.set_runtime_choice(
                self.session_id, selected, previous,
                expected_revision=expected_revision, request_id=request_id,
            )
            saved = self.memory.session_runtime(self.session_id)
            fields = ("model", "mode", "effort", "definition", "credentials")
            if (self.turns.session_options(self.session_id)[0] != revision
                    or saved is None
                    or any(saved[key] != selected[key] for key in fields)):
                raise ValueError("runtime choice was superseded")
            self.agent.model = info.model_id
            self.agent.model_info = info
            self.agent.reasoning_mode = mode
            if effort is not None:
                self.agent.reasoning_effort = effort
            self.agent.ollama_think = effort if mode == "thinking" else False
            self.agent.ollama_code_think = self.agent.ollama_think
            self.agent.set_session_context(self.session_id)
            return revision

    def resume(self, session_id: str) -> None:
        """Restore private continuity only for the explicitly selected runtime."""
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            if self.turns.queue(self.session_id, self.controller_id, include_submitted=False):
                raise RuntimeError("queued work must finish before switching sessions")
            if self.memory.session_archived(session_id):
                raise ValueError("session is archived")
            turns = self.memory.load_session(session_id)
            if not turns:
                raise ValueError("session does not exist")
            saved = self.memory.session_runtime(session_id)
            current = capture(self.agent)
            if saved is None or current is None or any(
                saved[key] != current[key]
                for key in ("model", "mode", "effort", "definition", "credentials")
            ):
                raise ValueError("explicit model/runtime selection required")
            binding = self.turns.workspace(session_id)
            if binding is not None and binding[0] != str(self.agent.workdir.resolve()):
                raise ValueError("session is bound to another workspace")
            self.turns.recover_session(session_id)
            self.agent.restore_session(turns)
            self.agent.plan_mode = self.turns.session_options(session_id)[1]
            self.agent.set_session_context(session_id)
            self.session_id = session_id

    def resume_local(self, session_id: str) -> None:
        """Restore an exact saved Ollama choice, then resume private continuity."""
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            if self.turns.queue(self.session_id, self.controller_id, include_submitted=False):
                raise RuntimeError("queued work must finish before switching sessions")
            info, mode, effort = saved_local_choice(self.agent, self.memory, session_id)
            agent = self.agent
            previous = (
                agent.model, agent.model_info, agent.reasoning_mode,
                agent.reasoning_effort, agent.ollama_think, agent.ollama_code_think,
            )
            agent.model = info.model_id
            agent.model_info = info
            agent.reasoning_mode = mode
            if effort is not None:
                agent.reasoning_effort = effort
            agent.ollama_think = effort if mode == "thinking" else False
            agent.ollama_code_think = agent.ollama_think
            try:
                self.resume(session_id)
            except BaseException:
                (agent.model, agent.model_info, agent.reasoning_mode,
                 agent.reasoning_effort, agent.ollama_think,
                 agent.ollama_code_think) = previous
                try:
                    agent.restore_session(self.memory.load_session(self.session_id))
                    agent.plan_mode = self.turns.session_options(self.session_id)[1]
                    agent.set_session_context(self.session_id)
                except Exception:
                    pass
                raise

    def branch_message(self, row_id: int, *, retry: bool = False) -> tuple[str, str | None]:
        """Keep the original conversation and activate its selected prefix."""
        with self._lock:
            if self._closed:
                raise RuntimeError("application is closed")
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            if self.turns.queue(self.session_id, self.controller_id, include_submitted=False):
                raise RuntimeError("queued work must finish before branching")
            target = uuid.uuid4().hex
            prompt = self.sessions.fork_message(SessionMessageForkChange(
                self.session_id, target, row_id, retry,
            ))
            self.agent.restore_session(self.memory.load_session(target))
            self.agent.plan_mode = self.turns.session_options(target)[1]
            self.agent.set_session_context(target)
            self.session_id = target
            return target, prompt

    def start_session(self) -> str:
        """Create an empty session in the current workspace without model work."""
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            if self.turns.queue(self.session_id, self.controller_id, include_submitted=False):
                raise RuntimeError("queued work must finish before switching sessions")
            session_id = uuid.uuid4().hex
            self.turns.bind_workspace(
                session_id, str(self.agent.workdir.resolve()), expected_revision=0,
            )
            self.agent.restore_session([])
            self.agent.plan_mode = False
            self.agent.set_session_context(session_id)
            self.session_id = session_id
            return session_id

    def reconcile_interrupted(
        self, *, expected_fence: int, acknowledge_unknown_effects: bool,
        request_id: str | None = None,
    ) -> bool:
        """Unfreeze only after the caller explicitly reviews possible external effects."""
        if acknowledge_unknown_effects is not True:
            raise ValueError("unknown effects must be explicitly acknowledged")
        with self._lock:
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("turn is active")
            return self.turns.reconcile_interrupted(
                self.session_id, expected_fence, request_id=request_id
            )

    def public_history(self) -> tuple[dict[str, str], ...]:
        """Project saved public dialogue, never model_content or system audit."""
        return tuple(
            {"role": turn["role"], "content": turn["content"]}
            for turn in self.memory.load_session(self.session_id)
            if turn["role"] in {"user", "assistant"}
            and isinstance(turn["content"], str)
        )

    def snapshot(
        self, *, viewer_id: str | None = None, control_epoch: int | None = None,
    ) -> dict[str, Any]:
        identity = viewer_id or self.controller_id
        with self._lock:
            snapshot = self.turns.snapshot(self.session_id, identity)
            if control_epoch is not None and snapshot["control_epoch"] != control_epoch:
                snapshot["has_control"] = False
            broker = self._active.broker if self._active is not None else None
            snapshot["interactions"] = (
                list(broker.pending()) if broker is not None and snapshot["has_control"] else []
            )
            return snapshot

    def replay(self, cursor: str, *, limit: int = 500) -> list[dict[str, Any]]:
        return self.turns.replay(self.session_id, cursor, limit=limit)

    def receipt(self, request_id: str) -> TurnReceipt | None:
        admission = self.turns.receipt(request_id)
        if admission is None or admission.session_id != self.session_id:
            return None
        return TurnReceipt(request_id, admission.session_id, admission.turn_id,
                           cast(Any, admission.state))

    def submit(
        self, text: str, *, request_id: str | None = None,
        scope: TurnScope | str = TurnScope.STANDARD,
        _controller_id: str | None = None,
        attachments: ChatAttachmentInput | None = None,
    ) -> TurnHandle:
        if not isinstance(text, str) or not text.strip() or len(text) > 65_536:
            raise ValueError("turn text must contain 1-65536 characters")
        identity = request_id if request_id is not None else uuid.uuid4().hex
        self._validate_request_id(identity)
        selected_scope = TurnScope(scope)
        public_text = attachments.public_text(text) if attachments else text
        input_key = attachments.identity if attachments else ""
        if len(public_text) > 65_536:
            raise ValueError("Message and attachment names must fit in 65536 characters")
        with self._lock:
            if self._closed:
                raise RuntimeError("application is closed")
            runtime = capture(self.agent)
            if runtime is None:
                raise ValueError("explicit model/runtime selection required")
            key = (
                self.session_id, public_text, selected_scope.value,
                self.turns.fingerprint(self.session_id, public_text, selected_scope.value,
                                       runtime, input_key),
            )
            previous = self._requests.get(identity)
            if previous is not None:
                if previous[0] != key:
                    raise ValueError("request ID already used with different input")
                return previous[1]
            if self._active is not None and not self._active.finished.is_set():
                raise RuntimeError("session already has an active turn")
            admission = self.turns.admit(
                request_id=identity, session_id=self.session_id,
                turn_id=uuid.uuid4().hex, worker_id=self.client_id,
                text=public_text, scope=selected_scope.value, runtime=runtime,
                controller_id=_controller_id or self.controller_id,
                input_key=input_key,
                attachments=attachments,
            )
            handle = TurnHandle(identity, self.session_id, admission.turn_id, self.agent)
            handle.state = cast(Any, admission.state)
            if not admission.created:
                handle.detached = True
                handle.finished.set()
                return handle
            handle.event_sink = lambda event: self.turns.append_public(
                handle.session_id, handle.turn_id, self.client_id, admission.fence, event
            )
            handle.emit("turn.accepted", persist=False, cursor=admission.cursor)
            self._requests[identity] = (key, handle)
            self._active = handle
            worker = threading.Thread(
                target=self._run, args=(handle, text, selected_scope, admission.fence, attachments),
                name="klaude-application-turn", daemon=True,
            )
            handle.worker = worker
            try:
                worker.start()
            except BaseException:
                self._requests.pop(identity, None)
                self._active = None
                self.turns.finish(
                    request_id=identity, session_id=self.session_id,
                    turn_id=handle.turn_id, worker_id=self.client_id,
                    fence=admission.fence, state="failed", assistant=None,
                )
                raise
            return handle

    def enqueue(
        self, text: str, *, request_id: str, scope: TurnScope | str = TurnScope.STANDARD,
        creator_id: str | None = None, priority: bool = False,
    ) -> QueuedTurn:
        self._validate_request_id(request_id)
        with self._lock:
            if self._closed:
                raise RuntimeError("application is closed")
            runtime = capture(self.agent)
            if runtime is None:
                raise ValueError("explicit model/runtime selection required")
            return self.turns.enqueue(
                session_id=self.session_id, creator_id=creator_id or self.controller_id,
                request_id=request_id, text=text, scope=TurnScope(scope).value,
                runtime=runtime, priority=priority,
            )

    @staticmethod
    def _validate_request_id(identity: str) -> None:
        if (not isinstance(identity, str) or not 0 < len(identity) <= 128
                or not identity.isascii() or not identity.isprintable()
                or any(character.isspace() for character in identity)):
            raise ValueError("request ID must be 1-128 printable ASCII characters without spaces")

    def queued(self, viewer_id: str | None = None) -> list[dict[str, Any]]:
        return self.turns.queue(self.session_id, viewer_id or self.controller_id)

    def cancel_active(
        self, turn_id: str, *, controller_id: str, control_epoch: int,
    ) -> bool:
        with self._lock:
            if not self.turns.controls(self.session_id, controller_id, control_epoch):
                return False
            active = self._active
            if active is None or active.turn_id != turn_id or active.finished.is_set():
                return False
            receipt = self.turns.receipt(active.request_id)
            if receipt is None or receipt.state != "running":
                return False
            try:
                self.turns.assert_fence(
                    active.session_id, active.turn_id, self.client_id, receipt.fence
                )
            except LeaseLost:
                return False
            active.cancel()
            return True

    def steer(
        self, text: str, *, request_id: str, turn_id: str,
        controller_id: str, control_epoch: int,
        scope: TurnScope | str = TurnScope.STANDARD,
    ) -> QueuedTurn:
        """Durably accept a priority follow-up, then cancel the exact active turn."""
        self._validate_request_id(request_id)
        with self._lock:
            active = self._active
            if active is None or active.turn_id != turn_id or active.finished.is_set():
                raise ValueError("active turn changed")
            runtime = capture(self.agent)
            if runtime is None:
                raise ValueError("explicit model/runtime selection required")
            item = self.turns.enqueue(
                session_id=self.session_id, creator_id=controller_id,
                request_id=request_id, text=text, scope=TurnScope(scope).value,
                runtime=runtime, priority=True,
                required_control_epoch=control_epoch,
            )
            if not self.cancel_active(
                turn_id, controller_id=controller_id, control_epoch=control_epoch,
            ):
                raise RuntimeError("session control changed after steering was queued")
            return item

    def run_next_queued(self) -> TurnHandle | None:
        with self._lock:
            if self._closed or (self._active is not None and not self._active.finished.is_set()):
                return None
            runtime = capture(self.agent)
            if runtime is None:
                raise ValueError("explicit model/runtime selection required")
            item = self.turns.claim_next_queued(self.session_id, runtime)
            if item is None:
                return None
            try:
                handle = self.submit(
                    item.text, request_id=item.request_id, scope=item.scope,
                    _controller_id=item.creator_id,
                )
            except BaseException:
                # Starting is a durable reservation; restart/review decides
                # whether it can be retried. Never silently rerun it here.
                self.turns.pause_queue_item(item)
                raise
            self.turns.mark_queue_submitted(item)
            return handle

    def control(self) -> tuple[str, int] | None:
        return self.turns.control(self.session_id)

    def active_turn_count(self) -> int:
        with self._lock:
            return int(self._active is not None and not self._active.finished.is_set())

    def active_turn_id(self) -> str:
        with self._lock:
            active = self._active
            return active.turn_id if active is not None and not active.finished.is_set() else ""

    def take_control(
        self, controller_id: str, *, expected_epoch: int, request_id: str | None = None,
    ) -> int:
        with self._lock:
            epoch = self.turns.claim_control(
                self.session_id, controller_id, expected_epoch=expected_epoch,
                request_id=request_id,
            )
            active = self._active
            if (active is not None and active.broker is not None
                    and self.turns.controls(self.session_id, controller_id, epoch)):
                for pending in active.broker.pending():
                    if isinstance(pending, ApprovalRequest):
                        active.emit(
                            "approval.required", interaction_id=pending.id, tool=pending.tool
                        )
                    else:
                        active.emit("user_input.required", interaction_id=pending.id)
            return epoch

    def pending_interactions(
        self, *, controller_id: str | None = None, control_epoch: int | None = None,
    ) -> tuple[ApprovalRequest | UserInputRequest, ...]:
        with self._lock:
            identity = controller_id or self.controller_id
            current = self.control()
            epoch = control_epoch if control_epoch is not None else (
                current[1] if current is not None and identity == self.controller_id else -1
            )
            if not self.turns.controls(self.session_id, identity, epoch):
                return ()
            broker = self._active.broker if self._active is not None else None
            return broker.pending() if broker is not None else ()

    def review_interaction(
        self, interaction_id: str, *, controller_id: str | None = None,
        control_epoch: int | None = None,
    ) -> dict[str, str] | None:
        """Return a bounded review only while this client controls the live turn."""
        with self._lock:
            current = self.control()
            identity = controller_id or self.controller_id
            if (current is None or current[0] != identity
                    or control_epoch is not None and current[1] != control_epoch):
                return None
            broker = self._active.broker if self._active is not None else None
            return broker.review(interaction_id) if broker is not None else None

    def decide(
        self, interaction_id: str, answer: str, *,
        controller_id: str | None = None, control_epoch: int | None = None,
    ) -> bool:
        with self._lock:
            identity = controller_id or self.controller_id
            current = self.control()
            epoch = control_epoch if control_epoch is not None else (
                current[1] if current is not None and identity == self.controller_id else -1
            )
            if not self.turns.controls(self.session_id, identity, epoch):
                return False
            broker = self._active.broker if self._active is not None else None
            active = self._active
            if broker is None or active is None:
                return False
            pending = next((item for item in broker.pending() if item.id == interaction_id), None)
            if pending is None or pending.expires_at <= time.time():
                return False
            if isinstance(pending, ApprovalRequest):
                if answer not in {"allow_once", "deny"}:
                    raise ValueError("invalid approval decision")
            elif len(answer) > 1000 or not answer.isprintable():
                raise ValueError("invalid user input")
            receipt = self.turns.receipt(active.request_id)
            if receipt is None:
                return False
            try:
                accepted = self.turns.record_decision(
                    session_id=active.session_id, turn_id=active.turn_id,
                    worker_id=self.client_id, fence=receipt.fence,
                    controller_id=identity, control_epoch=epoch,
                    interaction_id=interaction_id,
                )
            except LeaseLost:
                return False
            if not accepted:
                return False
            return broker.decide(interaction_id, answer)

    def _run(
        self, handle: TurnHandle, text: str, scope: TurnScope, fence: int,
        attachments: ChatAttachmentInput | None = None,
    ) -> None:
        agent = self.agent
        previous_cancel = agent.cancellation_check
        previous_execution = agent.execution_observer
        previous_guard = agent.execution_guard
        previous_tool_guard = agent.tool_execution_guard
        previous_ask = agent.gate._structured_ask
        previous_input = agent.tools.get("request_user_input")
        previous_broker = agent.user_input_broker
        broker = InteractionBroker(
            handle.session_id, handle.turn_id, handle.cancelled,
            lambda kind, identity, tool: handle.emit(
                cast(EventKind, kind), interaction_id=identity, tool=tool
            ),
        )
        handle.broker = broker
        if self.allow_approvals:
            agent.gate.set_structured_ask_callback(broker.ask_permission)
        agent.user_input_broker = broker
        if self.allow_user_input_tool:
            agent.tools["request_user_input"] = user_input_tool(broker)
        agent.cancellation_check = handle.cancelled.is_set
        agent.execution_observer = lambda tool, identity: handle.emit(
            "tool.started", tool=tool, execution_id=identity
        )
        def guard() -> None:
            if handle.cancelled.is_set():
                raise LeaseLost("turn cancelled before tool execution")
            try:
                self.turns.assert_fence(
                    handle.session_id, handle.turn_id, self.client_id, fence
                )
            except LeaseLost:
                handle.cancel()
                raise

        agent.execution_guard = guard
        def tool_guard() -> None:
            if getattr(agent, "workspace", None) is not None:
                binding = self.turns.workspace(handle.session_id)
                if binding is None:
                    raise PermissionError("workspace unbound; activate it before using tools")
                if binding[0] != str(agent.workdir.resolve()):
                    raise PermissionError("session workspace changed; rebind before using tools")

        agent.tool_execution_guard = tool_guard
        lease_keeper = SessionLeaseKeeper(
            self.memory, handle.session_id, self.client_id, handle.turn_id,
            fence=fence, on_lost=handle.cancel,
        )
        handle.renewer = lease_keeper.thread
        lease_keeper.start()
        final_text = ""
        deltas: list[str] = []
        saved = False
        model_content: object | None = None
        saw_error = False
        try:
            handle.emit("turn.started")
            effective_input: str | dict[str, Any] = text
            if attachments:
                try:
                    effective_input = attachments.compose(text, agent, handle.session_id)
                except ValueError as exc:
                    final_text = f"Attachment preparation failed: {exc}"
                    saved = True
                    raise
                self.turns.save_model_input(
                    request_id=handle.request_id, session_id=handle.session_id,
                    turn_id=handle.turn_id, worker_id=self.client_id, fence=fence,
                    model_content=effective_input,
                )
            for event in iter_agent_events(agent, effective_input, scope=scope):
                self._project_event(handle, event, deltas)
                if event.kind == "text" and isinstance(event.payload.get("content"), str):
                    final_text = event.payload["content"]
                    model_content = event.payload.get("model_message")
                    saved = True
                elif event.kind == "error":
                    saw_error = True
                if handle.cancelled.is_set():
                    break
            if handle.cancelled.is_set():
                handle.state = "cancelled"
                agent.mark_interrupted_turn()
                if not saved and deltas:
                    final_text = "".join(deltas)
                    saved = True
            elif saw_error:
                handle.state = "partial" if saved or deltas else "failed"
            elif saved:
                handle.state = "completed"
            else:
                handle.state = "failed"
        except BaseException as exc:
            if not saved and deltas:
                final_text = "".join(deltas)
                saved = True
            if handle.cancelled.is_set():
                handle.state = "cancelled"
            else:
                handle.failure = exc
                handle.state = "failed"
        finally:
            lease_keeper.close()
            agent.cancellation_check = previous_cancel
            agent.execution_observer = previous_execution
            agent.execution_guard = previous_guard
            agent.tool_execution_guard = previous_tool_guard
            agent.gate.set_structured_ask_callback(previous_ask)
            agent.user_input_broker = previous_broker
            if previous_input is None:
                agent.tools.pop("request_user_input", None)
            else:
                agent.tools["request_user_input"] = previous_input
            broker.cancel_all()
            try:
                handle.flush_delta()
                committed = self.turns.finish(
                    request_id=handle.request_id, session_id=handle.session_id,
                    turn_id=handle.turn_id, worker_id=self.client_id, fence=fence,
                    state=handle.state if handle.state != "interrupted" else "failed",
                    assistant=final_text if saved else None, model_content=model_content,
                    message_id=handle._final_message_id,
                )
                if saved:
                    handle.emit(
                        "message.completed", persist=False, cursor=committed.message_cursor,
                        text=final_text[:65_536],
                        message_id=handle._final_message_id or f"{handle.turn_id}:0",
                        offset=0,
                        status="truncated" if len(final_text) > 65_536 else "complete",
                    )
                handle.emit(
                    cast(EventKind, f"turn.{handle.state}"), persist=False,
                    cursor=committed.turn_cursor,
                )
            except LeaseLost:
                handle.state = "interrupted"
                handle.failure = None
                handle.emit("turn.interrupted", persist=False)
            except Exception as exc:
                handle.failure = exc
                handle.state = "interrupted"
                handle.emit("turn.interrupted", persist=False)
            handle.finished.set()
            if handle.state != "interrupted":
                try:
                    self.run_next_queued()
                except Exception:
                    # The queue item remains paused/reviewable. The completed
                    # turn receipt must not be rewritten by scheduling failure.
                    pass

    def _project_event(
        self, handle: TurnHandle, event: AgentEvent, deltas: list[str]
    ) -> None:
        payload = event.payload
        if event.kind == "text_delta":
            value = payload.get("content")
            if isinstance(value, str):
                message_id = f"{handle.turn_id}:{handle._message_index}"
                for start in range(0, len(value), 65_536):
                    piece = value[start:start + 65_536]
                    deltas.append(piece)
                    if not handle._pending_text:
                        handle._pending_offset = handle._message_offset
                        handle._pending_message_id = message_id
                    handle._pending_text += piece
                    handle._message_offset += len(piece)
                    if (len(handle._pending_text) >= 4096
                            or time.monotonic() - handle._last_flush >= 0.25):
                        handle.flush_delta()
        elif event.kind == "text":
            value = payload.get("content")
            if isinstance(value, str):
                handle.flush_delta()
                message_id = f"{handle.turn_id}:{handle._message_index}"
                if not (payload.get("metadata") or {}).get("streamed"):
                    for start in range(0, len(value), 65_536):
                        handle.emit(
                            "message.delta", text=value[start:start + 65_536],
                            message_id=message_id, offset=start,
                        )
                handle._final_message_id = message_id
                handle._message_index += 1
                handle._message_offset = 0
        elif event.kind == "tool_start":
            handle.flush_delta()
            handle.emit(
                "tool.requested", tool=str(payload.get("tool", ""))[:128],
                execution_id=str(payload.get("execution_id", ""))[:64],
            )
        elif event.kind == "tool_result":
            handle.flush_delta()
            metadata = payload.get("metadata") or {}
            executed = metadata.get("executed") is True
            handle.emit(
                "tool.finished", tool=str(payload.get("tool", ""))[:128],
                execution_id=str(metadata.get("execution_id", ""))[:64],
                executed=executed,
                status="executed" if executed else "rejected",
            )

    def close_interactions(self) -> None:
        """Deny pending and future reviews while leaving accepted work running."""
        with self._lock:
            active = self._active
            if active is not None and active.broker is not None:
                active.broker.close_interactions()

    async def close(self, *, drain: bool = False) -> None:
        with self._lock:
            self._closed = True
            active = self._active
        if active is not None and not active.finished.is_set():
            if drain:
                self.close_interactions()
                while not active.finished.is_set():
                    await asyncio.sleep(0.05)
            else:
                active.cancel()
        if active is not None and not await active.join():
            raise RuntimeError("agent worker did not stop during shutdown")
        if active is not None and active.renewer is not None and active.renewer.is_alive():
            raise RuntimeError("lease renewal worker did not stop after cancellation")
        close = getattr(self.agent.runtime, "close", None)
        if callable(close):
            close()
        self.memory.db.close()
