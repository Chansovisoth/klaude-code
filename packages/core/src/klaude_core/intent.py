"""Small, deterministic intent predicates shared by routing and execution."""

from __future__ import annotations

import re
from re import Pattern


def requests_skill_guidance(text: str, names=()) -> bool:
    """Explicit Skill usage, including a known name written with spaces."""
    if prohibits_skill_read(text) or explicitly_disallows_tools(text):
        return False
    if re.match(r"(?i)^\s*(?:what|which|why|how|did|have|were)\b", text):
        return False
    if not has_nonnegated_action(text, r"\b(?:use|using|apply|follow|read)\b"):
        return False
    normalized = " ".join(re.findall(r"\w+", text.casefold()))
    return bool(re.search(r"\bskills?\b|SKILL\.md", text, re.I)) or any(
        " " + " ".join(re.findall(r"\w+", name.casefold())) + " "
        in " " + normalized + " " for name in names
    )

_NEGATED_ACTION_PREFIX = re.compile(
    r"(?:\b(?:do|does|did|can|could|should|would|will|must|please)\s+not\b|"
    r"\b(?:don['’]?t|dont|never|without)\b|\bno\s+need\s+to\b)"
    r"(?:\s+(?:[a-z0-9_-]+|and|or|just|any|the|this|that),?){0,5}\s*$",
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
        clause_prefix = re.split(r"[.;:!?\n]|\bbut\b", text[: match.start()], flags=re.I)[-1]
        if not _NEGATED_ACTION_PREFIX.search(clause_prefix):
            return True
    return False


def explicitly_disallows_tools(text: str) -> bool:
    """Whether the user explicitly prohibited model tool use for this request."""
    return bool(_NO_TOOLS.search(text))


def explicit_literal_response_request(text: str) -> bool:
    """A complete request to echo quoted text is not an instruction to run it."""
    return bool(re.fullmatch(
        r'\s*(?:please\s+)?(?:reply|respond|answer|say|repeat|print|echo|output|return)\s+'
        r'(?:(?:with|only|exactly|just)\s+)*'
        r'(?:"[^"\n]*"|\'[^\'\n]*\'|`[^`\n]*`|“[^”\n]*”|‘[^’\n]*’)\s*[.!?]?\s*',
        text, re.I,
    ))


def exact_literal_response(text: str) -> str | None:
    """Resolve only a whole, unconditional request for user-supplied literal text.

    Unquoted output must be one token with an explicit 'exactly' modifier.
    Destinations, conditions, transformations and additional actions do not match.
    Backslashes remain literal; this never evaluates code or looks up a value.
    """
    match = re.fullmatch(
        r'\s*(?:please\s+)?(?:reply|respond|answer|say|repeat|print|echo|output|return)\s+'
        r'(?P<modifiers>(?:(?:with|only|exactly|just)\s+)*)'
        r'(?:"(?P<double>[^"\n]{0,4096})"|\'(?P<single>[^\'\n]{0,4096})\'|'
        r'`(?P<backtick>[^`\n]{0,4096})`|“(?P<curly>[^”\n]{0,4096})”|'
        r'‘(?P<curly_single>[^’\n]{0,4096})’|(?P<bare>[\w-]{1,128}))'
        r'\s*[.!?]?\s*(?:(?:do not|don\x27t) use (?:any )?tools[.!]?\s*)?',
        text, re.I,
    )
    if match is None:
        return None
    if match['bare'] is not None and 'exactly' not in match['modifiers'].lower().split():
        return None
    payload = next(match[name] for name in (
        'double', 'single', 'backtick', 'curly', 'curly_single', 'bare'
    ) if match[name] is not None)
    return payload if all(c.isprintable() for c in payload) else None


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


def explicit_public_page_read_request(text: str) -> bool:
    """A named URL read remains distinct from permission to search for sources."""
    return has_nonnegated_action(
        text, r"\b(?:fetch|open|read|visit)\b[^.;!?\n]{0,80}https?://"
    )


def prohibits_web_search(text: str) -> bool:
    """A specific web prohibition must not suppress permitted local retrieval."""
    return bool(_NO_WEB_SEARCH.search(text) or _NO_WEB_SEARCH_IN_LIST.search(text)) or bool(
        re.search(r"\b(?:offline only|no internet)\b", text, re.IGNORECASE)
    )


def prohibits_skill_read(text: str) -> bool:
    """Respect an explicit request to answer without opening Skill instructions."""
    return bool(_NO_SKILL_READ.search(text))


def requests_external_lookup(text: str) -> bool:
    """Recognize an action request with an arbitrary object, including pronouns.

    This is a bounded bootstrap for observable lookup obligations, not a semantic
    planner. Local dictionary/file/library operations retain their own routing.
    The model resolves the object and chooses all queries from the conversation.
    """
    if explicitly_disallows_tools(text) or prohibits_web_search(text):
        return False
    # Quoted examples/code are not host-enforced action requests. Keep the
    # actual user message intact for the model; this only scopes the bootstrap.
    text = re.sub(
        r'```.*?(?:```|\Z)|`[^`\n]*`|(?<!\w)"[^"\n]*"|(?<!\w)\'[^\'\n]*\'|'
        r'“[^”\n]*”|‘[^’\n]*’',
        ' ', text, flags=re.S,
    )
    action = r"\blook\s+(?:(?:[\w'’-]+\s+){0,10})up\b"
    for match in re.finditer(action, text, re.I):
        prefix = re.split(r"[.;:!?\n]|\bbut\b", text[:match.start()], flags=re.I)[-1]
        if _NEGATED_ACTION_PREFIX.search(prefix):
            continue
        clause = re.split(r"[.;!?\n]|\band\b", text[match.start():], maxsplit=1, flags=re.I)[0]
        if re.search(r"\b(?:online|web|internet)\b", clause, re.I):
            return True
        if not re.search(
            r"\b(?:dictionary|dict|table|database|variable|key|workspace|repo(?:sitory)?|"
            r"knowledge|libraries|library|local docs?|indexed|file)\b|"
            r"\b[\w.-]+\.(?:md|py|js|ts|json|csv|toml|txt)\b", clause, re.I,
        ):
            return True
    return False


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
