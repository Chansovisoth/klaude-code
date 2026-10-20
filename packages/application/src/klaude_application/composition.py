"""Small shared construction seam; no terminal imports or startup probes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from klaude_core import Agent, PermissionGate, Tool, WebResearchBudget
from klaude_core.config import Config, load_config
from klaude_core.memory import Memory
from klaude_core.model_runtime import ModelInfo, ModelRuntime
from klaude_tools import Workspace, build_tools


def compose_agent(
    runtime: ModelRuntime | Any,
    model: str,
    tools: list[Tool],
    gate: PermissionGate,
    system_prompt: str,
    *,
    max_steps: int = 20,
    max_tool_calls: int | None = None,
    max_total_tokens: int | None = None,
    max_code_continuations: int = 2,
    max_code_repairs: int = 2,
    tool_selector: Any = None,
    ollama_options: dict[str, Any] | None = None,
    ollama_think: bool | str | None = None,
    ollama_code_options: dict[str, Any] | None = None,
    ollama_code_think: bool | str | None = None,
    code_context: str = "",
    model_info: ModelInfo | None = None,
    max_subagent_concurrency: int = 0,
    web_research_budget: WebResearchBudget | None = None,
) -> Agent:
    """Construct the existing Agent from host-selected parts, without side effects."""
    return Agent(
        runtime, model, tools, gate, system_prompt,
        max_steps=max_steps,
        max_tool_calls=max_tool_calls,
        max_total_tokens=max_total_tokens,
        max_code_continuations=max_code_continuations,
        max_code_repairs=max_code_repairs,
        tool_selector=tool_selector,
        ollama_options=ollama_options,
        ollama_think=ollama_think,
        ollama_code_options=ollama_code_options,
        ollama_code_think=ollama_code_think,
        code_context=code_context,
        model_info=model_info,
        max_subagent_concurrency=max_subagent_concurrency,
        web_research_budget=web_research_budget,
    )


def open_local_session(
    workdir: Path,
    runtime: ModelRuntime | Any,
    *,
    config: Config | None = None,
    model: str | None = None,
    tool_selector: Any = None,
) -> tuple[Agent, Memory]:
    """Open local tools and memory without contacting a model or changing Git.

    Workspace writes remain disabled until the caller explicitly activates a
    clean work branch through the existing Workspace method.
    """
    cfg = config if config is not None else load_config()
    memory = Memory(cfg.memory_file, cfg.sessions_db)
    try:
        workspace = Workspace(workdir)
        workspace.write_enabled = False
        selected = model or cfg.models["coder"]
        gate = PermissionGate(cfg.permissions, lambda _tool, _detail: "n")
        agent = compose_agent(
            runtime, selected, build_tools(workspace), gate,
            "Klaude local coding assistant. Follow the user's instructions and tool policies.",
            max_steps=cfg.max_agent_steps,
            max_tool_calls=cfg.max_agent_tool_calls or None,
            max_total_tokens=cfg.max_agent_tokens or None,
            max_code_continuations=cfg.max_code_continuations,
            max_code_repairs=cfg.max_code_repairs,
            max_subagent_concurrency=cfg.max_subagent_concurrency,
            tool_selector=tool_selector,
            ollama_options=cfg.ollama_options,
            ollama_think=cfg.ollama_think_for_model(selected),
            ollama_code_options=cfg.ollama_code_options,
            ollama_code_think=cfg.ollama_code_think_for_model(selected),
            code_context=memory.facts(),
            model_info=ModelInfo("ollama", selected, selected),
        )
        agent.workspace = workspace
        agent.workdir = workdir.resolve()
        agent.tool_config = cfg
        return agent, memory
    except BaseException:
        memory.db.close()
        raise
