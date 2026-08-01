"""Web facade: search() and fetch() with caching — the only web interface
the agent sees."""

from __future__ import annotations

from klaude_core import Config

from .cache import TTLCache
from .crawler import crawl_site as crawl_site_pages
from .exa import exa_fetch, exa_search
from .fetch import fetch_page
from .huggingface import hub_repo_details, hub_repo_readme, hub_repo_search
from .providers import (
    SearchIntent,
    build_search_query,
    quality_search,
    search_cache_key,
    search_cache_ttl,
)
from .search import SearchResponse, searx_search_detailed

SEARCH_TTL = 3600       # 1 hour
PAGE_TTL = 24 * 3600    # 24 hours


class Web:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cache = TTLCache(cfg.data_dir / "webcache.db")

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        return self.search_detailed(query, max_results).results

    def search_detailed(
        self,
        query: str,
        max_results: int = 8,
        *,
        intent: SearchIntent | str | None = None,
    ) -> SearchResponse:
        original_query = query
        search_query = build_search_query(original_query, self.cfg, max_results, intent=intent)
        key = search_cache_key(self.cfg, search_query)
        if self.cfg.web_search.cache_enabled:
            hit = self.cache.get(key)
            if hit is not None:
                return SearchResponse(**hit)
        response = self._search_uncached_detailed(original_query, max_results, intent=intent)
        if self.cfg.web_search.cache_enabled:
            self.cache.set(key, response.to_dict(), search_cache_ttl(search_query))
        return response

    def fetch(self, url: str) -> str:
        key = f"page::{self.cfg.web_provider}::{url}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        text = self._fetch_uncached(url)
        self.cache.set(key, text, PAGE_TTL)
        return text

    def code_search(self, query: str, max_results: int = 8) -> list[dict]:
        key = f"code_search_v2::{self.cfg.web_provider}::{query}::{max_results}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        if self.cfg.web_provider == "exa":
            results = exa_search(
                self.cfg.exa_base_url,
                self.cfg.exa_api_key,
                query,
                max_results,
                code_context=True,
            )
        else:
            results = self.search_detailed(
                f"{query} code examples official documentation GitHub Stack Overflow",
                max_results,
                intent=SearchIntent.TECHNICAL_DOCUMENTATION,
            ).results
        self.cache.set(key, results, SEARCH_TTL)
        return results

    def huggingface_search(
        self,
        repo_type: str,
        query: str = "",
        max_results: int = 10,
        sort: str = "downloads",
    ) -> list[dict]:
        key = f"huggingface_search::{repo_type}::{query}::{max_results}::{sort}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        results = hub_repo_search(
            self.cfg.huggingface_base_url,
            self.cfg.huggingface_api_key,
            repo_type,
            query,
            max_results,
            sort,
        )
        self.cache.set(key, results, SEARCH_TTL)
        return results

    def huggingface_details(self, repo_type: str, repo_id: str) -> dict:
        key = f"huggingface_details::{repo_type}::{repo_id}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        result = hub_repo_details(
            self.cfg.huggingface_base_url,
            self.cfg.huggingface_api_key,
            repo_type,
            repo_id,
        )
        self.cache.set(key, result, PAGE_TTL)
        return result

    def huggingface_readme(self, repo_type: str, repo_id: str) -> str:
        key = f"huggingface_readme::{repo_type}::{repo_id}"
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        text = hub_repo_readme(
            self.cfg.huggingface_base_url,
            self.cfg.huggingface_api_key,
            repo_type,
            repo_id,
        )
        self.cache.set(key, text, PAGE_TTL)
        return text

    def crawl_site(
        self,
        start_url: str,
        max_depth: int | None = None,
        max_pages: int | None = None,
        pattern: str = "*",
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        use_sitemap: bool = False,
        respect_robots: bool | None = None,
        delay_min: float | None = None,
        delay_max: float | None = None,
        on_progress=None,
    ) -> dict:
        result = crawl_site_pages(
            start_url,
            self.fetch,
            max_depth=self.cfg.crawl_max_depth if max_depth is None else max_depth,
            max_pages=self.cfg.crawl_max_pages if max_pages is None else max_pages,
            pattern=pattern,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            use_sitemap=use_sitemap,
            respect_robots=(
                self.cfg.crawl_respect_robots if respect_robots is None else respect_robots
            ),
            delay_min=self.cfg.crawl_delay_min if delay_min is None else delay_min,
            delay_max=self.cfg.crawl_delay_max if delay_max is None else delay_max,
            user_agent=self.cfg.crawler_user_agent,
            on_progress=on_progress,
        )
        return {
            "start_url": result.start_url,
            "pages": [
                {"url": page.url, "markdown": page.markdown, "depth": page.depth}
                for page in result.pages
            ],
            "errors": [
                {"url": error.url, "depth": error.depth, "error": error.error}
                for error in result.errors
            ],
            "skipped": result.skipped,
            "seeded": result.seeded,
        }

    def _search_uncached(self, query: str, max_results: int) -> list[dict]:
        return self._search_uncached_detailed(query, max_results).results

    def _search_uncached_detailed(
        self,
        query: str,
        max_results: int,
        *,
        intent: SearchIntent | str | None = None,
    ) -> SearchResponse:
        if (
            self.cfg.web_search.strategy == "quality"
            and self.cfg.web_provider in {"quality", "auto"}
        ):
            return quality_search(self.cfg, query, max_results, intent=intent)
        if self.cfg.web_provider == "quality":
            return quality_search(self.cfg, query, max_results, intent=intent)
        if self.cfg.web_provider == "exa":
            return SearchResponse(
                results=exa_search(self.cfg.exa_base_url, self.cfg.exa_api_key, query, max_results),
                warnings=[],
                queries_attempted=[query],
                queries_failed=[],
                providers_attempted=["exa"],
                providers_succeeded=["exa"],
            )
        try:
            return searx_search_detailed(self.cfg.searxng_url, query, max_results)
        except Exception:
            if self.cfg.web_provider == "auto" and self.cfg.exa_api_key:
                return SearchResponse(
                    results=exa_search(
                        self.cfg.exa_base_url,
                        self.cfg.exa_api_key,
                        query,
                        max_results,
                    ),
                    warnings=[
                        {
                            "query": query,
                            "error_type": "SearXNGFallback",
                            "message": "used Exa fallback",
                        }
                    ],
                    queries_attempted=[query],
                    queries_failed=[query],
                    providers_attempted=["searxng", "exa"],
                    providers_succeeded=["exa"],
                )
            raise

    def _fetch_uncached(self, url: str) -> str:
        if self.cfg.web_provider == "exa":
            return exa_fetch(self.cfg.exa_base_url, self.cfg.exa_api_key, url)
        try:
            return fetch_page(url, self.cfg.crawl4ai_url, self.cfg.crawl4ai_api_key)
        except Exception:
            if self.cfg.web_provider == "auto" and self.cfg.exa_api_key:
                return exa_fetch(self.cfg.exa_base_url, self.cfg.exa_api_key, url)
            raise
