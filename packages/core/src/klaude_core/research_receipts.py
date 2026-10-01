"""Bounded durable research metadata, separate from tool audits and results."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

RESEARCH_TOOLS = {"web_search", "fetch_url", "query_knowledge", "code_search"}


def _short(value: object, limit: int) -> str:
    printable = "".join(char if char.isprintable() else " " for char in str(value or ""))
    return " ".join(printable.split())[:limit]


def _public_url(value: object) -> str:
    try:
        url = urlsplit(str(value or ""))
    except ValueError:
        return ""
    if url.scheme not in {"http", "https"} or not url.hostname or url.username:
        return ""
    # Query parameters and fragments can contain credentials or private terms.
    return urlunsplit((url.scheme, url.hostname, url.path[:240], "", ""))[:300]


def research_receipt(
    tool: str, args: dict[str, Any], metadata: dict[str, Any], result: object
) -> dict[str, Any] | None:
    """Persist only typed identifiers/counts; never copy an arbitrary tool body."""
    if tool not in RESEARCH_TOOLS and not tool.startswith("mcp__"):
        return None
    executed = metadata.get("executed") is True
    body = str(result)
    failed = not executed or body.startswith(("error:", "tool error:", "permission denied:"))
    receipt: dict[str, Any] = {
        "event": "research_receipt",
        "tool": _short(tool, 128),
        "status": "failed" if failed else "completed",
        "result_replayable": False,
    }
    if tool in {"web_search", "code_search", "query_knowledge"}:
        receipt["query"] = _short(args.get("query") or args.get("question"), 240)
    if tool == "web_search":
        results = metadata.get("search_results")
        receipt["lead_count"] = min(len(results), 100) if isinstance(results, list) else 0
        receipt["provider"] = _short(metadata.get("provider"), 60)
    elif tool == "query_knowledge":
        receipt["library"] = _short(metadata.get("library") or args.get("library"), 80)
        receipt["found"] = metadata.get("found") is True
        count = metadata.get("result_count")
        receipt["result_count"] = min(max(int(count), 0), 100) if isinstance(count, int) else 0
    elif tool == "fetch_url":
        receipt["source_id"] = _short(metadata.get("source_id"), 80)
        receipt["public_url"] = _public_url(
            metadata.get("canonical_url") or metadata.get("final_url") or args.get("url")
        )
    return receipt


def recovery_receipts(turns: list[dict[str, Any]], interruption: int) -> str:
    """Summarize receipts from only the interrupted user turn for model recovery."""
    start = next(
        (i for i in range(interruption - 1, -1, -1) if turns[i].get("role") == "user"),
        -1,
    )
    if start < 0:
        return ""
    receipts = [
        turn["content"]
        for turn in turns[start + 1 : interruption]
        if turn.get("role") == "system"
        and isinstance(turn.get("content"), dict)
        and turn["content"].get("event") == "research_receipt"
    ][:8]
    if not receipts:
        return "No durable research receipts are available. Re-run needed searches."
    lines = ["Durable research receipts (metadata only; results must be fetched again):"]
    for item in receipts:
        if item.get("status") != "completed":
            continue
        tool = _short(item.get("tool"), 128)
        detail = (
            _short(item.get("public_url"), 300)
            or _short(item.get("query"), 240)
            or _short(item.get("library"), 80)
        )
        lines.append(f"- {tool}: {detail or 'completed; result unavailable'}")
    if len(lines) == 1:
        return "Recorded research attempts failed. Re-run needed searches."
    return "\n".join(lines)[:1_500]
