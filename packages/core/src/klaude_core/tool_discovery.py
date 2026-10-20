"""Bounded metadata search; loading a schema never executes or authorizes it."""

from __future__ import annotations

import re
from collections.abc import Iterable

DESCRIPTION = (
    "Find enabled tools or installed Skills for the next action when the supplied "
    "tools are insufficient. Search by task or exact name. Matching tool schemas "
    "become available on the NEXT response; this does not run them or grant permission."
)
PARAMETERS = {
    "type": "object",
    "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 240}},
    "required": ["query"],
    "additionalProperties": False,
}
MAX_CALLS = 4
MAX_LOADED = 12
MAX_RESULTS = 4
MAX_CATALOG = 1000
_STOP = frozenset(
    "a an and are can for from how i in is it me of on please the to tool tools use with".split()
)


def clean(value: str, limit: int = 280) -> str:
    return " ".join("".join(c if c.isprintable() else " " for c in value).split())[:limit]


def matches(query: str, entries: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Return deterministic metadata matches, never untrusted instructions."""
    query = clean(query, 240).casefold()
    words = set(re.findall(r"[\w]+", query.replace("_", " "))) - _STOP
    ranked = []
    for index, (name, description) in enumerate(entries):
        if index >= MAX_CATALOG:
            break
        description = clean(description)
        if query in {name.casefold(), name.removeprefix("skill:").casefold()}:
            return [(name, description)]
        tokens = set(re.findall(r"[\w]+", f"{name} {description}".casefold().replace("_", " ")))
        score = len(words & tokens)
        if score:
            ranked.append((score, name, description))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(name, description) for _, name, description in ranked[:MAX_RESULTS]]
