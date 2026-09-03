"""Web facade: search() and fetch() with caching — the only web interface
the agent sees."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

from klaude_core import Config, EntityResolver, WikimediaEntityClient

from .cache import TTLCache
from .crawler import crawl_site as crawl_site_pages
from .exa import exa_fetch, exa_search
from .fetch import (
    FetchLimits,
    FetchPageError,
    UnsafeURL,
    canonical_url_key,
    canonicalize_public_url,
    fetch_page_detailed,
    resolve_public_url,
    validate_public_url,
)
from .huggingface import hub_repo_details, hub_repo_readme, hub_repo_search
from .providers import (
    DEFAULT_ENTITY_RESOLVER,
    SearchIntent,
    build_search_query,
    quality_search,
    search_cache_key,
    search_cache_ttl,
)
from .search import SearchResponse, searx_search_detailed
from .sources import SourceRegistry

SEARCH_TTL = 3600       # 1 hour
PAGE_TTL = 24 * 3600    # 24 hours


def _cacheable_search_response(response: SearchResponse) -> bool:
    """Cache evidence-bearing searches, never transient or total failures."""
    return bool(response.results)


class Web:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.cache = TTLCache(cfg.data_dir / "webcache.db")
        self.sources = SourceRegistry()
        wikimedia = None
        if cfg.entity_resolution.wikimedia_enabled:
            wikimedia = WikimediaEntityClient(
                user_agent=cfg.crawler_user_agent,
                timeout_seconds=cfg.entity_resolution.wikimedia_timeout_seconds,
                max_results=cfg.entity_resolution.wikimedia_max_results,
            )
        self.entity_resolver = EntityResolver(
            cfg.entities_db,
            wikimedia_client=wikimedia,
            metadata_ttl_days=cfg.entity_resolution.metadata_refresh_days,
        )

    def _source_registry(self) -> SourceRegistry:
        registry = getattr(self, "sources", None)
        if registry is None:
            registry = SourceRegistry()
            self.sources = registry
        return registry

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        return self.search_detailed(query, max_results).results

    def search_detailed(
        self,
        query: str,
        max_results: int = 8,
        *,
        intent: SearchIntent | str | None = None,
        provider: str | None = None,
        provider_strict: bool = False,
    ) -> SearchResponse:
        original_query = query
        resolver = getattr(self, "entity_resolver", DEFAULT_ENTITY_RESOLVER)
        search_query = build_search_query(
            original_query,
            self.cfg,
            max_results,
            intent=intent,
            provider_preference=provider,
            provider_strict=provider_strict,
            entity_resolver=resolver,
            allow_wikimedia=bool(
                getattr(self.cfg, "entity_resolution", None)
                and self.cfg.entity_resolution.wikimedia_enabled
            ),
        )
        provider = provider or search_query.provider_preference
        provider_strict = bool(provider_strict or search_query.provider_strict)
        key = search_cache_key(self.cfg, search_query)
        if self.cfg.web_search.cache_enabled:
            hit = self.cache.get(key)
            if hit is not None:
                cached_response = SearchResponse(**hit)
                if _cacheable_search_response(cached_response):
                    return self._finalize_search_response(
                        cached_response, search_query, resolver
                    )
        response = self._search_uncached_detailed(
            search_query.normalized_text or original_query,
            max_results,
            intent=intent,
            provider=provider,
            provider_strict=provider_strict,
        )
        if self.cfg.web_search.cache_enabled and _cacheable_search_response(response):
            self.cache.set(key, response.to_dict(), search_cache_ttl(search_query))
        return self._finalize_search_response(response, search_query, resolver)

    def _finalize_search_response(
        self,
        response: SearchResponse,
        search_query,
        resolver: EntityResolver,
    ) -> SearchResponse:
        metadata = dict(response.provider_metadata or {})
        metadata["original_text"] = search_query.original_text
        metadata["normalized_text"] = search_query.normalized_text
        metadata["corrections"] = [
            correction.to_dict() for correction in search_query.corrections
        ]
        metadata["query_provenance"] = [
            item.to_dict() for item in search_query.query_provenance
        ]
        learned = resolver.learn_from_search_metadata(metadata)
        if learned is not None:
            metadata["entity_cache"] = {
                "learned": learned.canonical_name,
                "aliases": list(learned.aliases),
                "source": learned.source,
            }
        if search_query.corrections:
            correction_text = " | ".join(
                f"{item.original} -> {item.corrected} [{item.kind}]"
                for item in search_query.corrections
            )
            queries = " | ".join(response.queries_attempted[:4])
            result_count = metadata.get("result_count")
            plausible = metadata.get("plausible_candidate_count")
            lines = [
                f"Input: {search_query.original_text}",
                f"Normalized: {search_query.normalized_text}",
                f"Correction: {correction_text}",
            ]
            if queries:
                lines.append(f"Queries: {queries}")
            if result_count is not None and plausible is not None:
                lines.append(
                    f"Returned {result_count} results; {plausible} plausible candidates."
                )
            metadata["display_lines"] = lines
        results = self._source_registry().register_search_results(
            search_query.normalized_text or search_query.text,
            response.results,
        )
        return SearchResponse(
            results=results,
            warnings=response.warnings,
            queries_attempted=response.queries_attempted,
            queries_failed=response.queries_failed,
            providers_attempted=response.providers_attempted,
            providers_succeeded=response.providers_succeeded,
            provider_states=response.provider_states,
            provider_metadata=metadata,
        )

    def fetch(self, url: str) -> str:
        return str(self.fetch_detailed(url).get("content", ""))

    def fetch_detailed(self, url: str) -> dict:
        try:
            requested_url = canonicalize_public_url(url)
            url_key = canonical_url_key(requested_url)
        except UnsafeURL as exc:
            return self._fetch_failure(url, exc, "unsafe_url", transient=False)

        sources = self._source_registry()
        registered = sources.source_for_url(requested_url)
        if registered is not None:
            return {
                **registered.to_dict(),
                "canonical_url": url_key,
                "status": "succeeded",
                "provider": "registry",
                "provider_label": "cache",
                "attempted_providers": [],
                "successful_providers": [],
                "cache_hit": True,
                "source_reused": True,
                "untrusted_external_evidence": True,
            }
        previous_failure = sources.failure_for_url(requested_url)
        if previous_failure is not None:
            return {**previous_failure, "attempt_reused": True}

        key = f"page_v2::{self.cfg.web_provider}::{url_key}"
        hit = self.cache.get(key)
        if hit is not None:
            if isinstance(hit, dict) and "content" in hit:
                cached = {**hit, "cache_hit": True}
            else:
                cached = {
                    "requested_url": requested_url,
                    "final_url": requested_url,
                    "title": "",
                    "domain": urlparse(requested_url).hostname or "",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "published_at": None,
                    "author": None,
                    "content": str(hit),
                    "fetch_status": "succeeded",
                    "extraction_status": "unknown",
                    "provider": "cache",
                    "provider_label": "cache",
                    "attempted_providers": [],
                    "successful_providers": [],
                    "cache_hit": True,
                    "untrusted_external_evidence": True,
                }
            source = sources.register_source(cached)
            return {
                **cached,
                **source.to_dict(),
                "canonical_url": url_key,
                "status": "succeeded",
                "provider_label": "cache",
                "cache_hit": True,
                "source_reused": True,
                "untrusted_external_evidence": True,
            }
        try:
            result = self._fetch_uncached_detailed(requested_url)
        except UnsafeURL as exc:
            result = self._fetch_failure(
                requested_url, exc, "unsafe_url", transient=False
            )
            sources.register_failure(requested_url, result)
            return result
        except FetchPageError as exc:
            result = self._fetch_failure(
                requested_url,
                exc,
                exc.failure_class,
                transient=exc.transient,
            )
            sources.register_failure(requested_url, result)
            return result
        except Exception as exc:
            result = self._fetch_failure(
                requested_url,
                exc,
                "fetch_failure",
                transient=True,
            )
            sources.register_failure(requested_url, result)
            return result

        source = sources.register_source(result)
        response = {
            **result,
            **source.to_dict(),
            "canonical_url": url_key,
            "status": "succeeded",
            "cache_hit": False,
            "source_reused": source.requested_url != result["requested_url"],
            "untrusted_external_evidence": True,
        }
        cache_value = dict(response)
        cache_value.pop("source_id", None)
        self.cache.set(key, cache_value, self.cfg.web_fetch.cache_ttl_seconds)
        return response

    def _fetch_failure(
        self,
        url: str,
        exc: Exception,
        failure_class: str,
        *,
        transient: bool,
    ) -> dict:
        try:
            requested_url = canonicalize_public_url(url)
        except ValueError:
            requested_url = str(url)
        try:
            canonical_url = canonical_url_key(requested_url)
        except ValueError:
            canonical_url = ""
        return {
            "status": "failed",
            "content": "",
            "requested_url": requested_url,
            "canonical_url": canonical_url,
            "final_url": str(getattr(exc, "final_url", "") or ""),
            "source_id": None,
            "fetch_status": "failed",
            "extraction_status": "not_available",
            "provider": "none",
            "provider_label": "none",
            "attempted_providers": list(
                getattr(exc, "attempted_providers", ()) or ()
            ),
            "successful_providers": [],
            "cache_hit": False,
            "redirect_count": int(getattr(exc, "redirect_count", 0) or 0),
            "download_status": "failed",
            "content_length": 0,
            "untrusted_external_evidence": True,
            "failure": {
                "reason": str(exc),
                "class": failure_class,
                "transient": transient,
            },
        }

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
        provider: str | None = None,
        provider_strict: bool = False,
    ) -> SearchResponse:
        search_query = build_search_query(query, self.cfg, max_results, intent=intent)
        semantic_query = search_query.text
        if provider:
            return quality_search(
                self.cfg,
                query,
                max_results,
                intent=intent,
                provider=provider,
                provider_strict=provider_strict,
            )
        if (
            self.cfg.web_search.strategy == "quality"
            and self.cfg.web_provider in {"quality", "auto"}
        ):
            return quality_search(
                self.cfg,
                query,
                max_results,
                intent=intent,
                provider=provider,
                provider_strict=provider_strict,
            )
        if self.cfg.web_provider == "quality":
            return quality_search(
                self.cfg,
                query,
                max_results,
                intent=intent,
                provider=provider,
                provider_strict=provider_strict,
            )
        if self.cfg.web_provider == "exa":
            return SearchResponse(
                results=exa_search(
                    self.cfg.exa_base_url,
                    self.cfg.exa_api_key,
                    semantic_query,
                    max_results,
                ),
                warnings=[],
                queries_attempted=[semantic_query],
                queries_failed=[],
                providers_attempted=["exa"],
                providers_succeeded=["exa"],
            )
        try:
            return searx_search_detailed(self.cfg.searxng_url, semantic_query, max_results)
        except Exception:
            if self.cfg.web_provider == "auto" and self.cfg.exa_api_key:
                return SearchResponse(
                    results=exa_search(
                        self.cfg.exa_base_url,
                        self.cfg.exa_api_key,
                        semantic_query,
                        max_results,
                    ),
                    warnings=[
                        {
                            "query": semantic_query,
                            "error_type": "SearXNGFallback",
                            "message": "used Exa fallback",
                        }
                    ],
                    queries_attempted=[semantic_query],
                    queries_failed=[semantic_query],
                    providers_attempted=["searxng", "exa"],
                    providers_succeeded=["exa"],
                )
            raise

    def _fetch_uncached(self, url: str) -> str:
        return str(self._fetch_uncached_detailed(url).get("content", ""))

    def _fetch_uncached_detailed(self, url: str) -> dict:
        if self.cfg.web_provider == "exa":
            requested_url = canonicalize_public_url(url)
            safe_url, redirect_count = resolve_public_url(
                requested_url,
                timeout_seconds=self.cfg.web_fetch.timeout_seconds,
                max_redirects=self.cfg.web_fetch.max_redirects,
            )
            content = exa_fetch(
                self.cfg.exa_base_url,
                self.cfg.exa_api_key,
                safe_url,
                max_characters=self.cfg.web_fetch.max_content_characters,
            )
            return {
                "requested_url": requested_url,
                "final_url": safe_url,
                "title": "",
                "domain": urlparse(safe_url).hostname or "",
                "fetched_at": datetime.now(UTC).isoformat(),
                "published_at": None,
                "author": None,
                "content": content,
                "fetch_status": "succeeded",
                "extraction_status": "main_content",
                "provider": "exa",
                "provider_label": "exa",
                "attempted_providers": ["exa"],
                "successful_providers": ["exa"],
                "redirect_count": redirect_count,
                "download_status": "provider_managed",
                "content_length": len(content),
            }
        try:
            limits = FetchLimits(
                timeout_seconds=self.cfg.web_fetch.timeout_seconds,
                max_download_bytes=self.cfg.web_fetch.max_download_bytes,
                max_content_characters=self.cfg.web_fetch.max_content_characters,
                max_redirects=self.cfg.web_fetch.max_redirects,
            )
            fetched = fetch_page_detailed(
                url,
                self.cfg.crawl4ai_url,
                self.cfg.crawl4ai_api_key,
                limits=limits,
            )
            return {
                "requested_url": fetched.requested_url,
                "final_url": fetched.final_url,
                "title": fetched.title,
                "domain": urlparse(fetched.final_url).hostname or "",
                "fetched_at": fetched.fetched_at,
                "published_at": fetched.published_at,
                "author": fetched.author,
                "content": fetched.content,
                "fetch_status": fetched.download_status,
                "extraction_status": fetched.extraction_status,
                "provider": fetched.provider,
                "provider_label": fetched.provider,
                "attempted_providers": list(fetched.attempted_providers),
                "successful_providers": (
                    [fetched.successful_provider] if fetched.successful_provider else []
                ),
                "redirect_count": fetched.redirect_count,
                "download_status": fetched.download_status,
                "downloaded_bytes": fetched.downloaded_bytes,
                "download_truncated": fetched.download_truncated,
                "content_truncated": fetched.content_truncated,
                "content_length": len(fetched.content),
            }
        except UnsafeURL:
            raise
        except FetchPageError as exc:
            if (
                self.cfg.web_provider == "auto"
                and self.cfg.exa_api_key
                and exc.failure_class
                in {"empty_extraction", "unsupported_content_type"}
                and exc.final_url
            ):
                safe_url = validate_public_url(exc.final_url)
                attempted = ["direct"]
                if self.cfg.crawl4ai_url:
                    attempted.append("crawl4ai")
                attempted.extend(["trafilatura", "exa"])
                content = exa_fetch(
                    self.cfg.exa_base_url,
                    self.cfg.exa_api_key,
                    safe_url,
                    max_characters=self.cfg.web_fetch.max_content_characters,
                )
                return {
                    "requested_url": canonicalize_public_url(url),
                    "final_url": safe_url,
                    "title": "",
                    "domain": urlparse(safe_url).hostname or "",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "published_at": None,
                    "author": None,
                    "content": content,
                    "fetch_status": "succeeded",
                    "extraction_status": "main_content",
                    "provider": "exa",
                    "provider_label": "exa",
                    "attempted_providers": attempted,
                    "successful_providers": ["exa"],
                    "fallback_used": True,
                    "redirect_count": exc.redirect_count,
                    "download_status": "provider_managed",
                    "content_length": len(content),
                }
            raise
