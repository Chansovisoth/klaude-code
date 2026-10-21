"""One terminal turn's fenced Memory lease and transcript writes."""

from __future__ import annotations

from typing import Any

from klaude_core import Agent
from klaude_core.memory import Memory
from klaude_core.session_runtime import capture

from .contracts import PublicEvent
from .coordination import DurableTurns, LeaseLost


class SessionTurn:
    """Terminal compatibility seam; provider/tool boundaries call ``guard``."""

    def __init__(
        self, memory: Any, agent: Agent, session_id: str, client_id: str, turn_id: str,
        *, claimed: bool = False, journal: bool = False,
    ) -> None:
        self.memory = memory
        self.agent = agent
        self.session_id = session_id
        self.client_id = client_id
        self.turn_id = turn_id
        self.claimed = claimed
        self.started = False
        self.fence: int | None = None
        self.journal: DurableTurns | None
        if journal and isinstance(memory, Memory) and isinstance(agent, Agent):
            if capture(agent) is None:
                raise ValueError("explicit model/runtime selection required")
            self.journal = DurableTurns(memory)
        else:
            # Test and compatibility clients with minimal Agent doubles keep
            # the older Memory seam; production Agent instances use the journal.
            self.journal = None
        self.request_id = f"terminal:{turn_id}"
        self._assistants: list[tuple[str, object | None]] = []

    def claim(self) -> bool:
        if self.claimed:
            return True
        if self.journal is not None:
            self.journal.recover_session(self.session_id)
        self.claimed = bool(self.memory.acquire_session_lease(
            self.session_id, self.client_id, self.turn_id
        ))
        if self.claimed and isinstance(self.memory, Memory):
            self.fence = self.memory.session_lease_fence(
                self.session_id, self.client_id, self.turn_id
            )
        return self.claimed

    def guard(self) -> None:
        if isinstance(self.memory, Memory):
            if self.fence is None:
                self.fence = self.memory.session_lease_fence(
                    self.session_id, self.client_id, self.turn_id
                )
            self.memory.assert_session_lease(
                self.session_id, self.client_id, self.turn_id, self.fence
            )

    def start(self, text: str, *, model_content: object | None = None) -> None:
        if not self.claimed or self.started:
            raise RuntimeError("turn must hold a fresh session lease")
        try:
            self.guard()
            if self.journal is not None:
                runtime = capture(self.agent)
                if runtime is None or self.fence is None:
                    raise ValueError("explicit model/runtime selection required")
                self.journal.admit_claimed(
                    request_id=self.request_id, session_id=self.session_id,
                    turn_id=self.turn_id, worker_id=self.client_id, fence=self.fence,
                    text=text, scope="standard", runtime=runtime,
                    model_content=model_content,
                )
                self.started = True
                self.journal.mark_started(
                    self.session_id, self.turn_id, self.client_id, self.fence,
                )
            else:
                self.memory.start_session_turn(
                    self.session_id, self.client_id, self.turn_id, text,
                    model_content=model_content,
                    **({"runtime": capture(self.agent), "fence": self.fence}
                       if isinstance(self.memory, Memory) else {}),
                )
                self.started = True
        except BaseException:
            try:
                self.release("failed")
            except Exception:
                # Keep the original admission error; expired ownership will
                # recover any receipt whose terminal write also failed.
                pass
            raise

    def save_assistant(self, content: str, *, model_content: object | None = None) -> None:
        if not self.started:
            raise RuntimeError("turn has not started")
        if isinstance(self.memory, Memory):
            self.guard()
            if self.journal is not None:
                self._assistants.append((content, model_content))
                return
            assert self.fence is not None
            self.memory.log_turn_fenced(
                self.session_id, self.client_id, self.turn_id, self.fence,
                "assistant", content, model_content=model_content,
            )
        elif model_content is None:
            self.memory.log_turn(self.session_id, "assistant", content)
        else:
            self.memory.log_turn(
                self.session_id, "assistant", content, model_content=model_content,
            )

    def publish_execution(self, event: PublicEvent) -> None:
        """Mirror terminal execution through the existing fenced public journal."""
        if self.journal is not None and self.started and self.fence is not None:
            self.journal.append_public(
                self.session_id, self.turn_id, self.client_id, self.fence, event,
            )

    def release(
        self, state: str = "idle", *, completion_payload: dict[str, Any] | None = None,
    ) -> bool:
        if not self.claimed:
            return False
        self.claimed = False
        if self.journal is not None and self.started and self.fence is not None:
            terminal = {
                "idle": "completed", "failed": "failed", "interrupted": "cancelled",
            }.get(state, "failed")
            try:
                self.journal.finish(
                    request_id=self.request_id, session_id=self.session_id,
                    turn_id=self.turn_id, worker_id=self.client_id,
                    fence=self.fence, state=terminal, assistant=None,
                    assistant_messages=self._assistants,
                    legacy_completion=completion_payload,
                )
            except LeaseLost:
                return False
            return True
        return bool(self.memory.release_session_lease(
            self.session_id, self.client_id, self.turn_id, state=state,
            **({"fence": self.fence} if isinstance(self.memory, Memory) else {}),
        ))
