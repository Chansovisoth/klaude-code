"""Safety-first contracts for bounded child-agent orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from typing import Any
from uuid import uuid4

from .capabilities import TurnScope


class SubagentRole(StrEnum):
    """Host-defined child roles; models cannot invent broader roles."""

    READ_RESEARCH = "read_research"
    TEST_DIAGNOSTIC = "test_diagnostic"


class SubagentStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ROLE_TOOLS: dict[SubagentRole, frozenset[str]] = {
    SubagentRole.READ_RESEARCH: frozenset(
        {
            "read_file",
            "list_dir",
            "grep",
            "workspace_info",
            "git_status",
            "git_diff",
            "web_search",
            "fetch_url",
            "http_probe",
            "code_search",
            "query_knowledge",
            "huggingface_search",
            "huggingface_details",
            "huggingface_readme",
            "current_time",
            "weather_lookup",
            "storage_usage",
        }
    ),
    # Shell remains excluded until a dedicated test sandbox can prove that a
    # command cannot mutate the workspace or host.
    SubagentRole.TEST_DIAGNOSTIC: frozenset(
        {
            "read_file",
            "list_dir",
            "grep",
            "workspace_info",
            "git_status",
            "git_diff",
            "query_knowledge",
        }
    ),
}


@dataclass(frozen=True)
class SubagentTask:
    """One bounded, public child task selected by the primary agent."""

    objective: str
    role: SubagentRole = SubagentRole.READ_RESEARCH
    context: str = ""
    requested_tools: tuple[str, ...] = ()
    task_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        objective = " ".join(self.objective.split())
        if not objective or len(objective) > 2_000:
            raise ValueError("subagent objective must contain 1-2,000 characters")
        if len(self.context) > 8_000:
            raise ValueError("subagent context must not exceed 8,000 characters")
        if not self.task_id or len(self.task_id) > 128:
            raise ValueError("subagent task_id must contain 1-128 characters")
        requested_tools = tuple(
            dict.fromkeys(str(name) for name in self.requested_tools if str(name))
        )
        if len(requested_tools) > 64 or any(len(name) > 128 for name in requested_tools):
            raise ValueError("subagent requested_tools exceeds its safe bounds")
        object.__setattr__(self, "objective", objective)
        object.__setattr__(self, "role", SubagentRole(self.role))
        object.__setattr__(self, "requested_tools", requested_tools)


@dataclass(frozen=True)
class SubagentBudget:
    """Parent-owned limits that children cannot enlarge."""

    max_children: int = 1
    max_steps_per_child: int = 6
    max_total_steps: int = 8
    max_tool_calls_per_child: int = 8
    max_total_tool_calls: int = 12
    max_tokens_per_child: int = 96_000
    max_total_tokens: int = 96_000
    max_result_characters: int = 8_000

    def bounded(self) -> SubagentBudget:
        children = max(1, min(8, int(self.max_children)))
        per_child = max(1, min(20, int(self.max_steps_per_child)))
        total = max(1, min(64, int(self.max_total_steps)))
        calls_per_child = max(1, min(64, int(self.max_tool_calls_per_child)))
        total_calls = max(1, min(128, int(self.max_total_tool_calls)))
        tokens_per_child = max(1, min(1_000_000, int(self.max_tokens_per_child)))
        total_tokens = max(1, min(2_000_000, int(self.max_total_tokens)))
        return SubagentBudget(
            max_children=children,
            max_steps_per_child=min(per_child, total),
            max_total_steps=total,
            max_tool_calls_per_child=min(calls_per_child, total_calls),
            max_total_tool_calls=total_calls,
            max_tokens_per_child=min(tokens_per_child, total_tokens),
            max_total_tokens=total_tokens,
            max_result_characters=max(512, min(32_000, int(self.max_result_characters))),
        )


@dataclass(frozen=True)
class SubagentAssignment:
    """The exact capability envelope supplied to one child worker."""

    task: SubagentTask
    callable_tools: tuple[str, ...]
    unavailable_tools: tuple[tuple[str, str], ...]
    max_steps: int
    max_tool_calls: int
    max_total_tokens: int


@dataclass(frozen=True)
class SubagentWorkerOutput:
    """Structured output returned by a child runtime adapter."""

    summary: str
    model_steps: int
    tool_calls: int = 0
    tools_used: tuple[str, ...] = ()
    input_tokens: int = 0
    output_tokens: int = 0
    unknown_token_requests: int = 0


@dataclass(frozen=True)
class SubagentResult:
    """Bounded public result safe for the primary agent and session UI."""

    task_id: str
    role: SubagentRole
    status: SubagentStatus
    summary: str
    callable_tools: tuple[str, ...]
    tools_used: tuple[str, ...]
    model_steps: int
    tool_calls: int
    error_category: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    unknown_token_requests: int = 0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["role"] = self.role.value
        value["status"] = self.status.value
        return value


@dataclass(frozen=True)
class SubagentEvent:
    """Public lifecycle event; never carries reasoning or provider secrets."""

    kind: str
    task_id: str
    role: SubagentRole
    status: SubagentStatus | None = None
    model_steps: int = 0
    tool_calls: int = 0
    tools_used: tuple[str, ...] = ()
    summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    unknown_token_requests: int = 0

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "kind": self.kind,
            "task_id": self.task_id,
            "role": self.role.value,
        }
        if self.status is not None:
            value["status"] = self.status.value
        if self.model_steps:
            value["model_steps"] = self.model_steps
        if self.tool_calls:
            value["tool_calls"] = self.tool_calls
        if self.tools_used:
            value["tools_used"] = list(self.tools_used)
        if self.summary:
            value["summary"] = self.summary[:4_000]
        if self.input_tokens:
            value["input_tokens"] = self.input_tokens
        if self.output_tokens:
            value["output_tokens"] = self.output_tokens
        if self.unknown_token_requests:
            value["unknown_token_requests"] = self.unknown_token_requests
        return value


SubagentWorker = Callable[[SubagentAssignment], SubagentWorkerOutput]
SubagentEventSink = Callable[[SubagentEvent], None]
CancellationCheck = Callable[[], bool]


class SubagentExecutionError(RuntimeError):
    """A child agent did not produce a coherent completed result."""

    def __init__(
        self,
        *,
        model_steps: int,
        tool_calls: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        unknown_token_requests: int = 0,
    ) -> None:
        super().__init__("child agent did not complete successfully")
        self.model_steps = max(0, int(model_steps))
        self.tool_calls = max(0, int(tool_calls))
        self.input_tokens = max(0, int(input_tokens))
        self.output_tokens = max(0, int(output_tokens))
        self.unknown_token_requests = max(0, int(unknown_token_requests))


def run_agent_assignment(parent: Any, assignment: SubagentAssignment) -> SubagentWorkerOutput:
    """Run one isolated child conversation on an independent provider runtime.

    The adapter deliberately receives no parent transcript. The bounded task
    objective and context are the only conversational handoff. Tool closures
    are reused only after the supervisor has intersected role, parent-turn, and
    permission boundaries.
    """
    from .agent import Agent
    from .permissions import PermissionGate

    runtime_factory = getattr(parent.runtime, "fork_for_child", None)
    if not callable(runtime_factory):
        raise RuntimeError("the active provider cannot create an isolated child runtime")
    child_runtime = runtime_factory()
    if child_runtime is parent.runtime:
        raise RuntimeError("the active provider returned a shared child runtime")

    child_tools = [
        parent.tools[name]
        for name in assignment.callable_tools
        if name in parent.tools
    ]
    child_gate = PermissionGate(
        {name: "allow" for name in assignment.callable_tools},
        lambda _tool, _detail: "n",
    )
    parent_prompt = str(parent.messages[0].get("content", "")) if parent.messages else ""
    child_prompt = (
        parent_prompt
        + "\n\n<subagent_contract>\n"
        + f"Role: {assignment.task.role.value}.\n"
        + "Complete only the bounded objective below. Work read-only and non-interactively. "
        + "Do not modify files, execute shell commands, mutate Git, delegate work, request "
        + "permission, or ask the user questions. Return concise findings with concrete public "
        + "evidence such as file paths, symbols, or source URLs. Do not expose private reasoning.\n"
        + f"Maximum model steps: {assignment.max_steps}.\n"
        + f"Maximum tool calls: {assignment.max_tool_calls}.\n"
        + f"Maximum reported provider tokens: {assignment.max_total_tokens}.\n"
        + "</subagent_contract>"
    )
    parent_selector = parent.tool_selector
    child_selector = (
        None
        if parent_selector is None
        else lambda _message, tools: parent_selector(assignment.task.objective, tools)
    )
    try:
        child = Agent(
            child_runtime,
            parent.model,
            child_tools,
            child_gate,
            child_prompt,
            max_steps=assignment.max_steps,
            max_tool_calls=assignment.max_tool_calls,
            max_total_tokens=assignment.max_total_tokens,
            max_code_continuations=0,
            max_code_repairs=0,
            tool_selector=child_selector,
            ollama_options=parent.ollama_options,
            ollama_think=parent.ollama_think,
            web_research_budget=parent.web_research_budget,
            model_info=parent.model_info,
        )
    except Exception:
        close = getattr(child_runtime, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        raise
    child.workspace = getattr(parent, "workspace", None)
    child.workdir = getattr(parent, "workdir", None)
    child.tool_config = getattr(parent, "tool_config", None)
    child.injected_instruction_paths = tuple(
        getattr(parent, "injected_instruction_paths", ())
    )
    child.injected_instructions_truncated = bool(
        getattr(parent, "injected_instructions_truncated", False)
    )
    parent.register_child_runtime(child_runtime)

    user_message = (
        "<subagent_task>\n"
        f"Role: {assignment.task.role.value}.\n"
        "Work read-only and non-interactively. Do not modify files, execute shell commands, "
        "mutate Git, delegate work, request permission, or ask the user questions. Return "
        "concise findings with concrete public evidence and no private reasoning.\n"
        f"Objective:\n{assignment.task.objective}"
    )
    if assignment.task.context:
        user_message += f"\n\nBounded context:\n{assignment.task.context}"
    user_message += "\n</subagent_task>"
    text_events: list[str] = []
    text_deltas: list[str] = []
    tools_used: list[str] = []
    tool_calls = 0
    completed = False
    errors: list[str] = []
    try:
        for event in child.run(user_message, scope=TurnScope.SUBAGENT):
            if event.kind == "text":
                text_events.append(str(event.payload.get("content", "")))
            elif event.kind == "text_delta":
                text_deltas.append(str(event.payload.get("content", "")))
            elif event.kind == "tool_start":
                tools_used.append(str(event.payload.get("tool", "")))
            elif event.kind == "tool_result":
                tool_calls += 1
            elif event.kind == "error":
                errors.append(str(event.payload.get("message", "")))
            elif event.kind == "done":
                completed = True
        if not completed or errors:
            usage = child.last_turn_budget
            raise SubagentExecutionError(
                model_steps=int(usage.get("model_steps_used", 0)),
                tool_calls=tool_calls,
                input_tokens=int(usage.get("input_tokens_used", 0)),
                output_tokens=int(usage.get("output_tokens_used", 0)),
                unknown_token_requests=int(usage.get("token_usage_unknown_requests", 0)),
            )
        summary = "\n\n".join(text_events).strip() or "".join(text_deltas).strip()
        usage = child.last_turn_budget
        return SubagentWorkerOutput(
            summary=summary,
            model_steps=int(usage.get("model_steps_used", 0)),
            tool_calls=tool_calls,
            tools_used=tuple(dict.fromkeys(tools_used)),
            input_tokens=int(usage.get("input_tokens_used", 0)),
            output_tokens=int(usage.get("output_tokens_used", 0)),
            unknown_token_requests=int(usage.get("token_usage_unknown_requests", 0)),
        )
    finally:
        parent.unregister_child_runtime(child_runtime)
        close = getattr(child_runtime, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                # Cleanup cannot replace an already-determined child outcome.
                pass


class SubagentSupervisor:
    """Prepare and run bounded read-only child tasks sequentially.

    Sequential execution remains intentional until aggregate budgets and event
    ordering are concurrency-safe. Each child already owns an independent
    provider stream and cancellation tracker.
    """

    def __init__(
        self,
        *,
        parent_callable_tools: Iterable[str],
        effective_permissions: Mapping[str, str],
        worker: SubagentWorker,
        process_grants: Iterable[str] = (),
        budget: SubagentBudget | None = None,
        cancelled: CancellationCheck | None = None,
        event_sink: SubagentEventSink | None = None,
    ) -> None:
        self.parent_callable_tools = frozenset(parent_callable_tools)
        self.effective_permissions = dict(effective_permissions)
        self.process_grants = frozenset(process_grants)
        self.worker = worker
        self.budget = (budget or SubagentBudget()).bounded()
        self.cancelled = cancelled or (lambda: False)
        self.event_sink = event_sink

    def prepare(
        self,
        task: SubagentTask,
        *,
        steps_left: int | None = None,
        tool_calls_left: int | None = None,
        tokens_left: int | None = None,
    ) -> SubagentAssignment:
        role_tools = _ROLE_TOOLS[task.role]
        requested = frozenset(task.requested_tools) if task.requested_tools else role_tools
        candidates = role_tools & requested & self.parent_callable_tools
        callable_tools = tuple(
            sorted(
                name
                for name in candidates
                if self.effective_permissions.get(name, "ask") == "allow"
                or (
                    self.effective_permissions.get(name, "ask") == "ask"
                    and name in self.process_grants
                )
            )
        )
        unavailable: dict[str, str] = {}
        for name in sorted(requested):
            if name not in role_tools:
                unavailable[name] = "not allowed for child role"
            elif name not in self.parent_callable_tools:
                unavailable[name] = "not callable by parent turn"
            elif name not in callable_tools:
                unavailable[name] = (
                    "denied by parent policy"
                    if self.effective_permissions.get(name, "ask") == "deny"
                    else "requires an interactive permission decision"
                )
        remaining = self.budget.max_total_steps if steps_left is None else max(0, steps_left)
        remaining_calls = (
            self.budget.max_total_tool_calls
            if tool_calls_left is None
            else max(0, tool_calls_left)
        )
        remaining_tokens = (
            self.budget.max_total_tokens if tokens_left is None else max(0, tokens_left)
        )
        return SubagentAssignment(
            task=task,
            callable_tools=callable_tools,
            unavailable_tools=tuple(unavailable.items()),
            max_steps=min(self.budget.max_steps_per_child, remaining),
            max_tool_calls=min(self.budget.max_tool_calls_per_child, remaining_calls),
            max_total_tokens=min(self.budget.max_tokens_per_child, remaining_tokens),
        )

    def run(self, tasks: Iterable[SubagentTask]) -> list[SubagentResult]:
        queued = list(tasks)
        if len(queued) > self.budget.max_children:
            raise ValueError(
                f"subagent request exceeds child limit ({len(queued)} > "
                f"{self.budget.max_children})"
            )
        if len({task.task_id for task in queued}) != len(queued):
            raise ValueError("subagent task IDs must be unique")

        results: list[SubagentResult] = []
        steps_used = 0
        tool_calls_used = 0
        tokens_used = 0
        for task in queued:
            was_cancelled = self.cancelled()
            budget_exhausted = (
                steps_used >= self.budget.max_total_steps
                or tool_calls_used >= self.budget.max_total_tool_calls
                or tokens_used >= self.budget.max_total_tokens
            )
            if was_cancelled or budget_exhausted:
                result = self._terminal_result(
                    task,
                    SubagentStatus.CANCELLED if was_cancelled else SubagentStatus.FAILED,
                    error_category="cancelled" if was_cancelled else "budget_exhausted",
                )
                results.append(result)
                self._emit(self._finished_event(result))
                continue
            assignment = self.prepare(
                task,
                steps_left=self.budget.max_total_steps - steps_used,
                tool_calls_left=self.budget.max_total_tool_calls - tool_calls_used,
                tokens_left=self.budget.max_total_tokens - tokens_used,
            )
            self._emit(SubagentEvent("subagent_started", task.task_id, task.role))
            try:
                output = self.worker(assignment)
                model_steps = max(0, int(output.model_steps))
                tool_calls = max(0, int(output.tool_calls))
                input_tokens = max(0, int(output.input_tokens))
                output_tokens = max(0, int(output.output_tokens))
                unknown_token_requests = max(0, int(output.unknown_token_requests))
                child_tokens = input_tokens + output_tokens
                tools_used = tuple(dict.fromkeys(output.tools_used))
                invalid_tools = set(tools_used) - set(assignment.callable_tools)
                if (
                    model_steps > assignment.max_steps
                    or tool_calls > assignment.max_tool_calls
                    or child_tokens > assignment.max_total_tokens
                    or invalid_tools
                ):
                    result = self._terminal_result(
                        task,
                        SubagentStatus.FAILED,
                        assignment=assignment,
                        model_steps=model_steps,
                        tool_calls=tool_calls,
                        tools_used=tools_used,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        unknown_token_requests=unknown_token_requests,
                        error_category=(
                            "budget_violation"
                            if model_steps > assignment.max_steps
                            or tool_calls > assignment.max_tool_calls
                            or child_tokens > assignment.max_total_tokens
                            else "capability_violation"
                        ),
                    )
                elif self.cancelled():
                    result = self._terminal_result(
                        task,
                        SubagentStatus.CANCELLED,
                        assignment=assignment,
                        model_steps=model_steps,
                        tool_calls=tool_calls,
                        tools_used=tools_used,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        unknown_token_requests=unknown_token_requests,
                    )
                else:
                    result = SubagentResult(
                        task_id=task.task_id,
                        role=task.role,
                        status=SubagentStatus.COMPLETED,
                        summary=str(output.summary)[: self.budget.max_result_characters],
                        callable_tools=assignment.callable_tools,
                        tools_used=tools_used,
                        model_steps=model_steps,
                        tool_calls=tool_calls,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        unknown_token_requests=unknown_token_requests,
                    )
                steps_used += min(model_steps, assignment.max_steps)
                tool_calls_used += min(tool_calls, assignment.max_tool_calls)
                tokens_used += min(child_tokens, assignment.max_total_tokens)
            except Exception as exc:
                model_steps = max(0, int(getattr(exc, "model_steps", 0)))
                tool_calls = max(0, int(getattr(exc, "tool_calls", 0)))
                input_tokens = max(0, int(getattr(exc, "input_tokens", 0)))
                output_tokens = max(0, int(getattr(exc, "output_tokens", 0)))
                unknown_token_requests = max(
                    0,
                    int(getattr(exc, "unknown_token_requests", 0)),
                )
                steps_used += min(model_steps, assignment.max_steps)
                tool_calls_used += min(tool_calls, assignment.max_tool_calls)
                tokens_used += min(
                    input_tokens + output_tokens,
                    assignment.max_total_tokens,
                )
                was_cancelled = self.cancelled()
                result = self._terminal_result(
                    task,
                    SubagentStatus.CANCELLED if was_cancelled else SubagentStatus.FAILED,
                    assignment=assignment,
                    model_steps=model_steps,
                    tool_calls=tool_calls,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    unknown_token_requests=unknown_token_requests,
                    error_category="cancelled" if was_cancelled else type(exc).__name__,
                )
            results.append(result)
            self._emit(self._finished_event(result))
        return results

    def _terminal_result(
        self,
        task: SubagentTask,
        status: SubagentStatus,
        *,
        assignment: SubagentAssignment | None = None,
        model_steps: int = 0,
        tool_calls: int = 0,
        tools_used: tuple[str, ...] = (),
        input_tokens: int = 0,
        output_tokens: int = 0,
        unknown_token_requests: int = 0,
        error_category: str = "",
    ) -> SubagentResult:
        return SubagentResult(
            task_id=task.task_id,
            role=task.role,
            status=status,
            summary="",
            callable_tools=assignment.callable_tools if assignment else (),
            tools_used=tools_used,
            model_steps=model_steps,
            tool_calls=tool_calls,
            error_category=error_category,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            unknown_token_requests=unknown_token_requests,
        )

    def _emit(self, event: SubagentEvent) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(event)
        except Exception:
            # UI/session telemetry must never alter child execution.
            pass

    @staticmethod
    def _finished_event(result: SubagentResult) -> SubagentEvent:
        return SubagentEvent(
            "subagent_finished",
            result.task_id,
            result.role,
            result.status,
            model_steps=result.model_steps,
            tool_calls=result.tool_calls,
            tools_used=result.tools_used,
            summary=result.summary,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            unknown_token_requests=result.unknown_token_requests,
        )


def supervise_agent_tasks(
    parent: Any,
    tasks: Iterable[SubagentTask],
    *,
    budget: SubagentBudget | None = None,
    cancelled: CancellationCheck | None = None,
    event_sink: SubagentEventSink | None = None,
) -> list[SubagentResult]:
    """Run isolated children and charge their completed usage to the parent turn."""
    queued = list(tasks)
    configured_budget = (budget or SubagentBudget()).bounded()
    if len(queued) > configured_budget.max_children:
        raise ValueError(
            f"subagent request exceeds child limit ({len(queued)} > "
            f"{configured_budget.max_children})"
        )
    if len({task.task_id for task in queued}) != len(queued):
        raise ValueError("subagent task IDs must be unique")
    governor = getattr(parent, "active_turn_governor", None)
    if governor is not None:
        parent_steps_left = max(0, governor.max_model_steps - governor.model_steps_used)
        parent_tool_calls_left = max(
            0,
            governor.max_tool_calls - governor.tool_calls_used,
        )
        # The parent loop charges the delegate_task invocation after this
        # helper returns. Preserve one slot for that enclosing tool result.
        child_tool_calls_left = max(0, parent_tool_calls_left - 1)
        parent_tokens_left = governor.snapshot().tokens_left
        if (
            parent_steps_left == 0
            or child_tool_calls_left == 0
            or parent_tokens_left == 0
        ):
            results = [
                SubagentResult(
                    task_id=task.task_id,
                    role=task.role,
                    status=SubagentStatus.FAILED,
                    summary="",
                    callable_tools=(),
                    tools_used=(),
                    model_steps=0,
                    tool_calls=0,
                    error_category="parent_budget_exhausted",
                )
                for task in queued
            ]
            if event_sink is not None:
                for result in results:
                    try:
                        event_sink(SubagentSupervisor._finished_event(result))
                    except Exception:
                        # Session/UI telemetry cannot change the terminal result.
                        pass
            return results
        configured_budget = replace(
            configured_budget,
            max_steps_per_child=min(
                configured_budget.max_steps_per_child,
                parent_steps_left,
            ),
            max_total_steps=min(configured_budget.max_total_steps, parent_steps_left),
            max_tool_calls_per_child=min(
                configured_budget.max_tool_calls_per_child,
                child_tool_calls_left,
            ),
            max_total_tool_calls=min(
                configured_budget.max_total_tool_calls,
                child_tool_calls_left,
            ),
            **(
                {
                    "max_tokens_per_child": min(
                        configured_budget.max_tokens_per_child,
                        parent_tokens_left,
                    ),
                    "max_total_tokens": min(
                        configured_budget.max_total_tokens,
                        parent_tokens_left,
                    ),
                }
                if parent_tokens_left is not None
                else {}
            ),
        )
    snapshot = getattr(parent, "last_turn_capabilities", {})
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    callable_tools = snapshot.get("callable_tools", ())
    if not isinstance(callable_tools, (list, tuple, set, frozenset)):
        callable_tools = ()
    supervisor = SubagentSupervisor(
        parent_callable_tools=(str(name) for name in callable_tools),
        effective_permissions=getattr(parent.gate, "policies", {}),
        process_grants=getattr(parent.gate, "process_grants", ()),
        worker=lambda assignment: run_agent_assignment(parent, assignment),
        budget=configured_budget,
        cancelled=cancelled,
        event_sink=event_sink,
    )
    results = supervisor.run(queued)
    if governor is not None:
        governor.charge_delegated_usage(
            model_steps=sum(result.model_steps for result in results),
            tool_calls=sum(result.tool_calls for result in results),
            input_tokens=sum(result.input_tokens for result in results),
            output_tokens=sum(result.output_tokens for result in results),
            unknown_token_requests=sum(
                result.unknown_token_requests for result in results
            ),
        )
        parent.last_turn_budget = governor.snapshot().to_dict()
    return results
