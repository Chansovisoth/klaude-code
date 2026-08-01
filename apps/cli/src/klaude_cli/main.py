"""klaude — local-first AI coding agent.

Commands:
  klaude chat                 interactive agent session in the current repo
  klaude ask "question"       one-shot question (tools enabled)
  klaude learn URL|FILE -l X  ingest docs into a named library
  klaude docs add NAME URL    install refreshable llms.txt documentation
  klaude crawl URL -l X       politely crawl same-domain pages into a library
  klaude import-skill ZIP -l X install an assistant skill package
  klaude query "q" [-l X]     hybrid-search the knowledge base
  klaude libraries            list learned libraries
  klaude skills               list installed assistant skills
  klaude search "q"           web search via the configured provider
  klaude code-search "q"      search programming docs and examples
  klaude huggingface-search   search Hugging Face models, datasets, and Spaces
  klaude remember "fact"      append a durable fact to memory
  klaude memory               inspect and manage durable memory
  klaude session-search "q"   search previous conversation sessions
  klaude status               show configured modes, storage, and tool permissions
  klaude system-info          show normalized runtime context diagnostics
  klaude doctor               verify every service and model
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import textwrap
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from difflib import get_close_matches
from enum import StrEnum
from importlib import resources
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import typer
from klaude_core import Agent, Memory, Ollama, PermissionGate, Tool, load_config
from klaude_core.config import CONFIG_DIR
from klaude_core.memory import explicit_memory_candidate, is_sensitive_memory
from klaude_core.runtime_context import (
    collect_runtime_context,
    context_to_dict,
    render_runtime_context,
)
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

app = typer.Typer(add_completion=False, no_args_is_help=True)
docs_app = typer.Typer(
    help="Manage refreshable documentation sources.",
    invoke_without_command=True,
)
app.add_typer(docs_app, name="docs")
memory_app = typer.Typer(
    help="Manage durable memory and session recall.",
    invoke_without_command=True,
)
app.add_typer(memory_app, name="memory")
console = Console()
_RUNTIME_CONTEXT_NOTICE_SHOWN = False
DEFAULT_COMMAND_REFERENCE_WIDTH = 100
WEB_SEARCH_PROVIDER_LABELS = {
    "google",
    "parallel",
    "tavily",
    "exa",
    "firecrawl",
    "ddgs",
    "searxng",
    "none",
}


def _print_trace(line: str) -> None:
    console.print(Text(line, style="dim"))


class CommandSurface(StrEnum):
    OPTION = "option"
    CLI = "cli"
    DOCS = "docs"
    CHAT = "chat"


@dataclass(frozen=True)
class CommandSpec:
    name: str
    surface: CommandSurface
    usage: str
    summary: str
    aliases: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommandResolution:
    exact: CommandSpec | None
    suggestions: tuple[CommandSpec, ...] = ()


OPTION_COMMANDS = (
    CommandSpec(
        "help-option",
        CommandSurface.OPTION,
        "--help",
        "Show this message and exit.",
    ),
)
CLI_COMMANDS = (
    CommandSpec(
        "chat",
        CommandSurface.CLI,
        "chat",
        "Interactive agent session in the current directory.",
    ),
    CommandSpec("ask", CommandSurface.CLI, "ask", "One-shot question with tools enabled."),
    CommandSpec(
        "learn",
        CommandSurface.CLI,
        "learn",
        "Ingest a URL or local file into the knowledge base.",
    ),
    CommandSpec(
        "crawl",
        CommandSurface.CLI,
        "crawl",
        "Politely crawl same-domain pages and index them into a knowledge library.",
    ),
    CommandSpec(
        "import-skill",
        CommandSurface.CLI,
        "import-skill",
        "Install a skill ZIP/folder and index its text into a knowledge library.",
    ),
    CommandSpec(
        "query",
        CommandSurface.CLI,
        "query",
        "Hybrid-search the knowledge base (no LLM, raw chunks).",
    ),
    CommandSpec("libraries", CommandSurface.CLI, "libraries", "List learned knowledge libraries."),
    CommandSpec(
        "collections",
        CommandSurface.CLI,
        "collections",
        "Compatibility alias for libraries.",
        aliases=("collection",),
    ),
    CommandSpec("skills", CommandSurface.CLI, "skills", "List installed assistant skills."),
    CommandSpec(
        "search",
        CommandSurface.CLI,
        "search",
        "Web search via the configured provider.",
        aliases=("web search", "search the web"),
    ),
    CommandSpec(
        "code-search",
        CommandSurface.CLI,
        "code-search",
        "Search programming docs, code examples, and debugging references.",
    ),
    CommandSpec(
        "huggingface-search",
        CommandSurface.CLI,
        "huggingface-search",
        "Search Hugging Face Hub models, datasets, or Spaces.",
    ),
    CommandSpec(
        "huggingface-details",
        CommandSurface.CLI,
        "huggingface-details",
        "Print Hugging Face Hub metadata for a model, dataset, or Space.",
    ),
    CommandSpec(
        "huggingface-readme",
        CommandSurface.CLI,
        "huggingface-readme",
        "Fetch a Hugging Face model card, dataset card, or Space README.",
    ),
    CommandSpec(
        "models",
        CommandSurface.CLI,
        "models",
        "List every model installed in Ollama and which role klaude assigns it.",
    ),
    CommandSpec(
        "remember",
        CommandSurface.CLI,
        "remember",
        "Append a durable fact to memory.md (goes into every system prompt).",
    ),
    CommandSpec("sessions", CommandSurface.CLI, "sessions", "List recent conversation sessions."),
    CommandSpec(
        "session-search",
        CommandSurface.CLI,
        "session-search",
        "Search previous conversation sessions.",
    ),
    CommandSpec(
        "status",
        CommandSurface.CLI,
        "status",
        "Show configured modes, storage, and tool permissions.",
    ),
    CommandSpec(
        "system-info",
        CommandSurface.CLI,
        "system-info",
        "Show normalized runtime context diagnostics.",
    ),
    CommandSpec(
        "doctor",
        CommandSurface.CLI,
        "doctor",
        "Check every service, model, and directory klaude needs.",
    ),
    CommandSpec("docs", CommandSurface.CLI, "docs", "Manage refreshable documentation sources."),
    CommandSpec(
        "memory",
        CommandSurface.CLI,
        "memory",
        "Manage durable memory and session recall.",
    ),
)
DOCS_COMMANDS = (
    CommandSpec(
        "docs-add",
        CommandSurface.DOCS,
        "docs add NAME URL -l LIBRARY",
        "Install refreshable llms.txt documentation.",
        aliases=("docs add", "klaude docs add"),
    ),
    CommandSpec(
        "docs-update",
        CommandSurface.DOCS,
        "docs update NAME",
        "Refresh one installed docs source.",
        aliases=("docs update", "klaude docs update"),
    ),
    CommandSpec(
        "docs-update-sources",
        CommandSurface.DOCS,
        "docs update --sources",
        "Refresh all installed refreshable docs sources.",
    ),
    CommandSpec(
        "docs-update-online",
        CommandSurface.DOCS,
        "docs update --online",
        "Update sources listed in online-docs.txt.",
    ),
    CommandSpec(
        "docs-update-all",
        CommandSurface.DOCS,
        "docs update --all",
        "Refresh docs sources and process online-docs.txt.",
        aliases=("update all docs", "refresh all docs"),
    ),
)
CHAT_COMMANDS = (
    CommandSpec("help", CommandSurface.CHAT, "/help", "Show this command reference."),
    CommandSpec("commands", CommandSurface.CHAT, "/commands", "Show this command reference."),
    CommandSpec(
        "/models",
        CommandSurface.CHAT,
        "/models",
        "List installed Ollama models and mark the active model.",
    ),
    CommandSpec(
        "model",
        CommandSurface.CHAT,
        "/model",
        "Show the active chat model.",
    ),
    CommandSpec(
        "model-name",
        CommandSurface.CHAT,
        "/model NAME",
        "Switch the active chat model while keeping the current chat history.",
        aliases=("/model [NAME]",),
        examples=("/model", "/model qwen3-coder:30b"),
    ),
    CommandSpec("quit", CommandSurface.CHAT, "/quit", "Exit the interactive chat session."),
    CommandSpec("exit", CommandSurface.CHAT, "/exit", "Exit the interactive chat session."),
    CommandSpec("q", CommandSurface.CHAT, "/q", "Exit the interactive chat session."),
)
PUBLIC_COMMAND_SPECS = CLI_COMMANDS + DOCS_COMMANDS + CHAT_COMMANDS


def _plain_command_text(value: str) -> str:
    return "".join(
        char for char in value if char == "\n" or char == "\t" or ord(char) >= 32
    )


def _command_reference_width(width: int | None = None) -> int:
    if width is None:
        return DEFAULT_COMMAND_REFERENCE_WIDTH
    return max(32, width)


def iter_command_specs(
    surface: CommandSurface | None = None,
) -> tuple[CommandSpec, ...]:
    specs = PUBLIC_COMMAND_SPECS
    if surface is None:
        return specs
    return tuple(spec for spec in specs if spec.surface == surface)


def _command_lookup_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\bklaude\s+", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" ?.!,;:")


def _command_lookup_keys(spec: CommandSpec) -> tuple[str, ...]:
    values = {spec.name, spec.usage, *spec.aliases}
    if spec.surface in {CommandSurface.CLI, CommandSurface.DOCS}:
        values.add(f"klaude {spec.usage}")
    if spec.surface == CommandSurface.CHAT and spec.usage.startswith("/"):
        values.add(spec.usage.split()[0])
    return tuple(sorted({_command_lookup_text(value) for value in values if value}))


def _registered_command_map() -> dict[str, CommandSpec]:
    lookup: dict[str, CommandSpec] = {}
    for spec in PUBLIC_COMMAND_SPECS:
        for key in _command_lookup_keys(spec):
            lookup.setdefault(key, spec)
    return lookup


def _registered_command_usages() -> tuple[str, ...]:
    return tuple(spec.usage for spec in PUBLIC_COMMAND_SPECS)


def _command_reference_context() -> str:
    chat = ", ".join(spec.usage for spec in CHAT_COMMANDS)
    cli = ", ".join(spec.usage for spec in CLI_COMMANDS)
    docs = ", ".join(spec.usage for spec in DOCS_COMMANDS)
    return (
        "Displayed Klaude's canonical command reference from "
        "canonical_command_registry. CLI commands shown included "
        f"{cli}. Docs commands shown included {docs}. Chat commands shown "
        f"included {chat}."
    )


COMMAND_REFERENCE_TERMS = {
    "command",
    "commands",
    "comand",
    "comands",
    "comman",
    "commans",
    "commmand",
    "commmands",
    "cmd",
    "cmds",
}
COMMAND_REFERENCE_ACTION_TERMS = {
    "available",
    "list",
    "show",
    "use",
    "uss",
    "type",
    "help",
    "klaude",
    "slash",
}
COMMAND_REFERENCE_TERM_TARGETS = tuple(
    sorted(COMMAND_REFERENCE_TERMS | COMMAND_REFERENCE_ACTION_TERMS)
)


def _command_request_tokens(text: str) -> list[str]:
    return re.findall(r"/?[a-z0-9_-]+", text.lower())


def _is_fuzzy_command_term(token: str, targets: set[str]) -> bool:
    if token in targets:
        return True
    if len(token) < 4:
        return False
    matches = get_close_matches(token, COMMAND_REFERENCE_TERM_TARGETS, n=1, cutoff=0.82)
    return bool(matches and matches[0] in targets)


def is_complete_command_reference_request(text: str) -> bool:
    normalized = _command_lookup_text(text)
    if normalized in {"/help", "/commands"}:
        return True
    if any(pattern in normalized for pattern in COMMAND_REFERENCE_PATTERNS):
        return True

    tokens = _command_request_tokens(normalized)
    has_command_noun = any(
        _is_fuzzy_command_term(token, COMMAND_REFERENCE_TERMS) for token in tokens
    )
    has_reference_action = any(
        _is_fuzzy_command_term(token, COMMAND_REFERENCE_ACTION_TERMS) for token in tokens
    )
    if has_command_noun and has_reference_action:
        return True
    if "slash" in tokens and has_command_noun:
        return True
    if {"what", "can", "i", "type"} <= set(tokens):
        return True
    return False


def _format_command_entries(
    entries: tuple[CommandSpec, ...],
    *,
    width: int | None,
) -> list[str]:
    lines: list[str] = []
    effective_width = _command_reference_width(width)
    name_width = max(len(entry.usage) for entry in entries) + 2
    inline_threshold = 56

    for entry in entries:
        name = _plain_command_text(entry.usage)
        description = _plain_command_text(entry.summary)
        if not description:
            lines.append(f"  {name}")
            continue

        prefix = f"  {name:<{name_width}}"
        if effective_width < inline_threshold or len(prefix) + 20 > effective_width:
            lines.append(f"  {name}")
            wrapped = textwrap.wrap(
                description,
                width=max(20, effective_width - 6),
                initial_indent="      ",
                subsequent_indent="      ",
                break_long_words=False,
                break_on_hyphens=False,
            )
            lines.extend(wrapped or ["      "])
            continue

        description_width = max(20, effective_width - len(prefix))
        wrapped = textwrap.wrap(
            description,
            width=description_width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        lines.append(prefix + (wrapped[0] if wrapped else ""))
        continuation_indent = " " * len(prefix)
        lines.extend(f"{continuation_indent}{line}" for line in wrapped[1:])
    return lines


def _append_command_section(
    lines: list[str],
    title: str,
    entries: tuple[CommandSpec, ...],
    *,
    width: int | None,
) -> None:
    if lines:
        lines.append("")
    lines.append(title)
    lines.append("-" * len(title))
    lines.extend(_format_command_entries(entries, width=width))


def format_command_reference(*, width: int | None = None) -> str:
    lines = ["Usage: klaude [OPTIONS] COMMAND [ARGS]..."]
    _append_command_section(lines, "OPTIONS", OPTION_COMMANDS, width=width)
    _append_command_section(lines, "CLI COMMANDS", CLI_COMMANDS, width=width)
    _append_command_section(lines, "DOCS COMMANDS", DOCS_COMMANDS, width=width)
    _append_command_section(lines, "CHAT COMMANDS", CHAT_COMMANDS, width=width)
    return "\n".join(lines)


COMMAND_REFERENCE = format_command_reference()
COMMAND_REFERENCE_SYSTEM_HINT = (
    "The complete command reference is available through the deterministic "
    "command-reference router and the list_commands tool. Preserve that "
    "formatted output exactly when it is returned."
)

WEATHER_TOOL_DESCRIPTION = (
    "Get current weather and a short forecast for a city or province. "
    "Use for single-location weather, forecast, temperature, rain, or humidity questions."
)
LIST_COMMANDS_TOOL_DESCRIPTION = (
    "Return Klaude's canonical public CLI and chat command reference. "
    "Use only when the user explicitly asks for available commands, CLI help, "
    "slash commands, or command usage. Never invent commands. For a question "
    "about one command, use focused command help instead of returning the "
    "complete reference."
)


class ToolUseRoute(StrEnum):
    DIRECT_RESPONSE = "DIRECT_RESPONSE"
    HEURISTIC_TOOL_SELECTION = "HEURISTIC_TOOL_SELECTION"
    WORKSPACE_TOOL = "WORKSPACE_TOOL"
    KNOWLEDGE_TOOL = "KNOWLEDGE_TOOL"
    WEB_TOOL = "WEB_TOOL"
    UTILITY_TOOL = "UTILITY_TOOL"
    COMMAND_REFERENCE = "COMMAND_REFERENCE"


def _ask_permission(tool: str, detail: str) -> str:
    console.print(Panel(detail, title=f"[bold yellow]{tool}[/]", border_style="yellow"))
    return console.input("[yellow]allow? \\[y]es / \\[n]o / \\[a]lways: [/]").strip().lower()[:1]


def _system_prompt(memory: Memory, runtime_context: str = "") -> str:
    template = (
        resources.files("klaude_core") / "prompts" / "system.md"
    ).read_text()
    auto = "enabled" if memory.auto_memory_enabled() else "disabled"
    return (
        template
        .replace("{MEMORY}", memory.facts() or "(none)")
        .replace("{AUTO_MEMORY}", auto)
        .replace("{COMMANDS}", COMMAND_REFERENCE_SYSTEM_HINT)
        .replace("{RUNTIME_CONTEXT}", runtime_context or "(runtime context unavailable)")
    )


def _runtime_context_result(cfg, workdir: Path, *, refresh: bool = False):
    try:
        return collect_runtime_context(cfg, workdir, force_refresh=refresh)
    except Exception as exc:
        console.print(f"[yellow]runtime context unavailable:[/] {exc}")
        return None


def _runtime_context_text(cfg, workdir: Path, *, refresh: bool = False) -> str:
    result = _runtime_context_result(cfg, workdir, refresh=refresh)
    if not result:
        return ""
    return render_runtime_context(result.context, cfg)


def _apply_runtime_context_to_search_config(cfg, runtime_result) -> None:
    if runtime_result is None:
        return
    location = getattr(runtime_result.context, "location", None)
    if location is None:
        return
    if not cfg.runtime_context.location.configured_country and location.country_code:
        cfg.runtime_context.location.configured_country = location.country_code
    if not cfg.runtime_context.location.configured_region and location.region:
        cfg.runtime_context.location.configured_region = location.region


def _maybe_show_runtime_context_note(result) -> None:
    global _RUNTIME_CONTEXT_NOTICE_SHOWN
    if _RUNTIME_CONTEXT_NOTICE_SHOWN or not result:
        return
    _RUNTIME_CONTEXT_NOTICE_SHOWN = True
    context = result.context
    if context.provider == "fastfetch":
        console.print(
            f"[dim]system context: fastfetch ({result.duration_ms} ms)[/]"
        )
        return
    if context.provider == "off":
        console.print("[dim]system context: off[/]")
        return
    suggestion = result.install_suggestion
    if suggestion:
        console.print(f"[dim]{suggestion}[/]")
    else:
        console.print(f"[dim]system context: {context.provider} fallback[/]")


def _format_session_hits(hits: list[dict]) -> str:
    if not hits:
        return "(no matching previous sessions)"
    parts = []
    for hit in hits:
        parts.append(
            f"{hit['date']} session={hit['session_id']} role={hit['role']}\n"
            f"{hit['content'][:700]}"
        )
    return "\n\n---\n\n".join(parts)


def _format_recent_sessions(sessions: list[dict]) -> str:
    if not sessions:
        return "(no previous sessions)"
    return "\n".join(
        f"{s['date']}  {s['session_id']}  {s['turns']} turns  {s['preview']}"
        for s in sessions
    )


def _permission_label(cfg, tool: str) -> str:
    return cfg.permissions.get(tool, "ask")


def _mode_from_permission(policy: str) -> str:
    if policy == "allow":
        return "on"
    if policy == "deny":
        return "off"
    return "ask"


def _web_mode(cfg, tool: str = "web_search") -> str:
    permission = _permission_label(cfg, tool)
    if permission == "deny":
        return "off"
    if cfg.web_provider == "auto":
        return "auto"
    if permission == "ask":
        return f"ask/{cfg.web_provider}"
    return f"on/{cfg.web_provider}"


def _auth_label(value: str) -> str:
    return "configured" if value else "not configured"


def _count_status(label: str, count: int) -> str:
    return f"{count} {label}" if count else "none"


def _format_web_results(results: list[dict], requested: int | None = None) -> str:
    if not results:
        return "(no results)"
    formatted = []
    if requested is not None and len(results) < requested:
        formatted.append(f"Found {len(results)} relevant results (requested {requested}).")
    for i, result in enumerate(results, 1):
        formatted.append(
            f"[{i}] {result.get('title', '')}\n"
            f"{result.get('url', '')}\n"
            f"{result.get('snippet', '')}"
        )
    return "\n\n".join(formatted)


def _format_search_response(response, requested: int | None = None) -> str:
    text = _format_web_results(response.results, requested)
    ambiguity = _format_ambiguity_summary(response.provider_metadata or {})
    if ambiguity:
        text = f"{ambiguity}\n\n{text}"
    if response.warnings:
        warning_lines = [
            f"{warning.get('query', '')}: {warning.get('message', '')}".strip(": ")
            for warning in response.warnings
        ]
        text += "\n\nWarnings:\n" + "\n".join(f"- {line}" for line in warning_lines if line)
    return text


def _format_ambiguity_summary(metadata: dict) -> str:
    debug = metadata.get("ambiguity") if isinstance(metadata.get("ambiguity"), dict) else {}
    candidates = metadata.get("entity_candidates")
    if not debug or not isinstance(candidates, list) or not candidates:
        return ""
    if not debug.get("ambiguity_detected") and len(candidates) <= 1:
        return ""

    location = str(debug.get("location_country") or "").strip()
    location_bits = []
    if location and debug.get("location_mode") == "bias":
        location_bits.append(f"Based on the approximate {location} context")
    elif location:
        location_bits.append(f"Based on the explicit {location} context")
    prefix = (
        f"{location_bits[0]}, the most relevant candidate is"
        if location_bits
        else "The most relevant candidate is"
    )
    top = candidates[0]
    lines = [
        '"{}" can refer to several things.'.format(
            (top.get("aliases") or [top.get("canonical_name", "this term")])[0]
        ),
        (
            f"{prefix} {top.get('canonical_name', '')}"
            f" - {top.get('description', 'a supported entity')}."
        ),
    ]
    other = [candidate for candidate in candidates[1:4] if candidate.get("canonical_name")]
    if other:
        lines.append("Other credible meanings:")
        for candidate in other:
            description = candidate.get("description") or "supported by retrieved evidence"
            lines.append(f"- {candidate.get('canonical_name')} - {description}.")
    if debug.get("is_ambiguous"):
        lines.append("Ask a clarification question if the user did not specify which one.")
    return "\n".join(lines)


def _stable_web_search_providers(values) -> list[str]:
    providers: list[str] = []
    for value in values or []:
        name = str(value or "").strip().lower()
        if name == "local":
            name = "searxng"
        if name == "quality":
            continue
        if name in WEB_SEARCH_PROVIDER_LABELS and name not in providers:
            providers.append(name)
    return providers


def _web_search_display_lines(metadata: dict, result: str) -> list[str]:
    provider_attempts = [
        attempt
        for attempt in metadata.get("provider_attempts", [])
        if isinstance(attempt, dict)
    ]
    result_providers = _stable_web_search_providers(
        item.get("provider")
        for item in metadata.get("search_results", [])
        if isinstance(item, dict)
    )
    successful = _stable_web_search_providers(metadata.get("successful_providers"))
    if not successful:
        successful = result_providers
    returned = _stable_web_search_providers(metadata.get("providers_returned"))
    attempted = _stable_web_search_providers(metadata.get("attempted_providers"))
    if not attempted and provider_attempts:
        attempted = _stable_web_search_providers(
            attempt.get("provider") for attempt in provider_attempts
        )
    if not attempted:
        attempted = successful
    provider_label = str(metadata.get("provider_label") or metadata.get("provider") or "")
    if provider_label.lower() not in {"multi", *WEB_SEARCH_PROVIDER_LABELS}:
        provider_label = ""
    preview = result[:200].replace("\n", " ")
    lines: list[str] = []

    if not successful:
        if returned:
            for attempt in provider_attempts:
                name = str(attempt.get("provider") or "").lower()
                status = str(attempt.get("status") or "").replace("_", " ")
                reason = str(attempt.get("reason") or status)
                if name in WEB_SEARCH_PROVIDER_LABELS:
                    lines.append(f"-> web_search [{name}]")
                    lines.append(f"   {reason}")
            if lines:
                return lines
            label = provider_label or " + ".join(returned)
            lines.append(f"-> web_search [{label}]")
            lines.append(f"   {preview}")
            return lines
        if provider_attempts:
            for attempt in provider_attempts:
                name = str(attempt.get("provider") or "").lower()
                status = str(attempt.get("status") or "").replace("_", " ")
                reason = str(attempt.get("reason") or status)
                if name in WEB_SEARCH_PROVIDER_LABELS:
                    lines.append(f"-> web_search [{name}]")
                    lines.append(f"   {reason}")
            if lines:
                lines.append("   No search provider succeeded.")
                return lines
        if provider_label == "none" and not attempted:
            lines.append("-> web_search [none]")
            lines.append("   No configured provider was available.")
            return lines
        if len(attempted) == 1:
            lines.append(f"-> web_search [{attempted[0]}]")
        else:
            lines.append("-> web_search")
        lines.append("   No search provider succeeded.")
        return lines

    first_success = successful[0]
    for attempt in provider_attempts:
        name = str(attempt.get("provider") or "").lower()
        if not name or name in successful:
            if name == first_success:
                break
            continue
        status = str(attempt.get("status") or "").replace("_", " ")
        reason = str(attempt.get("reason") or status)
        lines.append(f"-> web_search [{name}]")
        lines.append(f"   {reason} - trying next provider.")

    if not provider_label and len(successful) > 1:
        provider_label = " + ".join(successful)
    label = provider_label or first_success
    lines.append(f"-> web_search [{label}]")
    display_lines = metadata.get("display_lines")
    if isinstance(display_lines, list) and display_lines:
        lines.extend(f"   {line}" for line in display_lines if str(line).strip())
    else:
        lines.append(f"   {preview}")
    return lines


def _bounded_result_count(value, default: int = 12) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = default
    return max(1, min(count, 50))


def _search_execution_metadata(response, configured_provider: str | None = None) -> dict:
    result_providers = _stable_web_search_providers(
        result.get("provider") for result in response.results if isinstance(result, dict)
    )
    provider_metadata = response.provider_metadata or {}
    attempted = _stable_web_search_providers(response.providers_attempted or [])
    successful = _stable_web_search_providers(response.providers_succeeded or [])
    if not successful:
        successful = result_providers
    returned = _stable_web_search_providers(provider_metadata.get("providers_returned"))
    if not attempted:
        attempted = successful or returned
    if not attempted and configured_provider:
        configured = "searxng" if configured_provider == "local" else configured_provider
        attempted = _stable_web_search_providers([configured])
        if response.results:
            successful = attempted
    if len(successful) > 1:
        provider = "multi"
        provider_label = " + ".join(successful)
    elif successful:
        provider = successful[0]
        provider_label = successful[0]
    elif returned:
        provider = "multi" if len(returned) > 1 else returned[0]
        provider_label = " + ".join(returned) if len(returned) > 1 else returned[0]
    else:
        metadata_provider = str(provider_metadata.get("provider") or "").lower()
        provider = metadata_provider if metadata_provider in WEB_SEARCH_PROVIDER_LABELS else "none"
        provider_label = provider
    first_success_index = (
        min(attempted.index(name) for name in successful if name in attempted)
        if successful and any(name in attempted for name in successful)
        else 0
    )
    fallback_used = bool(successful and first_success_index > 0)
    provider_attempts = provider_metadata.get("provider_attempts", [])
    if not provider_attempts and successful:
        provider_attempts = [
            {
                "provider": name,
                "status": "succeeded",
                "reason": f"found {len(response.results)} relevant results",
            }
            for name in successful
        ]
    return {
        "tool": "web_search",
        "canonical_tool": "web_search",
        "provider": provider,
        "active_provider": provider,
        "provider_label": provider_label,
        "attempted_providers": attempted,
        "successful_providers": successful,
        "providers_returned": returned,
        "fallback_used": fallback_used,
        "query_count": len(response.queries_attempted or []),
        "provider_request_count": len(attempted),
        "provider_attempts": provider_attempts,
        "display_lines": provider_metadata.get("display_lines", []),
        "result_count": provider_metadata.get("result_count"),
        "plausible_candidate_count": provider_metadata.get("plausible_candidate_count"),
    }


def _web_search_start_metadata(web, query: str, max_results: int = 12) -> dict:
    requested = _bounded_result_count(max_results, 12)
    try:
        from klaude_web.providers import ProviderRegistry, build_search_query

        search_query = build_search_query(query, web.cfg, requested)
        registry = ProviderRegistry(web.cfg)
        providers, _skipped = registry.eligible_providers(search_query)
        planned = _stable_web_search_providers(provider.name for provider in providers)
    except Exception:
        planned = []
        search_query = None
    provider = planned[0] if planned else "none"
    return {
        "tool": "web_search",
        "canonical_tool": "web_search",
        "provider": provider,
        "active_provider": provider,
        "provider_label": "" if provider == "none" else provider,
        "attempted_providers": planned[:1],
        "successful_providers": [],
        "fallback_used": False,
        "query": getattr(search_query, "text", query),
    }


def _web_search_tool_result(web, query: str, max_results: int = 12) -> dict:
    requested = _bounded_result_count(max_results, 12)
    response = web.search_detailed(query, requested)
    execution = _search_execution_metadata(response, web.cfg.web_provider)
    return {
        "content": _format_search_response(response, requested),
        "metadata": {
            **execution,
            "search_results": response.results,
            "warnings": response.warnings,
            "queries_attempted": response.queries_attempted,
            "queries_failed": response.queries_failed,
            "providers_attempted": response.providers_attempted,
            "providers_succeeded": response.providers_succeeded,
            "provider_states": response.provider_states,
            "provider_metadata": response.provider_metadata,
        },
    }


def _fetch_url_tool_result(web, url: str) -> dict:
    content = web.fetch(url)[:15_000]
    metadata: dict[str, object] = {"url": url}
    try:
        from klaude_web.providers import classify_fetch_outcome, targeted_same_domain_links

        outcome = classify_fetch_outcome(content)
        metadata["fetch_outcome"] = {
            "status": outcome.status,
            "retryable": outcome.retryable,
            "use_next_candidate": outcome.use_next_candidate,
            "reason": outcome.reason,
        }
        schoolish = bool(
            re.search(
                r"\b(school|schools|academy|admissions?|campus|campuses|"
                r"students?|education)\b",
                f"{url}\n{content}",
                re.IGNORECASE,
            )
        )
        if outcome.status == "ok" and schoolish:
            max_pages = max(
                0,
                min(
                    3,
                    int(getattr(web.cfg.web_verification, "max_pages_per_domain", 4) or 4) - 1,
                ),
            )
            metadata["verification_links"] = targeted_same_domain_links(
                url,
                content,
                relationship="school identity and location",
                max_pages=max_pages,
            )
    except Exception:
        metadata.setdefault("verification_links", [])
    return {"content": content, "metadata": metadata}


def _query_knowledge_tool_result(
    kn,
    query: str,
    library: str = "",
    collection: str = "",
    k: int = 6,
) -> dict:
    target_library = library or collection
    content = kn.query_as_context(query, target_library, k)
    found = not content.startswith("No relevant local knowledge found.")
    return {
        "content": content,
        "metadata": {
            "tool": "query_knowledge",
            "library": target_library,
            "found": found,
            "result_count": _knowledge_context_chunk_count(content) if found else 0,
        },
    }


def _knowledge_context_chunk_count(content: str) -> int:
    matches = re.findall(r"(?m)^###\s+", content)
    if matches:
        return len(matches)
    return 1 if content.strip() and not content.startswith("No relevant") else 0


def _query_knowledge_display_lines(metadata: dict, result: str) -> list[str]:
    library = str(metadata.get("library") or "").strip()
    found = bool(metadata.get("found"))
    count = int(metadata.get("result_count") or 0)
    suffix = f" [{library}]" if library else ""
    lines = [f"-> query_knowledge{suffix}"]
    if found:
        noun = "chunk" if count == 1 else "chunks"
        lines.append(f"   Found {max(1, count)} relevant {noun}.")
    else:
        lines.append("   No sufficiently relevant local knowledge.")
    return lines


def _command_reference_result(*, width: int | None = None) -> dict:
    return {
        "content": format_command_reference(width=width),
        "metadata": {
            "content_type": "command_reference",
            "preserve_whitespace": True,
            "direct_render": True,
            "source": "canonical_command_registry",
            "command_usages": _registered_command_usages(),
        },
    }


def _format_single_command_help(
    command: str,
    description: str,
    *,
    width: int | None = None,
) -> str:
    effective_width = _command_reference_width(width)
    lines = [command]
    wrapped = textwrap.wrap(
        _plain_command_text(description),
        width=max(20, effective_width - 4),
        initial_indent="    ",
        subsequent_indent="    ",
        break_long_words=False,
        break_on_hyphens=False,
    )
    lines.extend(wrapped or ["    "])
    return "\n".join(lines)


SLASH_COMMAND_RE = re.compile(r"/[a-z][a-z0-9_-]*", re.IGNORECASE)
FOCUSED_COMMAND_HELP_RE = re.compile(
    r"(?i)\b(?:what does|how do i use|how does|explain|what command|which command)\b"
)


def _unique_specs(specs: list[CommandSpec]) -> tuple[CommandSpec, ...]:
    unique: list[CommandSpec] = []
    for spec in specs:
        if spec not in unique:
            unique.append(spec)
    return tuple(unique)


def _resolve_exact_command(value: str) -> CommandSpec | None:
    return _registered_command_map().get(_command_lookup_text(value))


def _command_suggestions(
    value: str,
    *,
    surface: CommandSurface | None = None,
) -> tuple[CommandSpec, ...]:
    lookup = {
        key: spec
        for key, spec in _registered_command_map().items()
        if surface is None or spec.surface == surface
    }
    query = _command_lookup_text(value)
    matches = get_close_matches(query, tuple(lookup), n=3, cutoff=0.74)
    return _unique_specs([lookup[match] for match in matches])


def resolve_command_help_request(user_message: str) -> CommandResolution | None:
    text = _command_lookup_text(user_message)
    slash_match = SLASH_COMMAND_RE.search(user_message)
    if slash_match:
        token = slash_match.group(0)
        exact = _resolve_exact_command(token)
        if exact is None:
            return CommandResolution(
                exact=None,
                suggestions=_command_suggestions(token, surface=CommandSurface.CHAT),
            )
        return CommandResolution(exact=exact)

    help_intent = bool(FOCUSED_COMMAND_HELP_RE.search(user_message))
    if (
        "what command" in text
        and "search" in text
        and any(word in text for word in ("web", "internet", "online"))
    ):
        return CommandResolution(exact=next(spec for spec in CLI_COMMANDS if spec.name == "search"))
    if "update all docs" in text or "refresh all docs" in text:
        return CommandResolution(
            exact=next(spec for spec in DOCS_COMMANDS if spec.name == "docs-update-all")
        )
    if not help_intent:
        return None

    lookup = _registered_command_map()
    for key in sorted(lookup, key=len, reverse=True):
        if key and re.search(rf"(?<![\w/-]){re.escape(key)}(?![\w/-])", text):
            return CommandResolution(exact=lookup[key])
    return None


def _focused_command_usage(spec: CommandSpec) -> str:
    if spec.surface == CommandSurface.CHAT:
        return spec.usage
    if spec.name == "search":
        return "klaude search QUERY"
    return f"klaude {spec.usage}"


def _format_model_command_help(*, include_yes: bool = False) -> str:
    lines = []
    if include_yes:
        lines.append("Yes. `/model` manages the active chat model.")
        lines.append("")
    lines.extend(
        [
            "/model",
            "    Show the currently active model.",
            "",
            "/model NAME",
            "    Switch to an installed Ollama model while preserving this conversation.",
            "",
            "Examples:",
            "    /model",
            "    /model qwen3-coder:30b",
            "",
            "Use /models to list the available models.",
        ]
    )
    return "\n".join(lines)


def format_unknown_command_message(
    command: str,
    suggestions: tuple[CommandSpec, ...] = (),
    *,
    chat_input: bool = False,
) -> str:
    command = command.strip().split()[0]
    if chat_input:
        lines = [f"Unknown chat command: {command}"]
    else:
        kind = "chat command" if command.startswith("/") else "command"
        lines = [f"{command} is not a recognized Klaude {kind}."]
    if suggestions:
        suggestion = suggestions[0].usage.split()[0]
        lines.append(f"Did you mean {suggestion}?")
    lines.append("Type /help to see the available commands.")
    return "\n".join(lines)


def _known_chat_slash_bases() -> set[str]:
    return {spec.usage.split()[0] for spec in CHAT_COMMANDS}


def _handle_unknown_slash_command(
    user_msg: str,
    *,
    agent: Agent | None = None,
    memory: Memory | None = None,
    session_id: str | None = None,
) -> bool:
    if not user_msg.startswith("/"):
        return False
    base = user_msg.split()[0]
    if base in _known_chat_slash_bases():
        return False
    suggestions = _command_suggestions(base, surface=CommandSurface.CHAT)
    message = format_unknown_command_message(base, suggestions, chat_input=True)
    _print_preformatted_text(message)
    _record_direct_command_context(
        user_msg,
        message,
        agent=agent,
        memory=memory,
        session_id=session_id,
    )
    return True


def format_command_help(
    resolution: CommandResolution,
    user_message: str,
    *,
    width: int | None = None,
) -> str:
    if resolution.exact is None:
        match = SLASH_COMMAND_RE.search(user_message)
        command = match.group(0) if match else "command"
        return format_unknown_command_message(command, resolution.suggestions)

    spec = resolution.exact
    if spec.name in {"model", "model-name"}:
        return _format_model_command_help(
            include_yes="these are the commands" in _command_lookup_text(user_message)
        )
    command = _focused_command_usage(spec)
    return _format_single_command_help(command, spec.summary, width=width)


def format_focused_command_help(
    user_message: str,
    *,
    width: int | None = None,
) -> str | None:
    resolution = resolve_command_help_request(user_message)
    if resolution is not None:
        return format_command_help(resolution, user_message, width=width)
    return None


CASUAL_DIRECT_PATTERNS = (
    "hi",
    "hello",
    "hey",
    "how are you",
    "who are you",
    "who might you be",
    "what are you",
    "introduce yourself",
    "thanks",
    "thank you",
    "okay",
    "ok",
    "good morning",
    "good night",
)
CONVERSATIONAL_PREFIX_PATTERNS = (
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "okay",
    "ok",
    "good morning",
    "good night",
)
CAPABILITY_DIRECT_PATTERNS = (
    "what can you do",
    "what are you able to do",
    "what can you help with",
    "what are your capabilities",
    "tell me what you can do",
)
COMMAND_REFERENCE_PATTERNS = (
    "/help",
    "/commands",
    "show commands",
    "show me commands",
    "show me all commands",
    "show me all slash commands",
    "show klaude commands",
    "show the command reference",
    "what commands are available",
    "what commands can i use",
    "available commands",
    "list klaude commands",
    "list commands",
    "command reference",
    "show help",
    "what can i type",
    "how do i use klaude",
    "how to use klaude",
    "slash commands",
    "cli usage",
)
WORKSPACE_LOCATION_PATTERNS = (
    "where am i",
    "pwd",
    "current directory",
    "current working directory",
    "working directory",
    "repo root",
    "repository root",
)


def _normalized_request_text(user_message: str) -> str:
    return " ".join(user_message.lower().strip().strip("?.!").split())


def _looks_like_public_lookup_term(user_message: str) -> bool:
    stripped = user_message.strip().strip("?.!,")
    text = stripped.lower()
    if not stripped or len(stripped) > 80:
        return False
    if _is_direct_response_request(stripped) or _is_command_reference_request(stripped):
        return False
    if any(word in text for word in ("how ", "why ", "write ", "create ", "make ")):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z0-9_.-]*", stripped)
    if not words or len(words) > 5:
        return False
    if len(words) == 1:
        return len(words[0]) >= 4
    if " and " in text and any(word[:1].isupper() for word in words):
        return True
    return any(word[:1].isupper() for word in words)


def _is_direct_response_request(user_message: str) -> bool:
    text = _normalized_request_text(user_message)
    if not text:
        return True
    if text in CASUAL_DIRECT_PATTERNS or text in CAPABILITY_DIRECT_PATTERNS:
        return True
    for pattern in CONVERSATIONAL_PREFIX_PATTERNS:
        for separator in (",", " "):
            prefix = f"{pattern}{separator}"
            if text.startswith(prefix):
                rest = text[len(prefix) :].strip(" ,")
                return _is_direct_response_request(rest)
    return any(
        text.startswith(f"{pattern},") or text.startswith(f"{pattern} ")
        for pattern in (
            set(CASUAL_DIRECT_PATTERNS) | set(CAPABILITY_DIRECT_PATTERNS)
        )
        - set(CONVERSATIONAL_PREFIX_PATTERNS)
    )


def _is_command_reference_request(user_message: str) -> bool:
    return is_complete_command_reference_request(user_message)


def _tool_use_route(user_message: str) -> ToolUseRoute:
    text = _normalized_request_text(user_message)
    if _is_command_reference_request(user_message):
        return ToolUseRoute.COMMAND_REFERENCE
    if any(word in text for word in WORKSPACE_LOCATION_PATTERNS):
        return ToolUseRoute.WORKSPACE_TOOL
    if any(word in text for word in ("time", "date", "weather", "forecast")):
        return ToolUseRoute.UTILITY_TOOL
    if any(word in text for word in ("search", "web", "latest", "current", "online")):
        return ToolUseRoute.WEB_TOOL
    if any(word in text for word in ("docs", "documentation", "knowledge", "library")):
        return ToolUseRoute.KNOWLEDGE_TOOL
    if _is_direct_response_request(user_message):
        return ToolUseRoute.DIRECT_RESPONSE
    return ToolUseRoute.HEURISTIC_TOOL_SELECTION


def _select_tool_names(user_message: str, tools: dict[str, Tool]) -> list[str]:
    text = user_message.lower()
    route = _tool_use_route(user_message)
    if route == ToolUseRoute.DIRECT_RESPONSE:
        return []
    if route == ToolUseRoute.COMMAND_REFERENCE:
        return ["list_commands"] if "list_commands" in tools else []
    if route == ToolUseRoute.WORKSPACE_TOOL:
        return ["workspace_info"] if "workspace_info" in tools else []
    selected: list[str] = []

    def add(*names: str) -> None:
        for name in names:
            if name in tools and name not in selected:
                selected.append(name)

    memory_words = (
        "remember",
        "forget",
        "previous session",
        "past session",
        "last session",
        "did i ask",
        "have i asked",
        "what did we discuss",
        "what did i say",
        "do you remember",
    )
    if any(word in text for word in memory_words):
        add("search_sessions", "list_recent_sessions", "remember_fact")

    huggingface_words = ("hugging face", "huggingface", "model card", "dataset", "space")
    if any(word in text for word in huggingface_words):
        add("huggingface_search", "huggingface_details", "huggingface_readme")

    search_words = (
        "web",
        "internet",
        "online",
        "look up",
        "lookup",
        "search",
        "current",
        "latest",
        "url",
        "http",
        "result",
        "results",
        "source",
        "sources",
        "link",
        "links",
    )
    if any(word in text for word in search_words):
        add("web_search", "fetch_url")

    if not selected and _looks_like_public_lookup_term(user_message):
        add("search_sessions", "query_knowledge", "web_search", "fetch_url")

    if any(word in text for word in ("today", "date", "time", "day is", "what day")):
        add("current_time")

    weather_words = (
        "weather",
        "forecast",
        "temperature",
        "hottest",
        "coldest",
        "rain",
        "humidity",
    )
    if any(word in text for word in weather_words):
        add("current_time", "weather_lookup", "web_search")

    workspace_location_words = (
        "where am i",
        "where am i?",
        "pwd",
        "current directory",
        "current working directory",
        "working directory",
        "repo root",
        "repository root",
    )
    if any(word in text for word in workspace_location_words):
        add("workspace_info")

    evidence_words = (
        "channel",
        "creator",
        "fortnite",
        "game",
        "games",
        "gamer",
        "gaming",
        "hypixel",
        "minecraft",
        "play",
        "played",
        "plays",
        "roblox",
        "stream",
        "streams",
        "streamer",
        "tiktok",
        "twitch",
        "video",
        "videos",
        "valorant",
        "youtube",
    )
    if any(word in text for word in evidence_words):
        add("query_knowledge", "web_search", "fetch_url")

    capability_words = (
        "command",
        "commands",
        "slash",
        "/help",
        "/model",
        "who might you be",
        "what can you do",
        "what are all the things you can do",
        "things you can do",
        "all the things you can do",
        "capabilities",
    )
    if any(word in text for word in capability_words):
        add("list_commands")

    if "feature" in text or "features" in text:
        add("query_knowledge", "code_search", "web_search")

    crawl_words = ("crawl", "crawler", "crawl4ai", "scrape", "site map", "sitemap")
    if any(word in text for word in crawl_words):
        add("crawl_site", "fetch_url", "web_search")

    knowledge_words = (
        "docs",
        "documentation",
        "knowledge",
        "library",
        "framework",
        "api",
        "example",
        "snippet",
        "godot",
        "react",
        "next.js",
        "nextjs",
        "pydantic",
        "typescript",
        "python",
        "laravel",
    )
    if any(word in text for word in knowledge_words):
        add("query_knowledge", "code_search", "web_search", "fetch_url")

    workspace_words = (
        "file",
        "repo",
        "project",
        "bug",
        "fix",
        "edit",
        "implement",
        "test",
        "run",
        "commit",
        "diff",
        "git",
        "directory",
        "folder",
        "workspace",
        "pwd",
    )
    if any(word in text for word in workspace_words):
        add(
            "read_file",
            "list_dir",
            "workspace_info",
            "grep",
            "git_status",
            "git_diff",
            "write_file",
            "edit_file",
            "run_shell",
            "git_commit",
            "query_knowledge",
            "code_search",
        )

    followup_lookup = (
        "more about",
        "tell me more",
        "more info",
        "more information",
        "find more",
        "look into",
        "research more",
    )
    if not selected and any(word in text for word in followup_lookup):
        add("query_knowledge", "web_search", "fetch_url")

    local_entity_words = (
        "school",
        "academy",
        "college",
        "university",
        "campus",
        "institution",
        "business",
        "company",
        "organization",
        "cambodia",
        "phnom penh",
    )
    if not selected and any(word in text for word in local_entity_words):
        add("search_sessions", "query_knowledge", "web_search", "fetch_url")

    lookup_starters = (
        "how do",
        "where is",
        "where are",
        "who is",
        "who are",
        "what is",
        "what are",
        "when is",
        "when was",
        "why is",
    )
    if not selected and any(word in text for word in lookup_starters):
        add("search_sessions", "query_knowledge", "web_search", "fetch_url")

    return selected[:14]


def _crawl_source_name(start_url: str, library: str, name: str = "") -> str:
    if name:
        return name
    if library:
        return library
    return start_url


def _crawl_and_install(
    cfg,
    start_url: str,
    library: str,
    *,
    name: str = "",
    max_depth: int | None = None,
    max_pages: int | None = None,
    pattern: str = "*",
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    use_sitemap: bool = False,
    respect_robots: bool | None = None,
    delay_min: float | None = None,
    delay_max: float | None = None,
    on_progress=None,
):
    from klaude_knowledge import Knowledge, install_crawl_source
    from klaude_web import Web

    web = Web(cfg)
    effective_max_depth = cfg.crawl_max_depth if max_depth is None else max_depth
    effective_max_pages = cfg.crawl_max_pages if max_pages is None else max_pages
    effective_respect_robots = (
        cfg.crawl_respect_robots if respect_robots is None else respect_robots
    )
    effective_delay_min = cfg.crawl_delay_min if delay_min is None else delay_min
    effective_delay_max = cfg.crawl_delay_max if delay_max is None else delay_max

    crawled = web.crawl_site(
        start_url,
        max_depth=effective_max_depth,
        max_pages=effective_max_pages,
        pattern=pattern,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        use_sitemap=use_sitemap,
        respect_robots=effective_respect_robots,
        delay_min=effective_delay_min,
        delay_max=effective_delay_max,
        on_progress=on_progress,
    )
    if not crawled["pages"]:
        raise RuntimeError(
            f"crawl found no indexable pages from {start_url}; "
            f"errors={len(crawled['errors'])}, skipped={len(crawled['skipped'])}"
        )

    options = {
        "max_depth": effective_max_depth,
        "max_pages": effective_max_pages,
        "pattern": pattern,
        "include_patterns": include_patterns or [],
        "exclude_patterns": exclude_patterns or [],
        "use_sitemap": use_sitemap,
        "respect_robots": effective_respect_robots,
        "delay_min": effective_delay_min,
        "delay_max": effective_delay_max,
    }
    installed = install_crawl_source(
        cfg,
        _crawl_source_name(start_url, library, name),
        library,
        start_url,
        crawled["pages"],
        errors=crawled["errors"],
        skipped=crawled["skipped"],
        seeded=crawled["seeded"],
        options=options,
    )
    total = _index_installed_docs(installed, Knowledge(cfg))
    return installed, total, crawled


def _crawl_tool_result(
    cfg,
    url: str,
    library: str = "",
    collection: str = "",
    name: str = "",
    max_depth: int | None = None,
    max_pages: int | None = None,
    pattern: str = "*",
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
    use_sitemap: bool = False,
) -> str:
    target_library = library or collection
    if not target_library:
        return "error: provide a library name"
    installed, total, crawled = _crawl_and_install(
        cfg,
        url,
        target_library,
        name=name,
        max_depth=max_depth,
        max_pages=max_pages,
        pattern=pattern,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        use_sitemap=use_sitemap,
    )
    return (
        f"crawled {len(crawled['pages'])} pages from {url}; "
        f"learned {total} chunks into library '{installed.library}'; "
        f"errors={len(crawled['errors'])}, skipped={len(crawled['skipped'])}; "
        f"manifest={installed.manifest_path}"
    )


def _summarize_recent_memory(agent: Agent, memory: Memory, session_id: str, request: str) -> str:
    turns = memory.session_tail(session_id, limit=10)
    if not turns:
        return ""
    context = "\n".join(
        f"{turn['role']}: {str(turn['content'])[:1000]}" for turn in turns
    )
    prompt = (
        "Summarize the durable memory the user likely wants saved.\n"
        "Return one concise sentence only. Do not include secrets, API key values, "
        "passwords, or temporary debugging details.\n\n"
        f"User request: {request}\n\nRecent conversation:\n{context}"
    )
    try:
        msg = agent.ollama.chat(
            agent.model,
            [
                {"role": "system", "content": "You distill safe durable memories."},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception:
        return ""
    fact = " ".join(str(msg.get("content", "")).strip().split())
    if not fact or is_sensitive_memory(fact):
        return ""
    return fact[:500].rstrip(" .")


def _current_time(timezone: str = "Asia/Phnom_Penh") -> str:
    try:
        tz = ZoneInfo(timezone)
    except Exception:
        tz = ZoneInfo("Asia/Phnom_Penh")
        timezone = "Asia/Phnom_Penh"
    now = datetime.now(tz)
    return now.strftime(f"%A, %B %d, %Y, %H:%M %Z ({timezone})")


def _format_weather_day(day: dict) -> str:
    date = day.get("date", "?")
    avg = day.get("avgtempC", "?")
    high = day.get("maxtempC", "?")
    low = day.get("mintempC", "?")
    hourly = day.get("hourly") or []
    desc = ""
    if hourly:
        desc = (hourly[len(hourly) // 2].get("weatherDesc") or [{}])[0].get("value", "")
    return f"{date}: {desc}; avg {avg}C, high {high}C, low {low}C"


def _weather_lookup(location: str = "Phnom Penh, Cambodia", days: int = 3) -> str:
    days = max(1, min(int(days or 3), 5))
    response = httpx.get(
        f"https://wttr.in/{location}",
        params={"format": "j1"},
        timeout=20,
        follow_redirects=True,
    )
    response.raise_for_status()
    data = response.json()
    current = (data.get("current_condition") or [{}])[0]
    nearest = (data.get("nearest_area") or [{}])[0]
    area = (nearest.get("areaName") or [{}])[0].get("value", location)
    country = (nearest.get("country") or [{}])[0].get("value", "")
    weather = (current.get("weatherDesc") or [{}])[0].get("value", "")
    lines = [
        f"Location: {area}{', ' + country if country else ''}",
        (
            f"Now: {weather}; {current.get('temp_C', '?')}C "
            f"(feels {current.get('FeelsLikeC', '?')}C), "
            f"humidity {current.get('humidity', '?')}%, "
            f"wind {current.get('windspeedKmph', '?')} km/h"
        ),
        "Forecast:",
    ]
    lines.extend(_format_weather_day(day) for day in data.get("weather", [])[:days])
    return "\n".join(lines)


def _build_agent(workdir: Path, model: str | None = None) -> tuple[Agent, object]:
    from klaude_knowledge import Knowledge
    from klaude_tools import Workspace, build_tools
    from klaude_web import Web

    cfg = load_config()
    ollama = Ollama(cfg.ollama_url)
    memory = Memory(cfg.memory_file, cfg.sessions_db)
    ws = Workspace(workdir)
    tools = build_tools(ws)

    runtime_result = _runtime_context_result(cfg, workdir)
    _apply_runtime_context_to_search_config(cfg, runtime_result)
    web = Web(cfg)
    kn = Knowledge(cfg, ollama)
    runtime_text = render_runtime_context(runtime_result.context, cfg) if runtime_result else ""
    S = {"type": "string"}
    tools += [
        Tool(
            "current_time",
            "Get the current local date and time for a timezone. Default is Cambodia.",
            {"type": "object", "properties": {"timezone": S}, "required": []},
            lambda timezone="Asia/Phnom_Penh": _current_time(timezone),
        ),
        Tool(
            "weather_lookup",
            WEATHER_TOOL_DESCRIPTION,
            {
                "type": "object",
                "properties": {"location": S, "days": {"type": "integer"}},
                "required": [],
            },
            lambda location="Phnom Penh, Cambodia", days=3: _weather_lookup(location, days),
        ),
        Tool(
            "web_search",
            "Search the web through the configured provider. "
            "Use for current info not in local knowledge.",
            {
                "type": "object",
                "properties": {
                    "query": S,
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
            lambda query, max_results=12: _web_search_tool_result(web, query, max_results),
            start_metadata=lambda args: _web_search_start_metadata(
                web,
                str(args.get("query", "")),
                _bounded_result_count(args.get("max_results", 12), 12),
            ),
        ),
        Tool(
            "fetch_url",
            "Fetch a web page as markdown.",
            {"type": "object", "properties": {"url": S}, "required": ["url"]},
            lambda url: _fetch_url_tool_result(web, url),
        ),
        Tool(
            "list_commands",
            LIST_COMMANDS_TOOL_DESCRIPTION,
            {"type": "object", "properties": {}, "required": []},
            lambda: _command_reference_result(width=console.width),
            return_direct=True,
        ),
        Tool(
            "crawl_site",
            "Politely crawl same-domain documentation pages and store them in a knowledge library. "
            "Use only when the user asks to crawl or ingest multiple pages.",
            {
                "type": "object",
                "properties": {
                    "url": S,
                    "library": S,
                    "collection": S,
                    "name": S,
                    "max_depth": {"type": "integer"},
                    "max_pages": {"type": "integer"},
                    "pattern": S,
                    "include_patterns": {"type": "array", "items": S},
                    "exclude_patterns": {"type": "array", "items": S},
                    "use_sitemap": {"type": "boolean"},
                },
                "required": ["url"],
            },
            lambda url, library="", collection="", name="", max_depth=None,
            max_pages=None, pattern="*", include_patterns=None,
            exclude_patterns=None, use_sitemap=False: _crawl_tool_result(
                cfg,
                url,
                library,
                collection=collection,
                name=name,
                max_depth=max_depth,
                max_pages=max_pages,
                pattern=pattern,
                include_patterns=include_patterns,
                exclude_patterns=exclude_patterns,
                use_sitemap=use_sitemap,
            ),
        ),
        Tool(
            "code_search",
            "Search programming docs, code examples, and debugging references.",
            {
                "type": "object",
                "properties": {
                    "query": S,
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
            lambda query, max_results=10: _format_web_results(
                web.code_search(query, _bounded_result_count(max_results, 10)),
                _bounded_result_count(max_results, 10),
            ),
        ),
        Tool(
            "huggingface_search",
            "Search Hugging Face Hub models, datasets, or Spaces.",
            {
                "type": "object",
                "properties": {"repo_type": S, "type": S, "kind": S, "query": S},
                "required": [],
            },
            lambda repo_type="", type="", kind="", query="": "\n\n".join(
                f"{r['id']}\n{r['url']}\nlikes={r['likes']} downloads={r['downloads']}\n"
                f"{r['summary']}"
                for r in web.huggingface_search(repo_type or type or kind or "model", query)
            ) or "(no results)",
        ),
        Tool(
            "huggingface_details",
            "Get Hugging Face Hub metadata for a model, dataset, or Space.",
            {
                "type": "object",
                "properties": {"repo_type": S, "type": S, "kind": S, "repo_id": S, "id": S},
                "required": [],
            },
            lambda repo_type="", type="", kind="", repo_id="", id="": (
                json.dumps(
                    web.huggingface_details(repo_type or type or kind or "model", repo_id or id),
                    ensure_ascii=False,
                    indent=2,
                )[:15_000]
                if repo_id or id
                else "error: provide a Hugging Face repo_id"
            ),
        ),
        Tool(
            "huggingface_readme",
            "Fetch a Hugging Face model card, dataset card, or Space README as markdown.",
            {
                "type": "object",
                "properties": {"repo_type": S, "type": S, "kind": S, "repo_id": S, "id": S},
                "required": [],
            },
            lambda repo_type="", type="", kind="", repo_id="", id="": (
                web.huggingface_readme(
                    repo_type or type or kind or "model",
                    repo_id or id,
                )[:15_000]
                if repo_id or id
                else "error: provide a Hugging Face repo_id"
            ),
        ),
        Tool(
            "query_knowledge",
            "Search the local docs knowledge base (learned documentation). "
            "Always try this before web_search for library/framework questions.",
            {
                "type": "object",
                "properties": {"question": S, "query": S, "library": S, "collection": S},
                "required": [],
            },
            lambda question="", query="", library="", collection="": (
                _query_knowledge_tool_result(
                    kn,
                    question or query,
                    library,
                    collection,
                    cfg.retrieval_k,
                )
                if question or query
                else "error: provide a question or query"
            ),
        ),
        Tool(
            "search_sessions",
            "Search prior Klaude conversation sessions. "
            "Use when the user asks what they said before.",
            {"type": "object", "properties": {"query": S, "question": S}, "required": []},
            lambda query="", question="": _format_session_hits(
                memory.search_sessions(query or question)
            ),
        ),
        Tool(
            "list_recent_sessions",
            "List recent Klaude conversation sessions with short previews.",
            {"type": "object", "properties": {}, "required": []},
            lambda: _format_recent_sessions(memory.recent_sessions()),
        ),
        Tool(
            "remember_fact",
            "Save a concise durable memory after the user clearly asked you to remember it.",
            {"type": "object", "properties": {"fact": S}, "required": ["fact"]},
            lambda fact: (
                f"saved memory: {fact}"
                if memory.remember(fact, source="tool")
                else "memory was not saved (duplicate, empty, or sensitive)"
            ),
        ),
    ]

    gate = PermissionGate(cfg.permissions, _ask_permission)
    agent = Agent(
        ollama,
        model or cfg.models["coder"],
        tools,
        gate,
        _system_prompt(memory, runtime_text),
        max_steps=cfg.max_agent_steps,
        tool_selector=_select_tool_names,
    )
    def refreshed_system_prompt() -> str:
        refreshed_runtime = _runtime_context_result(cfg, workdir)
        _apply_runtime_context_to_search_config(cfg, refreshed_runtime)
        refreshed_text = (
            render_runtime_context(refreshed_runtime.context, cfg)
            if refreshed_runtime
            else ""
        )
        return _system_prompt(memory, refreshed_text)

    agent.set_system_prompt_builder = refreshed_system_prompt
    _maybe_show_runtime_context_note(runtime_result)
    branch_note = ws.ensure_work_branch(time.strftime("%Y%m%d-%H%M"))
    console.print(f"[dim]{branch_note}[/]")
    return agent, memory


def _print_preformatted_text(content: str) -> None:
    console.print(Text(content), overflow="fold")


def _print_assistant_text(content: str, metadata: dict | None = None) -> None:
    metadata = metadata or {}
    if (
        metadata.get("preserve_whitespace")
        or metadata.get("content_type") == "command_reference"
        or content.startswith("Usage: klaude [OPTIONS]")
    ):
        _print_preformatted_text(content)
        return
    console.print(Markdown(content))


def _record_direct_command_context(
    user_msg: str,
    context: str,
    *,
    agent: Agent | None = None,
    memory: Memory | None = None,
    session_id: str | None = None,
) -> None:
    if agent is not None:
        agent.messages.append({"role": "user", "content": user_msg})
        agent.messages.append({"role": "assistant", "content": context})
    if memory is not None and session_id is not None:
        memory.log_turn(session_id, "user", user_msg)
        memory.log_turn(session_id, "assistant", context)


def _handle_command_reference_request(
    user_msg: str,
    agent: Agent | None = None,
    memory: Memory | None = None,
    session_id: str | None = None,
) -> bool:
    if _is_command_reference_request(user_msg):
        response = format_command_reference(width=console.width)
        context = _command_reference_context()
        show_trace = True
    else:
        focused = format_focused_command_help(user_msg, width=console.width)
        if focused is None:
            return False
        response = focused
        context = focused
        show_trace = False

    _record_direct_command_context(
        user_msg,
        context,
        agent=agent,
        memory=memory,
        session_id=session_id,
    )
    if show_trace:
        _print_trace("-> command_reference [local]")
    _print_preformatted_text(response)
    return True


def _render(agent: Agent, memory: Memory, session_id: str, user_msg: str) -> str:
    builder = getattr(agent, "set_system_prompt_builder", None)
    if builder:
        agent.set_system_prompt(builder())
    memory.log_turn(session_id, "user", user_msg)
    assistant_text: list[str] = []
    pending_tool_start_metadata: dict[str, dict] = {}
    for event in agent.run(user_msg):
        if event.kind == "text" and event.payload.get("content"):
            _print_assistant_text(
                event.payload["content"],
                event.payload.get("metadata") or {},
            )
            memory.log_turn(session_id, "assistant", event.payload["content"])
            assistant_text.append(event.payload["content"])
        elif event.kind == "tool_start":
            if event.payload["tool"] == "web_search":
                pending_tool_start_metadata["web_search"] = event.payload.get("metadata") or {}
            if event.payload["tool"] not in {"web_search", "list_commands", "query_knowledge"}:
                _print_trace(f"-> {event.payload['tool']}")
        elif event.kind == "tool_result":
            if (event.payload.get("metadata") or {}).get("suppress_user_output"):
                continue
            if event.payload.get("tool") == "web_search":
                metadata = {
                    **pending_tool_start_metadata.pop("web_search", {}),
                    **(event.payload.get("metadata") or {}),
                }
                for line in _web_search_display_lines(
                    metadata,
                    event.payload["result"],
                ):
                    _print_trace(line)
                continue
            if event.payload.get("tool") == "query_knowledge":
                for line in _query_knowledge_display_lines(
                    event.payload.get("metadata") or {},
                    event.payload["result"],
                ):
                    _print_trace(line)
                continue
            preview = event.payload["result"][:200].replace("\n", " ")
            _print_trace(f"   {preview}")
        elif event.kind == "error":
            console.print(f"[red]error: {event.payload['message']}[/]")
    return "\n\n".join(assistant_text)


def _handle_explicit_memory_request(
    user_msg: str,
    agent: Agent,
    memory: Memory,
    session_id: str,
) -> bool:
    candidate = explicit_memory_candidate(user_msg)
    if not candidate:
        return False

    fact, needs_confirmation = candidate
    if needs_confirmation:
        fact = _summarize_recent_memory(agent, memory, session_id, user_msg)
        if not fact:
            console.print(
                "[yellow]I need the exact memory to save. Try: "
                "remember that <short durable fact>[/]"
            )
            return True
        answer = console.input(f"[yellow]Save memory?[/]\n{fact}\n[y/N/edit]: ").strip()
        if answer.lower().startswith("e"):
            fact = console.input("[yellow]memory>[/] ").strip()
        elif not answer.lower().startswith("y"):
            console.print("[dim]memory not saved[/]")
            return True

    saved = memory.remember(fact, source="manual")
    console.print("[green]saved to memory[/]" if saved else "[dim]memory not saved[/]")
    return True


def _learn_source_if_changed(cfg, source: str, library: str) -> tuple[str, int]:
    from klaude_knowledge import Knowledge
    from klaude_web import Web

    kn = Knowledge(cfg)
    if source.startswith(("http://", "https://")):
        console.print(f"[dim]fetching {source}...[/]")
        text = Web(cfg).fetch(source)
        source_id = source
        title = ""
    else:
        path = Path(source)
        text = path.read_text()
        source_id = str(path)
        title = path.stem

    if kn.source_is_current(library, text, source_id):
        return "unchanged", 0
    return "updated", kn.learn_text(library, text, source=source_id, title=title)


def _online_docs_file() -> Path:
    override = os.environ.get("KLAUDE_ONLINE_DOCS_FILE")
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parents[4] / "online-docs.txt"


def _iter_online_docs_entries(path: Path) -> list[tuple[str, str, str]]:
    entries = []
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            continue
        if (
            len(parts) == 7
            and parts[:4] == ["uv", "run", "klaude", "learn"]
            and parts[5] in {"-c", "--collection", "-l", "--library"}
        ):
            entries.append((parts[4], parts[6], line))
    return entries


def _update_online_docs(cfg) -> tuple[int, int, int, list[tuple[str, str, str]]]:
    path = _online_docs_file()
    if not path.exists():
        raise FileNotFoundError(f"online docs list not found: {path}")
    total = updated = unchanged = 0
    failed: list[tuple[str, str, str]] = []
    for source, library, _line in _iter_online_docs_entries(path):
        total += 1
        console.print("────────────────────────────────────────────────────────────")
        console.print(f"[{total}] {library}")
        console.print(f"Source: {source}\n")
        try:
            status, chunks = _learn_source_if_changed(cfg, source, library)
        except Exception as exc:
            failed.append((library, source, str(exc)))
            console.print(f"[red]failed:[/] {exc}\n")
            continue
        if status == "unchanged":
            unchanged += 1
            console.print(f"[dim]unchanged; skipped indexing for library '{library}'[/]\n")
        else:
            updated += 1
            console.print(f"[green]learned {chunks} chunks into library '{library}'[/]\n")
    return total, updated, unchanged, failed


def _print_online_docs_summary(
    total: int,
    updated: int,
    unchanged: int,
    failed: list[tuple[str, str, str]],
) -> None:
    console.print("============================================================")
    console.print("Online documentation summary")
    console.print("============================================================")
    console.print(f"Processed: {total}")
    console.print(f"Updated:   {updated}")
    console.print(f"Unchanged: {unchanged}")
    console.print(f"Failed:    {len(failed)}")
    if failed:
        console.print("\n[yellow]Failed sources:[/]")
        for library, source, error in failed:
            console.print(f"  {library}: {source}\n    {error}")


def _update_managed_docs_sources(cfg, targets: list[str], max_pages: int) -> None:
    from klaude_knowledge import Knowledge, update_docs_source
    from klaude_web import Web

    web = Web(cfg)
    kn = Knowledge(cfg)
    for target in targets:
        console.print(f"[dim]updating docs source {target}...[/]")
        installed = update_docs_source(
            cfg,
            target,
            web.fetch,
            max_pages=None if max_pages < 0 else max_pages,
            crawler=web.crawl_site,
        )
        total = _index_installed_docs(installed, kn)
        snapshot = f"; snapshot {installed.snapshot}" if installed.snapshot else ""
        console.print(
            f"[green]{installed.name}[/]: learned {total} chunks into "
            f"library '{installed.library}' from {len(installed.files)} files{snapshot}"
        )


def _resolve_model(ollama: Ollama, name: str) -> str | None:
    """Match a user-typed name against installed models (exact, then prefix,
    then substring). Returns the full model name or None."""
    installed = ollama.list_models()
    if name in installed:
        return name
    prefix = [m for m in installed if m.startswith(name)]
    if len(prefix) == 1:
        return prefix[0]
    sub = [m for m in installed if name.lower() in m.lower()]
    if len(sub) == 1:
        return sub[0]
    return None


@app.command()
def chat(model: str = typer.Option("", help="override the coder model")):
    """Interactive agent session in the current directory."""
    agent, memory = _build_agent(Path.cwd(), model or None)
    session_id = str(uuid.uuid4())[:8]
    console.print(
        f"[bold]klaude[/] [dim]({agent.model})[/] — type your task; "
        "/help lists commands, /models lists, /model NAME switches, /quit exits\n"
    )
    while True:
        try:
            user_msg = console.input("[bold cyan]you>[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_msg:
            continue
        if user_msg in {"/quit", "/exit", "/q"}:
            break
        if user_msg in {"/help", "/commands"}:
            _handle_command_reference_request(user_msg, agent, memory, session_id)
            continue
        if user_msg == "/models":
            for m in agent.ollama.list_models():
                marker = " [green]<- active[/]" if m == agent.model else ""
                console.print(f"  {m}{marker}")
            continue
        if user_msg.startswith("/model"):
            target = user_msg.removeprefix("/model").strip()
            if not target:
                console.print(f"active model: [bold]{agent.model}[/]")
                continue
            resolved = _resolve_model(agent.ollama, target)
            if resolved:
                agent.model = resolved
                console.print(f"[green]switched to {resolved}[/] [dim](history kept)[/]")
            else:
                console.print(
                    f"[red]no unique match for '{target}'[/] — see /models"
                )
            continue
        if _handle_unknown_slash_command(
            user_msg,
            agent=agent,
            memory=memory,
            session_id=session_id,
        ):
            continue
        if _handle_command_reference_request(user_msg, agent, memory, session_id):
            continue
        if _handle_explicit_memory_request(user_msg, agent, memory, session_id):
            continue
        _render(agent, memory, session_id, user_msg)
        for fact in memory.auto_remember_turn(user_msg):
            console.print(f"[dim]memory saved: {fact}[/]")
    console.print("[dim]bye[/]")


@app.command()
def ask(question: str, model: str = typer.Option("", help="override model")):
    """One-shot question with tools enabled."""
    agent, memory = _build_agent(Path.cwd(), model or None)
    session_id = str(uuid.uuid4())[:8]
    if _handle_unknown_slash_command(
        question,
        agent=agent,
        memory=memory,
        session_id=session_id,
    ):
        return
    if _handle_command_reference_request(question, agent, memory, session_id):
        return
    if not _handle_explicit_memory_request(question, agent, memory, session_id):
        _render(agent, memory, session_id, question)
        for fact in memory.auto_remember_turn(question):
            console.print(f"[dim]memory saved: {fact}[/]")


@app.command()
def learn(
    source: str,
    library: str = typer.Option(
        ...,
        "-l",
        "--library",
        "-c",
        "--collection",
        help="library name",
    ),
):
    """Ingest a URL or local file into the knowledge base."""
    cfg = load_config()
    status, chunks = _learn_source_if_changed(cfg, source, library)
    if status == "unchanged":
        console.print(f"[dim]unchanged; skipped indexing for library '{library}'[/]")
    else:
        console.print(f"[green]learned {chunks} chunks into library '{library}'[/]")


@app.command()
def crawl(
    url: str,
    library: str = typer.Option(
        ...,
        "-l",
        "--library",
        "-c",
        "--collection",
        help="library name",
    ),
    name: str = typer.Option("", "--name", help="docs source name; defaults to the library"),
    max_depth: int = typer.Option(-1, "--max-depth", help="link depth; default from config"),
    max_pages: int = typer.Option(-1, "--max-pages", help="page cap; default from config"),
    pattern: str = typer.Option("*", "--pattern", help="fnmatch URL pattern to include"),
    include: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--include",
        help="repeatable fnmatch URL/path include pattern",
    ),
    exclude: list[str] | None = typer.Option(  # noqa: B008
        None,
        "--exclude",
        help="repeatable fnmatch URL/path exclude pattern",
    ),
    use_sitemap: bool = typer.Option(
        False,
        "--sitemap",
        help="seed URLs from robots.txt Sitemap entries and /sitemap.xml",
    ),
    respect_robots: bool | None = typer.Option(
        None,
        "--respect-robots/--ignore-robots",
        help="honor robots.txt before fetching pages; default from config",
    ),
    delay_min: float = typer.Option(-1.0, "--delay-min", help="minimum seconds between pages"),
    delay_max: float = typer.Option(-1.0, "--delay-max", help="maximum seconds between pages"),
):
    """Politely crawl same-domain pages and index them into a knowledge library."""
    cfg = load_config()
    effective_respect_robots = (
        cfg.crawl_respect_robots if respect_robots is None else respect_robots
    )

    def show_progress(event: dict) -> None:
        if event["event"] == "indexed":
            console.print(f"[dim]indexed {event['pages']}: {event['url']}[/]")
        elif event["event"] == "skipped":
            console.print(f"[dim]skipped {event['reason']}: {event['url']}[/]")

    console.print(
        f"[dim]crawling {url} into library '{library}' "
        f"(same-domain, robots {'on' if effective_respect_robots else 'off'}, "
        f"sitemap {'on' if use_sitemap else 'off'})...[/]"
    )
    try:
        installed, total, crawled = _crawl_and_install(
            cfg,
            url,
            library,
            name=name,
            max_depth=None if max_depth < 0 else max_depth,
            max_pages=None if max_pages < 0 else max_pages,
            pattern=pattern,
            include_patterns=include,
            exclude_patterns=exclude,
            use_sitemap=use_sitemap,
            respect_robots=effective_respect_robots,
            delay_min=None if delay_min < 0 else delay_min,
            delay_max=None if delay_max < 0 else delay_max,
            on_progress=show_progress,
        )
    except Exception as exc:
        console.print(f"[red]crawl failed:[/] {exc}")
        raise typer.Exit(1) from exc
    console.print(
        f"[green]installed crawl source '{installed.name}'[/] at {installed.current_dir}\n"
        f"[green]learned {total} chunks into library '{installed.library}'[/] "
        f"from {len(crawled['pages'])} pages"
    )
    if crawled["errors"]:
        console.print(f"[yellow]errors: {len(crawled['errors'])}[/]")
    if crawled["skipped"]:
        console.print(f"[dim]skipped: {len(crawled['skipped'])}[/]")
    if crawled["seeded"]:
        console.print(f"[dim]sitemap seeded: {len(crawled['seeded'])} URLs[/]")
    if installed.snapshot:
        snapshot_path = installed.root / "snapshots" / installed.snapshot
        console.print(f"[dim]snapshot saved: {snapshot_path}[/]")
    console.print(f"[dim]manifest: {installed.manifest_path}[/]")


def _index_installed_docs(installed, kn) -> int:
    from klaude_knowledge import IndexDocument, finalize_docs_source

    documents = []
    for path, source_url in zip(installed.files, installed.source_urls, strict=False):
        rel = path.relative_to(installed.current_dir).as_posix()
        documents.append(
            IndexDocument(
                source=source_url,
                text=path.read_text(errors="replace"),
                title=rel,
            )
        )
    total = kn.replace_owner_snapshot_atomic(
        installed.library,
        f"docs:{installed.name}",
        documents,
    )
    finalize_docs_source(installed)
    return total


@docs_app.callback(invoke_without_command=True)
def docs_root(ctx: typer.Context):
    """Manage refreshable documentation sources."""
    if ctx.invoked_subcommand is None:
        docs_list()


@docs_app.command("add")
def docs_add(
    name: str,
    llms_url: str,
    library: str = typer.Option(
        "",
        "-l",
        "--library",
        "-c",
        "--collection",
        help="library name; defaults to the docs source name",
    ),
    max_pages: int = typer.Option(200, "--max-pages", help="maximum linked docs to fetch"),
):
    """Install a refreshable llms.txt documentation source."""
    from klaude_knowledge import Knowledge, install_docs_source
    from klaude_web import Web

    cfg = load_config()
    web = Web(cfg)
    console.print(f"[dim]fetching docs source {llms_url}...[/]")
    installed = install_docs_source(
        cfg,
        llms_url,
        web.fetch,
        name=name,
        library=library,
        max_pages=max_pages,
    )
    total = _index_installed_docs(installed, Knowledge(cfg))
    console.print(
        f"[green]installed docs '{installed.name}'[/] at {installed.current_dir}\n"
        f"[green]learned {total} chunks into library '{installed.library}'[/] "
        f"from {len(installed.files)} files"
    )
    if installed.warnings:
        console.print(f"[yellow]warnings: {len(installed.warnings)} linked pages failed[/]")
    if installed.snapshot:
        snapshot_path = installed.root / "snapshots" / installed.snapshot
        console.print(f"[dim]snapshot saved: {snapshot_path}[/]")
    console.print(f"[dim]manifest: {installed.manifest_path}[/]")


@docs_app.command("update")
def docs_update(
    name: str = typer.Argument("", help="docs source name; omit when using --sources or --all"),
    sources: bool = typer.Option(False, "--sources", help="update every installed docs source"),
    all_sources: bool = typer.Option(
        False,
        "--all",
        help="update installed docs sources and online-docs.txt",
    ),
    online_docs: bool = typer.Option(
        False,
        "--online",
        "--online-docs",
        help="update sources listed in online-docs.txt",
    ),
    max_pages: int = typer.Option(-1, "--max-pages", help="page cap; default per source"),
):
    """Refresh installed documentation, snapshotting the old current files first."""
    from klaude_knowledge import list_docs_sources

    cfg = load_config()
    update_online = online_docs or all_sources
    update_sources = sources or all_sources or bool(name)

    if update_online:
        total, updated, unchanged, failed = _update_online_docs(cfg)
        _print_online_docs_summary(total, updated, unchanged, failed)
        if failed:
            raise typer.Exit(1)

    if not update_sources:
        return

    targets = [s["name"] for s in list_docs_sources(cfg)] if (sources or all_sources) else [name]
    targets = [t for t in targets if t]
    if not targets:
        if sources or all_sources:
            console.print(
                "[yellow]no refreshable docs sources installed[/]\n"
                "Use `klaude docs add ...` / `klaude crawl ...` for managed docs "
                "sources, or run `klaude docs update --online` for online-docs.txt."
            )
        else:
            console.print(
                "[red]provide a docs source name, use --sources for managed docs, "
                "--online for online-docs.txt, or --all for both[/]"
            )
        raise typer.Exit(1)
    _update_managed_docs_sources(cfg, targets, max_pages)


@docs_app.command("list")
def docs_list():
    """List installed refreshable documentation sources."""
    from klaude_knowledge import list_docs_sources

    sources = list_docs_sources(load_config())
    if not sources:
        console.print("[dim](none yet)[/]")
        return
    for source in sources:
        source_url = source.get("llms_url") or source.get("start_url") or ""
        kind = source.get("kind", "llms")
        console.print(
            f"[bold]{source.get('name', '?')}[/] -> library "
            f"[cyan]{source.get('library', '?')}[/] "
            f"({len(source.get('files', []))} files, {kind})\n"
            f"[blue]{source_url}[/]"
        )


@app.command("import-skill")
def import_skill(
    source: str,
    library: str = typer.Option(
        "",
        "-l",
        "--library",
        "-c",
        "--collection",
        help="library name; defaults to the skill name",
    ),
    name: str = typer.Option("", "--name", help="installed skill name"),
):
    """Install a skill ZIP/folder and index its text into a knowledge library."""
    from klaude_knowledge import (
        IndexDocument,
        Knowledge,
        finalize_skill_package,
        install_skill_package,
    )

    cfg = load_config()
    installed = install_skill_package(cfg, source, name=name, library=library)
    kn = Knowledge(cfg)
    documents = []
    for path, source_uri in zip(installed.text_files, installed.source_uris, strict=False):
        rel = path.relative_to(installed.current_dir).as_posix()
        documents.append(
            IndexDocument(
                source=source_uri,
                text=path.read_text(errors="replace"),
                title=rel,
            )
        )
    total = kn.replace_owner_snapshot_atomic(
        installed.library,
        f"skill:{installed.name}",
        documents,
    )
    finalize_skill_package(installed)

    console.print(
        f"[green]installed skill '{installed.name}'[/] "
        f"at {installed.current_dir}\n"
        f"[green]learned {total} chunks into library '{installed.library}'[/] "
        f"from {len(installed.text_files)} text files"
    )
    if installed.snapshot:
        snapshot_path = installed.root / "snapshots" / installed.snapshot
        console.print(f"[dim]snapshot saved: {snapshot_path}[/]")
    console.print(f"[dim]manifest: {installed.manifest_path}[/]")


@app.command()
def query(
    question: str,
    library: str = typer.Option(
        "",
        "-l",
        "--library",
        "-c",
        "--collection",
        help="library name; omit to search all",
    ),
    k: int = typer.Option(6, "-k"),
):
    """Hybrid-search the knowledge base (no LLM, raw chunks)."""
    from klaude_knowledge import Knowledge

    kn = Knowledge(load_config())
    for hit in kn.query(question, library, k):
        src = hit.get("source") or hit.get("collection", "?")
        console.print(Panel(hit["text"][:600], title=src, border_style="dim"))


def _print_libraries() -> None:
    from klaude_knowledge import Knowledge

    names = Knowledge(load_config()).store.collections()
    if not names:
        console.print("[dim](none yet)[/]")
        return
    for name in names:
        console.print(name)


@app.command()
def libraries():
    """List learned knowledge libraries."""
    _print_libraries()


@app.command("collections")
def collections_alias():
    """List learned knowledge libraries."""
    _print_libraries()


@app.command()
def skills():
    """List installed assistant skills."""
    from klaude_knowledge import list_installed_skills

    installed = list_installed_skills(load_config())
    if not installed:
        console.print("[dim](none yet)[/]")
        return
    for skill in installed:
        console.print(
            f"[bold]{skill.get('name', '?')}[/] -> library "
            f"[cyan]{skill.get('library', '?')}[/] "
            f"({len(skill.get('indexed_files', []))} files)"
        )


@app.command()
def search(q: str, n: int = typer.Option(8, "-n")):
    """Web search via the configured provider."""
    from klaude_web import Web

    cfg = load_config()
    response = Web(cfg).search_detailed(q, n)
    metadata = _search_execution_metadata(response, cfg.web_provider)
    for line in _web_search_display_lines(metadata, _format_search_response(response, n)):
        _print_trace(line)
    if not response.results:
        console.print(_format_search_response(response, n), markup=False)
        return
    for r in response.results:
        console.print(f"[bold]{r['title']}[/]\n[blue]{r['url']}[/]\n{r['snippet']}\n")
    if response.warnings:
        warning_lines = [
            f"{warning.get('provider', '')}: {warning.get('message', '')}".strip(": ")
            for warning in response.warnings
        ]
        console.print("\nWarnings:\n" + "\n".join(f"- {line}" for line in warning_lines if line))


@app.command("code-search")
def code_search(q: str, n: int = typer.Option(8, "-n")):
    """Search programming docs, code examples, and debugging references."""
    from klaude_web import Web

    for r in Web(load_config()).code_search(q, n):
        console.print(f"[bold]{r['title']}[/]\n[blue]{r['url']}[/]\n{r['snippet']}\n")


@app.command("huggingface-search")
def huggingface_search(
    repo_type: str = typer.Argument(..., help="model, dataset, or space"),
    query: str = typer.Argument("", help="search query; omit for trending repos"),
    n: int = typer.Option(10, "-n"),
    sort: str = typer.Option("downloads", "--sort"),
):
    """Search Hugging Face Hub models, datasets, or Spaces."""
    from klaude_web import Web

    for r in Web(load_config()).huggingface_search(repo_type, query, n, sort):
        console.print(
            f"[bold]{r['id']}[/]\n"
            f"[blue]{r['url']}[/]\n"
            f"likes={r['likes']} downloads={r['downloads']} "
            f"updated={r['last_modified']}\n"
            f"{r['summary']}\n"
        )


@app.command("huggingface-details")
def huggingface_details(repo_type: str, repo_id: str):
    """Print Hugging Face Hub metadata for a model, dataset, or Space."""
    from klaude_web import Web

    console.print_json(
        json.dumps(
            Web(load_config()).huggingface_details(repo_type, repo_id),
            ensure_ascii=False,
        )
    )


@app.command("huggingface-readme")
def huggingface_readme(repo_type: str, repo_id: str):
    """Fetch a Hugging Face model card, dataset card, or Space README."""
    from klaude_web import Web

    console.print(Markdown(Web(load_config()).huggingface_readme(repo_type, repo_id)))


@app.command()
def models():
    """List every model installed in Ollama and which role klaude assigns it."""
    cfg = load_config()
    ollama = Ollama(cfg.ollama_url, timeout=5)
    if not ollama.is_up():
        console.print(f"[red]ollama not reachable at {cfg.ollama_url}[/]")
        raise typer.Exit(1)
    roles = {v: k for k, v in cfg.models.items() if v}
    for m in ollama.list_models():
        role = roles.get(m) or roles.get(m.split(":")[0], "")
        tag = f"  [green]<- {role}[/]" if role else ""
        console.print(f"  {m}{tag}")
    console.print(
        "\n[dim]use any of these:  klaude chat --model NAME   or  /model NAME in chat\n"
        "make one permanent in ~/.config/klaude/config.toml under [models.override][/]"
    )


@app.command()
def remember(fact: str):
    """Append a durable fact to memory.md (goes into every system prompt)."""
    cfg = load_config()
    saved = Memory(cfg.memory_file, cfg.sessions_db).remember(fact, source="cli")
    console.print("[green]saved to memory[/]" if saved else "[dim]memory not saved[/]")


def _memory_store() -> Memory:
    cfg = load_config()
    return Memory(cfg.memory_file, cfg.sessions_db)


@memory_app.callback(invoke_without_command=True)
def memory_root(ctx: typer.Context):
    """Manage durable memory and session recall."""
    if ctx.invoked_subcommand is None:
        memory_status()


@memory_app.command("status")
def memory_status():
    """Show memory status and storage locations."""
    cfg = load_config()
    memory = Memory(cfg.memory_file, cfg.sessions_db)
    console.print(f"auto memory: {'on' if memory.auto_memory_enabled() else 'off'}")
    console.print(f"memory file: {cfg.memory_file}")
    console.print(f"sessions db: {cfg.sessions_db}")


@memory_app.command("on")
def memory_on():
    """Enable conservative automatic memory."""
    memory = _memory_store()
    memory.set_auto_memory(True)
    console.print("[green]auto memory on[/]")


@memory_app.command("off")
def memory_off():
    """Disable automatic memory."""
    memory = _memory_store()
    memory.set_auto_memory(False)
    console.print("[green]auto memory off[/]")


@memory_app.command("list")
def memory_list():
    """List durable saved memories."""
    facts = _memory_store().list_facts()
    if not facts:
        console.print("[dim](none yet)[/]")
        return
    for fact in facts:
        console.print(fact)


@memory_app.command("add")
def memory_add(fact: str):
    """Save a durable memory."""
    saved = _memory_store().remember(fact, source="cli")
    console.print("[green]saved to memory[/]" if saved else "[dim]memory not saved[/]")


@memory_app.command("forget")
def memory_forget(query: str):
    """Remove one saved memory by exact ID or exact text."""
    result = _memory_store().forget(query)
    if result.removed:
        console.print(f"[green]removed {result.removed} memory[/]")
        return
    if result.matches:
        console.print("[yellow]memory not removed; choose an exact memory ID or text:[/]")
        for entry in result.matches:
            console.print(f"  memory:{entry.id}  {entry.fact}")
        return
    console.print("[dim]removed 0 memories[/]")


@memory_app.command("search")
def memory_search(query: str, n: int = typer.Option(8, "-n")):
    """Search previous conversation sessions."""
    console.print(_format_session_hits(_memory_store().search_sessions(query, n)))


@app.command()
def sessions(n: int = typer.Option(10, "-n")):
    """List recent conversation sessions."""
    console.print(_format_recent_sessions(_memory_store().recent_sessions(n)))


@app.command("session-search")
def session_search(query: str, n: int = typer.Option(8, "-n")):
    """Search previous conversation sessions."""
    console.print(_format_session_hits(_memory_store().search_sessions(query, n)))


def _runtime_status_summary(cfg, workdir: Path) -> tuple[str, str, str, object | None]:
    if not cfg.runtime_context_enabled or cfg.runtime_context_provider == "off":
        return "off", "system context disabled", "off", None
    result = _runtime_context_result(cfg, workdir)
    if not result:
        return "error", "collection failed", "unknown", None
    context = result.context
    collected = context.stable_collected_at or context.collected_at
    age = max(0, int((datetime.now().astimezone() - collected).total_seconds()))
    status_label = "on"
    detail = (
        f"provider={context.provider}; age={age}s; "
        f"cache={'hit' if context.cache_hit else 'miss'}; timeout="
        f"{cfg.runtime_context_command_timeout_seconds}s"
    )
    location = context.location.country_name or context.location.country_code or "unknown"
    location_detail = (
        f"{location}; source={context.location.source}; "
        f"confidence={context.location.confidence}"
    )
    return status_label, detail, location_detail, result


def _knowledge_libraries_count(cfg) -> int | None:
    db_path = cfg.knowledge_dir / "fts.db"
    if not db_path.exists():
        return 0
    try:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
        try:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "active_sources" in tables:
                row = db.execute("SELECT COUNT(DISTINCT library) FROM active_sources").fetchone()
                return int(row[0] or 0)
            if "chunks" in tables:
                row = db.execute("SELECT COUNT(DISTINCT collection) FROM chunks").fetchone()
                return int(row[0] or 0)
            return 0
        finally:
            db.close()
    except sqlite3.Error:
        return None


def _executable_version(path: str | None, timeout: int) -> str:
    if not path:
        return "not found"
    try:
        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except Exception as exc:
        return f"found; version unavailable ({exc})"
    text = (result.stdout or result.stderr).splitlines()
    return text[0].strip() if result.returncode == 0 and text else "found; version unavailable"


@app.command()
def status():
    """Show configured modes, storage, and tool permissions."""
    from klaude_knowledge import list_docs_sources, list_installed_skills
    from klaude_web.providers import provider_status_detail, search_provider_statuses

    cfg = load_config()
    memory = Memory(cfg.memory_file, cfg.sessions_db)
    docs_sources = list_docs_sources(cfg)
    skills_installed = list_installed_skills(cfg)
    online_docs_count = (
        len(_iter_online_docs_entries(_online_docs_file()))
        if _online_docs_file().exists()
        else 0
    )
    libraries_count = _knowledge_libraries_count(cfg)
    runtime_status, runtime_detail, runtime_location, _runtime_result = (
        _runtime_status_summary(cfg, Path.cwd())
    )
    provider_statuses = search_provider_statuses(cfg)

    modes = Table(title="Klaude Status", show_header=True, header_style="bold")
    modes.add_column("Area")
    modes.add_column("Status")
    modes.add_column("Detail")
    modes.add_row(
        "web search",
        _web_mode(cfg, "web_search"),
        f"strategy={cfg.web_search.strategy}; provider={cfg.web_provider}",
    )
    modes.add_row(
        "search billing",
        "on",
        (
            f"mode={cfg.web_billing.mode}; "
            f"paid_overage={'on' if cfg.web_billing.allow_paid_overage else 'off'}; "
            f"auto_recharge={'on' if cfg.web_billing.allow_auto_recharge else 'off'}"
        ),
    )
    modes.add_row(
        "search cache",
        "on" if cfg.web_search.cache_enabled else "off",
        "intent-aware structured result cache",
    )
    for provider_status in provider_statuses:
        modes.add_row(
            f"search/{provider_status.name}",
            provider_status.state.value.replace("_", " "),
            provider_status_detail(provider_status),
        )
    modes.add_row(
        "fetch url",
        _web_mode(cfg, "fetch_url"),
        f"crawl4ai={cfg.crawl4ai_url or 'off'}; exa={_auth_label(cfg.exa_api_key)}",
    )
    modes.add_row(
        "code search",
        _web_mode(cfg, "code_search"),
        "programming docs/examples search",
    )
    modes.add_row(
        "weather",
        _mode_from_permission(_permission_label(cfg, "weather_lookup")),
        "wttr.in JSON forecast lookup",
    )
    modes.add_row(
        "time",
        _mode_from_permission(_permission_label(cfg, "current_time")),
        "runtime context uses local system clock",
    )
    modes.add_row(
        "runtime context",
        runtime_status,
        runtime_detail,
    )
    modes.add_row(
        "runtime location",
        "on" if runtime_status == "on" else runtime_status,
        runtime_location,
    )
    modes.add_row(
        "network geolocation",
        "on" if cfg.runtime_context_location_allow_network else "off",
        f"mode={cfg.runtime_context_location_mode}",
    )
    modes.add_row(
        "auto memory",
        "on" if memory.auto_memory_enabled() else "off",
        str(cfg.memory_file),
    )
    modes.add_row(
        "remember tool",
        _mode_from_permission(_permission_label(cfg, "remember_fact")),
        "manual CLI remember is always available",
    )
    modes.add_row(
        "session recall",
        _mode_from_permission(_permission_label(cfg, "search_sessions")),
        str(cfg.sessions_db),
    )
    libraries_label = (
        _count_status("libraries", libraries_count or 0)
        if libraries_count is not None
        else "unavailable"
    )
    modes.add_row(
        "knowledge",
        "on",
        f"learned libraries: {libraries_label}; retrieval_k={cfg.retrieval_k}",
    )
    modes.add_row(
        "managed docs sources",
        "on",
        _count_status("sources", len(docs_sources)),
    )
    modes.add_row("online-docs entries", "on", _count_status("entries", online_docs_count))
    modes.add_row("installed skills", "on", _count_status("skills", len(skills_installed)))
    modes.add_row(
        "crawl",
        _mode_from_permission(_permission_label(cfg, "crawl_site")),
        (
            f"robots={cfg.crawl_respect_robots}; max_pages={cfg.crawl_max_pages}; "
            f"delay={cfg.crawl_delay_min}-{cfg.crawl_delay_max}s"
        ),
    )
    modes.add_row(
        "huggingface",
        _mode_from_permission(_permission_label(cfg, "huggingface_search")),
        f"auth={_auth_label(cfg.huggingface_api_key)}; base={cfg.huggingface_base_url}",
    )
    modes.add_row(
        "models",
        "on",
        (
            f"tier={cfg.tier}; coder={cfg.models.get('coder', '')}; "
            f"embed={cfg.models.get('embed', '')}"
        ),
    )
    modes.add_row("data", "on", str(cfg.data_dir))
    modes.add_row("config", "on", str(CONFIG_DIR / "config.toml"))
    console.print(modes)

    tool_rows = Table(title="Agent Tool Permissions", show_header=True, header_style="bold")
    tool_rows.add_column("Tool")
    tool_rows.add_column("Policy")
    tool_rows.add_column("Mode")
    for tool_name in sorted(cfg.permissions):
        policy = cfg.permissions[tool_name]
        tool_rows.add_row(tool_name, policy, _mode_from_permission(policy))
    console.print(tool_rows)


@app.command("system-info")
def system_info(
    as_json: bool = typer.Option(False, "--json", help="emit normalized context as JSON"),
    refresh: bool = typer.Option(False, "--refresh", help="refresh cached stable context"),
):
    """Show normalized runtime context diagnostics."""
    cfg = load_config()
    result = _runtime_context_result(cfg, Path.cwd(), refresh=refresh)
    if not result:
        raise typer.Exit(1)
    if as_json:
        console.print_json(json.dumps(context_to_dict(result.context), ensure_ascii=False))
        return
    console.print(render_runtime_context(result.context, cfg), markup=False)
    if result.install_suggestion and cfg.runtime_context.show_install_suggestion:
        console.print(f"\n{result.install_suggestion}", markup=False)


@app.command()
def doctor():
    """Check every service, model, and directory klaude needs."""
    from klaude_web.providers import (
        ProviderState,
        provider_capability_summary,
        provider_status_detail,
        search_provider_statuses,
    )

    cfg = load_config()
    ok = True

    def check(name: str, passed: bool, hint: str = ""):
        nonlocal ok
        mark = "[green]OK[/]" if passed else "[red]FAIL[/]"
        console.print(f"{mark}  {name}" + (f"  [dim]{hint}[/]" if not passed and hint else ""))
        ok = ok and passed

    ollama = Ollama(cfg.ollama_url, timeout=5)
    up = ollama.is_up()
    check(f"ollama at {cfg.ollama_url}", up, "start with: ollama serve")

    if up:
        installed = ollama.list_models()
        for role, model in cfg.models.items():
            if not model:
                continue
            have = any(m.startswith(model.split(":")[0]) for m in installed)
            check(f"model {role}: {model}", have, f"run: ollama pull {model}")

    try:
        import httpx

        r = httpx.get(
            f"{cfg.searxng_url}/search",
            params={"q": "test", "format": "json"},
            timeout=8,
        )
        check(
            f"searxng at {cfg.searxng_url}",
            r.status_code == 200,
            "docker compose up -d; ensure 'json' in search.formats",
        )
    except Exception:
        check(f"searxng at {cfg.searxng_url}", False, "docker compose up -d")

    provider_statuses = search_provider_statuses(cfg)
    has_available_provider = any(
        status.state == ProviderState.AVAILABLE for status in provider_statuses
    )
    check(
        "search provider availability",
        has_available_provider,
        "configure a provider, install DDGS, or start SearXNG",
    )
    console.print(
        "[dim]--   search policy "
        f"(strategy={cfg.web_search.strategy}; billing={cfg.web_billing.mode}; "
        f"paid_overage={'disabled' if not cfg.web_billing.allow_paid_overage else 'blocked'}; "
        f"auto_recharge={'disabled' if not cfg.web_billing.allow_auto_recharge else 'blocked'})[/]"
    )
    for status in provider_statuses:
        detail = provider_status_detail(status)
        capabilities = provider_capability_summary(status)
        if status.state == ProviderState.AVAILABLE:
            console.print(
                f"[green]OK[/]  search provider {status.name}  "
                f"[dim]{detail}; capabilities={capabilities}[/]"
            )
        elif status.state in {
            ProviderState.UNCONFIGURED,
            ProviderState.DISABLED,
            ProviderState.BILLING_BLOCKED,
        }:
            console.print(
                f"[dim]--   search provider {status.name} "
                f"({detail}; capabilities={capabilities})[/]"
            )
        else:
            console.print(
                f"[yellow]WARN[/] search provider {status.name} "
                f"[dim]{detail}; capabilities={capabilities}[/]"
            )

    if cfg.crawl4ai_url:
        try:
            import httpx

            r = httpx.get(f"{cfg.crawl4ai_url}/health", timeout=5)
            check(f"crawl4ai at {cfg.crawl4ai_url}", r.status_code == 200)
        except Exception:
            check(
                f"crawl4ai at {cfg.crawl4ai_url}",
                False,
                "docker compose --profile heavy up -d",
            )
    else:
        console.print(
            "[dim]--   crawl4ai not configured "
            "(optional; trafilatura fallback active)[/]"
        )

    fastfetch_path = shutil.which("fastfetch")
    neofetch_path = shutil.which("neofetch")
    timeout = cfg.runtime_context_command_timeout_seconds
    console.print(
        "[dim]--   runtime context "
        f"(selected provider={cfg.runtime_context_provider}; timeout={timeout}s)[/]"
    )
    console.print(
        "[dim]--   fastfetch "
        f"({_executable_version(fastfetch_path, timeout)})[/]"
    )
    console.print(
        "[dim]--   neofetch "
        f"({_executable_version(neofetch_path, timeout)})[/]"
    )
    runtime_result = _runtime_context_result(cfg, Path.cwd())
    if runtime_result:
        context = runtime_result.context
        console.print(
            "[dim]--   runtime provider "
            f"({context.provider}; duration={runtime_result.duration_ms}ms; "
            f"warnings={len(context.warnings)})[/]"
        )
        console.print(
            "[dim]--   timezone "
            f"({context.temporal.timezone or 'unknown'}; offset={context.temporal.utc_offset})[/]"
        )
        console.print(
            "[dim]--   location inference "
            f"({context.location.source}; confidence={context.location.confidence})[/]"
        )
        if runtime_result.install_suggestion and cfg.runtime_context.show_install_suggestion:
            console.print(f"[dim]--   {runtime_result.install_suggestion}[/]")
    console.print(
        "[dim]--   network geolocation "
        f"({'enabled' if cfg.runtime_context_location_allow_network else 'disabled'})[/]"
    )

    console.print(
        "[dim]--   huggingface hub "
        f"({'authenticated' if cfg.huggingface_api_key else 'public; add HUGGINGFACE_API_KEY'})[/]"
    )
    auto_memory = (
        "enabled"
        if Memory(cfg.memory_file, cfg.sessions_db).auto_memory_enabled()
        else "disabled"
    )
    console.print(f"[dim]--   auto memory ({auto_memory})[/]")

    check(f"data dir {cfg.data_dir}", cfg.data_dir.exists() and cfg.data_dir.is_dir())
    console.print(f"\n[dim]hardware tier: {cfg.tier} -> coder model {cfg.models['coder']}[/]")
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
