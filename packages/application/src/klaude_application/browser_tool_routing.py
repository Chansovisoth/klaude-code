"""Keep external schemas lazy so MCP inventories cannot evict chat history."""

import json
import re

from klaude_core import Tool, tool_discovery
from klaude_core.intent import explicit_only_tool_names, explicitly_disallows_tools


def select_browser_tools(text: str, tools: dict[str, Tool]) -> list[str]:
    if explicitly_disallows_tools(text):
        return []
    explicit = explicit_only_tool_names(text, set(tools))
    if explicit is not None:
        return list(explicit)
    # Built-in browser tools remain available. Large external schemas are
    # searched on demand, then admitted through the Agent's existing budget,
    # live-definition, scope and permission checks. Never execute from discovery.
    selected = [name for name in tools if not name.startswith("mcp__")]
    # Preserve explicit calls to a named server/tool while bounding the initial
    # schema cost. The rest remain discoverable, never executed by this route.
    lowered = " ".join(re.findall(r"\w+", text.casefold().replace("_", " ")))
    named = []
    for name, tool in tools.items():
        if not name.startswith("mcp__"):
            continue
        parts = name.split("__", 2)
        server = " ".join(re.findall(r"\w+", parts[1].casefold().replace("_", " ")))
        if server and " " + server + " " in " " + lowered + " ":
            named.append((name, tool.description))
    used = 0
    for name, _ in tool_discovery.matches(text, named):
        size = len(json.dumps(tools[name].schema()))
        if used + size <= 8000:
            selected.append(name)
            used += size
    return selected


def configure_browser_routing(agent) -> None:
    agent.tool_selector = select_browser_tools
    agent.compact_capability_context = True
    agent.tools["discover_tools"] = Tool(
        "discover_tools", tool_discovery.DESCRIPTION, tool_discovery.PARAMETERS,
        agent.discover_tools,
    )
    agent.gate.policies["discover_tools"] = "allow"
