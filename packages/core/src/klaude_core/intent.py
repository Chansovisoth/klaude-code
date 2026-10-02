"""Small, deterministic intent predicates shared by routing and execution."""

from __future__ import annotations

import re
from re import Pattern

_NEGATED_ACTION_PREFIX = re.compile(
    r"(?:\b(?:do|does|did|can|could|should|would|will|must|please)\s+not\b|"
    r"\b(?:don['’]?t|dont|never|without)\b|\bno\s+need\s+to\b)"
    r"(?:\s+(?:[a-z0-9_-]+|and|or|just|any|the|this|that)){0,5}\s*$",
    re.IGNORECASE,
)
_WORKSPACE_ACTION = re.compile(
    r"\b(?:inspect|analy[sz]e|review|explore|audit|identify|determine)\b", re.I
)
_WORKSPACE_SUBJECT = re.compile(
    r"\b(?:workspace|repo(?:sitory)?|codebase|project files|files in (?:this|the)|"
    r"primary implementation language)\b",
    re.IGNORECASE,
)
_NO_TOOLS = re.compile(
    r"\b(?:do\s+not|don['’]?t|dont|never)"
    r"(?:\s+[a-z0-9_-]+){0,8}\s+(?:use|call|invoke)\s+"
    r"(?:any\s+)?tools?\b|\bwithout\s+(?:using|calling|invoking)\s+"
    r"(?:any\s+)?tools?\b|\bno\s+tools?\b",
    re.IGNORECASE,
)


def has_nonnegated_action(text: str, action: str | Pattern[str]) -> bool:
    """Return whether an action occurs outside a nearby explicit prohibition.

    This is deliberately bounded lexical handling rather than sentiment or
    dependency parsing. It handles direct CLI instructions predictably while
    leaving genuinely ambiguous language for the model or user.
    """
    pattern = re.compile(action, re.IGNORECASE) if isinstance(action, str) else action
    for match in pattern.finditer(text):
        clause_prefix = re.split(r"[.;:!?\n]", text[: match.start()])[-1]
        if not _NEGATED_ACTION_PREFIX.search(clause_prefix):
            return True
    return False


def explicitly_disallows_tools(text: str) -> bool:
    """Whether the user explicitly prohibited model tool use for this request."""
    return bool(_NO_TOOLS.search(text))


def without_tool_use_prohibition(text: str) -> str:
    """Remove a usage constraint when deciding the subject of a request."""
    return _NO_TOOLS.sub(" ", text)


def explicit_only_tool_names(text: str, available_names: set[str]) -> list[str] | None:
    """Resolve an explicit ``use only NAME`` boundary against callable names."""
    match = re.search(r"(?i)\b(?:use|call|invoke)\s+only\s+(.{1,160})", text)
    if match is None:
        return None
    clause = re.split(
        r"(?i)\b(?:to|for|then|when|because|but|not|no)\b|[.!?;\n]",
        match.group(1),
        maxsplit=1,
    )[0]
    positions = [
        (found.start(), name)
        for name in available_names
        if (found := re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", clause, re.IGNORECASE))
        is not None
    ]
    return [name for _position, name in sorted(positions)]


def explicit_workspace_inspection(text: str) -> bool:
    """Recognize a positive request to inspect the active workspace."""
    return bool(_WORKSPACE_SUBJECT.search(text)) and has_nonnegated_action(text, _WORKSPACE_ACTION)
