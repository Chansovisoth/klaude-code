"""Mechanical constraints for requested quotations, separate from code generation."""

from __future__ import annotations

import re


def code_quote_limit(request: str) -> int | None:
    match = re.search(
        r"(?i)\b(?:quote|excerpt)\s+(?:at most|no more than|up to)\s+"
        r"(\d{1,3})\s+(?:code lines|lines of code)\b",
        request,
    )
    return min(int(match[1]), 100) if match else None


def limit_code_quotes(content: str, limit: int | None) -> str:
    """Limit fenced quotations across blocks without silently editing programs."""
    if limit is None:
        return content
    remaining = limit
    omitted = False
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    fence = ""
    for line in lines:
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if not fence and marker:
            fence = marker[1]
            output.append(line)
        elif fence and marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
            fence = ""
            output.append(line)
        elif fence:
            if remaining > 0:
                output.append(line)
                remaining -= 1
            else:
                omitted = True
        else:
            output.append(line)
    if fence:
        output.append("\n" + fence + "\n")
    result = "".join(output)
    if omitted:
        result = (
            result.rstrip()
            + f"\n\nCode quotation limited to {limit} lines; remaining lines omitted."
        )
    return result
