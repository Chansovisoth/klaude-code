"""Shared installed-item filtering for MCP and Skills settings."""

from enum import StrEnum

from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind


class InstalledFilter(StrEnum):
    ALL = "all"
    ENABLED = "enabled"
    DISABLED = "disabled"

    @property
    def label(self) -> str:
        return self.value.capitalize()

    def includes(self, enabled: bool) -> bool:
        return self == self.ALL or enabled == (self == self.ENABLED)


def filter_page(category: str, current: InstalledFilter) -> PanelPage:
    rows = [PanelRow("filter-heading", RowKind.SECTION, "SHOW INSTALLED")]
    rows.extend(PanelRow(
        item.value, RowKind.CHOICE, item.label,
        "Current" if item == current else "",
        action=PanelAction("installed-filter-apply", f"{category}:{item.value}"),
        section_id="filter-heading",
    ) for item in InstalledFilter)
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK,
                         action=PanelAction("installed-filter-back", category)))
    return PanelPage(f"installed-filter:{category}",
                     ("Settings", category, "Manage", "Filter"), tuple(rows))
