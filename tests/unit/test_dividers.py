from datetime import datetime

import pytest
from klaude_cli.dividers import DIVIDER_COLORS, divider_color_page, divider_fragments, divider_page
from klaude_cli.main import (
    TUI_THEME_STYLES,
    TranscriptLexer,
    TUIAppearance,
    _load_tui_appearance,
    _message_divider,
    _save_tui_appearance,
    _session_divider,
    _tui_style,
)
from klaude_cli.settings_panel import PanelState, render_body
from prompt_toolkit.document import Document
from prompt_toolkit.utils import get_cwidth


@pytest.mark.parametrize("visible", [False, True])
def test_divider_visibility_retains_metadata_and_ignores_body_rules(visible):
    stamp = datetime(2026, 10, 2, 12, 0)
    message = _message_divider("klaude", width=100, timestamp=stamp, suffix="worked for 11s")
    session = _session_divider("public-session-id", width=100)
    lexer = TranscriptLexer(lambda: visible)
    lines = lexer.lex_document(Document(message + "\n" + session))
    for index, original in enumerate((message, session)):
        rendered = "".join(text for _style, text in lines(index))
        assert ("━" in rendered) is visible
        if visible:
            assert rendered == original
        else:
            assert rendered == original[3:].rstrip("━").rstrip()
    assert "worked for 11s" in "".join(text for _style, text in lines(0))
    assert divider_fragments("━━━━━━━━━━━━━━━━", visible=visible) is None
    assert divider_fragments("ordinary answer", visible=visible) is None


@pytest.mark.parametrize("theme", TUI_THEME_STYLES)
def test_divider_accent_and_same_as_text_follow_active_theme(theme):
    style = _tui_style(
        theme, "vscode-dark", divider_color="same-as-text", divider_text_color="accent"
    )
    line = style.get_attrs_for_style_str("class:transcript.divider.rule").color
    text = style.get_attrs_for_style_str("class:transcript.divider.text").color
    accent = style.get_attrs_for_style_str("class:panel.focus").color
    assert line == text == accent
    normal = _tui_style(theme, "vscode-dark", divider_text_color="text")
    assert normal.get_attrs_for_style_str("class:transcript.divider.text").color == (
        normal.get_attrs_for_style_str("class:output-field").color
    )
    input_color = _tui_style(theme, "vscode-dark", divider_color="same-as-input-field")
    assert input_color.get_attrs_for_style_str("class:transcript.divider.rule").color == (
        input_color.get_attrs_for_style_str("class:input-field").bgcolor
    )


@pytest.mark.parametrize("color", DIVIDER_COLORS)
def test_divider_palette_resolves_valid_terminal_styles(color):
    style = _tui_style("autumn", "vscode-dark", divider_color=color, divider_text_color=color)
    assert style.get_attrs_for_style_str("class:transcript.divider.rule").color == (
        style.get_attrs_for_style_str("class:transcript.divider.text").color
    )


@pytest.mark.parametrize("line_color", ["same-as-text", "same-as-input-field"])
def test_divider_persistence_is_scoped_and_validates_untrusted_preferences(tmp_path, line_color):
    path = tmp_path / "appearance.json"
    path.write_text('{"theme":"hacker-green","text_theme":"monokai","future":1}')
    value = TUIAppearance(
        divider_visible=False, divider_color=line_color, divider_text_color="cyan"
    )
    _save_tui_appearance(
        path, value, fields=("divider_visible", "divider_color", "divider_text_color")
    )
    saved = _load_tui_appearance(path)
    assert saved.theme == "hacker-green"
    assert saved.text_theme == "monokai"
    assert not saved.divider_visible
    assert saved.divider_color == line_color
    assert saved.divider_text_color == "cyan"
    _save_tui_appearance(path, TUIAppearance(theme="autumn"), fields=("theme",))
    assert _load_tui_appearance(path).divider_text_color == "cyan"
    path.write_text('{"divider":{"visible":"false","color":[],"text_color":"same-as-text"}}')
    assert _load_tui_appearance(path) == TUIAppearance()


@pytest.mark.parametrize("width", [18, 36, 70, 110])
@pytest.mark.parametrize("pattern", ["━", "∘₊✧", "x" * 24])
def test_divider_typed_pages_filter_and_render_at_terminal_width(width, pattern):
    state = PanelState(divider_page(False, "same-as-text", "red", pattern))
    assert state.page.breadcrumb == ("Settings", "Divider")
    assert next(row for row in state.page.rows if row.id == "pattern").label == "Custom"
    assert not any(row.id == "scope" for row in state.page.rows)
    assert state.row().checked is False
    body = render_body(state, width)
    assert any("[■  ] OFF" in "".join(text for _style, text in line) for line in body.lines)
    assert all(get_cwidth("".join(text for _style, text in line)) <= width for line in body.lines)
    colors = divider_color_page("line", "same-as-text")
    assert any(row.selected and row.id == "color:same-as-text" for row in colors.rows)
    assert not any(row.id == "color:same-as-text" for row in divider_color_page("text", "red").rows)
    assert any(row.id == "color:same-as-input-field" for row in colors.rows)


@pytest.mark.parametrize("pattern", ["━", "-", "∘₊✧", "界", "e\u0301", " ✧ ", "👩\u200d💻"])
@pytest.mark.parametrize("width", [0, 1, 2, 18, 36, 70, 110])
def test_divider_pattern_repeats_without_exceeding_terminal_cells(pattern, width):
    from klaude_cli.dividers import repeat_divider_pattern, validate_divider_pattern

    assert validate_divider_pattern(pattern) == pattern
    result = repeat_divider_pattern(pattern, width)
    assert get_cwidth(result) == width
    if width >= get_cwidth(pattern):
        assert result.startswith(pattern)
    assert not result.endswith("\u200d")
    if pattern == "∘₊✧":
        assert result == (pattern * (width // 3)) + pattern[: width % 3]
    if pattern == "e\u0301":
        assert result == pattern * width


@pytest.mark.parametrize(
    "pattern",
    [
        "",
        " " * 24,
        "a" * 25,
        "\n",
        "x\t",
        "\x1b[31m",
        "\u0301x",
        "\u202ex",
        "x\u2028y",
        None,
        [],
        1,
    ],
)
def test_divider_pattern_rejects_invalid_text_in_editor_and_saved_preferences(tmp_path, pattern):
    import json

    from klaude_cli.dividers import validate_divider_pattern

    with pytest.raises(ValueError):
        validate_divider_pattern(pattern)
    path = tmp_path / "appearance.json"
    path.write_text(json.dumps({"divider": {"pattern": pattern}}))
    assert _load_tui_appearance(path).divider_pattern == "━ "


def test_divider_pattern_persistence_is_field_scoped_and_preserves_spaces(tmp_path):
    from klaude_cli.dividers import validate_divider_pattern

    assert validate_divider_pattern("x" * 24) == "x" * 24
    path = tmp_path / "appearance.json"
    _save_tui_appearance(path, TUIAppearance(divider_color="orange"))
    _save_tui_appearance(path, TUIAppearance(divider_pattern=" ✧ "), fields=("divider_pattern",))
    loaded = _load_tui_appearance(path)
    assert loaded.divider_pattern == " ✧ "
    assert loaded.divider_color == "orange"
    _save_tui_appearance(path, TUIAppearance(theme="autumn"), fields=("theme",))
    assert _load_tui_appearance(path).divider_pattern == " ✧ "


@pytest.mark.parametrize("width", [18, 36, 70, 110])
def test_divider_pattern_decorates_chrome_without_modifying_metadata_or_transcript(width):
    pattern = "∘₊✧"
    original = _message_divider("klaude", width=width, suffix="worked for 11s")
    lexer = TranscriptLexer(divider_pattern=lambda: pattern)
    fragments = lexer.lex_document(Document(original))(0)
    rendered = "".join(text for _, text in fragments)
    assert "worked for 11s" in rendered
    assert get_cwidth(rendered) == get_cwidth(original)
    assert "━" not in rendered
    assert fragments[1][1] == original[3:].rstrip("━").rstrip()
    assert pattern in fragments[2][1] or get_cwidth(fragments[2][1]) < 3
    assert divider_fragments("answer contains ━", pattern=pattern) is None
    hidden = divider_fragments(original, visible=False, pattern=pattern)
    assert hidden == [("class:transcript.divider.text", fragments[1][1])]


def test_divider_presets_order_default_and_existing_saved_pattern(tmp_path):
    page = divider_page(True, "default", "default")
    rows = [row for row in page.rows if row.selectable and not row.footer]
    assert [row.label for row in rows] == [
        "Show divider", "Line color", "Text color", "Custom",
        "'━'", "'─'", "'━ '", "'─ '",
    ]
    assert [row.id for row in page.rows if row.selected] == ["pattern:heavy-spaced"]
    assert not any(row.id == "default" for row in page.rows)
    assert next(row for row in page.rows if row.id == "reset").action.kind == "divider-reset"
    path = tmp_path / "appearance.json"
    assert _load_tui_appearance(path).divider_pattern == "━ "
    path.write_text('{"divider":{"pattern":"━"}}')
    assert _load_tui_appearance(path).divider_pattern == "━"


def test_divider_default_line_color_matches_input_and_preserves_saved_color(tmp_path):
    path = tmp_path / "appearance.json"
    assert TUIAppearance().divider_color == "same-as-input-field"
    assert _load_tui_appearance(path).divider_color == "same-as-input-field"
    style = _tui_style("pastelle-azure", "vscode-dark")
    assert style.get_attrs_for_style_str("class:transcript.divider.rule").color == (
        style.get_attrs_for_style_str("class:input-field").bgcolor
    )
    path.write_text('{"divider":{"color":"default"}}')
    assert _load_tui_appearance(path).divider_color == "default"
