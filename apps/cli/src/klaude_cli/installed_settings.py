"""Shared installed-item filtering for MCP and Skills settings."""

from enum import StrEnum

from prompt_toolkit.utils import get_cwidth

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


def list_preview(value: object, *, width: int = 76) -> str:
    """Keep a list summary within a few terminal lines; details retain full text."""
    text = " ".join(str(value or "Description unavailable").split())
    if get_cwidth(text) <= width:
        return text
    while text and get_cwidth(text + "…") > width:
        text = text[:-1]
    if " " in text:
        whole_words = text.rsplit(" ", 1)[0]
        if get_cwidth(whole_words) >= width // 2:
            text = whole_words
    return text.rstrip(" ,;:.") + "…"


def inventory_summary(description: object, source_label: object) -> str:
    """Show the source type without repeating a long repository path in every row."""
    source = " ".join(str(source_label or "Source unknown").split())
    if source.startswith("MCP Registry · "):
        if not description:
            return "Official MCP Registry"
        source = "Registry · " + source.removeprefix("MCP Registry · ")
    if not description:
        return list_preview(source)
    origin = source.partition(" · ")[0]
    return list_preview(f"{origin} · {description}")


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
