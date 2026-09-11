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
    CodexAuthError,
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
    assert get_line(2) == [("class:transcript.divider", "━━ you · 2026-09-05 12:34:56 ━━━━━━━━━━")]


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

    assert "⠋ EDITING" in status
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

    assert "⠋ WAITING" in status
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
    assert first in tui._choice_fragments()[0][1]
    fragments = tui._choice_fragments()
    assert ("class:choice.active.edge", "[") in fragments
    assert ("class:choice.active.word", "ACTIVE") in fragments
    assert ("class:choice.active.edge", "]") in fragments
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
    assert "⠙ EXPLORING" in status
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


def test_completion_match_color_uses_the_composer_foreground_without_a_new_background():
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
    assert selected.color == composer.color
    assert selected.bgcolor == row.bgcolor
    assert not selected.bold
    assert not selected.underline

    selected_match = style.get_attrs_for_style_str(
        "class:completion-menu.completion.current class:suggestion-match-text"
    )
    assert selected_match.color == composer.color
    assert selected_match.bgcolor == row.bgcolor
    assert not selected_match.bold
    assert not selected_match.underline

    selected_unmatched = style.get_attrs_for_style_str(
        "class:completion-menu.completion.current class:suggestion-unmatched-text"
    )
    assert selected_unmatched.color == composer.color
    assert selected_unmatched.bgcolor == row.bgcolor


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


def test_persistent_tui_restores_enhanced_keyboard_mode_on_failure(monkeypatch):
    tui = _fake_persistent_tui()
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

    return PersistentChatTUI(
        FakeAgent(),
        FakeMemory(),
        "session-1",
        Config(),
        appearance_path=appearance_path,
        chat_preferences_path=chat_preferences_path,
    )


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
    assert saved["tool_validation"] == {"web_search": False, "knowledge_search": True}
    assert all(saved["tool_availability"].values())
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
        ("tools", "web search validation:"),
        ("permissions", "Write file:"),
        ("runtime", "CPU threads:"),
    ):
        tui._open_settings_category(category)
        row = next(value for value in tui._choice_values if value.startswith(selected))
        tui._choice_index = tui._choice_values.index(row)

        tui._open_settings_category(category)

        assert tui._choice_values[tui._choice_index].startswith(selected)


def test_settings_include_memory_and_skills_categories():
    tui = _fake_persistent_tui()

    categories = tui._settings_categories()

    assert "memory" in categories
    assert "skills" in categories


def test_memory_settings_toggle_show_facts_and_reset_to_enabled(tmp_path):
    tui = _fake_persistent_tui()
    tui.memory = Memory(tmp_path / "memory.md", tmp_path / "sessions.db")
    tui.memory.remember("Prefer concise answers", source="manual")

    tui._open_settings_category("memory")

    assert tui._choice_kind == "memory settings"
    assert "automatic memory: on (toggle)" in tui._choice_values
    assert "\0info:Durable facts: 1" in tui._choice_values
    assert any("Prefer concise answers" in value for value in tui._choice_values)
    tui._choice_index = tui._choice_values.index("automatic memory: on (toggle)")
    tui._accept_choice()
    assert not tui.memory.auto_memory_enabled()
    assert "automatic memory: off (toggle)" in tui._choice_values

    tui._choice_index = tui._choice_values.index("reset to default")
    tui._accept_choice()
    assert tui.memory.auto_memory_enabled()


def test_skills_settings_show_read_only_installed_inventory(monkeypatch):
    tui = _fake_persistent_tui()
    monkeypatch.setattr(
        "klaude_knowledge.list_installed_skills",
        lambda _cfg: [
            {
                "name": "crawl4ai",
                "library": "web-tools",
                "indexed_files": ["SKILL.md", "reference.md"],
            }
        ],
    )

    tui._open_settings_category("skills")

    assert tui._choice_kind == "skills settings"
    assert "\0info:Installed: 1" in tui._choice_values
    assert (
        "\0info:crawl4ai · library web-tools · 2 indexed files" in tui._choice_values
    )
    assert "reset to default" not in tui._choice_values
    assert tui._choice_values[-1] == "back"
    rendered = "".join(text for _style, text in tui._choice_fragments())
    assert "\0info:" not in rendered
    assert "crawl4ai · library web-tools · 2 indexed files" in rendered


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
        gate=SimpleNamespace(
            policies={"read_file": "allow", "run_shell": "ask", "write_file": "deny"}
        ),
    )

    result = _chat_status(agent, memory, "session-1")

    assert "Session ID    session-1" in result
    assert "Session name  Parser investigation" in result
    assert "Mode          thinking" in result
    assert "Effort        high" in result
    assert "Turn limit    40 steps + finalization" in result
    assert "Turn scope    review" in result
    assert "Callable now  2/3 enabled tools" in result
    assert "Turn budget   models 3/40 · tools 5/80 · 7.2s" in result
    assert "Context left  ~16,381 tokens" in result
    assert f"Workspace     {workdir}" in result
    assert "AGENTS.md     injected" in result
    assert f"              {root_instructions}" in result
    assert f"              {nested_instructions}" in result
    assert "Permissions   allow 1 · ask 1 · deny 1" in result
    assert "Memory        on" in result
    assert "Tools         3" in result


def test_status_columns_align_values():
    rendered = _status_columns([("ID", "abc"), ("Session name", "Parser work"), ("", "/path")])
    lines = rendered.splitlines()

    assert {
        line.index(value)
        for line, value in zip(lines, ("abc", "Parser work", "/path"), strict=True)
    } == {len("Session name") + 2}


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
        "• Queued follow-up inputs\n"
        "  ↳ like this\n"
        "  ↳ and ↵ this\n"
        "    alt + ↑ edit last queued message"
    )
    root = tui.application.layout.container
    assert root.content.children[0] is tui.text_theme_preview_panel
    assert root.content.children[2] is tui.queue_panel
    assert root.content.children[3] is tui.input_spacer
    assert root.content.children[4] is tui.input_panel


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
    assert tui._choice_values[tui._choice_index] == "models"


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
    assert f" {expected_path} ┃" == "".join(
        text for _style, text in tui._footer_path_fragments()
    )
    assert "Enter to send/queue" in "".join(text for _style, text in tui._keybind_fragments())


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
    tui._choice_index = tui._choice_values.index("interface theme: Autumn")
    tui._accept_choice()
    assert tui._choice_values[-1] == "back"
    tui._choice_index = len(tui._choice_values) - 1
    tui._accept_choice()
    assert tui._choice_kind == "theme settings"
    assert tui.appearance.theme == original_theme


def test_cancel_during_effort_picker_restores_original_model():
    tui = _fake_persistent_tui()
    tui._set_input("/model")
    tui._submit_buffer(steer=False)
    tui._choice_index = tui._choice_values.index("Local")
    tui._accept_choice()
    tui._choice_index = tui._choice_values.index("gpt-oss:20b")
    tui._accept_choice()

    assert tui.agent.model == "gpt-oss:20b"
    assert tui._choice_kind == "mode"
    tui._choice_index = tui._choice_values.index("thinking")
    tui._accept_choice()
    assert tui._choice_kind == "effort"
    assert tui._choice_values[-1] == "cancel"
    tui._choice_index = len(tui._choice_values) - 1
    tui._accept_choice()

    assert tui._choice_kind is None
    assert tui.agent.model == "qwen3.5:4b"


def test_persistent_tui_renders_unavailable_picker_options_in_gray(monkeypatch):
    monkeypatch.setattr("klaude_cli.main.load_model_cache", lambda _path: [])
    tui = _fake_persistent_tui()
    tui._open_cloud_provider()

    fragments = tui._choice_fragments()

    assert tui._choice_values[tui._choice_index] == "OpenAI Codex — not signed in"
    assert (
        "class:choice.disabled.selected",
        "  › OpenAI Codex — not signed in\n",
    ) in fragments
    assert tui._choice_values[-3:] == [
        "back",
        "",
        "Tip: use `klaude auth login openai-codex`, or add API keys to config/.env",
    ]
    assert ("class:choice.disabled", "\n") in fragments
    assert (
        "class:choice.disabled",
        "    Tip: use `klaude auth login openai-codex`, or add API keys to config/.env",
    ) in fragments


def test_unavailable_picker_options_can_be_highlighted_but_not_accepted(monkeypatch):
    monkeypatch.setattr("klaude_cli.main.load_model_cache", lambda _path: [])
    tui = _fake_persistent_tui()
    tui._open_cloud_provider()

    codex = tui._choice_index
    tui._move_choice(1)
    openai = tui._choice_index
    assert tui._choice_values[openai] == "OpenAI — API key not configured"
    tui._move_choice(1)
    google = tui._choice_index
    assert tui._choice_values[google] == "Google — API key not configured"

    tui._accept_choice()
    assert tui._choice_kind == "model cloud provider"
    assert tui._choice_index == google

    tui._move_choice(1)
    assert tui._choice_values[tui._choice_index] == "back"
    tui._click_choice(codex)
    assert tui._choice_index == codex
    tui._click_choice(codex)
    assert tui._choice_kind == "model cloud provider"
    assert tui._choice_index == codex


def test_expired_codex_auth_keeps_model_picker_open(monkeypatch):
    tui = _fake_persistent_tui()
    tui._model_choices = {
        "gpt-5.6-sol": ModelInfo("openai_codex", "gpt-5.6-sol", "GPT-5.6 Sol")
    }
    tui._begin_choice("model", ["gpt-5.6-sol", "back"], "gpt-5.6-sol")
    monkeypatch.setattr(
        "klaude_cli.main._set_agent_model",
        lambda *_args: (_ for _ in ()).throw(CodexAuthError("sign in again")),
    )

    tui._accept_choice()

    assert tui._choice_kind == "model"
    assert tui.agent.model == "qwen3.5:4b"
    assert tui.status_error == "sign in again"


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
            tui._begin_choice("model", [f"model-{i:02}" for i in range(count)], "model-00")
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


@pytest.mark.parametrize("responds_to_cpr", [False, True])
@pytest.mark.parametrize("switch_session", [False, True])
def test_terminal_scrollback_survives_streaming_refresh_resize_and_preview(
    tmp_path,
    responds_to_cpr,
    switch_session,
):
    import pyte
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.vt100 import Vt100_Output

    async def exercise():
        tui = _fake_persistent_tui(tmp_path / "appearance.json")

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
                    tui.agent.restore_session = lambda turns: Agent.restore_session(
                        tui.agent,
                        turns,
                    )
                    tui._set_input("/resume other")
                    tui._submit_buffer(steer=False)
                    tui.application._redraw()
                    await asyncio.sleep(0.01)
                    lines = transcript_lines()
                    assert "Selected saved conversation" in lines
                    assert not any(line in expected for line in lines)
                    assert "Session: session-1" not in "\n".join(lines)
                    tui._set_input("/new")
                    tui._submit_buffer(steer=False)
                    tui.application._redraw()
                    await asyncio.sleep(0.01)
                    assert "Selected saved conversation" not in transcript_lines()
                    assert tui.session_id in "\n".join(transcript_lines())
                    assert len(tui.memory.load_session("other")) == 1
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


def test_printed_transcript_background_fills_rows_without_padding(tmp_path):
    import pyte
    from prompt_toolkit.data_structures import Size
    from prompt_toolkit.output.color_depth import ColorDepth
    from prompt_toolkit.output.vt100 import Vt100_Output

    tui = _fake_persistent_tui(tmp_path / "appearance.json")
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
        "━━ Session: test ━━",
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
    tui._begin_choice("theme", ["autumn", "neon-synth"], "autumn")
    tui._move_choice(1)
    assert tui.appearance.theme == "neon-synth"
    preview_rows = "".join(text for _style, text in tui._choice_fragments())
    assert "autumn *" in preview_rows
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
        "usage": {"input_tokens": 12, "output_tokens": 4},
    }


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
    assert tui._secret_request is None
    assert not password_processor.filter()

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
    monkeypatch.setattr(tui, "_sync_shared_session", lambda: calls.append("sync"))
    tui._begin_choice("settings", tui._settings_categories(), "models")
    tui._last_picker_session_sync = time.monotonic()

    tui._before_render(None)

    assert calls == []
    tui._last_picker_session_sync = 0.0
    tui._before_render(None)
    assert calls == ["sync"]


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
    tui._set_input("unknown")

    tui._submit_choice_response()

    assert tui._choice_kind == "settings"
    assert tui.input.text == "unknown"
    assert tui.status_error == "That is not an available option"


def test_tui_appearance_store_defaults_and_round_trips(tmp_path):
    path = tmp_path / "appearance.json"

    assert _load_tui_appearance(path) == TUIAppearance()

    appearance = TUIAppearance(
        theme="hacker-green",
        text_theme="monokai",
        input_border=False,
        input_height=12,
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
    assert _load_tui_appearance(path) == TUIAppearance()
    assert tui.output.window.right_margins == []


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
            yield AgentEvent("text_delta", {"content": "```python\n"})
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
        "read_file",
        "list_dir",
        "grep",
        "workspace_info",
        "delegate_task",
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
