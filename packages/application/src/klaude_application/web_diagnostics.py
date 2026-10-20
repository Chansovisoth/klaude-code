"""Bounded private Web Search and URL Fetch configuration checks."""

from __future__ import annotations

import os
import time
from typing import Any

from klaude_core.fetch_settings import apply_fetch_settings
from klaude_core.search_settings import KEYS, PROVIDERS, apply_search_settings

FETCH_KEYS = {
    "crawl4ai": ("CRAWL4AI_API_KEY", "crawl4ai_api_key"),
    "exa": ("EXA_API_KEY", "exa_api_key"),
}
NAMES = {"crawl4ai": "Crawl4AI", "exa": "Exa"}

def run_search_test(request: dict[str, Any]) -> dict[str, Any]:
    """Private worker; no snippets, credentials or upstream errors in the result."""
    from klaude_core.config import load_config, provider_secret_value
    from klaude_web.providers import quality_search

    os.environ["KLAUDE_CONFIG_DIR"] = request["config_dir"]
    os.environ["KLAUDE_DATA_DIR"] = request["data_dir"]
    cfg = load_config()
    for name, (default_env, attr) in KEYS.items():
        reference = cfg.web_providers[name].api_key_env or default_env
        value = request.get("environment_keys", {}).get(reference)
        if isinstance(value, str) and len(value) <= 8192:
            os.environ[reference] = value
        fallback = getattr(cfg, attr, "") if reference == default_env else ""
        setattr(cfg, attr, provider_secret_value(cfg.config_dir, reference, fallback))
    apply_search_settings(cfg, request.get("settings"))
    for name, enabled in request.get("availability", {}).items():
        if name in cfg.web_providers and isinstance(enabled, bool):
            cfg.web_providers[name].enabled = enabled
    cfg.web_search.result_validation_enabled = request.get("validation") is not False
    if request.get("enabled") is False:
        return {"status": "disabled", "message": "Web Search is disabled", "attempted": []}
    query = str(request.get("query", "")).strip()
    provider = str(request.get("provider", ""))
    if not query or len(query) > 500 or provider not in {"", *PROVIDERS}:
        raise ValueError("Invalid search test")
    if provider:
        # Detail tests identify this provider, never silently test a fallback.
        cfg.web_search.allow_explicit_provider_fallback = False
    start = time.monotonic()
    try:
        response = quality_search(
            cfg,
            query,
            cfg.web_search.default_results,
            provider=provider or None,
            provider_strict=bool(provider),
        )
    except Exception:
        return {
            "status": "failed",
            "message": "Search test failed; check provider settings",
            "attempted": [],
            "count": 0,
        }
    attempted = [name for name in response.providers_attempted if name in PROVIDERS][:9]
    used = [name for name in response.providers_succeeded if name in PROVIDERS][:9]
    count = len(response.results)
    metadata = response.provider_metadata or {}
    states = [
        item.get("status")
        for item in metadata.get("provider_attempts", [])
        if isinstance(item, dict)
    ]
    status = "ok" if count else "empty" if used else "failed"
    if not count and "authentication_failed" in states:
        status = "authentication"
    elif not count and "quota_exhausted" in states:
        status = "quota"
    elif not count and "rate_limited" in states:
        status = "rate_limit"
    names = ", ".join(PROVIDERS[name] for name in used or attempted) or "No provider"
    issue = {
        "authentication": "Authentication failed",
        "quota": "Quota exhausted",
        "rate_limit": "Rate limited",
        "failed": "Search unavailable",
        "empty": "No results",
    }.get(status)
    return {
        "status": status,
        "message": f"{issue} · {names}" if issue else f"{names} · {count} results",
        "attempted": attempted,
        "used": used,
        "count": min(count, 50),
        "elapsed_ms": int((time.monotonic() - start) * 1000),
    }


def run_fetch_test(request: dict[str, Any]) -> dict[str, Any]:
    """Exercise the real uncached route, returning only sanitized outcome metadata."""
    from klaude_core.config import load_config, provider_secret_value
    from klaude_web.facade import Web
    from klaude_web.fetch import FetchPageError, UnsafeURL, canonicalize_public_url

    os.environ["KLAUDE_CONFIG_DIR"] = request["config_dir"]
    os.environ["KLAUDE_DATA_DIR"] = request["data_dir"]
    cfg = load_config()
    for provider, (env, attr) in FETCH_KEYS.items():
        reference = (cfg.web_providers["exa"].api_key_env or env) if provider == "exa" else env
        value = request.get("environment_keys", {}).get(reference)
        if isinstance(value, str) and len(value) <= 8192:
            os.environ[reference] = value
        fallback = getattr(cfg, attr, "") if reference == env else ""
        setattr(cfg, attr, provider_secret_value(cfg.config_dir, reference, fallback))
    apply_fetch_settings(cfg, request.get("settings"))
    if request.get("enabled") is False:
        return {"status": "disabled", "message": "URL Fetch is disabled"}
    provider = request.get("provider", "")
    if provider not in ("", "local", "crawl4ai", "exa"):
        raise ValueError("Invalid fetch provider")
    # Detail tests exercise exactly that extraction choice, without cloud fallback.
    if provider:
        cfg.web_fetch.settings_provider = "exa" if provider == "exa" else "local"
        cfg.web_fetch.exa_fallback = False
    start = time.monotonic()
    try:
        url = canonicalize_public_url(str(request.get("url", "")))
        result = Web(cfg)._fetch_uncached_detailed(
            url, extraction=provider if provider == "crawl4ai" else ""
        )
    except UnsafeURL:
        return {"status": "unsafe_url", "message": "URL blocked by public-address safety rules"}
    except FetchPageError as exc:
        reason = exc.failure_class
        labels = {
            "timeout": "Fetch timed out",
            "authentication": "Authentication failed",
            "rate_limit": "Rate limited",
            "disabled": "Provider is disabled",
            "configuration": "Provider configuration missing",
            "response_too_large": "Provider response too large",
        }
        return {
            "status": reason,
            "message": labels.get(reason, "Fetch failed; check URL and provider settings"),
        }
    except Exception:
        return {"status": "failed", "message": "Fetch failed; check URL and provider settings"}
    used = result.get("provider", "")
    used = used if used in {"direct", "trafilatura", *NAMES} else "unknown"
    fallback = bool(result.get("fallback_used"))
    return {
        "status": "ok",
        "provider": used,
        "attempted": [
            p
            for p in result.get("attempted_providers", [])
            if p in {"direct", "trafilatura", *NAMES}
        ][:4],
        "characters": min(len(result.get("content", "")), cfg.web_fetch.max_content_characters),
        "fallback": fallback,
        "elapsed_ms": int((time.monotonic() - start) * 1000),
        "message": f"{NAMES.get(used, used.title())} · "
        f"{len(result.get('content', '')):,} characters"
        + (" · cloud fallback used" if fallback else ""),
    }
