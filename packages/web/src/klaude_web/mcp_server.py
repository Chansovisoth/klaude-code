"""MCP server exposing configured web search + fetch to any MCP client."""

import json

from klaude_core import load_config

from klaude_web import Web


def _search_execution_payload(response) -> dict:
    successful = [name for name in response.providers_succeeded if name]
    if len(successful) > 1:
        provider = "multi"
    elif successful:
        provider = successful[0]
    else:
        provider = "none"
    return {
        "tool": "web_search",
        "provider": provider,
        "attempted_providers": response.providers_attempted,
        "successful_providers": response.providers_succeeded,
        "fallback_used": bool(
            successful
            and response.providers_attempted
            and response.providers_attempted[0] not in successful
        ),
        "results": response.results,
        "warnings": response.warnings,
        "queries_attempted": response.queries_attempted,
        "queries_failed": response.queries_failed,
        "provider_states": response.provider_states,
        "provider_metadata": response.provider_metadata,
    }


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    web = Web(load_config())
    mcp = FastMCP("klaude-web")

    @mcp.tool()
    def web_search(query: str, max_results: int = 8) -> str:
        """Search for source leads; inspect snippets, then fetch only promising pages."""
        return json.dumps(
            _search_execution_payload(web.search_detailed(query, max_results)),
            ensure_ascii=False,
            indent=1,
        )

    @mcp.tool()
    def code_search(query: str, max_results: int = 8) -> str:
        """Search programming docs, code examples, and debugging references."""
        return json.dumps(web.code_search(query, max_results), ensure_ascii=False, indent=1)

    @mcp.tool()
    def huggingface_search(
        repo_type: str = "",
        type: str = "",
        kind: str = "",
        query: str = "",
        max_results: int = 10,
        sort: str = "downloads",
    ) -> str:
        """Search Hugging Face Hub models, datasets, or Spaces."""
        return json.dumps(
            web.huggingface_search(repo_type or type or kind or "model", query, max_results, sort),
            ensure_ascii=False,
            indent=1,
        )

    @mcp.tool()
    def huggingface_details(
        repo_type: str = "",
        repo_id: str = "",
        type: str = "",
        kind: str = "",
        id: str = "",
    ) -> str:
        """Get Hugging Face Hub metadata for a model, dataset, or Space."""
        if not repo_id and not id:
            return "error: provide a Hugging Face repo_id"
        return json.dumps(
            web.huggingface_details(repo_type or type or kind or "model", repo_id or id),
            ensure_ascii=False,
            indent=1,
        )

    @mcp.tool()
    def huggingface_readme(
        repo_type: str = "",
        repo_id: str = "",
        type: str = "",
        kind: str = "",
        id: str = "",
    ) -> str:
        """Fetch a Hugging Face model card, dataset card, or Space README."""
        if not repo_id and not id:
            return "error: provide a Hugging Face repo_id"
        return web.huggingface_readme(repo_type or type or kind or "model", repo_id or id)[:20_000]

    @mcp.tool()
    def fetch_url(url: str) -> str:
        """Read one public page as bounded, untrusted external evidence."""
        return json.dumps(web.fetch_detailed(url), ensure_ascii=False, indent=1)

    @mcp.tool()
    def crawl_site(
        url: str,
        max_depth: int = 2,
        max_pages: int = 25,
        pattern: str = "*",
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        use_sitemap: bool = False,
        respect_robots: bool = True,
    ) -> str:
        """Politely crawl same-domain pages and return markdown previews as JSON."""
        crawled = web.crawl_site(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
            pattern=pattern,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            use_sitemap=use_sitemap,
            respect_robots=respect_robots,
        )
        crawled["pages"] = [
            {**page, "markdown": page["markdown"][:4_000]} for page in crawled["pages"]
        ]
        return json.dumps(crawled, ensure_ascii=False, indent=1)

    mcp.run()


if __name__ == "__main__":
    main()
