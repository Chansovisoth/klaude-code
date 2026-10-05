"""Typed removal navigation over the existing sanitized MCP inventory."""

import shlex

from klaude_core.mcp_catalog import MCPInstallPlan

from .installed_settings import InstalledFilter, inventory_summary
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind


def setup_review_page(setup: dict[str, object]) -> PanelPage:
    """Show exact nonsecret setup choices before a server is saved disabled."""
    kind = str(setup.get("kind") or "")
    name = str(setup.get("name") or "")
    candidate = setup.get("plan")
    plan = candidate if kind == "registry" and isinstance(candidate, MCPInstallPlan) else None
    registry = plan is not None
    transport = plan.transport if plan is not None else str(setup.get("transport") or "")
    endpoint = str(setup.get("endpoint") or "")
    if plan is not None:
        endpoint = plan.url if transport == "http" else shlex.join(
            [plan.command, *plan.args]
        )
    elif transport == "stdio":
        arguments = setup.get("args")
        if not isinstance(arguments, (list, tuple)):
            arguments = []
        endpoint = shlex.join([str(setup.get("command") or ""),
                               *[str(arg) for arg in arguments]])
    rows = [
        PanelRow("heading", RowKind.SECTION,
                 "INSTALL SERVER" if registry else "ADD SERVER"),
        PanelRow("name", RowKind.INFO, "Local name", description=name,
                 section_id="heading"),
        PanelRow("transport", RowKind.INFO, "Transport",
                 description="Streamable HTTP" if transport == "http" else "Local stdio",
                 section_id="heading"),
        PanelRow("endpoint", RowKind.INFO,
                 "Endpoint" if transport == "http" else "Command",
                 description=endpoint, section_id="heading"),
    ]
    if plan is not None:
        rows.append(PanelRow("source", RowKind.INFO, "Registry source",
                             description=f"{plan.source_name} · {plan.source_version}",
                             section_id="heading"))
        answers = setup.get("answers")
        supplied = answers if isinstance(answers, dict) else {}
        for item in plan.inputs:
            state = ("Provided (masked)" if item.secret else "Provided") \
                if supplied.get(item.key) else "Default" if item.default else "Not supplied"
            rows.append(PanelRow("input:" + item.key, RowKind.INFO, item.label,
                                 description=state, section_id="heading"))
    elif transport == "http":
        auth = str(setup.get("authentication") or "No authentication")
        rows.append(PanelRow("authentication", RowKind.INFO, "Authentication",
                             description=auth, section_id="heading"))
    rows.extend((
        PanelRow("state", RowKind.INFO, "Initial state",
                 description="Disabled · review before enabling"),
        PanelRow("confirm", RowKind.ACTION,
                 "Install disabled server" if registry else "Add disabled server",
                 action=PanelAction("mcp-setup-confirm")),
        PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                 control=RowControl.BACK, action=PanelAction("mcp-setup-back")),
    ))
    breadcrumb = ("Settings", "MCPs", "Search", "Review install") if registry else \
        ("Settings", "MCPs", "Add server", "Review")
    return PanelPage("mcp-setup-review", breadcrumb, tuple(rows),
                     scroll_wrapped_rows=True)


def install_result_page(name: str) -> PanelPage:
    return PanelPage("mcp-install-result", ("Settings", "MCPs", "Server added"), (
        PanelRow("heading", RowKind.SECTION, "SERVER ADDED"),
        PanelRow("name", RowKind.INFO, "Local name", description=name,
                 section_id="heading"),
        PanelRow("state", RowKind.INFO, "Status", description="Installed as disabled",
                 section_id="heading"),
        PanelRow("open", RowKind.NAVIGATION, "Open installed server",
                 description="Review it before enabling",
                 action=PanelAction("mcp-install-open", name), section_id="heading"),
        PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                 control=RowControl.BACK, action=PanelAction("mcp-install-back")),
    ))


def settings_page(servers: list[dict] | None, *, age: int = 0,
                  loading: bool = False, truncated: bool = False,
                  feedback: tuple[str, ...] = ()) -> PanelPage:
    summary = ""
    if servers is not None:
        prefix = "At least " if truncated else ""
        summary = (f"{prefix}{len(servers)} installed, "
                   f"{sum(bool(server.get('enabled')) for server in servers)} enabled"
                   f" · Configuration snapshot {age}s old")
    if loading:
        summary = " · ".join(filter(None, (summary, "Loading configured MCP servers…")))
    rows = [
        PanelRow("installed", RowKind.SECTION, "MCP Servers", description=summary),
        PanelRow("manage", RowKind.NAVIGATION, "Manage installed",
                 action=PanelAction("mcp-manage"), section_id="installed",
                 legacy_label="Manage"),
        PanelRow("search", RowKind.NAVIGATION, "Search catalog",
                 description="Official MCP Registry",
                 action=PanelAction("mcp-settings-search"), section_id="installed",
                 legacy_label="Search official MCP Registry"),
        PanelRow("custom", RowKind.NAVIGATION, "Add custom server",
                 action=PanelAction("mcp-settings-custom"), section_id="installed",
                 legacy_label="Add custom MCP server"),
        PanelRow("import", RowKind.ACTION, "Import configuration",
                 action=PanelAction("mcp-settings-import"), section_id="installed",
                 legacy_label="Import MCP configuration"),
        PanelRow("permissions", RowKind.NAVIGATION, "Permissions",
                 action=PanelAction("mcp-settings-permissions"), section_id="installed"),
    ]
    rows.extend(PanelRow(f"feedback:{index}", RowKind.STATUS, message)
                for index, message in enumerate(feedback))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK, legacy_label="back",
                         action=PanelAction("mcp-settings-back")))
    return PanelPage("mcp-settings", ("Settings", "MCPs"), tuple(rows))


def manage_page(servers: list[dict] | None, *, pending: bool = False,
                truncated: bool = False, error: str = "",
                show: InstalledFilter = InstalledFilter.ALL) -> PanelPage:
    visible = [server for server in servers or [] if show.includes(bool(server.get("enabled")))]
    rows = [
        PanelRow("servers", RowKind.SECTION, "MCP SERVERS",
                 description=(("At least " if truncated else "")
                              + f"{len(servers)} installed · "
                              f"{sum(bool(server.get('enabled')) for server in servers)} enabled")
                 if servers is not None else
                 "Loading configured servers…"),
        PanelRow("filter", RowKind.CHOICE, "Filter", show.label,
                 action=PanelAction("installed-filter-open", "MCPs"), section_id="servers"),
        PanelRow("refresh-list", RowKind.ACTION, "Refresh list",
                 description="Re-read configured servers",
                 action=PanelAction("mcp-manage-refresh-list"), section_id="servers"),
        PanelRow("reload", RowKind.ACTION, "Refresh tools", legacy_label="Reload",
                 description="Reload tool cache",
                 enabled=not pending, action=PanelAction("mcp-manage-reload"),
                 section_id="servers"),
        PanelRow("update-all", RowKind.ACTION, "Check for updates",
                 description="Review package updates"
                 if any(server.get("update_kind") == "registry-package"
                        for server in servers or []) else
                 "No verified package update sources",
                 enabled=not pending and any(
                     server.get("update_kind") == "registry-package"
                     for server in servers or []
                 ),
                 action=PanelAction("mcp-manage-update-all"), section_id="servers"),
        PanelRow("spacer", RowKind.SEPARATOR, ""),
    ]
    if servers is not None:
        if visible:
            rows.append(PanelRow("installed-items", RowKind.TABLE_HEADER, "INSTALLED SERVERS"))
        rows.extend(PanelRow(
            f"server:{server['name']}", RowKind.NAVIGATION, server["name"],
            "Enabled" if server.get("enabled") else "Disabled",
            inventory_summary(server.get("description"),
                              server.get("source_label") or "Local configuration"),
            action=PanelAction("mcp-manage-detail", server["name"]),
            section_id="installed-items",
            search_terms=" ".join((str(server.get("description") or ""),
                                   str(server.get("source_label") or ""))),
        ) for server in visible)
        if not servers:
            rows.append(PanelRow("empty", RowKind.INFO, "No MCP servers configured"))
            rows.append(PanelRow("search", RowKind.NAVIGATION, "Search catalog",
                                 action=PanelAction("mcp-manage-search"), section_id="servers"))
        elif not visible:
            rows.append(PanelRow("empty", RowKind.INFO, f"No {show.value} servers"))
    if truncated:
        rows.append(PanelRow("limited", RowKind.STATUS,
                             "Showing first 1,000 servers; inventory incomplete",
                             status_tone="warning"))
    if error:
        rows.append(PanelRow("feedback", RowKind.STATUS, error, status_tone="warning"))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK, action=PanelAction("mcp-manage-back")))
    return PanelPage("mcp-manage", ("Settings", "MCPs", "Manage"), tuple(rows),
                     column_headers=("MCP", "STATUS", "SUMMARY")
                     if visible else None, table_section_id="installed-items",
                     scroll_wrapped_rows=True)


def manage_detail_page(server: dict, *, pending: bool = False,
                       permissions_available: bool = False,
                       feedback: str = "") -> PanelPage:
    name = server["name"]
    rows = [
        PanelRow("server", RowKind.SECTION, name,
                 description="Installed MCP server"),
        PanelRow("description", RowKind.INFO, "Description",
                 description=server.get("description") or "Description unavailable",
                 section_id="server"),
        PanelRow("enabled", RowKind.TOGGLE, "Enabled", enabled=not pending,
                 checked=bool(server["enabled"]),
                 action=PanelAction("mcp-manage-toggle", name), section_id="server"),
        PanelRow("permissions", RowKind.NAVIGATION, "Tools & permissions",
                 description="Choose access for this server's tools" if permissions_available
                 else "Available after tools are loaded",
                 enabled=permissions_available,
                 action=PanelAction("mcp-manage-permissions", name), section_id="server"),
        PanelRow("update", RowKind.ACTION, "Check for update",
                 description="Check the official Registry for a newer package version"
                 if server.get("update_kind") == "registry-package" else
                 "No verified package update source",
                 enabled=server.get("update_kind") == "registry-package" and not pending,
                 action=PanelAction("mcp-manage-update", name), section_id="server"),
        PanelRow("source-heading", RowKind.SECTION, "SOURCE & CONNECTION"),
        PanelRow("source", RowKind.INFO, "Source",
                 description=server.get("source_label") or "Local configuration",
                 section_id="source-heading"),
        PanelRow("transport", RowKind.INFO, "Transport", server["transport"],
                 section_id="source-heading"),
        PanelRow("tools", RowKind.INFO, "Cached tools", str(server["tool_count"]),
                 section_id="source-heading"),
        PanelRow("delete", RowKind.ACTION, "Remove server", enabled=not pending,
                 action=PanelAction("mcp-manage-delete", name)),
    ]
    if feedback:
        rows.append(PanelRow("feedback", RowKind.STATUS, feedback))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK, action=PanelAction("mcp-manage-list")))
    return PanelPage(f"mcp-manage:{name}", ("Settings", "MCPs", "Manage", name),
                     tuple(rows), scroll_wrapped_rows=True)


def manage_update_review(name: str, candidate: dict[str, str]) -> PanelPage:
    return PanelPage(f"mcp-manage-update:{name}",
                     ("Settings", "MCPs", "Manage", name, "Review update"), (
        PanelRow("update", RowKind.SECTION, "UPDATE MCP"),
        PanelRow("package", RowKind.INFO, "Package", candidate["old_arg"],
                 section_id="update"),
        PanelRow("version", RowKind.INFO, "New package", candidate["new_arg"],
                 section_id="update"),
        PanelRow("warning", RowKind.INFO,
                 "Updating disables this server and clears cached tools; enable it after review"),
        PanelRow("confirm", RowKind.ACTION, "Update MCP",
                 action=PanelAction("mcp-manage-update-confirm", name)),
        PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                 control=RowControl.BACK,
                 action=PanelAction("mcp-manage-update-back", name)),
    ), scroll_wrapped_rows=True)


def manage_update_all_review(updates: list[tuple[str, dict[str, str]]]) -> PanelPage:
    rows = [PanelRow("updates", RowKind.SECTION, "MCP UPDATES",
                     description=f"{len(updates)} available")]
    rows.extend(PanelRow(
        f"server:{name}", RowKind.INFO, name,
        description=(f"{candidate['old_version']} → {candidate['new_version']} · "
                     f"{candidate['new_arg']}"),
        section_id="updates",
    ) for name, candidate in updates)
    rows.extend((
        PanelRow("warning", RowKind.INFO,
                 "Updated servers are disabled and their cached tools cleared until reviewed"),
        PanelRow("confirm", RowKind.ACTION, "Update all",
                 action=PanelAction("mcp-manage-update-all-confirm")),
        PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                 control=RowControl.BACK,
                 action=PanelAction("mcp-manage-update-all-back")),
    ))
    return PanelPage("mcp-manage-update-all-review",
                     ("Settings", "MCPs", "Manage", "Review updates"),
                     tuple(rows), scroll_wrapped_rows=True)


def manage_removal_confirmation(name: str) -> PanelPage:
    return PanelPage("mcp-manage-delete:" + name,
                     ("Settings", "MCPs", "Manage", name, "Confirm deletion"), (
        PanelRow("scope", RowKind.INFO, "Remove this server and its local OAuth credentials?",
                 description="Shared API keys remain · This does not uninstall server packages"),
        PanelRow("remove", RowKind.ACTION, "Remove server",
                 action=PanelAction("mcp-manage-delete-confirm", name)),
        PanelRow("cancel", RowKind.NAVIGATION, "Cancel", footer=True,
                 action=PanelAction("mcp-manage-delete-back", name),
                 control=RowControl.CANCEL),
    ))


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
