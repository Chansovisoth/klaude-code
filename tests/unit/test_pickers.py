import pytest
from klaude_cli.pickers import PickerController, PickerRow


def rows():
    return [
        PickerRow("heading", "Models", selectable=False),
        PickerRow("alpha", "Alpha"),
        PickerRow("beta", "Beta"),
        PickerRow("gamma", "Gamma", enabled=False),
        PickerRow("back", "back", exit=True),
    ]


def test_filter_clearing_restores_original_selection_not_first_row():
    picker = PickerController(rows(), "beta")
    picker.filter("Alpha")
    assert picker.selected_id == "alpha"
    picker.filter("")
    assert picker.selected_id == "beta"


def test_manual_selection_in_filtered_results_survives_clearing():
    picker = PickerController(rows(), "beta")
    picker.filter("a")
    picker.select(next(i for i, row in enumerate(picker.visible) if row.id == "gamma"))
    picker.filter("")
    assert picker.selected_id == "gamma"


@pytest.mark.parametrize("refresh", [False, True])
def test_no_results_never_automatically_selects_exit(refresh):
    picker = PickerController(rows(), "beta")
    picker.filter("zzzzzzzzzz")
    if refresh:
        picker.replace([*rows(), PickerRow("other", "Different")])
    assert picker.no_matches
    assert picker.selected_id is None
    assert not picker.visible[picker.index].selectable
    picker.filter("back")
    assert picker.selected_id == "back"


def test_refresh_reapplies_filter_and_keeps_stable_identity():
    picker = PickerController(rows(), "beta")
    picker.filter("Beta")
    picker.replace(
        [
            PickerRow("new", "New model"),
            PickerRow("beta", "Beta updated"),
            PickerRow("back", "back", exit=True),
        ]
    )
    assert picker.query == "beta"
    assert picker.selected_id == "beta"
    assert picker.visible[0].label == "Beta updated"
    assert all(row.id != "new" for row in picker.visible)


def test_refresh_losing_last_match_does_not_focus_back():
    picker = PickerController(rows(), "beta")
    picker.filter("Beta")
    picker.replace([PickerRow("other", "Other"), PickerRow("back", "back", exit=True)])
    assert picker.no_matches
    assert picker.selected_id is None


def test_unavailable_option_remains_selectable_after_availability_change():
    picker = PickerController([PickerRow("custom", "Custom", enabled=False)], "custom")
    assert picker.visible[picker.index].selectable
    picker.replace([PickerRow("custom", "Custom", enabled=True)])
    assert picker.selected_id == "custom"
    assert picker.visible[picker.index].enabled


def test_refresh_preserves_selected_viewport_offset_and_clamps_after_deletion():
    options = [PickerRow(str(i), f"Option {i}") for i in range(50)]
    picker = PickerController(options, "40")
    top = picker.viewport(8)
    offset = picker.index - top
    picker.replace([PickerRow("new", "Inserted"), *options])
    assert picker.index - picker.viewport(8) == offset
    picker.replace([options[40]])
    assert picker.index == picker.viewport(8) == 0


def test_first_option_in_section_reveals_heading_and_notes():
    picker = PickerController([
        PickerRow("prior", "Previous"),
        PickerRow("heading", "MCP Servers", selectable=False),
        PickerRow("note", "Configured tools", selectable=False),
        PickerRow("first", "context7"),
        PickerRow("second", "firecrawl"),
        PickerRow("later", "Later"),
    ], "second")
    picker.scroll_top = 3
    picker.select(3)
    assert picker.viewport(4) == 1
    assert [row.label for row in picker.visible[picker.scroll_top:picker.scroll_top + 4]] == [
        "MCP Servers", "Configured tools", "context7", "firecrawl"
    ]
    picker.scroll_top = 3
    assert picker.viewport(2) == 2


def test_missing_selection_has_safe_fallback():
    picker = PickerController(rows(), "beta")
    picker.replace([PickerRow("heading", "Heading", selectable=False), PickerRow("new", "New")])
    assert picker.selected_id == "new"
    assert picker.index == 1


def test_decorations_are_not_search_candidates():
    picker = PickerController(rows(), "alpha")
    picker.filter("Models")
    assert picker.no_matches
