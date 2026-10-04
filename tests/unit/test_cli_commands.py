import asyncio
import inspect
import json
import subprocess
import threading
import time
from datetime import datetime
from importlib.metadata import version as package_version
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from klaude_cli.main import (
    AGENTS_INSTRUCTION_MAX_CHARS,
    COMMAND_REFERENCE,
    CTRL_ENTER_SEQUENCES,
    DEFAULT_INPUT_BORDER,
    DEFAULT_INPUT_HEIGHT,
    DEFAULT_TEXT_THEME,
    DEFAULT_TUI_THEME,
    ESCAPE_SEQUENCE_TIMEOUT,
    FETCH_URL_TOOL_DESCRIPTION,
    HTTP_PROBE_TOOL_DESCRIPTION,
    KITTY_KEYBOARD_PROTOCOL_OFF,
    KITTY_KEYBOARD_PROTOCOL_ON,
    LARGE_PASTE_CHARACTER_THRESHOLD,
    LIST_COMMANDS_TOOL_DESCRIPTION,
    MAX_INPUT_HEIGHT,
    MIN_INPUT_HEIGHT,
    RESET_THEME_CHOICE,
    SHIFT_ENTER_SEQUENCES,
    TERMINAL_CLEAR_SEQUENCE,
    TEXT_THEME_PREVIEW_BLOCK,
    TUI_THEME_LABELS,
    TUI_THEME_STYLES,
    WEATHER_TOOL_DESCRIPTION,
    WEB_SEARCH_TOOL_DESCRIPTION,
    XTERM_MODIFY_OTHER_KEYS_OFF,
    XTERM_MODIFY_OTHER_KEYS_ON,
    ChatCommandCompleter,
    ChatUIState,
    CommandSurface,
    InputPlaceholderProcessor,
    PendingChatCommand,
    PendingChatTurn,
    PersistentChatTUI,
    TranscriptLexer,
    TUIAppearance,
    UserInputBroker,
    _active_tool_status,
    _activity_updates_enabled,
    _activity_value,
    _agent_configuration_context,
    _agent_context_window,
    _append_tool_capabilities,
    _apply_runtime_context_to_search_config,
    _apply_runtime_preferences,
    _apply_session_effort,
    _apply_tool_availability_preferences,
    _apply_web_provider_preferences,
    _ask_permission,
    _bounded_result_count,
    _chat_status,
    _chat_toolbar,
    _codex_usage_rows,
    _command_reference_context,
    _command_reference_result,
    _completed_tool_activity,
    _control_ollama_service,
    _control_ollama_service_with_sudo,
    _delegate_task_preflight,
    _delegate_task_result,
    _diff_syntax_lines,
    _edit_summary,
    _fenced_code_lines,
    _format_recent_sessions,
    _format_search_response,
    _format_web_results,
    _handle_command_reference_request,
    _handle_unknown_slash_command,
    _http_probe_display_lines,
    _http_probe_tool_result,
    _inferred_knowledge_library,
    _init_request,
    _is_termux_terminal,
    _iter_online_docs_entries,
    _klaude_logo,
    _knowledge_context_chunk_count,
    _knowledge_ingestion_intent,
    _knowledge_libraries_count,
    _learn_source_permission_detail,
    _learn_source_preflight,
    _learn_source_tool_result,
    _load_last_chat_model,
    _load_runtime_preferences,
    _load_tui_appearance,
    _message_divider,
    _migrate_runtime_device_preference,
    _mode_from_permission,
    _normalized_user_input_options,
    _online_docs_file,
    _pending_input_request_from_turns,
    _plan_command,
    _print_assistant_text,
    _print_trace,
    _prompt_cache_status,
    _public_model_metadata,
    _query_knowledge_display_lines,
    _read_chat_input,
    _read_plain_chat_input,
    _render,
    _repository_instruction_context,
    _resolve_requested_chat_model,
    _restored_transcript,
    _runtime_status_summary,
    _save_last_chat_model,
    _save_runtime_preferences,
    _save_tui_appearance,
    _search_execution_metadata,
    _select_tool_names,
    _status_columns,
    _status_rich_text,
    _styled_recent_sessions,
    _subagent_activity_text,
    _system_prompt,
    _tool_availability_preferences,
    _tui_style,
    _update_online_docs,
    _web_mode,
    _web_provider_preferences,
    _web_search_display_lines,
    _web_search_start_metadata,
    app,
    docs_update,
    format_chat_keybind_reference,
    format_command_reference,
    format_focused_command_help,
    is_complete_command_reference_request,
    iter_command_specs,
    resolve_command_help_request,
    sessions_clear,
    sessions_delete,
    system_info,
)
from klaude_core import (
    Agent,
    AgentEvent,
    ModelCapabilities,
    ModelInfo,
    PermissionGate,
    SubagentEvent,
    SubagentResult,
    SubagentRole,
    SubagentStatus,
    Tool,
    TurnScope,
)
from klaude_core.config import DEFAULT_PERMISSIONS, Config
from klaude_core.memory import Memory
from klaude_core.runtime_context import (
    LocationContext,
    RuntimeContext,
    RuntimeContextResult,
    SystemContext,
    TemporalContext,
)
from prompt_toolkit.buffer import CompletionState
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.keys import Keys
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


def test_system_prompt_points_to_deterministic_command_reference(tmp_path):
    prompt = _system_prompt(
        Memory(tmp_path / "memory.md", tmp_path / "sessions.db"),
        configuration_context="- Tool registry: 3/4 enabled",
    )

    assert "Usage: klaude [OPTIONS] COMMAND [ARGS]..." not in prompt
    assert "deterministic command-reference router" in prompt
    assert "Preserve its\n  formatting" in prompt
    assert "do not rewrite, summarize, or repeat the returned command list" in prompt
    assert "Do not claim all operations have no external data transmission" in prompt
    assert "Use tools only when they materially improve correctness" in prompt
    assert "Do not use tools for greetings" in prompt
    assert "Tool-use decision policy:" in prompt
    assert "Direct response: greetings" in prompt
    assert "Command reference: use list_commands only" in prompt
    assert "Command facts: never invent Klaude CLI commands" in prompt
    assert "canonical command registry" in prompt
    assert "If a requested command is absent" in prompt
    assert "current_time, weather_lookup, or web_search" in prompt
    assert "Do not expand an ambiguous acronym" in prompt
    assert "For greetings and casual openers, do not volunteer runtime context" in prompt
    assert "answer only with the current working directory and repository root" in prompt
    assert "If a search tool or provider fails, do not fabricate replacement facts" in prompt
    assert "Only call `list_commands` when the user explicitly asks for commands" in prompt
    assert "remember_fact" not in COMMAND_REFERENCE
    assert "list_commands" not in COMMAND_REFERENCE
    assert "list_files" not in COMMAND_REFERENCE
    assert "run_shell_command" not in COMMAND_REFERENCE
    assert "Runtime context:" in prompt
    assert "Active Klaude configuration:" in prompt
    assert "Tool registry: 3/4 enabled" in prompt


def test_agent_configuration_context_is_complete_dynamic_and_secret_free(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    cfg = Config()
    cfg.gemini_api_key = "super-secret-gemini-key"
    cfg.web_providers["brave"].enabled = True
    cfg.web_providers["google"].enabled = False
    cfg.web_search.result_validation_enabled = False
    cfg.retrieval_validation_enabled = True
    preferences_path = tmp_path / "chat-preferences.json"
    preferences_path.write_text(
        json.dumps(
            {
                "runtime_device_mode": "cpu-only",
                "composer_mode": "vim",
                "display": {"activity_updates": False},
            }
        )
    )
    appearance_path = tmp_path / "appearance.json"
    appearance_path.write_text(
        json.dumps(
            {
                "theme": {"interface": "crimson-red", "text": "monokai"},
                "input_field": {"border": False, "min_height": 6, "max_height": 10},
            }
        )
    )
    (tmp_path / "AGENTS.md").write_text("repository-specific instructions")
    agent = SimpleNamespace(
        model="qwen3-coder:30b",
        model_info=SimpleNamespace(backend="ollama", ref="ollama/qwen3-coder:30b"),
        reasoning_mode="thinking",
        reasoning_effort="high",
        ollama_think="high",
        ollama_code_think="medium",
        plan_mode=True,
        ollama_options={"num_ctx": 16_384, "num_thread": 8, "unknown_secret": "do-not-show"},
        ollama_code_options={"temperature": 0.2},
        tools={"read_file": object(), "web_search": object(), "write_file": object()},
        disabled_tool_names={"write_file"},
        gate=SimpleNamespace(
            policies={"read_file": "allow", "web_search": "ask", "write_file": "deny"}
        ),
        tool_config=cfg,
        workdir=tmp_path,
        workspace=SimpleNamespace(repo_root=tmp_path),
    )

    context = _agent_configuration_context(
        agent,
        memory,
        preferences_path=preferences_path,
        appearance_path=appearance_path,
    )

    assert "Model: ollama/qwen3-coder:30b (backend=ollama)" in context
    assert "mode=thinking; effort=chat high · code medium; plan_mode=on" in context
    assert "Turn execution limit: 20 model/tool steps" in context
    assert "Subagent concurrency: auto (1 effective)" in context
    assert "Tool registry: 2/3 enabled; enabled=read_file, web_search" in context
    assert "allow=1 (read_file); ask=1 (web_search); deny=1 (write_file)" in context
    assert "Web provider toggles: 8/9 on" in context
    assert "Web providers off: google" in context
    assert "web_search=off; knowledge_search=on" in context
    assert "Repository guidance: injected" in context
    assert "device=cpu-only; composer=vim; activity_updates=off" in context
    assert "interface=Crimson Red; syntax=Monokai; input_border=off; input_height=6-10" in context
    assert "super-secret-gemini-key" not in context
    assert "do-not-show" not in context
    assert "repository-specific instructions" in context

    agent.disabled_tool_names.clear()
    agent.reasoning_mode = "standard"
    cfg.web_providers["google"].enabled = True
    refreshed = _agent_configuration_context(agent, memory)

    assert "mode=standard; effort=standard; plan_mode=on" in refreshed
    assert "Tool registry: 3/3 enabled" in refreshed
    assert "Web provider toggles: 9/9 on" in refreshed
    assert "Web providers off:" not in refreshed


def test_repository_instructions_are_bounded_ordered_and_preserve_nested_guidance(tmp_path):
    repo = tmp_path / "repo"
    workdir = repo / "src" / "feature"
    workdir.mkdir(parents=True)
    root = repo / "AGENTS.md"
    nested = workdir / "AGENTS.md"
    root.write_text("ROOT-GUIDANCE\n" + ("r" * AGENTS_INSTRUCTION_MAX_CHARS))
    nested.write_text("NESTED-GUIDANCE\nOnly edit feature files.")
    agent = SimpleNamespace(
        workdir=workdir,
        workspace=SimpleNamespace(repo_root=repo),
    )

    context, paths, truncated = _repository_instruction_context(agent)

    assert paths == [root, nested]
    assert truncated
    assert "ROOT-GUIDANCE" in context
    assert "NESTED-GUIDANCE" in context
    assert context.index(str(root)) < context.index(str(nested))
    assert len(context) < AGENTS_INSTRUCTION_MAX_CHARS + 1_000
    assert 'permission_escalation="false"' in context


def test_cloud_context_uses_discovered_limit_and_hides_ollama_tuning(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    agent = SimpleNamespace(
        model="gpt-5",
        model_info=ModelInfo(
            "openai_codex",
            "gpt-5",
            "GPT-5",
            capabilities=ModelCapabilities(context_window=128_000),
        ),
        reasoning_mode="standard",
        plan_mode=False,
        max_steps=40,
        max_tool_calls=80,
        max_total_tokens=100_000,
        ollama_options={"num_ctx": 8192, "num_gpu": -1},
        ollama_code_options={"num_ctx": 4096},
        tools={},
        disabled_tool_names=set(),
        gate=SimpleNamespace(policies={}, process_grants=set()),
        workdir=tmp_path,
        tool_config=None,
    )

    context = _agent_configuration_context(agent, memory)

    assert _agent_context_window(agent) == 128_000
    assert "Context window: 128,000 tokens" in context
    assert "General request settings: provider/model defaults" in context
    assert "num_ctx=8192" not in context
    assert "num_gpu=-1" not in context


def test_chat_input_preserves_a_multiline_prompt_as_one_turn():
    class FakePromptSession:
        def prompt(self, _message):
            return "Create a script.\n- Requirement one\n- Requirement two\n"

    assert _read_chat_input(FakePromptSession()) == (
        "Create a script.\n- Requirement one\n- Requirement two"
    )


def test_plain_chat_input_uses_an_undecorated_terminal_prompt(monkeypatch):
    prompts = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "  hello  ")

    assert _read_plain_chat_input() == "hello"
    assert prompts == ["you> "]


def test_bare_cli_launches_the_interactive_chat(monkeypatch):
    from typer.testing import CliRunner

    calls = []
    monkeypatch.setattr(
        "klaude_cli.main.chat",
        lambda **kwargs: calls.append(kwargs),
    )

    result = CliRunner().invoke(app, [])

    assert result.exit_code == 0, result.output
    assert calls == [{"model": "", "legacy": False, "no_tui": False}]


def test_canonical_command_reference_preserves_sections_and_lines():
    reference = format_command_reference(width=100)

    assert reference.startswith("Usage: klaude [OPTIONS] [COMMAND] [ARGS]...\n\n")
    assert "\nCLI COMMANDS\n" in reference
    assert "\nDOCS COMMANDS\n" in reference
    assert "\nCHAT COMMANDS\n" in reference
    assert "\n------------\n" not in reference
    assert "\n  chat" in reference
    assert "\n  ask" in reference
    assert "\n  search" in reference
    assert "\n  docs update --online" in reference
    assert "\n  /help" in reference
    assert "\n  /models" not in reference
    assert "\n  /model" in reference
    assert "Select an available Cloud or Local chat model" in reference
    assert "\n  /effort" in reference
    assert "\n  /start" in reference
    assert "\n  /restart" in reference
    assert "\n  /stop" in reference
    assert "\n  /refresh" in reference
    assert "\n  /model NAME" not in reference
    assert "\n  /effort LEVEL" not in reference
    assert "AGENT CAPABILITIES" not in reference
    assert "chat Interactive" not in reference
    assert "ask One-shot" not in reference
    assert "\x1b" not in reference
    assert all(char == "\n" or ord(char) >= 32 for char in reference)


def test_command_registry_contains_model_commands_separately():
    usages = {spec.usage for spec in iter_command_specs()}

    assert "/model" in usages
    assert "/model NAME" in usages
    assert "/models" not in usages
    assert {"/init", "/vim", "/permission", "/settings [CATEGORY]"} <= usages
    assert not any(usage.startswith("/permissions") for usage in usages)
    assert "/debug_activity" not in usages
    assert "/nano" not in usages


def test_typer_commands_and_registry_do_not_silently_diverge():
    typer_names = {
        command.name or command.callback.__name__.replace("_", "-")
        for command in app.registered_commands
    }
    typer_names.update(group.name for group in app.registered_groups)
    registry_names = {spec.usage.split()[0] for spec in iter_command_specs(CommandSurface.CLI)}

    assert registry_names == typer_names


def test_sessions_subcommands_are_in_canonical_registry():
    sessions_group = next(group for group in app.registered_groups if group.name == "sessions")
    typer_usages = {
        f"sessions {command.name or command.callback.__name__.replace('_', '-')}"
        for command in sessions_group.typer_instance.registered_commands
    }
    registry_usages = {
        spec.usage
        for spec in iter_command_specs(CommandSurface.CLI)
        if spec.usage.startswith("sessions ")
    }

    assert registry_usages == {
        "sessions delete SESSION_ID",
        "sessions clear",
    }
    assert typer_usages == {"sessions delete", "sessions clear"}


def test_session_delete_and_clear_commands_require_confirmation(tmp_path, monkeypatch):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("s1", "user", "first")
    memory.log_turn("s1", "assistant", "reply")
    memory.log_turn("s2", "user", "second")
    prompts = []
    answers = [False, True]

    def fake_confirm(prompt, default=False):
        prompts.append(prompt)
        return answers.pop(0)

    monkeypatch.setattr("klaude_cli.main._memory_store", lambda: memory)
    monkeypatch.setattr("klaude_cli.main.typer.confirm", fake_confirm)

    sessions_delete("s1", yes=False)
    assert memory.session_counts() == {"sessions": 2, "turns": 3}
    assert prompts[-1] == "Delete session s1 (2 turns)?"

    sessions_delete("s1", yes=False)
    assert memory.session_counts() == {"sessions": 1, "turns": 1}

    sessions_clear(yes=True)
    assert memory.session_counts() == {"sessions": 0, "turns": 0}


def test_command_reference_excludes_invented_commands():
    reference = format_command_reference(width=100)

    for invented in (
        "/reload",
        "/reset",
        "/save",
        "/google",
        "/sudo",
        "/docker",
        "/kubectl",
        "/aws",
    ):
        assert invented not in reference


def test_command_reference_wraps_narrow_and_aligns_wide():
    wide = format_command_reference(width=120)
    narrow = format_command_reference(width=40)

    assert "  chat                        Interactive agent session" in wide
    assert "  huggingface-details\n      Print Hugging Face Hub" in narrow
    assert "docs add NAME URL -l LIBRARYInstall" not in wide
    assert ("  docs add NAME URL -l LIBRARY\n      Install refreshable llms.txt") in narrow


def test_focused_search_command_help_is_not_full_reference():
    response = format_focused_command_help("what command searches the web", width=80)

    assert response == ("klaude search QUERY\n    Web search via the configured provider.")
    assert "CLI COMMANDS" not in response


def test_no_search_instruction_is_not_intercepted_as_search_command_help():
    assert (
        format_focused_command_help(
            "Do not search the web or local knowledge. Explain recursion in one sentence."
        )
        is None
    )


def test_typo_tolerant_command_reference_detection():
    assert is_complete_command_reference_request("what commands can i use")
    assert is_complete_command_reference_request("what commans can i uss")
    assert is_complete_command_reference_request("what command can I use")
    assert is_complete_command_reference_request("show me the comands")
    assert is_complete_command_reference_request("list klaude commmands")
    assert is_complete_command_reference_request("available commands")
    assert is_complete_command_reference_request("what can i type here")
    assert is_complete_command_reference_request("show slash commands")


def test_typo_tolerant_detection_does_not_intercept_unrelated_questions():
    assert not is_complete_command_reference_request("what programming language should I use")
    assert not is_complete_command_reference_request("what database commands should my app support")
    assert not is_complete_command_reference_request("how should I design a command pattern")
    assert not is_complete_command_reference_request(
        "Use run_shell only to run this read-only command: cat /tmp/probe.txt. "
        "Report the tool result and do not use other tools."
    )


def test_named_prompt_file_routes_read_and_one_shot_workspace_tools():
    names = ("read_file", "list_dir", "workspace_info", "grep", "write_file",
             "edit_file", "run_shell", "git_status", "git_diff", "read_skill")
    tools = {name: Tool(name, name, {"type": "object"}, lambda **_kw: "")
             for name in names}

    assert _select_tool_names("Can you read xhallenge1.md?", tools) == [
        "read_file", "list_dir", "workspace_info", "grep"
    ]
    selected = _select_tool_names(
        "Read challenge1.md and follow the instructions inside", tools
    )
    assert {"read_file", "write_file", "edit_file", "run_shell"} <= set(selected)
    assert "read_skill" not in selected
    read_only = _select_tool_names(
        "Read challenge1.md and follow the instructions inside. Do not edit files.", tools
    )
    assert "read_file" in read_only
    assert not {"write_file", "edit_file", "run_shell"}.intersection(read_only)


def test_focused_model_help_matches_actual_model_behavior():
    response = format_focused_command_help("what does /model do?", width=90)

    assert "/model\n    Open the model picker, then choose Standard or Thinking mode." in response
    assert (
        "/model NAME\n"
        "    Select an available Cloud or Local model, then choose its reasoning mode while\n"
        "    preserving this conversation."
    ) in response
    assert "/mode [standard|thinking]" in response
    assert "/effort [low|medium|high]" in response
    assert "/model qwen3-coder:30b" in response
    assert "Use /models" not in response
    assert "/model list" not in response
    assert "/model select" not in response
    assert "/model info" not in response


def test_unknown_command_help_is_deterministic():
    response = format_focused_command_help("what does /reload do?", width=80)

    assert response == (
        "/reload is not a recognized Klaude chat command.\n"
        "Type /help to see the available commands."
    )
    assert "reload the session" not in response.lower()


def test_command_suggestions_come_from_registry_only():
    resolution = resolve_command_help_request("what does /modle do?")
    response = format_focused_command_help("what does /modle do?", width=80)
    usages = {spec.usage for spec in iter_command_specs()}

    assert resolution is not None
    assert resolution.exact is None
    assert {spec.usage for spec in resolution.suggestions} <= usages
    assert "Did you mean /mode?" in response


def test_focused_docs_and_status_help_use_registry():
    assert format_focused_command_help("how do I update all docs?", width=90).startswith(
        "klaude docs update --all\n"
    )
    assert format_focused_command_help("explain klaude docs update", width=90).startswith(
        "klaude docs update NAME\n"
    )
    assert format_focused_command_help("what does the status command do?", width=90) == (
        "klaude status\n    Show configured modes, storage, and tool permissions."
    )


def _fake_runtime_result():
    context = RuntimeContext(
        collected_at=datetime.now().astimezone(),
        provider="native",
        provider_version=None,
        working_directory="/workspace",
        repository=None,
        system=SystemContext(os_name="TestOS"),
        temporal=TemporalContext(
            local_iso="2026-08-01T12:00:00+07:00",
            utc_iso="2026-08-01T05:00:00+00:00",
            timezone="Asia/Phnom_Penh",
            utc_offset="+07:00",
            weekday="Saturday",
        ),
        location=LocationContext(
            country_code="KH",
            country_name="Cambodia",
            source="timezone",
            confidence="medium",
        ),
        warnings=[],
    )
    return RuntimeContextResult(context=context, duration_ms=2)


def _printed_plain(printed) -> str:
    values = []
    for args, _kwargs in printed:
        if not args:
            continue
        item = args[0]
        values.append(item.plain if isinstance(item, Text) else str(item))
    return "\n".join(values)


def test_command_reference_renders_as_plain_text(monkeypatch):
    printed = []

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    _print_assistant_text(COMMAND_REFERENCE)

    assert isinstance(printed[0][0][0], Text)
    assert printed[0][0][0].plain == COMMAND_REFERENCE
    assert any(span.style == "underline" for span in printed[0][0][0].spans)
    assert printed[0][1] == {"overflow": "fold"}


def test_transcript_lexer_underlines_help_categories_and_grays_message_dividers():
    document = Document("CLI COMMANDS\n  chat  Start chat\n━━ you · 2026-09-05 12:34:56 ━━━━━━━━━━")
    get_line = TranscriptLexer().lex_document(document)

    assert get_line(0) == [("class:help.category", "CLI COMMANDS")]
    assert get_line(2) == [
        ("class:transcript.divider.rule", "━━ "),
        ("class:transcript.divider.text", "you · 2026-09-05 12:34:56"),
        ("class:transcript.divider.rule", " ━━━━━━━━━━"),
    ]


def test_transcript_lexer_highlights_fenced_code_with_its_language():
    fence = "`" * 3
    document = Document(f"{fence}python\nvalue = 1\n{fence}")

    fragments = TranscriptLexer().lex_document(document)(1)

    assert ("class:pygments.name", "value") in fragments
    assert ("class:pygments.operator", "=") in fragments


def test_edit_summary_renders_counts_syntax_and_replays():
    text = _edit_summary(
        [
            {
                "path": "demo.py",
                "added": 1,
                "removed": 1,
                "lines": ["      1 - value = 1", "      1 + value = 2"],
            },
            {"path": "other.py", "added": 1, "removed": 0, "lines": []},
        ],
        elapsed_seconds=30,
    )
    assert "[edited] (30s) 2 files (+2 -1)" in text
    assert "└ demo.py (+1 -1)" in text
    fragments = TranscriptLexer().lex_document(Document(text))(3)
    assert any(style.startswith("class:pygments") for style, _ in fragments)
    assert fragments[0][0] == "#55d985"
    restored = _restored_transcript(
        "test", [{"role": "system", "content": {"event": "edit_summary", "text": text}}], 80
    )
    assert text in restored


def test_live_activity_uses_original_braille_animation_and_static_style(monkeypatch):
    tui = _fake_persistent_tui()
    tui.running = True
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 0.0)
    first = tui._status_fragments()[0]
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 0.1)
    second = tui._status_fragments()[0]
    assert first[0] == second[0] == "class:runtime_busy"
    assert first[1] == " ⠋ WORKING "
    assert second[1] == " ⠙ WORKING "
    tui.running = False
    assert tui._status_fragments()[0][0] == "class:runtime_text"


def test_live_activity_uses_progressive_label_and_whole_turn_elapsed(monkeypatch):
    tui = _fake_persistent_tui()
    tui.running = True
    tui.activity = "editing src/app.py"
    tui._turn_started_at = 100.0
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 111.0)

    status = "".join(text for _style, text in tui._status_fragments())

    assert f"{tui.appearance.spinner.animation.frame_at(111.0)} EDITING" in status
    assert "11s" in status
    assert "[EDITING]" not in status
    assert "src/app.py" not in status


def test_quiet_running_command_transitions_to_waiting_after_threshold(monkeypatch):
    tui = _fake_persistent_tui()
    tui.running = True
    tui.activity = "running pytest tests/unit"
    tui._turn_started_at = 90.0
    tui._activity_started_at = 100.0

    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 104.9)
    assert "RUNNING" in "".join(text for _style, text in tui._status_fragments())

    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 105.0)
    status = "".join(text for _style, text in tui._status_fragments())
    assert "WAITING" in status
    assert "15s" in status


def test_permission_wait_uses_braille_footer_and_compact_elapsed(monkeypatch):
    tui = _fake_persistent_tui()
    tui.running = True
    tui._turn_started_at = 40.0
    tui._permission_request = {"tool": "run_shell"}
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 111.0)

    status = "".join(text for _style, text in tui._status_fragments())

    assert f"{tui.appearance.spinner.animation.frame_at(111.0)} WAITING" in status
    assert "1m 11s" in status
    assert "[WAITING]" not in status


def test_transcript_lexer_highlights_git_diff_and_marks_the_patch_surface():
    document = Document(
        "Staged changes\n"
        "diff --git a/example.py b/example.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/example.py\n"
        "+++ b/example.py\n"
        "@@ -1 +1 @@\n"
        "-old_value = 1\n"
        "+new_value = 2\n"
        "Untracked files (names only)\n"
        "new.txt"
    )

    fragments = TranscriptLexer().lex_document(document)(6)

    assert any(style.startswith("class:pygments") for style, _text in fragments)
    assert _diff_syntax_lines(document) == set(range(1, 8))


def test_transcript_lexer_accents_help_command_without_restyling_description():
    line = "  /settings [CATEGORY]  Configure the interface."

    fragments = TranscriptLexer().lex_document(Document(line))(0)

    assert fragments[0] == ("class:help.command", "  /settings [CATEGORY]")
    assert "".join(text for _style, text in fragments[1:]) == "  Configure the interface."
    assert all(style != "class:help.command" for style, _text in fragments[1:])
    assert (
        _tui_style("autumn", "vscode-dark").get_attrs_for_style_str("class:help.command").color
        == "f59a78"
    )


def test_user_surface_background_preserves_command_and_code_foregrounds():
    style = _tui_style("autumn", "vscode-dark")

    command = style.get_attrs_for_style_str("class:help.command class:transcript.user-message")
    keyword = style.get_attrs_for_style_str("class:pygments.keyword class:transcript.user-message")
    code_keyword = style.get_attrs_for_style_str("class:pygments.keyword class:transcript.code")

    assert command.color == "f59a78"
    assert keyword.color == "6ebf26"
    assert code_keyword.color == "6ebf26"
    assert command.bgcolor == keyword.bgcolor == "35222a"
    assert code_keyword.bgcolor == "2f1e25"


@pytest.mark.parametrize("theme", TUI_THEME_STYLES)
def test_code_surface_is_slightly_darker_than_the_composer_for_every_theme(theme):
    style = _tui_style(theme, "vscode-dark")
    composer = style.get_attrs_for_style_str("class:input-field").bgcolor
    code = style.get_attrs_for_style_str("class:transcript.code").bgcolor

    assert code != composer
    assert all(
        int(code[index : index + 2], 16) < int(composer[index : index + 2], 16)
        for index in (0, 2, 4)
    )


def test_fenced_code_lines_include_the_fences_and_unclosed_blocks():
    closed = Document("before\n```python\nvalue = 1\n```\nafter")
    unclosed = Document("```python\nvalue = 1")

    assert _fenced_code_lines(closed) == {1, 2, 3}
    assert _fenced_code_lines(unclosed) == {0, 1}


def test_text_theme_preview_has_long_multilanguage_syntax_samples():
    assert TEXT_THEME_PREVIEW_BLOCK.count("\n") >= 90
    assert TEXT_THEME_PREVIEW_BLOCK.startswith("\n\n```html\n")
    assert "Regular text" not in TEXT_THEME_PREVIEW_BLOCK
    for language in ("html", "javascript", "css", "json", "python", "cpp", "csharp", "java"):
        assert f"```{language}" in TEXT_THEME_PREVIEW_BLOCK


def test_message_divider_includes_role_timestamp_and_fills_width():
    divider = _message_divider(
        "klaude",
        width=72,
        timestamp=datetime(2026, 9, 5, 12, 34, 56),
    )

    assert divider.startswith("━━ klaude · 2026-09-05 12:34:56 ")
    assert len(divider) == 72
    assert divider.endswith("━")


def test_start_next_separates_transcript_dividers_and_user_message(monkeypatch):
    tui = _fake_persistent_tui()
    tui.pending.append("hello there")
    monkeypatch.setattr(tui, "_run_turn", lambda *args, **kwargs: None)

    tui._start_next()

    assert "━━ Session: session-1 " in tui.output.text
    assert "\n\nhello there\n\n━━ you · " in tui.output.text


def test_persistent_tui_retains_the_full_transcript_without_trimming():
    tui = _fake_persistent_tui()
    opening = tui.output.text
    earlier = "earlier response\n"
    later = "x" * 250_001

    tui._append(earlier)
    tui._append(later)

    assert tui.output.text == opening + earlier + later
    assert "[older transcript trimmed]" not in tui.output.text


def test_resume_lists_all_sessions_in_columns_and_continues_selected_session(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    for i in range(15):
        tui.memory.log_turn(f"saved-{i:02}", "user", f"Original session title {i}")
        tui.memory.log_turn(f"saved-{i:02}", "assistant", "Saved answer")
    assert tui.memory.acquire_session_lease("saved-13", "other-client", "active-turn")
    tui.agent.restore_session = lambda turns: Agent.restore_session(tui.agent, turns)
    tui.agent.messages.append({"role": "user", "content": "unrelated current topic"})
    tui._set_input("/resume")
    tui._submit_buffer(steer=False)

    assert tui._choice_kind == "session"
    assert len(tui._choice_values) == 16  # Every session plus cancel, no reset.
    first = tui._choice_values[0]
    assert first == "now        saved-14  Original session title 14"
    assert tui._choice_values[1] == "now        saved-13  [ACTIVE] Original session title 13"
    assert tui._panel.page.breadcrumb == ("Sessions",)
    assert tui._panel.page.column_headers == ("Session", "Age", "Session ID")
    row = tui._panel.row()
    assert row.label == "Original session title 14"
    assert row.value == "now"
    assert row.description == "saved-14"
    fragments = tui._panel_body_fragments()
    assert ("class:choice.active.edge", "[") in fragments
    assert ("class:choice.active.word", "ACTIVE") in fragments
    assert ("class:choice.active.edge", "]") in fragments
    tui._set_input("ACTIVE")
    tui._refresh_choice_filter()
    assert tui._picker.selected_id == "session:saved-13"
    assert tui._panel.row().label_badge == "ACTIVE"
    tui._set_input("")
    tui._refresh_choice_filter()
    tui._panel.picker.focus("session:saved-14")
    tui._apply_picker_state()
    assert tui.memory.release_session_lease("saved-13", "other-client", "active-turn")
    tui._refresh_resume_choices()
    assert tui._choice_values[1] == "now        saved-13  Original session title 13"
    assert tui._choice_index == 0
    tui._accept_choice()

    assert tui.session_id == "saved-14"
    assert tui.agent.messages == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "Original session title 14"},
        {"role": "assistant", "content": "Saved answer"},
    ]
    assert "Saved answer" in tui.output.text
    assert tui._history == ["Original session title 14"]
    assert len(tui.memory.load_session("saved-14")) == 2
    tui.agent.run = lambda _message, *, scope=None: iter(
        [AgentEvent("text", {"content": "Next answer"})]
    )
    tui._run_turn("Follow-up", threading.Event())
    dialogue = [
        turn
        for turn in tui.memory.load_session("saved-14")
        if turn["role"] in {"user", "assistant"}
    ]
    assert dialogue[-2:] == [
        {"role": "user", "content": "Follow-up"},
        {"role": "assistant", "content": "Next answer"},
    ]


def test_active_session_badge_uses_green_edges_and_dark_text():
    style = _tui_style("autumn", "vscode-dark")
    edge = style.get_attrs_for_style_str("class:choice.active.edge")
    word = style.get_attrs_for_style_str("class:choice.active.word")

    assert edge.color == edge.bgcolor == "55d985"
    assert word.bgcolor == "55d985"
    assert word.color != "55d985"


def test_recent_session_formats_put_active_badge_before_name():
    sessions = [
        {
            "date": "2026-09-09 12:00",
            "session_id": "abc123",
            "turns": 2,
            "preview": "latest reply",
            "title": "Parser investigation",
            "active": True,
        }
    ]

    expected = "2026-09-09 12:00  abc123  2 turns  [ACTIVE] Parser investigation"
    assert _format_recent_sessions(sessions) == expected
    styled = _styled_recent_sessions(sessions)
    assert styled.plain == expected
    assert any("55d985" in str(span.style) for span in styled.spans)


def test_resume_cancel_empty_and_missing_preserve_session(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._open_resume()
    assert "No saved sessions yet" in tui.output.text
    tui.memory.log_turn("saved", "user", "Previous conversation")
    tui._open_resume()
    tui._cancel_choice()
    assert tui.session_id == "session-1"
    tui._resume_session("missing")
    assert "No saved session: missing" in tui.output.text
    assert tui.session_id == "session-1"
    assert tui.agent.messages == [{"role": "system", "content": "system prompt"}]


def test_invalid_resume_target_does_not_interrupt_active_worker(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.running = True
    tui.pending.append("Queued instruction")

    tui._resume_session("missing")

    assert tui.session_id == "session-1"
    assert tui.running
    assert not tui.cancel_requested.is_set()
    assert list(tui.pending) == ["Queued instruction"]
    assert "No saved session: missing" in tui.output.text


def test_second_batch_chat_commands_show_status_memory_skills_and_recap(tmp_path, monkeypatch):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.remember("Prefer concise answers")
    tui.agent.messages = [{"role": "system", "content": "system"}]
    tui.agent.compact_now = lambda: None
    monkeypatch.setattr("klaude_cli.main._chat_skills", lambda _cfg: "installed skills:\n- demo")

    def submit(command):
        tui._set_input(command)
        tui._submit_buffer(steer=False)

    submit("/status")
    submit("/memory")
    submit("/memory off")
    submit("/skills")
    submit("/recap")
    submit("/compact")
    output = tui.output.text
    assert "Session ID    session-1" in output
    assert "Prefer concise answers" in output
    assert "auto memory: off" in output
    assert "installed skills:" in output
    assert "Session session-1" in output
    assert "[context] compacted" in output


def test_status_submission_clears_exact_match_completion_popup(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._set_input("/status")
    tui._keep_exact_command_completion(tui.input.buffer)

    assert tui.input.buffer.complete_state is not None
    tui._submit_buffer(steer=False)

    assert tui.input.text == ""
    assert tui.input.buffer.complete_state is None


def test_debug_label_previews_every_label_style_without_waiting_for_idle(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.running = True
    tui._set_input("/debug_label")
    tui._keep_exact_command_completion(tui.input.buffer)

    tui._submit_buffer(steer=False)

    assert tui.input.text == ""
    assert tui.input.buffer.complete_state is None
    assert not tui.pending
    for label in (
        "[status]",
        "[appearance]",
        "[runtime]",
        "[permission · run_shell]",
        "[input · klaude]",
        "[secret · ollama service]",
        "[debug]",
        "[composer]",
        "[context]",
        "[recap]",
        "[memory]",
        "[skills]",
        "[diff]",
        "[settings]",
        "[session]",
        "[export]",
        "[hint]",
        "[workspace]",
        "[workspace listing]",
        "[ollama]",
        "[attached]",
        "[queued]",
        "[queued action]",
        "[pending turns]",
        "[steer queued]",
        "[you · steer]",
        "[worked]",
        "[explored]",
        "[edited]",
        "[ran]",
        "[unchanged]",
        "[committed]",
        "[answered]",
        "[approved]",
        "[denied]",
        "[cancelled]",
        "[warning]",
        "[interrupted]",
        "[interrupted at a safe boundary]",
        "[failed]",
        "[error]",
        "[success]",
        "[memory saved]",
    ):
        assert label in tui.output.text
    assert "[status] Neutral session information\n\n[appearance]" in tui.output.text
    assert "[memory saved] Green saved-memory notice\n\n" in tui.output.text


def test_debug_label_rejects_arguments(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui._set_input("/debug_label extra")

    tui._submit_buffer(steer=False)

    assert "[error] /debug_label takes no arguments." in tui.output.text


def test_debug_label_includes_cycling_footer_preview_without_starting_ai(tmp_path, monkeypatch):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    clock = {"now": 100.0}
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: clock["now"])
    tui._set_input("/debug_label")

    tui._submit_buffer(steer=False)

    assert not tui.running
    assert tui._debug_label_started_at == 100.0
    assert "[status] Neutral session information" in tui.output.text
    assert "worked for 1m 11s" in tui.output.text
    status = "".join(text for _style, text in tui._status_fragments())
    assert "⠋ WORKING" in status
    assert "1m 11s" in status

    clock["now"] = 102.1
    status = "".join(text for _style, text in tui._status_fragments())
    assert f"{tui.appearance.spinner.animation.frame_at(102.1)} EXPLORING" in status
    assert "1m 13s" in status

    tui._set_input("/debug_label")
    tui._submit_buffer(steer=False)
    assert tui._debug_label_started_at is None
    assert "★ READY" in "".join(text for _style, text in tui._status_fragments())


def test_clear_erases_only_terminal_view_and_keeps_live_session_state(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.log_turn(tui.session_id, "user", "Saved question")
    tui.agent.messages.append({"role": "user", "content": "Model context"})
    tui.pending.append("Queued follow-up")
    tui.running = True
    tui._append("Old visible transcript\n")
    original_messages = list(tui.agent.messages)

    tui._set_input("/clear")
    tui._keep_exact_command_completion(tui.input.buffer)
    tui._submit_buffer(steer=False)

    assert tui.output.text == ""
    assert tui.live_output.text == ""
    assert tui.input.text == ""
    assert tui.input.buffer.complete_state is None
    assert tui.session_id == "session-1"
    assert tui.agent.messages == original_messages
    assert list(tui.pending) == ["Queued follow-up"]
    assert tui.running
    assert [turn["content"] for turn in tui.memory.load_session(tui.session_id)] == [
        "Saved question"
    ]


def test_clear_rejects_arguments_without_erasing_transcript(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui._append("Keep this visible\n")
    tui._set_input("/clear now")

    tui._submit_buffer(steer=False)

    assert "Keep this visible" in tui.output.text
    assert "[error] /clear takes no arguments." in tui.output.text


def test_plan_mode_toggles():
    tui = _fake_persistent_tui()
    assert _plan_command(tui.agent, "on").startswith("Plan mode on")
    assert tui.agent.plan_mode
    assert _plan_command(tui.agent, "off").startswith("Plan mode off")
    assert not tui.agent.plan_mode


def test_bare_resume_opens_picker_without_interrupting_active_worker(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.log_turn("saved", "user", "Saved conversation")
    tui.agent.restore_session = lambda turns: Agent.restore_session(tui.agent, turns)
    tui.running = True
    tui.pending.append("queued follow-up")
    tui._set_input("/resume")
    tui._submit_buffer(steer=False)

    assert tui._choice_kind == "session"
    assert tui.running
    assert not tui.cancel_requested.is_set()
    assert list(tui.pending) == ["queued follow-up"]


def test_resume_command_bypasses_permission_prompt_while_worker_is_active(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.log_turn("saved", "user", "Saved conversation")
    tui.running = True
    tui._permission_request = {
        "tool": "run_shell",
        "answer": "n",
        "done": threading.Event(),
    }
    tui._set_input("/resume")
    enter = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.Enter,)
    )

    enter(None)

    assert tui._choice_kind == "session"
    assert tui._permission_request is not None
    assert not tui.cancel_requested.is_set()


def test_switching_from_remote_input_prompt_detaches_without_answering(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.log_turn("saved", "user", "Saved conversation")
    tui.agent.restore_session = lambda turns: Agent.restore_session(tui.agent, turns)
    tui._watching_remote = True
    tui._user_input_request = {
        "request_id": "remote-request",
        "question": "Choose one",
        "options": [],
        "remote": True,
        "turn_id": "remote-turn",
    }

    tui._resume_session("saved")

    assert tui.session_id == "saved"
    assert tui._user_input_request is None
    assert not any(
        turn["role"] == "system"
        and isinstance(turn["content"], dict)
        and turn["content"].get("event") == "input_answer"
        for turn in tui.memory.load_session("session-1")
    )


def test_cancelling_resume_picker_restarts_queue_if_worker_finished(tmp_path, monkeypatch):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.log_turn("saved", "user", "Saved conversation")
    started = []
    tui.running = True
    tui.pending.append("queued follow-up")
    tui._open_resume()
    tui.running = False
    monkeypatch.setattr(tui, "_start_next", lambda: started.append("next"))

    tui._cancel_choice()

    assert tui._choice_kind is None
    assert list(tui.pending) == ["queued follow-up"]
    assert started == ["next"]


def test_resume_target_interrupts_then_switches_at_safe_boundary(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.log_turn("saved", "user", "Saved conversation")
    tui.agent.restore_session = lambda turns: Agent.restore_session(tui.agent, turns)
    tui.running = True
    tui.pending.append("queued follow-up")
    tui._set_input("/resume saved")
    tui._submit_buffer(steer=False)

    assert tui._pending_resume == "saved"
    assert tui.session_id == "session-1"
    assert tui.running
    assert tui.cancel_requested.is_set()
    assert not tui.pending
    assert "Discarded 1 queued item(s)" in tui.output.text
    tui._events.put(("turn_done", {"cancelled": True}))
    tui._before_render(tui.application)
    assert not tui.running
    assert tui._pending_resume is None
    assert tui.session_id == "saved"


def test_cancel_releases_permission_wait():
    tui = _fake_persistent_tui()
    tui.cancel_requested.set()
    assert tui._ask_permission("read_file", "read pending") == "n"
    tui._before_render(tui.application)
    assert tui._permission_request is None


def test_session_commands_rename_fork_export_and_new_preserve_original(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.agent.workdir = tmp_path
    tui.agent.restore_session = lambda turns: Agent.restore_session(tui.agent, turns)
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.log_turn("session-1", "user", "Original question")
    tui.memory.log_turn("session-1", "assistant", "```python\nprint(1)\n```")
    tui.agent.restore_session(tui.memory.load_session("session-1"))
    original = list(tui.agent.messages)

    def submit(command):
        tui._set_input(command)
        tui._submit_buffer(steer=False)

    submit("/rename Parser work")
    assert tui.memory.resumable_sessions()[0]["title"] == "Parser work"
    submit("/fork")
    fork_id = tui.session_id
    assert fork_id != "session-1"
    assert tui.agent.messages == original
    assert tui.memory.load_session(fork_id) == tui.memory.load_session("session-1")
    tui.memory.log_turn(fork_id, "user", "Fork only")
    assert len(tui.memory.load_session("session-1")) == 2
    submit("/export conversation.md")
    exported = (tmp_path / "conversation.md").read_text()
    assert "Parser work (fork)" in exported
    assert "```python\nprint(1)\n```" in exported
    submit("/export conversation.md")
    assert (tmp_path / "conversation.md").read_text() == exported
    assert "[error]" in tui.output.text
    submit("/new")
    assert tui.session_id not in {fork_id, "session-1"}
    assert tui.agent.messages == original[:1]
    assert fork_id not in tui.output.text
    assert "Original question" not in tui.output.text
    assert tui.session_id in tui.output.text
    assert len(tui.memory.load_session(fork_id)) == 3


def test_diff_includes_staged_unstaged_and_untracked_names(tmp_path):
    import subprocess

    from klaude_cli.main import _workspace_diff

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "tracked.txt").write_text("staged\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked.txt"], check=True)
    (tmp_path / "tracked.txt").write_text("unstaged\n")
    (tmp_path / "new.txt").write_text("untracked content\n")
    result = _workspace_diff(SimpleNamespace(workdir=tmp_path))
    assert "Staged changes" in result and "+staged" in result
    assert "Unstaged changes" in result and "+unstaged" in result
    assert "Untracked files (names only)" in result and "new.txt" in result


def test_review_dispatches_read_only_turn(tmp_path, monkeypatch):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    monkeypatch.setattr("klaude_cli.main._workspace_diff", lambda _agent: "staged diff")
    started = []
    monkeypatch.setattr(tui, "_start_next", lambda: started.append(tui._review_next))
    tui._set_input("/review")
    tui._submit_buffer(steer=False)
    assert started == [True]
    assert "staged diff" in tui.pending[0]
    assert tui.pending[0].scope is TurnScope.REVIEW


def test_init_dispatches_scoped_repository_guidance_turn(tmp_path, monkeypatch):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.agent.workdir = tmp_path
    started = []
    monkeypatch.setattr(tui, "_start_next", lambda: started.append(True))
    tui._set_input("/init")

    tui._submit_buffer(steer=False)

    assert started == [True]
    assert str(tui.pending[0]) == "/init"
    assert tui.pending[0].scope is TurnScope.INIT
    request = tui.pending[0].model_message
    assert request == _init_request(tui.agent)
    assert request is not None
    assert str(tmp_path / "AGENTS.md") in request
    tools = {
        name: object()
        for name in (
            "read_file",
            "list_dir",
            "grep",
            "workspace_info",
            "write_file",
            "edit_file",
            "git_commit",
            "run_shell",
            "web_search",
        )
    }
    selected = _select_tool_names(request, tools)
    assert selected == [
        "read_file",
        "list_dir",
        "grep",
        "workspace_info",
        "write_file",
        "edit_file",
    ]


def test_init_line_mode_keeps_generated_task_out_of_public_user_message(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.agent.workdir = tmp_path
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    cfg = Config()
    rendered = []
    monkeypatch.setattr(Config, "data_dir", property(lambda _self: tmp_path))
    monkeypatch.setattr("klaude_cli.main.load_config", lambda: cfg)
    monkeypatch.setattr("klaude_cli.main._build_agent", lambda *_args: (tui.agent, memory))
    monkeypatch.setattr(
        "klaude_cli.main._render",
        lambda _agent, _memory, _session_id, user_message, _ui_state, **kwargs: rendered.append(
            (user_message, kwargs.get("model_message"), kwargs.get("scope"))
        ),
    )

    result = CliRunner().invoke(app, ["chat", "--no-tui"], input="/init\n/quit\n")

    assert result.exit_code == 0, result.output
    assert rendered == [("/init", _init_request(tui.agent), TurnScope.INIT)]


def test_resume_line_mode_lists_and_restores_without_sending_command_to_model(
    tmp_path,
    monkeypatch,
):
    from typer.testing import CliRunner

    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("saved", "user", "Earlier question")
    memory.log_turn("saved", "assistant", "Earlier reply")
    tui.agent.restore_session = lambda turns: Agent.restore_session(tui.agent, turns)
    cfg = Config()
    monkeypatch.setattr(Config, "data_dir", property(lambda _self: tmp_path))
    monkeypatch.setattr("klaude_cli.main.load_config", lambda: cfg)
    monkeypatch.setattr("klaude_cli.main._build_agent", lambda *_args: (tui.agent, memory))

    result = CliRunner().invoke(
        app,
        ["chat", "--no-tui"],
        input="/resume\n/resume saved\n/quit\n",
    )

    assert result.exit_code == 0, result.output
    assert "saved" in result.output
    assert "Earlier question" in result.output
    assert "Earlier reply" in result.output
    assert tui.agent.messages[-1] == {"role": "assistant", "content": "Earlier reply"}
    assert len(memory.load_session("saved")) == 2


def test_completed_assistant_message_has_unit_duration_in_closing_divider(monkeypatch):
    tui = _fake_persistent_tui()
    emitted = []
    tui._turn_started_at = 100.0
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 171.0)
    tui.agent.run = lambda _message, *, scope=None: iter(
        [AgentEvent("text_delta", {"content": "Hi!"})]
    )
    tui.memory.log_turn = lambda *_args: None
    tui.memory.auto_remember_turn = lambda _message: []
    tui._emit = lambda kind, payload=None: emitted.append((kind, payload))

    tui._run_turn("hello", threading.Event())

    closing = [payload for kind, payload in emitted if kind == "append"][-1]
    assert closing.startswith("\n\n━━ klaude · ")
    assert "worked for 1m 11s" in closing
    assert closing.endswith("\n")


def test_edit_group_is_flushed_saved_and_mirrored_at_end_of_turn(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._turn_elapsed_seconds = lambda: 30
    events = []
    for path in ("first.py", "second.py"):
        payload = {"tool": "write_file", "args": {"path": path}}
        events.append(AgentEvent("tool_start", payload))
        events.append(
            AgentEvent(
                "tool_result",
                {
                    **payload,
                    "result": "wrote file",
                    "metadata": {
                        "edit": {
                            "path": path,
                            "added": 1,
                            "removed": 0,
                            "lines": ["      1 + answer = 42"],
                            "changed": True,
                        }
                    },
                },
            )
        )
    tui.agent.run = lambda _message, *, scope=None: iter(events)
    tui._run_turn("Make two files", threading.Event(), turn_id="edit-turn")
    saved = tui.memory.load_session(tui.session_id)
    summaries = [
        turn["content"]
        for turn in saved
        if isinstance(turn["content"], dict) and turn["content"].get("event") == "edit_summary"
    ]
    assert len(summaries) == 1
    assert "[edited] (30s) 2 files (+2 -0)" in summaries[0]["text"]
    shared = tui.memory.session_events_since(tui.session_id, 0)
    assert any(event["kind"] == "edit_summary" for event in shared)


def test_run_turn_persists_real_tool_activity_milestones(tmp_path, monkeypatch):
    tui = _fake_persistent_tui()
    tui._turn_started_at = 100.0
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 130.0)
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.agent.run = lambda _message, *, scope=None: iter(
        [
            AgentEvent(
                "tool_start",
                {
                    "tool": "read_file",
                    "args": {"path": "src/app.py"},
                    "execution_id": "execution-1",
                },
            ),
            AgentEvent(
                "tool_result",
                {
                    "tool": "read_file",
                    "args": {"path": "src/app.py"},
                    "result": "file contents",
                    "metadata": {"execution_id": "execution-1", "executed": True},
                },
            ),
            AgentEvent("text", {"content": "Reviewed."}),
        ]
    )
    emitted = []
    original_emit = tui._emit

    def capture(kind, payload=None):
        emitted.append((kind, payload))
        original_emit(kind, payload)

    tui._emit = capture

    tui._run_turn("Review the file", threading.Event(), turn_id="turn-1")

    updates = [
        turn["content"]
        for turn in tui.memory.load_session(tui.session_id)
        if turn["role"] == "system"
        and isinstance(turn["content"], dict)
        and turn["content"].get("event") == "activity_update"
    ]
    assert updates == [
        {
            "event": "activity_update",
            "label": "explored",
            "detail": "Read src/app.py",
            "elapsed_seconds": 30,
        },
    ]
    appended = "".join(str(payload) for kind, payload in emitted if kind == "append")
    assert "[working]" not in appended
    assert "[explored] (30s) Read src/app.py" in appended
    assert "-> read_file" not in appended
    shared = tui.memory.session_events_since(tui.session_id, 0)
    audits = [event["payload"] for event in shared if event["kind"] == "tool_audit"]
    assert [(audit["phase"], audit["execution_id"]) for audit in audits] == [
        ("start", "execution-1"),
        ("result", "execution-1"),
    ]
    kinds = [event["kind"] for event in shared]
    assert kinds.index("tool_audit", kinds.index("tool_audit") + 1) < kinds.index(
        "activity_update"
    ) < kinds.index("turn_done")


def test_run_turn_persists_bounded_research_receipt_without_result_text(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.agent.run = lambda _message, *, scope=None: iter([
        AgentEvent("tool_start", {
            "tool": "query_knowledge", "args": {"query": "Godot movement"},
            "execution_id": "research-1",
        }),
        AgentEvent("tool_result", {
            "tool": "query_knowledge", "args": {"query": "Godot movement"},
            "result": "PRIVATE GODOT CHUNK",
            "metadata": {"execution_id": "research-1", "executed": True,
                         "library": "godot", "found": True, "result_count": 1},
        }),
        AgentEvent("text", {"content": "Found a source."}),
    ])

    tui._run_turn("Find Godot movement", threading.Event(), turn_id="research-turn")

    receipts = [
        turn["content"] for turn in tui.memory.load_session(tui.session_id)
        if turn["role"] == "system" and isinstance(turn["content"], dict)
        and turn["content"].get("event") == "research_receipt"
    ]
    assert len(receipts) == 1
    assert receipts[0]["query"] == "Godot movement"
    assert receipts[0]["library"] == "godot"
    assert "PRIVATE GODOT CHUNK" not in str(receipts[0])


def test_run_turn_mirrors_live_capability_snapshots(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    snapshot = {
        "globally_enabled_tools": ["read_file"],
        "callable_tools": ["read_file"],
        "effective_permissions": {"read_file": "allow"},
        "budget": {"model_steps_used": 1, "max_model_steps": 20},
    }
    def run(_message, *, scope=None):
        tui.agent.capability_observer(snapshot)
        return iter([AgentEvent("text", {"content": "Done."})])

    tui.agent.run = run

    tui._run_turn("Inspect", threading.Event(), turn_id="turn-1")

    events = tui.memory.session_events_since(tui.session_id, 0)
    capability_events = [event for event in events if event["kind"] == "capabilities"]
    assert len(capability_events) == 1
    assert capability_events[0]["payload"]["snapshot"] == snapshot
    assert [event["kind"] for event in events].index("capabilities") < [
        event["kind"] for event in events
    ].index("turn_done")


def test_run_turn_persists_and_mirrors_subagent_lifecycle(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    emitted = []
    original_emit = tui._emit

    def capture(kind, payload=None):
        emitted.append((kind, payload))
        original_emit(kind, payload)

    tui._emit = capture

    def run(_message, *, scope=None):
        tui.agent.subagent_event_observer(
            SubagentEvent("subagent_started", "child-1", SubagentRole.READ_RESEARCH)
        )
        tui.agent.subagent_event_observer(
            SubagentEvent(
                "subagent_finished",
                "child-1",
                SubagentRole.READ_RESEARCH,
                SubagentStatus.COMPLETED,
                model_steps=2,
                tool_calls=1,
                tools_used=("read_file",),
            )
        )
        return iter([AgentEvent("text", {"content": "Done."})])

    tui.agent.run = run

    tui._run_turn("Delegate inspection", threading.Event(), turn_id="turn-1")

    saved = [
        turn["content"]
        for turn in tui.memory.load_session(tui.session_id)
        if turn["role"] == "system"
        and isinstance(turn["content"], dict)
        and turn["content"].get("event") == "subagent_activity"
    ]
    assert [event["kind"] for event in saved] == [
        "subagent_started",
        "subagent_finished",
    ]
    assert saved[1]["tools_used"] == ["read_file"]
    shared = tui.memory.session_events_since(tui.session_id, 0)
    subagent_events = [event["payload"] for event in shared if event["kind"] == "subagent"]
    assert [event["kind"] for event in subagent_events] == [
        "subagent_started",
        "subagent_finished",
    ]
    assert any(
        kind == "append" and "[explored] read/research subagent completed" in str(payload)
        for kind, payload in emitted
    )


def test_transcript_dividers_refresh_after_resize():
    tui = _fake_persistent_tui()
    timestamp = datetime(2026, 9, 5, 12, 34, 56)
    initial = f"hello\n{_message_divider('you', width=80, timestamp=timestamp)}\n"
    tui.output.buffer.set_document(Document(initial, len(initial)), bypass_readonly=True)
    tui.output.window.render_info = SimpleNamespace(window_width=48)

    tui._refresh_transcript_dividers()

    refreshed = next(line for line in tui.output.text.splitlines() if line.startswith("━━ you · "))
    assert len(refreshed) == 47
    assert refreshed.startswith("━━ you · 2026-09-05 12:34:56 ")


def test_command_reference_metadata_renders_preformatted(monkeypatch):
    printed = []

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    _print_assistant_text(
        "Usage: klaude [OPTIONS] [COMMAND] [ARGS]...\n\nCLI COMMANDS\n",
        {"content_type": "command_reference", "preserve_whitespace": True},
    )

    assert isinstance(printed[0][0][0], Text)
    assert "\n\nCLI COMMANDS\n" in printed[0][0][0].plain


def test_normal_assistant_text_renders_as_markdown(monkeypatch):
    printed = []

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    _print_assistant_text("**hello**")

    assert isinstance(printed[0][0][0], Markdown)


def test_terminal_assistant_text_uses_styled_panel_and_code_theme(monkeypatch):
    printed = []

    class FakeTerminalConsole:
        is_terminal = True

        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    monkeypatch.setattr("klaude_cli.main.console", FakeTerminalConsole())

    _print_assistant_text("```python\nprint('hello')\n```")

    panel = printed[0][0][0]
    assert isinstance(panel, Panel)
    assert isinstance(panel.renderable, Markdown)
    assert panel.border_style == "#3aa7c4"


def test_plain_assistant_text_has_no_terminal_panel(monkeypatch):
    printed = []

    class FakeTerminalConsole:
        is_terminal = True

        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    monkeypatch.setattr("klaude_cli.main.console", FakeTerminalConsole())

    _print_assistant_text("**hello**", plain=True)

    assert isinstance(printed[0][0][0], Markdown)


def test_chat_toolbar_shows_model_effort_context_and_last_tokens():
    state = ChatUIState(
        model="gpt-oss:20b",
        effort="low",
        context_window=8192,
        prompt_tokens=2048,
        output_tokens=512,
    )

    rendered = "".join(fragment for _style, fragment in _chat_toolbar(state))

    assert "gpt-oss:20b" in rendered
    assert "mode low" in rendered
    assert "ctx 2,048/8,192 (25%)" in rendered
    assert "last ↑2,048 ↓512" in rendered


def test_welcome_logo_is_boxed_aligned_and_uses_installed_version():
    lines = _klaude_logo().splitlines()

    assert len(lines) == 12
    assert {len(line) for line in lines} == {69}
    assert lines[0].startswith("╔") and lines[0].endswith("╗")
    assert lines[-1].startswith(f"╚════ v{package_version('klaude-cli')} ")
    assert lines[-1].endswith("╝")


def test_transcript_lexer_and_theme_apply_primary_color_to_the_tui_logo():
    logo = _klaude_logo()
    fragments = TranscriptLexer().lex_document(Document(logo))(0)
    color = (
        _tui_style("autumn", "vscode-dark").get_attrs_for_style_str("class:transcript.logo").color
    )

    assert fragments == [("class:transcript.logo", logo.splitlines()[0])]
    assert color == "f59a78"


def test_transcript_lexer_styles_ai_activity_labels_and_mutes_tool_activity():
    document = Document("[reasoning] drafting response\n-> web_search")
    get_line = TranscriptLexer().lex_document(document)

    assert get_line(0) == [
        ("class:transcript.label.info.edge", "["),
        ("class:transcript.label.info.word", "REASONING"),
        ("class:transcript.label.info.edge", "]"),
        ("", " drafting response"),
    ]
    assert get_line(1) == [("class:transcript.activity", "-> web_search")]


def test_transcript_lexer_styles_semantic_and_informational_notice_labels():
    document = Document(
        "[error] connection failed\n"
        "[failed] request failed\n"
        "[warning] partial results\n"
        "[success] request completed\n"
        "[memory saved] durable preference\n"
        "[appearance] text/code theme: Monokai\n"
        "[runtime] edited config.toml\n"
        "[status] session details\n"
        "[interrupted at a safe boundary] user cancelled\n"
        "[approved] run shell\n"
        "[denied] write file\n"
        "[cancelled] permission request\n"
        "[permission · Ollama service] Restart the service?"
    )
    get_line = TranscriptLexer().lex_document(document)

    def badge(kind: str, label: str, body: str):
        return [
            (f"class:transcript.label.{kind}.edge", "["),
            (f"class:transcript.label.{kind}.word", label),
            (f"class:transcript.label.{kind}.edge", "]"),
            ("", body),
        ]

    assert get_line(0) == badge("failed", "ERROR", " connection failed")
    assert get_line(1) == badge("failed", "FAILED", " request failed")
    assert get_line(2) == badge("warning", "WARNING", " partial results")
    assert get_line(3) == badge("success", "SUCCESS", " request completed")
    assert get_line(4) == badge("success", "MEMORY SAVED", " durable preference")
    assert get_line(5) == badge("info", "APPEARANCE", " text/code theme: Monokai")
    assert get_line(6) == badge("info", "RUNTIME", " edited config.toml")
    assert get_line(7) == badge("info", "STATUS", " session details")
    assert get_line(8) == badge("warning", "INTERRUPTED AT A SAFE BOUNDARY", " user cancelled")
    assert get_line(9) == badge("success", "APPROVED", " run shell")
    assert get_line(10) == badge("warning", "DENIED", " write file")
    assert get_line(11) == badge("warning", "CANCELLED", " permission request")
    assert get_line(12) == badge("info", "PERMISSION · OLLAMA SERVICE", " Restart the service?")


def test_notice_label_theme_uses_footer_brand_foreground_and_semantic_backgrounds():
    style = _tui_style("crimson-red", "vscode-dark")
    footer_brand = style.get_attrs_for_style_str("class:footer.brand")

    expected_backgrounds = {
        "info": "9a9197",
        "warning": "f3c84b",
        "failed": "ff6574",
        "success": "55d985",
    }
    for kind, expected_background in expected_backgrounds.items():
        edge = style.get_attrs_for_style_str(f"class:transcript.label.{kind}.edge")
        word = style.get_attrs_for_style_str(f"class:transcript.label.{kind}.word")
        word_on_user_surface = style.get_attrs_for_style_str(
            f"class:output-field class:transcript.user-message class:transcript.label.{kind}.word"
        )
        assert edge.color == edge.bgcolor == expected_background
        assert word.bgcolor == expected_background
        assert word.color == footer_brand.color
        assert word_on_user_surface.bgcolor == expected_background
        assert word_on_user_surface.color == footer_brand.color


def test_slash_completer_lists_every_command_immediately_after_slash():
    completions = list(ChatCommandCompleter().get_completions(Document("/"), None))
    commands = {completion.text for completion in completions}

    assert commands == {
        spec.usage.split()[0] for spec in iter_command_specs(CommandSurface.CHAT) if spec.visible
    }
    assert "/keybinds" in commands
    assert "/quit" not in commands
    assert "/q" not in commands
    assert list(ChatCommandCompleter().get_completions(Document("say /"), None)) == []


def test_completion_rows_highlight_the_characters_that_match_the_typed_prefix(tmp_path):
    source = tmp_path / "stopwatch.md"
    source.write_text("context")
    command = next(
        item
        for item in ChatCommandCompleter().get_completions(Document("/sto"), None)
        if item.text == "/stop"
    )
    attachment = next(
        ChatCommandCompleter(workdir_provider=lambda: tmp_path).get_completions(
            Document("Review @sto"), None
        )
    )

    for completion, matched in ((command, "/sto"), (attachment, "sto")):
        fragments = list(completion.display)
        assert ("class:suggestion-match-text", matched) in fragments
        assert any(
            style == "class:suggestion-unmatched-text" and text.strip() for style, text in fragments
        )
        assert "".join(text for _style, text in fragments) == completion.display_text


def test_attachment_suggestions_start_muted_and_brighten_only_when_selected(tmp_path):
    source = tmp_path / "stopwatch.md"
    source.write_text("context")
    completer = ChatCommandCompleter(workdir_provider=lambda: tmp_path)
    for prompt in ("/attach ", "Review @"):
        completion = next(completer.get_completions(Document(prompt), None))
        assert list(completion.display) == [
            ("class:suggestion-unmatched-text", completion.display_text)
        ]

    typed = next(completer.get_completions(Document("Review @sto"), None))
    fragments = list(typed.display)
    assert fragments[0][0] == "class:suggestion-unmatched-text"
    assert ("class:suggestion-match-text", "sto") in fragments

    from prompt_toolkit.styles import merge_styles
    from prompt_toolkit.styles.defaults import default_ui_style

    style = merge_styles([default_ui_style(), _tui_style("autumn", DEFAULT_TEXT_THEME)])
    muted = style.get_attrs_for_style_str(
        "class:completion-menu.completion class:suggestion-unmatched-text"
    )
    selected = style.get_attrs_for_style_str(
        "class:completion-menu.completion.current class:suggestion-unmatched-text"
    )
    composer = style.get_attrs_for_style_str("class:input-field")
    assert muted.color != composer.color
    assert selected.color == composer.color


def test_completion_match_color_and_selected_background_follow_composer():
    from prompt_toolkit.styles import merge_styles
    from prompt_toolkit.styles.defaults import default_ui_style

    # Prompt Toolkit merges its own menu styles before application styles.
    # The regression only appears in that real composition.
    style = merge_styles([default_ui_style(), _tui_style("autumn", DEFAULT_TEXT_THEME)])
    matched = style.get_attrs_for_style_str(
        "class:completion-menu.completion class:suggestion-match-text"
    )
    row = style.get_attrs_for_style_str("class:completion-menu.completion")
    composer = style.get_attrs_for_style_str("class:input-field")
    status_text = style.get_attrs_for_style_str("class:runtime_text")
    unmatched = style.get_attrs_for_style_str(
        "class:completion-menu.completion class:suggestion-unmatched-text"
    )

    assert matched.color == composer.color
    assert matched.bgcolor == row.bgcolor
    assert unmatched.color == status_text.color
    assert unmatched.bgcolor == row.bgcolor

    selected = style.get_attrs_for_style_str("class:completion-menu.completion.current")
    panel_selected = style.get_attrs_for_style_str("class:panel.selected")
    assert selected.color == composer.color
    assert row.bgcolor == panel_selected.bgcolor
    assert composer.bgcolor is not None
    assert row.bgcolor is not None
    assert selected.bgcolor is not None
    assert all(
        int(composer.bgcolor[index : index + 2], 16)
        < int(row.bgcolor[index : index + 2], 16)
        < int(selected.bgcolor[index : index + 2], 16)
        for index in (0, 2, 4)
    )
    assert not selected.bold
    assert not selected.underline

    selected_match = style.get_attrs_for_style_str(
        "class:completion-menu.completion.current class:suggestion-match-text"
    )
    assert selected_match.color == composer.color
    assert selected_match.bgcolor == selected.bgcolor
    assert not selected_match.bold
    assert not selected_match.underline

    selected_unmatched = style.get_attrs_for_style_str(
        "class:completion-menu.completion.current class:suggestion-unmatched-text"
    )
    assert selected_unmatched.color == composer.color
    assert selected_unmatched.bgcolor == selected.bgcolor

    meta = style.get_attrs_for_style_str("class:completion-menu.meta.completion")
    selected_meta = style.get_attrs_for_style_str(
        "class:completion-menu.meta.completion.current"
    )
    assert meta.bgcolor == row.bgcolor
    assert selected_meta.bgcolor == selected.bgcolor


@pytest.mark.parametrize(
    "theme", ["autumn", "crimson-red", "neon-synth", "pastelle-pink", "hacker-green"]
)
@pytest.mark.parametrize("prompt", ["/sto", "/attach st", "Review @st"])
def test_every_completion_source_uses_the_same_selected_surface(tmp_path, prompt, theme):
    from prompt_toolkit.styles import merge_styles
    from prompt_toolkit.styles.defaults import default_ui_style

    (tmp_path / "stopwatch.md").write_text("context")
    completion = next(ChatCommandCompleter(
        workdir_provider=lambda: tmp_path
    ).get_completions(Document(prompt), None))
    assert completion.display_text

    style = merge_styles([default_ui_style(), _tui_style(theme, DEFAULT_TEXT_THEME)])
    selected = style.get_attrs_for_style_str(
        "class:completion-menu.completion.current class:suggestion-unmatched-text"
    )
    composer = style.get_attrs_for_style_str("class:input-field")
    menu = style.get_attrs_for_style_str("class:completion-menu.completion")
    panel_selected = style.get_attrs_for_style_str("class:panel.selected")
    assert menu.bgcolor == panel_selected.bgcolor
    assert composer.bgcolor is not None
    assert menu.bgcolor is not None
    assert selected.bgcolor is not None
    assert all(
        int(composer.bgcolor[index : index + 2], 16)
        < int(menu.bgcolor[index : index + 2], 16)
        < int(selected.bgcolor[index : index + 2], 16)
        for index in (0, 2, 4)
    )


def test_inline_attachment_mentions_complete_and_supply_file_or_folder_context(tmp_path):
    folder = tmp_path / "project notes"
    folder.mkdir()
    source = folder / "brief.md"
    source.write_text("Keep this context.")

    completer = ChatCommandCompleter(workdir_provider=lambda: tmp_path)
    folder_completions = list(completer.get_completions(Document("Review @pro"), None))
    assert any(completion.text == '"project notes/"' for completion in folder_completions)

    tui = _fake_persistent_tui()
    tui.agent.workdir = tmp_path
    paths = tui._inline_attachment_paths('Review @"project notes/brief.md" and @"project notes".')
    context = tui._attachment_context(paths)

    assert paths == (source.resolve(), folder.resolve())
    assert "[Attached file:" in context
    assert "Keep this context." in context
    assert "[Attached folder:" in context
    assert "brief.md" in context


def test_attachment_completion_expands_home_without_workspace_relative_crash(
    tmp_path, monkeypatch
):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    (home / "notes.md").write_text("notes")
    (home / "docs").mkdir()
    (home / "docs" / "guide.md").write_text("guide")
    monkeypatch.setenv("HOME", str(home))
    completer = ChatCommandCompleter(workdir_provider=lambda: workspace)

    for prompt in ("/attach ~", "Review @~"):
        completions = list(completer.get_completions(Document(prompt), None))
        assert [item.text for item in completions] == ["~/"]
        assert completions[0].start_position == -1
    assert [item.text for item in completer.get_completions(
        Document('/attach "~'), None
    )] == ['~/"']
    for prompt in ("/attach ~/", "Review @~/"):
        values = {
            item.text for item in completer.get_completions(Document(prompt), None)
        }
        assert {"~/docs/", "~/notes.md"}.issubset(values)
    assert [item.text for item in completer.get_completions(
        Document("/attach ~/docs/"), None
    )] == ["~/docs/guide.md"]
    assert list(completer.get_completions(Document("/attach ~no-such-user"), None)) == []


def test_tui_composer_completion_for_tilde_does_not_crash(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    tui = _fake_persistent_tui()
    tui.agent.workdir = workspace

    async def complete():
        tui._set_input("/attach ~")
        await tui.input.buffer._async_completer()

    asyncio.run(complete())
    state = tui.input.buffer.complete_state
    assert state is not None
    assert [item.text for item in state.completions] == ["~/"]


def test_attachment_completion_handles_parent_and_trailing_directory_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "sibling.md").write_text("sibling")
    folder = workspace / "docs"
    folder.mkdir()
    (folder / "guide.md").write_text("guide")
    completer = ChatCommandCompleter(workdir_provider=lambda: workspace)

    parent = list(completer.get_completions(Document("/attach ../sib"), None))
    assert [item.text for item in parent] == ["../sibling.md"]
    nested = list(completer.get_completions(Document("/attach docs/"), None))
    assert [item.text for item in nested] == ["docs/guide.md"]


@pytest.mark.parametrize("fragment", ["", "s", "src/klaude", '"project notes/'])
def test_inline_attachment_completion_is_anchored_at_the_at_sign(fragment):
    tui = _fake_persistent_tui()
    original = Document("Review this @" + fragment)
    tui._set_input(original.text)
    buffer = tui.input.buffer
    buffer.complete_state = CompletionState(
        original,
        [
            Completion('"project notes/"', start_position=-len(fragment)),
            Completion("src/", start_position=-len(fragment)),
        ],
        complete_index=None,
    )

    assert tui.input.control.menu_position() == len("Review this @")
    for index in (0, 1, None):
        buffer.go_to_completion(index)
        assert tui.input.control.menu_position() == len("Review this @")


def test_exact_command_completion_survives_automatic_completion_and_enter(monkeypatch):
    tui = _fake_persistent_tui()
    submitted = []
    monkeypatch.setattr(tui, "_submit_buffer", lambda **kw: submitted.append(tui.input.text))

    async def type_command():
        tui._set_input("/sto")
        await tui.input.buffer._async_completer()
        tui.input.buffer.insert_text("p", fire_event=False)
        await tui.input.buffer._async_completer()

    asyncio.run(type_command())
    state = tui.input.buffer.complete_state
    assert state is not None
    assert [item.text for item in state.completions] == ["/stop"]
    accept = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if binding.handler.__name__ == "accept"
    )
    accept(None)
    assert submitted == ["/stop"]


@pytest.mark.parametrize("key", [(Keys.Backspace,), (Keys.ControlH,)])
def test_backspace_reopens_inline_attachment_completion(monkeypatch, key):
    tui = _fake_persistent_tui()
    tui._set_input("Review @src")
    starts = []
    monkeypatch.setattr(
        tui.input.buffer,
        "start_completion",
        lambda **kwargs: starts.append(kwargs),
    )
    delete = next(
        binding.handler for binding in tui.key_bindings.bindings if tuple(binding.keys) == key
    )

    delete(None)

    assert tui.input.text == "Review @sr"
    assert starts == [{"select_first": False}]


def test_inline_attachment_mention_is_delivered_with_its_message(tmp_path, monkeypatch):
    source = tmp_path / "brief.md"
    source.write_text("Use this brief.")
    tui = _fake_persistent_tui()
    tui.agent.workdir = tmp_path
    delivered: list[tuple[str, str | None, TurnScope | str | None]] = []
    delivered_event = threading.Event()

    def capture(
        message,
        _cancel_event,
        *,
        model_message=None,
        read_only=False,
        scope=None,
        turn_id="",
    ):
        delivered.append((message, model_message, scope))
        delivered_event.set()

    monkeypatch.setattr(tui, "_run_turn", capture)
    tui._enqueue("Please review @brief.md.")

    assert delivered_event.wait(1)
    assert delivered == [
        (
            "Please review @brief.md.",
            f"Please review @brief.md.\n\n[Attached file: {source.resolve()}]\nUse this brief.",
            TurnScope.STANDARD,
        )
    ]


def test_picker_disables_slash_command_suggestions():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", ["theme", "cancel"], "theme")
    tui._set_input("/")

    completions = list(tui.input.completer.get_completions(tui.input.document, None))

    assert completions == []


def test_keybind_reference_contains_only_keyboard_controls():
    reference = format_chat_keybind_reference(width=100)

    assert "\nKEYBOARD\n" in reference
    assert "  Enter" in reference
    assert "  Alt+\\" in reference
    assert "  Alt+Enter" in reference
    assert "  Ctrl+J" in reference
    assert "  Ctrl+C" in reference
    assert "CHAT COMMANDS" not in reference
    assert "/help" not in reference
    assert "/settings" not in reference
    assert "\n--------\n" not in reference


def test_persistent_tui_keybinds_command_renders_without_model_call():
    tui = _fake_persistent_tui()
    tui._set_input("/keybinds")

    tui._submit_buffer(steer=False)

    assert "Klaude chat controls" in tui.output.text
    assert "KEYBOARD" in tui.output.text
    assert "/text-theme [NAME]" not in tui.output.text
    assert tui.running is False


def test_persistent_tui_registers_modified_enter_and_interrupt_bindings():
    tui = _fake_persistent_tui()
    handlers = {
        tuple(binding.keys): binding.handler.__name__ for binding in tui.key_bindings.bindings
    }

    assert (Keys.ControlM,) in handlers
    assert handlers[(Keys.Escape, Keys.ControlM)] == "newline"
    assert handlers[(Keys.ControlJ,)] == "newline"
    assert handlers[(Keys.Escape, "\\")] == "steer"
    assert (Keys.ControlC,) in handlers


def test_large_bracketed_paste_is_compact_but_submits_full_text(monkeypatch):
    tui = _fake_persistent_tui()
    pasted = "first line\n" + "x" * LARGE_PASTE_CHARACTER_THRESHOLD
    submitted = []
    monkeypatch.setattr(tui, "_enqueue", lambda text, **_kwargs: submitted.append(text))
    paste = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.BracketedPaste,)
    )

    async def insert_paste():
        paste(SimpleNamespace(data=pasted))
        await asyncio.sleep(0)

    asyncio.run(insert_paste())

    assert tui.input.text == f"[Pasted {len(pasted):,} chars]"
    assert tui._expanded_composer_text() == pasted
    tui._submit_buffer(steer=False)
    assert submitted == [pasted]
    assert tui._history == [pasted]
    assert tui.input.text == ""
    assert tui._composer_pastes == []


def test_small_bracketed_paste_remains_editable_and_normalizes_newlines():
    tui = _fake_persistent_tui()
    paste = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.BracketedPaste,)
    )

    async def insert_paste():
        paste(SimpleNamespace(data="one\r\ntwo\rthree"))
        await asyncio.sleep(0)

    asyncio.run(insert_paste())

    assert tui.input.text == "one\ntwo\nthree"
    assert tui._composer_pastes == []


def test_terminal_bracketed_paste_uses_compact_composer_marker():
    async def exercise():
        tui = _fake_persistent_tui()
        pasted = "z" * LARGE_PASTE_CHARACTER_THRESHOLD
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                pipe.send_text(f"\x1b[200~{pasted}\x1b[201~")
                await asyncio.sleep(0.1)
                assert tui.input.text == "[Pasted 1,000 chars]"
                assert tui._expanded_composer_text() == pasted
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_persistent_tui_restores_enhanced_keyboard_mode_on_failure(monkeypatch, tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    writes = []
    monkeypatch.setattr(tui.application.output, "write_raw", writes.append)
    monkeypatch.setattr(tui.application.output, "flush", lambda: None)
    monkeypatch.setattr(
        tui.application.output,
        "get_size",
        lambda: SimpleNamespace(rows=4),
    )

    def fail_after_pre_run(pre_run):
        pre_run()
        raise RuntimeError("render failed")

    monkeypatch.setattr(tui.application, "run", fail_after_pre_run)

    with pytest.raises(RuntimeError, match="render failed"):
        tui.run()

    assert tui._background_jobs.requests["status-metadata"]["kind"] == "status_metadata"
    assert writes == [
        TERMINAL_CLEAR_SEQUENCE,
        "\r\n" * 3,
        KITTY_KEYBOARD_PROTOCOL_ON,
        XTERM_MODIFY_OTHER_KEYS_ON,
        XTERM_MODIFY_OTHER_KEYS_OFF,
        KITTY_KEYBOARD_PROTOCOL_OFF,
    ]


def test_interactive_chat_clears_terminal_before_loading_configuration(monkeypatch):
    import klaude_cli.main as cli_main

    events = []
    monkeypatch.setattr(cli_main.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_main.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        cli_main,
        "_clear_plain_session_view",
        lambda **_kwargs: events.append("clear"),
    )

    def stop_after_clear():
        events.append("load config")
        raise RuntimeError("stop after startup-order check")

    monkeypatch.setattr(cli_main, "load_config", stop_after_clear)

    with pytest.raises(RuntimeError, match="startup-order check"):
        cli_main.chat(model="", legacy=False, no_tui=False)

    assert events == ["clear", "load config"]


def test_session_effort_supports_explicit_levels():
    class FakeAgent:
        model = "gpt-oss:20b"
        ollama_think = None
        ollama_code_think = None

    agent = FakeAgent()
    cfg = Config()

    _apply_session_effort(agent, cfg, "high")
    assert agent.ollama_think == "high"
    assert agent.ollama_code_think == "high"

    _apply_session_effort(agent, cfg, "off")
    assert agent.ollama_think is False
    assert agent.ollama_code_think is False

    _apply_session_effort(agent, cfg, "auto")
    assert agent.ollama_think is False
    assert agent.ollama_code_think is False


def _fake_persistent_tui(appearance_path=None, chat_preferences_path=None):
    class FakeOllama:
        last_chat_metadata = {}

        def list_models(self):
            return ["qwen3.5:4b", "gpt-oss:20b"]

        def cancel_active(self):
            return False

    class FakeAgent:
        class FakeGate:
            def set_ask_callback(self, ask):
                self.ask = ask

        model = "qwen3.5:4b"
        ollama = FakeOllama()
        gate = FakeGate()
        messages = [{"role": "system", "content": "system prompt"}]
        ollama_options = {"num_ctx": 8192}
        max_steps = 20
        ollama_think = None
        ollama_code_think = "low"
        tool_config = Config()

    class FakeMemory:
        def log_turn(self, *_args, **_kwargs):
            return None

        def remember(self, fact, source="manual"):
            return True

        def latest_session_event_id(self, _session_id):
            return 0

        def acquire_session_lease(self, _session_id, _client_id, _turn_id):
            return True

        def renew_session_lease(self, _session_id, _client_id, _turn_id):
            return True

        def release_session_lease(self, _session_id, _client_id, _turn_id, **_kwargs):
            return True

        def update_session_live(self, session_id, **updates):
            return {
                "session_id": session_id,
                "revision": 1,
                "owner_client_id": updates.get("owner_client_id", ""),
                "owner_lease_until": updates.get("owner_lease_until", 0.0),
                "turn_id": updates.get("turn_id", ""),
                "state": updates.get("state", "idle"),
                "draft_client_id": updates.get("draft_client_id", ""),
                "draft": updates.get("draft", ""),
                "activity": updates.get("activity", "ready"),
                "partial": updates.get("partial", ""),
                "queue": updates.get("queue_json", []),
                "updated_at": 0.0,
            }

        def update_session_client(self, _session_id, _client_id, *, draft, queue):
            self.client_state = {"draft": draft, "queue": queue}

        def session_client_states(self, _session_id):
            return []

        def session_live_state(self, session_id):
            return self.update_session_live(session_id)

        def session_events_since(self, _session_id, _cursor):
            return []

        def start_session_turn(self, *_args, **_kwargs):
            return 1

        def publish_session_event(self, *_args, **_kwargs):
            return 1

    tui = PersistentChatTUI(
        FakeAgent(),
        FakeMemory(),
        "session-1",
        Config(),
        appearance_path=appearance_path,
        chat_preferences_path=chat_preferences_path,
    )

    class FakeJobs:
        def __init__(self):
            self.latest = {}
            self.requests = {}

        def submit(self, key, request, *, timeout=30):
            import uuid

            identity = uuid.uuid4().hex
            self.latest[key] = identity
            self.requests[key] = request
            return identity

        def current(self, key, identity):
            return self.latest.get(key) == identity

        def cancel(self, key):
            self.latest.pop(key, None)

        def close(self, *, wait=False):
            self.latest.clear()

    tui._background_jobs.close()
    tui._background_jobs = FakeJobs()
    tui._skill_discovery.jobs = tui._background_jobs
    class FakeSessionIO:
        def __init__(self):
            self.requests = []

        def submit(self, request):
            self.requests.append(request)

        def switch_scope(self, session_id, client_id):
            self.requests.clear()

        def close(self, *, wait=False):
            pass

    tui._session_io = FakeSessionIO()
    class FakeSessionActions:
        def __init__(self):
            self.requests = []

        def submit(self, action):
            from klaude_cli.session_actions import AutomaticMemoryUpdate

            self.requests.append(action)
            if isinstance(action, AutomaticMemoryUpdate):
                tui.memory.set_auto_memory(action.enabled)
                tui._emit("memory_setting_saved", (action, True))
                return True
            tui.memory.log_turn(action.session_id, "system", {
                "event": "session_update", "detail": action.detail,
            })
            tui._publish_shared_event("session_update", {"detail": action.detail}, turn_id="")
            return True

        def close(self, *, wait=False):
            return True

    tui._session_actions = FakeSessionActions()
    tui._skill_actions.close()
    class FakeSkillActions:
        def watch(self):
            pass

        def submit(self, action):
            return False

        def close(self, *, wait=False):
            return True

    tui._skill_actions = FakeSkillActions()
    tui._skill_inbox_preparation_attempted = True
    class UnconfiguredMCPMutations:
        """Never let a default fake TUI write real MCP configuration."""
        path = tui.cfg.mcp_servers_file

        def submit(self, request):
            return False

        def close(self, *, wait=False):
            return True

    tui._mcp_mutations.close()
    tui._mcp_mutations = UnconfiguredMCPMutations()
    class SynchronousSettingsWriter:
        """Immediate test adapter; production uses the serialized worker."""

        def __init__(self):
            self.revision = 0

        def submit(self, changes):
            from klaude_cli.settings_writer import public_tool_settings
            from klaude_core.settings_store import update_settings

            self.revision += 1
            try:
                saved = update_settings(tui.chat_preferences_path, changes)
            except OSError:
                tui._emit("settings_saved", (self.revision, False))
            else:
                tui._emit("settings_saved", (self.revision, True))
                tui._emit("settings_permissions", (self.revision, saved.get("permissions", {})))
                tui._emit("settings_tools", (self.revision, public_tool_settings(saved)))
            return self.revision

        def close(self, *, wait=False):
            return True

    tui._settings_writer = SynchronousSettingsWriter()
    class SynchronousAppearanceWriter:
        revision = 0

        def submit(self, changes):
            from klaude_cli.main import _migrate_appearance
            from klaude_core.settings_store import update_settings

            self.revision += 1
            try:
                update_settings(tui.appearance_path, changes, prepare=_migrate_appearance)
            except OSError:
                tui._emit("appearance_saved", (self.revision, False))
            else:
                tui._emit("appearance_saved", (self.revision, True))
            return self.revision

        def close(self, *, wait=False):
            return True

    tui._appearance_writer = SynchronousAppearanceWriter()
    return tui


def test_tui_transport_cancellation_never_leaks_provider_close_errors():
    tui = _fake_persistent_tui()

    def raising_cancel():
        raise OSError("provider close failed")

    tui.agent.ollama.cancel_active = raising_cancel

    assert tui._cancel_active_transport() is False


def test_resumed_tuis_share_live_composers_without_overwriting_each_other(tmp_path):
    database = tmp_path / "sessions.db"
    first = _fake_persistent_tui()
    second = _fake_persistent_tui()
    first.memory = Memory(tmp_path / "memory.md", database)
    second.memory = Memory(tmp_path / "memory.md", database)

    first._set_input("draft from first")
    first.pending.append("queued by first")
    first._publish_live_composer()
    second._set_input("draft from second")
    second._publish_live_composer()

    first._sync_shared_session()
    second._sync_shared_session()

    assert first._remote_draft == "draft from second"
    assert second._remote_draft == "draft from first"
    assert second._remote_queue == ["queued by first"]
    assert first.input.text == "draft from first"
    assert second.input.text == "draft from second"


def test_resumed_observer_status_tracks_remote_worker_lease(tmp_path, monkeypatch):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.log_turn("shared", "user", "Long-running request")
    assert memory.acquire_session_lease("shared", "remote-owner", "remote-turn")
    started_at = time.time() - 36
    memory.update_session_live("shared", activity="web_search", turn_started_at=started_at)
    memory.publish_session_event(
        "shared",
        "remote-owner",
        "capabilities",
        {
            "snapshot": {
                "globally_enabled_tools": ["read_file", "web_search"],
                "callable_tools": ["web_search"],
                "effective_permissions": {"read_file": "allow", "web_search": "allow"},
                "budget": {
                    "model_steps_used": 2,
                    "max_model_steps": 20,
                    "tool_calls_used": 1,
                    "max_tool_calls": 40,
                    "elapsed_seconds": 36,
                },
            }
        },
        turn_id="remote-turn",
    )
    monkeypatch.setattr("klaude_cli.main.time.time", lambda: started_at + 36)
    observer = _fake_persistent_tui(tmp_path / "appearance.json")
    observer.memory = memory
    observer.agent.restore_session = lambda turns: Agent.restore_session(observer.agent, turns)

    observer._resume_session("shared")

    assert not observer.running
    assert observer._watching_remote
    status = "".join(text for _style, text in observer._status_fragments())
    assert "EXPLORING" in status
    assert "36s" in status
    assert "READY" not in status
    assert observer.agent.last_turn_capabilities["callable_tools"] == ["web_search"]
    assert observer.agent.last_turn_budget["model_steps_used"] == 2

    assert memory.release_session_lease("shared", "remote-owner", "remote-turn")
    observer._sync_shared_session()

    assert not observer._watching_remote
    status = "".join(text for _style, text in observer._status_fragments())
    assert "READY" in status
    assert "WORKING" not in status


def test_resumed_observer_durably_recovers_an_expired_remote_turn(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    assert memory.acquire_session_lease("shared", "remote-owner", "remote-turn")
    memory.start_session_turn(
        "shared", "remote-owner", "remote-turn", "Long-running request"
    )
    memory.publish_session_event(
        "shared",
        "remote-owner",
        "assistant_delta",
        {"text": "Partial remote answer"},
        turn_id="remote-turn",
    )
    observer = _fake_persistent_tui(tmp_path / "appearance.json")
    observer.memory = memory
    observer.agent.restore_session = lambda turns: Agent.restore_session(observer.agent, turns)
    observer._resume_session("shared")
    assert observer._watching_remote

    memory.update_session_live("shared", owner_lease_until=time.time() - 1)
    observer._sync_shared_session()

    assert not observer._watching_remote
    assert memory.session_live_state("shared")["state"] == "interrupted"
    done = [
        event
        for event in memory.session_events_since("shared", 0)
        if event["kind"] == "turn_done"
    ]
    assert len(done) == 1
    assert done[0]["payload"]["recovered"] is True
    assert "[interrupted] worker lease expired before completion" in observer.output.text
    assert "saved output is preserved" in observer.output.text


def test_resumed_observer_receives_structured_activity_updates(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    observer = _fake_persistent_tui(tmp_path / "appearance.json")
    observer.memory = memory
    observer.session_id = "shared"
    observer._session_event_cursor = 0
    memory.publish_session_event(
        "shared",
        "remote-owner",
        "activity_update",
        {"label": "explored", "detail": "Read src/app.py", "elapsed_seconds": 8},
        turn_id="remote-turn",
    )

    observer._sync_shared_session()

    assert "[explored] (8s) Read src/app.py" in observer.output.text


def test_resumed_observer_receives_subagent_lifecycle(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    observer = _fake_persistent_tui(tmp_path / "appearance.json")
    observer.memory = memory
    observer.session_id = "shared"
    observer._session_event_cursor = 0
    memory.publish_session_event(
        "shared",
        "remote-owner",
        "subagent",
        {
            "kind": "subagent_started",
            "task_id": "child-1",
            "role": "read_research",
        },
        turn_id="remote-turn",
    )

    observer._sync_shared_session()

    assert observer.activity == "exploring read/research subagent"
    memory.publish_session_event(
        "shared",
        "remote-owner",
        "subagent",
        {
            "kind": "subagent_finished",
            "task_id": "child-1",
            "role": "read_research",
            "status": "completed",
            "model_steps": 2,
        },
        turn_id="remote-turn",
    )

    observer._sync_shared_session()

    assert "[explored] read/research subagent completed (2 model steps)" in observer.output.text


def test_tools_settings_persist_independent_validation_toggles(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)

    tui._open_settings_category("tools")
    assert tui._choice_kind == "tools settings"
    tui._choice_index = tui._choice_values.index("web search validation: on (toggle)")
    tui._accept_choice()

    saved = json.loads(path.read_text())
    assert saved["tool_validation"] == {"web_search": False}
    # Only the edited field is persisted; missing availability values retain
    # their enabled defaults without replacing another client's choices.
    assert "tool_availability" not in saved
    assert tui.agent.tool_config.web_search.result_validation_enabled is False
    assert tui.agent.tool_config.retrieval_validation_enabled is True
    assert tui._choice_values[tui._choice_index] == "web search validation: off (toggle)"


def test_permission_command_opens_grouped_settings_and_replaces_plural_command(tmp_path):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")
    tui._set_input("/permission")

    tui._submit_buffer(steer=False)

    assert tui._choice_kind == "permission settings"
    assert "Current configuration: BALANCED" in tui._choice_values
    assert "Write file: ASK" in tui._choice_values
    assert "Web search: ALLOW" in tui._choice_values
    assert "Remember fact: ASK" in tui._choice_values
    assert "Delegate read-only task: ASK" in tui._choice_values
    assert tui._choice_values.index("reset to default") < tui._choice_values.index("back")

    tui._cancel_choice()
    tui._cancel_choice()
    tui._set_input("/permissions")
    tui._submit_buffer(steer=False)
    assert tui._choice_kind is None
    assert "Unknown chat command: /permissions" in tui.output.text


def test_permission_policy_values_use_semantic_green_yellow_red_styles():
    from klaude_core.mcp_client import namespaced_tool_name

    tui = _fake_persistent_tui()
    tui.agent.gate.policies = {"write_file": "deny"}
    page = tui._permission_panel_page()
    rows = {row.id: row for row in page.rows}
    assert rows["tool:web_search"].value_tone == "success"
    assert rows["tool:edit_file"].value_tone == "warning"
    assert rows["tool:write_file"].value_tone == "error"

    tool = namespaced_tool_name("firecrawl", "search")
    tui.agent.tools = {tool: SimpleNamespace(description="MCP server firecrawl: search")}
    tui.agent.gate.policies[tool] = "deny"
    server_page = tui._mcp_permission_servers_page()
    detail_page = tui._mcp_permission_detail_page("firecrawl")
    assert detail_page is not None
    assert next(
        row for row in server_page.rows if row.id == "server:firecrawl"
    ).value_tone == "error"
    detail_rows = {row.id: row for row in detail_page.rows}
    assert detail_rows["server-heading"].description == "Current policy  DENY"
    assert detail_rows[f"mcp-tool:{tool}"].value_tone == "error"

    style = _tui_style("autumn", DEFAULT_TEXT_THEME)
    colors = [
        style.get_attrs_for_style_str(f"class:panel.value.{tone}").color
        for tone in ("success", "warning", "error")
    ]
    assert len(set(colors)) == 3
    for tone, color in zip(("success", "warning", "error"), colors, strict=True):
        selected = style.get_attrs_for_style_str(
            f"class:panel.selected class:panel.value.{tone}"
        )
        assert selected.color == color


def test_permission_preset_preview_colors_policy_values_only():
    tui = _fake_persistent_tui()
    tui._show_permission_preview(
        "Workspace\nRead file       ALLOW\nWrite file      ASK\nRun shell       DENY"
    )
    lexer = tui.text_theme_preview.control.lexer
    lines = lexer.lex_document(tui.text_theme_preview.buffer.document)
    for number, policy, tone in (
        (1, "ALLOW", "success"),
        (2, "ASK", "warning"),
        (3, "DENY", "error"),
    ):
        fragments = lines(number)
        assert fragments[-1] == (f"class:panel.value.{tone}", policy)
        assert fragments[0][0] == ""
    assert lines(0) == [("", "Workspace")]

    tui._hide_permission_preview()
    assert lexer.get_lexer().get_lexer() is tui._text_preview_lexer


def test_permission_rows_cycle_persist_and_detect_custom_configuration(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)
    tui._open_settings_category("permissions")
    tui._choice_index = tui._choice_values.index("Write file: ASK")

    tui._accept_choice()

    saved = json.loads(path.read_text())
    assert saved["permissions"]["write_file"] == "allow"
    assert tui.agent.gate.policies["write_file"] == "allow"
    assert "Current configuration: CUSTOM" in tui._choice_values
    assert tui._choice_values[tui._choice_index] == "Write file: ALLOW"


def test_mcp_permissions_group_by_server_and_offer_scoped_bulk_controls(tmp_path):
    from klaude_core.mcp_client import namespaced_tool_name

    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)
    tools = {
        namespaced_tool_name(server, remote): SimpleNamespace(
            description=f"MCP server {server}: {remote}"
        )
        for server, remote in (
            ("context7", "resolve_library"),
            ("context7", "get_docs"),
            ("firecrawl", "search"),
        )
    }
    tui.agent.tools = tools
    tui._open_settings_category("permissions")

    assert not any("MCP" in row for row in tui._choice_values)
    assert not any("resolve library:" in row for row in tui._choice_values)
    tui._open_settings_category("mcp servers")
    tui._choice_index = tui._choice_values.index("Permissions")
    tui._accept_choice()
    assert tui._choice_kind == "mcp permission servers"
    assert "context7: ASK · 2 tools" in tui._choice_values
    assert "firecrawl: ASK · 1 tool" in tui._choice_values
    tui._choice_index = tui._choice_values.index("context7: ASK · 2 tools")
    tui._accept_choice()
    assert tui._choice_kind == "mcp permission tools"
    heading = tui._panel.page.rows[0]
    assert heading.label == "SERVER:"
    assert heading.description == "Current policy  ASK"
    assert not any(row.id == "current-policy" for row in tui._panel.page.rows)
    heading_line = tui._panel_body().lines[0]
    assert ("class:panel.muted", "  Current policy  ASK") in heading_line
    assert "resolve library: ASK" in tui._choice_values
    assert {"ALLOW ALL", "ASK FOR EACH TOOL", "DENY ALL"}.issubset(tui._choice_values)
    bulk_rows = [
        row for row in tui._panel.page.rows
        if row.action is not None and row.action.kind == "mcp-bulk"
    ]
    assert {row.label for row in bulk_rows} == {
        "Allow all", "Ask for each tool", "Deny all"
    }
    assert all(row.value == "" and row.description for row in bulk_rows)
    assert "[ Apply ]" not in "".join(
        text for line in tui._panel_body().lines for _style, text in line
    )

    tui._choice_index = tui._choice_values.index("ALLOW ALL")
    tui._accept_choice()
    context_tools = [name for name in tools if "context7" in name]
    firecrawl_tool = next(name for name in tools if "firecrawl" in name)
    assert all(tui.agent.gate.policies[name] == "allow" for name in context_tools)
    assert tui.agent.gate.policies.get(firecrawl_tool, "ask") == "ask"
    saved = json.loads(path.read_text())["permissions"]
    assert all(saved[name] == "allow" for name in context_tools)
    assert firecrawl_tool not in saved

    tui._choice_index = tui._choice_values.index("resolve library: ALLOW")
    tui._accept_choice()
    assert tui._panel.page.rows[0].description == "Current policy  CUSTOM"
    assert any(tui.agent.gate.policies[name] == "deny" for name in context_tools)
    tui._choice_index = tui._choice_values.index("DENY ALL")
    tui._accept_choice()
    assert all(tui.agent.gate.policies[name] == "deny" for name in context_tools)
    tui._choice_index = tui._choice_values.index("ASK FOR EACH TOOL")
    tui._accept_choice()
    assert all(tui.agent.gate.policies[name] == "ask" for name in context_tools)
    assert tui.agent.gate.policies.get(firecrawl_tool, "ask") == "ask"
    tui._choice_index = tui._choice_values.index("back")
    tui._accept_choice()
    assert tui._choice_kind == "mcp permission servers"
    tui._choice_index = tui._choice_values.index("back")
    tui._accept_choice()
    assert tui._choice_kind == "mcp settings"
    assert tui._choice_values[tui._choice_index] == "Permissions"


def test_mcp_settings_shortcut_focuses_server_permissions(tmp_path):
    from klaude_core.mcp_client import namespaced_tool_name

    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")
    name = namespaced_tool_name("firecrawl", "search")
    tui.agent.tools = {name: SimpleNamespace(description="MCP server firecrawl: search")}
    tui._mcp_inventory = {"servers": [], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    tui._open_settings_category("mcp servers")
    heading = next(row for row in tui._panel.page.rows if row.label == "MCP Servers")
    assert heading.description.startswith("0 installed, 0 enabled · Configuration snapshot ")
    assert not any(row.label.startswith("Configuration snapshot ") for row in tui._panel.page.rows)
    tui._choice_index = tui._choice_values.index("Permissions")
    tui._accept_choice()
    assert tui._choice_kind == "mcp permission servers"
    assert tui._choice_values[tui._choice_index] == "firecrawl: ASK · 1 tool"
    tui._choice_index = tui._choice_values.index("back")
    tui._accept_choice()
    assert tui._choice_kind == "mcp settings"
    assert tui._choice_values[tui._choice_index] == "Permissions"


def test_mcp_permission_groups_keep_original_server_identity(tmp_path):
    from klaude_core.mcp_client import namespaced_tool_name

    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")
    servers = ("context7.prod", "context7_prod")
    tui.agent.tools = {
        namespaced_tool_name(server, "search"): SimpleNamespace(
            description=f"MCP server {server}: search"
        )
        for server in servers
    }
    tui._open_settings_category("mcp servers")
    tui._choice_index = tui._choice_values.index("Permissions")
    tui._accept_choice()
    assert all(f"{server}: ASK · 1 tool" in tui._choice_values for server in servers)


def test_permission_preset_picker_previews_grouped_policies_and_applies_preset(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)
    tui._open_settings_category("permissions")
    tui._choice_index = tui._choice_values.index("Current configuration: BALANCED")
    tui._accept_choice()

    assert tui._choice_kind == "permission preset"
    assert tui._choice_values[0] == "Custom"
    assert tui._choice_values[tui._choice_index] == "Balanced"
    assert tui._permission_preview_visible
    preview = tui.text_theme_preview.text
    assert "Workspace\n" in preview
    assert "\n\nGit\n" in preview
    assert "\n\nWeb & Research\n" in preview
    assert "Write file" in preview and "ASK" in preview
    assert "Web search" in preview and "ALLOW" in preview
    assert tui._choice_values.index("reset to default") < tui._choice_values.index("back")

    tui._move_choice(-1)
    assert tui._choice_values[tui._choice_index] == "Custom"
    unavailable_fragments = tui._choice_fragments()
    assert ("class:choice.disabled.selected", "  › Custom\n") in unavailable_fragments
    tui._accept_choice()
    assert tui._choice_kind == "permission preset"
    assert tui._choice_values[tui._choice_index] == "Custom"

    tui._choice_index = tui._choice_values.index("Balanced")
    tui._apply_choice_preview()

    tui._choice_index = tui._choice_values.index("reset to default")
    tui._apply_choice_preview()
    reset_preview = tui.text_theme_preview.text
    assert "RESET TO DEFAULT" in reset_preview
    assert "configured default policy" in reset_preview
    reset_write_line = next(
        line for line in reset_preview.splitlines() if line.startswith("Write file")
    )
    assert reset_write_line.endswith("ASK")

    tui._choice_index = tui._choice_values.index("Full Access")
    tui._apply_choice_preview()
    assert "FULL ACCESS" in tui.text_theme_preview.text
    tui._accept_choice()

    assert not tui._permission_preview_visible
    assert "Current configuration: FULL ACCESS" in tui._choice_values
    assert set(json.loads(path.read_text())["permissions"].values()) == {"allow"}


def test_permission_preset_picker_selects_custom_and_previews_current_map(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)
    tui._open_settings_category("permissions")
    tui._choice_index = tui._choice_values.index("Write file: ASK")
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("Current configuration: CUSTOM")
    tui._accept_choice()

    assert tui._choice_values[tui._choice_index] == "Custom"
    assert "CUSTOM" in tui.text_theme_preview.text
    write_line = next(
        line for line in tui.text_theme_preview.text.splitlines() if line.startswith("Write file")
    )
    assert write_line.endswith("ALLOW")


def test_permission_reset_removes_saved_overrides_and_restores_configured_defaults(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)
    tui._open_settings_category("permissions")
    tui._choice_index = tui._choice_values.index("Write file: ASK")
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("reset to default")

    tui._accept_choice()

    assert "permissions" not in json.loads(path.read_text())
    assert tui.agent.gate.policies["write_file"] == "ask"
    assert "Current configuration: BALANCED" in tui._choice_values
    assert tui._choice_values[tui._choice_index] == "reset to default"


def test_rebuilding_any_settings_page_preserves_its_selected_logical_row(tmp_path):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    for category, selected in (
        ("theme", "text/code theme:"),
        ("input field", "border:"),
        ("memory", "automatic memory:"),
        ("providers", "OpenRouter:"),
        ("tools", "web search validation:"),
        ("permissions", "Write file:"),
        ("runtime", "CPU threads:"),
    ):
        tui._open_settings_category(category)
        row = next(value for value in tui._choice_values if value.startswith(selected))
        tui._choice_index = tui._choice_values.index(row)

        tui._open_settings_category(category)

        assert tui._choice_values[tui._choice_index].startswith(selected)


def test_settings_include_memory_skills_and_provider_categories():
    tui = _fake_persistent_tui()

    categories = tui._settings_categories()

    assert "\0section:APPEARANCE" in categories
    assert "\0section:ASSISTANT" in categories
    assert "\0section:CAPABILITIES & SAFETY" in categories
    assert "\0section:ADVANCED" in categories
    assert any(value.startswith("Models:") for value in categories)
    assert any(value.startswith("Providers:") for value in categories)
    assert any(value.startswith("Memory:") for value in categories)
    assert any(value.startswith("Skills:") for value in categories)
    assert any(value.startswith("Permissions:") for value in categories)
    assert any(value.startswith("Runtime:") for value in categories)
    assert "Divider" in categories
    assert "" not in categories


def test_settings_overview_opens_without_synchronous_memory_or_mcp_reads(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr(
        tui.memory, "auto_memory_enabled", lambda: pytest.fail("UI SQLite read"), raising=False
    )
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: pytest.fail("UI MCP read"))
    tui._begin_choice("settings", tui._settings_categories(), "memory")
    assert any(row == "Memory: loading…" for row in tui._choice_values)
    assert any(row == "MCP servers: loading…" for row in tui._choice_values)
    assert tui._background_jobs.requests["settings-overview"] == {
        "kind": "settings_overview", "sessions_db": "",
        "mcp_file": str(tui.cfg.mcp_servers_file),
        "memory_file": "",
    }


def test_settings_overview_refresh_preserves_selector_and_throttles_retries():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "mcp servers")
    identity = tui._background_jobs.latest["settings-overview"]
    tui._apply_background_result((
        "settings-overview", identity,
        {"memory_enabled": True, "mcp_enabled": 2, "mcp_total": 3}, ""
    ))
    assert tui._choice_values[tui._choice_index] == "MCP servers: 2/3 enabled"
    assert "Memory: on" in tui._choice_values
    assert not tui._settings_overview_request
    tui._begin_choice("settings", tui._settings_categories(), "memory")
    assert tui._background_jobs.latest["settings-overview"] == identity
    tui._settings_overview_checked_at -= 31
    tui._begin_choice("settings", tui._settings_categories(), "memory")
    newer = tui._background_jobs.latest["settings-overview"]
    assert newer != identity
    memory_time = tui._settings_overview.memory_loaded_at
    tui._apply_background_result(("settings-overview", newer, None, "timed out"))
    assert tui._settings_overview.memory_loaded_at == memory_time
    assert any("Memory: on · cached" in row and "unavailable" in row for row in tui._choice_values)
    tui._begin_choice("settings", tui._settings_categories(), "memory")
    assert tui._background_jobs.latest["settings-overview"] == newer


def test_open_settings_overview_refreshes_after_cache_expiry_without_losing_filter():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "mcp servers")
    identity = tui._background_jobs.latest["settings-overview"]
    tui._apply_background_result((
        "settings-overview", identity,
        {"memory_enabled": True, "mcp_enabled": 1, "mcp_total": 3}, ""
    ))
    tui._panel.search_active = True
    tui._set_input("mcp")
    tui._refresh_choice_filter()
    tui._settings_overview_checked_at -= 31
    tui._before_render(None)
    assert tui._background_jobs.latest["settings-overview"] != identity
    assert tui._choice_filter_query == "mcp"
    assert tui._choice_values[tui._choice_index].startswith("MCP servers: 1/3 enabled")
    assert "refreshing" in tui._choice_values[tui._choice_index]


def test_failed_overview_inventory_does_not_disable_category_navigation(monkeypatch):
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "mcp servers")
    tui._apply_background_result((
        "settings-overview", tui._background_jobs.latest["settings-overview"], None, "timed out"
    ))
    assert tui._choice_values[tui._choice_index] == "MCP servers: unavailable"
    opened = []
    monkeypatch.setattr(tui, "_open_settings_category", lambda category: opened.append(category))
    tui._accept_choice()
    assert opened == ["mcp servers"]


@pytest.mark.parametrize("change", ["navigate", "cancel", "session", "storage", "memory"])
def test_settings_overview_late_results_never_replace_newer_state(tmp_path, change):
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "memory")
    identity = tui._background_jobs.latest["settings-overview"]
    if change == "navigate":
        tui._open_settings_category("runtime")
    elif change == "cancel":
        tui._cancel_choice()
    elif change == "session":
        tui.session_id = "another-session"
    elif change == "storage":
        tui.memory.sessions_db = tmp_path / "other.db"
    else:
        tui._invalidate_settings_overview()
        tui._settings_overview = tui._settings_overview.with_memory(False, time.monotonic())
    tui._apply_background_result((
        "settings-overview", identity,
        {"memory_enabled": True, "mcp_enabled": 5, "mcp_total": 5}, ""
    ))
    assert tui._settings_overview.memory_enabled is (False if change == "memory" else None)
    assert tui._settings_overview.mcp_counts is None


def test_live_settings_overview_is_filterable_during_background_read():
    async def exercise():
        tui = _fake_persistent_tui()
        tui._begin_choice("settings", tui._settings_categories(), "mcp servers")
        identity = tui._background_jobs.latest["settings-overview"]
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                pipe.send_text("/mcp")
                await asyncio.sleep(0.15)
                assert tui._choice_filter_query == "mcp"
                assert tui._choice_values[tui._choice_index] == "MCP servers: loading…"
                tui._emit("background_result", (
                    "settings-overview", identity,
                    {"memory_enabled": False, "mcp_enabled": 1, "mcp_total": 2}, ""
                ))
                await asyncio.sleep(0.15)
                assert tui._choice_filter_query == "mcp"
                assert tui._choice_values[tui._choice_index] == (
                    "MCP servers: 1/2 enabled"
                )
                assert tui.panel_body_window.render_info is not None
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("category", "summary_prefix"),
    [
        ("theme", "Theme:"),
        ("input field", "Input field:"),
        ("memory", "Memory:"),
        ("skills", "Skills:"),
        ("providers", "Providers:"),
        ("tools", "Tools:"),
        ("permissions", "Permissions:"),
        ("runtime", "Runtime:"),
    ],
)
def test_settings_back_returns_to_the_same_summary_row(
    category, summary_prefix, tmp_path
):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    tui._open_settings_category(category)
    tui._choice_index = tui._choice_values.index("back")
    tui._accept_choice()

    assert tui._choice_kind == "settings"
    assert tui._choice_values[tui._choice_index].startswith(summary_prefix)


def test_memory_settings_toggle_inventory_without_recent_facts_and_reset(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.remember("Prefer concise answers", source="manual")

    tui._open_settings_category("memory")

    identity = tui._background_jobs.latest["memory-inventory"]
    tui._apply_background_result(("memory-inventory", identity, {
        "enabled": True, "count": 1, "facts": ["Prefer concise answers"], "hidden": 0,
    }, ""))

    assert tui._choice_kind == "memory settings"
    assert "automatic memory: on (toggle)" in tui._choice_values
    heading = next(row for row in tui._panel.page.rows if row.label == "MEMORY")
    assert heading.description.startswith("Saved memories: 1 · snapshot ")
    assert not any(value.startswith("\0info:Durable facts:") for value in tui._choice_values)
    assert "Manage memories" in tui._choice_values
    assert not any("Prefer concise answers" in value for value in tui._choice_values)
    assert not any("RECENT FACTS" in value for value in tui._choice_values)
    tui._choice_index = tui._choice_values.index("automatic memory: on (toggle)")
    tui._accept_choice()
    assert not tui.memory.auto_memory_enabled()
    assert "automatic memory: off (toggle)" in tui._choice_values

    tui._choice_index = tui._choice_values.index("reset to default")
    tui._accept_choice()
    assert tui.memory.auto_memory_enabled()


def test_memory_picker_and_pending_toggles_use_snapshots_without_ui_io(tmp_path, monkeypatch):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    actions = []

    class PendingActions:
        def submit(self, action):
            actions.append(action)
            return True

    tui._session_actions = PendingActions()
    for method in ("list_facts", "auto_memory_enabled", "set_auto_memory"):
        monkeypatch.setattr(tui.memory, method, lambda *args: pytest.fail("UI memory I/O"))
    tui._open_settings_category("memory")
    assert next(row for row in tui._panel.page.rows if row.label == "MEMORY").description == (
        "Loading memory inventory…"
    )
    identity = tui._background_jobs.latest["memory-inventory"]
    tui._apply_background_result(("memory-inventory", identity, {
        "enabled": True, "count": 0, "facts": [], "hidden": 0,
    }, ""))
    for enabled in (False, True, False):
        row = next(value for value in tui._choice_values if value.startswith("automatic memory:"))
        tui._choice_index = tui._choice_values.index(row)
        tui._accept_choice()
        assert actions[-1].enabled is enabled
        assert tui.memory._auto_memory_override is enabled
        assert tui._choice_values[tui._choice_index].startswith("automatic memory:")
    tui._emit("memory_setting_saved", (actions[0], True))
    tui._before_render(None)
    assert tui._memory_save_state == "saving" and tui.memory._auto_memory_override is False
    tui._emit("memory_setting_saved", (actions[-1], False))
    tui._before_render(None)
    assert tui._memory_save_state == "failed" and tui.memory._auto_memory_override is False
    assert "Save unconfirmed" in "".join(text for _, text in tui._panel_footer_fragments())
    assert not any("save unconfirmed" in row for row in tui._choice_values)
    tui._choice_index = tui._choice_values.index(RESET_THEME_CHOICE)
    tui._accept_choice()
    assert actions[-1].enabled is True
    tui._memory_inventory_loaded_at = 0
    tui._open_settings_category("memory")
    old_read = tui._background_jobs.latest["memory-inventory"]
    tui._emit("memory_setting_saved", (actions[-1], True))
    tui._before_render(None)
    assert tui._memory_save_state == "saved" and tui.memory._auto_memory_override is None
    tui._apply_background_result(("memory-inventory", old_read, {
        "enabled": False, "count": 0, "facts": [], "hidden": 0,
    }, ""))
    assert tui._status_memory_enabled is True
    tui.memory.db.close()


def test_memory_inventory_late_and_failed_results_preserve_scope_and_cache(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._open_settings_category("memory")
    identity = tui._background_jobs.latest["memory-inventory"]
    tui._cancel_choice()
    tui._apply_background_result(("memory-inventory", identity, {
        "enabled": True, "count": 1, "facts": ["obsolete"], "hidden": 0,
    }, ""))
    assert tui._memory_inventory is None
    tui._open_settings_category("memory")
    identity = tui._background_jobs.latest["memory-inventory"]
    tui._apply_background_result(("memory-inventory", identity, {
        "enabled": False, "count": 1, "facts": ["cached"], "hidden": 0,
    }, ""))
    saved_time = tui._memory_inventory_loaded_at
    tui._memory_inventory_loaded_at -= 31
    tui._open_settings_category("memory")
    identity = tui._background_jobs.latest["memory-inventory"]
    tui._apply_background_result(("memory-inventory", identity, None, "private failure"))
    assert tui._memory_inventory["facts"] == ["cached"]
    assert tui._memory_inventory_loaded_at == saved_time - 31
    assert "private failure" not in " ".join(tui._choice_values)
    assert any("unavailable" in row for row in tui._choice_values)
    tui.memory.db.close()


def test_skills_settings_show_installed_inventory_and_import_action(monkeypatch):
    from klaude_cli.settings_panel import RowKind

    tui = _fake_persistent_tui()
    installed = [
            {
                "name": "crawl4ai",
                "library": "web-tools",
                "indexed_files": ["SKILL.md", "reference.md"],
            }
    ]

    opened_at = time.monotonic()
    tui._open_settings_category("skills")

    assert time.monotonic() - opened_at < 0.25
    assert tui._choice_kind == "skills settings"
    assert tui._panel.page.rows[0].label == "SKILLS"
    assert next(row for row in tui._panel.page.rows if row.id == "installed").description == (
        "Loading installed skills…"
    )
    identity = tui._background_jobs.latest["skills"]
    tui._events.put(("background_result", (
        "skills", identity, {"skills": installed, "truncated": False}, ""
    )))
    tui._before_render(tui.application)

    assert not tui._skills_inventory_loading
    heading = next(row for row in tui._panel.page.rows if row.id == "installed")
    assert heading.label == "SKILLS"
    assert heading.description == "1 installed, 1 enabled"
    row = next(row for row in tui._panel.page.rows if row.id == "manage")
    assert row.kind == RowKind.NAVIGATION
    assert row.action.kind == "skill-manage"
    assert "Import skills" in tui._choice_values
    assert "reset to default" not in tui._choice_values
    assert tui._choice_values[-1] == "back"
    rendered = "".join(fragment[1] for fragment in tui._panel_body_fragments())
    assert "\0info:" not in rendered
    assert "Manage" in rendered
    tui._skill_feedback = "No new skill file."
    tui._open_settings_category("skills")
    heading = next(row for row in tui._panel.page.rows if row.id == "installed")
    assert heading.description == "1 installed, 1 enabled"
    assert not any(row.id == "feedback" for row in tui._panel.page.rows)


def test_skill_toggle_uses_ordered_action_and_preserves_list_navigation(tmp_path):
    from klaude_cli.skill_actions import SkillAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._skill_inbox_preparation_attempted = True
    tui._skills_inventory = [
        {"name": "alpha", "identity": "a", "library": "alpha", "enabled": True},
        {"name": "beta", "identity": "b", "library": "beta", "enabled": False},
    ]
    submitted = []
    tui._skill_actions.submit = lambda action: submitted.append(action) or True
    tui._open_settings_category("skills")
    tui._panel.picker.focus("manage")
    tui._apply_picker_state()
    tui._accept_choice()
    tui._panel.picker.focus("skill:alpha")
    tui._apply_picker_state()
    tui._accept_choice()
    tui._panel.picker.focus("enabled")
    tui._apply_picker_state()
    tui._activate_panel_toggle()
    assert submitted == [SkillAction("set-enabled", "alpha", "a", enabled=False)]
    assert tui._panel.picker.selected_id == "enabled"
    tui._events.put(("skill_action_done", (submitted[0], True, "Skill disabled")))
    tui._before_render(tui.application)
    tui._emit("skills_inventory", ([
        {"name": "alpha", "identity": "a", "library": "alpha", "enabled": False},
        {"name": "beta", "identity": "b", "library": "beta", "enabled": True},
    ], ""))
    tui._before_render(tui.application)
    assert tui._panel.picker.selected_id == "enabled"
    assert next(row for row in tui._panel.page.rows if row.id == "enabled").checked is False
    home = tui._settings_home_page()
    assert next(row for row in home.rows if row.id == "category:skills").value == (
        "1/2 enabled"
    )
    ids = [row.id for row in home.rows]
    assert ids.index("category:skills") < ids.index("category:memory")
    tui._accept_choice()
    assert submitted[-1] == SkillAction("set-enabled", "alpha", "a", enabled=True)
    assert tui._panel.page.breadcrumb == ("Settings", "Skills", "Manage", "alpha")
    assert tui._panel.picker.selected_id == "enabled"
    assert not any(row.action and row.action.kind == "skill-delete"
                   for row in tui._panel.page.rows)


def test_tools_settings_persist_and_apply_individual_research_tool_toggles(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)

    tui._open_settings_category("tools")
    tui._choice_index = tui._choice_values.index("knowledge library: on (toggle)")
    tui._accept_choice()

    assert _tool_availability_preferences(path)["query_knowledge"] is False
    assert "query_knowledge" in tui.agent.disabled_tool_names
    assert "web_search" not in tui.agent.disabled_tool_names

    tui.agent.disabled_tool_names = set()
    _apply_tool_availability_preferences(tui.agent, path)
    assert tui.agent.disabled_tool_names == {"query_knowledge"}


def test_tools_settings_persist_and_apply_web_provider_toggles(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)

    tui._open_settings_category("tools")
    tui._choice_index = tui._choice_values.index("provider exa: on (toggle)")
    tui._accept_choice()

    assert _web_provider_preferences(path, tui.cfg)["exa"] is False
    assert tui.agent.tool_config.web_providers["exa"].enabled is False
    assert tui.agent.tool_config.web_providers["google"].enabled is True

    tui.agent.tool_config.web_providers["exa"].enabled = True
    _apply_web_provider_preferences(tui.agent, path)
    assert tui.agent.tool_config.web_providers["exa"].enabled is False


def test_settings_choice_sections_are_visible_and_not_selectable():
    tui = _fake_persistent_tui()

    tui._open_settings_category("tools")
    headings = [
        value.removeprefix("\0section:")
        for value in tui._choice_values
        if value.startswith("\0section:")
    ]
    assert headings == ["DISPLAY", "RESEARCH TOOLS", "WEB PROVIDERS", "RESULT VALIDATION"]
    assert not tui._choice_values[tui._choice_index].startswith("\0section:")

    tui._choice_index = tui._choice_values.index("\0section:WEB PROVIDERS")
    tui._accept_choice()
    assert not tui._choice_values[tui._choice_index].startswith("\0section:")


def test_first_picker_option_reveals_its_section_heading():
    tui = _fake_persistent_tui()
    tui._open_settings_category("tools")
    first = tui._choice_values.index("activity updates: on (toggle)")
    tui._choice_index = first
    assert tui._picker is not None
    tui._picker.scroll_top = first
    assert tui._choice_scroll(None) == 0
    assert tui._choice_values[0] == "\0section:DISPLAY"


def test_tools_settings_can_toggle_high_level_activity_updates(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)

    tui._open_settings_category("tools")
    tui._choice_index = tui._choice_values.index("activity updates: on (toggle)")
    tui._accept_choice()

    assert tui.show_activity_updates is False
    assert json.loads(path.read_text())["display"]["activity_updates"] is False
    assert tui._choice_values[tui._choice_index] == "activity updates: off (toggle)"


def test_activity_updates_default_on_and_migrate_reasoning_activity_preference(tmp_path):
    path = tmp_path / "chat-preferences.json"

    assert _activity_updates_enabled(path) is True
    path.write_text(json.dumps({"display": {"reasoning_activity": False}}))
    assert _activity_updates_enabled(path) is False
    path.write_text(json.dumps({"display": {"activity_updates": True}}))
    assert _activity_updates_enabled(path) is True


def test_restored_transcript_replays_persisted_activity_updates():
    transcript = _restored_transcript(
        "session-1",
        [
            {"role": "user", "content": "Inspect it", "ts": 1_700_000_000},
            {
                "role": "system",
                "content": {
                    "event": "activity_update",
                    "label": "explored",
                    "detail": "Read src/app.py",
                },
                "ts": 1_700_000_001,
            },
            {"role": "assistant", "content": "Done.", "ts": 1_700_000_002},
        ],
        80,
    )

    assert "[explored] Read src/app.py" in transcript
    assert (
        transcript.index("Inspect it") < transcript.index("[explored]") < transcript.index("Done.")
    )


def test_restored_transcript_replays_model_session_updates():
    transcript = _restored_transcript(
        "session-1",
        [
            {
                "role": "system",
                "content": {
                    "event": "session_update",
                    "detail": "model openai_codex/gpt-5 · thinking · conversation retained",
                },
                "ts": 1_700_000_000,
            }
        ],
        80,
    )

    assert (
        "[session] model openai_codex/gpt-5 · thinking · conversation retained"
        in transcript
    )


def test_restored_transcript_replays_completed_subagent_activity():
    transcript = _restored_transcript(
        "session-1",
        [
            {
                "role": "system",
                "content": {
                    "event": "subagent_activity",
                    "kind": "subagent_finished",
                    "task_id": "child-1",
                    "role": "read_research",
                    "status": "completed",
                    "model_steps": 2,
                    "tool_calls": 1,
                    "input_tokens": 120,
                    "output_tokens": 30,
                    "summary": "Found parser routing in src/parser.py.",
                },
                "ts": 1_700_000_000,
            }
        ],
        80,
    )

    assert (
        "[explored] read/research subagent completed "
        "(2 model steps · 1 tool call · 150 tokens)"
    ) in transcript
    assert "└ Found parser routing in src/parser.py." in transcript


@pytest.mark.parametrize(
    ("status", "label"),
    [("completed", "explored"), ("failed", "failed"), ("cancelled", "cancelled")],
)
def test_subagent_activity_uses_semantic_terminal_status(status, label):
    rendered = _subagent_activity_text(
        {
            "kind": "subagent_finished",
            "role": "test_diagnostic",
            "status": status,
        }
    )

    assert rendered == f"[{label}] test/diagnostic subagent {status}"


def test_subagent_activity_distinguishes_work_rejected_before_start():
    rendered = _subagent_activity_text(
        {
            "kind": "subagent_rejected",
            "role": "read_research",
            "status": "failed",
        }
    )

    assert rendered == "[failed] read/research subagent rejected"


@pytest.mark.parametrize(
    "tool,args,active,completed,detail",
    [
        (
            "read_file",
            {"path": "src/app.py"},
            "exploring src/app.py",
            "explored",
            "Read src/app.py",
        ),
        ("edit_file", {"path": "src/app.py"}, "editing src/app.py", "edited", "Edited src/app.py"),
        ("run_shell", {"command": "pytest -q"}, "running pytest -q", "ran", "pytest -q"),
        (
            "learn_source",
            {"url": "https://example.com/docs", "library": "example"},
            "learning https://example.com/docs into example",
            "learned",
            "https://example.com/docs into example",
        ),
    ],
)
def test_activity_updates_derive_from_real_tool_events(tool, args, active, completed, detail):
    assert _active_tool_status(tool, args) == active
    assert _completed_tool_activity(tool, args, "ok", {}) == (completed, detail)


def test_failed_activity_keeps_a_concise_failure_reason():
    assert _completed_tool_activity(
        "edit_file",
        {"path": "src/app.py"},
        "error: old_str not found in file",
        {},
    ) == ("failed", "Edited src/app.py — error: old_str not found in file")


def test_activity_updates_redact_secret_shaped_values():
    value = _activity_value(
        "curl -H 'Authorization: Bearer abc.123' --api-key topsecret "
        "https://user:password@example.com/?token=querysecret"
    )

    assert "abc.123" not in value
    assert "topsecret" not in value
    assert "password" not in value
    assert "querysecret" not in value
    assert value.count("[redacted]") >= 4


def test_settings_toggles_render_as_theme_colored_two_cell_switches(tmp_path):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")

    tui._open_settings_category("tools")
    tui._choice_index = tui._choice_values.index("activity updates: on (toggle)")
    fragments = tui._choice_fragments()

    assert ("class:toggle.on", "■") in fragments
    rendered = "".join(text for _style, text in fragments)
    activity_row = next(line for line in rendered.splitlines() if "activity updates" in line)
    assert activity_row.endswith("[  ■]")
    assert "activity updates: on (toggle)" not in rendered
    toggle_index = next(
        index for index, fragment in enumerate(fragments) if fragment == ("class:toggle.on", "■")
    )
    assert fragments[toggle_index - 1] == ("class:toggle.track", "[  ")
    assert fragments[toggle_index + 1] == ("class:toggle.track", "]")

    tui._accept_choice()
    fragments = tui._choice_fragments()

    assert ("class:toggle.off", "■") in fragments
    toggle_index = next(
        index for index, fragment in enumerate(fragments) if fragment == ("class:toggle.off", "■")
    )
    assert fragments[toggle_index - 1] == ("class:toggle.track", "[")
    assert fragments[toggle_index + 1] == ("class:toggle.track", "  ]")
    rendered = "".join(text for _style, text in fragments)
    activity_row = next(line for line in rendered.splitlines() if "activity updates" in line)
    assert activity_row.endswith("[■  ]")
    assert "activity updates: off (toggle)" not in rendered


def test_off_toggle_square_matches_brackets_and_on_square_uses_primary_color():
    style = _tui_style("autumn", "vscode-dark")

    track = style.get_attrs_for_style_str("class:toggle.track")
    off = style.get_attrs_for_style_str("class:toggle.off")
    on = style.get_attrs_for_style_str("class:toggle.on")

    assert off.color == track.color
    assert on.color != track.color


def test_settings_category_rows_render_as_aligned_columns(tmp_path):
    preferences = tmp_path / "chat-preferences.json"
    preferences.write_text(json.dumps({"runtime_device_mode": "gpu-preferred"}))
    tui = _fake_persistent_tui(chat_preferences_path=preferences)

    tui._open_settings_category("runtime")
    rendered = "".join(text for _style, text in tui._choice_fragments())
    rows = [
        line
        for line in rendered.splitlines()
        if any(name in line for name in ("device", "CPU threads", "context size"))
    ]

    value_columns = {
        next(line.index(value) for line in rows if value in line)
        for value in ("GPU preferred", "auto (Klaude decides)", "8,192")
    }
    assert len(value_columns) == 1
    assert all(": " not in line for line in rows)

    tui._open_settings_category("tools")
    rendered = "".join(text for _style, text in tui._choice_fragments())
    toggle_rows = [
        line
        for line in rendered.splitlines()
        if any(
            name in line
            for name in (
                "activity updates",
                "web search validation",
                "knowledge search validation",
            )
        )
    ]
    assert len(toggle_rows) == 3
    assert len({line.index("[") for line in toggle_rows}) == 1


def test_input_setting_toggle_keeps_its_selector_row(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")

    tui._open_settings_category("input field")
    tui._choice_index = tui._choice_values.index("border: on (toggle)")
    tui._accept_choice()

    assert tui._choice_values[tui._choice_index] == "border: off (toggle)"


def test_persistent_tui_keeps_input_live_and_queues_while_running():
    tui = _fake_persistent_tui()
    tui.running = True
    tui._set_input("explain the tests")

    tui._submit_buffer(steer=False)

    assert tui.input.text == ""
    assert list(tui.pending) == ["explain the tests"]
    assert "[queued 1] explain the tests" in tui.output.text
    assert not tui.input.window.dont_extend_width()


def test_chat_status_reports_session_runtime_permissions_and_agents_file(tmp_path):
    repo = tmp_path / "repo"
    workdir = repo / "src"
    workdir.mkdir(parents=True)
    root_instructions = repo / "AGENTS.md"
    nested_instructions = workdir / "AGENTS.md"
    root_instructions.write_text("root guidance")
    nested_instructions.write_text("nested guidance")
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    memory.rename_session("session-1", "Parser investigation")
    agent = SimpleNamespace(
        model="qwen3-coder:30b",
        reasoning_mode="thinking",
        ollama_think="high",
        ollama_code_think="high",
        ollama_options={"num_ctx": 16_384},
        messages=[{"role": "system", "content": "system prompt"}],
        plan_mode=False,
        max_steps=40,
        last_turn_budget={
            "model_steps_used": 3,
            "max_model_steps": 40,
            "tool_calls_used": 5,
            "max_tool_calls": 80,
            "elapsed_seconds": 7.25,
        },
        last_turn_capabilities={
            "scope": "review",
            "injected_instructions": [str(root_instructions), str(nested_instructions)],
            "instructions_truncated": False,
            "globally_enabled_tools": ["read_file", "run_shell", "write_file"],
            "callable_tools": ["read_file", "run_shell"],
            "budget": {
                "model_steps_used": 3,
                "max_model_steps": 40,
                "tool_calls_used": 5,
                "max_tool_calls": 80,
                "elapsed_seconds": 7.25,
            },
        },
        workdir=workdir,
        workspace=SimpleNamespace(repo_root=repo),
        ollama=SimpleNamespace(
            last_chat_metadata={
                "provider": "openai_api",
                "usage": {
                    "input_tokens": 1_000,
                    "output_tokens": 100,
                    "input_tokens_details": {
                        "cached_tokens": 768,
                        "cache_write_tokens": 232,
                    },
                },
            }
        ),
        gate=SimpleNamespace(
            policies={"read_file": "allow", "run_shell": "ask", "write_file": "deny"}
        ),
    )

    result = _chat_status(agent, memory, "session-1")

    assert "Session ID    session-1" in result
    assert "Session name  Parser investigation" in result
    assert "Mode          Thinking" in result
    assert "Effort        High" in result
    assert "Turn limit    40 steps + 1 finalization" in result
    assert "Subagents     Auto · 1 effective worker" in result
    assert "Turn scope    Review" in result
    assert "Callable now  2/3 enabled tools" in result
    assert "Turn budget   models 3/40 · tools 5/80 · 7.2s" in result
    assert "Context left  ~16,381 tokens" in result
    assert f"Workspace     {workdir}" in result
    assert "AGENTS.md     injected" in result
    assert f"              {root_instructions}" in result
    assert f"              {nested_instructions}" in result
    assert "Permissions   ALLOW 1 · ASK 1 · DENY 1" in result
    assert "Memory        On" in result
    assert "Tools         3 available" in result
    assert "Prompt cache  768/1,000 input tokens cached · 232 written" in result
    assert "Session name  Parser investigation\n\nModel" in result
    assert f"Workspace     {workdir}\nAGENTS.md" in result
    assert "Context       ~3 / 16,384 tokens · 0%" in result


def test_status_columns_align_values():
    rendered = _status_columns([("ID", "abc"), ("Session name", "Parser work"), ("", "/path")])
    lines = rendered.splitlines()

    assert {
        line.index(value)
        for line, value in zip(lines, ("abc", "Parser work", "/path"), strict=True)
    } == {len("Session name") + 2}


def test_status_permission_labels_are_colored_without_coloring_counts():
    line = "Permissions   ALLOW 55 · ASK 1 · DENY 0"
    fragments = TranscriptLexer().lex_document(Document("[status]\n" + line))(1)

    assert fragments == [
        ("", "Permissions   "),
        ("class:panel.value.success", "ALLOW"),
        ("", " 55 · "),
        ("class:panel.value.warning", "ASK"),
        ("", " 1 · "),
        ("class:panel.value.error", "DENY"),
        ("", " 0"),
    ]
    rich_status = _status_rich_text(line)
    assert rich_status.plain == "[STATUS]\n" + line
    assert [(rich_status.plain[span.start:span.end], span.style) for span in rich_status.spans] == [
        ("ALLOW", "green"), ("ASK", "yellow"), ("DENY", "red"),
    ]


@pytest.mark.parametrize(
    ("percent", "style", "rich_color"),
    [
        (69, None, None),
        (70, "class:panel.value.warning", "yellow"),
        (89, "class:panel.value.warning", "yellow"),
        (90, "class:panel.value.error", "red"),
    ],
)
def test_status_context_colors_only_value_at_warning_thresholds(percent, style, rich_color):
    value = f"~{percent * 100:,} / 10,000 tokens · {percent}%"
    line = f"Context       {value}"
    fragments = TranscriptLexer().lex_document(Document("[status]\n" + line))(1)
    if style is None:
        assert not any(
            fragment_style.startswith("class:panel.value") for fragment_style, _ in fragments
        )
    else:
        assert fragments == [("", "Context       "), (style, value)]

    rich_status = _status_rich_text(line)
    assert rich_status.plain == "[STATUS]\n" + line
    assert [(rich_status.plain[span.start:span.end], span.style) for span in rich_status.spans] == (
        [(value, rich_color)] if rich_color else []
    )


def test_codex_status_rows_show_five_hour_weekly_and_luna_reserve_limits():
    usage = SimpleNamespace(
        buckets=(
            SimpleNamespace(
                limit_id="codex",
                limit_name="Codex",
                model="",
                primary=SimpleNamespace(
                    used_percent=5,
                    window_duration_minutes=300,
                    resets_at=2_000_000_000,
                ),
                secondary=SimpleNamespace(
                    used_percent=31,
                    window_duration_minutes=10_080,
                    resets_at=2_000_100_000,
                ),
            ),
            SimpleNamespace(
                limit_id="base_model_inference",
                limit_name="Reserve",
                model="gpt-5.6-luna",
                primary=SimpleNamespace(
                    used_percent=0,
                    window_duration_minutes=10_080,
                    resets_at=2_000_200_000,
                ),
                secondary=None,
            ),
        )
    )
    agent = SimpleNamespace(
        model_info=SimpleNamespace(backend="openai_codex"),
        ollama=SimpleNamespace(auth=SimpleNamespace(rate_limits=lambda: usage)),
    )

    rows = _codex_usage_rows(agent)
    rendered = dict(rows)

    assert "95% left" in rendered["5h limit"]
    assert "69% left" in rendered["Weekly limit"]
    assert "100% left" in rendered["Luna Reserve Weekly limit"]
    assert rendered["Usage details"] == "https://chatgpt.com/codex/settings/usage"


def test_chat_status_uses_first_input_hint_before_worker_persists_turn(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._run_turn = lambda *_args, **_kwargs: None

    tui._enqueue("Investigate why the parser drops nested fields")

    assert tui.running
    assert tui.memory.session_title("session-1") == "Untitled session"
    tui._set_input("/status")
    tui._submit_buffer(steer=False)
    assert "Session name  Investigate why the parser drops nested fields" in tui.output.text


def test_status_runs_immediately_while_a_turn_is_running(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr("klaude_cli.main._chat_status", lambda *_args, **_kwargs: "ready")
    tui.running = True
    tui._set_input("/status")

    tui._submit_buffer(steer=False)

    assert tui.input.text == ""
    assert not tui.pending
    assert "[queued action" not in tui.output.text
    assert "[status]\nready" in tui.output.text
    assert tui.running


@pytest.mark.parametrize(
    "command",
    ["/recap", "/status", "/memory", "/skills", "/diff"],
)
def test_live_snapshot_commands_do_not_require_idle(command):
    assert not PersistentChatTUI._command_requires_idle(*command.partition(" ")[::2])


@pytest.mark.parametrize(
    "command,label",
    [
        ("/recap", "[recap]"),
        ("/status", "[status]"),
        ("/memory", "[memory]"),
        ("/skills", "[skills]"),
        ("/diff", "[diff]"),
    ],
)
def test_live_snapshot_commands_execute_during_work(monkeypatch, command, label):
    tui = _fake_persistent_tui()
    tui.running = True
    monkeypatch.setattr("klaude_cli.main._chat_status", lambda *_args, **_kwargs: "status snapshot")
    monkeypatch.setattr("klaude_cli.main._chat_memory", lambda *_args: "memory snapshot")
    monkeypatch.setattr("klaude_cli.main._chat_skills", lambda *_args: "skills snapshot")
    monkeypatch.setattr("klaude_cli.main._workspace_diff", lambda *_args: "diff snapshot")
    tui._set_input(command)

    tui._submit_buffer(steer=False)

    assert tui.input.text == ""
    assert not tui.pending
    assert "[queued action" not in tui.output.text
    assert label in tui.output.text
    assert tui.running


@pytest.mark.parametrize(
    "command",
    [
        "/compact",
        "/memory off",
        "/plan on",
        "/init",
        "/new",
        "/rename Parser work",
        "/fork",
        "/export",
        "/review",
    ],
)
def test_state_changing_commands_still_require_idle(command):
    assert PersistentChatTUI._command_requires_idle(*command.partition(" ")[::2])


def test_resume_does_not_require_idle():
    assert not PersistentChatTUI._command_requires_idle("/resume", "")


@pytest.mark.parametrize(
    "command",
    [
        "/compact",
        "/memory off",
        "/plan on",
        "/init",
        "/new",
        "/rename Parser work",
        "/fork",
        "/export",
        "/review",
    ],
)
def test_state_changing_commands_queue_during_work(command):
    tui = _fake_persistent_tui()
    tui.running = True
    tui._set_input(command)

    tui._submit_buffer(steer=False)

    assert tui.input.text == ""
    assert list(tui.pending) == [command]
    assert type(tui.pending[0]).__name__ == "PendingChatCommand"
    assert f"[queued action 1] {command}" in tui.output.text


def test_persistent_tui_input_has_empty_state_placeholder():
    tui = _fake_persistent_tui()

    placeholder = tui.input.control.input_processors[-1]

    assert tui.input.text == ""
    assert isinstance(placeholder.processor, InputPlaceholderProcessor)


def test_persistent_tui_permission_uses_a_contextual_composer_placeholder():
    tui = _fake_persistent_tui()

    tui._permission_request = {"tool": "run_shell"}

    assert (
        tui._composer_placeholder_text()
        == "Type y/yes, n/no, or a/always · Enter allows once."
    )


def test_persistent_tui_composer_uses_a_themed_side_rail_instead_of_a_frame():
    tui = _fake_persistent_tui()

    assert tui.input_panel is tui.composer_surface
    assert tui.composer_rail.content.width == 1
    assert tui.composer_rail.content.children[0].char == "┃"
    assert tui.composer_rail.content.children[1].char == "┃"
    assert tui._composer_rail_style() == "class:composer.rail"

    tui.running = True
    assert tui._composer_rail_style() == "class:composer.rail.busy"
    tui._permission_request = {"tool": "run_shell"}
    assert tui._composer_rail_style() == "class:composer.rail.warning"
    tui._permission_request = None
    tui.status_error = "connection failed"
    assert tui._composer_rail_style() == "class:composer.rail.error"


def test_composer_rail_uses_output_background_on_input_surface():
    attrs = _tui_style("autumn", "vscode-dark").get_attrs_for_style_str("class:composer.rail")

    assert attrs.color == "211820"
    assert attrs.bgcolor == "35222a"


def test_crimson_red_uses_autumn_neutral_output_background():
    autumn = _tui_style("autumn", "vscode-dark").get_attrs_for_style_str("class:output-field")
    crimson = _tui_style("crimson-red", "vscode-dark").get_attrs_for_style_str("class:output-field")

    assert crimson.bgcolor == autumn.bgcolor == "211820"


def test_crimson_red_uses_autumn_input_surface_and_lighter_runtime_text():
    autumn = _tui_style("autumn", "vscode-dark")
    crimson = _tui_style("crimson-red", "vscode-dark")

    assert crimson.get_attrs_for_style_str("class:input-field").bgcolor == (
        autumn.get_attrs_for_style_str("class:input-field").bgcolor
    )
    assert crimson.get_attrs_for_style_str("class:runtime_text").color == "ae999c"
    assert crimson.get_attrs_for_style_str("class:footer.keybinds").color == "ae999c"


def test_persistent_tui_composer_keeps_vertical_padding_inside_configured_height():
    tui = _fake_persistent_tui()

    assert tui._composer_vertical_padding_visible()
    assert tui.input.window.height().min == tui.appearance.input_height - 2
    assert tui.input.window.height().max == tui.appearance.input_max_height - 2

    tui._begin_choice("model", ["model-a", "model-b"], "model-a")
    assert tui._composer_vertical_padding_visible()
    assert tui._choice_height() == tui.appearance.input_height - 2

    tui.appearance.input_height = tui.appearance.input_max_height = 1
    assert not tui._composer_vertical_padding_visible()
    assert tui.input.window.height().min == 1
    assert tui.input.window.height().max == 1


def test_persistent_tui_marks_active_settings_options():
    tui = _fake_persistent_tui()
    tui.appearance.input_height = tui.appearance.input_max_height = 8
    tui._begin_choice("input height", ["8 lines", "10 lines"], "10 lines")
    rendered = "".join(text for _style, text in tui._choice_fragments())

    assert "8 lines *" in rendered
    assert "10 lines *" not in rendered


def test_persistent_tui_uses_short_escape_sequence_timeout():
    tui = _fake_persistent_tui()

    assert tui.application.full_screen is False
    assert tui.application.ttimeoutlen == ESCAPE_SEQUENCE_TIMEOUT
    assert tui.application.timeoutlen == ESCAPE_SEQUENCE_TIMEOUT


def test_persistent_tui_shows_compact_queued_inputs_above_composer():
    tui = _fake_persistent_tui()
    tui.pending.extend(["like this", "and\nthis"])

    rendered = "".join(text for _style, text in tui._queue_fragments())

    assert rendered == (
        "⏳ Queued follow-up inputs\n"
        "  ↳ like this\n"
        "  ↳ and ↵ this\n"
        "    alt + ↑ edit last queued message"
    )
    root = tui.application.layout.container
    assert root.content.children[0] is tui.text_theme_preview_panel
    assert root.content.children[2] is tui.output_spacer
    assert root.content.children[3] is tui.queue_panel
    assert root.content.children[4] is tui.input_spacer
    assert root.content.children[5] is tui.input_panel


def test_repeated_alt_up_edits_queued_inputs_from_newest_to_oldest():
    tui = _fake_persistent_tui()
    tui.running = True
    tui.pending.extend(["first", "middle", "last"])
    edit_last = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.Escape, Keys.Up)
    )

    edit_last(None)
    assert list(tui.pending) == ["first", "middle", "last"]
    assert tui.input.text == "last"
    assert tui._queue_edit_index == 2

    tui._set_input("last edited")
    edit_last(None)
    assert list(tui.pending) == ["first", "middle", "last edited"]
    assert tui.input.text == "middle"
    assert tui._queue_edit_index == 1

    tui._set_input("middle edited")
    edit_last(None)
    assert tui.input.text == "first"
    assert tui._queue_edit_index == 0
    assert "  › first" in "".join(text for _style, text in tui._queue_fragments())

    tui._set_input("first edited")
    tui._submit_buffer(steer=False)

    assert list(tui.pending) == ["first edited", "middle edited", "last edited"]
    assert tui._queue_edit_index is None
    assert tui.input.text == ""


def test_empty_queue_edit_and_enter_deletes_that_follow_up():
    tui = _fake_persistent_tui()
    tui.running = True
    tui.pending.extend(["keep", "delete me"])
    tui._edit_previous_queued()
    tui._set_input("")

    tui._submit_buffer(steer=False)

    assert list(tui.pending) == ["keep"]
    assert tui._queue_edit_index is None
    assert tui.activity == "queued follow-up deleted"


def test_alt_backslash_promotes_the_selected_queue_edit_to_steering():
    tui = _fake_persistent_tui()
    tui.running = True
    attachment = Path("brief.md")
    tui.pending.extend(
        [
            PendingChatTurn("earlier"),
            PendingChatTurn("steer this", (attachment,)),
        ]
    )
    alt_up = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.Escape, Keys.Up)
    )
    alt_steer = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.Escape, "\\")
    )

    alt_up(None)
    assert "alt + \\ steer selected" in "".join(
        text for _style, text in tui._queue_fragments()
    )
    tui._set_input("steer this edited")
    alt_steer(None)

    assert [str(turn) for turn in tui.pending] == ["steer this edited", "earlier"]
    assert tui.pending[0].attachments == (attachment,)
    assert tui._queue_edit_index is None
    assert tui.input.text == ""
    assert tui.cancel_requested.is_set()
    assert tui.activity == "steering at safe boundary"
    assert tui.output.text.count("[steer queued] steer this edited") == 1


def test_alt_backslash_does_not_turn_a_queued_session_action_into_model_input():
    tui = _fake_persistent_tui()
    tui.running = True
    tui.pending.append(PendingChatCommand("/resume saved"))
    tui._edit_previous_queued()
    tui._set_input("/resume other")

    tui._submit_buffer(steer=True)

    assert isinstance(tui.pending[0], PendingChatCommand)
    assert str(tui.pending[0]) == "/resume saved"
    assert tui._queue_edit_index == 0
    assert not tui.cancel_requested.is_set()
    assert "cannot be used as steering messages" in tui.status_error


def test_persistent_tui_steer_prioritizes_and_interrupts_active_turn():
    tui = _fake_persistent_tui()
    tui.running = True
    tui.pending.append("later")
    tui._set_input("focus on the parser")

    tui._submit_buffer(steer=True)

    assert list(tui.pending) == ["focus on the parser", "later"]
    assert tui.cancel_requested.is_set()
    assert "steering at safe boundary" in tui.activity


def test_persistent_tui_inline_model_picker_leads_to_effort_picker(tmp_path):
    preferences = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=preferences)

    tui._begin_choice("model", ["qwen3.5:4b", "gpt-oss:20b"], tui.agent.model)
    tui._move_choice(1)
    tui._accept_choice()

    assert tui.agent.model == "gpt-oss:20b"
    assert tui._choice_kind == "mode"
    assert tui.input.text == ""
    tui._choice_index = tui._choice_values.index("thinking")
    tui._accept_choice()
    assert tui._choice_kind == "effort"
    effort_options = "".join(text for _style, text in tui._choice_fragments())
    assert all(choice in effort_options for choice in ("low", "medium", "high"))
    assert "off" not in effort_options and "auto" not in effort_options

    tui._accept_choice()

    assert _load_last_chat_model(preferences) == "ollama/gpt-oss:20b"


@pytest.mark.parametrize("key,expected", [(Keys.Down, 0), (Keys.Up, 1)])
def test_arrow_keys_prioritize_completion_over_history(key, expected):
    tui = _fake_persistent_tui()
    tui._history = ["previous input"]
    tui._set_input("/")
    buffer = tui.input.buffer
    buffer.complete_state = CompletionState(
        buffer.document,
        [Completion("/help", start_position=-1), Completion("/model", start_position=-1)],
        complete_index=None,
    )
    handler = next(
        binding.handler for binding in tui.key_bindings.bindings if tuple(binding.keys) == (key,)
    )

    handler(None)

    assert buffer.complete_state is not None
    assert buffer.complete_state.complete_index == expected
    assert buffer.text == ("/help", "/model")[expected]
    assert tui._history == ["previous input"]


@pytest.mark.parametrize(
    "key,start,expected",
    [
        (Keys.Left, len("first\n"), len("first")),
        (Keys.Right, len("first"), len("first\n")),
    ],
)
def test_horizontal_arrow_keys_cross_logical_line_boundaries(key, start, expected):
    tui = _fake_persistent_tui()
    tui.input.buffer.set_document(Document("first\nsecond", start), bypass_readonly=True)
    handler = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (key,)
    )

    handler(SimpleNamespace(arg=1))

    assert tui.input.buffer.cursor_position == expected


@pytest.mark.parametrize("key,start", [(Keys.Left, 0), (Keys.Right, len("first\nsecond"))])
def test_horizontal_arrow_keys_stop_at_composer_boundaries(key, start):
    tui = _fake_persistent_tui()
    tui.input.buffer.set_document(Document("first\nsecond", start), bypass_readonly=True)
    handler = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (key,)
    )

    handler(SimpleNamespace(arg=1))

    assert tui.input.buffer.cursor_position == start


def test_escape_closes_completion_without_clearing_input():
    tui = _fake_persistent_tui()
    tui._set_input("/")
    buffer = tui.input.buffer
    buffer.complete_state = CompletionState(
        buffer.document,
        [Completion("/help", start_position=-1)],
        complete_index=0,
    )
    dismiss = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if binding.handler.__name__ == "dismiss_completion"
    )

    dismiss(None)

    assert buffer.complete_state is None
    assert buffer.text == "/"


@pytest.mark.parametrize("key", [(Keys.Backspace,), (Keys.ControlH,)])
def test_backspace_refreshes_slash_command_completion(monkeypatch, key):
    tui = _fake_persistent_tui()
    tui._set_input("/model")
    starts = []
    monkeypatch.setattr(
        tui.input.buffer,
        "start_completion",
        lambda **kwargs: starts.append(kwargs),
    )
    delete = next(
        binding.handler for binding in tui.key_bindings.bindings if tuple(binding.keys) == key
    )

    delete(None)

    assert tui.input.text == "/mode"
    assert starts == [{"select_first": False}]


@pytest.mark.parametrize("command,kind", [("/settings", "settings"), ("/model", "model source")])
def test_enter_accepts_and_executes_highlighted_command(command, kind):
    tui = _fake_persistent_tui()
    tui._set_input("/")
    buffer = tui.input.buffer
    buffer.complete_state = CompletionState(
        buffer.document,
        [Completion(command, start_position=-1)],
        complete_index=None,
    )
    buffer.complete_next()
    enter = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.ControlM,)
    )

    async def accept():
        enter(None)

    asyncio.run(accept())

    assert tui._choice_kind == kind
    assert buffer.text == ""


def test_enter_submits_model_command_when_completion_menu_has_no_selection():
    tui = _fake_persistent_tui()
    tui._set_input("/model")
    tui.input.buffer.complete_state = CompletionState(
        tui.input.buffer.document,
        [Completion("/model", start_position=-len("/model"))],
        complete_index=None,
    )
    assert tui.input.buffer.complete_state is not None
    assert tui.input.buffer.complete_state.current_completion is None
    enter = next(
        binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) == (Keys.ControlM,)
    )

    enter(None)

    assert tui._choice_kind == "model source"
    assert tui._choice_values == ["Local", "Cloud", "cancel"]
    rendered = "".join(text for _style, text in tui._choice_fragments())
    assert "Cloud" in rendered and "Local" in rendered
    assert "gpt-oss:20b" not in rendered and "qwen3.5:4b" not in rendered


@pytest.mark.parametrize("category", ["theme", "input field"])
def test_settings_submenus_end_with_back_instead_of_cancel(category):
    tui = _fake_persistent_tui()
    tui._open_settings_category(category)

    assert tui._choice_values[-2:] == ["reset to default", "back"]
    assert "cancel" not in tui._choice_values
    assert tui._choice_values.count("back") == 1
    tui._choice_index = len(tui._choice_values) - 1
    tui._accept_choice()
    assert tui._choice_kind == "settings"


def test_models_settings_uses_model_picker_flow_and_returns_to_settings():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "models")

    tui._accept_choice()

    assert tui._choice_kind == "model source"
    assert tui._choice_values == ["Local", "Cloud", "back"]
    tui._choice_index = tui._choice_values.index("Local")
    tui._accept_choice()
    assert tui._choice_kind == "model"

    tui._choice_index = tui._choice_values.index("back")
    tui._accept_choice()
    assert tui._choice_kind == "model source"
    assert tui._choice_values[-1] == "back"

    tui._choice_index = tui._choice_values.index("back")
    tui._accept_choice()
    assert tui._choice_kind == "settings"
    assert tui._choice_values[tui._choice_index].startswith("Models:")


def test_settings_models_command_opens_same_source_picker():
    tui = _fake_persistent_tui()
    tui._set_input("/settings models")

    tui._submit_buffer(steer=False)

    assert tui._choice_kind == "model source"
    assert tui._choice_values == ["Local", "Cloud", "back"]


def test_bottom_status_omits_obsolete_scroll_hint():
    tui = _fake_persistent_tui()
    text = "".join(fragment[1] for fragment in tui._keybind_fragments())
    assert "Scroll" not in text
    assert "/ commands" not in text


def test_footer_omits_standard_composer_but_keeps_vim_indicator():
    tui = _fake_persistent_tui()

    standard = "".join(fragment[1] for fragment in tui._keybind_fragments())
    tui.composer_mode = "vim"
    vim = "".join(fragment[1] for fragment in tui._keybind_fragments())

    assert "Standard" not in standard
    assert "composer" not in standard
    assert "Vim composer" in vim


def test_vim_command_toggles_and_persists_composer_mode(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)

    tui._set_input("/vim")
    tui._submit_buffer(steer=False)

    assert tui.composer_mode == "vim"
    assert tui.application.editing_mode == EditingMode.VI
    assert json.loads(path.read_text())["composer_mode"] == "vim"

    tui._set_input("/vim")
    tui._submit_buffer(steer=False)

    assert tui.composer_mode == "standard"
    assert tui.application.editing_mode == EditingMode.EMACS


def test_vim_composer_applies_modal_editing_keybindings(tmp_path):
    async def exercise():
        tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "chat-preferences.json")
        tui._set_composer_mode("vim")
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.1)
                pipe.send_text("abc\x1b0x")
                await asyncio.sleep(0.1)
                assert tui.input.buffer.text == "bc"
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_modified_enter_sequences_override_plain_enter_mappings():
    for sequence in CTRL_ENTER_SEQUENCES:
        assert ANSI_SEQUENCES[sequence] == (Keys.Escape, Keys.ControlJ)
    for sequence in SHIFT_ENTER_SEQUENCES:
        assert ANSI_SEQUENCES[sequence] == (Keys.Escape, Keys.ControlM)


def test_footer_separates_runtime_model_spacer_and_keybind_rows():
    tui = _fake_persistent_tui()

    assert tui.status_row.children == [tui.status_window, tui.status_model_window]
    assert tui.status_spacer.height == 1
    assert tui.footer_row.children == [
        tui.footer_brand_window,
        tui.footer_path_window,
        tui.keybind_window,
    ]
    status_model = "".join(text for _style, text in tui._status_model_fragments())
    assert "qwen3.5:4b" in status_model
    assert tui.ui_state.effort in status_model
    assert "klaude v" in "".join(text for _style, text in tui._footer_brand_fragments())
    workdir = Path(getattr(tui.agent, "workdir", Path.cwd())).resolve()
    try:
        relative = workdir.relative_to(Path.home())
    except ValueError:
        expected_path = str(workdir)
    else:
        expected_path = "~" if not relative.parts else f"~/{relative}"
    footer_path = "".join(text for _style, text in tui._footer_path_fragments())
    assert footer_path.endswith(" ┃")
    assert expected_path.endswith(footer_path[1:-2].removeprefix("…"))
    assert sum(len(text) for fragments in (
        tui._footer_brand_fragments(), tui._footer_path_fragments(),
        tui._keybind_fragments()
    ) for _style, text in fragments) <= tui.application.output.get_size().columns
    assert "ENTER send/queue · ALT+\\ steer · ALT+ENTER newline" in "".join(
        text for _style, text in tui._keybind_fragments()
    )


def test_runtime_calibration_submits_without_collecting_runtime_context(tmp_path, monkeypatch):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
    monkeypatch.setattr(
        "klaude_cli.main.collect_runtime_context", lambda *args: pytest.fail("UI probe")
    )
    tui._open_settings_category("runtime", "auto calibrate")
    previous = dict(tui.agent.ollama_options)
    tui._apply_settings_action("runtime settings", "auto calibrate")
    assert tui.agent.ollama_options == previous
    assert tui._background_jobs.requests["runtime-calibration"] == {"kind": "runtime_calibration"}
    assert tui._choice_values[tui._choice_index] == "cancel calibration"
    tui._apply_background_result((
        "runtime-calibration", tui._background_jobs.latest["runtime-calibration"],
        {"num_thread": 4, "num_ctx": 16384, "num_gpu": "untrusted"}, ""
    ))
    assert tui.agent.ollama_options["num_ctx"] == 16384
    assert "num_gpu" not in tui.agent.ollama_options
    saved = json.loads((tmp_path / "preferences.json").read_text())
    assert saved["runtime_options"]["num_thread"] == 4
    assert tui._choice_values[tui._choice_index] == "auto calibrate"


@pytest.mark.parametrize(
    "action", ["cancel", "back", "settings", "runtime change", "session change"]
)
def test_runtime_calibration_late_results_do_not_overwrite_new_choices(tmp_path, action):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
    tui._open_settings_category("runtime")
    tui._apply_settings_action("runtime settings", "auto calibrate")
    identity = tui._background_jobs.latest["runtime-calibration"]
    if action == "cancel":
        tui._apply_settings_action("runtime settings", "cancel calibration")
    elif action == "back":
        tui._cancel_choice()
    elif action == "settings":
        tui._open_settings_category("theme")
    elif action == "runtime change":
        tui.agent.ollama_options["num_ctx"] = 4096
        tui._persist_runtime_preferences("num_ctx")
    else:
        tui.session_id = "different"
    before = dict(tui.agent.ollama_options)
    tui._apply_background_result((
        "runtime-calibration", identity, {"num_thread": 16, "num_ctx": 65536}, ""
    ))
    assert tui.agent.ollama_options == before
    assert not tui._calibration_request


@pytest.mark.parametrize(
    "result,error", [(None, "timed out"), ({"num_thread": 0, "num_ctx": 42}, "")]
)
def test_runtime_calibration_failure_preserves_options_and_selection(result, error):
    tui = _fake_persistent_tui()
    tui._open_settings_category("runtime")
    tui._apply_settings_action("runtime settings", "auto calibrate")
    selected = next(row for row in tui._choice_values if row.startswith("context size:"))
    tui._choice_index = tui._choice_values.index(selected)
    before = dict(tui.agent.ollama_options)
    tui._apply_background_result((
        "runtime-calibration", tui._background_jobs.latest["runtime-calibration"], result, error
    ))
    assert tui.agent.ollama_options == before
    assert "unchanged" in tui.status_error
    assert tui._choice_values[tui._choice_index] == selected


def test_runtime_calibration_does_not_start_during_active_work():
    tui = _fake_persistent_tui()
    tui.running = True
    tui._calibrate_runtime()
    assert not tui._calibration_request
    assert "runtime-calibration" not in tui._background_jobs.latest


def test_live_calibration_picker_remains_filterable_and_preserves_query(tmp_path):
    async def exercise():
        tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
        tui._open_settings_category("runtime", "auto calibrate")
        tui._accept_choice()
        identity = tui._background_jobs.latest["runtime-calibration"]
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                pipe.send_text("cal")
                await asyncio.sleep(0.15)
                assert tui._choice_filter_query == "cal"
                assert tui._choice_values[tui._choice_index] == "cancel calibration"
                assert tui._calibration_request
                tui._emit("background_result", (
                    "runtime-calibration", identity, {"num_thread": 4, "num_ctx": 8192}, ""
                ))
                await asyncio.sleep(0.15)
                assert tui._choice_filter_query == "cal"
                assert tui._choice_values[tui._choice_index] == "auto calibrate"
                assert not tui._calibration_request
                assert tui.panel_body_window.render_info is not None
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_appearance_save_never_writes_on_ui_and_ignores_stale_acknowledgements(monkeypatch):
    tui = _fake_persistent_tui()
    requests = []

    class PendingWriter:
        def submit(self, changes):
            requests.append(dict(changes))
            return len(requests)

    tui._appearance_writer = PendingWriter()
    monkeypatch.setattr(
        "klaude_cli.main.update_settings", lambda *args, **kwargs: pytest.fail("UI write")
    )
    tui.appearance.theme = "crimson-red"
    tui._commit_appearance("theme", fields=("theme",))
    tui.appearance.input_border = False
    tui._commit_appearance("border", fields=("input_border",))
    assert requests == [
        {("theme", "interface"): "crimson-red"}, {("input_field", "border"): False},
    ]
    tui._emit("appearance_saved", (1, False))
    tui._before_render(None)
    assert tui._appearance_save_state == "saving"
    tui._emit("appearance_saved", (2, False))
    tui._before_render(None)
    assert tui._appearance_save_state == "failed"
    assert tui.appearance.theme == "crimson-red" and not tui.appearance.input_border
    assert "Appearance save unconfirmed" in tui.output.text
    tui._commit_appearance("theme", fields=("theme",))
    assert tui.status_error == ""
    tui._emit("appearance_saved", (3, True))
    tui._before_render(None)
    assert tui._appearance_save_state == "saved"
    assert tui._runtime_save_state == ""


def test_runtime_save_submits_without_ui_filesystem_access_and_scopes_acknowledgement(monkeypatch):
    tui = _fake_persistent_tui()
    requests = []
    class PendingWriter:
        def submit(self, changes):
            requests.append(dict(changes))
            return len(requests)
    tui._settings_writer = PendingWriter()
    monkeypatch.setattr("klaude_cli.main.update_settings", lambda *args: pytest.fail("UI write"))
    tui.agent.max_steps = 40
    tui._persist_runtime_preferences("max_steps")
    tui._persist_runtime_preferences("num_ctx")
    assert requests[0] == {("runtime_options", "max_steps"): 40}
    assert tui.agent.max_steps == 40 and tui._runtime_save_state == "saving"
    tui._emit("settings_saved", (1, False))
    tui._before_render(None)
    assert tui._runtime_save_state == "saving"
    tui._emit("settings_saved", (2, False))
    tui._before_render(None)
    assert tui._runtime_save_state == "failed"
    assert "could not be confirmed" in tui.output.text
    assert tui.agent.max_steps == 40
    tui._persist_runtime_preferences("max_steps")
    assert tui.status_error == ""
    tui._emit("settings_saved", (3, True))
    tui._before_render(None)
    assert tui._runtime_save_state == "saved"


def test_runtime_preferences_editor_waits_for_pending_save():
    tui = _fake_persistent_tui()
    tui._runtime_save_state = "saving"
    tui._open_runtime_config_editor("preferences")
    assert "finish saving" in tui.status_error


def test_pending_permission_toggles_use_live_gate_not_stale_disk(monkeypatch):
    tui = _fake_persistent_tui()
    requests = []
    class PendingWriter:
        def submit(self, changes):
            requests.append(dict(changes))
            return len(requests)
    tui._settings_writer = PendingWriter()
    monkeypatch.setattr("klaude_cli.main.update_settings", lambda *args: pytest.fail("UI write"))
    tui._open_settings_category("permissions", "Write file:")
    for policy in ("allow", "deny", "ask"):
        tui._panel.picker.focus("tool:write_file")
        tui._apply_panel_action(tui._panel.row().action)
        assert tui.agent.gate.policies["write_file"] == policy
        assert tui._choice_values[tui._choice_index] == f"Write file: {policy.upper()}"
    assert requests == [
        {("permissions", "write_file"): policy} for policy in ("allow", "deny", "ask")
    ]
    tui._panel.search_active = True
    tui._set_input("write file")
    tui._refresh_choice_filter()
    focused = tui._panel.picker.selected_id
    tui._emit("settings_saved", (3, False))
    tui._before_render(None)
    assert tui.agent.gate.policies["write_file"] == "ask"
    assert tui._panel.picker.selected_id == focused
    assert tui._panel.picker.query == "write file"
    assert tui._choice_values[tui._choice_index] == "Write file: ASK"
    assert "Save unconfirmed" in str(tui._panel_footer_fragments())
    assert "could not be confirmed" in tui.output.text


def test_permission_reset_and_composer_take_effect_before_save_finishes():
    tui = _fake_persistent_tui()
    requests = []
    class PendingWriter:
        def submit(self, changes):
            requests.append(dict(changes))
            return len(requests)
    tui._settings_writer = PendingWriter()
    tui._save_permission_settings({"write_file": "allow"}, tool="write_file")
    tui._reset_permission_settings()
    assert tui.agent.gate.policies["write_file"] == tui.cfg.permissions.get("write_file", "ask")
    tui._set_composer_mode("vim")
    assert tui.composer_mode == "vim"
    assert tui.application.editing_mode == EditingMode.VI
    assert tui._runtime_save_state == "saving"
    tui._emit("settings_saved", (1, False))
    tui._before_render(None)
    assert tui._runtime_save_state == "saving"
    tui._emit("settings_saved", (3, True))
    tui._before_render(None)
    assert tui._runtime_save_state == "saved"


def test_permission_ack_ignores_old_revisions_and_preserves_process_grants():
    tui = _fake_persistent_tui()
    tui.agent.gate.policies = {"write_file": "ask"}
    tui.agent.gate.process_grants = {"read_file"}
    tui._runtime_save_revision = 3
    tui._emit("settings_permissions", (2, {"write_file": "allow"}))
    tui._before_render(None)
    assert tui.agent.gate.policies["write_file"] == "ask"
    tui._emit("settings_permissions", (3, {"write_file": "deny", "unknown": "allow"}))
    tui._before_render(None)
    assert tui.agent.gate.policies["write_file"] == "deny"
    assert "unknown" not in tui.agent.gate.policies
    assert tui.agent.gate.process_grants == {"read_file"}


@pytest.mark.parametrize("category", ["runtime", "appearance", "tools", "model"])
def test_live_picker_is_responsive_while_settings_writer_is_blocked(
    tmp_path, monkeypatch, category
):
    import threading

    import klaude_cli.settings_writer as module

    async def exercise():
        tui = _fake_persistent_tui(
            chat_preferences_path=tmp_path / "preferences.json",
            appearance_path=tmp_path / "appearance.json",
        )
        entered, release = threading.Event(), threading.Event()
        original = module.update_settings
        def slow(path, changes, **kwargs):
            entered.set()
            assert release.wait(3)
            return original(path, changes, **kwargs)
        monkeypatch.setattr(module, "update_settings", slow)
        if category in {"runtime", "tools", "model"}:
            writer = module.SettingsWriter(
                tui.chat_preferences_path, tui._emit, publish_tools=True
            )
            tui._settings_writer = writer
            if category == "runtime":
                tui._persist_runtime_preferences("num_ctx")
                tui._open_settings_category("runtime", "context size:")
                query, prefix = "context", "context size:"
            elif category == "tools":
                tui._open_settings_category("tools", "web search validation:")
                tui._apply_settings_action("tools settings", "web search validation: on (toggle)")
                query, prefix = "validation", "web search validation:"
            else:
                tui._model_flow_parent = "settings"
                tui._activate_selected_model(ModelInfo("ollama", "gpt-oss:20b", "gpt-oss:20b"))
                tui._choice_index = tui._choice_values.index("standard")
                tui._accept_choice()
                query, prefix = "models", "Models:"
            state = "_runtime_save_state"
        else:
            from klaude_cli.main import _migrate_appearance

            writer = module.SettingsWriter(
                tui.appearance_path,
                lambda _kind, payload: tui._emit("appearance_saved", payload),
                prepare=_migrate_appearance, publish_permissions=False,
            )
            tui._appearance_writer = writer
            tui.appearance.input_border = False
            tui._commit_appearance("border", fields=("input_border",))
            tui._open_settings_category("input field", "border:")
            query, prefix, state = "border", "border:", "_appearance_save_state"
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                assert entered.is_set()
                pipe.send_text("/" + query if category == "model" else query)
                for _ in range(40):
                    if tui._choice_filter_query == query:
                        break
                    await asyncio.sleep(0.025)
                assert tui._choice_filter_query == query
                assert getattr(tui, state) == "saving"
                assert (tui.panel_body_window if tui._panel else tui.choice_window
                        ).render_info is not None
                release.set()
                for _ in range(40):
                    if getattr(tui, state) == "saved":
                        break
                    await asyncio.sleep(0.025)
                assert getattr(tui, state) == "saved"
                assert tui._choice_filter_query == query
                assert tui._choice_values[tui._choice_index].startswith(prefix)
            finally:
                release.set()
                tui.application.exit()
                await task
                writer.close(wait=True)

    asyncio.run(exercise())


def test_runtime_settings_control_device_threads_and_context_persist(tmp_path):
    preferences_path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=preferences_path)

    tui._open_settings_category("runtime")
    assert tui._choice_kind == "runtime settings"
    assert any(value.startswith("device: auto") for value in tui._choice_values)

    device_row = next(value for value in tui._choice_values if value.startswith("device:"))
    tui._choice_index = tui._choice_values.index(device_row)
    tui._accept_choice()
    assert tui._choice_kind == "runtime device"

    tui._begin_choice("runtime device", ["auto (Klaude decides)", "CPU only", "back"], "CPU only")
    tui._accept_choice()
    assert tui.agent.ollama_options["num_gpu"] == 0

    tui._begin_choice("CPU threads", ["auto (Klaude decides)", "4", "back"], "4")
    tui._accept_choice()
    assert tui.agent.ollama_options["num_thread"] == 4

    tui._begin_choice("context size", ["8,192", "16,384", "back"], "16,384")
    tui._accept_choice()
    assert tui.agent.ollama_options["num_ctx"] == 16_384
    assert tui.ui_state.context_window == 16_384
    assert _load_runtime_preferences(preferences_path) == {
        "num_gpu": 0,
        "num_thread": 4,
        "num_ctx": 16_384,
    }


def test_runtime_turn_limit_presets_custom_value_and_reset_persist(tmp_path):
    preferences_path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=preferences_path)

    tui._open_settings_category("runtime")
    turn_row = next(value for value in tui._choice_values if value.startswith("turn limit:"))
    tui._choice_index = tui._choice_values.index(turn_row)
    tui._accept_choice()

    assert tui._choice_kind == "turn limit"
    tui._choice_index = tui._choice_values.index("Extended · 40 steps")
    tui._accept_choice()
    assert tui.agent.max_steps == 40
    assert _load_runtime_preferences(preferences_path)["max_steps"] == 40

    tui._choice_index = tui._choice_values.index("turn limit: 40 steps")
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("custom input")
    tui._accept_choice()
    tui._set_input("31")
    tui._submit_buffer(steer=False)
    assert tui.agent.max_steps == 31
    assert _load_runtime_preferences(preferences_path)["max_steps"] == 31

    tui._choice_index = tui._choice_values.index("turn limit: 31 steps")
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("reset to default")
    tui._accept_choice()
    assert tui.agent.max_steps == tui.cfg.max_agent_steps
    assert "max_steps" not in _load_runtime_preferences(preferences_path)


def test_runtime_turn_limit_preference_applies_to_agent(tmp_path):
    path = tmp_path / "chat-preferences.json"
    _save_runtime_preferences(path, {"max_steps": 40})
    agent = _fake_persistent_tui().agent

    _apply_runtime_preferences(agent, _load_runtime_preferences(path))

    assert agent.max_steps == 40


def test_runtime_subagent_workers_persist_and_reset(tmp_path):
    preferences_path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=preferences_path)
    tui.agent.max_subagent_concurrency = 0

    tui._open_settings_category("runtime")
    workers_row = next(
        value for value in tui._choice_values if value.startswith("subagent workers:")
    )
    tui._choice_index = tui._choice_values.index(workers_row)
    tui._accept_choice()
    assert tui._choice_kind == "subagent workers"

    tui._choice_index = tui._choice_values.index("3")
    tui._accept_choice()
    assert tui.agent.max_subagent_concurrency == 3
    assert _load_runtime_preferences(preferences_path)["max_subagent_concurrency"] == 3

    workers_row = next(
        value for value in tui._choice_values if value.startswith("subagent workers:")
    )
    tui._choice_index = tui._choice_values.index(workers_row)
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("reset to default")
    tui._accept_choice()
    assert tui.agent.max_subagent_concurrency == getattr(
        tui.cfg, "max_subagent_concurrency", 0
    )
    assert "max_subagent_concurrency" not in _load_runtime_preferences(preferences_path)


def test_runtime_turn_limit_rejects_out_of_range_custom_value():
    tui = _fake_persistent_tui()
    tui._runtime_edit = "max_steps"
    tui._set_input("65")

    tui._submit_buffer(steer=False)

    assert tui.agent.max_steps != 65
    assert "1 to 64" in tui.status_error


def test_runtime_settings_offer_scoped_nano_editors(monkeypatch):
    tui = _fake_persistent_tui()
    opened: list[str] = []
    monkeypatch.setattr("klaude_cli.main.shutil.which", lambda _name: "/usr/bin/nano")
    monkeypatch.setattr(
        tui,
        "_open_runtime_config_editor",
        lambda target: opened.append(target),
    )

    tui._open_settings_category("runtime")
    assert "edit config.toml (nano)" in tui._choice_values
    assert "edit runtime preferences (nano)" in tui._choice_values

    tui._apply_settings_action("runtime settings", "edit config.toml (nano)")
    tui._apply_settings_action("runtime settings", "edit runtime preferences (nano)")

    assert opened == ["config", "preferences"]


def test_runtime_settings_keep_unavailable_editors_highlightable(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr("klaude_cli.main.shutil.which", lambda _name: None)

    tui._open_settings_category("runtime")
    unavailable = "edit config.toml (nano) — nano unavailable"
    tui._choice_index = tui._choice_values.index(unavailable)

    assert ("class:choice.disabled.selected", f"  › {unavailable}\n") in (
        tui._choice_fragments()
    )
    tui._accept_choice()
    assert tui._choice_kind == "runtime settings"
    assert tui._choice_values[tui._choice_index] == unavailable


def test_custom_setting_edit_cancel_returns_to_its_parent_category():
    tui = _fake_persistent_tui()

    tui._runtime_edit = "num_ctx"
    tui._set_input("12345")
    tui._cancel_choice()
    assert tui._choice_kind == "runtime settings"
    assert not tui._runtime_edit

    tui._choice_kind = None
    tui._height_edit = True
    tui._set_input("3 9")
    tui._cancel_choice()
    assert tui._choice_kind == "input field settings"
    assert not tui._height_edit


def test_tui_renders_model_fragments_without_character_playback(monkeypatch):
    tui = _fake_persistent_tui()
    emitted = []
    monkeypatch.setattr(tui, "_emit", lambda kind, value: emitted.append((kind, value)))
    assert tui._emit_assistant_text("hi", initial=True) == "hi"
    assert emitted == [("append", "\nhi")]

    tui.character_stream = False
    emitted.clear()
    assert tui._emit_assistant_text("ok", initial=False) == "ok"
    assert emitted == [("append", "ok")]


def test_pastelle_themes_are_contiguous_rainbow_ordered_and_neutral_surface():
    names = tuple(TUI_THEME_LABELS)
    pastelle = tuple(name for name in names if name.startswith("pastelle-"))
    assert pastelle == (
        "pastelle-red",
        "pastelle-orange",
        "pastelle-yellow",
        "pastelle-lime",
        "pastelle-green",
        "pastelle-cyan",
        "pastelle-azure",
        "pastelle-blue",
        "pastelle-lavender",
        "pastelle-purple",
        "pastelle-magenta",
        "pastelle-pink",
    )
    assert {TUI_THEME_STYLES[name]["output-field"] for name in pastelle} == {"bg:#181818 #e8e8e8"}
    assert {TUI_THEME_STYLES[name]["input-field"] for name in pastelle} == {"bg:#242424 #f2f2f2"}


def test_status_text_has_no_fill_while_footer_uses_input_surface():
    style = _tui_style("autumn", "vscode-dark")
    status = style.get_attrs_for_style_str("class:runtime_busy")
    footer = style.get_attrs_for_style_str("class:footer")
    brand = style.get_attrs_for_style_str("class:footer.brand")
    path = style.get_attrs_for_style_str("class:footer.path")
    path_rail = style.get_attrs_for_style_str("class:footer.path.rail")
    runtime = style.get_attrs_for_style_str("class:runtime_text")
    keybinds = style.get_attrs_for_style_str("class:footer.keybinds")

    assert not status.bgcolor
    assert footer.bgcolor == "35222a"
    assert brand.bgcolor == "f29a72"
    assert brand.color == "211820"
    assert path.bgcolor == "452a35"
    assert path_rail.bgcolor == "452a35"
    assert path_rail.color == "35222a"
    assert runtime.color == "8d7878"
    assert keybinds.color == runtime.color


def test_cd_changes_agent_workspace_and_reports_current_path(tmp_path):
    from klaude_tools import Workspace

    tui = _fake_persistent_tui()
    tui.agent.workspace = Workspace(tmp_path)
    tui.agent.workdir = tmp_path
    tui._set_input("/cd")
    tui._submit_buffer(steer=False)
    assert str(tmp_path.resolve()) in tui.output.text

    target = tmp_path / "nested"
    target.mkdir()
    tui._set_input("/cd nested")
    tui._submit_buffer(steer=False)
    assert tui.agent.workdir == target.resolve()
    assert tui.agent.workspace.root == target.resolve()
    assert str(target.resolve()) in tui.output.text

    tui._set_input("/pwd")
    tui._submit_buffer(steer=False)
    assert str(target.resolve()) in tui.output.text

    (target / "folder").mkdir()
    (target / "file.txt").write_text("ok")
    tui._set_input("/ls")
    tui._submit_buffer(steer=False)
    assert "folder/" in tui.output.text
    assert "file.txt" in tui.output.text


def test_mouse_capture_is_reserved_for_click_selectable_menus():
    tui = _fake_persistent_tui()

    assert not tui._mouse_interaction_active()
    tui._begin_choice("model", ["model-a"], "model-a")
    assert tui._mouse_interaction_active()
    tui._cancel_choice()
    tui.input.buffer.complete_state = CompletionState(
        tui.input.buffer.document,
        [Completion("/help")],
        complete_index=0,
    )
    assert tui._mouse_interaction_active()


def test_termux_disables_mouse_capture_so_touch_scrolling_stays_native(monkeypatch):
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")

    assert _is_termux_terminal()

    monkeypatch.setattr("klaude_cli.main._is_termux_terminal", lambda: True)
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", ["theme", "cancel"], "theme")
    assert not tui.application.mouse_support()


def test_model_picker_cancels_while_theme_picker_goes_back_to_settings(tmp_path):
    tui = _fake_persistent_tui(
        appearance_path=tmp_path / "appearance.json",
        chat_preferences_path=tmp_path / "chat-preferences.json",
    )
    original_theme = tui.appearance.theme
    tui._set_input("/model")
    tui._submit_buffer(steer=False)

    assert tui._choice_kind == "model source"

    assert tui._choice_values[-1] == "cancel"
    tui._choice_index = len(tui._choice_values) - 1
    tui._accept_choice()
    assert tui._choice_kind is None
    assert tui.agent.model == "qwen3.5:4b"

    tui._set_input("/theme")
    tui._submit_buffer(steer=False)
    assert tui._choice_kind == "theme settings"
    tui._choice_index = tui._choice_values.index("interface theme: Pastelle Azure")
    tui._accept_choice()
    assert tui._choice_values[-1] == "back"
    tui._choice_index = len(tui._choice_values) - 1
    tui._accept_choice()
    assert tui._choice_kind == "theme settings"
    assert tui.appearance.theme == original_theme


@pytest.mark.parametrize("cancel_at", ["mode", "effort"])
def test_cancel_during_reasoning_picker_restores_runtime_without_saving(tmp_path, cancel_at):
    preferences = tmp_path / "preferences.json"
    preferences.write_text('{"last_model": "ollama/qwen3.5:4b", "future": 1}')
    tui = _fake_persistent_tui(chat_preferences_path=preferences)
    original_runtime = tui.agent.ollama
    tui.agent.history = ["existing conversation"]
    tui._set_input("/model")
    tui._submit_buffer(steer=False)
    tui._choice_index = tui._choice_values.index("Local")
    tui._accept_choice()
    identity = tui._background_jobs.latest["local-models"]
    tui._apply_background_result((
        "local-models", identity, {"names": ["qwen3.5:4b", "gpt-oss:20b"]}, ""
    ))
    tui._choice_index = tui._choice_values.index("gpt-oss:20b")
    tui._accept_choice()

    assert tui.agent.model == "gpt-oss:20b"
    assert tui._choice_kind == "mode"
    if cancel_at == "effort":
        tui._choice_index = tui._choice_values.index("thinking")
        tui._accept_choice()
        assert tui._choice_kind == "effort"
    assert tui._choice_values[-1] == "cancel"
    tui._choice_index = len(tui._choice_values) - 1
    tui._accept_choice()

    assert tui._choice_kind is None
    assert tui.agent.model == "qwen3.5:4b"
    assert tui.agent.ollama is original_runtime
    assert tui.agent.history == ["existing conversation"]
    assert tui._runtime_save_revision == 0 and tui._model_save_state == ""
    assert json.loads(preferences.read_text()) == {"last_model": "ollama/qwen3.5:4b", "future": 1}


def test_confirmed_model_save_is_async_and_failures_keep_selected_runtime(monkeypatch):
    tui = _fake_persistent_tui()
    requests = []

    class PendingWriter:
        def submit(self, changes):
            requests.append(dict(changes))
            return len(requests)

    tui._settings_writer = PendingWriter()
    actions = []

    class PendingActions:
        def submit(self, action):
            actions.append(action)
            return True

    tui._session_actions = PendingActions()
    monkeypatch.setattr(tui.memory, "log_turn", lambda *args: pytest.fail("UI database write"))
    monkeypatch.setattr(
        tui.memory, "publish_session_event", lambda *args, **kwargs: pytest.fail("UI event write")
    )
    monkeypatch.setattr(
        "klaude_cli.main.update_settings", lambda *args, **kwargs: pytest.fail("UI write")
    )
    tui.agent.history = ["existing conversation"]
    tui._activate_selected_model(ModelInfo("ollama", "gpt-oss:20b", "gpt-oss:20b"))
    selected_runtime = tui.agent.ollama
    assert requests == [] and tui._choice_kind == "mode"
    tui._choice_index = tui._choice_values.index("standard")
    tui._accept_choice()
    assert requests == [{("last_model",): "ollama/gpt-oss:20b"}]
    assert len(actions) == 1 and actions[0].session_id == tui.session_id
    assert tui._model_save_state == "saving"
    assert tui.agent.history == ["existing conversation"]
    # A later unrelated write shares the serialized revision boundary.
    tui._persist_runtime_preferences("num_ctx")
    tui._emit("settings_saved", (1, False))
    tui._before_render(None)
    assert tui._model_save_state == "saving"
    tui._emit("settings_saved", (2, False))
    tui._before_render(None)
    assert tui._model_save_state == "failed"
    assert tui.agent.model == "gpt-oss:20b" and tui.agent.ollama is selected_runtime
    assert tui.agent.history == ["existing conversation"]
    tui._persist_runtime_preferences("num_ctx")
    tui._emit("settings_saved", (3, True))
    tui._before_render(None)
    assert tui._model_save_state == "saved"


def test_session_setting_failures_report_original_scope_without_changing_runtime():
    from klaude_cli.session_actions import SessionSettingUpdate

    tui = _fake_persistent_tui()
    original = tui.agent.ollama
    tui._emit("session_setting_saved", (
        SessionSettingUpdate("previous-session", tui.client_id, "model change"), False
    ))
    tui._before_render(None)
    assert "save unconfirmed for previous-session" in tui.output.text
    assert tui.status_error == ""
    assert tui.agent.ollama is original


@pytest.mark.parametrize("path", [
    "packages/core/src/klaude_core/knowledge_tool_contract.py",
    "/home/klaude/klaude-code/packages/core/src/klaude_core/agent.py",
    "https://example.org/model/reference",
])
def test_workspace_paths_and_urls_are_not_slash_command_help(path):
    request = (
        f"Inspect the workspace read-only. Read {path} and explain its behavior. "
        "Do not use web search or modify files."
    )
    assert resolve_command_help_request(request) is None
    tools = {
        name: Tool(name, name, {}, lambda: "")
        for name in ("read_file", "list_dir", "grep", "workspace_info", "list_commands")
    }
    selected = _select_tool_names(request, tools)
    assert "read_file" in selected
    assert "list_commands" not in selected


@pytest.mark.parametrize("operation", ["model", "memory"])
def test_settings_picker_responds_while_session_write_is_blocked(
    tmp_path, monkeypatch, operation
):
    import threading

    from klaude_cli.session_actions import SessionActionWriter

    async def exercise():
        tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
        memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
        entered, release = threading.Event(), threading.Event()
        method = "record_session_update" if operation == "model" else "set_auto_memory"
        original = getattr(Memory, method)

        def blocked(connection, *args):
            entered.set()
            assert release.wait(3)
            return original(connection, *args)

        monkeypatch.setattr(Memory, method, blocked)
        writer = SessionActionWriter(memory, tui._emit)
        tui._session_actions = writer
        if operation == "model":
            tui._model_flow_parent = "settings"
            tui._activate_selected_model(ModelInfo("ollama", "gpt-oss:20b", "gpt-oss:20b"))
            tui._choice_index = tui._choice_values.index("standard")
            tui._accept_choice()
            query = "models"
        else:
            tui.memory = memory
            tui._status_memory_enabled = True
            tui._open_settings_category("memory")
            tui._choice_index = tui._choice_values.index("automatic memory: on (toggle)")
            tui._accept_choice()
            query = "automatic"
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                assert entered.is_set()
                pipe.send_text("/" + query if operation == "model" else query)
                for _ in range(40):
                    if tui._choice_filter_query == query:
                        break
                    await asyncio.sleep(0.025)
                assert tui._choice_filter_query == query
                assert (tui.panel_body_window if tui._panel else tui.choice_window
                        ).render_info is not None
                assert memory.load_session(tui.session_id) == []
            finally:
                release.set()
                tui.application.exit()
                await task
                assert writer.close(wait=True)
                expected_turns = 1 if operation == "model" else 0
                assert len(memory.load_session(tui.session_id)) == expected_turns
                if operation == "memory":
                    assert memory.db.execute(
                        "SELECT value FROM settings WHERE key='auto_memory_enabled'"
                    ).fetchone()[0] == "0"
                memory.db.close()

    asyncio.run(exercise())


def test_mode_only_selection_does_not_change_remembered_model(tmp_path):
    preferences = tmp_path / "preferences.json"
    preferences.write_text('{"last_model": "ollama/another-model"}')
    tui = _fake_persistent_tui(chat_preferences_path=preferences)
    tui._begin_choice("mode", ["standard", "thinking", "cancel"], "standard")
    tui._accept_choice()
    assert tui._runtime_save_revision == 0 and tui._model_save_state == ""
    assert json.loads(preferences.read_text()) == {"last_model": "ollama/another-model"}


def test_cloud_providers_remain_available_for_in_picker_login(monkeypatch):
    monkeypatch.setattr("klaude_cli.main.load_model_cache", lambda _path: [])
    tui = _fake_persistent_tui()
    tui._open_cloud_provider()

    fragments = tui._choice_fragments()

    assert tui._choice_values[tui._choice_index] == "OpenAI"
    assert ("class:choice.selected", "  › OpenAI\n") in fragments
    assert all("API key not configured" not in value for value in tui._choice_values)
    assert tui._choice_values[-3:] == [
        "back",
        "",
        "Tip: open any cloud provider to sign in, sign out, or choose a model",
    ]
    assert ("class:choice.disabled", "\n") in fragments
    assert (
        "class:choice.disabled",
        "    Tip: open any cloud provider to sign in, sign out, or choose a model",
    ) in fragments


def test_unauthenticated_cloud_provider_opens_login_action(monkeypatch):
    monkeypatch.setattr("klaude_cli.main.load_model_cache", lambda _path: [])
    tui = _fake_persistent_tui()
    tui._open_cloud_provider()

    tui._choice_index = tui._choice_values.index("OpenRouter")
    tui._accept_choice()

    assert tui._choice_kind == "model"
    assert tui._choice_values[tui._choice_index] == "Login"
    assert tui._panel.page.rows[0].description == "Status: not signed in"


def test_expired_codex_auth_keeps_model_picker_open(monkeypatch):
    async def exercise():
        tui = _fake_persistent_tui()
        tui._model_choices = {
            "gpt-5.6-sol": ModelInfo("openai_codex", "gpt-5.6-sol", "GPT-5.6 Sol")
        }
        tui._begin_choice("model", ["gpt-5.6-sol", "back"], "gpt-5.6-sol")
        tui._accept_choice()
        task = tui._setup_job
        for _ in range(5):
            await asyncio.sleep(0)
            if tui._model_activation_id:
                break
        tui._apply_background_result((
            "model-activation", tui._model_activation_id, None, "expired authentication"
        ))
        await task
        assert tui._choice_kind == "model"
        assert tui.agent.model == "qwen3.5:4b"
        assert "check sign-in" in tui.status_error

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "minimum,maximum,count,selected,expected_height",
    [(8, 12, 2, 1, 6), (2, 10, 5, 4, 7), (8, 12, 30, 25, 10), (1, 1, 30, 25, 1), (6, 6, 30, 25, 4)],
)
def test_live_picker_scrolls_selected_row_into_view(
    tmp_path,
    minimum,
    maximum,
    count,
    selected,
    expected_height,
):
    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json")
        tui.appearance.input_height = minimum
        tui.appearance.input_max_height = maximum
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            tui._begin_choice("generic", [f"model-{i:02}" for i in range(count)], "model-00")
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.1)
                pipe.send_text("\x1b[B" * selected)
                await asyncio.sleep(0.2)
                info = tui.choice_window.render_info
                assert info is not None
                assert tui._choice_index == selected
                assert info.window_height == expected_height
                if selected >= expected_height:
                    assert info.vertical_scroll > 0
                assert selected in info.displayed_lines
                assert tui.application.layout.current_control is tui.choice_control
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_live_picker_keeps_heading_above_first_option_visible():
    async def exercise():
        tui = _fake_persistent_tui()
        tui.appearance.input_height = 4
        tui.appearance.input_max_height = 4
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            tui._open_settings_category("tools")
            tui._choice_index = tui._choice_values.index("activity updates: on (toggle)")
            assert tui._picker is not None
            tui._picker.scroll_top = tui._choice_index
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.1)
                info = tui.panel_body_window.render_info
                assert info is not None
                assert tui._panel_body().selected_line in info.displayed_lines
                assert 0 in info.displayed_lines
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


@pytest.mark.parametrize("responds_to_cpr", [False, True])
@pytest.mark.parametrize("switch_session", [False, True])
@pytest.mark.parametrize("show_divider", [False, True])
def test_terminal_scrollback_survives_streaming_refresh_resize_and_preview(
    tmp_path,
    responds_to_cpr,
    switch_session,
    show_divider,
):
    import pyte
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.vt100 import Vt100_Output
    from prompt_toolkit.renderer import CPR_Support

    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json")
        tui.appearance.divider_visible = show_divider

        class Screen(pyte.HistoryScreen):
            def write_process_input(self, data):
                if responds_to_cpr:
                    pipe.send_text(data)

        screen = Screen(100, 30, history=2000)
        stream = pyte.Stream(screen)
        captured = StringIO()

        class Terminal:
            def isatty(self):
                return True

            def write(self, text):
                captured.write(text)
                stream.feed(text)

            def flush(self):
                pass

        output = Vt100_Output(
            Terminal(),
            lambda: Size(rows=screen.lines, columns=screen.columns),
            enable_cpr=responds_to_cpr,
        )

        def transcript_lines():
            return [
                "".join(row[x].data for x in range(screen.columns)).rstrip()
                for row in screen.history.top
            ] + [line.rstrip() for line in screen.display]

        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = output
            tui.application.renderer.output = output
            # The fake TUI starts with DummyOutput, which disables CPR. Merely
            # swapping output does not enable terminal cursor reports.
            tui.application.renderer.cpr_support = (
                CPR_Support.SUPPORTED if responds_to_cpr else CPR_Support.NOT_SUPPORTED
            )
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                expected = [f"session message {i:03d}" for i in range(120)]
                for start in range(0, 120, 12):
                    tui._append("\n".join(expected[start : start + 12]) + "\n")
                    tui.application._redraw()
                    await asyncio.sleep(0.01)
                tui._append("streaming par")
                tui.application._redraw()
                assert tui.live_output.text == "streaming par"
                tui._append("tial\n")
                tui.application._redraw()
                expected.append("streaming partial")
                wrapped = "wrapped-output-" * 100
                tui._append(wrapped + "\n")
                tui.application._redraw()
                assert wrapped.strip() in "".join(transcript_lines())
                tui._set_input("unsent draft\nsecond line")
                tui.pending.append("queued follow-up")
                tui._refresh_tui()
                screen.resize(lines=36, columns=110)
                tui.application._redraw()
                tui._show_text_theme_preview()
                tui._append("arrived during preview\n")
                tui.application._redraw()
                tui._hide_text_theme_preview()
                tui.application._redraw()
                expected.append("arrived during preview")
                tui._open_settings_category("permissions")
                tui.application._redraw()
                tui._append("arrived during settings\n")
                tui.application._redraw()
                tui._cancel_choice()
                tui._cancel_choice()
                tui.application._redraw()
                expected.append("arrived during settings")
                lines = transcript_lines()
                assert [line for line in lines if line in expected] == expected, lines[-50:]
                assert any("Session: session-1" in line for line in lines)
                assert tui.input.text == "unsent draft\nsecond line"
                assert not tui.live_output.text
                assert tui.output.window.render_info is None
                if switch_session:
                    tui.pending.clear()
                    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
                    tui.memory.log_turn("session-1", "user", "Original saved conversation")
                    tui.memory.log_turn("other", "user", "Selected saved conversation")
                    saved_lines = [f"restored answer line {i:03d}" for i in range(60)]
                    tui.memory.log_turn("other", "assistant", "\n".join(saved_lines))
                    tui.agent.restore_session = lambda turns: Agent.restore_session(
                        tui.agent,
                        turns,
                    )
                    if responds_to_cpr:
                        # A terminal whose CPR support is still being detected
                        # permits only one outstanding measurement. A report
                        # taken before replay would incorrectly reserve the
                        # whole screen after the replay has already printed.
                        tui.application.renderer.cpr_support = CPR_Support.UNKNOWN
                    tui._set_input("/resume other")
                    tui._submit_buffer(steer=False)
                    tui.application._redraw()
                    await asyncio.sleep(0.1)
                    lines = transcript_lines()
                    assert "Selected saved conversation" in lines
                    assert [line for line in lines if line in saved_lines] == saved_lines
                    assert saved_lines[-1] in [line.rstrip() for line in screen.display]
                    closing = next(line for line in lines if "klaude · " in line)
                    assert ("━" in closing) is show_divider
                    assert tui.input.window.render_info is not None
                    assert tui.application.layout.current_control is tui.input.control
                    assert not any(line in expected for line in lines)
                    assert "Session: session-1" not in "\n".join(lines)
                    tui._set_input("/new")
                    tui._submit_buffer(steer=False)
                    tui.application._redraw()
                    await asyncio.sleep(0.01)
                    assert "Selected saved conversation" not in transcript_lines()
                    assert tui.session_id in "\n".join(transcript_lines())
                    assert len(tui.memory.load_session("other")) == 2
                    assert len(tui.memory.load_session("session-1")) == 1
                    expected = []
            finally:
                tui.application.exit()
                await task
            lines = transcript_lines()
            assert [line for line in lines if line in expected] == expected
            assert "\x1b[?1049h" not in captured.getvalue()
            assert ("\x1b[3J" in captured.getvalue()) is switch_session

    asyncio.run(exercise())


@pytest.mark.parametrize("show_divider", [False, True])
def test_printed_transcript_background_fills_rows_without_padding(tmp_path, show_divider):
    import pyte
    from klaude_cli.main import _session_divider
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.color_depth import ColorDepth
    from prompt_toolkit.output.vt100 import Vt100_Output

    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.appearance.divider_visible = show_divider
    tui.application.style = _tui_style("autumn", "vscode-dark")
    screen = pyte.Screen(80, 30)
    stream = pyte.Stream(screen)

    class Terminal:
        def write(self, text):
            stream.feed(text)

        def flush(self):
            pass

    output = Vt100_Output(
        Terminal(),
        lambda: Size(rows=30, columns=80),
        default_color_depth=ColorDepth.DEPTH_24_BIT,
        enable_cpr=False,
    )
    tui.application.output = tui.application.renderer.output = output
    lines = [
        _session_divider("test", width=80),
        "[success] Green success",
        "",
        "━━ you · time ━━",
        "assistant text",
        "",
        "```python",
        "value = 1",
        "```",
        "X" * 80,
        "Y" * 85,
    ]
    text = "\n".join(lines) + "\n"
    tui.output.buffer.set_document(Document(text, len(text)), bypass_readonly=True)
    tui._flush_transcript()

    normal = tui.application.style.get_attrs_for_style_str("class:output-field").bgcolor
    surface = tui.application.style.get_attrs_for_style_str("class:transcript.user-message").bgcolor
    code_surface = tui.application.style.get_attrs_for_style_str("class:transcript.code").bgcolor
    for row in set(range(12)) - {1}:
        expected = code_surface if row in {6, 7, 8} else surface if row in {1, 2} else normal
        assert {screen.buffer[row][column].bg for column in range(80)} == {expected}
    success = tui.application.style.get_attrs_for_style_str("class:transcript.label.success.word")
    assert {screen.buffer[1][column].bg for column in range(9)} == {success.bgcolor}
    assert {screen.buffer[1][column].bg for column in range(9, 80)} == {surface}
    assert screen.buffer[1][0].fg == success.bgcolor
    assert {screen.buffer[1][column].fg for column in range(1, 8)} == {success.color}
    assert screen.display[9] == "X" * 80
    assert screen.display[10] == "Y" * 80
    assert screen.display[11].rstrip() == "Y" * 5
    assert tui.output.text == text


def test_escape_follows_a_pickers_visible_back_or_cancel_action():
    tui = _fake_persistent_tui()

    tui._begin_choice("model", ["demo-model", "back"], "demo-model")
    tui._model_parent = "cloud"
    tui._dismiss_picker()
    assert tui._choice_kind == "model cloud provider"

    tui._dismiss_picker()
    assert tui._choice_kind == "model source"

    tui._dismiss_picker()
    assert tui._choice_kind is None

    tui._open_settings_category("tools")
    tui._dismiss_picker()
    assert tui._choice_kind == "settings"
    assert tui._choice_values[tui._choice_index].startswith("Tools:")

    tui._open_settings_category("providers")
    tui._open_provider_key_settings("OpenRouter")
    tui._dismiss_picker()
    assert tui._choice_kind == "providers settings"
    assert tui._choice_values[tui._choice_index].startswith("OpenRouter:")

    tui._begin_choice("input height", ["8 lines", "cancel"], "8 lines")
    tui._dismiss_picker()
    assert tui._choice_kind == "input field settings"


def test_height_range_rejects_invalid_input_and_persists_valid_range(tmp_path):
    path = tmp_path / "appearance.json"
    tui = _fake_persistent_tui(path)
    tui._height_edit = True
    for invalid in ("9 2", "0 8", "1 13", "two 8", "3.5 8", "8"):
        tui._set_input(invalid)
        tui._submit_buffer(steer=False)
        assert tui._height_edit
        assert not path.exists()
    tui._set_input("2 10")
    tui._submit_buffer(steer=False)
    loaded = _load_tui_appearance(path)
    assert (loaded.input_height, loaded.input_max_height) == (2, 10)
    assert not tui._height_edit


def test_theme_preview_cancel_restores_colors_and_preserves_new_output(tmp_path):
    path = tmp_path / "appearance.json"
    tui = _fake_persistent_tui(path)
    original = (tui.appearance.theme, tui.appearance.text_theme)
    tui._begin_choice("theme", [DEFAULT_TUI_THEME, "neon-synth"], DEFAULT_TUI_THEME)
    tui._move_choice(1)
    assert tui.appearance.theme == "neon-synth"
    preview_rows = "".join(text for _style, text in tui._choice_fragments())
    assert f"{DEFAULT_TUI_THEME} *" in preview_rows
    assert "neon-synth *" not in preview_rows
    assert not path.exists()
    tui._cancel_choice()
    assert (tui.appearance.theme, tui.appearance.text_theme) == original
    assert tui._choice_kind == "theme settings"
    tui._begin_choice("text theme", ["vscode-dark", "monokai"], "vscode-dark")
    tui._move_choice(1)
    assert "```html" in tui.text_theme_preview.text
    assert tui.text_theme_preview.text == TEXT_THEME_PREVIEW_BLOCK
    assert tui.text_theme_preview.buffer.cursor_position == 0
    tui._append("\narrived during preview\n")
    assert "arrived during preview" not in tui.output.text
    tui._cancel_choice()
    assert TEXT_THEME_PREVIEW_BLOCK not in tui.output.text
    assert "arrived during preview" in tui.output.text
    assert (tui.appearance.theme, tui.appearance.text_theme) == original
    assert tui._choice_kind == "theme settings"


def test_text_theme_preview_page_keys_scroll_its_dedicated_pane(monkeypatch):
    tui = _fake_persistent_tui()
    tui._begin_choice("text theme", ["vscode-dark", "monokai"], "vscode-dark")
    tui._move_choice(1)
    scrolls = []
    monkeypatch.setattr(tui.text_theme_preview.window, "_scroll_up", lambda: scrolls.append("up"))
    monkeypatch.setattr(
        tui.text_theme_preview.window, "_scroll_down", lambda: scrolls.append("down")
    )
    handlers = {
        tuple(binding.keys): binding.handler
        for binding in tui.key_bindings.bindings
        if tuple(binding.keys) in {(Keys.PageUp,), (Keys.PageDown,)}
    }

    handlers[(Keys.PageUp,)](None)
    handlers[(Keys.PageDown,)](None)

    assert scrolls == ["up", "down"]


def test_persistent_tui_replaces_live_context_estimate_with_exact_tokens():
    tui = _fake_persistent_tui()
    tui.running = True
    tui.ui_state.prompt_tokens = 3000
    tui.ui_state.prompt_tokens_estimated = True
    tui._events.put(
        (
            "turn_done",
            {"metadata": {"prompt_eval_count": 2400, "eval_count": 120}},
        )
    )

    tui._before_render(None)

    assert tui.ui_state.prompt_tokens == 2400
    assert tui.ui_state.output_tokens == 120
    assert tui.ui_state.prompt_tokens_estimated is False
    assert tui.running is False


def test_persistent_tui_reads_openai_usage_without_losing_missing_estimate():
    tui = _fake_persistent_tui()
    tui.ui_state.prompt_tokens = 3000
    tui.ui_state.output_tokens = 40
    tui.ui_state.prompt_tokens_estimated = True

    tui._events.put(
        (
            "turn_done",
            {"metadata": {"usage": {"input_tokens": 2400, "output_tokens": 120}}},
        )
    )
    tui._before_render(None)

    assert tui.ui_state.prompt_tokens == 2400
    assert tui.ui_state.output_tokens == 120
    assert tui.ui_state.prompt_tokens_estimated is False

    tui.ui_state.prompt_tokens = 2800
    tui.ui_state.prompt_tokens_estimated = True
    tui._events.put(("turn_done", {"metadata": {"provider": "openai_codex"}}))
    tui._before_render(None)

    assert tui.ui_state.prompt_tokens == 2800
    assert tui.ui_state.prompt_tokens_estimated is True


def test_resumed_observer_receives_cloud_token_usage(tmp_path):
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    observer = _fake_persistent_tui(tmp_path / "appearance.json")
    observer.memory = memory
    observer.session_id = "shared"
    observer.agent.restore_session = lambda _turns: None
    observer.ui_state.prompt_tokens = 3000
    observer.ui_state.prompt_tokens_estimated = True
    memory.publish_session_event(
        "shared",
        "remote-owner",
        "turn_done",
        {
            "model_metadata": {
                "provider": "openai_codex",
                "response_id": "resp_public",
                "usage": {"input_tokens": 2500, "output_tokens": 175},
            }
        },
        turn_id="remote-turn",
    )

    observer._sync_shared_session()

    assert observer.ui_state.prompt_tokens == 2500
    assert observer.ui_state.output_tokens == 175
    assert observer.ui_state.prompt_tokens_estimated is False


def test_shared_model_metadata_is_secret_free_and_bounded():
    public = _public_model_metadata(
        {
            "provider": "openai_codex",
            "response_id": "resp_public",
            "status": "completed",
            "access_token": "secret",
            "headers": {"authorization": "Bearer secret"},
            "usage": {
                "input_tokens": 12,
                "output_tokens": 4,
                "input_tokens_details": {"cached_tokens": 7},
            },
        }
    )

    assert public == {
        "provider": "openai_codex",
        "response_id": "resp_public",
        "status": "completed",
        "usage": {
            "input_tokens": 12,
            "output_tokens": 4,
            "input_tokens_details": {"cached_tokens": 7},
        },
    }


def test_failed_request_retains_last_known_usage_without_claiming_new_counts():
    from klaude_cli.main import _agent_model_metadata

    agent = SimpleNamespace(
        ollama=SimpleNamespace(last_chat_metadata={}), last_request_usage=(6510, 120),
    )
    metadata = _agent_model_metadata(agent)
    assert metadata == {
        'usage': {'input_tokens': 6510, 'output_tokens': 120},
        'usage_from_previous_request': True,
    }
    agent.ollama.last_chat_metadata = {'prompt_eval_count': 6200, 'eval_count': 75}
    metadata = _agent_model_metadata(agent)
    assert metadata['prompt_eval_count'] == 6200
    assert metadata['eval_count'] == 75
    assert 'usage_from_previous_request' not in metadata


def test_prompt_cache_status_ignores_malformed_provider_counters():
    agent = SimpleNamespace(
        ollama=SimpleNamespace(
            last_chat_metadata={
                "usage": {
                    "input_tokens": "unknown",
                    "input_tokens_details": {
                        "cached_tokens": {"unexpected": True},
                        "cache_write_tokens": -1,
                    },
                }
            }
        )
    )

    assert _prompt_cache_status(agent) is None


def test_persistent_tui_permission_answer_unblocks_worker_request():
    tui = _fake_persistent_tui()
    done = __import__("threading").Event()
    request = {"tool": "run_shell", "detail": "run tests", "answer": "n", "done": done}
    tui._permission_request = request

    tui._answer_permission("a")

    assert request["answer"] == "a"
    assert done.is_set()
    assert tui._permission_request is None


def test_user_input_broker_normalizes_options_and_returns_structured_answer():
    broker = UserInputBroker()
    captured = []
    broker.handler = lambda question, options, header: (
        captured.append((question, options, header)) or ("Banana", "option")
    )

    result = json.loads(
        broker.request(
            " Pick one ",
            [
                {"label": " Apple ", "description": " Red fruit "},
                {"label": "apple", "description": "duplicate"},
                " Banana ",
            ],
            " Fruit ",
        )
    )

    assert captured == [
        (
            "Pick one",
            [
                {"label": "Apple", "description": "Red fruit"},
                {"label": "Banana", "description": ""},
            ],
            "Fruit",
        )
    ]
    assert result == {"status": "answered", "answer": "Banana", "source": "option"}


def test_user_input_composer_submits_custom_text_without_overwriting_selection():
    tui = _fake_persistent_tui()
    done = __import__("threading").Event()
    request = {
        "request_id": "request-1",
        "question": "Which fruit?",
        "options": _normalized_user_input_options(["Apple", "Banana", "Orange"]),
        "answer": None,
        "source": "cancelled",
        "done": done,
        "remote": False,
        "turn_id": "turn-1",
    }
    tui._user_input_request = request
    tui._set_input("Dragon fruit")

    tui._move_user_input_choice(1)
    tui._submit_user_input_response()

    assert request["answer"] == "Dragon fruit"
    assert request["source"] == "custom"
    assert done.is_set()
    assert tui._user_input_request is None


def test_user_input_composer_uses_highlighted_option_only_when_draft_is_empty():
    tui = _fake_persistent_tui()
    done = __import__("threading").Event()
    request = {
        "request_id": "request-2",
        "question": "Which fruit?",
        "options": _normalized_user_input_options(["Apple", "Banana", "Orange"]),
        "answer": None,
        "source": "cancelled",
        "done": done,
        "remote": False,
        "turn_id": "turn-2",
    }
    tui._user_input_request = request
    tui._user_input_index = 2

    tui._submit_user_input_response()

    assert request["answer"] == "Orange"
    assert request["source"] == "option"


def test_remote_user_input_stays_open_when_answer_cannot_be_published(monkeypatch):
    tui = _fake_persistent_tui()
    request = {
        "request_id": "request-remote",
        "question": "Which fruit?",
        "options": _normalized_user_input_options(["Apple"]),
        "remote": True,
        "turn_id": "turn-remote",
    }
    tui._user_input_request = request
    monkeypatch.setattr(tui, "_publish_shared_event", lambda *_args, **_kwargs: False)

    tui._submit_user_input_response()

    assert tui._user_input_request is request
    assert "not submitted" in tui.status_error


def test_pending_user_input_is_recovered_only_until_its_answer():
    request = {
        "role": "system",
        "content": {
            "event": "input_request",
            "request_id": "request-1",
            "question": "Which fruit?",
            "options": [{"label": "Apple", "description": ""}],
        },
    }
    assert _pending_input_request_from_turns([request])["question"] == "Which fruit?"
    answer = {
        "role": "system",
        "content": {
            "event": "input_answer",
            "request_id": "request-1",
            "answer": "Apple",
        },
    }
    assert _pending_input_request_from_turns([request, answer]) is None


def test_permission_prompt_emits_waiting_activity_state(monkeypatch):
    tui = _fake_persistent_tui()
    emitted = []
    updates = []
    published = []

    def emit(kind, payload=None):
        emitted.append((kind, payload))
        if kind == "permission":
            payload["done"].set()

    monkeypatch.setattr(tui, "_emit", emit)
    monkeypatch.setattr(
        tui,
        "_record_activity_update",
        lambda label, detail, *, turn_id: updates.append((label, detail, turn_id)),
    )
    monkeypatch.setattr(
        tui,
        "_publish_shared_event",
        lambda kind, payload, *, turn_id: published.append((kind, payload, turn_id)),
    )
    tui._turn_id = "turn-1"

    assert tui._ask_permission("run_shell", "run tests") == "n"
    assert emitted[0] == ("activity", "waiting for run shell approval")
    assert updates == [("denied", "Permission for run shell", "turn-1")]
    assert published[0] == (
        "activity",
        {"text": "waiting for run shell approval"},
        "turn-1",
    )


def test_active_ollama_service_control_confirms_before_cancelling(monkeypatch):
    tui = _fake_persistent_tui()
    tui.running = True
    cancel_calls = []
    control_finished = threading.Event()
    tui.agent.ollama.cancel_active = lambda: cancel_calls.append("cancel") or True

    def approve(_tool, _detail):
        assert cancel_calls == []
        return "y"

    def control(action):
        assert action == "restart"
        control_finished.set()
        return True, "Ollama service restarted"

    monkeypatch.setattr(tui, "_ask_permission", approve)
    monkeypatch.setattr("klaude_cli.main._control_ollama_service", control)

    tui._request_ollama_service_control("restart")

    assert control_finished.wait(2)
    assert cancel_calls == ["cancel"]


def test_starting_ollama_does_not_cancel_an_active_response(monkeypatch):
    tui = _fake_persistent_tui()
    tui.running = True
    cancel_calls = []
    prompts = []
    control_finished = threading.Event()
    tui.agent.ollama.cancel_active = lambda: cancel_calls.append("cancel") or True
    monkeypatch.setattr(
        tui,
        "_ask_permission",
        lambda _tool, detail: prompts.append(detail) or "y",
    )

    def control(action):
        assert action == "start"
        control_finished.set()
        return True, "Ollama service started"

    monkeypatch.setattr("klaude_cli.main._control_ollama_service", control)

    tui._request_ollama_service_control("start")

    assert control_finished.wait(2)
    assert cancel_calls == []
    assert prompts == ["Start the local Ollama service?"]


def test_ollama_service_control_supports_start(monkeypatch):
    calls = []
    monkeypatch.setattr("klaude_cli.main.shutil.which", lambda command: "/usr/bin/systemctl")

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("klaude_cli.main.subprocess.run", run)

    ok, message = _control_ollama_service("start")

    assert ok
    assert message == "Ollama service started"
    assert calls[0][0] == ["systemctl", "--no-ask-password", "start", "ollama"]


def test_cancelled_transport_error_is_not_saved_as_runtime_failure(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.agent.run = lambda _message, *, scope=None: iter(
        [AgentEvent("error", {"message": "[Errno 9] Bad file descriptor"})]
    )
    cancelled = threading.Event()
    cancelled.set()

    tui._run_turn("hello", cancelled, turn_id="turn-1")

    turns = tui.memory.load_session(tui.session_id)
    assert turns[0] == {"role": "user", "content": "hello"}
    assert turns[1]["content"]["event"] == "interruption"
    assert "Bad file descriptor" not in str(turns)
    events = tui.memory.session_events_since(tui.session_id, 0)
    assert "error" not in {event["kind"] for event in events}


def test_ollama_service_control_does_not_attempt_an_interactive_password(monkeypatch):
    from types import SimpleNamespace

    calls = []
    monkeypatch.setattr("klaude_cli.main.shutil.which", lambda command: "/usr/bin/systemctl")
    monkeypatch.setattr(
        "klaude_cli.main.subprocess.run",
        lambda arguments, **kwargs: (
            calls.append((arguments, kwargs))
            or SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="Failed to restart ollama.service: Interactive authentication required.\n",
            )
        ),
    )

    ok, message = _control_ollama_service("restart")

    assert not ok
    assert calls[0][0] == ["systemctl", "--no-ask-password", "restart", "ollama"]
    assert "sudo systemctl restart ollama" in message


def test_ollama_service_control_gives_a_terminal_command_for_generic_failures(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("klaude_cli.main.shutil.which", lambda command: "/usr/bin/systemctl")
    monkeypatch.setattr(
        "klaude_cli.main.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="See system logs and 'systemctl status ollama.service' for details.\n",
            stderr="",
        ),
    )

    ok, message = _control_ollama_service("restart")

    assert not ok
    assert "sudo systemctl restart ollama" in message


def test_sudo_ollama_control_keeps_password_out_of_argv_and_service_stdin(monkeypatch):
    calls = []
    monkeypatch.setattr("klaude_cli.main.shutil.which", lambda command: f"/usr/bin/{command}")

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("klaude_cli.main.subprocess.run", run)

    ok, message = _control_ollama_service_with_sudo("restart", "private-password")

    assert ok
    assert message == "Ollama service restarted"
    assert calls[0][0] == ["/usr/bin/sudo", "-S", "-p", "", "-v"]
    assert calls[0][1]["input"] == "private-password\n"
    assert calls[1][0] == [
        "/usr/bin/sudo",
        "-n",
        "--",
        "/usr/bin/systemctl",
        "--no-ask-password",
        "restart",
        "ollama",
    ]
    assert calls[1][1]["stdin"] is subprocess.DEVNULL
    assert all("private-password" not in argument for call, _kwargs in calls for argument in call)


def test_masked_secret_composer_round_trip_clears_input_and_can_cancel():
    tui = _fake_persistent_tui()
    result = []

    worker = threading.Thread(
        target=lambda: result.append(tui._ask_secret("API key", "Enter API key"))
    )
    worker.start()
    for _attempt in range(20):
        tui._before_render(None)
        if tui._secret_request:
            break
        threading.Event().wait(0.01)

    assert tui._secret_request is not None
    password_processor = next(
        processor
        for processor in tui.input.control.input_processors
        if type(getattr(processor, "processor", None)).__name__ == "PasswordProcessor"
    )
    assert password_processor.filter()
    tui._set_input("private-api-key")
    tui._submit_secret_response()
    worker.join(2)

    assert result == ["private-api-key"]
    assert tui.input.text == ""


def test_provider_settings_collect_and_save_api_key_through_masked_composer(monkeypatch):
    tui = _fake_persistent_tui()
    saved = []
    monkeypatch.setattr(
        "klaude_cli.main.save_provider_secret",
        lambda config_dir, name, value: saved.append((config_dir, name, value)),
    )

    tui._open_settings_category("providers")
    row = next(value for value in tui._choice_values if value.startswith("OpenRouter:"))
    tui._choice_index = tui._choice_values.index(row)
    tui._accept_choice()

    assert tui._choice_kind == "provider key settings"
    assert tui._panel.page.rows[0].description == "Status: not configured"
    assert "Add API key" in tui._choice_values
    assert "Remove API key" not in tui._choice_values
    tui._choice_index = tui._choice_values.index("Add API key")
    tui._accept_choice()
    assert tui._secret_request is not None
    password_processor = next(
        processor
        for processor in tui.input.control.input_processors
        if type(getattr(processor, "processor", None)).__name__ == "PasswordProcessor"
    )
    assert password_processor.filter()
    tui._set_input("sk-or-secret")
    tui._submit_secret_response()

    assert saved == [(tui.cfg.config_dir, "OPENROUTER_API_KEY", "sk-or-secret")]
    assert tui.cfg.openrouter_api_key == "sk-or-secret"
    assert "sk-or-secret" not in tui.output.text
    assert tui._choice_kind == "provider key settings"
    assert tui._panel.page.rows[0].description == "Status: configured"
    assert "Update API key" in tui._choice_values
    assert "Remove API key" in tui._choice_values
    assert tui._choice_values[tui._choice_index] == "Update API key"
    assert tui._secret_request is None
    assert not password_processor.filter()

    tui._open_settings_category("providers")
    assert "\0section:WEB SEARCH API KEYS" in tui._choice_values
    assert (
        "\0info:OpenAI Codex login: klaude auth login openai-codex"
        in tui._choice_values
    )
    assert "Brave Search: not configured" in tui._choice_values
    assert "Parallel: not configured" in tui._choice_values
    assert "Tavily: not configured" in tui._choice_values
    assert "Exa: not configured" in tui._choice_values
    assert "\0section:HOSTED WEB FETCHING & CRAWLING" in tui._choice_values
    assert "Firecrawl: not configured" in tui._choice_values
    assert "Crawl4AI Cloud: not configured" in tui._choice_values
    assert "Hugging Face: not configured" in tui._choice_values

    tui._choice_index = tui._choice_values.index("Brave Search: not configured")
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("Add API key")
    tui._accept_choice()
    tui._set_input("brave-private-key")
    tui._submit_secret_response()

    assert saved[-1] == (
        tui.cfg.config_dir,
        "BRAVE_SEARCH_API_KEY",
        "brave-private-key",
    )
    assert tui.cfg.brave_search_api_key == "brave-private-key"
    assert "brave-private-key" not in tui.output.text
    assert tui._panel.page.rows[0].description == "Status: configured"
    assert "Remove API key" in tui._choice_values

    tui._choice_index = tui._choice_values.index("Remove API key")
    tui._accept_choice()

    assert saved[-1] == (tui.cfg.config_dir, "BRAVE_SEARCH_API_KEY", "")
    assert tui.cfg.brave_search_api_key == ""
    assert tui._panel.page.rows[0].description == "Status: not configured"
    assert "Remove API key" not in tui._choice_values
    assert tui._choice_values[tui._choice_index] == "Add API key"

    cancelled = threading.Event()
    tui._secret_request = {
        "label": "password",
        "prompt": "Enter password",
        "value": "should be replaced",
        "done": cancelled,
    }
    tui._set_input("must-not-remain-visible")
    tui._answer_secret(None)
    assert cancelled.is_set()
    assert tui.input.text == ""


def test_ollama_control_retries_through_generic_masked_secret_prompt(monkeypatch):
    tui = _fake_persistent_tui()
    finished = threading.Event()
    privileged_calls = []
    monkeypatch.setattr(tui, "_ask_permission", lambda *_args: "y")
    monkeypatch.setattr(tui, "_ask_secret", lambda *_args: "private-password")
    monkeypatch.setattr(
        "klaude_cli.main._control_ollama_service",
        lambda _action: (False, "Run `sudo systemctl restart ollama` in a normal terminal"),
    )

    def privileged(action, password):
        privileged_calls.append((action, password))
        finished.set()
        return True, "Ollama service restarted"

    monkeypatch.setattr("klaude_cli.main._control_ollama_service_with_sudo", privileged)

    tui._request_ollama_service_control("restart")

    assert finished.wait(2)
    assert privileged_calls == [("restart", "private-password")]


def test_persistent_tui_refresh_erases_and_invalidates_current_frame(monkeypatch):
    tui = _fake_persistent_tui()
    calls = []

    class FakeRenderer:
        def erase(self, *, leave_alternate_screen):
            calls.append(("erase", leave_alternate_screen))

    monkeypatch.setattr(tui.application, "renderer", FakeRenderer())
    monkeypatch.setattr(tui.application, "invalidate", lambda: calls.append(("invalidate",)))

    tui._refresh_tui()

    assert calls == [("erase", False), ("invalidate",)]


def test_picker_redraws_throttle_shared_session_polling(monkeypatch):
    tui = _fake_persistent_tui()
    calls = []
    monkeypatch.setattr(tui, "_request_session_sync", lambda: calls.append("sync"))
    tui._begin_choice("settings", tui._settings_categories(), "models")
    tui._last_picker_session_sync = time.monotonic()

    tui._before_render(None)

    assert calls == []
    tui._last_picker_session_sync = 0.0
    tui._before_render(None)
    assert calls == ["sync"]


def test_render_submits_session_snapshot_without_database_calls(monkeypatch):
    tui = _fake_persistent_tui()
    def blocked(*args, **kwargs):
        pytest.fail("SQLite must not run in render polling")
    for name in (
        "session_live_state", "session_client_states", "session_events_since",
        "update_session_client", "renew_session_lease",
    ):
        monkeypatch.setattr(tui.memory, name, blocked)
    tui._set_input("public draft")
    tui._before_render(None)
    assert tui._session_io.requests[-1].draft == "public draft"


def test_session_snapshot_never_publishes_secret_composer():
    tui = _fake_persistent_tui()
    tui._secret_request = {"prompt": "API key"}
    tui._set_input("private secret")
    assert tui._session_io_request().draft is None


def test_session_snapshot_rejects_late_previous_session_result():
    from klaude_cli.session_io import SessionIORequest, SessionIOResult

    tui = _fake_persistent_tui()
    tui._apply_session_io(
        SessionIORequest("previous", tui.client_id, "", 0),
        SessionIOResult({}, [], [], renewed=False),
    )
    assert not tui.cancel_requested.is_set()


def test_session_lease_timeout_requests_safe_interruption():
    tui = _fake_persistent_tui()
    tui.running = True
    tui._turn_id = "turn"
    tui._last_lease_renewal = time.monotonic() - 13
    tui._request_session_sync()
    assert tui.cancel_requested.is_set()
    assert "could not be renewed" in tui.status_error


def test_live_composer_accepts_input_while_session_io_is_blocked(tmp_path, monkeypatch):
    import threading

    import klaude_cli.session_io as module

    async def exercise():
        tui = _fake_persistent_tui()
        tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
        entered, release = threading.Event(), threading.Event()
        original = module.collect_session_io

        def slow(connection, request):
            entered.set()
            assert release.wait(3)
            return original(connection, request)

        monkeypatch.setattr(module, "collect_session_io", slow)
        tui._session_io = module.SessionIOCoordinator(tui.memory, tui._emit)
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                for _ in range(40):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.025)
                assert entered.is_set()
                pipe.send_text("still responsive")
                await asyncio.sleep(0.15)
                assert tui.input.text == "still responsive"
                assert tui.input.window.render_info is not None
                assert not release.is_set()
            finally:
                release.set()
                tui.application.exit()
                await task
                tui._session_io.close(wait=True)
                tui.memory.db.close()

    asyncio.run(exercise())


def test_persistent_tui_permission_response_accepts_composer_input():
    tui = _fake_persistent_tui()
    done = __import__("threading").Event()
    request = {"tool": "run_shell", "detail": "run tests", "answer": "n", "done": done}
    tui._permission_request = request
    tui._set_input("yes")

    tui._submit_permission_response()

    assert request["answer"] == "y"
    assert done.is_set()
    assert tui.input.text == ""


def test_persistent_tui_empty_permission_response_allows_once():
    tui = _fake_persistent_tui()
    done = threading.Event()
    request = {"tool": "run_shell", "detail": "run tests", "answer": "n", "done": done}
    tui._permission_request = request

    tui._submit_permission_response()

    assert request["answer"] == "y"
    assert done.is_set()
    assert tui.input.text == ""


def test_line_permission_empty_enter_allows_once(monkeypatch):
    monkeypatch.setattr("klaude_cli.main.console.print", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("klaude_cli.main.console.input", lambda *_args, **_kwargs: "")

    assert _ask_permission("learn_source", "Learn this page?") == "y"


def test_persistent_tui_permission_response_keeps_invalid_composer_input():
    tui = _fake_persistent_tui()
    done = __import__("threading").Event()
    tui._permission_request = {
        "tool": "run_shell",
        "detail": "run tests",
        "answer": "n",
        "done": done,
    }
    tui._set_input("maybe")

    tui._submit_permission_response()

    assert not done.is_set()
    assert tui.input.text == "maybe"
    assert "Type y/yes" in tui.status_error


def test_persistent_tui_choice_response_accepts_a_typed_option():
    tui = _fake_persistent_tui()
    tui._begin_choice(
        "runtime device",
        ["auto (Klaude decides)", "CPU only", "GPU preferred", "back"],
        "auto (Klaude decides)",
    )
    tui._set_input("GPU preferred")

    tui._submit_choice_response()

    assert "num_gpu" not in tui.agent.ollama_options
    assert tui._runtime_device_mode == "gpu-preferred"
    assert tui._choice_kind == "runtime settings"


def test_runtime_gpu_only_mode_requests_full_offload_and_persists(tmp_path):
    path = tmp_path / "chat-preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)
    tui._open_settings_category("runtime")
    device_row = next(value for value in tui._choice_values if value.startswith("device:"))
    tui._choice_index = tui._choice_values.index(device_row)
    tui._accept_choice()

    assert "GPU only" in tui._choice_values
    tui._set_input("GPU only")
    tui._submit_choice_response()

    saved = json.loads(path.read_text())
    assert tui.agent.ollama_options["num_gpu"] == -1
    assert saved["runtime_device_mode"] == "gpu-only"
    tui._open_settings_category("runtime")
    assert "device: GPU only" in tui._choice_values


def test_persistent_tui_choice_response_preserves_invalid_typed_option():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", ["theme", "input field"], "theme")
    tui._panel.search_active = True
    tui._set_input("unknown")
    tui._refresh_choice_filter()

    tui._submit_choice_response()

    assert tui._choice_kind == "settings"
    assert tui.input.text == "unknown"
    assert tui._panel.picker.no_matches


def test_tui_appearance_store_defaults_and_round_trips(tmp_path):
    path = tmp_path / "appearance.json"

    assert _load_tui_appearance(path) == TUIAppearance()

    appearance = TUIAppearance(
        theme="hacker-green",
        text_theme="monokai",
        input_border=False,
        input_height=12,
        input_max_height=12,
    )
    _save_tui_appearance(path, appearance)

    assert _load_tui_appearance(path) == appearance


def test_tui_appearance_reads_legacy_flat_theme_file(tmp_path):
    path = tmp_path / "appearance.json"
    path.write_text('{"theme":"hacker-green","text_theme":"monokai"}')

    assert _load_tui_appearance(path) == TUIAppearance(
        theme="hacker-green",
        text_theme="monokai",
    )


def test_last_chat_model_store_defaults_and_round_trips(tmp_path):
    path = tmp_path / "chat-preferences.json"

    assert _load_last_chat_model(path) is None

    _save_last_chat_model(path, "qwen3.5:9b")

    assert _load_last_chat_model(path) == "qwen3.5:9b"


def test_requested_codex_model_refreshes_catalog_when_cache_is_empty(monkeypatch):
    expected = ModelInfo("openai_codex", "gpt-5.5", "gpt-5.5")
    monkeypatch.setattr("klaude_cli.main._available_chat_models", lambda *_args: [])
    monkeypatch.setattr(
        "klaude_cli.main.CodexAuthManager",
        lambda: SimpleNamespace(
            status=lambda: SimpleNamespace(authenticated=True),
        ),
    )
    monkeypatch.setattr("klaude_cli.main.discover_codex_models", lambda: [expected])

    selected = _resolve_requested_chat_model(
        SimpleNamespace(openai_api_key="", gemini_api_key=""),
        SimpleNamespace(),
        "openai_codex/gpt-5.5",
    )

    assert selected == expected


def test_runtime_preferences_persist_alongside_the_last_chat_model(tmp_path):
    path = tmp_path / "chat-preferences.json"
    _save_runtime_preferences(
        path,
        {"num_gpu": -1, "num_thread": 8, "num_ctx": 16_384},
    )
    _save_last_chat_model(path, "qwen3.5:9b")

    assert _load_last_chat_model(path) == "qwen3.5:9b"
    assert _load_runtime_preferences(path) == {
        "num_gpu": -1,
        "num_thread": 8,
        "num_ctx": 16_384,
    }
    tui = _fake_persistent_tui()
    tui.agent.ollama_options.update({"num_gpu": 0, "num_thread": 1, "num_ctx": 8192})
    _apply_runtime_preferences(tui.agent, _load_runtime_preferences(path))
    assert tui.agent.ollama_options == {"num_gpu": -1, "num_thread": 8, "num_ctx": 16_384}


def test_legacy_gpu_preferred_preference_migrates_to_ollama_managed_placement(tmp_path):
    path = tmp_path / "chat-preferences.json"
    _save_runtime_preferences(path, {"num_gpu": -1, "num_ctx": 4096})
    raw = json.loads(path.read_text())
    raw["runtime_device_mode"] = "gpu-preferred"
    path.write_text(json.dumps(raw))

    preferences, mode = _migrate_runtime_device_preference(path, _load_runtime_preferences(path))

    assert mode == "gpu-preferred"
    assert preferences == {"num_gpu": None, "num_ctx": 4096}
    assert _load_runtime_preferences(path) == preferences


def test_explicit_gpu_only_preference_keeps_the_advanced_offload_override(tmp_path):
    path = tmp_path / "chat-preferences.json"
    _save_runtime_preferences(path, {"num_gpu": -1})
    raw = json.loads(path.read_text())
    raw["runtime_device_mode"] = "gpu-only"
    path.write_text(json.dumps(raw))

    preferences, mode = _migrate_runtime_device_preference(path, _load_runtime_preferences(path))

    assert mode == "gpu-only"
    assert preferences == {"num_gpu": -1}


def test_runtime_preference_auto_removes_the_saved_request(tmp_path):
    path = tmp_path / "chat-preferences.json"
    _save_runtime_preferences(path, {"num_gpu": None})
    tui = _fake_persistent_tui()
    tui.agent.ollama_options["num_gpu"] = -1

    _apply_runtime_preferences(tui.agent, _load_runtime_preferences(path))

    assert "num_gpu" not in tui.agent.ollama_options


def test_persistent_tui_theme_and_text_theme_persist_independently(tmp_path):
    path = tmp_path / "appearance.json"
    tui = _fake_persistent_tui(path)

    tui._set_input("/theme neon")
    tui._submit_buffer(steer=False)
    assert _load_tui_appearance(path).theme == "neon-synth"
    assert _load_tui_appearance(path).text_theme == DEFAULT_TEXT_THEME

    tui._set_input("/theme")
    tui._submit_buffer(steer=False)
    assert tui._choice_kind == "theme settings"
    tui._choice_index = tui._choice_values.index("text/code theme: VS Code Dark")
    tui._accept_choice()
    assert tui._choice_kind == "text theme"
    tui._choice_index = tui._choice_values.index("monokai")
    tui._accept_choice()
    assert _load_tui_appearance(path).theme == "neon-synth"
    assert _load_tui_appearance(path).text_theme == "monokai"

    tui._set_input("/theme reset")
    tui._submit_buffer(steer=False)
    assert _load_tui_appearance(path).theme == DEFAULT_TUI_THEME
    assert _load_tui_appearance(path).text_theme == "monokai"

    tui._apply_appearance_choice("text theme", "reset to default")
    assert _load_tui_appearance(path) == TUIAppearance()


def test_persistent_tui_categorized_field_settings_toggle_and_reset(tmp_path):
    path = tmp_path / "appearance.json"
    tui = _fake_persistent_tui(path)

    assert tui.appearance.input_border is DEFAULT_INPUT_BORDER
    assert tui.output.window.right_margins == []

    tui._cancel_choice()
    tui._set_input("/settings input")
    tui._submit_buffer(steer=False)
    tui._accept_choice()
    assert _load_tui_appearance(path).input_border is False

    tui._cancel_choice()
    tui._set_input("/settings reset")
    tui._submit_buffer(steer=False)
    assert _load_tui_appearance(path).input_border is False
    assert tui._choice_kind == "settings reset confirmation"
    tui._panel.picker.focus("confirm")
    tui._apply_picker_state()
    tui._accept_choice()
    assert _load_tui_appearance(path) == TUIAppearance()
    assert tui.output.window.right_margins == []


def test_tui_mcp_search_suggestions_stay_private_and_submit_only_search(monkeypatch):
    tui = _fake_persistent_tui()
    tui._mcp_catalog_results = {
        "io.example/context7": SimpleNamespace(name="io.example/context7")
    }
    tui._mcp_catalog_query = True
    tui._set_input("Context7")
    assert tui._completion_menu_position() == 0
    assert tui._session_io_request().draft is None
    assert ("io.example/context7", "loaded registry result") in tui._mcp_search_suggestions("con")
    calls = []
    monkeypatch.setattr(tui, "_search_mcp_catalog", calls.append)
    tui._submit_buffer(steer=False)
    assert calls == ["Context7"]
    assert tui.input.text == "" and tui.input.buffer.complete_state is None
    assert not tui.pending


def test_mcp_initial_search_hint_submits_registry_query(monkeypatch):
    tui = _fake_persistent_tui()
    tui._begin_mcp_catalog_query()
    state = tui.input.buffer.complete_state
    assert state is not None
    tui.input.buffer.go_to_completion(0)
    selected = tui.input.buffer.complete_state.current_completion
    assert selected is not None and selected.text == "Context7"
    tui.input.buffer.cancel_completion()
    tui._set_input(selected.text)
    assert tui._mcp_catalog_query is True and tui.input.text == "Context7"
    calls = []
    monkeypatch.setattr(tui, "_search_mcp_catalog", calls.append)
    tui._submit_buffer(steer=False)
    assert calls == ["Context7"]
    assert not tui.pending


def test_mcp_typeahead_debounces_discards_stale_results_and_cancels_on_exit():
    tui = _fake_persistent_tui()
    tui._begin_mcp_catalog_query()
    initial = tui.input.buffer.complete_state
    assert initial is not None
    assert [(item.text, item.display_meta_text) for item in initial.completions][:2] == [
        ("Context7", "suggested search"), ("GitHub", "suggested search")
    ]
    assert "mcp-suggestions" not in tui._background_jobs.latest
    tui._set_input("context")
    tui._refresh_mcp_suggestions()
    assert "mcp-suggestions" not in tui._background_jobs.latest
    tui._mcp_suggestion_due = 0
    tui._refresh_mcp_suggestions()
    identity = tui._background_jobs.latest["mcp-suggestions"]
    assert tui._background_jobs.requests["mcp-suggestions"]["query"] == "context"
    tui._apply_background_result(("mcp-suggestions", identity, {
        "servers": [{"name": "io.example/context7"}],
    }, ""))
    assert tui._mcp_search_suggestions("context")[0][0] == "io.example/context7"
    tui._set_input("github")
    tui._apply_background_result(("mcp-suggestions", identity, {
        "servers": [{"name": "stale"}],
    }, ""))
    assert "stale" not in tui._mcp_suggestion_names
    tui._mcp_catalog_query = False
    tui._refresh_mcp_suggestions()
    assert "mcp-suggestions" not in tui._background_jobs.latest


def test_tui_mcp_registry_search_installs_supported_plan_disabled(monkeypatch, tmp_path):
    from klaude_core.mcp_catalog import _parse_servers
    from klaude_core.mcp_client import MCPRegistry

    registry = MCPRegistry(tmp_path / "mcp-servers.json")
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: registry)
    server = _parse_servers(
        {
            "servers": [
                {
                    "server": {
                        "name": "io.github.example/browser",
                        "title": "Example Browser",
                        "description": "Accessible browser automation.",
                        "version": "1.2.3",
                        "remotes": [
                            {
                                "type": "streamable-http",
                                "url": "https://mcp.example.com/mcp",
                            }
                        ],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "isLatest": True,
                        }
                    },
                }
            ]
        }
    )[0]
    tui = _fake_persistent_tui()
    _configure_test_mcp_lane(tui, registry, monkeypatch)

    tui._open_settings_category("mcp servers")
    tui._choice_index = tui._choice_values.index("Search official MCP Registry")
    tui._accept_choice()

    assert tui._choice_kind == "mcp registry results"
    assert tui._panel.page.breadcrumb == ("Settings", "MCPs", "Search")
    assert any(row.id.startswith("suggest:") for row in tui._panel.page.rows)

    tui._mcp_catalog_results = {server.name: server}
    tui._open_mcp_catalog_results()
    tui._picker.focus("registry:" + server.name)
    tui._apply_picker_state()
    tui._accept_choice()
    tui._picker.focus("plan:0")
    tui._apply_picker_state()
    tui._accept_choice()
    assert registry.load() == {} and tui._choice_kind == "mcp registry detail"
    identity = tui._background_jobs.latest["mcp-inventory"]
    tui._apply_background_result(("mcp-inventory", identity, {
        "servers": [], "truncated": True,
    }, ""))
    assert tui._mcp_catalog_install_choices == {}
    tui._invalidate_mcp_inventory()
    tui._open_mcp_catalog_detail(server)
    identity = tui._background_jobs.latest["mcp-inventory"]
    tui._apply_background_result(("mcp-inventory", identity, {
        "servers": [], "truncated": False,
    }, ""))

    tui._picker.focus("plan:0")
    tui._apply_picker_state()
    tui._accept_choice()

    assert tui._mcp_mutations.close(wait=True)
    tui._before_render(None)

    installed = registry.load()["browser"]
    assert installed.enabled is False
    assert installed.url == "https://mcp.example.com/mcp"
    assert installed.source["name"] == "io.github.example/browser"


def test_tui_mcp_registry_result_event_is_runtime_safe(monkeypatch, tmp_path):
    from klaude_core.mcp_catalog import _parse_servers

    server = _parse_servers(
        {
            "servers": [
                {
                    "server": {
                        "name": "io.github.example/runtime-safe",
                        "title": "Runtime Safe",
                        "description": "A runtime-safe test server.",
                        "version": "1.0.0",
                        "remotes": [
                            {
                                "type": "streamable-http",
                                "url": "https://mcp.example.com/mcp",
                            }
                        ],
                    },
                    "_meta": {
                        "io.modelcontextprotocol.registry/official": {
                            "status": "active",
                            "isLatest": True,
                        }
                    },
                }
            ]
        }
    )[0]
    tui = _fake_persistent_tui()
    tui._mcp_catalog_request_id = "request-1"
    tui._open_mcp_catalog_results()
    tui._events.put(("mcp_catalog_results", ("request-1", [server], False, "")))

    tui._before_render(None)

    assert server.name in tui._mcp_catalog_results
    assert any(row.id == "registry:" + server.name for row in tui._panel.page.rows)


def test_tui_mcp_search_query_editor_submits_owned_job_without_chat_turn(monkeypatch):
    tui = _fake_persistent_tui()
    submitted = []
    monkeypatch.setattr(tui._background_jobs, "submit", lambda key, request, **_kwargs:
                        submitted.append((key, request)) or "owned-search")
    tui._open_settings_category("mcp servers")
    tui._choice_index = tui._choice_values.index("Search official MCP Registry")
    tui._accept_choice()
    tui._picker.focus("query")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._settings_input_request["single_line"] is True
    tui._set_input("browser automation")
    tui._submit_settings_input_response()
    assert [item for item in submitted if item[0] == "mcp-search"] == [(
        "mcp-search", {"kind": "mcp_search", "query": "browser automation",
                       "cache_file": str(tui.cfg.mcp_registry_cache_file)},
    )]
    assert tui._choice_kind == "mcp registry results"
    assert tui._mcp_catalog_request_id == "owned-search"
    assert tui._panel.row("loading") is not None
    assert tui._settings_input_request is None


def test_tui_mcp_registry_table_keeps_distinct_servers_and_detail_navigation():
    from klaude_core.mcp_catalog import MCPCatalogServer

    servers = [MCPCatalogServer(
        name=f"io.github.example/{name}", title="Shared friendly name",
        description=f"Unique {name} documentation examples", version="1.0.0", status="active",
    ) for name in ("first", "second")]
    tui = _fake_persistent_tui()
    tui._mcp_catalog_request_id = "table-request"
    tui._open_mcp_catalog_results()
    assert tui._panel.page.column_headers is None
    tui._events.put(("mcp_catalog_results", ("table-request", servers, False, "")))
    tui._before_render(None)
    assert len(tui._mcp_catalog_results) == 2
    assert tui._panel.page.column_headers == ("MCP NAME", "VERSION", "DESCRIPTION")
    tui._picker.focus("sort")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._mcp_catalog_sort == "Name A–Z"
    assert tui._picker.selected_id == "sort"
    assert [row.id for row in tui._panel.page.rows if row.id.startswith("registry:")] == [
        "registry:" + server.name for server in servers
    ]
    tui._panel.filter("Unique second")
    tui._apply_picker_state()
    assert tui._panel.row().label == servers[1].name
    assert tui._panel.row().value == "1.0.0"
    identity = tui._picker.selected_id
    tui._accept_choice()
    assert tui._choice_kind == "mcp registry detail"
    assert tui._mcp_detail_server is servers[1]
    tui._dismiss_picker()
    assert tui._choice_kind == "mcp registry results"
    assert tui._picker.selected_id == identity
    assert tui._picker.query == "unique second"


def test_tui_mcp_repository_stars_are_owned_and_preserve_result_focus(monkeypatch):
    from klaude_core.mcp_catalog import MCPCatalogServer

    server = MCPCatalogServer(
        name="io.github.example/docs", title="Docs", description="Documentation",
        version="1.0.0", status="active",
        repository_url="https://github.com/example/docs",
    )
    tui = _fake_persistent_tui()
    submitted = []
    monkeypatch.setattr(tui._background_jobs, "submit", lambda key, request, **_kw:
                        submitted.append((key, request)) or "stars-request"
                        if key == "mcp-stars" else "inventory-request")
    monkeypatch.setattr(tui._background_jobs, "current", lambda _key, _id: True)
    tui._mcp_catalog_results = {server.name: server}
    tui._open_mcp_catalog_results()
    tui._picker.focus("registry:" + server.name)
    tui._apply_picker_state()
    tui._open_mcp_catalog_detail(server)
    assert ("mcp-stars", {"kind": "mcp_repository_stars",
                            "repository_url": server.repository_url}) in submitted
    assert tui._panel.row("repository-stars").description == "Loading…"
    tui._apply_background_result(("mcp-stars", "wrong-request", {
        "repository_url": server.repository_url, "stars": 1234,
    }, ""))
    assert server.repository_url not in tui._mcp_repository_stars
    tui._apply_background_result(("mcp-stars", "stars-request", {
        "repository_url": server.repository_url, "stars": 1234,
    }, ""))
    assert tui._panel.row("repository-stars").description == "1,234"
    tui._open_mcp_catalog_results()
    assert tui._picker.selected_id == "registry:" + server.name
    assert "Repository stars: 1,234" in tui._panel.row(
        "registry:" + server.name).description


def test_tui_mcp_registry_table_live_resize_and_long_description_scrolling():
    from klaude_core.mcp_catalog import MCPCatalogServer
    from prompt_toolkit.data_structures import Size

    class SizedOutput(DummyOutput):
        columns = 120

        def get_size(self):
            return Size(rows=30, columns=self.columns)

    async def exercise():
        tui = _fake_persistent_tui()
        output = SizedOutput()
        server = MCPCatalogServer(
            "io.github.example/documentation", "Documentation",
            "Public documentation and code examples " * 12, "2026.10.2-preview.12", "active",
        )
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = output
            tui.application.renderer.output = output
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.08)
                tui._set_input("unsent draft")
                tui._begin_choice("settings", tui._settings_categories(), "mcp servers")
                tui._open_settings_category("mcp servers")
                tui._mcp_catalog_results = {server.name: server}
                tui._open_mcp_catalog_results(new_results=True)
                tui._picker.focus("registry:" + server.name)
                tui._apply_picker_state()
                for width in (120, 75, 36, 22, 120):
                    output.columns = width
                    tui.application._redraw()
                    assert tui.application.layout.current_control is tui.panel_control
                    info = tui.panel_body_window.render_info
                    assert tui._panel_selected_line() in info.displayed_lines
                    header_height = 3 if tui._panel_width() >= 60 else 2
                    assert tui.panel_header_window.render_info.window_height == header_height
                    assert tui.panel_footer_window.render_info.window_height == 2
                assert tui._picker.selected_id == "registry:" + server.name
                output.columns = 22
                tui.application._redraw()
                identity = tui._picker.selected_id
                pipe.send_text("\x1b[6~")  # PageDown
                await asyncio.sleep(0.08)
                tui.application._redraw()
                assert tui._picker.selected_id == identity
                assert tui._panel_selected_line() > tui._panel_body().selected_line
                assert tui.panel_body_window.render_info.vertical_scroll > 0
                assert tui.panel_header_window.render_info.window_height == 2
                pipe.send_text("\x1b[5~")  # PageUp
                await asyncio.sleep(0.08)
                tui.application._redraw()
                assert tui._panel_selected_line() == tui._panel_body().selected_line
                tui._dismiss_picker()
                tui._dismiss_picker()
                tui._dismiss_picker()
                assert tui._choice_kind is None
                assert tui.input.text == "unsent draft"
                assert tui.application.layout.current_control is tui.input.control
                assert not tui.application.full_screen
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_tui_registry_install_collects_required_secret_in_settings(monkeypatch, tmp_path):
    from klaude_core.mcp_catalog import MCPCatalogInput, MCPInstallPlan
    from klaude_core.mcp_client import MCPRegistry

    registry = MCPRegistry(tmp_path / "mcp-servers.json")
    saved = []
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: registry)
    monkeypatch.setattr(
        "klaude_cli.main.save_provider_secret",
        lambda config_dir, name, value: saved.append((config_dir, name, value)),
    )
    plan = MCPInstallPlan(
        label="remote",
        source_name="io.github.example/secure",
        source_version="1.0.0",
        transport="http",
        url="https://mcp.example.com/mcp",
        header_templates=(("Authorization", "Bearer {token}"),),
        inputs=(
            MCPCatalogInput(
                key="token",
                label="API token",
                secret=True,
                required=True,
            ),
        ),
    )
    tui = _fake_persistent_tui()

    tui._begin_mcp_catalog_plan(plan)
    assert tui._secret_request is not None
    tui._set_input("top-secret-token")
    tui._submit_secret_response()

    server = registry.load()["secure"]
    assert server.enabled is False
    assert server.headers == {"Authorization": "Bearer ${env:MCP_SECURE_TOKEN}"}
    assert saved[-1][1:] == ("MCP_SECURE_TOKEN", "top-secret-token")
    assert "top-secret-token" not in tui.output.text


def test_tui_custom_remote_mcp_setup_stays_inside_settings(monkeypatch, tmp_path):
    from klaude_core.mcp_client import MCPRegistry

    registry = MCPRegistry(tmp_path / "mcp-servers.json")
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: registry)
    tui = _fake_persistent_tui()
    _configure_test_mcp_lane(tui, registry, monkeypatch)

    tui._open_settings_category("mcp servers")
    tui._choice_index = tui._choice_values.index("Add custom MCP server")
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("Remote · Streamable HTTP")
    tui._accept_choice()
    tui._set_input("context-docs")
    tui._submit_settings_input_response()
    tui._set_input("https://mcp.example.com/mcp")
    tui._submit_settings_input_response()
    tui._choice_index = tui._choice_values.index("No authentication")
    tui._accept_choice()
    assert tui._mcp_mutations.close(wait=True)
    tui._before_render(None)

    server = registry.load()["context-docs"]
    assert server.url == "https://mcp.example.com/mcp"
    assert server.enabled is False
    assert tui._choice_kind == "mcp settings"


def test_picker_text_fuzzy_filters_to_closest_option():
    tui = _fake_persistent_tui()
    tui._begin_choice(
        "model cloud provider",
        ["OpenAI Codex", "OpenAI", "OpenRouter", "Google", "back"],
        "OpenAI",
    )

    tui._set_input("codx")
    tui._refresh_choice_filter()

    assert tui._choice_values[0] == "OpenAI Codex"
    assert tui._choice_index == 0


def test_persistent_tui_input_height_picker_persists_and_resets(tmp_path):
    path = tmp_path / "appearance.json"
    tui = _fake_persistent_tui(path)

    assert tui.appearance.input_height == DEFAULT_INPUT_HEIGHT
    tui._open_settings_category("input field")
    tui._move_choice(1)
    tui._accept_choice()

    assert tui._choice_kind == "input height"
    assert f"{MIN_INPUT_HEIGHT} line" in tui._choice_values
    assert f"{MAX_INPUT_HEIGHT} lines" in tui._choice_values
    tui._choice_index = tui._choice_values.index(f"{MAX_INPUT_HEIGHT} lines")
    tui._accept_choice()

    assert _load_tui_appearance(path).input_height == MAX_INPUT_HEIGHT
    assert _load_tui_appearance(path).input_max_height == MAX_INPUT_HEIGHT
    assert tui._choice_kind == "input field settings"
    tui._choice_index = next(
        index for index, value in enumerate(tui._choice_values) if value == "reset to default"
    )
    tui._accept_choice()

    assert _load_tui_appearance(path).input_height == DEFAULT_INPUT_HEIGHT
    assert _load_tui_appearance(path).input_max_height == 6


def test_trace_print_preserves_provider_brackets(monkeypatch):
    output = StringIO()
    monkeypatch.setattr(
        "klaude_cli.main.console",
        Console(file=output, force_terminal=False, width=80),
    )

    _print_trace("-> web_search [google]")

    assert "-> web_search [google]" in output.getvalue()


def test_render_suppresses_internal_tool_policy_correction(monkeypatch):
    printed = []
    turns = []

    class FakeAgent:
        def run(self, user_msg, *, scope=None):
            yield AgentEvent(
                "tool_result",
                {
                    "tool": "list_commands",
                    "result": (
                        "The command reference is unnecessary for this conversational request."
                    ),
                    "metadata": {"suppress_user_output": True},
                },
            )
            yield AgentEvent("text", {"content": "Hi! I'm Klaude."})

    class FakeMemory:
        def log_turn(self, session_id, role, content, **_kwargs):
            turns.append((session_id, role, content))

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    assistant_text = _render(FakeAgent(), FakeMemory(), "session-1", "hi")

    assert assistant_text == "Hi! I'm Klaude."
    rendered = _printed_plain(printed)
    assert "command reference is unnecessary" not in rendered
    assert turns[0] == ("session-1", "user", "hi")
    assert turns[-1] == ("session-1", "assistant", "Hi! I'm Klaude.")


def test_render_streams_code_and_logs_only_the_completed_assistant_turn(monkeypatch):
    output = StringIO()
    turns = []
    completed = "```python\nprint('ok')\n```"

    class FakeAgent:
        model = "small-coder"

        def run(self, user_msg, *, scope=None):
            yield AgentEvent("progress", {"stage": "drafting code"})
            yield AgentEvent("progress", {"stage": "drafting code"})
            yield AgentEvent("text_delta", {"content": "```python\n"})
            yield AgentEvent("progress", {"stage": "drafting code"})
            yield AgentEvent("text_delta", {"content": "print('ok')\n```"})
            yield AgentEvent(
                "text",
                {"content": completed, "metadata": {"streamed": True}},
            )

    class FakeMemory:
        def log_turn(self, session_id, role, content, **_kwargs):
            turns.append((session_id, role, content))

    monkeypatch.setattr(
        "klaude_cli.main.console",
        Console(file=output, force_terminal=False, width=80),
    )

    assistant_text = _render(FakeAgent(), FakeMemory(), "session-1", "write code")

    assert assistant_text == completed
    assert "```python\nprint('ok')\n```" in output.getvalue()
    assert output.getvalue().count("drafting code...") == 1
    assert turns == [
        ("session-1", "user", "write code"),
        ("session-1", "assistant", completed),
    ]


def test_render_shows_web_search_provider_from_structured_metadata(monkeypatch):
    printed = []
    turns = []

    class FakeAgent:
        def run(self, user_msg, *, scope=None):
            yield AgentEvent(
                "tool_start",
                {
                    "tool": "web_search",
                    "args": {"query": "AIS school Cambodia"},
                    "metadata": {
                        "provider": "ddgs",
                        "query": "AIS school Cambodia",
                        "canonical_tool": "web_search",
                    },
                },
            )
            yield AgentEvent(
                "tool_result",
                {
                    "tool": "web_search",
                    "result": "Found 1 relevant result.",
                    "metadata": {
                        "provider": "ddgs",
                        "provider_label": "ddgs",
                        "successful_providers": ["ddgs"],
                    },
                },
            )
            yield AgentEvent("text", {"content": "AIS is a school candidate."})

    class FakeMemory:
        def log_turn(self, session_id, role, content, **_kwargs):
            turns.append((session_id, role, content))

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    _render(FakeAgent(), FakeMemory(), "session-1", "AIS school Cambodia")

    rendered = _printed_plain(printed)
    assert "-> web_search [ddgs]" in rendered
    assert "-> web_search\n" not in rendered


def test_render_shows_fetch_url_provider_from_structured_metadata(monkeypatch):
    printed = []
    turns = []

    class FakeAgent:
        def run(self, user_msg, *, scope=None):
            yield AgentEvent(
                "tool_start",
                {
                    "tool": "fetch_url",
                    "args": {"url": "https://example.test/"},
                },
            )
            yield AgentEvent(
                "tool_result",
                {
                    "tool": "fetch_url",
                    "result": "# Example\n\nFetched body.",
                    "metadata": {
                        "provider": "trafilatura",
                        "provider_label": "trafilatura",
                        "successful_providers": ["trafilatura"],
                    },
                },
            )
            yield AgentEvent("text", {"content": "Fetched it."})

    class FakeMemory:
        def log_turn(self, session_id, role, content, **_kwargs):
            turns.append((session_id, role, content))

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    _render(FakeAgent(), FakeMemory(), "session-1", "fetch https://example.test/")

    rendered = _printed_plain(printed)
    assert "-> fetch_url [trafilatura]" in rendered
    assert "-> fetch_url\n" not in rendered


def test_natural_language_command_reference_uses_direct_renderer(monkeypatch):
    printed = []
    turns = []

    class FakeAgent:
        def __init__(self):
            self.messages = []

    class FakeConsole:
        width = 100

        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    class FakeMemory:
        def log_turn(self, session_id, role, content, **_kwargs):
            turns.append((session_id, role, content))

    monkeypatch.setattr("klaude_cli.main.console", FakeConsole())
    agent = FakeAgent()
    memory = FakeMemory()

    handled = _handle_command_reference_request(
        "what commands can I use",
        agent,
        memory,
        "session-1",
    )

    assert handled is True
    assert isinstance(printed[0][0][0], Text)
    assert printed[0][0][0].plain == "-> command_reference [local]"
    rendered = printed[1][0][0]
    assert isinstance(rendered, Text)
    assert "\nCLI COMMANDS\n  chat" in rendered.plain
    assert "\nDOCS COMMANDS\n" in rendered.plain
    assert "\nCHAT COMMANDS\n" in rendered.plain
    assert not rendered.plain.endswith("These commands allow you to")
    assert turns[0] == ("session-1", "user", "what commands can I use")
    assert turns[-1][1] == "assistant"
    assert turns[-1][2] == _command_reference_context()
    assert agent.messages[-1]["content"] == _command_reference_context()
    assert rendered.plain not in agent.messages[-1]["content"]


def test_slash_command_reference_requests_use_same_canonical_source(monkeypatch):
    printed = []

    class FakeConsole:
        width = 100

        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    monkeypatch.setattr("klaude_cli.main.console", FakeConsole())

    assert _handle_command_reference_request("/help") is True
    assert isinstance(printed[0][0][0], Text)
    assert printed[0][0][0].plain == "-> command_reference [local]"
    assert printed[1][0][0].plain == format_command_reference(width=100)


def test_non_command_casual_requests_do_not_render_reference():
    assert _handle_command_reference_request("who are you") is False
    assert _handle_command_reference_request("what can you do") is False


def test_focused_search_command_request_uses_concise_renderer(monkeypatch):
    printed = []

    class FakeConsole:
        width = 80

        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    monkeypatch.setattr("klaude_cli.main.console", FakeConsole())

    handled = _handle_command_reference_request("what command searches the web")

    assert handled is True
    assert printed[0][0][0].plain == (
        "klaude search QUERY\n    Web search via the configured provider."
    )
    assert "CLI COMMANDS" not in printed[0][0][0].plain


def test_list_commands_result_is_structured_for_direct_rendering():
    result = _command_reference_result(width=100)

    assert result["content"] == format_command_reference(width=100)
    assert result["metadata"]["content_type"] == "command_reference"
    assert result["metadata"]["preserve_whitespace"] is True
    assert result["metadata"]["direct_render"] is True
    assert result["metadata"]["source"] == "canonical_command_registry"
    assert result["metadata"]["command_usages"] == tuple(
        spec.usage for spec in iter_command_specs()
    )


def test_unknown_slash_command_is_intercepted_before_model(monkeypatch):
    printed = []
    turns = []

    class FakeAgent:
        def __init__(self):
            self.messages = []

    class FakeMemory:
        def log_turn(self, session_id, role, content, **_kwargs):
            turns.append((session_id, role, content))

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    handled = _handle_unknown_slash_command(
        "/reload",
        agent=FakeAgent(),
        memory=FakeMemory(),
        session_id="session-1",
    )

    assert handled is True
    assert printed[0][0][0].plain == (
        "Unknown chat command: /reload\nType /help to see the available commands."
    )
    assert turns[-1] == (
        "session-1",
        "assistant",
        "Unknown chat command: /reload\nType /help to see the available commands.",
    )


def test_unknown_slash_typo_suggests_registered_command(monkeypatch):
    printed = []

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    assert _handle_unknown_slash_command("/modle") is True
    assert printed[0][0][0].plain == (
        "Unknown chat command: /modle\n"
        "Did you mean /mode?\n"
        "Type /help to see the available commands."
    )


def test_direct_command_reference_does_not_create_durable_memory(tmp_path, monkeypatch):
    printed = []

    class FakeAgent:
        def __init__(self):
            self.messages = []

    class FakeConsole:
        width = 100

        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    monkeypatch.setattr("klaude_cli.main.console", FakeConsole())
    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")

    assert _handle_command_reference_request(
        "what commans can i uss",
        FakeAgent(),
        memory,
        "session-1",
    )

    assert memory.facts() == ""


def test_followup_command_question_after_direct_reference_uses_registry(monkeypatch):
    printed = []

    class FakeAgent:
        def __init__(self):
            self.messages = []

    class FakeConsole:
        width = 100

        def print(self, *args, **kwargs):
            printed.append((args, kwargs))

    monkeypatch.setattr("klaude_cli.main.console", FakeConsole())
    agent = FakeAgent()

    assert _handle_command_reference_request("what commans can i uss", agent)
    assert _handle_command_reference_request(
        "these are the commands? what does /model do?",
        agent,
    )

    assert printed[1][0][0].plain == format_command_reference(width=100)
    focused = printed[2][0][0].plain
    assert "Yes. `/model` manages the active chat model." in focused
    assert "/model\n    Open the model picker, then choose Standard or Thinking mode." in focused
    assert "/model NAME\n    Select an available Cloud or Local model" in focused
    assert agent.messages[1]["content"] == _command_reference_context()
    assert agent.messages[-1]["content"] == focused


def test_tool_selector_exposes_list_commands_when_asked():
    tool = Tool(
        "list_commands",
        "Show commands.",
        {"type": "object", "properties": {}, "required": []},
        lambda: "",
    )

    selected = _select_tool_names("show me all slash commands", {"list_commands": tool})

    assert selected == ["list_commands"]


def test_tool_selector_routes_explicit_delegation_without_mutation_tools():
    tools = {
        name: Tool(name, name, {"type": "object"}, lambda **_kwargs: "")
        for name in (
            "delegate_task",
            "read_file",
            "list_dir",
            "grep",
            "workspace_info",
            "write_file",
            "run_shell",
            "git_commit",
        )
    }

    selected = _select_tool_names(
        "Use a subagent for an independent review of the parser",
        tools,
    )

    assert selected == [
        "delegate_task",
        "read_file",
        "list_dir",
        "grep",
        "workspace_info",
    ]
    assert not {"write_file", "run_shell", "git_commit"}.intersection(selected)


def test_delegate_preflight_rejects_unsafe_child_tool_requests():
    with pytest.raises(ValueError, match="cannot request"):
        _delegate_task_preflight(
            {
                "objective": "Run the tests",
                "role": "test_diagnostic",
                "requested_tools": ["run_shell"],
            }
        )

    with pytest.raises(ValueError, match="cannot request"):
        _delegate_task_preflight(
            {
                "objective": "Inspect routing",
                "additional_tasks": [
                    {"objective": "Change it", "requested_tools": ["edit_file"]}
                ],
            }
        )


def test_delegate_result_passes_host_cancellation_and_event_observer(monkeypatch):
    cancel = threading.Event()
    observed = []
    agent = SimpleNamespace(
        cancellation_check=cancel.is_set,
        subagent_event_observer=observed.append,
    )
    captured = {}

    def supervise(parent, tasks, **kwargs):
        captured.update({"parent": parent, "tasks": tasks, **kwargs})
        task = tasks[0]
        return [
            SubagentResult(
                task_id=task.task_id,
                role=task.role,
                status=SubagentStatus.COMPLETED,
                summary="Found the routing boundary.",
                callable_tools=("read_file",),
                tools_used=("read_file",),
                model_steps=2,
                tool_calls=1,
            )
        ]

    monkeypatch.setattr("klaude_cli.main.supervise_agent_tasks", supervise)

    result = _delegate_task_result(
        agent,
        "Inspect routing",
        requested_tools=["read_file"],
    )

    assert result["content"] == "Found the routing boundary."
    assert result["metadata"]["status"] == "completed"
    assert captured["parent"] is agent
    assert captured["cancelled"] is agent.cancellation_check
    assert captured["event_sink"] is agent.subagent_event_observer


def test_delegate_result_batches_independent_cloud_tasks_in_input_order(monkeypatch):
    agent = SimpleNamespace(
        cancellation_check=lambda: False,
        subagent_event_observer=None,
        model_info=ModelInfo("openai_codex", "gpt-test", "GPT Test"),
    )
    captured = {}

    def supervise(_parent, tasks, **kwargs):
        captured.update({"tasks": tasks, **kwargs})
        return [
            SubagentResult(
                task_id=task.task_id,
                role=task.role,
                status=SubagentStatus.COMPLETED,
                summary=f"result {index}",
                callable_tools=("read_file",),
                tools_used=("read_file",),
                model_steps=1,
                tool_calls=1,
                input_tokens=10,
                output_tokens=5,
            )
            for index, task in enumerate(tasks, start=1)
        ]

    monkeypatch.setattr("klaude_cli.main.supervise_agent_tasks", supervise)

    result = _delegate_task_result(
        agent,
        "Inspect parser",
        requested_tools=["read_file"],
        additional_tasks=[
            {
                "objective": "Inspect tests",
                "role": "test_diagnostic",
                "requested_tools": ["read_file"],
            }
        ],
    )

    assert [task.objective for task in captured["tasks"]] == [
        "Inspect parser",
        "Inspect tests",
    ]
    assert captured["budget"].max_children == 2
    assert captured["budget"].max_concurrency == 2
    assert result["content"].startswith("Task 1 (read_research):\nresult 1")
    assert "Task 2 (test_diagnostic):\nresult 2" in result["content"]
    assert result["metadata"]["status"] == "completed"
    assert result["metadata"]["task_count"] == 2
    assert result["metadata"]["model_steps"] == 2


def test_parent_agent_executes_one_isolated_delegation_and_accounts_for_it():
    class NestedRuntime:
        def __init__(self):
            self.responses = [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "delegate_task",
                                "arguments": {
                                    "objective": "Inspect parser routing",
                                    "requested_tools": ["read_file"],
                                },
                            }
                        }
                    ],
                },
                {"role": "assistant", "content": "Child found parser.py."},
                {"role": "assistant", "content": "The parser route is in parser.py."},
            ]
            self.calls = []

        def chat(self, model, messages, tools=None, options=None, think=None):
            self.calls.append({"messages": messages, "tools": tools})
            return self.responses.pop(0)

        def fork_for_child(self):
            child = object.__new__(type(self))
            child.responses = self.responses
            child.calls = self.calls
            return child

    runtime = NestedRuntime()
    agent_ref = {}
    tools = [
        Tool(
            "read_file",
            "Read file",
            {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            lambda path: f"contents of {path}",
        ),
        Tool(
            "delegate_task",
            "Delegate safely",
            {
                "type": "object",
                "properties": {
                    "objective": {"type": "string"},
                    "requested_tools": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["objective"],
            },
            lambda objective, requested_tools=None: _delegate_task_result(
                agent_ref["agent"],
                objective,
                requested_tools=requested_tools,
            ),
        ),
    ]
    agent = Agent(
        runtime,
        "test-model",
        tools,
        PermissionGate({"read_file": "allow", "delegate_task": "allow"}, lambda *_args: "n"),
        "system",
        tool_selector=lambda _message, available: list(available),
    )
    agent_ref["agent"] = agent

    events = list(agent.run("Use a subagent to inspect parser routing"))

    assert [event.payload.get("content") for event in events if event.kind == "text"] == [
        "The parser route is in parser.py."
    ]
    delegated = [
        event
        for event in events
        if event.kind == "tool_result" and event.payload.get("tool") == "delegate_task"
    ]
    assert len(delegated) == 1
    assert delegated[0].payload["metadata"]["status"] == "completed"
    assert delegated[0].payload["result"] == "Child found parser.py."
    assert len(runtime.calls) == 3
    assert agent.last_turn_budget["model_steps_used"] == 3
    assert agent.last_turn_budget["tool_calls_used"] == 1


def test_tool_selector_does_not_use_commands_for_identity_questions():
    tool = Tool(
        "list_commands",
        "Show commands.",
        {"type": "object", "properties": {}, "required": []},
        lambda: "",
    )

    selected = _select_tool_names(
        "who might you be and what are all the things you can do?",
        {"list_commands": tool},
    )

    assert selected == []


def test_tool_selector_direct_response_requests_do_not_call_tools():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("list_commands", "web_search", "workspace_info")
    }

    for message in (
        "hi",
        "hello",
        "hellooo",
        "whaaa",
        "who are you",
        "hi, who might you be",
        "introduce yourself",
        "what can you do",
    ):
        assert _select_tool_names(message, tools) == []


def test_tool_selector_respects_negated_actions_and_preserves_positive_followups():
    tools = {
        name: Tool(name, name, {}, lambda: "")
        for name in (
            "workspace_info",
            "list_dir",
            "read_file",
            "write_file",
            "edit_file",
            "run_shell",
            "storage_usage",
        )
    }

    assert _select_tool_names(
        "Explain why tests matter. Do not inspect the workspace or use tools.", tools
    ) == []
    selected = _select_tool_names(
        "Run them and summarize the evidence. Do not modify anything.", tools
    )
    assert "run_shell" in selected
    assert "write_file" not in selected
    assert "edit_file" not in selected


def test_tool_selector_uses_command_registry_for_named_slash_command_help():
    tool = Tool(
        "list_commands",
        "Show commands.",
        {"type": "object", "properties": {}, "required": []},
        lambda: "",
    )

    assert _select_tool_names("what does /init do in Klaude?", {"list_commands": tool}) == [
        "list_commands"
    ]


def test_tool_selector_does_not_treat_text_reader_as_image_vision():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("list_dir", "read_file", "workspace_info")
    }

    assert _select_tool_names(
        "look at the image I placed in the current directory", tools
    ) == ["list_dir", "workspace_info"]


def test_list_commands_is_allowed_by_default():
    assert DEFAULT_PERMISSIONS["list_commands"] == "allow"
    assert DEFAULT_PERMISSIONS["current_time"] == "allow"
    assert DEFAULT_PERMISSIONS["weather_lookup"] == "allow"
    assert DEFAULT_PERMISSIONS["workspace_info"] == "allow"
    assert DEFAULT_PERMISSIONS["http_probe"] == "allow"
    assert DEFAULT_PERMISSIONS["learn_source"] == "ask"


def test_list_commands_description_excludes_casual_identity_questions():
    description = LIST_COMMANDS_TOOL_DESCRIPTION

    assert "canonical public CLI and chat command reference" in description
    assert "available commands" in description
    assert "Never invent commands" in description
    assert "focused command help" in description


@pytest.mark.parametrize(
    "message",
    [
        "Learn this source: https://obsidian.md/help/",
        "Learn and save this documentation https://obsidian.md/help/",
        "Save https://obsidian.md/help/ into my Obsidian knowledge library",
        "Index this documentation site in the obsidian library",
        "Please ingest the page into knowledge",
        "learn context7 skill",
        "learn from Context7",
        "download the Context7 skill",
        "install the official React documentation skill",
    ],
)
def test_knowledge_ingestion_intent_requires_explicit_persistence_language(message):
    assert _knowledge_ingestion_intent(message)


@pytest.mark.parametrize(
    "message",
    [
        "I want to learn about retrieval augmented generation",
        "Read https://obsidian.md/help/ for this answer",
        "What does the Obsidian documentation say?",
        "Remember that I use Obsidian",
        "Learn from this answer and explain it back to me",
        "Implement CSV import using only the standard library",
        "Add a CSV import command. Update README documentation and use the standard library.",
        "Implement CSV stock adjustments. Save stock atomically. Use only the standard library.",
    ],
)
def test_knowledge_ingestion_intent_rejects_temporary_or_personal_memory_requests(message):
    assert not _knowledge_ingestion_intent(message)


def test_tool_selector_routes_explicit_learning_only_to_persistent_ingestion():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in (
            "learn_source",
            "query_knowledge",
            "web_search",
            "fetch_url",
            "crawl_site",
            "write_file",
            "run_shell",
        )
    }

    assert _select_tool_names(
        "Learn and keep this documentation: https://obsidian.md/help/", tools
    ) == ["learn_source"]


def test_tool_selector_preserves_an_explicit_crawl_site_request_with_a_url():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("learn_source", "crawl_site", "web_search", "fetch_url")
    }
    request = (
        "Test the built-in `crawl_site` capability. Crawl this page and store it "
        "in the test library: https://docs.python.org/3/library/unittest.html"
    )

    assert _select_tool_names(request, tools) == ["crawl_site"]
    assert _select_tool_names(
        "Do not use crawl_site; learn and keep this documentation: "
        "https://docs.python.org/3/library/unittest.html",
        tools,
    ) == ["learn_source"]
    assert _select_tool_names(
        request,
        {name: tool for name, tool in tools.items() if name != "crawl_site"},
    ) == []


def test_tool_selector_discovers_named_learning_source_before_ingestion():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in (
            "learn_source",
            "query_knowledge",
            "web_search",
            "fetch_url",
            "request_user_input",
            "write_file",
            "run_shell",
            "git_commit",
        )
    }

    assert _select_tool_names("learn context7 skill", tools) == [
        "web_search",
        "fetch_url",
        "learn_source",
        "request_user_input",
    ]


def test_inferred_knowledge_library_prefers_explicit_name_then_domain():
    assert _inferred_knowledge_library("https://docs.python.org/3/", "Python 3") == "Python 3"
    assert _inferred_knowledge_library("https://docs.python.org/3/") == "python"
    assert _inferred_knowledge_library("https://obsidian.md/help/") == "obsidian"


def test_learn_source_preflight_rejects_invalid_scope_credentials_and_bounds():
    with pytest.raises(ValueError, match="HTTP"):
        _learn_source_preflight({"url": "file:///tmp/private", "scope": "page"})
    with pytest.raises(ValueError, match="credentials"):
        _learn_source_preflight({"url": "https://user:secret@example.com", "scope": "page"})
    with pytest.raises(ValueError, match="scope"):
        _learn_source_preflight({"url": "https://example.com", "scope": "domain"})
    with pytest.raises(ValueError, match="max_pages"):
        _learn_source_preflight(
            {"url": "https://example.com", "scope": "site", "max_pages": 501}
        )


def test_learn_source_permission_detail_shows_persistent_scope_and_inferred_library():
    detail = _learn_source_permission_detail(
        {"url": "https://obsidian.md/help/", "scope": "site"}
    )

    assert detail == (
        "Learn documentation site https://obsidian.md/help/ into the local knowledge "
        "library 'obsidian'?"
    )


def test_learn_source_page_fetches_and_indexes_canonical_content():
    class FakeWeb:
        def fetch_detailed(self, url):
            assert url == "https://example.com/docs/start"
            return {
                "status": "succeeded",
                "content": "# Start\n" + ("Useful documentation. " * 20),
                "final_url": "https://example.com/docs/start/",
                "title": "Start",
                "provider_label": "direct",
            }

    class FakeKnowledge:
        def __init__(self):
            self.learned = []

        def source_is_current(self, library, text, source):
            return False

        def learn_text(self, library, text, source, title=""):
            self.learned.append((library, text, source, title))
            return 3

    knowledge = FakeKnowledge()

    result = _learn_source_tool_result(
        object(),
        FakeWeb(),
        knowledge,
        "https://example.com/docs/start",
    )

    assert result["metadata"] == {
        "canonical_tool": "learn_source",
        "status": "learned",
        "scope": "page",
        "library": "example",
        "url": "https://example.com/docs/start/",
        "title": "Start",
        "pages": 1,
        "chunks": 3,
        "provider": "direct",
    }
    assert knowledge.learned[0][0::2] == (
        "example",
        "https://example.com/docs/start/",
    )


def test_learn_source_page_reports_unchanged_without_reindexing():
    class FakeWeb:
        def fetch_detailed(self, _url):
            return {
                "status": "succeeded",
                "content": "existing content",
                "canonical_url": "https://example.com/docs",
            }

    class FakeKnowledge:
        def source_is_current(self, _library, _text, _source):
            return True

        def learn_text(self, *_args, **_kwargs):
            raise AssertionError("unchanged source must not be reindexed")

    result = _learn_source_tool_result(
        object(), FakeWeb(), FakeKnowledge(), "https://example.com/docs"
    )

    assert result["metadata"]["status"] == "unchanged"
    assert result["metadata"]["chunks"] == 0
    assert result["content"].startswith("source unchanged")


def test_learn_source_page_reports_fetch_failure_without_indexing():
    class FakeWeb:
        def fetch_detailed(self, _url):
            return {
                "status": "failed",
                "content": "",
                "failure": {"reason": "robots policy denied the request"},
            }

    class FakeKnowledge:
        def source_is_current(self, *_args, **_kwargs):
            raise AssertionError("failed fetch must not inspect the index")

        def learn_text(self, *_args, **_kwargs):
            raise AssertionError("failed fetch must not be indexed")

    result = _learn_source_tool_result(
        object(), FakeWeb(), FakeKnowledge(), "https://example.com/private"
    )

    assert result["metadata"]["status"] == "failed"
    assert result["metadata"]["pages"] == 0
    assert result["metadata"]["chunks"] == 0
    assert "robots policy denied" in result["content"]


def test_learn_source_site_defaults_to_the_supplied_documentation_subtree(monkeypatch):
    captured = {}

    def fake_crawl(cfg, url, library, **kwargs):
        captured.update(cfg=cfg, url=url, library=library, **kwargs)
        return (
            SimpleNamespace(library=library, manifest_path=Path("/data/manifest.json")),
            12,
            {"pages": [{"url": url}], "errors": [], "skipped": [], "seeded": []},
        )

    monkeypatch.setattr("klaude_cli.main._crawl_and_install", fake_crawl)

    result = _learn_source_tool_result(
        "cfg",
        object(),
        object(),
        "https://obsidian.md/help/",
        scope="site",
    )

    assert captured["library"] == "obsidian"
    assert captured["include_patterns"] == ["/help", "/help/*"]
    assert captured["use_sitemap"] is True
    assert result["metadata"]["status"] == "learned"
    assert result["metadata"]["pages"] == 1
    assert result["metadata"]["chunks"] == 12


def test_tool_selector_exposes_knowledge_for_local_knowledge_questions():
    tool = Tool(
        "query_knowledge",
        "Search local knowledge.",
        {"type": "object", "properties": {}, "required": []},
        lambda: "",
    )

    selected = _select_tool_names("do you have local knowledge of C++?", {"query_knowledge": tool})

    assert selected == ["query_knowledge"]


def test_tool_selector_exposes_web_for_general_fact_questions():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("search_sessions", "query_knowledge", "web_search")
    }

    selected = _select_tool_names("where is Dieng?", tools)

    assert selected == ["search_sessions", "query_knowledge", "web_search"]


def test_tool_selector_exposes_workspace_info_for_where_am_i():
    tools = {
        "workspace_info": Tool(
            "workspace_info",
            "Show workspace.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        ),
        "web_search": Tool(
            "web_search",
            "Search web.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        ),
    }

    selected = _select_tool_names("where am I?", tools)

    assert selected == ["workspace_info"]


def test_tool_selector_preserves_workspace_and_search_routing():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("workspace_info", "web_search", "fetch_url")
    }

    assert _select_tool_names("where am I currently", tools) == ["workspace_info"]
    assert _select_tool_names("search for AIS school in Cambodia", tools) == [
        "web_search",
        "fetch_url",
    ]
    assert _select_tool_names("hi, what is AIS", tools) == [
        "web_search",
        "fetch_url",
    ]


def test_tool_selector_routes_explicit_workspace_inspection_to_read_only_tools():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("workspace_info", "list_dir", "read_file", "run_shell")
    }

    selected = _select_tool_names(
        "Inspect this workspace read-only and identify its primary implementation language.",
        tools,
    )

    assert "workspace_info" in selected
    assert "read_file" in selected
    assert "list_dir" in selected
    assert "run_shell" not in selected


def test_tool_selector_exposes_web_for_lookup_without_question_mark():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("search_sessions", "query_knowledge", "web_search", "list_commands")
    }

    selected = _select_tool_names("who is FlazeSlayer", tools)

    assert selected == ["search_sessions", "query_knowledge", "web_search"]


def test_tool_selector_exposes_retrieval_for_unfamiliar_standalone_name():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("search_sessions", "query_knowledge", "web_search")
    }

    selected = _select_tool_names("chansovisoth", tools)

    assert selected == ["search_sessions", "query_knowledge", "web_search"]


def test_tool_selector_keeps_search_registered_for_local_entity_followup():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("search_sessions", "query_knowledge", "web_search", "fetch_url")
    }

    first = _select_tool_names("what is AIS", tools)
    second = _select_tool_names("AIS school in cambodia", tools)

    assert "web_search" in first
    assert "web_search" in second


def test_tool_selector_exposes_web_for_followup_lookup():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("query_knowledge", "web_search", "fetch_url")
    }

    selected = _select_tool_names("more about them", tools)

    assert selected == ["query_knowledge", "web_search", "fetch_url"]


def test_tool_selector_exposes_web_for_claim_verification_followup():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("query_knowledge", "web_search", "fetch_url")
    }

    selected = _select_tool_names("how long has it been operating?", tools)

    assert selected == ["query_knowledge", "web_search", "fetch_url"]


def test_tool_selector_exposes_web_for_department_leadership_followup():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("query_knowledge", "web_search", "fetch_url")
    }

    selected = _select_tool_names("head of CS department?", tools)

    assert selected == ["query_knowledge", "web_search", "fetch_url"]


@pytest.mark.skip(
    reason="superseded: retrieval is initiated by model tool calls, not chat-selector synthesis"
)
def test_chat_selector_searches_resolved_university_duration_followup():
    queries = []
    fetched_urls = []

    class FakeOllama:
        def chat(self, model, messages, tools=None):
            return {"role": "assistant", "content": "answer"}

    def web_search(query):
        queries.append(query)
        if "university" not in query.lower():
            return {
                "content": "Found Paragon Indiana.",
                "metadata": {
                    "search_results": [
                        {
                            "title": "Paragon, Indiana",
                            "url": "https://en.wikipedia.org/wiki/Paragon,_Indiana",
                            "snippet": "Paragon is a town in Indiana.",
                        }
                    ],
                    "provider_metadata": {"entity_candidates": []},
                },
            }
        return {
            "content": "Found Paragon International University.",
            "metadata": {
                "search_results": [
                    {
                        "title": "Home - Paragon International University",
                        "url": "https://www.paragoniu.edu.kh/",
                        "snippet": (
                            "Paragon International University is among the top "
                            "universities in Cambodia."
                        ),
                    }
                ],
                "provider_metadata": {
                    "entity_candidates": [
                        {
                            "canonical_name": "Paragon International University",
                            "aliases": [
                                "Paragon",
                                "Paragon International University",
                                "PIU",
                            ],
                            "entity_type": "university",
                            "country": "Cambodia",
                            "domains": ["paragoniu.edu.kh"],
                            "score": 0.92,
                        }
                    ]
                },
            },
        }

    def fetch_url(url):
        fetched_urls.append(url)
        return {
            "content": (
                "Paragon International University is among the top universities in Cambodia."
            ),
            "metadata": {},
        }

    tools = [
        Tool(
            "web_search",
            "Search the web.",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            web_search,
        ),
        Tool(
            "fetch_url",
            "Fetch a page.",
            {"type": "object", "properties": {"url": {"type": "string"}}},
            fetch_url,
        ),
    ]
    system_prompt = (
        '<runtime_context machine_generated="true">\n'
        "- Timezone: Asia/Phnom_Penh\n"
        "- Approximate country: Cambodia\n"
        "</runtime_context>"
    )
    agent = Agent(
        FakeOllama(),
        "fake-model",
        tools,
        PermissionGate(
            {"web_search": "allow", "fetch_url": "allow"},
            lambda tool, detail: "y",
        ),
        system_prompt,
        tool_selector=_select_tool_names,
    )

    list(agent.run("where is Paragon"))
    list(agent.run("i meant a university here"))
    list(agent.run("how long has it been operating?"))

    assert queries == [
        "where is Paragon",
        "Paragon university Cambodia",
        "When was Paragon International University in Cambodia established?",
    ]
    assert all("Indiana university" not in query for query in queries)
    assert fetched_urls == []


def test_tool_selector_exposes_web_for_requested_result_list():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("web_search", "fetch_url")
    }

    selected = _select_tool_names("show me 20 results about FlazeSlayer", tools)

    assert selected == ["web_search", "fetch_url"]


def test_tool_selector_exposes_restricted_probe_for_endpoint_diagnostics():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("web_search", "fetch_url", "http_probe", "run_shell")
    }

    selected = _select_tool_names("Is this endpoint reachable?", tools)

    assert "http_probe" in selected
    assert "run_shell" not in selected


def test_http_probe_tool_result_and_display_use_structured_metadata():
    class FakeWeb:
        def probe_detailed(self, url, method):
            return {
                "requested_url": url,
                "final_url": "https://example.com/health",
                "method": method,
                "status": "succeeded",
                "reachable": True,
                "status_code": 204,
                "ok": True,
                "content_type": "text/plain",
                "content_length": 0,
                "redirect_count": 1,
                "elapsed_ms": 12,
            }

    result = _http_probe_tool_result(FakeWeb(), "http://example.com/health", "GET")
    lines = _http_probe_display_lines(result["metadata"], result["content"])

    assert HTTP_PROBE_TOOL_DESCRIPTION
    assert "Status: 204" in result["content"]
    assert result["metadata"]["canonical_tool"] == "http_probe"
    assert lines[0] == "-> http_probe [204]"


def test_tool_selector_exposes_web_for_activity_evidence_question():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("query_knowledge", "web_search", "fetch_url")
    }

    selected = _select_tool_names("do they play minecraft", tools)

    assert selected == ["query_knowledge", "web_search", "fetch_url"]


def test_format_web_results_numbers_evidence():
    results = [
        {
            "title": "FlazeSlayer - YouTube",
            "url": "https://www.youtube.com/@Flazeslayer/search",
            "snippet": "I am Flaze.",
        },
        {
            "title": "flaze_slayer - Twitch",
            "url": "https://www.twitch.tv/flaze_slayer",
            "snippet": "Gaming streams.",
        },
    ]

    formatted = _format_web_results(results)

    assert formatted.startswith("[search_result_001] FlazeSlayer - YouTube")
    assert "[search_result_002] flaze_slayer - Twitch" in formatted


def test_format_web_results_reports_when_fewer_than_requested():
    formatted = _format_web_results(
        [
            {
                "title": "FlazeSlayer - YouTube",
                "url": "https://www.youtube.com/@Flazeslayer/search",
                "snippet": "I am Flaze.",
            }
        ],
        requested=20,
    )

    assert formatted.startswith("Found 1 relevant results (requested 20).")


def test_format_search_response_includes_ambiguity_summary_without_precise_location():
    class FakeResponse:
        results = [
            {
                "title": "American Intercon School (AIS)",
                "url": "https://americanintercon.edu.kh/about",
                "snippet": "American Intercon School is a Cambodian school.",
            }
        ]
        warnings = []
        provider_metadata = {
            "ambiguity": {
                "ambiguity_detected": True,
                "location_mode": "bias",
                "location_country": "Cambodia",
                "is_ambiguous": True,
            },
            "entity_candidates": [
                {
                    "canonical_name": "American Intercon School",
                    "aliases": ["AIS"],
                    "description": "a Cambodian school",
                },
                {
                    "canonical_name": "Automatic Identification System",
                    "aliases": ["AIS"],
                    "description": "a maritime vessel tracking system",
                },
            ],
        }

    formatted = _format_search_response(FakeResponse(), requested=5)

    assert '"AIS" can refer to several things.' in formatted
    assert "Based on the approximate Cambodia context" in formatted
    assert "American Intercon School" in formatted
    assert "Automatic Identification System" in formatted
    assert "physically in" not in formatted


def test_format_search_response_does_not_overstate_inferred_location_mismatch():
    class FakeResponse:
        results = [
            {
                "title": "Advanced Info Service",
                "url": "https://www.ais.th/",
                "snippet": "Advanced Info Service is a Thai mobile network operator.",
            }
        ]
        warnings = []
        provider_metadata = {
            "ambiguity": {
                "ambiguity_detected": True,
                "location_mode": "bias",
                "location_country": "Cambodia",
                "is_ambiguous": True,
            },
            "entity_candidates": [
                {
                    "canonical_name": "Advanced Info Service",
                    "aliases": ["AIS"],
                    "description": "a Thai telecommunications company",
                    "country": "Thailand",
                },
                {
                    "canonical_name": "Automatic Identification System",
                    "aliases": ["AIS"],
                    "description": "a maritime vessel tracking system",
                },
            ],
        }

    formatted = _format_search_response(FakeResponse(), requested=5)

    assert "I did not identify a clearly Cambodia-specific candidate" in formatted
    assert "The top retrieved candidate is Advanced Info Service" in formatted
    assert "Based on the approximate Cambodia context" not in formatted


def test_tool_capabilities_context_marks_web_search_available():
    text = _append_tool_capabilities("runtime", web_search_available=True)

    assert "web_search_available: true" in text


def test_web_search_display_lines_show_exa_provider_label():
    lines = _web_search_display_lines(
        {
            "provider": "exa",
            "provider_label": "exa",
            "successful_providers": ["exa"],
            "attempted_providers": ["exa"],
            "search_results": [
                {
                    "title": "American Intercon School",
                    "url": "https://ais.edu.kh/",
                    "snippet": "American Intercon School Cambodia.",
                    "provider": "exa",
                }
            ],
            "display_lines": ["Query: American Intercon School Cambodia"],
        },
        "Found 1 relevant result.",
    )

    assert lines[0] == "-> web_search [exa]"
    assert lines[1] == "   Query: American Intercon School Cambodia"


def test_bounded_result_count_limits_search_requests():
    assert _bounded_result_count("20") == 20
    assert _bounded_result_count("999") == 50
    assert _bounded_result_count("oops", 12) == 12


def test_capability_question_does_not_fall_through_to_web_lookup():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("search_sessions", "query_knowledge", "web_search", "list_commands")
    }

    selected = _select_tool_names("who might you be?", tools)

    assert selected == []


def test_tool_selector_keeps_command_help_explicit():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("list_commands", "query_knowledge", "web_search")
    }

    assert _select_tool_names("what commands are available", tools) == ["list_commands"]
    assert _select_tool_names("show commands", tools) == ["list_commands"]
    assert _select_tool_names("/help", tools) == ["list_commands"]
    assert _select_tool_names("how do I use the docs command", tools) == ["list_commands"]


def test_tool_selector_exposes_time_and_weather_tools():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("current_time", "weather_lookup", "web_search")
    }

    selected = _select_tool_names(
        "what day is today in Cambodia and how is the weather forecast?",
        tools,
    )

    assert selected == ["current_time", "weather_lookup", "web_search"]


def test_feature_questions_use_knowledge_not_command_help():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("list_commands", "query_knowledge", "code_search", "web_search")
    }

    selected = _select_tool_names("what new features were added to Godot 4.7?", tools)

    assert selected == ["query_knowledge", "code_search", "web_search"]


def test_how_to_code_questions_do_not_expose_file_write_tools():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in (
            "query_knowledge",
            "code_search",
            "web_search",
            "read_file",
            "list_dir",
            "run_shell",
            "write_file",
        )
    }

    selected = _select_tool_names("how to code topdown 2d movement on godot?", tools)

    assert selected == []


def test_code_generation_uses_retrieval_when_current_docs_are_explicitly_requested():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in ("query_knowledge", "code_search", "web_search", "fetch_url")
    }

    selected = _select_tool_names(
        "Use the current official docs to write a Godot movement script.", tools
    )

    assert selected == ["web_search", "fetch_url", "query_knowledge", "code_search"]


def test_do_not_search_removes_retrieval_tools_from_workspace_code_request():
    tools = {
        name: Tool(
            name,
            f"{name}.",
            {"type": "object", "properties": {}, "required": []},
            lambda: "",
        )
        for name in (
            "query_knowledge",
            "code_search",
            "web_search",
            "fetch_url",
            "read_file",
            "edit_file",
        )
    }

    selected = _select_tool_names("Edit the Character.gd in this repo, but do not search.", tools)

    assert selected == ["read_file", "edit_file"]


def test_public_command_reference_does_not_overpromise_local_only():
    assert "No API keys" not in COMMAND_REFERENCE
    assert "no cloud" not in COMMAND_REFERENCE.lower()
    assert "Web search via the configured provider" in COMMAND_REFERENCE


def test_status_mode_helpers():
    class FakeConfig:
        web_provider = "auto"
        permissions = {"web_search": "allow", "fetch_url": "deny", "run_shell": "ask"}

    assert _mode_from_permission("allow") == "on"
    assert _mode_from_permission("deny") == "off"
    assert _mode_from_permission("ask") == "ask"
    assert _web_mode(FakeConfig(), "web_search") == "auto"
    assert _web_mode(FakeConfig(), "fetch_url") == "off"


def test_web_search_display_shows_successful_google_provider():
    lines = _web_search_display_lines(
        {
            "provider": "google",
            "provider_label": "google",
            "attempted_providers": ["google"],
            "successful_providers": ["google"],
            "provider_attempts": [
                {"provider": "google", "status": "succeeded", "reason": "found 8 results"}
            ],
        },
        "Found 8 relevant results.",
    )

    assert lines[0] == "-> web_search [google]"
    assert lines[1] == "   Found 8 relevant results."


def test_web_search_display_shows_tavily_fallback_without_missing_providers():
    lines = _web_search_display_lines(
        {
            "provider": "tavily",
            "provider_label": "tavily",
            "attempted_providers": ["google", "tavily"],
            "successful_providers": ["tavily"],
            "provider_attempts": [
                {"provider": "google", "status": "quota_exhausted", "reason": "quota exhausted"},
                {"provider": "tavily", "status": "succeeded", "reason": "found 6 results"},
            ],
        },
        "Found 6 relevant results.",
    )

    assert lines[:4] == [
        "-> web_search [google]",
        "   quota exhausted - trying next provider.",
        "-> web_search [tavily]",
        "   Found 6 relevant results.",
    ]
    assert not any("missing" in line.lower() for line in lines)


def test_web_search_display_shows_ddgs_and_searxng_labels():
    ddgs = _web_search_display_lines(
        {
            "provider": "ddgs",
            "provider_label": "ddgs",
            "successful_providers": ["ddgs"],
        },
        "Found 3 relevant results.",
    )
    searxng = _web_search_display_lines(
        {
            "provider": "searxng",
            "provider_label": "searxng",
            "successful_providers": ["searxng"],
        },
        "Found 1 relevant result.",
    )

    assert ddgs[0] == "-> web_search [ddgs]"
    assert searxng[0] == "-> web_search [searxng]"


def test_web_search_display_shows_all_failed_providers():
    lines = _web_search_display_lines(
        {
            "provider": "",
            "attempted_providers": ["google", "tavily", "ddgs", "searxng"],
            "successful_providers": [],
            "provider_attempts": [
                {"provider": "google", "status": "quota_exhausted", "reason": "quota exhausted"},
                {"provider": "tavily", "status": "degraded", "reason": "unavailable"},
                {"provider": "ddgs", "status": "rate_limited", "reason": "rate limited"},
                {
                    "provider": "searxng",
                    "status": "no_relevant_results",
                    "reason": "no relevant results",
                },
            ],
        },
        "(no results)",
    )

    assert lines[:2] == ["-> web_search [google]", "   quota exhausted"]
    assert "-> web_search [tavily]" in lines
    assert "-> web_search [ddgs]" in lines
    assert "-> web_search [searxng]" in lines
    assert lines[-1] == "   No search provider succeeded."


def test_web_search_display_distinguishes_irrelevant_results_from_provider_failure():
    lines = _web_search_display_lines(
        {
            "provider": "searxng",
            "provider_label": "searxng",
            "attempted_providers": ["searxng"],
            "successful_providers": [],
            "providers_returned": ["searxng"],
            "provider_attempts": [
                {
                    "provider": "searxng",
                    "status": "no_candidate_results",
                    "reason": "returned 8 results; none passed candidate discovery",
                }
            ],
        },
        "(no results)",
    )

    assert lines == [
        "-> web_search [searxng]",
        "   returned 8 results; none passed candidate discovery",
    ]
    assert "No search provider succeeded." not in "\n".join(lines)


def test_web_search_display_shows_none_when_no_provider_selected():
    lines = _web_search_display_lines(
        {
            "provider": "none",
            "provider_label": "none",
            "attempted_providers": [],
            "successful_providers": [],
            "providers_returned": [],
            "provider_attempts": [],
        },
        "(no results)",
    )

    assert lines == [
        "-> web_search [none]",
        "   No configured provider was available.",
    ]


def test_web_search_display_shows_multi_provider_label():
    lines = _web_search_display_lines(
        {
            "provider": "multi",
            "provider_label": "google + exa",
            "successful_providers": ["google", "exa"],
        },
        "Found 9 relevant sources.",
    )

    assert lines[0] == "-> web_search [google + exa]"


def test_web_search_display_uses_structured_metadata_not_result_text():
    lines = _web_search_display_lines(
        {
            "provider": "google",
            "provider_label": "google",
            "successful_providers": ["google"],
        },
        "Found 8 relevant results from [searxng].",
    )

    assert lines[0] == "-> web_search [google]"


def test_web_search_display_infers_provider_from_result_metadata():
    lines = _web_search_display_lines(
        {
            "search_results": [
                {
                    "title": "American Intercon School",
                    "url": "https://americanintercon.edu.kh/",
                    "snippet": "American Intercon School Cambodia.",
                    "provider": "ddgs",
                }
            ]
        },
        "Found 1 relevant result.",
    )

    assert lines[0] == "-> web_search [ddgs]"


def test_search_execution_metadata_includes_counts_and_canonical_tool():
    class FakeResponse:
        results = [{"provider": "tavily"}]
        providers_attempted = ["google", "tavily"]
        providers_succeeded = ["tavily"]
        queries_attempted = ["q1", "q2"]
        provider_metadata = {}

    metadata = _search_execution_metadata(FakeResponse())

    assert metadata["canonical_tool"] == "web_search"
    assert metadata["active_provider"] == "tavily"
    assert metadata["fallback_used"] is True
    assert metadata["query_count"] == 2
    assert metadata["provider_request_count"] == 2


def test_search_execution_metadata_uses_none_when_all_providers_fail():
    class FakeResponse:
        results = []
        providers_attempted = ["google", "ddgs"]
        providers_succeeded = []
        queries_attempted = ["q1"]
        provider_metadata = {
            "provider_attempts": [
                {"provider": "google", "status": "quota_exhausted", "reason": "quota"},
                {"provider": "ddgs", "status": "rate_limited", "reason": "rate limited"},
            ]
        }

    metadata = _search_execution_metadata(FakeResponse())

    assert metadata["canonical_tool"] == "web_search"
    assert metadata["provider"] == "none"
    assert metadata["active_provider"] == "none"


def test_web_search_start_metadata_uses_router_provider_without_result_text(
    tmp_path,
    monkeypatch,
):
    import klaude_core.config as config_module

    class FakeWeb:
        cfg = None

    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path)
    cfg = Config()
    cfg.web_provider = "local"
    FakeWeb.cfg = cfg

    metadata = _web_search_start_metadata(FakeWeb(), "AIS school Cambodia", 5)

    assert metadata["canonical_tool"] == "web_search"
    assert metadata["provider"] == "searxng"
    assert metadata["provider_label"] == "searxng"
    assert metadata["query"] == "AIS school Cambodia"


def test_runtime_context_location_is_copied_to_search_config_only_in_memory():
    cfg = Config()

    _apply_runtime_context_to_search_config(cfg, _fake_runtime_result())

    assert cfg.runtime_context.location.configured_country == "KH"
    assert cfg.runtime_context.location.configured_region == ""


def test_query_knowledge_display_shows_library_and_result_count():
    lines = _query_knowledge_display_lines(
        {"library": "godot", "found": True, "result_count": 5},
        "context",
    )

    assert lines == ["-> query_knowledge [godot]", "   Found 5 relevant chunks."]


def test_knowledge_context_chunk_count_matches_hybrid_context_blocks():
    content = (
        "--- library: react; source: hooks; relevance: 0.91 ---\nFirst chunk\n\n"
        "--- library: react; source: effects; relevance: 0.84 ---\nSecond chunk"
    )

    assert _knowledge_context_chunk_count(content) == 2


def test_runtime_status_summary_reports_provider_and_location(monkeypatch, tmp_path):
    class FakeConfig:
        runtime_context_enabled = True
        runtime_context_provider = "auto"
        runtime_context_command_timeout_seconds = 3
        runtime_context_location_allow_network = False
        runtime_context_location_mode = "local"

    monkeypatch.setattr(
        "klaude_cli.main._runtime_context_result",
        lambda cfg, workdir: _fake_runtime_result(),
    )

    status_label, detail, location, result = _runtime_status_summary(FakeConfig(), tmp_path)

    assert status_label == "on"
    assert "provider=native" in detail
    assert "Cambodia" in location
    assert "source=timezone" in location
    assert result.context.provider == "native"


def test_knowledge_libraries_count_uses_lightweight_sqlite(tmp_path):
    import sqlite3

    db_dir = tmp_path / "knowledge.lance"
    db_dir.mkdir()
    db = sqlite3.connect(db_dir / "fts.db")
    db.execute(
        "CREATE TABLE active_sources (library TEXT, owner TEXT, source TEXT, version_id TEXT)"
    )
    db.execute("INSERT INTO active_sources VALUES ('react', 'docs:a', 'a', 'v1')")
    db.execute("INSERT INTO active_sources VALUES ('react', 'docs:b', 'b', 'v2')")
    db.execute("INSERT INTO active_sources VALUES ('nextjs', 'docs:c', 'c', 'v3')")
    db.commit()
    db.close()

    class FakeConfig:
        @property
        def knowledge_dir(self):
            return db_dir

    assert _knowledge_libraries_count(FakeConfig()) == 2


def test_system_info_json_emits_normalized_json(monkeypatch):
    printed = []

    monkeypatch.setattr("klaude_cli.main.load_config", lambda: object())
    monkeypatch.setattr(
        "klaude_cli.main._runtime_context_result",
        lambda cfg, workdir, refresh=False: _fake_runtime_result(),
    )
    monkeypatch.setattr(
        "klaude_cli.main.console.print_json",
        lambda payload: printed.append(payload),
    )

    system_info(as_json=True, refresh=False)

    payload = json.loads(printed[0])
    assert payload["provider"] == "native"
    assert payload["location"]["country_name"] == "Cambodia"


def test_iter_online_docs_entries_accepts_collection_and_library_aliases(tmp_path):
    docs_file = tmp_path / "online-docs.txt"
    docs_file.write_text(
        "# comment\n"
        "uv run klaude learn https://example.test/a -c alpha\n"
        "uv run klaude learn https://example.test/b -l beta\n"
        "uv run klaude query nope -c skipped\n"
    )

    entries = _iter_online_docs_entries(docs_file)

    assert entries == [
        (
            "https://example.test/a",
            "alpha",
            "uv run klaude learn https://example.test/a -c alpha",
        ),
        (
            "https://example.test/b",
            "beta",
            "uv run klaude learn https://example.test/b -l beta",
        ),
    ]


def test_iter_online_docs_entries_accepts_quoted_values(tmp_path):
    docs_file = tmp_path / "online-docs.txt"
    docs_file.write_text(
        'uv run klaude learn "docs/my source.md" -l "my library"\n'
        "uv run klaude learn 'https://example.test/a?q=hello world' --library quoted\n"
    )

    entries = _iter_online_docs_entries(docs_file)

    assert entries == [
        (
            "docs/my source.md",
            "my library",
            'uv run klaude learn "docs/my source.md" -l "my library"',
        ),
        (
            "https://example.test/a?q=hello world",
            "quoted",
            "uv run klaude learn 'https://example.test/a?q=hello world' --library quoted",
        ),
    ]


def test_online_docs_file_honors_environment_override(tmp_path, monkeypatch):
    docs_file = tmp_path / "custom online docs.txt"

    monkeypatch.setenv("KLAUDE_ONLINE_DOCS_FILE", str(docs_file))

    assert _online_docs_file() == docs_file


def test_online_docs_file_prefers_config_dir_copy(tmp_path, monkeypatch):
    config_dir = tmp_path / ".klaude" / "config"
    project_root = tmp_path / "project"
    config_dir.mkdir(parents=True)
    project_root.mkdir()
    configured_docs = config_dir / "online-docs.txt"
    root_docs = project_root / "online-docs.txt"
    configured_docs.write_text("uv run klaude learn https://example.test/a -l a\n")
    root_docs.write_text("uv run klaude learn https://example.test/b -l b\n")

    monkeypatch.delenv("KLAUDE_ONLINE_DOCS_FILE", raising=False)
    monkeypatch.setattr("klaude_cli.main.CONFIG_DIR", config_dir)
    monkeypatch.setattr("klaude_cli.main.SOURCE_ROOT", project_root)

    assert _online_docs_file() == configured_docs


def test_online_docs_file_falls_back_to_tracked_example(tmp_path, monkeypatch):
    config_dir = tmp_path / ".klaude" / "config"
    project_root = tmp_path / "project"
    config_dir.mkdir(parents=True)
    (project_root / "config" / "examples").mkdir(parents=True)
    example_docs = project_root / "config" / "examples" / "online-docs.txt"
    example_docs.write_text("uv run klaude learn https://example.test/a -l a\n")

    monkeypatch.delenv("KLAUDE_ONLINE_DOCS_FILE", raising=False)
    monkeypatch.setattr("klaude_cli.main.CONFIG_DIR", config_dir)
    monkeypatch.setattr("klaude_cli.main.SOURCE_ROOT", project_root)

    assert _online_docs_file() == example_docs


def test_update_online_docs_continues_after_failed_source(tmp_path, monkeypatch):
    docs_file = tmp_path / "online-docs.txt"
    docs_file.write_text(
        "uv run klaude learn https://example.test/ok -c ok\n"
        "uv run klaude learn https://example.test/bad -c bad\n"
        "uv run klaude learn https://example.test/same -c same\n"
    )
    monkeypatch.setattr("klaude_cli.main._online_docs_file", lambda: docs_file)

    def fake_learn(cfg, source, library):
        if library == "bad":
            raise RuntimeError("404 Not Found")
        if library == "same":
            return "unchanged", 0
        return "updated", 3

    monkeypatch.setattr("klaude_cli.main._learn_source_if_changed", fake_learn)

    total, updated, unchanged, failed = _update_online_docs(object())

    assert total == 3
    assert updated == 1
    assert unchanged == 1
    assert failed == [("bad", "https://example.test/bad", "404 Not Found")]


def test_docs_update_sources_updates_only_managed_sources(monkeypatch):
    calls = []
    cfg = object()

    monkeypatch.setattr("klaude_cli.main.load_config", lambda: cfg)
    monkeypatch.setattr(
        "klaude_knowledge.list_docs_sources",
        lambda _cfg: [{"name": "managed"}],
    )
    monkeypatch.setattr(
        "klaude_cli.main._update_managed_docs_sources",
        lambda _cfg, targets, max_pages: calls.append(("sources", targets, max_pages)),
    )
    monkeypatch.setattr(
        "klaude_cli.main._update_online_docs",
        lambda _cfg: calls.append(("online",)) or (0, 0, 0, []),
    )

    docs_update(name="", sources=True, all_sources=False, online_docs=False, max_pages=7)

    assert calls == [("sources", ["managed"], 7)]


def test_docs_update_online_processes_only_online_docs(monkeypatch):
    calls = []
    cfg = object()

    monkeypatch.setattr("klaude_cli.main.load_config", lambda: cfg)
    monkeypatch.setattr(
        "klaude_cli.main._update_managed_docs_sources",
        lambda _cfg, targets, max_pages: calls.append(("sources", targets, max_pages)),
    )
    monkeypatch.setattr(
        "klaude_cli.main._update_online_docs",
        lambda _cfg: calls.append(("online",)) or (1, 1, 0, []),
    )

    docs_update(name="", sources=False, all_sources=False, online_docs=True, max_pages=-1)

    assert calls == [("online",)]


def test_docs_update_all_processes_sources_and_online_docs(monkeypatch):
    calls = []
    cfg = object()

    monkeypatch.setattr("klaude_cli.main.load_config", lambda: cfg)
    monkeypatch.setattr(
        "klaude_knowledge.list_docs_sources",
        lambda _cfg: [{"name": "managed"}],
    )
    monkeypatch.setattr(
        "klaude_cli.main._update_managed_docs_sources",
        lambda _cfg, targets, max_pages: calls.append(("sources", targets, max_pages)),
    )
    monkeypatch.setattr(
        "klaude_cli.main._update_online_docs",
        lambda _cfg: calls.append(("online",)) or (1, 1, 0, []),
    )

    docs_update(name="", sources=False, all_sources=True, online_docs=False, max_pages=-1)

    assert calls == [("online",), ("sources", ["managed"], -1)]


def test_shell_online_docs_script_delegates_to_cli_parser():
    script_path = Path(__file__).resolve().parents[2] / "scripts/knowledge/install-online-docs.sh"
    script = script_path.read_text()

    assert "$KLAUDE_CONFIG_DIR/online-docs.txt" in script
    assert "$PROJECT_ROOT/config/examples/online-docs.txt" in script
    assert "uv run klaude docs update --online" in script
    assert "read -r -a" not in script


def test_install_script_uses_visible_config_and_data_only_klaude_home():
    script_path = Path(__file__).resolve().parents[2] / "scripts/install.sh"
    script = script_path.read_text()

    assert 'DEFAULT_CONFIG_DIR="$PWD/config"' in script
    assert 'ENV_FILE="$KLAUDE_CONFIG_DIR/.env"' in script
    assert 'ENV_EXAMPLE="config/examples/.env.example"' in script
    assert 'SEARXNG_ENV_FILE="$KLAUDE_CONFIG_DIR/searxng.env"' in script
    assert 'SEARXNG_ENV_EXAMPLE="config/examples/searxng.env"' in script
    assert 'KLAUDE_DATA_DIR="${KLAUDE_DATA_DIR:-$KLAUDE_HOME/data}"' in script
    assert ".klaude/config" not in script


def test_weather_tool_description_matches_single_location_capability():
    lowered = WEATHER_TOOL_DESCRIPTION.lower()

    assert "single-location" in lowered
    assert "hottest" not in lowered
    assert "coldest" not in lowered


def test_web_search_tool_description_requires_standalone_context():
    lowered = WEB_SEARCH_TOOL_DESCRIPTION.lower()

    assert "query must be standalone" in lowered
    assert "resolved entity" in lowered
    assert "relationship or role" in lowered
    assert "location constraints" in lowered
    assert "bare pronoun" in lowered
    assert "bare relationship" in lowered


def test_fetch_url_tool_description_requires_selective_untrusted_reading():
    lowered = FETCH_URL_TOOL_DESCRIPTION.lower()

    assert "one promising public webpage" in lowered
    assert "do not fetch every search result" in lowered
    assert "untrusted external evidence" in lowered
    assert "never instructions" in lowered


def test_cli_docs_indexing_uses_shared_owner_snapshot_helper():
    from klaude_cli.main import _index_installed_docs

    source = inspect.getsource(_index_installed_docs)

    assert "replace_owner_snapshot_atomic" in source
    assert "delete_sources" not in source


def test_mcp_indexing_uses_shared_owner_snapshot_helper():
    import klaude_knowledge.mcp_server as mcp_server

    source = inspect.getsource(mcp_server.main)

    assert "replace_owner_snapshot_atomic" in source
    assert "delete_sources" not in source


def test_setup_job_is_responsive_cancellable_and_does_not_start_queued_work(monkeypatch):
    import asyncio

    async def scenario():
        tui = _fake_persistent_tui()
        started = asyncio.Event()
        cleaned = asyncio.Event()
        finished = []

        async def operation(cancel):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        tui._start_setup_job("Test login", operation, finished.append, timeout=30)
        await started.wait()
        tui.pending.append("queued input")
        tui._start_next()
        assert list(tui.pending) == ["queued input"]
        assert "Esc / Ctrl+C cancel" in "".join(text for _, text in tui._status_fragments())
        tui._dismiss_picker()
        task = tui._setup_job
        await task
        assert cleaned.is_set()
        assert finished == [None]
        assert tui._setup_job is None
        assert tui.status_error == "Test login cancelled"

    asyncio.run(scenario())


@pytest.mark.parametrize("had_credentials", [True, False])
def test_mcp_oauth_setup_cancellation_closes_listener_and_preserves_prior_credentials(
    tmp_path, monkeypatch, had_credentials
):
    from contextlib import asynccontextmanager

    import klaude_cli.main as cli_main
    import klaude_cli.setup_jobs as setup_jobs
    from klaude_core.mcp_client import MCPClient, MCPRegistry, MCPServerConfig, MCPTokenStorage

    registry = MCPRegistry(tmp_path / "oauth.json")
    registry.save({"test": MCPServerConfig(
        name="test", transport="http", enabled=False, oauth=True, url="https://example.com/mcp"
    )})
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: registry)
    monkeypatch.setattr(
        MCPTokenStorage, "status", lambda _: SimpleNamespace(configured=had_credentials)
    )
    cleared = []
    monkeypatch.setattr(MCPTokenStorage, "clear", lambda _: cleared.append(True))

    async def inline_to_thread(function, /, *args, **kwargs):
        # This test targets callback cancellation after definition loading.
        # Keep its setup read deterministic across Python executor teardown races.
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline_to_thread)


    async def scenario():
        tui = _fake_persistent_tui()
        entered = asyncio.Event()
        closed = asyncio.Event()

        @asynccontextmanager
        async def loopback(*_args):
            answer = asyncio.get_running_loop().create_future()
            try:
                yield answer
            finally:
                answer.cancel()
                closed.set()

        async def discover(client, server):
            entered.set()
            await client.oauth_callback_handler()

        monkeypatch.setattr(setup_jobs, "oauth_loopback", loopback)
        monkeypatch.setattr(MCPClient, "discover_async", discover)
        monkeypatch.setattr(tui, "_open_settings_category", lambda *_: None)
        tui._run_mcp_enable("test")
        await asyncio.wait_for(entered.wait(), 1)
        task = tui._setup_job
        tui._cancel_setup_job()
        await asyncio.wait_for(task, 2)
        assert closed.is_set()
        assert not registry.load()["test"].enabled
        assert bool(cleared) is (not had_credentials)

    asyncio.run(scenario())


def test_setup_job_cancel_before_first_run_releases_ownership():
    import asyncio

    async def scenario():
        tui = _fake_persistent_tui()
        finished = []

        async def operation(cancel):
            raise AssertionError("cancelled job must not run")

        tui._start_setup_job("Test", operation, finished.append, timeout=30)
        task = tui._setup_job
        tui._cancel_setup_job()
        await asyncio.gather(task, return_exceptions=True)
        assert tui._setup_job is None
        assert finished == [None]

    asyncio.run(scenario())


def test_setup_job_timeout_is_visible_and_cleans_resources():
    import asyncio

    async def scenario():
        tui = _fake_persistent_tui()
        cleaned = asyncio.Event()

        async def operation(cancel):
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        tui._start_setup_job("Slow MCP", operation, lambda _: None, timeout=0.01)
        await tui._setup_job
        assert cleaned.is_set()
        assert "timed out" in tui.status_error
        assert tui._setup_job is None

    asyncio.run(scenario())


def test_codex_setup_runs_off_ui_thread_and_drains_cancelled_broker(monkeypatch):
    import asyncio

    import klaude_cli.main as cli_main

    entered = threading.Event()
    stopped = threading.Event()

    class Manager:
        def login(self, display, *, cancel_event):
            display("https://auth.openai.com/codex/device", "PRIVATE-CODE")
            entered.set()
            cancel_event.wait(2)
            stopped.set()
            raise cli_main.CodexAuthError("cancelled")

    async def scenario():
        tui = _fake_persistent_tui()
        monkeypatch.setattr(cli_main, "CodexAuthManager", Manager)
        monkeypatch.setattr(tui, "_open_model_backend", lambda *_: None)
        monkeypatch.setattr(tui, "_flush_transcript", lambda: None)
        tui._run_codex_auth_action("Login")
        for _ in range(100):
            if entered.is_set():
                break
            await asyncio.sleep(0.01)
        assert entered.is_set(), tui.status_error
        assert not stopped.is_set()  # the UI loop is live while broker waits
        tui._before_render(tui.application)
        assert any("PRIVATE-CODE" in value for value in tui._choice_values)
        assert "PRIVATE-CODE" not in tui.output.text
        assert "PRIVATE-CODE" not in tui._history
        task = tui._setup_job
        tui._cancel_setup_job()
        await task
        assert stopped.is_set()
        assert tui._setup_job is None
        assert not tui._codex_auth_state

    # Keep the real broker thread; debug mode avoids an observed Python 3.12
    # default-executor shutdown wakeup race on this host.
    asyncio.run(scenario(), debug=True)


def _configure_test_mcp_lane(tui, registry, monkeypatch):
    from klaude_cli.mcp_mutations import MCPMutationWriter

    monkeypatch.setattr(type(tui.cfg), "mcp_servers_file", property(lambda _: registry.path))
    if not hasattr(tui.agent, "tools"):
        tui.agent.tools = {}
    if not hasattr(tui.agent.gate, "policies"):
        tui.agent.gate.policies = {}
    tui._mcp_mutations.close()
    tui._mcp_mutations = MCPMutationWriter(registry.path, tui._emit, tui._prepare_mcp_catalog)


@pytest.mark.parametrize("outcome", ["success", "failure", "cancel", "changed"])
def test_mcp_setup_commits_enable_only_after_valid_discovery(tmp_path, monkeypatch, outcome):
    import asyncio

    import klaude_cli.main as cli_main
    from klaude_core.mcp_client import MCPClient, MCPRegistry, MCPServerConfig

    registry = MCPRegistry(tmp_path / "mcp.json")
    server = MCPServerConfig(
        name="test", transport="http", enabled=False, url="https://example.com/mcp"
    )
    registry.save({"test": server})
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: registry)

    async def inline_to_thread(function, /, *args, **kwargs):
        # This test targets discovery/save ordering, not worker scheduling.
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline_to_thread)

    async def discover(_client, _server):
        await asyncio.sleep(0)
        if outcome == "failure":
            raise RuntimeError("unavailable")
        if outcome == "cancel":
            raise asyncio.CancelledError
        if outcome == "changed":
            changed = registry.load()
            changed["test"].url = "https://other.example/mcp"
            registry.save(changed)
        return [{"name": "inspect", "inputSchema": {"type": "object"}}]

    monkeypatch.setattr(MCPClient, "discover_async", discover)

    async def scenario():
        tui = _fake_persistent_tui()
        _configure_test_mcp_lane(tui, registry, monkeypatch)
        reloads = []
        monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *_: reloads.append(True))
        monkeypatch.setattr(tui, "_open_settings_category", lambda *_: None)
        tui._run_mcp_enable("test")
        await tui._setup_job
        tui._mcp_mutations.close(wait=True)
        tui._before_render(None)
        assert registry.load()["test"].enabled is (outcome == "success")
        assert bool(reloads) is (outcome == "success")
        assert ("Enabled MCP" in tui.output.text) is (outcome == "success")

    asyncio.run(scenario())


@pytest.mark.parametrize("outcome", ["success", "save_failure", "session_changed"])
def test_mcp_enable_save_does_not_hold_setup_and_late_result_reports_actual_outcome(
    tmp_path, monkeypatch, outcome
):
    import asyncio

    import klaude_cli.main as cli_main
    from klaude_core.mcp_client import MCPClient, MCPRegistry, MCPServerConfig

    registry = MCPRegistry(tmp_path / "mcp.json")
    registry.save({"test": MCPServerConfig(
        name="test", transport="http", enabled=False, url="https://example.com/mcp"
    )})
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: registry)

    async def inline_to_thread(function, /, *args, **kwargs):
        # Definition reads and JSON encoding are incidental here. Keep the
        # save on its real mutation thread while avoiding this host's Python
        # 3.12 default-executor shutdown wakeup race.
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline_to_thread)
    entered = threading.Event()
    release = threading.Event()
    ui_thread = threading.get_ident()
    save = MCPRegistry.save

    def slow_save(current_registry, servers):
        assert threading.get_ident() != ui_thread
        entered.set()
        assert release.wait(2)
        if outcome == "save_failure":
            raise ValueError("configuration save rejected")
        save(current_registry, servers)

    async def discover(*_):
        return [{"name": "inspect", "inputSchema": {"type": "object"}}]

    monkeypatch.setattr(MCPRegistry, "save", slow_save)
    monkeypatch.setattr(MCPClient, "discover_async", discover)

    async def scenario():
        tui = _fake_persistent_tui()
        _configure_test_mcp_lane(tui, registry, monkeypatch)
        published = []
        opened = []
        monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *_: published.append(True))
        monkeypatch.setattr(tui, "_open_settings_category", lambda *_: opened.append(True))
        tui._run_mcp_enable("test")
        task = tui._setup_job
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            assert entered.is_set(), tui.status_error
            await task
            assert tui._setup_job is None
            assert tui._mcp_mutation_pending is not None
            assert "Enabled MCP" not in tui.output.text
            opened_before = len(opened)
            tui._cancel_setup_job()
            await asyncio.sleep(0.01)
            assert task.done()  # accepted filesystem write no longer holds setup
            if outcome == "session_changed":
                tui.session_id = "different-session"
        finally:
            release.set()
        # This is bounded test teardown, not a UI action.
        tui._mcp_mutations.close(wait=True)
        tui._before_render(None)
        assert registry.load()["test"].enabled is (outcome != "save_failure")
        assert bool(published) is (outcome == "success")
        assert len(opened) == opened_before  # late ack cannot reopen unrelated modal
        if outcome == "save_failure":
            assert "Enabled MCP" not in tui.output.text
            assert tui.status_error
        else:
            assert "Enabled MCP server" in tui.output.text
            assert tui._mcp_catalog_unconfirmed is (outcome == "session_changed")

    asyncio.run(scenario())


def test_mcp_enable_saved_but_failed_catalog_keeps_old_tools(tmp_path, monkeypatch):
    import asyncio

    import klaude_cli.main as cli_main
    from klaude_core.mcp_client import MCPClient, MCPRegistry, MCPServerConfig

    registry = MCPRegistry(tmp_path / "mcp.json")
    registry.save({"test": MCPServerConfig(
        name="test", transport="http", enabled=False, url="https://example.com/mcp"
    )})
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: registry)

    async def inline_to_thread(function, /, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline_to_thread)

    async def discover(*_):
        return [{"name": "inspect", "inputSchema": {"type": "object"}}]

    def failed_catalog(*_, **__):
        raise ValueError("invalid replacement catalog")

    monkeypatch.setattr(MCPClient, "discover_async", discover)
    monkeypatch.setattr(cli_main, "_configured_mcp_tools", failed_catalog)

    async def scenario():
        tui = _fake_persistent_tui()
        _configure_test_mcp_lane(tui, registry, monkeypatch)
        old_tools = dict(getattr(tui.agent, "tools", {}))
        old_tools["mcp__old"] = object()
        tui.agent.tools = old_tools
        monkeypatch.setattr(tui, "_open_settings_category", lambda *_: None)
        tui._run_mcp_enable("test")
        await tui._setup_job
        tui._mcp_mutations.close(wait=True)
        tui._before_render(None)
        assert registry.load()["test"].enabled
        assert tui.agent.tools is old_tools
        assert "Enabled MCP server" in tui.output.text
        assert "live tools unchanged" in tui.output.text

    asyncio.run(scenario())


def test_mcp_reload_failure_does_not_remove_existing_tools(monkeypatch):
    import klaude_cli.main as cli_main

    tui = _fake_persistent_tui()
    old_tools = dict(getattr(tui.agent, "tools", {}))
    old_tools["mcp__old"] = object()
    tui.agent.tools = old_tools

    def fail(*_, **__):
        raise ValueError("malformed MCP registry")

    monkeypatch.setattr(cli_main, "_configured_mcp_tools", fail)
    with pytest.raises(ValueError, match="malformed MCP registry"):
        tui._reload_mcp_tools()
    assert tui.agent.tools is old_tools


def test_mcp_publication_keeps_local_tools_and_permission_overrides():
    from types import SimpleNamespace

    tui = _fake_persistent_tui()
    local = object()
    remote = SimpleNamespace(name="mcp__new")
    tui.agent.tools = {"read_file": local, "mcp__old": object()}
    tui.agent.gate.policies = {"mcp__new": "deny"}
    manager = object()
    tui._publish_mcp_tools([remote], manager)
    assert tui.agent.tools == {"read_file": local, "mcp__new": remote}
    assert tui.agent.gate.policies["mcp__new"] == "deny"
    assert tui.agent.mcp_client_manager is manager
    assert tui.cfg._mcp_client_manager is manager


def test_configured_mcp_servers_render_boolean_toggles_with_transport_details():
    from klaude_cli.settings_panel import RowKind

    tui = _fake_persistent_tui()
    tui._mcp_inventory = {"servers": [
        {"name": "context7", "enabled": True, "tool_count": 2,
         "transport": "http", "oauth": False},
        {"name": "firecrawl-mcp-server", "enabled": False, "tool_count": 25,
         "transport": "stdio", "oauth": False},
    ], "truncated": False}
    tui._begin_choice("mcp settings", [
        "Manage permissions", "Reload",
        "Configuration snapshot 0s old",
        "context7: on (toggle) · http · 2 tools",
        "firecrawl-mcp-server: off (toggle) · stdio · 25 tools",
        "back",
    ], "context7: on (toggle) · http · 2 tools")

    rows = {row.id: row for row in tui._panel.page.rows}
    assert rows["context7"].kind == RowKind.TOGGLE
    assert rows["context7"].checked is True
    assert rows["context7"].description == "http · 2 tools"
    assert rows["firecrawl-mcp-server"].kind == RowKind.TOGGLE
    assert rows["firecrawl-mcp-server"].checked is False
    assert rows["firecrawl-mcp-server"].description == "stdio · 25 tools"
    body = tui._panel_body()
    rendered = {
        identity: "".join(
            text for line, owner in zip(body.lines, body.row_for_line, strict=True)
            if owner == identity for _style, text in line
        )
        for identity in ("context7", "firecrawl-mcp-server")
    }
    assert "[  ■] ON" in rendered["context7"]
    assert "[■  ] OFF" in rendered["firecrawl-mcp-server"]


@pytest.mark.parametrize("outcome", ["saved", "rejected", "unconfirmed", "catalog_failed", "stale"])
def test_mcp_cached_toggle_uses_owned_lane_and_scoped_ack(tmp_path, monkeypatch, outcome):
    from types import SimpleNamespace

    import klaude_cli.main as cli_main
    from klaude_cli.mcp_mutations import MCPMutationResult
    from klaude_cli.settings_panel import RowKind

    tui = _fake_persistent_tui()
    monkeypatch.setattr(
        type(tui.cfg), "mcp_servers_file", property(lambda _: tmp_path / "mcp.json")
    )
    submitted = []
    tui._mcp_mutations = SimpleNamespace(path=tui.cfg.mcp_servers_file,
                                       submit=lambda request: submitted.append(request) or True)
    tui._mcp_inventory = {"servers": [{
        "name": "docs", "enabled": True, "tool_count": 1, "fingerprint": "a" * 64,
        "transport": "http", "oauth": False,
    }], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    tui._begin_choice("mcp settings", ["docs: on (toggle)", "back"], "docs: on (toggle)")
    server_row = next(row for row in tui._panel.page.rows if row.id == "docs")
    assert server_row.kind == RowKind.TOGGLE
    assert server_row.checked is True
    assert server_row.value == ""
    publications = []
    monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *_: publications.append(True))
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: (_ for _ in ()).throw(
        AssertionError("UI must not read the MCP registry")
    ))
    tui._activate_panel_toggle()
    assert len(submitted) == 1 and not submitted[0].enabled
    assert tui._mcp_mutation_pending is not None
    tui._apply_settings_action("mcp settings", "docs: on (toggle)")
    assert len(submitted) == 1  # duplicate input cannot flip stale snapshot intent
    if outcome == "stale":
        tui.session_id = "new-session"
    state = "saved" if outcome in {"saved", "catalog_failed", "stale"} else outcome
    catalog = None if outcome == "catalog_failed" else ([], None)
    tui._emit("mcp_mutation_saved", MCPMutationResult(
        submitted[0], str(tui.cfg.mcp_servers_file), state, catalog,
    ))
    tui._before_render(None)
    assert tui._mcp_mutation_pending is None
    assert bool(publications) is (outcome == "saved")
    assert tui._mcp_catalog_unconfirmed is (outcome in {"unconfirmed", "catalog_failed", "stale"})
    if outcome in {"saved", "catalog_failed", "stale"}:
        assert "MCP setting saved" in tui.output.text
    else:
        assert "MCP setting saved" not in tui.output.text


def test_mcp_pending_save_timeout_is_not_a_rollback_and_late_ack_is_processed(monkeypatch):
    from klaude_cli.mcp_mutations import MCPMutationResult, MCPToggle

    tui = _fake_persistent_tui()
    request = MCPToggle("one", tui.session_id, "docs", "a" * 64, False)
    tui._mcp_mutation_pending = (request, time.monotonic() - 9)
    tui._before_render(None)
    assert "outcome unknown, not rolled back" in tui.status_error
    assert tui._mcp_mutation_pending is not None
    published = []
    monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *_: published.append(True))
    tui._emit("mcp_mutation_saved", MCPMutationResult(
        request, str(tui.cfg.mcp_servers_file), "saved", ([], None),
    ))
    tui._before_render(None)
    assert published == [True] and tui._mcp_mutation_pending is None


@pytest.mark.parametrize("outcome", ["loaded", "rejected", "stale"])
def test_mcp_reload_recovery_is_scoped_and_keeps_queue_safe(monkeypatch, outcome):
    from types import SimpleNamespace

    from klaude_cli.mcp_mutations import MCPMutationResult, MCPReload

    tui = _fake_persistent_tui()
    requests = []
    tui._mcp_mutations = SimpleNamespace(
        path=tui.cfg.mcp_servers_file, submit=lambda request: requests.append(request) or True,
    )
    tui._mcp_catalog_unconfirmed = True
    tui._begin_choice("mcp settings", ["Reload", "back"],
                      "Reload")
    published = []
    monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *_: published.append(True))
    tui._apply_settings_action("mcp settings", "Reload")
    assert isinstance(requests[0], MCPReload)
    assert tui._mcp_mutation_pending is not None
    if outcome == "stale":
        tui.session_id = "new-session"
    state = "rejected" if outcome == "rejected" else "loaded"
    tui._emit("mcp_mutation_saved", MCPMutationResult(
        requests[0], str(tui.cfg.mcp_servers_file), state,
        None if state == "rejected" else ([], None),
    ))
    tui._before_render(None)
    assert tui._mcp_catalog_unconfirmed is (outcome != "loaded")
    assert bool(published) is (outcome == "loaded")
    if outcome != "loaded":
        tui._choice_kind = None
        tui.pending.append("queued message")
        tui._start_next()
        assert list(tui.pending) == ["queued message"]


@pytest.mark.parametrize("duplicate", [False, True])
def test_mcp_import_input_queues_scoped_batch_without_ui_registry_reads(
    tmp_path, monkeypatch, duplicate
):
    import klaude_cli.main as cli_main
    from klaude_core.mcp_client import MCPRegistry, MCPServerConfig

    registry = MCPRegistry(tmp_path / "saved.json")
    if duplicate:
        registry.save({"new": MCPServerConfig(name="new", transport="stdio", command="original")})
    source = tmp_path / "private-source.json"
    source.write_text(json.dumps({"servers": {"new": {"command": "never-execute"}}}))
    tui = _fake_persistent_tui()
    _configure_test_mcp_lane(tui, registry, monkeypatch)
    monkeypatch.setattr(cli_main, "_mcp_registry", lambda: (_ for _ in ()).throw(
        AssertionError("UI import must not read registry")
    ))
    tui._import_mcp_configuration(str(source))
    assert tui._mcp_mutation_pending is not None
    assert "Imported" not in tui.output.text
    assert tui._mcp_mutations.close(wait=True)
    tui._before_render(None)
    saved = registry.load()["new"]
    assert saved.command == ("original" if duplicate else "never-execute")
    assert not saved.enabled or duplicate
    assert ("Imported 1 MCP server(s) as disabled" in tui.output.text) is (not duplicate)
    assert "private-source" not in tui.output.text


def test_picker_clearing_filter_restores_selection_and_no_match_enter_is_inert():
    tui = _fake_persistent_tui()
    tui._begin_choice("model cloud provider", ["OpenAI", "OpenRouter", "Google"], "Google")
    tui._set_input("OpenRouter")
    tui._refresh_choice_filter()
    tui._set_input("")
    tui._refresh_choice_filter()
    assert tui._choice_values[tui._choice_index] == "Google"
    tui._set_input("zzzzzzzzzz")
    tui._refresh_choice_filter()
    tui._submit_choice_response()
    assert tui._choice_kind == "model cloud provider"
    assert tui.input.text == "zzzzzzzzzz"
    assert "No matching options" in tui.status_error


def test_picker_permission_toggle_preserves_filter_and_logical_row(tmp_path):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
    tui._open_settings_category("permissions")
    tui._panel.search_active = True
    tui._set_input("Write file")
    tui._refresh_choice_filter()
    identity = tui._picker.selected_id
    tui._submit_choice_response()
    assert tui._choice_kind == "permission settings"
    assert tui.input.text == "write file"
    assert tui._picker.selected_id == identity
    assert tui._choice_values[tui._choice_index] == "Write file: ALLOW"
    assert not any(value.startswith("Current configuration:") for value in tui._choice_values)


def test_permission_panel_live_layout_resize_search_and_composer_restore(tmp_path):
    from prompt_toolkit.data_structures import Size

    class SizedOutput(DummyOutput):
        columns = 100

        def get_size(self):
            return Size(rows=30, columns=self.columns)

    async def exercise():
        tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
        output = SizedOutput()
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = output
            tui.application.renderer.output = output
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.08)
                tui._set_input("unsent draft")
                tui._open_settings_category("permissions")
                focused_before_redraw = tui.application.layout.current_control
                tui.application._redraw()
                assert tui.application.layout.current_control is tui.panel_control, (
                    tui._choice_kind, tui._panel is not None,
                    tui.application.layout.current_window,
                    focused_before_redraw,
                    tui.panel_body_window.render_info,
                    tui.choice_window.render_info,
                )
                assert tui.panel_header_window.render_info.window_height == 2
                assert tui.panel_footer_window.render_info.window_height == 2
                assert tui.panel_body_window.render_info.window_height >= 3
                tui._panel.picker.focus("reset")
                tui._apply_picker_state()
                tui.application._redraw()
                info = tui.panel_body_window.render_info
                assert info.vertical_scroll > 0
                assert tui._panel_body().selected_line in info.displayed_lines
                assert tui.panel_header_window.render_info.window_height == 2
                assert tui.panel_footer_window.render_info.window_height == 2
                output.columns = 36
                tui.application._redraw()
                assert 25 <= tui._panel_width() < 36
                tui._panel.search_active = True
                tui._set_input("Write file")
                tui._refresh_choice_filter()
                assert tui._panel.picker.selected_id == "tool:write_file"
                tui._accept_choice()
                assert tui._panel.picker.selected_id == "tool:write_file"
                assert tui._panel.picker.query == "write file"
                tui._cancel_choice()
                assert tui._panel.picker.query == ""
                tui._cancel_choice()
                assert tui._choice_kind == "settings"
                tui._cancel_choice()
                assert tui._choice_kind is None
                assert tui.application.layout.current_control is tui.input.control
                assert tui.input.text == "unsent draft"
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_panel_keyboard_space_search_and_escape_are_distinct(monkeypatch):
    from klaude_cli.settings_panel import PanelAction, PanelPage, PanelRow, RowKind

    async def exercise():
        tui = _fake_persistent_tui()
        actions = []
        monkeypatch.setattr(tui, "_apply_panel_action", actions.append)
        page = PanelPage("toggle-test", ("Settings", "Toggle Test"), (
            PanelRow("heading", RowKind.SECTION, "OPTIONS"),
            PanelRow("flag", RowKind.TOGGLE, "Activity updates", checked=True,
                     action=PanelAction("toggle", "flag"), section_id="heading"),
        ))
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                tui._open_panel(page, "toggle test")
                pipe.send_text(" ")
                await asyncio.sleep(0.05)
                assert actions == [PanelAction("toggle", "flag")]
                pipe.send_text("/activity")
                await asyncio.sleep(0.05)
                assert tui._panel.picker.query == "activity"
                pipe.send_text("\x1b")
                await asyncio.sleep(0.25)
                assert tui._choice_kind == "toggle test"
                assert tui._panel.picker.query == ""
                pipe.send_text("\x1b")
                await asyncio.sleep(0.25)
                assert tui._choice_kind is None
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_panel_mouse_confirmation_uses_row_identity_after_refresh(monkeypatch):
    from klaude_cli.settings_panel import PanelAction, PanelPage, PanelRow, RowKind

    tui = _fake_persistent_tui()
    actions = []
    monkeypatch.setattr(tui, "_apply_panel_action", actions.append)
    first = PanelPage("changing", ("Settings",), (
        PanelRow("first", RowKind.ACTION, "First", action=PanelAction("first")),
    ))
    second = PanelPage("changing", ("Settings",), (
        PanelRow("second", RowKind.ACTION, "Second", action=PanelAction("second")),
    ))
    tui._open_panel(first, "changing")
    tui._click_panel_line(0)
    tui._panel.replace(second)
    tui._click_panel_line(0)
    assert actions == []
    tui._click_panel_line(0)
    assert actions == [PanelAction("second")]


def test_settings_permission_mcp_breadcrumb_and_parent_focus_restore():
    from klaude_core.mcp_client import namespaced_tool_name

    tui = _fake_persistent_tui()
    tool = namespaced_tool_name("firecrawl", "search")
    tui.agent.tools = {tool: SimpleNamespace(description="MCP server firecrawl: search")}
    tui._begin_choice("settings", tui._settings_categories(), "mcp servers")
    assert tui._panel.picker.selected_id == "category:mcp servers"
    home = tui._panel
    home.scroll_top = 2
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "MCPs")
    tui._panel.picker.focus("permissions")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "MCPs", "Permissions")
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == (
        "Settings", "MCPs", "Permissions", "firecrawl"
    )
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "server:firecrawl"
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "permissions"
    tui._cancel_choice()
    assert tui._panel is home
    assert tui._panel.picker.selected_id == "category:mcp servers"
    assert tui._panel.scroll_top == 2


@pytest.mark.parametrize(
    ("category", "title"),
    [
        ("theme", "Theme"),
        ("input field", "Input Field"),
        ("divider", "Divider"),
        ("models", "Models"),
        ("providers", "Providers"),
        ("mcp servers", "MCPs"),
        ("memory", "Memory"),
        ("skills", "Skills"),
        ("tools", "Tools"),
        ("permissions", "Permissions"),
        ("runtime", "Runtime"),
    ],
)
def test_every_settings_category_uses_dedicated_panel(category, title):
    from klaude_cli.settings_panel import render_header

    tui = _fake_persistent_tui()
    tui._open_settings_category(category)

    assert tui._panel is not None
    assert tui.application.layout.current_control is tui.panel_control
    assert tui._panel.page.breadcrumb == ("Settings", title)
    assert title in str(render_header(tui._panel.page, 100))
    assert tui.application.full_screen is False
    assert "Local-first coding" in tui.output.text


def test_settings_heading_underlines_only_the_title():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "models")
    heading = next(row for row in tui._panel_body().lines if "ASSISTANT" in str(row))
    assert heading == (
        ("class:panel.heading-marker", "▪ "),
        ("class:panel.section", "ASSISTANT"),
    )
    style = tui.application.style
    assert style.get_attrs_for_style_str("class:panel.section").underline is True
    assert style.get_attrs_for_style_str("class:panel.heading-marker").underline is False


@pytest.mark.parametrize(
    "theme", ["autumn", "crimson-red", "neon-synth", "pastelle-pink", "hacker-green"]
)
def test_panel_focus_background_keeps_text_hierarchy(theme):
    style = _tui_style(theme, DEFAULT_TEXT_THEME)
    input_surface = style.get_attrs_for_style_str("class:input-field")
    for text_style in ("panel.label", "panel.value", "panel.muted", "toggle.on"):
        plain = style.get_attrs_for_style_str(f"class:{text_style}")
        focused = style.get_attrs_for_style_str(
            f"class:panel.selected class:{text_style}"
        )
        assert focused.color == plain.color
        assert focused.bgcolor is not None
        assert focused.bgcolor != plain.bgcolor
        assert input_surface.bgcolor is not None
        assert all(
            0 < int(focused.bgcolor[index : index + 2], 16)
            - int(input_surface.bgcolor[index : index + 2], 16) <= 16
            for index in (0, 2, 4)
        )


def test_settings_subpages_keep_panel_focus_and_toggle_state(tmp_path):
    from klaude_cli.settings_panel import RowKind

    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
    tui._open_settings_category("tools")
    assert tui._panel is not None
    assert tui._panel.page.legacy_actions
    row = next(row for row in tui._panel.page.rows if row.id == "activity updates")
    assert row.kind == RowKind.TOGGLE and row.checked is True
    tui._picker.focus(row.id)
    tui._apply_picker_state()
    tui._activate_panel_toggle()
    assert tui.show_activity_updates is False
    assert tui._panel is not None
    assert tui._panel.picker.selected_id == row.id
    assert tui._panel.row().checked is False

    tui._open_settings_category("theme")
    tui._picker.focus("interface theme")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Theme", "Interface")

    tui._open_settings_category("runtime")
    tui._picker.focus("turn limit")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Runtime", "Turn Limit")

    tui._open_settings_category("providers")
    provider = next(row for row in tui._panel.page.rows if row.label == "Tavily")
    tui._picker.focus(provider.id)
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Providers", "Tavily")
    assert not any("API key" in row.value for row in tui._panel.page.rows)


def test_panel_footer_reports_only_the_current_settings_save_state():
    tui = _fake_persistent_tui()
    tui._runtime_save_state = "saved"
    tui._appearance_save_state = "failed"
    tui._open_settings_category("theme")
    assert "Save unconfirmed" in str(tui._panel_footer_fragments())
    tui._open_settings_category("tools")
    assert "Saved" in str(tui._panel_footer_fragments())
    tui._open_settings_category("providers")
    assert "Save unconfirmed" not in str(tui._panel_footer_fragments())
    assert "Saved" not in str(tui._panel_footer_fragments())


def test_settings_reset_rows_keep_actions_without_bracketed_control():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "permissions")
    home_reset = next(row for row in tui._panel.page.rows if row.id == "reset-all")
    assert home_reset.action.kind == "reset-all"
    assert home_reset.value == ""

    tui._open_settings_category("permissions")
    permission_reset = next(row for row in tui._panel.page.rows if row.id == "reset")
    assert permission_reset.action.kind == "reset"
    assert permission_reset.value == ""
    assert permission_reset.description

    tui._open_settings_category("tools")
    legacy_reset = next(
        row for row in tui._panel.page.rows if row.legacy_label == "reset to default"
    )
    assert legacy_reset.action.kind == "legacy-choice"
    assert legacy_reset.value == ""
    assert "[ Reset ]" not in "".join(
        text for line in tui._panel_body().lines for _style, text in line
    )


def test_settings_panel_keeps_live_status_counters_below_composer(monkeypatch):
    from os import terminal_size

    monkeypatch.setattr(
        "klaude_cli.main.shutil.get_terminal_size",
        lambda _fallback: terminal_size((120, 30)),
    )
    tui = _fake_persistent_tui()
    tui.ui_state.context_window = 16_384
    tui.ui_state.prompt_tokens = 0
    tui.ui_state.output_tokens = 0
    tui._open_settings_category("permissions")

    ready = "".join(text for _style, text in tui._status_fragments())
    assert "★ READY" in ready
    assert "queue 0" in ready
    assert "ctx 0/16,384 (0%)" in ready
    assert "last ↑0 ↓0" in ready
    assert "PERMISSIONS" not in ready

    tui.running = True
    tui.activity = "exploring"
    active = "".join(text for _style, text in tui._status_fragments())
    assert "READY" not in active
    assert "queue 0" in active
    assert "ctx 0/16,384 (0%)" in active
    assert "last ↑0 ↓0" in active


def test_model_logout_confirmation_uses_settings_panel():
    tui = _fake_persistent_tui()
    tui._model_flow_parent = "settings"
    tui._begin_model_logout_confirmation("openai_codex")
    assert tui._panel is not None
    assert tui._panel.page.breadcrumb == ("Settings", "Models", "Confirm logout")
    tui._dismiss_picker()
    assert tui._choice_kind == "model"
    assert tui._panel is not None


def test_picker_live_resume_refresh_preserves_filter_and_session_identity(monkeypatch):
    tui = _fake_persistent_tui()
    sessions = [
        {"session_id": "one", "title": "Parser investigation", "ts": 1, "active": False},
        {"session_id": "two", "title": "Other task", "ts": 1, "active": False},
    ]
    monkeypatch.setattr(tui.memory, "resumable_sessions", lambda: sessions, raising=False)
    tui._open_resume()
    tui._set_input("Parser")
    tui._refresh_choice_filter()
    sessions[0].update(title="Parser repaired", active=True)
    sessions.reverse()
    tui._refresh_resume_choices()
    assert tui._picker.selected_id == "session:one"
    assert tui.input.text == "Parser"
    assert "Parser repaired" in tui._choice_values[tui._choice_index]
    assert all("Other task" not in value for value in tui._choice_values)
    tui._set_input("")
    tui._refresh_choice_filter()
    assert tui._picker.selected_id == "session:one"
    assert any("Other task" in value for value in tui._choice_values)
    assert all("Parser investigation" not in value for value in tui._choice_values)


@pytest.mark.parametrize("wait_kind", ("none", "input", "secret"))
@pytest.mark.parametrize("cancel_key", ("\x1b", "\x03"))
def test_resume_panel_live_resize_search_refresh_and_cancel_preserve_active_work(
    monkeypatch, wait_kind, cancel_key,
):
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.utils import get_cwidth

    sessions = [
        {"session_id": "a" * 32, "title": "Parser investigation with detailed context",
         "ts": time.time(), "active": True},
        {"session_id": "b" * 32, "title": "Other project", "ts": time.time(), "active": False},
    ]

    class SizedOutput(DummyOutput):
        columns = 120

        def get_size(self):
            return Size(rows=30, columns=self.columns)

    async def exercise():
        tui = _fake_persistent_tui()
        monkeypatch.setattr(tui.memory, "resumable_sessions", lambda: sessions, raising=False)
        tui.running = True
        tui.pending.append("queued follow-up")
        request = {"question": "Choose an option", "options": ["One", "Two"],
                   "done": threading.Event(), "answer": None,
                   "label": "private credential", "prompt": "Enter credential"}
        if wait_kind == "input":
            tui._user_input_request = request
        elif wait_kind == "secret":
            tui._secret_request = request
        output = SizedOutput()
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = output
            tui.application.renderer.output = output
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                transcript = tui.output.text
                tui._open_resume()
                for width in (120, 75, 36, 22, 120):
                    output.columns = width
                    tui.application._redraw()
                    assert tui.application.layout.current_control is tui.panel_control
                    assert tui.panel_body_window.render_info is not None
                    assert tui.panel_header_window.render_info.window_height == (
                        3 if tui._panel_width() >= 60 else 2
                    )
                    assert tui.panel_footer_window.render_info.window_height == 2
                    body = tui._panel_body()
                    assert all(get_cwidth("".join(text for _style, text in line))
                               <= tui._panel_width() for line in body.lines)
                    assert tui.output.text == transcript
                pipe.send_text("\x1b[B")  # Down selects another session, not an input answer.
                await asyncio.sleep(0.08)
                assert tui._picker.selected_id == "session:" + "b" * 32
                pipe.send_text("/Parser")
                await asyncio.sleep(0.08)
                assert tui._panel.search_active
                assert tui._picker.selected_id == "session:" + "a" * 32
                tui._panel.scroll_top = 1
                sessions[0].update(title="Parser repaired", active=False)
                tui._refresh_resume_choices()
                assert tui._picker.query == "parser"
                assert tui._panel.row().label == "Parser repaired"
                assert not tui._panel.row().label_badge
                assert tui._panel.scroll_top == 1
                tui._append("\nBackground progress\n")
                tui.application._redraw()
                assert tui._choice_kind == "session"
                assert "Background progress" in tui.output.text
                pipe.send_text(cancel_key)
                await asyncio.sleep(0.6)
                assert tui._choice_kind == "session"  # First Escape leaves search.
                assert not tui._picker.query
                pipe.send_text(cancel_key)
                await asyncio.sleep(0.6)
                assert tui._choice_kind is None
                assert tui._panel is None
                assert tui.application.layout.current_control is tui.input.control
                assert tui.session_id == "session-1"
                assert tui.running
                assert not tui.cancel_requested.is_set()
                assert list(tui.pending) == ["queued follow-up"]
                assert not request["done"].is_set()
                assert not tui.application.full_screen
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


@pytest.mark.parametrize("wait_kind", ("input", "secret", "permission"))
def test_resume_panel_enter_selects_session_without_answering_pending_prompt(
    monkeypatch, wait_kind,
):
    tui = _fake_persistent_tui()
    monkeypatch.setattr(tui.memory, "resumable_sessions", lambda: [
        {"session_id": "saved", "title": "Saved project", "ts": time.time(), "active": False},
    ], raising=False)
    request = {"question": "Choose", "options": ["Yes", "No"], "done": threading.Event(),
               "answer": None, "label": "private credential", "prompt": "Enter credential",
               "tool": "run_shell"}
    setattr(tui, f"_{'user_input' if wait_kind == 'input' else wait_kind}_request", request)
    targets = []
    monkeypatch.setattr(tui, "_resume_session", targets.append)
    tui._open_resume()
    enter = next(binding.handler for binding in tui.key_bindings.bindings
                 if tuple(binding.keys) == (Keys.Enter,))
    enter(None)
    assert targets == ["saved"]
    assert tui._choice_kind is None
    assert not request["done"].is_set()
    assert request["answer"] is None


def test_picker_back_restores_parent_filter():
    tui = _fake_persistent_tui()
    tui._open_settings_category("providers")
    tui._set_input("OpenRouter")
    tui._refresh_choice_filter()
    tui._accept_choice()
    assert tui._choice_kind == "provider key settings"
    tui._cancel_choice()
    assert tui._choice_kind == "providers settings"
    assert tui.input.text == "openrouter"
    assert "OpenRouter" in tui._choice_values[tui._choice_index]


def test_picker_unavailable_selection_preserves_search(tmp_path):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
    tui._open_settings_category("permissions")
    tui._accept_choice()
    tui._set_input("Custom")
    tui._refresh_choice_filter()
    tui._submit_choice_response()
    assert tui._choice_kind == "permission preset"
    assert tui.input.text == "Custom"
    assert tui._choice_values[tui._choice_index] == "Custom"


def test_picker_mouse_confirmation_uses_identity_not_screen_position(monkeypatch):
    tui = _fake_persistent_tui()
    tui._begin_choice("test", ["Alpha", "Beta"], "Alpha")
    confirmed = []
    monkeypatch.setattr(tui, "_accept_choice", lambda: confirmed.append(True))
    tui._click_choice(0)
    tui._begin_choice("test", ["Beta", "Alpha"], "Alpha", refresh=True)
    tui._click_choice(0)
    assert not confirmed  # same screen position now means a different option
    tui._click_choice(0)
    assert confirmed == [True]


def test_picker_refresh_keeps_permission_preview_scroll_position(tmp_path):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "preferences.json")
    tui._open_settings_category("permissions")
    tui._accept_choice()
    tui.text_theme_preview.buffer.cursor_position = len(tui.text_theme_preview.text) // 2
    position = tui.text_theme_preview.buffer.cursor_position
    tui._begin_choice(
        "permission preset", list(tui._choice_all_values), "Balanced", refresh=True
    )
    assert tui.text_theme_preview.buffer.cursor_position == position


def test_picker_model_refresh_uses_model_reference_and_auth_action_identity():
    from klaude_core.model_runtime import ModelInfo

    tui = _fake_persistent_tui()
    tui._model_auth_backend = "openai_codex"
    model = ModelInfo("openai_codex", "gpt-test", "GPT Test")
    tui._model_choices = {"GPT Test": model}
    tui._begin_choice("model", ["Login", "GPT Test", "back"], "GPT Test")
    tui._set_input("GPT")
    tui._refresh_choice_filter()
    tui._model_choices = {"GPT Test updated": model}
    tui._begin_choice("model", ["Logout", "GPT Test updated", "back"], "Logout", refresh=True)
    assert tui._picker.selected_id == "model:openai_codex/gpt-test"
    assert tui._choice_values[tui._choice_index] == "GPT Test updated"
    assert tui.input.text == "gpt"
    tui._set_input("")
    tui._refresh_choice_filter()
    tui._choice_index = tui._choice_values.index("Logout")
    tui._begin_choice("model", ["Login", "GPT Test updated", "back"], "GPT Test updated",
                      refresh=True)
    assert tui._picker.selected_id == "account-auth"
    assert tui._choice_values[tui._choice_index] == "Login"


def test_stale_tui_clients_save_only_edited_runtime_and_appearance_fields(tmp_path):
    preferences, appearance = tmp_path / "preferences.json", tmp_path / "appearance.json"
    first = _fake_persistent_tui(appearance, preferences)
    second = _fake_persistent_tui(appearance, preferences)
    first.agent.ollama_options["num_ctx"] = 16384
    first._persist_runtime_preferences("num_ctx")
    second.agent.max_steps = 40
    second._persist_runtime_preferences("max_steps")
    assert _load_runtime_preferences(preferences) == {"num_ctx": 16384, "max_steps": 40}
    first.appearance.theme = "crimson-red"
    first._commit_appearance("theme", fields=("theme",))
    second.appearance.input_border = False
    second._commit_appearance("border", fields=("input_border",))
    saved = json.loads(appearance.read_text())
    assert saved["theme"]["interface"] == "crimson-red"
    assert saved["input_field"]["border"] is False


def test_stale_tui_permission_rows_do_not_overwrite_each_other(tmp_path):
    preferences = tmp_path / "preferences.json"
    first = _fake_persistent_tui(chat_preferences_path=preferences)
    second = _fake_persistent_tui(chat_preferences_path=preferences)
    first._open_settings_category("permissions")
    second._open_settings_category("permissions")
    first._choice_index = first._choice_values.index("Write file: ASK")
    first._accept_choice()
    second._choice_index = second._choice_values.index("Edit file: ASK")
    second._accept_choice()
    saved = json.loads(preferences.read_text())["permissions"]
    assert saved == {"write_file": "allow", "edit_file": "allow"}
    second._before_render(None)
    assert second.agent.gate.policies["write_file"] == "allow"


def test_tools_toggle_preserves_other_client_settings_and_unknown_fields(tmp_path):
    from klaude_core.settings_store import update_settings

    preferences = tmp_path / "preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=preferences)
    tui._open_settings_category("tools")
    update_settings(preferences, {
        ("last_model",): "new-model",
        ("tool_availability", "fetch_url"): False,
        ("display", "future_setting"): "preserved",
    })
    tui._choice_index = tui._choice_values.index("web search validation: on (toggle)")
    tui._accept_choice()
    saved = json.loads(preferences.read_text())
    assert saved["last_model"] == "new-model"
    assert saved["tool_availability"]["fetch_url"] is False
    assert saved["display"]["future_setting"] == "preserved"
    assert saved["tool_validation"]["web_search"] is False
    tui._before_render(None)
    assert tui._tool_availability["fetch_url"] is False
    assert "fetch_url" in tui.agent.disabled_tool_names


def test_pending_tool_toggles_and_reset_use_live_state_without_disk_reads(monkeypatch):
    tui = _fake_persistent_tui()
    requests = []

    class PendingWriter:
        def submit(self, changes):
            from copy import deepcopy

            requests.append(deepcopy(changes))
            return len(requests)

    tui._settings_writer = PendingWriter()
    monkeypatch.setattr(
        "klaude_cli.main._load_chat_preferences", lambda *_: pytest.fail("UI read")
    )
    monkeypatch.setattr(
        "klaude_cli.main.update_settings", lambda *args, **kwargs: pytest.fail("UI write")
    )
    tui._open_settings_category("tools")
    for prefix, expected_key in (
        ("web search validation:", ("tool_validation", "web_search")),
        ("knowledge library:", ("tool_availability", "query_knowledge")),
        ("provider exa:", ("web_provider_availability", "exa")),
        ("activity updates:", ("display", "activity_updates")),
    ):
        for enabled in (False, True, False):
            row = next(value for value in tui._choice_values if value.startswith(prefix))
            tui._choice_index = tui._choice_values.index(row)
            tui._accept_choice()
            assert requests[-1][expected_key] is enabled
            assert tui._choice_values[tui._choice_index].startswith(prefix)
    assert tui.agent.tool_config.web_search.result_validation_enabled is False
    assert "query_knowledge" in tui.agent.disabled_tool_names
    assert tui.agent.tool_config.web_providers["exa"].enabled is False
    assert tui.show_activity_updates is False
    tui._choice_index = tui._choice_values.index(RESET_THEME_CHOICE)
    tui._accept_choice()
    assert tui.agent.tool_config.web_search.result_validation_enabled is True
    assert "query_knowledge" not in tui.agent.disabled_tool_names
    assert tui.agent.tool_config.web_providers["exa"].enabled is True
    assert tui.show_activity_updates is True
    tui._choice_index = tui._choice_values.index("knowledge library: on (toggle)")
    tui._accept_choice()
    assert requests[-1] == {("tool_availability", "query_knowledge"): False}
    assert "query_knowledge" in tui.agent.disabled_tool_names
    tui._emit("settings_tools", (1, {"tool_availability": {"query_knowledge": True}}))
    tui._emit("settings_saved", (1, True))
    tui._before_render(None)
    assert "query_knowledge" in tui.agent.disabled_tool_names
    assert tui._runtime_save_state == "saving"
    tui._emit("settings_saved", (len(requests), False))
    tui._before_render(None)
    assert tui._runtime_save_state == "failed"
    assert "query_knowledge" in tui.agent.disabled_tool_names
    footer = "".join(text for _style, text in tui._panel_footer_fragments())
    assert "save unconfirmed" in footer.lower()


def test_tool_ack_merges_only_registered_boolean_settings():
    tui = _fake_persistent_tui()
    tui._runtime_save_revision = 3
    tui.agent.disabled_tool_names = {"external_tool"}
    tui._emit("settings_tools", (3, {
        "tool_availability": {"fetch_url": False, "unknown": False, "web_search": "secret"},
        "tool_validation": {"web_search": False},
        "web_provider_availability": {"exa": False, "unknown": False},
        "display": {"activity_updates": False},
    }))
    tui._before_render(None)
    assert tui.agent.disabled_tool_names == {"fetch_url", "external_tool"}
    assert tui.agent.tool_config.web_search.result_validation_enabled is False
    assert tui.agent.tool_config.web_providers["exa"].enabled is False
    assert tui.show_activity_updates is False
    assert "unknown" not in tui._web_provider_availability


def test_scoped_appearance_save_preserves_legacy_theme_fields(tmp_path):
    path = tmp_path / "appearance.json"
    path.write_text('{"theme": "hacker-green", "text_theme": "monokai", "future": 1}')
    _save_tui_appearance(path, TUIAppearance(theme="crimson-red"), fields=("theme",))
    assert _load_tui_appearance(path).text_theme == "monokai"
    assert json.loads(path.read_text())["future"] == 1


def test_busy_composer_save_is_visible_and_keeps_live_mode(tmp_path):
    from klaude_cli.settings_writer import SettingsWriter
    from klaude_core.settings_store import settings_lock

    path = tmp_path / "preferences.json"
    tui = _fake_persistent_tui(chat_preferences_path=path)
    tui._settings_writer = SettingsWriter(path, tui._emit)
    try:
        with settings_lock(path):
            start = time.monotonic()
            tui._set_composer_mode("vim")
            assert time.monotonic() - start < 0.25
            deadline = time.monotonic() + 2
            while tui._runtime_save_state != "failed" and time.monotonic() < deadline:
                tui._before_render(None)
                time.sleep(0.01)
        assert tui.composer_mode == "vim"
        assert "could not be confirmed" in tui.output.text
        assert not path.exists()
    finally:
        tui._settings_writer.close(wait=True)


def test_mcp_cli_save_conflict_is_a_clean_failure(tmp_path, monkeypatch):
    import typer
    from klaude_cli.main import _save_mcp_cli
    from klaude_core.mcp_client import MCPRegistry, MCPServerConfig

    registry = MCPRegistry(tmp_path / "mcp.json")
    initial = MCPServerConfig(name="test", transport="http", url="https://example.com/mcp")
    registry.save({"test": initial})
    stale = registry.load()
    other = MCPRegistry(registry.path)
    updated = other.load()
    updated["test"].url = "https://other.example/mcp"
    other.save(updated)
    stale["test"].enabled = False
    output = StringIO()
    monkeypatch.setattr("klaude_cli.main.console", Console(file=output, force_terminal=False))
    with pytest.raises(typer.Exit) as error:
        _save_mcp_cli(registry, stale)
    assert error.value.exit_code == 1
    assert "reload and retry" in output.getvalue()


def test_leaving_skills_cancels_job_and_drops_late_result():
    tui = _fake_persistent_tui()
    tui._open_settings_category("skills")
    identity = tui._background_jobs.latest["skills"]
    tui._cancel_choice()
    tui._events.put(("background_result", (
        "skills", identity, {"skills": [{"name": "late"}], "truncated": False}, ""
    )))
    tui._before_render(tui.application)
    assert tui._choice_kind == "settings"
    assert tui._skills_inventory is None
    assert tui._skills_inventory_loading  # Settings owns a fresh count inventory.
    assert tui._background_jobs.latest["skills"] != identity
    tui._cancel_choice()  # Closing Settings cancels that job too.
    assert not tui._skills_inventory_loading
    tui._open_settings_category("skills")
    assert tui._background_jobs.latest["skills"] != identity


def test_leaving_mcp_search_drops_late_catalog():
    tui = _fake_persistent_tui()
    tui._search_mcp_catalog("browser")
    identity = tui._background_jobs.latest["mcp-search"]
    tui._cancel_choice()
    tui._events.put(("background_result", (
        "mcp-search", identity, {"servers": [], "cached": False}, ""
    )))
    tui._before_render(tui.application)
    assert tui._choice_kind == "mcp settings"
    assert not tui._mcp_catalog_request_id


def test_mcp_settings_navigation_never_loads_registry_and_retains_focus_filter(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: pytest.fail("UI registry read"))
    tui._open_settings_category("mcp servers")
    assert next(row for row in tui._panel.page.rows if row.label == "MCP Servers").description == (
        "Loading configured MCP servers…"
    )
    identity = tui._background_jobs.latest["mcp-inventory"]
    result = {"servers": [{
        "name": "browser", "enabled": False, "oauth": False,
        "transport": "http", "tool_count": 0, "fingerprint": "a" * 64,
        "source_label": "Local configuration", "description": "",
    }], "truncated": False}
    tui._set_input("custom")
    tui._panel.search_active = True
    tui._refresh_choice_filter()
    tui._apply_background_result(("mcp-inventory", identity, result, ""))
    assert tui._choice_filter_query == "custom"
    assert tui._choice_values[tui._choice_index] == "Add custom MCP server"
    tui._set_input("")
    tui._refresh_choice_filter()
    assert "Manage" in tui._choice_values
    assert all(not row.startswith("browser:") for row in tui._choice_values)
    tui._mcp_inventory_loaded_at -= 31
    cached_time = tui._mcp_inventory_loaded_at
    tui._open_settings_category("mcp servers")
    identity = tui._background_jobs.latest["mcp-inventory"]
    tui._apply_background_result(("mcp-inventory", identity, None, "private error"))
    assert tui._mcp_inventory == result and tui._mcp_inventory_loaded_at == cached_time
    assert "private error" not in " ".join(tui._choice_values)


def test_leaving_mcp_inventory_drops_late_results_and_reopens_for_retry():
    tui = _fake_persistent_tui()
    tui._open_settings_category("mcp servers")
    identity = tui._background_jobs.latest["mcp-inventory"]
    tui._cancel_choice()
    tui._apply_background_result(("mcp-inventory", identity, {
        "servers": [], "truncated": False,
    }, ""))
    assert tui._mcp_inventory is None
    tui._open_settings_category("mcp servers")
    assert tui._background_jobs.latest["mcp-inventory"] != identity


def test_live_mcp_picker_filters_while_inventory_is_pending():
    async def exercise():
        tui = _fake_persistent_tui()
        tui._open_settings_category("mcp servers")
        identity = tui._background_jobs.latest["mcp-inventory"]
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                pipe.send_text("/custom")
                for _ in range(40):
                    if tui._choice_filter_query == "custom":
                        break
                    await asyncio.sleep(0.025)
                assert tui._choice_filter_query == "custom"
                assert tui._mcp_inventory_request
                tui._emit("background_result", ("mcp-inventory", identity, {
                    "servers": [], "truncated": False,
                }, ""))
                await asyncio.sleep(0.15)
                assert tui._choice_filter_query == "custom"
                assert tui._choice_values[tui._choice_index] == "Add custom MCP server"
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_mcp_disabled_server_review_has_no_ui_registry_read_and_binds_confirmation(monkeypatch):
    from klaude_cli.settings_panel import RowKind

    tui = _fake_persistent_tui()
    tui._mcp_inventory = {"servers": [{
        "name": "docs", "enabled": False, "oauth": False,
        "transport": "http", "tool_count": 0,
    }], "truncated": False}
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: pytest.fail("UI registry read"))
    tui._begin_choice("mcp settings", ["docs: off (toggle)", "back"], "docs: off (toggle)")
    assert tui._panel.row().kind == RowKind.TOGGLE
    assert tui._panel.row().checked is False
    tui._activate_panel_toggle()
    assert tui._choice_kind == "mcp review"
    identity = tui._background_jobs.latest["mcp-review"]
    tui._apply_background_result(("mcp-review", identity, {
        "name": "docs", "enabled": False, "tool_count": 0, "oauth": False,
        "fingerprint": "a" * 64, "endpoint": "https://example.com",
    }, ""))
    assert tui._choice_kind == "mcp enable confirmation"
    assert tui._mcp_enable_fingerprint == "a" * 64
    assert "exact definition" in " ".join(tui._choice_values)


def test_mcp_enable_rejects_definition_changed_after_review_before_discovery(tmp_path, monkeypatch):
    import asyncio

    from klaude_cli.mcp_inventory import definition_digest
    from klaude_core.mcp_client import MCPClient, MCPRegistry, MCPServerConfig

    registry = MCPRegistry(tmp_path / "mcp.json")
    server = MCPServerConfig("docs", "stdio", enabled=False, command="original-command")
    registry.save({"docs": server})
    expected = definition_digest(server)
    changed = registry.load()
    changed["docs"].command = "different-command"
    registry.save(changed)
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: registry)

    async def inline_to_thread(function, /, *args, **kwargs):
        # This case tests definition identity, not executor scheduling.
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", inline_to_thread)
    monkeypatch.setattr(
        MCPClient, "discover_async", lambda *args: pytest.fail("Unreviewed server discovery")
    )

    async def exercise():
        tui = _fake_persistent_tui()
        tui._run_mcp_enable("docs", expected_fingerprint=expected)
        await tui._setup_job
        assert "changed after review" in tui.status_error
        assert registry.load()["docs"].enabled is False

    asyncio.run(exercise())


def test_cancelled_mcp_review_cannot_open_confirmation_from_late_result():
    tui = _fake_persistent_tui()
    tui._review_mcp_server("docs")
    identity = tui._background_jobs.latest["mcp-review"]
    tui._cancel_choice()
    assert tui._choice_kind == "mcp settings"
    tui._apply_background_result(("mcp-review", identity, {
        "name": "docs", "enabled": False, "tool_count": 0, "oauth": False,
        "fingerprint": "a" * 64, "endpoint": "https://example.com",
    }, ""))
    assert tui._choice_kind == "mcp settings" and tui._mcp_enable_fingerprint == ""


def test_background_job_completion_does_not_replace_secret_modal(monkeypatch):
    tui = _fake_persistent_tui()
    opened = []
    monkeypatch.setattr(tui, "_open_model_backend", lambda *args: opened.append(args))
    identity = tui._background_jobs.submit("models:openrouter", {})
    tui._choice_kind = None
    tui._secret_request = {"label": "API key"}
    tui._set_input("private-unsent-text")
    tui._events.put(("background_result", (
        "models:openrouter", identity, {"updated": True}, ""
    )))
    tui._before_render(tui.application)
    assert not opened
    assert tui.input.text == "private-unsent-text"
    assert tui._secret_request is not None


def test_cloud_picker_never_waits_on_local_model_discovery(monkeypatch, tmp_path):
    from klaude_cli.main import _model_picker_rows

    monkeypatch.setattr("klaude_core.config.DATA_DIR", tmp_path)
    cfg = Config()
    cfg.openrouter_api_key = "test-key"

    class ForbiddenLocal:
        def list_models(self):
            pytest.fail("A cloud picker queried the local daemon")

    monkeypatch.setattr("klaude_cli.main.load_model_cache", lambda path: [
        ModelInfo("openrouter", "openrouter/free", "Free")
    ])
    start = time.monotonic()
    rows, choices = _model_picker_rows(cfg, ForbiddenLocal(), "openrouter")
    assert time.monotonic() - start < 0.25
    assert rows == ["openrouter/free"]
    assert choices["openrouter/free"].backend == "openrouter"


def test_exit_closes_background_job_owner(monkeypatch):
    tui = _fake_persistent_tui()
    tui._background_jobs.submit("skills", {})
    monkeypatch.setattr(tui.application, "exit", lambda **kwargs: None)
    monkeypatch.setattr(tui.memory, "clear_session_client", lambda *args: None, raising=False)
    tui._exit()
    assert not tui._background_jobs.latest
    assert tui.shutting_down


def test_local_picker_opens_without_network_and_discards_results_after_back(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr(tui.agent.ollama, "list_models", lambda: pytest.fail("UI network I/O"))
    tui.agent.model_info = ModelInfo("ollama", tui.agent.model, tui.agent.model)
    started = time.monotonic()
    tui._open_model_backend("ollama", "source")
    assert time.monotonic() - started < 0.25
    assert tui.agent.model in tui._model_choices
    assert any("Loading Ollama" in row for row in tui._choice_values)
    identity = tui._background_jobs.latest["local-models"]
    tui._dismiss_picker()
    tui._apply_background_result(("local-models", identity, {"names": ["late:1b"]}, ""))
    assert not tui._local_models
    assert not tui._local_models_loading
    assert tui._choice_kind == "model source"


def test_local_refresh_failure_keeps_previous_models_and_does_not_retry_loop():
    tui = _fake_persistent_tui()
    tui._local_models = [ModelInfo("ollama", "gemma4:e4b", "gemma4:e4b")]
    tui._open_model_backend("ollama", "source")
    identity = tui._background_jobs.latest["local-models"]
    tui._apply_background_result(("local-models", identity, None, "timed out"))
    assert "gemma4:e4b" in tui._model_choices
    assert "previous models" in tui._local_models_error
    assert tui._background_jobs.latest["local-models"] == identity
    assert not tui._local_models_loading


def test_live_local_picker_filters_while_catalog_is_pending(tmp_path, monkeypatch):
    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json")
        monkeypatch.setattr(tui.agent.ollama, "list_models", lambda: pytest.fail("UI network I/O"))
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            tui._open_model_backend("ollama", "source")
            identity = tui._background_jobs.latest["local-models"]
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                pipe.send_text("gem")
                await asyncio.sleep(0.15)
                assert tui._choice_filter_query == "gem"
                assert tui._local_models_loading
                tui._emit("background_result", (
                    "local-models", identity,
                    {"names": ["gemma4:e4b", "qwen3.5:9b"]}, ""
                ))
                await asyncio.sleep(0.15)
                assert tui._choice_filter_query == "gem"
                assert tui._choice_values[tui._choice_index] == "gemma4:e4b"
                assert tui.panel_body_window.render_info is not None
                pipe.send_text("\x1b")
                await asyncio.sleep(0.6)
                assert tui._choice_kind == "model"
                assert tui._choice_filter_query == ""
                pipe.send_text("\x1b")
                await asyncio.sleep(0.6)
                assert tui._choice_kind == "model source"
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_codex_status_never_waits_for_limits_and_drops_cross_session_output(tmp_path, monkeypatch):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.agent.model_info = ModelInfo("openai_codex", "gpt-test", "GPT")
    monkeypatch.setattr(
        "klaude_cli.main._codex_usage_rows", lambda agent: pytest.fail("UI quota I/O")
    )
    tui.running = True
    tui._set_input("/status")
    start = time.monotonic()
    tui._submit_buffer(steer=False)
    assert time.monotonic() - start < 0.25
    assert "loading account limits" in tui.output.text
    assert not tui.pending
    identity = tui._background_jobs.latest["codex-usage"]
    tui.session_id = "another-session"
    before = tui.output.text
    tui._apply_background_result((
        "codex-usage", identity,
        {"buckets": [{"limit_id": "codex", "primary": {
            "used_percent": 25, "window_duration_minutes": 300, "resets_at": None,
        }}]}, ""
    ))
    assert tui.output.text == before
    assert "75% left" in dict(tui._status_usage_rows())["5h limit"]
    assert not tui._codex_usage_loading


def test_codex_quota_failure_is_visible_and_cached_without_retry_loop():
    tui = _fake_persistent_tui()
    tui.agent.model_info = ModelInfo("openai_codex", "gpt-test", "GPT")
    tui._status_usage_rows()
    identity = tui._background_jobs.latest["codex-usage"]
    tui._apply_background_result(("codex-usage", identity, None, "private-provider-error"))
    assert "temporarily unavailable" in tui.output.text
    assert "private-provider-error" not in tui.output.text
    tui._status_usage_rows()
    assert tui._background_jobs.latest["codex-usage"] == identity


def test_model_reset_waits_for_async_local_inventory_without_network(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr(tui.agent.ollama, "list_models", lambda: pytest.fail("UI network I/O"))
    tui.cfg.models["coder"] = "qwen3.5:4b"
    tui._open_model_backend("ollama", "source")
    tui._choice_index = tui._choice_values.index(RESET_THEME_CHOICE)
    tui._accept_choice()
    assert "after discovery" in tui.status_error
    assert tui._choice_kind == "model"
    identity = tui._background_jobs.latest["local-models"]
    tui._apply_background_result((
        "local-models", identity, {"names": ["qwen3.5:4b"]}, ""
    ))
    tui._choice_index = tui._choice_values.index(RESET_THEME_CHOICE)
    tui._accept_choice()
    assert tui._choice_kind == "mode"


def test_unknown_local_model_command_opens_filtered_async_picker(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr(tui.agent.ollama, "list_models", lambda: pytest.fail("UI network I/O"))
    tui._set_input("/model ollama/gemma")
    tui._submit_buffer(steer=False)
    assert tui._choice_kind == "model"
    assert tui._choice_filter_query == "gemma"
    assert tui._local_models_loading
    assert tui.agent.model == "qwen3.5:4b"


def test_quota_refresh_failure_does_not_make_old_snapshot_appear_fresh():
    tui = _fake_persistent_tui()
    tui.agent.model_info = ModelInfo("openai_codex", "gpt-test", "GPT")
    tui._codex_usage_rows_cache = [("5h limit", "75% left")]
    old = tui._codex_usage_loaded_at = time.monotonic() - 90
    tui._status_usage_rows()
    identity = tui._background_jobs.latest["codex-usage"]
    tui._apply_background_result(("codex-usage", identity, None, "timed out"))
    assert tui._codex_usage_loaded_at == old
    rows = dict(tui._status_usage_rows())
    assert rows["5h limit"] == "75% left"
    assert "90s old" in rows["Limits snapshot"]
    assert "previous snapshot retained" in tui.output.text


@pytest.mark.parametrize("remote", [False, True])
def test_active_model_selection_applies_only_after_current_work(remote):
    tui = _fake_persistent_tui()
    original = tui.agent.ollama
    history = list(tui.agent.messages)
    tui.running = not remote
    tui._watching_remote = remote
    tui._activate_selected_model(ModelInfo("ollama", "gemma4:e2b", "Gemma"))
    assert tui.agent.model == "qwen3.5:4b"
    assert tui.agent.ollama is original
    assert "next prompt" in tui.output.text
    assert not tui._apply_next_prompt_model()
    # Replacing a pending selection does not touch the active turn either.
    tui._activate_selected_model(ModelInfo("ollama", "qwen3.5:9b", "Qwen"))
    tui.running = False
    tui._watching_remote = False
    assert tui._apply_next_prompt_model()
    assert tui.agent.model == "qwen3.5:9b"
    assert tui.agent.messages == history
    assert tui._next_prompt_model is None


@pytest.mark.parametrize("prompt", [
    "hi there where can i find a coffee shop near here?",
    "Where can I find a bookstore nearby?",
    "Recommend a local restaurant",
    "Can you find them for me",
])
def test_public_discovery_exposes_read_only_web_tools(prompt):
    tools = {name: SimpleNamespace(name=name) for name in (
        "web_search", "fetch_url", "write_file", "edit_file", "git_commit", "run_shell",
    )}
    selected = _select_tool_names(prompt, tools)
    assert "web_search" in selected and "fetch_url" in selected
    assert not {"write_file", "edit_file", "git_commit", "run_shell"}.intersection(selected)


def test_pending_model_does_not_leak_to_another_session():
    tui = _fake_persistent_tui()
    tui.running = True
    tui._activate_selected_model(ModelInfo("ollama", "gemma4:e2b", "Gemma"))
    tui.session_id = "different"
    tui.running = False
    assert tui._apply_next_prompt_model()
    assert tui.agent.model == "qwen3.5:4b"
    assert tui._next_prompt_model is None


def test_unavailable_model_remains_inert_with_visible_reason():
    from klaude_cli.main import _choice_unavailable

    tui = _fake_persistent_tui()
    label = _choice_unavailable("OpenRouter — API key not configured")
    tui._begin_choice("model", [label, "back"], label)
    tui._accept_choice()
    assert tui._choice_kind == "model"
    assert tui._choice_values[tui._choice_index] == label
    assert not tui.status_error
    assert any(style == "class:panel.status.warning" and str(label) in text
               for style, text in tui._panel_footer_fragments())


@pytest.mark.parametrize(
    "outcome", ["success", "cancel", "session", "key", "modal", "remote", "active"]
)
def test_cloud_activation_is_owned_and_commits_only_current_selection(monkeypatch, outcome):
    from klaude_core.model_runtime import OpenRouterRuntime

    async def exercise():
        tui = _fake_persistent_tui()
        original = tui.agent.ollama
        tui.agent.reasoning_mode = "standard"
        tui.agent.reasoning_effort = "low"
        tui.agent.model_info = ModelInfo("ollama", tui.agent.model, tui.agent.model)
        tui.cfg.openrouter_api_key = "private-test-key"
        monkeypatch.setattr(OpenRouterRuntime, "_client", lambda self: pytest.fail("UI SDK work"))
        info = ModelInfo("openrouter", "openrouter/free", "Free")
        if outcome == "active":
            tui.running = True
        started = time.monotonic()
        tui._activate_selected_model(info)
        assert time.monotonic() - started < 0.25
        task = tui._setup_job
        assert tui.agent.ollama is original
        for _ in range(5):
            await asyncio.sleep(0)
            if tui._model_activation_id:
                break
        identity = tui._model_activation_id
        assert identity
        tui.pending.append(PendingChatTurn("queued follow-up"))
        tui._start_next()
        assert tui.running == (outcome == "active") and len(tui.pending) == 1
        if outcome == "cancel":
            tui._cancel_setup_job()
        else:
            if outcome == "session":
                tui.session_id = "another-session"
            elif outcome == "key":
                tui.cfg.openrouter_api_key = "replacement-key"
            elif outcome == "modal":
                tui._choice_kind = None
                tui._secret_request = {"label": "unrelated secret"}
                tui._set_input("private-modal-text")
            elif outcome == "remote":
                tui._watching_remote = True
            tui._apply_background_result((
                "model-activation", identity, {"ready": True}, ""
            ))
        await task
        assert tui._setup_job is None
        assert not tui._model_activation_id
        assert "model-activation" not in tui._background_jobs.latest
        if outcome == "success":
            assert tui.agent.model_info == info
            assert tui._choice_kind == "mode"
            assert isinstance(tui.agent.ollama, OpenRouterRuntime)
            # Cancelling the reasoning step restores the *same* prior runtime,
            # with no second credential check or SDK initialization.
            tui._choice_index = tui._choice_values.index("thinking")
            tui._accept_choice()
            tui._cancel_choice(resume_queue=False)
            assert tui.agent.reasoning_mode == "standard"
            assert tui.agent.reasoning_effort == "low"
        assert tui.agent.ollama is original
        assert tui.agent.model == "qwen3.5:4b"
        assert len(tui.pending) == 1
        if outcome == "modal":
            assert tui.input.text == "private-modal-text"
            assert tui._secret_request is not None
        assert "private-test-key" not in tui.output.text
        assert "replacement-key" not in tui.output.text
        if outcome in {"active", "remote"}:
            assert tui._next_prompt_model == (tui.session_id, info)
            tui.running = False
            tui._watching_remote = False
            assert tui._apply_next_prompt_model()
            assert tui.agent.model_info == info
            assert isinstance(tui.agent.ollama, OpenRouterRuntime)

    asyncio.run(exercise())


def test_cloud_activation_timeout_cancels_worker_and_preserves_model(monkeypatch):
    async def exercise():
        tui = _fake_persistent_tui()
        start = tui._start_setup_job
        monkeypatch.setattr(tui, "_start_setup_job", lambda title, op, finish, **kwargs: start(
            title, op, finish, timeout=0.01
        ))
        original = tui.agent.ollama
        tui._activate_selected_model(ModelInfo("openai_codex", "gpt-test", "GPT"))
        await tui._setup_job
        assert tui.agent.ollama is original
        assert tui.agent.model == "qwen3.5:4b"
        assert "timed out" in tui.status_error
        assert tui._model_activation_future is None
        assert "model-activation" not in tui._background_jobs.latest
        assert tui._choice_kind == "model"

    asyncio.run(exercise())


@pytest.mark.parametrize("cancel_key", ["\x1b", "\x03"])
def test_live_cloud_activation_picker_accepts_escape_and_ctrl_c(tmp_path, cancel_key):
    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json")
        original = tui.agent.ollama
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                tui._activate_selected_model(ModelInfo("openai_codex", "gpt-test", "GPT"))
                setup = tui._setup_job
                await asyncio.sleep(0.1)
                assert tui._model_activation_future is not None
                assert tui.choice_window.render_info is not None
                pipe.send_text(cancel_key)
                await asyncio.sleep(0.6)
                await setup
                assert tui._setup_job is None
                assert tui._model_activation_future is None
                assert tui.agent.ollama is original
                assert tui.agent.model == "qwen3.5:4b"
                assert tui._choice_kind == "model"
                assert "cancelled" in tui.status_error
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_tui_status_uses_snapshot_without_database_or_guidance_reads(monkeypatch, tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._session_title_hint = "Current title"
    tui._status_memory_enabled = False
    tui.agent.injected_instruction_paths = ("/already-injected/AGENTS.md",)
    tui.agent.injected_instructions_truncated = True
    tui.agent.last_turn_capabilities = {
        "injected_instructions": ["/worker-snapshot/AGENTS.md"],
        "instructions_truncated": False,
    }
    before = vars(tui.agent).copy()
    def forbidden(*args, **kwargs):
        pytest.fail("Status did blocking metadata I/O")

    monkeypatch.setattr(tui.memory, "session_title", forbidden)
    monkeypatch.setattr(tui.memory, "auto_memory_enabled", forbidden)
    monkeypatch.setattr("klaude_cli.main._repository_instruction_context", forbidden)
    tui.running = True
    tui._set_input("/status")
    started = time.monotonic()
    tui._submit_buffer(steer=False)
    assert time.monotonic() - started < 0.25
    assert "Current title" in tui.output.text
    assert "Memory        Off" in tui.output.text
    assert "/worker-snapshot/AGENTS.md" in tui.output.text
    assert "/already-injected" not in tui.output.text
    assert vars(tui.agent) == before
    assert tui._status_metadata_loading
    assert not tui.pending


def test_status_does_not_claim_newly_created_guidance_is_injected(tmp_path):
    tui = _fake_persistent_tui()
    tui.agent.workdir = tmp_path
    (tmp_path / "AGENTS.md").write_text("New guidance not loaded into any prompt")
    result = _chat_status(
        tui.agent, tui.memory, tui.session_id, snapshot_only=True,
        title_hint="Snapshot title", memory_enabled=True, usage_rows=[],
    )
    assert "not injected (no prompt snapshot yet)" in result
    assert str(tmp_path / "AGENTS.md") not in result
    assert not hasattr(tui.agent, "injected_instruction_paths")


def test_status_metadata_refresh_updates_next_status_without_duplicate_output(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._set_input("/status")
    tui._submit_buffer(steer=False)
    original_output = tui.output.text
    assert original_output.count("Session name") == 1
    assert original_output.count("Memory ") == 1
    assert "Memory        Loading…" in original_output

    identity = tui._background_jobs.latest["status-metadata"]
    tui._apply_background_result((
        "status-metadata", identity,
        {"assigned_title": "Saved session name", "memory_enabled": True}, "",
    ))
    assert tui.output.text == original_output
    assert tui._session_title_hint == "Saved session name"
    assert tui._status_memory_enabled is True

    tui._set_input("/status")
    tui._submit_buffer(steer=False)
    second_status = tui.output.text[len(original_output):]
    assert second_status.count("Session name") == 1
    assert "Session name  Saved session name" in second_status
    assert "Memory        On" in second_status


@pytest.mark.parametrize("change", ["session", "title", "memory", "secret"])
def test_status_metadata_rejects_stale_results_and_preserves_modals(tmp_path, change):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._session_title_hint = "Original title"
    tui._refresh_status_metadata()
    identity = tui._background_jobs.latest["status-metadata"]
    if change == "session":
        tui.session_id = "another-session"
    elif change == "title":
        tui._session_title_hint = "Local rename"
    elif change == "memory":
        tui._invalidate_status_metadata()
        tui._status_memory_enabled = False
    else:
        tui._secret_request = {"label": "masked secret"}
        tui._set_input("unsent-secret")
    before = tui.output.text
    tui._apply_background_result((
        "status-metadata", identity, {"assigned_title": "Saved title", "memory_enabled": True}, ""
    ))
    if change == "secret":
        assert tui._session_title_hint == "Saved title"
        assert tui._status_memory_enabled is True
        assert tui.input.text == "unsent-secret"
        assert tui._secret_request is not None
    else:
        assert tui.output.text == before
        assert tui._session_title_hint != "Saved title"
        assert tui._status_memory_enabled is not True
    assert not tui._status_metadata_loading


def test_status_metadata_failure_is_visible_without_retry_loop(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui._refresh_status_metadata()
    identity = tui._background_jobs.latest["status-metadata"]
    tui._apply_background_result(("status-metadata", identity, None, "private-database-error"))
    assert "metadata unavailable" in tui.output.text
    assert "private-database-error" not in tui.output.text
    tui._refresh_status_metadata()
    assert tui._background_jobs.latest["status-metadata"] == identity
    tui._set_input("/status")
    tui._submit_buffer(steer=False)
    assert "Memory        Unavailable" in tui.output.text


@pytest.mark.parametrize("spelling", ["http_probe", "http probe"])
def test_named_probe_remains_exposed_in_multi_tool_request(spelling):
    tools = {
        name: Tool(name, name, {"type": "object", "properties": {}}, lambda: "")
        for name in ("http_probe", "current_time", "weather_lookup")
    }
    selected = _select_tool_names(
        f"Get the current time and weather, and perform a HEAD {spelling} of https://www.python.org.",
        tools,
    )
    assert set(selected) == set(tools)


@pytest.mark.parametrize("service", ["Hugging Face", "HuggingFace"])
def test_remote_hub_repository_inspection_does_not_become_workspace_inspection(service):
    names = ("read_file", "list_dir", "workspace_info", "huggingface_search",
             "huggingface_details", "huggingface_readme", "http_probe")
    tools = {name: Tool(name, name, {"type": "object", "properties": {}}, lambda: "")
             for name in names}
    selected = _select_tool_names(
        f"Use the {service} tools to find Qwen/Qwen3.5-0.8B, inspect its repository details "
        "and read its model card. Also use http_probe with HEAD on https://www.python.org.",
        tools,
    )
    assert set(selected) == {
        "huggingface_search", "huggingface_details", "huggingface_readme", "http_probe"
    }


@pytest.mark.parametrize("prefix", ["/cd ", "/cd ..", "/cd ~", "/cd ~/", "/cd ../"])
def test_cd_completion_directories_and_navigation_shortcuts(tmp_path, monkeypatch, prefix):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "src").mkdir()
    (workspace / "source.py").write_text("pass")
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "projects").mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    completer = ChatCommandCompleter(workdir_provider=lambda: workspace)
    values = [item.text for item in completer.get_completions(Document(prefix), None)]
    expected = {
        "/cd ": ["../", "src/"],
        "/cd ..": ["../"],
        "/cd ~": ["~/"],
        "/cd ~/": ["~/projects/"],
        "/cd ../": ["../home/", "../workspace/"],
    }
    assert values == expected[prefix]


def test_cd_completion_quotes_spaces_and_preserves_absolute_paths(tmp_path):
    folder = tmp_path / "project notes"
    folder.mkdir()
    (tmp_path / "project.md").write_text("not a directory")
    completer = ChatCommandCompleter(workdir_provider=lambda: tmp_path)
    assert [c.text for c in completer.get_completions(Document("/cd pro"), None)] == [
        '"project notes/"'
    ]
    assert [c.text for c in completer.get_completions(Document('/cd "pro'), None)] == [
        'project notes/"'
    ]
    assert [c.text for c in completer.get_completions(Document(f"/cd {tmp_path}/pro"), None)] == [
        f'"{folder}/"'
    ]


def test_backspace_reopens_cd_completion(monkeypatch):
    tui = _fake_persistent_tui()
    tui._set_input("/cd src")
    starts = []
    monkeypatch.setattr(tui.input.buffer, "start_completion", lambda **kw: starts.append(kw))
    delete = next(binding.handler for binding in tui.key_bindings.bindings
                  if tuple(binding.keys) == (Keys.Backspace,))
    delete(None)
    assert tui.input.text == "/cd sr"
    assert starts == [{"select_first": False}]


def test_memory_management_uses_ids_confirmation_and_background_write():
    from klaude_cli.session_actions import MemoryFactUpdate
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui()
    tui._memory_inventory = {
        "enabled": True, "count": 1, "hidden": 0, "facts": ["Prefer uv"],
        "entries": [{"id": "123456abcdef", "fact": "Prefer uv"}],
    }
    accepted = []
    tui._session_actions.submit = lambda action: accepted.append(action) or True
    tui._open_memory_facts()
    assert tui._panel.picker.selected_id == "fact:123456abcdef"
    tui._accept_choice()
    assert tui._panel.page.breadcrumb[-1] == "Memory detail"
    tui._apply_panel_action(PanelAction("memory-confirm", "123456abcdef"))
    assert tui._panel.picker.selected_id == "back"
    assert not accepted
    tui._apply_panel_action(PanelAction("memory-delete", "123456abcdef"))
    assert accepted == [MemoryFactUpdate(
        tui.session_id, tui.client_id, "123456abcdef", None
    )]
    assert tui._memory_fact_save_state == "saving"
    assert tui._panel.page.breadcrumb[-1] == "Manage memories"


def test_memory_edit_input_cancel_returns_to_memory_without_chat_history():
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui()
    tui._memory_inventory = {
        "count": 1, "hidden": 0,
        "entries": [{"id": "123456abcdef", "fact": "Prefer uv"}],
    }
    tui._open_memory_facts()
    tui._apply_panel_action(PanelAction("memory-edit", "123456abcdef"))
    assert tui.input.text == "Prefer uv"
    tui._answer_settings_input(None)
    assert tui._panel.page.breadcrumb[-1] == "Manage memories"
    assert tui._settings_input_request is None
    assert not tui._history


def test_memory_management_is_visible_while_loading_and_opens_after_refresh(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    try:
        tui._open_settings_category("memory")
        row = next(row for row in tui._panel.page.rows if row.id == "manage memories")
        assert row.label == "Manage memories"
        assert row.value == "Loading…"
        assert "Edit or delete" in row.description
        assert not row.enabled
        tui._panel.picker.focus(row.id)
        tui._apply_picker_state()
        tui._accept_choice()
        assert tui._choice_kind == "memory settings"
        identity = tui._background_jobs.latest["memory-inventory"]
        tui._apply_background_result(("memory-inventory", identity, {
            "enabled": True, "count": 1, "hidden": 0, "facts": ["Prefer uv"],
            "entries": [{"id": "123456abcdef", "fact": "Prefer uv"}],
        }, ""))
        assert tui._panel.picker.selected_id == "manage memories"
        row = next(row for row in tui._panel.page.rows if row.id == "manage memories")
        assert row.enabled
        assert not row.value
        tui._accept_choice()
        assert tui._panel.page.breadcrumb == ("Settings", "Memory", "Manage memories")
        tui._accept_choice()
        assert {row.label for row in tui._panel.page.rows} >= {"Edit memory", "Delete memory"}
    finally:
        tui.memory.db.close()


def test_memory_management_unavailable_remains_visible_and_inert(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._open_settings_category("memory")
    identity = tui._background_jobs.latest["memory-inventory"]
    tui._apply_background_result(("memory-inventory", identity, None, "private failure"))
    row = next(row for row in tui._panel.page.rows if row.id == "manage memories")
    assert row.value == "Unavailable"
    assert not row.enabled
    tui._panel.picker.focus(row.id)
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "memory settings"


@pytest.mark.parametrize("category", ["providers", "mcp servers"])
def test_settings_management_pages_do_not_invent_reset_actions(category, tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._open_settings_category(category)
    assert RESET_THEME_CHOICE not in tui._choice_values
    if category == "providers":
        tui._open_provider_key_settings("Tavily")
        assert RESET_THEME_CHOICE not in tui._choice_values


def test_tools_cancel_returns_to_settings_and_restores_draft_after_closing(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._set_input("Unsent draft")
    tui._begin_choice("settings", tui._settings_categories(), "tools")
    tui._open_settings_category("tools")
    tui._cancel_choice()
    assert tui._panel.page.breadcrumb == ("Settings",)
    assert tui._panel.picker.selected_id == "category:tools"
    tui._cancel_choice()
    assert tui.input.text == "Unsent draft"


def test_input_height_back_is_navigation_and_does_not_save(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._open_settings_category("input field")
    tui._apply_settings_action("input field settings", "height: 6–6 lines")
    assert "back" in tui._choice_values
    tui._panel.picker.focus("back")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Input Field")
    assert not (tmp_path / "appearance.json").exists()


def test_skills_delete_confirmation_is_inert_until_confirmed_and_keeps_identity(tmp_path):
    from klaude_cli.settings_panel import PanelAction
    from klaude_cli.skill_actions import SkillAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._skills_inventory = [{
        "name": "demo", "library": "shared", "indexed_file_count": 2, "identity": "old",
    }]
    requests = []
    tui._skill_actions.submit = lambda action: requests.append(action) or True
    tui._skill_discovery.installed.add("previous-install")
    tui._open_settings_category("skills")
    assert all(row.id != "skill:demo" for row in tui._panel.page.rows)
    tui._apply_panel_action(PanelAction("skill-manage"))
    assert tui._panel.page.breadcrumb == ("Settings", "Skills", "Manage")
    tui._panel.picker.focus("skill:demo")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Skills", "Manage", "demo")
    tui._panel.picker.focus("delete")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb[-1] == "Confirm deletion"
    assert tui._panel.picker.selected_id == "back"
    assert not requests
    # A refresh after confirmation cannot silently authorize a different definition.
    tui._skills_inventory[0]["identity"] = "new"
    tui._apply_panel_action(PanelAction("skill-delete", "demo"))
    assert requests == [SkillAction("delete", "demo", "old")]
    assert tui._skill_action_pending
    assert tui._panel.page.breadcrumb == ("Settings", "Skills", "Manage")
    tui._cancel_choice()
    tui._events.put(("skill_action_done", (requests[0], True, "Skill deleted")))
    tui._before_render(tui.application)
    assert tui._panel.page.breadcrumb == ("Settings", "Skills")
    assert not tui._skill_action_pending
    assert not tui._skill_discovery.installed


def test_skills_confirmation_reopens_on_back_even_after_previous_delete_focus(tmp_path):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._skills_inventory = [{"name": "demo", "identity": "id", "library": "demo"}]
    tui._open_settings_category("skills")
    tui._apply_panel_action(PanelAction("skill-manage"))
    assert tui._panel.picker.selected_id == "skill:demo"
    tui._apply_panel_action(PanelAction("skill-manage-detail", "demo"))
    tui._apply_panel_action(PanelAction("skill-manage-delete", "demo"))
    tui._panel.picker.focus("delete")
    tui._apply_picker_state()
    tui._cancel_choice()
    assert tui._choice_kind == "skills manage detail"
    assert tui._skill_delete_identity == ""
    tui._apply_panel_action(PanelAction("skill-manage-delete", "demo"))
    assert tui._panel.picker.selected_id == "back"


def test_skills_open_prepares_drop_folder_once_without_importing(tmp_path):
    from klaude_cli.skill_actions import SkillAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._skill_inbox_preparation_attempted = False
    requests = []
    tui._skill_actions.submit = lambda action: requests.append(action) or True
    tui._open_settings_category("skills")
    assert requests == [SkillAction("prepare")]
    assert tui._skill_action_pending
    tui._events.put(("skill_action_done", (requests[0], True, "")))
    tui._before_render(tui.application)
    tui._open_settings_category("skills")
    assert requests == [SkillAction("prepare")]
    assert not tui._skill_action_pending


def test_divider_settings_navigation_toggle_colors_reset_and_save_feedback(tmp_path):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._set_input("unsent draft")
    tui._begin_choice("settings", tui._settings_categories(), "divider")
    assert tui._panel.row().section_id == "section:appearance"
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Divider")
    tui._activate_panel_toggle()
    assert not tui.appearance.divider_visible
    assert not _load_tui_appearance(tui.appearance_path).divider_visible
    assert tui._panel.picker.selected_id == "visible"
    tui._before_render(None)
    assert "Saved" in "".join(text for _style, text in tui._panel_footer_fragments())
    tui._panel.picker.focus("line-color")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Divider", "Line color")
    tui._panel.picker.focus("color:same-as-text")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui.appearance.divider_color == "same-as-text"
    assert tui._panel.picker.selected_id == "color:same-as-text"
    assert tui._panel.row().value == "Current"
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "line-color"
    tui._panel.picker.focus("text-color")
    tui._apply_picker_state()
    tui._accept_choice()
    tui._panel.picker.focus("color:red")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui.appearance.divider_text_color == "red"
    assert _load_tui_appearance(tui.appearance_path).divider_text_color == "red"
    before = tui._panel.picker.selected_id
    tui._panel.search_active = True
    tui._set_input("Red")
    tui._refresh_choice_filter()
    tui._emit("appearance_saved", (tui._appearance_save_revision, False))
    tui._before_render(None)
    assert tui._panel.picker.selected_id == before
    assert tui._picker.query == "red"
    assert tui.appearance.divider_text_color == "red"
    assert "Save unconfirmed" in "".join(text for _style, text in tui._panel_footer_fragments())
    tui._cancel_choice()  # Clear search first.
    assert tui._choice_kind == "divider color"
    tui._cancel_choice()
    assert tui._choice_kind == "divider settings"
    tui._apply_panel_action(PanelAction("divider-reset"))
    assert tui.appearance.divider_visible
    assert tui.appearance.divider_color == "same-as-input-field"
    assert tui.appearance.divider_text_color == "bright-black"
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "category:divider"
    tui._cancel_choice()
    assert tui.input.text == "unsent draft"


def test_settings_divider_direct_entry_and_color_back_preserve_selection(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._set_input("/settings divider")
    tui._submit_buffer(steer=False)
    assert tui._choice_kind == "divider settings"
    tui._panel.picker.focus("text-color")
    tui._apply_picker_state()
    tui._accept_choice()
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "text-color"
    assert tui.appearance.divider_text_color == "bright-black"


def test_divider_panel_live_keyboard_resize_and_composer_restoration(tmp_path):
    from prompt_toolkit.data_structures import Size

    class SizedOutput(DummyOutput):
        columns = 110

        def get_size(self):
            return Size(rows=30, columns=self.columns)

    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
        output = SizedOutput()
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = output
            tui.application.renderer.output = output
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                tui._set_input("unsent divider draft")
                tui._begin_choice("settings", tui._settings_categories(), "divider")
                pipe.send_text("\r")
                await asyncio.sleep(0.08)
                for width in (110, 70, 36, 18, 110):
                    output.columns = width
                    tui.application._redraw()
                    assert tui.panel_header_window.render_info.window_height == 2
                    assert tui.panel_footer_window.render_info.window_height == 2
                    assert tui.application.layout.current_control is tui.panel_control
                    assert tui._panel.picker.selected_id == "visible"
                pipe.send_text(" ")
                await asyncio.sleep(0.08)
                assert not tui.appearance.divider_visible
                assert tui._panel.picker.selected_id == "visible"
                pipe.send_text("\x1b[B\r")  # Open Line color.
                await asyncio.sleep(0.08)
                assert tui._panel.page.breadcrumb[-1] == "Line color"
                pipe.send_text("/Accent")
                await asyncio.sleep(0.08)
                assert tui._panel.picker.selected_id == "color:accent"
                pipe.send_text("\r")
                await asyncio.sleep(0.08)
                assert tui.appearance.divider_color == "accent"
                assert tui._panel.picker.selected_id == "color:accent"
                assert tui._panel.row().value == "Current"
                pipe.send_text("\x1b")  # Clear the filter.
                await asyncio.sleep(0.6)
                pipe.send_text("\x1b")  # Return to Divider.
                await asyncio.sleep(0.6)
                assert tui._panel.picker.selected_id == "line-color"
                pipe.send_text("\x1b[B\x1b[B\r")  # Text color -> Custom pattern editor.
                await asyncio.sleep(0.08)
                assert tui._settings_input_request["on_submit"] == ("divider-pattern",)
                assert tui.application.layout.current_control is tui.input.control
                pipe.send_text("\x01\x0b∘₊✧\r")  # Replace the default pattern and apply.
                await asyncio.sleep(0.08)
                assert tui.appearance.divider_pattern == "∘₊✧"
                assert tui._panel.picker.selected_id == "pattern"
                pipe.send_text("\r")
                await asyncio.sleep(0.08)
                pipe.send_text("\x1b")  # Cancel editing without leaving Divider.
                await asyncio.sleep(0.6)
                assert tui._choice_kind == "divider settings"
                assert tui._panel.picker.selected_id == "pattern"
                pipe.send_text("\x1b")
                await asyncio.sleep(0.6)
                assert tui._panel.picker.selected_id == "category:divider"
                pipe.send_text("\x1b")
                await asyncio.sleep(0.6)
                assert tui._panel is None
                assert tui.input.text == "unsent divider draft"
                assert tui.application.layout.current_control is tui.input.control
                assert not tui.application.full_screen
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


@pytest.mark.parametrize("responds_to_cpr", [False, True])
def test_refresh_command_replays_current_style_without_changing_live_session(
    tmp_path, responds_to_cpr,
):
    import pyte
    from klaude_cli.main import _session_divider
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.color_depth import ColorDepth
    from prompt_toolkit.output.vt100 import Vt100_Output
    from prompt_toolkit.renderer import CPR_Support

    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")

        class Screen(pyte.HistoryScreen):
            def write_process_input(self, data):
                if responds_to_cpr:
                    pipe.send_text(data)

        screen = Screen(100, 30, history=2000)
        stream = pyte.Stream(screen)
        captured = StringIO()

        class Terminal:
            def isatty(self):
                return True

            def write(self, text):
                captured.write(text)
                stream.feed(text)

            def flush(self):
                pass

        output = Vt100_Output(
            Terminal(), lambda: Size(rows=screen.lines, columns=screen.columns),
            default_color_depth=ColorDepth.DEPTH_24_BIT, enable_cpr=responds_to_cpr,
        )

        def all_lines():
            return [
                "".join(row[x].data for x in range(screen.columns)).rstrip()
                for row in screen.history.top
            ] + [line.rstrip() for line in screen.display]

        def assert_replayed(visible):
            lines = all_lines()
            footer_row = next(i for i, line in enumerate(screen.display) if "klaude v" in line)
            assert footer_row == screen.lines - 1, screen.display
            assert [line for line in lines if line in messages] == messages
            row = next(i for i, line in enumerate(screen.display) if "klaude · " in line)
            assert ("━" in screen.display[row]) is visible
            label_start = 3 if visible else 0
            assert screen.buffer[row][label_start].fg == "ff80bf"
            if visible:
                assert screen.buffer[row][0].fg == "ff9f43"
            assert "streaming partial" in screen.display[row + 1]
            assert tui.live_output.text == "streaming partial"
            assert tui.running
            assert not tui.cancel_requested.is_set()
            assert list(tui.pending) == ["queued follow-up"]
            assert tui.session_id == "session-1"
            assert tui.agent.messages == original_messages
            assert tui._history[:len(original_history)] == original_history
            assert all(command == "/refresh" for command in tui._history[len(original_history):])
            assert tui.application.layout.current_control is tui.input.control
            assert not tui.application.full_screen

        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = tui.application.renderer.output = output
            tui.application.renderer.cpr_support = (
                CPR_Support.SUPPORTED if responds_to_cpr else CPR_Support.NOT_SUPPORTED
            )
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                tui._clear_session_view()
                messages = [f"retained transcript message {i:03d}" for i in range(80)]
                tui._append(_session_divider(tui.session_id, width=99) + "\n")
                tui._append("\n".join(messages) + "\n")
                tui._append(_message_divider("klaude", width=99) + "\nstreaming partial")
                tui.application._redraw()
                await asyncio.sleep(0.05)
                canonical = tui.output.text
                tui.running = True
                tui.pending.append("queued follow-up")
                original_messages = list(tui.agent.messages)
                original_history = list(tui._history)
                tui.appearance.divider_color = "orange"
                tui.appearance.divider_text_color = "pink"
                tui.application.style = tui._appearance_style()
                tui._set_input("unsent draft")
                tui._refresh_tui(replay_transcript=True)
                tui.application._redraw()
                await asyncio.sleep(0.1)
                assert_replayed(True)
                assert tui.input.text == "unsent draft"
                assert tui.output.text == canonical
                for visible in (False, True):
                    tui.appearance.divider_visible = visible
                    if responds_to_cpr:
                        tui.application.renderer.cpr_support = CPR_Support.UNKNOWN
                    tui._set_input("/refresh")
                    tui._submit_buffer(steer=False)
                    tui.application._redraw()
                    await asyncio.sleep(0.1)
                    assert_replayed(visible)
                rendered = captured.getvalue()
                tui.application._redraw()
                await asyncio.sleep(0.05)
                assert not any(
                    message in captured.getvalue()[len(rendered):] for message in messages
                )
                assert "\x1b[?1049h" not in captured.getvalue()
                tui._set_input("/clear")
                tui._submit_buffer(steer=False)
                tui._append("Only after clear\n")
                tui._set_input("/refresh")
                tui._submit_buffer(steer=False)
                tui.application._redraw()
                await asyncio.sleep(0.1)
                assert "Only after clear" in all_lines()
                footer_row = next(i for i, line in enumerate(screen.display) if "klaude v" in line)
                assert footer_row == screen.lines - 1, screen.display
                for columns, rows in ((70, 24), (110, 40), (100, 30)):
                    screen.resize(lines=rows, columns=columns)
                    tui._commit_appearance("Appearance redraw", fields=("divider_visible",))
                    tui.application._redraw()
                    await asyncio.sleep(0.1)
                    footer_row = next(
                        i for i, line in enumerate(screen.display) if "klaude v" in line
                    )
                    assert footer_row == rows - 1, screen.display
                    assert all_lines().count("Only after clear") == 1
                    tui.application._redraw()
                    await asyncio.sleep(0.05)
                    assert "klaude v" in screen.display[-1]
                assert not any(message in all_lines() for message in messages)
                assert tui.running
                assert list(tui.pending) == ["queued follow-up"]
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_refresh_replay_keeps_picker_preview_and_defers_pending_output(monkeypatch, tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    printed = []
    monkeypatch.setattr("klaude_cli.main.print_formatted_text",
                        lambda **kwargs: printed.append(kwargs["formatted_text"]))
    tui._append("\nExisting public transcript\n")
    tui._flush_transcript()
    printed.clear()
    tui._begin_choice("permission preset", ["Custom", "Balanced", "back"], "Balanced")
    tui._show_permission_preview("Temporary policy preview")
    tui._append("Pending public output\n")
    panel = tui._panel
    tui._refresh_tui(replay_transcript=True)
    tui._flush_transcript()
    assert not printed
    assert tui._permission_preview_visible
    assert tui._panel is panel
    assert tui.text_theme_preview.text == "Temporary policy preview"
    assert tui._text_theme_preview_pending == "Pending public output\n"
    tui._hide_permission_preview()
    tui._flush_transcript()
    public = "".join(value for batch in printed for _style, value in batch)
    assert public.count("Existing public transcript") == 1
    assert public.count("Pending public output") == 1
    assert "Temporary policy preview" not in public
    tui._flush_transcript()
    assert len(printed) == 1


@pytest.mark.parametrize("field,value", [
    ("theme", "hacker-green"), ("text_theme", "monokai"),
    ("input_border", False), ("input_height", 4), ("input_max_height", 10),
    ("divider_visible", False), ("divider_color", "orange"),
    ("divider_text_color", "pink"),
    ("divider_pattern", "∘₊✧"),
])
def test_applied_appearance_repaints_history_and_preserves_filtered_panel(
    tmp_path, field, value,
):
    import pyte
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.color_depth import ColorDepth
    from prompt_toolkit.output.vt100 import Vt100_Output

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    screen = pyte.HistoryScreen(100, 30, history=2000)
    stream = pyte.Stream(screen)
    captured = StringIO()

    class Terminal:
        def write(self, text):
            captured.write(text)
            stream.feed(text)

        def flush(self):
            pass

    output = Vt100_Output(
        Terminal(), lambda: Size(rows=30, columns=100),
        default_color_depth=ColorDepth.DEPTH_24_BIT, enable_cpr=False,
    )
    tui.application.output = tui.application.renderer.output = output
    tui._clear_session_view()
    messages = [f"earlier public message {i:03d}" for i in range(50)]
    tui._append("\n".join(messages) + "\n")
    divider = _message_divider("klaude", width=99)
    tui._append(divider + "\n")
    tui._flush_transcript()
    tui._set_input("unsent draft")
    tui._open_settings_category("divider")
    tui._panel.search_active = True
    tui._set_input("color")
    tui._refresh_choice_filter()
    panel = tui._panel
    focused = panel.picker.selected_id
    panel.scroll_top = 2
    tui.running = True
    tui.pending.append("queued follow-up")
    messages_before = list(tui.agent.messages)
    setattr(tui.appearance, field, value)
    tui._commit_appearance("test setting", fields=(field,))
    tui._flush_transcript()
    lines = [
        "".join(row[x].data for x in range(screen.columns)).rstrip()
        for row in screen.history.top
    ] + [line.rstrip() for line in screen.display]
    assert [line for line in lines if line in messages] == messages
    row = next(i for i, line in enumerate(screen.display) if "klaude · " in line)
    assert (tui.appearance.divider_pattern in screen.display[row]) is tui.appearance.divider_visible
    label_start = 3 if tui.appearance.divider_visible else 0
    style = tui.application.style
    assert screen.buffer[row][label_start].fg == style.get_attrs_for_style_str(
        "class:transcript.divider.text"
    ).color.removeprefix("ansi")
    if tui.appearance.divider_visible:
        assert screen.buffer[row][0].fg == style.get_attrs_for_style_str(
            "class:transcript.divider.rule"
        ).color
    assert tui._panel is panel
    assert panel.picker.selected_id == focused
    assert panel.picker.query == "color"
    assert panel.scroll_top == 2
    assert tui._panel_composer_draft[0] == "unsent draft"
    assert tui.running and not tui.cancel_requested.is_set()
    assert list(tui.pending) == ["queued follow-up"]
    assert tui.agent.messages == messages_before
    clears = captured.getvalue().count(TERMINAL_CLEAR_SEQUENCE)
    tui._emit("appearance_saved", (tui._appearance_save_revision, False))
    tui._before_render(None)
    assert captured.getvalue().count(TERMINAL_CLEAR_SEQUENCE) == clears
    assert getattr(tui.appearance, field) == value
    assert panel.picker.selected_id == focused


def test_divider_pattern_editor_validation_cancel_save_and_reset(tmp_path):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._set_input("unsent draft")
    tui._open_settings_category("divider")
    tui._panel.picker.focus("pattern")
    tui._apply_picker_state()
    messages = list(tui.agent.messages)
    tui._accept_choice()
    assert tui._settings_input_request["on_submit"] == ("divider-pattern",)
    assert tui.input.text == "━ "
    revision = tui._appearance_save_revision
    for invalid in ("", "x" * 25, "x\t", "\x1b[31m"):
        tui._set_input(invalid)
        tui._submit_settings_input_response()
        assert tui._settings_input_request is not None
        assert tui.input.text == invalid
        assert tui.status_error
        assert tui._appearance_save_revision == revision
        assert tui.appearance.divider_pattern == "━ "
    tui._answer_settings_input(None)
    assert tui._choice_kind == "divider settings"
    assert tui._panel.picker.selected_id == "pattern"
    assert not tui.status_error
    tui._accept_choice()
    tui._set_input(" ∘₊✧ ")
    tui._submit_settings_input_response()
    assert tui._settings_input_request is None
    assert tui._panel.picker.selected_id == "pattern"
    assert tui.appearance.divider_pattern == " ∘₊✧ "
    assert _load_tui_appearance(tui.appearance_path).divider_pattern == " ∘₊✧ "
    tui._emit("appearance_saved", (tui._appearance_save_revision, False))
    tui._before_render(None)
    assert tui.appearance.divider_pattern == " ∘₊✧ "
    assert tui._panel.picker.selected_id == "pattern"
    assert "Save unconfirmed" in "".join(text for _, text in tui._panel_footer_fragments())
    tui._apply_panel_action(PanelAction("divider-reset"))
    assert tui.appearance.divider_pattern == "━ "
    assert _load_tui_appearance(tui.appearance_path).divider_pattern == "━ "
    assert tui.agent.messages == messages
    tui._cancel_choice()
    tui._cancel_choice()
    assert tui.input.text == "unsent draft"


@pytest.mark.parametrize("category", ["theme", "input field", "divider"])
def test_appearance_save_feedback_stays_in_panel_footer(tmp_path, category):
    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._open_settings_category(category)
    tui.appearance.divider_pattern = "∘₊✧"
    tui._commit_appearance("Line pattern", fields=("divider_pattern",))
    assert "[appearance]" not in tui.output.text
    assert "Saving" in "".join(text for _, text in tui._panel_footer_fragments())
    tui._before_render(None)
    assert tui._appearance_save_state == "saved"
    assert "Saved" in "".join(text for _, text in tui._panel_footer_fragments())
    tui._open_settings_category(category)
    body = "".join(text for _, text in tui._panel_body_fragments())
    assert "Appearance saved" not in body
    assert "Saving appearance" not in body
    assert "Changes automatically refresh" not in body
    assert "[appearance]" not in tui.output.text
    assert _load_tui_appearance(tui.appearance_path).divider_pattern == "∘₊✧"


def test_spinner_settings_preview_selection_custom_draft_and_save_feedback(tmp_path, monkeypatch):
    from klaude_cli.settings_panel import PanelAction
    from klaude_cli.spinners import CATALOG, SpinnerSettings

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 0.2)
    tui._set_input("unsent spinner draft")
    tui._begin_choice("settings", tui._settings_categories(), "spinner")
    assert tui._panel.row().section_id == "section:appearance"
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Spinner")
    assert tui._choice_kind == "spinner settings"
    assert tui._panel.page.rows[0].label == "Custom"
    assert not any(row.id == "default" for row in tui._panel.page.rows)
    assert tui._panel.page.rows[-2].id == "reset"
    initial = tui.appearance.spinner
    revision = tui._appearance_save_revision
    tui._panel.picker.focus("spinner:dots2")
    tui._apply_picker_state()
    preview = "".join(text for _, text in tui._panel_header_fragments())
    assert CATALOG["dots2"].frame_at(0.2) in preview
    assert tui._spinner_preview().interval == 80
    assert tui.appearance.spinner == initial
    assert tui._appearance_save_revision == revision
    tui._accept_choice()
    assert tui.appearance.spinner.name == "dots2"
    assert _load_tui_appearance(tui.appearance_path).spinner.name == "dots2"
    tui._before_render(None)
    assert "Saved" in "".join(text for _, text in tui._panel_footer_fragments())
    tui._apply_panel_action(PanelAction("spinner-custom"))
    tui._accept_choice()  # Frames editor.
    assert tui.application.layout.current_control is tui.input.control
    tui._set_input('"⢎⡰", " ⢎⡡ "')
    tui._submit_settings_input_response()
    assert tui._spinner_draft.frames == ("⢎⡰", " ⢎⡡ ")
    assert tui.appearance.spinner.name == "dots2"
    tui._apply_panel_action(PanelAction("spinner-interval"))
    tui._set_input("0")
    tui._submit_settings_input_response()
    assert tui._settings_input_request is not None
    assert tui.status_error
    tui._set_input("240")
    tui._submit_settings_input_response()
    assert tui._spinner_draft.interval == 240
    tui._apply_panel_action(PanelAction("spinner-frames"))
    tui._set_input("")
    tui._submit_settings_input_response()
    assert tui._settings_input_request is not None
    tui._answer_settings_input(None)
    assert tui._choice_kind == "spinner custom"
    assert tui._spinner_draft.frames == ("⢎⡰", " ⢎⡡ ")
    tui._apply_panel_action(PanelAction("spinner-apply"))
    assert tui.appearance.spinner == SpinnerSettings("custom", ("⢎⡰", " ⢎⡡ "), 240)
    assert _load_tui_appearance(tui.appearance_path).spinner == tui.appearance.spinner
    tui._emit("appearance_saved", (tui._appearance_save_revision, False))
    tui._before_render(None)
    assert "Save unconfirmed" in "".join(text for _, text in tui._panel_footer_fragments())
    assert tui.appearance.spinner.name == "custom"
    assert tui._panel.picker.selected_id == "custom"
    tui._panel.picker.focus("reset")
    tui._apply_picker_state()
    assert tui._spinner_preview() == CATALOG["dots"]
    assert tui.appearance.spinner.name == "custom"
    tui._accept_choice()
    assert tui.appearance.spinner == SpinnerSettings()
    assert tui._panel.picker.selected_id == "reset"
    assert tui._panel.row().value == ""
    assert next(row for row in tui._panel.page.rows if row.id == "spinner:dots").value == "Current"
    assert _load_tui_appearance(tui.appearance_path).spinner == SpinnerSettings()
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "category:spinner"
    tui._cancel_choice()
    assert tui.input.text == "unsent spinner draft"


@pytest.mark.parametrize("activity", ["work", "remote", "setup", "permission", "input"])
def test_selected_spinner_used_by_every_tui_progress_indicator(monkeypatch, activity):
    from klaude_cli.spinners import SpinnerSettings

    tui = _fake_persistent_tui()
    tui.appearance.spinner = SpinnerSettings("custom", ("ab", "cd"), 200)
    monkeypatch.setattr("klaude_cli.main.time.monotonic", lambda: 0.2)
    if activity == "work":
        tui.running = True
    elif activity == "remote":
        tui._watching_remote = True
    elif activity == "setup":
        tui._setup_job = object()
    elif activity == "permission":
        tui._permission_request = {"tool": "run_shell"}
    else:
        tui._user_input_request = {"id": "test"}
    assert " cd " in "".join(text for _, text in tui._status_fragments())
    tui._setup_job = None
    tui._permission_request = None
    tui._user_input_request = None
    tui.running = tui._watching_remote = False
    assert "★ READY" in "".join(text for _, text in tui._status_fragments())


def test_spinner_settings_live_keyboard_preview_resize_custom_and_close(tmp_path):
    from prompt_toolkit.data_structures import Size

    class SizedOutput(DummyOutput):
        columns = 110

        def get_size(self):
            return Size(rows=30, columns=self.columns)

    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
        output = SizedOutput()
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = tui.application.renderer.output = output
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                tui._set_input("unsent spinner draft")
                tui._open_settings_category("spinner")
                pipe.send_text("/dots2")
                await asyncio.sleep(0.08)
                assert tui._panel.picker.selected_id == "spinner:dots2"
                assert tui.appearance.spinner.name == "dots"
                for width in (110, 70, 36, 18, 110):
                    output.columns = width
                    tui.application._redraw()
                    assert tui.panel_header_window.render_info.window_height >= 3
                    assert tui.panel_footer_window.render_info.window_height == 2
                    assert tui._panel.picker.selected_id == "spinner:dots2"
                pipe.send_text("\r")
                await asyncio.sleep(0.08)
                assert tui.appearance.spinner.name == "dots2"
                assert tui._choice_kind == "spinner settings"
                assert tui._panel.picker.query == "dots2"
                assert tui._panel.row().value == "Current"
                pipe.send_text("\x1b")  # Clear search before opening Custom.
                await asyncio.sleep(0.6)
                tui._panel.picker.focus("custom")
                tui._apply_picker_state()
                pipe.send_text("\r\r")  # Custom -> Frames.
                await asyncio.sleep(0.08)
                assert tui._settings_input_request["on_submit"] == ("spinner-frames",)
                pipe.send_text("\x01\x0b👩🏽\u200d💻🇺🇸\r")
                await asyncio.sleep(0.08)
                assert tui._spinner_draft.frames == ("👩🏽\u200d💻", "🇺🇸")
                assert tui.appearance.spinner.name == "dots2"
                pipe.send_text("\x1b[B\x1b[B\r")  # Apply spinner.
                await asyncio.sleep(0.08)
                assert tui.appearance.spinner.name == "custom"
                assert tui.application.refresh_interval == 0.1
                pipe.send_text("\x1b")
                await asyncio.sleep(0.6)
                pipe.send_text("\x1b")
                await asyncio.sleep(0.6)
                assert tui._panel is None
                assert tui.input.text == "unsent spinner draft"
                assert tui.application.layout.current_control is tui.input.control
                assert not tui.application.full_screen
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


def test_spinner_direct_entry_clock_cadence_and_background_state_are_preserved(tmp_path):
    from klaude_cli.spinners import SpinnerSettings

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._set_input("/settings spinner")
    tui._submit_buffer(steer=False)
    assert tui._choice_kind == "spinner settings"
    tui.running = True
    tui.pending.append("queued follow-up")
    original = list(tui.agent.messages)
    tui._before_render(None)
    before = tui.output.text
    tui._panel.picker.focus("spinner:dots8Bit")  # Upstream interval is 80 ms.
    tui._apply_picker_state()
    tui._before_render(None)
    assert tui.application.refresh_interval == 0.08
    assert tui.appearance.spinner.name == "dots"
    assert tui.output.text == before
    tui.appearance.spinner = SpinnerSettings("custom", ("ab", "x"), 16)
    tui._panel.picker.focus("custom")
    tui._apply_picker_state()
    tui._before_render(None)
    assert tui.application.refresh_interval == 0.016
    tui._cancel_choice()
    tui._cancel_choice()
    tui._before_render(None)
    assert tui.running
    assert list(tui.pending) == ["queued follow-up"]
    assert tui.agent.messages == original
    tui.running = False
    tui.pending.clear()
    tui._before_render(None)
    assert tui.application.refresh_interval == 0.1


@pytest.mark.parametrize("target,field", [
    ("line", "divider_color"), ("text", "divider_text_color"),
])
def test_divider_color_apply_keeps_page_filter_viewport_and_current_marker(tmp_path, target, field):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui._open_settings_category("divider")
    tui._apply_panel_action(PanelAction("divider-colors", target))
    tui._panel.search_active = True
    tui._set_input("blue")
    tui._refresh_choice_filter()
    tui._panel.picker.focus("color:blue")
    tui._apply_picker_state()
    panel = tui._panel
    scroll = panel.scroll_top
    tui._accept_choice()
    assert tui._choice_kind == "divider color"
    assert tui._panel is panel
    assert panel.picker.query == "blue"
    assert panel.scroll_top == scroll
    assert panel.picker.selected_id == "color:blue"
    assert panel.row().value == "Current"
    assert [row.id for row in panel.page.rows if row.selected] == ["color:blue"]
    assert getattr(_load_tui_appearance(tui.appearance_path), field) == "blue"
    tui._emit("appearance_saved", (tui._appearance_save_revision, False))
    tui._before_render(None)
    assert panel.row().value == "Current"
    assert getattr(tui.appearance, field) == "blue"
    assert panel.picker.query == "blue"
    tui._cancel_choice()  # Clear search.
    tui._cancel_choice()  # Explicit back.
    assert tui._choice_kind == "divider settings"


@pytest.mark.parametrize("kind,field,choice,other", [
    ("theme", "theme", "pastelle-pink", "autumn"),
    ("text theme", "text_theme", "monokai", "vscode-dark"),
])
def test_theme_apply_keeps_picker_and_marks_applied_value_through_preview_and_failure(
    tmp_path, kind, field, choice, other,
):
    from klaude_cli.main import TEXT_THEME_LABELS, TUI_THEME_LABELS

    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    labels = TUI_THEME_LABELS if kind == "theme" else TEXT_THEME_LABELS
    tui._begin_choice(kind, list(labels), getattr(tui.appearance, field))
    original_id = tui._panel.row().id
    assert tui._panel.row().value == "Current"
    tui._panel.search_active = True
    tui._set_input(choice)
    tui._refresh_choice_filter()
    tui._apply_choice_preview()
    assert getattr(tui.appearance, field) == choice
    assert [row.id for row in tui._panel.page.rows if row.selected] == [original_id]
    panel = tui._panel
    tui._accept_choice()
    assert tui._choice_kind == kind
    assert tui._panel is panel
    assert tui._panel.picker.query == choice
    assert tui._panel.row().value == "Current"
    assert [row.id for row in tui._panel.page.rows if row.selected] == [choice]
    assert getattr(_load_tui_appearance(tui.appearance_path), field) == choice
    tui._emit("appearance_saved", (tui._appearance_save_revision, False))
    tui._before_render(None)
    assert tui._panel.row().value == "Current"
    assert "Save unconfirmed" in "".join(text for _, text in tui._panel_footer_fragments())
    tui._cancel_choice()  # Clear search.
    tui._picker.focus(other)
    tui._apply_picker_state()
    tui._apply_choice_preview()
    assert getattr(tui.appearance, field) == other
    assert [row.id for row in tui._panel.page.rows if row.selected] == [choice]
    tui._cancel_choice()
    assert getattr(tui.appearance, field) == choice
    assert tui._choice_kind == "theme settings"


@pytest.mark.parametrize("editor", ["divider-pattern", "spinner-frames", "spinner-interval"])
def test_appearance_editors_keyboard_delete_typing_paste_and_cancel(tmp_path, editor):
    from klaude_cli.settings_panel import PanelAction

    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
        tui._history = ["previous chat message"]
        tui._set_input("unsent chat draft")
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                if editor == "divider-pattern":
                    tui._open_settings_category("divider")
                else:
                    tui._open_settings_category("spinner")
                    tui._apply_panel_action(PanelAction("spinner-custom"))
                parent = tui._panel
                tui._apply_panel_action(PanelAction(editor))
                assert tui._panel is parent  # Retained navigation state is not an active picker.
                assert tui._choice_kind is None
                assert not tui.input.buffer.multiline()
                pipe.send_text("\x01\x0banyz\x7f\x08")
                await asyncio.sleep(0.08)
                assert tui.input.text == "an"
                assert tui.application.layout.current_control is tui.input.control
                pipe.send_text("y\x1b\r\x0a")  # Alt+Enter and Ctrl+J must not add newlines.
                await asyncio.sleep(0.08)
                assert tui.input.text == "any"
                pipe.send_text("\x1b[A\x1b[B")  # Never load chat history into a setup editor.
                await asyncio.sleep(0.08)
                assert tui.input.text == "any"
                pipe.send_text("\x1b[200~a\r\nb\nc\x1b[201~")
                await asyncio.sleep(0.08)
                assert tui.input.text == "anya b c"
                assert not tui._composer_pastes
                assert tui._session_io_request().draft is None
                pipe.send_text("\x01\x0b\r")  # Invalid empty input stays editable.
                await asyncio.sleep(0.08)
                if editor != "spinner-interval":  # Blank interval has a valid default.
                    assert tui._settings_input_request is not None
                    pipe.send_text("any\x7f")
                    await asyncio.sleep(0.08)
                    assert tui.input.text == "an"
                    pipe.send_text("\x1b")
                    await asyncio.sleep(0.6)
                assert tui._settings_input_request is None
                assert tui._choice_kind == (
                    "divider settings" if editor == "divider-pattern" else "spinner custom"
                )
                assert tui.appearance.divider_pattern == "━ "
                assert tui.appearance.spinner.name == "dots"
                tui._cancel_choice()
                if editor != "divider-pattern":
                    tui._cancel_choice()
                tui._cancel_choice()
                assert tui._panel is None
                assert tui.input.text == "unsent chat draft"
                assert tui.input.buffer.multiline()
                pipe.send_text("\x0a")
                await asyncio.sleep(0.08)
                assert tui.input.text == "unsent chat draft\n"
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


@pytest.mark.parametrize("text,surface", [
    ("assistant answer\n", "class:output-field"),
    ("━━ Session: test\nuser message\n", "class:output-field class:transcript.user-message"),
    ("```python\nvalue = 1\n", "class:output-field class:transcript.code"),
    ("assistant partial", "class:output-field"),
])
def test_gap_below_output_keeps_output_background(tmp_path, text, surface):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.output.buffer.set_document(Document(text, len(text)), bypass_readonly=True)
    tui._flush_transcript()
    assert tui.output_spacer.height == 1
    assert tui.input_spacer.height == 2
    assert tui.output_spacer.style == "class:output-field"
    assert tui.input_spacer.style == "class:output-field"
    for theme in ("autumn", "pastelle"):
        style = _tui_style(theme, "vscode-dark")
        assert style.get_attrs_for_style_str(tui.output_spacer.style).bgcolor == (
            style.get_attrs_for_style_str("class:output-field").bgcolor
        )
    tui._text_theme_preview_visible = True
    assert tui.output_spacer.style == "class:output-field"
    tui._text_theme_preview_visible = False
    assert tui.output_spacer.style == "class:output-field"
    tui._clear_session_view()
    assert tui.output_spacer.style == "class:output-field"


@pytest.mark.parametrize("backend", ["openai_api", "openai_codex", "gemini_api", "openrouter"])
@pytest.mark.parametrize("signed_in", [False, True])
def test_model_provider_sign_in_status_is_muted_beside_heading(monkeypatch, backend, signed_in):
    import klaude_cli.main as cli_main

    monkeypatch.setattr(cli_main, "_model_picker_rows", lambda *args, **kwargs: ([], {}))
    tui = _fake_persistent_tui()
    provider = cli_main.MODEL_PROVIDER_FOR_BACKEND[backend]
    if backend == "openai_codex":
        tui._codex_auth_state = signed_in
    else:
        _env_name, attribute = cli_main.MODEL_API_KEY_PROVIDERS[provider]
        setattr(tui.cfg, attribute, "private-test-key" if signed_in else "")
    tui._open_model_backend(backend, "cloud")
    expected = "Status: signed in" if signed_in else "Status: not signed in"
    heading = tui._panel.page.rows[0]
    assert heading.label == provider.upper()
    assert heading.description == expected
    assert ("class:panel.muted", "  " + expected) in tui._panel_body().lines[0]
    assert not any(row.label.startswith("Status:") for row in tui._panel.page.rows)
    assert tui._choice_values[tui._choice_index] == ("Logout" if signed_in else "Login")
    assert "private-test-key" not in repr(tui._panel.page)


@pytest.mark.parametrize("width", [70, 120])
@pytest.mark.parametrize(
    "category", ["model", "tools", "permissions", "runtime", "memory", "spinner"]
)
def test_panel_errors_only_appear_in_page_footer(monkeypatch, category, width):
    from os import terminal_size

    import klaude_cli.main as cli_main

    monkeypatch.setattr(
        cli_main.shutil, "get_terminal_size", lambda fallback: terminal_size((width, 30))
    )
    monkeypatch.setattr(cli_main, "_model_picker_rows", lambda *args, **kwargs: ([], {}))
    tui = _fake_persistent_tui()
    if category == "model":
        tui._open_model_backend("gemini_api", "cloud")
    else:
        tui._open_settings_category(category)
    tui.status_error = "Gemini API — models unavailable"
    footer = "".join(text for _, text in tui._panel_footer_fragments())
    assert tui.status_error in footer
    status = tui._status_fragments()
    text = "".join(text for _, text in status)
    assert "READY" in text
    assert "ctx" in text
    assert "q:" in text or "queue" in text
    assert not any(style == "class:runtime_error" for style, _ in status)
    assert tui.status_error not in text


def test_modal_editor_errors_remain_visible_with_retained_parent_panel():
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui()
    tui._open_settings_category("divider")
    tui._apply_panel_action(PanelAction("divider-pattern"))
    assert tui._panel is not None
    tui.status_error = "Enter 1–24 characters"
    assert tui.status_error in "".join(text for _, text in tui._status_fragments())
    tui._answer_settings_input(None)
    tui._cancel_choice()
    tui._cancel_choice()
    tui.status_error = "Normal chat error"
    assert tui.status_error in "".join(text for _, text in tui._status_fragments())


def test_panel_save_failure_keeps_error_in_footer():
    tui = _fake_persistent_tui()
    tui._open_settings_category("tools")
    tui._runtime_save_state = "failed"
    tui.status_error = "Retry save"
    footer = "".join(text for _, text in tui._panel_footer_fragments())
    assert "Save unconfirmed" in footer
    assert "Retry save" in footer
    assert tui.status_error not in "".join(text for _, text in tui._status_fragments())


@pytest.mark.parametrize("row_id,pattern", [
    ("pattern:heavy", "━"), ("pattern:light", "─"),
    ("pattern:heavy-spaced", "━ "), ("pattern:light-spaced", "─ "),
])
def test_divider_presets_apply_only_pattern_and_preserve_focus(tmp_path, row_id, pattern):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.appearance.divider_visible = False
    tui.appearance.divider_color = "accent"
    tui.appearance.divider_text_color = "red"
    tui.appearance.divider_pattern = "∘₊✧"
    tui._commit_appearance("Divider", fields=(
        "divider_visible", "divider_color", "divider_text_color", "divider_pattern"
    ))
    tui._open_settings_category("divider")
    panel = tui._panel
    panel.picker.focus(row_id)
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel is panel
    assert panel.picker.selected_id == row_id
    assert tui.appearance.divider_pattern == pattern
    saved = _load_tui_appearance(tui.appearance_path)
    assert saved.divider_pattern == pattern
    assert not saved.divider_visible
    assert saved.divider_color == "accent"
    assert saved.divider_text_color == "red"
    assert [row.action.target for row in panel.page.rows if row.selected] == [
        "heavy-spaced" if pattern == "━ " else "heavy" if pattern == "━"
        else "light-spaced" if pattern == "─ " else "light"
    ]
    tui._emit("appearance_saved", (tui._appearance_save_revision, False))
    tui._before_render(None)
    assert panel.picker.selected_id == row_id
    assert tui.appearance.divider_pattern == pattern
    assert "Save unconfirmed" in "".join(text for _, text in tui._panel_footer_fragments())


@pytest.mark.parametrize("target", ["line", "text"])
def test_divider_color_reset_is_scoped_and_stays_on_page(tmp_path, target):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.appearance.divider_visible = False
    tui.appearance.divider_color = "accent"
    tui.appearance.divider_text_color = "red"
    tui.appearance.divider_pattern = "─ "
    tui._commit_appearance("Divider", fields=(
        "divider_visible", "divider_color", "divider_text_color", "divider_pattern"
    ))
    tui._open_settings_category("divider")
    tui._apply_panel_action(PanelAction("divider-colors", target))
    panel = tui._panel
    assert not any(row.label == "Default" for row in panel.page.rows)
    reset = next(row for row in panel.page.rows if row.id == "color:default")
    assert reset.display_label == "⏻ RESET TO DEFAULT"
    assert reset.footer
    panel.picker.focus(reset.id)
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel is panel
    assert panel.picker.selected_id == reset.id
    assert panel.row().value == ""
    saved = _load_tui_appearance(tui.appearance_path)
    assert saved.divider_color == ("same-as-input-field" if target == "line" else "accent")
    assert saved.divider_text_color == ("bright-black" if target == "text" else "red")
    assert saved.divider_pattern == "─ "
    assert not saved.divider_visible


def test_settings_reset_all_requires_confirmation_and_restores_parent_and_draft(tmp_path):
    tui = _fake_persistent_tui(tmp_path / "appearance.json")
    tui.appearance = TUIAppearance(theme="autumn", divider_visible=False, divider_pattern="─")
    original = tui.appearance
    revision = tui._appearance_save_revision
    tui._set_input("unsent draft")
    tui._begin_choice("settings", tui._settings_categories(), RESET_THEME_CHOICE)
    tui._accept_choice()
    assert tui._choice_kind == "settings reset confirmation"
    assert tui._panel.picker.selected_id == "cancel"
    assert tui.appearance is original
    assert tui._appearance_save_revision == revision
    assert not tui.appearance_path.exists()
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "reset-all"
    tui._accept_choice()
    tui._accept_choice()  # Cancel is the default action.
    assert tui._choice_kind == "settings"
    assert tui.appearance is original
    assert tui._appearance_save_revision == revision
    tui._accept_choice()
    tui._panel.picker.focus("confirm")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui.appearance == TUIAppearance()
    assert _load_tui_appearance(tui.appearance_path) == TUIAppearance()
    assert tui._appearance_save_revision == revision + 1
    assert tui._choice_kind == "settings"
    assert tui._panel.picker.selected_id == "reset-all"
    tui._accept_choice()
    assert tui._panel.picker.selected_id == "cancel"  # Reopening resets focus.
    tui._cancel_choice()
    tui._cancel_choice()
    assert tui.input.text == "unsent draft"


@pytest.mark.parametrize("command", ["/settings reset", "/settings reset all"])
def test_settings_reset_command_requires_confirmation(command):
    tui = _fake_persistent_tui()
    tui.appearance.divider_visible = False
    revision = tui._appearance_save_revision
    tui._set_input(command)
    tui._submit_buffer(steer=False)
    assert tui._choice_kind == "settings reset confirmation"
    assert tui._panel.picker.selected_id == "cancel"
    assert not tui.appearance.divider_visible
    assert tui._appearance_save_revision == revision


@pytest.mark.parametrize("backend,provider", [
    ("ollama", None), ("openrouter", "OpenRouter"), ("openai_api", "OpenAI"),
    ("openai_codex", "OpenAI Codex"), ("gemini_api", "Google"),
])
def test_model_panel_current_markers_follow_active_source_provider_and_model(
    monkeypatch, backend, provider
):
    tui = _fake_persistent_tui()
    active = ModelInfo(
        backend, "openrouter/free" if backend == "openrouter" else "active-model", "Active"
    )
    other = ModelInfo(backend, "other-model", "Other")
    tui.agent.model_info = active
    tui.agent.model = active.model_id
    tui._local_models = [active, other] if backend == "ollama" else []
    monkeypatch.setattr("klaude_cli.main._available_chat_models", lambda *args: [active, other])
    monkeypatch.setattr(tui, "_refresh_local_models", lambda: None)
    monkeypatch.setattr(tui, "_refresh_codex_auth_state", lambda: None)
    tui._open_model_source("settings")
    assert [(row.label, row.value) for row in tui._panel.page.rows if row.selected] == [
        ("Local" if backend == "ollama" else "Cloud", "Current")
    ]
    if provider:
        tui._open_cloud_provider()
        assert [(row.label, row.value) for row in tui._panel.page.rows if row.selected] == [
            ({"OpenAI": "OpenAI API", "Google": "Gemini API"}.get(provider, provider), "Current")
        ]
    tui._open_model_backend(backend, "cloud" if provider else "source")
    assert [(row.label, row.value) for row in tui._panel.page.rows if row.selected] == [
        (active.model_id, "Current")
    ]
    other_row = next(row for row in tui._panel.page.rows if row.label == other.model_id)
    tui._panel.picker.focus(other_row.id)
    tui._apply_picker_state()
    assert next(row for row in tui._panel.page.rows if row.selected).label == active.model_id
    assert tui.agent.model_info == active
    tui._open_model_backend("openrouter" if backend != "openrouter" else "ollama", "source")
    assert not any(row.selected for row in tui._panel.page.rows)


def test_settings_tools_summary_counts_live_registered_tools_after_toggle_and_back(tmp_path):
    tui = _fake_persistent_tui(chat_preferences_path=tmp_path / "prefs.json")
    tui.agent.tools = {"read_file": object(), "web_search": object(), "mcp_test": object()}
    tui.agent.disabled_tool_names = {"mcp_test", "not_registered"}
    tui._begin_choice("settings", tui._settings_categories(), "tools")
    assert tui._panel.row().value == "2/3 enabled"
    tui._accept_choice()
    row = next(row for row in tui._panel.page.rows if row.id == "web search")
    tui._panel.picker.focus(row.id)
    tui._apply_picker_state()
    tui._activate_panel_toggle()
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "category:tools"
    assert tui._panel.row().value == "1/3 enabled"


def test_settings_skills_count_loads_without_navigation_and_preserves_focus_and_filter():
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), "tools")
    panel = tui._panel
    skills = next(row for row in panel.page.rows if row.id == "category:skills")
    assert skills.value == "Loading…"
    assert tui._skills_inventory_loading
    panel.search_active = True
    tui._set_input("tools")
    tui._refresh_choice_filter()
    tui._emit("skills_inventory", ([{"name": "demo"}, {"name": "other"}], ""))
    tui._before_render(None)
    assert tui._panel is panel
    assert panel.picker.selected_id == "category:tools"
    assert panel.picker.query == "tools"
    skills = next(row for row in panel.page.rows if row.id == "category:skills")
    assert skills.value == "2/2 enabled"
    tui._cancel_choice()
    tui._cancel_choice()
    assert not tui._skills_inventory_loading


def test_settings_skills_empty_and_unavailable_counts_are_honest():
    tui = _fake_persistent_tui()
    tui._skills_inventory_error = "Inventory unavailable"
    page = tui._settings_home_page()
    assert next(row for row in page.rows if row.id == "category:skills").value == "Unavailable"
    tui._skills_inventory = []
    page = tui._settings_home_page()
    assert next(row for row in page.rows if row.id == "category:skills").value == "0/0 enabled"


@pytest.mark.parametrize("enabled,label", [(True, "1 saved, ON"), (False, "1 saved, OFF")])
def test_settings_memory_summary_shows_saved_count_and_flag(enabled, label):
    from klaude_cli.settings_overview import SettingsOverviewSnapshot

    tui = _fake_persistent_tui()
    tui._settings_overview_scope = tui._settings_overview_paths()
    tui._settings_overview = SettingsOverviewSnapshot().refreshed({
        "memory_enabled": enabled, "memory_count": 1, "mcp_enabled": 0, "mcp_total": 0,
    }, time.monotonic())
    row = next(row for row in tui._settings_home_page().rows if row.id == "category:memory")
    assert row.value == label


def test_appearance_parent_summaries_show_defaults_and_keep_actual_choices():
    tui = _fake_persistent_tui()
    tui.appearance = TUIAppearance()
    rows = {row.id: row for row in tui._settings_home_page().rows}
    assert rows["category:theme"].value == "Default"
    assert rows["category:input field"].value == "6-6, border"
    assert rows["category:spinner"].value == "Default, 80 ms"
    assert rows["category:divider"].value == "ON, default, default"
    tui._open_settings_category("divider")
    rows = {row.id: row for row in tui._panel.page.rows}
    assert rows["line-color"].value == rows["text-color"].value == "Default"
    tui._open_settings_category("theme")
    rows = {row.id: row for row in tui._panel.page.rows}
    assert rows["interface theme"].value == rows["text/code theme"].value == "Default"
    tui.appearance.theme = "autumn"
    tui.appearance.text_theme = "monokai"
    tui.appearance.divider_color = "red"
    tui.appearance.divider_text_color = "accent"
    rows = {row.id: row for row in tui._settings_home_page().rows}
    assert rows["category:theme"].value == "Autumn, Monokai"
    assert rows["category:divider"].value == "ON, red, accent"


def test_settings_input_and_divider_summaries_show_live_values_without_comments(tmp_path):
    tui = _fake_persistent_tui(appearance_path=tmp_path / "appearance.json")
    tui.appearance.divider_text_color = "bright-black"
    rows = {row.id: row for row in tui._settings_home_page().rows}
    assert rows["category:input field"].value == "6-6, border"
    assert rows["category:input field"].description == ""
    assert rows["category:divider"].value == "ON, default, default"
    assert rows["category:divider"].description == ""
    tui.appearance.input_border = False
    tui.appearance.input_height = 4
    tui.appearance.input_max_height = 6
    tui.appearance.divider_visible = False
    rows = {row.id: row for row in tui._settings_home_page().rows}
    assert rows["category:input field"].value == "4-6, no border"
    assert rows["category:divider"].value == "OFF, default, default"


@pytest.mark.parametrize("truncated,prefix", [(False, ""), (True, "At least ")])
def test_mcp_page_heading_shows_installed_and_enabled_counts(truncated, prefix):
    tui = _fake_persistent_tui()
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    tui._mcp_inventory = {"servers": [
        {"name": "one", "enabled": True, "oauth": False, "transport": "http", "tool_count": 2},
        {"name": "two", "enabled": False, "oauth": False, "transport": "stdio", "tool_count": 0},
    ], "truncated": truncated}
    tui._open_settings_category("mcp servers")
    heading = next(row for row in tui._panel.page.rows if row.label == "MCP Servers")
    assert heading.description.startswith(
        prefix + "2 installed, 1 enabled · Configuration snapshot "
    )


def test_settings_conventions_use_scoped_reset_and_footer_only_persistence(monkeypatch):
    monkeypatch.setattr("klaude_cli.main.shutil.which", lambda name: "/usr/bin/nano")
    tui = _fake_persistent_tui()
    tui._runtime_device_mode = "auto"
    reset = next(row for row in tui._settings_home_page().rows if row.id == "reset-all")
    assert reset.display_label == "⏻ RESET APPEARANCE SETTINGS"
    tui._runtime_save_state = "saved"
    tui._open_settings_category("runtime")
    assert "Saved" in "".join(text for _, text in tui._panel_footer_fragments())
    assert not any("saved" in row.label.lower() for row in tui._panel.page.rows)
    device = next(row for row in tui._panel.page.rows if row.id == "device")
    assert device.value == "Auto"
    editor = next(row for row in tui._panel.page.rows if row.id == "edit config.toml (nano)")
    assert editor.label == "Edit configuration"
    tui._open_settings_category("tools")
    assert not any(row.label.lower().startswith("provider ") for row in tui._panel.page.rows)
    assert not any("saved" in row.label.lower() for row in tui._panel.page.rows)
    tui._memory_save_state = "saved"
    tui._open_settings_category("memory")
    assert not any("preference saved" in row.label.lower() for row in tui._panel.page.rows)
    assert "Saved" in "".join(text for _, text in tui._panel_footer_fragments())


@pytest.mark.parametrize("input_field, expected", [
    ({}, (6, 6)),
    ({"min_height": 8, "max_height": 12}, (8, 12)),
    ({"height": 8}, (8, 12)),
    ({"min_height": 9, "max_height": 2}, (6, 6)),
])
def test_input_height_defaults_preserve_explicit_and_legacy_ranges(tmp_path, input_field, expected):
    path = tmp_path / "appearance.json"
    path.write_text(json.dumps({"input_field": input_field}))
    appearance = _load_tui_appearance(path)
    assert (appearance.input_height, appearance.input_max_height) == expected
    default = TUIAppearance()
    assert (default.input_height, default.input_max_height) == (6, 6)


@pytest.mark.parametrize("mcp", [False, True])
def test_space_cycles_individual_permission_policies_and_preserves_focus(tmp_path, mcp):
    from klaude_core.mcp_client import namespaced_tool_name

    async def exercise():
        path = tmp_path / "permissions.json"
        tui = _fake_persistent_tui(chat_preferences_path=path)
        if mcp:
            name = namespaced_tool_name("context7", "get_docs")
            tui.agent.tools = {name: SimpleNamespace(description="MCP server context7: get_docs")}
            tui._open_mcp_permission_server("context7")
            row_id = f"mcp-tool:{name}"
        else:
            name = "write_file"
            tui._open_settings_category("permissions")
            row_id = f"tool:{name}"
        tui._panel.picker.focus(row_id)
        tui._apply_picker_state()
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                for policy in ("allow", "deny", "ask"):
                    pipe.send_text(" ")
                    await asyncio.sleep(0.05)
                    assert tui.agent.gate.policies[name] == policy
                    assert json.loads(path.read_text())["permissions"][name] == policy
                    assert tui._panel.picker.selected_id == row_id
                    assert not tui._panel.search_active
                pipe.send_text("/get docs" if mcp else "/write file")
                await asyncio.sleep(0.05)
                assert " " in tui._panel.picker.query
                assert tui.agent.gate.policies[name] == "ask"
            finally:
                tui.application.exit()
                await task

    asyncio.run(exercise())


@pytest.mark.parametrize("category, first", [("divider", "visible"), ("spinner", "custom")])
def test_appearance_page_reentry_starts_at_first_option_after_back(category, first):
    tui = _fake_persistent_tui()
    tui._begin_choice("settings", tui._settings_categories(), category)
    tui._accept_choice()
    assert tui._panel.picker.selected_id == first
    tui._panel.picker.focus("back")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "settings"
    tui._accept_choice()
    assert tui._panel.picker.selected_id == first
    assert tui._panel.picker.query == ""


@pytest.mark.parametrize("arguments", ["-lsha ~", "~ -lsha"])
def test_ls_expands_home_with_flags_in_either_order(tmp_path, monkeypatch, arguments):
    from klaude_cli.main import _list_agent_directory

    home = tmp_path / "home"
    home.mkdir()
    (home / ".hidden-file").write_text("test")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    agent = SimpleNamespace(workdir=workspace)
    ok, output = _list_agent_directory(agent, arguments)
    assert ok, output
    assert ".hidden-file" in output
    assert agent.workdir == workspace


def test_ls_quoted_paths_and_option_terminator_are_literal(tmp_path):
    from klaude_cli.main import _list_agent_directory

    directory = tmp_path / "folder with spaces"
    directory.mkdir()
    (directory / "example.txt").write_text("test")
    agent = SimpleNamespace(workdir=tmp_path)
    ok, output = _list_agent_directory(agent, '-a "folder with spaces"')
    assert ok, output
    assert "example.txt" in output
    (tmp_path / "-literal").mkdir()
    (tmp_path / "-literal" / "safe.txt").write_text("test")
    ok, output = _list_agent_directory(agent, "-- -literal")
    assert ok, output
    assert "safe.txt" in output
    ok, output = _list_agent_directory(agent, '"unterminated')
    assert not ok
    assert "invalid ls arguments" in output


def test_mcp_remove_settings_confirmation_cancel_and_submit(tmp_path, monkeypatch):
    from klaude_cli.mcp_mutations import MCPMutationResult, MCPRemove

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._mcp_inventory = {"servers": [{
        "name": "docs", "enabled": False, "transport": "http", "oauth": False,
        "tool_count": 0, "fingerprint": "a" * 64,
    }], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    requests = []
    tui._mcp_mutations = SimpleNamespace(path=tui.cfg.mcp_servers_file,
                                       submit=lambda request: requests.append(request) or True)
    tui._open_settings_category("mcp servers")
    assert "Manage" in tui._choice_values
    tui._panel.picker.focus(next(row.id for row in tui._panel.page.rows
                                if row.label == "Manage installed"))
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "mcp manage list"
    tui._panel.picker.focus("server:docs")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "mcp manage detail"
    tui._panel.picker.focus("delete")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.picker.selected_id == "cancel"
    assert requests == []
    tui._cancel_choice()
    assert tui._choice_kind == "mcp manage detail"
    tui._panel.picker.focus("delete")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.picker.selected_id == "cancel"
    tui._panel.picker.focus("remove")
    tui._apply_picker_state()
    tui._accept_choice()
    assert len(requests) == 1
    assert isinstance(requests[0], MCPRemove)
    assert requests[0].name == "docs" and requests[0].fingerprint == "a" * 64
    assert tui._choice_kind == "mcp manage list"
    assert not tui.status_error
    assert ("class:panel.status.neutral", "Removing MCP server docs…") in (
        tui._panel_footer_fragments()
    )
    published = []
    monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *catalog: published.append(catalog))
    catalog = ([], None)
    tui._events.put(("mcp_mutation_saved", MCPMutationResult(
        requests[0], str(tui.cfg.mcp_servers_file), "saved", catalog,
    )))
    tui._before_render(tui.application)
    assert published == [catalog]
    assert tui._mcp_mutation_pending is None
    assert "Removed MCP server docs" in tui.output.text


def test_mcp_manage_refresh_preserves_filter_focus_and_page(tmp_path):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    first = {"name": "docs", "enabled": True, "transport": "http", "oauth": False,
             "tool_count": 2, "fingerprint": "a" * 64,
             "source_label": "MCP Registry metadata", "description": "Old description"}
    tui._mcp_inventory = {"servers": [first], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._open_settings_category("mcp servers")
    tui._apply_panel_action(PanelAction("mcp-manage"))
    assert tui._panel.picker.selected_id == "server:docs"
    tui._panel.search_active = True
    tui._set_input("docs")
    tui._refresh_choice_filter()
    tui._panel.picker.focus("server:docs")
    tui._apply_picker_state()
    identity = tui._background_jobs.latest["mcp-inventory"]
    updated = {**first, "description": "New description"}
    tui._apply_background_result(("mcp-inventory", identity, {
        "servers": [updated], "truncated": False,
    }, ""))
    assert tui._choice_kind == "mcp manage list"
    assert tui._panel.picker.selected_id == "server:docs"
    assert tui._panel.picker.query == "docs"
    assert tui._panel.row().description == "New description"
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "MCPs", "Manage", "docs")
    tui._cancel_choice()
    assert tui._panel.picker.selected_id == "server:docs"
    assert tui._panel.picker.query == "docs"


def test_mcp_manage_enable_review_returns_to_server_detail(tmp_path, monkeypatch):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._mcp_inventory = {"servers": [{
        "name": "docs", "enabled": False, "transport": "http", "oauth": False,
        "tool_count": 0, "fingerprint": "a" * 64,
        "source_label": "Local configuration", "description": "",
    }], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    tui._open_settings_category("mcp servers")
    tui._apply_panel_action(PanelAction("mcp-manage"))
    tui._apply_panel_action(PanelAction("mcp-manage-detail", "docs"))
    monkeypatch.setattr(tui, "_review_mcp_server", lambda _name: tui._begin_choice(
        "mcp review", ["Reviewing…", "back"], "back"
    ))
    tui._apply_panel_action(PanelAction("mcp-manage-toggle", "docs"))
    assert tui._choice_kind == "mcp review"
    tui._cancel_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "MCPs", "Manage", "docs")
    assert tui._panel.picker.selected_id == "enabled"


def test_manage_update_controls_explain_unsupported_source_updates(tmp_path):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._skills_inventory = [{"name": "demo", "identity": "id", "enabled": True}]
    tui._skill_inbox_preparation_attempted = True
    tui._open_settings_category("skills")
    tui._apply_panel_action(PanelAction("skill-manage"))
    tui._panel.picker.focus("update-all")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skills manage list"
    assert not tui.status_error
    assert ("class:panel.status.warning", "No verified upstream update sources") in (
        tui._panel_footer_fragments()
    )
    tui._apply_panel_action(PanelAction("skill-manage-detail", "demo"))
    tui._panel.picker.focus("update")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skills manage detail"
    assert not tui.status_error
    assert ("class:panel.status.warning", "No verified upstream update source") in (
        tui._panel_footer_fragments()
    )


def test_mcp_manage_update_requires_review_then_disables_server(tmp_path):
    from klaude_cli.mcp_mutations import MCPUpdateDisabled
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    fingerprint = "a" * 64
    tui._mcp_inventory = {"servers": [{
        "name": "docs", "enabled": True, "transport": "stdio", "oauth": False,
        "tool_count": 1, "fingerprint": fingerprint,
        "source_label": "MCP Registry metadata", "description": "Documentation MCP",
        "update_kind": "registry-package",
    }], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    accepted = []
    tui._mcp_mutations = SimpleNamespace(
        path=tui.cfg.mcp_servers_file,
        submit=lambda request: accepted.append(request) or True,
    )
    tui._open_settings_category("mcp servers")
    tui._apply_panel_action(PanelAction("mcp-manage"))
    tui._apply_panel_action(PanelAction("mcp-manage-detail", "docs"))
    tui._apply_panel_action(PanelAction("mcp-manage-update", "docs"))
    assert accepted == []
    request = tui._background_jobs.requests["mcp-update-check"]
    assert request["fingerprint"] == fingerprint
    identity = tui._background_jobs.latest["mcp-update-check"]
    candidate = {"old_arg": "@example/docs@1.2.3",
                 "new_arg": "@example/docs@1.2.4", "old_version": "1.2.3",
                 "new_version": "1.2.4", "registry_version": "1.2.4",
                 "description": "New documentation MCP"}
    tui._apply_background_result(("mcp-update-check", identity, {
        "name": "docs", "fingerprint": fingerprint,
        "status": "available", "candidate": candidate,
    }, ""))
    assert tui._choice_kind == "mcp manage update"
    assert tui._panel.picker.selected_id == "back"
    tui._apply_panel_action(PanelAction("mcp-manage-update-confirm", "docs"))
    assert len(accepted) == 1 and isinstance(accepted[0], MCPUpdateDisabled)
    assert accepted[0].new_arg == "@example/docs@1.2.4"
    assert tui._choice_kind == "mcp manage detail"


def test_mcp_update_all_reviews_and_serializes_disabled_updates(tmp_path, monkeypatch):
    from klaude_cli.mcp_mutations import MCPMutationResult, MCPUpdateDisabled
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    names = ("alpha", "beta")
    tui._mcp_inventory = {"servers": [{
        "name": name, "enabled": True, "transport": "stdio", "oauth": False,
        "tool_count": 1, "fingerprint": char * 64,
        "source_label": "MCP Registry metadata", "description": "Example",
        "update_kind": "registry-package",
    } for name, char in zip(names, "ab", strict=True)], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    accepted = []
    tui._mcp_mutations = SimpleNamespace(
        path=tui.cfg.mcp_servers_file,
        submit=lambda request: accepted.append(request) or True,
    )
    monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *_: None)
    tui._open_settings_category("mcp servers")
    tui._apply_panel_action(PanelAction("mcp-manage"))
    tui._apply_panel_action(PanelAction("mcp-manage-update-all"))
    request = tui._background_jobs.requests["mcp-update-all-check"]
    assert [item["name"] for item in request["items"]] == list(names)
    identity = tui._background_jobs.latest["mcp-update-all-check"]
    result = {"items": [{
        "name": name, "fingerprint": char * 64, "status": "available",
        "candidate": {"old_arg": f"@example/{name}@1.2.3",
                      "new_arg": f"@example/{name}@1.2.4",
                      "old_version": "1.2.3", "new_version": "1.2.4",
                      "registry_version": "1.2.4", "description": "Updated"},
    } for name, char in zip(names, "ab", strict=True)]}
    tui._apply_background_result(("mcp-update-all-check", identity, result, ""))
    assert tui._choice_kind == "mcp manage update all"
    assert tui._panel.picker.selected_id == "back"
    tui._apply_panel_action(PanelAction("mcp-manage-update-all-confirm"))
    assert len(accepted) == 1 and isinstance(accepted[0], MCPUpdateDisabled)
    tui._events.put(("mcp_mutation_saved", MCPMutationResult(
        accepted[0], str(tui.cfg.mcp_servers_file), "saved", ([], None),
    )))
    tui._before_render(tui.application)
    assert [item.name for item in accepted] == list(names)
    assert tui._mcp_mutation_pending[0] == accepted[1]
    tui._events.put(("mcp_mutation_saved", MCPMutationResult(
        accepted[1], str(tui.cfg.mcp_servers_file), "saved", ([], None),
    )))
    tui._before_render(tui.application)
    assert tui._mcp_mutation_pending is None
    assert tui._mcp_update_all_total == 0


def test_skill_update_all_reviews_and_serializes_remote_updates(tmp_path):
    from klaude_cli.settings_panel import PanelAction
    from klaude_core.skill_catalog import SkillRecord

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._skill_inbox_preparation_attempted = True
    names = ("alpha", "beta")
    tui._skills_inventory = [{
        "name": name, "identity": char * 64, "enabled": True,
        "update_kind": "github", "source_label": "GitHub · org/repo",
    } for name, char in zip(names, "ab", strict=True)]
    tui._skills_inventory_loaded_at = time.monotonic()
    accepted = []
    tui._skill_actions.submit = lambda action: accepted.append(action) or True
    tui._open_settings_category("skills")
    tui._apply_panel_action(PanelAction("skill-manage"))
    tui._apply_panel_action(PanelAction("skill-update-all"))
    request = tui._background_jobs.requests["skill-update-all-check"]
    assert [item["name"] for item in request["items"]] == list(names)
    identity = tui._background_jobs.latest["skill-update-all-check"]
    records = [SkillRecord(
        "skillsmp", f"installed:org/repo:{name}/SKILL.md", name,
        repository="org/repo", skill_path=f"{name}/SKILL.md",
        source_url=f"https://github.com/org/repo/blob/{char * 40}/{name}/SKILL.md",
        revision=char * 40,
    ) for name, char in zip(names, "cd", strict=True)]
    result = {"items": [{
        "name": name, "identity": char * 64, "status": "available",
        "current_revision": "e" * 40, "record": record.payload(),
    } for (name, char), record in zip(zip(names, "ab", strict=True), records, strict=True)]}
    tui._apply_background_result(("skill-update-all-check", identity, result, ""))
    assert tui._choice_kind == "skill update all review"
    assert tui._panel.picker.selected_id == "back"
    tui._apply_panel_action(PanelAction("skill-update-all-confirm"))
    assert len(accepted) == 1 and accepted[0].name == "alpha"
    assert tui._panel.picker.selected_id == "update-all"
    tui._events.put(("skill_action_done", (accepted[0], True, "Updated alpha")))
    tui._before_render(tui.application)
    assert [item.name for item in accepted] == list(names)
    tui._events.put(("skill_action_done", (accepted[1], True, "Updated beta")))
    tui._before_render(tui.application)
    assert not tui._skill_action_pending
    assert tui._skill_update_all_total == 0


def test_skill_manage_update_checks_source_then_requires_review(tmp_path):
    from klaude_cli.settings_panel import PanelAction
    from klaude_core.skill_catalog import SkillRecord

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._skill_inbox_preparation_attempted = True
    current, latest = "a" * 40, "b" * 40
    tui._skills_inventory = [{
        "name": "demo", "identity": "c" * 64, "enabled": True,
        "update_kind": "github", "source_label": "GitHub · org/repo",
    }]
    tui._skills_inventory_loaded_at = time.monotonic()
    accepted = []
    tui._skill_actions.submit = lambda action: accepted.append(action) or True
    tui._open_settings_category("skills")
    tui._apply_panel_action(PanelAction("skill-manage"))
    tui._apply_panel_action(PanelAction("skill-manage-detail", "demo"))
    tui._apply_panel_action(PanelAction("skill-update", "demo"))
    assert accepted == []
    request = tui._background_jobs.requests["skill-update-check"]
    assert request["name"] == "demo" and request["identity"] == "c" * 64
    record = SkillRecord(
        "skillsmp", "installed:org/repo:demo/SKILL.md", "demo",
        repository="org/repo",
        source_url=f"https://github.com/org/repo/blob/{latest}/demo/SKILL.md",
        skill_path="demo/SKILL.md", revision=latest, license="MIT",
    )
    identity = tui._background_jobs.latest["skill-update-check"]
    tui._apply_background_result(("skill-update-check", identity, {
        "name": "demo", "identity": "c" * 64, "status": "available",
        "current_revision": current, "record": record.payload(),
    }, ""))
    assert tui._panel.page.breadcrumb[-1] == "Review update"
    assert tui._panel.picker.selected_id == "back"
    assert accepted == []
    tui._panel.picker.focus("confirm")
    tui._apply_picker_state()
    tui._accept_choice()
    assert len(accepted) == 1
    assert accepted[0].kind == "update-remote"
    assert accepted[0].expected_manifest_identity == "c" * 64
    assert accepted[0].record == record
    assert tui._choice_kind == "skills manage list"


def test_skills_and_mcp_manage_back_restore_parent_focus():
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui()
    tui._skill_inbox_preparation_attempted = True
    tui._skills_inventory = [{"name": "demo", "identity": "id", "enabled": True}]
    tui._open_settings_category("skills")
    tui._apply_panel_action(PanelAction("skill-manage"))
    tui._cancel_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "Skills")
    assert tui._panel.picker.selected_id == "manage"

    tui._mcp_inventory = {"servers": [], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    tui._open_settings_category("mcp servers")
    tui._apply_panel_action(PanelAction("mcp-manage"))
    tui._cancel_choice()
    assert tui._panel.page.breadcrumb == ("Settings", "MCPs")
    assert tui._panel.picker.selected_id == "manage"


def test_mcp_actions_order_and_nonselectable_gap_before_servers():
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui()
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    tui._mcp_inventory = {"servers": [{
        "name": "docs", "enabled": True, "transport": "http", "oauth": False,
        "tool_count": 2, "fingerprint": "a" * 64,
    }], "truncated": False}
    tui._open_settings_category("mcp servers")
    rows = tui._panel.page.rows
    start = next(index for index, row in enumerate(rows) if row.label == "MCP Servers")
    assert [row.id for row in rows[start + 1:start + 6]] == [
        "manage", "search", "custom", "import", "permissions",
    ]
    assert not any(row.label == "Reload" for row in rows)
    assert not any(row.label == "docs" for row in rows)
    tui._apply_panel_action(PanelAction("mcp-manage"))
    manage_rows = tui._panel.page.rows
    assert [row.label for row in manage_rows[:5]] == [
        "MCP SERVERS", "Filter", "Refresh list", "Refresh tools", "Check for updates",
    ]


def test_mcp_manage_reload_stays_near_update_all_after_ack(tmp_path, monkeypatch):
    from klaude_cli.mcp_mutations import MCPMutationResult, MCPReload
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    tui._mcp_inventory = {"servers": [], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    requests = []
    tui._mcp_mutations = SimpleNamespace(
        path=tui.cfg.mcp_servers_file,
        submit=lambda request: requests.append(request) or True,
    )
    monkeypatch.setattr(tui, "_publish_mcp_tools", lambda *_: None)
    tui._open_settings_category("mcp servers")
    tui._apply_panel_action(PanelAction("mcp-manage"))
    tui._panel.picker.focus("reload")
    tui._apply_picker_state()
    tui._accept_choice()
    assert len(requests) == 1 and isinstance(requests[0], MCPReload)
    assert tui._choice_kind == "mcp manage list"
    assert tui._panel.picker.selected_id == "reload"
    assert ("class:panel.status.neutral", "Reloading configured MCP tools…") in (
        tui._panel_footer_fragments()
    )
    tui._events.put(("mcp_mutation_saved", MCPMutationResult(
        requests[0], str(tui.cfg.mcp_servers_file), "loaded", ([], None),
    )))
    tui._before_render(tui.application)
    assert tui._panel.picker.selected_id == "reload"
    assert tui._mcp_mutation_pending is None
    assert ("class:panel.saved", "Saved") in tui._panel_footer_fragments()


@pytest.mark.parametrize("domain", ["skills", "mcp"])
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("outcome,tone", [
    ("current", "success"), ("unavailable", "error"),
    ("invalid", "error"), ("unsupported", "warning"),
])
def test_manage_update_feedback_colors_follow_outcomes(
    tmp_path, monkeypatch, domain, batch, outcome, tone,
):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    monkeypatch.setattr(tui, "_panel_width", lambda: 180)
    tui._skill_inbox_preparation_attempted = True
    identity = "a" * 64
    if domain == "skills":
        tui._skills_inventory = [{
            "name": "demo", "identity": identity, "enabled": True, "update_kind": "github",
        }]
        tui._skills_inventory_loaded_at = time.monotonic()
        tui._open_skills_manage()
        if not batch:
            tui._open_skill_manage_detail("demo")
        action = "skill-update-all" if batch else "skill-update"
        key = "skill-update-all-check" if batch else "skill-update-check"
        item = {"name": "demo", "identity": identity, "status": outcome}
    else:
        tui._mcp_inventory = {"servers": [{
            "name": "demo", "fingerprint": identity, "enabled": True,
            "transport": "stdio", "tool_count": 1, "update_kind": "registry-package",
        }], "truncated": False}
        tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
        tui._mcp_inventory_loaded_at = time.monotonic()
        tui._open_mcp_manage()
        if not batch:
            tui._open_mcp_manage_detail("demo")
        action = "mcp-manage-update-all" if batch else "mcp-manage-update"
        key = "mcp-update-all-check" if batch else "mcp-update-check"
        item = {"name": "demo", "fingerprint": identity, "status": outcome}
    tui._apply_panel_action(PanelAction(action, "demo"))
    footer = tui._panel_footer_fragments()
    assert any(style == "class:panel.status.neutral" and text.startswith("Checking")
               for style, text in footer)
    assert not tui.status_error
    if outcome == "invalid":
        item["status"] = "available"  # Missing required source/package metadata.
    result = {"items": [item]} if batch else item
    tui._apply_background_result((
        key, tui._background_jobs.latest[key], result,
        "timeout" if outcome == "unavailable" else "",
    ))
    footer = tui._panel_footer_fragments()
    assert any(style == f"class:panel.status.{tone}" and text for style, text in footer)
    assert "Checking" not in "".join(text for _, text in footer)
    if outcome == "current" and batch:
        expected = "All verified Skills are current" if domain == "skills" else (
            "All verified MCP packages are current"
        )
        assert ("class:panel.status.success", expected) in footer
    if domain == "skills" and not batch:
        row = tui._panel.row("feedback")
        assert row is not None and row.status_tone == tone
        assert any(f"class:panel.status.{tone}" in style and row.label in text
                   for line in tui._panel_body().lines for style, text in line)
    if domain == "mcp":
        if batch:
            tui._open_mcp_manage()
        else:
            tui._open_mcp_manage_detail("demo")
    else:
        if batch:
            tui._open_skills_manage()
        else:
            tui._open_skill_manage_detail("demo")
    assert tui._panel_footer_fragments() == footer  # Same-page refresh retains the outcome.
    tui._open_settings_category("theme")
    assert not tui._panel_feedback
    assert not any(style == f"class:panel.status.{tone}" and text
                   for style, text in tui._panel_footer_fragments())


@pytest.mark.parametrize("success,tone", [
    (True, "success"), (False, "error"), (True, "warning"), (False, "warning"),
])
def test_skill_action_feedback_uses_acknowledgement_outcome(tmp_path, monkeypatch, success, tone):
    from klaude_cli.settings_panel import PanelAction

    tui = _fake_persistent_tui(tmp_path / "appearance.json", tmp_path / "prefs.json")
    monkeypatch.setattr(tui, "_panel_width", lambda: 180)
    tui._skills_inventory = [{"name": "demo", "identity": "id", "enabled": True}]
    tui._skills_inventory_loaded_at = time.monotonic()
    accepted = []
    tui._skill_actions.submit = lambda action: accepted.append(action) or True
    tui._open_skill_manage_detail("demo")
    tui._apply_panel_action(PanelAction("skill-toggle", "demo"))
    assert ("class:panel.muted", "Saving…") in tui._panel_footer_fragments()
    # Wording deliberately does not match any old success-message prefix.
    tui._events.put(("skill_action_done", (accepted[0], success, "Operation outcome", tone)))
    tui._before_render(tui.application)
    assert (f"class:panel.status.{tone}", "Operation outcome") in tui._panel_footer_fragments()


def test_panel_footer_separates_save_warning_from_error_and_neutral_text(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr(tui, "_panel_width", lambda: 180)
    tui._open_settings_category("tools")
    tui._runtime_save_state = "failed"
    tui.status_error = "Disk write failed"
    footer = tui._panel_footer_fragments()
    assert ("class:panel.warning", "Save unconfirmed") in footer
    assert ("class:panel.error", "Disk write failed") in footer
    tui._runtime_save_state = ""
    assert ("class:panel.error", "Disk write failed") in tui._panel_footer_fragments()
    tui.status_error = ""
    tui._set_panel_feedback("Checking sources…")
    assert ("class:panel.status.neutral", "Checking sources…") in tui._panel_footer_fragments()


def test_panel_feedback_styles_use_semantic_colors():
    from klaude_cli.main import DEFAULT_TEXT_THEME, _tui_style

    style = _tui_style("claude", DEFAULT_TEXT_THEME)

    def color(name):
        return style.get_attrs_for_style_str(f"class:{name}").color

    assert color("panel.warning") == color("panel.status.warning") == "f3c84b"
    assert color("panel.saved") == color("panel.status.success")
    assert color("panel.error") == color("panel.status.error")
    assert color("panel.muted") == color("panel.status.neutral")
    assert len({color(f"panel.status.{tone}")
                for tone in ("neutral", "success", "warning", "error")}) == 4


def test_skill_drop_inventory_shows_files_without_importing_and_preserves_focus():
    tui = _fake_persistent_tui()
    tui._skills_inventory = [{
        "name": "demo", "library": "demo", "indexed_file_count": 1, "identity": "id",
    }]
    requests = []
    tui._skill_actions.submit = lambda request: requests.append(request) or True
    tui._open_settings_category("skills")
    tui._panel.picker.focus("manage")
    tui._apply_picker_state()
    tui._events.put(("skill_drop_inventory", ("file.zip", "file2.zip")))
    tui._before_render(tui.application)
    assert tui._panel.picker.selected_id == "manage"
    assert requests == []
    rendered = "".join(text for line in tui._panel_body().lines for _, text in line)
    assert "2 files ready to import" in rendered
    assert "file.zip" not in rendered and "file2.zip" not in rendered
    tui._panel.picker.focus("import")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skills import" and requests == []
    rendered = "".join(text for line in tui._panel_body().lines for _, text in line)
    assert "Detected 2 new skill files" in rendered
    assert "Press Import skills to start importing" in rendered
    assert "- file.zip" in rendered and "- file2.zip" in rendered
    tui._accept_choice()
    assert len(requests) == 1 and requests[0].kind == "import"


def test_skills_discovery_reload_and_delete_navigation_preserve_safety():
    tui = _fake_persistent_tui()
    tui._skills_inventory = [{"name": "demo", "library": "demo", "identity": "reviewed"}]
    tui._skills_inventory_loaded_at = time.monotonic()
    requests = []
    tui._skill_actions.submit = lambda action: requests.append(action) or True
    tui._open_settings_category("skills")
    assert tui._panel.page.rows[0].label == "SKILLS"
    tui._panel.picker.focus("search")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skill discovery" and requests == []
    tui._cancel_choice()
    assert tui._choice_kind == "skills settings"
    assert not any(row.id == "reload" for row in tui._panel.page.rows)
    tui._panel.picker.focus("manage")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skills manage list"
    assert [row.label for row in tui._panel.page.rows[:4]] == [
        "MANAGE SKILLS", "Filter", "Refresh list", "Check for updates",
    ]
    tui._panel.picker.focus("reload")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._skills_inventory_loading
    assert tui._panel.picker.selected_id == "reload"
    assert requests == []
    assert tui._choice_kind == "skills manage list"
    assert tui._panel.page.breadcrumb == ("Settings", "Skills", "Manage")
    tui._panel.picker.focus("skill:demo")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skills manage detail"
    tui._panel.picker.focus("delete")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb[-1] == "Confirm deletion"
    assert tui._panel.picker.selected_id == "back"
    assert requests == []
    tui._accept_choice()
    assert tui._choice_kind == "skills manage detail"
    tui._cancel_choice()
    assert tui._choice_kind == "skills manage list"
    assert tui._panel.picker.selected_id == "skill:demo"


def test_skill_discovery_jobs_are_read_only_and_back_restores_panel_state(monkeypatch):
    from klaude_cli.settings_panel import PanelAction
    from klaude_core.skill_catalog import CatalogStatus, SearchResult, SkillRecord

    tui = _fake_persistent_tui()
    tui._skills_inventory = []
    tui._skills_inventory_loaded_at = time.monotonic()
    tui._set_input("unsent draft")
    writes = []
    tui._skill_actions.submit = lambda action: writes.append(action) or True
    submitted = []
    monkeypatch.setattr(tui._background_jobs, "submit", lambda key, request, **_: (
        submitted.append((key, request)) or str(len(submitted))))
    monkeypatch.setattr(tui._background_jobs, "current", lambda *_: True)
    monkeypatch.setattr(tui, "_append", lambda *_: pytest.fail("Discovery rewrote transcript"))
    tui._open_settings_category("skills")
    tui._panel.picker.focus("search")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skill discovery"
    assert not submitted and not writes
    tui._accept_choice()  # Query uses the existing private settings editor.
    assert tui._settings_input_request["on_submit"] == ("skill-search-query",)
    assert tui._settings_input_is_single_line()
    tui._set_input("python")
    tui._submit_settings_input_response()
    assert submitted == [("skill-search", {"kind": "skill_search", "request": {
        "query": "python", "provider": "skillsmp", "sort": "stars", "page": 1}})]
    record = SkillRecord("skillsmp", "one", "test", "Useful source text", repository="org/repo")
    tui._apply_background_result(("skill-search", "1", SearchResult(
        CatalogStatus.OK, (record,), fetched_at=time.time()).payload(), ""))
    panel = tui._panel
    panel.picker.focus(record.identity)
    panel.scroll_top = 2
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._choice_kind == "skill discovery detail"
    assert "Unknown" in "".join(text for _, text in tui._panel_body_fragments())
    tui._cancel_choice()
    assert tui._panel is panel and panel.picker.selected_id == record.identity
    assert panel.scroll_top == 2
    tui._cancel_choice()
    assert tui._choice_kind == "skills settings" and tui._panel.picker.selected_id == "search"
    assert not writes
    tui._cancel_choice()
    tui._cancel_choice()
    assert tui.input.text == "unsent draft"
    assert len([key for key, _request in submitted if key == "skill-search"]) == 1
    assert not tui.application.full_screen
    assert tui._skill_discovery.action(PanelAction("unrelated")) is False


def test_resolved_skill_install_needs_confirmation_and_keeps_discovery_open():
    from klaude_cli.settings_panel import PanelAction
    from klaude_cli.skill_discovery import DETAIL_KIND, INSTALL_KIND
    from klaude_core.skill_catalog import SkillRecord

    tui = _fake_persistent_tui()
    record = SkillRecord(
        "skillsmp", "one", "example", repository="org/repo",
        source_url="https://github.com/org/repo/tree/main/skills/example",
        skill_path="skills/example/SKILL.md", revision="a" * 40,
    )
    submitted = []
    tui._skill_actions.submit = lambda action: submitted.append(action) or True
    tui._skill_discovery.detail = record
    tui._skill_discovery.show_detail()
    tui._apply_panel_action(PanelAction("discover-install"))
    assert tui._choice_kind == INSTALL_KIND and tui._panel.picker.selected_id == "back"
    assert submitted == []
    tui._apply_panel_action(PanelAction("discover-confirm-install"))
    assert len(submitted) == 1 and submitted[0].record == record
    assert tui._choice_kind == DETAIL_KIND
    assert next(row for row in tui._panel.page.rows if row.id == "install-status").label == (
        "Installing…"
    )
    tui._events.put(("skill_action_done", (submitted[0], True, "Installed example")))
    tui._before_render(tui.application)
    assert tui._choice_kind == DETAIL_KIND
    assert next(row for row in tui._panel.page.rows if row.id == "install").label == "Installed"


def test_skill_discovery_source_switch_keeps_focus_after_cached_return():
    from klaude_cli.settings_panel import PanelAction
    from klaude_core.skill_catalog import CatalogStatus, SearchResult, SkillRecord

    tui = _fake_persistent_tui()
    tui._skill_discovery.search("frontend design")
    key = tui._background_jobs.latest["skill-search"]
    tui._apply_background_result(("skill-search", key, SearchResult(
        CatalogStatus.OK, (SkillRecord("skillsmp", "one", "frontend-design"),),
        fetched_at=time.time(),
    ).payload(), ""))

    tui._apply_panel_action(PanelAction("discover-provider"))
    assert tui._panel.picker.selected_id == "provider"
    key = tui._background_jobs.latest["skill-search"]
    tui._apply_background_result(("skill-search", key, SearchResult(
        CatalogStatus.OK, (SkillRecord("skills.sh", "one", "frontend-design"),),
        fetched_at=time.time(),
    ).payload(), ""))
    assert tui._panel.picker.selected_id == "provider"

    tui._apply_panel_action(PanelAction("discover-provider"))
    assert tui._panel.picker.selected_id == "provider"
    assert tui._skill_discovery.result.records[0].provider == "skillsmp"


@pytest.mark.parametrize("width", [24, 70, 120])
def test_skill_discovery_live_keyboard_resize_filter_cancel_and_background_work(width, monkeypatch):
    from klaude_core.skill_catalog import CatalogStatus, SearchResult, SkillRecord
    from prompt_toolkit.data_structures import Size

    async def exercise():
        tui = _fake_persistent_tui()
        tui._skills_inventory = []
        tui._skills_inventory_loaded_at = time.monotonic()
        tui._set_input("retained draft")
        before = list(tui.agent.messages)
        tui.running = True
        tui.pending.append("queued work")
        submitted = []
        monkeypatch.setattr(tui._background_jobs, "submit", lambda key, request, **_: (
            submitted.append((key, request)) or str(len(submitted))))
        monkeypatch.setattr(tui._background_jobs, "current", lambda *_: True)
        tui._open_settings_category("skills")
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            columns = [width]
            monkeypatch.setattr(tui.application.output, "get_size", lambda: Size(
                rows=30, columns=columns[0]))
            task = asyncio.create_task(tui.application.run_async())

            async def wait_until(predicate):
                for _ in range(60):
                    if predicate():
                        return
                    await asyncio.sleep(0.025)
                assert predicate()

            try:
                pipe.send_text("\x1b[B\r")  # Manage installed is first; Search is next.
                await wait_until(lambda: tui._choice_kind == "skill discovery")
                assert tui._choice_kind == "skill discovery"
                pipe.send_text("\rpython\r")  # Query editor, submit
                await wait_until(lambda: bool(submitted) and submitted[-1][0] == "skill-search")
                assert submitted[-1][0] == "skill-search"
                record = SkillRecord("skillsmp", "one", "testing", "Long description",
                                     repository="org/repo")
                # Production records have normalized whitespace.
                tui._apply_background_result(("skill-search", "1", SearchResult(
                    CatalogStatus.OK, (record,), fetched_at=time.time()).payload(), ""))
                tui._panel.picker.focus(record.identity)
                tui._apply_picker_state()
                columns[0] = 40 if width != 40 else 80
                tui.application.invalidate()
                pipe.send_text("/testing")
                await wait_until(lambda: tui._panel.picker.query == "testing")
                assert tui._panel.picker.query == "testing"
                pipe.send_text("\x1b")  # leave local filter first
                await wait_until(lambda: not tui._panel.search_active)
                assert not tui._panel.search_active
                pipe.send_text("\r")
                await wait_until(lambda: tui._choice_kind == "skill discovery detail")
                assert tui._choice_kind == "skill discovery detail"
                pipe.send_text("\x1b")
                await wait_until(lambda: tui._choice_kind == "skill discovery")
                assert tui._choice_kind == "skill discovery"
                assert tui._panel.picker.selected_id == record.identity
                assert tui.running and list(tui.pending) == ["queued work"]
                assert tui.agent.messages == before
                assert not tui.cancel_requested.is_set()
                assert not tui.application.full_screen
            finally:
                tui.application.exit()
                await task
    asyncio.run(exercise())


@pytest.mark.parametrize("category", ["Skills", "MCPs"])
def test_installed_filter_and_detail_back_preserve_list_state(category, monkeypatch):
    tui = _fake_persistent_tui()
    tui._skill_inbox_preparation_attempted = True
    inventory = [
        {"name": "enabled-item", "enabled": True, "identity": "one",
         "transport": "http", "tool_count": 0, "description": "First item"},
        {"name": "disabled-item", "enabled": False, "identity": "two",
         "transport": "stdio", "tool_count": 0, "description": "Second item"},
    ]
    tui._skills_inventory = inventory
    tui._skills_inventory_loaded_at = time.monotonic()
    tui._mcp_inventory = {"servers": inventory, "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    monkeypatch.setattr("klaude_cli.main._mcp_registry", lambda: pytest.fail("UI registry read"))
    key = "skills" if category == "Skills" else "mcp servers"
    prefix = "skill:" if category == "Skills" else "server:"
    tui._open_settings_category(key)
    assert tui._panel.picker.selected_id == "manage"
    tui._accept_choice()
    tui._panel.picker.focus("filter")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb == ("Settings", category, "Manage", "Filter")
    tui._panel.picker.focus("disabled")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.picker.selected_id == "filter"
    item_ids = [row.id for row in tui._panel.page.rows if row.id.startswith(prefix)]
    assert item_ids == [prefix + "disabled-item"]
    panel = tui._panel
    panel.search_active = True
    tui._set_input("disabled")
    tui._refresh_choice_filter()
    panel.picker.focus(prefix + "disabled-item")
    panel.scroll_top = 2
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb[-1] == "disabled-item"
    tui._dismiss_picker()
    assert tui._panel is panel and panel.picker.selected_id == prefix + "disabled-item"
    assert panel.picker.query == "disabled" and panel.scroll_top == 2
    tui._dismiss_picker()
    assert tui._panel is panel and not panel.picker.query
    tui._dismiss_picker()
    assert tui._panel.page.breadcrumb == ("Settings", category)
    assert tui._panel.picker.selected_id == "manage"
    assert not tui._skill_action_pending and not tui._mcp_mutation_pending


@pytest.mark.parametrize("category", ["Skills", "MCPs"])
def test_empty_manage_search_returns_to_its_origin(category):
    tui = _fake_persistent_tui()
    tui._skill_inbox_preparation_attempted = True
    tui._skills_inventory = []
    tui._skills_inventory_loaded_at = time.monotonic()
    tui._mcp_inventory = {"servers": [], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    key = "skills" if category == "Skills" else "mcp servers"
    tui._open_settings_category(key)
    tui._accept_choice()
    tui._panel.picker.focus("search")
    tui._apply_picker_state()
    tui._accept_choice()
    assert tui._panel.page.breadcrumb[-1] == "Search"
    tui._dismiss_picker()
    assert tui._panel.page.breadcrumb == ("Settings", category, "Manage")
    assert tui._panel.picker.selected_id == "search"
    tui._dismiss_picker()
    tui._panel.picker.focus("search")
    tui._apply_picker_state()
    tui._accept_choice()
    tui._dismiss_picker()
    assert tui._panel.page.breadcrumb == ("Settings", category)
    assert tui._panel.picker.selected_id == "search"


def test_skills_import_navigation_preserves_pending_work_and_draft():
    tui = _fake_persistent_tui()
    tui._skill_inbox_preparation_attempted = True
    tui._skills_inventory = []
    tui._skills_inventory_loaded_at = time.monotonic()
    tui._set_input("unsent draft")
    submitted = []
    tui._skill_actions.submit = lambda action: submitted.append(action) or True
    tui._open_settings_category("skills")
    tui._accept_choice()
    tui._panel.picker.focus("import")
    tui._apply_picker_state()
    tui._accept_choice()
    assert not submitted
    assert tui._panel.page.breadcrumb == ("Settings", "Skills", "Manage", "Import")
    tui._accept_choice()
    assert len(submitted) == 1 and submitted[0].kind == "import"
    assert tui._choice_kind == "skills import" and tui._skill_action_pending
    assert not tui._panel.row("import").enabled
    tui._dismiss_picker()
    assert tui._panel.page.breadcrumb == ("Settings", "Skills", "Manage")
    tui._dismiss_picker()
    tui._dismiss_picker()
    tui._dismiss_picker()
    assert tui.input.text == "unsent draft"
    tui._events.put(("skill_action_done", (submitted[0], True, "Imported 1 skill")))
    tui._before_render(tui.application)
    assert tui._choice_kind is None and not tui._skill_action_pending
    assert tui.input.text == "unsent draft"


def test_mcp_refresh_list_never_queues_tool_reload(monkeypatch):
    tui = _fake_persistent_tui()
    tui._mcp_inventory = {"servers": [], "truncated": False}
    tui._mcp_inventory_scope = str(tui.cfg.mcp_servers_file)
    tui._mcp_inventory_loaded_at = time.monotonic()
    monkeypatch.setattr(tui._mcp_mutations, "submit", lambda *_: pytest.fail("Tool reload"))
    tui._open_settings_category("mcp servers")
    tui._accept_choice()
    tui._panel.picker.focus("refresh-list")
    tui._apply_picker_state()
    tui._accept_choice()
    identity = tui._background_jobs.latest["mcp-inventory"]
    assert tui._panel.picker.selected_id == "refresh-list"
    tui._apply_background_result(("mcp-inventory", identity,
                                  {"servers": [], "truncated": False}, ""))
    assert tui._panel.picker.selected_id == "refresh-list"
    assert not tui._mcp_mutation_pending


def test_skill_query_editor_does_not_answer_background_prompt_or_share_query(monkeypatch):
    from klaude_cli.settings_panel import PanelAction

    async def exercise():
        tui = _fake_persistent_tui()
        tui._user_input_request = {"id": "waiting", "question": "Choose a strategy",
                                   "choices": [], "remote": True}
        replies = []
        monkeypatch.setattr(tui, "_submit_user_input_response", lambda: replies.append(True))
        submissions = []
        monkeypatch.setattr(tui._background_jobs, "submit", lambda *args, **kwargs: (
            submissions.append(args) or "request-1"))
        tui._skill_discovery.open()
        tui._apply_panel_action(PanelAction("discover-query"))
        assert tui._session_io_request().draft is None
        with create_pipe_input() as pipe:
            tui.application.input = pipe
            tui.application.output = DummyOutput()
            task = asyncio.create_task(tui.application.run_async())
            try:
                await asyncio.sleep(0.05)
                pipe.send_text("python\r")
                await asyncio.sleep(0.1)
                assert len(submissions) == 1 and not replies
                assert tui._user_input_request["id"] == "waiting"
                assert tui._settings_input_request is None
                assert tui._choice_kind == "skill discovery"
                assert tui._session_io_request().draft is None
            finally:
                tui.application.exit()
                await task
    asyncio.run(exercise())


def test_implementation_resource_constraints_retain_workspace_tools():
    names = ("read_file", "write_file", "edit_file", "run_shell", "list_dir", "grep",
             "workspace_info", "learn_source", "web_search", "fetch_url", "read_skill")
    tools = {name: Tool(name, name, {}, lambda: "") for name in names}
    prompt = (
        "Implement CSV import in this project. Inspect the code and tests first. "
        "Add `python3 -m stockroom import-csv INPUT`. Save stock atomically in the same store. "
        "Use only the standard library. Add tests and update README documentation."
    )
    selected = _select_tool_names(prompt, tools)
    assert {"read_file", "write_file", "edit_file", "run_shell"} <= set(selected)
    assert "learn_source" not in selected



def test_oneshot_renderer_reports_failure_after_persisting_session(tmp_path, monkeypatch):
    from typer import Exit

    memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    class FailedAgent:
        model = "broken-provider"
        def run(self, _message, *, scope=None):
            yield AgentEvent("error", {"message": "Malformed function call"})
    monkeypatch.setattr("klaude_cli.main.console", Console(file=StringIO()))
    with pytest.raises(Exit) as failure:
        _render(FailedAgent(), memory, "failure-session", "Fix this project", raise_on_error=True)
    assert failure.value.exit_code == 1
    assert memory.session_live_state("failure-session")["state"] == "failed"
    assert any(turn["role"] == "system" and "Malformed function call" in str(turn["content"])
               for turn in memory.load_session("failure-session"))



def test_current_project_behavior_does_not_imply_current_external_research():
    names = ("read_file", "write_file", "edit_file", "run_shell", "web_search", "fetch_url",
             "query_knowledge", "code_search")
    tools = {name: Tool(name, name, {}, lambda: "") for name in names}
    local = _select_tool_names(
        "Review the Python code in this project to plan atomic persistence, keeping the "
        "current CLI behavior. Propose a plan for the implementation.", tools,
    )
    assert {"read_file", "edit_file"} <= set(local)
    assert not {"web_search", "fetch_url", "code_search"} & set(local)
    fresh = _select_tool_names(
        "Update this project to use the current stable Python API, inspecting documentation.",
        tools,
    )
    assert "web_search" in fresh
