"""SearXNG client. Requires 'json' in the instance's search.formats."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

LOOKUP_PREFIX_RE = re.compile(
    r"(?i)^\s*(?:who|what|where|when)\s+(?:is|are|was|were)\s+"
)
RESULT_LIST_PREFIX_RE = re.compile(
    r"(?i)^\s*(?:show|list|give|display|print|return|find|get)\s+"
    r"(?:me\s+)?(?:the\s+)?(?:(?:top|all)\s+)?(?:\d{1,3}\s+)?"
    r"(?:search\s+)?(?:results?|sources?|links?)\s*(?:about|for|on)?\s*"
)
SEARCH_VERB_PREFIX_RE = re.compile(
    r"(?i)^\s*(?:search|look up|lookup|research|find)\s+"
    r"(?:the\s+web\s+)?(?:for\s+)?"
)
STOP_WORDS = {
    "a",
    "all",
    "about",
    "an",
    "and",
    "are",
    "display",
    "find",
    "for",
    "get",
    "give",
    "in",
    "is",
    "link",
    "links",
    "list",
    "me",
    "more",
    "of",
    "on",
    "or",
    "print",
    "result",
    "results",
    "return",
    "search",
    "show",
    "source",
    "sources",
    "tell",
    "the",
    "them",
    "to",
    "top",
    "was",
    "were",
    "what",
    "when",
    "where",
    "who",
}
PRIORITY_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "twitch.tv",
    "tiktok.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "reddit.com",
    "github.com",
    "linkedin.com",
)
ACTIVITY_TERMS = {
    "call",
    "creator",
    "duty",
    "fortnite",
    "game",
    "games",
    "gamer",
    "gaming",
    "hypixel",
    "minecraft",
    "nhl",
    "play",
    "played",
    "plays",
    "record",
    "recorded",
    "records",
    "roblox",
    "stream",
    "streams",
    "streamer",
    "streaming",
    "upload",
    "uploads",
    "valorant",
    "video",
    "videos",
    "youtube",
    "twitch",
    "tiktok",
}
TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
}
LEET_SUBS = {
    "a": "4",
    "e": "3",
    "o": "0",
    "s": "5",
    "i": "1",
    "l": "1",
}


@dataclass(frozen=True)
class SearchResponse:
    results: list[dict]
    warnings: list[dict] = field(default_factory=list)
    queries_attempted: list[str] = field(default_factory=list)
    queries_failed: list[str] = field(default_factory=list)
    providers_attempted: list[str] = field(default_factory=list)
    providers_succeeded: list[str] = field(default_factory=list)
    provider_states: list[dict] = field(default_factory=list)
    provider_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "results": self.results,
            "warnings": self.warnings,
            "queries_attempted": self.queries_attempted,
            "queries_failed": self.queries_failed,
            "providers_attempted": self.providers_attempted,
            "providers_succeeded": self.providers_succeeded,
            "provider_states": self.provider_states,
            "provider_metadata": self.provider_metadata,
        }


def clean_search_query(query: str) -> str:
    """Remove conversational wrappers that make exact-name search noisier."""
    cleaned = query.strip()
    cleaned = RESULT_LIST_PREFIX_RE.sub("", cleaned).strip()
    cleaned = LOOKUP_PREFIX_RE.sub("", cleaned).strip()
    cleaned = SEARCH_VERB_PREFIX_RE.sub("", cleaned).strip()
    cleaned = cleaned.strip(" \t\r\n?.!:;\"'")
    return cleaned or query.strip()


def expand_search_queries(query: str, max_queries: int = 8) -> list[str]:
    """Build a small, evidence-oriented fanout for ambiguous names/handles."""
    cleaned = clean_search_query(query)
    queries: list[str] = []

    def add(candidate: str) -> None:
        candidate = " ".join(candidate.split())
        if candidate and candidate not in queries:
            queries.append(candidate)

    add(cleaned)
    entity = _entity_phrase(cleaned)
    if entity:
        add(f'"{entity}"')
    terms = _terms(cleaned)
    activity_terms = [term for term in terms if term in ACTIVITY_TERMS]

    if entity and activity_terms:
        activity = " ".join(activity_terms[:3])
        add(f'"{entity}" {activity} YouTube Twitch')
        add(f'site:youtube.com "{entity}" {activity}')
        add(f'site:twitch.tv "{entity}" {activity}')
        for variant in _handle_variants(entity):
            add(f'"{variant}" {activity}')
    elif entity and _looks_like_handle(entity):
        add(f'"{entity}" YouTube Twitch TikTok')
        add(f'site:youtube.com "{entity}"')
        add(f'site:twitch.tv "{entity}"')
        for variant in _handle_variants(entity):
            add(f'"{variant}"')

    return queries[:max_queries]


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _tokens(text: str) -> set[str]:
    return set(_normalized(text).split())


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and f" {phrase} " in f" {text} "


def _terms(query: str) -> list[str]:
    cleaned = clean_search_query(query)
    split_camel = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", cleaned)
    terms = []
    for source in (cleaned, split_camel):
        for term in re.findall(r"[a-z0-9]+", source.lower()):
            if (
                len(term) > 1
                and term not in STOP_WORDS
                and not term.isdigit()
                and term not in terms
            ):
                terms.append(term)
    return terms


def _entity_phrase(query: str) -> str:
    words = re.findall(r"[A-Za-z0-9_.-]+", clean_search_query(query))
    entity_words = [
        word
        for word in words
        if (
            word.lower() not in STOP_WORDS
            and word.lower() not in ACTIVITY_TERMS
            and not word.isdigit()
        )
    ]
    return " ".join(entity_words[:3])


def _looks_like_handle(query: str) -> bool:
    stripped = query.strip()
    return (
        len(stripped.split()) == 1
        or "_" in stripped
        or "." in stripped
        or any(char.isdigit() for char in stripped)
        or bool(re.search(r"[a-z][A-Z]", stripped))
    )


def _is_entity_lookup(query: str) -> bool:
    cleaned = clean_search_query(query)
    entity = _entity_phrase(cleaned)
    if not entity:
        return False
    if _looks_like_handle(entity):
        return True
    words = entity.split()
    return 1 <= len(words) <= 4 and any(word[:1].isupper() for word in words)


def _handle_variants(entity: str, max_variants: int = 8) -> list[str]:
    compact = "".join(re.findall(r"[A-Za-z0-9]+", entity))
    if not compact or not _looks_like_handle(compact):
        return []
    variants: list[str] = []
    for source, replacement in LEET_SUBS.items():
        for index, char in enumerate(compact):
            if char.lower() != source:
                continue
            candidate = f"{compact[:index]}{replacement}{compact[index + 1:]}"
            if candidate.lower() != compact.lower() and candidate not in variants:
                variants.append(candidate)
            if len(variants) >= max_variants:
                return variants
    return variants


def _entity_variants(entity: str) -> list[str]:
    variants: list[str] = []
    for candidate in [entity, *_handle_variants(entity)]:
        normalized = _normalized(candidate)
        if normalized and normalized not in variants:
            variants.append(normalized)
    return variants


def _activity_terms(query: str) -> list[str]:
    return [term for term in _terms(query) if term in ACTIVITY_TERMS]


def _canonical_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    netloc = hostname
    if parsed.port and not (
        (parsed.scheme.lower() == "http" and parsed.port == 80)
        or (parsed.scheme.lower() == "https" and parsed.port == 443)
    ):
        netloc = f"{hostname}:{parsed.port}"
    query = urlencode(
        [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
        ]
    )
    return urlunparse(
        (
            parsed.scheme.lower(),
            netloc,
            parsed.path.rstrip("/") or "/",
            "",
            query,
            "",
        )
    )


def _has_entity_match(query: str, result: dict) -> bool:
    entity = _entity_phrase(query)
    if not entity or not _looks_like_handle(entity):
        return True

    entity_variants = _entity_variants(entity)
    entity_terms = set(_terms(entity))
    if not entity_variants and not entity_terms:
        return True

    title = _normalized(result.get("title", ""))
    url = _normalized(result.get("url", ""))
    snippet = _normalized(result.get("snippet", ""))
    if any(
        _contains_phrase(title, variant)
        or _contains_phrase(url, variant)
        or _contains_phrase(snippet, variant)
        for variant in entity_variants
    ):
        return True

    title_tokens = _tokens(result.get("title", ""))
    url_tokens = _tokens(result.get("url", ""))
    snippet_tokens = _tokens(result.get("snippet", ""))
    matched_terms = {
        term
        for term in entity_terms
        if term in title_tokens or term in url_tokens or term in snippet_tokens
    }
    return len(matched_terms) >= min(2, len(entity_terms))


def _entity_match_score(query: str, result: dict) -> float:
    entity = _entity_phrase(query)
    if not entity:
        return 1.0
    variants = _entity_variants(entity)
    entity_terms = set(_terms(entity))
    title = _normalized(result.get("title", ""))
    url = _normalized(result.get("url", ""))
    title_tokens = _tokens(result.get("title", ""))
    url_tokens = _tokens(result.get("url", ""))
    snippet_tokens = _tokens(result.get("snippet", ""))
    domain = urlparse(result.get("url", "")).netloc.lower().removeprefix("www.")
    score = 0.0
    if variants and _contains_phrase(title, variants[0]):
        score += 1.0
    if any(_contains_phrase(url, variant) for variant in variants):
        score += 0.85
    if entity_terms and entity_terms <= title_tokens:
        score += 0.75
    coverage = 0.0
    if entity_terms:
        coverage = len(entity_terms & (title_tokens | snippet_tokens | url_tokens)) / len(
            entity_terms
        )
    score += coverage * 0.45
    if any(domain.endswith(priority) for priority in PRIORITY_DOMAINS):
        score += 0.15
    return score


def _result_score(query: str, result: dict, index: int) -> float:
    terms = _terms(query)
    if not terms:
        return -index / 1000

    title = _normalized(result.get("title", ""))
    url = _normalized(result.get("url", ""))
    snippet = _normalized(result.get("snippet", ""))
    title_tokens = _tokens(result.get("title", ""))
    url_tokens = _tokens(result.get("url", ""))
    snippet_tokens = _tokens(result.get("snippet", ""))
    all_tokens = title_tokens | url_tokens | snippet_tokens
    phrase = _normalized(clean_search_query(query))
    entity = _entity_phrase(query)
    entity_variants = _entity_variants(entity)
    entity_terms = _terms(entity)
    domain = urlparse(result.get("url", "")).netloc.lower().removeprefix("www.")
    activity_terms = _activity_terms(query)
    score = -index / 1000
    exact_entity_match = False

    for variant_index, entity_variant in enumerate(entity_variants):
        title_boost = 60 if variant_index == 0 else 45
        url_boost = 45 if variant_index == 0 else 32
        snippet_boost = 12 if variant_index == 0 else 10
        if _contains_phrase(title, entity_variant):
            score += title_boost
            exact_entity_match = True
        if _contains_phrase(url, entity_variant):
            score += url_boost
            exact_entity_match = True
        if _contains_phrase(snippet, entity_variant):
            score += snippet_boost
            exact_entity_match = True

    if phrase and phrase not in entity_variants:
        if _contains_phrase(title, phrase):
            score += 25
        if _contains_phrase(url, phrase):
            score += 18
        if _contains_phrase(snippet, phrase):
            score += 6

    entity_title_url_terms: set[str] = set()
    entity_any_terms: set[str] = set()
    for term in entity_terms:
        in_title = term in title_tokens
        in_url = term in url_tokens
        in_snippet = term in snippet_tokens
        if in_title:
            score += 16
            entity_title_url_terms.add(term)
            entity_any_terms.add(term)
        if in_url:
            score += 12
            entity_title_url_terms.add(term)
            entity_any_terms.add(term)
        if in_snippet:
            score += 3
            entity_any_terms.add(term)

    required_entity_matches = min(2, len(entity_terms)) if entity_terms else 0
    strong_entity_match = exact_entity_match or (
        required_entity_matches > 0
        and len(entity_title_url_terms) >= required_entity_matches
    )

    non_entity_terms = [
        term
        for term in terms
        if term not in entity_terms and term not in activity_terms
    ]
    for term in non_entity_terms:
        if term in title_tokens:
            score += 6
        if term in url_tokens:
            score += 4
        if term in snippet_tokens:
            score += 1

    if activity_terms:
        activity_matches = sum(
            1
            for term in activity_terms
            if term in title_tokens or term in url_tokens or term in snippet_tokens
        )
        if strong_entity_match:
            if activity_matches:
                score += activity_matches * 40
            else:
                score -= 10
        elif activity_matches and entity:
            score -= 18
        elif activity_matches:
            score += activity_matches * 8
        else:
            score -= 12

    if strong_entity_match and any(domain.endswith(priority) for priority in PRIORITY_DOMAINS):
        score += 5
    if entity and not strong_entity_match:
        score -= 16
    if not entity_title_url_terms and any(term in snippet_tokens for term in terms):
        score -= 4
    if not any(term in all_tokens for term in terms) and not exact_entity_match:
        score -= 10
    if entity_terms and not entity_any_terms:
        score -= 10
    return score


def rank_search_results(query: str, results: list[dict]) -> list[dict]:
    ranked = sorted(
        enumerate(results),
        key=lambda item: _result_score(query, item[1], item[0]),
        reverse=True,
    )
    return [result for _index, result in ranked]


def _filter_relevant_results(query: str, results: list[dict]) -> list[dict]:
    if not _is_entity_lookup(query):
        return [result for result in results if _has_entity_match(query, result)]
    relevant = [
        result
        for result in results
        if _has_entity_match(query, result) and _entity_match_score(query, result) >= 0.75
    ]
    return relevant


def _merge_results(query: str, results: list[dict]) -> list[dict]:
    by_url: dict[str, dict] = {}
    scores: dict[str, float] = {}
    for index, result in enumerate(results):
        url = result.get("url", "")
        key = _canonical_url(url) if url else f"missing-url-{index}"
        score = _result_score(query, result, index)
        if key not in by_url or score > scores[key]:
            by_url[key] = result
            scores[key] = score
    return list(by_url.values())


def searx_search_detailed(
    base_url: str,
    query: str,
    max_results: int = 8,
    *,
    relevance_filter: bool = True,
) -> SearchResponse:
    query = clean_search_query(query)
    collected: list[dict] = []
    warnings: list[dict] = []
    attempted: list[str] = []
    failed: list[str] = []
    per_query = max(max_results, 8)
    for search_query in expand_search_queries(query):
        attempted.append(search_query)
        try:
            r = httpx.get(
                f"{base_url.rstrip('/')}/search",
                params={"q": search_query, "format": "json", "language": "en-US"},
                timeout=20,
            )
            if r.status_code == 403:
                raise RuntimeError(
                    "SearXNG returned 403 — JSON format is not enabled. "
                    "Add 'json' under search.formats in deploy/searxng/settings.yml."
                )
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:
            failed.append(search_query)
            warnings.append(
                {
                    "query": search_query,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
            continue
        collected.extend(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "snippet": item.get("content", ""),
                "matched_query": search_query,
            }
            for item in payload.get("results", [])[:per_query]
        )
    if not collected and failed:
        raise RuntimeError(
            "all SearXNG expanded queries failed: "
            + "; ".join(f"{w['query']}: {w['message']}" for w in warnings)
        )
    merged = _merge_results(query, collected)
    ranked_source = _filter_relevant_results(query, merged) if relevance_filter else merged
    ranked = rank_search_results(query, ranked_source)[:max_results]
    if collected and _is_entity_lookup(query) and not ranked:
        warnings.append(
            {
                "query": query,
                "error_type": "NoRelevantMatch",
                "message": "no relevant entity match found",
            }
        )
    return SearchResponse(
        results=ranked,
        warnings=warnings,
        queries_attempted=attempted,
        queries_failed=failed,
        providers_attempted=["searxng"] if attempted else [],
        providers_succeeded=["searxng"] if ranked else [],
    )


def searx_search(base_url: str, query: str, max_results: int = 8) -> list[dict]:
    return searx_search_detailed(base_url, query, max_results).results
