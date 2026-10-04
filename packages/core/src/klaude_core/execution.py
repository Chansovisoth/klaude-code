"""Progress-aware, provider-independent execution budgets for one agent turn."""

from __future__ import annotations

import re
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
NO_EVIDENCE_RE = re.compile(
    r"(?i)\b(?:no (?:relevant |matching |usable )?(?:results?|documents?|sources?|"
    r"knowledge)|nothing (?:found|relevant)|could(?: not|n't) find|not found)\b"
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
    max_total_tokens: int | None = None
    input_tokens_used: int = 0
    output_tokens_used: int = 0
    token_usage_unknown_requests: int = 0

    @property
    def model_steps_left(self) -> int:
        return max(0, self.max_model_steps - self.model_steps_used)

    @property
    def tool_calls_left(self) -> int:
        return max(0, self.max_tool_calls - self.tool_calls_used)

    @property
    def total_tokens_used(self) -> int:
        return self.input_tokens_used + self.output_tokens_used

    @property
    def tokens_left(self) -> int | None:
        if self.max_total_tokens is None:
            return None
        return max(0, self.max_total_tokens - self.total_tokens_used)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["model_steps_left"] = self.model_steps_left
        value["tool_calls_left"] = self.tool_calls_left
        value["total_tokens_used"] = self.total_tokens_used
        value["tokens_left"] = self.tokens_left
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
        max_total_tokens: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_model_steps = max(1, max_model_steps)
        self.max_tool_calls = max(1, max_tool_calls or max(4, self.max_model_steps * 2))
        self.max_elapsed_seconds = max(1.0, max_elapsed_seconds)
        self.max_no_progress = max(1, max_no_progress)
        self.max_total_tokens = (
            max(1, int(max_total_tokens)) if max_total_tokens is not None else None
        )
        self._clock = clock
        self._started_at = clock()
        self.model_steps_used = 0
        self.tool_calls_used = 0
        self.no_progress_streak = 0
        self.input_tokens_used = 0
        self.output_tokens_used = 0
        self.token_usage_unknown_requests = 0
        self.stop_reason = ""
        self._successful_outcomes: set[str] = set()
        self._progress_group: int | None = None
        self._group_failed = False
        self._group_succeeded = False

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
        *,
        progress_group: int | None = None,
    ) -> str:
        """Record a completed tool boundary and return a reason to stop tools."""
        self.tool_calls_used += 1
        normalized = " ".join(result.casefold().split())[:2_000]
        failed = normalized.startswith(FAILED_RESULT_PREFIXES)
        no_evidence = (
            metadata is not None
            and (
                metadata.get("found") is False
                or metadata.get("status") in {"failed", "skipped", "no_results"}
                or (metadata.get("result_count") == 0 and tool in {"web_search", "query_knowledge"})
                or (isinstance(metadata.get("edit"), dict)
                    and metadata["edit"].get("changed") is False)
            )
        ) or bool(NO_EVIDENCE_RE.match(normalized))
        outcome = f"{tool}:{normalized}"
        duplicate_outcome = outcome in self._successful_outcomes
        executed = (metadata or {}).get("executed") is not False

        if progress_group != self._progress_group:
            self._progress_group = progress_group
            self._group_failed = False
            self._group_succeeded = False
        if failed or no_evidence or duplicate_outcome or not executed:
            # Parallel calls from one model response are one recovery attempt.
            # A batch of bad paths must leave room for directory discovery on
            # the next request. Every call still consumes the hard call budget.
            if progress_group is None or not (self._group_failed or self._group_succeeded):
                self.no_progress_streak += 1
            self._group_failed = True
        else:
            self.no_progress_streak = 0
            self._successful_outcomes.add(outcome)
            self._group_succeeded = True

        if self.tool_calls_used >= self.max_tool_calls:
            self.stop_reason = "tool-call budget reached"
        elif self.no_progress_streak >= self.max_no_progress:
            self.stop_reason = "tool activity stopped making progress"
        elif self.elapsed_seconds >= self.max_elapsed_seconds:
            self.stop_reason = "turn wall-time budget reached"
        return self.stop_reason

    def forget_tool_result(self, tool: str, result: str) -> None:
        """A result omitted from working context may need a real fresh read."""
        normalized = " ".join(result.casefold().split())[:2_000]
        self._successful_outcomes.discard(f"{tool}:{normalized}")

    def charge_delegated_usage(
        self,
        *,
        model_steps: int,
        tool_calls: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        unknown_token_requests: int = 0,
    ) -> str:
        """Charge completed child work to this turn's non-expandable budget."""
        delegated_steps = max(0, int(model_steps))
        delegated_calls = max(0, int(tool_calls))
        self.model_steps_used += delegated_steps
        self.tool_calls_used += delegated_calls
        self.input_tokens_used += max(0, int(input_tokens))
        self.output_tokens_used += max(0, int(output_tokens))
        self.token_usage_unknown_requests += max(0, int(unknown_token_requests))
        if self.model_steps_used >= self.max_model_steps:
            self.stop_reason = "model/tool step budget reached"
        elif self.tool_calls_used >= self.max_tool_calls:
            self.stop_reason = "tool-call budget reached"
        elif (
            self.max_total_tokens is not None
            and self.input_tokens_used + self.output_tokens_used >= self.max_total_tokens
        ):
            self.stop_reason = "token budget reached"
        elif self.elapsed_seconds >= self.max_elapsed_seconds:
            self.stop_reason = "turn wall-time budget reached"
        return self.stop_reason

    def observe_model_usage(self, usage: tuple[int, int] | None) -> str:
        """Charge one provider request using exact counters when available."""
        if usage is None:
            self.token_usage_unknown_requests += 1
            return self.stop_reason
        input_tokens, output_tokens = usage
        self.input_tokens_used += max(0, int(input_tokens))
        self.output_tokens_used += max(0, int(output_tokens))
        if (
            self.max_total_tokens is not None
            and self.input_tokens_used + self.output_tokens_used >= self.max_total_tokens
        ):
            self.stop_reason = "token budget reached"
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
            max_total_tokens=self.max_total_tokens,
            input_tokens_used=self.input_tokens_used,
            output_tokens_used=self.output_tokens_used,
            token_usage_unknown_requests=self.token_usage_unknown_requests,
        )
