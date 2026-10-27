"""Allowlisted browser settings backed by the shared field-level settings writer."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from klaude_core.agent_settings import EXECUTION_LIMITS, execution_defaults
from klaude_core.config import Config
from klaude_core.fetch_settings import exa_fallback, fetch_provider
from klaude_core.mcp_client import MCPRegistry, MCPServerConfig, namespaced_tool_name
from klaude_core.research import LIMITS as RESEARCH_LIMITS
from klaude_core.research import read_research_defaults, research_defaults, save_research_defaults
from klaude_core.search_settings import PROVIDERS, primary_provider, service_url
from klaude_core.settings_store import MISSING, read_settings, settings_lock, update_settings
from klaude_core.time_settings import AUTOMATIC_TIMEZONE, timezone_names, validate_timezone

from .mcp_inventory import definition_digest

TOOLS = {
    "read_file": "Read files", "list_dir": "List folders", "workspace_info": "Workspace info",
    "grep": "Search workspace", "git_status": "Git status", "git_diff": "Git diff",
    "query_knowledge": "Search Knowledge", "read_skill": "Read Skills",
    "web_search": "Web search", "fetch_url": "Read web pages", "http_probe": "HTTP diagnostics",
    "current_time": "Current date and time",
}
EXECUTION = {"max_steps": "Steps per turn", "max_tool_calls": "Tool calls (0 = Auto)",
             "max_total_tokens": "Token budget (0 = no cap)"}
SEARCH = {"provider": "Search provider", "results": "Search results",
          "tavily_depth": "Tavily search depth", "searxng_url": "SearXNG URL"}
FETCH = {"provider": "Page reader", "exa_fallback": "Exa fallback",
         "crawl4ai_enabled": "Crawl4AI", "exa_enabled": "Exa page reader",
         "crawl4ai_url": "Crawl4AI URL"}
RESEARCH = {"provider": "Research search provider", "output_tokens": "Report output tokens",
            "extract_timeout": "Source extraction timeout (seconds)",
            "parallel": "Parallel source reads", "timeout": "Job timeout (seconds)",
            "rounds": "Research rounds", "queries": "Search budget", "sources": "Source budget",
            "context_tokens": "Research context tokens"}


def _choices(values: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "choices": [{"value": value, "label": label}
                                          for value, label in values.items()]}


def _definition(cfg: Config, identity: str) -> tuple[str, str, str, object, object]:
    group, _, name = identity.partition(".")
    if group == "time_settings" and name == "timezone":
        return group, name, "Timezone", AUTOMATIC_TIMEZONE, "timezone"
    if group == "runtime_options" and name in EXECUTION:
        minimum, maximum = EXECUTION_LIMITS[name]
        return group, name, EXECUTION[name], execution_defaults(cfg)[name], (minimum, maximum)
    if group == "tool_availability" and name in TOOLS:
        return group, name, TOOLS[name], True, "boolean"
    if group == "permissions" and name in TOOLS:
        return group, name, TOOLS[name], cfg.permissions.get(name, "ask"), "policy"
    if group == "search_settings" and name in SEARCH:
        options: dict[str, tuple[object, object]] = {
            "provider": (primary_provider(cfg), _choices({"auto": "Auto", **PROVIDERS})),
            "results": (cfg.web_search.default_results, (1, 50)),
            "tavily_depth": (cfg.web_providers["tavily"].default_depth,
                             _choices({"basic": "Basic", "advanced": "Advanced"})),
            "searxng_url": (cfg.searxng_url, "url"),
        }
        default, bounds = options[name]
        return group, name, SEARCH[name], default, bounds
    if group == "fetch_settings" and name in FETCH:
        options = {
            "provider": (fetch_provider(cfg), _choices({"local": "Local", "exa": "Exa"})),
            "exa_fallback": (exa_fallback(cfg), "boolean"),
            "crawl4ai_enabled": (cfg.web_fetch.crawl4ai_enabled, "boolean"),
            "exa_enabled": (cfg.web_fetch.exa_enabled, "boolean"),
            "crawl4ai_url": (cfg.crawl4ai_url, "optional-url"),
        }
        default, bounds = options[name]
        return group, name, FETCH[name], default, bounds
    if group == "research" and name in RESEARCH:
        default = read_research_defaults(cfg).public()[name]
        bounds = (_choices({"auto": "Auto", **PROVIDERS}) if name == "provider"
                  else RESEARCH_LIMITS[name])
        return group, name, RESEARCH[name], default, bounds
    raise ValueError("Unsupported browser setting")


def _valid(value: object, bounds: object) -> bool:
    if bounds == "timezone":
        try:
            validate_timezone(value)
            return True
        except ValueError:
            return False
    if isinstance(bounds, tuple):
        return type(value) is int and bounds[0] <= value <= bounds[1]
    if isinstance(bounds, dict):
        return isinstance(value, str) and value in {item["value"] for item in bounds["choices"]}
    if bounds == "boolean":
        return type(value) is bool
    if bounds in {"url", "optional-url"}:
        if not isinstance(value, str):
            return False
        try:
            return bool(service_url(value)) if value or bounds == "url" else True
        except ValueError:
            return False
    return isinstance(value, str) and value in {"ask", "allow", "deny"}


def _raw(document: dict[str, Any], group: str, name: str) -> dict[str, Any]:
    section = document.get(group, {})
    if not isinstance(section, dict):
        raise ValueError("Settings section is invalid; repair it before saving")
    return {"present": name in section, "value": section.get(name)}


def _revision(raw: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()


def mcp_permission_state(cfg: Config, name: str) -> dict[str, Any]:
    """Review the exact discovered tool set using the terminal's permission fields."""
    server = MCPRegistry(cfg.mcp_servers_file).load().get(name)
    if server is None:
        raise ValueError("MCP connection changed; refresh before reviewing")
    document = read_settings(cfg.data_dir / "chat-preferences.json")
    return _mcp_permission_state(cfg, server, document)


def mcp_permission_states(cfg: Config) -> dict[str, dict[str, Any]]:
    document = read_settings(cfg.data_dir / "chat-preferences.json")
    return {name: _mcp_permission_state(cfg, server, document)
            for name, server in MCPRegistry(cfg.mcp_servers_file).load().items()}


def _mcp_permission_state(cfg: Config, server: MCPServerConfig,
                          document: dict[str, Any]) -> dict[str, Any]:
    tools = sorted({namespaced_tool_name(server.name, tool["name"]) for tool in server.tools
                    if isinstance(tool.get("name"), str) and tool["name"]})
    expected = {tool: _raw(document, "permissions", tool) for tool in tools}
    policies = set()
    for tool, raw in expected.items():
        value = raw["value"] if raw["present"] else cfg.permissions.get(tool, "ask")
        policies.add(value if _valid(value, "policy") else "ask")
    policy = next(iter(policies)) if len(policies) == 1 else "mixed" if policies else "ask"
    if policy not in {"allow", "ask", "deny", "mixed"}:
        policy = "ask"
    state = {"fingerprint": definition_digest(server), "expected": expected}
    return {"policy": policy, "revision": _revision(state), **state}


def read_browser_settings(cfg: Config) -> dict[str, Any]:
    document = read_settings(cfg.data_dir / "chat-preferences.json")
    fields = []
    identities = ["time_settings.timezone"]
    identities += [f"runtime_options.{name}" for name in EXECUTION]
    identities += [f"{group}.{name}" for group in ("tool_availability", "permissions")
                   for name in TOOLS]
    identities += [f"{group}.{name}" for group, names in (
        ("search_settings", SEARCH), ("fetch_settings", FETCH), ("research", RESEARCH)
    ) for name in names]
    for identity in identities:
        group, name, label, default, bounds = _definition(cfg, identity)
        raw = _raw(document, group, name)
        value = raw["value"] if raw["present"] else default
        if bounds == "timezone":
            extra = {**_choices({AUTOMATIC_TIMEZONE: "Automatic (host timezone)",
                                **{name: name for name in timezone_names()}}),
                     "description": "Used for WebUI date and time. Automatic follows the "
                                    "host timezone."}
        elif isinstance(bounds, tuple):
            extra = {"type": "number", "min": bounds[0], "max": bounds[1]}
        elif isinstance(bounds, dict):
            extra = bounds
        elif bounds == "boolean":
            extra = {"type": "boolean"}
        elif bounds in {"url", "optional-url"}:
            extra = {"type": "text", "max_length": 2048, "optional": bounds == "optional-url"}
        else:
            extra = {"type": "policy"}
        fields.append({"id": identity, "label": label,
                       "value": value if _valid(value, bounds) else default,
                       "revision": _revision(raw), **extra})
    return {"fields": fields}


def prepare_setting(cfg: Config, draft: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    if set(draft) != {"operation", "id", "value", "revision"}:
        raise ValueError("Invalid setting draft")
    identity, value = draft["id"], draft["value"]
    if not isinstance(identity, str):
        raise ValueError("Choose a setting")
    if identity.startswith("mcp_permissions."):
        name = identity.removeprefix("mcp_permissions.")
        state = mcp_permission_state(cfg, name)
        if not _valid(value, "policy") or not state["expected"]:
            raise ValueError("Choose a policy for a server with discovered tools")
        if state["revision"] != draft["revision"]:
            raise ValueError("MCP permissions or connection changed; refresh before reviewing")
        label = {"allow": "Auto", "ask": "Ask first", "deny": "Deny"}[value]
        return {"setting_id": identity, "value": value, "expected": state["expected"],
                "fingerprint": state["fingerprint"]}, f"setting:{identity}", (
            f"Set {name} to {label} for its {len(state['expected'])} discovered tools. "
            "Auto skips tool approval; Ask first requests permission; Deny blocks execution. "
            "Applies to future turns. Newly discovered tools keep their own default policy."
        )
    group, name, label, _, bounds = _definition(cfg, identity)
    if not _valid(value, bounds):
        raise ValueError("Setting value is outside its supported range")
    if bounds in ("url", "optional-url") and value:
        value = service_url(value)
    raw = _raw(read_settings(cfg.data_dir / "chat-preferences.json"), group, name)
    if _revision(raw) != draft["revision"]:
        raise ValueError("Setting changed; refresh before reviewing")
    fields = {"setting_id": identity, "value": value, "expected": raw}
    if group == "research":
        fields["expected_research"] = read_research_defaults(cfg).public()
        research_defaults({**fields["expected_research"], name: value})
    category = {"tool_availability": "Tool availability", "permissions": "Permission",
                "time_settings": "Date and time",
                "runtime_options": "Execution", "research": "Research",
                "search_settings": "Web search", "fetch_settings": "Web pages"}[group]
    return fields, f"setting:{identity}", (
        f"Set {label} ({category}) to {value}. "
        "Applies to future turns."
    )


def save_setting(cfg: Config, request: dict[str, Any]) -> None:
    if request["setting_id"].startswith("mcp_permissions."):
        name = request["setting_id"].removeprefix("mcp_permissions.")
        with settings_lock(cfg.mcp_servers_file):
            state = mcp_permission_state(cfg, name)
            if state["fingerprint"] != request["fingerprint"]:
                raise ValueError("MCP connection changed; refresh before reviewing")
            if not _valid(request["value"], "policy") or not request["expected"]:
                raise ValueError("Invalid MCP policy")
            expected = request["expected"]
            if set(expected) != set(state["expected"]):
                raise ValueError("MCP tools changed; refresh before reviewing")
            update_settings(cfg.data_dir / "chat-preferences.json",
                            {("permissions", tool): request["value"] for tool in expected},
                            expected={("permissions", tool): raw["value"] if raw["present"]
                                      else MISSING for tool, raw in expected.items()})
        return
    group, name, _, _, _ = _definition(cfg, request["setting_id"])
    if group == "research":
        expected = request["expected_research"]
        save_research_defaults(cfg, {**expected, name: request["value"]}, expected)
        return
    expected = request["expected"]
    update_settings(cfg.data_dir / "chat-preferences.json", {(group, name): request["value"]},
                    expected={(group, name): expected["value"] if expected["present"] else MISSING})
