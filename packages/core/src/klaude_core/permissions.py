"""Permission gate.

Every tool execution passes through here. Policies: ask | allow | deny.
The 'ask' path calls a callback injected by the client (CLI prompt today,
VS Code dialog later) — the engine itself never reads stdin, which is what
keeps it headless-ready.
"""

from __future__ import annotations

from collections.abc import Callable

AskCallback = Callable[[str, str], str]
DecisionObserver = Callable[[str, str], None]
# (tool_name, human_readable_detail) -> "y" | "n" | "a"  (yes / no / always)


class PermissionDenied(Exception):
    pass


class PermissionGate:
    def __init__(self, policies: dict[str, str], ask: AskCallback):
        self.policies = dict(policies)
        self.process_grants: set[str] = set()
        self._ask = ask
        self.decision_observer: DecisionObserver | None = None

    def set_ask_callback(self, ask: AskCallback) -> None:
        """Replace the client prompt when the active UI surface changes."""
        self._ask = ask

    def set_decision_observer(self, observer: DecisionObserver | None) -> None:
        """Observe prompted decisions without receiving potentially sensitive detail."""
        self.decision_observer = observer

    def check(self, tool: str, detail: str) -> None:
        policy = self.policies.get(tool, "ask")
        if policy == "allow":
            return
        if policy == "deny":
            raise PermissionDenied(f"tool '{tool}' is denied by policy")
        if tool in self.process_grants:
            return
        answer = self._ask(tool, detail)
        if self.decision_observer is not None:
            try:
                self.decision_observer(tool, answer)
            except Exception:
                # Telemetry and evaluation observers must never alter policy.
                pass
        if answer == "a":  # allow until this process exits; never save as a preference
            self.process_grants.add(tool)
            return
        if answer != "y":
            raise PermissionDenied(f"user declined '{tool}'")
