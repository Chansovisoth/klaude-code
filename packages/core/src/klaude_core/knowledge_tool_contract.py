"""Model-facing local retrieval contract and compatibility argument mapping."""

from __future__ import annotations

from typing import Any

KNOWLEDGE_TOOL_DESCRIPTION = (
    "Search locally indexed documentation, code examples, and learned content. "
    "Use when the user asks about local knowledge or learned libraries. "
    "Returns matching passages with source references, or reports no relevant matches. "
    "Omit library to select relevant libraries automatically. "
    "Does not search the live web or modify indexed content."
)


def knowledge_tool_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "minLength": 1,
                "description": "Question or search terms to find in locally indexed content.",
            },
            "library": {
                "type": "string",
                "description": (
                    "Optional existing library name, such as godot-2d. "
                    "Omit or leave empty for automatic library selection."
                ),
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    }


def normalize_knowledge_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Retain legacy precedence without exposing duplicate parameters to models."""
    result = dict(arguments)
    # Do not let a valid preferred field hide a malformed alternate field.
    # Leave invalid input intact for the ordinary schema validator to reject,
    # before permission checks and execution.
    if any(
        key in result and not isinstance(result[key], str)
        for key in ("query", "question", "library", "collection")
    ):
        return result
    if "question" in result:
        question = result.pop("question")
        if question or "query" not in result:
            result["query"] = question
    if isinstance(result.get("query"), str):
        result["query"] = result["query"].strip()
    if "collection" in result:
        collection = result.pop("collection")
        if not result.get("library"):
            result["library"] = collection
    return result
