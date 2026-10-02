"""Typed removal navigation over the existing sanitized MCP inventory."""

from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind


def removal_page(servers: list[dict], *, truncated: bool = False) -> PanelPage:
    rows = [PanelRow("servers", RowKind.SECTION, "MCP SERVERS")]
    rows.extend(PanelRow(
        f"server:{server['name']}", RowKind.NAVIGATION, server["name"],
        description="Enabled" if server["enabled"] else "Disabled",
        action=PanelAction("mcp-remove-review", server["name"]), section_id="servers",
    ) for server in servers)
    if not servers:
        rows.append(PanelRow("empty", RowKind.INFO, "No MCP servers configured"))
    if truncated:
        rows.append(PanelRow("limited", RowKind.INFO,
                             "Showing first 1,000 servers · klaude mcp remove NAME for others"))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back",
                         action=PanelAction("mcp-remove-back"), control=RowControl.BACK))
    return PanelPage("mcp-removal", ("Settings", "MCPs", "Delete MCP"), tuple(rows))


def removal_confirmation(name: str) -> PanelPage:
    return PanelPage("mcp-removal-confirm", ("Settings", "MCPs", "Delete MCP", name), (
        PanelRow("scope", RowKind.INFO, "Remove this server and its local OAuth credentials?",
                 description="Shared API keys remain · This does not uninstall server packages"),
        PanelRow("remove", RowKind.ACTION, "Delete MCP",
                 action=PanelAction("mcp-remove-confirm", name)),
        PanelRow("cancel", RowKind.NAVIGATION, "Cancel",
                 action=PanelAction("mcp-remove-list"), control=RowControl.CANCEL),
    ))
