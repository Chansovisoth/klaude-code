"""Bounded, in-memory MCP Registry search hints."""

from __future__ import annotations

from collections.abc import Iterable

from .pickers import match_score

# These are search terms, not claimed registry entries or popularity rankings.
# Keep them useful before the first network response and when the registry is offline.
SUGGESTED_SEARCHES = (
    "Context7",
    "GitHub",
    "filesystem",
    "Playwright",
    "Postgres",
    "Slack",
)


def search_suggestions(query: str, registry_names: Iterable[str] = ()) -> list[tuple[str, str]]:
    """Rank at most eight bounded hints without network, disk, or credentials."""
    if len(query) > 120 or any(not char.isprintable() for char in query):
        return []
    needle = query.strip().casefold()
    candidates: dict[str, tuple[str, str]] = {}
    for index, name in enumerate(registry_names):
        if index >= 200:
            break
        if not name or len(name) > 120 or any(not char.isprintable() for char in name):
            continue
        candidates.setdefault(name.casefold(), (name, "loaded registry result"))
    for term in SUGGESTED_SEARCHES:
        candidates.setdefault(term.casefold(), (term, "suggested search"))
    ranked = [
        (match_score(name, needle) if needle else 0, name, source)
        for name, source in candidates.values()
    ]
    ranked = [item for item in ranked if not needle or item[0] >= 0.45]
    suggested_order = {term.casefold(): index for index, term in enumerate(SUGGESTED_SEARCHES)}
    ranked.sort(key=lambda item: (
        item[2] != "loaded registry result",
        -item[0],
        suggested_order.get(item[1].casefold(), len(SUGGESTED_SEARCHES)),
        item[1].casefold(),
    ))
    return [(name, source) for _, name, source in ranked[:8]]
