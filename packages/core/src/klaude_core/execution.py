"""Progress-aware, provider-independent execution budgets for one agent turn."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

FAILED_RESULT_PREFIXES = (
    "tool error:",
    "permission denied:",
    "error:",
    "blocked ",
    "skipped ",
)


@dataclass(frozen=True)
class TurnBudgetSnapshot:
    """Public, serializable state for status and model capability context."""

    max_model_steps: int
    model_steps_used: int
    max_tool_calls: int
    tool_calls_used: int
    max_elapsed_seconds: float
    elapsed_seconds: float
    no_progress_streak: int
    max_no_progress: int
    stop_reason: str = ""

    @property
    def model_steps_left(self) -> int:
        return max(0, self.max_model_steps - self.model_steps_used)

    @property
    def tool_calls_left(self) -> int:
        return max(0, self.max_tool_calls - self.tool_calls_used)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["model_steps_left"] = self.model_steps_left
        value["tool_calls_left"] = self.tool_calls_left
        return value


class TurnGovernor:
    """Track useful progress and stop tool activity before a turn can loop.

    The governor never interrupts a running model request or tool. It is checked
    only at safe boundaries, and its stop signal reserves the next model request
    for a tool-free factual finalization.
    """

    def __init__(
        self,
        max_model_steps: int,
        *,
        max_tool_calls: int | None = None,
        max_elapsed_seconds: float = 1_800.0,
        max_no_progress: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_model_steps = max(1, max_model_steps)
        self.max_tool_calls = max(1, max_tool_calls or max(4, self.max_model_steps * 2))
        self.max_elapsed_seconds = max(1.0, max_elapsed_seconds)
        self.max_no_progress = max(1, max_no_progress)
        self._clock = clock
        self._started_at = clock()
        self.model_steps_used = 0
        self.tool_calls_used = 0
        self.no_progress_streak = 0
        self.stop_reason = ""
        self._successful_outcomes: set[str] = set()

    def begin_model_step(self) -> str:
        """Record a safe-boundary model request or return a reason to finalize."""
        if self.stop_reason:
            return self.stop_reason
        if self.elapsed_seconds >= self.max_elapsed_seconds:
            self.stop_reason = "turn wall-time budget reached"
            return self.stop_reason
        if self.model_steps_used >= self.max_model_steps:
            self.stop_reason = "model/tool step budget reached"
            return self.stop_reason
        self.model_steps_used += 1
        return ""

    def observe_tool_result(
        self,
        tool: str,
        result: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Record a completed tool boundary and return a reason to stop tools."""
        self.tool_calls_used += 1
        normalized = " ".join(result.casefold().split())[:2_000]
        failed = normalized.startswith(FAILED_RESULT_PREFIXES)
        outcome = f"{tool}:{normalized}"
        duplicate_outcome = outcome in self._successful_outcomes
        executed = (metadata or {}).get("executed") is not False

        if failed or duplicate_outcome or not executed:
            self.no_progress_streak += 1
        else:
            self.no_progress_streak = 0
            self._successful_outcomes.add(outcome)

        if self.tool_calls_used >= self.max_tool_calls:
            self.stop_reason = "tool-call budget reached"
        elif self.no_progress_streak >= self.max_no_progress:
            self.stop_reason = "tool activity stopped making progress"
        elif self.elapsed_seconds >= self.max_elapsed_seconds:
            self.stop_reason = "turn wall-time budget reached"
        return self.stop_reason

    def charge_delegated_usage(self, *, model_steps: int, tool_calls: int) -> str:
        """Charge completed child work to this turn's non-expandable budget."""
        delegated_steps = max(0, int(model_steps))
        delegated_calls = max(0, int(tool_calls))
        self.model_steps_used += delegated_steps
        self.tool_calls_used += delegated_calls
        if self.model_steps_used >= self.max_model_steps:
            self.stop_reason = "model/tool step budget reached"
        elif self.tool_calls_used >= self.max_tool_calls:
            self.stop_reason = "tool-call budget reached"
        elif self.elapsed_seconds >= self.max_elapsed_seconds:
            self.stop_reason = "turn wall-time budget reached"
        return self.stop_reason

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self._clock() - self._started_at)

    def snapshot(self) -> TurnBudgetSnapshot:
        return TurnBudgetSnapshot(
            max_model_steps=self.max_model_steps,
            model_steps_used=self.model_steps_used,
            max_tool_calls=self.max_tool_calls,
            tool_calls_used=self.tool_calls_used,
            max_elapsed_seconds=self.max_elapsed_seconds,
            elapsed_seconds=self.elapsed_seconds,
            no_progress_streak=self.no_progress_streak,
            max_no_progress=self.max_no_progress,
            stop_reason=self.stop_reason,
        )
