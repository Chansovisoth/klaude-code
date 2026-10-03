"""Typed Skills inventory and confirmed deletion pages."""

from __future__ import annotations

from collections.abc import Mapping

from klaude_core.skill_catalog import SkillRecord

from .installed_settings import InstalledFilter
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind


def skills_page(
    installed: list[dict[str, object]] | None,
    error: str = "",
    *, detected: tuple[str, ...] = (),
) -> PanelPage:
    rows = [
        PanelRow(
            "installed", RowKind.SECTION, "SKILLS",
            description=(
                f"{len(installed)} installed, "
                f"{sum(skill.get('enabled') is not False for skill in installed)} enabled"
                if installed is not None
                else "Loading installed skills…"
            ),
        ),
        PanelRow("manage", RowKind.NAVIGATION, "Manage installed",
                 action=PanelAction("skill-manage"), section_id="installed"),
        PanelRow("search", RowKind.NAVIGATION, "Search catalog",
                 action=PanelAction("discover-open"), section_id="installed"),
        PanelRow("import", RowKind.NAVIGATION, "Import skills",
                 description=(f"{len(detected)} "
                              + ("file ready to import" if len(detected) == 1
                                 else "files ready to import")) if detected else "",
                 action=PanelAction("skill-import-open"), section_id="installed"),
    ]
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
                footer=True,
                control=RowControl.BACK,
            ),
        ]
    )
    return PanelPage("skills", ("Settings", "Skills"), tuple(rows))


def skills_import_page(inbox: str, *, detected: tuple[str, ...] = (),
                       pending: bool = False, empty_import: bool = False,
                       from_manage: bool = False) -> PanelPage:
    rows = [
        PanelRow("import-heading", RowKind.SECTION, "IMPORT SKILLS"),
        PanelRow("inbox", RowKind.INFO, "Drop folder",
                 description=f"Drop ZIPs or skill files at: {inbox}, then import",
                 section_id="import-heading"),
        PanelRow("import", RowKind.ACTION, "Import skills", enabled=not pending,
                 action=PanelAction("skill-import"), section_id="import-heading"),
    ]
    if detected:
        rows.append(PanelRow("detected", RowKind.INFO,
                             f"Detected {len(detected)} new skill "
                             + ("file" if len(detected) == 1 else "files"),
                             description="Press Import skills to start importing",
                             section_id="import-heading"))
        rows.extend(PanelRow(f"drop:{index}", RowKind.INFO, f"- {name}",
                             section_id="import-heading")
                    for index, name in enumerate(detected))
    elif empty_import:
        rows.append(PanelRow("empty", RowKind.INFO, "No new skill file.",
                             section_id="import-heading"))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK, legacy_label="back",
                         action=PanelAction("skill-import-back")))
    breadcrumb = ("Settings", "Skills", "Manage", "Import") if from_manage \
        else ("Settings", "Skills", "Import")
    return PanelPage("skills-import", breadcrumb, tuple(rows),
                     scrollable_body=True)


def skills_manage_page(installed: list[dict[str, object]] | None,
                       *, pending: bool = False, error: str = "",
                       show: InstalledFilter = InstalledFilter.ALL) -> PanelPage:
    visible = [skill for skill in installed or []
               if show.includes(skill.get("enabled") is not False)]
    rows = [
        PanelRow("manage", RowKind.SECTION, "MANAGE SKILLS",
                 description=(f"{len(installed)} installed · "
                              f"{sum(skill.get('enabled') is not False for skill in installed)} "
                              "enabled") if installed is not None else
                 "Loading installed skills…"),
        PanelRow("filter", RowKind.CHOICE, "Filter", show.label,
                 action=PanelAction("installed-filter-open", "Skills"), section_id="manage"),
        PanelRow("reload", RowKind.ACTION, "Refresh list", legacy_label="Reload",
                 description="Refresh installed skill inventory",
                 enabled=not pending, action=PanelAction("skill-reload"),
                 section_id="manage"),
        PanelRow("update-all", RowKind.ACTION, "Check for updates",
                 description="Check verified GitHub sources and review available updates"
                 if any(skill.get("update_kind") == "github" for skill in installed or [])
                 else "No verified upstream update sources",
                 enabled=not pending and any(
                     skill.get("update_kind") == "github" for skill in installed or []
                 ),
                 action=PanelAction("skill-update-all"), section_id="manage"),
        PanelRow("spacer", RowKind.SEPARATOR, ""),
    ]
    if installed is not None:
        if visible:
            rows.append(PanelRow("installed-items", RowKind.TABLE_HEADER, "INSTALLED SKILLS"))
        rows.extend(PanelRow(
            f"skill:{skill['name']}", RowKind.NAVIGATION, str(skill["name"]),
            ("Enabled" if skill.get("enabled") is not False else "Disabled") + " · "
            + str(skill.get("source_label") or "Source unknown"),
            str(skill.get("description") or "Description unavailable"),
            enabled=bool(skill.get("identity")),
            action=PanelAction("skill-manage-detail", str(skill["name"])),
            section_id="installed-items",
        ) for skill in visible)
        if not installed:
            rows.append(PanelRow("empty", RowKind.INFO, "No skills installed"))
            rows.extend((
                PanelRow("search", RowKind.NAVIGATION, "Search catalog",
                         action=PanelAction("skill-manage-search"), section_id="manage"),
                PanelRow("import", RowKind.NAVIGATION, "Import skills",
                         action=PanelAction("skill-import-open"), section_id="manage"),
            ))
        elif not visible:
            rows.append(PanelRow("empty", RowKind.INFO, f"No {show.value} skills"))
    if error:
        rows.append(PanelRow("feedback", RowKind.STATUS, error, status_tone="warning"))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back",
                         action=PanelAction("skill-manage-back"), footer=True,
                         control=RowControl.BACK))
    return PanelPage("skills-manage", ("Settings", "Skills", "Manage"), tuple(rows),
                     column_headers=("SKILL", "STATUS / SOURCE", "DESCRIPTION")
                     if visible else None, table_section_id="installed-items",
                     scroll_wrapped_rows=True)


def skill_manage_detail_page(skill: Mapping[str, object], *, pending: bool = False,
                             feedback: str = "", feedback_tone: str = "neutral") -> PanelPage:
    name = str(skill["name"])
    raw_files = skill.get("indexed_file_count")
    files = raw_files if type(raw_files) is int else 0
    rows = [
        PanelRow("detail", RowKind.SECTION, "SKILL"),
        PanelRow("source", RowKind.INFO, "Source",
                 description=str(skill.get("source_label") or "Source unknown"),
                 section_id="detail"),
        PanelRow("description", RowKind.INFO, "Description",
                 description=str(skill.get("description") or "Description unavailable"),
                 section_id="detail"),
        PanelRow("files", RowKind.INFO, "Indexed files", str(files), section_id="detail"),
        PanelRow("enabled", RowKind.TOGGLE, "Enabled",
                 enabled=bool(skill.get("identity")) and not pending,
                 checked=skill.get("enabled") is not False,
                 action=PanelAction("skill-toggle", name), section_id="detail"),
        PanelRow("update", RowKind.ACTION, "Check for update",
                 description="Check the original GitHub source for a newer revision"
                 if skill.get("update_kind") == "github" else
                 "No verified upstream update source",
                 enabled=skill.get("update_kind") == "github" and not pending,
                 action=PanelAction("skill-update", name), section_id="detail"),
        PanelRow("delete", RowKind.ACTION, "Delete skill",
                 enabled=bool(skill.get("identity")) and not pending,
                 action=PanelAction("skill-manage-delete", name), section_id="detail"),
    ]
    if feedback:
        rows.append(PanelRow("feedback", RowKind.STATUS, feedback, status_tone=feedback_tone))
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         action=PanelAction("skill-manage-list"), control=RowControl.BACK))
    return PanelPage(f"skill-manage:{name}", ("Settings", "Skills", "Manage", name),
                     tuple(rows), scroll_wrapped_rows=True)


def skill_update_review_page(name: str, current_revision: str,
                             record: SkillRecord) -> PanelPage:
    rows = (
        PanelRow("update", RowKind.SECTION, "UPDATE SKILL"),
        PanelRow("source", RowKind.INFO, "Source", record.repository,
                 section_id="update"),
        PanelRow("path", RowKind.INFO, "Skill path", record.skill_path,
                 section_id="update"),
        PanelRow("current", RowKind.INFO, "Installed revision", current_revision[:12],
                 section_id="update"),
        PanelRow("latest", RowKind.INFO, "New revision", record.revision[:12],
                 section_id="update"),
        PanelRow("license", RowKind.INFO, "Skill license", record.license or "Unknown",
                 section_id="update"),
        PanelRow("compatibility", RowKind.INFO, "Compatibility",
                 record.compatibility or "Unknown", section_id="update"),
        PanelRow("warning", RowKind.INFO,
                 "Updating changes indexed skill content; scripts are not executed"),
        PanelRow("confirm", RowKind.ACTION, "Update skill",
                 action=PanelAction("skill-update-confirm", name)),
        PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                 control=RowControl.BACK, action=PanelAction("skill-update-back", name)),
    )
    return PanelPage(f"skill-update:{name}",
                     ("Settings", "Skills", "Manage", name, "Review update"),
                     rows, scroll_wrapped_rows=True)


def skill_update_all_review_page(updates: list[tuple[str, str, SkillRecord]]) -> PanelPage:
    rows = [
        PanelRow("updates", RowKind.SECTION, "SKILL UPDATES",
                 description=f"{len(updates)} available"),
    ]
    rows.extend(PanelRow(
        f"skill:{name}", RowKind.INFO, name,
        description=(
            f"{current[:12]} → {record.revision[:12]} · "
            f"{record.repository}/{record.skill_path} · "
            f"License: {record.license or 'Unknown'} · "
            f"Compatibility: {record.compatibility or 'Unknown'}"
        ),
        section_id="updates",
    ) for name, current, record in updates)
    rows.extend((
        PanelRow("warning", RowKind.INFO,
                 "Each update rechecks its installed identity; scripts are not executed"),
        PanelRow("confirm", RowKind.ACTION, "Update all",
                 action=PanelAction("skill-update-all-confirm")),
        PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                 control=RowControl.BACK, action=PanelAction("skill-update-all-back")),
    ))
    return PanelPage("skill-update-all-review",
                     ("Settings", "Skills", "Manage", "Review updates"),
                     tuple(rows), scroll_wrapped_rows=True)


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
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", footer=True,
                         control=RowControl.BACK, action=PanelAction("skill-list")))
    return PanelPage("skills-delete", ("Settings", "Skills", "Delete skill"), tuple(rows))


def skill_delete_confirmation_page(skill: Mapping[str, object]) -> PanelPage:
    name = str(skill["name"])
    rows = [
        PanelRow("name", RowKind.INFO, "Skill", name),
        PanelRow("library", RowKind.INFO, "Library", str(skill.get("library", "?"))),
        PanelRow(
            "delete",
            RowKind.ACTION,
            "Delete this skill",
            description="Remove installed files and this skill's indexed content",
            action=PanelAction("skill-delete", name),
        ),
    ]
    rows.append(PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("skill-list")))
    return PanelPage(
        f"skill-delete-confirm:{name}",
        ("Settings", "Skills", "Manage", name, "Confirm deletion"),
        tuple(rows),
    )
