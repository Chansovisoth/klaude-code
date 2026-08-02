"""Small deterministic date helpers for grounded answer support."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

MONTH_DAY_YEAR_RE = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|August|September|October|"
    r"November|December"
    r")\s+([0-9]{1,2}),\s*([0-9]{4})\b",
    re.IGNORECASE,
)
ESTABLISHMENT_DATE_RE = re.compile(
    r"(?i)\b(?:established|founded|opened|started)\b"
    r"(?:\s+(?:on|in|at))?\s+"
    r"("
    r"(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+[0-9]{1,2},\s*[0-9]{4}"
    r")"
)


@dataclass(frozen=True)
class OperatingDuration:
    start: date
    as_of: date
    completed_years: int
    approximate_years: int
    approximate_months: int
    next_anniversary: date

    @property
    def approximate_label(self) -> str:
        if self.approximate_months:
            return f"{self.approximate_years} years and {self.approximate_months} months"
        return f"{self.approximate_years} years"


def parse_month_day_year(value: str) -> date | None:
    match = MONTH_DAY_YEAR_RE.search(value)
    if not match:
        return None
    month_name, day_value, year_value = match.groups()
    month = _month_number(month_name)
    day = int(day_value)
    year = int(year_value)
    try:
        return date(year, month, day)
    except ValueError:
        return None


def find_establishment_date(text: str) -> date | None:
    for match in ESTABLISHMENT_DATE_RE.finditer(text):
        parsed = parse_month_day_year(match.group(1))
        if parsed:
            return parsed
    return None


def operating_duration_since(start: date, as_of: date) -> OperatingDuration:
    if as_of < start:
        raise ValueError("as_of must be on or after start")
    completed_years = as_of.year - start.year
    if (as_of.month, as_of.day) < (start.month, start.day):
        completed_years -= 1

    completed_months = (as_of.year - start.year) * 12 + (as_of.month - start.month)
    if as_of.day < start.day:
        completed_months -= 1
    completed_months = max(0, completed_months)

    anchor = _add_months(start, completed_months)
    if (as_of - anchor).days >= 15:
        completed_months += 1

    return OperatingDuration(
        start=start,
        as_of=as_of,
        completed_years=max(0, completed_years),
        approximate_years=completed_months // 12,
        approximate_months=completed_months % 12,
        next_anniversary=_next_anniversary(start, as_of),
    )


def _month_number(name: str) -> int:
    return list(calendar.month_name).index(name[:1].upper() + name[1:].lower())


def _add_months(value: date, months: int) -> date:
    year = value.year + (value.month - 1 + months) // 12
    month = (value.month - 1 + months) % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _next_anniversary(start: date, as_of: date) -> date:
    candidate = _safe_anniversary(start, as_of.year)
    if candidate <= as_of:
        candidate = _safe_anniversary(start, as_of.year + 1)
    return candidate


def _safe_anniversary(start: date, year: int) -> date:
    day = min(start.day, calendar.monthrange(year, start.month)[1])
    return date(year, start.month, day)
