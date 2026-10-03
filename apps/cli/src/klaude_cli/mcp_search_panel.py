"""Typed, read-only presentation for official MCP Registry discovery."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from klaude_core.mcp_catalog import MCPCatalogServer, github_repository_identity

from .mcp_suggestions import SUGGESTED_SEARCHES
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

SORTS = ("Registry order", "Name A–Z", "Name Z–A")


def _safe_text(value: str, maximum: int = 500) -> str:
    """Registry prose is remote data, including when a client reports an error."""
    return " ".join("".join(character for character in value
                            if character.isprintable()).split())[:maximum]


@dataclass(frozen=True)
class InstallOption:
    id: str
    label: str
    endpoint: str
    enabled: bool = True
    note: str = ""


def sorted_servers(
    servers: Sequence[MCPCatalogServer], sort: str
) -> list[MCPCatalogServer]:
    if sort == "Name A–Z":
        return sorted(servers, key=lambda item: (item.name.casefold(), item.version))
    if sort == "Name Z–A":
        return sorted(servers, key=lambda item: (item.name.casefold(), item.version),
                      reverse=True)
    return list(servers)


def mcp_search_page(
    query: str, servers: Sequence[MCPCatalogServer], *, sort: str = SORTS[0],
    loading: bool = False, cached: bool = False, error: str = "",
    searched: bool = False, repository_stars: dict[str, int] | None = None,
) -> PanelPage:
    """Keep query and source context fixed while result rows scroll and filter."""
    rows = [
        PanelRow("search-heading", RowKind.SECTION, "SEARCH"),
        PanelRow("query", RowKind.ACTION, "Search query", _safe_text(query, 120)
                 or "Enter keywords",
                 action=PanelAction("mcp-search-query"), section_id="search-heading"),
        PanelRow("source", RowKind.INFO, "Source", "Official MCP Registry",
                 section_id="search-heading"),
        PanelRow("sort", RowKind.CHOICE, "Sort", sort,
                 description="Sorts loaded results",
                 action=PanelAction("mcp-search-sort"), section_id="search-heading"),
    ]
    if not query and not searched and not servers:
        rows.append(PanelRow("suggestions", RowKind.SECTION, "SUGGESTIONS",
                             description="Local query ideas"))
        rows.extend(PanelRow(
            "suggest:" + term.casefold(), RowKind.ACTION, term,
            action=PanelAction("mcp-search-suggest", term), section_id="suggestions",
        ) for term in SUGGESTED_SEARCHES)
    else:
        rows.append(PanelRow("results", RowKind.SECTION, "RESULTS",
                             description="Official MCP Registry"))
        if loading:
            rows.append(PanelRow("loading", RowKind.STATUS, "Searching…",
                                 section_id="results"))
        if cached:
            rows.append(PanelRow("cached", RowKind.STATUS, "Cached registry results",
                                 section_id="results"))
        if error:
            rows.append(PanelRow("error", RowKind.STATUS, "Search unavailable",
                                 description=_safe_text(error, 200), status_tone="warning",
                                 section_id="results"))
        for server in sorted_servers(servers, sort):
            stars = (repository_stars or {}).get(server.repository_url)
            description = _safe_text(server.description)
            if stars is not None:
                description += f" · Repository stars: {stars:,}"
            elif github_repository_identity(server.repository_url):
                description += " · Repository stars: open detail"
            rows.append(PanelRow(
                "registry:" + server.name, RowKind.NAVIGATION, _safe_text(server.name),
                _safe_text(server.version), description,
                action=PanelAction("mcp-search-detail", server.name),
                section_id="results", search_terms=_safe_text(server.title),
            ))
        if searched and not servers and not loading and not error:
            rows.append(PanelRow("empty", RowKind.INFO,
                                 "No supported active servers matched",
                                 section_id="results"))
        if query:
            rows.append(PanelRow("retry", RowKind.ACTION, "Search again",
                                 enabled=not loading,
                                 action=PanelAction("mcp-search-retry")))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK, action=PanelAction("mcp-search-back")))
    return PanelPage("mcp-registry-search", ("Settings", "MCPs", "Search"), tuple(rows),
                     column_headers=("MCP NAME", "VERSION", "DESCRIPTION")
                     if servers else None, scroll_wrapped_rows=True)


def mcp_detail_page(
    server: MCPCatalogServer, options: Sequence[InstallOption], *,
    inventory_loading: bool = False, inventory_error: str = "",
    inventory_age: int | None = None, inventory_truncated: bool = False,
    repository_stars: int | None = None, stars_loading: bool = False,
    stars_error: str = "",
) -> PanelPage:
    rows = [
        PanelRow("server", RowKind.SECTION, "MCP SERVER"),
        PanelRow("name", RowKind.INFO, "Registry name", description=_safe_text(server.name),
                 section_id="server"),
        PanelRow("version", RowKind.INFO, "Version", description=_safe_text(server.version),
                 section_id="server"),
        PanelRow("description", RowKind.INFO, "Description",
                 description=_safe_text(server.description) or "Not supplied",
                 section_id="server"),
    ]
    if server.repository_url:
        rows.append(PanelRow("repository", RowKind.INFO, "Source",
                             description=_safe_text(server.repository_url), section_id="server"))
    if github_repository_identity(server.repository_url):
        rows.append(PanelRow("repository-stars", RowKind.INFO, "Repository stars",
                             description=(f"{repository_stars:,}" if repository_stars is not None
                                          else "Loading…" if stars_loading else
                                          "Unavailable" if stars_error else "Not loaded"),
                             section_id="server"))
        if stars_error:
            rows.append(PanelRow("retry-stars", RowKind.ACTION, "Retry repository stars",
                                 action=PanelAction("mcp-stars-retry"), section_id="server"))
    rows.extend((
        PanelRow("install", RowKind.SECTION, "INSTALL OPTIONS"),
        PanelRow("trust", RowKind.INFO, "Review",
                 description="Installed servers stay disabled until you enable them.",
                 section_id="install"),
    ))
    if inventory_loading:
        rows.append(PanelRow("loading", RowKind.STATUS, "Checking configured servers…",
                             section_id="install"))
    if inventory_error:
        rows.append(PanelRow("error", RowKind.STATUS,
                             "Configuration inventory unavailable; reopen to retry",
                             status_tone="warning", section_id="install"))
    if inventory_age is not None:
        rows.append(PanelRow("age", RowKind.STATUS,
                             f"Configuration snapshot {inventory_age}s old",
                             section_id="install"))
    if inventory_truncated:
        rows.append(PanelRow("truncated", RowKind.STATUS,
                             "Configuration exceeds the 1,000-server preview; use CLI",
                             status_tone="warning", section_id="install"))
    for option in options:
        rows.append(PanelRow(
            option.id, RowKind.ACTION, _safe_text(option.label),
            description=" · ".join(filter(None, (_safe_text(option.endpoint),
                                                   _safe_text(option.note)))),
            enabled=option.enabled,
            action=PanelAction("mcp-search-install", option.id), section_id="install",
        ))
    if not options:
        rows.append(PanelRow("unsupported", RowKind.INFO,
                             "No supported Streamable HTTP, npm, or PyPI plan",
                             section_id="install"))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK, action=PanelAction("mcp-search-results")))
    return PanelPage("mcp-registry-detail:" + server.name,
                     ("Settings", "MCPs", "Search",
                      _safe_text(server.title or server.name)),
                     tuple(rows), scroll_wrapped_rows=True)
