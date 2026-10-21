from datetime import UTC, datetime

import pytest
from klaude_core.settings_store import read_settings, update_settings
from klaude_core.time_settings import clock_reading, timezone_names, validate_timezone


@pytest.mark.parametrize("value", [None, True, "", "Mars/Olympus", "../UTC", "/etc/passwd",
                                   "Asia/Phnom_Penh\n", "localtime", "Factory"])
def test_invalid_timezones_are_rejected(value):
    with pytest.raises(ValueError, match="valid IANA timezone"):
        validate_timezone(value)


def test_saved_zone_and_explicit_override_do_not_change_settings(tmp_path):
    update_settings(tmp_path / "chat-preferences.json", {
        ("time_settings", "timezone"): "Asia/Phnom_Penh",
    })
    instant = datetime(2026, 12, 31, 20, 30, tzinfo=UTC)
    local = clock_reading(tmp_path, now=instant)
    assert local == {"local": "2027-01-01T03:30:00+07:00", "utc_offset": "+07:00",
                     "weekday": "Friday", "timezone": "Asia/Phnom_Penh",
                     "utc": "2026-12-31T20:30:00+00:00"}
    assert clock_reading(tmp_path, "UTC", now=instant)["local"] == instant.isoformat()
    assert read_settings(tmp_path / "chat-preferences.json")["time_settings"] == {
        "timezone": "Asia/Phnom_Penh",
    }


@pytest.mark.parametrize("instant,expected", [
    ("2026-03-08T06:59:00+00:00", "2026-03-08T01:59:00-05:00"),
    ("2026-03-08T07:01:00+00:00", "2026-03-08T03:01:00-04:00"),
    ("2026-11-01T05:30:00+00:00", "2026-11-01T01:30:00-04:00"),
    ("2026-11-01T06:30:00+00:00", "2026-11-01T01:30:00-05:00"),
])
def test_named_zone_observes_daylight_saving(tmp_path, instant, expected):
    assert clock_reading(tmp_path, "America/New_York", now=datetime.fromisoformat(instant))[
        "local"
    ] == expected


def test_automatic_uses_system_clock_without_creating_preferences(tmp_path):
    instant = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
    reading = clock_reading(tmp_path, now=instant)
    assert reading["local"] == instant.astimezone().isoformat()
    assert not (tmp_path / "chat-preferences.json").exists()
    assert "Asia/Phnom_Penh" in timezone_names() and "UTC" in timezone_names()
    with pytest.raises(ValueError, match="offset-aware"):
        clock_reading(tmp_path, now=datetime(2026, 10, 21))
