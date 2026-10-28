"""Immutable, auditable capability state for one model request."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .execution import TurnBudgetSnapshot


def _names(names: Iterable[str]) -> str:
    values = list(names)
    shown = []
    size = 0
    for value in values[:32]:
        if size + len(value) > 2400:
            break
        shown.append(value)
        size += len(value) + 2
    extra = len(values) - len(shown)
    return (", ".join(shown) or "(none)") + (f" (+{extra} omitted)" if extra else "")


def _reasons(reasons: Mapping[str, str]) -> str:
    shown = dict(list(reasons.items())[:32])
    return json.dumps(shown, sort_keys=True) + (
        f"; {len(reasons) - len(shown)} additional restrictions omitted"
        if len(reasons) > len(shown) else ""
    )


class TurnScope(StrEnum):
    """Host-selected purpose and safety envelope for one agent turn."""

    STANDARD = "standard"
    PLAN = "plan"
    REVIEW = "review"
    INIT = "init"
    EVALUATION = "evaluation"
    SUBAGENT = "subagent"
    RESEARCH = "research"


@dataclass(frozen=True)
class TurnCapabilities:
    """The exact capability contract supplied with one model request.

    Tuples keep the snapshot immutable after construction. The model prompt,
    host status UI, and durable completion metadata all serialize this same
    object instead of independently reconstructing what a turn could do.
    """

    globally_enabled_tools: tuple[str, ...]
    callable_tools: tuple[str, ...]
    unavailable_tools: tuple[tuple[str, str], ...]
    effective_permissions: tuple[tuple[str, str], ...]
    hard_constraints: tuple[str, ...]
    provider_backend: str
    provider_model: str
    provider_supports_tools: bool
    provider_context_window: int | None
    provider_effort_levels: tuple[str, ...]
    injected_instructions: tuple[str, ...]
    instructions_truncated: bool
    plan_mode: bool
    workspace_write_enabled: bool | None
    budget: TurnBudgetSnapshot
    scope: TurnScope = TurnScope.STANDARD

    @classmethod
    def create(
        cls,
        *,
        globally_enabled_tools: Iterable[str],
        callable_tools: Iterable[str],
        unavailable_tools: Mapping[str, str],
        effective_permissions: Mapping[str, str],
        hard_constraints: Iterable[str],
        provider_backend: str,
        provider_model: str,
        provider_supports_tools: bool,
        provider_context_window: int | None,
        provider_effort_levels: Iterable[str],
        injected_instructions: Iterable[str],
        instructions_truncated: bool,
        plan_mode: bool,
        workspace_write_enabled: bool | None,
        budget: TurnBudgetSnapshot,
        scope: TurnScope | str = TurnScope.STANDARD,
    ) -> TurnCapabilities:
        return cls(
            globally_enabled_tools=tuple(sorted(set(globally_enabled_tools))),
            callable_tools=tuple(sorted(set(callable_tools))),
            unavailable_tools=tuple(sorted(unavailable_tools.items())),
            effective_permissions=tuple(sorted(effective_permissions.items())),
            hard_constraints=tuple(dict.fromkeys(hard_constraints)),
            provider_backend=provider_backend,
            provider_model=provider_model,
            provider_supports_tools=provider_supports_tools,
            provider_context_window=provider_context_window,
            provider_effort_levels=tuple(provider_effort_levels),
            injected_instructions=tuple(injected_instructions),
            instructions_truncated=instructions_truncated,
            plan_mode=plan_mode,
            workspace_write_enabled=workspace_write_enabled,
            budget=budget,
            scope=TurnScope(scope),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "globally_enabled_tools": list(self.globally_enabled_tools),
            "callable_tools": list(self.callable_tools),
            "unavailable_tools": dict(self.unavailable_tools),
            "effective_permissions": dict(self.effective_permissions),
            "hard_constraints": list(self.hard_constraints),
            "provider": {
                "backend": self.provider_backend,
                "model": self.provider_model,
                "supports_tools": self.provider_supports_tools,
                "context_window": self.provider_context_window,
                "effort_levels": list(self.provider_effort_levels),
            },
            "injected_instructions": list(self.injected_instructions),
            "instructions_truncated": self.instructions_truncated,
            "plan_mode": self.plan_mode,
            "workspace_write_enabled": self.workspace_write_enabled,
            "budget": self.budget.to_dict(),
            "scope": self.scope.value,
        }

    def render_for_model(self) -> str:
        unavailable = dict(self.unavailable_tools)
        permissions = dict(self.effective_permissions)
        policy_groups = {
            policy: sorted(name for name, value in permissions.items() if value == policy)
            for policy in ("allow", "ask", "deny")
        }
        constraints = " ".join(self.hard_constraints)
        instructions = ", ".join(self.injected_instructions) or "(none)"
        token_budget = (
            f"{self.budget.total_tokens_used:,}/{self.budget.max_total_tokens:,} "
            "reported provider tokens used; "
            if self.budget.max_total_tokens is not None
            else ""
        )
        unknown_usage = (
            f"{self.budget.token_usage_unknown_requests} "
            f"{'request' if self.budget.token_usage_unknown_requests == 1 else 'requests'} "
            "lacked exact token usage; "
            if self.budget.token_usage_unknown_requests
            else ""
        )
        return (
            "<turn_capabilities>\n"
            f"Turn scope: {self.scope.value}.\n"
            f"Provider: {self.provider_backend}/{self.provider_model}; "
            f"tools={'yes' if self.provider_supports_tools else 'no'}; "
            f"context={self.provider_context_window or 'unknown'}; "
            f"effort={', '.join(self.provider_effort_levels) or '(none)'}.\n"
            f"Injected repository instructions: {instructions}"
            f"{' (bounded)' if self.instructions_truncated else ''}.\n"
            "Globally enabled registry: "
            f"{_names(self.globally_enabled_tools)}.\n"
            f"Callable this request: {_names(self.callable_tools)}.\n"
            f"Not callable this request: {_names(unavailable)}.\n"
            f"Reasons: {_reasons(unavailable)}\n"
            "The supplied schemas are authoritative for calls. A tool marked 'turn routing' "
            "is enabled in Klaude but omitted from this request; do not describe it as "
            "unavailable in Klaude or claim to have used it. Other omissions may reflect "
            "settings, plan mode, permissions, hard safety constraints, or exhausted budgets. "
            "Effective permission policy for registered "
            "tools: "
            + "; ".join(
                f"{policy.upper()}={_names(names)}"
                for policy, names in policy_groups.items()
            )
            + ". ALLOW executes without a prompt; ASK invokes the host permission UI; "
            "DENY is unavailable and cannot execute. These are the current live settings "
            "for this turn. "
            f"Execution budget: {self.budget.model_steps_used}/"
            f"{self.budget.max_model_steps} model steps and "
            f"{self.budget.tool_calls_used}/{self.budget.max_tool_calls} tool calls used; "
            f"{token_budget}{unknown_usage}"
            "one tool-free finalization request is reserved. "
            f"Hard constraints: {constraints or '(none)'}.\n"
            "</turn_capabilities>"
        )

    def render_compact_for_model(self) -> str:
        """Small capability statement for direct, schema-free requests."""
        unavailable = dict(self.unavailable_tools)
        return (
            "<turn_capabilities>"
            f"Turn scope: {self.scope.value}. "
            f"Provider: {self.provider_backend}/{self.provider_model}. "
            f"Callable this request: {_names(self.callable_tools)}. "
            f"Not callable this request: {_names(unavailable)}. "
            "Only supplied schemas are callable; turn routing is not global unavailability."
            "</turn_capabilities>"
        )

    def render_execution_for_model(self, *, include_registry: bool = True) -> str:
        """Request-relevant policies; the complete snapshot remains auditable."""
        policies = dict(self.effective_permissions)
        unavailable = {
            name: reason for name, reason in self.unavailable_tools
            if reason != "turn routing"
        }
        registry = (
            f"Globally enabled registry: {_names(self.globally_enabled_tools)}.\n"
            if include_registry else
            f"Enabled tools in registry: {len(self.globally_enabled_tools)}. "
            "Use discover_tools to find tools omitted by routing.\n"
        )
        return (
            "<turn_capabilities>\n"
            f"Turn scope: {self.scope.value}. Provider: {self.provider_backend}/"
            f"{self.provider_model}; context={self.provider_context_window}.\n"
            f"{registry}"
            f"Callable this request: {_names(self.callable_tools)}.\n"
            "Only supplied schemas are callable. Other enabled tools are omitted by "
            "turn routing, not globally unavailable. "
            f"Restrictions: {_reasons(unavailable)}.\n"
            + "; ".join(
                f"{policy.upper()}=" + _names(
                    n for n in self.callable_tools if policies.get(n) == policy
                ) for policy in ("allow", "ask", "deny")
            )
            + ". ASK invokes the host approval UI. Hard constraints: "
            + " ".join(self.hard_constraints)
            + f"\nBudget: {self.budget.model_steps_used}/{self.budget.max_model_steps} "
            f"model steps; {self.budget.tool_calls_used}/{self.budget.max_tool_calls} "
            "tool calls.\n</turn_capabilities>"
        )
