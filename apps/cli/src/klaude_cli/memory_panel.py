"""Typed memory-management pages over the bounded inventory snapshot."""

from .settings_panel import PanelAction, PanelPage, PanelRow, RowKind


def memory_list_page(entries: list[dict[str, str]], count: int, hidden: int) -> PanelPage:
    rows = [PanelRow("heading", RowKind.SECTION, "SAVED MEMORIES")]
    rows.extend(
        PanelRow(
            f"fact:{entry['id']}",
            RowKind.NAVIGATION,
            entry["fact"],
            action=PanelAction("memory-open", entry["id"]),
            section_id="heading",
        )
        for entry in entries
    )
    if not entries:
        rows.append(PanelRow("empty", RowKind.INFO, "No memories available to edit"))
    if count - hidden > len(entries):
        rows.append(
            PanelRow(
                "bounded",
                RowKind.INFO,
                "Showing the first 200 memories · klaude memory list shows the rest",
            )
        )
    if hidden:
        rows.append(PanelRow("hidden", RowKind.INFO, f"Sensitive memories hidden: {hidden}"))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("memory-back")))
    return PanelPage("memory-facts", ("Settings", "Memory", "Manage memories"), tuple(rows))


def memory_detail_page(memory_id: str, fact: str, *, confirm: bool = False) -> PanelPage:
    rows = [PanelRow("fact", RowKind.INFO, fact)]
    if confirm:
        rows.append(
            PanelRow(
                "delete",
                RowKind.ACTION,
                "Delete this memory",
                description="Permanently remove this memory",
                action=PanelAction("memory-delete", memory_id),
            )
        )
    else:
        rows.extend(
            [
                PanelRow(
                    "edit",
                    RowKind.ACTION,
                    "Edit memory",
                    action=PanelAction("memory-edit", memory_id),
                ),
                PanelRow(
                    "delete",
                    RowKind.ACTION,
                    "Delete memory",
                    action=PanelAction("memory-confirm", memory_id),
                ),
            ]
        )
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("memory-list")))
    return PanelPage(
        f"memory-fact:{memory_id}:{confirm}",
        (
            "Settings",
            "Memory",
            "Manage memories",
            "Confirm deletion" if confirm else "Memory detail",
        ),
        tuple(rows),
    )
