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


def explicit_workspace_inspection(text: str) -> bool:
    """Recognize a positive request to inspect the active workspace."""
    return bool(_WORKSPACE_SUBJECT.search(text)) and has_nonnegated_action(
        text, _WORKSPACE_ACTION
    )
