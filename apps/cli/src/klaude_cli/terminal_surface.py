"""Theme the normal terminal surface before the live application renders."""

from collections.abc import Iterator
from contextlib import contextmanager

from prompt_toolkit.output import Output
from prompt_toolkit.styles import BaseStyle
from rich.console import Console
from rich.style import Style as RichStyle


def clear_output_surface(
    output: Output, style: BaseStyle, clear_sequence: str, *, reserve_rows: int = 0
) -> None:
    """Erase and reserve blank cells with the transcript's background.

    Terminal erase operations use the current background color. Setting it before
    clearing avoids copyable space padding and keeps ordinary scrollback intact.
    """
    try:
        output.set_attributes(
            style.get_attrs_for_style_str("class:output-field"),
            output.get_default_color_depth(),
        )
        output.write_raw(clear_sequence)
        if reserve_rows:
            output.write_raw("\r\n" * reserve_rows)
    finally:
        output.reset_attributes()
        output.flush()


@contextmanager
def startup_output_surface(
    console: Console, output: Output, style: BaseStyle, clear_sequence: str
) -> Iterator[None]:
    """Give early Rich setup messages the same surface as the transcript."""
    previous_style = console.style
    background = style.get_attrs_for_style_str("class:output-field").bgcolor
    clear_output_surface(output, style, clear_sequence)
    try:
        # Appearance themes resolve to RGB colors; retain existing foreground,
        # dimming and semantic colors used by startup messages.
        surface = RichStyle(bgcolor=f"#{background}") if background else RichStyle()
        console.style = console.get_style(previous_style or "") + surface
        yield
    finally:
        console.style = previous_style
        output.reset_attributes()
        output.flush()
