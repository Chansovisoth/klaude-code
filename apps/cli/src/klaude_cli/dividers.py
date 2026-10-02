"""Transcript divider presentation and typed appearance controls."""

from __future__ import annotations

import unicodedata

from prompt_toolkit.utils import get_cwidth

from .settings_panel import PanelAction, PanelPage, PanelRow, RowControl, RowKind

DEFAULT_DIVIDER_COLOR = "same-as-input-field"
DEFAULT_DIVIDER_TEXT_COLOR = "bright-black"
DEFAULT_DIVIDER_PATTERN = "━ "
DIVIDER_PATTERNS = {
    "heavy": "━",
    "light": "─",
    "heavy-spaced": DEFAULT_DIVIDER_PATTERN,
    "light-spaced": "─ ",
}

DIVIDER_COLORS = {
    "default": ("Default", "#808080"),
    "accent": ("Accent", ""),
    "text": ("Normal text", ""),
    "red": ("Red", "ansired"),
    "orange": ("Orange", "#ff9f43"),
    "yellow": ("Yellow", "ansiyellow"),
    "green": ("Green", "ansigreen"),
    "cyan": ("Cyan", "ansicyan"),
    "blue": ("Blue", "ansiblue"),
    "purple": ("Purple", "#b084f5"),
    "magenta": ("Magenta", "ansimagenta"),
    "pink": ("Pink", "#ff80bf"),
    "bright-red": ("Bright red", "ansibrightred"),
    "bright-orange": ("Bright orange", "#ffbd73"),
    "bright-yellow": ("Bright yellow", "ansibrightyellow"),
    "bright-green": ("Bright green", "ansibrightgreen"),
    "bright-cyan": ("Bright cyan", "ansibrightcyan"),
    "bright-blue": ("Bright blue", "ansibrightblue"),
    "bright-purple": ("Bright purple", "#c8a6ff"),
    "bright-magenta": ("Bright magenta", "ansibrightmagenta"),
    "bright-pink": ("Bright pink", "#ffadd0"),
    "black": ("Black", "ansiblack"),
    "bright-black": ("Gray", "ansibrightblack"),
    "white": ("White", "ansigray"),
    "bright-white": ("Bright white", "ansiwhite"),
}
LINE_COLORS = {
    "default": DIVIDER_COLORS["default"],
    "accent": DIVIDER_COLORS["accent"],
    "same-as-text": ("Same as text", ""),
    "same-as-input-field": ("Same as input field", ""),
    **{
        key: value
        for key, value in DIVIDER_COLORS.items()
        if key not in {"default", "accent", "text"}
    },
    "text": DIVIDER_COLORS["text"],
}


def color_label(color: str, *, default: str | None = None) -> str:
    if color == default:
        return "Default"
    return LINE_COLORS.get(color, DIVIDER_COLORS["default"])[0]


def divider_styles(
    line: str,
    text: str,
    *,
    accent: str,
    foreground: str,
    input_background: str,
) -> dict[str, str]:
    def resolve(color: str) -> str:
        if color == "accent":
            return accent
        if color == "text":
            return foreground
        return DIVIDER_COLORS.get(color, DIVIDER_COLORS["default"])[1]

    label_color = resolve(text)
    return {
        "transcript.divider.text": label_color,
        "transcript.divider.rule": (
            label_color
            if line == "same-as-text"
            else input_background
            if line == "same-as-input-field"
            else resolve(line)
        ),
    }


def validate_divider_pattern(pattern: object) -> str:
    """Validate user text before it enters terminal chrome or preferences."""
    if not isinstance(pattern, str) or not 1 <= len(pattern) <= 24:
        raise ValueError("Enter 1–24 characters for the divider pattern.")
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} and char != "\u200d"
        for char in pattern
    ):
        raise ValueError("The divider pattern cannot contain control characters.")
    if not pattern.strip() or get_cwidth(pattern[0]) == 0:
        raise ValueError("Start the divider pattern with a visible character.")
    return pattern


def repeat_divider_pattern(pattern: str, width: int) -> str:
    """Fill terminal cells, retaining combining marks and joined emoji together."""
    units: list[str] = []
    for char in pattern:
        if units and (get_cwidth(char) == 0 or units[-1].endswith("\u200d")):
            units[-1] += char
        else:
            units.append(char)
    pattern_width = get_cwidth(pattern)
    if width <= 0 or pattern_width <= 0:
        return ""
    repetitions, remaining = divmod(width, pattern_width)
    result = pattern * repetitions
    for unit in units:
        cells = get_cwidth(unit)
        if cells > remaining:
            break
        result += unit
        remaining -= cells
    return result + " " * remaining


def divider_fragments(
    line: str, *, visible: bool = True, pattern: str = "━"
) -> list[tuple[str, str]] | None:
    """Keep canonical transcript text intact; decorate only known chrome rows."""
    if not line.startswith(("━━ you · ", "━━ klaude · ", "━━ Session: ")):
        return None
    content = line[3:]
    label = content.rstrip("━").rstrip()
    if not visible:
        return [("class:transcript.divider.text", label)]
    suffix = content[len(label) :]
    if pattern != "━":
        spaces = len(suffix) - len(suffix.lstrip(" "))
        suffix = " " * spaces + repeat_divider_pattern(pattern, get_cwidth(suffix) - spaces)
    return [
        ("class:transcript.divider.rule", repeat_divider_pattern(pattern, 2) + " "),
        ("class:transcript.divider.text", label),
        ("class:transcript.divider.rule", suffix),
    ]


def divider_page(
    visible: bool, line: str, text: str, pattern: str = DEFAULT_DIVIDER_PATTERN
) -> PanelPage:
    return PanelPage(
        "divider",
        ("Settings", "Divider"),
        (
            PanelRow("section:divider", RowKind.SECTION, "DIVIDER"),
            PanelRow(
                "visible",
                RowKind.TOGGLE,
                "Show divider",
                description="Turn off for better performance",
                checked=visible,
                action=PanelAction("divider-toggle"),
                section_id="section:divider",
            ),
            PanelRow(
                "line-color",
                RowKind.NAVIGATION,
                "Line color",
                color_label(line, default=DEFAULT_DIVIDER_COLOR),
                action=PanelAction("divider-colors", "line"),
                section_id="section:divider",
            ),
            PanelRow(
                "text-color",
                RowKind.NAVIGATION,
                "Text color",
                color_label(text, default=DEFAULT_DIVIDER_TEXT_COLOR),
                "Speaker, time, session ID, and duration",
                action=PanelAction("divider-colors", "text"),
                section_id="section:divider",
            ),
            PanelRow("spacer:custom", RowKind.SEPARATOR, "", section_id="section:divider"),
            PanelRow(
                "pattern", RowKind.ACTION, "Custom",
                "Current" if pattern not in DIVIDER_PATTERNS.values() else "",
                selected=pattern not in DIVIDER_PATTERNS.values(),
                action=PanelAction("divider-pattern"),
                section_id="section:divider",
            ),
        )
        + tuple(
            PanelRow(
                "pattern:" + key, RowKind.CHOICE, repr(value),
                "Current" if pattern == value else "",
                selected=pattern == value,
                action=PanelAction("divider-preset", key),
                section_id="section:divider",
            )
            for key, value in DIVIDER_PATTERNS.items()
        )
        + (
            PanelRow(
                "reset",
                RowKind.ACTION,
                "Reset to default",
                action=PanelAction("divider-reset"),
                footer=True,
                control=RowControl.RESET,
            ),
            PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("back"), footer=True),
        ),
    )


def divider_color_page(target: str, selected: str) -> PanelPage:
    colors = LINE_COLORS if target == "line" else DIVIDER_COLORS
    title = "Line color" if target == "line" else "Text color"
    rows = tuple(
        PanelRow(
            "color:" + key,
            RowKind.CHOICE,
            label,
            "Current" if key == selected else "",
            selected=key == selected,
            action=PanelAction("divider-" + target, key),
        )
        for key, (label, _color) in colors.items()
        if key != "default"
    )
    return PanelPage(
        "divider-color:" + target,
        ("Settings", "Divider", title),
        rows
        + (
            PanelRow(
                "color:default", RowKind.ACTION, "Reset to default",
                action=PanelAction("divider-" + target,
                                   DEFAULT_DIVIDER_COLOR if target == "line"
                                   else DEFAULT_DIVIDER_TEXT_COLOR),
                footer=True, control=RowControl.RESET,
            ),
        )
        + (PanelRow("back", RowKind.NAVIGATION, "Back", action=PanelAction("back"), footer=True),),
    )
