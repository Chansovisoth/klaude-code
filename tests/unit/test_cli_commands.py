import inspect
import json
from datetime import datetime
from io import StringIO
from pathlib import Path

from klaude_cli.main import (
    COMMAND_REFERENCE,
    LIST_COMMANDS_TOOL_DESCRIPTION,
    WEATHER_TOOL_DESCRIPTION,
    CommandSurface,
    _append_tool_capabilities,
    _apply_runtime_context_to_search_config,
    _bounded_result_count,
    _command_reference_context,
    _command_reference_result,
    _format_search_response,
    _format_web_results,
    _handle_command_reference_request,
    _handle_unknown_slash_command,
    _iter_online_docs_entries,
    _knowledge_libraries_count,
    _mode_from_permission,
    _online_docs_file,
    _print_assistant_text,
    _print_trace,
    _query_knowledge_display_lines,
    _render,
    _runtime_status_summary,
    _search_execution_metadata,
    _select_tool_names,
    _system_prompt,
    _update_online_docs,
    _web_mode,
    _web_search_display_lines,
    _web_search_start_metadata,
    app,
    docs_update,
    format_command_reference,
    format_focused_command_help,
    is_complete_command_reference_request,
    iter_command_specs,
    resolve_command_help_request,
    sessions_clear,
    sessions_delete,
    system_info,
)
from klaude_core import Agent, AgentEvent, PermissionGate, Tool
from klaude_core.config import DEFAULT_PERMISSIONS, Config
from klaude_core.memory import Memory
from klaude_core.runtime_context import (
    LocationContext,
    RuntimeContext,
    RuntimeContextResult,
    SystemContext,
    TemporalContext,
)
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text


def test_system_prompt_points_to_deterministic_command_reference(tmp_path):
    prompt = _system_prompt(Memory(tmp_path / "memory.md", tmp_path / "sessions.db"))

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


def test_canonical_command_reference_preserves_sections_and_lines():
    reference = format_command_reference(width=100)

    assert reference.startswith("Usage: klaude [OPTIONS] COMMAND [ARGS]...\n\n")
    assert "\nCLI COMMANDS\n------------\n" in reference
    assert "\nDOCS COMMANDS\n-------------\n" in reference
    assert "\nCHAT COMMANDS\n-------------\n" in reference
    assert "\n  chat" in reference
    assert "\n  ask" in reference
    assert "\n  search" in reference
    assert "\n  docs update --online" in reference
    assert "\n  /help" in reference
    assert "\n  /models" in reference
    assert "\n  /model       Show the active chat model." in reference
    assert "\n  /model NAME" in reference
    assert "AGENT CAPABILITIES" not in reference
    assert "chat Interactive" not in reference
    assert "ask One-shot" not in reference
    assert "\x1b" not in reference
    assert all(char == "\n" or ord(char) >= 32 for char in reference)


def test_command_registry_contains_model_commands_separately():
    usages = {spec.usage for spec in iter_command_specs()}

    assert "/model" in usages
    assert "/model NAME" in usages
    assert "/models" in usages


def test_typer_commands_and_registry_do_not_silently_diverge():
    typer_names = {
        command.name or command.callback.__name__.replace("_", "-")
        for command in app.registered_commands
    }
    typer_names.update(group.name for group in app.registered_groups)
    registry_names = {
        spec.usage.split()[0]
        for spec in iter_command_specs(CommandSurface.CLI)
    }

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
    assert (
        "  docs add NAME URL -l LIBRARY\n"
        "      Install refreshable llms.txt"
    ) in narrow


def test_focused_search_command_help_is_not_full_reference():
    response = format_focused_command_help("what command searches the web", width=80)

    assert response == (
        "klaude search QUERY\n"
        "    Web search via the configured provider."
    )
    assert "CLI COMMANDS" not in response


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
    assert not is_complete_command_reference_request(
        "what database commands should my app support"
    )
    assert not is_complete_command_reference_request("how should I design a command pattern")


def test_focused_model_help_matches_actual_model_behavior():
    response = format_focused_command_help("what does /model do?", width=90)

    assert "/model\n    Show the currently active model." in response
    assert (
        "/model NAME\n"
        "    Switch to an installed Ollama model while preserving this conversation."
    ) in response
    assert "/model qwen3-coder:30b" in response
    assert "Use /models to list the available models." in response
    assert "/model list" not in response
    assert "/model select" not in response
    assert "/model info" not in response


def test_focused_models_help_is_distinct_from_model_help():
    response = format_focused_command_help("how do I use /models?", width=90)

    assert response == (
        "/models\n"
        "    List installed Ollama models and mark the active model."
    )
    assert "/model NAME" not in response


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
    assert "Did you mean /model?" in response


def test_focused_docs_and_status_help_use_registry():
    assert format_focused_command_help("how do I update all docs?", width=90).startswith(
        "klaude docs update --all\n"
    )
    assert format_focused_command_help("explain klaude docs update", width=90).startswith(
        "klaude docs update NAME\n"
    )
    assert format_focused_command_help("what does the status command do?", width=90) == (
        "klaude status\n"
        "    Show configured modes, storage, and tool permissions."
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
    assert printed[0][1] == {"overflow": "fold"}


def test_command_reference_metadata_renders_preformatted(monkeypatch):
    printed = []

    monkeypatch.setattr(
        "klaude_cli.main.console.print",
        lambda *args, **kwargs: printed.append((args, kwargs)),
    )

    _print_assistant_text(
        "Usage: klaude [OPTIONS] COMMAND [ARGS]...\n\nCLI COMMANDS\n------------",
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
        def run(self, user_msg):
            yield AgentEvent(
                "tool_result",
                {
                    "tool": "list_commands",
                    "result": (
                        "The command reference is unnecessary for this "
                        "conversational request."
                    ),
                    "metadata": {"suppress_user_output": True},
                },
            )
            yield AgentEvent("text", {"content": "Hi! I'm Klaude."})

    class FakeMemory:
        def log_turn(self, session_id, role, content):
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


def test_render_shows_web_search_provider_from_structured_metadata(monkeypatch):
    printed = []
    turns = []

    class FakeAgent:
        def run(self, user_msg):
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
        def log_turn(self, session_id, role, content):
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
        def run(self, user_msg):
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
        def log_turn(self, session_id, role, content):
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
        def log_turn(self, session_id, role, content):
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
    assert "\nCLI COMMANDS\n------------\n  chat" in rendered.plain
    assert "\nDOCS COMMANDS\n-------------\n" in rendered.plain
    assert "\nCHAT COMMANDS\n-------------\n" in rendered.plain
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
    assert _handle_command_reference_request("/commands") is True

    assert isinstance(printed[0][0][0], Text)
    assert printed[0][0][0].plain == "-> command_reference [local]"
    assert printed[1][0][0].plain == format_command_reference(width=100)
    assert isinstance(printed[2][0][0], Text)
    assert printed[2][0][0].plain == "-> command_reference [local]"
    assert printed[3][0][0].plain == format_command_reference(width=100)


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
        "klaude search QUERY\n"
        "    Web search via the configured provider."
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
        def log_turn(self, session_id, role, content):
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
        "Unknown chat command: /reload\n"
        "Type /help to see the available commands."
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
        "Did you mean /model?\n"
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
    assert "/model\n    Show the currently active model." in focused
    assert "/model NAME\n    Switch to an installed Ollama model" in focused
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
        "who are you",
        "hi, who might you be",
        "introduce yourself",
        "what can you do",
    ):
        assert _select_tool_names(message, tools) == []


def test_list_commands_is_allowed_by_default():
    assert DEFAULT_PERMISSIONS["list_commands"] == "allow"
    assert DEFAULT_PERMISSIONS["current_time"] == "allow"
    assert DEFAULT_PERMISSIONS["weather_lookup"] == "allow"
    assert DEFAULT_PERMISSIONS["workspace_info"] == "allow"


def test_list_commands_description_excludes_casual_identity_questions():
    description = LIST_COMMANDS_TOOL_DESCRIPTION

    assert "canonical public CLI and chat command reference" in description
    assert "available commands" in description
    assert "Never invent commands" in description
    assert "focused command help" in description


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
                "Paragon International University is among the top universities "
                "in Cambodia."
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
    assert fetched_urls == [
        "https://www.paragoniu.edu.kh/",
        "https://www.paragoniu.edu.kh/",
    ]


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

    assert formatted.startswith("[1] FlazeSlayer - YouTube")
    assert "[2] flaze_slayer - Twitch" in formatted


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
    assert _select_tool_names("/commands", tools) == ["list_commands"]
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

    assert selected == ["query_knowledge", "code_search", "web_search"]


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


def test_web_search_start_metadata_uses_router_provider_without_result_text():
    class FakeWeb:
        cfg = None

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
        "CREATE TABLE active_sources "
        "(library TEXT, owner TEXT, source TEXT, version_id TEXT)"
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
