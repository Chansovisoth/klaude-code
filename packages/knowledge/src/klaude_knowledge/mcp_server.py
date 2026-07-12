"""MCP server exposing the knowledge layer to any MCP client.

Register in e.g. Claude Code / OpenCode / Cline as:
  command: uv, args: [run, klaude-knowledge-mcp]
"""

from klaude_core import load_config
from klaude_knowledge import Knowledge


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    cfg = load_config()
    kn = Knowledge(cfg)
    mcp = FastMCP("klaude-knowledge")

    @mcp.tool()
    def learn_url(url: str, collection: str) -> str:
        """Fetch a documentation page and store it in a knowledge library."""
        from klaude_web import Web

        text = Web(cfg).fetch(url)
        n = kn.learn_text(collection, text, source=url)
        return f"learned {n} chunks from {url} into library '{collection}'"

    @mcp.tool()
    def learn_file(path: str, collection: str) -> str:
        """Index a local text/markdown file into a knowledge library."""
        n = kn.learn_file(collection, path)
        return f"learned {n} chunks from {path} into library '{collection}'"

    @mcp.tool()
    def query_knowledge(question: str, collection: str = "") -> str:
        """Hybrid-search the local docs knowledge base. Empty collection = all."""
        return kn.query_as_context(question, collection)

    @mcp.tool()
    def list_collections() -> str:
        """List knowledge libraries. Kept for collection-compatible clients."""
        return "\n".join(kn.store.collections()) or "(none yet)"

    @mcp.tool()
    def list_libraries() -> str:
        """List knowledge libraries."""
        return "\n".join(kn.store.collections()) or "(none yet)"

    mcp.run()


if __name__ == "__main__":
    main()
