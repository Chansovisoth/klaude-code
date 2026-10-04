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
_NO_WEB_SEARCH = re.compile(
    r"\b(?:do\s+not|don['’]?t|dont|never|without|no)\b"
    r"[^,.;:!?\n]{0,70}\b(?:web[_ -]?search|search(?:ing)?\s+(?:the\s+)?"
    r"(?:web|internet)|brows(?:e|ing)\s+(?:the\s+)?web)\b",
    re.IGNORECASE,
)
_NO_WEB_SEARCH_IN_LIST = re.compile(
    r"\b(?:do\s+not|don['’]?t|dont|never)\b"
    r"[^.;:!?\n]{0,160}?\b(?:or\s+(?:use\s+)?(?:public\s+)?)"
    r"(?:web[_ -]?search|search(?:ing)?\s+(?:the\s+)?(?:web|internet))\b",
    re.IGNORECASE,
)
_NO_SKILL_READ = re.compile(
    r"\b(?:do\s+not|don['’]?t|dont|never|without)\b"
    r"[^,.;:!?\n]{0,70}\b(?:read(?:ing)?|open(?:ing)?|load(?:ing)?|consult(?:ing)?)\s+"
    r"(?:(?:the|any|an|installed|that)\s+){0,3}(?:skill\b|SKILL\.md\b)",
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


def explicit_local_file_read_request(text: str) -> bool:
    """Recognize a request to open a named workspace file without requiring 'file'."""
    without_urls = re.sub(r"https?://\S+", " ", text, flags=re.IGNORECASE)
    named_file = re.search(
        r"(?<![\w.])(?:/?[\w.-]+/)*[\w.-]+\."
        r"(?:md|txt|py|js|jsx|ts|tsx|json|toml|ya?ml|sh|html|css|csv|xml|"
        r"rs|go|java|c|cpp|h|sql|ipynb)\b",
        without_urls,
        re.IGNORECASE,
    )
    if named_file is None:
        return False
    return has_nonnegated_action(
        without_urls,
        r"\b(?:read|open|inspect|review|check|analy[sz]e|follow|"
        r"carry\s+out|implement|execute)\b",
    )


def prohibits_web_search(text: str) -> bool:
    """A specific web prohibition must not suppress permitted local retrieval."""
    return bool(_NO_WEB_SEARCH.search(text) or _NO_WEB_SEARCH_IN_LIST.search(text)) or bool(
        re.search(r"\b(?:offline only|no internet)\b", text, re.IGNORECASE)
    )


def prohibits_skill_read(text: str) -> bool:
    """Respect an explicit request to answer without opening Skill instructions."""
    return bool(_NO_SKILL_READ.search(text))


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
    if positions:
        return [name for _position, name in sorted(positions)]
    # "Use only the standard library" and similar implementation constraints
    # name resources, not tool permissions. Unknown explicit tool identifiers
    # still fail closed rather than widening an intended tool-only boundary.
    if re.search(r"\btools?\b|\b[a-z][a-z0-9]*_[a-z0-9_]+\b", clause, re.IGNORECASE):
        return []
    return None


def explicit_workspace_inspection(text: str) -> bool:
    """Recognize a positive request to inspect the active workspace."""
    return bool(_WORKSPACE_SUBJECT.search(text)) and has_nonnegated_action(text, _WORKSPACE_ACTION)
