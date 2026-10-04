"""Select policy modules without changing the canonical session prompt."""

from __future__ import annotations

import re
from collections.abc import Iterable


def select_request_prompt(
    prompt: str, callable_tools: Iterable[str], *, workspace_execution: bool = False,
) -> str:
    names = set(callable_tools)

    def tool_policy(match: re.Match[str]) -> str:
        required = match.group(1).split(",")
        applies = any(
            tool in names or (tool == "mcp__" and any(n.startswith(tool) for n in names))
            for tool in required
        )
        return match.group(2) if applies else ""

    prompt = re.sub(
        r'<tool_policy tools="([\w,]+)">\n(.*?)</tool_policy>',
        tool_policy, prompt, flags=re.DOTALL,
    )
    for tag, include in (
        ("web_research_policy", any(n in names for n in (
            "web_search", "fetch_url", "http_probe", "code_search", "learn_source",
        )) or any(n.startswith("mcp__") for n in names)),
        ("standalone_code_policy", not workspace_execution),
        ("configuration_detail", not workspace_execution),
        ("runtime_policy", not workspace_execution),
    ):
        prompt = re.sub(
            rf"<{tag}>\n(.*?)</{tag}>",
            r"\1" if include else "", prompt, flags=re.DOTALL,
        )
    return re.sub(r"\n{3,}", "\n\n", prompt).strip()
