"""Immutable, auditable capability state for one model request."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .execution import TurnBudgetSnapshot


class TurnScope(StrEnum):
    """Host-selected purpose and safety envelope for one agent turn."""

    STANDARD = "standard"
    PLAN = "plan"
    REVIEW = "review"
    INIT = "init"
    EVALUATION = "evaluation"
    SUBAGENT = "subagent"


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
            f"{', '.join(self.globally_enabled_tools) or '(none)'}.\n"
            f"Callable this request: {', '.join(self.callable_tools) or '(none)'}.\n"
            f"Unavailable this request: {', '.join(unavailable) or '(none)'}.\n"
            f"Reasons: {json.dumps(unavailable, sort_keys=True)}\n"
            "The global registry is an inventory, not permission to call omitted tools. "
            "Omissions may reflect routing, settings, plan mode, permissions, hard safety "
            "constraints, or exhausted budgets. Effective permission policy for registered "
            "tools: "
            + "; ".join(
                f"{policy.upper()}={', '.join(names) or '(none)'}"
                for policy, names in policy_groups.items()
            )
            + ". ALLOW executes without a prompt; ASK invokes the host permission UI; "
            "DENY is unavailable and cannot execute. These are the current live settings "
            "for this turn. "
            f"Execution budget: {self.budget.model_steps_used}/"
            f"{self.budget.max_model_steps} model steps and "
            f"{self.budget.tool_calls_used}/{self.budget.max_tool_calls} tool calls used; "
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
            f"Callable this request: {', '.join(self.callable_tools) or '(none)'}. "
            f"Unavailable this request: {', '.join(unavailable) or '(none)'}. "
            "Only supplied schemas are callable."
            "</turn_capabilities>"
        )
