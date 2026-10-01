"""Stable picker identity, ranked filtering, and viewport state without TUI I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class PickerRow:
    id: str
    label: str
    selectable: bool = True
    exit: bool = False
    enabled: bool = True


def match_score(value: str, query: str) -> float:
    label = value.casefold()
    if label == query:
        return 4.0
    if label.startswith(query):
        return 3.0
    words = re.findall(r"[\w.+-]+", label)
    if any(word.startswith(query) for word in words):
        return 2.5
    if query in label:
        return 2.0
    return max(
        [SequenceMatcher(None, query, label).ratio()]
        + [SequenceMatcher(None, query, word).ratio() for word in words]
    )


class PickerController:
    def __init__(self, rows: list[PickerRow], default_id: str):
        self.rows = rows
        self.visible = list(rows)
        self.query = ""
        self.selected_id: str | None = default_id
        self.filter_anchor = default_id
        self.scroll_top = 0
        self.no_matches = False
        self._choose(default_id)

    @property
    def index(self) -> int:
        return next(
            (index for index, row in enumerate(self.visible) if row.id == self.selected_id), 0
        )

    def select(self, index: int) -> None:
        if not 0 <= index < len(self.visible) or not self.visible[index].selectable:
            return
        row = self.visible[index]
        if row.id != self.selected_id:
            self.selected_id = row.id
            if not row.exit:
                self.filter_anchor = row.id

    def focus(self, identity: str) -> None:
        """Restore a known navigation target, revealing it if a stale filter hides it."""
        if not any(row.id == identity and row.selectable for row in self.rows):
            return
        if not any(row.id == identity for row in self.visible):
            self.filter("")
        self._choose(identity)
        self.filter_anchor = identity

    def _choose(self, preferred: str | None) -> None:
        selectable = [row for row in self.visible if row.selectable]
        self.selected_id = next(
            (row.id for row in selectable if row.id == preferred),
            selectable[0].id if selectable else None,
        )

    def _filter_rows(self) -> None:
        if not self.query:
            self.visible = list(self.rows)
            self.no_matches = False
            return
        ranked = [
            (match_score(row.label, self.query), index, row)
            for index, row in enumerate(self.rows)
            if row.selectable and not row.exit
        ]
        ranked = [item for item in ranked if item[0] >= 0.45]
        ranked.sort(key=lambda item: (-item[0], item[1]))
        matches = [row for _, _, row in ranked[:50]]
        exits = [row for row in self.rows if row.exit]
        if explicit := [row for row in exits if row.label.casefold() == self.query]:
            self.no_matches = False
            self.visible = explicit
            return
        self.no_matches = not matches
        self.visible = (
            [*matches, *exits]
            if matches
            else [PickerRow("no-matches", "\0info:No matching options", selectable=False), *exits]
        )

    def filter(self, query: str) -> None:
        query = " ".join(query.casefold().split())
        if query == self.query:
            return
        if not self.query:
            self.filter_anchor = self.selected_id or self.filter_anchor
        self.query = query
        self._filter_rows()
        if self.no_matches:
            # Do not automatically focus Back/Cancel when a search finds nothing.
            self.selected_id = None
        else:
            self._choose(self.filter_anchor if not query else None)
        self.scroll_top = 0

    def replace(self, rows: list[PickerRow]) -> None:
        if rows == self.rows:
            return
        offset = self.index - self.scroll_top
        previous = self.selected_id
        previous_exit = any(row.id == previous and row.exit for row in self.visible)
        self.rows = rows
        self._filter_rows()
        if self.no_matches:
            self.selected_id = previous if previous_exit else None
        else:
            self._choose(previous)
        self.scroll_top = max(0, self.index - offset)

    def viewport(self, height: int) -> int:
        height = max(1, height)
        if self.index < self.scroll_top:
            self.scroll_top = self.index
        elif self.index >= self.scroll_top + height:
            self.scroll_top = self.index - height + 1
        # When the selected option begins a section, keep its immediately
        # preceding heading and notes visible if the viewport can fit them.
        if self.visible and self.visible[self.index].selectable:
            section_start = self.index
            while section_start > 0 and not self.visible[section_start - 1].selectable:
                section_start -= 1
            if section_start < self.index:
                self.scroll_top = min(
                    self.scroll_top, max(section_start, self.index - height + 1)
                )
        self.scroll_top = min(self.scroll_top, max(0, len(self.visible) - height))
        return self.scroll_top
