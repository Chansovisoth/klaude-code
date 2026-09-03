"""Runtime source IDs and provenance for web discovery and page reading."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from .fetch import canonical_url_key, canonicalize_public_url


@dataclass
class SearchLead:
    result_id: str
    url_key: str
    title: str = ""
    queries: list[str] = field(default_factory=list)
    providers: list[str] = field(default_factory=list)


@dataclass
class SourceRecord:
    source_id: str
    requested_url: str
    final_url: str
    title: str
    domain: str
    fetched_at: str
    published_at: str | None
    author: str | None
    content: str
    fetch_status: str
    extraction_status: str
    provenance: list[dict[str, str]] = field(default_factory=list)
    aliases: set[str] = field(default_factory=set)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "title": self.title,
            "domain": self.domain,
            "fetched_at": self.fetched_at,
            "published_at": self.published_at,
            "author": self.author,
            "content": self.content,
            "fetch_status": self.fetch_status,
            "extraction_status": self.extraction_status,
            "provenance": list(self.provenance),
        }


class SourceRegistry:
    """Assign stable runtime IDs to SERP leads and successfully read pages."""

    def __init__(self) -> None:
        self._result_counter = 0
        self._source_counter = 0
        self._leads_by_url: dict[str, SearchLead] = {}
        self._sources_by_url: dict[str, SourceRecord] = {}
        self._sources_by_content: dict[str, SourceRecord] = {}
        self._failures_by_url: dict[str, dict[str, Any]] = {}

    def register_search_results(
        self,
        query: str,
        results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        registered: list[dict[str, Any]] = []
        for result in results:
            item = dict(result)
            try:
                normalized_url = canonicalize_public_url(str(item.get("url") or ""))
                key = canonical_url_key(normalized_url)
            except ValueError:
                registered.append(item)
                continue
            lead = self._leads_by_url.get(key)
            if lead is None:
                self._result_counter += 1
                lead = SearchLead(
                    result_id=f"search_result_{self._result_counter:03d}",
                    url_key=key,
                    title=str(item.get("title") or ""),
                )
                self._leads_by_url[key] = lead
            provider = str(item.get("provider") or "").strip().lower()
            if not lead.title and item.get("title"):
                lead.title = str(item["title"])
            if query and query not in lead.queries:
                lead.queries.append(query)
            if provider and provider not in lead.providers:
                lead.providers.append(provider)
            item["result_id"] = lead.result_id
            item["url"] = normalized_url
            registered.append(item)
        return registered

    def source_for_url(self, url: str) -> SourceRecord | None:
        try:
            return self._sources_by_url.get(canonical_url_key(url))
        except ValueError:
            return None

    def failure_for_url(self, url: str) -> dict[str, Any] | None:
        try:
            failure = self._failures_by_url.get(canonical_url_key(url))
        except ValueError:
            return None
        return dict(failure) if failure else None

    def register_failure(self, url: str, failure: dict[str, Any]) -> None:
        try:
            self._failures_by_url[canonical_url_key(url)] = dict(failure)
        except ValueError:
            return

    def register_source(self, document: dict[str, Any]) -> SourceRecord:
        requested_url = canonicalize_public_url(str(document["requested_url"]))
        final_url = canonicalize_public_url(str(document.get("final_url") or requested_url))
        requested_key = canonical_url_key(requested_url)
        final_key = canonical_url_key(final_url)
        existing = self._sources_by_url.get(requested_key) or self._sources_by_url.get(final_key)
        content = str(document.get("content") or "")
        content_key = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = existing or self._sources_by_content.get(content_key)
        provenance = self.provenance_for_url(requested_url)
        if final_key != requested_key:
            provenance.extend(self.provenance_for_url(final_url))

        if existing is None:
            lead = self._leads_by_url.get(requested_key) or self._leads_by_url.get(
                final_key
            )
            self._source_counter += 1
            existing = SourceRecord(
                source_id=f"src_{self._source_counter:03d}",
                requested_url=requested_url,
                final_url=final_url,
                title=str(document.get("title") or (lead.title if lead else "")),
                domain=str(document.get("domain") or ""),
                fetched_at=str(document.get("fetched_at") or ""),
                published_at=(
                    str(document["published_at"])
                    if document.get("published_at") is not None
                    else None
                ),
                author=(str(document["author"]) if document.get("author") is not None else None),
                content=content,
                fetch_status=str(document.get("fetch_status") or "succeeded"),
                extraction_status=str(document.get("extraction_status") or "succeeded"),
                provenance=provenance,
            )
            self._sources_by_content[content_key] = existing
        else:
            for item in provenance:
                if item not in existing.provenance:
                    existing.provenance.append(item)

        existing.aliases.update({requested_key, final_key})
        self._sources_by_url[requested_key] = existing
        self._sources_by_url[final_key] = existing
        self._failures_by_url.pop(requested_key, None)
        self._failures_by_url.pop(final_key, None)
        return existing

    def provenance_for_url(self, url: str) -> list[dict[str, str]]:
        try:
            lead = self._leads_by_url.get(canonical_url_key(url))
        except ValueError:
            return []
        if lead is None:
            return []
        provenance: list[dict[str, str]] = []
        queries = lead.queries or [""]
        providers = lead.providers or [""]
        for query in queries:
            for provider in providers:
                provenance.append(
                    {
                        "search_result_id": lead.result_id,
                        "query": query,
                        "provider": provider,
                    }
                )
        return provenance
