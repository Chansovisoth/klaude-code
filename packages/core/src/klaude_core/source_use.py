"""Answer retrospective source-use questions from observed turn activity."""

from __future__ import annotations

import re
from typing import Any

_ACTUAL_USE = re.compile(
    r"(?i)\b(?:which|what)\s+(?:(?:knowledge|research|external)\s+)?"
    r"(?:sources?|resources?|tools?)\s+"
    r"(?:did|have)\s+you\s+(?:actually\s+)?(?:use|used|consult|consulted)\b"
    r"|\b(?:did|have)\s+(?:you|u)\s+(?:actually\s+)?(?:use|consult)\b"
    r"|\bwhere\s+did\s+(?:you\s+)?(?:get|find)\s+(?:that|this)\b"
)

_RETRIEVAL_NAMES = {
    "query_knowledge": "local knowledge",
    "web_search": "web search",
    "fetch_url": "a fetched web page",
    "code_search": "code search",
    "huggingface_search": "Hugging Face search",
    "huggingface_details": "Hugging Face details",
    "huggingface_readme": "a Hugging Face README",
}


def asks_what_was_used(message: str) -> bool:
    """A past-use question is different from asking what is available now."""
    if re.search(r"(?i)\b(?:could|can|available|might|would)\b", message):
        return False
    return bool(_ACTUAL_USE.search(message))


def prior_answer_source_note(turns: list[dict[str, Any]]) -> str:
    """Use result records only; an invocation or audit success is not evidence text."""
    if not turns:
        return "I cannot verify which sources were used for an earlier answer."
    answer_index = next(
        (i for i in range(len(turns) - 1, -1, -1) if turns[i].get("role") == "assistant"),
        -1,
    )
    interruption_index = next(
        (
            i for i in range(len(turns) - 1, -1, -1)
            if turns[i].get("role") == "system"
            and isinstance(turns[i].get("content"), dict)
            and turns[i]["content"].get("event") == "interruption"
        ),
        -1,
    )
    if interruption_index > answer_index:
        return (
            "The previous turn was interrupted before a completed answer. "
            "Any tool audit only records execution, not the evidence returned."
        )
    if answer_index < 0:
        return "I cannot verify which sources were used for an earlier answer."
    start = next(
        (i for i in range(answer_index - 1, -1, -1) if turns[i].get("role") == "user"),
        -1,
    )
    if start < 0:
        return "I cannot verify which sources were used for an earlier answer."
    names: list[str] = []
    for turn in turns[start + 1 : answer_index]:
        role = turn.get("role")
        content = turn.get("content")
        if role == "tool" and isinstance(turn.get("metadata"), dict) and (
            turn["metadata"].get("executed") is True
        ):
            name = str(turn.get("tool_name", ""))
        elif role == "system" and isinstance(content, dict) and (
            content.get("event") == "tool_audit"
            and content.get("phase") == "result"
            and content.get("executed") is True
        ):
            name = str(content.get("tool", ""))
        else:
            continue
        if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name) and name not in names:
            names.append(name)
    if not names:
        return (
            "No retrieval tool was used for that answer. I generated it from the "
            "model's existing knowledge and the conversation context."
        )
    labels = [
        _RETRIEVAL_NAMES.get(name, f"MCP tool {name}" if name.startswith("mcp__") else name)
        for name in names
    ]
    return (
        "The recorded tool activity for that answer was: "
        + ", ".join(labels)
        + ". These records confirm tool execution, but do not by themselves "
        "preserve or prove the answer's specific evidence."
    )
