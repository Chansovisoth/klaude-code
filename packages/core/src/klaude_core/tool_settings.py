"""Built-in tool presentation metadata and registry-scoped availability.

Classification never registers tools or grants permissions. External MCP tools
retain their own server owner; inventory always comes from the live registry.
"""

from collections.abc import Iterable, Mapping
from typing import Any

BUILTIN_TOOL_GROUPS = (
    (
        "WORKSPACE",
        (
            ("read_file", "Read file"),
            ("list_dir", "List directory"),
            ("grep", "Search files"),
            ("workspace_info", "Workspace info"),
            ("storage_usage", "OS storage usage"),
            ("write_file", "Write file"),
            ("edit_file", "Edit file"),
            ("run_shell", "Run shell"),
        ),
    ),
    (
        "GIT",
        (
            ("git_status", "Status"),
            ("git_diff", "Diff"),
            ("git_commit", "Commit"),
        ),
    ),
    (
        "WEB & RESEARCH",
        (
            ("web_search", "Web search"),
            ("fetch_url", "Fetch URL"),
            ("http_probe", "HTTP probe"),
            ("code_search", "Code search"),
            ("crawl_site", "Crawl site"),
            ("learn_source", "Learn source"),
            ("weather_lookup", "Weather lookup"),
            ("current_time", "Current time"),
            ("huggingface_search", "Hugging Face search"),
            ("huggingface_details", "Hugging Face details"),
            ("huggingface_readme", "Hugging Face README"),
        ),
    ),
    (
        "KNOWLEDGE & SESSIONS",
        (
            ("query_knowledge", "Query knowledge"),
            ("read_skill", "Read skill"),
            ("search_sessions", "Search sessions"),
            ("list_recent_sessions", "List recent sessions"),
            ("remember_fact", "Remember fact"),
            ("list_commands", "List commands"),
        ),
    ),
    (
        "USER INTERACTION",
        (("request_user_input", "Request user input"),),
    ),
    (
        "ORCHESTRATION",
        (("delegate_task", "Delegate read-only task"),),
    ),
)

BUILTIN_TOOL_LABELS = {
    name: label for _group, tools in BUILTIN_TOOL_GROUPS for name, label in tools
}


def builtin_names(names: Iterable[str]) -> set[str]:
    return {name for name in names if not name.startswith("mcp__")}


def availability_values(raw: Any, names: Iterable[str]) -> dict[str, bool]:
    values = raw if isinstance(raw, dict) else {}
    return {name: values.get(name) is not False for name in builtin_names(names)}


def tool_groups(registry: Mapping[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    remaining = builtin_names(registry)
    groups = []
    for label, tools in BUILTIN_TOOL_GROUPS:
        names = tuple(name for name, _label in tools if name in remaining)
        if names:
            groups.append((label, names))
            remaining.difference_update(names)
    if remaining:
        groups.append(("OTHER", tuple(sorted(remaining))))
    return groups
