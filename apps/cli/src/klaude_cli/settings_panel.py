"""Typed settings pages and width-aware, terminal-friendly panel rendering."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from enum import StrEnum

from prompt_toolkit.utils import get_cwidth

from .pickers import PickerController, PickerRow


class RowKind(StrEnum):
    SECTION = "section"
    INFO = "info"
    NAVIGATION = "navigation"
    TOGGLE = "toggle"
    CHOICE = "choice"
    ACTION = "action"
    STATUS = "status"
    SEPARATOR = "separator"


@dataclass(frozen=True)
class PanelAction:
    kind: str
    target: str = ""


@dataclass(frozen=True)
class PanelRow:
    id: str
    kind: RowKind
    label: str
    value: str = ""
    description: str = ""
    status: str = ""
    status_tone: str = "neutral"
    enabled: bool = True
    selected: bool = False
    action: PanelAction | None = None
    navigation_target: str = ""
    section_id: str = ""
    legacy_label: str = ""
    checked: bool | None = None
    value_tone: str = "neutral"

    def __post_init__(self) -> None:
        if self.kind == RowKind.TOGGLE and type(self.checked) is not bool:
            raise ValueError("Toggle rows require a boolean checked state")
        if self.status_tone not in {"neutral", "success", "warning", "error"}:
            raise ValueError("Invalid panel status tone")
        if self.value_tone not in {"neutral", "success", "warning", "error"}:
            raise ValueError("Invalid panel value tone")

    @property
    def effective_value(self) -> str:
        return toggle_text(self.checked is True) if self.kind == RowKind.TOGGLE else self.value

    @property
    def selectable(self) -> bool:
        return self.kind in {RowKind.NAVIGATION, RowKind.TOGGLE, RowKind.CHOICE, RowKind.ACTION}

    def picker_row(self) -> PickerRow:
        return PickerRow(
            self.id,
            self.legacy_label or self.label,
            self.selectable,
            self.navigation_target == "back" or (
                self.action is not None and self.action.kind in {"back", "close"}
            ),
            enabled=self.enabled,
            search_text=" ".join((self.label, self.effective_value, self.description)),
            section_id=self.section_id or None,
        )


@dataclass(frozen=True)
class PanelPage:
    id: str
    breadcrumb: tuple[str, ...]
    rows: tuple[PanelRow, ...]
    subtitle: str = ""
    legacy_actions: bool = False

    def __post_init__(self) -> None:
        ids = [row.id for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Panel row IDs must be unique")


@dataclass(frozen=True)
class BodyRender:
    lines: tuple[tuple[tuple[str, str], ...], ...]
    row_for_line: tuple[str | None, ...]
    selected_line: int
    context_line: int


class PanelState:
    """Page-local focus, search, and line viewport survive value refreshes."""

    def __init__(self, page: PanelPage, default_id: str = "") -> None:
        self.page = page
        self.picker = PickerController([row.picker_row() for row in page.rows], default_id)
        self.scroll_top = 0
        self.search_active = False

    def replace(self, page: PanelPage) -> None:
        if page.id != self.page.id:
            raise ValueError("Cannot replace a different panel page")
        self.page = page
        self.picker.replace([row.picker_row() for row in page.rows])

    def bind_picker(self, page: PanelPage, picker: PickerController) -> None:
        """Present an existing settings picker without replacing its state machine."""
        if page.id != self.page.id:
            raise ValueError("Cannot bind a different panel page")
        self.page = page
        self.picker = picker

    def row(self, identity: str | None = None) -> PanelRow | None:
        target = self.picker.selected_id if identity is None else identity
        return next((row for row in self.page.rows if row.id == target), None)

    def visible_rows(self) -> list[PanelRow]:
        by_id = {row.id: row for row in self.page.rows}
        return [
            by_id[item.id]
            if item.id in by_id
            else PanelRow(item.id, RowKind.STATUS, "No matching options")
            for item in self.picker.visible
        ]

    def filter(self, query: str) -> None:
        self.picker.filter(query)
        self.scroll_top = 0

    def move(self, delta: int) -> None:
        indices = [i for i, row in enumerate(self.picker.visible) if row.selectable]
        if not indices:
            return
        current = self.picker.index
        position = indices.index(current) if current in indices else 0
        self.picker.select(indices[(position + delta) % len(indices)])

    def viewport(self, height: int, body: BodyRender) -> int:
        height = max(1, height)
        selected = body.selected_line
        if selected < self.scroll_top:
            self.scroll_top = selected
        elif selected >= self.scroll_top + height:
            self.scroll_top = selected - height + 1
        if body.context_line < selected:
            self.scroll_top = min(self.scroll_top, max(body.context_line, selected - height + 1))
        self.scroll_top = max(0, min(self.scroll_top, max(0, len(body.lines) - height)))
        return self.scroll_top


def _fit(value: str, width: int) -> str:
    if width <= 0:
        return ""
    if get_cwidth(value) <= width:
        return value + " " * (width - get_cwidth(value))
    while value and get_cwidth(value + "…") > width:
        value = value[:-1]
    return value + "…" if value else "…"


def _wrapped(value: str, width: int) -> list[str]:
    return textwrap.wrap(value, width=max(1, width), break_long_words=True) or []


def toggle_text(checked: bool, *, unicode_blocks: bool = True) -> str:
    block = "■" if unicode_blocks else "X"
    return f"[  {block}] ON" if checked else f"[{block}  ] OFF"


def _value_fragments(
    row: PanelRow, value: str, style: str, *, unicode_blocks: bool
) -> tuple[tuple[str, str], ...]:
    if row.kind == RowKind.TOGGLE and row.checked is True and row.enabled:
        block = "■" if unicode_blocks else "X"
        before, found, after = value.partition(block)
        if found:
            return ((style, before), ("class:toggle.on", found), (style, after))
    return ((style, value),)


def _value_style(row: PanelRow) -> str:
    if not row.enabled:
        return "class:panel.disabled"
    if row.value_tone != "neutral":
        return f"class:panel.value.{row.value_tone}"
    return "class:panel.value"


def _focused_line(
    fragments: tuple[tuple[str, str], ...], width: int
) -> tuple[tuple[str, str], ...]:
    styled = tuple(
        (f"class:panel.selected {style}" if style else "class:panel.selected", text)
        for style, text in fragments
    )
    # Leave the final terminal cell unused to avoid deferred wrapping.
    remaining = max(0, width - 1 - sum(get_cwidth(text) for _style, text in fragments))
    if remaining:
        return (*styled, ("class:panel.selected", " " * remaining))
    return styled


def render_body(state: PanelState, width: int, *, unicode_blocks: bool = True) -> BodyRender:
    """Return styled logical lines; only the body is allowed to scroll."""
    width = max(1, width)
    rows = state.visible_rows()
    lines: list[tuple[tuple[str, str], ...]] = []
    owners: list[str | None] = []
    selected_line = 0
    context_line = 0
    last_section_line = 0
    for row in rows:
        value = (
            toggle_text(row.checked is True, unicode_blocks=unicode_blocks)
            if row.kind == RowKind.TOGGLE
            else row.value
        )
        start = len(lines)
        parts: tuple[tuple[str, str], ...]
        if row.kind == RowKind.SECTION:
            last_section_line = start
            heading = _fit(row.label.upper(), width - 2).rstrip()
            parts = (
                ("class:panel.heading-marker", "▪ "),
                ("class:panel.section", heading),
            )
        elif row.kind == RowKind.SEPARATOR:
            parts = (("", ""),)
        elif row.kind in {RowKind.INFO, RowKind.STATUS}:
            if row.value:
                parts = (
                    ("class:panel.muted", f"  {_fit(row.label, max(1, width // 2)).rstrip()}"),
                    (_value_style(row), f"  {row.value}"),
                )
            else:
                info_lines = _wrapped(row.label, width - 2)
                parts = (
                    (("class:panel.muted", f"  {info_lines[0]}"),)
                    if info_lines else (("", ""),)
                )
        else:
            marker = "›" if row.id == state.picker.selected_id else " "
            label_style = "class:panel.disabled" if not row.enabled else "class:panel.label"
            value_style = _value_style(row)
            stacked_value = False
            stacked_description = False
            if width >= 90:
                label_width = min(28, max(12, width // 3))
                value_width = min(max(8, get_cwidth(value)), width - label_width - 6)
                description_width = max(0, width - label_width - value_width - 7)
                stacked_value = get_cwidth(value) > value_width
                stacked_description = description_width < 12
                parts = (
                    ("class:panel.focus", f"{marker} "),
                    (label_style, _fit(row.label, label_width)),
                ) + _value_fragments(
                    row, "  " + _fit("" if stacked_value else value, value_width),
                    value_style, unicode_blocks=unicode_blocks,
                ) + (
                    (
                        "class:panel.muted",
                        "  "
                        + _fit(
                            "" if stacked_description else row.description, description_width
                        ).rstrip(),
                    ),
                )
            elif width >= 55:
                label_width = max(14, width - min(20, max(8, width // 3)) - 4)
                value_width = max(1, width - label_width - 4)
                stacked_value = get_cwidth(value) > value_width
                parts = (
                    ("class:panel.focus", f"{marker} "),
                    (label_style, _fit(row.label, label_width)),
                ) + _value_fragments(
                    row, "  " + _fit("" if stacked_value else value, value_width).rstrip(),
                    value_style, unicode_blocks=unicode_blocks,
                )
            else:
                label_lines = _wrapped(row.label, width - 2)
                parts = (
                    ("class:panel.focus", f"{marker} "),
                    (label_style, label_lines[0] if label_lines else ""),
                )
        lines.append(parts)
        owners.append(row.id)
        if row.kind in {RowKind.INFO, RowKind.STATUS} and not row.value:
            for extra in info_lines[1:]:
                lines.append((("class:panel.muted", f"  {extra}"),))
                owners.append(row.id)
        if row.id == state.picker.selected_id:
            selected_line = start
            context_line = last_section_line
        if row.selectable and width < 55:
            for label_line in label_lines[1:]:
                lines.append(((label_style, f"  {label_line}"),))
                owners.append(row.id)
            if value:
                for value_line in _wrapped(value, width - 4):
                    lines.append(_value_fragments(
                        row, f"    {value_line}", value_style,
                        unicode_blocks=unicode_blocks,
                    ))
                    owners.append(row.id)
        elif row.selectable and stacked_value:
            for value_line in _wrapped(value, width - 4):
                lines.append(_value_fragments(
                    row, f"    {value_line}", value_style,
                    unicode_blocks=unicode_blocks,
                ))
                owners.append(row.id)
        if row.selectable and row.description and (width < 90 or stacked_description):
            for description in _wrapped(row.description, width - 4):
                lines.append((("class:panel.muted", f"    {description}"),))
                owners.append(row.id)
        if row.selectable and row.status:
            lines.append(((f"class:panel.status.{row.status_tone}", f"    {row.status}"),))
            owners.append(row.id)
    selected_id = state.picker.selected_id
    if selected_id is not None:
        for index, owner in enumerate(owners):
            if owner == selected_id:
                lines[index] = _focused_line(lines[index], width)
    return BodyRender(tuple(lines), tuple(owners), selected_line, context_line)


def render_header(page: PanelPage, width: int, query: str = "") -> tuple[tuple[str, str], ...]:
    title = " › ".join(page.breadcrumb)
    if get_cwidth(title) > width and len(page.breadcrumb) > 1:
        title = " › ".join(page.breadcrumb[-2:])
    if get_cwidth(title) > width:
        title = page.breadcrumb[-1]
    if query and get_cwidth(title) + get_cwidth(query) + 4 <= width:
        title += f"  / {query}"
    return (
        ("class:panel.header", _fit(title, max(1, width)).rstrip() + "\n"),
        ("class:panel.rule", "─" * max(1, width)),
    )


def render_footer(
    width: int, *, search: bool, query: str = "", status: str = "", status_style: str = ""
) -> tuple[tuple[str, str], ...]:
    hints = (
        f"/{query} · ENTER select · ESC clear"
        if search
        else "↑↓ move · ENTER open/apply · SPACE toggle · / search · ESC back"
    )
    status_width = min(get_cwidth(status), max(0, width // 2))
    hint_width = max(0, width - status_width - (2 if status else 0))
    return (
        ("class:panel.rule", "─" * max(1, width) + "\n"),
        ("class:panel.muted", _fit(hints, hint_width)),
        (status_style, f"  {_fit(status, status_width).rstrip()}" if status else ""),
    )
