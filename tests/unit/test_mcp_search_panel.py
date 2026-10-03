"""The official MCP Registry search uses the same typed panel conventions as Skills."""

from klaude_cli.mcp_search_panel import InstallOption, mcp_detail_page, mcp_search_page
from klaude_cli.settings_panel import PanelState, render_body
from klaude_core.mcp_catalog import MCPCatalogServer


def _server(name: str, description: str = "Documentation examples") -> MCPCatalogServer:
    return MCPCatalogServer(
        name=f"io.github.example/{name}", title=name.title(),
        description=description, version="1.0.0", status="active",
    )


def _text(state: PanelState, width: int) -> str:
    return "\n".join("".join(text for _style, text in line)
                     for line in render_body(state, width).lines)


def test_empty_entry_has_local_suggestions_and_explicit_source():
    page = mcp_search_page("", ())
    assert page.breadcrumb == ("Settings", "MCPs", "Search")
    assert page.column_headers is None
    assert any(row.id.startswith("suggest:") for row in page.rows)
    assert not any(row.id == "results" for row in page.rows)
    assert next(row for row in page.rows if row.id == "source").value == "Official MCP Registry"
    assert next(row for row in page.rows if row.id == "sort").description == (
        "Sorts loaded results"
    )


def test_results_sort_locally_without_changing_server_identity_or_focus():
    servers = (_server("zeta"), _server("alpha"))
    page = mcp_search_page("docs", servers, sort="Name A–Z", searched=True)
    ids = [row.id for row in page.rows if row.id.startswith("registry:")]
    assert ids == ["registry:io.github.example/alpha", "registry:io.github.example/zeta"]
    state = PanelState(page, ids[1])
    state.replace(mcp_search_page("docs", servers, sort="Name Z–A", searched=True,
                                  cached=True))
    assert state.picker.selected_id == ids[1]
    assert [row.id for row in state.page.rows if row.id.startswith("registry:")] == ids[::-1]
    state.filter("documentation zeta")
    assert state.picker.selected_id == ids[1]
    assert next(row for row in state.visible_rows() if row.id == ids[1]).selectable


def test_detail_wraps_long_description_and_disables_unavailable_install():
    server = _server("docs", "Code examples " * 30)
    page = mcp_detail_page(server, (InstallOption(
        "plan:0", "Install disabled · remote", "https://example.com/mcp",
        False, "Configuration inventory not ready",
    ),), inventory_loading=True)
    state = PanelState(page, "plan:0")
    body = render_body(state, 30)
    assert body.row_for_line.count("description") > 1
    assert state.row().enabled is False
    assert "Configuration inventory" in _text(state, 30)
    assert "not ready" in _text(state, 30)


def test_remote_error_and_metadata_cannot_insert_terminal_control_text():
    server = _server("docs", "safe\x1b[2J visible")
    search = mcp_search_page("docs", (server,), error="offline\x1b[2J", searched=True)
    detail = mcp_detail_page(server, ())
    for page in (search, detail):
        assert "\x1b" not in _text(PanelState(page), 50)


def test_github_repository_stars_are_labeled_as_repository_metric():
    from dataclasses import replace

    server = replace(_server("docs"), repository_url="https://github.com/example/docs")
    initial = mcp_search_page("docs", (server,), searched=True)
    assert "Repository stars: open detail" in next(
        row for row in initial.rows if row.id == "registry:" + server.name
    ).description
    search = mcp_search_page("docs", (server,), searched=True,
                             repository_stars={server.repository_url: 1234})
    row = next(row for row in search.rows if row.id == "registry:" + server.name)
    assert "Repository stars: 1,234" in row.description
    detail = mcp_detail_page(server, (), repository_stars=1234)
    assert next(row for row in detail.rows if row.id == "repository-stars").description == "1,234"
    failed = mcp_detail_page(server, (), stars_error="unavailable")
    assert next(row for row in failed.rows if row.id == "retry-stars").action.kind == (
        "mcp-stars-retry"
    )
    assert "repository-stars" not in {row.id for row in mcp_detail_page(_server("x"), ()).rows}
