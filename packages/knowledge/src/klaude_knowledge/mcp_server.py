"""MCP server exposing the knowledge layer to any MCP client.

Register in e.g. Claude Code / OpenCode / Cline as:
  command: uv, args: [run, klaude-knowledge-mcp]
"""

from klaude_core import load_config

from klaude_knowledge import (
    IndexDocument,
    Knowledge,
    finalize_docs_source,
    finalize_skill_package,
    install_crawl_source,
    install_docs_source,
    install_skill_package,
    list_docs_sources,
    list_installed_skills,
    update_docs_source,
)


def main() -> None:
    from mcp.server.fastmcp import FastMCP

    cfg = load_config()
    kn = Knowledge(cfg)
    mcp = FastMCP("klaude-knowledge")

    def index_docs(installed) -> int:
        documents = []
        for file, source_url in zip(installed.files, installed.source_urls, strict=False):
            rel = file.relative_to(installed.current_dir).as_posix()
            documents.append(
                IndexDocument(
                    source=source_url,
                    text=file.read_text(errors="replace"),
                    title=rel,
                )
            )
        total = kn.replace_owner_snapshot_atomic(
            installed.library,
            f"docs:{installed.name}",
            documents,
        )
        finalize_docs_source(installed)
        return total

    @mcp.tool()
    def learn_url(url: str, collection: str = "", library: str = "") -> str:
        """Fetch a documentation page and store it in a knowledge library."""
        from klaude_web import Web

        target_library = library or collection
        if not target_library:
            return "error: provide a library name"
        text = Web(cfg).fetch(url)
        n = kn.learn_text(target_library, text, source=url)
        return f"learned {n} chunks from {url} into library '{target_library}'"

    @mcp.tool()
    def learn_file(path: str, collection: str = "", library: str = "") -> str:
        """Index a local text/markdown file into a knowledge library."""
        target_library = library or collection
        if not target_library:
            return "error: provide a library name"
        n = kn.learn_file(target_library, path)
        return f"learned {n} chunks from {path} into library '{target_library}'"

    @mcp.tool()
    def docs_add(
        name: str,
        llms_url: str,
        collection: str = "",
        library: str = "",
        max_pages: int = 200,
    ) -> str:
        """Install refreshable llms.txt documentation and index it."""
        from klaude_web import Web

        installed = install_docs_source(
            cfg,
            llms_url,
            Web(cfg).fetch,
            name=name,
            library=library or collection,
            max_pages=max_pages,
        )
        total = index_docs(installed)
        snapshot = f"; snapshot {installed.snapshot}" if installed.snapshot else ""
        return (
            f"installed docs '{installed.name}' into library '{installed.library}'; "
            f"learned {total} chunks from {len(installed.files)} files{snapshot}"
        )

    @mcp.tool()
    def docs_update(name: str, max_pages: int = -1) -> str:
        """Refresh an installed documentation source and snapshot the old current tree."""
        from klaude_web import Web

        web = Web(cfg)
        installed = update_docs_source(
            cfg,
            name,
            web.fetch,
            max_pages=None if max_pages < 0 else max_pages,
            crawler=web.crawl_site,
        )
        total = index_docs(installed)
        snapshot = f"; snapshot {installed.snapshot}" if installed.snapshot else ""
        return (
            f"updated docs '{installed.name}' in library '{installed.library}'; "
            f"learned {total} chunks from {len(installed.files)} files{snapshot}"
        )

    @mcp.tool()
    def crawl_site(
        url: str,
        collection: str = "",
        library: str = "",
        name: str = "",
        max_depth: int = 2,
        max_pages: int = 50,
        pattern: str = "*",
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
        use_sitemap: bool = False,
        respect_robots: bool = True,
    ) -> str:
        """Politely crawl same-domain pages and index them into a knowledge library."""
        from klaude_web import Web

        target_library = library or collection
        if not target_library:
            return "error: provide a library name"
        web = Web(cfg)
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
        if not crawled["pages"]:
            return (
                f"crawl found no indexable pages from {url}; "
                f"errors={len(crawled['errors'])}, skipped={len(crawled['skipped'])}"
            )
        installed = install_crawl_source(
            cfg,
            name or target_library,
            target_library,
            url,
            crawled["pages"],
            errors=crawled["errors"],
            skipped=crawled["skipped"],
            seeded=crawled["seeded"],
            options={
                "max_depth": max_depth,
                "max_pages": max_pages,
                "pattern": pattern,
                "include_patterns": include_patterns or [],
                "exclude_patterns": exclude_patterns or [],
                "use_sitemap": use_sitemap,
                "respect_robots": respect_robots,
                "delay_min": cfg.crawl_delay_min,
                "delay_max": cfg.crawl_delay_max,
            },
        )
        total = index_docs(installed)
        snapshot = f"; snapshot {installed.snapshot}" if installed.snapshot else ""
        return (
            f"crawled docs '{installed.name}' into library '{installed.library}'; "
            f"learned {total} chunks from {len(installed.files)} files; "
            f"errors={len(crawled['errors'])}, skipped={len(crawled['skipped'])}{snapshot}"
        )

    @mcp.tool()
    def import_skill(
        path: str,
        collection: str = "",
        library: str = "",
        name: str = "",
    ) -> str:
        """Install a skill ZIP/folder and index it into a knowledge library."""
        installed = install_skill_package(cfg, path, name=name, library=library or collection)
        documents = []
        for file, source_uri in zip(
            installed.text_files,
            installed.source_uris,
            strict=False,
        ):
            rel = file.relative_to(installed.current_dir).as_posix()
            documents.append(
                IndexDocument(
                    source=source_uri,
                    text=file.read_text(errors="replace"),
                    title=rel,
                )
            )
        total = kn.replace_owner_snapshot_atomic(
            installed.library,
            f"skill:{installed.name}",
            documents,
        )
        finalize_skill_package(installed)
        return (
            f"installed skill '{installed.name}' into library '{installed.library}'; "
            f"learned {total} chunks from {len(installed.text_files)} text files"
        )

    @mcp.tool()
    def query_knowledge(
        question: str = "",
        query: str = "",
        collection: str = "",
        library: str = "",
    ) -> str:
        """Hybrid-search the local docs knowledge base. Empty collection = all."""
        if not question and not query:
            return "error: provide a question or query"
        return kn.query_as_context(question or query, library or collection)

    @mcp.tool()
    def list_collections() -> str:
        """List knowledge libraries. Kept for collection-compatible clients."""
        return "\n".join(kn.store.collections()) or "(none yet)"

    @mcp.tool()
    def list_libraries() -> str:
        """List knowledge libraries."""
        return "\n".join(kn.store.collections()) or "(none yet)"

    @mcp.tool()
    def list_skills() -> str:
        """List installed assistant skills."""
        skills = list_installed_skills(cfg)
        if not skills:
            return "(none yet)"
        return "\n".join(
            f"{s.get('name', '?')} -> {s.get('library', '?')} "
            f"({len(s.get('indexed_files', []))} files)"
            for s in skills
        )

    @mcp.tool()
    def docs_list() -> str:
        """List installed refreshable documentation sources."""
        sources = list_docs_sources(cfg)
        if not sources:
            return "(none yet)"
        return "\n".join(
            f"{s.get('name', '?')} -> {s.get('library', '?')} "
            f"({len(s.get('files', []))} files, {s.get('kind', 'llms')}) "
            f"{s.get('llms_url') or s.get('start_url', '')}"
            for s in sources
        )

    mcp.run()


if __name__ == "__main__":
    main()
