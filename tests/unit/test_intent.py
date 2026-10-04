import re

from klaude_core.intent import (
    explicit_local_file_read_request,
    explicit_only_tool_names,
    explicit_workspace_inspection,
    explicitly_disallows_tools,
    has_nonnegated_action,
    prohibits_skill_read,
    prohibits_web_search,
)


def test_nonnegated_action_ignores_prohibitions_without_hiding_positive_clauses():
    mutation = re.compile(r"\b(?:edit|modify|fix)\b", re.IGNORECASE)

    assert not has_nonnegated_action("Do not modify anything", mutation)
    assert not has_nonnegated_action("Review it without editing files", mutation)
    assert has_nonnegated_action("Fix the parser, but do not modify tests", mutation)
    assert has_nonnegated_action("Do not edit tests; fix the parser", mutation)


def test_workspace_inspection_requires_a_positive_inspection_action():
    assert explicit_workspace_inspection("Inspect this workspace read-only")
    assert explicit_workspace_inspection("Do not edit files; review this repository")
    assert not explicit_workspace_inspection("Do not inspect this workspace")
    assert not explicit_workspace_inspection("Answer without reviewing the codebase")


def test_explicit_tool_prohibition_variants_are_recognized():
    assert explicitly_disallows_tools("Do not use tools")
    assert explicitly_disallows_tools("Answer without calling any tools")
    assert explicitly_disallows_tools("No tools, please")
    assert not explicitly_disallows_tools("Use only read-only tools")


def test_web_prohibition_respects_coordinated_lists_and_positive_clauses():
    assert prohibits_web_search("Do not use public web search for this turn")
    assert prohibits_web_search(
        "Do not edit files, run shell, or use public web search."
    )
    assert prohibits_web_search("Do not use Context7 or web search")
    assert not prohibits_web_search("Do not use Context7, use web search instead")


def test_skill_read_prohibition_is_specific_to_opening_instructions():
    assert prohibits_skill_read("Do not read the Skill or infer its purpose")
    assert prohibits_skill_read("Answer without opening SKILL.md")
    assert not prohibits_skill_read("Read the coding-standards Skill")
    assert not prohibits_skill_read("Do not modify files; read the Skill")


def test_named_local_file_read_does_not_require_the_literal_word_file():
    assert explicit_local_file_read_request("Can you read xhallenge1.md?")
    assert explicit_local_file_read_request("Read challenge1.md and follow its instructions")
    assert explicit_local_file_read_request("Review src/main.py")
    assert not explicit_local_file_read_request("Do not read challenge1.md")
    assert not explicit_local_file_read_request("Read https://example.com/challenge1.md")
    assert not explicit_local_file_read_request("Create challenge1.md")


def test_resource_constraints_do_not_turn_off_tools():
    names = {"read_file", "write_file", "run_shell"}
    for message in (
        "Implement the CLI. Use only the standard library.",
        "Use only Python for this project.",
        "Use only local dependencies; test the implementation.",
    ):
        assert explicit_only_tool_names(message, names) is None
    assert explicit_only_tool_names("Use only read_file to inspect this", names) == ["read_file"]
    assert explicit_only_tool_names("Use only unavailable_tool to inspect this", names) == []
    assert explicit_only_tool_names("Use only the unavailable tool", names) == []
