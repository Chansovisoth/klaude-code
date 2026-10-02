"""Typed Skills inventory and confirmed deletion pages."""

from __future__ import annotations

from collections.abc import Mapping

from .settings_panel import PanelAction, PanelPage, PanelRow, RowKind


def skills_page(
    installed: list[dict[str, object]] | None,
    inbox: str,
    error: str = "",
    pending: bool = False,
    *, detected: tuple[str, ...] = (),
) -> PanelPage:
    rows = [
        PanelRow("discovery", RowKind.SECTION, "DISCOVERY"),
        PanelRow("search", RowKind.NAVIGATION, "Search", description="Not available yet",
                 enabled=False, section_id="discovery"),
        PanelRow("add", RowKind.SECTION, "ADD SKILLS"),
        PanelRow(
            "import", RowKind.ACTION, "Import skills",
            enabled=not pending, action=PanelAction("skill-import"), section_id="add",
        ),
        PanelRow("inbox", RowKind.INFO, f"Drop ZIPs or skill files here: {inbox}, then import",
                 section_id="add"),
    ]
    if detected:
        detected_count = len(detected)
        rows.append(PanelRow(
            "detected", RowKind.INFO,
            f"Detected {detected_count} new skill {'file' if detected_count == 1 else 'files'}",
            description="Press Import skills to start importing", section_id="add",
        ))
        rows.extend(PanelRow(f"drop:{index}", RowKind.INFO, f"- {name}", section_id="add")
                    for index, name in enumerate(detected))
    rows.append(PanelRow(
        "installed", RowKind.SECTION, "SKILLS",
        description=(
            f"{len(installed)} installed" if installed is not None else "Loading installed skills…"
        ),
    ))
    rows.extend([
        PanelRow("reload", RowKind.ACTION, "Reload", enabled=not pending,
                 action=PanelAction("skill-reload"), section_id="installed"),
        PanelRow("delete-skills", RowKind.NAVIGATION, "Delete skill",
                 enabled=installed is not None and not pending,
                 action=PanelAction("skill-delete-list"), section_id="installed"),
        PanelRow("spacer:skills", RowKind.SEPARATOR, ""),
    ])
    if installed is not None:
        for skill in installed:
            name = str(skill.get("name", "?"))
            files = skill.get("indexed_files", [])
            count = skill.get("indexed_file_count", len(files) if isinstance(files, list) else 0)
            library = str(skill.get("library", ""))
            rows.append(
                PanelRow(
                    f"skill:{name}",
                    RowKind.NAVIGATION,
                    name,
                    f"{count} {'file' if count == 1 else 'files'}",
                    f"Library: {library}" if library and library != name else "",
                    enabled=bool(skill.get("identity")) and not pending,
                    action=PanelAction("skill-open", name), section_id="installed",
                )
            )
        if not installed:
            rows.append(PanelRow(
                "empty", RowKind.INFO, "No skills installed", section_id="installed"
            ))
    if error:
        rows.append(PanelRow("feedback", RowKind.STATUS, error))
    rows.extend(
        [
            PanelRow(
                "back",
                RowKind.NAVIGATION,
                "Back",
                action=PanelAction("skill-back"),
                legacy_label="back",
            ),
        ]
    )
    return PanelPage("skills", ("Settings", "Skills"), tuple(rows))


def skill_delete_page(installed: list[dict[str, object]], *, pending: bool = False) -> PanelPage:
    rows = [PanelRow("installed", RowKind.SECTION, "SKILLS",
                     description=f"{len(installed)} installed")]
    rows.extend(PanelRow(
        f"skill:{skill['name']}", RowKind.NAVIGATION, str(skill["name"]),
        enabled=bool(skill.get("identity")) and not pending,
        action=PanelAction("skill-confirm", str(skill["name"])), section_id="installed",
    ) for skill in installed)
    if not installed:
        rows.append(PanelRow("empty", RowKind.INFO, "No skills installed"))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("skill-list")))
    return PanelPage("skills-delete", ("Settings", "Skills", "Delete skill"), tuple(rows))


def skill_detail_page(skill: Mapping[str, object], *, confirm: bool = False) -> PanelPage:
    name = str(skill["name"])
    rows = [PanelRow("library", RowKind.INFO, "Library", str(skill.get("library", "?")))]
    rows.append(
        PanelRow(
            "delete",
            RowKind.ACTION,
            "Delete this skill" if confirm else "Delete skill",
            description="Remove installed files and this skill's indexed content",
            action=PanelAction("skill-delete" if confirm else "skill-confirm", name),
        )
    )
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("skill-list")))
    return PanelPage(
        f"skill:{name}:{confirm}",
        ("Settings", "Skills", name, "Confirm deletion")
        if confirm
        else ("Settings", "Skills", name),
        tuple(rows),
    )
