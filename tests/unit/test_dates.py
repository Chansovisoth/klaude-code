from datetime import date

from klaude_core.dates import (
    find_establishment_date,
    operating_duration_since,
    parse_month_day_year,
)


def test_operating_duration_rounds_october_2005_to_august_2026():
    duration = operating_duration_since(date(2005, 10, 10), date(2026, 8, 2))

    assert duration.completed_years == 20
    assert duration.approximate_label == "20 years and 10 months"
    assert duration.next_anniversary == date(2026, 10, 10)


def test_establishment_date_parser_prefers_grounded_established_claim():
    parsed = find_establishment_date(
        "American Intercon School was established on October 10, 2005. "
        "Its 18th anniversary was celebrated in 2023."
    )

    assert parsed == date(2005, 10, 10)
    assert parse_month_day_year("October 10, 2005") == date(2005, 10, 10)
