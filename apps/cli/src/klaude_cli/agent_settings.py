"""Typed Agent Tools execution pages using authoritative live state."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from klaude_core.agent_settings import (
    EXECUTION_LIMITS,
    apply_execution_settings,
    execution_defaults,
    public_execution_settings,
)
from klaude_core.runtime_context import sanitize_text
from klaude_core.settings_store import DELETE
from klaude_core.tool_settings import BUILTIN_TOOL_LABELS, tool_groups

from .model_settings import row as model_row
from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

FIELDS = {
    "steps": ("max_steps", "Max steps per message"),
    "calls": ("max_tool_calls", "Tool-call limit"),
    "tokens": ("max_total_tokens", "Total token budget"),
    "workers": ("max_subagent_concurrency", "Subagent workers"),
}


def row(identity: str, label: str, value: str = "", **kwargs: Any) -> PanelRow:
    return replace(
        model_row(identity, label, value, **kwargs),
        action=PanelAction("agent-settings-" + identity, kwargs.get("target", "")),
    )


def back(target: str) -> PanelRow:
    return row("back", "Back", target=target, kind=RowKind.NAVIGATION, control=RowControl.BACK)


class AgentSettings:
    def __init__(self, host: Any):
        self.host = host
        self.view = "home"
        self.feedback: tuple[str, str] | None = None
        self.legacy_parent = ""
        self.legacy_return = ("home", "tools")
        self.tool_return: str = ""
        self.group = ""
        self.tool = ""
        self._usage_snapshot: tuple[int | None, int] = (None, 0)

    @property
    def visible(self) -> bool:
        return str(self.host._choice_kind).startswith("agent settings ")

    def worker_count(self, *, automatic: bool = False) -> int:
        from .main import _subagent_parallelism

        return _subagent_parallelism(self.host.agent, configured=0 if automatic else None)

    def value(self, field: str) -> str:
        agent = self.host.agent
        if field == "steps":
            return str(agent.max_steps)
        if field == "calls":
            limit = getattr(agent, "max_tool_calls", None)
            return str(limit) if limit else f"Auto · {max(4, agent.max_steps * 2)} effective"
        if field == "tokens":
            limit = getattr(agent, "max_total_tokens", None)
            return f"{limit:,} tokens" if limit else "No total-token cap"
        limit = getattr(agent, "max_subagent_concurrency", 0)
        return str(limit) if limit else f"Auto · {self.worker_count()} effective"

    def show(self, view: str | None = None, focus: str = "") -> None:
        if view is not None:
            self.view = view
        page = self.page()
        self.host._open_panel(page, "agent settings " + page.id.removeprefix("agent:"), focus)
        if focus:
            self.host._panel.picker.focus(focus)
            self.host._apply_picker_state()
        if self.feedback:
            self.host._set_panel_feedback(*self.feedback)

    def usage(self) -> tuple[int | None, int]:
        snapshot = getattr(self.host.agent, "last_turn_budget", {}) or {}
        reported = snapshot.get("total_tokens_used")
        unknown = snapshot.get("token_usage_unknown_requests", 0)
        return (
            reported if type(reported) is int and 0 <= reported <= 2**63 - 1 else None,
            unknown if type(unknown) is int and 0 <= unknown <= 2**63 - 1 else 0,
        )

    def refresh_usage(self) -> None:
        if self.visible and self.view == "advanced" and self.usage() != self._usage_snapshot:
            self.show()

    def open(self, *, view: str = "home") -> None:
        self.feedback = None
        self.legacy_parent = ""
        self.tool_return = ""
        self.show(view)

    def groups(self) -> dict[str, tuple[str, ...]]:
        registry = getattr(self.host.agent, "tools", {})
        for name in registry:
            if not name.startswith("mcp__"):
                self.host._tool_availability.setdefault(
                    name, name not in getattr(self.host.agent, "disabled_tool_names", set())
                )
        return dict(tool_groups(registry))

    def count(self, names: tuple[str, ...]) -> str:
        enabled = sum(self.host._tool_availability.get(name, True) for name in names)
        return f"{enabled}/{len(names)} enabled"

    def open_tool(self, name: str, *, parent: str = "") -> None:
        groups = self.groups()
        self.group = next((group for group, names in groups.items() if name in names), "")
        if not self.group:
            raise ValueError("Tool is no longer registered")
        self.tool, self.tool_return = name, parent
        self.feedback = None
        self.show("tool")

    def return_from_owner(self, kind: str | None) -> bool:
        if not self.legacy_parent or kind != self.legacy_parent:
            return False
        self.legacy_parent = ""
        self.show(*self.legacy_return)
        return True

    def owner(self, category: str, focus: str = "") -> None:
        self.legacy_return = (self.view, focus or category)
        self.legacy_parent = {
            "mcp servers": "mcp settings",
            "skills": "skills settings",
            "permissions": "permission settings",
        }[category]
        self.host._open_settings_category(category)

    def toggle_tools(self, names: tuple[str, ...], focus: str) -> None:
        registered = {name for group in self.groups().values() for name in group}
        names = tuple(name for name in names if name in registered)
        if not names:
            raise ValueError("Tool is no longer registered")
        enabled = not all(self.host._tool_availability[name] for name in names)
        self.host._tool_availability.update(dict.fromkeys(names, enabled))
        self.host._apply_live_tool_preferences()
        self.save({("tool_availability", name): enabled for name in names}, focus)

    def page(self) -> PanelPage:
        crumbs: tuple[str, ...] = ("Settings", "Agent Tools")
        rows: list[PanelRow] = []
        agent = self.host.agent
        if self.view == "home":
            rows = [
                row("execution", "Execution", f"{agent.max_steps} steps · " + self.value("calls")),
                row(
                    "tools",
                    "Built-in Tools",
                    self.count(tuple(name for names in self.groups().values() for name in names)),
                ),
                row(
                    "activity",
                    "Activity Updates",
                    "ON" if self.host.show_activity_updates else "OFF",
                    kind=RowKind.TOGGLE,
                    checked=self.host.show_activity_updates,
                ),
                row("mcp servers", "MCPs", description="Manage external servers and their tools"),
                row("skills", "Skills", description="Manage installed skills"),
                back("settings"),
            ]
        elif self.view == "tools":
            crumbs += ("Built-in Tools",)
            rows = [
                row(
                    "group:" + group,
                    group.title(),
                    self.count(names),
                    kind=RowKind.NAVIGATION,
                    target=group,
                    description="Mixed"
                    if 0 < sum(self.host._tool_availability[n] for n in names) < len(names)
                    else "",
                )
                for group, names in self.groups().items()
            ]
            if not rows:
                rows.append(PanelRow("empty", RowKind.INFO, "No built-in tools registered"))
            rows.append(
                row(
                    "reset-tools",
                    "Reset to default",
                    control=RowControl.RESET,
                    description="Enable registered built-in tools; keep permissions",
                )
            )
            rows.append(back("home"))
        elif self.view == "group":
            crumbs += ("Built-in Tools", self.group.title())
            names = self.groups().get(self.group, ())
            enabled = sum(self.host._tool_availability[name] for name in names)
            rows = [
                replace(
                    row(
                        "group-toggle",
                        "Enable group",
                        kind=RowKind.TOGGLE,
                        checked=enabled == len(names),
                        enabled=bool(names),
                        description=self.count(names),
                    ),
                    mixed=0 < enabled < len(names),
                )
            ]
            rows.extend(
                row(
                    "tool:" + name,
                    BUILTIN_TOOL_LABELS.get(name, name),
                    "ON" if self.host._tool_availability[name] else "OFF",
                    kind=RowKind.NAVIGATION,
                    target=name,
                )
                for name in names
            )
            if "query_knowledge" in names:
                rows.append(
                    row(
                        "knowledge-validation",
                        "Validate knowledge results",
                        kind=RowKind.TOGGLE,
                        checked=self.host._tool_validation["knowledge_search"],
                    )
                )
            rows.append(back("tools"))
        elif self.view == "tool":
            from .main import PERMISSION_VALUE_TONES, _effective_permission_policies

            crumbs += (
                "Built-in Tools",
                self.group.title(),
                BUILTIN_TOOL_LABELS.get(self.tool, self.tool),
            )
            tool = getattr(self.host.agent, "tools", {}).get(self.tool)
            enabled = self.host._tool_availability.get(self.tool, True)
            policy = _effective_permission_policies(self.host.agent, self.host.cfg).get(
                self.tool, "ask"
            )
            rows = [
                row(
                    "tool-toggle",
                    "Enabled",
                    kind=RowKind.TOGGLE,
                    checked=enabled,
                    enabled=tool is not None,
                ),
                PanelRow(
                    "purpose",
                    RowKind.INFO,
                    "Purpose",
                    description=sanitize_text(
                        getattr(tool, "description", "Tool is no longer registered"), max_chars=600
                    ),
                ),
                replace(
                    row(
                        "permissions",
                        "Permission policy",
                        policy.upper(),
                        description="Availability never grants permission",
                    ),
                    value_tone=PERMISSION_VALUE_TONES.get(policy, "neutral"),
                ),
            ]
            if self.tool in {"web_search", "fetch_url"}:
                rows.append(
                    row(
                        "configure",
                        "Configure " + ("Web Search" if self.tool == "web_search" else "URL Fetch"),
                    )
                )
            if self.tool == "read_skill":
                rows.append(row("skills", "Manage Skills"))
            rows.append(back("tool-parent"))
        elif self.view == "execution":
            crumbs += ("Execution",)
            rows = [
                row(
                    "steps",
                    FIELDS["steps"][1],
                    self.value("steps"),
                    description="Applies to new messages",
                ),
                row(
                    "calls",
                    FIELDS["calls"][1],
                    self.value("calls"),
                    description="Auto derives a finite ceiling from the step limit",
                ),
                row(
                    "workers",
                    FIELDS["workers"][1],
                    self.value("workers"),
                    description="Auto keeps local and compatible models at one worker",
                ),
                row(
                    "advanced",
                    "Advanced",
                ),
                row(
                    "reset",
                    "Reset to default",
                    control=RowControl.RESET,
                    description="Execution limits only; keep device, tools and permissions",
                ),
                back("home"),
            ]
        elif self.view == "advanced":
            crumbs += ("Execution", "Advanced")
            reported, unknown = self._usage_snapshot = self.usage()
            rows = [
                row("tokens", FIELDS["tokens"][1], self.value("tokens")),
                PanelRow(
                    "semantics",
                    RowKind.INFO,
                    "Counts provider-reported input and output tokens",
                    description="Checked between calls; responses can cross the cap.",
                ),
                PanelRow(
                    "usage",
                    RowKind.INFO,
                    "Last or active message",
                    f"{reported:,} reported tokens"
                    if type(reported) is int
                    else "No usage recorded",
                ),
                PanelRow(
                    "unknown",
                    RowKind.INFO,
                    "Unreported usage",
                    f"{unknown} requests" if type(unknown) is int else "Unknown",
                ),
                back("execution"),
            ]
        elif self.view in FIELDS:
            field = self.view
            key, label = FIELDS[field]
            crumbs += ("Execution", label)
            active = getattr(agent, key, None)
            if field == "steps":
                rows = [
                    row(
                        "choose:" + str(n),
                        str(n) + " steps",
                        "Current" if active == n else "",
                        target=str(n),
                    )
                    for n in (12, 20, 40)
                ]
            elif field == "workers":
                rows = [
                    row(
                        "choose:0",
                        "Auto",
                        "Current" if not active else "",
                        target="0",
                        description=(
                            f"{self.worker_count(automatic=True)} effective · provider policy"
                        ),
                    )
                ]
                rows += [
                    row("choose:" + str(n), str(n), "Current" if active == n else "", target=str(n))
                    for n in range(1, 5)
                ]
            else:
                rows = [
                    row(
                        "choose:0",
                        "Auto" if field == "calls" else "No total-token cap",
                        "Current" if not active else "",
                        target="0",
                        description=f"{max(4, agent.max_steps * 2)} calls effective"
                        if field == "calls"
                        else "Step/time and non-progress bounds remain finite",
                    )
                ]
            if field != "workers":
                _minimum, maximum = EXECUTION_LIMITS[key]
                rows.append(
                    row(
                        "custom",
                        "Custom",
                        str(active) if active else "",
                        description=f"1–{maximum:,}",
                    )
                )
            rows.extend(
                [
                    row(
                        "reset-field",
                        "Reset to default",
                        control=RowControl.RESET,
                        description="Restore configured default for this limit",
                    ),
                    back("advanced" if field == "tokens" else "execution"),
                ]
            )
        identity = self.view + (
            ":" + self.group
            if self.view == "group"
            else ":" + self.tool
            if self.view == "tool"
            else ""
        )
        return PanelPage(
            "agent:" + identity,
            crumbs,
            tuple(rows),
            scroll_wrapped_rows=True,
            subtitle="Enter: details · Space: toggle" if self.view == "group" else "",
        )

    def save(self, changes: dict[tuple[str, ...], object], focus: str = "") -> None:
        self.feedback = None
        self.host._submit_preference_changes(changes)
        self.show(focus=focus)

    def set_value(self, field: str, value: int | None, *, reset: bool = False) -> None:
        key = FIELDS[field][0]
        apply_execution_settings(self.host.agent, {key: value})
        if reset:
            self.host._runtime_preferences.pop(key, None)
        else:
            self.host._runtime_preferences[key] = value
        self.view = "advanced" if field == "tokens" else "execution"
        self.save({("runtime_options", key): DELETE if reset else value}, field)

    def action(self, action: PanelAction) -> None:
        kind = action.kind.removeprefix("agent-settings-")
        if kind == "back":
            if action.target == "settings":
                self.host._begin_choice(
                    "settings", self.host._settings_categories(), "Tools", refresh=True
                )
            elif action.target == "tool-parent":
                parent, self.tool_return = self.tool_return, ""
                if parent in {"search", "fetch"}:
                    controller = (
                        self.host._search_settings
                        if parent == "search"
                        else self.host._fetch_settings
                    )
                    controller.show("home", "enabled")
                else:
                    self.show("group", "tool:" + self.tool)
            elif action.target == "home":
                self.show("home", "tools")
            elif action.target == "tools":
                self.show("tools", "group:" + self.group)
            else:
                self.show(action.target)
        elif kind in {"execution", "advanced", *FIELDS}:
            self.show(kind)
        elif kind == "tools":
            self.show("tools")
        elif kind == "reset-tools":
            names = tuple(name for names in self.groups().values() for name in names)
            self.host._tool_availability.update(dict.fromkeys(names, True))
            self.host._apply_live_tool_preferences()
            # Publish defaults explicitly so other clients can merge a confirmed
            # reset through the bounded boolean acknowledgement.
            self.save({("tool_availability", name): True for name in names}, kind)
        elif kind.startswith("group:"):
            self.group = action.target
            self.show("group")
        elif kind.startswith("tool:"):
            self.open_tool(action.target)
        elif kind == "toggle-entry":
            self.toggle_tools((action.target,), "tool:" + action.target)
        elif kind == "tool-toggle":
            self.toggle_tools((self.tool,), "tool-toggle")
        elif kind == "group-toggle":
            self.toggle_tools(self.groups().get(self.group, ()), "group-toggle")
        elif kind == "knowledge-validation":
            values = self.host._tool_validation
            values["knowledge_search"] = not values["knowledge_search"]
            self.host._apply_live_tool_preferences()
            self.save({("tool_validation", "knowledge_search"): values["knowledge_search"]}, kind)
        elif kind in {"mcp servers", "skills", "permissions"}:
            self.owner(kind)
            if kind == "permissions" and self.tool:
                self.host._panel.picker.focus("tool:" + self.tool)
                self.host._apply_picker_state()
        elif kind == "configure":
            if self.tool == "web_search":
                self.host._search_settings.open(parent="agent-tool")
            else:
                self.host._fetch_settings.open(parent="agent-tool")
        elif kind == "activity":
            self.host.show_activity_updates = not self.host.show_activity_updates
            self.save(
                {
                    ("display", "activity_updates"): self.host.show_activity_updates,
                    ("display", "reasoning_activity"): DELETE,
                },
                "activity",
            )
        elif kind.startswith("choose:"):
            self.set_value(self.view, int(action.target))
        elif kind == "custom":
            key, label = FIELDS[self.view]
            _minimum, maximum = EXECUTION_LIMITS[key]
            self.host._begin_settings_input(
                label, f"Whole number from 1 to {maximum:,}", ("agent-settings", self.view)
            )
            self.host._set_input(str(getattr(self.host.agent, key, None) or ""))
        elif kind == "reset-field":
            self.set_value(
                self.view, execution_defaults(self.host.cfg)[FIELDS[self.view][0]], reset=True
            )
        elif kind == "reset":
            defaults = execution_defaults(self.host.cfg)
            apply_execution_settings(self.host.agent, defaults)
            for key in defaults:
                self.host._runtime_preferences.pop(key, None)
            self.save({("runtime_options", key): DELETE for key in defaults}, "reset")

    def answer(self, field: str, value: str | None) -> None:
        if value is None:
            self.host._set_input("")
            self.show(field)
            return
        key = FIELDS[field][0]
        _minimum, maximum = EXECUTION_LIMITS[key]
        try:
            parsed = int(value)
        except ValueError:
            raise ValueError(f"Enter a whole number from 1 to {maximum:,}") from None
        if not 1 <= parsed <= maximum:
            raise ValueError(f"Enter a whole number from 1 to {maximum:,}")
        # Returning from the private editor opens a panel while choice mode is
        # suspended. Never let its number become the saved chat composer draft.
        self.host._set_input("")
        self.set_value(field, parsed)

    def merge_saved(self, raw: Any) -> None:
        values = public_execution_settings(raw)
        apply_execution_settings(self.host.agent, execution_defaults(self.host.cfg))
        for key in EXECUTION_LIMITS:
            self.host._runtime_preferences.pop(key, None)
        self.host._runtime_preferences.update(values)
        apply_execution_settings(self.host.agent, values)
        if self.visible:
            self.show()
