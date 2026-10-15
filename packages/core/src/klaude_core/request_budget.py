"""One context/output authority for compaction and multimodal admission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

UNKNOWN_CLOUD_CONTEXT = 32768  # A local estimate, never a server allocation claim.


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
