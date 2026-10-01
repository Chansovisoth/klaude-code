import re

from klaude_core.intent import (
    explicit_workspace_inspection,
    explicitly_disallows_tools,
    has_nonnegated_action,
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
