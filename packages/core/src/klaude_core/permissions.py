"""Permission gate.

Every tool execution passes through here. Policies: ask | allow | deny.
The 'ask' path calls a callback injected by the client (CLI prompt today,
VS Code dialog later) — the engine itself never reads stdin, which is what
keeps it headless-ready.
"""

from __future__ import annotations

from collections.abc import Callable

AskCallback = Callable[[str, str], str]
# (tool_name, human_readable_detail) -> "y" | "n" | "a"  (yes / no / always)


class PermissionDenied(Exception):
    pass


class PermissionGate:
    def __init__(self, policies: dict[str, str], ask: AskCallback):
        self.policies = dict(policies)
        self._ask = ask

    def check(self, tool: str, detail: str) -> None:
        policy = self.policies.get(tool, "ask")
        if policy == "allow":
            return
        if policy == "deny":
            raise PermissionDenied(f"tool '{tool}' is denied by policy")
        answer = self._ask(tool, detail)
        if answer == "a":  # always allow for this session
            self.policies[tool] = "allow"
            return
        if answer != "y":
            raise PermissionDenied(f"user declined '{tool}'")
