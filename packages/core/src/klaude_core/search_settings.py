"""Bounded public Web Search preferences, separate from provider credentials."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from .config import Config

PROVIDERS = {
    "brave": "Brave (keyless)",
    "brave_api": "Brave Search API",
    "google": "Google Grounding",
    "parallel": "Parallel",
    "exa": "Exa",
    "ddgs": "DDGS (keyless)",
    "tavily": "Tavily",
    "firecrawl": "Firecrawl",
    "searxng": "SearXNG",
}
KEYS = {
    "brave_api": ("BRAVE_SEARCH_API_KEY", "brave_search_api_key"),
    "google": ("GEMINI_API_KEY", "gemini_api_key"),
    "parallel": ("PARALLEL_API_KEY", "parallel_api_key"),
    "tavily": ("TAVILY_API_KEY", "tavily_api_key"),
    "exa": ("EXA_API_KEY", "exa_api_key"),
    "firecrawl": ("FIRECRAWL_API_KEY", "firecrawl_api_key"),
}


def service_url(value: str) -> str:
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("Enter a valid HTTP(S) service endpoint") from None
    if (
        not value
        or len(value) > 2048
        or any(ord(c) < 33 for c in value)
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        raise ValueError("Use HTTP(S) without credentials, query or fragment")
    return urlunsplit(parsed)


def public_search_settings(raw: Any) -> dict[str, Any]:
    """Allowlist metadata in persistence acknowledgements and worker requests."""
    if not isinstance(raw, dict):
        return {}
    result: dict[str, Any] = {}
    provider = raw.get("provider")
    if isinstance(provider, str) and provider in {"auto", *PROVIDERS}:
        result["provider"] = provider
    count = raw.get("results")
    if type(count) is int and 1 <= count <= 50:
        result["results"] = count
    order = raw.get("fallbacks")
    if (
        isinstance(order, list)
        and len(order) <= len(PROVIDERS)
        and all(isinstance(name, str) and name in PROVIDERS for name in order)
    ):
        result["fallbacks"] = list(dict.fromkeys(order))
    if raw.get("tavily_depth") in ("basic", "advanced"):
        result["tavily_depth"] = raw["tavily_depth"]
    url = raw.get("searxng_url")
    if isinstance(url, str):
        try:
            result["searxng_url"] = service_url(url)
        except ValueError:
            pass
    return result


def apply_search_settings(cfg: Config, raw: Any) -> None:
    values = public_search_settings(raw)
    if "provider" in values:
        cfg.web_search.settings_provider = values["provider"]
    if "fallbacks" in values:
        cfg.web_search.settings_fallbacks = values["fallbacks"]
    if "results" in values:
        cfg.web_search.default_results = values["results"]
    if "searxng_url" in values:
        cfg.searxng_url = values["searxng_url"]
    if "tavily_depth" in values and "tavily" in cfg.web_providers:
        cfg.web_providers["tavily"].default_depth = values["tavily_depth"]


def primary_provider(cfg: Config) -> str:
    return cfg.web_search.settings_provider or {
        "local": "searxng",
        "exa": "exa",
        "brave": "brave",
        "brave_api": "brave_api",
    }.get(cfg.web_provider, "auto")
