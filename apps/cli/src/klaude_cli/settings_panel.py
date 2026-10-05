"""Typed settings pages and width-aware, terminal-friendly panel rendering."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from enum import StrEnum

import regex
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
    TABLE_HEADER = "table_header"


class RowControl(StrEnum):
    BACK = "back"
    CLOSE = "close"
    CANCEL = "cancel"
    RESET = "reset"


_ACTION_CONTROLS = {
    "back": RowControl.BACK, "memory-back": RowControl.BACK,
    "memory-list": RowControl.BACK, "skill-back": RowControl.BACK,
    "skill-list": RowControl.BACK, "close": RowControl.CLOSE,
    "reset": RowControl.RESET, "reset-all": RowControl.RESET,
}
_CONTROL_ICONS = {
    RowControl.BACK: "←", RowControl.CLOSE: "×",
    RowControl.CANCEL: "×", RowControl.RESET: "⏻",
}


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
    footer: bool = False
    search_terms: str = ""
    label_badge: str = ""
    control: RowControl | None = None

    def __post_init__(self) -> None:
        if self.kind == RowKind.TOGGLE and type(self.checked) is not bool:
            raise ValueError("Toggle rows require a boolean checked state")
        if self.status_tone not in {"neutral", "success", "warning", "error"}:
            raise ValueError("Invalid panel status tone")
        if self.value_tone not in {"neutral", "success", "warning", "error"}:
            raise ValueError("Invalid panel value tone")

    @property
    def effective_control(self) -> RowControl | None:
        return self.control or (
            _ACTION_CONTROLS.get(self.action.kind) if self.action is not None else None
        )

    @property
    def display_label(self) -> str:
        control = self.effective_control
        return f"{_CONTROL_ICONS[control]} {self.label.upper()}" if control else self.label

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
            self.effective_control in {RowControl.BACK, RowControl.CLOSE, RowControl.CANCEL}
            or self.navigation_target == "back" or (
                self.action is not None and self.action.kind in {"back", "close"}
            ),
            enabled=self.enabled,
            search_text=" ".join((self.label, self.effective_value, self.description,
                                  self.search_terms, self.label_badge)),
            section_id=self.section_id or None,
        )


@dataclass(frozen=True)
class PanelPage:
    id: str
    breadcrumb: tuple[str, ...]
    rows: tuple[PanelRow, ...]
    subtitle: str = ""
    legacy_actions: bool = False
    column_headers: tuple[str, str, str] | None = None
    table_section_id: str = ""
    scroll_wrapped_rows: bool = False
    scrollable_body: bool = False

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
        self._scroll_row_id: str | None = None
        self._row_line_offset = 0

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
        self._row_line_offset = 0

    def move(self, delta: int) -> None:
        indices = [i for i, row in enumerate(self.picker.visible) if row.selectable]
        if not indices:
            return
        current = self.picker.index
        position = indices.index(current) if current in indices else 0
        self.picker.select(indices[(position + delta) % len(indices)])

    def focus_line(self, body: BodyRender) -> int:
        """Keep an oversized table row readable without changing its identity."""
        if not (self.page.column_headers or self.page.scroll_wrapped_rows
                or self.page.scrollable_body):
            return body.selected_line
        if self._scroll_row_id != self.picker.selected_id:
            self._scroll_row_id = self.picker.selected_id
            self._row_line_offset = 0
        if self.page.scrollable_body:
            return max(0, min(len(body.lines) - 1, body.selected_line + self._row_line_offset))
        count = sum(owner == self.picker.selected_id for owner in body.row_for_line)
        self._row_line_offset = min(self._row_line_offset, max(0, count - 1))
        return body.selected_line + self._row_line_offset

    def scroll_row(self, delta: int, body: BodyRender) -> bool:
        """Page through wrapped result content before moving to another result."""
        current = self.focus_line(body)
        if self.page.scrollable_body:
            target = max(0, min(current + delta, len(body.lines) - 1))
            if target == current:
                return False
            self._row_line_offset = target - body.selected_line
            return True
        count = sum(owner == self.picker.selected_id for owner in body.row_for_line)
        target = max(body.selected_line, min(current + delta, body.selected_line + count - 1))
        if target == current:
            return False
        self._row_line_offset = target - body.selected_line
        return True

    def viewport(self, height: int, body: BodyRender) -> int:
        height = max(1, height)
        selected = self.focus_line(body)
        if selected < self.scroll_top:
            self.scroll_top = selected
        elif selected >= self.scroll_top + height:
            self.scroll_top = selected - height + 1
        if body.context_line < selected and selected == body.selected_line:
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


def _wrapped(value: str, width: int, *, break_on_hyphens: bool = False) -> list[str]:
    width = max(1, width)
    lines: list[str] = []
    # textwrap chooses readable word boundaries; terminal cells, rather than
    # Python string length, decide where each resulting line must end.
    for word_line in textwrap.wrap(value, width=width, break_long_words=False,
                                   break_on_hyphens=break_on_hyphens):
        line = ""
        line_width = 0
        for cluster in regex.findall(r"\X", word_line):
            cluster_width = get_cwidth(cluster)
            if line and line_width + cluster_width > width:
                lines.append(line)
                line = ""
                line_width = 0
            line += cluster
            line_width += cluster_width
        if line:
            lines.append(line)
    return lines


def _table_widths(
    width: int, headers: tuple[str, str, str] | None = None,
) -> tuple[int, int, int]:
    available = width - 7  # selector, two column gaps, unused final terminal cell
    name = min(40, max(20, available // 3))
    source_column = headers is not None and headers[1].upper() == "SOURCE"
    value = min(26 if source_column else 18,
                max(14 if source_column else 9,
                    available // (4 if source_column else 6),
                    get_cwidth(headers[1]) if headers else 0))
    return name, value, available - name - value


def _cell_lines(text: str, width: int) -> list[str]:
    return _wrapped(text, width, break_on_hyphens=True) or [""]


def _table_header_fragments(
    headers: tuple[str, str, str], width: int,
) -> tuple[tuple[str, str], ...]:
    fragments: tuple[tuple[str, str], ...] = (("", "  "),)
    for index, (label, size) in enumerate(zip(headers, _table_widths(width, headers), strict=True)):
        if index:
            fragments += (("", "  "),)
        heading = _fit(label.upper(), size).rstrip()
        for word_index, word in enumerate(heading.split(" ")):
            if word_index:
                fragments += (("", " "),)
            if word:
                fragments += (("class:panel.section", word),)
        fragments += (("", " " * (size - get_cwidth(heading))),)
    return fragments


def _table_row_lines(
    row: PanelRow, width: int, selected: bool,
    headers: tuple[str, str, str] | None = None,
) -> list[tuple[tuple[str, str], ...]]:
    marker = "›" if selected else " "
    badge_width = get_cwidth(row.label_badge) + 3 if row.label_badge else 0
    if width < 60:
        labels = _cell_lines(row.display_label, max(2, width - 2 - badge_width))
        lines: list[tuple[tuple[str, str], ...]] = [
            (("class:panel.focus", marker + " "),)
            + _label_fragments(row, labels[0], "class:panel.label")
        ]
        lines.extend((("class:panel.label", " " * (2 + badge_width) + line),)
                     for line in labels[1:])
        for text, style in ((row.value, _value_style(row)),
                            (row.description, "class:panel.muted")):
            lines.extend(((style, "    " + line),)
                         for line in _cell_lines(text, max(2, width - 4)) if line)
        return lines
    widths = _table_widths(width, headers)
    cells = [_cell_lines(row.display_label, widths[0] - badge_width),
             _cell_lines(row.value, widths[1]), _cell_lines(row.description, widths[2])]
    lines = []
    for index in range(max(map(len, cells))):
        values = [cell[index] if index < len(cell) else "" for cell in cells]
        label = _fit(values[0], widths[0] - badge_width)
        label_parts = _label_fragments(row, label, "class:panel.label") if index == 0 else (
            ("class:panel.label", " " * badge_width + label),
        )
        lines.append((("class:panel.focus", marker + " " if index == 0 else "  "),)
                     + label_parts + (
            (_value_style(row), "  " + _fit(values[1], widths[1])),
            ("class:panel.muted", "  " + values[2]),
        ))
    return lines


def _label_fragments(row: PanelRow, label: str, style: str) -> tuple[tuple[str, str], ...]:
    if row.label_badge:
        return (
            ("class:choice.active.edge", "["),
            ("class:choice.active.word", row.label_badge),
            ("class:choice.active.edge", "]"),
            (style, " " + label),
        )
    return ((style, label),)


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
    footer_started = False
    for row in rows:
        footer_row = row.footer or row.effective_control is not None
        if not footer_started and footer_row:
            if lines and any(text.strip() for _style, text in lines[-1]):
                lines.append((("", ""),))
                owners.append(None)
            footer_started = True
        if row.kind == RowKind.TABLE_HEADER:
            last_section_line = len(lines)
            table_header_parts = _table_header_fragments(state.page.column_headers, width) \
                if state.page.column_headers and width >= 60 else (
                    ("class:panel.section", "  " + _fit(row.label.upper(), width - 2).rstrip()),
                )
            lines.append(table_header_parts)
            owners.append(row.id)
            continue
        if state.page.column_headers and row.kind == RowKind.NAVIGATION and not footer_row \
                and (not state.page.table_section_id
                     or row.section_id == state.page.table_section_id):
            start = len(lines)
            row_lines = _table_row_lines(row, width, row.id == state.picker.selected_id,
                                         state.page.column_headers)
            lines.extend(row_lines)
            owners.extend([row.id] * len(row_lines))
            if row.id == state.picker.selected_id:
                selected_line, context_line = start, last_section_line
            continue
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
                ("class:panel.section", heading.removesuffix(":")),
            )
            if heading.endswith(":"):
                parts += (("class:panel.heading-marker", ":"),)
            if row.description:
                if get_cwidth(heading) + get_cwidth(row.description) + 4 <= width:
                    parts += (("class:panel.muted", "  " + row.description),)
                else:
                    lines.append(parts)
                    owners.append(row.id)
                    for description in _wrapped(row.description, width - 2):
                        lines.append((("class:panel.muted", "  " + description),))
                        owners.append(row.id)
                    continue
        elif row.kind == RowKind.SEPARATOR:
            parts = (("", ""),)
        elif row.kind in {RowKind.INFO, RowKind.STATUS}:
            info_style = (
                f"class:panel.status.{row.status_tone}"
                if row.kind == RowKind.STATUS else "class:panel.muted"
            )
            if row.value:
                parts = (
                    (info_style, f"  {_fit(row.label, max(1, width // 2)).rstrip()}"),
                    (_value_style(row), f"  {row.value}"),
                )
            else:
                info_lines = _wrapped(row.label, width - 2)
                parts = (
                    ((info_style, f"  {info_lines[0]}"),)
                    if info_lines else (("", ""),)
                )
        else:
            marker = "›" if row.id == state.picker.selected_id else " "
            label_style = "class:panel.disabled" if not row.enabled else "class:panel.label"
            badge_width = get_cwidth(row.label_badge) + 3 if row.label_badge else 0
            value_style = _value_style(row)
            stacked_value = False
            stacked_description = False
            if width >= 90 or (state.page.table_section_id and width >= 60):
                label_width = min(28, max(12, width // 3))
                value_width = min(max(8, get_cwidth(value)), width - label_width - 6)
                description_width = max(0, width - label_width - value_width - 7)
                stacked_value = get_cwidth(value) > value_width
                stacked_description = description_width < 12
                parts = (
                    ("class:panel.focus", f"{marker} "),
                ) + _label_fragments(
                    row, _fit(row.display_label, max(1, label_width - badge_width)), label_style
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
                label_width = (min(28, max(14, width // 3))
                               if state.page.table_section_id else
                               max(14, width - min(20, max(8, width // 3)) - 4))
                value_width = max(1, width - label_width - 4)
                stacked_value = get_cwidth(value) > value_width
                parts = (
                    ("class:panel.focus", f"{marker} "),
                ) + _label_fragments(
                    row, _fit(row.display_label, max(1, label_width - badge_width)), label_style
                ) + _value_fragments(
                    row, "  " + _fit("" if stacked_value else value, value_width).rstrip(),
                    value_style, unicode_blocks=unicode_blocks,
                )
            else:
                label_lines = _wrapped(row.display_label, max(1, width - 2 - badge_width))
                parts = (
                    ("class:panel.focus", f"{marker} "),
                ) + _label_fragments(row, label_lines[0] if label_lines else "", label_style)
        lines.append(parts)
        owners.append(row.id)
        if row.kind in {RowKind.INFO, RowKind.STATUS} and not row.value:
            for extra in info_lines[1:]:
                lines.append(((info_style, f"  {extra}"),))
                owners.append(row.id)
        if row.id == state.picker.selected_id:
            selected_line = start
            context_line = last_section_line
        if row.selectable and width < 55:
            for label_line in label_lines[1:]:
                lines.append(((label_style, " " * (2 + badge_width) + label_line),))
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
        if row.description and (
            row.kind == RowKind.INFO
            or row.selectable and (
                (width < 90 and not (state.page.table_section_id and width >= 60))
                or stacked_description
            )
        ):
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
    header: tuple[tuple[str, str], ...] = (
        ("class:panel.header", _fit(title, max(1, width)).rstrip() + "\n"),
        ("class:panel.rule", "─" * max(1, width)),
    )
    if page.column_headers and not page.table_section_id and width >= 60:
        header += (("", "\n"),) + _table_header_fragments(page.column_headers, width)
    return header


def render_footer(
    width: int, *, search: bool, query: str = "", status: str = "", status_style: str = "",
    navigation_hints: str = "", status_fragments: tuple[tuple[str, str], ...] = (),
) -> tuple[tuple[str, str], ...]:
    hints = (
        f"/{query} · ENTER select · ESC clear"
        if search
        else navigation_hints or "↑↓ move · ENTER open/apply · SPACE toggle · / search · ESC back"
    )
    parts = status_fragments or ((status_style, status),)
    status = "".join(text for _, text in parts)
    status_width = min(get_cwidth(status), max(0, width // 2))
    hint_width = max(0, width - status_width - (2 if status else 0))
    clipped = _fit(status, status_width).rstrip()
    rendered_status = [("class:panel.muted", "  ")] if status else []
    for style, text in parts:
        if not clipped:
            break
        rendered_status.append((style, clipped[:len(text)]))
        clipped = clipped[len(text):]
    return (
        ("class:panel.rule", "─" * max(1, width) + "\n"),
        ("class:panel.muted", _fit(hints, hint_width)),
    ) + tuple(rendered_status)
