"""Web facade: search() and fetch() with caching — the only web interface
the agent sees."""

from __future__ import annotations

from klaude_core import Config

from .cache import TTLCache
from .fetch import fetch_page
from .search import searx_search

SEARCH_TTL = 3600       # 1 hour
PAGE_TTL = 24 * 3600    # 24 hours


class Web:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cache = TTLCache(cfg.data_dir / "webcache.db")

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        key = f"search::{query}::{max_results}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        results = searx_search(self.cfg.searxng_url, query, max_results)
        self.cache.set(key, results, SEARCH_TTL)
        return results

    def fetch(self, url: str) -> str:
        key = f"page::{url}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        text = fetch_page(url, self.cfg.crawl4ai_url)
        self.cache.set(key, text, PAGE_TTL)
        return text
