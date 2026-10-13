"""Independent URL Fetch preferences; credentials remain in the private store."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .search_settings import service_url

if TYPE_CHECKING:
    from .config import Config


def public_fetch_settings(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    values: dict[str, Any] = {}
    if raw.get("provider") in ("local", "exa"):
        values["provider"] = raw["provider"]
    for name in ("exa_fallback", "crawl4ai_enabled", "exa_enabled"):
        if isinstance(raw.get(name), bool):
            values[name] = raw[name]
    if isinstance(raw.get("crawl4ai_url"), str):
        try:
            value = raw["crawl4ai_url"].strip()
            values["crawl4ai_url"] = service_url(value) if value else ""
        except ValueError:
            pass
    return values


def apply_fetch_settings(cfg: Config, raw: Any) -> None:
    for name, value in public_fetch_settings(raw).items():
        if name == "crawl4ai_url":
            cfg.crawl4ai_url = value
        else:
            setattr(cfg.web_fetch, "settings_provider" if name == "provider" else name, value)


def fetch_provider(cfg: Config) -> str:
    return cfg.web_fetch.settings_provider or ("exa" if cfg.web_provider == "exa" else "local")


def exa_fallback(cfg: Config) -> bool:
    value = cfg.web_fetch.exa_fallback
    return cfg.web_provider == "auto" if value is None else value
