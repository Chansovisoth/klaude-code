"""Offline spinner catalog, validated appearance state, and shared animation clock."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from types import MappingProxyType

import regex
from prompt_toolkit.utils import get_cwidth

from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

DEFAULT_CUSTOM_INTERVAL = 100
MAX_FRAMES = 256


@dataclass(frozen=True)
class Spinner:
    frames: tuple[str, ...]
    interval: int

    @property
    def width(self) -> int:
        return max(get_cwidth(frame) for frame in self.frames)

    def frame_at(self, seconds: float, *, encoding: str = "utf-8") -> str:
        frame = self.frames[int(max(0, seconds) * 1000 / self.interval) % len(self.frames)]
        try:
            frame.encode(encoding)
        except (UnicodeError, LookupError):
            return "-".ljust(self.width)
        return frame + " " * (self.width - get_cwidth(frame))


def validate_interval(value: object) -> int:
    if type(value) is not int or not 16 <= value <= 10000:
        raise ValueError("Use an interval from 16 to 10000 milliseconds.")
    return value


def validate_frames(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= MAX_FRAMES:
        raise ValueError("Enter between 1 and 256 animation frames.")
    frames: list[str] = []
    for frame in value:
        if not isinstance(frame, str) or not frame or len(frame) > 256:
            raise ValueError("Each frame must contain 1–256 characters.")
        if any(
            unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} and char != "\u200d"
            for char in frame
        ):
            raise ValueError("Animation frames cannot contain terminal control characters.")
        if get_cwidth(frame[0]) == 0 or not 1 <= get_cwidth(frame) <= 80:
            raise ValueError(
                "Each frame must occupy 1–80 cells and start without a combining mark."
            )
        frames.append(frame)
    return tuple(frames)


def parse_frames(text: str) -> tuple[str, ...]:
    """JSON string entries preserve spaces; compact input uses UAX #29 graphemes."""
    if len(text) > 65536:
        raise ValueError("Spinner input is too long.")
    if text.lstrip().startswith(('"', "[")):
        try:
            parsed = json.loads(text if text.lstrip().startswith("[") else "[" + text + "]")
        except json.JSONDecodeError as exc:
            raise ValueError('Use comma-separated double-quoted frames, such as "a", "b".') from exc
        return validate_frames(parsed)
    return validate_frames(regex.findall(r"\X", text.strip()))


def parse_interval(text: str) -> int:
    if not text.strip():
        return DEFAULT_CUSTOM_INTERVAL
    try:
        value = int(text.strip())
    except ValueError as exc:
        raise ValueError("Enter an interval in milliseconds, or leave blank for 100.") from exc
    return validate_interval(value)


def _load_catalog() -> Mapping[str, Spinner]:
    raw = json.loads(files("klaude_cli").joinpath("vendor/cli_spinners/spinners.json").read_text())
    catalog = {
        name: Spinner(validate_frames(value["frames"]), validate_interval(value["interval"]))
        for name, value in raw.items()
    }
    # Klaude additions stay separate from the unchanged, pinned upstream data.
    catalog["claude"] = Spinner(("·", "✢", "✳", "✶", "✻", "✽"), DEFAULT_CUSTOM_INTERVAL)
    return MappingProxyType(catalog)


# Package data is read once at startup, never in a settings key handler.
CATALOG = _load_catalog()


@dataclass(frozen=True)
class SpinnerSettings:
    name: str = "dots"
    custom_frames: tuple[str, ...] = CATALOG["dots"].frames
    custom_interval: int = DEFAULT_CUSTOM_INTERVAL

    @property
    def animation(self) -> Spinner:
        if self.name == "custom":
            return Spinner(self.custom_frames, self.custom_interval)
        return CATALOG[self.name]


def load_spinner_settings(value: object) -> SpinnerSettings:
    if not isinstance(value, dict):
        return SpinnerSettings()
    name = value.get("name", "dots")
    if not isinstance(name, str) or name not in {*CATALOG, "custom"}:
        name = "dots"
    try:
        frames = validate_frames(value.get("custom_frames", CATALOG["dots"].frames))
        interval = validate_interval(value.get("custom_interval", DEFAULT_CUSTOM_INTERVAL))
    except ValueError:
        frames, interval = CATALOG["dots"].frames, DEFAULT_CUSTOM_INTERVAL
        if name == "custom":
            name = "dots"
    return SpinnerSettings(name, frames, interval)


def spinner_page(settings: SpinnerSettings) -> PanelPage:
    return PanelPage(
        "spinner",
        ("Settings", "Spinner"),
        (
            PanelRow(
                "custom", RowKind.NAVIGATION, "Custom",
                "Current" if settings.name == "custom" else "",
                "Edit frames and animation interval",
                selected=settings.name == "custom",
                action=PanelAction("spinner-custom"),
            ),
        )
        + tuple(
            PanelRow(
                "spinner:" + name, RowKind.CHOICE, name,
                "Current" if name == settings.name else "",
                f"{len(spinner.frames)} frames · {spinner.interval} ms",
                selected=name == settings.name,
                action=PanelAction("spinner-select", name),
            )
            for name, spinner in CATALOG.items()
        )
        + (
            PanelRow(
                "reset", RowKind.ACTION, "Reset to default",
                footer=True, action=PanelAction("spinner-reset"), control=RowControl.RESET,
            ),
            PanelRow("back", RowKind.NAVIGATION, "Back", footer=True, action=PanelAction("back")),
        ),
    )


def custom_spinner_page(spinner: Spinner) -> PanelPage:
    return PanelPage(
        "spinner-custom",
        ("Settings", "Spinner", "Custom"),
        (
            PanelRow(
                "frames",
                RowKind.ACTION,
                "Edit frames",
                f"{len(spinner.frames)} frames",
                '⠋⠙⠹⠸ or "⠋", "⠙", "⠹", "⠸"',
                action=PanelAction("spinner-frames"),
            ),
            PanelRow(
                "interval",
                RowKind.ACTION,
                "Frame interval",
                f"{spinner.interval} ms",
                "Time between animation frames",
                action=PanelAction("spinner-interval"),
            ),
            PanelRow(
                "apply",
                RowKind.ACTION,
                "Apply spinner",
                action=PanelAction("spinner-apply"),
            ),
            PanelRow("back", RowKind.NAVIGATION, "Back", footer=True, action=PanelAction("back")),
        ),
    )
