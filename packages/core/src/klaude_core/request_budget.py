"""One context/output authority for compaction and multimodal admission."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

UNKNOWN_CLOUD_CONTEXT = 32768  # A local estimate, never a server allocation claim.


def estimate_prose_tokens(text: str, *, ratio: int) -> int:
    """ASCII heuristic plus conservative byte fallback for non-Latin text."""
    ascii_chars = sum(ord(character) < 128 for character in text)
    non_ascii_bytes = sum(len(character.encode("utf-8", errors="replace")) for character in text
                          if ord(character) >= 128)
    return (ascii_chars + ratio - 1) // ratio + non_ascii_bytes


def estimate_text_tokens(messages: list[dict], schemas: list[dict], *, local: bool) -> int:
    """Conservative text/protocol estimate, excluding separately admitted pixels."""
    total = (len(json.dumps(schemas, default=str)) + 1) // 2
    for message in messages:
        ratio = 3 if message.get("role") == "system" or not local else 2
        total += estimate_prose_tokens(str(message.get("content", "")), ratio=ratio) + 32
        total += sum((len(json.dumps(message[key], default=str)) + 1) // 2 for key in (
            "tool_calls", "openai_response_items", "codex_reasoning_items",
            "openrouter_reasoning_details", "deepseek_continuation", "anthropic_continuation",
            "gemini_continuation",
        ) if message.get(key))
    return total


def bound_search_snippets(messages: list[dict], limit: int) -> list[dict]:
    """Shorten optional search snippets without dropping later URLs or evidence provenance."""
    result = []
    for message in messages:
        content = message.get("content")
        if (message.get("role") == "tool" and message.get("tool_name") == "web_search"
                and isinstance(content, str)):
            def shortened(match):
                text = match[0]
                return text if len(text) <= limit else (
                    text[:limit] + " … [snippet shortened for context]" if limit else ""
                )

            projected = re.sub(r"(?m)^Snippet: .*$", shortened, content)
            if projected != content:
                message = {**message, "content": projected}
        result.append(message)
    return result


@dataclass(frozen=True)
class RequestBudget:
    context: int
    output: int
    source: str


def request_budget(info: Any, options: dict[str, Any]) -> RequestBudget:
    maximum = info.capabilities.context_window
    local = info.uses_configured_context
    allocated = options.get("num_ctx", 8192)
    allocated = allocated if type(allocated) is int and allocated > 0 else 8192
    context = (
        min(allocated, maximum)
        if local and maximum
        else allocated
        if local
        else maximum or UNKNOWN_CLOUD_CONTEXT
    )
    output = options.get("num_predict", 2048)
    output = output if type(output) is int and output > 0 else 2048
    if info.capabilities.max_output_tokens:
        output = min(output, info.capabilities.max_output_tokens)
    return RequestBudget(
        context,
        max(1024, output),
        "configured" if local else "declared" if maximum else "estimated",
    )
