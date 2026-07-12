"""MCP server exposing local web search + fetch to any MCP client."""

import json

from klaude_core import load_config
from klaude_web import Web


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    web = Web(load_config())
    mcp = FastMCP("klaude-web")

    @mcp.tool()
    def web_search(query: str, max_results: int = 8) -> str:
        """Search the web via local SearXNG. Returns title/url/snippet JSON."""
        return json.dumps(web.search(query, max_results), ensure_ascii=False, indent=1)

    @mcp.tool()
    def fetch_url(url: str) -> str:
        """Fetch a web page as clean markdown (Crawl4AI -> trafilatura cascade)."""
        return web.fetch(url)[:20_000]

    mcp.run()


if __name__ == "__main__":
    main()
