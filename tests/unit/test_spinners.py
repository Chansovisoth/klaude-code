import hashlib
import json
from importlib.resources import files

import pytest
from klaude_cli.main import TUIAppearance, _load_tui_appearance, _save_tui_appearance
from klaude_cli.settings_panel import PanelState, render_body
from klaude_cli.spinners import (
    CATALOG,
    Spinner,
    SpinnerSettings,
    load_spinner_settings,
    parse_frames,
    parse_interval,
    spinner_page,
)
from prompt_toolkit.utils import get_cwidth


@pytest.mark.parametrize(
    "text,expected",
    [
        ("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", tuple("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")),
        ('"⠋", "⠙", "⠹"', ("⠋", "⠙", "⠹")),
        (
            '"⢎⡰", "⢎⡡", "⢎⡑", "⢎⠱", "⠎⡱", "⢊⡱", "⢌⡱", "⢆⡱"',
            ("⢎⡰", "⢎⡡", "⢎⡑", "⢎⠱", "⠎⡱", "⢊⡱", "⢌⡱", "⢆⡱"),
        ),
        ('" a ", " ", "b,c"', (" a ", " ", "b,c")),
        ('["a", "b"]', ("a", "b")),
        ("e\u0301👩🏽\u200d💻🇺🇸क्ष", ("e\u0301", "👩🏽\u200d💻", "🇺🇸", "क्ष")),
    ],
)
def test_custom_frames_parse_graphemes_and_preserve_explicit_entries(text, expected):
    assert parse_frames(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        '""',
        "[]",
        '"a",',
        "[1]",
        '"a" "b"',
        '"a\\n"',
        '"\\u001b[31m"',
        "\u202ex",
        '"' + "x" * 81 + '"',
        "x" * 257,
    ],
)
def test_invalid_frames_rejected_cleanly(text):
    with pytest.raises(ValueError):
        parse_frames(text)


@pytest.mark.parametrize(
    "text,interval", [("", 100), (" ", 100), ("16", 16), ("80", 80), ("10000", 10000)]
)
def test_custom_interval_default_and_bounds(text, interval):
    assert parse_interval(text) == interval


@pytest.mark.parametrize("text", ["0", "-1", "15", "10001", "1.5", "fast"])
def test_invalid_intervals_rejected(text):
    with pytest.raises(ValueError):
        parse_interval(text)


def test_vendored_catalog_retains_pinned_frames_intervals_and_license():
    root = files("klaude_cli").joinpath("vendor/cli_spinners")
    data = root.joinpath("spinners.json").read_bytes()
    assert (
        hashlib.sha256(data).hexdigest()
        == "91b0d44a709e836adc24de83f8b999dfd670a0e25037931d8c5186bb9e923a2b"
    )
    raw = json.loads(data)
    assert len(raw) == 90
    assert set(CATALOG) == {*raw, "claude"}
    for name, value in raw.items():
        assert CATALOG[name].frames == tuple(value["frames"])
        assert CATALOG[name].interval == value["interval"]
    assert "Copyright (c) Sindre Sorhus" in root.joinpath("license").read_text()


def test_claude_spinner_selection_persists_and_animates(tmp_path):
    frames = ("·", "✢", "✳", "✶", "✻", "✽")
    spinner = CATALOG["claude"]
    assert spinner.frames == frames
    assert spinner.interval == 100
    assert tuple(spinner.frame_at(index * 0.1 + 0.001) for index in range(6)) == frames
    assert spinner.frame_at(0.601) == frames[0]
    path = tmp_path / "appearance.json"
    _save_tui_appearance(path, TUIAppearance(spinner=SpinnerSettings("claude")))
    assert _load_tui_appearance(path).spinner.animation == spinner
    row = next(
        row for row in spinner_page(SpinnerSettings("claude")).rows if row.id == "spinner:claude"
    )
    assert row.selected
    assert row.value == "Current"
    assert row.action.target == "claude"


def test_frame_clock_preserves_multi_character_frames_padding_and_encoding():
    spinner = Spinner(("ab", "x", "界"), 200)
    assert spinner.frame_at(0) == "ab"
    assert spinner.frame_at(0.199) == "ab"
    assert spinner.frame_at(0.2) == "x "
    assert spinner.frame_at(0.4) == "界"
    assert spinner.frame_at(0.6) == "ab"
    assert spinner.frame_at(0.4, encoding="ascii") == "- "
    assert all(get_cwidth(spinner.frame_at(t)) == 2 for t in (0, 0.2, 0.4))


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"name": "missing"},
        {"name": []},
        {"name": "custom", "custom_frames": []},
        {"name": "custom", "custom_frames": ["\x1b"]},
        {"name": "custom", "custom_interval": True},
    ],
)
def test_invalid_saved_spinners_fall_back_safely(value):
    assert load_spinner_settings(value) == SpinnerSettings()


def test_spinner_persistence_is_field_scoped_and_custom_frames_survive_builtin_selection(tmp_path):
    path = tmp_path / "appearance.json"
    settings = SpinnerSettings("custom", (" ab ", "界"), 240)
    _save_tui_appearance(path, TUIAppearance(theme="hacker-green", spinner=settings))
    assert _load_tui_appearance(path).spinner == settings
    _save_tui_appearance(
        path, TUIAppearance(spinner=SpinnerSettings("dots2")), fields=("spinner_name",)
    )
    loaded = _load_tui_appearance(path)
    assert loaded.theme == "hacker-green"
    assert loaded.spinner == SpinnerSettings("dots2", settings.custom_frames, 240)
    _save_tui_appearance(path, TUIAppearance(theme="autumn"), fields=("theme",))
    assert _load_tui_appearance(path).spinner == loaded.spinner


@pytest.mark.parametrize("width", [18, 36, 70, 110])
def test_spinner_catalog_filter_and_responsive_rows(width):
    page = spinner_page(SpinnerSettings("dots2"))
    assert len([row for row in page.rows if row.kind == "choice"]) == len(CATALOG)
    state = PanelState(page, "spinner:dots2")
    state.filter("dots2")
    state.replace(spinner_page(SpinnerSettings("dots2")))
    assert state.row().id == "spinner:dots2"
    assert state.picker.query == "dots2"
    assert all(
        get_cwidth("".join(text for _, text in line)) <= width
        for line in render_body(state, width).lines
    )
