"""Normal-screen startup surfaces, without padding transcript text."""

import pytest
from klaude_cli.main import TERMINAL_CLEAR_SEQUENCE, _tui_style
from klaude_cli.terminal_surface import clear_output_surface, startup_output_surface
from prompt_toolkit.data_structures import Size
from prompt_toolkit.output.color_depth import ColorDepth
from prompt_toolkit.output.vt100 import Vt100_Output
from rich.console import Console


@pytest.mark.parametrize("width", [18, 70, 110])
@pytest.mark.parametrize("theme", ["autumn", "pastelle"])
def test_startup_blank_viewport_and_messages_use_output_background(width, theme):
    import pyte

    screen = pyte.Screen(width, 24)
    stream = pyte.Stream(screen)
    # Materialize terminal cells: pyte's ED only updates existing cells, unlike
    # a physical terminal. Also check that prior shell content is cleared.
    for row in range(24):
        screen.cursor_position(row + 1, 1)
        screen.draw("x" * width)
    screen.cursor_position(1, 1)
    writes = []

    class Terminal:
        encoding = "utf-8"

        def write(self, text):
            writes.append(text)
            stream.feed(text)

        def flush(self):
            pass

        def isatty(self):
            return True

    terminal = Terminal()
    output = Vt100_Output(
        terminal,
        lambda: Size(rows=24, columns=width),
        default_color_depth=ColorDepth.DEPTH_24_BIT,
        enable_cpr=False,
    )
    style = _tui_style(theme, "vscode-dark")
    background = style.get_attrs_for_style_str("class:output-field").bgcolor
    console = Console(
        file=terminal, force_terminal=True, color_system="truecolor", no_color=False, width=width
    )
    original_style = console.style
    with startup_output_surface(console, output, style, TERMINAL_CLEAR_SEQUENCE):
        console.print("[dim]system context: off[/]")
        console.print("[dim]git branch ready[/]")
        for row in screen.display:
            assert len(row) == width
        assert all(screen.buffer[y][x].bg == background for y in range(24) for x in range(width))
    assert console.style is original_style
    assert screen.cursor.attrs.bg == "default"

    clear_output_surface(output, style, TERMINAL_CLEAR_SEQUENCE, reserve_rows=23)
    assert screen.cursor.y == 23
    assert all(not line.strip() for line in screen.display)
    assert all(screen.buffer[y][x].bg == background for y in range(24) for x in range(width))
    assert screen.cursor.attrs.bg == "default"
    assert " " * width not in "".join(writes)
    assert "\x1b[?1049h" not in "".join(writes)


def test_startup_failure_restores_console_and_terminal_attributes():
    from prompt_toolkit.output import DummyOutput

    console = Console(style="italic")
    output = DummyOutput()
    resets = []
    output.reset_attributes = lambda: resets.append(True)
    with pytest.raises(RuntimeError, match="setup failed"):
        with startup_output_surface(
            console, output, _tui_style("autumn", "vscode-dark"), TERMINAL_CLEAR_SEQUENCE
        ):
            raise RuntimeError("setup failed")
    assert console.style == "italic"
    assert len(resets) == 2


@pytest.mark.parametrize("no_tui", [False, True])
def test_chat_themes_agent_setup_only_for_interactive_tui(monkeypatch, tmp_path, no_tui):
    from io import StringIO
    from types import SimpleNamespace

    import klaude_cli.main as cli_main
    from prompt_toolkit.output import DummyOutput

    console = Console(
        file=StringIO(), force_terminal=True, color_system="truecolor", no_color=False
    )
    monkeypatch.setattr(cli_main, "console", console)
    monkeypatch.setattr(cli_main.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_main.sys, "stdout", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(cli_main, "_clear_plain_session_view", lambda **kwargs: None)
    monkeypatch.setattr(cli_main, "load_config", lambda: SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(cli_main, "_load_last_chat_model", lambda path: "")
    monkeypatch.setattr(
        "prompt_toolkit.output.defaults.create_output", lambda **kwargs: DummyOutput()
    )

    def setup(workspace, model):
        if no_tui:
            assert console.style is None
        else:
            appearance = cli_main._load_tui_appearance(tmp_path / "appearance.json")
            expected = cli_main._tui_style(appearance.theme, appearance.text_theme)
            background = expected.get_attrs_for_style_str("class:output-field").bgcolor
            assert console.get_style(console.style).bgcolor.get_truecolor().hex == f"#{background}"
        raise RuntimeError("stop after setup surface check")

    monkeypatch.setattr(cli_main, "_build_agent", setup)
    with pytest.raises(RuntimeError, match="stop after setup surface check"):
        cli_main.chat(model="", legacy=False, no_tui=no_tui)
    assert console.style is None
