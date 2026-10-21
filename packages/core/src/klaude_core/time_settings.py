"""Profile timezone preferences and local, network-free clock readings."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from .runtime_context import detect_iana_timezone
from .settings_store import read_settings

AUTOMATIC_TIMEZONE = "auto"


def validate_timezone(value: object) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("Choose Automatic or a valid IANA timezone")
    if value not in {AUTOMATIC_TIMEZONE, "UTC"}:
        if value not in timezone_names():
            raise ValueError("Choose Automatic or a valid IANA timezone")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Choose Automatic or a valid IANA timezone") from None
    return value


@lru_cache(maxsize=1)
def timezone_names() -> tuple[str, ...]:
    return tuple(sorted({"UTC", *available_timezones()} - {"localtime", "Factory"}))


def configured_timezone(data_dir: Path) -> str:
    section = read_settings(data_dir / "chat-preferences.json").get("time_settings", {})
    if not isinstance(section, dict):
        raise ValueError("Date and time settings are invalid")
    return validate_timezone(section.get("timezone", AUTOMATIC_TIMEZONE))


def clock_reading(
    data_dir: Path, timezone: str | None = None, *, now: datetime | None = None,
) -> dict[str, str]:
    selected = configured_timezone(data_dir) if timezone is None else validate_timezone(timezone)
    instant = now if now is not None else datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("Clock readings require an offset-aware instant")
    if selected == AUTOMATIC_TIMEZONE:
        local = instant.astimezone()
        label = f"System ({local.tzname() or 'local time'})"
        # Reuse local system detection, but keep the actual host clock and
        # offset authoritative if its configuration files disagree.
        system_zone = os.environ.get("TZ", "").removeprefix(":") or detect_iana_timezone()
        if system_zone:
            try:
                zone = ZoneInfo(system_zone)
                if instant.astimezone(zone).utcoffset() == local.utcoffset():
                    label = system_zone
            except (ZoneInfoNotFoundError, ValueError):
                pass
    else:
        local = instant.astimezone(UTC if selected == "UTC" else ZoneInfo(selected))
        label = selected
    offset = local.strftime("%z")
    return {"local": local.isoformat(timespec="seconds"),
            "utc": instant.astimezone(UTC).isoformat(timespec="seconds"),
            "timezone": label, "utc_offset": f"{offset[:3]}:{offset[3:]}",
            "weekday": local.strftime("%A")}


def current_time(data_dir: Path, timezone: str | None = None) -> str:
    reading = clock_reading(data_dir, timezone)
    return (f"{reading['weekday']}, {reading['local']}\n"
            f"Timezone: {reading['timezone']} (UTC{reading['utc_offset']})\n"
            f"UTC: {reading['utc']}")
